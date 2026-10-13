import contextlib
import io
import os
import re
import tempfile

import numpy as np

from academy_check import (CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run)

c = Checker()
DATA = "/data/academy/21-features"


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
        if "math" in msg and "size-1" in msg or "only length-1" in msg:
            msg += " — math.sqrt cannot take an array: use np.sqrt"
        if "does not require grad" in msg:
            msg += " — the loss lost its gradient: torch operations only (no .item(), numpy or torch.tensor of a result)"
        if "mat1 and mat2" in msg:
            msg += " — the Linear layer gets the wrong size: three 2 × 2 poolings, then flatten to 64 * 4 * 4"
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


# ---------------------------------------------------------------- unseen inputs (expected values from the reference)
IMG = np.random.default_rng(2121).integers(0, 256, (9, 11)).astype(np.uint8)
PIX = [(0, 0), (4, 5), (8, 10), (2, 7), (6, 1)]                       # (row, column)
GX = [0.0, 3.875, 0.0, 5.0, -9.125]
GY = [0.0, 4.875, 0.0, 33.0, -4.875]
_r = np.random.default_rng(77)
TGX = _r.normal(0, 10, (12, 14)).astype(np.float32)
TGY = _r.normal(0, 10, (12, 14)).astype(np.float32)
ST2 = {(6, 7): [124.924, 101.974, -4.329], (0, 0): [146.562, 100.528, 3.079], (11, 13): [52.136, 90.044, 0.984]}
ST08 = [143.896, 120.915, -48.948]


def square(h=30, w=36):
    img = np.zeros((h, w), np.uint8)
    img[5:20, 8:30] = 200
    return img


@c.test("TODO 1: gradients() on an unseen image — float32, divided by 8, both signs",
        hint="Lesson §1: cv2.Sobel with cv2.CV_32F (not −1) and ksize=3, (1, 0) for gx and (0, 1) for gy, each divided by 8. "
             "Return (gx, gy).")
def _():
    (f,) = functions("features", "gradients")
    got = go(f, IMG)
    if not isinstance(got, tuple) or len(got) != 2:
        raise CheckFailed(f"gradients() must return two arrays (gx, gy), got {type(got).__name__}")
    gx, gy = (np.asarray(x) for x in got)
    c.ok(gx.shape == IMG.shape and gy.shape == IMG.shape, f"gx and gy must have the image's shape {IMG.shape}, got "
         f"{gx.shape} and {gy.shape}")
    c.ok(gx.dtype == np.float32 and gy.dtype == np.float32, f"gx and gy must be float32 arrays, got {gx.dtype}, {gy.dtype}")
    vx = [float(gx[p]) for p in PIX]
    vy = [float(gy[p]) for p in PIX]
    if np.allclose(vx, [8 * v for v in GX], atol=1e-3):
        raise CheckFailed("gradients are 8 times too large: divide the Sobel sums by 8 (the course rule, mission 08)")
    if min(vx + vy) >= 0 and min(GX + GY) < 0:
        raise CheckFailed("no negative gradient at all: the output depth must be cv2.CV_32F (a uint8 result cuts "
                          "negative values to 0)")
    if np.allclose(vx, GY, atol=1e-3) and np.allclose(vy, GX, atol=1e-3):
        raise CheckFailed("gx and gy are swapped: (1, 0) is the derivative in x (to the right) and comes first")
    c.ok(np.allclose(vx, GX, atol=1e-3), f"gx at pixels (row, col) {PIX}: {vx}, expected other values")
    c.ok(np.allclose(vy, GY, atol=1e-3), f"gy at pixels (row, col) {PIX}: {vy}, expected other values")


@c.test("TODO 2: structure_tensor() on unseen gradients, with two window sizes",
        hint="Lesson §2: the three products gx·gx, gy·gy, gx·gy, each blurred by cv2.GaussianBlur(…, (0, 0), sigma). "
             "Use the sigma you are given. Return (sxx, syy, sxy).")
def _():
    (f,) = functions("features", "structure_tensor")
    got = go(f, TGX, TGY, 2.0)
    if not isinstance(got, tuple) or len(got) != 3:
        raise CheckFailed(f"structure_tensor() must return three arrays (sxx, syy, sxy), got {type(got).__name__}")
    st = [arr(x, "structure_tensor", TGX.shape) for x in got]
    v = [float(a[6, 7]) for a in st]
    if np.allclose(v, [float(TGX[6, 7] ** 2), float(TGY[6, 7] ** 2), float(TGX[6, 7] * TGY[6, 7])], atol=1e-2):
        raise CheckFailed("structure_tensor returns the products without the window: blur each product with "
                          "cv2.GaussianBlur(…, (0, 0), sigma)")
    for (y, x), want in ST2.items():
        got_v = [round(float(a[y, x]), 3) for a in st]
        if np.allclose(got_v, [want[0], want[2], want[1]], atol=0.02):
            raise CheckFailed("the order of the result: (sxx, syy, sxy) — Syy second, Sxy last")
        c.ok(np.allclose(got_v, want, atol=0.02), f"sigma 2.0, pixel (row {y}, col {x}): (Sxx, Syy, Sxy) = {got_v}, "
             "not the right values (the border is mirrored, as cv2.GaussianBlur does by default)")
    st = [arr(x, "structure_tensor") for x in go(f, TGX, TGY, 0.8)]
    c.ok(np.allclose([float(a[6, 7]) for a in st], ST08, atol=0.02),
         "with sigma = 0.8 the values are not right: do you use the sigma argument (not a fixed 1.5)?")


