import contextlib
import io
import math
import os
import re

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()

# ---------------------------------------------------------------- expected values (from the course reference,
# solutions/15-gps-nmea/expected.py; the unseen exam log is courses/15-gps-nmea/hidden/exam_drive.nmea)
EXAM_BAD = 7                                     # lines refused by is_valid in the exam log (6414 lines)
EXAM_STATES = {"FIX": 975, "DEGRADED": 46, "NO_FIX": 48}   # fix_state(parse_gga(line)) over its 1069 GGA-like lines
EXAM_REASONS = {"no satellite fix (quality 0)": 39, "receiver dead reckoning (quality 6)": 5, "no position": 1,
                "not a GGA sentence": 3, "σ unknown": 1}
FORGE_BASE = "$GPGGA,052200.00,3545.89257,N,01045.14417,E,1,12,0.77,2.1,M,32.0,M,,*59"   # lab Step 5
LAB = {"BYTES_PER_S": (410.6, 3.0), "LINK_LOAD_PCT": (42.8, 1.5), "BAD_LINES": (7, 0),
       "STREET_EDOP": (3.26, 0.011), "STREET_NDOP": (0.80, 0.011), "HDOP_MAX": (18.8, 0.011),
       "N_FIX": (976, 0), "N_DEGRADED": (30, 0), "N_NO_FIX": (63, 0), "SIGMA_MAX_M": (37.6, 0.051)}
IMPOSSIBLE_UTC = "051731"
JUMP_UTC = "052421"


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def functions(*names):
    fns = need(quiet("navera_lite.gnss"), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/gnss.py)")
    return fns


def answers(*names):
    return need(quiet("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def lab_number(name, v, where):
    want, tol = LAB[name]
    x = number(v, name)
    c.ok(abs(x - want) <= tol + 1e-9, f"{name} = {v!r} is not what {where} gives")


def utc_text(v, name):
    if not isinstance(v, str) or not v.strip():
        raise CheckFailed(f'{name} should be a time in quotes, like "hhmmss", got {v!r}')
    return re.sub(r"[^0-9]", "", v.strip())[:6]


TIPS = [("unsupported operand type(s) for ^", " — XOR works on numbers: ord(ch) (lesson §2)"),
        ("could not convert string to float", " — an empty or damaged field reached float(): use to_float()"),
        ("list index out of range", " — check len(f) before reading f[k]: a short line has few fields"),
        ("unsupported operand type(s) for +: 'NoneType'", " — an empty field is None: add the two heights only when BOTH "
                                                         "exist (lab Step 3 🧰)"),
        ("unsupported operand type(s) for +: 'float' and 'NoneType'", " — an empty field is None: add the two heights only "
                                                                    "when BOTH exist (lab Step 3 🧰)"),
        ("not enough values to unpack", " — the line has no *: test \"*\" in line before split(\"*\", 1)"),
        ("Singular matrix", " — test the rank of G first and return None (lesson §5, the warning box)"),
        ("'NoneType' object is not subscriptable", " — fields(line) is None for an invalid line: test it first"),
        ("'NoneType' object has no attribute", " — fields(line) is None for an invalid line: test it first")]


def go(fn, *args, **kw):
    """run() with one more sentence for the errors students meet most in this mission."""
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def cs(body):
    x = 0
    for ch in body:
        x ^= ord(ch)
    return f"${body}*{x:02X}"


def ref_valid(line):
    s = line.strip()
    if len(s) > 80 or not s.startswith("$") or "*" not in s:
        return False
    body, given = s[1:].split("*", 1)
    return "$" not in body and len(given) == 2 and cs(body)[-2:] == given.upper()


def ref_latlon(line):
    """The checker's own reading of a GGA position (to measure a forged line)."""
    f = line.strip()[1:].split("*")[0].split(",")

    def dm(v, h, top):
        try:
            x = float(v)
        except ValueError:
            return None
        d = int(x // 100)
        m = x - 100 * d
        if not 0 <= m < 60 or h not in "NSEW" or len(h) != 1:
            return None
        deg = d + m / 60.0
        return None if deg > top else (-deg if h in "SW" else deg)
    return dm(f[2], f[3], 90.0), dm(f[4], f[5], 180.0)


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, a)))


def is_dict(v, what):
    if not isinstance(v, dict):
        raise CheckFailed(f"{what} should be a dict, got {v!r}")
    return v


def near_or_none(got, want, tol, what):
    if want is None:
        c.ok(got is None, f"{what} is {got!r}: an empty or impossible field must give None")
    else:
        c.ok(isinstance(got, (int, float)) and not isinstance(got, bool), f"{what} should be a number, got {got!r}")
        c.near(got, want, tol, what)


# ================================================================ session 1 — the wire
@c.test("TODO 1: nmea_checksum() on unseen bodies, with the leading zero",
        hint="Lesson §2: XOR (^) of ord() of every character of the body, from 0; then f\"{x:02X}\".")
