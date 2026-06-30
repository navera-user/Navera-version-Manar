#!/usr/bin/env python3
"""
NAVERA — receiver_aonly.py  [OPTIMIZED v3]

Fixes appliqués :
  1. Cache modèles PERSISTANT → ResNet50 + DINOv2 téléchargés UNE SEULE FOIS
     dans /workspaces/isaac_ros-dev/model_cache (volume Docker monté sur host)
  2. NvMapMemAllocInternalTagged / NVML assert → batch=1 image par image
     (Jetson Orin Nano = iGPU mémoire unifiée, très sensible aux gros allocs)
  3. Précollecte bloquée à 95% → progress réel 0→70% (extract) + 70→100% (desc)
  4. Fallback CPU automatique si CUDA crash malgré tout
  5. Exception générale catchée dans load_models (pas seulement RuntimeError)
"""

import gc
import io
import csv
import json
import math
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from math import radians, degrees, cos, sin, tan, atan2, sqrt, asinh, atan, sinh
from pathlib import Path

# =============================================================================
# CHEMINS — définis AVANT les imports torch pour pouvoir set TORCH_HOME
# =============================================================================
BASE_DIR     = Path("/workspaces/isaac_ros-dev")
PKG_DIR      = BASE_DIR / "day_pkg" / "day_pkg"
MBTILES_PATH = BASE_DIR / "sousse_satellite.mbtiles"
FLIGHT_LOG   = BASE_DIR / "flight_log.csv"
GPS_STATUS   = BASE_DIR / "gps_status.json"
DATASET_DIR  = PKG_DIR  / "dataset_aonly"
IMAGES_DIR   = DATASET_DIR / "images"
CSV_PATH     = DATASET_DIR / "dataset.csv"
DESC_NPZ     = DATASET_DIR / "descriptors.npz"
CIRCLE_BASE  = PKG_DIR  / "circle_datasets"

# -----------------------------------------------------------------------------
# Cache modèles PERSISTANT
# /workspaces est un volume Docker bindmounté sur le host.
# ResNet50 (~98 MB) et DINOv2 (~330 MB) ne seront telecharges QU'UNE SEULE FOIS.
# Les lancements suivants liront directement depuis ce dossier.
# -----------------------------------------------------------------------------
MODEL_CACHE_DIR = BASE_DIR / "model_cache"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Ces variables d'env DOIVENT etre set AVANT "import torch"
os.environ["TORCH_HOME"]    = str(MODEL_CACHE_DIR)
os.environ["TORCH_HUB_DIR"] = str(MODEL_CACHE_DIR)
os.environ["HF_HOME"]       = str(MODEL_CACHE_DIR / "hf")

for d in [DATASET_DIR, IMAGES_DIR, CIRCLE_BASE]:
    d.mkdir(parents=True, exist_ok=True)

# =============================================================================
# IMPORTS (apres set env)
# =============================================================================
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as T
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image

# Double securite : forcer torch.hub a utiliser le cache persistant
torch.hub.set_dir(str(MODEL_CACHE_DIR))

# =============================================================================
# DEVICE
# =============================================================================
_device   = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_USE_FP16 = _device.type == "cuda"
_DTYPE    = torch.float16 if _USE_FP16 else torch.float32

