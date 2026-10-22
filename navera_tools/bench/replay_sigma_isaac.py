#!/usr/bin/env python3
"""Replay the GPS-lost part of an Isaac Sim closed-loop run through the day node's own fix logic, offline.

    python3 navera_tools/bench/replay_sigma_isaac.py RUN_DIR [RUN_DIR ...] [--variants all|base,...]
    python3 navera_tools/bench/replay_sigma_isaac.py --extract RUN_DIR --out FIXTURE.json.gz

SIMULATION data (navera_tools/isaac campaign runs: day.csv, events.jsonl, frames.jsonl, summary.json,
logs/day.log). The recorded matcher answers after the GPS cut (each frame's raw match: position before the
mount correction, inliers, fitted rotation, which candidate) go through DaySubscriber._publish_result —
the product code, built by its own __init__ with the shipped defaults, on a virtual clock: mount
correction and mount sigma, map bias, consistency gate, kinematic gate, blending with the carried
position, the track, the carry, dead-reckoning of the frames whose match was refused. What the GPS phase
taught the node is set as it stood at the cut (recorded): the mount calibration per position kind, the
sigma calibration (factor, flight floor), the map bias of each fix, the camera delay applied (if any).

Each variant toggles one feature (node attributes), so that the regression of 2026-10-22 (Isaac base:
c3_base 12.8 m / 1 of 317 beyond 3 sigma -> pd_ref_base 19 m / 146 of 356) can be bisected without a flight.
Printed per run and variant: measured fixes, error at the stated time and at the exposure
(median/p90/max), share beyond 3 stated sigma, wrong fixes (> 50 m from the truth at the exposure:
summarise.py's rule), median stated sigma.
"""
import argparse
import contextlib
import csv
import gzip
import json
import math
import os
import re
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ["ROS_DOMAIN_ID"] = os.environ.get("REPLAY_ROS_DOMAIN_ID", "86")
os.environ["ROS_LOCALHOST_ONLY"] = "1"
os.environ.setdefault("NAVERA_STATE_DIR", tempfile.mkdtemp(prefix="navera_replay_state_"))

M = 111320.0
WRONG_M = 50.0                                     # summarise.py: a wrong fix
MAP_MPP_Z17 = 156543.03392 * math.cos(math.radians(35.8685)) / 2 ** 17


def _en(p, ref):
    return ((p[1] - ref[1]) * M * math.cos(math.radians(ref[0])), (p[0] - ref[0]) * M)


def _dist(p, q):
    return math.hypot(*_en(p, q))


