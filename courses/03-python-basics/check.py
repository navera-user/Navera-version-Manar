import ast
import contextlib
import inspect
import io
import re
import textwrap

from academy_check import (CheckFailed, Checker, StudentError, explained, is_stub, load_student, need, predicted,
                           run)

c = Checker()


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def veh(*names):
    return need(quiet("navera_lite.vehicle"), *names)


def answers(*names):
    try:
        return need(quiet("answers.py"), *names)
    except StudentError as e:
        if "syntax" in str(e) or "NameError" in str(e):
            raise CheckFailed(f"{e} — text needs quotes: PREDICT_TRIP = \"longer\"")
        raise


def number(v, name):
    if isinstance(v, (bool, str)) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def done(fn, what):
    """A stub not written yet → one clear ✘."""
    if is_stub(fn):
        raise CheckFailed(f"{what} is not written yet (it is still the TODO stub)")


def pair(r, what):
    if not (isinstance(r, (tuple, list)) and len(r) == 2 and all(isinstance(x, (int, float)) for x in r)):
        raise CheckFailed(f"{what} returned {r!r} — expected a tuple of 2 numbers, like (1.0, 2.0)")
    return float(r[0]), float(r[1])


def raises(fn, *args, what):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r = fn(*args)
    except ValueError:
        return
    except NotImplementedError:
        raise CheckFailed(f"{what}: not written yet")
    except Exception as e:
        raise CheckFailed(f"{what} raised {type(e).__name__}: {e} — it should raise ValueError with a sentence "
                          "(`raise ValueError(\"...\")`)")
    raise CheckFailed(f"{what} returned {r!r} instead of raising ValueError")


