"""navera_lite/ros/gps_node.py — a fake GNSS receiver: a ROS 2 node that moves a vehicle with the REAL time
between its timer ticks and publishes honest NavSatFix messages. Part of NAVERA Lite, the course's teaching
stack (mission 10; mission 13 adds checked parameters). Written for the course; it is not NAVERA code.

    python3 -m navera_lite.ros.gps_node                                       defaults (DEFAULTS below)
    python3 -m navera_lite.ros.gps_node --ros-args -p speed_mps:=12.0         write 12.0, not 12
    ros2 param set /fake_gps heading_deg 90.0                                 turn east while it runs
    ros2 topic echo /navera_lite/fix/gps                                      watch it (another terminal)

It publishes on navera_lite/fix/gps (a relative name: in the namespace /drone it becomes
/drone/navera_lite/fix/gps), so arbiter v0 can use it directly.
"""
import math

from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor, SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

from navera_lite.estimate import COV_APPROXIMATED, COV_UNKNOWN
from navera_lite.geo import offset
from navera_lite.ros.convert import s_to_stamp
from navera_lite.ros.qos import FIX_QOS
from navera_lite.ros.runner import run_node
from navera_lite.vehicle import VEHICLES, ground_velocity

# @part 10
TOPIC = "navera_lite/fix/gps"
# @part 10
ALTITUDE_M = 40.0                   # metres above the WGS84 ellipsoid (the fake vehicle flies level)
# @part 10
DEFAULTS = {
    "rate_hz": 1.0,                 # fixes per second (a real receiver: 1 Hz)
    "speed_mps": 10.0,              # ground speed, m/s
    "heading_deg": 90.0,            # direction of motion, clockwise from north (90 = east)
    "start_lat": 35.8256,           # NAVERA's test area near Sousse, Tunisia
    "start_lon": 10.6084,
    "sigma_m": 3.0,                 # the 1-σ horizontal accuracy the receiver states; 0 = it states none
    "stamp_offset_s": 0.0,          # the saboteur's knob: header.stamp = now + this (−5.0: 5 s old)
    "vehicle": "drone",             # a key of vehicle.VEHICLES (mission 13 checks the speed against it)
}


# @part 10 todo 1
def step(lat, lon, speed_mps, heading_deg, dt_s):
    """Where a vehicle at (lat, lon) is after moving dt_s seconds at speed_mps on heading_deg (degrees,
    clockwise from north), on the flat-Earth shortcut of mission 06. No wind. Raises ValueError if dt_s < 0.

    Returns (lat, lon) in degrees.
    Example: step(35.8256, 10.6084, 10.0, 90.0, 0.62) → (about 35.8256, about 10.608469)   (6.2 m east)
    """
    if dt_s < 0:
        raise ValueError(f"dt_s must be >= 0, got {dt_s}")
    ve, vn = ground_velocity(speed_mps, heading_deg)
    return offset(lat, lon, ve * dt_s, vn * dt_s)


# @part 10 todo 2
def covariance_from_sigma(sigma_m):
    """The covariance a receiver stating a horizontal 1-σ of sigma_m metres publishes: σ² on East and North,
    (2σ)² on Up, 0.0 elsewhere — 9 FLOATS, ENU, row-major, m² — and its type, COV_APPROXIMATED.
    An accuracy that is not stated (None, nan, ≤ 0) is never invented: (nine 0.0, COV_UNKNOWN).

    Returns (cov9, cov_type): a list of 9 floats and an int.
    Example: covariance_from_sigma(3.0) → ([9.0, 0.0, 0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 36.0], 1)
    """
    if sigma_m is None or isinstance(sigma_m, bool) or not isinstance(sigma_m, (int, float)) \
            or not math.isfinite(sigma_m) or sigma_m <= 0:
        return [0.0] * 9, COV_UNKNOWN
    var = float(sigma_m) ** 2
    return [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 4.0 * var], COV_APPROXIMATED


