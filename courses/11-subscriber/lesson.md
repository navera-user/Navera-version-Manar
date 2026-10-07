# Listening: a subscriber

In lesson 10 your fake GPS shouted its position into the topic `/fake_gps/fix`, twice per second.
But shouting is only half of a conversation. Somebody has to **listen** — and not just listen, but
**remember**: a car's trip computer does not only show where you are now, it shows how far you have
driven since the start and how fast you are going. To know your speed, you must remember where you
were a moment ago.

That is today's lesson: **subscribers**, the **callbacks** ROS calls when a message arrives, and how a
node **keeps state** between two messages. At the end of the lab, a node you wrote will listen to the
decisions of NAVERA's real arbiter — fed by a GPS that *you* control, and that you will switch off to
see how NAVERA reacts.

## A subscriber: your node's ear

To receive messages, a node creates a **subscription**:

```python
self.create_subscription(NavSatFix, "/fake_gps/fix", self.on_fix, 10)
```

Four things, in this order:

1. **the message type** — it must be the type published on the topic, or nothing will connect;
2. **the topic name**;
3. **the callback** — the method ROS must call for every message (without parentheses, as for the
   timer in lesson 10);
4. **the queue depth** (or a QoS profile, see below).

Then you write the callback. ROS gives it **one argument: the message**.

```python
def on_fix(self, msg):
    print(msg.latitude, msg.longitude)
```

You never call `on_fix` yourself. While `rclpy.spin(node)` runs, ROS waits; when a message arrives on
`/fake_gps/fix`, ROS calls `on_fix(msg)` with it. When the callback returns, ROS goes back to waiting.
This style of programming — "when this happens, do that" — is called **event-driven**. Your phone
works the same way: an app does nothing until you touch the screen or a notification arrives.

> [!WARNING]
> A callback must be **quick**. While it runs, the node cannot handle anything else: no other
> message, no timer. If a callback needs 3 seconds, the 6 messages that arrived meanwhile wait in the
> queue — and if the queue (depth 10) is full, the oldest are thrown away.

## Keeping state: the node's memory

Here is a callback that tries to compute the distance travelled:

```python
def on_fix(self, msg):
    distance = 0.0
    distance = distance + 3.0      # pretend we moved 3 m
    print(distance)                 # always prints 3.0 !
```

It always prints `3.0`. Why? Every call of a function starts fresh: `distance` is a **local
variable**, created when the function starts and **forgotten** when it ends. Between two messages,
the callback remembers nothing.

To remember, store the value **in the object**, with `self` — the node's backpack from lesson 10:

```python
def __init__(self):
    ...
    self.distance_m = 0.0          # created once, when the node starts

def on_fix(self, msg):
    self.distance_m += 3.0         # still there at the next call
    print(self.distance_m)         # 3.0, 6.0, 9.0, ...
```

What a program remembers between two events is called its **state**. Our trip computer's state is:
how many fixes it received, the total distance, and **the previous fix** (latitude, longitude, time).
With the previous fix and the new one you can compute:

- the **step**: the distance between them, with the haversine formula of lesson 6;
- the **time between them**, `dt`, from the two time stamps;
- the **speed** = step ÷ dt.

![Two consecutive fixes give a step and a time: speed = step / dt](assets/two_fixes.svg)

### Which time?

Use the **time stamp in the message** (`msg.header.stamp`), not the clock of your computer when the
message arrives. The stamp says when the GPS *measured* the position. Messages can be delayed by the
network or wait in a queue: two fixes measured 0.5 s apart may arrive 0.1 s apart. With arrival
times your speed would jump around; with measurement times it is right. NAVERA follows this rule
everywhere — it even has two different stamps for it (lesson 12).

A ROS time stamp has two whole numbers: `sec` (seconds since 1 January 1970) and `nanosec`
(billionths of a second). In seconds: `t = stamp.sec + stamp.nanosec * 1e-9`.

### A class without ROS inside

In the lab, the trip computer is a small class, `Tracker`, with **no ROS inside**: its method
`update(lat, lon, t)` takes three plain numbers. The ROS node only unpacks each message and gives the
numbers to the tracker. Why bother? Because you can test `Tracker` with three lines of Python, without
starting any node, any GPS, any topic — and you will (lesson 14 is all about this). Engineers call
this **separating the logic from the plumbing**. NAVERA does it all the time: its GPS code has a
function `estimate_from_fix(m)` that turns one NavSatFix into a PositionEstimate, tested on its own
in `gps_pkg/test/test_ros_gps.py`.

## Talking to NAVERA

Now the exciting part. NAVERA's arbiter does not read NavSatFix messages: it reads the NAVERA
**contract**, `PositionEstimate`, on `/navera/estimate/gps`. Between the two, NAVERA has a small
node exactly for this job: **`ros_gps_node`**, in your copy at
[gps_pkg/…/ros_gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/ros_gps_node.py). It exists so that
NAVERA can use the GPS of a vehicle that already publishes a NavSatFix (a boat, a ground robot):

```python
self.create_subscription(NavSatFix, topic, self._on_fix, qos_profile_sensor_data)
...
def _on_fix(self, m: NavSatFix):
    ...
    self.pub_est.publish(estimate_from_fix(m))
```

A subscriber whose callback publishes: it **listens on one topic and speaks on another**. Many ROS
nodes are like that — they are links in a chain.

