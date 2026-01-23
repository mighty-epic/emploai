"""
Executor Agent - Stateless Action/Observation Executor (FULL Logic)
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

# Tool Availability Checks
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
    pyautogui.FAILSAFE = False 
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
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
# EXECUTOR TOOLS (Full Set)
# ============================================================

EXECUTOR_TOOLS = [
    {"type": "function", "function": {"name": "observe_browser", "description": "Get browser page state", "parameters": {"type": "object", "properties": {"include_screenshot": {"type": "boolean", "default": True}}}}},
    {"type": "function", "function": {"name": "observe_desktop", "description": "Get desktop state", "parameters": {"type": "object", "properties": {"window_title": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "observe_screen_ocr", "description": "Read screen text via OCR", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "capture_screenshot", "description": "Take screenshot", "parameters": {"type": "object", "properties": {"region": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "click_element", "description": "Click element or coordinates", "parameters": {"type": "object", "properties": {"target": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}}}}},
    {"type": "function", "function": {"name": "type_text", "description": "Type text", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "target": {"type": "string"}, "clear_first": {"type": "boolean", "default": False}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "press_key", "description": "Press key", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "scroll", "description": "Scroll", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer", "default": 3}}, "required": ["direction"]}}},
    {"type": "function", "function": {"name": "navigate_to", "description": "Navigate to URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "summarize_screen", "description": "Use vision to describe the current screen state", "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "Specific question about the screen"}}}}}
]

EXECUTOR_SYSTEM_PROMPT = """You are a PURE TOOL OPERATOR.
1. ATOMIC EXECUTION: Perform exactly ONE tool call to fulfill the REQUEST.
2. NO CHAINING: Do not attempt to click and then observe, or type and then press enter. Execute one atomic action and return.
3. NO PLANNING: The Memory Agent manages the sequence. Your only job is to execute the current atomic step.
"""

class ExecutorAgent:
    def __init__(self, model: str = "gemini-3-flash-preview", screenshot_dir: str = "test_outputs/screenshots"):
        self.model = model
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.driver = None
        self.client = self._setup_client()
    
    def _setup_client(self):
        m_lower = self.model.lower()
        if "gemini" in m_lower:
            return OpenAI(api_key=os.getenv("GEMINI_API_KEY"), base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        return OpenAI(api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1") if "grok" in m_lower else OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def execute(self, request: ExecutorRequest) -> ExecutorResponse:
        messages = [{"role": "system", "content": EXECUTOR_SYSTEM_PROMPT}, {"role": "user", "content": f"REQUEST: {request.to_prompt()}"}]
        try:
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=EXECUTOR_TOOLS, tool_choice="auto")
            return self._process_response(response, request)
        except Exception as e:
            return ExecutorResponse(request_type=request.request_type, impossible=True, impossible_reason=str(e))

    def _process_response(self, response, request: ExecutorRequest) -> ExecutorResponse:
        message = response.choices[0].message
        results = []
        obs_res = None
        act_res = None
        
        if message.tool_calls:
            # FORCE ATOMICITY: Only execute the first tool call, ignore any chaining
            tool_call = message.tool_calls[0]
            func_name = tool_call.function.name
            res = self._execute_tool(func_name, json.loads(tool_call.function.arguments))
            
            is_obs = func_name.startswith("observe") or func_name in ["capture_screenshot", "summarize_screen"]
            if is_obs:
                obs_res = res
                title = res.screen_title if hasattr(res, 'screen_title') else "Success"
                results.append(f"Observation: {title}")
            else:
                act_res = res
                results.append(f"Action ({func_name}): {res.action_taken}")
        
        if not results:
            return ExecutorResponse(request_type=request.request_type, impossible=True, impossible_reason="No tools executed")

        summary = " | ".join(results)
        
        if request.request_type == RequestType.OBSERVE:
            return ExecutorResponse(
                request_type=RequestType.OBSERVE,
                observation=obs_res or ObservationResult(success=True, method_used="direct", screen_title=summary)
            )
        else:
            # If it's a STEP, we allow success via observation (verification) OR action.
            # We ONLY return impossible if an ACTION was requested but only observation occurred.
            if request.request_type == RequestType.ACTION and not act_res and obs_res:
                return ExecutorResponse(
                    request_type=request.request_type,
                    impossible=True,
                    impossible_reason=f"Executor only observed ({summary}) but did not perform the requested ACTION."
                )
            
            return ExecutorResponse(
                request_type=request.request_type,
                action=act_res or ActionResult(success=True, action_taken=summary)
            )

    def _execute_tool(self, name: str, args: Dict) -> Any:
        if name == "summarize_screen": return self._describe_screen(args.get("question"))
        if name == "observe_browser": return self._observe_browser(args.get("include_screenshot", True))
        if name == "observe_desktop": return self._observe_desktop(args.get("window_title"))
        if name == "observe_screen_ocr": return self._observe_ocr()
        if name == "capture_screenshot": return self._capture_screenshot(args.get("region", "full"))
        if name == "click_element": return self._click(args.get("target"), args.get("x"), args.get("y"))
        if name == "type_text": return self._type_text(args.get("text"), args.get("target"), args.get("clear_first", False))
        if name == "press_key": return self._press_key(args.get("key"))
        if name == "scroll": return self._scroll(args.get("direction"), args.get("amount", 3))
        if name == "navigate_to": return self._navigate(args.get("url"))
        if name == "focus_window": return self._focus_window(args.get("window_title"))
        if name == "report_result": return args
        return {"error": f"Unknown tool: {name}"}

    def _observe_browser(self, include_screenshot: bool = True) -> ObservationResult:
        if not self.driver: return ObservationResult(success=False, method_used="browser", error="No browser instance")
        try:
            elements = []
            for sel, role in [("a", "link"), ("button", "button"), ("input", "input")]:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel)[:10]:
                    if el.is_displayed():
                        elements.append({"type": role, "text": el.text[:50], "tag": el.tag_name})
            screenshot_path = None
            if include_screenshot:
                screenshot_path = str(self.screenshot_dir / f"browser_{int(time.time())}.png")
                self.driver.save_screenshot(screenshot_path)
            return ObservationResult(success=True, method_used="browser", screen_title=self.driver.title, url=self.driver.current_url, key_elements=elements, screenshot_path=screenshot_path)
        except Exception as e: return ObservationResult(success=False, method_used="browser", error=str(e))

    def _observe_desktop(self, window_title: Optional[str] = None) -> ObservationResult:
        if not PYWINAUTO_AVAILABLE: return ObservationResult(success=False, method_used="desktop", error="pywinauto not available")
        try:
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            all_elements = []
            active_title = ""
            for win in windows:
                try:
                    title = win.window_text()
                    if not title: continue
                    is_active = win.is_active()
                    if is_active: active_title = title
                    all_elements.append({"type": "window", "text": title, "is_active": is_active})
                    # Enumerate children logic simplified for speed in test folder
                except: continue
            return ObservationResult(success=True, method_used="desktop", screen_title=active_title, key_elements=all_elements[:30])
        except Exception as e: return ObservationResult(success=False, method_used="desktop", error=str(e))

    def _observe_ocr(self) -> ObservationResult:
        if not TESSERACT_AVAILABLE: return ObservationResult(success=False, method_used="ocr", error="Tesseract not available")
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                text = pytesseract.image_to_string(img)
                return ObservationResult(success=True, method_used="ocr", raw_text=text[:2000])
        except Exception as e: return ObservationResult(success=False, method_used="ocr", error=str(e))

    def _describe_screen(self, question: Optional[str] = None) -> ObservationResult:
        """Use vision to describe screen state."""
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                path = str(self.screenshot_dir / f"describe_{int(time.time())}.png")
                img.save(path)
                
                # Encode for multimodal call
                with open(path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                prompt = question if question else "Describe this screen in detail. What applications are open? What is the focused element?"
                messages = [
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]}
                ]
                
                response = self.client.chat.completions.create(model=self.model, messages=messages, max_tokens=500)
                description = response.choices[0].message.content
                
                return ObservationResult(success=True, method_used="vision", screen_title=description[:100], raw_text=description, screenshot_path=path)
        except Exception as e:
            return ObservationResult(success=False, method_used="vision", error=str(e))

    def _capture_screenshot(self, region: str = "full") -> ObservationResult:
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                path = str(self.screenshot_dir / f"screen_{int(time.time())}.png")
                img.save(path)
                return ObservationResult(success=True, method_used="screenshot", screenshot_path=path)
        except Exception as e: return ObservationResult(success=False, error=str(e))

    def _click(self, target, x, y) -> ActionResult:
        if not PYAUTOGUI_AVAILABLE: return ActionResult(success=False, failure_reason="pyautogui missing")
        try:
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
                return ActionResult(success=True, action_taken=f"Clicked at ({x}, {y})")
            if self.driver and target:
                try:
                    el = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{target}')]")
                    el.click()
                    return ActionResult(success=True, action_taken=f"Clicked browser element '{target}'")
                except: pass
            return ActionResult(success=False, failure_reason=f"Target '{target}' not found")
        except Exception as e: return ActionResult(success=False, failure_reason=str(e))

    def _type_text(self, text, target, clear_first) -> ActionResult:
        if not PYAUTOGUI_AVAILABLE: return ActionResult(success=False, failure_reason="pyautogui missing")
        try:
            if clear_first:
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.press('delete')
            pyautogui.write(text, interval=0.01)
            return ActionResult(success=True, action_taken=f"Typed '{text}'")
        except Exception as e: return ActionResult(success=False, failure_reason=str(e))

    def _press_key(self, key) -> ActionResult:
        if not PYAUTOGUI_AVAILABLE: return ActionResult(success=False, failure_reason="pyautogui missing")
        try:
            pyautogui.press(key)
            return ActionResult(success=True, action_taken=f"Pressed '{key}'")
        except Exception as e: return ActionResult(success=False, failure_reason=str(e))

    def _scroll(self, direction, amount) -> ActionResult:
        if not PYAUTOGUI_AVAILABLE: return ActionResult(success=False, failure_reason="pyautogui missing")
        try:
            clicks = amount * 100 if direction == "down" else -amount * 100
            pyautogui.scroll(clicks)
            return ActionResult(success=True, action_taken=f"Scrolled {direction}")
        except Exception as e: return ActionResult(success=False, failure_reason=str(e))

    def _navigate(self, url) -> ActionResult:
        if not SELENIUM_AVAILABLE: return ActionResult(success=False, failure_reason="Selenium missing")
        try:
            if not self.driver:
                options = Options()
                options.add_argument("--no-sandbox")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.get(url)
            return ActionResult(success=True, action_taken=f"Navigated to {url}")
        except Exception as e: return ActionResult(success=False, failure_reason=str(e))

    def _focus_window(self, window_title) -> ActionResult:
        if not PYWINAUTO_AVAILABLE: return ActionResult(success=False, failure_reason="pywinauto missing")
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(title_re=f".*{window_title}.*")
            app.top_window().set_focus()
            return ActionResult(success=True, action_taken=f"Focused '{window_title}'")
        except Exception as e: return ActionResult(success=False, failure_reason=str(e))

    def _build_response_from_report(self, report, request) -> ExecutorResponse:
        success = report.get("success", False)
        if request.request_type == RequestType.OBSERVE:
            return ExecutorResponse(request_type=RequestType.OBSERVE, observation=ObservationResult(success=success, screen_title=report.get("summary")))
        return ExecutorResponse(request_type=RequestType.ACTION, action=ActionResult(success=success, action_taken=report.get("summary")))
