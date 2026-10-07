import json
import math
import os
import re
import sys

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
sys.path.insert(0, os.getcwd())


def est(source, stamp, sigma=None, **kw):
    if sigma is None:
        cov, ctype = [0.0] * 9, "UNKNOWN"
    else:
        v = float(sigma) ** 2
        cov, ctype = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 * v], "APPROXIMATED"
    e = dict(source=source, stamp=stamp, valid=True, mode="MEASURED", lat=23.588, lon=58.383,
             cov=cov, cov_type=ctype)
    e.update(kw)
    return e


def G(stamp, sigma=3.0, **kw):
    return est("gps", stamp, sigma, **kw)


def D(stamp, sigma=None, src="day", **kw):
    return est(src, stamp, sigma, **dict(dict(lat=23.5884, lon=58.3836), **kw))


def arb():
    return load_student("arbiter.py")


def dec(d):
    if not isinstance(d, dict):
        raise CheckFailed(f"decide()/step() should return a dict, it returned {d!r}")
    return d.get("state"), d.get("source")


def close(got, want, tol, what):
    c.near(got, want, tol, what)


# ------------------------------------------------------------------ the predicates
@c.test("is_fresh(): per-source windows, strict upper bound, future stamps refused",
        hint="age = now - est['stamp']; fresh means -FUTURE_TOLERANCE_S <= age < TIMEOUTS[source]. "
             "Exactly 3.0 s old is already stale for GPS (strictly smaller than).")
def _():
    (f,) = need(arb(), "is_fresh")
    for e, now, want, what in [(G(99.0), 100.0, True, "GPS 1 s old"), (G(97.0), 100.0, False, "GPS exactly 3 s old"),
                               (D(96.0), 100.0, True, "day 4 s old"), (D(94.0), 100.0, False, "day 6 s old"),
                               (D(60.0, src="cn"), 100.0, True, "celestial 40 s old"),
                               (G(100.3), 100.0, True, "GPS 0.3 s in the future"),
                               (G(160.0), 100.0, False, "GPS 60 s in the future")]:
        c.eq(f(e, now), want, f"is_fresh({what})")


@c.test("cov_ok(): finite, non-negative variances, symmetric, horizontal block PSD",
        hint="Four guard clauses. PSD of a symmetric 2x2 block with a non-negative diagonal: "
             "determinant cov[0]*cov[4] - cov[1]*cov[3] >= -tol. Wrap the float conversion in try/except.")
def _():
    (f,) = need(arb(), "cov_ok")
    good = [9.0, 1.0, 0.0, 1.0, 4.0, 0.0, 0.0, 0.0, 36.0]
    cases = [(good, True, "a valid covariance"), ([0.0] * 9, True, "all zeros"),
             ([9.0, 7.0, 0, 7.0, 4.0, 0, 0, 0, 1.0], False, "correlation > 1 (det < 0)"),
             ([9.0, 1.0, 0, 2.0, 4.0, 0, 0, 0, 1.0], False, "not symmetric"),
             ([-1.0, 0, 0, 0, 4.0, 0, 0, 0, 1.0], False, "negative variance"),
             ([float("nan")] + good[1:], False, "a NaN"), ([float("inf")] + good[1:], False, "an infinity"),
             (good[:4], False, "only 4 numbers"), (None, False, "None")]
    for cov, want, what in cases:
        c.eq(f(cov), want, f"cov_ok({what})")


@c.test("stated_sigma(): only a bounded covariance type with sigma >= 1 cm states an accuracy",
        hint="Type not in BOUNDED_TYPES -> None. sigma = sqrt(max(cov[0], cov[4])); below MIN_STATED_SIGMA_M -> None.")
def _():
    (f,) = need(arb(), "stated_sigma")
    close(f(G(1.0, sigma=3.0)), 3.0, 1e-9, "stated_sigma(GPS sigma 3)")
    e = G(1.0)
    e["cov"] = [16.0, 0, 0, 0, 100.0, 0, 0, 0, 1.0]
    close(f(e), 10.0, 1e-9, "stated_sigma(East var 16, North var 100)")
    c.eq(f(D(1.0)), None, "stated_sigma(type UNKNOWN)")
    c.eq(f(G(1.0, sigma=0.0)), None, "stated_sigma(APPROXIMATED, all zeros)")
    c.eq(f(G(1.0, sigma=5.0, cov_type="GARBAGE")), None, "stated_sigma(an undefined type)")


