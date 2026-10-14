"""run_kalman.py — runs YOUR functions of navera_lite/kalman.py on heights and on a flight, and draws the results.

    python3 run_kalman.py test               check each function on its docstring example (and a few traps)
    python3 run_kalman.py grow               40 s with no measurement: how fast does σ grow?          (Step 1)
    python3 run_kalman.py step               one predict + one update, the numbers of Step 2           (Step 2)
    python3 run_kalman.py race               your Height1D against the course's reference_heights.csv (Step 3)
    python3 run_kalman.py heights A          your Height1D with climb_accel = A m/s² (e.g. 0.05, 5)    (Step 4)
    python3 run_kalman.py track Q [P]        the 2-D tracker with q = Q m²/s⁴, gate probability P      (Steps 6–7)
    python3 run_kalman.py sweep [P]          the tracker for seven values of q (gate P, default 0.99)   (Step 8)

Data: /data/academy/28-kalman/ (read only). Pictures are saved in out/ — click them in the 📝 Code tab.
"""
import csv
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = os.environ.get("KALMAN_DATA", "/data/academy/28-kalman")
kf = rk.load_student("navera_lite.kalman")
SWEEP_Q = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
WRONG_M = 50.0                       # a fix farther than this from the truth is a wrong fix (the runner knows the truth)


def need_data(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: the course data is not mounted here (tell your teacher)")
    return path


def stub(name):
    f = getattr(kf, name, None)
    if f is None:
        sys.exit(f"{name}() does not exist in navera_lite/kalman.py — did you rename it?")
    return rk.is_stub(f)


def needs(*names):
    for n in names:
        if n == "Height1D.update":
            if getattr(kf, "Height1D", None) is None:
                sys.exit("class Height1D does not exist in navera_lite/kalman.py — did you rename it?")
            if rk.is_stub(kf.Height1D.update):
                sys.exit("Height1D.update() is not written yet: write TODO 4 in navera_lite/kalman.py first "
                         "(python3 run_kalman.py test shows which TODOs work)")
            continue
        if stub(n):
            sys.exit(f"{n}() is not written yet: write its TODO in navera_lite/kalman.py first "
                     "(python3 run_kalman.py test shows which ones work)")


def arr(v, shape, fn, what):
    """The student's result as a float array of the given shape, or a plain message and exit."""
    if v is None:
        sys.exit(f"{fn}() returned None for {what}: every path must end with a `return`")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() should give {what} as numbers (a numpy array), got {v!r}")
    if a.shape != shape:
        sys.exit(f"{fn}() gives {what} of shape {a.shape}, expected {shape}")
    if not np.all(np.isfinite(a)):
        sys.exit(f"{fn}() gives {what} with nan or inf: {a}")
    return a


def model(dt, q, dims):
    v = rk.need_ok(kf, "cv_model", dt, q, dims=dims)
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"cv_model() must return two arrays (F, Q), got {v!r}")
    n = 2 * dims
    return arr(v[0], (n, n), "cv_model", "F"), arr(v[1], (n, n), "cv_model", "Q")


def predict(x, P, F, Q):
    v = rk.need_ok(kf, "kf_predict", x, P, F, Q)
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"kf_predict() must return two things (x, P), got {v!r}")
    n = len(x)
    return arr(v[0], (n,), "kf_predict", "x"), arr(v[1], (n, n), "kf_predict", "P")


def update(x, P, z, H, R):
    v = rk.need_ok(kf, "kf_update", x, P, z, H, R)
    if not (isinstance(v, (tuple, list)) and len(v) == 3):
        sys.exit(f"kf_update() must return three things (x, P, nis), got {v!r}")
    n = len(x)
    nis = v[2]
    if isinstance(nis, bool) or not isinstance(nis, (int, float, np.floating)):
        try:
            nis = float(np.asarray(nis).reshape(-1)[0]) if np.size(nis) == 1 else None
        except (TypeError, ValueError):
            nis = None
        if nis is None:
            sys.exit(f"kf_update()'s third value (nis) must be ONE number, got {v[2]!r}")
    return arr(v[0], (n,), "kf_update", "x"), arr(v[1], (n, n), "kf_update", "P"), float(nis)


def plt_ready():
    plt = rk.plt_or_none()
    if plt is not None:
        os.makedirs("out", exist_ok=True)
    return plt


def read_heights():
    with open(need_data("heights.csv")) as f:
        return [(float(r["t_s"]), float(r["height_m"]), float(r["sigma_m"]), r["source"], float(r["true_height_m"]))
                for r in csv.DictReader(f)]


def read_track():
    with open(need_data("track.csv")) as f:
        rows = list(csv.DictReader(f))
    t = [float(r["t_s"]) for r in rows]
    truth = np.array([[float(r["true_e"]), float(r["true_n"])] for r in rows])
    zs = [None if r["z_e"] == "" else (float(r["z_e"]), float(r["z_n"])) for r in rows]
    return t, truth, zs, float(rows[0]["sigma_m"])


def rms(a):
    a = np.asarray(a, dtype=float)
    return math.sqrt(float(np.mean(a * a)))


