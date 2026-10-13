# Lab 15 — A GNSS part that cannot be fooled by a line of text (almost)

**Goal:** write NAVERA Lite's GNSS part (`navera_lite/gnss.py`): a robust NMEA reader, the satellite
geometry, and the judge that says FIX, DEGRADED or NO_FIX. Then forge a line that fools your own checksum,
and run a damaged 19 km drive through your judge.
**Time:** 3 to 5 h (a strong programmer: about 2 h 30).
**Fast track:** if you know Python and numpy, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further".

Your files (📝 Code tab): [navera_lite/gnss.py](file:./navera_lite/gnss.py) (**your code**: ten functions,
`TODO 1–10`), [answers.py](file:./answers.py), [report.md](file:./report.md), and the runner
[run_gnss.py](file:./run_gnss.py), which runs your functions on the lab's situations (you only run it).
`navera_lite/geo.py` is mission 06's part, given finished.

The data, in `/data/academy/15-gps-nmea/` (read only): `sousse_drive.nmea`, a **synthetic** 1 Hz log of a
GPS receiver in a car, from the port of Sousse to Monastir (NAVERA's test area; the places are real, the
log is made for the course, so the truth is known), and `truth.csv`, where the car really was every second.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | nothing: you watch a naive reader |
| §1 the line | Step 1 | two numbers |
| §2 the checksum | Step 2 | `nmea_checksum`, `is_valid` |
| §3 GGA | Step 3 | `dm_to_deg`, `parse_gga` |
| §4 GSA, GSV | Step 4 | `parse_gsa` |
| §2–§3 | Step 5 | a forged line |
| §5 geometry | Steps 6–7 | `geometry_matrix`, `dops` |
| §6 the decision | Step 8 | `fix_decision`, `covariance_from_hdop`, `fix_state` |
| all | Step 9 | the memo |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each function's docstring says its goal and gives one example with its
> result; `python3 run_gnss.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — The wire (1 h 45 to 2 h 15)

## Step 0 — A naive reader

No code. A naive reader takes every line that starts with `$GPGGA` and believes it: no checksum, no
quality, no range check. Run it on the drive:

```bash
python3 run_gnss.py naive
```

Open `out/naive.png` in the 📝 Code tab. Most of the drive looks fine. Look at the worst lines in the
table: what kind of mistake turns a car on a coastal road into a car 50 km to the north, out at sea in
the Gulf of Hammamet? And what is quality 6? (The naive reader skips lines it cannot even read as numbers,
such as the empty quality-0 lines of the start: that is why it reports "0 quality 0".) Keep these questions; the lesson's §1–§3 answer them, and your code will refuse every one of those lines.

## Step 1 — The raw log

Read the first two seconds of the log: a receiver that has just started.

```bash
head -n 12 /data/academy/15-gps-nmea/sousse_drive.nmea
```

GGA with quality `0` and empty fields, RMC with status `V` (void), GSA with fix type `1` (no fix), and three GSV
sentences: 12 satellites in view, no signal strength yet. Count the GGA lines. (The log contains a byte
that is not text, so `grep` needs `-a`, "treat as text".)

```bash
grep -a -c GGA /data/academy/15-gps-nmea/sousse_drive.nmea
```

```bash
wc -c /data/academy/15-gps-nmea/sousse_drive.nmea
```

> [!TASK]
> The drive lasts 1069 s. Write `BYTES_PER_S` (one decimal) and `LINK_LOAD_PCT`, that rate as a
> percentage of the **960 characters per second** a 9600-baud link carries (lesson §1).

## Step 2 — Checksum and validation (TODO 1, TODO 2)

Open `navera_lite/gnss.py`. The top holds constants (`MAX_LINE_LEN`, `USABLE_QUALITIES`, `UERE_M`…) and,
between the TODOs, given helpers: `to_float`, `to_int`, `fields`, `utc_seconds`, `parse_gsv`, `read_log`.
Each `TODO` function keeps its docstring and ends with `return None   # TODO…`: replace that line with your
code.

**TODO 1** `nmea_checksum(body)`: lesson §2 (its 🧰 box has every Python tool you need). **TODO 2**
`is_valid(line)`: the rules are in its docstring. It must answer `True` or `False` for **anything**: a good
line, garbage, `""`, `None`, a number.

<details><summary>🧰 Python: split, strip, isinstance</summary>

