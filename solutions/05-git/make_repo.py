#!/usr/bin/env python3
"""make_repo.py — TEACHER ONLY: build the NAVERA Lite history repository of mission 05.

    python3 solutions/05-git/make_repo.py                 # writes datasets/05-git/navera-lite-history.tar.gz
    python3 solutions/05-git/make_repo.py --out DIR       # builds the repository in an empty folder (tests)
    python3 solutions/05-git/make_repo.py --print-key     # also prints the hashes of the answer key

It lives in solutions/ because it reveals the answers: students see datasets/ (read only, as
/data/academy/05-git/) and extract the archive in lab Step 0:
    tar -xzf /data/academy/05-git/navera-lite-history.tar.gz

What it makes: a git repository with the invented history of an early NAVERA Lite (the course's own
teaching stack, not NAVERA code): 40 commits on `main` by five invented engineers between March and
September 2026, an annotated tag `v0.1`, and one review branch `kenji/fewer-refusals`.
Two things are planted in it for the lab: a commit on `main` that breaks the jump gate of mission 01
(the lab finds it with git bisect), and a broken commit that cannot even be imported (bisect must skip
it). The review branch mixes safe and unsafe changes (the lab reviews it hunk by hunk).

Deterministic: fixed authors, dates, contents and settings; the builder's own git settings are ignored
(GIT_CONFIG_GLOBAL=/dev/null), so the hashes never change (check.py and TEACHER.md rely on them). The
archive holds the repository without reflogs (students start with an empty journal).
"""
import argparse
import os
import subprocess
import sys

# ------------------------------------------------------------------ the people (invented)
PEOPLE = {
    "lena": ("Lena Hoffmann", "lena@lite.example", "+0100"),
    "amara": ("Amara Diallo", "amara@lite.example", "+0000"),
    "diego": ("Diego Ramírez", "diego@lite.example", "-0500"),
    "priya": ("Priya Nair", "priya@lite.example", "+0530"),
    "kenji": ("Kenji Sato", "kenji@lite.example", "+0900"),
}

# ------------------------------------------------------------------ the files, version 1
README = """# NAVERA Lite — history

NAVERA Lite is the small navigation stack written for the NAVERA Academy course. This repository is
a teaching history for mission 05: the people, dates and commits are invented, and the code is the
course's own (it is not NAVERA code).
"""

GITIGNORE = """__pycache__/
*.pyc
.pytest_cache/
*.mbtiles
"""

GEO = '''"""navera_lite/geo.py — distances for NAVERA Lite. Course code (it is not NAVERA code)."""
import math


def flat_distance_m(p, q):
    """Distance in metres between two points given as (east_m, north_m)."""
    return math.hypot(q[0] - p[0], q[1] - p[1])
'''

GUARD = '''"""navera_lite/guard.py — the jump gate of mission 01. Course code (it is not NAVERA code)."""
from navera_lite.geo import flat_distance_m


def gate_ok(last_xy, new_xy, elapsed_s, v_max_mps, margin_m):
    """True if a fix at new_xy is reachable from the trusted fix last_xy (metres, east/north)."""
    return flat_distance_m(last_xy, new_xy) <= v_max_mps * elapsed_s + margin_m
'''

JUMPGATE = '''

class JumpGate:
    """Remembers the last trusted fix and refuses the fixes the vehicle could not have reached."""

    def __init__(self, v_max_mps=100.0, margin_m=50.0):
        self.v_max_mps = v_max_mps
        self.margin_m = margin_m
        self.last_xy = None          # the last trusted fix (m)
        self.last_t_s = None         # its time (s)

    def check(self, t_s, xy):
        """True if the fix at time t_s is accepted; an accepted fix becomes the trusted one."""
        if self.last_xy is None:
            self.last_xy, self.last_t_s = xy, t_s
            return True
        elapsed_s = t_s - self.last_t_s
        ok = gate_ok(self.last_xy, xy, elapsed_s, self.v_max_mps, self.margin_m)
        if ok:
            self.last_xy, self.last_t_s = xy, t_s
        return ok
'''

