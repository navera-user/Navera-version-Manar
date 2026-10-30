"""run_rotations.py — runs YOUR functions of navera_lite/rotations.py on the lab's situations, and draws them.

    python3 run_rotations.py test       check each function on its docstring example (and a few traps)
    python3 run_rotations.py pitch      which way does a positive ROS pitch move the nose?        (Step 1)
    python3 run_rotations.py order      the same two turns in two orders                          (Step 2)
    python3 run_rotations.py gimbal     gimbal lock: four attitudes, one matrix                    (Step 3)
    python3 run_rotations.py pose X Y Z W   a ROS orientation (x, y, z, w) as a pilot reads it    (Step 5)
    python3 run_rotations.py slerp      a 160° turn interpolated two ways                          (Step 6)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

r = rk.load_student("navera_lite.rotations")
D = math.radians
WORLD = ("east", "north", "up")


def arr(v, shape):
    """v as a float array of the given shape, or None."""
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return None
    return a if a.shape == shape else None


def words(v):
    """A world vector in words: (0, 0.99, 0.1) → 'north (0.00, 0.99, 0.10)'."""
    v = np.asarray(v, dtype=float)
    k = int(np.argmax(np.abs(v)))
    name = WORLD[k] if v[k] > 0 else {"east": "west", "north": "south", "up": "down"}[WORLD[k]]
    if abs(v[k]) < 0.9:
        name = "between axes"
    return f"{name:13s} ({v[0]:+.3f}, {v[1]:+.3f}, {v[2]:+.3f})"


def get(fn, *args, shape=None):
    """Call one of the student's functions; stop the scenario with a plain message if unusable."""
    v = rk.need_ok(r, fn, *args)
    if shape is not None and arr(v, shape) is None:
        sys.exit(f"{fn}() must return a numpy array of shape {shape}, but it returned {v!r}")
    return np.asarray(v, dtype=float) if shape is not None else v


def same_q(a, b, tol):
    a, b = arr(a, (4,)), arr(b, (4,))
    return a is not None and b is not None and (np.abs(a - b).max() <= tol or np.abs(a + b).max() <= tol)


# ------------------------------------------------------------------------------------------- test
def attempt(fn, name):
    """Run fn() (a call of the student's function name); (result, None) or (None, one plain sentence)."""
    import contextlib
    import io
    import traceback
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            v = fn()
    except NotImplementedError:
        return None, "a function it needs is not written yet (an earlier TODO)"
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith("rotations.py")]
        where = f" (navera_lite/rotations.py line {tb[-1].lineno}, in {tb[-1].name}())" if tb else ""
        hint = rk._hint(e)
        if "math domain error" in str(e):
            hint = " — acos/asin got a number just outside [−1, 1] (rounding): clamp it first (lesson §3)"
        return None, f"{name}() stopped with {type(e).__name__}: {e}{where}{hint}"
    if v is None:
        stubbed = [n for n in ("rot_y", "rot_z", "q_mul", "q_conj", "q_from_axis_angle", "q_to_matrix")
                   if rk.is_stub(getattr(r, n, None))]
        if stubbed and name not in stubbed:
            return None, f"it uses {stubbed[0]}(), which is not written yet"
        return None, f"{name}() returned None: every path must end with a `return`"
    return v, None


