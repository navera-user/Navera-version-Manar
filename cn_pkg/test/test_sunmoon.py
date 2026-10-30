"""sunmoon: ephemeris, disc centre, gates and the line-of-position fusion (synthetic frames, no camera)."""
import math
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "navera_common")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
warnings.filterwarnings("ignore")

from cn_pkg import sunmoon as sm  # noqa: E402
from cn_pkg import sunmoon_validate as sv  # noqa: E402
from cn_pkg.sky360 import Lens, R_LEFT, R_RIGHT  # noqa: E402

SOUSSE = (35.83, 10.64)


def lenses():
    """The nominal lens model (independent of the machine's calibration file)."""
    return [Lens("left", 960.8, 959.4, 560.9, R_LEFT, 0.054), Lens("right", 2871.7, 962.6, 555.6, R_RIGHT, 0.069)]


def test_altaz_matches_astropy():
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, get_body
    from cn_pkg.nodes.celestial_math import obs_time
    for body, utc in (("sun", "2026-10-30 11:00:00"), ("moon", "2026-10-30 04:30:00")):
        alt, az, _ = sm.body_place(body, utc).altaz(*SOUSSE)
        t = obs_time(utc)
        loc = EarthLocation(lat=SOUSSE[0] * u.deg, lon=SOUSSE[1] * u.deg)
        c = get_body(body, t, loc).transform_to(AltAz(obstime=t, location=loc))
        assert abs(alt - c.alt.deg) < 0.005 and abs((az - c.az.deg + 180) % 360 - 180) < 0.01


def test_moon_phase_and_lit_centroid():
    assert abs(sm.body_place("moon", "2026-10-30 04:30:00").illuminated_fraction() - 0.79) < 0.02
    assert abs(sm.lit_centroid_offset(1.0)) < 1e-3
    assert abs(sm.lit_centroid_offset(0.5) - 4 / (3 * math.pi)) < 2e-3


def test_circle_fit():
    th = np.linspace(0, 2 * np.pi, 60, endpoint=False)
    pts = np.c_[100 + 7 * np.cos(th), 50 + 7 * np.sin(th)]
    cx, cy, r, rms = sm._circle_fit(pts)
    assert abs(cx - 100) < 1e-6 and abs(cy - 50) < 1e-6 and abs(r - 7) < 1e-6


def _frame_with(body, utc, up, heading, bg=12, extra_lamp_alt=None):
    L = lenses()
    place = sm.body_place(body, utc)
    h, az, _ = place.altaz(*SOUSSE)
    R = sv.pose(up, heading)
    ray = R @ sv.enu_vec(h + sm.refraction_deg(h), az)
    img = np.full((1920, 3840), bg, np.uint8)
    s_dir = R @ (sm.enu_basis(*SOUSSE) @ sm._unit(place.sun_ecef_km - place.r_ecef_km))
    img = sv.render_body(img, L, ray, place.semidiameter_deg(*SOUSSE), bloom_deg=0.8, halo_deg=2.0, halo_dn=120,
                         lit=place.illuminated_fraction(), sun_dir_imu=s_dir)
    if extra_lamp_alt is not None:
        lamp = R @ sv.enu_vec(extra_lamp_alt, (az + 120) % 360)
        img = sv.render_body(img, L, lamp, 0.3, bloom_deg=0.8, halo_deg=2.0, halo_dn=120)
    return img, h, az, L


def test_sun_altitude_from_a_synthetic_frame():
    up = np.array([0.0, 1.0, 0.05])
    img, h, az, L = _frame_with("sun", "2026-10-30 10:00:00", up, 40.0)
    s, rep = sm.sight_from_frame(img, up, "2026-10-30 10:00:00", (SOUSSE[0], SOUSSE[1], 30.0), lenses=L)
    assert s is not None, rep
    assert abs(s.alt_deg - h) < 0.1, (s.alt_deg, h, rep)


def test_gibbous_moon_altitude_from_a_synthetic_frame():
    up = np.array([0.0, 1.0, 0.0])
    utc = "2026-10-30 04:30:00"
    img, h, az, L = _frame_with("moon", utc, up, 200.0, bg=8)
    s, rep = sm.sight_from_frame(img, up, utc, (SOUSSE[0], SOUSSE[1], 30.0), lenses=L)
    assert s is not None, rep
    assert abs(s.alt_deg - h) < 0.12, (s.alt_deg, h, rep)
    assert "moon_lit" in rep