TEST_GEO = '''from navera_lite.geo import flat_distance_m


def test_flat_distance_3_4_5():
    assert flat_distance_m((0, 0), (3, 4)) == 5.0
'''

TEST_GUARD = '''from navera_lite.guard import gate_ok


def test_gate_on_the_limit_is_accepted():
    assert gate_ok((0, 0), (150, 0), 1.0, 100.0, 50.0)


def test_gate_just_beyond_the_limit_is_refused():
    assert not gate_ok((0, 0), (151, 0), 1.0, 100.0, 50.0)
'''

HAVERSINE = '''

def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres on a sphere (latitudes and longitudes in degrees)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(h))
'''

YAML = """# navera_lite.yaml — the settings of NAVERA Lite (ROS 2 params-file format)
/**:
  ros__parameters:
    max_speed_mps: 100.0        # v_max of the jump gate (m/s)
    gps_jump_margin_m: 50.0     # margin of the jump gate (m)
    gps_timeout_s: 3.0          # a GPS fix older than this is not fresh (s)
"""

SETTINGS = '''"""navera_lite/settings.py — read navera_lite.yaml. Course code (it is not NAVERA code)."""
DEFAULTS = {"max_speed_mps": 100.0, "gps_jump_margin_m": 50.0, "gps_timeout_s": 3.0}


def load_settings(path="navera_lite.yaml"):
    """DEFAULTS, updated by the `key: value` lines of the file (values as floats)."""
    out = dict(DEFAULTS)
    with open(path) as f:
        for line in f:
            line = line.split("#")[0].strip()
            key, _, value = line.partition(":")
            if value.strip():
                out[key.strip()] = float(value)
    return out
'''

TEST_SETTINGS = '''from navera_lite.settings import DEFAULTS, load_settings


def test_file_values_override_defaults(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("/**:\\n  ros__parameters:\\n    gps_jump_margin_m: 20.0   # tight\\n")
    s = load_settings(str(p))
    assert s["gps_jump_margin_m"] == 20.0
    assert s["max_speed_mps"] == DEFAULTS["max_speed_mps"]
'''

COUNT_REFUSED = '''

def count_refused(fixes, dt_s, v_max_mps=100.0, margin_m=50.0):
    """How many fixes the gate refuses; fixes[0] is trusted, then one fix every dt_s seconds."""
    refused, last, elapsed = 0, fixes[0], 0.0
    for fix in fixes[1:]:
        elapsed += dt_s
        if gate_ok(last, fix, elapsed, v_max_mps, margin_m):
            last, elapsed = fix, 0.0
        else:
            refused += 1
    return refused
'''

COUNT_REFUSED_V2 = '''

def count_refused(fixes, dt_s, v_max_mps=100.0, margin_m=50.0):
    """How many fixes the gate refuses; fixes[0] is trusted, then one fix every dt_s seconds."""
    gate = JumpGate(v_max_mps, margin_m)
    gate.check(0.0, fixes[0])
    refused = 0
    for i in range(1, len(fixes)):
        if not gate.check(i * dt_s, fixes[i]):
            refused += 1
    return refused
'''

CHANGELOG = """# Changelog

## v0.2 (in progress)
- settings come from navera_lite.yaml
- count_refused() for replay tests

## v0.1 (2026-03-27)
- flat_distance_m, haversine_m
- the jump gate: gate_ok, JumpGate
"""


