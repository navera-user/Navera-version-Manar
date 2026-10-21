#!/usr/bin/env python3
"""Validate the 360 all-sky star solver (cn_pkg.allsky) on REAL night-sky frames from public all-sky cameras.

    python3 navera_tools/bench/realsky_validate.py calibrate --camera mascot --frames F1 F2 ... [--out lens.json]
    python3 navera_tools/bench/realsky_validate.py run --camera mascot --lens lens.json --frames ... --out res.jsonl
    python3 navera_tools/bench/realsky_validate.py summary res.jsonl [...]

The public cameras are single fisheye lenses looking up, not NAVERA's dual-fisheye 360, so this is a thin
adapter: one cn_pkg.sky360.Lens per camera (its "IMU" frame = the lens frame) and a fixed 'up' in that frame
(the camera is bolted to a roof: its zenith is constant, as NAVERA's mount + accelerometer would give it).
The frame is turned into the 8-bit image NAVERA's camera delivers and given UNCHANGED to allsky.locate (the
same detector, identification, focal refinement and quality gate as the flight node and the field service).

Lens and mount are measured from the stars of separate calibration nights with the TRUE position and time
(like lens_calib_wide does on the screen, and like the field's TiltCalibration learns the tilt of 'up' on its
first fixes with a reference position); the test frames are other nights. The calibration does not use the
solver under test: catalogue stars are put at their true alt/az (astropy, site pressure) and matched to the
detected spots by a brute-force grid, then refined by least squares on pixel residuals.

Reads only local files (downloaded once into NAVERA_TESTDATA/sky); no network at run time.
"""
import argparse
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if p not in sys.path:
        sys.path.insert(0, p)

from cn_pkg import allsky  # noqa: E402
from cn_pkg.sky360 import Lens  # noqa: E402

KM_PER_DEG = 111.2
WRONG_KM = 50.0

# the public cameras: site (WGS84) and how their files are read
CAMERAS: Dict[str, dict] = {
    # ESO Paranal MASCOT (Mini All-Sky Cloud Observation Tool): 580x512 CCD, 8 s, fixed, 16-bit FITS
    # DATE-OBS is the exposure's start; a fixed camera's star trails are centred at mid-exposure (8 s with the moon
    # up, 90 s without): the frame's time is DATE-OBS + EXPTIME/2 (with DATE-OBS, the 8 s and 90 s frames disagree
    # by ~0.17 deg = ~16 km east-west)
    "mascot": {"lat": -24.6276, "lon": -70.4051, "elev_m": 2635.0, "pressure_hpa": 743.0, "kind": "fits",
               "time": "mid"},
    # ESO Paranal ALPACA: 8750x8750 (2023-10 on; 4096 before) CMOS, 120 s on a tracking mount, 16-bit FITS;
    # binned to ~2000 px across so a pixel spans about what the Insta360's does
    "alpaca": {"lat": -24.6276, "lon": -70.4051, "elev_m": 2648.0, "pressure_hpa": 743.0, "kind": "fits",
               "target_px": 2048},
}


# ---------------------------------------------------------------------------------------------- frames ---

def read_fits(path: str) -> Tuple[np.ndarray, str, float]:
    """(float32 image, DATE-OBS UTC, exposure s) of a (possibly .Z/.gz compressed) FITS file."""
    from astropy.io import fits
    raw = open(path, "rb").read()
    if raw[:2] in (b"\x1f\x9d", b"\x1f\x8b"):
        raw = subprocess.run(["gzip", "-dc", path], capture_output=True, check=True).stdout
    with fits.open(io.BytesIO(raw)) as h:
        hd = h[0] if h[0].data is not None else h[1]
        return hd.data.astype(np.float32), str(hd.header["DATE-OBS"]), float(hd.header.get("EXPTIME", hd.header.get("EXPOSURE", 0.0)))


def to_8bit(d: np.ndarray, gamma: float = 2.2) -> np.ndarray:
    """A camera-like 8-bit frame: black at the 0.5th percentile, white at the 99.99th, display gamma.
    (NAVERA's camera delivers 8-bit gamma-encoded video; the solver's thresholds are in those DN.)"""
    lo, hi = np.percentile(d, [0.5, 99.99])
    v = np.clip((d - lo) / max(hi - lo, 1e-6), 0.0, 1.0) ** (1.0 / gamma)
    return (v * 255.0 + 0.5).astype(np.uint8)


