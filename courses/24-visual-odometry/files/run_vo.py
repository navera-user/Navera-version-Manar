"""run_vo.py — runs YOUR functions of navera_lite/vo.py on the lab's flight and frame pairs, and draws them.

  Session 1 — Odometer
    python3 run_vo.py test            check each TODO of vo.py on its docstring example
    python3 run_vo.py look            the flight's frames on one sheet                                  (Step 0)
    python3 run_vo.py pair 10         one step, frames 9 → 10: your phase correlation and OpenCV's       (Step 1)
    python3 run_vo.py compare         your FFT against cv2.phaseCorrelate on the first leg              (Step 2)
    python3 run_vo.py leg             dead reckoning along the first leg (frames 0–51)                  (Steps 3–4)
          options:  --altitude A        use A metres instead of the barometer's height
                    --heading-offset D  add D degrees to every IMU heading
    python3 run_vo.py odometers       six odometers on 40 frame pairs, one of them with YOUR descriptor  (Step 5)
          option:   --weights FILE      (default: my_desc.pt here, else ../21-features/my_desc.pt, else ref_desc.pt)
  Session 2 — Navigator
    python3 drift_sim.py              random walk and bias, simulated                                  (Step 6)
    python3 run_vo.py responses       the peak response of every step of the whole flight              (Step 7)
    python3 run_vo.py fuse            the whole flight: threshold, gate, map fixes, stated σ           (Steps 8–9)
          options:  --min-response R  (default: MIN_RESPONSE of answers.py)   --sigma-step S (m, default 0.3)
                    --bias B (m, default 0.7)   --sigma-gate G (m/s, default 2.0)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab. Frames: map data © OpenStreetMap
contributors.
"""
import csv
import math
import os
import sys
import time

import cv2
import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = "/data/academy/24-visual-odometry"
OUT = "out"
HFOV_DEG, WIDTH_PX = 70.0, 320
LEG = 51                    # the first leg: steps 1–51 (frames 0–51), over the city, before the sea
GOOD_M = 2.5                # a step is "right" when it is within 2.5 m of the true step
_kit_hint = rk._hint


def _hint(e):
    s = str(e)
    if "operands could not be broadcast" in s:
        return " — a and b must have the same shape; the window must have the image's shape (h, w), in that order"
    if "math domain" in s or "must be real number, not" in s:
        return " — math.sin/cos take one number in radians: math.radians(heading_deg)"
    if "unhashable type" in s:
        return " — a numpy array cannot be a dict key or a set member"
    return _kit_hint(e)


rk._hint = _hint
vo = rk.load_student("navera_lite.vo")
from navera_lite.camera import gsd  # noqa: E402  (mission 18, finished)


# ------------------------------------------------------------------ data
def need_data():
    if not os.path.isdir(DATA):
        sys.exit(f"cannot find {DATA} — is the data folder mounted? (ls /data/academy)")


def load_flight():
    need_data()
    with open(os.path.join(DATA, "flight.csv")) as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(DATA, "truth.csv")) as f:
        truth = np.array([[float(r["east_m"]), float(r["north_m"])] for r in csv.DictReader(f)])
    with open(os.path.join(DATA, "map_fixes.csv")) as f:
        fixes = {int(r["frame"]): (float(r["east_m"]), float(r["north_m"]), float(r["sigma_m"]))
                 for r in csv.DictReader(f)}
    files = [os.path.join(DATA, r["file"]) for r in rows]
    heading = np.array([float(r["heading_deg"]) for r in rows])
    baro = np.array([float(r["baro_alt_m"]) for r in rows])
    return files, heading, baro, truth, fixes


def gray(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        sys.exit(f"cannot read {path}")
    return img.astype(np.float32)


def turn_between(h0, h1):
    """Heading change from h0 to h1 in degrees, in −180 … 180 (359° → 1° is a turn of +2°)."""
    return (h1 - h0 + 180.0) % 360.0 - 180.0


def stamp(img):
    out = img.copy()
    cv2.putText(out, "(c) OpenStreetMap contributors", (6, out.shape[0] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                (255, 255, 255), 1, cv2.LINE_AA)
    return out


def save_png(path, img):
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, path), img)
    rk.saved(os.path.join(OUT, path))


def shift_ok(fn, v):
    """Stop with one plain sentence when phase_shift does not return three numbers."""
    try:
        dx, dy, r = (float(x) for x in v)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return three numbers (dx, dy, response), but it returned {v!r}")
    return dx, dy, r


