"""Helpers for the lessons' check.py — friendly results for beginners.

    from academy_check import Checker, load_student, sh
    c = Checker()

    @c.test("distance() gives 0 m between a point and itself",
            hint="When both points are the same, every difference is 0.")
    def _():
        m = load_student("distance.py")
        c.near(m.distance(36.0, 10.0, 36.0, 10.0), 0.0, tol=0.01)

    c.run()

Each test prints ✔ or ✘ (with the hint); the last line is read by the dashboard.
A test that fails stops only itself. A test may call c.skip("why") to be skipped.

Also here (Batch 0, 2026-10-10): predicted() / explained() / TEACHER_NOTE for PREDICT_… and
EXPLAIN_… answers, run(fn, *args, seconds=40) with a time limit, and the ROS guard
publishers_ok(topic, expected=1) that fails clearly when a leftover node also publishes.

NAVERA Lite (2026-10-12): load_student("navera_lite.arbiter") or load_student("navera_lite/arbiter.py")
imports a module of the student's package with the lesson folder first on sys.path (fresh=True
re-imports every navera_lite module); is_stub(func) tells a TODO stub (same rule as runner_kit);
publishers_ok() watches /navera_lite/status by default; sh()/Background() source ROS 2 only.

Sealed checks (2026-10-13, see AUTHORING.md "check.py — security"): the server and try_lesson start
check.py through academy_sealed.py. check.py and courses/<id>/hidden/ then exist only in the checker's
memory, load_student() returns proxies of modules that run in a separate student process
(academy_remote.py), every command started by the check runs without access to them, and the result
goes to the server through a private channel (an ACADEMY_RESULT line printed by anyone is ignored).
hidden("name") reads a file of courses/<id>/hidden/. Student files are always compiled from their
source (never a stale __pycache__).
"""
import importlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import traceback


class CheckFailed(AssertionError):
    pass


class Skip(Exception):
    pass


_SEALED = None        # set by academy_sealed.py: {"report": fn(result), "hidden": {name: bytes}}


def sealed():
    """True when this check runs sealed (server, try_lesson)."""
    return _SEALED is not None


def hidden(name, text=True):
    """A file of courses/<id>/hidden/ (test data the student must never see). Sealed: from the
    checker's memory (never on disk in the sandbox). Run by hand (python3 check.py in the course
    folder): read from the folder. text=False gives bytes."""
    if _SEALED is not None:
        try:
            data = _SEALED["hidden"][name]
        except KeyError:
            raise FileNotFoundError(f"hidden/{name} is not part of this mission's hidden data") from None
    else:
        main = sys.modules.get("__main__")
        base = os.path.dirname(os.path.abspath(getattr(main, "__file__", "") or "."))
        with open(os.path.join(base, "hidden", name), "rb") as f:
            data = f.read()
    return data.decode("utf-8") if text else data


def hidden_names():
    if _SEALED is not None:
        return sorted(_SEALED["hidden"])
    main = sys.modules.get("__main__")
    base = os.path.join(os.path.dirname(os.path.abspath(getattr(main, "__file__", "") or ".")), "hidden")
    out = []
    for d, _, fs in os.walk(base):
        out += [os.path.relpath(os.path.join(d, f), base) for f in fs]
    return sorted(out)


