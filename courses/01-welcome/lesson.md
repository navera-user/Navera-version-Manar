# Ghost position: navigation without GNSS

![Cold open: a survey drone flies along the coast; over the sea its GPS position is slowly dragged away with no alarm; when the camera sees land again, NAVERA catches the lie 391 m off](assets/cold_open.svg)

> [!NOTE] Mission brief
> **22 June 2017, Black Sea, near Novorossiysk.** A ship's master reports that his GPS puts him at
> Gelendzhik airport, on land, tens of kilometres from where he really is. The AIS of about twenty
> nearby ships shows the same spot. The receivers appear to work normally. (Reported to the US
> Maritime Administration.)
>
> Today you find out how that is possible by doing it yourself. **Session 1 — build & spoof:** you
> launch an attack in Step 0, then build a satellite-style receiver, break it and fool
> it. **Session 2 — detect & defend:** you play detective on a spoofed flight, then fight NAVERA's jump
> gate as attacker and defender. Each session ends with a badge: **Ghost hunter**, then **Gatekeeper**.
>
> **Start now:** open the 🛠️ **Lab** tab, do **Step 0** (two minutes, no code), then come back here for §1.

**Objectives.** After this mission you can:

1. explain trilateration, and why one cheap clock makes it a **4-unknown** problem;
2. solve a position as a **least-squares** problem, by brute force and by **Gauss–Newton**;
3. explain, from the residuals, which attacks a receiver can notice by itself (jamming, a full spoof, a
   partial spoof), and name what better receivers add;
4. reason like NAVERA's arbiter: source priority, the FIX / DEGRADED / NO_FIX states, the jump gate
   and the cross-check, including **where each one fails**.

**You need:** Pythagoras, vectors, a derivative, a matrix × vector product, and one short Python course.
🧰 boxes refresh the rest. ⏱ Reading: about 75 minutes, with pencil and calculator. Lab: 2 h 30 to 4 h
(up to 7 h if Python is new to you).

<details><summary>Workspace and words (open if you need them)</summary>

Left: **Course**, **Lab**, and **✔ Check my work** (tests your files, gives hints). Right: **📝 Code**
(editor, `Ctrl+S` saves) and **⌨️ Terminal**. `~/navera/` is your own copy of NAVERA: you may change
anything (the 👤 menu resets it).

| Word | Meaning | Français |
|---|---|---|
| **pseudorange** | a measured range that includes the receiver's clock error | pseudo-distance |
| **clock bias** | the receiver clock error expressed as a distance, c × time error | biais d'horloge |
| **residual** | measured value − value predicted by a model | résidu |
| **least squares** | choose the unknowns that minimise the sum of squared residuals | moindres carrés |
| **Jacobian** | the matrix of partial derivatives of the predictions with respect to the unknowns | jacobienne |
| **fix** | one position computed by a receiver ("no fix" = none) | position calculée |
| **jamming / spoofing** | noise on the GPS band / fake but consistent GPS signals | brouillage / leurrage |
| **arbiter** | the NAVERA program that decides which position to trust | arbitre |
| **uncertainty (σ)** | how far off a position may be, stated by its source (e.g. 30 m) | incertitude |
</details>

## 1. Ranging: a time becomes a distance

A satellite cannot see you; it only broadcasts. Each GPS satellite repeats, in essence: *"I am here
(orbit data), and I sent this signal at exactly t₀ by my atomic clock."* Your receiver notes the
arrival time t₁ **on its own clock** and converts the travel time into a range with the speed of
light, `c ≈ 300 000 km/s`:

```
range = c × (t₁ − t₀)          0.07 s of travel  →  21 000 km
```

Picture a storm behind a hill: you cannot see the flash, but a weather station radios *"lightning at
15:00:00"*, and you hear the thunder at 15:00:03 by your watch: 3 s × 340 m/s ≈ 1 km. Two clocks are
involved, the station's and yours. Keep that in mind for §3.

The number that rules everything: at the speed of light, **1 µs** of timing error is **300 m** of
range error, and 1 ns is 30 cm. Satellite navigation is, above all, a clock problem.

## 2. Trilateration as a least-squares problem

**A flat model first.** On a 10 km × 10 km field, three beacons sit at `A = (0, 0)`, `B = (10, 0)`,
`C = (0, 10)` (km). You measure ranges **5.000**, **8.062** and **6.708** km. Each range puts you on a
circle; two circles cross in two points; the third picks one: **(3, 4)**.

![Three beacons and three circles. Left: the circles meet at the true position. Right: every range is 0.3 km too long, and they no longer meet in one point.](assets/beacons.svg)

