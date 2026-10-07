#!/usr/bin/env python3
"""Run a command in a REAL student's sandbox, like the dashboard terminal does.

    tools/student_shell.py <student> <lesson-id> "python3 hello_navera.py"
    tools/student_shell.py <student> <lesson-id> --check     # same as the "Check my work" button

Unlike try_lesson.py, the student's files are kept between calls (the lesson files are
installed once, never reset). --check records progress like the dashboard.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import config  # noqa: E402
import sandbox  # noqa: E402
import workspaces  # noqa: E402

if len(sys.argv) < 4:
    sys.exit(__doc__)
name, lid, cmd = sys.argv[1], sys.argv[2], sys.argv[3]
users = json.load(open(os.path.join(config.STATE, "users.json")))
if name not in users:
    sys.exit(f"no student {name}")
if not os.path.isfile(os.path.join(config.COURSES, lid, "meta.json")):
    sys.exit(f"no lesson {lid}")
workspaces.create_student(name)
workspaces.install_lesson(name, lid)
mounts = [(os.path.join(config.COURSES, "_lib"), "/academy/lib")] + \
         [(os.path.join(config.COURSES, d), f"/academy/courses/{d}") for d in sorted(os.listdir(config.COURSES))
          if os.path.isfile(os.path.join(config.COURSES, d, "meta.json"))]
check = cmd == "--check"
inner = (f"PYTHONPATH=/academy/lib:$PYTHONPATH python3 /academy/courses/{lid}/check.py" if check else cmd)
argv = sandbox.bwrap_argv(name, workspaces.student_home(name), users[name]["index"],
                          ["bash", "-lc", f"source ~/.bashrc >/dev/null 2>&1; cd ~/lessons/{lid} && {inner}"],
                          extra_ro=mounts)
reset = lambda: [signal.signal(s, signal.SIG_DFL) for s in (signal.SIGINT, signal.SIGTERM)]
try:
    r = subprocess.run(argv, text=True, capture_output=True, timeout=600, preexec_fn=reset)
    out, code = r.stdout + r.stderr, r.returncode
except subprocess.TimeoutExpired:
    out, code = "⏱ stopped after 600 s", 124
if check:
    m = re.findall(r"^ACADEMY_RESULT (\{.*\})$", out, re.M)
    score = json.loads(m[-1]) if m else None
    out = re.sub(r"^ACADEMY_RESULT .*\n?", "", out, flags=re.M)
    passed = code == 0 and (score is None or score["passed"] == score["total"])
    p = os.path.join(config.STATE, "progress.json")
    prog = json.load(open(p)) if os.path.exists(p) else {}
    rec = prog.setdefault(name, {}).setdefault(lid, {})
    rec["attempts"] = rec.get("attempts", 0) + 1
    rec["last"] = time.strftime("%Y-%m-%d %H:%M")
    if score:
        rec["best"] = max(rec.get("best", 0), score["passed"]); rec["total"] = score["total"]
    if passed:
        rec["status"] = "passed"; rec.setdefault("passed_at", rec["last"])
    elif rec.get("status") != "passed":
        rec["status"] = "started"
    tmp = p + ".tmp"; json.dump(prog, open(tmp, "w"), indent=1); os.replace(tmp, p)
print(out, end="")
sys.exit(code)