def measure_step(files, heading, i, method="numpy"):
    """Frames i−1 → i: the previous frame derotated by the IMU heading change, then the shift."""
    a = vo.derotate(gray(files[i - 1]), turn_between(heading[i - 1], heading[i]))
    b = gray(files[i])
    if method == "opencv":
        return vo.opencv_shift(a, b)
    return shift_ok("phase_shift", rk.need_ok(vo, "phase_shift", a, b))


def en(dx, dy, mpp, hdg):
    v = rk.need_ok(vo, "px_to_en", dx, dy, mpp, hdg, n=2)
    return float(v[0]), float(v[1])


def track_of(steps, start=(0.0, 0.0)):
    t = rk.need_ok(vo, "integrate", steps, start)
    t = np.asarray(t, dtype=float)
    if t.shape != (len(steps) + 1, 2):
        sys.exit(f"integrate() must return an array of shape ({len(steps) + 1}, 2) for {len(steps)} steps, "
                 f"got shape {t.shape} — row 0 is the start")
    return t


# ------------------------------------------------------------------ test
def close(v, want, tol):
    try:
        return np.allclose(np.asarray(v, dtype=float), np.asarray(want, dtype=float), atol=tol)
    except (TypeError, ValueError):
        return False


def show(v):
    if isinstance(v, np.ndarray):
        return np.array2string(np.round(v, 3), separator=", ").replace("\n", "")
    if isinstance(v, tuple):
        return "(" + ", ".join(show(x) for x in v) + ")"
    if isinstance(v, float):
        return f"{v:.4g}"
    return repr(v)


