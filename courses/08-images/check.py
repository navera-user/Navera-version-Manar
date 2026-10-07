import json
import os
import re

import numpy as np

from academy_check import Checker, load_student, need, sh

c = Checker()
D = "/data/academy/08-images/"


def lab():
    return load_student("images_lab.py")


def arr(v, what):
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    c.ok(isinstance(v, np.ndarray), f"{what} should return a numpy array, got {type(v).__name__}")
    return v


def u8(v, what):
    v = arr(v, what)
    c.ok(v.dtype == np.uint8, f"{what} returned dtype {v.dtype}, but it must return uint8 "
                              f"(convert with to_uint8() — round, clip, astype — before returning)")
    return v


def f32(v, what):
    v = arr(v, what)
    c.ok(v.dtype == np.float32, f"{what} returned dtype {v.dtype}, expected float32 (compute with .astype(np.float32))")
    return v


def photo_gray():
    import cv2
    return cv2.cvtColor(cv2.imread(D + "drone_photo.jpg"), cv2.COLOR_BGR2GRAY)


@c.test("to_uint8(): rounds, clips to 0..255 BEFORE converting, returns uint8",
        hint="np.clip(np.rint(a), 0, 255).astype(np.uint8). If you convert first, 300 becomes 44 (300 − 256).")
def _():
    (f,) = need(lab(), "to_uint8")
    r = u8(f(np.array([-5.6, 0.4, 99.5, 254.6, 300.0, 1e6])), "to_uint8()")
    c.eq(r.tolist(), [0, 0, 100, 255, 255, 255], what="to_uint8([-5.6, 0.4, 99.5, 254.6, 300, 1e6])")


@c.test("to_gray(): pure blue, green, red → 29, 150, 76; equal to cv2.cvtColor (± 1); a grey picture is unchanged",
        hint="OpenCV images are BGR: img[..., 0] is BLUE. Y = 0.114·B + 0.587·G + 0.299·R, in float32, then to_uint8().")
def _():
    import cv2
    (f,) = need(lab(), "to_gray")
    img = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], np.uint8)
    g = u8(f(img), "to_gray()")
    c.eq(g.shape, (1, 4), what="the shape of the grey picture")
    c.ok(all(abs(int(a) - b) <= 1 for a, b in zip(g[0], [29, 150, 76, 255])), f"grey values are {g[0].tolist()}, expected [29, 150, 76, 255]")
    photo = cv2.imread(D + "drone_photo.jpg")
    diff = np.abs(u8(f(photo), "to_gray(photo)").astype(int) - cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)).max()
    c.ok(diff <= 1, f"to_gray(photo) differs from cv2.cvtColor by up to {diff} grey levels")
    grey = np.arange(12, dtype=np.uint8).reshape(3, 4)
    c.ok(np.array_equal(u8(f(grey), "to_gray(grey)"), grey), "a picture that is already grey must come back unchanged")


@c.test("histogram(): 256 counts that add up to the number of pixels",
        hint="np.bincount(gray.ravel(), minlength=256) — minlength makes sure there are 256 bins even if 255 never appears.")
def _():
    (f,) = need(lab(), "histogram")
    g = np.array([[0, 0, 7], [7, 7, 200]], np.uint8)
    h = arr(f(g), "histogram()")
    c.eq(len(h), 256, what="the number of bins")
    c.ok(h[0] == 2 and h[7] == 3 and h[200] == 1 and int(h.sum()) == 6, f"wrong counts: h[0]={h[0]}, h[7]={h[7]}, h[200]={h[200]}")
    p = photo_gray()
    c.eq(int(arr(f(p), "histogram(photo)").sum()), p.size, what="the sum of the histogram of the photo")


@c.test("normalise(): darkest → 0, brightest → 255, result is uint8; a uniform picture is unchanged",
        hint="(g − min) / (max − min) × 255 is float64 (or float32): the result must go through to_uint8(). "
             "If max == min, return the picture unchanged (no division by zero).")
def _():
    (f,) = need(lab(), "normalise")
    r = u8(f(np.array([[50, 100], [150, 50]], np.uint8)), "normalise()")
    c.ok(r.tolist() == [[0, 128], [255, 0]], f"normalise([[50, 100], [150, 50]]) gave {r.tolist()}, expected [[0, 128], [255, 0]]")
    flat = np.full((3, 3), 7, np.uint8)
    c.ok(np.array_equal(u8(f(flat), "normalise(uniform)"), flat), "a uniform picture should come back unchanged")


@c.test("equalise(): the same result as cv2.equalizeHist (± 1), uint8",
        hint="cdf = np.cumsum(histogram(g)); cdf_min = the first non-zero cdf value; "
             "lut = to_uint8((cdf − cdf_min) / (N − cdf_min) × 255); return lut[g] (numpy indexing with an array).")
