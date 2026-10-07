# Lab 6 — Geodetic, ECEF, ENU: implement, verify, measure the error

**Goal:** implement the WGS84 conversions geodetic ↔ ECEF ↔ ENU, the spherical haversine and
bearing, and NAVERA's flat shortcut; prove they agree with NAVERA's own code; then run an error
study around Sousse (NAVERA's test area) and write a short engineering report on how far the shortcuts can be trusted.
**Time:** about 3 hours.

Files in your lesson folder:

| File | Role |
|---|---|
| [geo_lab.py](file:./geo_lab.py) | **your work**: ten functions marked `TODO` |
| [compare_navera.py](file:./compare_navera.py) | compares your functions with NAVERA's (ready) |
| [error_study.py](file:./error_study.py) | the error study: writes `results.json` and `error_study.png` (ready) |
| [geodesic_ref.py](file:./geodesic_ref.py) | reference distance on the ellipsoid (Vincenty), used as "truth" (ready) |
| [report.md](file:./report.md) | **your work**: the written analysis |
| [answers.py](file:./answers.py) | **your work**: three quiz answers |

Conventions in `geo_lab.py`: angles in **degrees** at the interface, radians inside `math.sin/cos`;
heights in meters above the ellipsoid; several results are returned as a **tuple**
(`return x, y, z`) except the ENU vector, which is a numpy array.

## Step 1 — Run the starter

```bash
python3 geo_lab.py
```

Every value prints `TODO`. Read the top of the file: the constants `WGS84_A`, `WGS84_F`, `WGS84_B`,
`WGS84_E2`, `EARTH_RADIUS_M` and `M_PER_DEG`, then the ten functions. Below the line
`# ---- you don't need to change anything below this line ----` is the demo and the list `PLACES`
(Sousse, Monastir, Kairouan, Rome and the summit of Kilimanjaro).

> [!TIP]
> Test small pieces with `python3 -c "..."` (one command) or in the interactive interpreter
> (`python3`, then `from geo_lab import *`). After editing the file, start the interpreter again:
> an import is done only once per session.

## Step 2 — Radii of curvature (TODO 1)

Write `radii(lat)`: compute `w = 1 - WGS84_E2 * sin²(lat)` (latitude in radians!), then M and N
(course, section 2), and `return m, n`.

```bash
python3 -c "from geo_lab import radii; print(radii(0.0)); print(radii(35.8277))"
```

At the equator you must get (6 335 439.327, 6 378 137.0) — N equals a. At Sousse
(6 357 299.6, 6 385 464.5). Run `python3 geo_lab.py`: the first table now shows km per degree;
compare it with the table of the course.

## Step 3 — Geodetic ↔ ECEF (TODO 2 and TODO 3)

**TODO 2** `geodetic_to_ecef(lat, lon, h)`: the three formulas, with N from your `radii()`
(`_, n = radii(lat)` keeps only the second value). Return `x, y, z`.

**TODO 3** `ecef_to_geodetic(x, y, z)`: the iteration of the course. Keep `lat` in **degrees**
between iterations (because `radii()` takes degrees) and convert to radians only inside `cos` and
`atan2` calls. Six iterations are plenty; compute h once more with the final latitude.

```bash
python3 -c "from geo_lab import *; x = geodetic_to_ecef(-3.0674, 37.3556, 5895.0); print(x); print(ecef_to_geodetic(*x))"
```

The summit of Kilimanjaro (Tanzania, 5895 m) must give (5 067 349.7, 3 868 062.8, −339 332.2) and come
back as (−3.0674, 37.3556, 5895.0) to better than a millimeter. It is south of the equator, so Z is negative. `*x` unpacks the tuple into three
arguments (lesson 3): `ecef_to_geodetic(*x)` is `ecef_to_geodetic(x[0], x[1], x[2])`.

> [!WARNING]
> If the height comes back kilometers (or thousands of kilometers) wrong, a latitude was used in
> degrees inside `cos`, or in radians inside `radii()`. If you see `ZeroDivisionError`, the first guess or `cos(lat)`
> is wrong.

> [!TASK]
> **TODO 1–3 done** means: `radii()` returns (M, N) to 1 cm at 0°, 90° and Sousse;
> `geodetic_to_ecef()` gives (a, 0, 0) at (0°, 0°), (0, 0, b) at the pole and the Kilimanjaro
> values above; `ecef_to_geodetic()` inverts it to 10⁻⁸ degree and 1 mm, also for a point at
> 10 km height, a point below the ellipsoid (h = −45 m) and a point in the south-west quadrant.

## Step 4 — ENU (TODO 4, 5, 6)

**TODO 4** `enu_matrix(lat0, lon0)`: return `np.array([[...], [...], [...]])` whose rows are E, N, U.

**TODO 5** `geodetic_to_enu(lat, lon, h, lat0, lon0, h0)`: ECEF of both points as numpy arrays,
difference, then `enu_matrix(lat0, lon0) @ d`.

**TODO 6** `enu_to_geodetic(e, n, u, lat0, lon0, h0)`: `X = X0 + R.T @ np.array([e, n, u])`, then
your `ecef_to_geodetic()` (give it three floats: `float(X[0])`, …).

Reproduce the worked example of the course (Kairouan from Sousse):

```bash
python3 -c "from geo_lab import *; print(geodetic_to_enu(35.6812, 10.1036, 100.0, 35.8277, 10.6388, 0.0))"
```

Expected: about `[-48449.130 -16122.611 -104.248]` (numpy prints more digits). And back:

```bash
python3 -c "from geo_lab import *; print(enu_to_geodetic(-48449.130, -16122.611, -104.248, 35.8277, 10.6388, 0.0))"
```

> [!QUESTION]
> Check that your R is a rotation: in `python3`, `R = enu_matrix(35.8277, 10.6388)`, then
> `print(R @ R.T)` and `print(np.linalg.det(R))`. What do you expect? If the determinant is −1,
> which mistake gives that?

<details><summary>Answer to the question above</summary>
R·Rᵀ must print the identity matrix (with tiny numbers like 1e-17 instead of 0) and det R must be
+1. A determinant of −1 means a <b>reflection</b> (a mirror), not a rotation: two rows are in the
wrong order (for example east and north swapped) or one row has the wrong sign (for example
<code>-sin λ</code> written <code>sin λ</code>). R·Rᵀ is still the identity, so only the determinant shows the mistake.
</details>

> [!TASK]
> **TODO 4–6 done** means: R·Rᵀ = I and det R = +1, with the east and up rows of the course; the ENU
> of the origin is (0, 0, 0), a point 100 m above it has u = 100, Kairouan is at the values above
> (± 1 cm); ENU → geodetic → ENU returns the same vector to 1 mm.

## Step 5 — Haversine and bearing (TODO 7 and TODO 8)

**TODO 7** `haversine()`: the formula of the course with `EARTH_RADIUS_M` (that is the name in this
file) and `min(1.0, a)` before the square root.

**TODO 8** `bearing()`: it needs its **own** `p1`, `p2`, `dl` — the variables of `haversine()` are
local to that function. Then `atan2(east, north)`, `math.degrees`, `% 360`.

```bash
python3 -c "from geo_lab import *; print(haversine(35.8277, 10.6388, 41.8902, 12.4922), bearing(35.8277, 10.6388, 41.8902, 12.4922))"
```

Sousse → Rome: 692 906.0 m and 12.82°. Try the way back too (193.98°), and the four cardinal
directions: a point 0.01° north of Sousse must give 0°, 0.01° east 90°, and so on.

## Step 6 — NAVERA's flat shortcut and the comparison (TODO 9 and TODO 10)

**TODO 9** `flat_en(lat, lon, lat0, lon0)` and **TODO 10** `flat_move(lat, lon, de, dn)`: the
formulas of section 6 of the course. Read NAVERA's version first:

```bash
sed -n 25,37p ~/navera/day_pkg/day_pkg/vision_nav.py
```

Note one detail: `_move()` divides by the cosine of the **current** latitude `p[0]`, not of a fixed
home. Your `flat_move()` must do the same. Then compare everything:

```bash
python3 compare_navera.py
```

Part 1 must show differences of `0.000000` m; parts 2 and 3 identical numbers. Part 4 flies NAVERA's
spherical `dead_reckon()` 12 km towards Rome and measures the result with **your** exact ENU:
read how many meters the sphere loses or gains, and compare with the 0.22 % of the course.

> [!TASK]
> **TODO 7–10 done** means: `haversine()` equals NAVERA's `haversine_m()` (to 1 mm) and gives
> 692 906.0 m Sousse → Rome; `bearing()` gives 0/90/180/270 for due N/E/S/W, 12.82° and 193.98°
> for Sousse ↔ Rome; `flat_en()` and `flat_move()` equal NAVERA's `_en()` and `_move()`.

## Step 7 — The error study

Read the header of [error_study.py](file:./error_study.py): it explains the method. In short,
around Sousse, for 41 distances from 10 m to 300 km and 8 bearings, it places an exact point in the
ENU frame, converts it to (lat, lon) with **your** `enu_to_geodetic()`, and measures how far the
shortcuts put it. It also compares your `haversine()` with the ellipsoid distance.

```bash
python3 error_study.py
```

Open **error_study.png** (log–log axes). Look at the slopes: on a log–log plot, an error proportional
to d is a line of slope 1, an error proportional to d² a line of slope 2. Then open
[results.json](file:./results.json) and find `navera_flat_d_1m_m`, `navera_flat_d_10m_m`,
`wgs84_flat_d_1m_m` and the `sousse_rome` block.

> [!QUESTION]
> The NAVERA curve starts at 3.3 cm for 10 m. A curvature effect would be far smaller at 10 m
> (d²/(2R) ≈ 8 µm). So what is it? Compute 111 320 / (M·π/180) − 1 with the M of Sousse.

> [!TASK]
> `python3 error_study.py` runs without error and writes **results.json** and **error_study.png**.
> The check recomputes the expected values: if your functions are right, your results.json is right.

## Step 8 — The report

Write [report.md](file:./report.md) (150–400 words, your own words, keep the three headings):

- **## Method** — what is the reference ("truth"), what are the two shortcuts, what is measured.
- **## Results** — quote, in meters, the distance where NAVERA's flat error reaches **1 m** and
  **10 m** (`navera_flat_d_1m_m`, `navera_flat_d_10m_m`), the same 1 m distance for the WGS84-radii
  version, and the Sousse → Rome **difference** between sphere and ellipsoid (`difference_m`).
- **## Discussion** — where the NAVERA error comes from (scale or curvature? use the slopes); why
  it cancels when day vision measures a velocity with `_en()` and applies it with `_move()`, and
  where it does *not* cancel; whether the shortcut is acceptable for 2 km of dead-reckoning and for
  a 300 km survey flight with a single home point; what you would change in NAVERA and at what cost.

> [!TASK]
> report.md has the headings `## Method`, `## Results`, `## Discussion`, at least 150 words of your
> own, and quotes the three numbers (1 m distance, 10 m distance, Sousse–Rome difference in m).

## Step 9 — Quiz

Answer Q1–Q3 in [answers.py](file:./answers.py) (Q1 is a number in **kilometers**).

> [!TASK]
> Q1, Q2 and Q3 answered. Then press **✔ Check my work**. Every red line has a hint; fix, save, check again.

## Going further (optional)

- **Bowring's closed form.** Implement ECEF → geodetic with Bowring's formula (one step, no loop)
  and compare it with your iteration for heights from −500 m to 20 km. How large is the difference?
- **Ellipsoidal dead reckoning.** Write `destination(lat, lon, bearing, dist)` that walks in small
  ENU steps (re-centring the frame every 1 km) and compare its end point with NAVERA's spherical
  `dead_reckon()` for 50 km towards Rome (41.89° N, 12.49° E). Plot the difference against distance.
- **A better flat frame for NAVERA.** Write `flat_en_wgs84()` with M and N of the home latitude.
  Run the error study with it in place of `flat_en()`. What would the change cost per call (time it
  with `timeit`), and which NAVERA tests would you add before proposing it?