def test():
    print("TODO  function       result")
    ok_all = True

    def line(todo, name, got, err, good, note):
        nonlocal ok_all
        if err:
            print(f"✘ {todo:<4} {name:14s} {err}")
            ok_all = False
        elif good:
            print(f"✔ {todo:<4} {name:14s} {show(got)}")
        else:
            print(f"✘ {todo:<4} {name:14s} got {show(got)} — {note}")
            ok_all = False

    g = np.random.default_rng(0).random((64, 80))
    v, e = rk.call(vo, "phase_shift", g, np.roll(g, (2, -5), axis=(0, 1)))
    if not e and not (isinstance(v, tuple) and len(v) == 3):
        e = f"phase_shift() must return three numbers (dx, dy, response), got {v!r}"
    note = "the docstring says about (-5.00, 2.00, 0.93). "
    if not e:
        dx, dy, r = (float(x) for x in v)
        if abs(dx - 75) < 0.6:
            note += "75 = 80 − 5: a shift past half the width is negative (lesson §3, detail 1)"
        elif abs(dx - 2) < 0.6 and abs(dy + 5) < 0.6:
            note += "x and y are swapped: np.unravel_index gives (row, column) = (y, x)"
        elif abs(dx - 5) < 0.6 and abs(dy + 2) < 0.6:
            note += "both signs are reversed: the cross-power spectrum is B · conj(A), not A · conj(B)"
        elif r > 1.5 or r < 0.01:
            note += f"the response {r:.3g} is not a peak between 0 and 1: divide B·conj(A) by its magnitude"
        else:
            note += "Lab Step 1, hints"
        line(1, "phase_shift", (dx, dy, r), None, abs(dx + 5) < 0.05 and abs(dy - 2) < 0.05 and 0.5 < r <= 1.01, note)
    else:
        line(1, "phase_shift", None, e, False, "")
    v, e = rk.call(vo, "px_to_en", 0.0, 10.0, 0.5, 90.0)
    note = "the docstring says (5.0, 0.0). "
    if not e and close(v, (0.0, 5.0), 1e-6):
        note += "east and north swapped, or the heading not used: heading 90° means the frame's top points east"
    elif not e and close(v, (-5.0, 0.0), 1e-6):
        note += "the sign of forward: the ground slid DOWN (dy > 0), so the drone flew FORWARD"
    elif not e and close(v, (0.0, -5.0), 1e-6):
        note += "a heading of 0 instead of 90? or math.sin of degrees? (math.radians)"
    else:
        note += "Lab Step 3, hints"
    line(2, "px_to_en", v, e, not e and close(v, (5.0, 0.0), 1e-6), note)
    v2, e2 = rk.call(vo, "px_to_en", -10.0, 0.0, 0.5, 0.0)
    line(2, "px_to_en", v2, e2, not e2 and close(v2, (5.0, 0.0), 1e-6),
         "(−10, 0) px at heading 0 must give (5, 0): the ground slid LEFT, so the drone moved RIGHT = east")
    v, e = rk.call(vo, "integrate", [(1.0, 0.0), (0.0, 2.0)], (10.0, 10.0))
    note = "the docstring says [[10, 10], [11, 10], [11, 12]]. "
    if not e and np.asarray(v).shape == (2, 2):
        note += "2 rows for 2 steps: row 0 must be the start"
    elif not e and close(v, [[0, 0], [1, 0], [1, 2]], 1e-9):
        note += "the start is missing: begin at `start`"
    else:
        note += "Lab Step 3, hints"
    line(3, "integrate", v if e else np.asarray(v), e,
         not e and np.asarray(v).shape == (3, 2) and close(v, [[10, 10], [11, 10], [11, 12]], 1e-9), note)
    v, e = rk.call(vo, "median_shift", [(0, 0), (10, 10), (50, 5)], [(3, 1), (13, 11), (0, 0)])
    note = "the docstring says (3.0, 1.0, 2). "
    if not e and isinstance(v, tuple) and len(v) == 3 and close(v[:2], (-14.67, -1.0), 0.02):
        note += "that is the MEAN: one wrong match pulls it far away — use the median (lesson §4)"
    else:
        note += "Lab Step 5, hints"
    line(4, "median_shift", v, e, not e and isinstance(v, tuple) and len(v) == 3 and close(v, (3, 1, 2), 1e-9), note)
    for args, want in (((25, 1.0, 0.0), 5.0), ((25, 0.0, 0.2), 5.0), ((0, 1.0, 0.2), 0.0), ((25, 1.0, 0.2), 50 ** 0.5)):
        v, e = rk.call(vo, "drift_sigma", *args)
        note = f"the docstring says {want:.4g}. "
        if not e and args == (25, 1.0, 0.0) and close(v, 25.0, 1e-6):
            note += "random errors do not grow like n: their VARIANCES add (lesson §7)"
        elif not e and args == (25, 1.0, 0.2) and close(v, 10.0, 1e-6):
            note += "5 + 5: the two parts are independent — add their VARIANCES (squares), then one square root"
        else:
            note += "Lab Step 6, hints"
        line(5, "drift_sigma", v, e, not e and close(v, want, 1e-9), note)
    ds = rk.load_student("drift_sim")
    v, e = rk.call(ds, "simulate_drift", 100, 0.0, 0.1)
    if not e and np.asarray(v).shape != (100,):
        e = f"simulate_drift(100, …) must return 100 numbers, got shape {np.asarray(v).shape}"
    line(6, "simulate_drift", None if e else f"[{float(v[0]):.3f}, {float(v[1]):.3f}, …, {float(v[-1]):.3f}]", e,
         not e and close(v, 0.1 * np.arange(1, 101), 1e-9),
         "the docstring says [0.1, 0.2, …, 10.0]: the error after k steps is the SUM of k step errors (np.cumsum)")
    v, e = rk.call(ds, "simulate_drift", 100, 0.5, 0.0)
    line(6, "simulate_drift", None if e else f"after 100 steps {float(np.asarray(v)[-1]):.3f}", e,
         not e and np.asarray(v).shape == (100,) and 4.7 < float(np.asarray(v)[-1]) < 5.3,
         "the docstring says about 5.0: the RMS over the trials (square, mean over axis 0, square root) of the sums")
    v, e = rk.call(vo, "blend", 10.0, 9.0, 16.0, 3.0)
    note = "the docstring says (14.5, 2.25). "
    if not e and close(v, (11.5, 2.25), 1e-6):
        note += "the weights are swapped: the estimate with the SMALLER variance must count more"
    elif not e and isinstance(v, tuple) and len(v) == 2 and close(v[0], 14.5, 1e-6):
        note += "the blended variance is v1·v2 / (v1 + v2) (lesson §8)"
    else:
        note += "Lab Step 8, hints"
    line(7, "blend", v, e, not e and close(v, (14.5, 2.25), 1e-9), note)
    v, e = rk.call(vo, "vo_gate", (20.0, 0.0), (19.0, 1.0), 1.0)
    v2, e2 = rk.call(vo, "vo_gate", (0.0, 0.0), (20.0, 0.0), 2.0)
    line(8, "vo_gate", (v, v2) if not (e or e2) else None, e or e2, not (e or e2) and v is True and v2 is False,
         "the docstring says (True, False); return a bool (True/False), from the distance between the two vectors")
    print()
    print("All the examples work. Run the lab's commands now." if ok_all else
          "Fix the ✘ lines from the top (a later TODO may wait: the lab says when you need it).")


