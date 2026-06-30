#!/usr/bin/env python3
"""
simulation_bridge.py
═════════════════════
Bridges ROS2 /drone/gps to the Flask Receiver (receiver.py).
This allows the Vision Node to receive "virtual" frames.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
import requests
import json
import base64
import os
import random
from pathlib import Path

class SimulationBridge(Node):
    def __init__(self):
        super().__init__('simulation_bridge')
        self.receiver_url = "http://localhost:5000/frame"
        self.frame_id = 0
        
        # Path to real images for simulation matching
        self.pkg_dir = Path(__file__).resolve().parent
        self.fallback_base = self.pkg_dir / "dataset" / "fallback_dataset"
        
        # Check global dir, then wp_0000, then Case 2: fallback_dataset/A/images
        if (self.fallback_base / "images").exists():
            self.images_dir = self.fallback_base / "images"
        elif (self.fallback_base / "wp_0000" / "images").exists():
            self.images_dir = self.fallback_base / "wp_0000" / "images"
        elif (self.fallback_base / "A" / "images").exists():
            self.images_dir = self.fallback_base / "A" / "images"
        else:
            self.images_dir = self.fallback_base / "images" # Fallback to non-existent for now

        self.create_subscription(NavSatFix, '/drone/gps', self._gps_cb, 10)
        self.get_logger().info(f"🌉 Bridge Active: ROS2 /drone/gps -> {self.receiver_url}")
        self.get_logger().info(f"📸 Images source: {self.images_dir}")

    def _get_closest_image_b64(self, lat, lon):
        """Pick the image closest to current (lat, lon) in the dataset."""
        try:
            if not self.images_dir.exists():
                return ""

            imgs = list(self.images_dir.glob("*.jpg"))
            if not imgs:
                return ""

            # Extract lat/lon from filenames (format: ID_z18_lat_lon.jpg)
            best_img = None
            min_dist = float('inf')

            for img_path in imgs:
                parts = img_path.name.split('_')
                if len(parts) >= 4:
                    try:
                        # parts[0]=ID, parts[1]=z18, parts[2]=lat, parts[3]=lon.jpg
                        i_lat = float(parts[2])
                        i_lon = float(parts[3].replace('.jpg', ''))
                        dist = (i_lat - lat)**2 + (i_lon - lon)**2
                        if dist < min_dist:
                            min_dist = dist
                            best_img = img_path
                    except ValueError:
                        continue

            if not best_img:
                best_img = random.choice(imgs)

            with open(best_img, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            self.get_logger().error(f"Error picking image: {e}")
            return ""

    def _gps_cb(self, msg):
        self.frame_id += 1
        gps_valid = (msg.status.status != NavSatStatus.STATUS_NO_FIX)
        
        payload = {
            "metadata": {
                "frame_id": self.frame_id,
                "gps_valid": gps_valid,
                "lat": msg.latitude if gps_valid else 0.0,
                "lon": msg.longitude if gps_valid else 0.0,
                "altitude_m": int(msg.altitude),
                "heading_deg": 0.0,
                "speed_mps": 0.0
            },
            "image_b64": self._get_closest_image_b64(msg.latitude, msg.longitude) if not gps_valid else ""
        }

        try:
            requests.post(self.receiver_url, json=payload, timeout=0.5)
            # self.get_logger().info(f"📤 Sent Frame {self.frame_id} (GPS {'OK' if gps_valid else 'LOST'})")
        except Exception as e:
            self.get_logger().error(f"❌ Failed to send frame: {e}")

def main():
    rclpy.init()
    node = SimulationBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
