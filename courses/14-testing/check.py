"""Mission 14 checker: your tests must PASS on the stack as given and FAIL on wrong copies of it (mutants).

Every student test runs in a separate process (pytest / launch_test through sh()), in a temporary folder that
holds the GIVEN stack (from the read-only starter files) with one change, never the student's own copy.
"""
import ast
import math
import os
import re
import shutil
import tempfile

from academy_check import (CheckFailed, Checker, explained, load_student, need, predicted, publishers_ok, sh)

c = Checker()

LID = "14-testing"
GIVEN = f"/academy/courses/{LID}/files"
if not os.path.isdir(GIVEN):                     # run by hand from the course folder (authors)
    GIVEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")
EXAMPLES, PROPERTIES, LAUNCH = "test_geo_examples.py", "test_geo_properties.py", "test_arbiter_launch.py"

# ---------------------------------------------------------------- expected values (course reference, 2026-10-13)
N_TESTS = 89                    # pytest navera_lite/tests in the 14 copy
N_FAILED = 1                    # is_finite_latlon accepting (0, 0): only test_geo's Null Island test fails
EQUIVALENT = 3                  # hunt.py's training mutant 3 (finite = math.isfinite(la))
R_M = 6_371_000.0

# hidden mutants: (file, old, new, what it does, which test kills it). Each old text appears once in the file.
HAVERSINE = [
    ("geo.py", "np.sin(np.radians(lon2 - lon1) / 2.0)", "np.sin((lon2 - lon1) / 2.0)",
     "haversine_m forgets to turn the longitude difference into radians",
     "a known distance between two points at different longitudes"),
    ("geo.py", "d = 2.0 * EARTH_RADIUS_M * np.arcsin", "d = 2.0 * 6371.0 * np.arcsin",
     "haversine_m returns kilometres", "a known distance, in METRES"),
    ("geo.py", "np.sin((p2 - p1) / 2.0) ** 2", "np.sin(p2 - p1) ** 2",
     "haversine_m forgets the half of the latitude difference", "a known distance along a meridian (north–south)"),
]
VALIDITY = [
    ("geo.py", "return in_range and not null_island", "return in_range",
     "is_finite_latlon accepts Null Island", "(0.0, 0.0) must give False"),
    ("geo.py", "abs(la) <= 90.0", "abs(la) <= 180.0",
     "is_finite_latlon accepts latitudes up to ±180°", "a latitude just beyond 90° (or −90°) must give False"),
    ("geo.py", "abs(lo) <= 180.0", "abs(lo) <= 360.0",
     "is_finite_latlon accepts longitudes up to ±360°", "a longitude just beyond 180° (or −180°) must give False"),
    ("geo.py", "abs(la) <= 90.0", "abs(la) < 90.0",
     "is_finite_latlon refuses the poles", "the limits themselves are valid: a latitude of exactly 90° (or −90°) gives True"),
    ("geo.py", "        if isinstance(v, bool) or not isinstance(v, (int, float, np.floating, np.integer)):\n"
               "            return False\n", "",
     "is_finite_latlon does not check that the inputs are numbers (a text becomes a number, None crashes)",
     "inputs that are not numbers at all (None, a text) must give False"),
]
OFFSET = [
    ("geo.py", "lon2 = (lon2 + 180.0) % 360.0 - 180.0", "lon2 = lon2",
     "offset never brings the longitude back into [−180, 180)",
     "a move east across the ±180° meridian (offset's docstring)"),
    ("geo.py", "lat2 = lat + math.degrees(n_m / EARTH_RADIUS_M)", "lat2 = lat + math.degrees(e_m / EARTH_RADIUS_M)",
     "offset moves the latitude with the EAST metres", "a move north changes the latitude by the right amount, "
     "and a move east alone leaves the latitude unchanged"),
    ("geo.py", "e = math.radians(dlon) * EARTH_RADIUS_M * math.cos(mean_lat)", "e = math.radians(dlon) * EARTH_RADIUS_M",
     "enu_flat forgets that a parallel is shorter far from the equator",
     "enu_flat of a point placed by hand EAST of you, far from the equator"),
    ("geo.py", "n = math.radians(lat - lat0) * EARTH_RADIUS_M", "n = math.radians(lat0 - lat) * EARTH_RADIUS_M",
     "enu_flat has north and south swapped", "enu_flat of a point placed by hand NORTH of you (n > 0)"),
    ("geo.py", "if math.pi - d < 1e-9:", "if math.pi - d < 0.0:",
     "great_circle_points no longer refuses two opposite points",
     "pytest.raises(ValueError) for two opposite points, e.g. (10, 20) and (−10, −160)"),
]
GATE = [
    ("guard.py", "d = math.hypot(new_xy[0] - last_xy[0], new_xy[1] - last_xy[1])",
     "d = abs(new_xy[0] - last_xy[0]) + abs(new_xy[1] - last_xy[1])",
     "gate_ok measures the distance as east + north instead of the straight line",
     "a DIAGONAL jump: e.g. (100, 100) after 1 s is 141 m, accepted; a test that moves only east misses it"),
    ("guard.py", "return d <= v_max_mps * max(0.0, elapsed_s) + margin_m",
     "return d < v_max_mps * max(0.0, elapsed_s) + margin_m",
     "gate_ok refuses a fix exactly at the limit", "a jump of exactly v_max × elapsed + margin is accepted (≤)"),
    ("guard.py", "v_max_mps * max(0.0, elapsed_s) + margin_m", "v_max_mps * elapsed_s + margin_m",
     "gate_ok lets a negative elapsed time shrink the gate", "a negative elapsed time counts as 0 (the docstring)"),
    ("guard.py", "max(0.0, elapsed_s) + margin_m", "max(0.0, elapsed_s)",
     "gate_ok forgets the margin", "a small jump with no time between the fixes: the margin alone decides"),
    ("guard.py", "        allowed = self.v_max_mps * max(0.0, elapsed) + self.margin_m\n",
     "        self.trusted = est\n        allowed = self.v_max_mps * max(0.0, elapsed) + self.margin_m\n",
     "JumpGate makes a REFUSED fix the trusted one",
     "a regression test: after a refused jump, the next fix is still judged from the last TRUSTED fix"),
]
PROPERTY_ONLY = [
    ("geo.py", "np.cos(p1) * np.cos(p2)", "np.cos(p1) ** 2",
     "haversine_m uses cos(lat1)² (right whenever both latitudes are equal)", "symmetry: d(A, B) = d(B, A)"),
    ("geo.py", "    mean_lat = math.radians((lat + lat2) / 2.0)", "    mean_lat = math.radians(lat)",
     "offset takes the scale of the parallel at the start, enu_flat at the mean latitude",
     "the round trip enu_flat(offset(…)) with a move north AND east"),
]
JUDGE = [
    ("ros/arbiter_v0.py", "            ok, why = self.gate.check(est)", '            ok, why = True, "no gate"',
     "a judge without its jump gate", "TODO 7a: the jump must be refused, and named in the status"),
    ("ros/arbiter_v0.py", '        if not is_finite_latlon(est.lat, est.lon):\n            return False, "bad position"\n',
     "", "a judge that takes a NaN position", "TODO 7b: NO_FIX, with the reason"),
    ("ros/arbiter_v0.py", "if key != self.last_sent:", "if True:",
     "a judge that re-publishes the same position at 5 Hz (NAVERA's EST-1)",
     "TODO 7a: exactly ONE position published since the test began"),
    ("ros/arbiter_v0.py", 'return False, "bad position"', 'return False, "no position"',
     "a judge that says NO_FIX for a NaN fix but gives the wrong reason",
     "TODO 7b: its message says WHY (the words of arbiter_v0.py's usable())"),
]

