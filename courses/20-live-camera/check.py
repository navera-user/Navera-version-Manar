import contextlib
import io
import json
import math
import re

import numpy as np

from academy_check import (Background, CheckFailed, Checker, explained, hidden, is_stub, load_student, need,
                           predicted, run, wait_for_messages)

c = Checker()

# ---- unseen inputs (the lab never uses them) and their expected values, from the course reference --------------
STREAM_A = [100.0, 100.033, 100.067, 100.1, 100.2, 100.234, 100.267, 100.334, 100.368]
STREAM_B = [20.0, 20.040002, 20.08045, 20.120039, 20.158703, 20.198021, 20.236533, 20.276624, 20.318634, 20.357896,
            20.396965, 20.4377, 20.478235, 20.518393, 20.556997, 20.596954, 20.637996, 20.67598, 20.715294, 20.752442,
            20.790508, 20.827745, 20.867392, 20.905491, 20.945898, 20.986133, 21.025853, 21.062078, 21.10127, 21.141197,
            21.181367, 21.219072, 21.258355, 21.296887, 21.335674, 21.377265, 21.416054, 21.456005, 21.976005, 22.01513,
            22.054962, 22.095128, 22.135224, 22.173386, 22.2135, 22.255539, 22.293218, 22.334507, 22.374686, 22.413724,
            22.456724, 22.497868, 22.536069, 22.576181, 22.617046, 22.656762, 22.697787, 22.737687, 22.778688, 22.820846,
            22.859832]
STATS_A = {"n": 9, "fps": 21.739130, "median_ms": 34.0, "jitter_ms": 23.173260, "max_gap_ms": 100.0, "dropped": 3}
STATS_B = {"n": 61, "fps": 20.980253, "median_ms": 39.866, "jitter_ms": 61.506780, "max_gap_ms": 520.0, "dropped": 12}
STATS_C = {"n": 2, "fps": 20.0, "median_ms": 50.0, "jitter_ms": 0.0, "max_gap_ms": 50.0, "dropped": 0}


def bench2():
    """An unseen flash bench: 5 flashes (the first one before any frame, the third one not seen, the fourth one with
    half-lit frames, the second one with a frame exactly at the midpoint)."""
    fl = [9.0, 10.0, 11.5, 13.0, 14.5]
    ft = [round(9.5 + 0.04 * k, 4) for k in range(143)]
    fb = []
    for t in ft:
        b = 25.0
        if 10.13 <= t < 10.6:
            b = 230.0
        if abs(t - 10.10) < 1e-9:
            b = 127.5                                   # exactly the midpoint (25 + 230) / 2: not "brighter"
        if 11.65 <= t < 12.0:
            b = 38.0                                    # a rise of 13 < 20: not seen
        if 13.11 <= t < 13.5:
            b = 210.0
        if 13.07 <= t < 13.11:
            b = 100.0                                   # half lit, below (25 + 210) / 2
        if 14.62 <= t < 15.0:
            b = 200.0
        fb.append(b)
    return fl, ft, fb


DELAYS2 = [None, 0.14, None, 0.14, 0.12]


def qe(roll_deg, pitch_deg, yaw_deg):
    """ROS ZYX Euler angles → quaternion (x, y, z, w), built here so the check never trusts the student's copy."""
    cr, sr = math.cos(math.radians(roll_deg) / 2), math.sin(math.radians(roll_deg) / 2)
    cp, sp = math.cos(math.radians(pitch_deg) / 2), math.sin(math.radians(pitch_deg) / 2)
    cy, sy = math.cos(math.radians(yaw_deg) / 2), math.sin(math.radians(yaw_deg) / 2)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy)


IT = [1.00, 1.02, 1.04, 1.30, 1.32]
IQ = [qe(0, 0, 30), tuple(-v for v in qe(1, 0, 31)), qe(2, 1, 32), qe(15, 3, 45), qe(16, 3, 46)]   # one stored as −q
ATT = {1.005: [0.002102319, 0.000583025, 0.26092506, 0.965356594],
       1.03: [-0.01139025, -0.007765032, -0.271341045, -0.962384541],
       1.17: [0.062690534, 0.043690996, 0.326804998, 0.941997605],
       1.25: [0.092249702, 0.062332176, 0.357416882, 0.927285212],
       0.85: [0.0, 0.0, 0.258819045, 0.965925826],
       1.50: [0.117937006, 0.078222136, 0.383442453, 0.912657682],
       1.04: [0.014370698, 0.013197559, 0.275438482, 0.961120674],
       1.315: [0.116108668, 0.077145281, 0.381617708, 0.913747945]}
ATT_HOLE08 = [0.001796404, 0.001649756, 0.260906177, 0.965361082]      # 2.1 s in a 2.0–2.8 s hole
ATT_F_INVERTED = [0.006306957, 0.001749074, 0.265129697, 0.964190545]     # 1.005 with the fraction upside down

DEFAULTS = {"latency_s": 0.138, "max_gap_s": 0.2, "rate_window_s": 0.2, "max_rate_dps": 30.0, "max_tilt_deg": 45.0,
            "gimbal": False}
CFG2 = dict(DEFAULTS, max_rate_dps=20.0, max_tilt_deg=30.0)
Q35 = qe(0, -35, 80)                     # nose 35° up: the camera axis 35° from straight down
USABLE = [("level, 19.9 °/s", ((0.0, 0.0, 0.0, 1.0), 19.9, CFG2), (True, "ok")),
          ("level, exactly 20.0 °/s", ((0.0, 0.0, 0.0, 1.0), 20.0, CFG2), (True, "ok")),
          ("level, 25.67 °/s", ((0.0, 0.0, 0.0, 1.0), 25.67, CFG2), (False, "turning 25.7 °/s > 20.0 °/s")),
          ("tilted 35°, 5 °/s", (Q35, 5.0, CFG2), (False, "tilted 35.0° > 30.0°")),
          ("tilted 35° AND 25.67 °/s", (Q35, 25.67, CFG2), (False, "turning 25.7 °/s > 20.0 °/s")),
          ("level, rate None", ((0.0, 0.0, 0.0, 1.0), None, CFG2), (False, "rotation rate unknown")),
          ("no attitude, gimbal", (None, 5.0, dict(CFG2, gimbal=True)), (False, "no attitude at the exposure")),
          ("tilted 35°, rate None, gimbal", (Q35, None, dict(CFG2, gimbal=True)), (True, "ok")),
          ("tilted 29.96°, 3 °/s", (qe(0, -29.96, 10), 3.0, CFG2), (True, "ok"))]

