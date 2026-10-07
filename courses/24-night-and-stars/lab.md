# Lab 24 — The sky above Sousse, and a night frame

**Goal:** compute where the bright stars are above Sousse tonight with NAVERA's celestial code,
find your latitude from Polaris, measure what an attitude error costs, and look at a night frame
next to the map like NAVERA's night localizer prepares it.
**Time:** about 1 h 15.

You will work in three files:

| File | What you do |
|---|---|
| [stars.py](file:./stars.py) | TODO 1–4: stars in your sky, Polaris, attitude error |
| [thermal.py](file:./thermal.py) | TODO 5–6: read a night frame's label, scale it to the map |
| [answers.py](file:./answers.py) | 4 quiz questions |

## Step 1 — Meet the star catalogue

NAVERA's star catalogue is a plain text file, one star per line, with fixed columns. Look at the
line of Polaris (its catalogue name is "Alp UMi": alpha of the Little Bear):

```bash
grep "Alp UMi" /data/bsc5.dat
```

You see `023148.7+891551` in the middle: right ascension **02 h 31 min 48.7 s**, declination
**+89° 15′ 51″** — less than 1° from the pole (90°). Right ascension is written in hours: one hour
= 15°. The given function `load_bright_stars` (bottom of `stars.py`) turns these columns into
degrees for you. Then, a few columns later, `2.02` is its **magnitude** (brightness: the
*smaller*, the brighter; the brightest star, Sirius, is −1.46).

## Step 2 — Run the program before changing it

```bash
python3 stars.py
```

It finds 92 stars brighter than magnitude 2.5, then asks NAVERA's
[celestial_math.py](file:navera/cn_pkg/cn_pkg/nodes/celestial_math.py) for the Greenwich sidereal
time at 2026-10-07 20:00 UTC (21:00 in Tunisia): about **316.48°**. Everything else says
"TODO … is not done yet". (It takes a few seconds: *astropy*, the astronomy library NAVERA uses,
is big.)

> [!NOTE]
> The box has no internet in flight. `navera_sky_clock` tells astropy not to download its Earth
> rotation tables and to use the ones it ships with: the sidereal time is then right to about
> 0.004°, plenty for us.

## Step 3 — TODO 1: altitude and azimuth of a star

Open [stars.py](file:./stars.py). Fill in `star_altaz(ra_deg, dec_deg, lat_deg, lon_deg, gast_deg)`
following the four steps written above it. Remember that `math.sin` and `math.cos` want
**radians**: convert with `math.radians(...)`, and convert the result of `math.asin` / `math.atan2`
back with `math.degrees(...)`.

Test it on Vega (RA 279.2346°, Dec 38.7837°) seen from Sousse at our time:

```bash
python3 -c "from stars import star_altaz; print(star_altaz(279.2346, 38.7837, 35.83, 10.64, 316.48))"
```

You should see about `(52.23, 289.24)`: Vega is 52° high, towards the west-north-west (azimuth
270° is west). Go outside on a clear October evening at 21:00 and look: it is there.

> [!TASK]
> **TODO 1** — `star_altaz` returns `(altitude, azimuth)` in degrees, azimuth between 0 and 360.
> The check compares it with NAVERA's own inverse function `local_to_radec` on 20 random stars.

## Step 4 — TODO 2: which stars are up tonight?

Fill in `visible_stars(stars, lat_deg, lon_deg, gast_deg, min_alt_deg=0.0)`: loop over the stars,
compute `(alt, az)` with your `star_altaz`, keep the stars **above** `min_alt_deg`, and return a
list of dicts `{"name", "mag", "alt", "az"}` sorted from the brightest (smallest `mag`) to the
faintest. Then:

```bash
python3 stars.py
```

You get a table — Vega, Capella, Altair, Aldebaran just rising in the east (0.1° high!),
Fomalhaut low in the south… — and **sky.png**. Open [sky.png](file:./sky.png): it is the sky
as a round map, the zenith in the middle and the horizon on the edge, like when you lie on your
back with your head to the north (so east is on the **left**). Polaris is the orange dot.

Notice the line in `__main__` that calls NAVERA's `to_date` (`apparent_radec`) on every star before
your function: it moves the catalogue's year-2000 addresses to 2026 (**precession**). Polaris'
right ascension moves from 37.95° to 47.09°! Near the pole, a small wobble is a big change of
right ascension.

> [!TASK]
> **TODO 2** — `visible_stars` returns the stars above the horizon, brightest first.
> 40 stars brighter than 2.5 are above Sousse at our time.

## Step 5 — TODO 3 and 4: Polaris and the price of a degree

**TODO 3.** `latitude_from_polaris(polaris_alt_deg)` returns your latitude. (One line! Look at the
picture "The altitude of Polaris equals your latitude" in the course.)

**TODO 4.** `position_error_km(attitude_error_deg)` returns how far a celestial fix moves when the
camera's attitude is wrong by that many degrees: one degree of the Earth's circle is
`EARTH_KM_PER_DEG` = 111.195 km. Use `abs()` — an error of −2° is still 222 km away.