TRAINING_OLD = [("geo.py", "d = 2.0 * EARTH_RADIUS_M * np.arcsin"), ("geo.py", "abs(lo) <= 180.0"),
                ("geo.py", "finite = math.isfinite(la) and math.isfinite(lo)"),
                ("geo.py", "lat2 = lat + math.degrees(n_m / EARTH_RADIUS_M)"),
                ("geo.py", "dlon = (lon - lon0 + 180.0) % 360.0 - 180.0"),
                ("guard.py", "v_max_mps * max(0.0, elapsed_s) + margin_m"), ("guard.py", "max(0.0, elapsed_s)")]
REPUBLISH = JUDGE[2]
REPUBLISH_RANGE = (8, 16)        # measured 12–13 (2 s × 5 Hz + one per arrival); generous for a loaded machine

FORBIDDEN = [r"\bopen\s*\(", r"__file__", r"\binspect\b", r"getsource", r"\bhashlib\b", r"__code__", r"co_code",
             r"\bimportlib\b", r"sys\.modules", r"\bsubprocess\b", r"os\.system", r"\bpathlib\b", r"read_text",
             r"read_bytes", r"\bexec\s*\(", r"\beval\s*\(", r"\blinecache\b", r"__loader__", r"__spec__",
             r"\bmarshal\b", r"\bimport\s+dis\b", r"\bfrom\s+dis\b", r"(?<!re\.)\bcompile\s*\("]

CONFTEST = '''from hypothesis import Phase, settings
settings.register_profile("check", derandomize=True, database=None, deadline=None,
                          phases=[Phase.explicit, Phase.generate])
'''
PYTEST = ("PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout {t} python3 -B -m pytest -q -x -p no:cacheprovider "
          "-p _hypothesis_pytestplugin --hypothesis-profile=check {files}")


# ---------------------------------------------------------------- helpers
def given_text(rel):
    with open(os.path.join(GIVEN, "navera_lite", rel)) as f:
        return f.read()


def mutate(m):
    name, old, new = m[:3]
    src = given_text(name)
    if src.count(old) != 1:
        raise CheckFailed(f"checker problem: a mutant no longer fits navera_lite/{name} — tell your teacher")
    return name, src.replace(old, new)


def student_file(name):
    if not os.path.exists(name):
        raise CheckFailed(f"{name} is missing in your lesson folder")
    with open(name) as f:
        text = f.read()
    try:
        ast.parse(text)
    except SyntaxError as e:
        raise CheckFailed(f"{name} has a syntax error on line {e.lineno}: {e.msg}")
    return text


