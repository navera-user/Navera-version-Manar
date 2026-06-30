#!/usr/bin/env python3
"""
reactive_simulator.py
══════════════════════
A smarter simulator that:
  1. Replays a CSV mission.
  2. Detects GPS loss (NaN) and sends STATUS_NO_FIX.
  3. LISTENS to /vision/predicted_gps.
  4. RESUMES the mission from the predicted position instead of staying at NaN.
"""

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import NavSatFix, NavSatStatus
    from std_msgs.msg import Float32
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print("⚠️  rclpy not found — running in standalone mode (file-based only)")
    # Mocking Node for standalone mode
    class Node:
        def __init__(self, name): self.name = name
        def get_logger(self):
            class Logger:
                def info(self, m): print(f"[INFO] {m}")
                def warn(self, m): print(f"[WARN] {m}")
                def error(self, m): print(f"[ERROR] {m}")
            return Logger()
        def create_publisher(self, *a):
            class Pub:
                def publish(self, m): pass
            return Pub()
        def create_subscription(self, *a): pass
        def get_clock(self):
            class Clock:
                def now(self):
                    class Time:
                        def to_msg(self): return None
                    return Time()
            return Clock()

import csv
import math
import time
import threading
from io import StringIO

# ── Mission Logic ────────────────────────────────────────────────────────────
class ReactiveSimulator(Node):
    def __init__(self, csv_data: str, delay: float = 1.7):
        super().__init__('reactive_simulator')
        self.delay = delay
        self.frames = self._parse_csv(csv_data)
        self.current_idx = 0
        self.is_lost = False
        self.resumed = False

        # State for navigation
        self.curr_lat = None
        self.curr_lon = None
        self.curr_alt = 400.0
        self.target_lat = 35.7900    # Point B from user
        self.target_lon = 10.6100

        # Memory Chain config
        self.mission_mode = 'known'
        self.t_safe = 10.0
        self.step_idx = 0
        self.last_anchor_lat = None
        self.last_anchor_lon = None
        self.radius_r = 300.0
        self.expansion_triggered = False

        self.speed_m_per_tick = 75.0 # Steps of 75m during recovery

        # Publishers
        self.gps_pub = self.create_publisher(NavSatFix, '/drone/gps', 10)
        self.alt_pub = self.create_publisher(Float32,   '/drone/altitude', 10)

        # Subscriber to Visual Localization
        self.create_subscription(NavSatFix, '/vision/predicted_gps', self._predicted_gps_cb, 10)

        # Try to load target from mission_config if exists
        self._load_mission_config()

        self.get_logger().info(f'🚀 Reactive Simulator Ready — {len(self.frames)} frames')
        self.get_logger().info(f'📡 Subscribed to /vision/predicted_gps for resumption')

        # Main Simulation Loop (Threaded to not block callbacks)
        self.sim_thread = threading.Thread(target=self._run_simulation, daemon=True)
        self.sim_thread.start()

    def _publish_current_state(self, sim_status):
        """Helper to publish current lat/lon/alt."""
        if not ROS2_AVAILABLE: return

        # Altitude
        alt_msg = Float32(); alt_msg.data = float(self.curr_alt)
        self.alt_pub.publish(alt_msg)

        # GPS
        gps_msg = NavSatFix()
        gps_msg.header.stamp = self.get_clock().now().to_msg()
        gps_msg.header.frame_id = 'simulator'
        gps_msg.latitude = self.curr_lat if self.curr_lat else 0.0
        gps_msg.longitude = self.curr_lon if self.curr_lon else 0.0
        gps_msg.altitude = self.curr_alt
        gps_msg.status.status = sim_status
        self.gps_pub.publish(gps_msg)

    def _signal_mission_finished(self):
        """Writes a flag to let the receiver/UI know we arrived."""
        try:
            from pathlib import Path
            pkg_dir = Path(__file__).resolve().parent
            flag = pkg_dir / "dataset" / ".mission_finished"
            flag.write_text(str(time.time()))
        except: pass

    def _parse_csv(self, data: str) -> list:
        frames = []
        reader = csv.DictReader(StringIO(data))
        for row in reader:
            frames.append({
                'frame'  : int(row['frame']),
                'lat'    : row['lat'].strip(),
                'lon'    : row['lon'].strip(),
                'alt_m'  : float(row['alt_m']),
                'heading': float(row.get('heading_deg', 0)),
                'ts'     : row.get('timestamp', '').strip()
            })
        return frames

    def _load_mission_config(self):
        """Loads Point B from mission_config if available; otherwise uses last valid point of mission CSV."""
        try:
            from pathlib import Path
            import json
            # Search for mission_config.json in likely locations
            possible_paths = [
                Path(__file__).resolve().parent / "dataset" / "mission_config.json",
                Path(__file__).resolve().parent.parent.parent / "vision_pkg" / "vision_pkg" / "dataset" / "mission_config.json",
                Path("/app/ros2_ws/src/vision_pkg/vision_pkg/dataset/mission_config.json")
            ]

            config_path = None
            for p in possible_paths:
                if p.exists():
                    config_path = p
                    break

            if config_path:
                with open(config_path, 'r') as f:
                    cfg = json.load(f)

                    # Mode detection
                    if "config" in cfg and "missionMode" in cfg["config"]:
                        self.mission_mode = 'known' if cfg["config"]["missionMode"] == 'ab' else 'unknown'
                        self.t_safe = float(cfg["config"].get("tSafe", 10.0))
                        if "radius_r" in cfg["config"]:
                            self.radius_r = float(cfg["config"]["radius_r"])
                        if "altitude" in cfg["config"]:
                            self.curr_alt = float(cfg["config"]["altitude"])
                        self.get_logger().info(f"📋 Mission Mode: {self.mission_mode} (T_safe: {self.t_safe}s, R: {self.radius_r:.1f}m, Alt: {self.curr_alt:.1f}m)")

                    # Use last waypoint from planner if available
                    if "point_b" in cfg:
                        self.target_lat = cfg["point_b"]["lat"]
                        self.target_lon = cfg["point_b"]["lon"]
                        self.get_logger().info(f"📍 Target set from point_b: ({self.target_lat:.6f}, {self.target_lon:.6f})")
                        return
                    elif "waypoints" in cfg and len(cfg["waypoints"]) > 0:
                        self.target_lat = cfg["waypoints"][-1]["lat"]
                        self.target_lon = cfg["waypoints"][-1]["lon"]
                        self.get_logger().info(f"📍 Target set from waypoints: ({self.target_lat:.6f}, {self.target_lon:.6f})")
                        return

            # Fallback to last valid frame in the mission
            for frame in reversed(self.frames):
                if frame['lat'].lower() != 'nan' and frame['lat'] != '':
                    self.target_lat = float(frame['lat'])
                    self.target_lon = float(frame['lon'])
                    self.get_logger().info(f"📍 Target set from mission: ({self.target_lat:.6f}, {self.target_lon:.6f})")
                    return
        except Exception as e:
            self.get_logger().warn(f"⚠️ Could not load mission config: {e}")

    def _predicted_gps_cb(self, msg):
        """Triggered when vision_node finds a match."""
        self.get_logger().info(f'🟢 MATCH RECEIVED! Recovered position: ({msg.latitude:.6f}, {msg.longitude:.6f})')
        
        # Update current position to the predicted one
        self.curr_lat = msg.latitude
        self.curr_lon = msg.longitude
        
        # Calculate distance to target (Point B)
        dist = self._haversine(self.curr_lat, self.curr_lon, self.target_lat, self.target_lon)
        self.get_logger().info(f'🎯 Distance to target: {dist:.1f}m')

        if dist < 150.0:
            self.get_logger().info('🏁 REACHED Point B! Mission accomplished.')
            self.current_idx = len(self.frames) # Stop simulation
            self.is_lost = False
            self.resumed = False
            self._signal_mission_finished()
            # Also update current state so UI sees arrival
            self._publish_current_state(NavSatStatus.STATUS_FIX)
        else:
            self.get_logger().info(f'🚀 Moving 75m towards Point B...')
            new_lat, new_lon = self._move_towards(self.curr_lat, self.curr_lon, self.target_lat, self.target_lon, 75.0)
            self.curr_lat = new_lat
            self.curr_lon = new_lon

            self.is_lost = False # Reset so _run_simulation can set it again if needed
            self.resumed = True

            # Trigger immediate publication of the NEW position (still NO_FIX)
            # to keep the vision loop spinning
            self._publish_current_state(NavSatStatus.STATUS_NO_FIX)

            # Check for memory chain expansion AFTER moving
            if self.mission_mode == 'unknown':
                self._check_memory_chain_expansion()

    def _check_memory_chain_expansion(self):
        """Dynamic Re-Collection Logic (Memory Chain)"""
        if self.last_anchor_lat is None:
            self.last_anchor_lat = self.curr_lat
            self.last_anchor_lon = self.curr_lon
            # Initial R calculation: R = max(footprint × 3, altitude × 2)
            res = 0.24 # Assuming z17 for pre-vol, can be 0.12 if z18
            # The user said R = max(footprint × 3, altitude × 2)
            # footprint = alt * res * 640 / 1000
            footprint = self.curr_alt * 0.24 * 640 / 1000
            self.radius_r = max(footprint * 3, self.curr_alt * 2)
            self.get_logger().info(f"⚓ Initial anchor set. R={self.radius_r:.1f}m")
            return

        # R1 = R - 50m
        r1 = self.radius_r - 50.0

        dist_from_anchor = self._haversine(self.curr_lat, self.curr_lon, self.last_anchor_lat, self.last_anchor_lon)
        self.get_logger().info(f"📏 Dist from anchor: {dist_from_anchor:.1f}m (R1: {r1:.1f}m)")

        if dist_from_anchor > r1 and not self.expansion_triggered:
            self.expansion_triggered = True
            self.step_idx += 1
            self.get_logger().warn(f"🚨 BOUNDARY R1 REACHED! Triggering expansion A{self.step_idx}")

            # 2. Select new point An ahead using HEADING
            # Project new point A_n at distance R
            hdg_rad = math.radians(self.curr_heading)
            r_earth = 6371000.0

            d_lat = (self.radius_r * math.cos(hdg_rad)) / r_earth * (180.0 / math.pi)
            d_lon = (self.radius_r * math.sin(hdg_rad)) / (r_earth * math.cos(math.radians(self.curr_lat))) * (180.0 / math.pi)

            an_lat = self.curr_lat + d_lat
            an_lon = self.curr_lon + d_lon

            self.get_logger().info(f"📍 Projecting An ahead: hdg={self.curr_heading}° dist={self.radius_r}m -> ({an_lat:.6f}, {an_lon:.6f})")

            # 3. Trigger API call to server.py
            self._trigger_expansion_api(an_lat, an_lon, self.step_idx)

            # Update anchor for next check
            self.last_anchor_lat = an_lat
            self.last_anchor_lon = an_lon

            # Reset flag after some time (e.g. 5 seconds or based on speed) to allow next expansion
            threading.Timer(5.0, self._reset_expansion_flag).start()

    def _reset_expansion_flag(self):
        self.expansion_triggered = False

    def _trigger_expansion_api(self, lat, lon, idx):
        import requests
        url = "http://localhost:8181/api/precollect_progressive"
        payload = {
            "lat": lat, "lon": lon,
            "alt_m": int(self.curr_alt),
            "radius_m": self.radius_r,
            "step_idx": idx
        }
        try:
            requests.post(url, json=payload, timeout=2.0)
            self.get_logger().info(f"✅ Expansion request sent for A{idx}")
        except Exception as e:
            self.get_logger().error(f"❌ Failed to trigger expansion: {e}")

    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _move_towards(self, lat1, lon1, lat2, lon2, distance):
        total_dist = self._haversine(lat1, lon1, lat2, lon2)
        if total_dist <= distance or total_dist == 0:
            return lat2, lon2
        frac = distance / total_dist
        return lat1 + (lat2 - lat1) * frac, lon1 + (lon2 - lon1) * frac

    def _run_simulation(self):
        while rclpy.ok():
            if self.current_idx < len(self.frames):
                frame = self.frames[self.current_idx]
                frame_id = frame['frame']
                lat_str  = frame['lat']
                lon_str  = frame['lon']
                alt      = frame['alt_m']
                is_nan = (lat_str.lower() == 'nan' or lon_str.lower() == '')
            else:
                # End of CSV, but maybe we continue with vision?
                if self.resumed:
                    is_nan = True
                    lat_str = 'nan'
                    lon_str = 'nan'
                    alt = self.frames[-1]['alt_m']
                    frame_id = self.frames[-1]['frame'] + 1
                else:
                    break

            # Priority 1: Real GPS from mission CSV
            if not is_nan:
                lat = float(lat_str)
                lon = float(lon_str)
                self.curr_lat = lat
                self.curr_lon = lon
                self.curr_alt = float(alt)
                self.curr_heading = float(frame['heading'])
                self.resumed = False # Back to mission track
                sim_status = NavSatStatus.STATUS_FIX
                self.get_logger().info(f'📍 Frame {frame_id:>2} | GPS OK | {lat:.6f}, {lon:.6f}')
                self.current_idx += 1

            # Priority 2: Vision Recovery Mode
            elif self.resumed:
                # Use current internal state
                lat = self.curr_lat
                lon = self.curr_lon
                sim_status = NavSatStatus.STATUS_NO_FIX
                self.get_logger().info(f'🚁 NAVIGATING (Vision) | {lat:.6f}, {lon:.6f} | Target: B')

                # Consume NaN frames if they exist in CSV
                if is_nan:
                    self.current_idx += 1

            # Priority 3: Lost and waiting
            else:
                if self.curr_lat is None:
                    # Try to get from last valid frame
                    for f in reversed(self.frames[:self.current_idx]):
                        if f['lat'].lower() != 'nan' and f['lat'] != '':
                            self.curr_lat = float(f['lat'])
                            self.curr_lon = float(f['lon'])
                            break

                lat = self.curr_lat if self.curr_lat else 0.0
                lon = self.curr_lon if self.curr_lon else 0.0
                sim_status = NavSatStatus.STATUS_NO_FIX
                self.is_lost = True
                self.get_logger().warn(f'❌ Frame {frame_id:>2} | GPS LOST | (Waiting for Vision...)')
                # Stay on this NaN frame until a prediction arrives

            self._publish_current_state(sim_status)
            
            # Wait for next frame
            time.sleep(self.delay)

            # Check if we reached Point B while in vision mode
            if self.resumed and self._haversine(self.curr_lat, self.curr_lon, self.target_lat, self.target_lon) < 50.0:
                 self.get_logger().info('🏁 REACHED Point B! Ending simulation.')
                 break

        self.get_logger().info('🏁 Simulation Ended.')

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    # Built-in mission with 18 valid + fallback
    FLIGHT_CSV = """frame,lat,lon,alt_m,heading_deg,timestamp
1,35.825400,10.636000,600,296,2026-03-02T12:19:35.951Z
2,35.826503,10.633243,545,296,2026-03-02T12:19:37.674Z
3,35.827691,10.631454,500,52,2026-03-02T12:19:39.393Z
4,35.829280,10.633811,492,42,2026-03-02T12:19:41.150Z
5,NaN,NaN,454,337,2026-03-02T12:19:42.872Z
6,NaN,NaN,479,337,2026-03-02T12:19:44.605Z
7,NaN,NaN,502,302,2026-03-02T12:19:46.340Z
8,35.836977,10.630047,521,302,2026-03-02T12:19:48.087Z
9,35.838285,10.627429,540,302,2026-03-02T12:19:49.812Z
10,35.839692,10.624893,564,308,2026-03-02T12:19:51.537Z
"""
    if ROS2_AVAILABLE:
        rclpy.init()

    node = ReactiveSimulator(csv_data=FLIGHT_CSV, delay=2.0)

    if ROS2_AVAILABLE:
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        finally:
            node.destroy_node()
            rclpy.shutdown()
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    main()
