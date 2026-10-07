import json
import math
import os
import re

import numpy as np

from academy_check import Checker, load_student, need, sh

c = Checker()
LOG = "/data/academy/16-imu/imu_log.csv"
rng = np.random.default_rng(16)

# Expected values for the dataset (computed with the reference solution; tolerances allow
# small differences between correct implementations).
EXP = {"gyro_heading_error_end_deg": (-9.42, 0.35), "declination_deg": (3.348, 0.01),
       "accel_roll_max_deg": (19.3, 0.6), "true_heading_rms_deg": (1.37, 0.2),
       "no_tilt_comp_rms_deg": (4.92, 0.4), "fused_true_heading_rms_deg": (0.20, 0.05)}
WORLD = {"London": 1.213, "Reykjavik": -11.049, "Cape Town": -26.808, "Sydney": 12.827, "Singapore": 0.240}


def arr(x, shape, what):
    c.ok(x is not None, f"{what} still returns None")
    a = np.asarray(x, dtype=float)
    c.ok(a.shape == shape, f"{what} should have shape {shape}, got {a.shape}")
    return a


def Q():
    return load_student("quaternions.py")


def rand_rpy():
    return rng.uniform(-1.2, 1.2), rng.uniform(-1.2, 1.2), rng.uniform(-3.1, 3.1)


def _aa(axis, ang):
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    return np.r_[math.cos(ang / 2), math.sin(ang / 2) * a]


def _qmul(p, q):
    w = p[0] * q[0] - np.dot(p[1:], q[1:])
    v = p[0] * np.asarray(q[1:]) + q[0] * np.asarray(p[1:]) + np.cross(p[1:], q[1:])
    return np.r_[w, v]


def same_rot(qa, qb):
    return abs(abs(float(np.dot(qa, qb))) - 1.0) < 1e-9


@c.test("quaternions.py runs without errors",
        hint="Run `python3 quaternions.py` in the terminal and read the LAST line of the error.")
def _():
    code, out = sh("python3 quaternions.py", timeout=30)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])


@c.test("euler_to_matrix: a rotation (RᵀR = I, det = 1) equal to NAVERA's rpy_to_matrix",
        hint="R = Rz(yaw) @ Ry(pitch) @ Rx(roll) — the order matters, and the angles are radians.")
def _():
    from navera_common.camera_model import rpy_to_matrix
    (f,) = need(Q(), "euler_to_matrix")
    for _ in range(20):
        r, p, y = rand_rpy()
        R = arr(f(r, p, y), (3, 3), "euler_to_matrix()")
        c.ok(np.allclose(R.T @ R, np.eye(3), atol=1e-9), "RᵀR is not the identity: this is not a rotation")
        c.ok(abs(np.linalg.det(R) - 1) < 1e-9, f"det(R) = {np.linalg.det(R):.4f}, expected 1")
        c.ok(np.allclose(R, rpy_to_matrix(r, p, y), atol=1e-9),
             f"for roll={r:.2f} pitch={p:.2f} yaw={y:.2f} rad your matrix differs from NAVERA's")


@c.test("matrix_to_euler gives the angles back, and survives gimbal lock (pitch = ±90°)",
        hint="pitch = −asin(R[2,0]) with R[2,0] clamped into [−1, 1]; at gimbal lock return roll 0 and "
             "yaw = atan2(−R[0,1], R[1,1]).")
