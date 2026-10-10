import json
import math
import os
import re
import shutil
import tempfile

from academy_check import Checker, load_student, need, sh

c = Checker()
LOG = "/data/academy/15-gps-nmea/sousse_drive.nmea"
TEXTBOOK = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
NEO = "$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70"   # NAVERA's real receiver
RMC = "$GPRMC,051217.00,A,3549.61531,N,01038.52535,E,11.88,136.6,121026,,,A*5F"
NOFIX = "$GPGGA,052009.00,,,,,0,00,99.99,,,,,,*68"
SWAP60 = "$GPGGA,051731.00,3574.17098,N,01041.88184,E,1,11,0.85,10.9,M,32.0,M,,*62"
GSA = "$GPGSA,A,3,02,05,07,09,13,20,23,24,30,,,,1.98,1.15,1.61*0C"
GSA_NOFIX = "$GPGSA,A,1,,,,,,,,,,,,,99.99,99.99,99.99*30"
GSV = "$GPGSV,3,2,12,13,72,160,48,15,24,200,,18,12,225,,20,40,253,42*7C"


def cs(body):
    x = 0
    for ch in body:
        x ^= ord(ch)
    return f"${body}*{x:02X}"


def nt():
    return load_student("nmea_tools.py")


def saved_results():
    if not os.path.exists("results.json"):
        c.ok(False, "results.json does not exist yet — run python3 analyze_drive.py (Step 8)")
    try:
        with open("results.json") as f:
            return json.load(f)
    except ValueError as e:
        c.ok(False, f"results.json is not valid JSON ({e}) — run python3 analyze_drive.py again")


_fresh = {}
GRADED = ("lines_total", "lines_rejected", "gga_by_quality", "navera_valid", "jump_rejected_utc", "fixes_accepted",
          "dop_epochs_compared", "dop_max_abs_diff", "outage_s", "outage_from_utc", "outage_to_utc", "hdop_max",
          "uere_est_m", "frac_within_2drms", "track_length_m")


def results():
    """The numbers of YOUR analyze_drive.py, run again now in a scratch folder with your nmea_tools.py,
    dop.py and gps_filter.py — and the saved results.json must agree with them."""
    if "r" not in _fresh:
        saved = saved_results()
        tmp = tempfile.mkdtemp(prefix="check15_")
        try:
            for f in ("analyze_drive.py", "nmea_tools.py", "dop.py", "gps_filter.py"):
                c.ok(os.path.exists(f), f"{f} is missing (↺ Reset lab files gives it back)")
                shutil.copy(f, tmp)
            code, out = sh(f"cd {tmp} && MPLBACKEND=Agg python3 -B analyze_drive.py", timeout=40)
            c.ok(code == 0 and os.path.exists(os.path.join(tmp, "results.json")),
                 "python3 analyze_drive.py did not finish:\n" + out[-600:])
            with open(os.path.join(tmp, "results.json")) as f:
                fresh = json.load(f)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        diff = [k for k in GRADED if saved.get(k) != fresh.get(k)]
        c.ok(not diff, f"results.json does not match what your code gives now for {', '.join(diff)}: "
                       "run python3 analyze_drive.py again (and never edit results.json by hand)")
        _fresh["r"] = fresh
    return _fresh["r"]


@c.test("nmea_checksum(): XOR of the body, 2 upper-case hex digits",
        hint="Start from 0, XOR (^) the ord() of every character, format with :02X (13 must give \"0D\").")
def _():
    (f,) = need(nt(), "nmea_checksum")
    got = f(TEXTBOOK)
    c.ok(isinstance(got, str), f"nmea_checksum should return text like \"47\", it returned {got!r}")
    for body, want in [(TEXTBOOK, "47"), ("GPGSA,A,1", "32"), ("", "00"),
                       ("GNGSA,A,3,05,13,15,18,20,23,24,29,,,,,1.32,0.82,1.03,1", "0D")]:
        c.eq(f(body), want, f"nmea_checksum({body[:24]!r}…)")


