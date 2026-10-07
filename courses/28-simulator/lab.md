# Lab 28 — Fly, jam, spoof, and read the logs

**Goal:** start the mission simulator, fly a drone mission over Sousse, jam the GPS in flight, then
spoof it, record what happens, stop everything cleanly — and answer questions from the logs with a few
small Python functions.
**Time:** about 1 h 30 (the flight itself: about 10 minutes).

Your files: [sim_ctl.py](file:./sim_ctl.py) (drive and record the simulator from the terminal — no
change needed), [flight_log.py](file:./flight_log.py) (TODO 1–5), [answers.py](file:./answers.py).

> [!WARNING]
> **The simulator is shared by the whole class.** Take it first (Step 1), fly, then **stop it and release
> it** (Step 7) — others are waiting. If the teacher tells you the simulator is not available today, jump
> to **"No simulator?"** at the end: you will work on a recorded flight instead.

## Step 1 — Book the simulator and open a terminal that may use it

1. Click **Hardware** (top bar) → next to *Mission simulator*, **Take**. If someone else holds it, wait
   or ask the teacher.
2. Open a **new** terminal tab (**⌨️ Terminal** → **＋ new**). Its first line says
   `[this terminal has access to: sim]`. Only terminals opened *after* taking it have that access.
3. Check that nobody uses the simulator's ports — this command must print **nothing**:

```bash
ss -ltn | grep -E ':(8181|8190|8443|5760|5762) '
```

## Step 2 — Start the simulator

In that terminal:

```bash
mkdir -p ~/.navera_sim && cd ~/navera && NAVERA_SIM_DOMAIN=$ROS_DOMAIN_ID navera_tools/run_sim.sh 2>&1 | tee -i ~/.navera_sim/run_sim.out
```

`NAVERA_SIM_DOMAIN=$ROS_DOMAIN_ID` runs the simulator's ROS nodes on **your own** ROS domain (lesson
9), so your other terminals can listen to them and nobody else's NAVERA can hear them. `tee` shows the
simulator's messages and also saves them in `~/.navera_sim/run_sim.out` (`-i`: tee ignores `Ctrl+C`, so
the simulator can finish writing while it stops).

Wait for `simulator ready on port 8190`. **Leave this terminal alone** — it *is* the simulator; `Ctrl+C`
there stops it.

> [!NOTE]
> The first lines say `NAVERA nodes started (ROS_DOMAIN_ID=…)` and `GPS receiver on /dev/pts/…`: the
> real `gps_node` is reading the simulated receiver through a **pseudo serial port**, exactly as it reads
> `/dev/ttyTHS1` on the box.

## Step 3 — Start recording

Open a **second** terminal and go to the lesson folder:

```bash
cd ~/lessons/28-simulator && python3 sim_ctl.py record --seconds 900
```

