# Lab 15 — A robust NMEA reader, DOP from geometry, and NAVERA's GPS driver

**Goal:** build a robust NMEA 0183 parser (checksum, GGA, GSA, GSV), recompute the receiver's
PDOP/HDOP/VDOP from the satellite geometry, reproduce the decisions of NAVERA's `gps_node`, estimate
the range error (UERE) of a drive whose truth is known, replay the log into NAVERA's real driver,
and write a short engineering report.
**Time:** about 3 hours.

## The data

`/data/academy/15-gps-nmea/` (read only):

| File | What |
|---|---|
| `sousse_drive.nmea` | a **synthetic** NMEA log, 1 Hz, GPS-only receiver (`GP` talker): a car drives about 19 km along the coast from the port of Sousse to the Ribat of Monastir, in NAVERA's test area (Tunisia). 6414 lines, 1069 s. |
| `truth.csv` | the true position of the car every second (`utc,lat,lon,alt_msl`) |
| `make_dataset.py` | the script that generated both (read it after the lab, not before!) |

The places are real; the roads are approximate and the underpass is invented. The log is synthetic
so that we know the truth exactly. It contains on purpose: a cold start, an underpass (outage),
a town centre with high buildings, and damaged lines.

Your files:

| File | What you do |
|---|---|
| [nmea_tools.py](file:./nmea_tools.py) | TODO 1–6: checksum, validation, degrees-minutes, GGA, GSA, GSV |
| [dop.py](file:./dop.py) | TODO 7–8: geometry matrix G and the DOPs |
| [gps_filter.py](file:./gps_filter.py) | TODO 9–11: gps_node's decision, its covariance, a jump gate |
| [analyze_drive.py](file:./analyze_drive.py) | TODO 12–13: UERE estimate, longest gap; then it writes `results.json` and 2 plots |
| `compare_with_navera.py` | compares your parser with pynmea2 (ready) |
| `play_to_gps_node.py` | plays the log into NAVERA's real `gps_node` (ready) |
| [report.md](file:./report.md) | your written analysis (template) |

> [!TIP]
> Run each file after each TODO: every file has a small demo at the bottom (`python3 dop.py`…).
> A TODO that is not done returns `None`; the demos and `analyze_drive.py` say which one is missing.

## Step 1 — Look at the raw log (10 min)

```bash
head -n 14 /data/academy/15-gps-nmea/sousse_drive.nmea
```

The first seconds: `GPGGA` with quality `0` and empty positions, `GPRMC` with status `V`, a `GPGSA`
with mode `1`, and 3 `GPGSV` sentences listing 12 satellites. The receiver has just started.

Count the sentence types. The log contains one non-ASCII byte, so `grep` needs `-a` (treat the file
as text):

```bash
grep -a -c GGA /data/academy/15-gps-nmea/sousse_drive.nmea
```

```bash
grep -a -c GSV /data/academy/15-gps-nmea/sousse_drive.nmea
```

```bash
wc -c /data/academy/15-gps-nmea/sousse_drive.nmea
```

Divide the size by 1069 s: this is the data rate of the course's worked example (411 bytes/s,
43 % of a 9600-baud link). Now look at one second in the middle of the drive:

```bash
sed -n 1985,1990p /data/academy/15-gps-nmea/sousse_drive.nmea
```

Compare the latitude of the GGA (`3574.17098`) with the RMC of the same second (`3547.17098`).
Keep this in mind.

## Step 2 — Checksum and validation (TODO 1–2, 20 min)

Try the three Python tools you need:

```bash
python3 -c "print(ord('G'), ord('P'), ord('G') ^ ord('P'), f'{23:02X}', f'{13:02X}')"
```

You should see `71 80 23 17 0D`. Write `nmea_checksum(body)` and `is_valid(line)` in
[nmea_tools.py](file:./nmea_tools.py). The rules of `is_valid` are listed above TODO 2 (and in
section 7 of the course). It must return `True` or `False` — never `None`, never an exception,
even for `None` or an empty string.

```bash
python3 nmea_tools.py
```

Then list the damaged lines of the log:

```bash
python3 -c "import nmea_tools as t; bad = [(i + 1, l) for i, l in enumerate(t.read_log('/data/academy/15-gps-nmea/sousse_drive.nmea')) if not t.is_valid(l)]; print(len(bad)); [print(n, repr(l[:72])) for n, l in bad]"
```

You must find **7** lines. For each one, decide what happened on the wire (cut, flipped character,
missing checksum, garbage, two glued sentences, a non-ASCII byte shown as `�`). You will
describe them in section 1 of the report.

<details><summary>Hint: two lines look alike — which one is the "flipped character"?</summary>

There are **two** flipped characters: one in a GGA latitude, and one in a GSA. Look at the end of
the GSA line `…,1.31,0.77,1906*0D`: the last field is the VDOP. A VDOP of "1906" is impossible.
One character changed: the decimal point became a `9` (the real value was `1.06`).
</details>

