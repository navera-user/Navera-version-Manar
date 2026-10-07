# Your first publisher: a fake GNSS receiver

Before a NAVERA box flies, it spends many hours on a **test bench**: a table, a Jetson, cables —
and no aircraft. The arbiter still needs GNSS positions that *move*, as if the box were flying
along the Batinah coast. So the engineers write a program that **pretends to be a GNSS receiver**:
it publishes the same message type, at the same rate, with the same honest uncertainty as a real
receiver. Because of publish/subscribe (lesson 09), the rest of the graph cannot tell the
difference.

Today you write such a node: a **fake GNSS receiver** that drives from near the Sultan Qaboos Grand
Mosque in Muscat (about 23.5880 N, 58.3829 E) with a speed and a heading you can change while it
runs. (NAVERA's own recorded data and map cover Sousse, Tunisia, where it is developed; this lab
uses synthetic data, so we can drive anywhere.) On the way you will learn how an `rclpy` node is
built, how timers and clocks behave, what every field of `sensor_msgs/NavSatFix` means — and how
large the error of a "flat Earth" is.

## 1. A node is an object

In lesson 03 you learned to write **classes**. An `rclpy` node is an object of a class that
**inherits** from `rclpy.node.Node`:

```python
import rclpy
from rclpy.node import Node


class FakeGps(Node):                       # a FakeGps IS a Node, plus what we add
    def __init__(self):
        super().__init__("fake_gps")       # run Node's own constructor: name in the graph
        self.count = 0                     # state, kept between two timer calls
        self.create_timer(0.5, self.on_timer)

    def on_timer(self):                    # a METHOD: called by ROS every 0.5 s
        self.count += 1
        self.get_logger().info(f"tick {self.count}")


def main():
    rclpy.init()                           # 1. start the ROS client library
    node = FakeGps()                       # 2. create the object (registers the node)
    rclpy.spin(node)                       # 3. wait for events and run callbacks, until Ctrl+C
    node.destroy_node()                    # 4. clean up
    rclpy.shutdown()
```

Read it with the vocabulary of lesson 03:

- `class FakeGps(Node)` — **inheritance**. `FakeGps` gets every method of `Node`:
  `create_publisher`, `create_timer`, `get_clock`, `get_logger`, `declare_parameter`… We only write
  what is specific to our node.
- `super().__init__("fake_gps")` — calls the constructor of the **parent** class. Without this line
  the object is not registered in ROS and every `create_…` call fails. The string is the node name
  that `ros2 node list` shows.
- `self` — the object itself. `self.count = 0` stores an **attribute** in the object; it survives
  between two calls of `on_timer`. A plain variable `count = 0` inside a method would be **local**:
  forgotten when the method returns.
- `self.on_timer` without parentheses — a **bound method** given to ROS as a **callback**: ROS
  will call it later. `self.on_timer()` with parentheses would call it *now*, once, and give ROS
  its result (`None`) — a classic bug.

`rclpy.spin(node)` turns your program into an **event-driven** one: it does not run from top to
bottom and stop; it waits, and when a timer expires or a message arrives, it calls the right
callback. All callbacks of a node run one after the other in this loop (lesson 11 shows how to
change that), so a callback must be short.

## 2. Publishers and timers

```python
self.pub = self.create_publisher(NavSatFix, "/fake_gps/fix", 10)
self.timer = self.create_timer(1.0 / rate_hz, self.on_timer)
...
self.pub.publish(msg)
```

`create_publisher(type, topic, qos)`: the third argument is a QoS profile; a plain `10` means the
default profile (RELIABLE, VOLATILE, KEEP_LAST) with depth 10, as you saw in lesson 09.
`create_timer(period_s, callback)`: the period is the inverse of the rate — at 2 Hz,
`1 / 2 = 0.5` s.

### Clocks and time stamps

