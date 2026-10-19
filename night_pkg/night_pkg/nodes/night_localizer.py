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
# Ground footprint of the thermal query STHN was trained with: a 512 px crop at
# the satellite resolution (then resized to RESIZE_WIDTH). A query at another
# scale makes the prediction wrong while the consistency score stays high
# (measured: 4.7 km median drift on the replay set, LOC-16), so every frame is
# resampled to this footprint from the altitude and the camera field of view.
STHN_QUERY_PX      = 512
# Share of the reference square the (rotated) frame must cover. Measured on
# synthetic frames: at 0.77 (300 m, 84 deg camera, diagonal heading) tracking
# ran away to 2.4 km while the consistency stayed ~0.9; >= 0.88 (350 m) held
# at every heading.
MIN_QUERY_COVERAGE = 0.85
# Share of the reference the frame's ground pixels must cover once the empty wedges of a
# straightened (tilted) frame are removed; the wedges are filled with the mean, which
# STHN tolerated down to ~0.6 on synthetic frames (tilt 20 deg at 400 m: 0.57-0.71).
MIN_GROUND_COVERAGE = 0.55


def ground_resolution_m(lat, zoom):
    """Metres per pixel of a 256 px Web Mercator tile at this latitude."""
    return 40_075_016.686 * math.cos(math.radians(lat)) / (2 ** zoom) / 256.0


