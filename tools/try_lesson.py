#!/usr/bin/env python3
"""Test a lesson the way a student would, in a throw-away sandbox.

    tools/try_lesson.py 03-python-basics             # starter files: the check must FAIL
    tools/try_lesson.py 03-python-basics --solution  # solutions/<id>/ copied over: must PASS
    tools/try_lesson.py 03-python-basics --solution --shell "python3 distance.py"

The throw-away student is "_try_<id>" (removed with --clean). Never touches ~/Navera.
A check run is SEALED exactly like the dashboard's (server/sealed.py): check.py and hidden/ stay in the
checker's memory, student code cannot read them, and the result printed at the end
("ACADEMY_RESULT {...}") comes from the checker's private channel — a line the student's code prints
is shown as "(ignored …)". --shell keeps the old mounts (every course folder, read only): a dev tool.
--overlay DIR copies DIR over the lesson folder after --solution (attack tests, variants).
--solution copies solutions/<id>/ with its sub-folders (navera_lite/) over the lesson folder; a
solutions/<id>/_apply.sh is optional (run first when present) and not needed for NAVERA Lite missions.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import config  # noqa: E402
import netns  # noqa: E402
import sandbox  # noqa: E402
import workspaces  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("lesson")
ap.add_argument("--solution", action="store_true")
ap.add_argument("--shell", help="run this command in the lesson folder instead of the check")
ap.add_argument("--resources", default="", help="comma list: sim,camera,sensors (only when free!)")
ap.add_argument("--clean", action="store_true")
ap.add_argument("--fresh", action="store_true", help="with --shell: start again from the starter files")
ap.add_argument("--timeout", type=int, default=600)
ap.add_argument("--overlay", help="a folder copied over the lesson folder (after --solution)")
ap.add_argument("--who", default="", help="a separate throw-away student per tester (e.g. strong, weak, expert): "
                                          "parallel testers of one lesson never share files")
a = ap.parse_args()

lid = a.lesson
if not os.path.isfile(os.path.join(config.COURSES, lid, "meta.json")):
    sys.exit(f"no lesson {lid}")
WHO = {"": 0, "strong": 1, "weak": 2, "expert": 3, "fix": 4}
name = "_try_" + re.sub(r"[^a-z0-9]", "", lid.lower())[:16] + \
       ("_" + re.sub(r"[^a-z0-9]", "", a.who.lower())[:12] if a.who else "")
if a.clean:
    workspaces.delete_student(name)
    print("removed", name)
    sys.exit(0)
workspaces.create_student(name)
# a check run or --solution starts from the starter files; --shell alone keeps the tester's work (like a student)
workspaces.install_lesson(name, lid, overwrite=a.fresh or a.solution or not a.shell)
if a.fresh or a.solution or not a.shell:            # starting again from the starter: forget the stored seal
    import seals  # noqa: E402
    seals.reset(name, lid)
dst = workspaces.lesson_dir(name, lid)
if a.solution:
    sol = os.path.join(config.ACADEMY, "solutions", lid)
    if not os.path.isdir(sol):
        sys.exit(f"no solutions/{lid}/")
    # sub-folders too (navera_lite/ made by tools/lite_build.py); no _apply.sh is needed
    shutil.copytree(sol, dst, dirs_exist_ok=True, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
if a.overlay:
    shutil.copytree(a.overlay, dst, dirs_exist_ok=True, symlinks=True)
mounts = [(os.path.join(config.COURSES, "_lib"), "/academy/lib")] + \
         [(os.path.join(config.COURSES, d), f"/academy/courses/{d}") for d in sorted(os.listdir(config.COURSES))
          if os.path.isfile(os.path.join(config.COURSES, d, "meta.json"))]
pre = ""
if a.solution and os.path.exists(os.path.join(dst, "_apply.sh")):   # optional (older missions only)
    pre = "bash ./_apply.sh && "
domain = config.TEST_DOMAINS[(int(lid[:2]) + 40 * WHO.get(a.who, 0)) % len(config.TEST_DOMAINS)]  # unique per lesson and tester
res = [r for r in a.resources.split(",") if r]
if not a.shell:                          # the check, sealed exactly like the dashboard's
    import sealed  # noqa: E402
    if pre:
        r = subprocess.run(sandbox.bwrap_argv(name, workspaces.student_home(name), 0,
                                              ["bash", "-lc", f"cd ~/lessons/{lid} && {pre[:-4]}"], domain=domain,
                                              extra_ro=sealed.mounts(lid)))    # what a student's terminal sees
    try:
        code, _, score = sealed.run_check(name, lid, 0, timeout=a.timeout, resources=res, heavy=bool(res),
                                          domain=domain, stream=sys.stdout)
    finally:
        netns.release(name)         # its private network: stopped unless a sandbox still uses it
    if code == 124:
        sys.exit(f"TIMEOUT after {a.timeout} s")
    print("ACADEMY_RESULT " + json.dumps(score) if score else "NO RESULT: the checker reported nothing (crash?)")
    sys.exit(0 if sealed.passed(code, score) else 1)
inner = a.shell
# the command goes in a file, not on bash's command line: `pgrep -f <name>` must not find the wrapper itself
with open(os.path.join(workspaces.student_home(name), ".try_cmd.sh"), "w") as f:
    f.write(f"source ~/.bashrc >/dev/null 2>&1\ncd ~/lessons/{lid} || exit 1\n{pre}{inner}\n")
cmd = ["bash", "-l", "/home/student/.try_cmd.sh"]
argv = sandbox.bwrap_argv(name, workspaces.student_home(name), 0, cmd, resources=res, heavy=bool(res),
                          domain=domain, extra_ro=mounts)
try:
    import signal
    r = subprocess.run(argv, timeout=a.timeout, preexec_fn=lambda: [signal.signal(s, signal.SIG_DFL) for s in (signal.SIGINT, signal.SIGTERM)])
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    sys.exit(f"TIMEOUT after {a.timeout} s")
finally:
    netns.release(name)
