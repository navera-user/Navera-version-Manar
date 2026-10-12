"""runner_kit.py — the parts of a lab runner that turn the student's mistakes into one plain sentence.

Extracted from mission 01's where_am_i.py. A mission's runner (the script the student runs to see
their functions work: `python3 run_lab.py test`) uses it like this:

    import runner_kit as rk
    b = rk.load_student("beacons")                 # a syntax error in beacons.py → a plain message, exit 1
    a = rk.load_student("navera_lite.arbiter")     # a module of the NAVERA Lite package (navera_lite/arbiter.py)
    v, err = rk.call(b, "distance", (0, 0), (3, 4))
    print(err or f"distance = {v}")
    x, y = rk.need_ok(b, "find_position", beacons, ranges, n=2)   # stops the scenario with a plain message
    plt = rk.plt_or_none()                         # matplotlib (Agg) or None; no Axes3D warning

HOW A RUNNER GETS THIS FILE — copy it into the mission's files/ (and solutions/ needs nothing):

    cp courses/_lib/runner_kit.py courses/<NN-slug>/files/

Why a copy and not an import from /academy/lib: in the dashboard, /academy/lib (courses/_lib) is
mounted in the sandbox ONLY while check.py runs (server/app.py `_course_mounts`, with
`PYTHONPATH=/academy/lib`). The student's terminal, where the runner runs, has neither the mount
nor the PYTHONPATH. tools/try_lesson.py mounts /academy/lib for --shell too, so an
`import runner_kit` from /academy/lib would PASS the authoring test and FAIL for real students.
The copy sits next to the runner, so a plain `import runner_kit` works; keep the comment line
"you don't need to change anything in this file" for students. Version: 2026-10-12 (NAVERA Lite: package
modules, is_stub shared with academy_check).
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import contextlib
import importlib
import inspect
import io
import os
import sys
import traceback

STUB_MARKS = ("return None   # TODO", "return None  # TODO", "return None # TODO", 'NotImplementedError("TODO')


def _path_of(module_name):
    """navera_lite.arbiter → navera_lite/arbiter.py (a package → its __init__.py)."""
    rel = module_name.replace(".", os.sep)
    return os.path.join(rel, "__init__.py") if os.path.isdir(rel) else rel + ".py"


def load_student(module_name):
    """Import the student's module (beacons.py → load_student("beacons"); navera_lite/arbiter.py →
    load_student("navera_lite.arbiter")) with this folder first on sys.path; on any error at import
    time, print the error's last line simply and stop (exit 1)."""
    if module_name.endswith(".py"):
        module_name = module_name[:-3].replace("/", ".")
    path = _path_of(module_name)
    if not os.path.exists(path):
        sys.exit(f"{path} is missing in this folder — did you rename or move it?")
    here = os.getcwd()
    if here in sys.path:
        sys.path.remove(here)
    sys.path.insert(0, here)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return importlib.import_module(module_name)
    except Exception:
        print(f"{path} has an error, so it cannot be loaded:\n")
        traceback.print_exc(limit=0, file=sys.stdout)
        print("\nRead the LAST line above: it names the problem, the file and the line number.")
        sys.exit(1)


def _file_of(mod):
    """The module's file as the student sees it: navera_lite/arbiter.py, or beacons.py."""
    f = getattr(mod, "__file__", "") or ""
    if not f:
        return "your file"
    rel = os.path.relpath(f)
    return os.path.basename(f) if rel.startswith("..") else rel


def is_stub(func):
    """True if func is still the starter's TODO stub (same rule as academy_check.is_stub)."""
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        return False
    return any(m in src for m in STUB_MARKS)


_is_stub = is_stub          # older runners


