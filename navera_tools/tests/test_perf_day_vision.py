"""NAV-PERF-02 regression: day vision accuracy benchmark, offline on data already on disk.

The product day matcher (matcher:=auto: DISK + LightGlue, SIFT fallback, the node's default gates)
on (1) REAL Insta360 frames recorded on the screen bench (2026-10-20, four recordings: clear 20 / 60 m/s,
heavy rain, flare; 20 frames each) and (2) campaign 4's screen mission replayed with the camera replaced
by the other-date terrain imagery it filmed (5 terrains, one 135 s racetrack lap after the GPS loss,
VisionNavigator + FrameOdometry between fixes). See navera_tools/bench/day_perf.py.

Two kinds of bounds:
  * requirement bounds — campaign 4's measured numbers (VALIDATION_STATUS.md, screen bench table):
    land median <= 5.5 m, p95 <= 20 m, coast median <= 7.3 m and availability >= 50 %, no wrong fix;
  * regression bounds — this benchmark's own baseline (2026-10-22, commit of this file) with about
    2x margin, so that a matcher / navigator regression fails here long before the requirement does.
Baseline 2026-10-22 (two runs; the GPU matcher is not bit-reproducible): recorded frames all accepted,
median 2.8-3.9 m, p95 7-13 m, max 13.6 m, 0 wrong; offline mission: land median 0.9-2.0 m, p95 1.6-2.7 m
(farms once 10.5 m: 4 frames carried), coast median 3.2-3.5 m, p95 4.8-6.2 m, availability 100 %, 0 wrong.
The offline mission is far better than campaign 4 on the same terrains: what it lacks is the screen and
camera chain (moire, exposure on dark sea, blur), which the recorded frames carry.
Run: NAVERA_PERF=1 flock /tmp/claude-1000/navera_gpu.lock \
    python3 -m pytest -q navera_tools/tests/test_perf_day_vision.py
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "navera_tools", "bench"), ROOT, os.path.join(ROOT, "day_pkg"),
          os.path.join(ROOT, "navera_common"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import day_perf  # noqa: E402
from _perf_common import require_perf  # noqa: E402

pytestmark = pytest.mark.perf
LAND = ("city", "olives", "hills", "farms")


def _pooled(res, keys):
    e = sorted(x for k in keys for x in res[k]["errs"])
    return dict(n=len(e), median=day_perf.pct(e, 0.5), p95=day_perf.pct(e, 0.95), max=e[-1] if e else None)


@pytest.fixture(scope="module")
def recorded():
    require_perf([os.path.join(day_perf.BENCH_DIR, "area")] + day_perf.recorded_paths())
    res = day_perf.run_recorded(n_per_run=20)
    print("\nrecorded:", {k: {x: y for x, y in v.items() if x != "errs"} for k, v in res.items()})
    return res


@pytest.fixture(scope="module")
def mission():
    paths = [os.path.join(day_perf.BENCH_DIR, "areas.json")]
    for t in day_perf.TERRAINS:
        paths += [os.path.join(day_perf.BENCH_DIR, "wb2022" if t == "city" else f"terrain_{t}"),
                  os.path.join(day_perf.BENCH_DIR, "area_k" if t == "city" else f"map_{t}", "images")]
    require_perf(paths)
    res = day_perf.run_missions()
    print("\nmission:", {k: {x: y for x, y in v.items() if x != "errs"} for k, v in res.items()})
    return res


def test_perf_day_recorded_camera_frames_located(recorded):
    """NAV-PERF-02 real camera, screen bench recordings: >= 90 % of frames located per recording,
    no wrong fix (> 50 m)."""
    for run, s in recorded.items():
        assert s["accepted"] >= 0.9 * s["frames"], (run, s["accepted"], s["frames"])
        assert s["wrong"] == 0, (run, s["max"])


def test_perf_day_recorded_camera_accuracy(recorded):
    """NAV-PERF-02 real camera, screen bench recordings: pooled median <= 5.5 m and p95 <= 17 m
    (campaign 4 city), regression: median <= 5 m, p95 <= 20 m every recording."""
    pooled = _pooled(recorded, recorded.keys())
    assert pooled["median"] <= 5.5, pooled
    assert pooled["p95"] <= 17.0, pooled
    for run, s in recorded.items():
        assert s["median"] <= 5.0 and s["p95"] <= 20.0, (run, s["median"], s["p95"])


def test_perf_day_screen_mission_land_accuracy(mission):
    """NAV-PERF-02 screen mission on other-date imagery, land terrains (city, olives, hills, farms),
    GPS lost: position always available, per terrain median <= 5.5 m and p95 <= 20 m (campaign 4);
    regression: pooled median <= 3 m, p95 <= 6 m."""
    for t in LAND:
        s = mission[t]
        assert s["available"] >= 0.99, (t, s["available"])
        assert s["median"] <= 5.5 and s["p95"] <= 20.0, (t, s["median"], s["p95"])
    pooled = _pooled(mission, LAND)
    assert pooled["median"] <= 3.0 and pooled["p95"] <= 6.0, pooled


def test_perf_day_screen_mission_coast(mission):
    """NAV-PERF-02 screen mission, coast (half sea), GPS lost: availability >= 50 % and median
    <= 7.3 m (campaign 4: 51.6 %, 7.3 m); regression: median <= 6 m, p95 <= 12 m."""
    s = mission["coast"]
    assert s["available"] >= 0.5, s["available"]
    assert s["median"] <= 6.0 and s["p95"] <= 12.0, (s["median"], s["p95"])


def test_perf_day_screen_mission_no_wrong_fix(mission):
    """NAV-PERF-02 screen mission, every terrain: no accepted map fix > 50 m from the truth, output
    within 3 stated sigma >= 95 % (campaign 4: 96-100 %)."""
    for t, s in mission.items():
        assert s["wrong_fixes"] == 0, (t, s["max"])
        assert s["within_3sigma"] is not None and s["within_3sigma"] >= 0.95, (t, s["within_3sigma"])