def _():
    (f,) = functions("nmea_checksum")
    for body, want in [("GNGGA,000000.00,,,,,0,00,99.99,,,,,,", "78"), ("GAGSV,1,1,01,12,45,090,40", "56"),
                       ("PSRF,0", "0B"), ("", "00")]:
        got = go(f, body)
        c.ok(isinstance(got, str), f"nmea_checksum({body!r}) should return a str like \"4F\", got {got!r}")
        if got != want and got.upper().lstrip("0") == want.lstrip("0") and want.lstrip("0"):
            raise CheckFailed(f"nmea_checksum({body!r}) gives {got!r}: always 2 UPPER-case digits — f\"{{x:02X}}\"")
        if got != want and len(body) > 2 and got == cs(body[1:])[-2:]:
            raise CheckFailed(f"nmea_checksum({body!r}) gives {got!r}: the first character is missing from your XOR")
        c.ok(got == want, f"nmea_checksum({body!r}) gives {got!r}, not the right checksum — XOR (^), not +")


@c.test("TODO 2: is_valid() on unseen lines: True/False only, never a crash",
        hint="Lesson §2: strip, ≤ MAX_LINE_LEN, starts with $, a * and exactly 2 hex digits equal to the checksum "
             "(compare in upper case), no second $ in the body. Anything that is not a str → False.")
def _():
    (f,) = functions("is_valid")
    good = cs("GPGGA,101010.00,0013.50000,S,07829.10000,W,4,21,0.45,2850.4,M,,M,,")
    cases = [(good + "\r\n", True, "a good line ending with \\r\\n"),
             ("  " + good, True, "a good line with spaces in front"),
             ("$GNGSA,A,3,07,12,30,05,,,,,,,,,3.1,1.8,2.5,1*3f", True, "lower-case hex digits"),
             (cs("GPTXT,01,01,02," + "X" * 61) + "\r\n", True,
              "a legal 80-character sentence ending with \\r\\n (strip BEFORE the length test)"),
             (cs("GPGGA,1$GPGGA,2"), False, "a $ inside the body, even with a matching XOR (two sentences glued)"),
             (good.replace("2850.4", "2850.5"), False, "one changed character"),
             (good[:40], False, "a cut line"),
             (good.split("*")[0], False, "no checksum"),
             (good[:-1], False, "only one hex digit"),
             (good + "7", False, "three characters after *"),
             (good[:30] + cs("GPRMC,101010.00,V,,,,,,,121026,,,N"), False, "two sentences glued (one $ inside)"),
             (cs("GPTXT,01,01,02," + "X" * 63), False, "a line longer than 82 characters with \\r\\n"),
             (cs("GPGGA,1").replace("G", "�", 1), False, "a non-ASCII byte shown as �"),
             ("", False, "an empty line"), (None, False, "None"), (12345, False, "a number")]
    for line, want, label in cases:
        got = go(f, line)
        c.ok(isinstance(got, bool), f"is_valid({line!r:.50}) returned {got!r}: it must return True or False, "
                                    "never None (does every path end with a return?)")
        c.ok(got is want, f"is_valid({line!r:.50}) gives {got} for {label} — expected {want}")


@c.test("TODO 3: dm_to_deg() on unseen angles, hemispheres and impossible values",
        hint="Lesson §3: degrees = the part before the last two digits of the integer part, minutes = the rest; "
             "S and W negative; None for minutes ≥ 60, a latitude > 90°, a longitude > 180°, an empty or unreadable value.")
def _():
    (f,) = functions("dm_to_deg")
    for args, want in [(("6409.12345", "N"), 64.1520575), (("02156.77700", "W"), -21.946283333),
                       (("0013.50000", "S"), -0.225), (("17959.99990", "E"), 179.999998333),
                       (("9000.00000", "N"), 90.0)]:
        got = go(f, *args)
        c.ok(isinstance(got, (int, float)) and not isinstance(got, bool), f"dm_to_deg{args} should be a number, got {got!r}")
        if want and abs(got - (abs(want) if args[1] in "SW" else want)) < 1e-6 and want < 0:
            raise CheckFailed(f"dm_to_deg{args} gives {got:.6f}: {args[1]} must be negative")
        if abs(got - want) > 1e-6 and abs(got - float(args[0]) / 100.0 * (1 if args[1] in "NE" else -1)) < 1e-9:
            raise CheckFailed(f"dm_to_deg{args} gives {got}: you divided by 100 — the last two digits before the "
                              "point are MINUTES (minutes / 60)")
        c.near(got, want, 1e-6, f"dm_to_deg{args}")
    for args, why in [(("3560.00000", "N"), "60 minutes"), (("9000.00010", "N"), "a latitude above 90°"),
                      (("18000.00010", "E"), "a longitude above 180°"), (("", "N"), "an empty value"),
                      (("35a0.1", "N"), "a value that is not a number"), (("3544.04006", "X"), "hemisphere X"),
                      (("3544.04006", ""), "an empty hemisphere"),
                      (("-3544.04006", "N"), "a negative value (the sign is the hemisphere's job)")]:
        got = go(f, *args)
        c.ok(got is None, f"dm_to_deg{args} gives {got!r} — {why} must give None")


