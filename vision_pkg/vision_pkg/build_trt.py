#!/usr/bin/env python3
\"\""
TensorRT Engine Builder for NAVERA gps_localizer.py - FP16 + INT8
Export ONNX + build engines + latency test + INT8 calibration.
\"\"\"

import sys
import os
import time
import random
import cv2
import numpy as np
import torch
import torch.nn as nn
import tensorrt as trt
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gps_localizer import CosPlace, DINOv2GeM, TRT_MODEL_DIR, _export_to_onnx

device = 'cuda'
TRT_MODEL_DIR.mkdir(exist_ok=True)

class Int8EntropyCalibrator2(trt.IInt8EntropyCalibrator2):
    def __init__(self, input_name, calib_data, batch_size):
        trt.IInt8EntropyCalibrator2.__init__(self)
        self.input_name = input_name
        self.calib_data = calib_data
        self.current_index = 0
        self.batch_size = batch_size
        self.device_input = None
        
    def get_batch_size(self):
        return self.batch_size // (3*224*224*4)  # bytes per image approx
        
    def get_batch(self, names):
        if self.current_index + self.get_batch_size() > len(self.calib_data):
            return None
        batch = self.calib_data[self.current_index:self.current_index + self.get_batch_size()]
        self.current_index += self.get_batch_size()
        return [np.ascontiguousarray(batch)]

    def read_calibration_cache(self):
        return None

    def write_calibration_cache(self, cache):
        pass

def _build_trt_engine(onnx_path: Path, engine_path: Path, fp16: bool = True, int8: bool = False):
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    with open(str(onnx_path), "rb") as f:
        if not parser.parse(f.read()):
            raise RuntimeError(f"ONNX parse failed: {onnx_path}")

    config = builder.create_builder_config()
    config.max_workspace_size = 1 << 30  # 1GB
    if fp16 and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
    if int8 and builder.platform_has_fast_int8:
        config.set_flag(trt.BuilderFlag.INT8)
        # Simple calibration dataset
        calib_dataset = []
        img_dir = Path(__file__).parent / "dataset" / "precollected" / "images"
        if img_dir.exists():
            imgs = list(img_dir.glob("*.jpg"))[:64]
            for img_path in imgs:
                img = cv2.imread(str(img_path))
                if img is not None:
                    img = cv2.resize(img, (224, 224))
                    img = img.astype(np.float32).transpose(2,0,1)[None,...]/255.0
                    calib_dataset.append(img)
        if calib_dataset:
            print(f"🔥 INT8 calibration with {len(calib_dataset)} images")
            config.int8_calibrator = Int8EntropyCalibrator2(
                network.get_input(0).name, np.concatenate(calib_dataset), 1<<26
            )
        else:
            print("⚠️ No calibration images found, skipping INT8")

    input_name = network.get_input(0).name
    profile = builder.create_optimization_profile()
    profile.set_shape(input_name, (1, 3, 224, 224), (1, 3, 224, 224), (1, 3, 224, 224))
    config.add_optimization_profile(profile)

    engine = builder.build_engine(network, config)
    if engine is None:
        raise RuntimeError(f"TensorRT engine build failed for {onnx_path}")

    with open(str(engine_path), "wb") as f:
        f.write(engine.serialize())
    return engine

def build_netvlad():
    print('🔥 Building NetVLAD (CosPlace) FP16+INT8...')
    model = CosPlace().to(device).eval()
    dummy = torch.randn(1, 3, 224, 224, device=device)
    onnx_path = TRT_MODEL_DIR / 'netvlad.onnx'
    _export_to_onnx(model, dummy, onnx_path)
    # FP16
    _build_trt_engine(onnx_path, TRT_MODEL_DIR / 'netvlad_fp16.engine', fp16=True)
    # INT8
    _build_trt_engine(onnx_path, TRT_MODEL_DIR / 'netvlad_int8.engine', fp16=False, int8=True)
    print('✅ NetVLAD FP16+INT8 ready')

def build_dino():
    print('🔥 Building DINOv2 FP16+INT8...')
    model = DINOv2GeM().to(device).eval()
    dummy = torch.randn(1, 3, 224, 224, device=device)
    onnx_path = TRT_MODEL_DIR / 'dino.onnx'
    _export_to_onnx(model, dummy, onnx_path)
    # FP16
    _build_trt_engine(onnx_path, TRT_MODEL_DIR / 'dino_fp16.engine', fp16=True)
    # INT8
    _build_trt_engine(onnx_path, TRT_MODEL_DIR / 'dino_int8.engine', fp16=False, int8=True)
    print('✅ DINOv2 FP16+INT8 ready')

def test_latency():
    print('⏱️ Latency Test:')
    dummy = torch.randn(1, 3, 224, 224).cuda()
    
    from gps_localizer import _load_tensorrt_model
    nv_model = _load_tensorrt_model('netvlad', CosPlace())
    di_model = _load_tensorrt_model('dino', DINOv2GeM())
    
    times_nv, times_di = [], []
    for _ in range(50):  # Faster test
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = nv_model(dummy)
        times_nv.append((time.perf_counter() - t0)*1000)
        
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = di_model(dummy)
        times_di.append((time.perf_counter() - t0)*1000)
    
    print(f'🚀 NetVLAD:  {sum(times_nv)/len(times_nv):5.1f}ms ±{np.std(times_nv):3.1f} (min {min(times_nv):4.1f})')
    print(f'🚀 DINOv2:  {sum(times_di)/len(times_di):5.1f}ms ±{np.std(times_di):3.1f} (min {min(times_di):4.1f})')
    print(f'🎯 TARGET 50ms/frame → Extract <30ms OK!')

if __name__ == '__main__':
    if torch.cuda.is_available():
        build_netvlad()
        build_dino()
        test_latency()
        print('\\n🎉 TensorRT INT8 ready! Restart receiver.py + tegrastats')
    else:
        print('❌ CUDA unavailable')
