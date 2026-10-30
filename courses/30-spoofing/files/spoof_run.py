"""spoof_run.py — plays the attacks of scenarios.py through YOUR spoofing guard (navera_lite/spoof.py) in front of
the judge of mission 29 (navera_lite/arbiter.py), and shows who wins.

    python3 spoof_run.py test                 each function of spoof.py on its docstring example (and a few traps)
    python3 spoof_run.py stats                20 000 honest GPS/vision pairs: does your test keep its promise?
    python3 spoof_run.py ATTACK [options]     one attack, second by second (only the changes are printed)
    python3 spoof_run.py all                  every attack, with and without the guard: the summary table
    python3 spoof_run.py ATTACK --ros         the same attack LIVE over ROS 2, against guard_node.py (Step 10)

    ATTACK: jump, patient, patient_vision, drift, drift_novision, jamspoof, jamspoof_novision, glitch, creep
    options: --no-guard      the judge alone (mission 29), no spoofing guard
             --vmax V        the jump gate's top speed in m/s (default: the vehicle's, 30 m/s for the drone)
             --drift U       the drift speed of the drift attacks (m/s, default 4)
             --creep M       the offset of the creep attack (m, default 30)
             --pfa P         the guard's false-alarm probability per test (default 0.01)
             --seed N        another noise draw of the same attack (default 30)
             --mine          fly YOUR judge from ../29-arbiter instead of the course's (Going further)
    with --ros:  --until T       stop after T s of the attack (drift: 45 s)
                 --out FILE      save the live run in FILE (default ros_<attack>.json)

Every run is saved in runs.json (the check reads it) and drawn in out/<attack>.png (click it in the 📝 Code tab).
"""
import importlib.util
import json
import math
import os
import sys

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

sp = rk.load_student("navera_lite.spoof")
est_mod = rk.load_student("navera_lite.estimate")
geo = rk.load_student("navera_lite.geo")
settings = rk.load_student("navera_lite.settings")
vehicle = rk.load_student("navera_lite.vehicle")
import scenarios  # noqa: E402  (after the student's package is on sys.path)

RUNS = "runs.json"
TICK_S = 0.2                       # the judge also decides 5 times a second (tick_hz)


# ------------------------------------------------------------------------------------------- helpers
def flag(args, name, default=None, kind=float):
    if name not in args:
        return default
    i = args.index(name)
    if i + 1 >= len(args):
        sys.exit(f"{name} needs a value, e.g. {name} 30")
    try:
        return kind(args[i + 1])
    except ValueError:
        sys.exit(f"{name} needs a number, got {args[i + 1]!r}")


def settings_for(args):
    try:
        cfg = settings.load("navera_lite.yaml")
    except (OSError, ValueError) as e:
        sys.exit(f"navera_lite.yaml cannot be read: {e}")
    top = vehicle.VEHICLES.get(cfg["vehicle"], 30.0)
    cfg["max_speed_mps"] = float(flag(args, "--vmax", top))
    p = flag(args, "--pfa", sp.GUARD_DEFAULTS["p_fa"])
    if not 0.0 < p < 1.0:
        sys.exit(f"--pfa must be a probability between 0 and 1, got {p}")
    cfg["p_fa"] = p
    return cfg


