"""Where the camera points, from the phone fixed beside it.

The phone lies flat, screen up, top edge towards the car's front, the camera next to it
pointing straight up (the phone's screen normal). The browser gives the phone's tilt as
beta (front/back) and gamma (left/right), in degrees.

At the zenith the sky's declination is the latitude and its right ascension minus the
sidereal time is the longitude: no heading is needed. The heading only turns a small tilt
into a direction, so a poor heading costs (tilt x heading error), not 111 km per degree.
"""
import math
from typing import Optional, Tuple


def boresight(beta_deg: float, gamma_deg: float, heading_deg: Optional[float]) -> Tuple[float, float, float]:
    """(altitude, azimuth, off_vertical) of the camera axis in degrees.

    heading_deg: compass bearing of the phone's top edge (GPS course while driving straight,
    else the compass); None is taken as north, which only matters when the tilt is large.
    """
    b, g = math.radians(beta_deg), math.radians(gamma_deg)
    hx, hy = math.sin(g), -math.cos(g) * math.sin(b)         # horizontal part of the axis, phone frame
    up = max(-1.0, min(1.0, math.cos(g) * math.cos(b)))
    off_vertical = math.degrees(math.acos(up))
    h = math.radians(heading_deg if heading_deg is not None else 0.0)
    east = hx * math.cos(h) + hy * math.sin(h)
    north = -hx * math.sin(h) + hy * math.cos(h)
    az = math.degrees(math.atan2(east, north)) % 360.0 if (east or north) else 0.0
    return 90.0 - off_vertical, az, off_vertical


def best_heading(course_deg: Optional[float], speed_mps: Optional[float],
                 compass_deg: Optional[float], min_speed: float = 3.0) -> Tuple[Optional[float], str]:
    """The GPS course when the car is moving, else the compass, else nothing."""
    if course_deg is not None and speed_mps is not None and speed_mps >= min_speed:
        return course_deg % 360.0, "gps course"
    if compass_deg is not None:
        return compass_deg % 360.0, "phone compass"
    return None, "none"
