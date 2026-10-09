# Geodesy for navigation: WGS84, ECEF and ENU

> [!NOTE] In short
> - GPS and maps use degrees, but the flight controller needs metres, so NAVERA converts between
>   them every second.
> - You learn three ways to write one point: **geodetic** (lat, lon, height), **ECEF** (X, Y, Z
>   from the Earth's centre) and **ENU** (metres east, north, up from a home point).
> - The exact conversions use the WGS84 ellipsoid; the haversine (sphere) and the flat-Earth
>   formula are faster shortcuts.
> - The key question for an engineer: how big is the error of each shortcut?
> - In the lab you implement the conversions, check them against NAVERA's code, and measure the
>   error of the shortcuts around Sousse (Tunisia), NAVERA's test area.

A survey drone takes off from **Monastir** and flies up the coast towards **Sousse**, in Tunisia
(NAVERA's test map covers Sousse). Halfway, its GPS is jammed. NAVERA's camera matches the ground
with the on-board map and reports *"you are at 35.7960° N, 10.7250° E"*. The flight controller does not think in
degrees: it needs **metres** — how far to the next waypoint, in which direction, how fast the
drone drifts east. Every second, NAVERA converts between three ways of writing the same point:

1. **geodetic coordinates** (latitude, longitude, height) — what GPS and maps use;
2. **ECEF** — a Cartesian (X, Y, Z) frame fixed to the Earth, with its origin at the Earth's centre;
3. **ENU** — a local frame in metres: **E**ast, **N**orth, **U**p from a home point.

This lesson gives you the exact mathematics of these conversions on the **WGS84 ellipsoid**,
the spherical shortcuts (haversine, bearing) and the flat-Earth shortcut that NAVERA uses, and —
most important for an engineer — **how big the error of each shortcut is**.

## 1. Latitude, longitude and sign conventions

- **Latitude** φ: angle north (+) or south (−) of the equator, from −90° to +90°.
  Circles of equal latitude are **parallels**.
- **Longitude** λ: angle east (+) or west (−) of the **Greenwich meridian**, from −180° to +180°.
  Half-circles of equal longitude, from pole to pole, are **meridians**.

![Latitude, longitude and the length of one degree of longitude](assets/globe.svg)

Software writes positions in **decimal degrees**, latitude first: the Eiffel Tower in Paris is
(48.8584, 2.2945). Paris is north of the equator and east of Greenwich, so both numbers are
positive. Cape Town is (−33.9249, 18.4241): south of the equator, so its latitude is negative.
New York (40.7128, −74.0060) is west of Greenwich, so its longitude is negative. Old notation uses
degrees, minutes and seconds: 48° 51′ 30″ N = 48 + 51/60 + 30/3600 = 48.8583°.

> [!WARNING]
> **Order and units.** NAVERA always writes (lat, lon). GeoJSON and some web tools write
> (lon, lat): the Eiffel Tower written the wrong way round, (2.2945, 48.8584), falls in the Indian
> Ocean off the coast of Somalia, 6 800 km away. And Python's `math.sin`, `math.cos`, `math.tan` take
> **radians**: `math.cos(35.83)` is −0.294, not 0.811. Convert with `math.radians()` and back with `math.degrees()`.

> [!NOTE]
> **Null Island.** The point (0°, 0°) lies in the open Atlantic Ocean, in the Gulf of Guinea, about
> 600 km south of the coast of Ghana. There is no island there — only a weather buoy. Mapping
> people call it "Null Island" because it is where data with **missing coordinates** lands: a
> GPS receiver that has no fix yet, a variable left at its default value 0, a failed conversion.
> A drone over Sousse that suddenly "is" at (0, 0) has a software problem, not a 4 100 km jump. That is
> why NAVERA's `is_finite_latlon()` refuses exactly (0, 0) as well as NaN, infinity and out-of-range
> values.

**Precision of the number.** One degree of latitude is about 111 km, so the 5th decimal is about
1.1 m and the 7th about 1.1 cm. A Python `float` keeps about 15–16 significant digits: the
*number* is never the problem — the *measurement* is.

## 2. The shape of the Earth: the WGS84 ellipsoid

The Earth spins, so it is slightly flattened: the equatorial radius is 21 km longer than the polar
radius. GPS uses a reference **ellipsoid** (an ellipse rotated around the spin axis) called
**WGS84** (World Geodetic System 1984). It is defined by two exact numbers:

```
a = 6 378 137.0 m              semi-major axis (equatorial radius)
f = 1 / 298.257223563          flattening, f = (a − b) / a
```

and everything else follows:

```
b  = a (1 − f)        = 6 356 752.314 m     semi-minor axis (polar radius)
e² = f (2 − f)        = 0.00669438          first eccentricity squared, e² = (a² − b²) / a²
```

In `geo_lab.py` these are `WGS84_A`, `WGS84_F`, `WGS84_B` and `WGS84_E2`.

![A meridian cut through the WGS84 ellipsoid](assets/ellipsoid.svg)

On an ellipsoid, "latitude" needs a precise definition. The **geodetic latitude** φ (the one GPS
gives) is the angle between the **normal** to the ellipsoid at the point (the line perpendicular to
the surface, the direction a plumb line roughly follows) and the equatorial plane. It is *not* the
angle of the line to the Earth's centre (the **geocentric latitude**). At 45° the two differ by
0.19°: confusing them moves a point about 21 km north or south.

**Height.** GPS heights are measured along the normal, above the ellipsoid: the **ellipsoidal
height h**. The height on a road sign is above **mean sea level** (the **geoid**, an irregular
surface of equal gravity potential). The two differ by the **geoid separation**, which varies
between about −106 m and +85 m around the world. An NMEA receiver gives the altitude above mean
sea level *and* the separation; NAVERA's GPS node adds them to publish an ellipsoidal height.

### Radii of curvature: how long is a degree?

A sphere has one radius. An ellipsoid curves differently north–south and east–west, so at latitude
φ we need two **radii of curvature** (with w = 1 − e² sin²φ):

```
M(φ) = a (1 − e²) / w^1.5        meridian radius: curvature along the north-south direction
N(φ) = a / √w                    prime-vertical radius: curvature along the east-west direction
```

A small change of latitude dφ (in radians) is a ground distance M·dφ; a small change of longitude
dλ is N·cos φ·dλ (the parallel at latitude φ is a circle of radius N cos φ). So:

```
metres per degree of latitude  = M(φ) · π / 180
metres per degree of longitude = N(φ) · cos φ · π / 180
```

| Place | φ | M (km) | N (km) | 1° latitude | 1° longitude |
|---|---|---|---|---|---|
| Equator | 0° | 6335.4 | 6378.1 | 110.574 km | 111.319 km |
| Cape Town | −33.92° | 6355.3 | 6384.8 | 110.921 km | 92.466 km |
| Sousse (NAVERA's test area) | 35.83° | 6357.3 | 6385.5 | 110.956 km | 90.359 km |
| Rome | 41.89° | 6363.9 | 6387.7 | 111.071 km | 82.993 km |
| London | 51.51° | 6374.6 | 6391.3 | 111.258 km | 69.429 km |
| Reykjavik | 64.15° | 6387.3 | 6395.5 | 111.480 km | 48.675 km |
| North Pole | 90° | 6399.6 | 6399.6 | 111.694 km | 0 km |

Two things to notice. First, **longitude shrinks with cos φ**: in Sousse one degree east is
90.4 km, in London 69.4 km, in Reykjavik only 48.7 km. A program that forgets the cosine makes
east–west distances 23 % too long in Sousse and 129 % too long (more than double) in Reykjavik.
The sign of the latitude does not matter: Cape Town (34° S) and Sousse (36° N) have almost the same
values. Second, a degree of **latitude is not
constant**: 110.57 km at the equator, 111.69 km at the poles — because the ellipsoid is *flatter*
near the poles, its curvature radius M is *larger* there.

## 3. ECEF: a Cartesian frame for the whole Earth

**ECEF** (Earth-Centred, Earth-Fixed) puts the origin at the centre of the ellipsoid, the Z axis on
the spin axis (towards the North Pole), the X axis through (0°, 0°) and the Y axis through (0°, 90° E).
It rotates with the Earth, so a building has constant ECEF coordinates. Any point (φ, λ, h) is:

```
X = (N + h) cos φ cos λ
Y = (N + h) cos φ sin λ
Z = (N (1 − e²) + h) sin φ
```

Check: at (0°, 0°, 0 m), N = a, so X = a, Y = Z = 0. At the North Pole, Z = N(1 − e²) = b. ✔

**The inverse** (ECEF → φ, λ, h) has no simple closed form, but a fixed-point iteration converges
very fast:

```
λ = atan2(Y, X)
p = √(X² + Y²)                         distance from the spin axis
φ = atan2(Z, p (1 − e²))               first guess (exact for h = 0)
repeat:  N = N(φ);   h = p / cos φ − N;   φ = atan2(Z, p (1 − e² N / (N + h)))
```

Each iteration reduces the error by a factor of the order of e² ≈ 0.007, so 5–6 iterations give
sub-millimetre accuracy for any point near the Earth. (Closed-form solutions exist, for example
Bowring's method, but the iteration is easier to read and to test.) Because the formula divides by
cos φ, it would fail exactly at the poles — not a problem for our drones, which do not fly there. You do not need to prove
that the iteration converges: the lab checks it with a **round-trip test** (geodetic → ECEF →
geodetic must give back the same point to a millimetre).

## 4. ENU: the local tangent frame

For a vehicle, ECEF numbers are inconvenient: moving 10 m north changes X, Y *and* Z. We want a
frame attached to a **home point** (φ0, λ0, h0): x to the **east**, y to the **north**, z **up**
(along the ellipsoid normal). Its three unit vectors, written in ECEF, are:

```
E = (−sin λ0,          cos λ0,          0     )
N = (−sin φ0 cos λ0,  −sin φ0 sin λ0,   cos φ0)
U = ( cos φ0 cos λ0,   cos φ0 sin λ0,   sin φ0)
```

You can check them: U is the normal direction (the X, Y, Z formulas above without the radius); E is
horizontal (no Z part) and points towards increasing λ; N = U × E. Put them as the **rows** of a
3 × 3 matrix R. To express a point in ENU, take its ECEF position minus the home's ECEF position and
project it on each axis — a dot product with each row, which is a matrix product:

```
[e, n, u]ᵀ = R · (X − X0)                   R = [[E], [N], [U]]
```

R is a **rotation matrix**: its rows are orthonormal, so R·Rᵀ = I, det R = +1 and its inverse is its
transpose. The way back is therefore cheap:

```
X = X0 + Rᵀ · [e, n, u]ᵀ          then ECEF → (φ, λ, h) with the iteration above
```

![The local ENU frame is a tangent plane](assets/enu_frame.svg)

The ENU plane **touches** the Earth at home. A point on the ground d metres away is below the
plane: u ≈ −d² / (2R). That is −8 cm at 1 km, −7.8 m at 10 km, and −38 km for Rome seen from
Sousse. ENU is exact everywhere (it is just a rotation and a translation of ECEF), but its
horizontal (e, n) is a "flat picture" of a curved surface, so it is most meaningful near home.

### Worked example: Kairouan seen from Sousse

Home: Sousse (35.8277°, 10.6388°, h0 = 0). Target: the Great Mosque of Kairouan, inland
(35.6812°, 10.1036°, h = 100 m).

1. ECEF of Sousse: X0 = (5 088 219.3, 955 801.2, 3 712 708.0) m.
   ECEF of Kairouan: X = (5 106 355.9, 909 911.6, 3 699 575.1) m.
2. Difference: X − X0 = (18 136.6, −45 889.6, −13 132.9) m.
3. R at Sousse (rounded): E = (−0.1846, 0.9828, 0), N = (−0.5753, −0.1081, 0.8108),
   U = (0.7968, 0.1497, 0.5853).
4. e = E·(X − X0) = −48 449.1 m, n = N·(X − X0) = −16 122.6 m, u = U·(X − X0) = −104.2 m.

Kairouan is 48 km west and 16 km south of Sousse. Although the mosque is 100 m above the ellipsoid,
it is 104 m **below** Sousse's tangent plane: at 51 km, the curvature term d²/(2R) ≈ 205 m is larger
than its height. The horizontal ENU distance is √(e² + n²) = 51 061.3 m; the distance along the
ellipsoid (Vincenty's formula) is 51 061.0 m.

## 5. The spherical shortcuts: haversine and bearing

Many programs, NAVERA included, use a **sphere** of mean radius R = 6 371 000 m (`EARTH_RADIUS_M`)
for distances. The shortest path on a sphere follows a **great circle** (a circle whose centre is the
centre of the sphere). The central angle θ between two points satisfies the **haversine formula**
(hav θ = sin²(θ/2)):

```
a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)        all angles in radians
d = 2 · EARTH_RADIUS_M · asin(√a)
```

It is mathematically equal to the spherical law of cosines, cos θ = sin φ1 sin φ2 + cos φ1 cos φ2
cos Δλ, but numerically much better for short distances: for points 1 m apart, cos θ = 0.999999999999988
and `acos` of a number so close to 1 loses most of its digits; `asin` of a small number does not.

The **initial bearing** (direction to fly, clockwise from north) is the same idea as ENU. Put both
points on a unit sphere, rotate the target into the ENU frame of the start point: its east and north
components are

```
east  ∝ sin Δλ · cos φ2
north ∝ cos φ1 · sin φ2 − sin φ1 · cos φ2 · cos Δλ
bearing = atan2(east, north)   → degrees → % 360
```

`atan2(y, x)` returns the angle of the vector (x, y) in (−π, π], using the signs of both arguments
to choose the right quadrant. Mathematicians measure from the x axis counter-clockwise; navigators
measure from **north**, clockwise — so the east component goes **first**: `atan2(east, north)`.
`% 360` maps −90° to 270°.

From Sousse, Rome is at a bearing of **12.8°** (north-north-east) and 692.9 km away on the
sphere. The way back is **194.0°**, not 12.8° + 180° = 192.8°: on a great circle the bearing changes
along the way.

### How wrong is the sphere?

On the WGS84 ellipsoid, Sousse → Rome is **691.924 km**; the sphere says **692.906 km**,
0.98 km (0.14 %) too long. The reason is the radii table: at Sousse a north–south distance really
curves with M = 6357.3 km, but the sphere uses 6371 km — **0.22 % too large**. East–west
(N = 6385.5 km) the sphere is 0.23 % too small. (The route to Rome is not due north, and M grows on
the way, so the final error is a little smaller than 0.22 %.) So the haversine error depends on the
direction and on the latitude: about ±0.2 % around Sousse, but between −0.1 % and +0.6 % on the
equator, where M = 6335.4 km: **1 to 6 m per km**. It is fine for "how far is the next
waypoint"; it is not fine for surveying.

## 6. The flat-Earth shortcut and its error

Inside one city, the fastest conversion is to treat degrees as a flat grid with a constant scale.
This is what NAVERA's day vision does, with `M_PER_DEG = 111 320.0`:

```
east  = (λ − λ0) · M_PER_DEG · cos φ0
north = (φ − φ0) · M_PER_DEG
```

and the inverse (`flat_move` in the lab, `_move` in NAVERA) divides instead of multiplying. It has
two kinds of error:

1. **Scale error (first order, proportional to distance).** 111 320 m is a·π/180, the length of a
   degree *of the equator*. At Sousse a degree of latitude is 110 956 m (M·π/180), so every
   north displacement is **0.33 % too long** — 3.3 m per km. East is almost right (−0.11 %), because
   N·π/180 ≈ 111 448 m is close to 111 320 m.
2. **Curvature and convergence of the meridians (second order, proportional to d²).** Using the
   cosine of the home latitude for all points ignores that meridians get closer as you go north:
   the east error is about e·n·tan φ0 / R (e, n: the east and north distances in metres). Example
   at Sousse (φ0 = 35.8°, tan φ0 = 0.722), a point 10 km east and 10 km north:
   `10 000 × 10 000 × 0.722 / 6 371 000 ≈ 11.3 m`. Twice farther (20 km, 20 km) gives four times
   more, 45 m: that is "proportional to d²". With the exact radii M and N instead of 111 320 m, this
   is all that remains: a few metres at 10 km (6.5 m at Sousse, in the worst direction).

In the lab you will measure both curves. For the worked example above, the flat formula puts
Kairouan at (−48 305, −16 308) m instead of (−48 449, −16 123) m: **235 m wrong** at 51 km.
A flat frame is a tool for a few kilometres, not for a flight across a whole country.

> [!TIP]
> **Python and numpy notes for this lab.**
> - A function can return several values as a **tuple**: `return east, north`. The caller
>   **unpacks** it: `e, n = flat_en(...)`. `m, n = radii(lat)` works the same way.
> - Variables created inside a function are **local**: they exist only during that call. The `p1`,
>   `p2`, `dl` of `haversine()` do not exist inside `bearing()`; each function computes its own.
>   Using one anyway gives `NameError: name 'dl' is not defined` (Python may then suggest a
>   similar name such as `'d'` — ignore the suggestion and define the variable).
> - Use the constant names of the file: the sphere radius is `EARTH_RADIUS_M`, not `R`.
> - A `*` in front of a tuple in a call **unpacks** it into separate arguments (lesson 3):
>   `ecef_to_geodetic(*x)` is `ecef_to_geodetic(x[0], x[1], x[2])`.
> - Tuples do not do arithmetic: `(1, 2) - (1, 1)` raises `TypeError: unsupported operand type(s)`.
>   Make numpy arrays, `np.array(geodetic_to_ecef(...))`, then `-` works element by element,
>   `R @ d` is the matrix–vector product and `R.T` is the transpose.
> - `ValueError: math domain error` means a function received a value outside its domain:
>   `math.asin(1.0000000002)` or `math.sqrt(-1e-12)`. In geodesy it comes from rounding (clip with
>   `min(1.0, a)`) or from degrees passed where radians were expected.

## 🐦 How birds do it

In the 1950s the Dutch biologist **Albert Perdeck** caught about 11 000 starlings that were
migrating through the Netherlands, flying west-south-west towards their winter quarters in
north-west France and southern England. He ringed them, transported them by plane to Switzerland,
and released them there (published 1958). Recoveries of the rings told the result:

| Birds | What they did | Interpretation |
|---|---|---|
| **Adults** | corrected towards the north-west, back to their usual winter area | they have a **map** (a sense of position) and a compass |
| **Juveniles**, first migration | kept flying west-south-west, parallel to their normal route, and wintered in southern France and Spain | they have only a **compass** and a programmed direction |

The young birds behaved like a vehicle with heading but no position: displaced sideways, they kept
the same bearing and missed by the size of the displacement. The adults behaved like a navigation
computer: they knew where they were and computed a **new bearing** to the goal.

Long-distance migrants face the same problem at a larger scale. **Bar-tailed godwits** fly from
Alaska to New Zealand in one non-stop flight of more than 11 000 km over the Pacific, and
**Arctic terns** travel between the Arctic and the Antarctic every year; satellite and geolocator
tracking studies have followed both across the globe. For trips of that length the difference between a flat map, a sphere and the real Earth is not
an academic detail. Navi, our swallow, prefers the version of the story where she knows her
position *and* the shape of the Earth.

## In NAVERA

NAVERA's real data — its satellite map, recorded frames and simulator area — cover **Sousse,
Tunisia**, where NAVERA is developed. The code below works the same anywhere on Earth; the lab uses
Sousse as home and a few places in Africa and Europe.

**`navera_common/navera_common/geo.py`** ([open it](file:navera/navera_common/navera_common/geo.py))
— the geodesy helpers shared by all localizers. They work on a sphere:

```python
EARTH_RADIUS_M = 6_371_000.0

def is_finite_latlon(lat, lon) -> bool:
    """True for a real, in-range position. Rejects None, NaN/inf and (0, 0)."""
    ...
    return not (lat == 0.0 and lon == 0.0)

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (spherical Earth, R = 6 371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))
```

`min(1.0, a)` protects `sqrt`/`asin` against rounding. The same file has `dead_reckon()`, the
inverse problem ("from here, on bearing h at speed v for t seconds, where am I?") on the same sphere.

**`day_pkg/day_pkg/vision_nav.py`** ([open it](file:navera/day_pkg/day_pkg/vision_nav.py)) — day
vision's flat shortcut:

```python
M_PER_DEG = 111_320.0

def _en(p, ref):
    """(east, north) metres of p from ref."""
    return ((p[1] - ref[1]) * M_PER_DEG * math.cos(math.radians(ref[0])), (p[0] - ref[0]) * M_PER_DEG)

def _move(p, de, dn):
    return (p[0] + dn / M_PER_DEG, p[1] + de / (M_PER_DEG * math.cos(math.radians(p[0]))))
```

Day vision measures its **velocity** from two map fixes with `_en()` (metres per second) and later
carries the position along that velocity with `_move()`, for example over the sea where the camera
finds nothing to match. Because the same constant is used in both directions, the 0.33 % scale
error **cancels** in the carried position; it only affects numbers expressed in metres, such as
the distance gates and the stated uncertainty. You will quantify this in the lab and decide whether
it matters.

**`gps_pkg/gps_pkg/nodes/gps_node.py`** — the GPS node publishes the height above the **WGS84
ellipsoid**: `fix.altitude = msl + geo_sep` (NMEA altitude above mean sea level plus the geoid
separation).

## Glossary

| Term | Meaning |
|---|---|
| **geodetic latitude φ** | angle between the ellipsoid normal and the equatorial plane |
| **longitude λ** | angle east (+) or west (−) of the Greenwich meridian |
| **ellipsoid, WGS84** | the reference shape of GPS: a = 6 378 137 m, f = 1/298.257223563 |
| **flattening f, eccentricity e²** | f = (a − b)/a; e² = f(2 − f) = 0.00669438 |
| **ellipsoidal height h** | height above the ellipsoid, along the normal (what GPS computes) |
| **geoid, mean sea level** | the surface heights on maps refer to; differs from the ellipsoid by up to ~100 m |
| **radius of curvature M, N** | meridian (north–south) and prime-vertical (east–west) radii at φ |
| **ECEF** | Earth-centred Earth-fixed Cartesian frame (X, Y, Z) in metres |
| **ENU** | local frame east, north, up at a home point; a rotation + translation of ECEF |
| **rotation matrix** | orthonormal matrix with det = +1; inverse = transpose |
| **great circle** | shortest path on a sphere; its centre is the sphere's centre |
| **haversine** | numerically stable formula for the great-circle distance |
| **bearing** | direction to a point, degrees clockwise from north, in [0, 360) |
| **Null Island** | the point (0°, 0°) in the Gulf of Guinea, where missing coordinates land |
| **scale error** | an error proportional to distance (a wrong constant); first order |

## Check what you learned

<details><summary>1. How many kilometres is 1° of longitude in Sousse and in London, and why do they differ?</summary>
N(φ)·cos φ·π/180: 90.4 km at Sousse (35.8°) and 69.4 km at London (51.5°). Parallels are
circles of radius N cos φ, which shrink as cos φ decreases away from the equator.
</details>

<details><summary>2. Why is the inverse of R simply its transpose, and why does it matter for enu_to_geodetic()?</summary>
The rows of R are orthonormal unit vectors (E, N, U), so R·Rᵀ = I. Inverting a general 3 × 3 matrix
costs more and loses precision; with a rotation, X = X0 + Rᵀ·[e, n, u] is exact and cheap.
</details>

<details><summary>3. Your function returns math.cos(35.83) = −0.294 for Sousse. What happened, and what would happen in asin?</summary>
The angle was passed in degrees; math.cos expects radians (use math.radians(35.83) → cos = 0.811).
With asin or sqrt, a wrong unit or rounding can give a value outside the domain and the error
"ValueError: math domain error".
</details>

<details><summary>4. A point 10 km from home is 7.8 m below the ENU plane. Is the ENU frame wrong?</summary>
No. ENU is an exact Cartesian frame (rotation of ECEF): the ground curves away from the tangent
plane by about d²/(2R). A program that assumes "ground = u = 0" far from home makes that error.
</details>

<details><summary>5. NAVERA's flat shortcut is 0.33 % too long in the north direction at Sousse. Give one case where it matters and one where it cancels.</summary>
It cancels when a velocity measured with _en() is applied with _move() (same constant both ways).
It matters when the result is compared with true metres: a distance gate, a stated uncertainty, a
speed from another sensor (airspeed, IMU) — about 3.3 m per km.
</details>

<details><summary>6. Why is the bearing from Rome back to Sousse (194.0°) not 12.8° + 180°?</summary>
A great circle is not a line of constant bearing: the direction relative to the local meridian
changes along the path, so the final bearing of A→B differs from the initial bearing of B→A + 180°.
</details>

Now open the **🛠️ Lab** tab.
