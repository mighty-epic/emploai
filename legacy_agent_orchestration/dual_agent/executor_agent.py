"""
Executor Agent - Stateless Action/Observation Executor
Receives tools and ONE request, executes it, reports result.
Memory is wiped after every request.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List

from openai import OpenAI
import anthropic

from .schemas import (
    ExecutorRequest, ExecutorResponse, RequestType,
    ObservationResult, ActionResult, ObservationMethod, ActionType
)

# Try to import observation/action tools
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import pywinauto
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    import mss
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


# ============================================================
# EXECUTOR TOOLS DEFINITION
# ============================================================

EXECUTOR_TOOLS = [
    # Observation tools
    {
        "type": "function",
        "function": {
            "name": "observe_browser",
            "description": "Get browser page state: URL, title, visible elements via Selenium",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_screenshot": {"type": "boolean", "default": True}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "observe_desktop",
            "description": "Get desktop state: active window, visible elements via pywinauto",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_title": {"type": "string", "description": "Optional: focus on specific window"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "observe_screen_ocr",
            "description": "Read all visible text from screen via OCR",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screenshot",
            "description": "Take a screenshot of current screen",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Optional: 'full' or 'active_window'"}
                }
            }
        }
    },
    # Action tools
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click on an element by description, text, or coordinates",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Element description or visible text"},
                    "x": {"type": "number", "description": "Optional: x coordinate"},
                    "y": {"type": "number", "description": "Optional: y coordinate"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into focused element or specified target",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "target": {"type": "string", "description": "Optional: element to type into"},
                    "clear_first": {"type": "boolean", "default": False}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a keyboard key",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key to press (enter, tab, escape, etc.)"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the page or element",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "default": 3}
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Navigate browser to URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "focus_window",
            "description": "Bring a window to foreground",
            "parameters": {
                "type": "object",
                "properties": {
                    "window_title": {"type": "string"}
                },
                "required": ["window_title"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "report_result",
            "description": "Report the result of observation or action back to the planner",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "summary": {"type": "string", "description": "Brief summary of what was observed/done"},
                    "details": {"type": "object", "description": "Structured details"},
                    "impossible": {"type": "boolean", "default": False},
                    "impossible_reason": {"type": "string"}
                },
                "required": ["success", "summary"]
            }
        }
    }
]


# ============================================================
# EXECUTOR SYSTEM PROMPT
# ============================================================

EXECUTOR_SYSTEM_PROMPT = """You are an EXECUTOR agent. You have NO MEMORY of previous requests.

You receive ONE request and must fulfill it using the tools available, then report the result.

RULES:
1. You have NO context about previous actions or the overall task.
2. Each request is independent - treat the current screen state as your starting point.
3. Execute EXACTLY what is requested.
4. If a request is an ACTION (click, type, etc.), your priority is to REPORT THE RESULT OF THAT ACTION. Do not spend excessive time observing unrelated elements after the action is done.
5. If a request is impossible (element not found, window blocked), report it honestly.

DESKTOP CONTEXT:
- You are running on Windows. 
- Often, a terminal or IDE (like 'Antigravity' or 'VS Code') might be in focus, covering the desktop.
- If the requested target (e.g., 'Spotify', 'Taskbar') is not visible in the current active window, search for it across ALL windows or minimize the current window if necessary to see the desktop.
- When observing the 'desktop', look for icons, the taskbar, the start menu, and the system tray.

