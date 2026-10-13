"""compare_oracle.py — Step 7: your rotations.py against an independent library (an "oracle").

    python3 compare_oracle.py

The oracle is scipy.spatial.transform.Rotation (SciPy, used in robotics, astronomy and computer
vision). It stores quaternions as (x, y, z, w) — the scalar LAST, as ROS does — and names Euler
sequences with letters: "ZYX" in CAPITALS means rotations about the moving (body) axes, z first,
which is ROS's R = Rz(yaw) · Ry(pitch) · Rx(roll); the angles are then given yaw FIRST.
If SciPy is missing, a few course reference values are used instead.

Your functions are called on 500 random attitudes (seeded: the same every run).
"""
import math
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

r = rk.load_student("navera_lite.rotations")
N = 500


def oracle():
    try:
        from scipy.spatial.transform import Rotation, Slerp
        return Rotation, Slerp
    except ImportError:
        return None, None


def q_dist(a, b):
    """Distance between two quaternions that ignores the sign (q and −q are the same attitude)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return min(np.abs(a - b).max(), np.abs(a + b).max())


def row(name, worst, what):
    ok = worst < 1e-9
    print(f"  {'✔' if ok else '✘'} {name:24s} largest difference {worst:9.2e}   {what}")
    return ok


def with_scipy(Rotation, Slerp):
    rng = np.random.default_rng(16)
    eul = np.column_stack([rng.uniform(-math.pi, math.pi, N), rng.uniform(-1.5, 1.5, N),
                           rng.uniform(-math.pi, math.pi, N)])            # roll, pitch (ROS), yaw
    A = Rotation.random(N, random_state=161)
    B = Rotation.random(N, random_state=162)
    V = rng.normal(size=(N, 3))
    T = rng.uniform(0, 1, N)
    worst = {k: 0.0 for k in ("euler", "back", "mul", "rotate", "matrix", "slerp", "angle", "axis")}
    for i in range(N):
        roll, pitch, yaw = eul[i]
        ref = Rotation.from_euler("ZYX", [yaw, pitch, roll])               # yaw FIRST for scipy
        M = rk.need_ok(r, "euler_zyx_to_matrix", roll, pitch, yaw)
        worst["euler"] = max(worst["euler"], np.abs(np.asarray(M) - ref.as_matrix()).max())
        back = rk.need_ok(r, "matrix_to_euler_zyx", ref.as_matrix())
        y2, p2, r2 = ref.as_euler("ZYX")
        worst["back"] = max(worst["back"], abs(back[0] - r2), abs(back[1] - p2), abs(back[2] - y2))
        qa, qb = A[i].as_quat(), B[i].as_quat()
        worst["mul"] = max(worst["mul"], q_dist(rk.need_ok(r, "q_mul", qa, qb), (A[i] * B[i]).as_quat()))
        worst["rotate"] = max(worst["rotate"], np.abs(np.asarray(rk.need_ok(r, "q_rotate", qa, V[i]))
                                                      - A[i].apply(V[i])).max())
        worst["matrix"] = max(worst["matrix"], np.abs(np.asarray(rk.need_ok(r, "q_to_matrix", qa))
                                                      - A[i].as_matrix()).max())
        s = Slerp([0.0, 1.0], Rotation.concatenate([A[i], B[i]]))(T[i]).as_quat()
        worst["slerp"] = max(worst["slerp"], q_dist(rk.need_ok(r, "slerp", qa, qb, float(T[i])), s))
        ang = math.degrees((A[i].inv() * B[i]).magnitude())
        worst["angle"] = max(worst["angle"], abs(rk.need_ok(r, "q_angle_deg", qa, qb) - ang))
        rv = V[i] * rng.uniform(0.1, 3.0) / np.linalg.norm(V[i])
        worst["axis"] = max(worst["axis"], q_dist(rk.need_ok(r, "q_from_axis_angle", V[i], float(np.linalg.norm(rv))),
                                                  Rotation.from_rotvec(V[i] / np.linalg.norm(V[i])
                                                                       * np.linalg.norm(rv)).as_quat()))
    print(f"Your functions against scipy.spatial.transform.Rotation, {N} random cases each:\n")
    good = [row("euler_zyx_to_matrix", worst["euler"], 'Rotation.from_euler("ZYX", [yaw, pitch, roll])'),
            row("matrix_to_euler_zyx", worst["back"], 'Rotation.as_euler("ZYX") → (yaw, pitch, roll)'),
            row("q_from_axis_angle", worst["axis"], "Rotation.from_rotvec(axis · angle)"),
            row("q_mul", worst["mul"], "A * B"),
            row("q_rotate", worst["rotate"], "A.apply(v)"),
            row("q_to_matrix", worst["matrix"], "A.as_matrix()"),
            row("slerp", worst["slerp"], "scipy's Slerp"),
            row("q_angle_deg", worst["angle"], "(A⁻¹ · B).magnitude(), in degrees")]
    biggest = max(worst.values())
    print(f"\nlargest difference of all: {biggest:.2e}")
    if all(good):
        print("Your functions agree with the oracle to rounding (about 1e-15 is the size of float rounding).")
    else:
        print("✘ lines: your function is wrong on some attitudes. If python3 run_rotations.py test is all ✔, it is right "
              "on the easy examples only:\nread the lab's Stuck? box of that TODO and compare your formula with the "
              "lesson term by term.")
    print("\nThe gimbal lock, as the oracle sees it (ROS pitch exactly 90°, roll 25°, yaw 70°):")
    import warnings
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        y, p, rr = Rotation.from_euler("ZYX", [math.radians(70), math.pi / 2, math.radians(25)]).as_euler("ZYX",
                                                                                                         degrees=True)
    print(f"  scipy as_euler: yaw {y:.1f}°, pitch {p:.1f}°, roll {rr:.1f}°")
    for w in caught:
        print(f"  scipy warns: {w.message}")
    mine = rk.need_ok(r, "matrix_to_euler_zyx",
                      Rotation.from_euler("ZYX", [math.radians(70), math.pi / 2, math.radians(25)]).as_matrix())
    print(f"  yours:          yaw {math.degrees(mine[2]):.1f}°, pitch {math.degrees(mine[1]):.1f}°, "
          f"roll {math.degrees(mine[0]):.1f}°, locked={mine[3]}")


def without_scipy():
    print("SciPy is not installed here: comparing with course reference values instead.\n")
    refs = [("euler_zyx_to_matrix(0.4, -0.3, 1.9)[0]", lambda: r.euler_zyx_to_matrix(0.4, -0.3, 1.9)[0],
             [-0.30885032, -0.83439562, 0.45650349]),
            ("q_mul(...)", lambda: r.q_mul((0.1, 0.7, -0.1, 0.7), (0.5, -0.5, 0.5, 0.5)),
             [0.7, -0.1, -0.1, 0.7]),
            ("q_rotate(...)", lambda: r.q_rotate((0.5, 0.5, 0.5, 0.5), (1.0, 2.0, 3.0)), [3.0, 1.0, 2.0])]
    for name, fn, want in refs:
        try:
            got = np.asarray(fn(), dtype=float)
            print(f"  {'✔' if np.allclose(got, want, atol=1e-6) else '✘'} {name:40s} {np.round(got, 6).tolist()}")
        except Exception as e:
            print(f"  ✘ {name:40s} {type(e).__name__}: {e}")


if __name__ == "__main__":
    Rotation, Slerp = oracle()
    if Rotation is None:
        without_scipy()
        sys.exit(0)
    with_scipy(Rotation, Slerp)