```python
"  $AB*12\r\n".strip()             # '$AB*12' — removes spaces and \r\n at both ends
"AB*12*X".split("*", 1)            # ['AB', '12*X'] — at most ONE cut, at the first *
body, given = "AB*12".split("*", 1)  # unpacking: body = 'AB', given = '12'
isinstance(None, str), isinstance("x", str)   # (False, True)
"$" in "GP$GGA"                    # True
```
</details>

```bash
python3 run_gnss.py test
```

The TODO 1 and TODO 2 lines must be ✔ (the others are later TODOs).

> [!TASK]
> **Predict** (`PREDICT_BAD`): the log has 6414 lines. How many will your `is_valid` refuse, and what kinds
> of damage do you expect on a car's serial cable? Then run:

```bash
python3 run_gnss.py log
```

> [!TASK]
> Write `BAD_LINES` and `EXPLAIN_BAD`: look at each refused line and say what happened on the wire (name at
> least three kinds of damage).

<details><summary>Stuck? Hints, one at a time</summary>

1. `TypeError: unsupported operand type(s) for ^: 'int' and 'str'`: XOR works on numbers — `ord(ch)`.
2. `"A"` instead of `"0A"`: write the format `02X`, not `X`. `"0a"`: upper case, `X` not `x`.
3. `is_valid` returns `None` for some line: one path has no `return` (an `if` without `else`?).
   `AttributeError: 'NoneType' object has no attribute 'strip'`: test `isinstance(line, str)` **first**.
   `ValueError: not enough values to unpack (expected 2, got 1)`: the line has no `*`. Test `"*" in line`
   before `split("*", 1)`. `IndexError` on the empty line: `line[0]` does not exist — use `startswith("$")`.
4. The good line with `\r\n` refused: strip **before** you look at the length and the last characters. The
   lower-case hex line refused: compare with `given.upper()`. The glued line accepted: look for a `$` inside
   the body. `log` refuses thousands of lines: print `nmea_checksum(body)` and `given` for the first line of
   the log and compare them.
</details>

## Step 3 — Degrees-minutes and GGA (TODO 3, TODO 4)

**TODO 3** `dm_to_deg(value, hemisphere)`: lesson §3, with every range check of the docstring. Use the
given `to_float`: it turns `""` and damaged numbers into `None` instead of raising.

**TODO 4** `parse_gga(line)`: one dict, keys in the docstring. Use the given `fields(line)` (it calls your
`is_valid`, so an invalid line gives `None`), and `to_float`, `to_int`, `utc_seconds`, your `dm_to_deg`.

<details><summary>🧰 Python: a dict with None, and the conditional expression</summary>

```python
f = "GPGGA,1,,3".split(",")        # ['GPGGA', '1', '', '3'] — an empty field is the empty string ''
f[0].endswith("GGA"), len(f)        # (True, 4)
d = {"alt": 12.0, "sep": None}
total = d["alt"] + d["sep"] if d["alt"] is not None and d["sep"] is not None else None
# BOTH must exist: here total is None, never 12.0 + 0
```
</details>

```bash
python3 run_gnss.py test
```

> [!TASK]
> One GGA line of the drive has a correct checksum and quality 1, but an impossible latitude (you met it in
> Step 0). Find it with your `parse_gga` (a short loop over `read_log(…)`, in a script or in `python3`) and
> write its time in `IMPOSSIBLE_UTC` as `"hhmmss"`. Then `IMPOSSIBLE_WHY`: which check of yours refuses it, and
> why did the checksum not?

<details><summary>Stuck? Hints, one at a time</summary>

1. `35.4404006` instead of `35.734001`: you divided by 100. The last two digits before the point are
   minutes: degrees = `int(v // 100)`, minutes = `v − 100 × degrees`.
2. `−10.575849` expected but `10.575849`: W (and S) are negative. `90.0001` accepted: a latitude must stay
   ≤ 90, a longitude ≤ 180 (the hemisphere tells you which).
3. `ValueError: could not convert string to float: ''`: use `to_float(f[k])`, not `float(f[k])`.
   `IndexError: list index out of range`: test `len(f) >= 15` before reading `f[14]`.
4. `h_ell_m` equal to the altitude: add the geoid separation (field 11, not 10: field 10 is the unit "M").
   `h_ell_m` a number when the separation is empty: a missing height stays `None`.
