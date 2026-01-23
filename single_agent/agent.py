"""
Single Agent - Unified Desktop & Browser Automation Agent
Uses Gemini 3 Flash with a comprehensive tool set.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
import base64
import pyperclip
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

from openai import OpenAI

# ============================================================
# TOOL AVAILABILITY CHECKS
# ============================================================

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    from pywinauto import Desktop, Application
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
# TOOL DEFINITIONS
# ============================================================

AGENT_TOOLS = [
    # --- OBSERVATION TOOLS ---
    {"type": "function", "function": {"name": "describe_screen", "description": "Use AI vision to describe the current screen state. Best for understanding UI layout.", "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "Optional specific question about the screen"}}}}},
    {"type": "function", "function": {"name": "ocr_screen", "description": "Read all text on screen using OCR. Best for extracting text content.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "observe_browser", "description": "Get browser page state including title, URL, and key elements.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "observe_desktop", "description": "List all open windows and their states using Pywinauto.", "parameters": {"type": "object", "properties": {}}}},
    
    # --- BROWSER TOOLS ---
    {"type": "function", "function": {"name": "open_browser", "description": "Open Chrome browser and navigate to a URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to navigate to"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "browser_click", "description": "Click an element in the browser by text content or CSS selector.", "parameters": {"type": "object", "properties": {"target": {"type": "string", "description": "Text content or CSS selector of element to click"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "browser_type", "description": "Type text into the focused browser element.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "clear_first": {"type": "boolean", "default": False}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "browser_press_key", "description": "Press a key in the browser (enter, tab, escape, etc).", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "browser_scroll", "description": "Scroll the browser page.", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer", "default": 300}}}}},
    {"type": "function", "function": {"name": "switch_tab", "description": "Switch to a browser tab by index (0-based).", "parameters": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}}},
    {"type": "function", "function": {"name": "close_tab", "description": "Close the current browser tab.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "go_back", "description": "Navigate back in browser history.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "go_forward", "description": "Navigate forward in browser history.", "parameters": {"type": "object", "properties": {}}}},
    
    # --- DESKTOP TOOLS ---
    {"type": "function", "function": {"name": "open_app", "description": "Open a Windows application by name.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string", "description": "Name of app to open (e.g., 'notepad', 'spotify', 'chrome')"}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "focus_window", "description": "Bring a window to foreground by title.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "minimize_window", "description": "Minimize a window by title.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "maximize_window", "description": "Maximize a window by title.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "close_window", "description": "Close a window by title.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}},
    
    # --- INPUT TOOLS (Desktop) ---
    {"type": "function", "function": {"name": "click", "description": "Click at screen coordinates or on text found via OCR.", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "text": {"type": "string", "description": "Text to find and click on (alternative to x,y)"}}}}},
    {"type": "function", "function": {"name": "right_click", "description": "Right-click at screen coordinates.", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "double_click", "description": "Double-click at screen coordinates.", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "type_text", "description": "Type text using keyboard.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "press_key", "description": "Press a single key (enter, tab, escape, f1, etc).", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "hotkey", "description": "Press a key combination (e.g., ctrl+c, alt+tab, ctrl+shift+n).", "parameters": {"type": "object", "properties": {"keys": {"type": "string", "description": "Keys separated by + (e.g., 'ctrl+c', 'alt+f4')"}}, "required": ["keys"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Scroll at current mouse position.", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer", "default": 3}}}}},
    {"type": "function", "function": {"name": "drag_and_drop", "description": "Drag from one position to another.", "parameters": {"type": "object", "properties": {"start_x": {"type": "integer"}, "start_y": {"type": "integer"}, "end_x": {"type": "integer"}, "end_y": {"type": "integer"}}, "required": ["start_x", "start_y", "end_x", "end_y"]}}},
    
    # --- CLIPBOARD TOOLS ---
    {"type": "function", "function": {"name": "get_clipboard", "description": "Get current clipboard content.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "set_clipboard", "description": "Set clipboard content.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    
    # --- UTILITY TOOLS ---
    {"type": "function", "function": {"name": "wait", "description": "Wait for specified seconds.", "parameters": {"type": "object", "properties": {"seconds": {"type": "number", "default": 1}}}}}
]


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """You are an AI assistant with the ability to control the user's computer. You can browse the web, use desktop applications, and automate tasks.

