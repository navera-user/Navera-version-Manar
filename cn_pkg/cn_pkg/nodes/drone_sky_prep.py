#!/usr/bin/env python3
"""Drone GPS positioning via sky astrometry.

Usage: python3 drone_sky_prep.py <image> <YYYY-MM-DD> <HH:MM:SS> <tilt> <azimuth> [fov]
                                 [--prior-lat LAT] [--prior-lon LON]

  tilt    = camera degrees above horizon (90=straight up, 0=horizontal)
  azimuth = compass direction (0=N, 90=E, 180=S, 270=W)
  fov     = horizontal field of view in degrees (optional, makes solving faster)
  --prior-lat/--prior-lon = approximate position (operating area). One sky
            direction is consistent with TWO positions in general; without a
            prior that separates them, no position is reported.
  --up-cam ux,uy,uz = 'up' in the camera's optical frame (x right, y down the
            image, z along the axis), from the vehicle IMU's roll/pitch and the
            camera's full mounting (B11). The position then comes from the plate
            solve's whole camera rotation: one answer, no compass, no prior;
            tilt/azimuth are only reported (pass nan nan when unknown).

Examples:
  python3 drone_sky_prep.py ~/Images/Tsky.jpeg 2026-03-10 20:20:00 75.46 283.18
  python3 drone_sky_prep.py ~/Images/Tsky.jpeg 2026-03-10 20:20:00 75.46 283.18 55.89
"""

import sys
import os
import re
import time
import shutil
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from celestial_math import (apparent_radec, camera_rotation_from_wcs,  # noqa: E402
                            choose_candidate, gast_deg, observer_candidates, zenith_fix)


def _pop_flag(name):
    """Remove `name VALUE` from sys.argv and return VALUE as float (or None)."""
    if name in sys.argv:
        i = sys.argv.index(name)
        val = float(sys.argv[i + 1])
        del sys.argv[i:i + 2]
        return val
    return None


def _pop_vec(name):
    """Remove `name X,Y,Z` from sys.argv and return the three floats (or None)."""
    if name in sys.argv:
        i = sys.argv.index(name)
        val = [float(v) for v in sys.argv[i + 1].split(",")]
        del sys.argv[i:i + 2]
        if len(val) != 3:
            print(f"ERROR: {name} needs three comma-separated numbers")
            sys.exit(2)
        return val
    return None


PRIOR_LAT = _pop_flag("--prior-lat")
PRIOR_LON = _pop_flag("--prior-lon")
UP_CAM = _pop_vec("--up-cam")

# ── Arguments ──────────────────────────────────────────────
if len(sys.argv) < 4:
    print("Usage: python3 drone_sky_prep.py <image> <YYYY-MM-DD> <HH:MM:SS> <tilt> <azimuth> [fov]"
          " [--prior-lat LAT] [--prior-lon LON]")
    sys.exit(1)

IMAGE = sys.argv[1]
DATE_STR = sys.argv[2]
TIME_STR = sys.argv[3]

# Parse remaining arguments: [tilt, az] or [tilt, az, fov]
TILT_IN = None
AZ_IN = None
FOV_IN = None

remaining = sys.argv[4:]
if len(remaining) < 2:
    # The former "auto" mode guessed tilt from a self-consistency scan and
    # azimuth from the image rotation plus a fixed 313.18° offset tuned on one
    # sample: not valid for any other camera mounting. Attitude must be measured.
    print("ERROR: tilt and azimuth are required (from the IMU); auto mode is not supported.")
    sys.exit(2)
elif len(remaining) == 2:
    TILT_IN, AZ_IN = float(remaining[0]), float(remaining[1])
elif len(remaining) >= 3:
    TILT_IN, AZ_IN = float(remaining[0]), float(remaining[1])
    FOV_IN = float(remaining[2])

if not os.path.exists(IMAGE):
    print(f"ERROR: File not found: {IMAGE}")
    sys.exit(1)