@c.test("TODO 3: eigen2() on numbers and on arrays, larger one first",
        hint="Lesson §2's 🧰 box: (a + c)/2 ± √(((a − c)/2)² + b²), with np.sqrt so that arrays work; l1 is the larger.")
def _():
    (f,) = functions("features", "eigen2")
    v = go(f, 7.0, 3.0, 2.0)
    try:
        l1, l2 = (float(x) for x in v)
    except (TypeError, ValueError):
        raise CheckFailed(f"eigen2(7, 3, 2) must return two numbers (l1, l2), got {v!r}")
    if abs(l1 - 2.1716) < 1e-3 and abs(l2 - 7.8284) < 1e-3:
        raise CheckFailed("eigen2 returns (smaller, larger): l1 must be the LARGER eigenvalue")
    c.ok(abs(l1 - 7.828427) < 1e-5 and abs(l2 - 2.171573) < 1e-5, f"eigen2(7, 3, 2) = ({l1:.4f}, {l2:.4f}), expected "
         "other values — check ((a − c)/2)² and b² under the root")
    v = go(f, -1.0, 5.0, 0.0)
    c.ok(np.allclose([float(x) for x in v], [5.0, -1.0], atol=1e-9), f"eigen2(−1, 5, 0) = {v!r}: expected (5, −1)")
    A = np.array([[10.0, 4.0], [1.0, 0.0]])
    B = np.array([[2.0, 4.0], [9.0, 0.0]])
    C = np.array([[3.0, -2.0], [0.0, 1.0]])
    v = go(f, A, B, C)
    l1, l2 = (arr(x, "eigen2 on arrays", (2, 2)) for x in v)
    c.ok(np.allclose(l1, [[11, 6], [9, 1]]) and np.allclose(l2, [[1, 2], [1, -1]]),
         "eigen2 on 2 × 2 arrays (one matrix per element) gives wrong values: use numpy operations (np.sqrt), "
         "element by element")


@c.test("TODO 4: harris() on an unseen picture, with other k and sigma",
        hint="Lesson §2: R = Sxx·Syy − Sxy² − k·(Sxx + Syy)², from YOUR gradients and structure_tensor with the given "
             "sigma; k and sigma are arguments.")
def _():
    (f,) = functions("features", "harris")
    img = square()
    for (k, s), want in (((0.04, 1.5), [5003020.0, -917502.62, 0.0, 0.0]), ((0.06, 1.0), [7431260.0, -2464631.75, 0.0, 0.0])):
        r = arr(go(f, img, k, s), f"harris(img, {k}, {s})", img.shape)
        v = [float(r[p]) for p in ((5, 8), (12, 8), (12, 18), (25, 3))]
        if v[0] < 0 and v[1] > 0:
            raise CheckFailed("harris: the signs are reversed — R = det − k·trace², det = Sxx·Syy − Sxy²")
        c.ok(np.allclose(v, want, rtol=1e-4, atol=1.0), f"harris(k={k}, sigma={s}) at the corner, the side, the inside "
             f"and the outside of a rectangle: {[round(x, 1) for x in v]} — expected other values (if check 1 or 2 fails, fix "
             "it first: harris uses your gradients and structure_tensor)"
             + (" (do you use k and sigma, not fixed values?)" if (k, s) != (0.04, 1.5) else ""))


P1 = np.array([[80.5, 80.794], [51.533, 28.58], [5.393, 38.337], [40.847, 4.528], [4.876, 99.918], [65.237, 23.451],
               [43.495, 97.419], [89.768, 84.423], [39.24, 49.302], [67.669, 6.08], [55.56, 27.145], [87.965, 6.421],
               [67.918, 87.009], [22.732, 89.545], [87.22, 1.852], [70.75, 0.12], [50.336, 43.667], [20.325, 32.494],
               [80.622, 31.645], [14.904, 69.851], [44.854, 79.894], [23.552, 31.978], [79.988, 50.707], [50.639, 23.619],
               [1.454, 93.322], [8.583, 84.493], [36.788, 95.102], [39.943, 93.644], [55.616, 24.014], [74.142, 67.439],
               [68.421, 46.382], [22.189, 64.094], [10.709, 69.222], [63.539, 37.651], [79.852, 19.403], [39.046, 79.793],
               [38.048, 71.326], [61.252, 94.1], [99.168, 72.368], [80.884, 15.287]])
