import json
import math
import os
import re
import sys

import numpy as np

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
sys.path.insert(0, os.getcwd())


def S():
    return load_student("spoof.py")


def D():
    return load_student("detection.py")


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


# ---------------------------------------------------------------- part A: the guard

@c.test("reachable_m(): top speed x time + margin",
        hint="The farthest the vehicle can be after dt seconds; a negative dt must count as 0.")
def _():
    (f,) = need(S(), "reachable_m")
    c.near(f(2.0), 110.0, 1e-9, "reachable_m(2 s) at 30 m/s + 50 m")
    c.near(f(10.0, 100.0, 50.0), 1050.0, 1e-9, "reachable_m(10 s, 100 m/s, 50 m)")
    c.near(f(-1.0), 50.0, 1e-9, "reachable_m(-1 s) (a negative time counts as 0)")


@c.test("kinematic_gate(): reachable or not",
        hint="Compare the distance between the two fixes with reachable_m() of the time between them "
             "(<= means accepted).")
def _():
    (f,) = need(S(), "kinematic_gate")
    c.eq(f((0.0, 0.0, 0.0), (1.0, 60.0, 0.0)), True, "60 m in 1 s (max 80 m)")
    c.eq(f((0.0, 0.0, 0.0), (1.0, 0.0, 2000.0)), False, "2 km in 1 s")
    c.eq(f((0.0, 0.0, 0.0), (100.0, 0.0, 2000.0)), True, "2 km in 100 s (max 3050 m)")
    c.eq(f((0.0, 0.0, 0.0), (1.0, 0.0, 90.0), 30.0, 100.0), True, "90 m in 1 s with a 100 m margin")


@c.test("attack 'jump': a 2 km jump is refused at once, the true GPS re-accepted when it returns",
        hint="python3 spoof.py shows every change. At t=50 the true GPS is reachable again from the last "
             "trusted fix: that is TODO 4b (no vision of stated accuracy).")
def _():
    r = run("jump")
    st, reason = at(r, 20.0)
    c.ok(st == "REFUSED" and "implausible jump" in str(reason), f"at t=20 s (2 km jump): {st} — {reason}")
    c.ok(states(r, 20, 50) == {"REFUSED"}, f"during the spoof (20–50 s) GPS was {sorted(map(str, states(r, 20, 50)))}")
    c.ok(states(r, 50, 61) == {"TRUSTED"}, f"after the spoof (50–60 s) GPS was {sorted(map(str, states(r, 50, 61)))}")


@c.test("attack 'patient', no vision: the known weakness of the kinematic gate alone",
        hint="Without vision, a refused GPS comes back as soon as it is reachable from the last trusted fix "
             "— even a spoofer who just waited.")
def _():
    r = run("patient")
    c.ok(at(r, 93.0)[0] == "REFUSED", f"at t=93 s the 2 km spoof should still be refused: {at(r, 93.0)}")
    c.ok(at(r, 95.0)[0] == "TRUSTED", f"at t=95 s the spoof is 'reachable' and accepted: {at(r, 95.0)}")
    c.ok(at(r, 120.0)[0] == "REFUSED", f"at t=120 s the TRUE GPS returns, 2 km from the spoofed one: "
                                       f"refused as a jump — locked out. Yours: {at(r, 120.0)}")


@c.test("attack 'patient', with vision (15 m): the spoof is never accepted, the true GPS is",
        hint="TODO 4a: while refused, count DISTINCT vision stamps that agree within 3 sigma; "
             "CONFIRM_N of them re-accept, one disagreeing fix resets the count.")
def _():
    r = run("patient_vision")
    c.ok(states(r, 20, 120) == {"REFUSED"}, f"during the 100 s spoof GPS was {sorted(map(str, states(r, 20, 120)))}")
    c.ok(at(r, 123.0)[0] == "TRUSTED", f"the true GPS (back at 120 s) is not re-accepted by t=123 s: {at(r, 123.0)}")
    c.ok(any("confirmed" in str(x[2]) for x in r), "no reason says the GPS was 'confirmed by vision'")


