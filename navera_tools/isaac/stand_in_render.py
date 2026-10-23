#!/usr/bin/env python3
"""A stand-in for Isaac Sim (isaac_flight.py) on any computer: writes the same run directory
(session.json, frames/, frames.jsonl, done.json) with frames cut from the scene's orthophoto
mosaic instead of rendered. SIMULATION / development only (no relief, no buildings in 3-D, no
light): for long soak runs of NAVERA's real node chain on the Jetson without the PC, e.g. the
day_subscriber memory profile (memory_soak.sh). isaac_link.py reads the directory unchanged
(camera model, IMU, baro, NMEA GPS, the GPS cut) from flight_profile.Profile, here a circle.

    python3 stand_in_render.py --scene SCENE_DIR --out RUN_DIR [--radius 500] [--speed 8]
        [--height 250] [--fps 5] [--duration 2400] [--keep 200]

The camera is the closed loop's: nadir, held level (gimbal), image top = the nose, a wide pinhole
(--hfov 100, 1920 x 1080). Frames older than the newest --keep are deleted (isaac_link reads
each one within a second): a 40-min run stays below 100 MB on disk.
"""
import argparse
import json
import math
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flight_profile import GeoRef, Profile  # noqa: E402


def render(mosaic, mos, geo, e, n, heading_deg, agl_m, w, h, hfov_deg):
    """The nadir pinhole view (w x h) at east/north e, n (m from the scene origin), image top =
    heading, from agl_m above the (flat) ground."""
    f = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
    gsd = agl_m / f                                    # ground metres per image pixel
    hd = math.radians(heading_deg)
    fwd = np.array([math.sin(hd), math.cos(hd)])       # (east, north) of the image's up
    right = np.array([math.cos(hd), -math.sin(hd)])
    lat_n, lat_s, lon_w, lon_e = mos["lat_n"], mos["lat_s"], mos["lon_w"], mos["lon_e"]
    W, H = mos["width"], mos["height"]

    def to_px(pe, pn):
        lat, lon = geo.to_latlon(pe, pn)
        return (lon - lon_w) / (lon_e - lon_w) * W, (lat_n - lat) / (lat_n - lat_s) * H
    src, dst = [], []
    for u, v in ((0, 0), (w, 0), (0, h)):
        du, dv = (u - w / 2) * gsd, (v - h / 2) * gsd
        g = np.array([e, n]) + right * du - fwd * dv
        src.append(to_px(*g))
        dst.append((u, v))
    A = cv2.getAffineTransform(np.float32(src), np.float32(dst))
    return cv2.warpAffine(mosaic, A, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", required=True, help="prepared scene dir (scene.json, mosaic.jpg)")
    ap.add_argument("--out", required=True, help="the run dir isaac_link reads (run_dir)")
    ap.add_argument("--radius", type=float, default=500.0)
    ap.add_argument("--speed", type=float, default=8.0)
    ap.add_argument("--height", type=float, default=250.0)
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--duration", type=float, default=2400.0, help="s, then done.json")
    ap.add_argument("--hfov", type=float, default=100.0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height-px", type=int, default=1080)
    ap.add_argument("--keep", type=int, default=200, help="frames kept on disk")
    a = ap.parse_args()
    scene = json.load(open(os.path.join(a.scene, "scene.json")))
    mos = scene["mosaic"]
    mosaic = cv2.imread(os.path.join(a.scene, "mosaic.jpg"))
    if mosaic is None:
        raise SystemExit(f"{a.scene}/mosaic.jpg: not readable")
    geo = GeoRef(scene["lat0"], scene["lon0"])
    prof = Profile(route="circuit", radius_m=a.radius, speed_mps=a.speed, height_m=a.height, shake=0.0)
    os.makedirs(os.path.join(a.out, "frames"), exist_ok=True)
    for name in ("done.json", "frames.jsonl"):
        if os.path.exists(os.path.join(a.out, name)):
            os.remove(os.path.join(a.out, name))
    t0 = time.time()
    with open(os.path.join(a.out, "session.json"), "w") as f:
        json.dump(dict(t0_wall=t0, lat0=scene["lat0"], lon0=scene["lon0"], z_ref_m=scene["z_ref_m"],
                       vehicle="copter", traj=None, stand_in=True,
                       profile=dict(radius_m=a.radius, speed_mps=a.speed, height_m=a.height),
                       duration_s=a.duration,
                       render=dict(hfov_deg=a.hfov, width=a.width, height=a.height_px, fps=a.fps,
                                   mount="nadir, image top = nose, gimbal (level)", gimbal=True,
                                   mount_err_rpy_deg=[0.0, 0.0, 0.0])), f, indent=1)
    log = open(os.path.join(a.out, "frames.jsonl"), "a")
    i, kept = 0, []
    while True:
        t = time.time() - t0
        if t > a.duration:
            break
        st = prof.state(t)
        heading = (90.0 - st.yaw) % 360.0
        img = render(mosaic, mos, geo, st.e, st.n, heading, st.u, a.width, a.height_px, a.hfov)
        name = f"f_{i:06d}.jpg"
        cv2.imwrite(os.path.join(a.out, "frames", name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        lat, lon = geo.to_latlon(st.e, st.n)
        log.write(json.dumps(dict(i=i, t=round(t, 4), file=name, lat=round(lat, 7), lon=round(lon, 7),
                                  z=round(st.u, 2), roll=0.0, pitch=0.0, heading=round(heading, 2))) + "\n")
        log.flush()
        kept.append(name)
        while len(kept) > a.keep:
            try:
                os.remove(os.path.join(a.out, "frames", kept.pop(0)))
            except OSError:
                pass
        i += 1
        time.sleep(max(0.0, t0 + i / a.fps - time.time()))
    json.dump(dict(frames=i, duration_s=round(time.time() - t0, 1)), open(os.path.join(a.out, "done.json"), "w"))


if __name__ == "__main__":
    main()
