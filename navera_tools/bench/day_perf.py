#!/usr/bin/env python3
"""Day vision accuracy benchmark, offline (NAV-PERF-02 regression): data already on disk, no camera.

Two parts, both with the product's day matcher (``matcher:=auto`` = LearnedMatcher, DISK + LightGlue
on the GPU with SIFT as fallback, at the day node's default gates):

``recorded``  REAL Insta360 frames recorded on the screen bench (screen_flight.py --record,
              2026-10-20: rec_clear_v20 / rec_clear_v60 / rec_heavyrain07_v20 / rec_flare07_v60),
              each located around its recorded truth moved 0-150 m in a seeded random direction
              (search 400 m), as bench/eval_recorded.py. The screen showed NAVERA's own map imagery:
              this part checks the real camera chain (lens, straightening, blur, screen moire),
              not the other-date imagery.

``mission``   Campaign 4's screen mission (bench/screen_mission.py: racetrack with turns, height
              +-20 %, simulated IMU heading +-5 deg, 25 m/s, ~520 m equivalent height, GPS then
              lost) with the camera replaced by the view it filmed: the OTHER-DATE terrain imagery
              (Esri Wayback, 2-3 years older than the map) cut heading-up at the frame's height
              (1500 x 420 m at 520 m, 111 deg), slightly blurred, noised and JPEG-compressed.
              Same NAVERA chain as screen_mission's worker: the matcher, VisionNavigator between
              frames (search window, gates, height retries, map bias, "no position") and
              FrameOdometry. Terrains: city, olives, hills, farms, coast (campaign 4's areas).
              Frames every --dt seconds of simulated time (independent of the processing speed).

    python3 navera_tools/bench/day_perf.py recorded [--n 30]
    python3 navera_tools/bench/day_perf.py mission [--terrains city,coast] [--gps-s 20 --lost-s 60]

Data: NAVERA_BENCH_DIR (default ~/.navera_sim/bench_2026-10-06: area*/ map_*/ terrain_*/ wb2022/
areas.json), NAVERA_SCREEN_REC_DIR (default ~/navera-field/day_image_2026-10-20/before).
"""
import argparse
import json
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

BENCH_DIR = os.environ.get("NAVERA_BENCH_DIR", os.path.expanduser("~/.navera_sim/bench_2026-10-06"))
REC_DIR = os.environ.get("NAVERA_SCREEN_REC_DIR",
                         os.path.expanduser("~/navera-field/day_image_2026-10-20/before"))
RECORDINGS = ("rec_clear_v20", "rec_clear_v60", "rec_heavyrain07_v20", "rec_flare07_v60")
TERRAINS = ("city", "olives", "hills", "farms", "coast")
WRONG_M = 50.0
HFOV = 111.0                       # the bench camera's straightened view (screen_mission default)
FRAME = (960, 270)                 # half the bench crop (1920 x 540): the matcher works below that
H0 = 520.0                         # campaign 4's equivalent height at k = 1


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


def pct(e, p):
    """The p-quantile of a sorted list (nearest rank, as the bench summaries)."""
    return e[min(len(e) - 1, int(p * len(e)))] if e else None


def make_matcher(images_dir: str, zoom: int = 17, models_from=None):
    """The day node's matcher for ``matcher:=auto`` with its default gates (min_inliers 8, scale_tol 0.15,
    pose_tilt_guard 4 deg); learned features cached next to the map (as screen_mission.py).
    models_from: a LearnedMatcher whose networks are reused (one copy on the GPU)."""
    from day_pkg.learned_matcher import LearnedMatcher
    cache = os.path.join(os.path.dirname(os.path.abspath(images_dir.rstrip("/"))), "learned_features")
    return LearnedMatcher(images_dir, zoom=zoom, cache_dir=cache, min_inliers=8, scale_tol=0.15,
                          pose_tilt_guard_deg=4.0, models_from=models_from)


def release(m) -> None:
    import torch
    del m
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ---------------------------------------------------------------- recorded real-camera frames
def recorded_paths():
    return [os.path.join(REC_DIR, r) for r in RECORDINGS]