@c.test("attack 'drift' (4 m/s, vision 15 m): IN DOUBT first, then REFUSED, then re-accepted",
        hint="TODO 3: the streak is a SET of vision stamps beyond 3 sigma — DOUBT_AFTER of them -> "
             "IN_DOUBT, STREAK_N -> refused. An agreeing fix empties it.")
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
        hint="After an outage (gap > GPS_TIMEOUT_S), on_gps() calls _confirm(): vision must agree first. "
             "Without a stated vision accuracy, only the gate is left (TODO 4b).")
def _():
    r = run("jamspoof")
    c.ok(states(r, 100, 120) == {"REFUSED"}, f"the spoofed GPS after the outage was {sorted(map(str, states(r, 100, 120)))}")
    c.ok(at(r, 123.0)[0] == "TRUSTED", f"the true GPS (back at 120 s) is not re-accepted by 123 s: {at(r, 123.0)}")
    r2 = run("jamspoof_novision")
    c.ok(at(r2, 100.0)[0] == "TRUSTED", "without a stated vision accuracy, the kinematic gate alone accepts the "
                                        f"'reachable' spoof (the documented limit). Yours: {at(r2, 100.0)}")


# ---------------------------------------------------------------- part B: statistics

@c.test("p_exceed() and p_streak(): the false-alarm probabilities of one fix and of a streak",
        hint="|GPS - vision| is Rayleigh-distributed under H0 with variance s2 = sigma_ref^2 + sigma_g^2 per "
             "axis: P(|d| > r) = exp(-r^2 / (2 s2)) with r = k * sigma_ref. A streak of independent fixes: "
             "multiply.")
def _():
    pe, ps = need(D(), "p_exceed", "p_streak")
    c.near(pe(3.0), math.exp(-4.5), 1e-9, "p_exceed(3) with vision noise only")
    c.near(pe(1.0, 15.0, 0.0), math.exp(-0.5), 1e-9, "p_exceed(1, 15, 0)")
    c.near(pe(3.0, 15.0, 3.0), math.exp(-9 * 225 / (2 * 234)), 1e-9, "p_exceed(3, sigma_ref 15, sigma_g 3)")
    v = ps(3.0, 5)
    c.ok(isinstance(v, (int, float)) and abs(v - math.exp(-4.5) ** 5) < 1e-15,
         f"p_streak(3, 5) is {v!r}, expected {math.exp(-4.5) ** 5:.3g}")


@c.test("patient_accept_time(): when does a patient spoofer become 'reachable'?",
        hint="Square both sides of v*dt + m >= sqrt((s*dt)^2 + D^2): (v^2 - s^2) dt^2 + 2 v m dt + m^2 - D^2 >= 0. "
             "Take the positive root. If m >= D the answer is 0; if v <= s it may never happen (math.inf).")
def _():
    (f,) = need(D(), "patient_accept_time")
    c.near(f(2000.0, 15.0, 30.0, 50.0), 74.7658, 0.01, "patient_accept_time(2000 m, 15 m/s, 30 m/s, 50 m)")
    c.near(f(2000.0, 0.0, 30.0, 50.0), 65.0, 1e-6, "a hovering drone: (2000 - 50) / 30")
    c.near(f(40.0, 15.0, 30.0, 50.0), 0.0, 1e-9, "an offset inside the margin")
    v = f(2000.0, 30.0, 30.0, 0.0)
    c.ok(v == math.inf, f"vehicle at its top speed, no margin: never reachable -> math.inf, got {v!r}")
    out = json.load(open("results.json")) if os.path.exists("results.json") else None
    if out is not None:
        p = out.get("patient", {})
        g, th = p.get("accepted_by_guard_t_s"), p.get("accepted_theory_t_s")
        c.ok(isinstance(g, (int, float)) and isinstance(th, (int, float)) and 0 <= g - th < 1.0,
             f"results.json: theory says {th}, your guard accepted at {g} — the guard checks once per second, "
             f"so it should accept at the first fix after the theory time (run python3 detection.py again)")


