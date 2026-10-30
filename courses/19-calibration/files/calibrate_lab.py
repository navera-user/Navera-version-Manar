"""calibrate_lab.py — calibrate the Insta360 top lens with YOUR functions of navera_lite/fisheye.py (session 2),
and test the calibration honestly.

    python3 calibrate_lab.py test         check TODO 5-8 on made-up views (no detection needed)
    python3 calibrate_lab.py detect       find the chessboard in the 36 real views (about 30 s) -> corners.npz
    python3 calibrate_lab.py calibrate    YOUR calibration on every view: refused views, RMS, each view    (Steps 7-8)
    python3 calibrate_lab.py stability    fx from random subsets of 8, 12, 20 and 30 views (about 30 s)  (Step 9)
    python3 calibrate_lab.py holdout      train on 28 views, test on 8 unseen ones; Brown–Conrady too      (Step 10)
    python3 calibrate_lab.py curves       the angle of the same pixels: the bench file, yours, Brown–Conrady (Step 10)

Pictures and your calibration go to out/ — click them in the file list of the 📝 Code tab.
"""
import glob
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

fe = rk.load_student("navera_lite.fisheye")
DATA = "/data/academy/19-calibration"
VIEWS = os.path.join(DATA, "views")
CALIB = os.path.join(DATA, "insta360_top.yaml")
SIZE = (1920, 540)
OUT = "out"
CACHE = "corners.npz"
_kit_hint = rk._hint


def _hint(e):
    s = str(e)
    if "objectPoints should contain vector of vectors of points of type Point3f" in s or "Point3f" in s:
        return " — the board points must be float64 for cv2.fisheye (float32 for cv2.calibrateCamera), shape (N, 1, 3)"
    if "CALIB_CHECK_COND" in s:
        return " — OpenCV refused a view: do not catch cv2.error in calibrate_fisheye (calibrate_robust drops the view)"
    if "imagePoints" in s or "objectPoints" in s:
        return " — OpenCV wants a LIST of arrays, one per view: board points (N, 1, 3), corners (N, 1, 2)"
    if "could not broadcast" in s or "operands could not" in s:
        return " — two arrays of different shapes: print the .shape of each (OpenCV corners are (N, 1, 2))"
    return _kit_hint(e)


rk._hint = _hint


def need_cv2():
    import cv2
    return cv2


def obj_points():
    obj = rk.need_ok(fe, "board_points", fe.BOARD[0], fe.BOARD[1], fe.SQUARE_M)
    obj = np.asarray(obj)
    if obj.shape != (54, 1, 3):
        sys.exit(f"board_points(9, 6, …) must return shape (54, 1, 3), got {obj.shape}: python3 calibrate_lab.py test")
    return obj


def load_views():
    if not os.path.exists(CACHE):
        sys.exit("no corners.npz yet: run  python3 calibrate_lab.py detect  first (about 30 s)")
    z = np.load(CACHE)
    return [str(n) for n in z["names"]], [c for c in z["corners"]]


def angles_deg(corners, K, D):
    """Angle from the optical axis (degrees) of each corner, with the calibration (K, D)."""
    cv2 = need_cv2()
    n = cv2.fisheye.undistortPoints(np.asarray(corners, dtype=np.float64).reshape(-1, 1, 2), K, D).reshape(-1, 2)
    return np.degrees(np.arctan(np.hypot(n[:, 0], n[:, 1])))