# ---- the lab's data, measured with the course reference (lab Steps 1–9) -------------------------------------------
FPS_LOG, DROPPED_LOG, JITTER_40S_MS, JITTER_60S_MS = 28.2655, 32, 5.00, 9.72
DELAY_MEDIAN_MS, DELAY_MIN_MS, UNSEEN_FLASH, OUTLIER_FLASH = 156.3, 141.1, 8, 14
PHASE_SLOPE = -0.990                      # phase.py on the bench, flash 14 left out (r = −0.995)
T_MS, SCREEN_MS = 1000.0 / 28.8, 20.0
BUDGET_500_M, ALONG_60_M, DT_FOR_30M_S = 13.6388, 2.0833, 0.4524
STEADY_RATE_DPS = 12.9805                 # g·tan 30° / 25 m/s
BANK48_RATE_DPS = 24.9697                 # g·tan 48° / 25 m/s


def tm():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.timing", fresh=True)


def only_stub(func, path):
    """True if the function's body is ONLY the starter's stub (a docstring plus `return None` / `raise …`). Code
    written above the stub line counts as written (the stub below it is never reached). The student's file is read as
    text (never executed here)."""
    import ast
    if not is_stub(func):
        return False
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (OSError, SyntaxError, ValueError):
        return True
    name = getattr(func, "__name__", "")
    defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    if not defs:
        return True
    body = [x for x in defs[-1].body if not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant))]
    if len(body) != 1:
        return False
    x = body[0]
    return isinstance(x, ast.Raise) or (isinstance(x, ast.Return) and (x.value is None or (
        isinstance(x.value, ast.Constant) and x.value.value is None)))


def functions(*names, module=None, path="navera_lite/timing.py"):
    fns = need(module or tm(), *names)
    for f in fns:
        if only_stub(f, path):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in {path})")
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


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, (tuple, list, dict)) or (hasattr(v, "shape") and getattr(v, "shape", ()) != ()):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


TIPS = [("phase.py", " — no frame at or before the flash? flash_phase must return None then (its docstring's second "
                     "example; lab Step 3b, hint 2)"),
        ("not supported between instances of 'NoneType'", " — a value is None and is compared: test `is None` "
                                                           "first (usable: rate_dps can be None — lab Step 8, hint 6)"),
        ("list index out of range", " — an index past the end: with bisect, i can be 0 or len(…) (lab Step 6, hints "
                                    "1 and 4)"),
        ("index out of bounds", " — an index past the end: with bisect, i can be 0 or len(…) (lab Step 6, hints 1 "
                                "and 4)")]