P2 = np.array([[66.27, 99.593], [58.648, 44.072], [10.809, 42.349], [53.011, 20.684], [71.57, 48.355], [28.886, 103.207],
               [71.791, 107.502], [39.821, 61.674], [78.149, 29.816], [60.417, 45.059], [97.563, 36.408], [55.225, 107.486],
               [52.238, 58.171], [27.277, 38.356], [83.162, 59.805], [11.808, 73.179], [40.152, 87.932], [32.118, 40.233],
               [58.458, 42.317], [-7.752, 89.535], [3.821, 84.211], [26.316, 102.551], [28.831, 104.916], [64.097, 43.556],
               [67.916, 86.099], [66.988, 68.857], [22.003, 72.438], [8.892, 67.588], [69.784, 60.134], [31.268, 84.9],
               [50.078, 106.481], [87.033, 99.328], [87.452, 41.195], [11.134, 112.245], [43.816, 21.101], [0.0, 7.251],
               [25.758, 50.118], [72.188, 117.724], [106.857, 29.07], [73.385, 110.585], [12.192, 102.485], [47.528, 93.802],
               [38.712, 75.087], [60.842, 12.531], [91.176, 98.753], [57.958, 46.561], [113.699, 44.917], [105.554, 50.229]])
HS = np.array([[0.9, -0.3, 20.0], [0.3, 0.9, 5.0], [0, 0, 1.0]])


@c.test("TODO 5: repeatability() with an unseen homography, tolerances and edge cases",
        hint="Lesson §4: project pts1 with warp_points(H, pts1); keep only the projections INSIDE picture 2 "
             "(0 ≤ x ≤ w − 1, 0 ≤ y ≤ h − 1, h, w = shape2[:2]); share of them with a point of pts2 within tol_px (≤). "
             "0.0 when nothing is inside or pts2 is empty.")
def _():
    (f,) = functions("features", "repeatability")
    v = float(go(f, P1, P2, HS, (90, 120)))
    if abs(v - 20 / 40) < 1e-6:
        raise CheckFailed(f"repeatability = {v:.3f}: you divided by ALL the points of picture 1 — only those whose "
                          "projection falls inside picture 2 count")
    c.ok(abs(v - 0.7142857) < 1e-6, f"an unseen pair (a turn, a zoom and a shift, 90 × 120 picture): {v:.4f}, expected "
         "another value — is the image of a point H·[x, y, 1] divided by its last number (warp_points does it)?")
    c.ok(abs(float(go(f, P1, P2, HS, (90, 120), 1.0)) - 0.1785714) < 1e-6, "with tol_px = 1.0 the value is wrong: use "
         "the tol_px argument")
    c.ok(abs(float(go(f, P1, P2, HS, (90, 120, 3), 5.0)) - 0.8928571) < 1e-6,
         "with a colour shape (90, 120, 3) and tol_px = 5 the value is wrong: h, w = shape2[:2]")
    v = go(f, [[2.0, 2.0], [7.0, 7.0]], [[5.0, 2.0], [7.0, 9.0]], np.eye(3), (10, 10), 3.0)
    c.ok(abs(float(v) - 1.0) < 1e-9, f"two points exactly 3 px and 2 px from a point of picture 2, tol 3: expected 1.0, "
         f"got {v!r} — the test is ≤ tol_px")
    v = go(f, [[2.0, 2.0], [9.0, 9.0]], [[9.0, 9.0]], np.eye(3), (10, 10), 0.5)
    c.ok(abs(float(v) - 0.5) < 1e-9, f"a point at (9, 9) in a 10 × 10 picture is inside (x ≤ w − 1): expected 0.5, got {v!r}")
    for args, why in ((([[1.0, 1.0]], np.zeros((0, 2)), np.eye(3), (10, 10)), "picture 2 has no point"),
                      (([[50.0, 50.0]], [[1.0, 1.0]], np.eye(3), (10, 10)), "no point of picture 1 falls inside")):
        v = go(f, *args)
        c.ok(v is not None and abs(float(v)) < 1e-12 and not np.isnan(float(v)), f"when {why} the answer is 0.0, got {v!r}")


def kind(v, name):
    s = str(v).strip().lower().strip(".")
    if s not in ("flat", "edge", "corner"):
        raise CheckFailed(f'{name} must be "flat", "edge" or "corner", got {v!r}')
    return s


@c.test("Steps 0–3: the scout's ranking, the three points of the house",
        hint="Step 2: run `python3 run_features.py house`; for each point compute eigen2(Sxx, Syy, Sxy) and "
             "R = Sxx·Syy − Sxy² − 0.04·(Sxx + Syy)²: two small eigenvalues = flat, one large = edge, two large = corner.")
