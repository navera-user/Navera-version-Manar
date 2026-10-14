import contextlib
import io
import math
import os
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()


# ---------------------------------------------------------------- loading and small helpers
def module(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def functions(mod, *names):
    m = module(mod)
    fns = need(m, *names)
    for f in fns:
        if is_stub(f):
            where = "navera_lite/vo.py" if mod.startswith("navera_lite") else mod
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in {where})")
    return fns


def answers(*names):
    return need(module("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")
    if not math.isfinite(x):
        raise CheckFailed(f"{name} is {x}: write the number the runner printed")
    return x


def go(fn, *args, seconds=60, **kw):
    try:
        return run(fn, *args, seconds=seconds, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "could not be broadcast" in msg:
            if getattr(fn, "__name__", "") == "phase_shift":
                msg += " — the window must have the image's shape (h, w): np.outer(np.hanning(h), np.hanning(w))"
            else:
                msg += " — two arrays of different shapes were combined: print the .shape of each one"
        if "must be real number" in msg or "only size-1 arrays" in msg or "only length-1 arrays" in msg:
            msg += " — math functions take one number; on arrays use numpy (np.sqrt, np.median…)"
        raise CheckFailed(msg)


def three(v, what):
    try:
        if any(np.iscomplexobj(np.asarray(x)) for x in v):
            raise CheckFailed(f"{what} returned a complex number: the correlation surface is the REAL part, "
                              "r = np.real(np.fft.ifft2(R)) (lesson §3, step 4)")
    except TypeError:
        pass
    try:
        a, b, r = v
        return float(a), float(b), float(r)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} must return three numbers (dx, dy, response), got {v!r}")


def two(v, what):
    try:
        a, b = v
        return float(a), float(b)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} must return two numbers, got {v!r}")


# ======================================================================== session 1 — Odometer
G = np.random.default_rng(2424).random((48, 64))
R_REF = [0.2613, 0.2311, 0.1614, 0.2702, 0.1343, 0.2671]          # responses on the hidden pairs, numpy window
R_SQRT_WIN = [0.2714, 0.2333, 0.1801, 0.2724, 0.1824, 0.2944]     # the same with cv2.createHanningWindow
ROLLS = {(3, -7): (-7.001, 2.999), (-11, 20): (20.017, -11.004), (0, 31): (30.966, -0.035), (17, 0): (-0.009, 17.002)}


def smooth(seed, h, w):
    import cv2
    return cv2.GaussianBlur(np.random.default_rng(seed).random((h, w)), (0, 0), 1.2)


def fourier_shift(img, dx, dy):
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(img) * np.exp(-2j * np.pi * (fx * dx + fy * dy))))


@c.test("TODO 1: phase_shift() on unseen shifts — signs, negative shifts, sub-pixel, response",
        hint="Lesson §2–§3: (image − mean) × Hann window, fft2 of both, R = B·conj(A) / |B·conj(A)|, real part of ifft2, "
             "peak with argmax + unravel_index (row = y), parabola through the peak and its two neighbours in x and in "
             "y, an index past half the size is negative. Return (dx, dy, response).")
