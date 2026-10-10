# Lab 25 — The sky over Tenerife, and an honest look at night data

**Goal:** build the celestial chain yourself (Julian date → sidereal time → alt/az), check it
against astropy and NAVERA's `cn_pkg`, measure what clock and attitude errors cost a celestial fix
with a Monte Carlo on NAVERA's own solver; then re-implement the geometry of NAVERA's night
localizer (scale, coverage, minimum height, motion gate) and test whether the night replay frames
can be trusted.
**Time:** about 5 h for this lab, in **two sessions**: Part A (the sky, ~2 h 30) and Part B (night
vision, ~2 h), then the report (~30 min); about 7 h 30 for the whole mission with the lesson. The two parts are independent: you can
do Part B first.

| File | What you do |
|---|---|
| [stars.py](file:./stars.py) | Part A — TODO 1–3 and 5–8: the sky, Polaris, the error budget, the Monte Carlo (`visible_stars`, number 4, is given) |
| [thermal.py](file:./thermal.py) | Part B — TODO 10, 11, 13–15: night geometry, the motion gate, the data check (`parse_thermal_name` and `min_altitude`, numbers 9 and 12, are given) |
| [compare_navera.py](file:./compare_navera.py) | given: your coverage against NAVERA's `normalize_query` |
| [report.md](file:./report.md) | your written analysis (5 sections) |

Both programs write their numbers into `results.json`; the check reads it, and so should you when
you write the report.

> [!WARNING]
> Common errors in this lab: `math.sin` wants **radians** (use `np.radians` / `math.radians`);
> `math.sin` refuses numpy arrays (use `np.sin`); pictures read by OpenCV are **uint8**, so
> `255 - a` or `a * b` overflow unless you convert to float first.

## Part A — the sky

### Step 1 — The star catalogue

```bash
grep "Alp UMi" /data/bsc5.dat
```

This is Polaris (alpha of the Little Bear). In the middle of the line, `023148.7+891551` is its J2000
position: α = 02 h 31 min 48.7 s (1 h = 15°), δ = +89° 15′ 51″. A few columns later `2.02` is its
visual **magnitude** (smaller = brighter). `load_bright_stars()` at the bottom of `stars.py` reads
these fixed columns for you.

Run the program once before changing anything:

```bash
python3 stars.py
```

It stops at `(TODO 1 is not done yet)`. Read `offline_astropy()` at the bottom of the file: these
lines stop astropy from trying to download the IERS tables (there is no internet here, and none on
a drone). Keep them.

### Step 2 — The clock of the sky (TODO 1, 2)

> [!TASK]
> **TODO 1.** `julian_date(year, month, day, hour=0, minute=0, second=0.0)` with Meeus' algorithm
> (the comment above the function gives it). Use `math.floor`, not `int()` (they differ for
> negative numbers).
>
> **TODO 2.** `gmst_deg(jd)`: the IAU 1982 GMST formula, result in 0…360.

Test with the epoch J2000.0 (must be exactly 2451545.0) and with Meeus' example 12.a
(1987-04-10 0h UT → GMST 197.693195°):

```bash
python3 -c "from stars import julian_date; print(julian_date(2000, 1, 1, 12))"
```

```bash
python3 -c "from stars import julian_date, gmst_deg; print(gmst_deg(julian_date(1987, 4, 10)))"
```

Then run `python3 stars.py` again. It prints your JD and GMST next to astropy's, and NAVERA's GAST.
Your GMST should agree with astropy to a small fraction of an arcsecond. GAST is about 0.5 s of time
later: the equation of the equinoxes (nutation).

### Step 3 — Equatorial to horizontal (TODO 3)

> [!TASK]
> **TODO 3.** `radec_to_altaz(ra_deg, dec_deg, lat_deg, lon_deg, gst_deg)` — **vectorised**: it
> must accept one star or numpy arrays of stars. Formulas in the course (section 2.3) and above the
> function.

**Given 4** — `visible_stars(...)` is already written below TODO 3: read it. It calls your
`radec_to_altaz` **once** on arrays of all the stars (no Python loop over the stars for the maths)
and sorts the visible ones, brightest first. This is the pattern "vectorise, then filter".

Check the worked example of the course (Vega from Teide Observatory on Tenerife, apparent coordinates, GAST —
note the negative longitude, because the site is west of Greenwich):

```bash
python3 -c "from stars import radec_to_altaz; print(radec_to_altaz(279.45960, 38.81067, 28.30, -16.51, 316.48003))"
```

You should get about `(70.006, 307.013)`. Run `python3 stars.py`: it now compares your alt/az of the
10 brightest stars with astropy's full `AltAz` transformation (worst difference: about half an
arcsecond), lists the 44 stars brighter than 2.5 above Teide Observatory (the
brightest is Arcturus, low in the west) and draws **sky.png**. Open
[sky.png](file:./sky.png): zenith in the centre, horizon on the edge, north at the top and east on
the **left** (you lie on your back, head to the north). Polaris is the orange dot.

