"""run_uncertainty.py — runs YOUR functions of navera_lite/uncertainty.py on the lab's situations and draws them.

    python3 run_uncertainty.py test        check each function on its docstring example (and a few traps)
    python3 run_uncertainty.py look        the three data files, in numbers                           (Step 1)
    python3 run_uncertainty.py cloud       600 fixes of a receiver standing still: covariance, ellipses (Steps 2–3)
    python3 run_uncertainty.py radar       range + bearing → east, north: J P Jᵀ against 20 000 draws   (Step 4)
    python3 run_uncertainty.py radar wide  the same with a bearing σ of 10° (a radio direction finder)  (Step 4)
    python3 run_uncertainty.py judge       six fixes after a 40 s GPS outage: which ones are plausible? (Step 5)
    python3 run_uncertainty.py attack      the largest fake offset your gate lets through, every 5°   (Step 6)
    python3 run_uncertainty.py fuse        GPS + day vision on a 400 s drive: five policies compared   (Step 7)
    python3 run_uncertainty.py publish     the result in the position contract: what the judge reads   (Step 8)

Also: python3 chi2_sim.py (Step 3). Data: /data/academy/27-uncertainty/ (read only). Pictures go to out/ — click
them in the 📝 Code tab. Every number is also written to out/results.json.
"""
import contextlib
import csv
import io
import json
import math
import os
import sys
import traceback

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = os.environ.get("UNCERTAINTY_DATA", "/data/academy/27-uncertainty")
un = rk.load_student("navera_lite.uncertainty")
est = rk.load_student("navera_lite.estimate")
settings = rk.load_student("navera_lite.settings")
FILE = "navera_lite/uncertainty.py"


def cfg():
    try:
        return settings.load("navera_lite.yaml")
    except Exception as e:                       # a broken yaml must not stop this lab
        print(f"(navera_lite.yaml could not be read: {e} — using the default settings)")
        return dict(settings.DEFAULTS)


def need_data(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: the course data is not mounted here (tell your teacher)")
    return path


def needs(*names):
    for n in names:
        f = getattr(un, n, None)
        if f is None:
            sys.exit(f"{n}() does not exist in {FILE} — did you rename it?")
        if rk.is_stub(f):
            sys.exit(f"{n}() is not written yet: write its TODO in {FILE} first "
                     "(python3 run_uncertainty.py test shows which ones work)")


def written(name):
    f = getattr(un, name, None)
    return f is not None and not rk.is_stub(f)


def num(v, fn):
    if isinstance(v, bool) or v is None:
        sys.exit(f"{fn}() must return a number, but it returned {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return one number, but it returned {v!r}")
    if not math.isfinite(x):
        sys.exit(f"{fn}() returned {x}: not a usable number")
    return x


def mat(v, fn, shape=(2, 2)):
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return a {shape[0]} × {shape[1]} numpy array, but it returned {v!r}")
    if a.shape != shape:
        sys.exit(f"{fn}() must return a {shape[0]} × {shape[1]} array, but it returned shape {a.shape}")
    if not np.all(np.isfinite(a)):
        sys.exit(f"{fn}() returned a matrix with nan or inf in it: {a.tolist()}")
    return a


def vec(v, fn, n=2):
    try:
        a = np.asarray(v, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return {n} numbers, but it returned {v!r}")
    if a.shape != (n,):
        sys.exit(f"{fn}() must return {n} numbers (east, north), but it returned {a.size}")
    return a


def ell(P, k=1.0):
    v = rk.need_ok(un, "ellipse", P, k=k)
    if not (isinstance(v, (tuple, list)) and len(v) == 3):
        sys.exit(f"ellipse() must return three numbers (a_m, b_m, angle_deg), but it returned {v!r}")
    return tuple(num(x, "ellipse") for x in v)


def d2(r, S):
    return num(rk.need_ok(un, "mahalanobis2", r, S), "mahalanobis2")


def gate(r, S, p=0.99):
    v = rk.need_ok(un, "gate", r, S, p=p)
    if not isinstance(v, (bool, np.bool_)):
        sys.exit(f"gate() must return True or False, but it returned {v!r} (a {type(v).__name__})")
    return bool(v)


def fuse(x1, P1, x2, P2):
    v = rk.need_ok(un, "fuse", x1, P1, x2, P2)
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"fuse() must return two things (x, P), but it returned {v!r}")
    return vec(v[0], "fuse"), mat(v[1], "fuse")


def plt_ready():
    plt = rk.plt_or_none()
    if plt is not None:
        os.makedirs("out", exist_ok=True)
    return plt


def save_results(update):
    os.makedirs("out", exist_ok=True)
    path = "out/results.json"
    try:
        with open(path) as f:
            res = json.load(f)
    except (OSError, ValueError):
        res = {}
    res.update(update)
    with open(path, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)


def outline(a, b, ang, centre=(0.0, 0.0)):
    return un.ellipse_outline(a, b, ang, centre=centre)


def bearing_of(e, n):
    return math.degrees(math.atan2(e, n)) % 360.0


def gps_cov(row):
    return np.array([[float(row["gps_a"]), float(row["gps_b"])], [float(row["gps_b"]), float(row["gps_c"])]])


# ------------------------------------------------------------------------------------------- test
def attempt(fn):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(), None
    except NotImplementedError:
        return None, "it is not written yet"
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__)
              if f.filename.endswith(os.path.join("navera_lite", "uncertainty.py")) or f.filename.endswith("chi2_sim.py")]
        where = f" ({os.path.basename(tb[-1].filename)} line {tb[-1].lineno}, in {tb[-1].name}())" if tb else ""
        hint = rk._hint(e)
        s = str(e)
        if "matmul" in s or "aligned" in s or "mismatch in its core dimension" in s:
            hint = " — two shapes do not fit in a matrix product: print the .shape of each side (did you forget a .T?)"
        elif "math domain error" in s:
            hint = (" — a square root of a negative number: a tiny negative λ from rounding (−1e-15)? "
                    "max(λ, 0.0) before the root")
        elif "Singular matrix" in s:
            hint = " — a matrix you invert (or solve with) has no inverse: which one, and why?"
        return None, f"stopped with {type(e).__name__}: {e}{where}{hint}"


