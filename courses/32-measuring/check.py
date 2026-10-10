import json
import math
import os
import re

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
DATA = "/data/academy/32-measuring"
FLIGHTS = ("flight_target", "flight_measured", "flight_selective")
# expected values, computed from the recorded flights (simulation) with the lab's rules
EXPECT = {
 "flight_target": {"all": {"n": 284, "cep50": 3.65, "rmse": 13.95, "cep95": 30.9, "max": 64.33},
                   "jam": {"n": 60, "cep50": 20.45, "rmse": 24.13, "cep95": 32.06, "max": 64.33},
                   "baseline": {"n": 60, "cep50": 454.93, "rmse": 501.07, "cep95": 803.85, "max": 847.26},
                   "availability_pct": 100.0, "availability_jam_pct": 100.0, "longest_gap_s": 0,
                   "ci": {"jam_cep50_iid": [17.9, 23.2], "jam_cep50_block": [18.6, 23.2],
                          "diff_cep50_block": [-648.5, -200.7]}},
 "flight_measured": {"all": {"n": 190, "cep50": 4.71, "rmse": 390.13, "cep95": 842.64, "max": 1152.32},
                     "jam": {"n": 60, "cep50": 430.08, "rmse": 514.11, "cep95": 847.33, "max": 1081.64},
                     "baseline": {"n": 60, "cep50": 452.31, "rmse": 516.17, "cep95": 842.91, "max": 890.26},
                     "availability_pct": 100.0, "availability_jam_pct": 100.0, "longest_gap_s": 0,
                     "ci": {"jam_cep50_iid": [389.5, 510.1], "jam_cep50_block": [389.5, 553.9],
                            "diff_cep50_block": [-297.3, 221.1]}},
 "flight_selective": {"all": {"n": 115, "cep50": 3.11, "rmse": 83.25, "cep95": 243.52, "max": 296.44},
                      "jam": {"n": 14, "cep50": 154.0, "rmse": 186.67, "cep95": 286.9, "max": 296.44},
                      "baseline": {"n": 60, "cep50": 452.31, "rmse": 516.17, "cep95": 842.91, "max": 890.26},
                      "availability_pct": 60.53, "availability_jam_pct": 23.33, "longest_gap_s": 13,
                      "ci": {"jam_cep50_iid": [94.2, 238.7], "jam_cep50_block": [114.4, 159.1],
                             "diff_cep50_block": [-308.3, -5.1]}},
}
DEMO = [3.1, 4.0, 2.2, 5.9, 3.7, 4.4, 2.8, 31.0, 3.3, 4.9, 3.0, 6.2]


def M():
    return load_student("measure.py")


def BS():
    return load_student("bootstrap.py")


def row(t, phase="enroute", gps="ok", state="FIX", source="GPS", nlat=35.80, nlon=10.60, tlat=35.80, tlon=10.60):
    return {"t_s": float(t), "phase": phase, "gps_mode": gps, "navera_state": state, "navera_source": source,
            "navera_lat": nlat, "navera_lon": nlon, "truth_lat": tlat, "truth_lon": tlon}


def pair(ci, what):
    try:
        lo, hi = float(ci[0]), float(ci[1])
    except (TypeError, ValueError, IndexError, KeyError):
        raise CheckFailed(f"{what} should be a pair (lo, hi) of numbers, got {ci!r}")
    c.ok(math.isfinite(lo) and math.isfinite(hi) and lo <= hi, f"{what}: ({lo}, {hi}) is not an interval")
    return lo, hi


@c.test("errors(): one (t, error) per en-route row with a NAVERA position",
        hint="Skip rows that are not 'enroute' and rows whose navera_lat is None; error = haversine_m(truth, NAVERA).")