@c.test("is_eligible(): valid, usable mode, fresh, sane position, sane covariance",
        hint="One guard clause per rule; position_ok() and cov_ok() do the last two.")
def _():
    (f,) = need(arb(), "is_eligible")
    cases = [(G(99.5), True, "a good GPS"), (G(99.5, valid=False), False, "valid=False"),
             (G(99.5, mode="HELD"), False, "mode HELD"), (G(99.5, mode="REPLAYED"), False, "mode REPLAYED"),
             (D(99.5, mode="PROPAGATED"), True, "mode PROPAGATED"), (D(99.5), True, "type UNKNOWN, zeros"),
             (G(99.5, lat=float("nan")), False, "latitude NaN"), (G(99.5, lat=0.0, lon=0.0), False, "(0, 0)"),
             (G(95.0), False, "GPS 5 s old"),
             (G(99.5, cov=[9.0, 0, 0, 0, -4.0, 0, 0, 0, 1.0]), False, "a negative variance")]
    for e, want, what in cases:
        c.eq(f(e, 100.0), want, f"is_eligible({what})")


@c.test("classify(): FIX only for a MEASURED fix with a stated sigma up to 25 m",
        hint="Follow the 4 lines of the docstring in that order; use stated_sigma().")
def _():
    (f,) = need(arb(), "classify")
    c.eq(tuple(f(G(1.0, sigma=3.0))), ("FIX", "GPS fix"), "classify(GPS, sigma 3)")
    c.eq(tuple(f(G(1.0, sigma=25.0))), ("FIX", "GPS fix"), "classify(GPS, sigma exactly 25)")
    c.eq(tuple(f(G(1.0, sigma=40.0))), ("DEGRADED", "GPS fix, uncertainty 40 m > 25 m"), "classify(GPS, sigma 40)")
    c.eq(tuple(f(D(1.0, sigma=30.0))), ("DEGRADED", "day vision fix, uncertainty 30 m > 25 m"),
         "classify(day vision, sigma 30)")
    c.eq(tuple(f(D(1.0))), ("DEGRADED", "day vision fix, uncertainty unknown"), "classify(day, UNKNOWN)")
    c.eq(tuple(f(G(1.0, sigma=0.0))), ("DEGRADED", "GPS fix, uncertainty unknown"), "classify(GPS, sigma 0)")
    c.eq(tuple(f(D(1.0, sigma=80.0, src="night", mode="PROPAGATED"))),
         ("DEGRADED", "night vision solution is propagated (dead-reckoned)"), "classify(night, PROPAGATED)")


# ------------------------------------------------------------------ the decision
@c.test("decide(): INITIALIZING, NO_FIX with one clause per source, priority order",
        hint="Empty list -> INITIALIZING. No eligible estimate -> NO_FIX, reason = why_not() clauses in "
             "PRIORITY order joined with '; '. Otherwise the first eligible source in PRIORITY.")
def _():
    (f,) = need(arb(), "decide")
    c.eq(dec(f([], 100.0)), ("INITIALIZING", None), "decide([])")
    d = f([D(90.0), G(90.0)], 100.0)
    c.eq(dec(d), ("NO_FIX", None), "decide(old day, old GPS)")
    c.eq(d.get("reason"), "GPS: stale (10.0s>3.0s); day: stale (10.0s>5.0s)", "the NO_FIX reason")
    c.eq(dec(f([G(99.5), D(99.5)], 100.0)), ("FIX", "gps"), "GPS + day")
    c.eq(dec(f([D(99.5), G(96.0)], 100.0)), ("DEGRADED", "day"), "old GPS + day")
    c.eq(dec(f([D(99.5, src="night", sigma=10.0), D(99.5, src="cn", sigma=900.0)], 100.0)),
         ("FIX", "night"), "night (sigma 10) + celestial")


@c.test("decide(): the hold-off (and its holdoff_s parameter)",
        hint="If `active` is eligible, best != active and now - eligible_since[best] < holdoff_s, keep `active`. "
             "Losing `active` switches at once. Use the holdoff_s argument, not the constant.")
