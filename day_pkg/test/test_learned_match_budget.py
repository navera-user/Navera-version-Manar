"""learned_matcher._match: LightGlue memory is bounded by MATCH_PAIRS_MAX (block matching), CPU only."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from day_pkg.learned_matcher import LearnedMatcher  # noqa: E402


class _Fake(LearnedMatcher):
    """_match with a stand-in LightGlue: records the pair counts, 'matches' frame i to map i."""

    def __init__(self, budget):
        self._t, self.dev, self.MATCH_PAIRS_MAX = torch, torch.device("cpu"), budget
        self.calls = []

    def _lightglue(self, k0, d0, k1, d1, hw0, hw1):
        self.calls.append((len(k0), len(k1), hw1, k1.clone()))
        # map keypoint j carries its global id in its descriptor's first value
        ids = d1[:, 0].long()
        keep = ids < len(k0)
        j = torch.nonzero(keep).flatten()
        return torch.stack([ids[j], j], dim=1)


def _scene(m=300, n=4000, side=3000, seed=0):
    g = torch.Generator().manual_seed(seed)
    k0 = torch.rand((m, 2), generator=g) * 600
    d0 = torch.zeros((m, 128))
    k1 = torch.rand((n, 2), generator=g) * side
    d1 = torch.zeros((n, 128))
    d1[:, 0] = torch.arange(n, dtype=torch.float32)
    return k0, d0, k1, d1


def test_within_budget_is_one_call_unchanged():
    M = _Fake(budget=10 ** 9)
    k0, d0, k1, d1 = _scene()
    idx = M._match(k0, d0, k1, d1, (450, 600), 3000)
    assert len(M.calls) == 1 and M.calls[0][1] == len(k1) and M._last_blocks == 1
    assert np.array_equal(idx, np.stack([np.arange(300), np.arange(300)], 1))


def test_over_budget_every_call_fits_and_matches_map_back():
    budget = 300 * 1000
    M = _Fake(budget=budget)
    k0, d0, k1, d1 = _scene()
    idx = M._match(k0, d0, k1, d1, (450, 600), 3000)
    assert M._last_blocks > 1
    assert all(m * n <= budget for m, n, _, _ in M.calls)
    # matches come back in the window's indices, once each
    assert np.array_equal(idx, np.stack([np.arange(300), np.arange(300)], 1))


def test_any_frame_footprint_lies_inside_one_block():
    M = _Fake(budget=300 * 1000)
    k0, d0, k1, d1 = _scene()
    M._match(k0, d0, k1, d1, (450, 600), 3000)
    g = int(round(M._last_blocks ** 0.5))
    b = M.calls[0][2][0]
    step = (3000 - b) / (g - 1)
    assert b - step >= 750 - 1                     # overlap >= the frame diagonal (450, 600)