def angle_gap(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


# C-level iterators a line trace cannot see (they loop without running a Python line of the student's file)
LOOPY = {"map", "filter", "sum", "range", "zip", "enumerate", "sorted", "reversed", "iter", "next", "reduce"}


def loops_in(fn):
    """A loop the line count below cannot see: a builtin iterator (map, sum, zip, …) over the data, or a NumPy
    wrapper that calls a function once per element. Python-level loops (for/while, comprehensions, helpers)
    are left to the line count, so a comprehension over two lists or a .tolist()-like conversion is not refused."""
    import builtins
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    g, local = getattr(fn, "__globals__", {}), set(fn.__code__.co_varnames)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and (f.attr in ("vectorize", "frompyfunc")
                                             or f.attr == "reduce" and getattr(f.value, "id", "") == "functools"):
            return True
        if isinstance(f, ast.Name) and f.id in LOOPY and f.id not in local \
                and g.get(f.id, getattr(builtins, f.id, None)) is getattr(builtins, f.id, None):
            data = n.args[1:] if f.id == "map" else n.args
            if not all(isinstance(x, (ast.Tuple, ast.List)) for x in data):   # map(np.array, (a, b)) is fine
                return True
    return False


def python_lines_run(T, method, *args, n=2000):
    """How many Python lines of the student's own files run while tr.method(*args) works on an n-position
    track. A whole-array version runs a handful; a loop hidden anywhere (a helper, a lambda in np.vectorize,
    a loop moved into arrays()…) runs thousands."""
    import os
    import sys
    tr = T()
    for i in range(n):
        tr.add(i, 3.0 * i, 4.0 * i)
    here = os.getcwd() + os.sep
    count = [0]

    def tracer(frame, event, arg):
        if frame.f_code.co_filename.startswith(here):
            if event == "line":
                count[0] += 1
            return tracer
        return None
    sys.settrace(tracer)
    try:
        getattr(tr, method)(*args)
    finally:
        sys.settrace(None)
    return count[0]


def vectorised(T, method, *args):
    return not loops_in(getattr(T, method)) and python_lines_run(T, method, *args) < 100


def make_track(T, points):
    tr = T()
    for p in points:
        run(tr.add, *p)
    return tr


# ================================================================ Session 1 — vehicle.py functions
@c.test("TODO 1: heading_vector() — (east, north), clockwise from north",
        hint="Lesson §2: degrees → math.radians first; east is the sine, north the cosine (not the maths order).")
def _():
    (f,) = veh("heading_vector")
    done(f, "heading_vector()")
    for h, want in ((0, (0.0, 1.0)), (90, (1.0, 0.0)), (225, (-0.70711, -0.70711)), (-30, (-0.5, 0.86603)),
                    (123.4, (0.83485, -0.55048))):
        e, n = pair(run(f, h), f"heading_vector({h})")
        if abs(e - want[1]) < 1e-3 and abs(n - want[0]) < 1e-3 and h not in (225,):
            raise CheckFailed(f"heading_vector({h}) gives ({e:.4f}, {n:.4f}): east and north are swapped — "
                              "a heading counts from NORTH, so east = sin, north = cos")
        if abs(e - 1.0) < 0.01 and h == 0:
            raise CheckFailed("heading_vector(0) points east: headings start at north (lesson §2)")
        c.near(e, want[0], 1e-4, f"east of heading_vector({h})")
        c.near(n, want[1], 1e-4, f"north of heading_vector({h})")


@c.test("TODO 2: ground_velocity() = air velocity + wind",
        hint="Lesson §2: airspeed × the unit vector of the heading (call heading_vector), then add the wind, "
             "component by component. Without wind arguments the defaults are 0.0.")
def _():
    (f,) = veh("ground_velocity")
    done(f, "ground_velocity()")
    for args, want in (((15, 0, 4, 0), (4.0, 15.0)), ((20, 135, 1, 2), (15.14214, -12.14214)),
                       ((10, 270), (-10.0, 0.0))):
        e, n = pair(run(f, *args), f"ground_velocity{args}")
        c.near(e, want[0], 1e-3, f"east of ground_velocity{args}")
        c.near(n, want[1], 1e-3, f"north of ground_velocity{args}")


@c.test("TODO 3: wind_components() — along and across the track",
        hint="Lesson §2: along = wind · (unit vector of the track); cross = wind · (unit vector 90° to the RIGHT "
             "of the track). Dot product: wₑ·uₑ + wₙ·uₙ.")
def _():
    (f,) = veh("wind_components")
    done(f, "wind_components()")
    for args, want in (((30, -3, -4), (-4.96410, -0.59808)), ((250, 4, 1.5), (-4.27180, 0.04146)),
                       ((135, -2, 6), (-5.65685, -2.82843)), ((0, 0, -7), (-7.0, 0.0))):
        a, x = pair(run(f, *args), f"wind_components{args}")
        if abs(a - want[1]) < 1e-3 and abs(x - want[0]) < 1e-3 and args[0] != 0:
            raise CheckFailed(f"wind_components{args} gives ({a:.3f}, {x:.3f}): along and cross are swapped")
        if abs(a - want[0]) < 1e-3 and abs(x + want[1]) < 1e-3 and abs(want[1]) > 0.01:
            raise CheckFailed(f"wind_components{args}: along is right but cross has the wrong sign — cross > 0 "
                              "must push to the RIGHT of the track (unit vector of track + 90°)")
        c.near(a, want[0], 1e-3, f"along of wind_components{args}")
        c.near(x, want[1], 1e-3, f"cross of wind_components{args}")


@c.test("TODO 4: heading_for_track() — heading to fly and ground speed",
        hint="Lesson §2: the crab angle c has sin c = cross / airspeed; fly INTO the wind: heading = track − c; "
             "ground speed = airspeed · cos c + along. Degrees out, kept in [0, 360) with % 360.")
def _():
    (f,) = veh("heading_for_track")
    done(f, "heading_for_track()")
    cases = (((135, 15, -2, 6), (145.86886, 9.07407)), ((250, 18, 4, 1.5), (249.86803, 13.72815)),
             ((300, 25, 8, -3), (296.78534, 16.53246)), ((10, 9, 0, 0), (10.0, 9.0)),
             ((350, 14, -5, -5), (14.43963, 8.68977)))
    for args, (h, gs) in cases:
        r = pair(run(f, *args), f"heading_for_track{args}")
        crab = angle_gap(args[0], h)
        if abs(angle_gap(r[0], args[0] + crab)) < 0.01 and abs(crab) > 0.5:
            raise CheckFailed(f"heading_for_track{args}: the heading is on the wrong side of the track — you add "
                              "the crab angle; the vehicle must point INTO the crosswind (track − crab)")
        if abs(r[0] - h) > 1 and abs(r[0] - math_deg_to_rad(h)) < 0.01:
            raise CheckFailed(f"heading_for_track{args}: the heading looks like radians — convert with math.degrees")
        if not 0 <= r[0] < 360:
            raise CheckFailed(f"heading_for_track{args} gives the heading {r[0]:.4g}: keep it in [0, 360) with % 360")
        c.ok(abs(angle_gap(r[0], h)) <= 0.01, f"heading_for_track{args}: the heading {r[0]:.4g}° is not right")
        c.near(r[1], gs, 1e-3, f"the ground speed of heading_for_track{args}")


def math_deg_to_rad(d):
    import math
    return math.radians(d)


@c.test("TODO 4: heading_for_track() refuses an impossible wind with ValueError",
        hint="Two cases (lesson §1 and §2): |cross| > airspeed — check it BEFORE math.asin, which would crash "
             "with 'math domain error' — and a ground speed <= 0 (a headwind as strong as the vehicle).")
def _():
    (f,) = veh("heading_for_track")
    done(f, "heading_for_track()")
    for args, what in (((0, 10, 11, 0), "heading_for_track(0, 10, 11, 0) (crosswind 11 m/s, airspeed 10 m/s)"),
                       ((90, 8, 1, -9), "heading_for_track(90, 8, 1, -9) (crosswind 9 m/s, airspeed 8 m/s)"),
                       ((0, 10, -11, 0), "heading_for_track(0, 10, -11, 0) (crosswind 11 m/s pushing LEFT, "
                                         "airspeed 10 m/s: is your test `abs(cross) > tas_mps`?)")):
        raises(f, *args, what=what)
        try:
            f(*args)
        except ValueError as e:
            c.ok("math domain" not in str(e),
                 f"{what}: the ValueError comes from math.asin ('math domain error'), not from your code — test "
                 "abs(cross) > tas_mps yourself BEFORE math.asin and raise your own ValueError with a sentence")
    raises(f, 0, 10, 0, -10, what="heading_for_track(0, 10, 0, -10) (headwind 10 m/s: ground speed 0)")
    raises(f, 180, 10, 1, 12, what="heading_for_track(180, 10, 1, 12) (headwind 12 m/s)")


@c.test("TODO 5: endurance_s() — values in seconds, and ValueError on impossible input",
        hint="Lesson §1: usable energy = battery × (1 − reserve) Wh; energy / power = hours; × 3600 = seconds. "
             "Check the inputs FIRST: battery > 0, power > 0, 0 <= reserve < 1 (1.0 itself is refused).")
def _():
    (f,) = veh("endurance_s")
    done(f, "endurance_s()")
    got = run(f, 80, 300)
    if isinstance(got, (int, float)) and abs(got - 768.0 / 60) < 0.01:
        raise CheckFailed("endurance_s(80, 300) looks like minutes: the function returns SECONDS (_s)")
    if isinstance(got, (int, float)) and abs(got - 960.0) < 0.01:
        raise CheckFailed("endurance_s(80, 300) ignores the default reserve of 0.2")
    for args, want in (((80, 300), 768.0), ((80, 300, 0), 960.0), ((37, 148, 0.35), 585.0),
                       ((1.2, 25, 0.15), 146.88)):
        c.near(run(f, *args), want, 1e-6, f"endurance_s{args}")
    raises(f, 0, 300, what="endurance_s(0, 300) (no battery)")
    raises(f, 80, -5, what="endurance_s(80, -5) (negative power)")
    raises(f, 80, 300, 1.0, what="endurance_s(80, 300, 1.0) (reserve 100 %: nothing usable)")
    raises(f, 80, 300, -0.1, what="endurance_s(80, 300, -0.1) (negative reserve)")


@c.test("Step 3–4: the lighthouse mission — wind, go/no-go, explanation",
        hint="Heading and ground speeds: your heading_for_track with the wind vector printed by plan_mission.py "
             "wind (2 decimals); TRIP_MIN: add the two legs printed by gonogo (minutes, 2 decimals). DECISION is \"GO\" or \"NO-GO\". EXPLAIN_TRIP: compare the time LOST on the "
             "slow leg with the time GAINED on the fast one.")
def _():
    (pw, h, g1, g2, pt, trip, endu, dec, why) = answers(
        "PREDICT_WIND", "OUT_HEADING_DEG", "OUT_GS_MPS", "BACK_GS_MPS", "PREDICT_TRIP", "TRIP_MIN", "ENDURANCE_MIN",
        "DECISION", "EXPLAIN_TRIP")
    predicted("PREDICT_WIND", pw)
    predicted("PREDICT_TRIP", pt)
    h = number(h, "OUT_HEADING_DEG")
    c.ok(abs(h - 30) > 0.5, "OUT_HEADING_DEG is the track itself: heading_for_track gives the heading to FLY")
    c.near(h, 25.02, 0.05, "OUT_HEADING_DEG")
    c.near(number(g1, "OUT_GS_MPS"), 6.05, 0.02, "OUT_GS_MPS")
    c.near(number(g2, "BACK_GS_MPS"), 17.86, 0.02, "BACK_GS_MPS")
    t = number(trip, "TRIP_MIN")
    c.ok(abs(t - 20.83) > 0.05, "TRIP_MIN is the still-air time: write the round trip WITH the wind")
    c.ok(t < 1000, "TRIP_MIN looks like seconds: write minutes")
    c.near(t, 27.67, 0.05, "TRIP_MIN")
    c.near(number(endu, "ENDURANCE_MIN"), 21.94, 0.05, "ENDURANCE_MIN")
    c.ok(str(dec).strip().upper().replace(" ", "-").replace("_", "-") in ("GO", "NO-GO"),
         f"DECISION = {dec!r}: write \"GO\" or \"NO-GO\"")
    c.ok(str(dec).strip().upper().replace(" ", "-").replace("_", "-") == "NO-GO",
         "DECISION: compare your TRIP_MIN with ENDURANCE_MIN — GO only if the round trip is shorter")
    explained("EXPLAIN_TRIP", why,
              ([r"head", r"against", r"slow", r"out"], "the slow (headwind) leg"),
              ([r"tail", r"back", r"fast", r"return"], "the fast (tailwind) leg"),
              ([r"time", r"longer", r"more", r"minute", r"second", r"lose", r"lost", r"gain"],
               "why the time lost is larger than the time gained"))


@c.test("Step 5: the wind limit of the quad — my_limit.py and MAX_WIND_MPS",
        hint="my_limit.py: winds from 020° at 0.0, 0.5, 1.0 … m/s; for each, the round trip with your "
             "heading_for_track() against your endurance_s(); stop at the first NO-GO; the LAST line printed is "
             "MAX_WIND_MPS = <the last GO speed>. Copy that value into answers.py.")
def _():
    import os
    import re
    import subprocess
    import sys
    c.ok(os.path.exists("my_limit.py"), "my_limit.py does not exist yet in the lesson folder (Step 5)")
    probe = (
        "import runpy, sys\n"
        "import navera_lite.vehicle as v\n"
        "calls = {'h': 0, 'e': 0}; winds = []\n"
        "h0, e0 = v.heading_for_track, v.endurance_s\n"
        "def h(*a, **k):\n"
        "    calls['h'] += 1\n"
        "    names = ('track_deg', 'tas_mps', 'wind_e', 'wind_n')\n"
        "    d = dict(zip(names, a)); d.update(k)\n"
        "    winds.append((float(d.get('wind_e', 0)), float(d.get('wind_n', 0))))\n"
        "    return h0(*a, **k)\n"
        "def e(*a, **k):\n"
        "    calls['e'] += 1\n"
        "    return e0(*a, **k)\n"
        "v.heading_for_track, v.endurance_s = h, e\n"
        "try:\n"
        "    runpy.run_path('my_limit.py', run_name='__main__')\n"
        "finally:\n"
        "    sys.stdout.flush()\n"
        "    ne = sum(1 for we, wn in winds if we > 0.01 and wn > 0.01)\n"
        "    sw = sum(1 for we, wn in winds if we < -0.01 and wn < -0.01)\n"
        "    print('PROBE', calls['h'], calls['e'], ne if sw == 0 else 0, flush=True)\n")
    try:
        r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise CheckFailed("my_limit.py did not finish in 60 s — is its loop endless?")
    out = r.stdout + r.stderr
    if r.returncode:
        raise CheckFailed("my_limit.py stops with an error: " + (out.strip().splitlines() or ["?"])[-1])
    pr = re.findall(r"^PROBE (\d+) (\d+) (\d+)$", r.stdout, re.M)
    c.ok(pr, "my_limit.py could not be run by the check (does it run with python3 my_limit.py?)")
    nh, ne, wrongway = (int(x) for x in pr[-1])
    found = re.findall(r"MAX_WIND_MPS\s*=\s*(\S+)", r.stdout)
    c.ok(found, "my_limit.py does not print a line `MAX_WIND_MPS = …` (its last line, Step 5)")
    if found[-1] in ("None", "0", "0.0"):
        raise CheckFailed(f"my_limit.py prints MAX_WIND_MPS = {found[-1]}: it never found a GO speed, even in "
                          "still air — compare seconds with seconds (endurance_s gives seconds) and add both legs")
    c.ok(nh >= 12, f"my_limit.py called your heading_for_track() {nh} times: the round trip must be computed with "
                   "it, two legs for each wind speed 0.0, 0.5, … up to the first NO-GO")
    c.ok(ne >= 1, "my_limit.py never calls your endurance_s(): compare the round trip with the quad's endurance")
    c.ok(wrongway == 0, "my_limit.py builds the wind blowing towards the north-east (+e, +n): that is where the wind "
                        "comes FROM. Wind from 020° blows TOWARDS 200°: for 6 m/s, print(we, wn) must show "
                        "-2.05 -5.64 (lesson §2, Step 5 hint 5)")
    try:
        printed = float(found[-1])
    except ValueError:
        raise CheckFailed(f"my_limit.py prints MAX_WIND_MPS = {found[-1]}: print a number")
    c.ok(abs(printed - 2.5) < 0.01, f"my_limit.py prints MAX_WIND_MPS = {printed:g}, which is not the limit. Check "
         "the wind (FROM 020° blows TOWARDS 200°), both legs, the 20 % reserve, seconds against seconds, and that "
         "you keep the last GO speed before the first NO-GO")
    (m,) = answers("MAX_WIND_MPS")
    m = number(m, "MAX_WIND_MPS")
    c.ok(abs(m - printed) < 0.01, "MAX_WIND_MPS in answers.py is not the value your my_limit.py prints")


@c.test("Step 5: the limit by algebra (ANALYTIC_WIND_MPS)",
        hint="Pure head/tailwind w: round trip = 2LV/(V² − w²) (the box after Step 4). Set it equal to the "
             "endurance in seconds and solve for w: V² − w² = 2LV / endurance. L = 7500 m, V = 12 m/s.")
def _():
    (a,) = answers("ANALYTIC_WIND_MPS")
    a = number(a, "ANALYTIC_WIND_MPS")
    c.ok(a != 0, "ANALYTIC_WIND_MPS is still 0")
    c.ok(abs(a - 2.70) <= 0.05, f"ANALYTIC_WIND_MPS = {a:g} does not solve 2LV/(V² − w²) = endurance — check the "
         "units (endurance in SECONDS, L in metres) and the algebra")


# ================================================================ Session 2 — classes
@c.test("TODO 6: Vehicle.__init__ stores its attributes and refuses impossible speeds",
        hint="Lesson §3: self.name = name, and the same for cruise_mps, max_speed_mps, battery_wh and power_w "
             "(exactly these names). Refuse cruise_mps <= 0 and max_speed_mps < cruise_mps BEFORE storing.")
def _():
    (V,) = veh("Vehicle")
    done(V.__init__, "Vehicle.__init__")
    v = run(V, "van", 3.5, 5, 200, 150)
    for attr, want in (("name", "van"), ("cruise_mps", 3.5), ("max_speed_mps", 5), ("battery_wh", 200),
                       ("power_w", 150)):
        c.ok(hasattr(v, attr), f"a Vehicle has no attribute {attr} — write self.{attr} = {attr} in __init__")
        c.eq(getattr(v, attr), want, f"Vehicle('van', 3.5, 5, 200, 150).{attr}")
    w = run(V, "kite", 9.0, 9.0, 10, 20)
    c.ok(w.max_speed_mps == 9.0, "max_speed_mps equal to cruise_mps is allowed")
    raises(V, "bad", 0.0, 5, 200, 150, what="Vehicle('bad', 0.0, 5, 200, 150) (cruise 0)")
    raises(V, "bad", -2.0, 5, 200, 150, what="Vehicle('bad', -2.0, 5, 200, 150)")
    raises(V, "bad", 6.0, 5, 200, 150, what="Vehicle('bad', 6.0, 5, 200, 150) (cruise above max speed)")


@c.test("TODO 7–8: Vehicle.endurance_s() and Vehicle.range_m() use THIS vehicle's values",
        hint="Lesson §3: inside a method, self.battery_wh is this vehicle's battery. endurance_s(self, reserve) "
             "calls the module function endurance_s(...); range_m: ground speed (cruise + wind along) × endurance, "
             "0.0 if the ground speed is <= 0.")
def _():
    (V,) = veh("Vehicle")
    done(V.endurance_s, "Vehicle.endurance_s")
    v = run(V, "van", 3.5, 5, 200, 150)
    big = run(V, "barge", 2.0, 3.0, 900, 100)
    c.near(run(v.endurance_s), 3840.0, 1e-6, "Vehicle('van', 3.5, 5, 200, 150).endurance_s()")
    e0 = run(v.endurance_s, 0.0)
    c.ok(not (isinstance(e0, (int, float)) and abs(e0 - 3840.0) < 1e-6),
         "Vehicle('van', 3.5, 5, 200, 150).endurance_s(0.0) gives the same as endurance_s() (3840 s): your method "
         "ignores its reserve — pass it on to the module function (Step 6 hint 4)")
    c.near(e0, 4800.0, 1e-6, "Vehicle('van', 3.5, 5, 200, 150).endurance_s(0.0)")
    c.near(run(big.endurance_s), 25920.0, 1e-6, "another vehicle's endurance_s() (does it use self.?)")
    done(V.range_m, "Vehicle.range_m")
    for args, want in (((), 13440.0), ((1.5,), 19200.0), ((-1,), 9600.0), ((-4,), 0.0), ((0.0, 0.0), 16800.0)):
        got = run(v.range_m, *args)
        c.ok(got is not None, f"van.range_m{args} returned None: every path needs a `return` (0.0 when stopped)")
        if args == (0.0, 0.0) and isinstance(got, (int, float)) and abs(got - 13440.0) < 1e-6:
            raise CheckFailed("range_m(0.0, 0.0) equals range_m(): range_m ignores its reserve — call "
                              "self.endurance_s(reserve) (Step 6 hint 4)")
        c.near(got, want, 1e-6, f"Vehicle('van', 3.5, 5, 200, 150).range_m{args if args else '()'}")


@c.test("TODO 9: FixedWing.__init__ — super() first, then the stall check",
        hint="Lesson §3: super().__init__(name, cruise_mps, max_speed_mps, battery_wh, power_w) builds the Vehicle "
             "part; then refuse cruise_mps <= stall_mps and store self.stall_mps.")
def _():
    FW, V = veh("FixedWing", "Vehicle")
    done(FW.__init__, "FixedWing.__init__")
    w = run(FW, "albatross", 25, 40, 300, 180, 14)
    c.ok(isinstance(w, V), "a FixedWing must be a Vehicle: class FixedWing(Vehicle)")
    c.ok(getattr(w, "stall_mps", None) == 14, "FixedWing(...).stall_mps is not stored")
    if not hasattr(w, "battery_wh"):
        v = run(V, "probe", 10.0, 12.0, 100.0, 100.0)
        if not hasattr(v, "battery_wh"):
            raise CheckFailed("Vehicle.__init__ (TODO 6) does not store self.battery_wh (a misspelt name?): fix "
                              "TODO 6 first")
        raise CheckFailed("the FixedWing has no battery_wh: call super().__init__(...) first")
    p = run(V, "probe", 10.0, 12.0, 100.0, 100.0)
    if abs(run(p.range_m, 0.0, 0.3) - run(p.range_m)) < 1e-6 or abs(run(p.endurance_s, 0.0) - run(p.endurance_s)) < 1e-6:
        raise CheckFailed("FixedWing inherits range_m and endurance_s from Vehicle, which ignore their reserve "
                          "(✘11): fix TODO 7–8 first; your FixedWing.__init__ is not the problem")
    c.near(run(w.endurance_s), 4800.0, 1e-6, "FixedWing('albatross', 25, 40, 300, 180, 14).endurance_s()")
    c.near(run(w.range_m, -5, 0.3), 84000.0, 1e-6, "….range_m(-5, 0.3)")
    raises(FW, "brick", 14, 40, 300, 180, 14, what="FixedWing('brick', 14, 40, 300, 180, 14) (cruise = stall)")
    raises(FW, "brick", 10, 40, 300, 180, 14, what="FixedWing('brick', 10, 40, 300, 180, 14) (cruise < stall)")
    raises(FW, "brick", 50, 40, 300, 180, 14,
           what="FixedWing('brick', 50, 40, 300, 180, 14) (cruise above max speed: Vehicle's own check, via super())")


@c.test("Step 7: inheritance — where methods come from, and what super() does",
        hint="Run python3 plan_mission.py fleet and print(wing). One class name per WHERE_… field; reasons go in "
             "the EXPLAIN_… fields. WHERE_ENDURANCE_FROM: the class whose code runs for "
             "wing.endurance_s(). SUPER_ERROR: the exception name on the LAST line of the traceback when the "
             "super().__init__ line is commented out (then put it back!).")
def _():
    where, err, why, wt, wd, pw, rf, wr = answers("WHERE_ENDURANCE_FROM", "SUPER_ERROR", "EXPLAIN_SUPER",
                                                  "WING_TRIP_MIN", "WING_DECISION", "PRINT_WING", "WHERE_REPR_FROM",
                                                  "EXPLAIN_REPR")
    one = lambda v: re.sub(r"[^a-z]", "", str(v).lower())
    c.ok(one(where) != "", "WHERE_ENDURANCE_FROM is empty")
    c.ok(one(where) in ("vehicle", "fixedwing"), f"WHERE_ENDURANCE_FROM = {where!r}: write ONE class name, no "
         "explanation")
    c.ok(one(where) == "vehicle", "WHERE_ENDURANCE_FROM: FixedWing does not define endurance_s() — look in its parent")
    c.ok(one(err) == "attributeerror",
         f"SUPER_ERROR = {err!r} is not the exception name on the last line of the traceback (one name, exactly)")
    explained("EXPLAIN_SUPER", why,
              ([r"super", r"parent", r"vehicle", r"__init__", r"init"], "which constructor did not run"),
              ([r"attribute", r"battery", r"self\.", r"power", r"cruise", r"name"], "what is missing in the object"))
    c.ok(re.sub(r"\s+", " ", str(pw)).strip().replace('"', "'") in ("FixedWing('wing', cruise 20 m/s)",
                                                                   "FixedWing('wing', cruise 20.0 m/s)"),
         f"PRINT_WING = {pw!r} is not the line print(wing) shows (copy it exactly)")
    c.ok(one(rf) in ("vehicle", "fixedwing"), f"WHERE_REPR_FROM = {rf!r}: write ONE class name (the reason goes in "
         "EXPLAIN_REPR)")
    c.ok(one(rf) == "vehicle", "WHERE_REPR_FROM: FixedWing defines no __repr__ — whose __repr__ runs?")
    explained("EXPLAIN_REPR", wr,
              ([r"type", r"class of", r"object", r"instance"], "what type(self) gives"),
              ([r"fixed", r"wing"], "which class the object is"), min_words=6)
    c.near(number(wt, "WING_TRIP_MIN"), 13.72, 0.05, "WING_TRIP_MIN (your heading_for_track at 20 m/s, two legs)")
    c.ok(one(wd) in ("go", "nogo"), f"WING_DECISION = {wd!r}: write \"GO\" or \"NO-GO\"")
    c.ok(one(wd) == "go", "WING_DECISION: compare the wing's round trip with its endurance (fleet prints it)")


# ================================================================ Session 2 — track.py with NumPy
def track_class():
    (T,) = need(quiet("navera_lite.track"), "Track")
    return T


@c.test("TODO 10: Track.add() keeps time order and stores floats",
        hint="Lesson §3: if the track is not empty and t_s <= the last time (self.t_s[-1]), raise ValueError; "
             "otherwise append float(t_s), float(e_m) and float(n_m) to the three lists.")
def _():
    T = track_class()
    done(T.add, "Track.add")
    first = T()
    try:
        first.add(10, 1, 2)
    except ValueError:
        raise CheckFailed("add() refuses the FIRST position of an empty track: test the time BEFORE you append, "
                          "and only when the track is not empty")
    tr = make_track(T, [(10, 1, 2), (12, "7", 9)])
    c.ok(len(tr) == 2, f"after two add() the track has {len(tr)} positions")
    c.ok(tr.t_s == [10.0, 12.0] and tr.e_m == [1.0, 7.0] and tr.n_m == [2.0, 9.0]
         and all(type(x) is float for x in tr.t_s + tr.e_m + tr.n_m),
         f"the lists are t_s={tr.t_s!r}, e_m={tr.e_m!r}, n_m={tr.n_m!r} — store float(...) of each value")
    raises(tr.add, 12, 0, 0, what="add(12, …) after time 12 (same time)")
    raises(tr.add, 11, 0, 0, what="add(11, …) after time 12 (going back)")
    c.ok(len(tr) == 2, "a refused position must not be added (raise BEFORE appending)")
    t2 = T()
    run(t2.add, -5, 0, 0)
    c.ok(len(t2) == 1, "the first add() must always be accepted, whatever its time")


@c.test("TODO 11–12: length_m() and speeds_mps() with NumPy, no Python loop",
        hint="Lesson §4: np.diff on the arrays from self.arrays(), np.hypot for the segment lengths; speeds = "
             "lengths / time differences. Fewer than 2 positions: 0.0 and an empty array.")
def _():
    import numpy as np
    T = track_class()
    done(T.length_m, "Track.length_m")
    a = make_track(T, [(10, 1, 1), (12, 7, 9), (13, 7, 9), (17, -5, 0), (18, -5, 30)])
    L = run(a.length_m)
    c.ok(isinstance(L, (int, float, np.floating)), f"length_m() returned {L!r}: a number is expected")
    c.near(L, 55.0, 1e-6, "length_m() of a 5-position track")
    one = make_track(T, [(0, 3, 3)])
    c.near(run(one.length_m), 0.0, 1e-12, "length_m() with one position")
    c.near(run(T().length_m), 0.0, 1e-12, "length_m() of an empty track")
    c.ok(vectorised(T, "length_m"), "length_m() uses a Python loop (for/while, a comprehension, map/sum/…, or a "
         "helper that loops): use np.diff, np.hypot and np.sum on whole arrays")
    done(T.speeds_mps, "Track.speeds_mps")
    s = run(a.speeds_mps)
    c.ok(isinstance(s, np.ndarray), f"speeds_mps() returned a {type(s).__name__}: a NumPy array is expected")
    c.ok(s.shape == (4,), f"speeds_mps() of 5 positions has shape {s.shape}: one speed per SEGMENT (n − 1)")
    if np.allclose(s, [5.0, 0.0, 15.0, 30.0]) or np.allclose(s, [10.0, 0.0, 15.0, 30.0]):
        raise CheckFailed("speeds_mps() gives the segment LENGTHS (m), not speeds: divide each one by its own time "
                          "difference (np.diff of t) — on this track the positions are not 1 s apart")
    c.ok(np.allclose(s, [5.0, 0.0, 3.75, 30.0]), f"speeds_mps() gives {np.round(s, 3).tolist()}: not the right speeds")
    e = run(one.speeds_mps)
    c.ok(isinstance(e, np.ndarray) and e.size == 0, f"speeds_mps() with one position must be an empty array, got {e!r}")
    c.ok(vectorised(T, "speeds_mps"), "speeds_mps() uses a Python loop (for/while, a comprehension, map/sum/…, or "
         "a helper that loops): use whole-array operations")


@c.test("TODO 13: glitches() lists the positions reached too fast",
        hint="Lesson §4: a boolean mask on the speeds, np.flatnonzero (or np.nonzero(...)[0]) for the indices — "
             "speed i ENDS at position i + 1 — then .tolist() for Python ints. Nothing too fast: [].")
def _():
    T = track_class()
    done(T.glitches, "Track.glitches")
    a = make_track(T, [(10, 1, 1), (12, 7, 9), (13, 7, 9), (17, -5, 0), (18, -5, 30)])
    import numpy as np
    g = run(a.glitches, 4)
    if isinstance(g, (list, tuple, np.ndarray)) and np.asarray(g).tolist() == [0, 3]:
        raise CheckFailed("glitches(4) gives the SPEED indices [0, 3]: list the positions REACHED (speed i ends at "
                          "position i + 1)")
    c.ok(isinstance(g, list), f"glitches() returned a {type(g).__name__}: return a list (end with .tolist())")
    c.ok(all(type(i) is int for i in g), f"glitches() returned {g!r}: the items must be Python ints (.tolist())")
    c.eq(g, [1, 4], "glitches(4) on a 5-position track")
    c.eq(run(a.glitches, 100), [], "glitches(100) (nothing that fast)")
    b = make_track(T, [(0, 0, 0), (1, 5, 5), (2, 60, 5), (3, 10, 6), (4, 15, 6), (5, 15, 80)])
    c.eq(run(b.glitches, 30), [2, 3, 5], "glitches(30) on another track")
    c.eq(run(b.glitches, 55), [5], "glitches(55): exactly 55 m/s is not faster than 55")
    if vectorised(T, "speeds_mps"):          # a loop inside speeds_mps() is ✘15's business, not glitches()'s
        c.ok(python_lines_run(T, "glitches", 50.0) < 100, "glitches() loops over the speeds in Python: use a mask "
             "and np.flatnonzero (lesson §4)")


@c.test("Step 9: the harbour survey in numbers",
        hint="python3 plan_mission.py track prints the length and the median; the number of positions and the "
             "maximum speed come from your own one-liner (len(tr), tr.speeds_mps().max()). "
             "EXPLAIN_MEDIAN: what does ONE extreme value do to a mean, and to a median?")
def _():
    n, L, med, mx, why = answers("TRACK_POINTS", "TRACK_LENGTH_M", "MEDIAN_SPEED_MPS", "MAX_SPEED_MPS",
                                 "EXPLAIN_MEDIAN")
    c.ok(number(n, "TRACK_POINTS") == 263, f"TRACK_POINTS = {n!r} is not the number of positions")
    c.near(number(L, "TRACK_LENGTH_M"), 3270.1, 0.2, "TRACK_LENGTH_M")
    c.near(number(med, "MEDIAN_SPEED_MPS"), 12.05, 0.01, "MEDIAN_SPEED_MPS")
    c.near(number(mx, "MAX_SPEED_MPS"), 54.34, 0.01, "MAX_SPEED_MPS")
    explained("EXPLAIN_MEDIAN", why,
              ([r"glitch", r"outlier", r"extreme", r"wrong", r"one", r"bad", r"spike", r"54"], "the effect of one extreme value"),
              ([r"median", r"middle", r"robust", r"typical", r"cruise", r"12"], "why the median describes the flight"))


@c.test("Step 10: the glitch hunt",
        hint="Run python3 plan_mission.py glitch and open out/glitch.png. Which of the listed positions is far from "
             "its neighbours? FLAGGED_AT_15: len(tr.glitches(15)). GLITCH_EXTRA_M: build a new Track without the "
             "bad position and compare the two lengths.")
def _():
    pg, g, bad, why, f15, f100, why2, extra = answers("PREDICT_GLITCH", "GLITCHES", "BAD_FIX_T_S", "EXPLAIN_GLITCH",
                                                      "FLAGGED_AT_15", "FLAGGED_AT_100", "EXPLAIN_THRESHOLD",
                                                      "GLITCH_EXTRA_M")
    predicted("PREDICT_GLITCH", pg)
    c.ok(isinstance(g, (list, tuple)) and list(g) == [150, 151],
         f"GLITCHES = {g!r} is not what glitch prints (a list, like [1, 2])")
    b = number(bad, "BAD_FIX_T_S")
    c.ok(b != 151, "BAD_FIX_T_S = 151: look at out/glitch.png — which listed point is far from BOTH its neighbours?")
    c.ok(b == 150, f"BAD_FIX_T_S = {bad!r} is not the time of the wrong fix")
    explained("EXPLAIN_GLITCH", why,
              ([r"two", r"\b2\b", r"both", r"twice", r"\btoo\b", r"also", r"as well", r"second", r"each"],
               "why one wrong fix makes two fast segments"),
              ([r"into", r"out", r"leav", r"arriv", r"to and from", r"back", r"next", r"after", r"before",
                r"return", r"previous", r"neighbo"],
               "the segment into and the segment out of the wrong fix"))
    c.ok(number(f15, "FLAGGED_AT_15") == 33, f"FLAGGED_AT_15 = {f15!r} is not len(glitches(15)) on the harbour track")
    c.ok(isinstance(f100, (list, tuple)) and len(f100) == 0 and f100 is not None,
         f"FLAGGED_AT_100 = {f100!r} is not what tr.glitches(100) prints (a list)")
    explained("EXPLAIN_THRESHOLD", why2,
              ([r"false", r"honest", r"noise", r"good", r"real", r"too many", r"alarm"], "what a low threshold costs"),
              ([r"max", r"physic", r"vehicle", r"cannot", r"can't", r"faster", r"20"],
               "why the vehicle's maximum speed is the right limit"))
    c.ok(not 1400 < number(extra, "GLITCH_EXTRA_M") < 1500, "GLITCH_EXTRA_M ≈ 1451: your new track stops at the "
         "bad fix — `break` leaves the loop, `continue` skips only that position")
    c.near(number(extra, "GLITCH_EXTRA_M"), 90.9, 1.0, "GLITCH_EXTRA_M")


@c.test("Step 11: a loop against NumPy",
        hint="Write PREDICT_SPEEDUP before you run python3 plan_mission.py speed, then copy the first "
             "'times faster' number into SPEEDUP_X (it depends on the computer: any measured value is fine).")
def _():
    p, x = answers("PREDICT_SPEEDUP", "SPEEDUP_X")
    predicted("PREDICT_SPEEDUP", p)
    x = number(x, "SPEEDUP_X")
    c.ok(x > 1, f"SPEEDUP_X = {x:g}: run python3 plan_mission.py speed and copy its 'times faster' number")


c.milestone("flight-planner", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "Step 3–4:", "Step 5:",
            label="Session 1 complete: Flight planner badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("track-detective", "TODO", "Step", label="Mission complete: Flight planner and Track detective badges earned")

c.run()
