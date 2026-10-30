# 🧰 Toolbox — reusable boxes for authors

Copy a box into a lesson or lab **just before** the first task that needs it (AUTHORING.md: "teach the
tool before the task"). Each box is short, uses numbers that are **not** any mission's exercise, and
every number was run in Python 3.10 / numpy 1.26 on the Jetson. Change the numbers if they collide
with a mission's prediction (no spoilers). Python boxes go in the lab as
`<details><summary>🧰 …</summary> … </details>`; maths boxes go in the lesson as `> [!TIP] 🧰 …`.

---

### Python 1 — functions, tuples, `zip`, default arguments

```python
def middle(p, q):                  # p and q are points: p[0] is x, p[1] is y
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)     # a tuple: two values in one

mx, my = middle((0, 0), (4, 2))    # "unpacking": mx = 2.0, my = 1.0
for name, km in zip(["A", "B"], [5.0, 8.1]):          # zip walks two lists together
    print(name, km)                # A 5.0, then B 8.1

def speed(d_m, t_s=1.0):           # t_s has a default: speed(30) means speed(30, 1.0)
    return d_m / t_s
```

### Python 2 — lists, `append`, slicing

```python
xs = []                            # an empty list, created BEFORE the loop
for v in (3, 1, 4):
    xs.append(v * 2)               # xs is now [6, 2, 8]
xs[0], xs[-1]                      # 6 and 8 (−1 = the last one)
xs[1:3], xs[:2]                    # [2, 8] and [6, 2]: the end index is NOT included
len(xs), sum(xs) / len(xs)         # 3 and 5.33…
```

### Python 3 — dicts, `None`, `continue`

```python
row = {"t": 2.0, "lat": 35.83, "lon": None}   # a dict: names → values
row["lat"]                         # 35.83
row.get("alt")                     # None: the key is absent (row["alt"] would crash with KeyError)
for r in rows:
    if r["lon"] is None:           # "no value": test with `is None`, not == 0
        continue                   # skip this row, go to the next one
    ...
```

### Python 4 — reading a CSV file

```python
import csv
rows = []
with open("flight.csv") as f:
    for r in csv.DictReader(f):    # one dict per line, keys from the header line
        rows.append(float(r["lat"]))           # every value arrives as TEXT: convert it
```

With numpy, for a file of numbers only: `data = np.loadtxt("flight.csv", delimiter=",", skiprows=1)`,
then `data[:, 0]` is the first column. An empty cell breaks `loadtxt`; use the `csv` version then.

### Python 5 — numpy arrays, `solve`/`lstsq`, `matrix_rank`, `inv`

```python
import numpy as np
A = np.array([[2.0, 1.0], [1.0, 3.0]]); b = np.array([3.0, 5.0])
A @ b                       # matrix × vector (NOT A * b, which multiplies element by element)
np.linalg.solve(A, b)       # [0.8 1.4]: solves 2x + y = 3 and x + 3y = 5
np.linalg.inv(A)            # [[0.6 −0.2] [−0.2 0.4]]; inv(A) @ b gives the same [0.8 1.4]
x, *_ = np.linalg.lstsq(H, r, rcond=None)   # more equations than unknowns: best fit
np.linalg.matrix_rank(np.array([[1, 2], [2, 4]]))   # 1: the rows are parallel, no unique solution
```

`lstsq` returns **four** things (solution, residuals, rank, singular values): keep the first with
`x, *_ = …`. Forgetting it gives `ValueError: … inhomogeneous shape` or "could not be broadcast"
when you then add it to an array. A list has no `.T`: write `H = np.array(H)` first.

### Python 6 — dataclasses (first needed in mission 12)

```python
from dataclasses import dataclass, field, replace, asdict

@dataclass                         # writes __init__, __repr__ and == for you, from the fields below
class Reading:
    sensor: str                    # a field without default: required
    value: float
    t_s: float = 0.0               # fields with a default come AFTER those without
    tags: list = field(default_factory=list)   # a list default: never `= []` (it would be shared)

r = Reading("baro", 1013.2)        # Reading(sensor='baro', value=1013.2, t_s=0.0, tags=[])
r.value, r.t_s                     # 1013.2 and 0.0
r == Reading("baro", 1013.2)       # True: compared field by field
r2 = replace(r, value=1009.8)      # a copy with one field changed; r.value is still 1013.2
asdict(r)                          # {'sensor': 'baro', 'value': 1013.2, 't_s': 0.0, 'tags': []}
```

The type after `:` is a note for the reader: Python does not check it (`Reading("baro", "high")` is
accepted). Check the values yourself where it matters, and raise `ValueError` with a clear sentence.

### Python 7 — packages and `python3 -m` (first needed in mission 09)

```
lessons/09-ros-intro/              ← run commands from HERE (the folder that holds the package)
  weather/                         a package: a folder with an __init__.py
    __init__.py                    runs once, at the first `import weather…`
    units.py                       def c_to_f(c): return c * 9 / 5 + 32
    report.py                      from weather.units import c_to_f   (absolute import)
```

```bash
python3 -m weather.report          # 70.7 — "run the module weather.report": dots, no .py
python3 weather/report.py          # ModuleNotFoundError: No module named 'weather'
cd weather && python3 -m weather.report   # same error: weather/ must be in the CURRENT folder
```

`python3 -m` puts the current folder first on Python's search path, so `from weather.units import …`
finds the package wherever the module lives. Running the file by its path puts only the file's own
folder (`weather/`) on the path, where there is no `weather` package. NAVERA Lite works the same way:
`python3 -m navera_lite.ros.arbiter_v0` from the lesson folder.

---

### Maths 1 — scientific notation

`6.371e6` = 6.371 × 10⁶ = 6 371 000 (the Earth's radius in metres). `3.36e-05` = 0.0000336, still
larger than `1e-6` = 0.000001. Light travels 3.0e8 m/s × 1e-6 s = **300 m** in one microsecond.
In code, `1.08e-07` printed for a value that should be 0 is zero up to rounding.

### Maths 2 — decibels: dB and dBm

A **ratio** in decibels is `10 · log10(P1 / P0)`: ×2 ≈ +3 dB, ×10 = +10 dB, ×1000 = +30 dB; dB add
where powers multiply. **dBm** is a power compared with 1 mW: 0 dBm = 1 mW, 30 dBm = 1 W,
40 dBm = 10 W, −130 dBm = 10⁻¹⁶ W (about the strength of a GPS signal at the ground).
Back to watts: `P_mW = 10 ** (dBm / 10)`.

### Maths 3 — dot product

`a · b = aₓbₓ + a_y b_y = |a| |b| cos θ`. With a = (3, 4), b = (1, 0): a · b = 3, |a| = 5, so
cos θ = 3/5 and θ = 53.1°. a · b = 0 means perpendicular; for a unit vector u, `a · u` is the
length of a's shadow along u. In numpy: `a @ b` or `np.dot(a, b)`.

### Maths 4 — derivative of a distance

`d = √((x − sₓ)² + (y − s_y)²)` gives `∂d/∂x = (x − sₓ)/d`, `∂d/∂y = (y − s_y)/d`: the unit vector
from s towards the point. Check at p = (6, 8), s = (0, 0): d = 10, gradient (0.6, 0.8); moving 0.1
east gives d = 10.060, i.e. +0.060 = 0.6 × 0.1. Moving straight away changes d fully, moving
sideways barely.

### Maths 5 — variance vs standard deviation

For the values 2, 4, 4, 4, 5, 5, 7, 9: mean 5, **variance** σ² = mean of (x − mean)² = 4 (unit²:
m²), **standard deviation** σ = √4 = 2 (unit: m — the size of a typical error). Independent errors add
their **variances**, not their σ: σ = 3 m and σ = 4 m together give √(9 + 16) = 5 m. numpy:
`np.var(x)` = 4.0, `np.std(x)` = 2.0 (divides by n); `np.std(x, ddof=1)` = 2.14 (divides by n − 1,
the "sample" version). Say which one you use.

### Maths 6 — matrix × vector by hand

Each output number is one **row** times the vector:

```
| 1  2 |   | 5 |   | 1·5 + 2·6 |   | 17 |
| 3  4 | · | 6 | = | 3·5 + 4·6 | = | 39 |
```

The rotation by +90° (counter-clockwise) `[[0, −1], [1, 0]]` turns (2, 1) into (−1, 2). The order
matters: A·B ≠ B·A in general. numpy: `A @ v`.