def _():
    (errors,) = need(M(), "errors")
    rows = [row(0, phase="takeoff"), row(1, tlat=35.80 + 100 / 111195.0), row(2, nlat=None, nlon=None), row(3)]
    out = errors(rows)
    c.ok(isinstance(out, list) and len(out) == 2, f"errors() should give 2 pairs here, got {out!r}")
    c.near(out[0][0], 1.0, 1e-9, "the time of the first pair")
    c.near(out[0][1], 100.0, 0.5, "the error of a fix 100 m south of the truth")


@c.test("percentile(): the nearest-rank rule of evaluate_session.py (with Python's round())",
        hint="index = round(p/100 * (n-1)), never beyond n-1. Python rounds 4.5 to 4 (round half to even): "
             "use round(), not math.ceil or +0.5.")
def _():
    (pct,) = need(M(), "percentile")
    v = [5, 1, 9, 3, 7, 2, 8, 4, 6, 11, 10]
    c.near(pct(v, 90), 10, 1e-9, "percentile(1..11, 90)")
    c.near(pct(v, 50), 6, 1e-9, "percentile(1..11, 50)")
    c.near(pct(v, 100), 11, 1e-9, "percentile(1..11, 100)")
    c.near(pct(list(range(1, 11)), 50), 5, 1e-9, "percentile(1..10, 50) (index round(4.5) = 4)")
    c.near(pct([42.0], 95), 42.0, 1e-9, "percentile([42], 95)")


@c.test("stats(): n, mean, rmse, cep50, p90, cep95, max — on the lesson's worked example",
        hint="rmse = sqrt(sum of squares / n); cep50, p90, cep95 = percentile(values, 50 / 90 / 95).")
def _():
    (stats,) = need(M(), "stats")
    s = stats([2.1, 3.4, 1.8, 4.6, 2.9, 3.1, 12.5, 2.4, 3.8, 2.6])
    c.ok(isinstance(s, dict), f"stats() should return a dict, got {s!r}")
    c.eq(s.get("n"), 10, "n")
    for k, want in (("mean", 3.92), ("rmse", 4.9153), ("cep50", 2.9), ("p90", 4.6), ("cep95", 12.5), ("max", 12.5)):
        c.near(s.get(k), want, 1e-3, k)


@c.test("availability() and longest_gap_s(): how often, and the longest hole",
        hint="Only 'enroute' rows (and that gps_mode if given); usable(r) is written for you. The gap counter "
             "goes back to 0 at each usable row; keep the largest value it reached.")
def _():
    av, gap = need(M(), "availability", "longest_gap_s")
    nf = dict(state="NO FIX", nlat=None, nlon=None)
    rows = [row(0), row(1, **nf), row(2, gps="jammed", state="DEGRADED"), row(3, gps="jammed", **nf),
            row(4, gps="jammed", **nf), row(5, phase="arrived", **nf)]
    c.near(av(rows), 40.0, 1e-9, "availability (2 usable of 5 en-route rows)")
    c.near(av(rows, "jammed"), 100 / 3, 1e-6, "availability while jammed (1 of 3)")
    c.eq(gap(rows), 2, "longest_gap_s (rows 3 and 4)")
    c.eq(gap([row(0), row(1)]), 0, "longest_gap_s with no gap")


@c.test("baseline_errors(): repeat the last GPS position during the jam",
        hint="1) index of the first row with gps_mode 'jammed'; 2) the last navera position with source GPS "
             "before it; 3) for each jammed en-route row: haversine_m(truth, that position).")
def _():
    (be,) = need(M(), "baseline_errors")
    d = 1 / 111195.0
    rows = [row(0, tlat=35.80, nlat=35.80), row(1, tlat=35.80 + 10 * d, nlat=35.80 + 10 * d),
            row(2, gps="jammed", source="DAY VISION", tlat=35.80 + 20 * d),
            row(3, gps="jammed", source="DAY VISION", tlat=35.80 + 30 * d), row(4, tlat=35.80 + 40 * d)]
    out = be(rows)
    c.ok(isinstance(out, list) and len(out) == 2, f"baseline_errors() should give 2 pairs here, got {out!r}")
    c.near(out[0][1], 10.0, 0.1, "baseline error 1 s into the jam (the last GPS position was at 10 m)")
    c.near(out[1][1], 20.0, 0.1, "baseline error 2 s into the jam")
    c.eq(be([row(0), row(1)]), [], "baseline_errors() without a jam")


