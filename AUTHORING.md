# NAVERA Academy — how to write a lesson

The academy is a web dashboard (`server/`, port 8300) where students read a lesson beside a code
editor, a terminal and the simulator. Every student works in a **sandbox** with their own lesson
files (`~/lessons/<id>/`), where they build **NAVERA Lite**, the course's own navigation stack (see
"NAVERA Lite" below).

**The rule.** Students never see, run, import, grep or edit NAVERA's code or files. Lessons describe
NAVERA, IRIS's product, in **words and numbers** (design, rules, settings values, measured results with
dates). Everything a student runs is course-written code. (A teacher can give one student full NAVERA
access from the dashboard; no lesson may rely on it.)

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
- Labs are substantial (2–4 h): implement, test, measure, compare with the course's reference values or a third-party library, and a short
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
  check.py       the automatic grader ("✔ Check my work") — never visible to students (sealed)
  hidden/        optional test data only check.py reads (hidden("name")) — never visible to students
solutions/<NN-slug>/   a complete solution (same file names as files/), teacher only — never mounted
datasets/<NN-slug>/    optional larger read-only data, seen in the sandbox as /data/academy/<NN-slug>/
```

`solutions/` and the real repo are **not** visible to students. Of `courses/<id>/`, the sandbox sees
only `files/` (read only, at `/academy/courses/<id>/files/`) and `courses/_lib/` (at `/academy/lib/`).
`check.py`, `hidden/` and `meta.json` are never mounted: the check gets them in memory (see
"check.py — security" below). `datasets/` is public: never put expected answers there.

## Markdown features of the dashboard

- Callouts: a blockquote starting with `[!NOTE]`, `[!TIP]`, `[!WARNING]`, `[!TASK]` ("🎯 Your turn"),
  `[!QUESTION]` ("❓ Think").
- ```` ```bash ```` blocks get a **▶ Run** button that types the command in the student's terminal
  (one command per block is best; the terminal starts in `~/lessons/<id>/`). Other languages get **Copy**.