# @part 10 todo 3
def make_fix(lat, lon, alt_m, sigma_m, stamp_s):
    """One complete, honest sensor_msgs/NavSatFix (lesson §4 table): header.stamp from stamp_s (seconds,
    use convert.s_to_stamp), frame_id "gps", status STATUS_FIX, service SERVICE_GPS, the position as floats,
    and the covariance and its type from covariance_from_sigma(sigma_m).
    Example: make_fix(35.8256, 10.6084, 40.0, 3.0, 100.5).position_covariance_type → 1
             (and .header.stamp → Time(sec=100, nanosec=500000000))
    """
    msg = NavSatFix()
    msg.header.stamp = s_to_stamp(stamp_s)
    msg.header.frame_id = "gps"
    msg.status.status = NavSatStatus.STATUS_FIX
    msg.status.service = NavSatStatus.SERVICE_GPS
    msg.latitude = float(lat)
    msg.longitude = float(lon)
    msg.altitude = float(alt_m)
    cov, cov_type = covariance_from_sigma(sigma_m)
    msg.position_covariance = cov
    msg.position_covariance_type = cov_type
    return msg


# @part 10
class FakeGps(Node):
    """The fake receiver, a node named "fake_gps". __init__ is finished: it calls your declare_all() and
    start(); the timer then calls your on_timer() rate_hz times a second.
    """

    def __init__(self):
        super().__init__("fake_gps")
        self.pub = None                      # start() creates the publisher here
        self.lat = self.lon = None           # the vehicle's position now (declare_all() sets the start)
        self.last_t = None                   # the time of the previous tick (s), None before the first
        self.count = 0
        self.declare_all()
        self.start()
        self.get_logger().info(f"fake GPS on {self.resolve_topic_name(TOPIC)} from ({self.lat}, {self.lon})")

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    # @part 10 todo 4
    def declare_all(self):
        """Declare one ROS parameter per entry of DEFAULTS (name and default value), then put the start
        position (start_lat, start_lon, READ from the parameters) in self.lat and self.lon.
        Example: after it, self.get_parameter("speed_mps").value → 10.0 (or what --ros-args -p gave)
        """
        for name, value in DEFAULTS.items():
            self.declare_parameter(name, value)
        self.lat = self.get_parameter("start_lat").value
        self.lon = self.get_parameter("start_lon").value

    # @part 10 todo 5
    def start(self):
        """Create the publisher (NavSatFix on TOPIC, with qos.FIX_QOS) in self.pub, and a timer that calls
        self.on_timer every 1 / rate_hz seconds (rate_hz read from the parameters).
        Example: with rate_hz 2.0, `ros2 topic hz /navera_lite/fix/gps` shows about 2.0
        """
        self.pub = self.create_publisher(NavSatFix, TOPIC, FIX_QOS)
        self.create_timer(1.0 / self.get_parameter("rate_hz").value, self.on_timer)

    # @part 10 todo 6
    def on_timer(self):
        """One tick: dt = the REAL time since the previous tick (0.0 on the first one; remember now in
        self.last_t); move self.lat, self.lon with step() using speed_mps and heading_deg read NOW from the
        parameters (so `ros2 param set` works while it runs); publish make_fix(...) stamped
        now + stamp_offset_s, with sigma_m from the parameters.
        Example: ticks at real dt 0.50, 0.62, 0.41, 0.55 s at 10 m/s move the vehicle 20.8 m, not 20.0 m
        """
        now = self.now_s()
        dt = 0.0 if self.last_t is None else now - self.last_t
        self.last_t = now
        p = {name: self.get_parameter(name).value for name in DEFAULTS}
        self.lat, self.lon = step(self.lat, self.lon, p["speed_mps"], p["heading_deg"], dt)
        self.pub.publish(make_fix(self.lat, self.lon, ALTITUDE_M, p["sigma_m"], now + p["stamp_offset_s"]))
        self.count += 1
        if self.count % 10 == 1:
            self.get_logger().info(f"fix {self.count}: lat {self.lat:.6f}  lon {self.lon:.6f}")


