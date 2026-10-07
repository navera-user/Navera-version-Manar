import json
import math
import os
import sys

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()


def G(stamp, sigma=3.0, **kw):
    return dict(dict(source="gps", stamp=stamp, valid=True, mode="MEASURED", lat=35.8256, lon=10.6385,
                     sigma=sigma), **kw)


def D(stamp, sigma=None, src="day", **kw):
    return dict(dict(source=src, stamp=stamp, valid=True, mode="MEASURED", lat=35.8259, lon=10.6390,
                     sigma=sigma), **kw)


def arb():
    return load_student("arbiter.py")


def dec(d):
    if not isinstance(d, dict):
        raise CheckFailed(f"decide() should return a dict, it returned {d!r}")
    return d.get("state"), d.get("source")


@c.test("is_fresh(): a fresh GPS is fresh, a 3 s old GPS is not",
        hint="age = now - est['stamp']; fresh means -FUTURE_TOLERANCE_S <= age < TIMEOUTS[source]. "
             "Exactly 3.0 s old is already too old (strictly smaller than).")
def _():
    (f,) = need(arb(), "is_fresh")
    c.eq(f(G(99.0), 100.0), True, "is_fresh(GPS 1 s old)")
    c.eq(f(G(97.0), 100.0), False, "is_fresh(GPS exactly 3 s old)")
    c.eq(f(G(90.0), 100.0), False, "is_fresh(GPS 10 s old)")


@c.test("is_fresh(): each source has its own window (day 5 s, celestial 45 s)",
        hint="Use TIMEOUTS[est['source']], not a single number for everybody.")
def _():
    (f,) = need(arb(), "is_fresh")
    c.eq(f(D(96.0), 100.0), True, "is_fresh(day vision 4 s old)")
    c.eq(f(D(94.0), 100.0), False, "is_fresh(day vision 6 s old)")
    c.eq(f(D(60.0, src="cn"), 100.0), True, "is_fresh(celestial 40 s old)")


@c.test("is_fresh(): a stamp from the future is refused (clock problem)",
        hint="A negative age down to -0.5 s is tolerated; further in the future is not fresh.")
def _():
    (f,) = need(arb(), "is_fresh")
    c.eq(f(G(100.3), 100.0), True, "is_fresh(GPS stamped 0.3 s in the future)")
    c.eq(f(G(160.0), 100.0), False, "is_fresh(GPS stamped 60 s in the future)")


@c.test("is_eligible(): valid, usable mode, finite position",
        hint="Check valid is True, mode in USABLE_MODES, is_fresh(...), and position_ok(lat, lon).")
def _():
    (f,) = need(arb(), "is_eligible")
    c.eq(f(G(99.5), 100.0), True, "is_eligible(a good GPS)")
    c.eq(f(G(99.5, valid=False), 100.0), False, "is_eligible(valid=False)")
    c.eq(f(G(99.5, mode="HELD"), 100.0), False, "is_eligible(mode HELD)")
    c.eq(f(G(99.5, mode="REPLAYED"), 100.0), False, "is_eligible(mode REPLAYED)")
    c.eq(f(D(99.5, mode="PROPAGATED"), 100.0), True, "is_eligible(mode PROPAGATED)")
    c.eq(f(G(99.5, lat=float("nan")), 100.0), False, "is_eligible(latitude NaN)")
    c.eq(f(G(99.5, lat=0.0, lon=0.0), 100.0), False, "is_eligible(position 0, 0)")
    c.eq(f(G(95.0), 100.0), False, "is_eligible(GPS 5 s old)")


@c.test("is_eligible(): unknown sigma is allowed, an impossible sigma is not",
        hint="sigma None is fine (it will be DEGRADED). A NaN, infinite or negative sigma is not a covariance.")
def _():
    (f,) = need(arb(), "is_eligible")
    c.eq(f(D(99.5, sigma=None), 100.0), True, "is_eligible(sigma None)")
    c.eq(f(G(99.5, sigma=float("nan")), 100.0), False, "is_eligible(sigma NaN)")
    c.eq(f(G(99.5, sigma=-4.0), 100.0), False, "is_eligible(sigma -4)")
    c.eq(f(G(99.5, sigma=float("inf")), 100.0), False, "is_eligible(sigma infinite)")


@c.test("classify(): FIX only for a measured fix with a stated sigma up to 25 m",
        hint="Follow the 4 lines of the docstring in order. 'bounded' = sigma is not None and sigma >= 0.01.")
def _():
    (f,) = need(arb(), "classify")
    c.eq(tuple(f(G(1.0, sigma=3.0))), ("FIX", "GPS fix"), "classify(GPS, sigma 3)")
    c.eq(tuple(f(G(1.0, sigma=40.0))), ("DEGRADED", "GPS fix, uncertainty 40 m > 25 m"), "classify(GPS, sigma 40)")
    c.eq(tuple(f(D(1.0, sigma=None))), ("DEGRADED", "day vision fix, uncertainty unknown"),
         "classify(day vision, sigma unknown)")
    c.eq(tuple(f(G(1.0, sigma=0.0))), ("DEGRADED", "GPS fix, uncertainty unknown"), "classify(GPS, sigma 0)")
    c.eq(tuple(f(D(1.0, sigma=80.0, src="night", mode="PROPAGATED"))),
         ("DEGRADED", "night vision solution is propagated (dead-reckoned)"), "classify(night, PROPAGATED)")


@c.test("decide(): INITIALIZING when nothing was ever received, NO_FIX when nothing is usable",
        hint="An empty list -> INITIALIZING. If no estimate is eligible -> NO_FIX, and the reason joins the "
             "why_not() clauses with '; '.")
