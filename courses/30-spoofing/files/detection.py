"""detection.py — spoofing detection as a statistical test: measure the ROC of the persistence rule by Monte Carlo
(lab Steps 7–8). Uses YOUR navera_lite/spoof.py (chi2_threshold_2d, first_alarm).

    python3 detection.py        # about 10 s; prints the table, writes results.json and out/roc.png

H0 = "the GPS is honest", H1 = "the GPS is pulled away slowly" (a drift of DRIFT_MPS from the first test).
One test every PERIOD_S: d² = |GPS − vision|² / (σ_g² + σ_v²) (the innovation of lesson §3, S = (σ_g² + σ_v²)·I).
The rule: ALARM when n tests in a row have d² > γ, with γ = chi2_threshold_2d(p) (p = false alarms per TEST).

You write TODO 8 (roc_point) and TODO 9 (your operating point). The simulator is below the line.
"""
import json
import math
import os

import numpy as np

import runner_kit as rk

sp = rk.load_student("navera_lite.spoof")

# ---- the experiment (the numbers of the lab's attacks) ----
SIGMA_V = 15.0          # vision: σ on each axis (m), stated honestly
SIGMA_G = 3.0           # GPS: σ on each axis (m)
PERIOD_S = 2.0          # one vision fix (one test) every 2 s
H0_TESTS = 60           # an honest flight: 60 tests = 2 minutes
H1_TESTS = 20           # a spoofed flight: we want the alarm within 20 tests = 40 s
DRIFT_MPS = 1.5         # the spoofer pulls the GPS away at 1.5 m/s from the first test
FLIGHTS = 2000          # Monte-Carlo flights per hypothesis
SEED = 30
P_GRID = [0.2, 0.1, 0.05, 0.01, 0.001, 0.0001]     # p_fa per test → γ = chi2_threshold_2d(p)
N_GRID = [1, 2, 3, 5]                               # tests in a row
MAX_PFA = 0.01          # the requirement: at most 1 % of honest 2-minute flights with an alarm

# ---- TODO 9: your operating point, chosen from the table (lab Step 8) ----
CHOSEN_P = 0.2          # p_fa per test, one value of P_GRID
CHOSEN_N = 1            # tests in a row, one value of N_GRID


# TODO 8
def roc_point(d2_h0, d2_h1, threshold, n, period_s=PERIOD_S):
    """One point of the ROC curve: how the rule "n tests in a row with d² > threshold" does on simulated flights.

    d2_h0, d2_h1: 2-D arrays (flights × tests) of d², honest flights and spoofed flights.
    Returns a dict:
        "p_fa"     the share of HONEST flights with an alarm (anywhere in the flight)
        "p_d"      the share of SPOOFED flights with an alarm
        "delay_s"  the mean alarm time (alarm test index × period_s) over the spoofed flights that HAVE an
                   alarm; None if none has one
    Use first_alarm() of navera_lite/spoof.py (TODO 3) for each flight.
    Example: roc_point(np.array([[1.0, 12.0, 13.0], [0.5, 0.5, 0.5]]), np.array([[10.0, 11.0, 12.0]]), 9.21, 2)
             → {"p_fa": 0.5, "p_d": 1.0, "delay_s": 2.0}
    """
    return None   # TODO 8: write your code above, and return the result


# ---- you don't need to change anything below this line (but read it!) ----

def simulate_d2(rng, flights, tests, drift_mps=0.0, rho=0.0, sigma_v=SIGMA_V, sigma_g=SIGMA_G, period_s=PERIOD_S):
    """d² of `flights` × `tests` simulated vision checks. Vision error: Gaussian σ_v on each axis, AR(1)-correlated
    from one test to the next with rho (0: independent; 0.9: the same map error lasts several tests). GPS error:
    Gaussian σ_g. H1: the GPS is pulled east by drift_mps × t (t = 0 at the first test)."""
    w = rng.standard_normal((flights, tests, 2))
    ev = np.empty_like(w)
    ev[:, 0] = w[:, 0]
    c = math.sqrt(1.0 - rho * rho)
    for i in range(1, tests):
        ev[:, i] = rho * ev[:, i - 1] + c * w[:, i]
    ev *= sigma_v
    eg = sigma_g * rng.standard_normal((flights, tests, 2))
    bias = np.zeros((flights, tests, 2))
    bias[:, :, 0] = drift_mps * period_s * np.arange(tests)
    d = bias + eg - ev
    return (d[..., 0] ** 2 + d[..., 1] ** 2) / (sigma_v ** 2 + sigma_g ** 2)


def _num(v):
    if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) and math.isfinite(v):
        return round(float(v), 6)
    return None


