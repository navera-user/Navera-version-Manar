# Lab 27 — Build a GPS guard, measure its ROC, attack the real arbiter

**Goal:** (A) implement the kinematic gate and the cross-check state machine (TRUSTED / IN_DOUBT /
REFUSED) and test them against seven attacks; (B) treat detection as a hypothesis test: compute
false-alarm probabilities, the patient-spoofer time, and run a Monte-Carlo **ROC experiment**;
(C) attack NAVERA's **real** arbiter with a scripted fake GPS; (D) write a short report.
**Time:** about 4 h.

Your files:

| File | What you do |
|---|---|
| [spoof.py](file:./spoof.py) | your guard — TODO 1–4 |
| [scenarios.py](file:./scenarios.py) | the seven attacks — read it, do not change it |
| [detection.py](file:./detection.py) | the statistics — TODO 5–11 |
| [spoof_real.py](file:./spoof_real.py) | the attack on the real `estimator_node` — do not change it |
| [report.md](file:./report.md) | your analysis — five sections |

Positions in `spoof.py` are **metres on a flat local map** (x east, y north), as in lessons 6 and 26.
The vehicle flies east at 15 m/s. GPS sends one fix per second. Vision sends one fix every 2 s at the
true position plus a little noise, and states σ = 15 m (the simulator's *target* accuracy, not a
measured one) or "unknown" (`None`).

# Part A — the guard

## Step 1 — Run the attacks on the empty guard

```bash
python3 spoof.py
```

For each attack it prints only the **changes** of state. With empty TODOs every attack is refused
at t = 1 s ("max ? m": the gate cannot compute yet), then stays on "TODO 4b".

## Step 2 — The kinematic gate (TODO 1–2)

- `reachable_m(dt_s, max_speed, margin)` returns `max_speed · dt + margin`, with a negative dt counted
  as 0 (a fix stamped before the trusted one).
- `kinematic_gate(trusted, fix, max_speed, margin)` takes two `(t, x, y)` tuples and returns `True` when
  the distance between them is **at most** `reachable_m(t1 − t0, …)`. Use `distance()` (already written).

```bash
python3 -c "import spoof; print(spoof.reachable_m(2.0), spoof.kinematic_gate((0, 0, 0), (1, 0, 2000)))"
```

Expected: `110.0 False` (2 s at 30 m/s + 50 m; a 2 km jump in 1 s is refused).

## Step 3 — Read the guard's flow

Open [spoof.py](file:./spoof.py) and read `on_gps()` (already written). For every GPS fix:

1. the very first fix is trusted;
2. if GPS is **REFUSED**, or it returns after an **outage** (more than `GPS_TIMEOUT_S` = 3 s since the
   last trusted fix), it must be **confirmed** → `_confirm()` (TODO 4);
3. otherwise the **kinematic gate**: a jump → REFUSED, "implausible jump";
4. otherwise the **cross-check** with vision → `_cross_check()` (TODO 3) sets TRUSTED, IN_DOUBT or REFUSED;
5. if not refused, this fix becomes the new trusted fix.

`vision_reference()` (below the line) returns `(d, sigma, vt)` — the GPS–vision distance, the vision σ
and the vision **stamp** — or `None` when there is no fresh vision fix with a **stated** σ. The guard
stores stamps in a `set()`: that is how it counts **distinct** vision fixes. One vision fix compared
with three GPS fixes counts once — otherwise a single wrong match would look like a streak.

## Step 4 — The cross-check (TODO 3)

Follow the four numbered comments in `_cross_check()`: the 3σ streak, the refusal at `STREAK_N`, the
"5σ + 50 m for 3 s" rule, then IN_DOUBT from `DOUBT_AFTER` fixes. Then:

```bash
python3 spoof.py
```

Look at the attack **drift**: GPS goes `IN_DOUBT` around 55–60 m off, then `REFUSED` ("drifting away")
a few seconds later. Compare with the worked example of the course (§4: ≈ 77 m expected for a refusal).
In **drift_novision** nothing happens during the drift: that is the documented limit, not a bug.

## Step 5 — Re-acceptance (TODO 4)

`_confirm()` has two halves. **4a**, with an independent source: two distinct agreeing vision fixes →
TRUSTED ("confirmed by vision"), a disagreeing one → REFUSED. **4b**, without one: the kinematic gate
decides — except after a cross-check refusal (`refused_by == "crosscheck"`), which only vision can clear.

```bash
python3 spoof.py
```

Two stories should make you uneasy:

- **patient** (no vision): the 2 km spoof is *accepted* at t = 94 s ("plausible again") and at 120 s the
  **true** GPS is refused as a jump — locked out.
- **jamspoof_novision**: after an 80 s outage the 2 km spoof is "reachable" and accepted at once.

With vision of stated accuracy (**patient_vision**, **jamspoof**) the spoof is never accepted, and the
true GPS is confirmed 2 s after it returns.

