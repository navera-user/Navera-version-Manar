#!/usr/bin/env python3
"""Make the data of mission 02 (deterministic: the same files every time).

    python3 solutions/02-terminal/make_dataset.py           # from the academy folder

Teacher only (solutions/ is never mounted for students): it shows how the logs were made.

Writes:
  datasets/02-terminal/navera_lite_tree/   the SKELETON of NAVERA Lite, the stack the students build in
                                           missions 03-33: every folder and file of the finished stack, with
                                           names and one-line descriptions only (no code: `...` bodies),
                                           plus a deploy/ folder (systemd units), config/, and copies in
                                           build/ and install/ as a packaging tool would leave them.
                                           Students explore it read only at /data/academy/02-terminal/.
  datasets/02-terminal/examples/           the small log of the lesson's worked example
  datasets/02-terminal/evidence/           what an engineer saved from a test box whose GPS service failed
                                           (the "Permission denied" story of lab Step 4b)
  courses/02-terminal/files/inbox/         two SYNTHETIC flight logs, three SYNTHETIC camera views rendered
                                           from the OpenStreetMap map (© OpenStreetMap contributors), three cache files

The logs imitate the ROS 2 console format that NAVERA Lite's nodes write (mission 10 on):
    [LEVEL] [epoch_seconds.nanoseconds] [node_name]: message
The flights are invented for the lab; the GPS losses are simulated. Nothing here is NAVERA code or data.
"""
import datetime
import os
import random
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
DATA = os.path.join(ACADEMY, "datasets", "02-terminal")
TREE = os.path.join(DATA, "navera_lite_tree")
INBOX = os.path.join(ACADEMY, "courses", "02-terminal", "files", "inbox")


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, mode)


# =============================================================================== flight logs
def epoch(y, mo, d, h, mi, s=0):
    """Tunisian time (UTC+1 all year, no daylight saving) -> Unix seconds."""
    tz = datetime.timezone(datetime.timedelta(hours=1))
    return datetime.datetime(y, mo, d, h, mi, s, tzinfo=tz).timestamp()


class Log:
    def __init__(self, t0, seed):
        self.t0, self.rnd, self.lines = t0, random.Random(seed), []

    def add(self, t, level, node, msg):
        ts = self.t0 + t + self.rnd.randint(0, 249_999_999) * 1e-9   # sub-second jitter (< 0.25 s)
        sec = int(ts)
        ns = int(round((ts - sec) * 1e9))
        self.lines.append((ts, f"[{level}] [{sec}.{ns:09d}] [{node}]: {msg}"))

    def text(self):
        self.lines.sort(key=lambda x: x[0])
        return "".join(l + "\n" for _, l in self.lines)


ARB = "navera_lite_arbiter"


def routine(log, duration, lost, sats=(10, 13), heading=300.0):
    r = log.rnd
    log.add(0.0, "INFO", ARB, "arbiter started: priority gps > day > night > star")
    log.add(0.4, "INFO", "nmea", "serial port /dev/ttyTHS1 open at 9600 baud")
    log.add(0.6, "INFO", "imu", "IMU ready, declination 3.3 deg")
    log.add(0.8, "INFO", "camera", "camera streaming, 2 frames per second")
    log.add(1.0, "INFO", "day_vision", "map loaded, search radius 600 m")
    log.add(1.2, "INFO", "output", "MAVLink link to autopilot up")
    log.add(3.0, "INFO", ARB, "state FIX source=gps")
    for t in range(5, duration, 10):
        if not any(a <= t < b for a, b in lost):
            log.add(t, "INFO", "nmea", f"fix OK, {r.randint(*sats)} satellites, hdop {r.uniform(0.7, 1.4):.1f}")
    for t in range(30, duration, 60):
        log.add(t + 0.5, "INFO", "imu", f"attitude OK, heading {heading + r.uniform(-25, 25):.1f} deg")
    for t in range(20, duration, 30):
        log.add(t + 0.7, "INFO", "output", "GPS_INPUT sent to autopilot")


def gps_outage(log, a, b, why):
    log.add(a + 2.0, "WARN", "nmea", f"no fix for 2.0 s ({why})")
    for t in range(a + 12, b, 20):
        log.add(t, "WARN", "nmea", f"no fix for {t - a:.1f} s")
    log.add(b, "INFO", "nmea", "fix OK, 9 satellites, hdop 1.6")