def test():
    q60 = (0.0, 0.0, 0.5, 0.866025)                       # yaw +60°
    cases = []                                            # (TODO, label, call, check(result) -> (ok, note))

    def m3(want, tol=1e-3):
        def chk(v):
            a = arr(v, (3, 3))
            if a is None:
                return False, f"expected a 3 × 3 numpy array, got {v!r}"
            return np.abs(a - np.asarray(want)).max() <= tol, None
        return chk

    def v3(want, tol=1e-3):
        def chk(v):
            a = arr(v, (3,))
            if a is None:
                return False, f"expected 3 numbers, got {v!r}"
            return np.abs(a - np.asarray(want)).max() <= tol, None
        return chk

    def q4(want, tol=1e-4, sign_free=False):
        def chk(v):
            a = arr(v, (4,))
            if a is None:
                return False, f"expected a numpy array of 4 numbers (x, y, z, w), got {v!r}"
            ok = np.abs(a - np.asarray(want)).max() <= tol or (sign_free and np.abs(a + np.asarray(want)).max() <= tol)
            return ok, None
        return chk

    def roty_chk(v):
        a = arr(v, (3, 3))
        if a is None:
            return False, f"expected a 3 × 3 numpy array, got {v!r}"
        nose = a @ [1, 0, 0]
        if abs(nose[0] - 0.866) < 1e-3 and abs(nose[2] - 0.5) < 1e-3:
            return False, ("the nose went UP: by the right-hand rule a positive rotation about +y (left) carries +z "
                           "towards +x, so +x goes DOWN. The −sin sits in row 2, column 0 (lesson §2)")
        if abs(nose[0] - math.cos(30)) < 1e-3:
            return False, "math.cos got 30 RADIANS: convert with math.radians — the call already passes radians"
        return np.allclose(nose, [0.866025, 0, -0.5], atol=1e-3) and np.allclose(a @ a.T, np.eye(3)), None

    def rotz_chk(v):
        a = arr(v, (3, 3))
        if a is None:
            return False, f"expected a 3 × 3 numpy array, got {v!r}"
        x = a @ [1, 0, 0]
        if np.allclose(x, [0.866025, -0.5, 0], atol=1e-3):
            return False, "east was carried towards SOUTH: that is the transpose — a positive yaw turns east towards north"
        return np.allclose(x, [0.866025, 0.5, 0], atol=1e-3) and np.allclose(a @ a.T, np.eye(3)), None

    def euler_chk(v):
        a = arr(v, (3, 3))
        if a is None:
            return False, f"expected a 3 × 3 numpy array, got {v!r}"
        nose = a[:, 0]
        if np.allclose(nose, [0.7399, -0.6718, -0.0335], atol=1e-3):
            return False, "wrong ORDER: you built Rx · Ry · Rz; the ZYX attitude is Rz(yaw) @ Ry(pitch) @ Rx(roll)"
        if np.allclose(nose, [0.7399, 0, 0], atol=1e-3):
            return False, "`*` multiplies element by element: multiply matrices with `@` (🧰 lesson §2)"
        if np.allclose(nose, [0.7400, -0.6209, -0.2588], atol=1e-3):
            return False, "the nose points DOWN for a negative ROS pitch: your rot_y has its sign wrong (TODO 1)"
        return np.allclose(nose, [0.7400, -0.6209, 0.2588], atol=1e-3), None

    def m2e(want_locked):
        def chk(v):
            if not (isinstance(v, (tuple, list)) and len(v) == 4):
                return False, f"expected 4 values (roll, pitch, yaw, locked), got {v!r}"
            vals = [float(x) for x in v[:3]]
            if want_locked:
                if v[3] is not True and not (v[3] == 1 and isinstance(v[3], (bool, np.bool_))):
                    return False, "at pitch 90° the 4th value `locked` must be True (|cos(pitch)| < 1e-6)"
                return (abs(vals[0]) < 1e-9 and abs(vals[1] - math.pi / 2) < 1e-6 and abs(vals[2] - 0.5) < 1e-6,
                        "at the lock: roll = 0.0, yaw = atan2(−R[0][1], R[1][1]) (lesson §4)")
            if abs(vals[0] - 0.3) < 1e-6 and abs(vals[1] - 0.2) < 1e-6:
                return False, "the pitch sign is wrong: pitch = asin(−R[2][0]) (the minus!)"
            if max(abs(x) for x in vals) > 2 * math.pi + 0.1:
                return False, "these look like DEGREES: the function returns radians"
            return (np.allclose(vals, [0.3, -0.2, 2.5], atol=1e-6) and not v[3],
                    "use atan2(R[2][1], R[2][2]) for roll and atan2(R[1][0], R[0][0]) for yaw; locked False")
        return chk

    def mul_chk(v):
        a = arr(v, (4,))
        if a is None:
            return False, f"expected a numpy array of 4 numbers, got {v!r}"
        if np.allclose(a, [-0.36, 0.48, -0.48, 0.64], atol=1e-6) or np.allclose(a, [0.36, 0.48, 0.48, 0.64], atol=1e-6):
            return False, "a cross-product term has the wrong sign: that is q ⊗ p, or p × q reversed (lesson §4)"
        if abs(a[0] - 0.64) < 1e-6 or abs(a[3] - (-0.36)) < 1e-6 or np.allclose(a, [0.48, 0.48, -0.36, -0.64]):
            return False, "w is not LAST: the inputs and the result are (x, y, z, w) — unpack as x, y, z, w = p"
        return np.allclose(a, [-0.36, 0.48, 0.48, 0.64], atol=1e-6), None

    def ij_chk(v):
        a = arr(v, (4,))
        if a is None:
            return False, f"expected a numpy array of 4 numbers, got {v!r}"
        if np.allclose(a, [0, 0, -1, 0]):
            return False, "you got j ⊗ i = −k: the cross product must be p_v × q_v, p first (lesson §4)"
        if np.allclose(a, [1, 0, 0, 0]):
            return False, "w is not LAST: (1, 0, 0, 0) is i in ROS order — unpack as x, y, z, w = p"
        return np.allclose(a, [0, 0, 1, 0]), None

    def sq_chk(v):
        a = arr(v, (4,))
        if a is None:
            return False, f"expected a numpy array of 4 numbers, got {v!r}"
        if np.allclose(a, [0, 0, 0.96, 1.0], atol=1e-4):
            return False, "w = p_w·q_w MINUS p_v·q_v (lesson §4): your scalar part adds the dot product"
        return np.allclose(a, [0, 0, 0.96, 0.28], atol=1e-4), None

    def conj_chk(v):
        a = arr(v, (4,))
        if a is not None and np.allclose(a, [0.1, -0.2, 0.3, -0.9]):
            return False, "you negated w: the conjugate keeps w and negates x, y, z"
        if a is not None and np.allclose(a, [-0.1, 0.2, -0.3, -0.9]):
            return False, "you negated w too: keep w unchanged, negate only x, y, z"
        return a is not None and np.allclose(a, [-0.1, 0.2, -0.3, 0.9]), None

    def aa_chk(v):
        a = arr(v, (4,))
        if a is None:
            return False, f"expected a numpy array of 4 numbers, got {v!r}"
        if np.allclose(a, [0, 0, 0.866025, 0.5], atol=1e-4) or np.allclose(a, [0, 0, 1.732051, 0.5], atol=1e-4):
            return False, "the FULL angle was used: a quaternion holds HALF the angle — sin(α/2), cos(α/2)"
        if np.allclose(a, [0, 0, 1.0, 0.866025], atol=1e-4):
            return False, "the axis (0, 0, 2) was not normalised: divide it by its length first"
        if np.allclose(a, [0.866025, 0, 0, 0.5], atol=1e-4) or np.allclose(a, [0.866025, 0, 0, 1.0], atol=1e-4):
            return False, "w is FIRST: the result must be (x, y, z, w), w last"
        return np.allclose(a, [0, 0, 0.5, 0.866025], atol=1e-4), None

    def rot_chk(v):
        a = arr(v, (3,))
        if a is None:
            return False, f"expected 3 numbers, got {v!r}"
        if np.allclose(a, [1, -1.732, 0], atol=1e-3):
            return False, "the vector turned the WRONG way (clockwise): q ⊗ v ⊗ q*, not q* ⊗ v ⊗ q"
        return np.allclose(a, [1, 1.732, 0], atol=1e-3), None

    def q2m_chk(v):
        a = arr(v, (3, 3))
        if a is None:
            return False, f"expected a 3 × 3 numpy array, got {v!r}"
        if np.allclose(a, [[0.5, 0.866, 0], [-0.866, 0.5, 0], [0, 0, 1]], atol=1e-3):
            return False, "this is the TRANSPOSE (the inverse rotation): the w·z terms have their signs swapped"
        return np.allclose(a, [[0.5, -0.866, 0], [0.866, 0.5, 0], [0, 0, 1]], atol=1e-3), None

    def q2m_norm_chk(v):
        a = arr(v, (3, 3))
        if a is None:
            return False, f"expected a 3 × 3 numpy array, got {v!r}"
        return (np.allclose(a @ a.T, np.eye(3), atol=1e-9),
                "q = (0, 0, 1, 1.7320508) has length 2: normalise q first (q_normalize is given)")

    def q2m_full_chk(v):
        a = arr(v, (3, 3))
        if a is None:
            return False, f"expected a 3 × 3 numpy array, got {v!r}"
        want = [[0.4981, -0.8453, 0.1933], [0.8627, 0.5055, -0.0125], [-0.0872, 0.1730, 0.9811]]
        return (np.abs(a - np.asarray(want)).max() < 2e-3,
                "one of the 2·(…) terms has a wrong sign or letter: compare each of the nine entries with lesson §4, "
                "term by term (a pure-yaw example cannot see the x and y terms)")

    def raises(f):
        try:
            f()
        except ValueError:
            return "ValueError"
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        return "no exception"

    def raise_chk(v):
        if v == "ValueError":
            return True, None
        if v == "no exception":
            return False, "a zero axis has no direction: `raise ValueError(\"…\")` when its length is 0 (docstring)"
        return False, f"it raised {v} — raise a ValueError yourself before dividing by the length"

    def slerp_chk(v):
        a = arr(v, (4,))
        if a is None:
            return False, f"expected a numpy array of 4 numbers, got {v!r}"
        return same_q(a, [0, 0, 0.707107, 0.707107], 1e-4), "half-way between no rotation and a 180° yaw: a 90° yaw"

    def short_chk(v):
        a = arr(v, (4,))
        if a is None:
            return False, f"expected a numpy array of 4 numbers, got {v!r}"
        yaw = math.degrees(2 * math.atan2(a[2], a[3]))
        yaw = (yaw + 180) % 360 - 180
        if abs(yaw - 127.5) < 1:
            return False, ("from yaw +60° to yaw −30° (given as −q1) you went the LONG way round (yaw 127.5° at a "
                           "quarter): if q0 · q1 < 0, use −q1 (lesson §5)")
        if abs(yaw - 28.08) < 0.1:
            return False, "you used −q1 but kept the negative d: when you flip q1, flip d too (b, d = -b, -d)"
        if abs(np.linalg.norm(a) - 1) > 1e-6:
            return False, f"the result has length {np.linalg.norm(a):.4f}: return a unit quaternion"
        return abs(yaw - 37.5) < 0.01, "expected a yaw of +37.5° at a quarter (the short way: 60° − 90°/4)"

    def ang_chk(want):
        def chk(v):
            try:
                x = float(v)
            except (TypeError, ValueError):
                return False, f"expected one number (degrees), got {v!r}"
            if want == 0.0 and abs(x - 360.0) < 1e-6:
                return False, "q and −q are the SAME attitude: use abs(q0 · q1) (lesson §5)"
            if abs(x - want / 2) < 0.01 and want:
                return False, "half the right angle: the angle of a rotation is 2 · acos(|q0 · q1|)"
            if abs(x - math.radians(want)) < 0.01 and want:
                return False, "radians: convert with math.degrees"
            return abs(x - want) < 0.01, None
        return chk

    cases = [
        (1, "rot_y(30°) — column 0, where the nose (1, 0, 0) goes", lambda: r.rot_y(D(30)), roty_chk),
        (2, "rot_z(30°) — column 0, where east (1, 0, 0) goes", lambda: r.rot_z(D(30)), rotz_chk),
        (3, "euler_zyx_to_matrix(0, 0, 90°)", lambda: r.euler_zyx_to_matrix(0.0, 0.0, D(90)),
         m3([[0, -1, 0], [1, 0, 0], [0, 0, 1]])),
        (3, "euler_zyx_to_matrix(20°, −15°, −40°) — column 0, the nose", lambda: r.euler_zyx_to_matrix(D(20), D(-15), D(-40)),
         euler_chk),
        (4, "matrix_to_euler_zyx(R of (0.3, −0.2, 2.5))",
         lambda: r.matrix_to_euler_zyx(r.euler_zyx_to_matrix(0.3, -0.2, 2.5)), m2e(False)),
        (4, "matrix_to_euler_zyx at pitch 90° (gimbal lock)",
         lambda: r.matrix_to_euler_zyx(r.euler_zyx_to_matrix(0.0, math.pi / 2, 0.5)), m2e(True)),
        (5, "q_mul(i, j)", lambda: r.q_mul((1, 0, 0, 0), (0, 1, 0, 0)), ij_chk),
        (5, "q_mul((0, 0, 0.6, 0.8), (0, 0.6, 0, 0.8))", lambda: r.q_mul((0.0, 0.0, 0.6, 0.8), (0.0, 0.6, 0.0, 0.8)),
         mul_chk),
        (5, "q_mul(yaw 73.7°, yaw 73.7°) — same axis, the dot product counts",
         lambda: r.q_mul((0.0, 0.0, 0.6, 0.8), (0.0, 0.0, 0.6, 0.8)), sq_chk),
        (6, "q_conj((0.1, −0.2, 0.3, 0.9))", lambda: r.q_conj((0.1, -0.2, 0.3, 0.9)), conj_chk),
        (7, "q_from_axis_angle((0, 0, 2), 60°)", lambda: r.q_from_axis_angle((0, 0, 2), D(60)), aa_chk),
        (7, "q_from_axis_angle((0, 0, 0), 1.0) must raise ValueError",
         lambda: raises(lambda: r.q_from_axis_angle((0, 0, 0), 1.0)), raise_chk),
        (8, "q_rotate(yaw 60°, (2, 0, 0))", lambda: r.q_rotate(q60, (2.0, 0.0, 0.0)), rot_chk),
        (9, "q_to_matrix(yaw 60°)", lambda: r.q_to_matrix(q60), q2m_chk),
        (9, "q_to_matrix of a quaternion of length 2", lambda: r.q_to_matrix((0.0, 0.0, 1.0, 1.7320508)), q2m_norm_chk),
        (9, "q_to_matrix of lesson §4's (0.0537, 0.0812, 0.4943, 0.8638) = §3's R",
         lambda: r.q_to_matrix((0.0537, 0.0812, 0.4943, 0.8638)), q2m_full_chk),
        (10, "slerp(no rotation, yaw 180°, 0.5)", lambda: r.slerp((0, 0, 0, 1), (0, 0, 1, 0), 0.5), slerp_chk),
        (10, "slerp the short way at t = 0.25 (q1 given as its negative)",
         lambda: r.slerp((0, 0, 0.5, 0.8660254), (0, 0, 0.2588190, -0.9659258), 0.25), short_chk),
        (11, "q_angle_deg(no rotation, yaw 30°)", lambda: r.q_angle_deg((0, 0, 0, 1), (0, 0, 0.258819, 0.965926)),
         ang_chk(30.0)),
        (11, "q_angle_deg(q, −q)", lambda: r.q_angle_deg((0, 0, 0, 1), (0, 0, 0, -1)), ang_chk(0.0)),
        (11, "q_angle_deg(q, q) when rounding makes q · q = 1.0000000003",
         lambda: r.q_angle_deg((0, 0, 0.5000000001, 0.8660254039), (0, 0, 0.5000000001, 0.8660254039)), ang_chk(0.0)),
    ]
    names = {1: "rot_y", 2: "rot_z", 3: "euler_zyx_to_matrix", 4: "matrix_to_euler_zyx", 5: "q_mul", 6: "q_conj",
             7: "q_from_axis_angle", 8: "q_rotate", 9: "q_to_matrix", 10: "slerp", 11: "q_angle_deg"}
    done, said = 0, set()
    for k, label, fn, chk in cases:
        name = names[k]
        func = getattr(r, name, None)
        if func is None:
            print(f"✘ TODO {k:2d}  {name}() does not exist in navera_lite/rotations.py — did you rename it?")
            continue
        if rk.is_stub(func):
            if k not in said:
                print(f"· TODO {k:2d}  {name}() is not written yet")
            said.add(k)
            continue
        got, err = attempt(fn, name)
        if err:
            print(f"✘ TODO {k:2d}  {label}: {err}")
            continue
        ok, note = chk(got)
        if "column 0" in label and arr(got, (3, 3)) is not None:
            shown = np.asarray(got, dtype=float)[:, 0].round(4).tolist()
        elif isinstance(got, str):
            shown = got
        elif isinstance(got, tuple):
            shown = "(" + ", ".join(repr(x) if isinstance(x, (bool, np.bool_)) else f"{float(x):.4f}" for x in got) + ")"
        else:
            shown = np.asarray(got, dtype=float).round(4).tolist() if arr(got, np.shape(got)) is not None else got
        print(f"{'✔' if ok else '✘'} TODO {k:2d}  {label}  ->  {shown}" + ("" if ok else f"\n           ({note or 'not the docstring result'})"))
        done += ok
    print(f"\n{done} of {len(cases)} examples give the expected result.")