> [!TASK]
> Complete TODO 1–4 in `spoof.py`. "Done": the seven attacks behave as described above — jump refused
> and recovered; patient spoofer accepted only without vision; drift IN_DOUBT before REFUSED and refused
> below 150 m; jam-then-spoof refused when vision states σ. Press **✔ Check my work** (checks 1–8).

# Part B — detection as a hypothesis test

## Step 6 — False alarms and the patient spoofer (TODO 5–7)

In [detection.py](file:./detection.py):

- **TODO 5** `p_exceed(k, sigma_ref, sigma_g)`: P(z > k) for one fix under H0. The course §4 gives the
  Rayleigh tail: `exp(−ρ² / (2 s²))` with `ρ = k · sigma_ref` and `s² = sigma_ref² + sigma_g²`.
- **TODO 6** `p_streak(k, n, …)`: n independent fixes in a row.
- **TODO 7** `patient_accept_time(offset_m, speed_mps, max_speed_mps, margin_m)`: the smallest Δt with
  `v·Δt + m ≥ sqrt((s·Δt)² + D²)`. Square both sides (both are positive) to get
  `a·Δt² + b·Δt + c ≥ 0` with `a = v² − s²`, `b = 2·v·m`, `c = m² − D²`, and take the positive root.
  Handle the edge cases: `m ≥ D` → 0; `a < 0` (the vehicle flies faster than the gate's
  `max_speed`) → never reachable → `math.inf`; `a = 0` → the inequality is linear,
  `b·Δt + c ≥ 0`, so Δt = −c / b.

```bash
python3 -c "import detection as d; print(d.p_exceed(3.0), d.p_streak(3.0, 5), d.patient_accept_time(2000, 15, 30, 50))"
```

Expected: `0.0111…`, `1.69…e-10`, `74.77…`. The last trusted fix of the attack *patient* is at
t = 19 s, so the theory predicts acceptance at t ≈ 93.8 s. Your guard (Step 5) accepted at 94 s: it
checks once per second.

> [!WARNING]
> `math.exp(-k**2 / 2)` works; `math.exp(-k^2 / 2)` does not: in Python `^` is the bitwise XOR, and
> with a float it raises `TypeError: unsupported operand type(s) for ^`.

## Step 7 — The ROC experiment (TODO 8–9)

The rule we test is NAVERA's persistence rule: **alarm when n vision fixes in a row have z > k**, with
z = |GPS − vision| / σ_v.

- **TODO 8** `alarm_index(z, k, n)`: the index of the first fix where the last n values are all `> k`,
  or −1. One pass, one counter.
- **TODO 9** `roc_point(z_h0, z_h1, k, n, period_s)`: P_FA = fraction of H0 flights with an alarm, P_D =
  fraction of H1 flights with an alarm, `delay_s` = mean alarm time over the **detected** H1 flights.

Below the line, `simulate_z()` generates Monte-Carlo flights with a fixed seed (every run gives the
same numbers): 2 000 honest flights of 2 min (60 vision checks) and 2 000 spoofed flights where the GPS
is pulled north at 1.5 m/s and we want an alarm within 40 s. GPS noise σ_g = 3 m, vision σ_v = 15 m.
It also generates 2 000 honest flights whose vision error is **correlated** from one fix to the next
(an **AR(1)** series, "auto-regressive of order 1": each error = ρ × the previous error + fresh
noise, here with ρ = 0.9, so the same map error lasts several frames).

```bash
python3 detection.py
```

It takes a few seconds, prints the table (k, n, P_FA, P_D, delay), and writes `results.json` and
`roc.png`. Open [roc.png](file:./roc.png) and [results.json](file:./results.json).

Read `results.json` → `"single_fix"`: the measured fraction of fixes beyond k against the two theories.
Which one matches — with or without σ_g? Why?

> [!TASK]
> Complete TODO 5–9. "Done": the functions return the values above and pass the edge cases of the check;
> `results.json` contains the 24 ROC points of the grid (the check recomputes them with its own
> reference). Press **✔ Check my work** (checks 9–13).

## Step 8 — Choose an operating point (TODO 10)

The requirement: **at most 1 % of honest 2-minute flights may raise a false alarm** (`MAX_PFA`). Among
the 24 rules, choose the one with the highest P_D that meets it. Set `CHOSEN_K` and `CHOSEN_N` at the
top of `detection.py` and run it again:

```bash
python3 detection.py
```

> [!QUESTION]
> Your rule is probably not NAVERA's (k = 3, n = 5), which has a much lower P_D here. A real flight
> lasts an hour: 1 800 vision checks, not 60. Roughly, how does the false-alarm rate per flight scale with
> the number of checks? Which choice would you defend for a product? Put this in report §2.

Also look at `"correlated"`: for the same rule, how much larger is P_FA when ρ = 0.9? (report §3)