# ── extraction: a run directory -> a compact replay record ─────────────────────────────────────
def extract(run: str) -> dict:
    """The run's GPS-lost frames and what the node had learned by the cut (see the module doc)."""
    summ = json.load(open(os.path.join(run, "summary.json")))
    sess = json.load(open(os.path.join(run, "session.json")))
    cut = float(summ["mission"]["cut_at"])
    fr = [json.loads(x) for x in open(os.path.join(run, "frames.jsonl"))]
    T = np.array([(f["t"], f["lat"], f["lon"], f.get("z", 0.0), f.get("heading", 0.0)) for f in fr])
    hd = np.unwrap(np.radians(T[:, 4]))

    def truth(t):
        return (float(np.interp(t, T[:, 0], T[:, 1])), float(np.interp(t, T[:, 0], T[:, 2])))

    def heading(t):
        return float(np.degrees(np.interp(t, T[:, 0], hd)) % 360.0)

    day = {}
    for r in csv.DictReader(open(os.path.join(run, "day.csv"))):
        day.setdefault(int(r["frame"]), r)
    events = [json.loads(x) for x in open(os.path.join(run, "events.jsonl"))]
    rows, mount, sig_cal, lat_applied = [], {}, None, None
    for e in events:
        d = e.get("day_status") or {}
        if e["t"] < cut or d.get("raw_lat") is None or d.get("matcher") != "local":
            continue
        r = day.get(int(d.get("frame_id", -1)))
        if r is None:
            continue
        stamp, t_exp = float(r["t"]), float(r["t_exposure"])
        accepted = d.get("source") == "local_match" or "geometric inliers" not in str(d.get("reason"))
        if d.get("source") != "local_match":
            # a match the matcher itself refused (too few inliers): the node dead-reckons
            accepted = False
        kind = d.get("position_from") or "frame centre"
        mc = d.get("mount_cal")
        if mc and mc.get("calibrated") and kind not in mount:
            mount[kind] = {"top_deg": mc.get("top_deg"), "right_deg": mc.get("right_deg"),
                           "sigma_deg": mc.get("sigma_deg")}
        sc = d.get("sigma_cal")
        if sc is not None and sig_cal is None:
            sig_cal = {"factor": sc.get("factor"), "floor_m": sc.get("flight_floor_m"),
                       "calibrated": bool(sc.get("calibrated"))}
        la = d.get("latency") or {}
        if lat_applied is None:
            lat_applied = {"applied_s": la.get("applied_s"), "applied_sigma_s": la.get("applied_sigma_s")}
        rows.append({
            "t": round(e["t"], 3), "frame": int(d["frame_id"]), "stamp": round(stamp, 3), "t_exp": round(t_exp, 3),
            "accepted": accepted, "raw": [d["raw_lat"], d["raw_lon"]], "inliers": int(d.get("inliers") or 0),
            "rotation_deg": d.get("rotation_deg"), "kind": kind, "map_bias_m": d.get("map_bias_m"),
            "reason": None if accepted else d.get("reason"),
            "height_m": round(float(np.interp(stamp, T[:, 0], T[:, 3])), 1), "heading_deg": round(heading(stamp), 2),
            "truth_stamp": [round(v, 7) for v in truth(stamp)], "truth_exp": [round(v, 7) for v in truth(t_exp)]})
    # the mount calibration of the kinds no post-cut fix showed: the last one saved before the cut
    t0 = float(sess.get("t0_wall", 0.0))
    try:
        for line in open(os.path.join(run, "logs", "day.log"), errors="replace"):
            m = re.search(r"\[(\d+\.\d+)\].*camera mount calibration saved: (\{.*\})", line)
            if m and float(m.group(1)) - t0 <= cut:
                saved = json.loads(m.group(2))
                for k, v in saved.items():
                    if k not in mount or mount[k].get("_from_log"):
                        mount[k] = dict(v, _from_log=True)
    except OSError:
        pass
    gps = [(float(r["t"]), float(r["lat"]), float(r["lon"]), float(r["sigma_m"] or 1.5))
           for r in csv.DictReader(open(os.path.join(run, "position.csv")))
           if r["gps"] == "on" and r["source"] == "gps" and cut - 20.0 <= float(r["t"]) <= cut
           and r["lat"] not in ("", "nan")]
    gps = gps[::5] if len(gps) > 100 else gps            # ~ the node's 1-5 Hz GPS
    mount_on = any(e.get("day_status", {}).get("mount_cal") for e in events if e["t"] >= cut)
    return {"run": os.path.basename(os.path.normpath(run)), "vehicle": sess.get("vehicle"), "cut": cut,
            "mount_cal_on": bool(mount_on), "mount": {k: {a: b for a, b in v.items() if not a.startswith("_")}
                                                      for k, v in mount.items()},
            "sigma_cal": sig_cal, "latency": lat_applied, "gps": gps, "rows": rows}


def load(path: str) -> dict:
    """A replay record: a run directory (extracted now) or a fixture (.json / .json.gz)."""
    if os.path.isdir(path):
        return extract(path)
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt") as f:
        return json.load(f)


# ── the node, on a virtual clock ───────────────────────────────────────────────────────────────
class VClock:
    now = 0.0


class _FakeTime:
    def time(self):
        return VClock.now

    def monotonic(self):
        return VClock.now

    def __getattr__(self, n):
        import time as _t
        return getattr(_t, n)


class _NoMatcher:
    """Stands for the matcher: the recorded answers are given to _publish_result directly."""
    torch = None

    def __init__(self, *a, **k):
        self.tiles = type("T", (), {"prefetch": staticmethod(lambda *x, **k: None)})()

    def locate(self, *a, **k):
        return {"accepted": False, "reason": "replay"}


class _Pub:
    def __init__(self, fn=None, topic="replay"):
        self.fn, self.topic_name = fn, topic

    def publish(self, m):
        if self.fn is not None:
            self.fn(m)


class _FixedSigmaCal:
    """The sigma calibration as it stood at the cut (factor, flight floor), or the no-calibration floor."""
    def __init__(self, base, factor, floor_m):
        self._b, self._t = base, (None if factor is None else (float(factor), float(floor_m or 0.0)))

    def terms(self):
        return self._t

    def apply(self, s):
        if self._t is None:
            return max(float(s), self._b.floor_no_cal_m)
        return math.hypot(float(s) * self._t[0], self._t[1])

    def state(self):
        return {"calibrated": self._t is not None}

    def __getattr__(self, n):
        return getattr(self._b, n)


