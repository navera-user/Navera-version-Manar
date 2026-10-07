# NAVERA Academy

A 30-lesson course (course + detailed lab each) that teaches beginners how NAVERA works, in a web
dashboard in the style of The Construct: the lesson on the left; a code editor, terminals, the
mission simulator and the operator view on the right; **✔ Check my work** grades the lab.

Every student works on **their own copy of NAVERA** in a sandbox and can reset it to the original at
any time. **The real repository `~/Navera` is never modified**: the students' base is a snapshot taken
from one of its commits (read with `git archive`).

## Start / stop

```bash
~/navera-academy/academy.sh start      # → http://<jetson-ip>:8300
~/navera-academy/academy.sh status | stop | restart | logs
```

Open `http://<jetson-ip>:8300` from any PC on the same network (Chrome, Firefox, Edge).
Teacher login: `teacher`, password in `state/teacher_password.txt` (change it from the 👤 menu).

## Teacher page (`/teacher`)

- **Add students**: one per line `login, Display name, password` (name and password optional). The
  generated passwords are shown once — copy them.
- **Open**: see and use a student's workspace exactly as they do (files, terminal, checks).
- **Reset NAVERA**: put a student's copy back to the base (their version is saved first in
  `students/<name>/backups/*.bundle`; restore with `git clone <bundle>`).
- **Progress by lesson**: green = passed, orange = started.
- **NAVERA base**: pick a commit of `~/Navera` to build a new base (≈ 40 s). Students keep their
  copy until they reset; new students start from the new base.

## What a student has

| In the sandbox | Where it really is |
|---|---|
| `~/navera` — their NAVERA copy (built, Python edits work immediately) | `students/<name>/home/navera` |
| `~/lessons/<id>/` — lab files of each lesson | `students/<name>/home/lessons/<id>` |
| `/data/…` — map, datasets, ArduPilot (read only) | ADATA disk, `datasets/`, `~/ardupilot` |

The sandbox (bubblewrap + systemd scope) shows the system read only and nothing else of the
`shadow-team` home folder: not `~/Navera`, not SSH/Claude keys, not other students. Memory is capped
(1.8 GB per student, 4.5 GB while holding the simulator or camera). Each student has their own ROS
domain (1–101, never NAVERA's 77–79), loopback only.

## Shared hardware

The simulator (fixed ports 8181/8190/5760…, ~3 GB RAM), the camera and the I²C/serial sensors exist
once. Students **book** them from the "Hardware" button; only the holder's new terminals get access.
The teacher can release any booking. Do not run your own `run_sim.sh` or bench while a student holds
the simulator or camera (and a student cannot book the simulator while your own NAVERA uses those
ports).

## Files

```
academy.sh            start/stop
server/               dashboard (Flask): app.py, sandbox.py, workspaces.py, config.py, static/
base/                 the students' NAVERA base (git, tag "base")
courses/<id>/         meta.json, lesson.md, lab.md, files/, check.py, assets/
courses/_lib/         academy_check.py (grading helpers)
courses/modules.json  the 7 modules and the order of the 30 lessons
solutions/<id>/       reference solutions (teacher only, never shown to students)
datasets/<id>/        lesson data (read only in the sandbox at /data/academy/<id>)
students/<name>/      each student's home and backups
state/                users, progress, bookings, teacher password
tools/try_lesson.py   test a lesson as a student (starter must fail, --solution must pass)
AUTHORING.md          how to write or change a lesson
```

## Limits to know

- Plain HTTP on the local network (passwords travel unencrypted): use it on a trusted network.
- The simulator and camera serve one student at a time; plan those lessons (19, 28) in turns.
- A student could join another student's ROS domain on purpose (same machine); there is no
  protection against that beyond the default separate domains.