Note: The user is also using this computer. They might switch windows or change things while you work. If something seems off, use describe_screen to check what's currently on screen.

YOUR TOOLS:

VISION:
- describe_screen: Takes a screenshot and uses AI vision to describe what's visible
- ocr_screen: Extracts all readable text from the screen using OCR

BROWSER (Selenium-controlled Chrome):
- open_browser: Opens Chrome and navigates to a URL
- observe_browser: Returns the page title, URL, and list of clickable elements
- browser_click: Clicks an element by its text or CSS selector
- browser_type: Types text into the currently focused input field
- browser_press_key: Presses a key (enter, tab, escape, etc)
- browser_scroll: Scrolls the page up or down
- switch_tab: Switches to a different browser tab by index
- close_tab: Closes the current tab
- go_back: Goes back in browser history
- go_forward: Goes forward in browser history

DESKTOP:
- open_app: Opens an application using Win+R run dialog
- observe_desktop: Lists all open windows and which one is active
- focus_window: Brings a window to the front by its title
- minimize_window: Minimizes a window by its title
- maximize_window: Maximizes a window by its title
- close_window: Closes a window by its title

INPUT:
- click: Clicks at x,y coordinates on screen
- right_click: Right-clicks at x,y coordinates
- double_click: Double-clicks at x,y coordinates
- type_text: Types text using the keyboard
- press_key: Presses a single key (enter, tab, f1, etc)
- hotkey: Presses a key combination (ctrl+c, alt+tab, etc)
- scroll: Scrolls up or down at the current mouse position
- drag_and_drop: Drags from one position to another

CLIPBOARD:
- get_clipboard: Returns the current clipboard content
- set_clipboard: Copies text to the clipboard

UTILITY:
- wait: Pauses for a specified number of seconds

OBSERVATION HINTS:
- When working in the browser, use observe_browser to see page elements
- When working on the desktop, use observe_desktop to see open windows
- Use describe_screen as a visual verification method (to confirm what happened)
- If you can't find or click something, use ocr_screen to see all text on screen
- IMPORTANT: describe_screen and ocr_screen capture whatever is currently visible. Make sure the correct window is focused first, or you'll see the wrong content.

