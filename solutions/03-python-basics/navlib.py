"""navlib.py — a small navigation library (lab 3).

Part A  functions          heading vectors, wind triangle, battery endurance
Part B  classes            Vehicle, FixedWing(Vehicle)
Part C  NumPy              the Track class: lengths and speeds without a Python loop

Conventions used everywhere in this file (and in NAVERA):
  * angles in DEGREES at the interface, converted to radians inside;
  * headings and tracks clockwise from TRUE NORTH: 0 = north, 90 = east;
  * local positions in metres: east (x) and north (y) from a reference point;
  * a wind vector is the direction the air MOVES TOWARDS (east, north components, m/s).

Each TODO replaces a line  raise NotImplementedError("TODO n").
Run the demo with:   python3 navlib.py
"""
import math

import numpy as np

G_MPS2 = 9.81                     # gravity (m/s²)

# ---------------------------------------------------------------------------
# Part A — functions
# ---------------------------------------------------------------------------


def heading_vector(heading_deg):
    """Unit vector (east, north) of a heading measured clockwise from north.
    Example: 0 -> (0.0, 1.0), 90 -> (1.0, 0.0), 225 -> (-0.7071, -0.7071)."""
    h = math.radians(heading_deg)
    return math.sin(h), math.cos(h)


def ground_velocity(airspeed_ms, heading_deg, wind_east_ms=0.0, wind_north_ms=0.0):
    """Ground velocity (east, north) in m/s = air velocity + wind velocity.
    Example: 15 m/s heading 0, wind (4, 0) -> (4.0, 15.0)."""
    ue, un = heading_vector(heading_deg)
    return airspeed_ms * ue + wind_east_ms, airspeed_ms * un + wind_north_ms


def wind_correction(airspeed_ms, track_deg, wind_east_ms, wind_north_ms):
    """Heading to fly so that the GROUND track is track_deg, and the ground speed.

    Returns (heading_deg in [0, 360), ground_speed_ms).
    Raises ValueError when the crosswind is stronger than the airspeed (no heading works)
    or when the resulting ground speed is not positive (the wind pushes the vehicle back).
    Example: 15 m/s, track 0, wind (4, 0) -> (344.53, 14.46)."""
    t = math.radians(track_deg)
    w_cross = wind_east_ms * math.cos(t) - wind_north_ms * math.sin(t)     # to the right of the track
    w_along = wind_east_ms * math.sin(t) + wind_north_ms * math.cos(t)     # along the track
    if abs(w_cross) > airspeed_ms:
        raise ValueError(f"crosswind {w_cross:.1f} m/s is stronger than the airspeed {airspeed_ms:.1f} m/s")
    crab = math.asin(w_cross / airspeed_ms)
    gs = airspeed_ms * math.cos(crab) + w_along
    if gs <= 0:
        raise ValueError(f"ground speed {gs:.1f} m/s: the wind is stronger than the vehicle")
    heading = (track_deg - math.degrees(crab)) % 360.0
    return heading, gs


def flight_time_min(battery_wh, power_w, reserve_frac=0.2):
    """Minutes of flight with a fraction reserve_frac of the battery kept unused.
    Raises ValueError if battery_wh <= 0, power_w <= 0 or reserve_frac not in [0, 1).
    Example: 100 Wh, 400 W, reserve 0.2 -> 80 Wh usable -> 0.2 h -> 12.0 min."""
    if battery_wh <= 0 or power_w <= 0:
        raise ValueError("battery_wh and power_w must be positive")
    if not 0.0 <= reserve_frac < 1.0:
        raise ValueError(f"reserve_frac={reserve_frac} must be in [0, 1)")
    usable_wh = battery_wh * (1.0 - reserve_frac)
    return usable_wh / power_w * 60.0


# ---------------------------------------------------------------------------
# Part B — classes
# ---------------------------------------------------------------------------


class Vehicle:
    """A vehicle with a cruise airspeed and a battery."""

    def __init__(self, name, cruise_ms, battery_wh, power_w):
        if cruise_ms <= 0:
            raise ValueError(f"{name}: cruise_ms must be positive, got {cruise_ms}")
        self.name = name
        self.cruise_ms = cruise_ms
        self.battery_wh = battery_wh
        self.power_w = power_w

    def endurance_s(self, reserve_frac=0.2):
        """Seconds of flight (uses flight_time_min)."""
        return flight_time_min(self.battery_wh, self.power_w, reserve_frac) * 60.0

    def range_m(self, reserve_frac=0.2, wind_along_ms=0.0):
        """Distance (m) flown in a straight line: ground speed × endurance.
        wind_along_ms > 0 is a tailwind, < 0 a headwind. 0.0 if the ground speed is <= 0."""
        gs = self.cruise_ms + wind_along_ms
        if gs <= 0:
            return 0.0
        return gs * self.endurance_s(reserve_frac)

    def __repr__(self):
        # __repr__ is the text Python shows when you print() the object (course, section 5).
        # {self.name!r} inserts repr(self.name): the name WITH its quotes, e.g. 'quad'.
        return f"{type(self).__name__}({self.name!r}, cruise {self.cruise_ms} m/s)"


