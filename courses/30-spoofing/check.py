"""Check of mission 30 — detecting GPS spoofing. Sealed: never shown to students.

Unseen inputs everywhere: hidden/expected.json (made by solutions/30-spoofing/make_expected.py) holds the inputs and
the course reference's answers for TODOs 1–5, short event sequences for TODOs 6–7, seven attacks the lab never
plays (other places, speeds, offsets, timings) with the reference guard's verdict on every GPS fix, and the lab's
own numbers read back from the lab's tools run on the reference. Checks 12 and 15 run the student's own runner
(their guard in front of mission 29's judge) and judge properties, not copies of numbers.
"""
import contextlib
import io
import json
import math
import os

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run, sh

c = Checker()
E = json.loads(hidden("expected.json"))
U, SEQ, ATT, LAB = E["units"], E["sequences"], E["attacks"], E["lab"]
DEFAULTS = {"gps_timeout_s": 3.0, "day_timeout_s": 5.0, "night_timeout_s": 5.0, "celestial_timeout_s": 45.0,
            "future_tolerance_s": 0.5, "fix_max_sigma_m": 25.0, "min_stated_sigma_m": 0.01,
            "switch_holdoff_s": 2.0, "tick_hz": 5.0, "max_speed_mps": 30.0, "gps_jump_margin_m": 50.0,
            "vehicle": "drone"}


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def spoof():
    return quiet("navera_lite.spoof")


