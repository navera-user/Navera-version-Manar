import json
import math
import os
import re

import cv2
import numpy as np

from academy_check import Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/21-matching"
TRUTH = json.load(open(os.path.join(DATA, "truth.json")))
_cache = {}


def G():
    return load_student("geometry.py")


def M():
    return load_student("matching.py")


def pair(name):
    return (cv2.imread(os.path.join(DATA, f"view_{name}.jpg")), cv2.imread(os.path.join(DATA, f"patch_{name}.jpg")))


def matched(name, method):
    if (name, method) not in _cache:
        (mv,) = need(M(), "match_views")
        r = mv(*pair(name), method=method)
        c.ok(isinstance(r, tuple) and len(r) == 3, f"match_views() should return (H, inliers, details), got {r!r}")
        _cache[(name, method)] = r
    return _cache[(name, method)]


class NoOpenCVHomography:
    """During a `with` block, OpenCV's own robust estimators raise: the code under test must use YOUR
    RANSAC (geometry.ransac_homography), not cv2.findHomography(..., cv2.RANSAC)."""
    NAMES = ("findHomography", "estimateAffine2D", "estimateAffinePartial2D")

    def __enter__(self):
        self.saved = {n: getattr(cv2, n) for n in self.NAMES if hasattr(cv2, n)}

        def forbidden(*a, **k):
            raise RuntimeError("cv2.findHomography / estimateAffine* is not allowed here: use your own RANSAC")
        for n in self.saved:
            setattr(cv2, n, forbidden)
        return self

    def __exit__(self, *exc):
        for n, f in self.saved.items():
            setattr(cv2, n, f)
        return False


def uses_opencv_ransac(func):
    import inspect
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        return False
    src = "\n".join(ln.split("#")[0] for ln in src.splitlines())   # comments do not count
    return bool(re.search(r"findHomography|estimateAffine|cv2\.(RANSAC|USAC|LMEDS|RHO)", src))


def H_sim(rot_deg, scale, tx=100.0, ty=50.0, persp=(0.0, 0.0)):
    a = math.radians(rot_deg)
    return np.array([[scale * math.cos(a), -scale * math.sin(a), tx],
                     [scale * math.sin(a), scale * math.cos(a), ty], [persp[0], persp[1], 1.0]])


def angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def check_pair(name, method, rot_tol, scale_tol, centre_tol, min_inl):
    H, inl, _ = matched(name, method)
    c.ok(H is not None, f"no homography found on '{name}' with method '{method}'")
    c.ok(int(inl) >= min_inl, f"only {inl} inliers on '{name}' ({method}); expected at least {min_inl}")
    (sp,) = need(G(), "similarity_params")
    p = sp(H)
    t = TRUTH[name]
    c.ok(angle_diff(p["rotation_deg"], t["rotation_deg"]) <= rot_tol,
         f"'{name}' ({method}): rotation {p['rotation_deg']:.2f}°, truth {t['rotation_deg']:.0f}° (± {rot_tol}°)")
    c.near(p["scale"], t["scale"], tol=scale_tol * t["scale"], what=f"the scale of '{name}' ({method})")
    w, h = 480, 360
    q = H @ np.array([w / 2.0, h / 2.0, 1.0])
    d = math.hypot(q[0] / q[2] - t["centre"][0], q[1] / q[2] - t["centre"][1])
    c.ok(d <= centre_tol, f"'{name}' ({method}): the view centre lands {d:.1f} px from the truth (max {centre_tol})")


@c.test("geometry.py runs its self-test without errors",
        hint="Run `python3 geometry.py` and read the last lines of the output.")
def _():
    code, out = sh("python3 geometry.py", timeout=60)
    c.ok(code == 0, "geometry.py stopped with an error:\n" + out[-600:])
    c.ok("not done yet" not in out, "geometry.py says some TODOs are not done yet:\n" + out[-600:])


@c.test("TODO 1 — apply_homography() divides by w'; reprojection_errors() gives one distance per pair",
        hint="Homogeneous coordinates: append a 1 to each point, multiply by H, divide x' and y' by w'.")
