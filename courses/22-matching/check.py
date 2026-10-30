import contextlib
import io
import json
import os
import re

import numpy as np

from academy_check import (CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run)

c = Checker()
DATA = "/data/academy/22-matching"
REF = "ref_desc.pt"                     # the course's network, shipped in the lesson folder


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
        if "larger sample than population" in msg:
            msg += " — with fewer pairs than a sample needs, return (None, all False) before drawing"
        if "SVD did not converge" in msg:
            msg += " — the system has NaN or inf values"
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


def warp(H, pts):
    p = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    q = np.column_stack([p, np.ones(len(p))]) @ np.asarray(H, dtype=np.float64).T
    return q[:, :2] / q[:, 2:3]


def sim_matrix(s, t, tx, ty):
    a, b = s * np.cos(np.radians(t)), s * np.sin(np.radians(t))
    return np.array([[a, -b, tx], [b, a, ty], [0, 0, 1.0]])


def torch_threads():
    try:
        import torch
        torch.set_num_threads(2)
    except Exception:                                                        # noqa: BLE001
        pass


# ================================================================== session 1 — Geometer (unseen inputs)
D1 = np.array([[3.18, 2.75, 1.5, 4.53, 9.72], [5.91, 3.19, 4.63, 9.06, 6.49], [6.83, 4.21, 9.79, 7.76, 6.82],
               [4.0, 4.0, 6.0, 7.0, 9.0], [3.32, 1.31, 1.59, 1.33, 5.58], [2.0, 9.0, 2.6, 8.0, 9.0],
               [5.6, 9.26, 5.68, 9.32, 7.96]])