@c.test("alarm_index(): first fix where the last n values are all above k",
        hint="Walk through z once, keeping the length of the current run of values > k (reset to 0 when a "
             "value is <= k). Return the index where the run reaches n; -1 if it never does.")
def _():
    (f,) = need(D(), "alarm_index")
    c.eq(f([0, 4, 4, 0, 4, 4, 4, 0], 3.0, 3), 6, "alarm_index([0,4,4,0,4,4,4,0], k=3, n=3)")
    c.eq(f([0, 4, 4, 0, 4, 4, 0], 3.0, 3), -1, "a run of 2 when n = 3")
    c.eq(f([3.0, 3.0, 3.0], 3.0, 1), -1, "equal to k is NOT beyond k")
    c.eq(f(np.array([5.0, 0.0]), 3.0, 1), 0, "n = 1 on a numpy array")
    c.eq(f([], 3.0, 1), -1, "an empty flight")


@c.test("roc_point(): P_FA, P_D and the mean detection delay of a rule",
        hint="P_FA = fraction of H0 flights whose alarm_index is not -1; P_D the same on H1; delay_s = mean of "
             "index * period_s over the DETECTED H1 flights only (None if none).")
def _():
    (f,) = need(D(), "roc_point")
    z0 = np.array([[0, 0, 0, 0], [4, 0, 0, 0], [0, 0, 0, 0], [0, 0, 4, 4]], float)
    z1 = np.array([[0, 4, 4, 4], [4, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 4]], float)
    p = f(z0, z1, 3.0, 1, 2.0)
    c.ok(isinstance(p, dict), f"roc_point should return a dict, got {p!r}")
    c.near(p.get("p_fa"), 0.5, 1e-9, "p_fa (n = 1)")
    c.near(p.get("p_d"), 0.75, 1e-9, "p_d (n = 1)")
    c.near(p.get("delay_s"), 2.0 * (1 + 0 + 3) / 3, 1e-9, "delay_s (n = 1)")
    p = f(z0, z1, 3.0, 2, 2.0)
    c.near(p.get("p_fa"), 0.25, 1e-9, "p_fa (n = 2)")
    c.near(p.get("p_d"), 0.5, 1e-9, "p_d (n = 2)")
    p = f(z0, z1, 9.0, 1, 2.0)
    c.ok(p.get("p_d") == 0 and p.get("delay_s") is None, f"nothing detected: delay_s must be None, got {p!r}")


# ---- reference experiment (same generator as detection.py)

def _sim(rng, flights, fixes, drift=0.0, rho=0.0, sv=15.0, sg=3.0, T=2.0):
    w = rng.standard_normal((flights, fixes, 2))
    ev = np.empty_like(w)
    ev[:, 0] = w[:, 0]
    cc = math.sqrt(1.0 - rho * rho)
    for i in range(1, fixes):
        ev[:, i] = rho * ev[:, i - 1] + cc * w[:, i]
    ev *= sv
    eg = sg * rng.standard_normal((flights, fixes, 2))
    b = np.zeros((flights, fixes, 2))
    b[:, :, 1] = drift * T * np.arange(fixes)
    d = b + eg - ev
    return np.hypot(d[..., 0], d[..., 1]) / sv


def _first(z, k, n):
    """vectorised alarm index for every flight (-1 = none)"""
    above = z > k
    run = np.zeros(z.shape[0], int)
    idx = np.full(z.shape[0], -1)
    for i in range(z.shape[1]):
        run = np.where(above[:, i], run + 1, 0)
        idx = np.where((idx < 0) & (run >= n), i, idx)
    return idx


_REF = {}