def _():
    pr, k1, k2, k3, r3, why = answers("PREDICT_RANK", "KIND_1", "KIND_2", "KIND_3", "R_POINT_3", "EXPLAIN_EIGEN")
    predicted("PREDICT_RANK", pr)
    ks = [kind(k1, "KIND_1"), kind(k2, "KIND_2"), kind(k3, "KIND_3")]
    c.ok(ks[0] == "flat", f"KIND_1 = {ks[0]!r}: both eigenvalues of point 1 are tiny (Sxx ≈ Syy ≈ 0.2)")
    c.ok(ks[1] == "edge", f"KIND_2 = {ks[1]!r}: point 2 has one large eigenvalue (≈ 383) and one ≈ 0, and R < 0")
    c.ok(ks[2] == "corner", f"KIND_3 = {ks[2]!r}: point 3 has two large eigenvalues (≈ 160 and 46), and R > 0")
    r3 = number(r3, "R_POINT_3")
    if abs(r3 - 10650.2) < 60 or abs(r3 - 7378.4) < 60:
        raise CheckFailed(f"R_POINT_3 = {r3:g}: that is det alone (or without Sxy²); R = Sxx·Syy − Sxy² − 0.04·(Sxx + Syy)²")
    c.near(r3, 5674.0, 30.0, "R_POINT_3")
    explained("EXPLAIN_EIGEN", why,
              ((r"chang", r"direction", r"move", r"shift", r"vary", r"variation"), "what an eigenvalue measures"),
              ((r"det", r"trace", r"product", r"sum", r"square root", r"sqrt", r"faster", r"cheap", r"slow", r"costly",
                r"expensive"), "why Harris uses det and trace instead"))


@c.test("Steps 4–5: repeatability numbers, the scout's terrains, CLAHE",
        hint="Copy the numbers from `python3 run_features.py repeat` (two decimals) and `python3 run_features.py terrain` "
             "(the first SIFT column), then explain in your own words.")
def _():
    (pz, hr, hz, sz, ch, why_s, mk, sf, db, da, why_t) = answers(
        "PREDICT_ZOOM", "REP_HARRIS_ROT35", "REP_HARRIS_ZOOM4", "REP_SIFT_ZOOM4", "CHANCE", "EXPLAIN_SCALE",
        "MOST_KEYPOINTS", "SIFT_FIELDS", "DARK_SIFT_BEFORE", "DARK_SIFT_AFTER", "EXPLAIN_TERRAIN")
    predicted("PREDICT_ZOOM", pz)
    hr, hz, sz, ch = (number(v, n) for v, n in ((hr, "REP_HARRIS_ROT35"), (hz, "REP_HARRIS_ZOOM4"),
                                                  (sz, "REP_SIFT_ZOOM4"), (ch, "CHANCE")))
    if hr > 1 or hz > 1 or sz > 1:
        raise CheckFailed("repeatability is a share from 0 to 1 (write 0.85, not 85)")
    if abs(hz - 0.78) < 0.012 and abs(sz - 0.39) < 0.012:
        raise CheckFailed("REP_HARRIS_ZOOM4 and REP_SIFT_ZOOM4 are swapped: the zoom4 row, columns harris and sift")
    c.near(hr, 0.85, 0.011, "REP_HARRIS_ROT35 (if your harris is right, `repeat` prints 0.85)")
    c.near(hz, 0.39, 0.011, "REP_HARRIS_ZOOM4")
    c.near(sz, 0.78, 0.011, "REP_SIFT_ZOOM4")
    c.ok(0.07 <= ch <= 0.10, f"CHANCE = {ch}: the last column of the `repeat` table")
    explained("EXPLAIN_SCALE", why_s,
              ((r"rotat", r"turn", r"eigen", r"invarian", r"orient"), "why a turn does not hurt Harris"),
              ((r"scale", r"window", r"size", r"zoom", r"detail", r"closer", r"fixed"), "what the zoom does to a fixed window"))
    c.ok(str(mk).strip().lower().strip(".") in ("olives", "olive", "olive grove", "terrain_olives", "terrain_olives.png"),
         f"MOST_KEYPOINTS = {mk!r}: read the first SIFT column of `terrain`")
    sf, db, da = (number(v, n) for v, n in ((sf, "SIFT_FIELDS"), (db, "DARK_SIFT_BEFORE"), (da, "DARK_SIFT_AFTER")))
    if abs(sf - 493) < 2:
        raise CheckFailed("SIFT_FIELDS = 493 is the 'SIFT 0.02' column; the question uses OpenCV's default contrast")
    c.near(sf, 71, 1, "SIFT_FIELDS")
    c.near(db, 17, 2, "DARK_SIFT_BEFORE")
    c.near(da, 632, 3, "DARK_SIFT_AFTER")
    explained("EXPLAIN_TERRAIN", why_t,
              ((r"olive", r"field", r"tree", r"sea", r"coast", r"salt"), "which terrain surprised you"),
              ((r"repet", r"alike", r"similar", r"same", r"twin", r"uniform", r"distinct", r"confus", r"spread", r"bunch",
                r"pattern"), "why many keypoints do not mean easy matching"))


c.milestone("corner-hunter", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "Steps 0–3:", "Steps 4–5:",
            label="Corner hunter")


