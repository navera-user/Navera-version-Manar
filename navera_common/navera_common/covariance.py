"""Checks and summaries of a 3x3 position covariance (row-major, east/north/up, m^2). Pure Python."""
import math
from typing import Sequence

# relative tolerance of the symmetry and positive-semi-definite checks (float rounding)
REL_TOL = 1e-9


def horizontal_sigma(cov: Sequence[float]) -> float:
    """1-sigma of the worst horizontal direction: the square root of the largest eigenvalue of
    the 2x2 east/north block. sqrt(max(var_e, var_n)) under-reads a tilted (correlated)
    ellipse by up to sqrt(2): a fix could be judged within a bound its long axis is not."""
    a, b, c = float(cov[0]), 0.5 * (float(cov[1]) + float(cov[3])), float(cov[4])
    lam = 0.5 * (a + c) + math.sqrt((0.5 * (a - c)) ** 2 + b * b)
    return math.sqrt(max(lam, 0.0))


def covariance_sane(cov: Sequence[float]) -> bool:
    """A covariance that is one: finite, non-negative variances, symmetric, horizontal block
    positive semi-definite. Each tolerance is sized from the variances it compares: the
    symmetry of a pair by sqrt(var_i var_j) (m^2), the horizontal determinant by var_e var_n
    (m^4). One tolerance sized by the largest variance (the up one, often huge when the height
    is unknown) switched the horizontal tests off; a fixed m^2 one refused valid km-scale
    covariances with a correlation of exactly 1."""
    cov = [float(c) for c in cov]
    if len(cov) != 9 or not all(math.isfinite(c) for c in cov):
        return False
    var = (cov[0], cov[4], cov[8])
    if min(var) < 0.0:
        return False
    for i, j in ((0, 1), (0, 2), (1, 2)):
        tol = REL_TOL * max(1.0, math.sqrt(var[i] * var[j]))
        if abs(cov[3 * i + j] - cov[3 * j + i]) > tol:
            return False
    b = 0.5 * (cov[1] + cov[3])
    return var[0] * var[1] - b * b >= -REL_TOL * max(1.0, var[0] * var[1])
