#!/usr/bin/env python3
# Lesson 19 — watch what NAVERA's live camera node publishes, like day vision does:
#   /day/image_raw   the undistorted, straightened picture
#   /day/frame_meta  its description (JSON): exposure stamp, attitude, tilt, field of view...
#   /day/frame_done  our "ack" — "I am done with frame N, send the next one"
#
#     python3 watch_live.py --frames 3
# Saves out/live_view.jpg and out/live_meta.json (the last frame received), then stops.
# You don't need to change this file.
import argparse
import json
import os
import time

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import Int32, String

ap = argparse.ArgumentParser()
ap.add_argument("--ns", default="/day")
ap.add_argument("--frames", type=int, default=3)
ap.add_argument("--timeout", type=float, default=60.0)
a = ap.parse_args()


def ns_of(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


class Watch(Node):
    def __init__(self):
        super().__init__("watch_live")
        self.bridge = CvBridge()
        self.images, self.metas, self.sources = {}, [], []
        self.create_subscription(Image, a.ns + "/image_raw", self.on_image, 2)
        self.create_subscription(String, a.ns + "/frame_meta", self.on_meta, 10)
        # the pictures the "camera" sent, to see how far back NAVERA put the exposure stamp
        self.create_subscription(Image, "/vehicle/camera/image_raw", self.on_source, qos_profile_sensor_data)
        self.ack = self.create_publisher(Int32, a.ns + "/frame_done", 10)

    def on_source(self, m):
        self.sources = (self.sources + [ns_of(m.header.stamp)])[-50:]

    def on_image(self, m):
        self.images[ns_of(m.header.stamp)] = self.bridge.imgmsg_to_cv2(m, "bgr8")

    def on_meta(self, m):
        meta = json.loads(m.data)
        self.metas.append(meta)
        self.ack.publish(Int32(data=int(meta["frame_id"])))       # "done, send the next"
        print(f"frame {meta['frame_id']}: usable={meta['usable']} straightened={meta['straightened']} "
              f"tilt={meta.get('tilt_deg')} deg  heading={meta.get('heading_deg')} deg  "
              f"field of view={meta['camera_hfov_deg']} deg  attitude={meta['attitude_source']}"
              + ("" if meta["usable"] else f"  ({meta.get('reason')})"))


def main():
    rclpy.init()
    node = Watch()
    end = time.time() + a.timeout
    print(f"waiting for {a.frames} frames on {a.ns}/frame_meta ...")
    try:
        while time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.1)
            done = [m for m in node.metas if m["image_stamp_ns"] in node.images]
            if len(done) >= a.frames:
                break
        done = [m for m in node.metas if m["image_stamp_ns"] in node.images]
        if not done:
            raise SystemExit("no frame received — is live_camera.py running? (see the lab, step 6)")
        meta = done[-1]
        stamp = meta["image_stamp_ns"]
        later = [s for s in node.sources if s >= stamp]
        if later:                                   # the camera message this frame came from
            meta["source_stamp_ns"] = min(later)
            print(f"camera message stamped {min(later) / 1e9:.3f} s -> exposure stamp "
                  f"{stamp / 1e9:.3f} s : {(min(later) - stamp) / 1e9:.3f} s earlier")
        os.makedirs("out", exist_ok=True)
        cv2.imwrite("out/live_view.jpg", node.images[stamp])
        with open("out/live_meta.json", "w") as f:
            json.dump(meta, f, indent=1)
        h, w = node.images[stamp].shape[:2]
        print(f"saved out/live_view.jpg ({w}x{h}) and out/live_meta.json")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
