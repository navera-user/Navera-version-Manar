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
def data_mounts():
    m = []
    def add(host, inside):
        host = os.path.realpath(os.path.expanduser(host))
        if os.path.exists(host):
            m.append((host, inside))
    add("~/navera_data", S_DATA + "/navera_data")
    add("~/navera_data_map.mbtiles", S_DATA + "/map.mbtiles")
    add("~/ardupilot", S_DATA + "/ardupilot")
    add("~/.navera_sim/bsc5.dat", S_DATA + "/bsc5.dat")
    # astrometry.net was unpacked without root; its scripts hold absolute paths.
    astro = os.path.join(HOME, ".navera_sim", "astrometry")
    if os.path.isdir(astro):
        m.append((astro, astro))
        m.append((astro, S_HOME + "/.navera_sim/astrometry"))
    add(os.path.join(ACADEMY, "datasets"), S_DATA + "/academy")
    return m

PYTHON_USER_SITE = os.path.join(HOME, ".local", "lib")   # pip --user packages (torch, cv2 extras…)

PORT = int(os.environ.get("ACADEMY_PORT", "8300"))
MEMORY_MAX = os.environ.get("ACADEMY_MEMORY_MAX", "1800M")   # per student sandbox
HEAVY_MEMORY_MAX = os.environ.get("ACADEMY_HEAVY_MEMORY_MAX", "4500M")  # holder of the simulator
PIDS_MAX = 400
# ROS domains in the range ROS documents as safe on Linux (1–101), without NAVERA's own 77–79.
STUDENT_DOMAINS = [d for d in range(1, 102) if d not in (77, 78, 79)]
TEST_DOMAINS = list(range(215, 233))     # tools/try_lesson.py


def domain_for(index):
    return STUDENT_DOMAINS[index % len(STUDENT_DOMAINS)]

# Exclusive resources a student books from the dashboard.
RESOURCES = {
    "sim": {"title": "Mission simulator (ports 8181, 8190, SITL)", "ports": [8181, 8190, 8443, 5760, 5762]},
    "camera": {"title": "Insta360 camera (/dev/video*)", "devices": ["/dev/video0", "/dev/video1",
                                                                      "/dev/v4l"]},
    "sensors": {"title": "IMU / RTC / serial GPS (I2C, ttyTHS)", "devices": ["/dev/i2c-1", "/dev/i2c-7",
                                                                              "/dev/ttyTHS1", "/dev/ttyTHS2"]},
}
