#!/usr/bin/env python3
"""Numbers of one hardware-in-the-loop flight (hil_flight.sh): accuracy as summarise.py computes
it for the container runs, plus what only the real box shows — latency end to end, CPU / GPU /
memory / temperature, timing and network jitter, service restarts during the flight.

    python3 navera_tools/isaac/hil_summarise.py RESULTS [--baseline DIR_OF_A_CONTAINER_RUN]

Reads the box's record (hil_record.py) and the PC's files copied next to it (stream.csv: each
camera frame's send time and true exposure; sitl_gps.csv: the autopilot's GPS as fed by NAVERA;
frames.jsonl, sitl_*.json*), and hil_kills.jsonl (the nodes killed in flight). Writes
day.csv's exposure columns (the raw record is kept as day_box.csv), hil_summary.json and
hil_report.md. Box times are converted to the PC's clock with pc_offset_s (hil_t0.json).
SIMULATION (Isaac Sim + SITL) feeding the real box.
"""
import argparse
import bisect
import csv
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from summarise import stats, summarise  # noqa: E402

M_PER_DEG = 111320.0


def rows(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def fv(r, k):
    v = r.get(k)
    try:
        return float(v) if v not in (None, "", "nan") else float("nan")
    except ValueError:
        return float("nan")


def dist_m(lat1, lon1, lat2, lon2):
    return math.hypot((lat1 - lat2) * M_PER_DEG, (lon1 - lon2) * M_PER_DEG * math.cos(math.radians(lat1)))


class Truth:
    """truth.csv (t, lat, lon) interpolated."""

    def __init__(self, path):
        r = rows(path)
        self.t = [fv(x, "t") for x in r]
        self.lat = [fv(x, "lat") for x in r]
        self.lon = [fv(x, "lon") for x in r]

    def at(self, t):
        if len(self.t) < 2 or not math.isfinite(t):
            return None
        i = max(0, min(bisect.bisect_right(self.t, t) - 1, len(self.t) - 2))
        f = min(max((t - self.t[i]) / max(self.t[i + 1] - self.t[i], 1e-9), 0.0), 1.0)
        return self.lat[i] + f * (self.lat[i + 1] - self.lat[i]), self.lon[i] + f * (self.lon[i + 1] - self.lon[i])


def match_exposure(grab_pc, sent):
    """The stream frame a grab (PC clock) received: the last one sent before it, within 3 s."""
    i = bisect.bisect_right([s[0] for s in sent], grab_pc) - 1
    if i < 0 or grab_pc - sent[i][0] > 3.0:
        return None
    return sent[i]


def join_exposure(res, offset, t0, truth):
    """day.csv: t_exposure and err_frame_m from the PC's stream.csv; per-frame latency rows."""
    sent = sorted((fv(r, "wall"), fv(r, "t_exposure")) for r in rows(os.path.join(res, "stream.csv")))
    meta = {int(r["frame"]): r for r in rows(os.path.join(res, "hil_meta.csv")) if r.get("frame", "").lstrip("-").isdigit()}
    frames = {}
    for fid, r in meta.items():
        grab_pc = fv(r, "grab_box") + offset
        s = match_exposure(grab_pc, sent) if sent else None
        if s is None:
            continue
        frames[fid] = dict(t_exp=s[1], sent_pc=s[0], grab_pc=grab_pc, meta_pc=fv(r, "meta_rx_box") + offset)
    day_path = os.path.join(res, "day.csv")
    raw = os.path.join(res, "day_box.csv")
    if not os.path.exists(raw) and os.path.exists(day_path):
        shutil.copy(day_path, raw)
    day = rows(raw)
    with open(day_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(day[0].keys()) if day else
                           "t,frame,lat,lon,mode,valid,sigma_m,err_m,err_frame_m,t_exposure,proc_ms,reason".split(","))
        w.writeheader()
        for r in day:
            fr = frames.get(int(r["frame"])) if r["frame"].lstrip("-").isdigit() else None
            if fr and r["valid"] == "1":
                tr = truth.at(fr["t_exp"])
                if tr:
                    r["err_frame_m"] = f"{dist_m(fv(r, 'lat'), fv(r, 'lon'), tr[0], tr[1]):.2f}"
                r["t_exposure"] = f"{fr['t_exp']:.3f}"
            w.writerow(r)
    return frames


def latency(res, frames, offset, t0, cut):
    """Per measured day fix after the cut: where the time goes, exposure -> autopilot."""
    pos = rows(os.path.join(res, "hil_pos.csv"))
    hday = rows(os.path.join(res, "hil_day.csv"))
    proc = {int(r["frame"]): fv(r, "proc_ms") for r in rows(os.path.join(res, "proc.csv"))}
    pos_by_frame = {}
    for r in pos:
        if r["source"] == "day" and r["mode"] == "measured" and r["valid"] == "1":
            pos_by_frame.setdefault(int(r["frame"]), fv(r, "rx_box"))
    gps = [(fv(r, "wall"), fv(r, "lat"), fv(r, "lon")) for r in rows(os.path.join(res, "sitl_gps.csv"))
           if r.get("fix_type") not in (None, "", "0", "1")]
    # where the box's positions reached the autopilot: GPS_RAW_INT with the same coordinates
    by_ll = {}
    for w, la, lo in gps:
        by_ll.setdefault((round(la, 6), round(lo, 6)), w)
    posll = {}
    out = dict(sim_delay_s=[], transport_ms=[], camera_ms=[], day_ms=[], estimator_ms=[],
               exposure_to_position_s=[], exposure_to_autopilot_s=[], position_to_autopilot_ms=[])
    pos_rows = rows(os.path.join(res, "position.csv"))     # written row for row with hil_pos.csv
    for i, r in enumerate(pos):
        if i < len(pos_rows) and r["source"] == "day" and r["valid"] == "1":
            key = (round(fv(pos_rows[i], "lat"), 6), round(fv(pos_rows[i], "lon"), 6))
            posll[key] = fv(r, "rx_box")
    for r in hday:
        if r["valid"] != "1" or r["mode"] != "measured":
            continue
        fid = int(r["frame"])
        fr = frames.get(fid)
        if not fr or fr["t_exp"] < cut:
            continue
        exp_pc = t0 + fr["t_exp"]
        out["sim_delay_s"].append(fr["sent_pc"] - exp_pc)
        out["transport_ms"].append(1000 * (fr["grab_pc"] - fr["sent_pc"]))
        out["camera_ms"].append(1000 * (fr["meta_pc"] - fr["grab_pc"]))
        if fid in proc:
            out["day_ms"].append(proc[fid])
        p_rx = pos_by_frame.get(fid)
        if p_rx is not None:
            out["estimator_ms"].append(1000 * (p_rx - fv(r, "rx_box")))
            out["exposure_to_position_s"].append(p_rx + offset - exp_pc)
    for key, p_rx in posll.items():
        w = by_ll.get(key)
        if w is not None and 0 <= w - (p_rx + offset) < 5.0:
            out["position_to_autopilot_ms"].append(1000 * (w - (p_rx + offset)))
    res_ = {k: stats(v) for k, v in out.items() if k not in ("sim_delay_s", "exposure_to_position_s")}
    res_["sim_delay_s"] = stats([round(x, 3) for x in out["sim_delay_s"]])
    res_["exposure_to_position_s"] = stats(out["exposure_to_position_s"])
    if out["exposure_to_position_s"] and out["position_to_autopilot_ms"]:
        med_pa = sorted(out["position_to_autopilot_ms"])[len(out["position_to_autopilot_ms"]) // 2] / 1000.0
        res_["exposure_to_autopilot_s_median"] = round(res_["exposure_to_position_s"]["median"] + med_pa, 2)
    return res_


def system(res, flight):
    sys_ = [r for r in rows(os.path.join(res, "hil_sys.csv")) if flight[0] <= fv(r, "box") <= flight[1]]
    col = lambda k: [fv(r, k) for r in sys_ if math.isfinite(fv(r, k))]  # noqa: E731
    out = {k: stats(col(k)) for k in ("ram_mb", "swap_mb", "cpu_avg", "cpu_max", "gpu", "t_cpu", "t_gpu", "t_tj",
                                      "vdd_in_mw")}
    units = {}
    for r in rows(os.path.join(res, "hil_units.csv")):
        if not flight[0] <= fv(r, "box") <= flight[1]:
            continue
        u = units.setdefault(r["unit"], dict(mem=[], cpu=[], restarts=[], states=set()))
        if math.isfinite(fv(r, "mem_mb")):
            u["mem"].append(fv(r, "mem_mb"))
        u["cpu"].append((fv(r, "box"), fv(r, "cpu_s")))
        if r["restarts"].isdigit():
            u["restarts"].append(int(r["restarts"]))
        u["states"].add(r["state"])
    per = {}
    for name, u in units.items():
        c = [x for x in u["cpu"] if math.isfinite(x[1])]
        # CPU % of one core, averaged over the flight (a restart resets the counter: per segment)
        busy = span = 0.0
        for (t1, c1), (t2, c2) in zip(c, c[1:]):
            if c2 >= c1:
                busy, span = busy + c2 - c1, span + t2 - t1
        per[name.replace("navera-stage-", "").replace(".service", "")] = dict(
            mem_max_mb=max(u["mem"]) if u["mem"] else None,
            mem_median_mb=sorted(u["mem"])[len(u["mem"]) // 2] if u["mem"] else None,
            cpu_pct_one_core=round(100 * busy / span, 1) if span else None,
            restarts=(max(u["restarts"]) - min(u["restarts"])) if u["restarts"] else None,
            states=sorted(u["states"]))
    out["units"] = per
    return out


def jitter(res, flight, cut_box):
    rx = [r for r in rows(os.path.join(res, "hil_rx.csv")) if flight[0] <= fv(r, "box") <= flight[1]]
    out = {}
    for topic in ("vehicle_imu", "gps_est", "truth", "position"):
        rr = [r for r in rx if r["topic"] == topic]
        if topic == "gps_est":
            rr = [r for r in rr if fv(r, "box") < cut_box - 2]          # the receiver talks until the cut
        rate = [fv(r, "n") for r in rr]
        gap = [fv(r, "max_gap_ms") for r in rr if fv(r, "n") > 0]
        out[topic] = dict(rate_hz=stats(rate), max_gap_ms=stats(gap))
    tr = [fv(r, "delta_ms") for r in rows(os.path.join(res, "hil_truth_rx.csv")) if flight[0] <= fv(r, "rx_box") <= flight[1]]
    if tr:
        lo = sorted(tr)[0]
        out["truth_udp_one_way_minus_min_ms"] = stats([x - lo for x in tr])
    pg = [fv(r, "rtt_ms") for r in rows(os.path.join(res, "hil_ping.csv")) if flight[0] <= fv(r, "box") <= flight[1]]
    out["ping_rtt_ms"] = stats(pg)
    return out


def restarts(res, offset):
    """Each node killed in flight (hil_kills.jsonl): when /navera/position and the autopilot's
    GPS came back, and what the autopilot said meanwhile."""
    kills = [json.loads(x) for x in open(os.path.join(res, "hil_kills.jsonl"))] \
        if os.path.exists(os.path.join(res, "hil_kills.jsonl")) else []
    pos = sorted(fv(r, "rx_box") for r in rows(os.path.join(res, "hil_pos.csv")) if r["valid"] == "1")
    gps = [(fv(r, "wall"), r["fix_type"]) for r in rows(os.path.join(res, "sitl_gps.csv"))]
    ev = [json.loads(x) for x in open(os.path.join(res, "sitl_events.jsonl"))] \
        if os.path.exists(os.path.join(res, "sitl_events.jsonl")) else []
    t0 = json.load(open(os.path.join(res, "hil_t0.json")))["t0_pc"] if os.path.exists(os.path.join(res, "hil_t0.json")) else 0
    out = []
    for k in kills:
        tk = float(k["box"])
        before = [p for p in pos if p < tk]
        after = [p for p in pos if p > tk + 0.05]
        gap_pos = (after[0] - before[-1]) if before and after else None
        back_pos = (after[0] - tk) if after else None
        tk_pc = tk + offset
        bad = [w for w, ft in gps if w > tk_pc and ft not in ("3", "4", "5", "6")]
        good_after = [w for w, ft in gps if w > tk_pc and ft in ("3", "4", "5", "6")]
        ap_lost = None
        if bad:
            first_bad = bad[0]
            back = [w for w in good_after if w > first_bad]
            ap_lost = dict(lost_after_s=round(first_bad - tk_pc, 1), back_after_s=round(back[0] - tk_pc, 1) if back else None)
        texts = [e.get("text") or f"mode {e.get('mode')}" for e in ev
                 if e.get("kind") in ("text", "mode") and tk_pc - t0 <= e["t"] <= tk_pc - t0 + 60]
        out.append(dict(unit=k["unit"], t_flight=round(tk_pc - t0, 1), position_back_after_s=round(back_pos, 1) if back_pos else None,
                        position_gap_s=round(gap_pos, 1) if gap_pos else None,
                        systemd_restarted=k.get("restarted"), autopilot_gps=ap_lost, autopilot_said=texts[:8]))
    return out


def report(s, base):
    a = s["after_cut"]
    f3 = lambda d: "/".join("-" if not d or d.get(k) is None else f"{d[k]:.1f}" for k in ("median", "p90", "max"))  # noqa: E731
    lines = ["| metric | HIL (real box) | container (baseline) |", "|---|---|---|"]
    b = (base or {}).get("after_cut", {})
    for label, hv, bv in (
            ("matched % after the cut", a["accepted_pct"], b.get("accepted_pct")),
            ("fix error vs stamp med/p90/max m", f3(a["fix_err_stamp_m"]), f3(b.get("fix_err_stamp_m"))),
            ("fix error vs exposure med/p90/max m", f3(a["fix_err_exposure_m"]), f3(b.get("fix_err_exposure_m"))),
            ("wrong fixes (> 50 m)", a["wrong_fixes"], b.get("wrong_fixes")),
            ("output error med/p90/max m", f3(a["output_err_m"]), f3(b.get("output_err_m"))),
            ("autopilot EKF error med/p90/max m", f3(s.get("autopilot_ekf_err_after_cut_m")),
             f3((base or {}).get("autopilot_ekf_err_after_cut_m"))),
            ("ms/frame (frame_meta -> frame_done) med/p90/max", f3(s["ms_per_frame"]), f3((base or {}).get("ms_per_frame"))),
            ("mission", (s.get("mission") or {}).get("completed"), ((base or {}).get("mission") or {}).get("completed"))):
        lines.append(f"| {label} | {hv} | {bv} |")
    L = s.get("hil", {}).get("latency", {})
    lines += ["", "| latency stage (after the cut, measured day fixes) | median | p90 | max |", "|---|---|---|---|"]
    for k, v in L.items():
        if isinstance(v, dict) and v.get("n"):
            lines.append(f"| {k} | {v['median']} | {v['p90']} | {v['max']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("results")
    ap.add_argument("--baseline", default=os.path.expanduser("~/.navera_sim/isaac/campaign/c3_base"))
    a = ap.parse_args()
    res = os.path.expanduser(a.results)
    t0j = json.load(open(os.path.join(res, "hil_t0.json")))
    offset, t0 = float(t0j["pc_offset_s"]), float(t0j["t0_pc"])
    cut = float(open(os.path.join(res, "gps_cut")).read()) if os.path.exists(os.path.join(res, "gps_cut")) else 1e9
    truth = Truth(os.path.join(res, "truth.csv"))
    frames = join_exposure(res, offset, t0, truth)
    s = summarise(res, cut)
    tr = truth.t
    flight = (t0 + (tr[0] if tr else 0) - offset, t0 + (tr[-1] if tr else 1e12) - offset)   # box clock
    s["hil"] = dict(pc_offset_s=offset, latency=latency(res, frames, offset, t0, cut),
                    system=system(res, flight), jitter=jitter(res, flight, t0 + cut - offset),
                    restarts=restarts(res, offset), frames_joined=len(frames))
    base = None
    for n in ("summary_flight.json", "summary.json"):
        p = os.path.join(a.baseline, n)
        if os.path.exists(p):
            base = json.load(open(p))
            break
    s["baseline"] = dict(dir=a.baseline, summary={k: base.get(k) for k in ("after_cut", "autopilot_ekf_err_after_cut_m",
                                                                         "ms_per_frame", "mission")} if base else None)
    json.dump(s, open(os.path.join(res, "hil_summary.json"), "w"), indent=1)
    open(os.path.join(res, "hil_report.md"), "w").write(report(s, base))
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