GGA_CASES = [
    ("$GNGGA,234559.50,3352.12000,S,15112.55800,E,2,15,0.61,58.2,M,22.4,M,1.2,0131*49",
     {"t_utc_s": 85559.5, "lat": -33.868666667, "lon": 151.2093, "qual": 2, "sats": 15, "hdop": 0.61,
      "alt_msl_m": 58.2, "geoid_m": 22.4, "h_ell_m": 80.6}, "a GN line in Sydney"),
    ("$GPGGA,000001.00,6409.12345,N,02156.77700,W,1,07,2.35,31.0,M,64.9,M,,*78",
     {"t_utc_s": 1.0, "lat": 64.1520575, "lon": -21.946283333, "qual": 1, "sats": 7, "hdop": 2.35,
      "alt_msl_m": 31.0, "geoid_m": 64.9, "h_ell_m": 95.9}, "Reykjavik, west"),
    ("$GPGGA,101010.00,0013.50000,S,07829.10000,W,4,21,0.45,2850.4,M,,M,,*72",
     {"t_utc_s": 36610.0, "lat": -0.225, "lon": -78.485, "qual": 4, "sats": 21, "hdop": 0.45,
      "alt_msl_m": 2850.4, "geoid_m": None, "h_ell_m": None}, "Quito, no geoid separation"),
    ("$GPGGA,101011.00,3561.00000,N,01038.00000,E,1,08,1.10,12.0,M,32.0,M,,*6D",
     {"t_utc_s": 36611.0, "lat": None, "lon": 10.633333333, "qual": 1, "sats": 8, "hdop": 1.1,
      "alt_msl_m": 12.0, "geoid_m": 32.0, "h_ell_m": 44.0}, "61 minutes of latitude"),
    ("$GPGGA,101012.00,,,,,0,03,,,M,,M,,*48",
     {"t_utc_s": 36612.0, "lat": None, "lon": None, "qual": 0, "sats": 3, "hdop": None,
      "alt_msl_m": None, "geoid_m": None, "h_ell_m": None}, "no fix, empty fields"),
    ("$GPGGA,120000.00,4807.03800,N,01131.00000,E,1,09,0.95,,M,47.0,M,,*75",
     {"t_utc_s": 43200.0, "lat": 48.1173, "lon": 11.516666667, "qual": 1, "sats": 9, "hdop": 0.95,
      "alt_msl_m": None, "geoid_m": 47.0, "h_ell_m": None}, "no altitude, geoid separation present"),
    ("$GNGGA,120001.00,4807.03800,W,01131.00000,N,1,09,0.95,520.0,M,47.0,M,,*51",
     {"t_utc_s": 43201.0, "lat": None, "lon": None, "qual": 1, "sats": 9, "hdop": 0.95,
      "alt_msl_m": 520.0, "geoid_m": 47.0, "h_ell_m": 567.0}, "hemispheres swapped (latitude W, longitude N)"),
]


@c.test("TODO 4: parse_gga() on unseen GGA lines (any talker, empty fields, impossible values)",
        hint="Lesson §3 and the docstring: fields(line) gives the list; f[0] must end with GGA and there must be at "
             "least 15 items; to_float / to_int / dm_to_deg / utc_seconds give None for empty fields; "
             "h_ell_m = alt_msl_m + geoid_m only when both exist; lat needs N/S, lon needs E/W.")
def _():
    (f,) = functions("parse_gga")
    for line, want, label in GGA_CASES:
        got = is_dict(go(f, line), f"parse_gga({label})")
        missing = [k for k in want if k not in got]
        c.ok(not missing, f"parse_gga({label}) has no key {missing[:1]} — the keys are in the docstring")
        for k, v in want.items():
            if k in ("qual", "sats"):
                c.ok(got[k] == v and (v is None or isinstance(got[k], int)), f"{label}: {k} is {got[k]!r}, expected an "
                     f"int ({'None' if v is None else 'the field as an int'})")
            elif k == "h_ell_m" and v is not None and isinstance(got[k], (int, float)) and abs(got[k] - want["alt_msl_m"]) < 1e-6:
                raise CheckFailed(f"{label}: h_ell_m = {got[k]} is the sea-level altitude — add the geoid separation "
                                  "(lesson §3, mission 06 §8)")
            elif k == "h_ell_m" and v is None and got[k] is not None:
                raise CheckFailed(f"{label}: h_ell_m is {got[k]!r} with a height missing — a missing height is None, "
                                  "never invented (GPS-4)")
            elif k in ("lat", "lon") and v is None and "swapped" in label and got[k] is not None:
                raise CheckFailed(f"{label}: {k} is {got[k]!r} — a latitude needs hemisphere N or S, a longitude E or W "
                                  "(the docstring); anything else is None")
            else:
                near_or_none(got[k], v, 1e-6, f"{label}: {k}")
    for line, why in [("$GPGGA,101013.00,3549.6,N,01038.5,E,1,08*56", "a GGA with too few fields"),
                      ("$GPGLL,3549.61531,N,01038.52535,E,051217.00,A,A*6C", "a GLL sentence"),
                      ("$GPGGA,000001.00,6409.12345,N,02156.77700,W,1,07,2.35,31.0,M,64.9,M,,*79", "a bad checksum"),
                      ("", "an empty line")]:
        got = go(f, line)
        c.ok(got is None, f"parse_gga gives {got!r:.60} for {why} — expected None")


@c.test("TODO 5: parse_gsa() on unseen GSA lines (NMEA 4.10, empty slots and DOPs)",
        hint="Lesson §4: at least 18 items (a 19th, the system ID, is allowed); prns from f[3] to f[14] inclusive, empty slots "
             "skipped, as ints; pdop, hdop, vdop from f[15], f[16], f[17].")
