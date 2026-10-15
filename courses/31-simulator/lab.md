# Lab 31 — Close the loop: the bytes, the sensors, the campaign

**Goal:** be the test engineer of NAVERA Lite. Session 1 (**Messenger**): decode the bytes your stack sends to an
autopilot, and check the simulator's sensor models. Session 2 (**Test engineer**): fly NAVERA Lite in a closed
loop, inject faults, derive expected values from the rules, give verdicts, diagnose the run that fails — then fly
your own parts and your own networks.
**Time:** 4 h (fast) to 8 h (if bytes, statistics or Linux are rusty), plus the lesson (80–100 min).

| Lesson | Lab step | You write |
|---|---|---|
| §3 MAVLink | Steps 0–3 | `decode_gps_input` (TODO 1), `parse_frames` (TODO 2), `lost_frames` (TODO 3) |
| §4 the sensors | Steps 4–5 | `gauss_markov` (4), `stationary_sigma` (5), `autocorrelation` (6), `rayleigh_quantile` (7) |
| §5 campaigns | Steps 6–9 | `latencies` (TODO 8), `verdict` (TODO 9), your expected values, your diagnosis |
| §7 your stack | Steps 10–11 | one rule of your guard changed (`--part`), your networks measured |
| §5–§6 | Step 12 | your own scenario and requirement |

Your files: [navera_lite/output.py](file:./navera_lite/output.py) (TODO 1–3),
[navera_lite/sim/sensors.py](file:./navera_lite/sim/sensors.py) (TODO 4–7), [campaign.py](file:./campaign.py)
(TODO 8–9), [answers.py](file:./answers.py), [my_scenario.json](file:./my_scenario.json). Read, don't change:
[mav_lab.py](file:./mav_lab.py), [vision_check.py](file:./vision_check.py), `campaign/*.json` (the agreed
scenarios), and the given parts: `navera_lite/sim/world.py`, `sim/run.py`, `sim/vision.py`, and missions 21–30's
parts shipped finished.

