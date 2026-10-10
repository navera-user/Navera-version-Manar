"""Lesson 15 — Dilution Of Precision from the satellite geometry.

Linearised pseudorange model (one row per satellite i):
    delta_rho_i = -u_i . delta_x + delta_b        u_i = unit vector receiver -> satellite (E, N, U)
    =>  delta_rho = G @ [dE, dN, dU, db]         G row i = [-uE_i, -uN_i, -uU_i, 1]
Least squares: Q = (G^T G)^-1 ;  covariance of the solution = UERE^2 * Q
    GDOP = sqrt(trace Q)            PDOP = sqrt(Q_EE + Q_NN + Q_UU)
    HDOP = sqrt(Q_EE + Q_NN)        VDOP = sqrt(Q_UU)          TDOP = sqrt(Q_bb)

    python3 dop.py          (prints the worked example of the course)
"""
import math

import numpy as np


# TODO 7: the geometry matrix G (shape N x 4) from azimuths and elevations in DEGREES.
#   Azimuth: clockwise from north. Elevation: above the horizon.
#   unit vector to the satellite in (East, North, Up):
#       (cos(el) sin(az),  cos(el) cos(az),  sin(el))
#   Row of G = [-uE, -uN, -uU, 1].  Accept lists or numpy arrays; use np.radians!
def geometry_matrix(az_deg, el_deg):
    az = np.radians(np.asarray(az_deg, dtype=float))
    el = np.radians(np.asarray(el_deg, dtype=float))
    u = np.column_stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)])
    return np.column_stack([-u, np.ones(len(az))])


# TODO 8: the five DOPs as a dictionary {"GDOP", "PDOP", "HDOP", "VDOP", "TDOP"} (floats).
#   Q = inverse of (G^T G). Raise ValueError("need at least 4 satellites") when fewer than
#   4 satellites are given (with 3 the 4 x 4 matrix G^T G cannot be inverted).
def dops(az_deg, el_deg):
    G = geometry_matrix(az_deg, el_deg)
    if G.shape[0] < 4:
        raise ValueError("need at least 4 satellites")
    A = G.T @ G
    if np.linalg.matrix_rank(A) < 4:              # singular geometry: the DOPs are infinite
        return {k: math.inf for k in ("GDOP", "PDOP", "HDOP", "VDOP", "TDOP")}
    Q = np.linalg.inv(A)
    d = np.diag(Q)
    return {"GDOP": float(np.sqrt(d.sum())),
            "PDOP": float(np.sqrt(d[0] + d[1] + d[2])),
            "HDOP": float(np.sqrt(d[0] + d[1])),
            "VDOP": float(np.sqrt(d[2])),
            "TDOP": float(np.sqrt(d[3]))}


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
