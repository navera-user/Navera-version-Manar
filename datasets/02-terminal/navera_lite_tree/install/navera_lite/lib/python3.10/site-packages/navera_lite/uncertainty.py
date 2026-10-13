"""navera_lite/uncertainty.py — covariance, ellipses, gating, fusion.

Part of NAVERA Lite, the course's teaching stack (mission 27). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 27.
"""


def ellipse(P, k=1.0):
    """The error ellipse of a covariance."""
    ...


def mahalanobis2(r, S):
    """Squared distance in units of uncertainty."""
    ...


def fuse(x1, P1, x2, P2):
    """Two estimates into one."""
    ...
