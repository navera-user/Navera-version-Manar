"""Check of mission 27 — how sure are we? Covariance, gating and fusion. Sealed: never shown to students.

Unseen inputs everywhere. Expected values come from the course reference on hidden inputs (hidden/expected.json, made
by solutions/27-uncertainty/make_expected.py); the student's gate + fuse are also flown on a hidden drive
(hidden/drive.csv, a street at −25° instead of the lab's 40°). The lab's numbers (expected.json "lab") are what
run_uncertainty.py prints with the reference; solutions/27-uncertainty/TEACHER.md lists them. Wrong-but-plausible
variants are recomputed here only to NAME the mistake.
"""
import contextlib
import csv
import io
import json
import math
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()
E = json.loads(hidden("expected.json"))
LAB = E["lab"]
FILE = "navera_lite/uncertainty.py"


def un():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.uncertainty", fresh=True)


def functions(*names, mod=None, file=FILE):
    fns = need(mod or un(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in {file})")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


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


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "matmul" in msg or "aligned" in msg or "core dimension" in msg:
            raise CheckFailed(msg + " — two shapes do not fit in a matrix product: print the .shape of each side "
                                    "(a missing .T?)")
        if "Singular matrix" in msg:
            raise CheckFailed(msg + " — a matrix you invert has no inverse: is it the right one?")
        if "math domain error" in msg:
            raise CheckFailed(msg + " — a square root of a tiny negative number (−1e-15 from rounding): max(λ, 0.0) "
                                    "first")
        if "'NoneType'" in msg:
            raise CheckFailed(msg + " — a function it calls returned None: is an earlier TODO still a stub?")
        raise


def as_array(v, what, shape=None):
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should be numbers (a numpy array), got {v!r}")
    if shape is not None and a.shape != tuple(shape):
        raise CheckFailed(f"{what} should have shape {tuple(shape)}, got {a.shape}")
    return a


def polar_variant(r, b, sr, sb, deg=False, squared=True, r_factor=True, transpose=True):
    """A wrong-but-plausible J P Jᵀ of polar_to_en, only to NAME a student's mistake."""
    be = math.radians(b)
    s = sb if deg else math.radians(sb)
    k = r if r_factor else 1.0
    J = np.array([[math.sin(be), k * math.cos(be)], [math.cos(be), -k * math.sin(be)]])
    Pp = np.diag([sr ** 2, s ** 2] if squared else [sr, s])
    return J @ Pp @ (J.T if transpose else J)


def pair(v, what):
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        raise CheckFailed(f"{what} should return two things, got {v!r}")
    return v


def same(a, b, tol):
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), atol=tol, rtol=0)


# ======================================================================== session 1 — Ellipse maker
@c.test("TODO 1: sample_cov() on unseen clouds (5, 7 and 40 points, one far from the origin)",
        hint="Lesson §1: subtract the mean point (x.mean(axis=0)), then d.T @ d / (N − 1). Fewer than 2 points: raise "
             "ValueError.")
def _():
    (f,) = functions("sample_cov")
    for pts, want in E["sample_cov"]:
        x = np.array(pts)
        got = as_array(go(f, x), f"sample_cov of {len(x)} points", (2, 2))
        if same(got, want, 1e-6):
            continue
        n = len(x)
        if same(got, np.array(want) * (n - 1) / n, 1e-6):
            raise CheckFailed(f"sample_cov of {n} points: you divided by N; the lesson divides by N − 1")
        raw = x.T @ x / (n - 1)
        if same(got, raw, 1e-6) or same(got, x.T @ x / n, 1e-6):
            raise CheckFailed(f"sample_cov of {n} points far from (0, 0): the mean point is not subtracted")
        if same(got, np.diag(np.diag(want)), 1e-6):
            raise CheckFailed("the off-diagonal term (the covariance b) is missing")
        raise CheckFailed(f"sample_cov of {n} points gives {np.round(got, 3).tolist()}: wrong values")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            v = f(np.array([[1.0, 2.0]]))
    except ValueError:
        return
    except Exception as e:
        raise CheckFailed(f"sample_cov of ONE point should raise ValueError, it raised {type(e).__name__}: {e}")
    raise CheckFailed(f"sample_cov of ONE point should raise ValueError (N − 1 = 0), it returned {v!r}")


@c.test("TODO 2: ellipse() on unseen covariances — tilted, k > 1, long axis north, round, errors on a line",
        hint="Lesson §2 🧰: λ = (a + c)/2 ± √(((a − c)/2)² + b²), semi-axes k·√λ (metres, not m²), angle ½·atan2(2b, a − c) "
             "in degrees from EAST towards north, in (−90, 90]; a round ellipse has angle 0.0; max(λ, 0.0) before the root.")
