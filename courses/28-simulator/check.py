import json
import math
import os
from datetime import datetime, timezone

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
DATA = "/data/academy/28-simulator"
CAMP = f"{DATA}/campaign"
STREAM = f"{DATA}/gps_input.bin"

# Expected values, computed once from the recorded data (not the code that computes them).
BAD_SEQS = {115, 45, 205}                  # seq (mod 256) of the three damaged GPS_INPUT frames
FLIGHT_ROWS = {"jam_spoof_target": 393, "drift_target": 231, "off_target": 186,
               "jam_camfail_target": 196, "jam_spoof_measured": 269}
INTERVALS = {"jam_spoof_target": [(110.8, 171.2, "jammed"), (210.6, 240.8, "spoof_jump")],
             "drift_target": [(110.9, 190.8, "spoof_drift")], "off_target": [(111.8, 151.1, "off")],
             "jam_camfail_target": [(112.1, 171.7, "jammed")]}
ALL_INTERVALS = dict(INTERVALS, jam_spoof_measured=[(110.8, 171.3, "jammed"), (210.6, 240.9, "spoof_jump")])
# flight, fault -> (switch_s, recovery_s, availability, err_p50_m, err_p95_m, spoof_leak_s, gps_err_max_m)
FAULTS = {
    ("jam_spoof_target", "jammed"): (0.0, 2.0, 1.0, 20.0, 33.0, 0, None),
    ("jam_spoof_target", "spoof_jump"): (1.0, 4.1, 1.0, 18.7, 34.9, 0, 2.9),
    ("jam_spoof_measured", "jammed"): (0.0, 2.0, 1.0, 426.9, 851.8, 0, None),
    ("jam_spoof_measured", "spoof_jump"): (0.0, 2.0, 1.0, 550.1, 915.2, 0, None),
    ("drift_target", "spoof_drift"): (18.3, 3.1, 1.0, 19.8, 58.1, 0, 72.8),
    ("off_target", "off"): (2.1, 1.0, 1.0, 17.9, 30.6, 0, 32.0),
    ("jam_camfail_target", "jammed"): (0.0, 0.0, 0.362, 23.1, 38.0, 0, None),
}
CAMPAIGN_PASS = 22


def M():
    return load_student("mavlink_lab.py")


def S():
    return load_student("sensor_models.py")


def C():
    return load_student("campaign.py")


def frames():
    (pf,) = need(M(), "parse_frames")
    with open(STREAM, "rb") as f:
        fr = pf(f.read())
    if not fr:
        raise CheckFailed("parse_frames() returned no frame (TODO 2)")
    return fr


def no_simulator():
    try:
        return bool(getattr(load_student("answers.py"), "NO_SIMULATOR", False))
    except Exception:
        return False


