"""
Model Tool Execution Test
Tests how the Gemini model executes browser tools and OCR/click tools.

Run with:
  python tests/test_model_tool_execution.py browser   # Browser tools only
  python tests/test_model_tool_execution.py ocr       # OCR + Click tools only
  python tests/test_model_tool_execution.py           # Choose mode interactively

Logs are saved to: tests/test_logs/
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import json
import time
import base64
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from openai import OpenAI

# ============================================================
# LOGGING SETUP
# ============================================================

LOG_DIR = Path(__file__).parent / "test_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Create timestamped log file
LOG_FILE = LOG_DIR / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure logging
# Configure logging
# File handler gets full DEBUG logs (for troubleshooting)
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s'))

# Console handler gets only INFO logs (cleaner output)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(levelname)-8s | %(message)s'))

# Root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)  # Capture everything at root
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Silence noisy external libraries
for lib in ['openai', 'httpcore', 'httpx', 'urllib3', 'selenium', 'webdriver_manager', 'PIL', 'mss']:
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger("ModelToolTest")
logger.info(f"Log file: {LOG_FILE}")

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================
# TOOL AVAILABILITY CHECKS
# ============================================================

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
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
    import pytesseract
    from PIL import Image
    import mss
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


# ============================================================
# TOOL DEFINITIONS - BROWSER MODE
# ============================================================

BROWSER_TOOLS = [
    {"type": "function", "function": {"name": "open_browser", "description": "Open Chrome browser and navigate to a URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to navigate to"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "observe_browser", "description": "Get browser page state including title, URL, and key elements.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "browser_click", "description": "Click an element in the browser by text content or CSS selector.", "parameters": {"type": "object", "properties": {"target": {"type": "string", "description": "Text content or CSS selector of element to click"}}, "required": ["target"]}}},
    {"type": "function", "function": {"name": "browser_type", "description": "Type text into the focused browser element.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "clear_first": {"type": "boolean", "default": False}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "browser_press_key", "description": "Press a key in the browser (enter, tab, escape, etc).", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "browser_scroll", "description": "Scroll the browser page.", "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer", "default": 300}}}}},
]

BROWSER_SYSTEM_PROMPT = """You are an AI assistant testing browser automation tools.

YOUR TOOLS:
- open_browser: Opens Chrome and navigates to a URL
- observe_browser: Returns the page title, URL, and list of clickable elements
- browser_click: Clicks an element by its text or CSS selector
- browser_type: Types text into the currently focused input field
- browser_press_key: Presses a key (enter, tab, escape, etc)
- browser_scroll: Scrolls the page up or down

WORKFLOW:
1. Use open_browser to navigate to a page
2. Use observe_browser to see what elements are available
3. Use browser_click to interact with elements
4. Use browser_type to fill in forms
5. Use browser_press_key for keyboard actions

Always confirm what you did after completing actions."""


# ============================================================
# TOOL DEFINITIONS - OCR + CLICK MODE
# ============================================================

OCR_CLICK_TOOLS = [
    {"type": "function", "function": {"name": "describe_screen", "description": "Use AI vision to describe the current screen state. Best for understanding UI layout.", "parameters": {"type": "object", "properties": {"question": {"type": "string", "description": "Optional specific question about the screen"}}}}},
    {"type": "function", "function": {"name": "ocr_screen", "description": "Read all text on screen using OCR. Returns text with x,y center coordinates for clicking.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "click", "description": "Click at screen coordinates. Use ocr_screen first to find coordinates of text.", "parameters": {"type": "object", "properties": {"x": {"type": "integer", "description": "X coordinate on screen"}, "y": {"type": "integer", "description": "Y coordinate on screen"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "right_click", "description": "Right-click at screen coordinates.", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "double_click", "description": "Double-click at screen coordinates.", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}}},
    {"type": "function", "function": {"name": "type_text", "description": "Type text using keyboard.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "press_key", "description": "Press a single key (enter, tab, escape, f1, etc).", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "hotkey", "description": "Press a key combination (e.g., ctrl+c, alt+tab, ctrl+shift+n).", "parameters": {"type": "object", "properties": {"keys": {"type": "string", "description": "Keys separated by + (e.g., 'ctrl+c', 'alt+f4')"}}, "required": ["keys"]}}},
]

OCR_CLICK_SYSTEM_PROMPT = """You are an AI assistant testing OCR and desktop click tools.

