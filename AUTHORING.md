# NAVERA Academy — how to write a lesson

The academy is a web dashboard (`server/`, port 8300) where students read a lesson beside a code
editor, a terminal and the simulator. Every student works in a **sandbox** with their own copy of
NAVERA (`~/navera`, reset button) and their own lesson files (`~/lessons/<id>/`).

## Audience — read this twice

- **University students in Oman** (engineering / computer science, years 1–3). English is their
  second language (Arabic first): write clear, direct English — short sentences, no idioms, define
  every technical term the first time (bold it). They know school maths (trigonometry, vectors,
  matrices, derivatives, basic probability) and may have done one programming course; some never used
  Linux, git or ROS.
- **University level**: real maths where it matters (rotation matrices, quaternions, the pinhole
  model with K, homography and DLT, RANSAC probability, covariance propagation, Kalman-style fusion,
  time-compensated celestial navigation…), with a worked numeric example and the code that implements
  it. Basics (terminal, Python, git) go fast and assume they will look things up — but never use a
  concept before it is introduced (e.g. Python classes before the ROS publisher lesson).
- Labs are substantial (2–4 h): implement, test, measure, compare with NAVERA's real code, and a short
  written analysis (results.json / report.md that the check verifies). Each lab ends with
  "Going further" challenges for strong students.
