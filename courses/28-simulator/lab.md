# Lab 28 — Decode the link, check the models, analyse a fault-injection campaign

**Goal:** work like a test engineer on NAVERA's mission simulator. You will (A) decode, byte by byte,
the MAVLink messages NAVERA sends to the autopilot, (B) check the simulator's sensor models against
their theory, (C) turn a recorded fault-injection campaign of five flights into measurements and
PASS / FAIL verdicts, (D) write a short test report, and (E) if the simulator is free, fly your own
scripted scenario.
**Time:** about 3 hours (Part E adds 20 minutes).

Your files:

| File | Part | What you do |
|---|---|---|
| [mavlink_lab.py](file:./mavlink_lab.py) | A | TODO 1–5: CRC, frame parser, GPS_INPUT decoder |
| [sensor_models.py](file:./sensor_models.py) | B | TODO 1–5: Gauss–Markov noise, Rayleigh quantiles, a Monte Carlo |
| [campaign.py](file:./campaign.py) | C | TODO 1–7: metrics and requirements; writes `results.json` |
| [report.md](file:./report.md) | D | your test report |
| [answers.py](file:./answers.py) | C | six short answers |
| [sim_ctl.py](file:./sim_ctl.py), [my_scenario.json](file:./my_scenario.json) | E | drive the simulator (no change needed in `sim_ctl.py`) |

The recorded data is in `/data/academy/28-simulator/` (read only). NAVERA's test map covers
**Sousse, Tunisia**, so every flight flies there.

> [!NOTE]
> **Parts A–D need no simulator.** The simulator is shared by the whole class and is often busy. The
> campaign you analyse was recorded with exactly the tools of Part E (`record_sample.sh` and
> `record_campaign.sh` in the data folder show how). If you cannot use the simulator, set
> `NO_SIMULATOR = True` in `answers.py` and the Part E check is skipped.

## Part A — MAVLink, byte by byte

### Step 1 — Look at the raw bytes

The file `gps_input.bin` is what NAVERA's `vehicle_output` would send to the autopilot during the
sample flight: a `HEARTBEAT` and a `GPS_INPUT` per second, packed by NAVERA's own
`mavlink_out.gps_input_fields()` (one row per second of the recording, not 5 Hz). Three frames were
damaged on purpose, and two frames are missing. Look at the first 64 bytes:

```bash
od -A d -t x1 -N 64 /data/academy/28-simulator/gps_input.bin
```

You should recognise `fd 09 00 00 00 01 bf 00 00 00`: a MAVLink 2 frame (`fd`), 9 bytes of payload,
sequence 0, system 1, component 191, message id 0 — a `HEARTBEAT`. The next frame starts at byte 21
with `fd 3e`.

### Step 2 — The checksum (TODO 1)

Complete `crc_x25(data, crc=0xFFFF)` in [mavlink_lab.py](file:./mavlink_lab.py) with the three lines
of the lesson (section 3). Python's `^` is XOR, `&` is AND, `<<` and `>>` are shifts. Test it with the
standard check value:

```bash
python3 -c "import mavlink_lab as m; print(hex(m.crc_x25(b'123456789')))"
```

You must see `0x6f91`. If you see a huge number, you forgot to keep `crc` on 16 bits (`& 0xFFFF`).

### Step 3 — The frame parser (TODO 2)

Complete `parse_frames(data)`. It returns a list of dicts, one per frame:
`{"seq", "sysid", "compid", "msgid", "payload", "crc_ok"}`. Follow the comments in the file. Two
details matter:

- the CRC covers `data[i+1 : i+10+n]` (from `len` to the end of the payload), **then** one more byte,
  `CRC_EXTRA[msgid]`: `crc = crc_x25(bytes([CRC_EXTRA[msgid]]), crc)`;
- the received checksum is little-endian: `data[end-2] | (data[end-1] << 8)`.

```bash
python3 mavlink_lab.py
```

You should now see the first four frames, alternating `msgid 0` (len 9) and `msgid 232` (len 62 —
not 65!), all with `crc_ok True`.

### Step 4 — Decode GPS_INPUT (TODO 3–5)

