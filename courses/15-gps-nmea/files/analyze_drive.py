"""Lesson 15 — analyse the Sousse drive with YOUR functions, write results.json and 2 plots.

    python3 analyze_drive.py
    python3 analyze_drive.py other.nmea other_truth.csv

Uses nmea_tools.py (TODO 1-6), dop.py (TODO 7-8), gps_filter.py (TODO 9-11) and the two
functions below (TODO 12-13). Everything else is ready.
"""
import csv
import json
import math
import sys
import warnings

import numpy as np

import dop
import gps_filter as gf
import nmea_tools as nt

LOG = "/data/academy/15-gps-nmea/sousse_drive.nmea"
TRUTH = "/data/academy/15-gps-nmea/truth.csv"


# TODO 12: estimate the UERE (user equivalent range error, metres) from horizontal errors.
#   Course: section 6, "Estimating UERE from data".
#   err_h (horizontal errors, m) and hdop are lists (or arrays) of the same length.
#   Return a float (metres).
def estimate_uere(err_h, hdop):
    return None  # TODO 12: replace this line with your code


# TODO 13: the longest interval WITHOUT a usable fix.
#   times = sorted list of the UTC times (seconds) of the accepted fixes.
#   Return (gap_s, t_before, t_after): the largest difference between two CONSECUTIVE
#   times, the time of the last fix before it and of the first fix after it.
#   With fewer than 2 times return (0.0, None, None).
def longest_gap(times):
    return None  # TODO 13: replace this line with your code


# ---- you don't need to change anything below this line ----


def hms(t):
    """seconds since midnight -> 'hhmmss'."""
    t = int(round(t))
    return f"{t // 3600:02d}{t % 3600 // 60:02d}{t % 60:02d}"


def group_epochs(lines):
    """Group the VALID sentences into epochs (one per second): {'time', 'gga', 'rmc', 'gsa', 'gsv'}.
    A new epoch starts with a GGA/RMC of a new time, or a second GSA in the same epoch
    (when the GGA and RMC of a second were both damaged)."""
    epochs, cur = [], None
    for ln in lines:
        typ = nt.sentence_type(ln)
        if typ is None:
            continue
        f = nt.fields(ln)
        t = f[1] if typ in ("GGA", "RMC") else None
        if cur is None or (t is not None and cur["time"] not in (None, t)) or \
                (typ == "GSA" and cur["gsa"] is not None):
            cur = {"time": t, "gga": None, "rmc": None, "gsa": None, "gsv": []}
            epochs.append(cur)
        if t is not None:
            cur["time"] = t
        if typ == "GGA":
            cur["gga"] = ln
        elif typ == "RMC":
            cur["rmc"] = ln
        elif typ == "GSA":
            cur["gsa"] = ln
        elif typ == "GSV":
            cur["gsv"].append(ln)
    return epochs


def read_truth(path):
    with open(path) as f:
        return {row["utc"][:6]: (float(row["lat"]), float(row["lon"]), float(row["alt_msl"]))
                for row in csv.DictReader(f)}


def stop(msg):
    sys.exit("Not ready yet: " + msg)


