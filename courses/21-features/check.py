import json
import os
import re

import cv2
import numpy as np

from academy_check import Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/21-features"
# SIFT keypoints per terrain (OpenCV 4.11, these exact pictures, nfeatures=10000)
EXPECTED = {"city": 6626, "olives": 5852, "farms": 3983, "hills": 2571, "coast_water": 5, "sea": 0}


def img(name, flag=cv2.IMREAD_COLOR):
    return cv2.imread(os.path.join(DATA, name), flag)


def F():
    return load_student("features.py")


def square(size=200, lo=40, hi=200, a=60, b=139):
    im = np.full((size, size), lo, np.uint8)
    im[a:b + 1, a:b + 1] = hi
    return im


@c.test("features.py runs without errors",
        hint="Run `python3 features.py` in the terminal and read the last lines of the error.")
def _():
    code, out = sh("python3 features.py", timeout=60)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])


@c.test("TODO 0 — ORB_BYTES and SIFT_LENGTH are what you measured",
        hint="Run `python3 peek.py` and read the descriptor array shapes: (number of keypoints, length of one).")
def _():
    o, s = need(F(), "ORB_BYTES", "SIFT_LENGTH")
    c.eq(o, 32, "ORB_BYTES")
    c.eq(s, 128, "SIFT_LENGTH")


@c.test("TODO 1 — image_gradients(): a ramp I = 3x gives Ix = 3, Iy = 0; float32 arrays",
        hint="cv2.Sobel with the output depth cv2.CV_32F (not uint8: negative values would be cut to 0), "
             "dx=1,dy=0 for Ix and dx=0,dy=1 for Iy, then divide by SOBEL_NORM.")
def _():
    (grad,) = need(F(), "image_gradients")
    ramp = np.tile(np.arange(30, dtype=np.uint8) * 3, (30, 1))
    ix, iy = grad(ramp)
    c.ok(ix.dtype == np.float32 and ix.shape == ramp.shape, f"Ix should be float32 {ramp.shape}, got {ix.dtype} {ix.shape}")
    c.near(ix[15, 15], 3.0, 1e-4, "Ix in the middle of the ramp")
    c.near(iy[15, 15], 0.0, 1e-4, "Iy in the middle of the ramp")
    ix2, iy2 = grad(ramp.T.copy())          # the ramp going down: I = 3y
    c.near(iy2[15, 15], 3.0, 1e-4, "Iy of the ramp I = 3y")
    down = np.tile(np.arange(30, 0, -1, dtype=np.uint8)[:, None] * 2, (1, 30))  # brightness falls going down
    c.near(grad(down)[1][15, 15], -2.0, 1e-4, "Iy where brightness falls by 2 per row (a negative slope)")


@c.test("TODO 2 — harris_response(): flat = 0, ramp = -k·a⁴, a square's corner > 0 > its edge",
        hint="Sxx, Syy, Sxy are the Gaussian-weighted averages of Ix², Iy², Ix·Iy. "
             "det = Sxx·Syy − Sxy², trace = Sxx + Syy. All element-wise on whole arrays.")
def _():
    (hr,) = need(F(), "harris_response")
    flat = np.full((40, 40), 90, np.uint8)
    c.near(np.abs(hr(flat)).max(), 0.0, 1e-3, "max |R| on a flat picture")
    ramp = np.tile(np.arange(40, dtype=np.uint8) * 2, (40, 1))       # Ix = 2, Iy = 0 → R = -k·16
    r = hr(ramp, sigma=1.0, k=0.05)
    c.near(r[20, 20], -0.05 * 16, 1e-3, "R in the middle of the ramp I = 2x (k = 0.05)")
    r = hr(square())
    c.ok(r.shape == (200, 200), f"R should have the picture's shape (200, 200), got {r.shape}")
    corner, edge, inside = r[60, 60], r[100, 60], r[100, 100]
    c.ok(corner > 0 and edge < 0 and abs(inside) < 1e-3,
         f"at the square's corner R = {corner:.3g} (expected > 0), on its edge R = {edge:.3g} (expected < 0), "
         f"inside R = {inside:.3g} (expected 0)")


@c.test("TODO 2 — harris_response() on the city agrees with cv2.cornerHarris (correlation > 0.9)",
        hint="If the shape is right but the correlation is low, check the window (GaussianBlur of each "
             "product with sigma) and the formula det − k·trace².")
def _():
    (hr,) = need(F(), "harris_response")
    g = img("terrain_city.jpg", cv2.IMREAD_GRAYSCALE)
    r = np.asarray(hr(g), np.float64)
    ref = cv2.cornerHarris(g.astype(np.float32), 5, 3, 0.05)
    cc = float(np.corrcoef(r.ravel(), ref.ravel())[0, 1])
    c.ok(cc > 0.9, f"correlation with cv2.cornerHarris(blockSize=5) is {cc:.3f}, expected > 0.9")


