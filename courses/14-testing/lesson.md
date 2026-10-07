# Testing code like an engineer

Imagine: a drone flies over the sea with NAVERA on board. Yesterday, an engineer made a small change to a
function that checks whether a position is real. He tried it on his desk: it worked. But he did not
notice that the function now accepts the position (0, 0) — the "Null Island" value of a GPS field
nobody filled. Today, a sensor glitch sends (0, 0)… and NAVERA believes it.

How do you make sure that a change in one place does not break something somewhere else — in a
program of tens of thousands of lines, written by several people, over years? You cannot try
everything by hand after every change. You write **tests**: small programs that check your program,
automatically, in seconds, every time. NAVERA has **359 of them** for its non-ROS logic alone (you
will run them all in the lab), and they would have caught yesterday's bug in under one second.

## What a test is

A **test** is a function that runs a piece of your code with a known input and checks the result:

```python
def test_one_degree_of_latitude():
    d = haversine_m(35.0, 10.0, 36.0, 10.0)    # run the code
    assert d == pytest.approx(111_195, rel=1e-3)   # check the result
```

`assert` is a Python keyword: `assert condition` does nothing if the condition is true, and stops
with an **AssertionError** if it is false. A test **passes** when it reaches its end without error,
and **fails** otherwise.

Good tests check what the code **promises**, with values you know independently: 1 degree of
latitude is about 111 195 m (you computed it in lesson 6), (0, 0) must be refused (it is written in
the function's docstring), 100 m in 20 s is 5 m/s (a child can check it).

## pytest

**pytest** is the tool that finds and runs tests. Its rules are simple:

- test files are named `test_something.py`;
- test functions are named `test_something()`;
- you run `python3 -m pytest` followed by a file or a folder.

```bash
python3 -m pytest -v test_geo_tools.py
```

`-v` (*verbose*) prints one line per test with `PASSED` or `FAILED`; `-q` (*quiet*) prints one dot
per passing test and an `F` per failure. At the end, a summary: `9 passed in 0.12s`.

### Comparing decimal numbers

Never compare floats with `==`. Computers store decimals with tiny rounding errors:
`0.1 + 0.2 == 0.3` is **False** in Python! Use `pytest.approx`:

```python
assert 0.1 + 0.2 == pytest.approx(0.3)                 # True
assert d == pytest.approx(111_195, abs=50)             # within ± 50 m
assert d == pytest.approx(111_195, rel=1e-3)           # within ± 0.1 %
```

Choose the tolerance like an engineer: tight enough to catch a real mistake (a missing `cos()` is a
20 % error), loose enough to accept honest rounding.

### Checking None, True, False

`is` checks that it is *exactly* that object: `assert speed_mps(100, 0) is None`,
`assert is_valid_position(0.0, 0.0) is False`. (With `== False`, a function returning `0` would pass.)

### Many cases, one test

When the same check applies to many inputs, `@pytest.mark.parametrize` runs the test once per case:

```python
@pytest.mark.parametrize("lat, lon", [(0.0, 0.0), (91.0, 10.0), (math.nan, 10.0)])
def test_invalid_positions(lat, lon):
    assert is_valid_position(lat, lon) is False
```

pytest counts this as 3 tests, and if one fails, its name tells you which case:
`test_invalid_positions[0.0-0.0]`.

## Reading a failing test

When a test fails, pytest shows you exactly what went wrong. Here is a real failure from NAVERA's
own tests (you will produce it yourself in the lab):

```
_____________________ test_is_finite_latlon[0.0-0.0-False] _____________________
lat = 0.0, lon = 0.0, ok = False
    def test_is_finite_latlon(lat, lon, ok):
>       assert is_finite_latlon(lat, lon) is ok
E       assert True is False
E        +  where True = is_finite_latlon(0.0, 0.0)

navera_common/test/test_geo.py:62: AssertionError
```

Read it from top to bottom:

1. **The name** — `test_is_finite_latlon` with the case `[0.0-0.0-False]`: the inputs were (0, 0)
   and the expected answer `False`.
2. **The `>` line** — the line of the test that failed.
3. **The `E` lines** — the explanation: the function returned `True` where `False` was expected,
   and pytest even shows the call: `is_finite_latlon(0.0, 0.0)`.
4. **The file and line** — where to look.

A failing test is not bad news: it is **good news delivered early**. The bug was found on your desk,
in one second, instead of over the sea.

## A test suite must catch bugs

Here is a trap: a test that checks nothing useful still passes. This test of `meters_to_degrees`
passes on correct code…

```python
def test_meters_to_degrees():
    dlat, dlon = meters_to_degrees(0, 0, 35.0)
    assert dlat == 0 and dlon == 0
```

…but it also passes if someone forgets the `cos(latitude)`, or swaps north and east. It gives a
**false feeling of safety**. How do you know your tests are good? You break the code on purpose and
check that a test fails. A wrong copy of the code is called a **mutant**; a mutant that no test
detects has **survived**. This is **mutation testing**, and it is exactly what the checker of this
lesson does with your tests.

![The checker runs your tests on the correct code and on wrong copies of it](assets/mutants.svg)

A useful habit: for every test you write, ask "**which mistake would this test catch?**" If you can't
name one, the test is decoration.

## Separate the logic, test the logic

In lesson 11, you put the trip computer's logic in a class `Tracker` with **no ROS inside**. Now you
see why: a function that takes numbers and returns numbers can be tested in a millisecond, without
starting nodes, waiting for messages or running a simulator. NAVERA is built this way: almost every
decision lives in a plain function, and the ROS node around it is thin. That is why its tests are
split in two groups (see [navera_tools/run_tests.sh](file:navera/navera_tools/run_tests.sh)):

| | Unit tests | Integration tests |
|---|---|---|
| What | one function or class, alone | real nodes started together, talking over ROS |
| Where | `<package>/test/test_*.py` | `navera_tools/tests/test_*.py` |
| Speed | about one minute for all of them | longer: real nodes must start and talk |
| Run with | `navera_tools/run_tests.sh` | `navera_tools/run_tests.sh --integration` |

A **unit test** checks one small unit. An **integration test** checks that the units work together
(the arbiter receiving a real GPS node's messages, for example). You need both — but most tests should
be unit tests, because they are fast and they point at the exact place of a bug.

## 🐦 How birds do it

How do you ask a bird *"which way do you want to go?"* In the 1960s, Stephen Emlen and his father John
Emlen built a simple, clever instrument: the **Emlen funnel**. It is a paper funnel with an ink pad at
the bottom. A migratory bird is put inside at night; it keeps hopping toward the direction it wants to
fly, and its inky footprints mark the paper. In the morning, the scientist counts the marks. It is an
**automatic measurement**: it runs while the scientist sleeps, and it gives the same kind of answer
every time.

Then Emlen tested ideas, one at a time, in a **planetarium**, with indigo buntings (small night
migrants):

1. Show the real star sky → the birds hop in their migration direction.
2. Turn the projected sky → the birds turn with it. *They use the stars.*
3. Raise young birds under a sky that turns around a different star (Betelgeuse) → as adults, they
   treat Betelgeuse as their "north". *They are not born knowing the constellations: they learn the
   centre of rotation of the sky.*

In the 1960s and 1970s, Wolfgang and Roswitha Wiltschko did the same with robins and magnets: turn the
magnetic field with coils, and the robins' preferred direction turns too.

A good experiment is a good test: **change one thing, keep everything else the same, repeat many
times** — and design it so that it **fails** if your idea is wrong.

NAVERA's tests follow the same rules, and run in seconds instead of migration seasons.

## In NAVERA

Open [navera_common/test/test_geo.py](file:navera/navera_common/test/test_geo.py), the tests of the
geography helpers that every NAVERA pipeline shares. Look at how they are written:

```python
@pytest.mark.parametrize("lat, lon, ok", [
    (35.8, 10.6, True), (-89.9, -179.9, True), (0.0, 0.0, False),
    (float("nan"), 1.0, False), (91.0, 0.0, False), (0.0, 181.0, False),
    (None, 1.0, False), ("x", 1.0, False)])
def test_is_finite_latlon(lat, lon, ok):
    assert is_finite_latlon(lat, lon) is ok
```

Eight cases in five lines — including strange inputs like `None` and `"x"`, because a function that
receives data from sensors must survive anything. And this one:

```python
def test_stationary_vehicle_does_not_move():
    # The old code floored every step at 120 m.
    out = dead_reckon(35.83, 10.64, 45.0, 0.0, 30.0)
    assert haversine_m(35.83, 10.64, *out) < 1e-6
```

Read the comment: **the old code had a bug** (a stopped vehicle was moved 120 m at every step). When
the bug was fixed, a test was added so that it can **never come back** unnoticed. Such a test is called
a **regression test** — a *regression* is a bug that returns. Many tests in NAVERA tell a story like
this one; reading them is a great way to learn what can go wrong in navigation.

Finally, notice that `test_geo.py` has its own small copy of `haversine_m` at the top, to compute the
expected distances **independently** of the code under test. Testing a function with itself proves
nothing!

## Words to remember

| Word | Meaning |
|---|---|
| **test** | a small function that runs code with known inputs and checks the result |
| **assert** | "this must be true" — stops with an AssertionError when it is false |
| **pytest** | the tool that finds `test_*.py` files and runs their `test_*` functions |
| **pass / fail** | the test reached its end / an assert (or an error) stopped it |
| **pytest.approx** | compare decimal numbers with a tolerance |
| **parametrize** | run one test with many cases |
| **unit / integration test** | one piece alone / several pieces working together |
| **regression test** | a test written after a bug, so that it can never return unnoticed |
| **mutant / mutation testing** | a wrong copy of the code / checking that the tests catch such copies |

## Check what you learned

<details><summary>1. Why is <code>assert haversine_m(...) == 111195.0</code> a bad test?</summary>
Decimal results carry tiny rounding errors, and 1° of latitude is only <i>about</i> 111 195 m. Use
<code>pytest.approx(111_195, rel=1e-3)</code>.
</details>

<details><summary>2. All your tests pass. Does that prove your code has no bug?</summary>
No. It proves the code does what your tests check — nothing more. If no test checks (0, 0), a bug
with (0, 0) passes. Mutation testing measures how many bugs your tests would catch.
</details>

<details><summary>3. In NAVERA, breaking <code>is_finite_latlon</code> also made a test of <code>dead_reckon</code> fail. Why?</summary>
<code>dead_reckon</code> calls <code>is_finite_latlon</code> to refuse an invalid start. One bug in a
shared helper can break every function that uses it — which is why shared code needs good tests.
</details>

<details><summary>4. What is a regression test? Find one in test_geo.py.</summary>
A test added after fixing a bug, so the bug cannot return unnoticed:
<code>test_stationary_vehicle_does_not_move</code> ("The old code floored every step at 120 m").
</details>

Now open the **🛠️ Lab** tab.
