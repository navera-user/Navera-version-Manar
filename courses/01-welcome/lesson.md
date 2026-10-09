# Welcome: navigation without GNSS

> [!NOTE] Mission brief
> **June 2017, Black Sea.** About twenty ships report the same strange GPS position: an airport on
> land, tens of kilometres from where they really are. No alarm on any receiver. Every position looks
> precise and normal.
>
> By the end of this mission you will know exactly how that is possible, because you will do it
> yourself: you will **build** a satellite-style position solver, **break** it, **attack** it as a
> spoofer, and then find the **hole** in NAVERA's own defence.

**Objectives.** After this mission you can:

1. explain trilateration and why a cheap clock turns it into a **4-unknown** problem;
2. compute a position as a **least-squares** problem, by hand and in Python;
3. explain why jamming is detectable and a good spoof is not;
4. reason like NAVERA's arbiter: source priority, the FIX / DEGRADED / NO_FIX states, and the jump gate,
   including what it **cannot** stop.

⏱ Reading: about 60 minutes, pencil in hand. Lab: 2 h 30 to 4 h.

**How this mission works.** The lesson gives you each idea with one worked example, then a short
**✏️ check** (answer hidden: try first). The lab is where you write all the code yourself. Your
workspace: **Course** and **Lab** on the left, **✔ Check my work** at the bottom; **📝 Code** and
**⌨️ Terminal** on the right. `~/navera/` is your own copy of NAVERA: you may change anything (the
👤 menu resets it).

| Word | Meaning | Français |
|---|---|---|
| **GNSS / GPS** | satellite navigation in general / the American system | GNSS / GPS |
| **pseudorange** | a measured range that includes the receiver's clock error | pseudo-distance |
| **clock bias** | the receiver clock error, expressed as a distance (c × time error) | biais d'horloge |
| **residual** | measured value − value predicted by a model | résidu |
| **least squares** | choose the unknowns that minimise the sum of squared residuals | moindres carrés |
| **fix** | one position computed by a receiver ("no fix" = none) | position calculée |
| **jamming / spoofing** | noise on the GPS band / fake but consistent GPS signals | brouillage / leurrage |
| **autopilot** | the flight computer (ArduPilot, PX4) | autopilote |
| **arbiter** | the NAVERA program that decides which position to trust | arbitre |
| **uncertainty** | how far off a position may be (e.g. ± 10 m) | incertitude |

## 1. Ranging: a time becomes a distance

A satellite cannot see you; it only broadcasts. Each GPS satellite repeats, in essence: *"I am here
(orbit data), and I sent this signal at exactly t₀ by my atomic clock."* Your receiver notes the
arrival time t₁ **on its own clock**, and converts the travel time into a range with the speed of
light, `c ≈ 300 000 km/s`:

```
range = c × (t₁ − t₀)          0.07 s of travel  →  21 000 km
```

Think of a storm behind a hill. You cannot see the flash, but a weather station radios: *"Lightning
at 15:00:00."* You hear the thunder at 15:00:03 by your watch: 3 s × 340 m/s ≈ 1 km. Two clocks are
involved, the station's and yours. Keep that in mind: it is the whole problem of §3.

Now the uncomfortable number: at the speed of light, **1 µs** of timing error is **300 m** of range
error. 1 ns is 30 cm. Satellite navigation is, above all, a clock problem.

## 2. Trilateration as a least-squares problem

**A flat model first.** On a 10 km × 10 km field, three beacons sit at known places (km):
`A = (0, 0)`, `B = (10, 0)`, `C = (0, 10)`. You measure ranges **5.000**, **8.062** and **6.708** km.
Each range puts you on a circle; two circles cross in two points; the third picks one. Here they
meet at **(3, 4)**.

![Three beacons and three circles. Left: the circles meet at the true position. Right: every range is 0.3 km too long, and they no longer meet in one point.](assets/beacons.svg)

**How a computer does it.** It cannot "look" at circles. It scores a candidate position `p`: for each
beacon, the **residual** is the range you would measure from `p` minus the range you measured. The
**mismatch** is the sum of the squared residuals:

```
mismatch(p) = Σ  ( ‖p − beaconᵢ‖ − measuredᵢ )²          ‖·‖ = Euclidean distance (Pythagoras)
```

The position is the `p` that **minimises** it. That is a **least-squares** problem, the same family
as fitting a line to data points. Squaring keeps a −0.8 and a +0.8 from cancelling, and makes large
errors weigh much more than small ones.

