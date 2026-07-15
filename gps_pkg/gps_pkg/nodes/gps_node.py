#!/usr/bin/env python3
"""
gps_node.py — NAVERA GPS sensor driver.

Reads NMEA sentences from a serial GPS (e.g. /dev/ttyTHS1 on Jetson UART, or
/dev/ttyUSB0 for a USB GPS) and publishes:
    /navera/sensors/gps_fix   sensor_msgs/NavSatFix
    /navera/sensors/gps_vel   geometry_msgs/TwistStamped

Parameters:
    serial_port  (default "/dev/ttyTHS1") — serial device
    baud_rate    (default 9600)            — typical for NMEA GPS modules
"""
import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from geometry_msgs.msg import TwistStamped
import serial, pynmea2, threading, traceback


class GPSNode(Node):
    def __init__(self):
        super().__init__("gps_node")
        self.declare_parameter("serial_port", "/dev/ttyTHS1")
        self.declare_parameter("baud_rate", 9600)
        port = self.get_parameter("serial_port").value
        baud = self.get_parameter("baud_rate").value

        self.pub_fix = self.create_publisher(NavSatFix,    "/navera/sensors/gps_fix", 10)
        self.pub_vel = self.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        self.fix_count = 0

        try:
            self.ser = serial.Serial(port, baud, timeout=2)
            self.get_logger().info(f"Port open OK: {port} @ {baud}")
        except Exception as e:
            self.get_logger().error(f"FAILED to open port: {e}")
            return

        self.running = True
        threading.Thread(target=self._read_loop, daemon=True).start()
        self.get_logger().info("Read thread started")

    def _read_loop(self):
        self.get_logger().info("READ LOOP RUNNING")
        count = 0
        while self.running:
            try:
                raw = self.ser.readline().decode("ascii", errors="replace").strip()
                count += 1
                if count <= 5 or count % 30 == 0:
                    self.get_logger().info(f"LINE {count}: {raw[:80]}")
                if not raw.startswith("$"):
                    continue
                try:
                    msg = pynmea2.parse(raw)
                except pynmea2.ParseError:
                    continue
                if isinstance(msg, pynmea2.types.talker.GGA):
                    self._publish_fix(msg)
                elif isinstance(msg, pynmea2.types.talker.RMC):
                    self._publish_vel(msg)
            except serial.SerialException as e:
                self.get_logger().error(f"Serial error: {e}")
                break
            except Exception as e:
                self.get_logger().error(f"Loop error: {e}\n{traceback.format_exc()}")
        self.get_logger().error("READ LOOP EXITED")

    def _publish_fix(self, msg):
        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = "gps"
        try:
            gps_qual = int(msg.gps_qual) if msg.gps_qual else 0
        except Exception:
            gps_qual = 0
        if not msg.latitude or gps_qual == 0:
            fix.status.status = NavSatStatus.STATUS_NO_FIX
            fix.latitude = fix.longitude = fix.altitude = 0.0
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
            self.pub_fix.publish(fix)
            self.get_logger().info(f"No fix yet (qual={gps_qual})")
            return
        fix.status.status = NavSatStatus.STATUS_FIX
        fix.status.service = NavSatStatus.SERVICE_GPS | NavSatStatus.SERVICE_GLONASS
        fix.latitude = msg.latitude
        fix.longitude = msg.longitude
        fix.altitude = float(msg.altitude) if msg.altitude else 0.0
        hdop = float(msg.horizontal_dil) if msg.horizontal_dil else 2.0
        cov = (hdop * 2.0) ** 2
        fix.position_covariance = [float(cov),0.0,0.0, 0.0,float(cov),0.0, 0.0,0.0,float(cov*4)]
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        self.pub_fix.publish(fix)
        self.fix_count += 1
        self.get_logger().info(
            f"FIX #{self.fix_count}: lat={msg.latitude:.6f} lon={msg.longitude:.6f} "
            f"alt={fix.altitude:.1f}m sats={msg.num_sats} hdop={hdop:.1f}"
        )

    def _publish_vel(self, msg):
        try:
            if not msg.latitude or msg.status != "A":
                return
            vel = TwistStamped()
            vel.header.stamp = self.get_clock().now().to_msg()
            vel.header.frame_id = "gps"
            vel.twist.linear.x = float(msg.spd_over_grnd)*0.5144 if msg.spd_over_grnd else 0.0
            self.pub_vel.publish(vel)
        except Exception as e:
            self.get_logger().error(f"vel error: {e}")

    def destroy_node(self):
        self.running = False
        if hasattr(self, "ser") and self.ser.is_open:
            self.ser.close()
        super().destroy_node()


def main(args=None):
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = GPSNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