def _():
    (f,) = functions("ellipse")
    for P, k, want in E["ellipse"]:
        got = go(f, np.array(P), k=k)
        if not (isinstance(got, (tuple, list)) and len(got) == 3):
            raise CheckFailed(f"ellipse should return three numbers (a_m, b_m, angle_deg), got {got!r}")
        a, b, ang = (float(x) for x in got)
        wa, wb, wang = want
        tag = f"ellipse({P}, k={k:g})"
        if not all(math.isfinite(x) for x in (a, b, ang)):
            raise CheckFailed(f"{tag} returned {got!r}: nan — a square root of a tiny negative λ? max(λ, 0.0) first")
        if abs(a - wb) < 1e-6 and abs(b - wa) < 1e-6 and wa != wb:
            raise CheckFailed(f"{tag}: a and b are swapped — a is the LONG semi-axis")
        if abs(a - wa * wa / k) < 1e-6 * max(1, wa * wa) and wa > 1.5:
            raise CheckFailed(f"{tag}: a = {a:.4g} looks like a variance (m²): the semi-axis is the SQUARE ROOT of λ")
        if k != 1 and abs(a - wa / k) < 1e-6:
            raise CheckFailed(f"{tag}: k is ignored — the k-sigma ellipse is k times larger")
        if k != 1 and abs(a - wa * k) < 1e-6 * max(1, wa):
            raise CheckFailed(f"{tag}: k is applied twice (or to λ): the semi-axes are k·√λ")
        c.ok(abs(a - wa) < 1e-6 and abs(b - wb) < 1e-6, f"{tag}: semi-axes ({a:.4f}, {b:.4f}) are wrong")
        if wa - wb < 1e-9:
            c.ok(abs(ang) < 1e-6, f"{tag} is round: its angle must be 0.0 (the convention), got {ang:.3f}")
            continue
        if abs(ang - wang) < 1e-4:
            continue
        if abs(ang - math.radians(wang)) < 1e-6 and abs(wang) > 1:
            raise CheckFailed(f"{tag}: the angle is in radians — the interface uses degrees")
        if abs(ang + 90.0) < 1e-6 and abs(wang - 90.0) < 1e-6:
            raise CheckFailed(f"{tag}: the angle is −90°: the same line as 90°, but the range is (−90, 90] — add 180°")
        d = (ang - wang + 90.0) % 180.0 - 90.0
        if abs(d) < 1e-4 and not -90.0 < ang <= 90.0:
            raise CheckFailed(f"{tag}: angle {ang:.2f}° is the right line but outside (−90, 90]: add or remove 180°")
        if abs(((90.0 - ang) - wang + 90.0) % 180.0 - 90.0) < 1e-4:
            raise CheckFailed(f"{tag}: the angle is measured from NORTH (a bearing); here it is from EAST towards north")
        if abs(((ang + 90.0) - wang + 90.0) % 180.0 - 90.0) < 1e-4:
            raise CheckFailed(f"{tag}: the angle is the SHORT axis' — use the eigenvector of the LARGEST eigenvalue")
        raise CheckFailed(f"{tag}: angle {ang:.3f}° is wrong")


@c.test("TODO 3: mahalanobis2() on unseen vectors — correlated covariances, and one 3-D case",
        hint="Lesson §3: d² = rᵀ S⁻¹ r (np.linalg.solve(S, r) gives S⁻¹ r without inverting S); return d², not d, as a "
             "float. Write it for any number of dimensions (numpy), not a 2-D formula.")
def _():
    (f,) = functions("mahalanobis2")
    for r, S, want in E["mahalanobis2"]:
        got = go(f, np.array(r), np.array(S))
        if isinstance(got, (tuple, list)) or np.ndim(got) != 0:
            raise CheckFailed(f"mahalanobis2 should return one number, got {got!r}")
        g = float(got)
        rr, SS = np.array(r), np.array(S)
        if abs(g - math.sqrt(want)) < 1e-6:
            raise CheckFailed("mahalanobis2 returns d, the square root: the function returns d² (no root)")
        if abs(g - float(rr @ SS @ rr)) < 1e-6:
            raise CheckFailed("mahalanobis2 uses S, not S⁻¹: rᵀ S⁻¹ r (np.linalg.solve(S, r))")
        if abs(g - float(np.sum(rr ** 2 / np.diag(SS)))) < 1e-6:
            raise CheckFailed("mahalanobis2 divides by the diagonal only: the off-diagonal terms of S count too "
                              "(use np.linalg.solve(S, r))")
        c.ok(abs(g - want) < 1e-6 * max(1.0, want), f"mahalanobis2({r}, …) = {g:.6g}: wrong value"
             + (" (does it work for 3 numbers? use numpy, not a 2-D formula)" if len(r) == 3 else ""))


@c.test("TODO 4: d2_samples() in chi2_sim.py draws an honest χ² law (40 000 values, two seeds)",
        hint="Lesson §3: one generator made from seed inside the function; two independent standard NORMAL numbers "
             "per value, each squared, then added. An honest χ²₂ has mean 2 and 95 % below 5.99.")