class Checker:
    def __init__(self):
        self.tests = []
        self.milestones = {}          # name -> list of title prefixes that must all pass

    def milestone(self, name, *title_prefixes, label=None):
        """A named part of a mission (e.g. a session) reached when every check whose title starts with one
        of title_prefixes passes. Reported in ACADEMY_RESULT; the dashboard can show it as a badge."""
        self.milestones[name] = list(title_prefixes)
        self.milestone_labels = getattr(self, "milestone_labels", {})
        self.milestone_labels[name] = label or name

    def test(self, title, hint=None):
        def deco(fn):
            self.tests.append((title, hint, fn))
            return fn
        return deco

    # ---- assertions with readable messages
    def ok(self, cond, msg="this is not right yet"):
        if not cond:
            raise CheckFailed(msg)

    def eq(self, got, want, what="the result"):
        if got != want:
            raise CheckFailed(f"{what} is {got!r}, expected {want!r}")

    def near(self, got, want, tol, what="the result"):
        try:
            g = float(got)
        except (TypeError, ValueError):
            raise CheckFailed(f"{what} should be a number, got {got!r}")
        if not math.isfinite(g):
            raise CheckFailed(f"{what} is {g} — not a usable number")
        if abs(g - want) > tol:
            # the right value is not shown: the student finds it with their own code
            raise CheckFailed(f"{what} is {g:.6g}: {'too high' if g > want else 'too low'} "
                              f"(it must be within ± {tol:g} of the right value)")

    def file_exists(self, path):
        if not os.path.exists(path):
            raise CheckFailed(f"the file {path} does not exist yet")

    def skip(self, why):
        raise Skip(why)

    def run(self):
        passed = 0
        ok_titles = []
        print(f"Running {len(self.tests)} checks…\n")
        for i, (title, hint, fn) in enumerate(self.tests, 1):
            try:
                fn()
                passed += 1
                ok_titles.append(title)
                print(f"✔ {i}. {title}")
            except Skip as e:
                passed += 1
                print(f"➖ {i}. {title} — skipped: {e}")
            except CheckFailed as e:
                print(f"✘ {i}. {title}\n     → {e}")
                if hint:
                    print(f"     💡 Hint: {hint}")
            except StudentError as e:
                print(f"✘ {i}. {title}\n     → {e}")
                if hint:
                    print(f"     💡 Hint: {hint}")
            except Exception as e:  # an error inside the student's code
                where = _where(e)
                print(f"✘ {i}. {title}\n     → your code raised {type(e).__name__}: {e}"
                      + (f"  ({where})" if where else ""))
                if hint:
                    print(f"     💡 Hint: {hint}")
        total = len(self.tests)
        print()
        print("🎉 All checks pass!" if passed == total else f"{passed} of {total} checks pass. Keep going!")
        reached = []
        for name, prefixes in self.milestones.items():
            needed = [t for t, _, _ in self.tests if any(t.startswith(pre) for pre in prefixes)]
            if needed and all(t in ok_titles for t in needed):
                reached.append(name)
        if reached:                       # the last milestone reached is the most complete one
            print(f"🏅 {getattr(self, 'milestone_labels', {}).get(reached[-1], reached[-1])}")
        result = {"passed": passed, "total": total}
        if reached:
            result["milestones"] = reached
        if _SEALED is not None:
            _SEALED["report"](result)       # the private channel; nothing printed can fake it
        else:
            print("ACADEMY_RESULT " + json.dumps(result))
        sys.stdout.flush()
        sys.exit(0 if passed == total else 1)


class StudentError(Exception):
    pass


_loaded = {}
PACKAGE = "navera_lite"
STUB_MARKS = ("return None   # TODO", "return None  # TODO", "return None # TODO", 'NotImplementedError("TODO')


def _show(path):
    """A file name as the student knows it: relative to the lesson folder (navera_lite/arbiter.py)."""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return os.path.basename(path)
    return os.path.basename(path) if rel.startswith("..") else rel


def _where(e):
    """'navera_lite/arbiter.py line 12': the deepest frame of the student's code in a traceback."""
    if getattr(e, "academy_where", None):          # raised by the student's code in the student process
        return e.academy_where
    tb = traceback.extract_tb(e.__traceback__)
    return next((f"{_show(f.filename)} line {f.lineno}" for f in reversed(tb)
                 if not f.filename.endswith(("check.py", "academy_check.py"))
                 and "importlib" not in f.filename), "")


def is_stub(func):
    """True if func is still the starter's TODO stub (`return None   # TODO…` or
    `raise NotImplementedError("TODO…")`). The same rule as runner_kit.is_stub."""
    import inspect
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        return False
    return any(m in src for m in STUB_MARKS)


def _module_of(filename):
    """("module.name", "path/of/module.py") for "beacons.py", "navera_lite/arbiter.py" or
    "navera_lite.arbiter"."""
    if filename.endswith(".py"):
        rel = os.path.normpath(filename)
        return rel[:-3].replace(os.sep, "."), rel
    rel = filename.replace(".", os.sep)
    if os.path.isdir(rel):
        return filename, os.path.join(rel, "__init__.py")
    return filename, rel + ".py"


def load_student(filename, fresh=False):
    """Import the student's file (in the current lesson folder) as a module.

    "beacons.py": a single file, loaded by path (as mission 01). "navera_lite/arbiter.py" or
    "navera_lite.arbiter": a module of the student's package, imported by name with the lesson folder
    first on sys.path, so `from navera_lite.geo import …` inside it finds the lesson's own copy.
    fresh=True loads it again (after the check changed a file); for the package it drops every
    navera_lite module first.

    Sealed: the module is imported in the student process and a proxy comes back (academy_remote).
    The source is always compiled fresh (no __pycache__)."""
    if _SEALED is not None:
        import academy_remote
        return academy_remote.load(filename, fresh)
    _fresh_imports()
    modname, rel = _module_of(filename)
    if "." not in modname and filename.endswith(".py"):
        return _load_file(filename, fresh)
    path = os.path.abspath(rel)
    if not os.path.exists(path):
        raise StudentError(f"{rel} is missing — did you delete or rename it?")
    if path in _loaded and not fresh:
        return _loaded[path]
    here = os.getcwd()
    if here in sys.path:
        sys.path.remove(here)
    sys.path.insert(0, here)
    top = modname.split(".")[0]
    if fresh:
        for k in [k for k in sys.modules if k == top or k.startswith(top + ".")]:
            del sys.modules[k]
        for k in [k for k in _loaded if k.startswith(os.path.join(here, top) + os.sep)]:
            del _loaded[k]
        importlib.invalidate_caches()
    try:
        mod = importlib.import_module(modname)
    except SyntaxError as e:
        raise StudentError(f"{_show(e.filename or rel)} has a syntax error on line {e.lineno}: {e.msg}")
    except Exception as e:
        where = _where(e)
        raise StudentError(f"{rel} crashed when loading: {type(e).__name__}: {e}" + (f" ({where})" if where else ""))
    _loaded[path] = mod
    return mod