REPORTING:
- Always use the 'report_result' tool to finalize your response.
- Your summary must clearly state if the action succeeded or failed.
- If observing, your summary should highlight the most relevant targets found.
"""


class ExecutorAgent:
    """
    Stateless Executor Agent.
    Each call is independent - no memory between calls.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        screenshot_dir: str = "test_outputs/executor_screenshots"
    ):
        self.model = model
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Browser instance (managed externally)
        self.driver: Optional[webdriver.Chrome] = None
        
        # Setup LLM client
        self.client = self._setup_client()
    
    def _setup_client(self):
        """Setup OpenAI client."""
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def set_browser(self, driver: webdriver.Chrome):
        """Set browser instance for browser-based tasks."""
        self.driver = driver
    
    def execute(self, request: ExecutorRequest) -> ExecutorResponse:
        """
        Execute a single request with fresh context.
        This is the main entry point - each call is stateless.
        """
        # Build the prompt from request
        request_prompt = request.to_prompt()
        
        # Call LLM with tools
        messages = [
            {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
            {"role": "user", "content": f"REQUEST: {request_prompt}"}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=EXECUTOR_TOOLS,
                tool_choice="auto",
                max_tokens=2000
            )
            
            # Process tool calls
            return self._process_response(response, request)
            
        except Exception as e:
            return ExecutorResponse(
                request_type=request.request_type,
                impossible=True,
                impossible_reason=f"LLM call failed: {str(e)}"
            )
    
    def _process_response(self, response, request: ExecutorRequest) -> ExecutorResponse:
        """Process LLM response and execute tools."""
        message = response.choices[0].message
        
        observation_result = None
        action_result = None
        final_report = None
        
        # Execute each tool call
        if message.tool_calls:
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                result = self._execute_tool(func_name, func_args)
                
                # Track results by type
                if func_name.startswith("observe_") or func_name == "capture_screenshot":
                    observation_result = result
                elif func_name == "report_result":
                    final_report = result
                else:
                    action_result = result
        
        # Build response
        if final_report:
            return self._build_response_from_report(final_report, request)
        elif observation_result:
            return ExecutorResponse(
                request_type=RequestType.OBSERVE,
                observation=observation_result
            )
        elif action_result:
            return ExecutorResponse(
                request_type=RequestType.ACTION,
                action=action_result
            )
        else:
            return ExecutorResponse(
                request_type=request.request_type,
                impossible=True,
                impossible_reason="No tools executed or no result reported"
            )
    
    def _execute_tool(self, name: str, args: Dict) -> Any:
        """Execute a single tool and return result."""
        
        # Observation tools
        if name == "observe_browser":
            return self._observe_browser(args.get("include_screenshot", True))
        elif name == "observe_desktop":
            return self._observe_desktop(args.get("window_title"))
        elif name == "observe_screen_ocr":
            return self._observe_ocr()
        elif name == "capture_screenshot":
            return self._capture_screenshot(args.get("region", "full"))
        
        # Action tools
        elif name == "click_element":
            return self._click(args.get("target"), args.get("x"), args.get("y"))
        elif name == "type_text":
            return self._type_text(args.get("text"), args.get("target"), args.get("clear_first", False))
        elif name == "press_key":
            return self._press_key(args.get("key"))
        elif name == "scroll":
            return self._scroll(args.get("direction"), args.get("amount", 3))
        elif name == "navigate_to":
            return self._navigate(args.get("url"))
        elif name == "focus_window":
            return self._focus_window(args.get("window_title"))
        
        # Report
        elif name == "report_result":
            return args  # Just return the report data
        
        return {"error": f"Unknown tool: {name}"}
    
    # ============================================================
    # OBSERVATION IMPLEMENTATIONS
    # ============================================================
    
    def _observe_browser(self, include_screenshot: bool = True) -> ObservationResult:
        """Get browser state via Selenium."""
        if not self.driver:
            return ObservationResult(
                success=False,
                method_used="browser",
                error="No browser instance available"
            )
        
        try:
            elements = []
            
            # Get interactive elements
            for selector, role in [
                ("a", "link"),
                ("button", "button"),
                ("input", "input"),
                ("[role='button']", "button"),
                ("[onclick]", "clickable")
            ]:
                for el in self.driver.find_elements(By.CSS_SELECTOR, selector)[:20]:
                    try:
                        if el.is_displayed():
                            text = el.text or el.get_attribute("aria-label") or el.get_attribute("placeholder") or ""
                            elements.append({
                                "type": role,
                                "text": text[:50],
                                "tag": el.tag_name,
                                "id": el.get_attribute("id") or None
                            })
                    except:
                        pass
            
            screenshot_path = None
            if include_screenshot:
                screenshot_path = str(self.screenshot_dir / f"browser_{int(time.time())}.png")
                self.driver.save_screenshot(screenshot_path)
            
            return ObservationResult(
                success=True,
                method_used="browser",
                screen_title=self.driver.title,
                url=self.driver.current_url,
                key_elements=elements[:30],
                screenshot_path=screenshot_path
            )
            
        except Exception as e:
            return ObservationResult(
                success=False,
                method_used="browser",
                error=str(e)
            )
    
    def _observe_desktop(self, window_title: Optional[str] = None) -> ObservationResult:
        """
        Get comprehensive desktop state via pywinauto.
        Enumerates all windows and their UI elements.
        """
        if not PYWINAUTO_AVAILABLE:
            return ObservationResult(
                success=False,
                method_used="desktop",
                error="pywinauto not available"
            )
        
        try:
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            
            all_elements = []
            active_title = ""
            active_window = None
            focused_element_info = None
            
            # First pass: identify all windows and find the active one
            window_list = []
            for win in windows:
                try:
                    title = win.window_text()
                    if not title or title.strip() == "":
                        continue
                    
                    is_active = False
                    try:
                        is_active = win.is_active()
                    except:
                        pass
                    
                    is_visible = False
                    try:
                        is_visible = win.is_visible()
                    except:
                        is_visible = True  # Assume visible if we can't check
                    
                    if not is_visible:
                        continue
                    
                    window_info = {
                        "window": win,
                        "title": title,
                        "is_active": is_active,
                        "is_target": window_title and window_title.lower() in title.lower()
                    }
                    window_list.append(window_info)
                    
                    if is_active:
                        active_title = title
                        active_window = win
                except Exception:
                    continue
            
            # Second pass: enumerate UI elements within each window
            for win_info in window_list:
                win = win_info["window"]
                win_title = win_info["title"]
                is_active = win_info["is_active"]
                is_target = win_info["is_target"]
                
                # Add window header
                all_elements.append({
                    "type": "window",
                    "text": win_title,
                    "is_active": is_active,
                    "is_target": is_target,
                    "is_focused": is_active
                })
                
                # Get UI elements within this window
                try:
                    # Limit depth and count to prevent hanging on complex windows
                    ui_elements = self._enumerate_window_controls(win, max_depth=4, max_elements=100)
                    
                    for el in ui_elements:
                        el["parent_window"] = win_title
                        el["in_focused_window"] = is_active
                        all_elements.append(el)
                        
                        # Track focused element
                        if el.get("has_keyboard_focus"):
                            focused_element_info = f"{el.get('control_type', 'unknown')}: {el.get('text', '')[:30]}"
                except Exception as e:
                    all_elements.append({
                        "type": "error",
                        "text": f"Could not enumerate elements in '{win_title}': {str(e)[:50]}",
                        "parent_window": win_title
                    })
            
            # Take screenshot for visual reference
            screenshot_path = None
            try:
                if TESSERACT_AVAILABLE:
                    with mss.mss() as sct:
                        screenshot = sct.grab(sct.monitors[1])
                        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                        screenshot_path = str(self.screenshot_dir / f"desktop_{int(time.time())}.png")
                        img.save(screenshot_path)
            except:
                pass
            
            return ObservationResult(
                success=True,
                method_used="desktop",
                screen_title=active_title,
                key_elements=all_elements,
                focused_element=focused_element_info,
                screenshot_path=screenshot_path
            )
            
        except Exception as e:
            return ObservationResult(
                success=False,
                method_used="desktop",
                error=str(e)
            )
    
    def _enumerate_window_controls(self, window, max_depth: int = 4, max_elements: int = 100) -> List[Dict]:
        """
        Recursively enumerate UI controls within a window.
        Returns a list of element dictionaries.
        """
        elements = []
        
        def _get_control_info(ctrl, depth: int):
            """Extract info from a single control."""
            try:
                info = {}
                
                # Get control type
                try:
                    info["control_type"] = ctrl.element_info.control_type
                except:
                    info["control_type"] = "unknown"
                
                # Get text/name
                try:
                    name = ctrl.element_info.name or ""
                    info["text"] = name[:100] if name else ""
                except:
                    info["text"] = ""
                
                # Get automation ID
                try:
                    auto_id = ctrl.element_info.automation_id
                    if auto_id:
                        info["automation_id"] = auto_id
                except:
                    pass
                
                # Get class name
                try:
                    class_name = ctrl.element_info.class_name
                    if class_name:
                        info["class_name"] = class_name
                except:
                    pass
                
                # Get bounding rectangle
                try:
                    rect = ctrl.element_info.rectangle
                    if rect:
                        info["bounds"] = {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                            "width": rect.width(),
                            "height": rect.height()
                        }
                except:
                    pass
                
                # Check if enabled
                try:
                    info["is_enabled"] = ctrl.is_enabled()
                except:
                    info["is_enabled"] = True
                
                # Check if visible
                try:
                    info["is_visible"] = ctrl.is_visible()
                except:
                    info["is_visible"] = True
                
                # Check keyboard focus
                try:
                    info["has_keyboard_focus"] = ctrl.has_keyboard_focus()
                except:
                    info["has_keyboard_focus"] = False
                
                # Add depth for context
                info["depth"] = depth
                
                return info
            except Exception:
                return None
        
        def _recurse(ctrl, depth: int):
            """Recursively process controls."""
            if depth > max_depth or len(elements) >= max_elements:
                return
            
            # Get info for this control
            info = _get_control_info(ctrl, depth)
            if info and (info.get("text") or info.get("control_type") not in ["", "unknown", "Pane", "Group"]):
                # Skip empty panes/groups but keep ones with text
                if info.get("text") or info.get("control_type") not in ["Pane", "Group", "Custom"]:
                    elements.append(info)
            
            # Recurse into children
            try:
                children = ctrl.children()
                for child in children:
                    if len(elements) >= max_elements:
                        break
                    _recurse(child, depth + 1)
            except:
                pass
        
        # Start recursion from window
        try:
            _recurse(window, 0)
        except Exception:
            pass
        
        return elements
    
    def _observe_ocr(self) -> ObservationResult:
        """Get screen text via OCR."""
        if not TESSERACT_AVAILABLE:
            return ObservationResult(
                success=False,
                method_used="ocr",
                error="Tesseract not available"
            )
        
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                text = pytesseract.image_to_string(img)
                
                return ObservationResult(
                    success=True,
                    method_used="ocr",
                    raw_text=text[:2000]  # Limit length
                )
        except Exception as e:
            return ObservationResult(
                success=False,
                method_used="ocr",
                error=str(e)
            )
    
    def _capture_screenshot(self, region: str = "full") -> ObservationResult:
        """Capture screenshot."""
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                path = str(self.screenshot_dir / f"screen_{int(time.time())}.png")
                img.save(path)
                
                return ObservationResult(
                    success=True,
                    method_used="screenshot",
                    screenshot_path=path
                )
        except Exception as e:
            return ObservationResult(
                success=False,
                method_used="screenshot",
                error=str(e)
            )
    
    # ============================================================
    # ACTION IMPLEMENTATIONS
    # ============================================================
    
    def _click(self, target: Optional[str], x: Optional[float], y: Optional[float]) -> ActionResult:
        """Click on element or coordinates."""
        if not PYAUTOGUI_AVAILABLE:
            return ActionResult(success=False, action_taken="click", failure_reason="pyautogui not available")
        
        try:
            # If coordinates provided, use them
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
                return ActionResult(
                    success=True,
                    action_taken=f"Clicked at ({x}, {y})",
                    coordinates_used=(x, y)
                )
            
            # Try browser click if available
            if self.driver and target:
                try:
                    # Try various selectors
                    element = None
                    for selector in [
                        f"//*[contains(text(), '{target}')]",
                        f"//*[@aria-label='{target}']",
                        f"//*[@placeholder='{target}']",
                        f"//button[contains(., '{target}')]",
                        f"//a[contains(., '{target}')]"
                    ]:
                        try:
                            element = self.driver.find_element(By.XPATH, selector)
                            if element.is_displayed():
                                break
                        except:
                            continue
                    
                    if element:
                        element.click()
                        return ActionResult(
                            success=True,
                            action_taken=f"Clicked element with text '{target}'"
                        )
                except Exception as e:
                    pass
            
            # Target not found
            return ActionResult(
                success=False,
                action_taken=f"Attempted to click '{target}'",
                failure_reason="Element not found",
                element_found=False
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="click",
                failure_reason=str(e)
            )
    
    def _type_text(self, text: str, target: Optional[str], clear_first: bool) -> ActionResult:
        """Type text into element."""
        try:
            # Try browser typing first
            if self.driver and target:
                try:
                    element = self.driver.find_element(By.XPATH, f"//*[contains(@placeholder, '{target}')] | //*[contains(@aria-label, '{target}')]")
                    if clear_first:
                        element.clear()
                    element.send_keys(text)
                    return ActionResult(
                        success=True,
                        action_taken=f"Typed '{text}' into '{target}'"
                    )
                except:
                    pass
            
            # Fallback to pyautogui
            if PYAUTOGUI_AVAILABLE:
                if clear_first:
                    pyautogui.hotkey('ctrl', 'a')
                    pyautogui.press('delete')
                pyautogui.typewrite(text, interval=0.02)
                return ActionResult(
                    success=True,
                    action_taken=f"Typed '{text}' via keyboard"
                )
            
            return ActionResult(
                success=False,
                action_taken="type",
                failure_reason="No typing method available"
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="type",
                failure_reason=str(e)
            )
    
    def _press_key(self, key: str) -> ActionResult:
        """Press a keyboard key."""
        if not PYAUTOGUI_AVAILABLE:
            return ActionResult(success=False, action_taken="press_key", failure_reason="pyautogui not available")
        
        try:
            pyautogui.press(key)
            return ActionResult(
                success=True,
                action_taken=f"Pressed key '{key}'"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="press_key",
                failure_reason=str(e)
            )
    
    def _scroll(self, direction: str, amount: int) -> ActionResult:
        """Scroll the page."""
        if not PYAUTOGUI_AVAILABLE:
            return ActionResult(success=False, action_taken="scroll", failure_reason="pyautogui not available")
        
        try:
            clicks = amount if direction == "down" else -amount
            pyautogui.scroll(clicks * -100)  # Negative because pyautogui scroll is inverted
            return ActionResult(
                success=True,
                action_taken=f"Scrolled {direction} by {amount}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="scroll",
                failure_reason=str(e)
            )
    
    def _navigate(self, url: str) -> ActionResult:
        """Navigate browser to URL."""
        if not self.driver:
            if not SELENIUM_AVAILABLE:
                return ActionResult(
                    success=False,
                    action_taken="navigate",
                    failure_reason="Selenium not available"
                )
            try:
                options = Options()
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                self.driver.set_window_size(1280, 900)
            except Exception as e:
                return ActionResult(
                    success=False,
                    action_taken="navigate",
                    failure_reason=str(e)
                )
        
        try:
            self.driver.get(url)
            return ActionResult(
                success=True,
                action_taken=f"Navigated to {url}"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="navigate",
                failure_reason=str(e)
            )

    
    def _focus_window(self, window_title: str) -> ActionResult:
        """Focus a window by title."""
        if not PYWINAUTO_AVAILABLE:
            return ActionResult(success=False, action_taken="focus_window", failure_reason="pywinauto not available")
        
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(title_re=f".*{window_title}.*")
            app.top_window().set_focus()
            return ActionResult(
                success=True,
                action_taken=f"Focused window '{window_title}'"
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_taken="focus_window",
                failure_reason=str(e)
            )
    
    def _build_response_from_report(self, report: Dict, request: ExecutorRequest) -> ExecutorResponse:
        """Build ExecutorResponse from report_result call."""
        if report.get("impossible"):
            return ExecutorResponse(
                request_type=request.request_type,
                impossible=True,
                impossible_reason=report.get("impossible_reason", "Unknown reason")
            )
        
        if request.request_type == RequestType.OBSERVE:
            return ExecutorResponse(
                request_type=RequestType.OBSERVE,
                observation=ObservationResult(
                    success=report.get("success", False),
                    method_used="report",
                    screen_title=report.get("summary", ""),
                    key_elements=report.get("details", {}).get("elements", [])
                )
            )
        else:
            return ExecutorResponse(
                request_type=RequestType.ACTION,
                action=ActionResult(
                    success=report.get("success", False),
                    action_taken=report.get("summary", ""),
                    failure_reason=report.get("details", {}).get("failure_reason")
                )
            )
