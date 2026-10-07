import math
import time

from academy_check import Background, Checker, load_student, need, sh, wait_for_messages

c = Checker()
R = 6_371_000.0
START = (35.8256, 10.6084)


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def mod():
    return load_student("fake_gps.py")


@c.test("fake_gps.py loads without errors",
        hint="Run `python3 fake_gps.py` and read the error message (line number!).")
def _():
    need(mod(), "meters_to_degrees", "position_at", "make_fix", "FakeGps")


@c.test("TODO 1 — meters_to_degrees(): 111 195 m north is 1 degree of latitude",
        hint="One degree of latitude is 2π × R / 360 metres: divide the metres north by that length.")
def _():
    (f,) = need(mod(), "meters_to_degrees")
    out = f(111_195.0, 0.0, 35.0)
    c.ok(isinstance(out, (tuple, list)) and len(out) == 2, f"meters_to_degrees should return 2 numbers, got {out!r}")
    c.near(out[0], 1.0, 0.003, "dlat for 111 195 m north")
    c.near(out[1], 0.0, 1e-9, "dlon for 0 m east")


@c.test("TODO 1 — meters_to_degrees(): longitude degrees are shorter away from the equator",
        hint="At latitude 60°, cos(60°) = 0.5: one degree of longitude is only half as long, "
             "so the same metres east give TWICE as many degrees. Use math.cos(math.radians(lat_deg)).")
def _():
    (f,) = need(mod(), "meters_to_degrees")
    c.near(f(0.0, 111_195.0, 0.0)[1], 1.0, 0.003, "dlon for 111 195 m east at the equator")
    c.near(f(0.0, 111_195.0, 60.0)[1], 2.0, 0.006, "dlon for 111 195 m east at latitude 60°")


@c.test("TODO 2 — position_at(0) is the start and position_at(10) is 50 m away to the north-east",
        hint="Distance = speed × time, separately north and east. Convert both with meters_to_degrees() "
             "at START_LAT, then add the result to the start point.")
def _():
    (f,) = need(mod(), "position_at")
    lat0, lon0 = f(0.0)
    c.ok(dist_m(lat0, lon0, *START) < 0.5, f"position_at(0) = {lat0, lon0}, expected the start {START}")
    lat1, lon1 = f(10.0)
    c.near(dist_m(lat0, lon0, lat1, lon1), 50.0, 1.0, "distance travelled in 10 s (m)")
    c.ok(lat1 > lat0 and lon1 > lon0, "after 10 s the vehicle should be further north AND further east")


@c.test("TODO 3 — make_fix() fills status, position and covariance",
        hint="Fill status (two fields), latitude / longitude / altitude, the 9 covariance numbers "
             "(variances, so sigma squared) and position_covariance_type. The NavSatStatus and NavSatFix "
             "constants are in the course.")
def _():
    from builtin_interfaces.msg import Time
    from sensor_msgs.msg import NavSatFix, NavSatStatus
    (f,) = need(mod(), "make_fix")
    m = f(35.9, 10.5, Time(sec=1000, nanosec=0))
    c.ok(isinstance(m, NavSatFix), f"make_fix should return a NavSatFix, got {type(m).__name__}")
    c.near(m.latitude, 35.9, 1e-9, "latitude")
    c.near(m.longitude, 10.5, 1e-9, "longitude")
    c.near(m.altitude, 40.0, 1e-6, "altitude")
    c.eq(m.status.status, NavSatStatus.STATUS_FIX, "status.status")
    c.eq(m.status.service, NavSatStatus.SERVICE_GPS, "status.service")
    cov = list(m.position_covariance)
    c.near(cov[0], 9.0, 1e-6, "position_covariance[0] (east variance = 3 m squared)")
    c.near(cov[4], 9.0, 1e-6, "position_covariance[4] (north variance)")
    c.near(cov[8], 36.0, 1e-6, "position_covariance[8] (up variance = 6 m squared)")
    c.ok(all(cov[i] == 0.0 for i in (1, 2, 3, 5, 6, 7)), "the 6 numbers off the diagonal should be 0.0")
    c.eq(m.position_covariance_type, NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN, "position_covariance_type")