def _():
    with contextlib.redirect_stdout(io.StringIO()):
        mod = load_student("chi2_sim.py", fresh=True)
    (f,) = functions("d2_samples", mod=mod, file="chi2_sim.py")
    a = as_array(go(f, 40000, seed=11), "d2_samples(40000, seed=11)").reshape(-1)
    c.ok(a.size == 40000, f"d2_samples(40000) returned {a.size} values")
    c.ok(np.all(a >= 0), "d2_samples returned negative values: a sum of squares never is")
    b = as_array(go(f, 40000, seed=11), "d2_samples").reshape(-1)
    c.ok(same(a, b, 0), "two runs with the same seed give different numbers: create the generator INSIDE the function, "
                        "from seed (np.random.default_rng(seed))")
    d = as_array(go(f, 40000, seed=12), "d2_samples").reshape(-1)
    c.ok(not same(a, d, 0), "seed=11 and seed=12 give the same numbers: the seed argument is ignored")
    m = a.mean()
    if 0.6 < m < 0.74:
        raise CheckFailed(f"the mean of d² is {m:.3f}: uniform numbers (rng.random)? x and y are standard NORMAL")
    if 1.18 < m < 1.32:
        raise CheckFailed(f"the mean is {m:.3f}: that is the mean distance d — return d² = x² + y², no square root")
    if 0.95 < m < 1.05:
        raise CheckFailed(f"the mean is {m:.3f}: only one squared number per value — d² = x² + y² adds TWO")
    c.ok(1.95 < m < 2.05, f"the mean of 40 000 values of d² is {m:.3f}; an honest χ²₂ has mean 2.0")
    s1 = np.mean(a <= 1.0)
    if 0.49 < s1 < 0.55:
        raise CheckFailed(f"{100 * s1:.1f} % of the values are ≤ 1 (39 % expected): (x + y)² is not x² + y² — "
                          "square each number first, then add")
    c.ok(abs(s1 - 0.3935) < 0.012, f"{100 * s1:.1f} % of the values are ≤ 1; an honest χ²₂: 39.3 %")
    c.ok(abs(np.mean(a <= 5.991) - 0.95) < 0.006, "the share below 5.99 is not 95 %: are x and y independent?")


@c.test("TODO 5: propagate() with unseen Jacobians — 2 × 2, 1 × 2, 3 × 2 and 2 × 3",
        hint="Lesson §4: J P Jᵀ — an m × n J and an n × n P give an m × m covariance (mind the transpose).")
def _():
    (f,) = functions("propagate")
    for J, P, want in E["propagate"]:
        JJ, PP = np.array(J), np.array(P)
        got = go(f, JJ, PP)
        g = as_array(got, f"propagate of a {JJ.shape[0]} × {JJ.shape[1]} J")
        if g.shape == (JJ.shape[1], JJ.shape[1]) and JJ.shape[0] != JJ.shape[1] and same(g, JJ.T @ PP[:JJ.shape[0], :JJ.shape[0]] @ JJ, 1e-6):
            raise CheckFailed("propagate computes Jᵀ P J: the lesson's formula is J P Jᵀ")
        c.ok(g.shape == np.shape(want), f"propagate with a {JJ.shape[0]} × {JJ.shape[1]} J should give a "
                                        f"{JJ.shape[0]} × {JJ.shape[0]} matrix, got shape {g.shape}")
        if JJ.shape[0] == JJ.shape[1] and same(g, JJ @ PP @ JJ, 1e-6) and not same(want, JJ @ PP @ JJ, 1e-6):
            raise CheckFailed("propagate computes J P J: the transpose is missing (J P Jᵀ)")
        c.ok(same(g, want, 1e-6 * max(1.0, np.abs(want).max())), f"propagate of a {JJ.shape[0]} × {JJ.shape[1]} J: "
                                                                 "wrong values")


@c.test("TODO 6: polar_to_en() on unseen ranges and bearings (all four quadrants)",
        hint="Lesson §4 (the radar): β and σβ in RADIANS; a bearing is clockwise from north; J holds the derivatives "
             "of east and north by r and β; P_polar = diag(σr², σβ²); return (en, J P_polar Jᵀ).")
def _():
    (f,) = functions("polar_to_en")
    for args, wen, wP in E["polar_to_en"]:
        r, b, sr, sb = args
        got = pair(go(f, *args), "polar_to_en")
        en = as_array(got[0], "polar_to_en's position").reshape(-1)
        P = as_array(got[1], "polar_to_en's covariance", (2, 2))
        tag = f"polar_to_en{tuple(args)}"
        if en.shape == (2,) and same(en, wen[::-1], 1e-6):
            raise CheckFailed(f"{tag}: east and north are swapped — a bearing is clockwise from NORTH: "
                              "east = r sin β, north = r cos β")
        c.ok(en.shape == (2,) and same(en, wen, 1e-6), f"{tag}: the position {np.round(en, 3).tolist()} is wrong")
        for variant, msg in ((polar_variant(*args, deg=True), "σβ is still in DEGREES (math.radians)"),
                             (polar_variant(*args, squared=False), "P_polar holds σ, not σ²: diag(σr², σβ²)"),
                             (polar_variant(*args, r_factor=False), "the bearing column of J misses the factor r "
                                                                    "(∂(r sin β)/∂β = r cos β)"),
                             (polar_variant(*args, transpose=False), "J P J instead of J P Jᵀ")):
            if same(P, variant, 1e-6 * max(1.0, np.abs(variant).max())) and not same(P, wP, 1e-6):
                raise CheckFailed(f"{tag}: {msg}")
        lam = np.linalg.eigvalsh(np.array(wP))
        c.ok(same(np.linalg.eigvalsh(P), lam, 1e-4 * max(1.0, lam.max())), f"{tag}: the size of the ellipse is wrong "
                                                                            "(check J and P_polar)")
        c.ok(same(P, wP, 1e-4 * max(1.0, np.abs(wP).max())), f"{tag}: the ellipse has the right size but the wrong "
                                                              "tilt: check the signs and the order of J's rows")


