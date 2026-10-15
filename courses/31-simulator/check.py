"""Check of mission 31 — simulation and fault injection. Sealed: never shown to students.

hidden/expected.json (made by solutions/31-simulator/make_expected.py from the course's reference) holds unseen inputs
and the reference's answers for TODOs 1–10, the lab's own numbers (deterministic: same seeds, same parts), the
campaign's reference metrics, two hidden flights the check flies with the student's decoder in the autopilot, and the
campaign's scenario files as shipped. hidden/stream_truth.json: what gps_input.bin contains.
"""
import contextlib
import csv
import io
import json
import math
import os
import re
import shutil
import tempfile

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run, sh

c = Checker()
E = json.loads(hidden("expected.json"))
U, LAB = E["units"], E["lab"]
METRICS = ("switch_s", "recover_s", "availability", "leak_s", "max_err_m", "error95_m", "failsafe_s",
           "false_refusal_s", "ap_max_err_m")
RUNS = ["baseline", "jam", "off", "jump", "drift", "blind", "plane_late"]


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def functions(modname, *names):
    fns = need(quiet(modname), *names)
    for f in fns:
        if is_stub(f):
            where = modname if modname.endswith(".py") else modname.replace(".", "/") + ".py"
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in {where})")
    return fns


def answers(*names):
    return need(quiet("answers.py"), *names)


def number(v, name):
    if isinstance(v, (bool, str)) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")
    if not math.isfinite(x):
        raise CheckFailed(f"{name} is {x}: not a usable number")
    return x


def answer_near(name, v, want, tol, where):
    x = number(v, name)
    if x == 0.0 and want != 0.0:
        raise CheckFailed(f"{name} is still 0.0 — {where}")
    if abs(x - want) > tol:
        raise CheckFailed(f"{name} = {x:g} is not what {where} gives (it must be within ± {tol:g} of it)")


TIPS = [("unpack requires a buffer of 65 bytes", " — pad the payload with zero bytes up to 65 first "
                                                 "(MAVLink 2 drops the trailing zeros)"),
        ("index out of range", " — a frame cut by the end of the data: check that all its bytes are there before "
                               "reading them"),
        ("'NoneType'", " — a function it calls returned None: is an earlier TODO still a stub?"),
        ("unsupported operand type(s) for ^", " — in Python ^ is XOR, not a power: write x ** 2"),
        ("math domain error", " — math.log(0) or of a negative number: refuse impossible inputs first (ValueError)"),
        ("not subscriptable", " — a row is a dict: row[\"t_s\"]; payload bytes: payload[i]")]


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def same(got, want, tol=1e-6):
    if want is None or got is None:
        return got is None and want is None
    if isinstance(want, bool) or isinstance(want, str):
        return got == want
    if isinstance(want, (int, float)):
        try:
            return abs(float(got) - float(want)) <= tol * max(1.0, abs(float(want)))
        except (TypeError, ValueError):
            return False
    if isinstance(want, (list, tuple)):
        return isinstance(got, (list, tuple)) and len(got) == len(want) and all(same(g, w, tol) for g, w in zip(got, want))
    return got == want


def read_json(path, what):
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        raise CheckFailed(f"{path} is missing — {what}")
    except ValueError as e:
        raise CheckFailed(f"{path} is not valid JSON ({e})")


def run_rows(path):
    try:
        with open(path) as f:
            return list(csv.DictReader(f))
    except OSError:
        raise CheckFailed(f"{path} is missing — fly it first")


