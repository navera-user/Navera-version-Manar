"""uncertainty.py — the maths of "how sure are we?" (lesson 27).

Small numpy functions, each graded by the check. analyse.py and kalman.py use them.
Vectors are 1-D numpy arrays, matrices 2-D numpy arrays. Positions are (east, north) in metres.

Run the demo:   python3 uncertainty.py
"""
import math

import numpy as np
from scipy.stats import chi2


def sample_cov(points):
    """The 2x2 SAMPLE covariance of N points (an N x 2 array of east, north):
         d = points - mean          (subtract the mean of each column)
         P = d^T d / (N - 1)        (N - 1: the "unbiased" estimate, like numpy.cov)
    """
    pts = np.asarray(points, dtype=float)
    d = pts - pts.mean(axis=0)
    return d.T @ d / (len(pts) - 1)


def error_ellipse(P, k=1.0):
    """(a, b, angle_deg) of the k-sigma ellipse of the 2x2 covariance P.

    P = V diag(l1, l2) V^T  (eigen-decomposition: numpy.linalg.eigh, eigenvalues ascending)
      a = k * sqrt(largest eigenvalue)     semi-major axis (m)
      b = k * sqrt(smallest eigenvalue)    semi-minor axis (m)
      angle_deg = direction of the major axis (its eigenvector (ve, vn)), counted from EAST
                  towards NORTH: degrees(atan2(vn, ve)), brought into (-90, 90]
                  (an axis has no arrow: 120 deg and -60 deg are the same line)
    """
    vals, vecs = np.linalg.eigh(np.asarray(P, dtype=float))
    a, b = k * math.sqrt(max(vals[1], 0.0)), k * math.sqrt(max(vals[0], 0.0))
    ang = math.degrees(math.atan2(vecs[1, 1], vecs[0, 1]))
    while ang > 90.0:
        ang -= 180.0
    while ang <= -90.0:
        ang += 180.0
    return a, b, ang


def chi2_threshold(p, dof):
    """The value t with P(chi-square with `dof` degrees of freedom <= t) = p.
    2 dof: 0.39 -> 1.0, 0.95 -> 5.99, 0.99 -> 9.21.   (scipy.stats.chi2.ppf)"""
    return float(chi2.ppf(p, dof))


def propagate(J, P):
    """Covariance of y = f(x) when x has covariance P and J is the Jacobian of f:  J P J^T."""
    J = np.atleast_2d(np.asarray(J, dtype=float))
    return J @ np.atleast_2d(np.asarray(P, dtype=float)) @ J.T


def polar_to_en(r, bearing_deg, sigma_r, sigma_bearing_deg):
    """A range-bearing fix (range r in m, bearing from NORTH, clockwise, in degrees) to
    (east, north) and its 2x2 covariance.
        east = r sin(b)        north = r cos(b)
        J = [[d east/d r, d east/d b], [d north/d r, d north/d b]]   (b in RADIANS)
        P_polar = diag(sigma_r^2, sigma_b^2)                         (sigma_b in RADIANS)
    Returns (np.array([east, north]), J P_polar J^T)."""
    b = math.radians(bearing_deg)
    sb = math.radians(sigma_bearing_deg)
    en = np.array([r * math.sin(b), r * math.cos(b)])
    J = np.array([[math.sin(b), r * math.cos(b)],
                  [math.cos(b), -r * math.sin(b)]])
    return en, propagate(J, np.diag([sigma_r ** 2, sb ** 2]))


def mahalanobis2(r, S):
    """Squared Mahalanobis distance of the vector r for the covariance S:  r^T S^-1 r.
    Use numpy.linalg.solve(S, r) rather than inverting S. Returns a float."""
    r = np.atleast_1d(np.asarray(r, dtype=float))
    return float(r @ np.linalg.solve(np.atleast_2d(np.asarray(S, dtype=float)), r))


def chi2_gate(r, S, p=0.99):
    """True when r is plausible for covariance S at probability p:
    mahalanobis2(r, S) <= chi2_threshold(p, len(r))."""
    r = np.atleast_1d(np.asarray(r, dtype=float))
    return mahalanobis2(r, S) <= chi2_threshold(p, len(r))


