#!/usr/bin/env python3
"""Make the two SYNTHETIC flight logs of lab 02 (deterministic: same files every time).

The logs imitate the ROS 2 console format of NAVERA's nodes:
    [LEVEL] [epoch_seconds.nanoseconds] [node_name]: message
Two training flights, invented for the lab (the GPS losses are simulated):
  sousse_2026-09-21.log  coast near Sousse (NAVERA's test area): a jammed stretch over land, then a
                         long one over the sea
  range_2026-09-22.log   rocky hills of a desert test range: a GPS jump (spoofing test) refused by
                         the arbiter

    python3 make_dataset.py ../../courses/02-terminal/files/inbox
"""
import datetime
import os
import random
import sys


def epoch(y, mo, d, h, mi, s=0):
    """Tunisian time (UTC+1, no daylight saving) -> Unix seconds."""
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

    def write(self, path):
        self.lines.sort(key=lambda x: x[0])
        with open(path, "w") as f:
            for _, l in self.lines:
                f.write(l + "\n")
        return len(self.lines)


def routine(log, duration, lost, sats=(10, 13), heading=300.0):
    r = log.rnd
    log.add(0.0, "INFO", "estimator_node", "arbiter started: priority GPS > day > night > cn")
    log.add(0.4, "INFO", "gps_node", "serial port /dev/ttyTHS1 open at 9600 baud")
    log.add(0.6, "INFO", "imu_node", "IMU ready, declination 3.3 deg")
    log.add(0.8, "INFO", "live_camera", "day camera streaming, 2 frames per second")
    log.add(1.0, "INFO", "day_subscriber", "map loaded, search radius 600 m")
    log.add(1.2, "INFO", "vehicle_output_node", "MAVLink link to autopilot up")
    log.add(3.0, "INFO", "estimator_node", "state FIX source=GPS")
    for t in range(5, duration, 10):
        if not any(a <= t < b for a, b in lost):
            log.add(t, "INFO", "gps_node",
                    f"fix OK, {r.randint(*sats)} satellites, hdop {r.uniform(0.7, 1.4):.1f}")
    for t in range(30, duration, 60):
        log.add(t + 0.5, "INFO", "imu_node", f"attitude OK, heading {heading + r.uniform(-25, 25):.1f} deg")
    for t in range(20, duration, 30):
        log.add(t + 0.7, "INFO", "vehicle_output_node", "GPS_INPUT sent to autopilot")


def gps_outage(log, a, b, why):
    log.add(a + 2.0, "WARN", "gps_node", f"no fix for 2.0 s ({why})")
    for t in range(a + 12, b, 20):
        log.add(t, "WARN", "gps_node", f"no fix for {t - a:.1f} s")
    log.add(b, "INFO", "gps_node", "fix OK, 9 satellites, hdop 1.6")


