#!/usr/bin/env python3
"""analyse.py — lesson 27: ellipses, propagation, fusion, gating and filter consistency.

    python3 analyse.py        # prints the numbers, writes results.json, ellipse.png, track.png, nees.png

Data (/data/academy/27-uncertainty/, SIMULATED by make_dataset.py):
  static_fixes.csv  a receiver standing still on a surveyed point in Sousse harbour (error in metres)
  track.csv         a drone flying west-north-west from Monastir along the coast, truth + noisy fixes,
                    a 40 s gap (GPS jammed) and 6 outliers (wrong matches)
"""
import csv
import json
import math
import warnings

import numpy as np

warnings.filterwarnings("ignore", message="Unable to import Axes3D")   # harmless on this Jetson
import matplotlib                          # noqa: E402
matplotlib.use("Agg")                      # no window: we save PNG files
import matplotlib.pyplot as plt            # noqa: E402
from matplotlib.patches import Ellipse     # noqa: E402

from kalman import nees, run_filter                                     # noqa: E402
from uncertainty import (chi2_gate, chi2_threshold, error_ellipse, fuse,  # noqa: E402
                         mahalanobis2, polar_to_en, sample_cov)

DATA = "/data/academy/27-uncertainty"
GATE_P = 0.99                 # the probability of the chi-square gate
Q_FILTER = 0.3                # the process noise you give the filter (m^2/s^3)
Q_SWEEP = [0.003, 0.03, 0.3, 3.0, 30.0]


def load(name):
    with open(f"{DATA}/{name}") as f:
        return list(csv.DictReader(f))


def track_inputs():
    rows = load("track.csv")
    times = [float(r["t_s"]) for r in rows]
    zs = [None if r["z_e"] == "" else np.array([float(r["z_e"]), float(r["z_n"])]) for r in rows]
    truth = np.array([[float(r["true_e"]), float(r["true_n"])] for r in rows])
    outlier = [r["outlier"] == "1" for r in rows]
    return times, zs, truth, outlier, float(rows[0]["sigma_m"])


def track_stats(run, truth, zs):
    """RMSE (on the steps WITH a measurement: the 40 s gap is reported apart), max error, and the
    NEES of the position at every step."""
    est = np.array([x[:2] for x in run["x"]])
    err = est - truth
    dist = np.hypot(err[:, 0], err[:, 1])
    seen = np.array([z is not None for z in zs])
    n = [nees(e, P[:2, :2]) for e, P in zip(err, run["P"])]
    return float(np.sqrt(np.mean(dist[seen] ** 2))), float(dist[seen].max()), n


def missing():
    """The names of the functions that are not finished yet (they return None or raise an error)."""
    P = np.array([[4.0, 1.0], [1.0, 2.0]])
    tries = {"sample_cov (TODO 1)": lambda: sample_cov([[0.0, 0.0], [1.0, 2.0], [2.0, 1.0]]),
             "error_ellipse (TODO 2)": lambda: error_ellipse(P)[0],
             "chi2_threshold (TODO 3)": lambda: chi2_threshold(0.95, 2),
             "polar_to_en (TODO 4)": lambda: polar_to_en(100.0, 30.0, 1.0, 1.0)[1],
             "mahalanobis2 (TODO 5)": lambda: mahalanobis2([1.0, 1.0], P),
             "chi2_gate (TODO 5)": lambda: chi2_gate([1.0, 1.0], P),
             "fuse (TODO 6)": lambda: fuse([0.0, 0.0], P, [1.0, 1.0], P)[1],
             "nees (TODO 11)": lambda: nees(np.array([1.0, 1.0]), P),
             "run_filter (TODO 12)": lambda: run_filter([0.0, 1.0], [np.zeros(2), np.ones(2)], 5.0, 0.3)}
    out = []
    for name, f in tries.items():
        try:
            if f() is None:
                out.append(name)
        except Exception as e:          # e.g. run_filter() calling a kalman.py function not done yet
            out.append(f"{name}: raises {type(e).__name__}: {e}")
    return out


