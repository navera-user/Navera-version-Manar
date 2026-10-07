# Who to believe? The NAVERA arbiter

A drone flies along the coast near Sousse. Its GPS says *"you are here, ±3 m"*. Its day camera,
matching the ground with the satellite map, says *"you are 40 m further north, accuracy unknown"*.
The star camera, pointed at the sky, says *"you are somewhere in this 50 km circle"*. Then a truck
with a jammer drives by and the GPS goes quiet…

The autopilot cannot fly on four opinions. It needs **one** position, now, and an honest idea of how
much to trust it. In NAVERA, the part that decides is called the **arbiter** (the package
`navera_estimator`). It is like the referee of a football match: it does not play, it does not
measure anything itself — it watches the players (the sources) and applies **the same written rules
every time**.

In this lesson you will learn those rules, write your own arbiter in Python, and race it against the
real one.

## 1. The players: four sources, one contract

You met them all in modules 4 and 5. Each one is a ROS 2 node that publishes the **same message**,
`navera_msgs/PositionEstimate` (lesson 12), on its own topic:

| Source | Topic | Typical accuracy today |
|---|---|---|
| GPS (`gps_node`) | `/navera/estimate/gps` | a few metres, **stated** from the HDOP |
| Day vision (`day_subscriber`) | `/navera/estimate/day` | states 30 m (`local_sigma_m`) until measured with NAVERA's camera |
| Night vision (`night_subscriber`) | `/navera/estimate/night` | not validated on real thermal images |
| Celestial (`cn_subscriber`) | `/navera/estimate/cn` | coarse: tens of km (bounded by the IMU attitude) |

Because every source speaks the same language, the arbiter has **no special case** for any of them.
It reads the same fields from everybody: `valid`, `mode`, `header.stamp` / `sensor_stamp`, `latitude`,
`longitude`, `position_covariance` and `position_covariance_type`. One rule for all — that is what
makes it testable, and what lets a new source be added tomorrow without touching the arbiter.

![The two questions of the arbiter](assets/arbiter.svg)

## 2. Question one: is this source usable? (eligibility)

A source that talks is not automatically a source you can use. A message is **eligible** only when
*all* of these are true:

1. **`valid` is true.** The source itself says "use me". The GPS driver, for example, publishes
   `valid=false` when the receiver has no satellite fix — it does not stay silent, it says *"I have
   nothing"*. That is honest, and the arbiter respects it.
2. **The mode is `MEASURED` or `PROPAGATED`.** A `HELD` message (the last value repeated, no new
   information) or a `REPLAYED` one (test data from a file) can never win.
3. **It is fresh.** Its *age* — now minus the instant it was measured — must be smaller than the
   source's **freshness window**. A position from 10 seconds ago describes where the drone *was*,
   not where it *is*.
4. **The position is a real position:** finite numbers (no `NaN`, no infinity), latitude within ±90°,
   longitude within ±180°, and not exactly (0, 0) — the famous "Null Island" in the Atlantic where
   broken software puts things.
5. **The covariance is a real covariance:** finite, no negative variance, symmetric. You will learn
   what that means in lesson 26; for now: *if the error description is impossible, the whole message
   is thrown away*, because the autopilot's filter would break on it.

### Freshness windows

Each source has its own window, in `navera_estimator/config/estimator_params.yaml`:

| Source | Window | Why |
|---|---|---|
| GPS | 3 s | the receiver sends 1 fix per second (measured: 1.000 Hz); 3 s tolerates 2–3 lost fixes |
| Day vision | 5 s | frames come every 1–4 s under load |
| Night vision | 5 s | same idea |
| Celestial | 45 s | a star solve takes ~15 s and fixes are rare |

The day window used to be 3 s. In the mission simulator, under load, NAVERA then flickered between
FIX and NO FIX on 20–60 % of samples and the autopilot landed during a 6.7–9.2 s gap; it is 5 s since
(docs/VALIDATION_STATUS.md, **simulator only**). A good example of a number that was *measured*, not
decided.

> [!NOTE]
> **"Age" is measured from the instant of the measurement**, the field `sensor_stamp` (the photo's
> exposure, the NMEA sentence). A fix computed slowly from an old photo is as old as the photo.
> And a stamp more than **0.5 s in the future** is refused: it means a clock went wrong, so its age
> cannot be trusted. The reason then reads *"timestamp 60.0s in the future (clock problem)"*.

