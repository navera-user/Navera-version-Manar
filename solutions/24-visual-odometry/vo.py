"""Lesson 24 — Visual odometry: measure the camera's motion from the images alone.

Run:   python3 vo.py sheet                  contact sheet of the flight's photos (frames.png)
       python3 vo.py pair 10                one step: frames 10 -> 11, your FFT vs OpenCV
       python3 vo.py compare                your phase correlation vs cv2.phaseCorrelate on all 79 pairs
       python3 vo.py heading 10             the same step with heading-up photos (TODO 4 with a heading)
       python3 vo.py                        the whole flight: odometry, drift, fusion -> PNGs + results.json
       python3 vo.py --altitude 114.25      the same with another height than the barometer's
       python3 vo.py navera                 NAVERA's own FrameOdometry on the same flight
"""
import csv
import json
import math
import os
import sys

import cv2
import numpy as np

DATA = "/data/academy/24-visual-odometry"


# TODO 1: ground size of one pixel of a nadir camera (lesson 18)
def frame_m_per_px(altitude_m, hfov_deg, width_px):
    """m per pixel = footprint width / image width, footprint width = 2 h tan(HFOV / 2)."""
    return 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0) / width_px


# TODO 2: phase correlation with numpy's FFT
def phase_correlation(a, b):
    """Shift (dx, dy) of the content of b relative to a, in pixels, and the peak value.

    a, b: 2-D float arrays of the same shape. Returns (dx, dy, response):
    dx > 0 when the content moved RIGHT in b, dy > 0 when it moved DOWN.
    """
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))           # 2-D Hanning window
    Fa = np.fft.fft2(a * win)
    Fb = np.fft.fft2(b * win)
    cross = Fb * np.conj(Fa)                               # cross-power spectrum
    cross /= np.abs(cross) + 1e-12                         # keep the phase only
    r = np.real(np.fft.ifft2(cross))                       # a sharp peak at the shift
    py, px = np.unravel_index(np.argmax(r), r.shape)
    response = float(r[py, px])

    def refine(cm, c0, cp):                                # parabola through 3 points
        den = cm - 2.0 * c0 + cp
        return 0.0 if abs(den) < 1e-12 else 0.5 * (cm - cp) / den

    fx = refine(r[py, (px - 1) % w], r[py, px], r[py, (px + 1) % w])
    fy = refine(r[(py - 1) % h, px], r[py, px], r[(py + 1) % h, px])
    dx, dy = px + fx, py + fy
    if dx > w / 2:                                         # indices past the middle are negative shifts
        dx -= w
    if dy > h / 2:
        dy -= h
    return float(dx), float(dy), response


# TODO 3: the slide of the ground between two frames
def frame_shift(prev, cur, method="numpy"):
    """(dx, dy) in pixels of the ground from prev to cur (dx > 0 right, dy > 0 down).
    method "numpy": your phase_correlation(); "opencv": cv2.phaseCorrelate."""
    a, b = to_grey_float(prev), to_grey_float(cur)
    if method == "numpy":
        dx, dy, _ = phase_correlation(a, b)
        return dx, dy
    if method == "opencv":
        win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
        (dx, dy), _ = cv2.phaseCorrelate(a, b, win)
        return dx, dy
    raise ValueError(f"unknown method {method!r}")


# TODO 4: from an image shift to the vehicle's motion, east / north
def shift_to_east_north(dx, dy, m_per_px, heading_deg=0.0):
    """(east, north) metres moved by the CAMERA when the ground slid (dx, dy) pixels.
    heading_deg: azimuth the image's top points to (0 = north-up photo)."""
    right = -dx * m_per_px                                 # the ground moves the other way
    fwd = dy * m_per_px                                    # image y points down
    th = math.radians(heading_deg)
    east = fwd * math.sin(th) + right * math.cos(th)
    north = fwd * math.cos(th) - right * math.sin(th)
    return east, north


# TODO 5: add up the steps
def integrate(steps, start=(0.0, 0.0)):
    """Track: track[0] = start, track[i] = track[i-1] + steps[i-1]."""
    track = [(float(start[0]), float(start[1]))]
    e, n = track[0]
    for de, dn in steps:
        e, n = e + de, n + dn
        track.append((e, n))
    return track


# TODO 6: drift in metres per 100 m flown
def drift_per_100m(track, truth):
    """100 x |track[-1] - truth[-1]| / (length of the true path)."""
    flown = sum(math.hypot(truth[i][0] - truth[i - 1][0], truth[i][1] - truth[i - 1][1])
                for i in range(1, len(truth)))
    err = math.hypot(track[-1][0] - truth[-1][0], track[-1][1] - truth[-1][1])
    return 100.0 * err / flown


