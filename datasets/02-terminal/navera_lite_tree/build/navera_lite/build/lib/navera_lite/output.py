"""navera_lite/output.py — the messenger: a GPS_INPUT message for the autopilot.

Part of NAVERA Lite, the course's teaching stack (mission 31). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 31.
"""


def crc_x25(data, crc=65535):
    """The MAVLink checksum."""
    ...


def decode_gps_input(payload):
    """Read a message back."""
    ...