- `[label](file:./name.py)` opens `~/lessons/<id>/name.py` in the editor
  (`file:./navera_lite/geo.py` for a part of the student's stack). There are no links to NAVERA files.
- Images: `![alt](assets/x.svg)`. Tables, `<details><summary>Question</summary>Answer</details>` for
  self-quizzes. No external images or links needed to understand the lesson (internet may be absent).

## lesson.md — the course

Follow "Teaching method" above, in this order: objectives → how to study / what you already know →
Words of this lesson → the problem (a concrete situation) → numbered sections (Why → idea → worked
example → ✏️ Your turn → Remember), with Common mistakes boxes → "In NAVERA" (how the product does it, in
**words and numbers only**: no code, no file or package names) followed by "In NAVERA Lite" (where the
idea lives in the student's own `navera_lite/` code) → 🐦 birds (short) → Summary → Check yourself →
"Now open the **🛠️ Lab** tab."

## lab.md — the lab

- Goal + time range at the top, then a "plan" table (lesson section → lab step → function). Numbered
  steps `## Step N — …`. Each step: what to do, the exact command (` ```bash `), what to look at (but
  not the result itself when the student must predict it), and why.
- 2–5 `[!TASK]` blocks: the work that check.py grades. Say precisely what "done" means
  (function name, file, output). Then "Press **✔ Check my work**".
- A "Look back" step (reflection, not graded), then "Going further (optional)" with 2–3 ungraded
  challenges for fast students.
- Commands must work **in the sandbox**: `python3`, `python3 -m navera_lite.…`, `ros2`, `git`, `pytest`, OpenCV,
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
- Everything the check reads is in the lesson folder. A NAVERA Lite module is loaded with
  `load_student("navera_lite.arbiter")` (or `"navera_lite/arbiter.py"`): the lesson folder comes first
  on `sys.path`, `fresh=True` re-imports every `navera_lite` module; `is_stub(func)` tells a TODO stub.
  ROS checks call `publishers_ok()` (default topic `/navera_lite/status`) before reading a topic.
- `tools/try_lesson.py <id> --solution` copies `solutions/<id>/` **with its sub-folders**
  (`navera_lite/`) over the lesson folder. No `_apply.sh` is needed (one is still run if present).

## check.py — security (sealed checks, mandatory)

Every check runs **sealed** (dashboard and `tools/try_lesson.py` alike, `server/sealed.py` →
`courses/_lib/academy_sealed.py`): the checker gets `check.py` and `hidden/` in memory, is
non-dumpable (no `/proc/<pid>/mem|environ|fd`), and runs **every piece of student code in another
process**: commands (`subprocess`, `os.system`, `sh()`, `Background()`) get the student's environment
(`~/.bashrc` sourced, as before) but see no check.py and no hidden data; `load_student()` and any
`import` of a module from a writable folder (`~/lessons/…`, `~/navera/…`, after `sys.path.insert`)
return **proxies** of a module running in a separate student Python process (`academy_remote.py`).
The score reaches the server on a private pipe with a nonce: an `ACADEMY_RESULT` line printed by
anyone is ignored (and removed from the output). Student files are always compiled from source (no
stale `__pycache__`). Attack tests: `python3 -m pytest -q tools/tests/test_sealed_check.py`.

Rules for authors:
- **Expected values** live in `check.py` (constants) or in `courses/<id>/hidden/` (files, read with
  `from academy_check import hidden` → `hidden("expected.json")` (str) or `hidden("x.npy", text=False)`
  (bytes); `hidden_names()` lists them; 64 MB max). Never in `files/`, `datasets/`, `assets/` or a
  lesson text.
- **Never write an expected value or hidden data to disk** (`/tmp`, the lesson folder, a temp file):
  student processes run in the same sandbox and can read it. Data the student's program must
  *process* (a test log it has never seen) may be written to a temp file just before running it — the
  student sees that input anyway; keep its expected *output* in memory.
- **Never execute student code in check.py's process**: no `exec(open(...))`, `runpy`, `importlib`
  with a path (use `load_student`), `pickle`/`torch.load`/`np.load(allow_pickle=True)` of a student
  file, `ctypes` of a student library. Read student files as text/JSON/CSV/YAML (`yaml.safe_load`).
- Values come back by value (numbers, str, list/tuple/dict/set, namedtuple, NumPy, pandas, datetime,
  ROS messages of installed packages); instances of student classes, generators… are proxies that
  forward attributes, calls, operators, `len`/`iter`/`[]`/`==`/`float()`. `isinstance(x, list)` on a
  proxy is False (as `isinstance(proxy, m.Track)` is True). A list/dict/ndarray the student's
  function changes in place is copied back after the call; deeper sharing (the student keeps a
  reference to your list and you change it later) is not.
- Functions/objects you pass to student code become call-only proxies (the student may call them and
  read their public attributes — not `__globals__`, `__code__` or anything starting with `_`). Never pass
  a module or an object that holds expected values.
- `run(fn, …, seconds=N)` (SIGALRM) interrupts the student's code in its process; if it does not stop
  within 2 s that process is restarted (modules, functions and classes reconnect, other objects are
  lost: load them again inside the test).
- An exception keeps its built-in class (`ValueError` stays `ValueError`); `e.academy_where` gives the
  student's file and line (`_where`/`run()` show it). A student cannot raise the checker's `Skip`.
- ROS: `wait_for_messages()` runs in the checker: the message type must be an installed package
  (`/opt/ros`, read only), not a package the student builds.
- `check.py` itself may read the student's files, run commands and compare outputs as before.

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
| `/data/map.mbtiles` | The course map of the Sousse region (SQLite MBTiles, tiles `z/x/y`, TMS row order; `navera_lite/tiles.py` reads it). It is being switched to OpenStreetMap-based tiles (design §7.3): show "© OpenStreetMap contributors" wherever a tile is shown |
| `/data/academy/<id>/` | your lesson's dataset (from `datasets/<id>/`) |

NAVERA's own data folder, the ArduPilot build and NAVERA's star catalogue are **not** mounted for students
(staff and students given NAVERA access only). Data copied from NAVERA (photos, frames, calibration views —
never code) goes into `datasets/<id>/` (owner decision §7.2).

Synthetic "drone photos" with exact ground truth are easy to make from the map (crop,
rotate, scale, blur, change brightness) — preferred for vision labs. The real frames are good for
"looks like a real flight" demos. Prepare datasets with a script run on the host (copy the script
into `solutions/<id>/make_dataset.py` so the teacher can regenerate them), keep each dataset ≤ 50 MB.
Generators never go in `datasets/<id>/` (students can read it: a generator's comments give the answers away):
`datasets/<id>/` holds the generated outputs only, plus at most a neutral README.

## Environment facts

- NVIDIA Jetson Orin Nano 8 GB, Ubuntu 22.04, ROS 2 Humble, Python 3.10, torch 2.8 (CUDA works).
- `ROS_LOCALHOST_ONLY=1`, a `ROS_DOMAIN_ID` per student: students never see each other's topics.
- Students fly NAVERA Lite in **Sim Lite** (the browser). NAVERA's full simulator is staff-only (described in
  words in lessons). The camera and the I²C/serial sensors are shared by the
  class: a lab that needs them lists them in `meta.json` `resources`; the student books them in the
  dashboard. Such a lab must still teach something (and its check must pass or `c.skip`) when the
  hardware is absent — say so in the lab.
- The student's home is `/home/student`; `whoami` says `student`.

## NAVERA Lite — the students' stack

Design: `reviews/fledgling-design.md` (§7 owner decisions override it: read "Fledgling" as NAVERA Lite,
`fledgling` as `navera_lite`, topics `/navera_lite/*`, settings `navera_lite.yaml`). Conventions:
`courses/_lib/CONVENTIONS.md`.

- **What it is.** A small GPS-denied navigation stack (pure Python + numpy + OpenCV, a thin rclpy layer on
  standard messages, no colcon build) with NAVERA's *shape* (witnesses → judge → messenger). Students
  complete one part per mission; earlier parts ship finished (the course's reference, not the student's
  own version). Lessons say "NAVERA Lite, the stack you build" vs "NAVERA, IRIS's product".
- **One source.** `solutions/_navera_lite/` (teacher only) holds the complete reference: `navera_lite/<part>.py`,
  `navera_lite/tests/`, `navera_lite.yaml`. Every top-level function/class has a tag line right above it:
  `# @part NN todo K` (introduced in mission NN as its TODO K) or `# @part NN` (given). A method may carry
  its own tag. The student-facing docstring (goal, inputs/outputs with units, one `Example:` with its
  result) is written once, there. Write it from the lessons and the design, **never from NAVERA's code**.
- **One manifest fragment per mission**: `solutions/_navera_lite/manifest.d/<NN-slug>.json` =
  `{"parts": [...], "todo_missions": [NN], "tests": ["test_<part>.py"], "extra": []}`. Missions are built in
  parallel, so there is no shared list to edit: `manifest.json` holds global settings only, and the
  `PARTS` table of each copy's `navera_lite/__init__.py` is **generated** from the tags (never hand-edit
  `navera_lite/__init__.py` to register a part; adding `vehicle.py` for 03 and `geo.py` for 06 touches no
  common file). `tools/lite_build.py --parts` prints the table.
- **Build:** `python3 tools/lite_build.py <id>` (or `--all`) writes `courses/<id>/files/navera_lite/`
  (tags < NN finished, tags == NN stubbed to signature + docstring + `return None   # TODO: write your code
  above, and return the result` or `raise NotImplementedError("TODO K")`, tags > NN removed, plus `PARTS.md`)
  and `solutions/<id>/navera_lite/` (complete), then verifies: the starter imports, its TODOs are stubs,
  every TODO docstring has an `Example:`, the shipped tests pass on the solution, lite_lint is clean.
  Both folders are generated: edit the reference and rebuild. Runners, answers.py, report.md and play tools
  stay hand-written in `courses/<id>/files/`.
- **Lint:** `python3 tools/lite_lint.py <id>` (or `--all`) refuses NAVERA's identifiers (package, node,
  message and class names, `~/navera`, NAVERA's data folder, `file:navera/` links, `/navera/…` topics) and
  any 6 consecutive non-trivial lines identical to a file of NAVERA's base snapshot. The words "NAVERA" and
  `navera_lite` are fine. A mission is not done until its lint is clean.
- **Tests of the tools:** `python3 -m pytest -q tools/tests`.