def events(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        raise CheckFailed(f"{path} is missing — fly it first")


def fnum(v):
    return None if v in (None, "") else float(v)


def given_metrics(rows, sc):
    """The metrics of campaign.py's measure() that are GIVEN code (not TODO 8), from a run's CSV rows."""
    faults = sc.get("faults", [])
    t0 = float(faults[0][0]) if faults else None
    back = [f[0] for f in faults[1:] if faults and f[1] == faults[0][1] and f[2] in ("ok", "day")]
    t1 = float(back[0]) if back else None
    t = [float(r["t_s"]) for r in rows]
    end = t[-1] if t else 0.0
    a, b = (t0 if t0 is not None else 0.0), (t1 if t1 is not None else end + 1.0)
    win = [r for r, ti in zip(rows, t) if a <= ti < b]
    errs = [fnum(r["lite_err_m"]) for r in rows if r["lite_err_m"]]
    werrs = [fnum(r["lite_err_m"]) for r in win if r["lite_err_m"]]
    fs = next((ti for r, ti in zip(rows, t) if ti >= a and r["ap_mode"] in ("LAND", "HOLD")), None)
    return {"availability": round(sum(r["lite_state"] in ("FIX", "DEGRADED") for r in win) / len(win), 4) if win else None,
            "leak_s": round(0.2 * sum(r["lite_source"] == "gps" and (fnum(r["lite_err_m"]) or 0) > 100.0 for r in win), 1),
            "max_err_m": round(max(werrs), 1) if werrs else None,
            "error95_m": round(float(np.percentile(errs, 95)), 1) if errs else None,
            "failsafe_s": None if fs is None else round(fs - a, 1),
            "false_refusal_s": round(0.2 * sum(r["guard"] == "REFUSED" and r["gps_mode"] == "ok" and r["gps_err_m"] != ""
                                               and float(r["gps_err_m"]) < 20.0 for r in rows), 1),
            "ap_max_err_m": round(max(fnum(r["ap_err_m"]) for r in rows if r["ap_err_m"]), 1)}


# ======================================================================== session 1 — Messenger
@c.test("TODO 1: decode_gps_input() on unseen payloads (some truncated), and refuses more than 65 bytes",
        hint="Lesson §3: pad with bytes(65 − len(payload)) first, then struct.unpack(GPS_INPUT_FORMAT, …), zip with "
             "GPS_INPUT_FIELDS, and divide lat and lon by 1e7.")
def _():
    (f,) = functions("navera_lite.output", "decode_gps_input")
    for case in U["decode"]:
        p = bytes.fromhex(case["payload"])
        got = go(f, p)
        if not isinstance(got, dict):
            raise CheckFailed(f"decode_gps_input(<{len(p)} bytes>) must return a dict, got {type(got).__name__}")
        for k, w in case["want"].items():
            if k not in got:
                raise CheckFailed(f"the dict has no key {k!r} (use the names of GPS_INPUT_FIELDS)")
            if k in ("lat", "lon") and same(got[k], w * 1e7, 1e-9):
                raise CheckFailed(f"{k} = {got[k]}: still in 1e-7 degrees — divide by 1e7 (10 000 000)")
            if k in ("lat", "lon") and isinstance(got[k], int) and not isinstance(got[k], bool):
                raise CheckFailed(f"{k} = {got[k]} is a whole number: divide by 1e7 with /, not // (the decimals "
                                  "are the position)")
            if not same(got[k], w, 1e-6):
                raise CheckFailed(f"on a payload of {len(p)} bytes, {k} = {got[k]!r} is wrong (struct format, field "
                                  "order, or the zero padding?)")
    try:
        run(f, bytes(70))
    except CheckFailed as e:
        if "ValueError" in str(e):
            return
        raise
    raise CheckFailed("decode_gps_input(<70 bytes>) must raise ValueError (a GPS_INPUT payload has at most 65 bytes)")


@c.test("TODO 2: parse_frames() on unseen byte streams (noise, a bad checksum, an unknown message, a signed frame, "
        "cut frames)",
        hint="Lesson §3 'reading a stream': skip to 0xFD; size = 10 + len + 2 (+13 if incompat_flags & 1); not enough "
             "bytes → skip; crc_ok from frame_crc(); after crc_ok True jump over the frame, otherwise resync at the "
             "next byte.")
def _():
    (f,) = functions("navera_lite.output", "parse_frames")
    for k, case in enumerate(U["parse"], 1):
        got = go(f, bytes.fromhex(case["data"]))
        if not isinstance(got, list) or not all(isinstance(d, dict) for d in got):
            raise CheckFailed(f"parse_frames() must return a list of dicts, got {got!r:.80}")
        want = case["want"]
        if len(got) != len(want):
            raise CheckFailed(f"stream {k}: {len(got)} frames found, not the right number (a frame cut by the end, a "
                              "signed frame's 13 extra bytes, or the resync after a failed checksum?)")
        if want and all(g.get("crc_ok") is False for g in got) and any(w["crc_ok"] for w in want):
            raise CheckFailed(f"stream {k}: every frame has crc_ok False — compare frame_crc(frame, msgid) with the "
                              "received checksum: bytes 10 + len and 11 + len, little-endian")
        for g, w in zip(got, want):
            for key in ("seq", "sysid", "compid", "msgid", "crc_ok"):
                if g.get(key) != w[key]:
                    raise CheckFailed(f"stream {k}: a frame's {key} is {g.get(key)!r}, not right"
                                      + (" (crc_ok is None when CRC_EXTRA has no entry for the msgid)" if key == "crc_ok"
                                         else " (msgid: 3 bytes, little-endian)" if key == "msgid" else ""))
            if bytes(g.get("payload", b"")) != bytes.fromhex(w["payload"]):
                raise CheckFailed(f"stream {k}: a frame's payload is wrong (bytes 10 … 10 + len)")


@c.test("TODO 3: lost_frames() on unseen sequences (wrap-around at 255 included)",
        hint="lost_frames: walk over consecutive pairs; b == a is doubled, else (b − a − 1) % 256 frames were lost.")
def _():
    (lost,) = functions("navera_lite.output", "lost_frames")
    for case in U["lost"]:
        got = go(lost, case["seqs"])
        if not (isinstance(got, (tuple, list)) and list(got) == case["want"]):
            msg = f"lost_frames({case['seqs']}) = {got!r} is wrong"
            if case["seqs"][:3] == [254, 255, 0]:
                msg += " — after 255 comes 0: count modulo 256"
            raise CheckFailed(msg)


@c.test("Steps 0–3: the recording through your decoder (answers.py)",
        hint="Copy the numbers `python3 mav_lab.py hex --answer` and `python3 mav_lab.py stream` print (with your "
             "finished TODOs 1–3). EXPLAIN_63: the trailing zero bytes; EXPLAIN_FLAGS: altitude and velocity not measured; "
             "EXPLAIN_LOST: a frame with a bad checksum is thrown away.")
def _():
    a = quiet("answers.py")
    s = LAB["stream"]
    predicted("PREDICT_FRAME", getattr(a, "PREDICT_FRAME", ""))
    answer_near("HEADER_LEN_BYTE", getattr(a, "HEADER_LEN_BYTE", 0), LAB["header_len"], 0, "the first frame's len byte")
    answer_near("STREAM_BAD_CRC", getattr(a, "STREAM_BAD_CRC", 0), s["bad_crc"], 0, "mav_lab.py stream (crc_ok False)")
    answer_near("STREAM_LOST", getattr(a, "STREAM_LOST", 0), s["lost_doubled"][0], 0, "your lost_frames")
    answer_near("STREAM_DOUBLED", getattr(a, "STREAM_DOUBLED", 0), s["lost_doubled"][1], 0, "your lost_frames")
    vis = [int(k) for k in s["flag_counts"] if int(k) & 1]
    answer_near("VISION_FLAGS", getattr(a, "VISION_FLAGS", 0), vis[0], 0, "the stream table (satellites 0)")
    explained("EXPLAIN_63", getattr(a, "EXPLAIN_63", ""), ([r"zero", r"0x00", r"00"], "the trailing zero bytes"),
              ([r"pad", r"add", r"fill", r"append", r"zeros? back"], "what the receiver must do (pad)"))
    explained("EXPLAIN_FLAGS", getattr(a, "EXPLAIN_FLAGS", ""), ([r"alt", r"height"], "the missing altitude"),
              ([r"veloc", r"speed"], "the missing velocity"),
              ([r"not measur", r"does not (know|measure|have)", r"no (alt|veloc|speed)", r"invent", r"unknown",
                r"doesn't (know|have)", r"cannot", r"can't"], "why it is honest (vision does not measure them)"))
    explained("EXPLAIN_LOST", getattr(a, "EXPLAIN_LOST", ""), ([r"crc", r"checksum"], "the checksum"),
              ([r"drop", r"discard", r"throw", r"reject", r"ignor", r"not used", r"skip", r"lost"],
               "that a damaged frame is thrown away, so its seq is missing"))


@c.test("TODO 4–5: gauss_markov() exactly on unseen seeds and starts, and stationary_sigma()",
        hint="Lesson §4: a = 1 − dt/τ; draw w = rng.standard_normal(n) ONCE, first; then x = a·x + q·√dt·w[k] and keep "
             "every new x. σ² = q²·dt / (1 − a²). Refuse dt ≤ 0 or dt ≥ 2τ (ValueError).")
def _():
    gm, st = functions("navera_lite.sim.sensors", "gauss_markov", "stationary_sigma")
    for case in U["gauss_markov"]:
        n, dt, tau, q, seed, x0 = case["args"]
        got = go(gm, n, dt, tau, q, np.random.default_rng(seed), x0)
        g = np.asarray(got, dtype=float) if got is not None else None
        if g is None or g.shape != (n,):
            raise CheckFailed(f"gauss_markov({n}, …) must return {n} numbers, got {got!r:.60}")
        w = np.asarray(case["want"])
        if not np.allclose(g, w, atol=1e-9):
            if np.allclose(g[1:], w[:-1], atol=1e-9) or abs(g[0] - x0) < 1e-12:
                raise CheckFailed("the first sample must already be one step after x0 (sample 0 = a·x0 + q·√dt·w[0])")
            raise CheckFailed(f"gauss_markov({n}, {dt}, {tau}, {q}, rng(seed {seed}), x0={x0}) is not right (draw all w "
                              "first with rng.standard_normal(n); √dt multiplies q; a = 1 − dt/τ)")
    for case in U["stationary"]:
        got = go(st, *case["args"])
        if not same(got, case["want"], 1e-6):
            raise CheckFailed(f"stationary_sigma{tuple(case['args'])} = {got!r} is wrong (σ² = q²dt/(1 − a²), then √)")
    for bad in ((0.0, 10.0, 1.0), (25.0, 10.0, 1.0)):
        try:
            run(st, *bad)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise
        raise CheckFailed(f"stationary_sigma{bad} must raise ValueError (|a| < 1 needs 0 < dt < 2τ)")


@c.test("TODO 6–7: autocorrelation() and rayleigh_quantile() on unseen inputs",
        hint="autocorrelation: subtract the mean, Σ d[i]·d[i+lag] over the overlap divided by Σ d² over the WHOLE "
             "series; lag outside 0 … len−1 → ValueError. rayleigh_quantile: σ·√(−2·ln(1 − p)).")
def _():
    ac, rq = functions("navera_lite.sim.sensors", "autocorrelation", "rayleigh_quantile")
    for case in U["autocorr"]:
        got = go(ac, case["x"], case["lag"])
        if not same(got, case["want"], 1e-6):
            raise CheckFailed(f"autocorrelation(<12 numbers>, {case['lag']}) = {got!r} is wrong (mean removed? divided "
                              "by the sum over the WHOLE series, not the overlap?)")
    try:
        run(ac, [1.0, 2.0, 3.0], 3)
    except CheckFailed as e:
        if "ValueError" not in str(e):
            raise
    else:
        raise CheckFailed("autocorrelation([1.0, 2.0, 3.0], 3) must raise ValueError (lag ≥ len)")
    for case in U["rayleigh"]:
        got = go(rq, *case["args"])
        if not same(got, case["want"], 1e-6):
            s, p = case["args"]
            hint = ""
            if same(got, s * math.sqrt(-2 * math.log(p)) if p > 0 else -1, 1e-6):
                hint = " — ln(1 − p), not ln(p)"
            raise CheckFailed(f"rayleigh_quantile({s}, {p}) = {got!r} is wrong{hint}")


@c.test("Steps 4–5: the noise and the vision errors, measured (answers.py)",
        hint="Copy what `python3 mav_lab.py noise` and `python3 mav_lab.py rayleigh` print. EXPLAIN_AVERAGE: the samples "
             "are correlated (τ = 20 s), so 50 of them are not 50 independent ones. EXPLAIN_MEDIAN: median = 1.177 σ.")
def _():
    a = quiet("answers.py")
    predicted("PREDICT_AVERAGE", getattr(a, "PREDICT_AVERAGE", ""))
    answer_near("GM_SIGMA_MEASURED", getattr(a, "GM_SIGMA_MEASURED", 0), LAB["gm_sigma"], 0.002, "mav_lab.py noise")
    answer_near("CORR_10S", getattr(a, "CORR_10S", 0), LAB["corr_10s"], 0.002, "mav_lab.py noise (lag 10 s)")
    predicted("PREDICT_RAYLEIGH_95", getattr(a, "PREDICT_RAYLEIGH_95", ""))
    explained("EXPLAIN_AVERAGE", getattr(a, "EXPLAIN_AVERAGE", ""),
              ([r"correl", r"depend", r"slow", r"previous", r"not independent", r"similar", r"memory"],
               "that the samples are correlated"),
              ([r"τ", r"tau", r"20 ?s", r"time", r"independent"], "the time scale (τ = 20 s)"))
    explained("EXPLAIN_MEDIAN", getattr(a, "EXPLAIN_MEDIAN", ""), ([r"median"], "the median"),
              ([r"1\.17", r"1\.18", r"rayleigh", r"√ ?\(?2", r"sqrt", r"ln ?2", r"log", r"per axis", r"each axis",
                r"two axes", r"east and north", r"2-?d", r"2d"],
               "the link median ↔ σ (1.177 σ for a 2-D error)"))


# ======================================================================== session 2 — Test engineer
@c.test("TODO 8: latencies() on unseen runs (a source of '' (none) counts as 'not GPS'; never → None)",
        hint="Lesson §5: next(...) over the rows with t_s ≥ t0 and lite_source != 'gps', minus t0; the same with t1 and "
             "== 'gps'; None when there is no such row, and recover_s None when t1 is None.")
def _():
    (f,) = functions("campaign.py", "latencies")
    for case in U["latencies"]:
        rows = [dict(r) for r in case["rows"]]
        got = go(f, rows, case["t0"], case["t1"])
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"latencies() must return two values, got {got!r}")
        if not same(list(got), case["want"], 1e-6):
            raise CheckFailed(f"latencies(<rows>, {case['t0']}, {case['t1']}) = {tuple(got)!r} is wrong"
                              + (" — t1 None means recover_s None" if case["t1"] is None else ""))


