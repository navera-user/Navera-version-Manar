"""band_sim.py — where does the mean NEES of an HONEST filter fall? Find out by simulation.

    python3 band_sim.py        (lab Step 5) — needs TODO 6 below

An honest filter's error at one step, measured in its own σ's, is like n independent standard normal numbers
(one per dimension): its NEES is their sum of squares. Over N steps we average the NEES. Repeat that "flight"
thousands of times: the averages spread around n. The middle share p of them is the band an honest filter's mean
NEES falls into with probability p. The program prints bands for a few cases and draws out/band.png.
"""
import os
import sys

import numpy as np

import runner_kit as rk


# TODO 6 -------------------------------------------------------------------------------------------
def nees_band(n_dim, n_steps, trials=4000, p=0.95, seed=0):
    """The band (low, high) that holds the share p of the mean NEES of an honest n_dim filter over n_steps steps,
    found by simulation (lesson §6): `trials` simulated flights, each with n_steps NEES values, each NEES the sum of
    the squares of n_dim standard normal numbers (np.random.default_rng(seed): a run can be repeated exactly).
    low and high cut off (1 − p)/2 of the flights' mean NEES at each end. Returns two floats.
    Example: nees_band(2, 1, trials=200000) → about (0.051, 7.38)     (one step: the χ² values of mission 27)
             nees_band(2, 100) → about (1.6, 2.4)                      (a few % either way: it is random)
    """
    return None   # TODO: write your code above, and return the result


# ---- you don't need to change anything below this line ----

def main():
    here = sys.modules[__name__]
    print("The band of the mean NEES of an honest filter (your nees_band, 4 000 simulated flights each)\n")
    print(f"{'dimensions n':>13s}{'steps N':>9s}{'p':>6s}{'band':>22s}{'width':>8s}")
    rows = ((2, 1, 0.95), (2, 10, 0.95), (2, 100, 0.95), (2, 361, 0.95), (2, 361, 0.99), (1, 131, 0.95))
    res = {}
    for n, N, p in rows:
        v = rk.need_ok(here, "nees_band", n, N, p=p)
        if not (isinstance(v, (tuple, list)) and len(v) == 2):
            sys.exit(f"nees_band() must return two numbers (low, high), got {v!r}")
        lo, hi = float(v[0]), float(v[1])
        if not lo < hi:
            sys.exit(f"nees_band({n}, {N}) gave low {lo} ≥ high {hi}: low is the lower end")
        if N > 1 and not lo < n < hi:
            sys.exit(f"✘ nees_band({n}, {N}) = ({lo:.3f}, {hi:.3f}) does not contain {n}: an honest filter's mean NEES "
                     f"is near n = {n}. Average over the STEPS (do not sum them) and sum over the DIMENSIONS.")
        res[(n, N, p)] = (lo, hi)
        print(f"{n:13d}{N:9d}{p:6.2f}{'':6s}{lo:7.3f} – {hi:7.3f}{hi - lo:8.3f}")
    lo1, hi1 = res[(2, 1, 0.95)]
    if not (0.035 < lo1 < 0.07 and 6.9 < hi1 < 7.9):
        print(f"\n✘ one step, n = 2: an honest NEES is χ² with 2 degrees of freedom, 95 % between 0.05 and 7.38, but your "
              f"band is {lo1:.3f} – {hi1:.3f}. Check: the sum over the DIMENSIONS, the mean over the STEPS, and "
              f"(1 − p)/2 cut at EACH end.")
        return
    lo, hi = res[(2, 361, 0.95)]
    print(f"\nThe lab's flight lasts 361 s: an honest 2-D tracker's mean NEES falls in {lo:.2f} – {hi:.2f} "
          "95 % of the time.")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    rng = np.random.default_rng(1)
    fig, ax = plt.subplots(figsize=(7, 3.4))
    for N, c in ((10, "#8a96a3"), (100, "#a8680d"), (361, "#0b6e8a")):
        m = (rng.standard_normal((4000, N, 2)) ** 2).sum(axis=2).mean(axis=1)
        ax.hist(m, bins=80, range=(0, 5), histtype="step", color=c, lw=1.5, label=f"N = {N} steps")
    ax.axvline(2.0, color="#1d2733", lw=1)
    ax.set_xlabel("mean NEES of one simulated honest flight (n = 2)")
    ax.set_ylabel("flights")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig("out/band.png", dpi=90)
    rk.saved("out/band.png")


if __name__ == "__main__":
    main()