Which topic does it listen to? By default `/navera/vehicle/gps2` (the autopilot's second GPS), but
it has a **parameter** called `fix_topic` that you can change when you start it:

```bash
ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix
```

`--ros-args -p name:=value` sets a parameter — lesson 13 explains them in detail. With this one
command, NAVERA listens to **your** GPS.

![The chain: your GPS → ros_gps_node → the arbiter → your status listener](assets/chain.svg)

Notice the QoS: `qos_profile_sensor_data` is a **BEST_EFFORT** profile. As you learned in lesson 10,
a best-effort subscriber receives from both kinds of publishers — so NAVERA works with any GPS
driver, whatever QoS it uses.

### What the arbiter says

The arbiter answers on `/navera/nav_status` with a `NavStatus` message, 5 times per second. The
fields you need today:

| Field | Meaning |
|---|---|
| `state` | `STATE_INITIALIZING` (0), `STATE_NO_FIX` (1), `STATE_FIX` (2) or `STATE_DEGRADED` (3) |
| `active_source` | who provides the position: `SOURCE_GPS` (1), `SOURCE_DAY_VISION` (2)… or `SOURCE_UNKNOWN` (0) |
| `active_mode` | measured, propagated… (lesson 12) |
| `sources` | one line per source: `alive`, `last_seen`, `contributing` |
| `reason` | one sentence for humans, e.g. `GPS fix` |

Use the **constants** in your code (`NavStatus.STATE_FIX`), never the bare numbers: `if msg.state == 2`
means nothing to the next reader, `if msg.state == NavStatus.STATE_FIX` explains itself.

The `reason` is for humans: NAVERA's rule, written at the top of `NavStatus.msg`, is that **no program
may make a decision on that text** — decisions are taken on the typed fields. Your status listener
will *print* the reason, but decide on `state` and `active_source`.

### Freshness: what happens when the GPS stops

The arbiter only trusts a **fresh** position. When it starts with `ros2 run`, its GPS window is
3 seconds (`gps_timeout_s`): if the newest GPS fix was measured more than 3 s ago, GPS is not usable
anymore. With no other source, the state goes to `NO_FIX`, and the reason explains which source said
what: `GPS: stale (3.2s>3.0s); day: none received; …`. NAVERA never keeps sending an old position as if
it were current — an old position presented as new is how vehicles get lost. You will see this
yourself in the lab by stopping the GPS.

## 🐦 How birds do it

Remember the chickadee's alarm call from lesson 10? Somebody listens. **Red-breasted nuthatches**,
another small bird of the same forests, react to chickadee alarms. In 2007, Christopher Templeton and
Erick Greene showed that the nuthatches don't just react to *any* call: they react more strongly to the
"dangerous predator" version, with more "dee" notes. They **read the value inside the message** and
decide what to do. That is a subscriber with a callback.

Birds also **keep state**. The **Clark's nutcracker**, a bird of the mountains of North America, hides
thousands of pine seeds in autumn, a few at a time, in many small hiding places in the ground. Months
later, sometimes under snow, it comes back and finds a large part of them — using the landmarks
around each hiding place. Every seed it hides is like one message stored in the node's memory, to be
used much later.

And Navi adds one more thing: **freshness**. An alarm call is useful *now*. A swallow that panics
because of a cat that left ten minutes ago wastes its energy; one that ignores a fresh alarm may be
eaten. The age of a message matters as much as its content.

That is exactly what NAVERA's arbiter does in its callbacks: it **stores** each new position with its
time, then decides in `_tick()` — and a source that has gone silent for too long is no longer trusted.

## In NAVERA

Open [estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py) and
look at the callbacks of the arbiter. They are short — they **store**, and the decision happens in
`_tick()`:

```python
def _on_day(self, msg: PositionEstimate) -> None:
    self._day_last = msg
    self._tick()
```

`self._day_last` is state: the latest day-vision estimate, kept between messages. `_tick()` is also
called by a **timer** 5 times per second — so the arbiter notices a source that went silent even when
no message arrives at all. A subscriber alone could never notice silence: its callback is only called
when something *arrives*. Combining a subscription (to receive) and a timer (to check regularly) is a
classic pattern you now know.

## Words to remember

| Word | Meaning |
|---|---|
| **subscription / subscriber** | the object (and the node) that receives the messages of a topic |
| **callback** | the method ROS calls for each message, with the message as argument |
| **event-driven** | a program that waits and reacts to events (messages, timers) |
| **local variable** | a variable inside a function, forgotten when it returns |
| **state** | what a node remembers between events, stored in `self` |
| **step / dt / speed** | distance between two fixes / time between them / step ÷ dt |
| **fresh / stale** | recent enough to be used / too old |
| **parameter** | a setting of a node that you can change when you start it (`-p name:=value`) |

## Check what you learned

<details><summary>1. Who calls your callback <code>on_fix</code>, and when?</summary>
ROS calls it, during <code>rclpy.spin(node)</code>, each time a message arrives on the topic. You never
call it yourself.
</details>

<details><summary>2. Your callback computes <code>count = count + 1</code> with <code>count = 0</code> at its first line. It always prints 1. Why, and how do you fix it?</summary>
<code>count</code> is a local variable, recreated at every call. Store it in the node:
<code>self.count = 0</code> in <code>__init__</code>, and <code>self.count += 1</code> in the callback.
</details>

<details><summary>3. Why compute the speed with the message time stamps instead of the arrival times?</summary>
The stamps say when the positions were measured. Arrival times include network and queue delays,
which would make the speed jump.
</details>

<details><summary>4. The GPS stops publishing. Can a node that only has a subscription notice it?</summary>
No: its callback is only called when a message arrives, so silence calls nothing. You need a timer
that regularly checks the age of the last message — exactly what the arbiter's <code>_tick()</code> does.
</details>

Now open the **🛠️ Lab** tab.