@c.test("TODO 9: verdict() on unseen values (None fails, the limit itself passes, wrong operator → ValueError)",
        hint="Lesson §5: <= means 'at most', >= 'at least'; None → (\"FAIL\", \"never happened\"); the text shows "
             "the value, the operator that holds (<=, >, >=, <) and the limit, with :g.")
def _():
    (f,) = functions("campaign.py", "verdict")
    for case in U["verdict"]:
        got = go(f, *case["args"])
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"verdict() must return (verdict, why), got {got!r}")
        if got[0] != case["want"][0]:
            raise CheckFailed(f"verdict{tuple(case['args'])} gives {got[0]!r}, not the right verdict")
        if got[1] != case["want"][1]:
            raise CheckFailed(f"verdict{tuple(case['args'])}: the text {got[1]!r} should be {case['want'][1]!r}")
    try:
        run(f, 1.0, "<", 2.0)
    except CheckFailed as e:
        if "ValueError" in str(e):
            return
        raise
    raise CheckFailed('verdict(1.0, "<", 2.0) must raise ValueError (only "<=" and ">=")')


@c.test("Your decoder in the autopilot: two hidden flights (other vehicle, night, GPS off, a blackout) fly as the "
        "course's reference",
        hint="The autopilot reads every byte with YOUR parse_frames and decode_gps_input: if a hidden flight goes wrong, "
             "check the no-fix frames (fix_type 1, short payload) and frames that arrive two at a time.")