def close(a, b, tol=1e-6):
    try:
        return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float), atol=tol, rtol=0)
    except (TypeError, ValueError):
        return False


def test():
    import chi2_sim
    rows = []

    def line(todo, name, ok, msg):
        rows.append(f"{'✔' if ok else '✘'} TODO {todo} {name}(): {msg}")

    def fmt(v):
        if isinstance(v, np.ndarray):
            return fmt(np.round(v, 4).tolist())
        if isinstance(v, (tuple, list)):
            inner = ", ".join(fmt(x) for x in v)
            return f"({inner})" if isinstance(v, tuple) else f"[{inner}]"
        if isinstance(v, float):
            return f"{v:.6g}"
        return repr(v)

    def run(todo, name, cases, mod=un, file=FILE):
        """cases: (label, call, check); check(v) → None when right, else a sentence (the likely mistake)."""
        f = getattr(mod, name, None)
        if f is None:
            line(todo, name, False, f"does not exist in {file} — did you rename it?")
            return
        if rk.is_stub(f):
            rows.append(f"· TODO {todo} {name}(): not written yet")
            return
        for label, call, check in cases:
            v, err = attempt(lambda: call(f))
            if err:
                line(todo, name, False, f"{label}: {err}")
                return
            if v is None:
                line(todo, name, False, f"{label}: returned None — every path must end with a `return`")
                return
            bad = check(v)
            if bad:
                line(todo, name, False, f"{label}: got {fmt(v)} — {bad}")
                return
        line(todo, name, True, f"{len(cases)} case(s) right")

    def arr(v):
        try:
            return np.asarray(v, dtype=float)
        except (TypeError, ValueError):
            return None

    def mat_is(want, diagnose=()):
        def check(v):
            a = arr(v)
            if a is None:
                return "not a matrix of numbers"
            if a.shape != np.shape(want):
                return f"shape {a.shape}, expected {np.shape(want)}"
            if close(a, want):
                return None
            for wrong, msg in diagnose:
                if close(a, wrong):
                    return msg
            return f"expected {fmt(np.asarray(want, dtype=float))}"
        return check

    def ellipse_is(want):
        def check(v):
            if not (isinstance(v, (tuple, list)) and len(v) == 3):
                return "three numbers (a_m, b_m, angle_deg) expected"
            a, b, g = (float(x) for x in v)
            wa, wb, wg = want
            if close((a, b), (wb, wa), 1e-3) and wa != wb:
                return "a and b are swapped: a is the LONG semi-axis"
            if close((a, b), (wa * wa, wb * wb), 1e-3) and wa > 1.5:
                return "those are variances (m²): the semi-axes are the SQUARE ROOTS of λ"
            if not close((a, b), (wa, wb), 1e-3):
                return f"the semi-axes should be ({wa:g}, {wb:g})"
            if abs(g - wg) < 1e-3:
                return None
            if abs(g - math.radians(wg)) < 1e-3 and abs(wg) > 1:
                return "the angle is in RADIANS: the interface uses degrees (math.degrees)"
            if abs((g - wg + 90.0) % 180.0 - 90.0) < 1e-3:
                return "the right line, but the angle must be in (−90, 90]: add or remove 180°"
            return f"the angle should be {wg:g}° (from east towards north)"
        return check

    def num_is(want, diagnose=()):
        def check(v):
            if isinstance(v, (bool, tuple, list, np.ndarray)) and np.ndim(v) != 0:
                return "one number expected"
            try:
                x = float(v)
            except (TypeError, ValueError):
                return "one number expected"
            if close(x, want):
                return None
            for wrong, msg in diagnose:
                if close(x, wrong):
                    return msg
            return f"expected {want:g}"
        return check

    def bool_is(want, msg):
        return lambda v: None if (v is want or v is np.bool_(want)) else msg

    def pair_is(wx, wP, diagnose=()):
        def check(v):
            if not (isinstance(v, (tuple, list)) and len(v) == 2):
                return "two things (vector, matrix) expected"
            x, P = arr(v[0]), arr(v[1])
            if x is None or P is None:
                return "numbers expected"
            if x.reshape(-1).shape == np.shape(wx) and close(x.reshape(-1), wx, 1e-4) and P.shape == np.shape(wP) \
                    and close(P, wP, 1e-3):
                return None
            for test_, msg in diagnose:
                if test_(x.reshape(-1), P):
                    return msg
            return f"expected ({fmt(np.asarray(wx, dtype=float))}, {fmt(np.asarray(wP, dtype=float))})"
        return check

    def raises(f, *a, **k):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                f(*a, **k)
        except ValueError:
            return "ValueError"
        return "no error"

    pts = [[0.0, 0.0], [2.0, 2.0], [4.0, 1.0]]
    run(1, "sample_cov", [
        ("the docstring example", lambda f: f(pts),
         mat_is([[4.0, 1.0], [1.0, 1.0]], (([[8 / 3, 2 / 3], [2 / 3, 2 / 3]], "you divided by N: divide by N − 1"),
                                           ([[10.0, 4.0], [4.0, 2.5]], "the mean point is not subtracted"),
                                           ([[35 / 8, 5 / 8], [5 / 8, 11 / 8]],
                                            "you subtracted ONE number (the mean of all values): the mean point is "
                                            "x.mean(axis=0), one mean per column"),
                                           ([[35 / 12, 5 / 12], [5 / 12, 11 / 12]],
                                            "x.mean() without axis=0 (one number for both columns), and divided by N")))),
        ("one point only", lambda f: raises(f, [[1.0, 2.0]]),
         lambda v: None if v == "ValueError" else "with N − 1 = 0 there is no spread: raise ValueError"),
    ])
    run(2, "ellipse", [
        ("the docstring example", lambda f: f([[13.6, 4.8], [4.8, 6.4]]), ellipse_is((4.0, 2.0, 26.5651))),
        ("k = 3", lambda f: f([[13.6, 4.8], [4.8, 6.4]], k=3), ellipse_is((12.0, 6.0, 26.5651))),
        ("long axis due north", lambda f: f([[4.0, 0.0], [0.0, 9.0]]), ellipse_is((3.0, 2.0, 90.0))),
        ("a round error", lambda f: f([[4.0, 0.0], [0.0, 4.0]]), ellipse_is((2.0, 2.0, 0.0))),
        ("errors on one line (ρ = 1)", lambda f: f([[16.0, 8.48], [8.48, 4.4944]]), ellipse_is((4.52707, 0.0, 27.9236))),
    ])
    run(3, "mahalanobis2", [
        ("the docstring example", lambda f: f([6.0, 0.0], [[9.0, 0.0], [0.0, 1.0]]),
         num_is(4.0, ((2.0, "that is d: the function returns d², no square root"),
                      (324.0, "that is rᵀ S r: use S⁻¹ (np.linalg.solve(S, r))")))),
        ("the same 6 m, north", lambda f: f([0.0, 6.0], [[9.0, 0.0], [0.0, 1.0]]), num_is(36.0)),
        ("a correlated S", lambda f: f([3.0, 1.0], [[13.6, 4.8], [4.8, 6.4]]),
         num_is(0.6625, ((9.0 / 13.6 + 1.0 / 6.4, "you divided by the diagonal only: the off-diagonal terms count too"),))),
    ])
    f4 = getattr(chi2_sim, "d2_samples", None)
    if f4 is None:
        line(4, "d2_samples", False, "does not exist in chi2_sim.py — did you rename it?")
    elif rk.is_stub(f4):
        rows.append("· TODO 4 d2_samples(): not written yet (chi2_sim.py)")
    else:
        v, err = attempt(lambda: f4(20000, seed=5))
        w, _ = attempt(lambda: f4(20000, seed=5))
        a = arr(v).reshape(-1) if v is not None and arr(v) is not None else np.array([])
        m = a.mean() if a.size else float("nan")
        if err and "as a data type" in err:
            line(4, "d2_samples", False, "TypeError \"Cannot interpret '2' as a data type\": the shape is ONE argument, "
                                          "a tuple — rng.standard_normal((n, 2)), not standard_normal(n, 2)")
        elif err:
            line(4, "d2_samples", False, err)
        elif a.shape != (20000,):
            line(4, "d2_samples", False, f"d2_samples(20000) returned {a.size} numbers, not 20000")
        elif np.any(a < 0):
            line(4, "d2_samples", False, "some values are negative: a sum of squares never is")
        elif w is None or not close(a, arr(w).reshape(-1)):
            line(4, "d2_samples", False, "two runs with the same seed give different numbers: make the generator "
                                          "INSIDE the function, from seed")
        elif 0.6 < m < 0.74:
            line(4, "d2_samples", False, f"the mean of 20 000 values is {m:.3f}: uniform numbers (rng.random)? x and y "
                                          "are standard NORMAL")
        elif 1.18 < m < 1.32:
            line(4, "d2_samples", False, f"the mean is {m:.3f}: that is the distance d — return d² (no square root)")
        elif 0.95 < m < 1.05:
            line(4, "d2_samples", False, f"the mean is {m:.3f}: one squared number per value — d² = x² + y² adds two")
        elif not 1.9 < m < 2.1:
            line(4, "d2_samples", False, f"the mean of 20 000 values is {m:.3f}, about 2.0 expected")
        elif not abs(np.mean(a <= 1.0) - 0.393) < 0.02:
            line(4, "d2_samples", False, f"{100 * np.mean(a <= 1.0):.0f} % of the values are ≤ 1, about 39 % expected: "
                                          "(x + y)² is not x² + y² — square each number, then add")
        else:
            line(4, "d2_samples", True, f"20 000 values ≥ 0, repeatable, mean {m:.3f}, {100 * np.mean(a <= 1):.1f} % ≤ 1")
    run(5, "propagate", [
        ("the docstring example", lambda f: f([[1.0, 1.0], [1.0, -1.0]], [[4.0, 0.0], [0.0, 9.0]]),
         mat_is([[13.0, -5.0], [-5.0, 13.0]])),
        ("a 1 × 2 Jacobian (one output)", lambda f: f([[1.0, 1.0]], [[4.0, 0.0], [0.0, 9.0]]), mat_is([[13.0]])),
    ])
    deg2 = math.radians(1.0) ** 2
    run(6, "polar_to_en", [
        ("the docstring example", lambda f: f(1000.0, 90.0, 10.0, 1.0),
         pair_is([1000.0, 0.0], [[100.0, 0.0], [0.0, 1e6 * deg2]],
                 ((lambda x, P: close(x, [0.0, 1000.0], 1e-4), "east and north are swapped: a bearing is clockwise from "
                                                               "NORTH (east = r sin β)"),
                  (lambda x, P: P.shape == (2, 2) and P[1, 1] > 1e5, "the north variance is 57² = 3 283 times too large: "
                                                                     "σβ is still in degrees")))),
        ("due north, 500 m", lambda f: f(500.0, 0.0, 4.0, 2.0),
         pair_is([0.0, 500.0], [[250000 * 4 * deg2, 0.0], [0.0, 16.0]])),
    ])
    run(7, "gate", [
        ("the docstring example (6 m east)", lambda f: f([6.0, 0.0], [[9.0, 0.0], [0.0, 1.0]]),
         bool_is(True, "True expected (a bool, not a number)")),
        ("6 m north", lambda f: f([0.0, 6.0], [[9.0, 0.0], [0.0, 1.0]]),
         bool_is(False, "False expected: d² = 36 — did you compare d (6), not d², with the threshold?")),
        ("d² = 7.29 at p = 0.99, two numbers", lambda f: f([2.7, 0.0], [[1.0, 0.0], [0.0, 1.0]]),
         bool_is(True, "True expected: a 2-D r uses 2 degrees of freedom (chi2_threshold(p, len(r)))")),
        ("one number, d² = 7.29 at p = 0.99", lambda f: f([2.7], [[1.0]]),
         bool_is(False, "False expected: a 1-number r has 1 degree of freedom (6.63 at 99 %): chi2_threshold(p, len(r))")),
    ])
    run(8, "fuse", [
        ("the docstring example", lambda f: f([0.0, 0.0], [[4.0, 0.0], [0.0, 100.0]], [10.0, 10.0],
                                              [[100.0, 0.0], [0.0, 4.0]]),
         pair_is([0.384615, 9.615385], [[3.846154, 0.0], [0.0, 3.846154]],
                 ((lambda x, P: not (np.all(np.isfinite(x)) and np.all(np.isfinite(P))),
                   "nan or inf: did you write 1 / P? It divides each NUMBER, so the zeros become inf — the inverse of "
                   "a matrix is np.linalg.inv(P)"),
                  (lambda x, P: close(x, [9.615385, 0.384615], 1e-4), "x moves towards the WORSE estimate on each axis: "
                                                                       "weigh each x with its OWN information")))),
        ("the same estimate twice", lambda f: f([5.0, 5.0], [[8.0, 2.0], [2.0, 8.0]], [5.0, 5.0], [[8.0, 2.0], [2.0, 8.0]]),
         pair_is([5.0, 5.0], [[4.0, 1.0], [1.0, 4.0]],
                 ((lambda x, P: close(P, np.linalg.inv([[8.0, 2.0], [2.0, 8.0]]) * 2, 1e-4),
                   "P is the SUM of the informations: P is the inverse of that sum"),
                  (lambda x, P: True, "two equal estimates: same x, P halved ([[4, 1], [1, 4]]) — is the inverse a "
                                      "matrix inverse (np.linalg.inv), not 1 / P?")))),
    ])
    run(9, "make_covariance", [
        ("the docstring example", lambda f: f([[13.6, 4.8], [4.8, 6.4]], sigma_up_m=5.0),
         lambda v: None if (isinstance(v, (tuple, list)) and len(v) == 2 and isinstance(v[0], list)
                            and close(v[0], [13.6, 4.8, 0, 4.8, 6.4, 0, 0, 0, 25.0]) and v[1] == 3)
         else "expected ([13.6, 4.8, 0.0, 4.8, 6.4, 0.0, 0.0, 0.0, 25.0], 3): a LIST of 9 numbers and the type"),
        ("nothing known (None)", lambda f: f(None),
         lambda v: None if (isinstance(v, (tuple, list)) and len(v) == 2 and close(v[0], [0.0] * 9) and v[1] == 0)
         else "nine 0.0 and COV_UNKNOWN (0) expected"),
        ("no up σ given", lambda f: f([[9.0, 0.0], [0.0, 4.0]]),
         lambda v: None if (isinstance(v, (tuple, list)) and len(v) == 2 and close(v[0], [9, 0, 0, 0, 4, 0, 0, 0, 36])
                            and v[1] == 1)
         else "expected ([9.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 36.0], 1): the up variance is a guess, so APPROXIMATED"),
        ("an impossible matrix (ρ = 1.5)", lambda f: raises(f, [[25.0, 30.0], [30.0, 16.0]], 3.0),
         lambda v: None if v == "ValueError" else "never publish it: ask is_covariance and raise ValueError"),
    ])
    print("\n".join(rows))
    print("\n(✔ = right on these few cases; ✔ Check my work tests more cases that you have not seen.)")


