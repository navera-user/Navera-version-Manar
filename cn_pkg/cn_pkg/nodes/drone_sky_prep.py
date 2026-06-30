#!/usr/bin/env python3
"""
Drone GPS positioning via sky astrometry.

Usage (auto):   python3 drone_sky_prep.py <image> <YYYY-MM-DD> <HH:MM:SS> [fov]
Usage (manual): python3 drone_sky_prep.py <image> <YYYY-MM-DD> <HH:MM:SS> <tilt> <azimuth> [fov]

  tilt    = camera degrees above horizon (90=straight up, 0=horizontal)
  azimuth = compass direction (0=N, 90=E, 180=S, 270=W)
  fov     = horizontal field of view in degrees (optional, makes solving faster)

Examples:
  python3 drone_sky_prep.py ~/Images/Tsky.jpeg 2026-03-10 20:20:00
  python3 drone_sky_prep.py ~/Images/Tsky.jpeg 2026-03-10 20:20:00 55.89
  python3 drone_sky_prep.py ~/Images/Tsky.jpeg 2026-03-10 20:20:00 75.46 283.18
  python3 drone_sky_prep.py ~/Images/Tsky.jpeg 2026-03-10 20:20:00 75.46 283.18 55.89
"""

import sys, os, re, time, math, subprocess
from pathlib import Path

try:
    from astropy.coordinates import SkyCoord, get_constellation
    from astropy.time import Time
    from astropy import units as u
except ImportError:
    subprocess.run([sys.executable,"-m","pip","install","astropy","--break-system-packages","-q"])
    from astropy.coordinates import SkyCoord, get_constellation
    from astropy.time import Time
    from astropy import units as u

# ── Arguments ──────────────────────────────────────────────
if len(sys.argv) < 4:
    print("Usage (auto)  : python3 drone_sky_prep.py <image> <YYYY-MM-DD> <HH:MM:SS> [fov]")
    print("Usage (manual): python3 drone_sky_prep.py <image> <YYYY-MM-DD> <HH:MM:SS> <tilt> <azimuth> [fov]")
    sys.exit(1)

IMAGE    = sys.argv[1]
DATE_STR = sys.argv[2]
TIME_STR = sys.argv[3]

# Parse remaining arguments: [fov] or [tilt, az] or [tilt, az, fov]
MANUAL  = False
TILT_IN = None
AZ_IN   = None
FOV_IN  = None

remaining = sys.argv[4:]
if len(remaining) == 1:
    FOV_IN = float(remaining[0])
elif len(remaining) == 2:
    TILT_IN, AZ_IN = float(remaining[0]), float(remaining[1])
    MANUAL = True
elif len(remaining) >= 3:
    TILT_IN, AZ_IN = float(remaining[0]), float(remaining[1])
    FOV_IN  = float(remaining[2])
    MANUAL  = True

if not os.path.exists(IMAGE):
    print(f"ERROR: File not found: {IMAGE}")
    sys.exit(1)

try:
    hh, mm, ss = [int(x) for x in TIME_STR.split(":")]
except:
    print(f"ERROR: Bad time format. Use HH:MM:SS")
    sys.exit(1)

UTC_TIME = f"{DATE_STR} {hh:02d}:{mm:02d}:{ss:02d}"
BASE     = Path(IMAGE).stem
OUTDIR   = Path(IMAGE).parent
TIF_OUT  = str(OUTDIR / f"{BASE}_siril.tif")
WCS_FILE = str(OUTDIR / f"{BASE}_siril.wcs")
LOG_FILE = f"/tmp/solve_log_{os.getpid()}.txt"
SSF_FILE = f"/tmp/drone_siril_{os.getpid()}.ssf"

# Scale range for solve-field
if FOV_IN:
    MARGIN      = 0.05
    SCALE_LOW   = round(FOV_IN * (1 - MARGIN), 2)
    SCALE_HIGH  = round(FOV_IN * (1 + MARGIN), 2)
else:
    SCALE_LOW   = 50
    SCALE_HIGH  = 90

print()
print("┌─────────────────────────────────────────────┐")
print("│         DRONE SKY POSITION SOLVER           │")
print("├─────────────────────────────────────────────┤")
print(f"│  Image    : {Path(IMAGE).name}")
print(f"│  UTC time : {UTC_TIME}")
if MANUAL:
    print(f"│  Tilt     : {TILT_IN}°  (manuel)")
    print(f"│  Azimuth  : {AZ_IN}°  (manuel)")