def functions(*names):
    fns = need(spoof(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/spoof.py)")
    return fns


def answers(*names):
    return need(quiet("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")
    if not math.isfinite(x):
        raise CheckFailed(f"{name} is {x}: not a usable number")
    return x


def answer_near(name, v, want, tol, where):
    x = number(v, name)
    if x == 0.0 and want != 0.0:
        raise CheckFailed(f"{name} is still 0.0 — {where}")
    if abs(x - want) > tol:
        raise CheckFailed(f"{name} = {x:g} is not what {where} gives (it must be within ± {tol:g} of it)")


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, bool) or isinstance(v, (tuple, list, dict, str)):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


TIPS = [("math domain error", " — math.log of 0 or of a negative number, or math.sqrt of a negative: refuse "
                              "impossible inputs first (ValueError), or check the sign under the root"),
        ("division by zero", " — a = 0 (the vehicle flies at the gate's top speed): the quadratic becomes a line, "
                             "never divide by 2a there"),
        ("'NoneType'", " — a function it calls returned None: is an earlier TODO (innovation, first_alarm, "
                       "chi2_threshold_2d) still a stub?"),
        ("Singular matrix", " — S has a zero row: did you add the two covariances (and the gap term)?"),
        ("has no attribute 'cov'", " — innovation(gps, ref, cfg) takes two Estimates (gps.cov, ref.cov)"),
        ("not subscriptable", " — cfg is a dict: cfg[\"max_speed_mps\"]; an Estimate has attributes: est.lat"),
        ("unsupported operand type(s) for ^", " — in Python ^ is not a power: write x ** 2"),
        ("cannot unpack non-iterable NoneType", " — innovation() returned None (a source that states no accuracy, "
                                                "lesson §3): test for None before you unpack (d2, dist)")]


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def cfg_for(vmax=30.0):
    c0 = dict(DEFAULTS, max_speed_mps=float(vmax))
    c0.update({"p_fa": 0.01, "p_fa_far": 1e-6, "doubt_n": 2, "refuse_n": 5, "far_n": 2, "confirm_n": 2,
               "doubt_max_m": 500.0, "max_gap_s": 0.5, "ref_memory_s": 120.0})
    return c0


def make(est_mod, d):
    return est_mod.Estimate(d["source"], d["lat"], d["lon"], d["stamp_s"], cov=tuple(d["cov"]), cov_type=d["cov_type"],
                            valid=d["valid"])


def stamp(t):
    return f"t = {t:g} s"


# ======================================================================== session 1 — Statistician
@c.test("TODO 1: chi2_threshold_2d() on unseen probabilities, and refuses what is not a probability",
        hint="Lesson §2: a false alarm is an honest d² OUTSIDE the gate; mission 27's chi2_threshold(p) wants the "
             "probability INSIDE (1 − p_fa). By hand: P(d² > γ) = e^(−γ/2). Refuse p_fa ≤ 0 or ≥ 1 with a ValueError.")
def _():
    (f,) = functions("chi2_threshold_2d")
    for p, want in U["chi2"]:
        got = num(go(f, p), f"chi2_threshold_2d({p})")
        if abs(got - want) < 1e-9:
            continue
        if abs(got + 2 * math.log(1 - p)) < 1e-9:
            raise CheckFailed(f"chi2_threshold_2d({p}) = {got:.4f}: uncertainty.chi2_threshold takes the probability of "
                              "being INSIDE the gate — pass 1 − p_fa")
        if abs(got + 2 * math.log10(p)) < 1e-9:
            raise CheckFailed(f"chi2_threshold_2d({p}) = {got:.4f}: math.log10 is not ln — use math.log")
        if abs(got + math.log(p)) < 1e-9:
            raise CheckFailed(f"chi2_threshold_2d({p}) = {got:.4f}: the factor 2 is missing (P = e^(−γ/2))")
        if abs(got - 2 * math.log(p)) < 1e-9:
            raise CheckFailed(f"chi2_threshold_2d({p}) = {got:.4f} is negative: γ = −2 ln p_fa (ln of a probability "
                              "is negative)")
        if abs(got - math.sqrt(-2 * math.log(p))) < 1e-9:
            raise CheckFailed(f"chi2_threshold_2d({p}) = {got:.4f}: that is the RADIUS √γ in σ; the function "
                              "returns γ, the threshold on d²")
        raise CheckFailed(f"chi2_threshold_2d({p}) = {got:.6g} is not the threshold of lesson §2")
    for bad in (0.0, 1.0, 1.2, -0.1):
        try:
            got = run(f, bad)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise CheckFailed(f"chi2_threshold_2d({bad}) should raise ValueError, but it stopped with: {e}")
        raise CheckFailed(f"chi2_threshold_2d({bad}) returned {got!r}: {bad} is not a false-alarm probability — "
                          "raise ValueError")


@c.test("TODO 2: innovation() on unseen pairs — correlated covariances, a time gap, sources that state nothing",
        hint="Lesson §3: r = geo.enu_flat(ref.lat, ref.lon, gps.lat, gps.lon); S = [[a, b], [b, c]] of the GPS + the same of "
             "the reference + g² on the diagonal, g = max_speed_mps × |gap|; d² = uncertainty.mahalanobis2(r, S); return "
             "(d2, |r|), or None when stated_sigma() of either is None.")
def _():
    m = spoof()
    (f,) = functions("innovation")
    est = quiet("navera_lite.estimate")
    for k, case in enumerate(U["innovation"]):
        g, r = make(est, case["gps"]), make(est, case["ref"])
        got = go(f, g, r, cfg_for(case["vmax"]))
        want = case["want"]
        if want is None:
            c.ok(got is None, f"innovation(): the reference states no accuracy (covariance type "
                              f"{case['ref']['cov_type']}, numbers {case['ref']['cov'][:1]}…) — there is nothing to test "
                              f"against: return None (estimate.stated_sigma() is None), got {got!r}")
            continue
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"innovation() must return (d2, dist_m), two numbers, got {got!r}")
        d2, dist = num(got[0], "innovation()[0]"), num(got[1], "innovation()[1]")
        if abs(d2 - want[0]) <= 1e-6 * max(1.0, want[0]) and abs(dist - want[1]) < 1e-3:
            continue
        rv = np.array(case["r"])
        cg, cr = case["gps"]["cov"], case["ref"]["cov"]
        gap = abs(case["gps"]["stamp_s"] - case["ref"]["stamp_s"]) * case["vmax"]

        def d2_of(Sm):
            return float(rv @ np.linalg.solve(np.array(Sm), rv))
        Pg = [[cg[0], cg[1]], [cg[1], cg[4]]]
        Pr = [[cr[0], cr[1]], [cr[1], cr[4]]]
        variants = [
            (np.add(Pr, np.eye(2) * gap ** 2), "S misses the GPS covariance: the innovation's covariance is the SUM of both"),
            (np.add(Pg, np.eye(2) * gap ** 2), "S misses the reference's covariance"),
            (np.add(Pg, Pr), "the time-gap term is missing: add g² on the diagonal, g = max_speed_mps × |gps.stamp_s − "
                             "ref.stamp_s|" if gap > 0 else None),
            (np.add(np.add(Pg, Pr), np.eye(2) * gap), "the gap term is g, not g²: add (max_speed × |gap|)²"),
            (np.add(np.diag(np.diag(Pg)), np.diag(np.diag(Pr))) + np.eye(2) * gap ** 2,
             "the off-diagonal b terms are missing: S = [[a, b], [b, c]] of each covariance"),
            (np.add(np.add(np.sqrt(np.abs(Pg)), np.sqrt(np.abs(Pr))), np.eye(2) * gap),
             "you added σ (metres), not variances (m²): a and c are σ²"),
        ]
        for Sm, msg in variants:
            if msg and abs(d2 - d2_of(Sm)) <= 1e-6 * max(1.0, d2):
                raise CheckFailed(f"innovation(), pair {k + 1}: d² = {d2:.4f} — {msg}")
        if abs(d2 - math.sqrt(want[0])) < 1e-6 or abs(d2 - want[1] ** 2) < 1e-3:
            raise CheckFailed(f"innovation(), pair {k + 1}: d² = {d2:.4f} — return d² = rᵀ S⁻¹ r itself (not its root, "
                              "not |r|²)")
        if abs(d2 - want[0]) > 1e-6 * max(1.0, want[0]):
            raise CheckFailed(f"innovation(), pair {k + 1}: d² = {d2:.4f} is {d2 - want[0]:+.4f} off (r from the "
                              f"reference to the GPS, east and north metres; S as in lesson §3)")
        raise CheckFailed(f"innovation(), pair {k + 1}: dist_m = {dist:.3f} is not the length of r ({want[1]:.1f} m "
                          "expected to the metre)" if abs(dist - want[1]) > 1.0 else
                          f"innovation(), pair {k + 1}: dist_m = {dist:.3f} m is a little off: |r| = math.hypot(east, north)")
    del m


@c.test("TODO 3: first_alarm() — unseen series, a value equal to the threshold, n = 1, an empty series",
        hint="Lesson §4: one counter; +1 when the value is ABOVE the threshold (strictly), back to 0 otherwise; return "
             "the index when it reaches n; −1 after the loop. Refuse n < 1 with ValueError.")
