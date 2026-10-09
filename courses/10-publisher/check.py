import json
import math
import re
import time

from academy_check import Background, Checker, load_student, need, sh, wait_for_messages

c = Checker()
R = 6_371_000.0
SOUSSE = (35.8277, 10.6388)       # the fake GPS's default start
MONASTIR = (35.78, 10.83)


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def stamp(m):
    return m.header.stamp.sec + m.header.stamp.nanosec * 1e-9


def mod():
    return load_student("fake_gps.py")


@c.test("fake_gps.py loads without errors", hint="Run `python3 fake_gps.py` and read the error (line number!).")
def _():
    need(mod(), "velocity_ne", "offset_to_latlon", "make_covariance", "make_fix", "FakeGps")


@c.test("TODO 1 — velocity_ne(): north at 0°, east at 90°, both at 30°",
        hint="v_north = speed·cos(heading), v_east = speed·sin(heading), heading clockwise from north, "
             "in radians inside cos/sin.")
def _():
    (f,) = need(mod(), "velocity_ne")
    for h, want in ((0.0, (10.0, 0.0)), (90.0, (0.0, 10.0)), (30.0, (8.660254, 5.0)), (180.0, (-10.0, 0.0))):
        out = f(10.0, h)
        c.ok(isinstance(out, (tuple, list)) and len(out) == 2, f"velocity_ne should return 2 numbers, got {out!r}")
        c.near(out[0], want[0], 1e-4, f"v_north for heading {h}°")
        c.near(out[1], want[1], 1e-4, f"v_east for heading {h}°")


@c.test("TODO 2 — offset_to_latlon(): 111 195 m north is 1°, and longitude degrees stretch by 1/cos(lat0)",
        hint="lat = lat0 + degrees(north / R); lon = lon0 + degrees(east / (R·cos(lat0))), cos in radians.")
def _():
    (f,) = need(mod(), "offset_to_latlon")
    lat, lon = f(*SOUSSE, 2 * math.pi * R / 360.0, 0.0)
    c.near(lat, SOUSSE[0] + 1.0, 1e-6, "latitude after 111 195 m north")
    c.near(lon, SOUSSE[1], 1e-9, "longitude after a move north")
    lat, lon = f(60.0, 10.0, 0.0, 2 * math.pi * R / 360.0)
    c.near(lon, 12.0, 1e-6, "longitude after 111 195 m east at latitude 60° (cos 60° = 0.5)")
    c.near(lat, 60.0, 1e-9, "latitude after a move east")


@c.test("TODO 3 — make_covariance(): 9 FLOATS, variances on the diagonal (ENU, row-major)",
        hint="[h², 0.0, 0.0, 0.0, h², 0.0, 0.0, 0.0, v²] with floats: ROS refuses ints in float64 fields.")
def _():
    (f,) = need(mod(), "make_covariance")
    cov = f(3.0, 6.0)
    c.ok(isinstance(cov, (list, tuple)) and len(cov) == 9, f"make_covariance should return 9 numbers, got {cov!r}")
    c.ok(all(isinstance(x, float) for x in cov), f"every number must be a float (9.0, 0.0…), got {cov!r}")
    c.eq(list(cov), [9.0, 0.0, 0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 36.0], "make_covariance(3.0, 6.0)")
    c.eq(list(f(2.5, 5.0))[8], 25.0, "the Up variance of make_covariance(2.5, 5.0)")


@c.test("TODO 4 — make_fix() fills status, position, altitude and covariance",
        hint="status.status = STATUS_FIX, status.service = SERVICE_GPS, latitude/longitude/altitude, "
             "position_covariance = make_covariance(sigma, 2·sigma), type DIAGONAL_KNOWN.")
def _():
    from builtin_interfaces.msg import Time
    from sensor_msgs.msg import NavSatFix, NavSatStatus
    (f,) = need(mod(), "make_fix")
    m = f(35.77, 10.83, 40.0, 2.0, Time(sec=1000, nanosec=5))
    c.ok(isinstance(m, NavSatFix), f"make_fix should return a NavSatFix, got {type(m).__name__}")
    c.near(m.latitude, 35.77, 1e-9, "latitude")
    c.near(m.longitude, 10.83, 1e-9, "longitude")
    c.near(m.altitude, 40.0, 1e-9, "altitude")
    c.eq(m.status.status, NavSatStatus.STATUS_FIX, "status.status")
    c.eq(m.status.service, NavSatStatus.SERVICE_GPS, "status.service")
    c.eq(list(m.position_covariance), [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 16.0], "position_covariance (sigma 2 m)")
    c.eq(m.position_covariance_type, NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN, "position_covariance_type")
    c.eq((m.header.stamp.sec, m.header.stamp.nanosec), (1000, 5), "header.stamp (keep the stamp you are given)")


RUN = {}