def _():
    (f,) = need(arb(), "decide")
    c.eq(dec(f([], 100.0)), ("INITIALIZING", None), "decide([]) (state, source)")
    d = f([G(90.0), D(90.0)], 100.0)
    c.eq(dec(d), ("NO_FIX", None), "decide(old GPS, old day) (state, source)")
    c.ok("GPS: stale" in str(d.get("reason")) and "day: stale" in str(d.get("reason")),
         f"the NO_FIX reason should explain both sources, it is {d.get('reason')!r}")


@c.test("decide(): priority GPS > day > night > celestial",
        hint="Walk PRIORITY in order and take the first source that is eligible.")
def _():
    (f,) = need(arb(), "decide")
    c.eq(dec(f([G(99.5), D(99.5)], 100.0)), ("FIX", "gps"), "GPS + day")
    c.eq(dec(f([D(99.5), G(96.0)], 100.0)), ("DEGRADED", "day"), "old GPS + day")
    c.eq(dec(f([D(99.5, src="night", sigma=10.0), D(99.5, src="cn", sigma=900.0)], 100.0)),
         ("FIX", "night"), "night (sigma 10) + celestial")
    c.eq(dec(f([D(99.5, src="cn", sigma=900.0)], 100.0)), ("DEGRADED", "cn"), "celestial alone")


@c.test("decide(): the hold-off keeps the active source for 2 s",
        hint="If `active` is still eligible and the best source has been eligible for less than "
             "SWITCH_HOLDOFF_S (now - eligible_since[best]), keep `active`. Losing `active` switches at once.")
def _():
    (f,) = need(arb(), "decide")
    ests = [G(99.9), D(99.5)]
    c.eq(dec(f(ests, 100.0, "day", {"gps": 99.0, "day": 80.0})), ("DEGRADED", "day"),
         "GPS back for 1 s while day is active")
    c.eq(dec(f(ests, 100.0, "day", {"gps": 97.5, "day": 80.0})), ("FIX", "gps"),
         "GPS back for 2.5 s while day is active")
    c.eq(dec(f([G(99.9), D(90.0)], 100.0, "day", {"gps": 99.9})), ("FIX", "gps"),
         "day lost (stale) while GPS is back for only 0.1 s")


@c.test("a whole flight: your arbiter over a timeline (jam, return, flapping)",
        hint="Run `python3 compare_real.py` and look at the ✘ lines: they show what the real arbiter decided.")
def _():
    a = arb()
    need(a, "decide", "is_eligible", "PRIORITY")
    sys.path.insert(0, os.getcwd())
    import compare_real as cr
    evs = []
    for k in range(20):                    # GPS flapping: valid / invalid every 0.5 s, day steady
        evs.append((0.5 * k, dict(G(0.5 * k, valid=(k % 2 == 0)))))
        if k % 2 == 0:
            evs.append((0.5 * k, D(0.5 * k)))
    evs.sort(key=lambda e: e[0])
    out = cr.run_timeline(a, evs, [x / 4 for x in range(1, 40)])
    srcs = [out[t].get("source") for t in sorted(out)]
    c.ok(set(srcs) <= {"gps", "day"} and "day" in srcs or "gps" in srcs,
         f"during this flight the winner should be GPS or day vision, yours said {sorted(set(map(str, srcs)))}")
    switches = sum(1 for x, y in zip(srcs, srcs[1:]) if x != y)
    c.ok(switches <= 2, f"a GPS flapping every 0.5 s made your output switch {switches} times in 10 s "
                        f"(the real one: at most 2) — the hold-off is missing")


@c.test("you ran the real NAVERA arbiter (real_run.json)",
        hint="Run `python3 compare_real.py` (about 35 s) and wait for the table at the end.")
def _():
    c.file_exists("real_run.json")
    with open("real_run.json") as f:
        data = json.load(f)
    s = data.get("samples", [])
    c.ok(len(s) == 11, f"real_run.json has {len(s)} moments instead of 11 — let compare_real.py finish")
    states = [x["state"] for x in s]
    c.ok(states[0] == "INITIALIZING" and states[1] == "FIX" and states[-1] == "NO_FIX",
         f"real_run.json does not look like a complete run: {states} — run compare_real.py again")


@c.test("your arbiter takes the same decisions as the real one (state + source, 11 moments)",
        hint="python3 compare_real.py prints both side by side; fix the moments marked ✘.")
def _():
    c.ok(os.path.exists("real_run.json"), "real_run.json is missing: run `python3 compare_real.py` first")
    sys.path.insert(0, os.getcwd())
    import compare_real as cr
    with open("real_run.json") as f:
        real = json.load(f)["samples"]
    rows = cr.compare(arb(), real)
    bad = [f"t={r['t']} s ({r['label']}): real {r['state']}/{r['source']}, yours {r['mine_state']}/{r['mine_source']}"
           for r in rows if not r["same"]]
    c.ok(not bad, "different decisions:\n       " + "\n       ".join(bad))
    bad = [f"t={r['t']} s: real '{r['reason']}', yours '{r['mine_reason']}'" for r in rows if not r["same_reason"]]
    c.ok(not bad, "same decisions, but different reason texts:\n       " + "\n       ".join(bad))


ANSWERS = {"Q1": "_eval_source", "Q2": "_sane", "Q3": "_select", "Q4": "_classify", "Q5": "_source_reason"}


@c.test("reading the real code: which method does what (answers.py)",
        hint="Search the file for 'def _' — each method has a docstring that says what it does.")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().replace("()", "").replace("self.", "")
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    (q6,) = need(m, "Q6")
    try:
        ok6 = math.isclose(float(q6), 2.0)
    except (TypeError, ValueError):
        ok6 = False
    if not ok6:
        wrong.append(f"Q6 = {q6!r}")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


c.run()
