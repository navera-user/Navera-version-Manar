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
import os
from typing import List, Optional, Tuple

import numpy as np
from astropy import units as u
from astropy.coordinates import TETE, SkyCoord
from astropy.time import Time
from astropy.utils import iers

# NAVERA runs offline in operation. Left alone, astropy downloads the IERS Earth-orientation table (UT1-UTC,
# polar motion) and, offline with no cached copy, refuses every 2026 date (IERSRangeError: no celestial fix at
# all). The table is fetched with the map before departure (navera_tools/fetch_iers.py) to NAVERA_IERS_FILE;
# without it the bundled IERS-B table is extrapolated (UT1-UTC is under 0.9 s by definition: < 0.4 km).
IERS_FILE = os.path.expanduser(os.environ.get("NAVERA_IERS_FILE", "~/navera_data/iers/finals2000A.all"))


def configure_offline_iers(path: str = IERS_FILE) -> str:
    """Never download at run time; use the pre-flight IERS-A file if there is one. Returns the source used."""
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None
    iers.conf.iers_degraded_accuracy = "warn"
    if os.path.exists(path):
        try:
            iers.earth_orientation_table.set(iers.IERS_A.open(path))
            return f"IERS-A file {path}"
        except Exception as e:                     # a damaged file must not stop the fix
            return f"bundled IERS-B (could not read {path}: {e})"
    return "bundled IERS-B (no pre-flight IERS-A file)"


IERS_SOURCE = configure_offline_iers()


def obs_time(utc) -> Time:
    """Time of an observation with UT1-UTC always set: from the IERS table, or past its ends its edge value
    (UT1-UTC drifts < 1 ms/day and stays under 0.9 s: < 0.4 km) instead of an IERSRangeError offline.
    """
    t = Time(utc, scale="utc")
    dut1, _ = iers.earth_orientation_table.get().ut1_utc(t, return_status=True)
    t.delta_ut1_utc = dut1
    return t


def apparent_radec(ra_icrs_deg: float, dec_icrs_deg: float, utc: str) -> Tuple[float, float]:
    """ICRS (J2000, what astrometry.net reports) → true equator & equinox of date.

    Includes precession (~0.36° in RA over 2000→2026), nutation and aberration,
    so the result pairs with apparent Greenwich sidereal time.
    """
    t = obs_time(utc)
    c = SkyCoord(ra=ra_icrs_deg * u.deg, dec=dec_icrs_deg * u.deg, frame="icrs")
    app = c.transform_to(TETE(obstime=t))
    return float(app.ra.deg), float(app.dec.deg)