# ------------------------------------------------------------------------------------------------ made-up views
def synthetic_views(K, D, n_views=10, seed=5, noise_px=0.0):
    """Views of the board seen by a known fisheye camera, made with OpenCV's own projection (for the test)."""
    cv2 = need_cv2()
    rng = np.random.default_rng(seed)
    obj = np.zeros((54, 1, 3))
    obj[:, 0, :2] = np.array([(c * fe.SQUARE_M, r * fe.SQUARE_M) for r in range(6) for c in range(9)])
    views, rvecs, tvecs = [], [], []
    for _ in range(n_views):
        rv = rng.uniform(-0.45, 0.45, 3)
        tv = np.array([rng.uniform(-0.35, 0.1), rng.uniform(-0.2, 0.05), rng.uniform(0.35, 0.6)])
        p, _ = cv2.fisheye.projectPoints(obj, rv.reshape(3, 1), tv.reshape(3, 1), K, D)
        views.append(p.reshape(-1, 1, 2) + rng.normal(0, noise_px, p.reshape(-1, 1, 2).shape))
        rvecs.append(rv.reshape(3, 1))
        tvecs.append(tv.reshape(3, 1))
    return obj, views, rvecs, tvecs


def test():
    K_t = np.array([[520.0, 0.0, 640.0], [0.0, 540.0, 360.0], [0.0, 0.0, 1.0]])
    D_t = np.array([0.05, -0.02, 0.01, -0.004])
    done = total = 0

    def line(k, ok, text, note=None):
        nonlocal done, total
        total += 1
        done += bool(ok)
        print(("✔" if ok else "✘") + f" TODO {k}  {text}" + ("" if ok or not note else f"   ({note})"))

    # TODO 5
    got, err = rk.call(fe, "board_points", 3, 2, 0.5)
    want = np.array([[0, 0, 0], [0.5, 0, 0], [1.0, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0], [1.0, 0.5, 0]], float)
    if err:
        line(5, False, err)
    else:
        a = np.asarray(got)
        note = "the docstring's example. Lab Step 6, hints 1–3"
        if a.shape != (6, 1, 3):
            note = f"shape {a.shape}: OpenCV wants (N, 1, 3) — one point per row, with a middle axis of 1. Lab Step 6, hint 3"
        elif np.allclose(a.reshape(-1, 3), want[[0, 3, 1, 4, 2, 5]]):
            note = "the column index must change FASTEST (row by row, like reading): swap the loops. Lab Step 6, hint 2"
        elif np.allclose(a.reshape(-1, 3), want[:, [1, 0, 2]]):
            note = ("the order is right, but x and y are swapped: x is the COLUMN (c·s), y the ROW (r·s) — swap the "
                    "values, not the loops. Lab Step 6, hints 1–2")
        elif a.dtype != np.float64:
            note = f"dtype {a.dtype}: cv2.fisheye wants float64"
        line(5, a.shape == (6, 1, 3) and a.dtype == np.float64 and np.allclose(a.reshape(-1, 3), want, atol=1e-12),
             f"board_points(3, 2, 0.5)[:, 0] = {np.asarray(got).reshape(-1, 3).tolist() if a.size == 18 else got!r}", note)
    # TODO 6
    obj, views, rv_true, tv_true = synthetic_views(K_t, D_t, 10, seed=5)
    res, err = rk.call(fe, "calibrate_fisheye", obj, views, (1280, 720))
    if err:
        line(6, False, err)
    else:
        try:
            rms, K, D, rvecs, tvecs = res
            K, D = np.asarray(K, float), np.asarray(D, float).ravel()
            ok = abs(K[0, 0] - 520) < 0.5 and abs(K[1, 1] - 540) < 0.5 and np.allclose(D, D_t, atol=2e-3) and len(rvecs) == 10
            note = "a perfect made-up camera fx 520, fy 540, D (0.05, −0.02, 0.01, −0.004) must come back. Lab Step 7, hints 1–3"
            if abs(K[0, 1]) > 1e-9:
                note = "K[0, 1] (the skew) must be 0: the 'no skew' flag. Lab Step 7, hint 2"
            line(6, ok and abs(K[0, 1]) < 1e-9, f"calibrate_fisheye(10 made-up views of a known lens): fx {K[0, 0]:.2f}, "
                 f"fy {K[1, 1]:.2f}, RMS {float(rms):.2e} px", note)
        except (TypeError, ValueError):
            line(6, False, f"calibrate_fisheye must return (rms, K, D, rvecs, tvecs) as OpenCV gives them, got {res!r}"[:300])
    obj_n, noisy, _, _ = synthetic_views(K_t, D_t, 10, seed=5, noise_px=0.3)
    res, err = rk.call(fe, "calibrate_fisheye", obj_n, noisy, (1280, 720))
    if err:
        line(6, False, err)
    else:
        try:
            skew = float(np.asarray(res[1], float)[0, 1])
            line(6, abs(skew) < 1e-12, f"calibrate_fisheye(10 made-up views with 0.3 px of noise): skew K[0, 1] = {skew:.3g}",
                 "with real (noisy) corners the skew must stay exactly 0: the 'no skew' flag. Lab Step 7, hint 3")
        except (TypeError, ValueError, IndexError):
            line(6, False, f"calibrate_fisheye must return (rms, K, D, rvecs, tvecs), got {res!r}"[:300])
    # TODO 7
    shifted = [v + np.array([0.3, 0.4]) for v in views]                       # every corner 0.5 px away
    got, err = rk.call(fe, "reprojection_rms", obj, shifted, rv_true, tv_true, K_t, D_t)
    if err:
        line(7, False, err)
    else:
        try:
            total_rms, per_view = got
            ok = abs(float(total_rms) - 0.5) < 1e-6 and len(per_view) == 10 and all(abs(float(p) - 0.5) < 1e-6 for p in per_view)
            note = "every corner is exactly 0.5 px (0.3 across, 0.4 down) from its projection: RMS 0.5. Lab Step 8, hints 1–4"
            if abs(float(total_rms) - 0.7) < 1e-6:
                note = "0.7 = 0.3 + 0.4: a distance is √(du² + dv²). Lab Step 8, hint 3"
            elif abs(float(total_rms) - 0.25) < 1e-6:
                note = "0.25 is the MEAN SQUARE: take the square root (RMS). Lab Step 8, hint 3"
            elif float(total_rms) > 20:
                note = ("hundreds of px? (N, 2) minus (N, 1, 2) silently makes an (N, N, 2) array: reshape the detected "
                        "corners to (N, 2) first. Lab Step 8, hint 1")
            line(7, ok, f"reprojection_rms(corners shifted by (0.3, 0.4) px) = {float(total_rms):.6g}, "
                 f"{len(per_view)} per-view values", note)
        except (TypeError, ValueError):
            line(7, False, f"reprojection_rms must return (rms, [rms of each view]), got {got!r}"[:300])
    obj2, uneven, rv2, tv2 = synthetic_views(K_t, D_t, 2, seed=8)
    uneven = [uneven[0] + np.array([0.0, 1.0]), uneven[1]]                   # view 0 off by 1 px, view 1 exact
    got, err = rk.call(fe, "reprojection_rms", obj2, uneven, rv2, tv2, K_t, D_t)
    if not err:
        try:
            total_rms, per_view = got
            note = "view 0 is 1 px off, view 1 exact: per view [1, 0], overall √((54·1 + 54·0) / 108) = 0.7071"
            if abs(float(total_rms) - 0.5) < 1e-6:
                note = "0.5 is the MEAN of the per-view values: the RMS is over ALL corners together. Lab Step 8, hint 4"
            line(7, abs(float(total_rms) - math.sqrt(0.5)) < 1e-6 and np.allclose([float(p) for p in per_view], [1, 0], atol=1e-6),
                 f"reprojection_rms(one view 1 px off, one exact) = {float(total_rms):.6g}", note)
        except (TypeError, ValueError):
            line(7, False, f"reprojection_rms must return (rms, [rms of each view]), got {got!r}"[:300])
    else:
        line(7, False, err)
    # TODO 8
    _, unseen, _, _ = synthetic_views(K_t, D_t, 4, seed=11, noise_px=0.0)
    got, err = rk.call(fe, "holdout_rms", obj, unseen, K_t, D_t)
    if err:
        line(8, False, err)
    else:
        try:
            r, per = got
            ok = float(r) < 1e-3 and len(per) == 4
            note = "4 unseen views of the SAME lens, no noise: the error must be ~0 once each pose is found. Lab Step 10, hints"
            line(8, ok, f"holdout_rms(4 unseen exact views, the true K and D) = {float(r):.2e} px", note)
        except (TypeError, ValueError):
            line(8, False, f"holdout_rms must return (rms, [rms of each view]), got {got!r}"[:300])
    print(f"\n{done} of {total} examples right.")