A node reads time with `self.get_clock().now()`. This is **ROS time**: normally the system clock
(seconds since 1 January 1970, UTC), but when the parameter `use_sim_time` is true, it follows the
`/clock` topic of a simulator instead — so a replayed or simulated mission runs with the
simulator's time. A ROS `Time` converts to the message format with `.to_msg()`: two integers,
`sec` and `nanosec`.

```python
now = self.get_clock().now()               # rclpy.time.Time
msg.header.stamp = now.to_msg()            # builtin_interfaces/Time {sec, nanosec}
t_s = now.nanoseconds / 1e9                # a float, in seconds
```

The **stamp is part of the measurement**. An arbiter that receives a position must know *when* it
was true: at 20 m/s, a fix that is 2 s old is 40 m behind. NAVERA refuses any GPS estimate older
than 3 s (lesson 11).

### Timers are not perfect: integrate with the real dt

A timer of period T does not fire exactly every T seconds: the operating system schedules your
process with small delays (**jitter**), and a long callback can delay the next one. rclpy computes
each deadline from the previous *deadline*, so delays do not accumulate, but individual intervals
vary. `ros2 topic hz` measures it: `average rate`, `min`, `max` and `std dev` of the intervals.

For a moving vehicle this matters. If you advance the position by `v × T` at every tick, with
T = 0.5 s fixed, a tick that comes 60 ms late still adds only `v × 0.5`. Measure the real interval
instead:

```
dt_k = t_k − t_(k−1)          (from the node's clock)
north_k = north_(k−1) + v · cos(h) · dt_k
east_k  = east_(k−1)  + v · sin(h) · dt_k
```

where v is the speed and h the heading, measured **clockwise from north** (0° = north, 90° = east).
Then the position is right at the instant of each stamp, whatever the jitter.

## 3. Parameters: settings you can change from outside

A **parameter** is a named, typed setting stored in a node. You declare it with a default, then
read it:

```python
self.declare_parameter("speed_mps", 5.0)        # name, default (the TYPE comes from it: double)
v = self.get_parameter("speed_mps").value       # the value now in use
```

You can set it when you start the node, and change it while it runs:

```bash
python3 fake_gps.py --ros-args -p speed_mps:=12.0 -p heading_deg:=90.0
ros2 param set /fake_gps heading_deg 180.0
```

A node that reads the parameter **at every tick** follows a `ros2 param set` immediately; a node
that reads it once in `__init__` does not. Your fake GPS reads `speed_mps` and `heading_deg` at every
tick, so you can "drive" it from the terminal. Lesson 13 goes much further (YAML files, launch files,
validation).

> [!WARNING]
> **The type trap.** `-p speed_mps:=12` (no `.0`) is an **integer**, and the parameter was declared
> as a double: the node stops with `InvalidParameterTypeException … of type 'INTEGER', expecting
> type 'DOUBLE'`. Write decimals with a dot.

## 4. The message: sensor_msgs/NavSatFix

Every GNSS driver in the ROS world publishes **`sensor_msgs/msg/NavSatFix`**. Its fields:

| Field | Type | Meaning |
|---|---|---|
| `header.stamp` | Time | when the position was measured |
| `header.frame_id` | string | the antenna's frame, e.g. `"gps"` |
| `status.status` | int8 | `STATUS_NO_FIX` (−1), `STATUS_FIX` (0), `STATUS_SBAS_FIX` (1), `STATUS_GBAS_FIX` (2) |
| `status.service` | uint16 | bit mask: `SERVICE_GPS` (1), `GLONASS` (2), `COMPASS` (4, BeiDou), `GALILEO` (8) |
| `latitude`, `longitude` | float64 | degrees, WGS84 (lesson 06) |
| `altitude` | float64 | metres above the WGS84 **ellipsoid** (not above sea level) |
| `position_covariance` | float64[9] | uncertainty, m², ENU, row-major (below) |
| `position_covariance_type` | uint8 | `UNKNOWN` (0), `APPROXIMATED` (1), `DIAGONAL_KNOWN` (2), `KNOWN` (3) |