# @part 10
NODE_CLASS = FakeGps                 # the node main() starts


# @part 13 todo 1
def make_descriptor(name, value):
    """The ParameterDescriptor of one FakeGps parameter (lesson 13 §2): a description, and limits that
    refuse impossible values at `ros2 param set` and in --params-file:
      rate_hz        read_only=True, floating_point_range 0.1 … 50.0
      speed_mps      floating_point_range 0.0 … 100.0
      heading_deg    floating_point_range 0.0 … 360.0
      sigma_m        floating_point_range 0.0 … 1000.0
      any other      a description only
    name, value: the parameter and its default (value is not used for the limits). The description is
    one short sentence of your own (not checked).
    Example: make_descriptor("speed_mps", 10.0).floating_point_range[0].to_value → 100.0
    """
    limits = {"rate_hz": (0.1, 50.0), "speed_mps": (0.0, 100.0), "heading_deg": (0.0, 360.0),
              "sigma_m": (0.0, 1000.0)}
    d = ParameterDescriptor(description=f"fake GPS setting {name} (default {value})")
    if name in limits:
        lo, hi = limits[name]
        d.floating_point_range = [FloatingPointRange(from_value=lo, to_value=hi, step=0.0)]
    if name == "rate_hz":
        d.read_only = True
    return d


# @part 13
class CheckedGps(FakeGps):
    """FakeGps with checked parameters (mission 13): limits from make_descriptor(), and a callback that
    refuses a speed the vehicle cannot fly. Same node name, same topic.
    """

    # @part 13 todo 2
    def declare_all(self):
        """Like FakeGps.declare_all, but declare each parameter WITH make_descriptor(name, value), and
        register self.on_set_parameters with self.add_on_set_parameters_callback (after declaring).
        Example: `ros2 param set /fake_gps rate_hz 5.0` → "Setting parameter failed: … read-only"
        """
        for name, value in DEFAULTS.items():
            self.declare_parameter(name, value, make_descriptor(name, value))
        self.lat = self.get_parameter("start_lat").value
        self.lon = self.get_parameter("start_lon").value
        self.add_on_set_parameters_callback(self.on_set_parameters)

    # @part 13 todo 3
    def on_set_parameters(self, params):
        """Called by ROS before parameters change. Refuse the change when it would make speed_mps larger
        than VEHICLES[vehicle] (use the NEW value of each one when it is in params, the current one
        otherwise) or name a vehicle that is not in VEHICLES. Returns an rcl_interfaces SetParametersResult:
        successful=True, or successful=False with a reason that names the limit.
        Example: vehicle "boat" (20 m/s), set speed_mps 25.0 → SetParametersResult(successful=False,
                 reason="speed_mps 25.0 > 20.0 m/s, the top speed of a boat")
        """
        new = {p.name: p.value for p in params}
        vehicle = new.get("vehicle", self.get_parameter("vehicle").value)
        speed = new.get("speed_mps", self.get_parameter("speed_mps").value)
        if vehicle not in VEHICLES:
            return SetParametersResult(successful=False,
                                       reason=f"vehicle must be one of {', '.join(VEHICLES)}, got {vehicle!r}")
        if speed > VEHICLES[vehicle]:
            return SetParametersResult(successful=False, reason=f"speed_mps {speed} > {VEHICLES[vehicle]} m/s, "
                                                                f"the top speed of a {vehicle}")
        return SetParametersResult(successful=True)


# @part 13
NODE_CLASS = CheckedGps              # from mission 13 on, main() starts the checked node


# @part 10
def main(args=None):
    """Start the fake GPS (NODE_CLASS) and spin until Ctrl+C."""
    run_node(NODE_CLASS, args)


if __name__ == "__main__":
    main()