def go(fn, *args, **kw):
    try:
        return run(fn, *args, seconds=20, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def camera_yaml():
    """The student's camera.yaml as a dict (read as text: never executed)."""
    import yaml
    try:
        with open("camera.yaml") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise CheckFailed("camera.yaml is missing in your lesson folder: restore it from the starter (lab Step 4)")
    except yaml.YAMLError as e:
        raise CheckFailed(f"camera.yaml cannot be read: {str(e).splitlines()[0]}")
    if not isinstance(data, dict):
        raise CheckFailed("camera.yaml must hold `key: value` lines")
    return data


def my_latency():
    lat = camera_yaml().get("latency_s", 0.138)
    if isinstance(lat, bool) or not isinstance(lat, (int, float)):
        raise CheckFailed(f"camera.yaml: latency_s must be a number of seconds, got {lat!r}")
    return float(lat)


def table():
    return json.loads(hidden("flight_table.json"))


def row_for(lat):
    t = table()["by_latency"]
    key = f"{round(lat, 3):.3f}"
    if key not in t:
        raise CheckFailed(f"camera.yaml: latency_s = {lat} is outside 0.000–0.200 s: is it in seconds?")
    return t[key]


def rules_are_defaults():
    d = camera_yaml()
    for k in ("max_gap_s", "rate_window_s", "max_rate_dps", "max_tilt_deg", "gimbal"):
        if k in d and d[k] != DEFAULTS[k]:
            raise CheckFailed(f"camera.yaml: {k} is {d[k]!r}, the lab's value is {DEFAULTS[k]!r} — restore it (only "
                              "latency_s is yours to change), then run `python3 run_timing.py turn` again")


def stats_ok(got, want, label):
    if not isinstance(got, dict):
        raise CheckFailed(f"frame_stats({label}) must return a dict, got {got!r}")
    keys = set(want)
    if set(got) != keys:
        raise CheckFailed(f"frame_stats() must return exactly the keys {sorted(keys)}, got {sorted(got)}")
    for k in ("n", "dropped"):
        if isinstance(got[k], bool) or not isinstance(got[k], (int, np.integer)):
            raise CheckFailed(f"frame_stats(): {k} must be a whole number (int), got {got[k]!r}")
    for k, w in want.items():
        g = num(got[k], f"frame_stats({label})[{k!r}]")
        if abs(g - w) > (1e-6 if k in ("n", "dropped") else 1e-3 * max(1.0, abs(w))):
            raise CheckFailed(f"frame_stats({label}): {k} = {g:.6g} is not right")


def mentions(text, value, tol):
    """True if the text quotes a number within tol of value."""
    for m in re.findall(r"\d+(?:[.,]\d+)?", text):
        try:
            if abs(float(m.replace(",", ".")) - value) <= tol:
                return True
        except ValueError:
            pass
    return False


# ======================================================================== session 1 — Timekeeper
@c.test("TODO 1: frame_stats() on unseen streams (drops, a stall, two frames, too few stamps)",
        hint="Lesson §2 and lab Step 2 (hints 2–5); python3 run_timing.py test names the symptom of each mistake.")
def _():
    (f,) = functions("frame_stats")
    got = go(f, STREAM_A)
    if isinstance(got, dict) and "fps" in got:
        if abs(float(got["fps"]) - 24.456522) < 1e-3:
            raise CheckFailed("fps: 9 frames have 8 intervals — (n − 1) / (last − first), not n / (last − first)")
        if "jitter_ms" in got and abs(float(got["jitter_ms"]) - 24.773257) < 1e-3:
            raise CheckFailed("jitter_ms: that is ddof = 1; the course rule is numpy's default, np.std(d) (ddof = 0)")
        if "dropped" in got and got["dropped"] == 5:
            raise CheckFailed("dropped = 5 on a stream with one 3-period gap and one 2-period gap: each gap of k "
                              "periods hides k − 1 frames, so 2 + 1 = 3")
        if "median_ms" in got and abs(float(got["median_ms"]) - 0.034) < 1e-6:
            raise CheckFailed("median_ms = 0.034: that is seconds; the dict wants milliseconds (× 1000)")
    stats_ok(got, STATS_A, "a stream with two gaps")
    got = go(f, np.asarray(STREAM_B))
    if isinstance(got, dict) and got.get("dropped") == 10:
        raise CheckFailed("dropped = 10 on a stream with a 0.52 s stall: count the periods with the MEDIAN interval "
                          "(one stall moves the mean)")
    stats_ok(got, STATS_B, "a numpy array with a 0.52 s stall")
    stats_ok(go(f, [5.0, 5.05]), STATS_C, "two stamps")
    for bad in ([1.0], []):
        try:
            got = go(f, bad)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise CheckFailed(f"frame_stats({bad}) must raise ValueError, not: {e}")
        raise CheckFailed(f"frame_stats({bad}) returned {got!r}: with fewer than 2 stamps there is no interval — "
                          "raise ValueError(\"…\")")


@c.test("TODO 2: delay_from_flashes() on an unseen bench (no frame before, not seen, half lit, exactly the midpoint)",
        hint="Read the docstring of delay_from_flashes again, word by word (dark, bright, STRICTLY brighter, None); lab "
             "Step 3, hints 1–4.")
def _():
    (f,) = functions("delay_from_flashes")
    fl, ft, fb = bench2()
    got = go(f, fl, ft, fb)
    if not isinstance(got, (list, tuple)):
        raise CheckFailed(f"delay_from_flashes() must return a list, got {got!r}")
    if len(got) != len(fl):
        raise CheckFailed(f"delay_from_flashes() returned {len(got)} entries for {len(fl)} flashes: one entry per "
                          "flash, None included, in the flashes' order")
    if got[0] is not None:
        raise CheckFailed(f"a flash before the first frame has no dark level: None, not {got[0]!r}")
    if got[2] is not None:
        raise CheckFailed(f"a flash whose brightness rises by 13 only (min_rise 20) was not seen: None, not {got[2]!r}")
    for k in (1, 3, 4):
        if got[k] is None:
            raise CheckFailed(f"flash {k} was seen (a clear rise), but you returned None for it")
    g1, g3 = float(got[1]), float(got[3])
    if abs(g3 - 0.10) < 1e-6:
        raise CheckFailed("flash 3: you counted a half-lit frame: the rule is brighter than the MIDPOINT LEVEL "
                          "(dark + bright) / 2 — not brighter than dark, and not half the rise (bright − dark) / 2 "
                          "(lab Step 3, hint 2)")
    if abs(g1 - 0.10) < 1e-6:
        raise CheckFailed("flash 1: a frame EXACTLY at the midpoint is not brighter than it — use >, not >=")
    for k in (1, 3, 4):
        c.near(float(got[k]), DELAYS2[k], 1e-6, f"the delay of flash {k} (s)")


@c.test("TODO 3: time_error_m() on unseen heights, rates and times — exact, positive",
        hint="Lesson §4 and lab Step 5 (hints 1, 2 and 4); python3 run_timing.py test names the symptom.")
def _():
    (f,) = functions("time_error_m")

    def pair(args):
        got = go(f, *args)
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"time_error_m{args} must return two numbers (attitude_m, position_m), got {got!r}")
        return num(got[0], f"time_error_m{args}[0]"), num(got[1], f"time_error_m{args}[1]")

    a, p = pair((250.0, 35.0, 0.05, 20.0))
    if abs(a - 7.635682) < 1e-3:
        raise CheckFailed("time_error_m(250, 35, 0.05, …) attitude part = 7.636: that is h × angle (small-angle); the "
                          "docstring wants the tangent (lab Step 5, hint 2)")
    if abs(a) > 100:
        raise CheckFailed(f"time_error_m(250, 35, 0.05, …) attitude part = {a:.1f}: math.tan got DEGREES (lab Step 5, "
                          "hint 1)")
    c.near(a, 7.638191, 1e-5, "time_error_m(250, 35, 0.05, 20) attitude part")
    c.near(p, 1.0, 1e-9, "time_error_m(250, 35, 0.05, 20) position part (speed × time)")
    a, p = pair((80.0, -20.0, 0.2))
    c.ok(a >= 0, f"time_error_m(80, −20, 0.2) attitude part = {a:.3f}: a rotation the other way is the same error — "
                 "a distance is ≥ 0")
    c.near(a, 5.594145, 1e-5, "time_error_m(80, −20, 0.2) attitude part")
    c.near(p, 0.0, 1e-12, "time_error_m(80, −20, 0.2) position part (speed_mps defaults to 0)")
    a, p = pair((400.0, 30.0, -0.1, 50.0))
    c.ok(a >= 0 and p >= 0, f"time_error_m(400, 30, −0.1, 50) = ({a:.3f}, {p:.3f}): a time error in the other "
                            "direction costs the same — both parts are distances, ≥ 0")
    c.near(a, 400 * math.tan(math.radians(3.0)), 1e-6, "time_error_m(400, 30, −0.1, 50) attitude part")
    c.near(p, 5.0, 1e-9, "time_error_m(400, 30, −0.1, 50) position part")
    a, p = pair((600.0, 45.0, 1.0))
    c.near(a, 600.0, 1e-6, "time_error_m(600, 45, 1) attitude part")


@c.test("Steps 0–1: your guess, the decode time and what it costs",
        hint="Lab Step 1: run python3 run_timing.py bench; CORES_ALL_FRAMES: lab Step 1, hint 1. EXPLAIN_DECODE: in "
             "your own words.")
def _():
    pe, dm, cores, why = answers("PREDICT_ERROR", "DECODE_MS", "CORES_ALL_FRAMES", "EXPLAIN_DECODE")
    predicted("PREDICT_ERROR", pe)
    dm = number(dm, "DECODE_MS")
    c.ok(dm > 0, "DECODE_MS is still 0: run python3 run_timing.py bench (Step 1)")
    c.ok(0.5 <= dm <= 500, f"DECODE_MS = {dm}: a 1920 × 1080 JPEG decodes in a few ms to a few tens of ms — copy the "
                           "printed number (milliseconds)")
    cores = number(cores, "CORES_ALL_FRAMES")
    want = 28.8 * dm / 1000.0
    if abs(cores - 28.8 * dm) < 0.5:
        raise CheckFailed("CORES_ALL_FRAMES: DECODE_MS is in milliseconds — divide by 1000 (a core-second is 1000 ms)")
    if abs(cores - dm / 28.8) < 0.01 or abs(cores - 28.8 / dm) < 0.01:
        raise CheckFailed("CORES_ALL_FRAMES: multiply, do not divide — 28.8 decodes per second × DECODE_MS / 1000 s each")
    c.ok(abs(cores - want) <= max(0.015, 0.05 * want), f"CORES_ALL_FRAMES = {cores}: with your DECODE_MS = {dm}, "
         "28.8 decodes per second keep 28.8 × DECODE_MS / 1000 cores busy")
    explained("EXPLAIN_DECODE", why,
              ((r"cpu", r"core", r"expensive", r"\d+ ?ms", r"heavy", r"processing (time|power)", r"computing"),
               "what decoding costs"),
              ((r"only (one|the|a few)", r"one (frame )?(per|a|each) second", r"(about|around) one", r"1 frame",
                r"sends? (only )?one", r"needs? (only )?one", r"rest are (thrown|dropped|discarded)", r"newest",
                r"latest"), "why decoding one frame is enough"))