def _():
    apply_h, rep = need(G(), "apply_homography", "reprojection_errors")
    H = H_sim(30, 2.0, persp=(1e-3, -2e-3))
    pts = np.array([[0.0, 0.0], [10.0, 20.0], [300.0, -40.0]])
    ph = np.c_[pts, np.ones(3)] @ H.T
    want = ph[:, :2] / ph[:, 2:]
    got = np.asarray(apply_h(H, pts), float)
    c.ok(got.shape == (3, 2), f"apply_homography should return shape (3, 2), got {got.shape}")
    c.ok(np.allclose(got, want, atol=1e-6), f"apply_homography gives {got.round(3).tolist()}, expected "
                                            f"{want.round(3).tolist()} — did you divide by the third coordinate?")
    e = np.asarray(rep(H, pts, want + [[3.0, 4.0], [0, 0], [0, -2.0]]), float)
    c.ok(e.shape == (3,) and np.allclose(e, [5.0, 0.0, 2.0], atol=1e-6),
         f"reprojection_errors should be [5, 0, 2] here, got {e}")


@c.test("TODO 2 — normalise_points(): centroid at 0, mean distance √2, and T does the same thing",
        hint="T = [[s, 0, -s·cx], [0, s, -s·cy], [0, 0, 1]] with s = √2 / (mean distance to the centroid).")
def _():
    (norm,) = need(G(), "normalise_points")
    rng = np.random.default_rng(5)
    pts = rng.uniform([3.55e7, 2.6e7], [3.55e7 + 800, 2.6e7 + 800], (30, 2))
    r = norm(pts)
    c.ok(isinstance(r, tuple) and len(r) == 2, "normalise_points should return (pts_n, T)")
    pn, T = np.asarray(r[0], float), np.asarray(r[1], float)
    c.ok(pn.shape == (30, 2) and T.shape == (3, 3), f"shapes {pn.shape} and {T.shape}, expected (30, 2) and (3, 3)")
    c.ok(np.allclose(pn.mean(0), 0, atol=1e-6), f"the centroid of pts_n is {pn.mean(0)}, expected (0, 0)")
    c.near(np.linalg.norm(pn, axis=1).mean(), math.sqrt(2), tol=1e-6, what="the mean distance to the origin")
    viaT = (np.c_[pts, np.ones(30)] @ T.T)[:, :2]
    c.ok(np.allclose(viaT, pn, atol=1e-5), "T applied to pts does not give pts_n")


@c.test("TODO 3a — build_dlt_matrix(): two rows per pair, 9 columns, the rows of the course",
        hint="For (x, y) → (u, v): [-x, -y, -1, 0, 0, 0, u·x, u·y, u] and [0, 0, 0, -x, -y, -1, v·x, v·y, v].")
def _():
    (b,) = need(G(), "build_dlt_matrix")
    A = np.asarray(b(np.array([[2.0, 3.0], [1.0, 1.0]]), np.array([[5.0, 7.0], [0.0, 1.0]])), float)
    c.ok(A.shape == (4, 9), f"A has shape {A.shape}, expected (4, 9) for 2 pairs")
    c.ok(np.allclose(A[0], [-2, -3, -1, 0, 0, 0, 10, 15, 5]) and np.allclose(A[1], [0, 0, 0, -2, -3, -1, 14, 21, 7]),
         f"the two rows of the pair (2, 3) → (5, 7) are {A[:2].tolist()}")


@c.test("TODO 3b — dlt_homography(): exact from 4 noise-free pairs (with and without normalisation); "
        "ValueError with 3", hint="h is the LAST row of Vt from np.linalg.svd(A); reshape to 3x3; de-normalise "
                                  "with inv(T_dst) @ Hn @ T_src; divide by H[2, 2].")
def _():
    (dlt,) = need(G(), "dlt_homography")
    H = H_sim(-50, 1.3, 400, -80, (2e-4, 1e-4))
    src = np.array([[0.0, 0.0], [640.0, 0.0], [640.0, 480.0], [0.0, 480.0]])
    ph = np.c_[src, np.ones(4)] @ H.T
    dst = ph[:, :2] / ph[:, 2:]
    for norm in (True, False):
        He = np.asarray(dlt(src, dst, normalise=norm), float)
        c.ok(He.shape == (3, 3), f"dlt_homography should return a 3x3 matrix, got shape {He.shape}")
        c.ok(np.allclose(He / He[2, 2], H, atol=1e-6, rtol=1e-6),
             f"normalise={norm}: H found\n{np.round(He, 5)}\nexpected\n{np.round(H, 5)}")
        c.near(He[2, 2], 1.0, tol=1e-9, what="H[2, 2]")
    try:
        dlt(src[:3], dst[:3])
    except ValueError:
        return
    c.ok(False, "dlt_homography with 3 pairs should raise ValueError")