def _():
    (f,) = functions("navera_lite.vo", "phase_shift")
    for (sy, sx), want in ROLLS.items():
        dx, dy, r = three(go(f, G, np.roll(G, (sy, sx), axis=(0, 1))), "phase_shift")
        if abs(dx - (sx % 64)) < 0.6 and sx < 0 or abs(dy - (sy % 48)) < 0.6 and sy < 0:
            raise CheckFailed(f"content rolled ({sx}, {sy}) px gave ({dx:.2f}, {dy:.2f}): a peak index past half the "
                              "picture is a NEGATIVE shift (index − width, index − height)")
        if abs(dx + want[0]) < 0.2 and abs(dy + want[1]) < 0.2 and (sx or sy):
            raise CheckFailed(f"content rolled ({sx}, {sy}) px gave ({dx:.2f}, {dy:.2f}): both signs reversed — the "
                              "cross-power spectrum is B · conj(A) (b against a)")
        if abs(dx - want[1]) < 0.2 and abs(dy - want[0]) < 0.2 and sx != sy:
            raise CheckFailed(f"content rolled ({sx}, {sy}) px gave ({dx:.2f}, {dy:.2f}): x and y are swapped — "
                              "np.unravel_index gives (row, column) = (y, x)")
        if round(dx) == round(want[0]) and round(dy) == round(want[1]) and not (abs(dx - want[0]) < 0.06
                                                                             and abs(dy - want[1]) < 0.06):
            raise CheckFailed(f"a 48 × 64 picture rolled by exactly ({sx}, {sy}) px gave ({dx:.3f}, {dy:.3f}): the integer "
                              f"peak is right, but your sub-pixel step moves it (it should stay within 0.06 px of "
                              f"({round(want[0])}, {round(want[1])})). Check the sign of δ = (c₋ − c₊) / (2 (c₋ − 2 c₀ + "
                              "c₊)) and that c₋ is the LEFT (or upper) neighbour")
        c.ok(abs(dx - want[0]) < 0.06 and abs(dy - want[1]) < 0.06,
             f"a 48 × 64 picture rolled by (dx, dy) = ({sx}, {sy}) px gave ({dx:.3f}, {dy:.3f})")
        if r > 1.5 or r < 0.05:
            raise CheckFailed(f"the response is {r:.4g}: a peak of a normalised spectrum lies between 0 and 1 — divide "
                              "B·conj(A) by its magnitude (np.abs) before ifft2")
    n = np.random.default_rng(99)
    _, _, r = three(go(f, n.random((48, 64)), n.random((48, 64))), "phase_shift")
    c.ok(r < 0.2, f"two unrelated noise pictures gave a response of {r:.3f}: it should be small (no common motion)")
    sm = smooth(7, 60, 72)
    for sx, sy in ((0.4, -0.3), (-2.25, 1.7), (5.5, 0.0)):
        dx, dy, _ = three(go(f, sm, fourier_shift(sm, sx, sy)), "phase_shift")
        c.ok(abs(dx - sx) < 0.2 and abs(dy - sy) < 0.2,
             f"a sub-pixel shift of ({sx}, {sy}) px gave ({dx:.3f}, {dy:.3f}): refine the peak with the parabola "
             "δ = (c₋ − c₊) / (2 (c₋ − 2 c₀ + c₊)) in x and in y (lesson §3, detail 3)")
    d = np.load(io.BytesIO(hidden("test_pairs.npz", text=False)))
    resp = []
    for a, b, t in zip(d["a"], d["b"], d["shift"]):
        dx, dy, r = three(go(f, a, b), "phase_shift")
        resp.append(r)
        c.ok(math.hypot(dx - t[0], dy - t[1]) < 0.35,
             f"on an unseen pair of real-looking uint8 frames (true shift about ({t[0]:.1f}, {t[1]:.1f}) px) you gave "
             f"({dx:.2f}, {dy:.2f}) — the Hann window (and the mean removed) matter on frames that do not wrap around")
    if np.allclose(resp, R_SQRT_WIN, atol=0.003) and not np.allclose(resp, R_REF, atol=0.003):
        raise CheckFailed("your window looks like cv2.createHanningWindow (the square root of hann·hann): use "
                          "np.outer(np.hanning(h), np.hanning(w)) — lesson §3, detail 2. The lab's thresholds (Step 7) "
                          "are measured with it")


@c.test("TODO 2: px_to_en() with unseen shifts, scales and headings",
        hint="Lesson §5: right = −dx·m_per_px, forward = +dy·m_per_px; east = forward·sin θ + right·cos θ, "
             "north = forward·cos θ − right·sin θ, θ = math.radians(heading_deg).")
def _():
    (f,) = functions("navera_lite.vo", "px_to_en")
    cases = (((12.0, -30.0, 0.4, 0.0), (-4.8, -12.0)), ((12.0, -30.0, 0.4, 37.5), (-11.11323, -6.59819)),
             ((-8.5, 4.0, 0.6, 200.0), (-5.61328, -0.51096)), ((3.0, 25.0, 0.25, 315.0), (-4.94975, 3.88909)))
    for args, want in cases:
        e, n = two(go(f, *args), "px_to_en")
        if args[3] == 0.0:
            if abs(e - 4.8) < 1e-3 and abs(n + 12.0) < 1e-3:
                raise CheckFailed("px_to_en(12, −30, 0.4, 0): east has the wrong sign — the ground slid RIGHT, so the "
                                  "drone moved LEFT (right = −dx · m_per_px)")
            if abs(n - 12.0) < 1e-3:
                raise CheckFailed("px_to_en(12, −30, 0.4, 0): north has the wrong sign — the ground slid UP (dy < 0), "
                                  "so the drone flew BACKWARDS (forward = +dy · m_per_px, y points down)")
        if args[3] == 37.5:
            th = math.radians(37.5)
            r, fw = -4.8, -12.0
            if abs(e - (fw * math.sin(-th) + r * math.cos(th))) < 1e-3 and abs(n - (fw * math.cos(th) + r * math.sin(th))) < 1e-3:
                raise CheckFailed("px_to_en at heading 37.5°: the rotation is turned the wrong way (the transposed "
                                  "matrix): east = forward·sin θ + right·cos θ, north = forward·cos θ − right·sin θ")
            if abs(e - (fw * math.sin(37.5) + r * math.cos(37.5))) < 1e-3:
                raise CheckFailed("px_to_en: math.sin and math.cos take RADIANS — math.radians(heading_deg)")
        c.ok(abs(e - want[0]) < 1e-3 and abs(n - want[1]) < 1e-3,
             f"px_to_en{args} = ({e:.4f}, {n:.4f}), expected other values")


