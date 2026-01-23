"""
LIVE TEST: pywinauto Observer
Tests extracting information from Windows desktop applications.

Run with: python -m observation_testing.tests.test_pywinauto_live
"""

import json
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from observation_testing.structured.pywinauto_observer import PywinautoObserver, PYWINAUTO_AVAILABLE


def test_active_window():
    """
    Test 1: Get information about the currently active window.
    """
    print("=" * 60)
    print("TEST 1: Active Window Info")
    print("=" * 60)
    
    if not PYWINAUTO_AVAILABLE:
        print("❌ pywinauto not available (Windows only)")
        return None
    
    observer = PywinautoObserver()
    
    try:
        print("\n[1] Getting active window info...")
        print("    (Make sure a window is active!)")
        time.sleep(1)
        
        window_info = observer.get_active_window_info()
        
        if window_info:
            print(f"\n[2] Active Window:")
            print(f"    Title: {window_info.get('title', 'N/A')}")
            print(f"    Class: {window_info.get('class_name', 'N/A')}")
            print(f"    PID: {window_info.get('process_id', 'N/A')}")
            bbox = window_info.get('bbox', {})
            print(f"    Position: ({bbox.get('x', 0)}, {bbox.get('y', 0)})")
            print(f"    Size: {bbox.get('width', 0)} x {bbox.get('height', 0)}")
            print("\n✅ TEST 1 PASSED")
        else:
            print("\n⚠️ No active window detected")
            
        return window_info
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        raise


def test_window_elements():
    """
    Test 2: Extract all UI elements from the active window.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Window Elements")
    print("=" * 60)
    
    if not PYWINAUTO_AVAILABLE:
        print("❌ pywinauto not available (Windows only)")
        return None
    
    observer = PywinautoObserver()
    
    try:
        print("\n[1] Extracting elements from active window...")
        print("    (This may take a few seconds)")
        
        elements = observer.get_visible_elements()
        
        print(f"\n[2] Found {len(elements)} elements")
        
        # Group by control type
        types = {}
        for el in elements:
            ct = el.get('control_type', 'Unknown')
            types[ct] = types.get(ct, 0) + 1
        
        print(f"\n[3] Element types:")
        for ct, count in sorted(types.items(), key=lambda x: -x[1]):
            print(f"    {ct}: {count}")
        
        # Show first 10 elements
        print(f"\n[4] First 10 elements:")
        for el in elements[:10]:
            text = el.get('text', '')[:40] or el.get('name', '')[:40] or '(no text)'
            role = el.get('role', 'generic')
            print(f"    [{role}] {text}")
        
        print("\n✅ TEST 2 PASSED")
        return elements
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        raise


def test_focused_element():
    """
    Test 3: Get the currently focused element.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Focused Element")
    print("=" * 60)
    
    if not PYWINAUTO_AVAILABLE:
        print("❌ pywinauto not available (Windows only)")
        return None
    
    observer = PywinautoObserver()
    
    try:
        print("\n[1] Getting focused element...")
        print("    (Try clicking in a text field first!)")
        
        focused = observer.get_focused_element()
        
        if focused:
            print(f"\n[2] Focused Element:")
            print(f"    Type: {focused.get('control_type', 'N/A')}")
            print(f"    Role: {focused.get('role', 'N/A')}")
            print(f"    Text: {focused.get('text', 'N/A')[:50]}")
            print(f"    Name: {focused.get('name', 'N/A')[:50]}")
            bbox = focused.get('bbox', {})
            print(f"    Position: ({bbox.get('x', 0)}, {bbox.get('y', 0)})")
            print("\n✅ TEST 3 PASSED")
        else:
            print("\n⚠️ No focused element detected")
        
        return focused
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        raise


def test_full_snapshot():
    """
    Test 4: Get complete observation snapshot.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Full Observation Snapshot")
    print("=" * 60)
    
    if not PYWINAUTO_AVAILABLE:
        print("❌ pywinauto not available (Windows only)")
        return None
    
    observer = PywinautoObserver()
    
    try:
        print("\n[1] Getting full observation snapshot...")
        
        snapshot = observer.get_observation_snapshot()
        
        print(f"\n[2] Snapshot Summary:")
        print(f"    Source: {snapshot.get('source', 'N/A')}")
        print(f"    Active Window: {snapshot.get('active_window', {}).get('title', 'N/A')}")
        print(f"    Elements: {len(snapshot.get('elements', []))}")
        print(f"    Focused: {snapshot.get('focused_element') is not None}")
        
        # Save snapshot to file
        output_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "test_outputs",
            "pywinauto_snapshot.json"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
        
        print(f"\n[3] Snapshot saved to: {output_path}")
        print("\n✅ TEST 4 PASSED")
        
        return snapshot
        
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        raise


def test_list_all_windows():
    """
    Test 5: List all open windows on the desktop.
    """
    print("\n" + "=" * 60)
    print("TEST 5: List All Windows")
    print("=" * 60)
    
    if not PYWINAUTO_AVAILABLE:
        print("❌ pywinauto not available (Windows only)")
        return None
    
    try:
        from pywinauto import Desktop
        
        print("\n[1] Enumerating all windows...")
        
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        
        print(f"\n[2] Found {len(windows)} windows:")
        
        visible_windows = []
        for win in windows:
            try:
                if win.is_visible():
                    title = win.window_text()
                    if title:  # Only show windows with titles
                        rect = win.rectangle()
                        visible_windows.append({
                            "title": title,
                            "class": win.class_name(),
                            "pid": win.process_id(),
                            "size": f"{rect.width()}x{rect.height()}"
                        })
            except:
                pass
        
        for i, w in enumerate(visible_windows[:15]):
            print(f"    {i+1}. [{w['class'][:20]}] {w['title'][:40]} ({w['size']})")
        
        if len(visible_windows) > 15:
            print(f"    ... and {len(visible_windows) - 15} more")
        
        print("\n✅ TEST 5 PASSED")
        return visible_windows
        
    except Exception as e:
        print(f"\n❌ TEST 5 FAILED: {e}")
        raise


def run_all_tests():
    """Run all pywinauto observer tests."""
    print("\n" + "=" * 60)
    print("PYWINAUTO OBSERVER LIVE TESTS")
    print("=" * 60)
    
    if not PYWINAUTO_AVAILABLE:
        print("\n❌ pywinauto is only available on Windows")
        print("   Skipping all tests.")
        return
    
    tests = [
        ("Active Window", test_active_window),
        ("Window Elements", test_window_elements),
        ("Focused Element", test_focused_element),
        ("Full Snapshot", test_full_snapshot),
        ("List All Windows", test_list_all_windows),
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