# ------------------------------------------------------------------------------------------- scenarios
def pitch():
    print("A ROS message says pitch = +0.12 rad (roll 0, yaw 0: the nose points east).\n")
    R = get("rot_y", 0.12, shape=(3, 3))
    nose = R @ np.array([1.0, 0.0, 0.0])
    print(f"  your rot_y(0.12) @ nose  ->  {words(nose)}")
    print("  (east, north, up) — look at the sign of the 'up' component.")
    print("\nWrite PITCH_UP_DEG (the pilot's pitch, positive nose up, in degrees) in answers.py.")


def order():
    a = get("rot_z", D(90), shape=(3, 3)) @ r.rot_x(D(90))
    b = r.rot_x(D(90)) @ get("rot_z", D(90), shape=(3, 3))
    for name, M in (("A = rot_z(90°) @ rot_x(90°)", a), ("B = rot_x(90°) @ rot_z(90°)", b)):
        print(name)
        for k, axis in enumerate(("nose     ", "left wing", "top      ")):
            print(f"    {axis} -> {words(M[:, k])}")
        print()
    draw([("A = Rz(90°)·Rx(90°)", a), ("B = Rx(90°)·Rz(90°)", b)], "order.png")


def gimbal():
    print("ROS pitch +90° (nose straight DOWN), four different (roll, yaw) pairs:\n")
    pairs = [(25, 70), (0, 45), (-20, 25), (40, 85)]
    mats = []
    for roll, yaw in pairs:
        M = get("euler_zyx_to_matrix", D(roll), D(90), D(yaw), shape=(3, 3))
        mats.append(M)
        out = rk.need_ok(r, "matrix_to_euler_zyx", M)
        back = f"({math.degrees(out[0]):6.1f}°, {math.degrees(out[1]):5.1f}°, {math.degrees(out[2]):6.1f}°, locked={out[3]})"
        print(f"  roll {roll:4d}°, yaw {yaw:3d}°   row 0 of R = {np.round(M[0], 4).tolist()}   your matrix_to_euler_zyx -> {back}")
    worst = max(np.abs(m - mats[0]).max() for m in mats)
    print(f"\n  largest difference between the four matrices: {worst:.1e}")
    print("\nNear the lock: ROS pitch 89.5°, roll 0°, yaw 0°, then the vehicle turns by just 1° about the world EAST axis.")
    M0 = get("euler_zyx_to_matrix", 0.0, D(89.5), 0.0, shape=(3, 3))
    rot_east = np.array([[1, 0, 0], [0, math.cos(D(1)), -math.sin(D(1))], [0, math.sin(D(1)), math.cos(D(1))]])
    M1 = rot_east @ M0
    for name, M in (("before", M0), ("after ", M1)):
        out = rk.need_ok(r, "matrix_to_euler_zyx", M)
        print(f"  {name}: roll {math.degrees(out[0]):8.2f}°   pitch {math.degrees(out[1]):7.2f}°   "
              f"yaw {math.degrees(out[2]):8.2f}°   locked={out[3]}")
    print("\nWrite NEAR_LOCK_YAW_JUMP_DEG (how much the yaw changed, in degrees) in answers.py.")