# ------------------------------------------------------------------ session 1
def look():
    files, heading, baro, truth, _ = load_flight()
    tiles = []
    for i in range(0, len(files), 6):
        im = cv2.resize(cv2.imread(files[i]), (160, 120), interpolation=cv2.INTER_AREA)
        cv2.putText(im, f"{i}", (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
        tiles.append(im)
    while len(tiles) % 5:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[k:k + 5]) for k in range(0, len(tiles), 5)])
    save_png("flight_sheet.png", stamp(sheet))
    print(f"{len(files)} frames, one per second (every 6th frame on the sheet). Frame 0: barometer {baro[0]:.1f} m, "
          f"IMU heading {heading[0]:.1f}°.")
    print("The top of every frame points to the drone's heading: the drone flies towards the top of the picture.")


def pair(i):
    files, heading, baro, truth, _ = load_flight()
    if not 1 <= i < len(files):
        sys.exit(f"pair N: N must be 1 … {len(files) - 1} (frames N−1 → N)")
    turn = turn_between(heading[i - 1], heading[i])
    t0 = time.perf_counter()
    dx, dy, r = measure_step(files, heading, i)
    t_np = time.perf_counter() - t0
    t0 = time.perf_counter()
    ox, oy, orr = measure_step(files, heading, i, "opencv")
    t_cv = time.perf_counter() - t0
    print(f"frames {i - 1} → {i}   (IMU heading change {turn:+.2f}°: the runner turns frame {i - 1} by it first)")
    print(f"  your phase_shift : dx = {dx:+8.3f} px   dy = {dy:+8.3f} px   response {r:.3f}   ({1e3 * t_np:.1f} ms)")
    print(f"  OpenCV           : dx = {ox:+8.3f} px   dy = {oy:+8.3f} px   response {orr:.3f}   ({1e3 * t_cv:.1f} ms)"
          "  (another response measure: lesson §3)")
    v, err = rk.call(vo, "px_to_en", dx, dy, gsd(baro[i], HFOV_DEG, WIDTH_PX), heading[i])
    if err is None:
        te, tn = truth[i] - truth[i - 1]
        print(f"  the drone moved east {v[0]:+7.2f} m, north {v[1]:+7.2f} m   (truth {te:+7.2f}, {tn:+7.2f}; "
              f"barometer height {baro[i]:.1f} m)")
    else:
        print("  (east/north appear when TODO 2, px_to_en, is written)")
    a = vo.derotate(gray(files[i - 1]), turn)
    b = gray(files[i])
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    moved = cv2.warpAffine(a, M, (a.shape[1], a.shape[0]), borderMode=cv2.BORDER_CONSTANT, borderValue=128)
    diff = np.clip(128 + (b - moved), 0, 255)
    row = np.hstack([a, b, diff]).astype(np.uint8)
    row = cv2.cvtColor(row, cv2.COLOR_GRAY2BGR)
    c = (159, 119)
    cv2.arrowedLine(row, (c[0] + 320, c[1]), (int(c[0] + 320 + dx), int(c[1] + dy)), (0, 0, 255), 2, tipLength=0.2)
    for k, s in enumerate((f"frame {i - 1} (turned)", f"frame {i}", "difference after your shift")):
        cv2.putText(row, s, (6 + 320 * k, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    save_png(f"pair_{i}.png", stamp(row))
    print("  Right panel: frame i−1 moved by YOUR (dx, dy), subtracted from frame i. Grey and flat = right shift.")


def compare():
    files, heading, *_ = load_flight()
    d, tn, tc, rn, rc = [], [], [], [], []
    for i in range(1, LEG + 1):
        t0 = time.perf_counter()
        dx, dy, r = measure_step(files, heading, i)
        tn.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        ox, oy, orr = measure_step(files, heading, i, "opencv")
        tc.append(time.perf_counter() - t0)
        d.append(math.hypot(dx - ox, dy - oy))
        rn.append(r)
        rc.append(orr)
    d = np.array(d)
    print(f"first leg, {LEG} steps (frames 0–{LEG}), each frame derotated by the IMU first")
    print(f"  |your shift − OpenCV's shift| : mean {d.mean():.3f} px, largest {d.max():.3f} px (step {1 + d.argmax()})")
    print(f"  response   yours: median {np.median(rn):.3f} (from {min(rn):.3f} to {max(rn):.3f})   "
          f"OpenCV's: median {np.median(rc):.3f}")
    print(f"  time per step (with reading the frames): yours {1e3 * np.mean(tn):.1f} ms, OpenCV {1e3 * np.mean(tc):.1f} ms")
    if d.max() > 1.0:
        print("\n  ⚠ a difference above 1 px: your phase_shift disagrees with OpenCV on some steps — run "
              "`python3 run_vo.py pair " f"{1 + d.argmax()}` and look at the difference picture.")


def fit_scale_rotation(steps, true_steps):
    """The single scale k and rotation that best turn your steps into the true ones (least squares)."""
    zs = steps[:, 0] + 1j * steps[:, 1]
    zt = true_steps[:, 0] + 1j * true_steps[:, 1]
    k = (np.conj(zs) @ zt) / (np.conj(zs) @ zs)
    return abs(k), math.degrees(np.angle(k))           # rotation > 0: your steps point clockwise of the truth


def leg(altitude=None, heading_offset=0.0):
    files, heading, baro, truth, _ = load_flight()
    steps = []
    for i in range(1, LEG + 1):
        dx, dy, _ = measure_step(files, heading, i)
        h = baro[i] if altitude is None else altitude
        steps.append(en(dx, dy, gsd(h, HFOV_DEG, WIDTH_PX), heading[i] + heading_offset))
    steps = np.array(steps)
    tr = track_of([tuple(s) for s in steps])
    true = truth[:LEG + 1]
    err = np.hypot(*(tr - true).T)
    length = float(np.sum(np.hypot(*np.diff(true, axis=0).T)))
    k, rot = fit_scale_rotation(steps, np.diff(true, axis=0))
    what = "barometer height" if altitude is None else f"height {altitude:g} m"
    if heading_offset:
        what += f", IMU heading {heading_offset:+g}°"
    print(f"first leg: {LEG} steps, {length:.0f} m flown ({what})")
    print(f"  error at the end : {err[-1]:.2f} m  →  drift {100 * err[-1] / length:.2f} m per 100 m flown")
    print(f"  your steps vs the true steps: the truth is {k:.3f} × your step length, and your steps point "
          f"{abs(rot):.2f}° {'clockwise' if rot >= 0 else 'anticlockwise'} of the true ones")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
        ax[0].plot(true[:, 0], true[:, 1], "k-", lw=2, label="truth")
        ax[0].plot(tr[:, 0], tr[:, 1], "-", color="#d64545", label="your visual odometry")
        ax[0].plot(*true[0], "k^", ms=9)
        ax[0].set_aspect("equal")
        ax[0].set_xlabel("east (m)")
        ax[0].set_ylabel("north (m)")
        ax[0].legend()
        ax[0].grid(alpha=0.3)
        ax[1].plot(err, color="#d64545")
        ax[1].set_xlabel("frame (one per second, 20 m apart)")
        ax[1].set_ylabel("error (m)")
        ax[1].grid(alpha=0.3)
        ax[0].set_title("first leg (map data © OpenStreetMap contributors)", fontsize=9)
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "leg.png"), dpi=80, bbox_inches="tight")
        plt.close(fig)
        rk.saved(os.path.join(OUT, "leg.png"))