RUN = {"done": False, "msgs": [], "nodes": "", "out": ""}


def collect(need_msgs=True):
    """Run the student's node once and keep what it published (shared by the next checks)."""
    if not RUN["done"]:
        RUN["done"] = True
        from sensor_msgs.msg import NavSatFix
        with Background("python3 fake_gps.py", settle=3.0) as bg:
            if wait_for_messages("/fake_gps/fix", NavSatFix, count=1, timeout=15):
                RUN["msgs"] = wait_for_messages("/fake_gps/fix", NavSatFix, count=9, timeout=12)
            RUN["nodes"] = sh("ros2 node list --no-daemon --spin-time 3", timeout=20)[1]
        RUN["out"] = bg.output()
    if need_msgs and len(RUN["msgs"]) < 3:
        if RUN.get("told"):
            c.ok(False, "not enough messages on /fake_gps/fix (see the check above)")
        RUN["told"] = True
        out = RUN["out"]
        c.ok(False, f"only {len(RUN['msgs'])} messages arrived on /fake_gps/fix." +
             (f"\n     Your node printed:\n{out[-700:]}" if out.strip() else ""))
    return RUN["msgs"]


@c.test("TODO 4/5 — the node publishes NavSatFix messages on /fake_gps/fix",
        hint="TODO 4: create_publisher(message type, topic, depth) stored in self.pub. TODO 5: "
             "create_timer(period, callback) — the period is 1 / RATE_HZ. Watch it with `ros2 topic echo /fake_gps/fix`.")
def _():
    collect()


@c.test("the node is called /fake_gps in the ROS graph",
        hint='Keep super().__init__("fake_gps") — that string is the node name `ros2 node list` shows.')
def _():
    collect(need_msgs=False)
    c.ok("/fake_gps" in RUN["nodes"], "`ros2 node list` did not show /fake_gps:\n" + RUN["nodes"])


@c.test("it publishes 2 times per second",
        hint="The timer period is 1.0 / RATE_HZ seconds (0.5 s). Check with `ros2 topic hz /fake_gps/fix`.")
def _():
    msgs = collect()
    stamps = [m.header.stamp.sec + m.header.stamp.nanosec * 1e-9 for m in msgs]
    c.ok(len(msgs) >= 5, f"only {len(msgs)} messages arrived in 12 s")
    span = stamps[-1] - stamps[0]
    c.ok(span > 0, "every message has the same header.stamp — use the node's clock (now.to_msg())")
    rate = (len(stamps) - 1) / span
    c.near(rate, 2.0, 0.3, "the rate (messages per second, from the stamps)")


@c.test("the messages are stamped with the current time and say 'fix'",
        hint="header.stamp must be the time of the measurement: now.to_msg(), done for you in on_timer().")
def _():
    from sensor_msgs.msg import NavSatStatus
    m = collect()[-1]
    age = time.time() - (m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
    c.ok(abs(age) < 30, f"header.stamp is {age:.0f} s away from the current time")
    c.eq(m.status.status, NavSatStatus.STATUS_FIX, "status.status of a published message")
    c.ok(dist_m(m.latitude, m.longitude, *START) < 2000,
         f"the published position ({m.latitude:.5f}, {m.longitude:.5f}) is far from the start {START}")


@c.test("the published position moves at 5 m/s",
        hint="The position must come from position_at(t) with t = seconds since the start. "
             "3 m/s east + 4 m/s north = 5 m/s (Pythagoras!).")
def _():
    msgs = collect()
    a, b = msgs[0], msgs[-1]
    dt = (b.header.stamp.sec + b.header.stamp.nanosec * 1e-9) - (a.header.stamp.sec + a.header.stamp.nanosec * 1e-9)
    c.ok(dt > 0, "the stamps do not advance")
    d = dist_m(a.latitude, a.longitude, b.latitude, b.longitude)
    c.ok(d > 0.1, "the position does not move")
    c.near(d / dt, 5.0, 0.5, "the speed between the first and the last message (m/s)")


c.run()
