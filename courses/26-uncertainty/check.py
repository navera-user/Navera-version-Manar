import json
import math
import os
import re
import shutil
import tempfile

import numpy as np

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/26-uncertainty"
P0 = np.array([[12.0, 5.0], [5.0, 6.0]])


def U():
    return load_student("uncertainty.py")


def K():
    return load_student("kalman.py")


def arr(x, what, shape=None):
    """x as a float numpy array, or a friendly failure."""
    if x is None:
        raise CheckFailed(f"{what} is None (the TODO is not done yet)")
    try:
        a = np.asarray(x, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should be numbers, got {x!r}")
    if shape is not None and a.shape != shape:
        raise CheckFailed(f"{what} should have the shape {shape}, got {a.shape}")
    return a


def close(got, want, tol, what):
    g = arr(got, what, np.shape(want))
    if not np.all(np.isfinite(g)) or np.max(np.abs(g - np.asarray(want, dtype=float))) > tol:
        raise CheckFailed(f"{what} is\n{np.round(g, 4)}\n       expected\n{np.round(np.asarray(want), 4)}  (± {tol:g})")


@c.test("sample_cov(): the 2x2 sample covariance (divide by N - 1)",
        hint="Subtract the mean of each column (points.mean(axis=0)), then d.T @ d / (N - 1). "
             "numpy.cov(points.T) must give the same matrix.")
def _():
    (f,) = need(U(), "sample_cov")
    pts = np.array([[0.0, 0.0], [2.0, 1.0], [4.0, 5.0], [-2.0, 2.0]])
    close(f(pts), np.cov(pts.T), 1e-9, "sample_cov(4 points)")
    close(f([[1.0, 1.0], [3.0, 3.0]]), [[2.0, 2.0], [2.0, 2.0]], 1e-9, "sample_cov([[1, 1], [3, 3]])")


@c.test("error_ellipse(): axes and direction from the eigen-decomposition",
        hint="vals, vecs = numpy.linalg.eigh(P): eigenvalues ascending, eigenvectors in the COLUMNS. "
             "a = k*sqrt(vals[1]); the major axis is vecs[:, 1]; angle = degrees(atan2(vn, ve)) brought into (-90, 90].")
def _():
    (f,) = need(U(), "error_ellipse")
    r = f(P0)
    c.ok(isinstance(r, tuple) and len(r) == 3 and None not in r, f"error_ellipse() should return (a, b, angle_deg), got {r!r}")
    c.near(r[0], 3.851097, 1e-4, "a for P = [[12, 5], [5, 6]]")
    c.near(r[1], 1.780182, 1e-4, "b for P = [[12, 5], [5, 6]]")
    c.near(r[2], 29.518122, 1e-3, "angle_deg for P = [[12, 5], [5, 6]]")
    a, b, ang = f(np.diag([1.0, 9.0]), 2.0)
    c.near(a, 6.0, 1e-9, "a of diag(1, 9) with k = 2")
    c.near(b, 2.0, 1e-9, "b of diag(1, 9) with k = 2")
    c.near(ang, 90.0, 1e-6, "angle of diag(1, 9) (the long axis points north: 90, not -90)")
    c.near(f(np.array([[6.0, -5.0], [-5.0, 12.0]]))[2], -60.481878, 1e-3, "angle for [[6, -5], [-5, 12]]")


@c.test("chi2_threshold(), mahalanobis2(), chi2_gate()",
        hint="chi2.ppf(p, dof); r^T S^-1 r with numpy.linalg.solve(S, r); the gate compares the two with dof = len(r).")
def _():
    u = U()
    th, m2, gate = need(u, "chi2_threshold", "mahalanobis2", "chi2_gate")
    c.near(th(0.95, 2), 5.991465, 1e-5, "chi2_threshold(0.95, 2)")
    c.near(th(0.99, 1), 6.634897, 1e-5, "chi2_threshold(0.99, 1)")
    c.near(m2([6.0, -2.0], P0), 8.170213, 1e-5, "mahalanobis2([6, -2], [[12, 5], [5, 6]])")
    c.near(m2([3.0], [[4.0]]), 2.25, 1e-9, "mahalanobis2([3], [[4]])")
    c.eq(bool(gate([6.0, -2.0], P0, 0.99)), True, "chi2_gate([6, -2], P, 0.99)")
    c.eq(bool(gate([6.0, -2.0], P0, 0.95)), False, "chi2_gate([6, -2], P, 0.95)")
    c.eq(bool(gate([7.0], [[4.0]], 0.99)), False, "chi2_gate([7], [[4]], 0.99)  (1 dof: 3.5 sigma)")


@c.test("propagate() and polar_to_en(): J P J^T",
        hint="propagate is one line: J @ P @ J.T. For polar_to_en, east = r sin b, north = r cos b; differentiate "
             "each with respect to r and to b (in radians), and convert sigma_bearing to radians too.")
def _():
    u = U()
    prop, pol = need(u, "propagate", "polar_to_en")
    J = np.array([[1.0, 2.0], [0.0, 1.0]])
    close(prop(J, np.diag([1.0, 4.0])), [[17.0, 8.0], [8.0, 4.0]], 1e-9, "propagate([[1, 2], [0, 1]], diag(1, 4))")
    r = pol(2000.0, 60.0, 5.0, 0.5)
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[1] is not None, f"polar_to_en() should return (en, P), got {r!r}")
    close(r[0], [1732.050808, 1000.0], 1e-4, "east, north of 2000 m at bearing 60 deg")
    close(r[1], [[94.904355, -121.077894], [-121.077894, 234.713065]], 1e-3, "covariance of the radar fix")


