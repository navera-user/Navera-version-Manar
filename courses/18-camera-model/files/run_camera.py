"""run_camera.py — runs YOUR functions of navera_lite/camera.py on the lab's situations, and draws them.

    python3 run_camera.py test          check each function on its docstring example (and TODO A, B)
    python3 run_camera.py project       a mast and a ground grid seen by a level and a tilted camera   (Step 2)
    python3 run_camera.py centre        where the image centre lands, nose-down pitch 0° to 25°        (Step 3)
    python3 run_camera.py footprint     the ground covered by a tilted camera                           (Step 6)
    python3 run_camera.py tilt          what 1° of attitude error costs on the ground                  (Step 8)
    python3 run_camera.py straighten    photo T turned into a level, north-up view                      (Step 9)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

cam = rk.load_student("navera_lite.camera")
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if "matmul" in s and "mismatch" in s:
        return (" — a matrix product with the wrong shapes: K and R are (3, 3), a point is 3 numbers; "
                "np.asarray(X, dtype=float) turns a list into an array")
    if "unsupported operand type(s) for -: 'list'" in s:
        return " — lists do not subtract: np.asarray(X, dtype=float) - np.asarray(C, dtype=float)"
    if "zero-size array" in s:
        return " — no orange pixel: test len(cols) == 0 and return None before .min() / .max()"
    if "Singular matrix" in s:
        return " — K cannot be inverted: is K_from_hfov right (a 1 in the corner, f on the diagonal)?"
    return _kit_hint(e)


rk._hint = _hint
W, H, HFOV = 960, 540, 90.0
OUT = "out"


def close(got, want, tol):
    try:
        g = np.asarray(got, dtype=float)
        return g.shape == np.shape(want) and bool(np.all(np.abs(g - np.asarray(want, dtype=float)) <= tol))
    except (TypeError, ValueError):
        return False


def show(v):
    if v is None:
        return "None"
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return repr(v)
    if a.ndim == 0:
        return f"{float(a):.6g}"
    return np.array2string(a, precision=3, suppress_small=True, separator=", ").replace("\n", "")


def test():
    K = np.array([[480.0, 0.0, 480.0], [0.0, 480.0, 270.0], [0.0, 0.0, 1.0]])   # the lab camera, written by hand
    R0 = cam.camera_rotation_hpr(0.0)
    Rt = cam.camera_rotation_hpr(30.0, -12.0, 4.0)
    C = [0.0, 0.0, 100.0]
    # TODO, function, arguments, docstring result (None = must return None), tolerance, note if wrong.
    # The notes name the SYMPTOM and the hint to open; the fixes are in the lab's "Stuck?" boxes.
    cases = [
        (1, "focal_px", (60.0, 1280), 1108.5125, 1e-3,
         "the docstring says about 1108.51. Negative, or 369.5? Lab Step 1, hint 2"),
        (2, "K_from_hfov", (60.0, 1280, 720),
         [[1108.5125, 0, 640], [0, 1108.5125, 360], [0, 0, 1]], 1e-3,
         "(640, 360) in the wrong place? Lab Step 1, hint 3"),
        (3, "project", (K, R0, C, [20.0, 10.0, 0.0]), [576.0, 222.0], 1e-6,
         "the docstring says [576, 222]. [576, 318]? Lab Step 2, hint 3"),
        (3, "project", (K, Rt, C, [30.0, -40.0, 0.0]), [738.3115, 262.2992], 1e-3,
         "a tilted camera (heading 30°, pitch −12°, roll 4°). [819.4, 451.7]? Which way does R_wc turn vectors "
         "(lesson §1)? Lab Step 2, hint 4"),
        (3, "project", (K, R0, C, [0.0, 0.0, 120.0]), None, None,
         "a point 20 m ABOVE the camera is behind it: lab Step 2, hint 5"),
        (4, "backproject_ground", (K, R0, C, 576, 222), [20.0, 10.0], 1e-6,
         "the inverse of project(): the docstring says [20, 10]. Lab Step 3, hints 1–2"),
        (4, "backproject_ground", (K, Rt, C, 480, 270), [-16.8190, -14.8335], 1e-3,
         "a tilted camera (heading 30°, pitch −12°, roll 4°), the image centre. [-6.99, 21.31]? The ray goes "
         "camera → world (lesson §3): lab Step 3, hint 3"),
        (4, "backproject_ground", (K, Rt, [50.0, -20.0, 100.0], 480, 270), [33.1810, -34.8335], 1e-3,
         "the same camera, 50 m east and 20 m south of the origin. [-16.82, -14.83]? Lab Step 3, hint 4"),
        (4, "backproject_ground", (K, cam.camera_rotation_hpr(0.0, 80.0, 0.0), C, 480, 0), None, None,
         "nose 80° UP, the top row of the image: that ray never meets the ground. Lab Step 3, hint 5"),
        (5, "gsd", (100.0, 90.0, 960), 0.208333, 1e-6, "the docstring says 0.20833. 0.337 or 0.104? Lab Step 4, hint 1"),
        (6, "footprint", (K, R0, C, 960, 540),
         [[-100, 56.25], [100, 56.25], [100, -56.25], [-100, -56.25]], 1e-6,
         "the right corners in another order? Lab Step 6, hint 2"),
        (7, "tilt_position_error", (100.0, 10.0, 1.0), 1.805333, 1e-5,
         "the docstring says 1.805. 1.799, 1.745 or a huge number? Lab Step 8, hint 1"),
        (8, "nadir_homography", (K, Rt, Rt), np.eye(3).tolist(), 1e-9,
         "when R_wv = R_wc nothing changes: the identity. Lab Step 9, hint 1"),
        (8, "nadir_homography", (K, Rt, R0),
         [[0.902793, -0.680329, 130.630273], [0.536585, 0.712701, -125.015048], [0.000139, -0.000423, 1.0]], 1e-5,
         None),
    ]
    done = 0
    if not close(Rt, [[0.856664, -0.489074, -0.164113], [-0.511342, -0.847101, -0.14474],
                      [-0.068232, 0.207912, -0.975765]], 1e-5):
        print("⚠ the given camera_rotation_hpr(30, -12, 4) is not the course's: navera_lite/rotations.py or "
              "camera_rotation_hpr was changed — restore them, or every tilted line below is wrong\n")
    for k, fn, args, want, tol, note in cases:
        got, err = rk.call(cam, fn, *args)
        if want is None:                                       # this case must return None
            what = "a point above the camera" if fn == "project" else "a ray towards the sky"
            if err and "returned None" in err:
                print(f"✔ TODO {k}  {fn}({what}) = None")
                done += 1
            elif err:
                print(f"✘ TODO {k}  {err}")
            else:
                print(f"✘ TODO {k}  {fn}({what}) = {show(got)}   ({note})")
            continue
        if err:
            if "returned None" in err and fn == "project":
                err = ("project() returned None for a point in front of the camera: your depth test fired — "
                       "the depth is the z of R_wcᵀ · (X − C), with C subtracted BEFORE rotating (lab Step 2, hint 2)")
            elif "returned None" in err and note:
                err += f"   ({note})"
            print(f"✘ TODO {k}  {err}")
            continue
        ok = close(got, want, tol)
        if fn == "nadir_homography" and note is None and not ok:
            note = _homography_symptom(got)
        if ok and fn == "K_from_hfov" and not hasattr(got, "shape"):
            note, ok = "right numbers, but return a numpy array (np.array(…)): later code does K @ v", True
            print(f"✔ TODO {k}  K_from_hfov{tuple(args)}   ({note})")
            done += 1
            continue
        line = f"{fn}{'(…)' if any(hasattr(a, 'shape') for a in args) else str(tuple(args))} = {show(got)}"
        print(("✔" if ok else "✘") + f" TODO {k}  {line}" + ("" if ok else f"   ({note})"))
        done += bool(ok)
    # TODO A, B and C of measure_pad.py
    try:
        mp = rk.load_student("measure_pad")
    except SystemExit as e:
        print(f"✘ TODO A–C  measure_pad.py: {e}")
        mp = None
    total = len(cases) + 5
    if mp is not None:
        img = np.zeros((6, 30, 3), np.uint8)
        img[2, 10] = img[4, 20] = img[3, 13] = (0, 140, 255)          # three orange pixels
        for fn, k, args, want, note in (
                ("pad_size_px", "A", (img,), 11, "orange pixels in columns 10 to 20: 11. 10 or 3? Lab Step 4, hint 3"),
                ("pad_centre_px", "B", (img,), (43 / 3, 3.0), "mean column 14.33, mean row 3.0. (3.0, 14.33)? "
                                                              "Lab Step 5, hint 2"),
                ("height_from_size", "C", (800.0, 4.5, 30), 120.0, "the docstring says 120.0. Lab Step 4, hint 5")):
            got, err = rk.call(mp, fn, *args)
            if err:
                print(f"✘ TODO {k}  {err}")
                continue
            ok = close(got, want, 1e-6)
            label = "(a test image)" if k != "C" else str(args)
            print(("✔" if ok else "✘") + f" TODO {k}  {fn}{label} = {show(got)}" + ("" if ok else f"   ({note})"))
            done += bool(ok)
        blank = np.zeros((6, 30, 3), np.uint8)
        for fn, k in (("pad_size_px", "A"), ("pad_centre_px", "B")):
            got, err = rk.call(mp, fn, blank)
            if err and "returned None" in err:
                done += 1
                print(f"✔ TODO {k}  {fn}(no orange pixel) = None")
            elif err:
                print(f"✘ TODO {k}  {err}")
            else:
                print(f"✘ TODO {k}  {fn}(no orange pixel) = {show(got)}   (no orange pixel at all: return None)")
    print(f"\n{done} of {total} examples right.")


def _homography_symptom(got):
    """One sentence for a wrong nadir_homography(K, tilted, north-up) of the test."""
    try:
        a = np.asarray(got, dtype=float)
    except (TypeError, ValueError):
        return "it should be a 3 × 3 array"
    if a.shape != (3, 3):
        return f"it should be a 3 × 3 array, not shape {a.shape}"
    s = a / a[2, 2] if abs(a[2, 2]) > 1e-12 else a                # compare the shape first, the scale last
    if close(s, [[1.398, -0.502, 61.11], [0.796, 1.272, -501.355], [0.0, 0.0, 1.0]], 0.01):
        return "[[1.398, −0.502, 61.1], …] (once scaled)? Lab Step 9, hint 3"
    if close(s, [[0.654, 0.62, -7.981], [-0.549, 0.877, 181.419], [0.0, 0.0, 1.0]], 0.01):
        return "[[0.654, 0.620, −7.98], …] (once scaled)? Lab Step 9, hint 4"
    if abs(a[2, 2] - 1.0) > 1e-6:
        return f"H[2, 2] = {a[2, 2]:.3f}, not 1: lab Step 9, hint 2"
    return "not the right matrix: trace the four matrices on paper again (lab Step 9)"


def need_K():
    return rk.need_ok(cam, "K_from_hfov", HFOV, W, H)


def project_mode():
    K = need_K()
    C = np.array([0.0, 0.0, 150.0])
    R0 = cam.camera_rotation_hpr(0.0)
    foot = rk.need_ok(cam, "project", K, R0, C, [40.0, 25.0, 0.0])
    top = rk.need_ok(cam, "project", K, R0, C, [40.0, 25.0, 30.0])
    print("A 30 m mast stands 40 m east and 25 m north of the point under the drone; level camera, nose north, 150 m.")
    print(f"  its foot appears at pixel ({foot[0]:.1f}, {foot[1]:.1f}), its top at ({top[0]:.1f}, {top[1]:.1f})")
    plt = rk.plt_or_none()
    if plt is None:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, (pitch, title) in zip(axes, ((0.0, "level camera, nose north"), (-20.0, "nose down 20°"))):
        R = cam.camera_rotation_hpr(0.0, pitch, 0.0)
        for k in range(-200, 201, 20):
            for line in ([(k, n, 0.0) for n in range(-200, 201, 5)], [(e, k, 0.0) for e in range(-200, 201, 5)]):
                pts = [cam.project(K, R, C, p) for p in line]
                pts = np.array([p for p in pts if p is not None and -50 < p[0] < W + 50 and -50 < p[1] < H + 50])
                if len(pts):
                    ax.plot(pts[:, 0], pts[:, 1], color="#0b6e8a" if k else "#d64545", lw=0.8 if k else 1.6)
        under = cam.project(K, R, C, [0.0, 0.0, 0.0])
        if under is not None:
            ax.plot(*under, "k^", ms=9, label="point under the drone")
        ax.plot(W / 2, H / 2, "+", color="#f08c00", ms=14, mew=2, label="image centre")
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.set_aspect("equal")
        ax.set_title(f"20 m ground grid, 150 m, {title}")
        ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "grid.png"), dpi=80)
    rk.saved("out/grid.png (red: the east and north axes through the point under the drone)")


def centre_mode():
    K = need_K()
    C = np.array([0.0, 0.0, 200.0])
    print("Camera 200 m above flat ground, nose north, the image centre (480, 270):")
    print("  pitch (nose up +)   ground point of the image centre (east, north), m")
    for pitch in (0, -5, -10, -15, -20, -25):
        R = cam.camera_rotation_hpr(0.0, float(pitch), 0.0)
        g, err = rk.call(cam, "backproject_ground", K, R, C, 480, 270)
        print(f"  {pitch:+4d}°               " + (err if err else f"({round(g[0], 2) + 0.0:7.2f}, {round(g[1], 2) + 0.0:7.2f})"))
    rng = np.random.default_rng(18)
    worst = 0.0
    for _ in range(200):
        R = cam.camera_rotation_hpr(rng.uniform(0, 360), rng.uniform(-25, 10), rng.uniform(-10, 10))
        X = np.array([rng.uniform(-150, 150), rng.uniform(-150, 150), 0.0])
        uv = rk.need_ok(cam, "project", K, R, C, X)
        back = rk.need_ok(cam, "backproject_ground", K, R, C, uv[0], uv[1])
        worst = max(worst, float(np.hypot(*(np.asarray(back, dtype=float) - X[:2]))))
    print(f"\nRound trip ground → project → backproject_ground on 200 random points and attitudes: worst {worst:.2e} m"
          + ("   ✔" if worst < 1e-6 else "   ✘ (should be ~0: project and backproject_ground disagree)"))


def shoelace(pts):
    """Area (m², positive) of a polygon given by its corners in order (the shoelace formula, lesson §4)."""
    x, y = np.asarray(pts, dtype=float).T
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)))


def footprint_mode():
    K = need_K()
    C = np.array([0.0, 0.0, 150.0])
    plt = rk.plt_or_none()
    fig, ax = (plt.subplots(figsize=(7, 7)) if plt else (None, None))
    print("Lab camera, 150 m, nose north:   pitch   area (m²)   image centre (east, north)   image bottom / top edge (north)")
    for pitch, col in ((0, "#0b6e8a"), (-10, "#2f9e44"), (-20, "#f08c00"), (-30, "#d64545")):
        R = cam.camera_rotation_hpr(0.0, float(pitch), 0.0)
        poly = rk.need_ok(cam, "footprint", K, R, C, W, H)
        poly = np.asarray(poly, dtype=float)
        if poly.shape != (4, 2):
            sys.exit(f"footprint() must return 4 corners [e, n] — shape (4, 2) — it returned shape {poly.shape}")
        centre = rk.need_ok(cam, "backproject_ground", K, R, C, W / 2, H / 2)
        area = shoelace(poly)
        print(f"{'':33}{pitch:+4d}°  {area:10.0f}    ({round(centre[0], 1) + 0.0:6.1f}, {round(centre[1], 1) + 0.0:7.1f})"
              f"            {poly[2:, 1].mean():7.1f} / {poly[:2, 1].mean():6.1f}")
        if ax is not None:
            closed = np.vstack([poly, poly[:1]])
            ax.fill(closed[:, 0], closed[:, 1], color=col, alpha=0.12)
            ax.plot(closed[:, 0], closed[:, 1], color=col, lw=2, label=f"pitch {pitch:+d}°")
            ax.plot(*centre, "o", color=col)
            ax.plot(*poly[0], "s", color=col, ms=5)
    print("(the image top looks towards the nose, north here; with the nose down, the image bottom is the FAR edge)")
    if ax is None:
        return
    ax.plot(0, 0, "k^", ms=10, label="point under the drone")
    ax.annotate("", xy=(0, 60), xytext=(0, 10), arrowprops=dict(arrowstyle="->"))
    ax.text(5, 40, "nose", fontsize=9)
    ax.set_aspect("equal")
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    ax.set_title("Ground footprint, 150 m, nose north\n(dots: image centre; squares: image corner (0, 0))", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "footprint.png"), dpi=80)
    rk.saved("out/footprint.png")


def tilt_mode():
    print("What 1° of attitude error costs on the ground (the point seen along the optical axis):")
    print("  tilt     h = 100 m    h = 300 m    h = 600 m")
    for tilt in (0, 10, 20, 30, 40):
        row = []
        for h in (100.0, 300.0, 600.0):
            v, err = rk.call(cam, "tilt_position_error", h, float(tilt), 1.0)
            if err:
                sys.exit(err)
            row.append(f"{v:9.2f} m")
        print(f"  {tilt:3d}°  " + "  ".join(row))
    plt = rk.plt_or_none()
    if plt is None:
        return
    tilts = np.arange(0, 46, 1.0)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for h, col in ((100.0, "#0b6e8a"), (300.0, "#f08c00"), (600.0, "#d64545")):
        ax.plot(tilts, [cam.tilt_position_error(h, t, 1.0) for t in tilts], color=col, lw=2, label=f"h = {h:.0f} m")
    ax.axhline(30.0, color="grey", ls=":", lw=1)
    ax.text(1, 31, "30 m: the σ day vision states", fontsize=8, color="grey")
    ax.set_xlabel("tilt from straight down (°)")
    ax.set_ylabel("ground error for 1° of tilt error (m)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "tilt_error.png"), dpi=80)
    rk.saved("out/tilt_error.png")


def straighten_mode():
    import cv2
    mp = rk.load_student("measure_pad")
    img = mp._read("photo_T.png")
    t = mp.TILTED
    K = need_K()
    C = np.array([0.0, 0.0, t["height_m"]])
    R = cam.camera_rotation_hpr(t["heading_deg"], t["pitch_deg"], t["roll_deg"])
    R_level = cam.camera_rotation_hpr(0.0)                       # level, straight down, image top = north
    Hm = rk.need_ok(cam, "nadir_homography", K, R, R_level)
    Hm = np.asarray(Hm, dtype=float)
    if Hm.shape != (3, 3):
        sys.exit(f"nadir_homography() must return a 3 × 3 array, it returned shape {Hm.shape}")
    straight = cv2.warpPerspective(img, Hm, (W, H))
    shown = straight.copy()                                      # the map credit travels with every map image
    cv2.rectangle(shown, (W - 276, H - 24), (W, H), (255, 255, 255), -1)
    cv2.putText(shown, "(c) OpenStreetMap contributors", (W - 268, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (40, 40, 40), 1, cv2.LINE_AA)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "straight_T.png"), shown)
    under = rk.need_ok(cam, "project", K, R, C, [0.0, 0.0, 0.0])
    where = cam.warp_point(Hm, under[0], under[1])
    print(f"The point under the drone: pixel ({under[0]:.1f}, {under[1]:.1f}) in photo T, "
          f"({where[0]:.1f}, {where[1]:.1f}) in the straightened view")
    px, err = rk.call(mp, "pad_size_px", straight)
    c, err2 = rk.call(mp, "pad_centre_px", straight)
    if err or err2:
        sys.exit(err or err2)
    print(f"The pad in the straightened view: {px} px wide, centre at pixel ({c[0]:.1f}, {c[1]:.1f})")
    rk.saved("out/straight_T.png")


MODES = {"test": test, "project": project_mode, "centre": centre_mode, "footprint": footprint_mode,
         "tilt": tilt_mode, "straighten": straighten_mode}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit("usage: python3 run_camera.py " + " | ".join(MODES))
    MODES[mode]()