5. `TypeError: unsupported operand type(s) for +: 'NoneType' and 'float'`: one height is empty; add the two
   only when **both** exist (🧰 box above).
6. For `IMPOSSIBLE_UTC`: loop over `g.read_log("/data/academy/15-gps-nmea/sousse_drive.nmea")`, call your
   `parse_gga` on each line, and print the lines whose dict has quality 1 but `lat` None.
</details>

## Step 4 — GSA, and the given GSV (TODO 5)

**TODO 5** `parse_gsa(line)`: lesson §4. Accept 18 items **or more** (NMEA 4.10's system ID). Then read
the given `parse_gsv` just below it: it is the same idea, with blocks of four fields.

```bash
python3 run_gnss.py test
```

<details><summary>Stuck? Hints</summary>

1. The NMEA 4.10 line gives `None`: you required `len(f) == 18`; the rule is `len(f) >= 18`. The 12-slot line
   loses its last PRN: the slots are f[3] to f[14] **inclusive**, so the slice is `f[3:15]`.
2. `prns` with `''` or `None` inside: skip the empty slots; `['02', '05']`: convert with `to_int`.
</details>

## Step 5 — Be the saboteur

A saboteur with a soldering iron on the serial cable (or a bug in a converter) can swap two characters of
a line. Your parser is now strict. Can it still be fooled? Start from this line of the log (05:22:00):

```
$GPGGA,052200.00,3545.89257,N,01045.14417,E,1,12,0.77,2.1,M,32.0,M,,*59
```

> [!TASK]
> **Predict** (`PREDICT_FORGE_KM`): with ONE swap of two characters, keeping the checksum `*59` as it is,
> how far can you move the position and still pass every check of your parser?

Copy the line into `FORGED_LINE` in `answers.py`, swap two characters, save, and test it:

```bash
python3 run_gnss.py forge
```

Try several swaps. Which ones does your parser refuse, and why? Then hunt: which single swap moves the
fix the **farthest** while your parser still says FIX? (Your teacher keeps the class record.)

> [!TASK]
> Keep your farthest forged line (it must move the fix by more than 1 km and pass your parser). Write
> `FORGE_KM` (what `forge` prints) and `EXPLAIN_FORGE`: why does the checksum not see it, why do your range
> checks not see it either, and what in a navigation stack could?

<details><summary>Open after you wrote EXPLAIN_FORGE</summary>
A range check refuses <b>impossible</b> values (74 minutes, a latitude of 95°), not <b>wrong</b> ones: 53° N is
a real latitude, 110° E a real longitude (in China). One swap can move the fix by thousands of kilometres and
still look like a perfect FIX with σ 1.5 m. Only something that knows where the vehicle <b>can</b> be — a jump
gate, a geofence, another source — refuses it.
</details>

> [!TIP] 🏅 End of session 1 — Line inspector
> Press **✔ Check my work** now: it tests your functions on lines they have never seen. When checks 1–7 pass
> (TODO 1–5, Steps 1–3 and 5), you earn the **Line inspector** badge. If the class session ends here, stop here.

## Session 2 — The sky (about 2 h to 2 h 30)

Read lesson §5–§6 first.

## Step 6 — The geometry matrix and the DOPs (TODO 6, TODO 7)

**TODO 6** `geometry_matrix(az_deg, el_deg)`: lesson §5, the first idea of mission 01 in 3-D. Work with numpy
on whole columns (no loop needed).

<details><summary>🧰 numpy for this step</summary>

```python
import numpy as np
a = np.radians(np.asarray([0, 90], dtype=float))      # array([0.    , 1.5708]) — degrees → radians
np.column_stack([a, 2 * a, np.ones(a.size)])          # 2 × 3: each list becomes a COLUMN
M = np.array([[2.0, 1.0], [1.0, 1.0]])
np.linalg.inv(M), np.diag(M), M.T @ M                 # inverse, diagonal [2., 1.], Mᵀ·M
np.linalg.matrix_rank(np.array([[1.0, 2.0], [2.0, 4.0]]))   # 1: the second row is twice the first
raise ValueError("a and b must have the same length")   # stops the function with an error, on purpose
```
</details>

**TODO 7** `dops(az_deg, el_deg)`: the seven DOPs of lesson §5, and `None` for a geometry that cannot give
a 3-D fix and a clock. Read the warning box of §5 before you write it. New since mission 01: the 4th column
and the **rank test**. If your TODO 7 is mission 01's code with one more column, make sure the `test` line
"without the overhead satellite" gives `None`.

```bash
python3 run_gnss.py test
```

> [!TASK]
> **Predict**, before you run `sky`: (`PREDICT_ROTATE`) the whole sky turns by 37° in azimuth, every
> elevation unchanged: what happens to HDOP, VDOP, EDOP and NDOP? (`PREDICT_STREET`) In a street that runs
> north–south, the buildings hide everything except the sky along the street and near the zenith. Which is
> larger, EDOP or NDOP, and why? (`PREDICT_LOW`) A 7th satellite appears in the open sky, low (12°) in the
> east-south-east. Which drops more, HDOP or VDOP?

```bash
python3 run_gnss.py sky
```

Open `out/sky.png` beside the numbers.

> [!TASK]
> Write `STREET_EDOP`, `STREET_NDOP` (two decimals) and `EXPLAIN_STREET`: why is the error so much larger in
> one direction? Compare with the ellipse of lesson §5's figure: in which direction is the error long there,
> and why is the street different?
>
> Part 4 added one satellite **low** in the east-south-east. Write `EXPLAIN_LOW`: why does VDOP fall much
> more than HDOP, although the new satellite is almost on the horizon? (Lesson §5, fact 1: look at its −u_U.)

<details><summary>Stuck? Hints, one at a time</summary>

1. `[[-0.1379, 0.0691, 0.988, 1.0]]`: `np.sin` and `np.cos` got degrees — `np.radians` first.
   `+0.866` instead of `−0.866`: a row is [−u_E, −u_N, −u_U, 1].
2. North and East swapped (a satellite due east gives −0.866 in the North column): East = cos el · **sin** az.
3. HDOP 1.33 instead of 1.155: you forgot the square root. HDOP 2.517: you added Q_UU (that is PDOP).
4. The `test` line "without the overhead satellite" shows numbers (VDOP about 9.5e+07) instead of `None`: your
   `try … except` around `inv` does not see this singular matrix. Test `np.linalg.matrix_rank(G) < 4` before
   inverting.
5. Three satellites crash with `LinAlgError` or give numbers: fewer than 4 satellites → `None` first.
</details>

## Step 7 — The receiver's DOPs, recomputed

The receiver wrote its own PDOP, HDOP and VDOP in every GSA. The runner groups the log into seconds, takes the
satellites **used** (your `parse_gsa`) and where they are (the given `parse_gsv`), and recomputes the DOPs
with **your** `dops`:

```bash
python3 run_gnss.py dop
```

Open `out/dop_timeline.png`. Find the port (the first minutes), the underpass (the gap near minute 8: why is
there no DOP there?) and the town at the end (why so few satellites?).

> [!TASK]
> Write `DOP_MAX_DIFF` (the largest of the three differences: HDOP, PDOP, VDOP) and `HDOP_MAX`. Why is the difference not exactly 0?
> (Look at how many decimals GSA writes.)

<details><summary>Open after you answered</summary>
The receiver computed its DOPs from the same whole-degree azimuths and elevations it wrote in GSV, then wrote
them with two decimals: rounding to 0.01 moves a value by at most 0.005. Your largest difference is that
rounding: your geometry is the receiver's. (Here the log is synthetic and its receiver used exactly these
rounded angles. A real receiver computes from its exact orbits, and may weight satellites by elevation or
signal: expect differences of a few hundredths or more — see Going further.)
</details>

