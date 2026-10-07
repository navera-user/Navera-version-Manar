import json
import math
import os
import re

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
DATA = "/data/academy/29-measuring"
# expected values, from the recorded flights (simulation)
EXPECT = {
 "flight_target": {
  "all": {
   "n": 284,
   "median": 3.65,
   "p90": 26.48,
   "max": 64.33
  },
  "jam": {
   "n": 60,
   "median": 20.45,
   "p90": 31.62,
   "max": 64.33
  },
  "baseline": {
   "n": 60,
   "median": 454.93,
   "p90": 761.66,
   "max": 847.26
  },
  "availability_pct": 100.0,
  "availability_jam_pct": 100.0
 },
 "flight_measured": {
  "all": {
   "n": 190,
   "median": 4.71,
   "p90": 701.78,
   "max": 1152.32
  },
  "jam": {
   "n": 60,
   "median": 430.08,
   "p90": 742.92,
   "max": 1081.64
  },
  "baseline": {
   "n": 60,
   "median": 452.31,
   "p90": 797.13,
   "max": 890.26
  },
  "availability_pct": 100.0,
  "availability_jam_pct": 100.0
 },
 "eval": {
  "within_2s": 59.0,
  "honest": 21.0
 }
}


def M():
    return load_student("measure.py")


def row(t, phase="enroute", gps="ok", state="FIX", source="GPS", nlat=35.80, nlon=10.60, tlat=35.80, tlon=10.60):
    return {"t_s": float(t), "phase": phase, "gps_mode": gps, "navera_state": state, "navera_source": source,
            "navera_lat": nlat, "navera_lon": nlon, "truth_lat": tlat, "truth_lon": tlon}


@c.test("errors(): one (t, error) per en-route row with a NAVERA position",
        hint="Skip rows not 'enroute' and rows whose navera_lat is None; error = haversine_m(truth, NAVERA).")
def _():
    (errors,) = need(M(), "errors")
    rows = [row(0, phase="takeoff"), row(1, tlat=35.80 + 100 / 111195.0), row(2, nlat=None, nlon=None),
            row(3)]
    out = errors(rows)
    c.ok(isinstance(out, list) and len(out) == 2, f"errors() should give 2 pairs here, got {out!r}")
    c.near(out[0][0], 1.0, 1e-9, "the time of the first pair")
    c.near(out[0][1], 100.0, 0.5, "the error of a fix 100 m south of the truth")


@c.test("percentile(): the nearest-rank rule of evaluate_session.py",
        hint="s = sorted(values); return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]")
def _():
    (pct,) = need(M(), "percentile")
    v = [5, 1, 9, 3, 7, 2, 8, 4, 6, 11, 10]
    c.near(pct(v, 90), 10, 1e-9, "percentile(1..11, 90)")
    c.near(pct(v, 50), 6, 1e-9, "percentile(1..11, 50)")
    c.near(pct(v, 100), 11, 1e-9, "percentile(1..11, 100)")
    c.near(pct([42.0], 90), 42.0, 1e-9, "percentile([42], 90)")


@c.test("stats(): n, mean, median, p90, max", hint="Use percentile(values, 50) and percentile(values, 90).")
def _():
    (stats,) = need(M(), "stats")
    s = stats([5, 1, 9, 3, 7, 2, 8, 4, 6, 10, 100])
    c.ok(isinstance(s, dict), f"stats() should return a dict, got {s!r}")
    c.eq(s.get("n"), 11, "n")
    c.near(s.get("mean"), 155 / 11, 1e-9, "mean (one outlier at 100)")
    c.near(s.get("median"), 6, 1e-9, "median")
    c.near(s.get("p90"), 10, 1e-9, "p90")
    c.near(s.get("max"), 100, 1e-9, "max")


@c.test("availability(): the share of time with a usable position",
        hint="Rows en route (and with that gps_mode if given); usable = state FIX or DEGRADED and navera_lat "
             "not None. Return a percentage (0..100).")