def run_default():
    """Default node: 10 fixes, then `ros2 param set heading_deg 90.0`, then 8 more fixes."""
    if "msgs" not in RUN:
        from sensor_msgs.msg import NavSatFix
        RUN.update(msgs=[], after=[], params="", out="")
        with Background("python3 -u fake_gps.py", settle=3.0) as bg:
            if wait_for_messages("/fake_gps/fix", NavSatFix, count=1, timeout=12):
                RUN["msgs"] = wait_for_messages("/fake_gps/fix", NavSatFix, count=10, timeout=10)
                RUN["params"] = sh("ros2 param list /fake_gps --no-daemon --spin-time 3", timeout=30)[1]
                sh("ros2 param set /fake_gps heading_deg 90.0", timeout=30)
                time.sleep(1.0)
                RUN["after"] = wait_for_messages("/fake_gps/fix", NavSatFix, count=8, timeout=8)
        RUN["out"] = bg.output()
    if len(RUN["msgs"]) < 5:
        out = RUN["out"]
        c.ok(False, f"only {len(RUN['msgs'])} messages on /fake_gps/fix in 10 s." +
             (f" Your node printed:\n{out[-700:]}" if out.strip() else ""))
    return RUN


@c.test("TODO 5/6 — the node /fake_gps publishes NavSatFix on /fake_gps/fix and declares its 6 parameters",
        hint="Course sections 2 and 3: TODO 5 declares every entry of DEFAULTS as a parameter; TODO 6 stores a "
             "NavSatFix publisher on TOPIC in self.pub and starts a timer whose PERIOD comes from the rate parameter "
             "and calls self.on_timer. Then `ros2 param list /fake_gps` must show the six names.")
def _():
    r = run_default()
    missing = [p for p in ("rate_hz", "speed_mps", "heading_deg", "start_lat", "start_lon", "sigma_m")
               if p not in r["params"]]
    c.ok(not missing, f"`ros2 param list /fake_gps` does not show: {missing}\n{r['params'][-300:]}")


@c.test("default run — 2 Hz, current stamps, a valid fix that starts near Sousse",
        hint="Course section 2: the timer takes a PERIOD, not a rate; the stamp is the node clock's current time "
             "converted to a message; the start position is read from the parameters, not from constants.")
def _():
    from sensor_msgs.msg import NavSatStatus
    msgs = run_default()["msgs"]
    rate = (len(msgs) - 1) / max(1e-6, stamp(msgs[-1]) - stamp(msgs[0]))
    c.near(rate, 2.0, 0.25, "the rate computed from the stamps (Hz)")
    age = time.time() - stamp(msgs[-1])
    c.ok(abs(age) < 30, f"header.stamp is {age:.0f} s away from the current time")
    c.eq(msgs[-1].status.status, NavSatStatus.STATUS_FIX, "status.status of a published fix")
    c.ok(dist_m(msgs[0].latitude, msgs[0].longitude, *SOUSSE) < 300,
         f"the first fix ({msgs[0].latitude:.5f}, {msgs[0].longitude:.5f}) is not near the Sousse start {SOUSSE}")


@c.test("TODO 7 — the vehicle drives at 5 m/s on heading 30° (measured between the published fixes)",
        hint="dt from the clock (t − self.last_t); speed and heading read with get_parameter() in on_timer; "
             "north += v_north·dt, east += v_east·dt.")
def _():
    msgs = run_default()["msgs"]
    a, b = msgs[0], msgs[-1]
    d = dist_m(a.latitude, a.longitude, b.latitude, b.longitude)
    c.ok(d > 0.5, "the position does not move")
    c.near(d / (stamp(b) - stamp(a)), 5.0, 0.4, "the speed between the first and the last fix (m/s)")
    c.near(bearing_deg(a.latitude, a.longitude, b.latitude, b.longitude), 30.0, 3.0, "the direction of motion (°)")


@c.test("TODO 7 — `ros2 param set /fake_gps heading_deg 90.0` turns the vehicle east while it runs",
        hint="Read heading_deg with self.get_parameter('heading_deg').value INSIDE on_timer, at every tick, "
             "not once in __init__.")
def _():
    after = run_default()["after"]
    c.ok(len(after) >= 4, f"only {len(after)} messages after the parameter change")
    a, b = after[0], after[-1]
    c.near(bearing_deg(a.latitude, a.longitude, b.latitude, b.longitude), 90.0, 3.0,
           "the direction of motion after heading_deg := 90 (°)")


SAL = {}


@c.test("parameters from the command line: 4 Hz, 10 m/s due east, starting in Monastir",
        hint="Start the node with  --ros-args -p rate_hz:=4.0 -p speed_mps:=10.0 -p heading_deg:=90.0 "
             "-p start_lat:=35.78 -p start_lon:=10.83  — rate, start and speed must all come from the parameters.")