def gast_deg(utc: str) -> float:
    """Greenwich apparent sidereal time, in degrees."""
    return float(obs_time(utc).sidereal_time("apparent", "greenwich").deg)


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
                     tolerance_deg: float = 2.0) -> Optional[Tuple[float, float]]:
    """Pick the solution consistent with the prior position, or None.

    A candidate is consistent when it lies within ``tolerance_deg`` (2 deg = 222 km; 5 deg
    let attitude-transient fixes 555 km off through) of the
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


# ── compass-free fix for a narrow star camera (B11) ─────────────────────────────────────────────────────────────
# The plate solve gives the camera's WHOLE rotation among the stars (R_icrs_cam), not only where its centre points.
# With the camera's full mounting on the vehicle (R_cam_body) and the vehicle's 'up' from its IMU (roll and pitch,
# gravity-referenced, no heading), the zenith among the stars is R_icrs_cam @ up_cam: its declination is the
# latitude and its right ascension minus the sidereal time the longitude. One answer, no prior, no compass, no
# magnetic declination; the hour-angle singularity of the one-direction method (B11) does not exist.
# Optical frame of the camera: x to the image's right, y down the image, z along the optical axis.

def camera_rotation_from_wcs(header, step_px: float = 20.0) -> np.ndarray:
    """R_icrs_cam (3x3, columns = the camera's optical x, y, z axes in ICRS) from a plate solution (FITS WCS
    header with IMAGEW/IMAGEH, or NAXIS1/NAXIS2). Raises ValueError for a mirrored solution (parity flipped:
    not a camera picture as taken) or a header without a usable solution."""
    from astropy.wcs import WCS
    w = WCS(header)
    width = header.get("IMAGEW") or header.get("NAXIS1")
    height = header.get("IMAGEH") or header.get("NAXIS2")
    if not width or not height:
        raise ValueError("WCS header without the image size (IMAGEW/IMAGEH)")
    cx, cy = (float(width) - 1.0) / 2.0, (float(height) - 1.0) / 2.0

    def vec(px, py):
        c = w.pixel_to_world(px, py)
        ra, dec = math.radians(float(c.ra.deg)), math.radians(float(c.dec.deg))
        return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])

    z = vec(cx, cy)
    xr = vec(cx + step_px, cy) - vec(cx - step_px, cy)
    yd = vec(cx, cy + step_px) - vec(cx, cy - step_px)
    x = xr - z * (z @ xr)
    y = yd - z * (z @ yd)
    x /= np.linalg.norm(x)
    y /= np.linalg.norm(y)
    if float(np.cross(x, y) @ z) < 0.0:
        raise ValueError("mirrored plate solution (parity flipped)")
    U, _, Vt = np.linalg.svd(np.column_stack([x, y, z]))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        raise ValueError("not a rotation")
    return R


def zenith_position(z_icrs, utc: str) -> Tuple[float, float]:
    """(lat, lon) of the observer whose zenith is the ICRS unit vector z_icrs at utc (shared by the 360 and the
    narrow-camera compass-free fixes)."""
    z = np.asarray(z_icrs, float) / np.linalg.norm(z_icrs)
    ra, dec = math.degrees(math.atan2(z[1], z[0])) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, float(z[2])))))
    ra_a, dec_a = apparent_radec(ra, dec, utc)
    return dec_a, (ra_a - gast_deg(utc) + 540.0) % 360.0 - 180.0


def zenith_fix(R_icrs_cam, up_cam, utc: str) -> Tuple[float, float]:
    """(lat, lon) from the plate-solved camera rotation and 'up' in the camera's optical frame (B11)."""
    return zenith_position(np.asarray(R_icrs_cam, float) @ np.asarray(up_cam, float), utc)


def mount_rotation(elevation_deg: float, azimuth_deg: float, roll_deg: float) -> np.ndarray:
    """R_cam_body (optical-frame vector = R @ body FLU vector) of a star camera mounted on the vehicle.

    elevation / azimuth: as boresight_altaz (the optical axis above the body's x-y plane, clockwise from the
    body's forward axis). roll_deg: the turn of the image about its optical axis; 0 = the image's top edge towards
    the body's up axis (for a camera looking straight up, elevation >= 89.9: towards the body's front); positive =
    right-handed about the optical axis (the top edge turns clockwise seen from behind the camera). It is set when
    the camera is mounted: measure it (one plate solve on a level vehicle with a known heading), never assume it.
    """
    el, az, rl = (math.radians(v) for v in (elevation_deg, azimuth_deg, roll_deg))
    b = np.array([math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), math.sin(el)])
    ref = np.array([0.0, 0.0, 1.0]) if abs(b[2]) < math.sin(math.radians(89.9)) else np.array([1.0, 0.0, 0.0])
    top = ref - b * (b @ ref)
    top /= np.linalg.norm(top)
    # turn the top edge about the optical axis (right-handed about b)
    top = top * math.cos(rl) + np.cross(b, top) * math.sin(rl) + b * (b @ top) * (1 - math.cos(rl))
    y = -top
    x = np.cross(y, b)
    return np.vstack([x, y, b])


def up_in_camera(q_xyzw, R_cam_body) -> np.ndarray:
    """'up' (unit) in the camera's optical frame from the vehicle IMU's orientation (only its roll and pitch matter:
    a heading error turns the body about 'up' and leaves it unchanged)."""
    x, y, z, w = (float(v) for v in q_xyzw)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if not n > 0:
        raise ValueError("invalid quaternion")
    x, y, z, w = x / n, y / n, z / n, w / n
    # third row of R_enu_body = 'up' (ENU z) in body coordinates
    up_body = np.array([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)])
    v = np.asarray(R_cam_body, float) @ up_body
    return v / np.linalg.norm(v)