> [!NOTE]
> The simulator flies over a 1 km × 3.8 km corridor west of Sousse, Tunisia (NAVERA's test area): fields, a
> motorway and the edge of a town, drawn from OpenStreetMap data (© OpenStreetMap contributors). The drone takes
> off at the south end and flies north at 15 m/s, 150 m high; the plane flies at 40 m/s, 300 m high. GPS: 5 fixes
> per second, σ 1.9 m stated (HDOP 0.95: the σ its noise model really has, Step 4). Vision: one fix per second, taken 0.1 s after a GPS fix and reaching the judge 0.3 s
> later.

# Session 1 — Messenger (about 2 h)

## Step 0 — The bytes (no code)

`/data/academy/31-simulator/gps_input.bin` is what an autopilot received on its serial link during 60 s of a
simulated flight of NAVERA Lite. First write `PREDICT_FRAME` in [answers.py](file:./answers.py), then:

```bash
python3 mav_lab.py hex
```

With the table of lesson §3, find where the first GPS_INPUT frame starts and name its header bytes (the first bytes
of the file are line noise: a real serial link has some). Copy its `len` byte, as a decimal number, into
`HEADER_LEN_BYTE`. Then compare with the answer and, after lesson §3, write `EXPLAIN_63`:

```bash
python3 mav_lab.py hex --answer
```

## Step 1 — Decode a payload (TODO 1)

🧰 **Padding bytes:** `b"\x01\x02" + bytes(3)` → `b"\x01\x02\x00\x00\x00"`. **Unpacking with names:**
`dict(zip(("a", "b"), (1, 2)))` → `{"a": 1, "b": 2}`. The format and the names are given in `output.py`:
`GPS_INPUT_FORMAT`, `GPS_INPUT_FIELDS`, `GPS_INPUT_LEN`.

Write `decode_gps_input(payload)` in [navera_lite/output.py](file:./navera_lite/output.py) (lesson §3, the worked
example). Then:

```bash
python3 mav_lab.py test
```

The three `decode_gps_input` lines should be ✔; the others stay ✘ until you write their TODOs.

<details><summary>Stuck? Hints, one at a time</summary>

1. Three steps: refuse a payload longer than 65 bytes; pad it to 65; unpack, then name the values.
2. `struct.unpack(GPS_INPUT_FORMAT, padded)` returns a tuple of 19 values in the order of `GPS_INPUT_FIELDS`.
3. lat and lon arrive as integers in 10⁻⁷ degree: divide them by `1e7` after naming.
4. `struct.error: unpack requires a buffer of 65 bytes`? You did not pad. lat = 358242433? You forgot the division.
</details>

## Step 2 — Find the frames in a stream (TODO 2)

🧰 **Walking through bytes with an index:** a `while i < len(data):` loop lets you jump: `i += 1` (one byte) or
`i += size` (a whole frame). `data[i + 1]` is an int; `data[i:i + n]` is bytes; `int.from_bytes(b, "little")`.

Write `parse_frames(data)` (lesson §3, the header table; the docstring says exactly what to return). The
checksum is given: `frame_crc(frame, msgid)`. Then `python3 mav_lab.py test` (the two `parse_frames` lines), and:

```bash
python3 mav_lab.py stream
```

Copy the number of frames with `crc_ok` False into `STREAM_BAD_CRC`. One frame has `crc_ok` None: look at its
message id. Where does it come from? Real parsers differ here: pymavlink (a MAVLink library) swallows that fake
frame whole and loses the HEARTBEAT and the GPS_INPUT hidden inside it (it finds 175 GPS_INPUT, you find 176).
Your resync rule is more robust, and costs more CPU.

<details><summary>Stuck? Hints, one at a time</summary>

1. At `i`: if `data[i]` is not 0xFD, or fewer than 10 bytes remain, step one byte. Else read `n = data[i + 1]`.
2. size = 10 + n + 2, plus 13 when `data[i + 2] & 1` (a signed frame). If `i + size > len(data)`: the frame is cut
   by the end — step one byte (it may not even be a frame).
3. `frame = data[i:i + size]`; msgid = the 3 bytes 7, 8, 9, little-endian; received checksum = bytes 10 + n and
   11 + n, little-endian; compare with `frame_crc(frame, msgid)` (None → crc_ok None).
4. After crc_ok True, jump `i += size`; after False or None, `i += 1` (resync: it was noise that looked like a
   frame).
5. The test shows 2 frames instead of 1 for "noise + 1 frame + a cut frame"? You returned the cut frame.
</details>

## Step 3 — Lost frames (TODO 3) and flags

🧰 **Modulo:** `(1 - 254 - 1) % 256` → 2 (Python's `%` is never negative for a positive divisor).

Write `lost_frames(seqs)` (lesson §3); `python3 mav_lab.py test` must show its line ✔. (`ignored(flags)`, which
turns a bit mask into names, is given in output.py: read its two lines — `flags & bit` is the whole trick.)
Then run `python3 mav_lab.py stream` again and copy `STREAM_LOST`, `STREAM_DOUBLED`, and the `ignore_flags` of the
frames sent while day vision flew (satellites 0) into `VISION_FLAGS`. Write `EXPLAIN_FLAGS` and `EXPLAIN_LOST`.
Open [out/stream.png](file:./out/stream.png): where did vision take over?

<details><summary>Stuck? Hints, one at a time</summary>

1. Walk over consecutive pairs, `for a, b in zip(seqs, seqs[1:]):`.
2. You get 255 lost for `[7, 7]`? A doubled frame: test `b == a` first.
3. A negative count after 255 → 0? Count modulo 256.
</details>

## Step 4 — The receiver's noise (TODOs 4–6)

🧰 **A numpy random generator:** `rng = np.random.default_rng(31)`; `rng.standard_normal(5)` → 5 numbers N(0, 1),
the same ones for the same seed. **An empty array to fill:** `out = np.empty(n)`, then `out[k] = x`.

Write `gauss_markov`, `stationary_sigma` and `autocorrelation` in
[navera_lite/sim/sensors.py](file:./navera_lite/sim/sensors.py) (lesson §4 and its worked examples). Run
`python3 mav_lab.py test` until their lines are ✔. Write `PREDICT_AVERAGE`, then:

```bash
python3 mav_lab.py noise
```

It generates one hour of receiver noise with your `gauss_markov` (the simulator's Δt, τ and q). Copy the measured
standard deviation into `GM_SIGMA_MEASURED` and your autocorrelation at 10 s into `CORR_10S`. Open
[out/noise.png](file:./out/noise.png). Then read lesson §4's box "after lab Step 4" and write `EXPLAIN_AVERAGE`.
Why is the measured σ not exactly your `stationary_sigma`, and the autocorrelation at 60 s not 0.049? (Hint: how
many correlation times are there in one hour?)

<details><summary>Stuck? Hints, one at a time</summary>

1. gauss_markov: check dt first; `w = rng.standard_normal(n)` before anything else; a = 1 − dt/τ; then a loop of n
   steps that updates x and stores it.
2. The first stored value is ONE step after x0 (not x0 itself).
3. stationary_sigma: from σ² = a²σ² + q²dt, solve for σ², then the square root.
4. autocorrelation: `d = np.asarray(x, float) - np.mean(x)`; the top is `np.sum(d[:-lag] * d[lag:])` (careful:
   lag = 0 is a special case: `d[:-0]` is empty), the bottom `np.sum(d * d)`.
5. Your gauss_markov values differ only after the first? You drew w one at a time inside the loop with another
   function, or used `rng.normal` with other arguments: draw all n at once, first.
</details>

## Step 5 — Vision errors (TODO 7)

Write `rayleigh_quantile(sigma, p)` (lesson §4) and check it with `python3 mav_lab.py test`. Write
`PREDICT_RAYLEIGH_95` (how many σ is the 95 % radius of a 2-D error: 1.96, 2.45 or 3?), then:

```bash
python3 mav_lab.py rayleigh
```

It draws 200 000 2-D errors for the target (σ 15 m) and the measured (σ 373.7 m) profiles. Was your prediction
right? Write `EXPLAIN_MEDIAN`.

Press **✔ Check my work**: checks 1–7 earn the 📡 **Messenger** badge.

<details><summary>Stuck? Hints, one at a time</summary>

1. Solve 1 − exp(−R²/(2σ²)) = p for R: exp(−R²/(2σ²)) = 1 − p, take ln, multiply by −2σ², square root.
2. `math.log` is ln. Refuse p outside [0, 1) and σ < 0 with a ValueError.
3. You get 17.7 for p = 0.95? You used ln(p) instead of ln(1 − p) somewhere — try p = 0.5, where both agree.
</details>

# Session 2 — Test engineer (about 3 h)

## Step 6 — A first flight

Write `PREDICT_JAM`, then fly the jam scenario of the campaign ([campaign/jam.json](file:./campaign/jam.json)):

```bash
python3 -m navera_lite.sim.run campaign/jam.json
```

It prints which parts fly (the course's), the events (mission seconds: faults, every change of NAVERA Lite's
state or source, the autopilot's events) and a summary; it writes `my_runs/jam.csv` (one row every 0.2 s) and
`my_runs/jam_events.log`. Open [my_runs/jam.csv](file:./my_runs/jam.csv) and find the columns `t_s`, `lite_source`,
`lite_err_m` (NAVERA Lite's error), `ap_err_m` (the autopilot's), `guard`, `gps_mode`. Copy into `JAM_RECOVER_S`
the time NAVERA Lite flies on the GPS again, minus 70 s. Look at the `guard` column just after 70 s: which rule of
mission 30 is acting, and what does it cost?

<details><summary>After your run: the same flight as a picture</summary>

![campaign/jam.json flown with the course's parts](assets/campaign.svg)

*Look at the band (the jam), the step of the source, and the two errors: NAVERA Lite's (dots) and the
autopilot's (line). Why is the autopilot's error smaller than NAVERA Lite's during the jam? (NAVERA Lite's error
is its latest position against the truth NOW: a held 1 Hz vision fix grows by 15 m per second of age.)*
</details>

## Step 7 — Measure a run (TODO 8)

🧰 **The first item that passes a test:** `next((r for r in rows if r["t_s"] >= 30.0), None)` → the first row at
or after 30 s, or None when there is none.

Write `latencies(rows, t0, t1)` in [campaign.py](file:./campaign.py) (lesson §5, the metric table). Then:

```bash
python3 campaign.py test
```

```bash
python3 campaign.py one jam
```

`one` prints every metric of a run (the others are given in `measure()`: read them). Does `switch_s` match what
you saw in the events?

<details><summary>Stuck? Hints, one at a time</summary>

1. Two searches with `next(...)`: the first over rows with `r["t_s"] >= t0` and a source that is not "gps";
   the second over rows with `r["t_s"] >= t1` and the source "gps".
2. Subtract t0 (or t1) from the row's time; keep None when `next` found nothing.
3. If t1 is None, recover_s is None — do not compare a number with None.
4. `(None, 0.0)` for the test "only gps"? That is right: the GPS never left, and it is there at t1.
</details>

## Step 8 — Expected values from the rules, then the verdict (TODO 9)

**Before** flying the campaign, write what the rules predict (lesson §5), in [answers.py](file:./answers.py):

- `EXPECT_OFF_SWITCH_S`: the GPS goes **silent** at 30 s (`campaign/off.json`). After how many seconds should
  NAVERA Lite stop using it? (Which setting of [navera_lite.yaml](file:./navera_lite.yaml)?)
- `EXPECT_JUMP_GATE_M`: the drone's jump gate for the next GPS fix, 0.2 s after the last trusted one (the runner
  gives the gate the drone's top speed, 30 m/s; the margin is in navera_lite.yaml).
- `EXPECT_DRIFT_SIGMA_S_M` and `EXPECT_DRIFT_REFUSED_S`: the guard against the campaign's drift
  (`campaign/drift.json`): the GPS drifts at 4.0 m/s, states σ 1.9 m; vision states σ 15 m; the GPS fix closest to a vision fix is 0.1 s away, so the guard's
  time-gap term is 30 m/s × 0.1 s = 3 m; p_fa 0.01, 5 disagreeing fixes in a row, one vision fix per second.
  Use mission 30's `drift_alarm_time` and `chi2_threshold_2d` (in `navera_lite/spoof.py`, finished).

<details><summary>Stuck on the drift? Hints, one at a time</summary>

1. drift_alarm_time(drift_mps, sigma_s_m, threshold, n, period_s): σ_s is the σ of the innovation on ONE axis —
   the square root of the sum of the three variances (mission 30 §3).
2. threshold = `chi2_threshold_2d(0.01)`.
3. `python3 -c "import math; from navera_lite.spoof import drift_alarm_time, chi2_threshold_2d; print(...)"`
</details>

Why do σ_s = 15.0, 15.1 and 15.4 m all give the same refusal time? (One test per second: the answer is rounded to
the test grid — which is why `EXPECT_DRIFT_SIGMA_S_M` is asked separately.)

Then write `verdict(value, op, limit)` in [campaign.py](file:./campaign.py) (lesson §5) and run
`python3 campaign.py test` until all lines are ✔.

<details><summary>Stuck? Hints, one at a time</summary>

1. Refuse an op that is not "<=" or ">=" (ValueError); a value None → ("FAIL", "never happened").
2. PASS when `value <= limit` (op "<=") or `value >= limit` (op ">=").
3. The text: `f"{value:g} {shown} {limit:g}"`, where `shown` is the operator that is TRUE: "<=" or ">" for a "<="
   requirement, ">=" or "<" for a ">=" one.
4. "4 <= 4" must PASS: the limit itself keeps the promise.
</details>

## Step 9 — The campaign, and the run that fails

```bash
python3 campaign.py run
```

```bash
python3 campaign.py report
```

`run` flies the seven scenarios of [campaign/](file:./campaign/) (about 10 s); `report` measures them with your
`latencies`, judges the nine requirements R1–R9 with your `verdict`, writes `results.json` and
[out/campaign.png](file:./out/campaign.png).

1. Copy the drift run's `switch_s` into `DRIFT_MEASURED_S` and compare it with your `EXPECT_DRIFT_REFUSED_S`:
   write `EXPLAIN_DRIFT`. (jam, off, jump and drift show `false_ref_s` 1.4: after a GPS outage the guard holds the
   returning GPS until two vision fixes agree — mission 30's "jam, then spoof" rule, a price paid on purpose. R9
   is about a GPS that never failed.)
2. One requirement FAILS: write its id in `FAILED`. Diagnose it with lesson §5's method. Useful commands:

```bash
cat my_runs/plane_late_events.log
```

```bash
python3 campaign.py one plane_late
```

   and in [my_runs/plane_late.csv](file:./my_runs/plane_late.csv) the columns `gps_err_m`, `vis_err_m`, `guard`,
   `lite_source`, `lite_err_m` around 20–30 s. Which source is wrong, by how much, and why that much? Write
   `EXPLAIN_FAIL` (step by step, and the fix).
3. Confirm your hypothesis with a variant that changes ONE thing: the same flight, the camera still 1.5 s late,
   but each picture stamped with its own time:

```bash
python3 -m navera_lite.sim.run campaign/plane_delayed.json
```

```bash
python3 campaign.py one plane_delayed
```

Then read lesson "In NAVERA", the box "after lab Step 9".

<details><summary>Stuck on the diagnosis? Hints, one at a time</summary>

1. Which source is honest here? Look at `gps_err_m` (the GPS's own error) — and at the scenario: no GPS fault at
   all.
2. Look at `vis_err_m` after 20 s. How far does a plane fly in 1.5 s?
3. What does the guard compare, and with which time stamps (mission 30 §3, the time-gap term)?
4. Why does it stay refused for so long (mission 30 §5: how does a refused GPS come back)?
</details>

## Step 10 — Your own stack in the loop

The same campaign, with **your** parts (lesson §7):

```bash
python3 campaign.py run --mine
```

```bash
python3 campaign.py report --mine
```

The first lines of each flight's events (`my_runs/mine/*_events.log`, lines `# part`) say which parts were yours
and why any was not (not found, a TODO left, an error — a part of yours that crashes during a flight is replaced by
the course's for that flight, and the line says why). Compare `results_mine.json` with `results.json`. Your parts
probably give the course's numbers: they passed the same checks. To fly without one of your parts:
`python3 campaign.py run --mine --not spoof` (arbiter, spoof or kalman).

**A regression test that catches something.** A regression test is worth something only if it catches a change.
Copy your guard (`cp ../30-spoofing/navera_lite/spoof.py my_spoof.py`; if you have none, copy the course's:
`cp navera_lite/spoof.py my_spoof.py`), change ONE rule in [my_spoof.py](file:./my_spoof.py) — for example
`"confirm_n": 2` → `6`, `"refuse_n": 5` → `2` or `"p_fa": 0.01` → `0.1` in `GUARD_DEFAULTS` — and **predict**
which requirement moves (perhaps none: a metric can move while every verdict stays).
Then fly and judge it:

```bash
python3 campaign.py run --mine --part spoof=my_spoof.py
```

```bash
python3 campaign.py report --mine
```

Compare [out/campaign_mine.png](file:./out/campaign_mine.png) with [out/campaign.png](file:./out/campaign.png). Write
`EXPLAIN_MINE` about this flight: the rule you changed, your prediction, which requirement moved (or why none did).

## Step 11 — Your networks in the loop

First measure them on the corridor (about 1 minute; your weights from missions 21 and 25, or the course's when
yours are missing):

```bash
python3 vision_check.py
```

It writes `my_vision_profile.json`: the median error of each network, the σ it implies (lesson §4), and the σ
your vision sources will **state** in "mine" flights. Copy the night median into `NIGHT_MINE_MEDIAN_M`. Then fly a
night mission, GPS jammed at 20 s, with your night network locating every thermal picture:

```bash
python3 -m navera_lite.sim.run campaign/night_mine.json --mine
```

Look at `vis_err_m`, `lite_err_m`, `lite_state` and `ap_err_m` in `my_runs/mine/night_mine.csv`, and at the
line `# part stated σ` of its events. **Is your night source FIX or DEGRADED?** Compare the σ it states with
`fix_max_sigma_m` in [navera_lite.yaml](file:./navera_lite.yaml): a network measured at σ 25.2 m states 25.2 m and
flies DEGRADED — a few decimetres of honesty change the state the judge gives it, and what the autopilot does
with it. (By day: `campaign/day_mine.json`, about 2 minutes, runs your PatchNet on about 100 photos — optional.)
Write `EXPLAIN_NETWORKS`: what your network did in the loop, the state it got and why, what makes these numbers
optimistic (lesson §6), and what an honest measurement would need. Never edit `my_vision_profile.json` by hand: the
check measures your night network again.

## Step 12 — Your own test

Design one test: edit [my_scenario.json](file:./my_scenario.json) — your own `name`, at least one fault (the
sensors and modes are listed in lesson §5; `"imu"` with `"bias"` or `"off"`, `"light": "night"`, `"vehicle"` …),
and a `duration_s`. ⚠️ `campaign.py one` measures from the **first** fault in your list (t0) to the moment **that
same sensor** comes back (t1): put the fault you want to measure first. Write the requirement FIRST (`MY_METRIC`, `MY_OP`, `MY_LIMIT`), then fly and measure:

```bash
python3 -m navera_lite.sim.run my_scenario.json
```

```bash
python3 campaign.py one my_run
```

(replace `my_run` by your scenario's name). Copy the value into `MY_VALUE` (`None` if it never happened) and write
`MY_VERDICT`, `EXPLAIN_MY_TEST` and `EXPLAIN_PROVES`.

Press **✔ Check my work**: all 16 checks earn the 🧪 **Test engineer** badge.

> [!TASK]
> Done means: TODOs 1–9 written; `answers.py` complete; `results.json`, `results_mine.json`,
> `my_vision_profile.json` and the runs of Steps 9–12 in `my_runs/` written by the tools (not by hand).

## Look back (not graded)

1. Which defect of this lab would a unit test of `output.py` have found, and which needed the loop?
2. Your campaign PASSES R7 (drift ≤ 100 m) with vision at the target accuracy. Would it pass with vision
   "measured" (no stated σ)? What would that tell a buyer?
3. Which number of this lab would you NOT put in a brochure, and why?

## Going further (optional)

- **The guard without a stated reference.** Copy `campaign/drift.json` to `my_scenario.json` with
  `"vision": "measured"` and another name; fly it and measure `max_err_m` (mission 30 §6: what the guard cannot
  catch).
- **IMU off and GPS jammed.** No attitude → no vision → … ? Predict the failsafe time, then fly it.
- **Sim Lite.** The 🛩️ Simulator tab flies the same world in your browser with your NAVERA Lite (your parts where
  you have finished them; a browser cannot run PyTorch, so "My networks" draws errors from your measured profile).
  Press **Fly my scenario**, save the run, and compare its CSV with yours (same world, same seed).
- **The 10-bit week.** `time_week` and `time_week_ms` give the instant in **GPS time**: weeks since 6 January 1980,
  no leap seconds (18 s ahead of UTC). The satellites' own message carries the week in only **10 bits** (0–1023): it
  rolled over to 0 on 22 August 1999 and again on **6 April 2019**, and some older receivers jumped back 19.6 years.
  `GPS_INPUT`'s `time_week` is 16 bits. Decode `time_week` of the first GPS_INPUT and compute what a receiver with a
  10-bit counter would display: which date would it believe?
