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
"""
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


class Checker:
    def __init__(self):
        self.tests = []

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
        if not math.isfinite(g) or abs(g - want) > tol:
            raise CheckFailed(f"{what} is {g:.6g}, expected {want:.6g} (± {tol:g})")

    def file_exists(self, path):
        if not os.path.exists(path):
            raise CheckFailed(f"the file {path} does not exist yet")

    def skip(self, why):
        raise Skip(why)

    def run(self):
        passed = 0
        print(f"Running {len(self.tests)} checks…\n")
        for i, (title, hint, fn) in enumerate(self.tests, 1):
            try:
                fn()
                passed += 1
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
                tb = traceback.extract_tb(e.__traceback__)
                where = next((f"{os.path.basename(f.filename)} line {f.lineno}" for f in reversed(tb)
                              if not f.filename.endswith(("check.py", "academy_check.py"))), "")
                print(f"✘ {i}. {title}\n     → your code raised {type(e).__name__}: {e}"
                      + (f"  ({where})" if where else ""))
                if hint:
                    print(f"     💡 Hint: {hint}")
        total = len(self.tests)
        print()
        print("🎉 All checks pass!" if passed == total else f"{passed} of {total} checks pass. Keep going!")
        print("ACADEMY_RESULT " + json.dumps({"passed": passed, "total": total}))
        sys.stdout.flush()
        sys.exit(0 if passed == total else 1)


class StudentError(Exception):
    pass


_loaded = {}


def load_student(filename, fresh=False):
    """Import the student's file (in the current lesson folder) as a module."""
    path = os.path.abspath(filename)
    if not os.path.exists(path):
        raise StudentError(f"{filename} is missing — did you delete or rename it?")
    if path in _loaded and not fresh:
        return _loaded[path]
    name = "student_" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
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


def need(mod, *names):
    for n in names:
        if not hasattr(mod, n):
            raise StudentError(f"I can't find `{n}` in your file — check the spelling of its name")
    return [getattr(mod, n) for n in names]


def sh(cmd, timeout=60, check=False):
    """Run a shell command (with ROS sourced); returns (exit code, output)."""
    full = "source /opt/ros/humble/setup.bash >/dev/null 2>&1; " \
           "[ -f ~/navera/install/setup.bash ] && source ~/navera/install/setup.bash >/dev/null 2>&1; " + cmd
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
        full = "source /opt/ros/humble/setup.bash >/dev/null 2>&1; " \
               "[ -f ~/navera/install/setup.bash ] && source ~/navera/install/setup.bash >/dev/null 2>&1; exec " + self.cmd
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
