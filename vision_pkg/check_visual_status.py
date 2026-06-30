#!/usr/bin/env python3
"""Check if visual localizer is ready and can match"""
import sys
sys.path.insert(0, 'vision_pkg')
from pathlib import Path

print("\n" + "="*70)
print("CHECKING VISUAL LOCALIZER STATUS")
print("="*70)

# Check dataset
dataset_base = Path("dataset")
fallback_dataset = dataset_base / "fallback_dataset"

print(f"\n1. Dataset Location:")
print(f"   {dataset_base} exists: {dataset_base.exists()}")
print(f"   {fallback_dataset} exists: {fallback_dataset.exists()}")

# Check coords.json
coords_file = fallback_dataset / "coords.json"
print(f"\n2. Coordinates File:")
print(f"   {coords_file} exists: {coords_file.exists()}")
if coords_file.exists():
    import json
    coords = json.load(open(coords_file))
    print(f"   Number of frames: {len(coords)}")

# Check descriptors
desc_file = fallback_dataset / "descriptors.npy"
print(f"\n3. Descriptors:")
print(f"   {desc_file} exists: {desc_file.exists()}")
if desc_file.exists():
    import numpy as np
    descs = np.load(desc_file)
    print(f"   Shape: {descs.shape}")
    print(f"   Dtype: {descs.dtype}")

# Check images
images_dir = fallback_dataset / "images"
print(f"\n4. Images Directory:")
print(f"   {images_dir} exists: {images_dir.exists()}")
if images_dir.exists():
    imgs = list(images_dir.glob("*.jpg"))
    print(f"   Number of images: {len(imgs)}")
    if imgs:
        print(f"   First image: {imgs[0].name}")

# Try to import and test matching
print(f"\n5. Testing Visual Localizer:")
try:
    from gps_localizer import match, extract_descriptor, get_model, DEVICE, MODEL_TYPE
    print(f"   ✓ gps_localizer imported")
    print(f"   Device: {DEVICE}")
    print(f"   Model: {MODEL_TYPE}")
    
    # Test descriptor extraction
    if images_dir.exists() and list(images_dir.glob("*.jpg")):
        test_img = list(images_dir.glob("*.jpg"))[0]
        print(f"\n6. Testing Descriptor Extraction:")
        desc = extract_descriptor(str(test_img))
        if desc is not None:
            print(f"   ✓ Extracted descriptor shape: {desc.shape}")
        else:
            print(f"   ✗ Failed to extract descriptor")
    
    # Test matching
    if desc_file.exists() and coords_file.exists() and list(images_dir.glob("*.jpg")):
        print(f"\n7. Testing Matching:")
        test_img = list(images_dir.glob("*.jpg"))[0]
        result = match(str(test_img), str(fallback_dataset))
        if result:
            print(f"   ✓ Match found!")
            best = result.get("best", result)
            print(f"   Lat: {best['lat']:.6f}")
            print(f"   Lon: {best['lon']:.6f}")
            print(f"   Score: {best['score']:.4f}")
        else:
            print(f"   ✗ No match found")
            
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70 + "\n")