@c.test("TODO 3: integrate() — start first, n + 1 rows, numpy array",
        hint="Lesson §6: row 0 = start, then each row = the previous one + the next step (a loop, or np.cumsum). "
             "Return np.array of shape (n + 1, 2).")
def _():
    (f,) = functions("navera_lite.vo", "integrate")
    steps = [(2.0, 1.0), (-1.5, 4.0), (0.25, -2.0), (3.0, 3.0)]
    v = go(f, steps, (-3.0, 5.0))
    if not isinstance(v, np.ndarray):
        raise CheckFailed(f"integrate() must return a numpy array, got {type(v).__name__} — np.array(...) at the end")
    want = np.array([[-3, 5], [-1, 6], [-2.5, 10], [-2.25, 8], [0.75, 11]], float)
    if v.shape == (4, 2):
        raise CheckFailed("integrate() returned 4 rows for 4 steps: row 0 must be the start (n + 1 rows)")
    c.ok(v.shape == (5, 2), f"integrate() of 4 steps must have shape (5, 2), got {v.shape}")
    if np.allclose(v, want - want[0] + 0, atol=1e-9) or np.allclose(v[0], 0):
        raise CheckFailed("integrate() ignores `start`: the track begins at start = (−3, 5)")
    c.ok(np.allclose(v, want, atol=1e-9), f"integrate(4 steps, start (−3, 5)) gave {np.round(v, 3).tolist()}")
    v = go(f, np.array([[1.0, 1.0]] * 3))
    c.ok(isinstance(v, np.ndarray) and np.allclose(v, [[0, 0], [1, 1], [2, 2], [3, 3]]),
         "integrate() of a numpy array of 3 steps (default start (0, 0)) is not [[0, 0], [1, 1], [2, 2], [3, 3]]")
    try:
        v = go(f, [], (7.0, 8.0))
    except CheckFailed as e:
        raise CheckFailed(f"integrate([], (7, 8)) — no step at all — {e}. With no step, np.array([]) has shape (0,), not "
                          "(0, 2): np.asarray(steps, dtype=float).reshape(-1, 2) (Lab Step 3, hint 5); the result must "
                          "be [[7., 8.]]")
    c.ok(isinstance(v, np.ndarray) and np.asarray(v).reshape(-1, 2).shape == (1, 2) and np.allclose(v, [[7, 8]]),
         "integrate([], (7, 8)) must give one row, the start: [[7., 8.]] (shape (1, 2))")


P1 = [(0, 0), (10, 10), (20, 5), (40, 40), (5, 30), (60, 2), (33, 3), (8, 8), (90, 50)]
P2 = [(4.0, -2.0), (14.5, 8.0), (24.0, 3.2), (0, 0), (9.0, 28.0), (66.0, -1.0), (37.4, 1.0), (11.9, 6.1), (10, 10)]


@c.test("TODO 4: median_shift() — the median of the votes, how many agree, no match",
        hint="Lesson §4: the votes are p2 − p1; dx, dy = the medians of their x and y (np.median); n_agree = how many "
             "votes are within tol_px (≤) of (dx, dy); with no match: (None, None, 0).")
def _():
    (f,) = functions("navera_lite.vo", "median_shift")
    v = go(f, P1, P2, 1.0)
    try:
        dx, dy, n = v
    except (TypeError, ValueError):
        raise CheckFailed(f"median_shift() must return three things (dx, dy, n_agree), got {v!r}")
    d = np.array(P2) - np.array(P1)
    if abs(float(dx) - d[:, 0].mean()) < 1e-6:
        raise CheckFailed("median_shift() returned the MEAN of the votes: three wrong matches pull it far away — use "
                          "np.median")
    c.ok(abs(float(dx) - 4.0) < 1e-9 and abs(float(dy) + 2.0) < 1e-9,
         f"median_shift on 9 unseen matches (3 wrong) gave ({dx}, {dy}), expected other values")
    c.ok(int(n) == 6, f"n_agree with tol_px = 1.0 is {n}: count the votes within 1.0 px of (dx, dy)")
    v = go(f, P1, P2, 2.5)
    c.ok(int(v[2]) == 7, f"with tol_px = 2.5, n_agree is {v[2]}: use the tol_px argument (and ≤)")
    v = go(f, [(0, 0), (1, 1), (2, 2), (3, 3)], [(1, 2), (3, 3), (5, 4), (4, 5)], 0.5)
    c.ok(np.allclose([float(v[0]), float(v[1])], [1.5, 2.0]),
         f"with 4 votes (an even number) you gave {v!r}: np.median takes the mean of the two middle values")
    c.ok(int(v[2]) == 3, f"dx, dy = (1.5, 2.0) are right, but n_agree = {v[2]}: three votes lie exactly tol_px = 0.5 px "
         "away — count with ≤ (distance ≤ tol_px), not <")
    v = go(f, np.zeros((0, 2)), np.zeros((0, 2)))
    c.ok(isinstance(v, tuple) and len(v) == 3 and v[0] is None and v[1] is None and v[2] == 0,
         f"with no match at all, median_shift must return (None, None, 0), got {v!r}")