# ======================================================================== session 2 — Learner
D1 = np.array([107, 222, 246, 73, 29, 154, 170, 199, 164, 183, 234, 234, 237, 220, 184, 235, 3, 6, 204, 111, 191, 124,
               230, 16, 172, 1, 37, 212, 74, 251, 89, 200], np.uint8)
D2 = np.array([245, 80, 250, 180, 247, 76, 131, 189, 247, 71, 123, 200, 214, 252, 54, 252, 29, 226, 223, 233, 223, 181,
               148, 141, 20, 236, 235, 22, 152, 94, 190, 155], np.uint8)


@c.test("TODO 6: hamming() on unseen 256-bit descriptors",
        hint="Lesson §5: np.bitwise_xor of the two uint8 arrays, np.unpackbits, then count the ones; return int(…).")
def _():
    (f,) = functions("features", "hamming")
    v = go(f, D1, D2)
    if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
        raise CheckFailed(f"hamming() must return an int, got {v!r} ({type(v).__name__}) — int(…)")
    c.eq(int(v), 128, "hamming of two unseen 32-byte descriptors")
    c.eq(int(go(f, D1, D1)), 0, "hamming of a descriptor with itself")
    a = np.array([255, 0, 15], np.uint8)
    b = np.array([0, 0, 240], np.uint8)
    w = int(go(f, a, b))
    if w == 8:
        raise CheckFailed("hamming([255, 0, 15], [0, 0, 240]) = 8: that counts the EQUAL bits — count the ones of the XOR")
    c.eq(w, 16, "hamming([255, 0, 15], [0, 0, 240])")


def reference_net():
    """The PatchNet of the specification, built by the check (never the student's class)."""
    import torch.nn as nn
    import torch.nn.functional as F

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 16, 3, padding=1)
            self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
            self.conv3 = nn.Conv2d(32, 64, 3, padding=1)
            self.fc = nn.Linear(1024, 64)

        def forward(self, x):
            x = F.max_pool2d(F.relu(self.conv1(x)), 2)
            x = F.max_pool2d(F.relu(self.conv2(x)), 2)
            x = F.max_pool2d(F.relu(self.conv3(x)), 2)
            return F.normalize(self.fc(x.flatten(1)), dim=1)
    return Net()


def tensors(p):
    """uint8 patches (N, s, s) → the network's input, as to_tensor() specifies (computed by the check)."""
    import torch
    o = (p.shape[-1] - 32) // 2
    x = torch.as_tensor(p[:, o:o + 32, o:o + 32].astype(np.float32)).unsqueeze(1)
    x = x - x.mean(dim=(2, 3), keepdim=True)
    return x / (x.std(dim=(2, 3), keepdim=True) + 1e-3)


def describe_ref(net, p):
    import torch
    net.eval()
    with torch.no_grad():
        return np.concatenate([net(tensors(p[s:s + 512])).numpy() for s in range(0, len(p), 512)])


def score(d1, d2, gallery=256):
    right = 0
    for s in range(0, len(d1), gallery):
        a, b = d1[s:s + gallery].astype(np.float64), d2[s:s + gallery].astype(np.float64)
        dist = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        right += int((dist.argmin(axis=1) == np.arange(len(a))).sum())
    return right / len(d1)


@c.test("TODO 7: PatchNet — the layers of the table, 88 896 parameters, the forward pass in order, unit rows",
        hint="Lab Step 7: in __init__, super().__init__() then conv1, conv2, conv3, fc with the docstring's sizes; in "
             "forward, conv → relu → max_pool2d(2) three times, flatten(1), fc, F.normalize(…, dim=1).")