# ------------------------------------------------------------------------------------------- test
def attempt(fn, name):
    import contextlib
    import io
    import traceback
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            v = fn()
    except NotImplementedError:
        return None, "it is not written yet"
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith(os.path.join("navera_lite", "kalman.py"))]
        where = f" (navera_lite/kalman.py line {tb[-1].lineno}, in {tb[-1].name}())" if tb else ""
        s = str(e)
        hint = rk._hint(e)
        if "matmul" in s or "not aligned" in s or "mismatch in its core dimension" in s:
            hint = (" — two matrices that cannot be multiplied: print their .shape (F is n × n, H is m × n, Hᵀ = H.T; "
                    "a list has no .T: np.asarray first)")
        elif "Singular matrix" in s:
            hint = " — a matrix with no inverse: is S = H P Hᵀ + R? (R adds to it, so it is never singular)"
        elif "object has no attribute 'T'" in s:
            hint = " — a list has no .T: convert the inputs with np.asarray(…, dtype=float) first"
        return None, f"{name}() stopped with {type(e).__name__}: {e}{where}{hint}"
    if v is None:
        return None, f"{name}() returned None: every path must end with a `return`"
    return v, None


def test():
    cases = []

    def mats(want, msgs=(), tol=1e-6):
        def chk(v):
            if not (isinstance(v, (tuple, list)) and len(v) == len(want)):
                return False, f"expected {len(want)} values, got {v!r}"
            try:
                got = [np.asarray(a, dtype=float) for a in v]
            except (TypeError, ValueError):
                return False, f"expected numbers / numpy arrays, got {v!r}"
            for bad, m in msgs:
                if all(g.shape == np.shape(b) and np.allclose(g, b, atol=tol) for g, b in zip(got, bad)):
                    return False, m
            for i, (g, w) in enumerate(zip(got, want)):
                if g.shape != np.shape(w):
                    return False, f"value {i + 1} has shape {g.shape}, expected {np.shape(w)}"
            return all(np.allclose(g, w, atol=tol) for g, w in zip(got, want)), None
        return chk

    def number(want, tol, msgs=()):
        def chk(v):
            try:
                x = float(v)
            except (TypeError, ValueError):
                return False, f"expected one number, got {v!r}"
            for bad, m in msgs:
                if abs(x - bad) <= tol:
                    return False, m
            return abs(x - want) <= tol, None
        return chk

    F05 = [[1.0, 0.5], [0.0, 1.0]]
    cases.append((1, "cv_model", "cv_model(0.5, 4.0, dims=1) (docstring)", lambda: kf.cv_model(0.5, 4.0, dims=1),
                  mats([F05, [[0.0625, 0.25], [0.25, 1.0]]], (
                      ([F05, [[1 / 24, 0.125], [0.125, 0.5]]], "Q = q·[[dt³/3, dt²/2], [dt²/2, dt]] is another model "
                       "(continuous noise): this course's Q is q·g·gᵀ with g = [dt²/2, dt] (lesson §2)"),
                      ([F05, [[0.015625, 0.0625], [0.0625, 0.25]]], "Q is not multiplied by q"),
                      ([F05, [[0.25, 0.5], [0.5, 1.0]]], "dt²/2 is squared wrong: g = [dt²/2, dt], Q = q·g·gᵀ, so "
                       "Q[0][0] = q·dt⁴/4")))))

    def big_chk(v):
        if not (isinstance(v, (tuple, list)) and len(v) == 2):
            return False, f"expected (F, Q), got {v!r}"
        F, Q = (np.asarray(a, dtype=float) for a in v)
        if F.shape != (4, 4) or Q.shape != (4, 4):
            return False, f"dims=2 should give 4 × 4 matrices, got {F.shape} and {Q.shape}"
        if abs(F[0, 1] - 0.5) < 1e-9 and abs(F[0, 2]) < 1e-9:
            return False, ("the state order is [e, n, v_e, v_n] (positions first): F[0, 2] = dt links east to v_east "
                           "— np.kron(F1, np.eye(2)), with F1 FIRST")
        return (abs(F[0, 2] - 0.5) < 1e-9 and abs(Q[1, 3] - 0.25) < 1e-9 and abs(Q[0, 1]) < 1e-9
                and abs(Q[2, 2] - 1.0) < 1e-9), f"F[0, 2] = {F[0, 2]}, Q[1, 3] = {Q[1, 3]}, Q[0, 1] = {Q[0, 1]}"
    cases.append((1, "cv_model", "cv_model(0.5, 4.0) — two axes (docstring)", lambda: kf.cv_model(0.5, 4.0), big_chk))

    F1 = np.array([[1.0, 1.0], [0.0, 1.0]])
    Q1 = 0.25 * np.array([[0.25, 0.5], [0.5, 1.0]])
    cases.append((2, "kf_predict", "kf_predict([80, 2], diag(9, 4), F, Q) (docstring)",
                  lambda: kf.kf_predict([80.0, 2.0], [[9.0, 0.0], [0.0, 4.0]], F1, Q1),
                  mats([[82.0, 2.0], [[13.0625, 4.125], [4.125, 4.25]]], (
                      ([[82.0, 2.0], [[13.0, 4.0], [4.0, 4.0]]], "Q is not added: P = F P Fᵀ + Q"),
                      ([[82.0, 2.0], [[9.0625, 0.125], [0.125, 4.25]]], "P is not moved by F: P = F P Fᵀ + Q"),
                      ([[82.0, 2.0], [[9.0625, 13.125], [0.125, 4.25]]], "F P Fᵀ: the transpose is missing (F @ P @ F)")))))
    def plain_lists(v):
        ok, note = mats([[82.0, 2.0], [[13.0625, 4.125], [4.125, 4.25]]], (
            ([[82.0, 2.0], [[9.0625, 13.125], [0.125, 4.25]]], "F P Fᵀ: the transpose is missing (F @ P @ F)"),
            ([[82.0, 2.0], [[13.0, 4.0], [4.0, 4.0]]], "Q is not added: P = F P Fᵀ + Q")))(v)
        return ok, note
    cases.append((2, "kf_predict", "kf_predict with plain lists (F and Q too)",
                  lambda: kf.kf_predict([80.0, 2.0], [[9.0, 0.0], [0.0, 4.0]], F1.tolist(), Q1.tolist()),
                  plain_lists))
    cases.append((3, "kf_update", "kf_update([82, 2], P, [85], [[1, 0]], [[2.25]]) (docstring)",
                  lambda: kf.kf_update([82.0, 2.0], [[13.0625, 4.125], [4.125, 4.25]], [85.0], [[1.0, 0.0]], [[2.25]]),
                  mats([[84.5591837, 2.8081633], [[1.9193878, 0.6061224], [0.6061224, 3.1387755]], 0.5877551], (
                      ([[84.5591837, 2.8081633], [[1.9193878, 0.6061224], [0.6061224, 3.1387755]], 4.0],
                       "nis divides by R only: nis = νᵀ S⁻¹ ν with S = H P Hᵀ + R"),
                      ([[84.5591837, 2.8081633], [[1.9193878, 0.6061224], [0.6061224, 3.1387755]], 0.6889952],
                       "nis divides by the predicted P only: S = H P Hᵀ + R (R too)"),
                      ([[84.5591837, 2.8081633], [[1.9193878, 0.6061224], [0.6061224, 3.1387755]], 0.7666],
                       "nis is √(νᵀ S⁻¹ ν): no square root, it is a d² (mission 27)"),
                      ([[84.5591837, 2.8081633], [[13.0625, 4.125], [4.125, 4.25]], 0.5877551],
                       "P did not change: after the update P = (I − K H) P"),
                  ), tol=1e-5)))

    def h1d():
        f = kf.Height1D()
        a = f.update(0.0, 80.0, 3.0)
        b = f.update(1.0, 83.0, 1.5)
        c = f.update(2.0, 0.0, 1.5)
        return a, b, c

    def h1d_chk(v):
        try:
            a, b, c = [None if x is None else (float(x[0]), float(x[1])) for x in v]
        except (TypeError, ValueError, IndexError):
            return False, f"update() should return (height, sigma), got {v!r}"
        if a is None or b is None or c is None:
            return False, "update() returned None for a usable height: return (height, σ) as two floats"
        if abs(a[1] - 9.0) < 1e-9:
            return False, "the first σ is 9.0: that is the variance; return σ = √P[0][0]"
        if abs(a[0] - 80.0) > 1e-9 or abs(a[1] - 3.0) > 1e-9:
            return False, f"the first height starts the filter: (80.0, 3.0) expected, got {a}"
        if abs(b[0] - 82.5591837) > 1e-6 and abs(b[0] - 82.5591837) < 0.5:
            return False, (f"second update: ({b[0]:.4f}, {b[1]:.4f}), expected (82.5592, 1.3854) — close, but not the "
                           "same filter: check the start (x = [h, 0.0], P = diag(σ², 4.0)), q = climb_accel² (not "
                           "climb_accel) and R = [[σ²]] (a variance)")
        if not (abs(b[0] - 82.5591837) < 1e-6 and abs(b[1] - 1.3854197) < 1e-6):
            return False, f"second update: (82.5592, 1.3854) expected, got ({b[0]:.4f}, {b[1]:.4f})"
        if abs(c[0] - b[0]) > 1e-12 or abs(c[1] - b[1]) > 1e-12:
            return False, f"a height of 0.0 is 'no reading': nothing changes, return the current (height, σ); got {c}"
        return True, None
    cases.append((4, "Height1D.update", "Height1D: 80 m, then 83 m, then 0.0 (docstring)", h1d, h1d_chk))

    def noread():
        f = kf.Height1D()
        a = f.update(0.0, 0.0, 3.0)
        b = f.update(1.0, float("nan"), 3.0)
        c = f.update(2.0, 80.0, 3.0)
        return [a, b, c]

    def noread_chk(v):
        a, b, c = v
        if a is not None:
            return False, f"the first call is 'no reading' (0.0) and the filter has no state yet: return None, got {a}"
        if b is not None:
            return False, ("a nan height must be ignored too: nan > 0 is False, but nan <= 0 is False as well — test "
                           f"`not h > 0`; got {b}")
        if c is None or abs(float(c[0]) - 80.0) > 1e-9 or abs(float(c[1]) - 3.0) > 1e-9:
            return False, f"the first USABLE height (80 m) starts the filter: (80.0, 3.0) expected, got {c}"
        return True, None
    cases.append((4, "Height1D.update", "Height1D: 0.0 and nan before the first height, then 80 m", noread, noread_chk))

    def back():
        f = kf.Height1D()
        f.update(5.0, 80.0, 3.0)
        try:
            f.update(4.0, 81.0, 3.0)
        except ValueError:
            return "ValueError"
        return "no error"
    cases.append((4, "Height1D.update", "Height1D: a time that goes backwards", back,
                  lambda v: (v == "ValueError", "a time before the filter's time must raise ValueError")))
    cases.append((5, "nees", "nees([3, −1], diag(4, 1)) (docstring)", lambda: kf.nees([3.0, -1.0], [[4.0, 0.0], [0.0, 1.0]]),
                  number(3.25, 1e-9, ((37.0, "errᵀ P err: the INVERSE of P is missing (np.linalg.solve(P, err))"),
                                      (math.sqrt(3.25), "no square root: NEES is a squared distance"),
                                      (1.625, "do not divide by n: the AVERAGE over many steps is n")))))
    cases.append((5, "nees", "nees([2], [[4]]) (docstring)", lambda: kf.nees([2.0], [[4.0]]), number(1.0, 1e-9)))

    def rf():
        return kf.run_filter([0.0, 1.0, 2.0], [(0.0, 0.0), None, (30.0, 0.0)], 5.0, 1.0)

    def rf_chk(r):
        if not isinstance(r, dict):
            return False, f"run_filter() must return a dict of lists, got {type(r).__name__}"
        for k in ("x", "P", "d2", "accepted"):
            if k not in r:
                return False, f"the result has no key {k!r}"
            if len(r[k]) != 3:
                return False, f"r[{k!r}] has {len(r[k])} entries for 3 times (one per time)"
        if r["d2"][0] is not None:
            return False, "d2[0] must be None: the first fix starts the filter, it is not compared with anything"
        if r["d2"][1] is not None or r["accepted"][1] is not None:
            return False, "at a time with no fix (None), d2 and accepted are None (predict only)"
        x1 = np.asarray(r["x"][1], dtype=float)
        if x1.shape != (4,) or not np.allclose(x1, 0.0):
            return False, f"after a time with no fix, x is the prediction: [0, 0, 0, 0] here, got {x1}"
        if r["d2"][2] is None:
            return False, "d2[2] is None: a fix arrived at t = 2 s"
        d2 = float(r["d2"][2])
        if abs(d2 - 0.5446293) > 1e-5:
            if abs(d2 - 1.9989) < 1e-3:
                return False, ("d2[2] = 1.9989: the prediction at t = 1 s (no fix) was skipped — predict at EVERY "
                               "time, then update only if there is a fix")
            if abs(d2 - 1.2163) < 2e-3:
                return False, "d2 looks like it skipped a prediction: predict at EVERY time, also when there is no fix"
            return False, f"d2[2] = {d2:.4f}, expected 0.5446 (the nis of kf_update)"
        if r["accepted"] != [True, None, True]:
            return False, f"accepted = {r['accepted']}, expected [True, None, True]"
        x2 = np.asarray(r["x"][2], dtype=float)
        return bool(abs(x2[2] - 14.559758) < 1e-4 and abs(x2[0] - 29.546142) < 1e-4), f"x[2] = {np.round(x2, 4)}"
    cases.append((7, "run_filter", "run_filter: a fix, a gap, a fix (docstring)", rf, rf_chk))

    def rfg():
        return kf.run_filter([0.0, 1.0, 2.0], [(0.0, 0.0), None, (30.0, 0.0)], 5.0, 1.0, gate_p=0.2)

    def rfg_chk(r):
        if not isinstance(r, dict) or "accepted" not in r:
            return False, f"run_filter() must return a dict of lists, got {r!r}"
        if r["accepted"] != [True, None, False]:
            return False, (f"accepted = {r['accepted']}: with gate_p = 0.2 the threshold is gate_threshold(0.2) = 0.446 "
                           "and d2 = 0.545 > 0.446, so the fix is refused")
        x2 = np.asarray(r["x"][2], dtype=float)
        if not np.allclose(x2, 0.0):
            return False, f"a refused fix changes nothing: x stays the prediction [0, 0, 0, 0], got {np.round(x2, 3)}"
        return True, None
    cases.append((7, "run_filter", "run_filter with gate_p = 0.2: the fix is refused (docstring)", rfg, rfg_chk))

    done, said, broken = 0, set(), set()
    for k, name, label, fn, chk in cases:
        if name == "Height1D.update":
            stubbed = getattr(kf, "Height1D", None) is None or rk.is_stub(kf.Height1D.update)
        else:
            stubbed = stub(name)
        if stubbed:
            if k not in said:
                print(f"· TODO {k}  {name}() is not written yet")
            said.add(k)
            broken.add(k)
            continue
        up = sorted(b for b in broken if b <= 3) if k in (4, 7) else []
        upnote = (f"\n          (TODO {k} uses your TODOs 1–3, and TODO {', '.join(map(str, up))} is not right yet: "
                  "fix it first)") if up else ""
        got, err = attempt(fn, name)
        if err:
            print(f"✘ TODO {k}  {label}: {err}{upnote}")
            broken.add(k)
            continue
        try:
            ok, note = chk(got)
        except Exception as e:                                       # a strange return value
            ok, note = False, f"could not read the result {got!r} ({type(e).__name__})"
        shown = got if not isinstance(got, (tuple, list, dict)) else ("(…)" if not isinstance(got, dict) else "{…}")
        if isinstance(got, (float, np.floating)):
            shown = f"{float(got):.6f}"
        print(f"{'✔' if ok else '✘'} TODO {k}  {label}" + (f"  ->  {shown}" if not isinstance(got, (tuple, list, dict))
                                                           else "") + ("" if ok else "\n          (" + (note or (
                "not the docstring result" if "docstring" in label else "not the expected result")) + ")"
              + upnote))
        done += bool(ok)
        if not ok:
            broken.add(k)
    try:
        import band_sim
        if rk.is_stub(band_sim.nees_band):
            print("· TODO 6  nees_band() in band_sim.py is not written yet")
        else:
            print("  TODO 6  nees_band() lives in band_sim.py: run python3 band_sim.py to try it")
    except Exception:
        pass
    print(f"\n{done} of {len(cases)} examples give the expected result.")


