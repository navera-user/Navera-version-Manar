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
    return math.sqrt((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2)


# TODO 2 ------------------------------------------------------------------------------------
def mismatch(p, beacons, measured, bias=0.0):
    """How badly the position p explains the measurements (lesson §2 and §3).

    For each beacon: (distance from p to the beacon + bias) minus the measured value, squared.
    Return the sum over all beacons. 0 means p (with this bias) explains every measurement.

    Example (the worked example of the course):
        mismatch((4, 4), [(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  about 1.409
    """
    total = 0.0
    for beacon, m in zip(beacons, measured):
        diff = distance(p, beacon) + bias - m
        total = total + diff ** 2
    return total


# TODO 3 ------------------------------------------------------------------------------------
def find_position(beacons, measured):
    """The grid point with the smallest mismatch (bias 0).

    Try every x from 0.0 to 10.0 and every y from 0.0 to 10.0, in steps of 0.1.
    Return the best point as a pair (x, y).

    Example:  find_position([(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  (3.0, 4.0)
    """
    best, best_m = None, None
    for i in range(101):
        for j in range(101):
            p = (i / 10, j / 10)
            m = mismatch(p, beacons, measured)
            if best_m is None or m < best_m:
                best, best_m = p, m
    return best


# TODO 4 ------------------------------------------------------------------------------------
def find_position_and_bias(beacons, measured):
    """Like find_position, but the clock bias is a third unknown.

    Try every x and y as before, and every bias from 0.00 to 1.00 km in steps of 0.05.
    Return the best guess as (x, y, bias).

    Example:  find_position_and_bias([(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008])  ->  (3.0, 4.0, 0.3)
    (It takes a few seconds: that is about 200 000 guesses.)
    """
    best, best_m = None, None
    for i in range(101):
        for j in range(101):
            for k in range(21):
                guess = (i / 10, j / 10, k / 20)
                m = mismatch(guess[:2], beacons, measured, guess[2])
                if best_m is None or m < best_m:
                    best, best_m = guess, m
    return best


# TODO 5 ------------------------------------------------------------------------------------
def spoof_measurements(beacons, fake_position, bias):
    """What a spoofer sends: the measurements a receiver WOULD make at fake_position,
    with this clock bias. Return a list with one value per beacon, in the same order.

    Example:  spoof_measurements([(0, 0), (10, 0)], (6, 8), 0.5)  ->  [10.5, 9.444…]
    """
    return [distance(fake_position, beacon) + bias for beacon in beacons]


# TODO 6 ------------------------------------------------------------------------------------
def gate_ok(last, new, elapsed_s, v_max_mps, margin_m):
    """NAVERA's jump gate (lesson §5). Positions in metres, time in seconds.

    Return True if the new fix is ACCEPTED: its distance to the last trusted fix is at most
    v_max × elapsed + margin. Return False if it is refused.

    Examples:  gate_ok((0, 0), (120, 0), 1.0, 100.0, 50.0)  ->  True    (120 <= 150)
               gate_ok((0, 0), (500, 0), 1.0, 100.0, 50.0)  ->  False   (500 >  150)
    """
    return distance(last, new) <= v_max_mps * elapsed_s + margin_m


# TODO 7 ------------------------------------------------------------------------------------
def count_refused(fixes, dt_s, v_max_mps, margin_m):
    """How many of these GPS fixes does NAVERA's jump gate refuse? (lesson §5)

    fixes[0] is trusted; one new fix arrives every dt_s seconds. Positions in metres.

    Example (the 7-row table of lesson §5: a 500 m jump, then 400 m more):
        count_refused([(0, 0)] + [(500, 0)] * 6 + [(900, 0)], 1.0, 100.0, 50.0)  ->  5
    """
    refused = 0
    last = fixes[0]
    elapsed = 0.0
    for fix in fixes[1:]:
        elapsed = elapsed + dt_s
        if gate_ok(last, fix, elapsed, v_max_mps, margin_m):
            last = fix
            elapsed = 0.0
        else:
            refused = refused + 1
    return refused
