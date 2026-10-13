#!/usr/bin/env python3
"""Test a lesson the way a student would, in a throw-away sandbox.

    tools/try_lesson.py 03-python-basics             # starter files: the check must FAIL
    tools/try_lesson.py 03-python-basics --solution  # solutions/<id>/ copied over: must PASS
    tools/try_lesson.py 03-python-basics --solution --shell "python3 distance.py"

The throw-away student is "_try_<id>" (removed with --clean). Never touches ~/Navera.
--solution copies solutions/<id>/ with its sub-folders (navera_lite/) over the lesson folder; a
solutions/<id>/_apply.sh is optional (run first when present) and not needed for NAVERA Lite missions.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import config  # noqa: E402
import sandbox  # noqa: E402
import workspaces  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("lesson")
ap.add_argument("--solution", action="store_true")
ap.add_argument("--shell", help="run this command in the lesson folder instead of the check")
ap.add_argument("--resources", default="", help="comma list: sim,camera,sensors (only when free!)")
ap.add_argument("--clean", action="store_true")
ap.add_argument("--timeout", type=int, default=600)
a = ap.parse_args()

lid = a.lesson
if not os.path.isfile(os.path.join(config.COURSES, lid, "meta.json")):
    sys.exit(f"no lesson {lid}")
name = "_try_" + re.sub(r"[^a-z0-9]", "", lid.lower())[:16]
if a.clean:
    workspaces.delete_student(name)
    print("removed", name)
    sys.exit(0)
workspaces.create_student(name)
workspaces.install_lesson(name, lid, overwrite=True)
dst = workspaces.lesson_dir(name, lid)
if a.solution:
    sol = os.path.join(config.ACADEMY, "solutions", lid)
    if not os.path.isdir(sol):
        sys.exit(f"no solutions/{lid}/")
    # sub-folders too (navera_lite/ made by tools/lite_build.py); no _apply.sh is needed
    shutil.copytree(sol, dst, dirs_exist_ok=True, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
mounts = [(os.path.join(config.COURSES, "_lib"), "/academy/lib")] + \
         [(os.path.join(config.COURSES, d), f"/academy/courses/{d}") for d in sorted(os.listdir(config.COURSES))
          if os.path.isfile(os.path.join(config.COURSES, d, "meta.json"))]
pre = ""
if a.solution and os.path.exists(os.path.join(dst, "_apply.sh")):   # optional (older missions only)
    pre = "bash ./_apply.sh && "
inner = a.shell or f"PYTHONPATH=/academy/lib:$PYTHONPATH python3 /academy/courses/{lid}/check.py"
cmd = ["bash", "-lc", f"source ~/.bashrc >/dev/null 2>&1; cd ~/lessons/{lid} && {pre}{inner}"]
res = [r for r in a.resources.split(",") if r]
argv = sandbox.bwrap_argv(name, workspaces.student_home(name), 0, cmd, resources=res, heavy=bool(res),
                          domain=config.TEST_DOMAINS[int(lid[:2]) % len(config.TEST_DOMAINS)],  # 200 + NN, unique per lesson
                          extra_ro=mounts)
try:
    import signal
    r = subprocess.run(argv, timeout=a.timeout, preexec_fn=lambda: [signal.signal(s, signal.SIG_DFL) for s in (signal.SIGINT, signal.SIGTERM)])
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    sys.exit(f"TIMEOUT after {a.timeout} s")
