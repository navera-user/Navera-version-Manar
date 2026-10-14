import contextlib
import io
import math
import os
import re

import numpy as np

from academy_check import (CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run)

c = Checker()
DATA = "/data/academy/25-thermal-night"


# ---------------------------------------------------------------- loading and small helpers
def module(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def functions(mod, *names):
    m = module(f"navera_lite.{mod}")
    fns = need(m, *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/{mod}.py)")
    return fns


def answers(*names):
    return need(module("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def go(fn, *args, seconds=60, **kw):
    try:
        return run(fn, *args, seconds=seconds, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "mat1 and mat2" in msg:
            msg += " — fc1 gets the wrong size: four 2 × 2 poolings, then flatten to 64 * 4 * 4"
        if "checkVector" in msg:
            msg += " — cv2.getPerspectiveTransform wants two float32 arrays of shape (4, 2)"
        if "same device" in msg:
            msg += " — move each batch with to_input(…, device) and the targets with .to(device)"
        raise CheckFailed(msg)


def arr(v, what, shape=None):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return numbers, got {type(v).__name__}")
    if shape is not None and a.shape != shape:
        raise CheckFailed(f"{what} should have shape {shape}, got {a.shape}")
    return a


def is_float(v):
    return isinstance(v, (float, np.floating)) and not isinstance(v, bool)


UNIT = None


def unit():
    global UNIT
    if UNIT is None:
        UNIT = dict(np.load(io.BytesIO(hidden("unit_cases.npz", text=False))))
    return UNIT


# ======================================================================== session 1 — Night watch
_r = np.random.default_rng(2525)
NA = _r.integers(0, 256, (7, 9))
NB = _r.integers(0, 256, (7, 9))
NCC_AB = 0.06757847320387891


@c.test("TODO 1: ncc() on unseen pictures — gain and offset cancel, a negative gives −1, uniform gives 0",
        hint="Lesson §2: subtract each picture's mean (in float64), Σ(a·b) / √(Σa² · Σb²); return 0.0 when the "
             "denominator is 0; return float(...).")
def _():
    (f,) = functions("night", "ncc")
    v = go(f, NA, NB)
    if not is_float(v):
        raise CheckFailed(f"ncc() must return a float, got {type(v).__name__} ({v!r:.60})")
    c.near(v, NCC_AB, 1e-9, "ncc() on two unseen 7 × 9 pictures")
    g = go(f, NA, 0.37 * NA + 55.0)
    if abs(float(g) - 1.0) > 1e-9:
        raise CheckFailed(f"ncc(a, 0.37·a + 55) = {float(g):.6f}, it must be 1.0: subtract BOTH means before multiplying")
    n = go(f, NA.astype(np.uint8), (255 - NA).astype(np.uint8))
    if abs(float(n) + 1.0) > 1e-9:
        raise CheckFailed(f"ncc(a, 255 − a) on uint8 pictures = {float(n):.6f}, it must be −1.0: convert to float64 "
                          "first (uint8 arithmetic wraps around)")
    u = go(f, NA, np.full((7, 9), 12))
    if u is None or (isinstance(u, float) and math.isnan(u)):
        raise CheckFailed("ncc(a, uniform picture) is nan or None: return 0.0 when there is nothing to compare")
    c.near(u, 0.0, 1e-12, "ncc(a, uniform picture)")


@c.test("TODO 2: footprint_m() with unseen heights and fields of view, in radians inside",
        hint="Lesson §3: width = 2·h·tan(hfov/2), height = 2·h·tan(vfov/2), with math.radians.")
def _():
    (f,) = functions("night", "footprint_m")
    v = arr(go(f, 250.0, 50.0, 40.0), "footprint_m(250, 50, 40)", (2,))
    if np.allclose(v, [116.58, 90.99], atol=0.05):
        raise CheckFailed("footprint_m(250, 50, 40) is half the right size: 2·h·tan(fov/2) — the camera sees "
                          "tan(fov/2)·h on EACH side")
    c.ok(np.allclose(v, [233.1538, 181.9851], atol=1e-3), f"footprint_m(250, 50, 40) = {np.round(v, 2).tolist()}: "
         "not right — tan of HALF the angle, in radians, times 2·h")
    w = arr(go(f, 1234.0, 12.0, 9.0), "footprint_m(1234, 12, 9)", (2,))
    c.ok(np.allclose(w, [259.3973, 194.2358], atol=1e-3), f"footprint_m(1234, 12, 9) = {np.round(w, 2).tolist()}: "
         "use each field of view for its own axis (hfov → width, vfov → height)")


COV = [((520.0, 380.0, 0.0, 450.0), 0.844444), ((520.0, 380.0, 37.0, 450.0), 0.808004),
       ((300.0, 200.0, -120.0, 500.0), 0.24), ((900.0, 900.0, 45.0, 500.0), 1.0),
       ((700.0, 420.0, 180.0, 450.0), 0.933333), ((450.0, 650.0, 63.0, 480.0), 0.897373)]


@c.test("TODO 3: coverage() on six unseen cameras, headings and squares (±0.005)",
        hint="Lesson §3 and lab Step 3: the share of the SQUARE inside the turned rectangle (grid of points or "
             "cv2.intersectConvexConvex), half sizes w/2 and h/2, the heading in radians.")
def _():
    (f,) = functions("night", "coverage")
    bad = []
    for args, want in COV:
        v = go(f, *args)
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float, np.floating)):
            raise CheckFailed(f"coverage{args} must return a number from 0 to 1, got {v!r:.60}")
        v = float(v)
        if v > 1.0001:
            raise CheckFailed(f"coverage{args} = {v:.4f} > 1: divide the overlap by the square's area")
        if abs(v - want) > 0.005:
            bad.append((args, v))
    if bad:
        args, v = bad[0]
        if all(a[2] != 0.0 for a, _ in bad):
            raise CheckFailed(f"coverage{args} = {v:.4f}: right at heading 0° but not when the rectangle is turned — "
                              "the heading in radians (math.radians), and u, v both use cos and sin")
        raise CheckFailed(f"coverage{args} = {v:.4f}: not right — the share of the SQUARE inside the rectangle, which "
                          "reaches w/2 and h/2 on each side of the centre")


PREP_CASES = [(251, 300, 400, 300.0, 70.0, 55.0, 25.0, 6.0, 64), (252, 256, 320, 500.0, 60.0, 48.0, -110.0, 9.0, 40),
              (253, 240, 360, 450.0, 80.0, 56.0, 90.0, 8.0, 56)]


def smooth_frame(seed, h, w):
    import cv2
    rng = np.random.default_rng(seed)
    small = rng.uniform(0, 255, (h // 16 + 2, w // 16 + 2)).astype(np.float32)
    big = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    yy, xx = np.mgrid[0:h, 0:w]
    big = 0.7 * big + 0.3 * (255 * xx / w)
    return np.clip(big, 0, 255).astype(np.uint8)


@c.test("TODO 4: prepare() on three unseen frames — scale, north-up, centre, coverage, and refusal",
        hint="Lab Step 5: coverage first (square side out_px · map_m_per_px); then ONE cv2.warpAffine whose 2 × 2 part "
             "turns by the heading and scales by (footprint / pixels) / map_m_per_px, centre → ((out−1)/2, (out−1)/2).")
def _():
    import cv2
    (f,) = functions("night", "prepare")
    u = unit()
    for k, (seed, h, w, alt, hf, vf, hd, mpp, op) in enumerate(PREP_CASES):
        out = go(f, smooth_frame(seed, h, w), alt, hf, vf, hd, mpp, op, need=0.5)
        if not (isinstance(out, tuple) and len(out) == 3):
            raise CheckFailed(f"prepare() must return (patch, cov, reason), got {type(out).__name__}")
        patch, cov, why = out
        c.near(cov, float(u[f"prep{k}_cov"]), 0.005, f"the coverage returned by prepare() (case {k + 1})")
        if patch is None:
            raise CheckFailed(f"prepare() refused case {k + 1} (coverage {float(cov):.2f} ≥ need = 0.5): use the "
                              "`need` argument")
        p = arr(patch, f"prepare() case {k + 1}", (op, op))
        want = u[f"prep{k}"].astype(float)
        inside = cv2.erode((want > 0).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        err = float(np.abs(p - want)[inside].mean())
        if err > 6.0:
            hint = ""
            if np.abs(p - u[f"prep{k}_wrongturn"].astype(float))[inside].mean() < 3.0:
                hint = (" (it is turned the OTHER way: the frame's top must end at the heading, clockwise from north — "
                        "lab Step 5, the 🧰 box 'which way to turn')")
            elif np.abs(p - u[f"prep{k}_corner"].astype(float))[inside].mean() < 3.0:
                hint = (" (half a pixel off: the frame's centre point is ((w − 1)/2, (h − 1)/2) and it must land on "
                        "((out_px − 1)/2, (out_px − 1)/2))")
            elif np.abs(np.rot90(p, 2) - want)[inside].mean() < 6.0:
                hint = " (it looks turned by 180°: check the direction of the turn)"
            raise CheckFailed(f"prepare() case {k + 1} (heading {hd:g}°, {op} px): your patch differs from the right "
                              f"one by {err:.0f} grey levels on average{hint}. Check the scale, the turn and the centre "
                              "(lab Step 5 hints)")
        if k == 0:
            empty = want == 0
            c.ok(float((p[empty] == 0).mean()) > 0.9, "where the frame does not cover the square, the patch must be 0 "
                 "(borderValue=0)")
    out = go(f, smooth_frame(254, 240, 320), 200.0, 70.0, 55.0, 20.0, 6.0, 64)
    if not (isinstance(out, tuple) and len(out) == 3) or out[0] is not None or "fly higher" not in str(out[2]):
        raise CheckFailed("at 200 m (coverage ≈ 0.4) prepare() must return (None, cov, a reason with 'fly higher')")


_s = np.random.default_rng(3).integers(0, 256, (40, 50)).astype(np.uint8)


@c.test("TODO 5: ncc_locate() finds an unseen template, centre to centre, with another brightness",
        hint="Lab Step 6: cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED), cv2.minMaxLoc → top-left (x, y); "
             "dx = x + (tw − 1)/2 − (sw − 1)/2, dy the same with heights.")
def _():
    (f,) = functions("night", "ncc_locate")
    v = arr(go(f, _s[7:18, 13:28], _s), "ncc_locate", (3,))
    if np.allclose(v[:2], [13, 7]):
        raise CheckFailed("ncc_locate returned the template's TOP-LEFT corner (13, 7): return its centre relative to "
                          "the search area's centre")
    if np.allclose(v[:2], [-7.5, -4.5]):
        raise CheckFailed("ncc_locate returned (dy, dx): minMaxLoc gives (x, y) = (column, row)")
    c.ok(np.allclose(v[:2], [-4.5, -7.5], atol=1e-6), f"ncc_locate found the template at ({v[0]:g}, {v[1]:g}) from "
         "the centre: not right — the template's centre minus the search area's centre point")
    c.near(v[2], 1.0, 1e-4, "the score of an exact copy")
    darker = np.clip(_s[7:18, 13:28].astype(float) * 0.5 + 20, 0, 255).astype(np.uint8)
    w = arr(go(f, darker, _s), "ncc_locate", (3,))
    c.ok(np.allclose(w[:2], [-4.5, -7.5], atol=1e-6), "a darker copy of the template must be found at the same "
         "place: use the NORMALISED mode cv2.TM_CCOEFF_NORMED")


@c.test("TODO 6: motion_gate() on unseen fixes, its arguments, and a negative elapsed time",
        hint="Lesson §5: reach = v_max_mps · max(0, t_s − t_anchor_s) + margin_m; refuse when the haversine distance "
             "is larger, with a reason containing 'jump'; no anchor → (True, …).")
def _():
    (f,) = functions("night", "motion_gate")
    a, b = (35.81, 10.62), (35.8125, 10.6225)
    v = go(f, a, 100.0, b, 108.0)
    if not (isinstance(v, tuple) and len(v) == 2):
        raise CheckFailed(f"motion_gate() must return (ok, reason), got {v!r:.80}")
    c.ok(v[0] is False, f"a 358 m jump in 8 s (limit 270 m) must be refused, got {v!r:.80}")
    c.ok("jump" in str(v[1]) and "358" in str(v[1]) and "270" in str(v[1]),
         f"the reason must contain 'jump', the distance and the limit in whole metres, got {v[1]!r:.80}")
    v = go(f, a, 100.0, b, 108.0, v_max_mps=40.0)
    c.ok(v[0] is False and "350" in str(v[1]), "with v_max_mps = 40 the limit is 350 m: use the v_max_mps argument")
    v = go(f, a, 100.0, b, 108.0, margin_m=200.0)
    c.ok(v[0] is True, "with margin_m = 200 the limit is 440 m and the fix is accepted: use the margin_m argument")
    v = go(f, a, 100.0, (35.8101, 10.6201), 95.0)
    c.ok(isinstance(v, tuple) and v[0] is True, "a fix 14 m away with a clock 5 s BEHIND the anchor: elapsed time "
         "max(0, t − t_anchor) = 0, reach = the margin (30 m) → accepted")
    v = go(f, None, 0.0, b, 3.0)
    c.ok(isinstance(v, tuple) and v[0] is True, "without an anchor (None) the first fix is accepted")


@c.test("Steps 0–2: your prediction, and the audit of the night replay set",
        hint="Run `python3 run_night.py audit`: the first line gives night frame 1's best day frame; the median best NCC "
             "is printed at the end. Then explain in your own words.")
def _():
    pl, pa, tw, an, why = answers("PREDICT_LOOK", "PREDICT_AUDIT", "TWIN_OF_NIGHT_01", "AUDIT_BEST_NCC", "EXPLAIN_AUDIT")
    predicted("PREDICT_LOOK", pl)
    predicted("PREDICT_AUDIT", pa)
    tw = number(tw, "TWIN_OF_NIGHT_01")
    if int(tw) == 1:
        raise CheckFailed("TWIN_OF_NIGHT_01 = 1: that is the label's frame number, not the day frame with the best NCC "
                          "(first line of `audit`)")
    c.eq(int(tw), 9, "TWIN_OF_NIGHT_01")
    an = number(an, "AUDIT_BEST_NCC")
    if 0.08 <= an <= 0.11:
        raise CheckFailed("AUDIT_BEST_NCC: that is the SECOND-best median; the question asks for the best")
    c.near(an, 0.899, 0.006, "AUDIT_BEST_NCC")
    explained("EXPLAIN_AUDIT", why,
              ((r"day", r"photo", r"copy", r"copies", r"dark", r"same frame", r"not thermal", r"fake", r"visible"),
               "what the night frames really are"),
              ((r"shadow", r"sun", r"label", r"position", r"place", r"\b8\b", r"eight", r"shift", r"offset",
                r"0\.9", r"ncc", r"correlat", r"bright"), "the clues"))


@c.test("Steps 3–5: coverage, the minimum heights of the first camera, the refused frame",
        hint="Copy the numbers of `python3 run_night.py coverage` (the 350 m row, the 30° column; the last line) and "
             "the frame `prepare` refused.")
def _():
    pf, cv, m0, m45, why, rf = answers("PREDICT_FIRST_CAM", "COV_350_30", "MIN_ALT_FIRST_0", "MIN_ALT_FIRST_45",
                                       "EXPLAIN_COVERAGE", "REFUSED_FRAME")
    predicted("PREDICT_FIRST_CAM", pf)
    cv = number(cv, "COV_350_30")
    if cv > 1:
        raise CheckFailed("COV_350_30 is a share from 0 to 1 (0.9, not 90)")
    c.near(cv, 0.896, 0.0015, "COV_350_30")
    m0, m45 = number(m0, "MIN_ALT_FIRST_0"), number(m45, "MIN_ALT_FIRST_45")
    if abs(m0 - 524) < 3 and abs(m45 - 474) < 3:
        raise CheckFailed("MIN_ALT_FIRST_0 and MIN_ALT_FIRST_45 are swapped")
    c.near(m0, 474, 2, "MIN_ALT_FIRST_0 (m)")
    c.near(m45, 524, 2, "MIN_ALT_FIRST_45 (m)")
    explained("EXPLAIN_COVERAGE", why,
              ((r"corner", r"diagonal", r"turn", r"rotat", r"45", r"stick out", r"outside"), "why 45° needs more height"),
              ((r"400", r"ceiling", r"never", r"cannot", r"can't", r"too low", r"no night", r"higher than", r"above"),
               "what it means for a drone limited to 400 m"))
    c.eq(int(number(rf, "REFUSED_FRAME")), 7, "REFUSED_FRAME")


@c.test("Steps 6–7: NCC in five conditions, and the gate's decisions",
        hint="Copy the 'good' column of `python3 run_night.py ncc` as shares (23 % → 0.23), and the times of the "
             "'refused' lines of `gate` as a list of numbers.")
def _():
    pn, gs, gn, gi, why, gr, whyg = answers("PREDICT_NCC", "NCC_GOOD_SAME", "NCC_GOOD_NIGHT", "NCC_GOOD_INVERTED",
                                            "EXPLAIN_NCC", "GATE_REFUSED", "EXPLAIN_GATE")
    predicted("PREDICT_NCC", pn)
    gs, gn, gi = (number(v, n) for v, n in ((gs, "NCC_GOOD_SAME"), (gn, "NCC_GOOD_NIGHT"), (gi, "NCC_GOOD_INVERTED")))
    if max(gs, gn, gi) > 1:
        raise CheckFailed("the NCC 'good' values are shares from 0 to 1 (0.23, not 23)")
    c.near(gs, 1.0, 0.015, "NCC_GOOD_SAME")
    c.near(gn, 0.230, 0.015, "NCC_GOOD_NIGHT")
    c.near(gi, 0.391, 0.015, "NCC_GOOD_INVERTED")
    explained("EXPLAIN_NCC", why,
              ((r"gain", r"offset", r"linear", r"bright", r"contrast", r"same (kind|sensor|picture)", r"scale"),
               "what NCC can undo"),
              ((r"monoton", r"revers", r"invert", r"order", r"road", r"tree", r"some", r"not all", r"material",
                r"differ"), "why the night is not a simple negative"))
    if isinstance(gr, (str, bytes)) or not hasattr(gr, "__iter__"):
        raise CheckFailed(f"GATE_REFUSED must be a list of times, e.g. [2.0, 6.0], got {gr!r:.60}")
    try:
        times = sorted(float(t) for t in gr)
    except (TypeError, ValueError):
        raise CheckFailed(f"GATE_REFUSED must hold numbers (seconds), got {gr!r:.60}")
    if times == [8.0]:
        raise CheckFailed("GATE_REFUSED = [8.0]: look at the end of the `gate` table too")
    c.ok(times == [8.0, 34.0, 36.0, 38.0, 40.0], f"GATE_REFUSED = {times}: copy the times of every 'refused' line")
    explained("EXPLAIN_GATE", whyg,
              ((r"reach", r"90", r"limit", r"too far", r"2 s", r"two seconds", r"speed", r"max"), "why 8 s was refused"),
              ((r"gap", r"14", r"long", r"450", r"grew", r"grow", r"larger", r"bigger", r"no fix", r"time"),
               "why 32 s was accepted"),
              ((r"anchor", r"lock", r"stuck", r"wrong", r"every", r"all", r"after", r"refus"), "what happened after it"))


c.milestone("night-watch", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "TODO 6:", "Steps 0–2:",
            "Steps 3–5:", "Steps 6–7:", label="Night watch")


# ======================================================================== session 2 — Night navigator
def scene(seed):
    return np.random.default_rng(seed).integers(0, 256, (140, 150)).astype(np.uint8)


CUT_CASES = [(261, (21.0, 33.0), [3.0, -2.0, 5.5, 1.0, -4.0, 6.0, 0.5, -7.5]),
             (262, (40.0, 12.0), [-9.0, 4.0, -6.0, 8.0, -11.0, 2.0, -7.0, 5.0])]


@c.test("TODO 7: cut_pair() on unseen scenes, corners and 4-point offsets",
        hint="Lab Step 8: square = SQUARE + (x0, y0), thermal corners = square + offsets.reshape(4, 2); "
             "getPerspectiveTransform from each to SQUARE (float32), warpPerspective to (PATCH_PX, PATCH_PX).")
def _():
    (f,) = functions("homography_net", "cut_pair")
    u = unit()
    for k, (seed, corner, off) in enumerate(CUT_CASES):
        out = go(f, scene(seed), scene(seed + 100), corner, off)
        if not (isinstance(out, tuple) and len(out) == 2):
            raise CheckFailed(f"cut_pair() must return (ref_patch, thermal_patch), got {type(out).__name__}")
        a = arr(out[0], "cut_pair's reference patch", (64, 64))
        b = arr(out[1], "cut_pair's thermal patch", (64, 64))
        c.ok(np.abs(a - u[f"cut{k}_a"]).mean() < 0.5, f"case {k + 1}: the reference patch is not the 64 px square "
             f"whose top-left pixel is at {corner}")
        e = float(np.abs(b - u[f"cut{k}_b"]).mean())
        if e > 1.0:
            if e < 20:
                raise CheckFailed(f"case {k + 1}: the thermal patch is close but not right ({e:.0f} grey levels off on "
                                  "average): warp onto the given SQUARE, whose corners are the pixel centres 0 and "
                                  "PATCH_PX − 1 = 63")
            raise CheckFailed(f"case {k + 1}: the thermal patch differs from the right one by {e:.0f} grey levels on "
                              "average: the thermal corners are the square's corners + offsets, warped onto SQUARE "
                              "(not the inverse)")
        c.ok(np.asarray(out[1]).dtype == np.uint8, "the patches must stay uint8")


@c.test("TODO 8: to_input() on unseen pairs — each channel on its own, (x − mean) / (std + 1), float32",
        hint="Lesson §7 and lab Step 9: x.mean(dim=(2, 3), keepdim=True), x.std(dim=(2, 3), keepdim=True), "
             "(x − m) / (s + 1.0); accept numpy and tensors; .float().")
def _():
    (f,) = functions("homography_net", "to_input")
    x = np.random.default_rng(271).integers(0, 256, (3, 2, 8, 8)).astype(np.uint8)
    x[1, 1] = 77
    t = go(f, x)
    got = arr(t.detach().cpu().numpy() if hasattr(t, "detach") else t, "to_input", (3, 2, 8, 8))
    want = unit()["toin"]
    if np.abs(got[1, 1]).max() > 1e-4:
        raise CheckFailed("a uniform channel must become all 0 (its mean removed); is the std taken per channel?")
    if not np.allclose(got, want, atol=1e-3):
        raise CheckFailed("to_input() gives other numbers: per pair and per channel (dim=(2, 3)), mean removed, "
                          "divided by (std + 1.0) with torch's default std")
    c.ok(str(getattr(t, "dtype", "")) == "torch.float32", f"to_input() must return a float32 tensor, got "
         f"{getattr(t, 'dtype', type(t).__name__)}")


def reference_net():
    """HomographyNet as the docstring specifies it, built by the check (never the student's class)."""
    import torch.nn as nn
    import torch.nn.functional as F

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(2, 16, 3, padding=1)
            self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
            self.conv3 = nn.Conv2d(32, 64, 3, padding=1)
            self.conv4 = nn.Conv2d(64, 64, 3, padding=1)
            self.fc1 = nn.Linear(1024, 128)
            self.fc2 = nn.Linear(128, 8)

        def forward(self, x):
            for conv in (self.conv1, self.conv2, self.conv3, self.conv4):
                x = F.max_pool2d(F.relu(conv(x)), 2)
            return self.fc2(F.relu(self.fc1(x.flatten(1))))
    return Net()


def norm_input(x):
    """The network's input as the docstring of to_input specifies it (computed by the check)."""
    import torch
    t = torch.as_tensor(np.asarray(x)).float()
    return (t - t.mean(dim=(2, 3), keepdim=True)) / (t.std(dim=(2, 3), keepdim=True) + 1.0)


def predict_ref(net, x, batch=256):
    import torch
    net.eval()
    with torch.no_grad():
        return np.concatenate([net(norm_input(x[s:s + batch])).numpy() * 16.0 for s in range(0, len(x), batch)])


def centre_err(pred, truth):
    import cv2
    sq = np.float32([[0, 0], [63, 0], [63, 63], [0, 63]])
    out = []
    for p, t in zip(pred, truth):
        cs = []
        for o in (p, t):
            H = cv2.getPerspectiveTransform(sq, (sq + np.asarray(o, np.float32).reshape(4, 2)).astype(np.float32))
            v = H @ np.array([31.5, 31.5, 1.0])
            cs.append(v[:2] / v[2])
        out.append(float(np.hypot(*(cs[0] - cs[1]))))
    return np.array(out)


@c.test("TODO 9: HomographyNet — the six layers of the table, 192 600 parameters, the forward pass in order",
        hint="Lab Step 10: super().__init__() then conv1…conv4, fc1, fc2 with the docstring's sizes; forward: four times "
             "conv → ReLU → max_pool2d(2), flatten(1), fc1, ReLU, fc2.")
def _():
    import tempfile
    import torch
    hn = module("navera_lite.homography_net")
    (cls,) = need(hn, "HomographyNet")
    net = go(cls)
    keys = sorted(str(k) for k in net.state_dict().keys())
    want = sorted(f"{n}.{p}" for n in ("conv1", "conv2", "conv3", "conv4", "fc1", "fc2") for p in ("weight", "bias"))
    c.ok(keys == want, f"HomographyNet's parameters are {keys}; the check and Sim Lite need exactly {want}")
    n = sum(int(p.numel()) for p in net.parameters())
    c.ok(n == 192600, f"HomographyNet has {n} parameters, the docstring 192 600 — check each layer's sizes")
    torch.manual_seed(25)
    ref = reference_net()
    fd, path = tempfile.mkstemp(suffix=".pt")
    os.close(fd)
    try:
        torch.save(ref.state_dict(), path)
        mine = go(hn.load_weights, path)
    finally:
        os.remove(path)
    probe = norm_input(np.random.default_rng(5).integers(0, 256, (4, 2, 64, 64)).astype(np.uint8))
    got = go(mine, hn.torch.as_tensor(probe.numpy()))
    got = arr(got.detach().cpu().numpy() if got is not None else None, "HomographyNet(x)", (4, 8))
    with torch.no_grad():
        want_o = ref(probe).numpy()
    c.ok(np.allclose(got, want_o, atol=1e-4), "with the same weights, your forward() gives other numbers than the "
         "table: four times conv → ReLU → 2 × 2 max-pooling, flatten, fc1, ReLU, fc2 (no ReLU after fc2)")


@c.test("TODO 10: offsets_to_H() on unseen offsets and another patch size",
        hint="Lesson §6: getPerspectiveTransform(square, square + offsets) with the square of side − 1 = 63 (or "
             "side − 1 for another side), both float32.")
def _():
    (f,) = functions("homography_net", "offsets_to_H")
    off = [3.0, -1.0, 1.5, 2.0, -2.0, 0.5, 4.0, -3.0]
    H = arr(go(f, off), "offsets_to_H", (3, 3))
    want = np.array([[0.963312, 0.020837, 3.0], [0.04722, 1.042706, -1.0], [-0.0002, 0.001241, 1.0]])
    if not np.allclose(H / H[2, 2], want, atol=1e-4):
        inv = np.linalg.inv(want)
        if np.allclose(H / H[2, 2], inv / inv[2, 2], atol=1e-4):
            raise CheckFailed("offsets_to_H gives the INVERSE: it must send the square's corners to corners + offsets")
        raise CheckFailed("offsets_to_H gives another H: the square's corners are (0, 0), (side − 1, 0), "
                          "(side − 1, side − 1), (0, side − 1), in that order")
    H2 = arr(go(f, off, side=32), "offsets_to_H(…, side=32)", (3, 3))
    want2 = np.array([[0.91211, 0.054803, 3.0], [0.094343, 1.0933, -1.0], [-0.001215, 0.005636, 1.0]])
    c.ok(np.allclose(H2 / H2[2, 2], want2, atol=1e-4), "offsets_to_H(…, side=32): use the `side` argument")


@c.test("TODO 11: train() — one row per epoch, it learns, it uses lr, the validation loss is measured at the end",
        hint="Lab Step 11 and its hints: Adam(model.parameters(), lr); per epoch a new seeded torch.randperm; each batch "
             "through to_input(…, device), targets / RHO_PX, mse_loss, zero_grad → backward → step; then model.eval() "
             "and torch.no_grad() for the validation loss; one dict per epoch.")
def _():
    import torch
    hn = module("navera_lite.homography_net")
    (f,) = functions("homography_net", "train")
    d = np.load(io.BytesIO(hidden("test_pairs.npz", text=False)))
    tx, ty = d["x"][:96], d["y"][:96]
    vx, vy = d["x"][96:160], d["y"][96:160]
    T = lambda a: hn.torch.as_tensor(a)                                         # tensors made in YOUR process  # noqa: E731

    def weights(m):
        sd = m.state_dict()
        return {str(k): np.asarray(sd[k].detach().cpu().numpy()) for k in sd.keys()}

    hn.torch.manual_seed(5)
    net = go(hn.HomographyNet)
    before = weights(net)
    hist = go(f, net, T(tx), T(ty), T(vx), T(vy), epochs=0, lr=1e-3, batch=32, seed=1, device="cpu")
    if not isinstance(hist, list):
        raise CheckFailed(f"train() must return a list (the history), got {type(hist).__name__}")
    c.ok(len(hist) == 0, f"with epochs = 0 the history must be empty, got {len(hist)} rows — use the epochs argument")
    hist = go(f, net, T(tx), T(ty), T(vx), T(vy), epochs=2, lr=0.0, batch=32, seed=1, device="cpu", seconds=120)
    now = weights(net)
    c.ok(all(np.allclose(before[k], now[k]) for k in before), "with lr = 0 the weights still changed: give lr to the "
         "optimiser (torch.optim.Adam(model.parameters(), lr=lr))")
    rows = []
    hist = go(f, net, T(tx), T(ty), T(vx), T(vy), epochs=3, lr=5e-3, batch=16, seed=1, device="cpu",
              log=rows.append, seconds=120)
    if not isinstance(hist, list) or len(hist) != 3:
        raise CheckFailed(f"with epochs = 3 the history must have 3 rows, got {hist!r:.200}")
    for i, row in enumerate(hist):
        if not isinstance(row, dict) or not {"epoch", "train_loss", "val_loss"} <= set(row):
            raise CheckFailed(f"row {i} of the history must be a dict with epoch, train_loss, val_loss: got {row!r:.120}")
        for k in ("train_loss", "val_loss"):
            if isinstance(row[k], bool) or not isinstance(row[k], (int, float)):
                raise CheckFailed(f"history[{i}][{k!r}] must be a float (loss.item()), got {type(row[k]).__name__}")
    c.ok([int(r["epoch"]) for r in hist] == [1, 2, 3], f"the epochs must be numbered 1, 2, 3, got {[r['epoch'] for r in hist]}")
    c.ok(len(rows) == 3, f"log(row) must be called once per epoch (it was called {len(rows)} times)")
    after = weights(net)
    c.ok(not all(np.allclose(before[k], after[k]) for k in before), "after 3 epochs with lr = 0.005 the model has not "
         "changed: opt.zero_grad(), loss.backward(), opt.step() in every batch")
    if hist[0]["train_loss"] > 1.0:
        raise CheckFailed(f"the first training loss is {hist[0]['train_loss']:.2f}, far above ≈ 0.2: divide the targets by "
                          "RHO_PX (the network predicts offsets / 16)")
    ref = reference_net()
    ref.load_state_dict({k: torch.as_tensor(v) for k, v in after.items()})
    ref.eval()
    with torch.no_grad():
        want = float(np.mean([torch.nn.functional.mse_loss(ref(norm_input(vx[s:s + 16])),
                                                            torch.as_tensor(vy[s:s + 16]) / 16.0).item()
                              for s in range(0, len(vx), 16)]))
    c.ok(abs(hist[-1]["val_loss"] - want) < 5e-4, f"the last val_loss is {hist[-1]['val_loss']:.4f}, but the validation "
         f"pairs give {want:.4f} with the trained model: measure it AFTER the epoch's batches, in model.eval() and "
         "torch.no_grad(), with targets / RHO_PX, in batches of `batch`, averaged")


TEST_PRIOR, TEST_NCC, TEST_REF, NEED = 9.549, 16.532, 3.419, 6.5


def load_weights_strict(path):
    import torch
    if not os.path.exists(path):
        raise CheckFailed(f"{path} is missing: run `python3 run_night.py train` (Step 11)")
    if os.path.getsize(path) > 10_000_000:
        raise CheckFailed(f"{path} is larger than 10 MB: it should hold HomographyNet's weights only (about 0.8 MB)")
    try:
        sd = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"{path} cannot be read as weights ({type(e).__name__}): save it with "
                          "torch.save(model.state_dict(), path) — the runner does")
    net = reference_net()
    try:
        net.load_state_dict(sd)                                             # strict: every layer must load
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"{path} does not fit HomographyNet's layers: {str(e).splitlines()[0][:200]}")
    return net


@c.test("Your trained network: my_homography.pt on 512 unseen night pairs from places you never saw",
        hint="Lab Step 11: `python3 run_night.py train` saves my_homography.pt (on the CPU: --device cpu --n-train 3000 "
             "--epochs 6). Do not save overfit.pt or quick.pt as my_homography.pt.")
def _():
    import torch
    torch.set_num_threads(2)
    net = load_weights_strict("my_homography.pt")
    d = np.load(io.BytesIO(hidden("test_pairs.npz", text=False)))
    e = float(np.median(centre_err(predict_ref(net, d["x"]), d["y"])))
    print(f"  your network on the hidden night pairs: median centre error {e:.2f} px "
          f"(prior alone {TEST_PRIOR:.2f}, NCC {TEST_NCC:.2f}, a full GPU training ≈ {TEST_REF:.1f})")
    c.ok(e <= NEED, f"my_homography.pt: median centre error {e:.2f} px on the hidden night pairs; it needs {NEED} or less "
         f"(the prior alone: {TEST_PRIOR:.2f}). Train on all the places (not overfit.pt), or check `python3 run_night.py compare`.")


@c.test("Steps 8–12: corners, input, parameters, training and overfitting",
        hint="N_PARAMS_FC1 = outputs × (inputs + 1); VAL_CENTRE_PX from the last line of `train`; explain in your own "
             "words (lesson §6–§8).")
def _():
    (wc, wn, pp, n1, vc, po, wo) = answers("EXPLAIN_CORNERS", "EXPLAIN_NORM", "PREDICT_PARAMS", "N_PARAMS_FC1",
                                           "VAL_CENTRE_PX", "PREDICT_OVERFIT", "EXPLAIN_OVERFIT")
    explained("EXPLAIN_CORNERS", wc,
              ((r"corner", r"offset", r"where", r"4 point", r"four point"), "what the 8 numbers are"),
              ((r"scale", r"size", r"pixel", r"balanc", r"different", r"same unit", r"bounded", r"range", r"perspective",
                r"9 entr", r"nine"), "why corners rather than H's entries"))
    explained("EXPLAIN_NORM", wn,
              ((r"gain", r"agc", r"offset", r"bright", r"contrast", r"absolute", r"mean", r"pale", r"level"),
               "why each channel on its own"),
              ((r"uniform", r"sea", r"flat", r"noise", r"zero", r"divid", r"small std", r"blow"),
               "what the + 1 protects"))
    predicted("PREDICT_PARAMS", pp)
    n1 = number(n1, "N_PARAMS_FC1")
    if int(n1) == 131072:
        raise CheckFailed("N_PARAMS_FC1 = 131 072: the 128 biases count too")
    c.eq(int(n1), 131200, "N_PARAMS_FC1")
    vc = number(vc, "VAL_CENTRE_PX")
    c.ok(1.0 <= vc <= 7.5, f"VAL_CENTRE_PX = {vc}: the median centre error printed at the end of the full training")
    predicted("PREDICT_OVERFIT", po)
    explained("EXPLAIN_OVERFIT", wo,
              ((r"train",), "what the training loss did"),
              ((r"valid", r"val\b", r"val loss", r"other place", r"unseen", r"new place"), "what the validation loss did"),
              ((r"memor", r"by heart", r"overfit", r"few", r"6 place", r"six", r"not general", r"specific", r"variety"),
               "why"))


CMP_NCC_NIGHT = 14.46


@c.test("Steps 13–15: learned vs NCC, sabotage, the night flight",
        hint="Copy the numbers of `compare` (one decimal), `sabotage` and `fly`; explain in your own words.")
def _():
    (nn_, nc, nno, wl, ps, mk, ws, fm) = answers("NET_NIGHT_PX", "NCC_NIGHT_PX", "NET_NOON_PX", "EXPLAIN_LEARNED",
                                                 "PREDICT_STRICT", "MISSING_KEYS", "EXPLAIN_STRICT", "FLY_MEDIAN_M")
    nn_, nc, nno = (number(v, n) for v, n in ((nn_, "NET_NIGHT_PX"), (nc, "NCC_NIGHT_PX"), (nno, "NET_NOON_PX")))
    c.near(nc, CMP_NCC_NIGHT, 0.3, "NCC_NIGHT_PX")
    if os.path.exists("my_homography.pt"):
        try:
            net = load_weights_strict("my_homography.pt")
            d = np.load(io.BytesIO(hidden("compare_pairs.npz", text=False)))
            mine_n = float(np.median(centre_err(predict_ref(net, d["night_x"]), d["night_y"])))
            mine_d = float(np.median(centre_err(predict_ref(net, d["noon_x"]), d["noon_y"])))
        except CheckFailed:
            mine_n = mine_d = None
        if mine_n is not None:
            c.ok(abs(nn_ - mine_n) <= 0.3, f"NET_NIGHT_PX = {nn_}, but your my_homography.pt gives {mine_n:.1f} px at "
                 "night: run `compare` again after your last training and copy its line")
            c.ok(abs(nno - mine_d) <= 0.3, f"NET_NOON_PX = {nno}, but your my_homography.pt gives {mine_d:.1f} px at "
                 "noon: copy the noon line of `compare`")
    explained("EXPLAIN_LEARNED", wl,
              ((r"train", r"learn", r"night", r"saw", r"seen", r"distribution", r"data"), "why it wins at night only"),
              ((r"real", r"thermal camera", r"flight", r"test", r"measure", r"season", r"weather", r"truth", r"frames"),
               "what you would need before trusting it"))
    predicted("PREDICT_STRICT", ps)
    c.eq(int(number(mk, "MISSING_KEYS")), 12, "MISSING_KEYS")
    explained("EXPLAIN_STRICT", ws,
              ((r"random", r"silent", r"no error", r"without", r"ignore", r"nothing", r"untrained", r"initial"),
               "what strict=False does"),
              ((r"refus", r"start", r"strict", r"check", r"error", r"fail", r"load", r"loc-6", r"loc 6"),
               "what NAVERA changed"))
    fm = number(fm, "FLY_MEDIAN_M")
    c.ok(3.0 <= fm <= 80.0, f"FLY_MEDIAN_M = {fm}: the last line of `python3 run_night.py fly` (metres)")


@c.test("report.md: four headings, your own words, your numbers",
        hint="Lab Step 16: keep the four ## headings, 200–500 words, replace every TODO, quote AUDIT_BEST_NCC, "
             "MIN_ALT_FIRST_0, NCC_GOOD_NIGHT and NET_NIGHT_PX as numbers.")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## 1. The data auditor", "## 2. Geometry and NCC", "## 3. The learned homography", "## 4. Limits and honesty"):
        c.ok(h in text, f"report.md lost its heading “{h}”")
    c.ok("TODO" not in text, "report.md still contains a TODO")
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    n = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body))
    c.ok(200 <= n <= 560, f"report.md has {n} words; write 200–500")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    has = lambda target, tol: any(abs(x - target) <= tol or abs(x - 100 * target) <= 100 * tol for x in nums)  # noqa: E731
    vals = answers("AUDIT_BEST_NCC", "MIN_ALT_FIRST_0", "NCC_GOOD_NIGHT", "NET_NIGHT_PX")
    for v, name in zip(vals, ("AUDIT_BEST_NCC", "MIN_ALT_FIRST_0", "NCC_GOOD_NIGHT", "NET_NIGHT_PX")):
        v = number(v, name)
        tol = 0.006 if v < 1 else 0.06 if v < 20 else 0.6
        c.ok(has(v, tol), f"report.md does not quote your {name} ({v:g})")


c.milestone("night-navigator", "TODO", "Step", "Your trained", "report", label="Night navigator")

c.run()
