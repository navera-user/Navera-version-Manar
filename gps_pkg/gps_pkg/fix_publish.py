"""A receiver's fix (navera_common.gnss.Fix) as NAVERA's GPS source messages.

The same contract as gps_node's NMEA path, for the UBX and DroneCAN receivers:
    /navera/sensors/gps_fix    sensor_msgs/NavSatFix         (DIAGONAL_KNOWN from the receiver's
                                                              stated accuracy, else UNKNOWN)
    /navera/sensors/gps_vel    geometry_msgs/TwistStamped    (ENU, m/s)
    /navera/estimate/gps       navera_msgs/PositionEstimate  (SOURCE_GPS / MODE_MEASURED; an
                                                              invalid fix is published, not swallowed)
    /navera/sensors/gnss_time  sensor_msgs/TimeReference     (the receiver's UTC, when it vouches for it)
"""
import json
import math

from geometry_msgs.msg import TwistStamped
from navera_msgs.msg import PositionEstimate
from sensor_msgs.msg import NavSatFix, NavSatStatus, TimeReference

from navera_common.gnss import Fix


def navsatfix(fix: Fix, stamp, frame_id: str = "gps") -> NavSatFix:
    m = NavSatFix()
    m.header.stamp, m.header.frame_id = stamp, frame_id
    if not fix.valid:
        m.status.status = NavSatStatus.STATUS_NO_FIX
        m.latitude = m.longitude = m.altitude = math.nan
        m.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        return m
    m.status.status = NavSatStatus.STATUS_GBAS_FIX if fix.gbas else NavSatStatus.STATUS_FIX
    m.status.service = NavSatStatus.SERVICE_GPS
    m.latitude, m.longitude, m.altitude = float(fix.lat), float(fix.lon), float(fix.alt)
    cov = fix.covariance()
    if cov is not None:
        m.position_covariance = cov
        m.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    else:
        m.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
    return m


def estimate(fix: Fix, header, producer: str, model_id: str) -> PositionEstimate:
    """The GPS source contract for one fix: valid only with a satellite fix; the receiver's
    stated accuracy as a diagonal covariance (DIAGONAL_KNOWN), else UNKNOWN; details carry
    the satellites (num_sats), the geoid separation (geo_sep_m) and the receiver's figures.
    """
    est = PositionEstimate()
    est.header = header
    est.latitude = float(fix.lat) if fix.valid else math.nan
    est.longitude = float(fix.lon) if fix.valid else math.nan
    est.altitude = float(fix.alt) if fix.valid else math.nan
    cov = fix.covariance() if fix.valid else None
    if cov is None:
        est.position_covariance = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
    else:
        est.position_covariance = cov
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN
    est.source, est.mode, est.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, bool(fix.valid)
    est.confidence = 0.0                     # as gps_node: the uncertainty lives in the covariance
    est.reason = "" if fix.valid else fix.reason
    est.sensor_stamp = header.stamp
    est.producer, est.model_id, est.frame_index = producer, model_id, -1
    est.details_json = json.dumps(fix.details)
    return est


def velocity(fix: Fix, stamp, frame_id: str = "gps"):
    """Return a TwistStamped (ENU) for a valid fix that has a velocity, else None."""
    if not fix.valid or fix.vel_enu is None or not all(math.isfinite(v) for v in fix.vel_enu):
        return None
    v = TwistStamped()
    v.header.stamp, v.header.frame_id = stamp, frame_id
    v.twist.linear.x, v.twist.linear.y, v.twist.linear.z = (float(x) for x in fix.vel_enu)
    return v


def time_reference(fix: Fix, stamp, frame_id: str = "gps"):
    """Return the receiver's UTC for a valid fix that carries one (as RMC status A), else None."""
    if not fix.valid or fix.utc is None or not math.isfinite(fix.utc) or fix.utc <= 0:
        return None
    ref = TimeReference()
    ref.header.stamp, ref.header.frame_id = stamp, frame_id
    ref.time_ref.sec = int(fix.utc)
    ref.time_ref.nanosec = int(round((fix.utc - int(fix.utc)) * 1e9)) % 1_000_000_000
    ref.source = "gnss"
    return ref


class FixPublisher:
    """The four GPS topics of a node, fed one Fix at a time."""

    def __init__(self, node, producer: str, model_id: str):
        self.node, self.producer, self.model_id = node, producer, model_id
        self.pub_fix = node.create_publisher(NavSatFix, "/navera/sensors/gps_fix", 10)
        self.pub_vel = node.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        self.pub_est = node.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
        self.pub_time = node.create_publisher(TimeReference, "/navera/sensors/gnss_time", 10)
        self.count = 0

    def publish(self, fix: Fix, model_id: str = "") -> None:
        stamp = self.node.get_clock().now().to_msg()
        nav = navsatfix(fix, stamp)
        self.pub_fix.publish(nav)
        self.pub_est.publish(estimate(fix, nav.header, self.producer, model_id or self.model_id))
        for msg, pub in ((velocity(fix, stamp), self.pub_vel), (time_reference(fix, stamp), self.pub_time)):
            if msg is not None:
                pub.publish(msg)
        if fix.valid:
            self.count += 1