## 3. Question two: who wins? (priority)

Among the usable sources, the arbiter takes the **first one in a fixed order**:

**GPS > day vision > night vision > celestial**

Why this order? Because it is the order of how good each source is *when it works*: a GPS lock is a
few metres; day vision is the next best; night vision works on fewer landmarks; celestial is a
coarse fix (tens of km). There is exactly **one winner**, or none. NAVERA does not average sources
today: it is a *single-winner* arbiter (lesson 26 shows the maths that a future fusion would use).

### The hold-off: no zig-zag

Imagine a GPS that keeps flapping: valid, invalid, valid, invalid, every half second (a bad cable,
a jammer at the edge of its range). With the pure priority rule, the output would jump between the
GPS position and a vision position maybe hundreds of metres away, twice a second. The autopilot would
see its position teleport back and forth.

So there is a **switch hold-off** (`switch_holdoff_s`, 2 s): *while the active source stays usable,
a better source must have been usable **continuously** for 2 s before it takes over.* Losing the
active source, on the other hand, switches **immediately** — you never keep a source that is gone.

Measured on the bench (VALIDATION_STATUS.md, *Robustness*): with a GPS flapping every 0.5 s, the
output made **one source switch in 8 s, no zig-zag**.

Here is the real code, `_select()` in `estimator_node.py` (shortened):

```python
def _select(self, now, candidates):
    for src, eligible, _ in candidates:          # remember since when each source is usable
        if eligible:
            self._eligible_since.setdefault(src, now)
        else:
            self._eligible_since.pop(src, None)
    eligible = [(src, msg) for src, ok, msg in candidates if ok]
    if not eligible:
        self._active_source = None
        return None                               # -> NO_FIX
    best_src, best_msg = eligible[0]              # candidates are in priority order
    active = next(((s, m) for s, m in eligible if s == self._active_source), None)
    if active is not None and best_src != self._active_source:
        dwell = (now - self._eligible_since[best_src]).nanoseconds / 1e9
        if dwell < self._holdoff:
            return active[1]                      # keep the active source for now
    self._active_source = best_src
    return best_msg
```

`setdefault` keeps the *first* time a source became usable; `pop` forgets it as soon as it stops.
That is how "continuously usable" is measured.

## 4. How good is the winner? The four states

Choosing a winner is half the job. The operator — and the autopilot — also need to know **how much
to trust it**. That is the `state` field of `/navera/nav_status`:

![The four states](assets/states.svg)

The rule (`_classify()`) is short and strict:

| The winner is… | State | Reason (examples of the real text) |
|---|---|---|
| MEASURED, stated σ between 1 cm and 25 m | **FIX** | `GPS fix` |
| MEASURED, stated σ above 25 m | **DEGRADED** | `GPS fix, uncertainty 40 m > 25 m` |
| MEASURED, uncertainty unknown (type UNKNOWN, or σ below 1 cm) | **DEGRADED** | `day vision fix, uncertainty unknown` |
| PROPAGATED (dead-reckoned) | **DEGRADED** | `day vision solution is propagated (dead-reckoned)` |
| no usable source | **NO_FIX** | `GPS: stale (4.2s>3.0s); day: none received; …` |
| nothing ever received | **INITIALIZING** | `waiting for first source message` |

**σ** ("sigma") is the source's own statement of its accuracy, in metres — lesson 26 explains it
properly. A GPS with a bad satellite geometry (HDOP 20) states σ ≈ 40 m: it still wins, but it is
DEGRADED, not FIX.

Why is a σ of **0** "unknown"? Because 0 m would mean *perfect* — and nothing is perfect. A zero
almost always means *"somebody forgot to fill the field"*. On the bench, a GPS with an all-zero
covariance used to be reported FIX "with accuracy 0"; it is now DEGRADED "uncertainty unknown"
(VALIDATION_STATUS.md, *Robustness*).

> [!TIP]
> This rule is **self-correcting**: the day the day-vision accuracy is measured with NAVERA's real
> camera and stated honestly below 25 m, day vision becomes FIX **without changing one line** of the
> arbiter. Promotion to green is the reward for measuring, never a decision.

