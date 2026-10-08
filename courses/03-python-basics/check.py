import contextlib
import io
import json
import math
import os
import re

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()


def quiet_load(name):
    """Import a student file without letting its print() calls mix with the check results."""
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def nav(*names):
    return need(quiet_load("navlib.py"), *names)


def call(fn, *args, **kw):
    """Call a student's function; a TODO not written yet becomes a friendly ✘."""
    try:
        return fn(*args, **kw)
    except NotImplementedError as e:
        raise CheckFailed(f"{getattr(fn, '__name__', 'this code')} is not written yet ({e})")


def raises_value_error(fn, *args, what=""):
    try:
        call(fn, *args)
    except ValueError:
        return
    except CheckFailed:
        raise
    except Exception as e:
        raise CheckFailed(f"{what} raised {type(e).__name__}: {e} — it should raise ValueError")
    raise CheckFailed(f"{what} did not raise ValueError")


def pair(r, what):
    c.ok(isinstance(r, tuple) and len(r) == 2, f"{what} returned {r!r} — expected a tuple of 2 numbers")
    return r


def near_angle(got, want, tol, what):
    d = (float(got) - want + 180.0) % 360.0 - 180.0
    c.ok(abs(d) <= tol, f"{what} is {float(got):.4g}°: {'too far clockwise' if d > 0 else 'too far anticlockwise'} "
                        f"(it must be within ± {tol:g}° of the right value)")


# ---------------------------------------------------------------- Part A
@c.test("TODO 1: heading_vector() — (east, north), clockwise from north",
        hint="Headings are in degrees: convert with math.radians. East is sin(heading), north is cos(heading).")
def _():
    (f,) = nav("heading_vector")
    for h, (e, n) in ((0, (0.0, 1.0)), (90, (1.0, 0.0)), (225, (-0.70711, -0.70711)), (330, (-0.5, 0.86603))):
        r = pair(call(f, h), f"heading_vector({h})")
        c.near(r[0], e, 1e-4, f"east of heading_vector({h})")
        c.near(r[1], n, 1e-4, f"north of heading_vector({h})")


@c.test("TODO 2: ground_velocity() = air velocity + wind",
        hint="Multiply the unit vector of the heading by the airspeed, then add the wind components one by one.")
def _():
    (f,) = nav("ground_velocity")
    for args, (e, n) in (((15, 0, 4, 0), (4.0, 15.0)), ((20, 135, 1, 2), (15.14214, -12.14214)),
                         ((10, 270), (-10.0, 0.0))):
        r = pair(call(f, *args), f"ground_velocity{args}")
        c.near(r[0], e, 1e-3, f"east of ground_velocity{args}")
        c.near(r[1], n, 1e-3, f"north of ground_velocity{args}")


@c.test("TODO 3: wind_correction() — heading to fly and ground speed",
        hint="Project the wind on the track (along) and on the direction 90° to its right (cross). "
             "crab = asin(cross / airspeed); heading = track − crab (degrees, then % 360).")
def _():
    (f,) = nav("wind_correction")
    for args, (h, gs) in (((15, 0, 4, 0), (344.534, 14.4568)), ((12, 30, -3, -4), (32.8568, 7.02099)),
                          ((12, 210, -3, -4), (207.143, 16.9492)), ((20, 90, 0, 5), (104.478, 19.3649)),
                          ((18, 300, 6, -2), (295.961, 11.7591))):
        r = pair(call(f, *args), f"wind_correction{args}")
        near_angle(r[0], h, 0.01, f"the heading of wind_correction{args}")
        c.ok(0 <= r[0] < 360, f"the heading of wind_correction{args} is {r[0]:.4g}: keep it in [0, 360) with % 360")
        c.near(r[1], gs, 1e-3, f"the ground speed of wind_correction{args}")


@c.test("TODO 3: wind_correction() raises ValueError when no heading works",
        hint="Two cases: |cross| > airspeed (asin would fail with 'math domain error'), and a ground speed <= 0.")
def _():
    (f,) = nav("wind_correction")
    raises_value_error(f, 15, 0, 20, 0, what="wind_correction(15, 0, 20, 0) (crosswind 20 m/s)")
    raises_value_error(f, 15, 0, 0, -20, what="wind_correction(15, 0, 0, -20) (headwind 20 m/s)")


@c.test("TODO 4: flight_time_min() — values and ValueError on bad inputs",
        hint="usable = battery × (1 − reserve_frac); minutes = usable / power × 60. Check the inputs FIRST.")
def _():
    (f,) = nav("flight_time_min")
    for args, want in (((100, 400), 12.0), ((50, 400), 6.0), ((77, 154), 24.0), ((100, 400, 0.0), 15.0),
                       ((120, 300, 0.25), 18.0)):
        c.near(call(f, *args), want, 1e-6, f"flight_time_min{args}")
    raises_value_error(f, 100, 0, what="flight_time_min(100, 0)")
    raises_value_error(f, -5, 400, what="flight_time_min(-5, 400)")
    raises_value_error(f, 100, 400, 1.0, what="flight_time_min(100, 400, 1.0)")
    raises_value_error(f, 100, 400, -0.1, what="flight_time_min(100, 400, -0.1)")