def image_valid_mask(img_bgr):
    """Pixels that carry a picture: the black wedges a straightened (tilted) frame or an
    undistorted lens leaves at its edges are not ground. Only exact-zero regions wide
    enough to survive a 7 px opening AND touching the image edge count as empty, so
    scattered clipped pixels (AGC) and cold objects inside the frame stay valid."""
    g = img_bgr if img_bgr.ndim == 2 else cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    zero = (g == 0).astype(np.uint8)
    if not zero.any():
        return np.full(g.shape, 255, np.uint8)
    zero = cv2.morphologyEx(zero, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab = cv2.connectedComponents(zero, connectivity=4)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    empty = np.isin(lab, edge[edge > 0])
    return np.where(empty, 0, 255).astype(np.uint8)


def normalize_query(img_bgr, lat, zoom, altitude_m, hfov_deg, heading_deg=None, return_mask=False):
    """Thermal frame → north-up, satellite-resolution, STHN_QUERY_PX square.

    altitude_m: height above ground; hfov_deg: horizontal field of view of the
    (nadir) camera; heading_deg: direction of the image top, clockwise from
    north (None = assume north-up). Returns (query_bgr, info) or (None, info)
    with info["reason"] when the frame cannot be brought to scale; with
    return_mask, a third value: the query's ground-covered pixels (255) or None.
    Empty borders of the frame (image_valid_mask) do not count as coverage.
    """
    info = {}

    def _out(q, m=None):
        return (q, info, m) if return_mask else (q, info)
    if altitude_m is None or not math.isfinite(altitude_m):
        info["reason"] = "altitude unknown — the thermal image cannot be scaled to the map"
        return _out(None)
    if altitude_m <= 1.0:
        info["reason"] = f"vehicle on the ground ({altitude_m:.0f} m): no ground footprint to match"
        return _out(None)
    if hfov_deg is None or not (1.0 < hfov_deg < 170.0):
        info["reason"] = "camera field of view not configured (camera_hfov_deg)"
        return _out(None)
    h, w = img_bgr.shape[:2]
    footprint_w = 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0)
    gsd_cam = footprint_w / w
    gsd_map = ground_resolution_m(lat, zoom)
    scale = gsd_cam / gsd_map
    info.update(footprint_w_m=footprint_w, footprint_h_m=footprint_w * h / w,
                gsd_cam_m=gsd_cam, gsd_map_m=gsd_map, scale=scale,
                heading_deg=heading_deg)
    valid = image_valid_mask(img_bgr)
    empty = 1.0 - float(np.count_nonzero(valid)) / valid.size
    info["empty_share"] = empty
    # channel 0: the frame's footprint; channel 1: its pixels that show ground
    mask = np.dstack([np.full_like(valid, 255), valid])
    if heading_deg is not None and math.isfinite(heading_deg) and abs(heading_deg) > 0.01:
        # The image top points along the heading, i.e. the camera image is the
        # north-up view turned counter-clockwise by the heading (OpenCV: positive
        # angle = counter-clockwise on screen). Turning it back clockwise by the
        # heading (negative angle) brings north to the top.
        diag = int(math.ceil(math.hypot(w, h)))
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -float(heading_deg), 1.0)
        M[0, 2] += (diag - w) / 2.0
        M[1, 2] += (diag - h) / 2.0
        img_bgr = cv2.warpAffine(img_bgr, M, (diag, diag), flags=cv2.INTER_LINEAR)
        mask = cv2.warpAffine(mask, M, (diag, diag), flags=cv2.INTER_NEAREST)
        h, w = diag, diag
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    img = cv2.resize(img_bgr, (nw, nh), interpolation=interp)
    mask = cv2.resize(mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
    q = STHN_QUERY_PX
    out = np.zeros((q, q, 3), np.uint8)
    out_mask = np.zeros((q, q, 2), np.uint8)
    sx, sy = (nw - q) // 2, (nh - q) // 2          # source crop origin (may be < 0)
    x0, y0 = max(0, -sx), max(0, -sy)
    x1, y1 = min(q, nw - sx), min(q, nh - sy)
    out[y0:y1, x0:x1] = img[y0 + sy:y1 + sy, x0 + sx:x1 + sx]
    out_mask[y0:y1, x0:x1] = mask[y0 + sy:y1 + sy, x0 + sx:x1 + sx]
    coverage = float(np.count_nonzero(out_mask[..., 0])) / (q * q)
    ground = float(np.count_nonzero(out_mask[..., 1])) / (q * q)
    out_mask = out_mask[..., 1].copy()
    info["coverage"] = coverage
    info["ground_coverage"] = ground
    if coverage >= MIN_QUERY_COVERAGE and ground < MIN_GROUND_COVERAGE:
        info["reason"] = (f"only {ground:.0%} of the {q * gsd_map:.0f} m reference shows ground: "
                          f"{empty:.0%} of the frame is empty (camera tilted, straightened frame)")
        return _out(None)
    if coverage < MIN_QUERY_COVERAGE:
        info["reason"] = (f"camera footprint too small for night matching ({footprint_w:.0f} m wide "
                          f"at {altitude_m:.0f} m, covers {coverage:.0%} of the {q * gsd_map:.0f} m "
                          f"reference) — fly higher")
        return _out(None)
    if coverage < 0.999:                           # fill the uncovered border with the mean
        mean = cv2.mean(out, mask=out_mask)[:3]
        out[out_mask == 0] = np.array(mean, dtype=np.uint8)
    return _out(out, out_mask)


def stretch_contrast(query_bgr, mask=None, lo_pct=1.0, hi_pct=99.0):
    """Percentile stretch of the query's ground pixels to the full 8-bit range.

    A thermal camera's own gain control decides how the scene fills the 8 bits: with a
    linear (min-max) AGC a fire or the sun's reflection takes the top of the range and
    the whole ground is left in a few grey levels, and at thermal crossover the scene
    is faint. STHN then sees an almost flat frame. Stretching the 1-99 % percentiles
    of the ground (empty borders excluded) restores the contrast; a frame already
    stretched by the camera is left nearly unchanged. Returns a new BGR image."""
    g = cv2.cvtColor(query_bgr, cv2.COLOR_BGR2GRAY) if query_bgr.ndim == 3 else query_bgr
    vals = g[mask > 0] if mask is not None and np.count_nonzero(mask) > 100 else g.ravel()
    lo, hi = np.percentile(vals, (lo_pct, hi_pct))
    if hi - lo < 1.0:
        return query_bgr                     # flat: nothing to stretch (refused later)
    out = np.clip((g.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    if mask is not None:
        out[mask == 0] = int(round(float(np.mean(out[mask > 0])))) if np.count_nonzero(mask) else 0
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def _edges(grey):
    """Polarity-free structure image: gradient magnitude of the lightly smoothed picture
    (a hot road on a cool field and a dark road on a bright field give the same edges)."""
    g = cv2.GaussianBlur(grey.astype(np.float32), (0, 0), 1.2)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.GaussianBlur(cv2.magnitude(gx, gy), (0, 0), 1.0)


def _ncc(a, b, m):
    a, b = a[m], b[m]
    if a.size < 100:
        return 0.0
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum()) / d if d > 1e-9 else 0.0


VERIFY_SIZE = 256           # the map check runs at STHN's input scale (~2 m/px)
# Gates measured on synthetic frames (navera_tools/bench/night_conditions.py, 2026-10-17;
# docs/VALIDATION_STATUS.md). The re-check is the strong one: from two search centres
# 150 m apart, correct fixes mostly agreed within 25 m while wrong ones disagreed by
# 27-480 m. The map correlation only refuses frames that do not resemble the map at all.
MIN_MATCH_NCC = 0.05
RECHECK_OFFSET_M = 150.0
RECHECK_MAX_M = 25.0
# Stated 1-sigma (per axis, metres) of a confirmed STHN fix (D3), fitted on 1389 accepted
# synthetic fixes (navera_tools/bench/night_conditions.py, 78 conditions x 30 frames,
# 2026-10-19): sigma = hypot(8 m + 1 % of the height above 400 m, 0.8 x the disagreement
# between the two search centres). 99.4 % of the fixes within 3 sigma (random half held
# out: 99.6 %); fitted on the city alone, it covered farmland only 96.4 %: terrain matters,
# and real thermal imagery is not measured.
SIGMA_BASE_M = 8.0
SIGMA_PER_M_ABOVE_400 = 0.01
SIGMA_RECHECK_K = 0.8


def fix_sigma_m(altitude_m, recheck_m):
    """The stated 1-sigma of a fix confirmed from two search centres (see SIGMA_BASE_M)."""
    base = SIGMA_BASE_M + SIGMA_PER_M_ABOVE_400 * max(0.0, float(altitude_m or 400.0) - 400.0)
    return math.hypot(base, SIGMA_RECHECK_K * float(recheck_m))


def verify_match(query_bgr, query_mask, sat_bgr, corners_rw, resize_width=256):
    """Does the satellite map, cut where STHN put the frame, look like the frame?

    STHN always returns a quad, even for a frame with no information (fog, cloud,
    sea, sensor noise): its own geometric consistency stays ~1 and the position
    sits near the search centre. This check is independent of the network: the
    satellite patch is warped into the frame by the predicted homography and the
    two edge images are correlated (NCC of gradient magnitudes: polarity-free, so
    black-hot and white-hot frames score alike).

    Returns {"ncc": the correlation}; the threshold is the caller's. Synthetic
    frames: correct fixes 0.08 (5th percentile) to 0.30 (median); a real thermal
    camera will score lower against a daylight map (not measured).
    """
    n = VERIFY_SIZE
    q = cv2.cvtColor(query_bgr, cv2.COLOR_BGR2GRAY) if query_bgr.ndim == 3 else query_bgr
    q = cv2.resize(q, (n, n), interpolation=cv2.INTER_AREA)
    m = np.full((n, n), 255, np.uint8) if query_mask is None else cv2.resize(
        query_mask, (n, n), interpolation=cv2.INTER_NEAREST)
    m = cv2.erode(m, np.ones((9, 9), np.uint8)) > 0
    s = cv2.cvtColor(sat_bgr, cv2.COLOR_BGR2GRAY) if sat_bgr.ndim == 3 else sat_bgr
    k = s.shape[1] / float(resize_width)                   # rw pixel -> satellite patch pixel
    src = np.array([[0, 0], [n - 1, 0], [n - 1, n - 1], [0, n - 1]], np.float32)
    dst = ((np.asarray(corners_rw, np.float64) + 0.5) * k - 0.5).astype(np.float32)
    H = cv2.getPerspectiveTransform(src, dst)              # frame pixel -> satellite pixel
    w = cv2.warpPerspective(s, H, (n, n), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                            borderMode=cv2.BORDER_REFLECT)
    return {"ncc": _ncc(_edges(q), _edges(w), m)}


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

def _ensure_cuda_linalg(device) -> bool:
    """Make torch.linalg.solve usable on CUDA; returns True if a CPU route was installed.

    STHN solves small 8x8 systems (kornia get_perspective_transform) at every
    iteration. The Jetson PyTorch build for JetPack 6 needs a newer cuSOLVER
    than JetPack ships, so CUDA linear algebra fails to load ("undefined
    symbol cusolverDn..."). Those systems are tiny: solving them on the CPU
    costs nothing and gives the same result (measured: <= 0.02 m difference,
    network ~6x faster on GPU than full CPU). Installed only when needed.
    """
    if str(device) != "cuda":
        return False
    try:
        torch.linalg.solve(torch.eye(2, device="cuda"), torch.ones(2, 1, device="cuda"))
        return False
    except RuntimeError as e:
        _solve = torch.linalg.solve

        def _cpu_solve(A, B, *args, **kwargs):
            if A.is_cuda:
                return _solve(A.cpu(), B.cpu(), *args, **kwargs).to(A.device)
            return _solve(A, B, *args, **kwargs)
        torch.linalg.solve = _cpu_solve
        logger.warning(f"CUDA linear algebra unavailable ({str(e).splitlines()[0][:90]}) — "
                       "small homography solves run on the CPU, the network on the GPU")
        return True


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
        min_match_ncc: float = MIN_MATCH_NCC,
        recheck_offset_m: float = RECHECK_OFFSET_M,
        recheck_max_m: float = RECHECK_MAX_M,
        mixed_precision: bool = False,
        map_offset_deg: tuple = (0.0, 0.0),
        contrast_stretch: bool = True,
    ):
        self.zoom           = zoom
        # percentile stretch of the query before STHN (stretch_contrast)
        self.contrast_stretch = bool(contrast_stretch)
        self.conf_threshold = conf_threshold
        # map-check gate (verify_match); None = measured and reported, not enforced
        self.min_match_ncc = min_match_ncc
        # second-centre re-check (_recheck): offset of the second search centre, and the
        # largest disagreement accepted (None = measured, not enforced)
        self.recheck_offset_m = recheck_offset_m
        self.recheck_max_m = recheck_max_m
        self.map_offset_deg = (float(map_offset_deg[0]), float(map_offset_deg[1]))
        self.mixed_precision = bool(mixed_precision)   # fp16 autocast au forward (network.py:110/139)
        self.device     = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Insert STHN into sys.path
        sthn_dir = str(Path(sthn_dir).resolve())
        self._sthn_dir = sthn_dir
        if sthn_dir not in sys.path:
            sys.path.insert(0, sthn_dir)

        _ensure_cuda_linalg(self.device)

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
        # The STHN directory given by the caller — not sys.path[0], which the
        # first load changes (a second NightLocalizer in the same process then
        # found nothing).
        sthn_root = Path(self._sthn_dir)
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

    def localize(self, query_bgr: np.ndarray, prior_lat: float, prior_lon: float,
                 altitude_m: float = None, hfov_deg: float = None,
                 heading_deg: float = None, require_scale: bool = True,
                 heading_retry_deg=(), height_retry=()) -> dict:
        """STHN fix (see _localize_once); when the map check fails and heading_retry_deg
        is given (e.g. (10, -10, 20, -20)), the frame is tried again turned by each offset
        and the first verified fix is kept (STHN does not absorb a heading error above
        ~5-10 deg: the frame must be north-up). height_retry (relative, e.g. (0.1, -0.1)):
        then the frame is tried at the height scaled by each (STHN does not absorb a ~10 %
        scale error either: a barometric or terrain height, or the stated field of view).
        Costs one more inference per retry, only on frames that failed the map check."""
        def attempt(heading, alt):
            a = self._localize_once(query_bgr, prior_lat, prior_lon, alt, hfov_deg,
                                    heading, require_scale)
            if a.get("success") and self.recheck_offset_m:
                a = self._recheck(a, query_bgr, prior_lat, prior_lon, alt, hfov_deg,
                                  heading, require_scale)
                if a.get("success") and a.get("recheck_m") is not None:
                    a["sigma_m"] = fix_sigma_m(alt, a["recheck_m"])
            return a

        r = attempt(heading_deg, altitude_m)
        small = str(r.get("reason") or "").startswith("camera footprint too small")
        if r.get("success") or not (r.get("map_check_failed") or small):
            return r
        # a footprint too small for the stated height: only a greater height can help
        tries = [] if heading_deg is None or small else [(float(d), 0.0) for d in heading_retry_deg]
        tries += [] if not altitude_m else [(0.0, float(f)) for f in height_retry if f > 0 or not small]
        if not tries:
            return r
        total = r["dt_ms"]
        for d, f in tries:
            t = attempt(None if heading_deg is None else (heading_deg + d) % 360.0, altitude_m * (1.0 + f))
            total += t["dt_ms"]
            if t.get("success"):
                if d:
                    t["heading_correction_deg"] = d
                if f:
                    t["height_correction"] = f
                t["dt_ms"] = total
                return t
        r["dt_ms"] = total
        r["reason"] += " (also tried: " + ", ".join(
            f"heading {d:+g} deg" if d else f"height {f:+.0%}" for d, f in tries) + ")"
        return r

    def _recheck(self, r, query_bgr, prior_lat, prior_lon, altitude_m, hfov_deg, heading_deg,
                 require_scale):
        """Second opinion from a search centre moved by recheck_offset_m: a frame that
        really matches the map lands on the same ground from both centres; a frame with
        no usable information (cloud, fog, sea, noise, wrong heading) stays near each
        search centre, so the two answers differ by about the offset."""
        d = self.recheck_offset_m / math.sqrt(2.0)              # towards the north-east
        lat2 = prior_lat + d / 111_320.0
        lon2 = prior_lon + d / (111_320.0 * math.cos(math.radians(prior_lat)))
        s = self._localize_once(query_bgr, lat2, lon2, altitude_m, hfov_deg, heading_deg,
                                require_scale)
        r["dt_ms"] += s["dt_ms"]
        if not s.get("success"):
            gap = None
        else:
            dn = (s["lat"] - r["lat"]) * 111_320.0
            de = (s["lon"] - r["lon"]) * 111_320.0 * math.cos(math.radians(r["lat"]))
            gap = math.hypot(dn, de)
        r["recheck_m"] = gap
        if self.recheck_max_m is not None and (gap is None or gap > self.recheck_max_m):
            why = ("not confirmed from a second search centre "
                   + (f"({gap:.0f} m apart, max {self.recheck_max_m:.0f} m)" if gap is not None
                      else f"(second try failed: {s.get('reason', 'rejected')})"))
            logger.warning(f"STHN prediction rejected: {why}")
            r.update(success=False, lat=prior_lat, lon=prior_lon, reason=why, map_check_failed=True)
        else:
            # the two answers agree: their mean, which halves the network's own spread
            r["lat"], r["lon"] = (r["lat"] + s["lat"]) / 2.0, (r["lon"] + s["lon"]) / 2.0
        return r

    @torch.no_grad()
    def _localize_once(self, query_bgr: np.ndarray, prior_lat: float, prior_lon: float,
                       altitude_m: float = None, hfov_deg: float = None,
                       heading_deg: float = None, require_scale: bool = True) -> dict:
        """
        Run STHN inference.

        Parameters
        ----------
        query_bgr  : drone camera frame (BGR, any size)
        prior_lat  : GPS prior latitude  (or dead-reckoning estimate)
        prior_lon  : GPS prior longitude
        altitude_m, hfov_deg, heading_deg : camera geometry, used to resample the
            frame to the scale STHN was trained on (normalize_query). With
            require_scale and no altitude / field of view, no position is given.

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
        span = STHN_DATABASE_SIZE * ground_resolution_m(prior_lat, self.zoom)
        search = {"search_center": [prior_lat, prior_lon], "search_size_m": span}
        _FAIL.update(search)

        # 0. Bring the thermal frame to the map's scale and orientation
        query, qinfo, qmask = normalize_query(query_bgr, prior_lat, self.zoom, altitude_m,
                                              hfov_deg, heading_deg, return_mask=True)
        _FAIL["query"] = {k: v for k, v in qinfo.items() if k != "reason"}
        if query is None:
            if require_scale:
                _FAIL["reason"] = qinfo["reason"]
                return _FAIL
            query = query_bgr                     # legacy: unscaled (known to drift)
            qmask = None
        if self.contrast_stretch:
            query = stretch_contrast(query, qmask)

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
        thr_t = self._preprocess(query, size=STHN_RESIZE_WIDTH, grey=True)

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

        verify = None
        if inside and conf >= self.conf_threshold:
            verify = verify_match(query, qmask, sat_patch, corners, STHN_RESIZE_WIDTH)
            dt_ms = (time.perf_counter() - t0) * 1000.0
        weak = None
        if verify is not None:
            if self.min_match_ncc is not None and verify["ncc"] < self.min_match_ncc:
                weak = (f"map check failed: frame and map correlate {verify['ncc']:.2f} "
                        f"(min {self.min_match_ncc:.2f})")
        if weak:
            logger.warning(f"STHN prediction rejected: {weak}")
            return {"success": False, "lat": prior_lat, "lon": prior_lon,
                    "conf": conf, "dt_ms": dt_ms, "rms_px": disp_px, "verify": verify,
                    "raw_lat": prior_lat, "raw_lon": prior_lon, **search,
                    "query": _FAIL["query"], "reason": weak, "map_check_failed": True}
        if not inside or conf < self.conf_threshold:
            logger.warning(
                f"STHN prediction rejected: consistency {conf:.2f} (min {self.conf_threshold:.2f}), "
                f"centre {'inside' if inside else 'OUTSIDE'} patch, shift {disp_px:.1f}px")
            return {"success": False, "lat": prior_lat, "lon": prior_lon,
                    "conf": conf, "dt_ms": dt_ms, "rms_px": disp_px,
                    "raw_lat": prior_lat, "raw_lon": prior_lon, **search,
                    "query": _FAIL["query"],
                    "reason": f"consistency {conf:.2f} < {self.conf_threshold:.2f}" if inside
                    else "predicted centre outside the search area"}

        # 5. Patch pixels → geographic position (exact Web Mercator, 256 px/tile)
        raw_lat, raw_lon = _tile_frac_to_latlon(
            origin_x + u / 256.0, origin_y + v / 256.0, self.zoom)

        # 6. Map calibration offset (none unless measured for this map)
        corr_lat = raw_lat - self.map_offset_deg[0]
        corr_lon = raw_lon - self.map_offset_deg[1]

        logger.debug(
            f"Night fix: ({corr_lat:.6f}, {corr_lon:.6f})  conf={conf:.2f}  dt={dt_ms:.1f}ms"
        )

        quad = [list(_tile_frac_to_latlon(origin_x + (px + 0.5) * scale / 256.0,
                                          origin_y + (py + 0.5) * scale / 256.0, self.zoom))
                for px, py in corners]
        return {
            **search,
            "query":   _FAIL["query"],
            "footprint_quad": quad,
            "success": True,
            "lat":     corr_lat,
            "lon":     corr_lon,
            "raw_lat": raw_lat,
            "raw_lon": raw_lon,
            "conf":    conf,
            "rms_px":  disp_px,
            "verify":  verify,
            "dt_ms":   dt_ms,
        }