def _hint(e):
    """One extra sentence for the errors students meet most (found in testing)."""
    s = str(e)
    if isinstance(e, NameError) and "sqrt" in s:
        return " — write math.sqrt, with `import math` at the top"
    if isinstance(e, NameError) and "'np'" in s:
        return " — add `import numpy as np` at the top of the file"
    if "could not be broadcast" in s or "inhomogeneous shape" in s:
        return (" — did you write `x = np.linalg.lstsq(...)` without `, *_`? lstsq returns four things: "
                "write `x, *_ = np.linalg.lstsq(A, b, rcond=None)`")
    if isinstance(e, TypeError) and "'NoneType'" in s:
        return " — a function you call returned None: does every path end with `return`?"
    if isinstance(e, ValueError) and "math domain error" in s:
        return " — math.sqrt / math.asin / math.acos got a value out of range (negative, or beyond ±1)"
    if isinstance(e, TypeError) and "cannot be interpreted as an integer" in s:
        return " — range() takes whole numbers only: use range(101) and x = i / 10"
    return ""


def call(mod, fn, *args, **kwargs):
    """Run mod.fn(*args). Returns (result, None) or (None, one plain sentence).

    The sentence says: not written yet (stub) / returned None (a path without return) /
    which exception, in which function and line — and when the crash is inside another of
    the student's functions, that it was called from fn (the mistake may be in what fn passes)."""
    f = _file_of(mod)
    mine_path = os.path.abspath(getattr(mod, "__file__", "") or f)
    func = getattr(mod, fn, None)
    if func is None:
        return None, f"{fn}() does not exist in {f} — check the spelling of its name (did you rename it?)"
    try:
        with contextlib.redirect_stdout(io.StringIO()):     # the student's debug prints stay out of the table
            result = func(*args, **kwargs)
    except NotImplementedError:
        return None, f"{fn}() is not written yet: write its TODO in {f} and `return` the result"
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        mine = [fr for fr in tb if os.path.abspath(fr.filename) == mine_path]
        where = f
        if mine:
            deepest = mine[-1]
            where = f"{f} line {deepest.lineno}"
            if deepest.name != fn:
                outer = next((fr for fr in mine if fr.name == fn), None)
                where = (f"in {deepest.name}() line {deepest.lineno}, called from {fn}()"
                         + (f" line {outer.lineno}" if outer else "") + " — the mistake may be in what "
                         f"{fn}() passes to {deepest.name}()")
        return None, f"{fn}() stopped with {type(e).__name__}: {e} ({where}){_hint(e)}"
    if result is None:
        if is_stub(func):
            return None, f"{fn}() is not written yet: write its TODO in {f} and `return` the result"
        return None, (f"{fn}() returned None for this case: every path must end with a `return` "
                      "(an `if` without `else`? a `return` missing after the loop?)")
    return result, None


def need_ok(mod, fn, *args, n=None, kind=None, **kwargs):
    """Call a function a scenario needs; stop the runner with a plain message if it is not usable yet.
    n: the result must be a list/tuple of n numbers. kind: the result must be of this type
    (e.g. float — an int is accepted for float, a bool is not)."""
    v, err = call(mod, fn, *args, **kwargs)
    if err:
        sys.exit(err)
    if n is not None:
        ok = isinstance(v, (list, tuple)) and len(v) == n and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
        if not ok and hasattr(v, "shape") and getattr(v, "shape", None) == (n,):
            ok = True                                    # a numpy array of n numbers is fine
        if not ok:
            sys.exit(f"{fn}() must return {n} numbers, like (1.0, 2.0), but it returned {v!r}.")
    if kind is not None:
        if kind is bool:
            good = isinstance(v, bool)
        elif kind is float:
            good = isinstance(v, (int, float)) and not isinstance(v, bool)
        else:
            good = isinstance(v, kind) and not isinstance(v, bool)
        if not good:
            sys.exit(f"{fn}() must return a {kind.__name__}, but it returned {v!r} "
                     f"(a {type(v).__name__}).")
    return v


def plt_or_none():
    """matplotlib.pyplot with the Agg backend (pictures are saved, never shown), or None if absent.
    Hides the harmless 'Unable to import Axes3D' warning of the sandbox's matplotlib."""
    try:
        import warnings
        warnings.filterwarnings("ignore", message="Unable to import Axes3D")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        return None


def saved(path):
    """The line to print after saving a picture."""
    print(f"\n🖼  picture saved: {path} (open it in the 📝 Code tab)")