def run_recorded(n_per_run: int = 30, seed: int = 7, matcher=None, verbose: bool = False) -> dict:
    """Every recording: n frames evenly spread (truth certain to 10 m), prior = truth moved 0-150 m."""
    area = os.path.join(BENCH_DIR, "area")
    M = matcher or make_matcher(area)
    out = {}
    try:
        for d in recorded_paths():
            meta = [json.loads(line) for line in open(os.path.join(d, "frames.jsonl"))]
            meta = [m for m in meta if m.get("mpp") and m.get("truth") and (m.get("truth_unc_m") or 0) <= 10.0]
            if n_per_run and len(meta) > n_per_run:
                meta = [meta[int(i)] for i in np.linspace(0, len(meta) - 1, n_per_run)]
            rng = np.random.default_rng(seed)
            rows = []
            for m in meta:
                img = cv2.imread(os.path.join(d, m["file"]))
                r_off, b_off = rng.uniform(0, 150.0), rng.uniform(0, 2 * math.pi)
                if img is None:
                    continue
                truth = tuple(m["truth"])
                prior = (truth[0] + r_off * math.cos(b_off) / 111320.0,
                         truth[1] + r_off * math.sin(b_off) / (111320.0 * math.cos(math.radians(truth[0]))))
                t0 = time.time()
                r = M.locate(img, prior, 400.0, m["mpp"], scale_tol=0.15, heading_deg=m.get("rot_deg") or 0.0,
                             heading_tol_deg=15.0)
                ok = bool(r.get("accepted"))
                rows.append(dict(file=m["file"], accepted=ok, ms=(time.time() - t0) * 1000,
                                 err=metres((r["predicted_lat"], r["predicted_lon"]), truth) if ok else None,
                                 features=r.get("features")))
                if verbose:
                    print(f"  {os.path.basename(d)} {m['file']} {rows[-1]['err']}", flush=True)
            out[os.path.basename(d).replace("rec_", "")] = summary_fixes(rows)
    finally:
        if matcher is None:
            release(M)
    return out


def summary_fixes(rows) -> dict:
    acc = [r for r in rows if r["accepted"]]
    e = sorted(r["err"] for r in acc)
    return dict(frames=len(rows), accepted=len(acc), median=pct(e, 0.5), p90=pct(e, 0.9), p95=pct(e, 0.95),
                max=e[-1] if e else None, wrong=sum(x > WRONG_M for x in e),
                ms=float(np.median([r["ms"] for r in rows])) if rows else None, errs=e)


# ---------------------------------------------------------------- the screen mission, offline
def terrain_setup(name: str):
    """(terrain z18 dir, NAVERA map z17 images dir, lat, lon) of campaign 4/5's areas."""
    if name == "city":
        return os.path.join(BENCH_DIR, "wb2022"), os.path.join(BENCH_DIR, "area_k", "images"), 35.869, 10.535
    c = json.load(open(os.path.join(BENCH_DIR, "areas.json")))[name]
    return (os.path.join(BENCH_DIR, f"terrain_{name}"), os.path.join(BENCH_DIR, f"map_{name}", "images"),
            c["lat"], c["lon"])


class Terrain:
    """The z18 other-date mosaic shown on the bench screen, and the camera's view of it."""

    def __init__(self, tdir: str, lat: float, lon: float, zoom: int = 18):
        from day_pkg.local_matcher import map_m_per_px
        self.z, self.mpp = zoom, map_m_per_px(lat, zoom)
        n = 2 ** zoom
        r_ = math.radians(lat)
        self.cx = (lon + 180) / 360 * n * 256
        self.cy = (1 - math.log(math.tan(r_) + 1 / math.cos(r_)) / math.pi) / 2 * n * 256
        names = [f for f in os.listdir(tdir) if f.startswith(f"tile_{zoom}_")]
        xs = [int(f.split("_")[2]) for f in names]
        ys = [int(f.split("_")[3].split(".")[0]) for f in names]
        self.x0, self.y0 = min(xs), min(ys)
        self.mosaic = np.zeros(((max(ys) - self.y0 + 1) * 256, (max(xs) - self.x0 + 1) * 256, 3), np.uint8)
        for f, x, y in zip(names, xs, ys):
            t = cv2.imread(os.path.join(tdir, f))
            if t is not None:
                self.mosaic[(y - self.y0) * 256:(y - self.y0 + 1) * 256,
                            (x - self.x0) * 256:(x - self.x0 + 1) * 256] = cv2.resize(t, (256, 256))

    def latlon(self, p):
        from day_pkg.local_matcher import tile_px_to_latlon
        return tile_px_to_latlon(self.cx + p[0] / self.mpp, self.cy - p[1] / self.mpp, self.z)

    def view(self, p, hdg: float, height_m: float, rng) -> np.ndarray:
        """The straightened camera frame centred on p (east, north m), heading up, at height_m."""
        w, h = FRAME
        s = 2.0 * height_m * math.tan(math.radians(HFOV / 2)) / w / self.mpp     # mosaic px per frame px
        gx, gy = self.cx + p[0] / self.mpp - self.x0 * 256, self.cy - p[1] / self.mpp - self.y0 * 256
        th = math.radians(hdg)
        c, sn = math.cos(th), math.sin(th)
        A = np.array([[c * s, -sn * s, 0.0], [sn * s, c * s, 0.0]])
        A[:, 2] = [gx, gy] - A[:, :2] @ [w / 2, h / 2]
        img = cv2.warpAffine(self.mosaic, A, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_AREA)
        # what the camera adds filming the screen, mildly: optics blur, sensor noise, JPEG
        img = cv2.GaussianBlur(img, (0, 0), 0.8)
        img = np.clip(img.astype(np.float32) + rng.normal(0, 3.0, img.shape), 0, 255).astype(np.uint8)
        return cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1], cv2.IMREAD_COLOR)


