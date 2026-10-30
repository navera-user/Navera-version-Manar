"""cn_pkg.starseg fast path (prob_fast: same map as prob_ref) and the optional second attempt in the 360 locator
(NAVERA_STARSEG=1 only, only after a failed solve, skipped when slow). Synthetic inputs; no weights needed.
"""
import numpy as np
import pytest

torch = pytest.importorskip("torch")

from cn_pkg import allsky, allsky_locator, starseg  # noqa: E402
from cn_pkg.allsky_locator import AllSkyLocator  # noqa: E402


def _model():
    """A StarSeg with random weights on the CPU (no file), torch path."""
    torch.manual_seed(0)
    m = starseg.StarSeg.__new__(starseg.StarSeg)
    m.torch, m.device, m.half, m.trt = torch, "cpu", False, None
    m.net = starseg.build(8).eval()
    return m


def test_prob_fast_equals_prob_ref(monkeypatch):
    monkeypatch.setattr(starseg, "FAST_TILE", 128)
    monkeypatch.setattr(starseg, "FAST_BATCH", 3)
    monkeypatch.setattr(starseg, "TILE", 256)                 # several reference tiles too
    monkeypatch.setattr(starseg, "TILE_PAD", 32)              # (16 px: the reference's own seams differ)
    rng = np.random.default_rng(1)
    g = rng.integers(0, 40, (300, 420)).astype(np.uint8)
    m = _model()
    for box in ((0, 0, 420, 300), (37, 21, 401, 290)):       # box offsets not multiples of 4 nor of the tile
        a, b = m.prob_ref(g, box), m.prob_fast(g, box)
        assert np.abs(a - b).max() < 1e-4
        x0, y0, x1, y1 = box
        assert not b[:y0].any() and not b[:, :x0].any()


def test_prob_fast_small_box(monkeypatch):
    monkeypatch.setattr(starseg, "FAST_TILE", 128)
    g = np.random.default_rng(2).integers(0, 40, (90, 70)).astype(np.uint8)
    m = _model()
    assert np.abs(m.prob_ref(g) - m.prob_fast(g)).max() < 1e-4


def test_sky_tiles_skip_the_ground(monkeypatch):
    from cn_pkg import sky360
    monkeypatch.setattr(starseg, "FAST_TILE", 256)
    L = sky360.default_lenses()[0]
    m = _model()
    shape = (1920, 3840)
    box = starseg.lens_box(L, shape)
    h, w = box[3] - box[1], box[2] - box[0]
    every = m._sky_tiles(box, None, None, None, h, w)
    # 'up' along the lens axis: the whole circle is sky; against it: none (lens looks at the ground)
    axis = allsky.unproject(L, np.array([L.cx]), np.array([L.cy]))[0]
    assert len(m._sky_tiles(box, L, axis, 12.0, h, w)) > 0
    assert m._sky_tiles(box, L, -axis, 12.0, h, w) == []
    assert len(m._sky_tiles(box, L, axis, 12.0, h, w)) <= len(every)


class _Calls:
    def __init__(self, solved_first=False, solved_second=True):
        self.calls, self.solved = [], [solved_first, solved_second]

    def __call__(self, frame, up, utc, cat, lenses=None, f_scales=None, spot_finder=None, **kw):
        i = len(self.calls)
        self.calls.append(spot_finder)
        if not self.solved[min(i, 1)]:
            return {"solved": False, "why": f"attempt {i}"}
        return {"solved": True, "lat": 36.0, "lon": 10.0, "R_icrs_imu": np.eye(3).tolist(), "f_scale": 1.0,
                "matched": 9, "used": 9, "rms_deg": 0.1, "p_chance": 1e-9, "sigma_fit_deg": 0.05}