try:
    hh, mm, ss = [int(x) for x in TIME_STR.split(":")]
except Exception:
    print("ERROR: Bad time format. Use HH:MM:SS")
    sys.exit(1)

UTC_TIME = f"{DATE_STR} {hh:02d}:{mm:02d}:{ss:02d}"
BASE = Path(IMAGE).stem
OUTDIR = Path(IMAGE).parent
TIF_OUT = str(OUTDIR / f"{BASE}_siril.tif")
WCS_FILE = str(OUTDIR / f"{BASE}_siril.wcs")
# Work files live next to the image (the caller's temporary directory), so
# nothing is left behind in /tmp, whatever happens.
LOG_FILE = str(OUTDIR / f"{BASE}_solve.log")
SSF_FILE = str(OUTDIR / f"{BASE}.ssf")
SOLVE_FIELD = (os.environ.get("NAVERA_SOLVE_FIELD") or shutil.which("solve-field")
               or "/usr/local/astrometry/bin/solve-field")
SIRIL_TIMEOUT_S = 60
SOLVE_TIMEOUT_S = 240      # > solve-field's own --cpulimit 180

# Scale range for solve-field
if FOV_IN:
    MARGIN = 0.05
    SCALE_LOW = round(FOV_IN * (1 - MARGIN), 2)
    SCALE_HIGH = round(FOV_IN * (1 + MARGIN), 2)
else:
    # Unknown camera: a wide search (slower) rather than a range that silently
    # excludes narrow-FOV star cameras.
    SCALE_LOW = 5
    SCALE_HIGH = 90

print()
print("┌─────────────────────────────────────────────┐")
print("│         DRONE SKY POSITION SOLVER           │")
print("├─────────────────────────────────────────────┤")
print(f"│  Image    : {Path(IMAGE).name}")
print(f"│  UTC time : {UTC_TIME}")
print(f"│  Tilt     : {TILT_IN}°")
print(f"│  Azimuth  : {AZ_IN}°")
if FOV_IN:
    print(f"│  FOV      : {FOV_IN}°  → scale {SCALE_LOW}–{SCALE_HIGH}° (faster!)")
else:
    print(f"│  FOV      : unknown → scale {SCALE_LOW}–{SCALE_HIGH}° (wide search)")
print("│  Please wait...")
print("└─────────────────────────────────────────────┘")
print()

T_START = time.time()

# ─────────────────────────────────────────────────────────
# STEP 1 — Preprocess with Siril
# ─────────────────────────────────────────────────────────
print("  [1/4] Preprocessing with Siril...")

with open(SSF_FILE, "w") as f:
    f.write("requires 1.2.0\n")
    f.write(f"load {IMAGE}\n")
    f.write("subsky -rbf\n")
    f.write(f"savetif {BASE}_siril\n")

try:
    subprocess.run(["siril", "-s", SSF_FILE], capture_output=True, cwd=str(OUTDIR),
                   timeout=SIRIL_TIMEOUT_S)
except FileNotFoundError:
    print("  siril not installed — using PIL fallback")
except subprocess.TimeoutExpired:
    print(f"  siril timed out after {SIRIL_TIMEOUT_S}s — using PIL fallback")
if os.path.exists(SSF_FILE):
    os.remove(SSF_FILE)

if not os.path.exists(TIF_OUT):
    if not os.path.exists(TIF_OUT):
        print("  Siril fallback — converting JPEG to TIF...")
        from PIL import Image as _PILImg
        _PILImg.open(IMAGE).save(TIF_OUT)
print(f"  TIF created: {TIF_OUT}")

# ─────────────────────────────────────────────────────────
# STEP 2 — Run solve-field
# ─────────────────────────────────────────────────────────
print(f"  [2/4] Running astrometry (scale {SCALE_LOW}–{SCALE_HIGH}°)...")