@c.test("is_valid() accepts correct sentences (with \\r\\n, lower-case hex)",
        hint="strip() first; the body is between \"$\" and the first \"*\"; compare with the 2 characters "
             "after \"*\" in upper case.")
def _():
    (f,) = need(nt(), "is_valid")
    for line in ("$" + TEXTBOOK + "*47", NEO, NEO + "\r\n", RMC, NOFIX, GSA[:-2] + "0c", SWAP60):
        got = f(line)
        c.ok(got is True, f"is_valid({line[:40]!r}…) should be True, got {got!r}")


@c.test("is_valid() refuses every kind of damaged line — and never crashes",
        hint="Return False (not None) for: no \"$\", no \"*\", not exactly 2 characters after \"*\", wrong "
             "checksum, a \"$\" inside the body (glued lines), more than MAX_SENTENCE_LEN characters, "
             "or something that is not a string.")
def _():
    (f,) = need(nt(), "is_valid")
    long_line = cs("GPTXT,01,01,02," + "A" * 70)
    bad = {"a changed digit": NEO.replace("95.3", "96.3"),
           "no checksum": NEO.split("*")[0],
           "no $": NEO[1:],
           "a cut line": NEO[:31],
           "a checksum that is not hex": "$GP#@!~~,,0,12,,1.0*ZZ",
           "a 1-digit checksum": NEO[:-1],
           "an empty line": "",
           "two glued sentences": "$GPGGA,052040.00,3546.15064,N,01044.0170" + RMC,
           f"a line of {len(long_line)} characters": long_line,
           "a non-ASCII character": NEO.replace("3544", "35�4"),
           "None": None}
    for why, line in bad.items():
        try:
            got = f(line)
        except Exception as e:
            c.ok(False, f"is_valid crashed on {why}: {type(e).__name__}: {e}")
        c.ok(got is False, f"is_valid should be False for {why}, got {got!r}")


@c.test("is_valid() finds the 7 damaged lines of the Sousse log",
        hint="Read the log with read_log() (it decodes like gps_node). 7 lines fail; the two swapped-digit "
             "lines PASS the checksum — that is expected (XOR cannot see the order).")
def _():
    m = nt()
    f, read_log = need(m, "is_valid", "read_log")
    lines = read_log(LOG)
    c.eq(len(lines), 6414, "number of lines in the log")
    n = sum(1 for ln in lines if f(ln) is not True)
    c.eq(n, 7, "number of lines refused by is_valid")


@c.test("dm_to_deg(): degrees-minutes to decimal degrees, with sign and range checks",
        hint="degrees = int(v // 100), minutes = the rest, result = degrees + minutes/60; S and W negative. "
             "None for an unreadable value, an unknown hemisphere or minutes outside [0, 60).")
def _():
    (f,) = need(nt(), "dm_to_deg")
    c.near(f("3549.61531", "N"), 35.8269218, 1e-7, "dm_to_deg('3549.61531', 'N')")
    c.near(f("01038.52535", "E"), 10.6420892, 1e-7, "dm_to_deg('01038.52535', 'E')")
    c.near(f("4807.038", "S"), -48.1173, 1e-7, "dm_to_deg('4807.038', 'S')")
    c.near(f("12224.000", "W"), -122.4, 1e-7, "dm_to_deg('12224.000', 'W')")
    c.near(f("0030.000", "N"), 0.5, 1e-7, "dm_to_deg('0030.000', 'N')")
    for v, h in (("", "N"), ("abc", "N"), (None, "N"), ("3574.17098", "N"), ("3549.6", "X"), ("3549.6", "")):
        got = f(v, h)
        c.ok(got is None, f"dm_to_deg({v!r}, {h!r}) should be None, got {got!r}")


@c.test("parse_gga(): the real receiver's sentence, a no-fix sentence, non-GGA and impossible minutes",
        hint="fields 1..11 as written above TODO 4; use dm_to_deg, to_int, to_float so empty fields become "
             "None. Return None for an invalid line or a type that does not end with 'GGA'.")