def pairs_of(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None")
    a = np.asarray(v)
    if a.size == 0:
        return []
    if a.ndim != 2 or a.shape[1] != 2:
        raise CheckFailed(f"{what} must return an array of shape (K, 2) of pairs (i, j), got shape {a.shape}")
    return [[int(i), int(j)] for i, j in a]


@c.test("TODO 1: ratio_test() on an unseen distance matrix, three ratios, ties and a single column",
        hint="Lesson §1: per row, the nearest column j and the two smallest distances; keep (i, j) when "
             "best < ratio × second (strictly). Fewer than 2 columns: an empty (0, 2) array.")
def _():
    (f,) = functions("match", "ratio_test")
    got = pairs_of(go(f, D1, 0.8), "ratio_test(D, 0.8)")
    if got == [[0, 2], [1, 1], [2, 1], [4, 1], [5, 0], [6, 0]]:
        raise CheckFailed("ratio_test(D, 0.8) keeps every row without a tie: did you compare with ratio × the SECOND "
                          "smallest distance (not the largest, not the mean)?")
    if [p[0] for p in got] == [0, 1, 2, 5] and got != [[0, 2], [1, 1], [2, 1], [5, 0]]:
        raise CheckFailed(f"the right rows are kept but with the wrong columns {got}: j is the column of the NEAREST "
                          "distance (np.argmin / argsort[0])")
    c.ok(got == [[0, 2], [1, 1], [2, 1], [5, 0]], f"ratio_test on an unseen 7 × 5 matrix, ratio 0.8: {got} — not the "
         "expected pairs")
    c.ok(pairs_of(go(f, D1, 0.6), "ratio_test(D, 0.6)") == [[0, 2]], "with ratio = 0.6 the result is wrong: use the "
         "ratio argument")
    g = pairs_of(go(f, D1, 1.0), "ratio_test(D, 1.0)")
    if [3, 0] in g or [3, 1] in g:
        raise CheckFailed("row 3 has a tie (4.0 and 4.0): with best < ratio × second STRICTLY, even ratio 1.0 drops it")
    c.ok(g == [[0, 2], [1, 1], [2, 1], [4, 1], [5, 0], [6, 0]], f"ratio 1.0 gives {g}: expected other pairs")
    for D, why in ((np.array([[1.0], [2.0]]), "a single column"), (np.array([[4.0, 4.0, 9.0]]), "one row with a tie")):
        v = go(f, D, 1.0)
        c.ok(v is not None and np.asarray(v).shape == (0, 2), f"with {why} nothing is kept: the result must still have "
             f"shape (0, 2), got {np.asarray(v).shape if v is not None else None} — np.array([]) has shape (0,); "
             "use np.zeros((0, 2), dtype=int) (lab Step 1, hint 3)")


SRC2 = [[20.898, 191.276], [52.429, 113.261], [149.458, 3.721], [121.742, 76.374], [21.931, 78.509], [66.338, 133.991],
        [186.599, 122.802], [171.846, 174.505], [60.692, 138.037]]
DST2 = [[283.785, 82.503], [211.105, -6.643], [142.107, -193.855], [210.836, -115.819], [149.203, 9.643],
        [245.28, -10.0], [308.518, -163.049], [362.105, -111.712], [245.438, -0.32]]
FIT2 = (1.3715803, -61.8912531, 39.8606546, -16.1974924)


@c.test("TODO 2: fit_similarity() on 9 unseen noisy pairs — least squares, degrees, the course's sign of θ",
        hint="Lesson §2: unknowns a = s·cos θ, b = s·sin θ, tx, ty; two rows per pair, np.linalg.lstsq; then "
             "s = hypot(a, b), θ = degrees(atan2(b, a)). Fewer than 2 pairs or one repeated point: ValueError.")
def _():
    (f,) = functions("match", "fit_similarity")
    v = go(f, SRC2, DST2)
    try:
        s, t, tx, ty = (float(x) for x in v)
    except (TypeError, ValueError):
        raise CheckFailed(f"fit_similarity must return four numbers (s, theta_deg, tx, ty), got {v!r:.80}")
    if abs(t - 61.891) < 0.01:
        raise CheckFailed("θ has the wrong sign: the model is x2 = s(cos θ x1 − sin θ y1) + tx, y2 = s(sin θ x1 + "
                          "cos θ y1) + ty (lesson §2)")
    if abs(t - np.radians(FIT2[1])) < 1e-3:
        raise CheckFailed("θ is in radians: return degrees (math.degrees)")
    if abs(s - 1.37) < 0.02 and abs(t - FIT2[1]) < 1.0 and not np.allclose([s, t, tx, ty], FIT2, atol=1e-4):
        raise CheckFailed(f"close to the truth but not the least-squares fit of ALL 9 pairs: ({s:.5f}, {t:.4f}, {tx:.4f}, "
                          f"{ty:.4f}) — use every pair, not two of them")
    c.ok(np.allclose([s, t, tx, ty], FIT2, atol=1e-4), f"fit_similarity on 9 unseen noisy pairs = ({s:.4f}, {t:.3f}, "
         f"{tx:.3f}, {ty:.3f}): not the least-squares similarity")
    for bad, why in ((([[1.0, 2.0]], [[3.0, 4.0]]), "a single pair"), (([[5.0, 5.0], [5.0, 5.0]], [[1.0, 1.0], [2.0, 2.0]]),
                                                                       "two copies of the same point")):
        try:
            run(f, *bad)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise CheckFailed(f"with {why}, fit_similarity must raise ValueError (got: {str(e)[:120]})")
        raise CheckFailed(f"with {why}, fit_similarity must raise ValueError (nothing can be measured), it returned a value")


S4 = [[10.0, 20.0], [300.0, 40.0], [280.0, 260.0], [30.0, 240.0]]
D4 = [[45.0, 29.0], [356.115108, 16.18705], [382.075472, 205.660377], [105.809129, 233.40249]]
H4 = np.array([[1.2, 0.15, 30.0], [-0.1, 0.9, 12.0], [4e-4, -2e-4, 1.0]])
SN = [[1265.86, 1142.4], [1102.52, 1517.45], [1275.88, 1342.97], [1040.13, 1250.37], [1029.03, 1217.46],
      [1227.83, 1424.33], [1405.34, 1120.37], [1118.54, 1266.4], [1177.52, 1338.57], [1115.68, 1457.75],
      [1441.38, 1113.05], [1374.21, 1108.58], [1025.25, 1186.52], [1324.46, 1416.58], [1055.26, 1228.28],
      [1250.16, 1050.5], [1342.56, 1422.24], [1557.89, 1570.04], [1144.46, 1169.34], [1050.12, 1586.89]]
DN = [[1346.84, 714.51], [1388.78, 1113.37], [1420.2, 880.58], [1257.66, 885.13], [1239.79, 860.84], [1424.12, 968.98],
      [1407.78, 657.49], [1308.59, 868.98], [1366.73, 913.47], [1375.25, 1048.83], [1423.88, 640.72], [1390.04, 656.95],
      [1226.29, 832.36], [1471.98, 926.32], [1258.3, 861.2], [1308.16, 644.39], [1482.21, 924.88], [1631.44, 969.86],
      [1291.35, 775.82], [1385.6, 1209.47]]
HN = np.array([[1.1964622266, 0.1655186007, 21.6711422325], [-0.1055506957, 0.9128198322, 6.1803199584],
               [0.0003940450632, -0.0001905610732, 1.0]])
GRID = [[x, y] for x in (1000, 1300, 1600) for y in (1050, 1300, 1600)]


@c.test("TODO 3: dlt_homography() — exact on 4 unseen pairs, normalised on 20 noisy pairs with large coordinates",
        hint="Lesson §3: normalise both point sets (normalise_points), two rows of A per pair, h = the last row of "
             "np.linalg.svd(A)[2], reshape(3, 3), undo the normalisations (inv(T2) @ Hn @ T1), divide by H[2, 2].")
def _():
    (f,) = functions("match", "dlt_homography")
    H = arr(go(f, S4, D4), "dlt_homography(4 pairs)", (3, 3))
    if abs(H[2, 2] - 1.0) > 1e-6:
        raise CheckFailed(f"H[2, 2] = {H[2, 2]:.4g}: divide H by H[2, 2] at the end")
    if np.allclose(H, H4.T, atol=1e-4):
        raise CheckFailed("H is transposed: reshape the 9 numbers row by row (h.reshape(3, 3))")
    c.ok(np.allclose(H, H4, atol=1e-5), "4 unseen pairs of a known homography: your H is not that homography — check "
         "the two rows of A (lesson §3's worked example)")
    H = arr(go(f, SN, DN), "dlt_homography(20 pairs)", (3, 3))
    d = np.hypot(*(warp(H, GRID) - warp(HN, GRID)).T).max()
    c.ok(d < 0.05, f"20 noisy pairs with coordinates near 1 000–1 600 px: your H maps a grid of points up to {d:.2f} px "
         "away from the normalised DLT's. Without Hartley's normalisation the system is badly scaled (lesson §3): "
         "use normalise_points on src and dst, and undo it at the end")
    try:
        run(f, S4[:3], D4[:3])
    except CheckFailed as e:
        if "ValueError" in str(e):
            return
        raise CheckFailed(f"with 3 pairs, dlt_homography must raise ValueError (got: {str(e)[:120]})")
    raise CheckFailed("with 3 pairs, dlt_homography must raise ValueError: 8 unknowns need at least 4 pairs")


@c.test("TODO 4: ransac_iterations() on unseen p, w, s — rounded up, w = 1, w = 0",
        hint="Lesson §4: N = log(1 − p) / log(1 − w^s), rounded UP (math.ceil), returned as an int; w = 1 → 1; w ≤ 0 or "
             "w > 1 → ValueError.")
def _():
    (f,) = functions("match", "ransac_iterations")
    for args, want in (((0.95, 0.4, 2), 18), ((0.999, 0.6, 4), 50), ((0.9, 0.25, 3), 147), ((0.99, 0.7, 1), 4)):
        v = go(f, *args)
        if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
            raise CheckFailed(f"ransac_iterations{args} must return an int, got {v!r} ({type(v).__name__})")
        if int(v) == want - 1:
            raise CheckFailed(f"ransac_iterations{args} = {v}: round UP (math.ceil): a fraction of a sample is a whole one")
        c.eq(int(v), want, f"ransac_iterations{args}")
    c.eq(int(go(f, 0.99, 1.0, 2)), 1, "ransac_iterations(0.99, 1.0, 2)")
    try:
        run(f, 0.99, 0.0, 2)
    except CheckFailed as e:
        if "ValueError" in str(e):
            return
        raise CheckFailed(f"with w = 0, ransac_iterations must raise ValueError (got: {str(e)[:120]})")
    raise CheckFailed("with w = 0, ransac_iterations must raise ValueError: no number of samples is enough")


RS = [[250.86, 228.4], [107.31, 63.71], [28.41, 60.38], [195.47, 196.06], [20.79, 171.76], [164.19, 17.38],
      [33.85, 114.67], [227.66, 158.92], [16.63, 106.39], [268.05, 33.18], [290.1, 23.96], [65.82, 232.32],
      [281.52, 192.77], [107.88, 298.8], [27.88, 48.08], [125.93, 265.0], [182.65, 17.62], [27.38, 130.97],
      [99.05, 152.75], [274.85, 87.78], [83.09, 187.34], [36.31, 151.19], [54.81, 244.9], [220.85, 256.74],
      [37.97, 226.23], [7.16, 90.75], [144.64, 234.2], [179.28, 194.79], [45.57, 112.61], [297.31, 178.22]]
RD = [[-8.92, 162.42], [162.28, 128.74], [350.05, 480.03], [35.89, 137.05], [113.97, 361.27], [171.57, 187.11],
      [157.16, 57.6], [108.65, 91.46], [-2.5, 39.01], [120.16, 252.82], [118.84, 271.29], [403.67, 310.18],
      [4.74, 197.3], [448.63, 236.15], [205.37, 79.34], [17.01, 61.9], [114.63, 17.22], [162.16, 98.74], [104.46, 87.96],
      [59.07, 377.31], [87.72, 62.38], [131.06, 44.35], [90.52, 84.74], [388.12, 448.38], [106.3, -16.33],
      [185.08, 48.05], [29.76, 86.72], [42.75, 126.79], [153.82, 65.56], [8.28, 214.57]]
R_OUT = [2, 4, 7, 8, 11, 13, 16, 17, 19, 22, 23, 24]
R_FIT = (0.7999055572, 119.8926980416, 250.1036074078, 79.6395654045)
R_SEED31 = [0, 3, 12, 15, 18, 20, 26, 27, 29]
HS = [[240.04, 345.04], [41.1, 199.14], [383.46, 261.32], [38.74, 357.11], [40.58, 215.33], [3.89, 310.37],
      [351.76, 125.54], [11.21, 276.78], [284.69, 164.07], [375.6, 390.74], [68.81, 179.43], [367.4, 192.87],
      [93.96, 240.09], [48.56, 285.37], [2.12, 319.65], [53.41, 176.58], [388.89, 355.8], [57.81, 150.77],
      [289.15, 352.21], [194.4, 296.14], [355.42, 263.04], [195.06, 124.18], [5.91, 324.15], [179.18, 59.45],
      [350.22, 298.44]]
HD = [[284.48, 309.98], [111.67, 211.04], [375.28, 205.82], [134.85, 366.91], [241.19, 371.09], [99.89, 329.59],
      [338.01, 83.74], [211.44, 176.77], [12.09, 118.91], [203.06, 384.02], [187.59, 498.42], [26.67, 126.95],
      [159.96, 241.31], [131.65, 295.51], [98.91, 339.33], [116.98, 185.93], [388.36, 289.36], [270.9, 481.38],
      [288.92, 79.04], [207.25, 225.02], [356.37, 212.62], [221.87, 108.41], [103.07, 343.2], [199.54, 46.09],
      [356.04, 245.21]]
H_IN = [0, 1, 2, 3, 5, 6, 12, 13, 14, 15, 16, 20, 21, 22, 23, 24]
H_FIT = np.array([[0.8914474953, 0.1945913559, 41.1270458548], [-0.151493034, 1.0922652024, 10.5482668525],
                  [0.0002841471050, 0.0001837785344, 1.0]])


def mask_of(v, n, what):
    if not (isinstance(v, tuple) and len(v) == 2):
        raise CheckFailed(f"{what} must return two things (M, inliers), got {type(v).__name__}")
    M, inl = v
    a = np.asarray(inl)
    if a.shape != (n,):
        raise CheckFailed(f"{what}: inliers must be an array of {n} booleans (one per pair), got shape {a.shape}")
    if a.dtype != bool:
        raise CheckFailed(f"{what}: inliers must be booleans (dtype bool), got {a.dtype}")
    return M, a


@c.test("TODO 5: ransac() on unseen pairs (40 % wrong) — similarity and homography, refit, iters, degenerate input",
        hint="Lesson §4 and the docstring's rules: rng.choice(len(src), s, replace=False) once per iteration, "
             "fit_model, inliers = distance ≤ thr_px with warp_points, keep the most inliers, refit on them at the end.")
def _():
    (f,) = functions("match", "ransac")
    n = len(RS)
    M, inl = mask_of(go(f, RS, RD, "similarity", 3.0, 200, np.random.default_rng(7)), n, "ransac(similarity)")
    if M is None:
        raise CheckFailed("ransac returned M = None on 30 pairs of which 18 are right")
    out = sorted(int(i) for i in np.nonzero(~inl)[0])
    if len(out) > len(R_OUT) and all(k in out for k in R_OUT):
        raise CheckFailed(f"{len(out)} pairs called outliers, expected 12: is the inlier test ≤ thr_px (3 px here) on "
                          "the distance between warp_points(M, src) and dst?")
    c.ok(out == R_OUT, f"similarity: your outliers are {out}, not the 12 wrong pairs of this unseen set")
    want = sim_matrix(*R_FIT)
    M = arr(M, "ransac M", (3, 3))
    if not np.allclose(M, want, atol=1e-4):
        raise CheckFailed("the inliers are right but M is not the fit on ALL of them: refit with fit_model on the best "
                          "sample's inliers at the end")
    _, inl1 = mask_of(go(f, RS, RD, "similarity", 3.0, 1, np.random.default_rng(31)), n, "ransac(iters=1)")
    got1 = sorted(int(i) for i in np.nonzero(inl1)[0])
    if got1 == sorted(set(range(n)) - set(R_OUT)):
        raise CheckFailed("with iters = 1 you still found the best model: use the iters argument (one sample per iteration)")
    c.ok(got1 == R_SEED31, f"with iters = 1 and rng = np.random.default_rng(31) the inliers are {got1}: the sample must be "
         "drawn exactly as the docstring says, rng.choice(len(src), s, replace=False), first thing in the iteration")
    M, inl = mask_of(go(f, HS, HD, "homography", 3.0, 300, np.random.default_rng(2)), len(HS), "ransac(homography)")
    c.ok(M is not None and sorted(int(i) for i in np.nonzero(inl)[0]) == H_IN, "homography: the inliers are not the 16 "
         "right pairs of this unseen set — kind 'homography' takes samples of 4 (MIN_SAMPLE) and fits with fit_model")
    c.ok(np.hypot(*(warp(arr(M, "M", (3, 3)), HS) - warp(H_FIT, HS)).T).max() < 0.01,
         "homography: M is not the refit on all the inliers")
    M, inl = mask_of(go(f, [[5.0, 5.0]] * 6, [[1.0, 1.0], [2, 2], [3, 3], [4, 4], [5, 5], [6, 6]], "similarity", 3.0,
                        20, np.random.default_rng(0)), 6, "ransac(all src points identical)")
    c.ok(M is None and not inl.any(), "when no sample can give a model (all src points identical), return (None, all False)")
    M, inl = mask_of(go(f, [[1.0, 2.0]], [[3.0, 4.0]], "similarity", 3.0, 20, np.random.default_rng(0)), 1,
                     "ransac(1 pair)")
    c.ok(M is None and not inl.any(), "with fewer pairs than a sample needs, return (None, all False)")


@c.test("TODO 6: gates() — unseen cases, the order of the gates, and the tolerance arguments",
        hint="Lesson §5 and the docstring: no fit → too few inliers → scale off → inliers bunched → ok, in that order; "
             "spread(…, grid=(4, 2), min_per_cell=3); use min_inliers, scale_tol and min_spread.")
def _():
    (f,) = functions("match", "gates")
    rng = np.random.default_rng(12)
    wide = np.column_stack([rng.uniform(0, 800, 60), rng.uniform(0, 600, 60)])
    left = np.column_stack([rng.uniform(0, 150, 60), rng.uniform(0, 280, 60)])
    cases = [
        ((None, wide[:2], (600, 800), 2.0), {}, (False, "no fit"), "fit None (even with few points: the first gate)"),
        (((3.0, 10.0, 0, 0), wide[:4], (600, 800), 2.0), {}, (False, "too few inliers"), "4 inliers and a wrong scale"),
        (((2.29, 10.0, 0, 0), wide, (600, 800), 2.0), {}, (True, "ok"), "scale 2.29 for 2.0 (14.5 % off)"),
        (((2.31, 10.0, 0, 0), wide, (600, 800), 2.0), {}, (False, "scale off"), "scale 2.31 for 2.0 (15.5 % off)"),
        (((1.68, 10.0, 0, 0), wide, (600, 800), 2.0), {}, (False, "scale off"), "scale 1.68 for 2.0"),
        (((2.0, 10.0, 0, 0), left, (600, 800), 2.0), {}, (False, "inliers bunched"), "60 inliers in one corner"),
        (((2.31, 10.0, 0, 0), left, (600, 800), 2.0), {}, (False, "scale off"), "a wrong scale AND bunched"),
        (((2.31, 10.0, 0, 0), wide, (600, 800), 2.0), {"scale_tol": 0.2}, (True, "ok"), "scale_tol = 0.2"),
        (((2.0, 10.0, 0, 0), wide[:8], (600, 800), 2.0), {"min_inliers": 10}, (False, "too few inliers"), "min_inliers = 10"),
        (((2.0, 10.0, 0, 0), left, (600, 800), 2.0), {"min_spread": 0.1}, (True, "ok"), "min_spread = 0.1"),
    ]
    for args, kw, want, what in cases:
        v = go(f, *args, **kw)
        if not (isinstance(v, tuple) and len(v) == 2):
            raise CheckFailed(f"gates() must return (bool, reason), got {v!r:.80}")
        got = (bool(v[0]), str(v[1]))
        c.ok(got == want, f"gates with {what}: {got}, expected {want}")


def near(v, want, tol, name):
    try:
        c.near(number(v, name), want, tol, name)
    except CheckFailed as e:
        raise CheckFailed(f"{e}. If you changed your code since you copied it, run the step again and copy the new "
                          "number")


@c.test("Steps 0–6: the numbers of the runs, the gates' verdicts, your explanations",
        hint="Copy the numbers from `ratio`, `fit`, `iters`, `ransac city_tilt` (the 500-sample rows) and `gates`, then "
             "explain in your own words.")
def _():
    (ph, pn, k8, p8, why_r, rs, rh, why_d, pi, i2, i4, es, eh, pg, rw, rhl, pw, why_g) = answers(
        "PREDICT_HARDEST", "PRECISION_NONE", "KEPT_08", "PRECISION_08", "EXPLAIN_RATIO", "RESID_SIM_TILT",
        "RESID_H_TILT", "EXPLAIN_DOF", "PREDICT_RANSAC_MIN", "ITERS_SIM_W02", "ITERS_H_W02", "CENTRE_ERR_SIM_TILT",
        "CENTRE_ERR_H_TILT", "PREDICT_GATES", "REASON_WRONG_PLACE", "REASON_HILLS", "PROTOTYPE_WRONG", "EXPLAIN_GATES")
    predicted("PREDICT_HARDEST", ph)
    if number(p8, "PRECISION_08") > 1 or number(pn, "PRECISION_NONE") > 1:
        raise CheckFailed("a precision is a share from 0 to 1 (write 0.935, not 93.5)")
    near(pn, 0.365, 0.002, "PRECISION_NONE")
    near(k8, 571, 1, "KEPT_08")
    near(p8, 0.935, 0.002, "PRECISION_08")
    explained("EXPLAIN_RATIO", why_r,
              ((r"second", r"next", r"runner", r"two neighbo", r"two nearest", r"other candidate"), "the second-nearest"),
              ((r"ambig", r"similar", r"alike", r"distinct", r"unique", r"confus", r"close to", r"repet", r"sure",
                r"doubt", r"clear"), "why a close second means a doubtful pair"))
    if abs(number(rs, "RESID_SIM_TILT") - 0.19) < 0.02 and abs(number(rh, "RESID_H_TILT") - 7.74) < 0.05:
        raise CheckFailed("RESID_SIM_TILT and RESID_H_TILT are swapped")
    near(rs, 7.74, 0.03, "RESID_SIM_TILT")
    near(rh, 0.19, 0.03, "RESID_H_TILT")
    explained("EXPLAIN_DOF", why_d,
              ((r"tilt", r"perspective", r"oblique", r"pitch", r"parallel", r"trapez", r"not flat", r"lean"),
               "what the tilt does that a similarity cannot model"),
              ((r"4 point", r"four point", r"8 ", r"eight", r"more sample", r"more iteration", r"more point", r"567",
                r"2876", r"2 876", r"degree", r"freedom", r"unknown", r"overfit", r"noise"), "what the homography costs"))
    predicted("PREDICT_RANSAC_MIN", pi)
    c.eq(int(number(i2, "ITERS_SIM_W02")), 113, "ITERS_SIM_W02")
    c.eq(int(number(i4, "ITERS_H_W02")), 2876, "ITERS_H_W02")
    if abs(number(es, "CENTRE_ERR_SIM_TILT") - 1.23) < 0.06:
        raise CheckFailed("CENTRE_ERR_SIM_TILT: take the 500-sample row of your similarity (the third row), not the first")
    near(es, 1.91, 0.06, "CENTRE_ERR_SIM_TILT")
    near(eh, 0.21, 0.06, "CENTRE_ERR_H_TILT")
    predicted("PREDICT_GATES", pg)
    for v, want, name in ((rw, "scale off", "REASON_WRONG_PLACE"), (rhl, "scale off", "REASON_HILLS")):
        c.ok(str(v).strip().lower().strip(".") == want, f"{name} = {v!r}: copy your gates' reason for that pair from "
             "`gates` (the exact words)")
    c.ok(str(pw).strip().lower().replace(" ", "_") in ("wrong_place", "wrong_place.jpg"), f"PROTOTYPE_WRONG = {pw!r}: "
         "which pair does the 'prototype' column accept although the photo shows another place?")
    explained("EXPLAIN_GATES", why_g,
              ((r"hill", r"altitude", r"height", r"right match", r"correct match", r"good match", r"refus", r"availab",
                r"lose", r"lost"), "what the scale gate costs (hills)"),
              ((r"wrong", r"false", r"another place", r"other place", r"dangerous", r"safe", r"never", r"1 ?097", r"trust"),
               "why a refused right match is better than an accepted wrong one"))


c.milestone("geometer", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "TODO 6:", "Steps 0–6:", label="Geometer")


# ================================================================== session 2 — Learned matcher
def hidden_img(name):
    import cv2
    return cv2.imdecode(np.frombuffer(hidden(name, text=False), np.uint8), cv2.IMREAD_GRAYSCALE)


def scenes():
    z = np.load(io.BytesIO(hidden("scenes.npz", text=False)))
    return {k: z[k] for k in z.files}, json.loads(hidden("scenes.json"))


def same_pairs(got, want_src, want_dst, what):
    if not (isinstance(got, tuple) and len(got) == 2):
        raise CheckFailed(f"{what} must return two arrays (src, dst), got {type(got).__name__}")
    src, dst = (arr(x, what) for x in got)
    src, dst = src.reshape(-1, 2), dst.reshape(-1, 2)
    if len(src) != len(dst):
        raise CheckFailed(f"{what}: src has {len(src)} points but dst {len(dst)}")
    ws, wd = np.asarray(want_src, float).reshape(-1, 2), np.asarray(want_dst, float).reshape(-1, 2)
    hit = 0
    for p, q in zip(src, dst):
        k = np.nonzero(np.hypot(*(ws - p).T) < 0.01)[0]
        hit += int(any(np.hypot(*(wd[i] - q)) < 0.05 for i in k))
    return src, dst, hit


@c.test("TODO 7: learned_pairs() on an unseen pair with the course's network — upright, describe, ratio, max_dist, "
        "back to the photo",
        hint="Lab Step 8: upright(photo, heading, zoom) → (img, valid, A); keypoints in the map and in img (valid=valid); "
             "describe the patches_at both; ratio_test on distance_matrix; the max_dist cut; dst = warp_points(inv(A), …).")
def _():
    torch_threads()
    lm = module("navera_lite.learned_match")
    ld = module("navera_lite.learned_desc")
    (f,) = functions("learned_match", "learned_pairs")
    if not os.path.exists(REF):
        raise CheckFailed("ref_desc.pt (the course's network, part of the lesson files) is missing in this folder: restore it (ask your teacher) — learned_pairs is tested with it")
    net = go(ld.load_weights, REF)
    exp = np.load(io.BytesIO(hidden("lp_expected.npz", text=False)))
    mg, pg = hidden_img("lp_map.png"), hidden_img("lp_photo.png")
    got = go(f, mg, pg, 75.0, 1.6, net, 0.8, None, seconds=120)
    src, dst, hit = same_pairs(got, exp["r80_src"], exp["r80_dst"], "learned_pairs")
    n = len(exp["r80_src"])
    if hit < 0.9 * n:
        H = exp["H"]
        if len(src):
            ok_up = np.hypot(*(warp(H, src) - dst).T) < 6
            if ok_up.mean() < 0.2:
                _, _, A = lm.upright(pg, 75.0, 1.6)
                back = warp(np.linalg.inv(np.asarray(A)), dst)
                if (np.hypot(*(warp(H, src) - back).T) < 6).mean() > 0.6:
                    raise CheckFailed("your dst points are still in the UPRIGHT picture's pixels: bring them back to the "
                                      "photo with warp_points(np.linalg.inv(A), …)")
        raise CheckFailed(f"on an unseen pair with the course's network (ratio 0.8) you return {len(src)} pairs, "
                          f"{hit} of them the expected ones (expected {n}). Lab Step 8 hints")
    if hit >= 0.9 * n and len(src) > n + max(2, n // 50):
        import cv2
        _, valid, A = go(lm.upright, pg, 75.0, 1.6)
        inside = cv2.erode((np.asarray(valid) > 0).astype(np.uint8), np.ones((49, 49), np.uint8))
        q = np.round(warp(np.asarray(A, float), dst)).astype(int)
        q[:, 0] = np.clip(q[:, 0], 0, inside.shape[1] - 1)
        q[:, 1] = np.clip(q[:, 1], 0, inside.shape[0] - 1)
        cut = int((inside[q[:, 1], q[:, 0]] == 0).sum())
        if cut >= 0.5 * (len(src) - n):
            raise CheckFailed(f"you return {len(src)} pairs where {n} are expected, {cut} of them with a patch that is "
                              "partly OUTSIDE the photo in the upright picture (half black): keypoints(up, valid=valid) "
                              "keeps only whole patches")
        raise CheckFailed(f"you return {len(src)} pairs where {n} are expected (the expected ones among them): keep only "
                          "the pairs YOUR ratio_test accepts with the given `ratio`")
    c.ok(len(src) <= n + max(2, n // 50), f"you return {len(src)} pairs where {n} are expected: pass `ratio` on to "
         "ratio_test, and find the upright picture's keypoints with keypoints(up, valid=valid)")
    got = go(f, mg, pg, 75.0, 1.6, net, 0.9, 0.6, seconds=120)
    src, dst, hit = same_pairs(got, exp["r90_d60_src"], exp["r90_d60_dst"], "learned_pairs(ratio 0.9, max_dist 0.6)")
    n = len(exp["r90_d60_src"])
    c.ok(hit >= 0.9 * n and len(src) <= n + max(2, n // 50), f"with ratio 0.9 and max_dist 0.6 you return {len(src)} "
         f"pairs, {hit} expected ones of {n}: is max_dist used (keep a pair only if its distance < max_dist)?")


@c.test("TODO 8: ratio_curve() on unseen numbers — kept, right, precision, strict test, nothing kept",
        hint="Lesson §7: for each t, kept = best < t × second; right = kept AND correct; precision = right / kept, or None "
             "when nothing is kept. One dict per t, in order.")
def _():
    (f,) = functions("learned_match", "ratio_curve")
    b = [0.2, 0.5, 0.45, 0.9, 0.3, 0.6, 0.7]
    s = [1.0, 0.6, 0.5, 1.0, 0.31, 1.2, 0.7]
    ok = [True, True, False, False, True, True, False]
    v = go(f, b, s, ok, [0.1, 0.5, 0.85, 0.95, 1.0])
    if not isinstance(v, list) or len(v) != 5 or not all(isinstance(r, dict) for r in v):
        raise CheckFailed(f"ratio_curve must return a list of 5 dicts (one per ratio), got {v!r:.120}")
    want = [(0.1, 0, 0, None), (0.5, 1, 1, 1.0), (0.85, 3, 3, 1.0), (0.95, 5, 3, 0.6), (1.0, 6, 4, 4 / 6)]
    for r, (t, k, rt, p) in zip(v, want):
        if not {"ratio", "kept", "right", "precision"} <= set(r):
            raise CheckFailed(f"each row needs the keys ratio, kept, right, precision: got {sorted(r)}")
        if (t == 1.0 and r["kept"] == 7) or (t == 0.5 and r["kept"] == 2):
            raise CheckFailed("ratio 1.0: 0.7 < 1.0 × 0.7 is False — the test is strict (<)")
        c.ok(abs(float(r["ratio"]) - t) < 1e-12 and int(r["kept"]) == k and int(r["right"]) == rt,
             f"ratio {t}: kept {r['kept']}, right {r['right']} — expected other counts")
        if p is None:
            c.ok(r["precision"] is None, f"ratio {t} keeps nothing: precision must be None (no division by 0), got "
                 f"{r['precision']!r}")
        else:
            c.ok(r["precision"] is not None and abs(float(r["precision"]) - p) < 1e-9, f"ratio {t}: precision "
                 f"{r['precision']!r}, expected right / kept")


def student_net():
    """The student's my_desc.pt, read safely (weights only) into the PatchNet the CHECK builds: it must load."""
    import torch
    import torch.nn as nn
    if not os.path.exists("my_desc.pt"):
        raise CheckFailed("my_desc.pt is missing in ~/lessons/22-matching: lab Step 7 (cp ../21-features/my_desc.pt .)")
    if os.path.getsize("my_desc.pt") > 5_000_000:
        raise CheckFailed("my_desc.pt is larger than 5 MB: it should hold PatchNet's weights only (about 360 kB)")
    try:
        sd = torch.load("my_desc.pt", map_location="cpu", weights_only=True)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"my_desc.pt cannot be read as weights ({type(e).__name__}): copy it again from mission 21")

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
            self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
            self.conv3 = nn.Conv2d(32, 64, 3, padding=1)
            self.fc = nn.Linear(1024, 64)
    try:
        Net().load_state_dict(sd)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"my_desc.pt does not fit PatchNet's layers: {str(e).splitlines()[0][:160]}")


def threshold():
    lr, md = answers("LEARNED_RATIO", "LEARNED_MAX_DIST")
    if lr is None:
        raise CheckFailed("LEARNED_RATIO is not decided yet (None): lab Step 9 — choose it from YOUR `curve` table")
    lr = number(lr, "LEARNED_RATIO")
    if not 0 < lr <= 1:
        raise CheckFailed(f"LEARNED_RATIO = {lr:g}: a ratio is more than 0 and at most 1")
    if md is not None:
        md = number(md, "LEARNED_MAX_DIST")
        if not 0 < md <= 2:
            raise CheckFailed(f"LEARNED_MAX_DIST = {md:g}: None, or a distance between unit vectors (more than 0, at most 2)")
    return lr, md


def heading_limit():
    (hl,) = answers("HEADING_LIMIT_DEG")
    if hl is None:
        raise CheckFailed("HEADING_LIMIT_DEG is not decided yet (None): lab Step 10 — choose it from YOUR `envelope` table A")
    hl = number(hl, "HEADING_LIMIT_DEG")
    if not 0 < hl <= 180:
        raise CheckFailed(f"HEADING_LIMIT_DEG = {hl:g}: a heading σ in degrees, more than 0 and at most 180")
    return hl


def decisions():
    lr, md = threshold()
    return {"learned_ratio": lr, "learned_max_dist": md, "heading_limit_deg": heading_limit()}


RULE_SCENES = ("h02", "h04", "h06", "h12", "h13", "h15", "h16")      # shaken or blurred, heading known (σ ≤ 8°)
P_MIN = 0.90
RIGHT_SHARE = 0.5            # of the right pairs YOUR network keeps with a loose ratio 0.95 on the same photos


@c.test("Step 9 — your DECISION, measured: your network's threshold on 7 unseen photos",
        hint="Lab Step 9: choose LEARNED_RATIO (and LEARNED_MAX_DIST, or None) from YOUR `curve` tables — all photos AND "
             "shaken photos: the share of right pairs among those kept must stay high (≥ 0.90 here), and you must keep at "
             "least half of the right pairs your network finds with a loose 0.95. Justify with numbers.")
def _():
    torch_threads()
    student_net()
    lr, md = threshold()
    why = answers("EXPLAIN_THRESHOLD")[0]
    explained("EXPLAIN_THRESHOLD", why,
              ((r"precision", r"right", r"wrong", r"correct", r"outlier", r"false"), "what the threshold trades"),
              ((r"\d",), "your numbers from the curve table"),
              ((r"sift", r"0\.8", r"lowe"), "how your choice compares with SIFT's 0.8"))
    ld = module("navera_lite.learned_desc")
    lm = module("navera_lite.learned_match")
    mt = module("navera_lite.match")
    net = go(ld.load_weights, "my_desc.pt")
    arrays, meta = scenes()
    right = kept = loose = 0
    for s in meta:
        if s["name"] not in RULE_SCENES:
            continue
        pr, H = s["prior"], np.array(s["H"])
        mg, pg = arrays["map_" + s["map"]], arrays[s["name"] + "_photo"]
        up, valid, A = go(lm.upright, pg, pr["heading_deg"], pr["zoom"])
        q1 = arr(go(lm.keypoints, mg), "keypoints").reshape(-1, 2)
        q2 = arr(go(lm.keypoints, up, valid=valid), "keypoints").reshape(-1, 2)
        d = arr(go(mt.distance_matrix, go(ld.describe, net, go(lm.patches_at, mg, q1), seconds=120),
                   go(ld.describe, net, go(lm.patches_at, up, q2), seconds=120)), "distances")
        if d.shape[0] == 0 or d.shape[1] < 2:
            continue
        o = np.argsort(d, axis=1, kind="stable")[:, :2]
        r = np.arange(len(d))
        b, s2 = d[r, o[:, 0]], d[r, o[:, 1]]
        ok = np.hypot(*(warp(H, q1) - warp(np.linalg.inv(np.asarray(A, float)), q2[o[:, 0]])).T) <= 6.0
        keep = b < lr * s2
        if md is not None:
            keep &= b < md
        right += int((keep & ok).sum())
        kept += int(keep.sum())
        loose += int(((b < 0.95 * s2) & ok).sum())
    prec = right / kept if kept else 0.0
    share = right / max(1, loose)
    print(f"  your rule on 7 unseen photos: {kept} pairs kept, {right} right: precision {prec:.3f}; your network keeps "
          f"{loose} right pairs with a loose 0.95, your rule {share:.0%} of them")
    c.ok(prec >= P_MIN, f"with your rule (ratio {lr:g}, max_dist {md}) only {prec:.2f} of the kept pairs are right on "
         f"unseen photos (at least {P_MIN} needed): RANSAC then needs many more samples and a wrong place collects "
         "inliers. Look at your `curve` tables again: a stricter threshold")
    c.ok(share >= RIGHT_SHARE, f"your rule keeps {share:.0%} of the {loose} right pairs your network finds with a loose "
         f"0.95 (at least {RIGHT_SHARE:.0%} needed): too strict for shaken photos — read the SHAKEN table of `curve`, "
         "then a looser threshold")


def env_attempt(lm, mt, net, e, err_deg, lr, md):
    """Your network on one envelope photo with the heading prior wrong by err_deg: accepted by YOUR gates AND right?"""
    mg = cv2_read(e["map"])
    pg = cv2_read(e["photo"])
    got = go(lm.learned_pairs, mg, pg, e["heading_deg"] + err_deg, e["zoom"], net, lr, md, seconds=120)
    src, dst = (arr(x, "learned_pairs").reshape(-1, 2) for x in got)
    fit, inl = go(mt.ransac_similarity, src, dst, 6.0, 500, np.random.default_rng(0))
    inl = np.asarray(inl, bool)
    ok, _ = go(mt.gates, fit, dst[inl] if len(dst) else dst, pg.shape, e["zoom"])
    if not ok:
        return False, int(inl.sum())
    cpt = np.array([[319.5, 239.5]])
    M = sim_matrix(*[float(x) for x in fit])
    err = float(np.hypot(*(warp(np.linalg.inv(M), cpt) - warp(np.linalg.inv(np.array(e["H"])), cpt))[0]))
    return err * e["map_m_per_px"] <= 10.0, int(inl.sum())


def cv2_read(rel):
    import cv2
    img = cv2.imread(os.path.join(DATA, rel), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise CheckFailed(f"cannot read {DATA}/{rel}: is the data folder mounted? (tell your teacher)")
    return img


@c.test("Step 10 — your DECISION: the heading limit, from your network's envelope (a σ, not an error)",
        hint="Lab Step 10: NETWORK_MAX_ERR_DEG = the error printed under table A of `envelope`; HEADING_LIMIT_DEG is a σ: "
             "a compass with σ is more than 2σ off about once in 20 photos, so 2 × HEADING_LIMIT_DEG must stay inside "
             "NETWORK_MAX_ERR_DEG.")
def _():
    torch_threads()
    student_net()
    lr, md = threshold()
    hl = heading_limit()
    (me,) = answers("NETWORK_MAX_ERR_DEG")
    if me is None:
        raise CheckFailed("NETWORK_MAX_ERR_DEG is still None: copy the error printed under table A of `envelope`")
    me = number(me, "NETWORK_MAX_ERR_DEG")
    ld = module("navera_lite.learned_desc")
    lm = module("navera_lite.learned_match")
    mt = module("navera_lite.match")
    net = go(ld.load_weights, "my_desc.pt")
    env = {(e["place"], e["effect"]): e for e in json.load(open(os.path.join(DATA, "envelope.json")))}
    sharp = [env[("city", "sharp")], env[("olives", "sharp")]]
    at = [env_attempt(lm, mt, net, e, me, lr, md) for e in sharp]
    c.ok(all(a[0] for a in at), f"NETWORK_MAX_ERR_DEG = {me:g}: with that heading error your network does not match "
         "both places (`envelope`, table A, with your LEARNED_RATIO): copy the error printed under table A")
    (ei,) = answers("ENV_OLIVES_INLIERS")
    if ei is None:
        raise CheckFailed("ENV_OLIVES_INLIERS is still None: copy your network's olives inliers from the row of table A "
                          "at NETWORK_MAX_ERR_DEG")
    n_ol = at[1][1]
    c.ok(abs(number(ei, "ENV_OLIVES_INLIERS") - n_ol) <= max(3, 0.2 * n_ol), f"ENV_OLIVES_INLIERS = {ei}: that is not "
         f"what your network finds on olives at {me:g}° — copy the number from YOUR `envelope` table A, row "
         "NETWORK_MAX_ERR_DEG")
    if me < 40:
        nxt = [env_attempt(lm, mt, net, e, me + 5, lr, md)[0] for e in sharp]
        c.ok(not all(nxt), f"NETWORK_MAX_ERR_DEG = {me:g}: your network still matches both places beyond {me:g}°: "
             "copy the error printed under table A of YOUR `envelope` run")
    c.ok(2 * hl <= me + 0.5, f"HEADING_LIMIT_DEG = {hl:g}: with σ up to {hl:g}°, about 1 photo in 20 is more than "
         f"2σ = {2 * hl:g}° off, beyond the {me:g}° your network can take. Choose σ ≤ {me / 2:g}° (lesson §8)")


@c.test("Steps 8 and 10: your network against SIFT, and its envelope",
        hint="Copy the pair counts from `learned olives_shaken`; run `envelope` and explain where your network wins, "
             "where it fails, and how its TRAINING data explains both (mission 21: turns ±20°, scale 0.8–1.25, blur).")
def _():
    ps, pl, pe, why = answers("PAIRS_SIFT_SHAKEN", "PAIRS_LEARNED_SHAKEN", "PREDICT_ENVELOPE", "EXPLAIN_ENVELOPE")
    near(ps, 2, 0, "PAIRS_SIFT_SHAKEN")
    pl = number(pl, "PAIRS_LEARNED_SHAKEN")
    if os.path.exists("my_desc.pt"):
        torch_threads()
        student_net()
        ld = module("navera_lite.learned_desc")
        lm = module("navera_lite.learned_match")
        net = go(ld.load_weights, "my_desc.pt")
        p = {q["name"]: q for q in json.load(open(os.path.join(DATA, "pairs.json")))}["olives_shaken"]
        got = go(lm.learned_pairs, cv2_read(p["map"]), cv2_read(p["photo"]), p["prior"]["heading_deg"],
                 p["prior"]["zoom"], net, 0.8, None, seconds=120)
        n = len(arr(got[0], "learned_pairs").reshape(-1, 2))
        c.ok(abs(pl - n) <= max(3, 0.1 * n), f"PAIRS_LEARNED_SHAKEN = {pl:g}, but your network gives {n} pairs on "
             "olives_shaken (ratio 0.8): run `learned olives_shaken` again and copy the 'pairs' column")
    predicted("PREDICT_ENVELOPE", pe)
    explained("EXPLAIN_ENVELOPE", why,
              ((r"blur", r"shak", r"motion", r"sharp"), "where your network beats SIFT (blur, shake)"),
              ((r"heading", r"rotat", r"turn", r"angle", r"orient", r"\d+ ?°", r"\d+ deg"), "where it fails (the heading)"),
              ((r"train", r"learn", r"data", r"±", r"20", r"saw", r"seen"), "what in its training explains it"),
              ((r"σ", r"sigma", r"2 ?σ", r"twice", r"1 in 20", r"one in 20", r"5 ?%", r"double"),
               "why your σ limit is about half the error your network can take"))


def crafted(kind):
    """Pairs the given sift_pairs is made to return (map → photo): exact inliers plus spread outliers."""
    r = np.random.default_rng(7 if kind == "bunched" else 8)
    if kind == "bunched":            # all the inliers in ONE cell of the 4 × 2 grid, the wrong pairs all over the photo
        M = sim_matrix(1.6, -30.0, 120.0, 260.0)
        dst_in = np.column_stack([r.uniform(10, 150, 40), r.uniform(10, 230, 40)])
    else:                            # zoom 4: inliers all over the photo, their MAP points in one corner of the map
        M = sim_matrix(4.0, 0.0, 0.0, 0.0)
        dst_in = np.column_stack([r.uniform(8, 632, 60), r.uniform(8, 472, 60)])
    src_in = warp(np.linalg.inv(M), dst_in)
    src_out = np.column_stack([r.uniform(0, 511, 30), r.uniform(0, 511, 30)])
    dst_out = np.column_stack([r.uniform(0, 639, 30), r.uniform(0, 479, 30)])
    return np.vstack([src_in, src_out]), np.vstack([dst_in, dst_out])


@c.test("TODO 9: match_photo() uses YOUR gates on the INLIERS' PHOTO points, with the prior's zoom (two crafted cases)",
        hint="Lab Step 11, hint 2: gates(fit, dst[inl], photo shape, prior['zoom']) — the spread is measured on the photo, "
             "with the inliers only; the scale is compared with the prior's zoom.")
def _():
    lm = module("navera_lite.learned_match")
    (f,) = need(lm, "match_photo")
    if is_stub(f):
        raise CheckFailed("match_photo() is not written yet (it is still the TODO stub in navera_lite/learned_match.py)")
    calls = []
    cfg = {"learned_ratio": 0.8, "learned_max_dist": None, "heading_limit_deg": 10.0}
    mg, pg = np.zeros((512, 512), np.uint8), np.zeros((480, 640), np.uint8)
    out = {}
    for kind, zoom in (("bunched", 1.6), ("spread", 4.0)):
        pairs = crafted(kind)

        def fake(map_gray, photo_gray, ratio=0.8, n=1500, _p=pairs):
            calls.append(1)
            return _p[0].copy(), _p[1].copy()
        lm.sift_pairs = fake
        out[kind] = go(f, mg, pg, {"heading_deg": None, "heading_sigma_deg": 180.0, "zoom": zoom}, None, cfg, seconds=60)
    if not calls:
        raise CheckFailed("match_photo never called sift_pairs: use the given sift_pairs (ratio SIFT_RATIO) for SIFT")
    for v in out.values():
        if not isinstance(v, dict) or "ok" not in v:
            raise CheckFailed(f"match_photo must return a dict with ok, method, fit, inliers, reason — got {v!r:.150}")
    c.ok(not out["bunched"]["ok"], "a fit whose 40 inliers sit in ONE corner of the photo, with 30 wrong pairs spread "
         "over it, was ACCEPTED: the spread gate must see the INLIERS' photo points (dst[inl]), not every pair")
    if not out["spread"]["ok"] and out["spread"].get("reason") == "inliers bunched":
        raise CheckFailed("60 inliers spread over the whole photo were refused as 'inliers bunched': you gave gates() "
                          "the MAP points — the spread is measured on the PHOTO points dst[inl]")
    c.ok(out["spread"]["ok"], f"a right, well-spread match at zoom 4 (the prior's zoom 4) was refused "
         f"({out['spread'].get('reason')!r}): give gates() the prior's zoom as predicted_scale, and dst[inl]")


@c.test("TODO 9 + your decisions: match_photo() on 16 unseen scenes — no wrong position, enough right ones",
        hint="Lab Step 11: SIFT and/or your network, each through ransac_similarity and YOUR gates with the prior's zoom; "
             "the network only when the heading prior is known and its σ ≤ cfg['heading_limit_deg']; refuse when no "
             "attempt passes. Run `python3 run_match.py mission` first.")
def _():
    torch_threads()
    student_net()
    cfg = decisions()
    ld = module("navera_lite.learned_desc")
    (f,) = functions("learned_match", "match_photo")
    net = go(ld.load_weights, "my_desc.pt")
    arrays, meta = scenes()
    right, wrong, refused = 0, [], 0
    tried_learned = accepted_learned = outside = 0
    (me,) = answers("NETWORK_MAX_ERR_DEG")
    for s in meta:
        pr = s["prior"]
        if pr["heading_deg"] is not None and pr["heading_sigma_deg"] <= cfg["heading_limit_deg"] and s["H"] is not None:
            Hs = np.array(s["H"])
            off = abs((pr["heading_deg"] + np.degrees(np.arctan2(Hs[1, 0], Hs[0, 0])) + 180.0) % 360.0 - 180.0)
            outside += isinstance(me, (int, float)) and not isinstance(me, bool) and off > me
        v = go(f, arrays["map_" + s["map"]], arrays[s["name"] + "_photo"], dict(s["prior"]), net, dict(cfg), seconds=120)
        if not isinstance(v, dict) or not {"ok", "method", "fit", "inliers", "reason"} <= set(v):
            raise CheckFailed(f"match_photo must return a dict with ok, method, fit, inliers, reason — got {v!r:.150}")
        if v["method"] not in ("sift", "learned", None):
            raise CheckFailed(f"method must be 'sift', 'learned' or None, got {v['method']!r}")
        tried_learned += v["method"] == "learned"
        if not v["ok"]:
            refused += 1
            continue
        if v["fit"] is None:
            raise CheckFailed("ok is True but fit is None: an accepted match returns its (s, theta_deg, tx, ty)")
        if s["H"] is None:
            wrong.append(f"{s['name']} (a photo of another place)")
            continue
        M = sim_matrix(*[float(x) for x in v["fit"]])
        cpt = np.array([[319.5, 239.5]])
        e = float(np.hypot(*(warp(np.linalg.inv(M), cpt) - warp(np.linalg.inv(np.array(s["H"])), cpt))[0])) * s["map_m_per_px"]
        if e <= 10.0:
            right += 1
            accepted_learned += v["method"] == "learned"
        else:
            wrong.append(f"{s['name']} ({e:.0f} m off)")
    print(f"  your matcher on {len(meta)} unseen scenes: {right} right, {refused} refused, {len(wrong)} wrong; your "
          f"network gave {accepted_learned} of the right answers; your limit let it see {outside} scene(s) with the "
          "prior outside its measured envelope")
    c.ok(not wrong, f"your matcher ACCEPTED {len(wrong)} wrong position(s): {', '.join(wrong)}. NAVERA's rule is zero: "
         "every accepted attempt must pass YOUR gates with the prior's zoom")
    if accepted_learned == 0 and tried_learned == 0:
        raise CheckFailed(f"{right} of {len(meta)} scenes matched, and your network was never used: shaken photos of "
                          "olive groves need it when the heading is known (σ 6–8° here): is HEADING_LIMIT_DEG too strict, "
                          "or is the network never tried after SIFT is refused?")
    c.ok(right >= 7 and accepted_learned >= 1, f"only {right} of {len(meta)} unseen scenes matched, {accepted_learned} of "
         "them by your network (at least 7, and at least one by your network, are possible with SIFT, your network and the "
         "gates): try the second matcher when the first is refused (and if a check of TODO 1–7 fails, fix it first: "
         "match_photo runs them)")
    explained("EXPLAIN_POLICY", answers("EXPLAIN_POLICY")[0],
              ((r"sift", r"network", r"learned"), "which matcher you run"),
              ((r"heading", r"σ", r"sigma", r"prior", r"compass"), "when the network may be used"),
              ((r"gate", r"refus", r"scale", r"inlier"), "what makes your matcher refuse"))


@c.test("report.md: four headings, your own words, your numbers",
        hint="Lab Step 12: keep the four ## headings, 200–500 words, replace every TODO, quote KEPT_08, RESID_H_TILT, "
             "your LEARNED_RATIO and HEADING_LIMIT_DEG as numbers.")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## 1. Pairs and models", "## 2. RANSAC and the gates", "## 3. Your network as a matcher",
              "## 4. Your matcher's policy"):
        c.ok(h in text, f"report.md lost its heading “{h}”")
    c.ok("TODO" not in text, "report.md still contains a TODO")
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    n = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body))
    c.ok(200 <= n <= 560, f"report.md has {n} words; write 200–500")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    k8, rh, lr, hl = answers("KEPT_08", "RESID_H_TILT", "LEARNED_RATIO", "HEADING_LIMIT_DEG")
    for v, name in ((k8, "KEPT_08"), (rh, "RESID_H_TILT"), (lr, "LEARNED_RATIO"), (hl, "HEADING_LIMIT_DEG")):
        v = number(v, name)
        c.ok(any(abs(x - v) <= (0.006 if v < 1 else 0.6) for x in nums), f"report.md does not quote your {name} ({v:g})")


c.milestone("matcher", "TODO", "Step", "report", label="Matchmaker")

c.run()
