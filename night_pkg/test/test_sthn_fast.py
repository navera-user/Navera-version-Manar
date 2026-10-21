"""sthn_fast: the closed-form rectangle -> quadrilateral homography equals STHN's solved one (CPU)."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
tgm = pytest.importorskip("kornia.geometry.transform")

from night_pkg.sthn_fast import rect_to_quad_points  # noqa: E402


def _kornia_points(disp, h, w):
    """IHN.get_flow_now_4's points for disp (already / 4): kornia's 8x8 solve, then the grid mapped."""
    b = disp.shape[0]
    org = torch.zeros((2, 2, 2), dtype=torch.float64)
    org[:, 0, 0] = torch.tensor([0, 0])
    org[:, 0, 1] = torch.tensor([w - 1, 0])
    org[:, 1, 0] = torch.tensor([0, h - 1])
    org[:, 1, 1] = torch.tensor([w - 1, h - 1])
    org = org.unsqueeze(0).repeat(b, 1, 1, 1)
    new = (org + disp).flatten(2).permute(0, 2, 1).contiguous()
    H = tgm.get_perspective_transform(org.flatten(2).permute(0, 2, 1).contiguous(), new)
    gy, gx = torch.meshgrid(torch.linspace(0, h - 1, h, dtype=torch.float64),
                            torch.linspace(0, w - 1, w, dtype=torch.float64), indexing="ij")
    pts = torch.stack([gx.flatten(), gy.flatten(), torch.ones(h * w, dtype=torch.float64)])[None].repeat(b, 1, 1)
    p = H.bmm(pts)
    p = p[:, :2] / p[:, 2:]
    return p.view(b, 2, h, w)


@pytest.mark.parametrize("seed", range(5))
def test_matches_kornia_solve(seed):
    g = torch.Generator().manual_seed(seed)
    disp = (torch.rand((3, 2, 2, 2), generator=g, dtype=torch.float64) - 0.5) * 30.0
    ours = rect_to_quad_points(disp, 64, 64)
    ref = _kornia_points(disp, 64, 64)
    assert torch.allclose(ours, ref, atol=1e-6)


def test_identity_is_the_grid():
    p = rect_to_quad_points(torch.zeros((1, 2, 2, 2)), 64, 64)
    gy, gx = np.mgrid[0:64, 0:64]
    assert np.allclose(p[0, 0].numpy(), gx, atol=1e-4)
    assert np.allclose(p[0, 1].numpy(), gy, atol=1e-4)


def test_pure_translation():
    d = torch.zeros((1, 2, 2, 2))
    d[:, 0] = 5.0
    d[:, 1] = -3.0
    p = rect_to_quad_points(d, 64, 64)
    gy, gx = np.mgrid[0:64, 0:64]
    assert np.allclose(p[0, 0].numpy(), gx + 5.0, atol=1e-4)
    assert np.allclose(p[0, 1].numpy(), gy - 3.0, atol=1e-4)


def test_degenerate_quad_is_not_finite():
    """All four corners on one point: no homography (STHN keeps its previous step)."""
    d = torch.zeros((1, 2, 2, 2))
    d[0, 0, 0, 1] = -63.0
    d[0, 0, 1, 1] = -63.0
    d[0, 1, 1, 0] = -63.0
    d[0, 1, 1, 1] = -63.0
    assert not torch.isfinite(rect_to_quad_points(d, 64, 64)).all()
