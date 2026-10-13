"""Check of mission 16 — rotations and quaternions. Sealed: never shown to students.

Unseen inputs everywhere; the oracle for the functions is SciPy's Rotation (x, y, z, w, like ROS).
Expected values of the lab's answers are constants below (computed from the course reference,
solutions/16-rotations/TEACHER.md lists them).
"""
import contextlib
import io
import math
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, is_stub, load_student, need, predicted, run

c = Checker()

PITCH_UP = -6.8755          # −degrees(0.12)
LOCK_UP_YAW = 80.0          # roll 30, ROS pitch −90, yaw 50 → ψ + φ
NEAR_LOCK_JUMP = 63.43      # run_rotations.py gimbal
POSE = (11.997, 215.005)    # rpy_human of (−0.1245, 0.0134, −0.8834, 0.4516): pitch_up, heading
LERP_ERR = 5.45             # run_rotations.py slerp, t = 0.2: 42.00 − 36.55
PAD_HEADING, PAD_ROLL, MAX_TILT, FLIP_T = 30.0, 60.0, 174.0, 111.4   # detective.py on the dataset


def oracle():
    try:
        from scipy.spatial.transform import Rotation, Slerp
    except ImportError:
        c.skip("SciPy is not installed on this computer: this check needs it as the oracle (tell your teacher)")
    return Rotation, Slerp


def rot():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.rotations", fresh=True)


