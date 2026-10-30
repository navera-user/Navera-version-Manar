"""cn_pkg.starseg (SYNTHETIC): the network only picks spots from real pixels; the filter mode only drops spots."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")


class _Lens:
    name = "t"
    cx, cy, radius = 64.0, 64.0, 60.0


def _model(tmp_path, bias: float):
    from cn_pkg import starseg
    net = starseg.build(4)
    with torch.no_grad():
        for p in net.parameters():
            p.zero_()
        net.out.bias.fill_(bias)
    path = tmp_path / "w.pth"
    torch.save({"model": net.state_dict(), "width": 4}, str(path))
    return starseg.StarSeg(str(path), device="cpu")


def _frame():
    rng = np.random.default_rng(0)
    g = 10.0 + rng.normal(0, 1.0, (128, 128))
    yy, xx = np.mgrid[0:128, 0:128]
    g += 20.0 * np.exp(-((xx - 40.3) ** 2 + (yy - 70.6) ** 2) / 2.0)
    return np.clip(np.rint(g), 0, 255).astype(np.uint8)


def test_prob_shape_and_tiling(tmp_path, monkeypatch):
    from cn_pkg import starseg
    m = _model(tmp_path, 3.0)
    monkeypatch.setattr(starseg, "TILE", 48)
    p = m.prob(_frame())
    assert p.shape == (128, 128) and np.allclose(p, 1 / (1 + np.exp(-3.0)), atol=1e-4)
    q = m.prob(_frame(), (10, 20, 100, 90))
    assert q[0, 0] == 0 and q[25, 50] > 0.9


def test_filter_only_drops_and_detect_uses_frame_light(tmp_path):
    from cn_pkg import allsky, starseg
    g = _frame()
    base = allsky.detect_spots(g, _Lens())
    assert base and abs(base[0][0] - 40.3) < 0.5
    keep_all = starseg.finder(_model(tmp_path, 5.0), "filter", 0.5)(g, _Lens())
    drop_all = starseg.finder(_model(tmp_path, -5.0), "filter", 0.5)(g, _Lens())
    assert keep_all == base and drop_all == []
    # a constant probability has no single peak: whatever is returned sits on the frame's own light
    for x, y, f in starseg.finder(_model(tmp_path, 5.0), "detect", 0.5)(g, _Lens()):
        assert f > 0
