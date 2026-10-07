import contextlib
import io

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()


def quiet_load(name):
    """Import a student file without letting its print() calls mix with the check results."""
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def nav(*names):
    return need(quiet_load("nav_math.py"), *names)


def call(fn, *args, **kw):
    """Call a student's function; a TODO not written yet becomes a friendly ✘."""
    try:
        return fn(*args, **kw)
    except NotImplementedError as e:
        raise CheckFailed(f"{fn.__name__}() is not written yet ({e})")


# ---------------------------------------------------------------- warm-up: mission.py
@c.test("mission.py runs without errors",
        hint="Run `python3 mission.py` in the terminal and read the last line of the error.")
def _():
    code, out = sh("python3 mission.py", timeout=20)
    c.ok(code == 0, "mission.py stopped with an error:\n" + out[-600:])


@c.test("TODO A: mission_time_min is computed from the variables",
        hint="hours = distance / speed; minutes = hours × 60. Use the variable names, not the numbers.")
def _():
    m = quiet_load("mission.py")
    d, v, t = need(m, "mission_distance_km", "cruise_speed_kmh", "mission_time_min")
    c.ok(t != 0, "mission_time_min is still 0")
    c.near(t, d / v * 60, tol=0.01, what="mission_time_min")


@c.test("TODO B: mission.py prints a sentence with the name and the time",
        hint='print(f"{drone_name} flies ... {mission_time_min:.1f} minutes") — the variables go between { }.')
def _():
    m = quiet_load("mission.py")
    name, t = need(m, "drone_name", "mission_time_min")
    _, out = sh("python3 mission.py", timeout=20)
    lines = [l for l in out.splitlines() if not l.startswith(("Drone:", "Speed:"))]
    text = "\n".join(lines)
    c.ok(str(name) in text, f"I can't find a new line with the drone name ({name}) in what mission.py prints")
    c.ok(f"{t:.1f}" in text, f"I can't find the time rounded to 1 decimal ({t:.1f}) in what mission.py prints")
    c.ok("min" in text, 'say the unit: the sentence should contain "minutes"')


# ---------------------------------------------------------------- Part 1
@c.test("TODO 1-2: kmh_to_ms() and ms_to_kmh()",
        hint="m/s = km/h ÷ 3.6 and km/h = m/s × 3.6. Use the parameter, not a fixed number.")
def _():
    to_ms, to_kmh = nav("kmh_to_ms", "ms_to_kmh")
    for kmh, ms in ((36, 10.0), (54, 15.0), (90, 25.0), (0, 0.0), (7.2, 2.0)):
        c.near(call(to_ms, kmh), ms, tol=1e-6, what=f"kmh_to_ms({kmh})")
        c.near(call(to_kmh, ms), kmh, tol=1e-6, what=f"ms_to_kmh({ms})")


@c.test("TODO 3: distance_m()", hint="distance = speed × time, with the two parameters.")
def _():
    (f,) = nav("distance_m")
    for v, t, want in ((15, 60, 900), (2.5, 10, 25), (0, 100, 0), (12, 0.5, 6)):
        c.near(call(f, v, t), want, tol=1e-6, what=f"distance_m({v}, {t})")


@c.test("TODO 4: travel_time_s() for a normal speed", hint="time = distance ÷ speed.")
def _():
    (f,) = nav("travel_time_s")
    for d, v, want in ((900, 15, 60), (1000, 4, 250), (50, 2.5, 20)):
        c.near(call(f, d, v), want, tol=1e-6, what=f"travel_time_s({d}, {v})")


@c.test("TODO 4: travel_time_s() returns None when the speed is 0 or negative",
        hint="Start the function with:  if speed_ms <= 0:  and return None inside it (indented!).")
def _():
    (f,) = nav("travel_time_s")
    for v in (0, -3):
        try:
            r = call(f, 900, v)
        except ZeroDivisionError:
            raise CheckFailed(f"travel_time_s(900, {v}) divides by zero — test the speed BEFORE dividing")
        c.ok(r is None, f"travel_time_s(900, {v}) returned {r!r}, expected None")


