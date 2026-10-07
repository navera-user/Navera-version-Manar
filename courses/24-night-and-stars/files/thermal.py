"""Lab 24, part B — night vision geometry, the motion gate, and an honest look at the night data.

Run:  python3 thermal.py
You re-implement the first steps of NAVERA's night localizer (night_pkg): bring a thermal frame
to the map's scale, measure how much of STHN's reference square it covers once turned north-up,
find the minimum flying height, and gate implausible fixes. Then you check the replay set's
labels with image correlation. Prints a report, draws thermal_vs_map.png and writes the
"thermal" part of results.json.
"""
import math
import os

import cv2
import numpy as np

from navmap import haversine_m, m_per_px, map_patch

THERMAL_DIR = "/data/navera_data/camera_pkg/camera_pkg/data/thermal"
DAY_DIR = "/data/navera_data/camera_pkg/camera_pkg/data/day"
if not os.path.isdir(THERMAL_DIR):                       # (outside the sandbox: the teacher's copy)
    THERMAL_DIR = os.path.expanduser("~/navera_data/camera_pkg/camera_pkg/data/thermal")
    DAY_DIR = os.path.expanduser("~/navera_data/camera_pkg/camera_pkg/data/day")
MAP_ZOOM = 17                 # STHN's satellite map: z17, ~0.97 m per pixel at Sousse
QUERY_PX = 512                # STHN_QUERY_PX: the reference square, in map pixels
MIN_COVERAGE = 0.85           # MIN_QUERY_COVERAGE in night_localizer.py


# TODO 9 — read the position written in a frame's file name.
#   "frame_0002_lat35.83026_lon10.64111_alt400m.jpg"  ->  (35.83026, 10.64111, 400.0)
#   "frame_0004_NOGPS_alt400m.jpg"                    ->  None   (no position recorded)
#   Works with a full path and with negative numbers ("lat-12.5").
def parse_thermal_name(filename):
    raise NotImplementedError("TODO 9")


# TODO 10 — the resize factor that gives the frame the map's resolution (normalize_query):
#   footprint_w = 2 h tan(hfov/2);  gsd_cam = footprint_w / width_px;
#   gsd_map = m_per_px(lat, zoom) (navmap);  scale = gsd_cam / gsd_map
def scale_to_map(altitude_m, hfov_deg, width_px, lat_deg, zoom=MAP_ZOOM):
    raise NotImplementedError("TODO 10")


# TODO 11 — share (0..1) of STHN's QUERY_PX x QUERY_PX north-up reference square covered by
# the frame, once it is scaled to the map (scale_to_map) and turned by its heading.
#   Sample the square at its pixel centres: u, v = np.meshgrid(np.arange(q) - (q - 1) / 2, same)
#   (map pixels from the centre). A sample lies in the frame when, in the frame's own axes
#       x = u cos(th) + v sin(th),   y = -u sin(th) + v cos(th)
#   |x| <= W / 2 and |y| <= H / 2, with W, H the frame size in MAP pixels (width_px * scale, ...).
#   Return the mean of that boolean array (a float).
def query_coverage(width_px, height_px, altitude_m, hfov_deg, heading_deg, lat_deg, q=QUERY_PX, zoom=MAP_ZOOM):
    raise NotImplementedError("TODO 11")


# TODO 12 — the lowest height (m) at which query_coverage >= need, by BISECTION between lo and hi
# (coverage grows with height). Stop when hi - lo < tol; return hi (a height that is enough).
def min_altitude(width_px, height_px, hfov_deg, heading_deg, lat_deg, need=MIN_COVERAGE, lo=50.0, hi=2000.0, tol=0.5):
    raise NotImplementedError("TODO 12")


# TODO 13 — NAVERA's motion gate (night_subscriber.py): a new fix is accepted only when the jump
# from the last accepted fix (the anchor) is within reach = max_speed * elapsed + margin.
#   anchor, fix: (lat, lon); t_anchor, t: seconds. Use haversine_m from navmap; elapsed >= 0.
#   Return (accepted: bool, jump_m: float, reach_m: float).
def motion_gate(anchor, t_anchor, fix, t, max_speed_mps=30.0, margin_m=30.0):
    raise NotImplementedError("TODO 13")


# TODO 14 — normalised cross-correlation of two pictures of the same shape (grey, any dtype):
#   a and b as float arrays, subtract each one's mean, then sum(a*b) / sqrt(sum(a*a) * sum(b*b)).
#   Returns a float in -1..1 (0.0 when one picture is uniform).
def ncc(a, b):
    raise NotImplementedError("TODO 14")


# TODO 15 — which DAY frame is this night frame a copy of?
#   Read the thermal frame and every day frame in grey (cv2.IMREAD_GRAYSCALE), shrink each to
#   `size` (cv2.resize(..., size, interpolation=cv2.INTER_AREA)), compute ncc with each day frame.
#   Return (name of the best day file (basename), best ncc, second-best ncc).
def find_day_twin(thermal_path, day_paths, size=(192, 91)):
    raise NotImplementedError("TODO 15")


# ---- you don't need to change anything below this line (but read it!) ----
import glob  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402

CAMERA_HFOV_DEG = 84.0        # the field of view NAVERA's synthetic night tests assumed
THERMAL_CAM = (640, 480)      # a 4:3 thermal sensor, as in NAVERA's synthetic night tests
SIM_THERMAL = (640, 528, 56.7)  # the simulator's first thermal camera: 56.7 x 48 deg


