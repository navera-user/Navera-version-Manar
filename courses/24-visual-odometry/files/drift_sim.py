"""drift_sim.py — dead reckoning in one axis, simulated many times: how does the error of a sum of steps grow?

    python3 drift_sim.py          (lab Step 6) — needs TODO 5 (drift_sigma in navera_lite/vo.py) and TODO 6 below

Every simulated step has an error = a bias (the same at every step) + a random part (new at every step). The program
compares YOUR simulation with YOUR formula drift_sigma(), fits the growth exponent p (error ∝ nᵖ) and draws
out/drift.png on log-log axes.
"""
import os
import sys

import numpy as np

import runner_kit as rk


# TODO 6 -------------------------------------------------------------------------------------------
def simulate_drift(n_steps, sigma_m, bias_m, trials=2000, seed=0):
    """Monte Carlo of dead reckoning in ONE axis (lesson §7): `trials` simulated flights of n_steps steps each.
    Every step's error is bias_m plus a random number drawn from a normal distribution of mean 0 and standard
    deviation sigma_m (use np.random.default_rng(seed), so that a run can be repeated exactly).
    Returns a numpy array of n_steps numbers: entry k is the RMS, over the trials, of the accumulated error after
    k + 1 steps.
    Example: simulate_drift(100, 0.0, 0.1) → array([0.1, 0.2, 0.3, …, 10.0])   (no randomness: exactly n · bias)
             simulate_drift(100, 0.5, 0.0)[-1] → about 5.0   (a few % either way: it is random)
    """
    return None   # TODO: replace this line with your code


# ---- you don't need to change anything below this line ----

def growth_exponent(rms):
    """The slope p of log(rms) against log(n), n = 1 … len(rms): error ∝ nᵖ."""
    n = np.arange(1, len(rms) + 1)
    return float(np.polyfit(np.log(n), np.log(rms), 1)[0])


def main():
    here = sys.modules[__name__]
    vo = rk.load_student("navera_lite.vo")
    n = 400
    cases = (("random only", 0.5, 0.0), ("bias only", 0.0, 0.1), ("both", 0.5, 0.1))
    curves = {}
    print(f"{n} steps, 2000 simulated flights each (one axis)\n")
    print(f"{'case':12s}{'sigma':>7s}{'bias':>7s}{'RMS after 100':>15s}{'drift_sigma(100)':>18s}{'exponent p':>12s}")
    for name, s, b in cases:
        rms = rk.need_ok(here, "simulate_drift", n, s, b)
        rms = np.asarray(rms, dtype=float)
        if rms.shape != (n,):
            sys.exit(f"simulate_drift({n}, …) must return {n} numbers (one per step), got shape {rms.shape}")
        theory = rk.need_ok(vo, "drift_sigma", np.arange(1, n + 1), s, b)
        theory = np.asarray(theory, dtype=float)
        if theory.shape != (n,):
            sys.exit("drift_sigma() on an array of n's must return one number per n (use numpy, not math)")
        curves[name] = (rms, theory)
        p = growth_exponent(rms) if name != "both" else float("nan")
        print(f"{name:12s}{s:7.2f}{b:7.2f}{rms[99]:13.2f} m{theory[99]:16.2f} m{p:12.2f}")
    print("\n(the exponent of 'both' is not one number: look at its curve)")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(7, 4.6))
        steps = np.arange(1, n + 1)
        for (name, (rms, theory)), col in zip(curves.items(), ("#0b6e8a", "#d64545", "#1d2733")):
            ax.loglog(steps, rms, "-", color=col, label=f"{name}: simulated")
            ax.loglog(steps, theory, "--", color=col, lw=1, label=f"{name}: drift_sigma")
        ax.set_xlabel("steps n")
        ax.set_ylabel("RMS error (m), one axis")
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=8)
        os.makedirs("out", exist_ok=True)
        fig.savefig("out/drift.png", dpi=80, bbox_inches="tight")
        plt.close(fig)
        rk.saved("out/drift.png")


if __name__ == "__main__":
    main()