def sousse():
    log = Log(epoch(2026, 9, 21, 8, 30), 2026_0921)
    r = log.rnd
    routine(log, 1260, [(300, 420), (800, 1010)], heading=315.0)
    # outage 1, over land: day vision takes over
    gps_outage(log, 300, 420, "jamming simulated")
    log.add(303.0, "WARN", ARB, "state DEGRADED source=day (gps: stale)")
    for t in range(304, 420, 2):
        if r.random() < 0.85:
            log.add(t, "INFO", "day_vision", f"match OK, {r.randint(18, 60)} inliers, sigma 30 m")
        else:
            log.add(t, "WARN", "day_vision", f"no match: {r.randint(1, 5)} inliers < 6")
    log.add(355.0, "ERROR", "camera", "frame timeout: no frame for 2.4 s")
    log.add(421.0, "INFO", ARB, "gps agrees with day vision (gap 14 m): accepted")
    log.add(423.2, "INFO", ARB, "state FIX source=gps")
    log.add(424.0, "INFO", ARB, "previous WARN cleared, gps trusted again")
    # outage 2, over the sea: nothing to match, then NO_FIX
    gps_outage(log, 800, 1010, "jamming simulated")
    log.add(803.0, "WARN", ARB, "state DEGRADED source=day (propagated)")
    for t in range(804, 1010, 4):
        log.add(t, "WARN", "day_vision", "no match: sea, nothing to recognise")
    log.add(924.0, "WARN", ARB, "state NO_FIX: no source usable (dead-reckoning limit 120 s)")
    for t in (929.0, 939.0, 949.0):
        log.add(t, "ERROR", "output", "no position for 5.0 s: autopilot uses its own failsafe")
    log.add(960.0, "INFO", "day_vision", "match OK, 22 inliers, sigma 30 m")
    log.add(960.4, "WARN", ARB, "state DEGRADED source=day (gps: stale)")
    log.add(975.0, "WARN", ARB, "state NO_FIX: no source usable (day: stale)")
    log.add(984.0, "ERROR", "camera", "frame timeout: no frame for 3.1 s")
    log.add(1011.0, "INFO", ARB, "gps returned after 211 s, no independent source: accepted (reachable)")
    log.add(1013.1, "INFO", ARB, "state FIX source=gps")
    log.add(1255.0, "INFO", ARB, "shutdown requested (SIGINT)")
    return log


def inland_range():
    log = Log(epoch(2026, 9, 22, 16, 5), 2026_0922)
    r = log.rnd
    routine(log, 980, [(610, 700)], sats=(7, 11), heading=40.0)
    # spoofing test: a jump of 2.4 km is refused by the jump gate
    log.add(450.0, "WARN", "nmea", "fix jump 2412 m in 1.0 s")
    log.add(450.1, "WARN", ARB, "gps refused: jump 2412 m > reachable 150 m")
    log.add(450.2, "WARN", ARB, "state DEGRADED source=day (gps in doubt)")
    for t in range(452, 520, 2):
        if r.random() < 0.9:
            log.add(t, "INFO", "day_vision", f"match OK, {r.randint(15, 48)} inliers, sigma 30 m")
        else:
            log.add(t, "WARN", "day_vision", "no match: scale check failed")
    log.add(520.0, "INFO", ARB, "gps agrees with day vision (gap 21 m): accepted")
    log.add(522.1, "INFO", ARB, "state FIX source=gps")
    log.add(580.0, "ERROR", "imu", "no sample for 0.6 s (I2C bus busy)")
    # an outage in a dry valley between ridges (sky partly hidden)
    gps_outage(log, 610, 700, "few satellites in view")
    log.add(613.0, "WARN", ARB, "state DEGRADED source=day (gps: stale)")
    for t in range(614, 700, 2):
        if t < 650 or t > 672:
            log.add(t, "INFO", "day_vision", f"match OK, {r.randint(12, 40)} inliers, sigma 30 m")
        else:
            log.add(t, "WARN", "day_vision", "no match: frame too dark (shadow of the ridge)")
    log.add(668.0, "WARN", ARB, "state NO_FIX: no source usable (day: stale)")
    log.add(669.0, "ERROR", "output", "no position for 5.0 s: autopilot uses its own failsafe")
    log.add(674.0, "WARN", ARB, "state DEGRADED source=day (gps: stale)")
    log.add(701.0, "INFO", ARB, "gps agrees with day vision (gap 9 m): accepted")
    log.add(703.2, "INFO", ARB, "state FIX source=gps")
    log.add(975.0, "INFO", ARB, "shutdown requested (SIGINT)")
    return log


