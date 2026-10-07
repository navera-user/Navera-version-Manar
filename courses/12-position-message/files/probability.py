#!/usr/bin/env python3
"""probability.py — how much probability is inside "1 sigma"? And what does NAVERA read?

    python3 probability.py

Part 1: draws 100 000 errors from your source's covariance (fixed seed) and counts how many fall
inside the k-sigma ellipse (Mahalanobis distance <= k), and how many have |east error| <= sigma_E.
Part 2: compares NAVERA's stated sigma (EstimatorNode._stated_sigma, from YOUR NAVERA copy) with the
largest sigma of the ellipse (your error_ellipse) for two covariances.
Writes both into results.json.
"""
import json
import math

import numpy as np
from navera_estimator.nodes.estimator_node import EstimatorNode
from navera_msgs.msg import PositionEstimate

from my_source import (HEADING_DEG, SIGMA_ALONG_M, SIGMA_CROSS_M, SIGMA_UP_M, enu_covariance,
                       error_ellipse)

KS = [1.0, 2.0, 2.448]


def mahalanobis2(e_east, e_north, cov):
    """Squared Mahalanobis distance d² = eᵀ Σ⁻¹ e of a horizontal error (e_east, e_north), with
    Σ the horizontal 2x2 block of `cov` (9 numbers). Works on numbers or numpy arrays."""
    # TODO 6: a, b, c = cov[0], cov[1], cov[4];  det = a·c − b²
    #   the inverse of [[a, b], [b, c]] is [[c, −b], [−b, a]] / det, so
    #   d² = (c·e_east² − 2·b·e_east·e_north + a·e_north²) / det
    return 0.0 * e_east


def p_inside(k):
    """Theory: probability that a 2-D Gaussian error lies inside the k-sigma ellipse."""
    # TODO 7: 1 − exp(−k² / 2)
    return 0.0


# ---- you don't need to change anything below this line ----
def main():
    cov = enu_covariance(SIGMA_ALONG_M, SIGMA_CROSS_M, HEADING_DEG, SIGMA_UP_M)
    rng = np.random.default_rng(12)
    sigma2 = np.array([[cov[0], cov[1]], [cov[3], cov[4]]])
    e = rng.multivariate_normal([0.0, 0.0], sigma2, size=100_000)
    d2 = mahalanobis2(e[:, 0], e[:, 1], cov)
    prob = {"theory": {}, "sampled": {}}
    for k in KS:
        prob["theory"][str(k)] = p_inside(k)
        prob["sampled"][str(k)] = float(np.mean(d2 <= k * k))
    prob["east_within_1sigma"] = float(np.mean(np.abs(e[:, 0]) <= math.sqrt(cov[0])))

    compare = {}
    for name, c in (("default", cov), ("tilted", enu_covariance(30.0, 5.0, 45.0, SIGMA_UP_M))):
        m = PositionEstimate()
        m.position_covariance = c
        m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        major, minor, heading = error_ellipse(c)
        compare[name] = {"stated_sigma_m": EstimatorNode._stated_sigma(m), "sigma_max_m": major,
                         "sigma_min_m": minor, "major_axis_heading_deg": heading}

    try:
        with open("results.json") as f:
            res = json.load(f)
    except (OSError, ValueError):
        res = {}
    res["probability"], res["stated_vs_max"] = prob, compare
    with open("results.json", "w") as f:
        json.dump(res, f, indent=2)
    for k in KS:
        print(f"inside the {k}-sigma ellipse: sampled {prob['sampled'][str(k)]:.4f}, theory {prob['theory'][str(k)]:.4f}")
    print(f"|east error| <= sigma_E: {prob['east_within_1sigma']:.4f}")
    for name, r in compare.items():
        print(f"{name}: NAVERA stated sigma {r['stated_sigma_m']}, ellipse {r['sigma_max_m']:.2f} x "
              f"{r['sigma_min_m']:.2f} m, major axis at {r['major_axis_heading_deg']:.1f} deg")
    print("written results.json")


if __name__ == "__main__":
    main()
