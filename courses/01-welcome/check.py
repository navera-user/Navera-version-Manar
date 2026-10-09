import contextlib
import io
import re
import signal

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()


def quiet_load(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def answers(*names):
    return need(quiet_load("answers.py"), *names)


def functions(*names):
    return need(quiet_load("beacons.py"), *names)


def number(v, name):
    if isinstance(v, bool):
        raise CheckFailed(f"{name} should be a number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number (no quotes), got {v!r}")


def last_line(out):
    lines = [l for l in out.strip().splitlines() if l.strip()]
    return lines[-1] if lines else "(no output)"


def run(fn, *args, seconds=40):
    """Call a student function; a crash or an endless loop becomes a clear ✘."""
    def too_long(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, too_long)
    signal.alarm(seconds)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)
    except TimeoutError:
        raise CheckFailed(f"{fn.__name__}() did not finish in {seconds} s — is a loop endless?")
    except Exception as e:
        raise CheckFailed(f"{fn.__name__}() stopped with {type(e).__name__}: {e}")
    finally:
        signal.alarm(0)


def point(v, n, what):
    if not isinstance(v, (tuple, list)) or len(v) != n or not all(isinstance(x, (int, float)) for x in v):
        raise CheckFailed(f"{what} should return {n} numbers like {'(x, y)' if n == 2 else '(x, y, bias)'}, got {v!r}")
    return [float(x) for x in v]


def words(s):
    return re.findall(r"[A-Za-zÀ-ÿ']{2,}", str(s))


def explained(name, value, keywords, need_what):
    c.ok(isinstance(value, str) and value.strip() != "", f"{name} is still empty")
    c.ok(len(words(value)) >= 8, f"{name} is very short — explain in one or two full sentences")
    low = value.lower()
    c.ok(any(k in low for k in keywords), f"{name} does not mention {need_what} yet")


# ---------------------------------------------------------------- steps 1–3
@c.test("hello_navera.py runs, with your name, a vehicle and your city",
        hint='Replace each "???" between the quotes; the vehicle is drone, car, boat or robot. '
             "If it does not run, read the LAST line of the error.")
def _():
    code, out = sh("python3 hello_navera.py", timeout=20)
    c.ok(code == 0, "the program stopped with an error: " + last_line(out))
    name, vehicle, city = need(quiet_load("hello_navera.py"), "PILOT_NAME", "FAVOURITE_VEHICLE", "CITY")
    c.ok(str(name).strip() not in ("", "???"), 'PILOT_NAME is still "???"')
    c.ok(str(vehicle).strip().lower() in ("drone", "car", "boat", "robot"), f'FAVOURITE_VEHICLE is "{vehicle}"')
    c.ok(str(city).strip() not in ("", "???"), 'CITY is still "???"')


@c.test("Step 1: the computer (ARCH, CPU_CORES)",
        hint='Run `uname -m` and `nproc` in the terminal and copy what they print. Text needs quotes: '
             'ARCH = "aarch64". A NameError in answers.py almost always means missing quotes.')
def _():
    arch, cores = answers("ARCH", "CPU_CORES")
    _, real_arch = sh("uname -m", timeout=10)
    _, real_cores = sh("nproc", timeout=10)
    c.ok(str(arch).strip() == real_arch.strip(), f"ARCH = {arch!r} is not what `uname -m` prints")
    c.ok(int(number(cores, "CPU_CORES")) == int(real_cores.strip()), f"CPU_CORES = {cores!r} is not what `nproc` prints")


@c.test("Step 3: NAVERA's settings (V_MAX_MPS, MARGIN_M, GPS_TIMEOUT_S)",
        hint="Open estimator_params.yaml (link in Step 3) and find max_speed_mps, gps_jump_margin_m and gps_timeout_s.")
def _():
    v, m, t = answers("V_MAX_MPS", "MARGIN_M", "GPS_TIMEOUT_S")
    c.ok(number(v, "V_MAX_MPS") == 100.0, f"V_MAX_MPS = {v!r} is not max_speed_mps of the file")
    c.ok(number(m, "MARGIN_M") == 50.0, f"MARGIN_M = {m!r} is not gps_jump_margin_m of the file")
    c.ok(number(t, "GPS_TIMEOUT_S") == 3.0, f"GPS_TIMEOUT_S = {t!r} is not gps_timeout_s of the file")


# ---------------------------------------------------------------- your functions, on new numbers
BEACONS = [(1, 1), (9, 2), (4, 9)]                         # not the lab's beacons
CLEAN = [5.859181, 3.275668, 5.738467]                     # measured from (6.2, 3.7)
LATE = [6.309181, 3.725668, 6.188467]                      # same, with a bias of 0.45 km


