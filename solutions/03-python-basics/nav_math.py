# Lab 3 — navigation maths in Python.
#
# Each function below has a TODO. Replace the line  raise NotImplementedError(...)
# by your code, save (Ctrl+S) and run:      python3 nav_math.py
# The demo at the bottom of the file prints what your functions answer.
#
# Remember: a function RETURNS its answer with `return`. Printing is not returning!

import math

# ---------------------------------------------------------------------------
# Part 1 — speeds, distances, times
# ---------------------------------------------------------------------------


def kmh_to_ms(speed_kmh):
    """Convert a speed from km/h to m/s.   Example: 36 km/h -> 10.0 m/s.
    (1 km = 1000 m and 1 h = 3600 s, so divide by 3.6)"""
    return speed_kmh / 3.6


def ms_to_kmh(speed_ms):
    """Convert a speed from m/s to km/h.   Example: 10 m/s -> 36.0 km/h."""
    return speed_ms * 3.6


def distance_m(speed_ms, time_s):
    """Distance (m) covered at speed_ms (m/s) during time_s (s).   Example: 15 m/s for 60 s -> 900 m."""
    return speed_ms * time_s


def travel_time_s(dist_m, speed_ms):
    """Time (s) needed to cover dist_m (m) at speed_ms (m/s).   Example: 900 m at 15 m/s -> 60 s.
    If the speed is 0 or negative, the drone never arrives: return None."""
    if speed_ms <= 0:
        return None
    return dist_m / speed_ms


# ---------------------------------------------------------------------------
# Part 2 — the battery
# ---------------------------------------------------------------------------


def flight_time_min(battery_wh, power_w, reserve_percent=20):
    """How many MINUTES the drone can fly.
    battery_wh       energy in the battery, in watt-hours (Wh)
    power_w          power the drone uses while flying, in watts (W)
    reserve_percent  part of the battery we never use (kept to land safely)
    Example: 100 Wh, 400 W, 20 % reserve -> 80 Wh usable -> 0.2 h -> 12.0 minutes."""
    usable_wh = battery_wh * (100 - reserve_percent) / 100
    hours = usable_wh / power_w
    return hours * 60


def battery_status(percent):
    """A word for the pilot:
         "OK"        when percent is 50 or more
         "LOW"       when percent is 20 or more (but less than 50)
         "LAND NOW"  below 20"""
    if percent >= 50:
        return "OK"
    elif percent >= 20:
        return "LOW"
    else:
        return "LAND NOW"


# ---------------------------------------------------------------------------
# Part 3 — the 600 m circle
# ---------------------------------------------------------------------------
# Positions are in metres from the take-off point ("home"):
#   x = metres to the EAST (negative = west),  y = metres to the NORTH (negative = south).

HOME_RADIUS_M = 600


def distance_from_home_m(x_m, y_m):
    """Straight-line distance (m) from home (0, 0) to (x_m, y_m).
    Pythagoras: distance² = x² + y².   Example: (300, 400) -> 500.0"""
    return math.sqrt(x_m ** 2 + y_m ** 2)


def inside_circle(x_m, y_m, radius_m=HOME_RADIUS_M):
    """True when (x_m, y_m) is inside the circle of radius radius_m around home
    (exactly ON the circle counts as inside), False otherwise."""
    return distance_from_home_m(x_m, y_m) <= radius_m


def status_line(name, x_m, y_m):
    """One line for the operator screen, built with an f-string, EXACTLY like this:
         "drone-1 is 500 m from home: INSIDE"
         "drone-2 is 707 m from home: OUTSIDE"
    The distance is rounded to a whole number of metres (format :.0f)."""
    d = distance_from_home_m(x_m, y_m)
    if inside_circle(x_m, y_m):
        where = "INSIDE"
    else:
        where = "OUTSIDE"
    return f"{name} is {d:.0f} m from home: {where}"


# ---- you don't need to change anything below this line (but you can read it!) ----

def _try(label, fn, *args):
    try:
        print(f"  {label:<38} -> {fn(*args)!r}")
    except NotImplementedError as e:
        print(f"  {label:<38} -> not written yet ({e})")


if __name__ == "__main__":
    print("Part 1 — speeds, distances, times")
    _try("kmh_to_ms(36)", kmh_to_ms, 36)
    _try("ms_to_kmh(10)", ms_to_kmh, 10)
    _try("distance_m(15, 60)", distance_m, 15, 60)
    _try("travel_time_s(900, 15)", travel_time_s, 900, 15)
    _try("travel_time_s(900, 0)", travel_time_s, 900, 0)
    print("Part 2 — the battery")
    _try("flight_time_min(100, 400)", flight_time_min, 100, 400)
    _try("battery_status(75)", battery_status, 75)
    _try("battery_status(35)", battery_status, 35)
    _try("battery_status(10)", battery_status, 10)
    print("Part 3 — the 600 m circle")
    _try("distance_from_home_m(300, 400)", distance_from_home_m, 300, 400)
    _try("inside_circle(300, 400)", inside_circle, 300, 400)
    _try("inside_circle(500, -500)", inside_circle, 500, -500)
    _try('status_line("drone-1", 300, 400)', status_line, "drone-1", 300, 400)
    _try('status_line("drone-2", 500, -500)', status_line, "drone-2", 500, -500)