@pytest.fixture
def loc(monkeypatch):
    monkeypatch.setattr(allsky_locator.sky360, "default_lenses", lambda *a: [])
    monkeypatch.setattr(starseg, "StarSeg", lambda *a, **k: object())
    monkeypatch.setattr(starseg, "finder", lambda model, mode="detect", **k: ("finder", mode))

    def make(env="1"):
        if env is None:
            monkeypatch.delenv("NAVERA_STARSEG", raising=False)
        else:
            monkeypatch.setenv("NAVERA_STARSEG", env)
        return AllSkyLocator(catalogue=object(), f_scale_search=(1.0,))
    return make


META = {"up_imu": [0.0, 0.0, 1.0], "stopped": True}


def test_off_by_default(loc, monkeypatch):
    c = _Calls()
    monkeypatch.setattr(allsky, "locate", c)
    out = loc(None).process(np.zeros((8, 8), np.uint8), "2026-10-29T23:00:00", META)
    assert not out["success"] and c.calls == [None] and "starseg" not in out


def test_second_attempt_only_after_a_failed_solve(loc, monkeypatch):
    c = _Calls(solved_first=True)
    monkeypatch.setattr(allsky, "locate", c)
    assert loc().process(np.zeros((8, 8), np.uint8), "2026-10-29T23:00:00", META)["success"]
    assert c.calls == [None]


def test_second_attempt_solves(loc, monkeypatch):
    c = _Calls(solved_first=False, solved_second=True)
    monkeypatch.setattr(allsky, "locate", c)
    out = loc().process(np.zeros((8, 8), np.uint8), "2026-10-29T23:00:00", META)
    assert out["success"] and c.calls == [None, ("finder", "detect")] and out["starseg"]["solved"]


def test_second_attempt_fails_keeps_first_reason(loc, monkeypatch):
    c = _Calls(solved_first=False, solved_second=False)
    monkeypatch.setattr(allsky, "locate", c)
    out = loc().process(np.zeros((8, 8), np.uint8), "2026-10-29T23:00:00", META)
    assert not out["success"] and out["error"] == "attempt 0" and out["starseg"]["solved"] is False


def test_skipped_after_a_slow_run(loc, monkeypatch):
    c = _Calls(solved_first=False, solved_second=False)
    monkeypatch.setattr(allsky, "locate", c)
    lo = loc()
    lo.starseg_last_s = allsky_locator.STARSEG_MAX_S + 0.1
    out = lo.process(np.zeros((8, 8), np.uint8), "2026-10-29T23:00:00", META)
    assert c.calls == [None] and "starseg" not in out


def test_model_that_cannot_load_is_skipped(loc, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("no weights")
    monkeypatch.setattr(starseg, "StarSeg", boom)
    c = _Calls(solved_first=False, solved_second=False)
    monkeypatch.setattr(allsky, "locate", c)
    lo = loc()
    for _ in range(2):
        out = lo.process(np.zeros((8, 8), np.uint8), "2026-10-29T23:00:00", META)
        assert not out["success"] and "starseg" not in out
    assert c.calls == [None, None] and lo._starseg is False


def test_trt_loader_off_and_without_tensorrt(monkeypatch):
    from cn_pkg import starseg_trt
    from navera_common import trt_engine
    monkeypatch.setenv("NAVERA_STARSEG_TRT", "0")
    assert starseg_trt.Loader("/nonexistent.pth").get() is None
    monkeypatch.setenv("NAVERA_STARSEG_TRT", "1")
    monkeypatch.setattr(trt_engine, "import_tensorrt", lambda: None)
    ld = starseg_trt.Loader("/nonexistent.pth")
    assert ld.get() is None and ld.dead


def test_run_net_falls_back_to_torch_when_the_engine_fails():
    m = _model()

    class Bad:
        def get(self):
            return self

        def __call__(self, x):
            raise RuntimeError("engine")

        def failed(self):
            self.dead = True
    m.trt = Bad()
    x = torch.zeros((1, 2, 16, 16))
    assert m.run_net(x).shape == (1, 1, 16, 16) and m.trt.dead