def _():
    (f,) = functions("first_alarm")
    for s, g, n, want in U["first_alarm"]:
        got = go(f, list(s), g, n)
        if got == want and not isinstance(got, bool):
            continue
        if isinstance(got, bool) or not isinstance(got, int):
            raise CheckFailed(f"first_alarm should return an index (an int) or −1, got {got!r}")
        ge = next((i for i in range(len(s)) if i >= n - 1 and all(v >= g for v in s[i - n + 1:i + 1])), -1)
        if got == ge and ge != want:
            raise CheckFailed(f"first_alarm({s}, {g}, {n}) = {got}: a value EQUAL to the threshold does not "
                              "disagree (use >, not >=)")
        cnt, nr = 0, -1
        for i, v in enumerate(s):
            cnt += v > g
            if cnt >= n:
                nr = i
                break
        if got == nr:
            raise CheckFailed(f"first_alarm({s}, {g}, {n}) = {got}: your counter does not restart at 0 after a value "
                              "below the threshold — n IN A ROW")
        raise CheckFailed(f"first_alarm({s}, {g}, {n}) = {got}, not the index of the n-th disagreeing test in a row")
    for bad in (0, -2):
        try:
            got = run(f, [10.0, 11.0], 9.21, bad)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise
        raise CheckFailed(f"first_alarm(…, n={bad}) returned {got!r}: n must be at least 1 — raise ValueError")


@c.test("TODO 4: patient_accept_time() — unseen spoofers, a hovering vehicle, the a = 0 and a < 0 cases",
        hint="Lesson §1: a = v_max² − s², b = 2·v_max·m, c = m² − D². m ≥ D → 0.0; a < 0 → math.inf; a = 0 → −c/b if "
             "b > 0, else math.inf; otherwise the + root (−b + √(b² − 4ac)) / 2a.")
def _():
    (f,) = functions("patient_accept_time")
    for args, want in U["patient"]:
        got = num(go(f, *args), f"patient_accept_time{tuple(args)}")
        if want == math.inf:
            c.ok(got == math.inf, f"patient_accept_time{tuple(args)} = {got:g}: here the spoof NEVER becomes reachable "
                                  "(lesson §1's ✏️ check): return math.inf")
            continue
        if abs(got - want) <= 1e-6 * max(1.0, want):
            continue
        D, s, v, m = args
        a, b, cc = v * v - s * s, 2 * v * m, m * m - D * D
        if a > 0 and abs(got - (-b - math.sqrt(b * b - 4 * a * cc)) / (2 * a)) < 1e-6:
            raise CheckFailed(f"patient_accept_time{tuple(args)} = {got:.3f}: that is the negative root — take −b + √…")
        if a > 0 and abs(got - (math.sqrt(D * D - m * m) / math.sqrt(a))) < 1e-6:
            raise CheckFailed(f"patient_accept_time{tuple(args)} = {got:.3f}: the margin's b·Δt term is missing "
                              "(b = 2·v_max·m)")
        if want == 0.0:
            raise CheckFailed(f"patient_accept_time{tuple(args)} = {got:g}: the margin already covers the offset "
                              "(m ≥ D): reachable at once, 0.0")
        raise CheckFailed(f"patient_accept_time{tuple(args)} = {got:.4f} is {got - want:+.4f} s off")


@c.test("TODO 5: drift_alarm_time() — unseen drifts, periods and n, and a spoofer that does not move",
        hint="Lesson §4: radius = sigma_s_m·√threshold; crossing at radius / drift; the first test STRICTLY after it is "
             "(floor(t / T) + 1)·T; the n-th in a row (n − 1)·T later; math.inf when drift_mps ≤ 0.")
def _():
    (f,) = functions("drift_alarm_time")
    for args, want in U["drift"]:
        got = num(go(f, *args), f"drift_alarm_time{tuple(args)}")
        if want == math.inf:
            c.ok(got == math.inf, f"drift_alarm_time{tuple(args)} = {got:g}: a spoofer who does not move is never "
                                  "caught by this test: math.inf")
            continue
        if abs(got - want) < 1e-9:
            continue
        u, sg, g, n, T = args
        tc = sg * math.sqrt(g) / u
        k = math.floor(tc / T) + 1
        if abs(got - (k + n) * T) < 1e-9:
            raise CheckFailed(f"drift_alarm_time{tuple(args)} = {got:g}: one period too late — the first disagreeing "
                              "test is already one of the n (add (n − 1)·T)")
        if abs(got - (k - 1 + n - 1) * T) < 1e-9:
            raise CheckFailed(f"drift_alarm_time{tuple(args)} = {got:g}: you took the test just BEFORE the crossing "
                              "(the first test strictly after it is (floor(t/T) + 1)·T)")
        if abs(got - (tc + (n - 1) * T)) < 1e-9:
            raise CheckFailed(f"drift_alarm_time{tuple(args)} = {got:g}: the crossing time is not a test time — tests "
                              "happen only at 0, T, 2T…")
        if abs(got - (sg * g / u + (n - 1) * T)) < 2 * T + 1e-9 and abs(sg * g / u - tc) > T:
            raise CheckFailed(f"drift_alarm_time{tuple(args)} = {got:g}: the radius is sigma_s_m·√threshold (γ is a "
                              "threshold on d², a squared distance)")
        raise CheckFailed(f"drift_alarm_time{tuple(args)} = {got:g}, not the alarm time of lesson §4's worked steps")


@c.test("Session 1 answers (Steps 0–4): the judge alone, your test's promise, the jump gate's hole, the drift delay",
        hint="Copy the numbers from the runs of Steps 0, 2 and 3 (the summary lines and the changes printed), and your own "
             "functions for PATIENT_THEORY_DT_S and DRIFT_THEORY_S. The EXPLAIN items: one to three sentences each.")
