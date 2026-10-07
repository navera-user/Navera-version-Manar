# Which way am I facing? The IMU

A drone flies at 150 m over the countryside near Sousse. Its GPS has just been jammed. The
camera under the drone takes a photo, and NAVERA wants to find that photo on its satellite map.
But before it can even start, it needs three answers:

1. **Which way does the top of the photo point?** North? South-west? A map is drawn north-up;
   if the photo is turned 120°, nothing will line up.
2. **Was the camera looking straight down?** A drone that flies forward leans its nose down.
   The photo then shows the ground a little *ahead* of the drone, not under it.
3. **And at which exact instant?** The drone moves and turns all the time.

The sensor that answers the first two questions is the **IMU**. In this lesson you will learn what
it measures, how engineers write "which way am I facing" with numbers, why one of its sensors
slowly lies, and how NAVERA uses it to straighten every photo.

## What is an IMU?

**IMU** means *Inertial Measurement Unit*. It is a small chip — the one on the NAVERA box is a
**BNO085**, about the size of a fingernail. "Inertial" means it measures motion **from the inside**,
without looking at anything outside: no satellites, no camera. Your body has one too: the
**inner ear**. Close your eyes on a turning chair and you still feel that you are turning.

Inside the chip there are three sensors, each measuring along three axes (x, y, z):

| Sensor | What it measures | Good at | Bad at |
|---|---|---|---|
| **accelerometer** | acceleration (m/s²) — and gravity, always | finding "down", so the tilt | shakes with every vibration |
| **gyroscope** ("gyro") | rotation speed (degrees or radians per second) | fast, smooth turns | slowly **drifts** (see below) |
| **magnetometer** | the Earth's magnetic field | finding **north**, like a compass | disturbed by motors, cables, metal |

**The accelerometer** feels gravity even when nothing moves. A phone lying flat on a table measures
9.81 m/s² pointing up from the table: that is how your phone knows which way to turn the screen.
If the drone tilts, gravity "slides" to another axis, and the tilt can be computed.

**The gyroscope** measures how fast the drone turns, for example "15 degrees per second to the
right". It does *not* say where the drone points — only how fast it is turning.

**The magnetometer** is a tiny compass. It points to **magnetic** north (we will see that this is not
exactly the north of maps).

No sensor is perfect alone, so the chip **combines** them: this is called **sensor fusion**. The
gyroscope gives smooth, fast changes; the accelerometer and the magnetometer gently pull the result
back towards "down" and "north" so that it never wanders away. The BNO085 does this fusion **on the
chip itself** and directly gives the drone's **attitude**.

> [!NOTE]
> **Attitude** (in navigation) = the orientation of the vehicle: how it is tilted and which way it
> faces. It has nothing to do with being polite!

On the NAVERA box the BNO085 is wired to the Jetson's **I²C** bus number 1 (a two-wire bus for small
chips), at address `0x4A`, and NAVERA reads it **50 times per second**. The same bus also carries the
clock chip (DS3231, address `0x68`). On the box used for this course **the IMU is not connected at the
moment**, so in the lab you will work with a recorded (simulated) log — exactly the numbers the
real sensor would give.

## Roll, pitch and yaw

To describe an attitude, we use three angles, borrowed from aviation:

![Roll, pitch and yaw](assets/rpy.svg)

- **Roll**: rotation around the line nose → tail. One wing (or arm) goes down. A drone rolls to fly
  sideways.
- **Pitch**: rotation around the line left wing → right wing. The nose goes up or down. A multirotor
  pitches its nose down a few degrees to fly forward.
- **Yaw**: rotation around the vertical line. The nose points somewhere else, like turning your
  head to say "no".

To be precise, ROS (and NAVERA) fix the axes once and for all:

| Frame | x | y | z |
|---|---|---|---|
| **body** (the vehicle) | forward | left | up |
| **world** (ENU) | east | north | up |

Angles turn the "right-hand" way: put your right thumb along an axis, your fingers curl in the
positive direction. With z pointing up, a positive yaw turns **counter-clockwise** (to the left) seen
from above. With y pointing *left*, a positive pitch puts the nose **down**, and a positive roll
puts the **right** side down.

