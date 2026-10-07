# Lab 27 — Build a GPS guard, then attack the real arbiter

**Goal:** implement the kinematic gate and a simplified cross-check state machine (TRUSTED /
IN_DOUBT / REFUSED), test it against seven attacks, then attack NAVERA's **real** arbiter with a
scripted fake GPS and read its reasons.
**Time:** about 1 h 30.

Your files: [spoof.py](file:./spoof.py) (your guard, TODO 1–4), [scenarios.py](file:./scenarios.py)
(the seven attacks — read it, don't change it), [spoof_real.py](file:./spoof_real.py) (the attack on the
real arbiter), [answers.py](file:./answers.py) (quiz).

To keep the maths simple, positions in `spoof.py` are **metres on a flat local map** (x east, y north),
like the "to_local_m" of lessons 6 and 26. The vehicle flies east at 15 m/s; GPS sends one fix per
second, vision one every 2 s at the true position (+ a little noise), stating σ = 15 m (the
simulator's *target* accuracy — not a measured one) or "unknown".

## Step 1 — Run the attacks on the empty guard

```bash
python3 spoof.py
```

For each attack it prints only the **changes** of state. With empty TODOs, everything is refused at
t = 1 s ("max ? m"): the gate cannot compute yet.

## Step 2 — The kinematic gate (TODO 1–2)

- `reachable_m(dt_s, max_speed, margin)`: `max_speed × dt + margin`, with a negative `dt` counted as 0
  (`max(0.0, dt_s)`).
- `kinematic_gate(trusted, fix, …)`: unpack `t0, x0, y0 = trusted` and `t1, x1, y1 = fix`, then
  `return distance(x0, y0, x1, y1) <= reachable_m(t1 - t0, max_speed, margin)`.

```bash
python3 -c "import spoof; print(spoof.reachable_m(2.0), spoof.kinematic_gate((0, 0, 0), (1, 0, 2000)))"
```

You should see `110.0 False`: 2 s at 30 m/s + 50 m, and a 2 km jump in 1 s refused.

## Step 3 — Read the guard's flow

Open [spoof.py](file:./spoof.py) and read `on_gps()` slowly — it is already written:

1. the very first fix is trusted;
2. if GPS is **REFUSED**, or it comes back after an **outage** (more than 3 s since the last trusted
   fix), it must be **confirmed** → `_confirm()` (TODO 4);
3. otherwise the **kinematic gate**: a jump → REFUSED, "implausible jump";
4. otherwise the **cross-check** with vision → `_cross_check()` (TODO 3) sets TRUSTED, IN_DOUBT or
   REFUSED;
5. if not refused, this fix becomes the new trusted one.

`vision_reference()` (below the line) gives `(d, sigma, vt)`: the distance GPS–vision, the vision σ and
the vision **stamp** — or `None` when there is no fresh vision fix **with a stated σ**. Using the
stamp in a `set()` is how we count **distinct** vision fixes: the same vision fix compared with three
GPS fixes counts once.

## Step 4 — The cross-check (TODO 3)

Follow the four numbered steps in the comments of `_cross_check()`. Then:

```bash
python3 spoof.py
```

Look at the attack **drift**: GPS should go `IN_DOUBT` around 50–60 m off, then `REFUSED` ("drifting
away") a few seconds later. And **drift_novision**: nothing happens during the whole drift — it is not
a bug, it is the limit of the course, §4.

## Step 5 — Re-acceptance (TODO 4)

`_confirm()` has two halves. **4a**, with an independent source: two distinct agreeing vision fixes
→ TRUSTED ("confirmed by vision"), a disagreeing one → REFUSED. **4b**, without one: the kinematic gate
decides — except after a cross-check refusal (`refused_by == "crosscheck"`), which only vision can
clear.

```bash
python3 spoof.py
```

Read the seven stories. Two of them should make you uneasy:

- **patient** (no vision): the 2 km spoof is *accepted* at t = 94 s ("plausible again") and, at 120 s,
  the **true** GPS is refused as a jump. Locked out — exactly what the mission simulator once showed
  in the real product.
- **jamspoof_novision**: after an 80 s outage, the 2 km spoof is "reachable" and accepted at once.

With vision of stated accuracy (**patient_vision**, **jamspoof**) the spoof is never accepted, and the
true GPS is confirmed 2 s after it returns.

> [!TASK]
> Complete TODO 1–4 in `spoof.py`. "Done" means: the seven attacks behave as described above —
> jump refused and recovered, patient spoofer accepted only without vision, drift IN_DOUBT before
> REFUSED (well before 150 m), jam-then-spoof refused with vision. Press **✔ Check my work**
> (checks 1–8).

## Step 6 — Attack the real arbiter

`spoof_real.py` starts NAVERA's real `estimator_node` from your copy, publishes a GPS (2 fixes/s) and a
day-vision estimate (1 fix/s) as `PositionEstimate` messages, and prints every change of
`/navera/nav_status`. Run the three attacks one after the other (30–50 s each):

```bash
python3 spoof_real.py jump
```

```bash
python3 spoof_real.py drift
```

```bash
python3 spoof_real.py jamspoof
```

Each run saves `real_<attack>.txt` (the status changes) and `real_<attack>_estimator.log` (what the
estimator itself logged). Read them in the editor: [real_jump.txt](file:./real_jump.txt),
[real_drift.txt](file:./real_drift.txt), [real_jamspoof.txt](file:./real_jamspoof.txt).

What to look for:

- **jump** — vision states *no* accuracy here, so only the gate can act: `DEGRADED day … — GPS refused:
  implausible jump 2000 m in 0.5 s (max 66 m at 30 m/s)`. When the true GPS returns: `GPS plausible
  again — re-accepted` in the log, and FIX GPS **2 s later** (the hold-off of lesson 25!).
- **drift** — first `DEGRADED GPS … uncertainty 51 m > 25 m — GPS IN DOUBT: day vision disagrees by
  51 m`: notice how *in doubt* raised the GPS's stated uncertainty to the gap (lesson 26). Then
  `GPS drifting away from day vision: 5 independent fixes in a row beyond 3 sigma`. Day vision (σ 15 m)
  is now **FIX**.
- **jamspoof** — while jammed, day vision takes over. When the spoofed GPS returns 2 km away, it is
  refused (`GPS 1998 m from day vision (3 sigma 46 m)`) although, at 100 m/s, 2 km was reachable after
  20 s. In the log: `GPS confirmed by day vision (… 2 fixes) — re-accepted` when the true GPS returns.

> [!QUESTION]
> In `real_drift.txt`, compare the GPS offset when the real arbiter refused it with the moment your
> guard refused the drift in Step 4. Why can't the two be identical? (Think: drift speed, vision rate,
> and the `max_speed × time gap` term your guard leaves out.)

> [!TASK]
> Run the three attacks so that `real_jump.txt`, `real_drift.txt` and `real_jamspoof.txt` exist and are
> complete (each ends with GPS back, `FIX GPS`). Then answer [answers.py](file:./answers.py) and press
> **✔ Check my work**.

## Going further (optional)

- **One wrong vision fix.** In `scenarios.py` (make a copy first), add one vision fix 2 km away in the
  middle of a normal flight. Does your guard refuse the good GPS? It must not: the real rule needs
  several **distinct** disagreeing fixes.
- **A faster spoofer.** In your copy of `spoof_real.py`, change the drift from `6.0 *` to `20.0 *` (m/s).
  Is it still refused by the streak of 5, or by the "5σ + 50 m for 3 s" rule? Read the log.
- **The product's own test.** `python3 ~/navera/navera_tools/tests/test_estimator.py` (about 2 min)
  plays the same attacks — and a few more — and prints `estimator: PASS`. Find in it the scenario
  "Gradual spoof" and compare with yours.
