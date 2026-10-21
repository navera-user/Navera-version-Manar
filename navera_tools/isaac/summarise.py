#!/usr/bin/env python3
"""Numbers of one Isaac Sim flight from isaac_link.py's record (position.csv, day.csv, events.jsonl).

    python3 navera_tools/isaac/summarise.py ~/navera_results/<run> [--gps-cut 60]

After the GPS cut:
  frames        day_subscriber answers (day_status, one per frame it processed)
  accepted %    of those, map matches day_subscriber accepted (success, not dead-reckoning)
  fix error     measured day fixes vs the truth at the fix's sensor stamp (what NAVERA claims)
                and at the frame's TRUE exposure (the matching alone): median / p90 / max
  wrong fixes   measured day fixes > 50 m from the truth at the true exposure
  output error  /navera/position (whatever the arbiter publishes: fixes and dead-reckoning)
  autopilot     (closed loop) the autopilot's EKF position vs the truth
  ms/frame      frame_meta -> frame_done (live_camera hands the frame over -> day_subscriber acks),
                after the cut
"""
import csv
import json
import math
import os
import sys

WRONG_M = 50.0
NOT_A_MATCH = ("dead_reckon", "gps", "gps_active", "unusable", "none")


def _q(v, p):
    return round(v[min(len(v) - 1, int(p * len(v)))], 1) if v else None


def stats(v):
    v = sorted(x for x in v if math.isfinite(x))
    return dict(n=len(v), median=_q(v, 0.5), p90=_q(v, 0.9), max=round(v[-1], 1) if v else None)


def summarise(results: str, gps_cut_s: float = 60.0) -> dict:
    rd = lambda n: list(csv.DictReader(open(os.path.join(results, n)))) if os.path.exists(os.path.join(results, n)) else []  # noqa: E731
    pos, day = rd("position.csv"), rd("day.csv")
    ev = []
    if os.path.exists(os.path.join(results, "events.jsonl")):
        ev = [json.loads(line) for line in open(os.path.join(results, "events.jsonl")) if line.strip()]
    # the flight ends with Isaac's last frame: NAVERA's dead-reckoning after it is not the flight
    t_end = float("inf")
    fj = os.path.join(results, "frames.jsonl")
    if os.path.exists(fj):
        ts = [json.loads(line)["t"] for line in open(fj) if line.strip()]
        if ts:
            t_end = max(ts) + 3.0
    f = lambda r, k: float(r[k]) if r.get(k) not in (None, "", "nan") else float("nan")  # noqa: E731
    st_after = [e["day_status"] for e in ev if gps_cut_s <= e["t"] <= t_end and "frame_id" in e.get("day_status", {})
                and e["day_status"].get("source") not in ("gps", "gps_active")]
    acc = [s for s in st_after if s.get("success") and s.get("source") not in NOT_A_MATCH]
    meas = [r for r in day if gps_cut_s <= f(r, "t") <= t_end and r["mode"] == "measured" and r["valid"] == "1"]
    wrong = [r for r in meas if f(r, "err_frame_m") > WRONG_M]
    out_after = [r for r in pos if gps_cut_s <= f(r, "t") <= t_end and r["valid"] == "1"]
    gps_phase = [r for r in pos if f(r, "t") < gps_cut_s and r["valid"] == "1"]
    by_src = {}
    for r in out_after:
        k = f"{r['source']}/{r['mode']}"
        by_src[k] = by_src.get(k, 0) + 1
    ekf = [r for r in rd("ekf.csv") if gps_cut_s <= f(r, "t") <= t_end]
    proc = [f(r, "proc_ms") for r in rd("proc.csv") if gps_cut_s <= f(r, "t") <= t_end]
    sources = {}
    for s in st_after:
        sources[s.get("source", "?")] = sources.get(s.get("source", "?"), 0) + 1
    lat = [e["day_status"]["latency"] for e in ev if isinstance(e.get("day_status", {}).get("latency"), dict)]
    beyond = [r for r in out_after if f(r, "sigma_m") > 0 and f(r, "err_m") > 3.0 * f(r, "sigma_m")]
    mission = None
    fl = os.path.join(results, "sitl_flown.json")
    if os.path.exists(fl):
        flown = json.load(open(fl))
        ss = json.load(open(os.path.join(results, "sitl_session.json")))
        ek = rd("ekf.csv")
        end_m = None
        if ek:
            la, lo = f(ek[-1], "truth_lat"), f(ek[-1], "truth_lon")
            end_m = round(math.hypot((la - ss["lat0"]) * 111320.0,
                                     (lo - ss["lon0"]) * 111320.0 * math.cos(math.radians(ss["lat0"]))), 1)
        texts = [json.loads(line).get("text", "") for line in open(os.path.join(results, "sitl_events.jsonl"))
                 if '"text"' in line]
        mission = dict(completed=flown.get("home_at") is not None, final_dist_from_home_m=end_m,
                       failsafe=[x for x in texts if "ailsafe" in x][:3], cut_at=flown.get("cut_at"),
                       home_at=flown.get("home_at"))
    return dict(
        flight_end_s=round(t_end, 1),
        mission=mission,
        output_beyond_3sigma=dict(n=len(beyond), of=len(out_after)),
        after_cut=dict(frames=len(st_after), accepted=len(acc),
                       accepted_pct=round(100.0 * len(acc) / len(st_after), 1) if st_after else None,
                       frame_sources=sources,
                       fix_err_stamp_m=stats([f(r, "err_m") for r in meas]),
                       fix_err_exposure_m=stats([f(r, "err_frame_m") for r in meas]),
                       wrong_fixes=len(wrong), wrong_t=[round(f(r, "t"), 1) for r in wrong][:20],
                       output_err_m=stats([f(r, "err_m") for r in out_after]), output_by_source=by_src,
                       output_seconds=round(f(out_after[-1], "t") - f(out_after[0], "t"), 1) if out_after else 0),
        autopilot_ekf_err_after_cut_m=stats([f(r, "err_m") for r in ekf]) if ekf else None,
        gps_phase_output_err_m=stats([f(r, "err_m") for r in gps_phase]),
        ms_per_frame=stats(proc),
        latency_last=lat[-1] if lat else None)


if __name__ == "__main__":
    cut = float(sys.argv[sys.argv.index("--gps-cut") + 1]) if "--gps-cut" in sys.argv else 60.0
    print(json.dumps(summarise(os.path.expanduser(sys.argv[1]), cut), indent=1))
