#!/usr/bin/env python3
"""
Verify GPU models (DINOv2, NetVLAD) are working correctly
"""
import sys
from pathlib import Path

# Add the vision_pkg directory to path
sys.path.insert(0, str(Path(__file__).parent / "vision_pkg"))

def check_pytorch():
    """Check if PyTorch and GPU are available"""
    try:
        import torch
        print("✅ PyTorch installed")
        print(f"   Version: {torch.__version__}")
        if torch.cuda.is_available():
            print(f"✅ CUDA available: {torch.cuda.get_device_name(0)}")
            print(f"   Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
        else:
            print("⚠️  CUDA not available - will use CPU (slow)")
        return True
    except ImportError:
        print("❌ PyTorch NOT installed - install with: pip install torch torchvision")
        return False

def check_dinov2():
    """Check if DINOv2 can be loaded"""
    try:
        import torch
        print("\n📦 Testing DINOv2 model...")
        model = torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14_reg')
        print("✅ DINOv2 model loaded successfully")
        print(f"   Model device: {next(model.parameters()).device}")
        return True
    except Exception as e:
        print(f"❌ DINOv2 failed to load: {e}")
        return False

def check_netvlad():
    """Check if NetVLAD can be loaded"""
    try:
        import torch
        print("\n📦 Testing NetVLAD model...")
        # Try to load from local models directory
        models_dir = Path(__file__).parent / "vision_pkg" / "models"
        weights_path = models_dir / "netvlad_weights.pth"
        
        if not weights_path.exists():
            print(f"⚠️  NetVLAD weights not found at {weights_path}")
            print("   NetVLAD will fallback to MobileNetV3")
            return False
        
        # Try to load the weights
        weights = torch.load(str(weights_path), map_location='cpu')
        print("✅ NetVLAD weights found and loadable")
        return True
    except Exception as e:
        print(f"⚠️  NetVLAD check failed: {e}")
        return False

def check_mobilenet():
    """Check if MobileNetV3 is available"""
    try:
        import torch
        import torchvision.models as models
        print("\n📦 Testing MobileNetV3 fallback...")
        m = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
        print("✅ MobileNetV3 loaded successfully (fallback available)")
        return True
    except Exception as e:
        print(f"❌ MobileNetV3 failed: {e}")
        return False

def check_gps_localizer():
    """Check if gps_localizer module loads correctly"""
    try:
        print("\n📦 Testing gps_localizer module...")
        import gps_localizer
        print(f"✅ gps_localizer module loaded")
        print(f"   Model type: {gps_localizer.MODEL_TYPE}")
        print(f"   Device: {gps_localizer.DEVICE}")
        print(f"   Torch OK: {gps_localizer.TORCH_OK}")
        
        # Try to get model
        model = gps_localizer.get_model()
        print(f"✅ Model obtained: {type(model).__name__}")
        print(f"   Feature dimension: {gps_localizer.FEATURE_DIM}")
        return True
    except Exception as e:
        print(f"❌ gps_localizer error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*60)
    print("GPU Model Verification - Visual Localization")
    print("="*60)
    
    results = {
        "PyTorch": check_pytorch(),
        "DINOv2": check_dinov2(),
        "NetVLAD": check_netvlad(),
        "MobileNetV3": check_mobilenet(),
        "GPS Localizer": check_gps_localizer(),
    }
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for component, status in results.items():
        icon = "✅" if status else "❌"
        print(f"{icon} {component}")
    
    if results["PyTorch"] and (results["DINOv2"] or results["MobileNetV3"]):
        print("\n✅ System ready for visual localization")
        print("   Fallback chain: DINOv2 > NetVLAD > MobileNetV3")
    else:
        print("\n❌ System not ready - missing critical components")
    
if __name__ == "__main__":
    main()
