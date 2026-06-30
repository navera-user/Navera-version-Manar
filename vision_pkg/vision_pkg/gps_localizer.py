#!/usr/bin/env python3
"""
gps_localizer.py ── OPTIMIZED v4 (Vectorized Matmul + Windowed Search)
════════════════════════════════════════════════════════════════════════
Changements v4 vs v3 :
  ✅ numpy matmul au lieu de sklearn.cosine_similarity (10× plus rapide)
  ✅ Fenêtre glissante [-WINDOW_BEFORE, +WINDOW_AFTER] autour d'une ancre
  ✅ localize_bytes() : matching direct depuis bytes RAM (zéro disk I/O)
  ✅ Descripteurs pré-normalisés L2 au startup (zéro normalisation runtime)
  ✅ Two-stage : NetVLAD matmul sur fenêtre → top-K → DINOv2 matmul
  ✅ Early-exit si score NetVLAD >= CONF_THRESH (skip DINOv2)
  ✅ API publique IDENTIQUE a v3 (predict_gps_cached, predict_gps, etc.)
"""
import os
import sys
import time
import math
import threading
import ctypes
import ctypes.util
from pathlib import Path

# GPU: Inject ai_env AVANT torch
# Cherche ai_env dans le home ou à côté du projet — non bloquant si absent
for _candidate in [
    os.path.expanduser("~/pfeAutonomTest/ai_env/lib/python3.12/site-packages"),
    os.path.expanduser("~/Desktop/pfeAutonomTest/ai_env/lib/python3.12/site-packages"),
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "cosplace_repo"),
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "cosplace_repo"),
]:
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)
        break

import cv2

# Persist model downloads across container restarts.
MODEL_CACHE_DIR = Path(os.environ.get("NAVERA_MODEL_CACHE", "/workspaces/isaac_ros-dev/model_cache"))
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["TORCH_HOME"] = str(MODEL_CACHE_DIR)
os.environ["TORCH_HUB_DIR"] = str(MODEL_CACHE_DIR)

import torch
import timm
import numpy as np
import pandas as pd
import torch.nn as nn
from concurrent.futures import ThreadPoolExecutor
from torchvision import transforms
try:
    from cosplace_model.cosplace_network import GeoLocalizationNet
    _COSPLACE_AVAILABLE = True
except ImportError:
    _COSPLACE_AVAILABLE = False

try:
    import torch_tensorrt
    _TORCH_TRT_AVAILABLE = True
except Exception:
    _TORCH_TRT_AVAILABLE = False

try:
    import tensorrt as trt
    _TENSORRT_AVAILABLE = True
except Exception:
    _TENSORRT_AVAILABLE = False

_CUDART_LIB = ctypes.util.find_library('cudart')
_CUDART_AVAILABLE = _CUDART_LIB is not None

TRT_MODEL_DIR = Path(__file__).resolve().parent / "trt_models"
TRT_MODEL_DIR.mkdir(parents=True, exist_ok=True)

try:
    torch.hub.set_dir(str(MODEL_CACHE_DIR))
except Exception:
    pass


def _has_torch_tensorrt() -> bool:
    return _TORCH_TRT_AVAILABLE and torch.cuda.is_available()


def _has_native_tensorrt() -> bool:
    return _TENSORRT_AVAILABLE and _CUDART_AVAILABLE and torch.cuda.is_available()


def _onnx_export_path(name: str) -> Path:
    return TRT_MODEL_DIR / f"{name}.onnx"


def _engine_path(name: str) -> Path:
    return TRT_MODEL_DIR / f"{name}.engine"


def _script_path(name: str) -> Path:
    return TRT_MODEL_DIR / f"{name}_trt.ts"