def _point(z0, z1, gamma, n):
    p, err = rk.call(_this(), "roc_point", z0, z1, gamma, n)
    if err:
        raise SystemExit(err)
    if not isinstance(p, dict) or not {"p_fa", "p_d", "delay_s"} <= set(p):
        raise SystemExit(f"roc_point() must return a dict with p_fa, p_d and delay_s, got {p!r}")
    return p


def _this():
    import sys
    return sys.modules[__name__]


def experiment():
    for name in ("chi2_threshold_2d", "first_alarm"):
        if rk.is_stub(getattr(sp, name)):
            raise SystemExit(f"{name}() is not written yet: write its TODO in navera_lite/spoof.py first")
    rng = np.random.default_rng(SEED)
    z0 = simulate_d2(rng, FLIGHTS, H0_TESTS)
    z1 = simulate_d2(rng, FLIGHTS, H1_TESTS, drift_mps=DRIFT_MPS)
    zc = simulate_d2(rng, FLIGHTS, H0_TESTS, rho=0.9)
    out = {"single_test": [], "roc": [], "correlated": [], "chosen": {}}
    for p in (0.1, 0.01, 0.001):
        g = rk.need_ok(sp, "chi2_threshold_2d", p, kind=float)
        out["single_test"].append({"p": p, "gamma": _num(g), "measured": float(np.mean(z0 > g))})
    for n in N_GRID:
        for p in P_GRID:
            g = sp.chi2_threshold_2d(p)
            r = _point(z0, z1, g, n)
            sigma_s = math.sqrt(SIGMA_V ** 2 + SIGMA_G ** 2)
            theory, err = rk.call(sp, "drift_alarm_time", DRIFT_MPS, sigma_s, g, n, PERIOD_S)
            out["roc"].append({"p": p, "n": n, "gamma": _num(g), **{k: _num(v) for k, v in r.items()},
                               "delay_theory_s": None if err else _num(theory)})
    for p, n in ((0.01, 5), (0.05, 3)):
        g = sp.chi2_threshold_2d(p)
        out["correlated"].append({"p": p, "n": n, "p_fa_independent": _num(_point(z0, z0[:1], g, n)["p_fa"]),
                                  "p_fa_rho_0.9": _num(_point(zc, zc[:1], g, n)["p_fa"])})
    pick = next((r for r in out["roc"] if r["p"] == CHOSEN_P and r["n"] == CHOSEN_N), None)
    out["chosen"] = {"p": CHOSEN_P, "n": CHOSEN_N, "p_fa": pick and pick["p_fa"], "p_d": pick and pick["p_d"],
                     "delay_s": pick and pick["delay_s"]}
    return out


def plot(out, path="out/roc.png"):
    plt = rk.plt_or_none()
    if not plt:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    for n in N_GRID:
        pts = [r for r in out["roc"] if r["n"] == n and r.get("p_fa") is not None]
        ax.plot([r["p_fa"] for r in pts], [r["p_d"] for r in pts], "o-", label=f"n = {n}")
        for r in pts:
            ax.annotate(f"{r['p']:g}", (r["p_fa"], r["p_d"]), fontsize=7, xytext=(3, -9), textcoords="offset points")
    ax.axvline(MAX_PFA, color="grey", ls="--", lw=1)
    ax.set_xscale("symlog", linthresh=1e-3)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("P_FA (share of honest 2-minute flights with an alarm)")
    ax.set_ylabel(f"P_D (drift {DRIFT_MPS} m/s caught within {H1_TESTS * PERIOD_S:.0f} s)")
    ax.set_title("ROC of the persistence rule (labels: p_fa per test)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    rk.saved(path)


if __name__ == "__main__":
    print(f"{FLIGHTS} honest flights × {H0_TESTS} tests, {FLIGHTS} spoofed flights × {H1_TESTS} tests "
          f"(drift {DRIFT_MPS} m/s), {FLIGHTS} honest flights with correlated vision errors …\n")
    out = experiment()
    print("one test: p_fa (theory)  γ        measured share of honest tests with d² > γ")
    for r in out["single_test"]:
        print(f"          {r['p']:<14} {r['gamma']:<8} {r['measured']:.4f}")
    print("\np_fa/test  n   P_FA (flight)  P_D     mean delay  delay without noise (drift_alarm_time)")
    for r in out["roc"]:
        print(f"{r['p']:<10} {r['n']:<3} {r['p_fa']!s:14} {r['p_d']!s:7} {str(r['delay_s']) + ' s':11} "
              f"{r['delay_theory_s']} s")
    print("\ncorrelated vision errors (ρ = 0.9), honest flights:", out["correlated"])
    print("your operating point:", out["chosen"])
    with open("results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\nwrote results.json")
    plot(out)
