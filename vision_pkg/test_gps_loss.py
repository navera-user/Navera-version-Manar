#!/usr/bin/env python3
"""
Test GPS loss handling and position prediction
"""
import time
import json
import requests
import base64
from pathlib import Path
import sys

# Test parameters
RECEIVER_URL = "http://localhost:5000/frame"
STATUS_URL = "http://localhost:5000/api/gps_status.json"
TEST_IMAGE_PATH = Path(__file__).parent / "dataset" / "frames_gps"

def get_test_image():
    """Get first available test image or create a dummy one"""
    gps_frames = list(TEST_IMAGE_PATH.glob("*.jpg"))
    if gps_frames:
        return gps_frames[0]
    # Create a simple test image
    import cv2
    import numpy as np
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    test_img = TEST_IMAGE_PATH / "test_frame.jpg"
    cv2.imwrite(str(test_img), img)
    return test_img

def send_gps_frame(frame_id, lat, lon):
    """Send a frame with GPS"""
    img_path = get_test_image()
    with open(img_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()
    
    metadata = {
        "frame_id": frame_id,
        "timestamp": time.time(),
        "gps_valid": True,
        "lat": lat,
        "lon": lon,
        "altitude_m": 400,
        "heading_deg": 45,
        "speed_mps": 10,
        "delta_t_s": 1.0
    }
    
    try:
        resp = requests.post(RECEIVER_URL, json={
            "image_b64": img_data,
            "metadata": metadata
        }, timeout=5)
        print(f"[GPS Frame #{frame_id}] {resp.status_code}")
        return resp.json()
    except Exception as e:
        print(f"[GPS Frame #{frame_id}] ERROR: {e}")
        return None

def send_nogps_frame(frame_id):
    """Send a frame without GPS (GPS loss scenario)"""
    img_path = get_test_image()
    with open(img_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()
    
    metadata = {
        "frame_id": frame_id,
        "timestamp": time.time(),
        "gps_valid": False,
        "altitude_m": 400,
        "heading_deg": 45,
        "speed_mps": 10,
        "delta_t_s": 1.0
    }
    
    try:
        resp = requests.post(RECEIVER_URL, json={
            "image_b64": img_data,
            "metadata": metadata
        }, timeout=5)
        print(f"[NO-GPS Frame #{frame_id}] {resp.status_code} - {resp.json()}")
        return resp.json()
    except Exception as e:
        print(f"[NO-GPS Frame #{frame_id}] ERROR: {e}")
        return None

def check_status():
    """Check GPS status"""
    try:
        status_file = Path("/home/navera/isaac_ros_common/vision_pkg/dataset/gps_status.json")
        if status_file.exists():
            with open(status_file) as f:
                data = json.load(f)
            print(f"Status: {data.get('status')} | lat={data.get('lat', 0):.5f} lon={data.get('lon', 0):.5f} score={data.get('score', 0):.3f}")
            return data
    except Exception as e:
        print(f"Status check error: {e}")
    return None

def test_gps_loss():
    """Test GPS loss scenario"""
    print("="*60)
    print("Testing GPS Loss Handling")
    print("="*60)
    
    # Start with GPS frames
    print("\n1. Sending GPS-valid frames...")
    for i in range(1, 4):
        result = send_gps_frame(i, 35.8216 + i*0.0001, 10.5947)
        time.sleep(0.5)
    
    # Check status
    print("\n2. Status after GPS frames:")
    check_status()
    
    # Now simulate GPS loss
    print("\n3. Simulating GPS LOSS - sending frames without GPS...")
    for i in range(4, 7):
        print(f"\n  Frame #{i}:")
        result = send_nogps_frame(i)
        time.sleep(0.1)
    
    # Check final status
    print("\n4. Final status (GPS lost scenario):")
    status = check_status()
    
    if status:
        print("\n✅ TEST OUTPUT FORMAT:")
        if status.get('status') == 'predicted':
            print(f"✅ PRÉDIT | lat={status.get('lat', 0):.5f} lon={status.get('lon', 0):.5f} score={status.get('score', 0):.3f}")
        elif status.get('status') == 'searching':
            print(f"🔍 Searching (R={status.get('search_radius_m', 0):.0f}m)")
        else:
            print(f"Status: {status.get('status')}")

if __name__ == "__main__":
    print("Make sure receiver.py is running (python3 receiver.py)")
    input("Press Enter to start test...")
    test_gps_loss()