print(f"[AONLY] CUDA={torch.cuda.is_available()} | "
      f"GPU={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
print(f"[AONLY] Precision={_DTYPE} | Device={_device}")
print(f"[AONLY] Model cache: {MODEL_CACHE_DIR}")

# =============================================================================
# ETAT GLOBAL
# =============================================================================
state = {
    "mission_alt_m":      400.0,
    "mission_zoom":       17,
    "point_a_lat":        None,
    "point_a_lon":        None,
    "last_known_lat":     None,
    "last_known_lon":     None,
    "last_pred_lat":      None,
    "last_pred_lon":      None,
    "precollect_running": False,
    "precollect_done":    0,
    "precollect_total":   0,
    "precollect_pct":     0,
    "precollect_phase":   "",
    "precollect_success": False,
    "precollect_error":   None,
    "nv_descs":           None,
    "dv_descs":           None,
    "coords":             None,
    "df_valid":           None,
    "cache_ready":        False,
    "matching_active":    False,
    "models_ready":       False,
}
_state_lock = threading.Lock()

# =============================================================================
# MODELES
# =============================================================================
_netvlad_model = None
_dino_model    = None


class NetVLAD(nn.Module):
    def __init__(self, num_clusters=32, dim=1024):
        super().__init__()
        self.num_clusters = num_clusters
        self.dim = dim
        self.conv = nn.Conv2d(dim, num_clusters, kernel_size=1, bias=False)
        self.centroids = nn.Parameter(torch.rand(num_clusters, dim))

    def forward(self, x):
        N, C, H, W = x.shape
        soft_assign = self.conv(x)
        soft_assign = F.softmax(soft_assign.view(N, self.num_clusters, -1), dim=2)
        x_flat = x.view(N, C, -1)
        vlad = torch.zeros(N, self.num_clusters, C, device=x.device, dtype=x.dtype)
        for k in range(self.num_clusters):
            residual = x_flat - self.centroids[k:k+1, :].unsqueeze(-1)
            vlad[:, k, :] = (soft_assign[:, k:k+1, :] * residual).sum(dim=-1)
        vlad = F.normalize(vlad, p=2, dim=2)
        vlad = vlad.view(N, -1)
        return F.normalize(vlad, p=2, dim=1)


class BackboneNetVLAD(nn.Module):
    """ResNet50 jusqu'a layer3 (1024-dim) + NetVLAD 32 clusters.
    layer3 au lieu de layer4 = 4x moins de VRAM que l'original."""
    def __init__(self):
        super().__init__()
        import torchvision.models as models
        resnet = models.resnet50(weights=models.ResNet50_Weights.DEFAULT)
        self.backbone = nn.Sequential(
            resnet.conv1, resnet.bn1, resnet.relu, resnet.maxpool,
            resnet.layer1, resnet.layer2, resnet.layer3
        )
        self.netvlad = NetVLAD(num_clusters=32, dim=1024)

    def forward(self, x):
        return self.netvlad(self.backbone(x))


class GeM(nn.Module):
    def __init__(self, p=3, eps=1e-6):
        super().__init__()
        self.p = nn.Parameter(torch.ones(1) * p)
        self.eps = eps

    def forward(self, x):
        return F.adaptive_avg_pool2d(
            x.clamp(min=self.eps).pow(self.p), 1
        ).pow(1.0 / self.p).squeeze(-1).squeeze(-1)


class DinoV2Gem(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = torch.hub.load(
            'facebookresearch/dinov2', 'dinov2_vits14',
            pretrained=True, verbose=False
        )
        self.gem = GeM()
        self.embed_dim = self.backbone.embed_dim

    def forward(self, x):
        with torch.no_grad():
            feats = self.backbone.forward_features(x)["x_norm_patchtokens"]
        N, L, C = feats.shape
        H = W = int(L**0.5)
        feats = feats.transpose(1, 2).reshape(N, C, H, W)
        return F.normalize(self.gem(feats), p=2, dim=1)


def _free_vram():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def load_models():
    global _netvlad_model, _dino_model, _device, _USE_FP16, _DTYPE
    try:
        print(f"[Models] Loading on {_device} (fp16={_USE_FP16}) ...")
        print(f"[Models] Cache dir: {MODEL_CACHE_DIR}")

        print("[Models] Loading NetVLAD (ResNet50-layer3, 32 clusters) ...")
        _netvlad_model = BackboneNetVLAD()
        if _USE_FP16:
            _netvlad_model = _netvlad_model.half()
        _netvlad_model = _netvlad_model.to(_device).eval()
        vram_msg = f"VRAM: {torch.cuda.memory_allocated()/1e6:.0f} MB" if torch.cuda.is_available() else ""
        print(f"[Models] NetVLAD OK {vram_msg}")

        print("[Models] Loading DINOv2-ViT-S/14 ...")
        _dino_model = DinoV2Gem()
        if _USE_FP16:
            _dino_model = _dino_model.half()
        _dino_model = _dino_model.to(_device).eval()
        vram_msg = f"VRAM: {torch.cuda.memory_allocated()/1e6:.0f} MB" if torch.cuda.is_available() else ""
        print(f"[Models] DINOv2 OK | embed_dim={_dino_model.embed_dim} {vram_msg}")

        state["models_ready"] = True
        print(f"[Models] Ready on {_device}")

    except Exception as e:
        # Catch TOUT : RuntimeError OOM, AssertionError NVML, etc.
        print(f"[Models] CUDA ERROR -> CPU fallback: {str(e)[:300]}")
        _free_vram()
        try:
            _device   = torch.device("cpu")
            _USE_FP16 = False
            _DTYPE    = torch.float32
            _netvlad_model = BackboneNetVLAD().to(_device).eval()
            _dino_model    = DinoV2Gem().to(_device).eval()
            state["models_ready"] = True
            print("[Models] Ready on CPU (fallback)")
        except Exception as e2:
            print(f"[Models] CPU fallback FAILED: {e2}")
            state["models_ready"] = False


_model_thread = threading.Thread(target=load_models, daemon=True)
_model_thread.start()

# =============================================================================
# TRANSFORMS
# =============================================================================
_tfm = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# =============================================================================
# GEOGRAPHIE
# =============================================================================
pi = math.pi


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))


