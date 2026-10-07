import json
import os

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
    c.ok(v.dtype == np.uint8, f"{what} should give uint8 pixels (0..255), got dtype {v.dtype}")
    return v


@c.test("to_gray(): pure blue, green and red become 29, 150 and 76; a grey picture stays as it is",
        hint="Look at img.ndim: 3 dimensions = colour. OpenCV's colours are BGR: use cv2.COLOR_BGR2GRAY.")
def _():
    (f,) = need(lab(), "to_gray")
    img = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], np.uint8)   # 1 x 4, BGR
    g = u8(f(img), "to_gray()")
    c.eq(g.shape, (1, 4), what="the shape of the grey picture")
    want = [29, 150, 76, 255]
    c.ok(all(abs(int(a) - b) <= 1 for a, b in zip(g[0], want)), f"grey values are {g[0].tolist()}, expected {want}")
    grey = np.arange(12, dtype=np.uint8).reshape(3, 4)
    g = u8(f(grey), "to_gray(grey picture)")
    c.ok(g.shape == (3, 4) and np.array_equal(g, grey), "a picture that is already grey must come back unchanged")


@c.test("crop(img, x, y, w, h) cuts the right rectangle",
        hint="img[y : y + h, x : x + w] — rows (y) come first in numpy.")
def _():
    (f,) = need(lab(), "crop")
    a = np.arange(48, dtype=np.uint8).reshape(6, 8)
    r = arr(f(a, 2, 1, 3, 4), "crop()")
    c.eq(r.shape, (4, 3), what="the shape of crop(a, x=2, y=1, w=3, h=4)")
    c.ok(np.array_equal(r, a[1:5, 2:5]), "the pixels are not the right ones (did you swap x and y?)")
    col = np.zeros((6, 8, 3), np.uint8)
    c.eq(arr(f(col, 0, 0, 5, 2), "crop()").shape, (2, 5, 3), what="the shape of a colour crop")


@c.test("crop_center() cuts the middle of the picture",
        hint="Top-left corner: x = (width − w) // 2, y = (height − h) // 2. img.shape is (height, width…).")
def _():
    (f,) = need(lab(), "crop_center")
    a = np.arange(48, dtype=np.uint8).reshape(6, 8)
    r = arr(f(a, 4, 2), "crop_center()")
    c.eq(r.shape, (2, 4), what="the shape of crop_center(6 x 8 picture, w=4, h=2)")
    c.ok(np.array_equal(r, a[2:4, 2:6]), f"got {r.tolist()}, expected {a[2:4, 2:6].tolist()}")
    b = np.arange(63, dtype=np.uint8).reshape(7, 9)
    r = arr(f(b, 3, 3), "crop_center()")
    c.ok(np.array_equal(r, b[2:5, 3:6]), "the 3 x 3 middle of a 7 x 9 picture is not right")


@c.test("rotate(): 0° changes nothing, 90° turns counter-clockwise, the size stays the same",
        hint="M = cv2.getRotationMatrix2D((width / 2, height / 2), angle_deg, 1.0), then "
             "cv2.warpAffine(img, M, (width, height)). Positive angles turn counter-clockwise in OpenCV.")
def _():
    (f,) = need(lab(), "rotate")
    img = np.zeros((101, 101), np.uint8)
    img[49:52, 79:82] = 255                       # a bright dot RIGHT of the centre (x = 80, y = 50)
    r0 = u8(f(img, 0), "rotate(img, 0)")
    c.eq(r0.shape, img.shape, what="the shape after rotate(img, 0)")
    c.ok(int(np.abs(r0.astype(int) - img).max()) <= 1, "rotate(img, 0) should give the same picture back")
    r = u8(f(img, 90), "rotate(img, 90)")
    c.eq(r.shape, img.shape, what="the shape after rotate(img, 90)")
    c.ok(r.max() > 100, "after a 90° turn the bright dot has disappeared")
    ys, xs = np.nonzero(r > 100)
    y, x = ys.mean(), xs.mean()
    c.ok(abs(x - 50) <= 1.5 and abs(y - 20) <= 1.5,
         f"a dot right of the centre should go ABOVE the centre (x≈50, y≈20) when turning 90° "
         f"counter-clockwise; it went to x={x:.0f}, y={y:.0f}")
    col = np.zeros((40, 60, 3), np.uint8)
    c.eq(u8(f(col, 30), "rotate(colour)").shape, (40, 60, 3), what="the shape of a rotated colour picture")


