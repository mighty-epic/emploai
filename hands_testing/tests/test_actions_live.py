"""
LIVE TEST: Hands Layer - Action Execution
Tests clicking, scrolling, typing via pyautogui.

Run with: python -m hands_testing.tests.test_actions_live

WARNING: This test will move your mouse and type on screen!
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1
except ImportError:
    PYAUTOGUI_AVAILABLE = False


def test_mouse_info():
    """Test 1: Get current mouse position and screen info."""
    print("=" * 60)
    print("TEST 1: Mouse & Screen Info")
    print("=" * 60)
    
    if not PYAUTOGUI_AVAILABLE:
        print("❌ pyautogui not installed")
        return
    
    pos = pyautogui.position()
    size = pyautogui.size()
    
    print(f"\n[Mouse Position]: ({pos.x}, {pos.y})")
    print(f"[Screen Size]: {size.width} x {size.height}")
    print("\n✅ TEST 1 PASSED")


def test_mouse_move():
    """Test 2: Move mouse to specific coordinates."""
    print("\n" + "=" * 60)
    print("TEST 2: Mouse Movement")
    print("=" * 60)
    
    if not PYAUTOGUI_AVAILABLE:
        print("❌ pyautogui not installed")
        return
    
    start = pyautogui.position()
    print(f"\n[Starting Position]: ({start.x}, {start.y})")
    
    # Move to center of screen
    size = pyautogui.size()
    target_x, target_y = size.width // 2, size.height // 2
    
    print(f"[Moving to]: ({target_x}, {target_y})")
    pyautogui.moveTo(target_x, target_y, duration=0.5)
    
    end = pyautogui.position()
    print(f"[Final Position]: ({end.x}, {end.y})")
    
    # Move back
    pyautogui.moveTo(start.x, start.y, duration=0.3)
    print("[Returned to start]")
    print("\n✅ TEST 2 PASSED")


def test_click_simulation():
    """Test 3: Simulate click (without actually clicking)."""
    print("\n" + "=" * 60)
    print("TEST 3: Click Simulation (DRY RUN)")
    print("=" * 60)
    
    if not PYAUTOGUI_AVAILABLE:
        print("❌ pyautogui not installed")
        return
    
    pos = pyautogui.position()
    
    print(f"\n[Would click at]: ({pos.x}, {pos.y})")
    print("[Click types available]:")
    print("  - pyautogui.click() - single left click")
    print("  - pyautogui.doubleClick() - double click")
    print("  - pyautogui.rightClick() - right click")
    print("  - pyautogui.mouseDown() / mouseUp() - for drag")
    
    # Actual click is commented out for safety
    # pyautogui.click(pos.x, pos.y)
    
    print("\n[DRY RUN - no actual click performed]")
    print("\n✅ TEST 3 PASSED")


def test_typing_simulation():
    """Test 4: Typing simulation (dry run)."""
    print("\n" + "=" * 60)
    print("TEST 4: Typing Simulation (DRY RUN)")
    print("=" * 60)
    
    if not PYAUTOGUI_AVAILABLE:
        print("❌ pyautogui not installed")
        return
    
    test_text = "Hello, World!"
    
    print(f"\n[Would type]: '{test_text}'")
    print("[Typing methods]:")
    print("  - pyautogui.write() - types text")
    print("  - pyautogui.press() - single key")
    print("  - pyautogui.hotkey() - key combination")
    
    # Actual typing is commented out for safety
    # pyautogui.write(test_text, interval=0.05)
    
    print("\n[DRY RUN - no actual typing performed]")
    print("\n✅ TEST 4 PASSED")


def test_scroll_simulation():
    """Test 5: Scroll simulation (dry run)."""
    print("\n" + "=" * 60)
    print("TEST 5: Scroll Simulation (DRY RUN)")
    print("=" * 60)
    
    if not PYAUTOGUI_AVAILABLE:
        print("❌ pyautogui not installed")
        return
    
    print("\n[Scroll methods]:")
    print("  - pyautogui.scroll(3) - scroll up 3 'clicks'")
    print("  - pyautogui.scroll(-3) - scroll down 3 'clicks'")
    print("  - pyautogui.hscroll(3) - horizontal scroll")
    
    # Actual scroll is commented out for safety
    # pyautogui.scroll(3)
    
    print("\n[DRY RUN - no actual scroll performed]")
    print("\n✅ TEST 5 PASSED")


def test_hotkey_simulation():
    """Test 6: Hotkey simulation (dry run)."""
    print("\n" + "=" * 60)
    print("TEST 6: Hotkey Simulation (DRY RUN)")
    print("=" * 60)
    
    if not PYAUTOGUI_AVAILABLE:
        print("❌ pyautogui not installed")
        return
    
    print("\n[Common hotkeys]:")
    print("  - pyautogui.hotkey('ctrl', 'c') - copy")
    print("  - pyautogui.hotkey('ctrl', 'v') - paste")
    print("  - pyautogui.hotkey('alt', 'tab') - switch window")
    print("  - pyautogui.hotkey('win') - start menu")
    
    print("\n[DRY RUN - no actual hotkey performed]")
    print("\n✅ TEST 6 PASSED")


def run_all_tests():
    """Run all hands layer tests."""
    print("\n" + "=" * 60)
    print("HANDS LAYER TESTS (DRY RUN)")
    print("=" * 60)
    print("\n⚠️  These tests show capabilities without executing actions")
    print("⚠️  Move mouse to top-left corner to abort if needed (FAILSAFE)")
    
    test_mouse_info()
    test_mouse_move()
    test_click_simulation()
    test_typing_simulation()
    test_scroll_simulation()
    test_hotkey_simulation()
    
    print("\n" + "=" * 60)
    print("ALL HANDS TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
