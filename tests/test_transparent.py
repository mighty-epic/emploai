"""
Ultra-Transparent Agent Test
Shows EXACTLY what the LLM receives and decides at each step.

Run: python tests/test_transparent.py
"""

from dotenv import load_dotenv
load_dotenv()

import json
import time
from pathlib import Path
from typing import Dict, List
from openai import OpenAI

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager


# ============================================================
# TOOLS (what LLM can call)
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "observe",
            "description": "Get fresh observation of current screen",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click element by ID or text",
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
            "name": "type_text",
            "description": "Type text into focused element",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "element_id": {"type": "string"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press Enter, Tab, etc",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": ["enter", "tab", "escape"]}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Signal task is done",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "reason": {"type": "string"}
                },
                "required": ["success", "reason"]
            }
        }
    }
]


# ============================================================
# TRANSPARENT AGENT
# ============================================================

class TransparentAgent:
    def __init__(self):
        self.client = OpenAI()
        self.driver = None
        self.full_log = []
    
    def log(self, category: str, data: any):
        """Log with full transparency."""
        entry = {"category": category, "data": data, "time": time.time()}
        self.full_log.append(entry)
        
        print(f"\n{'='*70}")
        print(f"[{category}]")
        print('='*70)
        
        if isinstance(data, dict) or isinstance(data, list):
            print(json.dumps(data, indent=2, default=str)[:2000])
        else:
            print(str(data)[:2000])
    
    def start_browser(self, url: str):
        options = Options()
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.get(url)
        time.sleep(2)
        self.log("BROWSER_STARTED", {"url": url})
    
    def stop_browser(self):
        if self.driver:
            self.driver.quit()
    
    def get_observation(self) -> Dict:
        """Get page state - this is what LLM sees."""
        elements = []
        for tag in ['input', 'button', 'a', 'textarea']:
            for el in self.driver.find_elements(By.TAG_NAME, tag):
                try:
                    if not el.is_displayed():
                        continue
                    el_id = el.get_attribute("id") or el.get_attribute("name") or ""
                    text = el.text or el.get_attribute("placeholder") or el.get_attribute("aria-label") or ""
                    if el_id or text:
                        elements.append({
                            "id": el_id if el_id else f"_{tag}_{len(elements)}",
                            "tag": tag,
                            "text": text[:40]
                        })
                except:
                    continue
        
        return {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "elements": elements[:20]
        }
    
    def execute(self, tool_name: str, args: Dict) -> Dict:
        """Execute action and return result."""
        try:
            if tool_name == "observe":
                return {"success": True, "observation": self.get_observation()}
            
            elif tool_name == "click":
                el = None
                if args.get("element_id"):
                    try: el = self.driver.find_element(By.ID, args["element_id"])
                    except: pass
                    if not el:
                        try: el = self.driver.find_element(By.NAME, args["element_id"])
                        except: pass
                if not el and args.get("text"):
                    try: el = self.driver.find_element(By.LINK_TEXT, args["text"])
                    except: pass
                    if not el:
                        try: el = self.driver.find_element(By.PARTIAL_LINK_TEXT, args["text"])
                        except: pass
                
                if el:
                    el.click()
                    time.sleep(1)
                    return {"success": True, "clicked": args.get("element_id") or args.get("text")}
                return {"success": False, "error": "Element not found"}
            
            elif tool_name == "type_text":
                active = self.driver.switch_to.active_element
                if args.get("element_id"):
                    try: active = self.driver.find_element(By.ID, args["element_id"])
                    except: pass
                active.send_keys(args["text"])
                return {"success": True, "typed": args["text"]}
            
            elif tool_name == "press_key":
                keys = {"enter": Keys.ENTER, "tab": Keys.TAB, "escape": Keys.ESCAPE}
                self.driver.switch_to.active_element.send_keys(keys[args["key"]])
                time.sleep(1)
                return {"success": True, "pressed": args["key"]}
            
            elif tool_name == "task_complete":
                return {"success": True, "task_done": True, "task_success": args["success"], "reason": args["reason"]}
            
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def run(self, task: str, url: str, max_steps: int = 10):
        """Run with full transparency."""
        self.full_log = []
        
        print("\n" + "#"*70)
        print("# TRANSPARENT AGENT RUN")
        print("#"*70)
        
        self.log("TASK", task)
        self.start_browser(url)
        
        # Get initial observation
        obs = self.get_observation()
        self.log("INITIAL_OBSERVATION", obs)
        
        # System prompt
        system = f"""You are an AI agent controlling a browser.
You have these tools: observe, click, type_text, press_key, task_complete.
Complete the task step by step. Call task_complete when done.
Task: {task}"""
        
        self.log("SYSTEM_PROMPT", system)
        
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Current page:\n{json.dumps(obs, indent=2)}"}
        ]
        
        self.log("INITIAL_MESSAGE_TO_LLM", messages[-1]["content"])
        
        for step in range(max_steps):
            print(f"\n{'*'*70}")
            print(f"* STEP {step + 1}")
            print('*'*70)
            
            # Call LLM
            self.log("SENDING_TO_LLM", {
                "message_count": len(messages),
                "tools_available": [t["function"]["name"] for t in TOOLS]
            })
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            
            # Log LLM's thinking
            if msg.content:
                self.log("LLM_THINKING", msg.content)
            
            # Log LLM's decision
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    
                    self.log("LLM_DECIDED", {
                        "tool": tc.function.name,
                        "arguments": args
                    })
                    
                    # Execute
                    result = self.execute(tc.function.name, args)
                    self.log("EXECUTION_RESULT", result)
                    
                    # Add to conversation
                    messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
                    
                    if result.get("task_done"):
                        self.log("TASK_COMPLETE", {
                            "success": result.get("task_success"),
                            "reason": result.get("reason")
                        })
                        self.stop_browser()
                        return result.get("task_success")
            else:
                self.log("LLM_NO_ACTION", "LLM did not call any tools")
                break
        
        self.log("MAX_STEPS_REACHED", max_steps)
        self.stop_browser()
        return False