def _load_file(filename, fresh=False):
    path = os.path.abspath(filename)
    if not os.path.exists(path):
        raise StudentError(f"{filename} is missing — did you delete or rename it?")
    if path in _loaded and not fresh:
        return _loaded[path]
    name = "student_" + os.path.splitext(os.path.basename(path))[0]
    spec = _spec_fresh(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(mod)
    except SyntaxError as e:
        raise StudentError(f"{filename} has a syntax error on line {e.lineno}: {e.msg}")
    except Exception as e:
        raise StudentError(f"{filename} crashed when loading: {type(e).__name__}: {e}")
    finally:
        sys.path.pop(0)
    _loaded[path] = mod
    return mod


def _fresh_imports():
    import academy_remote
    return academy_remote.install_fresh_source_hook()


def _spec_fresh(name, path):
    import academy_remote
    return academy_remote.spec_from_file_fresh(name, path)


def need(mod, *names):
    for n in names:
        if not hasattr(mod, n):
            raise StudentError(f"I can't find `{n}` in your file — check the spelling of its name")
    return [getattr(mod, n) for n in names]


def sh(cmd, timeout=60, check=False):
    """Run a shell command (with ROS sourced); returns (exit code, output)."""
    full = "source /opt/ros/humble/setup.bash >/dev/null 2>&1; " + cmd
    try:
        r = subprocess.run(["bash", "-c", full], capture_output=True, text=True, timeout=timeout)
        out = r.stdout + r.stderr
        if check and r.returncode != 0:
            raise CheckFailed(f"`{cmd}` failed:\n{out[-800:]}")
        return r.returncode, out
    except subprocess.TimeoutExpired as e:
        if check:
            raise CheckFailed(f"`{cmd}` did not finish in {timeout} s")
        return 124, (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")


class Background:
    """Start a command in the background for the length of a test:
        with Background("python3 my_node.py"):
            ... wait for its messages ...
    """
    def __init__(self, cmd, settle=1.5):
        self.cmd, self.settle = cmd, settle

    def __enter__(self):
        import time
        full = "source /opt/ros/humble/setup.bash >/dev/null 2>&1; exec " + self.cmd
        self.p = subprocess.Popen(["bash", "-c", full], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, start_new_session=True)
        time.sleep(self.settle)
        if self.p.poll() is not None:
            out = self.p.stdout.read()
            raise CheckFailed(f"`{self.cmd}` stopped right away:\n{out[-1200:]}")
        return self

    def output(self):
        return self._out if hasattr(self, "_out") else ""

    def __exit__(self, *a):
        import os as _os, signal
        try:
            _os.killpg(self.p.pid, signal.SIGINT)
            self._out = self.p.communicate(timeout=5)[0]
        except Exception:
            try:
                _os.killpg(self.p.pid, signal.SIGKILL)
            except Exception:
                pass
            self._out = ""
        return False


# ---------------------------------------------------------------- written answers (PREDICT_… / EXPLAIN_…)
TEACHER_NOTE = (" (Your teacher reads these answers with a rubric: the check only verifies that you "
                "really answered.)")


def words(s):
    """The words of a text (2+ letters, accents allowed)."""
    import re
    return re.findall(r"[A-Za-zÀ-ÿ']{2,}", str(s))


def predicted(name, value):
    """A PREDICT_… answer: graded only as "written" (any honest guess passes)."""
    if not (isinstance(value, str) and value.strip() != ""):
        raise CheckFailed(f"{name} is empty — write your guess (any honest guess is fine)")


def explained(name, value, *groups, min_words=8):
    """An EXPLAIN_… answer: a real sentence that touches each group of ideas.

    groups: (keywords, idea) pairs; keywords are regular expressions tried on the lower-case text,
    one match per group is enough, e.g.
        explained("EXPLAIN_GATE", a, ([r"speed", r"m/s"], "the speed limit"), ([r"margin"], "the margin"))
    """
    import re
    if not (isinstance(value, str) and value.strip() != ""):
        raise CheckFailed(f"{name} is still empty")
    if len(words(value)) < min_words:
        raise CheckFailed(f"{name} is very short — explain in one to three full sentences")
    low = value.lower()
    for keywords, idea in groups:
        if not any(re.search(k, low) for k in keywords):
            raise CheckFailed(f"{name} does not explain {idea} yet." + TEACHER_NOTE)


# ---------------------------------------------------------------- calling the student's code safely
def run(fn, *args, seconds=40, **kwargs):
    """Call a student function with a time limit; its prints are hidden. A crash or an endless loop
    becomes a clear ✘ (CheckFailed). Uses SIGALRM: call it from the main thread (as check.py does)."""
    import contextlib
    import io
    import signal

    def too_long(*_):
        raise TimeoutError
    name = getattr(fn, "__name__", "the function")
    old = signal.signal(signal.SIGALRM, too_long)
    signal.alarm(max(1, int(seconds)))
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs)
    except TimeoutError:
        raise CheckFailed(f"{name}() did not finish in {seconds} s — is a loop endless?")
    except NotImplementedError:
        raise CheckFailed(f"{name}() is not written yet (it still raises NotImplementedError)")
    except CheckFailed:
        raise
    except Exception as e:
        where = _where(e)
        raise CheckFailed(f"{name}() stopped with {type(e).__name__}: {e}" + (f" ({where})" if where else ""))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# ---------------------------------------------------------------- ROS guard: one publisher per topic
def topic_publishers(topic, spin_s=2):
    """(count, [node names]) of the publishers on `topic`, from `ros2 topic info -v` (no daemon, so a
    stale daemon cannot lie). count is None when ros2 could not answer."""
    import re
    code, out = sh(f"ros2 topic info -v {topic} --no-daemon --spin-time {spin_s}", timeout=30 + spin_s)
    m = re.search(r"Publisher count:\s*(\d+)", out)
    if not m:
        if "Unknown topic" in out:
            return 0, []
        return None, []
    names, node = [], None
    for line in out.splitlines():
        if line.startswith("Node name:"):
            node = line.split(":", 1)[1].strip()
        elif line.startswith("Endpoint type:") and "PUBLISHER" in line and node:
            names.append(node)
    return int(m.group(1)), names


def publishers_ok(topic="/navera_lite/status", expected=1, spin_s=2, tries=2, wait_s=8.0):
    """Fail with a clear message unless exactly `expected` nodes publish on `topic`.

    Use it before a test that reads a topic: expected=0 before starting the student's node (no
    leftover from an earlier run), expected=1 once it runs. A leftover node (a terminal still running
    `ros2 run …` or `python3 my_node.py`, or a node started in the background) also publishes, and the
    check would read its messages instead of the new ones. Returns the count.

    Discovery is not instant: one `ros2 topic info` can miss a node (tested: "Unknown topic" while two
    nodes published). So it asks `tries` times and keeps the largest count (a node is never invented),
    stopping early as soon as there are too many; while it still sees too FEW (a node just launched is
    not discovered yet) it keeps asking until `wait_s` seconds have passed."""
    import time
    best, names = None, []
    deadline = time.monotonic() + wait_s
    asked = 0
    while True:
        n, who = topic_publishers(topic, spin_s)
        asked += 1
        if n is not None and (best is None or n > best):
            best, names = n, who
        if best is not None and best > expected:
            break
        if asked >= max(1, tries) and (best == expected or time.monotonic() >= deadline):
            break
    n = best
    if n is None:
        raise CheckFailed(f"the check could not ask ROS 2 who publishes on {topic} (`ros2 topic info` failed)")
    if n == expected:
        return n
    who = f" ({', '.join(sorted(set(names)))})" if names else ""
    if n > expected:
        raise CheckFailed(
            f"{n} node(s) publish on {topic}{who}, but the check expects {expected}. A node from an earlier "
            "run is probably still running: list your background jobs with `jobs` and stop them with "
            "`kill -INT %1` (or `kill -INT $(jobs -rp)`), then press ✔ Check my work again. `ros2 topic info -v " + topic + "` lists them.")
    raise CheckFailed(f"{n} node(s) publish on {topic}, the check expects {expected}: is your node "
                      "running, and does it publish on exactly this topic name?")


def wait_for_messages(topic, msg_type, count=1, timeout=10.0):
    """Collect `count` messages from a ROS 2 topic (rclpy); returns the list."""
    import time
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    started_here = not rclpy.ok()
    if started_here:
        rclpy.init()
    node = rclpy.create_node("academy_checker")
    got = []
    # BEST_EFFORT receives from both BEST_EFFORT and RELIABLE publishers.
    sub = node.create_subscription(msg_type, topic, got.append, qos_profile_sensor_data)
    end = time.time() + timeout
    try:
        while time.time() < end and len(got) < count:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        if started_here:
            rclpy.shutdown()
    return got