# ------------------------------------------------------------------------------------------- look
def look():
    pts = np.loadtxt(need_data("static_fixes.csv"), delimiter=",", skiprows=1)
    print(f"static_fixes.csv: {len(pts)} fixes, every {pts[1, 0] - pts[0, 0]:.0f} s; error east "
          f"{pts[:, 1].min():.1f} … {pts[:, 1].max():.1f} m, north {pts[:, 2].min():.1f} … {pts[:, 2].max():.1f} m")
    with open(need_data("judge.json")) as f:
        j = json.load(f)
    print(f"judge.json: prediction covariance {j['P_pred']} m², GPS σ {j['gps_sigma_m']} m, "
          f"{len(j['candidates'])} candidate fixes {', '.join(j['candidates'])}")
    with open(need_data("fusion.csv")) as f:
        rows = list(csv.DictReader(f))
    print(f"fusion.csv: {len(rows)} rows (one per second), columns: {', '.join(rows[0])}")


# ------------------------------------------------------------------------------------------- cloud
def cloud():
    needs("sample_cov", "ellipse")
    pts = np.loadtxt(need_data("static_fixes.csv"), delimiter=",", skiprows=1)[:, 1:]
    P = mat(rk.need_ok(un, "sample_cov", pts), "sample_cov")
    np.set_printoptions(precision=3, suppress=True)
    print(f"{len(pts)} fixes of a receiver standing still. Sample covariance (m²):\n{P}")
    rho = P[0, 1] / math.sqrt(P[0, 0] * P[1, 1]) if P[0, 0] > 0 and P[1, 1] > 0 else float("nan")
    print(f"σE = {math.sqrt(max(P[0, 0], 0)):.2f} m, σN = {math.sqrt(max(P[1, 1], 0)):.2f} m, ρ = {rho:.2f}")
    a, b, ang = ell(P)
    print(f"\n1-sigma ellipse: a = {a:.2f} m, b = {b:.2f} m, long axis at {ang:.1f}° from east")
    cov9 = (float(P[0, 0]), float(P[0, 1]), 0.0, float(P[1, 0]), float(P[1, 1]), 0.0, 0.0, 0.0, 1.0)
    e = est.Estimate("gps", 35.8256, 10.6084, 0.0, cov=cov9, cov_type=est.COV_KNOWN)
    s = est.stated_sigma(e, cfg())
    if s is None:
        sys.exit("stated_sigma() reads no σ from this matrix: is your sample_cov a covariance (symmetric, a·c ≥ b²)?")
    print(f"the judge's one σ (mission 12, √max(a, c)): {s:.2f} m")
    res = {"cloud": {"a_m": round(a, 3), "b_m": round(b, 3), "angle_deg": round(ang, 2), "judge_sigma_m": round(s, 3)}}
    inside = None
    if written("mahalanobis2"):
        dd = np.array([d2(p, P) for p in pts])
        r = np.hypot(pts[:, 0], pts[:, 1])
        print(f"\n{'':22s}{'inside the ellipse':>20s}{'inside a circle of k × ' + format(s, '.2f') + ' m':>32s}"
              f"{'theory (ellipse)':>18s}")
        inside, circ = {}, {}
        for k in (1, 2, 3):
            pe, pc = 100 * np.mean(dd <= k * k), 100 * np.mean(r <= k * s)
            inside[k], circ[k] = pe, pc
            print(f"k = {k} ({k}-sigma):       {pe:17.1f} %{pc:30.1f} %{100 * un.p_inside(k):16.1f} %")
        res["cloud"].update({"inside1_pct": round(inside[1], 2), "inside2_pct": round(inside[2], 2),
                             "inside3_pct": round(inside[3], 2), "circle1_pct": round(circ[1], 2),
                             "circle3_pct": round(circ[3], 2)})
    else:
        print("\n(write TODO 3, mahalanobis2, then run this again: it will count the fixes inside each ellipse)")
    save_results(res)
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(6.4, 6.0))
    ax.scatter(pts[:, 0], pts[:, 1], s=5, alpha=0.5, label="600 fixes")
    for k, ls in ((1, "-"), (2, "--"), (3, ":")):
        ex, ny = outline(*ell(P, k=k))
        lab = f"{k}-sigma ellipse" + (f" ({inside[k]:.0f} % inside)" if inside else "")
        ax.plot(ex, ny, "tab:red", ls=ls, lw=1.4, label=lab)
    t = np.linspace(0, 2 * math.pi, 100)
    ax.plot(s * np.cos(t), s * np.sin(t), color="grey", lw=1.0, label=f"circle of the judge's σ ({s:.2f} m)")
    ax.set_aspect("equal")
    ax.set_xlabel("east error (m)")
    ax.set_ylabel("north error (m)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("A receiver standing still: the cloud and its ellipses", fontsize=10)
    fig.tight_layout()
    fig.savefig("out/cloud.png", dpi=90)
    rk.saved("out/cloud.png")


# ------------------------------------------------------------------------------------------- radar
def radar(rest):
    needs("polar_to_en", "propagate", "sample_cov", "ellipse", "mahalanobis2")
    wide = bool(rest) and rest[0] == "wide"
    r0, b0, sr, sb = 3000.0, 300.0, 8.0, (10.0 if wide else 1.0)
    v = rk.need_ok(un, "polar_to_en", r0, b0, sr, sb)
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"polar_to_en() must return two things (en, P), but it returned {v!r}")
    en, P = vec(v[0], "polar_to_en"), mat(v[1], "polar_to_en")
    rng = np.random.default_rng(27)
    r = r0 + sr * rng.standard_normal(20000)
    b = np.radians(b0 + sb * rng.standard_normal(20000))
    mc = np.stack([r * np.sin(b), r * np.cos(b)], axis=1)
    Pm = mat(rk.need_ok(un, "sample_cov", mc), "sample_cov")
    a1, b1, g1 = ell(P)
    a2, b2, g2 = ell(Pm)
    print(f"A target at {r0:.0f} m, bearing {b0:.0f}°; σ range {sr:.0f} m, σ bearing {sb:g}°\n")
    print(f"position: east {en[0]:.1f} m, north {en[1]:.1f} m (draws' mean: {mc[:, 0].mean():.1f}, {mc[:, 1].mean():.1f})")
    print(f"{'':26s}{'a (m)':>10s}{'b (m)':>10s}{'angle (°)':>12s}")
    print(f"{'J P Jᵀ (your polar_to_en)':26s}{a1:10.1f}{b1:10.1f}{g1:12.1f}")
    print(f"{'20 000 draws (sample_cov)':26s}{a2:10.1f}{b2:10.1f}{g2:12.1f}")
    thr = un.chi2_threshold(0.95)
    ins = 100 * np.mean([d2(x - en, P) <= thr for x in mc])
    print(f"\ndraws inside the 95 % ellipse of J P Jᵀ: {ins:.1f} %")
    key = "radar_wide" if wide else "radar"
    save_results({key: {"jpj_a_m": round(a1, 2), "jpj_b_m": round(b1, 2), "jpj_angle_deg": round(g1, 2),
                        "mc_a_m": round(a2, 2), "mc_b_m": round(b2, 2), "inside95_pct": round(ins, 2)}})
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(6.6, 6.0))
    ax.scatter(mc[::4, 0], mc[::4, 1], s=2, alpha=0.3, label="5 000 of the 20 000 draws")
    k = math.sqrt(thr)
    ex, ny = outline(*ell(P, k=k), centre=en)
    ax.plot(ex, ny, "tab:red", lw=1.6, label=f"95 % ellipse of J P Jᵀ ({ins:.0f} % of draws inside)")
    ex, ny = outline(*ell(Pm, k=k), centre=mc.mean(axis=0))
    ax.plot(ex, ny, "k--", lw=1.0, label="95 % ellipse of the draws' sample_cov")
    ax.plot(*en, "r+", ms=12)
    ax.set_aspect("equal")
    ax.set_xlabel("east (m) — the radar is at (0, 0), far to the lower right")
    ax.set_ylabel("north (m)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    ax.set_title(f"Range ± {sr:.0f} m, bearing ± {sb:g}°: straight-line maths vs reality", fontsize=10)
    fig.tight_layout()
    name = "out/radar_wide.png" if wide else "out/radar.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


# ------------------------------------------------------------------------------------------- judge
def judge():
    needs("mahalanobis2", "gate", "ellipse")
    with open(need_data("judge.json")) as f:
        j = json.load(f)
    R = j["gps_sigma_m"] ** 2 * np.eye(2)
    S = np.array(j["P_pred"]) + R
    S0 = np.array(j["P_pred_never_grown"]) + R
    circle = j["circle_rule_m"]
    print(j["story"])
    print(f"S = P_pred + R = {np.round(S, 1).tolist()} m²   (R: GPS σ {j['gps_sigma_m']:g} m)\n")
    print(f"{'fix':4s}{'east':>8s}{'north':>8s}{'dist (m)':>10s}{'d²':>9s}{'gate 99 %':>11s}{'gate 95 %':>11s}"
          f"{'never-grown':>13s}{'circle ' + format(circle, '.0f') + ' m':>14s}")
    out = {}
    for name, x in j["candidates"].items():
        dist = math.hypot(*x)
        dd = d2(x, S)
        g99, g95, g0 = gate(x, S, 0.99), gate(x, S, 0.95), gate(x, S0, 0.99)
        yes = lambda ok: "accept" if ok else "REFUSE"         # noqa: E731
        print(f"{name:4s}{x[0]:8.1f}{x[1]:8.1f}{dist:10.1f}{dd:9.2f}{yes(g99):>11s}{yes(g95):>11s}{yes(g0):>13s}"
              f"{yes(dist <= circle):>14s}")
        out[name] = {"d2": round(dd, 3), "g99": g99, "g95": g95, "never_grown": g0}
    n99 = sum(v["g99"] for v in out.values())
    print(f"\nyour gate at 99 % accepts {n99} of {len(out)}; 'never-grown' = a predictor that kept σ 5 m for 40 s")
    save_results({"judge": {"fixes": out, "n_accept_99": n99}})
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(6.6, 6.0))
    k = math.sqrt(un.chi2_threshold(0.99))
    ex, ny = outline(*ell(S, k=k))
    ax.plot(ex, ny, "tab:red", lw=1.6, label="your 99 % gate (P_pred + R)")
    ex, ny = outline(*ell(S0, k=k))
    ax.plot(ex, ny, "tab:purple", lw=1.2, label="gate of the never-grown predictor")
    t = np.linspace(0, 2 * math.pi, 100)
    ax.plot(circle * np.cos(t), circle * np.sin(t), color="grey", ls="--", lw=1.0, label=f"circle {circle:.0f} m")
    for name, x in j["candidates"].items():
        ax.plot(*x, "o", color="tab:green" if out[name]["g99"] else "k", ms=7)
        ax.annotate(name, x, textcoords="offset points", xytext=(6, 4), fontsize=10)
    tb = math.radians(j["track_bearing_deg"])
    ax.annotate("", xy=(120 * math.sin(tb), 120 * math.cos(tb)), xytext=(0, 0),
                arrowprops=dict(arrowstyle="->", color="tab:blue"))
    ax.text(70 * math.sin(tb) + 6, 70 * math.cos(tb) + 8, "track", color="tab:blue", fontsize=8)
    ax.plot(0, 0, "k+", ms=12)
    ax.set_aspect("equal")
    ax.set_xlabel("east of the prediction (m)")
    ax.set_ylabel("north of the prediction (m)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    ax.set_title("After 40 s on visual odometry: which fixes are plausible?", fontsize=10)
    fig.tight_layout()
    fig.savefig("out/judge.png", dpi=90)
    rk.saved("out/judge.png")


# ------------------------------------------------------------------------------------------- attack
def attack():
    needs("gate", "ellipse")
    with open(need_data("judge.json")) as f:
        j = json.load(f)
    S = np.array(j["P_pred"]) + j["gps_sigma_m"] ** 2 * np.eye(2)
    print("The attacker moves a fake fix away from the prediction in one direction at a time and finds the")
    print("largest offset YOUR gate (99 %) still accepts (bisection, to 0.1 m).\n")
    lim = []
    for brg in range(0, 360, 5):
        u = np.array([math.sin(math.radians(brg)), math.cos(math.radians(brg))])
        if not gate((0.001 * u).tolist(), S):
            sys.exit("your gate refuses even a 1 mm offset: is the comparison the right way round (d² ≤ threshold)?")
        lo, hi = 0.0, 5000.0
        if gate((hi * u).tolist(), S):
            sys.exit(f"your gate accepts a fake fix 5 km away (bearing {brg}°): is it really comparing d² "
                     "(not d, not a distance) with the χ² threshold?")
        while hi - lo > 0.1:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if gate((mid * u).tolist(), S) else (lo, mid)
        lim.append((brg, lo))
    longest = max(lim, key=lambda x: x[1])
    shortest = min(lim, key=lambda x: x[1])
    print(f"longest accepted offset:  {longest[1]:7.1f} m  at bearing {longest[0]:3d}°")
    print(f"shortest accepted offset: {shortest[1]:7.1f} m  at bearing {shortest[0]:3d}°")
    print("(compare with your PREDICT_ATTACK; you can check it with your own ellipse(S, k=math.sqrt(9.21)))")
    save_results({"attack": {"max_m": round(longest[1], 1), "max_bearing_deg": longest[0],
                             "min_m": round(shortest[1], 1), "min_bearing_deg": shortest[0]}})
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(6.2, 6.0))
    xs = [d * math.sin(math.radians(g)) for g, d in lim] + [lim[0][1] * math.sin(0)]
    ys = [d * math.cos(math.radians(g)) for g, d in lim] + [lim[0][1]]
    ax.fill(xs, ys, color="tab:red", alpha=0.15, label="offsets your gate accepts")
    ax.plot(xs, ys, "tab:red", lw=1.2)
    for g, d in (longest, shortest):
        tip = (d * math.sin(math.radians(g)), d * math.cos(math.radians(g)))
        ax.annotate("", xy=tip, xytext=(0, 0), arrowprops=dict(arrowstyle="->"))
        ax.annotate(f"{d:.0f} m (bearing {g}°)", xy=tip, xytext=(tip[0] * 0.55 + 6, tip[1] * 0.55 + 6), fontsize=9)
    ax.plot(0, 0, "k+", ms=12)
    ax.set_aspect("equal")
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    ax.set_title("Where can a fake fix hide? (the attacker's map of your gate)", fontsize=10)
    fig.tight_layout()
    fig.savefig("out/attack.png", dpi=90)
    rk.saved("out/attack.png")