def find_weights(arg):
    for p in ([arg] if arg else ["my_desc.pt", "../21-features/my_desc.pt", "ref_desc.pt"]):
        if p and os.path.exists(p):
            return p
    sys.exit("no descriptor weights found (my_desc.pt, ../21-features/my_desc.pt or ref_desc.pt)")


def odometers(weights=None):
    need_data()
    with open(os.path.join(DATA, "pairs.csv")) as f:
        rows = list(csv.DictReader(f))
    path = find_weights(weights)
    from academy_gpu import torch_device
    from navera_lite.learned_desc import load_weights
    methods = ["phase", "phase+IMU", "OpenCV+IMU", "ORB+IMU", "learned+IMU", "ORB fit"]
    res = {}
    with torch_device(wait_s=30) as device:
        try:
            model = load_weights(path, device)
        except Exception as e:                                       # noqa: BLE001
            sys.exit(f"{path} cannot be loaded as PatchNet weights ({type(e).__name__}): train it again in "
                     "mission 21, or use --weights ref_desc.pt")
        print(f"descriptor weights: {path}   (PatchNet on {device})\n")
        vo.keypoint_matches(np.zeros((240, 320), np.uint8), np.zeros((240, 320), np.uint8), "orb")   # warm-up
        for r in rows:
            k = int(r["pair"])
            a = gray(os.path.join(DATA, "pairs", f"a_{k:02d}.jpg"))
            b = gray(os.path.join(DATA, "pairs", f"b_{k:02d}.jpg"))
            truth = np.array([float(r["true_dx_px"]), float(r["true_dy_px"])])
            ra = vo.derotate(a, float(r["turn_deg"]))
            out = {}
            t0 = time.perf_counter()
            out["phase"] = shift_ok("phase_shift", rk.need_ok(vo, "phase_shift", a, b))[:2]
            out["phase+IMU"] = shift_ok("phase_shift", rk.need_ok(vo, "phase_shift", ra, b))[:2]
            t_phase = (time.perf_counter() - t0) / 2
            out["OpenCV+IMU"] = vo.opencv_shift(ra, b)[:2]
            times = {"phase": t_phase, "phase+IMU": t_phase}
            for m, name in (("orb", "ORB+IMU"), ("learned", "learned+IMU")):
                t0 = time.perf_counter()
                p1, p2 = vo.keypoint_matches(ra, b, m, model, device=device)
                v = rk.need_ok(vo, "median_shift", p1, p2, 1.0)
                times[name] = time.perf_counter() - t0
                out[name] = (None, None) if v[0] is None else (float(v[0]), float(v[1]))
            p1, p2 = vo.keypoint_matches(a, b, "orb")
            out["ORB fit"] = (None, None)
            if len(p1) >= 3:
                M, _ = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                if M is not None:
                    c = np.array([(a.shape[1] - 1) / 2.0, (a.shape[0] - 1) / 2.0])
                    q = M[:, :2] @ c + M[:, 2]
                    out["ORB fit"] = tuple(q - c)
            for m in methods:
                dx, dy = out[m]
                e = 1e9 if dx is None else math.hypot(dx - truth[0], dy - truth[1])
                res.setdefault((r["group"], m), []).append(e)
                if m in times:
                    res.setdefault(("time", m), []).append(times[m])
    groups = ["straight", "turn4", "turn12", "turn30", "sea"]
    print("right = within 1 px of the true shift, out of 8 pairs (median error in px)\n")
    print(f"{'group':9s}" + "".join(f"{m:>15s}" for m in methods))
    for g in groups:
        cells = []
        for m in methods:
            e = np.array(res[(g, m)])
            med = np.median(e)
            cells.append(f"{int((e <= 1.0).sum())}/8 ({med:6.2f})" if med < 1e3 else f"{int((e <= 1.0).sum())}/8 (  —  )")
        print(f"{g:9s}" + "".join(f"{c:>15s}" for c in cells))
    print(f"{'ms/pair':9s}" + "".join(f"{1e3 * np.mean(res[('time', m)]):15.1f}" if ('time', m) in res else f"{'':15s}"
                                       for m in methods))
    print("\nphase = your phase_shift; +IMU = frame a turned by the IMU heading change first (derotate);"
          "\nORB/learned = keypoints matched with ORB's bits or YOUR PatchNet, then YOUR median_shift;"
          "\nORB fit = keypoints + OpenCV's RANSAC fit of a turn and a shift (no IMU). Times: this machine, now.")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(10, 3.8))
        w = 0.13
        for j, m in enumerate(methods):
            ax.bar(np.arange(len(groups)) + (j - 2.5) * w, [np.sum(np.array(res[(g, m)]) <= 1.0) for g in groups], w,
                   label=m)
        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(groups)
        ax.set_ylabel("pairs right (of 8)")
        ax.legend(fontsize=8, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.1))
        ax.grid(alpha=0.3, axis="y")
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "odometers.png"), dpi=80, bbox_inches="tight")
        plt.close(fig)
        rk.saved(os.path.join(OUT, "odometers.png"))