**Worked example.** The candidate `p = (4, 4)`:

| Beacon | Range from (4, 4) | Measured | Residual | Squared |
|---|---|---|---|---|
| A | √(4² + 4²) = 5.657 | 5.000 | +0.657 | 0.431 |
| B | √(6² + 4²) = 7.211 | 8.062 | −0.851 | 0.725 |
| C | √(4² + 6²) = 7.211 | 6.708 | +0.503 | 0.253 |
| | | | **mismatch** | **1.409** |

At (3, 4) all residuals are 0. Mapped over the whole field, the mismatch is a valley whose lowest
point is the position:

![The mismatch of every point of the field: a valley whose lowest point is (3, 4)](assets/mismatch_map.png)

> [!QUESTION] ✏️ Check
> (3, 5) and (4, 4) are both exactly 1 km from the truth. Which one has the smaller mismatch? Guess
> first, then compute. What does it tell you about errors in different directions?

<details><summary>Answer</summary>
(3, 5): ranges 5.831, 8.602, 5.831 → residuals +0.831, +0.540, −0.877 → mismatch ≈ 1.75, worse than
1.41. The valley is not round: moving north changes the ranges to A and C a lot, moving east changes
them less. The <b>geometry</b> of the beacons makes some error directions cheap and others expensive.
Real GPS has the same effect: satellites bunched in one part of the sky give a long, flat valley and
a poor fix. This is called <b>dilution of precision</b> (DOP).
</details>

## 3. The clock problem: four unknowns, four satellites

The satellites carry atomic clocks. Your receiver has a quartz clock that may be off by
microseconds, which is hundreds of metres. Back to the storm: if **your** watch is 0.5 s ahead, you
read 15:00:03.5 instead of 15:00:03, and the storm seems 170 m too far. Every storm, by the same
170 m, because the station's clock and yours are different clocks. (Had you timed the visible flash
on your own watch, the error would cancel. GPS cannot do that: the start time is always the
satellite's.)

So a receiver whose clock is 1 µs ahead measures every range 0.3 km too long. These biased ranges
are **pseudoranges**:

```
pseudorange = true range + b          b = c × (receiver clock error) = 0.3 km for 1 µs
```

With pseudoranges 5.300, 8.362, 7.008 the circles no longer meet in a single point (right picture
above). What does a least-squares search find then? Write down a guess: you test it in the lab.

**The trick that makes GPS work.** We do not know `b`, but it is **the same for every satellite**,
because there is one receiver clock. So make it an unknown:

```
predicted pseudorange = ‖p − satelliteᵢ‖ + b          unknowns: x, y, (z), b
```

Minimise the mismatch over `(x, y, b)` and you get the position **and** the clock error. Counting:

| Situation | Unknowns | Measurements needed |
|---|---|---|
| flat field, perfect clock | x, y | 2, plus 1 to remove the mirror point |
| flat field, cheap clock | x, y, b | 3 |
| real GPS, cheap clock | x, y, z, b | **4** (the mirror solution lies far out in space) |

That is why a receiver needs **four satellites**, and why GPS is also the world's most used time
source: every fix solves for the time as well.

> [!QUESTION] ✏️ Check
> 1. A ship knows its altitude (sea level). How many satellites does it need?
> 2. Why not just put an atomic clock in every receiver?

<details><summary>Answer</summary>
1. Unknowns x, y, b: three satellites.<br>
2. Cost, size and power. A chip-scale atomic clock exists, but it costs far more than a whole
consumer receiver and still drifts. Solving for b with one extra satellite is free.
</details>

**Search, then something smarter.** The simplest solver tries every point of a grid and keeps the
smallest mismatch. In Python, in one dimension (which x in [0, 10], step 0.1, has x² closest to 20):

```python
best_x, best_err = None, None
for i in range(101):                  # integers, then scale: no accumulated rounding
    x = i / 10
    err = (x * x - 20) ** 2
    if best_err is None or err < best_err:
        best_x, best_err = x, err
print(best_x)                         # 4.5
```

Two unknowns means one loop inside the other; three unknowns, three loops. Count the cost: a 0.1 km
grid over 10 km is 101 × 101 = 10 201 candidates in 2-D. Add the clock in 21 steps and it is 214 221.
Now try **real** GPS: x, y, z over the Earth at 1 m and b over 1 ms at 1 m… far more candidates than
any computer can try. Real receivers therefore **linearise**: start from a guess, compute in which
direction the mismatch goes down (its gradient), jump, repeat. That is Gauss–Newton least squares;
it converges in a handful of steps. You run such a solver with 8 satellites in the lab's "Going
further".