# ------------------------------------------------------------------------------------------------ detect
def detect():
    cv2 = need_cv2()
    files = sorted(glob.glob(os.path.join(VIEWS, "*.jpg")))
    names, views = [], []
    for f in files:
        c = fe.find_corners(cv2.imread(f))
        name = os.path.basename(f)[:-4]
        print(f"  {name}: {'board found' if c is not None else 'no board'}", flush=True)
        if c is not None:
            names.append(name)
            views.append(c)
    np.savez(CACHE, names=np.array(names), corners=np.array(views))
    print(f"{len(views)} of {len(files)} views show the whole board -> {CACHE}")


# ------------------------------------------------------------------------------------------------ calibrate
def calibrate_all(names, views, obj):
    cv2 = need_cv2()
    try:
        return fe.calibrate_robust(obj, views, SIZE, names)
    except cv2.error as e:
        sys.exit("OpenCV stopped your calibration: " + str(e).strip().splitlines()[-1] + _hint(e))
    except ValueError as e:
        sys.exit(str(e))


def calibrate():
    obj = obj_points()
    names, views = load_views()
    (rms, K, D, rvecs, tvecs), kept, dropped = calibrate_all(names, views, obj)
    K, D = np.asarray(K, float), np.asarray(D, float).ravel()
    print(f"YOUR fisheye calibration: {len(kept)} views used, {len(dropped)} refused {dropped}")
    if not dropped:
        print("  ⚠ no view refused: is cv2.fisheye.CALIB_CHECK_COND in your flags? (lab Step 7, hint 3)")
    print(f"  fx {K[0, 0]:.2f}  fy {K[1, 1]:.2f}  cx {K[0, 2]:.2f}  cy {K[1, 2]:.2f}   D {np.round(D, 4).tolist()}")
    kept_views = [views[names.index(n)] for n in kept]
    mine, err = rk.call(fe, "reprojection_rms", obj, kept_views, rvecs, tvecs, K, D)
    if err:
        print(f"  RMS: OpenCV {float(rms):.4f} px   (per-view RMS: {err})")
        per_view = [float("nan")] * len(kept)
    else:
        try:
            total, per_view = mine
            per_view = [float(p) for p in per_view]
        except (TypeError, ValueError):
            sys.exit(f"reprojection_rms() must return (rms, [rms of each view]), it returned {mine!r}"[:300])
        print(f"  RMS: OpenCV {float(rms):.4f} px   your reprojection_rms() {float(total):.4f} px"
              + ("   ✔ equal" if abs(float(total) - float(rms)) < 1e-6 else
                 "   ✘ not equal yet (python3 calibrate_lab.py test)"))
    print("\n  view    RMS (px)   farthest corner from the axis   board's columns in the picture")
    for n, v, r in zip(kept, kept_views, per_view):
        a = angles_deg(v, K, D)
        print(f"  {n}   {r:6.3f}       {a.max():5.1f}°                    {v[:, 0, 0].min():5.0f} – {v[:, 0, 0].max():5.0f}")
    for n in dropped:
        v = views[names.index(n)]
        a = angles_deg(v, K, D)
        print(f"  {n}   refused      {a.max():5.1f}°                    {v[:, 0, 0].min():5.0f} – {v[:, 0, 0].max():5.0f}")
    used = np.concatenate([angles_deg(v, K, D) for v in kept_views])
    print(f"\n  farthest corner used by the calibration: {used.max():.1f}° from the optical axis")
    os.makedirs(OUT, exist_ok=True)
    fe.save_calibration(os.path.join(OUT, "my_fisheye.yaml"), K, D, SIZE, float(rms), len(kept),
                        note=f"calibrate_lab.py; farthest corner used {used.max():.1f} deg")
    print("  saved out/my_fisheye.yaml (used by `curves`)")