@c.test("Step 2: the grab log — rate, drops, jitter with and without the stall",
        hint="Lab Step 2: python3 run_timing.py stats after TODO 1 (two decimals). EXPLAIN_JITTER: look at "
             "out/intervals.png — what is different in the last 20 s?")
def _():
    fps, dr, j40, j60, why = answers("FPS_LOG", "DROPPED_LOG", "JITTER_40S_MS", "JITTER_60S_MS", "EXPLAIN_JITTER")
    fps = number(fps, "FPS_LOG")
    c.ok(fps != 0, "FPS_LOG is still 0: run python3 run_timing.py stats (Step 2)")
    if abs(fps - 28.8) < 0.005:
        raise CheckFailed("FPS_LOG = 28.8 is the camera's nominal rate; the grab log's mean rate is lower (drops, a "
                          "stall): copy it from python3 run_timing.py stats")
    c.near(fps, FPS_LOG, 0.006, "FPS_LOG")
    c.ok(number(dr, "DROPPED_LOG") == DROPPED_LOG, f"DROPPED_LOG = {dr} is not the 60 s line's dropped frames")
    j40, j60 = number(j40, "JITTER_40S_MS"), number(j60, "JITTER_60S_MS")
    if abs(j40 - JITTER_60S_MS) < 0.01 and abs(j60 - JITTER_40S_MS) < 0.01:
        raise CheckFailed("JITTER_40S_MS and JITTER_60S_MS are swapped")
    c.near(j40, JITTER_40S_MS, 0.01, "JITTER_40S_MS")
    c.near(j60, JITTER_60S_MS, 0.01, "JITTER_60S_MS")
    explained("EXPLAIN_JITTER", why,
              ((r"stall", r"pause", r"gap", r"freez", r"\b38\d", r"0\.38", r"outlier", r"spike"),
               "what happens in the last 20 s"),
              ((r"median", r"normal", r"typical", r"usual", r"rhythm"), "which number describes the normal rhythm"),
              ((r"risk", r"worst", r"max", r"largest", r"jitter", r"std", r"standard deviation"),
               "which number describes the risk"))


@c.test("Step 3: the flash bench — median, minimum, the unseen flash, the odd one; TODO P and the phase fit",
        hint="Lab Step 3 (python3 run_timing.py flashes, ms, one decimal) and Step 3b (TODO P in phase.py, then "
             "python3 phase.py). EXPLAIN_…: in your own words.")
def _():
    pd, med, mn, uf, of, why = answers("PREDICT_DELAY", "DELAY_MEDIAN_MS", "DELAY_MIN_MS", "UNSEEN_FLASH",
                                       "OUTLIER_FLASH", "EXPLAIN_SPREAD")
    predicted("PREDICT_DELAY", pd)
    med, mn = number(med, "DELAY_MEDIAN_MS"), number(mn, "DELAY_MIN_MS")
    if abs(med - DELAY_MEDIAN_MS / 1000) < 0.001:
        raise CheckFailed("DELAY_MEDIAN_MS is in seconds: write milliseconds (× 1000)")
    c.ok(med != 0, "DELAY_MEDIAN_MS is still 0: run python3 run_timing.py flashes (Step 3)")
    c.near(med, DELAY_MEDIAN_MS, 0.11, "DELAY_MEDIAN_MS")
    c.near(mn, DELAY_MIN_MS, 0.11, "DELAY_MIN_MS")
    c.ok(number(uf, "UNSEEN_FLASH") == UNSEEN_FLASH, f"UNSEEN_FLASH = {uf}: which line says 'not seen'?")
    c.ok(number(of, "OUTLIER_FLASH") == OUTLIER_FLASH, f"OUTLIER_FLASH = {of}: which flash's delay is far from all "
                                                       "the others? (out/flashes.png, right)")
    explained("EXPLAIN_SPREAD", why,
              ((r"wait", r"next (frame|exposure|image|picture)", r"random", r"phase", r"between (two )?(frames|exposures)",
                r"\bw\b", r"sync", r"any (time|moment)", r"when the flash"), "the random wait for the next exposure"),
              ((r"frame", r"exposure", r"period", r"image", r"picture"), "that frames come only every period"))
    with contextlib.redirect_stdout(io.StringIO()):
        ph_mod = load_student("phase.py", fresh=True)
    (fp,) = functions("flash_phase", module=ph_mod, path="phase.py")
    got = go(fp, 2.0, [1.9, 1.95, 1.99, 2.0, 2.03])
    if got is not None and abs(float(got) - 0.01) < 1e-9:
        raise CheckFailed("flash_phase(2.0, …): a frame grabbed exactly at t0 counts (at or before t0): the phase is 0")
    c.ok(got is not None and abs(float(got)) < 1e-9, f"flash_phase(2.0, frames 1.9 … 2.03 with one AT 2.0) should be "
                                                     f"0.0, got {got!r}")
    got = go(fp, 2.02, [1.9, 1.95, 1.99, 2.0, 2.03])
    if got is not None and abs(float(got) + 0.01) < 1e-6:
        raise CheckFailed("flash_phase: the LAST frame at or before t0, not the first one after it")
    c.ok(got is not None and abs(float(got) - 0.02) < 1e-9, f"flash_phase(2.02, …) should be 0.02 s, got {got!r}")
    got = go(fp, 1.5, [1.9, 1.95])
    c.ok(got is None, f"flash_phase(1.5, …) with no frame before 1.5: None, not {got!r}")
    pp, sl, whyp = answers("PREDICT_PHASE", "PHASE_SLOPE", "EXPLAIN_PHASE")
    predicted("PREDICT_PHASE", pp)
    sl = number(sl, "PHASE_SLOPE")
    c.ok(sl != 0, "PHASE_SLOPE is still 0: run python3 phase.py (Step 3b)")
    if abs(sl + PHASE_SLOPE) < 0.02:
        raise CheckFailed("PHASE_SLOPE: look at the sign in phase.py's printout — the delay goes DOWN as the phase grows")
    c.near(sl, PHASE_SLOPE, 0.011, "PHASE_SLOPE")
    explained("EXPLAIN_PHASE", whyp,
              ((r"later", r"each (ms|millisecond)", r"one (ms|millisecond)", r"one for one", r"less", r"shorter",
                r"inverse", r"opposite", r"minus one", r"−1", r"-1", r"decreas", r"[−-]0[.,]9\d",
                r"ms (of delay )?(per|for each|for every) (ms|millisecond)", r"same amount", r"one-to-one",
                r"all of the spread", r"whole spread", r"entire", r"almost all"), "what a slope of −1 means"),
              ((r"wait", r"phase", r"where", r"when the flash", r"between (two )?(frames|exposures|grabs)", r"\bw\b",
                r"not noise", r"not random", r"explain"), "that the spread is the flash's place between frames"))