def fuse(x1, P1, x2, P2):
    """Inverse-variance (information) fusion of two independent estimates of the same vector:
         P = (P1^-1 + P2^-1)^-1
         x = P (P1^-1 x1 + P2^-1 x2)
    Scalars are accepted (x = number, P = variance). Returns (x, P) as numpy arrays."""
    x1, x2 = np.atleast_1d(np.asarray(x1, dtype=float)), np.atleast_1d(np.asarray(x2, dtype=float))
    I1 = np.linalg.inv(np.atleast_2d(np.asarray(P1, dtype=float)))
    I2 = np.linalg.inv(np.atleast_2d(np.asarray(P2, dtype=float)))
    P = np.linalg.inv(I1 + I2)
    return P @ (I1 @ x1 + I2 @ x2), P


COVARIANCE_TYPE_UNKNOWN = 0         # the values of navera_msgs/PositionEstimate
COVARIANCE_TYPE_DIAGONAL_KNOWN = 2
COVARIANCE_TYPE_KNOWN = 3


def make_covariance(P2, sigma_up=None):
    """The 3x3 ENU position_covariance of PositionEstimate (9 numbers, row by row, m^2) and its type,
    from a 2x2 horizontal covariance P2 (east, north).

      - P2 is None: we do NOT know  ->  ([0.0] * 9, COVARIANCE_TYPE_UNKNOWN)
      - otherwise  [P2[0][0], P2[0][1], 0,
                    P2[1][0], P2[1][1], 0,
                    0,        0,        su^2]
        su = sigma_up, or 2 x the larger horizontal sigma when sigma_up is None (as gps_node does);
        type COVARIANCE_TYPE_KNOWN when P2 has a non-zero off-diagonal term, else DIAGONAL_KNOWN.
    All 9 values are Python floats."""
    if P2 is None:
        return [0.0] * 9, COVARIANCE_TYPE_UNKNOWN
    P2 = np.asarray(P2, dtype=float)
    su = sigma_up if sigma_up is not None else 2.0 * math.sqrt(max(P2[0, 0], P2[1, 1]))
    cov = [P2[0, 0], P2[0, 1], 0.0, P2[1, 0], P2[1, 1], 0.0, 0.0, 0.0, su * su]
    kind = COVARIANCE_TYPE_KNOWN if (P2[0, 1] != 0.0 or P2[1, 0] != 0.0) else COVARIANCE_TYPE_DIAGONAL_KNOWN
    return [float(v) for v in cov], kind


# ---- you don't need to change anything below this line (but you can read it!) ----

def estimate_message(lat, lon, P2):
    """A navera_msgs/PositionEstimate carrying YOUR covariance (lesson 12 contract)."""
    from navera_msgs.msg import PositionEstimate
    m = PositionEstimate()
    m.latitude, m.longitude, m.altitude = float(lat), float(lon), math.nan
    cov, kind = make_covariance(P2)
    m.position_covariance = [float(v) for v in cov]
    m.position_covariance_type = kind
    m.source, m.mode, m.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, True
    m.producer = "academy_lesson_26"
    return m


if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    P = np.array([[12.0, 5.0], [5.0, 6.0]])
    print("P =\n", P)
    print("1-sigma ellipse (a, b, angle from east):", error_ellipse(P))
    print("chi-square 2 dof, 95 %:", chi2_threshold(0.95, 2))
    print("radar on a headland: 2000 m, bearing 60 deg, sigma 5 m and 0.5 deg ->", polar_to_en(2000.0, 60.0, 5.0, 0.5))
    print("Mahalanobis^2 of (6, -2):", mahalanobis2([6.0, -2.0], P), " gate 99 %:", chi2_gate([6.0, -2.0], P))
    print("fuse 100 m (var 100) and 110 m (var 25):", fuse(100.0, 100.0, 110.0, 25.0))
    print("PositionEstimate covariance:", make_covariance(P))