@c.test("TODO 1: distance() works for any two points",
        hint="Pythagoras: the square root of (difference of x)² + (difference of y)². Use p[0], p[1], q[0], q[1].")
def _():
    (distance,) = functions("distance")
    c.near(run(distance, (0, 0), (3, 4)), 5.0, 1e-6, "distance((0, 0), (3, 4))")
    c.near(run(distance, (-2, 5), (4, -3)), 10.0, 1e-6, "distance((-2, 5), (4, -3))")
    c.near(run(distance, (1.5, 2.5), (1.5, 2.5)), 0.0, 1e-9, "distance between a point and itself")


@c.test("TODO 2: mismatch() works for other beacons, with and without a bias",
        hint="For each beacon: (distance + bias − measured)², and add them all. Return the total AFTER the loop.")
def _():
    (mismatch,) = functions("mismatch")
    c.near(run(mismatch, (4, 4), [(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708]), 1.4086, 0.001,
           "mismatch at (4, 4), the course example")
    c.near(run(mismatch, (5, 5), BEACONS, CLEAN), 5.62365, 0.0005, "mismatch on other beacons")
    c.near(run(mismatch, (5, 5), BEACONS, LATE, 0.2), 5.85783, 0.0005, "mismatch with bias = 0.2")
    c.near(run(mismatch, (6.2, 3.7), BEACONS, LATE, 0.45), 0.0, 1e-6, "mismatch at the true point with the right bias")


@c.test("TODO 3: find_position() finds a position it has never seen",
        hint="Two loops over range(101), x = i / 10 and y = j / 10; keep the point with the smallest mismatch "
             "(course example: the square closest to 20).")
def _():
    (find_position,) = functions("find_position")
    p = point(run(find_position, BEACONS, CLEAN), 2, "find_position")
    c.ok(abs(p[0] - 6.2) < 0.01 and abs(p[1] - 3.7) < 0.01,
         f"find_position gives {tuple(p)} for beacons it has not seen before — that is not the right point")


@c.test("TODO 4: find_position_and_bias() finds the position AND the clock bias",
        hint="A third loop inside the two others: bias = k / 20 for k in range(21). Give the bias to mismatch(). "
             "Return (x, y, bias).")
def _():
    (fpb,) = functions("find_position_and_bias")
    p = point(run(fpb, BEACONS, LATE, seconds=60), 3, "find_position_and_bias")
    c.ok(abs(p[0] - 6.2) < 0.01 and abs(p[1] - 3.7) < 0.01, f"the position found is ({p[0]}, {p[1]}) — not the right point")
    c.ok(abs(p[2] - 0.45) < 0.01, f"the bias found is {p[2]} — not the right bias")


@c.test("TODO 5: spoof_measurements() computes what a receiver at the fake position would measure",
        hint="For each beacon: distance(fake_position, beacon) + bias. Return a list, one value per beacon.")
def _():
    (spoof,) = functions("spoof_measurements")
    got = run(spoof, [(2, 7), (8, 1), (5, 5)], (1.5, 2.5), 0.25)
    c.ok(isinstance(got, (list, tuple)) and len(got) == 3, f"it should return 3 values (one per beacon), got {got!r}")
    for g, want, n in zip(got, [4.777693, 6.920832, 4.551163], "123"):
        c.near(g, want, 1e-4, f"value {n}")


@c.test("TODO 6: gate_ok() applies the jump gate",
        hint="Accepted when distance(last, new) <= v_max × elapsed + margin. Exactly on the limit counts as accepted.")
def _():
    (gate_ok,) = functions("gate_ok")
    cases = [((0, 0), (120, 0), 1.0, 100.0, 50.0, True), ((0, 0), (500, 0), 1.0, 100.0, 50.0, False),
             ((0, 0), (300, 400), 4.5, 100.0, 50.0, True), ((0, 0), (300, 400), 4.4, 100.0, 50.0, False),
             ((10, 10), (40, 50), 1.0, 30.0, 20.0, True), ((0, 0), (0, 40), 0.5, 30.0, 20.0, False)]
    for last, new, el, v, m, want in cases:
        got = run(gate_ok, last, new, el, v, m)
        c.ok(got in (True, False), f"gate_ok should return True or False, got {got!r}")
        c.ok(got == want, f"gate_ok({last}, {new}, elapsed {el} s, v_max {v}, margin {m}) gives {got}")


@c.test("TODO 7: count_refused() follows the arbiter's rule",
        hint="Compare each fix with the LAST ACCEPTED fix. The elapsed time grows by dt_s at each fix and goes back "
             "to 0 only when a fix is accepted.")
def _():
    (count_refused,) = functions("count_refused")
    c.eq(run(count_refused, [(0, 0)] + [(500, 0)] * 6, 1.0, 100.0, 50.0), 4, "the course's 500 m jump")
    fixes = [(0, 0), (10, 0), (30, 0), (31, 0), (80, 0), (82, 0), (84, 0), (10, 0)]
    got = run(count_refused, fixes, 0.5, 30.0, 10.0)
    c.ok(got == 3, f"on a test with other fixes (dt 0.5 s, v_max 30, margin 10) it gives {got!r} — not the "
                   "right count. Walk through it by hand: when does the time since the last accepted fix reset?")


# ---------------------------------------------------------------- what you saw and why
@c.test("Step 6: the late clock — prediction, error and explanation",
        hint="Run python3 where_am_i.py clock. CLOCK_ERROR_M is the 'distance from the true position' of part 1). "
             "In EXPLAIN_CLOCK, say what the bias does to every distance.")
def _():
    pred, err, why = answers("PREDICT_CLOCK", "CLOCK_ERROR_M", "EXPLAIN_CLOCK")
    c.ok(str(pred).strip() != "", "PREDICT_CLOCK is empty — write your guess (any guess is fine)")
    c.near(number(err, "CLOCK_ERROR_M"), 141, 2, "CLOCK_ERROR_M")
    explained("EXPLAIN_CLOCK", why, ("bias", "clock"), "the clock bias")
    c.ok(any(k in why.lower() for k in ("every", "all", "each", "same")),
         "EXPLAIN_CLOCK should say that the bias changes every distance (all of them, by the same amount)")


@c.test("Step 7: two beacons — prediction and explanation",
        hint="Run python3 where_am_i.py two. Count: how many unknowns (x, y, bias), how many measurements? "
             "Then: how many unknowns for a real GPS, so how many satellites?")
def _():
    pred, why = answers("PREDICT_TWO", "EXPLAIN_TWO")
    c.ok(str(pred).strip() != "", "PREDICT_TWO is empty — write your guess (any guess is fine)")
    explained("EXPLAIN_TWO", why, ("unknown",), "the unknowns")
    c.ok(any(k in why.lower() for k in ("4", "four")), "EXPLAIN_TWO should say how many satellites a real GPS needs")


@c.test("Step 8: the spoofer — prediction and explanation",
        hint="Run python3 where_am_i.py spoof. Why does the fake position explain the measurements perfectly? "
             "Can the receiver tell, using only its own measurements?")
def _():
    pred, why = answers("PREDICT_SPOOF", "EXPLAIN_SPOOF")
    c.ok(str(pred).strip() != "", "PREDICT_SPOOF is empty — write your guess (any guess is fine)")
    explained("EXPLAIN_SPOOF", why, ("cannot", "can't", "can not", "not ", "no ", "nothing", "never"),
              "whether the receiver can tell")


@c.test("Step 9: the jump gate against the two attacks",
        hint="Run python3 where_am_i.py gate and copy the two count_refused results. In EXPLAIN_GATE, say what NAVERA "
             "compares GPS with (course §4).")
def _():
    pred, jump, drift, why = answers("PREDICT_GATE", "JUMP_REFUSED", "DRIFT_REFUSED", "EXPLAIN_GATE")
    c.ok(str(pred).strip() != "", "PREDICT_GATE is empty — write your guess (any guess is fine)")
    c.ok(number(jump, "JUMP_REFUSED") == 2, f"JUMP_REFUSED = {jump!r} is not what the gate run gives for attack A")
    c.ok(number(drift, "DRIFT_REFUSED") == 0, f"DRIFT_REFUSED = {drift!r} is not what the gate run gives for attack B")
    explained("EXPLAIN_GATE", why, ("vision", "camera", "independent", "agree", "compare"),
              "what NAVERA compares GPS with")


@c.test("Step 10: threats.md — four threats, in your own words, with one of your numbers",
        hint="Keep the four ## headings, replace every '(write here)', 2–4 sentences each (100 words in total), "
             "and quote at least one number from your runs.")
def _():
    c.file_exists("threats.md")
    text = open("threats.md").read()
    parts = re.split(r"^##\s+", text, flags=re.M)
    c.ok("(write here)" not in "".join(parts[1:]).lower(), 'a section of threats.md still contains "(write here)"')
    sections = {p.splitlines()[0].strip().lower(): p for p in parts[1:]}
    for h in ("outage", "jamming", "spoofing", "meaconing"):
        body = next((v for k, v in sections.items() if k.startswith(h)), None)
        c.ok(body is not None, f'threats.md has no section "## {h.capitalize()}"')
        c.ok(len(words(body)) - 1 >= 15, f'the section "{h.capitalize()}" is too short — write 2–4 sentences')
    body = "".join(parts[1:])
    c.ok(len(words(body)) >= 100, f"threats.md has about {len(words(body))} words of your own — write at least 100")
    c.ok(re.search(r"\d", body), "quote at least one number from your own lab runs")


c.run()
