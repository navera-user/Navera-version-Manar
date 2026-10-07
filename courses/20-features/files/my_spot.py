"""Score any place of the map.   python3 my_spot.py LAT LON
Example:  python3 my_spot.py 35.8256 10.6370
Cuts a 512 x 512 patch of the satellite map at zoom 17 around (LAT, LON), saves it with its
keypoints as my_spot.png and prints its matchability (your TODO 8)."""
import sys

import cv2

import navmap
from features import detect_keypoints, draw_keypoints, matchability

lat, lon = float(sys.argv[1]), float(sys.argv[2])
patch, _ = navmap.map_patch(lat, lon, 17, 512, 512)
kps, _ = detect_keypoints(patch, "ORB", max_points=500)
draw_keypoints(patch, kps, "my_spot.png")
print(f"({lat}, {lon}): {len(kps)} ORB keypoints, matchability {matchability(patch):.2f} → my_spot.png")