def main(log, truth_path):
    lines = nt.read_log(log)
    valid = [nt.is_valid(ln) for ln in lines]
    if None in valid or not any(valid):
        stop("is_valid() (TODO 1-2) returns None or refuses everything.")
    rejected = [(i + 1, ln) for i, (ln, ok) in enumerate(zip(lines, valid)) if not ok]
    ggas = [nt.parse_gga(ln) for ln in lines]
    if not any(ggas):
        stop("parse_gga() (TODO 3-4) returns None for every line.")
    ggas = [g for g in ggas if g]
    qual = {}
    for g in ggas:
        qual[g["quality"]] = qual.get(g["quality"], 0) + 1

    # --- 1. DOP: recompute from GSV (az/el) + GSA (PRNs used) and compare with the receiver
    epochs = group_epochs(lines)
    if nt.parse_gsa(epochs[20]["gsa"]) is None or nt.parse_gsv(epochs[20]["gsv"][0]) is None:
        stop("parse_gsa() / parse_gsv() (TODO 5-6) return None.")
    dop_err, n_dop, dop_rows = [], 0, []
    for ep in epochs:
        gsa = nt.parse_gsa(ep["gsa"]) if ep["gsa"] else None
        if not gsa or gsa["mode"] != 3:
            continue
        sky, n_msgs = {}, set()
        for s in ep["gsv"]:
            v = nt.parse_gsv(s)
            n_msgs.add(v["msg"])
            for prn, el, az, snr in v["sats"]:
                sky[prn] = (az, el)
        if not ep["gsv"] or len(n_msgs) != nt.parse_gsv(ep["gsv"][0])["n_msgs"]:
            continue                              # a GSV part was lost: skip this second
        if any(p not in sky or None in sky[p] for p in gsa["prns"]):
            continue
        az = [sky[p][0] for p in gsa["prns"]]
        el = [sky[p][1] for p in gsa["prns"]]
        d = dop.dops(az, el)
        if d is None:
            stop("dops() (TODO 7-8) returns None.")
        errs = [abs(d["PDOP"] - gsa["pdop"]), abs(d["HDOP"] - gsa["hdop"]), abs(d["VDOP"] - gsa["vdop"])]
        g = nt.parse_gga(ep["gga"]) if ep["gga"] else None
        if g and g["hdop"] is not None:
            errs.append(abs(d["HDOP"] - g["hdop"]))
        dop_err.append(max(errs))
        n_dop += 1
        dop_rows.append((nt.utc_seconds(ep["time"]) if ep["time"] else None, d, len(gsa["prns"])))

    # --- 2. NAVERA's decision + the jump gate
    decisions = [gf.navera_decision(g) for g in ggas]
    if any(d is None for d in decisions):
        stop("navera_decision() (TODO 9) returns None.")
    reasons = {}
    for ok, why in decisions:
        if not ok:
            reasons[why] = reasons.get(why, 0) + 1
    if gf.navera_covariance(1.0) is None:
        stop("navera_covariance() (TODO 10) returns None.")
    accepted, jumps, prev, prev_t = [], [], None, None
    for g, (ok, why) in zip(ggas, decisions):
        if not ok:
            continue
        t = nt.utc_seconds(g["time"])
        cur = (g["lat"], g["lon"])
        slack = 3.0 * gf.UERE_M * (g["hdop"] if g["hdop"] else 1.0)       # 3 sigma of this fix
        gate = gf.jump_ok(prev, cur, None if prev_t is None else t - prev_t, slack)
        if gate is None:
            stop("jump_ok() (TODO 11) returns None.")
        if not gate:
            jumps.append(g["time"][:6])
            continue
        accepted.append(g)
        prev, prev_t = cur, t
    times = [nt.utc_seconds(g["time"]) for g in accepted]
    gap = longest_gap(times)
    if gap is None:
        stop("longest_gap() (TODO 13) returns None.")

    # --- 3. Accuracy against the truth (the log is synthetic: we know where the car was)
    truth = read_truth(truth_path)
    err_h, err_v, hd, sig_navera = [], [], [], []
    for g in accepted:
        tl = truth.get(g["time"][:6])
        if tl is None or g["hdop"] is None:
            continue
        de = math.radians(g["lon"] - tl[1]) * 6371000.0 * math.cos(math.radians(tl[0]))
        dn = math.radians(g["lat"] - tl[0]) * 6371000.0
        err_h.append(math.hypot(de, dn))
        err_v.append(g["alt_msl"] - tl[2])
        hd.append(g["hdop"])
        sig_navera.append(math.sqrt(gf.navera_covariance(g["hdop"])[0]))
    uere = estimate_uere(err_h, hd)
    if uere is None:
        stop("estimate_uere() (TODO 12) returns None.")
    err_h, hd = np.array(err_h), np.array(hd)
    within_2drms = float(np.mean(err_h <= 2 * uere * hd))
    within_navera_1s = float(np.mean(err_h <= np.array(sig_navera)))
    length = sum(nt.haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(accepted, accepted[1:]))

    res = {
        "lines_total": len(lines),
        "lines_rejected": len(rejected),
        "gga_valid": len(ggas),
        "gga_by_quality": {str(k): v for k, v in sorted(qual.items(), key=lambda x: str(x[0]))},
        "navera_valid": sum(1 for ok, _ in decisions if ok),
        "navera_invalid_reasons": reasons,
        "jump_rejected_utc": jumps,
        "fixes_accepted": len(accepted),
        "outage_s": round(gap[0], 1),
        "outage_from_utc": hms(gap[1]) if gap[1] is not None else None,
        "outage_to_utc": hms(gap[2]) if gap[2] is not None else None,
        "dop_epochs_compared": n_dop,
        "dop_max_abs_diff": round(max(dop_err), 4) if dop_err else None,
        "hdop_median": round(float(np.median(hd)), 2),
        "hdop_max": round(float(np.max(hd)), 2),
        "frac_hdop_over_5": round(float(np.mean(hd > 5)), 4),
        "horiz_err_median_m": round(float(np.median(err_h)), 2),
        "horiz_err_p95_m": round(float(np.percentile(err_h, 95)), 2),
        "vert_err_rms_m": round(float(np.sqrt(np.mean(np.square(err_v)))), 2),
        "uere_est_m": round(uere, 2),
        "frac_within_2drms": round(within_2drms, 4),
        "frac_within_navera_sigma": round(within_navera_1s, 4),
        "track_length_m": round(length, 1),
    }
    with open("results.json", "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)

    print(f"{len(lines)} lines, {len(rejected)} rejected by is_valid:")
    for no, ln in rejected:
        print(f"   line {no:5d}: {ln[:70]!r}")
    print(f"GGA by quality: {res['gga_by_quality']}")
    print(f"NAVERA decision: {res['navera_valid']} valid; invalid: {reasons}")
    print(f"jump gate ({gf.V_MAX_MPS:.0f} m/s + 3 sigma) rejected: {jumps}")
    print(f"accepted fixes: {len(accepted)};  longest gap {gap[0]:.0f} s "
          f"({res['outage_from_utc']} -> {res['outage_to_utc']} UTC)")
    print(f"DOP recomputed on {n_dop} epochs, largest difference with the receiver: {res['dop_max_abs_diff']}")
    print(f"HDOP median {res['hdop_median']}, max {res['hdop_max']}, > 5 on {100 * res['frac_hdop_over_5']:.1f} % of fixes")
    print(f"horizontal error: median {res['horiz_err_median_m']} m, 95 % {res['horiz_err_p95_m']} m;"
          f" vertical RMS {res['vert_err_rms_m']} m")
    print(f"UERE estimated: {uere:.2f} m;  within 2DRMS: {100 * within_2drms:.1f} %;"
          f"  within NAVERA's 1-sigma radius: {100 * within_navera_1s:.1f} %")
    print(f"track length (accepted fixes): {length:.0f} m")
    print("wrote results.json")
    plots(accepted, dop_rows, jumps, ggas, gap)


def plots(accepted, dop_rows, jumps, ggas, gap):
    import matplotlib
    matplotlib.use("Agg")
    warnings.filterwarnings("ignore")
    import matplotlib.pyplot as plt
    lat0 = accepted[0]["lat"]
    k = math.cos(math.radians(lat0))
    fig, ax = plt.subplots(figsize=(7, 7))
    lon = [g["lon"] for g in accepted]
    lat = [g["lat"] for g in accepted]
    h = [min(g["hdop"], 6) for g in accepted]
    sc = ax.scatter(lon, lat, c=h, s=6, cmap="viridis_r", vmin=0.5, vmax=6)
    fig.colorbar(sc, ax=ax, label="HDOP (clipped at 6)")
    q6 = [g for g in ggas if g["quality"] == 6 and g["lat"] is not None]
    if q6:
        ax.scatter([g["lon"] for g in q6], [g["lat"] for g in q6], s=18, c="red", label="quality 6 (refused)")
    if gap[1] is not None:
        a = next(g for g in accepted if nt.utc_seconds(g["time"]) == gap[1])
        ax.annotate(f"longest gap {gap[0]:.0f} s", (a["lon"], a["lat"]), xytext=(15, -25),
                    textcoords="offset points", arrowprops={"arrowstyle": "->"})
    ax.plot(lon[0], lat[0], "k*", ms=12, label="start (port of Sousse)")
    ax.plot(lon[-1], lat[-1], "ks", ms=8, label="end (Ribat of Monastir)")
    ax.set_aspect(1 / k)
    ax.set_xlabel("longitude (deg)")
    ax.set_ylabel("latitude (deg)")
    ax.set_title(f"Synthetic drive, {len(accepted)} accepted fixes")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("drive.png", dpi=100)
    plt.close(fig)

    t0 = min(r[0] for r in dop_rows if r[0] is not None)
    rows = [r for r in dop_rows if r[0] is not None]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    tt = [r[0] - t0 for r in rows]
    for key, col in (("PDOP", "tab:orange"), ("HDOP", "tab:blue"), ("VDOP", "tab:green")):
        a1.plot(tt, [r[1][key] for r in rows], ".", ms=2, c=col, label=key)
    a1.set_yscale("log")
    a1.set_ylabel("DOP (log scale)")
    a1.legend(fontsize=8, ncol=3)
    a1.grid(alpha=0.3)
    a2.plot(tt, [r[2] for r in rows], ".", ms=2, c="k")
    a2.set_ylabel("satellites used")
    a2.set_xlabel("time since first fix (s)")
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("dop_timeline.png", dpi=100)
    plt.close(fig)
    print("saved drive.png and dop_timeline.png — click them in the file list")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else LOG, sys.argv[2] if len(sys.argv) > 2 else TRUTH)