def racetrack(t: float, speed=25.0, leg=900.0, radius=250.0, track_deg=30.0, swing=0.2, period=150.0):
    """screen_mission.py's route: (east, north) m from the centre, heading deg, height factor k."""
    L, R = leg, radius
    perim = 2 * L + 2 * math.pi * R
    B = math.radians(track_deg)
    U, V = np.array([math.sin(B), math.cos(B)]), np.array([math.cos(B), -math.sin(B)])
    s = (speed * t) % perim
    if s < L:
        p, h = -L / 2 * U + s * U - R * V, U
    elif s < L + math.pi * R:
        ang = (s - L) / R
        p, h = L / 2 * U + R * (math.sin(ang) * U - math.cos(ang) * V), math.cos(ang) * U + math.sin(ang) * V
    elif s < 2 * L + math.pi * R:
        p, h = L / 2 * U - (s - L - math.pi * R) * U + R * V, -U
    else:
        ang = (s - 2 * L - math.pi * R) / R
        p, h = -L / 2 * U + R * (-math.sin(ang) * U + math.cos(ang) * V), -math.cos(ang) * U - math.sin(ang) * V
    k = 1.0 / (1.0 + swing * math.sin(2 * math.pi * t / period))
    return p, math.degrees(math.atan2(h[0], h[1])) % 360, k


def frame_mpp(height_m, width):
    return 2.0 * height_m * math.tan(math.radians(HFOV / 2)) / width


