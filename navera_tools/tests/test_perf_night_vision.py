"""NAV-PERF-03 regression: night vision accuracy benchmark, offline on data already on disk.

NightLocalizer.localize as night_subscriber calls it (default gates incl. the retry gate, default
heading / height retries) on (1) synthetic thermal-like frames of the Sousse map (night_conditions.py:
nominal 400 m, 600 m, farmland, and the no-information frames open sea / uniform), 24 seeded poses each,
and (2) REAL aerial night LWIR (Bordeaux winter scanner) rendered at the 2026-10-21 poses, FLIR Boson 640
and Hikvision 160 x 120 (50 deg) at 1000 m, 60 poses each. See navera_tools/bench/night_perf.py.

Bounds from the measured numbers (VALIDATION_STATUS.md, night sections) with margin:
  * synthetic: >= 85 % accepted, median <= 13 m, p90 <= 32 m, 0 wrong (> 50 m), 0 accepts on frames
    with no position information;
  * real night thermal: Boson >= 25 % accepted (measured 38 %, "about one frame in three"), median <= 14 m,
    p90 <= 30 m; Hikvision >= 18 % (measured 28 %), median <= 16 m; 0 wrong for both (the retry gate:
    Hikvision 1000 m had 2 wrong before it).
Baseline 2026-10-22: synthetic nominal 24/24, 10.8 / 16.2 / 23.4 m (median / p90 / max), 600 m 24/24 10.5 m,
farmland 22/24 10.8 m, sea 0/24, uniform 0/24; Boson 1000 m 23/60, 10.3 / 20.3 / 31.5 m; Hikvision 1000 m
17/60, 10.7 / 26.0 / 49.7 m; 0 wrong; 100 % within 3 stated sigma.
Run: NAVERA_PERF=1 flock /tmp/claude-1000/navera_gpu.lock \
    python3 -m pytest -q navera_tools/tests/test_perf_night_vision.py
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "navera_tools", "bench"), ROOT, os.path.join(ROOT, "night_pkg"),
          os.path.join(ROOT, "navera_common"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import night_perf  # noqa: E402
from _perf_common import require_perf  # noqa: E402

pytestmark = pytest.mark.perf
INFO = ("nominal", "agl_600m", "terrain_farmland")
NO_INFO = ("terrain_sea", "uniform_frame")


@pytest.fixture(scope="module")
def synthetic():
    require_perf([night_perf.MBTILES, night_perf.STHN_WEIGHTS])
    res = night_perf.run_synthetic(24)
    print("\nsynthetic:", res)
    return res


@pytest.fixture(scope="module")
def thermal():
    t = night_perf.THERMAL_DIR
    require_perf([night_perf.STHN_WEIGHTS, os.path.join(t, night_perf.THERMAL_POSES),
                  os.path.join(t, "bordeaux_2018_night", "raw"), os.path.join(t, "bordeaux_esri_z17.mbtiles")])
    res = night_perf.run_thermal(60)
    print("\nthermal:", res)
    return res


def test_perf_night_synthetic_accuracy(synthetic):
    """NAV-PERF-03 synthetic thermal frames at 400 / 600 m and farmland: >= 85 % accepted,
    median <= 13 m, p90 <= 32 m, no wrong fix (> 50 m), >= 95 % within 3 stated sigma."""
    for c in INFO:
        s = synthetic[c]
        assert s["availability"] >= 0.85, (c, s["accepted"], s["n"])
        assert s["median"] <= 13.0 and s["p90"] <= 32.0, (c, s["median"], s["p90"])
        assert s["wrong"] == 0, (c, s["max"])
        assert s["within_3sigma"] >= 0.95, (c, s["within_3sigma"])


def test_perf_night_synthetic_no_information_refused(synthetic):
    """NAV-PERF-03 synthetic frames with no position information (open sea, uniform frame):
    no position accepted."""
    for c in NO_INFO:
        assert synthetic[c]["accepted"] == 0, (c, synthetic[c])


def test_perf_night_real_thermal_boson_accuracy(thermal):
    """NAV-PERF-03 real aerial night LWIR (Bordeaux), Boson 640 50 deg at 1000 m: >= 25 % of frames
    give a position, median <= 14 m, p90 <= 30 m, no wrong fix (> 50 m)."""
    s = thermal["boson640_50:1000"]
    assert s["availability"] >= 0.25, s
    assert s["median"] <= 14.0 and s["p90"] <= 30.0, s
    assert s["wrong"] == 0, s


def test_perf_night_real_thermal_160px_retry_gate(thermal):
    """NAV-PERF-03 real aerial night LWIR, Hikvision 160 x 120 at 1000 m (where retried hypotheses
    gave 2 wrong fixes before the retry gate): >= 18 % of frames, median <= 16 m, no wrong fix,
    >= 95 % within 3 stated sigma."""
    s = thermal["hik160_50:1000"]
    assert s["availability"] >= 0.18, s
    assert s["median"] <= 16.0, s
    assert s["wrong"] == 0, s
    assert s["within_3sigma"] >= 0.95, s
