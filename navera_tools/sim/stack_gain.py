#!/usr/bin/env python3
"""How much stop-frame stacking (navera_tools/field/stack.py) gains on the 360 star solve: a synthetic standing-camera
night sky with its sensor noise drawn again in every frame, ENCODED to H.264 like the camera's live stream
(3840x1920, 30 fps, a key frame every 15, ~40 Mbit/s, libx264) and decoded, compared with no compression.
SIMULATION ONLY: the camera's real exposure, noise and encoder are not known for a night sky.

    PYTHONPATH=.:cn_pkg:navera_common:navera_tools/sim python3 -m navera_tools.sim.stack_gain [--frames 120]

Per condition (star brightness A = peak DN of a magnitude-1 star, temporal noise sigma DN): spots above the
horizon, solved, error km, matched stars, for one key frame, the stack of 8 key frames (4 s of a stop), and stacks
of 16 / 30 consecutive frames (every frame decoded).
"""
import argparse
import math
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_tools.field import allsky, sky360  # noqa: E402
from navera_tools.field.reprocess360 import haversine_km  # noqa: E402
from navera_tools.field.stack import stack_frames  # noqa: E402
from navera_tools.field.selftest360 import F_TRUE, LAT, night_longitude  # noqa: E402

W, H, GOP = 3840, 1920, 15


def sky_model(utc, lat, lon, limit_mag, seed=5):
    """(star layer float32 for A=1 (peak DN of a mag-1 star / A), 'up' in the IMU frame): selftest360's geometry."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    from sky_view import _enu, load_bsc5
    rng = np.random.default_rng(seed)
    ra, dec, mag = load_bsc5(os.path.expanduser("~/.navera_sim"))
    keep = mag <= limit_mag
    aa = SkyCoord(ra=ra[keep] * u.deg, dec=dec[keep] * u.deg).transform_to(
        AltAz(obstime=Time(utc), location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg)))
    alt = aa.alt.deg + allsky.refraction_deg(aa.alt.deg)
    v_enu, m = _enu(alt, aa.az.deg), mag[keep]
    heading, tilt = rng.uniform(0, 360), rng.normal(0, 3, 2)

    def rot(axis, deg):
        a = np.asarray(axis, float) / np.linalg.norm(axis)
        t = math.radians(deg)
        K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
        return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K
    upv, hd = np.array([0, 0, 1.0]), np.array([math.sin(math.radians(heading)), math.cos(math.radians(heading)), 0])
    R_world_imu = rot([1, 0, 0], tilt[0]) @ rot([0, 1, 0], tilt[1]) @ np.stack([upv, hd, np.cross(upv, hd)], axis=1)
    v_imu = v_enu @ R_world_imu
    layer = np.zeros((H, W), np.float32)
    ys, xs = np.mgrid[-4:5, -4:5]
    psf = np.exp(-(xs ** 2 + ys ** 2) / (2 * 1.2 ** 2)).astype(np.float32)
    for lens in sky360.default_lenses():
        lens.f *= F_TRUE
        x, y, th = lens.project(v_imu @ lens.R_lens_imu.T)
        ok = (alt > 0.5) & (th < math.radians(100)) & (x > 4) & (x < W - 5) & (y > 4) & (y < H - 5)
        for xi, yi, mi in zip(x[ok], y[ok], m[ok]):
            cx, cy = int(round(xi)), int(round(yi))
            layer[cy - 4:cy + 5, cx - 4:cx + 5] += 10 ** (-0.4 * (mi - 1)) * psf
    return layer, R_world_imu.T @ upv


def frames(layer, A, sigma, bg, n, seed=1):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        f = bg + A * layer + rng.normal(0, sigma, layer.shape).astype(np.float32)
        yield np.clip(np.round(f), 0, 255).astype(np.uint8)


def h264_roundtrip(gen, n, bitrate=40_000_000):
    """Encode grey frames as the camera would (I every GOP, no B-frames), decode: (decoded grey frames, key flags)."""
    import av
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = W, H, "yuv420p"
    enc.bit_rate, enc.gop_size, enc.max_b_frames = bitrate, GOP, 0
    enc.framerate = 30
    enc.options = {"preset": "ultrafast", "tune": "zerolatency", "keyint": str(GOP), "min-keyint": str(GOP)}
    dec = av.CodecContext.create("h264", "r")
    out, keys = [], []
    chroma = np.full((H // 2, W // 2), 128, np.uint8)

    def take(pkts):
        for p in pkts:
            for fr in dec.decode(p):
                y = np.frombuffer(fr.planes[0], np.uint8).reshape(fr.planes[0].height, fr.planes[0].line_size)[:, :W]
                out.append(y.copy())
                keys.append(bool(fr.key_frame))
    for i, g in enumerate(gen):
        vf = av.VideoFrame(W, H, "yuv420p")
        vf.planes[0].update(np.ascontiguousarray(g))
        vf.planes[1].update(chroma)
        vf.planes[2].update(chroma)
        vf.pts = i
        take(enc.encode(vf))
    take(enc.encode(None))
    take([None])                                          # flush the decoder
    return out[:n], keys[:n]


def score(img, up, cat, utc, lon):
    n = 0
    for L in sky360.default_lenses():
        n += len(allsky.detect_spots(img, L, up_imu=up, min_alt=allsky.LOCATE_MIN_ALT))
    r = allsky.locate(img, up, utc, cat, f_scales=(F_TRUE,))
    err = haversine_km(r["lat"], r["lon"], LAT, lon) if r.get("solved") else None
    return {"spots": n, "solved": bool(r.get("solved")), "err_km": None if err is None else round(err, 1),
            "matched": r.get("matched"), "why": None if r.get("solved") else str(r.get("why"))[:50]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--conditions", default="60:3,30:3,15:3,30:5,15:5", help="A:sigma pairs")
    ap.add_argument("--bg", type=float, default=14.0)
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    utc = now.strftime("%Y-%m-%d %H:%M:%S")
    lon = night_longitude(now)
    layer, up = sky_model(utc, LAT, lon, 5.0)
    cat = allsky.Catalogue(limit_mag=4.0)
    print("SIMULATION ONLY  | A (mag-1 peak DN) : noise sigma DN | variant | spots | solved | err km | matched | why")
    for cond in a.conditions.split(","):
        A, sig = (float(v) for v in cond.split(":"))
        t0 = time.time()
        raw = list(frames(layer, A, sig, a.bg, a.frames))
        dec, keys = h264_roundtrip(iter(raw), a.frames)
        key_idx = [i for i, k in enumerate(keys) if k]
        variants = {
            "raw 1 frame": raw[0],
            "raw stack 8": stack_frames(raw[:8]),
            "h264 1 key frame": dec[key_idx[0]],
            "h264 8 key frames": stack_frames([dec[i] for i in key_idx[:8]]),
            "h264 16 frames": stack_frames(dec[key_idx[0]:key_idx[0] + 16]),
            "h264 30 frames": stack_frames(dec[key_idx[0]:key_idx[0] + 30]),
        }
        for name, img in variants.items():
            s = score(img, up, cat, utc, lon)
            print(f"{A:4.0f} : {sig:3.0f} | {name:18s} | {s['spots']:4d} | {s['solved']!s:5s} | {s['err_km']} | "
                  f"{s['matched']} | {s['why'] or ''}", flush=True)
        print(f"   ({len(key_idx)} key frames of {len(dec)} decoded, {time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