```bash
python3 stars.py
```

At the end you now read:

```
Polaris: altitude 35.94°, azimuth 0.76°
Latitude from Polaris: 35.94°  (true: 35.83°, off by 0.11° = 12 km)
Round trip through NAVERA's local_to_radec: RA 47.091° (star 47.091°), Dec 89.374° (star 89.374°)
```

Two things to see:

- Polaris is 0.63° from the pole, so "latitude = altitude of Polaris" is wrong by up to 0.63°
  (70 km), depending on where Polaris is in its little daily circle around the pole. Tonight at
  21:00 it is only 0.11° off. Sailors used a small correction table for that.
- NAVERA's `local_to_radec` takes your altitude and azimuth and gives the star's address back:
  your code and NAVERA's agree.

And the table of attitude errors: 0.5° → 55.6 km. Compare with the course: in simulation, a 0.5°
tilt error gave a **53 km** error. Your one-line formula predicts what NAVERA measured.

> [!TASK]
> **TODO 3 and 4** — `latitude_from_polaris` and `position_error_km`. Then run `python3 stars.py`
> once more so that **sky.png** is up to date.

## Step 6 — A night frame next to the map

Now the night side. Open [thermal.py](file:./thermal.py).

**TODO 5.** `parse_thermal_name(filename)` reads the position written in the file name:
`frame_0002_lat35.83026_lon10.64111_alt400m.jpg` → `(35.83026, 10.64111, 400.0)`, and
`frame_0004_NOGPS_alt400m.jpg` → `None` (no position recorded). Use `os.path.basename`,
`os.path.splitext`, `.split("_")`, `.startswith("lat")`, and `float(...)`. It must also work with
negative numbers like `lat-12.5`.

**TODO 6.** `scale_to_map(altitude_m, hfov_deg, width_px, lat_deg, zoom=17)` is the very first
calculation of NAVERA's night localizer (`normalize_query` in
[night_localizer.py](file:navera/night_pkg/night_pkg/nodes/night_localizer.py)): footprint,
meters per pixel of the frame, meters per pixel of the map (`m_per_px` from `navmap.py`), and their
ratio. Then:

```bash
python3 thermal.py
```

It lists the 30 night frames, 5 of them without a position, prints
`scale 0.484 -> 744x354 px at map resolution`, and saves **thermal_vs_map.png**. Open
[thermal_vs_map.png](file:./thermal_vs_map.png). Three pictures at the same scale:

1. the night frame (brightened so you can see it),
2. the z17 map at the position written in its name,
3. that map in grey — the "fake thermal" images NAVERA's synthetic night tests used.

Look hard. Same streets? Same blocks? Same direction of the roads?

> [!WARNING]
> They are **not** the same place. The streets of the night frame run up and down; those of the
> map run diagonally. These "thermal" frames are in fact darkened grey copies of the day replay
> frames (we measured a correlation of ~0.88 between each one and a day frame), and the day frames'
> positions are known to be wrong. That is exactly why `VALIDATION_STATUS.md` says the replay set
> cannot be used for night vision, and why NAVERA's night results were measured on synthetic frames
> and in the simulator. Lesson: **always look at your test data before trusting a number computed
> on it.**

> [!TASK]
> **TODO 5 and 6** — `parse_thermal_name` and `scale_to_map`, then `python3 thermal.py` draws
> `thermal_vs_map.png`.

## Step 7 — The quiz

Open [answers.py](file:./answers.py) and answer the four questions (Q2 needs your picture from
step 6).

> [!TASK]
> Answer Q1–Q4 in `answers.py`.

## Step 8 — Check your work

Press **✔ Check my work**. The check runs `stars.py` and `thermal.py` itself, so they must run
without errors. Read the hints of any red line, fix, save, check again.

## Going further (optional)

- **The other half of the night.** Change `WHEN_UTC` to `"2026-10-08 03:00:00"` (04:00 in Tunisia)
  and run `python3 stars.py` again. Orion's stars (Betelgeuse, Rigel) and Sirius are up; Vega has set.
  Then put it back to `"2026-10-07 20:00:00"` before you check your work.
- **Two answers.** NAVERA's `observer_candidates` finds the places that see a given star at a
  given altitude and azimuth. Ask it for the star seen from Sousse at altitude 45°, azimuth 0° (due north):

  ```bash
  python3 -W ignore -c "from cn_pkg.nodes.celestial_math import local_to_radec as l2r, observer_candidates as oc; ra, dec = l2r(35.83, 10.64, 45, 0, 316.48); print(oc(45, 0, ra, dec, 316.48))"
  ```

  You get **two** positions: Sousse, and a place in the far north of the Pacific Ocean. Both see
  that star at exactly that altitude and azimuth! This is why NAVERA needs a prior
  (`choose_candidate`). Try azimuth 180° too: not every direction has a second answer.
- **A better Polaris.** The correction sailors used: latitude ≈ altitude − p·cos(H), where p is
  Polaris' distance from the pole (90° − its declination) and H its hour angle. Add it to your
  `latitude_from_polaris` as an optional argument and see the 0.11° shrink.
