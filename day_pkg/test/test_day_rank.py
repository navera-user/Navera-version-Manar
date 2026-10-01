"""Unit tests for the day retrieval ranking (circle applied before the descriptor comparison)."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics.pairwise import cosine_similarity

from day_pkg.nodes.day_localizer import TOP5_N, DayLocalizer


def make_localizer(n, seed=0):
    """A localizer with a synthetic map: n tiles spread over ~20 km, random descriptors."""
    rng = np.random.default_rng(seed)
    loc = DayLocalizer()
    loc.dino_descs = rng.standard_normal((n, 768)).astype(np.float32)
    loc.coords = np.c_[35.8 + rng.uniform(0, 0.2, n), 10.6 + rng.uniform(0, 0.2, n)]
    loc.df_valid = pd.DataFrame({"imageName": [f"tile_{i}.jpg" for i in range(n)]})
    loc.ready = True
    return loc, rng


def reference_rank(loc, q, center=None, radius_m=None):
    """The previous algorithm: compare with EVERY tile, then keep the circle."""
    sims = cosine_similarity(q.reshape(1, -1), loc.dino_descs)[0]
    if center is None:
        order = sims.argsort()[::-1]
    else:
        cand = np.where(loc._haversine_to_coords(*center) <= radius_m)[0]
        order = cand[np.argsort(sims[cand])[::-1]]
    return [int(i) for i in order[:TOP5_N]], sims


@pytest.mark.parametrize("radius_m", [300.0, 600.0, 2000.0])
def test_circle_first_gives_the_same_ranking_as_before(radius_m):
    loc, rng = make_localizer(5000)
    for _ in range(5):
        q = rng.standard_normal(768).astype(np.float32)
        center = (35.9, 10.7)
        ref_idx, ref_sims = reference_rank(loc, q, center, radius_m)
        res = loc.rank(q, center=center, radius_m=radius_m)
        assert [t["index"] for t in res["top5"]] == ref_idx
        assert [t["dino"] for t in res["top5"]] == pytest.approx([ref_sims[i] for i in ref_idx], abs=1e-6)
        assert res["score"] == pytest.approx(ref_sims[ref_idx[0]], abs=1e-6)
        assert (res["predicted_lat"], res["predicted_lon"]) == tuple(loc.coords[ref_idx[0]])
        assert res["n_candidates"] == int((loc._haversine_to_coords(*center) <= radius_m).sum())


def test_global_search_is_unchanged():
    loc, rng = make_localizer(2000, seed=1)
    q = rng.standard_normal(768).astype(np.float32)
    ref_idx, _ = reference_rank(loc, q)
    res = loc.rank(q)
    assert [t["index"] for t in res["top5"]] == ref_idx
    assert res["spatial"] is False and res["n_candidates"] == 2000


def test_empty_circle_reports_no_candidates():
    loc, rng = make_localizer(500, seed=2)
    res = loc.rank(rng.standard_normal(768).astype(np.float32), center=(0.0, 0.0), radius_m=500.0)
    assert res["spatial_empty"] is True and res["n_candidates"] == 0 and res["predicted_lat"] is None


def test_threshold_decides_acceptance():
    loc, rng = make_localizer(800, seed=3)
    q = loc.dino_descs[10].copy()                     # a query identical to tile 10
    c = tuple(loc.coords[10])
    res = loc.rank(q, threshold=0.75, center=c, radius_m=100.0)
    assert res["top5"][0]["index"] == 10 and res["score"] == pytest.approx(1.0) and res["accepted"]
    assert not loc.rank(q, threshold=1.5, center=c, radius_m=100.0)["accepted"]


@pytest.mark.parametrize("center,radius_m", [((35.9, 10.7), 600.0), ((35.8001, 10.6001), 450.0),
                                             ((35.95, 10.79), 5000.0), ((36.5, 11.5), 600.0)])
def test_circle_lookup_matches_a_full_scan(center, radius_m):
    """The grid index finds exactly the tiles a scan of every tile finds."""
    loc, _ = make_localizer(20000, seed=4)
    full = np.where(loc._haversine_to_coords(*center) <= radius_m)[0]
    assert np.array_equal(loc._tiles_in_circle(center[0], center[1], radius_m), full)


def test_circle_lookup_east_west_route_and_antimeridian():
    """An east-west route (one latitude band) and tiles on both sides of 180° longitude."""
    rng = np.random.default_rng(5)
    loc = DayLocalizer()
    n = 30000
    loc.coords = np.c_[64.0 + rng.normal(0, 0.005, n), np.mod(rng.uniform(170.0, 190.0, n) + 180.0, 360.0) - 180.0]
    for center in ((64.0, 179.999), (64.0, -179.995), (64.001, 175.0)):
        full = np.where(loc._haversine_to_coords(*center) <= 800.0)[0]
        got = loc._tiles_in_circle(center[0], center[1], 800.0)
        assert full.size > 0 and np.array_equal(got, full)
