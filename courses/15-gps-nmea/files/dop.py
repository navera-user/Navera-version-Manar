"""Lesson 15 — Dilution Of Precision from the satellite geometry.

Course: section 5 (linearised pseudorange model, the matrix G, Q = (G^T G)^-1 and the five DOPs)
and its worked example (5 satellites, HDOP 1.155). Use numpy.

    python3 dop.py          (prints the worked example of the course)
"""
import numpy as np


# TODO 7: the geometry matrix G (shape N x 4) from azimuths and elevations in DEGREES.
#   Azimuth: clockwise from north. Elevation: above the horizon. Axes: East, North, Up, clock.
#   Course: section 5 ("Linearisation" and "Stack the n satellites").
#   Input: two lists (or numpy arrays) of the same length n. Output: numpy array, shape (n, 4).
#   Careful: numpy's sin/cos take RADIANS.
def geometry_matrix(az_deg, el_deg):
    return None  # TODO 7: replace this line with your code


# TODO 8: the five DOPs as a dictionary {"GDOP", "PDOP", "HDOP", "VDOP", "TDOP"} (floats).
#   Course: section 5 (the DOP table under "The DOPs are the square roots…").
#   Raise ValueError("need at least 4 satellites") when fewer than 4 satellites are given.
#   Check yourself with the worked example: HDOP 1.155, VDOP 2.236.
def dops(az_deg, el_deg):
    return None  # TODO 8: replace this line with your code


# ---- you don't need to change anything below this line ----

# The worked example of the course: 5 satellites (azimuth, elevation) in degrees.
EXAMPLE_AZ = [0, 90, 180, 270, 0]
EXAMPLE_EL = [30, 30, 30, 30, 90]

if __name__ == "__main__":
    np.set_printoptions(precision=4, suppress=True)
    G = geometry_matrix(EXAMPLE_AZ, EXAMPLE_EL)
    print("TODO 7  G =\n", G)
    if G is not None:
        print("G^T G =\n", G.T @ G)
    print("TODO 8  DOPs of the worked example:", dops(EXAMPLE_AZ, EXAMPLE_EL))
    print("        (course: GDOP 2.887, PDOP 2.517, HDOP 1.155, VDOP 2.236, TDOP 1.414)")
    bunched = dops([20, 40, 60, 35, 50], [20, 25, 30, 60, 45])
    if bunched is not None:
        print("        5 satellites bunched in the north-east:", {k: round(v, 2) for k, v in bunched.items()})
