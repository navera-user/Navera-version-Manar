#!/usr/bin/env python3
"""Latency per stage, memory and power of NAVERA's product paths on the Jetson, with representative inputs.

    # day: DISK + LightGlue (SIFT fallback) on the real-camera screen recordings
    python3 navera_tools/bench/perf_profile.py day REC_DIR [REC_DIR ...] [--search-m 400] [--stride 3]
        [--matcher learned|sift] [--json out.json] [--tegra out_tegra.log] [--cache-dir DIR]
    # night: STHN on the night_conditions synthetic frames (NightLocalizer, same chain as the node)
    python3 navera_tools/bench/perf_profile.py night [--n 16] [--only nominal,...] [--json out.json]
    # celestial: the all-sky solver (CPU) on the celestial360_conditions synthetic skies
    python3 navera_tools/bench/perf_profile.py celestial [--seeds 2] [--only nominal] [--json out.json]
    # endurance: the day path replayed at maximum rate for --minutes, tegrastats logged
    python3 navera_tools/bench/perf_profile.py endurance REC_DIR [...] --minutes 30 --tegra out.log

Every GPU run of this tool must hold the shared GPU lock (flock /tmp/claude-1000/navera_gpu.lock ...).

Day: each frame is located around its recorded truth moved by a fixed random offset (up to 150 m,
seed 7, as eval_recorded.py) with the recorded height scale (mpp) and rotation, scale tolerance 15 %,
heading tolerance 15 deg. Stages (GPU synchronised at their boundaries): frame features (north-up
frame, DISK), map gathering (cached chunks read / computed, thinned), LightGlue, pose refinement,
SIFT fallback; "other" = warp / resize / RANSAC. Memory: peak RSS of the process (VmHWM), PyTorch's
peak allocated and reserved GPU memory (on the Jetson both come out of the same 8 GB).

The per-frame results (accepted, position, error) go to --json, so two runs (e.g. NAVERA_TRT=0 / 1)
compare frame for frame with navera_tools/bench/perf_gate.py.
"""
import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "night_pkg"), os.path.join(ROOT, "navera_common"),
          HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from tegra_monitor import TegraMonitor  # noqa: E402

DEFAULT_AREA = os.path.expanduser("~/.navera_sim/bench_2026-10-06/area")


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


def peak_rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) / 1024.0
    return float("nan")


def rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return float("nan")


def reset_peak_rss():
    """Reset VmHWM to the current RSS (allowed on one's own process)."""
    try:
        with open("/proc/self/clear_refs", "w") as f:
            f.write("5")
    except OSError:
        pass


class Stages:
    """Wall time per named stage, GPU synchronised at both ends; nested stages count in their parent too."""

    def __init__(self, torch=None):
        self.t = defaultdict(float)
        self.n = defaultdict(int)
        self.torch = torch

    def _sync(self):
        if self.torch is not None and self.torch.cuda.is_available():
            self.torch.cuda.synchronize()

    def wrap(self, name, fn):
        def w(*a, **k):
            self._sync()
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                self._sync()
                self.t[name] += (time.perf_counter() - t0) * 1000.0
                self.n[name] += 1
        return w

    def take(self):
        out = {k: round(v, 1) for k, v in self.t.items()}
        self.t.clear()
        self.n.clear()
        return out


class _Callable:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *a, **k):
        return self.fn(*a, **k)


def load_frames(dirs, stride=1, limit=0):
    out = []
    for d in dirs:
        meta = [json.loads(line) for line in open(os.path.join(d, "frames.jsonl"))]
        meta = [m for m in meta if m.get("mpp") and m.get("truth")][::max(1, stride)]
        if limit:
            meta = meta[:limit]
        run = os.path.basename(d.rstrip("/")).replace("rec_", "")
        for m in meta:
            out.append((run, os.path.join(d, m["file"]), m))
    rng = np.random.default_rng(7)
    return [(run, f, m, (rng.uniform(0, 150.0), rng.uniform(0, 2 * math.pi))) for run, f, m in out]


def make_day_matcher(a):
    import torch
    from day_pkg import learned_matcher as lm
    from day_pkg import local_matcher
    st = Stages(torch)
    local_matcher.LocalMatcher.locate = st.wrap("sift", local_matcher.LocalMatcher.locate)
    if a.matcher == "sift":
        M = local_matcher.LocalMatcher(a.area, zoom=17)
        return M, st, torch
    kw = {}
    if a.cache_dir:
        kw["cache_dir"] = a.cache_dir
    M = lm.LearnedMatcher(a.area, zoom=17, **kw)
    M._frame_features = st.wrap("frame_feat", M._frame_features)
    M.map_features = st.wrap("map_gather", M.map_features)
    M._features = st.wrap("disk", M._features)
    M.lg = _Callable(st.wrap("lightglue", M.lg))
    lm.refine_with_pose = st.wrap("pose", lm.refine_with_pose)
    M._locate_learned = st.wrap("learned_total", M._locate_learned)
    return M, st, torch