def load_arbiter(mine):
    """The judge: navera_lite/arbiter.py of this folder (the course's mission-29 judge), or yours (--mine)."""
    if mine:
        path = os.path.join("..", "29-arbiter", "navera_lite", "arbiter.py")
        if not os.path.exists(path):
            sys.exit(f"{path} is missing: --mine flies the judge you wrote in mission 29 (its lesson folder)")
        spec = importlib.util.spec_from_file_location("navera_lite.arbiter", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["navera_lite.arbiter"] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception as e:                                   # noqa: BLE001 — one plain sentence
            sys.exit(f"{path} has an error, so it cannot be loaded: {type(e).__name__}: {e}")
        print(f"flying YOUR judge: {path}")
        return mod
    if not os.path.exists(os.path.join("navera_lite", "arbiter.py")):
        sys.exit("navera_lite/arbiter.py is missing: it is mission 29's judge (tell your teacher)")
    return rk.load_student("navera_lite.arbiter")


def field(d, name):
    """A field of the judge's decision (an object with attributes, or a dict)."""
    return d.get(name) if isinstance(d, dict) else getattr(d, name, None)


def need_written(*names):
    for n in names:
        obj, cls_name = sp, None
        if "." in n:
            cls_name, meth = n.split(".")
            obj, n = getattr(sp, cls_name), meth
        f = getattr(obj, n, None)
        if f is None:
            sys.exit(f"{n}() does not exist in navera_lite/spoof.py — did you rename it?")
        if rk.is_stub(f):
            where = f"{cls_name}.{n}" if cls_name else n
            sys.exit(f"{where}() is not written yet: write its TODO in navera_lite/spoof.py first "
                     "(python3 spoof_run.py test shows which ones work)")


def err_m(est):
    """How far a position is from the truth at the instant it was measured (m)."""
    lat0, lon0 = scenarios.truth(est.stamp_s)
    e, n = geo.enu_flat(lat0, lon0, est.lat, est.lon)
    return math.hypot(e, n)


def save_run(key, summary):
    try:
        with open(RUNS) as f:
            runs = json.load(f)
    except (OSError, ValueError):
        runs = {}
    runs[key] = summary
    with open(RUNS, "w") as f:
        json.dump(runs, f, indent=1)


# ------------------------------------------------------------------------------------------- test
def cmd_test():
    print("Each function of navera_lite/spoof.py on its docstring example:\n")
    G = sp.GUARD_DEFAULTS
    cfg = dict(settings.DEFAULTS, max_speed_mps=30.0)
    ok_all = True

    def show(label, got, err, want, tol=1e-3):
        nonlocal ok_all
        if err:
            print(f"  ✘ {label}: {err}")
            ok_all = False
            return
        good = got == want if isinstance(want, str) else (
            isinstance(got, (int, float)) and not isinstance(got, bool) and
            (got == want or abs(got - want) <= tol))
        ok_all &= bool(good)
        print(f"  {'✔' if good else '✘'} {label} = {got!r}" + ("" if good else "   ← not the docstring's value"))

    v, e = rk.call(sp, "chi2_threshold_2d", 0.05)
    show("chi2_threshold_2d(0.05)", v, e, 5.991464547107979)
    v, e = rk.call(sp, "chi2_threshold_2d", 0.01)
    show("chi2_threshold_2d(0.01)", v, e, 9.210340371976182)
    _, e = rk.call(sp, "chi2_threshold_2d", 1.5)
    if e and "not written yet" in e:
        print(f"  ✘ chi2_threshold_2d(1.5): {e}")
    else:
        print("  " + ("✔ chi2_threshold_2d(1.5) refuses (not a probability)" if e and "ValueError" in e
                      else "✘ chi2_threshold_2d(1.5) should raise ValueError: 1.5 is not a probability"))
    lat, lon = 35.80, 10.66
    ref = est_mod.Estimate("day", lat, lon, 100.0, cov=(225.0, 0, 0, 0, 225.0, 0, 0, 0, 400.0), cov_type=2)
    glat, glon = geo.offset(lat, lon, 30.0, 0.0)
    gps = est_mod.Estimate("gps", glat, glon, 100.0, cov=(9.0, 0, 0, 0, 9.0, 0, 0, 0, 36.0), cov_type=2)
    v, e = rk.call(sp, "innovation", gps, ref, cfg)
    if not e and not (isinstance(v, (tuple, list)) and len(v) == 2):
        e = f"innovation() must return (d2, dist_m), two numbers, but it returned {v!r}"
    show("innovation(...)[0], d²", None if e else v[0], e, 3.846, 1e-3)
    if not e:
        show("innovation(...)[1], dist_m", v[1], None, 30.0, 0.05)
    blind = est_mod.Estimate("day", lat, lon, 100.0)
    v, e = rk.call(sp, "innovation", gps, blind, cfg)
    if e and "returned None" in e:
        print("  ✔ innovation(gps, a reference of UNKNOWN accuracy) → None (nothing to test against)")
    elif e and "not written yet" in e:
        print(f"  ✘ innovation(gps, a reference of UNKNOWN accuracy): {e}")
    else:
        ok_all = False
        print(f"  ✘ innovation(gps, a reference of UNKNOWN accuracy): {e}" if e else
              f"  ✘ innovation(gps, a reference of UNKNOWN accuracy) should be None, got {v!r}")
    v, e = rk.call(sp, "first_alarm", [1.0, 12.0, 13.0, 2.0, 11.0, 10.0, 15.0], 9.21, 3)
    show("first_alarm([1, 12, 13, 2, 11, 10, 15], 9.21, 3)", v, e, 6, 0)
    v, e = rk.call(sp, "first_alarm", [12.0, 13.0], 9.21, 3)
    show("first_alarm([12, 13], 9.21, 3)", v, e, -1, 0)
    v, e = rk.call(sp, "patient_accept_time", 1000.0, 10.0, 20.0, 50.0)
    show("patient_accept_time(1000, 10, 20, 50)", v, e, 54.4256, 1e-3)
    v, e = rk.call(sp, "patient_accept_time", 2000.0, 30.0, 30.0, 0.0)
    show("patient_accept_time(2000, 30, 30, 0)", v, e, math.inf)
    v, e = rk.call(sp, "drift_alarm_time", 2.5, 20.0, 5.99, 3, 1.0)
    show("drift_alarm_time(2.5, 20, 5.99, 3, 1)", v, e, 22.0, 1e-9)
    if all(not rk.is_stub(getattr(sp.SpoofGuard, m)) for m in ("on_reference", "on_gps")):
        g = sp.SpoofGuard(dict(cfg, **G))
        start = est_mod.Estimate("gps", lat, lon, 10.0, cov=(9.0, 0, 0, 0, 9.0, 0, 0, 0, 36.0), cov_type=2)
        v, e = rk.call(g, "check", start)
        show("SpoofGuard: first GPS fix → verdict", None if e else v[0], e, "TRUSTED")
        jl, jo = geo.offset(lat, lon, 2000.0, 0.0)
        jump = est_mod.Estimate("gps", jl, jo, 11.0, cov=start.cov, cov_type=2)
        v, e = rk.call(g, "check", jump)
        show("SpoofGuard: then 2 km away 1 s later → verdict", None if e else v[0], e, "REFUSED")
        vis = (225.0, 0, 0, 0, 225.0, 0, 0, 0, 400.0)
        rk.call(g, "check", est_mod.Estimate("day", lat, lon, 11.1, cov=vis, cov_type=2))   # a stated reference
        v, e = rk.call(g, "check", est_mod.Estimate("gps", jl, jo, 16.0, cov=start.cov, cov_type=2))
        show("SpoofGuard: REFUSED (jump), back after 5 s of silence → refused_by", None if e else g.refused_by, e,
             "jump")
        g2 = sp.SpoofGuard(dict(cfg, **G))
        for k in range(2):                       # two vision fixes 65 m west of the GPS: d² ≈ 17 (γ < d² < γ_far)
            f = est_mod.Estimate("gps", *geo.offset(lat, lon, 0.0, 15.0 * k), 20.0 + k, cov=start.cov, cov_type=2)
            rk.call(g2, "check", f)
            r = est_mod.Estimate("day", *geo.offset(lat, lon, -65.0, 15.0 * k + 1.5), 20.1 + k, cov=vis, cov_type=2)
            rk.call(g2, "check", r)
        v, e = rk.call(g2, "check", est_mod.Estimate("gps", *geo.offset(lat, lon, 0.0, 30.0), 22.0, cov=start.cov,
                                                      cov_type=2))
        show("SpoofGuard: IN_DOUBT, then a GPS fix the gate accepts → verdict", None if e else v[0], e, "IN_DOUBT")
    else:
        ok_all = False
        print("  ✘ SpoofGuard.on_reference / on_gps: not written yet (TODO 6–7)")
    print("\nAll examples right. Now the attacks: python3 spoof_run.py drift" if ok_all else
          "\nFix the ✘ lines first (the lesson's worked examples and the docstrings show the rule).")


# ------------------------------------------------------------------------------------------- stats
def cmd_stats(args):
    need_written("chi2_threshold_2d", "innovation")
    import numpy as np
    cfg = dict(settings.DEFAULTS, max_speed_mps=30.0)
    rng = np.random.default_rng(3030)
    n = 20000
    lat, lon = scenarios.START
    vis_cov = (225.0, 0, 0, 0, 225.0, 0, 0, 0, 400.0)
    gps_cov = (9.0, 0, 0, 0, 9.0, 0, 0, 0, 36.0)
    d2s = []
    for _ in range(n):
        ge, gn, ve, vn = rng.normal(0.0, 1.0, 4) * [3.0, 3.0, 15.0, 15.0]
        g = est_mod.Estimate("gps", *geo.offset(lat, lon, ge, gn), 50.0, cov=gps_cov, cov_type=2)
        r = est_mod.Estimate("day", *geo.offset(lat, lon, ve, vn), 50.1, cov=vis_cov, cov_type=2)
        got = rk.need_ok(sp, "innovation", g, r, cfg)
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            sys.exit(f"innovation() must return (d2, dist_m), got {got!r}")
        d2s.append(float(got[0]))
    d2s = np.array(d2s)
    print(f"{n} HONEST pairs: GPS σ 3 m, vision σ 15 m, photo 0.1 s after the GPS fix (top speed 30 m/s)\n")
    print("  p_fa     threshold γ   measured share with d² > γ")
    rows = []
    for p in (0.1, 0.05, 0.01, 0.001):
        gamma = rk.need_ok(sp, "chi2_threshold_2d", p, kind=float)
        share = float(np.mean(d2s > gamma))
        rows.append({"p_fa": p, "gamma": gamma, "measured": share})
        print(f"  {p:<7}  {gamma:9.3f}     {share:.4f}")
    dist = np.sqrt(d2s)
    print(f"\n  mean d² = {d2s.mean():.3f}   (a χ² law with 2 degrees of freedom has mean 2)")
    save_run("stats", {"pairs": n, "rows": rows, "mean_d2": float(d2s.mean())})
    plt = rk.plt_or_none()
    if plt:
        os.makedirs("out", exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 3.6))
        ax.hist(d2s, bins=np.linspace(0, 16, 65), density=True, color="#9ec5d6", label="your d² (honest pairs)")
        x = np.linspace(0, 16, 200)
        ax.plot(x, 0.5 * np.exp(-x / 2), color="#1d2733", lw=2, label="χ² with 2 degrees of freedom")
        g = rows[2]["gamma"]
        ax.axvline(g, color="#d64545", ls="--", label=f"γ for p_fa 0.01 = {g:.2f}")
        ax.set_xlabel("d²")
        ax.set_ylabel("density")
        ax.legend()
        fig.tight_layout()
        fig.savefig("out/stats.png", dpi=100)
        rk.saved("out/stats.png")
    del dist