@c.test("Step 4: your delay setting, from the bench (in answers.py and in camera.yaml)",
        hint="Lab Step 4: which parts of a measured delay are not the camera? Lesson §3, 'What does one delay "
             "contain?'. Write the setting in seconds in answers.py AND as latency_s in camera.yaml.")
def _():
    lat, why = answers("LATENCY_SETTING_S", "EXPLAIN_LATENCY")
    lat = number(lat, "LATENCY_SETTING_S")
    c.ok(lat != 0, "LATENCY_SETTING_S is still 0 (Step 4)")
    if lat > 1:
        raise CheckFailed(f"LATENCY_SETTING_S = {lat}: write seconds (0.1…), not milliseconds")
    if abs(lat - 0.138) < 0.0005:
        raise CheckFailed("LATENCY_SETTING_S = 0.138 is NAVERA's setting for ITS camera (the Insta360); this bench "
                          "measured another camera — compute yours from your bench numbers (lab Step 4)")
    traps = {DELAY_MEDIAN_MS: "the median as it is: it still holds the screen's delay and about half a period",
             DELAY_MIN_MS: "the minimum: it still holds the screen's delay (20 ms)",
             DELAY_MEDIAN_MS - SCREEN_MS: "the median minus the screen: half a frame period (T/2) is still in it",
             DELAY_MEDIAN_MS - T_MS / 2: "the median minus T/2: the screen's 20 ms are still in it",
             DELAY_MEDIAN_MS - T_MS - SCREEN_MS: "a whole period T removed: the wait w lies between 0 and T, so on "
                                                 "average (and in the median) it is T/2",
             166.1 - T_MS / 2 - SCREEN_MS: "the MEAN minus T/2 and s: one odd flash pulls the mean — use the median"}
    for v, why_trap in traps.items():
        if abs(lat * 1000 - v) < 1.5 and not (110 <= lat * 1000 <= 128):
            raise CheckFailed(f"LATENCY_SETTING_S = {lat}: that is {why_trap}")
    c.ok(0.110 <= lat <= 0.128, f"LATENCY_SETTING_S = {lat} s: the bench's numbers give a camera delay between about "
                                "0.11 and 0.13 s — remove from the median what is not the camera (lesson §3)")
    y = my_latency()
    c.ok(abs(y - lat) <= 0.0005, f"camera.yaml says latency_s: {y}, answers.py says {lat}: write the same value in "
                                 "both and save both files")
    explained("EXPLAIN_LATENCY", why,
              ((r"screen", r"20 ?ms", r"0\.02\b", r"monitor", r"display"), "the screen's delay"),
              ((r"half", r"t/2", r"17", r"wait"), "the wait for the next exposure (half a period)"))
    c.ok(mentions(str(why), DELAY_MEDIAN_MS, 0.6) or mentions(str(why), DELAY_MEDIAN_MS / 1000, 0.0006),
         "EXPLAIN_LATENCY: start from your bench median (in ms or s) and say what you removed from it")


@c.test("Step 5: what a time error costs (three numbers and why)",
        hint="Lab Step 5: BUDGET_500_M and ALONG_60_M come from your time_error_m (one frame period = 1/28.8 s); "
             "DT_FOR_30M_S: lab Step 5, hint 3. EXPLAIN_BUDGET: which two factors multiply?")
def _():
    b, al, dt, why = answers("BUDGET_500_M", "ALONG_60_M", "DT_FOR_30M_S", "EXPLAIN_BUDGET")
    b = number(b, "BUDGET_500_M")
    c.ok(b != 0, "BUDGET_500_M is still 0: use your time_error_m (Step 5)")
    if abs(b - 500 * math.tan(math.radians(45 * 0.138))) < 0.5:
        raise CheckFailed("BUDGET_500_M: the time error is ONE FRAME PERIOD, 1/28.8 s (34.7 ms), not 0.138 s")
    c.near(b, BUDGET_500_M, 0.02, "BUDGET_500_M (m)")
    al = number(al, "ALONG_60_M")
    c.near(al, ALONG_60_M, 0.006, "ALONG_60_M (m)")
    dt = number(dt, "DT_FOR_30M_S")
    if abs(dt - 0.2 / math.radians(25)) < 0.003:
        raise CheckFailed("DT_FOR_30M_S = 0.46: you used the small-angle formula (or radians per second); atan(0.2) "
                          "is 11.31°, and 11.31 / 25 = …")
    c.near(dt, DT_FOR_30M_S, 0.006, "DT_FOR_30M_S (s)")
    explained("EXPLAIN_BUDGET", why,
              ((r"height", r"high", r"altitude", r"\bh\b", r"300", r"lever", r"farther from the ground"),
               "why height multiplies the error"),
              ((r"rate", r"rotat", r"ω", r"omega", r"°/s", r"turn"), "that the rotation rate turns a time error into an "
                                                                    "angle error"),
              ((r"level", r"straight", r"no rotation", r"not rotat", r"zero", r"0 °/s", r"does not turn",
                r"doesn't turn", r"constant attitude"), "why straight, level flight costs nothing"))


# ======================================================================== session 2 — Shutter
def att_close(got, want, tol=1e-6):
    try:
        a = np.asarray(got, dtype=float)
    except (TypeError, ValueError):
        return False
    w = np.asarray(want, dtype=float)
    return a.shape == (4,) and (np.allclose(a, w, atol=tol) or np.allclose(-a, w, atol=tol))