def _():
    (f,) = functions("parse_gsa")
    got = is_dict(go(f, "$GNGSA,M,2,07,,12,30,,,,,,,,,4.10,3.95,1.10,2*02"), "parse_gsa(a GN line with a system ID)")
    c.ok(got.get("prns") == [7, 12, 30], f"prns is {got.get('prns')!r}: expected the satellite numbers as ints, "
                                         "empty slots skipped")
    c.ok(got.get("mode") == 2, f"mode is {got.get('mode')!r}, expected 2")
    for k, v in (("pdop", 4.10), ("hdop", 3.95), ("vdop", 1.10)):
        near_or_none(got.get(k), v, 1e-9, k)
    got = is_dict(go(f, "$GNGSA,A,3,03,06,09,12,15,18,21,24,27,30,32,31,1.4,0.8,1.1*23"), "parse_gsa(all 12 slots used)")
    want12 = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 32, 31]
    c.ok(got.get("prns") != want12[:11], "with all 12 slots used, your prns lose the last one: the slots are f[3] to "
                                         "f[14] inclusive, so the slice is f[3:15]")
    c.ok(got.get("prns") == want12, f"with all 12 slots used, prns is {got.get('prns')!r} — not the 12 satellites")
    got = is_dict(go(f, "$GPGSA,A,1,,,,,,,,,,,,,,,*1E"), "parse_gsa(no fix, all empty)")
    c.ok(got.get("prns") == [] and got.get("pdop") is None and got.get("vdop") is None,
         f"a GSA with empty slots and DOPs gives {got!r} — expected prns [] and None DOPs")
    for line, why in [("$GPGSA,A,3,01,02,03,04*34", "a GSA with too few fields"),
                      ("$GPGGA,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17*4B", "a GGA"),
                      ("$GNGSA,M,2,07,,12,30,,,,,,,,,4.10,3.95,1.10,2*03", "a bad checksum")]:
        got = go(f, line)
        c.ok(got is None, f"parse_gsa gives {got!r:.60} for {why} — expected None")


@c.test("Steps 1–3: the log — data rate, damaged lines, the impossible latitude",
        hint="Step 1: size ÷ 1069 s, and ÷ 960 characters/s. Step 2: run python3 run_gnss.py log. Step 3: loop over "
             "the log with your parse_gga and keep quality 1 with lat None; IMPOSSIBLE_WHY: which of your checks refuses "
             "it, and why XOR does not.")
def _():
    rate, load, pred, bad, why, utc, imp = answers("BYTES_PER_S", "LINK_LOAD_PCT", "PREDICT_BAD", "BAD_LINES",
                                                   "EXPLAIN_BAD", "IMPOSSIBLE_UTC", "IMPOSSIBLE_WHY")
    lab_number("BYTES_PER_S", rate, "wc -c ÷ 1069 s")
    if abs(number(load, "LINK_LOAD_PCT") - 34.2) < 1.0:
        raise CheckFailed("LINK_LOAD_PCT looks computed with 8 bits per character: a serial character costs 10 bits "
                          "(start, 8 data, stop), so 9600 baud = 960 characters/s (lesson §1)")
    lab_number("LINK_LOAD_PCT", load, "BYTES_PER_S ÷ 960 × 100")
    predicted("PREDICT_BAD", pred)
    lab_number("BAD_LINES", bad, "python3 run_gnss.py log")
    explained("EXPLAIN_BAD", why, ([r"checksum", r"\bxor"], "which check refused them (the checksum)"))
    kinds = [r"cut|truncat|short|incomplete|ends? too early", r"glue|two sentences|joined|merg|concaten|second \$",
             r"garbage|noise|junk|random", r"non.?ascii|�|byte|accent|degree sign|°",
             r"flip|changed|wrong (digit|character)|corrupt|1906|bit", r"no checksum|missing checksum|without (a )?checksum"]
    n = sum(1 for k in kinds if re.search(k, why.lower()))
    c.ok(n >= 3, f"EXPLAIN_BAD names {n} kind(s) of damage — name at least three of the seven lines' troubles "
                 "(open each one in `log`)")
    c.ok(utc_text(utc, "IMPOSSIBLE_UTC") == IMPOSSIBLE_UTC,
         f"IMPOSSIBLE_UTC = {utc!r} is not the GGA whose checksum is right but whose latitude is impossible")
    explained("IMPOSSIBLE_WHY", imp,
              ([r"minute", r"\b60\b", r"\b74\b", r"range", r"dm_to_deg", r"impossible"], "which check refuses it"),
              ([r"swap", r"order", r"xor", r"commut", r"same characters", r"exchang"], "why the checksum did not"))


@c.test("Step 5: be the saboteur — a forged line that passes the checksum and moves the fix",
        hint="Copy the original line of Step 5 into FORGED_LINE and swap two characters of the latitude or longitude; "
             "run python3 run_gnss.py forge until it is accepted and moves more than 1 km. FORGE_KM: what `forge` "
             "prints. EXPLAIN_FORGE: why XOR does not see it, why the range checks do not (the value is possible), and "
             "what in a navigation stack could.")