def _():
    functions("navera_lite.output", "parse_frames", "decode_gps_input")
    tmp = tempfile.mkdtemp(prefix="m31_", dir=".")
    try:
        for fl in E["flights"]:
            sc = fl["scenario"]
            p = os.path.join(tmp, "s.json")
            with open(p, "w") as f:
                json.dump(sc, f)
            code, out = sh(f"python3 -m navera_lite.sim.run {p} --out {tmp} --quiet", timeout=120)
            if code:
                raise CheckFailed(f"the hidden flight {sc['name']}: {out.strip().splitlines()[-1][:220]}")
            rows = run_rows(os.path.join(tmp, sc["name"] + ".csv"))
            if len(rows) != fl["rows"]:
                raise CheckFailed(f"the hidden flight {sc['name']} gave {len(rows)} rows, not the reference's number: "
                                  "the autopilot read different positions (your decoder?)")
            w = fl["want"]
            ap = max(float(r["ap_err_m"]) for r in rows if r["ap_err_m"])
            fs = next((float(r["t_s"]) for r in rows if r["ap_mode"] in ("LAND", "HOLD")), None)
            if abs(ap - w["ap_max_err_m"]) > 0.15:
                raise CheckFailed(f"in the hidden flight {sc['name']} the autopilot's largest error is {ap:.1f} m, not "
                                  "the reference's: your decoder gives it other numbers")
            want_fs = None if w["failsafe_s"] is None else w["failsafe_s"] + w["t0_s"]
            if (fs is None) != (want_fs is None) or (fs is not None and abs(fs - want_fs) > 0.25):
                raise CheckFailed(f"in the hidden flight {sc['name']} the failsafe came at {fs}, not as in the reference")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@c.test("Steps 6 and 8: the jam's recovery, and expected values FROM THE RULES (written before the campaign)",
        hint="JAM_RECOVER_S from the events of campaign/jam.json. EXPECT_OFF_SWITCH_S: gps_timeout_s. EXPECT_JUMP_GATE_M: "
             "v_max·Δt + margin with the drone's 30 m/s and Δt 0.2 s. EXPECT_DRIFT_SIGMA_S_M and "
             "EXPECT_DRIFT_REFUSED_S: drift_alarm_time with the numbers of lab Step 8.")
