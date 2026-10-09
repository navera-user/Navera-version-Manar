# NAVERA Academy — how to write a lesson

The academy is a web dashboard (`server/`, port 8300) where students read a lesson beside a code
editor, a terminal and the simulator. Every student works in a **sandbox** with their own copy of
NAVERA (`~/navera`, reset button) and their own lesson files (`~/lessons/<id>/`).

## Audience — read this twice

- **International university students** (engineering / computer science, years 1–3), from any
  country. For many, English is a second language (plan for B1): write clear, direct English — short
  sentences, no idioms, define every technical term the first time (bold it). Their school maths
  (trigonometry, vectors, matrices, derivatives, probability) may be rusty or weak: refresh what a
  lesson needs in a toolbox box before using it. Many did only one short programming course; some
  never used Linux, git or ROS.
- **University level**: real maths where it matters (rotation matrices, quaternions, the pinhole
  model with K, homography, RANSAC probability, covariance, Kalman-style fusion…), always built from
  an intuition and a worked numeric example before the formula, and never using a concept before it
  is introduced. Basics (terminal, Python, git) are taught too, with examples: do not assume students
  will look things up.
- Labs are substantial (2–4 h): implement, test, measure, compare with NAVERA's real code, and a short
  written analysis (results.json / report.md that the check verifies). Each lab ends with
  "Going further" challenges for strong students.
- **International context**: no single country is the setting. Worked examples use well-known places
  on several continents (e.g. London–Paris, Singapore, Cape Town, Sydney, Reykjavik, Quito on the
  equator, high latitudes for map-projection effects) when geography matters, and generic settings
  otherwise ("a coastal city", "a desert test range", "a harbour"). NAVERA's **real data**
  (satellite map, recorded frames, simulator area) covers its test area around **Sousse/Monastir
  (Tunisia)**: use it as is and say so once ("NAVERA's test map covers Sousse, Tunisia"); synthetic
  data (tracks, logs) may be placed in that test area or at clearly fictional/generic sites.
- **Birds are the origin of the NAVERA idea**: each lesson keeps a `## 🐦 How birds do it` section
  (global migration examples: Arctic tern, bar-tailed godwit, homing pigeons, European robins, storks, swallows…). The mascot **Navi the swallow** ("she") may appear
  lightly; the tone is friendly but adult — no baby talk.
- Honesty: NAVERA is a **commercial product, "Release 0.x — field validation pending"**. Never call it
  a prototype, a school project or a toy. Never invent accuracy numbers; quote only figures written
  in `docs/VALIDATION_STATUS.md` (and say "measured in simulation / on the bench" when that is the case).
- Python details that tripped testers: ROS float fields need floats (`9.0`, not `9`); show the exact
  names the lab files use (constants, functions) in the course; prepare students for the common
  error messages they will meet (radians vs degrees, f-string quotes, dtype/uint8 in OpenCV).

## Teaching method — every lesson follows it (mandatory)

**Pitch it at university level.** The students are engineering students: keep the pace brisk, the
maths honest and the problems interesting. Engagement comes from **real stakes** (a documented
incident or a real failure as the hook), **roles** (build it, break it, attack it, defend it),
**real numbers** (signal power, costs, limits of the product), **challenge questions** whose answer
is not in the text, and honesty about the **open problems** of NAVERA. Do not re-teach school maths
step by step in the main text: give one worked example and move on. Support for weaker students
lives in the hidden "Stuck?" hints, the 🧰 boxes and the teacher notes, not in a slower lesson.
Mission 01 was first over-simplified for weak simulated students and judged boring by the owner:
both reviews matter, the target is the engineering student.

Mission 01 is the reference: read it before writing or changing any lesson. Tested with simulated
students (an engineering student with English B2, and a weaker technician student with English B1),
the old style ("dense reference text + lab that dictates the code") scored 3–5/10; this method
scored 7–8/10. The rules:

1. **Learning objectives first.** Open with "What you will be able to do": 3–5 verbs a teacher can
   check (explain, compute, write, tell the difference, decide). Every section serves one of them.
2. **Start from what they know.** Say which earlier ideas the lesson uses. Never use a word, symbol,
   formula or Python feature before it is taught — in this lesson or an earlier one. If it is needed
   and not taught yet, teach it here in a few lines with an example (or a "toolbox" box).
3. **One idea per section:** the problem it solves → the idea (an analogy or a picture when it truly
   helps; analogies must be physically right) → **one worked example** with real numbers → a
   **✏️ check** (`[!QUESTION]`, answer hidden in `<details>`) that makes them think, not just repeat.
   This is "I do, we do, you do": the lesson does the first two, the lab is the "you do".
4. **Words.** A "Words of this lesson" table at the TOP (word, plain meaning, Français), not at the
   end. Short sentences, no idioms. Bold a term where it is defined.
