"""Lesson 15 — read GPS sentences (NMEA 0183), like NAVERA's gps_node does.

Fill in the TODOs one by one. After each one, run:   python3 nmea_tools.py
"""
import math

# GGA "fix quality" values that are a real satellite fix — the same set as
# NAVERA's gps_pkg/gps_pkg/nodes/gps_node.py (_VALID_GPS_QUAL).
USABLE_QUALITIES = {1, 2, 4, 5}


# TODO 1: the checksum of a sentence body (the text BETWEEN "$" and "*").
#   XOR (^) the character codes (ord) of every character, starting from 0,
#   and return the result as 2 upper-case hexadecimal digits, e.g. "47".
def nmea_checksum(body):
    return None  # replace this line with your code


# TODO 2: True when a whole line is a correct sentence:
#   starts with "$", has a "*" followed by exactly 2 characters,
#   and those 2 characters are the checksum of the body.
def is_valid(line):
    return None  # replace this line with your code


# TODO 3: NMEA "degrees and minutes" -> decimal degrees.
#   "3544.04006", "N"  ->  35 + 44.04006/60 = 35.734001
#   The degrees are everything before the last 2 digits in front of the ".".
#   South ("S") and West ("W") are negative. Unreadable value -> None.
def dm_to_deg(value, hemisphere):
    return None  # replace this line with your code


# TODO 4: read one GGA line into a dictionary with these keys (field number in brackets,
#   after splitting the body on ","):
#     "time" [1] text      "lat" [2]+[3] degrees   "lon" [4]+[5] degrees
#     "quality" [6] int    "sats" [7] int          "hdop" [8] float
#     "alt_msl" [9] float  "geo_sep" [11] float
#   Return None when the line is not valid (TODO 2) or is not a GGA sentence.
#   Empty or unreadable fields become None (use to_float / to_int below).
def parse_gga(line):
    return None  # replace this line with your code


# TODO 5: every usable fix of a log file, in order, as a list of (lat, lon).
#   Usable = parse_gga gives a result, its quality is in USABLE_QUALITIES,
#   and lat and lon are not None.
def usable_fixes(path):
    return None  # replace this line with your code


# TODO 6: the length of a track (list of (lat, lon)) in metres:
#   the sum of the distances between consecutive points (haversine_m below).
def track_length_m(points):
    return None  # replace this line with your code


# ---- you don't need to change anything below this line ----


def to_float(text):
    """Float from an NMEA field, or None when it is empty or not a number
    (the same idea as _field_float in NAVERA's gps_node.py)."""
    try:
        return float(text) if text not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_int(text):
    """Integer from an NMEA field, or None when it is empty or not a whole number."""
    try:
        return int(text) if text not in (None, "") else None
    except (TypeError, ValueError):
        return None


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance in metres between two points (the formula of lesson 6)."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


if __name__ == "__main__":
    example = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
    print("TODO 1  checksum of the textbook example:", nmea_checksum(example), "(should be 47)")
    good = "$" + example + "*47"
    print("TODO 2  is_valid(good line):", is_valid(good), "  is_valid(broken line):", is_valid(good.replace("545", "546")))
    print("TODO 3  dm_to_deg('3544.04006', 'N') =", dm_to_deg("3544.04006", "N"), "(should be 35.734001)")
    print("TODO 4  parse_gga(...) =", parse_gga("$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70"))
    pts = usable_fixes("drive.nmea")
    print("TODO 5  usable fixes in drive.nmea:", None if pts is None else len(pts))
    length = track_length_m(pts) if pts else None
    print("TODO 6  track length:", None if length is None else f"{length:.1f} m")