# ------------------------------------------------------------------ session 2
def measure_flight():
    files, heading, baro, truth, fixes = load_flight()
    meas = []
    for i in range(1, len(files)):
        dx, dy, r = measure_step(files, heading, i)
        e, n = en(dx, dy, gsd(baro[i], HFOV_DEG, WIDTH_PX), heading[i])
        meas.append((dx, dy, r, e, n))
    return np.array(meas), heading, truth, fixes


def responses():
    meas, heading, truth, _ = measure_flight()
    err = np.hypot(*(meas[:, 3:5] - np.diff(truth, axis=0)).T)
    right = err < GOOD_M
    steps = np.arange(1, len(meas) + 1)
    print(f"whole flight: {len(meas)} steps. A step is RIGHT when it is within {GOOD_M} m of the true step.\n")
    print("right steps, the 6 lowest responses : " + ", ".join(f"{x:.3f} (step {s})" for x, s in
                                                             sorted(zip(meas[right, 2], steps[right]))[:6]))
    wr = sorted(zip(meas[~right, 2], steps[~right]))
    print(f"wrong steps ({len(wr)}), sorted by response:")
    for k in range(0, len(wr), 6):
        print("   " + ", ".join(f"{x:.3f} (step {s})" for x, s in wr[k:k + 6]))
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.semilogy(steps[right], meas[right, 2], "o", color="#0b6e8a", ms=4, label="right step")
        ax.semilogy(steps[~right], meas[~right, 2], "x", color="#d64545", ms=6, label="wrong step")
        ax.set_xlabel("step (frame i−1 → i)")
        ax.set_ylabel("your response (log scale)")
        ax.grid(alpha=0.3, which="both")
        ax.legend()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "responses.png"), dpi=80, bbox_inches="tight")
        plt.close(fig)
        rk.saved(os.path.join(OUT, "responses.png"))