def _():
    (f,) = need(arb(), "decide")
    ests = [G(99.9), D(99.5)]
    c.eq(dec(f(ests, 100.0, "day", {"gps": 99.0, "day": 80.0})), ("DEGRADED", "day"), "GPS back 1 s, day active")
    c.eq(dec(f(ests, 100.0, "day", {"gps": 97.5, "day": 80.0})), ("FIX", "gps"), "GPS back 2.5 s, day active")
    c.eq(dec(f(ests, 100.0, "day", {"gps": 98.0, "day": 80.0})), ("FIX", "gps"), "GPS back exactly 2.0 s")
    c.eq(dec(f([G(99.9), D(90.0)], 100.0, "day", {"gps": 99.9})), ("FIX", "gps"), "day lost, GPS back 0.1 s")
    c.eq(dec(f(ests, 100.0, "day", {"gps": 97.5, "day": 80.0}, holdoff_s=4.0)), ("DEGRADED", "day"),
         "GPS back 2.5 s with holdoff_s=4")


# ------------------------------------------------------------------ the state machine
@c.test("Arbiter.receive() and step(): latest estimates, eligible_since, switches",
        hint="receive: keep the newest per source, drop a GPS older than the stored one. step: update "
             "eligible_since FIRST (setdefault / pop), then decide(), then record a switch if the source changed.")
def _():
    a_mod = arb()
    (A,) = need(a_mod, "Arbiter")
    a = A()
    a.receive(G(10.0))
    a.receive(G(9.0, lat=24.0))
    c.ok(isinstance(getattr(a, "latest", None), dict) and a.latest.get("gps", {}).get("stamp") == 10.0,
         "a late GPS fix (stamp 9.0 after 10.0) should be dropped by receive()")
    a.receive(D(10.0))
    a.receive(D(9.5))
    c.eq(a.latest["day"]["stamp"], 9.5, "the stored day stamp (only GPS drops late fixes)")
    d = a.step(10.0)
    c.eq(dec(d), ("FIX", "gps"), "step(10.0)")
    c.eq(a.eligible_since, {"gps": 10.0, "day": 10.0}, "eligible_since after step(10.0)")
    c.eq(a.switches, [(10.0, None, "gps")], "switches after step(10.0)")
    a.step(11.0)
    c.eq(a.eligible_since, {"gps": 10.0, "day": 10.0}, "eligible_since after step(11.0) (setdefault keeps the first)")
    a.step(13.5)
    c.eq(a.eligible_since, {"day": 10.0}, "eligible_since at 13.5 s (GPS is 3.5 s old: popped)")
    c.eq((a.active, a.switches[-1]), ("day", (13.5, "gps", "day")), "(active, last switch) at 13.5 s")


@c.test("the state machine over time: exact switch instant and a flapping GPS",
        hint="Run `python3 arbiter.py`: the demo prints the switches. GPS returning at 10.0 s must take over at "
             "12.0 s, not before. A flapping GPS must not make the output zig-zag.")
def _():
    import compare_real as cr
    a_mod = arb()
    need(a_mod, "Arbiter")
    evs = []
    for k in range(60):
        t = 0.5 * k
        evs.append((t, D(t)))
        if t >= 10.0:
            evs.append((t, G(t)))
    _, a = cr.run_timeline(a_mod, sorted(evs, key=lambda e: e[0]), [], end_s=30.0)
    sw = [(round(t, 2), o, n) for t, o, n in getattr(a, "switches", [])]
    c.eq(sw, [(0.0, None, "day"), (12.0, "day", "gps")], "switches (GPS back at 10.0 s)")
    evs = []
    for k in range(40):                     # GPS valid / invalid every 0.5 s, day steady
        evs.append((0.5 * k, G(0.5 * k, valid=(k % 2 == 0))))
        evs.append((0.5 * k, D(0.5 * k)))
    _, a = cr.run_timeline(a_mod, sorted(evs, key=lambda e: e[0]), [], end_s=20.0)
    n = len([s for s in a.switches if s[1] is not None])
    c.ok(n <= 1, f"a GPS flapping every 0.5 s made your output switch {n} times in 20 s (expected at most 1)")


# ------------------------------------------------------------------ the race
@c.test("race: your decisions = the real arbiter's at 11 moments (real_run.json)",
        hint="Run `python3 compare_real.py` (about 35 s) and fix the moments marked ✘. "
             "`python3 compare_real.py --replay` re-compares without restarting ROS.")