# ------------------------------------------------------------------------------------------------ stability
def stability():
    cv2 = need_cv2()
    obj = obj_points()
    names, views = load_views()
    rng = np.random.default_rng(19)
    print("fx of YOUR calibration from random subsets of the views (10 draws per size, refused views dropped):")
    for n in (8, 12, 20, 30):
        fxs, fails = [], 0
        for _ in range(10):
            idx = sorted(rng.choice(len(views), n, replace=False))
            try:
                (r, K, *_), _, _ = fe.calibrate_robust(obj, [views[i] for i in idx], SIZE)
                fxs.append(float(np.asarray(K)[0, 0]))
            except cv2.error:
                fails += 1
        print(f"  {n:2d} views: fx = {np.mean(fxs):6.1f} ± {np.std(fxs):5.1f} px  (std of {len(fxs)} draws; "
              f"min {min(fxs):.1f}, max {max(fxs):.1f}; {fails} failed)", flush=True)


# ------------------------------------------------------------------------------------------------ holdout
def holdout():
    cv2 = need_cv2()
    obj = obj_points()
    names, views = load_views()
    test_i = [i for i in range(len(views)) if i % 5 == 0]
    train_i = [i for i in range(len(views)) if i % 5 != 0]
    print(f"test views (never used to calibrate): {[names[i] for i in test_i]}")
    (tr, K, D, *_), kept, dropped = calibrate_all([names[i] for i in train_i], [views[i] for i in train_i], obj)
    te, per = rk.need_ok(fe, "holdout_rms", obj, [views[i] for i in test_i], K, D)
    print(f"fisheye:       train RMS {float(tr):.3f} px on {len(kept)} views ({len(dropped)} refused)   "
          f"test RMS {float(te):.3f} px on {len(test_i)} unseen views   fx {np.asarray(K)[0, 0]:.1f}")
    print("               per test view: " + ", ".join(f"{names[i]} {float(p):.2f}" for i, p in zip(test_i, per)))
    o32 = obj.reshape(-1, 3).astype(np.float32)
    tr_views = [views[i].reshape(-1, 2).astype(np.float32) for i in train_i]
    rp, Kp, dp, _, _ = cv2.calibrateCamera([o32] * len(tr_views), tr_views, SIZE, None, None)
    sq = []
    for i in test_i:
        v = views[i].reshape(-1, 2).astype(np.float32)
        ok, rv, tv = cv2.solvePnP(o32, v, Kp, dp)
        p, _ = cv2.projectPoints(o32, rv, tv, Kp, dp)
        sq.append(((p.reshape(-1, 2) - v) ** 2).sum(axis=1))
    print(f"Brown–Conrady: train RMS {rp:.3f} px on {len(tr_views)} views               "
          f"test RMS {math.sqrt(np.concatenate(sq).mean()):.3f} px on {len(test_i)} unseen views   fx {Kp[0, 0]:.1f}")
    rall, Kall, dall, _, _ = cv2.calibrateCamera([o32] * len(views), [v.reshape(-1, 2).astype(np.float32) for v in views],
                                                 SIZE, None, None)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "brown_conrady.txt"), "w") as f:
        f.write(" ".join(str(float(x)) for x in [Kall[0, 0], Kall[1, 1], Kall[0, 2], Kall[1, 2]]
                         + list(np.asarray(dall).ravel()[:5])) + "\n")
    print(f"Brown–Conrady on all {len(views)} views: RMS {rall:.3f} px, fx {Kall[0, 0]:.1f} (saved for `curves`; its fx "
          "is not comparable with the fisheye's: another model)")