def bench_example():
    """The lesson's worked example: a short bench test of a harbour boat's box (not a lab log)."""
    log = Log(epoch(2026, 9, 30, 10, 0), 2026_0930)
    log.add(0.0, "INFO", ARB, "arbiter started: priority gps > day > night > star")
    log.add(0.5, "INFO", "nmea", "serial port /dev/ttyUSB0 open at 38400 baud")
    log.add(1.0, "INFO", "camera", "camera streaming, 2 frames per second")
    log.add(2.0, "INFO", ARB, "state FIX source=gps")
    plan = [(10, "WARN", "nmea", "no fix for 2.0 s (antenna cable loose)"),
            (11, "WARN", ARB, "state DEGRADED source=day (gps: stale)"),
            (12, "WARN", "camera", "exposure too long: 40 ms"),
            (20, "WARN", "nmea", "no fix for 12.0 s"),
            (25, "INFO", "day_vision", "match OK, 31 inliers, sigma 30 m"),
            (30, "WARN", "nmea", "no fix for 22.0 s"),
            (31, "ERROR", "nmea", "serial port /dev/ttyUSB0 closed by the device"),
            (32, "WARN", "camera", "exposure too long: 45 ms"),
            (40, "WARN", "nmea", "no fix for 32.0 s"),
            (41, "INFO", "nmea", "serial port /dev/ttyUSB0 open at 38400 baud"),
            (44, "INFO", "nmea", "fix OK, 11 satellites, hdop 0.9"),
            (45, "INFO", ARB, "state FIX source=gps"),
            (50, "INFO", ARB, "a WARN above was about the cable, not the software")]
    for t, lvl, node, msg in plan:
        log.add(t, lvl, node, msg)
    return log


# =============================================================================== camera views (synthetic)
VIEWS = [(35.8420, 10.6270, 330.0), (35.8610, 10.6080, 315.0), (35.8000, 10.5800, 40.0)]   # lat, lon, heading


def synthetic_view(i):
    """A 640x480 downward 'camera view' rendered from the course's OpenStreetMap map of Sousse
    (datasets/_map/render_view.py, pseudo-satellite style, light camera effects). SYNTHETIC: a
    drawing made from map data, not a photograph. The OSM attribution is written on the image."""
    import cv2
    sys.path.insert(0, os.path.join(ACADEMY, "datasets", "_map"))
    from render_view import render_view
    lat, lon, heading = VIEWS[i - 1]
    img = render_view(lat, lon, heading_deg=heading, alt_m=300, out_px=(640, 480), seed=200 + i,
                      style="pseudo", effects="light")
    for text, y in (("SYNTHETIC VIEW rendered from map data", 462), ("(c) OpenStreetMap contributors", 476)):
        cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


