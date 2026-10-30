"""navera_lite/ros/nmea_node.py — replays a GNSS receiver's NMEA log on navera_lite/fix/gps, through the
parsers of gnss.py: one GGA sentence per tick → one NavSatFix. Part of NAVERA Lite, the course's teaching
stack (given in mission 15). Written for the course; it is not NAVERA code.

    python3 -m navera_lite.ros.nmea_node --ros-args -p file:=/data/academy/15-gps-nmea/sousse_drive.nmea

Every GGA line is published, also the ones the receiver marks as "no fix": they go out with
status -1 (STATUS_NO_FIX) and the reason in the log, so the judge KNOWS the receiver is alive but has no
position — silence would mean something else. Lines with a bad checksum are skipped (and counted).
The stamp is the replay instant: a recorded log's UTC times are in the past.
Parameters: file (required), rate_hz (1.0: one GGA per second, like the receiver), loop (true).
"""
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

from navera_lite.estimate import Estimate
from navera_lite.gnss import covariance_from_hdop, fix_decision, is_valid, parse_gga, read_log, sentence_type
from navera_lite.ros.convert import to_navsatfix
from navera_lite.ros.qos import FIX_QOS
from navera_lite.ros.runner import run_node


# @part 15
def gga_to_estimate(gga, stamp_s):
    """One parsed GGA (a dict from parse_gga) → (Estimate, reason) for the source "gps": valid only when
    fix_decision accepts it; the covariance from covariance_from_hdop (unknown when the HDOP is missing);
    the height above the ellipsoid = alt_msl_m + geoid_m when both are known.
    Example: gga_to_estimate(parse_gga("$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70"),
             100.0)[0].cov_type → 1
    """
    ok, why = fix_decision(gga)
    if not ok:
        return Estimate("gps", float("nan"), float("nan"), stamp_s, valid=False, reason=why), why
    cov, cov_type = covariance_from_hdop(gga.get("hdop"))
    alt, geoid = gga.get("alt_msl_m"), gga.get("geoid_m")
    alt_m = alt + geoid if alt is not None and geoid is not None else float("nan")
    return Estimate("gps", gga["lat"], gga["lon"], stamp_s, cov=tuple(cov), cov_type=cov_type, alt_m=alt_m), why


# @part 15
class NmeaReplay(Node):
    """The NMEA replay node, named "nmea"."""

    def __init__(self):
        super().__init__("nmea")
        self.declare_parameter("file", "")
        self.declare_parameter("rate_hz", 1.0)
        self.declare_parameter("loop", True)
        path = self.get_parameter("file").value
        if not path:
            raise ValueError("give the log: --ros-args -p file:=<path to a .nmea file>")
        lines = read_log(path)
        self.ggas = [ln for ln in lines if sentence_type(ln) == "GGA"]          # None for a bad checksum
        skipped = sum(1 for ln in lines if "GGA," in ln and not is_valid(ln))
        if not self.ggas:
            raise ValueError(f"{path}: no GGA sentence with a good checksum")
        self.next = 0
        self.pub = self.create_publisher(NavSatFix, "navera_lite/fix/gps", FIX_QOS)
        self.create_timer(1.0 / float(self.get_parameter("rate_hz").value), self.on_timer)
        self.get_logger().info(f"{len(self.ggas)} GGA sentences from {path} ({skipped} skipped: bad checksum)")

    def on_timer(self):
        if self.next >= len(self.ggas):
            if not self.get_parameter("loop").value:
                return
            self.next = 0
        line = self.ggas[self.next]
        self.next += 1
        now = self.get_clock().now().nanoseconds * 1e-9
        est, why = gga_to_estimate(parse_gga(line), now)
        if not est.valid:
            self.get_logger().warn(f"no position in this GGA: {why}")
        self.pub.publish(to_navsatfix(est))


# @part 15
def main(args=None):
    """Start the NMEA replay and spin until Ctrl+C."""
    run_node(NmeaReplay, args)


if __name__ == "__main__":
    main()
