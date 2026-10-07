"""Lesson 14 checker: your tests must PASS on correct code and FAIL on wrong code ("mutants")."""
import os
import re
import shutil
import tempfile

from academy_check import Checker, sh

c = Checker()
HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = open(os.path.join(HERE, "files", "geo_tools.py")).read()    # the correct geo_tools.py
NAV_GEO = "navera_common/navera_common/geo.py"
STUDENT_TESTS = ["test_geo_tools.py", "test_properties.py"]

# Wrong versions of geo_tools.py: (name, text to find, replacement, what a good test checks)
MUTANTS = {
    "haversine_m": [
        ("forgets the radians", "dp = math.radians(lat2 - lat1)", "dp = lat2 - lat1",
         "a known distance, e.g. 1 degree of latitude ≈ 111 195 m"),
        ("returns kilometres", "return 2 * EARTH_RADIUS_M * math.asin", "return 2 * 6371.0 * math.asin",
         "a known distance in METRES"),
        ("ignores the longitude", "dl = math.radians(lon2 - lon1)", "dl = 0.0",
         "a distance between two points on the same latitude (east-west)"),
    ],
    "meters_to_degrees": [
        ("forgets cos(latitude)", "m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat_deg))",
         "m_per_deg_lon = m_per_deg_lat", "a move EAST at a latitude far from 0 (e.g. 60°)"),
        ("swaps north and east", "return north_m / m_per_deg_lat, east_m / m_per_deg_lon",
         "return east_m / m_per_deg_lon, north_m / m_per_deg_lat", "a move north only: dlon must stay 0"),
    ],
    "is_valid_position": [
        ("accepts (0, 0)", "return not (lat == 0.0 and lon == 0.0)", "return True", "(0, 0) is refused"),
        ("accepts a latitude of 91", "-90.0 <= lat <= 90.0 and ", "", "a latitude above 90 is refused"),
        ("accepts NaN",
         "    if not (math.isfinite(lat) and math.isfinite(lon)):\n        return False\n"
         "    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):\n",
         "    if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:\n", "math.nan is refused"),
    ],
    "speed_mps": [
        ("divides by zero", "    if dt_s <= 0:\n        return None\n", "", "dt = 0 gives None"),
        ("is upside down", "return distance_m / dt_s", "return dt_s / distance_m", "100 m in 20 s is 5 m/s"),
    ],
    "properties": [
        ("haversine uses cos(lat1)² (asymmetric)", "math.cos(p1) * math.cos(p2)", "math.cos(p1) ** 2",
         "SYMMETRY with two points at different latitudes"),
        ("latlon_to_offset uses the target's latitude", "math.cos(math.radians(lat0))", "math.cos(math.radians(lat))",
         "the ROUND TRIP with a move both north and east"),
    ],
}

NAV_MUTANTS = [
    ("is_finite_latlon accepts (0, 0)", "return not (lat == 0.0 and lon == 0.0)", "return True",
     "is_finite_latlon(0.0, 0.0) is False"),
    ("is_finite_latlon accepts NaN",
     "    if not (math.isfinite(lat) and math.isfinite(lon)):\n        return False\n"
     "    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):\n",
     "    if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:\n",
     "is_finite_latlon(math.nan, 10.0) is False"),
    ("haversine_m in kilometres", "return 2 * 6_371_000.0 * math.asin", "return 2 * 6_371.0 * math.asin",
     "1 degree of latitude ≈ 111 195 m"),
    ("dead_reckon ignores dt", "d = spd * dt / EARTH_RADIUS_M", "d = spd / EARTH_RADIUS_M",
     "10 m/s during 10 s moves 100 m"),
    ("dead_reckon accepts a negative speed", "if spd < 0.0 or dt <= 0.0 or", "if dt <= 0.0 or",
     "a negative speed returns None"),
]


def pytest_in(folder, files, env=""):
    """Run pytest on test files in `folder`; returns (exit code, output)."""
    return sh(f"cd {folder} && {env} python3 -m pytest -q -p no:cacheprovider -x {' '.join(files)}", timeout=150)


def count_tests(out):
    m = re.search(r"(\d+) passed", out)
    return int(m.group(1)) if m else 0


def run_with(geo_source, files=STUDENT_TESTS):
    """Copy the student's test files next to `geo_source` (a version of geo_tools.py) and run them."""
    for f in files:
        c.file_exists(f)
    d = tempfile.mkdtemp(prefix="mut_")
    try:
        for f in files:
            shutil.copy(f, d)
        with open(os.path.join(d, "geo_tools.py"), "w") as fh:
            fh.write(geo_source)
        return pytest_in(d, files)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def mutated(source, old, new):
    """`source` with one bug in it (and still valid Python)."""
    assert old in source, f"checker bug: {old!r} not found"
    out = source.replace(old, new)
    compile(out, "mutant.py", "exec")
    return out


