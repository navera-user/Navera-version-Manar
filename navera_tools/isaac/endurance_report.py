#!/usr/bin/env python3
"""Endurance numbers of one long closed-loop Isaac Sim run, block by block (SIMULATION tooling).

    python3 navera_tools/isaac/endurance_report.py ~/navera_results/<run> [--block-min 15]

Reads isaac_link's record (position.csv, day.csv, events.jsonl, ekf.csv, frames.jsonl),
sitl_demo's (sitl_flown.json, sitl_events.jsonl) and resource_monitor.sh's resources.csv, and
writes into the run directory:
  endurance.json         per block after the GPS cut: fix error at the stated time and at the
                         true exposure (median / p90 / max), matched %, wrong fixes (> 50 m at
                         exposure), outputs beyond 3 sigma, err / sigma, autopilot EKF error, what
                         NAVERA carries (sigma calibration, latency estimate, heading offset of
                         the matches vs the truth, matched altitude / truth), resources
  error_vs_time.png      errors, matched %, sigma calibration, resources against flight time
  ENDURANCE.md           the short summary
"""
import argparse
import bisect
import csv
import json
import math
import os

WRONG_M = 50.0
NOT_A_MATCH = ("dead_reckon", "gps", "gps_active", "unusable", "none")


def q(v, p):
    v = sorted(x for x in v if x is not None and math.isfinite(x))
    return round(v[min(len(v) - 1, int(p * len(v)))], 2) if v else None


def st(v):
    v = [x for x in v if x is not None and math.isfinite(x)]
    return dict(n=len(v), median=q(v, 0.5), p90=q(v, 0.9), max=round(max(v), 1) if v else None)