def _():
    pred, line, km, why = answers("PREDICT_FORGE_KM", "FORGED_LINE", "FORGE_KM", "EXPLAIN_FORGE")
    predicted("PREDICT_FORGE_KM", pred)
    c.ok(isinstance(line, str) and line.strip(), "FORGED_LINE is still empty")
    line = line.strip()
    c.ok(len(line) == len(FORGE_BASE), f"FORGED_LINE has {len(line)} characters, the original {len(FORGE_BASE)}: "
                                       "a swap keeps the length (copy the whole original line, $ to the checksum)")
    diff = [k for k, (a, b) in enumerate(zip(FORGE_BASE, line)) if a != b]
    c.ok(diff, "FORGED_LINE is the original line: swap two different characters")
    c.ok(len(diff) == 2 and FORGE_BASE[diff[0]] == line[diff[1]] and FORGE_BASE[diff[1]] == line[diff[0]],
         f"FORGED_LINE differs from the original at {len(diff)} positions: exactly ONE swap of two characters, "
         "nothing else (the checksum stays as it is)")
    c.ok(ref_valid(line), "your forged line does not pass the checksum test")
    lat, lon = ref_latlon(line)
    c.ok(lat is not None and lon is not None, "a correct parser refuses your forged position (minutes ≥ 60, or "
                                              "beyond 90°/180°): find a swap that stays plausible")
    lat0, lon0 = ref_latlon(FORGE_BASE)
    d = dist_m(lat0, lon0, lat, lon)
    c.ok(d > 1000.0, f"your forged line moves the position by only {d:.0f} m: more than 1 km is asked")
    k = number(km, "FORGE_KM")
    if abs(k - d) <= 0.01 * d + 1.0:
        raise CheckFailed("FORGE_KM looks written in metres: write kilometres, as `forge` prints them")
    c.ok(abs(k - d / 1000.0) <= 0.01 * d / 1000.0 + 0.01, f"FORGE_KM = {km!r} is not the distance your forged line "
                                                          "moves the position (km, from `forge`)")
    explained("EXPLAIN_FORGE", why,
              ([r"order", r"swap", r"commutat", r"same characters", r"xor", r"exchang"], "why the checksum does not see it"),
              ([r"jump", r"gate", r"speed", r"plausib", r"previous", r"last (trusted )?(fix|position)", r"rmc", r"other source",
                r"cross", r"vision", r"compar", r"teleport", r"impossible"], "what could catch it"),
              ([r"range", r"real (latitude|longitude|place|position|value)", r"possible (latitude|longitude|value)",
                r"legal", r"valid (latitude|longitude|value|angle)", r"below 90", r"under 90", r"below 180", r"under 180",
                r"within", r"wrong but", r"not impossible"], "why your range checks do not see it either"))


# ================================================================ session 2 — the sky
@c.test("TODO 6: geometry_matrix() on an unseen sky",
        hint="Lesson §5: u = (cos el·sin az, cos el·cos az, sin el) with np.radians; one row [−u_E, −u_N, −u_U, 1] "
             "per satellite; a numpy array of shape (n, 4). Different lengths → ValueError.")
def _():
    import numpy as np
    (f,) = functions("geometry_matrix")
    az, el = [33, 128, 211, 305, 77, 160], [18, 64, 41, 27, 85, 12]
    G = go(f, az, el)
    try:
        G = np.asarray(G, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"geometry_matrix should return a numpy array of numbers, got {G!r:.80}")
    c.ok(G.shape == (6, 4), f"geometry_matrix of 6 satellites has shape {G.shape}, expected (6, 4)")
    want = np.array([[-0.517983, -0.797623, -0.309017, 1.0], [-0.345441, 0.269888, -0.898794, 1.0],
                     [0.388704, 0.646912, -0.656059, 1.0], [0.72987, -0.51106, -0.45399, 1.0],
                     [-0.084922, -0.019606, -0.996195, 1.0], [-0.334546, 0.919158, -0.207912, 1.0]])
    if np.allclose(G, -want * [1, 1, 1, -1], atol=1e-5):
        raise CheckFailed("the first three columns have the wrong sign: a row is [−u_E, −u_N, −u_U, 1] (lesson §5)")
    if np.allclose(np.abs(G[:, :3]), np.abs(want[:, [1, 0, 2]]), atol=1e-5):
        raise CheckFailed("East and North are swapped: East = cos el · sin az, North = cos el · cos az")
    c.ok(np.allclose(G, want, atol=1e-5), "the matrix is not right — degrees given to np.sin/np.cos? "
                                          "(use np.radians) Compare one row by hand with lesson §5")
    try:
        run(f, [10, 20, 30], [40, 50])
    except CheckFailed as e:
        c.ok("ValueError" in str(e), f"different lengths should raise ValueError, got: {e}")
    else:
        raise CheckFailed("geometry_matrix([10, 20, 30], [40, 50]) should raise ValueError (the lengths differ)")


@c.test("TODO 7: dops() on unseen skies, and None (no crash) for singular ones",
        hint="Lesson §5: Q = inverse of GᵀG, then square roots of sums of its diagonal; test np.linalg.matrix_rank(G) "
             "< 4 (or fewer than 4 satellites) FIRST and return None — try/except around inv is not enough.")
