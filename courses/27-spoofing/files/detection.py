"""detection.py — spoofing detection as a statistical test (lesson 27, part B).

    python3 detection.py        # computes everything, writes results.json and roc.png

H0 = "GPS is honest", H1 = "GPS is being pulled away (slow drift)".
Test statistic, at every vision fix:   z = |GPS - vision| / sigma_vision
Alarm rule ("persistence"):           n vision fixes IN A ROW with z > k

You write TODO 5-9. The flight simulator and the experiment are below the line.
"""
import json
import math

import numpy as np

# ---- the experiment (the same numbers as NAVERA's day vision checking GPS) ----
SIGMA_V = 15.0          # vision: the accuracy it STATES (m, per axis)
SIGMA_G = 3.0           # GPS noise (m, per axis)
PERIOD_S = 2.0          # one vision fix every 2 s (day_pkg gps_check_period_s)
H0_FIXES = 60           # an honest flight: 60 vision fixes = 2 minutes
H1_FIXES = 20           # a spoofed flight: we want an alarm within 20 fixes = 40 s
DRIFT_MPS = 1.5         # the spoofer pulls GPS north at 1.5 m/s from the first fix
FLIGHTS = 2000          # Monte-Carlo flights per hypothesis
SEED = 27
K_GRID = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
N_GRID = [1, 2, 3, 5]
MAX_PFA = 0.01          # the requirement for your operating point: at most 1 % of honest flights alarmed

# ---- TODO 10: your operating point, chosen from results.json (see lab step 8) ----
CHOSEN_K = None
CHOSEN_N = None

# ---- TODO 11: read real_drift.txt (lab step 9) and copy the GPS offsets (m) ----
REAL_DRIFT_OFFSET_AT_DOUBT_M = None      # the first line that says "IN DOUBT"
REAL_DRIFT_OFFSET_AT_REFUSAL_M = None    # the first line that says "drifting away"


def p_exceed(k, sigma_ref=SIGMA_V, sigma_g=0.0):
    """P(z > k) under H0 for ONE fix, z = |GPS - vision| / sigma_ref.

    Under H0 the 2-D difference GPS - vision is Gaussian with variance
    s2 = sigma_ref**2 + sigma_g**2 per axis, so |difference| follows a Rayleigh law:
        P(|d| > r) = exp(-r**2 / (2 * s2)),   here r = k * sigma_ref."""
    return None   # TODO 5


def p_streak(k, n, sigma_ref=SIGMA_V, sigma_g=0.0):
    """P(n INDEPENDENT fixes in a row all beyond k) under H0."""
    return None   # TODO 6  (one line: use p_exceed)


def patient_accept_time(offset_m, speed_mps, max_speed_mps, margin_m):
    """The patient spoofer. The vehicle flies straight at speed_mps; the spoofer puts GPS
    offset_m to the SIDE of the true track and keeps it there. The gate compares with the
    last trusted fix, dt seconds ago. Return the smallest dt (s) for which the spoofed fix is
    'reachable':   max_speed*dt + margin >= sqrt((speed*dt)**2 + offset**2)
    or math.inf if it never becomes reachable."""
    return None   # TODO 7  (square both sides: a quadratic in dt — see lab step 6)


def alarm_index(z, k, n):
    """Index of the first fix where the last n values of z are ALL > k, or -1 if never."""
    return None   # TODO 8  (count the current run of values > k)


def roc_point(z_h0, z_h1, k, n, period_s=PERIOD_S):
    """One point of the ROC curve for the rule (k, n).
    z_h0, z_h1: 2-D arrays (flights x fixes). Returns a dict:
        p_fa      fraction of H0 flights with an alarm (any fix)
        p_d       fraction of H1 flights with an alarm (any fix)
        delay_s   mean alarm time (index * period_s) over the DETECTED H1 flights, None if none"""
    return None   # TODO 9  (use alarm_index on every flight)


# ---- you don't need to change anything below this line (but read it!) ----

def simulate_z(rng, flights, fixes, drift_mps=0.0, rho=0.0,
               sigma_v=SIGMA_V, sigma_g=SIGMA_G, period_s=PERIOD_S):
    """z = |GPS - vision| / sigma_v for `flights` x `fixes` simulated vision checks.
    Vision error: Gaussian sigma_v per axis, AR(1)-correlated from fix to fix with rho
    (rho = 0: independent; rho = 0.9: the same map error lasts several fixes).
    GPS error: Gaussian sigma_g per axis. H1: GPS pulled north by drift_mps * t."""
    w = rng.standard_normal((flights, fixes, 2))
    ev = np.empty_like(w)
    ev[:, 0] = w[:, 0]
    c = math.sqrt(1.0 - rho * rho)
    for i in range(1, fixes):
        ev[:, i] = rho * ev[:, i - 1] + c * w[:, i]
    ev *= sigma_v
    eg = sigma_g * rng.standard_normal((flights, fixes, 2))
    bias = np.zeros((flights, fixes, 2))
    bias[:, :, 1] = drift_mps * period_s * np.arange(fixes)
    d = bias + eg - ev
    return np.hypot(d[..., 0], d[..., 1]) / sigma_v