Be helpful and conversational. Confirm what you did after completing actions."""


# ============================================================
# SINGLE AGENT CLASS
# ============================================================

class SingleAgent:
    def __init__(self, model: str = "gemini-3-flash-preview", screenshot_dir: str = "single_agent/screenshots", logger: Optional[Callable[[str], None]] = None):
        self.model = model
        self.logger = logger
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.driver = None
        self.messages = []
        
        # Pause/Resume state
        self.is_paused = False
        self.current_task = None
        self._turns_used = 0
        
        # Setup client
        self.client = OpenAI(
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )

    def _log(self, message: str):
        """Log message to console or custom logger."""
        if self.logger:
            self.logger(message)
        else:
            print(message)
    
    def pause(self):
        """Request the agent to pause after the current turn."""
        self.is_paused = True
        self._log("[PAUSE REQUESTED]")
    
    def run(self, task: str, max_turns: int = 20) -> str:
        """Execute a task with the agent."""
        self._log(f"\n[TASK] {task}")
        
        # Fresh start
        self.is_paused = False
        self.current_task = task
        self._turns_used = 0
        
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task}"}
        ]
        
        return self._run_loop(max_turns)
    
    def continue_task(self, max_turns: int = 20) -> str:
        """Continue a paused task."""
        if not self.current_task:
            return "No task to continue."
        
        self._log(f"\n[RESUMING] {self.current_task}")
        self.is_paused = False
        
        # Add resume message to context
        self.messages.append({
            "role": "user", 
            "content": "Continue the task from where you left off."
        })
        
        return self._run_loop(max_turns)
    
    def _run_loop(self, max_turns: int) -> str:
        """Internal loop that runs until complete, paused, or max turns."""
        for turn in range(max_turns):
            # Check for pause request
            if self.is_paused:
                self._log(f"[PAUSED] at turn {self._turns_used + turn + 1}")
                return f"Task paused after {self._turns_used + turn} turns. Use /continue to resume."
            
            self._log(f"\n--- Turn {self._turns_used + turn + 1} ---")
            
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=AGENT_TOOLS,
                    max_tokens=2000
                )
                
                message = response.choices[0].message
                
                # Check if task is complete (no tool calls)
                if not message.tool_calls:
                    self._log(f"[COMPLETE] {message.content}")
                    self.current_task = None  # Clear task on completion
                    return message.content or "Task completed."
                
                # Execute tool calls
                self.messages.append(message)
                tool_results = []
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    
                    self._log(f"  [TOOL] {func_name}({args})")
                    result = self._execute_tool(func_name, args)
                    self._log(f"  [RESULT] {str(result)[:200]}...")
                    
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result) if isinstance(result, dict) else str(result)
                    })
                
                self.messages.extend(tool_results)
                
            except Exception as e:
                self._log(f"[ERROR] {e}")
                self.messages.append({"role": "user", "content": f"Error occurred: {e}. Please try a different approach."})
        
        self._turns_used += max_turns
        last_msg = self.messages[-1]
        content = last_msg.get("content", "") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")
        return f"{content or 'Task stopped'} (Max turns reached)"
    
    def _execute_tool(self, name: str, args: Dict) -> Any:
        """Route and execute tool calls."""
        try:
            # Observation Tools
            if name == "describe_screen": return self._describe_screen(args.get("question"))
            if name == "ocr_screen": return self._ocr_screen()
            if name == "observe_browser": return self._observe_browser()
            if name == "observe_desktop": return self._observe_desktop()
            
            # Browser Tools
            if name == "open_browser": return self._open_browser(args["url"])
            if name == "browser_click": return self._browser_click(args["target"])
            if name == "browser_type": return self._browser_type(args["text"], args.get("clear_first", False))
            if name == "browser_press_key": return self._browser_press_key(args["key"])
            if name == "browser_scroll": return self._browser_scroll(args.get("direction", "down"), args.get("amount", 300))
            if name == "switch_tab": return self._switch_tab(args["index"])
            if name == "close_tab": return self._close_tab()
            if name == "go_back": return self._go_back()
            if name == "go_forward": return self._go_forward()
            
            # Desktop Tools
            if name == "open_app": return self._open_app(args["app_name"])
            if name == "focus_window": return self._focus_window(args["title"])
            if name == "minimize_window": return self._minimize_window(args["title"])
            if name == "maximize_window": return self._maximize_window(args["title"])
            if name == "close_window": return self._close_window(args["title"])
            
            # Input Tools
            if name == "click": return self._click(args.get("x"), args.get("y"), args.get("text"))
            if name == "right_click": return self._right_click(args["x"], args["y"])
            if name == "double_click": return self._double_click(args["x"], args["y"])
            if name == "type_text": return self._type_text(args["text"])
            if name == "press_key": return self._press_key(args["key"])
            if name == "hotkey": return self._hotkey(args["keys"])
            if name == "scroll": return self._scroll(args.get("direction", "down"), args.get("amount", 3))
            if name == "drag_and_drop": return self._drag_and_drop(args["start_x"], args["start_y"], args["end_x"], args["end_y"])
            
            # Clipboard Tools
            if name == "get_clipboard": return self._get_clipboard()
            if name == "set_clipboard": return self._set_clipboard(args["text"])
            
            # Utility Tools
            if name == "wait": return self._wait(args.get("seconds", 1))
            
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # OBSERVATION TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _describe_screen(self, question: Optional[str] = None) -> Dict:
        """Use AI vision to describe the screen."""
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                path = str(self.screenshot_dir / f"screen_{int(time.time())}.png")
                img.save(path)
                
                with open(path, "rb") as f:
                    base64_image = base64.b64encode(f.read()).decode('utf-8')
                
                prompt = question or "Describe this screen in detail. What applications are open? What elements are visible?"
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]}],
                    max_tokens=500
                )
                
                return {"description": response.choices[0].message.content}
        except Exception as e:
            return {"error": str(e)}
    
    def _ocr_screen(self) -> Dict:
        """OCR the entire screen."""
        if not TESSERACT_AVAILABLE:
            return {"error": "Tesseract not available"}
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                text = pytesseract.image_to_string(img)
                return {"text": text[:3000]}
        except Exception as e:
            return {"error": str(e)}
    
    def _observe_browser(self) -> Dict:
        """Get browser state with extended element visibility."""
        if not self.driver:
            return {"error": "No browser open. Use open_browser first."}
        try:
            elements = []
            
            # 1. Define selectors to scan
            selectors = [
                ("a", "link"), 
                ("button", "button"), 
                ("input", "input"), 
                ("[role='button']", "button"),
                ("h1, h2, h3", "header"),  # Capture main headings
                ("[role='link']", "link")
            ]
            
            for sel, role in selectors:
                # Increased limit per type to 30 to catch lists
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel)[:30]:
                    if el.is_displayed():
                        # Get text from multiple sources
                        text = (
                            el.text or 
                            el.get_attribute("placeholder") or 
                            el.get_attribute("aria-label") or 
                            el.get_attribute("title") or 
                            el.get_attribute("value")
                        )
                        
                        # Only add if it has meaningful text or is an input
                        if text or role == "input":
                            elements.append({
                                "type": role, 
                                "text": (text[:60] + "...") if text and len(text) > 60 else text
                            })
            
            # Return up to 100 elements (increased from 20)
            return {
                "title": self.driver.title, 
                "url": self.driver.current_url, 
                "elements": elements[:100]  
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _observe_desktop(self) -> Dict:
        """List all windows."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Pywinauto not available"}
        try:
            desktop = Desktop(backend="uia")
            windows = []
            for win in desktop.windows():
                try:
                    title = win.window_text()
                    if title:
                        windows.append({"title": title, "is_active": win.is_active()})
                except:
                    continue
            return {"windows": windows[:20]}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # BROWSER TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _open_browser(self, url: str) -> Dict:
        """Open browser and navigate. Restarts driver if crashed."""
        if not SELENIUM_AVAILABLE:
            return {"error": "Selenium not available"}
        
        def _init_driver():
            options = Options()
            options.add_argument("--no-sandbox")
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")  # Suppress most Chrome logs
            options.add_argument("--disable-logging")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)

        try:
            if not self.driver:
                self.driver = _init_driver()
            
            try:
                self.driver.get(url)
            except Exception as e:
                # If session is invalid/died, restart it
                if "invalid session id" in str(e).lower() or "no such window" in str(e).lower():
                    self._log("  [Browser session died, restarting...]")
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = _init_driver()
                    self.driver.get(url)
                else:
                    raise e
                    
            time.sleep(1)
            return {"success": True, "url": self.driver.current_url, "title": self.driver.title}
        except Exception as e:
            return {"error": str(e)}
    
    def _browser_click(self, target: str) -> Dict:
        """Click element in browser by text, selector, or attribute."""
        if not self.driver:
            return {"error": "No browser open"}
        try:
            # 1. Try Comprehensive XPath (Text + Attributes)
            # This searches text, placeholder, aria-label, alt, value, title, name, and id
            xpath = (
                f"//*["
                f"contains(text(), '{target}') or "
                f"contains(@placeholder, '{target}') or "
                f"contains(@aria-label, '{target}') or "
                f"contains(@alt, '{target}') or "
                f"contains(@value, '{target}') or "
                f"contains(@title, '{target}') or "
                f"contains(@name, '{target}') or "
                f"contains(@id, '{target}')"
                f"]"
            )
            
            try:
                # Find all matches but prioritize visible ones
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed():
                        el.click()
                        return {"success": True, "clicked": target, "method": "xpath_match"}
            except:
                pass

            # 2. Try as exact CSS selector (fallback)
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, target)
                if el.is_displayed():
                    el.click()
                    return {"success": True, "clicked": target, "method": "css_selector"}
            except:
                pass

            return {"error": f"Element not found: '{target}'. Tried text, attributes, and CSS selector."}
        except Exception as e:
            return {"error": str(e)}
    
    def _browser_type(self, text: str, clear_first: bool = False) -> Dict:
        """Type in focused browser element."""
        if not self.driver:
            return {"error": "No browser open"}
        try:
            active = self.driver.switch_to.active_element
            if clear_first:
                active.clear()
            active.send_keys(text)
            return {"success": True, "typed": text}
        except Exception as e:
            return {"error": str(e)}
    
    def _browser_press_key(self, key: str) -> Dict:
        """Press key in browser."""
        if not self.driver:
            return {"error": "No browser open"}
        try:
            key_map = {"enter": Keys.ENTER, "tab": Keys.TAB, "escape": Keys.ESCAPE, "backspace": Keys.BACKSPACE}
            active = self.driver.switch_to.active_element
            active.send_keys(key_map.get(key.lower(), key))
            return {"success": True, "pressed": key}
        except Exception as e:
            return {"error": str(e)}
    
    def _browser_scroll(self, direction: str, amount: int) -> Dict:
        """Scroll browser page."""
        if not self.driver:
            return {"error": "No browser open"}
        try:
            scroll = -amount if direction == "up" else amount
            self.driver.execute_script(f"window.scrollBy(0, {scroll})")
            return {"success": True, "scrolled": direction}
        except Exception as e:
            return {"error": str(e)}
    
    def _switch_tab(self, index: int) -> Dict:
        """Switch browser tab."""
        if not self.driver:
            return {"error": "No browser open"}
        try:
            self.driver.switch_to.window(self.driver.window_handles[index])
            return {"success": True, "tab": index, "title": self.driver.title}
        except Exception as e:
            return {"error": str(e)}
    
    def _close_tab(self) -> Dict:
        """Close current tab."""
        if not self.driver:
            return {"error": "No browser open"}
        try:
            self.driver.close()
            if self.driver.window_handles:
                self.driver.switch_to.window(self.driver.window_handles[0])
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    def _go_back(self) -> Dict:
        """Browser back."""
        if not self.driver:
            return {"error": "No browser open"}
        self.driver.back()
        return {"success": True}
    
    def _go_forward(self) -> Dict:
        """Browser forward."""
        if not self.driver:
            return {"error": "No browser open"}
        self.driver.forward()
        return {"success": True}
    
    # ============================================================
    # DESKTOP TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _open_app(self, app_name: str) -> Dict:
        """Open application."""
        try:
            pyautogui.hotkey('win', 'r')
            time.sleep(0.3)
            pyautogui.write(app_name)
            pyautogui.press('enter')
            time.sleep(1)
            return {"success": True, "opened": app_name}
        except Exception as e:
            return {"error": str(e)}
    
    def _focus_window(self, title: str) -> Dict:
        """Focus window by title."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Pywinauto not available"}
        try:
            # Find all matching windows and pick the first one
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if not matches:
                return {"error": f"No window found matching '{title}'"}
            matches[0].set_focus()
            return {"success": True, "focused": matches[0].window_text(), "total_matches": len(matches)}
        except Exception as e:
            return {"error": str(e)}
    
    def _minimize_window(self, title: str) -> Dict:
        """Minimize window."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Pywinauto not available"}
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if not matches:
                return {"error": f"No window found matching '{title}'"}
            matches[0].minimize()
            return {"success": True, "minimized": matches[0].window_text()}
        except Exception as e:
            return {"error": str(e)}
    
    def _maximize_window(self, title: str) -> Dict:
        """Maximize window."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Pywinauto not available"}
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if not matches:
                return {"error": f"No window found matching '{title}'"}
            matches[0].maximize()
            return {"success": True, "maximized": matches[0].window_text()}
        except Exception as e:
            return {"error": str(e)}
    
    def _close_window(self, title: str) -> Dict:
        """Close window."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "Pywinauto not available"}
        try:
            desktop = Desktop(backend="uia")
            matches = [w for w in desktop.windows() if title.lower() in w.window_text().lower()]
            if not matches:
                return {"error": f"No window found matching '{title}'"}
            matches[0].close()
            return {"success": True, "closed": matches[0].window_text()}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # INPUT TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _click(self, x: Optional[int], y: Optional[int], text: Optional[str]) -> Dict:
        """Click at coordinates or on text."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y)
                return {"success": True, "clicked": f"({x}, {y})"}
            elif text:
                # Use OCR to find text position
                location = pyautogui.locateOnScreen(text)
                if location:
                    pyautogui.click(location)
                    return {"success": True, "clicked": text}
                return {"error": f"Text not found: {text}"}
            return {"error": "Provide either x,y coordinates or text to find"}
        except Exception as e:
            return {"error": str(e)}
    
    def _right_click(self, x: int, y: int) -> Dict:
        """Right-click at coordinates."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.rightClick(x, y)
        return {"success": True, "right_clicked": f"({x}, {y})"}
    
    def _double_click(self, x: int, y: int) -> Dict:
        """Double-click at coordinates."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.doubleClick(x, y)
        return {"success": True, "double_clicked": f"({x}, {y})"}
    
    def _type_text(self, text: str) -> Dict:
        """Type text."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.write(text, interval=0.02)
        return {"success": True, "typed": text}
    
    def _press_key(self, key: str) -> Dict:
        """Press single key."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.press(key)
        return {"success": True, "pressed": key}
    
    def _hotkey(self, keys: str) -> Dict:
        """Press key combination."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        key_list = [k.strip() for k in keys.split('+')]
        pyautogui.hotkey(*key_list)
        return {"success": True, "hotkey": keys}
    
    def _scroll(self, direction: str, amount: int) -> Dict:
        """Scroll at mouse position."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        clicks = -amount if direction == "up" else amount
        pyautogui.scroll(clicks)
        return {"success": True, "scrolled": direction}
    
    def _drag_and_drop(self, start_x: int, start_y: int, end_x: int, end_y: int) -> Dict:
        """Drag from start to end."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.moveTo(start_x, start_y)
        pyautogui.drag(end_x - start_x, end_y - start_y, duration=0.5)
        return {"success": True, "dragged": f"({start_x},{start_y}) to ({end_x},{end_y})"}
    
    # ============================================================
    # CLIPBOARD TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _get_clipboard(self) -> Dict:
        """Get clipboard content."""
        try:
            return {"content": pyperclip.paste()}
        except Exception as e:
            return {"error": str(e)}
    
    def _set_clipboard(self, text: str) -> Dict:
        """Set clipboard content."""
        try:
            pyperclip.copy(text)
            return {"success": True, "copied": text[:50]}
        except Exception as e:
            return {"error": str(e)}
    
    # ============================================================
    # UTILITY TOOL IMPLEMENTATIONS
    # ============================================================
    
    def _wait(self, seconds: float) -> Dict:
        """Wait for specified seconds."""
        time.sleep(seconds)
        return {"waited": seconds}