def run_day_frames(M, st, torch, frames, search_m, rows, deadline=None, verbose=True):
    """Locate each frame; append one row per frame; returns when done or past `deadline` (time.time())."""
    for run, f, m, (r_off, b_off) in frames:
        if deadline is not None and time.time() > deadline:
            return False
        img = cv2.imread(f)
        if img is None:
            continue
        truth = tuple(m["truth"])
        prior = (truth[0] + r_off * math.cos(b_off) / 111320.0,
                 truth[1] + r_off * math.sin(b_off) / (111320.0 * math.cos(math.radians(truth[0]))))
        t0 = time.perf_counter()
        r = M.locate(img, prior, search_m, m["mpp"], scale_tol=0.15, heading_deg=m.get("rot_deg") or 0.0,
                     heading_tol_deg=15.0)
        if torch is not None and torch.cuda.is_available():
            torch.cuda.synchronize()
        ms = (time.perf_counter() - t0) * 1000.0
        ok = bool(r["accepted"])
        row = {"run": run, "file": os.path.basename(f), "accepted": ok, "ms": round(ms, 1),
               "features": r.get("features", "sift"), "inliers": r.get("inliers"),
               "lat": r.get("predicted_lat") if ok else None, "lon": r.get("predicted_lon") if ok else None,
               "err": round(metres((r["predicted_lat"], r["predicted_lon"]), truth), 2) if ok else None,
               "unc": m.get("truth_unc_m") or 0.0, "stages": st.take(), "rss_mb": round(rss_mb())}
        rows.append(row)
        if verbose:
            print(f"{run:16s} {row['file']} {'OK ' if ok else '-- '} {ms:7.0f} ms "
                  f"{row['features']:14s} err {row['err']}  {row['stages']}", flush=True)
    return True


def day_summary(rows):
    fair = [r for r in rows if r["unc"] <= 10.0]
    acc = [r for r in fair if r["accepted"]]
    e = sorted(r["err"] for r in acc)
    stages = defaultdict(list)
    for r in rows:
        for k, v in r["stages"].items():
            stages[k].append(v)
    ms = [r["ms"] for r in rows]
    return {"frames": len(rows), "fair_frames": len(fair), "accepted": len(acc),
            "err_median": round(statistics.median(e), 1) if e else None,
            "err_p90": round(e[min(len(e) - 1, int(0.9 * len(e)))], 1) if e else None,
            "wrong_gt50": sum(x > 50 for x in e),
            "ms_median": round(statistics.median(ms)) if ms else None,
            "ms_p90": round(sorted(ms)[min(len(ms) - 1, int(0.9 * len(ms)))]) if ms else None,
            "ms_mean": round(statistics.mean(ms)) if ms else None,
            "stage_ms_mean_per_frame": {k: round(sum(v) / len(rows), 1) for k, v in stages.items()},
            "sift_fallback_frames": sum("sift" in r["stages"] for r in rows),
            "by_features": {k: sum(r["features"] == k for r in rows) for k in {r["features"] for r in rows}}}


def mem_report(torch):
    out = {"peak_rss_mb": round(peak_rss_mb()), "rss_mb": round(rss_mb())}
    if torch is not None and torch.cuda.is_available():
        out["torch_peak_alloc_mb"] = round(torch.cuda.max_memory_allocated() / 2 ** 20)
        out["torch_peak_reserved_mb"] = round(torch.cuda.max_memory_reserved() / 2 ** 20)
    return out


def cmd_day(a):
    frames = load_frames(a.dirs, a.stride, a.limit)
    M, st, torch = make_day_matcher(a)
    if a.warmup:
        run_day_frames(M, st, torch, frames[:a.warmup], a.search_m, [], verbose=False)
    st.take()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    reset_peak_rss()
    rows = []
    mon = TegraMonitor(a.tegra) if a.tegra else None
    if mon:
        mon.start()
    try:
        run_day_frames(M, st, torch, frames, a.search_m, rows, verbose=not a.quiet)
    finally:
        if mon:
            mon.stop()
    out = {"mode": "day", "matcher": a.matcher, "search_m": a.search_m, "trt": os.environ.get("NAVERA_TRT", ""),
           "summary": day_summary(rows), "memory": mem_report(torch),
           "power": mon.summary() if mon else None, "rows": rows}
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


