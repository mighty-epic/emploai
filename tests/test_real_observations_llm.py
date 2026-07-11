"""
Real LLM + Real Observations Test
Uses actual Selenium, pywinauto, and Tesseract observations with real LLM.
"""

from dotenv import load_dotenv
load_dotenv()

import json
import time
import os
from typing import Dict, List, Any
from openai import OpenAI
import pytest


pytestmark = pytest.mark.live_external


# ============================================================
# TOOLS DEFINITION
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click an element by ID or text",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string", "description": "ID of element to click"},
                    "text": {"type": "string", "description": "Text of element to click (if no ID)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently focused element",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_respond",
            "description": "Provide analysis of what you see and recommend next action",
            "parameters": {
                "type": "object",
                "properties": {
                    "observation_summary": {"type": "string", "description": "Summary of what you see"},
                    "recommended_action": {"type": "string", "description": "What action to take next"},
                    "confidence": {"type": "number", "description": "Confidence 0-1"}
                },
                "required": ["observation_summary", "recommended_action"]
            }
        }
    }
]


# ============================================================
# REAL OBSERVATION FUNCTIONS
# ============================================================

def get_real_selenium_observation() -> Dict:
    """Get REAL browser observation using Selenium."""
    print("\n[SELENIUM] Getting real browser observation...")
    
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    
    options = Options()
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--log-level=3')  # Suppress logs
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Navigate to a simple page
    driver.get("https://www.google.com")
    time.sleep(2)
    
    # Extract real elements
    elements = []
    for tag in ['input', 'button', 'a', 'textarea']:
        for el in driver.find_elements("tag name", tag):
            try:
                if not el.is_displayed():
                    continue
                rect = el.rect
                elements.append({
                    "id": el.get_attribute("id") or el.get_attribute("name") or f"_{tag}_{len(elements)}",
                    "type": tag,
                    "text": (el.text or el.get_attribute("placeholder") or 
                            el.get_attribute("aria-label") or el.get_attribute("value") or ""),
                    "x": int(rect["x"]),
                    "y": int(rect["y"]),
                    "width": int(rect["width"]),
                    "height": int(rect["height"])
                })
            except:
                continue
    
    observation = {
        "source": "selenium",
        "url": driver.current_url,
        "title": driver.title,
        "element_count": len(elements),
        "elements": elements[:15]  # Limit to first 15 for context
    }
    
    driver.quit()
    
    print(f"  URL: {observation['url']}")
    print(f"  Elements found: {len(elements)}")
    
    return observation


def get_real_pywinauto_observation() -> Dict:
    """Get REAL desktop observation using pywinauto."""
    print("\n[PYWINAUTO] Getting real desktop observation...")
    
    from pywinauto import Desktop
    
    desktop = Desktop(backend="uia")
    windows = desktop.windows()
    
    if not windows:
        return {"source": "pywinauto", "error": "No windows found", "elements": []}
    
    # Get the first visible window
    active = None
    for w in windows:
        try:
            if w.is_visible() and w.element_info.name:
                active = w
                break
        except:
            continue
    
    if not active:
        return {"source": "pywinauto", "error": "No active window", "elements": []}
    
    elements = []
    try:
        for child in active.descendants()[:50]:
            try:
                rect = child.rectangle()
                name = child.element_info.name or ""
                ctrl_type = child.element_info.control_type
                
                if not name and ctrl_type not in ["Edit", "Button", "CheckBox"]:
                    continue
                    
                elements.append({
                    "id": child.element_info.automation_id or f"ctrl_{len(elements)}",
                    "type": ctrl_type,
                    "text": name[:50],
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.width(),
                    "height": rect.height()
                })
            except:
                continue
    except:
        pass
    
    observation = {
        "source": "pywinauto",
        "window_title": active.element_info.name,
        "element_count": len(elements),
        "elements": elements[:15]
    }
    
    print(f"  Window: {observation['window_title']}")
    print(f"  Elements found: {len(elements)}")
    
    return observation


def get_real_tesseract_observation() -> Dict:
    """Get REAL screenshot observation using Tesseract OCR."""
    print("\n[TESSERACT] Getting real screen observation...")
    
    import pytesseract
    from PIL import Image
    import mss
    import mss.tools
    
    # Capture real screenshot
    with mss.MSS() as sct:
        screenshot = sct.grab(sct.monitors[1])
        img_path = "temp_ocr_screenshot.png"
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=img_path)
    
    # Real OCR
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
                "text": text[:30],
                "x": data['left'][i],
                "y": data['top'][i],
                "width": data['width'][i],
                "height": data['height'][i],
                "confidence": round(conf, 1)
            })
    
    os.remove(img_path)
    
    observation = {
        "source": "tesseract",
        "screen_size": f"{screenshot.width}x{screenshot.height}",
        "element_count": len(elements),
        "elements": elements[:20]
    }
    
    print(f"  Screen: {observation['screen_size']}")
    print(f"  Text elements found: {len(elements)}")
    
    return observation


# ============================================================
# LLM REASONING TEST
# ============================================================

def run_llm_with_real_observation(observation: Dict, task: str) -> Dict:
    """Send real observation to LLM and get reasoning."""
    
    print(f"\n[LLM] Sending to GPT-4o-mini...")
    print(f"  Task: {task}")
    
    client = OpenAI()
    
    system_prompt = """You are an AI agent observing a computer screen.
Analyze the provided screen state and recommend actions to complete the task.
Use the analyze_and_respond tool to provide your analysis.
Be specific about which elements you would interact with."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"""Screen observation ({observation['source']}):
{json.dumps(observation, indent=2)}