def _():
    m = Q()
    f, e2m = need(m, "matrix_to_euler", "euler_to_matrix")
    for _ in range(20):
        want = rand_rpy()
        got = f(e2m(*want))
        c.ok(got is not None and len(got) == 3, "matrix_to_euler() should return (roll, pitch, yaw)")
        for g, w, n in zip(got, want, ("roll", "pitch", "yaw")):
            c.near(g, w, 1e-6, what=f"{n} (rad) for {np.round(want, 2)}")
    for pitch in (math.pi / 2, -math.pi / 2):
        R = e2m(0.4, pitch, 0.9)
        R[2, 0] = -math.copysign(1.0 + 1e-12, pitch)       # rounding noise past ±1
        got = f(R)
        c.ok(got is not None and all(math.isfinite(float(v)) for v in got),
             "matrix_to_euler() crashed or returned NaN at gimbal lock")
        c.near(got[1], pitch, 1e-6, what="pitch at gimbal lock")
        c.ok(np.allclose(e2m(*got), e2m(0.4, pitch, 0.9), atol=1e-6),
             "at gimbal lock your (roll, pitch, yaw) do not give the same matrix back")


@c.test("quat_mul is the Hamilton product (i⊗j = k, j⊗i = −k, and 20 random products)",
        hint="(pw, pv)⊗(qw, qv) = (pw·qw − pv·qv, pw·qv + qw·pv + pv × qv). The scalar w is FIRST.")
def _():
    from imu_pkg.orientation import quat_mul as nav_mul
    (f,) = need(Q(), "quat_mul")
    i, j = np.array([0, 1.0, 0, 0]), np.array([0, 0, 1.0, 0])
    c.ok(np.allclose(arr(f(i, j), (4,), "quat_mul()"), [0, 0, 0, 1]), f"i⊗j = {f(i, j)}, expected (0, 0, 0, 1)")
    c.ok(np.allclose(f(j, i), [0, 0, 0, -1]), f"j⊗i = {f(j, i)}, expected (0, 0, 0, −1)")
    for _ in range(20):
        p, q = rng.normal(size=4), rng.normal(size=4)
        nav = nav_mul((p[1], p[2], p[3], p[0]), (q[1], q[2], q[3], q[0]))
        c.ok(np.allclose(f(p, q), [nav[3], nav[0], nav[1], nav[2]], atol=1e-9),
             "a random product differs from NAVERA's quat_mul (remember: NAVERA's order is x, y, z, w)")


@c.test("quat_from_axis_angle and quat_rotate: 90° about z turns east into north",
        hint="q = (cos(θ/2), sin(θ/2)·axis/|axis|); rotate with q ⊗ (0, v) ⊗ q*, keep the last 3 numbers.")
def _():
    m = Q()
    fa, fr = need(m, "quat_from_axis_angle", "quat_rotate")
    q = arr(fa((0, 0, 2.0), math.pi / 2), (4,), "quat_from_axis_angle()")
    c.ok(np.allclose(q, [math.sqrt(0.5), 0, 0, math.sqrt(0.5)], atol=1e-9),
         f"90° about (0, 0, 2) gives {np.round(q, 4)}, expected (0.7071, 0, 0, 0.7071) — normalise the axis")
    v = arr(fr(q, (1.0, 0.0, 0.0)), (3,), "quat_rotate()")
    c.ok(np.allclose(v, [0, 1, 0], atol=1e-9), f"(1, 0, 0) rotated gives {np.round(v, 4)}, expected (0, 1, 0)")
    for _ in range(10):
        ax, ang, vec = rng.normal(size=3), rng.uniform(-3, 3), rng.normal(size=3)
        k = ax / np.linalg.norm(ax)
        rod = (vec * math.cos(ang) + np.cross(k, vec) * math.sin(ang)
               + k * np.dot(k, vec) * (1 - math.cos(ang)))
        c.ok(np.allclose(fr(fa(ax, ang), vec), rod, atol=1e-9), "a random rotation of a vector is wrong")


@c.test("quat_to_matrix equals NAVERA's quat_to_matrix (after converting the order)",
        hint="Use the matrix of the course with w FIRST in your order; normalise q first.")
def _():
    from navera_common.camera_model import quat_to_matrix as nav_q2m
    m = Q()
    f, conv = need(m, "quat_to_matrix", "wxyz_to_xyzw")
    for _ in range(20):
        q = rng.normal(size=4)
        q *= rng.uniform(0.9, 1.1) / np.linalg.norm(q)
        R = arr(f(q), (3, 3), "quat_to_matrix()")
        c.ok(np.allclose(R, nav_q2m(conv(q)), atol=1e-9),
             f"for q = {np.round(q, 3)} your matrix differs from NAVERA's")


