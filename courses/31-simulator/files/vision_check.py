"""vision_check.py — measure YOUR trained networks on the simulator's corridor before they fly (lab Step 11), and
turn the measurement into the σ your vision sources will STATE: my_vision_profile.json.

    python3 vision_check.py            your weights: ../21-features/my_desc.pt (day), ../25-thermal-night/my_homography.pt
                                       (night) — the course's (ref_desc.pt, ref_homography.pt) for any that is missing
    python3 vision_check.py --course   the course's weights, to compare

Day: 40 photos at random places of the corridor (random heading), the prior 30 m off on each axis (σ). Night: 80
thermal patches, the prior 40 m off. Each is located by navera_lite/sim/vision.py exactly as in a flight. About
1 minute (the first day run also prepares the map's descriptors, ≈ 20 s, kept in my_runs/).
Then: σ = sigma_for_median(median error) — the σ of a 2-D Gaussian error with that median — and YOUR
rayleigh_quantile(σ, 0.95) predicts the 95th percentile, compared with the measured one.
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import json
import math
import os
import random
import sys

import numpy as np

import runner_kit as rk
from academy_gpu import limit_threads

DATA = os.environ.get("NAVERA_LITE_SIM_DATA", "/data/academy/31-simulator")
MINE = {"day": os.path.join("..", "21-features", "my_desc.pt"),
        "night": os.path.join("..", "25-thermal-night", "my_homography.pt")}
COURSE = {"day": "ref_desc.pt", "night": "ref_homography.pt"}
FLOOR_M = 5.0          # a stated σ is never below this (see the lab: the simulated camera is too kind)


def main():
    limit_threads()
    course = "--course" in sys.argv
    w = {k: (COURSE[k] if course or not os.path.exists(MINE[k]) else MINE[k]) for k in MINE}
    for k in w:
        print(f"{k:5s} weights: {w[k]}" + ("" if w[k] == MINE[k] or course else f"   ({MINE[k]} not found)"))
    S = rk.load_student("navera_lite.sim.sensors")
    from navera_lite.sim.vision import NetworkVision
    try:
        v = NetworkVision(DATA, w["day"], w["night"])
    except Exception as e:                                       # noqa: BLE001 — one plain sentence
        sys.exit(f"the networks cannot be loaded: {type(e).__name__}: {e}")
    rng = random.Random(3131)
    prof = {"weights": w}
    for light, n, prior_s in (("day", 40, 30.0), ("night", 80, 40.0)):
        errs, fails = [], 0
        for _ in range(n):
            seen = (rng.uniform(-150, 150), rng.uniform(-1500, 1500))
            prior = (seen[0] + rng.gauss(0, prior_s), seen[1] + rng.gauss(0, prior_s))
            got, _ = v.locate(seen, prior, light, rng.uniform(0, 360), 150.0, rng)
            if got is None:
                fails += 1
                continue
            errs.append(math.hypot(got[0] - seen[0], got[1] - seen[1]))
        if not errs:
            print(f"{light}: no fix at all in {n} tries")
            prof[light] = {"sigma_m": 1000.0, "stated_sigma_m": None, "fail": 1.0}
            continue
        med, p95 = float(np.median(errs)), float(np.percentile(errs, 95))
        sigma = S.sigma_for_median(med)
        pred = rk.need_ok(S, "rayleigh_quantile", sigma, 0.95, kind=float)
        stated = round(max(sigma, FLOOR_M), 2)
        prof[light] = {"sigma_m": round(sigma, 3), "stated_sigma_m": stated, "fail": round(fails / n, 3),
                       "median_m": round(med, 2), "p95_m": round(p95, 2), "rayleigh_p95_m": round(pred, 2), "n": n}
        print(f"\n{light}: {n - fails} fixes of {n} ({fails} refused); error median {med:.2f} m, 95th percentile "
              f"{p95:.2f} m, largest {max(errs):.1f} m")
        print(f"  σ = sigma_for_median({med:.2f}) = {sigma:.2f} m → your rayleigh_quantile(σ, 0.95) predicts "
              f"{pred:.2f} m (measured {p95:.2f} m)")
        print(f"  the source will state σ = {stated:g} m" + ("  (floored)" if sigma < FLOOR_M else ""))
    with open("my_vision_profile.json", "w") as f:
        json.dump(prof, f, indent=1)
    print("\nwrote my_vision_profile.json (used by vision 'mine' flights for the σ they state, and by vision 'profile')")


if __name__ == "__main__":
    main()
