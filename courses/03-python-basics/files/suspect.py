"""suspect.py — a small helper module found on a shared drive (Going further of lab 3).

Its author swears every function returns what its name says (m, s, m/s). One of them does not.
Write tests (plain `assert` lines in a file test_suspect.py, run with `python3 -m pytest -q test_suspect.py`)
that EXPOSE the wrong one, using physics you know and NAVERA Lite's finished functions.
Do not read the code first: find it with tests, as you would in a real code review.
"""
from navera_lite.vehicle import VEHICLES


def leg_time_s(distance_m, gs_mps):
    """Seconds to fly distance_m at a ground speed of gs_mps."""
    return distance_m / gs_mps


def mean_speed_mps(distance_m, duration_min):
    """Mean speed (m/s) of a leg of distance_m flown in duration_min minutes."""
    return distance_m / (duration_min * 60.0)


def max_speed_mps(vehicle_type):
    """The maximum speed (m/s) of a vehicle type ("drone", "plane", "boat", "robot")."""
    return round(VEHICLES[vehicle_type] * 3600.0 / 1852.0, 1)


def climb_time_s(height_m, climb_rate_mps):
    """Seconds to climb height_m metres at climb_rate_mps."""
    return height_m / climb_rate_mps
