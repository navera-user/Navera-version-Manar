"""cn_pkg allsky.identify_prior: star identification with a rough position prior (the vehicle starts with GPS).

Synthetic rays (catalogue stars + junk points) and simulated frames: SIMULATION ONLY. The guarantee tested
first is the one that matters: junk alone never gives an accepted fix, and the chance probability is honest
(junk reaches p <= x no more often than x).
Run from the repository root (PYTHONPATH=.:cn_pkg:navera_common).
"""
import math

import numpy as np
import pytest

from cn_pkg import allsky


@pytest.fixture(scope="module")
def cat():
    return allsky.Catalogue(limit_mag=4.0, path=allsky.BUNDLED_CATALOGUE)


def _random_rotation(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _hemisphere(rng, n, up, min_alt=12.0):
    out = []
    while len(out) < n:
        v = rng.normal(size=3)
        v /= np.linalg.norm(v)
        if math.degrees(math.asin(v @ up)) > min_alt:
            out.append(v)
    return np.array(out).reshape(-1, 3)


def _tilt(rng, z, deg):
    """z turned by deg about a random axis perpendicular to it."""
    a = np.cross(z, rng.normal(size=3))
    a /= np.linalg.norm(a)
    t = math.radians(deg)
    return z * math.cos(t) + np.cross(a, z) * math.sin(t)


def _case(rng, cat, n_stars, n_junk, prior_off_deg, noise_deg=0.06):
    """(rays brightest first, up, true zenith, prior zenith): n_stars real stars hidden among junk points."""
    R = _random_rotation(rng)                                       # IMU -> ICRS (truth)
    up = rng.normal(size=3)
    up /= np.linalg.norm(up)
    z = R @ up
    vis = cat.vec @ R
    alt = np.degrees(np.arcsin(vis @ up))
    idx = np.nonzero(alt > 15)[0]
    idx = idx[np.argsort(cat.mag[idx])][:n_stars]
    s = vis[idx] + rng.normal(size=(len(idx), 3)) * math.radians(noise_deg)
    s /= np.linalg.norm(s, axis=1)[:, None]
    junk = _hemisphere(rng, n_junk, up)
    rays = np.vstack([junk[:5], s, junk[5:]])                       # the brightest spots are junk (lamps, planes)
    return rays, up, z, _tilt(rng, z, prior_off_deg)


def _zenith_err_deg(R, up, z):
    return math.degrees(math.acos(min(1.0, float((R @ up) @ z))))


def test_align_maps_a_onto_b():
    rng = np.random.default_rng(0)
    for _ in range(20):
        a, b = rng.normal(size=3), rng.normal(size=3)
        a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
        R = allsky._align(a, b)
        assert np.allclose(R @ a, b, atol=1e-9) and np.allclose(R @ R.T, np.eye(3), atol=1e-9)


def test_junk_never_accepted_and_chance_is_honest(cat):
    rng = np.random.default_rng(1)
    ps, accepted = [], 0
    for t in range(300):
        up = rng.normal(size=3)
        up /= np.linalg.norm(up)
        z = _random_rotation(rng) @ up
        rad = (0.3, 1.0, 0.5)[t % 3]
        rays = _hemisphere(rng, (20, 40, 60)[t % 3], up)
        r = allsky.identify_prior(rays, up, _tilt(rng, z, rad * rng.uniform()), rad, cat)
        if r is None:
            ps.append(1.0)
            continue
        ps.append(r[4])
        accepted += allsky.accept(len(r[1]), r[3], r[4]) is None
    ps = np.array(ps)
    assert accepted == 0
    for alpha in (0.1, 0.03):                                       # junk reaches p <= alpha at most ~alpha of the time
        assert (ps <= alpha).mean() <= alpha


@pytest.mark.parametrize("rad", [0.3, 1.0, 3.0])
def test_few_stars_among_junk_are_found(cat, rad):
    """8 real stars hidden among 40 junk points (the 5 brightest spots junk), the truth anywhere inside the prior's
    disc: the identification is right (zenith within 0.2 deg) and every accepted one is right. A wider prior
    means more hypotheses, so a higher chance probability: with 0.3 deg (~30 km) nearly all are accepted."""
    rng = np.random.default_rng(int(rad * 10))
    right = accepted = 0
    for _ in range(12):
        rays, up, z, zp = _case(rng, cat, 8, 40, rad * rng.uniform(0, 0.9))
        r = allsky.identify_prior(rays, up, zp, rad, cat)
        if r is None:
            continue
        ok = _zenith_err_deg(r[0], up, z) < 0.2
        right += ok
        if allsky.accept(len(r[1]), r[3], r[4]) is None:
            assert ok
            accepted += 1
    assert right >= 11
    assert accepted >= {0.3: 9, 1.0: 4, 3.0: 3}[rad]


def test_prior_beats_lost_in_space_on_few_stars(cat):
    """The same 7 stars among 40 junk points: the prior's chance probability is far lower (fewer hypotheses)."""
    rng = np.random.default_rng(5)
    better = 0
    for _ in range(10):
        rays, up, z, zp = _case(rng, cat, 7, 40, 0.2)
        rp = allsky.identify_prior(rays, up, zp, 0.5, cat)
        rl = allsky.identify(rays, cat, with_p=True)
        p_l = rl[4] if rl is not None else 1.0
        if rp is not None and _zenith_err_deg(rp[0], up, z) < 0.2 and rp[4] < p_l / 10:
            better += 1
    assert better >= 7


def test_wrong_prior_gives_no_fix_near_it(cat):
    """The truth 5 deg (~550 km) outside a 0.5 deg prior: the stars cannot be matched there, and nothing is
    accepted near the prior (a fix is never made because it is close to the prior)."""
    rng = np.random.default_rng(7)
    for _ in range(15):
        rays, up, z, _ = _case(rng, cat, 12, 30, 0.0)
        zp = _tilt(rng, z, 5.0)
        r = allsky.identify_prior(rays, up, zp, 0.5, cat)
        assert r is None or allsky.accept(len(r[1]), r[3], r[4]) is not None


def test_chance_probability_prior_counts_one_seed(cat):
    assert allsky.chance_probability_prior(40, 1, 100, cat, 0.5) == 1.0
    p1 = allsky.chance_probability_prior(40, 8, 100, cat, 0.5)
    assert p1 < allsky.chance_probability_prior(40, 8, 1000, cat, 0.5) <= 1.0
    # one seed matches by construction (lost-in-space: two): the same count is more significant here
    assert allsky.chance_probability(40, 8, 100, cat, 0.5) > p1
    assert allsky.chance_probability_prior(40, 8, 100, cat, 0.5, density=2.0) > p1


# ── end to end on simulated frames (SIMULATION ONLY) ─────────────────

def _sim():
    try:
        from navera_tools.sim import celestial360_conditions as cc
    except ImportError:
        pytest.skip("simulator (navera_tools) not on the path")
    return cc


def test_sim_locate_with_prior_gives_the_same_fix(cat):
    cc = _sim()
    cond = cc.Condition("baseline mag<=3")
    sc = cc.Scene(cond, 0)
    frame = cc.render(sc)
    up, _ = cc.solver_up(sc)
    lis = allsky.locate(frame, up, sc.utc, cat, f_scales=(1.0,))
    pri = allsky.locate(frame, up, sc.utc, cat, f_scales=(1.0,), prior=(cond.lat + 0.3, cond.lon - 0.3, 1.0))
    assert lis["solved"] and pri["solved"]
    assert pri["prior_radius_deg"] == 1.0 and pri["p_chance"] <= lis["p_chance"]
    assert abs(pri["lat"] - lis["lat"]) < 0.02 and abs(pri["lon"] - lis["lon"]) < 0.02


def test_sim_junk_frame_with_prior_is_refused(cat):
    cc = _sim()
    cond = cc.Condition("JUNK 60 random points", junk=True, effects={"random_points": 60})
    sc = cc.Scene(cond, 0)
    frame = cc.render(sc)
    up, _ = cc.solver_up(sc)
    out = allsky.locate(frame, up, sc.utc, cat, f_scales=(1.0,), prior=(cond.lat, cond.lon, 1.0))
    assert not out["solved"]


# ── bright planets as catalogue points ───────────────────────────────

def test_planets_sit_where_they_are_seen(cat):
    """A planet's catalogue point, looked at as a star, lands on the planet's apparent place (< 1 arcsec)."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
    from cn_pkg.nodes.celestial_math import obs_time
    utc, lat, lon = "2026-10-30 03:30:00", 35.83, 10.64
    t, loc = obs_time(utc), EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    frame = AltAz(obstime=t, location=loc)
    got = allsky.planet_vectors(utc, lat, lon)
    assert {"jupiter", "mars"} <= set(got)                          # both well up before dawn that night
    for name, (v, _) in got.items():
        ra, dec = allsky.vec_to_radec(v)
        a = SkyCoord(ra * u.deg, dec * u.deg).transform_to(frame)
        assert a.separation(get_body(name, t, loc).transform_to(frame)).arcsec < 1.0
    withp = cat.with_planets(utc, lat, lon)
    assert len(withp.vec) == len(cat.vec) + len(got) and withp.names == list(got)
    assert len(withp.pair_sep) > len(cat.pair_sep) and len(cat.vec) < len(withp.vec)
    assert withp is cat.with_planets(utc, lat, lon)                 # cached (10 min)
