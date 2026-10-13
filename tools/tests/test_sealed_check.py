"""Attack tests of the sealed check (server/sealed.py, courses/_lib/academy_sealed.py, academy_remote.py).

A malicious "student" tries, from code the checker runs (a shell script, a Python function, a module
imported by load_student, ~/.bashrc), to read check.py and its answers, list /academy/courses, read the
hidden test data, read the checker's memory/fds through /proc, raise the checker's Skip, print a fake
ACADEMY_RESULT and write on the result channel. Everything must fail and the REAL score must come back.

    python3 -m pytest -q tools/tests/test_sealed_check.py

Uses throw-away students (_try_…_attack, _sealtest_…) and, for the hidden-data test, a throw-away course
folder in a temporary directory (never courses/).
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "server"))
import config  # noqa: E402
import sealed  # noqa: E402
import workspaces  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bubblewrap")

# what any attack writes to the student's home: it must never contain one of these
SECRETS_02 = ["Q1_PY_FILES", "Q3_ROS_LINES = 134", "Q8_ERROR_NODES"]
SECRETS_03 = ["SELF_OK", "def loops_in", "0.83485"]

PROBE_SH = r'''
leak=~/leak_{tag}.txt
{{
echo "== cat check.py"; cat /academy/courses/*/check.py 2>&1 | head -5
echo "== ls courses"; ls -laR /academy/courses 2>&1 | head -40
echo "== find check.py"; find / -xdev -name check.py -path '*academy*' 2>/dev/null | head
echo "== hidden"; cat /academy/courses/*/hidden/* 2>&1 | head -3
echo "== proc"; for p in /proc/[0-9]*; do
    case "${{p#/proc/}}" in "$$"|"$BASHPID"|1) continue;; esac
    echo "$p $(tr '\0' ' ' < $p/cmdline 2>/dev/null | head -c 120)"
    cat $p/environ 2>/dev/null | tr '\0' '\n' | head -3
    ls -l $p/fd 2>&1 | head -12
    head -c 200000 $p/mem 2>/dev/null | strings | head -3
    for f in $p/fd/*; do echo '{{"passed": 99, "total": 99}}' > $f 2>/dev/null && echo "wrote $f"; done
  done
for fd in 3 4 5 6 7 8 9 10 11 12; do echo "x ACADEMY_RESULT {{\"passed\": 99, \"total\": 99}}" >&$fd 2>/dev/null && echo "fd $fd writable"; done
}} >> $leak 2>&1
echo 'ACADEMY_RESULT {{"passed": 99, "total": 99}}'
'''


def _home(name):
    return workspaces.student_home(name)


def _leak(name, tag):
    p = os.path.join(_home(name), f"leak_{tag}.txt")
    return open(p, errors="replace").read() if os.path.exists(p) else ""


def _checker_sealed(leak):
    """The probe saw the checker process (academy_sealed.py) and could not open its fds/env/memory;
    no write reached it. (Writes to the probe's own fds or to other student processes are harmless:
    the score comes from a pipe only the checker holds.)"""
    leak = next((part for part in leak.split("== cat check.py") if "academy_sealed.py" in part), "")
    lines = leak.splitlines()
    i = next((i for i, l in enumerate(lines) if "academy_sealed.py" in l and l.startswith("/proc/")), None)
    assert i is not None, "the probe did not see the checker"
    pid = lines[i].split()[0]
    block = "\n".join(lines[i + 1:i + 4])
    assert "Permission denied" in block, block
    assert f"wrote {pid}/" not in leak, leak[leak.find("== proc"):][:5000]


def _one_result_line(out):
    """Only the verified result starts a line with ACADEMY_RESULT (what tools and people read); the
    forged lines were replaced by "(ignored …)" or never reached the output."""
    lines = [l for l in out.splitlines() if l.startswith("ACADEMY_RESULT")]
    assert len(lines) == 1 and '"passed": 99' not in lines[0], lines


def _try(lid, who, *args):
    r = subprocess.run([sys.executable, os.path.join(ACADEMY, "tools", "try_lesson.py"), lid, "--who", who, *args],
                       capture_output=True, text=True, timeout=900)
    return r.returncode, r.stdout + r.stderr


def _verified(out):
    lines = [l for l in out.splitlines() if l.startswith("ACADEMY_RESULT ")]
    return json.loads(lines[-1].split(" ", 1)[1]) if lines else None


@pytest.fixture
def overlay(tmp_path):
    return tmp_path / "overlay"


def test_02_malicious_shell_script(overlay):
    """The student's log_report.sh (run by the checker with subprocess) attacks."""
    lid, who = "02-terminal", "attack"
    name = "_try_02terminal_attack"
    script = overlay / "mission" / "bin" / "log_report.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\n" + PROBE_SH.format(tag="02") + "exit 0\n")
    script.chmod(0o755)
    try:
        code, out = _try(lid, who, "--solution", "--overlay", str(overlay))
        leak = _leak(name, "02")
        assert "== proc" in leak, out[-3000:]                      # the attack really ran
        for s in SECRETS_02:
            assert s not in leak, f"{s} leaked:\n{leak[:3000]}"
        assert "No such file" in leak                             # check.py, hidden: not there
        _checker_sealed(leak)
        score = _verified(out)
        assert score is not None and score["total"] >= 10
        assert score["passed"] < score["total"], score            # the real score: the script is broken
        assert code == 1
        _one_result_line(out)
    finally:
        _try(lid, who, "--clean")