**How a computer does it.** It scores a candidate position `p`. For each beacon, the **residual** is the
measured range minus the range predicted from `p`. The position is the `p` that minimises the sum of
squared residuals, which we call the **mismatch**:

```
mismatch(p) = Σᵢ ( measuredᵢ − ‖p − beaconᵢ‖ )²          ‖·‖ = Euclidean distance
```

That is a **least-squares** problem, the same family as fitting a line to data. Why squares, not
absolute values? A sum of squares is smooth, so it can be differentiated, and §3 needs exactly that.

**Worked example.** The candidate `p = (4, 4)`:

| Beacon | Predicted ‖p − beacon‖ | Measured | Residual | Squared |
|---|---|---|---|---|
| A | √(4² + 4²) = 5.657 | 5.000 | −0.657 | 0.431 |
| B | √(6² + 4²) = 7.211 | 8.062 | +0.851 | 0.725 |
| C | √(4² + 6²) = 7.211 | 6.708 | −0.503 | 0.253 |
| | | | **mismatch** | **1.409** |

Mapped over the field, the mismatch is a valley whose lowest point is the position:

![The mismatch of every point of the field: a valley whose lowest point is (3, 4)](assets/mismatch_map.png)

> [!QUESTION] ✏️ Check
> (3, 5) and (4, 4) are both exactly 1 km from the truth. Which one has the smaller mismatch? Guess
> first, then compute. What does that say about errors in different directions?

<details><summary>Answer</summary>
(3, 5): predicted 5.831, 8.602, 5.831 → residuals −0.831, −0.540, +0.877 → mismatch ≈ 1.75, worse than
1.41. The valley is not round: moving north changes the ranges to A and C a lot (0.8 and 0.9 km per km),
moving east mostly changes B's (0.87); summed and squared, north costs 1.69 per km², east 1.31. The
<b>geometry</b> of the beacons makes some error directions cheap and others expensive. A long flat
valley means poor precision in that direction: this is <b>dilution of precision</b> (DOP). §3 shows
where it comes from; mission 15 uses it on real satellites.
</details>

## 3. The clock: four unknowns, and how real receivers solve them

The satellites carry atomic clocks; your receiver has a quartz clock that can be off by microseconds
up to a millisecond, i.e. hundreds of metres up to 300 km. Back to the storm: if **your** watch is
0.5 s ahead, the storm seems 170 m too far, and so does **every** storm, by the same amount, because
the station's clock and yours are different clocks. (Timing the visible flash on your own watch would
cancel the error; GPS cannot do that, the start time is always the satellite's.)

So every range is biased by the same `b = c × (receiver clock error)`. These are **pseudoranges**:

```
pseudorangeᵢ = ‖p − satelliteᵢ‖ + b
```

With a clock 1 µs ahead (b = 0.3 km) our ranges become 5.300, 8.362, 7.008, and the circles no longer
meet in one point. The trick that makes GPS work: `b` is **shared by all satellites**, so it is just
one more unknown. Solve for `(x, y, z, b)`:

