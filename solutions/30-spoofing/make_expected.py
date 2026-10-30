#!/usr/bin/env python3
"""Teacher only — writes courses/30-spoofing/hidden/expected.json: the check's unseen inputs and the course
reference's answers on them, plus every lab number read back from the lab's own tools run on the reference.

    python3 solutions/30-spoofing/make_expected.py [--arbiter PATH]

The reference is the generated solution copy solutions/30-spoofing/navera_lite/ (run tools/lite_build.py
30-spoofing first). The lab numbers that involve the judge need mission 29's navera_lite/arbiter.py: taken from
solutions/_navera_lite/navera_lite/arbiter.py when it exists, else from --arbiter PATH (a stand-in).
RE-RUN THIS SCRIPT whenever mission 29's arbiter or spoof.py changes.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
COURSE = os.path.join(ACADEMY, "courses", "30-spoofing")
sys.path.insert(0, HERE)                                   # solutions/30-spoofing: the complete navera_lite copy
from navera_lite import spoof as S                         # noqa: E402
from navera_lite.estimate import Estimate                  # noqa: E402
from navera_lite.geo import enu_flat, offset               # noqa: E402
from navera_lite.settings import DEFAULTS                  # noqa: E402

import numpy as np                                         # noqa: E402


def cfg_for(vmax=30.0, **kw):
    c = dict(DEFAULTS, max_speed_mps=vmax)
    c.update(S.GUARD_DEFAULTS)
    c.update(kw)
    return c


def est_json(e):
    return {"source": e.source, "lat": e.lat, "lon": e.lon, "stamp_s": e.stamp_s, "cov": list(e.cov),
            "cov_type": e.cov_type, "valid": e.valid}


def cov(sig, b=0.0, sig_n=None):
    sn = sig if sig_n is None else sig_n
    return (sig * sig, b, 0.0, b, sn * sn, 0.0, 0.0, 0.0, 100.0)


# ------------------------------------------------------------------------------- TODO 1–5 unit inputs
def units():
    out = {}
    out["chi2"] = [[p, S.chi2_threshold_2d(p)] for p in (0.2, 0.025, 0.0037, 1e-5, 0.5)]
    cases = []
    base = (-33.9100, 18.4300)                             # near Cape Town harbour
    specs = [  # (gps E, N offset from ref, gps cov, ref cov, gps stamp, ref stamp, vmax)
        ((40.0, -25.0), cov(3.0), cov(15.0), 50.0, 50.0, 30.0),
        ((12.0, 30.0), cov(4.0, 2.0, 3.0), cov(20.0, 80.0, 10.0), 10.0, 10.3, 30.0),
        ((-60.0, 5.0), cov(2.0), cov(25.0, -150.0, 18.0), 7.0, 6.6, 20.0),
        ((300.0, 400.0), cov(5.0), cov(30.0), 100.0, 100.25, 100.0),
        ((0.0, 0.0), cov(3.0), cov(15.0), 3.0, 3.0, 30.0),
    ]
    c0 = cfg_for()
    for (de, dn), cg, cr, tg, tr, vmax in specs:
        rl, ro = offset(base[0], base[1], 7.0 * len(cases), -5.0 * len(cases))
        gl, go = offset(rl, ro, de, dn)
        g = Estimate("gps", gl, go, tg, cov=cg, cov_type=2)
        r = Estimate("day", rl, ro, tr, cov=cr, cov_type=3)
        cfg = dict(c0, max_speed_mps=vmax)
        cases.append({"gps": est_json(g), "ref": est_json(r), "vmax": vmax, "want": S.innovation(g, r, cfg),
                      "r": list(enu_flat(r.lat, r.lon, g.lat, g.lon))})
    # no stated accuracy → None
    g = Estimate("gps", base[0], base[1], 1.0, cov=cov(3.0), cov_type=2)
    for bad in (Estimate("day", base[0], base[1], 1.0, cov=(0.0,) * 9, cov_type=0),
                Estimate("day", base[0], base[1], 1.0, cov=cov(15.0), cov_type=0),
                Estimate("day", base[0], base[1], 1.0, cov=(0.0,) * 9, cov_type=2)):
        cases.append({"gps": est_json(g), "ref": est_json(bad), "vmax": 30.0, "want": None})
    out["innovation"] = cases
    fa = [([0.5, 9.3, 9.0, 9.4, 9.5, 9.6, 1.0], 9.21, 3), ([10.0, 11.0], 9.21, 3), ([20.0], 9.21, 1),
          ([1.0, 9.21, 9.22, 9.3], 9.21, 2), ([5.0] * 30 + [6.0] * 4, 5.99, 4), ([], 9.21, 2),
          ([3.0, 0.0, 3.0, 3.0, 0.0, 3.0, 3.0, 3.0], 2.5, 3)]
    out["first_alarm"] = [[s, g, n, S.first_alarm(s, g, n)] for s, g, n in fa]
    pa = [(1200.0, 12.0, 30.0, 50.0), (800.0, 0.0, 25.0, 40.0), (3000.0, 20.0, 20.0, 50.0), (3000.0, 20.0, 20.0, 0.0),
          (500.0, 35.0, 30.0, 50.0), (40.0, 10.0, 30.0, 50.0), (2500.0, 5.0, 100.0, 50.0), (50.0, 10.0, 30.0, 50.0)]
    out["patient"] = [[list(a), S.patient_accept_time(*a)] for a in pa]
    da = [(3.0, 15.0, 9.21, 5, 2.0), (1.0, 20.0, 5.99, 3, 1.0), (6.0, 18.0, 13.8, 2, 0.5), (0.0, 15.0, 9.21, 5, 2.0),
          (5.0, 10.0, 4.0, 1, 2.0), (2.0, 16.0, 9.0, 4, 3.0)]
    out["drift"] = [[list(a), S.drift_alarm_time(*a)] for a in da]
    return out


# ------------------------------------------------------------------------------- TODO 6–7 unit sequences
def sequences():
    """Short event lists in ENU metres around a still point (Reykjavik harbour); expected guard state after each."""
    o = (64.1500, -21.9400)

    def gps(t, e=0.0, n=0.0, sig=3.0):
        la, lo = offset(o[0], o[1], e, n)
        return Estimate("gps", la, lo, t, cov=cov(sig), cov_type=2)

    def ref(t, e=0.0, n=0.0, sig=15.0, ctype=2, src="day"):
        la, lo = offset(o[0], o[1], e, n)
        return Estimate(src, la, lo, t, cov=cov(sig) if ctype else (0.0,) * 9, cov_type=ctype)

    seqs = {
        # the cross-check: unknown ref, no GPS near, agree, 1 disagree, doubt, cleared, streak → drift, confirm
        "crosscheck": [gps(0), ref(0.1, ctype=0), ref(5.0), gps(1), ref(1.1, 10), gps(2, 2), ref(2.1, -48),
                       gps(3), ref(3.1, -50), gps(4), ref(4.1, 5), gps(5), ref(5.1, -52), gps(6), ref(6.1, -55),
                       gps(7), ref(7.1, -51), gps(8), ref(8.1, -60), gps(9), ref(9.1, -58), gps(10), gps(11),
                       ref(11.1, 4), gps(12), ref(12.1, -3), gps(13), ref(13.1)],
        # the far rule, and one far fix alone
        "far": [gps(0), ref(0.1, 300), gps(1), ref(1.1, 2), gps(2), ref(2.1, 250), gps(3), ref(3.1, -260),
                gps(4), gps(5)],
        # a big gap with a vague reference: beyond γ but above doubt_max_m, and not beyond γ_far
        "doubt_max": [gps(0), ref(0.1, 700, sig=200.0), gps(1), ref(1.1, 690, sig=200.0), gps(2),
                      ref(2.1, 710, sig=200.0), gps(3), ref(3.1, 705, sig=200.0), gps(4), ref(4.1, 700, sig=200.0),
                      gps(5)],
        # back after an outage while a stated reference exists ("jam, then spoof"), then confirmed; an outage while
        # already REFUSED changes nothing
        "outage_ref": [gps(0), ref(0.1), gps(1), ref(1.1, 3), gps(10, 1), gps(11), ref(11.1, -4), gps(12),
                       ref(12.1, 2), gps(13), gps(14, 900), gps(25, 400), ref(25.1, 2), gps(26)],
        # on_gps: first fix, jump, still refused, reachable again (no ref), outage with ref, refused stays, memory
        "on_gps": [gps(0), gps(1, 2000), gps(2, 2000), gps(40, 1500), gps(41, 1490), ref(41.1, 1495),
                   gps(46, 1500), gps(47, 3000), ref(47.1, 1490), gps(48, 1500), ref(48.1, 1495), gps(49, 1500),
                   gps(50, 1510), ref(50.5, 1500), gps(180, 1600), gps(200, 1700)],
        # IN_DOUBT survives GPS fixes the gate accepts (rule 5: no change); only a reference clears the doubt
        "doubt_kept": [gps(0), ref(0.1, -65), gps(1), ref(1.1, -66), gps(2), gps(3), gps(4, 5), ref(4.1, 2),
                       gps(5), ref(5.1, -64), gps(6), ref(6.1, -66), gps(7)],
        # back after an outage WITHOUT any stated reference: the gate decides
        "outage_noref": [gps(0), ref(0.1, ctype=0), gps(10, 200), gps(11, 5000), gps(80, 1500)],
    }
    out = {}
    for name, events in seqs.items():
        g = S.SpoofGuard(cfg_for())
        steps = []
        for e in events:
            if e.source == "gps":
                verdict = g.check(e)
                ret = list(verdict)
            else:
                ret = g.on_reference(e)
            steps.append({"est": est_json(e), "ret": ret, "state": g.state, "refused_by": g.refused_by,
                          "disagree": g.disagree, "far": g.far, "agree": g.agree, "last_ref_s": g.last_ref_s,
                          "doubt_m": round(g.doubt_m, 3),
                          "gate_trusted_s": None if g.gate.trusted is None else g.gate.trusted.stamp_s})
        out[name] = steps
    return out


# ------------------------------------------------------------------------------- hidden attacks (TODO 6–7 together)
def attack(seed, start, heading_deg, speed, seconds, off_fn, gps_on=None, vis_sigma=15.0, vis_states=True,
           vis_after=0.1, vis_latency=0.5, vis_period=2, wrong=None, vmax=30.0):
    rng = np.random.default_rng(seed)
    h = math.radians(heading_deg)
    rows = []
    for i in range(seconds + 1):
        t = float(i)
        ge, gn = rng.normal(0, 3.0, 2)
        ve, vn = rng.normal(0, vis_sigma, 2)
        if gps_on is None or gps_on(t):
            oe, on = off_fn(t)
            la, lo = offset(start[0], start[1], speed * t * math.sin(h) + ge + oe, speed * t * math.cos(h) + gn + on)
            rows.append((t + 0.05, Estimate("gps", la, lo, t, cov=cov(3.0), cov_type=2), math.hypot(oe, on)))
        if i % vis_period == 0:
            tv = t + vis_after
            we, wn = (wrong or {}).get(i, (0.0, 0.0))
            la, lo = offset(start[0], start[1], speed * tv * math.sin(h) + ve + we, speed * tv * math.cos(h) + vn + wn)
            rows.append((tv + vis_latency, Estimate("day", la, lo, tv, cov=cov(vis_sigma) if vis_states else (0.0,) * 9,
                                                    cov_type=2 if vis_states else 0), 0.0))
    rows.sort(key=lambda r: r[0])
    g = S.SpoofGuard(cfg_for(vmax))
    out = []
    for _, e, off in rows:
        v = g.check(e)
        out.append({"est": est_json(e), "offset_m": off, "verdict": v[0] if e.source == "gps" else None})
    return {"vmax": vmax, "rows": out}


def attacks():
    cape, rey, quito, syd = (-33.90, 18.42), (64.15, -21.94), (-0.18, -78.47), (-33.86, 151.21)
    return {
        "drift 3 m/s north-east (Cape Town)": attack(41, cape, 90.0, 12.0, 80,
                                                     lambda t: (2.1 * (t - 8), 2.1 * (t - 8)) if 8 <= t < 60 else (0, 0)),
        "patient 1.2 km, vision σ 12 m (Reykjavik)": attack(42, rey, 200.0, 10.0, 90,
                                                           lambda t: (0.0, -1200.0) if 15 <= t < 70 else (0, 0),
                                                           vis_sigma=12.0),
        "jam, then 800 m spoof (Quito)": attack(43, quito, 45.0, 14.0, 80,
                                                lambda t: (800.0, 0.0) if 40 <= t < 55 else (0, 0),
                                                gps_on=lambda t: not 10 <= t < 40),
        "3 km jump, vision of unknown accuracy (Sydney)": attack(44, syd, 300.0, 15.0, 60,
                                                                 lambda t: (-3000.0, 0.0) if 20 <= t < 35 else (0, 0),
                                                                 vis_states=False),
        "patient 600 m, vision of unknown accuracy (Sydney)": attack(45, syd, 120.0, 10.0, 100,
                                                                     lambda t: (0.0, 600.0) if 10 <= t < 70 else (0, 0),
                                                                     vis_states=False),
        "honest GPS, wrong vision matches (Reykjavik)": attack(46, rey, 0.0, 15.0, 70, lambda t: (0, 0),
                                                              wrong={20: (150.0, 0.0), 22: (140.0, 20.0),
                                                                     40: (3000.0, 0.0), 56: (0.0, -400.0)}),
        "fast drift 8 m/s, photo 0.3 s after the GPS, top speed 20 m/s (Quito)":
            attack(47, quito, 270.0, 15.0, 60, lambda t: (0.0, 8.0 * (t - 10)) if 10 <= t < 45 else (0, 0),
                   vis_after=0.3, vmax=20.0),
    }


# ------------------------------------------------------------------------------- the lab's own numbers
def lab(arbiter_path):
    work = tempfile.mkdtemp(prefix="lab30_")
    try:
        shutil.copytree(os.path.join(COURSE, "files"), work, dirs_exist_ok=True)
        shutil.copytree(os.path.join(HERE, "navera_lite"), os.path.join(work, "navera_lite"), dirs_exist_ok=True)
        shutil.copy(os.path.join(HERE, "detection.py"), work)
        dst = os.path.join(work, "navera_lite", "arbiter.py")
        if not os.path.exists(dst):
            shutil.copy(arbiter_path, dst)

        def run(*cmd):
            r = subprocess.run([sys.executable, *cmd], cwd=work, capture_output=True, text=True, timeout=600,
                               env=dict(os.environ, MPLBACKEND="Agg"))
            if r.returncode:
                raise SystemExit(f"{cmd} failed:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
            return r.stdout
        run("spoof_run.py", "stats")
        run("spoof_run.py", "patient", "--no-guard", "--vmax", "100.0")
        runs_v100 = json.load(open(os.path.join(work, "runs.json")))["patient__noguard"]
        run("spoof_run.py", "all")
        runs = json.load(open(os.path.join(work, "runs.json")))
        run("detection.py")
        res = json.load(open(os.path.join(work, "results.json")))

        def flown_t(s):
            return next(r["t"] for r in s["timeline"] if r["flown_offset_m"] > 1000)
        creep = []
        for x10 in range(460, 545, 5):
            x = x10 / 10
            run("spoof_run.py", "creep", "--creep", str(x))
            s = json.load(open(os.path.join(work, "runs.json")))["creep"]
            creep.append([x, s["first"]["REFUSED"] is not None, s["first"]["IN_DOUBT"] is not None])
        stats = runs["stats"]
        best = max((r for r in res["roc"] if r["p_fa"] <= 0.01), key=lambda r: (r["p_d"], -r["p_fa"]))
        L = {
            "noguard_max_error_m": runs["drift__noguard"]["max_error_m"],
            "stats_share_1pc": next(r["measured"] for r in stats["rows"] if r["p_fa"] == 0.01),
            "mean_d2": stats["mean_d2"],
            "patient_theory_dt_s": S.patient_accept_time(2000.0, 15.0, 30.0, 50.0),
            "patient_flown_t_s": flown_t(runs["patient__noguard"]),
            "vmax100_flown_t_s": flown_t(runs_v100),
            "drift_theory_s": S.drift_alarm_time(4.0, math.sqrt(243.0), S.chi2_threshold_2d(0.01), 5, 2.0),
            "roc": res["roc"], "single_test": res["single_test"], "correlated": res["correlated"],
            "best": {"p": best["p"], "n": best["n"]},
            "navera_rule_pd": next(r["p_d"] for r in res["roc"] if r["p"] == 0.01 and r["n"] == 5),
            "correlated_pfa": next(r["p_fa_rho_0.9"] for r in res["correlated"] if r["p"] == 0.05 and r["n"] == 3),
            "drift_doubt_offset_m": runs["drift"]["first"]["IN_DOUBT"]["offset_m"],
            "drift_refused_offset_m": runs["drift"]["first"]["REFUSED"]["offset_m"],
            "drift_refused_t_s": runs["drift"]["first"]["REFUSED"]["t"],
            "drift_doubt_t_s": runs["drift"]["first"]["IN_DOUBT"]["t"],
            "creep_scan": creep,
            "all": {k: {kk: v[kk] for kk in ("first", "spoofed_trusted", "judge_flew_spoofed", "honest_refused_after",
                                             "max_error_m", "max_trusted_offset_m")}
                    for k, v in runs.items() if k != "stats"},
        }
        return L
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arbiter", default=None, help="a stand-in navera_lite/arbiter.py while mission 29 is missing")
    a = ap.parse_args()
    ref_arb = os.path.join(ACADEMY, "solutions", "_navera_lite", "navera_lite", "arbiter.py")
    arb = ref_arb if os.path.exists(ref_arb) else a.arbiter
    if not arb or not os.path.exists(arb):
        raise SystemExit("mission 29's arbiter.py is not in the reference yet: give --arbiter PATH (a stand-in)")
    E = {"units": units(), "sequences": sequences(), "attacks": attacks(), "lab": lab(arb),
         "arbiter_used": os.path.relpath(arb, ACADEMY) if arb.startswith(ACADEMY) else "stand-in: " + arb}
    os.makedirs(os.path.join(COURSE, "hidden"), exist_ok=True)
    with open(os.path.join(COURSE, "hidden", "expected.json"), "w") as f:
        json.dump(E, f, indent=None, separators=(",", ":"))
    L = E["lab"]
    print("lab numbers:", {k: v for k, v in L.items() if k not in ("roc", "all", "creep_scan", "single_test", "correlated")})
    print("creep: never refused up to", max(x for x, r, _ in L["creep_scan"] if not r), "m; refused from",
          min(x for x, r, _ in L["creep_scan"] if r), "m")
    print("wrote", os.path.relpath(os.path.join(COURSE, "hidden", "expected.json"), ACADEMY),
          f"({os.path.getsize(os.path.join(COURSE, 'hidden', 'expected.json')) // 1024} kB)")


if __name__ == "__main__":
    main()