Task: {task}

Analyze what you see and recommend the next action."""}
    ]
    
    start = time.time()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    duration = time.time() - start
    
    msg = response.choices[0].message
    result = {
        "duration_seconds": round(duration, 2),
        "reasoning": msg.content,
        "tool_calls": []
    }
    
    if msg.tool_calls:
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            result["tool_calls"].append({
                "name": tc.function.name,
                "args": args
            })
    
    return result


# ============================================================
# MAIN TESTS
# ============================================================

def test_selenium_with_llm():
    """TEST 1: Real Selenium + Real LLM"""
    print("\n" + "=" * 70)
    print("TEST 1: SELENIUM (Real Browser) + Real LLM")
    print("=" * 70)
    
    observation = get_real_selenium_observation()
    task = "Find the search box on the page and describe how you would enter a search query"
    
    result = run_llm_with_real_observation(observation, task)
    
    print(f"\n[RESULT]")
    print(f"  LLM Response Time: {result['duration_seconds']}s")
    
    if result["tool_calls"]:
        for tc in result["tool_calls"]:
            print(f"\n  Tool: {tc['name']}")
            for k, v in tc['args'].items():
                v_str = str(v)[:100]
                print(f"    {k}: {v_str}")
    
    return result


def test_pywinauto_with_llm():
    """TEST 2: Real pywinauto + Real LLM"""
    print("\n" + "=" * 70)
    print("TEST 2: PYWINAUTO (Real Desktop) + Real LLM")
    print("=" * 70)
    
    observation = get_real_pywinauto_observation()
    task = "Analyze the current window and describe what application is open and its main UI elements"
    
    result = run_llm_with_real_observation(observation, task)
    
    print(f"\n[RESULT]")
    print(f"  LLM Response Time: {result['duration_seconds']}s")
    
    if result["tool_calls"]:
        for tc in result["tool_calls"]:
            print(f"\n  Tool: {tc['name']}")
            for k, v in tc['args'].items():
                v_str = str(v)[:100]
                print(f"    {k}: {v_str}")
    
    return result


def test_tesseract_with_llm():
    """TEST 3: Real Tesseract + Real LLM"""
    print("\n" + "=" * 70)
    print("TEST 3: TESSERACT (Real OCR) + Real LLM")
    print("=" * 70)
    
    observation = get_real_tesseract_observation()
    task = "Read the visible text on screen and describe what you see"
    
    result = run_llm_with_real_observation(observation, task)
    
    print(f"\n[RESULT]")
    print(f"  LLM Response Time: {result['duration_seconds']}s")
    
    if result["tool_calls"]:
        for tc in result["tool_calls"]:
            print(f"\n  Tool: {tc['name']}")
            for k, v in tc['args'].items():
                v_str = str(v)[:100]
                print(f"    {k}: {v_str}")
    
    return result


def test_all_combined_with_llm():
    """TEST 4: All 3 observers + Real LLM"""
    print("\n" + "=" * 70)
    print("TEST 4: ALL COMBINED (Selenium + pywinauto + Tesseract) + Real LLM")
    print("=" * 70)
    
    # Get all observations
    selenium_obs = get_real_selenium_observation()
    pywinauto_obs = get_real_pywinauto_observation()
    tesseract_obs = get_real_tesseract_observation()
    
    combined = {
        "source": "combined",
        "observations": {
            "browser": selenium_obs,
            "desktop": pywinauto_obs,
            "screen_ocr": tesseract_obs
        }
    }
    
    task = "Using all available observation methods, provide a comprehensive analysis of what is currently on screen"
    
    result = run_llm_with_real_observation(combined, task)
    
    print(f"\n[RESULT]")
    print(f"  LLM Response Time: {result['duration_seconds']}s")
    
    if result["tool_calls"]:
        for tc in result["tool_calls"]:
            print(f"\n  Tool: {tc['name']}")
            for k, v in tc['args'].items():
                v_str = str(v)[:150]
                print(f"    {k}: {v_str}")
    
    return result


def run_single_test(test_name: str):
    """Run a single test by name."""
    if test_name == "selenium":
        return test_selenium_with_llm()
    elif test_name == "pywinauto":
        return test_pywinauto_with_llm()
    elif test_name == "tesseract":
        return test_tesseract_with_llm()
    elif test_name == "combined":
        return test_all_combined_with_llm()
    else:
        print(f"Unknown test: {test_name}")
        return None


def run_all_tests():
    """Run all 4 tests."""
    print("\n" + "=" * 70)
    print("REAL OBSERVATION + REAL LLM TESTS")
    print("=" * 70)
    
    results = {}
    
    # Test 1: Selenium
    results["selenium"] = test_selenium_with_llm()
    
    # Test 2: pywinauto
    results["pywinauto"] = test_pywinauto_with_llm()
    
    # Test 3: Tesseract
    results["tesseract"] = test_tesseract_with_llm()
    
    # Test 4: Combined
    results["combined"] = test_all_combined_with_llm()
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for name, result in results.items():
        tc_count = len(result.get("tool_calls", []))
        duration = result.get("duration_seconds", 0)
        print(f"  {name}: {tc_count} tool calls, {duration}s")
    
    print("\nAll tests completed!")
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        run_single_test(test_name)
    else:
        run_all_tests()