# TODO 7: fuse the odometry with map fixes (a scalar Kalman update)
def fuse_with_fixes(steps, fixes, fix_sigma=4.0, k=0.1, c=1.0, start=(0.0, 0.0), start_sigma=0.0):
    """Odometry between fixes, Kalman update at each fix.

    After step i (1-based): position += step, sigma += k * |step| + c (NAVERA's growth).
    If i is a key of fixes (east, north): P = sigma^2, R = fix_sigma^2, K = P / (P + R),
    position += K (fix - position), sigma = sqrt((1 - K) P).
    Returns (track, sigmas), both with len(steps) + 1 entries."""
    e, n = float(start[0]), float(start[1])
    s = float(start_sigma)
    track, sigmas = [(e, n)], [s]
    for i, (de, dn) in enumerate(steps, start=1):
        e, n = e + de, n + dn
        s = s + k * math.hypot(de, dn) + c
        if i in fixes:
            P, R = s * s, fix_sigma * fix_sigma
            K = P / (P + R)
            e, n = e + K * (fixes[i][0] - e), n + K * (fixes[i][1] - n)
            s = math.sqrt((1.0 - K) * P)
        track.append((e, n))
        sigmas.append(s)
    return track, sigmas


# TODO 8: NAVERA's own visual odometry on the same frames
def navera_steps(frames, m_per_px):
    """Steps measured by NAVERA's FrameOdometry (frames are north-up: heading 0, one per second).
    Returns (steps, refused): a refused step (step() returned None) is replaced by the previous
    accepted step (constant velocity), or (0, 0) if there is none yet."""
    from frame_odometry import FrameOdometry
    vo = FrameOdometry()
    steps, refused, last = [], 0, (0.0, 0.0)
    for t, path in enumerate(frames):
        r = vo.step(cv2.imread(path), 0.0, m_per_px, float(t))
        if t == 0:
            continue
        if r is None:
            refused += 1
            steps.append(last)
        else:
            last = (r[0], r[1])
            steps.append(last)
    return steps, refused


# ---- you don't need to change anything below this line ----

NAVERA_DAY = os.path.expanduser("~/navera/day_pkg/day_pkg")
if os.path.isdir(NAVERA_DAY) and NAVERA_DAY not in sys.path:
    sys.path.append(NAVERA_DAY)                    # so that `from frame_odometry import ...` works


def to_grey_float(img):
    """A colour picture -> grey float32 (what phase correlation wants)."""
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img.astype(np.float32)


def load_flight():
    with open(os.path.join(DATA, "info.json")) as f:
        info = json.load(f)
    truth, frames, headings = [], [], []
    with open(os.path.join(DATA, "truth.csv")) as f:
        for r in csv.DictReader(f):
            truth.append((float(r["east_m"]), float(r["north_m"])))
            frames.append(os.path.join(DATA, "frames", r["file"]))
            headings.append(float(r["heading_deg"]))
    fixes = {}
    with open(os.path.join(DATA, "map_fixes.csv")) as f:
        for r in csv.DictReader(f):
            fixes[int(r["frame"])] = (float(r["east_m"]), float(r["north_m"]))
    return info, frames, truth, fixes, headings


def measure_steps(frames, m_per_px, method="numpy"):
    """Visual odometry: one (east, north) step per pair of consecutive (north-up) frames."""
    steps, prev = [], cv2.imread(frames[0])
    for path in frames[1:]:
        cur = cv2.imread(path)
        dx, dy = frame_shift(prev, cur, method)
        steps.append(shift_to_east_north(dx, dy, m_per_px, 0.0))
        prev = cur
    return steps


def errors(track, truth):
    return [math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(track, truth)]