def turn_vector(v, deg):
    """An (east, north) vector turned clockwise by deg degrees (a heading change)."""
    t = math.radians(deg)
    return np.array([v[0] * math.cos(t) + v[1] * math.sin(t), -v[0] * math.sin(t) + v[1] * math.cos(t)])


def navigate(meas, heading, fixes, min_resp, use_gate, use_fixes, sigma_step, bias, sigma_gate,
             hold_sigma=2.0, max_ref_age=10):
    """Dead reckoning with your odometry: refuse weak steps (min_resp) and steps the gate refuses; a refused step
    is replaced by the last accepted step turned by the IMU heading change since then; map fixes are blended in.
    Returns (track (n+1, 2), sigma per axis (n+1), status list)."""
    pos, anchor_var, n_meas, n_hold = np.zeros(2), 0.0, 0, 0
    ref, ref_hdg, ref_age = None, 0.0, 10 ** 9
    track, sig, status = [pos.copy()], [0.0], []
    for i in range(1, len(meas) + 1):
        dx, dy, r, e, n = meas[i - 1]
        step = np.array([e, n])
        why = "ok"
        if r < min_resp:
            why = "weak"
        elif use_gate and ref is not None and ref_age <= max_ref_age:
            expect = turn_vector(ref, heading[i] - ref_hdg)
            ok = rk.need_ok(vo, "vo_gate", (float(e), float(n)), (float(expect[0]), float(expect[1])), sigma_gate,
                            kind=bool)
            if not ok:
                why = "gate"
        if why == "ok":
            ref, ref_hdg, ref_age = step, heading[i], 1
            n_meas += 1
        else:
            ref_age += 1
            n_hold += 1
            step = np.zeros(2) if ref is None else turn_vector(ref, heading[i] - ref_hdg)
        pos = pos + step
        ds = rk.need_ok(vo, "drift_sigma", n_meas, sigma_step, bias, kind=float)
        var = anchor_var + ds ** 2 + n_hold * hold_sigma ** 2
        if use_fixes and i in fixes:
            fe, fn, fs = fixes[i]
            v = rk.need_ok(vo, "blend", pos, np.array([var, var]), np.array([fe, fn]), np.array([fs * fs, fs * fs]))
            if not (isinstance(v, tuple) and len(v) == 2):
                sys.exit(f"blend() must return two things (x, v), got {type(v).__name__}")
            pos, var = np.asarray(v[0], dtype=float), float(np.asarray(v[1], dtype=float).ravel()[0])
            if pos.shape != (2,):
                sys.exit("blend() on arrays must return arrays: east and north at once (element by element)")
            anchor_var, n_meas, n_hold = var, 0, 0
            why += "+fix"
        track.append(pos.copy())
        sig.append(math.sqrt(var))
        status.append(why)
    return np.array(track), np.array(sig), status


def read_min_response(arg):
    if arg is not None:
        return float(arg)
    ans = rk.load_student("answers")
    v = getattr(ans, "MIN_RESPONSE", 0.0)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        sys.exit("Write your threshold MIN_RESPONSE in answers.py first (lab Step 7), or give --min-response R")
    return float(v)