def _():
    (f,) = need(nt(), "parse_gga")
    g = f(NEO)
    c.ok(isinstance(g, dict), f"parse_gga should return a dictionary, got {g!r}")
    want = {"time": "141621.00", "quality": 1, "sats": 12}
    for k, v in want.items():
        c.eq(g.get(k), v, f"g[{k!r}]")
    for k, v in {"lat": 35.734001, "lon": 10.5758485, "hdop": 0.72, "alt_msl": 95.3, "geo_sep": 32.1}.items():
        c.near(g.get(k), v, 1e-7, f"g[{k!r}]")
    c.ok(f(RMC) is None, "parse_gga(an RMC sentence) should be None")
    c.ok(f(NEO.replace("95.3", "96.3")) is None, "parse_gga(a line with a wrong checksum) should be None")
    n = f(NOFIX)
    c.ok(isinstance(n, dict), f"the no-fix sentence should still give a dictionary, got {n!r}")
    c.eq(n.get("quality"), 0, "quality of the no-fix sentence")
    c.ok(n.get("lat") is None and n.get("lon") is None and n.get("alt_msl") is None,
         "lat, lon and alt_msl of the no-fix sentence should be None")
    s = f(SWAP60)
    c.ok(isinstance(s, dict) and s.get("lat") is None and s.get("lon") is not None,
         f"in {SWAP60[:32]}… the minutes are 74: lat must be None (lon is fine), got {s!r}")


@c.test("parse_gsa(): mode, used PRNs and the three DOPs (NMEA 4.10 system id accepted)",
        hint="f[2] = mode, f[3]..f[14] = 12 PRN slots (skip the empty ones), f[15..17] = PDOP, HDOP, VDOP. "
             "Do not require exactly 18 fields: NMEA 4.10 adds a 19th (system id).")
def _():
    (f,) = need(nt(), "parse_gsa")
    g = f(GSA)
    c.ok(isinstance(g, dict), f"parse_gsa should return a dictionary, got {g!r}")
    c.eq(g.get("mode"), 3, "mode")
    c.eq(g.get("prns"), [2, 5, 7, 9, 13, 20, 23, 24, 30], "prns")
    for k, v in (("pdop", 1.98), ("hdop", 1.15), ("vdop", 1.61)):
        c.near(g.get(k), v, 1e-9, k)
    n = f(GSA_NOFIX)
    c.ok(isinstance(n, dict) and n.get("mode") == 1 and n.get("prns") == [],
         f"no-fix GSA should give mode 1 and prns [], got {n!r}")
    v410 = f(cs("GNGSA,A,3,05,13,15,18,20,23,24,29,,,,,1.32,0.82,1.03,1"))
    c.ok(isinstance(v410, dict) and v410.get("prns") == [5, 13, 15, 18, 20, 23, 24, 29]
         and abs((v410.get("vdop") or 0) - 1.03) < 1e-9, f"NMEA 4.10 GSA (with system id) read as {v410!r}")
    c.ok(f(RMC) is None, "parse_gsa(an RMC sentence) should be None")


@c.test("parse_gsv(): blocks of 4 (prn, elevation, azimuth, snr); empty SNR -> None",
        hint="After f[3], read the fields 4 at a time. Convert with to_int (empty -> None). Ignore leftover "
             "fields that do not make a full block (NMEA 4.10 signal id).")
def _():
    (f,) = need(nt(), "parse_gsv")
    g = f(GSV)
    c.ok(isinstance(g, dict), f"parse_gsv should return a dictionary, got {g!r}")
    c.eq((g.get("n_msgs"), g.get("msg"), g.get("in_view")), (3, 2, 12), "(n_msgs, msg, in_view)")
    c.eq([tuple(s) for s in g.get("sats", [])],
         [(13, 72, 160, 48), (15, 24, 200, None), (18, 12, 225, None), (20, 40, 253, 42)], "sats")
    last = f(cs("GPGSV,3,3,09,30,84,177,49,1"))
    c.ok(isinstance(last, dict) and [tuple(s) for s in last.get("sats", [])] == [(30, 84, 177, 49)],
         f"a last GSV with 1 satellite + a signal id should give [(30, 84, 177, 49)], got {last!r}")
    c.ok(f(GSA) is None, "parse_gsv(a GSA sentence) should be None")


