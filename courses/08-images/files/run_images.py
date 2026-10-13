"""run_images.py — runs YOUR functions of navera_lite/image.py on the lab's pictures, and saves what they make.

    python3 run_images.py test       check each function on its docstring example (and a few traps)
    python3 run_images.py cast       the 16-bit thermal frame: the naive cast, then your normalise   (Steps 0, 2)
    python3 run_images.py explore    a real aerial frame as numbers                                 (Step 1)
    python3 run_images.py filters    your convolution: Gaussian blur and Sobel edges vs OpenCV       (Step 4)
    python3 run_images.py warp       your affine matrix and warp vs OpenCV                           (Steps 5-6)
    python3 run_images.py like       the drone photo made like the map, with the compass heading      (Step 7)
    python3 run_images.py sweep [FROM TO STEP]    NCC with the map for a range of headings          (Step 8)
                                     (default: 10° either side of the compass heading, step 0.5°)
    python3 run_images.py scale HEADING [FROM TO STEP]   NCC for a range of photo m/px at one heading   (Step 8b)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
Data: /data/academy/08-images/ (map data © OpenStreetMap contributors).
"""
import json
import math
import os
import sys
import time

import cv2
import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = os.environ.get("ACADEMY_DATA_08", "/data/academy/08-images")
OUT = "out"
OSM = "map data (c) OpenStreetMap contributors"
CROP = 200                                   # side of the middle square compared with the map (px)

im = rk.load_student("navera_lite.image")
_kit_hint = rk._hint


def _hint(e):
    s = str(e)
    if "could not be broadcast" in s:
        return (" — two arrays of different shapes were combined: print the .shape of each one "
                "(a slice of the padded image must have the image's own shape (H, W))")
    if "only integer scalar arrays" in s or "arrays used as indices must be of integer" in s:
        return " — index arrays must be integers: np.floor(x).astype(np.int64)"
    if "Singular matrix" in s:
        return " — the 2 × 2 part of M cannot be inverted: is the scale 0?"
    return _kit_hint(e)


rk._hint = _hint


# ------------------------------------------------------------------------------------------------ helpers
def similarity(a, b):
    """NCC (normalised cross-correlation) of two grey pictures of the same size, lesson §7:
    1 = the same pattern (whatever the brightness and contrast), 0 = unrelated, −1 = a negative."""
    a = np.asarray(a, np.float64).ravel()
    b = np.asarray(b, np.float64).ravel()
    a, b = a - a.mean(), b - b.mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


def difference(a, b):
    """Mean absolute difference of two grey pictures of the same size: 0 = identical, 255 = opposite."""
    return float(np.mean(np.abs(np.asarray(a, np.float64) - np.asarray(b, np.float64))))