- **TODO 3** `decode_gps_input(payload)`: pad with zero bytes to `GPS_INPUT_LEN` (65), then
  `struct.unpack(GPS_INPUT_FORMAT, ...)`, `dict(zip(GPS_INPUT_FIELDS, values))`, and divide `lat` and
  `lon` by 1e7. Without the padding, `struct` raises `struct.error: unpack requires a buffer of 65 bytes`.
- **TODO 4** `ignored(flags)`: the names of the bits that are set (`flags & (1 << bit)`).
- **TODO 5** `gps_time_to_utc(week, week_ms)`: GPS time starts on 1980-01-06 and is 18 s ahead of UTC.

```bash
python3 mavlink_lab.py
```

The decoded frame #100 must be near Sousse (35.82° N, 10.64° E), a 3D fix with
`horiz_accuracy 1.4 m` and `ignore 48 ['VEL_VERT', 'SPEED_ACCURACY']`, and its GPS time must be on
**2026-10-07 around 10:15 UTC**. The last line is a summary: frames, bad CRCs, lost frames (from the
gaps in `seq`), and the fixes grouped by `ignore_flags`.

> [!QUESTION]
> The summary groups the 3D fixes by `ignore_flags`: 48, 56 and 57. Which source sends each? Why does
> exactly one GPS frame have 56? (Hint: what does bit 3 mean, and what is special about the very first
> GPS fix of a flight?)

> [!TASK]
> **Part A.** Complete TODO 1–5 in `mavlink_lab.py`. "Done" means: `crc_x25(b"123456789") == 0x6F91`;
> `parse_frames()` finds every frame of `gps_input.bin` with the right header fields and `crc_ok`
> (exactly 3 bad); `decode_gps_input()` handles truncated payloads; `ignored()` and
> `gps_time_to_utc()` are exact. The check also feeds your parser a frame it has never seen.

## Part B — The simulator's sensor models

### Step 5 — Read the real models

Open the simulated GNSS receiver of your NAVERA copy and find `reported()`:
[nmea_gps.py](file:navera/navera_tools/sim/nmea_gps.py). Then the vision profiles in the simulator:

```bash
grep -n "SIGMA\|MEASURED" ~/navera/navera_tools/sim/sim_server.py | head
```

Write down the numbers: Δt = 0.2 s, τ = 20 s, q = 0.6, target σ = 15 m, measured median 440 m.

### Step 6 — Gauss–Markov noise (TODO 1–3)

In [sensor_models.py](file:./sensor_models.py):

- **TODO 1** `gauss_markov(n_steps, dt, tau, q, seed, x0)`: the recursion of the lesson. Draw all the
  random numbers first, `w = rng.standard_normal(n_steps)`, so that the same seed gives the same series
  as the check.
- **TODO 2** `stationary_sigma(dt, tau, q)`: σ = q·√(Δt / (1 − a²)).
- **TODO 3** `autocorrelation(x, lag)`.

### Step 7 — Rayleigh and Monte Carlo (TODO 4–5)

- **TODO 4** `rayleigh_quantile(sigma, p)` and `sigma_for_median(median)`.
- **TODO 5** `lagged_vision_errors(sigma, speed, period, n, seed)`: a vision fix is made once per
  second; the recorded position is the last fix, so it lags behind a drone flying at 15 m/s by
  `speed × U(0, period)` metres. Simulate it.

```bash
python3 sensor_models.py
```

Expected: the simulated σ within 2 % of the theory (≈ 1.90 m), the autocorrelation after τ close to
1/e, the target median 17.66 m and 95 % 36.72 m, the measured-profile σ 373.7 m. Open
[models.png](file:./models.png) to see the noise, its autocorrelation and the Rayleigh histogram.

> [!TASK]
> **Part B.** Complete TODO 1–5 in `sensor_models.py`. The check compares your functions with the
> theory and with its own reference series (same seed), and tests other parameters than the default ones.

## Part C — Analyse the campaign

### Step 8 — Meet the data

```bash
ls -l /data/academy/28-simulator/campaign/
```

