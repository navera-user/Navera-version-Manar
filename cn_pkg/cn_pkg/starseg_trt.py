"""Optional TensorRT engine for the star-segmentation U-Net (cn_pkg.starseg). Never required: load() returns
None (the caller then runs torch fp16) when TensorRT is missing, the build fails, or NAVERA_STARSEG_TRT=0.

The engine is hardware-specific (rule: never committed): built on the box at first use (~1 min) from an ONNX
export of the loaded weights, fp16, fixed input (FAST_BATCH, 2, FAST_TILE + 2 FAST_PAD, same), cached at
NAVERA_STARSEG_ENGINE (default NAVERA_TRT_DIR/starseg_<weights hash>_b8_576_fp16_trt<ver>.engine). TensorRT
itself through navera_common.trt_engine (system python3-libnvinfer, else the unpacked SDK copy). Ahead of time:

    python3 -m cn_pkg.starseg_trt [--weights W.pth]     # prints the engine path, or why torch is used
"""
import hashlib
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)
BUILD_TIMEOUT_S = 900
BUILD_OPT_LEVEL = 1          # level 3 (default) did not finish in 10 min on the Orin Nano for this network


def shape():
    from cn_pkg import starseg
    s = starseg.FAST_TILE + 2 * starseg.FAST_PAD
    return (starseg.FAST_BATCH, 2, s, s)


def engine_path(weights: str) -> str:
    env = os.environ.get("NAVERA_STARSEG_ENGINE")
    if env:
        return os.path.expanduser(env)
    from navera_common import trt_engine
    trt = trt_engine.import_tensorrt()
    try:
        with open(weights, "rb") as fh:
            tag = hashlib.sha1(fh.read()).hexdigest()[:10]
    except OSError:
        tag = "unknown"
    b, _, h, _ = shape()
    ver = trt.__version__ if trt else "none"
    return os.path.join(trt_engine.TRT_DIR, f"starseg_{tag}_b{b}_{h}_fp16_trt{ver}.engine")


def _need_onnx():
    """onnx for the export: installed, else the unpacked copy under NAVERA_TRT_DIR/sdk/py (as build_engines.py)."""
    import sys
    try:
        import onnx  # noqa: F401
    except ImportError:
        from navera_common import trt_engine
        sys.path.insert(0, os.path.join(trt_engine.TRT_DIR, "sdk", "py"))
        for m in [m for m in sys.modules if m == "google" or m.startswith("google.")]:
            del sys.modules[m]
        import onnx  # noqa: F401


def build(net, weights: str) -> Optional[str]:
    """ONNX export + TensorRT fp16 build -> engine path (cached), or None. Run in its own process (main())."""
    import torch
    from navera_common import trt_engine
    path = engine_path(weights)
    if os.path.exists(path):
        return path
    if trt_engine.import_tensorrt() is None:
        logger.info("starseg_trt: no TensorRT: torch fp16")
        return None
    _need_onnx()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    onnx = path[:-len(".engine")] + ".onnx"
    p0 = next(net.parameters())
    was_half = p0.dtype == torch.float16
    try:
        net.float()
        torch.onnx.export(net, torch.zeros(shape(), device=p0.device), onnx, input_names=["x"],
                          output_names=["logits"], opset_version=17, dynamo=False)
    finally:
        if was_half:
            net.half()
    trt_engine.build_engine(onnx, path, fp16=True, workspace_mb=512, opt_level=BUILD_OPT_LEVEL)
    return path


def start_build(weights: str) -> bool:
    """Build the engine in a background child process (once per box: a lock file); False if not started."""
    import subprocess
    import sys
    path = engine_path(weights)
    lock = path + ".building"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(lock) and (time.time() - os.path.getmtime(lock)) < BUILD_TIMEOUT_S:
            return False                                # another process is building it
        with open(lock, "w") as fh:
            fh.write(str(os.getpid()))
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
        subprocess.Popen([sys.executable, "-m", "cn_pkg.starseg_trt", "--weights", weights, "--lock", lock],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as e:
        logger.warning("starseg_trt: cannot start the engine build: %s", e)
        return False


class Engine:
    """Callable on a CUDA tensor of exactly shape() -> logits (engine dtype)."""

    def __init__(self, path: str):
        from navera_common import trt_engine
        self.eng = trt_engine.TrtEngine(path)

    def __call__(self, x):
        if tuple(x.shape) != shape():
            raise ValueError(f"unexpected input shape {tuple(x.shape)}")
        return self.eng(x=x)["logits"]


class Loader:
    """The engine for these weights: loaded if cached, else built in the background at first use (torch fp16
    meanwhile) and picked up by a later get() once it is there. get() -> Engine or None (-> torch)."""

    def __init__(self, weights: str):
        self.weights, self.engine, self.dead = weights, None, False
        self.enabled = os.environ.get("NAVERA_STARSEG_TRT", "1") != "0"
        self._next_check = 0.0
        self._started = False

    def get(self):
        if self.engine is not None or self.dead or not self.enabled or time.time() < self._next_check:
            return self.engine
        self._next_check = time.time() + 10.0
        try:
            from navera_common import trt_engine
            if trt_engine.import_tensorrt() is None:
                self.dead = True
                return None
            path = engine_path(self.weights)
            if os.path.exists(path):
                self.engine = Engine(path)
            elif not self._started:
                self._started = start_build(self.weights) or True
        except Exception as e:                          # noqa: BLE001 - any failure: torch fallback
            logger.warning("starseg_trt: %s: torch fp16", e)
            self.dead = True
        return self.engine

    def failed(self):
        """The engine raised: torch from now on."""
        self.engine, self.dead = None, True


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="build the star-segmentation TensorRT engine on this box")
    ap.add_argument("--weights", default=None)
    ap.add_argument("--lock", default=None, help="(internal) lock file to remove when done")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    from cn_pkg import starseg
    w = a.weights or starseg.WEIGHTS
    os.environ["NAVERA_STARSEG_TRT"] = "0"              # build explicitly below
    m = starseg.StarSeg(w)
    try:
        p = build(m.net, w)
    finally:
        if a.lock and os.path.exists(a.lock):
            os.remove(a.lock)
    print(p or "no engine (torch fp16 is used)")
    return 0 if p else 1


if __name__ == "__main__":
    raise SystemExit(main())