def sousse():
    log = Log(epoch(2026, 9, 21, 8, 30), 2026_0921)
    r = log.rnd
    lost = [(300, 420), (800, 1010)]
    routine(log, 1260, lost, heading=315.0)
    # outage 1, over land: day vision takes over
    gps_outage(log, 300, 420, "jamming simulated")
    log.add(303.0, "WARN", "estimator_node", "state DEGRADED source=day vision (GPS lost)")
    for t in range(304, 420, 2):
        if r.random() < 0.85:
            log.add(t, "INFO", "day_subscriber", f"match OK, {r.randint(18, 60)} inliers, sigma 30 m")
        else:
            log.add(t, "WARN", "day_subscriber", f"no match: {r.randint(1, 5)} inliers < 6")
    log.add(355.0, "ERROR", "live_camera", "frame timeout: no frame for 2.4 s")
    log.add(421.0, "INFO", "estimator_node", "GPS agrees with day vision (gap 14 m): accepted")
    log.add(423.2, "INFO", "estimator_node", "state FIX source=GPS")
    log.add(424.0, "INFO", "estimator_node", "previous WARN cleared, GPS trusted again")
    # outage 2, over the sea: nothing to match, dead-reckoning, then NO_FIX
    gps_outage(log, 800, 1010, "jamming simulated")
    log.add(803.0, "WARN", "estimator_node", "state DEGRADED source=day vision (propagated)")
    for t in range(804, 1010, 4):
        log.add(t, "WARN", "day_subscriber", "no match: sea, nothing to recognise")
    log.add(924.0, "WARN", "estimator_node", "state NO_FIX: no source usable (dead-reckoning limit 120 s)")
    for t in (929.0, 939.0, 949.0):
        log.add(t, "ERROR", "vehicle_output_node", "no position for 5.0 s: autopilot uses its own failsafe")
    log.add(960.0, "INFO", "day_subscriber", f"match OK, 22 inliers, sigma 30 m")
    log.add(960.4, "WARN", "estimator_node", "state DEGRADED source=day vision (GPS lost)")
    log.add(975.0, "WARN", "estimator_node", "state NO_FIX: no source usable (day vision stale)")
    log.add(984.0, "ERROR", "live_camera", "frame timeout: no frame for 3.1 s")
    log.add(1011.0, "INFO", "estimator_node", "GPS returned after 211 s, no independent source: accepted (reachable)")
    log.add(1013.1, "INFO", "estimator_node", "state FIX source=GPS")
    log.add(1255.0, "INFO", "estimator_node", "shutdown requested (SIGINT)")
    return log


def desert_range():
    log = Log(epoch(2026, 9, 22, 16, 5), 2026_0922)
    r = log.rnd
    lost = [(610, 700)]
    routine(log, 980, lost, sats=(7, 11), heading=40.0)
    # spoofing test: a jump of 2.4 km is refused by the kinematic gate
    log.add(450.0, "WARN", "gps_node", "fix jump 2412 m in 1.0 s")
    log.add(450.1, "WARN", "estimator_node", "GPS refused: jump 2412 m > reachable 150 m")
    log.add(450.2, "WARN", "estimator_node", "state DEGRADED source=day vision (GPS in doubt)")
    for t in range(452, 520, 2):
        if r.random() < 0.9:
            log.add(t, "INFO", "day_subscriber", f"match OK, {r.randint(15, 48)} inliers, sigma 30 m")
        else:
            log.add(t, "WARN", "day_subscriber", "no match: scale check failed")
    log.add(520.0, "INFO", "estimator_node", "GPS agrees with day vision (gap 21 m): accepted")
    log.add(522.1, "INFO", "estimator_node", "state FIX source=GPS")
    # an outage in a dry valley between ridges (sky partly hidden)
    gps_outage(log, 610, 700, "few satellites in view")
    log.add(613.0, "WARN", "estimator_node", "state DEGRADED source=day vision (GPS lost)")
    for t in range(614, 700, 2):
        if t < 650 or t > 672:
            log.add(t, "INFO", "day_subscriber", f"match OK, {r.randint(12, 40)} inliers, sigma 30 m")
        else:
            log.add(t, "WARN", "day_subscriber", "no match: frame too dark (shadow of the ridge)")
    log.add(668.0, "WARN", "estimator_node", "state NO_FIX: no source usable (day vision stale)")
    log.add(669.0, "ERROR", "vehicle_output_node", "no position for 5.0 s: autopilot uses its own failsafe")
    log.add(674.0, "WARN", "estimator_node", "state DEGRADED source=day vision (GPS lost)")
    log.add(701.0, "INFO", "estimator_node", "GPS agrees with day vision (gap 9 m): accepted")
    log.add(703.2, "INFO", "estimator_node", "state FIX source=GPS")
    log.add(975.0, "INFO", "estimator_node", "shutdown requested (SIGINT)")
    return log


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    for name, fn in (("sousse_2026-09-21.log", sousse), ("range_2026-09-22.log", desert_range)):
        n = fn().write(os.path.join(out, name))
        print(name, n, "lines")
