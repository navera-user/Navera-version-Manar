from academy_check import Checker, load_student, need

c = Checker()
LOG = "drive.nmea"
TEXTBOOK = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
NEO = "$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70"   # NAVERA's real receiver
RMC = "$GNRMC,141621.00,A,3544.04006,N,01034.55091,E,0.012,,011026,,,A*62"
NOFIX = "$GNGGA,093000.00,,,,,0,00,99.99,,,,,,*72"


def tools():
    return load_student("nmea_tools.py")


@c.test("nmea_checksum() gives 47 for the textbook example",
        hint="Start from 0, XOR (^) the ord() of every character of the body, then format the number "
             "with 2 upper-case hexadecimal digits (an f-string with :02X).")
def _():
    (f,) = need(tools(), "nmea_checksum")
    got = f(TEXTBOOK)
    c.ok(isinstance(got, str), f"nmea_checksum should return text like \"47\", it returned {got!r}")
    c.eq(got, "47", "nmea_checksum(textbook body)")


@c.test("nmea_checksum() always gives 2 upper-case digits (also below 0x10 and with letters)",
        hint="A checksum of 13 must be written \"0D\", not \"D\" and not \"0d\": that is what 02X does.")
def _():
    (f,) = need(tools(), "nmea_checksum")
    for body, want in [("GNGSA,A,3,05,13,15,18,20,23,24,29,,,,,1.32,0.82,1.03,1", "0D"),
                       ("GNGGA,093014.00,3544.04043,N,01034.59249,E,1,12,0.99,95.4,M,32.1,M,,", "76"),
                       ("GNRMC,141621.00,A,3544.04006,N,01034.55091,E,0.012,,011026,,,A", "62"),
                       ("", "00")]:
        c.eq(f(body), want, f"nmea_checksum({body[:25]!r}…)")


@c.test("is_valid() accepts correct sentences",
        hint="Remove the spaces and the \\r\\n at the end (strip), take the text between \"$\" and \"*\", "
             "compare its checksum with the 2 characters after \"*\".")
def _():
    (f,) = need(tools(), "is_valid")
    for line in ("$" + TEXTBOOK + "*47", NEO, NEO + "\r\n", RMC, NOFIX):
        c.ok(f(line) is True, f"is_valid({line[:40]!r}…) should be True, got {f(line)!r}")


@c.test("is_valid() refuses broken lines",
        hint="Return False (not None, no crash) when: no \"$\" at the start, no \"*\", not exactly 2 "
             "characters after \"*\", or a checksum that does not match.")
def _():
    (f,) = need(tools(), "is_valid")
    bad = {"a changed digit": NEO.replace("95.3", "96.3"),
           "no checksum": NEO.split("*")[0],
           "no $": NEO[1:],
           "a cut line": NEO[:31],
           "a checksum of letters that are not hex": "$GN#@!~~,,0,12,,1.0*ZZ",
           "a 1-digit checksum": NEO[:-1],
           "an empty line": ""}
    for why, line in bad.items():
        got = f(line)
        c.ok(got is False, f"is_valid should be False for {why} ({line[:40]!r}), got {got!r}")


@c.test("drive.nmea has 6 corrupted lines",
        hint="Read drive.nmea line by line and count the lines where is_valid() is False. "
             "If you find more, check that you strip the \\r\\n before reading the checksum.")
def _():
    (f,) = need(tools(), "is_valid")
    lines = open(LOG, errors="replace").read().splitlines()
    c.ok(len(lines) == 969, f"drive.nmea has {len(lines)} lines instead of 969 — use ↺ Reset lab files")
    n = sum(1 for ln in lines if f(ln) is not True)
    c.eq(n, 6, "the number of lines refused by is_valid")


@c.test("dm_to_deg() turns degrees-minutes into decimal degrees, with the sign",
        hint="3544.04006 is 35 degrees and 44.04006 minutes: degrees = int(value // 100), "
             "minutes = the rest; a minute is 1/60 of a degree. S and W are negative.")
def _():
    (f,) = need(tools(), "dm_to_deg")
    c.near(f("3544.04006", "N"), 35.734001, 1e-7, "dm_to_deg('3544.04006', 'N')")
    c.near(f("01034.55091", "E"), 10.5758485, 1e-7, "dm_to_deg('01034.55091', 'E')")
    c.near(f("4807.038", "S"), -48.1173, 1e-7, "dm_to_deg('4807.038', 'S')")
    c.near(f("12224.000", "W"), -122.4, 1e-7, "dm_to_deg('12224.000', 'W')")
    c.near(f("0030.000", "N"), 0.5, 1e-7, "dm_to_deg('0030.000', 'N')")


@c.test("dm_to_deg() gives None for an empty or unreadable field",
        hint="Use to_float(value): it already gives None for '' or 'abc'. Return None in that case.")
def _():
    (f,) = need(tools(), "dm_to_deg")
    c.ok(f("0030.000", "N") is not None, "first make dm_to_deg work for normal values (the check above)")
    for v in ("", "abc", None):
        got = f(v, "N")
        c.ok(got is None, f"dm_to_deg({v!r}, 'N') should be None, got {got!r}")


@c.test("parse_gga() reads the real NAVERA receiver's sentence",
        hint="Split the body (between $ and *) on ',' and take the fields 1 to 11 as written above "
             "TODO 4. Use dm_to_deg for lat/lon, to_int for quality and sats, to_float for the rest.")