YOUR TOOLS:
- describe_screen: Takes a screenshot and uses AI vision to describe what's visible
- ocr_screen: Extracts all readable text from the screen WITH x,y CENTER COORDINATES for each element
- click: Clicks at x,y coordinates on screen
- right_click: Right-clicks at x,y coordinates
- double_click: Double-clicks at x,y coordinates
- type_text: Types text using the keyboard
- press_key: Presses a single key
- hotkey: Presses a key combination

CRITICAL WORKFLOW FOR CLICKING:
1. FIRST use describe_screen to understand what's visible on screen
2. THEN use ocr_screen to get the EXACT coordinates of the text you want to click
3. ocr_screen returns elements like: {"text": "Submit", "x": 500, "y": 300, ...}
4. Use those x,y coordinates with click(x, y)

EXAMPLE:
- Task: "Click the Submit button"
- Step 1: describe_screen() → "I see a form with a blue Submit button at the bottom"
- Step 2: ocr_screen() → find {"text": "Submit", "x": 520, "y": 340}
- Step 3: click(520, 340)

NEVER guess coordinates. ALWAYS use ocr_screen to find them first.
Always confirm what you did after completing actions."""


# ============================================================
# TOOL EXECUTOR CLASS
# ============================================================

class TestToolExecutor:
    """Executes tools for testing."""
    
    def __init__(self, model: str = "gemini-3-flash-preview"):
        self.model = model
        self.driver = None
        self.screenshot_dir = Path("tests/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.client = OpenAI(
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    
    def execute(self, name: str, args: Dict) -> Any:
        """Execute a tool by name."""
        args_str = json.dumps(args, indent=2) if args else '{}'
        logger.info(f"TOOL CALL: {name}")
        logger.debug(f"TOOL ARGS: {args_str}")
        
        method = getattr(self, f"_tool_{name}", None)
        if not method:
            logger.error(f"UNKNOWN TOOL: {name}")
            return {"error": f"Unknown tool: {name}"}
        
        try:
            result = method(**args)
            
            # Check if result contains an error
            if isinstance(result, dict) and "error" in result:
                logger.error(f"TOOL ERROR: {name} -> {result['error']}")
            else:
                # Truncate result preview for readability in console
                result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                if len(result_str) > 500:
                    logger.info(f"TOOL SUCCESS: {name} -> {result_str[:500]}...")
                else:
                    logger.info(f"TOOL SUCCESS: {name} -> {result_str}")
                # Log full result to DEBUG for file
                logger.debug(f"FULL RESULT: {result_str}")
            
            return result
        except Exception as e:
            # Log full stack trace
            logger.error(f"TOOL EXCEPTION: {name}")
            logger.error(f"Exception: {e}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")
            return {"error": str(e), "traceback": traceback.format_exc()}
    
    # --- BROWSER TOOLS ---
    
    def _tool_open_browser(self, url: str) -> Dict:
        if not SELENIUM_AVAILABLE:
            return {"error": "Selenium not available"}
        try:
            if not self.driver:
                options = Options()
                options.add_argument("--no-sandbox")
                options.add_argument("--start-maximized")
                options.add_argument("--log-level=3")
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            
            self.driver.get(url)
            time.sleep(1)
            return {"success": True, "url": self.driver.current_url, "title": self.driver.title}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_observe_browser(self) -> Dict:
        if not self.driver:
            return {"error": "No browser open. Use open_browser first."}
        try:
            elements = []
            selectors = [
                ("a", "link"), 
                ("button", "button"), 
                ("input", "input"), 
                ("[role='button']", "button"),
                ("h1, h2, h3", "header"),
            ]
            
            for sel, role in selectors:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel)[:30]:
                    if el.is_displayed():
                        text = (
                            el.text or 
                            el.get_attribute("placeholder") or 
                            el.get_attribute("aria-label") or 
                            el.get_attribute("title") or 
                            el.get_attribute("value")
                        )
                        if text or role == "input":
                            elements.append({
                                "type": role, 
                                "text": (text[:60] + "...") if text and len(text) > 60 else text
                            })
            
            return {
                "title": self.driver.title, 
                "url": self.driver.current_url, 
                "elements": elements[:100]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_browser_click(self, target: str) -> Dict:
        if not self.driver:
            return {"error": "No browser open"}
        try:
            # Comprehensive XPath search
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
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed():
                        el.click()
                        return {"success": True, "clicked": target, "method": "xpath_match"}
            except:
                pass

            # Fallback to CSS selector
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, target)
                if el.is_displayed():
                    el.click()
                    return {"success": True, "clicked": target, "method": "css_selector"}
            except:
                pass

            return {"error": f"Element not found: '{target}'"}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_browser_type(self, text: str, clear_first: bool = False) -> Dict:
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
    
    def _tool_browser_press_key(self, key: str) -> Dict:
        if not self.driver:
            return {"error": "No browser open"}
        try:
            key_map = {"enter": Keys.ENTER, "tab": Keys.TAB, "escape": Keys.ESCAPE, "backspace": Keys.BACKSPACE}
            active = self.driver.switch_to.active_element
            active.send_keys(key_map.get(key.lower(), key))
            return {"success": True, "pressed": key}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_browser_scroll(self, direction: str = "down", amount: int = 300) -> Dict:
        if not self.driver:
            return {"error": "No browser open"}
        try:
            scroll = -amount if direction == "up" else amount
            self.driver.execute_script(f"window.scrollBy(0, {scroll})")
            return {"success": True, "scrolled": direction}
        except Exception as e:
            return {"error": str(e)}
    
    # --- OCR + CLICK TOOLS ---
    
    def _tool_describe_screen(self, question: str = None) -> Dict:
        if not TESSERACT_AVAILABLE:
            return {"error": "Tesseract/mss not available"}
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
    
    def _tool_ocr_screen(self) -> Dict:
        if not TESSERACT_AVAILABLE:
            return {"error": "Tesseract not available"}
        try:
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                
                elements = []
                n_boxes = len(data['text'])
                for i in range(n_boxes):
                    text = data['text'][i].strip()
                    confidence = int(data['conf'][i])
                    
                    if text and confidence > 30:
                        x = data['left'][i]
                        y = data['top'][i]
                        w = data['width'][i]
                        h = data['height'][i]
                        center_x = x + w // 2
                        center_y = y + h // 2
                        
                        elements.append({
                            "text": text,
                            "x": center_x,
                            "y": center_y,
                            "confidence": confidence
                        })
                
                unfiltered_text = pytesseract.image_to_string(img)
                
                return {
                    "elements": elements[:500],  # Limit for readability
                    "plain_text": unfiltered_text[:5000],
                    "total_elements": len(elements)
                }
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_click(self, x: int, y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        try:
            pyautogui.moveTo(x, y, duration=0.1)
            time.sleep(0.05)
            pyautogui.click()
            return {"success": True, "clicked": f"({x}, {y})"}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_right_click(self, x: int, y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        try:
            pyautogui.moveTo(x, y, duration=0.1)
            time.sleep(0.05)
            pyautogui.rightClick()
            return {"success": True, "right_clicked": f"({x}, {y})"}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_double_click(self, x: int, y: int) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        try:
            pyautogui.moveTo(x, y, duration=0.1)
            time.sleep(0.05)
            pyautogui.doubleClick()
            return {"success": True, "double_clicked": f"({x}, {y})"}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_type_text(self, text: str) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.write(text, interval=0.02)
        return {"success": True, "typed": text}
    
    def _tool_press_key(self, key: str) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        pyautogui.press(key)
        return {"success": True, "pressed": key}
    
    def _tool_hotkey(self, keys: str) -> Dict:
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "PyAutoGUI not available"}
        key_list = [k.strip() for k in keys.split('+')]
        pyautogui.hotkey(*key_list)
        return {"success": True, "hotkey": keys}
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass


# ============================================================
# MAIN TEST RUNNER
# ============================================================

class ModelToolTester:
    """Tests how a model executes tools."""
    
    def __init__(self, mode: str):
        self.mode = mode
        self.model = "gemini-3-flash-preview"
        self.executor = TestToolExecutor(self.model)
        
        self.client = OpenAI(
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        
        if mode == "browser":
            self.tools = BROWSER_TOOLS
            self.system_prompt = BROWSER_SYSTEM_PROMPT
        else:  # ocr
            self.tools = OCR_CLICK_TOOLS
            self.system_prompt = OCR_CLICK_SYSTEM_PROMPT
        
        self.messages = []
    
    def run_task(self, task: str, max_turns: int = 20) -> str:
        """Run a task and return the final response."""
        logger.info("="*70)
        logger.info(f"NEW TASK STARTED")
        logger.info(f"MODE: {self.mode.upper()}")
        logger.info(f"TASK: {task}")
        logger.info(f"MODEL: {self.model}")
        logger.info(f"MAX TURNS: {max_turns}")
        logger.info("="*70)
        
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task}
        ]
        
        for turn in range(max_turns):
            logger.info(f"")
            logger.info(f"--- TURN {turn + 1}/{max_turns} ---")
            
            try:
                logger.debug(f"Calling model: {self.model}")
                logger.debug(f"Message count: {len(self.messages)}")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=self.tools,
                    max_tokens=2000
                )
                
                message = response.choices[0].message
                
                # Log token usage if available
                if hasattr(response, 'usage') and response.usage:
                    logger.debug(f"Token usage - Input: {response.usage.prompt_tokens}, Output: {response.usage.completion_tokens}")
                
                # If no tool calls, task is complete
                if not message.tool_calls:
                    logger.info(f"TASK COMPLETE")
                    logger.info(f"Final response: {message.content}")
                    return message.content or "Task completed."
                
                # Show model's thinking
                if message.content:
                    logger.info(f"MODEL THINKING: {message.content}")
                
                # Log tool calls summary
                tool_names = [tc.function.name for tc in message.tool_calls]
                logger.info(f"MODEL REQUESTED TOOLS: {tool_names}")
                
                # Execute tool calls
                self.messages.append(message)
                
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON PARSE ERROR for tool {func_name}: {e}")
                        logger.error(f"Raw arguments: {tool_call.function.arguments}")
                        args = {}
                    
                    logger.info(f"")
                    logger.info(f"🔧 EXECUTING: {func_name}")
                    result = self.executor.execute(func_name, args)
                    
                    # Check for errors in result
                    if isinstance(result, dict) and "error" in result:
                        logger.warning(f"Tool returned error: {result['error']}")
                    
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result) if isinstance(result, dict) else str(result)
                    })
                
            except Exception as e:
                logger.error(f"TURN ERROR: {e}")
                logger.error(f"Stack trace:\n{traceback.format_exc()}")
                return f"Error: {e}"
        
        logger.warning(f"MAX TURNS REACHED ({max_turns})")
        return "Max turns reached without completion."
    
    def cleanup(self):
        """Clean up resources."""
        self.executor.cleanup()


def main():
    """Main entry point."""
    logger.info("="*70)
    logger.info("MODEL TOOL EXECUTION TEST STARTED")
    logger.info(f"Selenium available: {SELENIUM_AVAILABLE}")
    logger.info(f"PyAutoGUI available: {PYAUTOGUI_AVAILABLE}")
    logger.info(f"Tesseract available: {TESSERACT_AVAILABLE}")
    logger.info("="*70)
    
    print("\n" + "="*70)
    print("MODEL TOOL EXECUTION TEST")
    print("="*70)
    print("This tests how the Gemini model generates and executes tool calls.")
    print("Your mouse may be moved during OCR+Click mode tests.")
    print(f"\n📁 Logs saved to: {LOG_FILE}\n")
    
    # Determine mode
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode not in ["browser", "ocr"]:
            logger.error(f"Unknown mode: {mode}")
            print(f"Unknown mode: {mode}")
            print("Usage: python test_model_tool_execution.py [browser|ocr]")
            return
    else:
        print("Select mode:")
        print("  1. browser - Test browser tools (open_browser, browser_click, etc)")
        print("  2. ocr     - Test OCR + click tools (ocr_screen, click, etc)")
        mode_input = input("\nEnter mode (browser/ocr): ").strip().lower()
        mode = mode_input if mode_input in ["browser", "ocr"] else "browser"
    
    logger.info(f"MODE SELECTED: {mode.upper()}")
    print(f"\n🚀 Starting {mode.upper()} mode...")
    
    tester = ModelToolTester(mode)
    
    try:
        while True:
            print("\n" + "-"*70)
            task = input("Enter task (or 'quit' to exit): ").strip()
            
            if task.lower() in ['quit', 'exit', 'q']:
                logger.info("User requested exit")
                break
            
            if not task:
                print("Please enter a task.")
                continue
            
            result = tester.run_task(task)
            print(f"\n{'='*70}")
            print(f"FINAL RESULT:")
            print(f"{'='*70}")
            print(result)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")
        print("\n\nInterrupted by user.")
    finally:
        tester.cleanup()
        logger.info("Test session ended")
        logger.info(f"Log file: {LOG_FILE}")
        print(f"\n👋 Test session ended.")
        print(f"📁 Full log saved to: {LOG_FILE}")


if __name__ == "__main__":
    main()