def _():
    a = quiet("answers.py")
    predicted("PREDICT_JAM", getattr(a, "PREDICT_JAM", ""))
    answer_near("JAM_RECOVER_S", getattr(a, "JAM_RECOVER_S", 0), LAB["runs"]["jam"]["recover_s"], 0.21,
                "the jam run (GPS used again minus 70 s)")
    answer_near("EXPECT_OFF_SWITCH_S", getattr(a, "EXPECT_OFF_SWITCH_S", 0), LAB["expect_off_switch_s"], 0.21,
                "the GPS timeout rule (navera_lite.yaml)")
    answer_near("EXPECT_JUMP_GATE_M", getattr(a, "EXPECT_JUMP_GATE_M", 0), LAB["expect_jump_gate_m"], 0.6,
                "the jump gate's rule with v_max 30 m/s, Δt 0.2 s, margin 50 m")
    answer_near("EXPECT_DRIFT_SIGMA_S_M", getattr(a, "EXPECT_DRIFT_SIGMA_S_M", 0), LAB["drift_sigma_s"], 0.05,
                "the innovation's σ on one axis: the square root of the SUM of the three variances (GPS², vision², "
                "time gap²)")
    answer_near("EXPECT_DRIFT_REFUSED_S", getattr(a, "EXPECT_DRIFT_REFUSED_S", 0), LAB["expect_drift_s"], 0.01,
                "drift_alarm_time with lab Step 8's numbers")


