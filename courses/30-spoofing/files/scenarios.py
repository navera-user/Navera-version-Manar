"""scenarios.py — the attacks of lab 30, as timed fixes (the red team's script: read it, you don't need to change it).

A survey drone flies NORTH along the coast near Sousse at 15 m/s (NAVERA's test area). The spoofer pushes the
GPS position EAST, out over the sea. Two sources feed the judge:

    GPS        one fix per second, measured at t = 0, 1, 2 … s, received 0.05 s later; it states σ 3 m;
               its error is Gaussian noise, σ 3 m on each axis — plus the spoofer's offset (H1)
    day vision one fix every 2 s, measured at t = 0.1, 2.1, 4.1 … s (0.1 s after a GPS fix), received 0.5 s
               after it was measured; it sees the TRUE position with Gaussian noise σ 15 m on each axis and
               states σ 15 m (the simulator's TARGET accuracy, not a measured one) — or, in the "…_novision"
               attacks, states NOTHING (covariance type UNKNOWN: a position of unknown accuracy)

build(name) returns the rows in the order the judge RECEIVES them:
    (t_recv_s, Estimate, offset_m, true_lat, true_lon)
offset_m = how far east the spoofer put that GPS fix (0 for an honest fix and for vision fixes).
Every run of one attack gives the same numbers (the noise has a fixed seed).
"""
import math

import numpy as np

from navera_lite.estimate import COV_DIAGONAL_KNOWN, COV_UNKNOWN, Estimate
from navera_lite.geo import offset

START = (35.7800, 10.6600)     # lat, lon of the drone at t = 0 (off the coast of Sousse)
SPEED_MPS = 15.0               # the drone flies north at this speed
GPS_SIGMA_M = 3.0              # GPS noise and stated σ (m, each axis)
VISION_SIGMA_M = 15.0          # vision noise and stated σ (m, each axis)
VISION_PERIOD_S = 2.0          # one vision fix every 2 s
VISION_AFTER_GPS_S = 0.1       # the photo is taken 0.1 s after the GPS fix
VISION_LATENCY_S = 0.5         # and its position reaches the judge 0.5 s later
GPS_LATENCY_S = 0.05

ATTACKS = {
    # name: (description, seconds, vision states σ?, spoofer offset east (m) as a function of t, GPS on?)
    "jump": ("GPS jumps 2 km east at t = 20 s and stays there 30 s; vision of UNKNOWN accuracy", 70, False,
             lambda t: 2000.0 if 20 <= t < 50 else 0.0, None),
    "patient": ("the same 2 km jump, but the spoofer stays 100 s (t = 20–120 s); vision of UNKNOWN accuracy", 140,
                False, lambda t: 2000.0 if 20 <= t < 120 else 0.0, None),
    "patient_vision": ("the patient 2 km spoof (t = 20–120 s), vision states σ 15 m", 140, True,
                       lambda t: 2000.0 if 20 <= t < 120 else 0.0, None),
    "drift": ("GPS pulled east slowly (DRIFT_MPS) from t = 10 s until t = 80 s; vision states σ 15 m", 100,
              True, None, None),
    "drift_novision": ("the same slow drift, vision of UNKNOWN accuracy", 100, False, None, None),
    "jamspoof": ("GPS jammed t = 20–100 s, back 2 km east (spoofed) until 120 s, then true; vision states σ 15 m",
                 140, True, lambda t: 2000.0 if 100 <= t < 120 else 0.0, lambda t: not 20 <= t < 100),
    "jamspoof_novision": ("jam, then spoof, vision of UNKNOWN accuracy", 140, False,
                          lambda t: 2000.0 if 100 <= t < 120 else 0.0, lambda t: not 20 <= t < 100),
    "glitch": ("an honest GPS; two WRONG vision matches: 300 m off at t = 40.1 s, 2 km off at t = 60.1 s", 80, True,
               lambda t: 0.0, None),
    "creep": ("a careful spoofer: GPS held CREEP_M east from t = 10 s to the end; vision states σ 15 m", 120,
              True, None, None),
}
NAMES = list(ATTACKS)
DRIFT_MPS = 4.0                # the "drift" attacks
CREEP_M = 30.0                 # the "creep" attack
SEED = 30


def truth(t_s):
    """The true (lat, lon) of the drone at t_s."""
    return offset(START[0], START[1], 0.0, SPEED_MPS * t_s)


def spoof_offset(name, t_s, drift_mps=None, creep_m=None):
    """How far east (m) the spoofer puts the GPS fix measured at t_s."""
    if name in ("drift", "drift_novision"):
        u = DRIFT_MPS if drift_mps is None else drift_mps
        return u * (t_s - 10.0) if 10.0 <= t_s < 80.0 else 0.0
    if name == "creep":
        return (CREEP_M if creep_m is None else creep_m) if t_s >= 10.0 else 0.0
    return ATTACKS[name][3](t_s)


def build(name, seed=SEED, drift_mps=None, creep_m=None):
    """The rows of one attack (see the file's docstring), sorted by the time the judge receives them."""
    if name not in ATTACKS:
        raise ValueError(f"unknown attack {name!r}; the attacks are: {', '.join(NAMES)}")
    _, seconds, vision_states, _, gps_on = ATTACKS[name]
    rng = np.random.default_rng(seed)
    rows = []
    gps_cov = (GPS_SIGMA_M ** 2, 0.0, 0.0, 0.0, GPS_SIGMA_M ** 2, 0.0, 0.0, 0.0, 36.0)
    vis_cov = (VISION_SIGMA_M ** 2, 0.0, 0.0, 0.0, VISION_SIGMA_M ** 2, 0.0, 0.0, 0.0, 400.0)
    for i in range(int(seconds) + 1):
        t = float(i)
        ge, gn = rng.normal(0.0, GPS_SIGMA_M, 2)        # drawn every second, so all attacks share the noise
        ve, vn = rng.normal(0.0, VISION_SIGMA_M, 2)
        if gps_on is None or gps_on(t):
            off = spoof_offset(name, t, drift_mps, creep_m)
            lat0, lon0 = truth(t)
            lat, lon = offset(lat0, lon0, ge + off, gn)
            rows.append((t + GPS_LATENCY_S, Estimate("gps", lat, lon, t, cov=gps_cov, cov_type=COV_DIAGONAL_KNOWN,
                                                     alt_m=120.0), off, lat0, lon0))
        if i % int(VISION_PERIOD_S) == 0:
            tv = t + VISION_AFTER_GPS_S
            lat0, lon0 = truth(tv)
            wrong = 0.0
            if name == "glitch":
                wrong = {40: 300.0, 60: 2000.0}.get(i, 0.0)
            lat, lon = offset(lat0, lon0, ve + wrong, vn)
            est = Estimate("day", lat, lon, tv, cov=vis_cov if vision_states else (0.0,) * 9,
                           cov_type=COV_DIAGONAL_KNOWN if vision_states else COV_UNKNOWN)
            rows.append((tv + VISION_LATENCY_S, est, 0.0, lat0, lon0))
    rows.sort(key=lambda r: r[0])
    return rows


def describe(name, drift_mps=None, creep_m=None):
    """One line about the attack, with the drift speed or the creep offset used."""
    u = DRIFT_MPS if drift_mps is None else drift_mps
    c = CREEP_M if creep_m is None else creep_m
    return ATTACKS[name][0].replace("DRIFT_MPS", f"at {u:g} m/s").replace("CREEP_M", f"{c:g} m")
