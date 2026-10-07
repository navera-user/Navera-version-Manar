import os
import sys

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
sys.path.insert(0, os.getcwd())


def S():
    return load_student("spoof.py")


def run(name):
    """[(t, state, reason, offset)] of the student's guard on a scenario."""
    m = S()
    play, Guard = need(m, "play", "GpsGuard")
    import scenarios
    return play(scenarios.build(name), Guard(max_speed=scenarios.MAX_SPEED[name]), verbose=False)


def states(rows, t0, t1):
    return {st for t, st, _, _ in rows if t0 <= t < t1}


def at(rows, t):
    for tt, st, reason, _ in rows:
        if abs(tt - t) < 1e-6:
            return st, reason
    raise CheckFailed(f"no GPS fix at t={t}")


@c.test("reachable_m(): top speed x time + margin", hint="max_speed * max(0.0, dt_s) + margin")
def _():
    (f,) = need(S(), "reachable_m")
    c.near(f(2.0), 110.0, 1e-9, "reachable_m(2 s) at 30 m/s + 50 m")
    c.near(f(10.0, 100.0, 50.0), 1050.0, 1e-9, "reachable_m(10 s, 100 m/s, 50 m)")
    c.near(f(-1.0), 50.0, 1e-9, "reachable_m(-1 s) (a negative time counts as 0)")


@c.test("kinematic_gate(): reachable or not", hint="distance(x0, y0, x1, y1) <= reachable_m(t1 - t0, max_speed, margin)")
def _():
    (f,) = need(S(), "kinematic_gate")
    c.eq(f((0.0, 0.0, 0.0), (1.0, 60.0, 0.0)), True, "60 m in 1 s (max 80 m)")
    c.eq(f((0.0, 0.0, 0.0), (1.0, 0.0, 2000.0)), False, "2 km in 1 s")
    c.eq(f((0.0, 0.0, 0.0), (100.0, 0.0, 2000.0)), True, "2 km in 100 s (max 3050 m)")
    c.eq(f((0.0, 0.0, 0.0), (1.0, 0.0, 90.0), 30.0, 100.0), True, "90 m in 1 s with a 100 m margin")


@c.test("attack 'jump': a 2 km jump is refused at once, the true GPS re-accepted when it returns",
        hint="python3 spoof.py shows every change. The jump at t=20 must be REFUSED ('implausible jump'); "
             "at t=50 the true GPS is reachable again from the last trusted fix (TODO 4b).")
def _():
    r = run("jump")
    st, reason = at(r, 20.0)
    c.ok(st == "REFUSED" and "implausible jump" in str(reason), f"at t=20 s (2 km jump): {st} — {reason}")
    c.ok(states(r, 20, 50) == {"REFUSED"}, f"during the spoof (20–50 s) GPS was {sorted(map(str, states(r, 20, 50)))}")
    c.ok(states(r, 50, 61) == {"TRUSTED"}, f"after the spoof (50–60 s) GPS was {sorted(map(str, states(r, 50, 61)))}")


@c.test("attack 'patient', no vision: the known weakness of the kinematic gate alone",
        hint="Without vision, a refused GPS comes back as soon as it is reachable from the last trusted fix "
             "— even a spoofer who just waited. That is what the real arbiter would do without vision.")
def _():
    r = run("patient")
    c.ok(at(r, 93.0)[0] == "REFUSED", f"at t=93 s the 2 km spoof should still be refused: {at(r, 93.0)}")
    c.ok(at(r, 95.0)[0] == "TRUSTED", f"at t=95 s the spoof is 'reachable' and accepted: {at(r, 95.0)}")
    c.ok(at(r, 120.0)[0] == "REFUSED", f"at t=120 s the TRUE GPS returns, 2 km from the spoofed one: "
                                       f"refused as a jump — locked out. Yours: {at(r, 120.0)}")


@c.test("attack 'patient', with vision (15 m): the spoof is never accepted, the true GPS is",
        hint="While refused, with a vision fix of stated sigma: agree within 3 sigma on 2 distinct vision "
             "fixes -> TRUSTED; disagree -> REFUSED (TODO 4a).")
def _():
    r = run("patient_vision")
    c.ok(states(r, 20, 120) == {"REFUSED"}, f"during the 100 s spoof GPS was {sorted(map(str, states(r, 20, 120)))}")
    c.ok(at(r, 123.0)[0] == "TRUSTED", f"the true GPS (back at 120 s) is not re-accepted by t=123 s: {at(r, 123.0)}")
    c.ok(any("confirmed" in str(x[2]) for x in r), "no reason says the GPS was 'confirmed by vision'")


@c.test("attack 'drift' (4 m/s, vision 15 m): IN DOUBT first, then REFUSED, then re-accepted",
        hint="TODO 3: the streak of distinct vision fixes beyond 3 sigma — 2 -> IN_DOUBT, 5 -> REFUSED.")