Recall from lesson 06: WGS84 models the Earth as an **ellipsoid** (a slightly flattened sphere); GPS
altitude is measured from that mathematical surface. In Muscat the sea surface (the geoid) is a few
tens of metres away from the ellipsoid, so "altitude 40 m" in NavSatFix is not "40 m above the sea".

A message is filled like any Python object; a nested message uses two dots:

```python
msg = NavSatFix()
msg.latitude = 23.5880
msg.status.status = NavSatStatus.STATUS_FIX
```

Every field starts at zero. If you forget latitude and longitude, they stay **0.0, 0.0** — a real
place in the Gulf of Guinea, nicknamed **Null Island** — and nothing warns you. This is why NAVERA's
GPS code refuses exactly (0, 0): in
[ros_gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/ros_gps_node.py) look for
`not (m.latitude == 0.0 and m.longitude == 0.0)`.

### Covariance: the uncertainty, in m²

A receiver says "I am here, give or take a few metres". If the error in the east direction, `e_E`, is
a random variable with mean 0 and **standard deviation** σ_E, its **variance** is σ_E² (unit m²).
For two directions, the **covariance** `cov(e_E, e_N) = E[e_E · e_N]` says whether the errors are
linked. The 3 × 3 **covariance matrix** of the (East, North, Up) error collects all of them:

```
      | σE²        cov(E,N)   cov(E,U) |
Σ  =  | cov(N,E)   σN²        cov(N,U) |      position_covariance = [Σ00, Σ01, Σ02,
      | cov(U,E)   cov(U,N)   σU²      |                             Σ10, Σ11, Σ12,
                                                                     Σ20, Σ21, Σ22]
```

The message stores it **row-major**: row 0, then row 1, then row 2, so the diagonal is at indices
0, 4 and 8. Worked example: a receiver with σ = 3 m horizontally and 6 m vertically (vertical GNSS
error is typically about twice the horizontal), errors assumed independent:

```
position_covariance = [9.0, 0.0, 0.0,
                       0.0, 9.0, 0.0,
                       0.0, 0.0, 36.0]
position_covariance_type = COVARIANCE_TYPE_DIAGONAL_KNOWN
```

"Diagonal known" says: the three variances are known, the off-diagonal terms are not (they are 0
here because we assume independence). If you do not know the accuracy at all, the honest choice is
`COVARIANCE_TYPE_UNKNOWN` and nine zeros — never an invented number. Lesson 12 explains why NAVERA is
so strict about this.

> [!WARNING]
> **ROS float fields refuse integers.** `[9, 0, 0, 0, 9, 0, 0, 0, 36]` crashes with
> `AssertionError: The 'position_covariance' field must be a set or sequence with length 9 and each
> value of type 'float' and each double in [-1797693…, 1797693…]` — followed by two 300-digit
> numbers (the smallest and largest float64). Read only the beginning: **"each value of type
> 'float'"**. Write `9.0` and `0.0`, or compute with floats: `SIGMA_M ** 2` is a float when
> `SIGMA_M = 3.0`.

## 5. From metres to degrees: the flat-Earth model and its error

Your node moves in metres (north, east) from a start point (φ0, λ0). To publish, it converts the
offset to latitude and longitude. Near the start, the Earth looks flat: one degree of latitude is
`2πR / 360` metres (R = 6 371 000 m, the radius NAVERA uses: 111 195 m), and a degree of
longitude is shorter by cos φ0. So:

```
φ = φ0 + (north / R)            [radians]   →  in degrees: φ0 + degrees(north / R)
λ = λ0 + east / (R · cos φ0)    [radians]   →  in degrees: λ0 + degrees(east / (R cos φ0))
```

This is the **equirectangular** (local flat) approximation.

> [!NOTE]
> Do not mix it up with lesson 6. There, NAVERA's day vision uses the shortcut
> `M_PER_DEG = 111 320.0` m per degree (the WGS84 equator radius a·π/180). Here, the node uses the
> sphere of radius R = 6 371 000 m, as `navera_common/geo.py` does: 111 195 m per degree. The two
> models differ by 0.1 % (about 125 m per degree); use one model consistently in one program. In Muscat, cos(23.588°) = 0.9165, so one
degree of longitude is 101 910 m. How wrong is it? Compare with a **great circle**, the true
"straight line" on a sphere, which NAVERA computes in `navera_common/geo.py` (`dead_reckon`).

