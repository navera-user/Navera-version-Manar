#!/usr/bin/env python3
"""Live star camera, end to end (not part of run_tests.sh: astrometry.net takes 10 s to
several minutes per frame). Usage, from the workspace root, after sourcing the install:

    python3 navera_tools/tests/star_camera_e2e.py [work_dir]

The real sky is drawn NOW (navera_tools/sim/sky_view.py, Yale Bright Star catalogue) at a
place where it is night at this moment, with the camera 70 deg up facing north. A GStreamer
source feeds that picture to the real live_camera (star settings NAVERA_STAR_CAMERA_*), the
real cn_pipeline solves it with the IMU attitude at the exposure (published level, facing
north), the clock and a GPS prior 50 km off. Pass: a position within 100 km (celestial
navigation is a coarse fallback: ~111 km per degree of attitude error). Exit code 0 = pass.
"""
import json, math, os, signal, subprocess, sys, threading, time
from datetime import datetime, timezone
import cv2, rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, String
from navera_msgs.msg import PositionEstimate
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
from sky_view import SkyCamera

W = sys.argv[1] if len(sys.argv) > 1 else "/tmp/navera_star_e2e"
os.makedirs(W, exist_ok=True)
now = datetime.now(timezone.utc)
utc = now.strftime("%Y-%m-%d %H:%M:%S")
# local solar midnight: the sub-solar longitude is 15 x (12 - UTC hours), midnight 180 deg away
LAT, EL = 35.0, 70.0                          # camera 70 deg up, facing north
LON = round((-15.0 * (now.hour + now.minute / 60.0) + 180.0) % 360.0 - 180.0, 1)
print(f"night place: {LAT}, {LON}")
sky = SkyCamera(os.path.expanduser("~/.navera_sim"), hfov_deg=60.0)
print("sun altitude", round(sky.sun_altitude(LAT, LON, utc), 1))
img, n, _ = sky.render(LAT, LON, utc, EL, 0.0, roll_deg=0.0)
cv2.imwrite(f"{W}/sky.png", img)
print("stars drawn", n, "utc", utc)
env = dict(os.environ, NAVERA_STAR_CAMERA_INPUT="gst",
           NAVERA_STAR_CAMERA_GST_PIPELINE=f"filesrc location={W}/sky.png ! pngdec ! imagefreeze ! videoconvert ! "
           "video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false",
           NAVERA_STAR_CAMERA_SIZE=f"{img.shape[1]}x{img.shape[0]}", NAVERA_STAR_CAMERA_HFOV_DEG="60",
           NAVERA_STAR_CAMERA_FPS="0.2", NAVERA_STAR_CAMERA_ELEVATION_DEG=str(EL), NAVERA_STAR_CAMERA_AZIMUTH_DEG="0",
           NAVERA_SENSOR_SOURCE="box")
log = open(f"{W}/cn.log", "w")
proc = subprocess.Popen(["ros2", "launch", "simulation_web", "cn_pipeline.launch.py"], env=env,
                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
rclpy.init(); node = rclpy.create_node("star_e2e")
pub_imu = node.create_publisher(Imu, "/navera/sensors/imu", 50)
pub_gps = node.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
node.create_publisher(Bool, "/celestial/start", latched).publish(Bool(data=True))
res = []
node.create_subscription(String, "/cn/cn_status", lambda m: res.append(json.loads(m.data)), 10)
ex = SingleThreadedExecutor(); ex.add_node(node); threading.Thread(target=ex.spin, daemon=True).start()
yaw = math.radians(90.0)                    # body x (forward) towards north, level
def feed():
    k = 0
    while run[0]:
        m = Imu(); m.header.stamp = node.get_clock().now().to_msg()
        m.orientation.z, m.orientation.w = math.sin(yaw / 2) + 1e-7 * (k % 5), math.cos(yaw / 2)
        pub_imu.publish(m)
        if k % 25 == 0:
            g = PositionEstimate(); g.header.stamp = m.header.stamp
            g.latitude, g.longitude, g.valid = LAT + 0.3, LON - 0.4, True    # prior ~50 km off
            g.mode, g.source = PositionEstimate.MODE_MEASURED, PositionEstimate.SOURCE_GPS
            pub_gps.publish(g)
        k += 1; time.sleep(0.02)
run = [True]; threading.Thread(target=feed, daemon=True).start()
t0 = time.time()
try:
    while time.time() - t0 < 600 and not any(r.get("success") is not None for r in res):
        time.sleep(1)
finally:
    run[0] = False
    os.killpg(proc.pid, signal.SIGINT)
    try: proc.wait(timeout=20)
    except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL)
for r in res[:3]:
    lat, lon = r.get("lat"), r.get("lon")
    err = (2 * 6371 * math.asin(math.sqrt(math.sin(math.radians(lat - LAT) / 2) ** 2 + math.cos(math.radians(LAT)) *
           math.cos(math.radians(lat)) * math.sin(math.radians(lon - LON) / 2) ** 2)) if lat is not None else None)
    print("result: success", r.get("success"), "attitude", r.get("attitude_source"), "prior", r.get("prior_source"),
          "utc", r.get("utc_source"), "error_km", None if err is None else round(err, 1), r.get("error") or "")
ok = [r for r in res if r.get("success") and r.get("lat") is not None]
err_km = min((2 * 6371 * math.asin(math.sqrt(math.sin(math.radians(r["lat"] - LAT) / 2) ** 2 + math.cos(math.radians(LAT))
             * math.cos(math.radians(r["lat"])) * math.sin(math.radians(r["lon"] - LON) / 2) ** 2)) for r in ok), default=None)
passed = err_km is not None and err_km < 100.0 and ok[0].get("attitude_source") == "imu (at exposure)"
print("star_camera_e2e:", "PASS" if passed else "FAIL", f"(error {err_km:.1f} km)" if err_km is not None else "(no position)")
sys.exit(0 if passed else 1)
