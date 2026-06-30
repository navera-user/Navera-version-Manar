"""
night_localizer.py  —  NAVERA Night Localization Engine
Wraps STHN local_pipeline for drone-to-satellite homography matching.

Usage:
    localizer = NightLocalizer(sthn_dir, weights_path, mbtiles_path)
    result = localizer.localize(query_img_bgr, gps_prior_lat, gps_prior_lon)
"""

import sys
import os
import math
import sqlite3
import logging
import time
from pathlib import Path
from collections import deque

import numpy as np
import cv2
import torch

logger = logging.getLogger("night_localizer")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─── Tile utilities (MBTiles → numpy) ────────────────────────────────────────

def _latlon_to_tile(lat, lon, zoom):
    """Convert lat/lon to tile x,y at given zoom (Web Mercator / XYZ)."""
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _read_tile(conn, z, x, y):
    """Read a tile from MBTiles (TMS y-flip required)."""
    tms_y = (2 ** z - 1) - y
    row = conn.execute(
        "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
        (z, x, tms_y),
    ).fetchone()
    if row is None:
        return None
    data = row[0]
    arr  = np.frombuffer(data, dtype=np.uint8)
    img  = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _stitch_satellite_patch(conn, lat, lon, zoom, patch_size=512):
    """
    Build a satellite patch of `patch_size x patch_size` px centered on (lat, lon).
    Returns (patch_bgr, ref_lat, ref_lon, metres_per_pixel).
    """
    cx, cy = _latlon_to_tile(lat, lon, zoom)

    # 3×3 neighbourhood of 256 px tiles → 768 px mosaic, then centre-crop
    rows = []
    for dy in range(-1, 2):
        row_tiles = []
        for dx in range(-1, 2):
            tile = _read_tile(conn, zoom, cx + dx, cy + dy)
            if tile is None:
                tile = np.zeros((256, 256, 3), dtype=np.uint8)
            if tile.shape[:2] != (256, 256):
                tile = cv2.resize(tile, (256, 256))
            row_tiles.append(tile)
        rows.append(np.concatenate(row_tiles, axis=1))
    mosaic = np.concatenate(rows, axis=0)   # 768×768

    h, w   = mosaic.shape[:2]
    cy_px  = h // 2
    cx_px  = w // 2
    half   = patch_size // 2
    patch  = mosaic[cy_px - half : cy_px + half, cx_px - half : cx_px + half]

    if patch.shape[0] != patch_size or patch.shape[1] != patch_size:
        patch = cv2.resize(patch, (patch_size, patch_size))

    mpp = 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)
    return patch, lat, lon, mpp


# ─── Bing ↔ ESRI projection bias correction ──────────────────────────────────

# Empirical bias measured between Bing and ESRI at zoom 17 over Sousse
BING_ESRI_BIAS_LAT = -0.00004   # degrees  (~4 m south)
BING_ESRI_BIAS_LON =  0.00006   # degrees  (~5 m east)


def _apply_bias_correction(lat, lon):
    return lat - BING_ESRI_BIAS_LAT, lon - BING_ESRI_BIAS_LON


# ─── Main localizer ───────────────────────────────────────────────────────────

