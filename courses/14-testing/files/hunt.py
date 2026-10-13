"""hunt.py — the mutant hunter's runner (mission 14). It never changes your navera_lite/.

    python3 hunt.py test    your two test files on the stack as given: do they pass, and keep the rules?
    python3 hunt.py         the same, then your tests against 7 TRAINING mutants: which ones they kill
    python3 hunt.py mine    your own mutants (my_mutants.py, TODO 6): does the stack's own suite miss them,
                            and do your tests kill them?

A MUTANT is a copy of the stack with one small change in navera_lite/geo.py or navera_lite/guard.py. Each
one runs in a temporary folder: your tests are copied next to the changed stack and pytest runs them. If at
least one test fails, the mutant is KILLED; if every test passes, it SURVIVED (lesson §4).
✔ Check my work does the same with mutants you have never seen.

hypothesis runs here with a fixed seed (the same examples on every run) and without shrinking (faster):
a property that kills a mutant here may print a bigger Falsifying example than in your own runs.
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEST_FILES = ["test_geo_examples.py", "test_geo_properties.py"]
TARGETS = ("geo.py", "guard.py")

# (number, file, what changes, old text, new text). Read them: each one is a bug someone could really write.
TRAINING = [
    (1, "geo.py", "haversine_m: the radius instead of the diameter",
     "d = 2.0 * EARTH_RADIUS_M * np.arcsin", "d = EARTH_RADIUS_M * np.arcsin"),
    (2, "geo.py", "is_finite_latlon: longitudes up to 190° accepted",
     "abs(lo) <= 180.0", "abs(lo) <= 190.0"),
    (3, "geo.py", "is_finite_latlon: only the latitude is tested for NaN and infinity",
     "finite = math.isfinite(la) and math.isfinite(lo)", "finite = math.isfinite(la)"),
    (4, "geo.py", "offset: the latitude step is added in radians, not degrees",
     "lat2 = lat + math.degrees(n_m / EARTH_RADIUS_M)", "lat2 = lat + n_m / EARTH_RADIUS_M"),
    (5, "geo.py", "enu_flat: the longitude difference is not brought back into [−180, 180)",
     "dlon = (lon - lon0 + 180.0) % 360.0 - 180.0", "dlon = lon - lon0"),
    (6, "guard.py", "gate_ok: the elapsed time is ignored (the gate never grows)",
     "v_max_mps * max(0.0, elapsed_s) + margin_m", "v_max_mps + margin_m"),
    (7, "guard.py", "gate_ok: a negative elapsed time shrinks the gate",
     "max(0.0, elapsed_s)", "elapsed_s"),
]

# rule 3 of the test files: through inputs and outputs only (a test that reads the source would "kill"
# every mutant without testing anything)
FORBIDDEN = [r"\bopen\s*\(", r"__file__", r"\binspect\b", r"getsource", r"\bhashlib\b", r"__code__", r"co_code",
             r"\bimportlib\b", r"sys\.modules", r"\bsubprocess\b", r"os\.system", r"\bpathlib\b", r"read_text",
             r"read_bytes", r"\bexec\s*\(", r"\beval\s*\(", r"\blinecache\b", r"__loader__", r"__spec__",
             r"\bmarshal\b", r"\bimport\s+dis\b", r"\bfrom\s+dis\b", r"(?<!re\.)\bcompile\s*\("]

CONFTEST = '''from hypothesis import Phase, settings
settings.register_profile("hunt", derandomize=True, database=None, deadline=None,
                          phases=[Phase.explicit, Phase.generate])
'''


def say(text=""):
    print(text, flush=True)


def stop(text):
    say(text)
    sys.exit(1)


def rules_broken(path):
    """The forbidden words found in a test file (rule 3)."""
    text = open(path).read()
    return sorted({m.group(0) for pat in FORBIDDEN for m in re.finditer(pat, text)})


def given_source(name):
    """navera_lite/<name> as committed at the tag `start` (Step 1), after checking yours is unchanged."""
    r = subprocess.run(["git", "show", f"start:navera_lite/{name}"], cwd=HERE, capture_output=True, text=True)
    if r.returncode != 0:
        stop("This folder is not a git repository with the tag `start` yet: do lab Step 1 first\n"
             "    bash navera_lite/tools/init_repo.sh")
    mine = open(os.path.join(HERE, "navera_lite", name)).read()
    if mine != r.stdout:
        stop(f"navera_lite/{name} is not the file of the start commit (see `git diff start -- navera_lite`).\n"
             f"Your tests must be judged on the stack as given: `git restore navera_lite/{name}` first.")
    return r.stdout


def copy_of_stack(changed=None, with_tests=True):
    """A temporary lesson folder: navera_lite/ (with `changed` = {file: text}), pytest.ini, your test files."""
    d = tempfile.mkdtemp(prefix="hunt_")
    shutil.copytree(os.path.join(HERE, "navera_lite"), os.path.join(d, "navera_lite"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    for name, text in (changed or {}).items():
        with open(os.path.join(d, "navera_lite", name), "w") as f:
            f.write(text)
    for f in (["pytest.ini"] + (TEST_FILES if with_tests else [])):
        if os.path.exists(os.path.join(HERE, f)):
            shutil.copy(os.path.join(HERE, f), d)
    with open(os.path.join(d, "conftest.py"), "w") as f:
        f.write(CONFTEST)
    return d


def pytest(folder, files, timeout=300):
    """(exit code, last lines) of pytest on `files` in `folder`. 0 = all passed, 1 = a test failed."""
    cmd = [sys.executable, "-B", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-p", "_hypothesis_pytestplugin",
           "--hypothesis-profile=hunt", *files]
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")     # no ROS plugins: 1 s faster per run
    try:
        r = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 3, f"pytest did not finish in {timeout} s — is a test endless?"
    return r.returncode, (r.stdout + r.stderr).strip()


def tail(text, n=12):
    return "\n".join("      " + line for line in text.splitlines()[-n:])


def baseline():
    """Your tests must exist, keep the rules and pass on the stack as given. Returns the files to run."""
    files = [f for f in TEST_FILES if os.path.exists(os.path.join(HERE, f))]
    if not files:
        stop("No test file found: test_geo_examples.py and test_geo_properties.py should be here.")
    for f in files:
        bad = rules_broken(os.path.join(HERE, f))
        if bad:
            stop(f"{f} uses {', '.join(bad)}: rule 3 says test through inputs and outputs only (no reading of "
                 "files or source code). Remove it.")
    for name in TARGETS:
        given_source(name)
    d = copy_of_stack()
    try:
        code, out = pytest(d, files)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    last = out.splitlines()[-1] if out else ""
    if code == 5:
        stop("pytest found no test in your files (a test is a function whose name starts with test_).")
    if code != 0:
        stop("Your tests do NOT all pass on the stack as given, so they cannot judge a mutant yet.\n"
             "A test that fails on correct code is a wrong test: check its expected value (metres or degrees?)\n"
             "and its tolerance (lesson §2). pytest says:\n" + tail(out, 20))
    say(f"Your tests on the stack as given: {last}  ✔")
    return files


def run_training(files):
    sources = {name: given_source(name) for name in TARGETS}
    say("\nTraining mutants (one change each, in a temporary copy):")
    killed, survivors = 0, []
    for num, name, what, old, new in TRAINING:
        if sources[name].count(old) != 1:
            stop(f"hunt.py: mutant {num} no longer fits navera_lite/{name} (tell your teacher).")
        d = copy_of_stack({name: sources[name].replace(old, new)})
        try:
            code, out = pytest(d, files)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        verdict = "✘ KILLED" if code == 1 else ("survived" if code == 0 else f"? pytest exit code {code}")
        if code == 1:
            killed += 1
        elif code == 0:
            survivors.append(num)
        say(f"  {num}. {what:<70} {verdict}")
        say(f"       {name}:  {old}   →   {new}")
    pct = 100.0 * killed / len(TRAINING)
    say(f"\nMutation score on the training set: {killed} killed of {len(TRAINING)} ({pct:.0f} %)."
        + (f" Survivors: {', '.join(map(str, survivors))}." if survivors else ""))
    if survivors:
        say("For each survivor: which input would show the difference? If there is none, it is an EQUIVALENT\n"
            "mutant (lesson §4) and no test can kill it.")


def load_my_mutants():
    path = os.path.join(HERE, "my_mutants.py")
    if not os.path.exists(path):
        stop("my_mutants.py is missing in this folder.")
    sys.path.insert(0, HERE)
    try:
        import my_mutants
    except Exception as e:
        stop(f"my_mutants.py has an error, so it cannot be loaded: {type(e).__name__}: {e}")
    muts = getattr(my_mutants, "MUTANTS", None)
    if not isinstance(muts, (list, tuple)) or not muts:
        stop("my_mutants.py: MUTANTS is still empty — TODO 6 (lab Step 5).")
    return muts


def without_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
                    and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree)


def span_of(name, old, sources):
    """(file, first line, last line) of `old` in the given file."""
    start = sources[name].index(old)
    first = sources[name].count("\n", 0, start)
    return name, first, first + old.count("\n")


def training_overlap(name, old, sources):
    a = sources[name].index(old), sources[name].index(old) + len(old)
    for _, t_name, _, t_old, _ in TRAINING:
        if t_name == name:
            b = sources[name].index(t_old), sources[name].index(t_old) + len(t_old)
            if a[0] < b[1] and b[0] < a[1]:
                return True
    return False


def check_mutant(m, sources):
    """(file, mutated text) or raise ValueError with a plain reason."""
    if not (isinstance(m, (list, tuple)) and len(m) == 3 and all(isinstance(x, str) for x in m)):
        raise ValueError(f"{m!r} is not a tuple of three texts (file, old, new)")
    name, old, new = m
    if name not in TARGETS:
        raise ValueError(f"the file must be \"geo.py\" or \"guard.py\", not {name!r}")
    n = sources[name].count(old) if old else 0
    if n != 1:
        raise ValueError(f"the old text appears {n} times in navera_lite/{name}; it must appear exactly once "
                         "(copy it exactly, spaces included, or take a longer piece)")
    if training_overlap(name, old, sources):
        raise ValueError("it changes the same code as a training mutant of hunt.py: find a hole of your own")
    text = sources[name].replace(old, new)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise ValueError(f"the mutated {name} is not valid Python (line {e.lineno}: {e.msg})")
    if without_docstrings(tree) == without_docstrings(ast.parse(sources[name])):
        raise ValueError("it changes only a comment, a docstring or the layout: the code is the same")
    return name, text


def run_mine(files):
    muts = load_my_mutants()
    sources = {name: given_source(name) for name in TARGETS}
    suite = sorted(f"navera_lite/tests/{f}" for f in os.listdir(os.path.join(HERE, "navera_lite", "tests"))
                   if f.startswith("test_") and f.endswith(".py") and f != "test_ros_smoke.py")
    say(f"\nYour mutants ({len(muts)}; TODO 6 needs 3 that pass both tests):")
    good = 0
    seen = set()
    for i, m in enumerate(muts, 1):
        try:
            name, text = check_mutant(m, sources)
        except ValueError as e:
            say(f"  {i}. refused: {e}")
            continue
        f_, first, last = span_of(name, m[1], sources)
        if any(f_ == g and first <= l2 and l1 <= last for g, l1, l2 in seen):
            say(f"  {i}. refused: it changes the same line as an earlier mutant — three DIFFERENT holes")
            continue
        seen.add((f_, first, last))
        d = copy_of_stack({name: text})
        try:
            code_suite, out_suite = pytest(d, suite)
            code_mine, _ = pytest(d, files)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        survives = code_suite == 0
        killed = code_mine == 1
        say(f"  {i}. {name}:  {m[1].strip()}   →   {m[2].strip()}")
        say(f"       the stack's own suite: " + ("misses it ✔ (it survives)" if survives else
                                                  "kills it ✘ — the stack is already protected here: find another"))
        if not survives:
            say(tail(out_suite, 3))
        say(f"       your tests:            " + ("kill it ✔" if killed else
                                                  "miss it ✘ — add a test to test_geo_examples.py (TODO 6b)"))
        good += survives and killed
    say(f"\n{good} of your mutants are good ones (missed by the stack's suite, killed by your tests).")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "train"
    if mode not in ("test", "train", "mine"):
        stop("Usage: python3 hunt.py [test | mine]")
    files = baseline()
    if mode == "train":
        run_training(files)
    elif mode == "mine":
        run_mine(files)


if __name__ == "__main__":
    main()