# ------------------------------------------------------------------------------------------- one attack
def play(name, args, verbose=True):
    """Play one attack; returns the summary saved in runs.json."""
    guard_on = "--no-guard" not in args
    if guard_on:
        need_written("chi2_threshold_2d", "innovation", "SpoofGuard.on_reference", "SpoofGuard.on_gps")
    cfg = settings_for(args)
    arb_mod = load_arbiter("--mine" in args)
    drift = flag(args, "--drift")
    creep = flag(args, "--creep")
    seed = flag(args, "--seed", scenarios.SEED, kind=int)
    try:
        rows = scenarios.build(name, seed=seed, drift_mps=drift, creep_m=creep)
    except ValueError as e:
        sys.exit(str(e))
    judge = arb_mod.Arbiter(cfg)
    guard = sp.SpoofGuard(cfg) if guard_on else None
    front = sp.GuardedArbiter(judge, guard) if guard_on else judge
    if verbose:
        print(f"=== {name}: {scenarios.describe(name, drift, creep)}"
              + ("" if seed == scenarios.SEED else f" (noise seed {seed})"))
        print(f"    top speed {cfg['max_speed_mps']:g} m/s, margin {cfg['gps_jump_margin_m']:g} m"
              + (f", guard p_fa {cfg['p_fa']:g}" if guard_on else ", NO guard (the judge alone)") + "\n")
        print("     t (s)  GPS offset │ guard verdict │ judge: state, source, error of its position")
    events = [(r[0], 0, r) for r in rows]
    end = rows[-1][0] + 1.0
    events += [(k * TICK_S, 1, None) for k in range(int(end / TICK_S) + 1)]
    events.sort(key=lambda e: (e[0], e[1]))
    gps_offset = {r[1].stamp_s: r[2] for r in rows if r[1].source == "gps"}
    timeline, last_key, verdict, why = [], None, "—", ""
    for t, kind, row in events:
        if kind == 0:
            est = row[1]
            if guard_on:
                got = rk.call(front, "receive", est, t)
                if got[1]:
                    sys.exit(f"the guard stopped: {got[1]}")
                verdict, why = got[0] if isinstance(got[0], tuple) else (got[0], "")
                if not isinstance(verdict, str):
                    sys.exit(f"SpoofGuard.check() must return (verdict, reason), got {got[0]!r} "
                             "(does on_gps return self.set_state(...)?)")
            else:
                judge.receive(est, t)
        d = front.step(t)
        state, source, win = field(d, "state"), field(d, "source"), field(d, "estimate")
        if kind == 0 and row[1].source == "gps":
            error = err_m(win) if win is not None else None
            flown = gps_offset.get(win.stamp_s, 0.0) if win is not None and win.source == "gps" else 0.0
            timeline.append({"t": round(row[1].stamp_s, 2), "offset_m": round(row[2], 1), "verdict": verdict,
                             "reason": why, "state": state, "source": source,
                             "flown_offset_m": round(flown, 1),
                             "error_m": None if error is None else round(error, 1)})
            key = (verdict, state, source)
            if verbose and key != last_key:
                e_txt = "—" if error is None else f"{error:.0f} m"
                print(f"  {row[1].stamp_s:7.1f}  {row[2]:7.0f} m │ {verdict:8s} │ {state} {source or ''}, error {e_txt}"
                      + (f"\n            guard: {why}" if guard_on and why else ""))
                last_key = key
    summary = summarise(name, timeline, cfg, guard_on, drift, creep)
    summary["seed"] = seed
    key = name + ("" if guard_on else "__noguard")
    save_run(key, summary)
    if verbose:
        print_summary(summary)
        draw(name, timeline, guard_on)
    return summary


