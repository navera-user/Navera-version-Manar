#!/usr/bin/env python3
"""sensor_models.py — the simulator's error models, checked with numbers (Part B).

    python3 sensor_models.py        runs the experiments and saves models.png

The models are copied from NAVERA's simulator (navera_tools/sim/nmea_gps.py, sim_server.py):
  GNSS noise   first-order Gauss-Markov per axis, dt = 0.2 s, tau = 20 s, q = 0.6
  vision       truth + N(0, sigma^2) on east and north; target sigma = 15 m
"""
import math

import numpy as np

DT = 0.2            # s, the simulated receiver's epoch (5 Hz)
TAU = 20.0          # s, correlation time
Q = 0.6             # m / sqrt(s), driving noise
DAY_TARGET_SIGMA = 15.0
DAY_MEASURED_MEDIAN = 440.0


def gauss_markov(n_steps, dt=DT, tau=TAU, q=Q, seed=0, x0=0.0):
    """One axis of the simulated receiver's noise: an array of n_steps values (metres)."""
    # TODO 1: rng = np.random.default_rng(seed); w = rng.standard_normal(n_steps)   (draw ALL w at once,
    #         in this order, so that your series is the same as the check's), then the recursion
    #         x[k] = a * x[k-1] + q * sqrt(dt) * w[k] with a = 1 - dt / tau, starting from x0.
    return np.zeros(n_steps)


def stationary_sigma(dt=DT, tau=TAU, q=Q):
    """Theoretical stationary standard deviation of gauss_markov() (exact discrete formula)."""
    # TODO 2: sigma^2 = q^2 dt / (1 - a^2)  (lesson, section 4)
    return 0.0


def autocorrelation(x, lag):
    """Sample autocorrelation of the series x at an integer lag (0 <= lag < len(x))."""
    # TODO 3: subtract the mean; rho(lag) = sum(x[k] * x[k+lag]) / sum(x[k]^2)  (numpy slices: x[:-lag], x[lag:]).
    #         lag 0 -> 1.0
    return 0.0


def rayleigh_quantile(sigma, p):
    """Horizontal error R_p not exceeded with probability p, when east and north errors are N(0, sigma^2)."""
    # TODO 4: R_p = sigma * sqrt(-2 ln(1 - p))
    return 0.0


def sigma_for_median(median):
    """The per-axis sigma whose Rayleigh median is `median` (how DAY_MEASURED_SIGMA is chosen)."""
    # TODO 4 (bis): invert the median formula
    return 0.0


def lagged_vision_errors(sigma, speed, period, n=20000, seed=1):
    """Monte Carlo: horizontal error of a vision fix of per-axis `sigma`, measured at a random
    instant within the last `period` seconds by a vehicle flying straight at `speed` m/s.
    The along-track lag is speed * U(0, period). Returns an array of n errors (metres)."""
    # TODO 5: rng = np.random.default_rng(seed); draw, IN THIS ORDER, east = rng.normal(0, sigma, n),
    #         north = rng.normal(0, sigma, n), lag = rng.uniform(0, period, n); add speed * lag to north
    #         (the vehicle flies north); return the horizontal error np.hypot(east, north).
    return np.zeros(n)


# ---- you don't need to change anything below this line (but you can read it!) ----

def model_results():
    """The numbers that go into results.json (section "models")."""
    x = gauss_markov(200000, seed=0)
    lag_tau = int(round(TAU / DT))
    lagged = lagged_vision_errors(DAY_TARGET_SIGMA, 15.0, 1.0)
    return {
        "gm_sigma_theory_m": round(stationary_sigma(), 3),
        "gm_sigma_sim_m": round(float(np.std(x)), 3),
        "gm_rho_at_tau": round(autocorrelation(x, lag_tau), 3),
        "target_median_m": round(rayleigh_quantile(DAY_TARGET_SIGMA, 0.5), 2),
        "target_p95_m": round(rayleigh_quantile(DAY_TARGET_SIGMA, 0.95), 2),
        "measured_sigma_m": round(sigma_for_median(DAY_MEASURED_MEDIAN), 1),
        "lagged_median_m": round(float(np.median(lagged)), 1),
    }


def main():
    r = model_results()
    print("Gauss-Markov GNSS noise (one axis):")
    print(f"  stationary sigma: theory {r['gm_sigma_theory_m']} m, simulated {r['gm_sigma_sim_m']} m")
    print(f"  autocorrelation after tau = {TAU:.0f} s: {r['gm_rho_at_tau']} (theory 1/e = {math.exp(-1):.3f}, "
          f"exact a^100 = {(1 - DT / TAU) ** 100:.3f})")
    print("Vision profiles (Rayleigh):")
    print(f"  target sigma {DAY_TARGET_SIGMA} m: median {r['target_median_m']} m, 95 % {r['target_p95_m']} m")
    print(f"  measured profile: sigma {r['measured_sigma_m']} m gives a median of {DAY_MEASURED_MEDIAN:.0f} m")
    print(f"  with a 1 s old fix at 15 m/s: median {r['lagged_median_m']} m")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        x = gauss_markov(3000, seed=0)
        lags = np.arange(0, 400)
        fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
        ax[0].plot(np.arange(len(x)) * DT, x)
        ax[0].set(title="GNSS noise, one axis", xlabel="time (s)", ylabel="m")
        xl = gauss_markov(200000, seed=0)
        ax[1].plot(lags * DT, [autocorrelation(xl, int(k)) for k in lags], label="simulated")
        ax[1].plot(lags * DT, (1 - DT / TAU) ** lags, "--", label="theory a^m")
        ax[1].set(title="autocorrelation", xlabel="lag (s)")
        ax[1].legend()
        e = np.hypot(*np.random.default_rng(2).normal(0, DAY_TARGET_SIGMA, (2, 20000)))
        ax[2].hist(e, bins=80, density=True, alpha=0.6, label="simulated |error|")
        rr = np.linspace(0, 70, 300)
        ax[2].plot(rr, rr / DAY_TARGET_SIGMA ** 2 * np.exp(-rr ** 2 / (2 * DAY_TARGET_SIGMA ** 2)), label="Rayleigh pdf")
        ax[2].set(title="target vision: horizontal error", xlabel="m")
        ax[2].legend()
        fig.tight_layout()
        fig.savefig("models.png", dpi=90)
        print("saved models.png")
    except Exception as ex:                       # plotting is a bonus
        print("no plot:", ex)


if __name__ == "__main__":
    main()
