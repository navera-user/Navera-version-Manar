import os
import subprocess

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
NAV = os.path.expanduser("~/navera")
LESSON = os.path.dirname(os.path.abspath(__file__))       # /academy/courses/02-terminal
STARTER = os.path.join(LESSON, "files")
PHOTOS = ["frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg"]
LOGS = ["flight_0930.log", "flight_1415.log"]
TMPS = ["cache_01.tmp", "cache_02.tmp", "cache_03.tmp"]


def git_show(path):
    """A file of NAVERA as it was at the start (tag "base"), whatever the student changed since."""
    r = subprocess.run(["git", "-C", NAV, "show", "refs/tags/base:" + path], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout
    with open(os.path.join(NAV, path)) as f:
        return f.read()


def same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def clean_path(v):
    v = str(v).strip().strip("'\"").strip()
    for prefix in ("/home/student/navera/", "~/navera/", "navera/", "./"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v.rstrip("/")


@c.test("the folders mission/photos, mission/logs and mission/docs exist",
        hint="mkdir can make several folders at once, and mkdir -p makes the parent folder too.")
def _():
    for d in ("mission", "mission/photos", "mission/logs", "mission/docs"):
        c.ok(os.path.isdir(d), f"the folder {d} does not exist yet")


@c.test("the 3 photos are in mission/photos",
        hint="One mv with a wildcard moves them all: the pattern *.jpg matches every name that ends in .jpg.")
def _():
    for p in PHOTOS:
        c.ok(os.path.isfile(os.path.join("mission/photos", p)), f"mission/photos/{p} is missing")
        c.ok(same_bytes(os.path.join("mission/photos", p), os.path.join(STARTER, "inbox", p)),
             f"mission/photos/{p} is not the original photo any more")
    c.ok(not any(os.path.exists(os.path.join("inbox", p)) for p in PHOTOS),
         "a photo is still in inbox/ — use mv (move), not cp (copy)")


@c.test("the 2 flight logs are in mission/logs",
        hint="Same idea as the photos, with the pattern *.log.")
def _():
    for p in LOGS:
        c.ok(os.path.isfile(os.path.join("mission/logs", p)), f"mission/logs/{p} is missing")
        c.ok(same_bytes(os.path.join("mission/logs", p), os.path.join(STARTER, "inbox", p)),
             f"mission/logs/{p} was changed — it should be the original log")
    c.ok(not any(os.path.exists(os.path.join("inbox", p)) for p in LOGS),
         "a log is still in inbox/ — use mv, not cp")


@c.test("the pilot's notes are mission/docs/notes.txt",
        hint="mv can move AND rename in one go: mv old_place/old_name new_place/new_name")
def _():
    c.ok(os.path.isfile("mission/docs/notes.txt"), "mission/docs/notes.txt does not exist yet")
    with open("mission/docs/notes.txt", "rb") as f, open(os.path.join(STARTER, "inbox", "notes_for_pilot.txt"), "rb") as g:
        c.ok(f.read().startswith(g.read()), "mission/docs/notes.txt is not the pilot's notes file")
    c.ok(not os.path.exists("inbox/notes_for_pilot.txt"), "inbox/notes_for_pilot.txt is still there")
    c.ok(not os.path.exists("mission/docs/notes_for_pilot.txt"),
         "the notes are in mission/docs but still called notes_for_pilot.txt — rename them notes.txt")


@c.test("the .tmp files and the inbox folder are deleted",
        hint="First look with ls inbox/*.tmp, then delete with rm. An EMPTY folder is removed with rmdir.")
def _():
    left = [t for t in TMPS if os.path.exists(os.path.join("inbox", t))]
    c.ok(not left, "still in inbox/: " + ", ".join(left))
    c.ok(not os.path.exists("inbox"), "the folder inbox still exists — when it is empty, remove it with rmdir inbox")


@c.test("a copy of gps_params.yaml is in mission/docs",
        hint="Find it with find ~/navera -name gps_params.yaml, then cp <that path> mission/docs/")
def _():
    dst = "mission/docs/gps_params.yaml"
    c.ok(os.path.isfile(dst), f"{dst} does not exist yet")
    with open(dst) as f:
        c.ok(f.read() == git_show("gps_pkg/gps_pkg/config/gps_params.yaml"),
             f"{dst} is not an exact copy of NAVERA's file")
    c.ok(os.path.isfile(os.path.join(NAV, "gps_pkg/gps_pkg/config/gps_params.yaml")),
         "the original gps_params.yaml has disappeared from ~/navera — you used mv instead of cp! "
         "Put it back: mv mission/docs/gps_params.yaml ~/navera/gps_pkg/gps_pkg/config/ and copy it again")


@c.test("packages.txt lists the folders of ~/navera (made with >)",
        hint="ls ~/navera > packages.txt   — the > sends what ls prints into the file instead of the screen.")
def _():
    c.file_exists("packages.txt")
    with open("packages.txt") as f:
        lines = [l.strip() for l in f if l.strip()]
    c.ok(lines, "packages.txt is empty")
    for pkg in ("day_pkg", "gps_pkg", "navera_msgs", "night_pkg", "cn_pkg", "navera_estimator"):
        c.ok(pkg in lines, f"{pkg} is not on its own line in packages.txt")
    c.ok(len(lines) >= 30, f"packages.txt has only {len(lines)} lines — it should have one line per name in ~/navera")


@c.test("sources.txt holds the SOURCE_ lines of PositionEstimate.msg (made with grep and >)",
        hint="grep SOURCE_ <path of PositionEstimate.msg> > sources.txt")
def _():
    c.file_exists("sources.txt")
    want = [l.rstrip() for l in git_show("navera_msgs/msg/PositionEstimate.msg").splitlines() if "SOURCE_" in l]
    with open("sources.txt") as f:
        got = [l.rstrip() for l in f if l.strip()]
    # tolerate grep -n ("12:uint8 ...") or a file name prefix
    got = [g.split(":", 1)[1] if ":" in g.split()[0] else g for g in got]
    c.ok(len(got) == len(want), f"sources.txt has {len(got)} lines, expected {len(want)}")
    c.ok(got == want, "the lines of sources.txt are not the SOURCE_ lines of PositionEstimate.msg")


def answer(q):
    (v,) = need(load_student("answers.py"), q)
    return v


def as_int(v, q):
    try:
        return int(str(v).strip())
    except ValueError:
        raise CheckFailed(f"{q} should be a whole number, got {v!r}")


@c.test("Q1: number of .py files in day_pkg",
        hint="ls shows only one folder. find looks inside every sub-folder: find ~/navera/day_pkg -name \"*.py\" | wc -l")
def _():
    names = subprocess.run(["git", "-C", NAV, "ls-tree", "-r", "--name-only", "refs/tags/base", "--", "day_pkg"],
                           capture_output=True, text=True).stdout.split()
    want = sum(n.endswith(".py") for n in names)
    v = as_int(answer("Q1"), "Q1")
    c.ok(v != 0, "Q1 is still 0")
    c.ok(v == want, f"Q1 = {v} is not right (did you count the sub-folders too?)")


@c.test("Q2: where PositionEstimate.msg is",
        hint="find ~/navera -name \"PositionEstimate.msg\" — keep the path that is NOT in build/ or install/, "
             "and write it starting from the package folder.")
def _():
    v = clean_path(answer("Q2"))
    c.ok(v != "", "Q2 is still empty")
    c.ok(not v.startswith(("install/", "build/")), "that is a copy made by the build — give the source file")
    c.eq(v, "navera_msgs/msg/PositionEstimate.msg", "Q2")


@c.test("Q3: number of lines of PositionEstimate.msg", hint="wc -l <the path you found in Q2>")
def _():
    want = len(git_show("navera_msgs/msg/PositionEstimate.msg").splitlines())
    v = as_int(answer("Q3"), "Q3")
    c.ok(v == want, f"Q3 = {v} is not right")


@c.test("Q4: the day_pkg Python file that uses PositionEstimate",
        hint="grep -rl PositionEstimate ~/navera/day_pkg  (-r = in every sub-folder, -l = only the file names)")
def _():
    v = clean_path(answer("Q4"))
    c.ok(v != "", "Q4 is still empty")
    ok = {"day_pkg/day_pkg/nodes/day_subscriber.py"}
    c.ok(v in ok or v == "day_subscriber.py",
         f"Q4 = {v!r} is not right — write the path from the package folder, like day_pkg/.../name.py")


@c.test("Q5: the package that holds nmea.py", hint="find ~/navera -name nmea.py — the first folder of the path is the package.")
def _():
    v = clean_path(answer("Q5")).split("/")[0]
    c.ok(v != "", "Q5 is still empty")
    c.eq(v, "navera_output", "Q5")


@c.test("Q6: lines with GPS LOST in the two logs",
        hint="cat mission/logs/*.log | grep \"GPS LOST\" | wc -l   — the quotes keep the two words together.")
def _():
    want = 0
    for p in LOGS:
        with open(os.path.join(STARTER, "inbox", p)) as f:
            want += sum("GPS LOST" in l for l in f)
    v = as_int(answer("Q6"), "Q6")
    c.ok(v != 0, "Q6 is still 0")
    c.ok(v == want, f"Q6 = {v} is not right — did you count both logs together?")


c.run()