5. **Show the mistakes.** A "Common mistakes" or "Common wrong ideas" box for the traps students
   really fall into (found by testing), with what they look like (e.g. "x always 0.0 → return inside
   the loop").
6. **Pictures carry ideas** (dual coding): one figure per key idea, with a caption that says what to
   see. Tell students what to ignore in a complex figure.
7. **Optional is optional.** A `<details class="further">` block may hold history or derivations, but
   nothing the quiz, lab or report needs.
8. **End with a summary** of the 3–5 ideas to keep, a link to the next mission, and "Check yourself"
   retrieval questions ("answer without scrolling up").
9. **Honest time.** State reading time *including* the exercises, and a lab range (fast / slower
   student). Measure it with the simulated students.
10. **Birds** (`## 🐦 How birds do it`): 3–6 lines, linked to the lesson's idea. Never a long story.

### The lab is where the student writes the code

- **The student writes the logic.** TODO comments state the **goal**, the inputs/outputs and **an
  example call with its result** — never the algorithm or the code. The way to do it was shown in the
  lesson's worked example; the lab asks to apply it to a new case.
- **Hints in steps**, hidden: `<details><summary>Stuck? Hints, one at a time</summary>` with 3–5
  numbered hints from vague to precise, plus "you got X instead of Y? → this mistake".
- **Teach the tool before the task.** If a TODO needs a Python feature (append, slicing, zip, default
  arguments, `None`), show a 3-line example of it *not* about the exercise, just before.
- **Predict → run → explain.** Before each experiment, the student writes a guess in `answers.py`
  (`PREDICT_…`, graded only as "written"). After it, an `EXPLAIN_…` in their own words. Never print
  the expected result before the student runs it, and never put the answer of a question right under
  it. A prediction must not be copyable from the lesson's worked example (use other numbers).
- **A runner with pictures.** Give a script (like `where_am_i.py`) that runs the student's functions
  on the lab's situations, prints clear results and saves a picture; and a `test` mode that checks
  each function on its example. It must turn crashes and wrong return types into one plain sentence.
- **The check tests on unseen numbers**: other inputs than the lab's, so copying the examples cannot
  pass. Keep expected *values* in check.py, never the solving code. Hints guide, never give the code.
  No multiple-choice quiz whose right answer is the longest option.
- **Close with "Look back"**: 2–3 reflection questions (not graded).
- **Test it like a student**: starter fails cleanly, solution passes, every command runs in the
  sandbox, and a simulated weak student can finish with the hints alone.

### Quality rules learned from mission 01 (all mandatory)

- **Alignment table.** Each mission has one (in `solutions/<id>/TEACHER.md`): objective → lesson
  "Your turn" → lab step → check.py test. Every objective is practised and assessed; every check
  serves an objective.
- **Prerequisites.** From mission 02 on, open with 3 short retrieval questions on the earlier
  missions this one uses ("if you miss two, reread lesson X §Y"), and put 1–2 questions from earlier
  missions in "Check yourself" (spaced practice). Maths-heavy missions start with a "🧰 maths
  toolbox" box (e.g. matrix × vector by hand before rotations; variance vs standard deviation before
  Kalman filters).
- **Analogies must be physically right**, and say where they stop working. Have a second reviewer
  check every analogy and number. Every number in the text must be reproducible by a script or by
  hand; name grid or rounding effects when they matter.
- **No spoilers.** For each `PREDICT_…`, search lesson.md for its answer; if it is there, move that
  passage into `<details><summary>Read this after lab Step N</summary>`.
- **Fading.** The first TODO adapts a worked example closely; the middle ones get hints that describe
  the steps; the **last TODO has the least help** (a goal, an example, a hand trace to do first, and
  hints). The last hint may show one line, never the whole function. Hints that diagnose a wrong
  result ("you get 4 instead of 5? …") must be checked by running the wrong versions.
- **Teacher notes** in `solutions/<id>/TEACHER.md`: alignment table, answer key, a 3-level rubric
  for each written answer (the check only catches empty or off-topic answers — say so to students),
  difficulties seen in testing, a suggested class plan, and differentiation (fast / struggling).
- **Load budget.** A lesson of about 2 500–3 500 words; a short words table (about 10 entries); one
  new Python feature per TODO, shown first in a 🧰 box; reading time stated honestly (about 60 minutes
  for 3 000 words with the checks).
- **Feedback.** Each ✘ names the likely mistake and the lesson section; where possible "on input X you
  returned Y". Runner scripts turn crashes, `None` and wrong types into one plain sentence.
- **Accuracy over slogans.** Do not overclaim (e.g. "nothing can detect spoofing"): state what simple
  systems cannot do, what better ones do, and NAVERA's place.
- **Order of lesson.md is fixed**; the workspace/orientation belongs in "How to study"; nothing comes
  after "Check yourself" except "Now open the Lab tab".
- **Validation.** Simulated students (B2 and weak B1) and an expert-teacher review before release;
  then a pilot with real students (one weak), timed, before the mission is called final.

## Folder of a lesson

```
courses/<NN-slug>/
  meta.json      {"number": "NN", "title": "...", "module": M, "duration": "1 h 30",
                  "summary": "one or two sentences for the card",
                  "resources": [],            # "sim" / "camera" / "sensors" if the lab needs them
                  "open": ["main_file.py"],   # files opened in the editor when the lesson starts
                  "check_timeout_s": 120}
  lesson.md      the course, built with the teaching method above
  lab.md         the lab, step by step (the student writes the code)
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

Follow "Teaching method" above, in this order: objectives → how to study / what you already know →
Words of this lesson → the problem (a concrete situation) → numbered sections (Why → idea → worked
example → ✏️ Your turn → Remember), with Common mistakes boxes → "In NAVERA" (where it lives in the
real code; excerpts ≤ 15 lines the student can read) → 🐦 birds (short) → Summary → Check yourself →
"Now open the **🛠️ Lab** tab."

## lab.md — the lab

- Goal + time range at the top, then a "plan" table (lesson section → lab step → function). Numbered
  steps `## Step N — …`. Each step: what to do, the exact command (` ```bash `), what to look at (but
  not the result itself when the student must predict it), and why.
- 2–5 `[!TASK]` blocks: the work that check.py grades. Say precisely what "done" means
  (function name, file, output). Then "Press **✔ Check my work**".
- A "Look back" step (reflection, not graded), then "Going further (optional)" with 2–3 ungraded
  challenges for fast students.
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