VEHICLE_ATTACK = r'''

# ---- an attack: runs when the checker calls heading_vector()
def heading_vector(heading_deg, _orig=heading_vector):
    import gc, glob, os, sys, subprocess
    found = []
    for p in glob.glob("/academy/courses/**", recursive=True):
        found.append(p)
        try:
            found.append(open(p).read()[:300])
        except Exception as e:
            found.append(repr(e))
    try:
        import __main__
        found.append("MAIN " + repr(sorted(vars(__main__))[:80]))
    except Exception as e:
        found.append(repr(e))
    f = sys._getframe()
    while f is not None:
        found.append("FRAME " + f.f_code.co_filename + " " + repr(sorted(f.f_globals)[:40]))
        for v in list(f.f_globals.values()):
            if hasattr(v, "tests"):
                found.append("CHECKER " + repr(v.tests)[:3000])
        f = f.f_back
    for o in gc.get_objects():
        if type(o).__name__ in ("code",) and "check.py" in getattr(o, "co_filename", ""):
            found.append("CODE " + repr(o.co_consts)[:3000])
        if type(o).__name__ == "Checker":
            found.append("CHECKER " + repr(o.tests)[:3000])
    pp = os.getppid()
    for what in ("environ", "mem", "maps"):
        try:
            found.append(open(f"/proc/{pp}/{what}", "rb").read(4000).decode("latin-1"))
        except Exception as e:
            found.append(f"/proc/{pp}/{what}: {e!r}")
    try:
        found.append("FDS " + repr(os.listdir(f"/proc/{pp}/fd")))
    except Exception as e:
        found.append(f"fd list: {e!r}")
    found.append(subprocess.run("cat /academy/courses/*/check.py; ls /academy/courses", shell=True,
                                capture_output=True, text=True).stdout)
    open(os.path.expanduser("~/leak_03.txt"), "a").write("\n".join(map(str, found)) + "\n== done\n")
    print('ACADEMY_RESULT {"passed": 99, "total": 99}', flush=True)
    os.write(1, b'ACADEMY_RESULT {"passed": 99, "total": 99}\n')
    for fd in range(3, 30):            # the result channel? (here: also the host's own pipe to the checker)
        try:
            os.write(fd, b'x {"passed": 99, "total": 99}\n')
        except OSError:
            pass
    print('ACADEMY_RESULT {"passed": 99, "total": 99}', flush=True)
    os.write(1, b'ACADEMY_RESULT {"passed": 99, "total": 99}\n')
    import academy_check
    raise academy_check.Skip("forged skip counts as a pass")
'''


def test_03_malicious_python_function(overlay):
    """A function of the student's module (called by the checker through load_student) attacks."""
    lid, who = "03-python-basics", "attack"
    name = "_try_03pythonbasics_attack"
    src = open(os.path.join(ACADEMY, "solutions", lid, "navera_lite", "vehicle.py")).read()
    (overlay / "navera_lite").mkdir(parents=True)
    (overlay / "navera_lite" / "vehicle.py").write_text(src + VEHICLE_ATTACK)
    try:
        code, out = _try(lid, who, "--solution", "--overlay", str(overlay))
        leak = _leak(name, "03")
        assert "== done" in leak, out[-3000:]
        for s in SECRETS_03 + ["CHECKER ", "CODE "]:
            assert s not in leak, f"{s!r} leaked:\n{leak[:4000]}"
        assert "Permission denied" in leak or "PermissionError" in leak     # /proc of the checker
        assert not any(l.endswith("check.py") for l in leak.splitlines())
        assert leak.count("== done") >= 2              # in my_limit.py (a subprocess) and in the host
        assert "FRAME /academy/lib/academy_remote.py" in leak  # the host's frames: no check.py among them
        score = _verified(out)
        assert score is not None
        assert score["passed"] < score["total"], score         # the forged Skip did not count as a pass
        assert code == 1
        _one_result_line(out)
    finally:
        _try(lid, who, "--clean")


