#!/usr/bin/env python3
"""make_dataset.py — builds datasets/20-live-camera/ (TEACHER ONLY: it holds the hidden truths of the lab).

    python3 solutions/20-live-camera/make_dataset.py            # everything (≈1 min: the map render)
    python3 solutions/20-live-camera/make_dataset.py --no-ortho # keep the rendered map, redo the CSVs

Outputs (deterministic, seeded):
  bench/frame_000..029.jpg, bench/insta360_top.yaml   REAL data from NAVERA's bench (2026-10-06), copied as data
                                                      (kept as they are; moved here from the old frames/ folder)
  grab_log.csv        60 s of grab times of a USB camera at 28.8 fps: jitter, dropped frames, one stall
  flashes.csv         a simulated screen-flash bench: when the program turned the screen white
  bench_frames.csv    the same bench: grab time and centre brightness of every frame
  flight/imu.csv      a survey plane's attitude at 50 Hz (x, y, z, w), with a 0.6 s dropout
  flight/frames.csv   the camera frames of that flight: grab time as the program saw it, and the TRUE pose at
                      each exposure (position ENU metres from the map centre, attitude x, y, z, w)
  flight/map.jpg, flight/map.json   the ground under the flight, rendered from OpenStreetMap data (© OSM contributors)

HIDDEN TRUTHS (never in datasets/: lesson, lab and README must not reveal them; check.py and TEACHER.md hold them):
  the camera's own delay L_TRUE = 0.118 s (same camera on the bench and on the plane);
  the bench screen's delay SCREEN_S = 0.020 s (the LAB gives this one: "measured with a photodiode").
"""
import argparse
import csv
import json
import math
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ACADEMY, "datasets", "20-live-camera")
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite.rotations import q_from_euler_zyx, q_mul, q_from_axis_angle, q_normalize  # noqa: E402

FPS = 28.8
T = 1.0 / FPS
L_TRUE = 0.118           # the lab camera's own delay: exposure (middle) -> grab returns
SCREEN_S = 0.020         # the bench screen's delay: "white" requested -> light out of the screen
EXPOSE_S = 0.008         # exposure time of one frame
MAP_CENTRE = (35.8290, 10.6330)      # Sousse, Tunisia (NAVERA's test area); the flight's ENU origin
MAP_GSD = 0.6
MAP_PX = 3600
G = 9.81


def write_csv(path, header, rows, fmt):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([fm.format(v) if isinstance(fm, str) else fm(v) for fm, v in zip(fmt, r)])


# ------------------------------------------------------------------ grab log (frame statistics)
def grab_log(rng):
    t0 = 5123.402                      # a monotonic clock: seconds since the computer started
    times = []
    k = 0
    e = t0
    stall_at = t0 + 41.3
    stalled = False
    while e < t0 + 60.0:
        e = t0 + k * T + rng.normal(0.0, 0.0004)
        k += 1
        if not stalled and e >= stall_at:            # the stream pauses for 0.35 s (USB re-sync)
            stalled = True
            k += int(round(0.35 / T)) - 1
            continue
        if rng.random() < 0.012:                     # a dropped frame (≈1 %)
            continue
        if k in (500, 1203):                         # two double drops
            k += 1
            continue
        late = rng.normal(0.0012, 0.0011)
        if rng.random() < 0.03:                      # USB / scheduler: some grabs come late
            late += rng.uniform(0.003, 0.009)
        times.append(e + max(0.0, late))
    times = sorted(times)
    write_csv(os.path.join(OUT, "grab_log.csv"), ["grab_s"], [[t] for t in times], ["{:.6f}"])
    return times


