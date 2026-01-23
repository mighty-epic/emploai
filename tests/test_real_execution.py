"""
REAL LLM Agent Executor
Actually executes LLM decisions in a real browser using Selenium.

The LLM observes → decides → EXECUTES → observes result → continues
"""

from dotenv import load_dotenv
load_dotenv()

import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from openai import OpenAI

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ============================================================
# TOOLS FOR LLM
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click on an element. Use element_id if available, otherwise use text to find by visible text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string", "description": "ID attribute of element"},
                    "text": {"type": "string", "description": "Visible text of element to click"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently focused element or a specific element",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "element_id": {"type": "string", "description": "Optional: ID of element to type into"},
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
            "description": "Press a special key like Enter, Tab, Escape",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key to press: enter, tab, escape, backspace"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate to a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait for a specified number of seconds",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Seconds to wait"}
                },
                "required": ["seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Signal that the task is complete",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "description": "Whether task succeeded"},
                    "summary": {"type": "string", "description": "What was accomplished"}
                },
                "required": ["success"]
            }
        }
    }
]


# ============================================================
# REAL BROWSER AGENT
# ============================================================

class RealBrowserAgent:
    """Agent that actually controls a browser."""
    
    def __init__(self, model: str = "gpt-4o-mini", headless: bool = False):
        self.model = model
        self.client = OpenAI()
        self.driver = None
        self.headless = headless
        self.action_log = []
    
    def start_browser(self):
        """Start Chrome browser."""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_window_size(1200, 800)
        print("[Browser] Started Chrome")
    
    def stop_browser(self):
        """Stop browser."""
        if self.driver:
            self.driver.quit()
            print("[Browser] Closed")
    
    def get_observation(self) -> Dict:
        """Get current page state."""
        elements = []
        
        # Find interactive elements
        for tag in ['input', 'button', 'a', 'textarea', 'select']:
            for el in self.driver.find_elements(By.TAG_NAME, tag):
                try:
                    if not el.is_displayed():
                        continue
                    
                    el_id = el.get_attribute("id") or el.get_attribute("name") or ""
                    text = el.text or el.get_attribute("placeholder") or el.get_attribute("aria-label") or el.get_attribute("value") or ""
                    el_type = el.get_attribute("type") or tag
                    
                    rect = el.rect
                    
                    elements.append({
                        "id": el_id if el_id else f"_{tag}_{len(elements)}",
                        "tag": tag,
                        "type": el_type,
                        "text": text[:50] if text else "",
                        "x": int(rect["x"]),
                        "y": int(rect["y"])
                    })
                except:
                    continue
        
        return {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "elements": elements[:20]  # Limit for context
        }
    
    def execute_action(self, tool_name: str, args: Dict) -> Dict:
        """Actually execute an action in the browser."""
        result = {"success": False, "error": None}
        
        try:
            if tool_name == "click":
                element = None
                if args.get("element_id"):
                    try:
                        element = self.driver.find_element(By.ID, args["element_id"])
                    except:
                        try:
                            element = self.driver.find_element(By.NAME, args["element_id"])
                        except:
                            pass
                
                if not element and args.get("text"):
                    # Try finding by text
                    try:
                        element = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{args['text']}')]")
                    except:
                        try:
                            element = self.driver.find_element(By.XPATH, f"//button[contains(., '{args['text']}')]")
                        except:
                            try:
                                element = self.driver.find_element(By.LINK_TEXT, args['text'])
                            except:
                                pass
                
                if element:
                    element.click()
                    result["success"] = True
                    result["clicked"] = args.get("element_id") or args.get("text")
                else:
                    result["error"] = "Element not found"
            
            elif tool_name == "type_text":
                element = None
                if args.get("element_id"):
                    try:
                        element = self.driver.find_element(By.ID, args["element_id"])
                    except:
                        try:
                            element = self.driver.find_element(By.NAME, args["element_id"])
                        except:
                            pass
                
                if not element:
                    # Use active element
                    element = self.driver.switch_to.active_element
                
                if args.get("clear_first"):
                    element.clear()
                
                element.send_keys(args["text"])
                result["success"] = True
                result["typed"] = args["text"]
            
            elif tool_name == "press_key":
                key_map = {
                    "enter": Keys.ENTER,
                    "tab": Keys.TAB,
                    "escape": Keys.ESCAPE,
                    "backspace": Keys.BACKSPACE
                }
                key = key_map.get(args["key"].lower())
                if key:
                    self.driver.switch_to.active_element.send_keys(key)
                    result["success"] = True
                else:
                    result["error"] = f"Unknown key: {args['key']}"
            
            elif tool_name == "navigate":
                self.driver.get(args["url"])
                time.sleep(1)
                result["success"] = True
                result["navigated_to"] = args["url"]
            
            elif tool_name == "wait":
                time.sleep(args.get("seconds", 1))
                result["success"] = True
            
            elif tool_name == "task_complete":
                result["success"] = True
                result["task_complete"] = True
                result["summary"] = args.get("summary", "")
            
            else:
                result["error"] = f"Unknown action: {tool_name}"
        
        except Exception as e:
            result["error"] = str(e)
        
        # Log action
        self.action_log.append({
            "action": tool_name,
            "args": args,
            "result": result
        })
        
        return result
    
    def run_task(self, task: str, start_url: str = None, max_steps: int = 10) -> Dict:
        """Run a task with real browser execution."""
        print(f"\n{'='*60}")
        print(f"TASK: {task}")
        print(f"{'='*60}")
        
        self.start_browser()
        self.action_log = []
        
        try:
            # Navigate to start URL
            if start_url:
                print(f"\n[Navigate] {start_url}")
                self.driver.get(start_url)
                time.sleep(2)
            
            system_prompt = f"""You are an AI agent controlling a real web browser.
Complete the task by using tools to interact with the page.
After each action, you'll receive the updated page state.
When done, call task_complete.

Be precise with element IDs. If an ID doesn't work, try using text.
If something fails, try an alternative approach.

Task: {task}"""

            messages = [{"role": "system", "content": system_prompt}]
            
            for step in range(max_steps):
                # Get current observation
                obs = self.get_observation()
                print(f"\n--- Step {step + 1} ---")
                print(f"[Observe] URL: {obs['url']}")
                print(f"[Observe] Elements: {len(obs['elements'])}")
                
                # Send to LLM
                messages.append({
                    "role": "user",
                    "content": f"Current page state:\n{json.dumps(obs, indent=2)}"
                })
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                
                if msg.content:
                    print(f"[Thinking] {msg.content[:100]}...")
                
                if not msg.tool_calls:
                    print("[No action] LLM did not call any tools")
                    break
                
                # Execute each tool call
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    print(f"[Action] {tc.function.name}({json.dumps(args)})")
                    
                    # ACTUALLY EXECUTE
                    result = self.execute_action(tc.function.name, args)
                    
                    if result["success"]:
                        print(f"[Result] Success")
                    else:
                        print(f"[Result] Failed: {result.get('error')}")
                    
                    # Add to conversation
                    messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result)
                    })
                    
                    # Check if done
                    if result.get("task_complete"):
                        print(f"\n[COMPLETE] {result.get('summary', 'Task finished')}")
                        return {
                            "success": True,
                            "steps": step + 1,
                            "actions": self.action_log
                        }
                    
                    # Small delay between actions
                    time.sleep(0.5)
            
            return {
                "success": False,
                "reason": "Max steps reached",
                "steps": max_steps,
                "actions": self.action_log
            }
        
        finally:
            # Keep browser open for 3 seconds to see result
            print("\n[Waiting 3s before closing browser...]")
            time.sleep(3)
            self.stop_browser()


