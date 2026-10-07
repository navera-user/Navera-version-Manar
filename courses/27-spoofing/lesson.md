# Fake GPS and how NAVERA catches it

A delivery drone crosses the bay of Sousse. Suddenly its GPS says it is **2 km north**, over the sea.
Nothing else changed: the motors, the wind, the camera picture of the coast below. If the autopilot
believes the GPS, it will "correct" its course — and fly 2 km the wrong way, convinced it is going home.

That is **spoofing**: someone transmits fake GPS signals, stronger than the real satellites, and the
receiver happily computes a position the attacker chose. The receiver does not know. Its little
"fix OK" light stays green. Only a system that **thinks** about the positions it receives can notice.

This lesson shows the two ideas NAVERA uses — physics, and a second opinion — and their honest limits.

## 1. Jamming vs spoofing (recap)

| | Jamming | Spoofing |
|---|---|---|
| What the attacker sends | noise on the GPS frequency | fake satellite signals |
| What the receiver says | "no fix" (GGA quality 0) | a **wrong** position, "fix OK" |
| Does the receiver know? | **yes** | **no** |
| In NAVERA | `valid = false` → simply not eligible (lesson 25) | must be **detected** by the arbiter |

Jamming is loud but honest: lesson 25 already handles it — the GPS estimate is `valid=false`, the
arbiter switches to vision. Spoofing is the dangerous one. And attackers often do both: **jam first,
then spoof**, so that when "GPS comes back", the receiver locks on the fake signal.

## 2. Idea one: physics — the kinematic gate

A drone that flies at most 30 m/s cannot be 2 km away one second later. So, for each new GPS fix, the
arbiter asks: *could the vehicle have travelled from the last **trusted** fix to here?*

```
reachable = max_speed × (time since the last trusted fix) + margin
```

![The kinematic gate](assets/gate.svg)

- `max_speed_mps` is the vehicle's top speed, **set per vehicle** (`NAVERA_MAX_SPEED_KMH` in the box's
  settings): a boat, a drone and a plane differ by ten times.
- `gps_jump_margin_m` (50 m) allows for the receiver's own noise.

A fix farther than that is **refused**, with a reason the operator can read:

```
GPS refused: implausible jump 2000 m in 0.5 s (max 66 m at 30 m/s) — possible spoofing
```