- **Oman context**: examples, exercises and stories use Omani places (Muscat, Sohar, Nizwa, Salalah,
  the Hajar mountains, Jebel Akhdar, Wahiba Sands, Masirah, Barr Al Hikman…) and birds seen in Oman
  (flamingos and shorebirds at Barr Al Hikman, steppe eagles in Dhofar, falcons, migrating swallows…)
  — accurate facts only. NAVERA's **real data** (satellite map, recorded frames, simulator area) covers
  **Sousse, Tunisia**, where NAVERA is developed: use it as is and say so once ("NAVERA's test map
  covers Sousse, Tunisia"); do not pretend it is Oman.
- **Birds are the origin of the NAVERA idea**: each lesson keeps a `## 🐦 How birds do it` section
  (adapt it to the new level; Omani birds welcome). The mascot **Navi the swallow** ("she") may appear
  lightly; the tone is friendly but adult — no baby talk.
- Honesty: NAVERA is a **commercial product, "Release 0.x — field validation pending"**. Never call it
  a prototype, a school project or a toy. Never invent accuracy numbers; quote only figures written
  in `docs/VALIDATION_STATUS.md` (and say "measured in simulation / on the bench" when that is the case).
- Python details that tripped testers: ROS float fields need floats (`9.0`, not `9`); show the exact
  names the lab files use (constants, functions) in the course; prepare students for the common
  error messages they will meet (radians vs degrees, f-string quotes, dtype/uint8 in OpenCV).

## Folder of a lesson

```
courses/<NN-slug>/
  meta.json      {"number": "NN", "title": "...", "module": M, "duration": "1 h 30",
                  "summary": "one or two sentences for the card",
                  "resources": [],            # "sim" / "camera" / "sensors" if the lab needs them
                  "open": ["main_file.py"],   # files opened in the editor when the lesson starts
                  "check_timeout_s": 120}
  lesson.md      the course (theory)               ~1500–3000 words
  lab.md         the lab, step by step             ~800–2000 words
  assets/        images for lesson.md / lab.md (SVG preferred, PNG/JPG ok; small)
  files/         starter files copied to ~/lessons/<id>/ (code with TODOs, data the lab edits)
  check.py       the automatic grader ("✔ Check my work")
solutions/<NN-slug>/   a complete solution (same file names as files/), teacher only — never mounted
datasets/<NN-slug>/    optional larger read-only data, seen in the sandbox as /data/academy/<NN-slug>/
```

`solutions/` and the real repo are **not** visible to students. Everything in `courses/<id>/` is
visible (read only) at `/academy/courses/<id>/` — do not put answers there (check.py may hold expected
values, but not the code that solves the exercise).

## Markdown features of the dashboard

- Callouts: a blockquote starting with `[!NOTE]`, `[!TIP]`, `[!WARNING]`, `[!TASK]` ("🎯 Your turn"),
  `[!QUESTION]` ("❓ Think").
- ```` ```bash ```` blocks get a **▶ Run** button that types the command in the student's terminal
  (one command per block is best; the terminal starts in `~/lessons/<id>/`). Other languages get **Copy**.
- `[label](file:./name.py)` opens `~/lessons/<id>/name.py` in the editor;
  `[label](file:navera/day_pkg/day_pkg/vision_nav.py)` opens a file of the NAVERA copy.
- Images: `![alt](assets/x.svg)`. Tables, `<details><summary>Question</summary>Answer</details>` for
  self-quizzes. No external images or links needed to understand the lesson (internet may be absent).

## lesson.md — the course

1. `# Title`, then a hook: a concrete situation (a drone loses GPS over the sea…).
2. Sections building the idea step by step, each with an example, a picture or a small table.
3. "In NAVERA": where this lives in the real code (file paths in the copy, short excerpts ≤ 20 lines).
4. A glossary table of the new words.
5. 3–5 `<details>` self-check questions with answers.
6. End with "Now open the **🛠️ Lab** tab."

## lab.md — the lab

- Goal + time at the top. Numbered steps `## Step N — …`. Each step: what to do, the exact command
  (` ```bash `), what the student should see, and why.
- 2–5 `[!TASK]` blocks: the work that check.py grades. Say precisely what "done" means
  (function name, file, output). Then "Press **✔ Check my work**".
- A "Going further (optional)" section with 2–3 ungraded challenges for fast students.
- Commands must work **in the sandbox**: `python3`, `ros2`, `colcon`, `git`, `pytest`, OpenCV,
  numpy, matplotlib (Agg backend — save PNGs and let the student open them in the editor, which shows
  images), torch on the GPU. No `sudo`, no `apt`, no GUI windows (`cv2.imshow`, `rqt`, `rviz` fail).

## files/ — starter code

- Python with clear comments, `# TODO 1: …` markers, and a `if __name__ == "__main__":` demo the
  student can run to see something happen. Keep the parts they don't need to change below a line
  `# ---- you don't need to change anything below this line ----`.
- The starter must **run** (no syntax errors) but fail the check (TODOs return `None` / `0` or raise
  `NotImplementedError("TODO 1")`).

## check.py — the grader

```python
from academy_check import Checker, load_student, need, sh, Background, wait_for_messages
c = Checker()

@c.test("distance() is 0 m between a point and itself", hint="All the differences are 0.")
def _():
    m = load_student("distance.py")
    (distance,) = need(m, "distance")
    c.near(distance(36.0, 10.0, 36.0, 10.0), 0.0, tol=0.01, what="distance(...)")

c.run()
```

- It runs in the student's sandbox, current directory `~/lessons/<id>/`, ROS sourced via `sh()`.
  `c.ok / c.eq / c.near / c.file_exists / c.skip`. `sh(cmd)` → (code, output).
  `Background("python3 node.py")` runs a node during a `with` block;
  `wait_for_messages(topic, MsgType, count, timeout)` collects ROS messages.
- 5–15 checks, from easy to hard, each with a **hint that guides without giving the code**.
- Deterministic, fast (whole check well under `check_timeout_s`), no internet.
- Must not crash on a starter file: a missing function / wrong type must produce a ✘ with a message.
- When the lab changes the NAVERA copy (`~/navera/...`), check those files / behaviour there.
  A solution that changes `~/navera` provides `solutions/<id>/_apply.sh` (run from the lesson folder
  by the test tool before checking) that makes those changes (e.g. `cp`, `sed`, `git apply`).

## Testing — mandatory before you finish

```bash
tools/try_lesson.py <id>               # starter: must run and FAIL (exit 1), no Python traceback in output
tools/try_lesson.py <id> --solution    # solution: must PASS every check (exit 0)
tools/try_lesson.py <id> --solution --shell "python3 main.py"   # run any lab command as a student would
tools/try_lesson.py <id> --clean       # remove the throw-away student when done
```

Run **every command of lab.md** this way (`--shell`) to make sure it works in the sandbox. Each lesson
uses its own ROS domain in the test tool, so several lessons can be tested at the same time.

## Data available in the sandbox (read only)

| Path in the sandbox | What |
|---|---|
| `/data/map.mbtiles` | Satellite map of the Sousse region, zoom 13–19 (10 GB, SQLite, tiles `z/x/y`, TMS row order — see `simulation_web/simulation_web/web_common.py` `MBTilesReader`) |
| `/data/navera_data/day_pkg/day_pkg/dataset/images/` + `dataset.csv` | 1120 satellite tiles z17 with lat/lon of each (`filename,lat,lon`; NW corner — check the code) |
| `/data/navera_data/camera_pkg/camera_pkg/data/day/frame_*.jpeg` | 31 real aerial frames 1536×730. **Their `flight_log.csv` positions are WRONG (different places) — never use them as ground truth** |
| `/data/navera_data/camera_pkg/camera_pkg/data/thermal/` | thermal frames with lat/lon/alt in the file name |
| `/data/navera_data/camera_pkg/camera_pkg/data/celestial/etoiles.jpeg` | a star photo |
| `/data/bsc5.dat` | Yale Bright Star Catalogue |
| `/data/ardupilot/` | ArduPilot SITL build (simulator) |
| `/data/academy/<id>/` | your lesson's dataset (from `datasets/<id>/`) |
| `~/navera/` | the student's NAVERA copy (built, `--symlink-install`: Python edits work without rebuild) |

Synthetic "drone photos" with exact ground truth are easy to make from `/data/map.mbtiles` (crop,
rotate, scale, blur, change brightness) — preferred for vision labs. The real frames are good for
"looks like a real flight" demos. Prepare datasets with a script run on the host (copy the script
into `datasets/<id>/make_dataset.py` so the teacher can regenerate them), keep each dataset ≤ 50 MB.

## Environment facts

- NVIDIA Jetson Orin Nano 8 GB, Ubuntu 22.04, ROS 2 Humble, Python 3.10, torch 2.8 (CUDA works).
- `ROS_LOCALHOST_ONLY=1`, a `ROS_DOMAIN_ID` per student: students never see each other's topics.
- The simulator (`navera_tools/run_sim.sh`), the camera and the I²C/serial sensors are shared by the
  class: a lab that needs them lists them in `meta.json` `resources`; the student books them in the
  dashboard. Such a lab must still teach something (and its check must pass or `c.skip`) when the
  hardware is absent — say so in the lab.
- The student's home is `/home/student`; `whoami` says `student`.