def middle(img, size=CROP):
    """The size × size square in the middle of a picture."""
    h, w = img.shape[:2]
    return img[(h - size) // 2:(h - size) // 2 + size, (w - size) // 2:(w - size) // 2 + size]


def save(name, img):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    img = np.asarray(img)
    if img.dtype != np.uint8:
        sys.exit(f"(runner) {name} is {img.dtype}, not uint8 — a picture to save must be uint8")
    cv2.imwrite(path, img)
    rk.saved(path)


def label(img, text):
    """A copy of a grey or colour uint8 picture with a white caption strip under it."""
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    strip = np.full((22, img.shape[1], 3), 255, np.uint8)
    cv2.putText(strip, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1, cv2.LINE_AA)
    return np.vstack([img, strip])


def side_by_side(*imgs):
    h = max(i.shape[0] for i in imgs)
    cols = []
    for i in imgs:
        pad = np.full((h - i.shape[0], i.shape[1], 3), 255, np.uint8)
        cols += [np.vstack([i, pad]), np.full((h, 8, 3), 255, np.uint8)]
    return np.hstack(cols[:-1])


def read(name, flags=cv2.IMREAD_COLOR):
    path = os.path.join(DATA, name)
    img = cv2.imread(path, flags)
    if img is None:
        sys.exit(f"cannot read {path} — is /data/academy/08-images/ there? (ask your teacher)")
    return img


def info():
    with open(os.path.join(DATA, "info.json")) as f:
        return json.load(f)


def need_uint8(fn, v, shape=None):
    """Stop with one plain sentence when a function that must return a uint8 picture does not."""
    if not isinstance(v, np.ndarray):
        sys.exit(f"{fn}() must return a numpy array, but it returned {type(v).__name__}.")
    if v.dtype != np.uint8:
        sys.exit(f"{fn}() returned dtype {v.dtype}: it must return uint8 (convert with your to_uint8() at the end).")
    if shape is not None and v.shape != shape:
        sys.exit(f"{fn}() returned shape {v.shape}, expected {shape}.")
    return v


def fmt(a):
    a = np.asarray(a)
    if a.dtype.kind == "f":
        return np.array2string(a, precision=4, suppress_small=True, separator=", ")
    return np.array2string(a, separator=", ")


# ------------------------------------------------------------------------------------------------ test
BANNED = ("cv2", "scipy", "skimage", "PIL")


def library_shortcut():
    """The name of an image library navera_lite/image.py imports (TODO 1–7 are numpy and math only), or None."""
    import ast
    try:
        tree = ast.parse(open(os.path.join("navera_lite", "image.py"), encoding="utf-8").read())
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                 [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in (
                "__import__", "import_module") and node.args and isinstance(node.args[0], ast.Constant):
            names.append(str(node.args[0].value))
        for n in names:
            if n.split(".")[0] in BANNED:
                return n
    return None


def test():
    lib = library_shortcut()
    if lib:
        print(f"✘ navera_lite/image.py imports {lib}: TODO 1–7 are written with numpy and math only — OpenCV is what "
              "you compare WITH (lab: the 'Your files' paragraph at the top). The check refuses it.\n")
    A = np.array
    cases = [  # (TODO, function, args, expected result, expected dtype or None, notes for wrong results)
        (1, "to_uint8", (A([-7.2, 0.4, 99.5, 254.6, 300.0]),), A([0, 0, 100, 255, 255]), np.uint8,
         [(A([0, 0, 100, 255, 44]), "300 → 44: the value WRAPS — np.clip(…, 0, 255) BEFORE .astype"),
          (A([0, 0, 99, 254, 255]), "254.6 → 254: astype TRUNCATES — round with np.rint first"),
          (A([0, 0, 99, 254, 44]), "254.6 → 254 and 300 → 44: astype alone truncates and wraps — np.rint, then "
                                   "np.clip, then .astype")]),
        (2, "to_float01", (A([0, 51, 255], np.uint8),), A([0.0, 0.2, 1.0]), np.float32, []),
        (2, "to_float01", (A([True, False]),), "ValueError", None,
         "a bool array is not a picture: raise ValueError (np.issubdtype(a.dtype, np.integer) is False for bool)"),
        (2, "to_float01", (A([0, 13107, 65535], np.uint16),), A([0.0, 0.2, 1.0]), np.float32,
         [(A([0.0, 51.4, 257.0]), "a uint16 image divided by 255: divide by the largest value of ITS dtype, "
                                  "np.iinfo(a.dtype).max (🧰 lab Step 2)")]),
        (3, "normalise", (A([[7200, 7800], [8400, 7500]], np.uint16),), A([[0, 128], [255, 64]]), np.uint8, []),
        (3, "normalise", (np.full((2, 3), 7.0),), np.zeros((2, 3)), np.uint8, []),
        (4, "convolve2d", (A([[0.0, 0.0, 3.0, 6.0, 6.0]]), A([[1.0, 0.0, -1.0]])), A([[0.0, 3.0, 6.0, 3.0, 0.0]]),
         np.float32, [(A([[0.0, -3.0, -6.0, -3.0, 0.0]]), "every sign is reversed: that is a CORRELATION — "
                                                        "a true convolution flips the kernel, k[::-1, ::-1]")]),
        (4, "convolve2d", (A([[1.0, 2.0, 3.0]]), A([[1.0, 0.0, 0.0]])), A([[2.0, 3.0, 2.0]]), np.float32,
         [(A([[2.0, 3.0, 3.0]]), "the border repeats the edge pixel (mode 'edge'); OpenCV's default mirrors it "
                                 "WITHOUT repeating the edge pixel: np.pad(…, mode=\"reflect\")"),
          (A([[2.0, 3.0, 0.0]]), "the border is filled with zeros; use np.pad(…, mode=\"reflect\")"),
          (A([[2.0, 1.0, 2.0]]), "not flipped: a 1 LEFT of the kernel's centre must read the pixel to the RIGHT "
                                 "(lesson §4)")]),
        (5, "affine_matrix", (90.0, 2.0, (10.0, 0.0)), A([[0.0, 2.0, 10.0], [-2.0, 0.0, 20.0]]), np.float64,
         [(A([[0.0, -2.0, 10.0], [2.0, 0.0, -20.0]]), "b has the wrong sign: this turns CLOCKWISE on the screen "
                                                     "(lesson §5: [[a, b, …], [−b, a, …]])"),
          (A([[0.0, 2.0, 0.0], [-2.0, 0.0, 0.0]]), "the last column is 0: the turn is about (0, 0), not about the "
                                                  "centre — move the centre to the origin and back (lesson §5)"),
          (A([[-0.8961, 1.7880, 18.9615], [-1.7880, -0.8961, 17.8799]]), "math.cos and math.sin take RADIANS: "
                                                                      "math.radians(angle_deg) first")]),
        (6, "warp_affine", (A([[0.0, 10.0], [20.0, 30.0]]), A([[1.0, 0.0, -0.5], [0.0, 1.0, -0.5]]), (2, 2)),
         A([[15.0, 10.0], [12.5, 7.5]]), np.float32,
         [(A([[0.0, 2.5], [5.0, 15.0]]), "the picture moved the wrong way: you used M itself to find the source; "
                                        "the source of (u, v) is A⁻¹·((u, v) − t), INVERSE mapping (lesson §6)"),
          (A([[30.0, 0.0], [0.0, 0.0]]), "no blending: that is 'nearest' or a missing weight — bilinear blends the 4 "
                                        "neighbours with (1−fx)(1−fy), fx(1−fy), (1−fx)fy, fx·fy")]),
        (6, "warp_affine", (A([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]), A([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), (3, 2)),
         A([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]), np.float32, []),
        (6, "warp_affine", (A([[0.0, 10.0], [20.0, 30.0]]), A([[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]]), (2, 2)),
         A([[0.0, 5.0], [10.0, 15.0]]), np.float32,
         [(A([[0.0, 0.0], [0.0, 0.0]]), "a zoom × 2 gave zeros: you multiplied by A, not by its INVERSE — the source of "
                                       "(u, v) is np.linalg.inv(M[:, :2]) · ((u, v) − t) (lesson §6)")]),
        (6, "warp_affine", (A([[0.0, 10.0], [20.0, 30.0]]), A([[2.0, 0.0, 1.0], [0.0, 2.0, 1.0]]), (3, 3)),
         A([[0.0, 0.0, 2.5], [0.0, 0.0, 5.0], [5.0, 10.0, 15.0]]), np.float32,
         [(A([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]),
           "zoom × 2 shifted by (1, 1) gave zeros: you subtracted t AFTER multiplying by A⁻¹ — the source of (u, v) "
           "is A⁻¹·((u, v) − t): first u − t[0] and v − t[1], then a_inv (lesson §6)")]),
    ]
    done = 0
    failed = set()
    unwritten = set()
    for k, fn, args, want, kind, traps in cases:
        if fn in unwritten:
            failed.add(k)
            continue
        if isinstance(want, str):                                 # the call must raise this exception
            try:
                with __import__("contextlib").redirect_stdout(__import__("io").StringIO()):
                    getattr(im, fn)(*args)
            except NotImplementedError:
                unwritten.add(fn)
                failed.add(k)
                continue
            except Exception as e:
                if type(e).__name__ == want:
                    print(f"✔ TODO {k}  {fn}({fmt(args[0])}) raises {want}")
                    done += 1
                else:
                    print(f"✘ TODO {k}  {fn}({fmt(args[0])}) raised {type(e).__name__}: {traps}")
                    failed.add(k)
                continue
            if rk.is_stub(getattr(im, fn)):
                failed.add(k)
                continue
            print(f"✘ TODO {k}  {fn}({fmt(args[0])}) returned a result: {traps}")
            failed.add(k)
            continue
        got, err = rk.call(im, fn, *args)
        if err:
            print(f"✘ TODO {k}  {err}")
            failed.add(k)
            if "not written yet" in err:
                unwritten.add(fn)
            continue
        if fn == "normalise" and not np.any(got) and np.ptp(args[0]) == 0:
            import warnings
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with np.errstate(all="warn"):
                    rk.call(im, fn, *args)
            if any(issubclass(w.category, RuntimeWarning) for w in caught):
                print("✘ TODO 3  normalise of a uniform picture: the zeros came out by luck — you divided 0 by 0 "
                      "(RuntimeWarning). Test max == min BEFORE dividing")
                failed.add(k)
                continue
        g = np.asarray(got)
        ok_val = g.shape == want.shape and np.allclose(g.astype(np.float64), want, atol=1e-3)
        ok_dtype = g.dtype == kind
        if ok_val and ok_dtype:
            print(f"✔ TODO {k}  {fn}  ->  {fmt(g)}")
            done += 1
            continue
        why = f"the docstring says {fmt(want.astype(kind))}"
        if (not ok_val and kind == np.uint8 and g.dtype.kind == "f" and g.shape == want.shape
                and np.allclose(g.astype(np.float64), want, atol=0.6)):
            ok_val = True                                   # right before rounding: the dtype message below
        if ok_val:
            why = f"right numbers, but dtype {g.dtype}: it must be {np.dtype(kind).name}" + (
                " — finish with your to_uint8()" if kind == np.uint8 and fn != "to_uint8" else "")
        else:
            if g.shape != want.shape:
                why = f"shape {g.shape}, expected {want.shape}" + (
                    " — (width, height) is OpenCV's order: the result has height rows and width columns"
                    if fn == "warp_affine" and g.shape == want.shape[::-1] else
                    " — the result must keep the image's size: pad first, then add shifted slices"
                    if fn == "convolve2d" else "")
            for bad, note in traps:
                if g.shape == bad.shape and np.allclose(g.astype(np.float64), bad, atol=0.06):
                    why = note
            if fn == "normalise" and not np.all(np.isfinite(g.astype(np.float64))):
                why = "a uniform picture gives nan: max = min, so you divided by 0 — return zeros in that case"
            elif fn == "normalise" and why.startswith("the docstring") and args[0].dtype.kind == "u":
                why += " — compute in FLOAT (g.astype(np.float64) first): in uint16, (g − min)·255 overflows"
            if (fn == "warp_affine" and g.shape == want.shape and why.startswith("the docstring")
                    and set(np.round(g.astype(np.float64), 6).ravel()) <= set(np.asarray(args[0], float).ravel()) | {0.0}):
                why = ("no blending: every value is one source pixel — that is 'nearest' or a missing weight; bilinear "
                       "blends the 4 neighbours with (1−fx)(1−fy), fx(1−fy), (1−fx)fy, fx·fy (np.floor, not np.rint)")
        print(f"✘ TODO {k}  {fn}  ->  {fmt(g)}   ({why})")
        failed.add(k)
    n = len(cases)
    if "convolve2d" not in unwritten:                            # an even kernel has no centre
        n += 1
        try:
            with __import__("contextlib").redirect_stdout(__import__("io").StringIO()):
                im.convolve2d(np.zeros((3, 3)), np.ones((2, 3)))
            print("✘ TODO 4  convolve2d with a 2 × 3 kernel must raise ValueError (an even size has no centre): "
                  "raise ValueError(\"…\")")
            failed.add(4)
        except ValueError:
            print("✔ TODO 4  convolve2d with a 2 × 3 kernel raises ValueError")
            done += 1
        except Exception as e:
            print(f"✘ TODO 4  convolve2d with a 2 × 3 kernel raised {type(e).__name__}: {e} — check the sizes first and "
                  "raise ValueError")
            failed.add(4)
    if rk.is_stub(im.like_map):
        print("✘ TODO 7  like_map() is not written yet: write its TODO in navera_lite/image.py and `return` the result")
        print(f"\n{done} of {n + 3} examples give the docstring's result.")
        return
    if failed & {1, 3, 5, 6}:
        need = ", ".join(f"TODO {k}" for k in sorted(failed & {1, 3, 5, 6}))
        print(f"✘ TODO 7  like_map uses your to_uint8, normalise, affine_matrix and warp_affine: fix {need} first")
        print(f"\n{done} of {n + 3} examples give the docstring's result.")
        return
    # like_map: shape, dtype, the turn's direction, the centre
    got, err = rk.call(im, "like_map", np.zeros((30, 70), np.uint8), 0.0, 0.5, 0.97)
    n += 1
    if not err:
        g = np.asarray(got)
        ok = g.shape == (39, 39)
        print(f"{'✔' if ok else '✘'} TODO 7  like_map(70 × 30 photo, 0.5 m/px, map 0.97 m/px) -> shape {g.shape}"
              + ("" if ok else "   (expected (39, 39): s = gsd_photo_m / gsd_map_m = 0.515, side = round(hypot(70, 30) · s))"))
        done += ok
    dot = np.zeros((30, 50), np.uint8)
    dot[14:16, 24:26] = 255                                     # a 2 × 2 dot at the photo's centre (24.5, 14.5)
    got, err = rk.call(im, "like_map", dot, 20.0, 1.0, 1.0)
    n += 1
    if not err:
        g = np.asarray(got, np.float64)
        side = g.shape[0]
        if g.ndim == 2 and g.sum() > 0:
            ys, xs = np.mgrid[0:g.shape[0], 0:g.shape[1]]
            cy, cx = (ys * g).sum() / g.sum(), (xs * g).sum() / g.sum()
            want = (side - 1) / 2.0
            ok = abs(cy - want) < 0.15 and abs(cx - want) < 0.15
            print(f"{'✔' if ok else '✘'} TODO 7  like_map: the photo's centre lands at ({cx:.2f}, {cy:.2f}), the "
                  f"result's centre is ({want:.2f}, {want:.2f})" + ("" if ok else
                  "   (centre points are ((w − 1)/2, (h − 1)/2) and ((side − 1)/2, (side − 1)/2): add the difference "
                  "to the last column of M)"))
            done += ok
    mark = np.zeros((41, 41), np.uint8)
    mark[0:3, 19:22] = 255                                      # a bright mark at the top-centre of the photo
    got, err = rk.call(im, "like_map", mark, 90.0, 1.0, 1.0)
    n += 1
    if err:
        print(f"✘ TODO 7  {err}")
    else:
        g = np.asarray(got)
        if g.shape != (58, 58) or g.dtype != np.uint8:
            print(f"✘ TODO 7  like_map(41 × 41 photo, s = 1) -> shape {g.shape}, dtype {g.dtype}   (expected (58, 58) "
                  "uint8: side = round(hypot(w, h) · s), and to_uint8 at the end)")
        else:
            y, x = np.unravel_index(int(g.argmax()), g.shape)
            if g.max() == 0:
                print("✘ TODO 7  like_map: the result is all black — is the photo inside the result? (the centre shift)")
            elif abs(y - 28.5) <= 2 and x > 40:
                print(f"✔ TODO 7  like_map: heading 90° (top looks east): the photo's top mark lands EAST, at "
                      f"row {y}, column {x}")
                done += 1
            elif abs(y - 28.5) <= 2 and x < 17:
                print("✘ TODO 7  like_map: heading 90°, the photo's top mark lands WEST: you turned the wrong way — "
                      "the photo must turn by MINUS the heading (lesson §7, the heading figure)")
            else:
                print(f"✘ TODO 7  like_map: heading 90°, the photo's top mark lands at row {y}, column {x}; expected "
                      "the middle row (28 or 29), on the right (east)")
    print(f"\n{done} of {n} examples give the docstring's result.")


# ------------------------------------------------------------------------------------------------ cast
def cast():
    t = read("thermal16.png", cv2.IMREAD_UNCHANGED)
    print(f"thermal16.png: shape {t.shape}, dtype {t.dtype}, " + f"{t.nbytes:,} bytes".replace(",", " "))
    print(f"   values from {t.min()} to {t.max()} (raw sensor counts)")
    naive = t.astype(np.uint8)
    print(f"\nnaive  t.astype(np.uint8): dtype {naive.dtype} — look at the picture")
    save("thermal_naive.png", label(label(naive, "t.astype(np.uint8)"), "synthetic thermal-like frame; " + OSM))
    v, err = rk.call(im, "normalise", t)
    if err:
        print(f"\nyour normalise(): {err}")
        return
    if not isinstance(v, np.ndarray) or v.dtype != np.uint8 or v.shape != t.shape:
        print(f"\nyour normalise() returned {getattr(v, 'dtype', type(v).__name__)} {getattr(v, 'shape', '')}: "
              f"expected uint8 {t.shape}")
        return
    print(f"\nyour normalise(t), NOT the naive cast: dtype {v.dtype}, darkest pixel {v.min()}, brightest {v.max()}")
    save("thermal_normalised.png", label(label(v, "normalise(t)"), "synthetic thermal-like frame; " + OSM))


# ------------------------------------------------------------------------------------------------ explore
def explore():
    f = read("real_frame.jpg")
    print("real_frame.jpg (a real aerial frame from NAVERA's day-camera test data)")
    print(f"   type {type(f).__name__}, dtype {f.dtype}, shape {f.shape}, " + f"{f.size:,} numbers".replace(",", " "))
    h, w = f.shape[:2]
    for (y, x) in [(0, 0), (h // 2, w // 2)]:
        print(f"   pixel row {y:3d}, column {x:4d}: [blue, green, red] = {f[y, x].tolist()}")
    for c, name in enumerate(["blue", "green", "red"]):
        print(f"   channel {c} ({name:5s}): from {f[..., c].min():3d} to {f[..., c].max():3d}, mean {f[..., c].mean():6.1f}")
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    y0, x0 = h // 2 - 4, w // 2 - 4
    block = g[y0:y0 + 8, x0:x0 + 8]
    print(f"\nthe 8 × 8 grey block at rows {y0}–{y0 + 7}, columns {x0}–{x0 + 7} (OpenCV's grey):")
    for row in block:
        print("   " + " ".join(f"{v:3d}" for v in row))
    big = cv2.resize(block, (8 * 32, 8 * 32), interpolation=cv2.INTER_NEAREST)
    save("frame_8x8_zoomed.png", label(big, f"grey rows {y0}-{y0 + 7}, columns {x0}-{x0 + 7}"))
    small = cv2.resize(f, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    cv2.rectangle(small, (x0 // 2 - 3, y0 // 2 - 3), (x0 // 2 + 7, y0 // 2 + 7), (0, 0, 255), 2)
    save("frame_half.png", label(small, "real_frame.jpg at half size; red: the 8 x 8 block"))


# ------------------------------------------------------------------------------------------------ filters
def filters():
    g = cv2.cvtColor(read("real_frame.jpg"), cv2.COLOR_BGR2GRAY)
    print(f"the real frame in grey: {g.shape}, {g.dtype}\n")
    k = rk.need_ok(im, "gaussian_kernel", 7, 1.5)
    t0 = time.perf_counter()
    blur = rk.need_ok(im, "convolve2d", g, k)
    t_mine = time.perf_counter() - t0
    if not isinstance(blur, np.ndarray) or blur.shape != g.shape:
        sys.exit(f"convolve2d() must return an array of the image's shape {g.shape}, got {getattr(blur, 'shape', blur)!r}")
    t0 = time.perf_counter()
    ref = cv2.GaussianBlur(g.astype(np.float32), (7, 7), 1.5)
    t_cv = time.perf_counter() - t0
    print(f"Gaussian 7 × 7, σ = 1.5:  your convolve2d vs cv2.GaussianBlur: largest difference "
          f"{np.abs(blur - ref).max():.5f} grey levels;  time {t_mine * 1000:.0f} ms vs {t_cv * 1000:.1f} ms")
    gx, gy = rk.need_ok(im, "sobel", g)
    cx = cv2.Sobel(g, cv2.CV_32F, 1, 0) / 8.0
    cy = cv2.Sobel(g, cv2.CV_32F, 0, 1) / 8.0
    print(f"Sobel (÷ 8):               gx vs cv2.Sobel: largest difference {np.abs(gx - cx).max():.5f};  "
          f"gy: {np.abs(gy - cy).max():.5f}")
    if np.abs(gx + cx).max() < 1e-3:
        print("   ⚠ your gx is exactly MINUS OpenCV's: your convolve2d does not flip the kernel (a correlation)")
    mag = np.sqrt(gx.astype(np.float64) ** 2 + gy.astype(np.float64) ** 2)
    print(f"   gradient magnitude: median {np.median(mag):.1f}, 99th percentile {np.percentile(mag, 99):.1f} "
          f"grey levels per pixel")
    u8, err = rk.call(im, "to_uint8", blur)
    if err:
        sys.exit(err)
    w2 = g.shape[1] // 2
    save("blur.png", label(np.asarray(u8)[:, :w2], "your Gaussian 7 x 7, sigma 1.5 (left half)"))
    edges, err = rk.call(im, "to_uint8", mag * 4.0)
    if err:
        sys.exit(err)
    save("edges.png", label(np.asarray(edges)[:, :w2], "gradient magnitude x 4 (left half)"))


# ------------------------------------------------------------------------------------------------ warp
def warp():
    for args in [(30.0, 0.5, (100.0, 50.0)), (-50.0, 0.8, (319.5, 239.5))]:
        M = rk.need_ok(im, "affine_matrix", *args)
        M = np.asarray(M, np.float64)
        ref = cv2.getRotationMatrix2D(args[2], args[0], args[1])
        print(f"affine_matrix{args}:\n{fmt(M)}\n   largest difference with cv2.getRotationMatrix2D: "
              f"{np.abs(M - ref).max():.2e}\n")
    g = cv2.cvtColor(read("real_frame.jpg"), cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    M = cv2.getRotationMatrix2D(((w - 1) / 2, (h - 1) / 2), 30.0, 0.5)       # OpenCV's matrix: tests your warp alone
    t0 = time.perf_counter()
    mine = rk.need_ok(im, "warp_affine", g, M, (w, h))
    t_mine = time.perf_counter() - t0
    if not isinstance(mine, np.ndarray) or mine.shape != (h, w):
        sys.exit(f"warp_affine(g, M, (width, height)) must return shape (height, width) = {(h, w)}, "
                 f"got {getattr(mine, 'shape', mine)!r}")
    t0 = time.perf_counter()
    ref = cv2.warpAffine(g, M, (w, h))
    t_cv = time.perf_counter() - t0
    d = np.abs(mine.astype(np.float64) - ref)
    print(f"warp_affine of the real frame (30°, scale 0.5, about its centre) vs cv2.warpAffine:")
    print(f"   mean difference {d.mean():.3f}, largest {d.max():.1f} grey levels;  time {t_mine * 1000:.0f} ms vs "
          f"{t_cv * 1000:.1f} ms;  dtype {mine.dtype}")
    if d.mean() > 1.0:
        inv = cv2.warpAffine(g, M, (w, h), flags=cv2.WARP_INVERSE_MAP)
        if np.abs(mine.astype(np.float64) - inv).mean() < 1.0:
            print("   ⚠ your warp treats M as the map from destination to source: you used A, not A⁻¹ — "
                  "a_inv = np.linalg.inv(M[:, :2]) (lab Step 6 hint 1)")
        M2 = np.hstack([M[:, :2], (M[:, :2] @ M[:, 2])[:, None]])
        if np.abs(mine.astype(np.float64) - cv2.warpAffine(g, M2, (w, h))).mean() < 1.0:
            print("   ⚠ you subtracted t after multiplying by A⁻¹: the source of (u, v) is A⁻¹·((u, v) − t) — compute "
                  "u − t[0], v − t[1] first, then multiply (lab Step 6 hint 1)")
    u8, err = rk.call(im, "to_uint8", mine)
    if err:
        sys.exit(err)
    save("rotated.png", label(np.asarray(u8), "your warp_affine: +30 deg, scale 0.5, about the centre"))


# ------------------------------------------------------------------------------------------------ like / sweep
def _photo_and_map():
    inf = info()
    photo = read(inf["photo"]["file"])
    mp = cv2.cvtColor(read(inf["map"]["file"]), cv2.COLOR_BGR2GRAY)
    return inf, photo, mp


def _prepared(photo, heading, gsd_photo, gsd_map):
    v = rk.need_ok(im, "like_map", photo, heading, gsd_photo, gsd_map)
    h, w = photo.shape[:2]
    side = int(round(math.hypot(w, h) * gsd_photo / gsd_map))
    return need_uint8("like_map", v, (side, side))


def like():
    inf, photo, mp = _photo_and_map()
    hd, gp, gm = inf["photo"]["heading_imu_deg"], inf["photo"]["m_per_px"], inf["map"]["m_per_px"]
    print(f"drone photo: {photo.shape[1]} × {photo.shape[0]} px, {gp} m/px, compass heading {hd}°")
    print(f"map patch:   {mp.shape[1]} × {mp.shape[0]} px, {gm} m/px, north up\n")
    ready = _prepared(photo, hd, gp, gm)
    map_mid = middle(mp)
    raw_mid = middle(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY))
    print(f"NCC with the map's middle {CROP} × {CROP} px:")
    print(f"   the photo as it is (grey, no turn, no scale):  {similarity(raw_mid, map_mid):6.3f}")
    print(f"   your like_map(photo, {hd}, {gp}, {gm:.4f}): {similarity(middle(ready), map_mid):6.3f}")
    print(f"\nlike_map's result: {ready.shape[1]} × {ready.shape[0]} px, dtype {ready.dtype}")
    big = cv2.resize(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), (ready.shape[1], int(ready.shape[1] * 0.75)))
    sq = lambda a: cv2.resize(a, (300, 300), interpolation=cv2.INTER_AREA)
    pic = side_by_side(label(sq(mp), "map patch (north up)"),
                       label(cv2.resize(big, (300, 225), interpolation=cv2.INTER_AREA), "the photo, grey"),
                       label(sq(ready), f"like_map, heading {hd}"))
    pic = label(pic, OSM)
    save("like_map.png", pic)


def _range(args, default, what):
    """(FROM, TO, STEP) from the command line, or the default."""
    if not args:
        return default
    try:
        lo, hi, st = (float(x) for x in args)
    except ValueError:
        sys.exit(f"{what}: give three numbers FROM TO STEP, e.g. 30 40 0.1")
    if st <= 0 or hi < lo or (hi - lo) / st > 400:
        sys.exit(f"{what}: FROM ≤ TO, STEP > 0, and at most 400 steps")
    return lo, hi, st


def _table(rows, name, fmt_x, decimals=3):
    print(f" {name:>8}   NCC")
    for x, s in rows:
        print(f" {fmt_x(x):>8}  {s:7.{decimals}f}  " + "#" * max(0, int(round(s * 40))))


def sweep(*args):
    inf, photo, mp = _photo_and_map()
    gp, gm = inf["photo"]["m_per_px"], inf["map"]["m_per_px"]
    hd0 = inf["photo"]["heading_imu_deg"]
    lo, hi, st = _range(args, (hd0 - 10.0, hd0 + 10.0, 0.5), "sweep")
    map_mid = middle(mp)
    rows = []
    t0 = time.perf_counter()
    for hd in np.arange(lo, hi + st / 2, st):
        ready = _prepared(photo, float(hd), gp, gm)
        rows.append((float(hd), similarity(middle(ready), map_mid)))
    print(f"NCC of like_map(photo, heading, {gp}, {gm:.4f}) with the map, middle {CROP} × {CROP} px, headings "
          f"{lo:g}° to {hi:g}° step {st:g}° ({time.perf_counter() - t0:.1f} s)\n")
    _table(rows, "heading", lambda x: f"{x:.1f}" if st >= 0.1 else f"{x:.2f}", 4 if st < 0.5 else 3)
    plt = rk.plt_or_none()
    if plt is not None:
        os.makedirs(OUT, exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 3.6))
        ax.plot([r[0] for r in rows], [r[1] for r in rows], "o-", ms=3)
        ax.axvline(inf["photo"]["heading_imu_deg"], color="tab:red", ls="--", label="compass heading (info.json)")
        ax.set_xlabel("heading given to like_map (°)")
        ax.set_ylabel("NCC with the map")
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "sweep.png"), dpi=110)
        rk.saved(os.path.join(OUT, "sweep.png"))


def scale(*args):
    inf, photo, mp = _photo_and_map()
    gm = inf["map"]["m_per_px"]
    if not args:
        sys.exit("scale: give the heading to use, e.g. python3 run_images.py scale 33.0 (optionally FROM TO STEP in m/px)")
    try:
        hd = float(args[0])
    except ValueError:
        sys.exit("scale: the first number is the heading in degrees")
    lo, hi, st = _range(args[1:], (0.54, 0.66, 0.005), "scale")
    map_mid = middle(mp)
    rows = [(float(g), similarity(middle(_prepared(photo, hd, float(g), gm)), map_mid))
            for g in np.arange(lo, hi + st / 2, st)]
    print(f"NCC of like_map(photo, {hd:g}, photo m/px, {gm:.4f}) with the map, middle {CROP} × {CROP} px\n")
    _table(rows, "m/px", lambda x: f"{x:.3f}", 4 if st < 0.005 else 3)


MODES = {"test": test, "cast": cast, "explore": explore, "filters": filters, "warp": warp, "like": like,
         "sweep": sweep, "scale": scale}
TAKES_ARGS = ("sweep", "scale")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODES or (len(sys.argv) > 2 and sys.argv[1] not in TAKES_ARGS):
        sys.exit("usage: python3 run_images.py " + " | ".join(MODES) + "   (sweep and scale take FROM TO STEP)")
    MODES[sys.argv[1]](*sys.argv[2:])
