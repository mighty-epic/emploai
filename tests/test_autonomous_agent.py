"""
Autonomous Visual Agent
- Model decides when to open browser
- Uses screenshots + vision for verification
- More complex SD5-10, AD1-3 tasks

Run: python tests/test_autonomous_agent.py
"""

from dotenv import load_dotenv
load_dotenv()

import json
import time
import base64
from pathlib import Path
from typing import Dict, List
from openai import OpenAI

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

import mss
import mss.tools


# ============================================================
# TOOLS - Model has full control
# ============================================================

TOOLS = [
    # Browser control
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Open a web browser and navigate to a URL",
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
            "name": "close_browser",
            "description": "Close the browser",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    # Observation
    {
        "type": "function",
        "function": {
            "name": "get_page_elements",
            "description": "Get list of interactive elements on current page",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot and analyze what you see. Use this to verify if actions succeeded.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What to look for in the screenshot"}
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
                    "target": {"type": "string", "description": "Element ID, name, or visible text to click"}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text. If target provided, clicks it first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "target": {"type": "string", "description": "Optional: element to type into"}
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
                    "key": {"type": "string", "enum": ["enter", "tab", "escape", "up", "down", "left", "right", "backspace"]}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the page",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "description": "Pixels to scroll (default 300)"}
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait for specified seconds",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Seconds to wait"}
                },
                "required": ["seconds"]
            }
        }
    },
    # Completion
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Signal that the task is finished",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "summary": {"type": "string", "description": "What was accomplished"}
                },
                "required": ["success", "summary"]
            }
        }
    }
]


# ============================================================
# AUTONOMOUS AGENT
# ============================================================