| Flight | Vision profile | Faults (seconds after "en route") |
|---|---|---|
| `jam_spoof_target` | target | GPS jammed 60 s; 40 s later spoof jump 2 km for 30 s |
| `jam_spoof_measured` | measured (DEGRADED, forwarded) | the same |
| `drift_target` | target | GPS spoof drift 4 m/s from +30 s to +110 s |
| `off_target` | target | GPS off from +30 s to +70 s |
| `jam_camfail_target` | target | GPS jammed at +30 s, camera failed at +50 s, both OK at +90 s |

Look at the columns and at a few rows during the drift:

```bash
head -3 /data/academy/28-simulator/campaign/drift_target.csv
```

```bash
grep -E "FAULT|NAVERA:|failsafe|LAND" /data/academy/28-simulator/campaign/jam_camfail_target_events.log
```

And what the arbiter itself logged during the last three flights:

```bash
grep -E "ERROR|WARN" /data/academy/28-simulator/campaign/estimator_campaign.log
```

### Step 9 — Load, error, intervals (TODO 1–3)

In [campaign.py](file:./campaign.py):

- **TODO 1** `load_flight(path)`: like lesson 4's CSV reading, but robust: a column can be **missing**
  (`jam_spoof_measured.csv` has no `navera_err_m`, older flights have no `camera`). Use `r.get(k)`.
- **TODO 2** `nav_error(r)`: compute the error yourself from the coordinates with `haversine_m()`
  (given). Do not trust the simulator's own `navera_err_m` column — it is not in every file.
- **TODO 3** `fault_intervals(rows, column, normal="ok")`: e.g. for the sample flight and `"gps_mode"`:
  `[(110.8, 171.2, 'jammed'), (210.6, 240.8, 'spoof_jump')]`.

```bash
python3 -c "import campaign as c; r = c.load_flight('/data/academy/28-simulator/campaign/jam_spoof_target.csv'); print(len(r), c.fault_intervals(r, 'gps_mode'))"
```

### Step 10 — Metrics (TODO 4–6)

- **TODO 4** `first_time(rows, condition, after)`, then `switch_latency` and `recovery_latency`. A
  **lambda** is a one-line function: `lambda r: r["navera_source"] != "GPS"` is a function that takes a
  row and returns True or False. So `first_time(rows, lambda r: r["navera_source"] != "GPS", t0)` is
  "the first time at or after t0 when NAVERA is not on GPS".
- **TODO 5** `availability(rows, t0, t1)` and `error_stats(rows, t0, t1)` (median, 95th percentile,
  maximum; `np.percentile` with its default linear interpolation).
- **TODO 6** `spoof_leak_s(...)` (seconds on a GPS more than 100 m wrong) and `gps_err_max(...)`.

```bash
python3 campaign.py --flight /data/academy/28-simulator/campaign/off_target.csv
```

### Step 11 — Requirements and the campaign table (TODO 7)

`REQUIREMENTS` lists R1–R6 as tuples `(id, applies to, text, measured key, test)`. **TODO 7**: add
R7 for the slow drift (see the comment). Then run the whole campaign:

```bash
python3 campaign.py
```

It prints one block per fault with its verdicts and writes `results.json` (the campaign, plus the
summaries of Parts A and B).

> [!WARNING]
> **Resolution and bias.** The flights have one row per second, and the recorder writes a row *before*
> it injects a fault, so the first row that shows a fault is up to 1 s after the real instant. Compare
> the latency `campaign.py` gives for the GPS-off flight with the times in
> `off_target_events.log` (`FAULT INJECTED` and `NAVERA: FIX — DAY VISION`). Answer Q1 of
> [answers.py](file:./answers.py) from the log, not from the CSV.

> [!TASK]
> **Part C.** Complete TODO 1–7 in `campaign.py`, run `python3 campaign.py` so that `results.json`
> exists and contains the whole campaign (the check recomputes every metric from the data and
> compares), and answer Q1–Q6 in `answers.py`.

## Part D — The test report

### Step 12 — Write report.md

Fill [report.md](file:./report.md): the five sections are already there. Use **your** numbers from
`results.json`. Write clear, short sentences; a table is better than a paragraph for results.

