#!/usr/bin/env python3
"""Re-read a 360 field test: errors against the phone's GPS, and the camera's mounting angle measured
from the first frames, checked on the frames after them.

    python3 -m navera_tools.field.reprocess360 <test folder> [--fit N] [--resolve] [--f-scale F]

The accelerometer and the lenses are fixed inside the camera, but the angle between the sensor's
axes and the lenses' (assumed exactly aligned) is not measured: a few tenths of a degree there
is tens of kilometres. Each solved frame holds the camera's orientation among the stars
(R_icrs_imu) and 'up' from gravity; with the phone's position as truth, the small rotation Q that
makes R (Q up) hit the true zenith is fitted on the first N frames and then applied to every
later frame, so the corrected error is measured on frames the fit did not see.

--resolve runs the all-sky solver again on the saved images (e.g. after a better lens model);
--f-scale fixes the focal length instead of searching it.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    sys.path.insert(0, p)

from navera_tools.field.store import read_jsonl  # noqa: E402


def haversine_km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(min(1.0, h)))


def truth_at(phone, t, max_gap_s=3.0):
    """The phone's position at Jetson time t (linear between the two nearest fixes), or None."""
    pts = [(p["t"], p["lat"], p["lon"]) for p in phone if p.get("lat") is not None and p.get("lon") is not None]
    if not pts:
        return None
    ts = np.array([p[0] for p in pts])
    i = int(np.searchsorted(ts, t))
    if 0 < i < len(pts) and ts[i] - ts[i - 1] <= 2 * max_gap_s:
        a, b = pts[i - 1], pts[i]
        w = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return a[1] + w * (b[1] - a[1]), a[2] + w * (b[2] - a[2])
    j = min(max(i, 0), len(pts) - 1) if i < len(pts) else len(pts) - 1
    j = j if abs(ts[j] - t) <= abs(ts[max(i - 1, 0)] - t) else max(i - 1, 0)
    return (pts[j][1], pts[j][2]) if abs(ts[j] - t) <= max_gap_s else None


def zenith_icrs(lat, lon, utc):
    """Unit vector (ICRS, J2000) of the point overhead at (lat, lon) and utc."""
    import astropy.units as u
    from astropy.coordinates import TETE, SkyCoord
    from astropy.time import Time
    from cn_pkg.nodes.celestial_math import gast_deg
    t = Time(utc, scale="utc")
    c = SkyCoord(ra=((gast_deg(utc) + lon) % 360.0) * u.deg, dec=lat * u.deg, frame=TETE(obstime=t)).icrs
    ra, dec = math.radians(c.ra.deg), math.radians(c.dec.deg)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


def position(z_icrs, utc):
    from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg
    z = z_icrs / np.linalg.norm(z_icrs)
    ra, dec = math.degrees(math.atan2(z[1], z[0])) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, z[2]))))
    ra_a, dec_a = apparent_radec(ra, dec, utc)
    return dec_a, (ra_a - gast_deg(utc) + 540.0) % 360.0 - 180.0


