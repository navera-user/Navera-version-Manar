#!/usr/bin/env python3
"""spoof_real.py — attack NAVERA's REAL arbiter with a scripted fake GPS, and read what it says.

    python3 spoof_real.py jump        # ~25 s: GPS jumps 2 km, vision of unknown accuracy
    python3 spoof_real.py drift       # ~45 s: GPS pulled away at 6 m/s, vision states 15 m
    python3 spoof_real.py jamspoof    # ~45 s: GPS jammed 20 s, back 2 km off, then true

It starts the real estimator_node from YOUR copy (~/navera, product settings file, the
vehicle's top speed given below), publishes GPS on /navera/estimate/gps and a day-vision
estimate on /navera/estimate/day (PositionEstimate, lesson 12), and prints every CHANGE of
/navera/nav_status (state, active source, reason). It saves:
    real_<scenario>.txt               the status changes (the check reads it)
    real_<scenario>_estimator.log     what the estimator itself logged (its ERROR / WARN lines)
You don't need to change this file.
"""
import math
import os
import re
import signal
import subprocess
import sys
import time

LAT0, LON0 = 35.8256, 10.6385          # Sousse
M_LAT = 111_195.0
M_LON = M_LAT * math.cos(math.radians(LAT0))
SPEED = 15.0                            # the vehicle flies east at 15 m/s


def truth(t):
    return SPEED * t, 0.0


# For each scenario: duration, the vehicle's top speed given to the arbiter, vision sigma,
# and the GPS (None = jammed: the receiver says "no fix") as a function of time.
SCENARIOS = {
    "jump": dict(end=24.0, max_speed=30.0, vision_sigma=None,
                 gps=lambda t: (0.0, 2000.0) if 8.0 <= t < 16.0 else (0.0, 0.0),
                 story="GPS good 0-8 s, a spoofer moves it 2 km north 8-16 s, true again 16-24 s. "
                       "Vision of UNKNOWN accuracy (only the kinematic gate can act)."),
    "drift": dict(end=44.0, max_speed=30.0, vision_sigma=15.0,
                  gps=lambda t: (0.0, 6.0 * (t - 4.0)) if 4.0 <= t < 34.0 else (0.0, 0.0),
                  story="GPS pulled north at 6 m/s from 4 s to 34 s (never a jump), true again "
                        "34-44 s. Vision states 15 m (the simulator's target accuracy, not a measured one)."),
    "jamspoof": dict(end=44.0, max_speed=100.0, vision_sigma=15.0,
                     gps=lambda t: None if 6.0 <= t < 26.0 else (0.0, 2000.0) if t < 36.0 and t >= 6.0
                     else (0.0, 0.0),
                     story="GPS good 0-6 s, jammed 6-26 s, back 2 km off (spoofed) 26-36 s, true 36-44 s. "
                           "Top speed 100 m/s: after 20 s of outage, 2 km is 'reachable'. Vision states 15 m."),
}
SRC = {0: "-", 1: "GPS", 2: "day", 3: "night", 4: "cn"}
STATE = {0: "INITIALIZING", 1: "NO_FIX", 2: "FIX", 3: "DEGRADED"}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in SCENARIOS:
        sys.exit("usage: python3 spoof_real.py jump|drift|jamspoof")
    sc = SCENARIOS[name]
    import rclpy
    from ament_index_python.packages import get_package_share_directory
    from navera_msgs.msg import NavStatus, PositionEstimate

    params = os.path.join(get_package_share_directory("navera_estimator"), "config", "estimator_params.yaml")
    logf = open(f"real_{name}_estimator.log", "w")
    proc = subprocess.Popen(["ros2", "run", "navera_estimator", "estimator_node.py", "--ros-args",
                             "--params-file", params, "-p", f"max_speed_mps:={sc['max_speed']}"],
                            stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    node = rclpy.create_node("academy_spoofer")
    pub_gps = node.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
    pub_day = node.create_publisher(PositionEstimate, "/navera/estimate/day", 10)
    status = []
    node.create_subscription(NavStatus, "/navera/nav_status", status.append, 10)

    def est(src, x, y, sigma, valid=True):
        m = PositionEstimate()
        m.header.stamp = node.get_clock().now().to_msg()
        m.sensor_stamp = m.header.stamp
        m.header.frame_id = "academy"
        if valid:
            m.latitude, m.longitude = LAT0 + y / M_LAT, LON0 + x / M_LON
        else:
            m.latitude = m.longitude = math.nan
        m.altitude = math.nan
        if sigma is None:
            m.position_covariance = [0.0] * 9
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        else:
            v = sigma ** 2
            m.position_covariance = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4 * v]
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        m.source = src
        m.mode = PositionEstimate.MODE_MEASURED
        m.valid = valid
        m.producer = "academy_spoofer"
        m.frame_index = -1
        return m

    lines = []
    try:
        end = time.time() + 30
        while not status and time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.2)
        if not status:
            sys.exit("the real estimator did not start within 30 s")
        print(f"real arbiter up (max_speed_mps {sc['max_speed']:.0f}). Scenario '{name}': {sc['story']}\n")
        t0 = time.time()
        next_gps, next_day, last = 0.0, 0.0, None
        while True:
            t = time.time() - t0
            if t > sc["end"]:
                break
            x, y = truth(t)
            if t >= next_day:                         # vision: 1 fix per second, at the truth
                pub_day.publish(est(PositionEstimate.SOURCE_DAY_VISION, x + 3.0 * math.sin(t), y + 3.0 * math.cos(t),
                                    sc["vision_sigma"]))
                next_day += 1.0
                time.sleep(0.01)
            if t >= next_gps:                         # GPS: 2 fixes per second
                g = sc["gps"](t)
                if g is None:
                    pub_gps.publish(est(PositionEstimate.SOURCE_GPS, 0, 0, None, valid=False))
                else:
                    pub_gps.publish(est(PositionEstimate.SOURCE_GPS, x + g[0], y + g[1], 3.0))
                next_gps += 0.5
            rclpy.spin_once(node, timeout_sec=0.02)
            if status:
                s = status[-1]
                key = (s.state, s.active_source, re.sub(r"[0-9.]+", "#", s.reason))
                if key != last:
                    g = sc["gps"](t)
                    gtxt = "jammed" if g is None else f"{math.hypot(*g):5.0f} m off"
                    line = (f"t={t:5.1f} s  GPS {gtxt:>10s} | {STATE.get(s.state, s.state):8s} "
                            f"{SRC.get(s.active_source, '?'):4s} {s.reason}")
                    print(line)
                    lines.append(line)
                    last = key
    finally:
        try:
            os.killpg(proc.pid, signal.SIGINT)
            proc.wait(timeout=8)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
        logf.close()
        node.destroy_node()
        rclpy.try_shutdown()
    with open(f"real_{name}.txt", "w") as f:
        f.write(f"# scenario {name}: {sc['story']}\n" + "\n".join(lines) + "\n")
    print(f"\nsaved real_{name}.txt — and the estimator's own log: real_{name}_estimator.log")
    print("its ERROR / WARN lines:")
    with open(f"real_{name}_estimator.log") as f:
        for ln in f:
            if "[ERROR]" in ln or "[WARN]" in ln:
                print("  " + re.sub(r"^\[(\w+)\] \[[0-9.]+\] \[estimator_node\]: ", r"[\1] ", ln.rstrip()))


if __name__ == "__main__":
    main()
