"""
Unified Real Agent
Complete LLM agent with all observation methods, verification, and proper execution.
"""

from dotenv import load_dotenv
load_dotenv()

import json
import time
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from openai import OpenAI

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# pywinauto
try:
    from pywinauto import Desktop, Application
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

# Tesseract
try:
    import pytesseract
    from PIL import Image
    import mss
    import mss.tools
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


# ============================================================
# TOOLS DEFINITION
# ============================================================

AGENT_TOOLS = [
    # Observation
    {
        "type": "function",
        "function": {
            "name": "observe",
            "description": "Get current screen state with all visible elements",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["auto", "browser", "desktop", "ocr"],
                        "description": "Observation method. 'auto' selects best available."
                    }
                }
            }
        }
    },
    # Actions
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click on an element by ID, name, or visible text",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string", "description": "Element ID or name attribute"},
                    "text": {"type": "string", "description": "Visible text of element"},
                    "index": {"type": "integer", "description": "If multiple matches, which one (0-indexed)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into an element or the focused element",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "element_id": {"type": "string", "description": "Target element ID (optional)"},
                    "clear_first": {"type": "boolean", "description": "Clear existing text first"}
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
                    "key": {"type": "string", "enum": ["enter", "tab", "escape", "backspace", "delete", "up", "down", "left", "right"]}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
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
    # Verification
    {
        "type": "function",
        "function": {
            "name": "verify_url",
            "description": "Check if current URL contains expected text",
            "parameters": {
                "type": "object",
                "properties": {
                    "contains": {"type": "string", "description": "Text that URL should contain"}
                },
                "required": ["contains"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_element",
            "description": "Check if an element exists and is visible",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string"},
                    "text": {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_text",
            "description": "Check if text appears anywhere on the page",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to look for"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Capture screenshot of current state",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for screenshot file"}
                }
            }
        }
    },
    # Completion
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Signal task is finished. Call this when you have completed the objective OR if you cannot proceed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "description": "True if task was completed successfully"},
                    "summary": {"type": "string", "description": "What was accomplished or why it failed"}
                },
                "required": ["success", "summary"]
            }
        }
    }
]


# ============================================================
# EXECUTION LOG
# ============================================================

@dataclass
class ActionLog:
    step: int
    action: str
    args: Dict
    result: Dict
    timestamp: float = field(default_factory=time.time)
    screenshot_path: Optional[str] = None


@dataclass
class TestResult:
    name: str
    task: str
    success: bool
    steps: int
    duration_seconds: float
    actions: List[ActionLog]
    verification_results: List[Dict]
    final_url: Optional[str] = None
    error: Optional[str] = None


# ============================================================
# UNIFIED AGENT
# ============================================================