def load_frame(path: str, cam: dict, mirror: bool = False) -> Tuple[np.ndarray, str, float]:
    """(8-bit frame, utc, exposure) prepared as the solver will see it: binned (ALPACA), mirrored if the file's
    row order makes the sky a mirror image, 8-bit. A '.png' next to a FITS (prepared earlier) is read as is."""
    import cv2
    if path.endswith(".png"):
        meta = json.load(open(path[:-4] + ".json"))
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        utc, exp = meta["utc"], meta["exposure"]
    else:
        d, utc, exp = read_fits(path)
        if cam.get("time") == "mid":
            utc = str(np.datetime64(utc) + np.timedelta64(int(round(exp * 500)), "ms"))
        if cam.get("target_px") and d.shape[0] > cam["target_px"] * 1.2:
            s = cam["target_px"] / d.shape[0]
            d = cv2.resize(d, (round(d.shape[1] * s), round(d.shape[0] * s)), interpolation=cv2.INTER_AREA)
        img = to_8bit(d)
    if mirror:
        img = np.ascontiguousarray(img[:, ::-1])
    return img, utc, exp


# --------------------------------------------------------------------------------------- truth geometry ---

def star_altaz(cat_vec: np.ndarray, utc: str, cam: dict) -> Tuple[np.ndarray, np.ndarray]:
    """True apparent (refracted, site pressure) alt, az (deg) of ICRS unit vectors."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from cn_pkg.nodes.celestial_math import obs_time
    ra = np.degrees(np.arctan2(cat_vec[:, 1], cat_vec[:, 0])) % 360
    dec = np.degrees(np.arcsin(np.clip(cat_vec[:, 2], -1, 1)))
    loc = EarthLocation(lat=cam["lat"] * u.deg, lon=cam["lon"] * u.deg, height=cam["elev_m"] * u.m)
    fr = AltAz(obstime=obs_time(utc), location=loc, pressure=cam["pressure_hpa"] * u.hPa,
               temperature=10 * u.deg_C, relative_humidity=0.2, obswl=0.55 * u.micron)
    aa = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs").transform_to(fr)
    return aa.alt.deg, aa.az.deg


def enu(alt, az):
    a, z = np.radians(alt), np.radians(az)
    return np.stack([np.cos(a) * np.sin(z), np.cos(a) * np.cos(z), np.sin(a)], axis=-1)


def body_altaz(name: str, utc: str, cam: dict) -> Tuple[float, float]:
    """(altitude deg, illuminated fraction) of 'sun' / 'moon' (astropy's built-in ephemeris: offline)."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, get_body
    from cn_pkg.nodes.celestial_math import obs_time
    t = obs_time(utc)
    loc = EarthLocation(lat=cam["lat"] * u.deg, lon=cam["lon"] * u.deg, height=cam["elev_m"] * u.m)
    b = get_body(name, t, loc)
    alt = float(b.transform_to(AltAz(obstime=t, location=loc)).alt.deg)
    if name != "moon":
        return alt, 1.0
    s = get_body("sun", t, loc)
    elong = float(s.separation(b).rad)
    return alt, (1 - math.cos(elong)) / 2


def great_circle_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * KM_PER_DEG


# ------------------------------------------------------------------------------------------ calibration ---

def _rotvec(w):
    from navera_tools.field.reprocess360 import rotvec
    return rotvec(w)


def bootstrap(spots_xy: np.ndarray, alt: np.ndarray, az: np.ndarray, shape, mirror_opts=(False, True)):
    """Brute force (mirror, centre, focal, turn) of an up-looking equidistant fisheye: the hypothesis that puts
    most bright catalogue stars on a detected spot. Returns dict(mirror, cx, cy, f, phi, n)."""
    from scipy.spatial import cKDTree
    H, W = shape
    zen = np.radians(90.0 - alt)
    best = None
    for mirror in mirror_opts:
        xy = spots_xy.copy()
        if mirror:
            xy[:, 0] = W - 1 - xy[:, 0]
        tree = cKDTree(xy)
        rmax = math.hypot(W, H) / 2
        for f in np.linspace(0.35, 1.7, 28) * (min(W, H) / 2) / (math.pi / 2):
            tol = max(2.0, 0.012 * f * math.pi / 2)
            phis = np.radians(np.arange(0, 360, 1.5))
            ang = phis[:, None] - np.radians(az)[None, :]        # proper rotation (camera looks up)
            for cx in np.linspace(W / 2 - 0.12 * W, W / 2 + 0.12 * W, 9):
                for cy in np.linspace(H / 2 - 0.12 * H, H / 2 + 0.12 * H, 9):
                    x = cx + f * zen * np.sin(ang)
                    y = cy - f * zen * np.cos(ang)
                    inside = (x > 2) & (x < W - 3) & (y > 2) & (y < H - 3) & (np.hypot(x - cx, y - cy) < rmax)
                    d, _ = tree.query(np.stack([x, y], -1).reshape(-1, 2), distance_upper_bound=tol)
                    n = (np.isfinite(d).reshape(x.shape) & inside).sum(axis=1)
                    k = int(np.argmax(n))
                    if best is None or n[k] > best["n"]:
                        best = dict(mirror=mirror, cx=float(cx), cy=float(cy), f=float(f), phi=float(phis[k]), n=int(n[k]))
    return best


def initial_rotation(phi: float) -> np.ndarray:
    """R_cam_enu (proper) of the bootstrap model x = cx + f zen sin(phi-az), y = cy - f zen cos(phi-az): lens frame
    x image right, y image down, z optical axis = up; north at image direction (sin phi, -cos phi)."""
    v_n = np.array([0.0, 1.0, 0.0])                      # north horizon (enu)
    v_e = np.array([1.0, 0.0, 0.0])
    cam_n = np.array([math.sin(phi), -math.cos(phi), 0.0])
    cam_e = np.array([-math.cos(phi), -math.sin(phi), 0.0])
    A = np.stack([v_n, v_e, np.array([0, 0, 1.0])], 1)
    B = np.stack([cam_n, cam_e, np.array([0, 0, 1.0])], 1)
    return allsky.wahba(A.T, B.T)


def calibrate(frames: List[str], cam: dict, min_alt: float = 8.0, cat_mag: float = 4.5, verbose: bool = True,
              per_frame: bool = False) -> dict:
    """Lens (cx, cy, f, k1, mirror) and mount (R_cam_enu, hence 'up' in the camera) from calibration frames with
    their true time; one rotation for all frames (a fixed camera), per-frame residuals reported. per_frame: each
    frame has its own small extra rotation (a camera on a tracking mount), only the lens is shared."""
    from scipy.optimize import least_squares
    from scipy.spatial import cKDTree
    cat = allsky.Catalogue(limit_mag=cat_mag, max_sep_deg=1.0, path=allsky.BUNDLED_CATALOGUE)
    data = []
    for fp in frames:
        img, utc, exp = load_frame(fp, cam)
        H, W = img.shape
        big = Lens("cal", W / 2, H / 2, 1.0, np.eye(3), radius=math.hypot(W, H))
        spots = np.array([(x, y) for x, y, _ in allsky.detect_spots(img, big, max_spots=300)])
        alt, az = star_altaz(cat.vec, utc, cam)
        data.append(dict(fp=fp, utc=utc, shape=(H, W), spots=spots, alt=alt, az=az, mag=cat.mag))
    # bootstrap on the frame with the most spots, bright stars only
    d0 = max(data, key=lambda d: len(d["spots"]))
    sel = (d0["alt"] > 20) & (d0["mag"] <= 3.0)
    b = bootstrap(d0["spots"][:120], d0["alt"][sel], d0["az"][sel], d0["shape"])
    if verbose:
        print("bootstrap", b, flush=True)
    mirror = b["mirror"]
    for d in data:
        if mirror:
            d["spots"][:, 0] = d["shape"][1] - 1 - d["spots"][:, 0]
    p = np.array([b["cx"], b["cy"], b["f"], 0.0, 0.0, 0.0, 0.0])      # cx cy f k1 rotvec(3) on top of R0
    if per_frame:
        p = np.r_[p, np.zeros(3 * len(data))]
    R0 = initial_rotation(b["phi"])

    def model(p, di=None):
        lens = Lens("cal", p[0], p[1], p[2], np.eye(3), k1=p[3])
        R = _rotvec(p[4:7]) @ R0
        if per_frame and di is not None:
            R = _rotvec(p[7 + 3 * di:10 + 3 * di]) @ R
        return lens, R

    pairs = None
    for tol_px, rounds in ((6.0, 2), (3.0, 2), (2.0, 3)):
        for _ in range(rounds):
            lens, R = model(p)
            pairs = []
            for di, d in enumerate(data):
                ok = d["alt"] > min_alt
                R = model(p, di)[1]
                x, y, th = lens.project(enu(d["alt"][ok], d["az"][ok]) @ R.T)
                inside = (x >= 0) & (x < d["shape"][1]) & (y >= 0) & (y < d["shape"][0])
                if len(d["spots"]) == 0:
                    continue
                tree = cKDTree(d["spots"])
                dist, k = tree.query(np.stack([x, y], -1), distance_upper_bound=tol_px * p[2] / 600.0 * 2)
                good = np.nonzero(np.isfinite(dist) & inside)[0]
                # one star per spot
                good = good[np.argsort(dist[good])]
                _, first = np.unique(k[good], return_index=True)
                for g in good[first]:
                    pairs.append((di, np.nonzero(ok)[0][g], k[g]))
            pairs = np.array(pairs)

            def res(q):
                lens, R = model(q)
                out = []
                for di, d in enumerate(data):
                    m = pairs[:, 0] == di
                    if not m.any():
                        continue
                    R = model(q, di)[1]
                    x, y, _ = lens.project(enu(d["alt"][pairs[m, 1]], d["az"][pairs[m, 1]]) @ R.T)
                    out.append(np.r_[x - d["spots"][pairs[m, 2], 0], y - d["spots"][pairs[m, 2], 1]])
                return np.concatenate(out)
            p = least_squares(res, p, loss="soft_l1", f_scale=1.0).x
            r = res(p).reshape(-1)
            if verbose:
                print(f"tol {tol_px}: {len(pairs)} pairs, rms {np.sqrt(np.mean(r ** 2)):.2f} px, median |r| "
                      f"{np.median(np.abs(r)):.2f} px, f {p[2]:.1f} k1 {p[3]:.4f} c ({p[0]:.1f},{p[1]:.1f})", flush=True)
    lens, R = model(p, 0)                    # per_frame: the first frame's rotation stands for the mount
    # per-frame rotation (a camera that moves between frames would show here), and the zenith each gives
    per = []
    for di, d in enumerate(data):
        m = pairs[:, 0] == di
        if m.sum() < 6:
            continue
        rays = allsky.unproject(lens, d["spots"][pairs[m, 2], 0], d["spots"][pairs[m, 2], 1])
        Rf = allsky.wahba(enu(d["alt"][pairs[m, 1]], d["az"][pairs[m, 1]]), rays)          # enu -> cam
        ang = math.degrees(math.acos(max(-1, min(1, float((Rf @ [0, 0, 1.0]) @ (R @ [0, 0, 1.0]))))))
        per.append(dict(frame=os.path.basename(d["fp"]), utc=d["utc"], n=int(m.sum()), up_offset_deg=round(ang, 4)))
    up = R @ np.array([0.0, 0.0, 1.0])
    return dict(cx=float(p[0]), cy=float(p[1]), f=float(p[2]), k1=float(p[3]), mirror=bool(mirror),
                R_cam_enu=R.tolist(), up_cam=up.tolist(), pairs=int(len(pairs)),
                rms_px=float(np.sqrt(np.mean(r ** 2))), frames=per)


# ------------------------------------------------------------------------------------------------- run ---

def lens_from(cal: dict, shape) -> Lens:
    H, W = shape
    # the circle the detector searches: everything the lens maps above the horizon (+ margin), clipped by the image
    r90 = cal["f"] * (math.pi / 2 + cal["k1"] * (math.pi / 2) ** 3)
    return Lens("cam", cal["cx"], cal["cy"], cal["f"], np.eye(3), k1=cal["k1"], radius=r90 + 20)


def per_frame_mount(img, lens: Lens, R0: np.ndarray, alt, az, min_alt: float = 10.0) -> Tuple[np.ndarray, int]:
    """The camera's rotation (R_cam_enu) in THIS frame, fitted on the truth (catalogue stars at their true
    alt/az matched to the detected spots, starting from the calibration's R0): for a camera on a tracking mount,
    whose 'up' moves from frame to frame. Independent of the solver under test."""
    from scipy.spatial import cKDTree
    spots = allsky.detect_spots(img, lens, max_spots=400)
    if len(spots) < 6:
        return R0, 0
    rays = allsky.unproject(lens, np.array([s[0] for s in spots]), np.array([s[1] for s in spots]))
    tree = cKDTree(rays)
    ok = alt > min_alt
    v = enu(alt[ok], az[ok])
    R, n = R0, 0
    for tol in (1.0, 0.5, 0.3, 0.3):
        d, k = tree.query(v @ R.T, distance_upper_bound=2 * math.sin(math.radians(tol) / 2))
        m = np.isfinite(d)
        if m.sum() < 6:
            return R0, 0
        R, n = allsky.wahba(v[m], rays[k[m]]), int(m.sum())
    return R, n


def transparency(img, lens: Lens, up: np.ndarray, R_cam_enu: np.ndarray, alt, az, mag, min_alt=20.0, mag_max=3.0):
    """Cloud/glare label from the truth (never fed to the solver): the fraction of catalogue stars <= mag_max,
    above min_alt and inside the image, that have a detected spot within 0.7 deg of their true place."""
    spots = allsky.detect_spots(img, lens, max_spots=600, up_imu=up, min_alt=min_alt - 3)
    sel = (alt > min_alt) & (mag <= mag_max)
    if not sel.any():
        return None, 0
    x, y, _ = lens.project(enu(alt[sel], az[sel]) @ R_cam_enu.T)
    H, W = img.shape
    inside = (x > 3) & (x < W - 4) & (y > 3) & (y < H - 4)
    if inside.sum() == 0:
        return None, 0
    if not spots:
        return 0.0, int(inside.sum())
    from scipy.spatial import cKDTree
    tree = cKDTree(allsky.unproject(lens, np.array([s[0] for s in spots]), np.array([s[1] for s in spots])))
    v = enu(alt[sel][inside], az[sel][inside]) @ R_cam_enu.T
    d, _ = tree.query(v, distance_upper_bound=2 * math.sin(math.radians(0.7) / 2))
    return float(np.isfinite(d).mean()), int(inside.sum())


def solve_both(img, up, utc, cat, lens):
    """The solver exactly as shipped (gated), and the same identification with the gate opened (to see what the
    gate refused or let through)."""
    t0 = time.perf_counter()
    r = allsky.locate(img, up, utc, cat, lenses=[lens], f_scales=(1.0,))
    dt = time.perf_counter() - t0
    if r.get("solved") and not r.get("retried_with"):
        return r, dict(r, gate_would_say=None), dt          # the gate passed the first identification as it is
    gate = allsky.accept
    seen = {}

    def open_gate(matched, rms_deg, p_chance, lens_disagree_deg=0.0):
        seen["why"] = gate(matched, rms_deg, p_chance, lens_disagree_deg)
        return None
    allsky.accept = open_gate
    try:
        u = allsky.locate(img, up, utc, cat, lenses=[lens], f_scales=(1.0,), retry_spots=0)
    finally:
        allsky.accept = gate
    u["gate_would_say"] = seen.get("why")
    return r, u, dt


def run(frames: List[str], cam: dict, cal: dict, out: str, catalogue_mag: float = 4.0, degrade: Optional[dict] = None,
        up_per_frame: bool = False):
    cat = allsky.Catalogue(limit_mag=catalogue_mag, path=allsky.BUNDLED_CATALOGUE)
    full = allsky.Catalogue(limit_mag=4.5, max_sep_deg=1.0, path=allsky.BUNDLED_CATALOGUE)
    R_cam_enu = np.array(cal["R_cam_enu"])
    up = np.array(cal["up_cam"])
    done = set()
    if os.path.exists(out):
        done = {json.loads(line)["frame"] for line in open(out) if line.strip()}
    with open(out, "a") as fh:
        for fp in frames:
            name = os.path.basename(fp)
            if name in done:
                continue
            try:
                img, utc, exp = load_frame(fp, cam, cal["mirror"])
            except Exception as e:                                   # a truncated download
                print("skip", name, e, flush=True)
                continue
            if degrade:
                img = degrade_frame(img, **degrade)
            lens = lens_from(cal, img.shape)
            alt, az = star_altaz(full.vec, utc, cam)
            n_mount = None
            if up_per_frame:                       # tracking mount: 'up' of this frame from the truth (see per_frame_mount)
                R_cam_enu, n_mount = per_frame_mount(img, lens, np.array(cal["R_cam_enu"]), alt, az)
                up = R_cam_enu @ np.array([0.0, 0.0, 1.0])
            tr, n_exp = transparency(img, lens, up, R_cam_enu, alt, az, full.mag)
            r, u, dt = solve_both(img, up, utc, cat, lens)
            sun, _ = body_altaz("sun", utc, cam)
            moon, illum = body_altaz("moon", utc, cam)
            rec = dict(frame=name, utc=utc, exposure=exp, sun_alt=round(sun, 2), moon_alt=round(moon, 2),
                       moon_illum=round(illum, 3), transparency=None if tr is None else round(tr, 3), bright_expected=n_exp,
                       solve_s=round(dt, 3), solved=bool(r.get("solved")), why=r.get("why"),
                       spots=r.get("spots"), rejected_spots=r.get("rejected_spots"), matched=r.get("matched"),
                       rms_deg=r.get("rms_deg"), p_chance=r.get("p_chance"), f_scale=r.get("f_scale"),
                       retried=r.get("retried_with"), mount_fit_stars=n_mount)
            if r.get("solved"):
                rec.update(lat=r["lat"], lon=r["lon"], err_km=round(great_circle_km(r["lat"], r["lon"], cam["lat"], cam["lon"]), 2),
                           err_n_km=round((r["lat"] - cam["lat"]) * KM_PER_DEG, 2),
                           err_e_km=round(((r["lon"] - cam["lon"] + 540) % 360 - 180) * KM_PER_DEG * math.cos(math.radians(cam["lat"])), 2),
                           k1_offset=r.get("k1_offset"), faintest_matched_mag=r.get("faintest_matched_mag"))
            # ungated identification (no retry): its error, and what the gate says of it
            if u.get("solved"):
                rec.update(ug_matched=u.get("matched"), ug_rms=u.get("rms_deg"), ug_p=u.get("p_chance"),
                           ug_err_km=round(great_circle_km(u["lat"], u["lon"], cam["lat"], cam["lon"]), 2),
                           ug_gate=u.get("gate_would_say"))
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(f"{name} sun {sun:5.1f} moon {moon:5.1f}/{illum:.2f} tr {rec['transparency']} spots {rec['spots']} "
                  f"solved {rec['solved']} err {rec.get('err_km')} m {rec['matched']} rms {rec['rms_deg']} p {rec['p_chance']} "
                  f"ug_err {rec.get('ug_err_km')} {dt:.2f}s {rec['why'] or ''}", flush=True)


def degrade_frame(img: np.ndarray, gain: float = 0.25, read_noise: float = 3.0, jpeg_q: int = 75, seed: int = 0) -> np.ndarray:
    """A short-exposure, compressed version of a real frame (the Insta360's video sees only the bright stars):
    the sky above the background is scaled by `gain` (gain 0.1 ~ 2.5 magnitudes shallower), Gaussian read noise
    added (DN), then JPEG at quality jpeg_q. The stars keep their real PSF, colour response and positions."""
    import cv2
    rng = np.random.default_rng(seed)
    lin = (img.astype(np.float32) / 255.0) ** 2.2
    bg = cv2.medianBlur((lin * 65535).astype(np.uint16), 5).astype(np.float32) / 65535
    bg = cv2.GaussianBlur(bg, (0, 0), 8)
    lin = bg + gain * (lin - bg)
    v = np.clip(lin, 0, 1) ** (1 / 2.2) * 255 + rng.normal(0, read_noise, lin.shape)
    v = np.clip(v, 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", v, [cv2.IMWRITE_JPEG_QUALITY, jpeg_q])
    return cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)


# --------------------------------------------------------------------------------------------- summary ---

def summary(paths: List[str]) -> str:
    rows = [json.loads(line) for p in paths for line in open(p) if line.strip()]
    lines = []

    def block(label, rs):
        if not rs:
            return
        ok = [r for r in rs if r["solved"]]
        e = np.array([r["err_km"] for r in ok]) if ok else np.array([])
        wrong = int((e > WRONG_KM).sum()) if len(e) else 0
        t = np.array([r["solve_s"] for r in rs])
        ug = [r for r in rs if r.get("ug_err_km") is not None]
        ug_right_refused = sum(1 for r in ug if r["ug_err_km"] <= WRONG_KM and not r["solved"])
        ug_wrong = sum(1 for r in ug if r["ug_err_km"] > WRONG_KM)
        lines.append(f"| {label} | {len(rs)} | {len(ok)} ({100 * len(ok) / len(rs):.0f}%) | "
                     + (f"{np.median(e):.1f} | {np.percentile(e, 90):.1f} | {e.max():.1f}" if len(e) else "- | - | -")
                     + f" | {wrong} | {ug_wrong} | {ug_right_refused} | {np.median(t):.2f} / {t.max():.2f} |")
    lines.append("| set | frames | solved | median km | p90 km | max km | wrong accepts (>50 km) | wrong ids refused by gate "
                 "| right ids refused by gate | solve s median / max |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    block("all", rows)
    dark = [r for r in rows if r["sun_alt"] < -18]
    block("night (sun < -18)", dark)
    block("twilight (-18 <= sun < -6)", [r for r in rows if -18 <= r["sun_alt"] < -6])
    block("night, moon down", [r for r in dark if r["moon_alt"] < 0])
    block("night, moon up < 50% lit", [r for r in dark if r["moon_alt"] >= 0 and r["moon_illum"] < 0.5])
    block("night, moon up >= 50% lit", [r for r in dark if r["moon_alt"] >= 0 and r["moon_illum"] >= 0.5])
    tr = [r for r in dark if r["transparency"] is not None]
    block("night, clear (>= 70% of mag<=3 stars seen)", [r for r in tr if r["transparency"] >= 0.7])
    block("night, partly cloudy/glare (30-70%)", [r for r in tr if 0.3 <= r["transparency"] < 0.7])
    block("night, overcast/glare (< 30%)", [r for r in tr if r["transparency"] < 0.3])
    why = {}
    for r in rows:
        if not r["solved"]:
            k = re.sub(r"\d[\d.e+-]*", "#", (r["why"] or "?").split(";")[0])
            why[k] = why.get(k, 0) + 1
    lines.append("")
    lines.append("refusal reasons: " + ", ".join(f"{k} x{v}" for k, v in sorted(why.items(), key=lambda kv: -kv[1])))
    # which tier of the gate let each fix through (allsky.accept): p <= MAX_P_CHANCE; p <= TIGHT and rms <= TIGHT;
    # p <= LOOSE and rms <= LOOSE (the third tier, from the screen campaign)
    tiers = {"p<=1e-6": 0, "tier 2 (p<=1e-4, rms<=0.12)": 0, "tier 3 (p<=1e-2, rms<=0.10)": 0}
    for r in rows:
        if r["solved"]:
            p, rms = r["p_chance"], r["rms_deg"]
            if p <= allsky.MAX_P_CHANCE:
                tiers["p<=1e-6"] += 1
            elif p <= allsky.MAX_P_CHANCE_TIGHT and rms <= allsky.MAX_RMS_TIGHT_DEG:
                tiers["tier 2 (p<=1e-4, rms<=0.12)"] += 1
            else:
                tiers["tier 3 (p<=1e-2, rms<=0.10)"] += 1
    lines.append("accepted by: " + ", ".join(f"{k} x{v}" for k, v in tiers.items()))
    wr = [r for r in rows if r.get("ug_err_km") is not None and r["ug_err_km"] > WRONG_KM]
    if wr:
        lines.append("wrong identifications (gate open): " + "; ".join(
            f"{r['frame'][:30]} m {r['ug_matched']} rms {r['ug_rms']} p {r['ug_p']:.2g} -> {r['ug_gate']}" for r in wr))
    rt = [r for r in rows if r.get("ug_err_km") is not None and r["ug_err_km"] <= WRONG_KM and not r["solved"]]
    if rt:
        lines.append("right identifications refused: " + "; ".join(
            f"{r['frame'][:30]} m {r['ug_matched']} rms {r['ug_rms']} p {r['ug_p']:.2g} err {r['ug_err_km']} km -> {r['ug_gate']}" for r in rt))
    # per night: the mean error vector is the mount's ('up') error that night, the scatter is the solver's own
    nights: Dict[str, list] = {}
    for r in rows:
        if r["solved"] and "err_n_km" in r:
            t = np.datetime64(r["utc"][:19]) - np.timedelta64(12, "h")      # a night = noon to noon UTC
            nights.setdefault(str(t)[:10], []).append((r["err_n_km"], r["err_e_km"]))
    sc, means, after = [], [], []
    for k, v in sorted(nights.items()):
        v = np.array(v)
        means.append(np.hypot(*v.mean(axis=0)))
        if len(v) >= 3:
            sc.extend(np.hypot(*(v - v.mean(axis=0)).T))
        if len(v) >= 4:          # the field's way: the tilt of 'up' learned on the first fixes with a reference
            after.extend(np.hypot(*(v[3:] - v[:3].mean(axis=0)).T))
    if sc:
        lines.append(f"per-night mean error (mount/'up' + clock): median {np.median(means):.1f} km, max {np.max(means):.1f} km over "
                     f"{len(means)} nights; scatter about the night's mean (the solver's own noise): median {np.median(sc):.1f} km, "
                     f"p90 {np.percentile(sc, 90):.1f} km, max {np.max(sc):.1f} km")
    if after:
        lines.append(f"'up' tilt learned on each night's first 3 fixes (true position), later fixes of the night: "
                     f"n {len(after)}, median {np.median(after):.1f} km, p90 {np.percentile(after, 90):.1f} km, max {np.max(after):.1f} km")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--camera", required=True, choices=sorted(CAMERAS))
    c.add_argument("--frames", nargs="+", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--per-frame", action="store_true", help="tracking mount: one rotation per frame")
    r = sub.add_parser("run")
    r.add_argument("--camera", required=True, choices=sorted(CAMERAS))
    r.add_argument("--lens", required=True)
    r.add_argument("--frames", nargs="+", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--degrade", default=None, help="gain,read_noise,jpeg_q: a shallower, noisier, compressed copy")
    r.add_argument("--up-per-frame", action="store_true", help="tracking mount: fit each frame's 'up' on the truth")
    s = sub.add_parser("summary")
    s.add_argument("results", nargs="+")
    a = ap.parse_args()
    if a.cmd == "calibrate":
        cal = calibrate(a.frames, CAMERAS[a.camera], per_frame=a.per_frame)
        cal["camera"] = a.camera
        cal["calibration_frames"] = [os.path.basename(f) for f in a.frames]
        json.dump(cal, open(a.out, "w"), indent=1)
        print(json.dumps({k: v for k, v in cal.items() if k != "frames"}, indent=1))
        for fr in cal["frames"]:
            print(fr)
    elif a.cmd == "run":
        frames = sorted(a.frames)
        deg = None
        if a.degrade:
            g, n, q = a.degrade.split(",")
            deg = dict(gain=float(g), read_noise=float(n), jpeg_q=int(q))
        run(frames, CAMERAS[a.camera], json.load(open(a.lens)), a.out, degrade=deg, up_per_frame=a.up_per_frame)
    else:
        print(summary(a.results))


if __name__ == "__main__":
    main()