@c.test("scale(): 0.5 halves the size, 2 doubles it, colours are kept",
        hint="cv2.resize(img, (new_width, new_height)) — the size is given as (WIDTH, HEIGHT), the opposite of img.shape.")
def _():
    (f,) = need(lab(), "scale")
    a = np.zeros((60, 100), np.uint8)
    c.eq(arr(f(a, 0.5), "scale()").shape, (30, 50), what="the shape of scale(60 x 100 picture, 0.5)")
    c.eq(arr(f(a, 2), "scale()").shape, (120, 200), what="the shape of scale(60 x 100 picture, 2)")
    b = np.zeros((61, 101, 3), np.uint8)
    c.eq(arr(f(b, 0.3), "scale()").shape, (18, 30, 3), what="the shape of scale(61 x 101 colour picture, 0.3)")


@c.test("adjust(): contrast and brightness, clipped to 0..255 (250 + 10 must give 255, not 4!)",
        hint="Convert to float first (img.astype(np.float32)), compute, np.clip(…, 0, 255), then .astype(np.uint8).")
def _():
    (f,) = need(lab(), "adjust")
    a = np.array([[250, 100, 10]], np.uint8)
    r = u8(f(a, 1.0, 10), "adjust(img, 1.0, 10)")
    c.eq(r.tolist(), [[255, 110, 20]], what="adjust([[250, 100, 10]], contrast 1.0, brightness 10)")
    r = u8(f(a, 2.0, 0), "adjust(img, 2.0, 0)")
    c.eq(r.tolist(), [[255, 200, 20]], what="adjust([[250, 100, 10]], contrast 2.0, brightness 0)")
    r = u8(f(a, 0.5, -20), "adjust(img, 0.5, -20)")
    c.eq(r.tolist(), [[105, 30, 0]], what="adjust([[250, 100, 10]], contrast 0.5, brightness -20)")


@c.test("normalise(): the darkest pixel becomes 0, the brightest 255",
        hint="(img − min) / (max − min) × 255, computed in float, then back to uint8. "
             "If max == min, return the picture unchanged (no division by zero!).")
def _():
    (f,) = need(lab(), "normalise")
    a = np.array([[50, 100], [150, 50]], np.uint8)
    r = u8(f(a), "normalise()")
    c.eq(r.shape, (2, 2), what="the shape")
    c.ok(r[0, 0] == 0 and r[1, 1] == 0 and r[1, 0] == 255 and abs(int(r[0, 1]) - 128) <= 1,
         f"normalise([[50, 100], [150, 50]]) gave {r.tolist()}, expected about [[0, 128], [255, 0]]")
    flat = np.full((3, 3), 7, np.uint8)
    r = u8(f(flat), "normalise(uniform picture)")
    c.ok(np.array_equal(r, flat), f"a uniform picture should come back unchanged, got {r.tolist()}")


@c.test("blur(): a uniform picture stays the same, a bright dot spreads out (more with a bigger window)",
        hint="cv2.GaussianBlur(img, (k, k), 0).")
def _():
    (f,) = need(lab(), "blur")
    flat = np.full((9, 9), 100, np.uint8)
    c.ok(np.array_equal(u8(f(flat, 3), "blur()"), flat), "blurring a uniform picture should not change it")
    dot = np.zeros((9, 9), np.uint8)
    dot[4, 4] = 255
    r3, r5 = u8(f(dot, 3), "blur(dot, 3)"), u8(f(dot, 5), "blur(dot, 5)")
    c.ok(0 < r3[4, 4] < 255 and r3[4, 5] > 0 and r3[3, 4] > 0, "with k = 3 the dot should get dimmer and spread to its neighbours")
    c.ok(r3[0, 0] == 0, "with k = 3 the far corner should stay black")
    c.ok(r5[4, 4] < r3[4, 4], "a 5 x 5 window should spread the dot more than a 3 x 3 one")


