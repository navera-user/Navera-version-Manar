"""gnss_fix.py — how a GNSS receiver turns pseudoranges into a position (lab 1).

The scene is simulated: a receiver on the coast at Sousse (Tunisia) sees up to 8 satellites. Each
satellite gives a PSEUDORANGE, the distance measured with the receiver's own (wrong) clock:

    rho_i = |s_i - r| + c * b + noise          s_i: satellite position, r: receiver position,
                                               b: receiver clock bias (s), c: speed of light
Unknowns: x, y, z of r and the clock bias b  ->  4 unknowns  ->  at least 4 satellites.
The solver linearises the equations around a guess and improves it (Gauss–Newton),
exactly the idea of a real receiver. Earth is a sphere here, to keep the maths short.

Change the settings below, save (Ctrl+S) and run:      python3 gnss_fix.py
"""
import math

import numpy as np

# ---- settings you may change ----------------------------------------------------
USE_SATELLITES = 8        # how many satellites the receiver tracks (0 to 8)
CLOCK_BIAS_US = 0.5       # the receiver clock is wrong by this many microseconds
NOISE_M = 3.0             # random error of each pseudorange (1 sigma, metres)
SPOOF_EAST_M = 0.0        # a spoofer fakes every signal to move you this many metres east
# ----------------------------------------------------------------------------------

C_MPS = 299_792_458.0                       # speed of light (m/s)
EARTH_R_M = 6_371_000.0                     # spherical Earth
ORBIT_R_M = 26_560_000.0                    # GPS orbit radius (about 20 200 km altitude)
TRUE_LAT, TRUE_LON, TRUE_ALT_M = 35.825, 10.640, 15.0      # Sousse, on the coast
SKY = [(10, 70), (80, 35), (150, 50), (200, 20),            # (azimuth, elevation) in degrees
       (260, 40), (320, 25), (40, 15), (120, 18)]


def enu_axes(lat_deg, lon_deg):
    """Unit vectors east, north, up of the local frame, in Earth-centred coordinates."""
    p, l = math.radians(lat_deg), math.radians(lon_deg)
    e = np.array([-math.sin(l), math.cos(l), 0.0])
    n = np.array([-math.sin(p) * math.cos(l), -math.sin(p) * math.sin(l), math.cos(p)])
    u = np.array([math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p)])
    return e, n, u


def position_ecef(lat_deg, lon_deg, alt_m):
    _, _, u = enu_axes(lat_deg, lon_deg)
    return (EARTH_R_M + alt_m) * u


def satellites(n_sats):
    """Earth-centred positions (n, 3) of the first n satellites of SKY, seen from Sousse."""
    r = position_ecef(TRUE_LAT, TRUE_LON, TRUE_ALT_M)
    e, n, u = enu_axes(TRUE_LAT, TRUE_LON)
    out = []
    for az, el in SKY[:n_sats]:
        a, b = math.radians(az), math.radians(el)
        d = math.cos(b) * math.sin(a) * e + math.cos(b) * math.cos(a) * n + math.sin(b) * u
        k = -r @ d + math.sqrt((r @ d) ** 2 - r @ r + ORBIT_R_M ** 2)   # |r + k d| = orbit radius
        out.append(r + k * d)
    return np.array(out).reshape(-1, 3)


def pseudoranges(sats, clock_bias_us, noise_m, spoof_east_m=0.0, seed=1):
    """What the receiver measures. A spoofer computes them for a FAKE position."""
    rng = np.random.default_rng(seed)
    e, _, _ = enu_axes(TRUE_LAT, TRUE_LON)
    r = position_ecef(TRUE_LAT, TRUE_LON, TRUE_ALT_M) + spoof_east_m * e
    geometric = np.linalg.norm(sats - r, axis=1)
    return geometric + C_MPS * clock_bias_us * 1e-6 + rng.normal(0.0, noise_m, len(sats))


def solve(sats, rho, iterations=8):
    """Gauss–Newton least squares for (x, y, z, c*b). Returns a dict."""
    if len(rho) < 4:
        return {"ok": False, "message": f"{len(rho)} satellite(s) for 4 unknowns (x, y, z, clock bias): "
                                        "the system is underdetermined — NO FIX"}
    x = np.zeros(4)                                  # start at the centre of the Earth, bias 0
    for _ in range(iterations):
        diff = sats - x[:3]
        ranges = np.linalg.norm(diff, axis=1)
        H = np.hstack([-diff / ranges[:, None], np.ones((len(rho), 1))])   # d rho / d (x, y, z, cb)
        dx, *_ = np.linalg.lstsq(H, rho - (ranges + x[3]), rcond=None)
        x = x + dx
    ranges = np.linalg.norm(sats - x[:3], axis=1)
    resid = rho - (ranges + x[3])
    Q = np.linalg.inv(H.T @ H)
    return {"ok": True, "xyz": x[:3], "clock_bias_m": float(x[3]),
            "residual_rms_m": float(np.sqrt(np.mean(resid ** 2))),
            "pdop": float(math.sqrt(Q[0, 0] + Q[1, 1] + Q[2, 2])),
            "message": "fix"}


def error_enu(xyz):
    """Error (east, north, up) of a solved position, in metres."""
    e, n, u = enu_axes(TRUE_LAT, TRUE_LON)
    d = xyz - position_ecef(TRUE_LAT, TRUE_LON, TRUE_ALT_M)
    return float(d @ e), float(d @ n), float(d @ u)


def run(n_sats=USE_SATELLITES, clock_bias_us=CLOCK_BIAS_US, noise_m=NOISE_M, spoof_east_m=SPOOF_EAST_M):
    sats = satellites(n_sats)
    rho = pseudoranges(sats, clock_bias_us, noise_m, spoof_east_m)
    res = solve(sats, rho)
    if res["ok"]:
        de, dn, du = error_enu(res["xyz"])
        res.update(east_err_m=de, north_err_m=dn, up_err_m=du, horizontal_err_m=math.hypot(de, dn))
    return res


if __name__ == "__main__":
    print(f"satellites: {USE_SATELLITES}   clock bias: {CLOCK_BIAS_US} µs "
          f"(= {C_MPS * CLOCK_BIAS_US * 1e-6:.1f} m)   noise: {NOISE_M} m   spoof: {SPOOF_EAST_M} m east")
    r = run()
    if not r["ok"]:
        print(r["message"])
    else:
        print(f"clock bias found      : {r['clock_bias_m']:9.1f} m")
        print(f"error east/north/up   : {r['east_err_m']:9.1f} {r['north_err_m']:9.1f} {r['up_err_m']:9.1f} m")
        print(f"horizontal error      : {r['horizontal_err_m']:9.1f} m")
        print(f"residual RMS          : {r['residual_rms_m']:9.1f} m   (how badly the measurements disagree)")
        print(f"PDOP (geometry factor): {r['pdop']:9.2f}")