def _():
    (av,) = need(M(), "availability")
    rows = [row(0), row(1, state="NO FIX", nlat=None, nlon=None), row(2, gps="jammed", state="DEGRADED"),
            row(3, gps="jammed", state="NO FIX", nlat=None, nlon=None), row(4, phase="arrived")]
    c.near(av(rows), 50.0, 1e-9, "availability (2 usable of 4 en-route rows)")
    c.near(av(rows, "jammed"), 50.0, 1e-9, "availability while jammed (1 of 2)")


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


def results(name):
    p = f"results_{name}.json"
    if not os.path.exists(p):
        raise CheckFailed(f"{p} does not exist yet: run python3 measure.py {DATA}/{name}.csv")
    with open(p) as f:
        return json.load(f)


for _name in ("flight_target", "flight_measured"):
    @c.test(f"{_name}: your numbers (errors, availability, baseline)",
            hint=f"Run `python3 measure.py {DATA}/{_name}.csv` after TODO 1–5 and compare with the checks above.")
    def _(name=_name):
        r, e = results(name), EXPECT[name]
        for part in ("all", "jam", "baseline"):
            got = r.get(part) or {}
            c.ok(got.get("n") == e[part]["n"], f"{part}: n = {got.get('n')}, expected {e[part]['n']}")
            for k in ("median", "p90", "max"):
                c.near(got.get(k), e[part][k], max(0.5, 0.01 * e[part][k]), f"{part} {k} (m)")
        c.near(r.get("availability_pct"), e["availability_pct"], 0.2, "availability of the flight (%)")
        c.near(r.get("availability_jam_pct"), e["availability_jam_pct"], 0.2, "availability while jammed (%)")


@c.test("the two plots exist, with the baseline (TODO 6)",
        hint="Run measure.py on both flights; TODO 6 draws the baseline with ax.plot(..., '-', color='#dc2626').")
def _():
    for n in ("flight_target", "flight_measured"):
        c.file_exists(f"error_{n}.png")
    src = open("measure.py").read()
    todo6 = src[src.find("TODO 6"):src.find("ax.axvspan")]
    c.ok("ax.plot" in todo6, "TODO 6: the baseline line is not drawn yet")


ANSWERS = {"Q1": "b", "Q2": "b", "Q3": "a"}


@c.test("evaluate_session.py and your conclusions (answers.py)",
        hint="Q4 and Q5 are in the 'stated accuracy vs truth' table of evaluate_session.py.")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    for q, good, tol in (("Q4", EXPECT["eval"]["within_2s"], 1.5), ("Q5", EXPECT["eval"]["honest"], 1.0)):
        (v,) = need(m, q)
        try:
            ok = math.isfinite(float(v)) and abs(float(v) - good) <= tol
        except (TypeError, ValueError):
            ok = False
        if not ok:
            wrong.append(f"{q} = {v!r}")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


@c.test("report.md: an honest result, with your numbers",
        hint="Replace every (…) placeholder; the table with your rounded numbers; a conclusion of 80+ words that "
             "mentions the baseline and that the flights are simulated.")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8", errors="replace").read()
    left = [p for p in ("(m)", "(%)", "(Which flights", "(One honest paragraph") if p in text]
    c.ok(not left, f"placeholders still there: {left}")
    concl = text.split("## Conclusion", 1)[-1]
    c.ok(len(concl.split()) >= 80, f"the conclusion has {len(concl.split())} words (at least 80)")
    low = text.lower()
    c.ok("baseline" in low, "the report does not mention the baseline")
    c.ok("simulat" in low, "the report does not say the flights are simulated")
    t = round(EXPECT["flight_target"]["jam"]["median"])
    b = round(EXPECT["flight_measured"]["jam"]["median"])
    nums = {int(x) for x in re.findall(r"\b\d+\b", text)}
    c.ok(any(abs(t - n) <= 1 for n in nums) and any(abs(b - n) <= 1 for n in nums),
         "the table should contain your jam medians of both flights (rounded to the metre)")


c.run()