def _export_to_onnx(model: nn.Module, dummy: torch.Tensor, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    traced = torch.jit.trace(model, dummy)
    torch.onnx.export(
        traced,
        dummy,
        str(path),
        export_params=True,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        opset_version=17,
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    return path


def _build_trt_engine(onnx_path: Path, engine_path: Path, fp16: bool = True):
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    with open(str(onnx_path), "rb") as f:
        if not parser.parse(f.read()):
            raise RuntimeError(f"ONNX parse failed: {onnx_path}")

    config = builder.create_builder_config()
    config.max_workspace_size = 1 << 30
    if fp16 and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)

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


def _load_trt_engine(engine_path: Path):
    runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
    with open(str(engine_path), "rb") as f:
        engine = runtime.deserialize_cuda_engine(f.read())
    if engine is None:
        raise RuntimeError(f"Failed to deserialize TensorRT engine: {engine_path}")
    return engine


class _TensorRTModuleWrapper:
    def __init__(self, inferer):
        self._inferer = inferer

    def __call__(self, x):
        if isinstance(x, torch.Tensor):
            x = x.detach().cpu().numpy()
        out = self._inferer.infer(x)
        return torch.from_numpy(out)


class _TensorRTInferer:
    def __init__(self, engine):
        self.engine = engine
        self.context = engine.create_execution_context()
        self._cudart = ctypes.CDLL(_CUDART_LIB)
        self._setup_cuda()
        self.bindings = [None] * engine.num_bindings
        self._device_ptrs = []
        self._binding_info = []
        for idx in range(engine.num_bindings):
            shape = tuple(engine.get_binding_shape(idx))
            if any(d <= 0 for d in shape):
                raise RuntimeError("TensorRT dynamic binding shapes are not supported in this wrapper")
            dtype = trt.nptype(engine.get_binding_dtype(idx))
            nbytes = int(np.prod(shape)) * np.dtype(dtype).itemsize
            ptr = self._cuda_malloc(nbytes)
            self._device_ptrs.append(ptr)
            self.bindings[idx] = int(ptr)
            self._binding_info.append({"shape": shape, "dtype": dtype, "nbytes": nbytes})
        self._input_idx = next(i for i in range(engine.num_bindings) if engine.binding_is_input(i))
        self._output_idx = next(i for i in range(engine.num_bindings) if not engine.binding_is_input(i))

    def _setup_cuda(self):
        self._cudart.cudaMalloc.restype = ctypes.c_int
        self._cudart.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self._cudart.cudaFree.restype = ctypes.c_int
        self._cudart.cudaFree.argtypes = [ctypes.c_void_p]
        self._cudart.cudaMemcpy.restype = ctypes.c_int
        self._cudart.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]

    def _cuda_malloc(self, size):
        ptr = ctypes.c_void_p()
        err = self._cudart.cudaMalloc(ctypes.byref(ptr), size)
        if err != 0:
            raise RuntimeError(f"cudaMalloc failed with code {err}")
        return ptr

    def _cuda_memcpy(self, dst, src, size, kind):
        err = self._cudart.cudaMemcpy(ctypes.c_void_p(dst), ctypes.c_void_p(src), size, kind)
        if err != 0:
            raise RuntimeError(f"cudaMemcpy failed with code {err}")

    def infer(self, x):
        if isinstance(x, torch.Tensor):
            x = x.detach().cpu().numpy()
        x = np.ascontiguousarray(x.astype(np.float32))
        info = self._binding_info[self._input_idx]
        if x.nbytes != info["nbytes"]:
            raise RuntimeError(f"Input size mismatch: expected {info['nbytes']} bytes, got {x.nbytes}")
        self._cuda_memcpy(self._device_ptrs[self._input_idx], x.ctypes.data, x.nbytes, 1)
        self.context.execute_v2(self.bindings)
        out_info = self._binding_info[self._output_idx]
        output = np.empty(out_info["shape"], dtype=out_info["dtype"])
        self._cuda_memcpy(output.ctypes.data, self._device_ptrs[self._output_idx], output.nbytes, 2)
        return output


def _compile_torchtrt_module(model: nn.Module, name: str):
    if not _TORCH_TRT_AVAILABLE:
        return None
    trt_path = _script_path(name)
    if trt_path.exists():
        return torch.jit.load(str(trt_path)).eval()

    model = model.eval().to("cuda")
    dummy = torch.randn(1, 3, 224, 224).to("cuda")
    trt_module = torch_tensorrt.compile(
        model,
        inputs=[torch_tensorrt.Input(dummy.shape, dtype=torch.float16)],
        enabled_precisions={torch.half},
    )
    torch.jit.save(trt_module, str(trt_path))
    return trt_module


def _load_tensorrt_model(name: str, model: nn.Module):
    engine_path = _engine_path(name)
    onnx_path = _onnx_export_path(name)
    if engine_path.exists():
        engine = _load_trt_engine(engine_path)
        return _TensorRTModuleWrapper(_TensorRTInferer(engine))

    if not _TENSORRT_AVAILABLE or not _CUDART_AVAILABLE:
        return None

    dummy = torch.randn(1, 3, 224, 224).to("cuda")
    _export_to_onnx(model.to("cuda"), dummy, onnx_path)
    engine = _build_trt_engine(onnx_path, engine_path, fp16=True)
    return _TensorRTModuleWrapper(_TensorRTInferer(engine))

# ── Chemins hardcodes ─────────────────────────────────────────────────────────
# Chemins résolus dynamiquement depuis l'emplacement de ce fichier
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASET_DIR  = os.path.join(_THIS_DIR, "dataset")
FALLBACK_DATASET_DIR = os.path.join(_THIS_DIR, "dataset", "precollected")

# ── Config matching ───────────────────────────────────────────────────────────
WINDOW_BEFORE  = 500
WINDOW_AFTER   = 700
TOP_K          = 5
MIN_SCORE      = 0.40
CONF_THRESH_NV = 0.95   # early-exit NetVLAD (skip DINOv2)

device = "cuda" if torch.cuda.is_available() else "cpu"
_GPU_NAME = torch.cuda.get_device_name(0).lower() if device == "cuda" else ""
_IS_JETSON = any(k in _GPU_NAME for k in ("orin", "xavier", "tegra", "nano"))
_USE_FP16 = device == "cuda"


def _is_unified_mem_error(exc: Exception) -> bool:
    msg = f"{type(exc).__name__}: {exc}".lower()
    needles = (
        "out of memory",
        "cuda out of memory",
        "nvmapmemallocinternaltagged",
        "nvml",
        "cudnn_status_alloc_failed",
    )
    return any(n in msg for n in needles)