# ---------------------------------------------------------------- Part B
@c.test("TODO 5: Vehicle.__init__ stores its attributes and refuses cruise_ms <= 0",
        hint="self.name = name, and the same for cruise_ms, battery_wh and power_w. Check cruise_ms first.")
def _():
    (V,) = nav("Vehicle")
    v = call(V, "quad", 12, 100, 400)
    for attr, want in (("name", "quad"), ("cruise_ms", 12), ("battery_wh", 100), ("power_w", 400)):
        c.ok(hasattr(v, attr), f"a Vehicle has no attribute {attr} — write self.{attr} = {attr}")
        c.eq(getattr(v, attr), want, f"Vehicle(...).{attr}")
    raises_value_error(V, "bad", 0, 100, 400, what='Vehicle("bad", 0, 100, 400)')


@c.test("TODO 6: Vehicle.endurance_s() and range_m()",
        hint="endurance_s() reuses flight_time_min() (minutes → seconds). range_m(): (cruise + wind_along) × "
             "endurance; 0.0 when that ground speed is <= 0.")
def _():
    (V,) = nav("Vehicle")
    v = call(V, "quad", 12, 100, 400)
    c.near(call(v.endurance_s), 720.0, 1e-6, "Vehicle('quad', 12, 100, 400).endurance_s()")
    c.near(call(v.endurance_s, 0.0), 900.0, 1e-6, "endurance_s(0.0)")
    c.near(call(v.range_m), 8640.0, 1e-6, "range_m()")
    c.near(call(v.range_m, 0.0, 4), 14400.0, 1e-6, "range_m(0.0, 4) (tailwind 4 m/s, no reserve)")
    c.near(call(v.range_m, wind_along_ms=-12), 0.0, 1e-9, "range_m(wind_along_ms=-12) (headwind = airspeed)")


@c.test("TODO 7: FixedWing(Vehicle) — super().__init__, stall check, turn radius",
        hint="First line of __init__: super().__init__(name, cruise_ms, battery_wh, power_w). "
             "Turn radius r = v² / (g · tan(bank)), bank in radians.")
def _():
    V, F = nav("Vehicle", "FixedWing")
    w = call(F, "wing", 25, 200, 300, 14)
    c.ok(isinstance(w, V), "a FixedWing should also be a Vehicle (class FixedWing(Vehicle))")
    for attr, want in (("name", "wing"), ("cruise_ms", 25), ("battery_wh", 200), ("power_w", 300), ("stall_ms", 14)):
        c.ok(hasattr(w, attr), f"a FixedWing has no attribute {attr} — did you call super().__init__(...)?")
        c.eq(getattr(w, attr), want, f"FixedWing(...).{attr}")
    c.near(call(w.endurance_s, 0.1), 2160.0, 1e-6, "FixedWing(...).endurance_s(0.1) (inherited)")
    c.near(call(w.turn_radius_m), 110.350, 1e-2, "turn_radius_m() (25 m/s, 30° bank)")
    c.near(call(w.turn_radius_m, 45), 63.710, 1e-2, "turn_radius_m(45)")
    raises_value_error(F, "slow", 12, 150, 200, 14, what='FixedWing("slow", 12, 150, 200, 14) (cruise below stall)')
    raises_value_error(F, "zero", 0, 150, 200, 14, what='FixedWing("zero", 0, ...) (Vehicle should refuse it)')


@c.test("TODO 8: Track.add() appends, and refuses a time that does not increase",
        hint="Compare t with self.t[-1] only when the list is not empty; raise ValueError for t <= last time.")
def _():
    (T,) = nav("Track")
    tr = T("x")
    for p in ((0, 0, 0), (2, 6, 8), (3, 6, 8)):
        call(tr.add, *p)
    c.eq(len(tr), 3, "len(track) after 3 add()")
    c.eq(list(tr.t), [0.0, 2.0, 3.0], "track.t")
    c.eq(list(tr.east), [0.0, 6.0, 6.0], "track.east")
    raises_value_error(tr.add, 3, 1, 1, what="add() with the same time as the last point")
    raises_value_error(tr.add, 1, 1, 1, what="add() with a time in the past")
    c.eq(len(tr), 3, "len(track) after two refused add()")


@c.test("TODO 9: Track.length_m() and speeds_ms() with NumPy",
        hint="np.diff gives the n−1 differences; np.hypot(de, dn) the segment lengths; divide by np.diff(t) "
             "for the speeds. Fewer than 2 points: length 0.0 and an empty array.")
