# Measuring honestly

A salesman shows you a new navigation box: *"Accuracy: 4 metres!"* Should you buy it?

Before answering, an engineer asks five questions. **4 metres — the average, the median, or the
best case?** **On how many measurements?** **Where: in a lab, a simulator, a real flight?** **Compared
with what?** **And how often does it give no position at all?** Without the answers, "4 metres" means
nothing — it might even be true *and* useless.

NAVERA's documentation is built on this discipline. Its engineering rules say *"Measure, don't guess"*
and *"Honesty over optimism. If a result is only validated in simulation, say so."* This lesson teaches
you to produce numbers that deserve to be believed — and to read other people's numbers critically.

## 1. Truth, estimate, error

To measure a navigation system you need the **truth**: where the vehicle really was. In a simulator
it is free (the simulator *is* the world). In a real flight it comes from a better reference: an RTK
GPS (centimetres), or the ordinary GPS when you measure vision — NAVERA's `evaluate_session.py` uses the
GPS fixes, interpolated at the instant each photo was taken, as the truth for vision.

For every moment where the system gave an **estimate**, the **error** is the distance between estimate
and truth (Pythagoras on a local map, or the *haversine* formula on the sphere — lesson 6). One flight
gives you a long list of errors, one per second or per frame. Now you have to summarise it.

## 2. Mean, median, percentiles, max

You met mean and median in lesson 26. For errors, engineers report several numbers, because each one
answers a different question:

| Number | Question it answers | Weakness |
|---|---|---|
| **median** (p50) | "how good is a typical fix?" — half are better, half worse | hides the bad cases completely |
| **mean** | the average | pulled by a few huge errors (outliers) |
| **p90** (90th percentile) | "how bad is it on a bad day?" — 90 % of fixes are better | needs enough samples |
| **max** | "what is the worst that happened?" | one unlucky sample decides it |

A **percentile** is easy: sort the errors; the p90 is the value 90 % of the way along the sorted list.
NAVERA's tools use the *nearest-rank* rule:

```python
def pct(v, q):                                   # navera_tools/evaluate_session.py
    s = sorted(v)
    return s[min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1))))]
```

Look how VALIDATION_STATUS.md reports the night-vision result in the simulator: *"290 matches, median
6 m, p90 11 m, max 37 m"*. Three numbers and a count: you know the typical case, the bad case, the worst
case, and how much data is behind them.

> [!TIP]
> The **max** matters more than you think. In lesson 30's example, a change moves the median from 3.3 m
> to 3.1 m (nothing) — and the max from 151 m to 11 m. For an autopilot, one 151 m jump can be the crash.

## 3. Availability: a position you don't get is not 0 m

A system that answers only when it is sure can show a beautiful median… computed on the 10 % of the
time it answered. So the second big number is **availability**: the percentage of time with a usable
position (in NAVERA: state FIX or DEGRADED, with a position).

NAVERA learned this the hard way. VALIDATION_STATUS.md (**simulator only**): with a 3 s freshness window
for day vision, under load, *NAVERA alternated FIX / NO_FIX on 20–60 % of samples and the autopilot
landed during a 6.7–9.2 s gap*. Every single fix was accurate; the system as a whole was not usable.
The window became 5 s.

Always report accuracy **and** availability, measured over the same period.

## 4. Compared with what? The baseline

Here is the most important idea of the lesson. A method is only useful if it beats the **simplest
thing you could do instead** — the **baseline**.

For navigation without GPS, the simplest thing is: **repeat the last known position**. The vehicle
moves, so the error of this baseline grows with time — at 15 m/s, about 900 m after a minute. Any
vision method must beat *that*, or it is worse than doing nothing.

![The baseline grows with time](assets/baseline.svg)

That sounds easy. It is not. Read this table from VALIDATION_STATUS.md (33 labelled replay frames,
search limited to 600 m around the previous true position):

| Method | Median error | Within 300 m |
|---|---|---|
| DINOv2 tile retrieval (the former day vision) | 442 m | 41 % |
| Random tile in the same circle (**baseline**) | 536 m | 17 % |
| Repeating the previous position (**baseline**) | 480 m | 31 % |
| Best tile available (resolution limit) | 107 m | 94 % |

A deep neural network, a database of 1120 tiles, GPU time… and the median beats "repeat the previous
position" by **38 metres**. The conclusion written in the document is honest: *"the retrieval method
must not be relied on as a GPS replacement"*. It was replaced by local feature matching — *32/33 frames
within 9 m, median 4 m* on the same benchmark (aerial frames from another source, **not yet NAVERA's
camera**). Without the baseline rows, 442 m might have looked "not bad".

## 5. Small samples

33 frames is not many. If 1 more frame had failed, "32/33" would be "31/33" — a 3 % change from one
frame. With few samples:

- give the **count** with every number ("32 of 33", "n = 60");
- prefer the median and the count within a threshold to the mean;
- don't compare 4.1 m with 4.3 m: the difference is noise;
- never extrapolate: 60 s of one flight says nothing about a 2-hour mission over different ground.

## 6. Simulation is not reality

A simulator is a wonderful **behaviour** test (does NAVERA switch? does the autopilot keep flying?). It
is a weak **accuracy** test, because the simulator decides the errors. In NAVERA's simulator the camera
images are cut from the very map vision matches against, the ground is flat, the GPS noise is a formula.
VALIDATION_STATUS.md labels every such number **"simulator only"** or **"optimistic"**, and lists as
*known limitation 1*: *"Accuracy is not established on real data. No real flight has been recorded with
camera, GPS and IMU together."*

So when you write a result, always say **where** it was measured: *on the bench*, *in simulation*, *on
synthetic data*, *in flight*. The same "6 m median" means very different things.

## 🐦 How birds do it

Ornithologists measure bird journeys with the same honesty problems you met in this lesson.

**Rings.** Since 1899, when the Danish teacher Hans Christian Mortensen ringed starlings, scientists
have put small numbered rings on birds' legs. But only a small fraction of ringed birds are ever
found and reported again. A ring that never comes back is not a bird that went nowhere — it is
**missing data**, like a position you didn't get.

**Geolocators and GPS tags.** A geolocator is a tiny light logger: from the time of sunrise and
sunset it estimates the bird's position, but with errors that are often over 100 km. A GPS tag is
much more precise, but heavier. The tool decides the error bars.

Even so, the results are amazing. In 2010, Carsten Egevang and his colleagues fitted geolocators
to **Arctic terns** breeding in Greenland and Iceland. The birds flew to the seas around Antarctica
and back: on **average about 70,900 km per year**, the longest migration ever recorded at the time.
In 2022, a young **bar-tailed godwit** with a satellite tag flew **non-stop** from Alaska to
Tasmania: about **13,560 km in about 11 days**, without landing once.

**Compared with what?** In experiments, biologists always keep a **control group**: birds handled the
same way but not changed — same day, same release site. Perdeck's displaced starlings (lesson 23)
only mean something compared with the normal route of starlings that were not moved. That control
group is a **baseline**, exactly like the "before" column in NAVERA's measurements.

## 7. In NAVERA: `evaluate_session.py`

For real data, the product has its own tool. The recipe (`navera_tools/README.md`, *Measuring accuracy
on a real session*): enable **shadow mode** (vision runs even while GPS is valid), record a session
into a ROS 2 bag with `record_session.sh`, then:

```
python3 navera_tools/evaluate_session.py <bag dir> [--csv out.csv]
```

It uses the valid GPS fixes as the truth, interpolated at each vision measurement's instant, and prints
per source and mode: the count, **median / p90 / max**, the share **within 50 / 100 / 300 m**, and how
many frames gave no position. Then — lesson 26 — for sources that state a σ, how often the true error is
within 1σ, 2σ, 3σ (an honest σ gives ~39 / 86 / 99 %) and the σ that *would* be honest. The README ends
with the rule: *"Only numbers produced this way, on representative data, go into
docs/VALIDATION_STATUS.md."*

## Glossary

| Word | Meaning |
|---|---|
| **ground truth** | the true position, from the simulator or a better reference |
| **error** | distance between the estimate and the truth |
| **percentile (p90)** | the value below which 90 % of the sorted errors are |
| **availability** | the share of time with a usable position |
| **baseline** | the simplest alternative a method must beat (e.g. repeat the last position) |
| **sample size (n)** | how many measurements a number is computed from |
| **shadow mode** | vision runs while GPS is good, so it can be scored against GPS |
| **representative data** | data like the real use: the real camera, terrain, weather, vehicle |

## Check what you learned

<details><summary>1. Method A: median 5 m, available 30 % of the time. Method B: median 12 m, available 98 %. Which is better for an autopilot?</summary>
Probably B: 70 % of the time A gives nothing, and the autopilot loses its position. The question has no answer without both numbers — that is the point.
</details>

<details><summary>2. Why is "repeat the last position" a fair baseline for GPS-denied navigation?</summary>
It is what you get for free, with no sensor and no computation. A method that cannot beat it adds risk and cost for nothing.
</details>

<details><summary>3. A result says "median 4 m on 33 frames". What else do you want to know?</summary>
p90 and max (the bad cases), how many frames gave no position, where the frames come from (simulation, another camera, real flight), and the baseline on the same frames.
</details>

<details><summary>4. Your simulated flight shows vision at 12 m median. Can you write "NAVERA's day vision is accurate to 12 m"?</summary>
No: "12 m median on one simulated flight (n = …), simulated camera images cut from the same map — optimistic; not measured with a real camera."
</details>

Now open the **🛠️ Lab** tab.