@c.test("geometry_matrix(): n x 4, row = [-cos(el)sin(az), -cos(el)cos(az), -sin(el), 1]",
        hint="Convert degrees to radians with np.radians; the line-of-sight unit vector is in (East, North, "
             "Up); the last column is 1 (the clock).")
def _():
    import numpy as np
    (f,) = need(load_student("dop.py"), "geometry_matrix")
    G = f([0, 90, 180, 270, 0], [30, 30, 30, 30, 90])
    c.ok(G is not None, "geometry_matrix returned None")
    G = np.asarray(G, dtype=float)
    c.eq(G.shape, (5, 4), "shape of G")
    c.ok(np.allclose(G[1], [-0.8660254, 0.0, -0.5, 1.0], atol=1e-6),
         f"row for az 90, el 30 should be [-0.866, 0, -0.5, 1], got {np.round(G[1], 4).tolist()}")
    c.ok(np.allclose(G[0], [0.0, -0.8660254, -0.5, 1.0], atol=1e-6),
         f"row for az 0, el 30 should be [0, -0.866, -0.5, 1], got {np.round(G[0], 4).tolist()}")
    c.ok(np.allclose(G[4], [0, 0, -1, 1], atol=1e-6), f"row for el 90 should be [0, 0, -1, 1], got {G[4]}")


@c.test("dops(): the worked example, a bad geometry, rotation invariance and < 4 satellites",
        hint="Q = inverse of (G^T G); HDOP = sqrt(Q[0,0] + Q[1,1]), VDOP = sqrt(Q[2,2]), "
             "PDOP = sqrt of the first three, TDOP = sqrt(Q[3,3]), GDOP = sqrt(trace). Raise ValueError "
             "yourself when fewer than 4 satellites are given. Singular geometry (np.linalg.matrix_rank(G^T G) < 4): "
             "return math.inf for all five — np.linalg.inv does not always raise for it.")
def _():
    (f,) = need(load_student("dop.py"), "dops")
    d = f([0, 90, 180, 270, 0], [30, 30, 30, 30, 90])
    c.ok(isinstance(d, dict), f"dops should return a dictionary, got {d!r}")
    for k, v in {"GDOP": 2.886751, "PDOP": 2.516611, "HDOP": 1.154701, "VDOP": 2.236068, "TDOP": 1.414214}.items():
        c.near(d.get(k), v, 1e-5, f"{k} of the worked example")
    b = f([20, 40, 60, 35, 50], [20, 25, 30, 60, 45])
    c.near(b["HDOP"], 16.176756, 1e-4, "HDOP of 5 satellites bunched in the north-east")
    az, el = [10, 80, 150, 200, 300, 333], [15, 50, 35, 70, 25, 60]
    r = f([a + 37 for a in az], el)
    d0 = f(az, el)
    c.near(r["HDOP"], d0["HDOP"], 1e-9, "HDOP after turning every azimuth by 37 deg (must not change)")
    c.near(r["VDOP"], d0["VDOP"], 1e-9, "VDOP after turning every azimuth by 37 deg (must not change)")
    try:
        f([0, 120, 240], [30, 30, 30])
    except ValueError:
        pass
    except Exception as e:
        c.ok(False, f"with 3 satellites dops should raise ValueError, it raised {type(e).__name__}")
    else:
        c.ok(False, "with 3 satellites dops should raise ValueError (G^T G is singular)")
    # singular geometry: 4 satellites at one elevation (inv raises for 35 deg, returns ~1e16 for 30 deg)
    for el in (35, 30):
        try:
            s = f([15, 105, 195, 285], [el] * 4)
        except Exception as e:
            c.ok(False, f"dops() of 4 satellites all at elevation {el} deg crashed with {type(e).__name__}: "
                        f"a singular geometry must return math.inf for every DOP (lab, TODO 7-8 task)")
        c.ok(isinstance(s, dict) and all(s.get(k) == math.inf for k in ("GDOP", "PDOP", "HDOP", "VDOP", "TDOP")),
             f"4 satellites all at elevation {el} deg (singular G^T G): every DOP must be math.inf, got {s!r}")