# ============================================================
# TEST SCENARIOS
# ============================================================

def test_google_search():
    """Test: Search on Google (Step Diff: 2, Adapt: 1)"""
    print("\n" + "=" * 70)
    print("TEST: Google Search (SD:2, AD:1)")
    print("=" * 70)
    
    agent = RealBrowserAgent()
    result = agent.run_task(
        task="Search for 'Selenium Python tutorial' on Google",
        start_url="https://www.google.com",
        max_steps=5
    )
    
    return result


def test_wikipedia_navigate():
    """Test: Navigate Wikipedia (Step Diff: 1, Adapt: 2)"""
    print("\n" + "=" * 70)
    print("TEST: Wikipedia Navigation (SD:1, AD:2)")
    print("=" * 70)
    
    agent = RealBrowserAgent()
    result = agent.run_task(
        task="Go to Wikipedia, search for 'Python programming language', and click on the first result",
        start_url="https://www.wikipedia.org",
        max_steps=6
    )
    
    return result


def test_form_fill():
    """Test: Fill a form (Step Diff: 3, Adapt: 1)"""
    print("\n" + "=" * 70)
    print("TEST: Form Fill (SD:3, AD:1)")
    print("=" * 70)
    
    # Use a test form website
    agent = RealBrowserAgent()
    result = agent.run_task(
        task="Fill the form with: First Name='John', Last Name='Doe', then click any submit button",
        start_url="https://www.w3schools.com/html/html_forms.asp",
        max_steps=8
    )
    
    return result


def run_all():
    """Run all real execution tests."""
    print("\n" + "=" * 70)
    print("REAL EXECUTION TESTS")
    print("=" * 70)
    
    results = {}
    
    # Test 1: Google Search
    results["google_search"] = test_google_search()
    
    # Test 2: Wikipedia
    results["wikipedia"] = test_wikipedia_navigate()
    
    # Test 3: Form
    results["form_fill"] = test_form_fill()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for name, result in results.items():
        status = "SUCCESS" if result.get("success") else "FAILED"
        steps = result.get("steps", 0)
        actions = len(result.get("actions", []))
        print(f"  {name}: {status} (steps: {steps}, actions: {actions})")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "google":
            test_google_search()
        elif test_name == "wiki":
            test_wikipedia_navigate()
        elif test_name == "form":
            test_form_fill()
        else:
            print(f"Unknown test: {test_name}")
            print("Available: google, wiki, form")
    else:
        run_all()
