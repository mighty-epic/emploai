"""
Real LLM Integration Tests
Tests actual LLM decision-making with different observation modes.

Run with: python -m tests.test_real_llm_decisions
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# Load environment
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.tools.definitions import OBSERVATION_TOOLS, ACTION_TOOLS, SYSTEM_TOOLS
from shared.schemas.observation import ObservationSnapshot


class ObservationMode(Enum):
    SELENIUM_ONLY = "selenium"
    PYWINAUTO_ONLY = "pywinauto"
    TESSERACT_ONLY = "tesseract"
    ALL_COMBINED = "all"


@dataclass
class TestResult:
    task: str
    observation_mode: ObservationMode
    model: str
    tool_calls: List[Dict]
    reasoning: str
    success: bool
    duration_seconds: float
    error: Optional[str] = None


class RealLLMTester:
    """Tests real LLM decision-making with actual observations."""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.client = self._setup_client()
        self.tool_call_log = []
    
    def _setup_client(self):
        """Setup OpenAI or Anthropic client based on model."""
        if "gpt" in self.model or "o1" in self.model:
            from openai import OpenAI
            return OpenAI()
        elif "claude" in self.model:
            from anthropic import Anthropic
            return Anthropic()
        else:
            raise ValueError(f"Unknown model: {self.model}")
    
    def get_tools_for_mode(self, mode: ObservationMode) -> List[Dict]:
        """Get limited tools based on observation mode."""
        # Basic observation tool
        observe_tool = {
            "type": "function",
            "function": {
                "name": "observe_screen",
                "description": "Get the current screen state. Returns visible elements with their positions and text.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        
        # Basic action tools
        click_tool = {
            "type": "function",
            "function": {
                "name": "click",
                "description": "Click on an element by its ID or text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "string", "description": "ID of the element to click"},
                        "text": {"type": "string", "description": "Text of the element to click (if ID not known)"}
                    },
                    "required": []
                }
            }
        }
        
        type_tool = {
            "type": "function",
            "function": {
                "name": "type_text",
                "description": "Type text into the currently focused element.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"}
                    },
                    "required": ["text"]
                }
            }
        }
        
        done_tool = {
            "type": "function",
            "function": {
                "name": "task_complete",
                "description": "Signal that the task is complete.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "description": "Whether the task was completed successfully"},
                        "message": {"type": "string", "description": "Summary of what was done"}
                    },
                    "required": ["success"]
                }
            }
        }
        
        return [observe_tool, click_tool, type_tool, done_tool]
    
    def get_observation(self, mode: ObservationMode) -> Dict:
        """Get actual observation based on mode."""
        if mode == ObservationMode.SELENIUM_ONLY:
            return self._get_selenium_observation()
        elif mode == ObservationMode.PYWINAUTO_ONLY:
            return self._get_pywinauto_observation()
        elif mode == ObservationMode.TESSERACT_ONLY:
            return self._get_tesseract_observation()
        elif mode == ObservationMode.ALL_COMBINED:
            return self._get_combined_observation()
    
    def _get_selenium_observation(self) -> Dict:
        """Get browser observation via Selenium."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from webdriver_manager.chrome import ChromeDriverManager
            
            options = Options()
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            # Navigate to a simple page
            driver.get("https://www.google.com")
            time.sleep(2)
            
            # Extract elements
            elements = []
            for tag in ['button', 'input', 'a', 'textarea']:
                for el in driver.find_elements("tag name", tag):
                    try:
                        rect = el.rect
                        elements.append({
                            "id": el.get_attribute("id") or f"{tag}_{len(elements)}",
                            "type": tag,
                            "text": el.text or el.get_attribute("placeholder") or el.get_attribute("aria-label") or "",
                            "x": rect["x"],
                            "y": rect["y"],
                            "width": rect["width"],
                            "height": rect["height"]
                        })
                    except:
                        continue
            
            observation = {
                "source": "selenium",
                "url": driver.current_url,
                "title": driver.title,
                "elements": elements[:20]  # Limit for context
            }
            
            driver.quit()
            return observation
            
        except Exception as e:
            return {"source": "selenium", "error": str(e), "elements": []}
    
    def _get_pywinauto_observation(self) -> Dict:
        """Get desktop observation via pywinauto."""
        try:
            from pywinauto import Desktop
            
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            
            if not windows:
                return {"source": "pywinauto", "error": "No windows found", "elements": []}
            
            # Get active window
            active = windows[0]
            elements = []
            
            try:
                for child in active.descendants()[:30]:
                    try:
                        rect = child.rectangle()
                        elements.append({
                            "id": child.element_info.automation_id or f"ctrl_{len(elements)}",
                            "type": child.element_info.control_type,
                            "text": child.element_info.name or "",
                            "x": rect.left,
                            "y": rect.top,
                            "width": rect.width(),
                            "height": rect.height()
                        })
                    except:
                        continue
            except:
                pass
            
            return {
                "source": "pywinauto",
                "window_title": active.element_info.name,
                "elements": elements[:20]
            }
            
        except Exception as e:
            return {"source": "pywinauto", "error": str(e), "elements": []}
    
    def _get_tesseract_observation(self) -> Dict:
        """Get screenshot-based observation via Tesseract."""
        try:
            import pytesseract
            from PIL import Image
            import mss
            import mss.tools
            
            # Capture screenshot
            with mss.mss() as sct:
                screenshot = sct.grab(sct.monitors[1])
                img_path = "temp_screenshot.png"
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=img_path)
            
            # OCR
            image = Image.open(img_path)
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            elements = []
            for i, text in enumerate(data['text']):
                if text.strip() and float(data['conf'][i]) > 50:
                    elements.append({
                        "id": f"text_{len(elements)}",
                        "type": "text",
                        "text": text.strip(),
                        "x": data['left'][i],
                        "y": data['top'][i],
                        "width": data['width'][i],
                        "height": data['height'][i],
                        "confidence": float(data['conf'][i])
                    })
            
            os.remove(img_path)
            
            return {
                "source": "tesseract",
                "screen_size": f"{screenshot.width}x{screenshot.height}",
                "elements": elements[:30]
            }
            
        except Exception as e:
            return {"source": "tesseract", "error": str(e), "elements": []}
    
    def _get_combined_observation(self) -> Dict:
        """Get observation from all sources."""
        return {
            "selenium": self._get_selenium_observation(),
            "pywinauto": self._get_pywinauto_observation(),
            "tesseract": self._get_tesseract_observation()
        }
    
    def run_task(self, task: str, mode: ObservationMode, max_steps: int = 5) -> TestResult:
        """Run a task with real LLM decision-making."""
        print(f"\n{'='*60}")
        print(f"TASK: {task}")
        print(f"MODE: {mode.value}")
        print(f"MODEL: {self.model}")
        print(f"{'='*60}")
        
        start_time = time.time()
        tools = self.get_tools_for_mode(mode)
        tool_calls = []
        
        # System prompt
        system_prompt = f"""You are an AI agent that controls a computer. 
Your task: {task}

You can observe the screen and perform actions. Think step by step:
1. First, observe the current screen state
2. Analyze what elements are available
3. Decide what action to take
4. Execute the action
5. Verify the result

Be precise with your actions. Use element IDs when available.
When the task is complete, call task_complete.

Current observation mode: {mode.value}"""

        messages = [{"role": "system", "content": system_prompt}]
        
        # Get initial observation
        print("\n[INITIAL OBSERVATION]")
        observation = self.get_observation(mode)
        print(f"  Source: {observation.get('source', mode.value)}")
        print(f"  Elements: {len(observation.get('elements', []))}")
        
        messages.append({
            "role": "user",
            "content": f"Here is the current screen state:\n{json.dumps(observation, indent=2)}\n\nPlease proceed with the task: {task}"
        })
        
        reasoning = []
        success = False
        error = None
        
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")
            
            try:
                # Call LLM
                if "gpt" in self.model:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto"
                    )
                    
                    assistant_message = response.choices[0].message
                    
                    # Log reasoning
                    if assistant_message.content:
                        print(f"[REASONING]: {assistant_message.content[:200]}...")
                        reasoning.append(assistant_message.content)
                    
                    # Check for tool calls
                    if assistant_message.tool_calls:
                        for tool_call in assistant_message.tool_calls:
                            func_name = tool_call.function.name
                            func_args = json.loads(tool_call.function.arguments)
                            
                            print(f"[TOOL CALL]: {func_name}({func_args})")
                            tool_calls.append({"name": func_name, "args": func_args})
                            
                            # Handle task_complete
                            if func_name == "task_complete":
                                success = func_args.get("success", False)
                                print(f"[TASK COMPLETE]: success={success}")
                                break
                            
                            # Simulate tool response
                            tool_response = self._simulate_tool(func_name, func_args, mode)
                            
                            messages.append({"role": "assistant", "content": None, "tool_calls": [tool_call]})
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(tool_response)
                            })
                        
                        if success or any(tc["name"] == "task_complete" for tc in tool_calls):
                            break
                    else:
                        # No tool calls, model is done
                        print("[NO TOOL CALLS] - Model finished without calling tools")
                        break
                        
            except Exception as e:
                error = str(e)
                print(f"[ERROR]: {error}")
                break
        
        duration = time.time() - start_time
        
        result = TestResult(
            task=task,
            observation_mode=mode,
            model=self.model,
            tool_calls=tool_calls,
            reasoning="\n".join(reasoning),
            success=success,
            duration_seconds=duration,
            error=error
        )
        
        print(f"\n[RESULT]")
        print(f"  Success: {result.success}")
        print(f"  Tool calls: {len(result.tool_calls)}")
        print(f"  Duration: {result.duration_seconds:.2f}s")
        
        return result
    
    def _simulate_tool(self, func_name: str, func_args: Dict, mode: ObservationMode) -> Dict:
        """Simulate tool execution (for safety)."""
        if func_name == "observe_screen":
            return self.get_observation(mode)
        elif func_name == "click":
            return {"success": True, "clicked": func_args.get("element_id") or func_args.get("text")}
        elif func_name == "type_text":
            return {"success": True, "typed": func_args.get("text")}
        else:
            return {"success": True}