### Yaw is not heading

Here is a trap that has fooled many engineers. In ROS the yaw is a maths angle: **0° = east**,
counting **counter-clockwise**. But pilots, sailors and phones use the **heading**: **0° = north**,
counting **clockwise** (90° = east). The conversion is short:

```
heading = (90 − yaw) mod 360
```

| The nose points | yaw (ROS) | heading (compass) |
|---|---|---|
| east | 0° | 90° |
| north | 90° | 0° |
| west | 180° | 270° |
| south | −90° | 180° |

"mod 360" means "add or remove 360 until the result is between 0 and 360" — in Python, `% 360`.

### Degrees and radians

Python's `math.sin`, `math.cos`, `math.atan2` use **radians**, not degrees. A full turn is 360° or
2π ≈ 6.283 radians, so 1 rad ≈ 57.3°. `math.radians(90)` gives 1.5708 and `math.degrees(1.5708)`
gives 90. ROS messages always use radians (and rad/s for the gyroscope). If you ever see a "yaw of
1.57", it is 90° in disguise.

## Quaternions: a safe way to store a rotation

Three angles are easy for humans, but computers have trouble with them:

- **The order matters.** "Turn 90° right, then lean 30°" is not the same attitude as "lean 30°, then
  turn 90° right". Try it with a book.
- **Gimbal lock.** When the nose points straight up (pitch 90°), roll and yaw become the same
  movement, and one angle is lost. The formulas divide by zero.
- **Jumps.** A heading going from 359° to 1° is a small turn of 2°, but the numbers jump by 358.

So the IMU, ROS and NAVERA store an attitude as a **quaternion**: four numbers **(x, y, z, w)**.
You do not need to understand the mathematics behind them — think of a quaternion as **a safe box for
a rotation**. One rule is enough to read them: a rotation by an angle θ around an axis
(aₓ, a_y, a_z) is stored as

```
x = aₓ·sin(θ/2)    y = a_y·sin(θ/2)    z = a_z·sin(θ/2)    w = cos(θ/2)
```

| Attitude | quaternion (x, y, z, w) |
|---|---|
| no rotation at all | (0, 0, 0, 1) |
| yaw 90° (nose from east to north) | (0, 0, 0.7071, 0.7071) |
| yaw 180° | (0, 0, 1, 0) |
| roll 90° | (0.7071, 0, 0, 0.7071) |

The four numbers always have a "length" of 1: x² + y² + z² + w² = 1. NAVERA's live camera even
uses that rule to reject broken messages.