@c.test("TODO 3b — with normalisation the DLT stays accurate in global map pixels (~3.55e7)",
        hint="Normalise BOTH point sets with their own T, and de-normalise at the end. Without it, A is "
             "hopelessly ill-conditioned at these coordinates.")
def _():
    dlt, sp = need(G(), "dlt_homography", "synthetic_pairs")
    src, dst, H_true, _ = sp(n=300, outlier_ratio=0.0, noise_px=1.0, seed=3)
    grid = np.stack(np.meshgrid(np.linspace(0, 640, 9), np.linspace(0, 480, 7)), -1).reshape(-1, 2)
    rng = np.random.default_rng(0)
    errs = []
    off = 3.55e7
    for _ in range(40):
        i = rng.choice(300, 8, replace=False)
        He = np.asarray(dlt(src[i], dst[i] + off), float)
        a = np.c_[grid, np.ones(len(grid))]
        p, q = a @ He.T, a @ H_true.T
        errs.append(np.linalg.norm(p[:, :2] / p[:, 2:] - (q[:, :2] / q[:, 2:] + off), axis=1).mean())
    c.ok(np.median(errs) < 3.0, f"median error {np.median(errs):.1f} px at global coordinates (expected ~1.3 px)")


@c.test("TODO 4 — ransac_iterations(): N = ⌈log(1−p) / log(1−wˢ)⌉ and its special cases",
        hint="Round UP (math.ceil) and return an int; w = 1 needs 1 sample; w = 0 (or p not in (0, 1)) is a "
             "ValueError.")
def _():
    (ri,) = need(G(), "ransac_iterations")
    for (p, w, s), want in (((0.99, 0.5, 4), 72), ((0.99, 0.5, 2), 17), ((0.999, 0.5, 4), 108),
                            ((0.99, 0.3, 4), 567), ((0.99, 0.9, 2), 3)):
        got = ri(p, w, s)
        c.ok(isinstance(got, (int, np.integer)), f"ransac_iterations should return an int, got {got!r}")
        c.eq(int(got), want, f"ransac_iterations(p={p}, w={w}, s={s})")
    c.eq(int(ri(0.99, 1.0, 4)), 1, "ransac_iterations(0.99, 1.0, 4)")
    try:
        ri(0.99, 0.0, 4)
    except ValueError:
        return
    c.ok(False, "ransac_iterations(0.99, 0.0, 4) should raise ValueError (no inlier: no N is enough)")


@c.test("TODO 5 — ransac_homography(): finds the true H among 30 % outliers, same result every run",
        hint="Use rng = np.random.default_rng(seed). Inliers: reprojection error < threshold. Refit on all the "
             "inliers of the best sample at the end.")
def _():
    g = G()
    rh, sp, dlt = need(g, "ransac_homography", "synthetic_pairs", "dlt_homography")
    c.ok(not uses_opencv_ransac(rh), "ransac_homography() calls OpenCV's robust estimator: write the loop "
                                     "yourself (sample 4 pairs, your DLT, count inliers, keep the best)")
    src, dst, H_true, is_in = sp()
    calls = []

    def counting_dlt(*a, **k):
        calls.append(1)
        return dlt(*a, **k)
    g.dlt_homography = counting_dlt
    try:
        with NoOpenCVHomography():
            r = rh(src, dst, 3.0)
            n_full = len(calls)
            del calls[:]
            rh(src, dst, 3.0, max_iters=3)
            n_three = len(calls)
    except RuntimeError as e:
        c.ok(False, str(e))
    finally:
        g.dlt_homography = dlt
    c.ok(n_full >= 2, f"ransac_homography() called dlt_homography() {n_full} time(s): each sample (and the final "
                      "refit) must use YOUR DLT")
    c.ok(n_three <= 4, f"with max_iters=3, dlt_homography() was called {n_three} times (at most 3 samples + "
                       "1 refit): respect max_iters")
    c.ok(isinstance(r, tuple) and len(r) == 2, "ransac_homography should return (H, mask)")
    H, mask = r
    c.ok(H is not None, "no homography found")
    mask = np.asarray(mask).astype(bool)
    c.ok(mask.shape == (len(src),), f"the mask should have shape ({len(src)},), got {mask.shape}")
    agree = (mask == is_in).mean()
    c.ok(agree >= 0.97, f"the mask agrees with the true inliers on only {agree:.0%} of the pairs")
    grid = np.c_[np.stack(np.meshgrid(np.linspace(0, 640, 5), np.linspace(0, 480, 5)), -1).reshape(-1, 2), np.ones(25)]
    p, q = grid @ np.asarray(H, float).T, grid @ H_true.T
    e = np.linalg.norm(p[:, :2] / p[:, 2:] - q[:, :2] / q[:, 2:], axis=1).max()
    c.ok(e < 1.5, f"H is up to {e:.1f} px away from the true H on the image (expected < 1.5 px)")
    H2, m2 = rh(src, dst, 3.0)
    c.ok(np.array_equal(np.asarray(m2).astype(bool), mask), "two runs with the same seed gave different inliers")
    H3, m3 = rh(src[:3], dst[:3], 3.0)
    c.ok(H3 is None, "with 3 pairs there is no homography: H should be None")