# ------------------------------------------------------------------------------------------------ curves
def curves():
    cv2 = need_cv2()
    plt = rk.plt_or_none()
    bench = fe.load_calibration(CALIB)
    mine_path = os.path.join(OUT, "my_fisheye.yaml")
    if not os.path.exists(mine_path):
        sys.exit("run  python3 calibrate_lab.py calibrate  first (it saves out/my_fisheye.yaml)")
    mine = fe.load_calibration(mine_path)
    note = open(mine_path).readline()
    far = float(note.split("farthest corner used ")[1].split()[0]) if "farthest corner used" in note else 43.0
    K, D = mine["K"], mine["D"]
    cx, cy = K[0, 2], K[1, 2]
    bc = None
    bc_path = os.path.join(OUT, "brown_conrady.txt")
    if os.path.exists(bc_path):
        vals = [float(x) for x in open(bc_path).read().split()]
        if len(vals) == 9:
            fxb, fyb, cxb, cyb = vals[:4]
            bc = (np.array([[fxb, 0.0, cxb], [0.0, fyb, cyb], [0.0, 0.0, 1.0]]), np.array(vals[4:]))

    def fisheye_angle(cal, u):
        td = math.hypot((u - cal["K"][0, 2]) / cal["K"][0, 0], (cy - cal["K"][1, 2]) / cal["K"][1, 1])
        t, err = rk.call(fe, "theta_from_theta_d", td, cal["D"])
        if err and "returned None" not in err:
            sys.exit(err)
        return float("nan") if t is None else math.degrees(t)

    def bc_angle(u):
        n = cv2.undistortPoints(np.array([[[u, cy]]], np.float64), bc[0], bc[1]).ravel()
        return math.degrees(math.atan(math.hypot(n[0], n[1])))

    print(f"The angle (deg) each model gives to the pixel at distance d from YOUR principal point, along row {cy:.0f}:")
    print("      d (px)    bench fisheye    your fisheye    Brown–Conrady")
    for d in (-800, -600, -400, -200, 200, 400, 600, 800):
        u = cx + d
        b_ = f"{bc_angle(u):9.2f}" if bc else "  (run holdout)"
        print(f"   {d:+8d}    {fisheye_angle(bench, u):10.2f}       {fisheye_angle(mine, u):10.2f}       {b_}")
    r_far = K[0, 0] * fe.theta_d_of(math.radians(far), D)
    print(f"(your calibration used corners up to {far:.1f} deg from the axis: about {r_far:.0f} px along this row)")
    if plt is None:
        return
    ds = np.linspace(-950, 950, 381)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(ds, [fisheye_angle(bench, cx + d) for d in ds], lw=3, color="#d64545", label="bench fisheye (38 views)")
    ax.plot(ds, [fisheye_angle(mine, cx + d) for d in ds], ":", lw=2.5, color="#0b6e8a", label="your fisheye")
    if bc:
        ax.plot(ds, [bc_angle(cx + d) for d in ds], "-.", lw=2, color="#f08c00", label="Brown–Conrady")
    for side in (-1, 1):
        ax.axvspan(side * r_far, side * 950, color="grey", alpha=0.12)
    ax.text(r_far + 10, 8, "no corner used\nby your calibration", color="grey", fontsize=8)
    ax.set_xlabel("distance from your principal point along its row (px; left negative)")
    ax.set_ylabel("angle of the pixel's ray from the optical axis (deg)")
    ax.set_title("The same pixels, three models (gaps: the fisheye model cannot describe the pixel)", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper center", fontsize=8)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "my_curves.png"), dpi=80)
    rk.saved("out/my_curves.png")


if __name__ == "__main__":
    modes = {"test": test, "detect": detect, "calibrate": calibrate, "stability": stability, "holdout": holdout,
             "curves": curves}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        sys.exit(__doc__)
    modes[sys.argv[1]]()