def close(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def pymav_frame(msg_kwargs, seq=7):
    """A GPS_INPUT frame packed by pymavlink (the reference implementation of MAVLink)."""
    from pymavlink.dialects.v20 import ardupilotmega as mav2

    class Buf:
        data = b""

        def write(self, b):
            self.data += b
    buf = Buf()
    mav = mav2.MAVLink(buf, srcSystem=42, srcComponent=7)
    mav.seq = seq
    mav.gps_input_send(**msg_kwargs)
    return buf.data, mav2


GPS_KW = dict(time_usec=1791368008123456, gps_id=0, ignore_flags=57, time_week_ms=123456789, time_week=2439,
              fix_type=3, lat=233456789, lon=581234567, alt=0.0, hdop=7.5, vdop=15.0, vn=0.0, ve=0.0, vd=0.0,
              speed_accuracy=0.0, horiz_accuracy=15.0, vert_accuracy=30.0, satellites_visible=0)


# ---------------- Part A ----------------
@c.test("A1. crc_x25(): the CRC-16/MCRF4XX of MAVLink",
        hint="Apply the three lines of the lesson (section 3) to every byte, starting from crc. Keep tmp on "
             "8 bits and crc on 16 bits with masks, or the numbers grow without limit.")
def _():
    (crc,) = need(M(), "crc_x25")
    c.eq(crc(b"123456789"), 0x6F91, "crc_x25(b'123456789')")
    c.eq(crc(b""), 0xFFFF, "crc_x25(b'') (nothing processed)")
    hb = bytes.fromhex("fd0900000001bf000000000000001208000403")
    got = crc(bytes([50]), crc(hb[1:]))
    c.eq(got, 0xC6AE, "the CRC of the first HEARTBEAT of gps_input.bin (with CRC_EXTRA 50)")


@c.test("A2. parse_frames(): every frame of gps_input.bin, with its header and crc_ok",
        hint="msgid is 3 bytes little-endian. The CRC starts at byte i+1 and stops at the end of the payload, "
             "then continues with the single byte CRC_EXTRA[msgid]. The received checksum is little-endian too. "
             "seq counts modulo 256.")
def _():
    fr = frames()
    c.eq(len(fr), 784, "number of frames in gps_input.bin")
    f0, f1 = fr[0], fr[1]
    for k in ("seq", "sysid", "compid", "msgid", "payload", "crc_ok"):
        c.ok(k in f0, f"a frame dict has no key '{k}'")
    c.eq((f0["sysid"], f0["compid"], f0["msgid"], len(f0["payload"])), (1, 191, 0, 9),
         "(sysid, compid, msgid, payload length) of frame 0")
    c.eq((f1["msgid"], len(f1["payload"]), f1["seq"]), (232, 62, 1), "(msgid, payload length, seq) of frame 1")
    bad = {f["seq"] for f in fr if f["crc_ok"] is False}
    c.eq(bad, BAD_SEQS, "the seq numbers of the frames with a bad CRC")
    c.ok(sum(1 for f in fr if f["crc_ok"] is True) == 781, "781 frames should have crc_ok True")


@c.test("A3. parse_frames() is robust: garbage before a frame, unknown message ids",
        hint="Bytes that are not 0xFD: skip them one by one. An msgid not in CRC_EXTRA: crc_ok = None "
             "(you cannot check it), but keep parsing after it.")
def _():
    (pf,) = need(M(), "parse_frames")
    good, _ = pymav_frame(GPS_KW, seq=9)
    unknown = bytes.fromhex("fd0400000a0203" + "1e0000") + b"\x01\x02\x03\x04" + b"\x00\x00"   # msgid 30
    data = b"\x00\x13\x37" + good + unknown + good
    fr = pf(data)
    c.eq([f["msgid"] for f in fr], [232, 30, 232], "msgids found in garbage + GPS_INPUT + unknown + GPS_INPUT")
    c.eq([f["crc_ok"] for f in fr], [True, None, True], "crc_ok of those three frames")
    c.eq((fr[0]["sysid"], fr[0]["compid"], fr[0]["seq"]), (42, 7, 9), "(sysid, compid, seq) of the first frame")


@c.test("A4. decode_gps_input(), ignored(), gps_time_to_utc()",
        hint="MAVLink 2 cuts the trailing zero bytes: pad the payload back to GPS_INPUT_LEN before unpacking. "
             "lat/lon are degrees x 1e7. GPS time = GPS epoch + weeks + milliseconds, minus the 18 leap seconds.")
def _():
    m = M()
    dec, ign, gtu = need(m, "decode_gps_input", "ignored", "gps_time_to_utc")
    frame, mav2 = pymav_frame(GPS_KW)
    payload = frame[10:10 + frame[1]]
    c.ok(len(payload) < 65, "test set-up: the payload should be truncated")
    d = dec(payload)
    c.ok(isinstance(d, dict), f"decode_gps_input() should return a dict, got {type(d).__name__}")
    c.near(d.get("lat"), 23.3456789, 1e-9, "lat (degrees) of a truncated frame")
    c.near(d.get("lon"), 58.1234567, 1e-9, "lon (degrees)")
    c.eq((d.get("fix_type"), d.get("ignore_flags"), d.get("satellites_visible")), (3, 57, 0),
         "(fix_type, ignore_flags, satellites_visible)")
    c.near(d.get("horiz_accuracy"), 15.0, 1e-6, "horiz_accuracy")
    c.eq(ign(57), ["ALT", "VEL_HORIZ", "VEL_VERT", "SPEED_ACCURACY"], "ignored(57)")
    c.eq(ign(0), [], "ignored(0)")
    c.eq(ign(255)[-1], "VERTICAL_ACCURACY", "ignored(255)[-1]")
    t = gtu(2439, 296126700)
    c.ok(isinstance(t, datetime), f"gps_time_to_utc() should return a datetime, got {t!r}")
    c.eq(t, datetime(2026, 10, 7, 10, 15, 8, 700000, tzinfo=timezone.utc), "gps_time_to_utc(2439, 296126700)")


# ---------------- Part B ----------------
@c.test("B1. gauss_markov() and stationary_sigma()",
        hint="Draw all the n_steps random numbers first (default_rng(seed).standard_normal), then apply the "
             "recursion of the lesson starting from x0 (x0 is the value BEFORE the first step). "
             "stationary_sigma: the formula of section 4, with a = 1 - dt/tau.")
def _():
    gm, ss = need(S(), "gauss_markov", "stationary_sigma")
    x = gm(1000, seed=0)
    c.eq(len(x), 1000, "len(gauss_markov(1000))")
    c.near(x[0], 0.033736959, 1e-6, "gauss_markov(1000, seed=0)[0]")
    c.near(x[999], -5.015986001, 1e-6, "gauss_markov(1000, seed=0)[999]")
    x2 = gm(500, dt=0.1, tau=5.0, q=1.0, seed=7, x0=3.0)
    c.near(x2[0], 2.940389009, 1e-6, "gauss_markov(500, dt=0.1, tau=5, q=1, seed=7, x0=3)[0]")
    c.near(x2[499], -4.126335397, 1e-6, "... [499]")
    c.near(ss(), 1.9024, 0.001, "stationary_sigma() with the simulator's values")
    c.near(ss(0.1, 5.0, 1.0), 1.589104, 1e-5, "stationary_sigma(0.1, 5, 1)")


@c.test("B2. autocorrelation(): theory a^m confirmed",
        hint="Remove the mean first; divide the sum of the products of samples `lag` apart by the sum of the "
             "squares. lag 0 is 1 by definition.")
def _():
    gm, ac = need(S(), "gauss_markov", "autocorrelation")
    c.near(ac([1, 2, 3, 4, 5, 4, 3, 2, 1], 2), -0.0134921, 1e-6, "autocorrelation([1,2,3,4,5,4,3,2,1], 2)")
    c.near(ac([3.0, 1.0, 2.0], 0), 1.0, 1e-12, "autocorrelation(x, 0)")
    x = gm(200000, seed=0)
    c.near(ac(x, 100), 0.36701, 1e-4, "autocorrelation(gauss_markov(200000, seed=0), 100)")


@c.test("B3. Rayleigh quantiles and the lagged-vision Monte Carlo",
        hint="The quantile formula is in section 4; invert it for p = 0.5. Monte Carlo: one generator from the "
             "seed, draw east, north and the lag in that order (the order changes the numbers).")
def _():
    rq, sfm, lag = need(S(), "rayleigh_quantile", "sigma_for_median", "lagged_vision_errors")
    import numpy as np
    c.near(rq(15.0, 0.5), 17.6611, 0.001, "rayleigh_quantile(15, 0.5)")
    c.near(rq(3.0, 0.9), 6.43790, 1e-4, "rayleigh_quantile(3, 0.9)")
    c.near(sfm(440.0), 373.69, 0.05, "sigma_for_median(440)")
    c.near(sfm(100.0), 84.9322, 1e-3, "sigma_for_median(100)")
    e = lag(15.0, 15.0, 1.0)
    c.eq(len(e), 20000, "len(lagged_vision_errors(15, 15, 1))")
    c.near(float(np.median(e)), 18.9623, 0.001, "median of lagged_vision_errors(15, 15, 1)")
    c.near(float(np.median(lag(20.0, 40.0, 2.0, n=30000, seed=5))), 45.8010, 0.001,
           "median of lagged_vision_errors(20, 40, 2, n=30000, seed=5)")


# ---------------- Part C ----------------
@c.test("C1. load_flight() and nav_error(): robust to missing columns",
        hint="A missing column and an empty cell must both become None (dict.get helps). A missing camera "
             "column means 'ok'. nav_error compares NAVERA's coordinates with the truth's.")
def _():
    lf, ne = need(C(), "load_flight", "nav_error")
    for name, n in FLIGHT_ROWS.items():
        rows = lf(f"{CAMP}/{name}.csv")
        c.eq(len(rows), n, f"rows in {name}.csv")
    rows = lf(f"{CAMP}/jam_spoof_measured.csv")
    r = rows[150]
    c.ok(isinstance(r["t_s"], float) and isinstance(r["truth_lat"], float), "t_s and truth_lat should be floats")
    c.ok(r.get("navera_err_m", "x") is None, "a missing column (navera_err_m) should give None")
    c.eq(r.get("camera"), "ok", "camera of a flight without a camera column")
    c.ok(rows[0]["navera_lat"] is None, "an empty cell should be None")
    c.eq(ne(rows[0]), None, "nav_error() of a row without NAVERA position")
    t = lf(f"{CAMP}/jam_spoof_target.csv")
    c.near(ne(t[100]), t[100]["navera_err_m"], 0.15, "nav_error() vs the simulator's own error column (row 100)")


@c.test("C2. fault_intervals(): when each fault started and ended",
        hint="Track the start and the value of the current run; close it when the value changes "
             "(to normal OR to another fault); close a run still open at the end with the last t_s.")
def _():
    lf, fi = need(C(), "load_flight", "fault_intervals")
    for name, want in INTERVALS.items():
        got = fi(lf(f"{CAMP}/{name}.csv"), "gps_mode")
        c.eq([tuple(x) for x in got or []], want, f"fault_intervals({name}, 'gps_mode')")
    mk = lambda t, v: {"t_s": float(t), "g": v}       # noqa: E731
    rows = [mk(0, "ok"), mk(1, "jammed"), mk(2, "spoof_jump"), mk(3, "ok"), mk(4, "off"), mk(5, "off")]
    c.eq([tuple(x) for x in fi(rows, "g") or []], [(1.0, 2.0, "jammed"), (2.0, 3.0, "spoof_jump"), (4.0, 5.0, "off")],
         "fault_intervals of ok, jammed, spoof_jump, ok, off, off")
    c.eq([tuple(x) for x in fi(rows[:1], "g") or []], [], "fault_intervals with no fault")


@c.test("C3. first_time(), switch_latency(), recovery_latency()",
        hint="first_time scans the rows from `after` and calls condition(row). The two latencies are first_time "
             "with the right lambda, minus the start time — and None when it never happens.")
def _():
    lf, ft, sw, rc = need(C(), "load_flight", "first_time", "switch_latency", "recovery_latency")
    rows = lf(f"{CAMP}/drift_target.csv")
    c.near(sw(rows, 110.9), 18.3, 0.05, "switch_latency(drift, 110.9)")
    c.near(rc(rows, 190.8), 3.1, 0.05, "recovery_latency(drift, 190.8)")
    rows = lf(f"{CAMP}/off_target.csv")
    c.near(sw(rows, 111.8), 2.1, 0.05, "switch_latency(off, 111.8)")
    c.near(ft(rows, lambda r: r["phase"] == "enroute", 0.0), 79.9, 0.2, "first_time(off, phase == 'enroute')")
    mk = lambda t, s: {"t_s": float(t), "navera_source": s}      # noqa: E731
    only_gps = [mk(0, "GPS"), mk(1, "GPS")]
    c.eq(sw(only_gps, 0.0), None, "switch_latency when NAVERA never leaves GPS")
    c.eq(rc([mk(0, "DAY VISION"), mk(1, "—")], 0.0), None, "recovery_latency when GPS never comes back")


@c.test("C4. availability(), error_stats(), spoof_leak_s(), gps_err_max() on every fault of the campaign",
        hint="Every metric uses the rows with t0 <= t_s < t1 (t1 excluded). Skip rows whose error is None. "
             "A row counts as available when NAVERA is FIX or DEGRADED AND has a latitude.")
def _():
    m = C()
    lf, av, es, sl, gm = need(m, "load_flight", "availability", "error_stats", "spoof_leak_s", "gps_err_max")
    wrong = []
    for (name, kind), (_sw, _rc, a, p50, p95, leak, gmax) in FAULTS.items():
        rows = lf(f"{CAMP}/{name}.csv")
        t0, t1, _ = next(x for x in ALL_INTERVALS[name] if x[2] == kind)
        stats = es(rows, t0, t1) or (None, None, None)
        got = (av(rows, t0, t1), stats[0], stats[1], sl(rows, t0, t1), gm(rows, t0, t1))
        want = (a, p50, p95, leak, gmax)
        tols = (0.002, 0.06, 0.06, 0, 0.06)
        for label, g, w, tol in zip(("availability", "p50", "p95", "leak", "gps_err_max"), got, want, tols):
            if not close(g, w, tol):
                wrong.append(f"{name}/{kind} {label} = {g!r} (expected {w})")
    c.ok(not wrong, "; ".join(wrong[:4]))
    c.eq(es([], 0, 1), (None, None, None), "error_stats() with no rows")


@c.test("C5. REQUIREMENTS has R7, and the whole campaign gives 22 PASS, 0 FAIL",
        hint="TODO 7: copy the shape of R1-R6: applies to 'spoof_drift', measured key 'gps_err_max_m', and a "
             "test that PASSES up to 150 m and FAILS for None.")
def _():
    m = C()
    reqs, verdicts = need(m, "REQUIREMENTS", "verdicts")
    r7 = [r for r in reqs if r[0] == "R7"]
    c.ok(len(r7) == 1, "REQUIREMENTS should contain exactly one 'R7'")
    _, applies, _, key, test = r7[0]
    c.eq((applies, key), ("spoof_drift", "gps_err_max_m"), "(applies to, measured key) of R7")
    c.ok(test(72.8) is True and test(150.0) is True and test(151.0) is False and test(None) is False,
         "R7's test: 72.8 and 150 PASS, 151 and None FAIL")
    base = dict(column="gps_mode", camera_ok=True, switch_s=0.0, recovery_s=2.0, availability=1.0, spoof_leak_s=0,
                ap_modes=["GUIDED"])
    v = verdicts(dict(base, fault="spoof_drift", gps_err_max_m=200.0))
    c.ok(("R7", "FAIL") in [(x[0], x[3]) for x in v], "a drift that dragged NAVERA 200 m must FAIL R7")
    old = os.getcwd()
    try:
        os.chdir("/tmp")          # (no my_runs/ there: the recorded campaign only)
        _res, n_pass, n_fail = m.campaign_results()
    finally:
        os.chdir(old)
    c.eq((n_pass, n_fail), (CAMPAIGN_PASS, 0), "(PASS, FAIL) over the recorded campaign")


@c.test("C6. results.json: the campaign, the MAVLink summary and the models",
        hint="Run `python3 campaign.py` again after finishing Parts A, B and C (it writes results.json).")
def _():
    c.file_exists("results.json")
    with open("results.json") as f:
        r = json.load(f)
    camp = r.get("campaign") or {}
    for (name, kind), (sw, rc, a, p50, p95, leak, gmax) in FAULTS.items():
        fs = [x for x in camp.get(name, []) if x.get("fault") == kind]
        c.ok(fs, f"results.json has no fault '{kind}' for the flight {name}")
        f = fs[0]
        for key, want, tol in (("switch_s", sw, 0.05), ("recovery_s", rc, 0.05), ("err_p50_m", p50, 0.06)):
            c.ok(close(f.get(key), want, tol), f"{name}/{kind}: {key} = {f.get(key)!r}, expected {want}")
    cam = [x for x in camp.get("jam_camfail_target", []) if x.get("fault") == "failed"]
    c.ok(cam and close(cam[0].get("nofix_s"), 4.1, 0.05) and "LAND" in cam[0].get("ap_modes", []),
         "jam_camfail_target / camera failed: nofix_s 4.1 and the autopilot in LAND expected")
    mv = r.get("mavlink") or {}
    c.eq((mv.get("frames"), mv.get("bad_crc"), mv.get("lost_frames"), mv.get("fix_3d")), (784, 3, 2, 385),
         "results.json mavlink (frames, bad_crc, lost_frames, fix_3d)")
    md = r.get("models") or {}
    c.ok(close(md.get("target_median_m"), 17.66, 0.01) and close(md.get("lagged_median_m"), 19.0, 0.06)
         and close(md.get("gm_sigma_theory_m"), 1.902, 0.002), f"results.json models are not right yet: {md}")


@c.test("C7. answers.py", hint="Q1: read the times in off_target_events.log. Q2: v x t. Q3: the kinematic gate. "
                               "Q4: add the bit values. Q5: lesson 25. Q6: lesson section 6.")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, want, tol in (("Q1", 3.0, 0.5), ("Q2", 45.0, 1.0), ("Q3", 56.0, 0.5), ("Q4", 189, 0)):
        (v,) = need(m, q)
        if not close(v, want, tol):
            wrong.append(f"{q} = {v!r}")
    for q, want in (("Q5", "b"), ("Q6", "a")):
        (v,) = need(m, q)
        if str(v).strip().lower().strip(")") != want:
            wrong.append(f"{q} = {v!r}")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


# ---------------- Part D ----------------
@c.test("D. report.md: five sections, ~350 words, your key numbers, behaviour vs accuracy",
        hint="Keep the five headings; write in the Set-up, Results, Observations, Fidelity and Next campaign "
             "sections; quote gps_err_max_m of the drift, target_median_m, lagged_median_m and the PASS total "
             "from results.json; say in Fidelity that these are behaviour results.")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8", errors="replace").read()
    low = text.lower()
    heads = ("## 1. set-up", "## 2. results", "## 3. observations", "## 4. fidelity", "## 5. next campaign")
    missing = [h for h in heads if h not in low]
    c.ok(not missing, f"missing section(s): {missing}")
    import re
    try:
        template = open("/academy/courses/28-simulator/files/report.md", encoding="utf-8").read()
    except OSError:
        template = ""
    template_lines = {ln.strip() for ln in template.splitlines() if ln.strip()}
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    body = "\n".join(ln for ln in body.splitlines() if ln.strip() not in template_lines)
    body = re.sub(r"\(What was simulated.*?\)|\(A table: one line.*?\)|\(At least these three.*?\)|"
                  r"\(What this campaign proves.*?\)|\(Two or three scenarios.*?\)", "", body, flags=re.S)
    words = len(re.findall(r"[A-Za-z0-9]+", body))
    c.ok(words >= 350, f"report.md has about {words} words of your own; at least 350 expected")
    fid = low.split("## 4. fidelity", 1)[1].split("## 5.", 1)[0]
    c.ok("behaviour" in fid or "behavior" in fid, "the Fidelity section should say these are behaviour results")
    try:
        r = json.load(open("results.json"))
    except Exception:
        raise CheckFailed("results.json is missing or broken: run python3 campaign.py first")
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    vals = [float(x) for x in nums]

    def has(v, tol):
        return any(abs(x - v) <= tol for x in vals)
    gmax = next((f.get("gps_err_max_m") for f in r.get("campaign", {}).get("drift_target", [])
                 if f.get("fault") == "spoof_drift"), None)
    md = r.get("models") or {}
    need_nums = [("the drift's gps_err_max_m", gmax, 0.6), ("target_median_m", md.get("target_median_m"), 0.06),
                 ("lagged_median_m", md.get("lagged_median_m"), 0.06),
                 ("the number of PASS verdicts", r.get("requirements_pass"), 0)]
    miss = [label for label, v, tol in need_nums if v is None or not has(float(v), tol)]
    c.ok(not miss, "report.md does not quote: " + ", ".join(miss))


# ---------------- Part E ----------------
@c.test("E. your own scripted run in the simulator (my_runs/)",
        hint="Part E: take the simulator, run `python3 sim_ctl.py campaign my_scenario.json --out-dir my_runs`, then "
             "`python3 campaign.py`. No simulator today? Set NO_SIMULATOR = True in answers.py.")
def _():
    if no_simulator():
        c.skip("NO_SIMULATOR = True: graded on the recorded campaign only")
    import glob
    runs = sorted(glob.glob("my_runs/*.csv"))
    c.ok(runs, "my_runs/ has no flight CSV yet (Step 14)")
    lf, fi = need(C(), "load_flight", "fault_intervals")
    ok = False
    for p in runs:
        rows = lf(p)
        enroute = sum(1 for x in rows if x.get("phase") == "enroute")
        faults = (fi(rows, "gps_mode") or []) + (fi(rows, "camera") or [])
        ok = ok or (enroute >= 30 and len(faults) >= 1)
    c.ok(ok, "no run in my_runs/ has 30 s en route and an injected fault")
    r = json.load(open("results.json")) if os.path.exists("results.json") else {}
    c.ok(any(k.startswith("my_runs/") for k in r.get("campaign", {})),
         "results.json does not include your run: run python3 campaign.py again")


c.run()