# ------------------------------------------------------------------ the history
def history():
    """[(person, date, subject, body, {path: new text | None}, tag)] — main, oldest first, then the
    review branch. A change is either a whole new text or an edit (old, new) applied once."""
    E = "edit"
    return [
        ("lena", "2026-03-02T09:14:00", "chore: start the NAVERA Lite history", "",
         {"README.md": README, ".gitignore": GITIGNORE, "navera_lite/__init__.py":
          '"""NAVERA Lite (history of mission 05). Course code, not NAVERA code."""\n'}),
        ("lena", "2026-03-03T10:02:00", "feat(geo): flat_distance_m between two east/north points", "",
         {"navera_lite/geo.py": GEO}),
        ("lena", "2026-03-03T16:40:00", "test(geo): flat_distance_m on a 3-4-5 triangle", "",
         {"tests/test_geo.py": TEST_GEO}),
        ("amara", "2026-03-06T08:30:00", "feat(guard): gate_ok, the jump gate of mission 01",
         "A fix is refused when it is farther from the last trusted fix than the vehicle\n"
         "can fly in the elapsed time, plus a margin for GPS noise.",
         {"navera_lite/guard.py": GUARD}),
        ("amara", "2026-03-06T11:05:00", "test(guard): gate_ok on the limit and just beyond", "",
         {"tests/test_guard.py": TEST_GUARD}),
        ("amara", "2026-03-10T09:45:00", "feat(guard): JumpGate keeps the last trusted fix",
         "Refused fixes never become trusted, so the time since the last trusted fix grows\n"
         "and the gate widens (lesson 1, section 5).",
         {"navera_lite/guard.py": (E, None, JUMPGATE)}),
        ("amara", "2026-03-10T14:20:00", "test(guard): JumpGate refuses a 500 m jump", "",
         {"tests/test_guard.py": (E, "from navera_lite.guard import gate_ok\n",
                                  "from navera_lite.guard import JumpGate, gate_ok\n"),
          "tests/test_guard.py+": (E, None, '''

def test_jump_gate_refuses_a_500_m_jump():
    gate = JumpGate(100.0, 50.0)
    assert gate.check(0.0, (0, 0))
    assert not gate.check(1.0, (500, 0))
''')}),
        ("diego", "2026-03-16T19:10:00", "feat(geo): haversine_m on a 6371 km sphere", "",
         {"navera_lite/geo.py": (E, None, HAVERSINE)}),
        ("diego", "2026-03-17T08:55:00", "test(geo): London to Paris is 343.6 km", "",
         {"tests/test_geo.py": (E, "from navera_lite.geo import flat_distance_m\n",
                                "from navera_lite.geo import flat_distance_m, haversine_m\n"),
          "tests/test_geo.py+": (E, None, '''

def test_london_paris():
    assert abs(haversine_m(51.5074, -0.1278, 48.8566, 2.3522) - 343556) < 1
''')}),
        ("lena", "2026-03-27T17:30:00", "docs(readme): what the gate does and how to run the tests", "",
         {"README.md": (E, None, """
## What it does

Each GPS fix you recieve is checked by the jump gate (`navera_lite/guard.py`): a fix farther from
the last trusted fix than the vehicle can fly in the elapsed time, plus a margin, is refused.

## Tests

    python3 -m pytest -q tests
""")}, ("v0.1", "v0.1: first release, the jump gate and its tests")),
        ("priya", "2026-04-02T10:10:00", "feat(settings): navera_lite.yaml with the gate values", "",
         {"navera_lite.yaml": YAML}),
        ("priya", "2026-04-02T15:25:00", "feat(settings): load_settings reads navera_lite.yaml", "",
         {"navera_lite/settings.py": SETTINGS}),
        ("priya", "2026-04-03T09:00:00", "test(settings): the file values override DEFAULTS", "",
         {"tests/test_settings.py": TEST_SETTINGS}),
        ("amara", "2026-04-08T11:40:00", "feat(guard): count_refused over a list of fixes",
         "For replay tests: how many fixes of a recorded flight the gate refuses.",
         {"navera_lite/guard.py": (E, None, COUNT_REFUSED)}),
        ("amara", "2026-04-08T16:15:00", "test(guard): count_refused with no jump refuses nothing", "",
         {"tests/test_guard.py": (E, "from navera_lite.guard import JumpGate, gate_ok\n",
                                  "from navera_lite.guard import JumpGate, count_refused, gate_ok\n"),
          "tests/test_guard.py+": (E, None, '''

def test_count_refused_without_a_jump():
    assert count_refused([(0, 0), (10, 0), (20, 0), (30, 0)], 1.0) == 0
''')}),
        ("diego", "2026-04-14T20:05:00", "feat(geo): EARTH_RADIUS_M and metres_per_degree_lat", "",
         {"navera_lite/geo.py": (E, "import math\n", "import math\n\nEARTH_RADIUS_M = 6371000.0          # mean radius of the sphere (m)\n"),
          "navera_lite/geo.py+": (E, None, '''

def metres_per_degree_lat():
    """Length of one degree of latitude on the sphere (m)."""
    return EARTH_RADIUS_M * math.pi / 180.0
''')}),
        ("lena", "2026-04-20T09:30:00", "docs(readme): the settings file", "",
         {"README.md": (E, "## Tests\n", """## Settings

The gate's values are in `navera_lite.yaml` (ROS 2 params-file format). Change them only with a
measurement that shows why.

## Tests
""")}),
        ("priya", "2026-04-24T12:00:00", "fix(settings): a missing file falls back to DEFAULTS", "",
         {"navera_lite/settings.py": (E, '''    out = dict(DEFAULTS)
    with open(path) as f:
        for line in f:
            line = line.split("#")[0].strip()
            key, _, value = line.partition(":")
            if value.strip():
                out[key.strip()] = float(value)
    return out
''', '''    out = dict(DEFAULTS)
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return out
    for line in lines:
        line = line.split("#")[0].strip()
        key, _, value = line.partition(":")
        if value.strip():
            out[key.strip()] = float(value)
    return out
''')}),
        ("amara", "2026-04-29T10:20:00", "refactor(guard): count_refused uses JumpGate",
         "One gate implementation instead of two.",
         {"navera_lite/guard.py": (E, COUNT_REFUSED, COUNT_REFUSED_V2)}),
        ("kenji", "2026-05-06T18:45:00", "test(guard): read the gate values from navera_lite.yaml", "",
         {"tests/test_guard.py": (E, "from navera_lite.guard import JumpGate, count_refused, gate_ok\n",
                                  "from navera_lite.guard import JumpGate, count_refused, gate_ok\n"
                                  "from navera_lite.settings import load_settings\n"),
          "tests/test_guard.py+": (E, '''def test_jump_gate_refuses_a_500_m_jump():
    gate = JumpGate(100.0, 50.0)
''', '''def test_jump_gate_refuses_a_500_m_jump():
    s = load_settings()
    gate = JumpGate(s["max_speed_mps"], s["gps_jump_margin_m"])
''')}),
        ("lena", "2026-05-12T09:00:00", "docs: CHANGELOG for v0.2", "", {"CHANGELOG.md": CHANGELOG}),
        ("priya", "2026-05-19T11:30:00", "style(settings): shorter names in load_settings", "",
         {"navera_lite/settings.py": (E, '''    for line in lines:
        line = line.split("#")[0].strip()
        key, _, value = line.partition(":")
        if value.strip():
            out[key.strip()] = float(value)
''', '''    for raw in lines:
        text = raw.split("#")[0].strip()
        key, _, value = text.partition(":")
        if value.strip():
            out[key.strip()] = float(value)
''')}),
        ("kenji", "2026-05-25T08:15:00", "chore: ignore editor backup files", "",
         {".gitignore": (E, None, "*~\n*.swp\n")}),
        ("diego", "2026-06-01T21:00:00", "test(geo): haversine_m is symmetric", "",
         {"tests/test_geo.py+": (E, None, '''

def test_haversine_is_symmetric():
    a = haversine_m(1.2921, 103.8198, -33.9249, 18.4241)
    b = haversine_m(-33.9249, 18.4241, 1.2921, 103.8198)
    assert abs(a - b) < 1e-6
''')}),
        # the BROKEN commit: guard.py does not even import (a missing colon). Bisect must skip it.
        ("diego", "2026-06-05T23:40:00", "wip: guard status line", "",
         {"navera_lite/guard.py": (E, '''        if ok:
            self.last_xy, self.last_t_s = xy, t_s
        return ok
''', '''        if ok:
            self.last_xy, self.last_t_s = xy, t_s
        return ok

    def status(self):
        """One line for the operator."""
        if self.last_xy is None
            return "no trusted fix yet"
''')}),
        ("diego", "2026-06-06T10:20:00", "fix(guard): finish the status line", "",
         {"navera_lite/guard.py": (E, '''        if self.last_xy is None
            return "no trusted fix yet"
''', '''        if self.last_xy is None:
            return "no trusted fix yet"
        e, n = self.last_xy
        return f"trusted fix at E {e:.0f} m, N {n:.0f} m (t = {self.last_t_s:.1f} s)"
''')}),
        ("diego", "2026-06-08T09:10:00", "test(guard): status before and after the first fix", "",
         {"tests/test_guard.py+": (E, None, '''

def test_status_line():
    gate = JumpGate(100.0, 50.0)
    assert gate.status() == "no trusted fix yet"
    gate.check(2.0, (10.0, 20.0))
    assert "E 10 m" in gate.status()
''')}),
        ("diego", "2026-06-15T19:30:00", "feat(geo): metres_per_degree_lon", "",
         {"navera_lite/geo.py+": (E, None, '''

def metres_per_degree_lon(lat_deg):
    """Length of one degree of longitude at this latitude (m)."""
    return metres_per_degree_lat() * math.cos(math.radians(lat_deg))
''')}),
        ("diego", "2026-06-16T08:40:00", "test(geo): a degree of longitude at 60 N is half", "",
         {"tests/test_geo.py": (E, "from navera_lite.geo import flat_distance_m, haversine_m\n",
                                "from navera_lite.geo import flat_distance_m, haversine_m, metres_per_degree_lat, "
                                "metres_per_degree_lon\n"),
          "tests/test_geo.py+": (E, None, '''

def test_longitude_degree_at_60_north():
    assert abs(metres_per_degree_lon(60.0) - metres_per_degree_lat() / 2) < 1e-6
''')}),
        # the REGRESSION: elapsed is measured from the previous fix (accepted or not), so the gate never
        # widens after a refusal: after a real jump, GPS is locked out for ever.
        ("amara", "2026-06-23T14:05:00", "feat(guard): say how long GPS has been refused",
         "The operator display wants to show for how long GPS has been refused.",
         {"navera_lite/guard.py": (E, '''        self.last_t_s = None         # its time (s)
''', '''        self.last_t_s = None         # its time (s)
        self.prev_t_s = None         # time of the previous fix, accepted or not (s)
        self.refused_since_s = None  # time of the first refusal in a row (s)
'''),
          "navera_lite/guard.py+": (E, '''        if self.last_xy is None:
            self.last_xy, self.last_t_s = xy, t_s
            return True
        elapsed_s = t_s - self.last_t_s
        ok = gate_ok(self.last_xy, xy, elapsed_s, self.v_max_mps, self.margin_m)
        if ok:
            self.last_xy, self.last_t_s = xy, t_s
        return ok
''', '''        if self.last_xy is None:
            self.last_xy, self.last_t_s, self.prev_t_s = xy, t_s, t_s
            return True
        elapsed_s = t_s - self.prev_t_s
        self.prev_t_s = t_s
        ok = gate_ok(self.last_xy, xy, elapsed_s, self.v_max_mps, self.margin_m)
        if ok:
            self.last_xy, self.last_t_s = xy, t_s
            self.refused_since_s = None
        elif self.refused_since_s is None:
            self.refused_since_s = t_s
        return ok

    def refused_for_s(self, now_s):
        """Seconds since GPS was first refused (0.0 while it is accepted)."""
        return 0.0 if self.refused_since_s is None else now_s - self.refused_since_s
'''),
          "tests/test_guard.py+": (E, None, '''

def test_refused_for_s():
    gate = JumpGate(100.0, 50.0)
    gate.check(0.0, (0, 0))
    gate.check(1.0, (500, 0))
    gate.check(2.0, (500, 0))
    assert gate.refused_for_s(3.0) == 2.0
''')}),
        ("lena", "2026-06-24T09:15:00", "docs(changelog): refused_for_s and the status line", "",
         {"CHANGELOG.md": (E, "- count_refused() for replay tests\n",
                           "- count_refused() for replay tests\n- JumpGate.status() and refused_for_s() for the operator\n")}),
        ("priya", "2026-07-01T10:45:00", "feat(settings): check_settings refuses impossible values", "",
         {"navera_lite/settings.py+": (E, None, '''

def check_settings(s):
    """The broken rules of a settings dict, as sentences (an empty list when all is well)."""
    problems = []
    for key in ("max_speed_mps", "gps_jump_margin_m", "gps_timeout_s"):
        if s[key] <= 0:
            problems.append(f"{key} must be > 0, got {s[key]}")
    return problems
''')}),
        ("priya", "2026-07-01T16:00:00", "test(settings): check_settings on a negative margin", "",
         {"tests/test_settings.py": (E, "from navera_lite.settings import DEFAULTS, load_settings\n",
                                     "from navera_lite.settings import DEFAULTS, check_settings, load_settings\n"),
          "tests/test_settings.py+": (E, None, '''

def test_check_settings():
    assert check_settings(DEFAULTS) == []
    bad = dict(DEFAULTS, gps_jump_margin_m=-5.0)
    assert check_settings(bad) == ["gps_jump_margin_m must be > 0, got -5.0"]
''')}),
        ("lena", "2026-07-09T13:20:00", "docs(readme): where this history comes from", "",
         {"README.md": (E, "course's own (it is not NAVERA code).\n",
                        "course's own (it is not NAVERA code). Missions 06 onwards build the full stack.\n")}),
        ("kenji", "2026-07-21T07:50:00", "refactor(settings): one place for the file name", "",
         {"navera_lite/settings.py": (E, '''DEFAULTS = {"max_speed_mps": 100.0, "gps_jump_margin_m": 50.0, "gps_timeout_s": 3.0}


def load_settings(path="navera_lite.yaml"):
''', '''DEFAULTS = {"max_speed_mps": 100.0, "gps_jump_margin_m": 50.0, "gps_timeout_s": 3.0}
SETTINGS_FILE = "navera_lite.yaml"


def load_settings(path=SETTINGS_FILE):
''')}),
        ("amara", "2026-08-03T11:00:00", "docs(guard): why a refused fix never becomes trusted", "",
         {"navera_lite/guard.py": (E, '''"""navera_lite/guard.py — the jump gate of mission 01. Course code (it is not NAVERA code)."""
''', '''"""navera_lite/guard.py — the jump gate of mission 01. Course code (it is not NAVERA code).

A refused fix never becomes the trusted one: otherwise a spoofer would only need one refusal to
move the reference. The gate widens with the time since the last TRUSTED fix.
"""
''')}),
        ("lena", "2026-08-18T09:40:00", "docs(changelog): v0.2 candidate", "",
         {"CHANGELOG.md": (E, "## v0.2 (in progress)\n", "## v0.2 (candidate, 2026-08-18)\n")}),
        ("priya", "2026-09-02T15:10:00", "docs(readme): how to report a bug", "",
         {"README.md+": (E, None, """
## Reporting a bug

Say what you ran, what you expected, what you got, and the commit (`git log -1 --oneline`).
""")}),
        # ---- the review branch forks here (see REVIEW below); main goes on with two commits
        ("lena", "2026-09-10T10:00:00", "docs(readme): two people read every change", "",
         {"README.md+": (E, None, """
## Review rule

Every change is read by a second person before it enters `main`. Small commits, one concern each.
""")}),
        ("diego", "2026-09-14T18:25:00", "test(geo): one degree of latitude is about 111 km", "",
         {"tests/test_geo.py+": (E, None, '''

def test_degree_of_latitude():
    assert abs(metres_per_degree_lat() - 111195) < 1
''')}),
    ]


