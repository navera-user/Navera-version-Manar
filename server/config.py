"""NAVERA Academy — where everything lives on this Jetson.

Nothing here ever writes to the real NAVERA repository (REAL_REPO): the base is a
read-only snapshot taken from one of its commits with `git archive`.
"""
import os

HOME = os.path.expanduser("~")
ACADEMY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REAL_REPO = os.path.join(HOME, "Navera")              # read only, never modified
BASE = os.path.join(ACADEMY, "base")                  # the students' starting point (git, tag "base")
COURSES = os.path.join(ACADEMY, "courses")            # NN-slug/{lesson.md, lab.md, files/, check.py, meta.json}
STUDENTS = os.path.join(ACADEMY, "students")          # <name>/home  (mounted as /home/student)
STATE = os.path.join(ACADEMY, "state")                # users.json, progress.json, bookings.json
LOGS = os.path.join(ACADEMY, "logs")

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
OSM_MAP = os.path.expanduser("~/academy-data/osm_sousse.mbtiles")


def navera_allowed(name):
    """Real NAVERA (its code, its workspace, running it) is not part of the course: staff only, and the
    students a teacher grants it to ("navera_access" in users.json)."""
    import json
    try:
        with open(os.path.join(STATE, "users.json")) as f:
            u = json.load(f).get(name)
    except (OSError, ValueError):
        return False
    return bool(u) and u.get("status", "active") == "active" and (u.get("role") in ("teacher", "admin")
                                                                  or bool(u.get("navera_access")))


def data_mounts(navera=True):
    """navera=False (a student without NAVERA access): only the course's data — the map and
    /data/academy. NAVERA's own data, the ArduPilot build, the star catalogue of NAVERA's simulator and
    astrometry.net stay with staff and students given access (mission 26 ships its own catalogue)."""
    m = []
    def add(host, inside):
        host = os.path.realpath(os.path.expanduser(host))
        if os.path.exists(host):
            m.append((host, inside))
    if navera:                       # NAVERA_WORKSPACE holds NAVERA code: never for a student without access
        add("~/navera_data", S_DATA + "/navera_data")
    add(OSM_MAP, S_DATA + "/map.mbtiles")           # OpenStreetMap, rendered by datasets/_map
    if navera:
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


PYTHON_USER_SITE = os.path.join(HOME, ".local", "lib")   # pip --user packages (torch, cv2 extras…)

PORT = int(os.environ.get("ACADEMY_PORT", "8300"))
MEMORY_MAX = os.environ.get("ACADEMY_MEMORY_MAX", "1800M")   # per student sandbox
HEAVY_MEMORY_MAX = os.environ.get("ACADEMY_HEAVY_MEMORY_MAX", "4500M")  # holder of the simulator
PIDS_MAX = 400
# ROS domains in the range ROS documents as safe on Linux (1–101), without NAVERA's own 77–79.
STUDENT_DOMAINS = [d for d in range(1, 102) if d not in (77, 78, 79)]
TEST_DOMAINS = list(range(215, 233))     # tools/try_lesson.py: inside ROS 2's safe range on Linux (0-101, 215-232)


def domain_for(index):
    return STUDENT_DOMAINS[index % len(STUDENT_DOMAINS)]

# Exclusive resources a student books from the dashboard.
RESOURCES = {
    # the full simulator (real ArduPilot): teacher only — students fly Sim Lite in their browser, no booking
    "sim": {"title": "Full mission simulator (ports 8181, 8190, SITL)", "ports": [8181, 8190, 8443, 5760, 5762],
            "teacher_only": True},
    "camera": {"title": "Insta360 camera (/dev/video*)", "devices": ["/dev/video0", "/dev/video1",
                                                                      "/dev/v4l"]},
    "sensors": {"title": "IMU / RTC / serial GPS (I2C, ttyTHS)", "devices": ["/dev/i2c-1", "/dev/i2c-7",
                                                                              "/dev/ttyTHS1", "/dev/ttyTHS2"]},
}