@c.test("Step 9: the campaign flown with the course's parts, measured and judged (results.json from YOUR code)",
        hint="python3 campaign.py run, then python3 campaign.py report (TODOs 8–9 finished). Do not edit "
             "campaign/*.json: the requirements are the customer's. The runs are deterministic: same seeds, same numbers.")
def _():
    for fn, sc in E["scenarios"].items():
        got = read_json(os.path.join("campaign", fn), "the lab's scenario files must stay as they were shipped")
        if got != sc:
            raise CheckFailed(f"campaign/{fn} was changed: restore it (the campaign must fly the agreed scenarios)")
    res = read_json("results.json", "run python3 campaign.py report")
    runs = res.get("runs", {})
    for name in RUNS:
        if name not in runs:
            raise CheckFailed(f"results.json has no run {name!r}: fly the whole campaign (python3 campaign.py run)")
        rows = run_rows(os.path.join("my_runs", name + ".csv"))
        if len(rows) != LAB["rows"][name] or "# outcome" not in events(os.path.join("my_runs", name + "_events.log")):
            raise CheckFailed(f"my_runs/{name}.csv is not the course's run of campaign/{name}.json: fly it again with "
                              "python3 campaign.py run (without --mine)")
        for k in METRICS:
            if not same(runs[name].get(k), LAB["runs"][name][k], 1e-3):
                raise CheckFailed(f"results.json: {name}.{k} = {runs[name].get(k)!r} is not what the course's run "
                                  "gives — your latencies()? your decoder (checks 1–3, 10)? or results.json older than "
                                  "my_runs/: fly again (campaign.py run) and run report again")
    ver = {v.get("id"): v.get("verdict") for v in res.get("verdicts", [])}
    if ver != LAB["verdicts"]:
        raise CheckFailed("results.json: the verdicts are not right — run python3 campaign.py report again")


@c.test("Step 9: the FAIL diagnosed, and the fix confirmed with plane_delayed (and the drift explained)",
        hint="FAILED is the id printed FAIL. The plane's camera is 1.5 s late and its pictures are stamped when they "
             "arrive: lesson §5 'diagnose a FAIL'. Fly campaign/plane_delayed.json to confirm.")
def _():
    a = quiet("answers.py")
    if str(getattr(a, "FAILED", "")).strip().upper() != LAB["failed"][0]:
        raise CheckFailed("FAILED is not the id of the requirement that fails (look at the report's FAIL line)")
    answer_near("DRIFT_MEASURED_S", getattr(a, "DRIFT_MEASURED_S", 0), LAB["runs"]["drift"]["switch_s"], 0.01,
                "the drift run's switch_s in the report")
    explained("EXPLAIN_DRIFT", getattr(a, "EXPLAIN_DRIFT", ""),
              ([r"noise", r"random", r"luck", r"streak", r"reset", r"agree", r"latenc", r"0\.3", r"delay"],
               "why the run differs (noise breaks the streak, the vision latency)"),
              ([r"requir", r"margin", r"limit", r"rule", r"expect", r"theor"], "which value a requirement uses"))
    explained("EXPLAIN_FAIL", getattr(a, "EXPLAIN_FAIL", ""),
              ([r"stamp", r"time ?stamp", r"late", r"delay", r"old", r"1\.5"], "the late, wrongly stamped pictures"),
              ([r"60 ?m", r"behind", r"40 ?m/s", r"fast", r"speed", r"moved"], "that the plane moved 60 m meanwhile"),
              ([r"guard", r"refus", r"spoof", r"cross-?check", r"disagree"], "that the guard refused the honest GPS"))
    rows = run_rows(os.path.join("my_runs", "plane_delayed.csv"))
    if len(rows) != LAB["rows"]["plane_delayed"]:
        raise CheckFailed("my_runs/plane_delayed.csv is not the course's run of campaign/plane_delayed.json: fly it "
                          "again (without --mine)")
    refused = sum(r["guard"] == "REFUSED" and r["gps_mode"] == "ok" for r in rows)
    if refused:
        raise CheckFailed("my_runs/plane_delayed.csv shows the guard refusing the GPS: fly the file as shipped")


@c.test("Step 10: the campaign flown with YOUR parts (--mine), one rule of your guard changed, measured and compared",
        hint="python3 campaign.py run --mine --part spoof=my_spoof.py (a copy of your guard with ONE rule changed), then "
             "python3 campaign.py report --mine. Parts you have not finished fly as the course's (the events say so). "
             "EXPLAIN_MINE: which rule you changed, which requirement moved (or why none did).")