def run_selenium_test():
    """Test 1: Browser-only with Selenium."""
    print("\n" + "="*70)
    print("TEST 1: SELENIUM ONLY (Browser)")
    print("="*70)
    
    tester = RealLLMTester(model="gpt-4o-mini")  # Use mini for cost efficiency
    
    task = "Find the search box on the page and describe what you see"
    result = tester.run_task(task, ObservationMode.SELENIUM_ONLY, max_steps=3)
    
    return result


def run_pywinauto_test():
    """Test 2: Desktop-only with pywinauto."""
    print("\n" + "="*70)
    print("TEST 2: PYWINAUTO ONLY (Desktop)")
    print("="*70)
    
    tester = RealLLMTester(model="gpt-4o-mini")
    
    task = "Observe the current window and list the main UI elements you see"
    result = tester.run_task(task, ObservationMode.PYWINAUTO_ONLY, max_steps=3)
    
    return result


def run_tesseract_test():
    """Test 3: Screenshot-only with Tesseract."""
    print("\n" + "="*70)
    print("TEST 3: TESSERACT ONLY (Screenshot OCR)")
    print("="*70)
    
    tester = RealLLMTester(model="gpt-4o-mini")
    
    task = "Read the text on the screen and describe what application is visible"
    result = tester.run_task(task, ObservationMode.TESSERACT_ONLY, max_steps=3)
    
    return result


def run_combined_test():
    """Test 4: All observation methods combined."""
    print("\n" + "="*70)
    print("TEST 4: ALL COMBINED (Multi-Platform)")
    print("="*70)
    
    tester = RealLLMTester(model="gpt-4o-mini")
    
    task = "Analyze the screen using all available observation methods and summarize what you see"
    result = tester.run_task(task, ObservationMode.ALL_COMBINED, max_steps=3)
    
    return result


def run_all_tests():
    """Run all real LLM tests."""
    print("\n" + "="*70)
    print("REAL LLM DECISION-MAKING TESTS")
    print("="*70)
    
    results = []
    
    # Test 1: Selenium
    results.append(run_selenium_test())
    
    # Test 2: pywinauto
    results.append(run_pywinauto_test())
    
    # Test 3: Tesseract
    results.append(run_tesseract_test())
    
    # Test 4: Combined
    results.append(run_combined_test())
    
    # Summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    
    for r in results:
        status = "✅" if r.success or not r.error else "⚠️"
        print(f"  {status} {r.observation_mode.value}: {len(r.tool_calls)} tool calls, {r.duration_seconds:.2f}s")
    
    return results


if __name__ == "__main__":
    run_all_tests()