GOOD = {}


def good(files):
    key = tuple(files)
    if key not in GOOD:
        GOOD[key] = run_with(REFERENCE, files)
    return GOOD[key]


def need_good_tests():
    code, _ = good(STUDENT_TESTS)
    c.ok(code == 0, "first make all your tests pass on the correct geo_tools.py (checks 2 and 7)")


@c.test("the test files load (pytest can collect them)",
        hint="Run `python3 -m pytest --collect-only -q test_geo_tools.py test_properties.py test_navera_geo.py` "
             "and read the error: a syntax error or a wrong import.")
def _():
    code, out = sh("python3 -m pytest --collect-only -q -p no:cacheprovider "
                   "test_geo_tools.py test_properties.py test_navera_geo.py", timeout=60)
    c.ok(code == 0, "pytest cannot collect your files:\n" + out[-800:])


@c.test("test_geo_tools.py: at least 10 tests, a fixture and a parametrize, all passing on the correct code",
        hint="Run `python3 -m pytest -v test_geo_tools.py`. A test that fails on correct code is a wrong test: check "
             "the expected value (metres? degrees?) and the tolerance. Use the fixture `muscat` in a test of yours.")
def _():
    code, out = good(["test_geo_tools.py"])
    c.ok(code == 0, "pytest says:\n" + out[-900:])
    n = count_tests(out)
    c.ok(n >= 10, f"pytest ran {n} tests in test_geo_tools.py — write at least 10 (parametrized cases count)")
    src = open("test_geo_tools.py").read()
    c.ok(src.count("@pytest.mark.parametrize") >= 2, "use @pytest.mark.parametrize for is_valid_position (TODO 3)")
    c.ok(len(re.findall(r"def test_\w+\([^)]*muscat", src)) >= 2, "use the `muscat` fixture in at least one test of yours")


for func, mutants in MUTANTS.items():
    if func == "properties":
        continue
    todo = {"haversine_m": 1, "meters_to_degrees": 2, "is_valid_position": 3, "speed_mps": 4}[func]

    @c.test(f"TODO {todo} — your tests catch {len(mutants)} wrong versions of {func}()",
            hint="For each wrong version that survived, add a test that the correct code passes and the "
                 "wrong code fails.")
    def _(func=func, mutants=mutants):
        need_good_tests()
        survived = []
        for name, old, new, idea in mutants:
            code, _ = run_with(mutated(REFERENCE, old, new))
            if code != 1:                     # 1 = some test failed: the mutant was caught
                survived.append(f"{func}() that {name} — add a test: {idea}")
        c.ok(not survived, "these wrong versions pass all your tests:\n       - " + "\n       - ".join(survived))


@c.test("TODO 5 — test_properties.py: at least 5 properties (@given), all passing on the correct code",
        hint="Run `python3 -m pytest -v test_properties.py`. Restrict the domain of the validity and round-trip "
             "properties (|lat0| ≤ 80, |lon0| ≤ 170) once you have read hypothesis's counterexample.")
def _():
    code, out = good(["test_properties.py"])
    c.ok(code == 0, "pytest says:\n" + out[-1200:])
    src = open("test_properties.py").read()
    n = src.count("@given(")
    c.ok(n >= 5, f"test_properties.py has {n} @given properties — write at least 5 (the example + 4)")
    c.ok("assume(" in src, "use hypothesis.assume(...) in the validity property (start at a valid position)")


@c.test("TODO 5 — your tests catch 2 subtle mutants (properties make it easy)",
        hint="Symmetry with two points at DIFFERENT latitudes catches the asymmetric haversine; a round trip with a "
             "move both north AND east catches a wrong cos() in latlon_to_offset.")
def _():
    need_good_tests()
    survived = []
    for name, old, new, idea in MUTANTS["properties"]:
        code, _ = run_with(mutated(REFERENCE, old, new))
        if code != 1:
            survived.append(f"{name} — add a property: {idea}")
    c.ok(not survived, "these wrong versions pass all your tests:\n       - " + "\n       - ".join(survived))


def navera_reference():
    code, out = sh(f"git -C ~/navera show base:{NAV_GEO}", timeout=20)
    c.ok(code == 0, "could not read the original geo.py from git:\n" + out[-300:])
    return out


