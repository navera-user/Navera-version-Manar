"""Unit tests for cn_pkg.nodes.celestial_math (celestial position geometry)."""
import math
import random

import pytest

from cn_pkg.nodes.celestial_math import (apparent_radec, choose_candidate, gast_deg,
                                         local_to_radec, observer_candidates)

UTC = "2026-03-10 20:20:00"


@pytest.fixture(scope="module")
def gast():
    return gast_deg(UTC)


def test_round_trip_never_wrong(gast):
    """Random pointings: the chosen solution is exact, or None (ambiguous) — never wrong."""
    rng = random.Random(1)
    wrong = none = 0
    for _ in range(5000):
        lat, lon = rng.uniform(-70, 70), rng.uniform(-180, 180)
        alt, az = rng.uniform(10, 89), rng.uniform(0, 360)
        ra, dec = local_to_radec(lat, lon, alt, az, gast)
        pick = choose_candidate(observer_candidates(alt, az, ra, dec, gast),
                                lat + rng.uniform(-1, 1), lon + rng.uniform(-1, 1))
        if pick is None:
            none += 1
        elif max(abs(pick[0] - lat), abs((pick[1] - lon + 180) % 360 - 180)) > 1e-6:
            wrong += 1
    assert wrong == 0
    assert none < 0.05 * 5000


def test_camera_facing_south_regression(gast):
    """The old single-root formula returned 25.83°N for this Sousse pointing."""
    ra, dec = local_to_radec(35.83, 10.64, 85.0, 180.0, gast)
    pick = choose_candidate(observer_candidates(85.0, 180.0, ra, dec, gast), 35.8)
    assert pick == pytest.approx((35.83, 10.64), abs=1e-6)


def test_two_solutions_without_prior_is_ambiguous(gast):
    ra, dec = local_to_radec(35.83, 10.64, 40.0, 60.0, gast)
    cands = observer_candidates(40.0, 60.0, ra, dec, gast)
    assert len(cands) == 2
    assert choose_candidate(cands, None) is None
    assert choose_candidate(cands, float("nan")) is None


def test_prior_far_from_both_solutions_gives_nothing(gast):
    ra, dec = local_to_radec(35.83, 10.64, 40.0, 60.0, gast)
    cands = observer_candidates(40.0, 60.0, ra, dec, gast)
    assert choose_candidate(cands, -60.0, 100.0) is None


def test_precession_moves_j2000_coordinates():
    """Crab nebula, J2000 → 2026: RA grows by ~0.4° (precession)."""
    ra, dec = apparent_radec(83.6331, 22.0145, UTC)
    assert 0.3 < ra - 83.6331 < 0.5
    assert abs(dec - 22.0145) < 0.1


def test_rotation_rate_between_two_attitudes():
    """The celestial frame gate: 30 deg/s of roll is far above 3 deg/s; 0 when still."""
    import math
    from cn_pkg.nodes.cn_subscriber import _rate_dps
    q0 = (0.0, 0.0, 0.0, 1.0)
    a = math.radians(3.0) / 2                                    # 3 deg about x in 0.1 s
    q1 = (math.sin(a), 0.0, 0.0, math.cos(a))
    assert abs(_rate_dps(q0, q1, 0.1) - 30.0) < 1e-6
    assert _rate_dps(q0, q0, 0.1) == 0.0


def test_a_candidate_far_from_the_prior_is_not_chosen():
    """5 deg let attitude-transient fixes 555 km off through; 2 deg (222 km) does not."""
    from cn_pkg.nodes.celestial_math import choose_candidate
    assert choose_candidate([(39.0, 10.6), (-30.0, 50.0)], 35.8, 10.6) is None
    assert choose_candidate([(36.5, 10.6), (-30.0, 50.0)], 35.8, 10.6) == (36.5, 10.6)