> [!TIP] The core idea of satellite navigation
> **Position (and clock) = the unknowns that minimise the squared residuals of the pseudoranges.**

## 4. Attacking GPS

A GPS signal reaches the ground at about **−130 dBm**, roughly 10⁻¹⁶ W, **below** the thermal
noise of the receiver. It is recovered only because the receiver knows the satellite's code and
correlates for milliseconds. The consequence: a one-watt transmitter can overpower it over
kilometres, and a drone at altitude sees transmitters far away.

| Threat | What happens | Does the receiver notice? |
|---|---|---|
| **Outage** | buildings, terrain, tunnels block the signal | yes: few satellites, poor geometry, or no fix |
| **Jamming** | noise is transmitted on the GPS band | yes: it loses the signal, "no fix" |
| **Spoofing** | fake signals are transmitted for a chosen false position | **?** — you find out in lab Step 8 |
| **Meaconing** | real signals are recorded and re-broadcast later | **?** — same idea |

A spoofer does not need to break any cryptography in civil GPS. It computes, for its chosen false
position, the pseudoranges a receiver *would* measure there (your `predicted pseudorange` formula),
and broadcasts the matching signals a little stronger than the real ones. The receiver then
minimises its mismatch as usual… Before the lab, think: what value will that minimum have?

Real cases are not rare: the 2017 Black Sea event in the brief, years of interference reports
around the Baltic, the Eastern Mediterranean and the Middle East, and airliners whose GPS showed a
false position for part of a flight.

> [!QUESTION] ✏️ Check
> Classify: (a) a drone in a narrow canyon sees two satellites; (b) every receiver near a truck
> reports "no fix" as it passes; (c) the Black Sea case of the brief.

<details><summary>Answer</summary>
(a) outage; (b) jamming (the receivers notice); (c) spoofing, or possibly meaconing: from the screen
alone you cannot tell which.
</details>

## 5. NAVERA: witnesses, a judge and a messenger

NAVERA runs on a small NVIDIA computer next to the autopilot.

