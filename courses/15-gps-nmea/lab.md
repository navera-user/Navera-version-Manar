# Lab 15 — Read a GPS log like NAVERA does

**Goal:** write your own NMEA reader — checksum, GGA parser, degrees-minutes conversion — check it
against the parser NAVERA really uses, find the damaged lines of a real-looking log, measure the length
of the drive, and finally watch NAVERA's own GPS driver read the same log.
**Time:** about 1 hour 15 minutes.

Your files:

| File | What |
|---|---|
| [nmea_tools.py](file:./nmea_tools.py) | **your work**: 6 functions with `TODO`s |
| [drive.nmea](file:./drive.nmea) | the log: a car driving a 3 km loop in M'saken, 287 seconds, 1 report per second |
| `compare_with_navera.py` | compares your parser with NAVERA's (ready, don't change) |
| `track_report.py` | a report and a map of the drive made with your functions (ready) |
| `play_to_gps_node.py` | plays the log into NAVERA's real GPS driver (ready) |
| [answers.py](file:./answers.py) | 4 quiz questions |

> [!NOTE]
> `drive.nmea` was made by a **simulated** receiver (written the same way as NAVERA's simulator,
> `navera_tools/sim/nmea_gps.py`), so we know exactly what is inside. The format is exactly what a real
> u-blox receiver sends — the first lines of the course were read from NAVERA's real one.

## Step 1 — Look at the raw log

```bash
head -12 drive.nmea
```

You see the first seconds: GGA sentences with **empty** positions and quality `0`, and RMC sentences
with status `V` — the receiver has just been switched on and is still looking for satellites. Every
five seconds a GSA and a GSV sentence (satellite lists) come too.

How many sentences of each kind? `grep -c` counts the lines that contain a word:

```bash
grep -c GGA drive.nmea
```

```bash
grep -c RMC drive.nmea
```

Now look at a few lines once the car moves (line 40 to 46):

```bash
sed -n 40,46p drive.nmea
```

Find the fields of the course in them: the time goes up by one second per GGA, the quality is `1`, the
HDOP is below 1.1. Open [drive.nmea](file:./drive.nmea) in the editor and scroll a little.

## Step 2 — The checksum (TODO 1)

Open [nmea_tools.py](file:./nmea_tools.py). First, play with the three Python tools you need, in the
terminal:

```bash
python3 -c "print(ord('G'), ord('N'), ord('G') ^ ord('N'), f'{9:02X}', f'{112:02X}')"
```

`ord` gives the number of a character, `^` is XOR, `:02X` writes a number in hexadecimal with 2 digits.
You should see `71 78 9 09 70`.

> [!TASK]
> **TODO 1** — write `nmea_checksum(body)`: start with `c = 0`, XOR every character's `ord()` into it,
> and return `f"{c:02X}"`. The body is the text **between** `$` and `*` (without them).

Run the demo at the bottom of the file:

```bash
python3 nmea_tools.py
```

The first line must say `checksum of the textbook example: 47 (should be 47)`.

## Step 3 — Accept or refuse a line (TODO 2)

A line from the wire still has its `$`, its `*hh` and its `\r\n`. `is_valid(line)` must:

1. remove spaces and `\r\n` at both ends: `line = line.strip()`;
2. refuse (return `False`) a line that does not start with `$` or has no `*`;
3. cut it in two at the first `*`: `body, given = line[1:].split("*", 1)`;
4. refuse it if `given` is not exactly 2 characters long;
5. return whether `nmea_checksum(body) == given.upper()`.

> [!TASK]
> **TODO 2** — write `is_valid(line)`. It must return `True` or `False` — never `None`, never crash.

Now hunt the damaged lines of the log. This one-line program prints how many lines are refused, then
the refused lines themselves:

```bash
python3 -c "import nmea_tools as t; bad = [l for l in open('drive.nmea').read().splitlines() if not t.is_valid(l)]; print(len(bad)); print(*bad, sep='\n')"
```

You should find **6** lines. Look at each one and say what went wrong on the wire:

- a line **cut** after 31 characters — the rest never arrived;
- a line with **no `*hh`** at the end — the checksum was lost;
- a line with `*ZZ` — not even hexadecimal: **garbage**;
- **three** lines that look complete — but one character changed on the way, so the checksum doesn't
  match. In one of them you can see the damage. Print the GGA and the RMC of that second:

```bash
grep -n 093221 drive.nmea
```

The RMC (same second, line 474) says `3544.38407`, the GGA says `3544738407`: the dot became a `7`.
For the two others, compare each GGA with the RMC just below it:

```bash
sed -n 72,73p drive.nmea
```

On line 72 the latitude `3544.04329` became `3544.74329`: 0.7 minute of latitude, a jump of **1.3 km**
in one second. Without the checksum, the car would have "teleported". (Line 737 has the same kind of
damage — find it.)

### The line that fools the checksum

Now look at line 327:

```bash
sed -n 327p drive.nmea
```

Two sentences are **glued** together: the end of a GGA was lost, and the RMC that followed was stuck on
it. Yet `is_valid` says `True`! By pure luck the XOR of the lost part is zero, so the checksum still
matches — the **1-in-256** case of the course. Keep this line in mind for step 5.

## Step 4 — Degrees and minutes (TODO 3)

> [!TASK]
> **TODO 3** — write `dm_to_deg(value, hemisphere)`:
> `"3544.04006", "N"` → `35.734001`; `"01034.55091", "E"` → `10.5758485`; `S` and `W` give negative
> numbers; an empty or unreadable value gives `None`.
> Use `to_float(value)` (already written below the line) to read the number: it returns `None` for
> `""` or garbage. Then `degrees = int(v // 100)`, `minutes = v - degrees * 100`.

Try it:

```bash
python3 -c "import nmea_tools as t; print(t.dm_to_deg('3544.04006','N'), t.dm_to_deg('4807.038','S'), t.dm_to_deg('','N'))"
```

Expected: `35.734001 -48.1173 None` (Python may print a few more digits, like `35.73400100000001` —
that is normal: computers store decimals with tiny rounding errors).

## Step 5 — Read a whole GGA sentence (TODO 4)

`parse_gga(line)` returns a **dictionary** (lesson 4) with the keys listed above TODO 4:
`time, lat, lon, quality, sats, hdop, alt_msl, geo_sep`.