@c.test("bootstrap_ci(): iid percentile bootstrap (the 12-error demo)",
        hint="rng = np.random.default_rng(seed); B times: idx = rng.integers(0, n, size=n), stat(x[idx]); "
             "then np.percentile(reps, [2.5, 97.5]). Run python3 bootstrap.py and compare with the lesson.")
def _():
    (bci,) = need(BS(), "bootstrap_ci")
    import numpy as np
    lo, hi = pair(bci(DEMO, np.median), "bootstrap_ci(demo, np.median)")
    c.near(lo, 3.05, 0.15, "CI of the median, lower end")
    c.near(hi, 5.40, 0.15, "CI of the median, upper end")
    lo, hi = pair(bci(DEMO, np.mean), "bootstrap_ci(demo, np.mean)")
    c.near(lo, 3.46, 0.3, "CI of the mean, lower end")
    c.near(hi, 10.99, 0.5, "CI of the mean, upper end (pulled by the 31 m outlier)")
    c.eq(tuple(bci(DEMO, np.mean, seed=7)), tuple(bci(DEMO, np.mean, seed=7)), "two calls with the same seed")
    lo, hi = pair(bci([4.0] * 20, np.median), "bootstrap_ci(constant data)")
    c.ok(lo == hi == 4.0, f"constant data must give the interval (4, 4), got ({lo}, {hi})")


@c.test("bootstrap_ci(block=10): moving blocks are wider on a trending series",
        hint="k = ceil(n / block) starts from rng.integers(0, n - block + 1, size=k); each start s gives "
             "s, s+1, ..., s+block-1; join them (np.concatenate) and keep the first n.")
def _():
    (bci,) = need(BS(), "bootstrap_ci")
    import numpy as np
    ramp = list(range(60))
    lo1, hi1 = pair(bci(ramp, np.median), "bootstrap_ci(ramp)")
    lo2, hi2 = pair(bci(ramp, np.median, block=10), "bootstrap_ci(ramp, block=10)")
    c.near(hi1 - lo1, 14.5, 3.0, "width of the iid CI of the median of 0..59")
    c.near(hi2 - lo2, 31.5, 5.0, "width of the block-10 CI of the median of 0..59")
    lo3, hi3 = pair(bci(ramp, np.median, block=60), "bootstrap_ci(ramp, block=60)")
    c.ok(lo3 == hi3, "with block = n there is only one possible resample (the data itself): zero width")


@c.test("paired_diff_ci() and wilson()",
        hint="Paired: the SAME idx for a and b in each resample. Wilson: follow the 3 lines of the docstring.")
def _():
    pdc, wil = need(BS(), "paired_diff_ci", "wilson")
    import numpy as np
    b = np.array(DEMO) * 10
    lo, hi = pair(pdc(b + 5.0, b, np.mean), "paired_diff_ci(b + 5, b)")
    c.ok(abs(lo - 5) < 1e-9 and abs(hi - 5) < 1e-9,
         f"a = b + 5 exactly: a paired CI must be (5, 5), got ({lo:.2f}, {hi:.2f}) — are you using the same "
         "indices for a and b?")
    lo, hi = pair(wil(32, 33), "wilson(32, 33)")
    c.near(lo, 0.8468, 1e-3, "wilson(32, 33) lower")
    c.near(hi, 0.9946, 1e-3, "wilson(32, 33) upper")
    lo, hi = pair(wil(0, 10), "wilson(0, 10)")
    c.near(lo, 0.0, 1e-9, "wilson(0, 10) lower")
    c.near(hi, 0.2775, 1e-3, "wilson(0, 10) upper")