def test_lamp_in_the_gate_makes_it_ambiguous_and_none_outside_refused():
    up = np.array([0.0, 1.0, 0.0])
    utc = "2026-10-30 10:00:00"
    h = sm.body_place("sun", utc).altaz(*SOUSSE)[0]
    img, _, _, L = _frame_with("sun", utc, up, 10.0, extra_lamp_alt=h + 0.3)
    s, rep = sm.sight_from_frame(img, up, utc, (SOUSSE[0], SOUSSE[1], 30.0), lenses=L)
    assert s is None and "ambiguous" in rep["why"]
    # a lamp alone, 10 deg away from the Sun's altitude: nothing
    img = np.full((1920, 3840), 12, np.uint8)
    R = sv.pose(up, 0.0)
    img = sv.render_body(img, L, R @ sv.enu_vec(h - 10, 90.0), 0.3, bloom_deg=0.8)
    s, rep = sm.sight_from_frame(img, up, utc, (SOUSSE[0], SOUSSE[1], 30.0), lenses=L)
    assert s is None and rep["candidates"] == 1 and rep["in_gate"] == 0


def test_running_fix_crosses_lines_and_stays_honest():
    """Exact sun altitudes 3 h apart (azimuths differ by ~45 deg): the fix lands within its sigma; with the bias
    learnt away the sigma is small."""
    truth = SOUSSE
    sights = []
    for utc in ("2026-10-30 08:00:00", "2026-10-30 11:00:00", "2026-10-30 14:00:00"):
        sights.append(sm.Sight("sun", utc, sm.body_place("sun", utc).altaz(*truth)[0], 0.05))
    prior = (*sm.offset_latlon(*truth, 120.0, -90.0), 200.0)
    f = sm.fuse(sights, prior, sigma_bias_deg=0.05, sigma_drift_deg=0.05, sigma_up_deg=0.05, sigma_fscale=0.001)
    assert f.accepted and sm.distance_km(f.lat, f.lon, *truth) < 3 * f.sigma_major_km < 60
    # an altitude bias of 0.5 deg common to all: inside the default (bias-aware) sigma
    biased = [sm.Sight(s.body, s.utc, s.alt_deg + 0.5, 0.05) for s in sights]
    f = sm.fuse(biased, prior)
    assert f.mahalanobis(*truth) < 3


def test_fused_lamp_at_constant_altitude_is_refused():
    """A lamp read as the Sun: constant altitude for 3 h while the Sun climbs and sets: chi-square refuses."""
    truth = SOUSSE
    h = sm.body_place("sun", "2026-10-30 11:00:00").altaz(*truth)[0]
    sights = [sm.Sight("sun", utc, h, 0.05) for utc in
              ("2026-10-30 08:00:00", "2026-10-30 09:30:00", "2026-10-30 11:00:00", "2026-10-30 12:30:00",
               "2026-10-30 14:00:00")]
    f = sm.fuse(sights, (*truth, 50.0))
    assert not f.accepted


def _geo_sights(truth, tilt, fscale, bias=0.0, n=12):
    """Exact Moon altitudes over 3 h with a camera-frame tilt of 'up', a focal scale error and a bias added."""
    out = []
    up = np.array([0.0, -1.0, 0.0])
    R = sv.pose(up, 30.0)
    for k in range(n):
        utc = f"2026-10-30 {2 + k // 4:02d}:{(k % 4) * 15:02d}:00"
        h, az, _ = sm.body_place("moon", utc).altaz(*truth)
        ray = R @ sv.enu_vec(h, az)
        a = sm._unit(ray - np.dot(ray, up) * up)
        g = -20.0 * (90.0 - h) / 45.0                       # roughly what the lens gives (deg per unit scale)
        out.append(sm.Sight("moon", utc, h + bias + float(np.dot(tilt, a)) + fscale * g, 0.05, horiz_imu=a,
                            lens="right", dalt_dfscale_deg=g))
    return out


def test_crossing_lines_with_a_tilt_stay_within_sigma():
    """A 0.6 deg tilt of 'up' and a 2 % focal error over a night (the body sweeps 100 deg of azimuth): the
    physical error model keeps the fix within 3 sigma, where a constant-bias model would not."""
    truth = SOUSSE
    sights = _geo_sights(truth, np.array([0.6, 0.0, 0.3]), 0.02, bias=0.2)
    prior = (*sm.offset_latlon(*truth, 100.0, 100.0), 300.0)
    f = sm.fuse(sights, prior)
    assert f.accepted and f.mahalanobis(*truth) < 3, (f.mahalanobis(*truth), sm.distance_km(f.lat, f.lon, *truth))


def test_fit_errors_recovers_the_systematics():
    truth = SOUSSE
    sights = _geo_sights(truth, np.array([0.3, 0.0, 0.2]), 0.01, bias=0.2, n=16)
    err = sm.fit_errors(sights, *truth)
    res = [s.alt_deg - sm.body_place("moon", s.utc).altaz(*truth)[0] for s in sm.correct(sights, err)]
    assert np.sqrt(np.mean(np.square(res))) < 0.1