def reference():
    if not _REF:
        rng = np.random.default_rng(27)
        z0 = _sim(rng, 2000, 60)
        z1 = _sim(rng, 2000, 20, drift=1.5)
        zc = _sim(rng, 2000, 60, rho=0.9)
        for n in (1, 2, 3, 5):
            for k in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
                a0, a1, ac = _first(z0, k, n), _first(z1, k, n), _first(zc, k, n)
                det = a1[a1 >= 0]
                _REF[(k, n)] = {"p_fa": float(np.mean(a0 >= 0)), "p_d": float(np.mean(a1 >= 0)),
                                "delay_s": float(2.0 * det.mean()) if det.size else None,
                                "p_fa_rho": float(np.mean(ac >= 0))}
    return _REF


@c.test("results.json: the ROC experiment and your operating point",
        hint="Run python3 detection.py after TODO 5–9. Then choose CHOSEN_K / CHOSEN_N (TODO 10): among the "
             "rules with P_FA <= MAX_PFA, the one with the highest P_D. Run detection.py again.")
def _():
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet: run `python3 detection.py`")
    out = json.load(open("results.json"))
    ref = reference()
    rows = {(r.get("k"), r.get("n")): r for r in out.get("roc", [])}
    for key, want in ref.items():
        got = rows.get(key)
        c.ok(got is not None and got.get("p_fa") is not None,
             f"results.json has no ROC point for k={key[0]}, n={key[1]} — run python3 detection.py")
        c.near(got["p_fa"], want["p_fa"], 0.003, f"P_FA for k={key[0]}, n={key[1]}")
        c.near(got["p_d"], want["p_d"], 0.003, f"P_D for k={key[0]}, n={key[1]}")
    for r in out.get("correlated", []):
        want = ref[(r.get("k"), r.get("n"))]["p_fa_rho"]
        c.near(r.get("p_fa_rho_0.9"), want, 0.003, f"correlated P_FA for k={r.get('k')}, n={r.get('n')}")
    ch = out.get("chosen", {})
    key = (ch.get("k"), ch.get("n"))
    c.ok(key in ref, f"your operating point CHOSEN_K, CHOSEN_N = {key} is not one of the grid points")
    c.ok(ref[key]["p_fa"] <= 0.01, f"your operating point has P_FA {ref[key]['p_fa']} > 0.01")
    best = max(v["p_d"] for v in ref.values() if v["p_fa"] <= 0.01)
    c.ok(ref[key]["p_d"] >= best - 1e-9,
         f"another rule with P_FA <= 0.01 has a higher P_D ({best}) than yours ({ref[key]['p_d']})")


# ---------------------------------------------------------------- part C: the real arbiter

def real(name):
    p = f"real_{name}.txt"
    if not os.path.exists(p):
        raise CheckFailed(f"{p} does not exist yet: run `python3 spoof_real.py {name}`")
    lines = [ln for ln in open(p).read().splitlines() if ln.startswith("t=")]
    if not lines:
        raise CheckFailed(f"{p} is empty: run `python3 spoof_real.py {name}` again and let it finish")
    return lines


@c.test("the real arbiter vs a jump and vs jam-then-spoof (real_jump.txt, real_jamspoof.txt)",
        hint="Run `python3 spoof_real.py jump` (~30 s) and `python3 spoof_real.py jamspoof` (~50 s) and let "
             "them finish: each must end with the true GPS back (FIX GPS).")
def _():
    lines = real("jump")
    c.ok(any("implausible jump" in ln for ln in lines), "no 'implausible jump' in real_jump.txt")
    c.ok(" GPS  GPS fix" in lines[-1], f"real_jump.txt should end with GPS back (FIX): {lines[-1]}")
    lines = real("jamspoof")
    spoofed = [ln for ln in lines if "2000 m off" in ln]
    c.ok(spoofed and all(" GPS  " not in ln.split("|")[1][:14] for ln in spoofed),
         "real_jamspoof.txt: while the GPS was 2 km off, it should never be the active source")
    c.ok(any("from day vision" in ln for ln in spoofed), "real_jamspoof.txt: the reason should say GPS is far 'from day vision'")
    c.ok(" GPS  GPS fix" in lines[-1], f"real_jamspoof.txt should end with GPS back (FIX): {lines[-1]}")