def _():
    import cv2
    (f,) = need(lab(), "equalise")
    for g in (photo_gray(), np.array([[10, 10, 20], [30, 30, 30]], np.uint8)):
        r = u8(f(g), "equalise()")
        c.eq(r.shape, g.shape, what="the shape of equalise()")
        d = int(np.abs(r.astype(int) - cv2.equalizeHist(g)).max())
        c.ok(d <= 1, f"equalise() differs from cv2.equalizeHist by up to {d} grey levels")


@c.test("equalise(): a uniform picture (one grey value) comes back unchanged, with no warning",
        hint="In a uniform picture every pixel has the same value, so cdf_min == N and (cdf − cdf_min) / (N − cdf_min) "
             "is 0 / 0 (RuntimeWarning: invalid value encountered in divide). Test N == cdf_min first and "
             "return a copy of the picture, as normalise() does when max == min.")
def _():
    import warnings
    (f,) = need(lab(), "equalise")
    flat = np.full((4, 5), 90, np.uint8)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with np.errstate(all="warn"):
            r = u8(f(flat.copy()), "equalise(uniform)")
    c.ok(np.array_equal(r, flat), f"equalise() of a 4 × 5 picture full of 90 gave {np.unique(r).tolist()} — "
                                  "a uniform picture should come back unchanged (all 90)")
    bad = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
    c.ok(not bad, f"equalise() of a uniform picture printed a RuntimeWarning: {bad[0] if bad else ''}")


@c.test("convolve2d(): identity kernel, TRUE convolution (flipped kernel), reflect-101 border, float32, = OpenCV",
        hint="np.pad(img, ((r, r), (r, r)), mode='reflect') is OpenCV's BORDER_REFLECT_101. Flip with kernel[::-1, ::-1], "
             "then add k[i, j] · padded[i:i+H, j:j+W] for every (i, j). With a 1 on the LEFT of the centre, a true "
             "convolution reads the RIGHT neighbour: out[y, x] = img[y, x + 1] (a correlation would read x − 1).")
def _():
    import cv2
    (f,) = need(lab(), "convolve2d")
    img = np.arange(30, dtype=np.uint8).reshape(5, 6) * 7
    delta = np.zeros((3, 3), np.float32)
    delta[1, 1] = 1
    r = f32(f(img, delta), "convolve2d(img, identity)")
    c.ok(np.allclose(r, img), "the identity kernel (a single 1 in the middle) must give the picture back")
    left = np.zeros((3, 3), np.float32)
    left[1, 0] = 1                                   # true convolution with this kernel: out[y, x] = img[y, x + 1]
    r = f(img, left)
    c.ok(np.allclose(r[:, :-1], img[:, 1:]), "with a 1 LEFT of the centre, a true convolution gives out[y, x] = "
                                             "img[y, x + 1] — did you flip the kernel?")
    c.near(float(r[0, 5]), float(img[0, 4]), tol=1e-4, what="out[0, 5] (border 'reflect 101' reads img[0, 4])")
    g = photo_gray()
    k = np.random.default_rng(1).normal(size=(5, 5)).astype(np.float32)
    ref = cv2.filter2D(g.astype(np.float32), -1, np.ascontiguousarray(k[::-1, ::-1]), borderType=cv2.BORDER_REFLECT_101)
    d = float(np.abs(f(g, k) - ref).max())
    c.ok(d < 1e-2, f"convolve2d(photo, random 5 x 5) differs from OpenCV by up to {d:.4g}")


@c.test("gaussian_kernel(): sums to 1, equals OpenCV's for (5, σ = 1.2) and for (11, σ = 0 → OpenCV's rule)",
        hint="x = np.arange(k) − (k − 1)/2; g = np.exp(−x² / (2σ²)); g /= g.sum(); np.outer(g, g). "
             "If sigma <= 0: sigma = 0.3·((k − 1)·0.5 − 1) + 0.8.")
def _():
    import cv2
    (f,) = need(lab(), "gaussian_kernel")
    for k, s in ((5, 1.2), (11, 0.0), (3, 0.6)):
        g = arr(f(k, s), f"gaussian_kernel({k}, {s})")
        c.eq(g.shape, (k, k), what=f"the shape of gaussian_kernel({k}, {s})")
        c.near(float(g.sum()), 1.0, tol=1e-5, what=f"the sum of gaussian_kernel({k}, {s})")
        one = cv2.getGaussianKernel(k, s)
        d = float(np.abs(g - one @ one.T).max())
        c.ok(d < 1e-6, f"gaussian_kernel({k}, {s}) differs from OpenCV's by {d:.3g}")


