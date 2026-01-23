"""
OmniParser Integration Wrapper
Provides a clean interface to OmniParser for UI element detection.
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image
import time

# Add OmniParser to path
OMNIPARSER_PATH = Path(__file__).parent.parent / "omniparser"
sys.path.insert(0, str(OMNIPARSER_PATH))

# Import shared schemas
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.schemas.observation import ElementDescriptor, BoundingBox, ObservationSnapshot


class OmniParserObserver:
    """Wrapper for OmniParser to extract UI elements from screenshots."""
    
    def __init__(self, weights_dir: str = None, detection_only: bool = True):
        self.weights_dir = weights_dir or str(OMNIPARSER_PATH / "weights")
        self.detection_only = detection_only
        self.model_loaded = False
        self.icon_detect_model = None
        self.icon_caption_model = None
        self.processor = None
        
    def load_models(self):
        """Load OmniParser models."""
        if self.model_loaded:
            return
        
        print("[OmniParser] Loading models...")
        
        try:
            # Load icon detection model (YOLO-based)
            from ultralytics import YOLO
            detect_model_path = os.path.join(self.weights_dir, "icon_detect", "model.pt")
            self.icon_detect_model = YOLO(detect_model_path)
            print(f"  ✓ Icon detection model loaded")
            
            # Only load caption model if requested
            if not self.detection_only:
                try:
                    from transformers import AutoProcessor, AutoModelForCausalLM
                    import torch
                    
                    caption_model_path = os.path.join(self.weights_dir, "icon_caption_florence")
                    self.processor = AutoProcessor.from_pretrained(
                        "microsoft/Florence-2-base-ft", 
                        trust_remote_code=True
                    )
                    self.icon_caption_model = AutoModelForCausalLM.from_pretrained(
                        caption_model_path,
                        trust_remote_code=True,
                        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
                    )
                    
                    if torch.cuda.is_available():
                        self.icon_caption_model = self.icon_caption_model.to("cuda")
                        
                    print(f"  ✓ Icon caption model loaded")
                except Exception as e:
                    print(f"  ⚠ Caption model not loaded: {e}")
                    self.detection_only = True
            
            self.model_loaded = True
            mode = "detection-only" if self.detection_only else "full"
            print(f"[OmniParser] Models loaded ({mode} mode)")
            
        except Exception as e:
            print(f"[OmniParser] Error loading models: {e}")
            raise
    
    def detect_elements(self, image_path: str, conf_threshold: float = 0.3) -> List[Dict]:
        """
        Detect UI elements in an image.
        Returns list of detected elements with bounding boxes.
        """
        if not self.model_loaded:
            self.load_models()
        
        # Run YOLO detection
        results = self.icon_detect_model(image_path, conf=conf_threshold)
        
        elements = []
        for result in results:
            boxes = result.boxes
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = box.conf[0].item()
                cls = int(box.cls[0].item()) if hasattr(box, 'cls') else 0
                
                elements.append({
                    "id": f"elem_{i}",
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf,
                    "class_id": cls,
                    "type": "unknown"  # Will be classified later
                })
        
        return elements
    
    def caption_element(self, image: Image.Image, bbox: List[float]) -> str:
        """Generate a caption/description for a UI element."""
        if not self.model_loaded:
            self.load_models()
        
        import torch
        
        # Crop the element from the image
        x1, y1, x2, y2 = [int(c) for c in bbox]
        element_image = image.crop((x1, y1, x2, y2))
        
        # Generate caption using Florence
        prompt = "<CAPTION>"
        inputs = self.processor(text=prompt, images=element_image, return_tensors="pt")
        
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.icon_caption_model.generate(
                **inputs,
                max_new_tokens=50,
                num_beams=3
            )
        
        caption = self.processor.decode(outputs[0], skip_special_tokens=True)
        return caption.replace("<CAPTION>", "").strip()
    
    def classify_element_type(self, caption: str) -> str:
        """Classify element type based on its caption."""
        caption_lower = caption.lower()
        
        if any(w in caption_lower for w in ["button", "btn", "click", "submit", "send"]):
            return "button"
        elif any(w in caption_lower for w in ["text field", "input", "textbox", "search", "enter"]):
            return "textbox"
        elif any(w in caption_lower for w in ["checkbox", "check box", "toggle"]):
            return "checkbox"
        elif any(w in caption_lower for w in ["dropdown", "select", "menu", "list"]):
            return "dropdown"
        elif any(w in caption_lower for w in ["link", "hyperlink", "url"]):
            return "link"
        elif any(w in caption_lower for w in ["icon", "image", "logo", "picture"]):
            return "icon"
        elif any(w in caption_lower for w in ["label", "text", "title", "heading"]):
            return "label"
        else:
            return "generic"
    
    def parse_screenshot(self, image_path: str, caption_elements: bool = True) -> ObservationSnapshot:
        """
        Parse a screenshot and return structured observation.
        
        Args:
            image_path: Path to screenshot image
            caption_elements: Whether to generate captions (slower but more accurate)
        
        Returns:
            ObservationSnapshot with all detected elements
        """
        print(f"[OmniParser] Parsing: {image_path}")
        start_time = time.time()
        
        # Load image
        image = Image.open(image_path)
        
        # Detect elements
        raw_elements = self.detect_elements(image_path)
        print(f"  → Detected {len(raw_elements)} elements")
        
        # Convert to ElementDescriptors
        elements = []
        for i, el in enumerate(raw_elements):
            bbox = el["bbox"]
            
            # Optionally caption each element
            if caption_elements and len(raw_elements) <= 50:  # Limit for speed
                try:
                    caption = self.caption_element(image, bbox)
                    el_type = self.classify_element_type(caption)
                except Exception as e:
                    caption = ""
                    el_type = "generic"
            else:
                caption = ""
                el_type = "generic"
            
            element = ElementDescriptor(
                id=f"omni_{i}",
                role=el_type,
                text=caption,
                bbox=BoundingBox(
                    x=bbox[0],
                    y=bbox[1],
                    width=bbox[2] - bbox[0],
                    height=bbox[3] - bbox[1]
                ),
                confidence=el["confidence"]
            )
            elements.append(element)
        
        elapsed = time.time() - start_time
        print(f"  → Parsing complete in {elapsed:.2f}s")
        
        return ObservationSnapshot(
            source="omniparser",
            timestamp=time.time(),
            elements=elements,
            screenshot_path=image_path,
            metadata={
                "parsing_time_seconds": elapsed,
                "raw_element_count": len(raw_elements)
            }
        )


def test_omniparser():
    """Quick test of OmniParser."""
    import mss
    import mss.tools
    
    print("=" * 60)
    print("OmniParser Integration Test")
    print("=" * 60)
    
    # Capture screenshot
    print("\n[1] Capturing screenshot...")
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        
        output_dir = Path(__file__).parent.parent / "test_outputs"
        output_dir.mkdir(exist_ok=True)
        screenshot_path = str(output_dir / "omniparser_test.png")
        
        mss.tools.to_png(screenshot.rgb, screenshot.size, output=screenshot_path)
        print(f"    Saved: {screenshot_path}")
    
    # Initialize OmniParser
    print("\n[2] Initializing OmniParser...")
    observer = OmniParserObserver()
    
    # Parse screenshot (without captions for speed)
    print("\n[3] Parsing screenshot (detection only)...")
    snapshot = observer.parse_screenshot(screenshot_path, caption_elements=False)
    
    print(f"\n[4] Results:")
    print(f"    Source: {snapshot.source}")
    print(f"    Elements: {len(snapshot.elements)}")
    print(f"    Parsing time: {snapshot.metadata['parsing_time_seconds']:.2f}s")
    
    print(f"\n[5] Sample elements:")
    for el in snapshot.elements[:10]:
        print(f"    - [{el.role}] @ ({el.bbox.x:.0f}, {el.bbox.y:.0f}) "
              f"size: {el.bbox.width:.0f}x{el.bbox.height:.0f} "
              f"conf: {el.confidence:.2f}")
    
    print("\n✅ OmniParser test complete!")
    return snapshot


if __name__ == "__main__":
    test_omniparser()
