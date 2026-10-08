# Welcome: navigation without GNSS

> [!NOTE] In short
> - GPS can be lost (jamming, blockage) or faked (spoofing), and the autopilot cannot see the
>   difference.
> - A receiver needs at least four satellites, because its own clock error is a fourth unknown.
> - The GPS signal arrives weaker than the noise, so a small jammer can deny GPS over many
>   kilometres.
> - NAVERA has three layers: **sources** (GPS, day vision, night vision, celestial), an
>   **arbiter** that chooses one, and an **output** that looks like a GPS to the autopilot.
> - In the lab you run your first commands on the Jetson, run a GNSS solver, break it on purpose,
>   and apply the arbiter's jump gate.

A survey drone flies along a coastline, from one harbour town to the next. Its autopilot holds
the route with a position from **GPS**, updated five times per second. Suddenly the receiver reports
"no fix" — or worse, it keeps reporting a position that is calm, precise… and 2 km out at sea,
while the drone is still over the beach. The autopilot cannot see the difference. It will either
land where it is, fly a "return home" towards a wrong home, or follow the fake position.

This course is about the engineering answer to that situation: **GNSS-denied navigation**. You will
study, modify and test **NAVERA**, a commercial navigation product made by IRIS Systems. NAVERA
sits beside the autopilot of a vehicle (drone, aircraft, ground robot, boat) and keeps giving it a
position when satellite navigation is lost or cannot be trusted — from a camera and a satellite map,
a thermal camera, the stars, and a strict set of rules about whom to believe.

In this first lesson you learn how satellite positioning works and why it fails, what NAVERA is made
of, and how this dashboard works.

## 1. How GNSS works: pseudoranges

**GNSS** (Global Navigation Satellite System) is the general name; **GPS** (USA) is one system,
next to Galileo (Europe), GLONASS (Russia) and BeiDou (China). A GPS satellite orbits at about
20 200 km altitude (orbit radius 26 560 km) and continuously broadcasts:

- *when* it sent the signal, from its atomic clock;
- *where* it is, from its orbit parameters (the **ephemeris**).

The receiver notes *when* the signal arrived and multiplies the travel time by the speed of light
`c ≈ 299 792 458 m/s`. The travel time is about 67–86 ms. The problem: the receiver has a cheap
quartz clock, not an atomic one. If its clock is wrong by a **bias** `b`, every measured distance
is wrong by the same amount `c·b` — and 1 µs of clock error is already 300 m. The measured
distance is therefore called a **pseudorange**:

```
ρ_i = ‖s_i − r‖ + c·b + ε_i

  ρ_i   pseudorange to satellite i (measured, m)
  s_i   position of satellite i (known from its message)
  r     receiver position (x, y, z)        ← unknown
  b     receiver clock bias (s)            ← unknown
  ε_i   noise: atmosphere, multipath, receiver (a few metres)
```

There are **four unknowns**: `x, y, z` and `b`. Each satellite gives one equation, so a 3-D fix needs
**at least four satellites**. With more than four, the receiver solves a **least-squares** problem (it
chooses the position that makes the sum of the squared errors of all equations as small as possible):
the extra equations average the noise and make it possible to detect a measurement that disagrees.

![Four satellites, four pseudoranges: three unknown coordinates plus the clock bias](assets/gps.svg)

### A worked example in 2-D

Take a flat world with three beacons (in km): `A = (0, 0)`, `B = (10, 0)`, `C = (0, 10)`. The receiver is
really at `(3, 4)`, and its clock is 1 µs late, so every pseudorange is 0.3 km too long:

| Beacon | True distance | Pseudorange (+0.3 km) |
|---|---|---|
| A | √(3² + 4²) = 5.000 | 5.300 |
| B | √(7² + 4²) = 8.062 | 8.362 |
| C | √(3² + 6²) = 6.708 | 7.008 |