def latlon_to_tile(lat, lon, z):
    n = 2**z
    x = int((lon + 180.) / 360. * n)
    y = int((1. - asinh(tan(radians(lat))) / pi) / 2. * n)
    return x, y


def tile_to_latlon(x, y, z):
    n   = 2**z
    lon = x / n * 360. - 180.
    lat = degrees(atan(sinh(pi * (1. - 2.*y/n))))
    return lat, lon


def compute_radius(alt_m, zoom=17):
    res  = 0.12 if zoom == 18 else 0.24
    foot = alt_m * res * 224 / 1000.0
    return max(foot * 3.0, alt_m * 2.0, 150.0)


# =============================================================================
# EXTRACTION MBTILES — parallelisee (16 workers I/O)
# =============================================================================
_mbtiles_conn_local = threading.local()


def _get_db():
    if not hasattr(_mbtiles_conn_local, "conn"):
        _mbtiles_conn_local.conn = sqlite3.connect(
            str(MBTILES_PATH), check_same_thread=False
        )
    return _mbtiles_conn_local.conn


def _extract_one_tile(args):
    z, x, y, out_dir = args
    y_tms = (2**z - 1) - y
    try:
        conn  = _get_db()
        row   = conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, y_tms)
        ).fetchone()
        if row is None:
            return None
        img   = Image.open(io.BytesIO(row[0])).convert("RGB")
        fname = f"tile_{z}_{x}_{y}.jpg"
        img.save(str(out_dir / fname), "JPEG", quality=85)
        lat, lon = tile_to_latlon(x, y, z)
        return (fname, lat, lon)
    except Exception:
        return None


def extract_circle(center_lat, center_lon, R, zoom, out_dir, csv_path,
                   progress_callback=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    margin = R * 1.4
    lat_n  = center_lat + degrees(margin / 6_371_000)
    lat_s  = center_lat - degrees(margin / 6_371_000)
    lon_e  = center_lon + degrees(margin / (6_371_000 * cos(radians(center_lat))))
    lon_w  = center_lon - degrees(margin / (6_371_000 * cos(radians(center_lat))))

    x_min, y_min = latlon_to_tile(lat_n, lon_w, zoom)
    x_max, y_max = latlon_to_tile(lat_s, lon_e, zoom)

    candidates = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            tc_lat, tc_lon = tile_to_latlon(x + 0.5, y + 0.5, zoom)
            if haversine_m(center_lat, center_lon, tc_lat, tc_lon) <= margin:
                candidates.append((zoom, x, y, out_dir))

    t0      = time.time()
    records = []
    done    = 0
    total   = len(candidates)

    MAX_WORKERS = min(16, os.cpu_count() or 4)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_extract_one_tile, c): c for c in candidates}
        for fut in as_completed(futures):
            result = fut.result()
            done  += 1
            if result:
                records.append(result)
            if progress_callback:
                progress_callback(done, total)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "lat", "lon"])
        writer.writerows(records)

    print(f"[Extract] R={R:.0f}m zoom={zoom} -> {len(records)}/{total} tuiles en {time.time()-t0:.1f}s")
    return len(records), csv_path