# ------------------------------------------------------------------------------------------- fuse
POLICIES = (("GPS alone", "gps", None), ("vision alone", "vis", None), ("fuse every pair", "all", None),
            ("gate, then fuse", "gated", None), ("gate, then fuse — vision states 5 m", "gated", 5.0))


def run_policy(rows, policy, vis_sigma=None, p=0.99):
    """Errors (m), coverage flags and gate counts of one policy over a drive. Uses YOUR gate, fuse, mahalanobis2."""
    thr = un.chi2_threshold(0.95)
    errs, cover, caught, false_alarms, xs = [], [], 0, 0, []
    for row in rows:
        truth = np.array([float(row["true_e"]), float(row["true_n"])])
        g, Pg = np.array([float(row["gps_e"]), float(row["gps_n"])]), gps_cov(row)
        v = np.array([float(row["vis_e"]), float(row["vis_n"])])
        s = vis_sigma if vis_sigma is not None else float(row["vis_sigma_m"])
        Pv = s * s * np.eye(2)
        wrong = row.get("vis_wrong") == "1"
        if policy == "gps":
            x, P = g, Pg
        elif policy == "vis":
            x, P = v, Pv
        elif policy == "all":
            x, P = fuse(g, Pg, v, Pv)
        else:
            if gate((v - g).tolist(), (Pg + Pv).tolist(), p):
                x, P = fuse(g, Pg, v, Pv)
            else:
                x, P = g, Pg
                caught += wrong
                false_alarms += not wrong
        e = x - truth
        errs.append(math.hypot(*e))
        cover.append(d2(e, P) <= thr)
        xs.append(x)
    errs = np.array(errs)
    return {"rms_m": float(np.sqrt(np.mean(errs ** 2))), "p95_m": float(np.percentile(errs, 95)),
            "max_m": float(errs.max()), "cover_pct": float(100 * np.mean(cover)), "caught": int(caught),
            "false_alarms": int(false_alarms), "errs": errs, "xs": np.array(xs)}


