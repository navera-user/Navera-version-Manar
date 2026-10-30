"""NAVERA Academy — where everything lives on this Jetson.

Nothing here ever writes to the real NAVERA repository (REAL_REPO): the base is a
read-only snapshot taken from one of its commits with `git archive`.
"""
import os

HOME = os.path.expanduser("~")
ACADEMY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Product box (deploy/install_academy.sh): code read only in /opt/navera-academy, everything that changes in
# ACADEMY_VAR (/var/lib/navera-academy), the service runs as the system user "academy". Dev: all under the checkout.
PRODUCT = os.environ.get("ACADEMY_PRODUCT", "0") == "1"
VAR = os.environ.get("ACADEMY_VAR") or ACADEMY
DATA_DIR = os.environ.get("ACADEMY_DATA") or (os.path.join(VAR, "data") if PRODUCT else os.path.expanduser("~/academy-data"))

REAL_REPO = os.environ.get("ACADEMY_NAVERA_REPO") or os.path.join(HOME, "Navera")   # read only, never modified
BASE = os.path.join(VAR, "base")                      # the students' starting point (git, tag "base"); optional on the box
COURSES = os.path.join(ACADEMY, "courses")            # NN-slug/{lesson.md, lab.md, files/, check.py, meta.json}
STUDENTS = os.path.join(VAR, "students")              # <name>/home  (mounted as /home/student)
STATE = os.path.join(VAR, "state")                    # users.json, progress.json, bookings.json
# GPU slots shared by every sandbox (lock files): at most GPU_SLOTS trainings on the GPU at once
# (one training ≈ 1.2 GB on top of ≈ 2.7 GB used by the system, 7.6 GB in all; measured 2026-10-15).
GPU_SLOT_DIR = os.path.join(STATE, "gpu_slots")
GPU_SLOTS = int(os.environ.get("ACADEMY_GPU_SLOTS_N", "1" if PRODUCT else "3"))   # box: one training at a time
S_GPU_SLOTS = "/run/academy_gpu"
LOGS = os.path.join(VAR, "logs")

# Paths of NAVERA left out of the students' copy (personal paths / old experiments).
BASE_EXCLUDE = ("archive/", "vision_pkg/")
# Packages built in the students' copy.
BUILD_PACKAGES = ("navera_msgs", "navera_common", "camera_pkg", "cn_pkg", "day_pkg", "gps_pkg",
                  "imu_pkg", "navera_estimator", "navera_output", "night_pkg", "rtc_pkg",
                  "simulation_web")

# Inside every sandbox.
S_HOME = "/home/student"
S_NAVERA = S_HOME + "/navera"
S_LESSONS = S_HOME + "/lessons"
S_DATA = "/data"

# Read-only data shared with the sandboxes: (host path, sandbox path).
# The course's map: OpenStreetMap data rendered by datasets/_map/make_map.sh (© OpenStreetMap contributors).
OSM_MAP = os.path.join(DATA_DIR, "osm_sousse.mbtiles")
# Pretrained models given as data (third-party, e.g. DINOv2 ViT-S/14, Apache-2.0): never NAVERA code.
MODELS = os.path.join(DATA_DIR, "models")


def navera_allowed(name):
    """Real NAVERA (its code, its workspace, running it) is not part of the course. On the NAVERA box (PRODUCT):
    nobody, ever: the Academy is simulation only. Dev checkout: staff only."""
    if PRODUCT:
        return False
    import json
    try:
        with open(os.path.join(STATE, "users.json")) as f:
            u = json.load(f).get(name)
    except (OSError, ValueError):
        return False
    return bool(u) and u.get("status", "active") == "active" and u.get("role") in ("teacher", "admin")