# =============================================================================
# BUILD DESCRIPTEURS
#
# BATCH = 1 sur Jetson Orin Nano
# Le Jetson utilise une memoire unifiee CPU/GPU (iGPU).
# Meme avec fp16, un batch > 1 image declenche NvMapMemAllocInternalTagged
# error 12 puis l'assert NVML interne de PyTorch.
# batch=1 est stable. Sur 66 images : ~20s. C'est acceptable.
# =============================================================================
def _img_to_tensor(path):
    try:
        return _tfm(Image.open(path).convert("RGB"))
    except Exception:
        return torch.zeros(3, 224, 224)


def build_descriptors(img_dir, csv_path, progress_callback=None):
    img_dir  = Path(img_dir)
    df       = pd.read_csv(csv_path)
    df_valid = df[df["filename"].apply(
        lambda f: (img_dir / f).exists()
    )].reset_index(drop=True)
    n = len(df_valid)

    if n == 0:
        return None, None, None, None

    # Detecter si on est sur Jetson pour forcer batch=1
    if _device.type == "cuda":
        gpu_name  = torch.cuda.get_device_name(0).lower()
        is_jetson = any(k in gpu_name for k in ["orin", "xavier", "tegra", "nano"])
        BATCH = 1 if is_jetson else (8 if _USE_FP16 else 4)
    else:
        BATCH = 2

    print(f"[Desc] {n} images | batch={BATCH} | device={_device} | fp16={_USE_FP16}")

    nv_list, dv_list = [], []
    done = 0

    for start in range(0, n, BATCH):
        batch_rows = df_valid.iloc[start:start + BATCH]
        paths      = [img_dir / row["filename"] for _, row in batch_rows.iterrows()]
        tensors    = [_img_to_tensor(p) for p in paths]
        imgs       = torch.stack(tensors)

        if _USE_FP16:
            imgs = imgs.half()
        imgs = imgs.to(_device)

        with torch.no_grad():
            nv_out = _netvlad_model(imgs)
            nv_list.append(nv_out.float().cpu().numpy())
            dv_out = _dino_model(imgs)
            dv_list.append(dv_out.float().cpu().numpy())

        del imgs, nv_out, dv_out
        _free_vram()

        done += len(batch_rows)
        if progress_callback:
            progress_callback(done, n)

    nv_arr = np.vstack(nv_list)
    dv_arr = np.vstack(dv_list)
    co_arr = df_valid[["lat", "lon"]].values.astype(np.float64)

    print(f"[Desc] Done: nv={nv_arr.shape}  dv={dv_arr.shape}")
    return nv_arr, dv_arr, co_arr, df_valid


# =============================================================================
# FMC MATCHING
# =============================================================================
THRESHOLD = 0.30


def _mm(a):
    return (a - a.min()) / (a.max() - a.min() + 1e-8)


def fmc_match(query_img_pil, anchor_lat, anchor_lon,
              nv_descs, dv_descs, coords, df_valid, R):
    img_t = _tfm(query_img_pil).unsqueeze(0)
    if _USE_FP16:
        img_t = img_t.half()
    img_t = img_t.to(_device)

    with torch.no_grad():
        q_nv = _netvlad_model(img_t).float().cpu().numpy()[0]
        q_dv = _dino_model(img_t).float().cpu().numpy()[0]

    del img_t
    _free_vram()

    dists = np.array([haversine_m(anchor_lat, anchor_lon, c[0], c[1]) for c in coords])
    mask  = dists <= R
    if mask.sum() < 5:
        mask = dists <= R * 3

    idx      = np.where(mask)[0]
    nv_sub   = nv_descs[idx]
    dv_sub   = dv_descs[idx]
    co_sub   = coords[idx]
    dist_sub = dists[idx]

    nv_sims    = nv_sub @ q_nv / (np.linalg.norm(nv_sub, axis=1) * np.linalg.norm(q_nv) + 1e-8)
    dv_sims    = dv_sub @ q_dv / (np.linalg.norm(dv_sub, axis=1) * np.linalg.norm(q_dv) + 1e-8)
    gps_scores = np.maximum(0., 1. - dist_sub / R)

    top50  = np.argsort(nv_sims)[-50:]
    fused  = 0.25*_mm(nv_sims[top50]) + 0.55*_mm(dv_sims[top50]) + 0.20*gps_scores[top50]
    best_i = top50[np.argmax(fused)]

    return (
        float(co_sub[best_i][0]),
        float(co_sub[best_i][1]),
        float(dv_sims[best_i]),
        float(fused[np.argmax(fused)]),
        df_valid.iloc[idx[best_i]]["filename"],
        len(idx),
    )


