import math

from academy_check import Checker, load_student, need, sh

c = Checker()
DATA = "/data/academy/17-camera-model"


def cm():
    return load_student("camera_math.py")


@c.test("focal_px(): 480 px for 90° on 960 px, ≈ 660 px for the Insta360 view (111°, 1920 px)",
        hint="f = (width_px / 2) / tan(hfov / 2). Convert the angle with math.radians() before math.tan().")
def _():
    (focal_px,) = need(cm(), "focal_px")
    c.near(focal_px(90, 960), 480.0, tol=0.01, what="focal_px(90, 960)")
    c.near(focal_px(111, 1920), 659.79, tol=0.05, what="focal_px(111, 1920)")


@c.test("footprint(): 200 m wide at 100 m with 90°, 291 m at 100 m with 111°",
        hint="W = 2 * h * tan(hfov / 2) — don't forget the 2, and the half angle.")
def _():
    (footprint,) = need(cm(), "footprint")
    c.near(footprint(100, 90), 200.0, tol=0.01, what="footprint(100, 90)")
    c.near(footprint(100, 111), 291.002, tol=0.01, what="footprint(100, 111)")
    c.near(footprint(300, 60), 346.410, tol=0.01, what="footprint(300, 60)")


@c.test("meters_per_pixel() gives the same numbers as NAVERA's ground_m_per_px()",
        hint="The footprint divided by the width of the picture in pixels.")
def _():
    (mpp,) = need(cm(), "meters_per_pixel")
    for h, fov, w in ((150, 111, 1920), (120, 90, 960), (400, 60, 1280), (35, 84, 1536)):
        want = 2.0 * h * math.tan(math.radians(fov) / 2.0) / w        # navera_common.camera_model
        c.near(mpp(h, fov, w), want, tol=want * 1e-6, what=f"meters_per_pixel({h}, {fov}, {w})")


@c.test("height_from_object(): a 12 m pad seen as 48 px (90°, 960 px) → 120 m",
        hint="size_px / f = size_m / h, so h = size_m * f / size_px. Reuse focal_px().")
def _():
    (hfo,) = need(cm(), "height_from_object")
    c.near(hfo(12, 48, 90, 960), 120.0, tol=0.01, what="height_from_object(12, 48, 90, 960)")
    c.near(hfo(4.5, 20, 111, 1920), 148.45, tol=0.05, what="height_from_object(4.5, 20, 111, 1920) (a car)")


@c.test("map_meters_per_pixel(): the same as day_pkg's map_m_per_px()",
        hint="circumference * cos(latitude) / 2**zoom / 256 — cos also wants radians.")
def _():
    (mmpp,) = need(cm(), "map_meters_per_pixel")
    for lat, z in ((0.0, 0), (35.8, 17), (35.8, 19), (60.0, 13)):
        want = 40075016.7 * math.cos(math.radians(lat)) / 2 ** z / 256.0   # day_pkg.local_matcher
        c.near(mmpp(lat, z), want, tol=want * 1e-6, what=f"map_meters_per_pixel({lat}, {z})")


@c.test("scale_factor(): the zoom-17 map at 300 m with the Insta360 view → ≈ 0.469",
        hint="Photo meters per pixel divided by map meters per pixel — reuse your two functions.")
def _():
    (sf,) = need(cm(), "scale_factor")
    c.near(sf(300, 111, 1920, 35.8, 17), 0.46939, tol=0.0005, what="scale_factor(300, 111, 1920, 35.8, 17)")
    c.near(sf(120, 90, 960, 35.83, 19), 1.0327, tol=0.001, what="scale_factor(120, 90, 960, 35.83, 19)")


@c.test("best_zoom() picks the map zoom closest to the photo",
        hint="Loop over `zooms`, compute abs(math.log(map_mpp / photo_mpp)) for each, return the zoom "
             "with the smallest value (an int, not the meters per pixel).")
def _():
    (bz,) = need(cm(), "best_zoom")
    for args, want in (((300, 111, 1920, 35.8), 18), ((120, 90, 960, 35.83), 19),
                       ((150, 111, 1920, 35.8), 19), ((1200, 111, 1920, 35.8), 16),
                       ((20000, 111, 1920, 35.8), 13), ((5, 90, 960, 35.8), 19)):
        got = bz(*args)
        c.ok(got == want, f"best_zoom{args} is {got!r}, expected {want}")
    c.ok(bz(300, 111, 1920, 35.8, zooms=[15, 16, 17]) == 17, "best_zoom must only choose among `zooms`")


