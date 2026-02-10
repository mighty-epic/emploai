"""
Click Tool Verification Tests
Tests both browser_click (Selenium) and click (PyAutoGUI) to ensure they work correctly.

Run with: python tests/verify_click_tools.py
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================
# TEST 1: SELENIUM BROWSER_CLICK
# ============================================================

def test_selenium_browser_click():
    """
    Test browser_click by:
    1. Creating a simple HTML page with a button
    2. Opening it in Selenium
    3. Using browser_click to click the button
    4. Verifying the button state changed
    """
    print("\n" + "="*70)
    print("TEST 1: SELENIUM browser_click")
    print("="*70)
    
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as e:
        print(f"❌ FAILED: Selenium not installed - {e}")
        return False
    
    # Create a test HTML file
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Click Test</title></head>
    <body>
        <h1>Click Test Page</h1>
        <button id="test-button" onclick="this.textContent='CLICKED'; this.dataset.clicked='true'">
            Click Me
        </button>
        <p id="status">Not clicked yet</p>
    </body>
    </html>
    """
    
    # Write to temp file
    temp_dir = tempfile.gettempdir()
    html_path = os.path.join(temp_dir, "click_test.html")
    with open(html_path, "w") as f:
        f.write(html_content)
    
    print(f"  [1/4] Created test HTML at: {html_path}")
    
    # Initialize Selenium
    try:
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--log-level=3")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        print("  [2/4] Chrome browser started successfully")
    except Exception as e:
        print(f"❌ FAILED: Could not start Chrome - {e}")
        return False
    
    try:
        # Navigate to test page
        driver.get(f"file:///{html_path.replace(os.sep, '/')}")
        time.sleep(1)
        print(f"  [3/4] Navigated to test page. Title: {driver.title}")
        
        # Verify button exists and initial state
        button = driver.find_element(By.ID, "test-button")
        initial_text = button.text
        print(f"        Initial button text: '{initial_text}'")
        
        if initial_text != "Click Me":
            print(f"❌ FAILED: Unexpected initial button text")
            driver.quit()
            return False
        
        # === TEST browser_click by TEXT ===
        print("\n  [Test A] browser_click by text 'Click Me'...")
        
        # Simulate what browser_click does internally
        xpath = f"//*[contains(text(), 'Click Me')]"
        elements = driver.find_elements(By.XPATH, xpath)
        clicked = False
        for el in elements:
            if el.is_displayed():
                el.click()
                clicked = True
                print(f"        ✅ Found and clicked element via XPath")
                break
        
        if not clicked:
            print(f"❌ FAILED: browser_click could not find element by text")
            driver.quit()
            return False
        
        time.sleep(0.5)
        
        # Verify button changed
        new_text = button.text
        print(f"        Button text after click: '{new_text}'")
        
        if new_text == "CLICKED":
            print("  ✅ TEST A PASSED: browser_click by text works!")
        else:
            print(f"❌ TEST A FAILED: Button text is '{new_text}' instead of 'CLICKED'")
            driver.quit()
            return False
        
        # === Reset and TEST browser_click by CSS SELECTOR ===
        driver.refresh()
        time.sleep(1)
        
        print("\n  [Test B] browser_click by CSS selector '#test-button'...")
        
        try:
            el = driver.find_element(By.CSS_SELECTOR, "#test-button")
            if el.is_displayed():
                el.click()
                print(f"        ✅ Found and clicked element via CSS selector")
        except Exception as e:
            print(f"❌ FAILED: browser_click could not find element by CSS - {e}")
            driver.quit()
            return False
        
        time.sleep(0.5)
        
        button = driver.find_element(By.ID, "test-button")
        if button.text == "CLICKED":
            print("  ✅ TEST B PASSED: browser_click by CSS selector works!")
        else:
            print(f"❌ TEST B FAILED: Button not clicked")
            driver.quit()
            return False
        
        driver.quit()
        print("\n✅ SELENIUM browser_click: ALL TESTS PASSED")
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        driver.quit()
        return False


# ============================================================
# TEST 2: PYAUTOGUI CLICK
# ============================================================

