"""navera_lite/ros/trip_node.py — a trip computer: a subscriber WITH MEMORY. It listens to the GPS fixes,
refuses the bad ones (and says why), adds up the distance, measures the speed over a time window, and
notices when the receiver goes silent. Part of NAVERA Lite, the course's teaching stack (mission 11).
Written for the course; it is not NAVERA code.

    python3 -m navera_lite.ros.trip_node
    python3 -m navera_lite.ros.trip_node --ros-args -p window_s:=10.0 -p silence_s:=3.0
    ros2 topic echo /navera_lite/trip

Subscribes navera_lite/fix/gps (NavSatFix); publishes navera_lite/trip (DiagnosticStatus, name
"navera_lite/trip", values distance_m, speed_mps, fixes, refused, last_refusal, silent) once a second.
"""
import math

from diagnostic_msgs.msg import DiagnosticStatus, KeyValue
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

from navera_lite.geo import enu_flat, haversine_m, is_finite_latlon
from navera_lite.guard import gate_ok
from navera_lite.ros.convert import from_navsatfix
from navera_lite.ros.qos import FIX_QOS
from navera_lite.ros.runner import run_node


# @part 11
class TripComputer:
    """The memory of the trip: accepted fixes (time, lat, lon), total distance, refusals.

    max_speed_mps, margin_m: the jump gate's numbers (mission 01). update(est) is yours (TODO 1).
    Example: tc = TripComputer(); tc.update(Estimate("gps", 35.8256, 10.6084, 0.0)) → (True, "first fix")
    """

    def __init__(self, max_speed_mps=100.0, margin_m=50.0):
        self.max_speed_mps = max_speed_mps
        self.margin_m = margin_m
        self.fixes = []            # accepted fixes, oldest first: (t_s, lat, lon)
        self.distance_m = 0.0      # along the accepted fixes
        self.refused = 0
        self.last_refusal = ""

    # @part 11 todo 1
    def update(self, est):
        """Judge one GPS Estimate; remember it only if it is good. Returns (ok, reason).
        Four reasons to refuse (lesson §3 decides their ORDER: the first rule broken gives the reason):
          the source says it has no position (est.valid is False)            → (False, "no position")
          not a usable latitude/longitude (geo.is_finite_latlon)             → (False, "bad position")
          its stamp is not newer than the last ACCEPTED fix's stamp         → (False, "old fix")
          mission 01's jump gate refuses it, from the last ACCEPTED fix      → (False, "jump")
        Otherwise: (True, "first fix") for the very first one, else (True, "ok").
        Memory: accepted fixes are kept in self.fixes as (stamp_s, lat, lon), and self.distance_m is the
        great-circle length along them; a refused fix only counts in self.refused and self.last_refusal.
        Example: after a first fix (35.8256, 10.6084) at t = 0.0, a fix 5 km away at t = 1.0 → (False, "jump")
        """
        ok, why = True, "ok"
        if not est.valid:
            ok, why = False, "no position"
        elif not is_finite_latlon(est.lat, est.lon):
            ok, why = False, "bad position"
        elif self.fixes and est.stamp_s <= self.fixes[-1][0]:
            ok, why = False, "old fix"
        elif self.fixes:
            t0, lat0, lon0 = self.fixes[-1]
            e, n = enu_flat(lat0, lon0, est.lat, est.lon)
            if not gate_ok((0.0, 0.0), (e, n), est.stamp_s - t0, self.max_speed_mps, self.margin_m):
                ok, why = False, "jump"
        if not ok:
            self.refused += 1
            self.last_refusal = why
            return False, why
        if self.fixes:
            _, lat0, lon0 = self.fixes[-1]
            self.distance_m += haversine_m(lat0, lon0, est.lat, est.lon)
        else:
            why = "first fix"
        self.fixes.append((est.stamp_s, est.lat, est.lon))
        return True, why