def pose(args):
    if len(args) != 4:
        sys.exit("usage: python3 run_rotations.py pose X Y Z W   (the four numbers of the ROS orientation)")
    try:
        q = np.array([float(a) for a in args])
    except ValueError:
        sys.exit(f"the four numbers must be numbers, got {args}")
    print(f"ROS orientation (x, y, z, w) = {q.tolist()}   length {np.linalg.norm(q):.6f}\n")
    M = get("q_to_matrix", q, shape=(3, 3))
    for k, axis in enumerate(("nose     ", "left wing", "top      ")):
        print(f"    {axis} -> {words(M[:, k])}")
    roll, pitch_up, heading = rk.need_ok(r, "rpy_human", q, n=3)
    print(f"\n  rpy_human (uses your q_to_matrix and matrix_to_euler_zyx): roll {roll:.2f}°  "
          f"pitch_up {pitch_up:.2f}°  heading {heading:.2f}°")
    draw([("this attitude", M)], "pose.png")


def slerp():
    h0, h1 = 10.0, 170.0
    q0 = get("q_from_axis_angle", (0, 0, 1), D(90 - h0), shape=(4,))
    q1 = get("q_from_axis_angle", (0, 0, 1), D(90 - h1), shape=(4,))
    print(f"A level turn from heading {h0:.0f}° to heading {h1:.0f}° (yaw {90 - h0:.0f}° → {90 - h1:.0f}°), "
          "interpolated at 9 instants:\n")
    print("     t    slerp heading   lerp heading   lerp length before normalising")
    rows = []
    for t in np.round(np.arange(0.1, 0.91, 0.1), 1):
        qs = get("slerp", q0, q1, float(t), shape=(4,))
        raw = (1 - t) * q0 + t * q1
        ql = raw / np.linalg.norm(raw)
        hs, hl = r.heading_deg_from_q(qs), r.heading_deg_from_q(ql)
        rows.append((t, hs, hl))
        print(f"   {t:.1f}   {hs:12.2f}°   {hl:12.2f}°   {np.linalg.norm(raw):.4f}")
    plt = rk.plt_or_none()
    if plt:
        os.makedirs("out", exist_ok=True)
        fig, ax = plt.subplots(figsize=(6.4, 4))
        ts = [0] + [x[0] for x in rows] + [1]
        ax.plot([0, 1], [h0, h1], "-", color="#c5ccd3", lw=9, solid_capstyle="butt",
                label="constant turn rate (slerp lies on it)")
        ax.plot(ts, [h0] + [x[1] for x in rows] + [h1], "o-", label="slerp")
        ax.plot(ts, [h0] + [x[2] for x in rows] + [h1], "s--", label="linear, then normalised")
        ax.set_xlabel("t (fraction of the interval)")
        ax.set_ylabel("heading (°)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig("out/slerp.png", dpi=110)
        rk.saved("out/slerp.png")


# ------------------------------------------------------------------------------------------- drawing
PLANE = {  # a small aircraft in body FLU coordinates (m): lines to draw
    "fuselage": [(-4, 0, 0), (4, 0, 0)], "nose": [(4, 0, 0), (5, 0, 0)],
    "left wing": [(0.5, 0, 0), (0.5, 5, 0)], "right wing": [(0.5, 0, 0), (0.5, -5, 0)], "tail": [(-4, 1.8, 0), (-4, -1.8, 0)], "fin": [(-4, 0, 0), (-4, 0, 1.6)],
}
COLORS = {"fuselage": "#1d2733", "nose": "#d64545", "left wing": "#2e9e4f", "right wing": "#0b6e8a", "tail": "#7a8794", "fin": "#a8680d"}


def draw(items, fname):
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    views = (("from above (east →, north ↑)", 0, 1), ("from the south (east →, up ↑)", 0, 2),
             ("from the east (north →, up ↑)", 1, 2))
    fig, axs = plt.subplots(len(items), 3, figsize=(10, 3.4 * len(items)), squeeze=False)
    for row, (title, M) in enumerate(items):
        for col, (vt, i, j) in enumerate(views):
            ax = axs[row][col]
            for part, pts in PLANE.items():
                w = np.array([M @ np.array(p, dtype=float) for p in pts])
                ax.plot(w[:, i], w[:, j], color=COLORS[part], lw=3 if part != "nose" else 5)
            ax.set_xlim(-6, 6)
            ax.set_ylim(-6, 6)
            ax.set_aspect("equal")
            ax.grid(alpha=0.3)
            ax.set_title(f"{title}\n{vt}" if col == 0 else vt, fontsize=8)
    fig.suptitle("red = nose, green = LEFT wing, blue = right wing, grey = tailplane, orange = tail fin (on top)", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join("out", fname), dpi=100)
    rk.saved(os.path.join("out", fname))


MODES = {"test": test, "pitch": pitch, "order": order, "gimbal": gimbal, "slerp": slerp}

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "pose":
        pose(sys.argv[2:])
    elif len(sys.argv) == 2 and sys.argv[1] in MODES:
        MODES[sys.argv[1]]()
    else:
        print(__doc__)
        sys.exit(1)
