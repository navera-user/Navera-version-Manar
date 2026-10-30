#!/usr/bin/env python3
"""Does sky cleaning (cn_pkg.skyclean) help the 360 solver on real night frames, and does it ever make a wrong fix?

    python3 -m navera_tools.field.cleanbench <session> --at LAT,LON --truth-km KM [--frames N] [--amps 0,1,1.5]
        [--pipelines base,mask,clean,clean+mask] [--junk-mask PNG] [--control] [--prior-km KM] [--out FILE]

For N test frames spread over the session, each with the ring of saved frames before it (one per
skyclean.RING_GAP_S over ~RING_MAX_FRAMES x gap), the catalogue (mag <= INJECT_MAG) is injected into the test
frame AND every ring frame at its own time (the sky turns between them as a real sky would; heading INJECT_HEADING
about the true zenith, 'up' from the test frame's IMU), Gaussian sigma 1 px, peak amp x 10^(-0.4 (mag - 3)),
then rounded to 8 bit like a saved frame. --control injects the same number of points with the same amplitudes at
random directions of the sky (they turn with the sky too, so time cannot remove them): any fix is then wrong by
construction. amp 0 = the real night, nothing injected.

Each pipeline's frame is solved with allsky.locate lost-in-space and with a position prior (--prior-km + 0.5 deg
for 'up'); a fix further than --truth-km from --at is WRONG. Prints per-case lines and a summary table.
Memory: the ring (12 x 7.4 MB) + a few float frames, ~0.5 GB. Run with nice next to a live test.
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

INJECT_MAG = 4.5
INJECT_HEADING = 100.0


def utc_of(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def inject(gray, lenses, up, z, psi_deg: float, vec, amps, sigma_px: float = 1.0):
    """uint8 copy of gray with a Gaussian spot of peak amps[i] at each direction vec[i] (ICRS) for a camera whose
    'up' is up and heading psi_deg about the zenith z; rounded and clipped to 8 bit like a saved frame."""
    import numpy as np
    from cn_pkg.allsky import _align
    from cn_pkg.allsky_mount import rotvec
    out = gray.astype(np.float32)
    R = rotvec(z * math.radians(psi_deg)) @ _align(up, z)
    r = int(math.ceil(4 * sigma_px))
    gy, gx = np.mgrid[-r:r + 1, -r:r + 1]
    h, w = out.shape
    for lens in lenses:
        v_lens = (vec @ R) @ lens.R_lens_imu.T
        x, y, _ = lens.project(v_lens)
        for xx, yy, vz, a in zip(x, y, v_lens[:, 2], amps):
            if vz <= -0.2 or math.hypot(xx - lens.cx, yy - lens.cy) >= lens.radius - 10:
                continue
            xi, yi = int(round(xx)), int(round(yy))
            if r <= xi < w - r and r <= yi < h - r:
                out[yi - r:yi + r + 1, xi - r:xi + r + 1] += a * np.exp(-((gx + xi - xx) ** 2 + (gy + yi - yy) ** 2)
                                                                        / (2 * sigma_px ** 2))
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def sky_points(cat, control: bool, seed: int):
    """(vec, mag) to inject: the catalogue to INJECT_MAG, or (control) as many random directions, same mags."""
    import numpy as np
    sel = cat.mag <= INJECT_MAG
    vec, mag = cat.vec[sel], cat.mag[sel]
    if control:
        rng = np.random.default_rng(seed)
        v = rng.normal(size=vec.shape)
        vec = v / np.linalg.norm(v, axis=1, keepdims=True)
    return vec, mag


def pick(rows, n: int, gap_s: float, nring: int, full_ring: bool = True):
    """n test rows spread over the session, each with its ring: one earlier row per gap_s (>= 60 s before it), up to
    nring of them. full_ring: only rows with a full ring span behind them (else every row; a short session then
    tests the cleaner not ready, i.e. the frame unchanged)."""
    import numpy as np
    t = np.array([r["t"] for r in rows])
    span = gap_s * nring
    cand = [i for i in range(len(rows)) if not full_ring or t[i] - t[0] >= span + 60]
    out = []
    for i in np.unique(np.linspace(0, len(cand) - 1, n).astype(int)) if cand else []:
        k = cand[i]
        ring, last = [], None
        for j in range(k - 1, -1, -1):
            if t[k] - t[j] < 60:
                continue
            if last is None or last - t[j] >= gap_s:
                ring.append(j)
                last = t[j]
            if len(ring) == nring:
                break
        out.append((k, ring[::-1]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--at", required=True, help="LAT,LON of the camera")
    ap.add_argument("--truth-km", type=float, default=50.0)
    ap.add_argument("--prior-km", type=float, default=10.0)
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--amps", default="0")
    ap.add_argument("--pipelines", default="base,mask,clean,clean+mask")
    ap.add_argument("--junk-mask")
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--modes", default="lost-in-space,prior")
    ap.add_argument("--out")
    ap.add_argument("--starseg", help="weights of the star-segmentation network: pipelines unet, unet-filter")
    ap.add_argument("--prob-min", type=float, default=0.5)
    ap.add_argument("--positions", help="CSV: every fix appended (tool,session,frame,utc,lat,lon,sigma_km,...)")
    ap.add_argument("--any-ring", action="store_true", help="also test frames without a full ring behind them")
    a = ap.parse_args(argv)
    import cv2
    import numpy as np
    from cn_pkg import allsky, sky360, skyclean
    from cn_pkg.allsky_mount import zenith_icrs
    from navera_tools.field.reprocess360 import haversine_km
    lat, lon = (float(v) for v in a.at.split(","))
    cat = allsky.Catalogue(limit_mag=4.0)
    icat = allsky.Catalogue(limit_mag=INJECT_MAG, path=allsky.BUNDLED_CATALOGUE)
    lenses = sky360.default_lenses()
    junk = cv2.imread(a.junk_mask, cv2.IMREAD_GRAYSCALE) if a.junk_mask else None
    amps = [float(v) for v in a.amps.split(",")]
    pipes = a.pipelines.split(",")
    modes = a.modes.split(",")
    prior = (lat, lon, a.prior_km / allsky.KM_PER_DEG + 0.5)
    finders = {}
    if a.starseg:
        from cn_pkg import starseg
        net = starseg.StarSeg(a.starseg)
        finders = {"unet": starseg.finder(net, "detect", a.prob_min),
                   "unet-filter": starseg.finder(net, "filter", a.prob_min)}
    with open(os.path.join(a.session, "frames.jsonl")) as fh:
        rows = [json.loads(line) for line in fh]
    rows = [r for r in rows if r.get("image") and r.get("up_imu")]
    tests = pick(rows, a.frames, skyclean.RING_GAP_S, skyclean.RING_MAX_FRAMES, not a.any_ring)
    out = open(a.out, "a") if a.out else None
    tally = {}

    def load(r):
        return cv2.imread(os.path.join(a.session, r["image"]), cv2.IMREAD_GRAYSCALE)

    for k, ring in tests:
        r = rows[k]
        up = np.asarray(r["up_imu"], float)
        up /= np.linalg.norm(up)
        t = r.get("t_exp") or r["t"]
        raw = load(r)
        raw_ring = [(rows[j].get("t_exp") or rows[j]["t"], load(rows[j])) for j in ring]
        for amp in amps:
            vec, mag = sky_points(icat, a.control, seed=k)
            pa = amp * 10 ** (-0.4 * (mag - 3.0))

            def put(img, tt):
                if amp <= 0:
                    return img
                return inject(img, lenses, up, zenith_icrs(lat, lon, utc_of(tt)), INJECT_HEADING, vec, pa)
            cur = put(raw, t)
            cl = skyclean.SkyCleaner()
            for tt, f in raw_ring:
                cl.add(put(f, tt), tt)
            t0 = time.time()
            cleaned, info = cl.clean(cur, t)
            t_clean = time.time() - t0
            gate = skyclean.sky_usable(cur, lenses, up, cloud_map=cl.cloud_map)
            gate_why = skyclean.gate_reason(gate)
            for p in pipes:
                img = cleaned if p.startswith("clean") else cur.astype(np.float32)
                if "mask" in p:
                    if junk is None:
                        continue
                    img = img.copy()
                    bg = cv2.medianBlur(np.clip(img, 0, 255).astype(np.uint8), 31).astype(np.float32)
                    img[junk > 0] = bg[junk > 0]
                if p.startswith("unet") and p not in finders:
                    continue
                find = finders.get(p, allsky.detect_spots)
                n_spots = sum(len(find(img, L, up_imu=up, min_alt=allsky.LOCATE_MIN_ALT)) for L in lenses)
                for m in modes:
                    res = allsky.locate(img, up, r.get("utc_used") or utc_of(t), cat,
                                        prior=prior if m == "prior" else None, spot_finder=finders.get(p))
                    wrong = False
                    err = None
                    if res.get("solved"):
                        err = haversine_km(res["lat"], res["lon"], lat, lon)
                        wrong = a.control or err > a.truth_km
                    if res.get("solved") and a.positions:
                        from navera_tools.bench.realsky_pipelines import append_positions
                        what = ("control" if a.control else "inject") + f" {amp:g}DN" if amp > 0 else "real night"
                        append_positions(a.positions, [{
                            "tool": f"cleanbench {p}/{m} ({what})", "session": os.path.basename(a.session.rstrip("/")),
                            "frame": r.get("image"), "utc": r.get("utc_used") or utc_of(t),
                            "lat": round(res["lat"], 5), "lon": round(res["lon"], 5),
                            "sigma_km": round(res.get("sigma_fit_deg", 0.0) * allsky.KM_PER_DEG, 2),
                            "truth_lat": lat, "truth_lon": lon, "err_km": round(err, 2)}])
                    key = (amp, p, m)
                    tl = tally.setdefault(key, [0, 0, 0, 0])
                    tl[0] += 1
                    tl[1] += bool(res.get("solved")) and not wrong
                    tl[2] += wrong
                    tl[3] += n_spots
                    line = {"session": os.path.basename(os.path.normpath(a.session)), "idx": r.get("idx"),
                            "amp": amp, "control": a.control, "pipe": p, "mode": m,
                            "spots": n_spots, "solved": bool(res.get("solved")), "wrong": wrong,
                            "err_km": None if err is None else round(err, 1), "matched": res.get("matched"),
                            "p": res.get("p_chance"), "rms": res.get("rms_deg"), "why": res.get("why"),
                            "clean_s": round(t_clean, 2), "cloud_frac": info.get("cloud_frac"),
                            "static": info.get("static"), "usable": gate.get("usable_frac"),
                            "gated": bool(gate_why)}
                    print(json.dumps(line), flush=True)
                    if out:
                        out.write(json.dumps(line) + "\n")
                        out.flush()
    print(f"\n{'control ' if a.control else ''}amp  pipeline     mode           frames fixes WRONG spots/frame")
    for (amp, p, m), (n, fx, wr, sp) in sorted(tally.items()):
        print(f"{amp:5.2f}  {p:12s} {m:14s} {n:6d} {fx:5d} {wr:5d} {sp / max(n, 1):8.1f}")
    if out:
        out.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