# ============================================================
# TEST CASES (SD = Step Diff, AD = Adapt Degree)
# ============================================================

TESTS = {
    # SD1 AD1 - Single click
    "sd1_click": {
        "name": "SD1 AD1: Simple Click",
        "task": "Click the 'English' link. Then call task_complete.",
        "url": "https://www.wikipedia.org",
        "sd": 1, "ad": 1
    },
    
    # SD2 AD1 - Click + verify
    "sd2_search": {
        "name": "SD2 AD1: Type and Search",
        "task": "Type 'Python' in the search box and press enter. Call task_complete after.",
        "url": "https://duckduckgo.com",
        "sd": 2, "ad": 1
    },
    
    # SD3 AD1 - Multiple actions
    "sd3_form": {
        "name": "SD3 AD1: Fill Multiple Fields",
        "task": "Type 'John' in the text input, then type 'test@example.com' in the next field. Call task_complete.",
        "url": "https://www.selenium.dev/selenium/web/web-form.html",
        "sd": 3, "ad": 1
    },
    
    # SD4 AD1 - Complex form
    "sd4_complex": {
        "name": "SD4 AD1: Complex Form",
        "task": "Fill these fields: text box with 'Hello', password with 'secret123', then click the Submit button. Call task_complete.",
        "url": "https://www.selenium.dev/selenium/web/web-form.html",
        "sd": 4, "ad": 1
    },
}


def run_test(key: str):
    """Run single test with full transparency."""
    if key not in TESTS:
        print(f"Unknown test: {key}")
        print(f"Available: {list(TESTS.keys())}")
        return
    
    test = TESTS[key]
    print(f"\n{'#'*70}")
    print(f"# TEST: {test['name']}")
    print(f"# SD: {test['sd']} | AD: {test['ad']}")
    print(f"{'#'*70}")
    
    agent = TransparentAgent()
    success = agent.run(test["task"], test["url"])
    
    print(f"\n{'='*70}")
    print(f"FINAL RESULT: {'SUCCESS' if success else 'FAILED'}")
    print(f"{'='*70}")
    
    return success


def run_all():
    """Run all tests."""
    results = {}
    for key in TESTS:
        results[key] = run_test(key)
        time.sleep(2)
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for key, success in results.items():
        test = TESTS[key]
        status = "PASS" if success else "FAIL"
        print(f"  {test['name']}: {status}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_test(sys.argv[1])
    else:
        print("Available tests:")
        for k, v in TESTS.items():
            print(f"  {k}: {v['name']} (SD:{v['sd']}, AD:{v['ad']})")
        print("\nRun with: python tests/test_transparent.py <test_name>")
        print("Or run all: python tests/test_transparent.py all")