@c.test("fuse(): inverse-variance (information) fusion, scalar and 2-D",
        hint="Information = inverse covariance. P = inv(inv(P1) + inv(P2)); x = P @ (inv(P1) @ x1 + inv(P2) @ x2). "
             "numpy.atleast_1d / atleast_2d make scalars work too.")
def _():
    (f,) = need(U(), "fuse")
    r = f(100.0, 100.0, 110.0, 25.0)
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[0] is not None, f"fuse() should return (x, P), got {r!r}")
    c.near(np.ravel(r[0])[0], 108.0, 1e-6, "fused value of 100 m (var 100) and 110 m (var 25)")
    c.near(np.ravel(r[1])[0], 20.0, 1e-6, "fused variance")
    x, P = f([0.0, 0.0], P0, [6.0, -3.0], np.diag([64.0, 64.0]))
    Pw = np.linalg.inv(np.linalg.inv(P0) + np.eye(2) / 64.0)
    close(P, Pw, 1e-6, "fused 2x2 covariance")
    close(x, Pw @ (np.eye(2) / 64.0 @ np.array([6.0, -3.0])), 1e-6, "fused 2-D position")


@c.test("make_covariance(): the 9 numbers and the type of PositionEstimate",
        hint="Copy the 2x2 block into the top-left corner, the up variance at index 8, zeros elsewhere. "
             "Type 3 (KNOWN) with a correlation term, 2 (DIAGONAL_KNOWN) without, 0 and nine zeros for None.")
def _():
    (f,) = need(U(), "make_covariance")
    r = f(P0)
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[0] is not None,
         f"make_covariance() should return (list of 9 numbers, type), got {r!r}")
    cov, kind = r
    close(list(cov), [12.0, 5.0, 0.0, 5.0, 6.0, 0.0, 0.0, 0.0, 48.0], 1e-9, "make_covariance([[12, 5], [5, 6]])")
    c.eq(kind, 3, "its type")
    c.ok(all(type(v) is float for v in cov), "all 9 values must be Python floats (ROS float64 fields refuse numpy / int)")
    cov, kind = f(np.diag([9.0, 16.0]), 10.0)
    c.near(cov[8], 100.0, 1e-9, "up variance with sigma_up = 10")
    c.eq(kind, 2, "type of a diagonal matrix")
    cov, kind = f(None)
    c.eq((list(cov), kind), ([0.0] * 9, 0), "make_covariance(None)")


@c.test("the REAL NAVERA arbiter accepts your correlated covariance",
        hint="estimate_message() puts make_covariance() into a PositionEstimate; the estimator's _sane() checks "
             "symmetry and positive semi-definiteness, _stated_sigma() reads sqrt(max(cov[0], cov[4])).")
def _():
    msg_of, mk = need(U(), "estimate_message", "make_covariance")
    c.ok(mk(P0)[0] is not None, "finish make_covariance() first (TODO 7)")
    try:
        from navera_estimator.nodes.estimator_node import EstimatorNode as E
    except ImportError as e:
        c.skip(f"NAVERA's estimator cannot be imported here ({e})")
    m = msg_of(35.76, 10.81, P0)
    c.ok(E._sane(m), "the real arbiter's _sane() refuses this covariance: " + str(list(m.position_covariance)))
    s = E._stated_sigma(m)
    c.ok(s is not None and abs(s - math.sqrt(12.0)) < 1e-9, f"the real arbiter reads a stated sigma of {s}, expected sqrt(12)")
    m = msg_of(35.76, 10.81, None)
    c.ok(E._sane(m) and E._stated_sigma(m) is None, "with P2 None the arbiter must see 'uncertainty unknown'")