@c.test("TODO 4: attitude_at() on an unseen IMU history (a sign flip, holes, both ends, numpy arrays)",
        hint="Lesson §5 and lab Step 6, hints 1–6; python3 run_timing.py test names the symptom of each mistake.")
def _():
    (f,) = functions("attitude_at")
    got = go(f, 1.005, IT, IQ)
    if got is None:
        raise CheckFailed("attitude_at(1.005) returned None, but samples are 0.005 s away")
    if att_close(got, ATT_F_INVERTED):
        raise CheckFailed("attitude_at(1.005): the fraction is upside down — f = (t − t₀) / (t₁ − t₀)")
    try:
        a = np.asarray(got, dtype=float)
        if a.shape == (4,) and abs(a[0]) > 0.9:
            raise CheckFailed("attitude_at returns the scalar part FIRST: the course stores (x, y, z, w)")
    except (TypeError, ValueError):
        raise CheckFailed(f"attitude_at must return 4 numbers (x, y, z, w), got {got!r}")
    c.ok(att_close(got, ATT[1.005]), f"attitude_at(1.005) between a sample and the NEXT one stored as −q: {got!r} is "
         "not the slerp result — use rotations.slerp (it takes the short way), not a formula of your own")
    for t in (1.03, 1.04, 1.17, 1.25, 0.85, 1.50, 1.315):
        got = go(f, t, IT, IQ)
        if got is None:
            raise CheckFailed(f"attitude_at({t}) returned None, but a sample is within 0.2 s")
        if not att_close(got, ATT[t]):
            what = {1.04: "exactly on a sample: that sample", 0.85: "0.15 s before the first sample: the first sample — with i = 0, imu_q[i - 1] is imu_q[-1], the LAST "
                    "sample: test i == 0 first (lab Step 6, hint 4)",
                    1.50: "0.18 s after the last sample: the last sample (never extrapolate)",
                    1.17: "inside a 0.26 s hole, 0.13 s from its start: interpolate across it",
                    1.25: "inside a 0.26 s hole, 0.05 s from its end: interpolate"}.get(t, "between two samples")
            raise CheckFailed(f"attitude_at({t}) = {np.round(np.asarray(got, dtype=float), 5).tolist()} is not right "
                              f"({what})")
    for t, why in ((1.55, "0.23 s after the last sample"), (0.70, "0.30 s before the first sample")):
        got = go(f, t, IT, IQ)
        c.ok(got is None, f"attitude_at({t}): {why} (> max_gap_s = 0.2) — return None, not {got!r}")
    got = go(f, 2.1, [2.0, 2.8], [IQ[0], IQ[2]])
    c.ok(got is not None, "inside a 0.8 s hole but 0.1 s from its start: the nearest sample is within max_gap_s — "
                          "interpolate (lesson §5 ✏️: 17.1 s → yes); only the NEAREST sample counts, not the hole's "
                          "width (lab Step 6, hint 5)")
    c.ok(att_close(got, ATT_HOLE08), f"attitude_at(2.1) in a 0.8 s hole: f = 0.125 of the way, got {got!r}")
    got = go(f, 2.25, [2.0, 2.5], [IQ[0], IQ[2]])
    c.ok(got is None, f"in the middle of a 0.5 s hole both samples are 0.25 s away: None, not {got!r}")
    got = go(f, 1.03, IT, IQ, max_gap_s=0.005)
    c.ok(got is None, f"with max_gap_s = 0.005, 1.03 is 0.01 s from both samples: None, not {got!r} — use the "
                      "max_gap_s argument, not 0.2")
    c.ok(go(f, 1.0, [], []) is None, "an empty history: return None")
    got = go(f, 1.03, np.asarray(IT), np.asarray(IQ))
    c.ok(att_close(got, ATT[1.03]), "attitude_at with numpy arrays (imu_t an array, imu_q an (n, 4) array) must give "
                                    f"the same result as with lists, got {got!r}")


@c.test("TODO 5: rotation_rate_dps() on an unseen turn (40 °/s), other windows, and with no attitude",
        hint="Lesson §6 and lab Step 8, hint 1. The window lies BEFORE t (from t − window_s to t).")
def _():
    (f,) = functions("rotation_rate_dps")
    ht = [round(0.02 * k, 2) for k in range(40)]
    hq = [qe(5.0, 0.0, 40.0 * t) for t in ht]
    v = num(go(f, 0.5, ht, hq), "rotation_rate_dps(0.5, a 40 °/s turn)")
    if abs(v - 8.0) < 0.01:
        raise CheckFailed("rotation_rate_dps = 8.0 on a 40 °/s turn: that is the angle in 0.2 s — divide by window_s")
    c.near(v, 40.0, 1e-3, "rotation_rate_dps(0.5, a 40 °/s turn)")
    c.near(num(go(f, 0.5, ht, hq, window_s=0.1), "rotation_rate_dps(…, window_s=0.1)"), 40.0, 1e-3,
           "rotation_rate_dps with window_s = 0.1")
    got = go(f, 0.73, ht, hq, window_s=0.3)
    if got is None:
        raise CheckFailed("rotation_rate_dps(0.73, …, window_s=0.3) returned None although IMU samples exist at both "
                          "0.43 s and 0.73 s: is your window BEFORE t (t − window_s to t)? (lab Step 8, hint 1)")
    c.near(num(got, "rotation_rate_dps(0.73, …, window_s=0.3)"), 40.0, 1e-3,
           "rotation_rate_dps(0.73) with window_s = 0.3")
    got = go(f, 1.2, ht, hq)
    c.ok(got is None, f"at 1.2 s the last sample is 0.42 s old: no attitude, so no rate — None, not {got!r}")
    got = go(f, 0.51, ht, hq, max_gap_s=0.005)
    c.ok(got is None, f"with max_gap_s = 0.005, 0.51 s is 0.01 s from every sample: no attitude, so None, not {got!r} — "
                      "pass max_gap_s on to attitude_at")


@c.test("TODO 6: usable() with unseen settings (max 20 °/s, max 30°), the rule order, a gimbal",
        hint="The docstring of usable(), rule by rule and in its order; lab Step 8, hints 2–6.")