def _():
    import torch
    ld = module("navera_lite.learned_desc")
    (cls,) = need(ld, "PatchNet")
    net = go(cls)
    sd = net.state_dict()
    keys = sorted(str(k) for k in sd.keys())
    want = ["conv1.bias", "conv1.weight", "conv2.bias", "conv2.weight", "conv3.bias", "conv3.weight", "fc.bias", "fc.weight"]
    c.ok(keys == want, f"PatchNet's parameters are {keys}; the check, mission 22 and Sim Lite need exactly {want} — "
         "the attribute names conv1, conv2, conv3, fc")
    n = sum(int(p.numel()) for p in net.parameters())
    c.ok(n == 88896, f"PatchNet has {n} parameters, the table gives 88 896 — check each layer's sizes (and padding=1)")
    torch.manual_seed(21)
    ref = reference_net()
    fd, path = tempfile.mkstemp(suffix=".pt")
    os.close(fd)
    try:
        torch.save(ref.state_dict(), path)
        mine = go(ld.load_weights, path)
        probe = np.random.default_rng(3).integers(0, 256, (6, 48, 48)).astype(np.uint8)
        got = arr(go(ld.describe, mine, probe), "describe(your PatchNet, 6 patches)", (6, 64))
    finally:
        os.remove(path)
    want_d = describe_ref(ref, probe)
    norms = np.linalg.norm(got, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        raise CheckFailed(f"the descriptors have lengths {np.round(norms, 3).tolist()}: divide each row by its length at "
                          "the end (F.normalize(x, dim=1))")
    c.ok(np.allclose(got, want_d, atol=1e-4), "with the same weights, your forward() gives other descriptors than the "
         "table: the order must be conv → ReLU → 2 × 2 max-pooling (three times), flatten, fc, then length 1")


@c.test("TODO 8: triplet_loss() on unseen descriptors, with its gradient and other margins",
        hint="Lesson §8: d = torch.cdist(da, dp); d_pos = the diagonal; d_neg = each row's minimum with the diagonal left "
             "out; mean of relu(margin + d_pos − d_neg). Torch operations only.")
def _():
    ld = module("navera_lite.learned_desc")
    (f,) = functions("learned_desc", "triplet_loss")
    A = [[0.017995, 0.715613, 0.644551, -0.268566], [-0.35751, -0.632767, 0.68357, -0.067267],
         [0.294455, -0.728297, 0.617603, -0.038018], [0.742463, -0.149028, -0.413692, 0.505369],
         [0.748209, -0.183787, -0.138647, 0.62224], [-0.455151, -0.791958, 0.206559, -0.350677]]
    B = [[-0.616527, 0.320527, 0.37602, -0.612998], [-0.615402, -0.398522, 0.672123, -0.103494],
         [-0.002754, -0.53028, 0.835168, -0.14591], [0.851152, 0.23764, -0.440031, 0.159503],
         [0.936977, -0.089517, 0.317735, 0.114482], [-0.494823, -0.774909, -0.33482, -0.206306]]
    da = ld.torch.tensor(A, requires_grad=True)
    dp = ld.torch.tensor(B)
    out = go(f, da, dp)
    if out is None:
        raise CheckFailed("triplet_loss returned None")
    v = float(out.detach())
    for bad, why in ((1.6168990, "the SUM over the batch — the docstring asks for the mean"),
                     (0.5020547, "the diagonal was not left out, so d_neg can be d_pos itself"),
                     (0.2669873, "the impostors taken per COLUMN (min over dim 0): the anchor i compares with every dp[j]")):
        if abs(v - bad) < 1e-4:
            raise CheckFailed(f"triplet_loss = {v:.4f}: {why}")
    c.near(v, 0.2694832, 1e-4, "triplet_loss on 6 unseen pairs (margin 0.5)")
    c.ok(bool(out.requires_grad), "the loss has no gradient: compute it with torch operations only (no .item(), numpy, "
         "float() or torch.tensor() of a result inside)")
    c.near(float(go(f, da, dp, 1.0).detach()), 0.7637190, 1e-4, "triplet_loss with margin = 1.0 (use the margin argument)")
    c.near(float(go(f, da, dp, margin=0.1).detach()), 0.0259908, 1e-4, "triplet_loss with margin = 0.1")


def val_patches(n):
    d = np.load(os.path.join(DATA, "patches_val.npz"))
    return d["a"][:n], d["b"][:n]


def np_triplet(a, p, margin=0.5):
    d = np.sqrt(((a[:, None, :].astype(np.float64) - p[None, :, :]) ** 2).sum(axis=2))
    pos = np.diag(d).copy()
    np.fill_diagonal(d, np.inf)
    return float(np.maximum(0.0, margin + pos - d.min(axis=1)).mean())


@c.test("TODO 9: train() — one row per epoch, it learns, it uses lr, the validation loss is measured at the end",
        hint="Lab Step 9 and its hints: Adam(model.parameters(), lr); per epoch a new seeded torch.randperm, batches of "
             "`batch` (skip < 2), loss → zero_grad → backward → step; then model.eval() and torch.no_grad() for the "
             "validation loss in batches of `batch`; one dict per epoch.")
def _():
    ld = module("navera_lite.learned_desc")
    (f,) = functions("learned_desc", "train")
    ta, tp = val_patches(192)
    va, vp = val_patches(256)
    va, vp = va[192:], vp[192:]
    ld.torch.manual_seed(5)
    net = go(ld.PatchNet)
    before = arr(go(ld.describe, net, va), "describe", (64, 64))
    hist = go(f, net, ld.to_tensor(ta), ld.to_tensor(tp), ld.to_tensor(va), ld.to_tensor(vp), epochs=0, lr=1e-3,
              batch=32, seed=1, device="cpu")
    if not isinstance(hist, list):
        raise CheckFailed(f"train() must return a list (the history), got {type(hist).__name__}")
    c.ok(len(hist) == 0, f"with epochs = 0, the history must be empty, got {len(hist)} rows — use the epochs argument")
    still = arr(go(ld.describe, net, va), "describe", (64, 64))
    c.ok(np.allclose(before, still, atol=1e-6), "with epochs = 0 the model changed: only the epochs loop may train")
    hist = go(f, net, ld.to_tensor(ta), ld.to_tensor(tp), ld.to_tensor(va), ld.to_tensor(vp), epochs=2, lr=0.0,
              batch=32, seed=1, device="cpu", seconds=120)
    still = arr(go(ld.describe, net, va), "describe", (64, 64))
    c.ok(np.allclose(before, still, atol=1e-5), "with lr = 0 the weights still changed: give lr to the optimiser "
         "(torch.optim.Adam(model.parameters(), lr=lr))")
    log_rows = []
    hist = go(f, net, ld.to_tensor(ta), ld.to_tensor(tp), ld.to_tensor(va), ld.to_tensor(vp), epochs=3, lr=3e-3,
              batch=32, seed=1, device="cpu", log=log_rows.append, seconds=120)
    if not isinstance(hist, list) or len(hist) != 3:
        raise CheckFailed(f"with epochs = 3 the history must have 3 rows, got {hist!r:.200}")
    for i, row in enumerate(hist):
        if not isinstance(row, dict) or not {"epoch", "train_loss", "val_loss"} <= set(row):
            raise CheckFailed(f"row {i} of the history must be a dict with epoch, train_loss, val_loss: got {row!r:.120}")
        for k in ("train_loss", "val_loss"):
            if isinstance(row[k], bool) or not isinstance(row[k], (int, float)):
                raise CheckFailed(f"history[{i}][{k!r}] must be a float (loss.item()), got {type(row[k]).__name__}")
    c.ok([int(r["epoch"]) for r in hist] == [1, 2, 3], f"the epochs must be numbered 1, 2, 3, got {[r['epoch'] for r in hist]}")
    c.ok(len(log_rows) == 3, f"log(row) must be called once per epoch (it was called {len(log_rows)} times)")
    after = arr(go(ld.describe, net, va), "describe", (64, 64))
    c.ok(not np.allclose(before, after, atol=1e-5), "after 3 epochs with lr = 0.003 the model has not changed: "
         "opt.zero_grad(), loss.backward(), opt.step() in every batch")
    c.ok(hist[-1]["train_loss"] < hist[0]["train_loss"], f"the training loss did not go down over 3 epochs "
         f"({[round(r['train_loss'], 4) for r in hist]}): is opt.zero_grad() called before every backward()?")
    want = np.mean([np_triplet(after[s:s + 32], arr(go(ld.describe, net, vp), "describe")[s:s + 32])
                    for s in range(0, 64, 32)])
    c.ok(abs(hist[-1]["val_loss"] - want) < 2e-3, f"the last val_loss is {hist[-1]['val_loss']:.4f}, but the validation "
         f"pairs give {want:.4f} with the trained model: measure it AFTER the epoch's batches, in model.eval() and "
         "torch.no_grad(), in batches of `batch`, averaged")


TEST_ORB, TEST_SIFT, NEED = 0.7178, 0.8252, 0.85


@c.test("Your trained network: my_desc.pt on 1 024 unseen pairs from places you never saw",
        hint="Lab Step 9: `python3 run_features.py train` (all pairs) saves my_desc.pt; on the CPU use --device cpu "
             "--n-train 4096 --epochs 4. Do not save overfit.pt as my_desc.pt.")
def _():
    import torch
    if not os.path.exists("my_desc.pt"):
        raise CheckFailed("my_desc.pt is missing: run `python3 run_features.py train` (Step 9)")
    if os.path.getsize("my_desc.pt") > 5_000_000:
        raise CheckFailed("my_desc.pt is larger than 5 MB: it should hold PatchNet's weights only (about 360 kB)")
    try:
        sd = torch.load("my_desc.pt", map_location="cpu", weights_only=True)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"my_desc.pt cannot be read as weights ({type(e).__name__}): save it with "
                          "torch.save(model.state_dict(), path) — the runner does")
    net = reference_net()
    try:
        net.load_state_dict(sd)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"my_desc.pt does not fit PatchNet's layers: {str(e).splitlines()[0][:200]}")
    d = np.load(io.BytesIO(hidden("patches_test.npz", text=False)))
    s = score(describe_ref(net, d["a"]), describe_ref(net, d["b"]))
    print(f"  your network on the hidden test pairs: matching score {s:.3f} (ORB {TEST_ORB:.3f}, SIFT {TEST_SIFT:.3f})")
    c.ok(s >= NEED, f"my_desc.pt scores {s:.3f} on the hidden test pairs (ORB {TEST_ORB:.3f}, SIFT {TEST_SIFT:.3f}); it "
         f"needs {NEED}. Train on all the pairs (not overfit.pt), or check `python3 run_features.py compare`.")


