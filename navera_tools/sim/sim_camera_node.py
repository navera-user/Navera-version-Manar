#!/usr/bin/env python3
"""The simulated physical camera as its own process — a device next to NAVERA.

Reads the vehicle's TRUE state from the simulator (/navera/sim/state_true, JSON: lat,
lon, agl, heading, speed, vn, ve, vd, q = body ENU quaternion) and streams raw lens
frames (physical_camera.py) on `raw_topic`, each rendered for the instant it is
delivered (pose extrapolated by the expected render time). For each frame it also
publishes the truth of that instant on /navera/sim/<kind>_frame_truth (JSON:
stamp_ns, lat, lon) and, every few seconds, a JPEG preview for the dashboard.

Its own process: rendering never competes with the simulator's other threads (one
Python interpreter), as a real camera never does.
"""
import json
import math
import os
import sys
import threading
import time

import cv2
import rclpy
import yaml
from builtin_interfaces.msg import Time
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import String

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from physical_camera import PhysicalCamera  # noqa: E402
from vision_link import MultiTiles  # noqa: E402


class SimCamera(Node):
    def __init__(self):
        super().__init__("sim_camera")
        self.declare_parameter("kind", "day")                 # day | night (thermal)
        self.declare_parameter("lens_file", "")
        self.declare_parameter("raw_topic", "/sim/day_camera/image_raw")
        self.declare_parameter("maps", "")                     # MBTiles paths, ":"-separated
        self.declare_parameter("day_camera_at_night", False)
        p = lambda n: self.get_parameter(n).value             # noqa: E731
        self.kind = p("kind")
        with open(p("lens_file")) as f:
            lens = yaml.safe_load(f)
        from simulation_web.web_common import MBTilesReader
        self.tiles = MultiTiles([MBTilesReader(m, self.get_logger()) for m in str(p("maps")).split(":") if m])
        self.cam = PhysicalCamera(lens, self.tiles.get, thermal=self.kind == "night")
        self.dark = bool(p("day_camera_at_night"))
        self.pub_raw = self.create_publisher(Image, p("raw_topic"), qos_profile_sensor_data)
        self.pub_truth = self.create_publisher(String, f"/navera/sim/{self.kind}_frame_truth", 50)
        self.pub_prev = self.create_publisher(CompressedImage, f"/navera/sim/{self.kind}_preview", 2)
        self.create_subscription(String, "/navera/sim/state_true", self._on_state, 10)
        self.state, self.render_s, self.t_prev = None, 0.5, 0.0
        threading.Thread(target=self._loop, daemon=True).start()
        self.get_logger().info(f"simulated {self.kind} camera: {lens['image_width']}x{lens['image_height']} "
                               f"{lens['model']} lens → {p('raw_topic')}")

    def _on_state(self, m):
        try:
            self.state = json.loads(m.data)
        except ValueError:
            pass

    def _loop(self):
        while rclpy.ok():
            s = self.state
            if s is None or s.get("q") is None:
                time.sleep(0.1)
                continue
            d = self.render_s
            t0 = self.get_clock().now().nanoseconds
            lat = s["lat"] + s["vn"] * d / 111_320.0
            lon = s["lon"] + s["ve"] * d / (111_320.0 * math.cos(math.radians(s["lat"])))
            agl = max(s["agl"] - s["vd"] * d, 1.0)
            try:
                img = self.cam.render(lat, lon, agl, s["q"], speed_mps=s["speed"], heading_deg=s["heading"],
                                      night_day_camera=self.dark)
            except Exception as e:                            # noqa: BLE001
                self.get_logger().error(f"render: {e}", throttle_duration_sec=10.0)
                time.sleep(0.5)
                continue
            took = (self.get_clock().now().nanoseconds - t0) / 1e9
            self.render_s = 0.7 * d + 0.3 * took
            ns = t0 + int(d * 1e9)                              # the instant this view shows
            wait = (ns - self.get_clock().now().nanoseconds) / 1e9
            if wait > 0:
                time.sleep(wait)
            msg = Image()
            msg.header.stamp = Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)
            msg.header.frame_id = f"sim_{self.kind}_camera"
            msg.height, msg.width, msg.encoding = img.shape[0], img.shape[1], "bgr8"
            msg.step = img.shape[1] * 3
            msg.data = img.tobytes()
            self.pub_raw.publish(msg)
            self.pub_truth.publish(String(data=json.dumps({"stamp_ns": ns, "lat": lat, "lon": lon,
                                                            "render_s": round(took, 3)})))
            if time.monotonic() - self.t_prev > 2.0:
                self.t_prev = time.monotonic()
                ok, buf = cv2.imencode(".jpg", cv2.resize(img, (640, int(640 * img.shape[0] / img.shape[1]))),
                                       [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    c = CompressedImage()
                    c.header = msg.header
                    c.format, c.data = "jpeg", buf.tobytes()
                    self.pub_prev.publish(c)


def main():
    rclpy.init()
    node = SimCamera()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