def _():
    (f,) = functions("usable")
    for label, args, want in USABLE:
        got = go(f, *args)
        cfg = args[2]
        case = f"{label} (limits {cfg['max_rate_dps']} °/s and {cfg['max_tilt_deg']}°)"
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"usable() must return (bool, reason), got {got!r}")
        ok, why = got
        if not isinstance(ok, bool):
            raise CheckFailed(f"usable(): the first value must be True or False (a bool), got {ok!r}")
        if ok != want[0]:
            if ok and want[1].startswith(("turning", "tilted")) and (rate_v := args[1]) is not None and \
                    (want[1].startswith("tilted") or rate_v <= 30.0):
                raise CheckFailed(f"{case}: refused here — read the limits from cfg (cfg['max_rate_dps'], "
                                  "cfg['max_tilt_deg']), not 30 and 45")
            if want[1].startswith("turning") and str(why).startswith("tilted"):
                raise CheckFailed(f"{case}: the rate rule comes BEFORE the tilt rule — expected a 'turning …' reason")
            if "30.0" in str(why) or "45.0" in str(why):
                raise CheckFailed(f"{case}: you used 30 / 45 — read the limits from cfg")
            raise CheckFailed(f"{case}: usable() says {got!r}")
        if str(why) != want[1]:
            if str(why).startswith("tilted") and want[1].startswith("turning"):
                raise CheckFailed(f"{case}: the rate rule comes BEFORE the tilt rule")
            raise CheckFailed(f"{case}: the reason must be exactly {want[1]!r} (the docstring's words, one decimal), "
                              f"got {why!r}")


@c.test("Steps 6–7: the plane's turn — three attitudes, two delay settings, a steady bank",
        hint="Lab Steps 6–7: python3 run_timing.py turn --latency 0.138, then turn (your camera.yaml), two decimals. "
             "STEADY_RATE_DPS: lesson §4, 'A steady bank is still a rotation'.")
def _():
    pm, gm, cm, mm, why, sr, why_s = answers("PREDICT_METHODS", "GRAB_MEDIAN_M", "COPIED_MEDIAN_M", "MINE_MEDIAN_M",
                                             "EXPLAIN_TURN", "STEADY_RATE_DPS", "EXPLAIN_STEADY")
    predicted("PREDICT_METHODS", pm)
    meta = table()["meta"]
    c.ok(number(gm, "GRAB_MEDIAN_M") != 0, "GRAB_MEDIAN_M is still 0: run python3 run_timing.py turn (Step 7)")
    c.near(number(gm, "GRAB_MEDIAN_M"), meta["grab_median_m"], 0.011, "GRAB_MEDIAN_M ('held at the grab', median)")
    cm = number(cm, "COPIED_MEDIAN_M")
    if abs(cm - 0.24) < 0.011:
        raise CheckFailed("COPIED_MEDIAN_M: that is the 'nearest sample' line; write YOUR attitude_at's line")
    c.near(cm, row_for(0.138)["median_m"], 0.011, "COPIED_MEDIAN_M (yours with --latency 0.138)")
    lat = my_latency()
    c.near(number(mm, "MINE_MEDIAN_M"), row_for(lat)["median_m"], 0.011,
           f"MINE_MEDIAN_M (yours with camera.yaml's latency_s = {lat}; run `turn` again if you changed it)")
    explained("EXPLAIN_TURN", why,
              ((r"roll(s|ing)? (in|into|out)", r"bank(s|ing)? (in|into|out|change)", r"enter", r"start of the (turn|bank)",
                r"3 ?(–|-|to) ?5", r"1[78] ?s", r"17", r"while (it|the plane) (rolls|banks)", r"chang\w* (its )?(bank|roll)"),
               "when in the flight (the roll changes)"),
              ((r"rate", r"°/s", r"fast", r"quick"), "the rotation rate"),
              ((r"late", r"old", r"delay", r"latency", r"0\.1", r"after the exposure", r"too new"),
               "why the delay matters then"))
    sr = number(sr, "STEADY_RATE_DPS")
    c.ok(sr != 0, "STEADY_RATE_DPS is still 0: compute it (lesson §4, 'A steady bank is still a rotation')")
    if abs(sr - math.radians(STEADY_RATE_DPS)) < 0.01:
        raise CheckFailed("STEADY_RATE_DPS = 0.23: that is rad/s — the question asks °/s")
    if abs(sr - 9.81 * math.tan(math.radians(30)) / 25 * 1000) < 1:
        raise CheckFailed("STEADY_RATE_DPS: g·tan φ / v gives rad/s; convert with × 57.3")
    c.near(sr, STEADY_RATE_DPS, 0.03, "STEADY_RATE_DPS (°/s)")
    explained("EXPLAIN_STEADY", why_s,
              ((r"turn", r"heading", r"yaw"), "that the banked plane is turning (its heading changes)"),
              ((r"13", r"rate", r"°/s", r"rotat"), "the rotation rate it has"),
              ((r"late", r"old", r"delay", r"latency", r"0\.1", r"after the exposure", r"too new", r"grab", r"\bdt\b",
                r"δt", r"time error"), "why that rate still costs metres with the attitude held at the grab"))


@c.test("Steps 8–9: your refusals on the flight, and the delay the flight prefers",
        hint="Lab Step 8 (python3 run_timing.py turn after TODO 5–6, camera.yaml's rules unchanged) and Step 9 "
             "(python3 run_timing.py scan).")
def _():
    nl, br, why_b, why_r, best, why_s = answers("N_TILTED", "BANK48_RATE_DPS", "EXPLAIN_BANK48", "EXPLAIN_REFUSE",
                                                "BEST_LATENCY_S", "EXPLAIN_SCAN")
    rules_are_defaults()
    row = row_for(my_latency())
    br = number(br, "BANK48_RATE_DPS")
    c.ok(br != 0, "BANK48_RATE_DPS is still 0: the same formula as STEADY_RATE_DPS, with 48° (lesson §4)")
    if abs(br - math.radians(BANK48_RATE_DPS)) < 0.01:
        raise CheckFailed("BANK48_RATE_DPS: that is rad/s — the question asks °/s")
    c.near(br, BANK48_RATE_DPS, 0.05, "BANK48_RATE_DPS (°/s)")
    explained("EXPLAIN_BANK48", why_b,
              ((r"30", r"below", r"under", r"less than", r"lower", r"smaller", r"not (fast|above|over)"),
               "that 25 °/s is below the rate limit"),
              ((r"48", r"45", r"tilt", r"bank", r"lean"), "that the tilt is above 45°"))
    for name, v, key in (("N_TILTED", nl, "tilted"),):
        v = number(v, name)
        c.ok(v == row[key], f"{name} = {v:g} is not what the lesson's rules give on this flight with your camera.yaml "
                            f"(latency_s {my_latency()}). If `turn` prints this number, one of your functions differs "
                            "from the rules (lab Step 8, hint 7); if not, run `turn` again after your last change")
    explained("EXPLAIN_REFUSE", why_r,
              ((r"blur", r"rolling", r"shutter", r"exposure (time|lasts|takes)", r"few (ms|milliseconds)",
                r"uncertain", r"residual", r"not (exact|perfect)", r"jitter", r"leftover", r"left over",
                r"(setting|latency|delay) (is )?(only )?(known|accurate|precise)"), "what timing error is left"),
              ((r"rate", r"60", r"grow", r"multipl", r"ω", r"°/s", r"proportional"),
               "why it matters more at a high rate"))
    best = number(best, "BEST_LATENCY_S")
    if best > 1:
        raise CheckFailed("BEST_LATENCY_S: write seconds, not milliseconds")
    c.near(best, float(table()["meta"]["best_scan_s"]), 0.0025, "BEST_LATENCY_S (s)")
    explained("EXPLAIN_SCAN", why_s,
              ((r"bench", r"step 4"), "your bench setting"),
              ((r"agree", r"close", r"same", r"match", r"differ", r"0\.11\d", r"0\.12\d", r"1[12]\d ?ms"),
               "how the two compare"),
              ((r"truth", r"true", r"reference", r"know", r"ground.?truth", r"simulat"), "what a real plane lacks"))


