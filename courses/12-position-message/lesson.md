# The NAVERA position contract

Imagine a jury judging four athletes: a sprinter timed with a stopwatch, a swimmer timed with
an electronic plate, a cyclist timed by GPS, and a runner who says "trust me, I was fast". To compare
them fairly, the jury needs every result written **the same way**: the time, *how* it was measured,
*how precise* the measure is, and *when* the race took place. Without that, the jury compares
apples with oranges — and the one who boasts wins.

NAVERA's arbiter is that jury. GPS, day vision, night vision and the stars measure the position in
completely different ways, with very different precision. NAVERA forces them all to fill in **one
form**: the message `navera_msgs/msg/PositionEstimate`. Engineers call such an agreement a
**contract**: "if you want to be judged, you must fill every box, honestly". Today you learn every
box of that form — then you become a position source yourself and face the jury.

![PositionEstimate: one form, five questions](assets/contract.svg)

## WHERE? — position and covariance

| Field | Meaning |
|---|---|
| `latitude`, `longitude` | the position in degrees, WGS84 (lesson 6) |
| `altitude` | metres above the WGS84 ellipsoid — **NaN if unknown** |
| `position_covariance` | 9 numbers: the uncertainty, as in NavSatFix (lesson 10) |
| `position_covariance_type` | UNKNOWN (0), APPROXIMATED (1), DIAGONAL_KNOWN (2), KNOWN (3) |

Two rules of honesty hide in this table.

**"Unknown" is written NaN, never 0.** **NaN** ("Not a Number", `math.nan` in Python) is a special
float value meaning "no value". An altitude of `0.0` is a real altitude — sea level! A program that
writes 0.0 for "I don't know" is lying without knowing it. NaN has a useful property: any calculation
with NaN gives NaN, and NaN is not even equal to itself (`math.nan == math.nan` is `False`), so it
cannot be mistaken for a number. Test it with `math.isnan(x)`.

**Covariance: say how sure you are — or say you don't know.** As in lesson 10, the covariance holds
the **variances** (σ²) east and north at places 0 and 4. A source that is good to 15 m writes
`15² = 225` there. The arbiter takes the square root to read the stated **σ** back. You can picture
σ as a circle around the position: the error towards the east (or towards the north) is smaller than
σ about two times out of three, and smaller than 2σ about 19 times out of 20.

![The position, and its uncertainty as a circle of radius sigma](assets/sigma.svg)

And if a source does not know its precision? Then it must say so: `COVARIANCE_TYPE_UNKNOWN` and nine
zeros. The message file is very direct about it: *"Publish UNKNOWN rather than an invented matrix: a
fabricated covariance is indistinguishable from a measured one downstream."* A made-up "5 m" would
look exactly like a measured 5 m to everyone after.

The covariance must also *be* a covariance: variances can't be negative (they are squares!), the
table must be symmetric, and no number may be NaN or infinite. The arbiter checks all of it.

## WHO? and HOW? — source and mode

`source` says which method produced the position: `SOURCE_GPS` (1), `SOURCE_DAY_VISION` (2),
`SOURCE_NIGHT_VISION` (3), `SOURCE_CELESTIAL` (4)…

`mode` says **how fresh the information is** — the honesty axis of the contract:

| mode | meaning | may the arbiter use it? |
|---|---|---|
| `MODE_MEASURED` (0) | freshly measured now (a GPS fix, a matched photo) | yes |
| `MODE_PROPAGATED` (1) | **dead-reckoned**: carried forward from an older fix with the speed and heading — like counting steps blindfolded | yes, but DEGRADED |
| `MODE_HELD` (2) | the last value repeated: **no new information** | never |
| `MODE_REPLAYED` (3) | ground truth from a test dataset | never — not a measurement |

`REPLAYED` exists because engineers test pipelines with recorded data where the true position is
known. If such a position ever reached a real autopilot, it would look perfect and be totally
fake. Labelling it lets the arbiter refuse it automatically.

## MAY I USE IT? — valid, reason, confidence

`valid` is the source's own verdict: `false` means "do not use this position", for example when the
GPS receiver has no fix or a photo shows only sea. `reason` explains why, **for humans**: the
message file says *"nothing may make a decision"* on text. `confidence` (0 to 1) is a score
local to each source: a 0.9 from one algorithm and a 0.9 from another mean different things, so the
arbiter never compares them. Only the covariance may be compared across sources.

## WHEN? — two time stamps

| Field | The instant of… |
|---|---|
| `sensor_stamp` | the **measurement**: the photo's exposure, the GPS sentence |
| `header.stamp` | the **publication** of the message |

![sensor_stamp is when the photo was taken, header.stamp when the result was published](assets/stamps.svg)

Why two? Day vision needs some time to find a photo on the map. If the photo was taken at 12:00:00.000
and the result published at 12:00:00.640, the position describes **12:00:00.000** — the drone flew on
during those 0.64 s (at 20 m/s, 13 m!). The arbiter judges freshness on `sensor_stamp`: *a position is
as old as its photo*. `header.stamp` minus `sensor_stamp` is the **latency** of the source — useful to
know and to improve. (A producer that leaves `sensor_stamp` at zero is judged on `header.stamp`.)

## Traceability

`producer` (the node's name), `model_id` (the algorithm or its version), `frame_index` (which camera
frame, −1 if none) and `details_json` (any extras, as JSON text) let an engineer trace every position
back to where it came from. Rule 2 of the message: **nothing may decide on `details_json`**. If a value
becomes important for a decision, it must become a real, typed field of the contract.

## The jury's rule