def drift_offsets():
    lines = real("drift")
    doubt = next((ln for ln in lines if "IN DOUBT" in ln), None)
    refused = next((ln for ln in lines if "drifting away" in ln), None)
    if doubt is None or refused is None or lines.index(doubt) > lines.index(refused):
        raise CheckFailed("real_drift.txt should show 'GPS IN DOUBT' and then 'drifting away' — run it again")
    off = lambda ln: float(re.search(r"GPS\s+(\d+) m off", ln).group(1))  # noqa: E731
    return off(doubt), off(refused), lines


@c.test("the real arbiter vs a slow drift, and your reading of it (TODO 11)",
        hint="Run `python3 spoof_real.py drift` (~50 s). Open real_drift.txt: copy the 'GPS … m off' of the FIRST "
             "line with 'IN DOUBT' and of the first line with 'drifting away' into detection.py.")
def _():
    doubt, refused, lines = drift_offsets()
    c.ok(" GPS  GPS fix" in lines[-1], f"the run should end with GPS back (FIX): {lines[-1]}")
    m = D()
    a, b = need(m, "REAL_DRIFT_OFFSET_AT_DOUBT_M", "REAL_DRIFT_OFFSET_AT_REFUSAL_M")
    c.near(a, doubt, 2.0, "REAL_DRIFT_OFFSET_AT_DOUBT_M")
    c.near(b, refused, 2.0, "REAL_DRIFT_OFFSET_AT_REFUSAL_M")


# ---------------------------------------------------------------- part D: the report

SECTIONS = ["1. The patient spoofer", "2. Choosing an operating point", "3. Correlated vision errors",
            "4. The real arbiter", "5. Limits"]


def sections(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    parts = re.split(r"^##\s+", text, flags=re.M)
    out = {}
    for p in parts[1:]:
        head, _, body = p.partition("\n")
        out[head.strip()] = body
    return out


def numbers(s):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]


@c.test("report.md: five sections, your own words, the numbers you measured",
        hint="Keep the five '## ' headings of the template, replace every TODO with at least 40 words "
             "(section 5: 60). Quote your numbers: the patient-spoofer time, your chosen k and n, the two "
             "real offsets.")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    raw = open("report.md").read()
    sec = sections(raw)
    for h in SECTIONS:
        body = next((b for k, b in sec.items() if k.startswith(h[:2]) and h.split(" ", 1)[1].split()[0].lower()
                     in k.lower()), None)
        c.ok(body is not None, f"report.md has no section '## {h}'")
        c.ok("TODO" not in body, f"section '{h}' still contains TODO")
        words = len(re.findall(r"[A-Za-z]+", body))
        need_w = 60 if h.startswith("5") else 40
        c.ok(words >= need_w, f"section '{h}' has {words} words (at least {need_w})")
        sec[h] = body
    c.ok(any(abs(x - 74.77) < 0.6 or abs(x - 93.77) < 0.6 for x in numbers(sec[SECTIONS[0]])),
         "section 1 should quote the time computed by patient_accept_time (about 75 s after the last "
         "trusted fix, i.e. t ≈ 94 s)")
    m = D()
    k, n = need(m, "CHOSEN_K", "CHOSEN_N")
    nums = numbers(sec[SECTIONS[1]])
    c.ok(isinstance(k, (int, float)) and any(abs(x - k) < 1e-9 for x in nums) and any(abs(x - n) < 1e-9 for x in nums),
         f"section 2 should name your operating point (k = {k}, n = {n})")
    try:
        doubt, refused, _ = drift_offsets()
    except CheckFailed:
        c.skip("run spoof_real.py drift first")
    nums = numbers(sec[SECTIONS[3]])
    c.ok(any(abs(x - doubt) <= 2 for x in nums) and any(abs(x - refused) <= 2 for x in nums),
         f"section 4 should quote the two offsets of real_drift.txt ({doubt:.0f} m in doubt, {refused:.0f} m refused)")


c.run()
