import math
import os, time
import numpy as np
import torch
import torch.nn as nn
import cv2
from math import radians, sin, cos, sqrt, atan2
from torchvision import transforms
from sklearn.metrics.pairwise import cosine_similarity

def _resolve_dataset_dir():
    """Locate the descriptor dataset robustly across source / installed layouts.

    Priority:
      1. $DAY_DATASET_DIR (explicit override)
      2. <package_share>/dataset            (if installed via setup.py data_files)
      3. <pkg>/dataset                       (source layout: day_pkg/day_pkg/dataset)
      4. <nodes>/dataset                     (legacy layout)
    Uses realpath so a symlink-installed module resolves back to the source tree.
    """
    env = os.environ.get("DAY_DATASET_DIR")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.realpath(__file__))     # .../day_pkg/nodes
    candidates = [
        os.path.join(os.path.dirname(here), "dataset"),    # .../day_pkg/dataset (source)
        os.path.join(here, "dataset"),                     # .../nodes/dataset (legacy)
    ]
    try:
        from ament_index_python.packages import get_package_share_directory
        candidates.insert(0, os.path.join(get_package_share_directory("day_pkg"), "dataset"))
    except Exception:
        pass
    for c in candidates:
        if os.path.isdir(c):
            return c
    # Fall back to the source-style layout (clear error later if truly missing).
    return os.path.join(os.path.dirname(here), "dataset")


DATASET_DIR = _resolve_dataset_dir()
IMAGES_DIR  = os.path.join(DATASET_DIR, "images")
CSV_PATH    = os.path.join(DATASET_DIR, "dataset.csv")
CACHE_PATH  = os.path.join(DATASET_DIR, "descriptors_cache.npz")

# ── Retrieval ───────────────────────────────────────────────────
# Tiles are ranked by DINOv2 (pre-trained, deterministic) cosine similarity.
# The NetVLAD/ResNet50 branch that used to be loaded here was never trained
# (random weights, different in every process) and never used for ranking; it
# is gone, with its boot-time ImageNet download and its GPU memory.
TOP5_N             = 5          # matches logged for diagnostics

# ── Mémoire / OOM (ÉTAPE C — Jetson Orin Nano, 8 Go partagés CPU+GPU) ──
# La 1re localisation peut crasher en "CUBLAS_STATUS_ALLOC_FAILED". Ces options
# réduisent la pression mémoire. Toute l'inférence est déjà sous torch.no_grad().
USE_FP16                  = False  # encode la requête en demi-précision (moins de VRAM)
EMPTY_CACHE_AFTER_PREDICT = True   # libère le cache allocateur CUDA après chaque frame

transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
])

