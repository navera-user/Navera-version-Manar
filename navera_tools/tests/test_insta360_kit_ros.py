#!/usr/bin/env python3
"""The Insta360 kit through ROS, as the boot services wire it: insta360_node (replaying a synthetic
raw recording of a flight: the camera's packets and timing, navera_tools/sim/insta360_raw_sim.py)
-> /navera/sensors/insta360/imu + nadir view -> live_camera (input insta360, attitude from the kit's
IMU topic) -> /day/frame_meta. Every frame must carry the kit's attitude, straightened and usable
(before this change: "no attitude at the frame's exposure"). Exit code 0 = pass.

    python3 navera_tools/tests/test_insta360_kit_ros.py [--rec REC_DIR]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
AREA = os.path.expanduser("~/.navera_sim/bench_2026-10-06/area")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", default="", help="a recording made by insta360_raw_sim.py (default: make an 8 s one)")
    ap.add_argument("--seconds", type=float, default=25.0)
    a = ap.parse_args()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "camera_pkg"),
                                                       os.path.join(ROOT, "navera_common"),
                                                       os.environ.get("PYTHONPATH", "")]))
    env.setdefault("ROS_DOMAIN_ID", "79")
    env["ROS_LOCALHOST_ONLY"] = "1"
    env["NAVERA_STATE_DIR"] = tempfile.mkdtemp(prefix="navera_kit_state_")
    rec = a.rec
    if not rec:
        if not os.path.isdir(AREA):
            print(f"SKIP: no map tiles at {AREA} to draw the synthetic flight from")
            return 0
        rec = tempfile.mkdtemp(prefix="insta360_kit_rec_")
        subprocess.run([sys.executable, os.path.join(ROOT, "navera_tools/sim/insta360_raw_sim.py"), "--area", AREA,
                        "--lat", "35.8180", "--lon", "10.6120", "--seconds", "10", "--agl", "400",
                        "--out", rec], check=True, env=env)
    node = [sys.executable, "-m", "camera_pkg.nodes.insta360_node", "--ros-args",
            "-p", "source:=replay", "-p", f"replay_path:={os.path.join(rec, 'raw')}", "-p", "replay_rate:=1.0",
            "-p", "calibration_file:=/nonexistent", "-p", "exit_at_end:=false"]
    cam = [sys.executable, "-m", "camera_pkg.nodes.live_camera", "--ros-args", "-r", "__ns:=/day",
           "-p", "input:=insta360", "-p", "input_topic:=/navera/sensors/insta360/nadir/image_raw",
           "-p", "width:=1200", "-p", "height:=900", "-p", "camera_hfov_deg:=100.0",
           "-p", "imu_topic:=/navera/sensors/insta360/imu", "-p", "attitude_source:=insta360",
           "-p", "wait_for_ready:=false", "-p", "ack_timeout_s:=0.5", "-p", "fps:=1.0",
           "-p", "ground_altitude_m:=0.0"]
    procs = [subprocess.Popen(c, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) for c in (node, cam)]
    metas, imus = [], []
    try:
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Imu
        from std_msgs.msg import String
        os.environ.update(ROS_DOMAIN_ID=env["ROS_DOMAIN_ID"], ROS_LOCALHOST_ONLY="1")
        rclpy.init()
        n = rclpy.create_node("kit_check")
        n.create_subscription(String, "/day/frame_meta", lambda m: metas.append(json.loads(m.data)), 10)
        n.create_subscription(Imu, "/navera/sensors/insta360/imu", imus.append, qos_profile_sensor_data)
        end = time.time() + a.seconds
        while time.time() < end and len(metas) < 6:
            rclpy.spin_once(n, timeout_sec=0.1)
        n.destroy_node()
        rclpy.shutdown()
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    fails = []
    if not imus:
        fails.append("no IMU message from the kit")
    elif imus[-1].orientation_covariance[0] <= 0:
        fails.append("the kit's IMU carries no orientation")
    if len(metas) < 3:
        fails.append(f"only {len(metas)} frame(s) reached /day/frame_meta")
    for m in metas:
        if m.get("attitude_source") != "insta360" or not m.get("straightened") or not m.get("usable"):
            fails.append(f"frame {m.get('frame_id')}: attitude {m.get('attitude_source')}, straightened "
                         f"{m.get('straightened')}, usable {m.get('usable')} ({m.get('reason')})")
    for m in metas:
        print(f"frame {m.get('frame_id')}: attitude {m.get('attitude_source')} tilt {m.get('tilt_deg')} deg "
              f"roll {m.get('roll_deg')} pitch {m.get('pitch_deg')} heading {m.get('heading_deg')} "
              f"usable {m.get('usable')} altitude {m.get('altitude_m')}")
    print(f"{len(imus)} IMU messages")
    for f in fails:
        print("FAIL", f)
    print("insta360_kit_ros:", "PASS" if not fails else f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