def _():
    a = answers("PREDICT_NOGUARD", "NOGUARD_MAX_ERROR_M", "PREDICT_STATS", "STATS_SHARE_1PC", "MEAN_D2",
                "EXPLAIN_STATS", "PREDICT_PATIENT", "PATIENT_THEORY_DT_S", "PATIENT_FLOWN_T_S", "VMAX100_FLOWN_T_S",
                "EXPLAIN_PATIENT", "DRIFT_THEORY_S")
    (pn, noguard, ps, share, mean, ex_stats, pp, th, flown, v100, ex_pat, drift) = a
    predicted("PREDICT_NOGUARD", pn)
    answer_near("NOGUARD_MAX_ERROR_M", noguard, LAB["noguard_max_error_m"], 3.0,
                "`python3 spoof_run.py drift --no-guard` (the summary's largest error)")
    predicted("PREDICT_STATS", ps)
    x = number(share, "STATS_SHARE_1PC")
    if abs(x - 1.0) < 1e-9 or abs(x - 0.01) < 1e-9:
        raise CheckFailed("STATS_SHARE_1PC is the theory (0.01). Copy the MEASURED share printed by "
                          "`python3 spoof_run.py stats` for p_fa 0.01")
    if 0.5 < x < 1.5:
        raise CheckFailed("STATS_SHARE_1PC looks like a percentage: write the share as a number like 0.0123")
    answer_near("STATS_SHARE_1PC", x, LAB["stats_share_1pc"], 0.0004, "`python3 spoof_run.py stats` (p_fa 0.01)")
    answer_near("MEAN_D2", mean, LAB["mean_d2"], 0.005, "`python3 spoof_run.py stats` (the mean d²)")
    explained("EXPLAIN_STATS", ex_stats,
              ([r"gap", r"0\.1", r"time", r"v_?max", r"speed", r"mov", r"flew", r"fly"], "the time-gap term in S"),
              ([r"\bs\b", r"covariance", r"varian", r"bigger", r"larger", r"too (big|large|much)", r"pessimis",
                r"conservati", r"over"], "what that term does to S and to d² (honest pairs that did not move)"))
    predicted("PREDICT_PATIENT", pp)
    answer_near("PATIENT_THEORY_DT_S", th, LAB["patient_theory_dt_s"], 0.05,
                "your patient_accept_time(2000.0, 15.0, 30.0, 50.0)")
    fl = number(flown, "PATIENT_FLOWN_T_S")
    if abs(fl - LAB["patient_theory_dt_s"]) < 1.0:
        raise CheckFailed("PATIENT_FLOWN_T_S is the theory's Δt: copy the TIME of the run's line where the judge starts "
                          "flying on the GPS with an error near 2 000 m (`python3 spoof_run.py patient --no-guard`)")
    answer_near("PATIENT_FLOWN_T_S", fl, LAB["patient_flown_t_s"], 0.6,
                "`python3 spoof_run.py patient --no-guard` (the line where the judge flies the GPS, error ≈ 2 000 m)")
    answer_near("VMAX100_FLOWN_T_S", v100, LAB["vmax100_flown_t_s"], 0.6,
                "`python3 spoof_run.py patient --no-guard --vmax 100.0`")
    explained("EXPLAIN_PATIENT", ex_pat,
              ([r"19", r"last trusted", r"trusted fix", r"9[34]", r"74", r"75"], "theory against the run (the last "
               "trusted fix at t = 19 s, + Δt)"),
              ([r"hold", r"2 ?s", r"switch", r"whole", r"next fix", r"second"], "why the run is a few seconds later "
               "(the next whole-second fix, the judge's hold-off)"),
              ([r"120", r"true gps", r"real gps", r"honest", r"lock", r"refus", r"jump"], "what happened to the true GPS "
               "at t = 120 s"),
              ([r"100", r"top speed", r"max(imum)? speed", r"v_?max", r"generous", r"faster", r"sooner", r"earlier",
                r"vehicle"], "what a generous top speed does to the hole"))
    answer_near("DRIFT_THEORY_S", drift, LAB["drift_theory_s"], 0.01,
                "your drift_alarm_time(4.0, 243 ** 0.5, chi2_threshold_2d(0.01), 5, 2.0)")


def roc_ref(z0, z1, g, n, T):
    def first(z):
        run_ = 0
        for i, v in enumerate(z):
            run_ = run_ + 1 if v > g else 0
            if run_ >= n:
                return i
        return -1
    a0 = [first(z) for z in z0]
    a1 = [first(z) for z in z1]
    hits = [i for i in a1 if i >= 0]
    return {"p_fa": sum(i >= 0 for i in a0) / len(a0), "p_d": len(hits) / len(a1),
            "delay_s": T * sum(hits) / len(hits) if hits else None}


@c.test("TODO 8: roc_point() on unseen simulated flights (other sizes, thresholds and periods)",
        hint="For each flight (each row), first_alarm(row, threshold, n); P_FA = share of honest rows with an alarm (≥ 0), "
             "P_D = the same on the spoofed rows, delay_s = mean of index × period_s over the spoofed rows WITH an "
             "alarm (None if none).")