# ---------------------------------------------------------------- Part 2
@c.test("TODO 5: flight_time_min()",
        hint="usable = battery × (100 − reserve) ÷ 100; hours = usable ÷ power; minutes = hours × 60.")
def _():
    (f,) = nav("flight_time_min")
    c.near(call(f, 100, 400), 12.0, tol=1e-6, what="flight_time_min(100, 400)")
    c.near(call(f, 77, 154), 24.0, tol=1e-6, what="flight_time_min(77, 154)")
    c.near(call(f, 100, 400, 0), 15.0, tol=1e-6, what="flight_time_min(100, 400, 0)")
    c.near(call(f, 100, 400, reserve_percent=50), 7.5, tol=1e-6,
           what="flight_time_min(100, 400, reserve_percent=50)")


@c.test("TODO 6: battery_status() — including the limits 50 and 20",
        hint='50 is "OK" and 20 is "LOW": use >= (or <) carefully, and check the biggest value first.')
def _():
    (f,) = nav("battery_status")
    for p, want in ((100, "OK"), (50, "OK"), (49.9, "LOW"), (35, "LOW"), (20, "LOW"), (19.9, "LAND NOW"), (0, "LAND NOW")):
        c.eq(call(f, p), want, what=f"battery_status({p})")


# ---------------------------------------------------------------- Part 3
@c.test("TODO 7: distance_from_home_m()",
        hint="Pythagoras: math.sqrt(x ** 2 + y ** 2). A negative x or y gives the same distance.")
def _():
    (f,) = nav("distance_from_home_m")
    for x, y, want in ((300, 400, 500), (0, 0, 0), (-600, 0, 600), (0, -250, 250), (500, -500, 707.1068), (-5, -12, 13)):
        c.near(call(f, x, y), want, tol=1e-3, what=f"distance_from_home_m({x}, {y})")


@c.test("TODO 8: inside_circle() — 600 m by default, ON the circle counts as inside",
        hint="return distance_from_home_m(x_m, y_m) <= radius_m  — a comparison already IS True or False.")
def _():
    (f,) = nav("inside_circle")
    for args, want in (((300, 400), True), ((500, -500), False), ((600, 0), True), ((0, -601), False),
                       ((-360, 480), True), ((300, 400, 450), False), ((300, 400, 500), True)):
        r = call(f, *args)
        c.ok(isinstance(r, bool), f"inside_circle{args} returned {r!r} — it should be True or False")
        c.eq(r, want, what=f"inside_circle{args}")


@c.test("TODO 9: status_line() text, exactly as in the example",
        hint='return f"{name} is {d:.0f} m from home: {where}" — where is "INSIDE" or "OUTSIDE".')
def _():
    (f,) = nav("status_line")
    for args, want in (
        (("drone-1", 300, 400), "drone-1 is 500 m from home: INSIDE"),
        (("drone-2", 500, -500), "drone-2 is 707 m from home: OUTSIDE"),
        (("rover", 0, 600), "rover is 600 m from home: INSIDE"),
        (("boat", -1000, 20), "boat is 1000 m from home: OUTSIDE"),
    ):
        r = call(f, *args)
        c.ok(r is not None, "status_line() returned None — use return, not print")
        c.eq(r, want, what=f"status_line{args}")


@c.test("nav_math.py runs its demo without errors", hint="Run `python3 nav_math.py` and read the error.")
def _():
    code, out = sh("python3 nav_math.py", timeout=20)
    c.ok(code == 0, "nav_math.py stopped with an error:\n" + out[-600:])
    todo = sorted({l.split("(")[-1].rstrip(")") for l in out.splitlines() if "not written yet" in l})
    c.ok(not todo, "still not written: " + ", ".join(todo))


c.run()