@c.test("Steps 0–3: the cloud, its ellipse, the circle and the χ² simulation — numbers and explanation",
        hint="python3 run_uncertainty.py cloud: a, b, angle, the judge's σ, the shares inside the 1-sigma ellipse and the "
             "judge's circle (k = 1); python3 chi2_sim.py: the 95 % line. EXPLAIN_CHI2: two squared errors are added on "
             "a map, so d² is larger than on one axis.")
def _():
    p0, a, b, ang, js, pc, ins, circ, p95, why = answers(
        "PREDICT_INSIDE", "ELLIPSE_A_M", "ELLIPSE_B_M", "ELLIPSE_ANGLE_DEG", "JUDGE_SIGMA_M", "PREDICT_CIRCLE",
        "INSIDE_1SIGMA_PCT", "CIRCLE_1_PCT", "SIM_P95", "EXPLAIN_CHI2")
    L = LAB["cloud"]
    predicted("PREDICT_INSIDE", p0)
    a, b, ang, js = (number(v, n) for v, n in ((a, "ELLIPSE_A_M"), (b, "ELLIPSE_B_M"), (ang, "ELLIPSE_ANGLE_DEG"),
                                                (js, "JUDGE_SIGMA_M")))
    if abs(a - L["b_m"]) < 0.02 and abs(b - L["a_m"]) < 0.02:
        raise CheckFailed("ELLIPSE_A_M and ELLIPSE_B_M are swapped: a is the long semi-axis")
    c.near(a, L["a_m"], 0.02, "ELLIPSE_A_M (m)")
    c.near(b, L["b_m"], 0.02, "ELLIPSE_B_M (m)")
    if abs(ang - (L["angle_deg"] + 180.0)) < 0.5:
        raise CheckFailed("ELLIPSE_ANGLE_DEG is outside (−90, 90]: the same line, but write the angle your ellipse() prints")
    c.near(ang, L["angle_deg"], 0.5, "ELLIPSE_ANGLE_DEG (degrees from east)")
    c.near(js, L["judge_sigma_m"], 0.02, "JUDGE_SIGMA_M (m)")
    predicted("PREDICT_CIRCLE", pc)
    ins, circ = number(ins, "INSIDE_1SIGMA_PCT"), number(circ, "CIRCLE_1_PCT")
    if ins < 1.0 or circ < 1.0:
        raise CheckFailed("write the shares in percent (38.5, not 0.385)")
    if abs(ins - L["circle1_pct"]) < 0.3 and abs(circ - L["inside1_pct"]) < 0.3:
        raise CheckFailed("INSIDE_1SIGMA_PCT and CIRCLE_1_PCT are swapped")
    c.near(ins, L["inside1_pct"], 0.3, "INSIDE_1SIGMA_PCT (%)")
    c.near(circ, L["circle1_pct"], 0.3, "CIRCLE_1_PCT (%)")
    p95 = number(p95, "SIM_P95")
    if abs(p95 - 3.84) < 0.3:
        raise CheckFailed("SIM_P95 is the ONE-axis value (x² alone): write the 2-D column")
    c.ok(5.6 < p95 < 6.4, f"SIM_P95 = {p95:g}: write the d² that 95 % of your simulated values stay below "
                          "(python3 chi2_sim.py, the 2-D column)")
    explained("EXPLAIN_CHI2", why,
              ((r"two", r"\b2\b", r"both", r"x² ?\+ ?y²", r"x2 ?\+ ?y2", r"sum", r"add", r"each axis", r"2-?d", r"map",
                r"dimension", r"east and north"),
               'why fewer fit on a map (e.g. "on a map two squared errors are added, so d² is larger")'),
              ((r"5\.99", r"6\b", r"χ", r"chi", r"threshold", r"tail", r"mean", r"larger", r"bigger", r"spread",
                r"1\.96", r"3\.84", r"distribution", r"law"),
               'why 95 % is near 6 and not 4 (e.g. "the χ² law with 2 degrees of freedom: its 95 % point is 5.99")'))


@c.test("Step 4: the radar — J P Jᵀ against 20 000 draws, and where it fails",
        hint="python3 run_uncertainty.py radar, then radar wide: the a of each line, and the share inside the 95 % "
             "ellipse with 10°. EXPLAIN_RADAR: r·σβ across the line of sight; with 10° the positions lie on an arc.")
def _():
    pr, ra, mc, pw, wide, why = answers("PREDICT_RADAR", "RADAR_A_M", "MC_A_M", "PREDICT_WIDE", "WIDE_INSIDE_PCT",
                                        "EXPLAIN_RADAR")
    predicted("PREDICT_RADAR", pr)
    ra, mc = number(ra, "RADAR_A_M"), number(mc, "MC_A_M")
    if abs(ra - LAB["radar"]["mc_a_m"]) < 0.05 and abs(mc - LAB["radar"]["jpj_a_m"]) < 0.05:
        raise CheckFailed("RADAR_A_M and MC_A_M are swapped")
    if abs(ra - LAB["radar_wide"]["jpj_a_m"]) < 0.5:
        raise CheckFailed("RADAR_A_M is the 10° value: write the 1° one (python3 run_uncertainty.py radar)")
    c.near(ra, LAB["radar"]["jpj_a_m"], 0.1, "RADAR_A_M (m)")
    c.near(mc, LAB["radar"]["mc_a_m"], 0.1, "MC_A_M (m)")
    predicted("PREDICT_WIDE", pw)
    wide = number(wide, "WIDE_INSIDE_PCT")
    if wide <= 1.0:
        raise CheckFailed("write WIDE_INSIDE_PCT in percent (46.7, not 0.467)")
    c.near(wide, LAB["radar_wide"]["inside95_pct"], 0.3, "WIDE_INSIDE_PCT (%)")
    explained("EXPLAIN_RADAR", why,
              ((r"bearing", r"angle", r"angular", r"cross", r"sideways", r"across", r"perpendicular", r"r ?[·×x*] ?σ",
                r"lateral", r"radian"),
               'why the ellipse is long across the line of sight (e.g. "a bearing error moves the target sideways by r·σβ")'),
              ((r"curv", r"arc", r"bend", r"banana", r"linear", r"straight", r"approximat", r"jacobian", r"circle",
                r"tangent", r"small error"),
               'why J P Jᵀ fails with 10° (e.g. "the positions lie on a curved arc; J P Jᵀ is a straight-line approximation")'))