def experiment():
    rng = np.random.default_rng(SEED)
    z0 = simulate_z(rng, FLIGHTS, H0_FIXES)
    z1 = simulate_z(rng, FLIGHTS, H1_FIXES, drift_mps=DRIFT_MPS)
    zc = simulate_z(rng, FLIGHTS, H0_FIXES, rho=0.9)
    out = {"single_fix": [], "roc": [], "correlated": [], "patient": {}, "chosen": {}, "real_drift": {}}
    for k in (2.0, 3.0, 4.0):
        out["single_fix"].append({"k": k, "theory": _num(p_exceed(k, SIGMA_V, SIGMA_G)),
                                  "theory_vision_only": _num(p_exceed(k)),
                                  "measured": float(np.mean(z0 > k))})
    for n in N_GRID:
        for k in K_GRID:
            p = roc_point(z0, z1, k, n)
            out["roc"].append({"k": k, "n": n, **{key: _num(v) for key, v in (p or {}).items()}})
    for k, n in ((3.0, 5), (2.5, 3)):
        out["correlated"].append({"k": k, "n": n,
                                  "p_fa_independent": _num((roc_point(z0, z0[:1], k, n) or {}).get("p_fa")),
                                  "p_fa_rho_0.9": _num((roc_point(zc, zc[:1], k, n) or {}).get("p_fa"))})
    out["patient"] = _patient()
    out["chosen"] = {"k": CHOSEN_K, "n": CHOSEN_N}
    out["real_drift"] = {"offset_at_doubt_m": REAL_DRIFT_OFFSET_AT_DOUBT_M,
                         "offset_at_refusal_m": REAL_DRIFT_OFFSET_AT_REFUSAL_M}
    return out


def _patient():
    """The 'patient' attack of scenarios.py: theory vs your guard of spoof.py."""
    import scenarios
    import spoof
    t_theory = patient_accept_time(2000.0, scenarios.SPEED, 30.0, 50.0)
    rows = spoof.play(scenarios.build("patient"), spoof.GpsGuard(max_speed=30.0), verbose=False)
    accepted = next((t for t, st, _, off in rows if off > 0 and st == "TRUSTED" and t > 20), None)
    return {"last_trusted_t_s": 19.0, "dt_theory_s": _num(t_theory),
            "accepted_theory_t_s": _num(19.0 + t_theory if isinstance(t_theory, (int, float)) else None),
            "accepted_by_guard_t_s": accepted}


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return round(float(v), 6)
    return None


def plot(out, path="roc.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    for n in N_GRID:
        pts = [r for r in out["roc"] if r["n"] == n and r.get("p_fa") is not None]
        if pts:
            ax.plot([r["p_fa"] for r in pts], [r["p_d"] for r in pts], "o-", label=f"n = {n}")
            for r in pts:
                ax.annotate(f"{r['k']}", (r["p_fa"], r["p_d"]), fontsize=7, xytext=(3, -8),
                            textcoords="offset points")
    ax.axvline(MAX_PFA, color="grey", ls="--", lw=1)
    ax.set_xscale("symlog", linthresh=1e-3)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("P_FA (honest 2-min flights with an alarm)")
    ax.set_ylabel(f"P_D (drift {DRIFT_MPS} m/s caught within {H1_FIXES * PERIOD_S:.0f} s)")
    ax.set_title("ROC of the persistence test (labels: k)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=100)


if __name__ == "__main__":
    print("one fix beyond 3 sigma (vision only):", p_exceed(3.0))
    print("five in a row:", p_streak(3.0, 5))
    out = experiment()
    with open("results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\nk    n   P_FA    P_D    delay")
    for r in out["roc"]:
        print(f"{r['k']:<4} {r['n']:<3} {r.get('p_fa')!s:7} {r.get('p_d')!s:7} {r.get('delay_s')}")
    print("\npatient spoofer:", out["patient"])
    print("correlated vision errors:", out["correlated"])
    try:
        plot(out)
        print("\nwrote results.json and roc.png")
    except Exception as e:  # noqa: BLE001 — the plot is a bonus; results.json is what counts
        print("\nwrote results.json (no plot:", e, ")")