@c.test("slerp: endpoints, constant angular speed, shortest path, same as NAVERA's sensor_history.slerp",
        hint="If q0·q1 < 0 use −q1. θ = acos(d); weights sin((1−t)θ)/sin θ and sin(tθ)/sin θ. "
             "Normalise the result.")
def _():
    from navera_common.sensor_history import slerp as nav_slerp
    m = Q()
    f, fa = need(m, "slerp", "quat_from_axis_angle")
    q0, q1 = fa((0, 0, 1), 0.0), fa((0, 0, 1), math.radians(120))
    c.ok(np.allclose(arr(f(q0, q1, 0.0), (4,), "slerp()"), q0, atol=1e-9), "slerp(q0, q1, 0) must be q0")
    c.ok(np.allclose(f(q0, q1, 1.0), q1, atol=1e-9), "slerp(q0, q1, 1) must be q1")
    for t in (0.25, 0.5, 0.8):
        ang = math.degrees(2 * math.acos(min(1.0, abs(float(np.dot(q0, f(q0, q1, t)))))))
        c.near(ang, 120 * t, 1e-6, what=f"angle from q0 at t = {t} (deg)")
    c.ok(same_rot(f(q0, -q1, 0.5), f(q0, q1, 0.5)), "slerp to −q1 must give the same rotation as to q1 "
                                                    "(take the shortest path)")
    for _ in range(15):
        a, b, t = rng.normal(size=4), rng.normal(size=4), rng.uniform(0, 1)
        a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
        nav = nav_slerp((a[1], a[2], a[3], a[0]), (b[1], b[2], b[3], b[0]), t)
        mine = f(a, b, t)
        c.ok(same_rot(mine, [nav[3], nav[0], nav[1], nav[2]]), "a random slerp differs from NAVERA's")
    tiny = fa((1, 0, 0), 1e-7)
    out = f(q0, tiny, 0.5)
    c.ok(np.all(np.isfinite(out)), "slerp of two almost equal quaternions gave NaN (divide by sin θ ≈ 0?)")


@c.test("integrate_gyro: body rates multiply on the RIGHT (yaw 90°, then roll about the BODY x)",
        hint="q[k] = q[k−1] ⊗ dq with dq = quat_from_axis_angle(ω, |ω|·dt). Body rates → right side.")
def _():
    f, = need(load_student("imu_filters.py"), "integrate_gyro")
    fa = _aa
    t = np.arange(0, 10.001, 0.01)
    out = arr(f(t, np.tile([0.0, 0.0, 0.1], (len(t), 1)), np.array([1.0, 0, 0, 0])), (len(t), 4),
              "integrate_gyro()")
    c.ok(same_rot(out[-1], fa((0, 0, 1), 1.0)), "0.1 rad/s about z for 10 s should give a 1 rad yaw")
    q0 = fa((0, 0, 1), math.pi / 2)                     # nose north
    t = np.arange(0, 1.0001, 0.01)
    out = f(t, np.tile([math.pi / 6, 0.0, 0.0], (len(t), 1)), q0)
    want = _qmul(q0, fa((1, 0, 0), math.pi / 6))  # roll about the body x (= north)
    c.ok(same_rot(out[-1], want), "after a 30° roll about the BODY x axis the attitude is wrong "
                                  "(did you multiply dq on the left?)")
    c.near(np.linalg.norm(out[-1]), 1.0, 1e-9, what="norm of the last quaternion")


@c.test("accel_roll_pitch: level, nose down 10°, right side down 20° (ROS signs)",
        hint="roll = atan2(f_y, f_z), pitch = atan2(−f_x, √(f_y² + f_z²)); work on whole numpy arrays.")