> [!TASK]
> **TODO 1–2** — `nmea_checksum(body)` returns 2 upper-case hex digits; `is_valid(line)` returns
> `True`/`False` and finds exactly 7 damaged lines in the log. The two swapped-digit lines (UTC
> 051731 and 052421) must be **accepted**: the checksum cannot see them.

## Step 3 — Degrees-minutes and GGA (TODO 3–4, 25 min)

`dm_to_deg(value, hemisphere)` converts `"3549.61531", "N"` into `35.826922`. It returns `None` for
an unreadable value, an unknown hemisphere, or minutes outside `[0, 60)`. Use `to_float()` (already
written, below the line).

```bash
python3 -c "import nmea_tools as t; print(t.dm_to_deg('3549.61531', 'N'), t.dm_to_deg('01038.52535', 'E'), t.dm_to_deg('3574.17098', 'N'), t.dm_to_deg('', 'N'))"
```

Expected: `35.8269218… 10.6420891… None None` (Python may print more digits: floating-point rounding).

`parse_gga(line)` returns a dictionary with the keys `time, lat, lon, quality, sats, hdop, alt_msl,
geo_sep` (field numbers above TODO 4 and in the course). Use the helper `fields(line)`: it returns
the list of fields of a valid sentence, or `None`.

> [!TASK]
> **TODO 3–4** — `dm_to_deg` with the range checks, and `parse_gga`. A no-fix sentence gives a
> dictionary with `quality` 0 and `lat`/`lon`/`alt_msl` = `None`; the 74-minute line gives
> `lat = None`; an RMC or a damaged line gives `None`.

## Step 4 — GSA and GSV (TODO 5–6, 25 min)

These two sentences give the **geometry**. GSA: fix mode, the PRNs used (12 slots, some empty) and
PDOP/HDOP/VDOP. GSV: blocks of 4 fields `prn, elevation, azimuth, snr`, up to 4 satellites per
sentence. The exact output format is written above TODO 5 and TODO 6.

```bash
python3 nmea_tools.py
```

> [!WARNING]
> Common mistakes: forgetting that an empty SNR (`,,`) means "in view but not tracked" (it must give
> `None`, not crash); requiring exactly 18 items after `split(",")` for GSA — the sentence ID plus fields 1–17 (NMEA 4.10 adds
> field 18, the system ID: a 19th item); reading a last GSV
> block that has fewer than 4 fields.

> [!TASK]
> **TODO 5–6** — `parse_gsa(line)` and `parse_gsv(line)` as specified in the file.

## Step 5 — Compare with NAVERA's parser (10 min)

`gps_node` uses the **pynmea2** library. This script runs pynmea2 and your functions on every line
and lists every disagreement:

```bash
python3 compare_with_navera.py
```

Now (before Step 7) you should see 7 rejected lines on both sides and no disagreement. The "usable
fixes" column of your side shows `—`, with the message "TODO 9 not done yet": this column needs
your `navera_decision()` from Step 7. That is normal. **Run the script again after Step 7.**

After Step 7 you should see 1007 usable fixes for NAVERA and **1006 for you**, and
one disagreement: line 1988 (UTC 051731). pynmea2 accepts `3574.17098` and computes 36.2362° N —
about 50 km north of the road. Your parser refuses it because 74 minutes is impossible. Who is
right? Note the answer for section 4 of the report.

## Step 6 — The geometry matrix and the DOPs (TODO 7–8, 30 min)

Implement `geometry_matrix(az_deg, el_deg)` and `dops(az_deg, el_deg)` in [dop.py](file:./dop.py)
with numpy. Follow the equations of section 5 of the course. Remember `np.radians`: `np.sin(30)`
is the sine of 30 **radians**.

```bash
python3 dop.py
```

The worked example must give exactly the numbers of the course (HDOP 1.155, VDOP 2.236, PDOP 2.517,
TDOP 1.414, GDOP 2.887). Two experiments to understand the matrix:

1. Four satellites at the **same** elevation make `GᵀG` singular (the course explains why). Check
   its rank — 3 instead of 4:

```bash
python3 -c "import numpy as np, dop; G = dop.geometry_matrix([0, 90, 180, 270], [40, 40, 40, 40]); print(np.linalg.matrix_rank(G.T @ G))"
```

2. Turn the whole sky by 37° in azimuth: HDOP and VDOP must not change (a rotation about the
   vertical axis does not change the geometry, only the direction of the error ellipse):

```bash
python3 -c "import dop; a = [10, 80, 150, 200, 300]; e = [15, 50, 35, 70, 25]; print(dop.dops(a, e)['HDOP'], dop.dops([x + 37 for x in a], e)['HDOP'])"
```

> [!TASK]
> **TODO 7–8** — `geometry_matrix` returns an n × 4 numpy array; `dops` returns the dictionary
> `{"GDOP", "PDOP", "HDOP", "VDOP", "TDOP"}` and raises `ValueError` with fewer than 4 satellites.

## Step 7 — NAVERA's decisions (TODO 9–11, 25 min)