def fuse(min_resp=None, sigma_step=0.3, bias=0.7, sigma_gate=2.0):
    min_resp = read_min_response(min_resp)
    meas, heading, truth, fixes = measure_flight()
    stages = [("A  every step, no fix", 0.0, False, False), (f"B  + threshold {min_resp:g}", min_resp, False, False),
              ("C  + gate", min_resp, True, False), ("D  + map fixes", min_resp, True, True)]
    print(f"whole flight, {len(meas)} steps; σ model: sigma_step {sigma_step} m, bias {bias} m per step; gate "
          f"3 × {sigma_gate} m/s\n")
    print(f"{'stage':26s}{'weak':>6s}{'gate':>6s}{'worst error':>13s}{'final error':>13s}{'within 2σ':>11s}")
    runs = {}
    for name, mr, g, fx in stages:
        tr, sig, st = navigate(meas, heading, fixes, mr, g, fx, sigma_step, bias, sigma_gate)
        err = np.hypot(*(tr - truth).T)
        cover = float(np.mean(err[1:] <= 2 * sig[1:]))
        runs[name] = (tr, sig, err)
        nw = sum(s.startswith("weak") for s in st)
        ng = sum(s.startswith("gate") for s in st)
        print(f"{name:26s}{nw:6d}{ng:6d}{err.max():11.1f} m{err[-1]:11.1f} m{100 * cover:10.0f} %")
    gated = [i + 1 for i, s in enumerate(st) if s.startswith("gate")]
    print(f"\nsteps refused by your gate in D: {gated}")
    print("within 2σ = share of frames whose true error (distance) is at most twice the stated σ (per axis).")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
        ax[0].plot(truth[:, 0], truth[:, 1], "k-", lw=2, label="truth")
        for (name, (tr, sig, err)), col in zip(runs.items(), ("#bbbbbb", "#f2a33a", "#d64545", "#0b6e8a")):
            ax[0].plot(tr[:, 0], tr[:, 1], "-", color=col, label=name)
        fx = np.array([v[:2] for v in fixes.values()])
        ax[0].plot(fx[:, 0], fx[:, 1], "o", color="#0b6e8a", mfc="none", label="map fixes")
        ax[0].set_aspect("equal")
        ax[0].set_xlim(truth[:, 0].min() - 150, truth[:, 0].max() + 150)
        ax[0].set_ylim(truth[:, 1].min() - 150, truth[:, 1].max() + 150)
        ax[0].legend(fontsize=7)
        ax[0].grid(alpha=0.3)
        ax[0].set_xlabel("east (m)")
        ax[0].set_ylabel("north (m)")
        tr, sig, err = runs[stages[-1][0]]
        ax[1].plot(err, color="#0b6e8a", label="true error, D")
        ax[1].plot(2 * sig, "--", color="#0b6e8a", lw=1, label="2σ stated, D")
        ax[1].plot(runs[stages[2][0]][2], color="#d64545", lw=1, label="true error, C (no fixes)")
        for i in fixes:
            ax[1].axvline(i, color="#f2a33a", lw=0.8, ls=":")
        ax[1].axvspan(52, 77, color="#0b6e8a", alpha=0.08, label="over the sea")
        ax[1].set_ylim(0, max(80.0, 1.1 * float(np.max(2 * sig))))
        ax[1].set_xlabel("frame")
        ax[1].set_ylabel("metres")
        ax[1].legend(fontsize=8)
        ax[1].grid(alpha=0.3)
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "fuse.png"), dpi=80, bbox_inches="tight")
        plt.close(fig)
        rk.saved(os.path.join(OUT, "fuse.png"))


# ------------------------------------------------------------------ command line
def option(args, name, default=None, kind=float):
    if name in args:
        k = args.index(name)
        try:
            return kind(args[k + 1])
        except (IndexError, ValueError):
            sys.exit(f"{name} needs a number after it")
    return default


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "test":
        test()
    elif cmd == "look":
        look()
    elif cmd == "pair":
        try:
            pair(int(args[0]) if args else 10)
        except ValueError:
            sys.exit("pair N: N is a whole number, e.g. python3 run_vo.py pair 10")
    elif cmd == "compare":
        compare()
    elif cmd == "leg":
        leg(option(args, "--altitude"), option(args, "--heading-offset", 0.0))
    elif cmd == "odometers":
        odometers(option(args, "--weights", None, str))
    elif cmd == "responses":
        responses()
    elif cmd == "fuse":
        fuse(option(args, "--min-response"), option(args, "--sigma-step", 0.3), option(args, "--bias", 0.7),
             option(args, "--sigma-gate", 2.0))
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main(sys.argv[1:])