# ======================================================================== session 2 — Gatekeeper
@c.test("TODO 7: gate() on unseen surprises — near the thresholds, at 95 % and 99 %, correlated S",
        hint="Lesson §5: True when mahalanobis2(r, S) ≤ chi2_threshold(p, len(r)) — d², not d; dof = the length of r "
             "(2 on a map). Return a bool.")
def _():
    (f,) = functions("gate")
    for r, S, p, want in E["gate"]:
        got = go(f, np.array(r), np.array(S), p=p)
        if not isinstance(got, (bool, np.bool_)):
            raise CheckFailed(f"gate should return True or False, got {got!r} (a {type(got).__name__})")
        if bool(got) == want:
            continue
        rr, SS = np.array(r), np.array(S)
        d2 = float(rr @ np.linalg.solve(SS, rr))
        t1 = {0.99: 6.635, 0.95: 3.841}[p]
        t2 = {0.99: 9.210, 0.95: 5.991}[p]
        if want and 9.0 <= d2 <= t2:
            raise CheckFailed(f"gate({r}, {S}, p={p}) refuses d² = {d2:.2f}: the threshold is chi2_threshold(p, 2) "
                              f"({t2:.2f} here), not 3 sigma (9)")
        if want and d2 > t1:
            raise CheckFailed(f"gate({r}, {S}, p={p}) refuses a surprise of d² = {d2:.2f}: two numbers in r means 2 "
                              f"degrees of freedom (chi2_threshold(p, len(r))), not 1")
        if not want and float(np.sum(rr ** 2 / np.diag(SS))) <= t2 and abs(SS[0, 1]) > 0:
            raise CheckFailed(f"gate({r}, {S}, p={p}) accepts a surprise across a tilted ellipse (d² = {d2:.2f}): the "
                              "off-diagonal terms of S count (is mahalanobis2 right?)")
        if not want and math.sqrt(d2) <= t2:
            raise CheckFailed(f"gate({r}, {S}, p={p}) accepts d² = {d2:.2f}: compare d² (not d) with the threshold")
        raise CheckFailed(f"gate({r}, {S}, p={p}) returned {got}: d² is {d2:.2f}")


@c.test("TODO 8: fuse() on unseen tilted estimates",
        hint="Lesson §6: each estimate counts with its information, the inverse MATRIX (np.linalg.inv, not 1 / P); "
             "the fused P is the inverse of the summed informations, and each x is weighed by its own information.")
def _():
    (f,) = functions("fuse")
    for x1, P1, x2, P2, wx, wP in E["fuse"]:
        got = pair(go(f, np.array(x1), np.array(P1), np.array(x2), np.array(P2)), "fuse")
        x = as_array(got[0], "fuse's x").reshape(-1)
        P = as_array(got[1], "fuse's P", (2, 2))
        A1, A2 = np.array(P1), np.array(P2)
        if same(P, wP, 1e-6) and same(x, wx, 1e-6):
            continue
        e1, e2 = 1 / A1, 1 / A2
        Pe = 1 / (e1 + e2)
        if same(P, Pe, 1e-6) or same(P, np.linalg.inv(e1 + e2), 1e-6):
            raise CheckFailed("fuse divides number by number (1 / P): the inverse of a matrix is np.linalg.inv(P)")
        if same(P, np.linalg.inv(A1) + np.linalg.inv(A2), 1e-6):
            raise CheckFailed("fuse's P is the SUM of the informations: P is the inverse of that sum")
        if same(P, wP, 1e-6):
            sw = wP @ (np.linalg.inv(A2) @ np.array(x1) + np.linalg.inv(A1) @ np.array(x2))
            if same(x, sw, 1e-6):
                raise CheckFailed("fuse weighs each x with the OTHER estimate's information: x = P (P1⁻¹ x1 + P2⁻¹ x2)")
            if same(x, wP @ (A1 @ np.array(x1) + A2 @ np.array(x2)), 1e-6):
                raise CheckFailed("fuse weighs x1 by P1 (not P1⁻¹): the better estimate must weigh more")
            raise CheckFailed(f"fuse: P is right but x = {np.round(x, 3).tolist()} is wrong")
        raise CheckFailed(f"fuse: P = {np.round(P, 3).tolist()} is wrong")