def summarise(name, tl, cfg, guard_on, drift, creep):
    spoofed = [r for r in tl if r["offset_m"] > 0]
    honest_after = [r for r in tl if r["offset_m"] == 0 and spoofed and r["t"] > spoofed[0]["t"]]
    first = {}
    for v in ("IN_DOUBT", "REFUSED"):
        r = next((r for r in spoofed if r["verdict"] == v), None)
        first[v] = None if r is None else {"t": r["t"], "offset_m": r["offset_m"]}
    trusted_spoofed = [r for r in spoofed if r["verdict"] == "TRUSTED"]
    flown = [r for r in tl if r["flown_offset_m"] > 0]
    errors = [r["error_m"] for r in tl if r["error_m"] is not None]
    refused_honest = [r for r in honest_after if r["verdict"] == "REFUSED"]
    return {"attack": name, "guard": guard_on, "max_speed_mps": cfg["max_speed_mps"], "p_fa": cfg.get("p_fa"),
            "drift_mps": drift, "creep_m": creep, "gps_fixes": len(tl), "spoofed_fixes": len(spoofed),
            "first": first,
            "max_trusted_offset_m": max((r["offset_m"] for r in trusted_spoofed), default=0.0),
            "spoofed_trusted": len(trusted_spoofed), "judge_flew_spoofed": len(flown),
            "judge_flew_spoofed_state": sorted({r["state"] for r in flown}),
            "honest_refused_after": len(refused_honest),
            "last_honest_refused_t": refused_honest[-1]["t"] if refused_honest else None,
            "max_error_m": max(errors, default=None), "timeline": tl}


