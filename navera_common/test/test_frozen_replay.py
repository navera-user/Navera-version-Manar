"""Replay: the frozen-camera detector on a REAL recorded flight (D24 / H-01b, NAV-SAF-19).

MARS-LVIG AMvalley03 (DJI M300, downward global-shutter camera, JPEG stream, its own attitude and
GNSS): on the ground before take-off, climb, a hover with a slow yaw turn, then lawnmower legs.
Frames are offered at 1 Hz as live_camera does (fps default), with the vehicle motion judged as
LiveCamera._moved does (attitude change > 0.5 deg or GNSS travel > 5 m between the exposures).

* the real stream is never called frozen — not on the ground, not in the hover (no false alarm
  for a vehicle that holds still: a real sensor's noise makes every exposure differ);
* the margin: the smallest picture change between two real frames while the vehicle moved,
  against the detector's 0.5 grey-level threshold;
* a freeze injected in the replay while the vehicle moves: a driver re-delivering the last
  picture with new times is caught on every frozen frame; a stream re-encoding the stuck picture
  from its second frame (measured limit, below); the first real frame after it ends the freeze.

Data (not in git, academic licence, evaluation only): NAVERA_FLIGHT_DIR, default the ADATA disk's
mars_lvig/ext/AMvalley03 (made by navera_tools/bench/mars_lvig_extract.py). Skipped when absent.
"""
import csv
import math
import os

import numpy as np
import pytest

from navera_common.geo import haversine_m
from navera_common.health import FrozenFrameDetector

FLIGHT = os.environ.get("NAVERA_FLIGHT_DIR",
                        "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/mars_lvig/ext/AMvalley03")
cv2 = pytest.importorskip("cv2")
pytestmark = pytest.mark.skipif(not os.path.isfile(os.path.join(FLIGHT, "frames.csv")),
                                reason=f"recorded flight not found ({FLIGHT}; NAVERA_FLIGHT_DIR)")

MOTION_DEG, MOTION_M = 0.5, 5.0          # live_camera frozen_motion_deg / frozen_motion_m defaults


def _nearest(table, t):
    i = int(np.searchsorted(table[:, 0], t))
    i = min(max(i, 0), len(table) - 1)
    return table[i]


@pytest.fixture(scope="module")
def flight():
    """(time, frame) at 1 Hz and the vehicle-motion verdict between consecutive offered frames."""
    with open(os.path.join(FLIGHT, "frames.csv")) as f:
        rows = list(csv.DictReader(f))
    s = np.load(os.path.join(FLIGHT, "sensors.npz"))
    att, gps = s["att"], s["gps"]                 # att: t, qx, qy, qz, qw; gps: t, lat, lon, alt, ...
    offered, last_t = [], -1e9
    for r in rows:
        t = float(r["t"])
        if t - last_t >= 1.0:                     # live_camera offers at most fps (1 Hz)
            offered.append((t, os.path.join(FLIGHT, "frames", r["file"])))
            last_t = t
    moving = [None]
    for (t0, _), (t1, _) in zip(offered, offered[1:]):
        a, b = _nearest(att, t0)[1:5], _nearest(att, t1)[1:5]
        rot = math.degrees(2.0 * math.acos(min(1.0, abs(float(np.dot(a, b))))))
        g0, g1 = _nearest(gps, t0), _nearest(gps, t1)
        moving.append(rot > MOTION_DEG or haversine_m(g0[1], g0[2], g1[1], g1[2]) > MOTION_M)
    return offered, moving


def _frames(offered):
    for t, path in offered:
        img = cv2.imread(path)
        assert img is not None, path
        yield t, img


def test_a_real_stream_is_never_frozen_on_the_ground_in_the_hover_or_in_flight(flight):
    offered, moving = flight
    det = FrozenFrameDetector()
    frozen, still, min_moving_diff, prev = [], 0, math.inf, None
    for (t, img), mv in zip(_frames(offered), moving):
        if det.update(img, t, mv):
            frozen.append((round(t - offered[0][0]), det.reason))
        small = det._small_grey(img)
        if prev is not None and mv:
            min_moving_diff = min(min_moving_diff, float(np.abs(small - prev).mean()))
        still += mv is False
        prev = small
    print(f"{len(offered)} frames at 1 Hz, {still} with the vehicle still (ground / hover), "
          f"smallest change while moving {min_moving_diff:.2f} grey levels (threshold {det.still_diff})")
    assert len(offered) > 400 and still > 20          # the replay holds still periods, not only flight
    assert frozen == []
    assert min_moving_diff > 4 * det.still_diff        # a real moving picture is far from "unchanged"


def _replay_with(offered, moving, k0, n_frozen, stale):
    """Verdicts of the replay where frames k0 .. k0+n_frozen-1 are stale(i, stuck picture, previous output)."""
    det, stuck, out, verdicts = FrozenFrameDetector(), None, None, []
    for i, ((t, img), mv) in enumerate(zip(_frames(offered[:k0 + n_frozen + 3]), moving)):
        if i == k0 - 1:
            stuck = img
        if k0 <= i < k0 + n_frozen:
            assert mv, "the injected freeze must fall while the vehicle moves"
            out = stale(stuck, out)
        else:
            out = img
        verdicts.append(det.update(out, t, mv))
    return det, verdicts


def _reencode(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


K0, N_FROZEN = 200, 12                                   # in the lawnmower legs: the vehicle moves


def test_a_driver_re_delivering_the_last_picture_is_caught_on_every_frame_and_ends(flight):
    det, verdicts = _replay_with(*flight, K0, N_FROZEN, lambda stuck, prev: stuck.copy())
    assert all(v is None for v in verdicts[:K0])
    caught = verdicts[K0:K0 + N_FROZEN]
    assert all(v and "identical" in v for v in caught), caught
    assert det.repeats == 0 and verdicts[K0 + N_FROZEN] is None       # the first real frame ends it


def test_a_stream_re_encoding_a_stuck_picture_is_caught_from_its_second_frame(flight):
    """Measured limit: one JPEG re-encoding of the stuck picture changes it by ~1.1 grey levels
    (q90; 0.9 at q95, 3.6 at q75), above the 0.5 threshold, so the FIRST re-encoded frame passes
    (one frame, ~1 s old at 1 Hz); the stale picture encoded again is then identical / unchanged
    while the vehicle moves (real moving frames differ by >= 16 grey levels): caught from there on.
    """
    def stale(stuck, prev):
        return _reencode(stuck if prev is None or prev is stuck else prev)     # generation after generation

    det, verdicts = _replay_with(*flight, K0, N_FROZEN, stale)
    assert all(v is None for v in verdicts[:K0])
    caught = verdicts[K0 + 1:K0 + N_FROZEN]
    assert all(caught), caught
    assert det.repeats == 0 and verdicts[K0 + N_FROZEN] is None