def keep_rules(name):
    bad = sorted({m.group(0) for p in FORBIDDEN for m in re.finditer(p, student_file(name))})
    if bad:
        raise CheckFailed(f"{name} uses {', '.join(bad)}: rule 3 — test through inputs and outputs only "
                          "(no reading of files or source code)")


def stack_copy(changed=None, files=()):
    """A temporary lesson folder: the GIVEN navera_lite/ (one file changed), its yaml, pytest.ini, the files."""
    d = tempfile.mkdtemp(prefix="chk14_")
    shutil.copytree(os.path.join(GIVEN, "navera_lite"), os.path.join(d, "navera_lite"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for extra in ("navera_lite.yaml", "pytest.ini"):
        shutil.copy(os.path.join(GIVEN, extra), d)
    if changed:
        with open(os.path.join(d, "navera_lite", changed[0]), "w") as f:
            f.write(changed[1])
    for name in files:
        shutil.copy(name, d)
    with open(os.path.join(d, "conftest.py"), "w") as f:
        f.write(CONFTEST)
    return d


def pytest_on(files, changed=None, run=None, timeout=150):
    """pytest on the student's `files` (copied) against the given stack, maybe with one change. (code, out)"""
    d = stack_copy(changed, files)
    try:
        return sh(f"cd {d} && " + PYTEST.format(t=timeout, files=" ".join(run or files)), timeout=timeout + 30)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def tail(out, n=14):
    lines = [l for l in out.strip().splitlines() if l.strip()]
    keep = [l for l in lines if l.startswith(("E ", "FAILED", "ERROR", "Falsifying", "FAIL:", "AssertionError",
                                              "    self.assert", "KeyError", "TypeError", "AttributeError",
                                              "NameError", "IndexError"))] or lines
    return "\n".join("       " + l for l in keep[-n:])


_BASE = {}


def passes_as_given(name):
    """The student's file passes on the given stack (cached)."""
    keep_rules(name)
    if name not in _BASE:
        _BASE[name] = pytest_on([name])
    code, out = _BASE[name]
    if code == 5 or "no tests ran" in out:
        raise CheckFailed(f"pytest finds no test in {name}")
    if code != 0:
        deg = (" — math.cos takes RADIANS: math.cos(math.radians(60)) is 0.5, math.cos(60) is −0.95"
               if re.search(r"math\.cos\(\s*-?\d", student_file(name)) else "")
        raise CheckFailed(f"{name} does NOT pass on the stack as given — a test that fails on correct code is a "
                          f"wrong test (expected value? metres or degrees? tolerance?){deg}. pytest says:\n" + tail(out))
    m = re.search(r"(\d+) passed", out)
    return int(m.group(1)) if m else 0


def survivors(name, mutants):
    passes_as_given(name)
    out = []
    for m in mutants:
        code, _ = pytest_on([name], mutate(m))
        if code != 1:
            out.append(m)
    return out


def report_survivors(name, mutants, total):
    if mutants:
        lines = [f"  • {m[3]}: survived — a test that kills it: {m[4]}" for m in mutants]
        raise CheckFailed(f"{len(mutants)} of {total} wrong versions pass every test of {name}:\n" + "\n".join(lines))


def answers(*names):
    return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    return float(v)


def is_valid(lat, lon):
    return (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90.0 and abs(lon) <= 180.0
            and not (lat == 0.0 and lon == 0.0))


def offset_ref(lat, lon, e_m, n_m):
    """The given offset() of navera_lite/geo.py (mission 06), to judge a counterexample."""
    lat2 = lat + math.degrees(n_m / R_M)
    mean = math.radians((lat + lat2) / 2.0)
    lon2 = lon + math.degrees(e_m / (R_M * math.cos(mean)))
    return lat2, (lon2 + 180.0) % 360.0 - 180.0


def _num(node):
    """The value of a numeric literal expression (-90 + 10, 80.0, -80), or ValueError."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _num(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        a, b = _num(node.left), _num(node.right)
        return {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b}.get(type(node.op)) if not isinstance(node.op, ast.Div) \
            else a / b
    raise ValueError("not a number")


_FLIP = {ast.Lt: ast.Gt, ast.LtE: ast.GtE, ast.Gt: ast.Lt, ast.GtE: ast.LtE}


def _cmp_bound(node, name):
    """The largest |name| the comparisons in `node` let through (abs(name) <= 80, -80 <= name <= 80,
    name < 80 and name > -80), or None if `name` is not bounded on both sides."""
    lo, hi = -math.inf, math.inf
    for cmp in ast.walk(node):
        if not isinstance(cmp, ast.Compare):
            continue
        items = [cmp.left] + list(cmp.comparators)
        for a, op, b in zip(items, cmp.ops, items[1:]):
            for x, y, flip in ((a, b, False), (b, a, True)):
                try:
                    v = _num(y)
                except ValueError:
                    continue
                o = _FLIP.get(type(op), type(op)) if flip else type(op)
                xs = ast.unparse(x)
                if xs == f"abs({name})" and o in (ast.Lt, ast.LtE):
                    lo, hi = max(lo, -v), min(hi, v)
                elif xs == name and o in (ast.Lt, ast.LtE):
                    hi = min(hi, v)
                elif xs == name and o in (ast.Gt, ast.GtE):
                    lo = max(lo, v)
    return max(-lo, hi) if math.isfinite(lo) and math.isfinite(hi) else None


def _bound(node, assigns, depth=0):
    """The largest |value| a float strategy expression can draw, 0 if restricted by .filter/.map, None if unknown."""
    if depth > 5:
        return None
    if isinstance(node, ast.Name):
        return _bound(assigns[node.id], assigns, depth + 1) if node.id in assigns else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "filter":
        fn = node.args[0] if node.args else None
        if isinstance(fn, ast.Lambda) and fn.args.args:          # LAT.filter(lambda x: abs(x) <= 80): read it
            found = [b for b in (_cmp_bound(fn.body, fn.args.args[0].arg),
                                 _bound(node.func.value, assigns, depth + 1)) if b is not None]
            return min(found) if found else None
        return 0.0                                  # a named function of the student's: trusted
    if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(("floats", "integers")):
        vals = list(node.args[:2]) + [k.value for k in node.keywords if k.arg in ("min_value", "max_value")]
        if len(vals) < 2:
            return None                             # an open side: NaN, infinity or ±1e308
        try:
            return max(abs(_num(v)) for v in vals)
        except ValueError:
            return None
    return None


def funcs(tree):
    return [n for n in tree.body if isinstance(n, ast.FunctionDef)]


def decorated_with(fn, word):
    return any(word in ast.unparse(d) for d in fn.decorator_list)


# ================================================================ Session 1 — Pin the bugs
@c.test("Steps 0–1: the stack's suite, broken on purpose and restored with git",
        hint="Lab Steps 0–1: run the suite, run navera_lite/tools/init_repo.sh, make the small change, run the suite "
             "again, then `git restore navera_lite/geo.py`. `git status` must list no change in navera_lite/.")
def _():
    ps, n, slow, pf, nf, ex = answers("PREDICT_SUITE", "N_TESTS", "SLOWEST_TEST", "PREDICT_FAILS", "N_FAILED",
                                      "EXPLAIN_ONE_TEST")
    predicted("PREDICT_SUITE", ps)
    c.ok(number(n, "N_TESTS") == N_TESTS, "N_TESTS is not the number pytest printed for navera_lite/tests")
    c.ok(isinstance(slow, str) and "smoke" in slow, "SLOWEST_TEST is not the slowest test `--durations=3` lists")
    predicted("PREDICT_FAILS", pf)
    c.ok(number(nf, "N_FAILED") == N_FAILED, "N_FAILED is not the number of tests that failed after the small change")
    explained("EXPLAIN_ONE_TEST", ex, ([r"\bone\b", r"\bonly\b", r"single", r"\b1\b"], "how many tests guard the rule"),
              ([r"arbiter", r"judge", r"v0", r"trip", r"eligible", r"estimate", r"other part", r"caller",
                r"\bus(e|es|ed|ing)\b"],
               "which other parts use is_finite_latlon"))
    code, out = sh("git rev-parse --verify -q 'refs/tags/start^{commit}'", timeout=20)
    c.ok(code == 0, "your lesson folder is not a git repository with the tag `start` yet: "
                    "bash navera_lite/tools/init_repo.sh (lab Step 1)")
    changed = []
    for root, dirs, files in os.walk(os.path.join(GIVEN, "navera_lite")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, f), GIVEN)
                try:
                    with open(rel) as fh:
                        same = fh.read() == open(os.path.join(root, f)).read()
                except FileNotFoundError:
                    same = False
                if not same:
                    changed.append(rel)
    if changed:
        raise CheckFailed(f"{', '.join(sorted(changed)[:4])} {'is' if len(changed) == 1 else 'are'} not as given: restore "
                          f"{'it' if len(changed) == 1 else 'them'} "
                          f"(`git restore {sorted(changed)[0]}`; `git diff start -- navera_lite` shows the change)")


@c.test("TODO 1–4: test_geo_examples.py passes on the stack as given, with fixtures and a parametrized test",
        hint="`python3 -m pytest -v test_geo_examples.py`. A test that fails on correct code is a wrong test. TODO 2 is "
             "ONE function with @pytest.mark.parametrize and at least 8 cases; use a fixture (quito, gate or your own) "
             "in at least one test of yours.")
def _():
    n = passes_as_given(EXAMPLES)
    c.ok(n >= 20, f"pytest ran {n} tests in {EXAMPLES} (5 were given): write at least 15 more (TODO 1–4, "
                  "parametrized cases count)")
    tree = ast.parse(student_file(EXAMPLES))
    mine = [f for f in funcs(tree) if f.name.startswith("test_") and f.name not in
            ("test_bearing_of_the_four_cardinal_directions", "test_a_point_is_at_zero_metres_from_itself")]
    lists = {t.id: n.value for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
             if isinstance(t, ast.Name)}                         # CASES = [...] used as @parametrize("…", CASES)
    best = 0
    for f in mine:
        if decorated_with(f, "parametrize") and "is_finite_latlon" in ast.unparse(f):
            for d in f.decorator_list:
                if isinstance(d, ast.Call) and len(d.args) >= 2:
                    cases = lists.get(d.args[1].id) if isinstance(d.args[1], ast.Name) else d.args[1]
                    if isinstance(cases, (ast.List, ast.Tuple)):
                        best = max(best, len(cases.elts))
    c.ok(best >= 8, f"TODO 2: no parametrized test of is_finite_latlon with at least 8 cases (largest: {best})")
    fixtures = {f.name for f in funcs(tree) if decorated_with(f, "fixture")}
    c.ok(any({a.arg for a in f.args.args} & fixtures for f in mine),
         f"none of your tests uses a fixture ({', '.join(sorted(fixtures))}): name one as an argument")


for _todo, _group, _what in ((1, HAVERSINE, "haversine_m"), (2, VALIDITY, "is_finite_latlon"),
                             (3, OFFSET, "offset / enu_flat / great_circle_points"), (4, GATE, "the jump gate")):
    @c.test(f"TODO {_todo}: your example tests kill {len(_group)} wrong versions of {_what} you have not seen",
            hint="For each survivor, write a test that the given stack passes and the wrong version fails. Train with "
                 "`python3 hunt.py`. Only test_geo_examples.py runs here.")
    def _(group=_group):
        report_survivors(EXAMPLES, survivors(EXAMPLES, group), len(group))


@c.test("TODO 5: four more properties, true on the stack as given, that kill 2 mutants examples often miss",
        hint="Lesson §3 and lab Step 3: symmetry, triangle inequality, round trip, validity — each with @given and "
             "@settings(deadline=None); restrict the domain of the round trip and the validity (after Step 3's "
             "counterexample). Only test_geo_properties.py runs here.")
def _():
    n = passes_as_given(PROPERTIES)
    tree = ast.parse(student_file(PROPERTIES))
    props = [f for f in funcs(tree) if f.name.startswith("test_") and decorated_with(f, "given")]
    c.ok(len(props) >= 5, f"{len(props)} property test(s) with @given in {PROPERTIES} (1 was given): write the "
                          "four of TODO 5")
    c.ok(n >= 5, f"pytest ran only {n} tests in {PROPERTIES}")
    assigns = {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
               for t in node.targets if isinstance(t, ast.Name)}
    for f in props:
        if "offset(" not in ast.unparse(f):
            continue
        given = next(d for d in f.decorator_list if "given" in ast.unparse(d))
        params = [a.arg for a in f.args.args]
        lat_name = next((p for p in params if "lat" in p.lower()), params[0] if params else None)
        strat = next((k.value for k in getattr(given, "keywords", []) if k.arg == lat_name), None)
        if strat is None and isinstance(given, ast.Call) and lat_name in params:
            i = params.index(lat_name) - (len(params) - len(given.args))   # @given fills the RIGHTMOST parameters
            strat = given.args[i] if 0 <= i < len(given.args) else None
        b = _bound(strat, assigns) if strat is not None else None
        by_assume = any((_cmp_bound(n, lat_name) or 99.0) <= 89.5 for n in ast.walk(f)
                        if isinstance(n, ast.Call) and ast.unparse(n.func) == "assume")
        c.ok((b is not None and b <= 89.5) or by_assume,
             f"{f.name} still draws its start latitude ({lat_name}) from the whole Earth, or from a strategy the check "
             "cannot read: a start near a pole and a move towards it leave the domain of offset, even when a run is "
             "lucky (lab Step 3: st.floats(-80.0, 80.0), a .filter(…) or an assume(abs(lat0) <= 80) — the check reads "
             "the number: it must stop the start at least 50 km (0.45°) before a pole, so 89.9 or 90 is not a "
             "restriction)")
    report_survivors(PROPERTIES, survivors(PROPERTIES, PROPERTY_ONLY), len(PROPERTY_ONLY))


@c.test("Step 3: the counterexample of the validity property, and what it means",
        hint="Lab Step 3: copy the four numbers of hypothesis's Falsifying example (whole Earth, max_examples=2000) "
             "as (lat0, lon0, e_m, n_m). Lesson §3: a bug, or a limit of the domain?")
def _():
    p, ce, ex = answers("PREDICT_COUNTEREXAMPLE", "COUNTEREXAMPLE", "EXPLAIN_COUNTEREXAMPLE")
    predicted("PREDICT_COUNTEREXAMPLE", p)
    if not (isinstance(ce, (tuple, list)) and len(ce) == 4):
        raise CheckFailed(f"COUNTEREXAMPLE should be 4 numbers (lat0, lon0, e_m, n_m), got {ce!r}")
    lat0, lon0, e, n = (number(v, "each number of COUNTEREXAMPLE") for v in ce)
    c.ok(is_valid(lat0, lon0), f"COUNTEREXAMPLE starts at ({lat0}, {lon0}), which is not a valid start: the property "
                               "only uses valid starts (assume)")
    c.ok(abs(e) <= 50_000.0 and abs(n) <= 50_000.0, "COUNTEREXAMPLE: a move of more than 50 km is outside METRES")
    try:
        bad = not is_valid(*offset_ref(lat0, lon0, e, n))
    except (ZeroDivisionError, ValueError, OverflowError):
        bad = True
    c.ok(bad, f"offset{(lat0, lon0, e, n)} gives a valid position: this is not a counterexample of the validity "
              "property (copy the Falsifying example's numbers, in the order lat0, lon0, e_m, n_m)")
    explained("EXPLAIN_COUNTEREXAMPLE", ex,
              ([r"pole", r"\b90", r"latitude"], "what happens physically"),
              ([r"domain", r"restrict", r"limit", r"design", r"document", r"flat", r"small", r"far from", r"near"],
               "whether it is a bug or a limit of the domain"))


# ================================================================ Session 2 — Hunt and launch
@c.test("Step 4: the equivalent mutant",
        hint="Lab Step 4: which training mutant of `python3 hunt.py` survives whatever test you add? Lesson §4.")
def _():
    n, ex = answers("EQUIVALENT_MUTANT", "EXPLAIN_EQUIVALENT")
    c.ok(number(n, "EQUIVALENT_MUTANT") == EQUIVALENT, "EQUIVALENT_MUTANT: that mutant can be killed — find the "
                                                       "input that shows the difference")
    explained("EXPLAIN_EQUIVALENT", ex,
              ([r"range", r"abs", r"180", r"compar", r"in_range", r"<="], "what still refuses NaN and infinity"),
              ([r"every input", r"any input", r"all input", r"no input", r"same", r"never", r"cannot", r"can't",
                r"impossible", r"identical", r"always", r"both versions", r"\bboth\b", r"no test",
                r"tell (them|the two) apart", r"every \w+ input", r"for all", r"whatever"],
               "why no test can show a difference"))


@c.test("TODO 6: three mutants of your own — missed by the stack's suite, killed by your tests",
        hint="Lab Step 5 and `python3 hunt.py mine`: each (file, old, new) changes CODE of geo.py or guard.py, the "
             "stack's suite still passes, and a test of yours (TODO 6b) fails.")
def _():
    passes_as_given(EXAMPLES)
    passes_as_given(PROPERTIES)
    (muts,) = need(load_student("my_mutants.py", fresh=True), "MUTANTS")
    if not isinstance(muts, (list, tuple)) or len(muts) < 3:
        raise CheckFailed(f"my_mutants.py: MUTANTS holds {len(muts) if isinstance(muts, (list, tuple)) else muts!r} "
                          "mutant(s): write three (TODO 6)")
    suite = sorted(os.path.join("navera_lite", "tests", f) for f in os.listdir(os.path.join(GIVEN, "navera_lite", "tests"))
                   if f.startswith("test_") and f.endswith(".py") and f != "test_ros_smoke.py")
    good, notes, seen = 0, [], set()
    for i, m in enumerate(list(muts)[:6], 1):
        if not (isinstance(m, (list, tuple)) and len(m) == 3 and all(isinstance(x, str) for x in m)):
            notes.append(f"mutant {i} is not a tuple of three texts (file, old, new)")
            continue
        name, old, new = m
        if name not in ("geo.py", "guard.py"):
            notes.append(f"mutant {i}: the file must be \"geo.py\" or \"guard.py\"")
            continue
        src = given_text(name)
        if not old or src.count(old) != 1:
            k = src.count(old) if old else 0
            notes.append(f"mutant {i}: its old text appears {k} times in {name}, not once "
                         + ("(copy it exactly, or take a shorter piece)" if k == 0 else "(take a longer, unique piece)"))
            continue
        text = src.replace(old, new)
        try:
            same = _code(text) == _code(src)
        except SyntaxError:
            notes.append(f"mutant {i}: the mutated {name} is not valid Python")
            continue
        if same:
            notes.append(f"mutant {i}: changes no code (a comment, a docstring, the layout)")
            continue
        a0 = src.index(old)
        if any(t_name == name and a0 < src.index(t_old) + len(t_old) and src.index(t_old) < a0 + len(old)
               for t_name, t_old in TRAINING_OLD):
            notes.append(f"mutant {i}: it changes the same code as a training mutant of hunt.py — find a hole of your own")
            continue
        first = src.count("\n", 0, a0)
        lines = (name, first, first + old.count("\n"))
        if any(g == name and first <= l2 and l1 <= lines[2] for g, l1, l2 in seen):
            notes.append(f"mutant {i}: it changes the same line as another of your mutants — three DIFFERENT holes")
            continue
        seen.add(lines)
        if probe_results((name, text)) == probe_results(None):
            notes.append(f"mutant {i} ({old.strip()[:40]} → {new.strip()[:40]}): gives no wrong result on several hundred "
                         "inputs (only a message, a type or an unused detail changes): find a change that makes the stack "
                         "WRONG")
            continue
        code_suite, _ = pytest_on([], (name, text), run=suite)
        if code_suite != 0:
            notes.append(f"mutant {i} ({old.strip()[:40]} → {new.strip()[:40]}): the stack's own suite kills it")
            continue
        code_mine, _ = pytest_on([EXAMPLES, PROPERTIES], (name, text))
        if code_mine != 1:
            notes.append(f"mutant {i} ({old.strip()[:40]} → {new.strip()[:40]}): none of your tests kills it (TODO 6b)")
            continue
        good += 1
    c.ok(good >= 3, f"{good} good mutant(s) of 3:\n" + "\n".join("  • " + x for x in notes))


PROBE = r'''
import math, random, sys, warnings
sys.path.insert(0, sys.argv[1])
import numpy as np
warnings.simplefilter("ignore")
np.seterr(all="ignore")
from navera_lite import geo
from navera_lite.guard import JumpGate, gate_ok
from navera_lite.estimate import Estimate
from navera_lite.settings import DEFAULTS


def norm(v):
    if isinstance(v, (list, tuple)):
        return "(" + ",".join(norm(x) for x in v) + ")"
    if isinstance(v, np.ndarray):
        return norm(v.tolist())
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (int, float, np.floating, np.integer)):
        return f"{float(v):.10g}"
    return repr(v)


def call(f, *a):
    try:
        return norm(f(*a))
    except Exception as e:
        return "raise " + type(e).__name__


rng = random.Random(14)
pts = [(rng.uniform(-89.0, 89.0), rng.uniform(-180.0, 180.0)) for _ in range(150)]
pts += [(90.0, 0.0), (-90.0, 180.0), (0.0, 0.0), (0.0, 180.0), (89.99, 10.0), (35.8, 179.99), (-17.0, -179.95),
        (-44.0875753669041, -1.6433686469012514)]
odd = [(math.nan, 1.0), (1.0, math.nan), (math.inf, 1.0), (1.0, -math.inf), (None, 1.0), ("35.8", 10.6),
       (True, 1.0), (90.0001, 1.0), (1.0, 180.0001), (-90.0001, 1.0), (1.0, -180.0001), (0.0, 1e-300)]
out = []
for la, lo in pts + odd:
    out.append(call(geo.is_finite_latlon, la, lo))
for (a, b), (c, d) in zip(pts, pts[1:] + pts[:1]):
    out.append(call(geo.haversine_m, a, b, c, d))
    out.append(call(geo.bearing_deg, a, b, c, d))
    out.append(call(geo.enu_flat, a, b, a + (c - a) * 0.01, b + (d - b) * 0.01))
    out.append(call(geo.offset, a, b, rng.uniform(-60000, 60000), rng.uniform(-60000, 60000)))
    out.append(call(geo.great_circle_points, (a, b), (c, d), 4))
    out.append(call(geo.radii, a))
    out.append(call(geo.geodetic_to_ecef, a, b, 100.0))
    out.append(call(geo.geodetic_to_enu, c, d, 50.0, a, b, 10.0))
out.append(call(geo.haversine_m, -44.0875753669041, -1.6433686469012514, 44.0875753669041, 178.35663135409874))
out.append(call(geo.offset, -17.0, 179.99, 5000.0, 0.0))
out.append(call(geo.enu_flat, -17.0, 179.95, -17.0, -179.95))
out.append(call(geo.great_circle_points, (10.0, 20.0), (-10.0, -160.0), 3))
out.append(call(geo.great_circle_points, (10.0, 20.0), (-5.0, 40.0), 1))
out.append(call(geo.great_circle_points, (10.0, 20.0), (10.0, 20.0), 3))
out.append(call(geo.max_offset_km, (51.5, -0.13), (48.86, 2.35)))
out.append(call(geo.haversine_m, np.array([0.0, 10.0]), 0.0, 0.0, np.array([1.0, 90.0])))
for d in (0.0, 49.9, 50.0, 50.1, 120.0, 150.0, 150.1, 250.0, 500.0):
    for t in (-2.0, -1.0, 0.0, 0.5, 1.0, 2.0, 3.7):
        for ang in (0.0, 0.6, 1.2, 2.5):
            out.append(call(gate_ok, (3.0, -4.0), (3.0 + d * math.cos(ang), -4.0 + d * math.sin(ang)), t, 100.0, 50.0))
for seq in ([(0, 0), (500, 1), (500, 2), (500, 5), (900, 6), (900, 7)], [(0, 0), (5000, 1), (120, 2), (5000, 30)],
            [(0, 5), (100, 4), (300, 7), (-200, 8)]):
    g = JumpGate(DEFAULTS)
    for e, t in seq:
        la, lo = geo.offset(35.8256, 10.6084, float(e), float(e) * 0.5)
        r = g.check(Estimate("gps", la, lo, float(t)))
        out.append(norm(r[0]) + " " + r[1].split(" ")[0])
    g.reset()
    out.append(norm(g.check(Estimate("gps", 1.0, 1.0, 50.0))[0]))
print("\n".join(out))
'''
_PROBED = {}


def probe_results(changed):
    """What the given stack (or a mutant of it) RETURNS on the probe's inputs, as text (same probe as hunt.py)."""
    key = changed[1] if changed else ""
    if key not in _PROBED:
        d = stack_copy(changed)
        try:
            code, out = sh(f"cd {d} && timeout 120 python3 -B - {d} <<'CHK14PROBE'\n{PROBE}\nCHK14PROBE", timeout=150)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        _PROBED[key] = out if code == 0 else f"crash {code} {out[-200:]}"
    return _PROBED[key]


def _code(text):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
                    and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree)


_RUNS = {}


def launch_run(changed=None):
    """launch_test of the student's file against the given judge (or a broken one), cached. (code, output)"""
    key = changed[1] if changed else ""
    if key not in _RUNS:
        _RUNS[key] = _launch_once(changed)
    return _RUNS[key]


def _launch_once(changed):
    d = stack_copy(changed, [LAUNCH])
    try:
        return sh(f"cd {d} && timeout 90 launch_test {LAUNCH}", timeout=120)
    finally:
        shutil.rmtree(d, ignore_errors=True)


_LAUNCH = {}


def launch_ok():
    student_file(LAUNCH)
    if "ok" not in _LAUNCH:
        publishers_ok(expected=0)
        _LAUNCH["ok"] = launch_run()
    code, out = _LAUNCH["ok"]
    for todo in ("7a", "7b"):
        if f'TODO {todo}' in out and "AssertionError: TODO" in out:
            raise CheckFailed(f"TODO {todo} is not written yet (the test still calls self.fail(\"TODO {todo}\"))")
    if code == 124:
        raise CheckFailed("launch_test did not finish in 90 s: does a test wait forever?")
    ran = re.findall(r"Ran (\d+) tests?", out)
    if code != 0:
        raise CheckFailed("your launch test FAILS on the real judge (a test that fails on a correct judge is a wrong "
                          "test). launch_test says:\n" + tail(out))
    c.ok(ran and int(ran[0]) >= 3, f"launch_test ran {ran[0] if ran else 0} tests while the judge ran: test_0, test_1 "
                                   "and test_2 must all be there")
    return out


@c.test("TODO 7: your launch test passes on the real judge, and the judge stops cleanly",
        hint="`launch_test test_arbiter_launch.py` (lab Step 6). Run `jobs` first and stop any judge of yours "
             "(`kill -INT $(jobs -p)`): the check starts its own.")
def _():
    out = launch_ok()
    c.ok(len(re.findall(r"Ran \d+ tests?", out)) >= 2, "the post-shutdown test (exit code) did not run")


@c.test("TODO 7: your launch test catches 4 broken judges",
        hint="TODO 7a: after the jump assert the state, the jump in the GPS source's status AND the number of positions; "
             "TODO 7b: the state, the reason AND no position. Lab Step 6 shows one of the broken judges.")
def _():
    launch_ok()
    alive = []
    for m in JUDGE:
        code, out = launch_run(mutate(m))
        if code == 0:
            alive.append(m)
    report_survivors(LAUNCH, alive, len(JUDGE))


@c.test("Step 6: a judge that re-publishes, caught by your launch test",
        hint="Lab Step 6: the change `if True:` in arbiter_v0.py, launch_test, read which test FAILED, then git restore.")
def _():
    launch_ok()
    code, out = launch_run(mutate(REPUBLISH))
    c.ok(code != 0 and re.search(r"FAIL: test_1", out),
         "your launch test does not fail on the judge that re-publishes: test_1 must count the positions "
         "(exactly one since it began)")
    c.ok(not re.search(r"FAIL: test_2", out), "on the re-publishing judge your test_2 fails too: it must drain() "
         "after the NaN fix (positions re-published BEFORE the NaN fix arrived are not its business)")
    p, name, n = answers("PREDICT_REPUBLISH", "REPUBLISH_FAILED", "REPUBLISH_COUNT")
    predicted("PREDICT_REPUBLISH", p)
    c.ok(isinstance(name, str) and ("test_1" in name or "5_km" in name) and "test_2" not in name
         and "test_0" not in name, "REPUBLISH_FAILED is not the one test that fails on the re-publishing judge")
    seen_n = re.search(r"(\d+) != 1", out)
    lo, hi = (int(seen_n.group(1)) - 3, int(seen_n.group(1)) + 3) if seen_n else REPUBLISH_RANGE
    c.ok(lo <= number(n, "REPUBLISH_COUNT") <= hi, "REPUBLISH_COUNT is not the number of positions test_1 counted "
         "(the number before `!= 1` in launch_test's output)")


@c.test("Step 7: report.md — three headings, your words and your numbers",
        hint="Keep the headings ## Bugs pinned, ## Mutants, ## Properties and the launch test; at least 40 words "
             "under each, with your measured values.")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    with open("report.md") as f:
        text = f.read()
    parts = re.split(r"^##\s+", text, flags=re.M)
    secs = {p.splitlines()[0].strip().lower(): p for p in parts[1:] if p.strip()}
    for h in ("bugs pinned", "mutants", "properties and the launch test"):
        if h not in secs:
            raise CheckFailed(f"report.md has no heading `## {h.capitalize()}`")
        body = re.sub(r"\(.*?\)", " ", secs[h].split("\n", 1)[1] if "\n" in secs[h] else "", flags=re.S)
        n = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body))
        c.ok(n >= 40, f"report.md, {h}: {n} words of yours (the brackets of the template do not count), 40 needed")
        c.ok(re.search(r"\d", body), f"report.md, {h}: quote at least one of your measured values")


c.milestone("bug_pinner", "Steps 0–1:", "TODO 1", "TODO 2", "TODO 3", "TODO 4", "TODO 5", "Step 3:",
            label="Bug pinner")
c.milestone("mutant_hunter", "Step", "TODO", label="Mutant hunter")

c.run()