def main():
    todo = missing()
    if todo:
        print("Not finished yet — these return None or raise an error:\n  " + "\n  ".join(todo))
        print("Complete them (python3 uncertainty.py and python3 kalman.py to try them), then run me again.")
        return
    res = {}

    # ---- 1. A receiver standing still: covariance and error ellipse
    pts = np.array([[float(r["east_m"]), float(r["north_m"])] for r in load("static_fixes.csv")])
    P = sample_cov(pts)
    a, b, ang = error_ellipse(P, 1.0)
    d2 = [mahalanobis2(p - pts.mean(axis=0), P) for p in pts]
    res["static"] = dict(n=len(pts), cov=P.tolist(), a_m=a, b_m=b, angle_deg=ang,
                         navera_stated_sigma_m=math.sqrt(max(P[0, 0], P[1, 1])),   # what _stated_sigma() reads
                         share_1s=float(np.mean([d <= 1.0 for d in d2])),
                         share_95=float(np.mean([d <= chi2_threshold(0.95, 2) for d in d2])))

    # ---- 2. Propagation J P J^T: a coastal radar on a headland, checked by Monte Carlo
    en, Pp = polar_to_en(2000.0, 60.0, 5.0, 0.5)
    rng = np.random.default_rng(26)
    r_s = 2000.0 + 5.0 * rng.standard_normal(20000)
    b_s = np.radians(60.0 + 0.5 * rng.standard_normal(20000))
    mc = np.cov(np.vstack([r_s * np.sin(b_s), r_s * np.cos(b_s)]))
    res["polar"] = dict(en=en.tolist(), cov=Pp.tolist(), cov_monte_carlo=mc.tolist())

    # ---- 3. Fusion of the GPS position with a vision fix (gate first!)
    P_gps = P                                   # the ellipse measured above
    P_vis = np.diag([8.0 ** 2, 8.0 ** 2])       # vision states 8 m per axis
    fus = {}
    for name, xv in (("good", np.array([6.0, -3.0])), ("bad", np.array([40.0, 25.0]))):
        r = xv - np.zeros(2)
        ok = chi2_gate(r, P_gps + P_vis, GATE_P)
        # fuse only what the gate accepts; a refused fix leaves the GPS estimate as it is
        xf, Pf = fuse(np.zeros(2), P_gps, xv, P_vis) if ok else (np.zeros(2), P_gps)
        fus[name] = dict(d2=mahalanobis2(r, P_gps + P_vis), accepted=bool(ok), x=xf.tolist(), cov=Pf.tolist(),
                         ellipse=list(error_ellipse(Pf, 1.0)))
    res["fusion"] = fus

    # ---- 4. The Kalman filter on the track: with and without the gate
    times, zs, truth, outlier, sz = track_inputs()
    gated = run_filter(times, zs, sz, Q_FILTER, gate_p=GATE_P)
    raw = run_filter(times, zs, sz, Q_FILTER, gate_p=None)
    rmse_g, max_g, nees_g = track_stats(gated, truth, zs)
    rmse_u, max_u, nees_u = track_stats(raw, truth, zs)
    meas = [z is not None for z in zs]
    raw_err = [float(np.hypot(*(z - t))) for z, t, o in zip(zs, truth, outlier) if z is not None and not o]

    # TODO 14: count, from gated["accepted"] (False = refused by the gate) and `outlier`:
    #          caught = outliers refused,   false_alarms = good measurements refused
    caught = sum(1 for acc, o in zip(gated["accepted"], outlier) if o and acc is False)
    false_alarms = sum(1 for acc, o in zip(gated["accepted"], outlier) if not o and acc is False)

    # TODO 15: the mean NEES of the gated filter and its 95 % band for N independent steps:
    #          N * mean ~ chi-square with 2N dof  ->  band = [chi2.ppf(0.025, 2N) / N, chi2.ppf(0.975, 2N) / N]
    N = len(nees_g)
    mean_nees = float(np.mean(nees_g))
    band = [chi2_threshold(0.025, 2 * N) / N, chi2_threshold(0.975, 2 * N) / N]

    gap = [i for i, t in enumerate(times) if zs[i] is None]
    sig_gap = [math.sqrt(max(gated["P"][i][0, 0], gated["P"][i][1, 1])) for i in gap]
    err_gap = [float(np.hypot(*(gated["x"][i][:2] - truth[i]))) for i in gap]
    res["track"] = dict(n=N, n_measurements=sum(meas), q=Q_FILTER, gate_p=GATE_P,
                        rmse_raw_fixes_m=float(np.sqrt(np.mean(np.square(raw_err)))),
                        gated=dict(rmse_m=rmse_g, max_err_m=max_g, mean_nees=mean_nees, caught=caught,
                                   false_alarms=false_alarms, outliers=sum(outlier)),
                        ungated=dict(rmse_m=rmse_u, max_err_m=max_u, mean_nees=float(np.mean(nees_u))),
                        nees_band_95=band, gap_max_sigma_m=max(sig_gap), gap_max_err_m=max(err_gap))
    sweep = []
    for q in Q_SWEEP:
        rm, _, nn = track_stats(run_filter(times, zs, sz, q, gate_p=GATE_P), truth, zs)
        sweep.append(dict(q=q, rmse_m=rm, mean_nees=float(np.mean(nn))))
    res["q_sweep"] = sweep

    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    plots(pts, P, times, zs, truth, outlier, gated, nees_g, band)

    s, t = res["static"], res["track"]
    print(f"static : {s['n']} fixes, 1-sigma ellipse a = {s['a_m']:.2f} m, b = {s['b_m']:.2f} m, "
          f"axis {s['angle_deg']:.1f} deg from east; NAVERA's _stated_sigma() would read {s['navera_stated_sigma_m']:.2f} m")
    print(f"         inside the 1-sigma ellipse {100 * s['share_1s']:.1f} % (theory 39.3 %), "
          f"inside the 95 % ellipse {100 * s['share_95']:.1f} %")
    print(f"radar  : sigma east {math.sqrt(Pp[0, 0]):.2f} m, north {math.sqrt(Pp[1, 1]):.2f} m "
          f"(Monte Carlo {math.sqrt(mc[0, 0]):.2f} / {math.sqrt(mc[1, 1]):.2f} m)")
    for k, v in fus.items():
        print(f"fusion : {k} vision fix, d2 = {v['d2']:.2f} -> {'ACCEPTED' if v['accepted'] else 'REFUSED'}, "
              f"fused ellipse {v['ellipse'][0]:.2f} x {v['ellipse'][1]:.2f} m")
    print(f"track  : raw fixes RMSE {t['rmse_raw_fixes_m']:.2f} m (outliers excluded)")
    print(f"         gated   RMSE {t['gated']['rmse_m']:.2f} m, max {t['gated']['max_err_m']:.1f} m, "
          f"outliers caught {caught}/{t['gated']['outliers']}, false alarms {false_alarms}")
    print(f"         ungated RMSE {t['ungated']['rmse_m']:.2f} m, max {t['ungated']['max_err_m']:.1f} m")
    print(f"         mean NEES {mean_nees:.2f} (95 % band {band[0]:.2f} .. {band[1]:.2f}); "
          f"ungated {t['ungated']['mean_nees']:.2f}")
    print(f"         during the 40 s gap: sigma grows to {t['gap_max_sigma_m']:.1f} m, error up to {t['gap_max_err_m']:.1f} m")
    print("q sweep: " + ",  ".join(f"q={w['q']:g}: RMSE {w['rmse_m']:.2f} m NEES {w['mean_nees']:.2f}" for w in sweep))
    print("saved results.json, ellipse.png, track.png, nees.png")


