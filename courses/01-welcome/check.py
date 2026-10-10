import contextlib
import io
import re
import signal

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
TEACHER_NOTE = " (Your teacher reads these answers with a rubric: the check only verifies that you really answered.)"


def quiet_load(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def answers(*names):
    return need(quiet_load("answers.py"), *names)


def functions(*names):
    return need(quiet_load("beacons.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str):
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def run(fn, *args, seconds=40):
    """Call a student function; a crash or an endless loop becomes a clear ✘."""
    def too_long(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, too_long)
    signal.alarm(seconds)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)
    except TimeoutError:
        raise CheckFailed(f"{fn.__name__}() did not finish in {seconds} s — is a loop endless?")
    except Exception as e:
        extra = (" — did you write `delta = np.linalg.lstsq(...)` without `, *_`?"
                 if any(k in str(e) for k in ("could not be broadcast", "length-1 arrays", "0-dimensional arrays")) else "")
        raise CheckFailed(f"{fn.__name__}() stopped with {type(e).__name__}: {e}{extra}")
    finally:
        signal.alarm(0)


def point(v, n, what):
    if not isinstance(v, (tuple, list)) or len(v) != n or not all(isinstance(x, (int, float)) for x in v):
        raise CheckFailed(f"{what} should return {n} numbers, got {v!r}")
    return [float(x) for x in v]


def words(s):
    return re.findall(r"[A-Za-zÀ-ÿ']{2,}", str(s))


def predicted(name, value):
    c.ok(isinstance(value, str) and value.strip() != "", f"{name} is empty — write your guess (any honest guess is fine)")


def explained(name, value, *groups):
    """value must be a real sentence that touches each group of ideas (any keyword of each group)."""
    c.ok(isinstance(value, str) and value.strip() != "", f"{name} is still empty")
    c.ok(len(words(value)) >= 8, f"{name} is very short — explain in one to three full sentences")
    low = value.lower()
    for keywords, idea in groups:
        c.ok(any(re.search(k, low) for k in keywords), f"{name} does not explain {idea} yet." + TEACHER_NOTE)


# ---------------------------------------------------------------- Step 1
@c.test("Step 1: NAVERA's settings and your stealth prediction",
        hint="Open estimator_params.yaml (link in Step 1) and find max_speed_mps, gps_jump_margin_m, gps_timeout_s and "
             "day_timeout_s. "
             "A NameError in answers.py almost always means text without quotes.")
def _():
    v, m, t, d, pred = answers("V_MAX_MPS", "MARGIN_M", "GPS_TIMEOUT_S", "DAY_TIMEOUT_S", "PREDICT_STEALTH")
    c.ok(number(v, "V_MAX_MPS") == 100.0, f"V_MAX_MPS = {v!r} is not max_speed_mps of the file")
    c.ok(number(m, "MARGIN_M") == 50.0, f"MARGIN_M = {m!r} is not gps_jump_margin_m of the file")
    c.ok(number(t, "GPS_TIMEOUT_S") == 3.0, f"GPS_TIMEOUT_S = {t!r} is not gps_timeout_s of the file")
    c.ok(number(d, "DAY_TIMEOUT_S") == 5.0, f"DAY_TIMEOUT_S = {d!r} is not day_timeout_s of the file")
    predicted("PREDICT_STEALTH", pred)


# ---------------------------------------------------------------- your functions, on unseen numbers
BEACONS = [(1, 1), (9, 2), (4, 9)]
CLEAN = [5.859181, 3.275668, 5.738467]                     # measured from (6.2, 3.7)
LATE = [6.309181, 3.725668, 6.188467]                      # same, with b = 0.45 km
FOUR = [(1, 1), (9, 2), (4, 9), (8, 8)]
NOISY = [6.329181, 3.695668, 6.198467, 5.136545]           # four ranges with small errors


@c.test("TODO 1: distance() works for any two points", hint="Lesson §2; the 🧰 refresher of Step 2 shows p[0], ** and math.sqrt.")
def _():
    (distance,) = functions("distance")
    c.near(run(distance, (0, 0), (3, 4)), 5.0, 1e-6, "distance((0, 0), (3, 4))")
    c.near(run(distance, (-2, 5), (4, -3)), 10.0, 1e-6, "distance((-2, 5), (4, -3))")
    c.near(run(distance, (1.5, 2.5), (1.5, 2.5)), 0.0, 1e-9, "distance between a point and itself")


@c.test("TODO 2: mismatch() works for other beacons, with and without a bias",
        hint="Lesson §2: the sum of squared residuals, residual = measured − (distance + bias). "
             "If your value equals one row of the lesson table, see the Step 2 hints.")
def _():
    (mismatch,) = functions("mismatch")
    c.near(run(mismatch, (4, 4), [(0, 0), (10, 0), (0, 10)], [5.0, 8.062, 6.708]), 1.4086, 0.001,
           "mismatch at (4, 4), the lesson example")
    c.near(run(mismatch, (5, 5), BEACONS, CLEAN), 5.62365, 0.0005, "mismatch on other beacons")
    c.near(run(mismatch, (5, 5), BEACONS, LATE, 0.2), 5.85783, 0.0005, "mismatch with bias = 0.2")
    c.near(run(mismatch, (6.2, 3.7), BEACONS, LATE, 0.45), 0.0, 1e-6, "mismatch at the true point with the right bias")


@c.test("TODO 3: find_position() finds a position it has never seen",
        hint="Lesson §3 brute force in 2-D: one loop inside the other over the docstring grid; keep the smallest mismatch.")
def _():
    (find_position,) = functions("find_position")
    p = point(run(find_position, BEACONS, CLEAN), 2, "find_position")
    c.ok(abs(p[0] - 6.2) < 0.01 and abs(p[1] - 3.7) < 0.01, f"find_position gives {tuple(p)} on new beacons — not the right point")
    p = point(run(find_position, BEACONS, [10.444616, 4.414748, 6.579514]), 2, "find_position")
    c.ok(abs(p[0] - 10.0) < 0.01 and abs(p[1] - 6.3) < 0.01,
         f"for a point on the edge of the field (x = 10.0) it gives {tuple(p)} — does your grid really reach 10.0?")


@c.test("TODO 4: find_position_and_bias() finds the position AND the clock bias",
        hint="Your biases must be 0.00, 0.05, 0.10 … 1.00 (print them to check). Give the bias to mismatch(). "
             "Return three numbers.")
def _():
    (fpb,) = functions("find_position_and_bias")
    p = point(run(fpb, BEACONS, LATE, seconds=60), 3, "find_position_and_bias")
    c.ok(abs(p[0] - 6.2) < 0.01 and abs(p[1] - 3.7) < 0.01, f"the position found is ({p[0]}, {p[1]}) — not the right point")
    c.ok(abs(p[2] - 0.45) < 0.01, f"the bias found is {p[2]} — not the right bias")


@c.test("TODO 5: gauss_newton() solves exactly with 3 beacons and in the least-squares sense with 4 noisy ones",
        hint="Lesson §3: rows [uₓ, u_y, 1] with u = (p − beacon)/d, residuals measured − (d + b), "
             "np.linalg.lstsq, then ADD the correction. Check your first step against the lesson table.")
def _():
    (gn,) = functions("gauss_newton")
    s1 = point(run(gn, [(0, 0), (10, 0), (0, 10)], [5.3, 8.362, 7.008], (4.0, 4.0, 0.0), 1), 3, "gauss_newton")
    if abs(s1[0] - 3.0002) < 2e-3 and abs(s1[1] - 4.0001) < 2e-3:
        why = "that is the final answer, not one step — does it use `guess` and `steps`?"
    elif abs(s1[0] - 4.9793) < 2e-3:
        why = "the step goes the wrong way — check the signs: u = (p − beacon)/d, residual = measured − (d + b), ADD Δ"
    elif abs(s1[2]) < 1e-9:
        why = "the bias did not move — each row of H needs a 1 for the bias, and b must be updated"
    else:
        why = "compare your rows of H and r with the lesson's §3 table, beacon by beacon"
    c.ok(abs(s1[0] - 3.0207) < 2e-3 and abs(s1[1] - 3.9971) < 2e-3 and abs(s1[2] - 0.3377) < 2e-3,
         f"one step from (4, 4, 0) gives {tuple(round(v, 4) for v in s1)}, not the lesson's first step — {why}")
    p = point(run(gn, BEACONS, LATE), 3, "gauss_newton")
    c.ok(abs(p[0] - 6.2) < 1e-3 and abs(p[1] - 3.7) < 1e-3 and abs(p[2] - 0.45) < 1e-3,
         f"with 3 exact beacons it gives {tuple(round(v, 4) for v in p)} — not the exact solution")
    q = point(run(gn, FOUR, NOISY, (5.0, 5.0, 0.0), 10), 3, "gauss_newton")
    c.ok(abs(q[0] - 6.22040) < 1e-3 and abs(q[1] - 3.68361) < 1e-3 and abs(q[2] - 0.45252) < 1e-3,
         f"with 4 noisy beacons it gives {tuple(round(v, 4) for v in q)} — not the least-squares solution "
         "(does it use every beacon?)")


@c.test("TODO 6: spoof_measurements() computes what a receiver at the fake position would measure",
        hint="The predicted pseudorange of lesson §3, for a receiver at fake_position. Return a list, one value per beacon.")
def _():
    (spoof,) = functions("spoof_measurements")
    got = run(spoof, [(2, 7), (8, 1), (5, 5)], (1.5, 2.5), 0.25)
    c.ok(isinstance(got, (list, tuple)) and len(got) == 3, f"it should return 3 values (one per beacon), got {got!r}")
    for g, want, n in zip(got, [4.777693, 6.920832, 4.551163], "123"):
        c.near(g, want, 1e-4, f"value {n}")


@c.test("TODO 7: gate_ok() applies the jump gate",
        hint="Accepted when distance(last, new) ≤ v_max × elapsed + margin; exactly on the limit is accepted.")
def _():
    (gate_ok,) = functions("gate_ok")
    cases = [((0, 0), (120, 0), 1.0, 100.0, 50.0, True), ((0, 0), (500, 0), 1.0, 100.0, 50.0, False),
             ((0, 0), (300, 400), 4.5, 100.0, 50.0, True), ((0, 0), (300, 400), 4.4, 100.0, 50.0, False),
             ((10, 10), (40, 50), 1.0, 30.0, 20.0, True), ((0, 0), (0, 40), 0.5, 30.0, 20.0, False)]
    for last, new, el, v, m, want in cases:
        got = run(gate_ok, last, new, el, v, m)
        c.ok(got in (True, False), f"gate_ok should return True or False, got {got!r}")
        c.ok(got == want, f"gate_ok({last}, {new}, elapsed {el} s, v_max {v}, margin {m}) gives {got}")


@c.test("TODO 8: count_refused() follows the arbiter's rule",
        hint="Redo the 7-row table of lesson §5 by hand and compare it with your code, row by row. 5 on the table but "
             "wrong elsewhere: add dt_s BEFORE the gate test and restart after an accept (Step 8 hints).")
def _():
    (count_refused,) = functions("count_refused")
    got = run(count_refused, [(0, 0)] + [(500, 0)] * 6 + [(900, 0)], 1.0, 100.0, 50.0)
    c.ok(got == 5, f"on the lesson's 7-row table it gives {got!r} instead of 5")
    fixes = [(0, 0), (10, 0), (30, 0), (31, 0), (80, 0), (82, 0), (84, 0), (10, 0)]
    got = run(count_refused, fixes, 0.5, 30.0, 10.0)
    c.ok(got == 3, f"on other fixes (dt 0.5 s, v_max 30, margin 10) it gives {got!r} — not the right count")


@c.test("TODO 9: first_disagreement() applies the cross-check to a log",
        hint="Skip rows without vision (None). Refuse only when the distance is strictly larger than "
             "k × sigma + margin. Return the t_s of that row, or None if it never happens.")
def _():
    (fd,) = functions("first_disagreement")
    rows = [dict(t_s=10, gps_x_m=0, gps_y_m=0, vision_x_m=10, vision_y_m=0, vision_sigma_m=20),
            dict(t_s=11, gps_x_m=100, gps_y_m=0, vision_x_m=None, vision_y_m=None, vision_sigma_m=None),
            dict(t_s=12, gps_x_m=0, gps_y_m=150, vision_x_m=0, vision_y_m=0, vision_sigma_m=20),
            dict(t_s=13, gps_x_m=0, gps_y_m=151, vision_x_m=0, vision_y_m=0, vision_sigma_m=20)]
    got = run(fd, rows)
    c.ok(got is not None, "with the default k = 5 and margin 50 it finds no disagreement at all, on rows where σ = 20 m: "
                          "does your limit use each row's vision_sigma_m (not a fixed 30)?")
    c.ok(got == 13, f"with the default k = 5 and margin 50 it gives {got!r} — not the right time "
                    "(return the row's t_s; exactly on the limit is still agreement)")
    got = run(fd, rows, 3.0, 50.0)
    c.ok(got == 12, f"with k = 3 it gives {got!r} — does your function use its k and margin arguments?")
    c.ok(run(fd, rows[:3]) is None, "when GPS and vision always agree it should return None")


# ---------------------------------------------------------------- what you saw and why
@c.test("Step 4: a clock 1 µs ahead — prediction, error and explanation",
        hint="Run python3 where_am_i.py clock: CLOCK_ERROR_M is the distance from the true position in part 1. "
             "EXPLAIN_CLOCK: say that the clock bias is the same on every range, and that it becomes an unknown.")
def _():
    pred, err, why = answers("PREDICT_CLOCK", "CLOCK_ERROR_M", "EXPLAIN_CLOCK")
    predicted("PREDICT_CLOCK", pred)
    e = number(err, "CLOCK_ERROR_M")
    c.ok(140 <= e <= 142, f"CLOCK_ERROR_M = {err!r} is not what part 1 of `clock` prints")
    explained("EXPLAIN_CLOCK", why, ((r"bias", r"clock", r"\bb\b", r"offset"), "the clock bias"),
              ((r"every", r"\ball\b", r"each", r"same", r"common", r"shared"), "that it is the same for every range"))


@c.test("Step 5: two beacons — prediction, explanation and the curve",
        hint="Run python3 where_am_i.py two. Count unknowns and measurements. CURVE: not a line — on a bigger grid the "
             "dots bend. Sum of distances to two points constant = ellipse; difference constant = ?")
def _():
    pred, why, curve = answers("PREDICT_TWO", "EXPLAIN_TWO", "CURVE")
    predicted("PREDICT_TWO", pred)
    explained("EXPLAIN_TWO", why, ((r"unknown",), "the unknowns"),
              ((r"\b(3|three)\b",), "how many unknowns"), ((r"\b(2|two)\b",), "how many measurements"),
              ((r"\b(4|four)\b.*satellite|satellite.*\b(4|four)\b",), "how many satellites real GPS needs"))
    c.ok("hyperbol" in str(curve).lower(), f"CURVE = {curve!r} is not the right curve")


@c.test("Step 6: Gauss–Newton — steps, HDOP, a rank-deficient case, and explanation",
        hint="Run python3 where_am_i.py gn and count the steps until the mismatch is below 1e-6 (3.36e-05 = 0.0000336 "
             "is still above 1e-6). HDOP: H = np.array(H) at (3, 4), M = np.linalg.inv(H.T @ H), sqrt(M[0, 0] + M[1, 1]) — not the bias entry. Explain the linearisation, how it "
             "fails, and the link between HDOP and the valley.")
def _():
    steps, h1, h2, rank, why = answers("GN_STEPS", "HDOP_TRIANGLE", "HDOP_OUTSIDE", "COLLINEAR_RANK", "EXPLAIN_GN")
    s = number(steps, "GN_STEPS")
    c.ok(s == 3, f"GN_STEPS = {steps!r} is not what the `gn` table shows (mismatch below 1e-6, from (5, 5, 0))")
    h1, h2 = number(h1, "HDOP_TRIANGLE"), number(h2, "HDOP_OUTSIDE")
    c.ok(abs(h1 - 1.197) > 0.004 and abs(h2 - 1.250) > 0.004,
         "your HDOP looks computed without the clock: H needs one row [uₓ, u_y, 1] per beacon (lesson §3), so (HᵀH)⁻¹ is 3 × 3")
    c.near(h1, 1.216, 0.007, "HDOP_TRIANGLE")
    c.near(h2, 1.598, 0.007, "HDOP_OUTSIDE")
    c.ok(number(rank, "COLLINEAR_RANK") == 2, f"COLLINEAR_RANK = {rank!r} — build H at (4, 0) and print np.linalg.matrix_rank(H)")
    explained("EXPLAIN_GN", why, ((r"linear", r"jacobian", r"derivative", r"gradient", r"\bstep"), "why each step is cheap"),
              ((r"guess", r"start", r"diverg", r"far", r"line", r"singular", r"rank", r"mirror"), "how it could fail"),
              ((r"hdop", r"valley", r"flat", r"geometr", r"dop"), "the link between HDOP and the geometry"))


@c.test("Step 7: full and partial spoof — predictions and explanations",
        hint="Run python3 where_am_i.py spoof and partial. Why is a full spoof consistent? What does a spare, "
             "real measurement leave in the mismatch?")
def _():
    p1, e1, p2, e2 = answers("PREDICT_SPOOF", "EXPLAIN_SPOOF", "PREDICT_PARTIAL", "EXPLAIN_PARTIAL")
    predicted("PREDICT_SPOOF", p1)
    predicted("PREDICT_PARTIAL", p2)
    explained("EXPLAIN_SPOOF", e1, ((r"consistent", r"same", r"exact", r"agree", r"fit", r"match", r"one point"),
                                    "why the fake ranges fit perfectly"),
              ((r"cannot", r"can't", r"can not", r"\bnot\b", r"\bno\b", r"nothing", r"never"), "whether the receiver can tell"),
              ((r"jam", r"lose", r"lost", r"no signal", r"noise"), "why jamming, by contrast, is noticed"))
    explained("EXPLAIN_PARTIAL", e2, ((r"residual", r"mismatch"), "what stays in the residuals"),
              ((r"extra", r"redundan", r"spare", r"more", r"fourth", r"\bd\b", r"real"), "the role of the spare measurement"),
              ((r"power", r"antenna", r"direction", r"osnma", r"authent", r"sign", r"camera", r"vision"),
               "one defence that better receivers add"))


@c.test("Step 8: the jump gate against two attacks",
        hint="Run python3 where_am_i.py gate and copy the two count_refused results.")
def _():
    pred, jump, drift = answers("PREDICT_GATE", "JUMP_REFUSED", "DRIFT_REFUSED")
    predicted("PREDICT_GATE", pred)
    c.ok(number(jump, "JUMP_REFUSED") == 2, f"JUMP_REFUSED = {jump!r} is not what a correct count_refused gives for "
                                            "attack A; if your gate run printed it, fix TODO 8 first (check 9)")
    c.ok(number(drift, "DRIFT_REFUSED") == 0, f"DRIFT_REFUSED = {drift!r} is not what the gate run gives for attack B")


@c.test("Step 9: be the arbiter (ARBITER_SOURCE, ARBITER_STATE)",
        hint="Lesson §5: is the GPS fix fresh? Then the priority order decides (not precision), and the state "
             "depends only on that source's σ (25 m rule).")
def _():
    src, state = answers("ARBITER_SOURCE", "ARBITER_STATE")
    src, state = str(src).strip().lower(), str(state).strip().upper().replace("-", "_").replace(" ", "_")
    c.ok(src in ("gps", "day", "night", "celestial", "none"), f"ARBITER_SOURCE = {src!r} is not one of the five choices")
    c.ok(state in ("FIX", "DEGRADED", "NO_FIX"), f"ARBITER_STATE = {state!r} is not one of the three states")
    c.ok(src == "gps", "not this source: is the GPS fix fresh (GPS_TIMEOUT_S)? Then apply the priority order")
    c.ok(state == "DEGRADED", "the source is right, not the state: compare its σ with 25 m")


@c.test("Step 10: the detective — what each defence saw",
        hint="Run python3 where_am_i.py flight. Then read out/flight.png: when does the GPS start to leave vision, "
             "and where is the drone at that time?")
def _():
    pred, refused, caught, why = answers("PREDICT_FLIGHT", "FLIGHT_REFUSED", "CAUGHT_AT_S", "EXPLAIN_FLIGHT")
    predicted("PREDICT_FLIGHT", pred)
    c.ok(number(refused, "FLIGHT_REFUSED") == 0, f"FLIGHT_REFUSED = {refused!r} is not what `flight` prints for the jump gate")
    c.ok(number(caught, "CAUGHT_AT_S") == 450, f"CAUGHT_AT_S = {caught!r} is not what `flight` prints for the cross-check")
    explained("EXPLAIN_FLIGHT", why, ((r"(?<!\d)2[45]\d(?!\d)",), "when the spoof really started (read it on the plot)"),
              ((r"sea", r"water", r"no (vision|match)", r"vision"), "why vision could not see it earlier"))


@c.test("Step 11: attacker vs defender",
        hint="Write a short script with your count_refused: drag lists [(n * t, 0) for t in range(61)] for the attacker; "
             "the GPS fixes of flight.csv before the spoof started, v_max = 15, for the defender.")
def _():
    v, faster, margin, v2, why = answers("STEALTH_SPEED_MPS", "REFUSED_ONE_FASTER", "DEFENDER_MARGIN_M",
                                         "DEFENDER_STEALTH_MPS", "EXPLAIN_TRADEOFF")
    v, faster, margin, v2 = (number(v, "STEALTH_SPEED_MPS"), number(faster, "REFUSED_ONE_FASTER"),
                             number(margin, "DEFENDER_MARGIN_M"), number(v2, "DEFENDER_STEALTH_MPS"))
    c.ok(v == 150, f"STEALTH_SPEED_MPS = {v:g}: " + ("a faster drag still passes" if v < 150 else "at that speed fixes are refused"))
    c.ok(faster == 60, f"REFUSED_ONE_FASTER = {faster:g} — run your count_refused on the 151 m/s drag")
    c.ok(margin == 56, f"DEFENDER_MARGIN_M = {margin:g} — " + ("some honest fixes are still refused" if margin < 56
                                                             else "a smaller margin also gives zero refusals"))
    c.ok(v2 == 15 + margin, f"DEFENDER_STEALTH_MPS = {v2:g} is not the best drag speed against v_max 15 and your margin")
    explained("EXPLAIN_TRADEOFF", why, ((r"false", r"honest", r"noise", r"multipath", r"spike", r"refus"), "the cost on real GPS"),
              ((r"slow", r"drag", r"below", r"under", r"vision", r"cross", r"never"), "what the gate still cannot stop"))


c.run()