class _RecordedMapBias:
    """The map bias each fix had (recorded): set before each frame."""
    current = None

    def bias(self, p):
        return tuple(self.current) if self.current else (0.0, 0.0)


@contextlib.contextmanager
def _patched():
    """The product modules on the virtual clock, without a matcher, a map or a state store; restored after
    (a pytest process runs other tests with the real ones)."""
    import day_pkg.nodes.day_subscriber as ds
    import day_pkg.vision_nav as vn
    import day_pkg.learned_matcher as lm
    import navera_common.prior as prior_mod
    fake = _FakeTime()
    saved = [(m, n, getattr(m, n)) for m, n in ((ds, "time"), (vn, "time"), (prior_mod, "time"),
                                                (ds, "state_store"), (ds, "LocalMatcher"), (ds, "area_zooms"),
                                                (lm, "LearnedMatcher"))]
    try:
        for mod in (ds, vn, prior_mod):
            mod.time = fake
        ds.state_store = type("NoState", (), {"save": staticmethod(lambda *x, **k: True),
                                              "load": staticmethod(lambda *x, **k: None)})
        ds.LocalMatcher = lm.LearnedMatcher = _NoMatcher
        ds.area_zooms = lambda *_a, **_k: [17]
        yield ds
    finally:
        for m, n, v in saved:
            setattr(m, n, v)


def make_node(ds, params=None):
    """A DaySubscriber built by its own __init__ (shipped defaults, + params), inside _patched()."""
    from rclpy.parameter import Parameter
    node = ds.DaySubscriber()
    if params:
        # parameters read at __init__ time: re-run the parts that read them
        node.set_parameters([Parameter(k, value=v) for k, v in params.items()])
        node._init_mount_cal()
        node.blend_fixes = bool(node.get_parameter("blend_fixes").value)
        node.strong_gate_k = float(node.get_parameter("strong_gate_k_sigma").value)
        node.consistency.strong_gate_k = node.strong_gate_k
        node.unknown_delay_sigma_s = float(node.get_parameter("unknown_delay_sigma_s").value)
    for name in ("pub_fix", "pub_status", "pub_done", "pub_ready", "pub_vision_alt", "pub_gps_vo", "pub_cam_delay"):
        setattr(node, name, _Pub())
    return node


def replay(rec: dict, params=None, setup=None):
    """Run the record's GPS-lost frames through a fresh node. params: ROS parameters (product defaults
    otherwise); setup(node): a last change before the frames (a variant). Returns the outputs."""
    import rclpy
    owned = not rclpy.ok()                  # a context of our own is shut down after: a pytest process
    if owned:                               # that forks later must not carry DDS threads
        rclpy.init(args=["--ros-args", "--log-level", "error"])
    try:
        with _patched() as ds:
            return _replay(ds, rec, params, setup)
    finally:
        if owned:
            rclpy.shutdown()