def _():
    m = load_student("imu_filters.py")
    (f,) = need(m, "accel_roll_pitch")
    from navera_common.camera_model import rpy_to_matrix as e2m
    cases = [(0, 0), (0, 10), (20, 0), (-15, 25)]
    acc = np.array([e2m(math.radians(r), math.radians(p), 0.7).T @ [0, 0, 9.81] for r, p in cases])
    out = f(acc)
    c.ok(out is not None and len(out) == 2, "accel_roll_pitch() should return (roll_array, pitch_array)")
    roll, pitch = np.degrees(np.asarray(out[0], float)), np.degrees(np.asarray(out[1], float))
    for k, (r, p) in enumerate(cases):
        c.near(roll[k], r, 1e-6, what=f"roll for true roll {r}°, pitch {p}°")
        c.near(pitch[k], p, 1e-6, what=f"pitch for true roll {r}°, pitch {p}° (nose down is POSITIVE)")


@c.test("complementary_tilt on the log: RMS errors as expected for tau = 1 s and tau = 30 s",
        hint="Predict with the Euler-angle kinematics (gyro of sample k−1), then blend: "
             "alpha·prediction + (1 − alpha)·accelerometer, alpha = tau/(tau + dt). Angles in RADIANS.")
def _():
    m = load_student("imu_filters.py")
    f, load = need(m, "complementary_tilt", "load_log")
    L = load(LOG)
    t = L["t_s"]
    g = np.stack([L["gx"], L["gy"], L["gz"]], 1)
    a = np.stack([L["ax"], L["ay"], L["az"]], 1)
    out = f(t, g, a, 1.0)
    c.ok(out is not None and len(out) == 2, "complementary_tilt() should return (roll_array, pitch_array)")
    er = math.sqrt(np.mean((np.degrees(out[0]) - L["true_roll_deg"]) ** 2))
    ep = math.sqrt(np.mean((np.degrees(out[1]) - L["true_pitch_deg"]) ** 2))
    c.near(er, 4.23, 0.2, what="roll RMS error (deg) with tau = 1 s")
    c.near(ep, 1.84, 0.2, what="pitch RMS error (deg) with tau = 1 s")
    out30 = f(t, g, a, 30.0)
    er30 = math.sqrt(np.mean((np.degrees(out30[0]) - L["true_roll_deg"]) ** 2))
    c.near(er30, 0.53, 0.15, what="roll RMS error (deg) with tau = 30 s")


@c.test("mag_heading is tilt-compensated (field of Monastir, drone tilted 15°/−10°, 8 headings)",
        hint="m_h = Ry(pitch) @ Rx(roll) @ m_body, then atan2(m_h[1], m_h[0]) in degrees, % 360.")
def _():
    m = load_student("imu_filters.py")
    (f,) = need(m, "mag_heading")
    from navera_common.camera_model import rpy_to_matrix as e2m
    m_enu = np.array([1.650, 28.202, -34.298])          # WMM near Monastir, microtesla (E, N, U)
    D = math.degrees(math.atan2(m_enu[0], m_enu[1]))
    heads = np.arange(0, 360, 45.0)
    r, p = math.radians(15), math.radians(-10)
    mags = np.array([e2m(r, p, math.radians(90 - h)).T @ m_enu for h in heads])
    out = f(mags, np.full(len(heads), r), np.full(len(heads), p))
    c.ok(out is not None, "mag_heading() still returns None")
    out = np.asarray(out, float)
    c.ok(out.shape == (len(heads),), f"mag_heading() should return one heading per sample, got {out.shape}")
    for h, got in zip(heads, out):
        c.ok(0 <= got < 360, f"heading {got:.2f} is not in [0, 360)")
        d = (got - (h - D) + 180) % 360 - 180
        c.ok(abs(d) < 1e-6, f"true heading {h:.0f}° (magnetic {(h - D) % 360:.2f}°): you give {got:.2f}°")