@c.test("sobel(): gx, gy equal cv2.Sobel(gray, cv2.CV_32F, 1, 0) and (0, 1), float32",
        hint="cv2.Sobel correlates with [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]; your convolve2d flips the kernel, so give it "
             "the flipped one. gy uses the transpose. On a ramp that gets brighter to the right, gx must be POSITIVE.")
def _():
    import cv2
    (f,) = need(lab(), "sobel")
    ramp = np.tile(np.arange(0, 80, 10, dtype=np.uint8), (6, 1))
    r = f(ramp)
    c.ok(r is not None and len(r) == 2, "sobel() must return the pair (gx, gy)")
    gx, gy = f32(r[0], "gx"), f32(r[1], "gy")
    c.ok(gx[3, 3] > 0 and abs(float(gy[3, 3])) < 1e-6, f"on a ramp brighter to the right: gx = {gx[3, 3]} (should be +80), gy = {gy[3, 3]} (0)")
    g = photo_gray()
    gx, gy = f(g)
    d = max(float(np.abs(gx - cv2.Sobel(g, cv2.CV_32F, 1, 0)).max()), float(np.abs(gy - cv2.Sobel(g, cv2.CV_32F, 0, 1)).max()))
    c.ok(d < 1e-2, f"sobel(photo) differs from cv2.Sobel by up to {d:.4g}")


@c.test("rotation_scale_matrix() equals cv2.getRotationMatrix2D (2 × 3)",
        hint="a = s·cos θ, b = s·sin θ (θ in radians): [[a, b, (1 − a)·cx − b·cy], [−b, a, b·cx + (1 − a)·cy]]. "
             "Positive angles turn counter-clockwise on screen because the y axis points down.")
def _():
    import cv2
    (f,) = need(lab(), "rotation_scale_matrix")
    for args in ((320.0, 240.0, 30.0, 0.7), (50.0, 20.0, -35.0, 1.0), (0.0, 0.0, 90.0, 2.0), (199.5, 149.5, 212.3, 0.62)):
        m = arr(f(*args), "rotation_scale_matrix()")
        c.eq(m.shape, (2, 3), what="the shape of the matrix")
        ref = cv2.getRotationMatrix2D(args[:2], args[2], args[3])
        c.ok(np.allclose(m, ref, atol=1e-9), f"rotation_scale_matrix{args} = {np.round(m, 4).tolist()}, OpenCV gives {np.round(ref, 4).tolist()}")


@c.test("warp_affine(): identity gives the picture back, = cv2.warpAffine (mean diff < 0.25), outside = 0, float32",
        hint="Inverse mapping: for each output pixel (u, v), source = A⁻¹·((u, v) − t) with A = M[:, :2], t = M[:, 2]. "
             "Bilinear: weights (1 − fx)(1 − fy), fx(1 − fy), (1 − fx)fy, fx·fy on the 4 neighbours from _get().")
def _():
    import cv2
    (f,) = need(lab(), "warp_affine")
    g = photo_gray()
    r = f32(f(g, np.array([[1.0, 0, 0], [0, 1.0, 0]]), g.shape[1], g.shape[0]), "warp_affine(identity)")
    c.ok(np.allclose(r, g, atol=1e-3), "the identity matrix must give the picture back")
    m = cv2.getRotationMatrix2D((320, 240), 30, 0.7)
    r = f(g, m, 640, 480)
    c.eq(r.shape, (480, 640), what="the shape (out_h, out_w) of the result")
    d = np.abs(np.clip(np.rint(r), 0, 255) - cv2.warpAffine(g, m, (640, 480), flags=cv2.INTER_LINEAR).astype(np.float32))
    c.ok(float(d.mean()) < 0.25 and float(d.max()) <= 8, f"differs from cv2.warpAffine: mean {d.mean():.3f}, max {d.max():.0f}")
    c.ok(float(np.abs(r[:15, :15]).max()) == 0.0, "pixels that come from outside the source must be 0")


INFO = json.load(open(D + "info.json"))


def prepared(method="normalise"):
    import cv2
    (f,) = need(lab(), "make_like_map")
    photo = cv2.imread(D + INFO["photo"]["file"])
    r = f(photo, INFO["photo"]["heading_deg"], INFO["photo"]["m_per_px"], INFO["map"]["m_per_px"])
    c.ok(r is not None, "make_like_map() returned None — the TODO is not done yet")
    return np.asarray(r)


def map_mid(normalised):
    import cv2
    g = cv2.cvtColor(cv2.imread(D + INFO["map"]["file"]), cv2.COLOR_BGR2GRAY).astype(np.float32)
    if normalised:
        g = (g - g.min()) / (g.max() - g.min()) * 255.0
    return middle(g)