# ---- you don't need to change anything below this line (the pictures) ----

def plots(pts, P, times, zs, truth, outlier, run, nees_g, band):
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.scatter(pts[:, 0], pts[:, 1], s=7, color="#2563eb", alpha=0.55, label=f"fixes ({len(pts)})")
    for p, color in ((0.393, "#16a34a"), (0.95, "#d97706"), (0.99, "#dc2626")):
        k = math.sqrt(chi2_threshold(p, 2))
        a, b, ang = error_ellipse(P, k)
        ax.add_patch(Ellipse(pts.mean(axis=0), 2 * a, 2 * b, angle=ang, fill=False, color=color, lw=2,
                             label=f"{100 * p:.1f} % ellipse (k = {k:.2f})"))
    ax.plot(0, 0, "k+", markersize=16, mew=2, label="surveyed point")
    ax.set_aspect("equal")
    ax.set_xlim(-16, 16)
    ax.set_ylim(-16, 16)
    ax.grid(alpha=0.3)
    ax.set_xlabel("east error (m)")
    ax.set_ylabel("north error (m)")
    ax.set_title("Receiver standing still, Sousse harbour (simulated)")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig("ellipse.png", dpi=100)
    plt.close(fig)

    est = np.array([x[:2] for x in run["x"]])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(truth[:, 0], truth[:, 1], "k-", lw=1, label="truth")
    good = np.array([z for z, o in zip(zs, outlier) if z is not None and not o])
    bad = np.array([z for z, o in zip(zs, outlier) if z is not None and o])
    ax.scatter(good[:, 0], good[:, 1], s=5, color="#94a3b8", label="fixes")
    if len(bad):
        ax.scatter(bad[:, 0], bad[:, 1], s=40, marker="x", color="#dc2626", label="outliers")
    ax.plot(est[:, 0], est[:, 1], "-", color="#2563eb", lw=1.5, label="Kalman (gated)")
    for i in range(0, len(times), 20):
        a, b, ang = error_ellipse(run["P"][i][:2, :2], 3.0)
        ax.add_patch(Ellipse(est[i], 2 * a, 2 * b, angle=ang, fill=False, color="#2563eb", lw=0.8, alpha=0.7))
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_xlabel("east (m) from the start, near Monastir")
    ax.set_ylabel("north (m)")
    ax.set_title("Coastal flight from Monastir (simulated): 3-sigma ellipses every 20 s")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig("track.png", dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.semilogy(times, np.maximum(nees_g, 1e-3), ".", ms=3, color="#2563eb", label="NEES per step")
    ax.axhline(2.0, color="k", lw=1, label="expected mean = 2")
    ax.axhline(chi2_threshold(0.95, 2), color="#d97706", lw=1, ls="--", label="95 % of single steps below")
    ax.axhspan(band[0], band[1], color="#16a34a", alpha=0.25, label="95 % band of the MEAN")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("NEES (position)")
    ax.set_ylim(1e-2, 1e3)
    ax.legend(fontsize=8, loc="upper right", ncol=2)
    ax.set_title("Is the filter honest about its own error? (gated filter)")
    fig.tight_layout()
    fig.savefig("nees.png", dpi=100)
    plt.close(fig)


if __name__ == "__main__":
    main()
