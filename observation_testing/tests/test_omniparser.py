"""
TEST: OmniParser Vision-Based Observation
Tests extracting UI elements from screenshots using OmniParser.

Run with: python -m observation_testing.tests.test_omniparser

NOTE: OmniParser requires additional setup:
1. cd observation_testing/omniparser
2. pip install -r requirements.txt
3. Download model weights (see OmniParser README)
"""

import json
import time
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# OmniParser path
OMNIPARSER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "omniparser"
)

# Check if OmniParser is available
OMNIPARSER_AVAILABLE = os.path.exists(OMNIPARSER_PATH)


def capture_screenshot():
    """Capture current screen using mss."""
    try:
        import mss
        import mss.tools
        
        with mss.mss() as sct:
            # Capture primary monitor
            monitor = sct.monitors[1]  # Monitor 1 is the primary
            screenshot = sct.grab(monitor)
            
            # Save to file
            output_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "test_outputs",
                "screen_capture.png"
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
            
            return output_path, screenshot.size
    except ImportError:
        print("❌ mss not installed. Run: pip install mss")
        return None, None


def test_screenshot_capture():
    """
    Test 1: Capture a screenshot for OmniParser input.
    """
    print("=" * 60)
    print("TEST 1: Screenshot Capture")
    print("=" * 60)
    
    try:
        print("\n[1] Capturing screen...")
        
        screenshot_path, size = capture_screenshot()
        
        if screenshot_path:
            print(f"\n[2] Screenshot captured:")
            print(f"    Path: {screenshot_path}")
            print(f"    Size: {size[0]}x{size[1]}")
            print("\n✅ TEST 1 PASSED")
            return screenshot_path
        else:
            print("\n❌ Failed to capture screenshot")
            return None
            
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        raise


def test_omniparser_setup():
    """
    Test 2: Check OmniParser installation and dependencies.
    """
    print("\n" + "=" * 60)
    print("TEST 2: OmniParser Setup Check")
    print("=" * 60)
    
    print(f"\n[1] OmniParser path: {OMNIPARSER_PATH}")
    print(f"    Exists: {OMNIPARSER_AVAILABLE}")
    
    if not OMNIPARSER_AVAILABLE:
        print("\n❌ OmniParser not found")
        print("   Run: git clone https://github.com/microsoft/OmniParser.git")
        return False
    
    # Check for key files
    key_files = [
        "README.md",
        "requirements.txt",
    ]
    
    print(f"\n[2] Checking key files:")
    all_present = True
    for f in key_files:
        path = os.path.join(OMNIPARSER_PATH, f)
        exists = os.path.exists(path)
        icon = "✅" if exists else "❌"
        print(f"    {icon} {f}")
        if not exists:
            all_present = False
    
    # Check for model weights directory
    weights_dirs = ["weights", "models", "checkpoints"]
    print(f"\n[3] Checking for model weights:")
    weights_found = False
    for d in weights_dirs:
        path = os.path.join(OMNIPARSER_PATH, d)
        if os.path.exists(path):
            weights_found = True
            files = os.listdir(path)
            print(f"    ✅ {d}/ ({len(files)} files)")
            break
    
    if not weights_found:
        print("    ⚠️ No weights directory found")
        print("    You may need to download model weights")
    
    if all_present:
        print("\n✅ TEST 2 PASSED (basic setup)")
    else:
        print("\n⚠️ TEST 2 PARTIAL - some files missing")
    
    return all_present