def _():
    det = quiet("detection.py")
    (f,) = need(det, "roc_point")
    if is_stub(f):
        raise CheckFailed("roc_point() is not written yet (TODO 8 in detection.py)")
    functions("first_alarm")
    rng = np.random.default_rng(3008)
    for k, (fl, tests, g, n, T) in enumerate(((40, 25, 9.21, 2, 2.0), (30, 12, 5.99, 3, 1.0), (25, 30, 13.8, 1, 0.5),
                                              (20, 8, 40.0, 5, 2.0), (2, 3, 9.21, 1, 2.0))):
        z0 = rng.chisquare(2, (fl, tests))
        z1 = rng.chisquare(2, (fl, tests)) * np.linspace(1, 8, tests)
        if k == 4:                                       # alarms at the very first test (index 0, delay 0.0 s)
            z0, z1 = np.array([[50.0, 1.0, 1.0], [1.0, 1.0, 1.0]]), np.array([[60.0, 1.0, 1.0], [1.0, 70.0, 1.0]])
        got = go(f, z0, z1, g, n, T)
        if not isinstance(got, dict) or not {"p_fa", "p_d", "delay_s"} <= set(got):
            raise CheckFailed(f"roc_point() must return a dict with p_fa, p_d and delay_s, got {got!r}")
        want = roc_ref(z0, z1, g, n, T)
        if abs(num(got["p_fa"], "roc_point p_fa") - want["p_fa"]) > 1e-9:
            if k == 4:
                raise CheckFailed("roc_point: an alarm at the very FIRST test (first_alarm returns 0) is an alarm too: "
                                  "count the results ≥ 0, not > 0")
            if abs(got["p_fa"] - want["p_d"]) < 1e-9:
                raise CheckFailed("roc_point: p_fa and p_d are swapped (p_fa comes from the HONEST flights, d2_h0)")
            raise CheckFailed(f"roc_point case {k + 1}: p_fa = {got['p_fa']:.4f} is not the share of honest flights with an alarm")
        c.ok(abs(num(got["p_d"], "roc_point p_d") - want["p_d"]) < 1e-9,
             f"roc_point case {k + 1}: p_d = {got['p_d']:.4f} is not the share of spoofed flights with an alarm")
        if want["delay_s"] is None:
            c.ok(got["delay_s"] is None, f"roc_point case {k + 1}: no spoofed flight has an alarm, so delay_s must be "
                                         f"None, got {got['delay_s']!r}")
            continue
        d = num(got["delay_s"], "roc_point delay_s")
        if abs(d - want["delay_s"] / T) < 1e-9 and T != 1.0:
            raise CheckFailed("roc_point: delay_s is the mean INDEX — multiply by period_s to get seconds")
        c.ok(abs(d - want["delay_s"]) < 1e-9, f"roc_point case {k + 1}: delay_s = {d:.4f} s — the mean over the spoofed "
                                              "flights that HAVE an alarm only (index × period_s)")


@c.test("results.json: your ROC table, your operating point (TODO 9) and the Step 6 answers",
        hint="Run `python3 detection.py` again after setting CHOSEN_P and CHOSEN_N: the rule with P_FA ≤ 0.01 and the "
             "highest P_D in YOUR table. NAVERA_RULE_PD: the row p 0.01, n 5. CORRELATED_PFA: results.json → correlated, "
             "the rule (0.05, 3), p_fa_rho_0.9.")
def _():
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet: run `python3 detection.py` (Step 5)")
    try:
        res = json.load(open("results.json"))
    except ValueError:
        raise CheckFailed("results.json is not valid JSON: run `python3 detection.py` again, do not edit it")
    rows = {(r.get("p"), r.get("n")): r for r in res.get("roc", [])}
    for w in LAB["roc"]:
        r = rows.get((w["p"], w["n"]))
        if r is None:
            raise CheckFailed(f"results.json has no row p {w['p']}, n {w['n']}: run `python3 detection.py` again")
        for key in ("p_fa", "p_d", "delay_s"):
            if (r.get(key) is None) != (w[key] is None) or (w[key] is not None and abs(r[key] - w[key]) > 1e-5):
                raise CheckFailed(f"results.json, rule p {w['p']} n {w['n']}: {key} = {r.get(key)} is not what the "
                                  "simulation gives with a correct roc_point/first_alarm — fix them, then run "
                                  "`python3 detection.py` again")
    ch = res.get("chosen") or {}
    best = LAB["best"]
    if (ch.get("p"), ch.get("n")) == (0.2, 1):
        raise CheckFailed("CHOSEN_P and CHOSEN_N are still the starter's (0.2, 1): choose your operating point (TODO 9), "
                          "then run `python3 detection.py` again")
    if (ch.get("p"), ch.get("n")) != (best["p"], best["n"]):
        r = rows.get((ch.get("p"), ch.get("n")))
        if r is None:
            raise CheckFailed(f"your operating point (p {ch.get('p')}, n {ch.get('n')}) is not a rule of the grid "
                              "(P_GRID × N_GRID)")
        if r["p_fa"] > 0.01:
            raise CheckFailed(f"your operating point has P_FA {r['p_fa']} > 0.01: it breaks the requirement (MAX_PFA)")
        raise CheckFailed(f"your operating point (p {ch['p']}, n {ch['n']}) meets the requirement, but another rule "
                          "has a higher P_D: look again at every row with P_FA ≤ 0.01")
    a = answers("NAVERA_RULE_PD", "CORRELATED_PFA", "EXPLAIN_ROC", "EXPLAIN_CORRELATED")
    answer_near("NAVERA_RULE_PD", a[0], LAB["navera_rule_pd"], 0.0005, "your table (p 0.01, n 5)")
    x = number(a[1], "CORRELATED_PFA")
    if abs(x - next(r["p_fa_independent"] for r in LAB["correlated"] if r["p"] == 0.05)) < 1e-9:
        raise CheckFailed("CORRELATED_PFA is the INDEPENDENT value: copy p_fa_rho_0.9 of the rule (0.05, 3)")
    answer_near("CORRELATED_PFA", x, LAB["correlated_pfa"], 0.0005, "results.json → correlated, (0.05, 3), p_fa_rho_0.9")
    explained("EXPLAIN_ROC", a[2],
              ([r"p_?d", r"detect", r"catch", r"caught", r"miss"], "what your rule gains (P_D)"),
              ([r"hour", r"long", r"1 ?800", r"more tests", r"many tests", r"flight", r"per flight", r"conservativ",
                r"false alarm"], "why NAVERA's stricter rule makes sense for long flights (false alarms per flight)"))
    explained("EXPLAIN_CORRELATED", a[3],
              ([r"correlat", r"same error", r"persist", r"last", r"several", r"repeat", r"independ", r"rho", r"ρ"],
               "why correlated errors make streaks likely"),
              ([r"p_?fa\^?n", r"power", r"multipl", r"product", r"one event", r"single", r"independen", r"assum"],
               "which assumption of P_FA^n breaks"))


