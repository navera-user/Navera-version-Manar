# Lab 20 — Stamp it right

**Goal:** write the timing part of NAVERA Lite (`navera_lite/timing.py`): describe a frame stream, measure a
camera's delay on a flash bench and choose its setting, put a price on time errors, give every frame of a turning
plane the attitude of its exposure, refuse the frames you cannot trust, run the live camera over ROS, and write a
memo to your team.
**Time:** 3 h to 4 h 30 (a strong programmer: about 2 h 30). **No camera is needed**: every step uses recorded or
simulated data. A real camera is an optional extra (Step 12).
**Fast track:** if you know numpy, write the TODOs from the docstrings without the 🧰 boxes and the "Stuck?" boxes;
then do "Going further" and write your results in `LOOK_BACK`; your teacher reads them.

`python3 run_timing.py test` names the **symptom** of a wrong result and the hint to open ("lab Step 6, hint 3"):
try to find the mistake yourself first, then open that hint.

Your files (📝 Code tab): [navera_lite/timing.py](file:./navera_lite/timing.py) (**your code**: six functions,
`TODO 1–6`), [answers.py](file:./answers.py), [camera.yaml](file:./camera.yaml) (your camera's settings),
[report.md](file:./report.md) (the memo), and ready-made tools you only run: [run_timing.py](file:./run_timing.py)
(runs your functions on the lab's data and draws them), `navera_lite/ros/camera_node.py` (the live camera) and
[grab_real.py](file:./grab_real.py) (Step 12, optional).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1 a frame is an instant | Step 1 | (no code: NAVERA's real frames) |
| §2 describing a stream | Step 2 | `frame_stats` |
| §3 the flash bench | Steps 3–4 | `delay_from_flashes`; the delay setting |
| §4 what a time error costs | Step 5 | `time_error_m` |
| §5 the attitude at the exposure | Steps 6–7 | `attitude_at` |
| §6 refusing frames | Step 8 | `rotation_rate_dps`, `usable` |
| §3 and §5 together | Step 9 | (no code: check the bench against the flight) |
| §1 the newest frame | Step 10 | (no code: the live camera over ROS) |
| all | Step 11 | the memo |

The data, in `/data/academy/20-live-camera/`: `bench/` holds **real** frames of NAVERA's Insta360 (recorded on
NAVERA's bench, 2026-10-06); the rest is **simulated**, with an exact truth: a 60 s grab log, a flash bench, and a
survey plane's 30 s flight over Sousse, Tunisia (NAVERA's test area): its IMU at 50 Hz and the frames of its fixed,
downward camera, drawn from OpenStreetMap data (© OpenStreetMap contributors).

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never
> marked right or wrong. Each function's docstring says its goal and gives one example with its result;
> `python3 run_timing.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — Timekeeper (about 2 h)

## Step 0 — A guess

No code. A plane 120 m above flat ground rolls at 40 °/s. Its program straightens each picture with the attitude
it holds when the picture **arrives**, 0.10 s after the picture was taken.

> [!TASK]
> **Predict** (`PREDICT_ERROR` in `answers.py`): how many metres from the truth does it place the ground seen at
> the image centre? Save the file (`Ctrl+S`). Then read lesson §1.

## Step 1 — NAVERA's camera on the bench

```bash
python3 run_timing.py bench
```

It opens a **real** frame of NAVERA's Insta360, saves its two halves, and times how long your computer needs to
decode it. Open [out/bench_top.jpg](file:./out/bench_top.jpg): the fisheye view of the top lens, the one NAVERA
uses (straight lines look curved: mission 19 straightens them). The bottom half filmed people in the room: it is
pixelated.

> [!TASK]
> Write `DECODE_MS` (as printed), `CORES_ALL_FRAMES` (how many CPU cores would decoding **every** frame at 28.8
> frames per second keep busy? two decimals) and `EXPLAIN_DECODE`: why does a live camera program grab every frame
> but decode only the one it sends?

<details><summary>Stuck? Hints</summary>

1. One core decoding for DECODE_MS milliseconds, 28.8 times per second, is busy 28.8 × DECODE_MS / 1000 of each
   second: that fraction is the number of cores.
2. A number near 1.8 or 0.5 that does not change when you multiply? Check the units: DECODE_MS is in
   milliseconds; 28.8 × DECODE_MS is milliseconds of decoding per second.
3. Your decode time may differ from your neighbour's: the computer is shared. The check uses **your** number.
</details>

## Step 2 — Describe a frame stream (TODO 1)

Read lesson §2. Open [navera_lite/timing.py](file:./navera_lite/timing.py): the top holds the conventions, the
settings `DEFAULTS` and three finished helpers (`load_camera_settings`, `exposure_time`, `tilt_deg`). Each `TODO`
function keeps its docstring and ends with `return None   # TODO…`: replace that line with your code.

<details><summary>🧰 numpy: intervals, median, standard deviation</summary>

```python
import numpy as np
t = np.asarray([2.0, 2.5, 3.5], dtype=float)   # a list becomes an array
d = np.diff(t)                    # array([0.5, 1. ]) — each element minus the one before
float(np.median(d))               # 0.75
float(np.std(d))                  # 0.25 (ddof = 0, the course rule)
float(d.max()), t.size            # (1.0, 3)
round(2.6), int(round(2.4))       # (3, 2) — round() of a float gives an int in Python 3
```
</details>

**TODO 1** `frame_stats(stamps_s)`: the lesson's worked example is the docstring's. Raise
`ValueError("…")` (`raise ValueError("need at least 2 stamps")`) when there are fewer than 2 stamps.

```bash
python3 run_timing.py test
```

The two TODO 1 lines must be ✔ (the others are later TODOs).

```bash
python3 run_timing.py stats
```

It runs your function on 60 s of grab times, and on the first 40 s alone. Open
[out/intervals.png](file:./out/intervals.png): each dot is one interval (the vertical axis is **logarithmic**: equal
steps mean ×10, so 35 ms and 350 ms fit on one picture).

> [!TASK]
> Write `FPS_LOG`, `DROPPED_LOG` (the whole 60 s), `JITTER_40S_MS`, `JITTER_60S_MS`, and `EXPLAIN_JITTER`: why
> do 20 more seconds almost double the jitter? Which number describes the camera's normal rhythm, and which one
> the risk? (Find the reason in the picture.)

<details><summary>Stuck? Hints, one at a time</summary>

1. `d = np.diff(np.asarray(stamps_s, dtype=float))` gives the n − 1 intervals; everything else comes from `d` and
   `n`.
2. fps = 10.0 instead of 8.0: 5 frames have only 4 intervals — (n − 1) / (last − first).
3. jitter_ms = 50.0 instead of 43.3: that is ddof = 1 (🧰 above).
4. dropped = 2 instead of 1: an interval of 2 periods hides ONE frame. Loop over `d`; for each interval longer than
   1.5 × the median, add `int(round(x / median)) - 1`.
5. Times are seconds; the dict wants milliseconds for the three `_ms` keys: × 1000.
</details>

## Step 3 — The flash bench (TODO 2)

A camera faces a screen; 21 times, the program turns the screen white and records the brightness of every frame
(lesson §3's figure). The camera is the class's test camera, a USB camera like NAVERA's (not NAVERA's Insta360).

> [!TASK]
> **Predict first** (`PREDICT_DELAY`), before you read lesson §3: will the 20 delays be (almost) equal? If not, how
> far apart? Then read §3.

<details><summary>🧰 Python: two lists side by side, and the first match</summary>

```python
times = [0.9, 1.05, 1.1]
values = [30, 40, 200]
for t, v in zip(times, values):          # walks both lists together
    print(t, v)
after = [(t, v) for t, v in zip(times, values) if t > 1.0]    # [(1.05, 40), (1.1, 200)]
for t, v in after:                       # the FIRST pair with v > 100:
    if v > 100:
        print("first:", t)               # first: 1.1
        break                            # stop at the first one
```
</details>

**TODO 2** `delay_from_flashes(flash_s, frame_s, brightness)`: the docstring defines the dark level, the bright
level and the midpoint; return one entry per flash, `None` for a flash the camera did not see.

```bash
python3 run_timing.py test
```

```bash
python3 run_timing.py flashes
```

It prints one delay per flash and their statistics. Open [out/flashes.png](file:./out/flashes.png): left, the
brightness around every flash; right, one delay per flash.

> [!TASK]
> Write `DELAY_MEDIAN_MS`, `DELAY_MIN_MS`, `DELAY_MEAN_MS` (one decimal), `UNSEEN_FLASH` (the number of the flash
> the camera did not see), `OUTLIER_FLASH` (the flash whose delay is far from all the others) and
> `EXPLAIN_SPREAD`: why do the normal delays spread over about one frame period, even on a perfect clock?

<details><summary>Stuck? Hints, one at a time</summary>

1. For one flash t0: the frames with t ≤ t0 (take the last one's brightness: dark), and the frames with
   t0 < t ≤ t0 + window_s (bright = the largest brightness among them). Build the second list with zip (🧰).
2. [0.05] instead of [0.1] in the test: the frame at 1.05 (brightness 40) is above `dark` but below the midpoint
   (30 + 210) / 2 = 120. The rule is "brighter than the midpoint", not "brighter than dark".
3. A number instead of None for the unseen flash: test `bright - dark < min_rise` (and an empty list) before you
   search, and `append(None)`.
4. Fewer entries than flashes: every flash gets an entry, None included — the list must keep the flashes' order.
</details>

## Step 4 — Choose the delay setting (no new code)

The bench screen's own delay was measured separately with a photodiode: **s = 20 ms**. The camera runs at 28.8
frames per second (T = 34.7 ms).

> [!TASK]
> Choose the camera's delay setting from your bench numbers and lesson §3. Write it as `LATENCY_SETTING_S` in
> `answers.py` (seconds, three decimals) **and** as `latency_s` in [camera.yaml](file:./camera.yaml) (it holds
> NAVERA's 0.138 s for its own camera: replace it). Save both. Then `EXPLAIN_LATENCY`: how did you get it, and why
> not the median as it is?

<details><summary>Stuck? Hints</summary>

1. Lesson §3, consequence 3: each delay is s + w + L, and the median of w is about T/2.
2. 0.156? That is the median itself: it still holds the screen and half a period. 0.141? The minimum still holds
   the screen. 0.136? You removed the screen but not the half period.
3. In camera.yaml write a number in seconds, `latency_s: 0.123` (no quotes, no "ms").
</details>

## Step 5 — What a time error costs (TODO 3)

Read lesson §4. **TODO 3** `time_error_m(h_m, rate_dps, dt_s)`: the formula of §4, exact (with the tangent).

```bash
python3 run_timing.py test
```

```bash
python3 run_timing.py budget
```

> [!TASK]
> 1. `BUDGET_300_M`: 300 m above the ground, rotating at 30 °/s, a stamp wrong by one frame period (1/28.8 s).
> 2. `DT_FOR_30M_S`: at 150 m and 25 °/s, how large a time error moves the image centre by 30 m (the σ that day
>    vision states)? Solve the formula for δt by hand (atan), or search with your function (two decimals).
> 3. `EXPLAIN_BUDGET`: why does the same time error cost more at 300 m than at 150 m, and more in a turn than in
>    straight, level flight?

<details><summary>Stuck? Hints</summary>

1. 218.5 instead of 3.492 in the test: `math.tan` got degrees — `math.tan(math.radians(rate_dps * dt_s))`.
2. 3.4907 instead of 3.4921: that is h × angle (small-angle); the docstring asks for the tangent.
3. DT_FOR_30M_S: tan δθ = 30 / 150, so δθ = atan(0.2) in degrees, and δt = δθ / 25.
</details>

> [!TIP] 🏅 End of session 1 — Timekeeper
> Press **✔ Check my work**. When the checks of TODO 1–3 and Steps 0–5 pass (the first eight; the others are
> session 2), you earn the **Timekeeper** badge. If the class session ends here, stop here.

## Session 2 — Shutter (about 2 h)

## Step 6 — The attitude at the exposure (TODO 4)

Read lesson §5. **TODO 4** `attitude_at(t_s, imu_t, imu_q, max_gap_s=0.2)`: bracket with `bisect` (🧰 in §5),
handle the two ends and the "no sample within max_gap_s" rule, then slerp. `slerp` is imported at the top of the
file, finished (mission 16's).

<details><summary>🧰 Python: the nearest of two neighbours, and a list or an array</summary>

```python
times = [0.0, 0.2, 1.0]
i = bisect.bisect_right(times, 0.5)          # 2: between times[1] and times[2]
near = min(abs(0.5 - times[j]) for j in (i - 1, i) if 0 <= j < len(times))   # 0.3 — careful at both ends
qs = [(0, 0, 0, 1), (0, 0, 0.17, 0.98)]     # a list of tuples, or a numpy array of shape (n, 4):
qs[-1]                                       # both give the last quaternion the same way
```
</details>

```bash
python3 run_timing.py test
```

The eight TODO 4 lines must be ✔.

<details><summary>Stuck? Hints, one at a time</summary>

1. `i = bisect.bisect_right(imu_t, t_s)`: then `imu_t[i - 1] <= t_s < imu_t[i]` when both exist. i = 0 means before
   the first sample, i = len(imu_t) after the last.
2. Test the gap first: the nearest sample is `imu_t[i - 1]` or `imu_t[i]` (whichever exists); if it is farther than
   `max_gap_s`, return None. An empty history: return None at once.
3. Yaw 15° instead of 5°: the fraction is upside down — f = (t_s − t₀) / (t₁ − t₀) goes from 0 at t₀ to 1 at t₁.
4. A value 0.1 s after the last sample: return that last sample (`q_normalize(imu_q[-1])`), never extrapolate;
   the same before the first.
5. A value in the middle of a 1 s hole: both neighbours are 0.5 s away → None. The middle of a 0.3 s hole is
   0.15 s from both: interpolate.
6. The ✔ value has its large number first, like [0.999, 0, 0, 0.044]? You built (w, x, y, z): the course stores
   (x, y, z, w). Pass the samples to slerp as they are.
</details>

## Step 7 — The plane's turn

The flight: 150 m above Sousse, 25 m/s; it banks right to 30° (3–5 s), turns, levels (11–13 s), its IMU is silent
for 0.6 s (14.6–15.2 s), it banks left to 48° in one second (17–18 s), then levels slowly (20–23 s).

> [!TASK]
> **Predict** (`PREDICT_METHODS`): rank the three attitudes from the worst to the best — the IMU sample held at
> the grab, the nearest sample to the exposure, and your slerp at the exposure. Then run, first with NAVERA's
> setting for its own camera, then with yours (camera.yaml):

```bash
python3 run_timing.py turn --latency 0.138
```

```bash
python3 run_timing.py turn
```

Open [out/turn.png](file:./out/turn.png): top, the true roll; bottom, the error of each method for every frame
(logarithmic axis). Then look at one frame of the first roll:

```bash
python3 run_timing.py straighten
```

Open [out/straighten.png](file:./out/straighten.png): top, the frame as the camera took it; middle and bottom, the
frame straightened (mission 18's `nadir_homography`) with each attitude and laid over the true level view. Double
lines = a wrong attitude.

> [!TASK]
> Write `GRAB_MEDIAN_M`, `GRAB_MAX_M` ("held at the grab"), `COPIED_MEDIAN_M` (yours with `--latency 0.138`),
> `MINE_MEDIAN_M` (yours with your camera.yaml), `STRAIGHT_GRAB_M` (straighten, "held at the grab"), and
> `EXPLAIN_TURN`: when in the flight is "held at the grab" most wrong, and why then? Compare with your
> `PREDICT_METHODS`.

<details><summary>Stuck? Hints</summary>

1. The runner stops with "attitude_at() stopped on the flight's data": a case of Step 6 is still wrong — run
   `python3 run_timing.py test` again; the message names the error.
2. MINE_MEDIAN_M depends on YOUR setting: the check computes it for the latency_s in your camera.yaml. If you
   change camera.yaml, run `turn` again.
3. Why is the nearest sample sometimes better than slerp with 0.138 s? Slerp gives the exact attitude of the
   instant you ask; with the wrong instant, exactness does not help. Look at Step 9.
</details>

## Step 8 — Refuse the frames you cannot trust (TODO 5, TODO 6)

Read lesson §6. **TODO 5** `rotation_rate_dps(t_s, imu_t, imu_q, window_s=0.2, max_gap_s=0.2)`: two calls of your
`attitude_at` and the finished `q_angle_deg`.

**TODO 6** `usable(q, rate_dps, cfg)`: the least guided function. Before any code, trace on paper the docstring's
rules for these three cases (the settings of `DEFAULTS`), and write the answers next to them:
(a) q level, rate 35 °/s; (b) q rolled 50°, rate None; (c) q None, a gimbal. Then write it: the rules in the
docstring's order, each one a `return` with the exact words (`f"turning {rate_dps:.1f} °/s > …"`).

```bash
python3 run_timing.py test
```

```bash
python3 run_timing.py turn
```

The end of the printout now counts your decisions; on out/turn.png red crosses mark the refused frames.

> [!TASK]
> Write `N_TURNING`, `N_TILTED`, `N_NO_ATTITUDE` (with your camera.yaml) and `EXPLAIN_REFUSE`: the attitude is
> interpolated at the right instant — why still refuse a frame taken while the plane turns at 60 °/s?

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 5: `q1 = attitude_at(t_s, …)`, `q0 = attitude_at(t_s - window_s, …)`; None if either is None; else the angle
   between them divided by `window_s`. 20.0 instead of 100.0: you forgot to divide.
2. TODO 6 (a): turning 35.0 °/s > 30.0 °/s. (b): rotation rate unknown — the rate rule comes before the tilt rule.
   (c): no attitude at the exposure — rule 1 holds even with a gimbal.
3. A ✘ that shows the right words but says "the reason must be exactly": compare letter by letter — the degree
   sign, the spaces, one decimal (`:.1f`).
4. A ✘ on "rolled 50° AND 41.23 °/s": the rate rule must come before the tilt rule.
5. The tilt: `tilt_deg(q)` is given at the top of the file.
</details>

## Step 9 — Check the bench against the flight

In a simulation we know the truth, so we can ask the flight itself which delay is right: try many settings and keep
the one whose attitudes agree best with the truth.

```bash
python3 run_timing.py scan
```

Open [out/scan.png](file:./out/scan.png).

> [!TASK]
> Write `BEST_LATENCY_S` (three decimals) and `EXPLAIN_SCAN`: compare it with your bench setting of Step 4. Why can
> a real plane not run this scan as it is?

## Step 10 — Live, over ROS

Now the same chain runs live: NAVERA Lite's camera node replays the flight in real time over ROS — the IMU on
`/navera_lite/imu`, one frame offered every 0.5 s — stamps every frame at its exposure with the delay of your
camera.yaml, and calls **your** `attitude_at`, `rotation_rate_dps` and `usable`. Start it, watch about ten frames,
then stop it with `Ctrl+C`:

```bash
python3 -m navera_lite.ros.camera_node
```

Each line is one frame: its roll, your rotation rate, your decision, and the attitude error (the replay knows the
truth). Open [out/live_frame.jpg](file:./out/live_frame.jpg): the last frame offered, as the camera saw it. Its
meta is a standard ROS message; while the node runs, a second terminal (**+** in the terminal tab) can read one:

```bash
ros2 topic echo /navera_lite/camera/meta diagnostic_msgs/msg/DiagnosticStatus --once
```

(Discovery takes a second or two: run it again if it waits.) Now two wrong programs. Stamp the frames at the grab
(no delay at all), watch the attitude error during the first roll (frames 90 to 150), then `Ctrl+C`:

```bash
python3 -m navera_lite.ros.camera_node --ros-args -p latency_s:=0.0
```

And a program that lets frames queue (a queue of 4, read twice a second); watch the "waited" values, then `Ctrl+C`:

```bash
python3 -m navera_lite.ros.camera_node --ros-args -p queue:=4
```

> [!TASK]
> Write `QUEUE_WAITED_S` (a typical "waited … s in the queue", two decimals) and `EXPLAIN_QUEUE`: the node
> subtracts the right delay — why is the attitude still wrong with a queue? (Lesson §1, the queue figure.)

## Step 11 — The memo

Write [report.md](file:./report.md) to your team (150–400 words, your own words, keep the four headings): the
camera's rhythm, its delay and the setting you chose, what the turn showed, and your recommendation. Quote your
numbers with their units.

> [!TASK]
> report.md has the four headings, at least 150 words, and quotes the grab log's frame rate, the bench's median
> delay, your delay setting, and the median error of the attitude held at the grab.

## Step 12 — With a real camera (optional, only if you booked one)

The class camera is shared: book it in the dashboard (**Hardware** → **Take** on the camera line), then open a
**new** terminal (only terminals opened after the booking see it), and run `python3 grab_real.py`. It never opens a
camera that another program is using; without a camera it says so and stops: that is fine, skip this step.
Compare the real rhythm with the grab log of Step 2, and put the numbers in your memo. Release the camera when you
finish (**Hardware** → **Release**). The camera films the room: do not save or share pictures of people who did not
agree.

## Step 13 — Check, then look back

Press **✔ Check my work**: it tests your functions on streams, benches, IMU histories and settings they have never
seen, and runs the live camera node with your code. When every check passes, you earn the **Shutter** badge. Then
look back, without the lesson:

1. Explain to a colleague, in three sentences, how an 83 m error came out of a 1 m match (the mission brief).
2. Which of your predictions was the most wrong? What did you assume?
3. Your delay setting is 10 ms wrong. In which flights does it matter, and in which can you ignore it?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **A robust jitter.** Add `"mad_ms"` to a copy of your `frame_stats`: 1.4826 × median(|dᵢ − median|). Compare it
  with the jitter on the first 40 s and on the whole 60 s of `grab_log.csv`. Which number would you use to raise a
  "camera stutters" alarm, and which one for "camera stalled"?
- **How many flashes?** Draw 5, 10 and 20 of the 20 bench delays at random, many times
  (`np.random.default_rng(1).choice(v, 10)`), and look at the spread of `median − T/2 − s`. Does it shrink like
  1/√N? How many flashes would you ask for?
- **The delay without a truth.** In flight there is no true attitude, but there is a second clock-free witness: the
  picture itself turns when the plane turns. Mission 22 measures the rotation between two frames; with it you could
  compare the image rotation with the IMU rotation over many delays — the same scan as Step 9, without a truth.
- **Fly your own slerp.** Swap the course's `rotations.py` for yours from mission 16 (keep a copy) and run
  `turn` again: `cp navera_lite/rotations.py rotations_course.py && cp ../16-rotations/navera_lite/rotations.py navera_lite/`.