@c.test("TODO 6 — similarity_params(): rotation, scale, anisotropy, perspective of known matrices",
        hint="SVD of A = H[:2, :2]: R = U @ Vt, scale = √|det A|, anisotropy = S[0] / S[1], perspective = "
             "length of (H[2, 0], H[2, 1]) after dividing H by H[2, 2].")
def _():
    (sp,) = need(G(), "similarity_params")
    p = sp(3.0 * H_sim(140.0, 2.0))
    for k, want in (("rotation_deg", 140.0), ("scale", 2.0), ("anisotropy", 1.0), ("perspective", 0.0), ("tx", 100.0)):
        c.ok(k in p, f"the dict has no key '{k}'")
        c.near(p[k], want, tol=1e-6 if k != "rotation_deg" else 1e-4, what=k)
    stretched = H_sim(0, 1.0) @ np.diag([2.0, 1.0, 1.0])
    q = sp(stretched)
    c.near(q["anisotropy"], 2.0, tol=1e-6, what="anisotropy of a 2:1 stretch")
    c.near(q["scale"], math.sqrt(2.0), tol=1e-6, what="scale of a 2:1 stretch (√det)")


@c.test("TODO 7 — ratio_test(): keeps a clear match, drops an ambiguous one and a lonely one",
        hint="Keep `best` only when best.distance < ratio * second.distance — use the `ratio` argument.")
def _():
    (rt,) = need(M(), "ratio_test")
    clear = [cv2.DMatch(0, 5, 100.0), cv2.DMatch(0, 9, 300.0)]
    ambiguous = [cv2.DMatch(1, 2, 200.0), cv2.DMatch(1, 3, 210.0)]
    alone = [cv2.DMatch(2, 4, 50.0)]
    out = rt([clear, ambiguous, alone], 0.8)
    c.ok(isinstance(out, list), f"ratio_test should return a list, got {out!r}")
    c.eq([(m.queryIdx, m.trainIdx) for m in out], [(0, 5)], "the matches kept with ratio 0.8")
    c.eq(len(rt([clear, ambiguous], 0.97)), 2, "the number kept with ratio 0.97")


@c.test("TODO 8 — match_views(method='opencv') on 'city' and 'olives': rotation ±0.5°, scale ±1 %, centre ±2 px",
        hint="ratio_test → (N, 2) float32 src/dst → cv2.findHomography(..., cv2.RANSAC, threshold) → boolean mask.")
def _():
    check_pair("city", "opencv", 0.5, 0.01, 2.0, 150)
    check_pair("olives", "opencv", 0.5, 0.01, 2.0, 150)
    _, _, det = matched("city", "opencv")
    c.ok(det.get("mask") is not None and np.asarray(det["mask"]).dtype == bool and len(det["mask"]) == len(det["good"]),
         "details['mask'] should be a boolean array with one value per good match")
    c.ok(np.asarray(det.get("src")).shape == (len(det["good"]), 2), "details['src'] should be an (N, 2) array")


@c.test("TODO 8 — match_views(method='mine') uses YOUR RANSAC: 'city', 'otherdate' right, 'sea' refused",
        hint="method 'mine' calls geometry.ransac_homography(src, dst, threshold). The sea has no keypoints: "
             "return (None, 0, details).")
def _():
    try:
        with NoOpenCVHomography():
            for name in ("city", "otherdate", "sea"):
                matched(name, "mine")
    except RuntimeError as e:
        c.ok(False, f"method 'mine' still uses OpenCV ({e})")
    check_pair("city", "mine", 0.5, 0.01, 2.0, 150)
    check_pair("otherdate", "mine", 3.0, 0.05, 6.0, 10)
    H, inl, _ = matched("sea", "mine")
    c.ok(H is None or int(inl) < 8, f"a match on open water with {inl} inliers? It cannot be right")


