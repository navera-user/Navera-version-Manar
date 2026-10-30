"""TensorRT engines for NAVERA's networks: built once ON the Jetson from ONNX, cached, run on torch tensors.

An engine is specific to the GPU, the TensorRT version and the precision: it is built on the target
(navera_tools/trt/build_engines.py, a deployment step, minutes per network), never committed, and kept
under NAVERA_TRT_DIR (default ~/.navera_sim/trt/). A localizer that finds no engine (or no TensorRT)
runs its PyTorch path, as before.

Switch: NAVERA_TRT=1 forces the engines on, NAVERA_TRT=0 off; unset, each network uses its own
measured default (trt_enabled(default)).

TensorRT's Python bindings come from the JetPack package python3-libnvinfer; when it is not installed
system-wide, a copy unpacked under NAVERA_TRT_DIR/sdk/root (apt-get download + dpkg -x, no root) is used.
"""
import hashlib
import logging
import os
import sys
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

TRT_DIR = os.path.expanduser(os.environ.get("NAVERA_TRT_DIR", "~/.navera_sim/trt"))
_SDK_PY = os.path.join(TRT_DIR, "sdk", "root", "usr", "lib", "python3.10", "dist-packages")
_trt = None
_trt_tried = False


def trt_enabled(default: bool) -> bool:
    """NAVERA_TRT=1 / 0 forces TensorRT on / off; unset: `default` (the network's measured choice)."""
    v = os.environ.get("NAVERA_TRT", "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return bool(default)


def import_tensorrt():
    """The tensorrt module (system, else the unpacked SDK copy), or None."""
    global _trt, _trt_tried
    if _trt_tried:
        return _trt
    _trt_tried = True
    try:
        import tensorrt as trt
    except ImportError:
        if os.path.isdir(_SDK_PY) and _SDK_PY not in sys.path:
            sys.path.append(_SDK_PY)
        try:
            import tensorrt as trt
        except ImportError:
            return None
    _trt = trt
    return trt


def engine_path(name: str, onnx_path: str, fp16: bool) -> str:
    """Cache path of `name`'s engine for this ONNX file, precision and TensorRT version."""
    trt = import_tensorrt()
    with open(onnx_path, "rb") as f:
        h = hashlib.sha1(f.read()).hexdigest()[:10]
    ver = trt.__version__ if trt else "none"
    return os.path.join(TRT_DIR, f"{name}_{h}_{'fp16' if fp16 else 'fp32'}_trt{ver}.engine")


def find_engine(name: str, fp16: bool = True) -> Optional[str]:
    """The newest cached engine of `name` with that precision (built by build_engines.py), or None."""
    trt = import_tensorrt()
    if trt is None or not os.path.isdir(TRT_DIR):
        return None
    tag = f"_{'fp16' if fp16 else 'fp32'}_trt{trt.__version__}.engine"
    c = [os.path.join(TRT_DIR, f) for f in os.listdir(TRT_DIR) if f.startswith(name + "_") and f.endswith(tag)]
    return max(c, key=os.path.getmtime) if c else None


def build_engine(onnx_path: str, out_path: str, fp16: bool,
                 profile: Optional[Dict[str, Tuple[tuple, tuple, tuple]]] = None, workspace_mb: int = 1024,
                 opt_level: Optional[int] = None) -> str:
    """Build (minutes) and save an engine from an ONNX file; profile: input -> (min, opt, max) shapes;
    opt_level: TensorRT's builder optimisation level (default 3; lower builds faster)."""
    trt = import_tensorrt()
    if trt is None:
        raise RuntimeError("TensorRT Python bindings not found (python3-libnvinfer)")
    log = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(log)
    net = builder.create_network(0)
    parser = trt.OnnxParser(net, log)
    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            errors = "; ".join(str(parser.get_error(i)) for i in range(parser.num_errors))
            raise RuntimeError("ONNX parse failed: " + errors)
    cfg = builder.create_builder_config()
    cfg.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_mb << 20)
    if fp16:
        cfg.set_flag(trt.BuilderFlag.FP16)
    if opt_level is not None:
        cfg.builder_optimization_level = int(opt_level)
    if profile:
        p = builder.create_optimization_profile()
        for name, (mn, opt, mx) in profile.items():
            p.set_shape(name, mn, opt, mx)
        cfg.add_optimization_profile(p)
    blob = builder.build_serialized_network(net, cfg)
    if blob is None:
        raise RuntimeError(f"TensorRT build failed for {onnx_path}")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path + ".tmp", "wb") as f:
        f.write(blob)
    os.replace(out_path + ".tmp", out_path)
    return out_path


class TrtEngine:
    """One deserialised engine and its execution context, called with / returning torch CUDA tensors.

    Inputs are cast to the engine's input types and made contiguous; outputs are new tensors on the
    current device, written on the current torch stream. One call at a time (a lock).
    """

    def __init__(self, path: str):
        import torch
        trt = import_tensorrt()
        if trt is None:
            raise RuntimeError("TensorRT Python bindings not found (python3-libnvinfer)")
        self.path, self._torch, self._trt = path, torch, trt
        self._log = trt.Logger(trt.Logger.WARNING)
        with open(path, "rb") as f:
            self.engine = trt.Runtime(self._log).deserialize_cuda_engine(f.read())
        if self.engine is None:
            raise RuntimeError(f"cannot load TensorRT engine {path} (built for another TensorRT / GPU?)")
        self.ctx = self.engine.create_execution_context()
        names = [self.engine.get_tensor_name(i) for i in range(self.engine.num_io_tensors)]
        self.inputs = [n for n in names if self.engine.get_tensor_mode(n) == trt.TensorIOMode.INPUT]
        self.outputs = [n for n in names if self.engine.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT]
        dt = {trt.float32: torch.float32, trt.float16: torch.float16, trt.int32: torch.int32,
              trt.int64: torch.int64, trt.bool: torch.bool, trt.int8: torch.int8}
        self.dtype = {n: dt[self.engine.get_tensor_dtype(n)] for n in names}
        self._lock = threading.Lock()
        self._stream = None

    def __call__(self, **inputs) -> Dict[str, "object"]:
        torch = self._torch
        with self._lock:
            keep = []
            for n in self.inputs:
                x = inputs[n]
                x = x.to(dtype=self.dtype[n]).contiguous()
                keep.append(x)
                self.ctx.set_input_shape(n, tuple(x.shape))
                self.ctx.set_tensor_address(n, x.data_ptr())
            out = {}
            dev = keep[0].device
            for n in self.outputs:
                shape = tuple(self.ctx.get_tensor_shape(n))
                out[n] = torch.empty(shape, dtype=self.dtype[n], device=dev)
                self.ctx.set_tensor_address(n, out[n].data_ptr())
            # its own stream (TensorRT synchronises extra on the default one), ordered after the
            # current stream's work on the inputs and before its use of the outputs
            cur = torch.cuda.current_stream(dev)
            if self._stream is None:
                self._stream = torch.cuda.Stream(device=dev)
            self._stream.wait_stream(cur)
            if not self.ctx.execute_async_v3(self._stream.cuda_stream):
                raise RuntimeError(f"TensorRT execution failed ({os.path.basename(self.path)})")
            cur.wait_stream(self._stream)
            for x in keep + list(out.values()):
                x.record_stream(self._stream)
            return out