def _plt():
    import warnings
    warnings.filterwarnings("ignore")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot(truth, track, fused, sigmas, fixes):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.plot(*zip(*truth), "-", color="#1d2733", lw=2, label="truth")
    ax.plot(*zip(*track), "-", color="#d64545", label="visual odometry only")
    if fused:
        ax.plot(*zip(*fused), "-", color="#0b6e8a", label="odometry + map fixes")
        ax.plot(*zip(*fixes.values()), "o", color="#f2a33a", label="map fixes")
    ax.plot(*truth[0], "k^", ms=9)
    ax.set_xlabel("east (m)")
    ax.set_ylabel("north (m)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Synthetic flight (NAVERA's Sousse map)")
    fig.savefig("vo_track.png", dpi=90, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.plot(errors(track, truth), color="#d64545", label="error, odometry only")
    if fused:
        ax.plot(errors(fused, truth), color="#0b6e8a", label="error, odometry + fixes")
        ax.plot([2 * s for s in sigmas], "--", color="#0b6e8a", lw=1, label="2 sigma stated")
        for i in fixes:
            ax.axvline(i, color="#f2a33a", lw=0.8, ls=":")
    ax.set_xlabel("frame (one per second, about 20 m apart)")
    ax.set_ylabel("metres")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.savefig("vo_error.png", dpi=90, bbox_inches="tight")
    plt.close(fig)


def show_pair(i):
    info, frames, truth, _, _ = load_flight()
    mpp = frame_m_per_px(info["altitude_m"], info["camera_hfov_deg"], info["width_px"])
    a, b = cv2.imread(frames[i]), cv2.imread(frames[i + 1])
    dx, dy, resp = phase_correlation(to_grey_float(a), to_grey_float(b))
    ox, oy = frame_shift(a, b, "opencv")
    te, tn = truth[i + 1][0] - truth[i][0], truth[i + 1][1] - truth[i][1]
    print(f"frames {i} -> {i + 1}")
    print(f"  your FFT : dx = {dx:+8.3f} px, dy = {dy:+8.3f} px, peak (response) {resp:.3f}")
    print(f"  OpenCV   : dx = {ox:+8.3f} px, dy = {oy:+8.3f} px")
    try:
        de, dn = shift_to_east_north(dx, dy, mpp)
        print(f"  camera moved east {de:+7.2f} m, north {dn:+7.2f} m   ({mpp:.4f} m/px, barometer height)")
    except NotImplementedError:
        print("  camera moved      (TODO 4 not done yet)")
    print(f"  truth says   east {te:+7.2f} m, north {tn:+7.2f} m")
    cv2.imwrite(f"pair_{i}.png", np.hstack([a, np.full((a.shape[0], 6, 3), 255, np.uint8), b]))
    print(f"  saved pair_{i}.png (left: frame {i}, right: frame {i + 1})")


def heading_up(img, heading_deg, size=160):
    """The north-up photo turned so its top points to heading_deg, centre crop size x size."""
    h, w = img.shape[:2]
    R = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), heading_deg, 1.0)   # positive = counter-clockwise
    out = cv2.warpAffine(img, R, (w, h), flags=cv2.INTER_LINEAR)
    y0, x0 = (h - size) // 2, (w - size) // 2
    return out[y0:y0 + size, x0:x0 + size]


def show_heading(i):
    info, frames, truth, _, headings = load_flight()
    mpp = frame_m_per_px(info["altitude_m"], info["camera_hfov_deg"], info["width_px"])
    hdg = headings[i]
    a = heading_up(cv2.imread(frames[i]), hdg)
    b = heading_up(cv2.imread(frames[i + 1]), hdg)
    dx, dy = frame_shift(a, b, "numpy")
    de, dn = shift_to_east_north(dx, dy, mpp, hdg)
    te, tn = truth[i + 1][0] - truth[i][0], truth[i + 1][1] - truth[i][1]
    print(f"frames {i} -> {i + 1} turned heading-up (top of the photo = {hdg:.1f} deg)")
    print(f"  the ground slid dx = {dx:+.2f} px, dy = {dy:+.2f} px  (mostly DOWN: the camera flies forward)")
    print(f"  with heading {hdg:.1f}: east {de:+7.2f} m, north {dn:+7.2f} m")
    print(f"  truth says           east {te:+7.2f} m, north {tn:+7.2f} m")
    cv2.imwrite(f"heading_{i}.png", np.hstack([a, np.full((a.shape[0], 6, 3), 255, np.uint8), b]))
    print(f"  saved heading_{i}.png")