class NightLocalizer:
    """
    Wraps STHN local_pipeline to produce lat/lon fixes from night drone frames.

    Parameters
    ----------
    sthn_dir   : path to cloned github.com/arplaboratory/STHN
    weights    : path to local_pipeline checkpoint (.pth)
    mbtiles    : path to sousse_satellite.mbtiles
    zoom       : MBTiles zoom level (default 17)
    patch_size : satellite reference patch size (default 512)
    roll_avg_n : rolling average window (default 5)
    device     : 'cuda' or 'cpu'
    """

    def __init__(
        self,
        sthn_dir: str,
        weights: str,
        mbtiles: str,
        zoom: int = 17,
        patch_size: int = 256,
        roll_avg_n: int = 5,
        device: str = None,
        conf_threshold: float = 0.30,
        mixed_precision: bool = False,
    ):
        self.zoom           = zoom
        self.patch_size     = patch_size
        self.conf_threshold = conf_threshold
        self.mixed_precision = bool(mixed_precision)   # fp16 autocast au forward (network.py:110/139)
        self.device     = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.roll_avg_n = roll_avg_n
        self._lat_buf   = deque(maxlen=roll_avg_n)
        self._lon_buf   = deque(maxlen=roll_avg_n)

        # Insert STHN into sys.path
        sthn_dir = str(Path(sthn_dir).resolve())
        if sthn_dir not in sys.path:
            sys.path.insert(0, sthn_dir)

        # Load model
        self._model = self._load_model(weights)

        # Open MBTiles
        self._conn = sqlite3.connect(mbtiles, check_same_thread=False)
        logger.info(f"NightLocalizer ready | device={self.device} zoom={zoom}")

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_model(self, weights_path: str):
        """
        Load the STHN local_pipeline Network with safetensors + pth support.
        Only searches local_pipeline/model/network.py — avoids global_pipeline
        which pulls torchvision and breaks on NumPy 2.x.
        """
        import importlib.util

        # ── Look ONLY in local_pipeline/model/network.py ─────────────────────
        Network = None
        sthn_root = Path(sys.path[0])
        candidates = list(sthn_root.rglob("local_pipeline/model/network.py"))
        logger.info(f"Searching for local_pipeline/model/network.py in {sthn_root}")
        logger.info(f"Candidates found: {candidates}")

        for candidate in candidates:
            # add local_pipeline dir to sys.path so 'update', 'corr' etc. are importable
            lp_dir = str(candidate.parent.parent)
            if lp_dir not in sys.path:
                sys.path.insert(0, lp_dir)
            # mock heavy training-only deps so network.py loads for inference
            import unittest.mock as _mock
            _MOCK_MODS = [
                "wandb", "wandb.sdk", "wandb.sdk.lib",
                "matplotlib", "matplotlib.pyplot", "matplotlib.colors",
                "matplotlib.cm", "matplotlib.patches", "matplotlib.lines",
                "tensorboard", "tensorboard.summary", "tensorboard.summary.writer",
                "torch.utils.tensorboard", "torch.utils.tensorboard.writer",
                "loguru", "einops", "timm", "mmcv", "mmdet",
                "skimage", "skimage.transform", "skimage.color",
                "h5py", "tqdm", "tqdm.auto",
                "flow_vis", "spatial_correlation_sampler",
                "cupy", "cv2.cuda",
                "sklearn", "sklearn.metrics", "sklearn.preprocessing",
                "torchvision", "torchvision.transforms", "torchvision.models",
                "datasets_4cor_img",
            ]
            for _dep in _MOCK_MODS:
                if _dep not in sys.modules:
                    sys.modules[_dep] = _mock.MagicMock()
            spec = importlib.util.spec_from_file_location("_sthn_local_network", candidate)
            mod  = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                Network = getattr(mod, "STHN", None) or getattr(mod, "Network", None)
                if Network is not None:
                    logger.info(f"Loaded Network from {candidate}")
                    break
            except Exception as e:
                logger.warning(f"Failed to load {candidate}: {e}")
                continue

        if Network is None:
            raise RuntimeError(
                "Cannot find STHN Network class in local_pipeline/model/network.py\n"
                f"sthn_dir searched: {sthn_root}"
            )

        # ── Build minimal args namespace ─────────────────────────────────────
        import argparse
        args = argparse.Namespace(
            aggregation="netvlad",
            netvlad_clusters=64,
            fc_output_dim=512,
            infer_batch_size=1,
            resize=[self.patch_size, self.patch_size],
            db_size=512,
            rw=256,
            no_cuda=(self.device == "cpu"),
            device=self.device,
            mixed_precision=self.mixed_precision,   # fp16 SEULEMENT sur fnet1 + update_block_4 ; le solve cuSOLVER reste fp32 (hors autocast)
            iters=6,
            weight_decay=1e-5,
            epsilon=1e-8,
            clip=1.0,
            dropout=0.0,
            small=False,
            alternate_corr=False,
            iters_lev0=6,
            prior_location_threshold=-1,
            rej_threshold=0.0,
            use_ue=False,
            train_ue_method="none",
            ue_alpha=0.5,
            multi_aug_eval=False,
            test=True,
            name="navera",
            save_dir="/tmp",
            num_steps=100000,
            num_workers=0,
            batch_size=1,
            val_freq=1000,
            val_positive_dist_threshold=25,
            eval_model="",
            eval_model_fine="",
            eval_model_ue="",
            load_test_pairs=False,
            generate_test_pairs=False,
            dataset_name="navera",
            crop_width=512,
            resize_max=512,
            perspective_max=0.0,
            rotate_max=0.0,
            augment=False,
            identity=False,
            bce_weight=1.0,
            GAN_mode="none",
            D_net="none",
            G_contrast=False,
            resize_width=self.patch_size,
            resize_height=self.patch_size,
            database_size=self.patch_size,
            arch="IHN",
            two_stages=False,
            restore_ckpt=None,
            finetune=False,
            corr_level=2,
            corr_radius=4,
            vis_all=False,
            G_loss_lambda=1.0,
            gpuid=[0] if self.device == "cuda" else [0],
            lev0=True,
            fnet_cat=False,
            gamma=0.8,
            iters_lev1=6,
            augment_two_stages=False,
            augment_type="none",
            weight=False,
        )

        model = Network(args)

        # ── Load checkpoint — safetensors or pth ─────────────────────────────
        weights_path = str(weights_path)
        if weights_path.endswith(".safetensors"):
            from safetensors.torch import load_file
            state = load_file(weights_path, device=self.device)
        else:
            checkpoint = torch.load(weights_path, map_location=self.device)
            if isinstance(checkpoint, dict):
                state = (
                    checkpoint.get("model_state_dict")
                    or checkpoint.get("state_dict")
                    or checkpoint
                )
            else:
                state = checkpoint

        model.netG.load_state_dict(state, strict=False)
        model.netG = model.netG.to(self.device).eval()
        logger.info(f"STHN weights loaded from {weights_path}")

        # GPU warmup skipped — dummy tensors incompatible with STHN architecture
        logger.info("GPU warmup skipped — STHN initialises on first real frame")

        return model

    # ── Preprocessing ─────────────────────────────────────────────────────────

    def _preprocess(self, img_bgr, size=256):
        import cv2
        h, w = img_bgr.shape[:2]
        side = min(h, w)
        y0 = (h - side) // 2
        x0 = (w - side) // 2
        img_bgr = img_bgr[y0:y0+side, x0:x0+side]
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img_rgb, (size, size))
        tensor = torch.from_numpy(img_resized).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std  = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        tensor = (tensor - mean) / std
        return tensor.unsqueeze(0).to(DEVICE)
    
    # ── Homography corners → lat/lon ──────────────────────────────────────────

    def _corners_to_latlon(self, corners_px, ref_lat, ref_lon, mpp):
        """
        corners_px : (4, 2) predicted corner displacements in pixels
                     relative to the patch centre.
        Returns estimated (lat, lon) of the drone nadir point.
        """
        cx_px = float(corners_px[:, 0].mean())
        cy_px = float(corners_px[:, 1].mean())

        d_lon = cx_px * mpp / (111320.0 * math.cos(math.radians(ref_lat)))
        d_lat = -cy_px * mpp / 111320.0   # image y-axis is south-positive

        return ref_lat + d_lat, ref_lon + d_lon

    # ── Main inference ────────────────────────────────────────────────────────

    @torch.no_grad()
    def localize(self, query_bgr: np.ndarray, prior_lat: float, prior_lon: float) -> dict:
        """
        Run STHN inference.

        Parameters
        ----------
        query_bgr  : drone camera frame (BGR, any size)
        prior_lat  : GPS prior latitude  (or dead-reckoning estimate)
        prior_lon  : GPS prior longitude

        Returns
        -------
        dict with keys:
            success          bool
            lat, lon         corrected position (float)
            conf             confidence 0–1
            dt_ms            inference time ms
            raw_lat/raw_lon  uncorrected position
            rms_px           RMS corner displacement in pixels
        """
        t0 = time.perf_counter()

        _FAIL = {"success": False, "lat": prior_lat, "lon": prior_lon,
                 "conf": 0.0, "dt_ms": 0.0, "rms_px": 0.0}

        # 1. Fetch satellite reference patch
        try:
            sat_patch, ref_lat, ref_lon, mpp = _stitch_satellite_patch(
                self._conn, prior_lat, prior_lon, self.zoom, self.patch_size
            )
        except Exception as e:
            logger.warning(f"Tile fetch failed: {e}")
            return _FAIL

        # 2. Preprocess
        q_t  = self._preprocess(query_bgr,  size=self.patch_size)
        db_t = self._preprocess(sat_patch,  size=self.patch_size)

        # 3. Forward pass
        #    STHN Network.forward(query, db) — positional args, not kwargs.
        #    The model returns predicted 4-corner offsets: shape (1,4,2) or (1,8).
        try:
            # STHN is not nn.Module — use set_input + forward pattern
            pass  # empty_cache disabled (crashes Jetson allocator)
            self._model.set_input(q_t, db_t, flow_gt=torch.zeros(1, 2, 2, 2, device=self.device))
            with torch.no_grad():
                self._model.forward(for_training=False)
            pred = self._model.four_pred  # shape (1, 2, 2, 2)
        except Exception as e:
            logger.error(f"STHN forward failed: {e}")
            return _FAIL

        # 4. Normalise output → (4, 2)
        pred_np = pred.squeeze().cpu().float().numpy()
        if pred_np.ndim == 1:
            if pred_np.size == 8:
                pred_np = pred_np.reshape(4, 2)
            else:
                # Unexpected output size — abort gracefully
                logger.warning(f"Unexpected STHN output shape: {pred_np.shape}")
                return _FAIL

        # Scale from normalised [-1..1] to pixel coords
        pred_px = pred_np * (self.patch_size / 2.0)

        # 5. Confidence: inverse RMS displacement (large disp → low conf)
        rms = float(np.sqrt((pred_px ** 2).mean()))
        max_expected_px = self.patch_size * 0.3
        conf = float(np.clip(1.0 - rms / max_expected_px, 0.0, 1.0))

        # PATCHED: reject low-confidence predictions so the receiver can
        # fall back to dead-reckoning instead of jumping to a wrong point.
        if conf < self.conf_threshold:
            logger.warning(
                f"STHN low confidence {conf:.2f} < {self.conf_threshold:.2f} "
                f"(rms={rms:.1f}px) → rejected, receiver will dead-reckon")
            return {"success": False, "lat": prior_lat, "lon": prior_lon,
                    "conf": conf, "dt_ms": (time.perf_counter()-t0)*1000.0,
                    "rms_px": rms, "raw_lat": prior_lat, "raw_lon": prior_lon}

        # 6. Convert corners → lat/lon
        raw_lat, raw_lon = self._corners_to_latlon(pred_px, ref_lat, ref_lon, mpp)

        # 7. Bias correction (Bing ↔ ESRI alignment at zoom 17)
        corr_lat, corr_lon = _apply_bias_correction(raw_lat, raw_lon)

        # 8. Rolling average to smooth jitter
        self._lat_buf.append(corr_lat)
        self._lon_buf.append(corr_lon)
        avg_lat = float(np.mean(self._lat_buf))
        avg_lon = float(np.mean(self._lon_buf))

        dt_ms = (time.perf_counter() - t0) * 1000.0

        logger.debug(
            f"Night fix: ({avg_lat:.6f}, {avg_lon:.6f})  conf={conf:.2f}  dt={dt_ms:.1f}ms"
        )

        return {
            "success": True,
            "lat":     avg_lat,
            "lon":     avg_lon,
            "raw_lat": raw_lat,
            "raw_lon": raw_lon,
            "conf":    conf,
            "rms_px":  rms,
            "dt_ms":   dt_ms,
        }

    def reset_rolling(self):
        self._lat_buf.clear()
        self._lon_buf.clear()