def _():
    (f,) = functions("dops")
    d = go(f, [33, 128, 211, 305, 77, 160], [18, 64, 41, 27, 85, 12])
    c.ok(isinstance(d, dict), f"dops should return a dict, got {d!r:.80}")
    want = {"GDOP": 2.037312, "PDOP": 1.816107, "HDOP": 1.145002, "VDOP": 1.409686, "TDOP": 0.923252,
            "EDOP": 0.922617, "NDOP": 0.678090}
    missing = [k for k in want if k not in d]
    c.ok(not missing, f"the dict has no key {missing[:1]} — the keys are in the docstring")
    if abs(float(d["HDOP"]) - want["HDOP"] ** 2) < 1e-4:
        raise CheckFailed("HDOP is the square of the right value: take the square root (np.sqrt)")
    if abs(float(d["HDOP"]) - 1.816107) < 1e-4:
        raise CheckFailed("your HDOP includes Q_UU: HDOP = √(Q_EE + Q_NN), East and North only")
    for k, v in want.items():
        c.near(d[k], v, 1e-4, f"{k} of an unseen sky")
    d2 = go(f, [12, 140, 260, 330], [22, 48, 70, 15])
    c.ok(isinstance(d2, dict), "four well-spread satellites must give a dict of DOPs")
    c.near(d2["VDOP"], 3.735788, 1e-4, "VDOP with exactly 4 satellites")
    for args, why in [(([0, 90, 180, 270], [30, 30, 30, 30]), "four satellites at 30° (numpy's inv does NOT fail here: "
                                                                "test the rank)"),
                      (([15, 105, 195, 285, 40], [25, 25, 25, 25, 25]), "five satellites, all at 25°"),
                      (([0, 120, 240], [30, 50, 70]), "three satellites")]:
        got = go(f, *args)
        c.ok(got is None, f"dops gives {got!r:.70} for {why} — expected None (a singular geometry has no DOP)")


@c.test("Steps 6–7: DOP experiments and the receiver's DOPs, recomputed",
        hint="Run python3 run_gnss.py sky and python3 run_gnss.py dop. EXPLAIN_STREET: which direction do the "
             "satellites along the street constrain, and which one do they not? EXPLAIN_LOW: lesson §5 fact 1, the Up "
             "column vs the clock column.")
def _():
    p1, p2, e, n, why, diff, hmax, p3, low = answers("PREDICT_ROTATE", "PREDICT_STREET", "STREET_EDOP", "STREET_NDOP",
                                                     "EXPLAIN_STREET", "DOP_MAX_DIFF", "HDOP_MAX", "PREDICT_LOW",
                                                     "EXPLAIN_LOW")
    predicted("PREDICT_ROTATE", p1)
    predicted("PREDICT_STREET", p2)
    predicted("PREDICT_LOW", p3)
    if abs(number(e, "STREET_EDOP") - 0.80) < 0.02 and abs(number(n, "STREET_NDOP") - 3.26) < 0.02:
        raise CheckFailed("STREET_EDOP and STREET_NDOP are swapped — read the `sky` line again")
    lab_number("STREET_EDOP", e, "python3 run_gnss.py sky (part 3)")
    lab_number("STREET_NDOP", n, "python3 run_gnss.py sky (part 3)")
    explained("EXPLAIN_STREET", why,
              ([r"across", r"east", r"west", r"perpendicular", r"sideways", r"cross"], "the poorly known direction"),
              ([r"along", r"north", r"south", r"same direction", r"both (ends|sides)", r"opposite"],
               "where the satellites are"))
    explained("EXPLAIN_LOW", low,
              ([r"clock", r"\bbias", r"proportional", r"separat", r"up column", r"u_u", r"−u_u|-u_u", r"vertical column"],
               "the Up/clock link (lesson §5, fact 1)"),
              ([r"low", r"horizon", r"small", r"different", r"elevation", r"near zero", r"close to (0|zero)"],
               "what the low satellite changes"))
    dd = number(diff, "DOP_MAX_DIFF")
    c.ok(0.0 <= dd <= 0.006, f"DOP_MAX_DIFF = {diff!r}: python3 run_gnss.py dop prints the three largest "
                             "differences (HDOP, PDOP, VDOP) — write the largest (it should be tiny if your dops() is right)")
    lab_number("HDOP_MAX", hmax, "python3 run_gnss.py dop")


@c.test("TODO 8: fix_decision() on unseen receiver states",
        hint="Lesson §6 and the docstring: valid only for qualities 1, 2, 4, 5 with a latitude and a longitude; the "
             "reasons, in this order: None, quality 6, another unusable quality, no position.")
def _():
    (f,) = functions("fix_decision")
    cases = [({"qual": 2, "lat": -33.87, "lon": 151.21, "hdop": 0.6}, True, None),
             ({"qual": 4, "lat": 64.15, "lon": -21.95, "hdop": 0.5}, True, None),
             ({"qual": 5, "lat": 0.2, "lon": -78.5, "hdop": 0.9}, True, None),
             ({"qual": 6, "lat": None, "lon": None, "hdop": None}, False, "receiver dead reckoning (quality 6)"),
             ({"qual": 0, "lat": 35.8, "lon": 10.6, "hdop": 99.99}, False, "no satellite fix (quality 0)"),
             ({"qual": 7, "lat": 35.8, "lon": 10.6, "hdop": 1.0}, False, "no satellite fix (quality 7)"),
             ({"qual": 3, "lat": 35.8, "lon": 10.6, "hdop": 1.0}, False, "no satellite fix (quality 3)"),
             ({"qual": None, "lat": 35.8, "lon": 10.6, "hdop": 1.0}, False, "no satellite fix (quality None)"),
             ({"qual": 1, "lat": 35.8, "lon": None, "hdop": 1.0}, False, "no position"),
             (None, False, "not a GGA sentence")]
    for gga, ok, reason in cases:
        got = go(f, gga)
        c.ok(isinstance(got, (tuple, list)) and len(got) == 2, f"fix_decision should return (valid, reason), got {got!r}")
        q = None if gga is None else gga["qual"]
        c.ok(got[0] is ok, f"fix_decision(quality {q}, lat {None if gga is None else gga['lat']}, "
                           f"lon {None if gga is None else gga['lon']}) says valid = {got[0]!r}, expected {ok}")
        if reason:
            c.ok(got[1] == reason, f"for quality {q} the reason is {got[1]!r}; the docstring asks for {reason!r} "
                                   "(the order of the rules matters)")


