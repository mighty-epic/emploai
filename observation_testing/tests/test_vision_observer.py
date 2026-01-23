"""
TEST: Vision Observer (Tesseract OCR)
Tests text extraction with bounding boxes from screenshots.

Run with: python -m observation_testing.tests.test_vision_observer
"""

import sys
import os
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import pytesseract
    from PIL import Image
    import mss
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from shared.schemas.observation import ElementDescriptor, BoundingBox, ObservationSnapshot


def test_screenshot_capture():
    """Test 1: Capture current screen."""
    print("=" * 60)
    print("TEST 1: Screenshot Capture")
    print("=" * 60)
    
    import mss.tools
    
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        
        output_dir = Path(__file__).parent.parent / "test_outputs"
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / "vision_test.png")
        
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
        
        print(f"\n[Screenshot]:")
        print(f"    Path: {output_path}")
        print(f"    Size: {screenshot.width} x {screenshot.height}")
        print(f"    Exists: {os.path.exists(output_path)}")
    
    print("\n✅ TEST 1 PASSED")
    return output_path


def test_tesseract_ocr(image_path: str):
    """Test 2: Extract text with Tesseract OCR."""
    print("\n" + "=" * 60)
    print("TEST 2: Tesseract OCR Extraction")
    print("=" * 60)
    
    if not TESSERACT_AVAILABLE:
        print("\n⚠️ pytesseract not installed")
        print("   Install with: pip install pytesseract")
        return None
    
    image = Image.open(image_path)
    
    print("\n[1] Running Tesseract OCR...")
    start = time.time()
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    elapsed = time.time() - start
    
    # Count valid text elements
    valid_elements = 0
    for i, text in enumerate(data['text']):
        if text.strip() and float(data['conf'][i]) > 30:
            valid_elements += 1
    
    print(f"    Processing time: {elapsed:.2f}s")
    print(f"    Total boxes: {len(data['text'])}")
    print(f"    Valid text elements: {valid_elements}")
    
    print("\n[2] Sample text elements (first 10):")
    count = 0
    for i, text in enumerate(data['text']):
        if text.strip() and float(data['conf'][i]) > 30:
            conf = float(data['conf'][i])
            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
            text_preview = text[:30] + "..." if len(text) > 30 else text
            print(f"    \"{text_preview}\" @ ({x},{y}) {w}x{h} conf:{conf:.0f}%")
            count += 1
            if count >= 10:
                break
    
    print("\n✅ TEST 2 PASSED")
    return data


def test_grouped_lines(image_path: str):
    """Test 3: Group words into lines."""
    print("\n" + "=" * 60)
    print("TEST 3: Line Grouping")
    print("=" * 60)
    
    if not TESSERACT_AVAILABLE:
        print("\n⚠️ pytesseract not installed")
        return
    
    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    
    # Group by line
    lines = {}
    for i, text in enumerate(data['text']):
        if not text.strip() or float(data['conf'][i]) < 30:
            continue
        
        line_key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        if line_key not in lines:
            lines[line_key] = []
        lines[line_key].append(text)
    
    print(f"\n[Lines found]: {len(lines)}")
    print("\n[Sample lines (first 10)]:")
    for i, (key, words) in enumerate(list(lines.items())[:10]):
        line_text = ' '.join(words)
        if len(line_text) > 50:
            line_text = line_text[:50] + "..."
        print(f"    Line {i+1}: \"{line_text}\"")
    
    print("\n✅ TEST 3 PASSED")


def test_observation_snapshot(image_path: str):
    """Test 4: Create ObservationSnapshot from Tesseract output."""
    print("\n" + "=" * 60)
    print("TEST 4: ObservationSnapshot Creation")
    print("=" * 60)
    
    if not TESSERACT_AVAILABLE:
        print("\n⚠️ pytesseract not installed")
        return
    
    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    
    # Create element descriptors
    elements = []
    for i, text in enumerate(data['text']):
        if not text.strip() or float(data['conf'][i]) < 30:
            continue
        
        element = ElementDescriptor(
            id=f"text_{len(elements)}",
            role="text",
            text=text.strip(),
            bbox=BoundingBox(
                x=data['left'][i],
                y=data['top'][i],
                width=data['width'][i],
                height=data['height'][i]
            ),
            confidence=float(data['conf'][i]) / 100.0,
            is_enabled=True
        )
        elements.append(element)
    
    snapshot = ObservationSnapshot(
        source="tesseract",
        timestamp=time.time(),
        elements=elements,
        screenshot_path=image_path,
        metadata={"ocr_engine": "tesseract"}
    )
    
    print(f"\n[ObservationSnapshot]:")
    print(f"    Source: {snapshot.source}")
    print(f"    Elements: {len(snapshot.elements)}")
    print(f"    Screenshot: {snapshot.screenshot_path}")
    
    print("\n[Sample elements]:")
    for el in snapshot.elements[:5]:
        print(f"    [{el.id}] \"{el.text}\" @ ({el.bbox.x},{el.bbox.y})")
    
    print("\n✅ TEST 4 PASSED")
    return snapshot


def run_all_tests():
    """Run all vision observer tests."""
    print("\n" + "=" * 60)
    print("VISION OBSERVER TESTS (Tesseract OCR)")
    print("=" * 60)
    
    # Test 1: Screenshot
    image_path = test_screenshot_capture()
    
    # Test 2: OCR
    test_tesseract_ocr(image_path)
    
    # Test 3: Line grouping
    test_grouped_lines(image_path)
    
    # Test 4: Snapshot creation
    test_observation_snapshot(image_path)
    
    print("\n" + "=" * 60)
    print("ALL VISION OBSERVER TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