![NAVERA's architecture: sources, arbiter, output to the autopilot](assets/architecture.svg)

(Look at the three big boxes; the small labels come in later missions.)

- **Sources (witnesses)** each give a position with an uncertainty: GPS (mission 15), **day vision**
  (camera vs satellite map, 17–23), **night vision** (thermal image vs map, 24), **celestial** (stars,
  24). The **IMU** (gyroscopes and accelerometers, 16) gives the attitude; integrating it for position
  drifts fast, so NAVERA does not use it as a position source today.
- **The arbiter (judge)**, `estimator_node`, decides five times per second. A source is eligible if
  it is valid and **fresh** (GPS: younger than 3 s). Among eligible sources the **priority** order
  wins: **GPS > day > night > celestial**. Not the most precise one: the first in priority.
- **The output (messenger)** hands the result to the autopilot **in the same format as a GPS
  receiver**, so the autopilot needs no change, plus a state that says how much to trust it:

| State | Rule |
|---|---|
| **FIX** | fresh, measured, with a stated uncertainty ≤ 25 m (any source) |
| **DEGRADED** | a position exists, but its uncertainty is unknown or > 25 m |
| **NO_FIX** | nothing usable; an old position is never re-sent as new |

Today NAVERA's vision sources do not yet state a validated uncertainty, so in practice they show
DEGRADED. In exercises, when a source states one, apply the 25 m rule whatever its name.

### The jump gate, and its blind spot

A vehicle cannot teleport. The arbiter refuses a GPS fix that is farther from the **last trusted**
fix than the vehicle could have travelled:

```
refuse if   distance(last trusted fix, new fix)  >  v_max × elapsed + margin
```

**Worked example**, with NAVERA's defaults `v_max = 100 m/s`, `margin = 50 m`, one fix per second.
The GPS jumps 500 m, stays there, then jumps 400 m further:

| Fix | Distance from last trusted | Elapsed | Gate | Decision |
|---|---|---|---|---|
| 1–4 | 500 m | 1, 2, 3, 4 s | 150, 250, 350, 450 m | refused ×4 |
| 5 | 500 m | 5 s | 550 m | **accepted** → new trusted fix, elapsed restarts |
| 6 | 0 m | 1 s | 150 m | accepted |
| 7 | 400 m | 1 s | 150 m | refused |

Refused fixes never become trusted, so `elapsed` keeps growing and the gate widens until the fake
position is "reachable": the gate only **delays** a jump.

![The gate grows with the time since the last trusted fix. A 500 m jump is refused for 4 seconds, then accepted.](assets/gate.svg)

Worse, a spoofer who **drags** the position in small steps is never refused at all. NAVERA's real
defence is a **cross-check**: GPS must agree with another source that states its uncertainty. Today
NAVERA's vision does not state one yet, so **a patient spoof is not detected today**. NAVERA's own
documentation says so. In the lab you will measure exactly how big that hole is, as the attacker.
Missions 25–27 work on closing it.

In your copy, these rules are four lines of
`navera_estimator/navera_estimator/config/estimator_params.yaml`:

```yaml
    gps_timeout_s: 3.0        # older than this: not fresh
    fix_max_sigma_m: 25.0     # largest uncertainty shown as FIX
    max_speed_mps: 100.0      # v_max of the jump gate
    gps_jump_margin_m: 50.0   # margin of the jump gate
```

> [!QUESTION] ✏️ Check
> 1. GPS is jammed. Day vision is fresh with 40 m uncertainty; night vision is fresh with 10 m.
>    Which source, which state?
> 2. Same gate settings: a fix arrives 3 s after the last trusted one, 320 m away. And after 2 s?

<details><summary>Answer</summary>
1. <b>Day vision</b> (priority, not precision), and 40 m > 25 m → <b>DEGRADED</b>.<br>
2. After 3 s the gate is 350 m: accepted. After 2 s it is 250 m: refused.
</details>

> [!WARNING]
> NAVERA is **Release 0.2 — field validation pending**. `docs/VALIDATION_STATUS.md` lists what has
> been measured and how: e.g. day vision placed 32 of 33 aerial test photos within 9 m (median 4 m)
> **on the bench**, with photos not taken by NAVERA's own camera. Always quote a number with its
> conditions. NAVERA's test map and data cover the region of Sousse, Tunisia.

## 🐦 How birds do it

Migrating birds have no single perfect sense. They combine landmarks, the sun, the stars and a
magnetic sense, and cross-check them; some thrushes even recalibrate their magnetic compass from the
sunset every evening. That is NAVERA's founding idea. Meet **Navi**, a barn swallow, who appears
briefly in every mission.

![Navi's senses, and the NAVERA source each one inspired](assets/bird_senses.svg)

## Summary

1. Ranging turns a travel time into a distance; at light speed, **1 µs = 300 m**.
2. A position is the solution of a **least-squares** problem over the ranges.
3. One cheap receiver clock biases every range equally: it becomes a 4th unknown, hence **4
   satellites**, and GPS gives you the time for free.
4. Jamming is noticed. What a spoof does to the mismatch, you will see in lab Step 8.
5. NAVERA = sources + arbiter + output. The arbiter chooses by freshness and priority, reports
   FIX / DEGRADED / NO_FIX, and its jump gate only delays jumps. Its cross-check needs a source of
   stated uncertainty, which vision does not provide yet.

**Next mission:** the terminal, your control panel for the NAVERA computer.

## Check yourself

Answer without scrolling up.

<details><summary>1. Why does a GPS receiver need four satellites, and what does it get "for free"?</summary>
Unknowns x, y, z and the clock bias b: four equations. Solving for b gives the receiver's clock error,
so GPS is also a precise time source.
</details>

<details><summary>2. Your receiver's clock is 2 µs ahead. What happens to the pseudoranges, and to the solved position?</summary>
Every pseudorange is 0.6 km too long. The solved position is unaffected: the solver absorbs it into b
(b ≈ 0.6 km).
</details>

<details><summary>3. Why is the valley of the mismatch narrow in some directions and flat in others?</summary>
Because of the geometry of the beacons or satellites: moving in some directions changes the ranges a lot,
in others little. Flat directions mean poor precision there (dilution of precision).
</details>

<details><summary>4. GPS is 5 s old, day vision has nothing, night vision is fresh with 12 m. Source and state?</summary>
GPS is not fresh (> 3 s), so <b>night vision</b>; 12 m ≤ 25 m → <b>FIX</b>.
</details>

<details><summary>5. v_max = 100 m/s, margin 50 m, one fix per second. What is the largest jump per fix that is never refused?</summary>
150 m per fix (100 × 1 + 50). Remember this number when you play the attacker in the lab.
</details>

Now open the **🛠️ Lab** tab.