@c.test("TODO 9: make_covariance() — unseen covariances, the type rules, plain floats, and impossible matrices refused",
        hint="Lesson §7 table and the docstring: the 9 numbers in ENU row-major order, the type rules (what is known, "
             "what is guessed), Python floats; never repair a matrix: ask is_covariance and raise ValueError with its reason.")
def _():
    (f,) = functions("make_covariance")
    got = pair(go(f, None), "make_covariance")
    c.ok(list(got[0]) == [0.0] * 9 and got[1] == 0,
         f"make_covariance(None) should give nine 0.0 and COV_UNKNOWN (0), got {got!r}")
    for P2, up, w9, wk in E["make_covariance"]:
        got = pair(go(f, np.array(P2), sigma_up_m=up), "make_covariance")
        cov9, kind = got
        tag = f"make_covariance({P2}, sigma_up_m={up})"
        if not isinstance(cov9, list):
            raise CheckFailed(f"{tag}: cov9 should be a LIST of 9 floats, got a {type(cov9).__name__}")
        c.ok(len(cov9) == 9, f"{tag}: cov9 should have 9 numbers, got {len(cov9)}")
        bad = [x for x in cov9 if type(x) is not float]
        if bad:
            raise CheckFailed(f"{tag}: {bad[0]!r} is a {type(bad[0]).__name__}, not a Python float (float(x))")
        if up is None and abs(cov9[8] - 2 * max(P2[0][0], P2[1][1])) < 1e-9:
            raise CheckFailed(f"{tag}: the up variance is (2σ)² = 4·max(a, c), not 2·max(a, c)")
        if up is not None and abs(cov9[8] - up) < 1e-9 and up != 1:
            raise CheckFailed(f"{tag}: the up variance is σU² (m²), not σU")
        if w9[0] != w9[4] and same([cov9[0], cov9[4]], [w9[4], w9[0]], 1e-9):
            raise CheckFailed(f"{tag}: east and north are swapped: a = σE² is index 0, c = σN² index 4")
        c.ok(same(cov9, w9, 1e-9), f"{tag}: the 9 numbers {cov9} are wrong (row-major ENU: a, b, 0, b, c, 0, 0, 0, up)")
        if kind != wk:
            names = {0: "COV_UNKNOWN", 1: "COV_APPROXIMATED", 2: "COV_DIAGONAL_KNOWN", 3: "COV_KNOWN"}
            raise CheckFailed(f"{tag}: type {kind!r}, expected {names[wk]} — "
                              + ("the up variance is a guess, so the matrix is APPROXIMATED" if up is None else
                                 "KNOWN when the east-north term is not 0, else DIAGONAL_KNOWN"))
    for P2, up, why in E["make_covariance_bad"]:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                v = f(np.array(P2), sigma_up_m=up)
        except ValueError as e:
            c.ok(why in str(e), f"make_covariance({P2}, {up}) raised ValueError({str(e)!r}): include is_covariance's "
                                f"reason ({why!r}) in the message")
            continue
        except Exception as e:
            raise CheckFailed(f"make_covariance({P2}, {up}) should raise ValueError, it raised {type(e).__name__}: {e}")
        sym = isinstance(v, (tuple, list)) and len(v) == 2 and isinstance(v[0], (list, tuple)) and len(v[0]) == 9 \
            and v[0][1] == v[0][3]
        hint = (" — the east-north term must be copied from BOTH places, P2[0][1] and P2[1][0], so that is_covariance "
                "can see the asymmetry" if why == "not symmetric" and sym else
                " — ask is_covariance(cov9) before returning, and raise ValueError when it says no")
        raise CheckFailed(f"make_covariance({P2}, {up}) published {v!r}: {why}, it must raise ValueError{hint}")


@c.test("Steps 5–6: the judge and the attacker — numbers and explanations",
        hint="python3 run_uncertainty.py judge: A's d² and the number accepted at 99 %; attack: the longest and shortest "
             "accepted offsets. EXPLAINs: direction matters (across the track the prediction is sure); an over-confident "
             "predictor locks the truth out; the attacker goes along the long axis, √(χ²·λ).")