Measured on the bench (VALIDATION_STATUS.md): *a GPS jump of 5 km in 1 s is refused ("possible
spoofing") and re-accepted once plausible again*; in the mission simulator, a boat spoofed 2 km for
150 s was *refused within 1 s* and continued on vision.

Here is the heart of it, from `_check_gps_plausibility()` in `estimator_node.py`:

```python
lat0, lon0, t0 = self._gps_trusted
dt = max(0.0, (stamp - t0).nanoseconds / 1e9)
dist = _haversine_m(lat0, lon0, msg.latitude, msg.longitude)
reachable = self._max_speed * dt + self._jump_margin
if dist <= reachable:
    self._gps_suspect = None                       # plausible: trust it
    self._gps_trusted = (msg.latitude, msg.longitude, stamp)
else:
    reason = (f"implausible jump {dist:.0f} m in {dt:.1f} s "
              f"(max {reachable:.0f} m at {self._max_speed:.0f} m/s) — possible spoofing")
    self._gps_suspect = reason                     # refused until further notice
```

### The two holes in the gate

The gate is simple and strong, but look at the formula again: the reachable circle **grows with
time**.

1. **The patient spoofer.** The spoofer jumps 2 km and *stays there*. The GPS is refused… but after
   enough seconds, 2 km becomes "reachable" from the old trusted fix, and the gate lets it in. Worse:
   when the real GPS comes back, it is now 2 km from the (fake) trusted fix — and the **true** GPS is
   refused as a jump. This was found in NAVERA's mission simulator: *a 2 km spoof accepted after 33 s,
   then the true GPS locked out* (code comment and VALIDATION_STATUS.md; that is why idea two exists).
2. **The slow drift.** A spoofer who pulls the position away at 4 m/s never makes a jump: every single
   fix is reachable. The gate never fires. The autopilot follows the drift, metre by metre.

And "jam, then spoof" combines both: after a long outage, *almost any* position is reachable.

## 3. Idea two: a second opinion — the vision cross-check

The cure is an **independent** source: something that measures the position *without* using the GPS.
Day vision does exactly that: it matches the camera picture with the satellite map. If the GPS says
"2 km north, over the sea" and the camera sees the harbour, one of them is lying — and the camera
cannot be spoofed by a radio transmitter.

So, while GPS is good, NAVERA's day vision keeps checking one frame every 2 s around the GPS position
(`gps_check_period_s`) and publishes it as an independent estimate with its **stated** accuracy. The
arbiter compares every GPS fix with the most accurate fresh independent fix, at the instant that fix
was measured. With σ the vision's stated accuracy (lesson 26):

![A slow drift caught by the cross-check](assets/crosscheck.svg)

| Rule (ARCHITECTURE.md §3) | What happens |
|---|---|
| **In doubt** — 2 distinct vision fixes in a row beyond 3σ | GPS still used, but its published accuracy becomes no better than the gap → DEGRADED; reason `GPS IN DOUBT: day vision disagrees by N m (possible slow spoofing)`. (A gap above 500 m is more likely a wrong vision match: no doubt applied.) |
| **Refused, slow drift** — 5 distinct vision fixes in a row beyond 3σ | `GPS drifting away from day vision: 5 independent fixes in a row beyond 3 sigma …` |
| **Refused, clear disagreement** — beyond 5σ + 50 m for 3 s, with at least 2 distinct vision fixes | `GPS drifting away from day vision: N m apart for 3 s …` |
| **Never on one fix** | one wrong vision match (it happens!) never refuses a good GPS |
| **Re-acceptance** — a refused GPS, or a GPS returning after an outage | only when **2 distinct vision fixes agree within 3σ**: `GPS confirmed by day vision (… 2 fixes) — re-accepted` |

"Beyond 3σ" also adds `max_speed × the time between the two measurements`, because a photo taken 1 s
before the GPS fix describes a place the vehicle has since left.

Why these numbers? Look at lesson 26: with an honest σ, a fix beyond 3σ is rare (about 1 in 100 on
a map). Five **independent** ones in a row by chance is so unlikely — the code comment says *"chance:
< 1e-12"* — that it is not bad luck any more: it is an attack (or a broken source).

Why "in doubt" before "refused"? Because the operator and the autopilot should know **early**. A GPS in
doubt is still used, but with a large stated uncertainty, so the autopilot already weighs it less and a
later switch to vision is no surprise.

Measured (VALIDATION_STATUS.md, **simulator**): a drone spoofed by a slow drift (4 m/s) — *refused at
~140–200 m*, NAVERA's error median 15 m, max 143 m (before the cross-check: median 417 m, max 902 m,
never refused). A drone jammed 30 s then spoofed 2 km for 30 s — *spoof refused throughout; true GPS
re-accepted 3 s after it returns*.

## 4. The honest limit

Read this sentence from ARCHITECTURE.md twice:

> All three protections need an independent source with a stated accuracy. With vision of unknown
> accuracy only the kinematic gate applies: a sudden jump is caught, a patient or gradual spoofer is not.

A vision position with *unknown* accuracy cannot vouch for or against GPS: if you don't know whether
vision is within 10 m or 500 m, a 100 m disagreement proves nothing. So:

- over the sea, the desert, any terrain vision cannot match → **no independent source** → only the
  kinematic gate;
- if vision states a σ that is too small (dishonest), the cross-check could refuse a **good** GPS.

That is why lesson 26 insisted on honest σ, and why VALIDATION_STATUS.md lists GPS spoofing as *known
limitation 7*. Day vision states σ 30 m today, **not yet measured with NAVERA's camera**.

## 🐦 How birds do it

Birds can be fooled too — and the ways they are fooled look a lot like jamming and spoofing.

**False light.** Many songbirds migrate at night. Brightly lit towers, buildings and even strong
light beams can **attract and trap** them: birds circle around the lights for hours, wasting energy,
and many crash into lit glass. This is very well documented, and it is why some cities now switch
off decorative lights during migration nights. To the bird, the light is a **false signal**, much
stronger than the faint stars it should read — just like a spoofer's signal is stronger than the
real satellites.