# =============================================================================== the skeleton tree
# part -> (mission, one line, [signature, short meaning])
PARTS = {
    "settings": (1, "the settings file: load and check navera_lite.yaml", [
        ("load(path='navera_lite.yaml')", "the settings as a dict (defaults + the file)"),
        ("check_settings(cfg)", "every rule the settings break, as sentences (mission 13)")]),
    "vehicle": (3, "vehicles, wind triangle, endurance", [
        ("heading_vector(heading_deg)", "unit vector (east, north) of a heading"),
        ("ground_velocity(airspeed_mps, heading_deg, wind_e=0.0, wind_n=0.0)", "velocity over the ground"),
        ("heading_for_track(track_deg, tas_mps, wind_e, wind_n)", "heading to hold a track in wind"),
        ("endurance_s(battery_wh, power_w, reserve=0.2)", "flight time on one battery")]),
    "track": (3, "a time-ordered list of positions", [
        ("load_track(path)", "read a track file")]),
    "logbook": (4, "flight-log cleaning and outages (pandas)", [
        ("clean(df)", "remove broken rows, say why"), ("outage_runs(valid)", "the runs of missing GPS"),
        ("state_shares(df)", "share of time in FIX / DEGRADED / NO_FIX")]),
    "geo": (6, "positions on the Earth: sphere, WGS84, east/north", [
        ("haversine_m(lat1, lon1, lat2, lon2)", "great-circle distance, m"),
        ("bearing_deg(lat1, lon1, lat2, lon2)", "initial bearing, degrees from north"),
        ("enu_flat(lat0, lon0, lat, lon)", "metres east and north of a reference"),
        ("offset(lat, lon, e_m, n_m)", "move a position by metres east and north")]),
    "tiles": (7, "Web Mercator map tiles and the MBTiles map", [
        ("tile_xy(lat, lon, z)", "tile coordinates of a position"), ("m_per_px(lat, z)", "map scale"),
        ("read_tile(db, z, x, y)", "one tile from the map file")]),
    "image": (8, "images as arrays: filters and warps", [
        ("to_gray(img)", "a grey image"), ("convolve2d(img, k)", "a filter"),
        ("warp_affine(img, M, size)", "rotate and scale an image")]),
    "estimate": (12, "the position contract: one estimate from one source", [
        ("is_covariance(cov9, tol=1e-09)", "is this a real covariance matrix?"),
        ("stated_sigma(est, cfg)", "the uncertainty a source states, m"),
        ("eligible(est, now_s, cfg)", "may the judge use this estimate now?")]),
    "guard": (12, "the jump gate (mission 01) and the cross-check (mission 30)", [
        ("gate_ok(last_xy, new_xy, elapsed_s, v_max_mps, margin_m)", "the jump gate of mission 01"),
        ("crosscheck(gps_est, vis_est, cfg)", "does GPS agree with an independent source?")]),
    "gnss": (15, "NMEA sentences, DOP, the GPS receiver's decision", [
        ("nmea_checksum(body)", "the checksum of a sentence"), ("parse_gga(line)", "one GGA sentence as a dict"),
        ("fix_decision(gga)", "use this fix or not, and why")]),
    "rotations": (16, "rotation matrices, Euler angles, quaternions (x, y, z, w)", [
        ("euler_zyx_to_matrix(roll, pitch, yaw)", "a rotation matrix"), ("q_mul(p, q)", "quaternion product"),
        ("slerp(q0, q1, t)", "smooth interpolation between two attitudes")]),
    "imu": (17, "gyro integration, tilt, complementary filter, compass heading", [
        ("integrate_gyro(q0, t_s, gyro_rad_s)", "attitude from the gyro"),
        ("complementary(t_s, gyro, accel, tau_s)", "gyro + accelerometer"),
        ("true_heading(mag_deg, decl_deg)", "compass heading to true heading")]),
    "camera": (18, "pinhole and fisheye camera models, timing", [
        ("K_from_hfov(hfov_deg, w, h)", "the camera matrix K"), ("gsd(h_m, hfov_deg, w_px)", "metres per pixel"),
        ("attitude_at(t, imu_t, imu_q, max_gap_s=0.2)", "the attitude when a frame was taken (mission 20)")]),
    "features": (21, "corners and features in an image", [
        ("harris(gray, k=0.04)", "the Harris corner response"), ("matchability(gray)", "is there anything to match?")]),
    "match": (22, "matching features: ratio test, RANSAC, gates", [
        ("ratio_test(knn, ratio=0.8)", "keep the clear matches"),
        ("ransac_similarity(src, dst, thr_px, iters, rng)", "a fit that ignores the outliers")]),
    "locate": (23, "a camera view to a position on the map", [
        ("locate(photo, meta, prior, cfg)", "latitude and longitude, or a reason why not"),
        ("budget(terms)", "the error budget (root of the sum of squares)")]),
    "vo": (24, "visual odometry: motion from one frame to the next", [
        ("phase_shift(a, b)", "the shift between two frames"), ("drift_sigma(n, sigma_step_m, bias_m)", "how the error grows")]),
    "night": (25, "thermal images against the map", [
        ("ncc(a, b)", "normalised cross-correlation"), ("ncc_locate(prepared, patch)", "best position of a thermal view")]),
    "stars": (26, "position from the stars", [
        ("julian_date(y, mo, d, h=0, mi=0, s=0.0)", "the astronomers' day count"),
        ("altaz(ra_deg, dec_deg, lat, lon, gst_deg)", "where a star stands in the sky"),
        ("lat_from_polaris(alt_deg, ha_deg=None)", "latitude from the Pole Star")]),
    "uncertainty": (27, "covariance, ellipses, gating, fusion", [
        ("ellipse(P, k=1.0)", "the error ellipse of a covariance"),
        ("mahalanobis2(r, S)", "squared distance in units of uncertainty"),
        ("fuse(x1, P1, x2, P2)", "two estimates into one")]),
    "kalman": (28, "the Kalman filter", [
        ("kf_predict(x, P, F, Q)", "predict"), ("kf_update(x, P, z, H, R)", "correct with a measurement")]),
    "arbiter": (29, "the judge: which source to trust, and the state", [
        ("candidates(latest, now_s, cfg)", "eligible sources in priority order"),
        ("pick(cands, current, since, now_s, cfg)", "the winner, with the hold-off"),
        ("decide(latest, now_s, mem, cfg)", "one decision: state, source, reason")]),
    "output": (31, "the messenger: a GPS_INPUT message for the autopilot", [
        ("crc_x25(data, crc=65535)", "the MAVLink checksum"), ("decode_gps_input(payload)", "read a message back")]),
    "stats": (32, "measuring: errors, percentiles, confidence intervals", [
        ("percentile(v, q)", "a percentile (linear)"), ("bootstrap_ci(x, stat, B=2000, alpha=0.05, rng=None, block=1)",
                                                       "a confidence interval by resampling")]),
}
ROS = {
    "qos": (9, "the quality-of-service profiles of the topics", [("compatible(pub, sub)", "can they talk?")]),
    "convert": (12, "an estimate to and from a sensor_msgs/NavSatFix", [
        ("to_navsatfix(est)", "estimate to message"), ("from_navsatfix(msg, source, now_s)", "message to estimate")]),
    "gps_node": (10, "fake_gps: a GPS that drives along a straight line", [("main(args=None)", "run the node")]),
    "trip_node": (11, "trip_computer: listens to the GPS, computes the trip", [("main(args=None)", "run the node")]),
    "replay_node": (11, "replay: plays recorded fixes on the topics", [("main(args=None)", "run the node")]),
    "nmea_node": (15, "nmea: reads a GPS receiver (or a file) and publishes fixes", [("main(args=None)", "run the node")]),
    "arbiter_v0": (9, "navera_lite_arbiter, version 0: the naive judge", [("main(args=None)", "run the node")]),
    "arbiter_node": (29, "navera_lite_arbiter: your arbiter of mission 29 on ROS", [("main(args=None)", "run the node")]),
    "camera_node": (20, "camera: frames from the camera (or a recording)", [("main(args=None)", "run the node")]),
    "launch_util": (13, "helpers for launch files", [
        ("fl_node(module, name, namespace='', params_file=None, params=None, remaps=None)", "one node in a launch file")]),
}
SIM = {
    "world": (31, "the simulated world (the same file as Sim Lite's)", [("step(state, dt_s)", "move the world on")]),
    "sensors": (31, "simulated sensors and their noise", [
        ("gauss_markov(n, dt=0.2, tau_s=20, q=0.6, rng=None)", "slowly wandering noise")]),
    "run": (31, "fly a scenario headless and write the results", [("main(argv=None)", "run a scenario")]),
}
TESTS = ["geo", "tiles", "estimate", "guard", "gnss", "rotations", "camera", "match", "uncertainty", "arbiter"]