class AutonomousAgent:
    def __init__(self):
        self.client = OpenAI()
        self.driver = None
        self.screenshot_dir = Path("test_outputs/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    def log(self, category: str, data: any):
        print(f"\n[{category}]")
        if isinstance(data, dict):
            print(json.dumps(data, indent=2, default=str)[:1500])
        else:
            print(str(data)[:1500])
    
    # ==================== TOOL IMPLEMENTATIONS ====================
    
    def open_browser(self, url: str) -> Dict:
        if self.driver:
            self.driver.get(url)
        else:
            options = Options()
            options.add_argument('--log-level=3')
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.get(url)
        time.sleep(2)
        return {"success": True, "url": url, "title": self.driver.title}
    
    def close_browser(self) -> Dict:
        if self.driver:
            self.driver.quit()
            self.driver = None
        return {"success": True}
    
    def get_page_elements(self) -> Dict:
        if not self.driver:
            return {"error": "Browser not open. Call open_browser first."}
        
        elements = []
        for tag in ['input', 'button', 'a', 'textarea', 'select']:
            for el in self.driver.find_elements(By.TAG_NAME, tag):
                try:
                    if not el.is_displayed():
                        continue
                    el_id = el.get_attribute("id") or el.get_attribute("name") or ""
                    text = el.text or el.get_attribute("placeholder") or el.get_attribute("aria-label") or ""
                    if el_id or text:
                        elements.append({"id": el_id, "tag": tag, "text": text[:40]})
                except:
                    continue
        
        return {
            "url": self.driver.current_url,
            "title": self.driver.title,
            "elements": elements[:25]
        }
    
    def take_screenshot(self, question: str = None) -> Dict:
        """Take screenshot and use vision to analyze it."""
        path = str(self.screenshot_dir / f"screen_{int(time.time())}.png")
        
        if self.driver:
            self.driver.save_screenshot(path)
        else:
            with mss.mss() as sct:
                sct.shot(output=path)
        
        # Encode for vision API
        with open(path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
        
        # Ask vision model what it sees
        vision_prompt = question or "Describe what you see on this screen."
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                    ]
                }
            ],
            max_tokens=300
        )
        
        analysis = response.choices[0].message.content
        return {"success": True, "screenshot": path, "analysis": analysis}
    
    def find_element(self, target: str):
        """Find element by ID, name, or text."""
        if not self.driver:
            return None
        
        # Try ID
        try:
            return self.driver.find_element(By.ID, target)
        except: pass
        
        # Try name
        try:
            return self.driver.find_element(By.NAME, target)
        except: pass
        
        # Try link text
        try:
            return self.driver.find_element(By.LINK_TEXT, target)
        except: pass
        
        # Try partial link text
        try:
            return self.driver.find_element(By.PARTIAL_LINK_TEXT, target)
        except: pass
        
        # Try XPath with text
        try:
            return self.driver.find_element(By.XPATH, f"//*[contains(text(), '{target}')]")
        except: pass
        
        # Try button with text
        try:
            return self.driver.find_element(By.XPATH, f"//button[contains(., '{target}')]")
        except: pass
        
        # Try input with placeholder
        try:
            return self.driver.find_element(By.XPATH, f"//input[@placeholder='{target}']")
        except: pass
        
        return None
    
    def click(self, target: str) -> Dict:
        if not self.driver:
            return {"success": False, "error": "Browser not open"}
        
        el = self.find_element(target)
        if el:
            el.click()
            time.sleep(0.5)
            return {"success": True, "clicked": target}
        return {"success": False, "error": f"Element '{target}' not found"}
    
    def type_text(self, text: str, target: str = None) -> Dict:
        if not self.driver:
            return {"success": False, "error": "Browser not open"}
        
        if target:
            el = self.find_element(target)
            if el:
                el.click()
                el.send_keys(text)
                return {"success": True, "typed": text, "into": target}
            return {"success": False, "error": f"Could not find '{target}'"}
        else:
            self.driver.switch_to.active_element.send_keys(text)
            return {"success": True, "typed": text}
    
    def press_key(self, key: str) -> Dict:
        if not self.driver:
            return {"success": False, "error": "Browser not open"}
        
        key_map = {
            "enter": Keys.ENTER, "tab": Keys.TAB, "escape": Keys.ESCAPE,
            "up": Keys.UP, "down": Keys.DOWN, "left": Keys.LEFT, "right": Keys.RIGHT,
            "backspace": Keys.BACKSPACE
        }
        self.driver.switch_to.active_element.send_keys(key_map[key])
        time.sleep(0.3)
        return {"success": True, "pressed": key}
    
    def scroll(self, direction: str, amount: int = 300) -> Dict:
        if not self.driver:
            return {"success": False, "error": "Browser not open"}
        
        amt = amount if direction == "down" else -amount
        self.driver.execute_script(f"window.scrollBy(0, {amt})")
        return {"success": True, "scrolled": direction, "pixels": amount}
    
    def wait(self, seconds: float) -> Dict:
        time.sleep(seconds)
        return {"success": True, "waited": seconds}
    
    # ==================== EXECUTE TOOL ====================
    
    def execute(self, tool_name: str, args: Dict) -> Dict:
        self.log("EXECUTE", {"tool": tool_name, "args": args})
        
        if tool_name == "open_browser":
            result = self.open_browser(args["url"])
        elif tool_name == "close_browser":
            result = self.close_browser()
        elif tool_name == "get_page_elements":
            result = self.get_page_elements()
        elif tool_name == "take_screenshot":
            result = self.take_screenshot(args.get("question"))
        elif tool_name == "click":
            result = self.click(args["target"])
        elif tool_name == "type_text":
            result = self.type_text(args["text"], args.get("target"))
        elif tool_name == "press_key":
            result = self.press_key(args["key"])
        elif tool_name == "scroll":
            result = self.scroll(args["direction"], args.get("amount", 300))
        elif tool_name == "wait":
            result = self.wait(args["seconds"])
        elif tool_name == "task_complete":
            result = {"task_done": True, "success": args["success"], "summary": args["summary"]}
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        
        self.log("RESULT", result)
        return result
    
    # ==================== RUN TASK ====================
    
    def run(self, task: str, max_steps: int = 20):
        print(f"\n{'#'*70}")
        print(f"# AUTONOMOUS AGENT")
        print(f"# Task: {task[:60]}...")
        print(f"{'#'*70}")
        
        system_prompt = """You are an AI agent that can control a computer.

Available tools: open_browser, close_browser, get_page_elements, take_screenshot, click, type_text, press_key, scroll, wait, task_complete.

Behaviors:
- Open browser when needed, you decide the URLs
- Take screenshots to verify important steps worked
- When done, call task_complete with what you accomplished
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task}
        ]
        
        for step in range(max_steps):
            print(f"\n{'='*50}")
            print(f"STEP {step + 1}")
            print('='*50)
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            
            if msg.content:
                self.log("THINKING", msg.content)
            
            if not msg.tool_calls:
                print("[No tool calls]")
                break
            
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                result = self.execute(tc.function.name, args)
                
                messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
                
                if result.get("task_done"):
                    print(f"\n{'#'*70}")
                    print(f"# TASK COMPLETE: {'SUCCESS' if result['success'] else 'FAILED'}")
                    print(f"# {result.get('summary', '')}")
                    print(f"{'#'*70}")
                    if self.driver:
                        time.sleep(2)
                        self.driver.quit()
                    return result["success"]
        
        print("\n[MAX STEPS REACHED]")
        if self.driver:
            self.driver.quit()
        return False


# ============================================================
# TEST SCENARIOS - High SD (5-10), AD (1-3)
# ============================================================

TASKS = {
    # SD5 AD1 - Form task
    "sd5_ad1": {
        "name": "SD5 AD1: Fill a Form",
        "task": "Fill out a web form with some test data and submit it",
        "sd": 5, "ad": 1
    },
    
    # SD6 AD1 - Research task
    "sd6_ad1": {
        "name": "SD6 AD1: Research Python",
        "task": "Research when Python was created and who made it",
        "sd": 6, "ad": 1
    },
    
    # SD7 AD2 - Explore task
    "sd7_ad2": {
        "name": "SD7 AD2: Find Python Project",
        "task": "Browse GitHub and find an interesting Python project",
        "sd": 7, "ad": 2
    },
    
    # SD8 AD2 - Comparison task
    "sd8_ad2": {
        "name": "SD8 AD2: Compare Languages",
        "task": "Search for popular programming languages and compare Python vs JavaScript",
        "sd": 8, "ad": 2
    },
    
    # SD10 AD3 - Research across sites
    "sd10_ad3": {
        "name": "SD10 AD3: Research Selenium",
        "task": "Research what Selenium is used for and how popular it is",
        "sd": 10, "ad": 3
    },
}


def run_test(key: str):
    if key not in TASKS:
        print(f"Unknown: {key}")
        print(f"Available: {list(TASKS.keys())}")
        return
    
    t = TASKS[key]
    print(f"\n{'#'*70}")
    print(f"# TEST: {t['name']}")
    print(f"# SD: {t['sd']} | AD: {t['ad']}")
    print(f"{'#'*70}")
    
    agent = AutonomousAgent()
    return agent.run(t["task"], max_steps=25)


def run_all():
    results = {}
    for key in TASKS:
        results[key] = run_test(key)
        time.sleep(3)
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for key, success in results.items():
        t = TASKS[key]
        status = "PASS" if success else "FAIL"
        print(f"  {t['name']}: {status}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "all":
            run_all()
        else:
            run_test(sys.argv[1])
    else:
        print("Available tests:")
        for k, v in TASKS.items():
            print(f"  {k}: {v['name']} (SD:{v['sd']}, AD:{v['ad']})")
        print("\nRun: python tests/test_autonomous_agent.py <test_name>")