Here is the arbiter's rule, from `docs/ARCHITECTURE.md` §3, in plain words. A source is **eligible**
when:

1. `valid` is true;
2. `mode` is MEASURED or PROPAGATED;
3. it is **fresh**: its age (now − `sensor_stamp`) is below the source's window (GPS 3 s, day vision
   3 s when started with `ros2 run`, 5 s with NAVERA's launch file — lesson 13) and at most 0.5 s in
   the future;
4. its position is finite and in range, and its covariance is a real covariance.

Among eligible sources, the priority is **GPS > day > night > celestial**. Then the state:

- **FIX** if the winner is MEASURED with a **stated** σ of at most 25 m (`fix_max_sigma_m`) — a defined
  covariance type and σ ≥ 1 cm;
- **DEGRADED** if the winner's uncertainty is unknown or larger, or it is PROPAGATED;
- **NO_FIX** if no source is eligible, with a reason for each one.

The rule is **the same for every source**. The comment in the code says it proudly: *"Generic — no
per-source special-casing; the arbiter has NO knowledge of any source's quirks, it applies one rule."*
This is the power of a contract: when IRIS Systems adds a new source tomorrow, the arbiter does not
change — the new source only has to fill the form honestly.

> [!WARNING]
> The other side of "one rule": the arbiter **believes** the σ a source states. A source that
> claims 15 m while really being 500 m off would get a green FIX. That is why NAVERA's day vision
> does not state an accuracy until it is measured (`docs/VALIDATION_STATUS.md` shows which numbers
> are measured, and how). Honesty is not a decoration of the contract — it is what makes it work.

## In NAVERA

The rule lives in [estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py).
Here is the eligibility test, applied identically to every source:

```python
age = self._age_s(now, self._measured_at(last))      # now - sensor_stamp
alive = -self._future_tol <= age < timeout
eligible = (alive and last.valid and last.mode in _ELIGIBLE_MODES
            and self._sane(last))
```

and the classification of the winner:

```python
if winner.mode == PositionEstimate.MODE_MEASURED and bounded and sigma > self._fix_max_sigma:
    return (NavStatus.STATE_DEGRADED,
            f"{name} fix, uncertainty {sigma:.0f} m > {self._fix_max_sigma:.0f} m")
if winner.mode == PositionEstimate.MODE_MEASURED and bounded:
    return NavStatus.STATE_FIX, f"{name} fix"
if winner.mode == PositionEstimate.MODE_MEASURED:
    return NavStatus.STATE_DEGRADED, f"{name} fix, uncertainty unknown"
return NavStatus.STATE_DEGRADED, f"{name} solution is propagated (dead-reckoned)"
```

And here is how real day vision fills the form, in
[day_subscriber.py](file:navera/day_pkg/day_pkg/nodes/day_subscriber.py) (`_publish_estimate`):

```python
est.altitude  = float(_alt) if _alt is not None else math.nan
if src in ("local_match", "dead_reckon") and valid:
    var = (self.local_sigma_m if src == "local_match" else self._dr_sigma) ** 2
    est.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 0.0]
    est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
else:
    est.position_covariance      = [0.0] * 9
    est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
est.source     = PositionEstimate.SOURCE_DAY_VISION
...
est.sensor_stamp = exposure_stamp(meta, now)
est.producer   = "day_subscriber"
```

Altitude NaN when unknown, a covariance only when there is a stated accuracy (otherwise UNKNOWN and
zeros), and `sensor_stamp` at the photo's exposure. In the lab you will write your own version of
exactly this.

## Words to remember

| Word | Meaning |
|---|---|
| **contract** | an agreement on a message's format *and meaning*, that every producer respects |
| **NaN** | "Not a Number": the honest value for "unknown" (`math.nan`, `math.isnan()`) |
| **σ (sigma)** | the stated uncertainty in metres; the variance σ² goes in the covariance |
| **mode** | measured / propagated / held / replayed: how fresh the information is |
| **dead-reckoning** | carrying a position forward with speed and heading, without a new measurement |
| **sensor_stamp / header.stamp** | instant of the measurement / of the publication |
| **latency** | header.stamp − sensor_stamp: how long the source took |
| **eligible** | allowed to be chosen by the arbiter (valid, right mode, fresh, sane) |
| **traceability** | being able to trace a value back to who produced it, and how |

## Check what you learned

<details><summary>1. A night-vision node does not know the altitude. What does it write in <code>altitude</code>, and why not 0.0?</summary>
<code>math.nan</code>. 0.0 is a real altitude (sea level) and would be mistaken for a measurement.
</details>

<details><summary>2. A source is good to 20 m. What goes at places 0 and 4 of the covariance? Will NAVERA say FIX?</summary>
400 (20²). With a defined covariance type and MEASURED mode, σ = 20 m ≤ 25 m: FIX.
</details>

<details><summary>3. A photo was taken 4 s ago, its result published 0.2 s ago. Is it fresh for day vision (window 3 s)?</summary>
No. Freshness uses <code>sensor_stamp</code>: the position is 4 s old, whatever the publication time.
</details>

<details><summary>4. Why does the arbiter refuse MODE_HELD even when valid is true?</summary>
A held position is the last value repeated: it carries no new information. Accepting it would show
an old position as if it were current.
</details>

<details><summary>5. Why must decisions never be taken on <code>reason</code> or <code>details_json</code>?</summary>
They are free text: nobody guarantees their format, and a change of wording would silently change a
decision. Decisions use typed fields that every node agrees on.
</details>

Now open the **🛠️ Lab** tab.