# ======================================================================== session 2 — Guardian
def guard_for(m, vmax=30.0):
    return m.SpoofGuard(cfg_for(vmax))


def play_sequence(m, est, name):
    g = guard_for(m)
    for k, st in enumerate(SEQ[name]):
        e = make(est, st["est"])
        src, t = st["est"]["source"], st["est"]["stamp_s"]
        if src == "gps":
            got = go(g.check, e)
        else:
            got = go(g.on_reference, e)
        state, rby = g.state, g.refused_by
        yield k, src, t, st, got, state, rby, g


@c.test("TODO 6: SpoofGuard.on_reference() — the tests, the counters, IN_DOUBT, REFUSED (drift, far), confirmation",
        hint="Its docstring's rules, in that order. A reference that states nothing, or with no GPS fix within max_gap_s, "
             "returns None (but a stated one sets last_ref_s first). d² > gamma: disagree +1, agree 0; far +1 only "
             "while d² > gamma_far; else disagree 0, far 0, agree +1. Return d².")
def _():
    m = spoof()
    if is_stub(m.SpoofGuard.on_reference):
        raise CheckFailed("SpoofGuard.on_reference() is not written yet (TODO 6)")
    functions("innovation", "chi2_threshold_2d")
    est = quiet("navera_lite.estimate")
    for name in ("crosscheck", "far", "doubt_max"):
        n_ref = 0
        for k, src, t, st, got, state, rby, g in play_sequence(m, est, name):
            if src == "gps":
                continue
            n_ref += 1
            where = f"sequence '{name}', reference fix at {stamp(t)}"
            if st["ret"] is None:
                c.ok(got is None, f"{where}: no test is possible here "
                                  + ("(it states no accuracy)" if st["est"]["cov_type"] == 0 else
                                     "(no GPS fix within max_gap_s of its stamp)") + f" — return None, got {got!r}")
                if st["last_ref_s"] is not None:
                    c.ok(g.last_ref_s is not None and abs(g.last_ref_s - st["last_ref_s"]) < 1e-9,
                         f"{where}: a reference that STATES an accuracy must set self.last_ref_s = its stamp, even "
                         f"when no GPS fix is close enough to test (last_ref_s is {g.last_ref_s!r})")
                continue
            if got is None:
                raise CheckFailed(f"{where}: on_reference returned None — a test happened here: return d²")
            if abs(num(got, "on_reference()") - st["ret"]) > 1e-6 * max(1.0, st["ret"]):
                raise CheckFailed(f"{where}: on_reference returned {got:.3f}, not this test's d² (innovation of the GPS "
                                  "fix closest in time, self.closest_gps)")
            counters = (g.disagree, g.far, g.agree)
            want_c = (st["disagree"], st["far"], st["agree"])
            if state != st["state"] or rby != st["refused_by"]:
                raise CheckFailed(f"{where} (d² {st['ret']:.1f}; disagree/far/agree should now be {want_c}): your guard "
                                  f"is {state} (refused_by {rby!r}), expected {st['state']} (refused_by "
                                  f"{st['refused_by']!r}) — the docstring's rules, first one that applies")
            if counters != want_c:
                raise CheckFailed(f"{where} (d² {st['ret']:.1f}): disagree/far/agree = {counters}, expected {want_c} — "
                                  "a result of the other kind restarts a counter at 0; far counts only d² > gamma_far")
            if st["state"] == "IN_DOUBT" and abs(g.doubt_m - st["doubt_m"]) > 0.01:
                raise CheckFailed(f"{where}: IN_DOUBT but self.doubt_m = {g.doubt_m:.1f}: set it to the gap (dist_m)")
            if st["state"] == "TRUSTED" and k > 0 and SEQ[name][k - 1]["state"] == "REFUSED":
                gt = g.gate.trusted
                c.ok(gt is not None and abs(gt.stamp_s - st["gate_trusted_s"]) < 1e-9,
                     f"{where}: the GPS is confirmed, so the GPS fix you tested must become the jump gate's trusted fix "
                     "(self.gate.trusted)")
        c.ok(n_ref > 0, "internal: empty sequence")


@c.test("TODO 7: SpoofGuard.on_gps() — first fix, jump, outage (with and without a reference), memory, re-acceptance",
        hint="Its docstring's five rules, in order: first fix → gate → TRUSTED; outage (> gps_timeout_s) while not REFUSED "
             "and has_reference → REFUSED 'outage'; REFUSED + reference → stay; REFUSED + no reference → the gate decides; "
             "else the gate: a jump → REFUSED 'jump', otherwise no change. Return what set_state returns.")
def _():
    m = spoof()
    if is_stub(m.SpoofGuard.on_gps):
        raise CheckFailed("SpoofGuard.on_gps() is not written yet (TODO 7)")
    if is_stub(m.SpoofGuard.on_reference):
        raise CheckFailed("write TODO 6 (on_reference) first: these sequences need it")
    est = quiet("navera_lite.estimate")
    for name in ("on_gps", "outage_noref", "outage_ref"):
        prev = "TRUSTED"
        for k, src, t, st, got, state, rby, g in play_sequence(m, est, name):
            where = f"sequence '{name}', {'GPS' if src == 'gps' else 'reference'} fix at {stamp(t)}"
            if src == "gps":
                if not (isinstance(got, (tuple, list)) and len(got) == 2 and isinstance(got[0], str)):
                    raise CheckFailed(f"{where}: check() returned {got!r} — on_gps must return (state, reason), what "
                                      "self.set_state(...) returns (or self.state, self.reason when nothing changes)")
                if got[0] != state:
                    raise CheckFailed(f"{where}: on_gps returned {got[0]!r} but self.state is {state!r}: change the "
                                      "state with self.set_state(...) and return what it returns")
            if state != st["state"] or rby != st["refused_by"]:
                rule = {("TRUSTED", "REFUSED", "outage"): " (rule 2: back after an outage while a stated reference was "
                                                          "heard)",
                        ("REFUSED", "TRUSTED", None): " (rule 3 or 4: is a stated reference heard within ref_memory_s?)",
                        ("REFUSED", "REFUSED", "jump"): " (rule 3/4: without a reference the jump gate decides)"}
                tip = rule.get((prev, st["state"], st["refused_by"]), "")
                raise CheckFailed(f"{where}: your guard is {state} (refused_by {rby!r}), expected {st['state']} "
                                  f"(refused_by {st['refused_by']!r}){tip}")
            prev = state


