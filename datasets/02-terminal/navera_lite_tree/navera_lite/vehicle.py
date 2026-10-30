"""navera_lite/vehicle.py — vehicles, wind triangle, endurance.

Part of NAVERA Lite, the course's teaching stack (mission 03). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 03.
"""


def heading_vector(heading_deg):
    """Unit vector (east, north) of a heading."""
    ...


def ground_velocity(airspeed_mps, heading_deg, wind_e=0.0, wind_n=0.0):
    """Velocity over the ground."""
    ...


def heading_for_track(track_deg, tas_mps, wind_e, wind_n):
    """Heading to hold a track in wind."""
    ...


def endurance_s(battery_wh, power_w, reserve=0.2):
    """Flight time on one battery."""
    ...