Draw three circles with the pseudoranges as radii: they do **not** meet in one point. In 2-D the
unknowns are `x, y, b`: three unknowns, three equations. Find the `b` that makes the circles
**shrink** (radius `ρ_i − c·b`) until they meet in a single point: with `c·b = 0.3 km` they meet at
`(3, 4)`. (You do not have to solve this by hand; the lab's solver does it.) In 3-D the same idea needs four satellites. A real receiver does it numerically: it
**linearises** the equations around a guess and improves the guess a few times (Gauss–Newton). In
the lab you run such a solver and watch the clock bias come out of it.

### Geometry matters: DOP

The noise `ε` of a few metres becomes a position error multiplied by a **dilution of precision**
(DOP) that depends only on the geometry: satellites spread over the whole sky give a small DOP
(1–2); satellites bunched in one direction, or only four of them, give a larger one. That is why the
same receiver is precise in an open field and poor in a narrow old-town street between tall houses
and hills.

## 2. Why GNSS is fragile

A GPS satellite transmits about 25–50 W from 20 000 km away. On the ground the L1 signal
(1575.42 MHz) arrives with a power of about **−128.5 dBm**, i.e. about `1.4 × 10⁻¹⁶ W`. The
thermal noise of the receiver over the signal's 2 MHz bandwidth is about **−111 dBm**: the signal
is roughly **50 times weaker than the noise** (−17 dB). The receiver can still use it because it
knows the satellite's spreading code and **correlates** for a millisecond or more, which gains about
30 dB. (Why 30 dB? The GPS code has 1023 **chips** (code bits) per millisecond. Correlating adds
about 1000 chips together: the signal parts add in step, the random noise does not, so the
signal-to-noise ratio improves about 1000 times: `10·log10(1000) = 30 dB`.) But any transmitter on the same frequency competes with a signal
that is already below the noise.

> [!NOTE]
> **Decibels.** Engineers compare powers on a log scale: `P_dBm = 10·log10(P / 1 mW)`. +10 dB = ×10,
> +3 dB ≈ ×2, −20 dB = ÷100. A difference of 36 dB is a factor of about 4000.

**Worked example — how far can a jammer reach?** In free space, a radio signal loses
`FSPL(dB) = 20·log10(d_km) + 20·log10(f_MHz) + 32.44`. A small 1 W jammer (30 dBm) at 20 km:

```
FSPL = 20·log10(20) + 20·log10(1575.42) + 32.44 = 26.0 + 63.9 + 32.4 = 122.4 dB
received jamming power = 30 − 122.4 = −92.4 dBm
J/S = −92.4 − (−128.5) = 36 dB   → about 4000 times stronger than the satellite
```

Civil receivers usually lose tracking when the jamming is a few tens of dB above the signal
(the exact limit depends on the receiver and antenna). With a clear line of sight — which a drone
at altitude has — a one-watt device can therefore deny GPS over many kilometres.

### The threat model

| Threat | What happens | What the receiver knows | Example situations |
|---|---|---|---|
| **Outage / blockage** | the signal is blocked or reflected (**multipath**) | it sees fewer satellites, larger DOP, or no fix | streets between tall buildings, deep valleys, under bridges, tunnels, inside a hangar |
| **Interference / jamming** | noise is transmitted on the GNSS frequency, deliberately or not | it **knows** it lost the fix | a jammer in a vehicle, a faulty transmitter, a military exercise |
| **Spoofing** | fake but consistent GNSS signals are transmitted, for a chosen false position or time | it usually **does not know**: the fix looks normal | the receiver's position slowly drifts away, or jumps |
| **Meaconing** | real signals are recorded and **re-broadcast** with a delay | it does not know; it computes the position of the re-broadcaster, and a wrong time | a simple "repeater" attack |

Interference is not a theory. Navigation authorities for shipping and aviation have for years
published warnings about GNSS interference in several regions of the world — around the Baltic Sea,
the Black Sea, the Eastern Mediterranean and the Middle East, among others. Typical reports
describe ships whose broadcast position appears on land, or aircraft that lose GPS for part of a
flight. Any vehicle that must keep working in such conditions needs a second way to know where it is.

Spoofing is the most dangerous case for an autopilot, because the error is **silent**: with only
GNSS, the receiver has nothing independent to compare with. The defence is to compare GNSS with
something that does not use radio signals: the camera, the stars, the vehicle's own motion.

## Where the idea came from: birds

Twice a year, billions of birds travel between their breeding grounds and their winter quarters.
White storks cross from Europe to Africa over the Strait of Gibraltar; bar-tailed godwits fly
non-stop from Alaska to New Zealand; Arctic terns go from the Arctic to the Antarctic and back.
Barn swallows, wheatears, warblers and birds of prey cross the Mediterranean and the Sahara in
spring and in autumn, many of them flying at night. A barn swallow that breeds in Europe
or Central Asia winters in Africa and often comes back to the same building, sometimes to the same
nest, after a journey of thousands of kilometres over sea and desert — with no GPS.

Scientists have studied how they do it for more than a century, and the answer is the founding idea
of NAVERA: a bird does not have **one** perfect sense. It has **several**, each imperfect, and it
**cross-checks** them.

Meet **Navi**, a barn swallow. She will appear in each lesson, briefly, to show how birds solve the
problem the lesson is about.

![Navi's senses, and the NAVERA source each one inspired](assets/bird_senses.svg)

| What the bird uses | What it gives | NAVERA's version |
|---|---|---|
| **Eyes + landmarks** (coasts, mountains, rivers, roads) | "I know this place" | **day vision**: camera + satellite map |
| **The stars** (night migrants learn the sky's centre of rotation) | a direction at night | **celestial**: a star camera |
| **The sun + an inner clock** | a direction by day; needs the time | an accurate **clock** (GNSS and stars both need it) |
| **A magnetic sense** | a compass, even under clouds | the **magnetometer** of the IMU |
| **The inner ear** | which way is up, how fast it turns | the **IMU** (gyroscopes, accelerometers) |
| **A sense of its own motion** | "so far, in that direction" | **dead reckoning**, visual odometry |
| **Cross-checking** | which sense to trust when they disagree | the **arbiter** |

## 3. NAVERA: sources, arbiter, output

NAVERA is a set of programs (ROS 2 **nodes**, lesson 9) running on an NVIDIA Jetson computer. It has
three layers.

![NAVERA's architecture: sources, arbiter, output to the autopilot](assets/architecture.svg)

**1. Sources** — each one produces its own position estimate, with its own uncertainty:

| Source | Package in your copy | How it finds the position | Lessons |
|---|---|---|---|
| GPS | `gps_pkg` | reads the receiver (NMEA sentences) | 15 |
| Day vision | `day_pkg` | matches the camera image against a stored satellite map | 17–23 |
| Night vision | `night_pkg` | matches a thermal image against the map | 24 |
| Celestial | `cn_pkg` | recognises stars in a sky image, with the exact time | 24 |
| IMU | `imu_pkg` | attitude and heading (it does **not** give a position) | 16 |

**2. The arbiter** (`navera_estimator`, node `estimator_node`) decides, five times per second,
which source to publish. Its rule is simple and strict:

- a source is **eligible** only if its estimate is valid, fresh (for GPS: younger than
  `gps_timeout_s = 3.0` s), a real measurement, and has finite numbers;
- among the eligible ones, the first in the priority order **GPS > day vision > night vision >
  celestial** wins;
- a GPS fix that **jumps** farther than the vehicle could have moved is refused:

```
refuse GPS if   distance(new fix, last trusted fix) > v_max · Δt + margin
```

With `v_max = 100 m/s` (a parameter set per vehicle), `margin = 50 m` and fixes 1 s apart, a jump of
more than 150 m is refused. While GPS is refused, it is only accepted again when it **agrees** with
an independent source such as vision. Lessons 25–27 study these rules in detail.

**3. The output** (`navera_output`, node `vehicle_output_node`) gives the decision to the
autopilot **in the form of a GPS**: NMEA sentences on a serial port, or the MAVLink message
`GPS_INPUT` (ArduPilot, PX4), or a ROS topic. The autopilot does not need to change: NAVERA looks
like a GPS receiver that does not fail silently.

Every position NAVERA publishes carries its **source**, whether it was **measured** or
**dead-reckoned**, and its **uncertainty**. The arbiter summarises the situation as a state:

| State | Meaning |
|---|---|
| **FIX** | fresh measured position with a stated uncertainty of at most 25 m — today only GPS |
| **DEGRADED** | a position exists but its uncertainty is unknown, above 25 m, or it is dead-reckoned (all vision and celestial positions today) |
| **NO_FIX** | no usable source; no old position is re-sent as current |

> [!WARNING]
> NAVERA is **Release 0.2 — field validation pending**. Its documentation
> (`docs/VALIDATION_STATUS.md` in your copy) lists what has been measured and how. For example,
> day vision with local feature matching placed 32 of 33 aerial test frames within 9 m (median 4 m)
> **on the bench**, with frames that were not taken by NAVERA's own camera; celestial navigation
> gives 5.5–6.5 km with a perfect attitude in **simulation**. Engineers quote such numbers with
> their conditions, never alone. You will do the same in this course.

NAVERA's test map and recorded data cover the region of **Sousse, Tunisia**, where NAVERA is
developed. Other examples of this course use well-known places around the world; the real data stays
where it was recorded.

## 🐦 How birds do it

Navi has to admit that none of her senses is perfect. Clouds hide the sun and the stars; fog hides
the coast; and the magnetic sense can be disturbed. Homing pigeons released at **magnetic
anomalies** (places where the rocks distort the Earth's field) often fly off in wrong directions at
first.

So birds cross-check, and the clearest experiment is about **calibration**. In 2004 William Cochran
and colleagues (journal *Science*) followed migrating thrushes in North America through the night
with small radio transmitters, driving behind them with an antenna on the car's roof. At sunset,
just before departure, they placed some birds in an artificial magnetic field turned away from the
real one. That night, those birds flew in the wrong direction; the next night, in the normal field,
they flew the right way again. The thrushes **re-calibrate their magnetic compass every evening
from the sunset sky** — one sense calibrates another, and an error injected at the moment of
calibration goes straight into the flight.

That is the arbiter's job: never trust one source blindly, compare it with an independent one, and
notice when one starts telling a different story — a GPS that puts the drone 2 km out at sea while
the camera sees the roofs of the harbour town. It is also the arbiter's main risk: if a spoofer
manages to "calibrate" NAVERA with a false position, the error propagates. Lesson 27 returns to this.

## 4. Your workspace

The dashboard has two sides:

- **Left — the notebook.** The **Course** tab (this text), the **Lab** tab (step-by-step work), and
  **✔ Check my work**, which runs automatic tests on your files and shows a hint for each problem.
- **Right — your tools.** **📝 Code** (an editor: files on the left, `Ctrl+S` to save; it also
  shows images), **⌨️ Terminal** (a Linux shell on the Jetson — lesson 2), **🛩️ Simulator** (a
  flight simulator with NAVERA in the loop — lesson 28) and **🧭 Operator view** (the screen a
  NAVERA operator watches).

Your home folder contains:

| Folder | What it is |
|---|---|
| `~/navera/` | **your own copy of NAVERA**, already built. You may change anything: the 👤 menu's **Reset my NAVERA copy** gives you a fresh copy (your work is saved in a backup first — lesson 5 explains how). |
| `~/lessons/<lesson>/` | the files of each lab. **↺ Reset lab files** puts the current lesson's files back. |

> [!TIP]
> Code blocks with a **▶ Run** button type the command into your terminal. Links like
> [this one](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml) open a file
> of your NAVERA copy in the editor.

## Glossary

| Term | Meaning |
|---|---|
| **GNSS / GPS** | satellite navigation in general / the US system |
| **pseudorange** | distance measured with the receiver's clock: true range + clock bias × c + noise |
| **clock bias** | the receiver clock's error; one more unknown in the position solution |
| **least squares** | the solution that best fits more equations than unknowns |
| **DOP** | dilution of precision: how the satellite geometry multiplies the measurement noise |
| **dBm** | power in decibels relative to 1 mW |
| **multipath** | a signal that reaches the antenna after a reflection, so it travels a longer path |
| **jamming / spoofing / meaconing** | noise on the frequency / fake signals / re-broadcast real signals |
| **source** | a component that produces a position estimate (GPS, day vision…) |
| **arbiter** | NAVERA's `estimator_node`: decides which source to publish |
| **dead reckoning** | carrying a known position forward with a measured speed and heading |
| **autopilot** | the flight controller (ArduPilot, PX4); NAVERA gives it a position as a GPS would |
| **FIX / DEGRADED / NO_FIX** | NAVERA's states: bounded measured fix / reduced trust / nothing usable |

## Check what you learned

<details><summary>1. Why are four satellites the minimum for a 3-D fix, and what do the extra satellites bring?</summary>
The unknowns are x, y, z and the receiver clock bias b: four unknowns need four equations. Extra satellites
reduce the effect of noise (least squares, smaller DOP) and, above all, give <b>redundancy</b>: with exactly four
the equations always fit perfectly (residual 0), so a wrong measurement cannot be detected.
</details>

<details><summary>2. The receiver clock is 2 µs fast. What does that do to every pseudorange?</summary>
It changes all of them by the same amount, c × 2 µs ≈ 600 m. Because it is the same for all satellites, the
solver can estimate it as the fourth unknown — that is the point of the clock-bias term.
</details>

<details><summary>3. A 1 W jammer is 40 km away instead of 20 km. By how many dB does its effect drop?</summary>
FSPL grows by 20·log10(2) ≈ 6 dB: J/S drops from about 36 dB to about 30 dB — still enough to disturb many
receivers. Doubling the distance only divides the power by 4.
</details>

<details><summary>4. Why is spoofing more dangerous than jamming for an autopilot?</summary>
Jamming is detected: the receiver says "no fix" and the autopilot can react. A good spoof produces a normal-looking
fix with small residuals; the autopilot follows a false position without any alarm. Only an independent source can
reveal it.
</details>

<details><summary>5. NAVERA's day vision has a fresh fix and GPS is jammed. What state does the arbiter report, and why not FIX?</summary>
DEGRADED: today vision positions do not have a validated stated uncertainty of at most 25 m, so the contract
reports them as reduced trust. FIX is reserved for a measured position whose error is bounded (today only GPS).
</details>

<details><summary>6. Fixes arrive every 1 s, <code>v_max = 100 m/s</code>, margin 50 m. The GPS jumps 120 m. Refused?</summary>
No: 120 m &lt; 100 × 1 + 50 = 150 m. A small jump passes this gate — which is why a slow, gradual spoof needs the
cross-check with an independent source (lesson 27).
</details>

Now open the **🛠️ Lab** tab.
