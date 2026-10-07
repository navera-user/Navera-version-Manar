"""uncertainty.py — the maths of "how sure are we?".

Small functions, each tested by the check. analyse.py uses them on the lesson's dataset.

Run the demo:   python3 uncertainty.py
"""
import math


def mean(values):
    """The average: the sum divided by how many there are.  mean([1, 2, 6]) == 3.0"""
    return None   # TODO 1


def median(values):
    """The middle value once sorted. With an even count, the average of the two middle ones.
    median([7, 1, 3]) == 3      median([4, 1, 3, 2]) == 2.5"""
    return None   # TODO 2  (tip: s = sorted(values); n = len(s); mid = n // 2)


def std(values):
    """The standard deviation (the "population" one: divide by n, not n-1):
         sqrt( mean of (value - mean)^2 )
    std([2, 4, 4, 4, 5, 5, 7, 9]) == 2.0"""
    return None   # TODO 3  (tip: use your mean(), then math.sqrt)


def share_within(errors, radius):
    """The fraction (0.0 to 1.0) of errors that are <= radius."""
    return None   # TODO 4


def fuse(x1, s1, x2, s2):
    """Combine two measurements x1 (sigma s1) and x2 (sigma s2) of the same quantity.

    Weighted average with weights w = 1 / sigma^2 (the more precise, the heavier):
        x = (w1*x1 + w2*x2) / (w1 + w2)
        s = 1 / sqrt(w1 + w2)            <- always smaller than s1 and s2!
    Returns (x, s)."""
    return None, None   # TODO 5


COVARIANCE_TYPE_UNKNOWN = 0         # the values of navera_msgs/PositionEstimate
COVARIANCE_TYPE_DIAGONAL_KNOWN = 2


def make_covariance(sigma_east, sigma_north, sigma_up=None):
    """The 3x3 ENU covariance of PositionEstimate, as 9 numbers (row by row, in m^2),
    and its type.

      - if sigma_east or sigma_north is None: we do NOT know -> ([0.0]*9, COVARIANCE_TYPE_UNKNOWN)
      - otherwise the diagonal holds the VARIANCES (sigma squared), everything else is 0:
            [se^2, 0, 0,
             0, sn^2, 0,
             0, 0, su^2]              type COVARIANCE_TYPE_DIAGONAL_KNOWN
        If sigma_up is None, use 2 x the larger horizontal sigma (as gps_node does).
    """
    return None, None   # TODO 6


# ---- you don't need to change anything below this line (but you can read it!) ----
EARTH_RADIUS_M = 6_371_000.0


def to_local_m(lat, lon, lat0, lon0):
    """(east, north) in metres of (lat, lon) from the reference point (lat0, lon0).
    Flat-Earth approximation (lesson 6): perfect over a few km."""
    m_per_deg = math.pi * EARTH_RADIUS_M / 180.0
    return ((lon - lon0) * m_per_deg * math.cos(math.radians(lat0)), (lat - lat0) * m_per_deg)


def estimate_message(lat, lon, sigma_east, sigma_north):
    """A navera_msgs/PositionEstimate carrying YOUR covariance (lesson 12 contract)."""
    from navera_msgs.msg import PositionEstimate
    m = PositionEstimate()
    m.latitude, m.longitude, m.altitude = float(lat), float(lon), math.nan
    cov, kind = make_covariance(sigma_east, sigma_north)
    m.position_covariance = [float(v) for v in cov]
    m.position_covariance_type = kind
    m.source, m.mode, m.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, True
    m.producer = "academy_lesson_26"
    return m


if __name__ == "__main__":
    throws = [3, 5, 2, 6, 6, 1, 4, 4, 2, 5]          # ten throws of a die
    print("ten dice throws:", throws)
    print(f"  mean   {mean(throws)}")
    print(f"  median {median(throws)}")
    print(f"  std    {std(throws)}")
    print("two measurements: 100 m (sigma 10) and 110 m (sigma 5) ->", fuse(100.0, 10.0, 110.0, 5.0))
    print("covariance for sigma 3 m east, 4 m north:", make_covariance(3.0, 4.0))