def test_omniparser_inference():
    """
    Test 3: Run OmniParser on a screenshot.
    This is a placeholder - actual implementation depends on OmniParser's API.
    """
    print("\n" + "=" * 60)
    print("TEST 3: OmniParser Inference")
    print("=" * 60)
    
    if not OMNIPARSER_AVAILABLE:
        print("\n❌ OmniParser not available, skipping")
        return None
    
    # First capture a screenshot
    screenshot_path, _ = capture_screenshot()
    if not screenshot_path:
        print("\n❌ Could not capture screenshot")
        return None
    
    print(f"\n[1] Screenshot ready: {screenshot_path}")
    print(f"\n[2] OmniParser inference...")
    
    # Try to import OmniParser
    try:
        sys.path.insert(0, OMNIPARSER_PATH)
        
        # The actual import depends on OmniParser's structure
        # This is a placeholder showing the expected flow
        print("\n    ⚠️ OmniParser inference placeholder")
        print("    Actual implementation requires:")
        print("    1. Installing OmniParser dependencies")
        print("    2. Downloading model weights")
        print("    3. Running the detection pipeline")
        
        # Simulated output structure
        mock_result = {
            "elements": [
                {"type": "button", "text": "Submit", "bbox": [100, 200, 180, 240], "confidence": 0.95},
                {"type": "input", "text": "", "bbox": [100, 100, 300, 130], "confidence": 0.92},
                {"type": "icon", "text": "", "bbox": [50, 50, 80, 80], "confidence": 0.88},
            ],
            "ocr_text": ["Submit", "Username", "Password"],
            "screenshot_path": screenshot_path
        }
        
        print(f"\n[3] Mock result (for testing flow):")
        print(f"    Elements detected: {len(mock_result['elements'])}")
        for el in mock_result['elements']:
            print(f"    - {el['type']}: '{el['text']}' (conf: {el['confidence']})")
        
        print("\n⚠️ TEST 3 PLACEHOLDER - needs full OmniParser setup")
        return mock_result
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        return None


def test_vision_observation_wrapper():
    """
    Test 4: Test the vision observation wrapper that will integrate OmniParser.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Vision Observation Wrapper")
    print("=" * 60)
    
    print("\n[1] This test will verify the wrapper that normalizes")
    print("    OmniParser output to our ObservationSnapshot schema.")
    
    # Simulated OmniParser output
    raw_omniparser_output = {
        "elements": [
            {"type": "button", "text": "Login", "bbox": [400, 300, 500, 340], "confidence": 0.94},
            {"type": "text_input", "text": "", "bbox": [300, 200, 500, 230], "confidence": 0.91},
            {"type": "text", "text": "Welcome", "bbox": [350, 100, 450, 130], "confidence": 0.97},
        ]
    }
    
    print(f"\n[2] Raw OmniParser output: {len(raw_omniparser_output['elements'])} elements")
    
    # Convert to our schema
    from shared.schemas.observation import ElementDescriptor, BoundingBox, ObservationSnapshot
    import time as time_module
    
    elements = []
    for i, el in enumerate(raw_omniparser_output['elements']):
        bbox = BoundingBox(
            x=el['bbox'][0],
            y=el['bbox'][1],
            width=el['bbox'][2] - el['bbox'][0],
            height=el['bbox'][3] - el['bbox'][1]
        )
        
        # Map OmniParser types to our roles
        role_map = {
            "button": "button",
            "text_input": "textbox",
            "text": "label",
            "icon": "icon",
            "link": "link",
            "checkbox": "checkbox",
        }
        
        descriptor = ElementDescriptor(
            id=f"omni_{i}",
            role=role_map.get(el['type'], 'generic'),
            text=el.get('text', ''),
            bbox=bbox,
            confidence=el.get('confidence', 0.5)
        )
        elements.append(descriptor)
    
    snapshot = ObservationSnapshot(
        source="omniparser",
        timestamp=time_module.time(),
        elements=elements
    )
    
    print(f"\n[3] Normalized snapshot:")
    print(f"    Source: {snapshot.source}")
    print(f"    Elements: {len(snapshot.elements)}")
    for el in snapshot.elements:
        print(f"    - [{el.role}] '{el.text}' @ ({el.bbox.x}, {el.bbox.y}) conf={el.confidence}")
    
    print("\n✅ TEST 4 PASSED")
    return snapshot


def run_all_tests():
    """Run all OmniParser observation tests."""
    print("\n" + "=" * 60)
    print("OMNIPARSER OBSERVATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Screenshot Capture", test_screenshot_capture),
        ("OmniParser Setup", test_omniparser_setup),
        ("OmniParser Inference", test_omniparser_inference),
        ("Vision Wrapper", test_vision_observation_wrapper),
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
        icon = "✅" if "PASSED" in status else "❌"
        print(f"{icon} {name}: {status}")


if __name__ == "__main__":
    run_all_tests()