class UnifiedAgent:
    """Complete agent with all observation and execution capabilities."""
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        headless: bool = False,
        screenshot_dir: str = "test_outputs/screenshots"
    ):
        self.model = model
        self.client = OpenAI()
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # State
        self.driver = None
        self.mode = "browser"  # browser, desktop, hybrid
        self.action_log: List[ActionLog] = []
        self.verification_results: List[Dict] = []
        self.step_count = 0
    
    # ==================== BROWSER CONTROL ====================
    
    def start_browser(self):
        """Start Chrome browser."""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument('--window-size=1280,900')
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.mode = "browser"
        print("[Agent] Browser started")
    
    def stop_browser(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            print("[Agent] Browser closed")
    
    # ==================== OBSERVATION ====================
    
    def observe_browser(self) -> Dict:
        """Get browser page state."""
        if not self.driver:
            return {"error": "Browser not running"}
        
        elements = []
        for tag in ['input', 'button', 'a', 'textarea', 'select', 'label']:
            for el in self.driver.find_elements(By.TAG_NAME, tag):
                try:
                    if not el.is_displayed():
                        continue
                    
                    el_id = el.get_attribute("id") or el.get_attribute("name") or ""
                    text = (el.text or el.get_attribute("placeholder") or 
                            el.get_attribute("aria-label") or el.get_attribute("value") or "")
                    el_type = el.get_attribute("type") or tag
                    
                    elements.append({
                        "id": el_id if el_id else f"_{tag}_{len(elements)}",
                        "tag": tag,
                        "type": el_type,
                        "text": text[:60] if text else ""
                    })
                except:
                    continue
        
        return {
            "method": "browser",
            "url": self.driver.current_url,
            "title": self.driver.title,
            "element_count": len(elements),
            "elements": elements[:25]
        }
    
    def observe_desktop(self) -> Dict:
        """Get desktop window state via pywinauto."""
        if not PYWINAUTO_AVAILABLE:
            return {"error": "pywinauto not available"}
        
        try:
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            
            if not windows:
                return {"error": "No windows found"}
            
            active = windows[0]
            elements = []
            
            for child in active.descendants()[:50]:
                try:
                    name = child.element_info.name or ""
                    ctrl_type = child.element_info.control_type
                    auto_id = child.element_info.automation_id or ""
                    
                    if not name and ctrl_type not in ["Edit", "Button", "CheckBox", "MenuItem"]:
                        continue
                    
                    elements.append({
                        "id": auto_id if auto_id else f"ctrl_{len(elements)}",
                        "type": ctrl_type,
                        "text": name[:60]
                    })
                except:
                    continue
            
            return {
                "method": "desktop",
                "window": active.element_info.name,
                "element_count": len(elements),
                "elements": elements[:25]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def observe_ocr(self) -> Dict:
        """Get screen state via Tesseract OCR."""
        if not TESSERACT_AVAILABLE:
            return {"error": "Tesseract not available"}
        
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img_path = str(self.screenshot_dir / "temp_ocr.png")
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=img_path)
            
            image = Image.open(img_path)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            elements = []
            for i, text in enumerate(data['text']):
                text = text.strip()
                conf = float(data['conf'][i])
                if text and conf > 60 and len(text) > 1:
                    elements.append({
                        "id": f"text_{len(elements)}",
                        "type": "text",
                        "text": text[:40],
                        "x": data['left'][i],
                        "y": data['top'][i]
                    })
            
            os.remove(img_path)
            
            return {
                "method": "ocr",
                "element_count": len(elements),
                "elements": elements[:30]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def observe(self, method: str = "auto") -> Dict:
        """Get observation using specified or best method."""
        if method == "auto":
            if self.driver:
                return self.observe_browser()
            elif PYWINAUTO_AVAILABLE:
                return self.observe_desktop()
            else:
                return self.observe_ocr()
        elif method == "browser":
            return self.observe_browser()
        elif method == "desktop":
            return self.observe_desktop()
        elif method == "ocr":
            return self.observe_ocr()
        else:
            return {"error": f"Unknown method: {method}"}
    
    # ==================== ACTIONS ====================
    
    def find_element(self, element_id: str = None, text: str = None, index: int = 0):
        """Find element by ID, name, or text."""
        if not self.driver:
            return None
        
        # Try by ID
        if element_id:
            try:
                return self.driver.find_element(By.ID, element_id)
            except:
                pass
            try:
                return self.driver.find_element(By.NAME, element_id)
            except:
                pass
            try:
                return self.driver.find_element(By.CSS_SELECTOR, f"[data-testid='{element_id}']")
            except:
                pass
        
        # Try by text
        if text:
            try:
                elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{text}')]")
                if elements and len(elements) > index:
                    return elements[index]
            except:
                pass
            try:
                elements = self.driver.find_elements(By.XPATH, f"//button[contains(., '{text}')]")
                if elements and len(elements) > index:
                    return elements[index]
            except:
                pass
            try:
                return self.driver.find_element(By.LINK_TEXT, text)
            except:
                pass
            try:
                return self.driver.find_element(By.PARTIAL_LINK_TEXT, text)
            except:
                pass
        
        return None
    
    def execute_click(self, args: Dict) -> Dict:
        element = self.find_element(args.get("element_id"), args.get("text"), args.get("index", 0))
        if element:
            element.click()
            return {"success": True, "clicked": args.get("element_id") or args.get("text")}
        return {"success": False, "error": "Element not found"}
    
    def execute_type(self, args: Dict) -> Dict:
        element = None
        if args.get("element_id"):
            element = self.find_element(args["element_id"])
        if not element:
            element = self.driver.switch_to.active_element
        
        if args.get("clear_first"):
            element.clear()
        
        element.send_keys(args["text"])
        return {"success": True, "typed": args["text"]}
    
    def execute_key(self, args: Dict) -> Dict:
        key_map = {
            "enter": Keys.ENTER, "tab": Keys.TAB, "escape": Keys.ESCAPE,
            "backspace": Keys.BACKSPACE, "delete": Keys.DELETE,
            "up": Keys.UP, "down": Keys.DOWN, "left": Keys.LEFT, "right": Keys.RIGHT
        }
        key = key_map.get(args["key"].lower())
        if key:
            self.driver.switch_to.active_element.send_keys(key)
            return {"success": True, "pressed": args["key"]}
        return {"success": False, "error": f"Unknown key: {args['key']}"}
    
    def execute_navigate(self, args: Dict) -> Dict:
        self.driver.get(args["url"])
        time.sleep(1.5)
        return {"success": True, "navigated": args["url"]}
    
    # ==================== VERIFICATION ====================
    
    def verify_url(self, args: Dict) -> Dict:
        current = self.driver.current_url
        contains = args["contains"]
        passed = contains.lower() in current.lower()
        result = {"success": passed, "current_url": current, "expected": contains}
        self.verification_results.append({"type": "url", **result})
        return result
    
    def verify_element(self, args: Dict) -> Dict:
        element = self.find_element(args.get("element_id"), args.get("text"))
        passed = element is not None and element.is_displayed()
        result = {"success": passed, "found": passed}
        self.verification_results.append({"type": "element", **result})
        return result
    
    def verify_text(self, args: Dict) -> Dict:
        page_text = self.driver.find_element(By.TAG_NAME, "body").text
        passed = args["text"].lower() in page_text.lower()
        result = {"success": passed, "text_found": passed, "searched": args["text"]}
        self.verification_results.append({"type": "text", **result})
        return result
    
    def take_screenshot(self, name: str = None) -> str:
        if not name:
            name = f"step_{self.step_count}"
        path = str(self.screenshot_dir / f"{name}_{int(time.time())}.png")
        if self.driver:
            self.driver.save_screenshot(path)
        else:
            with mss.mss() as sct:
                sct.shot(output=path)
        return path
    
    # ==================== EXECUTION ====================
    
    def execute_action(self, tool_name: str, args: Dict) -> Dict:
        """Execute a single action."""
        self.step_count += 1
        result = {"success": False}
        
        try:
            if tool_name == "observe":
                result = self.observe(args.get("method", "auto"))
                result["success"] = "error" not in result
            
            elif tool_name == "click":
                result = self.execute_click(args)
            
            elif tool_name == "type_text":
                result = self.execute_type(args)
            
            elif tool_name == "press_key":
                result = self.execute_key(args)
            
            elif tool_name == "navigate":
                result = self.execute_navigate(args)
            
            elif tool_name == "verify_url":
                result = self.verify_url(args)
            
            elif tool_name == "verify_element":
                result = self.verify_element(args)
            
            elif tool_name == "verify_text":
                result = self.verify_text(args)
            
            elif tool_name == "screenshot":
                path = self.take_screenshot(args.get("name"))
                result = {"success": True, "path": path}
            
            elif tool_name == "task_complete":
                result = {"success": True, "task_complete": True, "task_success": args.get("success"), "summary": args.get("summary")}
            
            else:
                result = {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        except Exception as e:
            result = {"success": False, "error": str(e)}
        
        # Log action
        log = ActionLog(
            step=self.step_count,
            action=tool_name,
            args=args,
            result=result
        )
        self.action_log.append(log)
        
        return result
    
    # ==================== RUN TASK ====================
    
    def run_task(
        self,
        task: str,
        start_url: str = None,
        mode: Literal["browser", "desktop"] = "browser",
        max_steps: int = 15
    ) -> TestResult:
        """Execute a complete task."""
        print(f"\n{'='*60}")
        print(f"TASK: {task}")
        print(f"MODE: {mode}")
        print(f"{'='*60}")
        
        self.action_log = []
        self.verification_results = []
        self.step_count = 0
        start_time = time.time()
        
        # Start browser if needed
        if mode == "browser":
            self.start_browser()
            if start_url:
                self.driver.get(start_url)
                time.sleep(2)
        
        system_prompt = f"""You are an AI agent controlling a computer.
Complete the task using the available tools.

IMPORTANT RULES:
1. First observe the screen to understand the current state
2. Take actions one at a time, verify results
3. Use verify_url or verify_text to confirm progress
4. When the objective is achieved, call task_complete with success=true
5. If you cannot proceed, call task_complete with success=false and explain why
6. Be precise with element IDs. If ID fails, try text.

Task: {task}"""

        messages = [{"role": "system", "content": system_prompt}]
        
        # Initial observation
        initial_obs = self.observe()
        messages.append({
            "role": "user",
            "content": f"Task: {task}\n\nInitial screen state:\n{json.dumps(initial_obs, indent=2)}"
        })
        
        task_complete = False
        task_success = False
        task_summary = ""
        error = None
        
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")
            
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=AGENT_TOOLS,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                
                if msg.content:
                    print(f"[Think] {msg.content[:80]}...")
                
                if not msg.tool_calls:
                    print("[No action]")
                    break
                
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    print(f"[{tc.function.name}] {json.dumps(args)}")
                    
                    result = self.execute_action(tc.function.name, args)
                    status = "OK" if result.get("success") else "FAIL"
                    print(f"  -> {status}")
                    
                    messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
                    
                    if result.get("task_complete"):
                        task_complete = True
                        task_success = result.get("task_success", False)
                        task_summary = result.get("summary", "")
                        break
                    
                    time.sleep(0.3)
                
                if task_complete:
                    break
                    
            except Exception as e:
                error = str(e)
                print(f"[ERROR] {error}")
                break
        
        duration = time.time() - start_time
        final_url = self.driver.current_url if self.driver else None
        
        # Take final screenshot
        self.take_screenshot("final")
        
        # Cleanup
        print(f"\n[Closing in 2s...]")
        time.sleep(2)
        self.stop_browser()
        
        result = TestResult(
            name=task[:30],
            task=task,
            success=task_success,
            steps=self.step_count,
            duration_seconds=round(duration, 2),
            actions=self.action_log,
            verification_results=self.verification_results,
            final_url=final_url,
            error=error
        )
        
        print(f"\n{'='*60}")
        print(f"RESULT: {'SUCCESS' if task_success else 'FAILED'}")
        print(f"Steps: {self.step_count}")
        print(f"Duration: {duration:.2f}s")
        print(f"Verifications: {len(self.verification_results)} ({sum(1 for v in self.verification_results if v['success'])} passed)")
        print(f"{'='*60}")
        
        return result


# ============================================================
# EXPORT
# ============================================================

__all__ = ['UnifiedAgent', 'TestResult', 'AGENT_TOOLS']