@c.test("Steps 6–11: Hamming medians, parameters, training, overfitting, learned vs OpenCV",
        hint="Copy the numbers printed by `hamming`, `train` and `compare` (three decimals); N_PARAMS_CONV1 is 16 filters × "
             "(1 × 3 × 3 weights + 1 bias). Explain in your own words.")
def _():
    import torch
    (hs, hr, why_h, pp, n1, vs, po, why_o, so, ss, su, sl, why_l) = answers(
        "HAMMING_SAME", "HAMMING_RANDOM", "EXPLAIN_HAMMING", "PREDICT_PARAMS", "N_PARAMS_CONV1", "VAL_SCORE_FULL",
        "PREDICT_OVERFIT", "EXPLAIN_OVERFIT", "SCORE_ORB", "SCORE_SIFT", "SCORE_UNTRAINED", "SCORE_LEARNED",
        "EXPLAIN_LEARNED")
    c.near(number(hs, "HAMMING_SAME"), 61, 1, "HAMMING_SAME (bits)")
    c.near(number(hr, "HAMMING_RANDOM"), 127, 1, "HAMMING_RANDOM (bits)")
    explained("EXPLAIN_HAMMING", why_h,
              ((r"half", r"128", r"random", r"coin", r"chance", r"50", r"independ"), "why random pairs differ in about 128 bits"),
              ((r"threshold", r"separat", r"distinguish", r"reject", r"match", r"tell", r"gap", r"nearest", r"recogni"),
               "what the gap allows"))
    predicted("PREDICT_PARAMS", pp)
    n1 = number(n1, "N_PARAMS_CONV1")
    if n1 == 144:
        raise CheckFailed("N_PARAMS_CONV1 = 144: the 16 biases count too")
    c.eq(int(n1), 160, "N_PARAMS_CONV1")
    predicted("PREDICT_OVERFIT", po)
    explained("EXPLAIN_OVERFIT", why_o,
              ((r"train", r"300"), "what the training loss did"),
              ((r"valid", r"val\b", r"unseen", r"new place", r"other place"), "what the validation loss did"),
              ((r"memor", r"by heart", r"overfit", r"too few", r"small", r"not general", r"specific", r"learn"), "why"))
    vs, so, ss, su, sl = (number(v, n) for v, n in ((vs, "VAL_SCORE_FULL"), (so, "SCORE_ORB"), (ss, "SCORE_SIFT"),
                                                      (su, "SCORE_UNTRAINED"), (sl, "SCORE_LEARNED")))
    if max(so, ss, su, sl, vs) > 1:
        raise CheckFailed("matching scores are shares from 0 to 1 (write 0.875, not 87.5)")
    c.near(so, 0.756, 0.0015, "SCORE_ORB")
    c.near(ss, 0.875, 0.0015, "SCORE_SIFT")
    c.ok(0.8 <= vs <= 1.0, f"VAL_SCORE_FULL = {vs}: the score printed at the end of the full training (Step 9)")
    c.ok(0.35 <= su <= 0.70, f"SCORE_UNTRAINED = {su}: the 'untrained' line of `compare`")
    if os.path.exists("my_desc.pt"):
        net = reference_net()
        try:
            net.load_state_dict(torch.load("my_desc.pt", map_location="cpu", weights_only=True))
            a, b = val_patches(2048)
            mine = score(describe_ref(net, a), describe_ref(net, b))
        except Exception:                                                   # noqa: BLE001
            mine = None
        if mine is not None:
            c.ok(abs(sl - mine) <= 0.003, f"SCORE_LEARNED = {sl}, but your my_desc.pt scores {mine:.3f} on the validation "
                 "pairs: run `compare` again after your last training and copy its line")
    explained("EXPLAIN_LEARNED", why_l,
              ((r"train", r"learn", r"data", r"same kind", r"these pair", r"synthetic", r"drawn", r"render"),
               "why it wins here"),
              ((r"real", r"camera", r"flight", r"test", r"measure", r"season", r"light", r"photo", r"frame"),
               "what you would need before trusting it on a drone"))