@c.test("cv_model(): F and Q of the constant-velocity model (1-D and 2-D)",
        hint="F1 = [[1, dt], [0, 1]], Q1 = q [[dt^4/4, dt^3/2], [dt^3/2, dt^2]]; for several axes numpy.kron(F1, numpy.eye(dims)).")
def _():
    (f,) = need(K(), "cv_model")
    r = f(2.0, 0.5, dims=1)
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[0] is not None, f"cv_model() should return (F, Q), got {r!r}")
    close(r[0], [[1.0, 2.0], [0.0, 1.0]], 1e-12, "F (dt = 2, 1-D)")
    close(r[1], [[2.0, 2.0], [2.0, 2.0]], 1e-12, "Q (dt = 2, q = 0.5, 1-D)")
    F, Q = f(1.0, 0.3)
    c.eq(np.shape(F), (4, 4), "the shape of F for dims = 2")
    close(F[0], [1.0, 0.0, 1.0, 0.0], 1e-12, "first row of F (east += v_east * dt)")
    close(Q[1], [0.0, 0.075, 0.0, 0.15], 1e-12, "second row of Q (north)")


@c.test("kf_predict() and kf_update(): one step by hand",
        hint="Predict: F x and F P F^T + Q. Update: nu = z - H x, S = H P H^T + R, K = P H^T S^-1, "
             "x + K nu, (I - K H) P. Return (x, P, nu, S).")
def _():
    k = K()
    cv, pr, up = need(k, "cv_model", "kf_predict", "kf_update")
    F, Q = cv(1.0, 0.3, dims=1)
    c.ok(F is not None, "finish cv_model() first (TODO 8)")
    r = pr(np.array([80.0, 0.0]), np.diag([9.0, 4.0]), F, Q)
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[0] is not None, f"kf_predict() should return (x, P), got {r!r}")
    x, P = r
    close(P, [[13.075, 4.15], [4.15, 4.3]], 1e-9, "P after predict")
    r = up(x, P, np.array([83.0]), np.array([[1.0, 0.0]]), np.array([[2.25]]))
    c.ok(isinstance(r, tuple) and len(r) == 4 and r[0] is not None, "kf_update() should return (x, P, nu, S)")
    x, P, nu, S = r
    close(x, [82.559543, 0.812398], 1e-5, "x after the update")
    close(P, [[1.919657, 0.609299], [0.609299, 3.176183]], 1e-5, "P after the update")
    close(np.ravel(nu), [3.0], 1e-9, "the innovation nu")
    close(np.ravel(S), [15.325], 1e-9, "the innovation covariance S")


@c.test("nees(): normalised estimation error squared",
        hint="It is the Mahalanobis distance squared of the ERROR with the filter's own covariance.")
def _():
    (f,) = need(K(), "nees")
    c.near(f(np.array([3.0, -1.0]), np.diag([4.0, 1.0])), 3.25, 1e-9, "nees([3, -1], diag(4, 1))")
    c.near(f(np.array([6.0, -2.0]), P0), 8.170213, 1e-5, "nees([6, -2], [[12, 5], [5, 6]])")


def track():
    import csv
    with open(f"{DATA}/track.csv") as fh:
        rows = list(csv.DictReader(fh))
    times = [float(r["t_s"]) for r in rows]
    zs = [None if r["z_e"] == "" else np.array([float(r["z_e"]), float(r["z_n"])]) for r in rows]
    truth = np.array([[float(r["true_e"]), float(r["true_n"])] for r in rows])
    return times, zs, truth, [r["outlier"] == "1" for r in rows]


@c.test("run_filter(): the 2-D Kalman filter with a chi-square gate on the coastal track",
        hint="Follow the docstring exactly: start from the first fix, predict every step, gate with "
             "mahalanobis2(nu, S) <= chi2_threshold(gate_p, 2), update only when accepted, append one entry per time.")
