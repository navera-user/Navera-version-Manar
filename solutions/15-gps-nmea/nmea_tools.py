"""Lesson 15 — a robust NMEA 0183 reader (checksum, GGA, GSA, GSV).

Fill in the TODOs one by one. After each one, run:   python3 nmea_tools.py
Rule of a robust parser: NEVER crash on a bad line, NEVER invent a value.
A bad line gives False / None; an empty or impossible field gives None.
"""
import math

# GGA "fix quality" values that are a real satellite fix — the same set as
# NAVERA's gps_pkg/gps_pkg/nodes/gps_node.py (_VALID_GPS_QUAL).
USABLE_QUALITIES = {1, 2, 4, 5}
MAX_SENTENCE_LEN = 80          # NMEA 0183: at most 82 characters including "\r\n"


# TODO 1: the checksum of a sentence body (the text BETWEEN "$" and "*").
#   XOR (^) the character codes (ord) of every character, starting from 0,
#   and return the result as 2 upper-case hexadecimal digits, e.g. "47".
def nmea_checksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


# TODO 2: True when a whole line is a correct sentence, else False (never None, never crash):
#   - remove spaces and "\r\n" at both ends (strip)
#   - at most MAX_SENTENCE_LEN characters, starts with "$", contains "*"
#   - the body (between "$" and the first "*") contains no other "$"
#   - exactly 2 characters after "*", and they equal nmea_checksum(body)
#     (accept lower-case hex digits too: compare with .upper())
def is_valid(line):
    if not isinstance(line, str):
        return False
    line = line.strip()
    if len(line) > MAX_SENTENCE_LEN or not line.startswith("$") or "*" not in line:
        return False
    body, given = line[1:].split("*", 1)
    if "$" in body or len(given) != 2:
        return False
    return nmea_checksum(body) == given.upper()


