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
]


def pytest_in(folder, test_file, env=""):
    """Run pytest on one test file in `folder`; returns (exit code, output)."""
    return sh(f"cd {folder} && {env} python3 -m pytest -q -p no:cacheprovider -x {test_file}", timeout=90)


def count_tests(out):
    m = re.search(r"(\d+) passed", out)
    return int(m.group(1)) if m else 0


def run_with(geo_source, test_file="test_geo_tools.py"):
    """Copy the student's test file next to `geo_source` (a version of geo_tools.py) and run it."""
    c.file_exists(test_file)
    d = tempfile.mkdtemp(prefix="mut_")
    try:
        shutil.copy(test_file, d)
        with open(os.path.join(d, "geo_tools.py"), "w") as f:
            f.write(geo_source)
        return pytest_in(d, test_file)
    finally:
        shutil.rmtree(d, ignore_errors=True)


GOOD = {}


def mutated(source, old, new):
    """`source` with one bug in it (and still valid Python)."""
    assert old in source, f"checker bug: {old!r} not found"
    out = source.replace(old, new)
    compile(out, "mutant.py", "exec")
    return out


def need_good_tests():
    if "ok" not in GOOD:
        code, out = run_with(REFERENCE)
        GOOD["ok"], GOOD["n"] = code == 0, count_tests(out)
    c.ok(GOOD["ok"], "first make all your tests pass on the correct geo_tools.py (check 1)")


@c.test("your tests in test_geo_tools.py all pass on the correct geo_tools.py",
        hint="Run `python3 -m pytest -v test_geo_tools.py`. A test that fails on correct code is a wrong "
             "test: check the expected value, and use pytest.approx for decimals.")
def _():
    code, out = run_with(REFERENCE)
    GOOD["ok"], GOOD["n"] = code == 0, count_tests(out)
    c.ok(code == 0, "pytest says:\n" + out[-900:])


@c.test("test_geo_tools.py has at least 8 tests", hint="One test per idea: at least 2 for haversine_m, "
                                                      "2 for meters_to_degrees, 3 for is_valid_position, 2 for speed_mps.")
def _():
    if "n" not in GOOD:
        GOOD["n"] = count_tests(run_with(REFERENCE)[1])
    c.ok(GOOD["n"] >= 8, f"pytest ran {GOOD['n']} tests")


for func, mutants in MUTANTS.items():
    todo = {"haversine_m": 1, "meters_to_degrees": 2, "is_valid_position": 3, "speed_mps": 4}[func]

    @c.test(f"TODO {todo} — your tests catch {len(mutants)} wrong versions of {func}()",
            hint="For each wrong version that survived, add a test that the correct code passes "
                 "and the wrong code fails.")
    def _(func=func, mutants=mutants):
        need_good_tests()
        survived = []
        for name, old, new, idea in mutants:
            mutant = mutated(REFERENCE, old, new)
            code, out = run_with(mutant)
            if code != 1:                     # 1 = some test failed: the mutant was caught
                survived.append(f"{func}() that {name} — add a test: {idea}")
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
        return pytest_in(d, "test_navera_geo.py", env=f"PYTHONPATH={d}:$PYTHONPATH")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@c.test("TODO 5 — test_navera_geo.py: at least 3 tests, passing on NAVERA's real geo.py",
        hint="Run `python3 -m pytest -v test_navera_geo.py`. Import from navera_common.geo, as the file does.")
def _():
    code, out = run_navera(navera_reference())
    c.ok(code == 0, "pytest says:\n" + out[-900:])
    c.ok(count_tests(out) >= 3, f"pytest ran {count_tests(out)} tests")


@c.test("TODO 5 — your NAVERA tests catch 3 wrong versions of navera_common/geo.py",
        hint="Test (0, 0), NaN and a known distance in metres.")
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


@c.test("your NAVERA copy is restored: geo.py and estimator_params.yaml are back to the original",
        hint="cd ~/navera, then `git status` and `git diff` show what changed; "
             "`git restore <file>` puts a file back as it was in the last commit.")
def _():
    changed = []
    for f in (NAV_GEO, "navera_estimator/navera_estimator/config/estimator_params.yaml"):
        code, _ = sh(f"git -C ~/navera diff --quiet base -- {f}", timeout=20)
        if code != 0:
            changed.append(f)
    c.ok(not changed, "still different from the original: " + ", ".join(changed))


c.run()