def _():
    import numpy as np
    (T,) = nav("Track")
    tr = T("x")
    for p in ((0, 0, 0), (2, 6, 8), (3, 6, 8), (5, 0, 0)):
        call(tr.add, *p)
    c.near(call(tr.length_m), 20.0, 1e-9, "length_m() of (0,0)→(6,8)→(6,8)→(0,0)")
    s = call(tr.speeds_ms)
    c.ok(isinstance(s, np.ndarray), f"speeds_ms() returned {type(s).__name__} — it should return a NumPy array")
    c.eq([round(float(x), 6) for x in s], [5.0, 0.0, 5.0], "speeds_ms()")
    one = T("one")
    call(one.add, 0, 1, 1)
    c.near(call(one.length_m), 0.0, 1e-12, "length_m() of a 1-point track")
    c.eq(len(call(one.speeds_ms)), 0, "len(speeds_ms()) of a 1-point track")


# ---------------------------------------------------------------- mission.py and the report
EXPECTED = {
    "out_heading_deg": (32.857, 0.01), "out_ground_speed_ms": (7.0210, 0.001),
    "quad_endurance_min": (21.943, 0.001), "quad_round_trip_min": (30.215, 0.005),
    "wing_endurance_min": (32.727, 0.001), "wing_round_trip_min": (15.993, 0.005),
    "wing_turn_radius_m": (70.624, 0.01),
    "track_points": (263, 0), "track_length_m": (3270.14, 0.05), "track_max_speed_ms": (54.340, 0.005),
    "track_median_speed_ms": (12.052, 0.005),
    "glitch_time_s": (150, 0),
}
BOOLS = {"quad_can_do_it": False, "wing_can_do_it": True}


def results():
    c.file_exists("results.json")
    try:
        with open("results.json") as f:
            return json.load(f)
    except ValueError as e:
        raise CheckFailed(f"results.json is not valid JSON: {e}")


@c.test("mission.py runs and writes results.json",
        hint="Run `python3 mission.py`. If it says a TODO is not written yet, finish navlib.py first.")
def _():
    if os.path.exists("results.json"):
        os.remove("results.json")
    code, out = sh("python3 mission.py", timeout=30)
    if "not written yet" in out:
        raise CheckFailed(out.strip().splitlines()[-1])
    if code != 0:
        last = [l for l in out.strip().splitlines() if l.strip()][-1:] or ["(no output)"]
        raise CheckFailed("mission.py stopped with an error — run it and read the last line: " + last[0])
    results()


@c.test("results.json: wind triangle, endurance and round trips (TODO A, B)",
        hint="Each key named in mission.py must hold a number (or a bool for *_can_do_it). "
             "Round trip = out leg / ground speed out + back leg / ground speed back.")
def _():
    r = results()
    for k in ("out_heading_deg", "out_ground_speed_ms", "quad_endurance_min", "quad_round_trip_min",
              "wing_endurance_min", "wing_round_trip_min", "wing_turn_radius_m"):
        c.ok(r.get(k) is not None, f'results.json has no value for "{k}"')
        want, tol = EXPECTED[k]
        c.near(r[k], want, tol, k)
    for k, want in BOOLS.items():
        c.ok(isinstance(r.get(k), bool), f'"{k}" should be true or false (a bool), got {r.get(k)!r}')
        c.eq(r[k], want, k)


@c.test("results.json: the survey track (TODO C)",
        hint="Use your Track methods on load_track('harbour_track.csv'). glitch: the first speed > 25 m/s "
             "(a boolean mask, then np.argmax); speed i ends at point i+1, so the time is t[i + 1].")
def _():
    r = results()
    for k in ("track_points", "track_length_m", "track_max_speed_ms", "track_median_speed_ms", "glitch_time_s"):
        c.ok(r.get(k) is not None, f'results.json has no value for "{k}"')
        want, tol = EXPECTED[k]
        c.near(r[k], want, max(tol, 1e-9), k)


def numbers_in(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))]


@c.test("report.md: three sections, your own words, with the key numbers",
        hint="Keep the three ## headings, replace every '(write here)' by 2–4 sentences. Quote the quad's round "
             "trip in minutes and the glitch time in s.")
def _():
    c.file_exists("report.md")
    with open("report.md") as f:
        text = f.read()
    low = text.lower()
    for h in ("## wind", "## endurance", "## track"):
        c.ok(h in low, f'report.md has no section starting with "{h}"')
    c.ok("(write here)" not in low, 'report.md still contains "(write here)"')
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    c.ok(words >= 100, f"report.md has about {words} words — write at least 100")
    nums = numbers_in(text)
    c.ok(any(abs(x - 30.2) <= 0.15 for x in nums), "I can't find the quad's round-trip time (about 30.2 min) in report.md")
    c.ok(any(abs(x - 150) < 0.5 for x in nums), "I can't find the glitch time (in s) in report.md")


c.run()
