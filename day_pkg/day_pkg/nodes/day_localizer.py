import os, time
import numpy as np
import torch
import torch.nn as nn
import timm
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

# ── Retrieval config (correctif #1) ────────────────────────────────
# Le NetVLAD de ce repo n'est PAS entraîné (conv + centroids = init aléatoire,
# aucun checkpoint chargé, aucun seed) : ses poids changent à chaque process,
# donc le descripteur requête vit dans un espace différent de celui du cache
# → la shortlist NetVLAD est du bruit. DINOv2 (pré-entraîné, déterministe) est
# fiable, donc on classe TOUTES les tuiles directement par cosine DINOv2.
RETRIEVAL_BACKBONE = "dinov2"   # "dinov2" (fiable) | "netvlad" (legacy, non entraîné)
TOP5_N             = 5          # nb de matches loggés pour diagnostic

# ── Mémoire / OOM (ÉTAPE C — Jetson Orin Nano, 8 Go partagés CPU+GPU) ──
# La 1re localisation peut crasher en "CUBLAS_STATUS_ALLOC_FAILED". Ces options
# réduisent la pression mémoire. Toute l'inférence est déjà sous torch.no_grad().
USE_FP16                  = False  # encode la requête en demi-précision (moins de VRAM)
EMPTY_CACHE_AFTER_PREDICT = True   # libère le cache allocateur CUDA après chaque frame
COMPUTE_NETVLAD_DIAG      = False  # calcule aussi le cosine NetVLAD (colonne 'nv' du top5) :
                                   # coûteux (forward GPU + matmul 1120×131072 en RAM), inutile
                                   # pour le retrieval DINOv2 → OFF par défaut

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

class NetVLAD(nn.Module):
    def __init__(self, num_clusters=64, dim=2048):
        super().__init__()
        self.num_clusters = num_clusters
        self.conv      = nn.Conv2d(dim, num_clusters, kernel_size=1)
        self.centroids = nn.Parameter(torch.rand(num_clusters, dim))
    def forward(self, x):
        N, C, H, W = x.shape
        soft = torch.softmax(self.conv(x).view(N, self.num_clusters, -1), dim=1)
        xf   = x.view(N, C, -1)
        vlad = [(soft[:, k:k+1] * (xf - self.centroids[k:k+1].unsqueeze(-1))).sum(-1)
                for k in range(self.num_clusters)]
        return nn.functional.normalize(torch.cat(vlad, dim=1), p=2, dim=1)