FORK_AFTER = 38          # kenji/fewer-refusals starts at main's commit 38
REVIEW_BRANCH = "kenji/fewer-refusals"
REVIEW = ("kenji", "2026-09-11T08:30:00", "fix: fewer false GPS refusals, tidy geo",
          "Pilots complain that after a GPS glitch the GPS is refused for ever.\n"
          "- give up a refused old fix after 10 s\n"
          "- larger jump margin\n"
          "- haversine_m uses EARTH_RADIUS_M\n"
          "- remove a flaky test\n"
          "- fix a typo",
          {"README.md": ("edit", "Each GPS fix you recieve", "Each GPS fix you receive"),
           "navera_lite.yaml": ("edit", "    gps_jump_margin_m: 50.0     # margin of the jump gate (m)\n",
                                "    gps_jump_margin_m: 500.0    # margin of the jump gate (m): fewer false refusals\n"),
           "navera_lite/geo.py": ("edit", "    return 2 * 6371000.0 * math.asin(math.sqrt(h))\n",
                                  "    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))\n"),
           "navera_lite/guard.py": ("edit", '''        elif self.refused_since_s is None:
            self.refused_since_s = t_s
        return ok
''', '''        elif self.refused_since_s is None:
            self.refused_since_s = t_s
        elif t_s - self.refused_since_s > 10.0:
            # refused for more than 10 s: the old fix must be wrong, trust the new one
            self.last_xy, self.last_t_s = xy, t_s
            self.refused_since_s = None
            ok = True
        return ok
'''),
           "tests/test_guard.py": ("edit", '''

def test_jump_gate_refuses_a_500_m_jump():
    s = load_settings()
    gate = JumpGate(s["max_speed_mps"], s["gps_jump_margin_m"])
    assert gate.check(0.0, (0, 0))
    assert not gate.check(1.0, (500, 0))
''', "")})