def load_image_tensor(path_or_array):
    img = cv2.imread(path_or_array) if isinstance(path_or_array, str) else path_or_array
    if img is None:
        raise FileNotFoundError("Image not found")
    return transform(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

class GeM(nn.Module):
    def __init__(self, p=3.0, eps=1e-6):
        super().__init__()
        self.p   = nn.Parameter(torch.ones(1) * p)
        self.eps = eps
    def forward(self, x):
        return (x.clamp(min=self.eps).pow(self.p).mean(dim=(-2,-1)).pow(1.0/self.p))

class DINOv2GeM(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone  = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14", pretrained=True)
        self.gem       = GeM()
        self.embed_dim = self.backbone.embed_dim
    def forward(self, x):
        out     = self.backbone.get_intermediate_layers(x, n=1)[0]
        B, N, C = out.shape
        H = W   = int(N**0.5)
        out = self.gem(out.reshape(B,H,W,C).permute(0,3,1,2))
        return nn.functional.normalize(out, p=2, dim=1)

def tile_center_latlon(filename):
    """Centre (lat, lon) of an XYZ slippy-map tile named ``tile_<z>_<x>_<y>.jpg``.

    The dataset CSV stores each tile's NORTH-WEST CORNER (the value
    tile_to_latlon(x, y) returns), not its centre: publishing that as the
    position biases every fix by half a tile (~175 m at z17, to the NW).
    Returns None when the name does not follow the pattern.
    """
    parts = os.path.splitext(os.path.basename(str(filename)))[0].split("_")
    if len(parts) != 4 or parts[0] != "tile":
        return None
    try:
        z, x, y = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return None
    n   = 2 ** z
    lon = (x + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))
    return lat, lon


def dataset_coords(df):
    """(N, 2) array of tile-centre coordinates for the rows of the dataset CSV.

    Uses the centre derived from the tile filename; falls back to the CSV's
    lat/lon columns (``lat``/``lon`` or ``latitude``/``longitude``) for rows
    whose name does not encode a tile.
    """
    lat_col = "lat" if "lat" in df.columns else "latitude"
    lon_col = "lon" if "lon" in df.columns else "longitude"
    out = []
    for _, row in df.iterrows():
        c = tile_center_latlon(row["imageName"])
        out.append(c if c is not None else (float(row[lat_col]), float(row[lon_col])))
    return np.array(out, dtype=float)


def haversine_m(lat1, lon1, lat2, lon2):
    R       = 6_371_000
    p1, p2  = radians(lat1), radians(lat2)
    dp, dl  = radians(lat2-lat1), radians(lon2-lon1)
    a       = sin(dp/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

class DayLocalizer:
    def __init__(self):
        self.device         = "cuda" if torch.cuda.is_available() else "cpu"
        self.dinov2_model   = None
        self.dino_descs     = None
        self.coords         = None
        self.df_valid       = None
        self.ready          = False
        print(f"[DayLocalizer] device={self.device}")

    def load_models(self):
        print("[DayLocalizer] Loading DINOv2...")
        self.dinov2_model  = DINOv2GeM().to(self.device).eval()
        print("[DayLocalizer] Models ready")

    def load_or_build_cache(self):
        import pandas as pd
        if os.path.exists(CACHE_PATH):
            print("[DayLocalizer] Loading cache...")
            cache           = np.load(CACHE_PATH)
            self.dino_descs = cache["dinov2_descriptors"]
            valid_idx       = cache["valid_indices"].tolist()
            df              = pd.read_csv(CSV_PATH)
            df              = df.rename(columns={"filename": "imageName"})
            if len(valid_idx) != len(self.dino_descs) or (valid_idx and max(valid_idx) >= len(df)):
                raise RuntimeError(
                    f"descriptor cache {CACHE_PATH} does not match {CSV_PATH} "
                    f"({len(self.dino_descs)} descriptors, {len(valid_idx)} indices, "
                    f"{len(df)} CSV rows) — delete the cache to rebuild it")
            self.df_valid   = df.iloc[valid_idx].reset_index(drop=True)
            # Coordinates are always re-derived from the CSV rather than trusted
            # from the cache: caches built before the tile-centre fix hold NW corners.
            self.coords     = dataset_coords(self.df_valid)
            self.ready      = True
            print(f"[DayLocalizer] Cache loaded: {len(self.coords)} images")
        else:
            self._build_cache()

    def _build_cache(self):
        import pandas as pd
        print("[DayLocalizer] Building cache (takes a few minutes)...")
        df    = pd.read_csv(CSV_PATH)
        df    = df.rename(columns={"filename": "imageName"})
        total = len(df)
        dino_list=[]; valid_idx=[]
        with torch.no_grad():
            for i, (_, row) in enumerate(df.iterrows()):
                p = os.path.join(IMAGES_DIR, str(row["imageName"]).strip())
                if not os.path.exists(p): continue
                try:
                    img = load_image_tensor(p).unsqueeze(0).to(self.device)
                    dino_list.append(self.dinov2_model(img).cpu().numpy()[0])
                    valid_idx.append(i)
                    if i % 20 == 0:
                        print(f"  [{i}/{total}]...")
                except Exception as e:
                    print(f"  Skip {i}: {e}")
        self.dino_descs = np.array(dino_list)
        self.df_valid   = df.iloc[valid_idx].reset_index(drop=True)
        self.coords     = dataset_coords(self.df_valid)
        np.savez(CACHE_PATH,
                 dinov2_descriptors=self.dino_descs,
                 coords=self.coords,
                 valid_indices=np.array(valid_idx))
        self.ready = True
        print(f"[DayLocalizer] Cache saved: {len(self.coords)} images")

    def _haversine_to_coords(self, lat, lon):
        """Distance haversine (m) de (lat,lon) vers TOUTES les coords du cache → (N,)."""
        R   = 6_371_000.0
        la  = np.radians(self.coords[:, 0]); lo = np.radians(self.coords[:, 1])
        p1  = radians(lat);                  l1 = radians(lon)
        dp  = la - p1; dl = lo - l1
        a   = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(la) * np.sin(dl / 2) ** 2
        return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    def warm_up(self):
        """One throw-away inference, so CUDA kernel loading and allocator
        growth happen before the node reports ready, not on the first frame."""
        self.predict(np.zeros((224, 224, 3), dtype=np.uint8))

    def predict(self, img_array, top_k=50, threshold=0.75, center=None, radius_m=None):
        """center=(lat,lon) + radius_m → a priori spatial : ne classe que les tuiles
        dont le centre est dans le cercle (fix matching GPS-denied cross-source).
        Sans center/radius_m → comportement global inchangé."""
        if not self.ready:
            return {"error": "not_ready"}
        t0 = time.time()
        use_cuda = (self.device == "cuda")
        with torch.no_grad():
            t = load_image_tensor(img_array).unsqueeze(0).to(self.device)
            if USE_FP16 and use_cuda:
                with torch.autocast("cuda", dtype=torch.float16):
                    q_dino = self.dinov2_model(t).float().cpu().numpy()[0]
            else:
                q_dino = self.dinov2_model(t).cpu().numpy()[0]
            del t
        if EMPTY_CACHE_AFTER_PREDICT and use_cuda:
            torch.cuda.empty_cache()      # rend la VRAM cachée entre deux frames

        # ── Retrieval direct sur les 1120 tuiles ──
        # cosine DINOv2 sur TOUT le dataset (descripteurs déjà L2-normalisés).
        dino_sims = cosine_similarity(q_dino.reshape(1, -1), self.dino_descs)[0]
        base = dino_sims

        # ── a priori spatial : restreindre les candidats au cercle autour de center ──
        spatial = (center is not None and radius_m is not None)
        if spatial:
            d_to_center = self._haversine_to_coords(center[0], center[1])   # (N,)
            cand = np.where(d_to_center <= radius_m)[0]
            if cand.size == 0:
                # aucune tuile dans le cercle → le subscriber fera du dead_reckon (étape 5)
                return {
                    "spatial": True, "spatial_empty": True,
                    "radius_m": float(radius_m), "n_candidates": 0,
                    "predicted_lat": None, "predicted_lon": None,
                    "score": None, "fused_score": None, "accepted": False,
                    "match": None, "top5": [], "total_ms": (time.time() - t0) * 1000,
                }
            order = cand[np.argsort(base[cand])[::-1]]   # top-1 DINOv2 PARMI le cercle
        else:
            order = base.argsort()[::-1]                 # global (comportement inchangé)

        top5_idx = order[:TOP5_N]
        top5 = []
        for rank, idx in enumerate(top5_idx):
            idx = int(idx)
            lat, lon = float(self.coords[idx][0]), float(self.coords[idx][1])
            top5.append({
                "rank":    rank + 1,
                "index":   idx,
                "image":   str(self.df_valid.iloc[idx]["imageName"]),
                "dino":    float(dino_sims[idx]),
                "lat":     lat,
                "lon":     lon,
            })

        best  = int(top5_idx[0])
        score = float(dino_sims[best])              # similarité du top-1 (métrique fiable)
        gps   = self.coords[best]
        return {
            "predicted_lat": float(gps[0]),
            "predicted_lon": float(gps[1]),
            "score":         score,
            "fused_score":   score,
            "accepted":      score >= threshold,
            "match":         self.df_valid.iloc[best]["imageName"],
            "top5":          top5,
            "spatial":       spatial,
            "spatial_empty": False,
            "radius_m":      float(radius_m) if spatial else None,
            "n_candidates":  int(cand.size) if spatial else int(len(self.coords)),
            "total_ms":      (time.time()-t0)*1000
        }