@c.test("TODO 3 — harris_corners() finds the 4 corners of a square, strongest first, no duplicates",
        hint="Non-maximum suppression (lesson): a corner is a pixel equal to the maximum of its neighbourhood of "
             "radius r AND above rel_threshold times the strongest response. numpy gives (rows, columns) = (y, x), "
             "but the function returns (x, y); sort by decreasing response.")
def _():
    (hc,) = need(F(), "harris_corners")
    pts = np.asarray(hc(square(), n=4), np.float64)
    c.ok(pts.shape == (4, 2), f"harris_corners(square, n=4) should give an array (4, 2), got {pts.shape}")
    truth = np.array([[60, 60], [139, 60], [60, 139], [139, 139]], float)
    for t in truth:
        d = np.hypot(*(pts - t).T).min()
        c.ok(d <= 3.0, f"no corner found within 3 px of the true corner (x={t[0]:.0f}, y={t[1]:.0f}); "
                       f"your points: {np.round(pts).tolist()}")
    g = img("terrain_city.jpg", cv2.IMREAD_GRAYSCALE)
    p = np.asarray(hc(g, n=300, nms_radius=4), np.float64)
    c.ok(len(p) == 300, f"harris_corners(city, n=300) gave {len(p)} points")
    from scipy.spatial.distance import pdist
    c.ok(pdist(p).min() > 4.0, "two corners are closer than nms_radius: the non-maximum suppression is missing")
    (hr,) = need(F(), "harris_response")
    rr = hr(g)
    vals = [rr[int(y), int(x)] for x, y in p]
    c.ok(all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)), "the corners are not sorted strongest first")


@c.test("TODO 4 — characteristic_scale(): a disk of radius r answers σ ≈ r/√2 (r = 6 and 12)",
        hint="Scale-normalised: multiply the Laplacian by sigma² before comparing. Index the array as [y, x] "
             "(row first). Return the sigma itself, not its index.")
def _():
    (cs,) = need(F(), "characteristic_scale")
    sig = [1.0 * 1.08 ** i for i in range(40)]
    out = []
    for r in (6, 12):
        im = np.full((181, 181), 40, np.uint8)
        cv2.circle(im, (90, 90), r, 210, -1)
        s = cs(im, 90, 90, sig)
        out.append(s)
        c.near(s, r / 2 ** 0.5, 0.12 * r / 2 ** 0.5, f"characteristic_scale(disk of radius {r})")
    c.near(out[1] / out[0], 2.0, 0.25, "ratio of the two scales (the disk is twice as big)")


@c.test("TODO 5 — detect_keypoints(): ORB → (N, 32) uint8, SIFT → (N, 128) float32, other → ValueError",
        hint="cv2.ORB_create(nfeatures=max_points) / cv2.SIFT_create(nfeatures=max_points); convert BGR to grey "
             "only when img.ndim == 3; `raise ValueError(...)` for another name.")
def _():
    (det,) = need(F(), "detect_keypoints")
    res = det(img("terrain_city.jpg"), "ORB")
    c.ok(isinstance(res, tuple) and len(res) == 2, f"it should return (keypoints, descriptors), got {type(res).__name__}")
    kps, des = res
    c.ok(len(kps) > 1000, f"only {len(kps)} ORB keypoints on the city — expected thousands")
    c.ok(des is not None and des.shape == (len(kps), 32) and des.dtype == np.uint8,
         f"ORB descriptors should be ({len(kps)}, 32) uint8, got {None if des is None else (des.shape, des.dtype)}")
    kps, des = det(img("terrain_farms.jpg", cv2.IMREAD_GRAYSCALE), "SIFT")
    c.ok(des is not None and des.shape == (len(kps), 128) and des.dtype == np.float32,
         f"SIFT descriptors of a grey picture: {None if des is None else (des.shape, des.dtype)}")
    try:
        det(img("terrain_city.jpg"), "HARRIS-ROCKET")
    except ValueError:
        return
    c.ok(False, "detect_keypoints(img, 'HARRIS-ROCKET') did not raise ValueError")


@c.test("TODO 6 — hamming() counts different bits (agrees with cv2.norm NORM_HAMMING)",
        hint="np.bitwise_xor(a, b) leaves a 1 where the bits differ; np.unpackbits turns bytes into bits; sum them. "
             "Return a Python int.")
def _():
    (hm,) = need(F(), "hamming")
    a, b = np.array([0b10110000, 255], np.uint8), np.array([0b10010001, 0], np.uint8)
    c.eq(int(hm(a, b)), 2 + 8, "hamming([10110000, 11111111], [10010001, 00000000])")
    rng = np.random.default_rng(3)
    for _ in range(20):
        x, y = rng.integers(0, 256, 32, dtype=np.uint8), rng.integers(0, 256, 32, dtype=np.uint8)
        c.eq(int(hm(x, y)), int(cv2.norm(x, y, cv2.NORM_HAMMING)), "hamming of two random 32-byte descriptors")


