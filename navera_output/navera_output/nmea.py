"""NMEA 0183 sentences (GGA + RMC) for the GPS-emulation output.

GGA quality: 1 = GPS fix, 6 = estimated (dead reckoning / non-GNSS), 0 = no fix.
RMC status A/V and mode indicator A (autonomous) / E (estimated) / N (not valid).
HDOP is derived from the stated horizontal accuracy with the same 2 m user range
error assumed by gps_node (sigma = 2 m x HDOP).
"""
import math
from datetime import datetime

from navera_output.policy import KIND_ESTIMATED, KIND_FIX, Output

UERE_M = 2.0
KNOTS_PER_MPS = 1.0 / 0.514444


def checksum(body: str) -> str:
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{cs:02X}"


def sentence(body: str) -> str:
    return f"${body}*{checksum(body)}\r\n"


def _latlon(lat: float, lon: float):
    """Decimal degrees → ('ddmm.mmmmm', 'N'|'S', 'dddmm.mmmmm', 'E'|'W')."""
    def conv(v, deg_digits):
        a = abs(v)
        d = int(a)
        m = (a - d) * 60.0
        if round(m, 5) >= 60.0:          # carry, e.g. 35.9999999999
            d, m = d + 1, 0.0
        return f"{d:0{deg_digits}d}{m:08.5f}"
    return (conv(lat, 2), "N" if lat >= 0 else "S",
            conv(lon, 3), "E" if lon >= 0 else "W")


def _hhmmss(t: datetime) -> str:
    return t.strftime("%H%M%S.") + f"{t.microsecond // 10000:02d}"


def gga(out: Output, t_utc: datetime) -> str:
    if out.kind not in (KIND_FIX, KIND_ESTIMATED):
        return sentence(f"GPGGA,{_hhmmss(t_utc)},,,,,0,00,,,M,,M,,")
    la, ns, lo, ew = _latlon(out.lat, out.lon)
    quality = 1 if out.kind == KIND_FIX else 6
    sats = f"{out.satellites:02d}" if out.satellites is not None else ""
    hdop = f"{min(out.sigma_h_m / UERE_M, 99.9):.1f}" if math.isfinite(out.sigma_h_m) else ""
    msl, sep = out.alt_msl_m, out.geoid_sep_m
    if not math.isfinite(msl) and math.isfinite(out.alt_ellipsoid_m):
        msl, sep = out.alt_ellipsoid_m, 0.0       # geoid unknown: report the ellipsoid
    alt = f"{msl:.1f}" if math.isfinite(msl) else ""
    sep_s = f"{sep:.1f}" if math.isfinite(sep) else ""
    return sentence(f"GPGGA,{_hhmmss(t_utc)},{la},{ns},{lo},{ew},{quality},{sats},{hdop},"
                    f"{alt},M,{sep_s},M,,")


def rmc(out: Output, t_utc: datetime, speed_mps: float = math.nan,
        course_deg: float = math.nan) -> str:
    date = t_utc.strftime("%d%m%y")
    if out.kind not in (KIND_FIX, KIND_ESTIMATED):
        return sentence(f"GPRMC,{_hhmmss(t_utc)},V,,,,,,,{date},,,N")
    la, ns, lo, ew = _latlon(out.lat, out.lon)
    spd = f"{speed_mps * KNOTS_PER_MPS:.2f}" if math.isfinite(speed_mps) else ""
    crs = f"{course_deg % 360.0:.1f}" if math.isfinite(course_deg) else ""
    mode = "A" if out.kind == KIND_FIX else "E"
    return sentence(f"GPRMC,{_hhmmss(t_utc)},A,{la},{ns},{lo},{ew},{spd},{crs},{date},,,{mode}")