def _():
    res = read_json("results_mine.json", "run python3 campaign.py report --mine")
    runs = res.get("runs", {})
    changed = False
    for name in RUNS:
        log = events(os.path.join("my_runs", "mine", name + "_events.log"))
        if "# part arbiter:" not in log or "# outcome" not in log:
            raise CheckFailed(f"my_runs/mine/{name}_events.log was not written by the simulator: fly --mine again")
        m = re.search(r"^# part spoof: yours \((.*)\)$", log, re.M)
        changed = changed or bool(m and "30-spoofing" not in m.group(1))
        if name not in runs or not all(k in runs[name] for k in METRICS):
            raise CheckFailed(f"results_mine.json: the run {name} or its metrics are missing: run report --mine again")
        sc = E["scenarios"][name + ".json"]
        for k, want in given_metrics(run_rows(os.path.join("my_runs", "mine", name + ".csv")), sc).items():
            if not same(runs[name].get(k), want, 1e-3):
                raise CheckFailed(f"results_mine.json: {name}.{k} is not what my_runs/mine/{name}.csv gives — run "
                                  "python3 campaign.py report --mine again (after the last run --mine)")
    if not changed:
        raise CheckFailed("my_runs/mine/ was not flown with a changed copy of your guard: python3 campaign.py run --mine "
                          "--part spoof=my_spoof.py (lab Step 10), then report --mine")
    v = res.get("verdicts", [])
    if len(v) != 9:
        raise CheckFailed("results_mine.json must hold the 9 verdicts: run python3 campaign.py report --mine again")
    for x in v:
        val, op, lim = x.get("value"), x.get("op"), x.get("limit")
        ok = val is not None and ((val <= lim) if op == "<=" else (val >= lim))
        if x.get("verdict") != ("PASS" if ok else "FAIL"):
            raise CheckFailed(f"results_mine.json: the verdict of {x.get('id')} does not match its value")
    explained("EXPLAIN_MINE", getattr(quiet("answers.py"), "EXPLAIN_MINE", ""),
              ([r"refuse_n", r"p_fa", r"doubt_n", r"far_n", r"confirm_n", r"rule", r"threshold", r"guard", r"spoof"],
               "which rule of your guard you changed"),
              ([r"r\d", r"pass", r"fail", r"verdict", r"same", r"differ", r"chang", r"mov", r"metric", r"latenc",
                r"error", r"refus"], "which requirement moved (or why none did)"))


@c.test("Step 11: your networks measured (my_vision_profile.json, measured again by the check) and flown at night",
        hint="python3 vision_check.py (never edit my_vision_profile.json by hand: the check measures your night network "
             "again), then python3 -m navera_lite.sim.run campaign/night_mine.json --mine. NIGHT_MINE_MEDIAN_M is the "
             "night median vision_check printed.")
def _():
    prof = read_json("my_vision_profile.json", "run python3 vision_check.py")
    for light, n in (("day", 40), ("night", 80)):
        p = prof.get(light)
        if not isinstance(p, dict) or p.get("n") != n or "median_m" not in p:
            raise CheckFailed(f"my_vision_profile.json has no full '{light}' measurement: run vision_check.py again")
        if abs(p["sigma_m"] - p["median_m"] / math.sqrt(2 * math.log(2))) > 0.01:
            raise CheckFailed("my_vision_profile.json was edited by hand: run vision_check.py again")
    sha = (prof.get("weights_sha256") or {}).get("night")
    if not sha:
        raise CheckFailed("my_vision_profile.json was made by an older vision_check.py: run it again")
    # the night network measured again, with the course's own (read-only) copy of the tools: same seed, same places
    ro = "/academy/courses/31-simulator/files"
    code, out = sh(f"python3 -c \"import sys; sys.path.insert(0, '{ro}'); sys.argv = ['vision_check.py', "
                   f"'--night-only']; exec(open('{ro}/vision_check.py').read())\"", timeout=200)
    try:
        got = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise CheckFailed("the check could not measure your night network again: " + (out.strip()[-200:] or "no output"))
    if got.get("weights_sha256") != sha:
        raise CheckFailed("my_vision_profile.json was measured with other night weights than the ones you have now: "
                          "run vision_check.py again")
    if got.get("median_m") is None or abs(got["median_m"] - prof["night"]["median_m"]) > 0.05:
        raise CheckFailed("my_vision_profile.json is not what vision_check.py measures with your night network: run it "
                          "again (never edit the file by hand)")
    answer_near("NIGHT_MINE_MEDIAN_M", getattr(quiet("answers.py"), "NIGHT_MINE_MEDIAN_M", 0), prof["night"]["median_m"],
                0.06, "vision_check.py's night median")
    log = events(os.path.join("my_runs", "mine", "night_mine_events.log"))
    if '"vision": "mine"' not in log or "night weights" not in log or "# outcome" not in log:
        raise CheckFailed("my_runs/mine/night_mine_events.log is missing or not a 'mine' vision flight: fly "
                          "campaign/night_mine.json with --mine")
    m = re.search(r"^# part stated σ: .*night ([0-9.]+) m", log, re.M)
    if not m or abs(float(m.group(1)) - float(prof["night"]["stated_sigma_m"])) > 0.01:
        raise CheckFailed("my_runs/mine/night_mine was not flown with the σ of your current my_vision_profile.json: fly "
                          "campaign/night_mine.json --mine again")
    rows = run_rows(os.path.join("my_runs", "mine", "night_mine.csv"))
    if not any(r["lite_source"] == "night" for r in rows):
        raise CheckFailed("in my_runs/mine/night_mine.csv NAVERA Lite never flew on night vision: look at the events")
    explained("EXPLAIN_NETWORKS", getattr(quiet("answers.py"), "EXPLAIN_NETWORKS", ""),
              ([r"night", r"homograph", r"network", r"weights", r"model"], "what your night network did"),
              ([r"fix", r"degraded", r"25 ?m", r"state"], "the state your night source got (FIX or DEGRADED) and why"),
              ([r"optimis", r"same (map|picture|image)", r"cut from", r"synthetic", r"render", r"drawing", r"not real",
                r"simulat"], "why the numbers are optimistic (pictures cut from the matcher's own map)"),
              ([r"real", r"field", r"flight", r"camera", r"thermal"], "what an honest measurement needs"))


