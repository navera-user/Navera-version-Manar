# Lab 1 — First contact: the Jetson, NAVERA and a GNSS solver

**Goal:** run your first commands on the NAVERA computer, find real parameters in your NAVERA copy,
run a GNSS position solver and break it on purpose (too few satellites, spoofing), apply the
arbiter's jump gate, and write a short threat analysis.
**Time:** about 2 hours.

Your files (open in the **📝 Code** tab): [hello_navera.py](file:./hello_navera.py),
[gnss_fix.py](file:./gnss_fix.py), [answers.py](file:./answers.py) and
[threats.md](file:./threats.md). Write your answers in `answers.py` as you go.

## Step 1 — The computer

Click the **⌨️ Terminal** tab. The line `student@navera:~/lessons/01-welcome$` is the **prompt**:
user `student`, computer `navera`, current folder `~/lessons/01-welcome` (`~` is your home folder,
`/home/student`). Run these commands one by one (▶ Run, or type them and press `Enter`):

```bash
whoami
```

```bash
pwd
```

```bash
ls
```

```bash
uname -m
```

```bash
nproc
```

```bash
python3 --version
```

`uname -m` prints the processor architecture: `aarch64` is 64-bit ARM, the kind of processor of
the NVIDIA Jetson inside a NAVERA box (not the `x86_64` of most laptops). `nproc` prints the number
of CPU cores available to you.

> [!TASK]
> In `answers.py`, write `ARCH` (text, in quotes) and `CPU_CORES` (a number, no quotes).

## Step 2 — The mission card (your first Python edit)

```bash
python3 hello_navera.py
```

The card does not know you yet. In [hello_navera.py](file:./hello_navera.py), replace the three
`"???"` **between the quotes** with your own name, a vehicle (`drone`, `car`, `boat` or `robot`)
and your home town. Save with `Ctrl+S` and run again:

```bash
python3 hello_navera.py
```

> [!WARNING]
> Keep the quotes. If you delete one, Python stops with
> `SyntaxError: unterminated string literal (detected at line 4)`: the line number tells you where
> to look. Put the quote back and run again.

## Step 3 — Your NAVERA copy

List the top folder of your copy:

```bash
ls ~/navera
```

You see about forty names. Don't worry: most are support. These are the ones this course uses:

| Name | What it is |
|---|---|
| `gps_pkg`, `day_pkg`, `night_pkg`, `cn_pkg`, `imu_pkg` | the sources (GPS, day vision, night vision, celestial, IMU) |
| `navera_estimator` | the arbiter (`estimator_node`) |
| `navera_output` | the output to the autopilot |
| `navera_msgs` | the message definitions (`PositionEstimate`, `NavStatus`) |
| `navera_common` | shared Python code (geodesy, tracks, parameters) |
| `navera_tools`, `simulation_web` | simulator, test and operator tools |
| `docs` | the product documentation (architecture, validation status) |
| `build`, `install`, `log` | made by the build tool (lesson 9): never edit them |
| other files (`CLAUDE.md`, `AUDIT.md`, `camera_pkg`, `rtc_pkg`…) | not used in this course: you can ignore them |

The `isaac_ros_*` folders are interface packages from NVIDIA; `deploy`, `docker`, `scripts` install
the product on a real box.

Now read the arbiter's parameters. Open
[estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml)
in the editor, or print the important lines in the terminal:

