import contextlib
import io
import re

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        m = load_student("answers.py")
    return need(m, *names)


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


@c.test("hello_navera.py runs without errors",
        hint="Run `python3 hello_navera.py` and read the LAST line of the error. A missing quote is the usual reason.")
def _():
    code, out = sh("python3 hello_navera.py", timeout=20)
    c.ok(code == 0, "the program stopped with an error: " + last_line(out))


@c.test("the mission card has your name, a vehicle and your city",
        hint='Replace each "???" between the quotes. The vehicle is one of: drone, car, boat, robot (lower case).')
def _():
    with contextlib.redirect_stdout(io.StringIO()):
        m = load_student("hello_navera.py")
    name, vehicle, city = need(m, "PILOT_NAME", "FAVOURITE_VEHICLE", "CITY")
    c.ok(isinstance(name, str) and name.strip() not in ("", "???"), 'PILOT_NAME is still "???"')
    c.ok(str(vehicle).strip().lower() in ("drone", "car", "boat", "robot"), f'FAVOURITE_VEHICLE is "{vehicle}"')
    c.ok(str(city).strip() not in ("", "???"), 'CITY is still "???"')


@c.test("Step 1: the computer (ARCH, CPU_CORES)",
        hint="Run the two commands `uname -m` and `nproc` in the terminal and copy what they print.")
def _():
    arch, cores = answers("ARCH", "CPU_CORES")
    _, real_arch = sh("uname -m", timeout=10)
    _, real_cores = sh("nproc", timeout=10)
    c.ok(str(arch).strip() != "", "ARCH is still empty")
    c.ok(str(arch).strip() == real_arch.strip(), f"ARCH = {arch!r} is not what `uname -m` prints")
    c.ok(int(number(cores, "CPU_CORES")) == int(real_cores.strip()), f"CPU_CORES = {cores!r} is not what `nproc` prints")


@c.test("Step 3: values read in your NAVERA copy",
        hint="Open estimator_params.yaml (link in Step 3) and find gps_timeout_s and fix_max_sigma_m; "
             "grep SOURCE_ in PositionEstimate.msg.")
def _():
    t, s, d = answers("GPS_TIMEOUT_S", "FIX_MAX_SIGMA_M", "SOURCE_DAY_VISION")
    c.ok(number(t, "GPS_TIMEOUT_S") == 3.0, f"GPS_TIMEOUT_S = {t!r} is not the value in estimator_params.yaml")
    c.ok(number(s, "FIX_MAX_SIGMA_M") == 25.0, f"FIX_MAX_SIGMA_M = {s!r} is not the value in estimator_params.yaml")
    c.ok(number(d, "SOURCE_DAY_VISION") == 2, f"SOURCE_DAY_VISION = {d!r} is not the number in PositionEstimate.msg")


@c.test("Step 4: the clock bias found by the solver (default settings)",
        hint="Run python3 gnss_fix.py with the settings it came with and copy the line 'clock bias found'. "
             "It is close to c × 0.5 µs, but not exactly: the noise moves it.")
def _():
    (b,) = answers("BIAS_FOUND_M")
    c.near(number(b, "BIAS_FOUND_M"), 148.1, 0.15, "BIAS_FOUND_M")


@c.test("Step 4: 4 satellites — horizontal error and residual",
        hint="Set USE_SATELLITES = 4, save, run, copy 'horizontal error' and 'residual RMS'. Think about why the "
             "residual is what it is.")
def _():
    e, r = answers("H_ERR_4_SATS_M", "RESID_4_SATS_M")
    c.near(number(e, "H_ERR_4_SATS_M"), 4.34, 0.1, "H_ERR_4_SATS_M")
    c.near(number(r, "RESID_4_SATS_M"), 0.0, 0.05, "RESID_4_SATS_M")


@c.test("Step 4: the spoofed fix — horizontal error and residual",
        hint="USE_SATELLITES = 8 and SPOOF_EAST_M = 500.0 (other settings as delivered), run, copy the two lines.")
def _():
    e, r = answers("SPOOF_H_ERR_M", "SPOOF_RESID_M")
    c.near(number(e, "SPOOF_H_ERR_M"), 499.48, 0.15, "SPOOF_H_ERR_M")
    c.near(number(r, "SPOOF_RESID_M"), 1.78, 0.06, "SPOOF_RESID_M")


@c.test("gnss_fix.py still runs",
        hint="Run `python3 gnss_fix.py`. If it fails, look at the last line: a setting must stay a plain number.")
def _():
    code, out = sh("python3 gnss_fix.py", timeout=30)
    c.ok(code == 0, "gnss_fix.py stopped with an error: " + last_line(out))


@c.test("Step 5: the arbiter's GPS jump gate",
        hint="Refuse if distance > v_max × Δt + margin. Put the numbers of answers.py in that formula.")
def _():
    (g,) = answers("GATE_M")
    c.ok(number(g, "GATE_M") != 0, "GATE_M is still 0")
    c.near(number(g, "GATE_M"), 250.0, 0.01, "GATE_M")


QUIZ = {"Q1": ("b", "Count the unknowns in the pseudorange equation of the course."),
        "Q2": ("b", "How many equations, how many unknowns? Can a wrong measurement show up in the residual then?"),
        "Q3": ("a", "Look at the residual in your spoofed run, and at the end of section 2 of the course."),
        "Q4": ("c", "See the threat table of the course."),
        "Q5": ("b", "Section 3 of the course: the arbiter is a node of navera_estimator."),
        "Q6": ("a", "Section 3 of the course: the output looks like a GPS receiver to the autopilot."),
        "Q7": ("b", "Read the FIX / DEGRADED / NO_FIX table of the course.")}


def quiz(names):
    vals = answers(*names)
    wrong = []
    for q, v in zip(names, vals):
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        if v != QUIZ[q][0]:
            wrong.append(q)
    if wrong:
        raise CheckFailed("not right yet: " + ", ".join(wrong) + " — hint: " + " / ".join(QUIZ[q][1] for q in wrong))


@c.test("Step 7: quiz on GNSS (Q1–Q4)", hint="Each wrong answer comes with its own hint above.")
def _():
    quiz(["Q1", "Q2", "Q3", "Q4"])


@c.test("Step 7: quiz on NAVERA (Q5–Q7)", hint="Each wrong answer comes with its own hint above.")
def _():
    quiz(["Q5", "Q6", "Q7"])


@c.test("Step 6: threats.md — four threats analysed in your own words",
        hint="Keep the four ## headings, replace every '(write here)', write 3–5 sentences per threat (at least "
             "150 words in total) and name what NAVERA does about it.")
def _():
    c.file_exists("threats.md")
    with open("threats.md") as f:
        text = f.read()
    low = text.lower()
    c.ok("(write here)" not in low, 'threats.md still contains "(write here)"')
    parts = re.split(r"^##\s+", text, flags=re.M)
    sections = {p.splitlines()[0].strip().lower(): p for p in parts[1:]}
    for h in ("outage", "jamming", "spoofing", "meaconing"):
        body = next((v for k, v in sections.items() if k.startswith(h)), None)
        c.ok(body is not None, f'threats.md has no section "## {h.capitalize()}"')
        n = len(re.findall(r"[A-Za-z]{2,}", body)) - 1
        c.ok(n >= 25, f'the section "{h.capitalize()}" has only {n} words — write 3–5 sentences')
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    c.ok(words >= 150, f"threats.md has about {words} words — write at least 150")
    c.ok(any(w in low for w in ("arbiter", "estimator", "vision", "independent")),
         "say which NAVERA source or rule helps (e.g. the arbiter, vision…)")


c.run()