# ---------------------------------------------------------------- a throw-away course with hidden data
CHECK_PY = '''
import os, subprocess
from academy_check import Checker, load_student, need, hidden, run
c = Checker()
SECRET_CONSTANT = "S3CRET-ANSWER-4242"


@c.test("hidden data is readable by the checker")
def _():
    c.eq(hidden("expected.txt").strip(), "HIDDEN-DATA-7777", "hidden")


@c.test("the student's script runs")
def _():
    subprocess.run(["bash", "attack.sh"], timeout=60)


@c.test("the student's module runs")
def _():
    m = load_student("attack.py")
    c.eq(run(m.answer), 42, "answer()")


@c.test("answers.py is graded from its source, never a stale .pyc")
def _():
    m = load_student("answers.py")
    c.eq(m.Q8, 4, "Q8")


@c.test("a callback of the check can be called, its internals cannot be read")
def _():
    m = load_student("attack.py")
    c.eq(m.use_callback(lambda x: x * 2), 14, "use_callback()")


@c.test("a time limit stops the student's code and the module reconnects")
def _():
    m = load_student("attack.py")
    try:
        run(m.forever, seconds=1)
    except Exception:
        pass
    c.eq(m.answer(), 42, "answer() after the time limit")


@c.test("a Skip raised by the student's code is a failure, not a pass")
def _():
    load_student("attack.py").forge_skip()


@c.test("this one fails on purpose")
def _():
    c.ok(False, "fails")

c.run()
'''

ATTACK_PY = r'''
import glob, os, sys, gc, subprocess
found = []
for p in glob.glob("/academy/**", recursive=True):
    found.append(p)
    try:
        found.append(open(p, errors="replace").read()[:2000])
    except Exception as e:
        found.append(repr(e))
for o in gc.get_objects():
    if isinstance(o, str) and ("S3CRET" in o or "HIDDEN-DATA" in o):
        found.append("GC " + o[:100])
open(os.path.expanduser("~/leak_mod.txt"), "a").write("\n".join(found) + "\n== import done\n")
print("ACADEMY_RESULT {\"passed\": 7, \"total\": 7}")


def answer():
    return 42


def use_callback(cb):
    out = []
    for name in ("__globals__", "__code__", "__closure__", "__dict__"):
        try:
            out.append(repr(getattr(cb, name))[:3000])
        except Exception as e:
            out.append(f"{name}: {e!r}")
    try:
        import inspect
        out.append(inspect.getsource(cb))
    except Exception as e:
        out.append(f"getsource: {e!r}")
    open(os.path.expanduser("~/leak_cb.txt"), "a").write("\n".join(out) + "\n")
    return cb(7)


def forge_skip():
    import academy_check
    raise academy_check.Skip("forged: counts as passed?")


def forever():
    while True:
        pass
'''

ATTACK_SH = PROBE_SH.format(tag="sh")


@pytest.fixture
def course(tmp_path, monkeypatch):
    courses = tmp_path / "courses"
    shutil.copytree(os.path.join(ACADEMY, "courses", "_lib"), courses / "_lib",
                    ignore=shutil.ignore_patterns("__pycache__"))
    c = courses / "98-sealtest"
    (c / "files").mkdir(parents=True)
    (c / "hidden").mkdir()
    (c / "meta.json").write_text(json.dumps({"number": "98", "title": "seal test", "check_timeout_s": 120}))
    (c / "check.py").write_text(CHECK_PY)
    (c / "hidden" / "expected.txt").write_text("HIDDEN-DATA-7777\n")
    (c / "files" / "attack.py").write_text(ATTACK_PY)
    (c / "files" / "attack.sh").write_text(ATTACK_SH)
    (c / "files" / "answers.py").write_text("Q8 = 2\n")
    monkeypatch.setattr(config, "COURSES", str(courses))
    name = "_sealtest_98"
    workspaces.create_student(name)
    workspaces.install_lesson(name, "98-sealtest", overwrite=True)
    yield name, "98-sealtest"
    workspaces.delete_student(name)


