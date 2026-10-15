"""make_lesson_numbers.py — teacher only: recompute every number of lesson 33's worked example (and the TEACHER
figures of the example solution's exploring runs) with the given bench project.py and the course's stack.

    NAVERA_LITE_SIM_DATA=~/navera-academy-v2/datasets/31-simulator python3 solutions/33-final-project/make_lesson_numbers.py

The worked example: "day_timeout_s 5.0 → 2.0" on campaign/lake.json, seeds 1201–1230 (30 paired runs);
pre-registered metric err_p95 (window fault), lower is better, minimum effect 5 m; guard-rail availability (window
fault), higher is better, may lose at most 0.05. Takes about 30 s.
"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np

ACADEMY = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FILES = os.path.join(ACADEMY, "courses", "33-final-project", "files")
sys.path.insert(0, FILES)
import project as P  # noqa: E402
from navera_lite import stats  # noqa: E402


def variant(edit=None):
    d = tempfile.mkdtemp(prefix="l33_")
    for x in ("navera_lite", "campaign"):
        shutil.copytree(os.path.join(FILES, x), os.path.join(d, x), ignore=shutil.ignore_patterns("__pycache__"))
    for x in ("navera_lite.yaml", "ref_desc.pt", "ref_homography.pt"):
        shutil.copy(os.path.join(FILES, x), d)
    if edit:
        p = os.path.join(d, "navera_lite.yaml")
        t = open(p).read()
        assert edit[0] in t
        open(p, "w").write(t.replace(*edit))
    return d


def campaign(d, scen, seeds):
    sc = json.load(open(os.path.join(d, scen)))
    jobs = [{"file": scen, "scenario": sc, "seed": s, "name": f"{sc['name']}_s{s}"} for s in seeds]
    out = os.path.join(d, "runs")
    P.fly_jobs(d, jobs, out, quiet=True)
    return [(P.read_rows(os.path.join(out, j["name"] + ".csv")), sc) for j in jobs]


def vals(runs, m):
    return np.array([P.metric_value(m, rows, sc) for rows, sc in runs], dtype=float)


def main():
    seeds = list(range(1201, 1231))
    base, short = variant(), variant(("day_timeout_s: 5.0", "day_timeout_s: 2.0"))
    rb, ra = campaign(base, "campaign/lake.json", seeds), campaign(short, "campaign/lake.json", seeds)
    mean = lambda x: float(np.mean(x))       # noqa: E731
    print("Worked example: lake.json, seeds 1201–1230, day_timeout_s 5.0 → 2.0")
    for name, seed_off in (("err_p95", 0), ("availability", 1), ("err_median", 0), ("err_max", 0)):
        m = {"name": name, "window": "fault"}
        b, a = vals(rb, m), vals(ra, m)
        lo, hi = stats.paired_diff_ci(a, b, mean, B=2000, seed=33 + seed_off)
        print(f"  {name:12s} before {mean(b):8.3f}  after {mean(a):8.3f}  D {mean(a) - mean(b):8.3f}  "
              f"95 % CI [{lo:.3f}, {hi:.3f}]   per-run D min {np.min(a - b):.3f} max {np.max(a - b):.3f}")
    # the same rule judged on the first 5 runs only: what too few runs does
    m = {"name": "err_p95", "window": "fault"}
    b, a = vals(rb, m)[:5], vals(ra, m)[:5]
    lo, hi = stats.paired_diff_ci(a, b, mean, B=2000, seed=33)
    print(f"  first 5 runs only: err_p95 D {mean(a) - mean(b):.3f}  CI [{lo:.3f}, {hi:.3f}]")
    # unpaired (the wrong way): two separate intervals
    b, a = vals(rb, m), vals(ra, m)
    print(f"  separate 95 % CIs of the mean err_p95: before {stats.bootstrap_ci(b, mean, seed=1)}, after "
          f"{stats.bootstrap_ci(a, mean, seed=2)}; per-run spread before sd {np.std(b, ddof=1):.2f} m, "
          f"sd of D {np.std(a - b, ddof=1):.2f} m; sd after {np.std(a, ddof=1):.2f} m; independent "
          f"{np.hypot(np.std(b, ddof=1), np.std(a, ddof=1)):.2f} m; r {np.corrcoef(a, b)[0, 1]:.2f}")
    # the example solution's exploring numbers (idea 1): honest2 on jam, seed 101, as given
    rows = campaign(base, "campaign/jam.json", [101])
    print(f"  idea 1 exploring: jam seed 101, honest2 (fault) {P.metric_value({'name': 'honest2'}, *rows[0]):.3f}")
    for d in (base, short):
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