if device == "cuda":
    gpu_props = torch.cuda.get_device_properties(0)
    print(f"  ✅ GPU: {torch.cuda.get_device_name(0)}")
    print(f"     Memory: {gpu_props.total_memory/1e9:.1f}GB | "
          f"Cores: {gpu_props.multi_processor_count} | "
          f"Compute Capability: {gpu_props.major}.{gpu_props.minor}")
    if _IS_JETSON:
        print("     Platform: Jetson (iGPU unified memory)")
    torch.backends.cudnn.benchmark = True
else:
    print(f"  ⚠️ CPU MODE")

transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


# ── Models (identiques a v3 pour compatibilite cache) ────────────────────────
class GeM(nn.Module):
    def __init__(self, p=3.0, eps=1e-6):
        super().__init__()
        self.p   = nn.Parameter(torch.ones(1) * p)
        self.eps = eps

    def forward(self, x):
        return x.clamp(min=self.eps).pow(self.p).mean((-2, -1)).pow(1. / self.p)


class CosPlace(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = timm.create_model("resnet50", pretrained=True, features_only=True)
        dim = self.backbone.feature_info[-1]['num_chs']
        self.pool = GeM()

    def forward(self, x):
        features = self.backbone(x)[-1]
        return torch.nn.functional.normalize(self.pool(features), p=2, dim=1)

# ── Models (identiques a v3 pour compatibilite cache) ────────────────────────
# ── Models (identiques a v3 pour compatibilite cache) ────────────────────────
class DINOv2GeM(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = torch.hub.load(
            "facebookresearch/dinov2", "dinov2_vits14", pretrained=True)
        self.gem = GeM()

    def forward(self, x):
        out     = self.backbone.get_intermediate_layers(x, n=1)[0]
        B, N, C = out.shape
        H = W   = int(N ** 0.5)
        out     = self.gem(out.reshape(B, H, W, C).permute(0, 3, 1, 2))
        return torch.nn.functional.normalize(out, p=2, dim=1)
_localizer   = None
_dataset_dir = None
_lock        = threading.Lock()


def _get_localizer(dataset_dir: str) -> '_VisualLocalizer':
    global _localizer, _dataset_dir
    csv_path  = os.path.join(dataset_dir, "metadata.csv")
    csv_mtime = os.path.getmtime(csv_path) if os.path.exists(csv_path) else 0
    with _lock:
        if (_localizer is None or
                _dataset_dir != dataset_dir or
                _localizer.csv_mtime != csv_mtime):
            if _localizer:
                print(f"  Dataset change — Rechargement...")
            _localizer   = _VisualLocalizer(dataset_dir)
            _dataset_dir = dataset_dir
    return _localizer


class _VisualLocalizer:
    """
    Localizer vectorise avec fenetre glissante.
    Matrices descripteurs en RAM, L2-normalisees au startup.
    """

    def __init__(self, dataset_dir: str, max_images: int = None):
        self.dataset_dir = Path(dataset_dir)
        self.images_dir  = self.dataset_dir / "images"
        self.csv_path    = self.dataset_dir / "metadata.csv"
        self.csv_mtime   = (os.path.getmtime(str(self.csv_path))
                            if self.csv_path.exists() else 0)

        if not self.csv_path.exists():
            raise FileNotFoundError(f"metadata.csv introuvable: {dataset_dir}")

        self.df = pd.read_csv(str(self.csv_path))
        
        # Dynamically set max_images based on available GPU memory
        if max_images is None:
            try:
                if torch.cuda.is_available():
                    total_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
                    # Conservative estimate: 200MB per 1000 images
                    max_images = min(100000, int(total_mem * 5000))
                else:
                    max_images = 50000  # CPU: reasonable limit
            except:
                max_images = 100000
        
        self.max_images = max_images
        total_available = len(self.df)
        print(f"  [Localizer] Max images: {self.max_images} (available: {total_available})")

        print(f"  Chargement modeles...")
        if torch.cuda.is_available():
            torch.backends.cudnn.benchmark = True
        self._pre_build_trt_engines()
        self.netvlad_model = None
        self.dinov2_model  = None

        if device == "cuda":
            if _has_torch_tensorrt():
                try:
                    print("  TensorRT: torch_tensorrt disponible — compilation GPU")
                    self.netvlad_model = _compile_torchtrt_module(CosPlace(), "netvlad")
                    self.dinov2_model  = _compile_torchtrt_module(DINOv2GeM(), "dino")
                except Exception as e:
                    print(f"  TensorRT torch_tensorrt echec: {e} — fallback PyTorch")
            elif _has_native_tensorrt():
                try:
                    print("  TensorRT: native ONNX → engine disponible")
                    self.netvlad_model = _load_tensorrt_model("netvlad", CosPlace())
                    self.dinov2_model  = _load_tensorrt_model("dino", DINOv2GeM())
                except Exception as e:
                    print(f"  TensorRT native echec: {e} — fallback PyTorch")
            else:
                print("  TensorRT non disponible, fallback PyTorch")

        if self.netvlad_model is None:
            self.netvlad_model = CosPlace().to(device).eval()
        if self.dinov2_model is None:
            self.dinov2_model  = DINOv2GeM().to(device).eval()

        # Use fp16 on CUDA to reduce unified-memory pressure on Jetson.
        if _USE_FP16:
            print("  [Memory] Converting models to fp16...")
            self.netvlad_model = self.netvlad_model.half()
            self.dinov2_model = self.dinov2_model.half()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                allocated = torch.cuda.memory_allocated(device) / 1e9
                reserved = torch.cuda.memory_reserved(device) / 1e9
                print(f"  [Memory] GPU: {allocated:.2f}GB allocated, {reserved:.2f}GB reserved")

        # Warmup GPU
        if device == "cuda":
            warmup_dtype = torch.float16 if _USE_FP16 else torch.float32
            dummy = torch.randn(1, 3, 224, 224, device=device, dtype=warmup_dtype)
            with torch.no_grad():
                _ = self.netvlad_model(dummy)
                _ = self.dinov2_model(dummy)
        print(f"  GPU warmup OK")
        print(f"🔥 Using TensorRT NetVLAD: {isinstance(self.netvlad_model, _TensorRTModuleWrapper)}")
        print(f"🔥 Using TensorRT DINO: {isinstance(self.dinov2_model, _TensorRTModuleWrapper)}")

        cache_path = self.dataset_dir / "descriptors_cache.npz"
        self._load_or_build_cache(cache_path)

    def _load_or_build_cache(self, cache_path: Path):
        rebuild = not cache_path.exists()
        if not rebuild:
            try:
                cache = np.load(str(cache_path), allow_pickle=True)
                nv_raw   = cache["netvlad"].astype(np.float32)
                dino_raw = cache["dino"].astype(np.float32)
                self.coords    = cache["coords"].astype(np.float64)
                self.filenames = list(cache["filenames"])

                # L2-normaliser une fois -> dot product = cosine similarity
                def _norm_matrix(m):
                    n = np.linalg.norm(m, axis=1, keepdims=True)
                    n[n == 0] = 1e-8
                    return m / n

                self.nv_matrix   = _norm_matrix(nv_raw)
                self.dino_matrix = _norm_matrix(dino_raw)
                N = len(self.filenames)
                ram_mb = (self.nv_matrix.nbytes + self.dino_matrix.nbytes) / 1e6
                print(f"  Cache charge: {N} images | "
                      f"NV={self.nv_matrix.shape[1]}D | "
                      f"DINO={self.dino_matrix.shape[1]}D | "
                      f"RAM={ram_mb:.0f}MB")
                return
            except Exception as e:
                print(f"  Cache corrompu: {e} — rebuild")

        self._index_dataset(cache_path)

    def _index_dataset(self, cache_path: Path):
        """
        Indexation OPTIMISÉE v5 : GPU rapide, I/O parallèle, checkpoints
        ════════════════════════════════════════════════════════════════
        
        Optimisations :
          ✅ Batch dynamique : GPU 128-256 | CPU 32
          ✅ Chargement I/O parallèle (ThreadPoolExecutor)
          ✅ GPU memory monitoring + checkpoint toutes les 2000 images
          ✅ Progress logging détaillé par chunk
          ✅ Timeout/watchdog pour détecter blocages
          ✅ np.savez() GARANTI après chaque checkpoint + final
        """
        import os as _os
        import queue
        from threading import Thread, Event
        
        # Détection GPU capabilities
        has_cuda = device == "cuda"
        if has_cuda:
            BATCH_SIZE = 1 if _IS_JETSON else (8 if _USE_FP16 else 4)
        else:
            BATCH_SIZE = 16
        USE_AMP = has_cuda and _USE_FP16
        CHECKPOINT_EVERY = 2000  # Sauvegarder tous les 2000 images
        N_LOAD_WORKERS = min(12, _os.cpu_count() or 4)  # Plus de workers pour I/O
        LOAD_QUEUE_SIZE = BATCH_SIZE * 4  # Prefetch 4 batches ahead
        TIMEOUT_PER_BATCH = 60  # 60s timeout per batch
        
        # CPU optimization
        if not has_cuda:
            torch.set_num_threads(_os.cpu_count() or 4)
        
        # Column detection
        lat_col = "center_lat" if "center_lat" in self.df.columns else "lat"
        lon_col = "center_lon" if "center_lon" in self.df.columns else "lon"
        fn_col  = "filename"   if "filename"   in self.df.columns else "image_path"
        
        # Find valid rows
        valid_rows = []
        if self.images_dir.exists():
            valid_rows = [
                row for _, row in self.df.iterrows()
                if (self.images_dir / row[fn_col]).exists()
            ]
        
        # Respect max_images limit
        if len(valid_rows) > self.max_images:
            valid_rows = valid_rows[:self.max_images]
            print(f"  [LIMIT] {len(valid_rows)}/{len(self.df)} images (max_images={self.max_images})")
        
        total = len(valid_rows)
        if total == 0:
            self.nv_matrix   = np.zeros((0, 131072), dtype=np.float32)
            self.dino_matrix = np.zeros((0, 384),    dtype=np.float32)
            self.coords      = np.zeros((0, 2),      dtype=np.float64)
            self.filenames   = []
            print("  ⚠️ No valid images found")
            return
        
        print(f"  🚀 Indexing {total} images on {device.upper()}")
        print(f"     Batch: {BATCH_SIZE} | Workers: {N_LOAD_WORKERS} | "
              f"Checkpoint every {CHECKPOINT_EVERY} imgs")
        
        t0 = time.time()
        nv_list, dino_list, coords_list, fn_list = [], [], [], []
        last_save_count = 0
        
        # Checkpoint file (for resume capability)
        checkpoint_path = cache_path.with_stem(cache_path.stem + "_checkpoint")
        
        def _load_image(row):
            """Load + transform image (runs in ThreadPoolExecutor)."""
            try:
                img = cv2.imread(str(self.images_dir / row[fn_col]))
                if img is not None:
                    return (transform(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)),
                            float(row[lat_col]), float(row[lon_col]), row[fn_col])
            except Exception as e:
                pass
            return None
        
        def _save_checkpoint(nv, dino, coords, fns, checkpoint_file):
            """Safe checkpoint save."""
            try:
                np.savez(str(checkpoint_file),
                         netvlad=nv, dino=dino,
                         coords=coords, filenames=np.array(fns))
                return True
            except Exception as e:
                print(f"  ❌ Checkpoint save failed: {e}")
                return False
        
        # GPU memory monitoring
        def _log_gpu_stats():
            if not has_cuda:
                return ""
            try:
                allocated = torch.cuda.memory_allocated(0) / 1e9
                reserved = torch.cuda.memory_reserved(0) / 1e9
                return f" | GPU: {allocated:.1f}G/{reserved:.1f}G"
            except:
                return ""
        
        # Main indexing loop with timeout protection
        try:
            with torch.no_grad():
                for chunk_idx, bs in enumerate(range(0, total, BATCH_SIZE)):
                    chunk_start = time.time()
                    batch_rows = valid_rows[bs:bs + BATCH_SIZE]
                    
                    # Parallel image loading
                    with ThreadPoolExecutor(max_workers=N_LOAD_WORKERS) as pool:
                        loaded_items = list(pool.map(_load_image, batch_rows))
                    
                    # Build batch
                    batch_tensors, batch_coords, batch_fns = [], [], []
                    for item in loaded_items:
                        if item is not None:
                            t, lat, lon, fn = item
                            batch_tensors.append(t)
                            batch_coords.append([lat, lon])
                            batch_fns.append(fn)
                    
                    if not batch_tensors:
                        print(f"  ⚠️ Chunk {chunk_idx}: no valid images")
                        continue
                    
                    try:
                        batch = torch.stack(batch_tensors).to(device, non_blocking=has_cuda)
                        if USE_AMP:
                            with torch.amp.autocast('cuda'):
                                nv_out   = self.netvlad_model(batch).cpu().detach().numpy()
                                dino_out = self.dinov2_model(batch).cpu().detach().numpy()
                        else:
                            nv_out   = self.netvlad_model(batch).cpu().detach().numpy()
                            dino_out = self.dinov2_model(batch).cpu().detach().numpy()
                        
                        nv_list.extend(nv_out)
                        dino_list.extend(dino_out)
                        coords_list.extend(batch_coords)
                        fn_list.extend(batch_fns)
                        del batch
                        torch.cuda.empty_cache() if has_cuda else None
                    except Exception as e:
                        print(f"  ❌ Inference error chunk {chunk_idx}: {e}")
                        raise
                    
                    # Progress logging per chunk
                    processed = len(nv_list)
                    elapsed_s = time.time() - t0
                    rate = processed / elapsed_s if elapsed_s > 0 else 0
                    eta_s = (total - processed) / max(rate, 0.1)
                    gpu_stat = _log_gpu_stats()
                    print(f"  Chunk {chunk_idx:3d} | [{processed:>6}/{total}] "
                          f"{rate:.1f} img/s | ETA {eta_s:.0f}s{gpu_stat}")
                    
                    # Periodic checkpoint (resume capability)
                    if processed - last_save_count >= CHECKPOINT_EVERY:
                        nv_arr = np.array(nv_list, dtype=np.float32)
                        dino_arr = np.array(dino_list, dtype=np.float32)
                        if _save_checkpoint(nv_arr, dino_arr, 
                                          np.array(coords_list, dtype=np.float64),
                                          fn_list, checkpoint_path):
                            print(f"    💾 Checkpoint saved: {processed} images")
                        last_save_count = processed
        
        except KeyboardInterrupt:
            print(f"  ⏸️ Interrupted by user at {len(nv_list)} images")
            raise
        except Exception as e:
            print(f"  ❌ Fatal indexing error: {e}")
            raise
        
        # FINAL SAVE: Always save the complete cache
        print(f"  ⏹️ Finalizing cache...")
        nv_raw   = np.array(nv_list,   dtype=np.float32)
        dino_raw = np.array(dino_list, dtype=np.float32)
        self.coords    = np.array(coords_list, dtype=np.float64)
        self.filenames = fn_list
        
        # Verify dimensions before save
        print(f"     NetVLAD shape: {nv_raw.shape} | DINO shape: {dino_raw.shape}")
        
        # CRITICAL: np.savez to cache_path
        try:
            np.savez(str(cache_path),
                     netvlad=nv_raw, dino=dino_raw,
                     coords=self.coords, filenames=np.array(fn_list))
            print(f"  ✅ Cache saved: {cache_path}")
            print(f"     File size: {cache_path.stat().st_size / 1e6:.1f} MB")
        except Exception as e:
            print(f"  ❌ CRITICAL: Cache save failed: {e}")
            raise
        
        # Cleanup checkpoint
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        
        # Normalize descriptors
        def _norm_matrix(m):
            n = np.linalg.norm(m, axis=1, keepdims=True)
            n[n == 0] = 1e-8
            return m / n
        
        self.nv_matrix   = _norm_matrix(nv_raw)
        self.dino_matrix = _norm_matrix(dino_raw)
        
        # Final statistics
        elapsed = time.time() - t0
        rate = total / elapsed if elapsed > 0 else 0
        print(f"  🎉 Indexing complete: {total} images in {elapsed:.1f}s ({rate:.1f} img/s)")
        print(f"     GPU: {device.upper()} | "
              f"RAM: {(self.nv_matrix.nbytes + self.dino_matrix.nbytes) / 1e6:.0f}MB")

    # ── Extraction query ──────────────────────────────────────────────────────

    def _extract_query(self, img_bgr: np.ndarray) -> tuple:
        """NetVLAD + DINOv2 en parallele sur 2 CUDA streams. Retourne L2-normalises.
        
        With OOM recovery: if CUDA out-of-memory occurs, clear cache and retry.
        CUDA context can enter broken state after OOM, so recovery is critical.
        """
        t0_extract = time.perf_counter()
        rgb    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        tensor = transform(rgb).unsqueeze(0).to(device)
        
        # Cast input to fp16 when models run in fp16.
        if _USE_FP16:
            tensor = tensor.half()

        nv_feat   = [None]
        dino_feat = [None]

        def _nv():
            with torch.no_grad():
                if device == "cuda":
                    with torch.amp.autocast('cuda'):
                        nv_feat[0] = self.netvlad_model(tensor).cpu().numpy()[0]
                else:
                    nv_feat[0] = self.netvlad_model(tensor).cpu().numpy()[0]

        def _dino():
            with torch.no_grad():
                if device == "cuda":
                    with torch.amp.autocast('cuda'):
                        dino_feat[0] = self.dinov2_model(tensor).cpu().numpy()[0]
                else:
                    dino_feat[0] = self.dinov2_model(tensor).cpu().numpy()[0]

        def _run_inference():
            if device == "cuda":
                s1, s2 = torch.cuda.Stream(), torch.cuda.Stream()
                with torch.cuda.stream(s1): _nv()
                with torch.cuda.stream(s2): _dino()
                torch.cuda.synchronize()
            else:
                _nv(); _dino()

        # OOM/Jetson unified-memory recovery: clear cache and retry.
        max_retries = 2
        for attempt in range(max_retries):
            try:
                _run_inference()
                break
            except Exception as e:
                if _is_unified_mem_error(e):
                    print(f"  ⚠️ CUDA OOM on attempt {attempt+1}/{max_retries}")
                    if device == "cuda" and attempt < max_retries - 1:
                        # Clear CUDA cache and reset context
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        time.sleep(0.1)  # Brief pause before retry
                        print(f"  🔄 CUDA cache cleared, retrying...")
                    else:
                        print(f"  ❌ OOM recovery failed after {max_retries} attempts")
                        raise
                else:
                    # Non-OOM error, don't retry
                    raise

        extract_ms = (time.perf_counter() - t0_extract) * 1000
        print(f"  ⏱️ Extract: NV+DI={extract_ms:.1f}ms")

        def _norm1(v):
            n = np.linalg.norm(v)
            return v / (n + 1e-8)

        return _norm1(nv_feat[0]), _norm1(dino_feat[0])

    def _pre_build_trt_engines(self):
        if not _has_native_tensorrt():
            return
        print("  Pre-building TensorRT engines...")
        # For netvlad
        engine_path = _engine_path("netvlad")
        onnx_path = _onnx_export_path("netvlad")
        if not engine_path.exists():
            model = CosPlace().to("cuda")
            _export_to_onnx(model, torch.randn(1, 3, 224, 224).to("cuda"), onnx_path)
            _build_trt_engine(onnx_path, engine_path, fp16=True)
        # For dino
        engine_path = _engine_path("dino")
        onnx_path = _onnx_export_path("dino")
        if not engine_path.exists():
            model = DINOv2GeM().to("cuda")
            _export_to_onnx(model, torch.randn(1, 3, 224, 224).to("cuda"), onnx_path)
            _build_trt_engine(onnx_path, engine_path, fp16=True)
        print("  TensorRT engines pre-built")

    # ── Core matching vectorise ───────────────────────────────────────────────

    def _match_radial(self, q_nv: np.ndarray, q_dino: np.ndarray,
                      ref_lat: float, ref_lon: float, radius_m: float) -> dict:
        """
        Recherche radiale : filtre par cercle R autour du dernier GPS valide,
        puis two-stage vectorisé sur le sous-ensemble.

        R = max(footprint×3, alt×2)  — calculé dans receive_frame()

        Stage 1 : CosPlace matmul sur le sous-ensemble  → Top-K
        Stage 2 : DINOv2 matmul sur Top-K              → best

        100x plus rapide que la fenêtre glissante : ~30-150 images au lieu de 1200.
        """
        N = len(self.nv_matrix)
        if N == 0:
            return {"success": False}

        # ── Filtre bbox carré (vectorisé numpy, O(N)) ────────────────────
        delta_lat = radius_m / 111_000.0
        delta_lon = radius_m / (111_000.0 * math.cos(math.radians(ref_lat)) + 1e-9)

        lat_arr = self.coords[:, 0]
        lon_arr = self.coords[:, 1]

        bbox_mask = (
            (lat_arr >= ref_lat - delta_lat) &
            (lat_arr <= ref_lat + delta_lat) &
            (lon_arr >= ref_lon - delta_lon) &
            (lon_arr <= ref_lon + delta_lon)
        )
        candidate_idxs = np.where(bbox_mask)[0]

        # ── Filtre cercle exact ──────────────────────────────────────────
        if len(candidate_idxs) > 0:
            clat = self.coords[candidate_idxs, 0]
            clon = self.coords[candidate_idxs, 1]
            dlat = np.radians(clat - ref_lat)
            dlon = np.radians(clon - ref_lon)
            cos_ref = math.cos(math.radians(ref_lat))
            dists   = 6_371_000.0 * np.sqrt(dlat**2 + (cos_ref * dlon)**2)
            circle_mask    = dists <= radius_m
            candidate_idxs = candidate_idxs[circle_mask]

        W = len(candidate_idxs)

        # Fallback : si aucune image dans le rayon, prendre les 50 plus proches
        if W == 0:
            dlat2 = np.radians(lat_arr - ref_lat)
            dlon2 = np.radians(lon_arr - ref_lon)
            cos_ref = math.cos(math.radians(ref_lat))
            dists_all = 6_371_000.0 * np.sqrt(dlat2**2 + (cos_ref * dlon2)**2)
            candidate_idxs = np.argsort(dists_all)[:50]
            W = len(candidate_idxs)
            print(f"  [RadialSearch] Fallback 50 nearest (R={radius_m:.0f}m hors dataset)")

        # ── Stage 1 : CosPlace matmul sur sous-ensemble ──────────────────
        subset_nv  = self.nv_matrix[candidate_idxs]   # (W, D_nv)
        nv_scores  = subset_nv @ q_nv                 # (W,)

        best_local_nv = int(np.argmax(nv_scores))
        best_nv_score = float(nv_scores[best_local_nv])

        # Early-exit haute confiance CosPlace
        if best_nv_score >= CONF_THRESH_NV:
            best_row = int(candidate_idxs[best_local_nv])
            return self._build_result(best_row, best_nv_score, W, "nv_early_exit")

        # ── Stage 2 : DINOv2 matmul sur Top-K ───────────────────────────
        k         = min(TOP_K, W)
        top_k_loc = np.argpartition(nv_scores, -k)[-k:]
        top_k_rows = candidate_idxs[top_k_loc]

        subset_dino  = self.dino_matrix[top_k_rows]   # (K, D_dino)
        dino_scores  = subset_dino @ q_dino            # (K,)
        best_local   = int(np.argmax(dino_scores))
        best_score   = float(dino_scores[best_local])

        if best_score < MIN_SCORE:
            return {"success": False, "n_searched": W}

        best_row = int(top_k_rows[best_local])
        return self._build_result(best_row, best_score, W, "two_stage_radial")

    def _match_windowed(self, q_nv: np.ndarray, q_dino: np.ndarray,
                        anchor_row: int) -> dict:
        """Fenêtre glissante — conservé pour compatibilité. Utiliser _match_radial."""
        N = len(self.nv_matrix)
        if N == 0:
            return {"success": False}
        r_start = max(0, anchor_row - WINDOW_BEFORE)
        r_end   = min(N, anchor_row + WINDOW_AFTER)
        win_nv  = self.nv_matrix[r_start:r_end]
        W = len(win_nv)
        if W == 0:
            return {"success": False}
        nv_scores     = win_nv @ q_nv
        best_local_nv = int(np.argmax(nv_scores))
        best_nv_score = float(nv_scores[best_local_nv])
        if best_nv_score >= CONF_THRESH_NV:
            return self._build_result(r_start + best_local_nv, best_nv_score, W, "nv_early_exit")
        k          = min(TOP_K, W)
        top_k_loc  = np.argpartition(nv_scores, -k)[-k:]
        top_k_rows = r_start + top_k_loc
        win_dino    = self.dino_matrix[top_k_rows]
        dino_scores = win_dino @ q_dino
        best_local  = int(np.argmax(dino_scores))
        best_score  = float(dino_scores[best_local])
        if best_score < MIN_SCORE:
            return {"success": False, "n_searched": W}
        return self._build_result(int(top_k_rows[best_local]), best_score, W, "two_stage")

    def _build_result(self, row: int, score: float, n_searched: int, method: str) -> dict:
        return {
            "success":    True,
            "lat":        float(self.coords[row][0]),
            "lon":        float(self.coords[row][1]),
            "score":      score,
            "match":      self.filenames[row] if row < len(self.filenames) else "",
            "new_anchor": row,
            "n_searched": n_searched,
            "method":     method,
        }

    def anchor_from_gps(self, lat: float, lon: float) -> int:
        if len(self.coords) == 0:
            return 0
        dlat = np.radians(self.coords[:, 0] - lat)
        dlon = np.radians(self.coords[:, 1] - lon)
        clat = math.cos(math.radians(lat))
        d2   = dlat**2 + (clat * dlon)**2
        return int(np.argmin(d2))

    def find_closest_index(self, lat: float, lon: float) -> int:
        """Alias de anchor_from_gps — utilisé par vision_node.py."""
        return self.anchor_from_gps(lat, lon)

    # ── API publique ──────────────────────────────────────────────────────────

    def localize_bytes(self, img_bytes: bytes, anchor_row: int = -1,
                       ref_lat: float = None, ref_lon: float = None,
                       radius_m: float = None) -> dict:
        """
        Matching depuis bytes RAM — zéro disk I/O. Utilisée par receiver.py.

        Si ref_lat/ref_lon/radius_m fournis → recherche radiale (recommandé).
        Sinon → fenêtre glissante (fallback compatibilité).
        
        With OOM error handling: if inference fails after recovery attempts,
        returns failure dict so prediction chain can continue with fallback.
        """
        t0 = time.perf_counter()
        arr     = np.frombuffer(img_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return {"success": False, "error": "decode_failed"}
        
        try:
            q_nv, q_dino = self._extract_query(img_bgr)
        except Exception as e:
            # Inference failed even after retry/recovery path.
            error_msg = str(e)
            if _is_unified_mem_error(e):
                print(f"  ❌ Inference failed: CUDA OOM unrecoverable")
                return {"success": False, "error": "cuda_oom_unrecoverable"}
            else:
                print(f"  ❌ Inference failed: {error_msg}")
                return {"success": False, "error": f"inference_failed: {error_msg}"}

        if ref_lat is not None and ref_lon is not None and radius_m is not None:
            result = self._match_radial(q_nv, q_dino, ref_lat, ref_lon, radius_m)
        else:
            if anchor_row < 0:
                anchor_row = len(self.nv_matrix) // 2
            result = self._match_windowed(q_nv, q_dino, anchor_row)

        result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return result

    def localize(self, query_path: str) -> dict:
        """API compatible v3."""
        with open(query_path, "rb") as f:
            img_bytes = f.read()
        result = self.localize_bytes(img_bytes, anchor_row=len(self.nv_matrix) // 2)
        if result.get("success"):
            return {"lat": result["lat"], "lon": result["lon"],
                    "score": result["score"], "match": result["match"]}
        return {"lat": 0.0, "lon": 0.0, "score": 0.0, "match": ""}


# ── API publique (compatible v3) ──────────────────────────────────────────────

def predict_gps(image_path: str, dataset_dir: str = None) -> dict:
    if dataset_dir is None:
        dataset_dir = DEFAULT_DATASET_DIR
        if not (Path(dataset_dir) / "metadata.csv").exists():
            dataset_dir = FALLBACK_DATASET_DIR
    try:
        return _get_localizer(dataset_dir).localize(image_path)
    except Exception as e:
        print(f"[gps_localizer] Erreur: {e}")
        return None


def predict_gps_cached(image_path: str, dataset_dir: str = None) -> dict:
    if dataset_dir is None:
        dataset_dir = DEFAULT_DATASET_DIR
        if not (Path(dataset_dir) / "metadata.csv").exists():
            dataset_dir = FALLBACK_DATASET_DIR
    t = time.time()
    try:
        loc    = _get_localizer(dataset_dir)
        result = loc.localize(image_path)
        result["cached"]      = True
        result["matching_ms"] = round((time.time() - t) * 1000)
        print(f"  Match: {result['matching_ms']}ms · score={result['score']:.3f}")
        return result
    except Exception as e:
        print(f"  Erreur: {e}")
        return predict_gps(image_path, dataset_dir)


def is_cache_ready(dataset_dir: str = None) -> bool:
    if dataset_dir is None:
        dataset_dir = DEFAULT_DATASET_DIR
    return ((Path(dataset_dir) / "descriptors_cache.npz").exists() and
            (Path(dataset_dir) / "metadata.csv").exists())


def precollect_dataset(lat, lon, alt_m, mbtiles_path, output_dir, progress_cb=None):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dataset_gen import generate_dataset
    t_start = time.time()
    result  = {"success": False}
    if progress_cb:
        progress_cb(0, 3, "Generation dataset MBTiles...")
    try:
        gen = generate_dataset(lat=lat, lon=lon, altitude_m=alt_m,
                               mbtiles_path=mbtiles_path,
                               output_dir=output_dir, verbose=True)
        if not gen.success:
            result["error"] = str(gen.error)
            return result
    except Exception as e:
        result["error"] = str(e)
        return result
    result["images"]     = gen.total_images
    result["dataset_ms"] = round((time.time() - t_start) * 1000)
    if progress_cb:
        progress_cb(1, 3, f"Dataset {gen.total_images} imgs · Indexing...")
    t_idx = time.time()
    try:
        _get_localizer(output_dir)
    except Exception as e:
        result["error"] = str(e)
        return result
    result["index_ms"]   = round((time.time() - t_idx) * 1000)
    result["total_ms"]   = round((time.time() - t_start) * 1000)
    result["cache_path"] = str(Path(output_dir) / "descriptors_cache.npz")
    result["success"]    = True
    if progress_cb:
        progress_cb(3, 3, "Cache pret ! Matching ~70ms")
    return result