# ------------------------------------------------------------------------------------------- session 1
def grow():
    needs("cv_model", "kf_predict")
    q = 0.3
    x = np.array([0.0, 0.0, 12.0, 0.0])
    P = np.diag([9.0, 9.0, 1.0, 1.0])
    F, Q = model(1.0, q, 2)
    print(f"A drone flies east at 12 m/s. Its filter knows the position to σ 3 m and the velocity to σ 1 m/s per axis.")
    print(f"Then the fixes stop. Your filter predicts, one second at a time, with q = {q} m²/s⁴.\n")
    print("   t (s)    east (m)   σ position (m)   σ velocity (m/s)")
    ts, sp, sv = [0], [3.0], [1.0]
    for k in range(1, 41):
        x, P = predict(x, P, F, Q)
        ts.append(k)
        sp.append(math.sqrt(P[0, 0]))
        sv.append(math.sqrt(P[2, 2]))
        if k in (1, 2, 5, 10, 20, 30, 40):
            print(f"   {k:5d}   {x[0]:9.1f}   {sp[-1]:14.2f}   {sv[-1]:16.3f}")
    print(f"\n   σ position after 40 s: {sp[-1]:.1f} m")
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(ts, sp, color="#0b6e8a", lw=2, label="your filter: σ of the position")
    ax.plot(ts, [3.0 + 1.0 * t for t in ts], color="#8a96a3", ls="--", label="3 m + 1 m/s × t (a straight line)")
    ax.set_xlabel("time without a fix (s)")
    ax.set_ylabel("σ (m)")
    ax.legend(fontsize=8)
    ax.set_title("How fast does the uncertainty grow?", fontsize=10)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("out/grow.png", dpi=90)
    rk.saved("out/grow.png")