def show_sheet():
    _, frames, _, _, _ = load_flight()
    small = [cv2.resize(cv2.imread(p), (160, 120)) for p in frames]
    rows = [np.hstack(small[r:r + 10]) for r in range(0, len(small), 10)]
    for k in range(len(small)):
        r, c = divmod(k, 10)
        cv2.putText(rows[r], str(k), (c * 160 + 4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite("frames.png", np.vstack(rows))
    print(f"saved frames.png: the {len(frames)} photos of the flight, 10 per row, in order")


def compare():
    _, frames, _, _, _ = load_flight()
    diffs, t_np, t_cv = [], 0.0, 0.0
    import time
    prev = cv2.imread(frames[0])
    for p in frames[1:]:
        cur = cv2.imread(p)
        t0 = time.perf_counter()
        a = frame_shift(prev, cur, "numpy")
        t1 = time.perf_counter()
        b = frame_shift(prev, cur, "opencv")
        t2 = time.perf_counter()
        t_np, t_cv = t_np + t1 - t0, t_cv + t2 - t1
        diffs.append(math.hypot(a[0] - b[0], a[1] - b[1]))
        prev = cur
    print(f"{len(diffs)} pairs: |yours - OpenCV| mean {np.mean(diffs):.3f} px, max {np.max(diffs):.3f} px")
    print(f"time per pair: yours {1000 * t_np / len(diffs):.1f} ms, OpenCV {1000 * t_cv / len(diffs):.1f} ms")
    return float(np.mean(diffs)), float(np.max(diffs))


def main(altitude=None):
    info, frames, truth, fixes, _ = load_flight()
    alt = info["altitude_m"] if altitude is None else altitude
    mpp = frame_m_per_px(alt, info["camera_hfov_deg"], info["width_px"])
    print(f"{len(frames)} frames, height {alt} m ({'barometer' if altitude is None else 'your value'}), "
          f"{info['camera_hfov_deg']} deg, {info['width_px']} px -> {mpp:.4f} m per pixel")
    steps = measure_steps(frames, mpp, "numpy")
    track = integrate(steps)
    err = errors(track, truth)
    drift = drift_per_100m(track, truth)
    print(f"odometry only : final error {err[-1]:6.1f} m, worst {max(err):6.1f} m, drift {drift:.2f} m per 100 m")
    fused, sig = None, None
    try:
        fused, sig = fuse_with_fixes(steps, fixes)
    except NotImplementedError:
        print("fuse_with_fixes(): TODO 7 not done yet — the plots show odometry only")
    res = {"height_m": alt, "m_per_px": round(mpp, 5), "final_error_vo_m": round(err[-1], 2),
           "worst_error_vo_m": round(max(err), 2), "drift_per_100m": round(drift, 3)}
    if fused is not None:
        errf = errors(fused, truth)
        inside = sum(1 for e, s in zip(errf[1:], sig[1:]) if e <= 2 * s) / (len(errf) - 1)
        print(f"with a map fix every {min(fixes)} frames: final error {errf[-1]:6.1f} m, worst {max(errf):6.1f} m, "
              f"stated 2 sigma covers the error on {100 * inside:.0f} % of the frames")
        res.update(worst_error_fused_m=round(max(errf), 2), final_error_fused_m=round(errf[-1], 2),
                   max_sigma_fused_m=round(max(sig), 2), inside_2sigma=round(inside, 3))
    plot(truth, track, fused, sig, fixes)
    print("saved vo_track.png and vo_error.png")
    if altitude is None:
        _save_results(res, "barometer")
    else:
        _save_results({"drift_per_100m": round(drift, 3), "height_m": alt}, "other_height")


def run_navera():
    info, frames, truth, _, _ = load_flight()
    mpp = frame_m_per_px(info["altitude_m"], info["camera_hfov_deg"], info["width_px"])
    steps, refused = navera_steps(frames, mpp)
    track = integrate(steps)
    err = errors(track, truth)
    d = drift_per_100m(track, truth)
    print(f"NAVERA FrameOdometry: {len(steps)} steps, {refused} refused; final error {err[-1]:.1f} m, "
          f"drift {d:.2f} m per 100 m")
    _save_results({"drift_per_100m": round(d, 3), "refused": refused}, "navera")


def _save_results(part, key):
    path = "results.json"
    try:
        with open(path) as f:
            allres = json.load(f)
    except (OSError, ValueError):
        allres = {}
    allres[key] = part
    with open(path, "w") as f:
        json.dump(allres, f, indent=1)
    print(f"results.json updated ({key})")


if __name__ == "__main__":
    try:
        args = sys.argv[1:]
        if len(args) >= 2 and args[0] == "pair":
            show_pair(int(args[1]))
        elif len(args) >= 2 and args[0] == "heading":
            show_heading(int(args[1]))
        elif args and args[0] == "sheet":
            show_sheet()
        elif args and args[0] == "compare":
            m, x = compare()
            _save_results({"mean_px": round(m, 4), "max_px": round(x, 4)}, "fft_vs_opencv")
        elif args and args[0] == "navera":
            run_navera()
        elif len(args) >= 2 and args[0] == "--altitude":
            main(float(args[1]))
        else:
            main()
    except NotImplementedError as e:
        print(f"Not finished yet: {e} is still to do. Read the lab, fill it in, save, and run again.")
        sys.exit(1)