```bash
grep -n "timeout_s\|max_speed\|margin\|fix_max_sigma" ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

(`grep` prints the lines that contain one of the words; `-n` adds line numbers. Lesson 2 explains it.)
Then the list of sources in the message every source publishes:

```bash
grep -n "SOURCE_" ~/navera/navera_msgs/msg/PositionEstimate.msg
```

Finally, the first lines of NAVERA's validation document — the honest list of what is measured:

```bash
head -n 22 ~/navera/docs/VALIDATION_STATUS.md
```

> [!TASK]
> Write `GPS_TIMEOUT_S`, `FIX_MAX_SIGMA_M` and `SOURCE_DAY_VISION` in `answers.py` (numbers).

## Step 4 — A GNSS solver: four unknowns

[gnss_fix.py](file:./gnss_fix.py) simulates a receiver at Muscat that sees up to 8 satellites,
computes their pseudoranges (with a clock bias and noise) and solves for `x, y, z` and the clock
bias with Gauss–Newton least squares, as explained in the course. Read the settings at the top of
the file, then run it:

```bash
python3 gnss_fix.py
```

The clock was set 0.5 µs wrong, i.e. `c × 0.5 µs = 149.9 m` on every pseudorange. The solver
**finds** that bias (close to 149.9 m, not exactly, because of the noise), and the position error
stays a few metres.

> [!TASK]
> Write `BIAS_FOUND_M` (the "clock bias found" line, default settings).

Now change the settings at the top of `gnss_fix.py` (edit, `Ctrl+S`, run again each time) and fill
this table for yourself:

| `USE_SATELLITES` | horizontal error (m) | residual RMS (m) | PDOP |
|---|---|---|---|
| 8 | | | |
| 6 | | | |
| 5 | | | |
| 4 | | | |
| 3 | | | |

```bash
python3 gnss_fix.py
```

What happens at 3 satellites? Look at the **residual** at 4: why is it exactly 0? (Count the
equations and the unknowns.) And why does PDOP grow when satellites are removed?

> [!TASK]
> Write `H_ERR_4_SATS_M` and `RESID_4_SATS_M` (with `USE_SATELLITES = 4`, the other settings as
> delivered).

Now be the attacker. Put `USE_SATELLITES = 8` back and set `SPOOF_EAST_M = 500.0`: the spoofer
computes all the signals for a position 500 m east of the truth.

```bash
python3 gnss_fix.py
```

The fix moves about 500 m east — and the residual RMS looks perfectly normal. Nothing inside the
receiver says "spoofed".

> [!TASK]
> Write `SPOOF_H_ERR_M` and `SPOOF_RESID_M`. Then put every setting back to its delivered value
> (8, 0.5, 3.0, 0.0) and check that `python3 gnss_fix.py` runs.

> [!TIP]
> Try `CLOCK_BIAS_US = 2.0` too: the solver finds about 600 m of bias, and the position is as good
> as before. A clock bias, however large, is not a problem — it is just the fourth unknown.

## Step 5 — The arbiter's jump gate

The arbiter refuses a new GPS fix when its distance to the last trusted fix is larger than
`v_max · Δt + margin`. With the product's defaults you read in Step 3 (`max_speed_mps`,
`gps_jump_margin_m`) and a fix that comes **2.0 s** after the last trusted one:

> [!TASK]
> Compute `GATE_M`, the distance (m) beyond which the new fix is refused, and write it in
> `answers.py`. Would the 500 m spoof of Step 4 pass the gate if it appeared in one jump? And if the
> spoofer moved the position by 20 m per second?

## Step 6 — Threat analysis

> [!TASK]
> Fill [threats.md](file:./threats.md): for **outage**, **jamming**, **spoofing** and
> **meaconing**, write 3–5 sentences each (at least 150 words in total): what happens to the
> receiver, what an autopilot with GNSS alone would do, and which NAVERA source or rule helps, with
> its limit. Use your results of Steps 4–5.

## Step 7 — Quiz

> [!TASK]
> Answer `Q1`–`Q7` in `answers.py` (one letter each). The course tab has everything you need.

## Step 8 — Check your work

Press **✔ Check my work** at the bottom left. Each red line says what is wrong and gives a hint.
Fix, save, check again — as many times as you like.

## Going further (optional)

- **Jammer range.** With the formula of the course, at what distance does a 1 W jammer give
  J/S = 24 dB? And a 10 mW one? (Answers: about 80 km and 8 km in free space — real ranges are
  shorter because of the Earth's curvature and obstacles, but a drone at altitude sees far.)
- **Read the arbiter.** Open
  [estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py) and
  read its first docstring (lines 1–60). Find the sentence that explains why "reachable again" is
  not enough to re-accept GPS after a spoof.
- **Your own sky.** In `gnss_fix.py`, the list `SKY` gives the satellites' azimuth and elevation.
  Put four satellites all at elevation 15°–25° in the same quarter of the sky: how big does PDOP
  get, and the error?
