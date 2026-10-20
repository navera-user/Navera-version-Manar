"""Stop-frame stacking (navera_tools/field/stack.py) and the server's stacked 360 solve path, without a camera."""
import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_tools.field import stack  # noqa: E402


def _frames(n, sigma=3.0, star=6.0, streak_in=None, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        f = 14.0 + rng.normal(0, sigma, (200, 200))
        f[100, 100] += star                                  # a faint star, same place in every frame
        if i == streak_in:
            f[50, 20:180] += 120.0                           # a plane crossing in one frame
        out.append(np.clip(np.round(f), 0, 255).astype(np.uint8))
    return out


def test_stack_lowers_the_noise_and_keeps_the_star():
    fr = _frames(9)
    one, st = fr[0].astype(np.float32), stack.stack_frames(fr)
    gain = min(math.sqrt(8), stack.MAX_GAIN)
    # the star's contrast is amplified by the gain, the noise only by gain / sqrt(8) (= 1)
    snr1 = (one[100, 100] - np.median(one)) / one[150:190, 150:190].std()
    snr8 = (st[100, 100] - np.median(st)) / st[150:190, 150:190].std()
    assert snr8 > 2.0 * snr1
    assert st[150:190, 150:190].std() == pytest.approx(3.0 * gain / math.sqrt(8), rel=0.25)


def test_a_plane_in_one_frame_is_dropped():
    st = stack.stack_frames(_frames(8, streak_in=3))
    assert float(np.median(st[50, 30:170]) - np.median(st)) < 10.0     # the streak was ~120 DN in one frame


def test_saturated_pixels_stay_as_they_were():
    fr = [np.full((400, 400), 20, np.uint8) for _ in range(5)]
    for f in fr:
        f[300:304, 300:304] = 255                            # a lamp
    st = stack.stack_frames(fr)
    assert float(st[301, 301]) == 255.0 and float(st[10, 10]) == pytest.approx(20.0, abs=0.5)


def test_ring_window_and_duplicates():
    r = stack.StackRing(stack.ring_size(3.0))
    assert r.size == 7
    g = np.zeros((4, 4), np.uint8)
    for ms in (1000, 1500, 1500, 2000, 2500, 3000, 3500, 4000, 4500):
        r.keep(ms, g)
    assert [ms for ms, _ in r.window(2500, 4500)] == [2500, 3000, 3500, 4000, 4500]
    assert len(r) == 7 and stack.ring_size(0) == 0


def test_window_is_still_checks_the_whole_window():
    moving_at = {3000}
    still = lambda m: {"stopped": not any(m - 2000 <= x <= m + 500 for x in moving_at)}   # noqa: E731
    assert stack.window_is_still(still, 6000, 9000)
    assert not stack.window_is_still(still, 1000, 9000)


class _Driver:
    def __init__(self, moving=False):
        self.stack_ring, self.moving = None, moving

    def stopped(self, at_ms=None):
        return {"stopped": not self.moving}

    def gravity(self, at_ms=None):
        return np.array([0.0, 0.0, 1.0]), 1.0, 0.0


class _Cam:
    def __init__(self, drv):
        self.cam, self.frame_ms = drv, None


def _field(drv):
    from navera_tools.field import server as sv
    f = sv.Field.__new__(sv.Field)
    f.camera, f.live = _Cam(drv), {"confirmed": 2}
    return f, sv


def test_server_stacks_the_key_frames_of_a_still_window(monkeypatch):
    drv = _Driver()
    f, sv = _field(drv)
    monkeypatch.setattr(sv, "STACK_SECONDS", 3.0)
    f._sync_stack_ring()
    assert drv.stack_ring is not None and drv.stack_ring.size == 7
    grey = np.full((1920, 3840), 14, np.uint8)
    for k in range(7):
        drv.stack_ring.keep(10_000 + 500 * k, grey)
    f.camera.frame_ms = 13_000
    got, why = f._stack360(texp=1000.0)
    assert why is None
    img, up, t_mid, info = got
    assert info["frames"] == 7 and info["seconds"] == 3.0 and t_mid == pytest.approx(998.5)
    assert img.shape == grey.shape and info["spots_single"] == 2


def test_server_refuses_a_stack_when_the_camera_moved(monkeypatch):
    drv = _Driver(moving=True)
    f, sv = _field(drv)
    monkeypatch.setattr(sv, "STACK_SECONDS", 2.0)
    f._sync_stack_ring()
    for k in range(5):
        drv.stack_ring.keep(10_000 + 500 * k, np.zeros((8, 8), np.uint8))
    f.camera.frame_ms = 12_000
    got, why = f._stack360(texp=0.0)
    assert got is None and "moved" in why


def test_stacking_off_drops_the_ring(monkeypatch):
    drv = _Driver()
    f, sv = _field(drv)
    monkeypatch.setattr(sv, "STACK_SECONDS", 0.0)
    drv.stack_ring = stack.StackRing(3)
    f._sync_stack_ring()
    assert drv.stack_ring is None


def test_live_param_accepts_the_stack_window():
    from navera_tools.field import server as sv
    assert sv.check_live_param("server.STACK_SECONDS", 3) == (3.0, None)
    assert sv.check_live_param("server.STACK_SECONDS", 9)[0] is None


def test_offline_driver_keeps_key_frames_for_stacking(tmp_path):
    pytest.importorskip("av")
    from navera_tools.tests import test_field_raw as tr
    from navera_tools.field import replay360 as rp
    pk = tr._packets(seconds=3.0)
    drv = rp.OfflineDriver()
    drv.stack_ring = stack.StackRing(10)
    clock = rp.Clock(pk[0][0])
    saved, rp.insta360_usb.time = rp.insta360_usb.time, clock.module()
    try:
        for t, p in pk:
            clock.t = t
            drv.feed(t, p)
    finally:
        rp.insta360_usb.time = saved
    assert len(drv.stack_ring) >= 2
    ms = [m for m, _ in drv.stack_ring.window(0, 1e12)]
    assert ms == sorted(ms) and drv.stack_ring.window(0, 1e12)[0][1].ndim == 2


class _Session:
    def __init__(self):
        self.logged = []

    def log(self, kind, rec):
        self.logged.append((kind, dict(rec)))

    def event(self, *a, **k):
        pass


def test_solve_on_the_stack_uses_its_star_count_up_and_time(monkeypatch):
    drv = _Driver()
    f, sv = _field(drv)
    f.solving = True
    up_mid = np.array([0.0, 0.1, 0.995])
    info = {"frames": 7, "seconds": 3.0, "spots": 4, "spots_single": 2}
    monkeypatch.setattr(f, "_stack360", lambda texp: ((np.zeros((8, 8), np.float32), up_mid, texp - 1.5, info), None))
    s = _Session()
    f._solve360(s, {"idx": 1}, np.zeros((8, 8), np.uint8), np.array([0, 0, 1.0]), 100.0, stack=True)
    kind, rec = s.logged[-1]
    assert kind == "frames" and rec["stack"] == info and rec["t_exp"] == 98.5
    assert rec["up_imu"][1] == 0.1 and rec["why"].startswith("too few stars (4 in the stack")
    assert f.solving is False


def test_no_stack_falls_back_to_the_single_frame_gate(monkeypatch):
    drv = _Driver()
    f, sv = _field(drv)
    f.solving = True
    monkeypatch.setattr(f, "_stack360", lambda texp: (None, "2 key frames to stack (min 3)"))
    s = _Session()
    f._solve360(s, {"idx": 2}, np.zeros((8, 8), np.uint8), np.array([0, 0, 1.0]), 100.0, stack=True)
    rec = s.logged[-1][1]
    assert rec["stack"] == {"none": "2 key frames to stack (min 3)"} and rec["why"] == "too few stars (2)"