Worked example: drive **due east** for d metres from latitude φ0. A great circle that starts towards
the east does not stay on the parallel φ0; it bends towards the equator. For small d, its distance
from the parallel is about

```
y ≈ d² · tan(φ0) / (2R)
```

At Muscat, tan(23.588°) = 0.4366. For d = 10 km: y ≈ 10⁸ × 0.4366 / (2 × 6.371 × 10⁶) ≈ **3.4 m**.
For d = 100 km: about **343 m** — the error grows with d², so 10 times farther means 100 times
larger. For other headings a second term appears (the length of a degree of longitude changes as
the latitude changes), and the lab measures the total with NAVERA's own function. Conclusion: the
flat model is excellent for a bench test of a few kilometres, and unacceptable for a 100 km flight
plan. NAVERA uses the spherical formula wherever a position is carried far.

## 🐦 How birds do it

The **Arabian babbler** lives in dry wadis and scrub in Oman and across Arabia. Its groups feed on the
ground, where they cannot see much — so one bird often climbs to a high perch and keeps watch: a
**sentinel**. Studies of this species (Jonathan Wright and colleagues, 2001) found that sentinels go
on guard mostly after they have fed well, and that the sentinel is the first to call when a raptor
appears. In a related species, the southern pied babbler of the Kalahari, the sentinel also gives a
quiet, regular **"watchman's song"** while on duty; Linda Hollén, Matthew Bell and Andrew Radford
showed in 2008 that foragers who hear it spend less time looking up and more time feeding.

That is a periodic publisher with a heartbeat:

- the sentinel publishes on a channel everyone nearby can hear, without knowing who listens;
- it publishes **regularly**, so that silence itself is information ("nobody is watching");
- an alarm call is a different message type with a different meaning.

NAVERA does the same with `/navera/nav_status`: five messages per second even when nothing changes,
so that an operator notices at once when the arbiter goes silent.

> [!NOTE]
> **Time matters for birds too.** A pigeon's sun compass needs a correct internal clock, because the
> sun moves across the sky. In classic clock-shift experiments, pigeons kept for days under lights
> switched on and off 6 hours early flew off about 90° away from home — a quarter of the sun's
> daily turn. A wrong time stamp gives a wrong direction, for birds and for robots.

## In NAVERA

NAVERA's engineers have a fake sensor node too:
[navera_tools/sensor_sim.py](file:navera/navera_tools/sensor_sim.py). It publishes simulated GPS,
IMU and clock data on the **real** topic names to test the whole chain on a bench. Its GPS tick
(compare with your `make_fix`):

```python
def tick_gps(self):
    lat, lon, v_e, v_n, _, _, _ = self.state()
    now = self._stamp()
    cov = [SIGMA_M**2, 0.0, 0.0, 0.0, SIGMA_M**2, 0.0, 0.0, 0.0, (2*SIGMA_M)**2]
    ...
    fix = NavSatFix()
    fix.header.stamp = now
    fix.header.frame_id = "gps_link"
    fix.status.status = NavSatStatus.STATUS_FIX
    fix.status.service = NavSatStatus.SERVICE_GPS
    fix.latitude, fix.longitude, fix.altitude = lat, lon, ALT_M
    fix.position_covariance = cov
    fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
    self.pub_fix.publish(fix)
```

and its timers: `self.create_timer(0.20, self.tick_gps)   # 5 Hz`. Notice one safety habit at the
top of that file: it **refuses to run** unless `NAVERA_ALLOW_SIM=1` is set, because fake data on the
real topic names must never reach a real box by accident:

```python
if os.environ.get("NAVERA_ALLOW_SIM") != "1":
    sys.exit("refusing to run: this publishes simulated sensor data on the real "
             "NAVERA topics. Set NAVERA_ALLOW_SIM=1 on a test machine to allow it.")
```