@c.test("TODO 9: covariance_from_hdop() on unseen HDOPs, and unknown accuracy",
        hint="Lesson §6: σ = UERE_M × HDOP; nine numbers ENU row-major: σ² at [0] and [4], (2σ)² at [8], zeros "
             "elsewhere; type COV_TYPE_APPROXIMATED. None, nan, 0 or negative → nine 0.0 and COV_TYPE_UNKNOWN.")
def _():
    (f,) = functions("covariance_from_hdop")
    got = go(f, 1.35)
    c.ok(isinstance(got, (tuple, list)) and len(got) == 2, f"covariance_from_hdop should return (cov9, cov_type), got {got!r}")
    cov, t = got
    try:
        cov = [float(x) for x in cov]
    except (TypeError, ValueError):
        raise CheckFailed(f"cov9 should be 9 numbers, got {cov!r}")
    c.ok(len(cov) == 9, f"cov9 should have 9 numbers, got {len(cov)}")
    if abs(cov[0] - 2.7) < 1e-6:
        raise CheckFailed("cov[0] is σ (2.7 m), not the variance σ² — a covariance holds squares")
    if abs(cov[8] - 2 * 7.29) < 1e-6:
        raise CheckFailed("the Up variance is 2σ²: Up has σ_U = 2σ, so its variance is (2σ)² = 4σ²")
    for k, v in enumerate([7.29, 0, 0, 0, 7.29, 0, 0, 0, 29.16]):
        c.near(cov[k], v, 1e-6, f"cov9[{k}] for HDOP 1.35")
    c.ok(t == 1 and not isinstance(t, bool), f"cov_type for a known HDOP is {t!r}, expected 1 (APPROXIMATED)")
    for h in (None, float("nan"), 0.0, -2.0):
        got = go(f, h)
        c.ok(isinstance(got, (tuple, list)) and len(got) == 2, f"covariance_from_hdop({h}) should return (cov9, cov_type)")
        c.ok(isinstance(got[0], (tuple, list)) and len(got[0]) == 9,
             f"covariance_from_hdop({h}) gives cov9 = {got[0]!r}: still nine numbers (0.0), as NavSatFix does — the "
             "type 0 says they mean nothing")
        c.ok(got[1] == 0 and [float(x) for x in got[0]] == [0.0] * 9,
             f"covariance_from_hdop({h}) gives {got!r:.80} — an unknown accuracy is (nine 0.0, 0), never invented")


@c.test("TODO 10: fix_state() on unseen GGAs, and on an unseen damaged drive log",
        hint="Lesson §6: NO_FIX with fix_decision's reason; then σ from covariance_from_hdop: unknown → DEGRADED "
             "\"σ unknown\"; σ > fix_max_sigma_m → DEGRADED; else FIX. FIX at exactly the limit (σ ≤ 25 m).")