@c.test("navera_decision(): the same decisions and reason texts as gps_node._publish_fix",
        hint="Open gps_node.py: quality None counts as 0; no position or quality not in {1,2,4,5} is invalid; "
             "6, 7, 8 get the 'non-satellite position' reason (with the em dash —), others 'no GPS fix'.")
def _():
    (f,) = need(load_student("gps_filter.py"), "navera_decision")
    base = {"time": "051217.00", "lat": 35.83, "lon": 10.64, "sats": 9, "hdop": 1.15, "alt_msl": 8.8, "geo_sep": 32.0}
    cases = [(1, True, ""), (2, True, ""), (4, True, ""), (5, True, ""),
             (0, False, "no GPS fix (qual=0)"), (3, False, "no GPS fix (qual=3)"),
             (6, False, "receiver reports a non-satellite position (qual=6) — not used"),
             (7, False, "receiver reports a non-satellite position (qual=7) — not used"),
             (8, False, "receiver reports a non-satellite position (qual=8) — not used"),
             (None, False, "no GPS fix (qual=0)")]
    for q, ok, why in cases:
        got = f(dict(base, quality=q))
        c.ok(isinstance(got, tuple) and len(got) == 2, f"navera_decision should return (valid, reason), got {got!r}")
        c.eq(got, (ok, why), f"navera_decision(quality={q})")
    c.eq(f(dict(base, quality=1, lat=None)), (False, "no GPS fix (qual=1)"), "quality 1 without latitude")
    got = f(None)
    c.ok(isinstance(got, tuple) and got[0] is False, f"navera_decision(None) should be (False, ...), got {got!r}")


@c.test("navera_covariance() and jump_ok()",
        hint="Covariance: s = HDOP x UERE_M, diagonal [s², s², 4 s²], None when HDOP is missing or <= 0. "
             "Jump gate: distance <= v_max * dt + slack_m; prev None -> True; dt <= 0 -> False.")
def _():
    m = load_student("gps_filter.py")
    cov, jump = need(m, "navera_covariance", "jump_ok")
    got = cov(1.15)
    c.ok(isinstance(got, list) and len(got) == 9, f"navera_covariance(1.15) should be a list of 9 floats, got {got!r}")
    want = [5.29, 0, 0, 0, 5.29, 0, 0, 0, 21.16]
    c.ok(all(abs(a - b) < 1e-9 for a, b in zip(got, want)), f"navera_covariance(1.15) = {got}, expected {want}")
    c.ok(cov(None) is None and cov(0.0) is None, "navera_covariance(None) and (0.0) should be None")
    p = (35.80, 10.70)
    c.ok(jump(None, p, 1.0) is True, "jump_ok(None, ...) should be True (first fix)")
    c.ok(jump(p, (35.8005, 10.70), 1.0) is True, "55 m in 1 s is plausible (<= 60 m/s)")
    c.ok(jump(p, (35.8120, 10.70), 1.0) is False, "1.33 km in 1 s is a jump")
    c.ok(jump(p, (35.8120, 10.70), 30.0) is True, "1.33 km in 30 s is plausible")
    c.ok(jump(p, (35.8007, 10.70), 1.0, 30.0) is True, "78 m in 1 s with a slack of 30 m is plausible")
    c.ok(jump(p, (35.8005, 10.70), 0.0) is False, "dt = 0 must give False")


@c.test("results.json — data quality: rejected lines, qualities, NAVERA decisions, jump gate",
        hint="Run python3 analyze_drive.py after TODO 1-13. 7 lines rejected; the jump gate must catch the "
             "swapped-digit line at 052421, and your parser must refuse the 74-minute line at 051731.")