@c.test("TODO 7 — project() applies H (also a perspective H); repeatability() on simple cases",
        hint="project: use homogeneous coordinates and do not forget the division by the third coordinate (a "
             "perspective H has a non-zero last row). repeatability: only A points that land INSIDE image B count, "
             "both in the numerator and in the denominator.")
def _():
    pr, rep = need(F(), "project", "repeatability")
    H = np.array([[2.0, 0, 10], [0, 2.0, -5], [0.001, 0, 1]])
    got = np.asarray(pr(np.array([[0.0, 0.0], [100.0, 50.0]]), H), float)
    want = np.array([[10.0, -5.0], [210.0 / 1.1, 95.0 / 1.1]])
    c.ok(got.shape == (2, 2) and np.allclose(got, want, atol=1e-6), f"project(...) = {np.round(got, 3).tolist()}, "
                                                                     f"expected {np.round(want, 3).tolist()}")
    a = np.array([[10.0, 10], [20, 20], [30, 30], [500, 500]])          # the last one falls outside B
    b = np.array([[10.5, 10], [40, 40], [30, 31.5]])
    c.near(rep(a, b, np.eye(3), (100, 100), eps=2.0), 2 / 3, 1e-6, "repeatability (2 of the 3 inside points found)")
    c.near(rep(a, b, np.eye(3), (100, 100), eps=0.1), 0.0, 1e-6, "repeatability with eps = 0.1")
    c.near(rep(np.array([[500.0, 500]]), b, np.eye(3), (100, 100)), 0.0, 1e-6, "repeatability when no point is inside")


@c.test("TODO 8 — spread() of keypoints in one corner is 1/16; spread evenly it is 1",
        hint="Cell column = int(x / width * columns), row = int(y / height * rows), kept inside the grid. "
             "Then (cells with ≥ min_per_cell) / (rows × columns).")
def _():
    (spread,) = need(F(), "spread")
    corner = [cv2.KeyPoint(float(5 + i), float(5 + i), 3) for i in range(20)]
    c.near(spread(corner, (400, 400, 3)), 1 / 16, tol=1e-6, what="spread(20 points in the top-left corner)")
    even = [cv2.KeyPoint(float(x), float(y), 3) for x in range(10, 400, 25) for y in range(10, 300, 25)]
    c.near(spread(even, (300, 400)), 1.0, tol=1e-6, what="spread(points everywhere on a 400 x 300 picture)")
    edge = [cv2.KeyPoint(399.9, 299.9, 3)] * 3
    c.near(spread(edge, (300, 400), grid=(2, 2)), 0.25, tol=1e-6, what="spread(3 points at the bottom-right, 2x2 grid)")


@c.test("TODO 8 — matchability(): land > 0.8, water < 0.1, clear photo > blurry dark one, half city/half sea ≈ 0.5",
        hint="Two factors multiplied: min(1, n / enough) with n ORB keypoints (max_points=500), and their spread.")
def _():
    (m,) = need(F(), "matchability")
    land = min(m(img(f"terrain_{k}.jpg")) for k in ("city", "olives", "farms", "hills"))
    water = max(m(img("terrain_coast_water.jpg")), m(img("terrain_sea.jpg")))
    c.ok(0.8 < land <= 1.0 and 0.0 <= water < 0.1, f"lowest land score {land:.2f} (expected > 0.8), "
                                                   f"highest water score {water:.2f} (expected < 0.1)")
    clear, bad = m(img("drone_city.jpg")), m(img("drone_city_blurry_dark.jpg"))
    c.ok(clear > 0.8 and bad < 0.1, f"drone_city {clear:.2f} (expected > 0.8), blurry dark {bad:.2f} (expected < 0.1)")
    a = img("terrain_city.jpg").copy()
    a[:, 256:] = img("terrain_sea.jpg")[:, 256:]
    s = m(a)
    c.ok(0.3 <= s <= 0.65, f"matchability(half city / half sea) = {s:.2f}, expected about 0.5")


def results():
    if not os.path.exists("results.json"):
        c.ok(False, "results.json does not exist yet — run `python3 measure.py`")
    try:
        return json.load(open("results.json"))
    except Exception as e:  # noqa: BLE001
        c.ok(False, f"results.json is not valid JSON: {e}")


@c.test("results.json — made by measure.py with your functions, and its numbers are right",
        hint="Run `python3 measure.py` again after your last change to features.py (it rewrites results.json).")
