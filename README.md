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

## Organisation, teachers and classes

Three roles: **administrator** (the client's manager: organisation name and logo, teachers, the Jetson's
settings), **teacher** (their own classes only) and **student** (their own work only). The `teacher`
account (password in `state/teacher_password.txt`) is IRIS's support administrator.

- **First start of a new box:** the academy shows "Welcome to your NAVERA Academy". The client types
  the **setup code** (`state/setup_code.txt`, printed on the sticker by `setup/make_sticker.py`), the
  organisation, an optional logo, and becomes its administrator.
- **Create account** asks "student or teacher?". Students type their **class code** (or scan the class
  QR / open `/join/<code>`); teachers type the **teacher invitation code** (admin page), or wait for the
  administrator's approval.
- **Classes** (teacher page → ＋ New class): join code + QR poster, seats, dates, legs opened on dates,
  optional ranking (first names + XP), Excel export, certificate naming the class and organisation.
- Data: `state/org.json`, `state/classes.json`, `state/org_logo.png`; a student's class is `class` in
  `state/users.json`. Code: `server/orgs.py`.

## Capacity (measured 2026-10-09 on this Jetson: 6 cores, 7.4 GB)

"✔ Check my work" pressed by many students at the same moment (each check runs in the student's sandbox):

| Mission | Students at once | Time per check | Peak memory used |
|---|---|---|---|
| 03 Python | 1 / 5 / 10 / 20 | 2 / 4 / 8 / 15 s | 1.6 / 1.9 / 2.3 / 2.9 GB |
| 11 ROS 2 (heaviest kind) | 1 / 5 / 10 / 20 | 74 / 76 / 91 / 114 s | 1.8 / 2.7 / 3.9 / 5.4 GB |

All checks succeeded, no memory exhaustion, and the pages stayed fast during the 20-student ROS run
(median 21 ms). So one Jetson handles a class of ~20 checking at once; with ~30 students, ROS checks
would run close to the memory limit — stagger them, or use a second box. Sim Lite runs in each
student's browser and does not load the Jetson.

## Shared hardware

The camera and the I²C/serial sensors exist once. Students **book** them from the "Hardware" button;
only the holder's new terminals get access. The teacher can release any booking.

The **full simulator** (fixed ports 8181/8190/5760…, ~3 GB RAM) is **teacher only**: students fly
**Sim Lite** in the Simulator tab (it runs in each browser, so the whole class can fly at once, with
their own NAVERA code). The teacher page's "Full simulator" box shows whether it runs and how to start
it (Hardware → Take, then `cd ~/navera && navera_tools/run_sim.sh` in a new terminal); it then appears
in the Simulator tab (switch "Full") and the Operator view tab. Do not run your own `run_sim.sh` or
bench outside the academy while a student holds the camera.

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
- Wrong passwords: after 5 on one account from one browser, that browser gets one try per 30 s (a classmate's
  wrong tries never block the student's own browser); one browser waits 15 min after 30 (any accounts); a
  network after 100; an account under real attack (50 in 15 min) waits until the teacher gives a new password.
- Student sandboxes have their own network (loopback only): no internet, nothing on the Jetson. Staff keep
  the Jetson's network (the full simulator must be reachable). A terminal never sees the graders (check.py);
  a check sees only its own mission's grader.
- The full simulator listens on the Jetson's network (ports 8190/8181) while it runs: anyone on the same
  Wi-Fi can open it directly, without the academy's sign-in. Run it only during the lesson.
- The simulator and camera serve one student at a time; plan those lessons (19, 28) in turns.
- A student could join another student's ROS domain on purpose (same machine); there is no
  protection against that beyond the default separate domains.