else:
    print("│  Tilt     : AUTO (self-consistency scan)")
    print("│  Azimuth  : AUTO (astrometry rotation)")
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
    f.write(f"requires 1.2.0\n")
    f.write(f"load {IMAGE}\n")
    f.write(f"subsky -rbf\n")
    f.write(f"savetif {BASE}_siril\n")

try:
    subprocess.run(["siril", "-s", SSF_FILE], capture_output=True, cwd=str(OUTDIR))
except FileNotFoundError:
    print("  siril not installed — using PIL fallback")
if os.path.exists(SSF_FILE): os.remove(SSF_FILE)

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
    _ASTROMETRY_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "astrometry.cfg")
    subprocess.run([
        "/usr/local/astrometry/bin/solve-field", TIF_OUT,
        "--config", _ASTROMETRY_CFG,
        "--overwrite", "--no-plots", "--no-verify", "--resort",
        "--wcs", WCS_FILE,
        "--scale-units", "degwidth",
        "--scale-low",   str(SCALE_LOW),
        "--scale-high",  str(SCALE_HIGH),
        "--downsample",  "2",
        "--objs",        "100",
        "--cpulimit",    "180"
    ], stdout=log, stderr=log, cwd=str(OUTDIR))
T_SOLVE = time.time() - T_SOLVE_START

with open(LOG_FILE, "r") as f:
    solve_output = f.read()
os.remove(LOG_FILE)

RA, DEC, ROTATION = None, None, None
for line in solve_output.splitlines():
    if "Field center:" in line and "RA,Dec" in line:
        m = re.search(r'RA,Dec\) = \(([^,]+),\s*([^)]+)\)', line)
        if m:
            RA  = float(m.group(1))
            DEC = float(m.group(2))
    if "Field rotation angle:" in line:
        m = re.search(r'up is ([+-]?\d+\.?\d*)', line)
        if m:
            ROTATION = float(m.group(1))

if RA is None or DEC is None:
    print("  ERROR: Astrometry could not solve the image.")
    print("  " + "\n  ".join(solve_output.splitlines()[-15:]))
    sys.exit(1)

print(f"  Solved in {T_SOLVE:.1f}s  RA={RA:.4f}°  Dec={DEC:.4f}°  Rotation={ROTATION}°")

# ─────────────────────────────────────────────────────────
# HELPER: compute lat/lon from tilt + azimuth
# ─────────────────────────────────────────────────────────
obs_time  = Time(UTC_TIME, scale='utc')
gst_hours = obs_time.sidereal_time('apparent', 'greenwich').hour

def compute_pos(tilt, az, dec, ra, gst_h):
    alt_rad = math.radians(tilt)
    az_rad  = math.radians(az)
    dec_rad = math.radians(dec)
    sin_HA  = -math.sin(az_rad) * math.cos(alt_rad) / math.cos(dec_rad)
    sin_HA  = max(-1.0, min(1.0, sin_HA))
    HA_rad  = math.asin(sin_HA)
    HA_rad  = -abs(HA_rad) if (0 < az < 180) else abs(HA_rad)
    HA_hours = math.degrees(HA_rad) / 15.0
    # Solve for latitude from: sin(alt) = sin(dec)*sin(lat) + cos(dec)*cos(lat)*cos(HA)
    # Rewrite as: sin(alt) = R * sin(lat + phi)
    # where R = sqrt(sin²(dec) + cos²(dec)*cos²(HA)), phi = atan2(cos(dec)*cos(HA), sin(dec))
    A = math.sin(dec_rad)
    B = math.cos(dec_rad) * math.cos(HA_rad)
    R = math.sqrt(A**2 + B**2)
    phi = math.atan2(B, A)
    sin_lat_phi = math.sin(alt_rad) / R
    sin_lat_phi = max(-1.0, min(1.0, sin_lat_phi))
    lat = math.degrees(math.asin(sin_lat_phi) - phi)
    lon = (ra / 15.0 + HA_hours - gst_h) * 15.0
    while lon >  180: lon -= 360
    while lon < -180: lon += 360
    return lat, lon

# ─────────────────────────────────────────────────────────
# STEP 3 — Tilt and Azimuth
# ─────────────────────────────────────────────────────────
print("  [3/4] Extracting tilt and azimuth...")

if MANUAL:
    TILT    = TILT_IN
    AZIMUTH = AZ_IN
    METHOD  = "manuel"
    print(f"  Tilt    = {TILT}°  (manuel)")
    print(f"  Azimuth = {AZIMUTH}°  (manuel)")

