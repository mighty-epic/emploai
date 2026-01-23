"""
LIVE TEST: Selenium Observer
Tests extracting information from a currently open browser.

Run with: python -m observation_testing.tests.test_selenium_live
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from observation_testing.structured.selenium_observer import SeleniumObserver


def setup_driver(headless: bool = False) -> webdriver.Chrome:
    """Create and configure Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def test_navigate_and_observe(url: str = "https://www.google.com"):
    """
    Test 1: Navigate to a page and extract all observable elements.
    """
    print("=" * 60)
    print("TEST 1: Navigate and Observe")
    print("=" * 60)
    
    driver = setup_driver()
    observer = SeleniumObserver(driver)
    
    try:
        print(f"\n[1] Navigating to: {url}")
        driver.get(url)
        time.sleep(2)  # Wait for page load
        
        print(f"\n[2] Getting observation snapshot...")
        snapshot = observer.get_observation_snapshot()
        
        print(f"\n[3] Results:")
        print(f"    URL: {snapshot['url']}")
        print(f"    Title: {snapshot['title']}")
        print(f"    Elements found: {len(snapshot['elements'])}")
        
        # Show element breakdown by role
        roles = {}
        for el in snapshot['elements']:
            role = el.get('role', 'unknown')
            roles[role] = roles.get(role, 0) + 1
        
        print(f"\n[4] Element breakdown by role:")
        for role, count in sorted(roles.items(), key=lambda x: -x[1]):
            print(f"    {role}: {count}")
        
        # Show first 5 interactive elements
        print(f"\n[5] First 5 elements:")
        for el in snapshot['elements'][:5]:
            text = el.get('text', '')[:30] or el.get('placeholder', '')[:30] or el.get('aria_label', '')[:30] or '(no text)'
            print(f"    [{el['role']}] {text}")
        
        # Check focused element
        focused = snapshot.get('focused_element')
        if focused:
            print(f"\n[6] Focused element: [{focused['role']}] {focused.get('text', '')[:30]}")
        else:
            print(f"\n[6] No element currently focused")
        
        print("\n✅ TEST 1 PASSED")
        return snapshot
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        raise
    finally:
        driver.quit()


def test_multiple_pages():
    """
    Test 2: Navigate through multiple pages and track changes.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Multiple Page Navigation")
    print("=" * 60)
    
    driver = setup_driver()
    observer = SeleniumObserver(driver)
    
    pages = [
        "https://www.google.com",
        "https://www.wikipedia.org",
        "https://www.github.com"
    ]
    
    results = []
    
    try:
        for url in pages:
            print(f"\n[→] Navigating to: {url}")
            driver.get(url)
            time.sleep(2)
            
            snapshot = observer.get_observation_snapshot()
            results.append({
                "url": snapshot['url'],
                "title": snapshot['title'],
                "element_count": len(snapshot['elements'])
            })
            print(f"    Title: {snapshot['title']}")
            print(f"    Elements: {len(snapshot['elements'])}")
        
        print(f"\n[Summary]")
        for r in results:
            print(f"    {r['title'][:30]}: {r['element_count']} elements")
        
        print("\n✅ TEST 2 PASSED")
        return results
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        raise
    finally:
        driver.quit()


def test_interactive_elements():
    """
    Test 3: Find and analyze interactive elements on a form page.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Interactive Elements Analysis")
    print("=" * 60)
    
    driver = setup_driver()
    observer = SeleniumObserver(driver)
    
    # Use a page with many interactive elements
    url = "https://www.google.com/search?q=test"
    
    try:
        print(f"\n[1] Navigating to: {url}")
        driver.get(url)
        time.sleep(2)
        
        snapshot = observer.get_observation_snapshot()
        
        # Find specific element types
        textboxes = [el for el in snapshot['elements'] if el['role'] == 'textbox']
        buttons = [el for el in snapshot['elements'] if el['role'] == 'button']
        links = [el for el in snapshot['elements'] if el['role'] == 'link']
        
        print(f"\n[2] Interactive element counts:")
        print(f"    Textboxes: {len(textboxes)}")
        print(f"    Buttons: {len(buttons)}")
        print(f"    Links: {len(links)}")
        
        # Show elements with bounding boxes
        print(f"\n[3] Elements with bounding boxes:")
        for el in snapshot['elements'][:10]:
            bbox = el.get('bbox', {})
            if bbox.get('width', 0) > 0:
                print(f"    [{el['role']}] x:{bbox['x']:.0f}, y:{bbox['y']:.0f}, w:{bbox['width']:.0f}, h:{bbox['height']:.0f}")
        
        print("\n✅ TEST 3 PASSED")
        return snapshot
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        raise
    finally:
        driver.quit()


def test_screenshot_capture():
    """
    Test 4: Capture screenshot alongside observation.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Screenshot Capture")
    print("=" * 60)
    
    driver = setup_driver()
    observer = SeleniumObserver(driver)
    
    try:
        print(f"\n[1] Navigating to Google...")
        driver.get("https://www.google.com")
        time.sleep(2)
        
        print(f"\n[2] Capturing screenshot...")
        screenshot_bytes = observer.capture_screenshot()
        
        # Save screenshot
        screenshot_path = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "test_outputs",
            "selenium_screenshot.png"
        )
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        
        with open(screenshot_path, 'wb') as f:
            f.write(screenshot_bytes)
        
        print(f"    Screenshot saved: {screenshot_path}")
        print(f"    Size: {len(screenshot_bytes)} bytes")
        
        print("\n✅ TEST 4 PASSED")
        return screenshot_path
        
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        raise
    finally:
        driver.quit()


def run_all_tests():
    """Run all Selenium observer tests."""
    print("\n" + "=" * 60)
    print("SELENIUM OBSERVER LIVE TESTS")
    print("=" * 60)
    
    tests = [
        ("Navigate and Observe", test_navigate_and_observe),
        ("Multiple Pages", test_multiple_pages),
        ("Interactive Elements", test_interactive_elements),
        ("Screenshot Capture", test_screenshot_capture),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, "PASSED"))
        except Exception as e:
            results.append((name, f"FAILED: {e}"))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, status in results:
        icon = "✅" if status == "PASSED" else "❌"
        print(f"{icon} {name}: {status}")


if __name__ == "__main__":
    run_all_tests()