def cmd_endurance(a):
    frames = load_frames(a.dirs, 1, 0)
    M, st, torch = make_day_matcher(a)
    reset_peak_rss()
    rows = []
    mon = TegraMonitor(a.tegra, interval_ms=1000)
    mon.start()
    deadline = time.time() + a.minutes * 60.0
    laps = 0
    try:
        while time.time() < deadline:
            run_day_frames(M, st, torch, frames, a.search_m, rows, deadline=deadline, verbose=False)
            laps += 1
            s = mon.summary()
            print(f"lap {laps}: {len(rows)} frames, {s.get('seconds', 0):.0f} s, VDD_IN "
                  f"{s.get('VDD_IN')}, tj {s.get('t_tj')}, gpu MHz {s.get('gpu_mhz_busy')}", flush=True)
    finally:
        mon.stop()
    out = {"mode": "endurance", "minutes": a.minutes, "laps": laps, "summary": day_summary(rows),
           "memory": mem_report(torch), "power": mon.summary()}
    # latency drift over the run (thermal throttling shows as a slower second half)
    n = len(rows)
    if n >= 10:
        out["ms_median_first_quarter"] = round(statistics.median(r["ms"] for r in rows[:n // 4]))
        out["ms_median_last_quarter"] = round(statistics.median(r["ms"] for r in rows[-n // 4:]))
    print(json.dumps(out, indent=1))
    if a.json:
        json.dump(dict(out, rows=rows), open(a.json, "w"), indent=1)


def cmd_night(a):
    import torch
    sys.argv = [sys.argv[0]]
    import night_conditions as nc
    from night_pkg.nodes import night_localizer as nl
    st = Stages(torch)
    mbtiles = os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles"))
    sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
    weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))
    nl.normalize_query = st.wrap("normalize", nl.normalize_query)
    nl._stitch_satellite_patch = st.wrap("map_patch", nl._stitch_satellite_patch)
    nl.verify_match = st.wrap("verify", nl.verify_match)
    # the night node's retries (night_subscriber heading_retry_deg / height_retry defaults)
    nc.HEADING_RETRY = tuple(float(x) for x in a.heading_retry.split(",") if x.strip())
    nc.HEIGHT_RETRY = tuple(float(x) for x in a.height_retry.split(",") if x.strip())
    conds = nc.CONDITIONS
    if a.only:
        keys = set(a.only.split(","))
        conds = [c for c in conds if c.name in keys or c.group in keys]
    from navera_common.camera_model import CameraModel
    from navera_common.frame_builder import FrameBuilder
    lens = dict(model="pinhole", image_width=nc.SIZE[0], image_height=nc.SIZE[1], distortion=[],
                camera_matrix=CameraModel.ideal(nc.HFOV_DEG, nc.SIZE).K.ravel().tolist())
    tiles = nc.Tiles(mbtiles)
    cam = nc._GeomCamera(lens, tiles.get)
    fb = FrameBuilder(CameraModel.ideal(nc.HFOV_DEG, nc.SIZE), camera_type="thermal")
    reset_peak_rss()
    loc = nl.NightLocalizer(sthn, weights, mbtiles, sthn_backend=a.backend)
    print(f"STHN backend: {loc.sthn_backend}", flush=True)
    model_rss = rss_mb()
    forward = loc._model.forward
    loc._model.forward = st.wrap("sthn_forward", forward)
    loc._localize_once = st.wrap("localize_once", loc._localize_once)
    torch.cuda.reset_peak_memory_stats()
    summaries, rows = [], []
    mon = TegraMonitor(a.tegra) if a.tegra else None
    if mon:
        mon.start()
    stage_rows = []
    orig_loc = loc.localize

    def localize(*k, **kw):
        t0 = time.perf_counter()
        r = orig_loc(*k, **kw)
        stage_rows.append(dict(st.take(), total=round((time.perf_counter() - t0) * 1000.0, 1),
                               lat=r.get("lat") if r.get("success") else None,
                               lon=r.get("lon") if r.get("success") else None))
        return r
    loc.localize = localize
    try:
        for c in conds:
            s, rr = nc.run_condition(c, loc, cam, fb, a.n, None)
            summaries.append(s)
            rows += rr
            print(f"{c.name}: {s['accepted']}/{s['n']} accepted, median {s['median_m']}, wrong {s['wrong']}, "
                  f"ms {s['ms_median']:.0f}", flush=True)
    finally:
        if mon:
            mon.stop()
    for r, sr in zip(rows, stage_rows):
        r["lat"], r["lon"] = sr.pop("lat"), sr.pop("lon")
    stage_mean = {k: round(statistics.mean(r.get(k, 0.0) for r in stage_rows), 1)
                  for k in sorted({k for r in stage_rows for k in r})}
    out = {"mode": "night", "backend": loc.sthn_backend, "frames": len(stage_rows),
           "stage_ms_mean_per_frame": stage_mean,
           "total_ms_median": round(statistics.median(r["total"] for r in stage_rows)),
           "memory": dict(mem_report(torch), model_loaded_rss_mb=round(model_rss)),
           "power": mon.summary() if mon else None,
           "conditions": summaries}
    print(json.dumps({k: v for k, v in out.items() if k != "conditions"}, indent=1))
    nc.print_table(summaries)
    if a.json:
        json.dump(dict(out, rows=rows), open(a.json, "w"), indent=1, default=str)


def cmd_celestial(a):
    """allsky.locate (CPU, numpy) on the celestial360_conditions synthetic skies, one process, serial."""
    import cProfile
    import pstats
    sys.path.insert(0, os.path.join(ROOT, "navera_tools", "sim"))
    sys.path.insert(0, os.path.join(ROOT, "cn_pkg"))
    import celestial360_conditions as cc
    conds = cc.conditions()
    if a.only:
        keys = [k.strip() for k in a.only.split(",") if k.strip()]
        conds = [c for c in conds if any(k in c.name for k in keys)]
    jobs = [(c, s) for c in conds for s in range(a.seeds)]
    reset_peak_rss()
    mon = TegraMonitor(a.tegra) if a.tegra else None
    if mon:
        mon.start()
    prof = cProfile.Profile()
    rows = []
    t0 = time.time()
    try:
        for j in jobs:
            prof.enable()
            r = cc.run_one(j)
            prof.disable()
            rows.append(r)
    finally:
        if mon:
            mon.stop()
    wall = time.time() - t0
    st = pstats.Stats(prof)
    top = sorted(((v[3], f"{os.path.basename(k[0])}:{k[2]}") for k, v in st.stats.items()
                  if "cn_pkg" in k[0] or "celestial360" in k[0]), reverse=True)[:12]
    solved = [r for r in rows if r.get("solved")]
    ts = [r["t"] for r in rows if r.get("t")]
    out = {"mode": "celestial", "frames": len(rows), "solved": len(solved), "wall_s": round(wall, 1),
           "solve_s_median": round(statistics.median(ts), 2) if ts else None,
           "solve_s_p90": round(sorted(ts)[int(0.9 * (len(ts) - 1))], 2) if ts else None,
           "cum_s_top": [(round(c, 1), n) for c, n in top],
           "memory": {"peak_rss_mb": round(peak_rss_mb()), "rss_mb": round(rss_mb())},
           "power": mon.summary() if mon else None}
    print(json.dumps(out, indent=1))
    if a.json:
        json.dump(dict(out, rows=rows), open(a.json, "w"), indent=1, default=float)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("day", "endurance"):
        p = sub.add_parser(name)
        p.add_argument("dirs", nargs="+")
        p.add_argument("--area", default=DEFAULT_AREA)
        p.add_argument("--cache-dir", default="")
        p.add_argument("--matcher", choices=("learned", "sift"), default="learned")
        p.add_argument("--search-m", type=float, default=400.0)
        p.add_argument("--json", default="")
        p.add_argument("--tegra", default="")
        if name == "day":
            p.add_argument("--stride", type=int, default=1)
            p.add_argument("--limit", type=int, default=0, help="frames per recording (0: all)")
            p.add_argument("--warmup", type=int, default=3)
            p.add_argument("--quiet", action="store_true")
        else:
            p.add_argument("--minutes", type=float, default=30.0)
    p = sub.add_parser("night")
    p.add_argument("--n", type=int, default=16)
    p.add_argument("--only", default="")
    p.add_argument("--backend", default="auto", help="NightLocalizer sthn_backend: auto | torch | graph | trt")
    p.add_argument("--heading-retry", default="-10,10,-20,20")
    p.add_argument("--height-retry", default="0.1,-0.1,0.2")
    p.add_argument("--json", default="")
    p.add_argument("--tegra", default="")
    p = sub.add_parser("celestial")
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--only", default="")
    p.add_argument("--json", default="")
    p.add_argument("--tegra", default="")
    a = ap.parse_args()
    {"day": cmd_day, "endurance": cmd_endurance, "night": cmd_night, "celestial": cmd_celestial}[a.cmd](a)


if __name__ == "__main__":
    main()