def _():
    r = results()
    for k in ("repeatability", "hamming_orb", "sift_per_terrain", "matchability"):
        c.ok(k in r, f"results.json has no '{k}': run measure.py again")
    rep = r["repeatability"]
    c.ok(set(rep) >= {"city_zoom4", "city_rot35", "olives_rot35_zoom"}, f"pairs in results.json: {sorted(rep)}")
    z4 = rep["city_zoom4"]
    c.ok(z4["sift"] > 0.6 and z4["harris"] < z4["sift"] - 0.2,
         f"city_zoom4: SIFT {z4['sift']}, Harris {z4['harris']} — expected SIFT well above Harris at scale x4")
    c.ok(all(0.05 < v["chance"] < 0.15 for v in rep.values()), "the chance level should be about 0.10 on every pair")
    hm = r["hamming_orb"]
    c.ok(hm["median_same_point"] < 100 < hm["median_random"] < 140,
         f"Hamming medians: same point {hm['median_same_point']}, random {hm['median_random']} "
         "(expected well below 100 and about 128)")
    for k, v in EXPECTED.items():
        c.near(r["sift_per_terrain"].get(k, -1), v, max(3, v * 0.05), f"SIFT keypoints of {k} in results.json")
    # one value recomputed now with the student's own code: results.json must be up to date
    (hc, rep_fn) = need(F(), "harris_corners", "repeatability")
    pairs = {p["name"]: p for p in json.load(open(os.path.join(DATA, "pairs.json")))}
    p = pairs["city_zoom4"]
    a, b = img(p["map"], cv2.IMREAD_GRAYSCALE), img(p["photo"], cv2.IMREAD_GRAYSCALE)
    now = rep_fn(hc(a, n=r.get("n_points", 1000)), hc(b, n=r.get("n_points", 1000)), np.array(p["H"]), b.shape,
                 r.get("eps_px", 3.0))
    c.near(z4["harris"], now, 0.02, "Harris repeatability of city_zoom4 in results.json vs recomputed now")


def section(text, title_words):
    """The text of the '## ' section whose title contains all title_words (lower case), or None."""
    parts = re.split(r"(?m)^##\s+", text)
    for p in parts[1:]:
        title = p.splitlines()[0].lower()
        if all(w in title for w in title_words):
            return p
    return None


def quotes(text, v):
    """Does text quote the fraction v (as 0.32 / .32 / 32 %)?"""
    forms = {f"{v:.2f}", f"{v:.2f}".lstrip("0")} | {f"{p} %" for p in range(round(v * 100) - 1, round(v * 100) + 2)} \
        | {f"{p}%" for p in range(round(v * 100) - 1, round(v * 100) + 2)}
    return any(f in text for f in forms)


@c.test("report.md — four sections, each answered with your own numbers",
        hint="Use the template of Step 9: '## 1. Scale', '## 2. Descriptors', '## 3. Terrain', '## 4. World'. "
             "Each section needs at least 40 words; quote the numbers from YOUR results.json "
             "(e.g. 0.32 or 32 %).")
def _():
    c.file_exists("report.md")
    t = open("report.md", encoding="utf-8").read()
    r = results()
    secs = {}
    for key, words in (("scale", ["scale"]), ("desc", ["descriptor"]), ("terrain", ["terrain"]), ("world", ["world"])):
        s = section(t, words)
        c.ok(s is not None, f"report.md has no section '## … {words[0].capitalize()} …'")
        n = len(re.findall(r"[A-Za-z]{2,}", s))
        c.ok(n >= 40, f"the section about '{words[0]}' has {n} words — at least 40 needed")
        c.ok("TODO" not in s, f"the section about '{words[0]}' still contains 'TODO'")
        secs[key] = s
    z4 = r["repeatability"]["city_zoom4"]
    c.ok(quotes(secs["scale"], z4["harris"]) and quotes(secs["scale"], z4["sift"]),
         f"section Scale: quote the city_zoom4 repeatability of Harris ({z4['harris']}) and SIFT ({z4['sift']})")
    hm = r["hamming_orb"]
    c.ok(str(int(round(hm["median_same_point"]))) in secs["desc"] and str(int(round(hm["median_random"]))) in secs["desc"],
         f"section Descriptors: quote both Hamming medians ({hm['median_same_point']:.0f} and {hm['median_random']:.0f} bits)")
    places = ("sahara", "namib", "atacama", "gobi", "kalahari", "greenland", "antarctic", "amazon", "atlantic",
              "pacific", "indian ocean", "mediterranean", "alps", "andes", "himalaya", "rockies", "wadden", "uyuni",
              "nile", "paris", "london", "singapore", "tokyo", "new york", "sydney", "cape town", "cairo", "sousse",
              "iceland", "siberia", "arctic")
    o = secs["world"].lower()
    c.ok(sum(p in o for p in places) >= 2, "section World: discuss at least two real places (e.g. the Sahara dunes, "
                                            "the open Atlantic, the Alps)")


c.run()