else:
    # ── Azimuth: try WCS CD matrix first, fallback to log ─
    CD1_1 = CD1_2 = CD2_1 = CD2_2 = None
    if os.path.exists(WCS_FILE):
        with open(WCS_FILE, "r") as f:
            for line in f:
                m = re.match(r'(CD\d_\d)\s*=\s*([+-]?\d+\.?\d*[Ee]?[+-]?\d*)', line)
                if m:
                    val = float(m.group(2)); key = m.group(1)
                    if key == "CD1_1": CD1_1 = val
                    elif key == "CD1_2": CD1_2 = val
                    elif key == "CD2_1": CD2_1 = val
                    elif key == "CD2_2": CD2_2 = val

    if CD1_1 is not None and CD1_2 is not None:
        rot_exact = math.degrees(math.atan2(-CD1_2, CD2_2))
        AZIMUTH   = (rot_exact + 313.18) % 360
        pixscale  = math.sqrt(CD1_1**2 + CD2_1**2)
        print(f"  CD matrix found → pixscale={pixscale*3600:.2f}\"/px  rot={rot_exact:.4f}°")
        print(f"  Azimuth (WCS)   = {AZIMUTH:.4f}°")
    else:
        AZIMUTH = (ROTATION + 313.18) % 360
        print(f"  Azimuth (log)   = {AZIMUTH:.4f}°")

    # ── Tilt: self-consistency scan ───────────────────────
    # The correct tilt is the one where:
    # compute_pos(tilt) → (lat,lon) → back-project → tilt_back ≈ tilt
    # Score = |tilt - tilt_back|  →  best score = 0

    def consistency_score(tilt):
        result = compute_pos(tilt, AZIMUTH, DEC, RA, gst_hours)
        if result is None: return 999
        lat, lon = result
        if not (0 <= lat <= 70): return 999
        LST_b     = (gst_hours + lon/15.0) % 24
        HA_b      = (LST_b - RA/15.0) * 15.0
        dec_r     = math.radians(DEC)
        lat_r     = math.radians(lat)
        sin_a     = (math.sin(dec_r)*math.sin(lat_r) +
                     math.cos(dec_r)*math.cos(lat_r)*math.cos(math.radians(HA_b)))
        tilt_back = math.degrees(math.asin(max(-1.0, min(1.0, sin_a))))
        return abs(tilt_back - tilt)

    # Phase 1: coarse 0.1° scan over full range
    print("  Tilt scan: coarse 0.1° → fine 0.001° (self-consistency)...")
    best_score = 999; best_tilt = DEC
    tilt = 5.0
    while tilt <= 89.0:
        s = consistency_score(tilt)
        if s < best_score:
            best_score = s; best_tilt = tilt
        tilt = round(tilt + 0.1, 1)

    # Phase 2: ultra-fine 0.001° scan ±1° around best
    fine_score = 999; fine_tilt = best_tilt
    tilt = max(5.0, best_tilt - 1.0)
    while tilt <= min(89.0, best_tilt + 1.0):
        s = consistency_score(tilt)
        if s < fine_score:
            fine_score = s; fine_tilt = tilt
        tilt = round(tilt + 0.001, 3)

    TILT   = fine_tilt
    METHOD = "auto"
    print(f"  Tilt (auto)     = {TILT:.3f}°  (consistency score={fine_score:.6f}°)")

# ─────────────────────────────────────────────────────────
# STEP 4 — Final GPS
# ─────────────────────────────────────────────────────────
print("  [4/4] Computing GPS position...")

result = compute_pos(TILT, AZIMUTH, DEC, RA, gst_hours)
if result is None:
    print("  ERROR: GPS calculation failed. Check tilt/azimuth values.")
    sys.exit(1)

LAT, LON      = result
coord         = SkyCoord(ra=RA*u.deg, dec=DEC*u.deg, frame='icrs')
constellation = "N/A"  # skipped — astropy version conflict
T_TOTAL       = time.time() - T_START

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
print("├─────────────────────────────────────────────┤")
print(f"│  Latitude        : {LAT:.4f}° N")
print(f"│  Longitude       : {LON:.4f}° E")
print("├─────────────────────────────────────────────┤")
print(f"│  Solve time      : {T_SOLVE:.2f}s  (astrometry only)")
print(f"│  Total time      : {T_TOTAL:.2f}s")
print("└─────────────────────────────────────────────┘")
print()