def fake_thermal(map_bgr):
    """A grey render of the map: the stand-in NAVERA's synthetic night tests fed to STHN."""
    return cv2.cvtColor(cv2.cvtColor(map_bgr, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)


def side_by_side(frame_path, out_png="thermal_vs_map.png"):
    """frame (at map resolution) | the map at its labelled position | the same map in grey."""
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


def save_results(section, values, path="results.json"):
    data = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
    data[section] = values
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class Todo(Exception):
    pass


def _do(fn, *a, **k):
    try:
        return fn(*a, **k)
    except NotImplementedError as e:
        print(f"  ({e} is not done yet)")
        raise Todo()


def frame_number(name):
    return int(re.search(r"frame_(\d+)", name).group(1))


def main():
    res = {}
    files = sorted(glob.glob(os.path.join(THERMAL_DIR, "frame_*.jpg")))
    print(f"{len(files)} night frames in {THERMAL_DIR}")
    labels = [_do(parse_thermal_name, f) for f in files]
    for f, lab in list(zip(files, labels))[:4]:
        print(f"  {os.path.basename(f):48s} -> {lab}")
    res["n_frames"] = len(files)
    res["n_nogps"] = sum(lab is None for lab in labels)
    print(f"  ... {res['n_nogps']} frames have no position (NOGPS)")

    # scale and coverage of a replay frame, then of a 640 x 512 thermal camera
    frame = os.path.join(THERMAL_DIR, "frame_0010_lat35.85002_lon10.61131_alt400m.jpg")
    img = cv2.imread(frame)
    s = _do(scale_to_map, 400.0, CAMERA_HFOV_DEG, img.shape[1], 35.85002)
    print(f"\nReplay frame {img.shape[1]}x{img.shape[0]} px at 400 m, {CAMERA_HFOV_DEG:.0f}° camera: "
          f"scale {s:.3f} -> {img.shape[1] * s:.0f}x{img.shape[0] * s:.0f} map px")
    res["scale_frame10"] = s
    lat = 35.83
    print(f"\nCoverage of the {QUERY_PX} px reference square, {THERMAL_CAM[0]}x{THERMAL_CAM[1]} camera, "
          f"{CAMERA_HFOV_DEG:.0f}°:")
    print("  height   heading 0°   heading 45°")
    cov = {}
    for h in (250.0, 300.0, 350.0, 400.0, 500.0):
        c0 = _do(query_coverage, THERMAL_CAM[0], THERMAL_CAM[1], h, CAMERA_HFOV_DEG, 0.0, lat)
        c45 = _do(query_coverage, THERMAL_CAM[0], THERMAL_CAM[1], h, CAMERA_HFOV_DEG, 45.0, lat)
        cov[str(int(h))] = [c0, c45]
        print(f"  {h:5.0f} m   {c0:9.2f}   {c45:10.2f}")
    res["coverage_640x480_84deg"] = cov
    h0 = _do(min_altitude, THERMAL_CAM[0], THERMAL_CAM[1], CAMERA_HFOV_DEG, 0.0, lat)
    h45 = _do(min_altitude, THERMAL_CAM[0], THERMAL_CAM[1], CAMERA_HFOV_DEG, 45.0, lat)
    h57 = _do(min_altitude, SIM_THERMAL[0], SIM_THERMAL[1], SIM_THERMAL[2], 0.0, lat)
    print(f"Minimum height for {MIN_COVERAGE:.0%} coverage: heading 0° {h0:.0f} m, heading 45° {h45:.0f} m; "
          f"the 56.7° x 48° camera, heading 0°: {h57:.0f} m")
    res.update(min_alt_0deg_m=h0, min_alt_45deg_m=h45, min_alt_57x48_m=h57)

    # the motion gate on a run-away track
    track = [((35.8300, 10.6400), 0.0), ((35.8303, 10.6404), 2.0), ((35.8420, 10.6600), 4.0),
             ((35.8309, 10.6412), 6.0)]
    anchor, t_a = track[0]
    print("\nMotion gate (30 m/s + 30 m):")
    gate = []
    for fix, t in track[1:]:
        ok, jump, reach = _do(motion_gate, anchor, t_a, fix, t)
        print(f"  t={t:3.0f} s  jump {jump:6.0f} m  reach {reach:4.0f} m  -> {'accepted' if ok else 'REJECTED'}")
        gate.append(bool(ok))
        if ok:
            anchor, t_a = fix, t
    res["gate_decisions"] = gate

    # honesty: what are these night frames?
    days = sorted(glob.glob(os.path.join(DAY_DIR, "frame_*.jpeg")))
    print(f"\nEach night frame against the {len(days)} day frames (NCC on 192x91 grey thumbnails):")
    twins, best, second = {}, [], []
    for f in files:
        name, b, s2 = _do(find_day_twin, f, days)
        twins[os.path.basename(f)] = name
        best.append(b)
        second.append(s2)
    offs = [(frame_number(d) - frame_number(n)) % len(days) for n, d in twins.items()]
    for n in list(twins)[:5]:
        print(f"  {n[:10]} -> {twins[n]}")
    print(f"  ... best NCC median {np.median(best):.2f}, second best median {np.median(second):.2f}; "
          f"day number - night number (mod {len(days)}): {sorted(set(offs))}")
    res.update(twins=twins, twin_best_ncc_median=float(np.median(best)),
               twin_second_ncc_median=float(np.median(second)), twin_offsets=sorted(set(offs)))

    out, _ = side_by_side(frame)
    print(f"\nSaved {out} — compare the night frame with the map at its label.")
    save_results("thermal", res)
    print("Wrote the 'thermal' section of results.json")


if __name__ == "__main__":
    try:
        main()
    except Todo:
        print("\nStopped at the first TODO that is not done yet.")