> [!QUESTION]
> The program moves every catalogue position to the date with NAVERA's `apparent_radec` before
> calling your function. Polaris' right ascension moves by more than 9°, Vega's by 0.2°. Why is the
> change so large near the pole? (Think of how lines of longitude meet at the Earth's poles.)

### Step 4 — Polaris and the zenith fix (TODO 5, 6)

> [!TASK]
> **TODO 5.** `polaris_latitude(alt_deg, ha_deg=None, polar_dist_deg=None)`: the altitude itself
> without the optional arguments; `alt − p·cos(H)` with them.
>
> **TODO 6.** `zenith_fix(ra_deg, dec_deg, gst_deg)`: the position of a camera pointing exactly
> up, from its plate-solved centre (course, section 2.6). Longitude in −180…180.

`python3 stars.py` now follows Polaris from New York during a whole sidereal day (every 15 min) and
prints the worst latitude error with and without the correction (about 70 km → 0.3 km). It also
"plate-solves" a perfect zenith camera at Teide Observatory and gets the site back.

### Step 5 — The error budget (TODO 7)

> [!TASK]
> **TODO 7.** `attitude_error_km(error_deg)` and `clock_error_km(dt_s, lat_deg)` — both ≥ 0.
> Use the constants `EARTH_KM_PER_DEG` and `SIDEREAL_DEG_PER_S` at the top of the file.

Check yourself: 4 s of clock error at the equator must be about 1.86 km — one nautical mile, the
old navigators' rule of thumb ("4 seconds, one mile").

### Step 6 — Monte Carlo on NAVERA's solver (TODO 8)

This is the important measurement of Part A. You will use NAVERA's **own** functions
(`observer_candidates`, `choose_candidate`, `local_to_radec`, passed to you as `cn`) as a black box,
and feed them a noisy attitude.

> [!TASK]
> **TODO 8.** `monte_carlo_fix(cn, site, gst, cam_alt, cam_az, sigma_tilt_deg, sigma_heading_deg,
> n=2000, seed=24)`:
> 1. `rng = np.random.default_rng(seed)`;
> 2. the camera really points at (`cam_alt`, `cam_az`): compute once the (α, δ) it sees with
>    `cn.local_to_radec(site[0], site[1], cam_alt, cam_az, gst)` — this is what the plate solver
>    would report;
> 3. for each of the n draws, the IMU reports `cam_alt + rng.normal(0, sigma_tilt_deg)` and
>    `cam_az + rng.normal(0, sigma_heading_deg)` (draw the tilt first, then the heading); solve with
>    `cn.observer_candidates(...)` and `cn.choose_candidate(cands, site[0], site[1])`;
> 4. return `(np.array(errors_km), number_of_None_results)`, the errors measured with
>    `haversine_km(site, fix)`.

```bash
python3 stars.py
```

The end of the output gives the median and p90 for a camera at 75° (towards the north-east) and at
90°, with a BNO085-class IMU (0.3° tilt, 1.5° heading). Compare with the course: about 55 km RMS
predicted for 75°; NAVERA measured 24–119 km, ~50 km typical. Why is the 90° camera so much better?

The program writes the `"stars"` section of **results.json**. Open it.

## Part B — night vision

Part B does not use anything from Part A. If this is your second session, start here.

### Step 7 — The night replay frames (TODO 10)

```bash
head -5 /data/navera_data/camera_pkg/camera_pkg/data/thermal/flight_ready.csv
```

Each frame's file name holds a position and a height, e.g.
`frame_0002_lat35.83026_lon10.64111_alt400m.jpg`; five frames say `NOGPS`.

**Given 9** — `parse_thermal_name(filename)` (already written: read it) turns such a name into
`(lat, lon, alt)` floats, or `None` without a position; it accepts a full path and negative numbers.

> [!TASK]
> **TODO 10.** `scale_to_map(altitude_m, hfov_deg, width_px, lat_deg, zoom=17)`: the resize factor of
> `normalize_query` (course, section 1.5). `m_per_px` is imported from `navmap.py` (lesson 7).

### Step 8 — Coverage and minimum height (TODO 11)

> [!TASK]
> **TODO 11.** `query_coverage(width_px, height_px, altitude_m, hfov_deg, heading_deg, lat_deg)`:
> the share of the 512 × 512 reference square covered by the scaled frame turned by its heading.
> Sample the square at its pixel centres with `np.meshgrid`, rotate the samples into the frame's
> axes (formula above the function), test the two half-sizes, take the mean. No loops.

**Given 12** — `min_altitude(width_px, height_px, hfov_deg, heading_deg, lat_deg, need=0.85)` is
already written: read it. It finds the lowest height by **bisection** between 50 m and 2000 m, to
0.5 m, calling your `query_coverage`. Coverage only grows with height: that is what makes bisection
valid.

Now compare your coverage with NAVERA's real `normalize_query` (it imports PyTorch: ~10 s):

```bash
python3 compare_navera.py
```

The two columns must agree to about 0.001. NAVERA counts pixels of a warped mask; you count
sample points of an exact rectangle: small differences come from pixel rounding.

### Step 9 — The motion gate (TODO 13)

> [!TASK]
> **TODO 13.** `motion_gate(anchor, t_anchor, fix, t, max_speed_mps=30.0, margin_m=30.0)` →
> `(accepted, jump_m, reach_m)`, as in `night_subscriber.py` (course, section 1.6). A clock that
> goes backwards must not make `reach` smaller than the margin.

### Step 10 — Can we trust the night frames? (TODO 14, 15)

Before you use a dataset to measure accuracy, check that it is what it claims to be. Here, a
quantitative check: compare each night frame with each of the 30 **day** replay frames.

> [!TASK]
> **TODO 14.** `ncc(a, b)`: the normalised cross-correlation of two equal-size pictures
> (−1…1; 0.0 for a uniform picture). Convert to float first.
>
> **TODO 15.** `find_day_twin(thermal_path, day_paths, size=(192, 91))`: the basename of the day
> frame with the highest NCC, that NCC, and the second-best NCC. Work on grey thumbnails
> (`cv2.IMREAD_GRAYSCALE`, `cv2.resize(..., size, interpolation=cv2.INTER_AREA)`).

```bash
python3 thermal.py
```

It takes about 30 s (30 × 30 comparisons). It prints the scale of a replay frame, the coverage table
of a 640 × 480 thermal camera (84°), the minimum heights, the gate decisions on a run-away track,
then the twin of every night frame, and draws **thermal_vs_map.png**: the night frame at map scale,
the map at the position of its label, and that map in grey (what NAVERA's synthetic night tests
fed to STHN). Open [thermal_vs_map.png](file:./thermal_vs_map.png).

> [!QUESTION]
> Look at the twin table. Is there a pattern between the night frame number and its day twin's
> number? What does a best NCC of ~0.9 against a second best of ~0.1 tell you? What do you conclude
> about the positions written in the night frames' names, given that the day frames' positions are
> already known to be wrong (`docs/VALIDATION_STATUS.md`)?

## Step 11 — Write the report

Open [report.md](file:./report.md) and answer the questions in each of its five sections, in your
own words, with the numbers from `results.json` (at least 40 words per section).

> [!TASK]
> **report.md** — five sections: *Sidereal time*, *Polaris*, *Error budget*, *Night geometry*,
> *The night replay set*. The check verifies that each section exists and is long enough, and that
> you quote your Monte Carlo median (Error budget), your minimum height at heading 45° (Night
> geometry) and the frame-number offset you found (The night replay set).

## Step 12 — Check your work

Press **✔ Check my work**. The check calls your functions with its own inputs, then runs
`stars.py` and `thermal.py` itself (about one minute in total) and reads `results.json` and
`report.md`. Read the hint of any red line, fix, save, check again.

## Going further (optional)

- **Two answers.** Ask NAVERA which places see a given star at altitude 45°, azimuth 0° (due north)
  at our instant, when that star is the one seen from New York in that direction:

  ```bash
  python3 -W ignore -c "from cn_pkg.nodes.celestial_math import local_to_radec as l2r, observer_candidates as oc; ra, dec = l2r(40.71, -74.01, 45, 0, 316.48003); print(oc(45, 0, ra, dec, 316.48003))"
  ```

  You get two positions: New York and a second place on the other side of the world (in
  Mongolia). Both are exact solutions of
  equation (1). Try azimuth 180°: is there still a second solution? Explain with the triangle PZX.
- **Second-order Polaris.** Derive the next term of the Polaris correction from
  sin a = sin δ sin φ + cos δ cos φ cos H with δ = 90° − p, and show that it removes most of the
  remaining 0.3 km. Then add Bennett's refraction R = 1′ · cot(a + 7.31/(a + 4.4)) (a in degrees)
  and compute the error of an uncorrected measurement at New York.
- **A better IMU.** Change the Monte Carlo to a tactical-grade attitude (0.05° tilt, 0.2° heading)
  and to a gimballed camera pointing at the zenith. What position accuracy would make celestial
  useful as more than a "which region am I in" check?
- **Your own evening.** Change `WHEN` to tonight's date at 21:00 of your local time, written in UTC
  (for example UTC + 1: subtract 1 h), and the site to your own town (west longitudes negative), run `python3 stars.py`, and go outside to check sky.png against the real
  sky. Put the original values back before you press ✔ Check.
