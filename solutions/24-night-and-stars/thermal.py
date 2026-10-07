"""Lab 24 — a night frame next to the satellite map.

Run:  python3 thermal.py
It lists the night replay frames, reads the position written in each file name, and draws
thermal_vs_map.png: the frame, the map at the same place and scale, and a grey "fake thermal"
render of that map (what NAVERA's synthetic night tests use). Fill in the two TODOs.
"""
import math
import os

THERMAL_DIR = "/data/navera_data/camera_pkg/camera_pkg/data/thermal"
if not os.path.isdir(THERMAL_DIR):                       # (outside the sandbox: the teacher's copy)
    THERMAL_DIR = os.path.expanduser("~/navera_data/camera_pkg/camera_pkg/data/thermal")
CAMERA_HFOV_DEG = 84.0                                   # the field of view NAVERA's night tests assume
MAP_ZOOM = 17                                            # STHN's satellite map: z17, ~0.97 m per pixel


# TODO 5: read the position written in a frame's file name.
#   "frame_0002_lat35.83026_lon10.64111_alt400m.jpg"  ->  (35.83026, 10.64111, 400.0)
#   "frame_0004_NOGPS_alt400m.jpg"                    ->  None   (no position recorded)
# Tip: drop the ".jpg", split the name on "_", then look for the parts that start with
# "lat", "lon" and "alt" and turn the rest of each part into a float ("400m" -> remove the "m").
def parse_thermal_name(filename):
    base = os.path.basename(filename)
    parts = os.path.splitext(base)[0].split("_")
    vals = {}
    for p in parts:
        for key in ("lat", "lon", "alt"):
            if p.startswith(key):
                try:
                    vals[key] = float(p[len(key):].rstrip("m"))
                except ValueError:
                    pass
    if "lat" not in vals or "lon" not in vals or "alt" not in vals:
        return None
    return vals["lat"], vals["lon"], vals["alt"]


# TODO 6: how much the frame must be resized to have the map's resolution.
# This is the first thing NAVERA's night localizer does (night_localizer.py, normalize_query):
#   footprint_w = 2 · altitude · tan(hfov / 2)       ground width seen by the camera (lesson 17)
#   gsd_cam     = footprint_w / width_px            meters per pixel of the frame
#   gsd_map     = map_m_per_px(lat, zoom)           meters per pixel of the map (use m_per_px from navmap)
#   scale       = gsd_cam / gsd_map                 multiply the frame size by this
# Return scale (a float).
def scale_to_map(altitude_m, hfov_deg, width_px, lat_deg, zoom=MAP_ZOOM):
    footprint_w = 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0)
    return (footprint_w / width_px) / m_per_px(lat_deg, zoom)


# ---- you don't need to change anything below this line (but read it!) ----
import glob  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from navmap import m_per_px, map_patch  # noqa: E402


def fake_thermal(map_bgr):
    """A grey render of the map: the stand-in NAVERA's synthetic night tests feed to STHN."""
    return cv2.cvtColor(cv2.cvtColor(map_bgr, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)


def side_by_side(frame_path, out_png="thermal_vs_map.png"):
    """frame (at map resolution) | the map at its labelled position | fake thermal of that map."""
    lab = parse_thermal_name(frame_path)
    if lab is None:
        raise ValueError(f"{os.path.basename(frame_path)} has no position in its name")
    lat, lon, alt = lab
    frame = cv2.imread(frame_path)
    s = scale_to_map(alt, CAMERA_HFOV_DEG, frame.shape[1], lat)
    small = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    small = cv2.convertScaleAbs(small, alpha=2.5)        # brighten the dark frame to look at it
    h, w = small.shape[:2]
    patch, _ = map_patch(lat, lon, MAP_ZOOM, w, h)
    gap = np.full((h, 8, 3), 255, np.uint8)
    out = np.hstack([small, gap, patch, gap, fake_thermal(patch)])
    for x, text in ((5, "night frame (brightened)"), (w + 13, "map at its label"), (2 * w + 21, "map in grey")):
        cv2.putText(out, text, (x, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        cv2.putText(out, text, (x, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 200, 255), 1)
    cv2.imwrite(out_png, out)
    return out_png, s


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(THERMAL_DIR, "frame_*.jpg")))
    print(f"{len(files)} night frames in {THERMAL_DIR}\n")
    try:
        for f in files[:6]:
            print(f"  {os.path.basename(f):48s} -> {parse_thermal_name(f)}")
        print("  …")
        n = sum(parse_thermal_name(f) is None for f in files)
        print(f"\n{n} frames have no position (NOGPS)")
    except NotImplementedError as e:
        print(f"({e} is not done yet)")
        raise SystemExit(0)
    try:
        frame = os.path.join(THERMAL_DIR, "frame_0010_lat35.85002_lon10.61131_alt400m.jpg")
        img = cv2.imread(frame)
        s = scale_to_map(400.0, CAMERA_HFOV_DEG, img.shape[1], 35.85002)
        print(f"\nframe {img.shape[1]}x{img.shape[0]} px at 400 m with an {CAMERA_HFOV_DEG:.0f}° camera: "
              f"scale {s:.3f} -> {img.shape[1] * s:.0f}x{img.shape[0] * s:.0f} px at map resolution")
        out, _ = side_by_side(frame)
        print(f"Saved {out} — open it in the editor and compare the three pictures.")
    except NotImplementedError as e:
        print(f"({e} is not done yet)")