def _():
    (f,) = need(tools(), "parse_gga")
    g = f(NEO)
    c.ok(isinstance(g, dict), f"parse_gga should return a dictionary, got {g!r}")
    for k in ("time", "lat", "lon", "quality", "sats", "hdop", "alt_msl", "geo_sep"):
        c.ok(k in g, f"the key {k!r} is missing from the dictionary")
    c.eq(g["time"], "141621.00", "g['time']")
    c.near(g["lat"], 35.734001, 1e-7, "g['lat']")
    c.near(g["lon"], 10.5758485, 1e-7, "g['lon']")
    c.eq(g["quality"], 1, "g['quality']")
    c.eq(g["sats"], 12, "g['sats']")
    c.near(g["hdop"], 0.72, 1e-9, "g['hdop']")
    c.near(g["alt_msl"], 95.3, 1e-9, "g['alt_msl']")
    c.near(g["geo_sep"], 32.1, 1e-9, "g['geo_sep']")


@c.test("parse_gga() refuses non-GGA and broken lines, and survives a 'no fix' sentence",
        hint="First is_valid(line) — if not, return None. Then the first field must end with 'GGA' "
             "(GPGGA, GNGGA…). Empty fields must become None, not crash: use to_float / to_int.")
def _():
    (f,) = need(tools(), "parse_gga")
    c.ok(f(RMC) is None, "parse_gga(an RMC sentence) should be None")
    c.ok(f(NEO.replace("95.3", "96.3")) is None, "parse_gga(a line with a wrong checksum) should be None")
    g = f(NOFIX)
    c.ok(isinstance(g, dict), f"parse_gga(no-fix sentence) should still be a dictionary, got {g!r}")
    c.eq(g.get("quality"), 0, "quality of the no-fix sentence")
    c.ok(g.get("lat") is None and g.get("lon") is None, "lat and lon of the no-fix sentence should be None")
    c.near(g.get("hdop"), 99.99, 1e-9, "hdop of the no-fix sentence")


@c.test("parse_gga() agrees with NAVERA's parser (pynmea2) on every fix of drive.nmea",
        hint="Run python3 compare_with_navera.py: it shows the first lines where you and NAVERA differ.")
def _():
    import pynmea2
    (f,) = need(tools(), "parse_gga")
    n = 0
    for no, ln in enumerate(open(LOG, errors="replace").read().splitlines(), 1):
        try:
            m = pynmea2.parse(ln, check=True)
        except pynmea2.ParseError:
            continue
        if not isinstance(m, pynmea2.types.talker.GGA):
            continue
        try:
            q, lat, lon = int(m.gps_qual), m.latitude, m.longitude
        except (TypeError, ValueError):
            continue
        if q not in (1, 2, 4, 5):
            continue
        g = f(ln)
        c.ok(isinstance(g, dict), f"line {no}: parse_gga gave {g!r} for a good GGA line")
        c.near(g.get("lat"), lat, 1e-7, f"line {no}: lat")
        c.near(g.get("lon"), lon, 1e-7, f"line {no}: lon")
        n += 1
    c.ok(n > 250, f"only {n} fixes compared")


@c.test("usable_fixes() keeps the 261 usable fixes of drive.nmea",
        hint="Keep a GGA only when its quality is in USABLE_QUALITIES and lat/lon are not None. "
             "Quality 0 (no fix) and 6 (the receiver's own guess) are thrown away, like gps_node does.")
def _():
    (f,) = need(tools(), "usable_fixes")
    pts = f(LOG)
    c.ok(isinstance(pts, list), f"usable_fixes should return a list, got {type(pts).__name__}")
    if len(pts) == 273:
        c.ok(False, "273 fixes: you kept the 12 quality-6 fixes (dead reckoning under the bridge)")
    c.eq(len(pts), 261, "the number of usable fixes")
    lat, lon = pts[0]
    c.near(lat, 35.734001, 1e-6, "latitude of the first usable fix")
    c.near(lon, 10.5758493, 1e-6, "longitude of the first usable fix")


@c.test("track_length_m() adds the distances between consecutive points",
        hint="Loop over the pairs (points[i], points[i+1]) and add haversine_m of each pair. "
             "0 or 1 point means a length of 0.")
def _():
    (f,) = need(tools(), "track_length_m")
    c.near(f([(35.0, 10.0), (35.001, 10.0)]), 111.195, 0.01, "track of 2 points 0.001 deg apart")
    c.near(f([(35.0, 10.0), (35.001, 10.0), (35.0, 10.0)]), 222.39, 0.02, "there and back")
    c.near(f([(35.0, 10.0)]), 0.0, 1e-9, "track of 1 point")
    c.near(f([]), 0.0, 1e-9, "empty track")


@c.test("the drive in drive.nmea is 3034.6 m long",
        hint="Measure the usable fixes only (TODO 5 then TODO 6). About 3052 m means the quality-6 "
             "fixes were kept. Run python3 track_report.py to see the track.")
def _():
    f, u = need(tools(), "track_length_m", "usable_fixes")
    c.near(f(u(LOG)), 3034.62, 0.5, "the track length (m)")


ANSWERS = {"Q1": ("b", "Quality 6 is 'estimated (dead reckoning)'. Look at _VALID_GPS_QUAL in gps_node.py."),
           "Q2": ("b", "HDOP is a 'how badly placed are the satellites' number: smaller is better."),
           "Q3": ("a", "Look for 'hdop * 2.0' in gps_node.py, or the HDOP section of the course."),
           "Q4": ("b", "Read the section 'Why NAVERA checks the checksum' again.")}


@c.test("quiz in answers.py", hint="Each answer is one letter between quotes, e.g. Q1 = \"b\".")
def _():
    m = load_student("answers.py")
    for q, (good, why) in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer — {why}")


c.run()