@c.test("Step 12: your own test (my_scenario.json, flown, judged) and what the campaign proves",
        hint="Change my_scenario.json (another name, at least one fault), fly it, measure it with "
             "python3 campaign.py one <name>, and write MY_METRIC, MY_OP, MY_LIMIT, MY_VALUE, MY_VERDICT.")
def _():
    sc = read_json("my_scenario.json", "the lab's file")
    name = sc.get("name") if isinstance(sc, dict) else None
    if not isinstance(name, str) or not name or name in [x.get("name") for x in E["scenarios"].values()]:
        raise CheckFailed("my_scenario.json: give it your own name (not one of the campaign's)")
    if not sc.get("faults"):
        raise CheckFailed("my_scenario.json has no fault: a test needs at least one")
    d = "my_runs"
    if not os.path.exists(os.path.join(d, name + "_events.log")):
        d = os.path.join("my_runs", "mine")
    log = events(os.path.join(d, name + "_events.log"))
    m = re.search(r"^# scenario: (.*)$", log, re.M)
    if not m or json.loads(m.group(1)) != sc:
        raise CheckFailed(f"{d}/{name}_events.log is not a flight of the current my_scenario.json: fly it again")
    a = quiet("answers.py")
    metric, op = getattr(a, "MY_METRIC", ""), getattr(a, "MY_OP", "")
    if metric not in METRICS:
        raise CheckFailed(f"MY_METRIC must be one of {', '.join(METRICS)}, got {metric!r}")
    if op not in ("<=", ">="):
        raise CheckFailed('MY_OP must be "<=" or ">="')
    lim = number(getattr(a, "MY_LIMIT", None), "MY_LIMIT")
    val = getattr(a, "MY_VALUE", 0.0)
    val = None if val is None else number(val, "MY_VALUE")
    want = "FAIL" if val is None else ("PASS" if ((val <= lim) if op == "<=" else (val >= lim)) else "FAIL")
    if str(getattr(a, "MY_VERDICT", "")).strip().upper() != want:
        raise CheckFailed("MY_VERDICT does not follow from MY_VALUE, MY_OP and MY_LIMIT")
    explained("EXPLAIN_MY_TEST", getattr(a, "EXPLAIN_MY_TEST", ""),
              ([r"gps", r"camera", r"imu", r"night", r"jam", r"spoof", r"drift", r"bias", r"blackout", r"late", r"off"],
               "the fault you injected"),
              ([r"requir", r"limit", r"because", r"should", r"must", r"expect", r"so that", r"margin", r"bias"],
               "why this requirement"))
    explained("EXPLAIN_PROVES", getattr(a, "EXPLAIN_PROVES", ""),
              ([r"behavio", r"logic", r"rule", r"timing", r"integration", r"switch", r"decod", r"autopilot"],
               "what it proves (behaviour: rules, timing, integration)"),
              ([r"not .*accura", r"accuracy", r"real", r"field", r"optimis", r"model"],
               "what it does not prove (real accuracy, real sensors)"))


c.milestone("Messenger", "TODO 1", "TODO 2", "TODO 3", "Steps 0", "TODO 4", "TODO 6", "Steps 4", label="📡 Messenger")
c.milestone("Test engineer", "TODO", "Step", "Your decoder", label="🧪 Test engineer")
c.run()
