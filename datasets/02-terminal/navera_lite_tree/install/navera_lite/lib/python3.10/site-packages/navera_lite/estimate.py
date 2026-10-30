"""navera_lite/estimate.py — the position contract: one estimate from one source.

Part of NAVERA Lite, the course's teaching stack (mission 12). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 12.
"""


def is_covariance(cov9, tol=1e-09):
    """Is this a real covariance matrix?."""
    ...


def stated_sigma(est, cfg):
    """The uncertainty a source states, m."""
    ...


def eligible(est, now_s, cfg):
    """May the judge use this estimate now?."""
    ...