Your fake GPS uses its own topic, `/fake_gps/fix`, which no NAVERA node reads unless you ask it to —
you will connect it to NAVERA in lesson 11.

## Common errors

| Message | Cause | Fix |
|---|---|---|
| `AssertionError: The 'position_covariance' field must be … of type 'float' …` | an `int` in a float field | `9.0`, not `9` |
| `AttributeError: 'NoneType' object has no attribute 'publish'` | `self.pub` never created | `self.pub = self.create_publisher(...)` in `__init__` |
| `TypeError: 'NoneType' object is not callable` (in a timer) | `create_timer(T, self.on_timer())` | no parentheses after the callback |
| `InvalidParameterTypeException … 'INTEGER', expecting type 'DOUBLE'` | `-p speed_mps:=12` | `-p speed_mps:=12.0` |
| nothing on the topic, no error | an exception inside the timer callback is printed in the node's terminal | read the node's terminal |

## Glossary

| Term | Meaning |
|---|---|
| **rclpy** | the Python client library of ROS 2 |
| **inheritance / `super().__init__`** | a class built on a parent class / calling the parent's constructor |
| **attribute / bound method** | data stored in an object (`self.x`) / a method attached to an object (`self.on_timer`) |
| **callback** | a function given to ROS, called later when an event happens |
| **spin** | the event loop that waits and runs callbacks |
| **timer / jitter** | calls a callback every period / the random variation of the real intervals |
| **ROS time / use_sim_time** | the node's clock / follow a simulator's `/clock` instead of the system clock |
| **parameter** | a named, typed setting of a node, changeable from outside |
| **NavSatFix** | the standard ROS message for a satellite-navigation position |
| **variance / standard deviation (σ)** | expected squared error (m²) / its square root (m) |
| **covariance matrix (ENU, row-major)** | the 3 × 3 table of variances and covariances, stored row after row |
| **ellipsoid (WGS84)** | the mathematical surface GPS altitudes refer to |
| **equirectangular approximation** | local flat-Earth conversion of metres to degrees |
| **great circle** | the shortest path on a sphere |

## Check what you learned

<details><summary>1. Why does <code>FakeGps.__init__</code> start with <code>super().__init__("fake_gps")</code>? What happens without it?</summary>
It runs the constructor of the parent class <code>Node</code>, which registers the node in ROS with that
name and prepares its clock, logger and graph connections. Without it the object is not a working
node and <code>self.create_publisher</code> fails.
</details>

<details><summary>2. A GNSS receiver states σ = 2.5 m horizontally and 5 m vertically, independent errors. Write <code>position_covariance</code>.</summary>
<code>[6.25, 0.0, 0.0, 0.0, 6.25, 0.0, 0.0, 0.0, 25.0]</code> — variances in m², row-major, ENU, floats.
</details>

<details><summary>3. The timer is set to 0.5 s, but <code>ros2 topic hz</code> shows min 0.46 s, max 0.56 s. Why should the motion use the measured dt?</summary>
Each interval differs from 0.5 s (jitter). Integrating <code>v × 0.5</code> would put the position at the
wrong place for the stamp it carries; <code>v × dt</code> with dt from the clock keeps position and stamp consistent.
</details>

<details><summary>4. Using the formula y ≈ d² tan φ0 / (2R), estimate the flat-Earth error after 50 km due east from Salalah (17.02° N).</summary>
tan(17.02°) ≈ 0.306; y ≈ (5 × 10⁴)² × 0.306 / (2 × 6.371 × 10⁶) ≈ 2.5 × 10⁹ × 0.306 / 1.274 × 10⁷ ≈ 60 m.
</details>

<details><summary>5. You forget to fill latitude and longitude. What do subscribers receive, and how does NAVERA protect itself?</summary>
0.0 and 0.0 ("Null Island") with no error. NAVERA's GPS code treats exactly (0, 0) as invalid.
</details>

Now open the **🛠️ Lab** tab.