def part_text(path, mission, line, funcs):
    out = [f'"""{path} — {line}.',
           "",
           f"Part of NAVERA Lite, the course's teaching stack (mission {mission:02d}). Written for the course;",
           "it is not NAVERA code.",
           "",
           f"SKELETON: this file only names what the part will hold. You write it in mission {mission:02d}.",
           '"""', ""]
    for sig, meaning in funcs:
        out += ["", f"def {sig}:", f'    """{meaning[0].upper() + meaning[1:]}."""', "    ...", ""]
    return "\n".join(out).rstrip("\n") + "\n"


def test_text(part, mission):
    return (f'"""navera_lite/tests/test_{part}.py — tests of {part}.py (pytest, mission 14).\n\n'
            f'SKELETON: the tests are written when the part is finished (mission {mission:02d} or 14)."""\n\n\n'
            f"def test_{part}_placeholder():\n    ...\n")


GPS_UNIT = """\
# navera_lite-gps.service — NAVERA Lite's GPS reader started by systemd (course example)
# Install: copy to /etc/systemd/system/, then: sudo systemctl daemon-reload
#          sudo systemctl enable --now navera_lite-gps
[Unit]
Description=NAVERA Lite GPS reader (NMEA sentences from a serial port)
PartOf=navera_lite.target

[Service]
Type=simple
# the service runs as its own user, never as root
User=navera_lite
Group=navera_lite
# site settings (ROS domain, map path, vehicle): one NAME=value per line; "-" = optional file
EnvironmentFile=-/etc/navera_lite/navera_lite.env
ExecStart=/usr/bin/python3 -m navera_lite.ros.nmea_node --ros-args --params-file /etc/navera_lite/gps.yaml
# a crashed reader is started again after 10 s
Restart=always
RestartSec=10

[Install]
WantedBy=navera_lite.target
"""