def fuse_cmd():
    needs("fuse", "gate", "mahalanobis2")
    with open(need_data("fusion.csv")) as f:
        rows = list(csv.DictReader(f))
    n_wrong = sum(r["vis_wrong"] == "1" for r in rows)
    print(f"{len(rows)} s of driving: open sky, a street canyon (t 120–279 s), open sky. Vision states 15 m; "
          f"{n_wrong} of its fixes are wrong matches.\n")
    print(f"{'policy':38s}{'RMS (m)':>9s}{'p95 (m)':>9s}{'max (m)':>9s}{'coverage':>10s}{'wrong caught':>14s}"
          f"{'good refused':>14s}")
    res, runs = {}, {}
    for label, pol, vs in POLICIES:
        r = run_policy(rows, pol, vs)
        runs[label] = r
        gated = pol == "gated"
        print(f"{label:38s}{r['rms_m']:9.1f}{r['p95_m']:9.1f}{r['max_m']:9.1f}{r['cover_pct']:9.1f} %"
              f"{(str(r['caught']) + ' / ' + str(n_wrong)) if gated else '—':>14s}"
              f"{str(r['false_alarms']) if gated else '—':>14s}")
        res[label] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k not in ("errs", "xs")}
    print("\ncoverage = the share of seconds where the truth is inside the policy's own 95 % ellipse "
          "(an honest policy: about 95 %)")
    save_results({"fuse": res})
    plt = plt_ready()
    if plt is None:
        return
    t = np.array([float(r["t_s"]) for r in rows])
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.0, 6.2), sharex=True)
    for label, color in (("GPS alone", "tab:blue"), ("fuse every pair", "tab:orange"), ("gate, then fuse", "tab:green")):
        ax1.plot(t, np.maximum(runs[label]["errs"], 0.3), color=color, lw=1.0, label=label)
    ax1.axvspan(120, 280, color="grey", alpha=0.12)
    ax1.set_yscale("log")
    ax1.text(200, 0.4, "street canyon", ha="center", fontsize=8, color="grey")
    ax1.set_ylabel("error (m, log scale)")
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(alpha=0.3)
    w = [i for i, r in enumerate(rows) if r["vis_wrong"] == "1"]
    ax2.plot(t, runs["gate, then fuse"]["errs"], color="tab:green", lw=1.0, label="gate, then fuse (vision honest)")
    ax2.plot(t, runs["gate, then fuse — vision states 5 m"]["errs"], color="tab:red", lw=0.8,
             label="gate, then fuse (vision states 5 m)")
    ax2.plot(t[w], np.zeros(len(w)), "kx", ms=5, label="wrong vision matches")
    ax2.axvspan(120, 280, color="grey", alpha=0.12)
    ax2.set_xlabel("time (s)")
    ax2.set_ylabel("error (m)")
    ax2.legend(fontsize=8, loc="upper left")
    ax2.grid(alpha=0.3)
    fig.suptitle("Fusing GPS with day vision: error of each policy", fontsize=10)
    fig.tight_layout()
    fig.savefig("out/fuse.png", dpi=90)
    rk.saved("out/fuse.png")


