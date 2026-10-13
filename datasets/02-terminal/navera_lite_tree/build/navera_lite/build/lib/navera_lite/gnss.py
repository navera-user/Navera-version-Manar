"""navera_lite/gnss.py — NMEA sentences, DOP, the GPS receiver's decision.

Part of NAVERA Lite, the course's teaching stack (mission 15). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 15.
"""


def nmea_checksum(body):
    """The checksum of a sentence."""
    ...


def parse_gga(line):
    """One GGA sentence as a dict."""
    ...


def fix_decision(gga):
    """Use this fix or not, and why."""
    ...