@c.test("Your guard on seven attacks you have not seen (other places, speeds, offsets, photo timings, top speeds)",
        hint="Every GPS fix gets the verdict the course's guard gives. Read the first difference: the time, the offset, "
             "the expected verdict; replay the lab's attacks (python3 spoof_run.py all) and compare with lesson §5's table.")
def _():
    m = spoof()
    for meth in ("on_reference", "on_gps"):
        if is_stub(getattr(m.SpoofGuard, meth)):
            raise CheckFailed(f"SpoofGuard.{meth}() is not written yet")
    for f in ("innovation", "chi2_threshold_2d"):
        functions(f)
    est = quiet("navera_lite.estimate")
    for name, att in ATT.items():
        g = guard_for(m, att["vmax"])
        for row in att["rows"]:
            e = make(est, row["est"])
            got = go(g.check, e)
            if row["verdict"] is None:
                continue
            v = got[0] if isinstance(got, (tuple, list)) and got else got
            if v != row["verdict"]:
                t = row["est"]["stamp_s"]
                raise CheckFailed(f"attack '{name}': the GPS fix at {stamp(t)} (spoofer's offset {row['offset_m']:.0f} m) "
                                  f"gets {v!r} from your guard (reason: {g.reason!r}); the course's guard says "
                                  f"{row['verdict']!r}")


def runs():
    try:
        return json.load(open("runs.json"))
    except (OSError, ValueError):
        raise CheckFailed("runs.json is missing or broken: run `python3 spoof_run.py all`")


@c.test("Your guard in front of mission 29's judge: the lab's attacks with and without it",
        hint="`python3 spoof_run.py all` must run to the end. With your guard: the patient spoofer (vision σ 15 m) and jam-then-"
             "spoof never fly; the drift is caught below 100 m; two wrong vision matches never refuse an honest GPS.")
def _():
    if not os.path.exists(os.path.join("navera_lite", "arbiter.py")):
        raise CheckFailed("navera_lite/arbiter.py (mission 29's judge) is missing in this folder: tell your teacher")
    code, out = sh("python3 spoof_run.py all", timeout=150)
    if code != 0:
        raise CheckFailed("`python3 spoof_run.py all` stopped:\n" + out[-600:])
    R = runs()
    for k in ("drift", "drift__noguard", "patient_vision", "jamspoof", "glitch", "jump"):
        if k not in R:
            raise CheckFailed(f"runs.json has no run '{k}': run `python3 spoof_run.py all` again")
    c.ok(R["drift__noguard"]["max_error_m"] > 250, "without the guard, the drift should pull the judge far away "
                                                   "(> 250 m): is spoof_run.py or scenarios.py changed?")
    c.ok(R["drift"]["max_error_m"] < 100, f"with your guard the drift still pulls the judge {R['drift']['max_error_m']:.0f} m "
                                          "away: the guard should refuse it below 100 m")
    for k in ("patient_vision", "jamspoof"):
        c.ok(R[k]["judge_flew_spoofed"] == 0, f"'{k}': the judge flew {R[k]['judge_flew_spoofed']} s on spoofed GPS "
                                              "fixes although vision states its accuracy: the guard must refuse them all")
    c.ok(R["glitch"]["first"]["REFUSED"] is None and R["glitch"]["first"]["IN_DOUBT"] is None
         and all(r["verdict"] == "TRUSTED" for r in R["glitch"]["timeline"]),
         "'glitch': an honest GPS was refused or put in doubt because of single wrong vision matches — one fix is not evidence")
    c.ok(R["jump"]["first"]["REFUSED"] is not None, "'jump': the 2 km jump must be refused by the jump gate")


@c.test("Session 2 answers (Steps 8–9): the drift against your guard, and what still gets through",
        hint="DRIFT_DOUBT_OFFSET_M and DRIFT_REFUSED_OFFSET_M are the summary lines of `python3 spoof_run.py drift`. "
             "EXPLAIN_LIMITS: look at the attacks the table shows as never refused.")