# @part 11 todo 2
def speed_window(fixes, window_s):
    """The average speed (m/s) over the last window_s seconds: the haversine distance from the OLDEST fix
    whose time is ≥ (newest time − window_s) to the newest fix, divided by the time between them.
    fixes: a list of (t_s, lat, lon), oldest first. None when fewer than 2 fixes are in the window.
    A long window averages the GPS noise away, and pays with a delay (lesson §4).
    Example: speed_window([(0.0, 35.8256, 10.6084), (5.0, 35.8256, 10.60895), (10.0, 35.8256, 10.61005)], 6.0)
             → about 19.83   (only the fixes at 5 s and 10 s are inside: 99.2 m in 5 s)
    """
    if len(fixes) < 2:
        return None
    t_new = fixes[-1][0]
    inside = [f for f in fixes if f[0] >= t_new - window_s]
    if len(inside) < 2 or inside[-1][0] <= inside[0][0]:
        return None
    (t0, lat0, lon0), (t1, lat1, lon1) = inside[0], inside[-1]
    return haversine_m(lat0, lon0, lat1, lon1) / (t1 - t0)


# @part 11
class Watchdog:
    """Notices silence: kick(now_s) at every message; silent(now_s) is yours (TODO 3).

    Example: w = Watchdog(3.0); w.kick(10.0); w.silent(12.0) → False; w.silent(13.5) → True
    """

    def __init__(self, silence_s):
        self.silence_s = silence_s
        self.last_s = None         # time of the last kick, None before the first

    def kick(self, now_s):
        self.last_s = now_s

    # @part 11 todo 3
    def silent(self, now_s):
        """True when nothing came for MORE than self.silence_s seconds before now_s — and before the first
        message (nothing ever came). False otherwise.
        Example: w = Watchdog(3.0); w.silent(0.0) → True; w.kick(10.0); w.silent(13.0) → False; w.silent(13.1) → True
        """
        return self.last_s is None or now_s - self.last_s > self.silence_s


# @part 11
class TripNode(Node):
    """The trip computer as a node named "trip". __init__ is finished; listen() and on_fix() are yours."""

    def __init__(self):
        super().__init__("trip")
        self.declare_parameter("window_s", 5.0)
        self.declare_parameter("silence_s", 3.0)
        self.computer = TripComputer()
        self.watchdog = Watchdog(self.get_parameter("silence_s").value)
        self.pub = self.create_publisher(DiagnosticStatus, "navera_lite/trip", FIX_QOS)
        self.was_silent = None
        self.listen()
        self.create_timer(1.0, self.publish_trip)

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    # @part 11 todo 4
    def listen(self):
        """Subscribe to navera_lite/fix/gps (type NavSatFix, QoS qos.FIX_QOS) with self.on_fix as the callback,
        and keep the subscription in self.sub (so that you can look at it later, e.g. self.sub.topic_name).
        Example: after it, `ros2 node info /trip` lists /navera_lite/fix/gps under Subscribers
        """
        self.sub = self.create_subscription(NavSatFix, "navera_lite/fix/gps", self.on_fix, FIX_QOS)

    # @part 11 todo 5
    def on_fix(self, msg):
        """The callback, called once for every NavSatFix that arrives: the watchdog and the trip computer must
        hear about it, and a refused fix must leave a warning that says why (lesson §1, §3, §5).
        Example: a fix 5 km away → the terminal shows "[WARN] [...] [trip]: fix refused: jump"
        """
        now = self.now_s()
        self.watchdog.kick(now)
        ok, why = self.computer.update(from_navsatfix(msg, source="gps", now_s=now))
        if not ok:
            self.get_logger().warn(f"fix refused: {why}")

    def publish_trip(self):
        """Once a second: the trip so far, as a DiagnosticStatus (OK, or WARN while the GPS is silent)."""
        now = self.now_s()
        silent = self.watchdog.silent(now)
        if silent != self.was_silent:
            self.get_logger().info("GPS silent" if silent else "GPS talking")
            self.was_silent = silent
        speed = speed_window(self.computer.fixes, self.get_parameter("window_s").value)
        values = {"distance_m": f"{self.computer.distance_m:.1f}",
                  "speed_mps": "" if speed is None or not math.isfinite(speed) else f"{speed:.2f}",
                  "fixes": str(len(self.computer.fixes)), "refused": str(self.computer.refused),
                  "last_refusal": self.computer.last_refusal, "silent": str(silent).lower()}
        msg = DiagnosticStatus(level=DiagnosticStatus.WARN if silent else DiagnosticStatus.OK,
                               name="navera_lite/trip", message="GPS silent" if silent else "ok",
                               values=[KeyValue(key=k, value=v) for k, v in values.items()])
        self.pub.publish(msg)


# @part 11
def main(args=None):
    """Start the trip computer and spin until Ctrl+C."""
    run_node(TripNode, args)


if __name__ == "__main__":
    main()