def _():
    import compare_real as cr
    c.file_exists("real_run.json")
    with open("real_run.json") as fh:
        data = json.load(fh)
    s = data.get("samples", [])
    c.ok(len(s) == 11 and "history" in data,
         "real_run.json is incomplete or from the old lab version — run python3 compare_real.py again")
    states = [x["state"] for x in s]
    c.ok(states[0] == "INITIALIZING" and states[1] == "FIX" and states[-1] == "NO_FIX",
         f"real_run.json does not look like a complete run: {states}")
    rows = cr.compare(arb(), s)
    bad = [f"t={r['t']} s ({r['label']}): real {r['state']}/{r['source']}, yours {r['mine_state']}/{r['mine_source']}"
           for r in rows if not r["same"]]
    c.ok(not bad, "different decisions:\n       " + "\n       ".join(bad))
    bad = [f"t={r['t']} s: real '{r['reason']}', yours '{r['mine_reason']}'" for r in rows if not r["same_reason"]]
    c.ok(not bad, "same decisions, different reason texts:\n       " + "\n       ".join(bad))


@c.test("race: your source switches happen at the same instants as the real ones",
        hint="compare_real.py prints the switch table. A late switch usually means eligible_since is "
             "updated after decide() or reset when it should not be.")
def _():
    import compare_real as cr
    c.ok(os.path.exists("real_run.json"), "real_run.json is missing: run python3 compare_real.py")
    with open("real_run.json") as fh:
        hist = json.load(fh).get("history", [])
    rows, problems = cr.compare_switches(arb(), hist)
    c.ok(len(rows) >= 5, f"the real run has only {len(rows)} switches — run compare_real.py again")
    c.ok(not problems, "\n       ".join(problems))


# ------------------------------------------------------------------ the experiments
def exp():
    return load_student("experiment.py")


HOLD = {0.0: (27.1, 0.6467, 0.0), 2.0: (12.7, 0.312, 200.8), 8.0: (1.3, 0.0433, 362.0)}
FRESH = {3.0: (0.784, 79, 119.9), 5.0: (0.9113, 19, 199.9)}


@c.test("experiment A: holdoff_metrics() on the flapping GPS (h = 0, 2, 8 s)",
        hint="Follow the docstring exactly: receive+step on arrivals, step+measure on ticks only; count switches "
             "whose OLD source is not None; gps_unused_s = TICK_S x ticks where GPS is eligible but not used.")
def _():
    m = exp()
    hm, ev = need(m, "holdoff_metrics", "flapping_gps_events")
    evs = ev()
    for h, (sw, share, unused) in HOLD.items():
        r = hm(evs, h)
        c.ok(isinstance(r, dict), f"holdoff_metrics() should return a dict, got {r!r}")
        close(r.get("switches_per_min"), sw, 0.15, f"switches_per_min at h={h}")
        close(r.get("gps_share"), share, 0.003, f"gps_share at h={h}")
        close(r.get("gps_unused_s"), unused, 1.0, f"gps_unused_s at h={h}")


@c.test("experiments B and C: freshness_metrics(), fuse(), true_sigma()",
        hint="B: one pass over t_k = k*SAMPLE_S, strict age < window_s. C: weights 1/s^2 normalised; "
             "var = w1²s1² + w2²s2² + 2·w1·w2·rho·s1·s2.")
def _():
    m = exp()
    fm, frames, fuse, ts = need(m, "freshness_metrics", "day_frame_times", "fuse", "true_sigma")
    ft = frames()
    for w, (av, drops, err) in FRESH.items():
        r = fm(ft, w)
        c.ok(isinstance(r, dict), f"freshness_metrics() should return a dict, got {r!r}")
        close(r.get("availability"), av, 0.002, f"availability at T={w}")
        close(r.get("dropouts"), drops, 2, f"dropouts at T={w}")
        close(r.get("max_error_m"), err, 1.0, f"max_error_m at T={w}")
    x, s = fuse(2.0, 3.0, -20.0, 30.0)
    close(x, 1.78218, 1e-3, "fuse(2, 3, -20, 30) value")
    close(s, 2.98511, 1e-3, "fuse(2, 3, -20, 30) sigma")
    close(fuse(5.0, 2.0, 5.0, 2.0)[1], math.sqrt(2.0), 1e-6, "fuse of two equal sigmas 2 -> sigma")
    close(ts(3.0, 30.0, 0.8), 3.21287, 1e-3, "true_sigma(3, 30, 0.8)")
    close(ts(3.0, 30.0, 0.0), 2.98511, 1e-3, "true_sigma(3, 30, 0) (= the claimed sigma)")