# TODO 3: NMEA "degrees and minutes" -> decimal degrees.
#   "3546.15064", "N"  ->  35 + 46.15064/60 = 35.769177
#   degrees = int(v // 100), minutes = v - 100 * degrees.
#   S and W are negative. Return None when: the value is unreadable (to_float gives None),
#   the hemisphere is not one of N, S, E, W, or the minutes are not in [0, 60).
def dm_to_deg(value, hemisphere):
    v = to_float(value)
    if v is None or v < 0 or hemisphere not in ("N", "S", "E", "W"):
        return None
    degrees = int(v // 100)
    minutes = v - degrees * 100
    if not 0 <= minutes < 60:
        return None
    d = degrees + minutes / 60.0
    return -d if hemisphere in ("S", "W") else d


def fields(line):
    """The comma-separated fields of a VALID sentence (without "$" and "*hh"), or None."""
    if not is_valid(line):
        return None
    return line.strip()[1:].split("*", 1)[0].split(",")


# TODO 4: read one GGA line into a dictionary with these keys (field number in brackets):
#     "time" [1] text      "lat" [2]+[3] degrees   "lon" [4]+[5] degrees
#     "quality" [6] int    "sats" [7] int          "hdop" [8] float
#     "alt_msl" [9] float  "geo_sep" [11] float
#   Return None when the line is not valid, is not a GGA (f[0] ends with "GGA"),
#   or has fewer than 15 fields. Empty or unreadable fields become None.
def parse_gga(line):
    f = fields(line)
    if f is None or not f[0].endswith("GGA") or len(f) < 15:
        return None
    return {"time": f[1],
            "lat": dm_to_deg(f[2], f[3]),
            "lon": dm_to_deg(f[4], f[5]),
            "quality": to_int(f[6]),
            "sats": to_int(f[7]),
            "hdop": to_float(f[8]),
            "alt_msl": to_float(f[9]),
            "geo_sep": to_float(f[11])}


# TODO 5: read one GSA line ("DOP and active satellites"):
#   $GPGSA,A,3,05,13,...,(12 PRN slots),PDOP,HDOP,VDOP*hh   (NMEA 4.10+ adds a system id at the end)
#   f[1] = "A"/"M" (auto/manual), f[2] = fix mode (1 none, 2 = 2D, 3 = 3D),
#   f[3] .. f[14] = the PRNs USED in the fix (empty slots ""), f[15] PDOP, f[16] HDOP, f[17] VDOP.
#   Return {"mode": int, "prns": [ints, empty slots skipped], "pdop": float, "hdop": float,
#           "vdop": float}  (unreadable numbers -> None), or None when not a valid GSA
#   or fewer than 18 fields.
def parse_gsa(line):
    f = fields(line)
    if f is None or not f[0].endswith("GSA") or len(f) < 18:
        return None
    prns = [to_int(x) for x in f[3:15] if x != ""]
    return {"mode": to_int(f[2]),
            "prns": [p for p in prns if p is not None],
            "pdop": to_float(f[15]), "hdop": to_float(f[16]), "vdop": to_float(f[17])}


# TODO 6: read one GSV line ("satellites in view"). One GSV sentence carries up to 4 satellites:
#   $GPGSV,<number of sentences>,<this sentence number>,<satellites in view>,
#          prn,elevation,azimuth,snr, prn,elevation,azimuth,snr, ...*hh
#   Return {"n_msgs": int, "msg": int, "in_view": int,
#           "sats": [(prn, elev_deg, azim_deg, snr), ...]}  (each value int or None; skip a
#   block whose prn is None). Return None when not a valid GSV or fewer than 4 fields.
#   Careful: the number of fields after f[3] is a multiple of 4 (an extra last field in
#   NMEA 4.10+ is a signal id: ignore what does not make a full block of 4).
def parse_gsv(line):
    f = fields(line)
    if f is None or not f[0].endswith("GSV") or len(f) < 4:
        return None
    sats = []
    rest = f[4:]
    for k in range(0, len(rest) - 3, 4):
        prn, el, az, snr = (to_int(x) for x in rest[k:k + 4])
        if prn is not None:
            sats.append((prn, el, az, snr))
    return {"n_msgs": to_int(f[1]), "msg": to_int(f[2]), "in_view": to_int(f[3]), "sats": sats}


# ---- you don't need to change anything below this line ----


def to_float(text):
    """Float from an NMEA field, or None when it is empty or not a number
    (the same idea as _field_float in NAVERA's gps_node.py)."""
    try:
        v = float(text) if text not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return v if v is None or math.isfinite(v) else None


def to_int(text):
    """Integer from an NMEA field, or None when it is empty or not a whole number."""
    try:
        return int(text) if text not in (None, "") else None
    except (TypeError, ValueError):
        return None


def sentence_type(line):
    """'GGA', 'RMC', 'GSA', 'GSV'... of a valid sentence, else None."""
    f = fields(line)
    return f[0][-3:] if f else None


def utc_seconds(hhmmss):
    """'052004.00' -> seconds since midnight (float), or None."""
    try:
        return int(hhmmss[0:2]) * 3600 + int(hhmmss[2:4]) * 60 + float(hhmmss[4:])
    except (TypeError, ValueError, IndexError):
        return None


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance in metres between two points (the formula of lesson 6)."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def read_log(path):
    """All lines of a log, decoded like gps_node does (bad bytes become '�')."""
    with open(path, "rb") as f:
        return f.read().decode("ascii", errors="replace").splitlines()


if __name__ == "__main__":
    example = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
    print("TODO 1  checksum of the textbook example:", nmea_checksum(example), "(should be 47)")
    good = "$" + example + "*47"
    print("TODO 2  is_valid(good):", is_valid(good), "  is_valid(changed digit):",
          is_valid(good.replace("545", "546")), "(should be True False)")
    print("TODO 3  dm_to_deg('3546.15064', 'N') =", dm_to_deg("3546.15064", "N"),
          "(should be 35.769177)   dm_to_deg('3572.1', 'N') =", dm_to_deg("3572.1", "N"), "(None)")
    print("TODO 4  parse_gga:", parse_gga("$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,"
                                          "95.3,M,32.1,M,,*70"))
    print("TODO 5  parse_gsa:", parse_gsa("$GPGSA,A,3,02,05,09,13,15,20,23,24,30,,,,1.53,0.85,1.27*02"))
    print("TODO 6  parse_gsv:", parse_gsv("$GPGSV,3,1,12,02,62,012,47,05,33,047,39,07,18,095,35,"
                                          "09,47,128,43*70"))