def _():
    pj, d2a, n99, wj, amax, amin, wa = answers("PREDICT_JUDGE", "D2_A", "N_ACCEPT_99", "EXPLAIN_JUDGE", "ATTACK_MAX_M",
                                               "ATTACK_MIN_M", "EXPLAIN_ATTACK")
    J = LAB["judge"]
    predicted("PREDICT_JUDGE", pj)
    d2a = number(d2a, "D2_A")
    if abs(d2a - math.sqrt(J["fixes"]["A"]["d2"])) < 0.02:
        raise CheckFailed("D2_A is d (the square root): write d² as the runner prints it")
    c.near(d2a, J["fixes"]["A"]["d2"], 0.02, "D2_A")
    n99 = number(n99, "N_ACCEPT_99")
    c.ok(n99 == J["n_accept_99"], f"N_ACCEPT_99 = {n99:g}: count the 'accept' in the 'gate 99 %' column")
    explained("EXPLAIN_JUDGE", wj,
              ((r"across", r"direction", r"perpendicular", r"along", r"track", r"axis", r"ellipse", r"sideways",
                r"25 ?m", r"narrow", r"thin"),
               'why E is refused although nearer (e.g. "E is across the track, where the prediction is only 25 m unsure")'),
              ((r"lock", r"never", r"keep", r"stuck", r"forever", r"(every|all|each) (later|next|following)", r"again",
                r"refuse", r"reject"),
               'what the never-grown predictor does next (e.g. "it refuses the true GPS, and every later fix: locked out")'),
              ((r"\bb\b", r"spoof", r"circle", r"160", r"fake", r"attack"),
               'what the 160 m circle does (e.g. "the circle accepts the spoofer B")'))
    amax, amin = number(amax, "ATTACK_MAX_M"), number(amin, "ATTACK_MIN_M")
    A = LAB["attack"]
    if abs(amax - A["min_m"]) < 0.5 and abs(amin - A["max_m"]) < 0.5:
        raise CheckFailed("ATTACK_MAX_M and ATTACK_MIN_M are swapped")
    c.near(amax, A["max_m"], 0.3, "ATTACK_MAX_M (m)")
    c.near(amin, A["min_m"], 0.3, "ATTACK_MIN_M (m)")
    explained("EXPLAIN_ATTACK", wa,
              ((r"long axis", r"along", r"track", r"major", r"largest eigen", r"λ ?1", r"lambda ?1", r"120", r"300",
                r"longest", r"biggest", r"drift"),
               'which direction the attacker chooses (e.g. "along the track: the long axis of S")'),
              ((r"√", r"sqrt", r"root", r"9\.21", r"χ", r"chi", r"eigenvalue", r"λ", r"lambda", r"threshold"),
               'which formula gives the numbers (e.g. "√(9.21 · λ) for each axis")'),
              ((r"false alarm", r"refus", r"reject", r"honest", r"cost", r"truth", r"true", r"good fix", r"smaller p",
                r"lower p", r"better predict", r"smaller s", r"smaller covariance", r"shrink"),
               'what would shrink the room and its cost (e.g. "a lower p: more honest fixes refused")'))


def drive_run(gate, fuse, rows):
    thr = 5.991464547107979
    errs, cover, caught, fa = [], [], 0, 0
    for row in rows:
        truth = np.array([float(row["true_e"]), float(row["true_n"])])
        g = np.array([float(row["gps_e"]), float(row["gps_n"])])
        Pg = np.array([[float(row["gps_a"]), float(row["gps_b"])], [float(row["gps_b"]), float(row["gps_c"])]])
        v = np.array([float(row["vis_e"]), float(row["vis_n"])])
        Pv = float(row["vis_sigma_m"]) ** 2 * np.eye(2)
        ok = go(gate, v - g, Pg + Pv, p=0.99)
        if not isinstance(ok, (bool, np.bool_)):
            raise CheckFailed(f"gate should return a bool, got {ok!r}")
        if ok:
            got = pair(go(fuse, g, Pg, v, Pv), "fuse")
            x, P = as_array(got[0], "fuse's x").reshape(-1), as_array(got[1], "fuse's P", (2, 2))
        else:
            x, P = g, Pg
            caught += row["vis_wrong"] == "1"
            fa += row["vis_wrong"] != "1"
        e = x - truth
        errs.append(math.hypot(*e))
        cover.append(float(e @ np.linalg.solve(P, e)) <= thr)
    errs = np.array(errs)
    return float(np.sqrt(np.mean(errs ** 2))), float(100 * np.mean(cover)), caught, fa


@c.test("Step 7: your gate + fuse on an unseen drive, and your fusion numbers",
        hint="The check flies YOUR gate (99 %) and fuse on a hidden drive (another street); it must give the reference "
             "RMS, coverage and counts. python3 run_uncertainty.py fuse: the RMS of three policies, two coverages and "
             "the good fixes refused with the liar. EXPLAIN_FUSE: a few outliers dominate the RMS; a liar's σ is too small.")
def _():
    gate, fuse = functions("gate", "fuse")
    rows = list(csv.DictReader(io.StringIO(hidden("drive.csv"))))
    rms, cov, caught, fa = drive_run(gate, fuse, rows)
    D = E["drive"]
    c.ok(caught == D["caught"] and fa == D["false_alarms"],
         f"on the hidden drive your gate refused {caught} wrong and {fa} good vision fixes: not the reference counts "
         "(is the 99 % threshold applied to d² with 2 degrees of freedom?)")
    c.ok(abs(rms - D["rms_m"]) < 0.01, f"on the hidden drive, gate then fuse has an RMS of {rms:.2f} m: not the "
                                       "reference (is fuse right with TILTED covariances?)")
    c.ok(abs(cov - D["cover_pct"]) < 0.01, f"on the hidden drive the coverage is {cov:.1f} %: not the reference")
    pf, rg, ra, rgt, cg, cl, lr, why = answers("PREDICT_FUSE", "RMS_GPS_M", "RMS_ALL_M", "RMS_GATED_M",
                                               "COVER_GATED_PCT", "COVER_LIAR_PCT", "LIAR_REFUSED", "EXPLAIN_FUSE")
    F = LAB["fuse"]
    predicted("PREDICT_FUSE", pf)
    for v, name, key in ((rg, "RMS_GPS_M", "GPS alone"), (ra, "RMS_ALL_M", "fuse every pair"),
                         (rgt, "RMS_GATED_M", "gate, then fuse")):
        x = number(v, name)
        if key != "fuse every pair" and abs(x - F[key]["p95_m"]) < 0.1:
            raise CheckFailed(f"{name} is the p95 column: write the RMS")
        c.near(x, F[key]["rms_m"], 0.06, f"{name} (m, the RMS column of '{key}')")
    cg, cl = number(cg, "COVER_GATED_PCT"), number(cl, "COVER_LIAR_PCT")
    if cg <= 1.0 or cl <= 1.0:
        raise CheckFailed("write the coverages in percent (93.0, not 0.93)")
    c.near(cg, F["gate, then fuse"]["cover_pct"], 0.06, "COVER_GATED_PCT (%)")
    c.near(cl, F["gate, then fuse — vision states 5 m"]["cover_pct"], 0.06, "COVER_LIAR_PCT (%)")
    lr = number(lr, "LIAR_REFUSED")
    c.ok(lr == F["gate, then fuse — vision states 5 m"]["false_alarms"],
         f"LIAR_REFUSED = {lr:g}: the 'good refused' column of the liar's line")
    explained("EXPLAIN_FUSE", why,
              ((r"outlier", r"wrong", r"bad match", r"false match", r"mismatch", r"few", r"24"),
               'what spoils "fuse every pair" (e.g. "the wrong matches are fused too")'),
              ((r"rms", r"square", r"large error", r"big error", r"dominat", r"hundreds", r"300", r"far", r"p95",
                r"most (seconds|epochs|of the time)"),
               'why the RMS is worse while the p95 is better (e.g. "the RMS squares the few huge errors")'),
              ((r"too small", r"overconfiden", r"over-confiden", r"5 ?m", r"liar", r"lie", r"dishonest", r"coverage",
                r"75", r"false alarm", r"refus"),
               'what the liar does (e.g. "its σ is too small: coverage falls and the gate refuses good fixes")'))