# ------------------------------------------------------------------------------------------- publish
def publish():
    needs("make_covariance", "ellipse", "fuse", "gate")
    c = cfg()
    with open(need_data("fusion.csv")) as f:
        rows = list(csv.DictReader(f))

    def contract(P2, label):
        v = rk.need_ok(un, "make_covariance", P2)
        if not (isinstance(v, (tuple, list)) and len(v) == 2):
            sys.exit(f"make_covariance() must return two things (cov9, cov_type), but it returned {v!r}")
        cov9, kind = v
        if not (isinstance(cov9, list) and len(cov9) == 9 and all(type(x) is float for x in cov9)):
            sys.exit(f"make_covariance() must return a list of 9 Python floats, got {cov9!r} "
                     "(float(x) turns a numpy number or an int into one)")
        e = est.Estimate("gps", 35.8256, 10.6084, 0.0, cov=tuple(cov9), cov_type=kind)
        ok, why = est.is_covariance(cov9)
        s = est.stated_sigma(e, c)
        state, reason = est.classify(s, c)
        a = ell(P2)[0]
        print(f"{label}\n  cov9 = {[round(x, 1) for x in cov9]}, type {kind}")
        print(f"  is_covariance: {ok} ({why}); the judge's σ = {s:.1f} m → {state} ({reason}); "
              f"the long axis of the ellipse: {a:.1f} m\n" if s is not None else
              f"  is_covariance: {ok} ({why}); the judge reads no σ → {state} ({reason})\n")
        return s, a, state

    i = 160
    row = rows[i]
    Pg = gps_cov(row)
    print(f"t = {row['t_s']} s, in the street canyon.\n")
    s_gps, a_gps, st_gps = contract(Pg, "GPS alone:")
    g = np.array([float(row["gps_e"]), float(row["gps_n"])])
    v = np.array([float(row["vis_e"]), float(row["vis_n"])])
    Pv = float(row["vis_sigma_m"]) ** 2 * np.eye(2)
    if gate((v - g).tolist(), (Pg + Pv).tolist()):
        _, Pf = fuse(g, Pg, v, Pv)
        s_f, a_f, _ = contract(Pf, "gate, then fuse:")
    else:
        print("(your gate refused vision at this second: nothing to fuse)\n")
        s_f = a_f = None
    false_fix = 0
    for r in rows:
        P2 = gps_cov(r)
        cov9, kind = rk.need_ok(un, "make_covariance", P2)
        s = est.stated_sigma(est.Estimate("gps", 35.8, 10.6, 0.0, cov=tuple(cov9), cov_type=kind), c)
        state, _ = est.classify(s, c)
        if state == "FIX" and ell(P2)[0] > float(c["fix_max_sigma_m"]):
            false_fix += 1
    print(f"GPS alone over the whole drive: {false_fix} seconds shown FIX (judge's σ ≤ {c['fix_max_sigma_m']:g} m) "
          f"while the long axis of the ellipse is longer than {c['fix_max_sigma_m']:g} m")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            bad = un.make_covariance([[25.0, 30.0], [30.0, 16.0]], 3.0)
        print(f"\n⚠ make_covariance published the impossible matrix [[25, 30], [30, 16]]: {bad!r} — it must raise "
              "ValueError (lesson §7)")
    except ValueError as e:
        print(f"\nthe impossible matrix [[25, 30], [30, 16]] is refused: ValueError: {e}")
    save_results({"publish": {"t_s": float(row["t_s"]), "gps_judge_sigma_m": round(s_gps, 2) if s_gps else None,
                              "gps_long_axis_m": round(a_gps, 2), "gps_state": st_gps,
                              "fused_judge_sigma_m": round(s_f, 2) if s_f else None,
                              "fused_long_axis_m": round(a_f, 2) if a_f else None, "false_fix_s": false_fix}})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    m, rest = a[0], a[1:]
    table = {"test": test, "look": look, "cloud": cloud, "radar": lambda: radar(rest), "judge": judge,
             "attack": attack, "fuse": fuse_cmd, "publish": publish}
    if m not in table:
        print(__doc__)
        sys.exit(1)
    table[m]()
