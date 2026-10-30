#!/usr/bin/env python3
"""Star recall vs amplitude and junk spots per frame: thresholding (allsky.detect_spots) against the star
segmentation network (cn_pkg.starseg), on a held-out session's real frames.

    python3 -m navera_tools.field.starseg_eval <session> --weights W.pth [--frames N] [--per-amp K] [--out FILE]

Each test frame is used twice: as recorded (it holds no starlight: every spot above MIN_ALT is junk -> junk
spots/frame) and with K synthetic stars per amplitude (AMPS, peak DN) at random places above MIN_ALT in both lens
circles, >= 20 px apart, Gaussian or Moffat PSF sigma 0.7-1.3 px, rounded to 8 bit (recall: a spot within
MATCH_PX of the star). Detectors: threshold k = 6 (production), 5, 4; network peaks at prob 0.5 / 0.7 / 0.9;
network as a filter on the production detector's (k = 6) and k = 4 spots. Reports runtime of each on this machine.
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

AMPS = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
MIN_ALT = 12.0
MATCH_PX = 2.0


def place_stars(rng, lenses, up, shape, n):
    """n (x, y) above MIN_ALT inside the lens circles, >= 20 px apart."""
    import numpy as np
    from cn_pkg.allsky import unproject
    pts = []
    while len(pts) < n:
        L = lenses[rng.integers(len(lenses))]
        a, r = rng.uniform(0, 2 * math.pi), (L.radius - 20) * math.sqrt(rng.uniform(0, 1))
        x, y = L.cx + r * math.cos(a), L.cy + r * math.sin(a)
        if not (8 <= x < shape[1] - 8 and 8 <= y < shape[0] - 8):
            continue
        alt = math.degrees(math.asin(float(np.clip(unproject(L, np.array([x]), np.array([y]))[0] @ up, -1, 1))))
        if alt < MIN_ALT + 1:
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < 400 for px, py, _ in pts):
            continue
        pts.append((x, y, L.name))
    return pts


def add_stars(gray, stars, rng):
    """uint8 gray + PSF stars [(x, y, amp)], rounded."""
    import numpy as np
    out = gray.astype(np.float32)
    gy, gx = np.mgrid[-6:7, -6:7]
    for x, y, amp in stars:
        xi, yi = int(round(x)), int(round(y))
        s = rng.uniform(0.7, 1.3)
        r2 = (gx + xi - x) ** 2 + (gy + yi - y) ** 2
        if rng.uniform() < 0.5:
            psf = np.exp(-r2 / (2 * s * s))
        else:
            beta = rng.uniform(2.5, 4.0)
            psf = (1 + r2 / (s * s * 2 * math.log(2) / (2 ** (1 / beta) - 1))) ** (-beta)
        out[yi - 6:yi + 7, xi - 6:xi + 7] += amp * psf
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--weights", required=True)
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--per-amp", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    import cv2
    import numpy as np
    from cn_pkg import allsky, sky360, starseg
    rng = np.random.default_rng(a.seed)
    lenses = sky360.default_lenses()
    net = starseg.StarSeg(a.weights)
    with open(os.path.join(a.session, "frames.jsonl")) as fh:
        rows = [json.loads(line) for line in fh]
    rows = [r for r in rows if r.get("image") and r.get("up_imu")]
    rows = [rows[i] for i in np.linspace(0, len(rows) - 1, a.frames).astype(int)]

    dets = {f"thr k={k:g}": ("thr", k, None) for k in (6.0, 5.0, 4.0)}
    dets.update({f"net p>{p:g}": ("net", None, p) for p in (0.5, 0.7, 0.9)})
    dets.update({f"thr k=6 + net filter p>{p:g}": ("filter", 6.0, p) for p in (0.5, 0.9)})
    dets.update({f"thr k=4 + net filter p>{p:g}": ("filter", 4.0, p) for p in (0.5, 0.9)})
    junk = {d: 0 for d in dets}
    found = {d: {amp: 0 for amp in AMPS} for d in dets}
    total = {amp: 0 for amp in AMPS}
    secs = {"thr": 0.0, "net": 0.0}
    n_frames = 0

    def run(img, up):
        """{detector: [(x, y)]} above MIN_ALT, both lenses."""
        out = {d: [] for d in dets}
        for L in lenses:
            t0 = time.time()
            thr = {k: allsky.detect_spots(img, L, k_sigma=k, max_spots=10000, up_imu=up, min_alt=MIN_ALT)
                   for k in (6.0, 5.0, 4.0)}
            secs["thr"] += (time.time() - t0) / 3
            t0 = time.time()
            p = net.prob(img, starseg.lens_box(L, img.shape))
            pk = {pm: net.spots(img, L, up_imu=up, min_alt=MIN_ALT, max_spots=10000, prob_min=pm, prob=p)
                  for pm in (0.5, 0.7, 0.9)}
            secs["net"] += time.time() - t0
            H, W = p.shape
            pmax = cv2.dilate(p, np.ones((5, 5), np.uint8))
            for d, (kind, k, pm) in dets.items():
                if kind == "thr":
                    sp = thr[k]
                elif kind == "net":
                    sp = pk[pm]
                else:
                    sp = [s for s in thr[k] if pmax[min(H - 1, int(round(s[1]))), min(W - 1, int(round(s[0])))] >= pm]
                out[d] += [(s[0], s[1]) for s in sp]
        return out

    for r in rows:
        g = cv2.imread(os.path.join(a.session, r["image"]), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        up = np.asarray(r["up_imu"], float)
        up /= np.linalg.norm(up)
        base = run(g, up)
        for d in dets:
            junk[d] += len(base[d])
        pts = place_stars(rng, lenses, up, g.shape, a.per_amp * len(AMPS))
        stars = [(x, y, AMPS[i % len(AMPS)]) for i, (x, y, _) in enumerate(pts)]
        inj = run(add_stars(g, stars, rng), up)
        for d in dets:
            xy = np.array(inj[d]).reshape(-1, 2)
            for x, y, amp in stars:
                if len(xy) and np.min((xy[:, 0] - x) ** 2 + (xy[:, 1] - y) ** 2) <= MATCH_PX ** 2:
                    found[d][amp] += 1
        for _, _, amp in stars:
            total[amp] += 1
        n_frames += 1
        print(f"frame {r.get('idx')}: junk " + ", ".join(f"{d} {len(base[d])}" for d in dets), flush=True)
    head = "detector".ljust(30) + "junk/frame " + " ".join(f"{amp:>5g}DN" for amp in AMPS)
    print("\n" + head)
    res = {"frames": n_frames, "stars_per_amp": total, "detectors": {}}
    for d in dets:
        rec = [found[d][amp] / max(total[amp], 1) for amp in AMPS]
        print(d.ljust(30) + f"{junk[d] / max(n_frames, 1):10.1f} " + " ".join(f"{100 * v:6.0f}%" for v in rec))
        res["detectors"][d] = {"junk_per_frame": junk[d] / max(n_frames, 1),
                               "recall": dict(zip(map(str, AMPS), rec))}
    n_calls = 2 * n_frames * len(lenses)
    res["seconds_per_frame"] = {k: 2 * v / max(n_calls, 1) for k, v in secs.items()}
    print(f"runtime per frame (both lenses): threshold {res['seconds_per_frame']['thr']:.2f} s, "
          f"network {res['seconds_per_frame']['net']:.2f} s ({net.device})")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(res, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