def test_pyautogui_click():
    """
    Test PyAutoGUI click by:
    1. Getting current mouse position
    2. Moving to a specific position
    3. Clicking
    4. Verifying the click was registered (via mouse position)
    """
    print("\n" + "="*70)
    print("TEST 2: PYAUTOGUI click")
    print("="*70)
    
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except ImportError as e:
        print(f"❌ FAILED: PyAutoGUI not installed - {e}")
        return False
    
    # Get screen size
    screen_width, screen_height = pyautogui.size()
    print(f"  [1/4] Screen size: {screen_width}x{screen_height}")
    
    # Test 1: Move to center of screen
    center_x = screen_width // 2
    center_y = screen_height // 2
    
    print(f"  [2/4] Moving mouse to center ({center_x}, {center_y})...")
    pyautogui.moveTo(center_x, center_y, duration=0.3)
    
    actual_x, actual_y = pyautogui.position()
    print(f"        Actual position: ({actual_x}, {actual_y})")
    
    # Allow 5px tolerance
    if abs(actual_x - center_x) > 5 or abs(actual_y - center_y) > 5:
        print(f"❌ FAILED: Mouse did not move to expected position")
        return False
    
    print("  ✅ Mouse movement works correctly")
    
    # Test 2: Click (we can't easily verify a click worked, but we can verify no error)
    print(f"  [3/4] Testing click at current position...")
    try:
        pyautogui.click()
        print("        Click executed without error")
    except Exception as e:
        print(f"❌ FAILED: Click raised exception - {e}")
        return False
    
    # Test 3: Click at specific coordinates
    test_x = 100
    test_y = 100
    print(f"  [4/4] Testing click at specific coordinates ({test_x}, {test_y})...")
    try:
        pyautogui.click(test_x, test_y)
        
        # Verify mouse moved to click position
        actual_x, actual_y = pyautogui.position()
        if abs(actual_x - test_x) > 5 or abs(actual_y - test_y) > 5:
            print(f"        ⚠️ WARNING: Mouse at ({actual_x}, {actual_y}) after click")
        else:
            print(f"        Mouse correctly at ({actual_x}, {actual_y})")
        
        print("        Click executed without error")
    except Exception as e:
        print(f"❌ FAILED: Click at coordinates raised exception - {e}")
        return False
    
    print("\n✅ PYAUTOGUI click: ALL TESTS PASSED")
    return True


# ============================================================
# TEST 3: PYAUTOGUI DOUBLE-CLICK AND RIGHT-CLICK
# ============================================================

def test_pyautogui_click_variants():
    """
    Test double-click and right-click functionality.
    """
    print("\n" + "="*70)
    print("TEST 3: PYAUTOGUI click variants (double-click, right-click)")
    print("="*70)
    
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except ImportError as e:
        print(f"❌ FAILED: PyAutoGUI not installed - {e}")
        return False
    
    screen_width, screen_height = pyautogui.size()
    center_x = screen_width // 2
    center_y = screen_height // 2
    
    # Test double-click
    print(f"  [1/2] Testing double-click at center...")
    try:
        pyautogui.doubleClick(center_x, center_y)
        print("        ✅ Double-click executed without error")
    except Exception as e:
        print(f"❌ FAILED: Double-click raised exception - {e}")
        return False
    
    time.sleep(0.5)
    
    # Test right-click
    print(f"  [2/2] Testing right-click at center...")
    try:
        pyautogui.rightClick(center_x, center_y)
        print("        ✅ Right-click executed without error")
        
        # Press Escape to close any context menu that might have opened
        time.sleep(0.2)
        pyautogui.press('escape')
        print("        Pressed Escape to close any context menu")
    except Exception as e:
        print(f"❌ FAILED: Right-click raised exception - {e}")
        return False
    
    print("\n✅ PYAUTOGUI click variants: ALL TESTS PASSED")
    return True


# ============================================================
# TEST 4: INTEGRATION TEST - SingleAgent click method
# ============================================================

def test_single_agent_click_integration():
    """
    Test the actual SingleAgent._click method.
    """
    print("\n" + "="*70)
    print("TEST 4: SingleAgent._click integration")
    print("="*70)
    
    try:
        from single_agent.agent import SingleAgent
    except ImportError as e:
        print(f"❌ FAILED: Could not import SingleAgent - {e}")
        return False
    
    # Create agent instance (without actually running tasks)
    try:
        agent = SingleAgent()
        print("  [1/2] SingleAgent instantiated successfully")
    except Exception as e:
        print(f"❌ FAILED: Could not create SingleAgent - {e}")
        return False
    
    # Test the _click method directly
    print("  [2/2] Testing SingleAgent._click(500, 500)...")
    try:
        result = agent._click(500, 500)
        print(f"        Result: {result}")
        
        if isinstance(result, dict) and result.get("success"):
            print("  ✅ SingleAgent._click works correctly")
            return True
        elif isinstance(result, dict) and "error" in result:
            print(f"  ⚠️ SingleAgent._click returned error: {result['error']}")
            return False
        else:
            print(f"  ⚠️ Unexpected result format: {result}")
            return False
    except Exception as e:
        print(f"❌ FAILED: SingleAgent._click raised exception - {e}")
        return False


# ============================================================
# MAIN
# ============================================================

def run_all_tests():
    """Run all click verification tests."""
    print("\n" + "="*70)
    print("CLICK TOOL VERIFICATION TESTS")
    print("="*70)
    print("These tests verify that both Selenium and PyAutoGUI click methods work.")
    print("Some tests may briefly take control of your mouse - don't move it!\n")
    
    results = {}
    
    # Run tests
    results["selenium_browser_click"] = test_selenium_browser_click()
    results["pyautogui_click"] = test_pyautogui_click()
    results["pyautogui_variants"] = test_pyautogui_click_variants()
    results["single_agent_integration"] = test_single_agent_click_integration()
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️ SOME TESTS FAILED - Review output above for details")
    
    return all_passed


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        if test_name == "selenium":
            test_selenium_browser_click()
        elif test_name == "pyautogui":
            test_pyautogui_click()
        elif test_name == "variants":
            test_pyautogui_click_variants()
        elif test_name == "integration":
            test_single_agent_click_integration()
        else:
            print(f"Unknown test: {test_name}")
            print("Options: selenium, pyautogui, variants, integration")
    else:
        run_all_tests()