> [!TASK]
> **Part D.** `report.md` has the five sections (*Set-up*, *Results*, *Observations*, *Fidelity*,
> *Next campaign*), at least 350 words, the total of PASS verdicts, and these numbers from your
> `results.json`: the drift's `gps_err_max_m`, the target profile's Rayleigh median
> (`target_median_m`) and the lagged Monte Carlo median (`lagged_median_m`). The *Fidelity* section
> must say clearly that these are **behaviour** results, not accuracy results.

## Part E — Your own scripted run (needs the simulator)

Skip this part if the simulator is not available today (`NO_SIMULATOR = True`).

### Step 13 — Take the simulator

1. **Hardware** (top bar) → *Mission simulator* → **Take**. Then open a **new** terminal tab: its first
   line says `[this terminal has access to: sim]`.
2. Check that nobody uses the simulator's ports — this must print **nothing**:

```bash
ss -ltn | grep -E ':(8181|8190|8443|5760|5762) '
```

3. Start the simulator on your own ROS domain, and leave this terminal alone (it *is* the simulator;
   `Ctrl+C` there stops it):

```bash
mkdir -p ~/.navera_sim && cd ~/navera && NAVERA_SIM_DOMAIN=$ROS_DOMAIN_ID navera_tools/run_sim.sh 2>&1 | tee -i ~/.navera_sim/run_sim.out
```

Wait for `simulator ready on port 8190`.

### Step 14 — Run your scenario

Edit [my_scenario.json](file:./my_scenario.json): choose **one** question you want to answer (e.g.
"does a 10 s jam give the same recovery as a 40 s jam?", "what does a drift do with the measured
vision profile?"). Faults: `gps` → `ok | jammed | spoof_jump | spoof_drift | off`, `camera` →
`ok | failed`; times in seconds after the drone starts flying to its destination; keep the whole
scenario under 150 s after "en route" (the route is ~4 km). Then, in a second terminal:

```bash
python3 sim_ctl.py campaign my_scenario.json --out-dir my_runs
```

It takes about 4 minutes: start, alignment on NAVERA's GPS (30–60 s), take-off, your faults, stop.
Meanwhile, watch the **🛩️ Simulator** and **🧭 Operator view** tabs. `my_runs/<name>_events.log` also
records the exact instant of each injection (`[inject]` lines).

### Step 15 — Stop and release

1. In the simulator's terminal: `Ctrl+C`, and wait for the prompt.
2. Check that the ports are free again (must print nothing): run the `ss -ltn …` command of Step 13.
3. **Hardware** → Mission simulator → **Release**.

Then analyse your run with the rest of the campaign (`campaign.py` also reads `my_runs/*.csv`):

```bash
python3 campaign.py
```

> [!TASK]
> **Part E.** `my_runs/` contains your scripted flight (at least 30 s en route with at least one injected
> fault), and `results.json` includes it. Add one paragraph about it to *Observations* in your report.
> Press **✔ Check my work**.

## Going further (optional)

- **Check NAVERA's encoder against pymavlink.** pymavlink is installed: decode `gps_input.bin` with
  `from pymavlink.dialects.v20 import ardupilotmega as m; mav = m.MAVLink(None); mav.robust_parsing = True;
  msgs = mav.parse_buffer(open(path, 'rb').read())` and compare every field with your decoder.
  How does pymavlink report the three damaged frames?
- **Repeatability.** The simulator's noise is random: the same scenario never gives exactly the same
  numbers. Run one scenario three times (Part E) and compare the latencies and the drift's
  `gps_err_max_m`. How many runs would you need to state a 95th percentile honestly? (Lesson 29.)
- **A better recorder.** Change a copy of `sim_ctl.py` so that it records at 5 Hz and stamps each fault
  with its injection instant in the CSV itself. What is then the measured switch latency of a jam?
- **Unit test.** NAVERA has unit tests for its MAVLink encoder: find them in `~/navera/navera_output/`
  and run them with `python3 -m pytest`. Which property of `ignore_flags` do they check?