def middle(img, s=160):
    h, w = img.shape[:2]
    c.ok(h >= s and w >= s, f"the result ({w} × {h}) is too small to compare its {s} × {s} middle with the map")
    return img[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s].astype(np.float32)


@c.test("make_like_map(): a grey picture at the map's scale (≈ 397 × 298 px)",
        hint="The scale factor is photo_m_per_px / map_m_per_px (0.6 / 0.968 ≈ 0.62): the photo gets smaller. "
             "The output size is (round(w·s), round(h·s)).")
def _():
    r = prepared()
    c.eq(r.ndim, 2, what="the number of dimensions (grey = 2)")
    h, w = r.shape
    c.ok(abs(h - 298) <= 2 and abs(w - 397) <= 2, f"the result is {w} × {h} px, expected about 397 × 298")


@c.test("make_like_map(): the result is uint8 (a picture), not float",
        hint="Only the dtype is wrong here — your rotation and scale can be right. warp_affine() returns float32 "
             "and normalise() must return uint8: pass the final result through to_uint8().")
def _():
    r = prepared()
    c.ok(r.dtype == np.uint8, f"make_like_map() returned dtype {r.dtype}")


@c.test("make_like_map(): north up — its middle matches the map (similarity > 0.9)",
        hint="(This check ignores the dtype.) The photo's top points 35° clockwise from north. rotation_scale_matrix() "
             "turns counter-clockwise for positive angles: which sign brings north back to the top? Also check that "
             "the photo centre lands at the output centre (shift M by (out_w − w)/2, (out_h − h)/2).")
def _():
    a, b = middle(prepared()), map_mid(False)
    a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
    sim = float((a * b).sum() / max(1e-9, np.sqrt((a * a).sum() * (b * b).sum())))
    c.ok(sim > 0.9, f"similarity with the map is {sim:.2f} (it should be above 0.9)")


@c.test("make_like_map(): contrast normalised — mean difference with the normalised map < 25",
        hint="(This check ignores the dtype.) The photo is darker and duller than the map: normalise() the grey photo "
             "BEFORE the warp, so the black corners added by the rotation do not count as 'the darkest pixel'.")
def _():
    a, b = np.clip(middle(prepared()), 0, 255), map_mid(True)
    diff = float(np.abs(a - b).mean())
    c.ok(diff < 25, f"mean difference with the map is {diff:.1f} (it should be below 25)")


RES = {}


@c.test("python3 analysis.py runs; results.json: best heading 35°, best 0.60 m/px, your filters = OpenCV",
        hint="Run `python3 analysis.py` and read the error, if any. It needs TODO 1–11.")
def _():
    code, out = sh("python3 analysis.py", timeout=100)
    c.ok(code == 0, "analysis.py stopped with an error:\n" + out[-700:])
    RES.update(json.load(open("results.json")))
    c.eq(RES.get("best_heading_deg"), 35, what="best_heading_deg")
    c.near(RES.get("best_photo_m_per_px"), 0.6, tol=0.005, what="best_photo_m_per_px")
    c.ok(RES["convolution"]["gaussian_max_abs_diff"] < 1e-2, "your Gaussian convolution differs from OpenCV's")
    c.ok(RES["warp"]["mean_abs_diff"] < 0.25, "your warp differs from cv2.warpAffine")
    c.near(RES["similarity"]["normalise"], 0.975, tol=0.01, what="similarity.normalise")
    c.file_exists("analysis.png")


def numbers(text):
    return [float(v) for v in re.findall(r"\d+(?:\.\d+)?", text)]


@c.test("report.md: three sections, at least 150 words, and the key numbers quoted",
        hint="Headings '## Convolution', '## Preprocessing', '## Geometry'. Quote the similarity of the raw photo and "
             "after normalise (e.g. 0.06 and 0.975), the best heading (35) and the best photo m/px (0.60).")
def _():
    c.file_exists("report.md")
    text = re.sub(r"<!--.*?-->", "", open("report.md", encoding="utf-8").read(), flags=re.S)
    for h in ("## Convolution", "## Preprocessing", "## Geometry"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    words = re.findall(r"[A-Za-z]{2,}", text)
    c.ok(len(words) >= 150, f"report.md has only {len(words)} words of your own (at least 150 expected)")
    found = numbers(text)
    for want, tol, name in [(0.063, 0.011, "the similarity of the raw photo (≈ 0.06)"),
                            (0.975, 0.006, "the similarity after normalise (≈ 0.975)"),
                            (35, 0, "the best heading (35)"), (0.6, 0.005, "the best photo m/px (0.60)")]:
        c.ok(any(abs(v - want) <= tol for v in found), f"report.md does not quote {name}")

c.run()
