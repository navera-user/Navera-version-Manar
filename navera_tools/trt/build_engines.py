#!/usr/bin/env python3
"""Build NAVERA's TensorRT engines ON the Jetson (a deployment step; engines are never committed).

    python3 navera_tools/trt/build_engines.py [--only sthn,disk] [--precision fp16,fp32]

Each network is exported to ONNX from the weights the product loads, then built by TensorRT into
NAVERA_TRT_DIR (default ~/.navera_sim/trt/, gitignored, outside the repository):

  sthn  STHN one stage (night_pkg.sthn_fast.STHNCore: the network and its 6 iterations, closed-form
        homographies), inputs image1 / image2 (1, 3, 256, 256) in [0, 1], output four_pred (1, 2, 2, 2).
        Weights: NAVERA_STHN_DIR / NAVERA_STHN_WEIGHTS.
  disk  kornia DISK ("depth") U-Net, input image (1, 3, H, W) H, W multiples of 16 up to 1024, output
        (1, 129, H, W) = 128 descriptor channels + heatmap; keypoint selection stays in torch.

Building takes minutes per engine and holds the GPU: run it under the shared GPU lock. Needs
TensorRT's Python bindings (python3-libnvinfer) and the onnx package for the export (when they are not
installed, copies unpacked under NAVERA_TRT_DIR/sdk are used; see navera_common.trt_engine).
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "night_pkg"), os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_common import trt_engine  # noqa: E402

ONNX_DIR = os.path.join(trt_engine.TRT_DIR, "onnx")


def _need_onnx():
    try:
        import onnx  # noqa: F401
    except ImportError:
        # the unpacked copy brings a protobuf newer than Ubuntu's: it must come first
        sys.path.insert(0, os.path.join(trt_engine.TRT_DIR, "sdk", "py"))
        for m in [m for m in sys.modules if m == "google" or m.startswith("google.")]:
            del sys.modules[m]
        import onnx  # noqa: F401


def export_sthn() -> str:
    import torch
    from night_pkg.nodes.night_localizer import NightLocalizer
    from night_pkg.sthn_fast import STHNCore
    sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
    weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))
    mbtiles = os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles"))
    loc = NightLocalizer(sthn, weights, mbtiles, device="cuda", sthn_backend="torch")
    core = STHNCore(loc._model.netG).cuda().eval()
    x = (torch.rand(1, 3, 256, 256, device="cuda"), torch.rand(1, 3, 256, 256, device="cuda"))
    out = os.path.join(ONNX_DIR, "sthn.onnx")
    with torch.inference_mode():
        torch.onnx.export(core, x, out, input_names=["image1", "image2"], output_names=["four_pred"],
                          opset_version=17, dynamo=False)
    del loc, core
    torch.cuda.empty_cache()
    return out


def export_disk() -> str:
    import torch
    import kornia.feature as KF
    disk = KF.DISK.from_pretrained("depth").eval()
    out = os.path.join(ONNX_DIR, "disk.onnx")
    torch.onnx.export(disk.unet, torch.rand(1, 3, 640, 640), out, input_names=["image"], output_names=["out"],
                      dynamic_axes={"image": {2: "h", 3: "w"}, "out": {2: "h", 3: "w"}}, opset_version=17,
                      dynamo=False)
    return out


NETS = {
    "sthn": (export_sthn, None),
    "disk": (export_disk, {"image": ((1, 3, 32, 32), (1, 3, 640, 640), (1, 3, 1024, 1024))}),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default="sthn,disk")
    ap.add_argument("--precision", default="fp16,fp32")
    ap.add_argument("--workspace-mb", type=int, default=1024)
    a = ap.parse_args()
    if trt_engine.import_tensorrt() is None:
        sys.exit("TensorRT Python bindings not found: sudo apt install python3-libnvinfer "
                 "(or unpack it under NAVERA_TRT_DIR/sdk/root)")
    _need_onnx()
    os.makedirs(ONNX_DIR, exist_ok=True)
    for name in [n for n in a.only.split(",") if n]:
        export, profile = NETS[name]
        t0 = time.time()
        onnx_path = export()
        print(f"{name}: ONNX {onnx_path} ({time.time() - t0:.0f} s)", flush=True)
        for prec in [p for p in a.precision.split(",") if p]:
            fp16 = prec == "fp16"
            path = trt_engine.engine_path(name, onnx_path, fp16)
            if os.path.exists(path):
                print(f"{name} {prec}: {path} (already built)")
                continue
            t0 = time.time()
            trt_engine.build_engine(onnx_path, path, fp16, profile, a.workspace_mb)
            print(f"{name} {prec}: {path} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