def _():
    (run,) = need(K(), "run_filter")
    times, zs, truth, outlier = track()
    out = run(times, zs, 5.0, 0.3, gate_p=0.99)
    c.ok(isinstance(out, dict) and all(k in out for k in ("x", "P", "d2", "accepted")),
         "run_filter() should return a dict with the lists x, P, d2, accepted")
    c.eq(len(out["x"]), len(times), "the number of states (one per time)")
    acc = out["accepted"]
    c.eq(sum(1 for a, o in zip(acc, outlier) if o and a is False), 6, "outliers refused by the gate")
    c.eq(sum(1 for a, o in zip(acc, outlier) if not o and a is False), 3, "good fixes refused (false alarms)")
    c.ok(all(a is None for a, z in zip(acc, zs) if z is None), "accepted must be None at times without a measurement")
    est = np.array([np.asarray(x, dtype=float)[:2] for x in out["x"]])
    seen = np.array([z is not None for z in zs])
    rmse = float(np.sqrt(np.mean(np.sum((est - truth) ** 2, axis=1)[seen])))
    c.near(rmse, 4.48379, 0.01, "RMSE of the gated filter on the measured steps (m)")
    Pend = np.asarray(out["P"][189], dtype=float)
    c.near(math.sqrt(Pend[0, 0]), 91.69, 0.5, "east sigma at the end of the 40 s gap (m) — it must GROW without fixes")
    raw = run(times, zs, 5.0, 0.3, gate_p=None)
    c.ok(all(a is not False for a in raw["accepted"]), "with gate_p=None nothing may be refused")


@c.test("race_navera.py: your 1-D filter IS NAVERA's height filter (TODO 13)",
        hint="Same model (q = 0.25), same start (x = [h, 0], P = diag(sigma^2, 4)), predict with the real dt between rows, "
             "update with R = [[sigma^2]]. Then run `python3 race_navera.py`.")
def _():
    m = load_student("race_navera.py")
    sh_, rows_of, nav = need(m, "student_heights", "load_rows", "navera_heights")
    rows = rows_of()
    mine = sh_(rows)
    c.ok(isinstance(mine, list) and len(mine) == len(rows), f"student_heights() should return one (height, sigma) per row ({len(rows)})")
    try:
        real = nav(rows)
    except ImportError as e:
        c.skip(f"NAVERA's day_pkg cannot be imported here ({e})")
    dh = max(abs(float(a[0]) - b[0]) for a, b in zip(mine, real))
    ds = max(abs(float(a[1]) - b[1]) for a, b in zip(mine, real))
    c.ok(dh < 1e-6 and ds < 1e-6, f"largest difference with NAVERA: height {dh:.3g} m, sigma {ds:.3g} m (want < 1e-6)")
    c.file_exists("race.json")


def results():
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet: run `python3 analyse.py`")
    with open("results.json") as fh:
        return json.load(fh)


_fresh = {}


def fresh_results():
    """Run YOUR analyse.py (with your uncertainty.py and kalman.py) again in a scratch folder: the graded
    numbers come from your code, not from a results.json that could have been edited by hand."""
    if "r" not in _fresh:
        tmp = tempfile.mkdtemp(prefix="check26_")
        try:
            for f in ("analyse.py", "uncertainty.py", "kalman.py"):
                if not os.path.exists(f):
                    raise CheckFailed(f"{f} is missing (↺ Reset lab files gives it back)")
                shutil.copy(f, tmp)
            code, out = sh(f"cd {tmp} && MPLBACKEND=Agg python3 -B analyse.py", timeout=90)
            if code != 0 or not os.path.exists(os.path.join(tmp, "results.json")):
                raise CheckFailed("`python3 analyse.py` did not write results.json:\n" + out[-600:])
            with open(os.path.join(tmp, "results.json")) as fh:
                _fresh["r"] = json.load(fh)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return _fresh["r"]


@c.test("analyse.py: results.json (ellipse, fusion, gating counts, NEES — TODO 14 and 15)",
        hint="Keep Q_FILTER = 0.3 and GATE_P = 0.99, finish TODO 14 (count refusals by kind) and TODO 15 "
             "(mean NEES and chi2.ppf(0.025 / 0.975, 2N) / N), then run `python3 analyse.py`.")
