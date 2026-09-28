"""
night_localizer.py  —  NAVERA Night Localization Engine
Wraps STHN local_pipeline for drone-to-satellite homography matching.

Usage:
    localizer = NightLocalizer(sthn_dir, weights_path, mbtiles_path)
    result = localizer.localize(query_img_bgr, gps_prior_lat, gps_prior_lon)
"""

import sys
import math
import sqlite3
import logging
import time
from pathlib import Path

import numpy as np
import cv2
import torch

logger = logging.getLogger("night_localizer")

# STHN "one_stage" model geometry — MUST match the weights' one_stage/config.json
# (corr_level 4, database_size 1536, resize_width 256). The satellite search
# area is DATABASE_SIZE px at the tile GSD (z17 ≈ 0.97 m/px here, close to the
# ~1 m/px STHN was trained on); both images are fed to the network at
# RESIZE_WIDTH, and four_pred is expressed at that scale.
STHN_RESIZE_WIDTH  = 256
STHN_DATABASE_SIZE = 1536
STHN_CORR_LEVEL    = 4


# ─── Tile utilities (MBTiles → numpy) ────────────────────────────────────────

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


def _latlon_to_tile_frac(lat, lon, zoom):
    """Fractional XYZ tile coordinates (Web Mercator) of (lat, lon)."""
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


def _tile_frac_to_latlon(x, y, zoom):
    """Inverse of _latlon_to_tile_frac."""
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def _stitch_satellite_patch(conn, lat, lon, zoom, size):
    """
    Build a `size` x `size` px satellite patch CENTRED ON (lat, lon).

    The mosaic of 256 px tiles around the prior is cropped around the prior's
    own pixel position (not a tile centre, which can be half a tile away).

    Returns (patch_bgr, origin_x, origin_y, n_missing) where (origin_x,
    origin_y) are the fractional tile coordinates of the patch's top-left
    pixel edge — patch pixel (u, v) spans tile coords origin + (u, v) / 256 —
    and n_missing counts the tiles under the crop that are absent from the
    MBTiles (outside coverage).
    """
    xf, yf = _latlon_to_tile_frac(lat, lon, zoom)
    x0f = xf - size / 512.0          # crop edges in tile units (256 px per tile)
    y0f = yf - size / 512.0
    tx0, ty0 = int(math.floor(x0f)), int(math.floor(y0f))
    tx1 = int(math.floor(x0f + size / 256.0 - 1e-9))
    ty1 = int(math.floor(y0f + size / 256.0 - 1e-9))

    rows = []
    n_missing = 0
    for ty in range(ty0, ty1 + 1):
        row_tiles = []
        for tx in range(tx0, tx1 + 1):
            tile = _read_tile(conn, zoom, tx, ty)
            if tile is None:
                n_missing += 1
                tile = np.zeros((256, 256, 3), dtype=np.uint8)
            if tile.shape[:2] != (256, 256):
                tile = cv2.resize(tile, (256, 256))
            row_tiles.append(tile)
        rows.append(np.concatenate(row_tiles, axis=1))
    mosaic = np.concatenate(rows, axis=0)   # pixel (0,0) = tile (tx0, ty0)

    x0 = int(round((x0f - tx0) * 256.0))
    y0 = int(round((y0f - ty0) * 256.0))
    patch = mosaic[y0:y0 + size, x0:x0 + size]
    return patch, tx0 + x0 / 256.0, ty0 + y0 / 256.0, n_missing


# ─── Bing ↔ ESRI projection bias correction ──────────────────────────────────