@c.test("edges(): finds the border between a black and a white half, and nothing on a uniform picture",
        hint="to_gray(img) → blur(…, 5) → cv2.Canny(…, low, high). Canny gives 0 or 255.")
def _():
    (f,) = need(lab(), "edges")
    img = np.zeros((40, 40, 3), np.uint8)
    img[:, 20:] = 255
    e = u8(f(img), "edges()")
    c.eq(e.shape, (40, 40), what="the shape of the edge map (one grey layer)")
    c.ok(set(np.unique(e).tolist()) <= {0, 255}, "an edge map should only contain 0 and 255")
    cols = np.nonzero(e.max(axis=0))[0]
    c.ok(len(cols) > 0, "no edge found between the black and the white halves")
    c.ok(cols.min() >= 17 and cols.max() <= 22, f"edges found in columns {cols.tolist()}, expected only near column 20")
    c.ok(u8(f(np.full((30, 30), 90, np.uint8)), "edges(uniform)").max() == 0, "a uniform picture has no edge")


def prepared():
    (f,) = need(lab(), "make_like_map")
    import cv2
    info = json.load(open(D + "info.json"))
    photo = cv2.imread(D + info["photo"]["file"])
    r = u8(f(photo, info["photo"]["heading_deg"], info["photo"]["m_per_px"], info["map"]["m_per_px"]),
           "make_like_map()")
    return r, cv2.imread(D + info["map"]["file"])


def middle(img, s=160):
    h, w = img.shape[:2]
    return img[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s].astype(np.float32)


@c.test("make_like_map() returns a grey picture at the map's scale (≈ 397 × 298 px)",
        hint="The photo has 0.6 m per pixel, the map 0.968: to reach the map's meters per pixel, "
             "scale by photo_m_per_px / map_m_per_px (it makes the photo smaller).")
def _():
    r, _m = prepared()
    c.eq(r.ndim, 2, what="the number of dimensions (grey = 2)")
    h, w = r.shape
    c.ok(abs(h - 298) <= 2 and abs(w - 397) <= 2, f"the result is {w} × {h} px, expected about 397 × 298")


@c.test("make_like_map() turns the photo north-up: its middle matches the map (similarity > 0.9)",
        hint="The photo's top points to 35° clockwise from north. rotate() turns counter-clockwise for "
             "positive angles… which sign brings north back to the top?")
def _():
    import cv2
    r, m = prepared()
    a, b = middle(r), middle(cv2.cvtColor(m, cv2.COLOR_BGR2GRAY))
    c.ok(a.shape == b.shape, "the result is too small to compare its 160 × 160 middle with the map")
    a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
    sim = float((a * b).sum() / max(1e-9, np.sqrt((a * a).sum() * (b * b).sum())))
    c.ok(sim > 0.9, f"similarity with the map is {sim:.2f} (it should be above 0.9)")


@c.test("make_like_map() normalises the brightness: difference with the normalised map < 25",
        hint="The photo is darker and duller than the map: normalise() the grey photo (before rotating, "
             "so the black corners do not count).")
def _():
    import cv2
    r, m = prepared()
    g = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = (g - g.min()) / max(1e-9, float(g.max() - g.min())) * 255.0
    a, b = middle(r), middle(g)
    c.ok(a.shape == b.shape, "the result is too small to compare its 160 × 160 middle with the map")
    diff = float(np.abs(a - b).mean())
    c.ok(diff < 25, f"mean difference with the map is {diff:.1f} (it should be below 25)")


@c.test("python3 demo.py runs and saves the pictures in out/ (edges.png included)",
        hint="Run `python3 demo.py` and read the lines marked TODO or ERROR.")
def _():
    code, out = sh("python3 demo.py", timeout=90)
    c.ok(code == 0, "demo.py stopped with an error:\n" + out[-600:])
    c.ok("TODO" not in out and "ERROR" not in out, "demo.py reports problems:\n" +
         "\n".join(l for l in out.splitlines() if "TODO" in l or "ERROR" in l))
    for name in ("gray", "crop_center", "rotated_30", "half_size", "dark_normalised", "edges"):
        c.file_exists(os.path.join("out", name + ".png"))

c.run()