def print_summary(s):
    print("\nSummary")
    for v in ("IN_DOUBT", "REFUSED") if s["guard"] else ():
        f = s["first"][v]
        print(f"  first {v:8s} of a spoofed fix: " + ("never" if f is None else f"t = {f['t']:.0f} s, offset {f['offset_m']:.0f} m"))
    if s["guard"]:
        print(f"  spoofed fixes judged TRUSTED: {s['spoofed_trusted']} of {s['spoofed_fixes']}"
              f" (largest offset among them: {s['max_trusted_offset_m']:.0f} m)")
    print(f"  seconds the judge FLEW on a spoofed GPS fix: {s['judge_flew_spoofed']}"
          + (f" (as {', '.join(s['judge_flew_spoofed_state'])})" if s["judge_flew_spoofed"] else ""))
    if s["honest_refused_after"]:
        print(f"  honest GPS fixes REFUSED after the attack: {s['honest_refused_after']}"
              f" (the last at t = {s['last_honest_refused_t']:.0f} s)")
    print(f"  largest error of the judge's position: {s['max_error_m']:.0f} m" if s["max_error_m"] is not None
          else "  the judge never had a position")


def draw(name, tl, guard_on):
    plt = rk.plt_or_none()
    if not plt:
        return
    os.makedirs("out", exist_ok=True)
    colors = {"TRUSTED": "#2e9e4f", "IN_DOUBT": "#e0a106", "REFUSED": "#d64545", "—": "#8a96a3"}
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    t = [r["t"] for r in tl]
    a1.plot(t, [r["offset_m"] for r in tl], color="#8a96a3", lw=1.5, label="spoofer's offset (m)")
    a1.plot(t, [r["error_m"] if r["error_m"] is not None else float("nan") for r in tl], color="#0b6e8a", lw=2,
            label="error of the judge's position (m)")
    a1.set_ylabel("m")
    a1.set_yscale("symlog", linthresh=50)
    a1.legend(loc="upper left", fontsize=8)
    a1.set_title(f"{name} — {'with your guard' if guard_on else 'the judge alone, no guard'}")
    for r in tl:
        a2.bar(r["t"], 1, width=1.0, color=colors.get(r["verdict"], "#8a96a3"))
        a2.bar(r["t"], 0.4, width=1.0, bottom=-0.6,
               color={"gps": "#1d2733", "day": "#0b6e8a"}.get(r["source"], "#ffffff"))
    a2.set_yticks([-0.4, 0.5])
    a2.set_yticklabels(["judge flies", "guard"])
    a2.set_xlabel("t (s) — guard: green TRUSTED, yellow IN_DOUBT, red REFUSED; judge: black GPS, blue day vision")
    fig.tight_layout()
    path = f"out/{name}{'' if guard_on else '_noguard'}.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    rk.saved(path)


