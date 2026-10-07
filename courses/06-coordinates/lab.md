# Lab 6 — From degrees to meters

**Goal:** write the four geography functions every navigation system needs — `distance()`, `bearing()`,
`to_local_xy()`, `from_local_xy()` — check them against NAVERA's own code, and measure the length of
the loop NAVERA's demo mission flies over Sousse.
**Time:** about 1 hour.

You work in two files: [geo_lab.py](file:./geo_lab.py) (the functions) and [answers.py](file:./answers.py)
(a short quiz). The other files (`route.py`, `compare_navera.py`, `route.csv`) are ready: they *use*
your functions.

## Step 1 — Run the starter

```bash
python3 geo_lab.py
```

You see a table of four places around Sousse, full of `TODO`. Each `TODO` is a function that still
returns `None` ("nothing"). Open [geo_lab.py](file:./geo_lab.py): at the top you find two constants,
`EARTH_RADIUS_M` and `M_PER_DEG`, then five functions with a `# TODO` comment and `return None`.
Your job is to replace each `return None` by real code.

> [!TIP]
> Before writing a formula, try it by hand in Python. Type `python3` in the terminal to open the
> interactive Python, then for example `import math` and `math.cos(math.radians(35.8))`. Type `exit()`
> to leave.

## Step 2 — distance()

`distance(lat1, lon1, lat2, lon2)` must return the great-circle distance in meters. Write the
haversine formula of the course, line by line:

1. convert `lat1`, `lat2`, `lat2 - lat1` and `lon2 - lon1` to radians (`math.radians`);
2. compute `a` (the long line with `sin` and `cos`);
3. return `2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))`.

Like NAVERA, use `min(1.0, a)` inside the `sqrt` to be safe.

> [!TASK]
> Finish **TODO 1** `distance()` in `geo_lab.py`. Done means: 0 m between a point and itself,
> ≈ 111 195 m for one degree of latitude, ≈ 18 229 m from the Ribat of Sousse to Monastir marina,
> the same result both ways.

Run the program again:

```bash
python3 geo_lab.py
```

The `distance (m)` column is filled. Port El Kantaoui marina should be about **8 262 m** away.

## Step 3 — bearing()

`bearing(lat1, lon1, lat2, lon2)` returns the direction from point 1 to point 2, in degrees,
clockwise from north, **between 0 and 360**. Use the three lines from the course (`y`, `x`, then
`atan2(y, x)`), convert the result to degrees with `math.degrees`, and finish with `% 360`.

> [!WARNING]
> `math.atan2(y, x)` takes the **east** part (`y`) first. If you swap them, north and east are swapped:
> a point due east would come out at 0°.

Test it with points you can check in your head: from Sousse, a point 0.01° north should be at 0°,
0.01° east at 90°, 0.01° west at 270°. In the interactive Python (`python3`), type:

```python
from geo_lab import bearing
bearing(35.8277, 10.6388, 35.8277, 10.6288)
```

You should get about `270.0`. (`from geo_lab import bearing` loads your function from your file.
If you change the file, `exit()` and start `python3` again.)

> [!TASK]
> Finish **TODO 2** `bearing()`. Done means: 0 / 90 / 180 / 270 for points due north / east / south /
> west, ≈ 107.0° from the Ribat of Sousse to Monastir marina, ≈ 287.2° back, never negative.

## Step 4 — the local frame: to_local_xy() and from_local_xy()

Now take the **Ribat of Sousse** as home. `to_local_xy(lat, lon, home_lat, home_lon)` returns a pair
`(east, north)` in meters. Use `M_PER_DEG` (111 320) and the **cosine of the home latitude** for east.
Return the two numbers with `return east, north`.

`from_local_xy(east, north, home_lat, home_lon)` does the opposite and returns `(lat, lon)`.

```bash
python3 geo_lab.py
```

Check the table: Port El Kantaoui marina is at **east ≈ −3692 m, north ≈ 7403 m** (west and north of
the Ribat: does that match the map in your head?). The last lines show the point 1 km east of home:
the latitude must not change, the longitude grows by about 0.0111°.

> [!TASK]
> Finish **TODO 3** `to_local_xy()` and **TODO 4** `from_local_xy()`. Done means: home is (0, 0),
> 0.01° north is 1113.2 m north, 0.01° east is ≈ 902.6 m east, and going to the local frame and
> back gives the same point again (to the millimeter).

## Step 5 — compare with NAVERA

Your functions should give the same answers as NAVERA's. The script `compare_navera.py` imports
NAVERA's `haversine_m()` (from `navera_common/geo.py`) and `_en()` / `_move()` (from
`day_pkg/vision_nav.py`) and prints both side by side:

```bash
python3 compare_navera.py
```

The `difference` column should be `0.000` everywhere, and the local-frame numbers identical. If not,
read NAVERA's version and find what differs from yours:

```bash
cat ~/navera/navera_common/navera_common/geo.py
```

> [!QUESTION]
> In the same file, read `is_finite_latlon()`. It refuses `(0, 0)` even though it is a valid position
> on Earth. Find (0°, 0°) on the globe in the course: what is there? Why would a sensor send exactly
> (0, 0)? You will answer this in the quiz.

## Step 6 — the length of a route

Open [route.csv](file:./route.csv). It is the loop of `navera_tools/demo_mission.py`, the route NAVERA's
demonstration flies over Sousse, with the start written again at the end to close the loop. Like in
lesson 4, each row is a `name,lat,lon`.

`route_length(points)` receives a **list of (lat, lon) pairs** and must return the sum of the distances
of all the legs: point 0 → 1, 1 → 2, … , last-but-one → last. A `for` loop over the indexes
`range(len(points) - 1)` does it. With one point (or none) there is no leg: the answer is 0.

> [!TASK]
> Finish **TODO 5** `route_length()`, then run `python3 route.py`. Done means: the total is
> ≈ 14 198.7 m (14.2 km), and the program saves `route.png`.

```bash
python3 route.py
```

You see each leg with its length and bearing, then the total and the flight time at 20 m/s. Click
**route.png** in the file list to see the loop drawn in meters around the start point. Look at the
bearings: does the drawing turn the way the numbers say (322° = towards the north-west…)?

## Step 7 — the quiz

Open [answers.py](file:./answers.py) and answer the three questions (Q1 is a number in **kilometers**;
you can compute it in `python3`).

> [!TASK]
> Answer Q1, Q2 and Q3 in `answers.py` and save.

Press **✔ Check my work**. Every red line comes with a hint; fix, save and check again.

## Going further (optional)

- **Flat or round?** In the interactive Python, compute the Sousse → Monastir marina distance twice:
  with your `distance()`, and with Pythagoras on the `(east, north)` of `to_local_xy()`
  (`math.hypot(east, north)`). How many meters apart are they? Try a far place, Tunis
  (36.8065, 10.1815), then Paris (48.8566, 2.3522). When does the flat frame become a bad idea?
- **Dead reckoning.** NAVERA's `dead_reckon(lat, lon, heading_deg, speed_mps, dt_s)` in `geo.py`
  answers: "flying on this heading at this speed for this time, where am I?". Import it
  (`from navera_common.geo import dead_reckon`), fly from the Ribat of Sousse on bearing 107° at 20 m/s
  for 900 s, and check with your `distance()` and `bearing()` where you land. How close are you to
  Monastir marina?
- **Your own route.** Add a few points of your own neighbourhood to a copy of `route.csv`
  (find the coordinates with a map application) and change `route.py` to read your file.