@c.test("coverage(): the experiment runs, and coverage.json shows the correlation effect",
        hint="Run python3 bootstrap.py --coverage after TODO 10. iid errors should give ~95 %; correlated "
             "errors with an iid bootstrap much less; blocks should help.")
def _():
    (cov,) = need(BS(), "coverage")
    v = cov(trials=40, n=30, rho=0.0, B=200)
    c.near(v, 0.94, 0.09, "coverage(trials=40, n=30, rho=0, B=200)")
    if not os.path.exists("coverage.json"):
        raise CheckFailed("coverage.json does not exist yet: run python3 bootstrap.py --coverage")
    d = json.load(open("coverage.json"))
    for k in ("iid_n30", "iid_n60", "corr_n60_iid", "corr_n60_block10"):
        c.ok(isinstance(d.get(k), (int, float)), f"coverage.json: {k} is {d.get(k)!r} — run it again after TODO 10")
    c.ok(0.88 <= d["iid_n30"] <= 0.99 and 0.88 <= d["iid_n60"] <= 0.99,
         f"independent errors: coverage should be close to 95 %, got {d['iid_n30']}, {d['iid_n60']}")
    c.ok(d["corr_n60_iid"] < 0.8, f"correlated errors + iid bootstrap: {d['corr_n60_iid']} (expected well below 95 %)")
    c.ok(d["corr_n60_block10"] > d["corr_n60_iid"] + 0.05, "the block bootstrap should cover more often than iid")


def results(name):
    p = f"results_{name}.json"
    if not os.path.exists(p):
        raise CheckFailed(f"{p} does not exist yet: run python3 measure.py {DATA}/{name}.csv")
    with open(p) as f:
        return json.load(f)


@c.test("results_flight_*.json: errors, baseline, availability and gap of the three flights",
        hint=f"Run `python3 measure.py {DATA}/flight_*.csv` after TODO 1–5 (all three flights).")
def _():
    for name in FLIGHTS:
        r, e = results(name), EXPECT[name]
        for part in ("all", "jam", "baseline"):
            got = r.get(part) or {}
            c.ok(got.get("n") == e[part]["n"], f"{name} {part}: n = {got.get('n')}, expected {e[part]['n']}")
            for k in ("cep50", "rmse", "cep95", "max"):
                c.near(got.get(k), e[part][k], max(0.5, 0.01 * e[part][k]), f"{name} {part} {k} (m)")
        for k in ("availability_pct", "availability_jam_pct"):
            c.near(r.get(k), e[k], 0.2, f"{name} {k}")
        c.eq(r.get("longest_gap_s"), e["longest_gap_s"], f"{name} longest_gap_s")


@c.test("results_flight_*.json: the 95 % confidence intervals",
        hint="measure.py calls your bootstrap_ci and paired_diff_ci (block 10 s): finish TODO 7–8, then run "
             "measure.py on the three flights again.")
def _():
    for name in FLIGHTS:
        ci = results(name).get("ci") or {}
        for k, (wlo, whi) in EXPECT[name]["ci"].items():
            lo, hi = pair(ci.get(k), f"{name} ci.{k}")
            tol = max(2.0, 0.12 * (whi - wlo))
            c.ok(abs(lo - wlo) <= tol and abs(hi - whi) <= tol,
                 f"{name} ci.{k} = [{lo:.1f}, {hi:.1f}], expected about [{wlo}, {whi}]")


@c.test("the three plots exist, with the baseline (TODO 6)",
        hint="Run measure.py on the three flights; TODO 6 draws the baseline with ax.plot(..., '-', color='#dc2626').")
def _():
    for n in FLIGHTS:
        c.file_exists(f"error_{n}.png")
    src = open("measure.py").read()
    todo6 = src[src.find("TODO 6"):src.find("ax.axvspan")]
    c.ok("ax.plot" in todo6, "TODO 6: the baseline line is not drawn yet")


ANSWERS = {"Q1": "b", "Q2": "c", "Q3": "a", "Q4": "c", "Q5": "a"}