def _():
    r = run("drift")
    first = {}
    for t, st, _, off in r:
        first.setdefault(st, (t, off))
    c.ok("IN_DOUBT" in first, "GPS was never IN_DOUBT during the drift")
    c.ok("REFUSED" in first, "the drift was never refused")
    c.ok(first["IN_DOUBT"][0] < first["REFUSED"][0], "IN_DOUBT must come BEFORE the refusal")
    c.ok(first["REFUSED"][1] < 150, f"refused only when the GPS was {first['REFUSED'][1]:.0f} m off "
                                    f"(the real arbiter: well before 150 m)")
    c.ok(states(r, first["REFUSED"][0], 80) == {"REFUSED"}, "after the refusal, a still-drifting GPS must stay REFUSED")
    c.ok(at(r, 83.0)[0] == "TRUSTED", f"the true GPS (back at 80 s) is not re-accepted by 83 s: {at(r, 83.0)}")


@c.test("attack 'drift' with vision of UNKNOWN accuracy: not detected (the honest limit)",
        hint="vision_reference() returns None when sigma is None: nothing to compare with, GPS stays TRUSTED.")
def _():
    r = run("drift_novision")
    c.ok(states(r, 0, 80) == {"TRUSTED"}, f"during the slow drift GPS was {sorted(map(str, states(r, 0, 80)))} "
                                          f"— without a stated accuracy, nothing can see it")


@c.test("attack 'jam, then spoof' (vision 15 m): refused although 2 km is 'reachable'",
        hint="After an outage (gap > GPS_TIMEOUT_S), on_gps() calls _confirm(): vision must agree first.")
def _():
    r = run("jamspoof")
    c.ok(states(r, 100, 120) == {"REFUSED"}, f"the spoofed GPS after the outage was {sorted(map(str, states(r, 100, 120)))}")
    c.ok(at(r, 123.0)[0] == "TRUSTED", f"the true GPS (back at 120 s) is not re-accepted by 123 s: {at(r, 123.0)}")
    r2 = run("jamspoof_novision")
    c.ok(at(r2, 100.0)[0] == "TRUSTED", "without a stated vision accuracy, the kinematic gate alone accepts the "
                                        f"'reachable' spoof (the documented limit). Yours: {at(r2, 100.0)}")


def real(name):
    p = f"real_{name}.txt"
    if not os.path.exists(p):
        raise CheckFailed(f"{p} does not exist yet: run `python3 spoof_real.py {name}`")
    lines = [ln for ln in open(p).read().splitlines() if ln.startswith("t=")]
    if not lines:
        raise CheckFailed(f"{p} is empty: run `python3 spoof_real.py {name}` again and let it finish")
    return lines


@c.test("the real arbiter vs a jump (real_jump.txt)", hint="Run `python3 spoof_real.py jump` (about 30 s).")
def _():
    lines = real("jump")
    c.ok(any("implausible jump" in ln for ln in lines), "no 'implausible jump' in real_jump.txt")
    c.ok(" GPS  GPS fix" in lines[-1], f"the run should end with GPS back (FIX): {lines[-1]}")


@c.test("the real arbiter vs a slow drift (real_drift.txt)", hint="Run `python3 spoof_real.py drift` (about 50 s).")
def _():
    lines = real("drift")
    doubt = next((i for i, ln in enumerate(lines) if "IN DOUBT" in ln), None)
    refused = next((i for i, ln in enumerate(lines) if "drifting away" in ln), None)
    c.ok(doubt is not None and refused is not None and doubt < refused,
         "real_drift.txt should show 'GPS IN DOUBT' and then 'drifting away' — run it again")
    c.ok(" GPS  GPS fix" in lines[-1], f"the run should end with GPS back (FIX): {lines[-1]}")


@c.test("the real arbiter vs jam-then-spoof (real_jamspoof.txt)", hint="Run `python3 spoof_real.py jamspoof` (about 50 s).")
def _():
    lines = real("jamspoof")
    spoofed = [ln for ln in lines if "2000 m off" in ln]
    c.ok(spoofed and all(" GPS  " not in ln.split("|")[1][:14] for ln in spoofed),
         "while the GPS was 2 km off, it should never be the active source")
    c.ok(any("from day vision" in ln for ln in spoofed), "the reason should say GPS is far 'from day vision'")
    c.ok(" GPS  GPS fix" in lines[-1], f"the run should end with GPS back (FIX): {lines[-1]}")


ANSWERS = {"Q1": "a", "Q2": "b", "Q3": "a", "Q4": "b", "Q5": "b", "Q6": "b"}


@c.test("quiz (answers.py)", hint="Q4–Q6 are in your real_*.txt files.")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


c.run()
