"""beacons.py — find a position from distances (lab 1).

Positions are (x, y) pairs in km, like (3, 4). A list of beacons looks like [(0, 0), (10, 0), (0, 10)],
and the measured distances are a list in the same order, like [5.0, 8.062, 6.708].

Write each function, save (Ctrl+S), then test it:      python3 where_am_i.py test
Each function has an example: when your function gives the same result, it is probably right.
"""
import math


# TODO 1 ------------------------------------------------------------------------------------
def distance(p, q):
    """The straight-line distance between p = (x1, y1) and q = (x2, y2).

    Example:  distance((0, 0), (3, 4))  ->  5.0
    """
    return None   # TODO: write your code above, and return the result


# TODO 2 ------------------------------------------------------------------------------------
def mismatch(p, beacons, measured, bias=0.0):
    """How badly the position p explains the measurements (course §1 and §2).

    For each beacon: (distance from p to the beacon + bias) minus the measured value, squared.
    Return the sum over all beacons. 0 means p (with this bias) explains every measurement.

    Example (the worked example of the course):
        mismatch((4, 4), [(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  about 1.409
    """
    return None   # TODO: write your code above, and return the result


# TODO 3 ------------------------------------------------------------------------------------
def find_position(beacons, measured):
    """The grid point with the smallest mismatch (bias 0).

    Try every x from 0.0 to 10.0 and every y from 0.0 to 10.0, in steps of 0.1.
    Return the best point as a pair (x, y).

    Example:  find_position([(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  (3.0, 4.0)
    """
    return None   # TODO: write your code above, and return the result


# TODO 4 ------------------------------------------------------------------------------------
def find_position_and_bias(beacons, measured):
    """Like find_position, but the clock bias is a third unknown.

    Try every x and y as before, and every bias from 0.00 to 1.00 km in steps of 0.05.
    Return the best guess as (x, y, bias).

    Example:  find_position_and_bias([(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008])  ->  (3.0, 4.0, 0.3)
    (It takes a few seconds: that is about 200 000 guesses.)
    """
    return None   # TODO: write your code above, and return the result


# TODO 5 ------------------------------------------------------------------------------------
def spoof_measurements(beacons, fake_position, bias):
    """What a spoofer sends: the measurements a receiver WOULD make at fake_position,
    with this clock bias. Return a list with one value per beacon, in the same order.

    Example:  spoof_measurements([(0, 0), (10, 0)], (6, 8), 0.5)  ->  [10.5, 9.444…]
    """
    return None   # TODO: write your code above, and return the result


# TODO 6 ------------------------------------------------------------------------------------
def gate_ok(last, new, elapsed_s, v_max_mps, margin_m):
    """NAVERA's jump gate (course §4). Positions in metres, time in seconds.

    Return True if the new fix is ACCEPTED: its distance to the last trusted fix is at most
    v_max × elapsed + margin. Return False if it is refused.

    Examples:  gate_ok((0, 0), (120, 0), 1.0, 100.0, 50.0)  ->  True    (120 <= 150)
               gate_ok((0, 0), (500, 0), 1.0, 100.0, 50.0)  ->  False   (500 >  150)
    """
    return None   # TODO: write your code above, and return the result


# TODO 7 ------------------------------------------------------------------------------------
def count_refused(fixes, dt_s, v_max_mps, margin_m):
    """Run the jump gate on a list of GPS fixes, like the arbiter does.

    fixes[0] is trusted. The next fixes arrive one every dt_s seconds. Check each of them with
    gate_ok against the LAST ACCEPTED fix, where elapsed = the time since that accepted fix.
    An accepted fix becomes the new last accepted fix. Return how many fixes were refused.

    Example (the worked example of the course, a 500 m jump):
        count_refused([(0, 0)] + [(500, 0)] * 6, 1.0, 100.0, 50.0)  ->  4
    """
    return None   # TODO: write your code above, and return the result