Open [gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/gps_node.py) beside
[gps_filter.py](file:./gps_filter.py). Find `_VALID_GPS_QUAL`, the `reason = (...)` lines and the
covariance in `_publish_fix`. Then write:

- `navera_decision(gga)` → `(valid, reason)` with **exactly** the reason texts of gps_node (copy the
  em dash `—` from the file; a normal `-` is a different character);
- `navera_covariance(hdop)` → the 9 numbers gps_node writes, or `None`;
- `jump_ok(prev, cur, dt, slack_m)` → a plausibility gate: the distance must be at most
  `v_max × dt + slack_m`. NAVERA's **estimator** has the same idea with 100 m/s and 50 m (see
  `max_speed_mps` and `gps_jump_margin_m` in
  [estimator_node.py](file:navera/navera_estimator/navera_estimator/nodes/estimator_node.py)).

```bash
python3 gps_filter.py
```

Now go back to Step 5 and run `compare_with_navera.py` again: the "usable fixes" column is ready.

```bash
python3 compare_with_navera.py
```

> [!TASK]
> **TODO 9–11** — the three functions of `gps_filter.py`, as specified above each TODO.

## Step 8 — Analyse the drive (TODO 12–13, 30 min)

Two last functions in [analyze_drive.py](file:./analyze_drive.py):

- `estimate_uere(err_h, hdop)` → one number in metres (course, section 6, "Estimating UERE from data");
- `longest_gap(times)` → `(gap_s, t_before, t_after)` over consecutive accepted fixes.

The rest is ready: it groups the sentences into seconds, recomputes the DOPs of every second from
GSV + GSA with **your** `dops()`, applies your decision and your jump gate (60 m/s + 3 σ of the
fix), compares the accepted fixes with `truth.csv`, and writes `results.json`, `drive.png` and
`dop_timeline.png`.

```bash
python3 analyze_drive.py
```

Expected: 7 rejected lines; DOP recomputed on 1008 seconds with a largest difference of about 0.005
(rounding to 2 decimals); one jump rejected at 052421; a longest gap of 33 s; a UERE estimate close
to 1.9 m and about 98 % of fixes inside 2DRMS. Open `dop_timeline.png` and `drive.png` (click them
in the file list) and find the port area, the underpass and the town centre.

> [!TASK]
> **TODO 12–13** — then `results.json` must contain the values above (the check compares them).

## Step 9 — Replay the log into NAVERA's real driver (10 min)

The script creates a fake serial port (a **pseudo-terminal**, the same trick as NAVERA's test
`navera_tools/tests/test_gps_serial.py`), starts `ros2 run gps_pkg gps_node.py` on it, writes the
log into it about 40 times faster than real time, and counts the `PositionEstimate` messages on
`/navera/estimate/gps`. It takes about 40 seconds:

```bash
python3 play_to_gps_node.py
```

Expected: 1066 messages, **1007 valid**, 59 invalid (54 × "no GPS fix (qual=0)", 5 × "receiver
reports a non-satellite position (qual=6) — not used"), and a largest jump between consecutive
valid fixes of about 50 km. The counts are saved in `gps_node_counts.json`. The first valid fix shows
an ellipsoidal altitude near +38 m: the GGA altitude (about 6 m above sea level) plus the geoid
separation +32.0 m of this synthetic receiver.

> [!QUESTION]
> gps_node published the 50 km jump as a **valid** fix with a sigma of 1.7 m. Which part of NAVERA
> stops it before it reaches the autopilot, and with which rule?

## Step 10 — Write the report (30 min)

Fill [report.md](file:./report.md): 5 sections, at least 250 words, your own sentences. Quote
your numbers from `results.json` and `gps_node_counts.json`. The check looks for: the number of
rejected lines, the UTC times of the two swapped-digit lines, the outage length, your UERE
estimate and gps_node's valid count.

> [!TASK]
> **report.md** — every `TODO` line replaced, the 5 headings kept. Then press **✔ Check my work**.
> Each red line has a hint; fix, save, run the script again, and check again.

## Going further (optional)

1. **Elevation weighting.** Real receivers trust high satellites more (less atmosphere, less
   multipath). Use a weight matrix `W = diag(sin²(el_i))` and `Q_w = (Gᵀ W G)⁻¹`. How does HDOP
   change in the town centre? (The DOPs in the log are unweighted, so they will no longer match.)
2. **Property test.** With `hypothesis` (installed) and `pytest` (lesson 14), write a test that
   changes one random character of a valid sentence and asserts `is_valid` is `False`, and another
   that swaps two different neighbouring characters of the body and asserts it stays `True`.
   Explain both results with the XOR algebra.
3. **RMC cross-check.** Write `parse_rmc(line)` and compare the GGA and RMC positions of the same
   second. Which damaged lines does this catch that the checksum and the jump gate do not? Could
   gps_node do this cheaply?
4. **The simulator's receiver.** Open `~/navera/navera_tools/sim/nmea_gps.py`. What does it send in
   the `jammed` mode? How many decimals of minutes does it write, and what resolution in metres is
   that?