def _():
    from sensor_msgs.msg import NavSatFix
    if "msgs" not in SAL:
        cmd = ("python3 -u fake_gps.py --ros-args -p rate_hz:=4.0 -p speed_mps:=10.0 -p heading_deg:=90.0 "
               "-p start_lat:=35.78 -p start_lon:=10.83")
        with Background(cmd, settle=3.0):
            SAL["msgs"] = wait_for_messages("/fake_gps/fix", NavSatFix, count=1, timeout=12) and \
                wait_for_messages("/fake_gps/fix", NavSatFix, count=12, timeout=8)
    msgs = SAL["msgs"] or []
    c.ok(len(msgs) >= 5, f"only {len(msgs)} messages with these parameters")
    c.ok(dist_m(msgs[0].latitude, msgs[0].longitude, *MONASTIR) < 300,
         f"the first fix ({msgs[0].latitude:.4f}, {msgs[0].longitude:.4f}) is not near Monastir {MONASTIR}")
    dt = stamp(msgs[-1]) - stamp(msgs[0])
    c.near((len(msgs) - 1) / dt, 4.0, 0.5, "the rate (Hz)")
    c.near(dist_m(msgs[0].latitude, msgs[0].longitude, msgs[-1].latitude, msgs[-1].longitude) / dt, 10.0, 0.8,
           "the speed (m/s)")


def reference_error(d, h):
    from navera_common.geo import dead_reckon
    lat0, lon0 = SOUSSE
    n, e = d * math.cos(math.radians(h)), d * math.sin(math.radians(h))
    flat = (lat0 + math.degrees(n / R), lon0 + math.degrees(e / (R * math.cos(math.radians(lat0)))))
    sph = dead_reckon(lat0, lon0, h, d, 1.0)
    return dist_m(*flat, *sph)


def results():
    c.file_exists("results.json")
    try:
        return json.load(open("results.json"))
    except ValueError as e:
        c.ok(False, f"results.json is not valid JSON: {e}")


@c.test("TODO 8/9 — analysis.py: flat-Earth errors and the d² formula (results.json)",
        hint="flat_error_m(): the flat end point vs dead_reckon()'s end point, distance with haversine_m. "
             "predicted_due_east_m(): d² · tan(lat) / (2R). Then run `python3 analysis.py`.")
def _():
    a = load_student("analysis.py")
    (fe, pe) = need(a, "flat_error_m", "predicted_due_east_m")
    c.near(fe(10_000.0, 30.0), reference_error(10_000.0, 30.0), 0.01, "flat_error_m(10 km, 30°) (m)")
    c.near(pe(10_000.0, SOUSSE[0]), 1e8 * math.tan(math.radians(SOUSSE[0])) / (2 * R), 1e-3,
           "predicted_due_east_m(10 km, 35.8277°) (m)")
    r = results()
    for key, h in (("flat_error_heading30_m", 30.0), ("flat_error_east_m", 90.0)):
        for d in ("1000", "10000", "100000"):
            got = (r.get(key) or {}).get(d)
            want = reference_error(float(d), h)
            c.ok(got is not None, f"results.json has no {key}[{d}] — run python3 analysis.py")
            c.near(got, want, max(0.002, 0.01 * want), f"results.json {key}[{d}]")


@c.test("your measurements of the running node (results.json → measured)",
        hint="Copy average rate, min, max and std dev from `ros2 topic hz /fake_gps/fix`, and the "
             "`Message size mean` from `ros2 topic bw /fake_gps/fix`, into MEASURED in analysis.py; run it again.")
def _():
    m = results().get("measured") or {}
    for k in ("rate_hz", "period_min_s", "period_max_s", "period_std_s", "msg_bytes"):
        c.ok(isinstance(m.get(k), (int, float)), f"measured.{k} is missing — fill MEASURED in analysis.py and run it")
    c.near(m["rate_hz"], 2.0, 0.1, "measured.rate_hz")
    c.ok(0.3 < m["period_min_s"] <= 0.5 <= m["period_max_s"] < 0.8,
         f"min {m['period_min_s']} and max {m['period_max_s']} should surround 0.5 s")
    c.ok(0 <= m["period_std_s"] < 0.05, f"measured.period_std_s = {m['period_std_s']} s looks wrong (seconds!)")
    c.near(m["msg_bytes"], 128, 12, "measured.msg_bytes (B)")


@c.test("report.md — Timing and Flat Earth, with your numbers",
        hint="Keep the headings ## Timing and ## Flat Earth, at least 40 words each. Timing must quote your measurements; "
             "Flat Earth must quote your 100 km error (rounded to the metre is fine).")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8", errors="replace").read()
    r = results()
    secs = {}
    for title in ("Timing", "Flat Earth"):
        m = re.search(r"^##\s*" + title + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
        c.ok(m is not None, f"the heading `## {title}` is missing")
        body = re.sub(r"^\*(?=\S)[^*]+?\*\s*$", "", m.group(1), flags=re.M | re.S)
        words = len(re.findall(r"[A-Za-z0-9_.]+", body))
        c.ok(words >= 40, f"section {title} has {words} words of yours — write at least 40")
        secs[title] = body
    e100 = r["flat_error_heading30_m"]["100000"]
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", secs["Flat Earth"])]
    c.ok(any(abs(x - e100) <= max(1.0, 0.01 * e100) for x in nums),
         f"the Flat Earth section does not quote your 100 km error ({e100:.0f} m)")
    c.ok(re.search(r"\d", secs["Timing"]) is not None, "the Timing section quotes no measurement")


c.run()