@c.test("answers.py: reading your numbers and evaluate_session.py",
        hint="Q6 and Q7 are in the 'stated accuracy vs truth' table of evaluate_session.py; Q8 is 100 × the lower "
             "end of wilson(32, 33).")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    for q, good, tol in (("Q6", 59.0, 1.5), ("Q7", 21.0, 1.0), ("Q8", 84.7, 0.2)):
        (v,) = need(m, q)
        try:
            ok = math.isfinite(float(v)) and abs(float(v) - good) <= tol
        except (TypeError, ValueError):
            ok = False
        if not ok:
            wrong.append(f"{q} = {v!r}")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


def section(text, title):
    m = re.search(r"^## " + re.escape(title) + r".*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def graded_text():
    """report.md without the instructions above its first heading (they quote the placeholders)."""
    if not os.path.exists("report.md"):
        return ""
    text = open("report.md", encoding="utf-8", errors="replace").read()
    first = text.find("\n## ")
    return text[first:] if first >= 0 else text


@c.test("report.md: complete, with your numbers and confidence intervals",
        hint="No '(fill in' paragraph and no '(m)', '(%)', '(s)', '[lo, hi]' cell left; the jam CEP50 of the target "
             "and measured flights, the CI of the measured flight's difference, and the selective flight's "
             "availability while jammed — all rounded to whole numbers.")
def _():
    c.file_exists("report.md")
    text = graded_text()
    left = [p for p in ("(fill in", "(m)", "(%)", "(s)", "[lo, hi]") if p in text]
    c.ok(not left, f"placeholders still there: {left}")
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text.replace("−", "-"))]

    def has(v, tol=1.0):
        return any(abs(n - v) <= tol for n in nums)
    c.ok(has(round(EXPECT["flight_target"]["jam"]["cep50"])), "the target flight's jam CEP50 (≈ 20 m) is missing")
    c.ok(has(round(EXPECT["flight_measured"]["jam"]["cep50"])), "the measured flight's jam CEP50 (≈ 430 m) is missing")
    c.ok(has(round(EXPECT["flight_selective"]["availability_jam_pct"])),
         "the selective flight's availability while jammed (≈ 23 %) is missing")
    mine = (results("flight_measured").get("ci") or {}).get("diff_cep50_block")
    lo, hi = pair(mine, "your flight_measured ci.diff_cep50_block")
    c.ok(has(round(lo)) and has(round(hi)),
         f"the CI of the difference for the measured flight (your [{lo:.0f}, {hi:.0f}]) is not in the report")


@c.test("report.md: an honest analysis (difference, validity, conclusion)",
        hint="Sections 'Is the difference real?', 'Validity: simulation vs field' (60+ words) and 'Conclusion' "
             "(100+ words); name the baseline, the confidence interval, availability, and say the flights are "
             "simulated over Sousse.")
def _():
    text = graded_text()
    c.ok(text and "(fill in" not in text, "write your own text in place of the '(fill in …)' paragraphs first")
    diff, val, concl = (section(text, t) for t in ("Is the difference real?", "Validity", "Conclusion"))
    c.ok(len(diff.split()) >= 40, f"'Is the difference real?' has {len(diff.split())} words (at least 40)")
    c.ok(len(val.split()) >= 60, f"'Validity' has {len(val.split())} words (at least 60)")
    c.ok(len(concl.split()) >= 100, f"the conclusion has {len(concl.split())} words (at least 100)")
    low = text.lower()
    for word, why in (("baseline", "the baseline"), ("confidence interval", "the confidence interval"),
                      ("availab", "availability"), ("simulat", "that the flights are simulated"),
                      ("sousse", "where they were flown (Sousse)")):
        c.ok(word in low, f"the report does not mention {why}")
    c.ok("contain" in diff.lower() or "includ" in diff.lower() or " 0" in diff,
         "say whether each CI of the difference contains 0")


c.run()