@c.test("tilt_shift_m(): 150 m, tilt 10° → the picture centre is ≈ 26 m away",
        hint="h * tan(tilt), with the tilt in radians.")
def _():
    (ts,) = need(cm(), "tilt_shift_m")
    c.near(ts(150, 10), 26.449, tol=0.01, what="tilt_shift_m(150, 10)")
    c.near(ts(100, 0), 0.0, tol=1e-9, what="tilt_shift_m(100, 0)")


@c.test("tilted_extent(): near and far edges, and the horizon case",
        hint="near = h*tan(tilt - fov/2), far = h*tan(tilt + fov/2); return a tuple (near, far). "
             "When tilt + fov/2 >= 90 the far value is math.inf.")
def _():
    (te,) = need(cm(), "tilted_extent")
    r = te(100, 60, 20)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"tilted_extent(100, 60, 20) should be (near, far), got {r!r}")
    c.near(r[0], -17.633, tol=0.01, what="near edge of tilted_extent(100, 60, 20)")
    c.near(r[1], 119.175, tol=0.01, what="far edge of tilted_extent(100, 60, 20)")
    r0 = te(100, 90, 0)
    c.near(r0[0], -100.0, tol=0.01, what="near edge of tilted_extent(100, 90, 0)")
    c.near(r0[1], 100.0, tol=0.01, what="far edge of tilted_extent(100, 90, 0)")
    rh = te(100, 60, 70)
    c.ok(isinstance(rh, (tuple, list)) and len(rh) == 2 and rh[1] == math.inf,
         f"tilted_extent(100, 60, 70): the far edge looks at the horizon, expected math.inf, got {rh!r}")


@c.test("pad_size_px() measures the orange pad in both photos",
        hint="rows, cols = np.nonzero(mask); the width is cols.max() - cols.min() + 1.")
def _():
    import cv2
    (psp,) = need(load_student("measure_pad.py"), "pad_size_px")
    for name, want in (("photo_A.png", 48), ("photo_B.png", 27)):
        img = cv2.imread(f"{DATA}/{name}")
        c.ok(img is not None, f"cannot read {DATA}/{name} (ask your teacher)")
        got = psp(img)
        c.ok(got is not None, f"pad_size_px() returned None for {name}")
        c.near(got, want, tol=1, what=f"pad_size_px({name})")
    import numpy as np
    c.ok(psp(np.zeros((50, 50, 3), np.uint8)) is None, "with no orange pixel at all, pad_size_px() must return None")


@c.test("measure_pad.py finds the two heights (120 m and 210 m, ± 5 %)",
        hint="Run `python3 measure_pad.py`: it uses your pad_size_px() and height_from_object().")
def _():
    code, out = sh("python3 measure_pad.py", timeout=60)
    c.ok(code == 0, "measure_pad.py stopped with an error:\n" + out[-600:])
    import re
    found = {m.group(1): float(m.group(2)) for m in re.finditer(r"(photo_[AB])\.png: .*? at (\d+(?:\.\d+)?) m", out)}
    for p, want in (("photo_A", 120.0), ("photo_B", 210.0)):
        c.ok(p in found, f"no height printed for {p}:\n{out[-400:]}")
        c.ok(abs(found[p] - want) <= 0.05 * want, f"{p}: {found[p]:.0f} m, expected about {want:.0f} m")


@c.test("compare_with_navera.py: your formulas are NAVERA's",
        hint="Run `python3 compare_with_navera.py` and fix the lines marked ✘.")
def _():
    code, out = sh("python3 compare_with_navera.py", timeout=60)
    c.ok("ALL MATCH" in out, "not everything matches yet:\n" + out[-700:])


ANSWERS = {"Q1": ("b", "Meters per pixel are proportional to the height."),
           "Q2": ("b", "Read 'Why the height matters so much' again."),
           "Q3": ("a", "Read the section about tilt again.")}

for q, (good, hint) in ANSWERS.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