def step():
    needs("kf_update")
    x = np.array([120.0, 0.0])
    P = np.array([[16.0, 4.0], [4.0, 2.0]])
    print("Step 2: a height filter predicts x = [120 m, 0 m/s] with P = [[16, 4], [4, 2]];")
    print("a barometer reads 126 m with σ 2 m (R = 4 m²). Your kf_update says:\n")
    x2, P2, nis = update(x, P, [126.0], [[1.0, 0.0]], [[4.0]])
    print(f"   height       {x2[0]:9.3f} m")
    print(f"   climb rate   {x2[1]:9.3f} m/s      (nobody measured it)")
    print(f"   σ height     {math.sqrt(P2[0, 0]):9.3f} m        (it was {math.sqrt(16.0):.1f} m, the barometer says 2 m)")
    print(f"   P after      {np.round(P2, 4).tolist()}")
    print(f"   nis          {nis:9.3f}")


def run_height(climb_accel, rows):
    needs("cv_model", "kf_predict", "kf_update", "Height1D.update")
    try:
        f = kf.Height1D(climb_accel)
    except Exception as e:
        sys.exit(f"Height1D({climb_accel}) stopped with {type(e).__name__}: {e}")
    out, last = [], None
    for t, h, s, _, _ in rows:
        v, err = rk.call(f, "update", t, h, s)
        if err and "returned None" in err and last is None and not h > 0:
            v, err = None, None
        if err:
            sys.exit(f"at t = {t} s (height {h} m, σ {s} m): {err.replace('your file', 'navera_lite/kalman.py')}")
        if v is not None:
            if not (isinstance(v, (tuple, list)) and len(v) == 2):
                sys.exit(f"Height1D.update() must return (height, sigma), got {v!r}")
            last = (float(v[0]), float(v[1]))
        out.append(last)
    return out


