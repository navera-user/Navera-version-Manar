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
    # TODO 1: convert to radians, then return (sin, cos) — east first, north second
    raise NotImplementedError("TODO 1")


def ground_velocity(airspeed_ms, heading_deg, wind_east_ms=0.0, wind_north_ms=0.0):
    """Ground velocity (east, north) in m/s = air velocity + wind velocity.
    Example: 15 m/s heading 0, wind (4, 0) -> (4.0, 15.0)."""
    # TODO 2: use heading_vector(); air velocity = airspeed × unit vector; add the wind
    raise NotImplementedError("TODO 2")


def wind_correction(airspeed_ms, track_deg, wind_east_ms, wind_north_ms):
    """Heading to fly so that the GROUND track is track_deg, and the ground speed.

    Returns (heading_deg in [0, 360), ground_speed_ms).
    Raises ValueError when the crosswind is stronger than the airspeed (no heading works)
    or when the resulting ground speed is not positive (the wind pushes the vehicle back).
    Example: 15 m/s, track 0, wind (4, 0) -> (344.53, 14.46)."""
    # TODO 3: (see the course, "The wind triangle")
    #   w_cross = component of the wind to the RIGHT of the track, w_along = along the track
    #   if |w_cross| > airspeed  -> raise ValueError(...)
    #   crab = asin(w_cross / airspeed);  ground speed = airspeed·cos(crab) + w_along
    #   if ground speed <= 0     -> raise ValueError(...)
    #   heading = (track - crab in degrees) % 360
    raise NotImplementedError("TODO 3")


def flight_time_min(battery_wh, power_w, reserve_frac=0.2):
    """Minutes of flight with a fraction reserve_frac of the battery kept unused.
    Raises ValueError if battery_wh <= 0, power_w <= 0 or reserve_frac not in [0, 1).
    Example: 100 Wh, 400 W, reserve 0.2 -> 80 Wh usable -> 0.2 h -> 12.0 min."""
    # TODO 4: two checks that raise ValueError, then usable energy -> hours -> minutes
    raise NotImplementedError("TODO 4")


# ---------------------------------------------------------------------------
# Part B — classes
# ---------------------------------------------------------------------------


class Vehicle:
    """A vehicle with a cruise airspeed and a battery."""

    def __init__(self, name, cruise_ms, battery_wh, power_w):
        # TODO 5: raise ValueError if cruise_ms <= 0, then store the four parameters as
        #         attributes with the SAME names: self.name, self.cruise_ms, self.battery_wh, self.power_w
        raise NotImplementedError("TODO 5")

    def endurance_s(self, reserve_frac=0.2):
        """Seconds of flight (uses flight_time_min)."""
        # TODO 6a: call flight_time_min() with this vehicle's attributes
        raise NotImplementedError("TODO 6a")

    def range_m(self, reserve_frac=0.2, wind_along_ms=0.0):
        """Distance (m) flown in a straight line: ground speed × endurance.
        wind_along_ms > 0 is a tailwind, < 0 a headwind. 0.0 if the ground speed is <= 0."""
        # TODO 6b: ground speed = cruise + wind_along; distance = ground speed × self.endurance_s(...)
        raise NotImplementedError("TODO 6b")

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
        # TODO 7a: let Vehicle.__init__ do its part (super), then refuse cruise_ms <= stall_ms
        #          with a ValueError, and store self.stall_ms
        raise NotImplementedError("TODO 7a")

    def turn_radius_m(self, bank_deg=30.0):
        """Radius of a level turn: r = v² / (g · tan(bank))."""
        # TODO 7b: the formula of the docstring (G_MPS2 is defined at the top; bank in radians!)
        raise NotImplementedError("TODO 7b")


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
        # TODO 8: refuse a time that is not after the last one (ValueError), then append
        #         float(t), float(east), float(north) to the three lists
        raise NotImplementedError("TODO 8")

    def __len__(self):
        return len(self.t)

    def arrays(self):
        """The track as three NumPy arrays (t, east, north)."""
        return np.array(self.t), np.array(self.east), np.array(self.north)

    def length_m(self):
        """Total path length (m): sum of the straight segments. 0.0 with fewer than 2 points."""
        # TODO 9a: NumPy, no loop: np.diff, np.hypot, np.sum (and the < 2 points case)
        raise NotImplementedError("TODO 9a")

    def speeds_ms(self):
        """NumPy array of the n-1 segment speeds (m/s)."""
        # TODO 9b: segment lengths / segment durations, element by element (an array)
        raise NotImplementedError("TODO 9b")


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