def _():
    r = fresh_results()
    s, t = r["static"], r["track"]
    saved = results()
    for path in (("static", "a_m"), ("track", "gated", "mean_nees"), ("track", "gated", "caught"),
                 ("track", "gated", "false_alarms"), ("track", "nees_band_95")):
        mine, real = saved, r
        for k in path:
            mine, real = (mine or {}).get(k), real.get(k)
        c.ok(mine == real, f"results.json {'.'.join(path)} = {mine!r}, but your analyse.py gives {real!r} "
                           f"now: run `python3 analyse.py` again (and do not edit results.json by hand)")
    c.near(s["a_m"], 4.16957, 0.005, "static: semi-major axis a (m)")
    c.near(s["angle_deg"], 29.78, 0.05, "static: angle of the major axis (deg)")
    c.near(s["share_1s"], 0.3975, 0.003, "static: share inside the 1-sigma ellipse")
    c.near(r["fusion"]["bad"]["d2"], 27.348, 0.01, "fusion: d2 of the bad vision fix")
    c.eq(r["fusion"]["bad"]["accepted"], False, "fusion: the bad vision fix is accepted?")
    c.eq((t["q"], t["gate_p"]), (0.3, 0.99), "Q_FILTER and GATE_P used")
    c.eq((t["gated"]["caught"], t["gated"]["false_alarms"]), (6, 3), "TODO 14: (caught, false_alarms)")
    c.near(t["gated"]["mean_nees"], 1.92543, 0.002, "TODO 15: mean NEES of the gated filter")
    c.near(t["nees_band_95"][0], 1.79898, 0.002, "TODO 15: lower end of the 95 % band")
    c.near(t["nees_band_95"][1], 2.21151, 0.002, "TODO 15: upper end of the 95 % band")
    c.near(t["ungated"]["rmse_m"], 11.3095, 0.01, "RMSE of the ungated filter (m)")


@c.test("the three pictures: ellipse.png, track.png, nees.png",
        hint="analyse.py writes them at the end; open them in the editor and look at them before writing the report.")
def _():
    for name in ("ellipse.png", "track.png", "nees.png"):
        c.file_exists(name)
        with open(name, "rb") as fh:
            c.ok(fh.read(8) == b"\x89PNG\r\n\x1a\n", f"{name} is not a PNG image")


SECTIONS = [
    ("## 1. The error ellipse", [("a (m)", "a_m", 0.06), ("share inside the 1-sigma ellipse (%)", "share_1s_pct", 0.6)]),
    ("## 2. Fusion and gating", [("RMSE with the gate (m)", "rmse_g", 0.06), ("RMSE without the gate (m)", "rmse_u", 0.06)]),
    ("## 3. Consistency (NEES)", [("mean NEES", "nees", 0.015)]),
    ("## 4. NAVERA", [("probability of NAVERA's 3-sigma gate (%)", "p3", 0.15),
                      ("sigma that _stated_sigma() reads (m)", "stated", 0.06)]),
]


@c.test("report.md: four sections, your own words, the right numbers",
        hint="Each section needs at least 40 words and the numbers listed in report.md, copied from YOUR results "
             "(2 decimals is fine). For section 4: P(chi-square with 2 dof <= 9) and sqrt(max(P[0][0], P[1][1])).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    first = text.find("\n## ")                      # the instructions above the first heading are not graded
    body_text = text[first:] if first >= 0 else text
    c.ok(not re.search(r"\bTODO\b", body_text) and "…" not in body_text,
         "report.md still contains a TODO paragraph or a … placeholder under a heading")
    r = fresh_results()
    vals = {"a_m": r["static"]["a_m"], "share_1s_pct": 100 * r["static"]["share_1s"],
            "rmse_g": r["track"]["gated"]["rmse_m"], "rmse_u": r["track"]["ungated"]["rmse_m"],
            "nees": r["track"]["gated"]["mean_nees"], "p3": 100 * (1 - math.exp(-4.5)),
            "stated": r["static"].get("navera_stated_sigma_m", 0.0)}
    starts = [text.find(h) for h, _ in SECTIONS]
    for (h, _), s in zip(SECTIONS, starts):
        c.ok(s >= 0, f"the heading '{h}' is missing (copy it exactly)")
    bad = []
    for i, (h, needs) in enumerate(SECTIONS):
        end = min([s for s in starts if s > starts[i]] + [len(text)])
        body = text[starts[i] + len(h):end]
        words = len(re.findall(r"[A-Za-z]{2,}", body))
        if words < 40:
            bad.append(f"'{h}' has {words} words (at least 40)")
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", body)]
        for label, key, tol in needs:
            if not any(abs(n - vals[key]) <= tol for n in nums):
                bad.append(f"'{h}': I can't find {label} ≈ {vals[key]:.2f}")
    c.ok(not bad, "; ".join(bad))


c.run()