### The reason string

Every status carries a `reason` in plain English: *why* this state. It is written for humans (the
operator view shows it), **never parsed by a program** — decisions use the typed fields only. For
NO_FIX it lists one clause per source, in priority order:

```
GPS: stale (10.8s>3.0s); day: stale (8.3s>5.0s); night: stale (6.3s>5.0s); cn: timestamp 54.7s in the future (clock problem)
```

That line alone tells an engineer what went wrong in a flight. When GPS is still talking but has been
refused (lesson 27), the reason says so: `day vision fix, uncertainty unknown — GPS refused: …`.

## 5. When does the arbiter decide?

Two moments:

- **when a message arrives** (no added delay: a new GPS fix is passed on at once), and
- **on a 5 Hz clock** (`publish_rate_hz`), even if nothing arrives. Why? Because a source that goes
  *silent* sends no message to say so! Only a clock can notice that the GPS has said nothing for 3 s.

And `/navera/position` carries each winning measurement **once**: the same fix is never re-published
at every tick (a filter downstream would count it many times). Bench result: *"Estimator: one
measurement → Published once (it was re-published at 5 Hz)"*.

## 6. In NAVERA

| What | Where in your copy (`~/navera/…`) |
|---|---|
| The node | `navera_estimator/navera_estimator/nodes/estimator_node.py` |
| Its settings | `navera_estimator/navera_estimator/config/estimator_params.yaml` |
| How it is started | `navera_estimator/navera_estimator/launch/estimator.launch.py` |
| Its integration test (real node, scripted inputs) | `navera_tools/tests/test_estimator.py` |
| The documented rules | `docs/ARCHITECTURE.md` §3 |
| The messages | `navera_msgs/msg/PositionEstimate.msg`, `NavStatus.msg` |

The methods to know: `_eval_source()` (fresh / eligible), `_sane()` (position and covariance),
`_select()` (priority + hold-off), `_classify()` (FIX / DEGRADED), `_no_fix_reason()` and
`_source_reason()` (the reason text), `_tick()` (puts it all together, 5 times a second).

## Glossary

| Word | Meaning |
|---|---|
| **arbiter** | the part that elects one position among several sources (`navera_estimator`) |
| **eligible** | usable right now: valid, right mode, fresh, sane |
| **freshness window** | the maximum age of a message before it is "stale" |
| **stale** | too old to describe the present |
| **priority** | the fixed order GPS > day > night > celestial |
| **hold-off** | the 2 s a better source must stay usable before it takes over (anti zig-zag) |
| **flapping** | a source that keeps going on and off |
| **σ (sigma)** | the accuracy a source states, in metres (lesson 26) |
| **FIX / DEGRADED / NO_FIX / INITIALIZING** | the four states of `/navera/nav_status` |
| **reason** | the plain-English explanation of the state, for humans only |

## Check what you learned

<details><summary>1. GPS (σ 3 m) and day vision (σ unknown) are both fresh and valid. Who wins, and what is the state?</summary>
GPS wins (first in the priority order) and the state is <b>FIX</b>, reason "GPS fix".
</details>

<details><summary>2. The GPS stopped talking 4 s ago. Day vision is fresh. What happens?</summary>
GPS is stale (4 s ≥ 3 s), so day vision wins at once (losing the active source switches immediately).
The state is <b>DEGRADED</b>: "day vision fix, uncertainty unknown".
</details>

<details><summary>3. Day vision is active. GPS comes back, valid and fresh. Why does NAVERA wait before using it?</summary>
The hold-off: GPS must stay usable continuously for 2 s before it takes over, so that a flapping GPS
cannot make the position zig-zag between GPS and vision.
</details>

<details><summary>4. A GPS message says σ = 0 m. FIX or DEGRADED?</summary>
DEGRADED, "uncertainty unknown": a σ below 1 cm is not an accuracy, it is a missing one.
</details>

<details><summary>5. Why does the arbiter also decide on a clock, and not only when a message arrives?</summary>
Because a source that goes silent sends no message: only a clock can notice that nothing arrived for 3 s.
</details>

Now open the **🛠️ Lab** tab.