def rotvec(w):
    t = float(np.linalg.norm(w))
    if t < 1e-15:
        return np.eye(3)
    a = w / t
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def fit_mount(samples):
    """Rotation vector (rad) Q with R (Q up) closest to the true zenith over the samples [(R, up, z_true)].
    A turn about 'up' itself does not move 'up' and cannot be measured: Q is fitted as a tilt only (rotation
    axis perpendicular to the mean 'up'), so its angle is the mounting tilt (before, the free turn about 'up'
    came out as tens of degrees: a 1 deg simulated mount was reported as 56 deg)."""
    from scipy.optimize import least_squares
    u = np.mean([up / np.linalg.norm(up) for _, up, _ in samples], axis=0)
    u /= np.linalg.norm(u)
    e1 = np.cross(u, [1.0, 0, 0] if abs(u[0]) < 0.9 else [0, 1.0, 0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u, e1)

    def res(p):
        Q = rotvec(p[0] * e1 + p[1] * e2)
        return np.concatenate([np.asarray(R) @ (Q @ up) - z for R, up, z in samples])
    p = least_squares(res, np.zeros(2)).x
    return p[0] * e1 + p[1] * e2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--fit", type=int, default=5, help="frames used to measure the mounting angle (the first N with truth)")
    ap.add_argument("--resolve", action="store_true", help="solve the saved images again")
    ap.add_argument("--f-scale", type=float, default=None)
    a = ap.parse_args()
    frames = read_jsonl(os.path.join(a.folder, "frames.jsonl"))
    phone = read_jsonl(os.path.join(a.folder, "phone.jsonl"))
    cat = None
    rows = []
    for fr in frames:
        if fr.get("mode") != "360" or fr.get("up_imu") is None or fr.get("utc_used") is None:
            continue
        up = np.array(fr["up_imu"], float)
        R = fr.get("R_icrs_imu")
        if a.resolve and fr.get("image"):
            import cv2
            from navera_tools.field import allsky, server
            cat = cat or allsky.Catalogue(limit_mag=4.0)
            img = cv2.imread(os.path.join(a.folder, fr["image"]), cv2.IMREAD_GRAYSCALE)
            fs = (a.f_scale,) if a.f_scale else server.F_SCALE_SEARCH
            r = allsky.locate(img, up, fr["utc_used"], cat, f_scales=fs) if img is not None else {}
            R = r.get("R_icrs_imu") if r.get("solved") else None
            if r.get("solved") and not a.f_scale:
                a.f_scale = r["f_scale"]                       # found once, kept for the rest
        if R is None:
            continue
        tru = truth_at(phone, fr.get("t_exp") or fr["t"])
        if tru is None:
            continue
        rows.append({"idx": fr.get("idx"), "R": np.array(R), "up": up, "utc": fr["utc_used"], "truth": tru,
                     "z_true": zenith_icrs(tru[0], tru[1], fr["utc_used"]),
                     # 'up' of a frame taken while moving holds the vehicle's acceleration: never fit the mount on it
                     "trusted": bool(fr.get("stopped", True)) and not fr.get("stopped_but_phone_moving")})
    if not rows:
        print("no solved 360 frame with a phone position")
        return 1
    for r in rows:
        lat, lon = position(r["R"] @ r["up"], r["utc"])
        r["err_raw"] = haversine_km(lat, lon, *r["truth"])
    moving = [r for r in rows if not r["trusted"]]
    rows = [r for r in rows if r["trusted"]]
    n = len(rows)
    out = {"frames_scored": n, "err_raw_km": summary([r["err_raw"] for r in rows]),
           "moving_frames_not_used": len(moving), "moving_err_raw_km": summary([r["err_raw"] for r in moving])}
    if n > a.fit:
        w = fit_mount([(r["R"], r["up"], r["z_true"]) for r in rows[:a.fit]])
        Q = rotvec(w)
        for r in rows[a.fit:]:
            lat, lon = position(r["R"] @ (Q @ r["up"]), r["utc"])
            r["err_cal"] = haversine_km(lat, lon, *r["truth"])
        out.update(mount_angle_deg=round(math.degrees(float(np.linalg.norm(w))), 3),
                   mount_rotvec_deg=[round(math.degrees(float(v)), 3) for v in w], fitted_on=a.fit,
                   err_raw_after_fit_frames_km=summary([r["err_raw"] for r in rows[a.fit:]]),
                   err_calibrated_km=summary([r["err_cal"] for r in rows[a.fit:]]))
    else:
        out["note"] = f"need more than {a.fit} scored frames to measure the mounting angle"
    if a.f_scale:
        out["f_scale"] = a.f_scale
    print(json.dumps(out, indent=1))
    with open(os.path.join(a.folder, "reprocess360.json"), "w") as f:
        json.dump({**out, "frames": [{k: v for k, v in r.items() if k in ("idx", "err_raw", "err_cal", "truth")} for r in rows]},
                  f, indent=1)
    return 0


def summary(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    return {"n": len(v), "median": round(v[len(v) // 2], 1), "p90": round(v[min(len(v) - 1, int(0.9 * len(v)))], 1),
            "max": round(v[-1], 1)}


if __name__ == "__main__":
    sys.exit(main())