> [!TASK]
> Set `CHOSEN_K`, `CHOSEN_N`, rerun `python3 detection.py`. "Done": `results.json` → `"chosen"` is the
> grid rule with P_FA ≤ 0.01 and the highest P_D (check 13).

# Part C — attack the real arbiter

## Step 9 — Three attacks on `estimator_node` (TODO 11)

`spoof_real.py` starts NAVERA's real `estimator_node` from your copy (`~/navera`), publishes a GPS
(2 fixes/s) and a day-vision estimate (1 fix/s) as `PositionEstimate` messages on your private ROS
domain, and prints every change of `/navera/nav_status`. Run the three attacks one after the other
(30–50 s each; wait for `saved real_….txt`):

```bash
python3 spoof_real.py jump
```

```bash
python3 spoof_real.py drift
```

```bash
python3 spoof_real.py jamspoof
```

Each run saves `real_<attack>.txt` (the status changes; the check reads it) and
`real_<attack>_estimator.log` (what the estimator logged). Open them:
[real_jump.txt](file:./real_jump.txt), [real_drift.txt](file:./real_drift.txt),
[real_jamspoof.txt](file:./real_jamspoof.txt).

What to look for:

- **jump** — vision states *no* accuracy, so only the gate can act: `GPS refused: implausible jump
  2000 m in 0.5 s (max 65 m at 30 m/s)` — the exact numbers depend on timing (for example
  `0.5 s` or `0.6 s`, `max 65 m` or `66 m`). When the true GPS returns, the log says
  `GPS plausible again — re-accepted`, and FIX GPS comes **2 s later** — the hold-off of lesson 25.
- **drift** (6 m/s) — first `DEGRADED GPS … — GPS IN DOUBT: day vision disagrees by N m`: *in doubt*
  raised the GPS's stated uncertainty to the gap (lesson 26). Then `GPS drifting away from day vision: 5
  independent fixes in a row beyond 3 sigma`. Day vision (σ 15 m) becomes the FIX source.
- **jamspoof** — while jammed, day vision takes over. The spoofed GPS returns 2 km away and is refused
  (`GPS 1998 m from day vision (3 sigma 46 m)`) although, at 100 m/s, 2 km was reachable after 20 s.
  The log shows `GPS confirmed by day vision (… 2 fixes) — re-accepted` when the true GPS returns.

Every line carries the GPS offset at that moment (`GPS   54 m off`). In `real_drift.txt`, find the
**first** line with `IN DOUBT` and the **first** line with `drifting away`, and copy their offsets
into `REAL_DRIFT_OFFSET_AT_DOUBT_M` and `REAL_DRIFT_OFFSET_AT_REFUSAL_M` in `detection.py` (TODO 11).
Check them with the course: σ 15 m → 3σ = 45 m; at 6 m/s and one vision fix per second, five fixes in a
row take 4 s ≈ 24 m more.

You can list the estimator's own error lines:

```bash
grep -h "GPS refused\|re-accepted" real_jump_estimator.log real_drift_estimator.log real_jamspoof_estimator.log
```

> [!TASK]
> Run the three attacks so that the three `real_*.txt` files are complete (each ends with `FIX GPS`, the
> true GPS back), and fill TODO 11. Press **✔ Check my work** (checks 14–15). A run can differ by a few
> metres from your neighbour's: ROS timing is real time.

# Part D — the report

## Step 10 — Write report.md

Open [report.md](file:./report.md). Keep its five `##` headings; replace each TODO with your analysis
(the comments say what to answer). At least 40 words per section, 60 for §5. The check looks for:
§1 the patient-spoofer time from `patient_accept_time` (Δt ≈ 75 s or t ≈ 94 s), §2 your chosen k and n,
§4 the two real offsets you copied in TODO 11. Write short sentences and give units.

> [!TASK]
> Complete `report.md` and press **✔ Check my work** — all 16 checks should be green.

## Going further (optional)

- **One wrong vision fix.** In a copy of `scenarios.py`, add one vision fix 2 km away in the middle of an
  honest flight. Your guard must not refuse the good GPS. Which line of `_cross_check()` protects it?
- **A smarter spoofer.** Write an attack that keeps the offset at 2.5σ for ever (`offset = 37.5 m`).
  Show that neither your guard nor the real rule detects it, and compute the largest undetected offset
  of the real rule (`3σ + v_max · gap`). This is the **bound** of §6.
- **Delay vs drift speed.** Change `DRIFT_MPS` to 0.5, 1, 3 and 6 m/s (copy the file first) and plot the
  offset at detection (`delay_s · DRIFT_MPS`) for k = 3, n = 5. Is it roughly constant? Why?
- **The product's own test.** `python3 ~/navera/navera_tools/tests/test_estimator.py` (about 2 min)
  plays these attacks and more against the real node and prints `estimator: PASS`. Find its "gradual
  spoof" scenario and compare with yours.
