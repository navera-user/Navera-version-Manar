import math
import os
import random

from academy_check import Checker, load_student, need, sh

c = Checker()
LOG = "/data/academy/16-imu/imu_log.csv"


def rpy_of(fn, q):
    r = fn(q)
    c.ok(r is not None, "quat_to_euler() still returns None")
    c.ok(len(r) == 3, f"quat_to_euler() should return 3 numbers (roll, pitch, yaw), got {r!r}")
    return [float(v) for v in r]


def ang_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


@c.test("attitude.py runs without errors",
        hint="Run `python3 attitude.py` in the terminal and read the last lines of the error.")
def _():
    code, out = sh("python3 attitude.py", timeout=30)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])


@c.test("quat_to_euler: no rotation gives (0, 0, 0), a quarter turn around z gives yaw = 90",
        hint="Use the three formulas of TODO 1 and return math.degrees(...) of each, as a tuple. "
             "Getting 1.57 instead of 90? That is radians: use math.degrees.")
def _():
    (f,) = need(load_student("attitude.py"), "quat_to_euler")
    r = rpy_of(f, (0.0, 0.0, 0.0, 1.0))
    for v, n in zip(r, ("roll", "pitch", "yaw")):
        c.near(v, 0.0, 1e-6, what=n + " of (0, 0, 0, 1)")
    s = math.sqrt(0.5)
    r = rpy_of(f, (0.0, 0.0, s, s))
    c.near(r[2], 90.0, 1e-3, what="yaw of (0, 0, 0.7071, 0.7071)")
    c.near(r[0], 0.0, 1e-3, what="roll of (0, 0, 0.7071, 0.7071)")
    c.near(r[1], 0.0, 1e-3, what="pitch of (0, 0, 0.7071, 0.7071)")


@c.test("quat_to_euler gives back roll, pitch and yaw of 20 random attitudes",
        hint="Check each formula letter by letter: roll uses w·x + y·z, pitch w·y − z·x, yaw w·z + x·y.")
def _():
    from imu_pkg.orientation import quat_from_rpy
    (f,) = need(load_student("attitude.py"), "quat_to_euler")
    rnd = random.Random(16)
    for _ in range(20):
        want = (rnd.uniform(-60, 60), rnd.uniform(-60, 60), rnd.uniform(-179, 179))
        q = quat_from_rpy(*(math.radians(a) for a in want))
        got = rpy_of(f, q)
        for g, w, n in zip(got, want, ("roll", "pitch", "yaw")):
            c.ok(ang_diff(g, w) < 1e-3, f"for roll={want[0]:.1f} pitch={want[1]:.1f} yaw={want[2]:.1f} "
                                        f"your {n} is {g:.3f}")


@c.test("pitch survives a value slightly above 1 (straight up)",
        hint="Rounding can make 2(w·y − z·x) = 1.0000001 and asin() then crashes: clamp it with max(-1, min(1, ...)).")
def _():
    (f,) = need(load_student("attitude.py"), "quat_to_euler")
    s = math.sqrt(0.5) + 1e-9
    r = rpy_of(f, (0.0, s, 0.0, s))
    c.near(r[1], 90.0, 0.01, what="pitch")


@c.test("heading_from_yaw: east, north, west, south",
        hint="heading = 90 − yaw, then bring it between 0 and 360 with % 360.")
def _():
    (f,) = need(load_student("attitude.py"), "heading_from_yaw")
    for yaw, want in ((0, 90), (90, 0), (180, 270), (-90, 180), (-135, 225), (45, 45), (100, 350)):
        h = f(float(yaw))
        c.ok(h is not None, "heading_from_yaw() still returns None")
        c.ok(0.0 <= h < 360.0, f"heading_from_yaw({yaw}) = {h}: it must be between 0 and 360")
        c.near(h, want, 1e-6, what=f"heading_from_yaw({yaw})")


@c.test("your heading equals NAVERA's heading_deg() on 50 random attitudes",
        hint="heading_from_yaw(quat_to_euler(q)[2]) must give NAVERA's heading_deg(q) "
             "(~/navera/imu_pkg/imu_pkg/orientation.py).")
