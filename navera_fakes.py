#!/usr/bin/env python3
"""
navera_fakes.py — Fake publishers for the FULL NAVERA system graph.
Lightweight nodes that publish on the REAL topics so rqt_graph shows the
complete 8-node architecture WITHOUT loading heavy AI models (no OOM).

Run a single fake:   python3 navera_fakes.py imu
Run all at once:     python3 navera_fakes.py all
"""
import sys, math, json, time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import Imu, MagneticField, NavSatFix, NavSatStatus, Image
from geometry_msgs.msg import TwistStamped
from std_msgs.msg import Float64, String, Int32, Bool


class FakeIMU(Node):
    def __init__(self):
        super().__init__("imu_node")
        self.p_imu = self.create_publisher(Imu, "/navera/sensors/imu", 10)
        self.p_mag = self.create_publisher(MagneticField, "/navera/sensors/mag", 10)
        self.p_alt = self.create_publisher(Float64, "/navera/sensors/altitude_baro", 10)
        self.create_timer(0.1, self.tick)
        self.get_logger().info("FAKE imu_node publishing /navera/sensors/{imu,mag,altitude_baro}")
    def tick(self):
        now = self.get_clock().now().to_msg()
        m = Imu(); m.header.stamp = now; m.header.frame_id = "imu"
        m.linear_acceleration.z = 9.81; m.orientation_covariance[0] = -1.0
        self.p_imu.publish(m)
        g = MagneticField(); g.header.stamp = now; g.header.frame_id = "imu"
        g.magnetic_field.x = 2.1e-5; self.p_mag.publish(g)
        a = Float64(); a.data = 400.0; self.p_alt.publish(a)


class FakeGPS(Node):
    def __init__(self):
        super().__init__("gps_node")
        self.p_fix = self.create_publisher(NavSatFix, "/navera/sensors/gps_fix", 10)
        self.p_vel = self.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        self.create_timer(1.0, self.tick)
        self.get_logger().info("FAKE gps_node publishing /navera/sensors/{gps_fix,gps_vel}")
    def tick(self):
        now = self.get_clock().now().to_msg()
        f = NavSatFix(); f.header.stamp = now; f.header.frame_id = "gps"
        f.status.status = NavSatStatus.STATUS_FIX
        f.latitude = 35.8288; f.longitude = 10.6360; f.altitude = 400.0
        self.p_fix.publish(f)
        v = TwistStamped(); v.header.stamp = now; v.header.frame_id = "gps"
        v.twist.linear.x = 5.0; self.p_vel.publish(v)


class FakeNight(Node):
    """Mirrors night_subscriber I/O without loading STHN."""
    def __init__(self):
        super().__init__("night_subscriber")
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                         history=HistoryPolicy.KEEP_LAST, depth=10)
        d1 = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                        history=HistoryPolicy.KEEP_LAST, depth=1)
        latched = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        self.create_subscription(Image, "/thermal/image_raw", lambda m: None, rel)
        self.create_subscription(String, "/thermal/frame_meta", lambda m: None, rel)
        self.p_fix = self.create_publisher(NavSatFix, "/night/position_estimate", 10)
        self.p_st  = self.create_publisher(String, "/night/night_status", 10)
        self.p_done = self.create_publisher(Int32, "/thermal/frame_done", d1)
        self.p_ready = self.create_publisher(Bool, "/night/localizer_ready", latched)
        self.p_ready.publish(Bool(data=True))
        self.create_timer(2.0, self.tick)
        self.get_logger().info("FAKE night_subscriber (STHN) wired on /thermal/* and /night/*")
    def tick(self):
        self.p_fix.publish(NavSatFix())
        self.p_st.publish(String(data=json.dumps({"source": "night_sthn"})))
        self.p_done.publish(Int32(data=0))


class FakeCN(Node):
    """Mirrors cn_subscriber I/O without astrometry."""
    def __init__(self):
        super().__init__("cn_subscriber")
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                         history=HistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(Image, "/celestial/image_raw", lambda m: None, rel)
        self.create_subscription(String, "/celestial/frame_meta", lambda m: None, rel)
        self.p_fix = self.create_publisher(NavSatFix, "/cn/position_estimate", 10)
        self.p_st  = self.create_publisher(String, "/cn/cn_status", 10)
        self.create_timer(2.0, self.tick)
        self.get_logger().info("FAKE cn_subscriber (astrometry) wired on /celestial/* and /cn/*")
    def tick(self):
        self.p_fix.publish(NavSatFix())
        self.p_st.publish(String(data=json.dumps({"source": "stellar"})))


class FakeStellarBridge(Node):
    """Mirrors navera_stellar_bridge ROS I/O (no HTTP server)."""
    def __init__(self):
        super().__init__("navera_stellar_bridge")
        self.create_subscription(String, "/cn/cn_status", lambda m: None, 10)
        self.create_subscription(NavSatFix, "/cn/position_estimate", lambda m: None, 10)
        latched = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        self.create_publisher(Bool, "/celestial/camera/start", latched)
        self.get_logger().info("FAKE navera_stellar_bridge wired on /cn/* and /celestial/camera/start")


FAKES = {"imu": FakeIMU, "gps": FakeGPS, "night": FakeNight,
         "cn": FakeCN, "stellar": FakeStellarBridge}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    rclpy.init()
    nodes = []
    if which == "all":
        for cls in FAKES.values():
            nodes.append(cls())
    elif which in FAKES:
        nodes.append(FAKES[which]())
    else:
        print(f"unknown fake '{which}'. options: {list(FAKES)} or 'all'")
        return
    ex = rclpy.executors.MultiThreadedExecutor()
    for n in nodes:
        ex.add_node(n)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        for n in nodes:
            n.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