def _():
    (fs, pg, iv) = functions("fix_state", "parse_gga", "is_valid")
    for gga, kw, want in [({"qual": 1, "lat": 1.0, "lon": 2.0, "hdop": 12.5}, {}, ("FIX", "σ 25.0 m")),
                          ({"qual": 1, "lat": 1.0, "lon": 2.0, "hdop": 12.6}, {}, ("DEGRADED", "σ 25.2 m > 25.0 m")),
                          ({"qual": 4, "lat": 1.0, "lon": 2.0, "hdop": 6.0}, {"fix_max_sigma_m": 10.0},
                           ("DEGRADED", "σ 12.0 m > 10.0 m")),
                          ({"qual": 2, "lat": 1.0, "lon": 2.0, "hdop": None}, {}, ("DEGRADED", "σ unknown")),
                          ({"qual": 5, "lat": 1.0, "lon": 2.0, "hdop": 3.3}, {}, ("FIX", "σ 6.6 m")),
                          ({"qual": 6, "lat": 1.0, "lon": 2.0, "hdop": 0.9}, {}, ("NO_FIX", "receiver dead reckoning (quality 6)")),
                          (None, {}, ("NO_FIX", "not a GGA sentence"))]:
        got = go(fs, gga, **kw)
        c.ok(isinstance(got, (tuple, list)) and len(got) == 2, f"fix_state should return (state, reason), got {got!r}")
        h = None if gga is None else gga["hdop"]
        if gga and h == 12.5 and got[0] == "DEGRADED":
            raise CheckFailed("HDOP 12.5 gives σ = 25.0 m exactly: that is FIX (σ ≤ 25 m) — use >, not >=")
        if kw and got[0] == "FIX":
            raise CheckFailed("fix_state ignores its fix_max_sigma_m argument (σ 12 m > 10 m must be DEGRADED)")
        c.ok(got[0] == want[0], f"fix_state(quality {None if gga is None else gga['qual']}, HDOP {h}) gives "
                                f"{got[0]!r}, expected {want[0]!r}")
        c.ok(got[1] == want[1], f"fix_state(quality {None if gga is None else gga['qual']}, HDOP {h}): the reason is "
                                f"{got[1]!r}; the docstring's format gives {want[1]!r}")
    # the unseen exam log: other sky, other damage, GN talker, NMEA 4.10, a lower-case checksum, DGPS, no HDOP
    lines = hidden("exam_drive.nmea", text=False).decode("ascii", errors="replace").splitlines()
    bad = sum(1 for ln in lines if not run(iv, ln))
    c.ok(bad == EXAM_BAD, f"on an unseen drive log your is_valid refuses {bad} lines, not the right number "
                          "(lower-case hex digits are valid; check every rule of TODO 2)")
    count, reasons = {}, {}
    for ln in lines:
        if ln.startswith("$") and ln[3:6] == "GGA":
            st = run(fs, run(pg, ln))
            count[st[0]] = count.get(st[0], 0) + 1
            if st[0] != "FIX" and not st[1].startswith("σ ") or st[1] == "σ unknown":
                reasons[st[1]] = reasons.get(st[1], 0) + 1
    for k, v in EXAM_STATES.items():
        c.ok(count.get(k, 0) == v, f"on an unseen drive log (GN talker, a DGPS stretch, a GGA without HDOP…) your chain "
                                   f"is_valid → parse_gga → fix_state gives {count.get(k, 0)} {k}, not the right number")
    for k, v in EXAM_REASONS.items():
        c.ok(reasons.get(k, 0) == v, f"on an unseen drive log, the reason {k!r} appears {reasons.get(k, 0)} times, "
                                     "not the right number")


@c.test("Step 8: the drive through your judge — states, σ, the jump",
        hint="Run python3 run_gnss.py drive and copy its numbers. EXPLAIN_JUMP: why did every check of gnss.py accept "
             "that line, what σ did it state, and which part of a stack refuses it?")
def _():
    pred, nf, nd, nn, smax, jump, why = answers("PREDICT_STATES", "N_FIX", "N_DEGRADED", "N_NO_FIX", "SIGMA_MAX_M",
                                                "JUMP_UTC", "EXPLAIN_JUMP")
    predicted("PREDICT_STATES", pred)
    for name, v in (("N_FIX", nf), ("N_DEGRADED", nd), ("N_NO_FIX", nn)):
        lab_number(name, v, "python3 run_gnss.py drive")
    if abs(number(smax, "SIGMA_MAX_M") - 18.8) < 0.06:
        raise CheckFailed("SIGMA_MAX_M = 18.8 is the HDOP: σ = 2 m × HDOP")
    lab_number("SIGMA_MAX_M", smax, "python3 run_gnss.py drive")
    c.ok(utc_text(jump, "JUMP_UTC") == JUMP_UTC, f"JUMP_UTC = {jump!r} is not the first position the jump gate refuses")
    explained("EXPLAIN_JUMP", why,
              ([r"checksum", r"valid", r"swap", r"plausib", r"minutes", r"range", r"quality", r"looked (normal|fine)"],
               "why gnss.py accepted it"),
              ([r"σ", r"sigma", r"1\.5", r"small", r"hdop", r"precise", r"accura"], "the σ it stated"),
              ([r"gate", r"jump", r"speed", r"arbiter", r"judge", r"previous", r"last trusted", r"guard"],
               "which part refuses it"))


@c.test("Step 9: report.md — the three headings, your words and your numbers",
        hint="Keep the three headings of report.md, write at least 150 words, and quote: the damaged lines, the largest "
             "σ (or HDOP) of the drive, the number of FIX seconds, and the time of the jump.")
def _():
    c.file_exists("report.md")
    with open("report.md", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for h in ("## What the wire did", "## What the sky did", "## What gnss.py cannot see"):
        c.ok(h.lower() in body.lower(), f"report.md has lost the heading {h!r} — keep the three headings")
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok(len(words) >= 150, f"report.md has {len(words)} words of your own: at least 150, please")
    c.ok("TODO" not in body, "report.md still contains TODO")
    c.ok(re.search(r"\b7\b[^.\n]{0,40}(line|refus|damag|bad)|(line|refus|damag|bad)[^.\n]{0,40}\b7\b", body, re.I),
         "report.md does not quote how many lines your is_valid refused (e.g. \"7 lines refused\")")
    c.ok(re.search(r"37\.6|18\.8", body), "report.md does not quote the largest σ (or HDOP) of the drive")
    c.ok(re.search(r"\b976\b", body), "report.md does not quote the number of FIX seconds")
    c.ok(re.search(r"05:24:21|052421", body), "report.md does not quote the time of the jump")


c.milestone("line_inspector", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "Steps 1–3", "Step 5",
            label="Line inspector")
c.milestone("fix_judge", "TODO", "Step", label="Fix judge")
c.run()
