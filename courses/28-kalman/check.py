"""Check of mission 28 — the Kalman filter. Sealed: never shown to students.

Unseen inputs everywhere. Expected values of TODOs 1–5 and 7 come from the course reference on hidden inputs
(hidden/expected.json, made by solutions/28-kalman/make_expected.py); TODO 6 is random by nature: it is compared
with reference bands from 200 000 simulated flights, with a tolerance for the student's 4 000. The lab's numbers
(expected.json "lab") are what run_kalman.py prints with the reference; solutions/28-kalman/TEACHER.md lists them.
"""
import contextlib
import io
import json
import math
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()
E = json.loads(hidden("expected.json"))
LAB = E["lab"]


def kal():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.kalman", fresh=True)


def functions(*names):
    fns = need(kal(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/kalman.py)")
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
        if "matmul" in msg or "not aligned" in msg or "mismatch in its core dimension" in msg:
            raise CheckFailed(msg + " — two matrices that cannot be multiplied: print their .shape (H is m × n, Hᵀ = "
                              "H.T; a list has no .T: np.asarray first)")
        if "has no attribute 'T'" in msg or "for @" in msg:
            raise CheckFailed(msg + " — a plain list has no .T and cannot use @: convert the inputs with np.asarray(…, dtype=float) first")
        if "'NoneType'" in msg:
            raise CheckFailed(msg + " — something is None: either a function it calls returned None (an earlier TODO "
                              "still a stub?) or a value you use is still None (in Height1D: self.x and self.P are None "
                              "until the first usable height)")
        raise


def mat(v, shape, what):
    if v is None:
        raise CheckFailed(f"{what} is None — does every path end with `return`?")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should be numbers (a numpy array), got {v!r}")
    if a.shape != tuple(shape):
        raise CheckFailed(f"{what} has shape {a.shape}, expected {tuple(shape)}")
    return a


def pairs(v, n, what):
    if not (isinstance(v, (tuple, list)) and len(v) == n):
        raise CheckFailed(f"{what} should return {n} values, got {v!r}")
    return v


_UPSTREAM = {}


def upstream_note():
    """'' when the student's cv_model, kf_predict and kf_update pass one hidden case each; else a sentence saying
    that the failing TODO uses them (Height1D and run_filter are built on TODOs 1–3)."""
    if "note" in _UPSTREAM:
        return _UPSTREAM["note"]
    bad = []
    try:
        m = kal()
        cv, pr, up = need(m, "cv_model", "kf_predict", "kf_update")
        case = E["cv"][1]
        F, Q = run(cv, *case["args"])
        if not (np.allclose(np.asarray(F, dtype=float), case["F"], atol=1e-9)
                and np.allclose(np.asarray(Q, dtype=float), case["Q"], atol=1e-9)):
            bad.append("cv_model (TODO 1)")
        case = E["predict"][0]
        xp, Pp = run(pr, *(np.array(case[k], dtype=float) for k in ("x", "P", "F", "Q")))
        if not (np.allclose(np.asarray(xp, dtype=float), case["xp"], atol=1e-9)
                and np.allclose(np.asarray(Pp, dtype=float), case["Pp"], atol=1e-9)):
            bad.append("kf_predict (TODO 2)")
        case = E["update"][0]
        xu, Pu, nis = run(up, *(np.array(case[k], dtype=float) for k in ("x", "P", "z", "H", "R")))
        if not (np.allclose(np.asarray(xu, dtype=float), case["xu"], atol=1e-7)
                and np.allclose(np.asarray(Pu, dtype=float), case["Pu"], atol=1e-7)
                and abs(float(np.asarray(nis, dtype=float).reshape(-1)[0]) - case["nis"]) < 1e-7):
            bad.append("kf_update (TODO 3)")
    except Exception:
        bad.append("cv_model / kf_predict / kf_update (TODOs 1–3)")
    _UPSTREAM["note"] = ("" if not bad else " — but your " + ", ".join(bad) + " does not pass its own check yet, "
                         "and this TODO uses it: fix that first")
    return _UPSTREAM["note"]


# ======================================================================== session 1 — Height keeper
def height_variant(seq, ca, mode):
    """A wrong-but-plausible Height1D (sealed: used only to name the student's mistake)."""
    x = P = t0 = None
    out = []
    for t, h, s in seq:
        h = float("nan") if h is None else h
        if not h > 0:
            out.append(None if x is None else (x[0], math.sqrt(P[0, 0])))
            continue
        if x is None:
            x = np.array([h, 0.0])
            P = np.diag([s * s if mode != "start_sigma" else s, 0.0 if mode == "climb0" else
                         (s * s if mode == "climb_sigma2" else 4.0)])
            t0 = t
        else:
            dt = t - t0
            q = {"q_unsquared": ca, "q_fixed": 0.25}.get(mode, ca * ca)
            g = np.array([dt * dt / 2.0, dt])
            F = np.array([[1.0, dt], [0.0, 1.0]])
            x, P = F @ x, F @ P @ F.T + q * np.outer(g, g)
            R = s if mode == "R_sigma" else s * s
            S = P[0, 0] + R
            Kg = P[:, 0] / S
            x = x + Kg * (h - x[0])
            P = P - np.outer(Kg, P[0, :])
            t0 = t
        out.append((x[0], math.sqrt(P[0, 0])))
    return out


def height_diagnosis(H, i, gh, gs):
    for mode, msg in (("q_unsquared", "q is climb_accel, it must be climb_accel² (σ_a² is the variance)"),
                      ("q_fixed", "q is 0.25 whatever climb_accel is: use self.climb_accel ** 2 (here "
                                  f"{H['climb_accel']}²)"),
                      ("climb0", "the start climb variance is 0: the climb rate is unknown, P = diag(σ², 4.0)"),
                      ("climb_sigma2", "the start climb variance is σ²: it is 4.0 (σ 2 m/s), whatever the height's σ"),
                      ("start_sigma", "the start height variance is σ: it is σ² (P = diag(σ², 4.0))"),
                      ("R_sigma", "R = σ: R is a variance, [[σ²]]")):
        v = height_variant(H["seq"], H["climb_accel"], mode)[i]
        if v is not None and abs(gh - v[0]) < 1e-6 and abs(gs - v[1]) < 1e-6:
            return " — " + msg
    return (" — check the start (x = [h, 0.0], P = diag(σ², 4.0)), q = climb_accel² (self.climb_accel, here "
            f"{H['climb_accel']}) and R = σ²")


def q_variant(dt, q, kind):
    if kind == "continuous":
        return q * np.array([[dt ** 3 / 3, dt ** 2 / 2], [dt ** 2 / 2, dt]])
    if kind == "noq":
        return np.array([[dt ** 4 / 4, dt ** 3 / 2], [dt ** 3 / 2, dt ** 2]])
    if kind == "diag":
        return q * np.diag([dt ** 4 / 4, dt ** 2])
    if kind == "sqrtq":
        return math.sqrt(q) * np.array([[dt ** 4 / 4, dt ** 3 / 2], [dt ** 3 / 2, dt ** 2]])


@c.test("TODO 1: cv_model() on unseen time steps, noise levels and 1, 2 and 3 axes",
        hint="Lesson §2: one axis F1 = [[1, dt], [0, 1]], g = [dt²/2, dt], Q1 = q·g gᵀ (np.outer); then "
             "np.kron(F1, np.eye(dims)) and np.kron(Q1, np.eye(dims)) — F1 first, so the state is [positions…, velocities…].")
def _():
    (f,) = functions("cv_model")
    for case in E["cv"]:
        dt, q, dims = case["args"]
        got = pairs(go(f, dt, q, dims), 2, f"cv_model({dt}, {q}, dims={dims})")
        n = 2 * dims
        F = mat(got[0], (n, n), f"F of cv_model({dt}, {q}, dims={dims})")
        Q = mat(got[1], (n, n), f"Q of cv_model({dt}, {q}, dims={dims})")
        wF, wQ = np.array(case["F"]), np.array(case["Q"])
        if dims > 1 and np.allclose(F, np.kron(np.eye(dims), np.array([[1.0, dt], [0.0, 1.0]]))):
            raise CheckFailed(f"cv_model(…, dims={dims}): the state order is [p_1 … p_d, v_1 … v_d] — positions first: "
                              "np.kron(F1, np.eye(dims)), with F1 FIRST")
        c.ok(np.allclose(F, wF, atol=1e-9), f"F of cv_model({dt}, {q}, dims={dims}) is not right: F1 = [[1, dt], [0, 1]] "
                                            "copied onto each axis")
        if q > 0:
            for kind, msg in (("continuous", "Q = q·[[dt³/3, dt²/2], [dt²/2, dt]] is another model (continuous noise); "
                                             "this course's Q is q·g gᵀ with g = [dt²/2, dt] (lesson §2)"),
                              ("noq", "Q is not multiplied by q"),
                              ("diag", "the off-diagonal terms of Q are missing: q·g gᵀ has q·dt³/2 there (the same "
                                       "acceleration moves position and velocity)"),
                              ("sqrtq", "Q is multiplied by √q (σ_a): q is already the variance σ_a²")):
                if np.allclose(Q, np.kron(q_variant(dt, q, kind), np.eye(dims)), atol=1e-9):
                    raise CheckFailed(f"cv_model({dt}, {q}, dims={dims}): {msg}")
        c.ok(np.allclose(Q, wQ, atol=1e-9), f"Q of cv_model({dt}, {q}, dims={dims}) is off by up to "
                                            f"{np.abs(Q - wQ).max():.3g}: Q1 = q·g gᵀ, g = [dt²/2, dt]")


@c.test("TODO 2: kf_predict() on unseen states, covariances and models — numpy arrays and plain lists",
        hint="Lesson §2: x⁻ = F x, P⁻ = F P Fᵀ + Q with @ and .T, after np.asarray(…, dtype=float) on the four inputs. "
             "Do not change the inputs in place.")
def _():
    (f,) = functions("kf_predict")
    for case in E["predict"]:
        x, P, F, Q = case["x"], case["P"], case["F"], case["Q"]
        n = len(x)
        args = (x, P, F, Q) if case.get("lists") else tuple(np.array(a, dtype=float) for a in (x, P, F, Q))
        keep = [np.array(a, dtype=float) for a in args]
        got = pairs(go(f, *args), 2, "kf_predict")
        xp = mat(got[0], (n,), "the predicted x")
        Pp = mat(got[1], (n, n), "the predicted P")
        if not case.get("lists"):
            for a, k, nm in zip(args, keep, ("x", "P", "F", "Q")):
                if not np.array_equal(np.asarray(a, dtype=float), k):
                    raise CheckFailed(f"kf_predict changed its input {nm} in place: compute new arrays, leave the inputs "
                                      "as they are")
        F_, P_, Q_, x_ = (np.array(a, dtype=float) for a in (F, P, Q, x))
        if np.allclose(Pp, F_ @ P_ @ F_.T, atol=1e-9) and np.abs(Q_).max() > 0:
            raise CheckFailed("Q is not added: P⁻ = F P Fᵀ + Q")
        if np.allclose(Pp, F_ @ P_ @ F_ + Q_, atol=1e-9):
            raise CheckFailed("F P F + Q: the transpose is missing (F @ P @ F.T)")
        if np.allclose(Pp, P_ + Q_, atol=1e-9):
            raise CheckFailed("P is not moved by F: P⁻ = F P Fᵀ + Q")
        if np.allclose(Pp, F_ * P_ * F_.T + Q_, atol=1e-9):
            raise CheckFailed("`*` multiplies element by element: use @ for matrix products")
        c.ok(np.allclose(xp, case["xp"], atol=1e-9), f"the predicted x is {np.round(xp, 4)}: x⁻ = F @ x")
        c.ok(np.allclose(Pp, case["Pp"], atol=1e-9), "the predicted P is off: P⁻ = F P Fᵀ + Q")
        if case.get("lists"):
            c.ok(True)


@c.test("TODO 3: kf_update() on an unseen 2-D position fix (correlated R) and an unseen height",
        hint="Lesson §3: ν = z − H x, S = H P Hᵀ + R, K = P Hᵀ S⁻¹, x + K ν, (I − K H) P, and nis = νᵀ S⁻¹ ν "
             "(np.linalg.solve(S, nu)) as a float, computed before the update.")
def _():
    (f,) = functions("kf_update")
    for case in E["update"]:
        x, P, z, H, R = (np.array(case[k], dtype=float) for k in ("x", "P", "z", "H", "R"))
        n = len(x)
        keep = [a.copy() for a in (x, P, z, H, R)]
        got = pairs(go(f, x, P, z, H, R), 3, "kf_update")
        xu = mat(got[0], (n,), "the updated x")
        Pu = mat(got[1], (n, n), "the updated P")
        if isinstance(got[2], bool) or np.size(got[2]) != 1:
            raise CheckFailed(f"kf_update's third value (nis) must be ONE number, got {got[2]!r}")
        nis = float(np.asarray(got[2], dtype=float).reshape(-1)[0])
        for a, k, nm in zip((x, P, z, H, R), keep, ("x", "P", "z", "H", "R")):
            if not np.array_equal(a, k):
                raise CheckFailed(f"kf_update changed its input {nm} in place: compute new arrays")
        nu = z - H @ x
        S = H @ P @ H.T + R
        for bad, msg in ((float(nu @ np.linalg.solve(R, nu)), "nis divides by R only: S = H P Hᵀ + R contains both"),
                         (float(nu @ np.linalg.solve(H @ P @ H.T, nu)), "nis uses H P Hᵀ only: S = H P Hᵀ + R (add R)"),
                         (math.sqrt(case["nis"]), "nis has a square root: it is a d², νᵀ S⁻¹ ν"),
                         (float(nu @ nu) / float(np.trace(S)), "nis must use the inverse of S: νᵀ S⁻¹ ν "
                                                                "(np.linalg.solve(S, nu))")):
            if abs(nis - bad) < 1e-7 and abs(bad - case["nis"]) > 1e-6:
                raise CheckFailed(msg)
        if np.allclose(Pu, P, atol=1e-9):
            raise CheckFailed("P did not change: after the update P = (I − K H) P⁻")
        K = P @ H.T @ np.linalg.inv(S)
        if np.allclose(xu, x - K @ nu, atol=1e-7):
            raise CheckFailed("the state moved the wrong way: x = x⁻ + K ν with ν = z − H x (not H x − z)")
        if np.allclose(Pu, (np.eye(n) + K @ H) @ P, atol=1e-7):
            raise CheckFailed("P = (I − K H) P⁻: a minus, not a plus")
        Kr = P @ H.T @ np.linalg.inv(R)
        if np.allclose(xu, x + Kr @ nu, atol=1e-7):
            raise CheckFailed("K = P Hᵀ R⁻¹ is wrong: the gain divides by S = H P Hᵀ + R")
        c.ok(np.allclose(xu, case["xu"], atol=1e-7), f"the updated x is {np.round(xu, 4)}, expected "
                                                      f"{np.round(case['xu'], 4)}")
        c.ok(np.allclose(Pu, case["Pu"], atol=1e-7), "the updated P is off: P = (I − K H) P⁻ with K = P⁻ Hᵀ S⁻¹")
        c.ok(abs(nis - case["nis"]) < 1e-7, f"nis = {nis:.5f}, expected {case['nis']:.5f} (νᵀ S⁻¹ ν)")


@c.test("TODO 4: Height1D on an unseen sequence — another climb_accel, no readings, the same time twice, nan",
        hint="Docstring of Height1D.update: ignore heights that are not > 0 (return the current (h, σ), or None before "
             "the first usable one); start x = [h, 0], P = diag(σ², 4); then predict with cv_model(dt, climb_accel², 1) "
             "and update with z = [h], H = [[1, 0]], R = [[σ²]]; return (x[0], √P[0][0]); a time going back raises "
             "ValueError.")
def _():
    m = kal()
    (cls,) = need(m, "Height1D")
    if is_stub(cls.update):
        raise CheckFailed("Height1D.update() is not written yet (TODO 4 in navera_lite/kalman.py)")
    H = E["height"]
    f = go(cls, H["climb_accel"])
    for i, ((t, h, s), want) in enumerate(zip(H["seq"], H["out"])):
        h = float("nan") if h is None else h
        try:
            got = go(f.update, t, h, s)
        except CheckFailed as e:
            raise CheckFailed(f"update({t}, {h}, {s}) — call {i + 1} of the sequence"
                              + (" (a 'no reading' before any usable height: return None)" if want is None else "")
                              + f": {e}")
        if want is None:
            c.ok(got is None, f"update({t}, {h}, {s}) before any usable height should return None, got {got!r} — a "
                              "height that is not > 0 is 'no reading': ignore it")
            continue
        if got is None:
            raise CheckFailed(f"update({t}, {h}, {s}) returned None, but the filter has a height: return the current "
                              "(height, σ) — a height that is not > 0 changes nothing")
        got = pairs(got, 2, f"update({t}, {h}, {s})")
        gh, gs = float(got[0]), float(got[1])
        if not (math.isfinite(gh) and math.isfinite(gs)):
            raise CheckFailed(f"update({t}, {h}, {s}) gave ({gh}, {gs}): a 'nan' height must be ignored (nan > 0 is "
                              "False: test `not h > 0`)")
        if i == 1 and abs(gs - s * s) < 1e-9 and abs(gs - s) > 1e-9:
            raise CheckFailed("the σ returned is the variance P[0][0]: return √P[0][0]")
        if abs(gh - want[0]) > 1e-6 or abs(gs - want[1]) > 1e-6:
            prev = H["seq"][i - 1] if i else None
            hint = ""
            if h is not None and not (h > 0):
                hint = " — this height is 'no reading': nothing may change"
            elif prev is not None and prev[0] == t:
                hint = " — two heights at the same time: dt = 0, the prediction changes nothing"
            else:
                hint = height_diagnosis(H, i, gh, gs)
            note = upstream_note()
            raise CheckFailed(f"after update({t}, {h}, {s}): ({gh:.6f}, {gs:.6f}), expected ({want[0]:.6f}, "
                              f"{want[1]:.6f})" + (note or hint))
        c.ok(True)
    f = go(cls)
    for (t, h, s), want in zip(((10.0, 300.0, 6.0), (12.5, 296.0, 3.0)), E["height_default"]):
        got = pairs(go(f.update, t, h, s), 2, "update")
        if abs(float(got[0]) - want[0]) > 1e-6 or abs(float(got[1]) - want[1]) > 1e-6:
            raise CheckFailed(f"Height1D() (default climb_accel 0.5): update({t}, {h}, {s}) = ({float(got[0]):.6f}, "
                              f"{float(got[1]):.6f}), expected ({want[0]:.6f}, {want[1]:.6f})" + upstream_note())
    try:
        run(f.update, 11.0, 290.0, 3.0)
    except CheckFailed as e:
        c.ok("ValueError" in str(e), f"a time before the filter's time should raise ValueError, got: {e}")
    else:
        raise CheckFailed("update(11.0, …) after a height at 12.5 s should raise ValueError (t must not go backwards)")


@c.test("Steps 0–2: how fast σ grows, and the update by hand",
        hint="PREDICT_GROW is your Step 0 guess. python3 run_kalman.py grow: σ after 40 s. EXPLAIN_GROW: the velocity "
             "error × time, and the random accelerations (q) on top. TRACE_…: S = 16 + 4, K = [16/S, 4/S], "
             "x = x⁻ + K·(126 − 120), P[0][0] = (1 − K₀)·16, σ = its root.")
def _():
    pg, s40, why, th, tc, ts = answers("PREDICT_GROW", "SIGMA_40S_M", "EXPLAIN_GROW", "TRACE_HEIGHT_M",
                                       "TRACE_CLIMB_MPS", "TRACE_SIGMA_M")
    predicted("PREDICT_GROW", pg)
    s40 = number(s40, "SIGMA_40S_M")
    if abs(s40 - LAB["SIGMA_40S_M"] ** 2) < 5:
        raise CheckFailed("SIGMA_40S_M looks like a variance: write σ (m), as printed")
    c.near(s40, LAB["SIGMA_40S_M"], 0.1, "SIGMA_40S_M (python3 run_kalman.py grow, m)")
    explained("EXPLAIN_GROW", why,
              ((r"veloc", r"speed", r"1 ?m/s", r"× ?t", r"times? (the )?time", r"multipl", r"40 ?m", r"43"),
               'the velocity error growing with time (e.g. "1 m/s of velocity error is 40 m after 40 s")'),
              ((r"accel", r"\bq\b", r"q =", r"noise", r"random", r"cub", r"t³", r"t\^3", r"power", r"add", r"on top",
                r"grows? too", r"itself"),
               'the random accelerations adding on top (e.g. "q makes the velocity error itself grow")'))
    th, tc, ts = number(th, "TRACE_HEIGHT_M"), number(tc, "TRACE_CLIMB_MPS"), number(ts, "TRACE_SIGMA_M")
    if abs(th - 124.0) < 0.05:
        raise CheckFailed("TRACE_HEIGHT_M = 124: K₀ = P⁻₀₀ / S with S = 16 + 4 = 20 (not 16/(16 + 2): R = σ² = 4)")
    c.near(th, LAB["TRACE_HEIGHT_M"], 0.01, "TRACE_HEIGHT_M (m)")
    c.near(tc, LAB["TRACE_CLIMB_MPS"], 0.01, "TRACE_CLIMB_MPS (m/s): K₁ = P⁻₁₀ / S")
    if abs(ts - 3.2) < 0.01:
        raise CheckFailed("TRACE_SIGMA_M = 3.2 is P[0][0], a variance (m²): σ is its square root")
    c.near(ts, LAB["TRACE_SIGMA_M"], 0.01, "TRACE_SIGMA_M (m)")


@c.test("Steps 3–4: the race's errors, and what q does — numbers, prediction, explanation",
        hint="python3 run_kalman.py race: the two RMS errors. heights 0.05 and heights 5: the whole-flight RMS error. "
             "EXPLAIN_Q: small q lags in the climb (and states a small σ: overconfident), large q follows the noise.")
def _():
    raw, filt, pq, r005, r5, why = answers("RACE_RMSE_RAW_M", "RACE_RMSE_FILTER_M", "PREDICT_Q", "RMSE_CA_005_M",
                                           "RMSE_CA_5_M", "EXPLAIN_Q")
    raw, filt = number(raw, "RACE_RMSE_RAW_M"), number(filt, "RACE_RMSE_FILTER_M")
    if abs(raw - LAB["RACE_RMSE_FILTER_M"]) < 0.005 and abs(filt - LAB["RACE_RMSE_RAW_M"]) < 0.005:
        raise CheckFailed("RACE_RMSE_RAW_M and RACE_RMSE_FILTER_M are swapped")
    c.near(raw, LAB["RACE_RMSE_RAW_M"], 0.005, "RACE_RMSE_RAW_M (python3 run_kalman.py race, m)")
    c.near(filt, LAB["RACE_RMSE_FILTER_M"], 0.005, "RACE_RMSE_FILTER_M (your filter once it wins the race, m)")
    predicted("PREDICT_Q", pq)
    r005, r5 = number(r005, "RMSE_CA_005_M"), number(r5, "RMSE_CA_5_M")
    if abs(r005 - LAB["RMSE_CA_5_M"]) < 0.01 and abs(r5 - LAB["RMSE_CA_005_M"]) < 0.01:
        raise CheckFailed("RMSE_CA_005_M and RMSE_CA_5_M are swapped")
    c.near(r005, LAB["RMSE_CA_005_M"], 0.01, "RMSE_CA_005_M (heights 0.05, whole flight, m)")
    c.near(r5, LAB["RMSE_CA_5_M"], 0.01, "RMSE_CA_5_M (heights 5, whole flight, m)")
    explained("EXPLAIN_Q", why,
              ((r"lag", r"late", r"behind", r"slow", r"climb", r"cannot follow", r"can't follow", r"delay"),
               'what the small value does in the climb (e.g. "it lags behind the climb")'),
              ((r"noise", r"noisy", r"follow", r"every measurement", r"jump", r"jitter", r"level"),
               'what the large value does (e.g. "it follows the noise of every measurement")'),
              ((r"overconfiden", r"small (σ|sigma)", r"trusts? (its|the) model", r"believes? (its|the) model",
                r"too (sure|confident)", r"\bp\b.*small", r"stat", r"claims?", r"honest"),
               'why the smallest value states the smallest σ (e.g. "it trusts its model, so P stays small: overconfident")'))


# ======================================================================== session 2 — Tracker
@c.test("TODO 5: nees() on unseen errors — correlated 2-D, 3-D, 1-D",
        hint="Lesson §6: errᵀ P⁻¹ err, one float — the same algebra as the nis of TODO 3 (solve with P instead of "
             "forming its inverse). Use the full P (it may be correlated); no square root, no division by n.")
def _():
    (f,) = functions("nees")
    for case in E["nees"]:
        err, P = np.array(case["err"]), np.array(case["P"])
        got = go(f, err, P)
        if isinstance(got, bool) or got is None or np.size(got) != 1:
            raise CheckFailed(f"nees() must return ONE number, got {got!r}")
        v = float(np.asarray(got, dtype=float).reshape(-1)[0])
        want = case["v"]
        if abs(v - float(err @ P @ err)) < 1e-9 and abs(want - float(err @ P @ err)) > 1e-6:
            raise CheckFailed("errᵀ P err: the INVERSE of P is missing (np.linalg.solve(P, err))")
        if abs(v - math.sqrt(want)) < 1e-9:
            raise CheckFailed("NEES has no square root: it is a squared distance")
        if abs(v - want / len(err)) < 1e-9 and len(err) > 1:
            raise CheckFailed("do not divide by n: one step's NEES is errᵀ P⁻¹ err; it is its AVERAGE that is near n")
        if abs(v - float(np.sum(err ** 2 / np.diag(P)))) < 1e-9 and abs(want - v) > 1e-6:
            raise CheckFailed("only the diagonal of P is used: with a correlated P you need the full inverse")
        c.ok(abs(v - want) < 1e-7, f"nees({case['err']}, …) = {v:.5f}, expected {want:.5f}")


@c.test("TODO 6: nees_band() in band_sim.py — unseen dimensions, lengths and probabilities; the seed repeats a run",
        hint="Lesson §6 and Step 5: one generator from the seed; standard normal numbers of shape (trials, n_steps, "
             "n_dim), squared and SUMMED over the dimensions (one NEES per step), AVERAGED over the steps (one mean per "
             "flight); then cut (1 − p)/2 at each end with np.percentile.")
def _():
    with contextlib.redirect_stdout(io.StringIO()):
        m = load_student("band_sim.py", fresh=True)
    (f,) = need(m, "nees_band")
    if is_stub(f):
        raise CheckFailed("nees_band() is not written yet (TODO 6 in band_sim.py)")
    for case in E["band"]:
        n, N, p = case["args"]
        trials = 60000 if N == 1 else 6000
        got = pairs(go(f, n, N, trials=trials, p=p, seed=3, seconds=60), 2, f"nees_band({n}, {N}, p={p})")
        lo, hi = float(got[0]), float(got[1])
        wl, wh = case["v"]
        if lo > hi:
            raise CheckFailed(f"nees_band({n}, {N}) returned low {lo:.3f} > high {hi:.3f}: return (low, high)")
        if N > 1 and abs(lo / N - wl) < 0.2 * wl and abs(hi / N - wh) < 0.2 * wh:
            raise CheckFailed(f"nees_band({n}, {N}) ≈ ({lo:.1f}, {hi:.1f}): you SUMMED over the steps — average them "
                              "(.mean over the steps axis)")
        if n > 1 and abs(lo * n - wl) < 0.1 * wl and abs(hi * n - wh) < 0.1 * wh:
            raise CheckFailed(f"nees_band({n}, {N}) ≈ ({lo:.2f}, {hi:.2f}): you averaged over the dimensions too — one "
                              "step's NEES is the SUM of the n squares")
        tol_l = 0.12 * wl if N == 1 else 0.03 * wl
        tol_h = 0.04 * wh if N == 1 else 0.03 * wh
        if abs(lo - wl) > tol_l or abs(hi - wh) > tol_h:
            c5 = 100.0 * (1.0 - p)
            raise CheckFailed(f"nees_band({n}, {N}, p={p}) = ({lo:.3f}, {hi:.3f}), expected about ({wl:.3f}, {wh:.3f}): "
                              f"check the cut — {c5 / 2:g} % at EACH end for p = {p} — and the shape (trials, n_steps, "
                              "n_dim)")
        c.ok(True)
    a = pairs(go(f, 2, 20, trials=3000, seed=11), 2, "nees_band")
    b = pairs(go(f, 2, 20, trials=3000, seed=11), 2, "nees_band")
    c.ok(float(a[0]) == float(b[0]) and float(a[1]) == float(b[1]),
         "the same seed must give the same band: use np.random.default_rng(seed), and no other random source")
    d = pairs(go(f, 2, 20, trials=3000, seed=12), 2, "nees_band")
    c.ok(float(a[0]) != float(d[0]) or float(a[1]) != float(d[1]),
         "another seed gives exactly the same band: is the seed argument used?")


def flight_inputs():
    F = E["flight"]
    return F["times"], [None if z is None else tuple(z) for z in F["zs"]], F["sigma_z"], F["q"]


def compare_run(r, want, label):
    if not isinstance(r, dict):
        raise CheckFailed(f"run_filter() must return a dict of four lists, got {type(r).__name__}")
    for k in ("x", "P", "d2", "accepted"):
        if k not in r:
            raise CheckFailed(f"run_filter()'s result has no key {k!r}")
        if len(r[k]) != len(want["x"]):
            raise CheckFailed(f"r[{k!r}] has {len(r[k])} entries for {len(want['x'])} times (one per time, even "
                              "without a fix)")
    if r["d2"][0] is not None or r["accepted"][0] is not True:
        raise CheckFailed("at k = 0 the first fix starts the filter: d2 = None and accepted = True")
    for k in range(len(want["x"])):
        x = mat(r["x"][k], (4,), f"r['x'][{k}]")
        P = mat(r["P"][k], (4, 4), f"r['P'][{k}]")
        wd, wa = want["d2"][k], want["accepted"][k]
        if (r["d2"][k] is None) != (wd is None):
            raise CheckFailed(f"{label}: at k = {k} d2 is {r['d2'][k]!r}, expected "
                              + ("None (no fix at that time)" if wd is None else f"{wd:.4f}"))
        if wd is not None and abs(float(r["d2"][k]) - wd) > 1e-6:
            hint = ""
            if k == 1:
                hint = (" — the first prediction: check the start P = diag(σ_z², σ_z², v0_sigma², v0_sigma²) and "
                        "dt = times[1] − times[0] (the times here are irregular: not always 1 s)")
            elif abs(float(r["d2"][k]) - wd) / max(wd, 1e-9) > 0.2:
                hint = " — do you predict with the REAL time step dt = times[k] − times[k−1] (not 1 s)?"
            raise CheckFailed(f"{label}: d2 at k = {k} is {float(r['d2'][k]):.6f}, expected {wd:.6f}"
                              + (upstream_note() or hint))
        if r["accepted"][k] != wa:
            if wa is False:
                raise CheckFailed(f"{label}: the fix at k = {k} (d2 = {wd:.2f}) should be REFUSED by the gate "
                                  f"(threshold gate_threshold(p))")
            raise CheckFailed(f"{label}: accepted[{k}] is {r['accepted'][k]!r}, expected {wa!r}"
                              + (f" (its d2 is {wd:.2f} ≤ the threshold): the gate compares d2 — the nis of kf_update, "
                                 "which includes P and R — with gate_threshold(gate_p), not a distance in metres or "
                                 "in σ_z" if wa is True and wd is not None else ""))
        if not np.allclose(x, want["x"][k], atol=1e-6):
            hint = ""
            if k > 0 and want["accepted"][k] is False:
                hint = " — a refused fix changes nothing: keep the predicted state"
            elif k > 0 and want["d2"][k] is None:
                hint = " — no fix: the state is the prediction (predict at EVERY time)"
            raise CheckFailed(f"{label}: the state at k = {k} is {np.round(x, 3)}, expected "
                              f"{np.round(want['x'][k], 3)}" + (upstream_note() or hint))
        if abs(P[0, 0] - want["P00"][k]) > 1e-6 or abs(P[2, 3] - want["P23"][k]) > 1e-6:
            refused = [j for j in range(1, k + 1) if want["accepted"][j] is False]
            hint = (f" — a refused fix must change nothing (k = {refused[-1]} was refused): keep the predicted x AND P "
                    "(x, P = x_u, P_u only when the fix is accepted)") if refused else \
                " — append a copy of P after each time"
            raise CheckFailed(f"{label}: P at k = {k} is off (P[0][0] {P[0, 0]:.4f}, expected {want['P00'][k]:.4f})"
                              + (upstream_note() or hint))
    return True


@c.test("TODO 7: run_filter() without a gate on an unseen flight — irregular times, a gap",
        hint="Lesson §5 and the docstring: start at [e0, n0, 0, 0] with diag(σ_z², σ_z², v0_sigma², v0_sigma²); at every "
             "next time predict over dt = times[k] − times[k−1]; with a fix, kf_update with H = [I 0], R = σ_z² I; "
             "append x, P, d2 (None without a fix) and accepted (None without a fix) at every time.")
def _():
    (f,) = functions("run_filter")
    times, zs, sz, q = flight_inputs()
    r = go(f, times, zs, sz, q, seconds=60)
    c.ok(compare_run(r, E["flight"]["runs"]["None"], "no gate"))
    r = go(f, times, zs, sz, q, v0_sigma=5.0, seconds=60)
    if not isinstance(r, dict) or "x" not in r:
        raise CheckFailed("run_filter() must return a dict of four lists")
    xs = [mat(v, (4,), "a state") for v in r["x"]]
    c.ok(all(np.allclose(a, b, atol=1e-6) for a, b in zip(xs, E["flight"]["v0_5"])),
         "with v0_sigma = 5.0 the result is not right: the start P uses the argument v0_sigma (not 20)")


@c.test("TODO 7: run_filter() with a 95 % gate on the same flight — wrong fixes refused, nothing moved by them",
        hint="With gate_p, a fix whose d2 (the nis of kf_update) is above gate_threshold(gate_p) is refused: accepted = "
             "False, d2 still recorded, and the state stays the prediction.")
def _():
    (f,) = functions("run_filter")
    times, zs, sz, q = flight_inputs()
    r = go(f, times, zs, sz, q, gate_p=0.95, seconds=60)
    c.ok(compare_run(r, E["flight"]["runs"]["0.95"], "gate 0.95"))


@c.test("Step 5: the NEES band of the lab's flight — prediction and numbers",
        hint="PREDICT_BAND before running. python3 band_sim.py: the band for n = 2, N = 361, p = 0.95 (two decimals).")
def _():
    pb, lo, hi = answers("PREDICT_BAND", "BAND_LOW", "BAND_HIGH")
    predicted("PREDICT_BAND", pb)
    lo, hi = number(lo, "BAND_LOW"), number(hi, "BAND_HIGH")
    if lo > hi:
        raise CheckFailed("BAND_LOW is larger than BAND_HIGH: swapped?")
    c.near(lo, LAB["BAND_LOW"], 0.02, "BAND_LOW (n = 2, N = 361)")
    c.near(hi, LAB["BAND_HIGH"], 0.02, "BAND_HIGH (n = 2, N = 361)")


@c.test("Steps 6–7: the flight without and with the gate, the jam, and the judge — numbers and explanation",
        hint="python3 run_kalman.py track 0.3 (mean NEES, σ east and the true error at the end of the jam), then track 0.3 "
             "0.99 (mean NEES, wrong and good fixes refused, d² after the jam). JUDGE_D2 = 150² / (SIGMA_END_JAM_M² + "
             "5²). EXPLAIN_GATE: 1 % of good fixes by definition; wrong fixes believed with a small P.")
def _():
    nng, sj, ej, pg, ng, wr, gr, d2, why, jd, ja = answers(
        "NEES_NO_GATE", "SIGMA_END_JAM_M", "ERR_END_JAM_M", "PREDICT_GATE", "NEES_GATE", "WRONG_REFUSED",
        "GOOD_REFUSED", "D2_AFTER_JAM", "EXPLAIN_GATE", "JUDGE_D2", "JUDGE_ACCEPT")
    nng, ng = number(nng, "NEES_NO_GATE"), number(ng, "NEES_GATE")
    if abs(nng - LAB["NEES_GATE"]) < 0.05 and abs(ng - LAB["NEES_NO_GATE"]) < 0.2:
        raise CheckFailed("NEES_NO_GATE and NEES_GATE are swapped")
    c.near(nng, LAB["NEES_NO_GATE"], 0.1, "NEES_NO_GATE (track 0.3)")
    sj = number(sj, "SIGMA_END_JAM_M")
    c.near(sj, LAB["SIGMA_END_JAM_M"], 0.2, "SIGMA_END_JAM_M (σ east at the end of the jam, m)")
    ej = number(ej, "ERR_END_JAM_M")
    c.ok(abs(ej - LAB["ERR_END_JAM_M"]) < 0.3 or abs(ej - LAB["ERR_END_JAM_GATE_M"]) < 0.3,
         f"ERR_END_JAM_M = {ej:g}: copy the true error at the end of the jam from python3 run_kalman.py track 0.3")
    predicted("PREDICT_GATE", pg)
    c.near(ng, LAB["NEES_GATE"], 0.02, "NEES_GATE (track 0.3 0.99)")
    wr, gr = number(wr, "WRONG_REFUSED"), number(gr, "GOOD_REFUSED")
    if wr == LAB["GOOD_REFUSED"] and gr == LAB["WRONG_REFUSED"] and wr != gr:
        raise CheckFailed("WRONG_REFUSED and GOOD_REFUSED are swapped")
    c.ok(wr == LAB["WRONG_REFUSED"], f"WRONG_REFUSED = {wr:g}: how many of the 6 wrong fixes did the gate refuse?")
    c.ok(gr == LAB["GOOD_REFUSED"], f"GOOD_REFUSED = {gr:g}: copy 'good fixes refused' from track 0.3 0.99")
    d2 = number(d2, "D2_AFTER_JAM")
    c.ok(abs(d2 - LAB["D2_AFTER_JAM"]) < 0.02 or abs(d2 - LAB["D2_AFTER_JAM_NOGATE"]) < 0.02,
         f"D2_AFTER_JAM = {d2:g}: copy d² of the first fix after the jam (track 0.3 0.99)")
    explained("EXPLAIN_GATE", why,
              ((r"1 ?%", r"one percent", r"99", r"by definition", r"chance", r"random", r"expected", r"about 3",
                r"0\.01", r"tail", r"unlucky", r"normal"),
               'why a few good fixes are refused (e.g. "a 99 % gate refuses 1 % of honest fixes: about 3 of 315")'),
              ((r"pull", r"believ", r"accept", r"far", r"wrong fix", r"outlier", r"off", r"moved", r"small (p|σ|sigma)",
                r"overconfiden", r"jump"),
               'why wrong fixes raise the NEES (e.g. "each one pulls the estimate far off while P stays small")'))
    jd = number(jd, "JUDGE_D2")
    want = 150.0 ** 2 / (sj * sj + 25.0)
    if abs(jd - 150.0 ** 2 / (sj * sj)) < 0.005 and abs(want - jd) > 0.005:
        raise CheckFailed("JUDGE_D2: S = σ² + R — add the fix's own variance (5² = 25)")
    if abs(jd - 150.0 / math.sqrt(sj * sj + 25.0)) < 0.02:
        raise CheckFailed("JUDGE_D2: that is the distance in σ's; d² is its square")
    c.near(jd, want, 0.03, "JUDGE_D2 (150² / (SIGMA_END_JAM_M² + 25))")
    if not isinstance(ja, bool):
        raise CheckFailed(f"JUDGE_ACCEPT should be True or False (without quotes), got {ja!r}")
    c.ok(ja is (want <= 9.2103), "JUDGE_ACCEPT: compare your JUDGE_D2 with the 99 % threshold 9.21")


@c.test("Step 8: the tuner — the q you fly, and why",
        hint="python3 run_kalman.py sweep: keep the honest values (mean NEES inside your band), then the smallest error. "
             "EXPLAIN_TUNE: q = 0.01 and 0.03 lock out after the jam (σ too small, the first fix refused, then every "
             "one); q = 0.1 is overconfident (NEES above the band).")
def _():
    qb, why = answers("Q_BEST", "EXPLAIN_TUNE")
    qb = number(qb, "Q_BEST")
    if abs(qb - 0.1) < 1e-9:
        raise CheckFailed("Q_BEST = 0.1: its error is small, but its mean NEES is above the band — honest first")
    if abs(qb - 1.0) < 1e-9:
        raise CheckFailed("Q_BEST = 1: honest-looking but pessimistic (below the band) and a larger error than the best "
                          "honest value")
    c.ok(abs(qb - LAB["Q_BEST"]) < 1e-9, f"Q_BEST = {qb:g}: which q has its mean NEES inside the band, with the "
                                          "smallest error?")
    explained("EXPLAIN_TUNE", why,
              ((r"lock", r"lost", r"lose", r"refus", r"reject", r"never (came|comes) back", r"diverg", r"every fix",
                r"all (the )?fix"),
               'what happened to 0.01 and 0.03 after the jam (e.g. "the gate refused every fix: the filter locked out")'),
              ((r"small (σ|sigma|p)", r"too (sure|confident)", r"overconfiden", r"σ stayed", r"sigma stayed",
                r"did ?n.t grow", r"underestimat", r"(p|σ|sigma) (was |is )?too small",
                r"grew (only|too little|too slow)", r"only (grew|reached|rose)",
                r"(smaller|less|lower) than (the |its )?(true |real |actual )?error", r"while the (true|real|actual) error",
                r"(σ|sigma|\bp)\b.{0,40}\b(small|slow|little)", r"not grow enough", r"\d+(\.\d+)? ?> ?9\.2"),
               'why it happened (e.g. "σ stayed too small during the jam, so the first good fix looked too far")'),
              ((r"band", r"nees", r"honest", r"overconfiden", r"3\.1", r"3\.2", r"above"),
               'why not q = 0.1 (e.g. "its mean NEES 3.2 is above the band: overconfident")'))


@c.test("Step 9: the filter memo in report.md",
        hint="Keep the three headings; 150–350 words in your own words; quote the race's RMS errors (m), the mean NEES "
             "with the gate and your band, and the q you chose.")
def _():
    try:
        text = open("report.md", encoding="utf-8").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for h in ("## Predict and update", "## Choosing q and R", "## Gate and honesty"):
        c.ok(h in body, f"report.md must keep the heading '{h}'")
    words = re.findall(r"[A-Za-zÀ-ÿ0-9°'′.-]+", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok(len(words) >= 150, f"report.md has {len(words)} words: write at least 150")
    c.ok(len(words) <= 420, f"report.md has {len(words)} words: a memo is short — aim for 350 (the limit is 420)")
    low = body.lower()
    c.ok(re.search(r"\b1\.8[0-9]*\s*m\b", low) is not None and re.search(r"\b2\.7[0-9]*\s*m\b", low) is not None,
         "quote the race's RMS errors in m: your filter's and the raw heights' (python3 run_kalman.py race)")
    c.ok(re.search(r"\b2\.0[0-9]*\b", low) is not None and re.search(r"\b1\.8[0-9]*\b", low) is not None
         and re.search(r"\b2\.2[0-9]*\b", low) is not None,
         "quote the mean NEES with the gate (about 2.07) and your band (about 1.80 – 2.21)")
    c.ok(re.search(r"\bq\b[^.\n]{0,40}0\.3\b|0\.3\b[^.\n]{0,20}m²/s⁴|0\.3\s*m2/s4", low) is not None,
         "quote the q you chose (e.g. \"q = 0.3 m²/s⁴\")")


c.milestone("keeper", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "Steps 0–2", "Steps 3–4", label="Height keeper")
c.milestone("tracker", "TODO", "Step", label="Tracker")
c.run()