def data_mounts(navera=True):
    """navera=False (a student without NAVERA access): only the course's data — the map and
    /data/academy. NAVERA's own data, the ArduPilot build, the star catalogue of NAVERA's simulator and
    astrometry.net stay with staff and students given access (mission 26 ships its own catalogue)."""
    m = []
    def add(host, inside):
        host = os.path.realpath(os.path.expanduser(host))
        if os.path.exists(host):
            m.append((host, inside))
    if navera and not PRODUCT:       # NAVERA_WORKSPACE holds NAVERA code: never for a student without access
        add("~/navera_data", S_DATA + "/navera_data")
    add(OSM_MAP, S_DATA + "/map.mbtiles")           # OpenStreetMap, rendered by datasets/_map
    add(MODELS, S_DATA + "/models")                 # pretrained models (design §7.5)
    if navera and not PRODUCT:       # dev only: on the box NAVERA's own files belong to NAVERA
        add("~/ardupilot", S_DATA + "/ardupilot")
        add("~/.navera_sim/bsc5.dat", S_DATA + "/bsc5.dat")
        # astrometry.net was unpacked without root; its scripts hold absolute paths.
        astro = os.path.join(HOME, ".navera_sim", "astrometry")
        if os.path.isdir(astro):
            m.append((astro, astro))
            m.append((astro, S_HOME + "/.navera_sim/astrometry"))
    add(os.path.join(ACADEMY, "datasets"), S_DATA + "/academy")
    return m

def missing_data():
    """The external data the missions need (on the ADATA disk) that is not reachable right now: the map
    only (NAVERA's own data is not part of the course)."""
    need = {OSM_MAP: "the OpenStreetMap map of Sousse (missions 7, 8, 18, 21–24 and Sim Lite)"}
    return [{"path": p, "what": w, "target": os.path.realpath(os.path.expanduser(p))}
            for p, w in need.items() if not os.path.exists(os.path.realpath(os.path.expanduser(p)))]


# pip --user packages (flask, torch, cv2 extras…): on the box a copy under /opt/navera-academy/pyuser
PYTHON_USER_BASE = os.environ.get("ACADEMY_PYTHONUSERBASE") or os.path.join(HOME, ".local")
PYTHON_USER_SITE = os.path.join(PYTHON_USER_BASE, "lib")

PORT = int(os.environ.get("ACADEMY_PORT", "8300"))
# per student sandbox. On the Jetson, GPU memory counts against it: one GPU training (missions 21–25) peaks at
# 1.6–1.8 GB (measured 2026-10-15), so 1800M left no margin. At most GPU_SLOTS trainings run at once (below).
MEMORY_MAX = os.environ.get("ACADEMY_MEMORY_MAX", "2600M")
HEAVY_MEMORY_MAX = os.environ.get("ACADEMY_HEAVY_MEMORY_MAX", "4500M")  # holder of the simulator
PIDS_MAX = 400
# ROS domains in the range ROS documents as safe on Linux (1–101), without NAVERA's own 77–79.
STUDENT_DOMAINS = [d for d in range(1, 102) if d not in (77, 78, 79)]
TEST_DOMAINS = list(range(215, 233))     # tools/try_lesson.py: inside ROS 2's safe range on Linux (0-101, 215-232)


def domain_for(index):
    return STUDENT_DOMAINS[index % len(STUDENT_DOMAINS)]

# Exclusive resources a student books from the dashboard.
RESOURCES_DEV = {
    # the full simulator (real ArduPilot): teacher only — students fly Sim Lite in their browser, no booking
    "sim": {"title": "Full mission simulator (ports 8181, 8190, SITL)", "ports": [8181, 8190, 8443, 5760, 5762],
            "teacher_only": True},
    "camera": {"title": "Insta360 camera (/dev/video*)", "devices": ["/dev/video0", "/dev/video1",
                                                                      "/dev/v4l"]},
    "sensors": {"title": "IMU / RTC / serial GPS (I2C, ttyTHS)", "devices": ["/dev/i2c-1", "/dev/i2c-7",
                                                                              "/dev/ttyTHS1", "/dev/ttyTHS2"]},
}

# On the NAVERA box the camera, the sensors and NAVERA's simulator ports belong to NAVERA (flight safety first):
# nothing to book there.
RESOURCES = {} if PRODUCT else RESOURCES_DEV

# NAVERA's web bridge on the same box: GPU training and Sim Lite are refused while NAVERA flies (flightgate.py).
NAVERA_STATE_URL = os.environ.get("ACADEMY_NAVERA_STATE_URL", "http://127.0.0.1:8181/api/mission/state")
# Product (ACADEMY_PRODUCT=1): always on, cannot be switched off. Dev checkout: off unless ACADEMY_FLIGHT_GATE=on.
FLIGHT_GATE = PRODUCT or os.environ.get("ACADEMY_FLIGHT_GATE", "off") == "on"
