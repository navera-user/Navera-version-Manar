"""Check of mission 17 — the IMU. Sealed: never shown to students.

Unseen inputs everywhere. Oracles: SciPy's Rotation (x, y, z, w, like ROS) for integration, tilt, compass and
north; the course reference's outputs on hidden inputs for the complementary filter (hidden/expected.json, made
by solutions/17-imu/make_expected.py). Expected values of the lab's answers are constants below (computed from
the course reference on datasets/17-imu; solutions/17-imu/TEACHER.md lists them).
"""
import contextlib
import io
import json
import math
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()
G = 9.80665

PAD_BIAS = (0.0636, -0.0321, 0.0946)    # °/s, mean of gx, gy, gz for t_s < 10
GYRO_ERR_300 = -28.42                   # run_imu.py gyro, heading error at 300 s
CORR_ERR_300 = -1.75                    # run_imu.py gyro 0.0636 -0.0321 0.0946 (rounding of the typed bias: ± 0.3)
TURN_BANK, TURN_ACC = 15.1, 0.9         # run_imu.py tilt, turn at t = 99.8 s
TAUS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)
BEST_TAU, BEST_RMS = 30.0, 1.85         # run_imu.py tau
TILT_RMS = {0.3: 4.82, 1.0: 4.63, 3.0: 3.92, 10.0: 2.56, 30.0: 1.85, 100.0: 2.26, 300.0: 2.67}
DECL = 3.348                            # WMM at (35.76, 10.75), 2026.79
NO_TILT_RMS, TILT_RMS_TRUE, ACC_TILT_RMS = 4.98, 0.81, 4.37   # run_imu.py compass, true-heading RMS
CHIP_MEAN = -3.35                       # run_imu.py compass, chip as delivered
CAPE_SIDE = 2254.5                      # 5000 · sin(26.80°)
FROZEN_T, SMALL_N_T = 13.34, 5.08       # run_imu.py stale / stale 5


def oracle():
    try:
        from scipy.spatial.transform import Rotation
    except ImportError:
        c.skip("SciPy is not installed on this computer: this check needs it as the oracle (tell your teacher)")
    return Rotation


def imu():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.imu", fresh=True)


