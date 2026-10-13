import contextlib
import io
import math
import re

import cv2
import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run, sh

c = Checker()

# The lab's true values (the course reference and solutions/08-images/make_dataset.py). Never in files/ or datasets/.
TRUE_HEADING = 35.0          # the drone photo's real heading; info.json gives the compass's 31.0
NCC_COMPASS = 0.746          # run_images.py like: like_map at the compass heading 31.0 (middle 200 × 200)
NCC_BEST = 0.965             # like_map at 35.0
HEADING_TOL = 1.5            # NCC ≥ 0.9 from 33.5° to 36.6° (0.1° steps)
SCALE_TOL_PCT = 2.3          # at 35°, NCC ≥ 0.9 from 0.588 to 0.616 m/px: half-width 0.014 = 2.3 % of 0.60
LIKE_TRACE = (0.620, 496, -72.0, 8.0)   # s, side, c_out − c_in for 640 × 480 at 0.60 → 0.967527 m/px
NAIVE = 238                  # 7150 % 256 and 8430 % 256
BANNED = ("cv2", "scipy", "skimage", "PIL")


def no_library_shortcut():
    """TODO 4–7 must be written with numpy and math: refuse an image library imported by navera_lite/image.py
    (read as text, never executed). Correct numpy code never imports one."""
    import ast
    try:
        tree = ast.parse(open("navera_lite/image.py", encoding="utf-8").read())
    except (OSError, SyntaxError):
        return
    for node in ast.walk(tree):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                 [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in (
                "__import__", "import_module") and node.args and isinstance(node.args[0], ast.Constant):
            names.append(str(node.args[0].value))
        for m in names:
            if m.split(".")[0] in BANNED:
                raise CheckFailed(f"navera_lite/image.py imports {m}: TODO 4–7 are written with numpy and math only — "
                                  "OpenCV is what you compare WITH (lab: the 'Your files' paragraph at the top)")


def image():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.image", fresh=True)


def functions(*names):
    fns = need(image(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/image.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, (bool, str)) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def numbers(v, n, name):
    if v is None or (hasattr(v, "__len__") and not isinstance(v, str) and len(v) == 0):
        raise CheckFailed(f"{name} is not written yet")
    if isinstance(v, str) or not hasattr(v, "__len__"):
        raise CheckFailed(f"{name} should be {n} numbers in brackets, got {v!r}")
    vals = [number(x, name) for x in v]
    if len(vals) != n:
        raise CheckFailed(f"{name} should hold {n} numbers, it holds {len(vals)}")
    return np.array(vals)


def arr(v, what):
    """The student's result as a numpy array, or a plain ✘."""
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if not isinstance(v, np.ndarray):
        raise CheckFailed(f"{what} should return a numpy array, got {type(v).__name__}")
    return v


def dtype_is(v, kind, what, fix):
    if v.dtype != kind:
        raise CheckFailed(f"{what} returned dtype {v.dtype}; it must be {np.dtype(kind).name} — {fix}")


def same(a, b, tol=1e-3):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return a.shape == b.shape and np.allclose(a, b, atol=tol)


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "only integer scalar arrays" in msg or "arrays used as indices must be of integer" in msg:
            raise CheckFailed(msg + " — index arrays must be integers: np.floor(x).astype(np.int64)")
        if "could not be broadcast" in msg:
            raise CheckFailed(msg + " — two arrays of different shapes: print the .shape of each one")
        raise


def photo_b():
    return cv2.imdecode(np.frombuffer(hidden("photo_b.png", text=False), np.uint8), cv2.IMREAD_COLOR)


def ncc(a, b):
    a = np.asarray(a, np.float64).ravel()
    b = np.asarray(b, np.float64).ravel()
    a, b = a - a.mean(), b - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


# ======================================================================== session 1 — Darkroom
@c.test("TODO 1: to_uint8() rounds, clips and never wraps, on unseen values and shapes",
        hint="Lesson §2, the rule: compute in float, then ROUND (np.rint), CLIP to 0..255 (np.clip), and only then "
             ".astype(np.uint8). astype alone truncates (254.9 → 254) and wraps (300 → 44).")
def _():
    (f,) = functions("to_uint8")
    x = np.array([[-0.4, 0.6, 1.4, 127.49, 254.51], [255.4, 1000.0, -300.0, 300.0, 63.7]])
    want = np.array([[0, 1, 1, 127, 255], [255, 255, 0, 255, 64]])
    got = arr(go(f, x), "to_uint8")
    c.ok(got.shape == x.shape, f"to_uint8 of a {x.shape} array returned shape {got.shape}: keep the shape")
    if got.dtype == np.uint8 and int(got[1, 1]) == 1000 % 256:
        raise CheckFailed("1000.0 became 232 and 300.0 became 44: the values WRAP around — clip to 0..255 BEFORE astype")
    if same(got, [[0, 0, 1, 127, 254], [255, 255, 0, 255, 63]], 0):
        raise CheckFailed("0.6 → 0 and 254.51 → 254: astype TRUNCATES — round with np.rint first")
    if same(got, want, 0):
        dtype_is(got, np.uint8, "to_uint8", "finish with .astype(np.uint8)")
    c.ok(same(got, want, 0), f"to_uint8 gave {got.tolist()} — round to the nearest integer, then clip to 0..255")
    got = arr(go(f, np.array([-5, 17, 300], np.int32)), "to_uint8 (int32 input)")
    c.ok(got.dtype == np.uint8 and got.tolist() == [0, 17, 255], f"to_uint8 of int32 [-5, 17, 300] gave {got.tolist()}"
                                                                  f" ({got.dtype}); expected [0, 17, 255] uint8")


@c.test("TODO 2: to_float01() divides by the largest value of the image's own dtype, returns float32",
        hint="np.iinfo(a.dtype).max is 255 for uint8 and 65 535 for uint16 (lab 🧰 Step 2). A float image is only "
             "converted with .astype(np.float32). A bool image raises ValueError (np.issubdtype tells the kinds apart).")
def _():
    (f,) = functions("to_float01")
    got = arr(go(f, np.array([0, 102, 255], np.uint8)), "to_float01(uint8)")
    c.ok(same(got, [0.0, 0.4, 1.0], 1e-6), f"to_float01(uint8 [0, 102, 255]) gave {got.tolist()}")
    dtype_is(got, np.float32, "to_float01", "convert with .astype(np.float32)")
    got = arr(go(f, np.array([[0, 32768], [65535, 6553]], np.uint16)), "to_float01(uint16)")
    if same(got, np.array([[0, 32768], [65535, 6553]]) / 255.0, 1e-3):
        raise CheckFailed("a uint16 image divided by 255 gives values up to 257: divide by the largest value of ITS "
                          "dtype, np.iinfo(a.dtype).max (65 535 for uint16)")
    c.ok(same(got, np.array([[0, 32768], [65535, 6553]]) / 65535.0, 1e-6), f"to_float01(uint16) gave {got.tolist()}")
    dtype_is(got, np.float32, "to_float01", "convert with .astype(np.float32)")
    got = arr(go(f, np.array([0.25, 0.75])), "to_float01(float64)")
    c.ok(same(got, [0.25, 0.75], 1e-7), f"a float image must keep its values (only the dtype changes): got {got.tolist()}")
    dtype_is(got, np.float32, "to_float01 of a float image", "only .astype(np.float32)")
    try:
        f(np.array([True, False]))
    except ValueError:
        pass
    except Exception as e:
        raise CheckFailed(f"a bool image should raise ValueError, it raised {type(e).__name__}: {e}")
    else:
        raise CheckFailed("to_float01(np.array([True, False])) should raise ValueError (a bool image is not a picture)")


@c.test("TODO 3: normalise() stretches uint16 and float images to uint8 0..255, and survives a uniform image",
        hint="Lesson §2: (g − min) / (max − min) · 255 computed in FLOAT (g.astype(np.float64) first — in uint16, "
             "(g − min) · 255 overflows), then your to_uint8(). max == min → np.zeros(shape, np.uint8).")
def _():
    f, u8 = functions("normalise", "to_uint8")
    t = go(u8, np.array([101.6, 300.0]))
    if not (isinstance(t, np.ndarray) and t.dtype == np.uint8 and t.tolist() == [102, 255]):
        raise CheckFailed("normalise() ends with your to_uint8(), which is not right yet: finish TODO 1 first")
    g16 = np.array([[1000, 1612], [3550, 2234]], np.uint16)
    got = arr(go(f, g16), "normalise(uint16)")
    if got.dtype != np.uint8 and same(got, [[0, 61.2], [255, 123.4]], 0.6):
        raise CheckFailed(f"the stretch is right but normalise returned dtype {got.dtype}: finish with your to_uint8()")
    if same(got, np.rint(g16 / 65535.0 * 255.0), 0):
        raise CheckFailed("normalise(uint16) stays dark: stretch from the image's own MIN and MAX, not from the dtype's range")
    c.ok(same(got, [[0, 61], [255, 123]], 0), f"normalise(uint16 [[1000, 1612], [3550, 2234]]) gave {got.tolist()} "
                                             "instead of min → 0, max → 255 in proportion — compute in FLOAT "
                                             "(g.astype(np.float64)): in uint16, (g − min)·255 overflows and wraps")
    dtype_is(got, np.uint8, "normalise", "end with your to_uint8()")
    got = arr(go(f, np.array([[-1.0, 0.2], [2.0, 1.25]])), "normalise(float)")
    c.ok(same(got, [[0, 102], [255, 191]], 0) and got.dtype == np.uint8,
         f"normalise of a float image [[-1, 0.2], [2, 1.25]] gave {got.tolist()} ({got.dtype})")
    got = arr(go(f, np.full((3, 4), 77, np.uint8)), "normalise(uniform)")
    if got.dtype.kind == "f" and not np.all(np.isfinite(got)):
        raise CheckFailed("a uniform image gives nan: max = min, so you divided by 0 — return zeros in that case")
    c.ok(got.shape == (3, 4) and got.dtype == np.uint8 and not got.any(),
         f"a uniform image must give all zeros, uint8, same shape; got {got.dtype} {got.shape} {np.unique(got).tolist()}")
    code, out = sh("python3 -W error -c 'import numpy as np; from navera_lite.image import normalise; "
                   "normalise(np.full((2, 3), 9.5)); normalise(np.full((2, 2), 7, np.uint16))'", timeout=60)
    c.ok(code == 0, "a uniform image makes your normalise() divide 0 by 0 (RuntimeWarning: invalid value encountered "
                    "in divide); the zeros only come out by luck — test max == min BEFORE dividing")


@c.test("Steps 0–2: the thermal frame — the naive cast, and why",
        hint="NAIVE_…: load thermal16.png with "
             "cv2.IMREAD_UNCHANGED, find its min and max, and apply .astype(np.uint8) to them (or compute v % 256). "
             "EXPLAIN_CAST: what astype keeps of a 16-bit value, and what normalise does instead.")
def _():
    pred, lo, hi, why = answers("PREDICT_CAST", "NAIVE_COLDEST", "NAIVE_HOTTEST", "EXPLAIN_CAST")
    predicted("PREDICT_CAST", pred)
    for v, name in [(lo, "NAIVE_COLDEST"), (hi, "NAIVE_HOTTEST")]:
        x = number(v, name)
        if x in (0.0, 255.0):
            raise CheckFailed(f"{name} = {x:g}: that is the darkest/brightest pixel of the cast PICTURE (or what clipping "
                              "gives), not what the coldest/hottest PIXEL became — apply .astype(np.uint8) (value "
                              "modulo 256) to the frame's min and max")
        c.near(x, NAIVE, 0.5, name)
    explained("EXPLAIN_CAST", why,
              ((r"modul", r"\bmod\b", r"%", r"wrap", r"256", r"remainder", r"overflow", r"8 ?bits?", r"lowest"),
               "what astype keeps of a 16-bit value"),
              ((r"normali", r"\bmin", r"\bmax", r"stretch", r"scal", r"float", r"range"),
               "what normalise does instead"))


@c.test("TODO 4: convolve2d() — a true convolution, same size, reflect-101 border, float32, on unseen kernels",
        hint="Lesson §4: pad with np.pad(img, …, mode=\"reflect\"), FLIP the kernel (k[::-1, ::-1]), then for each "
             "kernel entry add weight × a shifted slice of the padded image, of the image's own size. Odd sizes only "
             "(else raise ValueError).")
def _():
    no_library_shortcut()
    (f,) = functions("convolve2d")
    rng = np.random.default_rng(808)
    img = rng.integers(0, 256, (7, 9)).astype(np.uint8)
    k = np.round(rng.normal(size=(3, 5)), 2)
    got = arr(go(f, img, k), "convolve2d")
    if got.shape != img.shape:
        raise CheckFailed(f"a 7 × 9 image with a 3 × 5 kernel gave shape {got.shape}: the result must keep the image's "
                          "size — pad by (rows // 2, columns // 2) first")
    fimg = img.astype(np.float32)
    conv = cv2.filter2D(fimg, -1, k[::-1, ::-1].astype(np.float32), borderType=cv2.BORDER_REFLECT_101)
    corr = cv2.filter2D(fimg, -1, k.astype(np.float32), borderType=cv2.BORDER_REFLECT_101)
    if same(got, corr, 1e-3) and not same(got, conv, 1e-3):
        raise CheckFailed("that is a CORRELATION (the kernel is not flipped): a true convolution uses k[::-1, ::-1] "
                          "(lesson §4)")
    for border, name in [(cv2.BORDER_REPLICATE, "repeats the edge pixel (mode 'edge')"),
                         (cv2.BORDER_CONSTANT, "fills the border with zeros"),
                         (cv2.BORDER_REFLECT, "mirrors WITH the edge pixel (mode 'symmetric')")]:
        if same(got, cv2.filter2D(fimg, -1, k[::-1, ::-1].astype(np.float32), borderType=border), 1e-3):
            raise CheckFailed(f"the inside is right, but your border {name}: OpenCV's default is reflect 101, "
                              "np.pad(…, mode=\"reflect\")")
    c.ok(same(got, conv, 1e-3), "the result differs from a true convolution with a reflect-101 border "
                                f"(largest gap {np.abs(got - conv).max():.3g}) — check the slice for each kernel entry")
    dtype_is(got, np.float32, "convolve2d", "convert the result with .astype(np.float32)")
    ident = np.zeros((5, 5))
    ident[2, 2] = 1.0
    c.ok(same(arr(go(f, img, ident), "convolve2d"), img, 1e-6), "the identity kernel (a 1 in the middle) must give the image back")
    for bad in [np.ones((2, 3)), np.ones((3, 4))]:
        try:
            f(img, bad)
        except ValueError:
            continue
        except Exception as e:
            raise CheckFailed(f"a kernel of shape {bad.shape} should raise ValueError, it raised {type(e).__name__}: {e}")
        raise CheckFailed(f"a kernel of shape {bad.shape} (an even size) should raise ValueError: it has no centre")


@c.test("Steps 3–4: convolution by hand, the flip, and a speed guess",
        hint="Lesson §4 worked example: each output = Σ weight × neighbour, with the mirror at both ends "
             "(… c b | a b c …). For [1, 0, −1] in a TRUE convolution, out(x) = img(x + 1) − img(x − 1). "
             "EXPLAIN_FLIP: the signs a correlation gives, and why a symmetric kernel does not care.")
def _():
    blur, deriv, speed, why = answers("HAND_BLUR", "HAND_DERIV", "PREDICT_SPEED", "EXPLAIN_FLIP")
    b = numbers(blur, 6, "HAND_BLUR")
    if np.allclose(b, [1.5, 2.0, 3.5, 6.5, 8.0, 6.0], atol=0.01):
        raise CheckFailed("HAND_BLUR: the two ends used 0 outside the signal; the border mirrors it (reflect 101)")
    c.ok(np.allclose(b, [2.0, 2.0, 3.5, 6.5, 8.0, 8.0], atol=0.01), f"HAND_BLUR {b.tolist()} is not right — "
         "each value is (left + 2·centre + right) / 4")
    d = numbers(deriv, 6, "HAND_DERIV")
    if np.allclose(d, [0, 0, -6, -6, 0, 0], atol=0.01):
        raise CheckFailed("HAND_DERIV has every sign reversed: that is a correlation — a true convolution flips "
                          "[1, 0, −1], so out(x) = img(x + 1) − img(x − 1)")
    c.ok(np.allclose(d, [0, 0, 6, 6, 0, 0], atol=0.01), f"HAND_DERIV {d.tolist()} is not right")
    predicted("PREDICT_SPEED", speed)
    explained("EXPLAIN_FLIP", why,
              ((r"sign", r"negative", r"minus", r"opposite", r"revers", r"invert", r"-6", r"−6"),
               "what the missing flip does to the derivative"),
              ((r"symmetr", r"same", r"identical", r"mirror", r"unchanged", r"does ?n.t change"),
               "why the Gaussian does not care"))


# ======================================================================== session 2 — Map matcher
@c.test("TODO 5: affine_matrix() equals cv2.getRotationMatrix2D on unseen angles, scales and centres",
        hint="Lesson §5: a = s·cos θ, b = s·sin θ (θ in RADIANS), [[a, b, (1 − a)·cx − b·cy], [−b, a, b·cx + (1 − a)·cy]], "
             "float64, shape (2, 3). Note the argument order: (angle_deg, scale, centre).")
def _():
    no_library_shortcut()
    (f,) = functions("affine_matrix")
    for ang, s, cen in [(-35.0, 0.62, (319.5, 239.5)), (123.4, 1.7, (12.0, -8.0)), (0.0, 1.0, (5.0, 5.0))]:
        got = np.asarray(arr(go(f, ang, s, cen), "affine_matrix"), dtype=np.float64)
        if got.shape != (2, 3):
            raise CheckFailed(f"affine_matrix returned shape {got.shape}: OpenCV's affine matrices are 2 × 3")
        ref = cv2.getRotationMatrix2D(cen, ang, s)
        if np.allclose(got, cv2.getRotationMatrix2D(cen, -ang, s), atol=1e-6) and ang != 0:
            raise CheckFailed(f"angle {ang}°: your matrix turns CLOCKWISE on the screen — b = s·sin θ goes in the TOP "
                              "row with a + sign, −b in the bottom row (lesson §5)")
        if np.allclose(got[:, :2], ref[:, :2], atol=1e-6) and not np.allclose(got[:, 2], ref[:, 2], atol=1e-6):
            if np.allclose(got[:, 2], cv2.getRotationMatrix2D((cen[1], cen[0]), ang, s)[:, 2], atol=1e-6):
                raise CheckFailed("the last column uses the centre as (cy, cx): centre = (cx, cy), x first")
            raise CheckFailed(f"angle {ang}°, centre {cen}: the 2 × 2 part is right, the last column is not — the "
                              "centre must stay where it is: tx = (1 − a)·cx − b·cy, ty = b·cx + (1 − a)·cy")
        if not np.allclose(got, ref, atol=1e-6) and abs(ang) > 1:
            t = ang
            a_deg = s * math.cos(t)
            if abs(got[0, 0] - a_deg) < 1e-6:
                raise CheckFailed("cos and sin got DEGREES: convert with math.radians first")
        c.ok(np.allclose(got, ref, atol=1e-6), f"affine_matrix({ang}, {s}, {cen}) gave {np.round(got, 4).tolist()}")


@c.test("TODO 6: warp_affine() — inverse mapping, bilinear, 0 outside, (width, height), on an unseen photo",
        hint="Lesson §6: np.mgrid gives (v, u) of every destination pixel; the source is A⁻¹·((u, v) − t) "
             "(np.linalg.inv(M[:, :2])); x0 = floor(x), fx = x − x0 (same for y); blend the 4 neighbours read with "
             "pixel_or_zero. size = (width, height) → the result has height rows. Return float32.")
def _():
    no_library_shortcut()
    (f,) = functions("warp_affine")
    got = arr(go(f, np.array([[0.0, 10.0], [20.0, 30.0]]), np.array([[1.0, 0.0, -0.5], [0.0, 1.0, -0.5]]), (2, 2)),
              "warp_affine")
    if same(got, [[0.0, 2.5], [5.0, 15.0]], 0.01):
        raise CheckFailed("a half-pixel shift went the wrong way: you used M itself to find the source — the source of "
                          "(u, v) is A⁻¹·((u, v) − t), INVERSE mapping (lesson §6)")
    if not same(got, [[15.0, 10.0], [12.5, 7.5]], 1e-4) and set(np.round(got.astype(np.float64), 6).ravel()) <= {0.0, 10.0, 20.0, 30.0}:
        raise CheckFailed(f"the docstring example gave {got.tolist()}: no blending — every value is one source pixel "
                          "('nearest', np.rint, or a missing weight); bilinear blends the 4 neighbours (np.floor)")
    c.ok(same(got, [[15.0, 10.0], [12.5, 7.5]], 1e-4), f"the docstring example gave {got.tolist()} instead of "
         "[[15, 10], [12.5, 7.5]] — bilinear weights (1−fx)(1−fy), fx(1−fy), (1−fx)fy, fx·fy, and 0 outside")
    zoom = arr(go(f, np.array([[0.0, 10.0], [20.0, 30.0]]), np.array([[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]]), (2, 2)),
               "warp_affine")
    if same(zoom, [[0.0, 0.0], [0.0, 0.0]], 1e-4):
        raise CheckFailed("a zoom × 2 gave only zeros: you multiplied by A, not by its INVERSE — the source of (u, v) is "
                          "np.linalg.inv(M[:, :2]) · ((u, v) − t) (lesson §6)")
    c.ok(same(zoom, [[0.0, 5.0], [10.0, 15.0]], 1e-4), f"a zoom × 2 of [[0, 10], [20, 30]] gave {zoom.tolist()} "
                                                      "instead of [[0, 5], [10, 15]]")
    g = cv2.cvtColor(photo_b(), cv2.COLOR_BGR2GRAY)
    M = cv2.getRotationMatrix2D((150.0, 100.0), 47.0, 0.8)
    M[0, 2] += 20.0
    M[1, 2] -= 7.0
    got = arr(go(f, g, M, (300, 260)), "warp_affine")
    if got.shape == (300, 260):
        raise CheckFailed("size = (300, 260) gave shape (300, 260): size is (width, height), OpenCV's order — the "
                          "result has height = 260 rows and width = 300 columns")
    c.ok(got.shape == (260, 300), f"warp_affine(…, (300, 260)) returned shape {got.shape}, expected (260, 300)")
    ref = cv2.warpAffine(g.astype(np.float32), M, (300, 260))
    near = cv2.warpAffine(g.astype(np.float32), M, (300, 260), flags=cv2.INTER_NEAREST)
    d = np.abs(got.astype(np.float64) - ref)
    if d.mean() > 0.6 and np.abs(got - cv2.warpAffine(g.astype(np.float32), M, (300, 260),
                                                      flags=cv2.WARP_INVERSE_MAP)).mean() < 0.6:
        raise CheckFailed("your warp treats M as the map from destination to source: you used A, not A⁻¹ — "
                          "np.linalg.inv(M[:, :2]) (lesson §6)")
    M2 = np.hstack([M[:, :2], (M[:, :2] @ M[:, 2])[:, None]])
    if d.mean() > 0.6 and np.abs(got - cv2.warpAffine(g.astype(np.float32), M2, (300, 260))).mean() < 0.6:
        raise CheckFailed("you subtracted t after multiplying by A⁻¹: the source of (u, v) is A⁻¹·((u, v) − t) — "
                          "compute u − t[0], v − t[1] first, then multiply (lesson §6)")
    if d.mean() > 0.6 and np.abs(got.astype(np.float64) - near).mean() < 0.6:
        raise CheckFailed("your warp takes the NEAREST pixel: blend the 4 neighbours (bilinear, lesson §6)")
    c.ok(d.mean() < 0.6, f"on an unseen photo your warp differs from cv2.warpAffine by {d.mean():.2f} grey levels on "
                         "average (allowed 0.6) — check the inverse, the floor and the four weights")
    dtype_is(got, np.float32, "warp_affine", "convert the result with .astype(np.float32)")
    far = np.array([[1.0, 0.0, 1000.0], [0.0, 1.0, 0.0]])
    out = arr(go(f, g, far, (50, 40)), "warp_affine")
    c.ok(out.shape == (40, 50) and not np.any(out), "a picture moved 1000 px away must leave only zeros: pixels from "
                                                    "outside the source are 0 (pixel_or_zero)")


@c.test("Step 5: the affine matrix by hand — where the corner (0, 0) goes",
        hint="Lesson §5 worked example: a = s·cos θ, b = s·sin θ with θ = −90°, then (u, v) = (a·x + b·y + tx, "
             "−b·x + a·y + ty) for (x, y) = (0, 0): only the last column is left.")
def _():
    (uv,) = answers("CORNER_UV")
    p = numbers(uv, 2, "CORNER_UV")
    if np.allclose(p, [25.0, 50.0], atol=0.01):
        raise CheckFailed("CORNER_UV (25, 50) is the result for +90°: the angle is −90°, so b = 0.5·sin(−90°) = −0.5")
    if np.allclose(p, [0.0, 0.0], atol=0.01):
        raise CheckFailed("CORNER_UV (0, 0): that turns about the origin — the turn is about (40, 30), so the last "
                          "column is not 0")
    c.ok(np.allclose(p, [55.0, 10.0], atol=0.01), f"CORNER_UV {tuple(p.tolist())} is not right")


@c.test("TODO 7: like_map() — size, uint8, turned by MINUS the heading, centre on centre, on an unseen photo",
        hint="Lesson §7 and the docstring: grey and contrast first, then ONE warp (turn, scale, centre shift), then "
             "back to uint8. The line above names the part that is off; python3 run_images.py test shows the same "
             "cases on small pictures.")
def _():
    no_library_shortcut()
    f, nz, am, wa = functions("like_map", "normalise", "affine_matrix", "warp_affine")
    for fn, args, want, todo in [
            (nz, (np.array([[10, 30], [50, 20]], np.uint8),), np.array([[0, 128], [255, 64]]), "TODO 3 (normalise)"),
            (am, (-20.0, 0.7, (3.0, 4.0)), cv2.getRotationMatrix2D((3.0, 4.0), -20.0, 0.7), "TODO 5 (affine_matrix)"),
            (wa, (np.arange(12.0).reshape(3, 4), np.array([[1.5, 0.0, -0.25], [0.0, 1.5, -0.5]]), (4, 3)),
             cv2.warpAffine(np.arange(12.0).reshape(3, 4).astype(np.float32),
                            np.array([[1.5, 0.0, -0.25], [0.0, 1.5, -0.5]]), (4, 3)), "TODO 6 (warp_affine)")]:
        try:
            v = run(fn, *args)
            ok = isinstance(v, np.ndarray) and same(v, want, 0.3)
        except CheckFailed:
            ok = False
        if not ok:
            raise CheckFailed(f"like_map() uses your {todo.split('(')[1][:-1]}(), which is not right yet: "
                              f"finish {todo.split(' (')[0]} first")
    got = arr(go(f, np.zeros((30, 70), np.uint8), 0.0, 0.5, 0.97), "like_map")
    side = int(round(math.hypot(70, 30) * 0.5 / 0.97))
    if got.shape == (int(round(math.hypot(70, 30) * 0.97 / 0.5)),) * 2:
        raise CheckFailed("the scale is upside down: s = gsd_photo_m / gsd_map_m (a photo with smaller pixels "
                          "shrinks)")
    c.ok(got.shape == (side, side), f"a 70 × 30 photo at 0.5 m/px for a 0.97 m/px map gave shape {got.shape}, "
                                    f"expected ({side}, {side}) = round(hypot(w, h) · s)")
    dtype_is(got, np.uint8, "like_map", "finish with to_uint8()")
    dot = np.zeros((40, 60), np.uint8)
    dot[19:21, 29:31] = 255                         # a 2 × 2 dot at the photo's centre (29.5, 19.5)
    out = arr(go(f, dot, 35.0, 0.8, 1.0), "like_map").astype(np.float64)
    if out.sum() == 0:
        raise CheckFailed("a dot at the photo's centre vanished: the photo's centre must land on the result's centre")
    ys, xs = np.mgrid[0:out.shape[0], 0:out.shape[1]]
    cy, cx = (ys * out).sum() / out.sum(), (xs * out).sum() / out.sum()
    m = (out.shape[0] - 1) / 2.0
    if abs(cx - m) > 0.15 or abs(cy - m) > 0.15:
        half = abs(abs(cx - m) - 0.5 * 0.8) < 0.2 or abs(abs(cy - m) - 0.5 * 0.8) < 0.2
        raise CheckFailed(f"the photo's centre lands at ({cx:.2f}, {cy:.2f}), the result's centre is ({m:.2f}, {m:.2f})"
                          + (" — half a pixel off: the centre points are ((w − 1)/2, (h − 1)/2) and ((side − 1)/2, "
                             "(side − 1)/2)" if half else " — add (output centre − photo centre) to M's last column"))
    mark = np.zeros((51, 51), np.uint8)
    mark[0:3, 24:27] = 255                          # a bright mark at the top-centre of the photo
    for heading, where, test in [(270.0, "WEST (left)", lambda y, x, m: abs(y - m) <= 2 and x < m - 15),
                                 (180.0, "SOUTH (bottom)", lambda y, x, m: abs(x - m) <= 2 and y > m + 15)]:
        out = arr(go(f, mark, heading, 1.0, 1.0), "like_map")
        if out.ndim != 2 or not out.any():
            raise CheckFailed(f"like_map(mark photo, {heading}) is empty or not grey: shape {out.shape}")
        y, x = np.unravel_index(int(out.argmax()), out.shape)
        m = (out.shape[0] - 1) / 2.0
        if not test(y, x, m):
            raise CheckFailed(f"heading {heading:g}°: the photo's top looks {where.split()[0]}, so a mark at its top must "
                              f"land {where} of the result's centre; it landed at row {y}, column {x} (centre {m:g}) — "
                              "turn by MINUS the heading (lesson §7)")
    pb = photo_b()
    want = cv2.imdecode(np.frombuffer(hidden("like_b.png", text=False), np.uint8), cv2.IMREAD_GRAYSCALE)
    out = arr(go(f, pb, 250.0, 0.45, 0.97), "like_map")
    c.ok(out.shape == want.shape, f"on an unseen photo: shape {out.shape}, expected {want.shape}")
    inside = want > 0
    r = ncc(out[inside], want[inside])
    diff = float(np.abs(out.astype(np.float64) - want)[inside].mean())
    if r < 0.5:
        raise CheckFailed(f"on an unseen photo (heading 250°) your result does not look like the reference (NCC {r:.2f})"
                          " — the angle (−heading), the scale or the centre shift")
    if r > 0.97 and diff > 6:
        raise CheckFailed(f"on an unseen photo the shapes are right (NCC {r:.3f}) but the grey levels are off by {diff:.0f} "
                          "on average: normalise BEFORE the warp (the black corners must not count as the darkest pixel)")
    c.ok(r > 0.985 and diff < 3.0, f"on an unseen photo your result differs from the reference: NCC {r:.3f} (need "
                                   f"> 0.985), mean difference {diff:.1f} grey levels (need < 3)")


@c.test("Step 7: the hand trace of like_map, and the NCC at the compass heading",
        hint="LIKE_TRACE = (s, side, dx, dy) for the lab photo (640 × 480, 0.60 m/px, map 0.967527 m/px): s = ratio of "
             "the m/px, side = round(hypot(w, h)·s), (dx, dy) = c_out − c_in with centre points ((n − 1)/2). "
             "NCC_COMPASS: the like_map line of python3 run_images.py like.")
def _():
    pred, trace, comp = answers("PREDICT_NCC", "LIKE_TRACE", "NCC_COMPASS")
    predicted("PREDICT_NCC", pred)
    t = numbers(trace, 4, "LIKE_TRACE")
    if abs(t[0] - 1 / LIKE_TRACE[0]) < 0.01:
        raise CheckFailed("LIKE_TRACE: s is upside down — s = photo m/px ÷ map m/px (the photo shrinks)")
    c.near(t[0], LIKE_TRACE[0], 0.002, "LIKE_TRACE s")
    if abs(t[1] - 640 * LIKE_TRACE[0]) < 1.5:
        raise CheckFailed("LIKE_TRACE side: that is w·s; the canvas side is round(hypot(w, h)·s), big enough for any turn")
    c.near(t[1], LIKE_TRACE[1], 0.5, "LIKE_TRACE side")
    if np.allclose(t[2:], [-72.5, 7.5], atol=0.01) or np.allclose(t[2:], [-71.5, 8.5], atol=0.01):
        raise CheckFailed("LIKE_TRACE (dx, dy) is half a pixel off: the centre points are ((n − 1)/2), e.g. 319.5, 239.5")
    if np.allclose(t[2:], [72.0, -8.0], atol=0.01):
        raise CheckFailed("LIKE_TRACE (dx, dy) has the wrong sign: c_out − c_in")
    c.ok(np.allclose(t[2:], LIKE_TRACE[2:], atol=0.01), f"LIKE_TRACE (dx, dy) = {tuple(t[2:].tolist())} is not right — "
                                                       "c_out = ((side − 1)/2, (side − 1)/2), c_in = ((w − 1)/2, (h − 1)/2)")
    c.near(number(comp, "NCC_COMPASS"), NCC_COMPASS, 0.02, "NCC_COMPASS")


@c.test("Steps 8–8b: the heading and scale sweeps — numbers and explanations",
        hint="python3 run_images.py sweep (then sweep FROM TO STEP around your peak) and python3 run_images.py scale "
             "HEADING. COMPASS_ERROR_DEG = best heading − the compass heading of info.json. HEADING_TOL_DEG and "
             "SCALE_TOL_PCT: how far either side of the best value the NCC stays ≥ 0.9 (half-widths).")
def _():
    pred, best, err, tol, why, stol, swhy = answers("PREDICT_SWEEP", "BEST_HEADING_DEG", "COMPASS_ERROR_DEG",
                                                   "HEADING_TOL_DEG", "EXPLAIN_SWEEP", "SCALE_TOL_PCT", "EXPLAIN_SCALE")
    predicted("PREDICT_SWEEP", pred)
    c.near(number(best, "BEST_HEADING_DEG"), TRUE_HEADING, 0.5, "BEST_HEADING_DEG")
    e = number(err, "COMPASS_ERROR_DEG")
    if abs(e + (TRUE_HEADING - 31.0)) < 0.6:
        raise CheckFailed("COMPASS_ERROR_DEG has the wrong sign: true heading − compass heading")
    c.near(e, TRUE_HEADING - 31.0, 0.5, "COMPASS_ERROR_DEG")
    t = number(tol, "HEADING_TOL_DEG")
    if abs(t - 2 * HEADING_TOL) < 0.6:
        raise CheckFailed("HEADING_TOL_DEG looks like the full width of the ≥ 0.9 zone: give the half-width (±)")
    c.near(t, HEADING_TOL, 0.5, "HEADING_TOL_DEG (±, degrees)")
    explained("EXPLAIN_SWEEP", why,
              ((r"degree", r"°", r"accura", r"precis", r"sharp", r"narrow", r"fall", r"drop", r"sensitiv", r"error"),
               "how precise the heading must be"),
              ((r"search", r"sweep", r"feature", r"estimat", r"try", r"several", r"many headings", r"rotation",
                r"invarian", r"better compass", r"imu"), "what a system can do about it"))
    sp = number(stol, "SCALE_TOL_PCT")
    if abs(sp - SCALE_TOL_PCT / 100) < 0.01:
        raise CheckFailed("SCALE_TOL_PCT looks like a fraction: give it in percent (e.g. 3.0 for 3 %)")
    if abs(sp - 2 * SCALE_TOL_PCT) < 0.8:
        raise CheckFailed("SCALE_TOL_PCT looks like the full width of the ≥ 0.9 zone: give the half-width (±)")
    c.near(sp, SCALE_TOL_PCT, 0.8, "SCALE_TOL_PCT (±, %)")
    explained("EXPLAIN_SCALE", swhy,
              ((r"heading", r"turn", r"rotat", r"angle", r"compass"), "the heading"),
              ((r"scale", r"altitude", r"height", r"m/px", r"gsd", r"metres per pixel"), "the scale"))


@c.test("report.md: the engineering note — three sections, ≥ 150 words, the key numbers",
        hint="Keep the headings '## Pixels and dtypes', '## Filters', '## Photo to map'. Quote: the naive cast value "
             "(Step 2), the NCC with the compass heading and at the best heading, the best heading, and the ± "
             "tolerance (Step 8).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## Pixels and dtypes", "## Filters", "## Photo to map"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", body)
    c.ok(len(words) >= 150, f"report.md has {len(words)} words of your own (at least 150 expected)")
    for pat, what in [(r"\b238\b", "the naive cast value of the thermal frame (Step 2)"),
                      (r"\b0?\.7[34]\d*\b", "the NCC with the compass heading (Step 7)"),
                      (r"\b0?\.9[56]\d*\b", "the NCC at the best heading (Step 8)"),
                      (r"(?<![\d.])(?:34\.[5-9]\d*|35(?:\.[0-4]\d*)?)(?![\d]|\.\d)", "the best heading (Step 8)"),
                      (r"(?:±|\+/-|\+-|plus or minus)\s*[12](?:\.\d+)?\b|\b1\.\d+\s*(?:°|deg)",
                       "the heading tolerance for NCC ≥ 0.9, as ± (Step 8)")]:
        c.ok(re.search(pat, body) is not None, f"report.md does not quote {what}")


c.milestone("darkroom", "TODO 1:", "TODO 2:", "TODO 3:", "Steps 0–2:", "TODO 4:", "Steps 3–4:",
            label="Session 1 complete: Darkroom badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("mapmatcher", "TODO", "Step", "report",
            label="Mission complete: Darkroom and Map matcher badges earned")

c.run()