@c.test("Your odometer on an unseen flight: 12 steps with a turn, another height",
        hint="If TODO 1–3 pass, this passes. The check turns each frame by the heading change (like derotate), calls YOUR "
             "phase_shift, px_to_en (heading of the newer frame) and integrate.")
def _():
    import cv2
    ps, pe, it = functions("navera_lite.vo", "phase_shift", "px_to_en", "integrate")
    d = np.load(io.BytesIO(hidden("test_flight.npz", text=False)))
    fr, hd, mpp, truth = d["frames"], d["heading"], float(d["m_per_px"]), d["truth"]
    steps = []
    for i in range(1, len(fr)):
        turn = (hd[i] - hd[i - 1] + 180.0) % 360.0 - 180.0
        a = fr[i - 1].astype(np.float32)
        R = cv2.getRotationMatrix2D(((a.shape[1] - 1) / 2.0, (a.shape[0] - 1) / 2.0), float(turn), 1.0)
        a = cv2.warpAffine(a, R, (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        dx, dy, _ = three(go(ps, a, fr[i]), "phase_shift")
        steps.append(two(go(pe, dx, dy, mpp, float(hd[i])), "px_to_en"))
    tr = np.asarray(go(it, steps), dtype=float)
    c.ok(tr.shape == truth.shape, f"integrate() gave shape {tr.shape} for {len(steps)} steps")
    err = np.hypot(*(tr - truth).T)
    print(f"  your odometer on the unseen flight: largest error {err.max():.2f} m over {len(steps)} steps")
    c.ok(err.max() < 0.6, f"on an unseen 12-step flight (216 m, a 30° turn) your track is {err.max():.1f} m off the "
         "truth at worst (the reference odometer: 0.13 m). Run `python3 run_vo.py leg` and compare with OpenCV.")


@c.test("Steps 0–4: the slide by hand, your FFT vs OpenCV, the drift and its two causes",
        hint="Copy the numbers printed by `pair`, `compare` and the three `leg` runs (lab Steps 0–4); explain in your "
             "own words.")
def _():
    (sl, ps, md, why_sp, db, sr, he, ta, dt, dbo, why_b) = answers(
        "SLIDE_PX", "PREDICT_SEA", "MEAN_DIFF_PX", "EXPLAIN_SUBPIXEL", "DRIFT_BARO", "SCALE_RATIO",
        "HEADING_ERROR_DEG", "TRUE_ALT_M", "DRIFT_TRUE_ALT", "DRIFT_BOTH", "EXPLAIN_BIAS")
    sl = number(sl, "SLIDE_PX")
    if abs(sl - 20.0) < 0.5:
        raise CheckFailed("SLIDE_PX = 20 is in metres: divide by the metres per pixel (2 h tan(HFOV/2) / W)")
    c.ok(37.5 <= sl <= 40.5, f"SLIDE_PX = {sl:g}: 20 m divided by the ground size of one pixel at the barometer "
         "height (lesson §1) — check math.radians and the 320 px width")
    predicted("PREDICT_SEA", ps)
    md = number(md, "MEAN_DIFF_PX")
    c.near(md, 0.061, 0.02, "MEAN_DIFF_PX (the mean |your shift − OpenCV's| of `compare`)")
    explained("EXPLAIN_SUBPIXEL", why_sp,
              ((r"sub.?pixel", r"parabol", r"centroid", r"between pixel", r"fraction", r"refine", r"interpol"),
               "where the small difference comes from (the sub-pixel refinement)"),
              ((r"same", r"integer", r"whole", r"agree", r"peak", r"both", r"identical"), "what both methods agree on"))
    db, sr, he, ta, dt, dbo = (number(v, n) for v, n in ((db, "DRIFT_BARO"), (sr, "SCALE_RATIO"),
                                                          (he, "HEADING_ERROR_DEG"), (ta, "TRUE_ALT_M"),
                                                          (dt, "DRIFT_TRUE_ALT"), (dbo, "DRIFT_BOTH")))
    c.near(db, 4.63, 0.08, "DRIFT_BARO (m per 100 m, `python3 run_vo.py leg`)")
    if abs(sr - 0.969) < 0.004:
        raise CheckFailed("SCALE_RATIO is upside down: the runner prints 'the truth is k × your step length'")
    c.near(sr, 1.032, 0.005, "SCALE_RATIO")
    c.ok(1.9 <= abs(he) <= 2.1, f"HEADING_ERROR_DEG = {he:g}: the angle printed by `leg` (how far your steps point "
         "away from the true ones)")
    if abs(ta - 116.4) < 0.6 or abs(ta - 112.8) < 1:
        raise CheckFailed(f"TRUE_ALT_M = {ta:g}: the barometer's height × SCALE_RATIO (steps 3 % too short = height 3 % "
                          "too low)")
    c.near(ta, 120.1, 1.0, "TRUE_ALT_M")
    c.near(dt, 3.51, 0.15, "DRIFT_TRUE_ALT (`leg --altitude …` with your TRUE_ALT_M)")
    c.ok(0 <= dbo <= 0.3, f"DRIFT_BOTH = {dbo:g}: `leg --altitude … --heading-offset …` with both corrections "
         "(the offset has the opposite sign of the error)")
    explained("EXPLAIN_BIAS", why_b,
              ((r"baro", r"height", r"altitude", r"scale", r"short", r"3 ?%"), "the first cause (the height, the scale)"),
              ((r"heading", r"imu", r"compass", r"direction", r"angle", r"2 ?°", r"2 deg", r"turn", r"rotat"),
               "the second cause (the heading)"),
              ((r"bias", r"system", r"every step", r"same", r"constant", r"each step", r"grow", r"linear",
                r"never cancel", r"accumul"), "why such errors add up step after step"))


@c.test("Step 5: the odometer race — turns, the coast, keypoints, your learned descriptor",
        hint="Compute TURN_LIMIT_DEG by hand; copy OK_PHASE_TURN4, OK_ORB_COAST and the two turn30 match counts from "
             "`python3 run_vo.py odometers` (it also saves out/odometers.json); explain in your own words.")
def _():
    import json
    tl, pt, okt, okc, li, lt, why = answers("TURN_LIMIT_DEG", "PREDICT_RACE", "OK_PHASE_TURN4", "OK_ORB_COAST",
                                            "LEARNED_IMU_TURN30", "LEARNED_MATCHES_TURN30", "EXPLAIN_ODOMETERS")
    tl = number(tl, "TURN_LIMIT_DEG")
    if abs(tl - 20.5) < 1.5:
        raise CheckFailed("TURN_LIMIT_DEG: math.asin works in radians — convert the result with math.degrees")
    c.ok(0.30 <= tl <= 0.40, f"TURN_LIMIT_DEG = {tl:g}: solve 160 · sin θ = 1 px for θ, in degrees (lesson §4: the "
         "edges of a 320 px frame are 160 px from its centre)")
    predicted("PREDICT_RACE", pt)
    if not os.path.exists("out/odometers.json"):
        raise CheckFailed("out/odometers.json is missing: run `python3 run_vo.py odometers` (Step 5)")
    try:
        run_ = json.load(open("out/odometers.json"))
        right, matches = run_["right"], run_["matches"]
        r_t4, r_coast = right["turn4"]["phase"], right["coast"]["ORB+IMU"]
        m_imu, m_fit = matches["turn30"]["learned+IMU"], matches["turn30"]["learned fit"]
    except (ValueError, KeyError, TypeError):
        raise CheckFailed("out/odometers.json cannot be read: run `python3 run_vo.py odometers` again (Step 5)")
    okt, okc = number(okt, "OK_PHASE_TURN4"), number(okc, "OK_ORB_COAST")
    c.ok(okt == r_t4, f"OK_PHASE_TURN4 = {okt:g}, but your run says {r_t4}: the 'turn4' row, column 'phase' (without the "
         "IMU)")
    c.ok(0 <= r_t4 <= 2, f"your raw phase correlation got {r_t4} of 8 right after a 4° turn: it should break (≤ 2). Is "
         "your phase_shift right (check 1)?")
    c.ok(okc == r_coast, f"OK_ORB_COAST = {okc:g}, but your run says {r_coast}: the 'coast' row, column 'ORB+IMU'")
    li, lt = number(li, "LEARNED_IMU_TURN30"), number(lt, "LEARNED_MATCHES_TURN30")
    if abs(li - m_fit) <= 1 and abs(lt - m_imu) <= 1 and abs(m_imu - m_fit) > 1:
        raise CheckFailed("LEARNED_IMU_TURN30 and LEARNED_MATCHES_TURN30 are swapped: 'learned+IMU' is the derotated "
                          "column, 'learned fit' the one without the IMU")
    c.ok(abs(li - m_imu) <= 1, f"LEARNED_IMU_TURN30 = {li:g}, but your run says {m_imu:g}: the matches table, row turn30, "
         "column 'learned+IMU' (the turn removed first)")
    c.ok(abs(lt - m_fit) <= 1, f"LEARNED_MATCHES_TURN30 = {lt:g}, but your run says {m_fit:g}: the matches table, row "
         "turn30, column 'learned fit' (the last one, without the IMU)")
    explained("EXPLAIN_ODOMETERS", why,
              ((r"rotat", r"turn", r"imu", r"derotat", r"heading"), "why phase correlation needs the IMU's turn"),
              ((r"coast", r"beach", r"sand", r"corner", r"every pixel", r"all (the )?pixels", r"low.?texture",
                r"little texture"), "why phase correlation still beats keypoints on the coast"),
              ((r"\bms\b", r"slow", r"cost", r"expensive", r"times (slower|longer)", r"train", r"20 ?°", r"range",
                r"half"), "what your learned descriptor costs, or where it stops working"))
    if m_fit >= 0.9 * m_imu:
        explained("EXPLAIN_ODOMETERS", why,
                  ((r"augment", r"rot90", r"rotat\w* (robust|invarian|proof)", r"trained (with|on) (larger|bigger|all|any)",
                    r"invarian"), "why YOUR network kept its matches after a 30° turn (the course's ±20° network loses "
                   "about half: what did you train differently?)"))


c.milestone("odometer", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "Your odometer", "Steps 0–4:", "Step 5:",
            label="Odometer")


# ======================================================================== session 2 — Navigator
@c.test("TODO 5: drift_sigma() — variances add, the bias adds up; numbers and arrays",
        hint="Lesson §7: the RMS after n steps in one axis is √(n²·bias² + n·σ²). Use np.sqrt so that n may be an array.")
def _():
    (f,) = functions("navera_lite.vo", "drift_sigma")
    v = number(go(f, 16, 0.5, 0.25), "drift_sigma(16, 0.5, 0.25)")
    if abs(v - (0.5 * 16 + 0.25 * 16)) < 1e-6 or abs(v - (0.5 * 4 + 0.25 * 16)) < 1e-6:
        raise CheckFailed(f"drift_sigma(16, 0.5, 0.25) = {v:g}: σ's do not add — VARIANCES add (n·σ² for the random "
                          "part, (n·bias)² for the bias), then one square root")
    c.ok(abs(v - math.sqrt(20.0)) < 1e-9, f"drift_sigma(16, 0.5, 0.25) = {v:.5g}, expected another value")
    a = go(f, np.array([0, 1, 4, 9]), 0.3, 0.1)
    a = np.asarray(a, dtype=float)
    c.ok(a.shape == (4,) and np.allclose(a, [0.0, 0.31622777, 0.72111026, 1.27279221]),
         f"drift_sigma(np.array([0, 1, 4, 9]), 0.3, 0.1) = {np.round(a, 4).tolist()}: one value per n (np.sqrt)")


@c.test("TODO 6: simulate_drift() — repeatable, the right shape, the RMS of the sums",
        hint="Lab Step 6: rng = np.random.default_rng(seed); errors = bias + rng.normal(0, σ, (trials, n_steps)); "
             "np.cumsum along the steps (axis=1); the RMS over the trials (axis=0).")
def _():
    (f,) = functions("drift_sim.py", "simulate_drift")
    a = np.asarray(go(f, 50, 0.0, 0.3, trials=10, seed=1), dtype=float)
    c.ok(a.shape == (50,), f"simulate_drift(50, …) must return 50 numbers, got shape {a.shape}")
    c.ok(np.allclose(a, 0.3 * np.arange(1, 51)), "with no randomness (σ = 0) the RMS after k steps is exactly k · bias: "
         "the error after k steps is the SUM of the first k step errors (np.cumsum, axis=1)")
    a = np.asarray(go(f, 64, 1.0, 0.0, trials=4000, seed=3), dtype=float)
    if a[-1] < 0.5:
        raise CheckFailed("the RMS after 64 random steps of σ = 1 is about 8; yours is near 0 — the mean of signed "
                          "errors cancels: square, average over the trials, square root")
    if abs(a[-1] - 1.0) < 0.15:
        raise CheckFailed("after 64 random steps your RMS is still about 1: the errors must ACCUMULATE (np.cumsum "
                          "along the steps) before the RMS")
    c.ok(abs(a[-1] - 8.0) < 0.4 and abs(a[15] - 4.0) < 0.25,
         f"σ = 1, no bias: RMS after 16 and 64 steps = {a[15]:.2f}, {a[-1]:.2f}; theory 4 and 8 (did you average over "
         "the trials, axis 0?)")
    b = np.asarray(go(f, 64, 1.0, 0.0, trials=4000, seed=3), dtype=float)
    d = np.asarray(go(f, 64, 1.0, 0.0, trials=4000, seed=4), dtype=float)
    c.ok(np.array_equal(a, b), "the same seed must give the same result: np.random.default_rng(seed), inside the "
         "function")
    c.ok(not np.array_equal(a, d), "another seed gives exactly the same result: use the seed argument")
    e = np.asarray(go(f, 30, 0.5, 0.1, trials=300, seed=0), dtype=float)
    c.ok(e.shape == (30,), "simulate_drift must use the trials argument and still return n_steps numbers")


@c.test("TODO 7: blend() — inverse-variance weights, numbers and arrays",
        hint="Lesson §8: x = (x1·v2 + x2·v1) / (v1 + v2), v = v1·v2 / (v1 + v2) — v1 and v2 are VARIANCES (σ²).")
def _():
    (f,) = functions("navera_lite.vo", "blend")
    x, v = two(go(f, -4.0, 25.0, 6.0, 100.0), "blend")
    if abs(x - 4.0) < 1e-6:
        raise CheckFailed("blend(−4, 25, 6, 100) = 4.0: the weights are swapped — the estimate with the SMALLER "
                          "variance (−4, variance 25) must count more")
    if abs(x - 1.0) < 1e-6:
        raise CheckFailed("blend(−4, 25, 6, 100) gave the plain average 1.0: weight each estimate by the OTHER one's "
                          "variance")
    c.ok(abs(x + 2.0) < 1e-9, f"blend(−4, 25, 6, 100): x = {x:g}, expected another value")
    if abs(v - 3.3333) < 1e-3 or abs(v - 125.0) < 1e-6:
        raise CheckFailed(f"blend(−4, 25, 6, 100): v = {v:g} — the blended variance is v1·v2 / (v1 + v2)")
    c.ok(abs(v - 20.0) < 1e-9, f"blend(−4, 25, 6, 100): v = {v:g}, expected 20")
    r = go(f, np.array([1.0, 50.0]), np.array([4.0, 4.0]), np.array([3.0, 44.0]), np.array([12.0, 1.0]))
    try:
        x, v = (np.asarray(t, dtype=float) for t in r)
    except (TypeError, ValueError):
        raise CheckFailed(f"blend() on arrays must return (x, v) — two arrays, got {r!r}")
    c.ok(x.shape == (2,) and np.allclose(x, [1.5, 45.2]) and np.allclose(v, [3.0, 0.8]),
         "blend() on arrays (east and north at once) must work element by element: use numpy operations, not math")


@c.test("TODO 8: vo_gate() — the distance between two velocity vectors against k·σ",
        hint="Lesson §9: compare the two velocity VECTORS (not only the speeds) with k · sigma_mps; exactly k·σ apart "
             "is still accepted. Return a bool, and use k.")
def _():
    (f,) = functions("navera_lite.vo", "vo_gate")
    cases = [(((20.0, 0.0), (-20.0, 0.0), 2.0), False, "same speed, opposite direction: the VECTORS differ by 40 m/s"),
             (((3.0, 4.0), (0.0, 0.0), 1.0), False, "5 m/s apart, 3 × 1 = 3 m/s allowed"),
             (((6.0, 8.0), (0.0, 0.0), 2.0, 5.0), True, "10 m/s apart with k = 5, σ = 2: 10 is allowed (≤)"),
             (((0.0, 0.0), (0.0, 6.0), 2.0), True, "exactly 3σ apart: allowed (≤)"),
             (((10.0, 10.0), (11.0, 9.0), 0.5), True, "1.41 m/s apart, 1.5 allowed"),
             (((14.0, 14.0), (14.1, 14.2), 0.05, 1.0), False, "0.22 m/s apart, k = 1: only 0.05 allowed (use k)")]
    for args, want, why in cases:
        v = go(f, *args)
        if not isinstance(v, (bool, np.bool_)):
            raise CheckFailed(f"vo_gate{args} must return True or False, got {v!r}")
        c.ok(bool(v) == want, f"vo_gate{args} = {v}: expected {want} ({why})")


@c.test("Steps 6–9: growth exponents, your threshold, the gate, the fixes",
        hint="Copy the numbers printed by `python3 drift_sim.py`, `responses` and `fuse` (lab Steps 6–9) and explain in "
             "your own words.")
def _():
    (pg, er, eb, nc, mr, sea, why_t, pgt, gr, wc, wd, cov, why_f) = answers(
        "PREDICT_GROWTH", "EXPONENT_RANDOM", "EXPONENT_BIAS", "N_CROSS", "MIN_RESPONSE", "SEA_MAX_RESPONSE",
        "EXPLAIN_THRESHOLD", "PREDICT_GATE", "GATE_REFUSED", "WORST_NO_FIX", "WORST_FUSED", "COVERAGE",
        "EXPLAIN_FUSION")
    predicted("PREDICT_GROWTH", pg)
    er, eb, nc = number(er, "EXPONENT_RANDOM"), number(eb, "EXPONENT_BIAS"), number(nc, "N_CROSS")
    c.near(er, 0.50, 0.03, "EXPONENT_RANDOM")
    c.near(eb, 1.00, 0.02, "EXPONENT_BIAS")
    if abs(nc - 5.0) < 0.6 or abs(nc - 50.0) < 1:
        raise CheckFailed(f"N_CROSS = {nc:g}: the two parts are equal when n²·b² = n·σ², so n = σ² / b² (squares)")
    c.near(nc, 25.0, 1.0, "N_CROSS (σ = 0.5 m, bias = 0.1 m)")
    mr, sea = number(mr, "MIN_RESPONSE"), number(sea, "SEA_MAX_RESPONSE")
    c.near(sea, 0.030, 0.003, "SEA_MAX_RESPONSE (the highest response of a wrong step over the water, `responses`)")
    if mr >= 0.1:
        raise CheckFailed(f"MIN_RESPONSE = {mr:g} refuses right steps (steps 51, 78 and 79 are right with responses "
                          "below 0.1) — and it still lets the overlay steps through: look at the two kinds of wrong "
                          "steps in `responses`")
    if mr > 0.0401:
        raise CheckFailed(f"MIN_RESPONSE = {mr:g} would refuse the right step 51 (response 0.040). Read the printed "
                          "numbers (three decimals), not the plot, and choose a value strictly between the two groups")
    c.ok(mr >= 0.0305, f"MIN_RESPONSE = {mr:g} would keep the wrong steps 66 and 77 over the water (response 0.030): "
         "choose a value strictly between 0.030 and 0.040 (three or four decimals)")
    explained("EXPLAIN_THRESHOLD", why_t,
              ((r"sea", r"water", r"wave", r"move", r"nothing fixed", r"texture"), "why the steps over the water are weak"),
              ((r"overlay", r"osd", r"text", r"box", r"static", r"stuck", r"fixed in the (picture|image|frame)"),
               "what a threshold cannot catch (and why)"),
              ((r"margin", r"narrow", r"thin", r"small gap", r"0\.01", r"close", r"risk", r"safe", r"knife"),
               "how safe your margin is"))
    predicted("PREDICT_GATE", pgt)
    gr, wc, wd, cov = (number(v, n) for v, n in ((gr, "GATE_REFUSED"), (wc, "WORST_NO_FIX"), (wd, "WORST_FUSED"),
                                                (cov, "COVERAGE")))
    c.ok(gr == 7, f"GATE_REFUSED = {gr:g}: how many steps your gate refused in stage D (the list under the table)")
    c.near(wc, 52.6, 2.0, "WORST_NO_FIX (stage C, worst error)")
    c.near(wd, 18.9, 1.5, "WORST_FUSED (stage D, worst error)")
    if cov > 1.0:
        cov = cov / 100.0
    c.near(cov, 0.78, 0.03, "COVERAGE (stage D, 'within 2σ', as a share or a %)")
    explained("EXPLAIN_FUSION", why_f,
              ((r"fix", r"map", r"blend", r"reset", r"drop", r"saw"), "what each map fix does to the error"),
              ((r"sea", r"water", r"gap", r"long", r"no fix"), "where the worst error comes from"),
              ((r"\b20\b", r"\b30\b", r"unlucky", r"fix(es)? (was|were|is|are) .*off", r"fix error", r"wrong fix",
                r"bad fix", r"after (the )?fix"), "where the true error leaves the 2σ band (and why)"),
              ((r"86", r"honest", r"optimist", r"over.?confiden", r"too small", r"one flight", r"few", r"correlat",
                r"proof", r"evidence", r"hint"), "what 78 % from one flight can and cannot tell"))


@c.test("report.md: four headings, your own words, your numbers",
        hint="Lab Step 10: keep the four ## headings, 200–450 words, replace every TODO, quote DRIFT_BARO, "
             "OK_PHASE_TURN4, WORST_FUSED and COVERAGE as numbers.")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## 1. The odometer", "## 2. The drift", "## 3. The odometer race", "## 4. The navigator"):
        c.ok(h in text, f"report.md lost its heading “{h}”")
    c.ok("TODO" not in text, "report.md still contains a TODO")
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    n = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body))
    c.ok(200 <= n <= 450, f"report.md has {n} words; write 200–450")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    db, okt, wd, cov = answers("DRIFT_BARO", "OK_PHASE_TURN4", "WORST_FUSED", "COVERAGE")  # noqa: F841
    for v, name, tol in ((db, "DRIFT_BARO", 0.011), (okt, "OK_PHASE_TURN4", 0.01), (wd, "WORST_FUSED", 0.11)):
        v = number(v, name)
        c.ok(any(abs(x - v) <= tol for x in nums), f"report.md does not quote your {name} ({v:g})")
    cv = number(cov, "COVERAGE")
    cv = cv / 100.0 if cv > 1 else cv
    c.ok(any(abs(x - cv) <= 0.011 or abs(x - 100 * cv) <= 1.1 for x in nums),
         f"report.md does not quote your COVERAGE ({cv:g} or {100 * cv:.0f} %)")


c.milestone("navigator", "TODO", "Your odometer", "Step", "report", label="Navigator")

c.run()