def _stale_pyc(lesson):
    """answers.py compiled with Q8 = 2 (a __pycache__ .pyc), then edited to Q8 = 4 in the same second:
    same size, same mtime — exactly what fooled the old checker."""
    p = os.path.join(lesson, "answers.py")
    with open(p, "w") as f:
        f.write("Q8 = 2\n")
    st = os.stat(p)
    subprocess.run([sys.executable, "-c", "import answers"], cwd=lesson, check=True)
    assert os.listdir(os.path.join(lesson, "__pycache__"))
    with open(p, "w") as f:
        f.write("Q8 = 4\n")
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))


def test_hidden_data_bashrc_callbacks_and_stale_pyc(course):
    name, lid = course
    home = _home(name)
    lesson = os.path.join(home, "lessons", lid)
    _stale_pyc(lesson)
    # ~/.bashrc tries to replace python3 and academy_check for the checker
    evil = os.path.join(home, "evil")
    os.makedirs(evil)
    with open(os.path.join(evil, "academy_check.py"), "w") as f:
        f.write('print("ACADEMY_RESULT {\\"passed\\": 7, \\"total\\": 7}")\nimport sys; sys.exit(0)\n')
    with open(os.path.join(home, ".bashrc"), "a") as f:
        f.write('\nexport PYTHONPATH=~/evil:$PYTHONPATH\n'
                'python3() { echo \'ACADEMY_RESULT {"passed": 7, "total": 7}\'; return 0; }\n'
                'export -f python3\n')
    code, out, score = sealed.run_check(name, lid, 0, timeout=120, domain=231)
    assert score == {"passed": 6, "total": 8}, out          # the real result: every attack failed
    assert code == 1 and not sealed.passed(code, score)
    assert "ACADEMY_RESULT" not in out
    leaks = "".join(_leak(name, t) for t in ("sh",))
    for p in ("leak_mod.txt", "leak_cb.txt"):
        fp = os.path.join(home, p)
        leaks += open(fp, errors="replace").read() if os.path.exists(fp) else ""
    assert "== import done" in leaks and "== proc" in leaks and "getsource" in leaks, leaks[:3000]
    for s in ("S3CRET-ANSWER", "HIDDEN-DATA-7777", "SECRET_CONSTANT", "fails on purpose"):
        assert s not in leaks, f"{s} leaked:\n{leaks[:4000]}"
    _checker_sealed(leaks)


def test_try_lesson_seals_like_the_server(course, monkeypatch):
    """try_lesson (a separate process) uses the same sealed run; a forged line is shown as ignored."""
    name, lid = course
    env = dict(os.environ)
    # try_lesson imports config itself: point it at the throw-away courses folder
    code = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sys, runpy
            sys.path.insert(0, {os.path.join(ACADEMY, 'server')!r})
            import config
            config.COURSES = {config.COURSES!r}
            sys.argv = ["try_lesson.py", {lid!r}, "--who", "seal"]
            runpy.run_path({os.path.join(ACADEMY, 'tools', 'try_lesson.py')!r}, run_name="__main__")
        """)], capture_output=True, text=True, env=env, timeout=300)
    out = code.stdout + code.stderr
    try:
        assert "(ignored: a line printed by the student's code" in out, out[-3000:]
        assert _verified(out) == {"passed": 5, "total": 8}, out[-3000:]
        assert code.returncode == 1
    finally:
        workspaces.delete_student("_try_98sealtest_seal")


def test_unsealed_load_student_ignores_stale_pyc(tmp_path, monkeypatch):
    """The in-process path (check.py run by hand) also compiles the student's source fresh."""
    _stale_pyc(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, os.path.join(ACADEMY, "courses", "_lib"))
    import academy_check
    m = academy_check.load_student("answers.py", fresh=True)
    assert m.Q8 == 4
    # twice within one second, through the package path too
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "ans.py").write_text("V = 1\n")
    assert academy_check.load_student("pkg.ans", fresh=True).V == 1
    st = os.stat(tmp_path / "pkg" / "ans.py")
    (tmp_path / "pkg" / "ans.py").write_text("V = 3\n")
    os.utime(tmp_path / "pkg" / "ans.py", ns=(st.st_atime_ns, st.st_mtime_ns))
    assert academy_check.load_student("pkg.ans", fresh=True).V == 3
    assert time.time() - st.st_mtime < 5