@c.test("report.md: four headings, your own words, your numbers",
        hint="Lab Step 12: keep the four ## headings, 180–450 words, replace every TODO, quote REP_SIFT_ZOOM4, both Hamming "
             "medians, and your learned and SIFT scores as numbers.")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## 1. The scout", "## 2. The detector", "## 3. Descriptors", "## 4. The learner"):
        c.ok(h in text, f"report.md lost its heading “{h}”")
    c.ok("TODO" not in text, "report.md still contains a TODO")
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    n = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body))
    c.ok(180 <= n <= 520, f"report.md has {n} words; write 180–450")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    has = lambda target, tol: any(abs(x - target) <= tol or abs(x - 100 * target) <= 100 * tol for x in nums)  # noqa: E731
    sz, hs, hr, ss, sl = answers("REP_SIFT_ZOOM4", "HAMMING_SAME", "HAMMING_RANDOM", "SCORE_SIFT", "SCORE_LEARNED")
    for v, name in ((sz, "REP_SIFT_ZOOM4"), (hs, "HAMMING_SAME"), (hr, "HAMMING_RANDOM"), (ss, "SCORE_SIFT"),
                    (sl, "SCORE_LEARNED")):
        v = number(v, name)
        c.ok(has(v, 0.006 if v < 1 else 0.6), f"report.md does not quote your {name} ({v:g})")


c.milestone("learner", "TODO", "Step", "Your trained", "report", label="Learner")

c.run()