@c.test("Step 10: the camera node (recorded clip) runs YOUR timing functions over ROS, and the queue experiment",
        hint="Lab Step 10. If no meta message comes, run python3 -m navera_lite.ros.camera_node in your terminal: its "
             "log names the function that fails.")
def _():
    from diagnostic_msgs.msg import DiagnosticStatus
    functions("attitude_at", "rotation_rate_dps", "usable")
    lat = my_latency()
    with Background("python3 -m navera_lite.ros.camera_node --ros-args -p start_s:=2.5 -p rate_hz:=4.0 "
                    "-p save_dir:=none", settle=2.0) as bg:
        msgs = wait_for_messages("/navera_lite/camera/meta", DiagnosticStatus, count=8, timeout=15.0)
    if len(msgs) < 4:
        tail = "\n".join((bg.output() or "").strip().splitlines()[-6:])
        raise CheckFailed(f"the camera node published {len(msgs)} meta message(s) in 15 s (4 or more expected). Its "
                          f"last lines:\n{tail}")
    usable_n, good = 0, 0
    for m in msgs:
        v = {kv.key: kv.value for kv in m.values}
        for k in ("grab_s", "exposure_s", "latency_s", "usable", "att_err_deg"):
            if k not in v:
                raise CheckFailed(f"a meta message has no {k!r}: was navera_lite/ros/camera_node.py changed? Restore it")
        try:
            g, e, l_ = float(v["grab_s"]), float(v["exposure_s"]), float(v["latency_s"])
        except ValueError:
            raise CheckFailed(f"a meta message has unreadable times: {v}")
        c.ok(abs(l_ - lat) < 1e-6 and abs((g - e) - lat) < 1e-4,
             f"the node stamped exposure = grab − {g - e:.3f} s; camera.yaml says {lat}: start it without -p latency_s")
        if v["usable"] == "true":
            usable_n += 1
            good += float(v["att_err_deg"]) < 1.5
        c.ok(m.message in ("ok", "no attitude at the exposure", "rotation rate unknown") or
             m.message.startswith(("turning ", "tilted ")), f"an unknown reason {m.message!r}: use the docstring's words")
    c.ok(usable_n >= 2, f"only {usable_n} of {len(msgs)} frames of a gentle roll were usable: check usable() and "
                        "rotation_rate_dps() (run_timing.py test)")
    c.ok(good >= 0.75 * usable_n, f"only {good} of {usable_n} usable frames had an attitude within 1.5° of the truth "
                                  "live (a well-stamped frame is well under 1°): is your delay setting right (Step 4)? "
                                  "Does run_timing.py test pass?")
    w, why = answers("QUEUE_WAITED_S", "EXPLAIN_QUEUE")
    w = number(w, "QUEUE_WAITED_S")
    c.ok(w != 0, "QUEUE_WAITED_S is still 0: run the node with -p queue:=4 (Step 10)")
    c.ok(1.5 <= w <= 2.5, f"QUEUE_WAITED_S = {w}: with -p queue:=4 the log says 'waited … s in the queue' on each "
                          "line, once the queue is full (after the first 2 s): copy a typical value")
    explained("EXPLAIN_QUEUE", why,
              ((r"wait", r"queue", r"old", r"buffer", r"stale", r"behind", r"\b2(\.0)? ?s"), "that the frame waited"),
              ((r"stamp", r"now", r"not (include|count|know|see)", r"does(n't| not) (include|count|know|see)",
                r"unknown"), "why the stamp does not know it"),
              ((r"rule", r"usable", r"refus", r"accept", r"catch", r"check"), "why the refusal rules accepted the frames"),
              min_words=20)


@c.test("Step 11: the memo (report.md)",
        hint="Keep the four headings, at least 150 words of your own, and quote: the grab log's frame rate, the bench's "
             "median delay, your delay setting and the median error of the attitude held at the grab.")
def _():
    try:
        text = open("report.md", encoding="utf-8").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing: restore it from the starter")
    for h in ("## Frame timing", "## Camera delay", "## Attitude at the exposure", "## Recommendation"):
        c.ok(h.lower() in text.lower(), f"report.md has no heading {h!r}: keep the four headings")
    c.ok("TODO" not in text, "report.md still has a TODO: replace each one with your text")
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    c.ok(len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body)) >= 150, "report.md has fewer than 150 words")
    c.ok(mentions(text, 28.27, 0.011) or mentions(text, 28.3, 0.001), "report.md does not quote the grab log's frame "
                                                                       "rate (28.27 frames/s)")
    c.ok(mentions(text, 156.3, 0.11) or mentions(text, 156, 0.001) or mentions(text, 0.156, 0.0006),
         "report.md does not quote the bench's median delay")
    lat = my_latency()
    c.ok(mentions(text, lat, 0.0006) or mentions(text, lat * 1000, 0.6), f"report.md does not quote your delay "
                                                                          f"setting ({lat} s)")
    gm = table()["meta"]["grab_median_m"]
    c.ok(mentions(text, gm, 0.011) or mentions(text, round(gm, 1), 0.001), "report.md does not quote the median error of the "
                                                                    "attitude held at the grab")


c.milestone("timekeeper", "TODO 1", "TODO 2", "TODO 3", "Steps 0–1", "Step 2", "Step 3", "Step 4", "Step 5",
            label="Timekeeper")
c.milestone("shutter", "TODO", "Step", label="Shutter")
c.run()