def _():
    a = answers("PREDICT_GUARD_DRIFT", "DRIFT_DOUBT_OFFSET_M", "DRIFT_REFUSED_OFFSET_M", "EXPLAIN_DRIFT", "EXPLAIN_LIMITS")
    predicted("PREDICT_GUARD_DRIFT", a[0])
    d, r = number(a[1], "DRIFT_DOUBT_OFFSET_M"), number(a[2], "DRIFT_REFUSED_OFFSET_M")
    if abs(d - LAB["drift_refused_offset_m"]) < 0.6 and abs(r - LAB["drift_doubt_offset_m"]) < 0.6:
        raise CheckFailed("DRIFT_DOUBT_OFFSET_M and DRIFT_REFUSED_OFFSET_M are swapped (the doubt comes first)")
    answer_near("DRIFT_DOUBT_OFFSET_M", d, LAB["drift_doubt_offset_m"], 0.6, "`python3 spoof_run.py drift` (first IN_DOUBT)")
    answer_near("DRIFT_REFUSED_OFFSET_M", r, LAB["drift_refused_offset_m"], 0.6,
                "`python3 spoof_run.py drift` (first REFUSED)")
    explained("EXPLAIN_DRIFT", a[3],
              ([r"20", r"30", r"31", r"80", r"predict", r"theory", r"drift_alarm_time"], "the comparison with your "
               "prediction (DRIFT_THEORY_S)"),
              ([r"noise", r"next (gps )?fix", r"one second", r"1 ?s", r"vision", r"arriv", r"latenc", r"random"],
               "why the run differs a little (noise, the next GPS fix)"),
              ([r"day", r"vision", r"judge", r"fl(y|ies|ew)"], "who flies after the refusal"))
    explained("EXPLAIN_LIMITS", a[4],
              ([r"novision", r"no vision", r"unknown", r"without", r"no (stated|reference|independent)", r"not stat",
                r"accuracy"], "what the attacks that still win have in common (no reference of stated accuracy)"),
              ([r"patient", r"drift", r"jam", r"creep", r"slow"], "which attacks"))


@c.test("Live over ROS 2: ros_drift.json from your guard_node run (Step 10)",
        hint="Start `python3 guard_node.py --ros-args --params-file navera_lite.yaml -p max_speed_mps:=30.0 &`, wait 2 s, run "
             "`python3 spoof_run.py drift --ros` to the end (45 s), then `kill %1`. ROS_REFUSED_T_S: the t of the first "
             "change with gps_guard REFUSED in ros_drift.json.")
def _():
    if not os.path.exists("ros_drift.json"):
        raise CheckFailed("ros_drift.json does not exist yet: do Step 10 (the live run)")
    try:
        d = json.load(open("ros_drift.json"))
    except ValueError:
        raise CheckFailed("ros_drift.json is not valid JSON: run the live attack again")
    if not d.get("live") or not isinstance(d.get("changes"), list):
        raise CheckFailed("ros_drift.json does not come from `python3 spoof_run.py drift --ros`: run it again")
    dom = os.environ.get("ROS_DOMAIN_ID")
    if dom and d.get("domain") not in (None, dom):
        raise CheckFailed("ros_drift.json was recorded on another ROS domain: run the live attack again here")
    ch = d["changes"]
    doubt = next((x for x in ch if x.get("gps_guard") == "IN_DOUBT"), None)
    ref = next((x for x in ch if x.get("gps_guard") == "REFUSED"), None)
    if ref is None:
        raise CheckFailed("ros_drift.json has no change with gps_guard REFUSED: let the live run go to the end (45 s); "
                          "was guard_node.py started with -p max_speed_mps:=30.0?")
    c.ok(doubt is not None and doubt["t"] < ref["t"], "ros_drift.json: the guard should be IN_DOUBT before it is REFUSED")
    want_t = LAB["drift_refused_t_s"] - 0.4
    c.ok(abs(ref["t"] - want_t) <= 1.6, f"ros_drift.json: the live refusal came at t = {ref['t']:.1f} s, far from the "
                                        "offline run (Step 8): was the node started with the lab's settings, and nothing "
                                        "else publishing (one judge only)?")
    c.ok(any(x.get("source") == "day" and x["t"] >= ref["t"] for x in ch),
         "ros_drift.json: after the refusal the judge should fly on day vision: did the run end too early?")
    (rt,) = answers("ROS_REFUSED_T_S")
    answer_near("ROS_REFUSED_T_S", rt, ref["t"], 0.15, "ros_drift.json (the first change with gps_guard REFUSED)")


@c.test("Red team: the largest creep offset your guard never refuses (Step 11)",
        hint="Try `python3 spoof_run.py creep --creep X` for several X: look at 'first REFUSED' in the summary. Narrow the "
             "interval until the two values differ by 2 m or less. Compare with the test's radius √(9.21 · 243) m.")
def _():
    (x, ex) = answers("CREEP_MAX_M", "EXPLAIN_CREEP")
    x = number(x, "CREEP_MAX_M")
    if x <= 0:
        raise CheckFailed("CREEP_MAX_M is still 0.0: do Step 11")
    if not 20.0 <= x <= 100.0:
        raise CheckFailed(f"CREEP_MAX_M = {x:g} m: look again, the answer is a few tens of metres")
    for value, must_refuse in ((x, False), (x + 2.0, True)):
        code, out = sh(f"python3 spoof_run.py creep --creep {value:.3f}", timeout=90)
        if code != 0:
            raise CheckFailed("`python3 spoof_run.py creep` stopped:\n" + out[-500:])
        refused = runs().get("creep", {}).get("first", {}).get("REFUSED") is not None
        if refused != must_refuse:
            raise CheckFailed(f"with --creep {value:g} your guard {'REFUSES' if refused else 'never refuses'} the GPS: "
                              + ("CREEP_MAX_M is too large" if not must_refuse else
                                 "CREEP_MAX_M is too small — find it to within 2 m"))
    explained("EXPLAIN_CREEP", ex,
              ([r"radius", r"threshold", r"γ", r"gamma", r"√", r"sqrt", r"47", r"bound", r"inside", r"below", r"under"],
               "why such an offset exists (it stays inside the test's radius)"),
              ([r"σ", r"sigma", r"accura", r"vision", r"reference", r"more (tests|fixes)", r"better", r"smaller",
                r"cusum", r"average", r"mean", r"bias"], "what would make it smaller"))


c.milestone("statistician", "TODO 1", "TODO 2", "TODO 3", "TODO 4", "TODO 5", "Session 1", "TODO 8", "results.json",
            label="Statistician")
c.milestone("guardian", "", label="Guardian")
c.run()