def unit(name, desc, module, extra=""):
    return (f"# navera_lite-{name}.service — {desc} (course example)\n"
            "[Unit]\n"
            f"Description=NAVERA Lite {desc}\n"
            "PartOf=navera_lite.target\n\n"
            "[Service]\n"
            "Type=simple\nUser=navera_lite\nGroup=navera_lite\n"
            f"{extra}"
            "EnvironmentFile=-/etc/navera_lite/navera_lite.env\n"
            f"ExecStart=/usr/bin/python3 -m navera_lite.ros.{module} --ros-args "
            "--params-file /etc/navera_lite/navera_lite.yaml\n"
            "Restart=always\nRestartSec=5\n\n"
            "[Install]\nWantedBy=navera_lite.target\n")


def tree():
    if os.path.isdir(TREE):
        shutil.rmtree(TREE)
    src = {}                                          # relative path -> text, for the source package
    src["navera_lite/__init__.py"] = ('"""navera_lite — NAVERA Lite, the navigation stack you build in this course.\n\n'
                                      "SKELETON: every part of the finished stack, with names only.\n"
                                      'Written for the course; it is not NAVERA code."""\n__version__ = "course-2026.1"\n')
    for p, (m, line, funcs) in PARTS.items():
        src[f"navera_lite/{p}.py"] = part_text(f"navera_lite/{p}.py", m, line, funcs)
    src["navera_lite/ros/__init__.py"] = '"""navera_lite.ros — the ROS 2 nodes of NAVERA Lite (missions 09-31)."""\n'
    for p, (m, line, funcs) in ROS.items():
        src[f"navera_lite/ros/{p}.py"] = part_text(f"navera_lite/ros/{p}.py", m, line, funcs)
    src["navera_lite/ros/navera_lite.launch.py"] = (
        '"""navera_lite/ros/navera_lite.launch.py — starts the nodes together (mission 13).\n\n'
        'SKELETON: you write this launch file in mission 13."""\n\n\ndef generate_launch_description():\n'
        '    """The nodes to start, and their settings."""\n    ...\n')
    src["navera_lite/sim/__init__.py"] = '"""navera_lite.sim — the headless simulator (mission 31)."""\n'
    for p, (m, line, funcs) in SIM.items():
        src[f"navera_lite/sim/{p}.py"] = part_text(f"navera_lite/sim/{p}.py", m, line, funcs)
    src["navera_lite/tools/__init__.py"] = '"""navera_lite.tools — command-line tools."""\n'
    src["navera_lite/tools/evaluate_bag.py"] = part_text(
        "navera_lite/tools/evaluate_bag.py", 32, "errors of every source in a recording, against the truth",
        [("main(argv=None)", "print one line per source")])
    src["navera_lite/tests/__init__.py"] = ""
    for p in TESTS:
        m = PARTS[p][0]
        src[f"navera_lite/tests/test_{p}.py"] = test_text(p, m)
    for rel, text in src.items():
        write(os.path.join(TREE, rel), text)
    write(os.path.join(TREE, "navera_lite/tools/init_repo.sh"),
          "#!/bin/bash\n# init_repo.sh — make your navera_lite/ folder a git repository (missions 14 and 33).\n"
          "# SKELETON: the real script comes with mission 14.\nset -e\necho \"not written yet\" >&2\nexit 1\n", 0o755)

    # a packaging tool (colcon, described in mission 13) leaves COPIES of the sources here:
    # never edit them, the next build overwrites them
    for rel, text in src.items():
        if rel.startswith("navera_lite/tests/"):
            continue
        write(os.path.join(TREE, "build", "navera_lite", "build", "lib", rel), text)
        write(os.path.join(TREE, "install", "navera_lite", "lib", "python3.10", "site-packages", rel), text)
    write(os.path.join(TREE, "build", "navera_lite", "colcon_build.rc"), "0\n")
    write(os.path.join(TREE, "install", "setup.bash"),
          "# generated by the packaging tool: `source install/setup.bash` adds navera_lite to the paths\n"
          "export PYTHONPATH=\"$(dirname \"${BASH_SOURCE[0]}\")/navera_lite/lib/python3.10/site-packages:$PYTHONPATH\"\n")

    with open(os.path.join(ACADEMY, "solutions", "_navera_lite", "navera_lite.yaml")) as f:
        write(os.path.join(TREE, "navera_lite.yaml"), f.read())
    write(os.path.join(TREE, "config", "gps.yaml"),
          "# gps.yaml — settings of the nmea node (the GPS reader), ROS 2 params-file format\n"
          "/**:\n  ros__parameters:\n"
          "    port: /dev/ttyTHS1       # the Jetson serial port wired to the GPS receiver\n"
          "    baud: 9600               # bits per second; must match the receiver\n"
          "    frame_id: gps\n"
          "    max_hdop: 5.0            # above this, the fix is published but marked doubtful\n")
    write(os.path.join(TREE, "navera_lite.env.example"),
          "# navera_lite.env.example — site settings of one NAVERA Lite box.\n"
          "# Copy to /etc/navera_lite/navera_lite.env and edit. One NAME=value per line, no spaces around =.\n"
          "# Every service reads this file (EnvironmentFile= in its unit) and gets these as environment variables.\n"
          "ROS_DOMAIN_ID=42\n"
          "ROS_LOCALHOST_ONLY=1\n"
          "NAVERA_LITE_MAP=/data/map.mbtiles\n"
          "NAVERA_LITE_VEHICLE=drone\n")
    write(os.path.join(TREE, "deploy", "systemd", "navera_lite-gps.service"), GPS_UNIT)
    write(os.path.join(TREE, "deploy", "systemd", "navera_lite-arbiter.service"),
          unit("arbiter", "arbiter (the judge)", "arbiter_node"))
    write(os.path.join(TREE, "deploy", "systemd", "navera_lite-camera.service"),
          unit("camera", "camera reader", "camera_node", "# /dev/video0 is root:video 0660\nSupplementaryGroups=video\n"))
    write(os.path.join(TREE, "deploy", "systemd", "navera_lite-replay.service"),
          unit("replay", "replay of a recorded flight (bench tests)", "replay_node"))
    write(os.path.join(TREE, "deploy", "systemd", "navera_lite.target"),
          "# navera_lite.target — all NAVERA Lite services: sudo systemctl start navera_lite.target\n"
          "[Unit]\nDescription=NAVERA Lite (all services)\nWants=navera_lite-gps.service "
          "navera_lite-camera.service navera_lite-arbiter.service\n\n[Install]\nWantedBy=multi-user.target\n")
    write(os.path.join(TREE, "deploy", "README.md"),
          "# deploy/ — running NAVERA Lite as services on a box\n\n"
          "Each node runs as a systemd service (a `.service` unit file in `systemd/`), as user `navera_lite`.\n"
          "The site settings come from `/etc/navera_lite/navera_lite.env` (see `../navera_lite.env.example`).\n"
          "A service that needs a device needs the device's group: see `ls -l /dev/<device>`.\n\n"
          "    sudo cp systemd/*.service systemd/*.target /etc/systemd/system/\n"
          "    sudo systemctl daemon-reload\n"
          "    sudo systemctl enable --now navera_lite.target\n"
          "    journalctl -u navera_lite-gps -f          # follow the GPS reader's messages\n")
    write(os.path.join(TREE, "README.md"),
          "# NAVERA Lite — the skeleton\n\n"
          "This is the map of the stack you build in this course, one part per mission. Every file is here\n"
          "with its name and a one-line description of what it will hold; there is no code yet (`...`).\n"
          "Names may still change a little: in each mission, your lesson folder is the reference.\n\n"
          "| Folder | What |\n|---|---|\n"
          "| `navera_lite/` | the Python package: one file per part (`geo.py` in mission 06, …) |\n"
          "| `navera_lite/ros/` | the ROS 2 nodes (missions 09–31) |\n"
          "| `navera_lite/sim/` | the headless simulator (mission 31) |\n"
          "| `navera_lite/tests/` | the tests (pytest, mission 14) |\n"
          "| `navera_lite.yaml` | the settings, a ROS 2 params file |\n"
          "| `config/` | settings of single nodes |\n"
          "| `deploy/` | how a box runs it: systemd units, site settings |\n"
          "| `build/`, `install/` | COPIES made by a packaging tool: never edit them |\n\n"
          "NAVERA's own code is IRIS's property and is not part of the course. NAVERA Lite has the same\n"
          "shape (witnesses → judge → messenger), written for the course.\n")