def functions(*names):
    fns = need(rot(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/rotations.py)")
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


def mat(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return a 3 × 3 numpy array, got {v!r}")
    if a.shape != (3, 3):
        raise CheckFailed(f"{what} should return a 3 × 3 numpy array, got shape {a.shape}")
    return a


def vec(v, n, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        a = np.asarray(v, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return {n} numbers, got {v!r}")
    if a.shape != (n,):
        raise CheckFailed(f"{what} should return {n} numbers, got {a.size}: {v!r}")
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


def qd(a, b):
    """Sign-free distance between quaternions."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return min(np.abs(a - b).max(), np.abs(a + b).max())


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "math domain error" in msg:
            raise CheckFailed(msg + " — asin/acos got a value just outside [−1, 1]: clamp it first")
        if "'NoneType'" in msg:
            raise CheckFailed(msg + " — a function it calls returned None: is an earlier TODO still a stub?")
        raise


# ======================================================================== session 1 — Attitude reader
@c.test("TODO 1: rot_y() on unseen angles — a proper rotation, positive = nose DOWN",
        hint="Lesson §2: Ry(α) = [[cos α, 0, sin α], [0, 1, 0], [−sin α, 0, cos α]], α in radians. The minus sign "
             "sits in row 2, column 0 (the right-hand rule about +y carries z towards x).")
def _():
    Rotation, _ = oracle()
    (f,) = functions("rot_y")
    for a in (-0.7, 2.2, 0.05):
        m = mat(go(f, a), f"rot_y({a})")
        if np.allclose(m, Rotation.from_euler("y", -a).as_matrix(), atol=1e-9):
            raise CheckFailed(f"rot_y({a}) turns the wrong way (it is the transpose): a positive angle must carry the "
                              "nose (1, 0, 0) DOWN — the −sin goes in row 2, column 0")
        if np.allclose(m, Rotation.from_euler("y", math.radians(a)).as_matrix(), atol=1e-9):
            raise CheckFailed(f"rot_y({a}): you converted the angle with math.radians — it is already in radians")
        c.ok(np.allclose(m, Rotation.from_euler("y", a).as_matrix(), atol=1e-9),
             f"rot_y({a}) is not the rotation about y: {np.round(m, 4).tolist()}")


@c.test("TODO 2: rot_z() on unseen angles — counter-clockwise seen from above",
        hint="Lesson §2: Rz(α) = [[cos α, −sin α, 0], [sin α, cos α, 0], [0, 0, 1]]: a positive yaw carries east "
             "towards north.")
def _():
    Rotation, _ = oracle()
    (f,) = functions("rot_z")
    for a in (-1.3, 2.9, 0.4):
        m = mat(go(f, a), f"rot_z({a})")
        if np.allclose(m, Rotation.from_euler("z", -a).as_matrix(), atol=1e-9):
            raise CheckFailed(f"rot_z({a}) is the transpose: a positive yaw must carry east (1, 0, 0) towards NORTH")
        c.ok(np.allclose(m, Rotation.from_euler("z", a).as_matrix(), atol=1e-9),
             f"rot_z({a}) is not the rotation about z: {np.round(m, 4).tolist()}")


@c.test("TODO 3: euler_zyx_to_matrix() = Rz(yaw)·Ry(pitch)·Rx(roll) on unseen attitudes (oracle: SciPy)",
        hint="Lesson §3: one line, `rot_z(yaw_rad) @ rot_y(pitch_rad) @ rot_x(roll_rad)` — `@`, yaw on the left. "
             "If TODO 1 or 2 fails, fix it first: this function uses them.")
def _():
    Rotation, _ = oracle()
    (f,) = functions("euler_zyx_to_matrix")
    for roll, pitch, yaw in ((-0.35, 0.42, 2.8), (1.1, -0.9, -2.3), (0.0, 0.25, 0.0)):
        m = mat(go(f, roll, pitch, yaw), f"euler_zyx_to_matrix({roll}, {pitch}, {yaw})")
        want = Rotation.from_euler("ZYX", [yaw, pitch, roll]).as_matrix()
        if np.allclose(m, Rotation.from_euler("XYZ", [roll, pitch, yaw]).as_matrix(), atol=1e-9) \
                and not np.allclose(m, want, atol=1e-9):
            raise CheckFailed("wrong ORDER: you built Rx·Ry·Rz — the ZYX attitude is Rz(yaw) @ Ry(pitch) @ Rx(roll)")
        if np.allclose(m, Rotation.from_euler("ZYX", [roll, pitch, yaw]).as_matrix(), atol=1e-9) \
                and not np.allclose(m, want, atol=1e-9):
            raise CheckFailed("roll and yaw are swapped: the arguments are (roll_rad, pitch_rad, yaw_rad), and yaw "
                              "goes into rot_z")
        if np.count_nonzero(np.abs(m) < 1e-12) >= 4 and not np.allclose(m, want, atol=1e-9):
            raise CheckFailed("`*` multiplies element by element: multiply the matrices with `@`")
        c.ok(np.allclose(m, want, atol=1e-9), f"euler_zyx_to_matrix({roll}, {pitch}, {yaw}): the nose (first column) "
             f"is {np.round(m[:, 0], 4).tolist()}, not the ZYX attitude")
    nose = mat(go(f, 0.0, 0.25, 0.0), "euler_zyx_to_matrix(0, 0.25, 0)")[:, 0]
    c.ok(nose[2] < 0, "a positive ROS pitch must put the nose DOWN (its up component negative): check rot_y (TODO 1)")


@c.test("TODO 4: matrix_to_euler_zyx() — unseen attitudes, both gimbal locks, and a matrix just past ±1",
        hint="Lesson §3: pitch = asin(clamp(−R[2][0])), roll = atan2(R[2][1], R[2][2]), yaw = atan2(R[1][0], R[0][0]), "
             "locked False. FIRST test the lock: if hypot(R[0][0], R[1][0]) < 1e-6 → (0.0, pitch, "
             "atan2(−R[0][1], R[1][1]), True). Radians.")
def _():
    Rotation, _ = oracle()
    (f,) = functions("matrix_to_euler_zyx")

    def four(v, what):
        if not (isinstance(v, (tuple, list)) and len(v) == 4):
            raise CheckFailed(f"{what} should return 4 values (roll, pitch, yaw, locked), got {v!r}")
        return [float(x) for x in v[:3]], v[3]

    for roll, pitch, yaw in ((0.6, -1.2, -2.9), (-2.8, 0.3, 1.4), (0.1, 1.5, 3.0)):
        R = Rotation.from_euler("ZYX", [yaw, pitch, roll]).as_matrix()
        (r, p, y), locked = four(go(f, R), "matrix_to_euler_zyx")
        if abs(p + pitch) < 1e-6 and abs(pitch) > 1e-3:
            raise CheckFailed("the pitch has the wrong sign: pitch = asin(−R[2][0])")
        if max(abs(r), abs(p), abs(y)) > 2 * math.pi + 0.01:
            raise CheckFailed("these look like DEGREES: return radians")
        c.ok(abs(r - roll) < 1e-9 and abs(p - pitch) < 1e-9 and abs(y - yaw) < 1e-9 and not locked,
             f"for (roll, pitch, yaw) = ({roll}, {pitch}, {yaw}) you return ({r:.4f}, {p:.4f}, {y:.4f}, {locked})")
    for roll, pitch, yaw, want in ((0.4, math.pi / 2, -1.0, -1.4), (-0.5, -math.pi / 2, 0.8, 0.3)):
        R = Rotation.from_euler("ZYX", [yaw, pitch, roll]).as_matrix()
        (r, p, y), locked = four(go(f, R), "matrix_to_euler_zyx at the lock")
        c.ok(bool(locked) is True, f"at ROS pitch {math.degrees(pitch):+.0f}° the 4th value `locked` must be True "
                                   "(|cos(pitch)| < 1e-6)")
        c.ok(r == 0.0, f"at the lock roll must be 0.0 by convention, got {r:.4f}")
        c.ok(abs(y - want) < 1e-6 and abs(p - pitch) < 1e-6,
             f"at ROS pitch {math.degrees(pitch):+.0f}° you return yaw {y:.4f} rad: at the lock yaw = "
             "atan2(−R[0][1], R[1][1])")
    R = Rotation.from_euler("ZYX", [0.2, math.pi / 2, 0.0]).as_matrix()
    R[2, 0] = -1.0000000002
    (r, p, y), locked = four(go(f, R), "matrix_to_euler_zyx with R[2][0] = −1.0000000002")
    c.ok(abs(p - math.pi / 2) < 1e-6 and bool(locked), "with R[2][0] = −1.0000000002 (rounding) the pitch must still be "
                                                      "+90°: clamp before asin")


@c.test("Step 1: which way a positive ROS pitch moves the nose — prediction, number and explanation",
        hint="pitch_up = −(ROS pitch), in degrees: −math.degrees(0.12). EXPLAIN_PITCH: the axis (y = left wing) "
             "and the right-hand rule.")
def _():
    pred, v, why = answers("PREDICT_PITCH", "PITCH_UP_DEG", "EXPLAIN_PITCH")
    predicted("PREDICT_PITCH", pred)
    x = number(v, "PITCH_UP_DEG")
    if abs(x - abs(PITCH_UP)) < 0.05:
        raise CheckFailed("PITCH_UP_DEG has the wrong sign: a positive ROS pitch is nose DOWN, so the pilot's "
                          "pitch_up is negative")
    if abs(abs(x) - 0.12) < 0.01:
        raise CheckFailed("PITCH_UP_DEG is in radians: convert to degrees")
    c.near(x, PITCH_UP, 0.05, "PITCH_UP_DEG (degrees)")
    explained("EXPLAIN_PITCH", why, ((r"\by\b", r"left", r"wing", r"axis"), "the axis of the rotation (y, the left wing)"),
              ((r"right.?hand", r"thumb", r"finger", r"curl", r"counter", r"clockwise", r"z.*x", r"up.*(nose|forward)"),
               "the right-hand rule"),
              ((r"down", r"below", r"dip", r"lower"), "that the nose goes down"))


@c.test("Step 2: the order of rotations — prediction and explanation",
        hint="Run python3 run_rotations.py order and look at out/order.png (green = left wing). Lesson §2: read a product "
             "left to right about the drone's own, moving axes. Answer the three parts of the task: same attitude or "
             "not, which letter, why.")
def _():
    pred, why = answers("PREDICT_ORDER", "EXPLAIN_ORDER")
    predicted("PREDICT_ORDER", pred)
    if not (isinstance(why, str) and why.strip()):
        raise CheckFailed("EXPLAIN_ORDER is still empty")
    w = re.sub(r"\b[AB]\s+(?:is\s+not|isn't|is\s+NOT)\b|\b[Nn]ot\s+[AB]\b", " ", why)   # "A is not …" names no A
    named = set(re.findall(r"\b([AB])\b(?=\s*(?:is|=|:|,|\.|\)|;|because|since|matches|corresponds|gives|reads|does|"
                           r"means|—|–|-|$))", w))
    named |= {m.upper() for m in re.findall(r"\b(?:answer|it|one) is ([ab])\b", w.lower())}
    if named == {"B"}:
        raise CheckFailed("EXPLAIN_ORDER: read right to left, B is indeed yaw first — but then the roll is about the "
                          "WORLD east axis (fixed axes), not about the new nose, which points north after the yaw. Read "
                          "left to right (moving axes), B is roll first. Which product starts with the yaw on the LEFT?")
    if not named:
        raise CheckFailed("EXPLAIN_ORDER: say clearly which one it is, e.g. \"A is …\" or \"B is …\"")
    explained("EXPLAIN_ORDER", why,
              ((r"new", r"mov", r"body", r"own", r"intrinsic", r"left to right", r"right to left", r"fixed",
                r"world", r"extrinsic"), "the two ways of reading the product (moving or fixed axes)"),
              ((r"not the same", r"different", r"differ", r"order", r"commut", r"swap"),
               "whether A and B are the same attitude"))


@c.test("Step 3: gimbal lock — prediction, the two numbers and the explanation",
        hint="LOCK_UP_YAW_DEG: your matrix_to_euler_zyx on euler_zyx_to_matrix(radians(30), −π/2, radians(50)), in "
             "degrees. NEAR_LOCK_YAW_JUMP_DEG: the yaw after − before in run_rotations.py gimbal. EXPLAIN_LOCK: the "
             "axes that line up, and Apollo's answer (mission brief).")
def _():
    pred, a, b, why = answers("PREDICT_LOCK", "LOCK_UP_YAW_DEG", "NEAR_LOCK_YAW_JUMP_DEG", "EXPLAIN_LOCK")
    predicted("PREDICT_LOCK", pred)
    x = number(a, "LOCK_UP_YAW_DEG")
    if abs(x - 20.0) < 0.1:
        raise CheckFailed("LOCK_UP_YAW_DEG is 20: that is ψ − φ, the rule at pitch +90°. At −90° (nose up) the "
                          "surviving angle is different — run your function on this case")
    if abs(x - 50.0) < 0.1:
        raise CheckFailed("LOCK_UP_YAW_DEG is 50: your matrix_to_euler_zyx has no lock test, so it returns rounding "
                          "noise — add the lock guard (Step 3, hints 3–4)")
    c.near(x, LOCK_UP_YAW, 0.05, "LOCK_UP_YAW_DEG (degrees)")
    c.near(number(b, "NEAR_LOCK_YAW_JUMP_DEG"), NEAR_LOCK_JUMP, 0.05, "NEAR_LOCK_YAW_JUMP_DEG (degrees)")
    explained("EXPLAIN_LOCK", why, ((r"axis", r"axes", r"align", r"line up", r"same", r"coincid", r"parallel"),
                                    "which axes line up"),
              ((r"degree of freedom", r"lost", r"lose", r"one angle", r"cannot", r"can't", r"undefined", r"separat",
                r"only", r"combin"), "what is lost"),
              ((r"apollo", r"avoid", r"steer", r"around", r"warn", r"fourth", r"realign", r"star"),
               "what Apollo did about it"))


# ======================================================================== session 2 — Quaternion detective
@c.test("TODOs 5–6: q_mul() and q_conj() in ROS order (x, y, z, w), on unseen quaternions (oracle: SciPy)",
        hint="Lesson §4: vector = p_w·q_v + q_w·p_v + p_v × q_v, scalar = p_w·q_w − p_v·q_v, returned as (x, y, z, w). "
             "q_conj negates x, y, z and keeps w.")
def _():
    Rotation, _ = oracle()
    mul, conj = functions("q_mul", "q_conj")
    A = Rotation.random(4, random_state=1601)
    B = Rotation.random(4, random_state=1602)
    for i in range(4):
        p, q = A[i].as_quat(), B[i].as_quat()
        got = vec(go(mul, p, q), 4, "q_mul")
        if qd(got, (B[i] * A[i]).as_quat()) < 1e-9:
            raise CheckFailed("q_mul(p, q) returns q ⊗ p: the cross product must be p_v × q_v (p first)")
        ref_w = (A[i] * B[i]).as_quat()
        if np.abs(got - np.append(ref_w[3], ref_w[:3])).max() < 1e-9:
            raise CheckFailed("q_mul returns w FIRST: the result must be (x, y, z, w)")
        wf = (Rotation.from_quat(np.roll(p, -1)) * Rotation.from_quat(np.roll(q, -1))).as_quat()
        if qd(got, wf) < 1e-9:
            raise CheckFailed("q_mul reads its inputs as (w, x, y, z): in ROS order w is LAST — unpack as x, y, z, w = p")
        c.ok(np.abs(got - ref_w).max() < 1e-9, f"q_mul on an unseen pair gives {np.round(got, 4).tolist()}, "
                                                f"not the Hamilton product (x, y, z, w)")
    got = vec(go(mul, (0.0, 0.0, 0.0, 2.0), (1.0, 2.0, 3.0, 4.0)), 4, "q_mul")
    c.ok(np.allclose(got, [2, 4, 6, 8]), "q_mul((0, 0, 0, 2), q) must be 2·q: a scalar times a quaternion")
    cj = vec(go(conj, (0.3, -0.1, 0.5, -0.8)), 4, "q_conj")
    if np.allclose(cj, [0.3, -0.1, 0.5, 0.8]) or np.allclose(cj, [-0.3, 0.1, -0.5, 0.8]):
        raise CheckFailed("q_conj changed w: the conjugate keeps w and negates only x, y, z")
    c.ok(np.allclose(cj, [-0.3, 0.1, -0.5, -0.8]), f"q_conj((0.3, −0.1, 0.5, −0.8)) gives {cj.tolist()}")


@c.test("TODOs 7–8: q_from_axis_angle() and q_rotate() on unseen axes, angles and vectors (oracle: SciPy)",
        hint="Lesson §4: q = (u·sin(α/2), cos(α/2)) with u the axis divided by its length; v' = q ⊗ (v, 0) ⊗ q*, keep "
             "the first three numbers. A zero axis → raise ValueError.")
def _():
    Rotation, _ = oracle()
    aa, rv = functions("q_from_axis_angle", "q_rotate")
    for axis, ang in (((1.0, -2.0, 0.5), 0.8), ((0.0, 3.0, 0.0), -2.5), ((-1.0, 1.0, 1.0), 3.0)):
        got = vec(go(aa, axis, ang), 4, f"q_from_axis_angle({axis}, {ang})")
        u = np.array(axis) / np.linalg.norm(axis)
        want = Rotation.from_rotvec(u * ang).as_quat()
        if qd(got, np.append(u * math.sin(ang), math.cos(ang))) < 1e-9:
            raise CheckFailed("q_from_axis_angle used the FULL angle: a quaternion holds sin(α/2) and cos(α/2)")
        if qd(got, np.append(np.array(axis) * math.sin(ang / 2), math.cos(ang / 2))) < 1e-9:
            raise CheckFailed(f"the axis {axis} was not normalised: divide it by its length first")
        if qd(got, np.append(want[3], want[:3])) < 1e-9:
            raise CheckFailed("q_from_axis_angle returns w FIRST: the result must be (x, y, z, w)")
        c.ok(qd(got, want) < 1e-9, f"q_from_axis_angle({axis}, {ang}) gives {np.round(got, 4).tolist()}")
    try:
        aa((0.0, 0.0, 0.0), 1.0)
    except ValueError:
        pass
    except Exception as e:
        raise CheckFailed(f"with a zero axis it should raise ValueError, it raised {type(e).__name__}: {e}")
    else:
        raise CheckFailed("with a zero axis (0, 0, 0) it should raise ValueError (the docstring says so)")
    R = Rotation.random(3, random_state=1603)
    for i, v in enumerate(((1.0, 2.0, -0.5), (-3.0, 0.2, 4.0), (0.0, 0.0, 1.0))):
        got = vec(go(rv, R[i].as_quat(), v), 3, "q_rotate")
        if np.abs(got - R[i].inv().apply(v)).max() < 1e-9:
            raise CheckFailed("q_rotate turns the vector the WRONG way: q ⊗ v ⊗ q*, not q* ⊗ v ⊗ q")
        c.ok(np.abs(got - R[i].apply(v)).max() < 1e-9,
             f"q_rotate on an unseen case gives {np.round(got, 4).tolist()} — if the TODO 5 check fails, fix q_mul "
             "first: q_rotate uses it")


@c.test("TODO 9: q_to_matrix() on unseen quaternions, including one that is not of length 1 (oracle: SciPy)",
        hint="Lesson §4: normalise q first (q_normalize is given), then the 3 × 3 formula. Compare the signs of the "
             "2·w·… terms one by one: a sign error gives the transpose (the inverse rotation).")
def _():
    Rotation, _ = oracle()
    (f,) = functions("q_to_matrix")
    R = Rotation.random(3, random_state=1604)
    for i in range(3):
        q = R[i].as_quat()
        m = mat(go(f, q), "q_to_matrix")
        if np.allclose(m, R[i].as_matrix().T, atol=1e-9):
            raise CheckFailed("q_to_matrix returns the TRANSPOSE (the inverse rotation): check the signs of the w terms")
        if not np.allclose(m @ m.T, np.eye(3), atol=1e-6):
            raise CheckFailed("q_to_matrix on an unseen quaternion is not a rotation (R·Rᵀ ≠ I): one of the 2·(…) terms has "
                              "a wrong sign or letter — compare the nine entries with lesson §4 one by one")
        c.ok(np.allclose(m, R[i].as_matrix(), atol=1e-9), "q_to_matrix on an unseen quaternion is not its matrix")
    q = 2.5 * R[0].as_quat()
    m = mat(go(f, q), "q_to_matrix of a quaternion of length 2.5")
    c.ok(np.allclose(m, R[0].as_matrix(), atol=1e-9), "a quaternion of length 2.5 must give the same rotation: "
                                                      "normalise q first")


@c.test("TODOs 10–11: slerp() and q_angle_deg() on unseen attitudes — constant rate, shortest way, q = −q",
        hint="Lesson §5: d = q0·q1; if d < 0 use −q1 and −d; if d > 0.9995 normalised linear; else "
             "[sin((1−t)Θ)q0 + sin(tΘ)q1]/sin Θ with Θ = acos d. Angle = 2·acos(|q0·q1|) in degrees, clamped.")
def _():
    Rotation, Slerp = oracle()
    sl, ang = functions("slerp", "q_angle_deg")
    A = Rotation.random(3, random_state=1605)
    B = Rotation.random(3, random_state=1606)
    for i, t in enumerate((0.2, 0.55, 0.9)):
        q0, q1 = A[i].as_quat(), B[i].as_quat()
        want = Slerp([0.0, 1.0], Rotation.concatenate([A[i], B[i]]))(t).as_quat()
        for sign in (1.0, -1.0):
            got = vec(go(sl, q0, sign * q1, t), 4, "slerp")
            if abs(np.linalg.norm(got) - 1.0) > 1e-9:
                raise CheckFailed(f"slerp returns a quaternion of length {np.linalg.norm(got):.4f}: normalise it")
            c.ok(qd(got, want) < 1e-9, "slerp on an unseen pair is not the constant-rate, shortest-way interpolation"
                 + (" (it fails when q1 is given as −q1: use −q1 when q0·q1 < 0)" if sign < 0 else ""))
    q0 = Rotation.from_euler("z", 0.3).as_quat()
    q1 = Rotation.from_euler("z", 0.31).as_quat()
    got = vec(go(sl, q0, q1, 0.5), 4, "slerp of two almost equal attitudes")
    c.ok(np.all(np.isfinite(got)) and qd(got, Rotation.from_euler("z", 0.305).as_quat()) < 1e-6,
         "slerp of two attitudes 0.6° apart must return a finite unit quaternion half-way (lesson §5: the "
         "d > 0.9995 case)")
    for i in range(3):
        q0, q1 = A[i].as_quat(), B[i].as_quat()
        want = math.degrees((A[i].inv() * B[i]).magnitude())
        got = num(go(ang, q0, q1), "q_angle_deg")
        if abs(got - want / 2) < 1e-6:
            raise CheckFailed("q_angle_deg gives half the angle: the rotation angle is 2·acos(|q0·q1|)")
        if abs(got - math.radians(want)) < 1e-6:
            raise CheckFailed("q_angle_deg returns radians: convert to degrees")
        if abs(got - (360.0 - want)) < 1e-6:
            raise CheckFailed(f"q_angle_deg gives {got:.2f}° instead of {want:.2f}°: q and −q are the same attitude — "
                              "use the absolute value of the dot product, 2·acos(|q0·q1|)")
        c.ok(abs(got - want) < 1e-6, f"q_angle_deg on an unseen pair gives {got:.4f}°")
        neg = num(go(ang, q0, -q1), "q_angle_deg")
        c.ok(abs(neg - want) < 1e-6, f"q_angle_deg(q0, −q1) gives {neg:.4f}° instead of {got:.4f}°: q and −q are the "
                                     "same attitude — use the absolute value of the dot product")
    qr = (0.0, 0.0, 0.5000000001, 0.8660254039)          # q · q = 1.0000000003 by rounding
    same = num(go(ang, qr, qr), "q_angle_deg of a quaternion with itself")
    c.ok(math.isfinite(same) and abs(same) < 1e-3, "q_angle_deg(q, q) must be 0 (clamp the dot product to at most 1 "
                                                   "before acos: rounding can give 1.0000000002)")


@c.test("Steps 5–6: the ROS pose, a full turn, and linear vs slerp — numbers, prediction and explanation",
        hint="Step 5: python3 run_rotations.py pose -0.1245 0.0134 -0.8834 0.4516 prints pitch_up and heading. Q360_W: "
             "cos(2π/2). Step 6: python3 run_rotations.py slerp, row t = 0.2: slerp − linear.")
def _():
    p, h, w, pred, e, why = answers("POSE_PITCH_UP_DEG", "POSE_HEADING_DEG", "Q360_W", "PREDICT_LERP", "LERP_ERR_DEG",
                                    "EXPLAIN_SLERP")
    p = number(p, "POSE_PITCH_UP_DEG")
    if abs(p + POSE[0]) < 0.1:
        raise CheckFailed("POSE_PITCH_UP_DEG has the wrong sign: write the pilot's pitch_up, positive nose UP, as "
                          "rpy_human prints it")
    c.near(p, POSE[0], 0.1, "POSE_PITCH_UP_DEG (degrees)")
    h = number(h, "POSE_HEADING_DEG")
    if abs(h - (90.0 - POSE[1]) % 360) < 0.2:
        raise CheckFailed("POSE_HEADING_DEG looks like the ENU yaw: the heading is (90° − yaw) mod 360")
    c.near(h, POSE[1], 0.1, "POSE_HEADING_DEG (degrees)")
    w = number(w, "Q360_W")
    if abs(w - 1.0) < 1e-6:
        raise CheckFailed("Q360_W = +1: a quaternion holds HALF the angle, cos(2π / 2) = cos π")
    c.near(w, -1.0, 1e-6, "Q360_W")
    predicted("PREDICT_LERP", pred)
    e = number(e, "LERP_ERR_DEG")
    if abs(e + LERP_ERR) < 0.02:
        raise CheckFailed("LERP_ERR_DEG has the wrong sign: slerp heading − linear heading")
    c.near(e, LERP_ERR, 0.02, "LERP_ERR_DEG (degrees)")
    explained("EXPLAIN_SLERP", why, ((r"chord", r"straight", r"short", r"length", r"norm", r"inside", r"cut"),
                                     "the chord / the length below 1"),
              ((r"middle", r"centre", r"center", r"end", r"faster", r"slower", r"not constant", r"uneven", r"speed",
                r"rate", r"angle"), "where it turns faster or slower"))


@c.test("Step 7: the oracle — explanation",
        hint="Independent code (written and tested by other people) and many random cases, against your own "
             "examples; the conventions: SciPy's (x, y, z, w) order and its 'ZYX' with the yaw first.")
def _():
    (why,) = answers("EXPLAIN_ORACLE")
    explained("EXPLAIN_ORACLE", why, ((r"independent", r"other people", r"someone else", r"not mine", r"not my own",
                                       r"different code", r"library", r"scipy", r"third"), "why an independent oracle"),
              ((r"random", r"500", r"many", r"cases", r"unseen", r"bias", r"same mistake", r"interpret"),
               "why many unseen cases are stronger than your own examples"),
              ((r"yaw first", r"order", r"zyx", r"x, ?y, ?z, ?w", r"scalar", r"w last", r"convention"),
               "which convention was translated"))


@c.test("Step 8: the detective — misread() and tilt_deg() on unseen inputs, the numbers and the symptoms",
        hint="TODO A: the script believed the four numbers were (w, x, y, z): return (x, y, z, w) of THAT reading. "
             "EXPLAIN_DETECTIVE: the cause, what looks wrong, what does not, and why line 5's sign change is harmless. "
             "TODO B: acos of the up component of q_rotate(q, (0, 0, 1)), clamped, in degrees. Then python3 detective.py.")
def _():
    Rotation, _ = oracle()
    with contextlib.redirect_stdout(io.StringIO()):
        d = load_student("detective.py", fresh=True)
    mis, tilt = need(d, "misread", "tilt_deg")
    for f in (mis, tilt):
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (detective.py, TODO {'A' if f is mis else 'B'})")
    q = (0.11, -0.52, 0.31, 0.78)
    got = vec(go(mis, q), 4, "misread")
    if np.allclose(got, [0.78, 0.11, -0.52, 0.31]):
        raise CheckFailed("misread shifts the numbers the wrong way: the script took the FIRST number as w, so in our "
                          "order its quaternion is (2nd, 3rd, 4th, 1st)")
    c.ok(np.allclose(got, [-0.52, 0.31, 0.78, 0.11]), f"misread((0.11, −0.52, 0.31, 0.78)) gives {got.tolist()}")
    for roll, pitch, yaw in ((0.3, -0.2, 2.0), (2.9, 0.1, -1.0), (0.0, 0.0, 0.7)):
        r = Rotation.from_euler("ZYX", [yaw, pitch, roll])
        want = math.degrees(math.acos(max(-1.0, min(1.0, r.as_matrix()[2, 2]))))
        got = num(go(tilt, r.as_quat()), "tilt_deg")
        if abs(got - math.radians(want)) < 1e-6 and want > 1:
            raise CheckFailed("tilt_deg returns radians: convert to degrees")
        c.ok(abs(got - want) < 1e-6, f"tilt_deg on an unseen attitude gives {got:.3f}° — the angle between the body's "
                                     "up axis and the world's up")
    lvl = num(go(tilt, (0.0, 0.0, 0.0, 1.0)), "tilt_deg of a level attitude")
    c.ok(abs(lvl) < 1e-6, "tilt_deg of a level attitude must be 0 (clamp before acos)")
    sus, a, b, m, ft, why = answers("PREDICT_SUSPECT", "PAD_HEADING_DEG", "COLLEAGUE_PAD_ROLL_DEG",
                                    "COLLEAGUE_MAX_TILT_DEG", "FLIP_T_S", "EXPLAIN_DETECTIVE")
    predicted("PREDICT_SUSPECT", sus)
    a = number(a, "PAD_HEADING_DEG")
    if abs(a - 270.0) < 0.5:
        raise CheckFailed("PAD_HEADING_DEG = 270 is the colleague's reading: write the TRUE heading (read as x, y, z, w)")
    if abs(a - 60.0) < 0.5:
        raise CheckFailed("PAD_HEADING_DEG = 60 looks like the ENU yaw: the heading is (90° − yaw) mod 360")
    c.near(a, PAD_HEADING, 0.2, "PAD_HEADING_DEG (degrees)")
    c.near(number(b, "COLLEAGUE_PAD_ROLL_DEG"), PAD_ROLL, 0.2, "COLLEAGUE_PAD_ROLL_DEG (degrees)")
    c.near(number(m, "COLLEAGUE_MAX_TILT_DEG"), MAX_TILT, 0.2, "COLLEAGUE_MAX_TILT_DEG (degrees)")
    ft = number(ft, "FLIP_T_S")
    c.ok(abs(ft - FLIP_T) < 0.05 or abs(ft - (FLIP_T + 0.1)) < 0.05, f"FLIP_T_S = {ft}: read line 5 of detective.py")
    explained("EXPLAIN_DETECTIVE", why,
              ((r"\bw\b", r"order", r"first", r"last", r"scalar", r"swap", r"misread"), "the cause (the order of w)"),
              ((r"roll", r"tilt", r"upside", r"heading", r"pad", r"level"), "what looks wrong"),
              ((r"length", r"norm", r"unit", r"rate", r"between samples", r"consecutive", r"step", r"no error",
                r"dot"), "which checks do not see it (length, rotation between samples)"),
              ((r"sign", r"−q", r"-q", r"same attitude", r"negat", r"opposite"),
               "why the sign change of line 5 is not a bug"),
              min_words=25)


@c.test("Step 9: the bug memo in report.md",
        hint="Keep the three headings; 150–350 words in your own words; quote the true pad heading (30°) and the "
             "colleague's pad roll or largest tilt, in degrees.")
def _():
    try:
        text = open("report.md", encoding="utf-8").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for h in ("## What the colleague saw", "## The cause", "## How to catch it next time"):
        c.ok(h in body, f"report.md must keep the heading '{h}'")
    words = re.findall(r"[A-Za-zÀ-ÿ0-9°'.-]+", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok(len(words) >= 150, f"report.md has {len(words)} words: write at least 150")
    c.ok(len(words) <= 420, f"report.md has {len(words)} words: a memo is short — aim for 350 (the limit is 420)")
    low = body.lower()
    c.ok(re.search(r"\b30(\.0)?\s*°|\b30(\.0)?\s*deg", low) is not None, "quote the true pad heading (30°) with its unit")
    c.ok(re.search(r"\b(60|174)(\.0)?\s*°|\b(60|174)(\.0)?\s*deg", low) is not None,
         "quote the colleague's pad roll (60°) or the largest misread tilt (174°), with the unit")
    c.ok(re.search(r"\bw\b|\(x, ?y, ?z, ?w\)|scalar", low) is not None, "say what the cause was (the position of w)")


c.milestone("reader", "TODO 1", "TODO 2", "TODO 3", "TODO 4", "Step 1", "Step 2", "Step 3", label="Attitude reader")
c.milestone("detective", "TODO", "Step", label="Quaternion detective")
c.run()