@c.test("declination_at matches the World Magnetic Model in Cape Town, Sydney and Sousse",
        hint="Two lines, as in NAVERA's class Declination: GeoMag().calculate(glat=…, glon=…, alt=0, time=year).d")
def _():
    (f,) = need(load_student("imu_filters.py"), "declination_at")
    for lat, lon, year, want in ((-33.925, 18.424, 2026.79, -26.808), (-33.869, 151.209, 2026.79, 12.827),
                                 (35.8256, 10.636, 2026.75, 3.333)):
        got = f(lat, lon, year)
        c.ok(got is not None, "declination_at() still returns None")
        c.near(got, want, 0.01, what=f"declination_at({lat}, {lon}, {year})")


@c.test("imu_filters.py runs and writes results.json and attitude.png with the right numbers",
        hint="Run `python3 imu_filters.py`; it must reach 'saved results.json'. A wrong number here "
             "points to the TODO that produced it.")
def _():
    for fn in ("results.json", "attitude.png"):
        if os.path.exists(fn):
            os.remove(fn)
    code, out = sh("python3 imu_filters.py", timeout=100)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])
    c.file_exists("results.json")
    c.file_exists("attitude.png")
    with open("results.json") as fh:
        res = json.load(fh)
    for k, (want, tol) in EXP.items():
        c.ok(k in res, f"results.json has no '{k}' (did the program stop early?)")
        c.near(res[k], want, tol, what=f"results.json {k}")
    c.eq(float(res.get("best_tau_s", -1)), 30.0, what="best_tau_s")
    for k, want in WORLD.items():
        c.near(res.get("world_declination_deg", {}).get(k), want, 0.01, what=f"declination in {k}")


def sections():
    c.file_exists("report.md")
    text = open("report.md").read()
    parts = re.split(r"^##\s+", text, flags=re.M)
    out = {}
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        out[title.strip()[:1]] = body
    return text, out


def numbers(s):
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", s.replace("−", "-"))]


def has_near(s, want, tol):
    return any(abs(abs(v) - abs(want)) <= tol for v in numbers(s))


@c.test("report.md: five sections written, no TODO left, at least 30 words each",
        hint="Keep the headings '## 1.' … '## 5.' and replace each TODO paragraph with your text.")
def _():
    text, sec = sections()
    c.ok("TODO" not in text, "report.md still contains 'TODO'")
    for k in "12345":
        c.ok(k in sec, f"report.md has no section '## {k}. …'")
        n = len(re.findall(r"[A-Za-z]{2,}", sec[k]))
        c.ok(n >= 30, f"section {k} has only {n} words; explain a little more (≥ 30)")


@c.test("report.md: the numbers match your results (drift, best tau, declinations, side error)",
        hint="Section 1: the 300 s heading error; 2: the best tau; 3: the declination of the log; "
             "4: London and Cape Town declinations (2 decimals) and the side error after 10 km from London (m).")
def _():
    _, sec = sections()
    for k in "1234":
        c.ok(k in sec, f"report.md has no section '## {k}. …'")
    c.ok(has_near(sec["1"], 9.42, 0.3), "section 1 does not give the gyroscope heading error after 300 s")
    c.ok(has_near(sec["1"], 9.0, 0.05), "section 1 does not give the bias × time prediction")
    c.ok(has_near(sec["2"], 30, 0.01), "section 2 does not give the best tau of the sweep")
    c.ok(has_near(sec["3"], 3.35, 0.02), "section 3 does not give the declination at the log's place")
    c.ok(has_near(sec["4"], 1.21, 0.011), "section 4 does not give the declination in London")
    c.ok(has_near(sec["4"], 26.81, 0.011), "section 4 does not give the declination in Cape Town")
    c.ok(has_near(sec["4"], 212, 6), "section 4 does not give the side error after 10 km from London (m)")
    s5 = sec.get("5", "")
    c.ok("sensor_history" in s5 or "camera_model" in s5,
         "section 5 should name the NAVERA files/functions (camera_model, sensor_history)")


c.run()