# =============================================================================== evidence (lab Step 4b)
EVIDENCE = {
    "README.txt":
        "Saved by the test engineer from a NAVERA Lite test box (course scenario, 2026-09-30).\n"
        "The GPS reader worked when the developer started it by hand, but not as a service.\n"
        "Files: ls_dev.txt (the serial port), id_navera_lite.txt (the service user),\n"
        "id_developer.txt (the developer), journal_gps.txt (the service's messages).\n",
    "ls_dev.txt":
        "$ ls -l /dev/ttyTHS1\n"
        "crw-rw---- 1 root dialout 238, 1 Sep 30 09:12 /dev/ttyTHS1\n",
    "id_navera_lite.txt":
        "$ id navera_lite\n"
        "uid=997(navera_lite) gid=997(navera_lite) groups=997(navera_lite)\n",
    "id_developer.txt":
        "$ id\n"
        "uid=1000(dev) gid=1000(dev) groups=1000(dev),4(adm),20(dialout),27(sudo),44(video)\n",
    "journal_gps.txt":
        "$ journalctl -u navera_lite-gps -n 8\n"
        "Sep 30 09:14:02 box python3[2211]: [INFO] [1790756042.104331207] [nmea]: starting, port /dev/ttyTHS1\n"
        "Sep 30 09:14:02 box python3[2211]: [ERROR] [1790756042.110908551] [nmea]: cannot open /dev/ttyTHS1: "
        "[Errno 13] Permission denied: '/dev/ttyTHS1'\n"
        "Sep 30 09:14:02 box systemd[1]: navera_lite-gps.service: Main process exited, code=exited, status=1/FAILURE\n"
        "Sep 30 09:14:02 box systemd[1]: navera_lite-gps.service: Failed with result 'exit-code'.\n"
        "Sep 30 09:14:12 box systemd[1]: navera_lite-gps.service: Scheduled restart job, restart counter is at 7.\n"
        "Sep 30 09:14:12 box systemd[1]: Started NAVERA Lite GPS reader (NMEA sentences from a serial port).\n"
        "Sep 30 09:14:12 box python3[2230]: [INFO] [1790756052.087713012] [nmea]: starting, port /dev/ttyTHS1\n"
        "Sep 30 09:14:12 box python3[2230]: [ERROR] [1790756052.093374209] [nmea]: cannot open /dev/ttyTHS1: "
        "[Errno 13] Permission denied: '/dev/ttyTHS1'\n",
}