def fnum(r, k):
    x = r.get(k)
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def load(res):
    # (\r stripped: nvidia-smi.exe ends its lines with CR LF)
    rd = lambda n: (list(csv.DictReader(open(os.path.join(res, n), newline="").read().replace("\r", "").splitlines()))  # noqa: E731
                    if os.path.exists(os.path.join(res, n)) else [])
    ev = []
    if os.path.exists(os.path.join(res, "events.jsonl")):
        for line in open(os.path.join(res, "events.jsonl")):
            try:
                ev.append(json.loads(line))
            except ValueError:
                pass
    fr = []
    if os.path.exists(os.path.join(res, "frames.jsonl")):
        fr = [json.loads(line) for line in open(os.path.join(res, "frames.jsonl")) if line.strip()]
    return rd("position.csv"), rd("day.csv"), ev, rd("ekf.csv"), fr, rd("resources.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--block-min", type=float, default=15.0)
    a = ap.parse_args()
    res = os.path.expanduser(a.results)
    pos, day, ev, ekf, fr, rsc = load(res)
    cut = float(open(os.path.join(res, "gps_cut")).read()) if os.path.exists(os.path.join(res, "gps_cut")) else 60.0
    flown = json.load(open(os.path.join(res, "sitl_flown.json"))) if os.path.exists(
        os.path.join(res, "sitl_flown.json")) else {}
    t_end = max(r["t"] for r in fr) + 3.0 if fr else (fnum(pos[-1], "t") if pos else float("inf"))
    rtl = flown.get("rtl_at") or t_end
    blk = 60.0 * a.block_min
    # truth heading (Isaac's frames) for the heading carried by the matches
    ft = [r["t"] for r in fr]
    fh = [r.get("heading", float("nan")) for r in fr]

    def truth_hdg(t):
        if not ft or not math.isfinite(t):
            return float("nan")
        i = min(max(bisect.bisect_left(ft, t), 0), len(ft) - 1)
        return fh[i]

    # the day pipeline's answers: frame_id -> (status), day.csv frame -> exposure
    exp_of = {int(fnum(r, "frame")): fnum(r, "t_exposure") for r in day if math.isfinite(fnum(r, "frame"))}
    stat = [(e["t"], e["day_status"]) for e in ev if "frame_id" in e.get("day_status", {})]
    allstat = [(e["t"], e["day_status"]) for e in ev if "day_status" in e]

    def phase_of(t):
        if t < cut:
            return None
        return int((t - cut) // blk)

    blocks = {}

    def B(k):
        return blocks.setdefault(k, dict(fix_s=[], fix_e=[], frames=0, acc=0, out=[], beyond=0, beyond1=0, ratio=[],
                                         ekf=[], sig_out=[], sigcal=None, lat=None, hdg_off=[], alt_ratio=[],
                                         sources={}, wrong=0, rtl=False))
    for r in day:
        t = fnum(r, "t")
        k = phase_of(t)
        if k is None or t > t_end or r["mode"] != "measured" or r["valid"] != "1":
            continue
        b = B(k)
        b["fix_s"].append(fnum(r, "err_m"))
        b["fix_e"].append(fnum(r, "err_frame_m"))
        if fnum(r, "err_frame_m") > WRONG_M:
            b["wrong"] += 1
    for t, s in stat:
        k = phase_of(t)
        if k is None or t > t_end or s.get("source") in ("gps", "gps_active"):
            continue
        b = B(k)
        b["frames"] += 1
        b["sources"][s.get("source", "?")] = b["sources"].get(s.get("source", "?"), 0) + 1
        if s.get("success") and s.get("source") not in NOT_A_MATCH:
            b["acc"] += 1
            te = exp_of.get(int(s["frame_id"]), float("nan"))
            if s.get("rotation_deg") is not None and math.isfinite(truth_hdg(te)):
                b["hdg_off"].append(wrap(float(s["rotation_deg"]) - truth_hdg(te)))
    for t, s in allstat:
        k = phase_of(t)
        if k is None or t > t_end:
            continue
        b = B(k)
        if isinstance(s.get("sigma_cal"), dict):
            b["sigcal"] = s["sigma_cal"]
        if isinstance(s.get("latency"), dict):
            b["lat"] = s["latency"]
    for r in pos:
        t = fnum(r, "t")
        k = phase_of(t)
        if k is None or t > t_end or r["valid"] != "1":
            continue
        b = B(k)
        e, sg = fnum(r, "err_m"), fnum(r, "sigma_m")
        b["out"].append(e)
        if sg > 0:
            b["sig_out"].append(sg)
            b["ratio"].append(e / sg)
            b["beyond"] += e > 3 * sg
            b["beyond1"] += e > sg
        b["rtl"] = b["rtl"] or t >= rtl
    for r in ekf:
        t = fnum(r, "t")
        k = phase_of(t)
        if k is not None and t <= t_end:
            B(k)["ekf"].append(fnum(r, "err_m"))
    # resources per block (t_s of resources.csv counts from the monitor's start: map by wall clock)
    rows = []
    for k in sorted(blocks):
        b = blocks[k]
        ho = b["hdg_off"]
        hmed = None
        if ho:      # circular median-ish: mean direction
            sx, sy = sum(math.cos(math.radians(x)) for x in ho), sum(math.sin(math.radians(x)) for x in ho)
            hmed = round(math.degrees(math.atan2(sy, sx)), 1)
        rows.append(dict(
            block=k, t_from_cut_min=[round(k * a.block_min, 1), round((k + 1) * a.block_min, 1)],
            includes_rtl=b["rtl"],
            frames=b["frames"], matched=b["acc"], matched_pct=round(100.0 * b["acc"] / b["frames"], 1) if b["frames"] else None,
            frame_sources=b["sources"],
            fix_err_stamp_m=st(b["fix_s"]), fix_err_exposure_m=st(b["fix_e"]), wrong_fixes=b["wrong"],
            output_err_m=st(b["out"]), output_sigma_m=st(b["sig_out"]),
            output_beyond_3sigma=b["beyond"], output_beyond_1sigma_pct=round(100.0 * b["beyond1"] / len(b["ratio"]), 1) if b["ratio"] else None,
            output_err_over_sigma=st(b["ratio"]), outputs=len(b["out"]),
            ekf_err_m=st(b["ekf"]),
            sigma_cal=b["sigcal"], latency=({k2: b["lat"].get(k2) for k2 in ("estimate_s", "applied_s", "samples", "stable", "frozen")}
                                            if b["lat"] else None),
            match_heading_offset_deg=dict(mean=hmed, n=len(ho))))
    # resources: first / last / max of every column, and the trend per hour (least squares)
    res_sum = {}
    if rsc:
        ss = os.path.join(res, "sitl_session.json")
        t0w = json.load(open(ss))["t0_wall"] if os.path.exists(ss) else None
        tt = [fnum(r, "epoch") - t0w if t0w else fnum(r, "t_s") for r in rsc]
        # the GPS-denied flight only (start-up and the end of the run are not a trend)
        keep = [(t, r) for t, r in zip(tt, rsc) if cut <= t <= min(rtl, t_end)]
        tt, rsc_f = [k[0] for k in keep], [k[1] for k in keep]
        for col in (rsc[0].keys() if rsc_f else []):
            if col in ("wall", "epoch", "t_s"):
                continue
            pts = [(t, fnum(r, col)) for t, r in zip(tt, rsc_f) if math.isfinite(fnum(r, col))]
            if len(pts) < 3:
                continue
            n = len(pts)
            mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
            sxx = sum((p[0] - mx) ** 2 for p in pts)
            slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx if sxx else 0.0
            # first / last 10 minutes medians (not one sample)
            first = [p[1] for p in pts if p[0] <= pts[0][0] + 600]
            last = [p[1] for p in pts if p[0] >= pts[-1][0] - 600]
            res_sum[col] = dict(first10min=q(first, 0.5), last10min=q(last, 0.5), max=max(p[1] for p in pts),
                                per_hour=round(slope * 3600.0, 2))
    after = dict(
        fix_err_stamp_m=st([fnum(r, "err_m") for r in day if cut <= fnum(r, "t") <= t_end and r["mode"] == "measured" and r["valid"] == "1"]),
        fix_err_exposure_m=st([fnum(r, "err_frame_m") for r in day if cut <= fnum(r, "t") <= t_end and r["mode"] == "measured" and r["valid"] == "1"]),
        wrong_fixes=sum(r["wrong_fixes"] for r in rows), beyond_3sigma=sum(r["output_beyond_3sigma"] for r in rows),
        outputs=sum(r["outputs"] for r in rows),
        matched=sum(r["matched"] for r in rows), frames=sum(r["frames"] for r in rows),
        ekf_err_m=st([fnum(r, "err_m") for r in ekf if cut <= fnum(r, "t") <= t_end]))
    texts = []
    if os.path.exists(os.path.join(res, "sitl_events.jsonl")):
        texts = [json.loads(line) for line in open(os.path.join(res, "sitl_events.jsonl")) if line.strip()]
    summ = json.load(open(os.path.join(res, "summary.json"))) if os.path.exists(os.path.join(res, "summary.json")) else {}
    out = dict(gps_cut_s=cut, flight_end_s=round(t_end, 1) if math.isfinite(t_end) else None,
               gps_denied_min=round((min(t_end, rtl) - cut) / 60.0, 1) if math.isfinite(min(t_end, rtl)) else None,
               flown={k: v for k, v in flown.items() if k != "wps"}, mission=summ.get("mission"),
               after_cut=after, blocks=rows, resources=res_sum,
               autopilot_failsafes=[e.get("text") for e in texts if "ailsafe" in str(e.get("text", ""))][:20],
               autopilot_modes=[(e["t"], e.get("mode")) for e in texts if e.get("kind") == "mode"][:40])
    json.dump(out, open(os.path.join(res, "endurance.json"), "w"), indent=1)
    plot(res, cut, t_end, day, pos, ekf, rows, rsc, a.block_min, rtl)
    write_md(res, out, a.block_min)
    print(json.dumps(dict(after_cut=after, gps_denied_min=out["gps_denied_min"]), indent=1))


def plot(res, cut, t_end, day, pos, ekf, rows, rsc, block_min, rtl):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6", "#e87ba4"]
    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                         "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                         "font.size": 9, "axes.titlesize": 10, "axes.titlecolor": INK,
                         "axes.spines.top": False, "axes.spines.right": False})
    m = lambda t: (t - cut) / 60.0  # noqa: E731
    fig, ax = plt.subplots(5, 1, figsize=(12, 15), sharex=True, gridspec_kw=dict(height_ratios=[3, 2, 1.4, 1.6, 1.6]))
    meas = [r for r in day if r["mode"] == "measured" and r["valid"] == "1" and cut <= fnum(r, "t") <= t_end]

    def rolling(ts, vs, w=300.0, step=30.0):
        """Median over a sliding w-s window, every step s."""
        pts = sorted((t, v) for t, v in zip(ts, vs) if math.isfinite(v))
        if not pts:
            return [], []
        keys = [p[0] for p in pts]
        out_t, out_v, t = [], [], pts[0][0]
        while t <= pts[-1][0]:
            win = sorted(p[1] for p in pts[bisect.bisect_left(keys, t - w / 2):bisect.bisect_right(keys, t + w / 2)])
            if win:
                out_t.append(t)
                out_v.append(win[len(win) // 2])
            t += step
        return out_t, out_v
    ts = [m(fnum(r, "t")) for r in meas]
    for key, c, lab in (("err_m", C[0], "fix error at stated time"), ("err_frame_m", C[1], "fix error at exposure")):
        vs = [fnum(r, key) for r in meas]
        ax[0].scatter(ts, vs, s=3, color=c, alpha=0.25, linewidths=0)
        rt, rv = rolling([fnum(r, "t") for r in meas], vs)
        ax[0].plot([m(t) for t in rt], rv, color=c, lw=2, label=lab + " (5-min rolling median)")
    po = [r for r in pos if r["valid"] == "1" and cut <= fnum(r, "t") <= t_end]
    pt = [fnum(r, "t") for r in po][::5]
    rt, rv = rolling(pt, [fnum(r, "err_m") for r in po][::5])
    ax[0].plot([m(t) for t in rt], rv, color=C[2], lw=2, label="NAVERA output error (rolling median)")
    rt, rv = rolling(pt, [3 * fnum(r, "sigma_m") for r in po][::5])
    ax[0].plot([m(t) for t in rt], rv, color=MUTED, lw=1.2, ls="--", label="3 x stated sigma (rolling median)")
    ax[0].axhline(WRONG_M, color="#e34948", lw=0.8, ls=":")
    ax[0].text(0, WRONG_M + 2, "wrong-fix threshold 50 m", color=MUTED, fontsize=8)
    ax[0].set_ylim(0, max(80, min(250, (q([fnum(r, "err_frame_m") for r in meas], 0.99) or 80) * 1.2)))
    ax[0].set_ylabel("m")
    ax[0].set_title("NAVERA position error vs time after the GPS cut (Isaac Sim closed loop, SIMULATION)")
    ax[0].legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    ek = [r for r in ekf if cut <= fnum(r, "t") <= t_end]
    ax[1].plot([m(fnum(r, "t")) for r in ek][::5], [fnum(r, "err_m") for r in ek][::5], color=C[4], lw=1)
    ax[1].set_ylabel("m")
    ax[1].set_title("Autopilot EKF position error (flies on NAVERA's GPS_INPUT only)")
    ax[1].set_ylim(0, max(60, (q([fnum(r, "err_m") for r in ek], 0.995) or 60) * 1.15))
    mid = [r["block"] * block_min + block_min / 2 for r in rows]
    ax[2].bar(mid, [r["matched_pct"] or 0 for r in rows], width=block_min * 0.9, color=C[0])
    for x, r in zip(mid, rows):
        ax[2].text(x, (r["matched_pct"] or 0) + 2, f"{r['matched_pct']}%  wrong {r['wrong_fixes']}  >3σ {r['output_beyond_3sigma']}",
                   ha="center", fontsize=7, color=INK)
    ax[2].set_ylim(0, 115)
    ax[2].set_ylabel("% frames")
    ax[2].set_title(f"Frames matched to the map, per {block_min:.0f}-min block (with wrong fixes and outputs beyond 3 sigma)")
    ax[3].plot(mid, [r["output_err_over_sigma"]["median"] for r in rows], "o-", color=C[2], lw=2, ms=5,
               label="output error / stated sigma (median)")
    ax[3].plot(mid, [r["output_err_over_sigma"]["p90"] for r in rows], "o--", color=C[2], lw=1, ms=4,
               label="output error / stated sigma (p90)")
    ax[3].plot(mid, [(r["sigma_cal"] or {}).get("factor") for r in rows], "s-", color=C[3], lw=2, ms=5,
               label="day sigma_cal factor (carried)")
    ho = [r["match_heading_offset_deg"]["mean"] for r in rows if r["match_heading_offset_deg"]["mean"] is not None]
    ax[3].set_title("Stated sigma vs the real error (ratio)" + (f"; match rotation - truth heading per block: "
                    f"{min(ho):+.1f} to {max(ho):+.1f} deg" if ho else ""))
    ax[3].legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    if rsc:
        # resources.csv: wall-clock epoch -> flight time (sitl_demo's t0)
        ss = os.path.join(res, "sitl_session.json")
        t0w = json.load(open(ss))["t0_wall"] if os.path.exists(ss) else None
        tr = [fnum(r, "epoch") - t0w if t0w else fnum(r, "t_s") for r in rsc]
        ax4 = ax[4]
        for col, c, lab in (("rss_day_mib", C[0], "day_subscriber RSS"), ("rss_estimator_mib", C[1], "estimator RSS"),
                            ("rss_link_mib", C[2], "isaac_link RSS (sim)"), ("gpu_mem_mib", C[4], "GPU memory (Isaac + NAVERA)"),
                            ("ctr_mem_mib", C[3], "container memory")):
            ax4.plot([m(t) for t in tr], [fnum(r, col) for r in rsc], color=c, lw=1.5, label=lab)
        ax4.set_ylabel("MiB")
        gt = [fnum(r, "gpu_temp_c") for r in rsc]
        ax4.set_title(f"Resources (MiB); GPU temperature {q(gt, 0.0)}-{max([x for x in gt if math.isfinite(x)] or [0])} °C")
        ax4.legend(loc="upper left", fontsize=8, frameon=False, ncol=3)
    ax[-1].set_xlabel("minutes after the GPS cut")
    for x in ax:
        x.axvline(m(rtl), color=MUTED, lw=0.8, ls="-.")
    ax[0].text(m(rtl), ax[0].get_ylim()[1] * 0.92, " RTL", color=MUTED, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(res, "error_vs_time.png"), dpi=110)


def write_md(res, o, block_min):
    L = []
    a = o["after_cut"]
    ms = o.get("mission") or {}
    L.append("# NAVERA endurance run — Isaac Sim closed loop (SIMULATION)\n")
    L.append(f"GPS cut at t = {o['gps_cut_s']:.0f} s; GPS-denied flight before RTL: **{o['gps_denied_min']} min**; "
             f"mission completed (back over home on vision): **{ms.get('completed')}**, "
             f"real distance from home at RTL arrival {ms.get('dist_from_home_at_rtl_arrival_m')} m.\n")
    L.append(f"After the cut: {a['matched']}/{a['frames']} frames matched; fix error at stated time "
             f"{a['fix_err_stamp_m']['median']} / {a['fix_err_stamp_m']['p90']} / {a['fix_err_stamp_m']['max']} m "
             f"(median / p90 / max), at exposure {a['fix_err_exposure_m']['median']} / {a['fix_err_exposure_m']['p90']} / "
             f"{a['fix_err_exposure_m']['max']} m; wrong fixes (> 50 m) {a['wrong_fixes']}; outputs beyond 3 sigma "
             f"{a['beyond_3sigma']}/{a['outputs']}; autopilot EKF error {a['ekf_err_m']['median']} / {a['ekf_err_m']['p90']} / "
             f"{a['ekf_err_m']['max']} m.\n")
    L.append(f"\n## Per {block_min:.0f}-minute block after the cut\n")
    L.append("| block (min) | matched % | fix err stamp med / p90 | at exposure med / p90 | wrong | >3σ / outputs | err/σ med | output err med / p90 | EKF err med / p90 / max | sigma_cal factor | match heading offset |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in o["blocks"]:
        f = lambda d: f"{d['median']} / {d['p90']}"  # noqa: E731
        sc = (r["sigma_cal"] or {}).get("factor")
        L.append(f"| {r['t_from_cut_min'][0]:.0f}-{r['t_from_cut_min'][1]:.0f}{' (RTL)' if r['includes_rtl'] else ''} | "
                 f"{r['matched_pct']} | {f(r['fix_err_stamp_m'])} | {f(r['fix_err_exposure_m'])} | {r['wrong_fixes']} | "
                 f"{r['output_beyond_3sigma']} / {r['outputs']} | {r['output_err_over_sigma']['median']} | {f(r['output_err_m'])} | "
                 f"{f(r['ekf_err_m'])} / {r['ekf_err_m']['max']} | {sc} | {r['match_heading_offset_deg']['mean']} |")
    L.append("\n## Resources during the GPS-denied flight (first 10 min -> last 10 min, max, linear trend per hour)\n")
    L.append("| quantity | first | last | max | per hour |")
    L.append("|---|---|---|---|---|")
    for k, v in o["resources"].items():
        L.append(f"| {k} | {v['first10min']} | {v['last10min']} | {v['max']} | {v['per_hour']} |")
    if o.get("autopilot_failsafes"):
        L.append("\nAutopilot failsafe messages: " + "; ".join(map(str, o["autopilot_failsafes"])))
    L.append("\n![error vs time](error_vs_time.png)\n")
    open(os.path.join(res, "ENDURANCE.md"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