def run_mission(terrain: str, gps_s: float = 20.0, lost_s: float = 135.0, dt: float = 3.0, seed: int = 1,
                heading_noise: float = 5.0, matcher=None, verbose: bool = False) -> dict:
    """One terrain: GPS for gps_s, then lost for lost_s (135 s = one lap of the racetrack); the chain
    of screen_mission.py's worker."""
    from day_pkg.frame_odometry import FrameOdometry
    from day_pkg.vision_nav import VisionNavigator
    tdir, mdir, lat, lon = terrain_setup(terrain)
    T = Terrain(tdir, lat, lon)
    M = make_matcher(mdir, models_from=matcher) if matcher is not None else make_matcher(mdir)
    rng = np.random.default_rng(seed)
    nav, vo = VisionNavigator(), FrameOdometry()
    rows = []
    try:
        M.warm(lat, lon, 450 + 250 + 1000)
        t = 0.0
        while t < gps_s + lost_s:
            p, hdg, k = racetrack(t)
            h_true = H0 / k
            img = T.view(p, hdg, h_true, rng)
            truth = T.latlon(p)
            gps_on = t < gps_s
            imu = (hdg + rng.normal(0, heading_noise)) % 360
            if gps_on:
                nav.gps(t, *truth, heading_deg=imu)
                nav.set_height(t, h_true * (1 + rng.normal(0, 0.02)), 0.03 * h_true, "gps")
            h, extra, tol = nav.heights_to_try(t)
            centre, R = (truth, 150.0) if gps_on else nav.search(t, imu)
            t1 = time.time()
            used = None
            if centre is None:
                r = {"accepted": False, "reason": "no prior"}
            elif h is None:
                r = M.locate_any_height(img, centre, R, HFOV, min_alt_m=100, max_alt_m=1500, heading_deg=imu)
                used = r.get("height_tried_m")
            else:
                for hh in [h] + extra:
                    r = M.locate(img, centre, R, frame_mpp(hh, img.shape[1]), scale_tol=tol, heading_deg=imu,
                                 heading_tol_deg=20.0)
                    used = hh
                    if r["accepted"]:
                        break
                sc = float(r.get("scale_residual") or 1.0)
                if r.get("accepted") and abs(sc - 1.0) > 0.05:
                    again = M.locate(img, centre, R, frame_mpp(used * sc, img.shape[1]), scale_tol=tol,
                                     heading_deg=imu, heading_tol_deg=20.0)
                    if again.get("accepted") and int(again.get("inliers") or 0) >= int(r.get("inliers") or 0) // 2:
                        r, used = again, used * sc
            ms = (time.time() - t1) * 1000
            vis = (r["predicted_lat"], r["predicted_lon"]) if r.get("accepted") else None
            if vis and gps_on:
                nav.bias_sample(vis, truth, imu)
            ok = nav.update(t, r, used, imu, gps_valid=gps_on, search_m=R)
            if nav.height is not None:
                pred = None
                if nav.vel is not None and vo._prev is not None:
                    pred = (nav.vel[0] * (t - vo._prev[3]), nav.vel[1] * (t - vo._prev[3]))
                d = vo.step(img, imu, frame_mpp(nav.height[0], img.shape[1]), t, pred)
                if d is not None and not gps_on and not ok:
                    nav.odometry(t, *d)
            olat, olon, sig, mode = nav.output(t, imu)
            oe = metres((olat, olon), truth) if olat is not None else None
            rows.append(dict(t=t, gps=gps_on, fix=bool(ok), vision_err=metres(vis, truth) if vis else None,
                             err=oe, sigma=sig, mode=mode, ms=ms))
            if verbose:
                print(f"  {terrain} {t:6.1f}s {'GPS ' if gps_on else 'LOST'} fix {int(ok)} "
                      f"err {'-' if oe is None else round(oe, 1)} sigma {sig} {ms:.0f} ms", flush=True)
            t += dt
    finally:
        if matcher is None:
            release(M)
        else:                   # its prefetch thread keeps it alive: drop the map features it holds
            M._grid.clear()
            M._tiles.clear()
    return summary_mission(rows)


def run_missions(terrains=TERRAINS, gps_s: float = 20.0, lost_s: float = 135.0, dt: float = 3.0, seed: int = 1,
                 verbose: bool = False) -> dict:
    """{terrain: summary}; the networks are loaded once, each terrain's map gets its own matcher."""
    first = make_matcher(terrain_setup(terrains[0])[1])
    try:
        return {t: run_mission(t, gps_s, lost_s, dt, seed, matcher=first, verbose=verbose) for t in terrains}
    finally:
        release(first)


def summary_mission(rows) -> dict:
    lost = [r for r in rows if not r["gps"]]
    e = sorted(r["err"] for r in lost if r["err"] is not None)
    fixes = [r for r in lost if r["fix"] and r["vision_err"] is not None]
    honest = [r for r in lost if r["err"] is not None and r["sigma"] and r["err"] <= 3 * r["sigma"]]
    return dict(frames=len(lost), available=len(e) / len(lost) if lost else 0.0, fixes=len(fixes),
                median=pct(e, 0.5), p90=pct(e, 0.9), p95=pct(e, 0.95), max=e[-1] if e else None,
                wrong_fixes=sum(r["vision_err"] > WRONG_M for r in fixes),
                within_3sigma=len(honest) / len(e) if e else None,
                ms=float(np.median([r["ms"] for r in rows])) if rows else None, errs=e)


def _fmt(s):
    return " ".join(f"{k} {round(v, 2) if isinstance(v, float) else v}" for k, v in s.items() if k != "errs")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part", choices=["recorded", "mission"])
    ap.add_argument("--n", type=int, default=30, help="recorded: frames per recording")
    ap.add_argument("--terrains", default=",".join(TERRAINS))
    ap.add_argument("--gps-s", type=float, default=20.0)
    ap.add_argument("--lost-s", type=float, default=135.0)
    ap.add_argument("--dt", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.part == "recorded":
        for k, s in run_recorded(a.n, verbose=a.verbose).items():
            print(f"{k:18s} {_fmt(s)}", flush=True)
    else:
        for t, s in run_missions(a.terrains.split(","), a.gps_s, a.lost_s, a.dt, a.seed, a.verbose).items():
            print(f"{t:8s} {_fmt(s)}", flush=True)
    print(f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