def functions(*names):
    fns = need(imu(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/imu.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def quats(v, n, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return an N × 4 numpy array, got {type(v).__name__}")
    if a.shape != (n, 4):
        raise CheckFailed(f"{what} should return one quaternion per sample, shape ({n}, 4); got shape {a.shape}"
                          + (" — row 0 must be q0 itself" if a.shape == (n - 1, 4) else ""))
    if not np.all(np.isfinite(a)):
        raise CheckFailed(f"{what} returned nan/inf (a division by a zero length?)")
    return a


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, (tuple, list)) or (hasattr(v, "shape") and np.shape(v) != ()):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


def ang(R, q):
    """Angle (degrees) between a SciPy rotation and a quaternion (x, y, z, w)."""
    Rotation = oracle()
    return math.degrees((R.inv() * Rotation.from_quat(np.asarray(q, dtype=float))).magnitude())


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "rotation axis must not be zero" in msg:
            raise CheckFailed(msg + " — a rate of (0, 0, 0) has no axis: when the turn angle is 0, skip the turn")
        if "only length-1 arrays" in msg or "only size-1 arrays" in msg:
            raise CheckFailed(msg + " — math.atan2/math.hypot take single numbers: use np.arctan2 and np.hypot")
        if "truth value of an array" in msg:
            raise CheckFailed(msg + " — == on numpy arrays gives an array: compare tuples of numbers")
        if "math domain error" in msg:
            raise CheckFailed(msg + " — asin/acos got a value just outside [−1, 1]: clamp it first")
        if "'NoneType'" in msg:
            raise CheckFailed(msg + " — a function it calls returned None: is an earlier TODO still a stub?")
        raise


def wrap(e):
    return (e + 180.0) % 360.0 - 180.0


# ======================================================================== session 1 — Drift hunter
@c.test("TODO 1: integrate_gyro() on unseen rates — body frame, rate of sample k−1, uneven dt, zero rates (oracle: SciPy)",
        hint="Lesson §2: each step turns by the rate of sample k−1 during dt = t[k] − t[k−1], about the BODY axes (so on "
             "which side of q?). A zero rate means no turn. Row 0 is q0 normalised.")
def _():
    Rotation = oracle()
    (f,) = functions("integrate_gyro")
    rng = np.random.default_rng(1702)
    n = 25
    dt = rng.uniform(0.01, 0.08, n - 1)
    t = np.concatenate([[12.0], 12.0 + np.cumsum(dt)])
    w = rng.normal(0.0, 0.8, (n, 3))
    w[4] = 0.0
    w[n - 1] = 0.0
    R0 = Rotation.from_euler("ZYX", [2.1, 0.4, -0.7])
    q0 = 1.7 * R0.as_quat()                                    # not of length 1 on purpose
    got = quats(go(f, q0, t.tolist(), w), n, "integrate_gyro")
    if abs(np.linalg.norm(got[0]) - 1.0) > 1e-6:
        raise CheckFailed("row 0 must be q0 NORMALISED (q0 here has length 1.7): q_normalize(q0)")

    def build(rule):
        R, out = R0, [R0]
        for k in range(1, n):
            step = t[k] - t[k - 1] if rule != "dt0" else t[1] - t[0]
            wk = w[k - 1] if rule != "k" else w[k]
            d = Rotation.from_rotvec(wk * step)
            R = d * R if rule == "left" else R * d
            out.append(R)
        return out
    good = build("good")
    errs = [ang(good[k], got[k]) for k in range(n)]
    if max(errs) > 1e-6:
        for rule, msg in (("left", "the small turn multiplies on the LEFT (world axes): the gyro measures in the BODY "
                                   "frame, so it is q ⊗ Δq (lesson §2)"),
                          ("k", "you used the rate of sample k for the step k−1 → k: use ω[k−1], the rate measured at "
                                "the start of the step"),
                          ("dt0", "dt changes from step to step here: use t[k] − t[k−1] at every step")):
            alt = build(rule)
            if max(ang(alt[k], got[k]) for k in range(n)) < 1e-6:
                raise CheckFailed(msg)
        q, first = np.asarray(R0.as_quat(), dtype=float), [R0]
        for kk in range(1, n):                                  # the textbook first-order update q + ½·dt·q ⊗ (ω, 0)
            x, y, z, ww = q
            wx, wy, wz = w[kk - 1]
            dq = 0.5 * np.array([ww * wx + y * wz - z * wy, ww * wy - x * wz + z * wx,
                                 ww * wz + x * wy - y * wx, -x * wx - y * wy - z * wz])
            q = q + (t[kk] - t[kk - 1]) * dq
            q = q / np.linalg.norm(q)
            first.append(Rotation.from_quat(q))
        if max(ang(first[kk], got[kk]) for kk in range(n)) < 1e-6:
            raise CheckFailed("you used the first-order update q + ½·dt·q ⊗ ω: it is close (0.01°) but not exact; build "
                              "the exact small turn with q_from_axis_angle(ω, |ω|·dt) (lesson §2)")
        k = int(np.argmax(errs))
        raise CheckFailed(f"integrate_gyro on unseen rates: row {k} is {errs[k]:.3f}° away from the right attitude "
                          "(the first rows are fine?) — check the half angle (q_from_axis_angle does it) and dt")
    c.ok(True)


@c.test("TODO 2: tilt_from_accel() on unseen attitudes — numbers and whole arrays, ROS signs, radians",
        hint="Lesson §3: roll = arctan2(ay, az), ROS pitch = arctan2(−ax, hypot(ay, az)), in radians, with np.arctan2 and "
             "np.hypot so that arrays work. The size of the force does not matter (only its direction).")
def _():
    Rotation = oracle()
    (f,) = functions("tilt_from_accel")
    rng = np.random.default_rng(1703)
    yaw = rng.uniform(-3, 3, 8)
    pitch = rng.uniform(-1.2, 1.2, 8)
    roll = rng.uniform(-2.5, 2.5, 8)
    roll[0], pitch[0] = 1.05, 0.35                             # roll 60°, pitch 20°: atan2(−fx, fz) is far off
    R = Rotation.from_euler("ZYX", np.stack([yaw, pitch, roll], 1))
    fb = np.array([R[i].inv().apply([0, 0, G]) for i in range(8)]) * rng.uniform(0.9, 1.2, (8, 1))
    got = go(f, fb[:, 0], fb[:, 1], fb[:, 2])
    if not (isinstance(got, (tuple, list)) and len(got) == 2):
        raise CheckFailed(f"tilt_from_accel should return two values (roll_rad, pitch_rad), got {got!r}")
    try:
        r, p = (np.asarray(x, dtype=float).reshape(-1) for x in got)
    except (TypeError, ValueError):
        raise CheckFailed("tilt_from_accel on arrays should return two numpy arrays")
    if r.shape != (8,) or p.shape != (8,):
        raise CheckFailed(f"on arrays of 8 samples tilt_from_accel should return two arrays of 8 values, got sizes "
                          f"{r.size} and {p.size} — use np.arctan2 / np.hypot on whole arrays")
    if np.allclose(np.radians(r), roll, atol=1e-6):
        raise CheckFailed("these are degrees: return radians (np.arctan2 already gives radians)")
    if np.allclose(r, roll, atol=1e-6) and np.allclose(p, -pitch, atol=1e-6):
        raise CheckFailed("the pitch has the wrong sign: a positive ROS pitch is nose DOWN, so pitch = arctan2(−ax, …)")
    if np.allclose(r, roll, atol=1e-6) and abs(p[0] - math.atan2(-fb[0, 0], fb[0, 2])) < 1e-6:
        raise CheckFailed("the pitch uses only az below the line: with a 60° roll it is wrong — the denominator is "
                          "hypot(ay, az), the size of the force in the y–z plane")
    c.ok(np.allclose(r, roll, atol=1e-6), f"the roll on unseen attitudes is off by up to "
                                          f"{np.degrees(np.abs(r - roll)).max():.2f}°: roll = arctan2(ay, az)")
    c.ok(np.allclose(p, pitch, atol=1e-6), f"the ROS pitch on unseen attitudes is off by up to "
                                           f"{np.degrees(np.abs(p - pitch)).max():.2f}°")
    one = go(f, 0.0, -2.0, 9.6)
    if not (isinstance(one, (tuple, list)) and len(one) == 2):
        raise CheckFailed(f"tilt_from_accel(0.0, −2.0, 9.6) should return (roll_rad, pitch_rad), got {one!r}")
    c.ok(abs(float(one[0]) - math.atan2(-2.0, 9.6)) < 1e-9 and abs(float(one[1])) < 1e-9,
         "on single numbers, tilt_from_accel(0.0, −2.0, 9.6) should give roll atan2(−2.0, 9.6) and pitch 0")


@c.test("Steps 1–2: the pad bias, the drift forecast, the drift measured with and without the bias",
        hint="GYRO_BIAS_DEG_S: the mean of gx, gy, gz for t_s < 10, converted to °/s (three numbers, 4 decimals). "
             "DRIFT_FORECAST_DEG: your z bias × 300 s. Then python3 run_imu.py gyro, and run_imu.py gyro BX BY BZ with your "
             "bias: the heading error at 300 s. EXPLAIN_DRIFT: the sign (heading = 90° − yaw) and what is left after.")
def _():
    b, fc, pred, e1, e2, why = answers("GYRO_BIAS_DEG_S", "DRIFT_FORECAST_DEG", "PREDICT_DRIFT_SIGN",
                                       "GYRO_HEADING_ERR_DEG", "CORRECTED_HEADING_ERR_DEG", "EXPLAIN_DRIFT")
    if not (isinstance(b, (tuple, list)) and len(b) == 3):
        raise CheckFailed(f"GYRO_BIAS_DEG_S should be three numbers (x, y, z) in °/s, like (0.1, -0.2, 0.3); got {b!r}")
    b = [number(x, "GYRO_BIAS_DEG_S") for x in b]
    if all(abs(math.radians(x) - y) < 2e-5 for x, y in zip(PAD_BIAS, b)):
        raise CheckFailed("GYRO_BIAS_DEG_S is in rad/s: the log is in rad/s, convert the means to °/s (np.degrees)")
    for name, x, y in zip("xyz", b, PAD_BIAS):
        c.ok(abs(x - y) < 0.0012, f"the {name} bias {x:.4f} °/s is not the mean of g{name} on the pad (t_s < 10, the "
                                  "first 500 samples), in °/s")
    fc = number(fc, "DRIFT_FORECAST_DEG")
    c.ok(abs(abs(fc) - abs(b[2]) * 300.0) < 0.5, f"DRIFT_FORECAST_DEG = {fc}: it should be your z bias × 300 s "
                                                 f"(about {abs(b[2]) * 300:.1f}°), with the size of the bias the log shows")
    predicted("PREDICT_DRIFT_SIGN", pred)
    e1 = number(e1, "GYRO_HEADING_ERR_DEG")
    if abs(e1 + GYRO_ERR_300) < 0.15:
        raise CheckFailed("GYRO_HEADING_ERR_DEG has the wrong sign: copy the heading error of run_imu.py gyro at 300 s")
    c.near(e1, GYRO_ERR_300, 0.15, "GYRO_HEADING_ERR_DEG (degrees, at 300 s)")
    e2 = number(e2, "CORRECTED_HEADING_ERR_DEG")
    c.near(e2, CORR_ERR_300, 0.35, "CORRECTED_HEADING_ERR_DEG (run_imu.py gyro with YOUR three bias numbers, at 300 s)")
    explained("EXPLAIN_DRIFT", why,
              ((r"yaw", r"counter", r"clockwise", r"90", r"heading.*(decreas|smaller|less|negative)",
                r"(increas|grow).*yaw"), "why the sign is negative (a positive z bias, yaw and heading)"),
              ((r"remain", r"residual", r"estimat", r"noise", r"random", r"not exact", r"average", r"√", r"sqrt",
                r"error of the (mean|bias)", r"500"), "what is left after the bias is removed"))


@c.test("Step 3: the coordinated turn fools the accelerometer — prediction, numbers, explanation",
        hint="python3 run_imu.py tilt, the turn at t ≈ 99.8 s: true roll and accelerometer roll (1 s averages). "
             "EXPLAIN_TURN: the accelerometer feels thrust, which stays along the body's z axis in a coordinated turn.")
def _():
    pred, a, b, why = answers("PREDICT_SPEEDUP", "TURN_TRUE_BANK_DEG", "TURN_ACCEL_ROLL_DEG", "EXPLAIN_TURN")
    predicted("PREDICT_SPEEDUP", pred)
    a, b = number(a, "TURN_TRUE_BANK_DEG"), number(b, "TURN_ACCEL_ROLL_DEG")
    if abs(a - TURN_ACC) < 0.15 and abs(b - TURN_BANK) < 0.15:
        raise CheckFailed("TURN_TRUE_BANK_DEG and TURN_ACCEL_ROLL_DEG are swapped")
    c.near(a, TURN_BANK, 0.15, "TURN_TRUE_BANK_DEG (the turn at t ≈ 99.8 s)")
    c.near(b, TURN_ACC, 0.15, "TURN_ACCEL_ROLL_DEG (the turn at t ≈ 99.8 s)")
    explained("EXPLAIN_TURN", why,
              ((r"thrust", r"lift", r"rotor", r"propel", r"body.?s? z", r"along the body", r"perpendicular",
                r"specific force", r"total force", r"same direction"), "which force the accelerometer feels"),
              ((r"centripet", r"turn", r"accelerat", r"bank", r"circle", r"sideways", r"lateral"),
               "the acceleration of the turn"),
              ((r"level", r"cannot tell", r"can't tell", r"same as", r"equivalen", r"indistinguish", r"looks like",
                r"believ", r"thinks", r"fool", r"no (roll|tilt)", r"zero"), "why it then looks level"))


# ======================================================================== session 2 — Attitude engineer
@c.test("TODO 3: complementary() on unseen data — a still drone, a gyro bias (b·τ), a bumpy flight",
        hint="Lesson §4: each step, (1) turn with the gyro exactly as integrate_gyro; (2) seen_up = q_rotate(q, f/|f|); "
             "error = angle between seen_up and (0, 0, 1); (3) q ← q_from_axis_angle(seen_up × (0, 0, 1), (1 − α)·error) ⊗ q "
             "with α = τ/(τ + dt) — on the LEFT. Normalise.")
def _():
    Rotation = oracle()
    (f,) = functions("complementary")
    for label, acc, msg in (
            ("a level drone reading exactly (0, 0, 9.81)", [[0.0, 0.0, 9.81]] * 3,
             "seen_up is exactly up: the axis seen_up × up has length 0 and there is nothing to correct — skip the "
             "gravity step when the axis length is (almost) 0"),
            ("a free-fall sample f = (0, 0, 0)", [[0.0, 0.0, 9.81], [0.0, 0.0, 0.0], [0.0, 0.0, 9.81]],
             "f = (0, 0, 0) has no direction (free fall): skip the gravity step when |f| is 0")):
        try:
            got = quats(run(f, (0.0, 0.0, 0.0, 1.0), [0.0, 0.02, 0.04], np.zeros((3, 3)), np.array(acc), 1.0),
                        3, "complementary")
        except CheckFailed as e:
            raise CheckFailed(f"on {label}: {e} — {msg}")
        if not np.all(np.abs(np.abs(got[:, 3]) - 1.0) < 1e-9):
            raise CheckFailed(f"on {label} with no turn measured, the attitude must stay level — {msg}")
    data = json.loads(hidden("expected.json"))
    for name in ("still", "bias", "bumpy"):
        k = data[name]
        n = len(k["t"])
        got = quats(go(f, k["q0"], k["t"], np.array(k["gyro"]), np.array(k["acc"]), k["tau"], seconds=60),
                    n, "complementary")
        want = np.array(k["expected"])
        errs = np.array([ang(Rotation.from_quat(want[i]), got[i]) for i in range(n)])
        if errs.max() < 0.02:
            continue
        last = Rotation.from_quat(got[-1])
        up_got, up_want = last.apply([0, 0, 1]), Rotation.from_quat(want[-1]).apply([0, 0, 1])
        tilt_got = math.degrees(math.acos(max(-1.0, min(1.0, up_got[2]))))
        tilt_want = math.degrees(math.acos(max(-1.0, min(1.0, up_want[2]))))
        if name == "still":
            r1 = Rotation.from_quat(got[1]).apply([0, 0, 1])[:2]
            w1 = Rotation.from_quat(want[1]).apply([0, 0, 1])[:2]
            if np.linalg.norm(r1) < 1e-9 and tilt_got < 1.0:
                raise CheckFailed("a still drone whose gravity says 'tilted 22°': your filter never tilted — is the gravity "
                                  "step there, and is (1 − α) not 0?")
            if np.linalg.norm(r1) > 20 * np.linalg.norm(w1):
                raise CheckFailed("in the first step (τ = 2 s, dt = 0.02 s) the tilt jumped almost all the way: α and 1 − α "
                                  "are swapped? The GYRO side keeps α = τ/(τ + dt), gravity gets the small share 1 − α")
            turn = math.degrees(abs(math.atan2(r1[0] * w1[1] - r1[1] * w1[0], float(r1 @ w1))))
            if turn > 150:
                raise CheckFailed("the nudge tilts the drone AWAY from what gravity says: the axis is seen_up × (0, 0, 1), in "
                                  "that order (np.cross(seen_up, up))")
            if turn > 10:
                raise CheckFailed("the nudge tilts the drone in the wrong direction when the heading is not 90°: it is a turn "
                                  "of the WORLD about a world axis, so it multiplies on the LEFT: q_mul(nudge, q)")
            r1_tilt = math.degrees(math.acos(max(-1.0, min(1.0, Rotation.from_quat(got[1]).apply([0, 0, 1])[2]))))
            w1_tilt = math.degrees(math.acos(max(-1.0, min(1.0, Rotation.from_quat(want[1]).apply([0, 0, 1])[2]))))
            if r1_tilt < w1_tilt * 0.99 and abs(tilt_got - tilt_want) < 0.05:
                raise CheckFailed("the first nudge is a little too small: turn by (1 − α) × the ANGLE between seen_up and "
                                  "up, error = atan2(|seen_up × up|, seen_up_z) — |seen_up × up| alone is sin(error), "
                                  "not the angle")
            if abs(tilt_got - tilt_want) < 0.05:
                raise CheckFailed("the tilt is right but the attitude is turned about the vertical: the gravity nudge is a "
                                  "rotation about the horizontal axis seen_up × (0, 0, 1), multiplied on the LEFT (world "
                                  "frame) — not a blend of Euler angles")
            raise CheckFailed(f"a still drone, τ = 2 s: after 4 s your tilt is {tilt_got:.2f}° instead of {tilt_want:.2f}°")
        if name == "bias":
            roll_err = math.degrees(math.asin(max(-1.0, min(1.0, -up_got[1]))))
            if abs(abs(roll_err) - 0.5 * 30.0) < 1.0:
                raise CheckFailed("with a gyro bias of 0.5 °/s for 30 s your roll error is ~15°, like the gyro alone: the "
                                  "gravity step does not act (is 1 − α almost 0?)")
            raise CheckFailed(f"a level drone, gyro bias 0.5 °/s on x, τ = 4 s: after 30 s the roll error should settle "
                              f"near b·τ = 2.0°; yours is {abs(roll_err):.2f}°")
        i = int(np.argmax(errs))
        raise CheckFailed(f"on a bumpy unseen flight (uneven dt, τ = 0.4 s) your attitude at row {i} is {errs[i]:.2f}° "
                          "from the right one: is dt = t[k] − t[k−1]? the gyro step uses ω[k−1], gravity uses the force "
                          "of sample k")
    c.ok(True)


@c.test("Step 4: choosing τ — prediction, the best τ of the sweep, its error, and the trade-off",
        hint="TRACE_FIRST_ROLL_DEG: α = τ/(τ + dt), gravity moves the roll by (1 − α) × 30°. python3 run_imu.py tau: the τ with the smallest tilt RMS and that RMS. EXPLAIN_TAU: what goes wrong with a "
             "small τ (the fooled accelerometer, its noise) and with a large τ (the gyro bias, b·τ).")
def _():
    tr, pred, t, r, why = answers("TRACE_FIRST_ROLL_DEG", "PREDICT_TAU", "BEST_TAU_S", "BEST_TILT_RMS_DEG", "EXPLAIN_TAU")
    tr = number(tr, "TRACE_FIRST_ROLL_DEG")
    if abs(tr - 22.5) < 0.1:
        raise CheckFailed("TRACE_FIRST_ROLL_DEG = 22.5: that gives gravity the big share. α = 1.5/(1.5 + 0.5) = 0.75 is "
                          "the GYRO's share; gravity gets 1 − α = 0.25 of the 30°")
    c.near(tr, 7.5, 0.1, "TRACE_FIRST_ROLL_DEG (α = τ/(τ + dt); gravity moves the roll by (1 − α) × 30°)")
    predicted("PREDICT_TAU", pred)
    t = number(t, "BEST_TAU_S")
    if t not in TAUS:
        raise CheckFailed(f"BEST_TAU_S = {t}: choose one of the seven values of the sweep {TAUS}")
    if t != BEST_TAU:
        raise CheckFailed(f"BEST_TAU_S = {t:g} s: in the table of run_imu.py tau, look at the 'tilt RMS' column — which τ "
                          "gives the smallest?")
    c.near(number(r, "BEST_TILT_RMS_DEG"), BEST_RMS, 0.03, "BEST_TILT_RMS_DEG (the tilt RMS at that τ)")
    explained("EXPLAIN_TAU", why,
              ((r"noise", r"vibrat", r"turn", r"accelerat", r"fool", r"follow", r"copies"),
               "what a small τ does (it follows the fooled, noisy accelerometer)"),
              ((r"bias", r"drift", r"b ?·? ?τ", r"b\*tau", r"b ?x ?τ", r"b times", r"recover", r"slow"),
               "what a large τ does (the gyro bias, b·τ)"),
              ((r"trade", r"balance", r"compromise", r"between", r"middle", r"optimum", r"minimum", r"smallest sum"),
               "why the best τ lies in between (a trade-off)"))


@c.test("TODOs 4–5: mag_heading() and true_heading() on unseen attitudes and fields (north and south, tilted)",
        hint="Lesson §5: level = rot_y(pitch) @ rot_x(roll) @ m, heading = atan2(level[1], level[0]) in degrees, % 360. "
             "In FLU (y = LEFT) it is atan2(y, x), not atan2(−y, x). true = (magnetic + D) % 360.")
def _():
    Rotation = oracle()
    mh, th = functions("mag_heading", "true_heading")
    cases = ((37.0, 12.0, -18.0, 22.0, 41.0), (251.0, -25.0, 9.0, 31.0, -63.0), (152.0, 3.0, 28.0, 39.0, -1.0),
             (318.0, 15.0, -5.0, 18.0, 70.0))
    for hdg, roll, pitch, H, incl in cases:                      # heading, roll, ROS pitch (deg), field H µT, inclination
        Z = H * math.tan(math.radians(incl))
        m_world = np.array([0.0, H, -Z])                         # magnetic-north ENU: north H, down Z (up −Z)
        R = Rotation.from_euler("ZYX", [math.radians(90 - hdg), math.radians(pitch), math.radians(roll)])
        mb = R.inv().apply(m_world)
        got = num(go(mh, mb, math.radians(roll), math.radians(pitch)), "mag_heading")
        if not 0.0 <= got < 360.0:
            raise CheckFailed(f"mag_heading returned {got:.2f}: a heading is in [0, 360) — use % 360.0")
        if abs(wrap(got - (360.0 - hdg))) < 0.01:
            raise CheckFailed("mag_heading is the mirror image (360° − the right heading): in FLU, y points LEFT, so "
                              "heading = atan2(y, x) of the level field; atan2(−y, x) is for frames whose y points right")
        nocomp = math.degrees(math.atan2(mb[1], mb[0])) % 360.0
        if abs(wrap(got - nocomp)) < 0.01 and abs(wrap(nocomp - hdg)) > 0.1:
            raise CheckFailed(f"mag_heading gives {got:.2f}° for a heading of {hdg:.0f}° with roll {roll:.0f}°, ROS pitch "
                              f"{pitch:.0f}°: there is no tilt compensation — turn the field with rot_y(pitch) @ "
                              "rot_x(roll) first")
        bad = np.array([[1, 0, 0], [0, math.cos(math.radians(roll)), -math.sin(math.radians(roll))],
                        [0, math.sin(math.radians(roll)), math.cos(math.radians(roll))]]) @ \
            np.array([[math.cos(math.radians(pitch)), 0, math.sin(math.radians(pitch))], [0, 1, 0],
                      [-math.sin(math.radians(pitch)), 0, math.cos(math.radians(pitch))]]) @ mb
        if abs(wrap(got - math.degrees(math.atan2(bad[1], bad[0])))) < 0.01 and abs(wrap(got - hdg)) > 0.01:
            raise CheckFailed("the two turns are in the wrong order: undo the roll FIRST, then the pitch — "
                              "rot_y(pitch) @ rot_x(roll) @ m (the matrix next to m acts first)")
        c.ok(abs(wrap(got - hdg)) < 0.01, f"mag_heading on an unseen tilted case gives {got:.2f}° instead of {hdg:.2f}° "
                                          f"(roll {roll:.0f}°, ROS pitch {pitch:.0f}°, inclination {incl:.0f}°)")
    for mag, d, want in ((355.0, 12.8, 7.8), (4.0, -26.8, 337.2), (181.5, -11.0, 170.5)):
        got = num(go(th, mag, d), "true_heading")
        if abs(got - (mag - d) % 360) < 0.01:
            raise CheckFailed("true_heading subtracts the declination: true = magnetic + D (D is positive EAST)")
        if abs(got - want) > 0.01 and abs(got - (want if want < 180 else want - 360)) < 0.01:
            raise CheckFailed(f"true_heading({mag}, {d}) gives {got:.2f}: keep it in [0, 360) with % 360.0")
        c.ok(abs(got - want) < 0.01, f"true_heading({mag}, {d}) gives {got:.2f}")


@c.test("TODO 6: q_true_north() on unseen tilted attitudes and both signs of D (oracle: SciPy)",
        hint="Lesson §5: true north = the magnetic-north world turned by −D about Up: "
             "q_from_axis_angle((0, 0, 1), −radians(D)) ⊗ q_mag — on the LEFT (a world-frame turn).")
def _():
    Rotation = oracle()
    (f,) = functions("q_true_north")
    for (yaw, pitch, roll), d in (((0.7, 0.3, -0.5), 3.35), ((-2.4, -0.2, 0.6), -26.8), ((2.9, 0.45, 0.25), 12.8)):
        Rm = Rotation.from_euler("ZYX", [yaw, pitch, roll])
        turn = Rotation.from_rotvec([0, 0, -math.radians(d)])
        got = go(f, Rm.as_quat(), d)
        try:
            q = np.asarray(got, dtype=float).reshape(4)
        except (TypeError, ValueError):
            raise CheckFailed(f"q_true_north should return 4 numbers (x, y, z, w), got {got!r}")
        if ang(Rm * turn, q) < 1e-6:
            raise CheckFailed("q_true_north multiplies on the RIGHT (a turn about the drone's own up axis): the "
                              "declination turns the WORLD frame, so it multiplies on the LEFT")
        if ang(Rotation.from_rotvec([0, 0, math.radians(d)]) * Rm, q) < 1e-6:
            raise CheckFailed("the correction turns the wrong way: true heading = magnetic + D, so the world turns by "
                              "−D about Up (the yaw decreases by D)")
        if ang(Rotation.from_rotvec([0, 0, -d]) * Rm, q) < 1e-6:
            raise CheckFailed("D is in degrees: convert it with math.radians before building the turn")
        c.ok(abs(np.linalg.norm(q) - 1.0) < 1e-6, "q_true_north must return a unit quaternion")
        c.ok(ang(turn * Rm, q) < 1e-6, f"q_true_north on an unseen tilted attitude (D = {d}°) is "
                                       f"{ang(turn * Rm, q):.3f}° away from the right attitude")


@c.test("Steps 5–6: declination, the compass with and without tilt, Cape Town, the chip — numbers and explanations",
        hint="python3 run_imu.py compass: the declination; the true-heading RMS without and with the TRUE tilt; the chip's "
             "mean error as delivered. CAPE_TOWN_SIDE_M = 5000 · sin(|D|) with declination_deg(−33.92, 18.42, 2026.79).")
def _():
    d, a, b, cape, chip, w1, w2 = answers("DECLINATION_DEG", "COMPASS_NO_TILT_RMS_DEG", "COMPASS_TILT_RMS_DEG",
                                          "CAPE_TOWN_SIDE_M", "CHIP_MEAN_ERR_DEG", "EXPLAIN_COMPASS", "EXPLAIN_NORTH")
    d = number(d, "DECLINATION_DEG")
    if abs(d + DECL) < 0.02:
        raise CheckFailed("DECLINATION_DEG has the wrong sign: east is positive (the run prints it with its sign)")
    c.near(d, DECL, 0.02, "DECLINATION_DEG")
    a, b = number(a, "COMPASS_NO_TILT_RMS_DEG"), number(b, "COMPASS_TILT_RMS_DEG")
    if abs(a - TILT_RMS_TRUE) < 0.05 and abs(b - NO_TILT_RMS) < 0.05:
        raise CheckFailed("COMPASS_NO_TILT_RMS_DEG and COMPASS_TILT_RMS_DEG are swapped")
    if abs(b - ACC_TILT_RMS) < 0.05:
        raise CheckFailed("COMPASS_TILT_RMS_DEG: take the line compensated with the TRUE roll and pitch (the "
                          "accelerometer's tilt is fooled in the turns — that is the next line)")
    c.near(a, NO_TILT_RMS, 0.05, "COMPASS_NO_TILT_RMS_DEG (true-heading RMS, no tilt compensation)")
    c.near(b, TILT_RMS_TRUE, 0.05, "COMPASS_TILT_RMS_DEG (true-heading RMS, compensated with the true tilt)")
    cape = number(cape, "CAPE_TOWN_SIDE_M")
    if abs(cape - 5000 * math.tan(math.radians(26.8015))) < 10:
        raise CheckFailed("CAPE_TOWN_SIDE_M: after flying 5 km in a straight line at an angle D off the intended track, "
                          "the drone is 5000 · sin(D) to the side (tan would be for 5 km measured along the track)")
    if abs(cape - 5000 * abs(math.sin(26.8015))) < 10:
        raise CheckFailed("CAPE_TOWN_SIDE_M ≈ 4976 m: math.sin got 26.8 DEGREES as if they were radians — use "
                          "math.sin(math.radians(abs(D)))")
    c.near(cape, CAPE_SIDE, 10.0, "CAPE_TOWN_SIDE_M (metres)")
    chip = number(chip, "CHIP_MEAN_ERR_DEG")
    if abs(chip - DECL) < 0.05:
        raise CheckFailed("CHIP_MEAN_ERR_DEG has the wrong sign: it is the chip's heading − the true heading")
    c.near(chip, CHIP_MEAN, 0.05, "CHIP_MEAN_ERR_DEG (the chip as delivered: mean of heading − true heading)")
    explained("EXPLAIN_COMPASS", w1,
              ((r"vertical", r"inclin", r"dip", r"\bz\b", r"steep", r"50"), "the vertical part of the field"),
              ((r"tilt", r"roll", r"pitch", r"bank", r"lean"), "what a tilt does"),
              ((r"horizontal", r"mix", r"leak", r"x and y", r"project"), "where the vertical part goes"))
    explained("EXPLAIN_NORTH", w2,
              ((r"declination", r"magnetic north", r"\bd\b", r"3\.3", r"true north", r"wmm"),
               "why the chip's error is about −D"),
              ((r"world", r"frame", r"map", r"up axis", r"vertical", r"earth", r"enu"),
               "why the correction multiplies on the left (it turns the world frame)"),
              ((r"body", r"own", r"tilt", r"bank", r"level", r"drone's up", r"nose"),
               "what multiplying on the right would do instead"))


@c.test("TODO 7: StaleDetector.update() on unseen streams — whole sample, exact count, starts again, recovers",
        hint="Lesson §6: compare the WHOLE sample (as a tuple of floats) with the previous one; count the exact repeats "
             "in a row; a different sample starts the count again; True from the max_repeat-th repeat on (trace the "
             "docstring example by hand).")
def _():
    m = imu()
    cls = need(m, "StaleDetector")[0]
    if is_stub(getattr(cls, "update", None)):
        raise CheckFailed("StaleDetector.update() is not written yet (navera_lite/imu.py, TODO 7)")

    def feed(seq, n):
        d = go(cls, max_repeat=n)
        out = []
        for s in seq:
            v = go(d.update, s)
            if v is None:
                raise CheckFailed("update() returned None: return True or False for every sample")
            out.append(bool(v))
        return out
    A, B, C = (0.12, -0.5, 9.81), (0.12, -0.5, 9.80), (0.13, -0.5, 9.81)
    seq = [A, A, A, A, B, B, B, A, A, C, C, C, C, C]
    want = [False, False, False, True, False, False, False, False, False, False, False, False, True, True]
    got = feed(seq, 3)
    if got == [False, False, True, True, False, False, True, False, False, False, False, True, True, True]:
        raise CheckFailed("one sample too early: the FIRST sample is not a repeat — True only at the max_repeat-th REPEAT")
    if got == [False, False, False, False, False, False, False, False, False, False, False, False, False, True]:
        raise CheckFailed("one sample too late: with max_repeat = 3 the 3rd repeat (the 4th equal sample) is frozen")
    if got[:5] == [False, False, False, True, True]:
        raise CheckFailed("after a frozen run, a DIFFERENT sample (it changed only its last number) must give False: "
                          "compare the whole sample, and start the count again")
    if got[4:7] != [False, False, False] and got[6]:
        raise CheckFailed("the count did not start again after a different sample: set repeats back to 0 there")
    c.ok(got == want, f"StaleDetector(3) on an unseen stream returns {got}, expected True only at the 3rd repeat and "
                      "after it, and False as soon as the sample changes")
    got = feed([[1.0, 2.0], [1.0, 2.0], [1.0, 2.0]], 2)
    c.ok(got == [False, False, True], "samples may come as LISTS too: turn each into a tuple of floats before comparing "
                                      f"(got {got})")
    got = feed([(5, 1)] * 6, 1)
    c.ok(got == [False, True, True, True, True, True], f"StaleDetector(1) on six equal samples returns {got}")


@c.test("Step 7: the frozen IMU — when it is caught, a too-small max_repeat, and why",
        hint="python3 run_imu.py stale (max_repeat 50) and python3 run_imu.py stale 5: the first 'frozen' times. "
             "EXPLAIN_STALE: noise makes real samples differ; the timestamps kept coming; the hiccup at 5 s.")
def _():
    pred, a, b, why = answers("PREDICT_STALE", "FROZEN_T_S", "SMALL_N_T_S", "EXPLAIN_STALE")
    predicted("PREDICT_STALE", pred)
    a, b = number(a, "FROZEN_T_S"), number(b, "SMALL_N_T_S")
    if abs(a - 12.34) < 0.03 or abs(a - 12.36) < 0.03:
        raise CheckFailed("FROZEN_T_S is when the data STOPPED changing; the question is when YOUR detector says "
                          "'frozen' (run_imu.py stale)")
    c.near(a, FROZEN_T, 0.011, "FROZEN_T_S (s)")
    c.near(b, SMALL_N_T, 0.011, "SMALL_N_T_S (s, with max_repeat = 5)")
    explained("EXPLAIN_STALE", why,
              ((r"noise", r"never (repeat|the same|identical)", r"always (chang|differ)", r"last digit", r"random"),
               "why a live sensor never repeats exactly"),
              ((r"time ?stamp", r"stamp", r"fresh", r"still (come|publish)", r"message"),
               "why fresh timestamps do not prove fresh data"),
              ((r"hiccup", r"5 ?s", r"5\.0", r"short", r"false", r"too (small|early|soon)", r"glitch", r"missed",
                r"trade", r"slow", r"1 ?s", r"one second"), "the trade-off in max_repeat (the hiccup at 5 s)"),
              min_words=20)


@c.test("Step 8: the attitude memo in report.md",
        hint="Keep the three headings; 150–350 words in your own words; quote the best τ (in s) with its tilt RMS (in °), "
             "and the declination near Monastir (in °).")
def _():
    try:
        text = open("report.md", encoding="utf-8").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for h in ("## The gyroscope alone", "## Choosing τ", "## Compass, north and trust"):
        c.ok(h in body, f"report.md must keep the heading '{h}'")
    words = re.findall(r"[A-Za-zÀ-ÿ0-9°'.-]+", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok(len(words) >= 150, f"report.md has {len(words)} words: write at least 150")
    c.ok(len(words) <= 420, f"report.md has {len(words)} words: a memo is short — aim for 350 (the limit is 420)")
    low = body.lower()
    c.ok(re.search(r"\b30(\.0)?\s*s\b|τ\s*=\s*30|tau\s*=\s*30|\b30(\.0)?\s*sec", low) is not None,
         "quote the best τ of the sweep, with its unit (e.g. 'τ = … s')")
    c.ok(re.search(r"\b1\.8[0-9]?\s*°|\b1\.8[0-9]?\s*deg", low) is not None, "quote the tilt RMS at that τ, in degrees")
    c.ok(re.search(r"\b3\.3[0-9]*\s*°|\b3\.3[0-9]*\s*deg", low) is not None,
         "quote the declination near Monastir, in degrees")


c.milestone("drift", "TODO 1", "TODO 2", "Steps 1–2", "Step 3", label="Drift hunter")
c.milestone("engineer", "TODO", "Step", label="Attitude engineer")
c.run()