# =============================================================================
# GPS STATUS
# =============================================================================
def write_gps(data: dict):
    with open(GPS_STATUS, "w") as f:
        json.dump(data, f)


# =============================================================================
# CACHE DISQUE
# =============================================================================
def _load_cache_from_disk():
    if DESC_NPZ.exists() and CSV_PATH.exists():
        try:
            npz = np.load(str(DESC_NPZ))
            state["nv_descs"]    = npz["nv_descs"]
            state["dv_descs"]    = npz["dv_descs"]
            state["coords"]      = npz["coords"]
            state["df_valid"]    = pd.read_csv(CSV_PATH)
            state["cache_ready"] = True
            print(f"[Cache] Rechargé depuis disque — {len(state['df_valid'])} images")
        except Exception as e:
            print(f"[Cache] Erreur rechargement: {e}")


_load_cache_from_disk()


# =============================================================================
# PRECOLLECTE
# =============================================================================
def _run_precollect(lat, lon, alt_m, zoom):
    try:
        state.update({
            "precollect_running": True,
            "precollect_success": False,
            "precollect_error":   None,
            "precollect_pct":     0,
            "precollect_phase":   "extract",
        })

        R = compute_radius(alt_m, zoom)
        print(f"[Precollect] START centre=({lat:.5f},{lon:.5f}) R={R:.0f}m")

        for f in IMAGES_DIR.glob("*.jpg"):
            f.unlink()

        # Phase 1 : extraction (0% -> 70%)
        def extract_cb(done, total):
            state["precollect_done"]  = done
            state["precollect_total"] = total
            state["precollect_pct"]   = int(done / total * 70) if total > 0 else 0

        n_imgs, _ = extract_circle(lat, lon, R, zoom, IMAGES_DIR, CSV_PATH,
                                   progress_callback=extract_cb)
        state["precollect_pct"] = 70
        print(f"[Precollect] {n_imgs} tuiles extraites — attente modeles...")

        # Attendre les modeles (max 300s — premier lancement = download)
        state["precollect_phase"] = "waiting_models"
        for _ in range(600):
            if state["models_ready"]:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Timeout attente modeles (300s)")

        if n_imgs == 0:
            raise RuntimeError("Aucune tuile extraite dans le cercle")

        # Phase 2 : descripteurs (70% -> 100%)
        state["precollect_phase"] = "descriptors"

        def desc_cb(done, total):
            state["precollect_pct"] = 70 + int(done / total * 30) if total > 0 else 70

        nv_arr, dv_arr, co_arr, df_valid = build_descriptors(
            IMAGES_DIR, CSV_PATH, progress_callback=desc_cb
        )

        if nv_arr is None:
            raise RuntimeError("build_descriptors a retourne None")

        np.savez(str(DESC_NPZ), nv_descs=nv_arr, dv_descs=dv_arr, coords=co_arr)

        with _state_lock:
            state.update({
                "nv_descs":           nv_arr,
                "dv_descs":           dv_arr,
                "coords":             co_arr,
                "df_valid":           df_valid,
                "cache_ready":        True,
                "precollect_pct":     100,
                "precollect_phase":   "done",
                "precollect_success": True,
                "precollect_running": False,
            })

        print(f"[Precollect] DONE — {n_imgs} images | nv={nv_arr.shape} | dv={dv_arr.shape}")

    except Exception as e:
        state.update({
            "precollect_error":   str(e),
            "precollect_running": False,
            "precollect_pct":     0,
            "precollect_phase":   "error",
        })
        print(f"[Precollect] ERROR: {e}")


