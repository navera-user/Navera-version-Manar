"""beacons.py — your position solver, your spoofer and your arbiter (lab 1).

Positions are (x, y) pairs: km on the beacon field, metres in the gate and flight steps.
Test each function as you go:      python3 where_am_i.py test
Each docstring gives an example call and its result.
"""
import math

import numpy as np


# TODO 1 ------------------------------------------------------------------------------------
def distance(p, q):
    """Euclidean distance between p = (x1, y1) and q = (x2, y2).

    Example:  distance((0, 0), (3, 4))  ->  5.0
    """
    return math.sqrt((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2)


# TODO 2 ------------------------------------------------------------------------------------
def mismatch(p, beacons, measured, bias=0.0):
    """Sum over the beacons of the squared residuals (lesson §2–§3):
    residual = measured − (distance from p to the beacon + bias).

    Example:  mismatch((4, 4), [(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  about 1.409
    """
    total = 0.0
    for beacon, m in zip(beacons, measured):
        total += (m - (distance(p, beacon) + bias)) ** 2
    return total


# TODO 3 ------------------------------------------------------------------------------------
def find_position(beacons, measured):
    """Brute force: the point of the grid x, y = 0.0, 0.1, … 10.0 with the smallest mismatch (bias 0).
    Returns (x, y).

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
    """Brute force with the clock: same grid, and bias = 0.00, 0.05, … 1.00 km. Returns (x, y, bias).

    Example:  find_position_and_bias([(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008])  ->  (3.0, 4.0, 0.3)
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
def gauss_newton(beacons, measured, guess=(5.0, 5.0, 0.0), steps=10):
    """Gauss–Newton least squares for (x, y, bias), from the guess, in `steps` iterations (lesson §3).
    Works with 3 or more beacons. Returns (x, y, bias) as three floats.

    Example:  gauss_newton([(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008])  ->  about (3.0, 4.0, 0.3)
    """
    x, y, b = guess
    for _ in range(steps):
        H, r = [], []
        for beacon, m in zip(beacons, measured):
            d = distance((x, y), beacon)
            H.append([(x - beacon[0]) / d, (y - beacon[1]) / d, 1.0])
            r.append(m - (d + b))
        dx, *_ = np.linalg.lstsq(np.array(H), np.array(r), rcond=None)
        x, y, b = x + dx[0], y + dx[1], b + dx[2]
    return (float(x), float(y), float(b))


# TODO 6 ------------------------------------------------------------------------------------
def spoof_measurements(beacons, fake_position, bias):
    """What a spoofer broadcasts: the pseudoranges a receiver at fake_position would measure with this
    clock bias. Returns a list, one value per beacon.

    Example:  spoof_measurements([(0, 0), (10, 0)], (6, 8), 0.5)  ->  [10.5, 9.444…]
    """
    return [distance(fake_position, beacon) + bias for beacon in beacons]


# TODO 7 ------------------------------------------------------------------------------------
def gate_ok(last, new, elapsed_s, v_max_mps, margin_m):
    """NAVERA's jump gate (lesson §5): True if the new fix is accepted.

    Examples:  gate_ok((0, 0), (120, 0), 1.0, 100.0, 50.0)  ->  True
               gate_ok((0, 0), (500, 0), 1.0, 100.0, 50.0)  ->  False
    """
    return distance(last, new) <= v_max_mps * elapsed_s + margin_m


# TODO 8 ------------------------------------------------------------------------------------
def count_refused(fixes, dt_s, v_max_mps, margin_m):
    """How many of these GPS fixes does the jump gate refuse? (lesson §5, no other source)
    fixes[0] is trusted; one new fix arrives every dt_s seconds.

    Example (the 7-row table of lesson §5):
        count_refused([(0, 0)] + [(500, 0)] * 6 + [(900, 0)], 1.0, 100.0, 50.0)  ->  5
    """
    refused, last, elapsed = 0, fixes[0], 0.0
    for fix in fixes[1:]:
        elapsed += dt_s
        if gate_ok(last, fix, elapsed, v_max_mps, margin_m):
            last, elapsed = fix, 0.0
        else:
            refused += 1
    return refused


# TODO 9 ------------------------------------------------------------------------------------
def first_disagreement(rows, k=5.0, margin_m=50.0):
    """NAVERA's cross-check on a flight log (lesson §5): the time t_s of the first row where vision has a
    position and the GPS is farther from it than k × vision_sigma_m + margin_m. None if it never happens.

    rows: a list of dicts with keys t_s, gps_x_m, gps_y_m, vision_x_m, vision_y_m, vision_sigma_m
    (the vision values are None when vision has no match).

    Example:  first_disagreement([{"t_s": 100, "gps_x_m": 0, "gps_y_m": 0, "vision_x_m": None, "vision_y_m": None,
              "vision_sigma_m": None}, {"t_s": 101, "gps_x_m": 500, "gps_y_m": 0, "vision_x_m": 0, "vision_y_m": 0,
              "vision_sigma_m": 30}])  ->  101
    """
    for r in rows:
        if r["vision_x_m"] is None:
            continue
        d = distance((r["gps_x_m"], r["gps_y_m"]), (r["vision_x_m"], r["vision_y_m"]))
        if d > k * r["vision_sigma_m"] + margin_m:
            return r["t_s"]
    return None