# ------------------------------------------------------------------ the flash bench (delay)
def flash_bench(rng):
    start = 1791400000.0                             # wall clock (time.time()) of the bench computer
    flashes = []
    for k in range(21):
        flashes.append(start + 1.0 + 1.4 * k + rng.uniform(0.0, 0.25))
    unseen = 8                                       # someone stood in front of the camera
    stall_flash = 14                                 # a USB stall right after this flash
    frames = []
    e = start + 0.3 + rng.uniform(0, T)
    end = flashes[-1] + 1.0
    i = 0
    while e < end:
        e_i = e + i * T + rng.normal(0, 0.0003)
        i += 1
        if e_i > end:
            break
        lo, hi = e_i - EXPOSE_S / 2, e_i + EXPOSE_S / 2
        frac = 0.0
        for k, t0 in enumerate(flashes):
            if k == unseen:
                continue
            w0, w1 = t0 + SCREEN_S, t0 + SCREEN_S + 0.55
            frac = max(frac, max(0.0, min(hi, w1) - max(lo, w0)) / EXPOSE_S)
        b = 31.0 + frac * (214.0 - 31.0) + rng.normal(0, 2.0)
        grab = e_i + L_TRUE + abs(rng.normal(0.0, 0.0015))
        t_s = flashes[stall_flash] + SCREEN_S
        if t_s - 0.05 < e_i < t_s + 0.20:            # these frames wait in the USB stall
            grab = max(grab, t_s + 0.33 + (e_i - t_s) * 0.2)
        frames.append((grab, round(min(255.0, max(0.0, b)), 1)))
    frames.sort()
    write_csv(os.path.join(OUT, "flashes.csv"), ["flash", "t_white_s"], [[k, t] for k, t in enumerate(flashes)],
              ["{:d}", "{:.6f}"])
    write_csv(os.path.join(OUT, "bench_frames.csv"), ["grab_s", "brightness"], frames, ["{:.6f}", "{:.1f}"])
    return flashes, frames


# ------------------------------------------------------------------ the flight
def smooth(t, t0, t1, a, b):
    """a → b between t0 and t1 with a smoothstep (zero rate at both ends)."""
    if t <= t0:
        return a
    if t >= t1:
        return b
    x = (t - t0) / (t1 - t0)
    return a + (b - a) * (3 * x * x - 2 * x ** 3)


ROLL_SEGMENTS = [(3.0, 5.0, 0.0, 30.0), (11.0, 13.0, 30.0, 0.0), (17.0, 18.0, 0.0, -48.0), (20.0, 23.0, -48.0, 0.0)]


def roll_deg(t):
    r = 0.0
    for t0, t1, a, b in ROLL_SEGMENTS:
        if t >= t0:
            r = smooth(t, t0, t1, a, b)
    return r


def pitch_up_deg(t):
    return 2.0 + 0.6 * math.sin(2 * math.pi * t / 7.0)


def truth(duration=30.0, dt=0.001, speed=25.0, heading0=60.0, start=(-380.0, -260.0), height=150.0):
    """Integrated flight: arrays t, east, north, heading (deg), roll (deg), pitch_up (deg), height."""
    n = int(round(duration / dt)) + 1
    t = np.arange(n) * dt
    hd = np.zeros(n)
    e = np.zeros(n)
    nn = np.zeros(n)
    hd[0], e[0], nn[0] = heading0, start[0], start[1]
    for k in range(1, n):
        r = math.radians(roll_deg(t[k - 1]))
        hd[k] = hd[k - 1] + math.degrees(G * math.tan(r) / speed) * dt     # coordinated turn
        h = math.radians(hd[k - 1])
        e[k] = e[k - 1] + speed * math.sin(h) * dt
        nn[k] = nn[k - 1] + speed * math.cos(h) * dt
    rl = np.array([roll_deg(x) for x in t])
    pu = np.array([pitch_up_deg(x) for x in t])
    hh = height + 3.0 * np.sin(2 * np.pi * t / 11.0)
    return t, e, nn, hd, rl, pu, hh


def attitude(heading_deg, roll, pitch_up):
    """Body → ENU quaternion (x, y, z, w): ROS ZYX with yaw = 90° − heading, ROS pitch = −pitch_up."""
    return q_from_euler_zyx(math.radians(roll), math.radians(-pitch_up), math.radians(90.0 - heading_deg))


def noisy(q, rng, sigma_deg):
    axis = rng.normal(size=3)
    axis /= np.linalg.norm(axis)
    return q_normalize(q_mul(q_from_axis_angle(axis, math.radians(abs(rng.normal(0, sigma_deg)))), q))


