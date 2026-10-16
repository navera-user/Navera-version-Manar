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
    return None   # TODO: replace this line with your code


# TODO 2 ------------------------------------------------------------------------------------
def mismatch(p, beacons, measured, bias=0.0):
    """Sum over the beacons of the squared residuals (lesson §2–§3):
    residual = measured − (distance from p to the beacon + bias).

    Example:  mismatch((4, 4), [(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  about 1.409
    """
    return None   # TODO: replace this line with your code


# TODO 3 ------------------------------------------------------------------------------------
def find_position(beacons, measured):
    """Brute force: the point of the grid x, y = 0.0, 0.1, … 10.0 with the smallest mismatch (bias 0).
    Returns (x, y).

    Example:  find_position([(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708])  ->  (3.0, 4.0)
    """
    return None   # TODO: replace this line with your code


# TODO 4 ------------------------------------------------------------------------------------
def find_position_and_bias(beacons, measured):
    """Brute force with the clock: same grid, and bias = 0.00, 0.05, … 1.00 km. Returns (x, y, bias).

    Example:  find_position_and_bias([(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008])  ->  (3.0, 4.0, 0.3)
    """
    return None   # TODO: replace this line with your code


# TODO 5 ------------------------------------------------------------------------------------
def gauss_newton(beacons, measured, guess=(5.0, 5.0, 0.0), steps=10):
    """Gauss–Newton least squares for (x, y, bias), from the guess, in `steps` iterations (lesson §3).
    Works with 3 or more beacons. Returns (x, y, bias) as three floats.

    Example:  gauss_newton([(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008])  ->  about (3.0, 4.0, 0.3)
    """
    return None   # TODO: replace this line with your code


# TODO 6 ------------------------------------------------------------------------------------
def spoof_measurements(beacons, fake_position, bias):
    """What a spoofer broadcasts: the pseudoranges a receiver at fake_position would measure with this
    clock bias. Returns a list, one value per beacon.

    Example:  spoof_measurements([(0, 0), (10, 0)], (6, 8), 0.5)  ->  [10.5, 9.444…]
    """
    return None   # TODO: replace this line with your code


# TODO 7 ------------------------------------------------------------------------------------
def gate_ok(last, new, elapsed_s, v_max_mps, margin_m):
    """NAVERA's jump gate (lesson §5): True if the new fix is accepted.

    Examples:  gate_ok((0, 0), (120, 0), 1.0, 100.0, 50.0)  ->  True
               gate_ok((0, 0), (500, 0), 1.0, 100.0, 50.0)  ->  False
    """
    return None   # TODO: replace this line with your code


# TODO 8 ------------------------------------------------------------------------------------
def count_refused(fixes, dt_s, v_max_mps, margin_m):
    """How many of these GPS fixes does the jump gate refuse? (lesson §5, no other source)
    fixes[0] is trusted; one new fix arrives every dt_s seconds.

    Example (the 7-row table of lesson §5):
        count_refused([(0, 0)] + [(500, 0)] * 6 + [(900, 0)], 1.0, 100.0, 50.0)  ->  5
    """
    return None   # TODO: replace this line with your code


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
    return None   # TODO: replace this line with your code