class Multirotor(Vehicle):
    """Example of inheritance (already written): a multirotor can also hover."""

    def __init__(self, name, cruise_ms, battery_wh, power_w, hover_power_w):
        super().__init__(name, cruise_ms, battery_wh, power_w)
        self.hover_power_w = hover_power_w

    def hover_time_min(self, reserve_frac=0.2):
        return flight_time_min(self.battery_wh, self.hover_power_w, reserve_frac)


class FixedWing(Vehicle):
    """A fixed-wing aircraft: it must fly faster than its stall speed, and it turns on a circle."""

    def __init__(self, name, cruise_ms, battery_wh, power_w, stall_ms):
        super().__init__(name, cruise_ms, battery_wh, power_w)
        if cruise_ms <= stall_ms:
            raise ValueError(f"{name}: cruise {cruise_ms} m/s is not above the stall speed {stall_ms} m/s")
        self.stall_ms = stall_ms

    def turn_radius_m(self, bank_deg=30.0):
        """Radius of a level turn: r = v² / (g · tan(bank))."""
        return self.cruise_ms ** 2 / (G_MPS2 * math.tan(math.radians(bank_deg)))


# ---------------------------------------------------------------------------
# Part C — NumPy: the Track class
# ---------------------------------------------------------------------------


class Track:
    """Time-stamped positions (local east/north metres) of one vehicle."""

    def __init__(self, name):
        self.name = name
        self.t = []
        self.east = []
        self.north = []

    def add(self, t, east, north):
        """Append one position. Raises ValueError if t is not strictly after the last time."""
        if self.t and t <= self.t[-1]:
            raise ValueError(f"time {t} is not after the last time {self.t[-1]}")
        self.t.append(float(t))
        self.east.append(float(east))
        self.north.append(float(north))

    def __len__(self):
        return len(self.t)

    def arrays(self):
        """The track as three NumPy arrays (t, east, north)."""
        return np.array(self.t), np.array(self.east), np.array(self.north)

    def length_m(self):
        """Total path length (m): sum of the straight segments. 0.0 with fewer than 2 points."""
        _, e, n = self.arrays()
        if len(e) < 2:
            return 0.0
        return float(np.sum(np.hypot(np.diff(e), np.diff(n))))

    def speeds_ms(self):
        """NumPy array of the n-1 segment speeds (m/s)."""
        t, e, n = self.arrays()
        if len(t) < 2:
            return np.array([])
        return np.hypot(np.diff(e), np.diff(n)) / np.diff(t)


# ---- you don't need to change anything below this line (but read it!) ----


def load_track(path, name="track"):
    """Read a CSV file t_s,east_m,north_m into a Track (np.loadtxt skips the header row)."""
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    tr = Track(name)
    for t, e, n in data:
        tr.add(t, e, n)
    return tr


def _try(label, fn, *args):
    # *args collects any extra arguments in a tuple; fn(*args) unpacks them again (course, section 2).
    try:
        r = fn(*args)
        if isinstance(r, tuple):
            r = "(" + ", ".join(f"{x:.4g}" if isinstance(x, float) else repr(x) for x in r) + ")"
        elif isinstance(r, float):
            r = f"{r:.4g}"
        print(f"  {label:<44} -> {r}")
    except NotImplementedError as e:
        print(f"  {label:<44} -> not written yet ({e})")
    except Exception as e:  # show the error in one line, like the checker does
        print(f"  {label:<44} -> {type(e).__name__}: {e}")


if __name__ == "__main__":
    # "lambda: ..." below is a small function without a name, run later by _try() (lesson 4 explains it).
    print("Part A — functions")
    _try("heading_vector(90)", heading_vector, 90)
    _try("ground_velocity(15, 0, 4, 0)", ground_velocity, 15, 0, 4, 0)
    _try("wind_correction(15, 0, 4, 0)", wind_correction, 15, 0, 4, 0)
    _try("wind_correction(15, 0, 20, 0)   (too windy)", wind_correction, 15, 0, 20, 0)
    _try("flight_time_min(100, 400)", flight_time_min, 100, 400)
    _try("flight_time_min(50, 400)", flight_time_min, 50, 400)
    _try("flight_time_min(100, 0)   (bad input)", flight_time_min, 100, 0)
    print("Part B — classes")
    _try('Vehicle("quad", 12, 100, 400)', Vehicle, "quad", 12, 100, 400)
    _try('...endurance_s()', lambda: Vehicle("quad", 12, 100, 400).endurance_s())
    _try('...range_m(wind_along_ms=-3)', lambda: Vehicle("quad", 12, 100, 400).range_m(wind_along_ms=-3))
    _try('FixedWing("wing", 20, 150, 250, 12)', FixedWing, "wing", 20, 150, 250, 12)
    _try('...turn_radius_m(30)', lambda: FixedWing("wing", 20, 150, 250, 12).turn_radius_m(30))
    print("Part C — NumPy: the Track class")
    tr = Track("demo")
    _try("Track.add(0, 0, 0); add(1, 3, 4); add(2, 3, 10)",
         lambda: [tr.add(0, 0, 0), tr.add(1, 3, 4), tr.add(2, 3, 10), len(tr)][-1])
    _try("Track.length_m()", tr.length_m)
    _try("Track.speeds_ms()", tr.speeds_ms)
