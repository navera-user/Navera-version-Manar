"""Celestial position fix: camera boresight (alt/az) + plate-solved RA/Dec → lat/lon.

Pure functions, no ROS, so the geometry can be tested on its own.

Given the direction the sky camera points in the LOCAL frame (altitude above
the horizon, azimuth clockwise from true north) and the same direction in the
EQUATORIAL frame (RA/Dec from astrometry.net), the observer's latitude φ and
local sidereal time follow from

    sin δ          =  sin a·sin φ + cos a·cos φ·cos A          (1)
    cos δ · sin H  = −cos a·sin A                              (2)
    cos δ · cos H  =  sin a·cos φ − cos a·sin φ·cos A          (3)

(1) has TWO latitude solutions in general; both are geometrically valid, so
one direction alone cannot tell them apart. The caller resolves the ambiguity
with a prior latitude (the known operating area) or gets no fix.
"""
import math
from typing import List, Optional, Tuple

from astropy import units as u
from astropy.coordinates import TETE, SkyCoord
from astropy.time import Time


def apparent_radec(ra_icrs_deg: float, dec_icrs_deg: float, utc: str) -> Tuple[float, float]:
    """ICRS (J2000, what astrometry.net reports) → true equator & equinox of date.

    Includes precession (~0.36° in RA over 2000→2026), nutation and aberration,
    so the result pairs with apparent Greenwich sidereal time.
    """
    t = Time(utc, scale="utc")
    c = SkyCoord(ra=ra_icrs_deg * u.deg, dec=dec_icrs_deg * u.deg, frame="icrs")
    app = c.transform_to(TETE(obstime=t))
    return float(app.ra.deg), float(app.dec.deg)


def gast_deg(utc: str) -> float:
    """Greenwich apparent sidereal time, in degrees."""
    return float(Time(utc, scale="utc").sidereal_time("apparent", "greenwich").deg)


def observer_candidates(alt_deg: float, az_deg: float, ra_deg: float, dec_deg: float,
                        gast: float) -> List[Tuple[float, float]]:
    """All (lat, lon) consistent with the boresight pointing at (ra, dec).

    ra/dec must be apparent-of-date (see apparent_radec). Returns 0, 1 or 2
    solutions, longitude in [-180, 180).
    """
    a, A, d = math.radians(alt_deg), math.radians(az_deg), math.radians(dec_deg)
    # (1) as R·sin(φ + ψ) = sin δ
    R = math.hypot(math.sin(a), math.cos(a) * math.cos(A))
    if R < 1e-12:
        return []
    s = math.sin(d) / R
    if abs(s) > 1.0:
        return []
    psi = math.atan2(math.cos(a) * math.cos(A), math.sin(a))
    out = []
    for phi in (math.asin(s) - psi, math.pi - math.asin(s) - psi):
        phi = math.atan2(math.sin(phi), math.cos(phi))       # wrap to (-π, π]
        if abs(phi) > math.pi / 2 + 1e-12:
            continue
        # (2)/(3) give the hour angle with its quadrant
        H = math.atan2(-math.cos(a) * math.sin(A),
                       math.sin(a) * math.cos(phi) - math.cos(a) * math.sin(phi) * math.cos(A))
        lst = ra_deg + math.degrees(H)
        lon = (lst - gast + 540.0) % 360.0 - 180.0
        cand = (math.degrees(phi), lon)
        if not any(abs(cand[0] - c[0]) < 1e-9 and abs(cand[1] - c[1]) < 1e-9 for c in out):
            out.append(cand)
    return out


def _angular_dist_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def choose_candidate(cands: List[Tuple[float, float]], prior_lat: Optional[float],
                     prior_lon: Optional[float] = None,
                     tolerance_deg: float = 5.0) -> Optional[Tuple[float, float]]:
    """Pick the solution consistent with the prior position, or None.

    A candidate is consistent when it lies within ``tolerance_deg`` of the
    prior (great-circle distance with a prior longitude, latitude difference
    otherwise). Exactly one consistent candidate → returned. Zero (the prior
    is wrong or absent) or two (the prior cannot tell them apart) → None:
    an ambiguous fix is not published.
    """
    if not cands:
        return None
    if prior_lat is None or not math.isfinite(prior_lat):
        return cands[0] if len(cands) == 1 else None

    def dist(c):
        if prior_lon is not None and math.isfinite(prior_lon):
            return _angular_dist_deg(prior_lat, prior_lon, c[0], c[1])
        return abs(c[0] - prior_lat)

    ok = [c for c in cands if dist(c) <= tolerance_deg]
    return ok[0] if len(ok) == 1 else None


def local_to_radec(lat_deg: float, lon_deg: float, alt_deg: float, az_deg: float,
                   gast: float) -> Tuple[float, float]:
    """Inverse of observer_candidates (apparent RA/Dec seen at alt/az). For tests."""
    p, a, A = math.radians(lat_deg), math.radians(alt_deg), math.radians(az_deg)
    sd = math.sin(a) * math.sin(p) + math.cos(a) * math.cos(p) * math.cos(A)
    d = math.asin(max(-1.0, min(1.0, sd)))
    H = math.atan2(-math.cos(a) * math.sin(A),
                   math.sin(a) * math.cos(p) - math.cos(a) * math.sin(p) * math.cos(A))
    ra = (gast + lon_deg - math.degrees(H)) % 360.0
    return ra, math.degrees(d)


def boresight_altaz(q_xyzw, mount_elevation_deg: float = 90.0, mount_azimuth_deg: float = 0.0,
                    declination_deg: float = 0.0) -> Tuple[float, float]:
    """Camera boresight (altitude above horizon, azimuth from true north) from the IMU.

    q_xyzw: body orientation in the local ENU frame (sensor_msgs/Imu, REP-103:
    body x forward, y left, z up). The camera is mounted at mount_elevation_deg
    above the body's x-y plane (90 = along the body's up axis) and
    mount_azimuth_deg clockwise from the body's forward axis. A magnetometer
    heading gives MAGNETIC north: declination_deg (east positive) turns it into
    true north.
    """
    x, y, z, w = q_xyzw
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if not n > 0:
        raise ValueError("invalid quaternion")
    x, y, z, w = x / n, y / n, z / n, w / n
    el, az = math.radians(mount_elevation_deg), math.radians(mount_azimuth_deg)
    b = (math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), math.sin(el))   # FLU
    # rotate b by q (body → ENU)
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    e, nn, u = (sum(r[i][j] * b[j] for j in range(3)) for i in range(3))
    alt = math.degrees(math.asin(max(-1.0, min(1.0, u))))
    azimuth = (math.degrees(math.atan2(e, nn)) + declination_deg) % 360.0
    return alt, azimuth