| Situation | Unknowns | Measurements needed |
|---|---|---|
| flat field, perfect clock | x, y | 2, plus 1 to remove the mirror point |
| flat field, cheap clock | x, y, b | 3 |
| real GPS | x, y, z, b | **4** (the mirror solution usually lies far from the Earth's surface) |

Hence **four satellites**, and GPS gives you the time for free.

**Solver 1: brute force.** Try every point of a grid and keep the smallest mismatch (lab Step 2). Two unknowns: two nested loops,
101² = 10 201 candidates. With the clock in 21 steps: 214 221. Now
real GPS at 1 m resolution: x, y, z over ±7 000 km and b over ±300 km is more than 10²⁷ candidates. At a
billion per second, longer than the age of the universe. We need something smarter.

**Solver 2: Gauss–Newton.** Start from a guess `(x, y, b)`. Near the guess, each prediction is almost
linear in a small correction `Δ = (Δx, Δy, Δb)`:

```
‖p + Δp − sᵢ‖ + b + Δb  ≈  dᵢ + b  +  uᵢ · Δp  +  Δb          dᵢ = ‖p − sᵢ‖,   uᵢ = (p − sᵢ) / dᵢ
```

`uᵢ` is the unit vector from the satellite to you: the derivative of a distance is a unit vector.
(`uᵢ · Δp` is a dot product: uₓΔx + u_yΔy.)

> [!TIP] 🧰 Derivative of a distance
> `d = √((x − sₓ)² + (y − s_y)²)` gives `∂d/∂x = (x − sₓ)/d` and `∂d/∂y = (y − s_y)/d`: a vector of length 1.
> Intuition: move 0.1 km straight away from the beacon and the range grows by 0.1; move sideways and it
> barely changes. Check at p = (4, 4), s = (0, 0): d = 5.657, u = (0.707, 0.707); moving 0.1 km east gives
> d = 5.728, i.e. +0.071 = 0.707 × 0.1.

Stack
one row `[uᵢ, 1]` per satellite into the **Jacobian** `H`, and the residuals `rᵢ = ρᵢ − (dᵢ + b)` into
`r`. The correction solves the linear least-squares problem

```
H Δ ≈ r          Δ = (Hᵀ H)⁻¹ Hᵀ r       (in numpy: np.linalg.lstsq(H, r))
```

Apply `Δ`, recompute, repeat. Each step is linear algebra, not a search.

> [!TIP] 🧰 What `lstsq` does, without the formula
> With 3 beacons and 3 unknowns, H is square: Δ is simply the solution of 3 linear equations, as at
> school. For the worked example below they read −0.357 = 0.707 Δx + 0.707 Δy + Δb,
> +1.151 = −0.832 Δx + 0.555 Δy + Δb and −0.203 = 0.555 Δx − 0.832 Δy + Δb. With more beacons than unknowns there is no exact solution, and `lstsq` returns the Δ whose
> squared leftovers are smallest: the same "mismatch" idea as §2, for a straight-line model. You never
> invert a matrix by hand.

**Worked example** (pseudoranges 5.300, 8.362, 7.008; guess (4, 4), b = 0):

| Beacon | dᵢ | rᵢ = ρᵢ − dᵢ − b | Row of H: uₓ, u_y, 1 |
|---|---|---|---|
| A (0, 0) | 5.657 | −0.357 | 0.707, 0.707, 1 |
| B (10, 0) | 7.211 | +1.151 | −0.832, 0.555, 1 |
| C (0, 10) | 7.211 | −0.203 | 0.555, −0.832, 1 |

Solving gives `Δ = (−0.979, −0.003, +0.338)`, so the new guess is (3.021, 3.997), b = 0.338. One more
step lands on (3.000, 4.000), b = 0.300, to within 0.2 m (the ranges are rounded to the metre, so no
solver can do better): two iterations. This is what a real receiver does, in 3-D, many times per
second.

`(HᵀH)⁻¹` is also where DOP comes from: with independent range noise σ on every satellite, the
covariance of the solution is σ²(HᵀH)⁻¹, and the horizontal error is about HDOP × σ with
`HDOP = √((HᵀH)⁻¹ₓₓ + (HᵀH)⁻¹ᵧᵧ)` (x, y = east, north: the first two numbers on the diagonal, not the bias
one). A flat valley in §2 is a large HDOP; you
compute it in lab Step 5.

> [!QUESTION] ✏️ Check
> 1. A ship knows its altitude. How many satellites does it need?
> 2. Why not put an atomic clock in every receiver?
> 3. Gauss–Newton needs a starting guess. What could go wrong with a very bad one?

<details><summary>Answer</summary>
1. Unknowns x, y, b: three.<br>
2. Cost, size and power: a chip-scale atomic clock costs far more than a whole consumer receiver and
still drifts. Solving for b with one extra satellite is free.<br>
3. The linear approximation is only good near the guess: from far away it can converge slowly, jump to
the mirror solution, or diverge. Receivers start from the last fix or the centre of the Earth, which
works for GPS geometry.
</details>

## 4. Attacking GPS

A GPS signal reaches the ground at about **−130 dBm** (dBm = power in decibels relative to 1 mW; 30 dBm
= 1 W), roughly 10⁻¹⁶ W, **below** the receiver's
thermal noise. It is recovered only because the receiver knows each satellite's code and correlates
for milliseconds. A transmitter on the same band does not need much power to win.

| Threat | What happens | Does the receiver notice? |
|---|---|---|
| **Outage** | buildings, terrain, tunnels block the signal | yes: few satellites, poor geometry, or no fix |
| **Jamming** | noise is transmitted on the GPS band | yes: it loses the signal |
| **Spoofing** | fake signals are transmitted for a chosen false position | **?** — lab Step 6 |
| **Meaconing** | real signals are recorded and re-broadcast later | **?** — same idea |

A spoofer needs no cryptography against civil GPS: it computes, for its chosen false position, the
pseudoranges a receiver *would* measure there (the formula of §3), and broadcasts matching signals a
little stronger than the real ones. Interference is not rare: besides the Black Sea case, years of
reports around the Baltic, the Eastern Mediterranean and the Middle East describe ships and
airliners with false or missing GPS positions.

> [!QUESTION] ✏️ Check
> In free space, a radio signal loses `FSPL(dB) = 20·log₁₀(d_km) + 20·log₁₀(f_MHz) + 32.44`. A cheap
> 1 W jammer (30 dBm) transmits at the GPS frequency, 1 575.42 MHz, from 10 km away. How much stronger
> than the GPS signal (−130 dBm) does it arrive?

<details><summary>Answer</summary>
FSPL = 20 + 63.9 + 32.4 ≈ 116.4 dB, so the jammer arrives at 30 − 116.4 ≈ −86 dBm: about 44 dB above the
satellite, i.e. 10^4.4 ≈ 25 000 times stronger (decibels to a ratio: 10^(dB/10); +10 dB = ×10,
+3 dB = ×2). A civil receiver typically tolerates a jammer some 25–40 dB above the signal: 44 dB is
beyond it. Even with terrain and antenna losses, a drone at altitude can lose GPS to a one-watt device
kilometres away.
</details>

## 5. NAVERA: witnesses, a judge and a messenger

NAVERA runs on a small NVIDIA computer next to the autopilot.

![NAVERA's architecture: sources, arbiter, output to the autopilot](assets/architecture.svg)

(Look at the three big boxes; the small labels come in later missions.)

- **Sources (witnesses)** each give a position and, when they can, a stated uncertainty σ: GPS;
  **day vision** (camera matched against a stored satellite map); **night vision** (thermal image
  against the map); **celestial** (stars). The **IMU** gives the attitude; integrated for position it
  drifts fast, so NAVERA does not use it as a position source today.
- **The arbiter (judge)**, `estimator_node`, decides whenever an estimate arrives and at least five
  times per second. A source is eligible if it is valid and **fresh** (GPS: younger than 3 s). Among
  eligible sources the **priority** order wins: **GPS > day > night > celestial**. Not the most
  precise one: the first in priority. (A higher-priority source that comes back waits a hold-off
  of 2 s before taking over while the current source is still usable; if the current source is lost,
  the switch is immediate.)
- **The output (messenger)** hands the result to the autopilot in the same format as a GPS receiver,
  so the autopilot needs no code change, only configuration (tested with ArduPilot in simulation).

| State | Rule |
|---|---|
| **FIX** | fresh, measured, with a stated σ ≤ 25 m (any source) |
| **DEGRADED** | a position exists, but its σ is unknown or > 25 m, or it is propagated (dead-reckoned) |
| **NO_FIX** | nothing usable; an old position is never re-sent as new |

Today day vision states σ = 30 m (a conservative value, not yet measured with NAVERA's own camera)
and night vision states none, so vision positions show DEGRADED.

### The jump gate, and the cross-check

A vehicle cannot teleport. The arbiter refuses a GPS fix that is farther from the **last trusted** fix
than the vehicle could have travelled:

```
refuse if   distance(last trusted fix, new fix)  >  v_max × elapsed + margin
```

**Worked example**, NAVERA's defaults `v_max = 100 m/s`, `margin = 50 m`, one fix per second, **no
other source available**. The GPS jumps 500 m, stays there, then jumps 400 m further:

| Fix | Distance from last trusted | Elapsed | Gate | Decision |
|---|---|---|---|---|
| 1–4 | 500 m | 1, 2, 3, 4 s | 150, 250, 350, 450 m | refused ×4 |
| 5 | 500 m | 5 s | 550 m | **accepted** → new trusted fix, elapsed restarts |
| 6 | 0 m | 1 s | 150 m | accepted |
| 7 | 400 m | 1 s | 150 m | refused |

Refused fixes never become trusted, so `elapsed` grows and the gate widens until the fake position is
"reachable": alone, the gate only **delays** a jump. What that means for an attacker who moves the fake
position slowly is your lab Steps 7 and 10.

![The gate grows with the time since the last trusted fix. A 500 m jump is refused for 4 seconds, then accepted.](assets/gate.svg)

NAVERA's real defence is the **cross-check**: GPS must agree with an independent source that states
its uncertainty (σ, one standard deviation). With day vision (σ 30 m), NAVERA compares each GPS fix with
the latest vision fix, allowing for what the vehicle can fly between the two:

- **Gap:** farther than **5 σ + 50 m** (200 m) for 3 s → GPS refused.
- **Streak:** 5 vision fixes in a row farther than **3 σ** (90 m) → refused; this catches a slow drag
  sooner. From 2 such fixes in a row GPS is already shown "in doubt" (DEGRADED).
- **Return:** a refused GPS comes back when 2 vision fixes in a row agree within 3 σ.

Day vision matches about every 2 s, so a streak of 5 takes about 10 s: in NAVERA's mission simulator, a
GPS dragged at 4 m/s was refused about 140 m from the truth. Where vision cannot match (over the sea, on uniform ground) there is no such source, and a
patient spoof is not detected. NAVERA's documentation
(`docs/VALIDATION_STATUS.md`) states this limit openly. The lab puts this limit to the test.

In your copy, these rules are four settings of
`navera_estimator/navera_estimator/config/estimator_params.yaml` (comments added here):

```yaml
    gps_timeout_s: 3.0        # older than this: not fresh
    fix_max_sigma_m: 25.0     # largest σ shown as FIX
    max_speed_mps: 100.0      # v_max of the jump gate (set per vehicle)
    gps_jump_margin_m: 50.0   # margin of the jump gate
```

> [!QUESTION] ✏️ Check
> 1. GPS is jammed. Day vision is fresh with σ 40 m; night vision (suppose a future version states
>    a σ) is fresh with σ 10 m. Which source, which state?
> 2. Same gate settings, no other source: a fix arrives 3 s after the last trusted one, 320 m away.
>    And after 2 s?

<details><summary>Answer</summary>
1. <b>Day vision</b> (priority, not precision), and 40 m > 25 m → <b>DEGRADED</b>.<br>
2. After 3 s the gate is 350 m: accepted. After 2 s it is 250 m: refused.
</details>

> [!WARNING]
> NAVERA is **Release 0.2 — field validation pending**. `docs/VALIDATION_STATUS.md` lists what has been
> measured and how, e.g. day vision placed 32 of 33 aerial test photos within 9 m (median 4 m) **on the
> bench**, with photos not taken by NAVERA's own camera. Always quote a number with its conditions.
> NAVERA's test map and data cover the region of Sousse, Tunisia.

> [!WARNING] Common wrong ideas
> - "Satellites track you." They only broadcast; your receiver computes everything.
> - "The most precise source wins." Priority wins; precision only sets the state.
> - "A 1 µs clock error moves the fix 300 m." It adds 300 m to every *range*; solved as the unknown b, it does
>   not move the fix at all.
> - "A strong, clean signal is a true signal." A spoofer's signal is stronger than the real one.

## 🐦 How birds do it

A European robin's magnetic compass stops working under weak man-made radio noise (Engels et al.,
*Nature* 2014): birds get jammed too. Night-migrating thrushes recalibrate that compass from the sunset
every evening (Cochran et al., *Science* 2004): an independent, trusted source correcting a drifting
one. That is NAVERA's cross-check: GPS stays trusted only while an independent witness agrees with it.

![The senses of a migrating bird, and the NAVERA source each one inspired](assets/bird_senses.svg)

## Summary

1. Ranging turns a travel time into a distance; at light speed, **1 µs = 300 m**.
2. A position is the solution of a **least-squares** problem: brute force works in a toy, real
   receivers linearise (**Gauss–Newton**: `H Δ ≈ r`).
3. One cheap clock biases every range equally: a 4th unknown, hence **4 satellites**, and the time
   for free.
4. Jamming is noticed. What spoofing does to the residuals is the subject of the lab.
5. NAVERA's arbiter chooses by freshness and **priority**, reports FIX / DEGRADED / NO_FIX, and guards
   GPS with a jump gate (which alone only delays a jump) and a cross-check (which needs a source with a
   stated σ, e.g. day vision over land).

**Next mission:** the terminal, your control panel for the NAVERA computer.

## Check yourself

Answer without scrolling up.

<details><summary>1. Why does a receiver need four satellites, and what does it get "for free"?</summary>
Unknowns x, y, z and the clock bias b. Solving for b gives the receiver's clock error, so GPS is also a
precise time source.
</details>

<details><summary>2. Write the row of the Jacobian for one satellite, and say what each entry means.</summary>
[uₓ, u_y, u_z, 1]: the unit vector from the satellite to the receiver (how the range changes when you
move), and 1 for the clock bias (every range changes by the same Δb).
</details>

<details><summary>3. Your receiver's clock is 2 µs ahead. What happens to the pseudoranges, and to the solved position?</summary>
Every pseudorange is 0.6 km too long. The position is unaffected: the solver absorbs it into b ≈ 0.6 km.
</details>

<details><summary>4. GPS is 5 s old, day vision has nothing, night vision is fresh and (suppose) states σ 12 m. Source and state?</summary>
GPS is not fresh (> 3 s), so <b>night vision</b>; 12 m ≤ 25 m → <b>FIX</b>.
</details>


Now open the **🛠️ Lab** tab.