# ------------------------------------------------------------------ the written analysis
SECTIONS = ["Hold-off", "Freshness", "Selection or fusion", "My arbiter against the real one", "Limits"]


def _numbers(text):
    return [float(x) for x in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", text.replace(",", ""))]


def _mentions(text, value, rel=0.02, pct=False):
    vals = [value] + ([value * 100.0] if pct else [])
    return any(abs(n - v) <= max(rel * abs(v), 0.051) for n in _numbers(text) for v in vals)


@c.test("results.json (python3 experiment.py) and report.md: 5 sections, real numbers, ≥ 350 words",
        hint="Run python3 experiment.py, then write each section of report.md in your own words, quoting "
             "the numbers you measured (e.g. switches per minute at h = 0 and 2 s, availability at 3 and 5 s, "
             "the claimed and true fused sigma).")
def _():
    c.file_exists("results.json")
    with open("results.json") as fh:
        res = json.load(fh)
    h = {r["holdoff_s"]: r for r in res.get("holdoff", [])}
    c.ok(2.0 in h and abs(h[2.0]["switches_per_min"] - 12.7) <= 0.15,
         "results.json is not from your finished experiment.py — run python3 experiment.py again")
    c.file_exists("report.md")
    text = re.sub(r"<!--.*?-->", "", open("report.md", encoding="utf-8").read(), flags=re.S)
    c.ok("TODO" not in text, "report.md still contains TODO")
    parts = re.split(r"^##\s+", text, flags=re.M)
    sec = {}
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        for s in SECTIONS:
            if s.lower() in title.lower():
                sec[s] = body
    missing = [s for s in SECTIONS if s not in sec]
    c.ok(not missing, f"report.md misses the section(s): {missing} (keep the '## ' headings of the template)")
    short = [s for s in SECTIONS if len(sec[s].split()) < 40]
    c.ok(not short, f"these sections have fewer than 40 words: {short}")
    words = sum(len(sec[s].split()) for s in SECTIONS)
    c.ok(words >= 350, f"the report has {words} words in its sections, at least 350 are needed")
    f = {r["window_s"]: r for r in res["freshness"]}
    need_nums = {
        "Hold-off": [(h[0.0]["switches_per_min"], False), (h[2.0]["switches_per_min"], False),
                     (h[2.0]["gps_unused_s"], False)],
        "Freshness": [(f[3.0]["availability"], True), (f[5.0]["availability"], True), (f[5.0]["max_error_m"], False)],
        "Selection or fusion": [(res["fusion"]["claimed_sigma_m"], False), (res["fusion"]["true_sigma_rho_0.8_m"], False),
                                (res["fusion"]["spoofed_fused_m"], False)],
    }
    for s, vals in need_nums.items():
        hits = sum(_mentions(sec[s], v, pct=p) for v, p in vals)
        c.ok(hits >= 2, f"section '{s}' should quote at least 2 of your measured numbers "
                        f"({', '.join(f'{v:.3g}' for v, _ in vals)}); it quotes {hits}")
    c.ok(len(_numbers(sec["My arbiter against the real one"])) >= 2,
         "section 'My arbiter against the real one' should give numbers (decisions identical, switch instants)")


# ------------------------------------------------------------------ code reading
ANSWERS = {"Q1": "_eval_source", "Q2": "_sane", "Q3": "_select", "Q4": "_classify", "Q5": "_source_reason",
           "Q6": "_tick"}
NUMS = {"Q7": (2.0, 0.01), "Q8": (3.0, 0.01), "Q9": (3.2, 0.01)}


@c.test("reading the real code (answers.py, 9 questions)",
        hint="Search estimator_node.py for 'def _' and read the docstrings; the numbers are in the yaml file, in "
             "the declare_float lines, and in publish_rate_hz (one tick = 1 / rate).")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().replace("()", "").replace("self.", "")
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    for q, (good, tol) in NUMS.items():
        (v,) = need(m, q)
        try:
            ok = abs(float(v) - good) <= tol
        except (TypeError, ValueError):
            ok = False
        if not ok:
            wrong.append(f"{q} = {v!r}")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


c.run()