@c.test("TODO 9 — trust(): NAVERA's gates, each with its own reason",
        hint="In order: no H → inliers < min_inliers → rotation (wrapped difference) → |scale/expected − 1| → "
             "inlier_spread(). Return (False, reason) or (True, 'ok').")
def _():
    (tr,) = need(M(), "trust")
    shape = (360, 480, 3)
    everywhere = np.array([[x, y] for x in range(30, 480, 60) for y in range(30, 360, 60)], float)
    one_strip = np.array([[x, 10.0] for x in range(5, 120, 5)], float)
    H = H_sim(30.0, 0.8)
    cases = [((None, everywhere, shape, 0.8), False, "homography"),
             ((H, everywhere[:5], shape, 0.8), False, "inliers"),
             ((H, everywhere, shape, 0.8, -150.0), False, "rotation"),
             ((H, everywhere, shape, 1.2), False, "scale"),
             ((H, one_strip, shape, 0.8), False, "spread"),
             ((H, everywhere, shape, 0.8, 30.0), True, ""),
             ((H, everywhere, shape, 0.8, 30.0 + 350.0), True, "")]       # 380° wraps to 20°: 10° away
    for args, ok, word in cases:
        r = tr(*args)
        c.ok(isinstance(r, tuple) and len(r) == 2, f"trust() should return (ok, reason), got {r!r}")
        c.ok(bool(r[0]) is ok, f"trust{('(H=None' if args[0] is None else '(H')}, {len(args[1])} inliers, "
                               f"expected scale {args[3]}{', heading ' + str(args[4]) if len(args) > 4 else ''}) "
                               f"returned {r[0]!r}, expected {ok}")
        c.ok(word.lower() in str(r[1]).lower(), f"the reason {r[1]!r} should mention '{word}'")


@c.test("results.json was written by experiments.py and holds your measurements",
        hint="Run `python3 experiments.py` once every TODO works (about 30 s).")
def _():
    c.file_exists("results.json")
    r = json.load(open("results.json"))
    for k in ("ransac_N", "monte_carlo", "normalisation", "pairs", "ratio_sweep"):
        c.ok(k in r, f"results.json has no '{k}' — run experiments.py again")
    c.eq(r["ransac_N"]["s4"]["0.5"], 72, "ransac_N s4 w=0.5")
    c.ok(abs(r["monte_carlo"]["success_rate"] - 0.99) < 0.01, f"monte_carlo success_rate {r['monte_carlo']['success_rate']}")
    g = r["normalisation"]["global_px"]
    c.ok(g["median_err_normalised_px"] < 3 < g["median_err_raw_px"],
         f"normalisation in global pixels: {g['median_err_normalised_px']} px normalised vs "
         f"{g['median_err_raw_px']} px raw — expected the normalised one small and the raw one large")
    c.ok(r["pairs"]["city"]["mine"].get("centre_error_px", 99) < 2, "your RANSAC misses the city centre in results.json")
    c.ok(r["ratio_sweep"]["1.0"]["trusted"] is False, "with ratio 1.0 the 'otherdate' match should not be trusted")


@c.test("analysis.md: five sections of at least 40 words, with the RANSAC numbers",
        hint="Replace every line starting with '>' by your own text. Section 3 must quote N for s = 4 and s = 2 "
             "(p = 0.99, w = 0.5).")
def _():
    c.file_exists("analysis.md")
    txt = open("analysis.md", encoding="utf-8").read()
    parts = re.split(r"^##\s+", txt, flags=re.M)[1:]
    want = ["ratio test", "normalisation", "ransac iterations", "opencv vs mine", "trust gates"]
    found = {}
    for p in parts:
        title, _, body = p.partition("\n")
        for w in want:
            if w in title.lower().replace("normalization", "normalisation"):
                found[w] = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith(">"))
    for w in want:
        c.ok(w in found, f"no section '## … {w.title()}' in analysis.md")
        n = len(re.findall(r"[A-Za-z0-9.,%²√≈]+", found[w]))
        c.ok(n >= 40, f"the section '{w}' has {n} words of your own (min 40)")
    nums = re.findall(r"\d+", found["ransac iterations"])
    c.ok("72" in nums and "17" in nums, "the section 'RANSAC iterations' should give N = 72 (s = 4) and N = 17 (s = 2)")


c.run()