def _():
    from imu_pkg.orientation import heading_deg, quat_from_rpy
    m = load_student("attitude.py")
    f, h = need(m, "quat_to_euler", "heading_from_yaw")
    rnd = random.Random(7)
    for _ in range(50):
        q = quat_from_rpy(math.radians(rnd.uniform(-40, 40)), math.radians(rnd.uniform(-40, 40)),
                          math.radians(rnd.uniform(-180, 180)))
        mine = h(rpy_of(f, q)[2])
        c.ok(mine is not None, "heading_from_yaw() still returns None")
        c.ok(ang_diff(mine, heading_deg(q)) < 1e-6, f"you say {mine:.3f}, NAVERA says {heading_deg(q):.3f}")


@c.test("true_heading adds the declination and stays between 0 and 360",
        hint="(magnetic + declination) % 360. East declinations are positive, west ones negative.")
def _():
    (f,) = need(load_student("attitude.py"), "true_heading")
    for mag, dec, want in ((100.0, 3.3, 103.3), (358.0, 3.3, 1.3), (10.0, -12.0, 358.0), (0.0, 0.0, 0.0)):
        got = f(mag, dec)
        c.ok(got is not None, "true_heading() still returns None")
        c.near(got, want, 1e-6, what=f"true_heading({mag}, {dec})")


@c.test("declination_at() matches the World Magnetic Model (Sousse and two far places)",
        hint="Copy the two lines of TODO 4: GeoMag().calculate(glat=lat, glon=lon, alt=0, time=year).d")
def _():
    (f,) = need(load_student("attitude.py"), "declination_at")
    for lat, lon, year, want in ((35.8256, 10.636, 2026.75, 3.333), (64.1, -21.9, 2026.5, -11.096),
                                 (-33.9, 151.2, 2026.5, 12.830)):
        got = f(lat, lon, year)
        c.ok(got is not None, "declination_at() still returns None")
        c.near(got, want, 0.02, what=f"declination_at({lat}, {lon}, {year})")


@c.test("ground_offset_m(150, 10) is about 26 m",
        hint="height × tan(tilt) — and math.tan wants RADIANS: math.radians(tilt_deg).")
def _():
    (f,) = need(load_student("attitude.py"), "ground_offset_m")
    c.ok(f(150.0, 10.0) is not None, "ground_offset_m() still returns None")
    c.near(f(150.0, 10.0), 26.449, 0.01, what="ground_offset_m(150, 10)")
    c.near(f(100.0, 0.0), 0.0, 1e-9, what="ground_offset_m(100, 0)")
    c.near(f(100.0, 45.0), 100.0, 1e-6, what="ground_offset_m(100, 45)")


@c.test("integrate_gyro on a tiny example: 0.1 rad/s for 2 s",
        hint="Start the list with 0.0, then add rates[i] × (times[i] − times[i-1]) each step, in DEGREES.")
def _():
    (f,) = need(load_student("gyro_drift.py"), "integrate_gyro")
    got = f([0.0, 1.0, 2.0], [0.1, 0.1, 0.1])
    c.ok(got is not None and len(got) == 3, f"expected a list of 3 angles, got {got!r}")
    for g, w in zip(got, (0.0, 5.7296, 11.4592)):
        c.near(g, w, 1e-3, what="angle")


@c.test("integrate_gyro on the 5-minute log: the total turn the gyroscope measured",
        hint="Use the time difference between samples (not 1/50 written by hand), and keep adding: "
             "the last value is the whole turn.")
def _():
    m = load_student("gyro_drift.py")
    f, load = need(m, "integrate_gyro", "load_log")
    log = load(LOG)
    got = f(log["t_s"], log["gz"])
    c.ok(got is not None and len(got) == len(log["t_s"]), "integrate_gyro must return one angle per sample")
    c.near(got[3000], -87.89, 0.3, what="the angle after 60 s")
    c.near(got[-1], -350.32, 0.3, what="the angle after 300 s")


@c.test("gyro_drift.py runs and saves drift.png",
        hint="Run `python3 gyro_drift.py` and read the error, if any.")
def _():
    if os.path.exists("drift.png"):
        os.remove("drift.png")
    code, out = sh("python3 gyro_drift.py", timeout=60)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])
    c.file_exists("drift.png")
    with open("drift.png", "rb") as fh:
        c.ok(fh.read(8) == b"\x89PNG\r\n\x1a\n", "drift.png is not a PNG image")


ANSWERS = {"Q1": ("c", "Which of the three sensors is a compass?"),
           "Q2": ("b", "Run gyro_drift.py and read the line 'after 300 s'."),
           "Q3": ("a", "Read the part of the course about straightening the photo.")}

for q, (good, hint) in ANSWERS.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