def _():
    r = results()
    c.eq(r.get("lines_total"), 6414, "lines_total")
    c.eq(r.get("lines_rejected"), 7, "lines_rejected")
    c.eq(r.get("gga_by_quality"), {"0": 54, "1": 1007, "6": 5}, "gga_by_quality")
    c.eq(r.get("navera_valid"), 1006, "navera_valid (your decision with your stricter parser)")
    c.eq(r.get("jump_rejected_utc"), ["052421"], "jump_rejected_utc")
    c.eq(r.get("fixes_accepted"), 1005, "fixes_accepted")


@c.test("results.json — geometry, outage and accuracy",
        hint="DOPs recomputed from GSV+GSA must match the receiver within rounding (0.005). The outage is the "
             "largest gap between accepted fixes. UERE = sqrt(mean((e_h / HDOP)^2)).")
def _():
    r = results()
    c.eq(r.get("dop_epochs_compared"), 1008, "dop_epochs_compared")
    c.near(r.get("dop_max_abs_diff"), 0.003, 0.0031, "dop_max_abs_diff")
    c.near(r.get("outage_s"), 33.0, 0.01, "outage_s")
    c.eq((r.get("outage_from_utc"), r.get("outage_to_utc")), ("052003", "052036"), "outage from/to")
    c.near(r.get("hdop_max"), 5.69, 0.001, "hdop_max")
    c.near(r.get("uere_est_m"), 1.87, 0.015, "uere_est_m")
    c.near(r.get("frac_within_2drms"), 0.9831, 0.002, "frac_within_2drms")
    c.near(r.get("track_length_m"), 19578.4, 1.0, "track_length_m")


@c.test("gps_node_counts.json — NAVERA's real driver read the log",
        hint="Run python3 play_to_gps_node.py (Step 9, about 40 s). It writes gps_node_counts.json.")
def _():
    if not os.path.exists("gps_node_counts.json"):
        c.ok(False, "gps_node_counts.json does not exist yet — run python3 play_to_gps_node.py")
    with open("gps_node_counts.json") as f:
        g = json.load(f)
    c.ok(g.get("log", "").endswith("sousse_drive.nmea"), f"the replay used {g.get('log')!r}, not the Sousse log")
    c.eq(g.get("published"), 1066, "PositionEstimate messages published (one per valid-checksum GGA)")
    c.eq(g.get("valid"), 1007, "valid estimates")
    c.eq(g.get("invalid"), 59, "invalid estimates")
    reasons = g.get("reasons") or {}
    c.ok(isinstance(reasons, dict) and sum(reasons.values()) == g.get("invalid")
         and any("qual=6" in k for k in reasons),
         "the reasons in gps_node_counts.json do not add up: run python3 play_to_gps_node.py again")
    c.near(g.get("max_jump_m"), 50050.2, 1.0, what="max_jump_m (largest jump between valid fixes, from the replay)")


@c.test("report.md — 5 sections, your numbers, at least 250 words",
        hint="Keep the 5 headings of the template, replace every TODO line by your own sentences, and quote "
             "the numbers: rejected lines, the two swapped-digit times, the outage length, your UERE, "
             "gps_node's valid count.")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8", errors="replace").read()
    first = text.find("\n## 1.")                    # the instructions above the first heading are not graded
    text = text[first:] if first >= 0 else text
    for h in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5."):
        c.ok(h in text, f"the heading starting with '{h}' is missing")
    c.ok("TODO" not in text, "report.md still contains 'TODO' lines from the template")
    words = len(re.findall(r"[A-Za-z]+", text))
    c.ok(words >= 250, f"report.md has {words} words; write at least 250")
    for token, what in (("051731", "the UTC time of the 74-minute line"), ("052421", "the UTC time of the jump"),
                        ("33", "the outage length (s)"), ("1007", "gps_node's valid count"),
                        ("7", "the number of rejected lines")):
        c.ok(token in text, f"report.md does not mention {what} ({token})")
    uere = None
    if os.path.exists("results.json"):
        try:
            uere = json.load(open("results.json")).get("uere_est_m")
        except ValueError:
            uere = None
    if isinstance(uere, (int, float)) and math.isfinite(uere):
        c.ok(f"{uere:.1f}" in text or f"{uere:.2f}" in text,
             f"report.md does not quote your UERE estimate ({uere:.2f} m)")


c.run()