To show an attitude to a human, we convert the quaternion back into roll, pitch and yaw with these
three formulas (you will type them in the lab — you don't need to know where they come from):

```
roll  = atan2( 2(w·x + y·z), 1 − 2(x² + y²) )
pitch = asin ( 2(w·y − z·x) )
yaw   = atan2( 2(w·z + x·y), 1 − 2(y² + z²) )
```

**atan2(a, b)** is the angle of the point (b, a): it is like `atan(a/b)` but it knows in which
quarter of the circle the point is, and never divides by zero. Try the yaw formula on the second
row of the table: w = z = 0.7071, x = y = 0 → atan2(2 × 0.5, 1 − 2 × 0.5) = atan2(1, 0) = 90°. ✔

## Gyroscope drift: counting turns blindfolded

The gyroscope only gives a **speed** of rotation. To know the angle, you must add up all the small
turns: speed × time, again and again, 50 times per second. This adding up is called
**integration**. It is exactly like walking blindfolded and counting your steps: "10 steps
forward, turn a quarter right, 5 steps…"

The problem: a real gyroscope is never perfect. Even perfectly still, it says something like "0.03 °/s"
instead of 0. This small constant error is called the **bias**. It looks tiny, but integration adds it
up every second, forever:

| Time | error from a 0.03 °/s bias |
|---|---|
| 1 second | 0.03° |
| 1 minute | 1.8° |
| 5 minutes | 9° |
| 1 hour | 108° |

After an hour the drone would believe it flies east while it flies north! This slow walk away from
the truth is called **drift**. In the lab you will integrate a 5-minute gyroscope log and see it
with your own eyes.

![Drift of the gyroscope vs fused attitude](assets/drift.svg)

That is why the BNO085 fuses the gyroscope with the magnetometer and the accelerometer: they don't
drift, so they keep pulling the answer back to the truth. The result is smooth like a gyroscope and
honest in the long run like a compass.

## True north and magnetic north

A compass does not point to the **geographic** North Pole (the end of the Earth's axis, the north of
every map), but to the **magnetic** north pole, which is in the Arctic, far from the real pole, and
moves by tens of kilometres every year. The angle between the two directions, at your place, is the
**magnetic declination**.

![True north vs magnetic north](assets/north.svg)

- Declination is counted **positive to the east**: around Sousse in 2026 it is about **+3.3°** (the
  compass points 3.3° to the east of true north).
- To get the **true heading**: `true heading = magnetic heading + declination`.
- It changes with the place (−11° in Iceland, +13° in Sydney) and slowly with the years.

Scientists publish a model of the Earth's magnetic field every five years: the **World Magnetic Model**
(**WMM**). The 2025 edition is valid from 2025 to 2030. With the latitude, the longitude and the date,
it gives the declination anywhere. In Python, the small library **pygeomag** computes it.

Does 3.3° matter? After 1 km of flight, a heading wrong by 3.3° puts you about 58 m to the side
(1000 × tan 3.3°). For a navigation system that wants an accuracy of tens of metres, yes, it matters.

## How NAVERA uses the attitude: straightening the photo

Back to our drone over Sousse. The camera is fixed under it, looking down. When the drone flies
forward, its nose is pitched down, so the camera looks a bit backwards; when it rolls in a turn, the
camera looks to the side.

![A tilted camera does not look under the drone](assets/tilt.svg)

The centre of the photo is then **not** the point under the drone. The distance is
height × tan(tilt): at 150 m with a 10° tilt, it is **26 m** — and NAVERA would place the drone 26 m
off before even starting. So, for every photo, NAVERA:

1. takes the attitude **at the instant the photo was exposed** (the IMU history is stored and
   interpolated — lesson 19 explains why this instant is not the instant the photo arrives);
2. computes the camera's direction from the drone's attitude and the way the camera is mounted;
3. **straightens** the photo: it rewarps it into the picture a level camera, looking straight
   down, would have taken from the same place. (The mathematical tool is a *homography*; the code
   does it in one line with OpenCV.)
4. writes in the photo's description (`frame_meta`) the roll, the pitch, the **tilt** and the
   **heading of the top of the image**, so day vision can turn the photo north-up before comparing it
   with the map.

If the tilt is too large (more than **45°**), the photo is marked *unusable*: too little ground, seen
too obliquely. If there is **no attitude** at the instant of the photo (IMU silent), the photo is
marked unusable too: guessing "straight down" could silently put the position tens of metres off.
Honest "I don't know" is better than a confident wrong answer.

## In NAVERA

**The driver** — [imu_pkg/imu_pkg/nodes/imu_node.py](file:navera/imu_pkg/imu_pkg/nodes/imu_node.py)
reads the BNO085 (bus 1, address `0x4A`, 50 Hz) and publishes a `sensor_msgs/Imu` on
`/navera/sensors/imu`: the orientation quaternion, the angular velocity (rad/s) and the acceleration.
Its settings are in [imu_params.yaml](file:navera/imu_pkg/imu_pkg/config/imu_params.yaml). Note the
honesty in the comments: the uncertainties (`orientation_stddev: 0.02` rad…) are *datasheet-derived
estimates, NOT measured on NAVERA hardware*.

**Yaw → heading** — [imu_pkg/imu_pkg/orientation.py](file:navera/imu_pkg/imu_pkg/orientation.py):

```python
def heading_deg(q: Sequence[float]) -> float:
    """Heading (deg clockwise from the frame's north) of the body x axis, ENU frame."""
    x, y, z, w = q
    yaw_enu = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return (90.0 - math.degrees(yaw_enu)) % 360.0
```

The yaw formula and the `90 − yaw` you just learned, in four lines.

**True north** — in the same file, the class `Declination` asks the World Magnetic Model (pygeomag)
for the declination at the vehicle's position, and recomputes it only when the vehicle has moved more
than 20 km. `OrientationCorrector.apply()` then turns the whole quaternion by the declination, so every
part of NAVERA receives a heading from **true** north. Until a position is known, `imu_node` uses the
`declination_deg` parameter (the YAML file mentions +3.3 around Sousse in 2026), or says clearly in its
log that the heading is still *MAGNETIC*.

**The camera** — [navera_common/navera_common/camera_model.py](file:navera/navera_common/navera_common/camera_model.py)
has `body_rpy_enu(q)`, which gives roll, pitch and heading for humans (with the pitch counted
**positive nose up**, the opposite sign of ROS — always read the comments!), and `tilt_deg()`.
[navera_common/navera_common/frame_builder.py](file:navera/navera_common/navera_common/frame_builder.py)
does the straightening:

```python
            if tilt > self.max_tilt_deg:
                meta.update(usable=False, reason=f"camera tilted {tilt:.0f} deg from vertical "
                                                 f"(max {self.max_tilt_deg:.0f}): not compared with the map")
                return out, meta
            if tilt > 0.05:
                H = nadir_homography(self.cam.K_out, R)
                h, w = out.shape[:2]
                out = cv2.warpPerspective(out, H, (w, h), flags=cv2.INTER_LINEAR,
                                          borderMode=cv2.BORDER_CONSTANT)
            meta["straightened"] = True
```

## Words you met

| Word | Meaning |
|---|---|
| **IMU** | Inertial Measurement Unit: accelerometer + gyroscope + magnetometer on one chip |
| **accelerometer** | measures acceleration, including gravity → tells where "down" is |
| **gyroscope** | measures rotation speed (rad/s) |
| **magnetometer** | measures the magnetic field → a compass |
| **sensor fusion** | combining several sensors so each one covers the others' weaknesses |
| **attitude** | the orientation of a vehicle: roll, pitch, yaw |
| **roll / pitch / yaw** | rotation around the forward / sideways / vertical axis |
| **heading** | the direction of the nose, clockwise from north (a compass angle) |
| **quaternion** | four numbers (x, y, z, w) that store a rotation safely |
| **radian** | the maths unit of angles: 180° = π rad |
| **integration** | adding up many small steps (speed × time) to get a total |
| **bias / drift** | a small constant sensor error / the growing error it causes once integrated |
| **declination** | the angle between magnetic north and true north (east positive) |
| **WMM** | World Magnetic Model: gives the declination anywhere, valid 2025–2030 |
| **straightening** | turning a tilted photo into the view of a level camera looking straight down |

## Check what you learned

<details><summary>1. A drone is perfectly still on a table. What does each IMU sensor measure?</summary>
The accelerometer measures gravity (9.81 m/s² towards "up" from the table), the gyroscope measures
(almost) zero rotation — only its small bias — and the magnetometer measures the Earth's magnetic
field, pointing towards magnetic north.
</details>

<details><summary>2. The ROS yaw is −90°. Where does the nose point, and what is the heading?</summary>
Yaw 0 is east and positive is counter-clockwise, so −90° is a quarter turn clockwise from east: south.
Heading = (90 − (−90)) mod 360 = 180°.
</details>

<details><summary>3. Why not just integrate the gyroscope to know the heading?</summary>
Because its small bias is added up at every step: the error grows without limit (drift). 0.03 °/s
becomes 9° after 5 minutes and 108° after one hour. The magnetometer must keep correcting it.
</details>

<details><summary>4. The compass says 100°, the declination is +3.3°. What is the true heading?</summary>
100 + 3.3 = 103.3°.
</details>

<details><summary>5. Why does NAVERA mark a photo "unusable" when there is no attitude at its instant?</summary>
Without the attitude, the camera's tilt is unknown. Assuming "straight down" could put the position
tens of metres off (26 m at 150 m height for a 10° tilt) without anyone knowing. NAVERA prefers to
say "I don't know".
</details>

Now open the **🛠️ Lab** tab.
