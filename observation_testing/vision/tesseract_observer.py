"""
Tesseract OCR Observer
Extracts text elements with bounding boxes from screenshots.
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import time

# Add shared schemas
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.schemas.observation import ElementDescriptor, BoundingBox, ObservationSnapshot

try:
    import pytesseract
    from PIL import Image
    import mss
    import mss.tools
    TESSERACT_AVAILABLE = True
except ImportError as e:
    TESSERACT_AVAILABLE = False
    print(f"Tesseract not available: {e}")


@dataclass
class TextElement:
    """Represents a detected text element."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    level: int  # Word level, line level, etc.


class TesseractObserver:
    """Observer using Tesseract OCR for text detection with bounding boxes."""
    
    def __init__(self, tesseract_cmd: str = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        self.last_screenshot_path = None
    
    def capture_screen(self, output_path: str = None) -> str:
        """Capture the current screen."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            
            if output_path is None:
                output_path = str(Path(__file__).parent.parent / "test_outputs" / "tesseract_capture.png")
            
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
            
            self.last_screenshot_path = output_path
            return output_path
    
    def extract_text_elements(self, image_path: str, min_confidence: float = 30.0) -> List[TextElement]:
        """
        Extract text elements with bounding boxes from an image.
        
        Args:
            image_path: Path to the image
            min_confidence: Minimum confidence threshold (0-100)
        
        Returns:
            List of TextElement objects with text and bounding boxes
        """
        image = Image.open(image_path)
        
        # Get detailed OCR data with bounding boxes
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        elements = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = float(data['conf'][i])
            
            # Skip empty text or low confidence
            if not text or conf < min_confidence:
                continue
            
            element = TextElement(
                text=text,
                x=data['left'][i],
                y=data['top'][i],
                width=data['width'][i],
                height=data['height'][i],
                confidence=conf / 100.0,  # Normalize to 0-1
                level=data['level'][i]
            )
            elements.append(element)
        
        return elements
    
    def extract_lines(self, image_path: str, min_confidence: float = 30.0) -> List[TextElement]:
        """
        Extract text as lines (grouped words) with bounding boxes.
        """
        image = Image.open(image_path)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        # Group by line number
        lines = {}
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = float(data['conf'][i])
            
            if not text or conf < min_confidence:
                continue
            
            # Create line key (block_num, par_num, line_num)
            line_key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            
            if line_key not in lines:
                lines[line_key] = {
                    'texts': [],
                    'x_min': data['left'][i],
                    'y_min': data['top'][i],
                    'x_max': data['left'][i] + data['width'][i],
                    'y_max': data['top'][i] + data['height'][i],
                    'confs': []
                }
            
            lines[line_key]['texts'].append(text)
            lines[line_key]['x_min'] = min(lines[line_key]['x_min'], data['left'][i])
            lines[line_key]['y_min'] = min(lines[line_key]['y_min'], data['top'][i])
            lines[line_key]['x_max'] = max(lines[line_key]['x_max'], data['left'][i] + data['width'][i])
            lines[line_key]['y_max'] = max(lines[line_key]['y_max'], data['top'][i] + data['height'][i])
            lines[line_key]['confs'].append(conf)
        
        elements = []
        for line_key, line_data in lines.items():
            element = TextElement(
                text=' '.join(line_data['texts']),
                x=line_data['x_min'],
                y=line_data['y_min'],
                width=line_data['x_max'] - line_data['x_min'],
                height=line_data['y_max'] - line_data['y_min'],
                confidence=sum(line_data['confs']) / len(line_data['confs']) / 100.0,
                level=4  # Line level
            )
            elements.append(element)
        
        return elements
    
    def get_observation_snapshot(self, image_path: str = None, group_as_lines: bool = True) -> ObservationSnapshot:
        """
        Get a full observation snapshot with all detected text elements.
        
        Args:
            image_path: Path to image (if None, captures current screen)
            group_as_lines: If True, group words into lines
        
        Returns:
            ObservationSnapshot with detected text elements
        """
        if image_path is None:
            image_path = self.capture_screen()
        
        if group_as_lines:
            text_elements = self.extract_lines(image_path)
        else:
            text_elements = self.extract_text_elements(image_path)
        
        # Convert to ElementDescriptor format
        elements = []
        for i, te in enumerate(text_elements):
            element = ElementDescriptor(
                id=f"text_{i}",
                role="text",
                text=te.text,
                bbox=BoundingBox(
                    x=te.x,
                    y=te.y,
                    width=te.width,
                    height=te.height
                ),
                confidence=te.confidence,
                is_enabled=True
            )
            elements.append(element)
        
        return ObservationSnapshot(
            source="tesseract",
            timestamp=time.time(),
            elements=elements,
            screenshot_path=image_path,
            metadata={
                "element_count": len(elements),
                "grouped_as_lines": group_as_lines
            }
        )


def test_tesseract():
    """Test Tesseract OCR observer."""
    print("=" * 60)
    print("TESSERACT OCR OBSERVER TEST")
    print("=" * 60)
    
    if not TESSERACT_AVAILABLE:
        print("❌ Tesseract not available")
        return
    
    observer = TesseractObserver()
    
    # Capture screen
    print("\n[1] Capturing screenshot...")
    screenshot_path = observer.capture_screen()
    print(f"    Saved: {screenshot_path}")
    
    # Extract text with bounding boxes
    print("\n[2] Extracting text elements...")
    start = time.time()
    snapshot = observer.get_observation_snapshot(screenshot_path, group_as_lines=True)
    elapsed = time.time() - start
    
    print(f"\n[3] Results:")
    print(f"    Elements found: {len(snapshot.elements)}")
    print(f"    Processing time: {elapsed:.2f}s")
    
    print(f"\n[4] Sample elements (first 10):")
    for el in snapshot.elements[:10]:
        text_preview = el.text[:40] + "..." if len(el.text) > 40 else el.text
        print(f"    [{el.id}] \"{text_preview}\"")
        print(f"           @ ({el.bbox.x}, {el.bbox.y}) size: {el.bbox.width}x{el.bbox.height} conf: {el.confidence:.2f}")
    
    print("\n" + "=" * 60)
    print("✅ TESSERACT TEST COMPLETE")
    print("=" * 60)
    
    return snapshot


if __name__ == "__main__":
    test_tesseract()