DATA_README = """# Mission 02 data (read only)

- `navera_lite_tree/` — the skeleton of NAVERA Lite, the stack you build in this course (names only).
- `examples/` — the small log of the lesson's worked example (§6).
- `evidence/` — files saved from a test box whose GPS service failed (lab Step 4b).

Written for the course; nothing here is NAVERA code or data.
"""


def main():
    tree()
    for name, text in EVIDENCE.items():
        write(os.path.join(DATA, "evidence", name), text)
    write(os.path.join(DATA, "examples", "bench_2026-09-30.log"), bench_example().text())
    write(os.path.join(DATA, "README.md"), DATA_README)
    os.makedirs(INBOX, exist_ok=True)
    for name, fn in (("sousse_2026-09-21.log", sousse), ("range_2026-09-22.log", inland_range)):
        text = fn().text()
        write(os.path.join(INBOX, name), text)
        print(f"inbox/{name}: {text.count(chr(10))} lines")
    for i in (1, 2, 3):
        with open(os.path.join(INBOX, f"cam_{i:04d}.jpg"), "wb") as f:
            f.write(synthetic_view(i))
    for i in (1, 2, 3):
        write(os.path.join(INBOX, f"cache_{i:02d}.tmp"), f"temporary map cache {i}: safe to delete\n")
    n = sum(len(fs) for _, _, fs in os.walk(TREE))
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(TREE) for f in fs)
    print(f"navera_lite_tree: {n} files, {size / 1000:.0f} kB")


if __name__ == "__main__":
    sys.exit(main())