def race():
    rows = read_heights()
    mine = run_height(0.5, rows)
    with open(need_data("reference_heights.csv")) as f:
        ref = [(float(r["height_m"]), float(r["sigma_m"])) for r in csv.DictReader(f)]
    if len(ref) != len(rows):
        sys.exit("reference_heights.csv and heights.csv have different lengths: tell your teacher")
    truth = [r[4] for r in rows]
    dh = max(abs(a[0] - b[0]) for a, b in zip(mine, ref))
    ds = max(abs(a[1] - b[1]) for a, b in zip(mine, ref))
    usable = [i for i, r in enumerate(rows) if r[1] > 0]
    raw = rms([rows[i][1] - truth[i] for i in usable])
    yours = rms([mine[i][0] - truth[i] for i in usable])
    print(f"{len(rows)} heights from three sources. Your Height1D (climb_accel 0.5) against the course's reference.\n")
    print("   t (s)    source       height   σ      yours ± σ          reference ± σ")
    for i in sorted(set(range(0, len(rows), max(1, len(rows) // 12))) | {len(rows) - 1}):
        t, h, s, src, _ = rows[i]
        print(f"   {t:7.2f}  {src:10s} {h:7.2f}  {s:4.2f}   {mine[i][0]:8.3f} ± {mine[i][1]:5.3f}   "
              f"{ref[i][0]:8.3f} ± {ref[i][1]:5.3f}")
    print(f"\n   largest difference: height {dh:.2e} m, σ {ds:.2e} m")
    if dh < 1e-6 and ds < 1e-6:
        print("   SAME FILTER ✔")
    else:
        i = next(k for k, (a, b) in enumerate(zip(mine, ref)) if abs(a[0] - b[0]) > 1e-6 or abs(a[1] - b[1]) > 1e-6)
        t, h, s, src, _ = rows[i]
        print(f"   the two filters differ from row {i + 1} on (t = {t} s, {src}, height {h} m, σ {s} m): yours "
              f"{mine[i][0]:.6f} ± {mine[i][1]:.6f}, reference {ref[i][0]:.6f} ± {ref[i][1]:.6f}.\n"
              "   Compare your start values, q and the rules of the docstring" +
              (" — this row is a 'no reading' (0.0): nothing may change" if not h > 0 else "") + ".")
    print(f"\n   RMS error against the truth ({len(usable)} usable heights): raw heights {raw:.3f} m, "
          f"your filter {yours:.3f} m")
    draw_heights(rows, mine, 0.5, "out/race.png", ref)


def heights(args):
    if not args:
        sys.exit("say which climb_accel to use, e.g. python3 run_kalman.py heights 0.05")
    try:
        a = float(args[0])
    except ValueError:
        sys.exit(f"climb_accel must be a number, got {args[0]!r}")
    if not a > 0:
        sys.exit("climb_accel must be > 0")
    rows = read_heights()
    mine = run_height(a, rows)
    truth = [r[4] for r in rows]
    usable = [i for i, r in enumerate(rows) if r[1] > 0]
    err = [mine[i][0] - truth[i] for i in usable]
    climb = [i for i in usable if 20.0 <= rows[i][0] <= 60.0]
    flat = [i for i in usable if rows[i][0] < 20.0 or 70.0 <= rows[i][0] <= 100.0]
    down = [i for i in usable if 100.0 <= rows[i][0] <= 125.0]
    print(f"Height1D with climb_accel = {a:g} m/s² (q = {a * a:g} m²/s⁴), {len(usable)} usable heights.\n")
    print(f"   RMS error, whole flight          {rms(err):6.3f} m")
    print(f"   RMS error, in the climb (20–60 s) {rms([mine[i][0] - truth[i] for i in climb]):6.3f} m")
    print(f"   RMS error, in the descent (100–125 s) {rms([mine[i][0] - truth[i] for i in down]):6.3f} m")
    print(f"   RMS error, level (0–20, 70–100 s) {rms([mine[i][0] - truth[i] for i in flat]):6.3f} m")
    print(f"   largest error                     {max(abs(e) for e in err):6.3f} m")
    print(f"   stated σ at the end               {mine[-1][1]:6.3f} m")
    draw_heights(rows, mine, a, f"out/heights_{a:g}.png")


def draw_heights(rows, mine, a, name, ref=None):
    plt = plt_ready()
    if plt is None:
        return
    t = [r[0] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.plot(t, [r[4] for r in rows], color="#1d2733", lw=1.2, label="truth")
    for src, c in (("baro", "#8a96a3"), ("gps-ground", "#a8680d"), ("vision", "#2e9e4f")):
        pts = [(r[0], r[1]) for r in rows if r[3] == src and r[1] > 0]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], ".", color=c, ms=4, label=src)
    h = np.array([m[0] for m in mine])
    s = np.array([m[1] for m in mine])
    ax.plot(t, h, color="#0b6e8a", lw=1.8, label=f"your filter (climb_accel {a:g})")
    ax.fill_between(t, h - 2 * s, h + 2 * s, color="#0b6e8a", alpha=0.15, label="± 2σ")
    if ref is not None:
        ax.plot(t, [r[0] for r in ref], color="#d64545", lw=0.8, ls="--", label="reference")
    ax.set_xlabel("t (s)")
    ax.set_ylabel("height above ground (m)")
    ax.legend(fontsize=7, ncol=3, loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(name, dpi=90)
    rk.saved(name)


# ------------------------------------------------------------------------------------------- session 2
def nees_of(err, P):
    v = rk.need_ok(kf, "nees", err, P)
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"nees() must return one number, got {v!r}")
    return x


def band_or_none(n_steps):
    try:
        import band_sim
    except Exception:
        return None
    if rk.is_stub(band_sim.nees_band):
        return None
    v, err = rk.call(band_sim, "nees_band", 2, n_steps)
    if err or not (isinstance(v, (tuple, list)) and len(v) == 2):
        return None
    return float(v[0]), float(v[1])


def flight(q, gate_p):
    needs("cv_model", "kf_predict", "kf_update", "run_filter")
    t, truth, zs, sz = read_track()
    r = rk.need_ok(kf, "run_filter", t, zs, sz, q, gate_p=gate_p)
    if not isinstance(r, dict) or any(k not in r for k in ("x", "P", "d2", "accepted")):
        sys.exit("run_filter() must return a dict with the keys 'x', 'P', 'd2', 'accepted'")
    if any(len(r[k]) != len(t) for k in ("x", "P", "d2", "accepted")):
        sys.exit(f"run_filter() must return one entry per time ({len(t)}) in each list")
    X = np.array([np.asarray(x, dtype=float) for x in r["x"]])
    Ps = [np.asarray(P, dtype=float) for P in r["P"]]
    if X.shape != (len(t), 4):
        sys.exit(f"each r['x'] entry must be a state of 4 numbers, got shape {X.shape[1:]}")
    err = X[:, :2] - truth
    ne = np.array([nees_of(e, P[:2, :2]) if not stub("nees") else np.nan for e, P in zip(err, Ps)])
    wrong = [k for k, z in enumerate(zs) if z is not None and math.hypot(z[0] - truth[k][0], z[1] - truth[k][1]) > WRONG_M]
    fixes = [k for k, z in enumerate(zs) if z is not None]
    jam = [k for k, z in enumerate(zs) if z is None]
    return dict(t=t, truth=truth, zs=zs, r=r, X=X, P=Ps, err=err, nees=ne, wrong=wrong, fixes=fixes, jam=jam)


def summary(f):
    r = f["r"]
    acc = r["accepted"]
    wrong_ref = sum(1 for k in f["wrong"] if acc[k] is False)
    good_ref = sum(1 for k in f["fixes"] if k not in f["wrong"] and acc[k] is False and k > 0)
    rmse = rms(np.hypot(f["err"][f["fixes"], 0], f["err"][f["fixes"], 1]))
    return wrong_ref, good_ref, rmse, float(np.nanmean(f["nees"]))


def track(args):
    if not args:
        sys.exit("say which q to use, e.g. python3 run_kalman.py track 0.3   (and a gate: track 0.3 0.99)")
    try:
        q = float(args[0])
        gate_p = float(args[1]) if len(args) > 1 else None
    except ValueError:
        sys.exit("q and the gate probability must be numbers, e.g. python3 run_kalman.py track 0.3 0.99")
    if not q > 0 or (gate_p is not None and not 0.0 < gate_p < 1.0):
        sys.exit("q must be > 0 and the gate probability between 0 and 1 (e.g. 0.99)")
    f = flight(q, gate_p)
    wrong_ref, good_ref, rmse, mnees = summary(f)
    raw = rms([math.hypot(f["zs"][k][0] - f["truth"][k][0], f["zs"][k][1] - f["truth"][k][1])
               for k in f["fixes"] if k not in f["wrong"]])
    j0, j1 = f["jam"][0], f["jam"][-1]
    after = j1 + 1
    sj = math.sqrt(f["P"][j1][0, 0])
    print(f"The flight: {len(f['t'])} s, a fix every second (σ 5 m), no fix from t = {f['t'][j0]:.0f} to {f['t'][j1]:.0f} s"
          f" (jammed), {len(f['wrong'])} wrong fixes (> {WRONG_M:.0f} m from the truth).")
    print(f"Your filter: q = {q:g} m²/s⁴, " + ("no gate" if gate_p is None else
                                               f"gate p = {gate_p:g} (refuse d² > {kf.gate_threshold(gate_p):.2f})") + "\n")
    print(f"   RMS error at the {len(f['fixes'])} seconds with a fix:  good fixes alone {raw:6.2f} m,  "
          f"your filter {rmse:7.2f} m")
    s2 = math.sqrt(f["P"][j1][0, 0] + f["P"][j1][1, 1])
    print(f"   at the end of the jam: σ east {sj:7.1f} m;  stated 2-D σ √(σe² + σn²) {s2:7.1f} m,  "
          f"true 2-D error |x − truth| {math.hypot(*f['err'][j1]):7.1f} m")
    d2a = f["r"]["d2"][after]
    print(f"   first fix after the jam (t = {f['t'][after]:.0f} s): d² = "
          + ("—" if d2a is None else f"{float(d2a):.2f}") + f", accepted: {f['r']['accepted'][after]}")
    print(f"   wrong fixes refused: {wrong_ref} of {len(f['wrong'])};   good fixes refused: {good_ref}")
    if np.all(np.isnan(f["nees"])):
        print("   mean NEES: write nees() (TODO 5) to see it")
    else:
        band = band_or_none(len(f["t"]))
        print(f"   mean NEES over {len(f['t'])} s: {mnees:.2f}   (an honest 2-D filter: 2" +
              (f"; your band {band[0]:.2f} – {band[1]:.2f})" if band else "; write band_sim.py to get its band)"))
    late = [k for k in f["fixes"] if k > after]
    refused_late = sum(1 for k in late if f["r"]["accepted"][k] is False)
    if gate_p is not None and refused_late > 0.5 * len(late):
        print(f"\n   ⚠ after the jam the gate refused {refused_late} of {len(late)} fixes: the filter has LOST the track")
    draw_track(f, q, gate_p)


def draw_track(f, q, gate_p):
    plt = plt_ready()
    if plt is None:
        return
    tr, X, zs, acc = f["truth"], f["X"], f["zs"], f["r"]["accepted"]
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2))
    ax = axs[0]
    ax.plot(tr[:, 0], tr[:, 1], color="#1d2733", lw=1, label="truth")
    good = [k for k in f["fixes"] if acc[k] is not False]
    bad = [k for k in f["fixes"] if acc[k] is False]
    ax.plot([zs[k][0] for k in good], [zs[k][1] for k in good], ".", color="#8a96a3", ms=3, label="fixes used")
    ax.plot([zs[k][0] for k in bad], [zs[k][1] for k in bad], "x", color="#d64545", ms=6, label="fixes refused")
    ax.plot(X[:, 0], X[:, 1], color="#0b6e8a", lw=1.5, label="your filter")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    ax.legend(fontsize=7)
    ax.set_title(f"q = {q:g}" + ("" if gate_p is None else f", gate {gate_p:g}"), fontsize=9)
    ax = axs[1]
    t = np.array(f["t"])
    e = np.hypot(f["err"][:, 0], f["err"][:, 1])
    s = np.array([math.sqrt(P[0, 0] + P[1, 1]) for P in f["P"]])
    ax.plot(t, e, color="#0b6e8a", lw=1.2, label="true error |x − truth|")
    ax.plot(t, s, color="#a8680d", lw=1.2, ls="--", label="stated √(σe² + σn²)")
    ax.axvspan(t[f["jam"][0]], t[f["jam"][-1]], color="#8a96a3", alpha=0.2, label="jammed")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("m (linear up to 10, then log)")
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    name = f"out/track_{q:g}" + ("" if gate_p is None else f"_gate{gate_p:g}") + ".png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


def sweep(args):
    try:
        gate_p = float(args[0]) if args else 0.99
    except ValueError:
        sys.exit("the gate probability must be a number, e.g. python3 run_kalman.py sweep 0.99")
    band = band_or_none(361)
    print(f"The same flight, gate p = {gate_p:g}, seven values of q. " +
          (f"Your NEES band (2-D, 361 s): {band[0]:.2f} – {band[1]:.2f}." if band else
           "(Write band_sim.py to see your NEES band here.)") + "\n")
    print("        q    RMS with fixes (m)   mean NEES   wrong refused   good refused   verdict")
    for q in SWEEP_Q:
        f = flight(q, gate_p)
        w, g, rmse, mn = summary(f)
        late = [k for k in f["fixes"] if k > f["jam"][-1] + 1]
        lost = sum(1 for k in late if f["r"]["accepted"][k] is False) > 0.5 * len(late)
        if lost:
            verdict = "LOST the track after the jam"
        elif band and mn > band[1]:
            verdict = "above the band: overconfident" if mn > 1.1 * band[1] else "just above the band (a hint)"
        elif band and mn < band[0]:
            verdict = ("below the band: pessimistic side" if mn < 0.9 * band[0]
                       else "just below the band (a hint: pessimistic side)")
        elif band:
            verdict = "honest (inside the band)"
        else:
            verdict = ""
        print(f"   {q:6g}   {rmse:16.2f}   {mn:9.2f}   {w:9d} of {len(f['wrong'])}   {g:12d}   {verdict}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    m, rest = a[0], a[1:]
    table = {"test": lambda: test(), "grow": lambda: grow(), "step": lambda: step(), "race": lambda: race(),
             "heights": lambda: heights(rest), "track": lambda: track(rest), "sweep": lambda: sweep(rest)}
    if m not in table:
        print(__doc__)
        sys.exit(1)
    table[m]()
