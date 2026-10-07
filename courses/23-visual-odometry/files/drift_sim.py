"""Lesson 23 — Drift as a random walk: how fast does dead-reckoning error grow?

Run:   python3 drift_sim.py        simulate, fit the growth exponents, save drift_sim.png, update results.json
"""
import json
import math

import numpy as np


# TODO 9: Monte Carlo of the position error after n steps
def simulate_drift(n_steps, sigma=0.5, bias=0.0, trials=2000, seed=0):
    """RMS position error (m) after 1, 2, ..., n_steps steps.

    Each step adds an error vector (ex, ey): ex = bias + N(0, sigma), ey = N(0, sigma)
    (bias: a systematic error in metres per step, along x). The position error after n
    steps is the SUM of the first n error vectors. Do `trials` independent flights
    (rng = np.random.default_rng(seed)) and return a numpy array of length n_steps:
    rms[n-1] = sqrt(mean over trials of |error after n steps|^2)."""
    # rng = np.random.default_rng(seed); arrays of shape (trials, n_steps) for ex and ey
    # np.cumsum(..., axis=1) gives the error after 1, 2, ... steps; then the RMS over the trials (axis=0)
    raise NotImplementedError("TODO 9")


# TODO 10: growth exponent from a log-log fit
def growth_exponent(rms):
    """p in rms(n) ~ C n^p: slope of log(rms) against log(n), n = 1..len(rms) (np.polyfit, degree 1)."""
    # n = 1 .. len(rms); np.polyfit(np.log(n), np.log(rms), 1) returns [slope, intercept]
    raise NotImplementedError("TODO 10")


# ---- you don't need to change anything below this line ----

def main():
    n = 200
    random_only = simulate_drift(n, sigma=0.5, bias=0.0)
    bias_only = simulate_drift(n, sigma=0.0, bias=0.1)
    both = simulate_drift(n, sigma=0.5, bias=0.1)
    pr, pb = growth_exponent(random_only), growth_exponent(bias_only)
    print(f"random errors only (0.5 m per step, per axis): after 100 steps {random_only[99]:.2f} m "
          f"(theory sigma*sqrt(2n) = {0.5 * math.sqrt(200):.2f} m), exponent {pr:.3f}")
    print(f"bias only (0.1 m per step):                    after 100 steps {bias_only[99]:.2f} m "
          f"(theory b*n = {0.1 * 100:.2f} m), exponent {pb:.3f}")
    # where the bias starts to dominate: b n = sigma sqrt(2n)  ->  n = 2 sigma^2 / b^2
    cross = 2 * 0.5 ** 2 / 0.1 ** 2
    print(f"both: after 100 steps {both[99]:.2f} m; the bias dominates beyond n = 2 sigma^2 / b^2 = {cross:.0f} steps")
    import warnings
    warnings.filterwarnings("ignore")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    k = np.arange(1, n + 1)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.loglog(k, random_only, color="#0b6e8a", label=f"random only: slope {pr:.2f}")
    ax.loglog(k, bias_only, color="#d64545", label=f"bias only: slope {pb:.2f}")
    ax.loglog(k, both, color="#1d2733", ls="--", label="both")
    ax.set_xlabel("number of steps n")
    ax.set_ylabel("RMS position error (m)")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.savefig("drift_sim.png", dpi=90, bbox_inches="tight")
    plt.close(fig)
    print("saved drift_sim.png")
    try:
        with open("results.json") as f:
            res = json.load(f)
    except (OSError, ValueError):
        res = {}
    res["drift_sim"] = {"exponent_random": round(pr, 3), "exponent_bias": round(pb, 3),
                        "rms_random_100": round(float(random_only[99]), 3),
                        "rms_bias_100": round(float(bias_only[99]), 3)}
    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    print("results.json updated (drift_sim)")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError as e:
        print(f"Not finished yet: {e} is still to do. Read the lab, fill it in, save, and run again.")
        raise SystemExit(1)