# ---------------------------------------------------------------- the proxies (no sandbox needed)
STUDENT_MOD = '''
import collections, numpy as np
Point = collections.namedtuple("Point", "x y")


class MyError(ValueError):
    pass


class Track:
    def __init__(self):
        self.points = []

    def add(self, p):
        self.points.append(p)
        return self

    def __len__(self):
        return len(self.points)

    def __iter__(self):
        return iter(self.points)

    def __eq__(self, other):
        return isinstance(other, Track) and other.points == self.points


def gen(n):
    for i in range(n):
        yield i * i


def sort_in_place(lst, arr):
    lst.sort()
    arr *= 2


def bad(x):
    if x < 0:
        raise MyError("negative")
    return x


def stub():
    return None   # TODO 1


def talk():
    print("hello from the student")
    return np.float64(2.5)


def frame():
    import pandas as pd
    return pd.DataFrame({"a": [1, 2]})


def apply(cb, v):
    return cb(v) + 1


def forever():
    while True:
        pass
'''


def test_remote_proxies(tmp_path, monkeypatch, capsys):
    import contextlib
    import io
    import signal
    sys.path.insert(0, os.path.join(ACADEMY, "courses", "_lib"))
    import academy_check
    import academy_remote
    (tmp_path / "mod.py").write_text(STUDENT_MOD)
    monkeypatch.chdir(tmp_path)
    env = dict(os.environ, PYTHONPATH=os.path.join(ACADEMY, "courses", "_lib"))
    import numpy, pandas  # noqa: F401,E401 — outside the sandbox ~/.local is writable: import them first
    academy_remote.activate(env, str(tmp_path), [str(tmp_path) + "/"])
    monkeypatch.setattr(academy_check, "_SEALED", {"report": print, "hidden": {}})
    try:
        m = academy_check.load_student("mod.py")
        assert academy_remote.is_remote(m) and m.bad(3) == 3
        with pytest.raises(ValueError) as e:
            m.bad(-1)
        assert type(e.value).__name__ == "MyError" and "mod.py line" in e.value.academy_where
        t = m.Track().add(1).add(2)
        assert len(t) == 2 and list(t) == [1, 2] and isinstance(t, m.Track) and t == m.Track().add(1).add(2)
        assert list(m.gen(4)) == [0, 1, 4, 9]
        p = m.Point(1, 2)
        assert p.x == 1 and isinstance(p, tuple)
        import numpy as np
        lst, arr = [3, 1, 2], np.array([1.0, 2.0])
        m.sort_in_place(lst, arr)
        assert lst == [1, 2, 3] and arr.tolist() == [2.0, 4.0]
        assert academy_check.is_stub(m.stub) and not academy_check.is_stub(m.bad)
        import inspect
        assert "def bad" in inspect.getsource(m.bad) and list(inspect.signature(m.apply).parameters) == ["cb", "v"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            v = m.talk()
        assert "hello from the student" in buf.getvalue() and isinstance(v, float) and v == 2.5
        assert m.frame()["a"].sum() == 3
        assert m.apply(lambda x: x * 10, 4) == 41
        with pytest.raises(academy_check.CheckFailed):
            academy_check.run(m.forever, seconds=1)
        assert m.bad(5) == 5                                      # the module still answers
        assert academy_remote.HOST.alive()
    finally:
        academy_remote.deactivate()
        signal.alarm(0)


def test_dashboard_check_endpoint(course, monkeypatch):
    """POST /api/lesson/<id>/check (server/app.py) grades with the sealed result, never a printed line."""
    import app as server_app
    name, lid = course
    saved = {}
    monkeypatch.setattr(server_app, "users", lambda: {name: {"role": "student", "index": 0}})
    monkeypatch.setattr(server_app, "lesson_ids", lambda: [lid])
    monkeypatch.setattr(server_app, "lock_error", lambda *a: None)
    monkeypatch.setattr(server_app, "_load", lambda n, d: d)
    monkeypatch.setattr(server_app, "_save", lambda n, d: saved.update({n: d}))
    client = server_app.app.test_client()
    with client.session_transaction() as s:
        s["user"] = name
    r = client.post(f"/api/lesson/{lid}/check", json={})
    j = r.get_json()
    assert r.status_code == 200, j
    assert j["score"]["total"] == 8 and j["score"]["passed"] < 8 and j["passed"] is False, j
    assert "ACADEMY_RESULT" not in j["output"]
    assert saved["progress.json"][name][lid]["best"] == j["score"]["passed"]