def run_navera(geo_source):
    """Run test_navera_geo.py with a navera_common package whose geo.py is `geo_source`."""
    c.file_exists("test_navera_geo.py")
    d = tempfile.mkdtemp(prefix="navmut_")
    try:
        os.makedirs(os.path.join(d, "navera_common"))
        open(os.path.join(d, "navera_common", "__init__.py"), "w").close()
        with open(os.path.join(d, "navera_common", "geo.py"), "w") as f:
            f.write(geo_source)
        shutil.copy("test_navera_geo.py", d)
        return pytest_in(d, ["test_navera_geo.py"], env=f"PYTHONPATH={d}:$PYTHONPATH")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@c.test("TODO 6 — test_navera_geo.py: at least 5 tests, passing on NAVERA's real geo.py",
        hint="Run `python3 -m pytest -v test_navera_geo.py`. Import from navera_common.geo, as the file does.")
def _():
    code, out = run_navera(navera_reference())
    c.ok(code == 0, "pytest says:\n" + out[-900:])
    c.ok(count_tests(out) >= 5, f"pytest ran {count_tests(out)} tests")


@c.test("TODO 6 — your NAVERA tests catch 5 wrong versions of navera_common/geo.py",
        hint="Test (0, 0), NaN, a known distance in metres, a dead-reckoned distance (speed × dt) and a negative speed.")
def _():
    ref = navera_reference()
    code, out = run_navera(ref)
    c.ok(code == 0 and count_tests(out) >= 1, "first make your tests pass on NAVERA's real geo.py (check above)")
    survived = []
    for name, old, new, idea in NAV_MUTANTS:
        code, out = run_navera(mutated(ref, old, new))
        if code != 1:
            survived.append(f"{name} — add a test: {idea}")
    c.ok(not survived, "these wrong versions pass all your tests:\n       - " + "\n       - ".join(survived))


@c.test("TODO 7 — `launch_test test_estimator_launch.py`: NAVERA's arbiter judged live (FIX, then NO_FIX)",
        hint="7a: publish one gps_estimate, spin, assert STATE_FIX and exactly one position. 7b: lat=math.nan → "
             "STATE_NO_FIX, 'non-finite' in the reason, no position. Run the command yourself and read the output.")
def _():
    c.file_exists("test_estimator_launch.py")
    src = open("test_estimator_launch.py").read()
    c.ok('self.fail("TODO 7a")' not in src and 'self.fail("TODO 7b")' not in src, "TODO 7a / 7b still call self.fail")
    c.ok("STATE_FIX" in src and "STATE_NO_FIX" in src and "positions" in src,
         "the tests must assert on NavStatus.STATE_FIX, STATE_NO_FIX and the published positions")
    code, out = sh("launch_test test_estimator_launch.py", timeout=120)
    c.ok(code == 0 and "FAILED" not in out, "launch_test failed:\n" + out[-1200:])
    c.ok(re.search(r"Ran 3 tests", out) is not None, "expected 3 tests during the launch (test_0, test_1, test_2):\n"
         + out[-600:])


@c.test("your NAVERA copy is restored: geo.py and estimator_params.yaml are back to the original",
        hint="cd ~/navera, then `git status` and `git diff` show what changed; `git restore <file>` puts a file "
             "back as it was in the last commit.")
def _():
    changed = []
    for f in (NAV_GEO, "navera_estimator/navera_estimator/config/estimator_params.yaml"):
        code, _ = sh(f"git -C ~/navera diff --quiet base -- {f}", timeout=20)
        if code != 0:
            changed.append(f)
    c.ok(not changed, "still different from the original: " + ", ".join(changed))


@c.test("report.md — NAVERA's tests, Mutants and Properties, with your observations",
        hint="Keep the three headings, at least 40 words each. NAVERA's tests: the number of tests run_tests.sh "
             "ran; Properties: the falsifying example (lat0=…) hypothesis printed.")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8", errors="replace").read()
    secs = {}
    for title in ("NAVERA's tests", "Mutants", "Properties"):
        m = re.search(r"^##\s*" + re.escape(title) + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
        c.ok(m is not None, f"the heading `## {title}` is missing")
        body = re.sub(r"^\*(?=\S)[^*]+?\*\s*$", "", m.group(1), flags=re.M | re.S)
        words = len(re.findall(r"[A-Za-z0-9_.]+", body))
        c.ok(words >= 40, f"section {title} has {words} words of yours — write at least 40")
        secs[title] = body
    nums = [int(x) for x in re.findall(r"\b\d{3}\b", secs["NAVERA's tests"])]
    c.ok(any(300 <= n <= 500 for n in nums), "the NAVERA's tests section does not give the number of unit tests")
    c.ok("lat0" in secs["Properties"] or "Falsifying" in secs["Properties"],
         "the Properties section does not quote hypothesis's falsifying example")


c.run()