def _replay(ds, rec, params, setup):
    from navera_msgs.msg import PositionEstimate
    node = make_node(ds, params)
    out = []

    def on_est(m):
        if m.source != PositionEstimate.SOURCE_DAY_VISION or not m.valid:
            return
        d = json.loads(m.details_json or "{}")
        sig = math.sqrt(m.position_covariance[0]) if m.position_covariance[0] > 0 else float("nan")
        out.append({"src": d.get("src"), "lat": m.latitude, "lon": m.longitude, "sigma": sig})
    node.pub_est = _Pub(on_est)
    # what the GPS phase left: the track and anchor on the last GPS points, the calibrations at the cut
    for t, la, lo, s in rec["gps"]:
        node.track.add(t, la, lo, s)
    if rec["gps"]:
        t, la, lo, s = rec["gps"][-1]
        node._anchor_lat, node._anchor_lon, node._anchor_time = la, lo, t
        node._anchor_sigma, node._last_measured_time = s, t
    sc = rec.get("sigma_cal") or {}
    node.sigma_cal = _FixedSigmaCal(node.sigma_cal, sc.get("factor") if sc.get("calibrated") else None,
                                    sc.get("floor_m"))
    mb = _RecordedMapBias()
    node.map_bias = mb
    lat = rec.get("latency") or {}
    if lat.get("applied_s") is not None:
        node.latency_cal.applied = float(lat["applied_s"])
        node.latency_cal.applied_sigma = float(lat.get("applied_sigma_s") or 0.0)
    # the mount calibration learned by the cut — if the code under test would have learned it: its rule
    # for a GPS-check sample (F38: _mount_sample_refused) with the camera delay as it stood at the cut
    if node.mount_cal is not None and rec.get("mount_cal_on") and \
            (not hasattr(node, "_mount_sample_refused") or node._mount_sample_refused(gps_velocity(rec)) is None):
        for k, v in (rec.get("mount") or {}).items():
            node.mount_cal.set_prior(k, v["top_deg"], v["right_deg"], max(float(v["sigma_deg"]), 1e-3))
    node._gps_was_trusted = False
    if setup is not None:
        setup(node)
    res = []
    for r in rec["rows"]:
        VClock.now = float(r["t"])
        meta = {"frame_id": r["frame"], "image_stamp_ns": int(round(r["stamp"] * 1e9)),
                "altitude_m": r["height_m"], "heading_deg": r["heading_deg"], "attitude_source": "imu",
                "straightened": True}
        mb.current = r.get("map_bias_m")
        result = {"matcher": "local", "accepted": bool(r["accepted"]), "predicted_lat": r["raw"][0],
                  "predicted_lon": r["raw"][1], "inliers": r["inliers"], "spread": 1.0, "score": float(r["inliers"]),
                  "sigma_m": None if not r["accepted"] else
                  (4.0 if r["inliers"] >= 100 else 8.0 if r["inliers"] >= 50 else 15.0 if r["inliers"] >= 20 else 25.0)
                  * MAP_MPP_Z17,
                  "rotation_deg": r.get("rotation_deg"), "position_from": r["kind"], "spatial": True,
                  "radius_m": 80.0, "reason": r.get("reason")}
        n0 = len(out)
        node._publish_result(r["frame"], meta, result)
        for o in out[n0:]:
            o.update(t=r["stamp"], frame=r["frame"],
                     err=_dist((o["lat"], o["lon"]), r["truth_stamp"]),
                     err_exp=_dist((o["lat"], o["lon"]), r["truth_exp"]))
            res.append(o)
    node.destroy_node()
    return res


def gps_velocity(rec: dict):
    """(east, north) m/s of the GPS over its last ~5 s before the cut, or None."""
    g = rec.get("gps") or []
    if len(g) < 2:
        return None
    last = g[-1]
    first = next((p for p in g if last[0] - p[0] <= 5.0), g[0])
    dt = last[0] - first[0]
    if dt <= 0:
        return None
    e, n = _en(last[1:3], first[1:3])
    return (e / dt, n / dt)


def score(res) -> dict:
    meas = [o for o in res if o["src"] == "local_match"]
    allo = [o for o in res if math.isfinite(o["sigma"])]

    def st(v):
        if not v:
            return None
        return [round(float(np.median(v)), 1), round(float(np.percentile(v, 90)), 1), round(float(max(v)), 1)]
    beyond = sum(1 for o in allo if o["err"] > 3.0 * o["sigma"])
    return {"fixes": len(meas), "outputs": len(allo), "err": st([o["err"] for o in meas]),
            "err_exp": st([o["err_exp"] for o in meas]),
            "beyond_3sigma": beyond, "beyond_pct": round(100.0 * beyond / max(1, len(allo)), 1),
            "wrong": sum(1 for o in meas if o["err_exp"] > WRONG_M),
            "sigma_med": round(float(np.median([o["sigma"] for o in meas])), 1) if meas else None}


VARIANTS = {
    "product": ({}, None),
    "no_blend": ({"blend_fixes": False}, None),
    "no_mount_cal": ({"mount_cal": False}, None),
    "no_blend_no_mount": ({"blend_fixes": False, "mount_cal": False}, None),
    "strong_gate_6": ({"strong_gate_k_sigma": 6.0}, None),
    "no_delay_sigma": ({"unknown_delay_sigma_s": 0.0}, None),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--variants", default="all")
    ap.add_argument("--extract", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    if a.extract:
        rec = extract(a.extract)
        with gzip.open(a.out, "wt") as f:
            json.dump(rec, f, separators=(",", ":"))
        print(f"{a.out}: {len(rec['rows'])} frames")
        return
    names = list(VARIANTS) if a.variants == "all" else a.variants.split(",")
    allres = {}
    for run in a.runs:
        rec = load(run)
        for n in names:
            params, setup = VARIANTS[n]
            s = score(replay(rec, params, setup))
            allres.setdefault(rec["run"], {})[n] = s
            print(f"{rec['run']:14s} {n:18s} fixes {s['fixes']:3d} err {s['err']} exp {s['err_exp']} "
                  f"sigma {s['sigma_med']} >3sig {s['beyond_3sigma']}/{s['outputs']} ({s['beyond_pct']} %) "
                  f"wrong {s['wrong']}", flush=True)
    if a.json:
        json.dump(allres, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
