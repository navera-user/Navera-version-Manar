#!/usr/bin/env python3
"""Show a calibration board or a piece of NAVERA's satellite map full screen, at a KNOWN size,
for bench tests of a real camera (no printer, no flight).

    python3 navera_tools/screen_target.py board            # 9x6 checkerboard for calibrate_camera.py
    python3 navera_tools/screen_target.py map 35.8288 10.6360 [--zoom 17]

The screen's physical width comes from the display (xrandr: e.g. 527 mm for 1920 px), or
--screen-mm. The tool prints what the camera needs:
  board : the printed-square size to give calibrate_camera.py (--square-mm);
  map   : the map scale on the screen (map metres per screen millimetre), so a camera at a
          distance d (mm) from the screen is "flying" at d x scale metres above that ground.
Escape or q closes the window.
"""
import argparse
import math
import os
import re
import sqlite3
import subprocess
import sys

import cv2
import numpy as np


def screen_size():
    """(width_px, height_px, width_mm) of the primary display, or None."""
    try:
        out = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5,
                             env=dict(os.environ, DISPLAY=os.environ.get("DISPLAY") or ":1")).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r" connected (?:primary )?(\d+)x(\d+)\+\d+\+\d+ .*? (\d+)mm x (\d+)mm", out)
    return (int(m.group(1)), int(m.group(2)), float(m.group(3))) if m else None


def board(w, h, cols=9, rows=6):
    """The largest (cols+1) x (rows+1)-square board fitting the screen with a white margin."""
    sq = int(min(w / (cols + 3), h / (rows + 3)))
    img = np.full((h, w), 255, np.uint8)
    x0, y0 = (w - sq * (cols + 1)) // 2, (h - sq * (rows + 1)) // 2
    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 0:
                img[y0 + r * sq:y0 + (r + 1) * sq, x0 + c * sq:x0 + (c + 1) * sq] = 0
    return img, sq


def map_view(mbtiles, lat, lon, zoom, w, h):
    """The map around (lat, lon) at one map pixel per screen pixel; (image, metres per pixel)."""
    n = 2 ** zoom
    fx = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    fy = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    con = sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True)
    out = np.zeros((h, w, 3), np.uint8)
    px0, py0 = fx * 256 - w / 2, fy * 256 - h / 2
    missing = 0
    for ty in range(int(py0 // 256), int((py0 + h) // 256) + 1):
        for tx in range(int(px0 // 256), int((px0 + w) // 256) + 1):
            row = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                              (zoom, tx, n - 1 - ty)).fetchone()
            if not row:
                missing += 1
                continue
            t = cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_COLOR)
            if t is None:
                continue
            t = cv2.resize(t, (256, 256))
            x, y = int(round(tx * 256 - px0)), int(round(ty * 256 - py0))
            sx0, sy0 = max(0, -x), max(0, -y)
            dx0, dy0 = max(0, x), max(0, y)
            cw, ch = min(256 - sx0, w - dx0), min(256 - sy0, h - dy0)
            if cw > 0 and ch > 0:
                out[dy0:dy0 + ch, dx0:dx0 + cw] = t[sy0:sy0 + ch, sx0:sx0 + cw]
    con.close()
    mpp = 156543.03392 * math.cos(r) / n
    return out, mpp, missing


def show(img, progress=None):
    """Full screen until Escape / q; with progress (a file calibrate_camera.py writes), its
    text is drawn in the top margin, and the window closes when the file says done."""
    cv2.namedWindow("NAVERA target", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("NAVERA target", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    base = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    while True:
        frame = base
        if progress:
            try:
                text = open(progress).read().strip()
            except OSError:
                text = "waiting for the camera..."
            if text.startswith("done"):
                break
            frame = base.copy()
            cv2.putText(frame, text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 255), 4)
        cv2.imshow("NAVERA target", frame)
        if cv2.waitKey(200) in (27, ord("q")):
            break
        if cv2.getWindowProperty("NAVERA target", cv2.WND_PROP_VISIBLE) < 1:
            break
    cv2.destroyAllWindows()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["board", "map"])
    ap.add_argument("lat", nargs="?", type=float)
    ap.add_argument("lon", nargs="?", type=float)
    ap.add_argument("--zoom", type=int, default=17)
    ap.add_argument("--mbtiles", default=os.environ.get("NAVERA_MBTILES", ""))
    ap.add_argument("--screen-mm", type=float, help="the screen's visible width in mm (else from xrandr)")
    ap.add_argument("--dry-run", action="store_true", help="print the scale, show nothing")
    ap.add_argument("--progress", help="board: show calibrate_camera.py's progress file on the board")
    a = ap.parse_args()
    s = screen_size()
    if s is None and not a.screen_mm:
        sys.exit("cannot read the screen size (xrandr): give --screen-mm")
    w, h = (s[0], s[1]) if s else (1920, 1080)
    mm_per_px = (a.screen_mm or s[2]) / w
    if a.what == "board":
        img, sq = board(w, h)
        print(f"checkerboard 9x6 inner corners, squares of {sq} px = {sq * mm_per_px:.2f} mm "
              f"(screen {w} px = {w * mm_per_px:.0f} mm)")
        print(f"calibrate with: --board 9x6 --square-mm {sq * mm_per_px:.2f}")
    else:
        if a.lat is None or a.lon is None or not a.mbtiles:
            sys.exit("map: give LAT LON and the map (--mbtiles or NAVERA_MBTILES)")
        img, mpp, missing = map_view(a.mbtiles, a.lat, a.lon, a.zoom, w, h)
        scale = mpp / (mm_per_px / 1000.0)              # map metres per screen metre
        print(f"map around {a.lat:.5f}, {a.lon:.5f} at zoom {a.zoom}: {mpp:.3f} m of ground per screen "
              f"pixel; scale 1 : {scale:.0f} — a camera d mm from the screen 'flies' at "
              f"d x {scale / 1000:.3f} m above this ground" + (f" ({missing} tiles missing)" if missing else ""))
        if missing:
            print("warning: tiles missing in the map around this point (black areas)")
    if not a.dry_run:
        show(img, a.progress)


if __name__ == "__main__":
    main()