# =============================================================================
# PIPELINE GPS-LOSS
# =============================================================================
def _run_gps_loss_pipeline(frame_id, img_pil, anchor_lat, anchor_lon,
                           alt_m, zoom, heading_deg, speed_mps, delta_t_s):
    state["matching_active"] = True
    t0 = time.time()
    try:
        R = compute_radius(alt_m, zoom)
        write_gps({"status": "generating",
                   "message": f"Extraction MBTiles zoom={zoom} r={R:.0f}m...",
                   "frame_id": frame_id})

        ts        = int(time.time())
        frame_dir = CIRCLE_BASE / f"frame_{frame_id:05d}_{ts}"
        img_dir_f = frame_dir / "images"
        csv_f     = frame_dir / "dataset.csv"
        img_dir_f.mkdir(parents=True, exist_ok=True)

        n_imgs, _ = extract_circle(anchor_lat, anchor_lon, R, zoom, img_dir_f, csv_f)
        if n_imgs == 0:
            write_gps({"status": "error", "error": "Dataset vide", "frame_id": frame_id})
            return

        write_gps({"status": "searching", "lat": anchor_lat, "lon": anchor_lon,
                   "search_radius_m": R, "frame_id": frame_id})

        nv_arr, dv_arr, co_arr, df_valid = build_descriptors(img_dir_f, csv_f)
        if nv_arr is None:
            write_gps({"status": "error", "error": "Descripteurs vides", "frame_id": frame_id})
            return

        pred_lat, pred_lon, dv_score, fused_score, best_tile, n_cands = fmc_match(
            img_pil, anchor_lat, anchor_lon, nv_arr, dv_arr, co_arr, df_valid, R
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        print(f"[Pipeline] frame {frame_id} score={dv_score:.3f} t={elapsed_ms}ms")

        if dv_score >= THRESHOLD:
            state["last_pred_lat"] = pred_lat
            state["last_pred_lon"] = pred_lon
            write_gps({"status": "predicted", "lat": pred_lat, "lon": pred_lon,
                       "score": dv_score, "fused_score": fused_score,
                       "match": best_tile, "search_radius_m": R,
                       "n_candidates": n_cands, "total_ms": elapsed_ms,
                       "dataset_images": n_imgs,
                       "last_valid_lat": anchor_lat, "last_valid_lon": anchor_lon,
                       "frame_id": frame_id})
        else:
            print(f"[Pipeline] score {dv_score:.3f} < {THRESHOLD} — DR kept frame {frame_id}")

    except Exception as e:
        print(f"[Pipeline] ERROR frame {frame_id}: {e}")
        write_gps({"status": "error", "error": str(e), "frame_id": frame_id})
    finally:
        state["matching_active"] = False


# =============================================================================
# FLASK
# =============================================================================
app = Flask(__name__)
CORS(app)


@app.route("/health")
def health():
    return jsonify({
        "cuda":         torch.cuda.is_available(),
        "models_ready": state["models_ready"],
        "cache_ready":  state["cache_ready"],
        "fp16":         _USE_FP16,
        "device":       str(_device),
        "mbtiles":      MBTILES_PATH.exists(),
        "model_cache":  str(MODEL_CACHE_DIR),
    })


@app.route("/api/set_mission", methods=["POST"])
def set_mission():
    d = request.json or {}
    if "altitude_m" in d:
        state["mission_alt_m"] = float(d["altitude_m"])
    if "zoom" in d:
        state["mission_zoom"] = int(d["zoom"])
    if "point_a" in d:
        state["point_a_lat"] = float(d["point_a"]["lat"])
        state["point_a_lon"] = float(d["point_a"]["lon"])
    return jsonify({"ok": True})


@app.route("/api/precollect", methods=["POST", "OPTIONS"])
def precollect():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    d = request.json or {}
    if state["precollect_running"]:
        return jsonify({"ok": False, "error": "precollect already running"})

    lat   = float(d.get("lat",        state.get("point_a_lat", 0)))
    lon   = float(d.get("lon",        state.get("point_a_lon", 0)))
    alt_m = float(d.get("altitude_m", state["mission_alt_m"]))
    zoom  = int(d.get("zoom",         state["mission_zoom"]))

    if "minLat" in d:
        lat = (float(d["minLat"]) + float(d["maxLat"])) / 2
        lon = (float(d["minLng"]) + float(d["maxLng"])) / 2

    R = compute_radius(alt_m, zoom)
    print(f"[R] alt={alt_m:.0f}m  footprint={alt_m*0.24*224/1000:.0f}m  R={R:.0f}m")
    threading.Thread(target=_run_precollect, args=(lat, lon, alt_m, zoom), daemon=True).start()
    return jsonify({"ok": True, "R": R})


@app.route("/api/precollect_progress")
def precollect_progress():
    return jsonify({
        "pct":     state["precollect_pct"],
        "done":    state["precollect_done"],
        "total":   state["precollect_total"],
        "phase":   state["precollect_phase"],
        "running": state["precollect_running"],
        "success": state["precollect_success"],
        "error":   state["precollect_error"],
    })


@app.route("/api/cache_status")
def cache_status():
    n = len(state["df_valid"]) if state["df_valid"] is not None else 0
    return jsonify({
        "ready":   state["cache_ready"],
        "images":  n,
        "message": (f"{n} images en cache" if state["cache_ready"] else
                    "Chargement modeles..." if not state["models_ready"] else
                    "Pas de cache"),
    })


@app.route("/frame", methods=["POST"])
def receive_frame():
    d    = request.json or {}
    meta = d.get("metadata", {})

    frame_id  = int(meta.get("frame_id",     0))
    lat       = float(meta.get("lat",        0))
    lon       = float(meta.get("lon",        0))
    gps_valid = bool(meta.get("gps_valid",   True))
    alt_m     = float(meta.get("altitude_m", state["mission_alt_m"]))
    heading   = float(meta.get("heading_deg", 0))
    speed     = float(meta.get("speed_mps",  0))
    delta_t   = float(meta.get("delta_t_s",  1))

    if gps_valid:
        state["last_known_lat"] = lat
        state["last_known_lon"] = lon
        write_gps({"status": "idle", "mission_started": True,
                   "lat": lat, "lon": lon, "frame_id": frame_id})
        return jsonify({"frame_id": frame_id, "gps_valid": True,
                        "source": "gps", "predicted_lat": lat,
                        "predicted_lon": lon, "match_score": 0.0})

    anchor_lat = state["last_pred_lat"] or state["last_known_lat"] or lat
    anchor_lon = state["last_pred_lon"] or state["last_known_lon"] or lon
    R_earth    = 6_371_000.
    hdg_r      = radians(heading)
    dist       = speed * delta_t
    dr_lat = anchor_lat + (dist * cos(hdg_r)) / R_earth * (180. / pi)
    dr_lon = anchor_lon + (dist * sin(hdg_r)) / (R_earth * cos(radians(anchor_lat))) * (180. / pi)
    state["last_pred_lat"] = dr_lat
    state["last_pred_lon"] = dr_lon

    img_pil = None
    if d.get("image_b64"):
        try:
            import base64
            img_pil = Image.open(io.BytesIO(base64.b64decode(d["image_b64"]))).convert("RGB")
        except Exception:
            pass

    if (state["models_ready"] and not state["matching_active"]
            and img_pil and anchor_lat and anchor_lon):
        zoom = int(meta.get("zoom", state["mission_zoom"]))
        threading.Thread(
            target=_run_gps_loss_pipeline,
            args=(frame_id, img_pil, anchor_lat, anchor_lon,
                  alt_m, zoom, heading, speed, delta_t),
            daemon=True
        ).start()

    return jsonify({"frame_id": frame_id, "gps_valid": False,
                    "source": "dead_reckoning",
                    "predicted_lat": dr_lat, "predicted_lon": dr_lon,
                    "match_score": 0.0})


@app.route("/gps_status.json")
def gps_status():
    if GPS_STATUS.exists():
        return send_file(str(GPS_STATUS), mimetype="application/json")
    return jsonify({"status": "idle"})


@app.route("/flight_log.csv")
def flight_log():
    if FLIGHT_LOG.exists():
        return send_file(str(FLIGHT_LOG), mimetype="text/csv")
    return ("frame_id,timestamp,image_file,lat,lon,alt_m,heading_deg,"
            "speed_mps,gps_valid,predicted_lat,predicted_lon,match_score\n", 200)


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("[AONLY] receiver_aonly demarre sur port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
