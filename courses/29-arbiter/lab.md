# Lab 29 — Write the judge, close the revival, measure what it costs

**Goal:** write NAVERA Lite's real judge (`navera_lite/arbiter.py`, five TODOs) as a state machine, make
sure a fix refused at the door can never come back, run it live on ROS against the course's reference,
then measure the price of the hold-off, of the freshness window and of fusion.
**Time:** 4 h 30 to 6 h in two sessions (a strong programmer: about 3 h).
**Fast track:** if you know Python, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further".

Your files (📝 Code tab): [navera_lite/arbiter.py](file:./navera_lite/arbiter.py) (**your code**:
`TODO 1–5`), [experiment.py](file:./experiment.py) (`TODO A`, `TODO B`), [answers.py](file:./answers.py),
[report.md](file:./report.md). Given, you only run them: [judge_lab.py](file:./judge_lab.py) (your
judge on a scenario, without ROS) and [play_scenario.py](file:./play_scenario.py) (a scenario played
live into your running judge). Everything else in `navera_lite/` is finished: `estimate.py` (your
mission-12 checklist, the course's version), `guard.py` (the jump gate), arbiter v0, the replay node,
and `ros/arbiter_node.py`, which runs YOUR `Arbiter` as a ROS node. The scenarios are in
`/data/academy/29-arbiter/` (mission 12's CSV format, synthetic, read only).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | nothing: arbiter v0 on a GPS that comes and goes |
| §2 candidates | Step 1 | `candidates` (TODO 1) |
| §4 hold-off | Step 2 | `track_since` (TODO 2), `pick` (TODO 3) |
| §3 the door | Step 3 | `Arbiter.receive` (TODO 4) |
| §1, §5 state machine, states | Step 4 | `Arbiter.step` (TODO 5), offline plays |
| §3 the door | Step 5 | the door left open: predict, run, explain |
| all | Step 6 | your judge live; the race |
| §4 | Step 7 | `holdoff_metrics` (TODO A), the hold-off experiment |
| §6, §7 | Step 8 | `true_sigma` (TODO B), freshness and fusion |
| all | Step 9 | `report.md` |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each TODO's docstring says its goal and gives one example with its result;
> `python3 judge_lab.py test` tries every example of `arbiter.py`. The lesson shows how; the code is yours.

> [!WARNING] One terminal tab for the ROS steps
> As in missions 09–14, a node started in one tab cannot be seen from another tab. In Session 2, run
> everything in **one** tab and start your judge in the background with `&`, its output in a log file.
> `jobs` lists the background jobs, `kill -INT %1` stops job 1, `kill -INT $(jobs -p)` stops all.

## Session 1 — The judge (2 h to 3 h, no ROS)

## Step 0 — Arbiter v0 and a GPS that comes and goes

No code. The scenario `flapping.csv` lasts 30 s: a GPS that sends a fix every 0.5 s but is usable for
0.5 to 2.5 s at a time (in between it says "no fix"), and a day vision that states σ 30 m every second.

> [!TASK]
> **Predict** (`PREDICT_FLAP` in `answers.py`): in these 30 s, how many times will arbiter v0 change its
> winner? Then run it:

```bash
python3 judge_lab.py play /data/academy/29-arbiter/flapping.csv --v0
```

`judge_lab.py play` feeds a scenario to a judge on a **simulated clock** (no ROS, the same rules as the
node: a decision at every arrival and every 0.2 s) and prints only the changes. Open the picture it
saved (`out/flapping_v0.png`, in the file list of the 📝 Code tab): one colour per state, one row per
source.

> [!TASK]
> Write `V0_FLAP_SWITCHES`: the number after "changes of winner:". Then read the lesson, §1 to §3.

## Step 1 — Who may compete (TODO 1)

Open [navera_lite/arbiter.py](file:./navera_lite/arbiter.py). Read the top of the file (the memory of
the judge), then the given `Decision`, `source_report()` and `no_fix_reason()`: you will use them in
TODO 5. Write **TODO 1**, `candidates(latest, now_s, cfg)`, as lesson §2's worked example does it by
hand. `eligible()` and `SOURCES` are already imported at the top of the file.

```bash
python3 judge_lab.py test
```

The TODO 1 lines must be ✔ (the other TODOs are still ✘: normal).

<details><summary>Stuck? Hints, one at a time</summary>

1. Which sources can compete at all? Those that have a stored fix: `name in latest`.
2. `eligible(est, now_s, cfg)` returns a pair `(ok, reason)`; you need only `ok`, so `[0]`.
3. The order of the result is the order of `SOURCES`, not the order of the dict: loop over `SOURCES`
   (lesson §2 🧰).
4. You get `['celestial', 'day', 'gps']` instead of `['gps', 'day', 'celestial']`? You walked the dict
   `latest` (its keys come in the order they were added), not `SOURCES`.
</details>

## Step 2 — The hold-off (TODO 2, TODO 3)

**TODO 2 — `track_since(since, cands, now_s)`** keeps the hold-off's memory: for each candidate, the
instant it became eligible **without a break**. Lesson §4 says the three rules; its 🧰 shows the two
Python tools (`dict.get` with a default, a dict built in one line).

<details><summary>Stuck? Hints, one at a time</summary>

1. The result has exactly one key per candidate, and no other key.
2. For a candidate, the value is its old instant if it had one, else `now_s`: that is `since.get(…, …)`.
3. You get `{'gps': 100.0, 'day': 100.0}` for the docstring example? You wrote `now_s` for every
   candidate: day vision lost its old instant (90.0), so it would wait the hold-off again and again.
4. You get `{'day': 90.0, 'night': 95.0, 'gps': 100.0}`? You kept a source that is no longer a
   candidate: night's next eligibility must start again from zero.
</details>

**TODO 3 — `pick(cands, current, since, now_s, cfg)`.** (Fast track: write it from lesson §4 only,
without reading the docstring's second paragraph, then run the test.) First a hand trace (on paper, 3 minutes):
hold-off 2 s, current winner `"night"`, `since = {"gps": 99.5, "day": 90.0, "night": 80.0}`, now
100.0 s, candidates `["gps", "day", "night"]`. Who wins? And with candidates `["gps", "day"]` only
(night has just gone stale)? Check your answers in the box, then write TODO 3.

<details><summary>The hand trace</summary>

GPS has waited 0.5 s only (< 2 s); day has waited 10 s: day replaces night. Without night, the winner
is lost: the first candidate wins at once, GPS.
</details>

```bash
python3 judge_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Two cases. Is `current` still a candidate (`current in cands`)? If not, there is no hold-off.
2. If it is: walk the candidates in order; the first one that is `current`, or has waited
   `now_s - since[name] >= cfg["switch_holdoff_s"]`, wins.
3. `pick([], …)` must return `None`: `cands[0]` of an empty list is an `IndexError`.
4. "exactly 2.0 s of eligibility" ✘ and you return `"day"`? You wrote `>` instead of `>=`.
5. The hand trace (and the test line "night wins; day has waited…") gives `"night"`? You looked only at
   the first candidate (GPS) and kept the current winner when GPS had not waited: day, which had
   waited, was skipped.
</details>

## Step 3 — The door (TODO 4)

**TODO 4 — `Arbiter.receive(est, now_s)`.** The docstring lists the five refusals **in their order**,
with their words. Lesson §3 explains why a fix refused at the door must never be stored, and why the
future test comes before the jump gate. The jump gate is ready: `self.gate.check(est)` returns
`(ok, reason)`, like in mission 01 (and it remembers the trusted fix itself).

> [!TIP] 🧰 One function, several exits
> ```python
> def ticket(age):
>     if age < 0:
>         return False, "impossible age"      # each refusal returns at once…
>     if age < 4:
>         return False, "too young"
>     return True, "ok"                       # …and only what passed every test arrives here
> ```

```bash
python3 judge_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. The "ahead" of a fix is `est.stamp_s - now_s` (positive = in the future); compare it with
   `self.cfg["future_tolerance_s"]`. The reason has one decimal: `f"from the future ({ahead:.1f} s ahead)"`.
2. Old news: `self.latest.get(est.source)` is the stored fix of that source, or `None`. Not newer means
   `est.stamp_s <= old.stamp_s`.
3. The gate only judges a GPS fix that has a position: `est.valid` and `is_finite_latlon(est.lat, est.lon)`
   (imported). A "no fix" GPS message is stored without the gate.
4. Remember a future or jump refusal in `self.refused[est.source]`; when you store a fix, remove its
   source from `self.refused` (`self.refused.pop(name, None)` does not fail when the key is missing).
5. "a fix older than the stored one" ✘ and the stored stamp became 99.1? You stored before you tested
   the order: every test comes BEFORE `self.latest[...] = est`.
6. Bad stamp: `math.isfinite(est.stamp_s)` (math is imported) is False for nan and inf.
   `est.stamp_s == float("nan")` never works: a NaN is equal to nothing, not even to itself.
</details>

## Step 4 — The decision (TODO 5)

**TODO 5 — `Arbiter.step(now_s)`** puts everything together. This one has the least help. First a
hand trace (5 minutes): a new `Arbiter`; `receive` a GPS fix stamped 99.5 at 100.0, `step(100.0)`;
`receive` a day fix (σ 30 m) stamped 102.0 at 102.4; then `step(104.0)` and `step(108.0)`. For each
step, write the state, the source, and what `self.switches` holds. `python3 judge_lab.py test` runs this
exact case (its last three lines), so you can compare.

```bash
python3 judge_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Follow the docstring's table from the top: the first situation that applies decides.
2. "Nothing received yet" means nothing stored **and** nothing refused: `not self.latest and not self.refused`.
3. The order matters: candidates (TODO 1), then `self.since = track_since(...)` (TODO 2), THEN
   `pick(...)` (TODO 3) — pick reads `since`, so it must be up to date first.
4. The winner's σ: `stated_sigma(self.latest[winner], self.cfg)`; then `state, words = classify(sigma, self.cfg)`.
5. Compare the winner with `self.current` before you overwrite it: a change goes to `self.switches` as
   `(now_s, self.current, winner)`.
</details>

When every line of `python3 judge_lab.py test` is ✔, play the lab's scenarios through **your** judge:

```bash
python3 judge_lab.py play /data/academy/29-arbiter/flapping.csv
```

Compare with Step 0 (and `out/flapping_mine.png` with `out/flapping_v0.png`): how many changes now?

> [!TASK]
> Write `MINE_FLAP_SWITCHES` (your judge's "changes of winner" on `flapping.csv`) and `EXPLAIN_FLAP`:
> between 2.5 s and 24.5 s the GPS was usable several times, yet your judge stayed on day vision. Why?
> Which run of GPS fixes finally took over, and why that one?

Then the revival of mission 12 — first mission 12's judge (v0 with your old `eligible()`), then yours:

```bash
python3 judge_lab.py play /data/academy/29-arbiter/revival.csv --v0 --eligible
```

```bash
python3 judge_lab.py play /data/academy/29-arbiter/revival.csv
```

Your judge never says GPS again after the last honest fix goes stale: the line "⤫ refused at the door"
shows where the fix from the future stopped. Last, the 31 s race scenario of Session 2, offline (it
compares your judge with the reference run, decision by decision):

```bash
python3 play_scenario.py --offline
```

11 of 11 and every switch ✔? Your state machine decides like the reference. A ✘: read its line (what
happens at that moment, the reference's decision, yours) and find the rule your judge applies differently.

## Step 5 — The door left open

`lockout.csv`: an honest GPS sends a fix every second for 40 s (vehicle at 20 m/s), plus day vision.
At t = 10.5 s **one** extra GPS fix arrives, stamped 20 s ahead (stamp 30.5 s). `--open-door` runs
**your** judge with only one change: during `receive()`, the future tolerance is infinite, so the door
lets that fix in. Everything else (old news, the jump gate, `eligible()`, the hold-off) is your code.

> [!TASK]
> **Predict** (`PREDICT_LOCKOUT`): with the door open, what happens to the honest GPS fixes that arrive
> after 10.5 s, and what does the judge say between 10 s and 40 s? Write it, then run both:

```bash
python3 judge_lab.py play /data/academy/29-arbiter/lockout.csv --open-door
```

```bash
python3 judge_lab.py play /data/academy/29-arbiter/lockout.csv
```

> [!TASK]
> `EXPLAIN_LOCKOUT`: what happened to the honest fixes, and why? Why did an old position win as FIX
> around t = 32 s, and why were honest fixes then refused as jumps? (Read the lines 31.0–37.0 s of the
> run: "in 0.5 s" measures the time from which fix?) (Then read the box of lesson §3
> "Read this after lab Step 5".)

Press **✔ Check my work**: checks 1–9 are Session 1 (badge **Fair judge**). The check tries your judge
on situations and scenarios it has never seen (other settings too: a hold-off of 3 s, a slower vehicle).

## Session 2 — Live, and what it costs (2 h to 2 h 30)

## Step 6 — Your judge on ROS, and the race

Check that nothing runs (`jobs` prints nothing), then start **your** judge in the background:

```bash
jobs
```

```bash
python3 -m navera_lite.ros.arbiter_node --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

Wait 2 s, then ask it (`status` listens 6 s and prints the state, the reason and each source's line):

```bash
python3 judge_lab.py status
```

STARTING: nothing has arrived. Now the race: `play_scenario.py` publishes `race.csv` (31 s: GPS good,
day vision, GPS lost, GPS back at σ 40 m, GPS "no fix", a 5 km jump, night vision with no σ, a
celestial fix stamped 60 s ahead) into your running judge, records every status, and compares 11
moments and every change of winner with the reference run (±0.35 s: your node ticks at 5 Hz with its
own phase). About 40 s:

```bash
python3 play_scenario.py
```

A judge remembers. **Before each new race, restart it** (the player refuses a judge that is not
STARTING). `wait` returns when the old judge has really stopped, so the new one is job 1 again:

```bash
kill -INT %1; wait
```

```bash
python3 -m navera_lite.ros.arbiter_node --ros-args --params-file navera_lite.yaml > arbiter.log 2>&1 &
```

> [!TASK]
> Race until **11 of 11** decisions and all switches match (`my_run.json` is saved after each race).
> Then `EXPLAIN_WAIT`: at t = 15.0 s the GPS is back, eligible and first in priority, yet your judge
> uses day vision. Why, and when does GPS take over?

`tail arbiter.log` shows what your node logged: the refusals at the door ("gps fix refused: jump …",
"celestial fix refused: from the future …") and each change of state. **Stop your judge** before the
check (the check starts its own, with your code, on a hidden scenario):

```bash
kill -INT $(jobs -p); wait
```

## Step 7 — The price of the hold-off (TODO A)

[experiment.py](file:./experiment.py), part A: a GPS at the edge of a jammer's range (usable for about
2 s, then "no fix" for about 1 s, again and again, 2 messages a second) and a day vision that always
works, for 10 minutes, seeded (the same for everybody). `fly()` (given) runs YOUR judge with a hold-off
of 0, 0.5, 1, 2, 4 and 8 s and records every 0.2 s tick: `(t, winner, gps_eligible)`. **TODO A,
`holdoff_metrics(ticks, duration_s)`**, turns the ticks into three numbers. Count by hand on the
docstring's 4-tick example first.

```bash
python3 experiment.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. A change of winner compares each tick with the one before: `zip(ticks, ticks[1:])` gives the pairs.
2. A tick is `(t, winner, gps_eligible)`; `None` is a winner value like the others ("no winner").
3. Per minute: divide by `duration_s / 60`. "Unused": GPS eligible AND winner not `"gps"`, 0.2 s each.
4. The None example gives 0.0 changes per minute instead of 20.0? You skipped the changes to or from None.
</details>

> [!TASK]
> **Predict** (`PREDICT_HOLDOFF`): changes of winner per minute with no hold-off, and with 2 s? Then run
> the experiment (a few seconds):

```bash
python3 experiment.py
```

> [!TASK]
> `EXPLAIN_HOLDOFF`: what does a longer hold-off buy, and what does it cost? Quote your numbers (table A,
> and `out/tradeoffs.png`).

## Step 8 — Freshness and fusion (TODO B)

Table B is given: day-vision photos under load (85 % of the gaps 1–4 s, 15 % stalls of 4–10 s), and a
window of 2 to 8 s. Read it with lesson §6: how much availability does each extra second buy, and what
does it cost at 40 m/s?

Part C fuses a GPS (σ 2.5 m) with a vision fix (σ 20 m). `fuse()` is given (mission 27's `uncertainty.fuse()`,
written with σ). **TODO B, `true_sigma(s1, s2, rho)`**: the real σ of that fused value when the two
errors are correlated (lesson §7, the formula of problem 1).

```bash
python3 experiment.py test
```

```bash
python3 experiment.py
```

<details><summary>Stuck? Hints</summary>

1. `fuse(0.0, s1, 0.0, s2)` returns `(x, s, w1, w2)`: take the weights from it, do not rewrite them.
2. The formula gives a **variance**; return its square root.
3. `true_sigma(3.0, 30.0, 0.8)` gives 3.10 instead of 3.21? You forgot the 2 in front of the last term.
</details>

## Step 9 — Write the analysis

Fill in [report.md](file:./report.md): four sections (keep the `## ` headings), at least 40 words each
and 250 in all, in full sentences. In sections 1–3, quote at least two of **your** numbers (as
`experiment.py` printed them). Section 4 is the **designer's** role: choose a hold-off and a day-vision
window for a fixed-wing plane at 40 m/s and for a harbour boat at 5 m/s, with one reason each — and say
what these synthetic experiments cannot tell you.

> [!TASK]
> Press **✔ Check my work**: all 15 checks ✔ (badge **Steady hand**). About 60 s: one check starts your
> judge on ROS. The check only verifies that your written answers are real answers on the topic; your
> teacher reads them.

## Look back (not graded)

- Which part of the memory (latest, refused, since, current, switches) would you print first if your
  judge made a strange decision in flight? Why?
- The door refuses a fix stamped in the future. What should an operator do when the status says
  "celestial: refused: from the future (60.0 s ahead)" for several minutes?
- Write `LOOK_BACK` in `answers.py`: one rule of your judge you would defend in front of a pilot.

## Going further (optional)

- **Model or simulation?** Lesson §4 predicts that a hold-off h keeps a share e^(−h/μ) of the GPS returns
  (here μ = 2 s). Compare e^(−1) with your switch rates at h = 2 s and h = 0. Why do they differ? (The
  GPS sends 2 messages a second: what happens to on- and off-periods shorter than 0.5 s?)
- **Your own scenario.** Write `my_scenario.csv` (mission 12's format) where the "first candidate that
  has waited" rule of `pick()` matters: night vision wins, day vision comes back, then GPS. Play it with
  `judge_lab.py play`, then live with `python3 play_scenario.py my_scenario.csv`.
- **Can a lost winner still chatter?** A lost winner is replaced at once by the first candidate, even a
  GPS that came back 0.1 s ago. When the fallback source is itself intermittent, can the output still
  chatter? Build a CSV that shows it, and propose a rule.
- **A hold-off per source?** Would you make the celestial source (fixes every 15–45 s) wait 2 s like GPS?
  Edit `switch_holdoff_s` in your `navera_lite.yaml`, replay `race.csv` offline, and argue.
- **Fly your own contract.** Mission 12's checklist is the course's version here. Try yours:
  `cp ../12-position-message/navera_lite/estimate.py navera_lite/estimate.py`, then
  `python3 judge_lab.py test` and `python3 play_scenario.py --offline` (keep a copy of the original first).