T_SOLVE_START = time.time()
with open(LOG_FILE, "w") as log:
    # $NAVERA_ASTROMETRY_CFG points at another index location (e.g. index files
    # on the data disk); default: the packaged config (/usr/share/astrometry).
    _ASTROMETRY_CFG = os.environ.get("NAVERA_ASTROMETRY_CFG") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "astrometry.cfg")
    try:
        subprocess.run([
            SOLVE_FIELD, TIF_OUT,
            "--config", _ASTROMETRY_CFG,
            # no --resort: re-sorting the detected stars made the fit land 46
            # arcmin off (reproducible) instead of 2.9 on the same frame.
            "--overwrite", "--no-plots", "--no-verify",
            "--wcs", WCS_FILE,
            "--scale-units", "degwidth",
            "--scale-low",   str(SCALE_LOW),
            "--scale-high",  str(SCALE_HIGH),
            # The boresight is read at the image centre: anchor the fit there and
            # fit the wide-field distortion (4th order). With the defaults the
            # fit was anchored near an edge and the centre came out ~1° off
            # (111 km); anchored + order 4: 2.9 arcmin on a 60° field.
            "--crpix-center", "--tweak-order", "4",
            "--downsample",  "1",
            "--objs",        "400",
            "--cpulimit",    "180",
            # astrometry.net's Python helpers for these two steps use np.bool,
            # gone from the NumPy NAVERA runs (1.26): "removelines" then fails
            # and nothing is solved. A star-camera frame needs neither.
            "--no-remove-lines", "--uniformize", "0",
        ], stdout=log, stderr=log, cwd=str(OUTDIR), timeout=SOLVE_TIMEOUT_S)
    except FileNotFoundError:
        print(f"  ERROR: solve-field not found ({SOLVE_FIELD}); install astrometry.net")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"  ERROR: solve-field timed out after {SOLVE_TIMEOUT_S}s")
        sys.exit(1)
T_SOLVE = time.time() - T_SOLVE_START

with open(LOG_FILE, "r") as f:
    solve_output = f.read()
os.remove(LOG_FILE)

RA, DEC, ROTATION, LOG_ODDS = None, None, None, None
for line in solve_output.splitlines():
    if LOG_ODDS is None and "log-odds ratio" in line:
        m = re.search(r'log-odds ratio\s+([-+]?\d+\.?\d*)', line)
        if m:
            LOG_ODDS = float(m.group(1))
    if "Field center:" in line and "RA,Dec" in line:
        m = re.search(r'RA,Dec\) = \(([^,]+),\s*([^)]+)\)', line)
        if m:
            RA = float(m.group(1))
            DEC = float(m.group(2))
    if "Field rotation angle:" in line:
        m = re.search(r'up is ([+-]?\d+\.?\d*)', line)
        if m:
            ROTATION = float(m.group(1))

# The solution file gives the direction of the exact image centre (the log's
# "Field center" line is kept only as a fallback).
_h = None
if os.path.exists(WCS_FILE):
    try:
        from astropy.io import fits as _fits
        from astropy.wcs import WCS as _WCS
        _h = _fits.getheader(WCS_FILE)
        _c = _WCS(_h).pixel_to_world((_h["IMAGEW"] - 1) / 2.0, (_h["IMAGEH"] - 1) / 2.0)
        RA, DEC = float(_c.ra.deg), float(_c.dec.deg)
        # the plate scale the stars gave: the star camera's field width, measured (solve-field's
        # degwidth: scale x width) — the celestial node keeps it for this camera (no lens needed)
        _cd = abs(float(_h.get("CD1_1", 0.0)) * float(_h.get("CD2_2", 0.0))
                  - float(_h.get("CD1_2", 0.0)) * float(_h.get("CD2_1", 0.0))) ** 0.5
        FIELD_WIDTH = _cd * float(_h["IMAGEW"]) if _cd > 0 else None
    except Exception as _e:                  # noqa: BLE001 — fall back to the log
        print(f"  WCS read failed ({_e}); using the solver's reported field centre")