def flight(rng):
    t, e, n, hd, rl, pu, hh = truth()

    def at(x):
        k = min(len(t) - 1, max(0, int(round(x / 0.001))))
        return k

    os.makedirs(os.path.join(OUT, "flight"), exist_ok=True)
    imu = []
    k = 0
    while True:
        ts = 0.02 * k + rng.uniform(-0.001, 0.001)
        k += 1
        if ts > 29.99:
            break
        if 14.6 <= ts < 15.2:                        # the IMU stops answering for 0.6 s (I²C bus busy)
            continue
        i = at(ts)
        q = noisy(attitude(hd[i], rl[i], pu[i]), rng, 0.03)
        if q[3] < 0:
            q = -q
        imu.append([ts, *q])
    write_csv(os.path.join(OUT, "flight", "imu.csv"), ["t_s", "qx", "qy", "qz", "qw"], imu,
              ["{:.6f}"] + ["{:.9f}"] * 4)
    frames = []
    j = 0
    while True:
        ex = 0.05 + j * T + rng.normal(0, 0.0004)
        j += 1
        if ex > 29.8:
            break
        if rng.random() < 0.01:
            continue
        i = at(ex)
        q = attitude(hd[i], rl[i], pu[i])
        if q[3] < 0:
            q = -q
        grab = ex + L_TRUE + abs(rng.normal(0.0, 0.0015))
        frames.append([len(frames), grab, e[i], n[i], hh[i], *q])
    write_csv(os.path.join(OUT, "flight", "frames.csv"),
              ["frame", "grab_s", "east_m", "north_m", "height_m", "true_qx", "true_qy", "true_qz", "true_qw"],
              frames, ["{:d}", "{:.6f}", "{:.3f}", "{:.3f}", "{:.3f}"] + ["{:.9f}"] * 4)
    print(f"flight: east {e.min():.0f}..{e.max():.0f} m, north {n.min():.0f}..{n.max():.0f} m, "
          f"heading {hd[0]:.0f} → {hd[-1]:.0f}°, {len(imu)} IMU samples, {len(frames)} frames")
    return imu, frames


def render_map():
    sys.path.insert(0, os.path.join(ACADEMY, "datasets", "_map"))
    import cv2
    from render_view import render_view
    img, meta = render_view(MAP_CENTRE[0], MAP_CENTRE[1], heading_deg=0.0, ground_size_m=MAP_GSD * MAP_PX,
                            out_px=MAP_PX, seed=3, style="pseudo", return_meta=True)
    cv2.imwrite(os.path.join(OUT, "flight", "map.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    info = {"centre_lat": MAP_CENTRE[0], "centre_lon": MAP_CENTRE[1], "gsd_m": MAP_GSD, "width_px": MAP_PX,
            "height_px": MAP_PX,
            "pixel_of_enu": "u = width_px / 2 + east_m / gsd_m,  v = height_px / 2 - north_m / gsd_m",
            "attribution": "© OpenStreetMap contributors (map data ODbL; synthetic rendering for the course)"}
    json.dump(info, open(os.path.join(OUT, "flight", "map.json"), "w"), indent=1)


README = """Mission 20 — live camera: data

bench/frame_000..029.jpg  REAL frames of NAVERA's Insta360 ONE R (USB webcam mode, MJPG 1920 x 1080), recorded on
                          NAVERA's bench on 2026-10-06 while its top lens was being calibrated. Top half = top lens,
                          bottom half = bottom lens (pixelated: it filmed people in the room).
bench/insta360_top.yaml   the real calibration file of that top lens (copied as data).

The other files are SYNTHETIC (simulated, seeded), made for this lab:
grab_log.csv              60 s of grab times of a USB camera (a monotonic clock, seconds).
flashes.csv               a screen-flash bench: when the program asked the screen to turn white.
bench_frames.csv          the same bench: grab time and centre brightness (0-255) of every frame.
flight/imu.csv            a survey plane's attitude at 50 Hz: t_s, then a quaternion (x, y, z, w), body -> ENU.
flight/frames.csv         the frames of that flight: grab_s = when the program received the frame (same clock as
                          imu.csv), and the TRUE pose at the frame's exposure (east/north/height in metres from the
                          map centre, attitude x, y, z, w).
flight/map.jpg, map.json  the ground under the flight (Sousse, Tunisia), drawn from OpenStreetMap data:
                          © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ortho", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    # the real bench frames: moved once from the old layout, never regenerated
    old = os.path.join(OUT, "frames")
    bench = os.path.join(OUT, "bench")
    if os.path.isdir(old) and not os.path.isdir(bench):
        shutil.move(old, bench)
    if os.path.exists(os.path.join(OUT, "insta360_top.yaml")):
        shutil.move(os.path.join(OUT, "insta360_top.yaml"), os.path.join(bench, "insta360_top.yaml"))
    for stale in ("flash_frames.csv", "grab_times.csv", "turn_frames.csv", "turn_imu.csv", "make_dataset.py",
                  "README.txt"):
        p = os.path.join(OUT, stale)
        if os.path.exists(p):
            os.remove(p)
    rng = np.random.default_rng(2026_10_20)
    grab_log(rng)
    flash_bench(rng)
    flight(rng)
    if not a.no_ortho or not os.path.exists(os.path.join(OUT, "flight", "map.jpg")):
        render_map()
    open(os.path.join(OUT, "README.txt"), "w").write(README)
    print("written", OUT)


if __name__ == "__main__":
    main()