Every second it writes a line to `flight.csv` (truth, NAVERA's state, source, position and error, the
autopilot's mode and error, the GPS fault) and the simulator's events to `events.log`. Every 10 s it
prints a summary. Leave it running.

## Step 4 — Launch a mission

Open the **🛩️ Simulator** tab (⟳ Reload if it was opened before the simulator started).

1. Vehicle: **Drone**.
2. Route: click the map near Sousse for the departure **A**, then a destination **B** 3–5 km away,
   **over land** (the drone flies ~15 m/s: 4 km takes about 4–5 minutes).
3. Conditions: **Day**, keep the default speed and altitude.
4. **Advanced settings** → *Position when GPS is lost* → **Simulated — target** (15 m, not a measured
   performance: it is light on the Jetson and lets the cross-check of lesson 27 work).
5. **Launch mission**.

> [!TIP]
> The same from a terminal (third terminal, in the lesson folder): `python3 sim_ctl.py mission` flies
> from the simulator's default start in Sousse to a point 4 km south-west, with the target profile. And
> `python3 sim_ctl.py status` prints one line about the flight at any time.

Watch the phases in the flight monitor: *aligning on NAVERA's GPS* (30–60 s), *arming*, *taking off*,
*flying to the destination*. Open the **🧭 Operator view** tab too: this is the screen a real NAVERA
operator watches (red SIMULATION banner).

## Step 5 — Jam the GPS, then spoof it

Only when the drone is **flying to the destination** (not before — the autopilot needs one real GPS fix
to start). In the flight monitor, tab **Faults** → GPS receiver:

1. **Jammed**. Watch NAVERA's card: within a second it switches from `FIX — GPS` to **DAY VISION**. The
   drone continues its mission. Keep it jammed **60 seconds**.
2. **OK**. GPS comes back… but not at once: count the seconds (lesson 25's hold-off).
3. Wait 30 s, then **Spoof jump** (the receiver suddenly reports a position 2 km away). Watch the reason
   on NAVERA's card and on the operator view. Keep it **30 seconds**.
4. **OK** again, and wait 30 s.

(From a terminal: `python3 sim_ctl.py fault gps jammed`, `… fault gps ok`, `… fault gps spoof_jump`.)

While it flies, in a third terminal you can listen to the arbiter directly — same ROS domain:

```bash
ros2 topic echo /navera/nav_status --field reason
```

(`Ctrl+C` to stop listening.)

> [!TASK]
> Fly the mission with a 60 s GPS jam and a 30 s spoof jump, recorded by `sim_ctl.py record`.
> "Done" means: `flight.csv` covers the flight (at least 60 s *en route*, with the jam), and
> `~/.navera_sim/estimator.log` shows the spoof refused (`implausible jump`).

## Step 6 — Stop the recording, the mission and the simulator

1. In the recording terminal: `Ctrl+C` (it saves and stops).
2. On the page: **Stop** (or `python3 sim_ctl.py stop`).
3. In the simulator's terminal: `Ctrl+C`. Wait until the prompt comes back (it stops NAVERA's nodes and
   ArduPilot, a few seconds).
4. Check that the ports are free again — this must print **nothing**:

```bash
ss -ltn | grep -E ':(8181|8190|8443|5760|5762) '
```

5. **Hardware** → Mission simulator → **Release** (it also closes the terminals that had access). Thank you!

## Step 7 — Read the logs

```bash
ls -la ~/.navera_sim/
```

The arbiter's own decisions — errors and warnings only:

```bash
grep -E "ERROR|WARN" ~/.navera_sim/estimator.log
```

How many times did the GPS driver report "no fix" while jammed (it writes at most one line every 10 s)?

```bash
grep -c "No fix" ~/.navera_sim/gps_node.log
```

And the simulator's own story:

```bash
grep -E "FAULT|NAVERA:" events.log
```

## Step 8 — Let Python read the flight (TODO 1–5)

`grep` is great for one question. For many questions, engineers write small functions. Open
[flight_log.py](file:./flight_log.py) and complete:

1. `load_flight(path)` — read the CSV with `csv.DictReader`; turn the columns of `NUMBERS` into `float`,
   an empty cell into `None`.
2. `first_time(rows, column, value, after=0.0)` — the time of the first matching row.
3. `switch_delay(rows)` — seconds from the jam to the first row where NAVERA's source is not `GPS`.
4. `median_error(rows, source)` — the median NAVERA error while a given source was used.
5. `log_lines(path, word)` — the lines of a log that contain a word.

Try them on the recorded **sample** flight first (it never changes, so you can compare with a friend):

```bash
python3 flight_log.py --sample
```

Then on **your** flight:

```bash
python3 flight_log.py
```

> [!QUESTION]
> In your flight, NAVERA's error with GPS and with day vision (target profile, 15 m): which one is
> bigger, and by how much? Is that a measurement of NAVERA's day vision? (Re-read the warning of the
> course, §1.)

> [!TASK]
> Complete TODO 1–5 so that `python3 flight_log.py --sample` prints the sample's story, then answer
> [answers.py](file:./answers.py). Press **✔ Check my work**.

## No simulator?

If the teacher says the simulator cannot be used today (busy, maintenance), you can still do the
lesson on a **recorded** flight, made exactly as described above (`/data/academy/28-simulator/`:
`sample_flight.csv`, `sample_events.log`, `sample_estimator.log`, and `record_sample.sh` — the script
that flew it).

1. In [answers.py](file:./answers.py), set `NO_SIMULATOR = True`.
2. Do Steps 7–8 on the sample: replace `~/.navera_sim/estimator.log` by
   `/data/academy/28-simulator/sample_estimator.log` and `events.log` by
   `/data/academy/28-simulator/sample_events.log`, and use `python3 flight_log.py --sample`.

The checks about *your own* flight are then skipped (➖), everything else is graded the same way. When
the simulator is free again, fly it: it is much more fun than reading about it.

## Going further (optional)

- **Spoof drift.** Fly again and choose **Spoof drift** (4 m/s) instead of the jump. With the *target*
  vision (stated σ 15 m), how far did the GPS drift before `GPS IN DOUBT`, then `drifting away`?
  Compare with lesson 27 and with VALIDATION_STATUS.md (refused at ~140–200 m in the simulator).
- **The other profile.** Fly with *Simulated — former day vision* (~440 m, uncertainty unknown) and
  jam the GPS. What does the operator view show? Does the autopilot keep flying? (Hint: NAVERA's
  default does not give DEGRADED positions to the autopilot.)
- **Camera failed + GPS jammed.** What does NAVERA say, and what does ArduPilot do by itself?
