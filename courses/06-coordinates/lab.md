# Lab 6 — Audit a long route, then survey the real Earth

**Goal:** write the geodesy part of NAVERA Lite (`navera_lite/geo.py`), use it to reproduce NAVERA's two
long-route bugs (R-6, R-2), check your ellipsoid code against an independent method, measure how far the
flat shortcut can be trusted, and write a short audit memo.
**Time:** 3 to 5 h (a strong programmer: about 2 h 30; 5 h if numpy or trigonometry is rusty).
**Fast track:** if you know numpy, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further" at the end.

Your files (📝 Code tab): [navera_lite/geo.py](file:./navera_lite/geo.py) (**your code**: twelve functions,
`TODO 1–12`), [error_study.py](file:./error_study.py) (**your code**: `TODO A`), [answers.py](file:./answers.py),
[report.md](file:./report.md), and three ready-made tools you only run: [run_geo.py](file:./run_geo.py) (runs
your functions on the lab's situations and draws them), [compare_oracle.py](file:./compare_oracle.py) and
[geodesic_ref.py](file:./geodesic_ref.py) (Vincenty's ellipsoid formula, an independent method).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1–§2 positions, flat shortcut | Step 1 | `enu_flat`, `offset` |
| §3 the sphere | Steps 2–3 | `haversine_m`, `bearing_deg`; the R-6 audit |
| §4 great circles | Step 4 | `great_circle_points`, `max_offset_km`; the R-2 audit |
| §5 WGS84 | Step 5 | `radii` |
| §6 ECEF | Step 6 | `geodetic_to_ecef`, `ecef_to_geodetic` |
| §7–§8 ENU, heights | Step 7 | `enu_matrix`, `geodetic_to_enu`, `enu_to_geodetic` |
| all | Steps 8–10 | the oracle, `worst_flat_error_m` (TODO A), the audit memo |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each function's docstring says its goal and gives one example with its
> result; `python3 run_geo.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — Navigator (about 1 h 45; 2 h 30 if numpy is new to you)

## Step 0 — Which way to Tunisia?

No code. Take a plain map whose x axis is the longitude and y axis the latitude. Draw a straight line
from Paris (48.85° N, 2.35° E) to central Tunisia (33.84° N, 9.40° E). A vehicle flies the **shortest**
path between the two.

> [!TASK]
> **Predict** (`PREDICT_ROUTE` in `answers.py`): does the shortest path pass east or west of your line,
> and how far from it at most (km)? Save the file (`Ctrl+S`). Then read lesson §1–§4.

## Step 1 — Metres from degrees (TODO 1, TODO 2)

Open the 📝 Code tab, then `navera_lite/geo.py`. The top of the file holds the constants
(`EARTH_RADIUS_M`, `WGS84_A`…) and two given functions (`is_finite_latlon`, `unit_vector`). Each `TODO`
function keeps its docstring and ends with `return None   # TODO…`: replace that line with your code.

<details><summary>🧰 Python: tuples, unpacking, the % operator</summary>

```python
def swap(p):                      # p is a tuple (a, b)
    return p[1], p[0]             # return two values = one tuple
x, y = swap((3.0, 4.0))           # unpacking: x = 4.0, y = 3.0
args = (1.0, 2.0)
print(max(*args))                 # * spreads a tuple into separate arguments: max(1.0, 2.0)
print(-7 % 5, 370 % 360)          # 3 10 — in Python, % with a positive right side is never negative
```
</details>

**TODO 1** `enu_flat(lat0, lon0, lat, lon)`: lesson §2, with the mean latitude and the date-line rule
of §1. **TODO 2** `offset(lat, lon, e_m, n_m)`: the inverse. Solve your two formulas for the new
latitude and longitude; the new latitude comes first, because the mean latitude needs it. Bring the new
longitude back into [−180°, 180°) with the rule of §1.

```bash
python3 run_geo.py test
```

The TODO 1 and TODO 2 lines must be ✔, including the two date-line lines (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. Convert every angle difference to radians before multiplying by `EARTH_RADIUS_M`; use
   `math.radians`, never `* 3.14 / 180`.
2. east 171 638.9 instead of 176 585.4: you used cos of the **start** latitude. 274 803.0: `math.cos`
   got degrees. north −16 888 246.8: Δφ is still in degrees. Tens of thousands of km EAST for a point to the
   WEST (the "WEST across ±180°" line): your wrap is `% 360` only; the rule of §1 is
   `(Δλ + 180) % 360 − 180`.
3. offset gives (−33.924586, 18.424289): you added metres / R (radians) straight to degrees — wrap it in
   `math.degrees(…)`. Latitude unchanged (−33.9249): `math.radians` instead of `math.degrees`.
   18.434938 instead of 18.434937 (the 7th decimal): your cos uses the old latitude only; enu_flat uses
   the mean of the two, so the inverse must too. 180.034966 or 179.990785 on the date-line line: the new
   longitude is not brought back into [−180°, 180°).
4. Check the inverse yourself, in both directions:
   `python3 -c "from navera_lite.geo import *; print(enu_flat(10, 20, *offset(10, 20, 500.0, -300.0)), enu_flat(10, 20, *offset(10, 20, -500.0, 300.0)))"`
   must print (500.0, −300.0) and (−500.0, 300.0) to rounding.
</details>

## Step 2 — Distance and bearing (TODO 3, TODO 4)

<details><summary>🧰 numpy instead of math: one formula for one number or a whole column</summary>

```python
import math
import numpy as np
x = np.array([0.0, 30.0, 90.0])
np.sin(np.radians(x))              # array([0. , 0.5, 1. ]) — math.sin(x) would raise TypeError
np.minimum(1.0, np.array([0.5, 1.0000000002]))   # array([0.5, 1. ]) — min() cannot do that
np.arcsin(0.5), np.sqrt(4.0)       # also work on plain numbers: 0.5236 and 2.0
float(np.sqrt(4.0))                # 2.0 as a plain Python float
```
</details>

**TODO 3** `haversine_m`: lesson §3, written with `np.` functions so that it works on numbers **and**
arrays (Step 4 needs that). Mission 04 gave you a finished `haversine_m` in `logbook.py`: write yours
from the lesson's formula without opening it, then compare the two in "Going further". **TODO 4**
`bearing_deg`: lesson §3 (plain `math` is fine here).

```bash
python3 run_geo.py test
```

```bash
python3 run_geo.py bearings
```

The first table is a sanity check: north, east, south, west from Geneva. (89.996°, not exactly 90°:
the great circle towards a point due east starts slightly north of east, lesson §3.) The second shows a
long flight out and back: the two take-off bearings are not 180° apart.

> [!TASK]
> With your `bearing_deg` (a `python3 -c "…"` line or a short script), on NAVERA's route Paris
> (48.8534951, 2.3483915) → central Tunisia (33.8439408, 9.400138): the **departure** heading, and the
> **arrival** heading (the bearing from Tunisia back to Paris, turned around by 180°). Write
> `TURN_DEG` = arrival − departure (two decimals, with its sign) and `EXPLAIN_BEARING`: why does a
> great-circle flight change heading, and why to the right here?

<details><summary>Stuck? Hints</summary>

1. `TypeError: only length-1 arrays…` in the array line: you used `math.sin` / `min`; use `np.sin`,
   `np.cos`, `np.arcsin`, `np.sqrt`, `np.minimum`.
2. 171 778.0 instead of 343 556.1: the factor 2 of `2 R asin(√a)` is missing. 615 391.4: the `/2` inside
   sin² is missing.
3. Bearing 301.884 instead of 148.12: `atan2(north, east)` — east goes first. −58.12: that mistake and a
   missing `% 360` together. 2.585: still radians,
   apply `math.degrees`. Negative bearings in `bearings`: add `% 360`.
4. TURN_DEG about 184.7: the bearing Tunisia → Paris points back north; add 180° (and `% 360`) to get
   the heading you arrive with.
</details>

## Step 3 — Audit 1: the route length (R-6)

NAVERA's server said the Paris → central Tunisia route was 1 750 km; the great circle is 1 768 km. The
runner computes the length three ways: flat with cos of the **start** latitude, flat with your `enu_flat`
(mean latitude), and the great circle with your `haversine_m`.

> [!TASK]
> **Predict** (`PREDICT_COS`), on paper, before running: by how many km will the start-latitude version
> and the mean-latitude version miss the 1 768 km? Two numbers. (London → Paris in lesson §2 gives you
> the ratios for a 344 km route spanning 2.65° of latitude; this one spans 15°.)

```bash
python3 run_geo.py cos
```

> [!TASK]
> Write `ROUTE_FLAT_START_KM` and `ROUTE_GC_KM` (one decimal) and `EXPLAIN_COS`: which version comes
> closest to the server's 1 750 km, and why does the mean latitude do better?

<details><summary>Why not exactly 1 750? (open after you wrote EXPLAIN_COS)</summary>
The closest is about 3 km below 1 750: the same formula with the constant 111 320 m per degree of lesson §5
gives 1 748.9 km, and the server's exact end points are not recorded. 3 km is small next to the 21 km bug.
</details>

## Step 4 — Audit 2: the corridor (R-2) (TODO 5, TODO 6)

**TODO 5** `great_circle_points(p1, p2, n)`: lesson §4 (unit vectors, the angle d, the slerp, back to
degrees). The first and last points are exactly `p1` and `p2`. `n < 2` → `raise ValueError("…")`.

<details><summary>🧰 numpy vectors</summary>

```python
a = np.array([1.0, 0.0, 0.0]); b = np.array([0.0, 1.0, 0.0])
a @ b                              # 0.0, the dot product (a · b)
0.5 * a + 0.5 * b                  # array([0.5, 0.5, 0. ]) — vectors scale and add element by element
v = 0.5 * a + 0.5 * b; v[2]        # 0.0, the z component
k / (n - 1)                        # for k in range(n): 0, …, 1 — n points including both ends
```
</details>

<details><summary>Stuck? Hints for TODO 5</summary>

1. `a = unit_vector(*p1)`, same for b; `d = math.acos(a @ b)`; then a loop over k with `f = k / (n − 1)`.
2. The middle point (0, 30) instead of (0, 45) on the equator: `f = k / n` never reaches 1; use `n − 1`.
3. (0, 0.785398) on the equator, or a middle point near (0.88, 0.02): radians — `atan2` returns radians;
   wrap lat and lon in `math.degrees(…)`.
4. London → Paris middle point (50.182, 1.1122): that is the straight line, you interpolated the angles;
   interpolate the **vectors** with the slerp of §4. (50.1942, 1.1466): the latitude must be
   `atan2(z, √(x² + y²))`, not `atan2(z, x)`.
</details>

**TODO 6** `max_offset_km(p1, p2)`: the least guided function. Its docstring gives the exact definition:
read it twice. First work it by hand on a tiny case: on a 3 × 4 table of distances (3 great-circle
points, 4 line points), which number do you keep from each row, and which one at the end?

<details><summary>Answer to the tiny case (open after you tried)</summary>
For each ROW (one great-circle point) keep its SMALLEST distance: the nearest line point. That gives 3
numbers; keep the LARGEST of them. In numpy: <code>table.min(axis=1).max()</code>. A double <code>for</code> loop over
the two lists of points also passes the check; broadcasting is just faster.
</details>

<details><summary>🧰 broadcasting: every pair at once</summary>

```python
col = np.array([[0.0], [10.0], [20.0]])        # shape (3, 1): a column
row = np.array([[1.0, 2.0, 3.0, 4.0]])         # shape (1, 4): a row
t = np.abs(col - row)                          # shape (3, 4): every column value against every row value
t.min(axis=1)                                  # array([ 1.,  6., 16.]) — smallest of each ROW
t.min(axis=1).max()                            # 16.0
x = np.linspace(0.0, 1.0, 5)                   # array([0.  , 0.25, 0.5 , 0.75, 1.  ])
pts = np.array([(1.0, 2.0), (3.0, 4.0)]); pts[:, 0]   # array([1., 3.]) — the first column
pts[:, 0][:, None]                             # shape (2, 1): the same values as a column
```

Your `haversine_m` broadcasts the same way: a (101, 1) column of latitudes/longitudes against a
(1, 1001) row gives a (101, 1001) table of distances.
</details>

```bash
python3 run_geo.py route
```

Open `out/route.png` and compare with your `PREDICT_ROUTE`.

> [!TASK]
> **Predict** (`PREDICT_LEG`), before you read the last line of the output: the offset of a great circle
> from its lat/lon chord grows like the square of its length. From your max offset and the route length
> (1 768 km), how many metres for the 10 km leg in the middle of the route?
>
> Then write `OFFSET_KM` (km) and `LEG_OFFSET_M` (metres, from the run), and
> `EXPLAIN_ROUTE`: which side does the great circle pass, what did it mean for a ±1 km corridor, and
> why do ≤ 10 km great-circle legs fix it?

<details><summary>Stuck? Hints for TODO 6</summary>

1. 101 points from your `great_circle_points`; 1001 line points with `np.linspace(0, 1, 1001)`:
   `lat = p1[0] + f * (p2[0] − p1[0])`, same for the longitude.
2. 2.558 instead of 2.48 on London → Paris: you compared points at the **same fraction** (point k with
   point k); the definition wants the **nearest** line point for each great-circle point.
   2.984: you took `min(axis=0)` (nearest great-circle point for each line point): wrong direction.
3. About 0: your TODO 5 still draws the straight line. 2 480: metres, divide by 1000.
4. The last line can be `return float(table.min(axis=1).max()) / 1000.0`.
</details>

> [!TIP] 🏅 End of session 1 — Navigator
> Press **✔ Check my work**. When the checks of TODO 1–6 and Steps 2–4 pass (checks 1–9; the others are
> session 2), you earn the **Navigator** badge. If the class session ends here, stop here.

## Session 2 — Surveyor (about 2 h; 2 h 30 if numpy is new to you)

Read lesson §5–§8 first.

## Step 5 — The radii of the ellipsoid (TODO 7)

**TODO 7** `radii(lat)`: M and N of lesson §5, in that order. Run the test; the two `radii` lines must be ✔.

```bash
python3 run_geo.py test
```

> [!TASK]
> With your `radii` (in `python3`, or a short script):
> 1. `KM_PER_DEG_LON_ANCHORAGE`: 1° of longitude at Anchorage (61.2181°), in km, three decimals.
> 2. `SCALE_NORTH_ZERO_LAT_DEG`: the 111 320 m-per-degree shortcut of lesson §5 is 0.33 % too long for
>    north distances at Sousse and too short near the poles. At which latitude is it exactly right
>    (M·π/180 = 111 320 m)? Find it with a loop or a bisection, two decimals.

<details><summary>Stuck? Hints</summary>

1. `python3 -c "from navera_lite.geo import radii; print(radii(61.2181))"` prints (M, N) in metres.
2. 6 347 285 for M at −41.3°, or a wrong M at 45° only: `math.sin` got degrees. (6 378 137.0, 6 335 439.3)
   at 0°: M and N are swapped.
3. 1° of longitude = N · cos φ · π/180 with φ in radians: at Anchorage between 50 and 60 km. A negative
   number: `math.cos` got degrees.
4. The zero: M grows from the equator to the pole, so `for lat in np.arange(0, 90, 0.001)` and stop at the
   first M·π/180 ≥ 111 320 works; bisection is faster.
</details>

## Step 6 — ECEF and back (TODO 8, TODO 9)

**TODO 8** `geodetic_to_ecef(lat, lon, h=0.0)`: lesson §6. **TODO 9** `ecef_to_geodetic(x, y, z)`: the
iteration of §6; keep `lat` in **degrees** between iterations (because `radii` takes degrees), radians
only inside `sin`, `cos`, `atan2`. Ten iterations are plenty; recompute h with the final latitude.

```bash
python3 run_geo.py test
```

```bash
python3 run_geo.py ecef
```

`ecef` makes round trips for six places, from 400 m below sea level to an airliner at 11 km: the worst
must be below 1 mm.

> [!TASK]
> `GEOCENTRIC_DIFF_DEG`: for a surface point at latitude 30° (h = 0), the geodetic latitude minus the
> geocentric one (the angle seen from the centre, `atan2(Z, √(X² + Y²))`, lesson §5), in degrees, four
> decimals. Then `GEOCENTRIC_MAX_AT_DEG`: with a loop over latitudes, where is this difference largest?
> `EXPLAIN_GEOCENTRIC`: why there? (Think of where the two angles must agree.) Bonus: derive the exact
> latitude from tan ψ = (1 − e²) tan φ, ψ the geocentric latitude.

<details><summary>After you found it</summary>
Not exactly 45°: the difference φ − ψ is largest where tan φ = 1/√(1 − e²), φ = 45.096°. A loop with a
0.01° step finds 45.10°. The two angles agree at the equator and at the poles, so the maximum is near, but
not at, the middle.
</details>

<details><summary>Stuck? Hints</summary>

1. `TypeError: can only concatenate tuple (not "float") to tuple`: `radii()` returns two numbers (M, N);
   keep only N with `_, n = radii(lat)`.
2. Z wrong but X and Y right: Z uses `N·(1 − e²) + h`.
3. A wrong height on the 60° test line (about 16 084 m if lat stays in radians through the loop, 19.3 m if
   only the call to `radii()` gets radians, instead of 100 m; Singapore 26.9 m instead of 15.02 m), or round
   trips of ~100 m to kilometres in `ecef`: radians given to `radii()` (it takes degrees), or degrees given
   to `math.cos`. Near the equator the mistake is much smaller: look at the 60° line.
4. Round trips of 0.6 mm to 0.4 m, or 99.997 m on the 60° line: too few iterations.
</details>

## Step 7 — The local frame (TODO 10–12) and heights

**TODO 10** `enu_matrix(lat0, lon0)`: the rows E, N, U of lesson §7, as `np.array([[…], […], […]])`.
**TODO 11** `geodetic_to_enu`: ECEF of both points **as numpy arrays**, the difference, then `R @ d`;
return three floats. **TODO 12** `enu_to_geodetic`: `X = X0 + R.T @ np.array([e, n, u])`, then your
`ecef_to_geodetic` with three floats (`float(X[0])`…).

> [!TASK]
> **Predict** (`PREDICT_DROP`): Tallinn and Helsinki are both at sea level, 82 km apart across the Gulf of
> Finland. In Helsinki's ENU frame, what is Tallinn's `up`?

```bash
python3 run_geo.py test
```

```bash
python3 run_geo.py enu
```

> [!TASK]
> Write `DROP_M` (Tallinn's `up`, with its sign). Then heights (lesson §8, no code): a receiver says
> 312.4 m above mean sea level with a geoid separation of −28.6 m. Write `H_ELLIPSOID_M`.

<details><summary>Stuck? Hints</summary>

1. `TypeError: unsupported operand type(s) for -: 'tuple' and 'tuple'`: wrap each ECEF in `np.array(…)`.
2. `det(R) = −1`: two rows swapped (north first?) or a sign; R·Rᵀ not the identity: degrees in sin/cos.
3. The way back lands at (60.43, 26.10, −42 423 m): you used `R` instead of `R.T`.
</details>

## Step 8 — The oracle: an independent method

Your code passes its own examples, but you wrote both the code and the examples' interpretation. An
**oracle** is an answer you did not compute: here Vincenty's ellipsoid formula (`geodesic_ref.py`,
written from the published 1975 formula), and pyproj, the library behind most GIS software, if this
computer has it.

> [!TASK]
> **Predict** (`PREDICT_SPHERE`) from your `radii(0.0)` alone: by how many %, and with which signs, will
> the sphere (6 371 km) be wrong 100 km due north and 100 km due east of Quito?

```bash
python3 compare_oracle.py
```

Part 1 measures your sphere against the ellipsoid, 100 km north and east of three places. Part 2 checks
your exact ENU against Vincenty, in distance **and** direction. The directions must agree: swapped or
reversed East/North axes fail here; a last line checks that Up points up. The distances agree to millimetres
up to a few km, then drift apart (4 mm at 10 km, 0.5 m at 50 km). That is not a bug: your ENU distance is
measured in the flat plane at home, Vincenty's along the curved ground. On a sphere a point at arc length s
is R·sin(s/R) from home in the plane, so the gap is about s³/(6R²) (sin x ≈ x − x³/6): check it at 50 km.
The last column, the height of the plane above the ground, is §7's d²/2R.

> [!TASK]
> Write `SPHERE_ERR_NORTH_PCT_QUITO` and `SPHERE_ERR_EAST_PCT_QUITO` (with their signs) and
> `EXPLAIN_SPHERE`: why is the sphere too long north–south and too short east–west at the equator?

## Step 9 — The error study (TODO A)

Your `enu_flat` (sphere, one cos) against your exact ENU (ellipsoid): how wrong is the flat shortcut at
10 m, 1 km, 100 km from home?

> [!TASK]
> **Predict** (`PREDICT_STUDY`) **before you write TODO A**: near home, does the error grow like d, d² or
> d³? At Sousse, at what distance will it reach 1 m?

**TODO A** `worst_flat_error_m(lat0, lon0, d_m)` in [error_study.py](file:./error_study.py): its docstring
defines the error exactly. Trace it by hand for one bearing first: for 90°, what are the true east and
north? Then test it on the two docstring examples. The first alone proves little: bearing 0° gives
the same sin and cos in degrees and in radians, and it is the first bearing of the loop.

```bash
python3 -c "import error_study as s; print(s.worst_flat_error_m(0.0, 0.0, 1000.0), s.worst_flat_error_m(-41.2865, 174.7762, 20000.0))"
```

It must print about 5.613 and 58.957. Then run the study (it repeats this self-test first):

```bash
python3 error_study.py
```

Open `out/error_study.png` (log–log axes: a line of slope 1 means error ∝ d, slope 2 means ∝ d²) and
`results.json`.

> [!TASK]
> Write `D_1M_SOUSSE_M` (`d_1m_m` of Sousse in results.json) and `EXPLAIN_STUDY`: what makes the error
> near home (look at the slope and at the size per km), and what takes over far away?

<details><summary>Read this after you wrote EXPLAIN_STUDY</summary>
Near home the flat shortcut's error grows <b>like the distance</b> (slope 1), not like its square: it is a
<b>scale</b> error, because <code>enu_flat</code> uses the sphere's 6 371 km where the ellipsoid has M and N
(0.22 % at Sousse, 0.56 % north–south on the equator). Curvature and the convergence of the meridians grow
like d² and take over beyond tens of kilometres (slope 2 at Sousse and Reykjavik; weak on the equator,
where the meridians are parallel; at Quito the far slope is even below 1, 0.88, because there the far-field
terms partly cancel the scale error instead of adding to it). A scale error cancels when the same function
converts both ways; it does not when metres are compared with real metres. Mission 01's jump gate is such a
case: it compares a distance with v_max × elapsed, real metres; 0.2 % of a 10 km gap is 20 m, almost half
of the 50 m margin.
</details>

<details><summary>Stuck? Hints</summary>

1. One loop over the 8 bearings, `range(0, 360, 45)`; a variable created **before** the loop keeps the
   largest error so far; return it **after** the loop.
2. Inside the loop: the true (e, n) from d and the bearing (radians!), as in lesson §3 (east = sin, north =
   cos); that point's (lat, lon) from your exact frame (`g.enu_to_geodetic`, up 0, home height 0); then
   what `g.enu_flat` says, seen from home.
3. 5.613 right but Wellington 24.645: only the first bearing counts — your `return` is inside the loop.
   Wellington 66.005: the bearing went to `math.sin` in degrees.
4. `math.hypot(dx, dy)` is the horizontal distance; keep the largest with `max(worst, …)`.
</details>

## Step 10 — The audit memo

Write [report.md](file:./report.md) (150–400 words, your own words, keep the three headings): the route
length bug and how you reproduced it, the corridor bug with your offset and leg numbers, and which model
to use where, from your error study. Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, at least 150 words, and quotes the route lengths (flat with
> cos(start) and great circle), the corridor offset, and where the flat shortcut reaches 1 m at Sousse.

## Step 11 — Check, then look back

Press **✔ Check my work**: it tests your functions on places and numbers they have never seen. When
every check passes, you earn the **Surveyor** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, why a ±1 km corridor around Paris → Tunisia missed the
   flown path, and how the fix works.
2. Which of your predictions was the most wrong? What did you assume?
3. Your flat frame is 0.2 % off near home. Name one NAVERA Lite computation where that cancels and one
   where it does not.

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Two haversines.** Compare your `geo.haversine_m` with mission 04's `logbook.haversine_m` on a few
  thousand random pairs (`np.random.default_rng(1).uniform(…)`). Largest difference? Two copies of one
  formula in a codebase can drift apart: which one should `logbook.py` use, and what test would catch a
  drift (mission 14)?
- **Bowring.** Write ECEF → geodetic with Bowring's one-step formula and compare it with your iteration
  from −500 m to 20 km of height. How large is the difference?
- **An ellipsoidal flat frame.** Write `enu_flat_wgs84` with M and N of the home latitude instead of
  `EARTH_RADIUS_M`, put it in `worst_flat_error_m`, and rerun the study. Where does it now reach 1 m at
  Sousse? What is left, and why does it grow like d²?
- **Rhumb line.** A ship holding a constant bearing follows a rhumb line, not a great circle. Plot the
  rhumb line Paris → Tunisia (a straight line on a Mercator map, mission 07) next to your two paths.
- **Antipodes.** What does your `great_circle_points` do for Quito → a point near its antipode? Why is
  there no unique shortest path?