# Map calibration offset (degrees), subtracted from every fix. A fixed
# Bing-vs-ESRI offset measured once over Sousse (-0.00004, +0.00006) used to be
# applied everywhere; an offset belongs to one map and must be measured for it,
# so the default is none.


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
    device     : 'cuda' or 'cpu'
    """

    def __init__(
        self,
        sthn_dir: str,
        weights: str,
        mbtiles: str,
        zoom: int = 17,
        device: str = None,
        conf_threshold: float = 0.30,
        mixed_precision: bool = False,
        map_offset_deg: tuple = (0.0, 0.0),
    ):
        self.zoom           = zoom
        self.conf_threshold = conf_threshold
        self.map_offset_deg = (float(map_offset_deg[0]), float(map_offset_deg[1]))
        self.mixed_precision = bool(mixed_precision)   # fp16 autocast au forward (network.py:110/139)
        self.device     = device or ("cuda" if torch.cuda.is_available() else "cpu")

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
            # Only modules that are really missing get a stand-in, and only
            # while network.py is being imported: a global MagicMock would
            # silently replace a real library for the rest of the process.
            installed = []
            for _dep in _MOCK_MODS:
                if _dep in sys.modules:
                    continue
                try:
                    if importlib.util.find_spec(_dep) is not None:
                        continue
                except (ImportError, ValueError):
                    pass
                sys.modules[_dep] = _mock.MagicMock()
                installed.append(_dep)
            spec = importlib.util.spec_from_file_location("_sthn_local_network", candidate)
            mod  = importlib.util.module_from_spec(spec)
            try:
                try:
                    spec.loader.exec_module(mod)
                finally:
                    for _dep in installed:
                        sys.modules.pop(_dep, None)
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
            resize=[STHN_RESIZE_WIDTH, STHN_RESIZE_WIDTH],
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
            resize_width=STHN_RESIZE_WIDTH,
            resize_height=STHN_RESIZE_WIDTH,
            database_size=STHN_DATABASE_SIZE,
            arch="IHN",
            two_stages=False,
            restore_ckpt=None,
            finetune=False,
            corr_level=STHN_CORR_LEVEL,
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

        # The published checkpoint stores the whole Network ("netG.<param>"),
        # while it is loaded into model.netG itself: strip that prefix.
        if state and all(k.startswith("netG.") for k in state):
            state = {k[len("netG."):]: v for k, v in state.items()}
        missing, unexpected = model.netG.load_state_dict(state, strict=False)
        if missing:
            # A wrong or re-prefixed checkpoint would otherwise leave the network
            # with random weights while reporting "loaded".
            raise RuntimeError(
                f"STHN checkpoint {weights_path} is missing {len(missing)} weights "
                f"(e.g. {missing[:3]}); refusing to run with random weights")
        if unexpected:
            logger.warning(f"STHN checkpoint has {len(unexpected)} unused keys (e.g. {unexpected[:3]})")
        model.netG = model.netG.to(self.device).eval()
        logger.info(f"STHN weights loaded from {weights_path}")

        # GPU warmup skipped — dummy tensors incompatible with STHN architecture
        logger.info("GPU warmup skipped — STHN initialises on first real frame")

        return model

    # ── Preprocessing ─────────────────────────────────────────────────────────

    def _preprocess(self, img_bgr, size=256, grey=False):
        """Centre-square crop, resize to `size`, RGB (or 3x grey) tensor in [0, 1].

        No ImageNet normalisation here: STHN's IHN.forward applies it itself,
        so normalising twice would feed the network out-of-distribution input.
        """
        h, w = img_bgr.shape[:2]
        side = min(h, w)
        y0 = (h - side) // 2
        x0 = (w - side) // 2
        img = img_bgr[y0:y0 + side, x0:x0 + side]
        if grey:
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = np.stack([g, g, g], axis=-1)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (size, size), interpolation=cv2.INTER_LINEAR)
        tensor = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1).float() / 255.0
        return tensor.unsqueeze(0).to(self.device)

    # ── Homography corners → lat/lon ──────────────────────────────────────────

    @staticmethod
    def _predicted_corners(four_pred, resize_width):
        """Predicted corners of the thermal frame inside the satellite patch.

        STHN's four_pred is [1, 2, 2, 2]: dim 1 is the coordinate (0 = x,
        1 = y), dims 2-3 the corner grid (row: top/bottom, col: left/right).
        Values are pixel DISPLACEMENTS at resize_width scale, added to the
        identity corners (0, rw-1) — see STHN_demo.visualize_result.
        Returns a (4, 2) array of (x, y) in TL, TR, BR, BL order.
        """
        fp = np.asarray(four_pred, dtype=np.float64).reshape(2, 2, 2)
        e = resize_width - 1.0
        org = np.array([[[0.0, e], [0.0, e]],      # x of TL, TR / BL, BR
                        [[0.0, 0.0], [e, e]]])     # y of TL, TR / BL, BR
        pts = fp + org
        return np.array([[pts[0, 0, 0], pts[1, 0, 0]],
                         [pts[0, 0, 1], pts[1, 0, 1]],
                         [pts[0, 1, 1], pts[1, 1, 1]],
                         [pts[0, 1, 0], pts[1, 1, 0]]])

    @staticmethod
    def _quad_consistency(corners):
        """Geometric plausibility of the predicted quad in [0, 1].

        1.0 = a square (what a nadir view of a square crop should map to);
        0.0 = self-intersecting or degenerate. This is NOT a calibrated
        probability of correctness — STHN outputs none — only a gate against
        geometrically impossible predictions.
        """
        c = np.asarray(corners)
        cross = []
        for i in range(4):
            a, b, d = c[i], c[(i + 1) % 4], c[(i + 2) % 4]
            cross.append((b[0] - a[0]) * (d[1] - b[1]) - (b[1] - a[1]) * (d[0] - b[0]))
        if not (all(x > 0 for x in cross) or all(x < 0 for x in cross)):
            return 0.0
        sides = [np.linalg.norm(c[(i + 1) % 4] - c[i]) for i in range(4)]
        diags = [np.linalg.norm(c[2] - c[0]), np.linalg.norm(c[3] - c[1])]
        if min(sides) <= 1e-6:
            return 0.0
        return float((min(sides) / max(sides)) * (min(diags) / max(diags)))

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

        # 1. Satellite reference patch centred on the prior
        try:
            sat_patch, origin_x, origin_y, n_missing = _stitch_satellite_patch(
                self._conn, prior_lat, prior_lon, self.zoom, STHN_DATABASE_SIZE
            )
        except Exception as e:
            logger.warning(f"Tile fetch failed: {e}")
            return _FAIL
        if n_missing:
            # Matching against black filler tiles is meaningless (outside coverage).
            logger.warning(f"{n_missing} satellite tiles missing around the prior")
            return _FAIL

        # 2. Preprocess: satellite RGB at full search size (STHN downsamples it
        #    itself), thermal as 3x grey at RESIZE_WIDTH, both in [0, 1]
        sat_t = self._preprocess(sat_patch, size=STHN_DATABASE_SIZE)
        thr_t = self._preprocess(query_bgr, size=STHN_RESIZE_WIDTH, grey=True)

        # 3. Forward pass. STHN's contract is set_input(A=satellite, B=thermal).
        try:
            self._model.set_input(sat_t, thr_t, flow_gt=torch.zeros(1, 2, 2, 2, device=self.device))
            with torch.no_grad():
                self._model.forward(for_training=False)
            pred = self._model.four_pred
        except Exception as e:
            logger.error(f"STHN forward failed: {e}")
            return _FAIL
        if tuple(pred.shape) != (1, 2, 2, 2):
            logger.warning(f"Unexpected STHN output shape: {tuple(pred.shape)}")
            return _FAIL
        pred_np = pred.detach().cpu().float().numpy()
        if not np.all(np.isfinite(pred_np)):
            logger.warning("STHN output is not finite → rejected")
            return _FAIL

        # 4. Where the thermal frame's centre lies in the satellite patch
        corners = self._predicted_corners(pred_np, STHN_RESIZE_WIDTH)
        conf = self._quad_consistency(corners)
        cx, cy = corners.mean(axis=0)           # RESIZE_WIDTH pixel coordinates
        scale = STHN_DATABASE_SIZE / float(STHN_RESIZE_WIDTH)   # → satellite patch px
        u = (cx + 0.5) * scale
        v = (cy + 0.5) * scale
        half = STHN_DATABASE_SIZE / 2.0
        disp_px = float(np.hypot(u - half, v - half))
        inside = 0.0 <= u <= STHN_DATABASE_SIZE and 0.0 <= v <= STHN_DATABASE_SIZE
        dt_ms = (time.perf_counter() - t0) * 1000.0

        if not inside or conf < self.conf_threshold:
            logger.warning(
                f"STHN prediction rejected: consistency {conf:.2f} (min {self.conf_threshold:.2f}), "
                f"centre {'inside' if inside else 'OUTSIDE'} patch, shift {disp_px:.1f}px")
            return {"success": False, "lat": prior_lat, "lon": prior_lon,
                    "conf": conf, "dt_ms": dt_ms, "rms_px": disp_px,
                    "raw_lat": prior_lat, "raw_lon": prior_lon}

        # 5. Patch pixels → geographic position (exact Web Mercator, 256 px/tile)
        raw_lat, raw_lon = _tile_frac_to_latlon(
            origin_x + u / 256.0, origin_y + v / 256.0, self.zoom)

        # 6. Map calibration offset (none unless measured for this map)
        corr_lat = raw_lat - self.map_offset_deg[0]
        corr_lon = raw_lon - self.map_offset_deg[1]

        logger.debug(
            f"Night fix: ({corr_lat:.6f}, {corr_lon:.6f})  conf={conf:.2f}  dt={dt_ms:.1f}ms"
        )

        return {
            "success": True,
            "lat":     corr_lat,
            "lon":     corr_lon,
            "raw_lat": raw_lat,
            "raw_lon": raw_lon,
            "conf":    conf,
            "rms_px":  disp_px,
            "dt_ms":   dt_ms,
        }