## Step 8 — The judge (TODO 8, TODO 9, TODO 10)

**TODO 8** `fix_decision(gga)`: the lesson §6 table, rule by rule, in the order of the docstring.
**TODO 9** `covariance_from_hdop(hdop)`: lesson §6; nine numbers, **variances** (σ², not σ). A HDOP that is
`None`, `nan`, 0 or negative is an unknown accuracy (🧰 `math.isfinite(x)` is False for `nan` and `inf`).

**TODO 10** `fix_state(gga, fix_max_sigma_m=25.0)`: the least guided function. Before you write it, trace
these four by hand with the docstring: quality 1 and HDOP 12.5; quality 1 and HDOP 13; quality 2 and no
HDOP; quality 6 and HDOP 0.9. Which state and which reason each? Then make your code do exactly that, using
your two previous functions.

```bash
python3 run_gnss.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Quality 6 gives "no satellite fix (quality 6)": test quality 6 **before** the general rule. Quality 1
   without a latitude gives "no satellite fix (quality 1)": quality first, then the position.
2. `cov[0]` is 1.44 for HDOP 0.72: that is σ, and a covariance holds σ² (2.0736). The Up entry is
   (2σ)² = 4σ², not 2σ².
3. HDOP 12.5 gives DEGRADED: σ = 25.0 m is still FIX (σ ≤ 25 m) — `>`, not `>=`. The reason "σ 25.2 m > 25.0
   m": one decimal for both numbers, `f"{x:.1f}"`.
4. `fix_state(None)` crashes with `'NoneType' object has no attribute 'get'`: ask `fix_decision` first — it
   already handles `None`.
</details>

> [!TASK]
> **Predict** (`PREDICT_STATES`): of the drive's 1069 seconds, about how many will be FIX, DEGRADED and
> NO_FIX? Then run the whole drive through your judge:

```bash
python3 run_gnss.py drive
```

Open `out/drive.png`. The runner also runs mission 01's jump gate on what your GNSS part let through.

> [!TASK]
> Write `N_FIX`, `N_DEGRADED`, `N_NO_FIX`, `SIGMA_MAX_M`, `JUMP_UTC` (the first position the jump gate
> refuses, `"hhmmss"`) and `EXPLAIN_JUMP`: why did every check of `gnss.py` accept that line, what σ did it
> state, and which part of a navigation stack refuses it?

<details><summary>Read this after you wrote EXPLAIN_JUMP</summary>
σ = 2 m × HDOP describes the <b>noise</b> of a healthy receiver. It says nothing about a line damaged on the
way, or about a spoofer: both come with a small, confident σ. That is why NAVERA's judge never trusts a σ
alone: the jump gate (mission 01) and the cross-check with an independent source (mission 30) look at where
the position <b>can</b> be.
</details>

## Step 9 — The memo

Write [report.md](file:./report.md) (150–350 words, your own words, keep the three headings): what the wire
did to the drive, what the sky did to σ, and what your GNSS part cannot see. Quote your numbers.

> [!TASK]
> report.md has the three headings, at least 150 words, and quotes the refused lines, the largest σ (or
> HDOP), the number of FIX seconds and the time of the jump.

## Step 10 — Check, then look back

Press **✔ Check my work**: it also runs your whole chain `is_valid → parse_gga → fix_state` on a drive log
you have never seen (another sky, other damage, a multi-system receiver). When every check passes, you earn
the **Fix judge** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, the difference between a damaged line, a guessing receiver
   and a bad geometry, and what NAVERA Lite does with each.
2. Which of your predictions was the most wrong? What did you assume?
3. NAVERA assumes a 2 m range error. How would you measure the real one for its receiver, and what would you
   need?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Elevation weighting.** Receivers trust high satellites more (less atmosphere, less multipath). With
  W = diag(sin²(el)), the weighted Q is (GᵀWG)⁻¹. How does HDOP change in the alley of the drive? (The
  receiver's DOPs are unweighted, so they will no longer match.)
- **A property test** (mission 14): with `hypothesis`, change one random character of a valid sentence and
  assert `is_valid` is False; swap two different characters of the body and assert it stays True. Explain
  both results with XOR. Then change the case of two letters (`GPGSA` → `gpgsA`…): when does the checksum
  stay the same, and why? (Hint: `ord("g") − ord("G")`.)
- **An RMC cross-check.** Write `parse_rmc(line)` and compare the GGA and RMC positions of the same second.
  Which damaged lines does it catch that the checksum does not? What does it **not** catch?
- **Why HDOP does not rotate.** Prove that turning every azimuth by α leaves HDOP and VDOP unchanged but not
  EDOP and NDOP. (Hint: the turn acts on G's first two columns as G·R′ with R′ orthogonal, and
  (GR′)ᵀ(GR′) = R′ᵀ GᵀG R′; the trace of a block is invariant under such a similarity.)
- **Elevation trade-off.** Six satellites evenly spread in azimuth at one elevation e, plus one at the
  zenith: plot PDOP for e from 5° to 85°. Geometry prefers low satellites; the atmosphere and multipath do not.
  If each range error grew like 2 m / sin e, which e would give the smallest position error?
- **Fly your own parts.** Replace the given `geo.py` with yours from mission 06:
  `cp ../06-coordinates/navera_lite/geo.py navera_lite/ && python3 run_gnss.py drive`. Same numbers?