if RA is None or DEC is None:
    print("  ERROR: Astrometry could not solve the image.")
    print("  " + "\n  ".join(solve_output.splitlines()[-15:]))
    sys.exit(1)

print(f"  Solved in {T_SOLVE:.1f}s  RA={RA:.4f}°  Dec={DEC:.4f}°  Rotation={ROTATION}°")

# ─────────────────────────────────────────────────────────
# STEP 3 — Position from boresight direction
# ─────────────────────────────────────────────────────────
# astrometry.net reports ICRS (J2000); sidereal time is apparent-of-date, so
# precess/nutate the field centre to the true equator & equinox of date first.
print("  [3/4] Converting RA/Dec to the equinox of date...")
RA_APP, DEC_APP = apparent_radec(RA, DEC, UTC_TIME)
GAST = gast_deg(UTC_TIME)
TILT, AZIMUTH, METHOD = TILT_IN, AZ_IN, "IMU"
print(f"  Apparent RA={RA_APP:.4f}°  Dec={DEC_APP:.4f}°  GAST={GAST:.4f}°")

print("  [4/4] Computing position...")
R_ICRS_CAM = None
FIX_METHOD = "boresight"
if UP_CAM is not None:
    # B11: the whole camera rotation from the plate solve + 'up' from the IMU: no compass, one answer
    if _h is None:
        print("  ERROR: no plate solution file (WCS): the compass-free fix needs the camera's rotation")
        sys.exit(1)
    try:
        R_ICRS_CAM = camera_rotation_from_wcs(_h)
    except ValueError as _e:
        print(f"  ERROR: {_e}")
        sys.exit(1)
    result = zenith_fix(R_ICRS_CAM, UP_CAM, UTC_TIME)
    FIX_METHOD = "zenith"
else:
    candidates = observer_candidates(TILT, AZIMUTH, RA_APP, DEC_APP, GAST)
    result = choose_candidate(candidates, PRIOR_LAT, PRIOR_LON)
    if result is None:
        print(f"  ERROR: no unambiguous position. Candidates: {candidates}; "
              f"prior lat={PRIOR_LAT} lon={PRIOR_LON}")
        sys.exit(1)

LAT, LON = result
constellation = "N/A"
T_TOTAL = time.time() - T_START

print()
print("┌─────────────────────────────────────────────┐")
print("│           DRONE POSITION RESULT             │")
print("├─────────────────────────────────────────────┤")
print(f"│  RA              : {RA:.4f}°")
print(f"│  Dec             : {DEC:.4f}°")
print(f"│  Constellation   : {constellation}")
print(f"│  UTC time        : {UTC_TIME}")
print(f"│  Tilt  ({METHOD:6s})   : {TILT:.4f}°")
print(f"│  Azimuth ({METHOD:6s}) : {AZIMUTH:.4f}°")
if FOV_IN:
    print(f"│  FOV provided    : {FOV_IN}°")
if globals().get("FIELD_WIDTH"):
    print(f"│  Field width     : {FIELD_WIDTH:.3f}°  (measured from the stars)")
print("├─────────────────────────────────────────────┤")
print(f"│  Log-odds        : {LOG_ODDS}")
_METHOD_TEXT = ("zenith (camera rotation + IMU up, no compass)" if FIX_METHOD == "zenith"
                else "boresight (tilt + compass azimuth)")
print(f"│  Method          : {_METHOD_TEXT}")
if R_ICRS_CAM is not None:
    print("│  R_icrs_cam      : " + ",".join(f"{v:.8f}" for v in R_ICRS_CAM.ravel()))
print(f"│  Latitude        : {LAT:+.6f}°")
print(f"│  Longitude       : {LON:+.6f}°")
print("├─────────────────────────────────────────────┤")
print(f"│  Solve time      : {T_SOLVE:.2f}s  (astrometry only)")
print(f"│  Total time      : {T_TOTAL:.2f}s")
print("└─────────────────────────────────────────────┘")
print()