class BackboneNetVLAD(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = timm.create_model("resnet50", pretrained=True, features_only=True)
        dim = self.backbone.feature_info[-1]['num_chs']
        self.netvlad  = NetVLAD(num_clusters=64, dim=dim)
    def forward(self, x):
        return self.netvlad(self.backbone(x)[-1])

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

def haversine_m(lat1, lon1, lat2, lon2):
    R       = 6_371_000
    p1, p2  = radians(lat1), radians(lat2)
    dp, dl  = radians(lat2-lat1), radians(lon2-lon1)
    a       = sin(dp/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def gps_consistency_score(coords, radius_m=50.0):
    K      = len(coords)
    scores = np.zeros(K)
    for i in range(K):
        for j in range(K):
            if i == j: continue
            if haversine_m(coords[i,0],coords[i,1],coords[j,0],coords[j,1]) <= radius_m:
                scores[i] += 1
    mx = scores.max()
    return scores / mx if mx > 0 else scores

def fused_reranking(q_nv, q_dino, cand_idx, nv_descs, dino_descs, coords,
                    w_nv=0.25, w_dino=0.55, w_gps=0.20, gps_radius=50.0, top_n=5):
    nv_s   = cosine_similarity(q_nv.reshape(1,-1),   nv_descs[cand_idx])[0]
    dino_s = cosine_similarity(q_dino.reshape(1,-1), dino_descs[cand_idx])[0]
    def mm(a):
        mn, mx = a.min(), a.max()
        return (a - mn) / (mx - mn + 1e-8)
    fused  = w_nv*mm(nv_s) + w_dino*mm(dino_s) + w_gps*gps_consistency_score(coords[cand_idx], gps_radius)
    top_l  = fused.argsort()[-top_n:][::-1]
    return cand_idx[top_l], fused[top_l], {
        "dinov2_raw":  dino_s[top_l],
        "netvlad_raw": nv_s[top_l],
        "fused":       fused[top_l]
    }

class DayLocalizer:
    def __init__(self):
        self.device         = "cuda" if torch.cuda.is_available() else "cpu"
        self.netvlad_model  = None
        self.dinov2_model   = None
        self.nv_descs       = None
        self.dino_descs     = None
        self.coords         = None
        self.df_valid       = None
        self.ready          = False
        print(f"[DayLocalizer] device={self.device}")

    def load_models(self):
        print("[DayLocalizer] Loading NetVLAD...")
        self.netvlad_model = BackboneNetVLAD().to(self.device).eval()
        print("[DayLocalizer] Loading DINOv2...")
        self.dinov2_model  = DINOv2GeM().to(self.device).eval()
        print("[DayLocalizer] Models ready")

    def load_or_build_cache(self):
        import pandas as pd
        if os.path.exists(CACHE_PATH):
            print("[DayLocalizer] Loading cache...")
            cache           = np.load(CACHE_PATH)
            self.nv_descs   = cache["netvlad_descriptors"]
            self.dino_descs = cache["dinov2_descriptors"]
            self.coords     = cache["coords"]
            valid_idx       = cache["valid_indices"].tolist()
            df              = pd.read_csv(CSV_PATH)
            df              = df.rename(columns={"filename": "imageName"})
            self.df_valid   = df.iloc[valid_idx].reset_index(drop=True)
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
        nv_list=[]; dino_list=[]; coords=[]; valid_idx=[]
        with torch.no_grad():
            for i, (_, row) in enumerate(df.iterrows()):
                p = os.path.join(IMAGES_DIR, str(row["imageName"]).strip())
                if not os.path.exists(p): continue
                try:
                    img = load_image_tensor(p).unsqueeze(0).to(self.device)
                    nv_list.append(self.netvlad_model(img).cpu().numpy()[0])
                    dino_list.append(self.dinov2_model(img).cpu().numpy()[0])
                    coords.append([float(row["latitude"]), float(row["longitude"])])
                    valid_idx.append(i)
                    if i % 20 == 0:
                        print(f"  [{i}/{total}]...")
                except Exception as e:
                    print(f"  Skip {i}: {e}")
        self.nv_descs   = np.array(nv_list)
        self.dino_descs = np.array(dino_list)
        self.coords     = np.array(coords)
        self.df_valid   = df.iloc[valid_idx].reset_index(drop=True)
        np.savez(CACHE_PATH,
                 netvlad_descriptors=self.nv_descs,
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
                    q_nv   = (self.netvlad_model(t).float().cpu().numpy()[0]
                              if COMPUTE_NETVLAD_DIAG else None)
            else:
                q_dino = self.dinov2_model(t).cpu().numpy()[0]
                q_nv   = (self.netvlad_model(t).cpu().numpy()[0]
                          if COMPUTE_NETVLAD_DIAG else None)
            del t
        if EMPTY_CACHE_AFTER_PREDICT and use_cuda:
            torch.cuda.empty_cache()      # rend la VRAM cachée entre deux frames

        # ── Retrieval direct sur les 1120 tuiles ──
        # cosine DINOv2 sur TOUT le dataset (descripteurs déjà L2-normalisés).
        dino_sims = cosine_similarity(q_dino.reshape(1, -1), self.dino_descs)[0]
        # NetVLAD calculé seulement si demandé (diagnostic, probablement du bruit).
        nv_sims   = (cosine_similarity(q_nv.reshape(1, -1), self.nv_descs)[0]
                     if q_nv is not None else None)

        base = nv_sims if (RETRIEVAL_BACKBONE == "netvlad" and nv_sims is not None) else dino_sims

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
                "netvlad": float(nv_sims[idx]) if nv_sims is not None else float("nan"),
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
