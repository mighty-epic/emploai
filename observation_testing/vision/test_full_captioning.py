"""
Full OmniParser Test: Detection + Captioning
"""
import sys
import os
sys.path.insert(0, 'observation_testing/omniparser')
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'

import warnings
warnings.filterwarnings('ignore')

print('=' * 60)
print('FULL OMNIPARSER: Detection + Captioning')
print('=' * 60)

# 1. Capture screenshot
print('\n[1] Capturing screenshot...')
import mss
import mss.tools
with mss.mss() as sct:
    s = sct.grab(sct.monitors[1])
    mss.tools.to_png(s.rgb, s.size, output='full_test.png')
print('    Done: full_test.png')

# 2. Load detection model
print('\n[2] Loading detection model...')
from ultralytics import YOLO
det = YOLO('observation_testing/omniparser/weights/icon_detect/model.pt')
print('    Done')

# 3. Load caption model
print('\n[3] Loading caption model...')
from util.utils import get_caption_model_processor
cap = get_caption_model_processor(
    model_name='florence2',
    model_name_or_path='observation_testing/omniparser/weights/icon_caption_florence',
    device='cpu'
)
print('    Done')

# 4. Detect elements
print('\n[4] Detecting elements...')
results = det('full_test.png', conf=0.7, verbose=False)
boxes = results[0].boxes
print(f'    Found {len(boxes)} high-confidence elements')

# 5. Caption first 5 elements
print('\n[5] Captioning top 5 elements:')
from PIL import Image

img = Image.open('full_test.png')
model = cap['model']
processor = cap['processor']

for i, box in enumerate(boxes[:5]):
    x1, y1, x2, y2 = [int(c) for c in box.xyxy[0].tolist()]
    conf = box.conf[0].item()
    
    # Crop and resize to 64x64
    crop = img.crop((x1, y1, x2, y2))
    crop = crop.resize((64, 64))
    
    # Caption
    inputs = processor(images=crop, text='<CAPTION>', return_tensors='pt')
    gen = model.generate(
        input_ids=inputs['input_ids'],
        pixel_values=inputs['pixel_values'],
        max_new_tokens=30,
        num_beams=1
    )
    caption = processor.decode(gen[0], skip_special_tokens=True)
    
    print(f'    [{i+1}] ({x1},{y1}) {x2-x1}x{y2-y1} conf:{conf:.2f}')
    print(f'        Caption: "{caption}"')

print('\n' + '=' * 60)
print('FULL OMNIPARSER TEST COMPLETE!')
print('=' * 60)