@c.test("Step 8: publishing — what the judge reads, and what it misses",
        hint="python3 run_uncertainty.py publish: the judge's σ and the long axis for GPS alone, and the count of false "
             "FIX seconds. EXPLAIN_PUBLISH: the judge reads the largest DIAGONAL term; the ellipse is tilted; up to √2.")
def _():
    s, w, n, why = answers("STATED_SIGMA_M", "WORST_SIGMA_M", "FALSE_FIX_S", "EXPLAIN_PUBLISH")
    P = LAB["publish"]
    s, w, n = number(s, "STATED_SIGMA_M"), number(w, "WORST_SIGMA_M"), number(n, "FALSE_FIX_S")
    if abs(s - P["gps_long_axis_m"]) < 0.06 and abs(w - P["gps_judge_sigma_m"]) < 0.06:
        raise CheckFailed("STATED_SIGMA_M and WORST_SIGMA_M are swapped")
    if abs(s - P["fused_judge_sigma_m"]) < 0.06:
        raise CheckFailed("STATED_SIGMA_M is the fused one: write the judge's σ for GPS ALONE")
    c.near(s, P["gps_judge_sigma_m"], 0.06, "STATED_SIGMA_M (m)")
    c.near(w, P["gps_long_axis_m"], 0.06, "WORST_SIGMA_M (m)")
    c.ok(n == P["false_fix_s"], f"FALSE_FIX_S = {n:g}: the count printed on the 'GPS alone over the whole drive' line")
    explained("EXPLAIN_PUBLISH", why,
              ((r"tilt", r"diagonal", r"rotat", r"correlat", r"40", r"street", r"oblique", r"diagonal term", r"√ ?max",
                r"sqrt ?\(?max", r"east or north", r"not along"),
               'why the two differ (e.g. "the judge reads the largest diagonal term, but the ellipse is tilted")'),
              ((r"√ ?2", r"sqrt ?\(?2", r"1\.41", r"41 ?%", r"factor"),
               'how large the difference can get (e.g. "up to a factor √2")'),
              ((r"eigen", r"λ", r"lambda", r"long axis", r"worst", r"largest", r"semi-?major", r"change", r"should",
                r"instead"),
               'what you would change (e.g. "read √λ₁, the long axis")'))


@c.test("Step 9: the memo in report.md",
        hint="Keep the three headings; 150–350 words in your own words; quote your coverage of 'gate, then fuse' (%), "
             "its RMS (m), and the 39 % of a 1-sigma ellipse.")
def _():
    try:
        text = open("report.md", encoding="utf-8").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for h in ("## What our σ means", "## When we refuse a position", "## When we fuse, and when we must not"):
        c.ok(h in body, f"report.md must keep the heading '{h}'")
    words = re.findall(r"[A-Za-zÀ-ÿ0-9°'′.-]+", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok(len(words) >= 150, f"report.md has {len(words)} words: write at least 150")
    c.ok(len(words) <= 420, f"report.md has {len(words)} words: a memo is short — aim for 350 (the limit is 420)")
    low = body.lower()
    c.ok(re.search(r"\b(39|39\.\d|38\.\d)\s*%", low) is not None, "quote the share inside a 1-sigma ellipse (39 %)")
    c.ok(re.search(r"\b9[0-9](\.\d+)?\s*%", low) is not None, "quote the coverage of 'gate, then fuse' (in %)")
    c.ok(re.search(r"\b1[0-4](\.\d+)?\s*m\b", low) is not None, "quote the RMS of 'gate, then fuse' (in m)")


c.milestone("ellipse", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "TODO 6:", "Steps 0–3", "Step 4",
            label="Ellipse maker")
c.milestone("gatekeeper", "TODO", "Step", label="Gatekeeper")
c.run()