**Radio noise.** In 2014, researchers in Oldenburg (Germany) found that European robins on their
university campus could not use their magnetic compass. The cause was weak, human-made radio-frequency
noise from electronic devices. Inside huts screened with grounded aluminium, the robins oriented again.
That is a kind of **jamming** of a natural sensor.

**Magnetic storms.** Some homing pigeon races have had unusually poor returns on days of strong solar
and geomagnetic activity. Scientists suspect the disturbed magnetic field confused the birds, but
this is **debated** and not proven.

What saves birds is the same thing that saves NAVERA: **more than one sense**. A bird with stars,
sunset, landmarks and a magnetic compass can notice when one of them disagrees with the others. A
single fooled sense is dangerous; a cross-checked one is much harder to fool.

## 5. In NAVERA

| What | Where in your copy |
|---|---|
| Kinematic gate | `estimator_node.py`, `_check_gps_plausibility()` |
| Cross-check while GPS is trusted (in doubt, refused) | `_drifting_away()`, `_refuse()`, `_in_doubt()` |
| The independent reference (fresh, stated σ, same instant) | `_independent_reference()`, `_gps_near()` |
| The constants | `STREAK_N = 5`, `DOUBT_MAX_M = 500.0`, `gps_crosscheck_sigmas` (5), `gps_crosscheck_persist_s` (3 s) |
| The top speed | `max_speed_mps`, from `NAVERA_MAX_SPEED_KMH` (`navera_common/vehicle.py`) |
| Vision checking GPS every 2 s | `day_pkg` (`gps_check_period_s`, `gps_check_radius_m` 600 m) |
| The integration test (jump, patient spoof, jam-then-spoof, drift, one wrong vision fix) | `navera_tools/tests/test_estimator.py` |

One more protection worth knowing: vision takes its search centre from the **arbiter's output**
(`/navera/position`), never from the raw GPS. So a GPS the arbiter refused cannot drag the vision
search away. (A QA campaign found the opposite once: vision followed the spoofed GPS and the drone
landed. Fixed — VALIDATION_STATUS.md, *QA campaign 2026-09-30*.)

## Glossary

| Word | Meaning |
|---|---|
| **spoofing** | sending fake GPS signals so the receiver computes a wrong position |
| **jamming** | drowning the GPS signals in noise: the receiver has no fix |
| **kinematic gate** | refuse a fix the vehicle could not have reached (max speed × time + margin) |
| **trusted fix** | the last GPS fix the arbiter accepted |
| **independent source** | a position measured without GPS (vision, stars) |
| **cross-check** | comparing GPS with the independent source at every fix |
| **in doubt** | GPS still used but flagged, with an accuracy no better than the disagreement |
| **re-acceptance** | a refused GPS coming back after 2 agreeing vision fixes |
| **patient spoofer** | an attacker who waits until the gate's circle is big enough |

## Check what you learned

<details><summary>1. Top speed 30 m/s, margin 50 m. Last trusted fix 3 s ago. Is a fix 150 m away accepted?</summary>
No: reachable = 30 × 3 + 50 = 140 m, and 150 m is more than that, so it is <b>refused</b> ("implausible jump"). Always compute — intuition is not enough.
</details>

<details><summary>2. Why can't the kinematic gate catch a GPS pulled away at 4 m/s by a drone flying 15 m/s?</summary>
Every new fix is only a few metres from the previous one, well within max speed × time + margin. No jump, nothing to catch. Only an independent source can see the slow drift.
</details>

<details><summary>3. Why does one disagreeing vision fix never refuse GPS?</summary>
Because vision makes mistakes too (a wrong map match). Refusing a good GPS on one wrong fix would be worse than the attack. Several distinct fixes must disagree.
</details>

<details><summary>4. GPS was jammed for 60 s, then comes back 1 km away. The top speed is 100 m/s. Day vision (stated σ 15 m) sees the true position. What does NAVERA do?</summary>
After an outage, GPS must agree with the independent source before it is used again. Vision disagrees by 1 km (far beyond 3σ = 45 m): GPS is refused ("possible spoofing"), even though 1 km was "reachable" in 60 s.
</details>

<details><summary>5. Over the open sea, vision has no landmark. What protects NAVERA against spoofing there?</summary>
Only the kinematic gate: a sudden jump is caught, a patient or slow spoofer is not. That is a documented limitation.
</details>

Now open the **🛠️ Lab** tab.