BROKEN_SUBJECT = "wip: guard status line"
BAD_SUBJECT = "feat(guard): say how long GPS has been refused"


# ------------------------------------------------------------------ building
def git(repo, *args, env=None, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, env=env)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout.strip()


def base_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", LC_ALL="C", TZ="UTC")
    return env


def apply_changes(repo, changes):
    for key, change in changes.items():
        path = key.rstrip("+")
        full = os.path.join(repo, path)
        if isinstance(change, tuple):
            _, old, new = change
            with open(full) as f:
                text = f.read()
            if old is None:                       # append
                text = text + new
            else:
                if text.count(old) != 1:
                    sys.exit(f"make_repo: edit of {path} does not match exactly once: {old[:60]!r}")
                text = text.replace(old, new)
        else:
            text = change
        os.makedirs(os.path.dirname(full) or repo, exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
        os.chmod(full, 0o644)
        git(repo, "add", path)


def commit(repo, person, date, subject, body, env0):
    name, email, tz = PEOPLE[person]
    stamp = f"{date} {tz}"
    env = dict(env0, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=stamp,
               GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=stamp)
    msg = subject + ("\n\n" + body if body else "")
    git(repo, "commit", "-q", "--no-verify", "-m", msg, env=env)
    return env


def build(out):
    if os.path.exists(out) and os.listdir(out):
        sys.exit(f"{out} already exists and is not empty.\n"
                 f"To start again from zero (your commits there are lost): rm -rf {out}   then run this again.")
    os.makedirs(out, exist_ok=True)
    env0 = base_env()
    git(out, "init", "-q", "-b", "main", env=env0)
    for k, v in (("core.autocrlf", "false"), ("core.filemode", "true"), ("commit.gpgsign", "false"),
                 ("tag.gpgsign", "false")):
        git(out, "config", k, v, env=env0)
    steps = history()
    for i, step in enumerate(steps, 1):
        person, date, subject, body, changes = step[:5]
        apply_changes(out, changes)
        env = commit(out, person, date, subject, body, env0)
        if len(step) > 5:
            tag, msg = step[5]
            git(out, "tag", "-a", tag, "-m", msg, env=env)
        if i == FORK_AFTER:
            git(out, "branch", REVIEW_BRANCH, env=env0)
    git(out, "switch", "-q", REVIEW_BRANCH, env=env0)
    person, date, subject, body, changes = REVIEW
    apply_changes(out, changes)
    commit(out, person, date, subject, body, env0)
    git(out, "switch", "-q", "main", env=env0)
    git(out, "gc", "-q", "--prune=now", env=env0)
    return out


def key(repo):
    """The facts of the answer key, computed from the repository itself."""
    env = base_env()
    def find(subject):
        return git(repo, "log", "--all", "--format=%H", "--fixed-strings", f"--grep={subject}", env=env).splitlines()[0]
    return {"main": git(repo, "rev-parse", "main", env=env),
            "v0.1": git(repo, "rev-parse", "v0.1^{commit}", env=env),
            "broken": find(BROKEN_SUBJECT), "bad": find(BAD_SUBJECT),
            "review": git(repo, "rev-parse", REVIEW_BRANCH, env=env),
            "suspects": int(git(repo, "rev-list", "--count", "v0.1..main", env=env)),
            "main_commits": int(git(repo, "rev-list", "--count", "main", env=env))}


ACADEMY = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ARCHIVE = os.path.join(ACADEMY, "datasets", "05-git", "navera-lite-history.tar.gz")


def pack(repo, archive):
    """The repository as a deterministic .tar.gz with one top folder navera-lite-history/ (no reflogs)."""
    import gzip
    import shutil
    import tarfile
    for extra in ("logs", "hooks", "COMMIT_EDITMSG", "ORIG_HEAD", "description", "info"):
        p = os.path.join(repo, ".git", extra)
        shutil.rmtree(p) if os.path.isdir(p) else (os.path.exists(p) and os.remove(p))
    os.makedirs(os.path.dirname(archive), exist_ok=True)
    entries = []
    for dp, dns, fns in os.walk(repo):
        dns.sort()
        for n in dns + sorted(fns):
            entries.append(os.path.join(dp, n))
    with open(archive, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(entries):
            info = tar.gettarinfo(path, arcname=os.path.join("navera-lite-history", os.path.relpath(path, repo)))
            info.mtime, info.uid, info.gid, info.uname, info.gname = 1767225600, 0, 0, "", ""
            info.mode = 0o755 if info.isdir() else 0o644
            if info.isfile():
                with open(path, "rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)


def main():
    import tempfile
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", help="build the repository in this empty folder instead of writing the archive")
    ap.add_argument("--print-key", action="store_true", help="print the hashes of the answer key")
    a = ap.parse_args()
    if a.out:
        out = os.path.abspath(a.out)
        build(out)
        k = key(out)
        print(f"Made {out}: {k['main_commits']} commits on main, tag v0.1, branch {REVIEW_BRANCH}.")
    else:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "navera-lite-history")
            build(out)
            k = key(out)
            pack(out, ARCHIVE)
        print(f"Wrote {os.path.relpath(ARCHIVE, ACADEMY)} ({os.path.getsize(ARCHIVE) // 1024} kB): "
              f"{k['main_commits']} commits on main, tag v0.1, branch {REVIEW_BRANCH}.")
    if a.print_key:
        for name, v in k.items():
            print(f"  {name:13s} {v}")


if __name__ == "__main__":
    main()
