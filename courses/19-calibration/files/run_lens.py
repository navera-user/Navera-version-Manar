"""run_lens.py — runs YOUR lens functions of navera_lite/fisheye.py (session 1) on the real Insta360 calibration.

    python3 run_lens.py test                 check TODO 1-4 on their docstring examples (and a few traps)
    python3 run_lens.py project              your projection against OpenCV's, on 1000 directions          (Step 2)
    python3 run_lens.py curve                where a ray lands, and where the calibration stops being valid (Step 3)
    python3 run_lens.py stretch              how wide should the straight view be? the trade-off table    (Step 4)
    python3 run_lens.py straighten [f0216]   straighten one real view and measure the chessboard lines    (Step 5)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

fe = rk.load_student("navera_lite.fisheye")
cam = rk.load_student("navera_lite.camera")
DATA = "/data/academy/19-calibration"
CALIB = os.path.join(DATA, "insta360_top.yaml")
OUT = "out"
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if "list indices must be integers" in s or "tuple indices must be integers" in s:
        return " — X_cam can be a plain list: turn it into an array first, X = np.asarray(X_cam, dtype=float)"
    if "too many indices" in s:
        return " — X_cam is an (N, 3) array: take its columns with X[:, 0], X[:, 1], X[:, 2]"
    if "ssize.width > 0" in s or "size.width" in s or "Expected Ptr<cv::UMat>" in s:
        return " — OpenCV wants the size as (width, height); img.shape is (height, width, 3)"
    if "could not broadcast" in s:
        return " — two arrays of different shapes: print the .shape of each one (OpenCV corners are (N, 1, 2))"
    return _kit_hint(e)


rk._hint = _hint


def bench():
    c = fe.load_calibration(CALIB)
    return c["K"], c["D"], c["size"]


def close(got, want, tol):
    try:
        g = np.asarray(got, dtype=float)
        w = np.asarray(want, dtype=float)
        return g.shape == w.shape and bool(np.all(np.abs(g - w) <= tol))
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
    return np.array2string(a, precision=4, suppress_small=True, separator=", ").replace("\n", "")


def isnan(v):
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------------------------------------ test
def test():
    K, D, size = bench()
    done = total = 0

    def line(k, ok, text, note=None):
        nonlocal done, total
        total += 1
        done += bool(ok)
        print(("✔" if ok else "✘") + f" TODO {k}  {text}" + ("" if ok or not note else f"   ({note})"))

    # TODO 1 — fisheye_project
    got, err = rk.call(fe, "fisheye_project", np.array([[1.0, 0.5, 2.0]]), K, D)
    if err:
        line(1, False, err)
    else:
        note = "the docstring says about [[1250.35, 488.75]]"
        if close(got, [[1267.30, 498.01]], 0.05):
            note = "[[1267.30, 498.01]] is the ideal PINHOLE: the lens polynomial is missing. Lab Step 2, hint 2"
        elif close(got, [[1238.19, 482.11]], 0.05):
            note = "[[1238.19, 482.11]] is the ideal fisheye r = f·θ: θ_d (the polynomial) is missing. Lab Step 2, hint 2"
        elif close(got, [[1112.19, 413.30]], 0.05) or close(got, [[1285.17, 507.77]], 0.05):
            note = "multiply a and b by θ_d / r (not θ_d alone, not r / θ_d). Lab Step 2, hint 3"
        elif close(got, [[1220.65, 472.53]], 0.05):
            note = "θ is the angle from the AXIS, atan(r) — not the direction in the image, atan2(b, a). Lab Step 2, hint 1"
        elif close(np.asarray(got, dtype=float)[:, :1], [[1250.35]], 0.05):
            note = "u is right, v is not: v uses fy = K[1, 1] and cy = K[1, 2]. Lab Step 2, hint 4"
        line(1, close(got, [[1250.3469, 488.7522]], 1e-3), f"fisheye_project([[1.0, 0.5, 2.0]]) = {show(got)}", note)
    got, err = rk.call(fe, "fisheye_project", np.array([[0.0, 0.0, 5.0], [0.3, -0.2, 1.0]]), K, D)
    if err:
        line(1, False, err)
    else:
        a = np.asarray(got, dtype=float)
        if a.shape != (2, 2):
            line(1, False, f"fisheye_project of 2 points must return shape (2, 2), got shape {a.shape}",
                 "one row (u, v) per point: np.stack([u, v], axis=1). Lab Step 2, hint 5")
        elif np.isnan(a[0]).any():
            line(1, False, f"a point ON the optical axis gives {show(a[0])}",
                 "r = 0 there, and θ_d / r is 0/0: its limit is 1 (the point lands on (cx, cy)). Lab Step 2, hint 6")
        else:
            line(1, close(a, [[937.0585, 317.6612], [1131.5387, 176.0502]], 1e-3),
                 f"fisheye_project(two points, one on the axis) = {show(a)}", "the axis point must land on (cx, cy)")
    got, err = rk.call(fe, "fisheye_project", [[1.0, 0.5, 2.0]], K, D)          # a plain list, as in the docstring
    if err:
        line(1, False, err + "   (X_cam may be a list, as in the docstring: start with X = np.asarray(X_cam, "
                             "dtype=float). Lab Step 2, hint 7)")
    else:
        line(1, close(got, [[1250.3469, 488.7522]], 1e-3), f"fisheye_project(a plain list [[1.0, 0.5, 2.0]]) = {show(got)}",
             "a list must give the same pixel as an array: np.asarray(X_cam, dtype=float). Lab Step 2, hint 7")

    # TODO 2 — theta_from_theta_d
    cases = [(0.5303, 0.50972, 1e-4, "the docstring says about 0.5097"),
             (0.0, 0.0, 1e-9, "θ_d = 0 is the optical axis: θ = 0"),
             (1.2, 1.08296, 1e-4, "1.2 is reached TWICE by the curve (rising, then falling): return the RISING-part "
                                  "angle, about 1.083. Lab Step 3, hint 2")]
    for td, want, tol, note in cases:
        got, err = rk.call(fe, "theta_from_theta_d", td, D)
        if err:
            line(2, False, err)
            continue
        if isinstance(got, (int, float, np.floating)) and abs(float(got) - math.degrees(want)) < 0.01 and want > 0:
            note = "that is in DEGREES: the function returns radians. Lab Step 3, hint 4"
        line(2, (not isnan(got)) and close(got, want, tol), f"theta_from_theta_d({td}) = {show(got)}", note)
    got, err = rk.call(fe, "theta_from_theta_d", 1.0, [0.0, 0.0, 0.0, 0.0])
    if err:
        line(2, False, err + "   (the ideal fisheye D = [0, 0, 0, 0] rises all the way to 90°: when np.diff never "
                             "becomes ≤ 0, the rising part is the whole [0, π/2]. Lab Step 3, 🧰 box and hint 3)")
    else:
        line(2, (not isnan(got)) and close(got, 1.0, 1e-6), f"the ideal fisheye, theta_from_theta_d(1.0, [0, 0, 0, 0]) = "
             f"{show(got)}", "θ_d = θ for the ideal lens: 1.0. Its curve never turns back: the top is the grid's last value")
    for td in (1.30, (1920 - K[0, 2]) / K[0, 0]):
        got, err = rk.call(fe, "theta_from_theta_d", td, D)
        if err and "returned None" in err:
            err = None
            got = None
        if err:
            line(2, False, err)
        else:
            line(2, isnan(got), f"theta_from_theta_d({td:.4f}) = {show(got)}",
                 "the curve never reaches this θ_d: return float('nan'). Find the curve's top with a grid and "
                 "np.diff (never type a number): Lab Step 3, plan (1) and hint 3")
    D4 = [0.10, -0.30, 0.25, -0.08]                  # another lens: its curve's top is θ_d = 1.1285 (at 1.2767 rad)
    for td, want in ((1.0156, 1.056433), (1.1385, None)):
        got, err = rk.call(fe, "theta_from_theta_d", td, D4)
        if err and "returned None" in err and want is None:
            got, err = None, None
        if err:
            line(2, False, err)
        elif want is None:
            line(2, isnan(got), f"another lens, theta_from_theta_d({td}) = {show(got)}",
                 "this lens' curve tops at θ_d = 1.1285: return nan above it. Your code must find each lens' own top "
                 "(Lab Step 3, plan (1))")
        else:
            line(2, (not isnan(got)) and close(got, want, 1e-4), f"another lens, theta_from_theta_d({td}) = {show(got)}",
                 "another lens (D = [0.10, −0.30, 0.25, −0.08]): about 1.0564. Your code must work for any D")

    # TODO 3 — stretch_at
    for args, want, note in (((0.0, 659.79), 0.998943, "the docstring says about 0.999 = f_new / fx at the centre"),
                             ((40.0, 659.79), 1.473577,
                              "the docstring says about 1.474. About 0, negative or nan? θ is still in degrees (hint 1). "
                              "1.702? The lens' own pixels per radian are missing "
                              "(its slope). 1.602? That is θ_d/θ, not the slope. 0.679? Upside down. Lab Step 4, hints 2–3"),
                             ((30.0, 257.23), 0.472553, "a 150° view at 30° from the axis")):
        got, err = rk.call(fe, "stretch_at", *args, K, D)
        if err:
            line(3, False, err)
            continue
        line(3, close(got, want, 1e-4), f"stretch_at{args} = {show(got)}", note)
    for args, why in (((70.0, 659.79), "70° is past the top of the lens curve (67.4°): the model is not valid there"),
                      ((90.0, 659.79), "a pinhole picture cannot show a ray at 90°")):
        got, err = rk.call(fe, "stretch_at", *args, K, D)
        if err and "returned None" in err:
            got, err = None, None
        if err:
            line(3, False, err)
        else:
            line(3, isnan(got), f"stretch_at{args} = {show(got)}", why + ": return float('nan'). Lab Step 4, hint 4")

    # TODO 4 — undistort (on a test picture whose colour says where each pixel came from)
    img = np.zeros((540, 1920, 3), np.uint8)
    img[:, :, 0] = (np.arange(1920) // 8).astype(np.uint8)[None, :]           # blue = column / 8
    img[:, :, 1] = (np.arange(540) // 4).astype(np.uint8)[:, None]             # green = row / 4
    img[:, :, 2] = 200
    K_new = cam.K_from_hfov(111.0, 1920, 540)
    got, err = rk.call(fe, "undistort", img, K, D, K_new)
    if err:
        line(4, False, err)
    else:
        a = np.asarray(got)
        if a.shape != img.shape:
            line(4, False, f"undistort returned shape {a.shape}, not {img.shape}",
                 "the size OpenCV wants is (width, height) = (1920, 540): img.shape is (height, width, 3). Lab Step 5, hint 2")
        elif a.dtype != np.uint8:
            line(4, False, f"undistort returned dtype {a.dtype}", "return the remapped image itself (uint8)")
        else:
            centre = a[270, 960].astype(int).tolist()
            line(4, abs(centre[0] - 117) <= 1 and abs(centre[1] - 79) <= 1 and centre[2] == 200,
                 f"undistort: the new image centre (960, 270) took its colour from column {centre[0] * 8}, row "
                 f"{centre[1] * 4} of the fisheye picture", "it must come from (cx, cy) ≈ (937, 318): no rotation, and "
                 "the NEW camera K_new for the output. Lab Step 5, hint 3")
            edge = a[270, 3].astype(int).tolist()
            line(4, edge[2] == 200 and abs(edge[0] - 28) <= 1,
                 f"undistort: the left edge of the straight view (3, 270) took its colour from column {edge[0] * 8}",
                 "a ray 55.4° to the left: about column 230 of the fisheye picture. Check K_new and the size")
            bottom = a[538, 960].astype(int).tolist()
            centre_ok = abs(centre[0] - 117) <= 1 and abs(centre[1] - 79) <= 1
            line(4, bottom == [0, 0, 0], f"undistort: the bottom row of the straight view, (960, 538), is {bottom}",
                 ("it looks below the fisheye picture's lower edge: it must stay BLACK — a constant border "
                  "(cv2.BORDER_CONSTANT). Lab Step 5, hint 4") if centre_ok else
                 "fix the first TODO 4 line first (K_new, the rotation): with the wrong new camera this row looks "
                 "elsewhere too")
    print(f"\n{done} of {total} examples right.")


# ------------------------------------------------------------------------------------------------ project
def project_mode():
    import cv2
    K, D, _ = bench()
    rng = np.random.default_rng(19)
    ang = np.radians(rng.uniform(0, 60, 1000))
    az = rng.uniform(0, 2 * np.pi, 1000)
    X = np.stack([np.sin(ang) * np.cos(az), np.sin(ang) * np.sin(az), np.cos(ang)], axis=1) * 3.0
    mine = np.asarray(rk.need_ok(fe, "fisheye_project", X, K, D), dtype=float)
    if mine.shape != (1000, 2):
        sys.exit(f"fisheye_project of 1000 points must return shape (1000, 2), got {mine.shape}")
    ref, _ = cv2.fisheye.projectPoints(X.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, D)
    diff = np.hypot(*(mine - ref.reshape(-1, 2)).T)
    print(f"1000 directions up to 60° off the axis: your fisheye_project against OpenCV's projectPoints")
    print(f"  largest difference {diff.max():.2e} px" + ("   ✔ the same model" if diff.max() < 1e-6 else
                                                         "   ✘ not the same model yet (python3 run_lens.py test)"))
    ex = rk.need_ok(fe, "fisheye_project", np.array([[1.0, 0.5, 2.0]]), K, D)
    print(f"  worked example of the lesson, X = (1.0, 0.5, 2.0) m → ({ex[0][0]:.2f}, {ex[0][1]:.2f}) px")
    plt = rk.plt_or_none()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(9, 3.2))
    th = np.radians(np.arange(0, 61, 10))
    for t in th:
        ring = np.stack([np.sin(t) * np.cos(np.linspace(0, 2 * np.pi, 120)),
                         np.sin(t) * np.sin(np.linspace(0, 2 * np.pi, 120)), np.full(120, np.cos(t))], axis=1)
        p = np.asarray(fe.fisheye_project(ring, K, D), dtype=float)
        ax.plot(p[:, 0], p[:, 1], lw=1, color="#0b6e8a")
        ax.text(K[0, 2] + (p[:, 0].max() - K[0, 2]) + 4, K[1, 2], f"{math.degrees(t):.0f}°", fontsize=7, color="#0b6e8a")
    ax.add_patch(plt.Rectangle((0, 0), 1920, 540, fill=False, lw=1.5, color="#d64545"))
    ax.set_xlim(-100, 2020)
    ax.set_ylim(640, -100)
    ax.set_aspect("equal")
    ax.set_title("Rays 10°, 20° … 60° from the optical axis, through YOUR fisheye_project (red: the 1920 × 540 picture)",
                 fontsize=9)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "rings.png"), dpi=80)
    rk.saved("out/rings.png")


# ------------------------------------------------------------------------------------------------ curve
def curve_mode():
    K, D, size = bench()
    fx, cx = K[0, 0], K[0, 2]
    grid = np.linspace(0.0, math.pi / 2, 20001)
    td = fe.theta_d_of(grid, D)
    i = int(np.argmax(td))
    print(f"The bench calibration's curve r = fx·θ_d(θ) rises until θ = {math.degrees(grid[i]):.1f}°, "
          f"r = {td[i] * fx:.0f} px, then turns back down.")
    print("Your theta_from_theta_d() on a few distances r from the principal point (along a row, θ_d = r / fx):")
    for r_px in (200.0, 400.0, 600.0, 800.0, cx, size[0] - cx):
        t, err = rk.call(fe, "theta_from_theta_d", r_px / fx, D)
        if err and "returned None" not in err:
            sys.exit(err)
        what = "the LEFT edge of the picture" if abs(r_px - cx) < 1e-6 else (
            "the RIGHT edge of the picture" if abs(r_px - (size[0] - cx)) < 1e-6 else "")
        val = "nan — the calibration cannot describe this pixel" if (t is None or isnan(t)) else f"{math.degrees(t):6.2f}°"
        print(f"  r = {r_px:6.1f} px   θ = {val}   {what}")
    plt = rk.plt_or_none()
    if plt is None:
        return
    th = np.radians(np.linspace(0, 85, 500))
    deg = np.degrees(th)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(deg, fx * np.tan(th), label="ideal pinhole: f·tan θ", color="#868e96")
    ax.plot(deg, fx * th, "--", label="ideal fisheye: f·θ", color="#0b6e8a")
    ax.plot(deg, fx * fe.theta_d_of(th, D), lw=3, label="bench calibration: fx·θ_d(θ)", color="#d64545")
    ax.axhline(cx, color="grey", ls=":")
    ax.text(2, cx + 15, f"left edge of the picture: {cx:.0f} px from the principal point", color="grey", fontsize=8)
    ax.plot(math.degrees(grid[i]), td[i] * fx, "ko")
    ax.text(math.degrees(grid[i]) + 1, td[i] * fx - 70, "the curve turns back", fontsize=8)
    ax.set_ylim(0, 1600)
    ax.set_xlabel("angle θ of the ray from the optical axis (°)")
    ax.set_ylabel("distance r from the principal point (px)")
    ax.set_title("Where a ray lands on the Insta360 picture")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "lens_curve.png"), dpi=80)
    rk.saved("out/lens_curve.png")


# ------------------------------------------------------------------------------------------------ stretch
def stretch_mode():
    K, D, size = bench()
    fx, w = K[0, 0], size[0]
    print(f"Straight (pinhole) views {w} px wide, from the bench calibration (fx = {fx:.2f} px):")
    print("   width    f_new (px)   centre: stretch_at(0°)   stretch_at(30°)   at the view's edge")
    rows = {}
    for hfov in (90.0, 111.0, 120.0, 150.0, 166.0):
        K_new = rk.need_ok(cam, "K_from_hfov", hfov, w, size[1])
        f_new = float(np.asarray(K_new)[0, 0])
        vals = []
        for t in (0.0, 30.0, hfov / 2):
            v, err = rk.call(fe, "stretch_at", t, f_new, K, D)
            if err and "returned None" not in err:
                sys.exit(err)
            vals.append(float("nan") if v is None else float(v))
        rows[hfov] = (f_new, vals)
        edge = "nan (not valid)" if isnan(vals[2]) else f"{vals[2]:.2f} at {hfov / 2:.1f}°"
        print(f"  {hfov:5.1f}°   {f_new:9.2f}     {vals[0]:12.3f}          {vals[1]:12.3f}        {edge}")
    print("(1 = the lens' own detail; above 1 = pixels invented by interpolation; below 1 = real detail thrown away)")
    plt = rk.plt_or_none()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for hfov, col in ((111.0, "#d64545"), (150.0, "#f08c00"), (166.0, "#0b6e8a")):
        f_new = rows[hfov][0]
        ts = np.linspace(0, hfov / 2, 200)
        ax.plot(ts, [fe.stretch_at(t, f_new, K, D) for t in ts], lw=2, color=col, label=f"{hfov:.0f}° straight view")
    ax.axhline(1.0, color="grey", ls=":")
    ax.set_yscale("log")
    ax.set_xlabel("angle from the optical axis (°)")
    ax.set_ylabel("straight-view pixels per lens pixel (log)")
    ax.set_title("YOUR stretch_at: below 1 detail is lost, above 1 it is invented; gaps = model not valid", fontsize=9)
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "stretch.png"), dpi=80)
    rk.saved("out/stretch.png")


# ------------------------------------------------------------------------------------------------ straighten
def line_bend_px(points):
    """Largest distance (px) between a point and the best straight line through all of them (cv2.fitLine)."""
    import cv2
    p = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    vx, vy, x0, y0 = cv2.fitLine(p, cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    return float(np.abs((p[:, 0] - x0) * vy - (p[:, 1] - y0) * vx).max())


def worst_bend(corners, board):
    g = np.asarray(corners).reshape(board[1], board[0], 2)
    return max([line_bend_px(g[r]) for r in range(board[1])] + [line_bend_px(g[:, c]) for c in range(board[0])])


def draw(img, corners, board, label):
    import cv2
    out = img.copy()
    if corners is not None:
        g = np.asarray(corners).reshape(board[1], board[0], 2)
        for r in range(board[1]):
            a, b = g[r][0], g[r][-1]
            cv2.line(out, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 0, 255), 2)
        cv2.drawChessboardCorners(out, board, np.asarray(corners, dtype=np.float32).reshape(-1, 1, 2), True)
    cv2.putText(out, label, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
    return out


def straighten_mode(name="f0216"):
    import cv2
    K, D, size = bench()
    path = os.path.join(DATA, "views", name + ".jpg")
    img = cv2.imread(path)
    if img is None:
        sys.exit(f"no view {name} in {DATA}/views (ls {DATA}/views)")
    K_new = rk.need_ok(cam, "K_from_hfov", 111.0, size[0], size[1])
    flat = rk.need_ok(fe, "undistort", img, K, D, K_new)
    flat = np.asarray(flat)
    if flat.shape != img.shape:
        sys.exit(f"undistort() returned shape {flat.shape}, not {img.shape}: python3 run_lens.py test")
    board = fe.BOARD
    c0, c1 = fe.find_corners(img, board), fe.find_corners(flat, board)
    if c0 is None:
        sys.exit(f"no whole chessboard in {name}: try another view")
    b0 = worst_bend(c0, board)
    print(f"{name}: the most bent chessboard row or column, in the fisheye picture: {b0:.2f} px from a straight line")
    if c1 is None:
        print("  no whole chessboard in the straightened picture (part of it fell outside the 111° view): try f0216")
        b1 = None
    else:
        b1 = worst_bend(c1, board)
        print(f"{name}: the same, in YOUR straightened 111° picture:                      {b1:.2f} px")
    both = np.vstack([draw(img, c0, board, f"{name} fisheye: worst line {b0:.1f} px"),
                      draw(flat, c1, board, "straightened 111 deg" + (f": {b1:.1f} px" if b1 is not None else ""))])
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "before_after.jpg"), both)
    rk.saved("out/before_after.jpg (red: each row's first and last corner joined by a straight line)")


if __name__ == "__main__":
    modes = {"test": test, "project": project_mode, "curve": curve_mode, "stretch": stretch_mode}
    if len(sys.argv) >= 2 and sys.argv[1] == "straighten":
        straighten_mode(*(sys.argv[2:3] or ["f0216"]))
    elif len(sys.argv) != 2 or sys.argv[1] not in modes:
        sys.exit(__doc__)
    else:
        modes[sys.argv[1]]()