def cmd_all(args):
    print(f"{'attack':18s} {'guard':5s} {'1st IN_DOUBT':>14s} {'1st REFUSED':>14s} {'spoof TRUSTED':>13s} "
          f"{'judge flew spoof':>16s} {'honest refused':>14s} {'max error':>9s}")
    for name in scenarios.NAMES:
        for guard in (True, False):
            s = play(name, args + ([] if guard else ["--no-guard"]), verbose=False)
            f = s["first"]

            def cell(x):
                return "never" if x is None else f"{x['t']:.0f} s/{x['offset_m']:.0f} m"
            print(f"{name:18s} {'yes' if guard else 'no':5s} {cell(f['IN_DOUBT']) if guard else '':>14s} "
                  f"{cell(f['REFUSED']) if guard else '':>14s} {s['spoofed_trusted'] if guard else '':>13} "
                  f"{s['judge_flew_spoofed']:>16} {s['honest_refused_after'] if guard else '':>14} "
                  f"{s['max_error_m']:>7.0f} m")
    print("\n(t/offset = time and spoofer's offset of the first spoofed GPS fix with that verdict; "
          "every run is in runs.json)")


# ------------------------------------------------------------------------------------------- live over ROS
def cmd_ros(name, args):
    """Publish the attack in real time on navera_lite/fix/gps and navera_lite/fix/day, listen to the judge's
    status and position, and save what happened in ros_<attack>.json."""
    try:
        import rclpy
        from diagnostic_msgs.msg import DiagnosticStatus
        from rclpy.node import Node
        from sensor_msgs.msg import NavSatFix
    except ImportError:
        sys.exit("rclpy is missing: run `source /opt/ros/humble/setup.bash` in this terminal first")
    conv = rk.load_student("navera_lite.ros.convert")
    qos = rk.load_student("navera_lite.ros.qos")
    drift, creep = flag(args, "--drift"), flag(args, "--creep")
    until = flag(args, "--until", {"drift": 45.0}.get(name, 1e9))
    seed = flag(args, "--seed", scenarios.SEED, kind=int)
    out_path = flag(args, "--out", f"ros_{name}.json", kind=str)
    rows = [r for r in scenarios.build(name, seed=seed, drift_mps=drift, creep_m=creep) if r[0] <= until]

    class Player(Node):
        def __init__(self):
            super().__init__("spoof_player")
            self.pub = {s: self.create_publisher(NavSatFix, f"navera_lite/fix/{s}", qos.FIX_QOS) for s in ("gps", "day")}
            self.create_subscription(DiagnosticStatus, "navera_lite/status", self.on_status, qos.STATUS_QOS)
            self.status, self.changes = None, []

        def on_status(self, msg):
            self.status = msg

    rclpy.init()
    node = Player()
    t_wait = node.get_clock().now().nanoseconds * 1e-9
    while node.count_subscribers("navera_lite/fix/gps") == 0:
        rclpy.spin_once(node, timeout_sec=0.2)
        if node.get_clock().now().nanoseconds * 1e-9 - t_wait > 20.0:
            node.destroy_node()
            rclpy.shutdown()
            sys.exit("no judge listens on navera_lite/fix/gps: start guard_node.py first (Step 10), then wait 2 s")
    print(f"=== {name} LIVE over ROS ({rows[-1][0]:.0f} s): {scenarios.describe(name, drift, creep)}\n")
    print("     t (s)  GPS offset │ status from the judge")
    t0 = node.get_clock().now().nanoseconds * 1e-9 + 1.0
    i, last, gps_off = 0, None, 0.0
    try:
        while i < len(rows) or node.get_clock().now().nanoseconds * 1e-9 < t0 + rows[-1][0] + 1.5:
            now = node.get_clock().now().nanoseconds * 1e-9
            while i < len(rows) and now >= t0 + rows[i][0]:
                est = rows[i][1]
                if est.source == "gps":
                    gps_off = rows[i][2]
                live = est_mod.Estimate(est.source, est.lat, est.lon, t0 + est.stamp_s, cov=est.cov,
                                        cov_type=est.cov_type, alt_m=est.alt_m)
                node.pub[est.source].publish(conv.to_navsatfix(live))
                i += 1
            rclpy.spin_once(node, timeout_sec=0.02)
            st = node.status
            if st is not None:
                vals = conv.status_values(st)
                key = (vals.get("state"), vals.get("source"), vals.get("gps_guard"))
                if key != last:
                    t_rel = now - t0
                    node.changes.append({"t": round(t_rel, 2), "offset_m": round(gps_off, 1),
                                         "state": vals.get("state"), "source": vals.get("source"),
                                         "gps_guard": vals.get("gps_guard"), "reason": st.message})
                    print(f"  {t_rel:7.1f}  {gps_off:7.0f} m │ {vals.get('state')} {vals.get('source') or ''}"
                          f" · guard {vals.get('gps_guard')} · {st.message}")
                    last = key
    except KeyboardInterrupt:
        print("\nstopped (Ctrl+C): the file is saved with what was recorded")
    out = {"attack": name, "live": True, "domain": os.environ.get("ROS_DOMAIN_ID"), "until_s": until,
           "changes": node.changes}
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nsaved {out_path} ({len(node.changes)} changes)")
    node.destroy_node()
    rclpy.shutdown()


# ------------------------------------------------------------------------------------------- main
def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    what, args = argv[0], argv[1:]
    if what == "test":
        cmd_test()
    elif what == "stats":
        cmd_stats(args)
    elif what == "all":
        cmd_all(args)
    elif what in scenarios.ATTACKS:
        if "--ros" in args:
            cmd_ros(what, args)
        else:
            play(what, args)
    else:
        sys.exit(f"unknown command {what!r}: test, stats, all, or an attack ({', '.join(scenarios.NAMES)})")


if __name__ == "__main__":
    main(sys.argv[1:])