1. If the line is not valid (TODO 2), return `None`.
2. Take the body between `$` and `*`, split it on `","` → a list `f`.
3. If `f[0]` does not end with `"GGA"` (it can be `GPGGA`, `GNGGA`…), return `None`.
4. Build the dictionary: `"lat": dm_to_deg(f[2], f[3])`, `"quality": to_int(f[6])`,
   `"hdop": to_float(f[8])`… (field numbers are in the comment and in the course's table).

> [!TASK]
> **TODO 4** — write `parse_gga(line)`. A "no fix" sentence such as
> `$GNGGA,093000.00,,,,,0,00,99.99,,,,,,*72` must give a dictionary with `quality` 0 and
> `lat`/`lon` `None` — not a crash.

Test it on the real receiver's sentence (the demo does it) and on the tricky glued line 327:

```bash
python3 nmea_tools.py
```

```bash
python3 -c "import nmea_tools as t; print(t.parse_gga(open('drive.nmea').read().splitlines()[326]))"
```

Look at the glued line's dictionary: the longitude field contained `01035.1016$GNRMC`, which is not a
number → `None`; the quality field contained `A` → `None`. Your parser did not crash, and this line
will never count as a usable fix. NAVERA's driver survives it the same way: its `int(msg.gps_qual)`
fails on `"A"`, so the quality becomes 0 and the line is published as "no fix".

## Step 6 — Compare with NAVERA's parser

NAVERA does not use a home-made parser: `gps_node.py` uses the **pynmea2** library with `check=True`
and keeps qualities 1, 2, 4 and 5. Open [gps_node.py](file:navera/gps_pkg/gps_pkg/nodes/gps_node.py)
and find `_read_loop` and `_publish_fix`. The script `compare_with_navera.py` does exactly what they do,
next to your functions, for every line of the log:

```bash
python3 compare_with_navera.py
```

Goal: **6** lines rejected and **261** usable fixes on both sides, a largest difference around
`1e-14` degrees (a rounding error, a few billionths of a millimetre), and the message
"No difference". If there are differences, the script prints the first lines where you disagree — fix
your code and run it again.

## Step 7 — Usable fixes and the length of the drive (TODO 5 and 6)

> [!TASK]
> **TODO 5** — `usable_fixes(path)`: open the file, run `parse_gga` on every line, and keep `(lat, lon)`
> only when the result is not `None`, its quality is in `USABLE_QUALITIES` and lat/lon are not `None`.
> **TODO 6** — `track_length_m(points)`: add the `haversine_m` distances (lesson 6) between each point
> and the next. With 0 or 1 point the length is 0.

Tip for TODO 6: `zip(points, points[1:])` gives the pairs (point 0, point 1), (point 1, point 2), …

```bash
python3 track_report.py
```

You should read **261 usable fixes** and a track of about **3034.6 m**. Open `track.png` in the file
list: blue dots are GPS fixes, green dots DGPS fixes (quality 2), and on the east side you see **red**
dots: 12 seconds where the car drove under a bridge and the receiver *guessed* (quality 6). They are
drawn so you can see them, but they are **not** in the track: the grey line jumps straight across.

> [!QUESTION]
> If you added the red points, the track would be about 3052 m — 17 m longer. Which number is closer
> to the truth? Here the guesses happen to be good; but a receiver's guess can also be very wrong, and
> NAVERA has no way to check it. That is why it refuses them.

## Step 8 — Watch NAVERA's real GPS driver read your log

Now the best part: the **real** `gps_node` from your NAVERA copy will read `drive.nmea` as if a receiver
were plugged in. The script creates a fake serial port (a "pseudo-terminal" — NAVERA's own test
`test_gps_serial.py` uses the same trick), starts `ros2 run gps_pkg gps_node.py` on it, writes the log
into it 25 times faster than real time, and counts the `PositionEstimate` messages on
`/navera/estimate/gps`. It takes about 20 seconds:

```bash
python3 play_to_gps_node.py
```

Expected result:

```
gps_node published 282 PositionEstimate messages:
  valid (usable fix): 261
  invalid           : 21
       12 x  receiver reports a non-satellite position (qual=6) — not used
        9 x  no GPS fix (qual=0)
```

Compare with your own report: the **same 261** fixes. 282 is the number of GGA sentences that passed
the checksum (281 good ones + the glued line). The 9 "no fix" are the 8 seconds at power-on **plus**
the glued line. The 6 broken lines produced nothing at all — they never left `_read_loop`.

> [!TIP]
> The first valid fix shows `altitude 127.5 m (ellipsoid)`: the GGA said 95.4 m above sea level, and
> `gps_node` added the geoid separation 32.1 m — the "two kinds of altitude" of the course.

## Step 9 — Quiz

> [!TASK]
> Answer the 4 questions in [answers.py](file:./answers.py).

Press **✔ Check my work**. Each red line has a hint; fix, save and check again.

## Going further (optional)

1. **Speed from RMC.** Write `parse_rmc(line)` that returns the speed in m/s (knots × 0.514444) and the
   course. Then compute the velocity towards east and north like `_publish_vel` in `gps_node.py`. Is
   the RMC speed the same as the distance between two consecutive fixes divided by 1 second?
2. **Break it yourself.** Copy a good GGA line, change one digit of the latitude, and give it to
   `pynmea2.parse(line, check=True)` in Python. Which error does it raise? Then change **two**
   characters so that the checksum still matches (hint: XOR of the two changes must be 0 — for
   example `'1'`→`'3'` in one place and `'3'`→`'1'` in another).
3. **Read the simulator's receiver.** Open `~/navera/navera_tools/sim/nmea_gps.py`: find its checksum
   function `_cs` and its `_lat` function. How does it write degrees-minutes — the opposite of your
   `dm_to_deg`? What does it send when the mode is `jammed`?
