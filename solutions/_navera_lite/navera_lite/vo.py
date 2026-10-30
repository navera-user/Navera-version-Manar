"""navera_lite/vo.py — visual odometry: how far the ground slid between two frames (phase correlation, or
keypoints), how far the drone moved east and north, how the error of the sum grows, and how a fix bounds it.
Part of NAVERA Lite, the course's teaching stack (mission 24). Written for the course; it is not NAVERA code.

Conventions (mission 08 and 18): an image is a numpy array img[row, column] = img[y, x], (0, 0) at the TOP-LEFT,
y grows DOWNWARDS. A shift (dx, dy) in pixels says how the CONTENT moved from picture a to picture b: dx > 0 = to
the right, dy > 0 = downwards. Frames are "heading-up": the top of the picture points to the drone's heading
(degrees clockwise from north). East/north in metres (ENU). A variance is a σ², in m².
"""
import math

import cv2
import numpy as np


# ====================================================================== given helpers

# @part 24
def to_gray32(img):
    """A picture (BGR colour or grey, any dtype) as a grey float32 array — what phase correlation works on.

    Example: to_gray32(np.full((2, 3, 3), 200, np.uint8)) → a (2, 3) float32 array of 200.0
    """
    # from mission 24 — finished: read it, use it, do not change it
    a = np.asarray(img)
    if a.ndim == 3:
        a = cv2.cvtColor(a.astype(np.uint8) if a.dtype != np.uint8 else a, cv2.COLOR_BGR2GRAY)
    return a.astype(np.float32)


# @part 24
def derotate(img, turn_deg):
    """The picture `img`, taken BEFORE the drone turned by turn_deg degrees (heading change, clockwise > 0), turned
    about its centre so that it has the orientation of the next, heading-up frame. Then only a translation is left
    between the two (lesson §4). Borders are mirrored, so no black corners appear.

    Example: derotate(img, 0.0) → img unchanged (a float32 copy)
    """
    # from mission 24 — finished: read it, use it, do not change it
    a = np.asarray(img, dtype=np.float32)
    if abs(turn_deg) < 1e-9:
        return a.copy()
    h, w = a.shape[:2]
    R = cv2.getRotationMatrix2D(((w - 1) / 2.0, (h - 1) / 2.0), float(turn_deg), 1.0)
    return cv2.warpAffine(a, R, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# @part 24
def opencv_shift(a, b):
    """OpenCV's phase correlation: (dx, dy, response) of picture b against picture a, with a Hanning window.
    The same sign convention as your phase_shift (content moved right/down = positive). OpenCV's `response` is
    computed differently from yours (lesson §3): compare shifts, not responses.
    to_gray32 makes copies on purpose: with a window, cv2.phaseCorrelate overwrites the two pictures it is given
    (OpenCV 4.11).

    Example: opencv_shift(a, np.roll(a, 3, axis=1)) → about (3.0, 0.0, 0.95)   (a: a textured picture)
    """
    # from mission 24 — finished: read it, use it, do not change it
    a, b = to_gray32(a), to_gray32(b)
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)      # (width, height)!
    (dx, dy), resp = cv2.phaseCorrelate(a, b, win)
    return float(dx), float(dy), float(resp)


# ====================================================================== the odometer (session 1)

# @part 24 todo 1
def phase_shift(a, b):
    """Phase correlation with numpy's FFT (lesson §2–§3): how far the content of picture b moved against picture a.

    Inputs: a, b — 2-D arrays of the same shape (grey, any dtype). Returns (dx, dy, response): the shift in pixels,
    with sub-pixel precision (dx > 0: moved right, dy > 0: moved down; a shift past half the picture is negative),
    and the height of the correlation peak (about 1 for a perfect shifted copy, near 0 when nothing moved
    together), three floats.
    Example: g = np.random.default_rng(0).random((64, 80))
             phase_shift(g, np.roll(g, (2, -5), axis=(0, 1))) → about (-5.00, 2.00, 0.93)   (5 left, 2 down)
             and g moved by a FRACTION of a pixel, (2.4, −1.3) px (the runner's test makes it) → about (2.29, −1.18):
             between pixels (the parabola falls a little short), never the whole numbers (2, −1)
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    h, w = a.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    A = np.fft.fft2((a - a.mean()) * win)
    B = np.fft.fft2((b - b.mean()) * win)
    R = B * np.conj(A)
    R /= np.abs(R) + 1e-12
    r = np.real(np.fft.ifft2(R))
    py, px = np.unravel_index(np.argmax(r), r.shape)
    c0 = r[py, px]

    def vertex(cm, cp):
        den = cm - 2.0 * c0 + cp
        return 0.0 if abs(den) < 1e-12 else 0.5 * (cm - cp) / den

    dx = px + vertex(r[py, (px - 1) % w], r[py, (px + 1) % w])
    dy = py + vertex(r[(py - 1) % h, px], r[(py + 1) % h, px])
    if dx > w / 2:
        dx -= w
    if dy > h / 2:
        dy -= h
    return float(dx), float(dy), float(c0)


# @part 24 todo 2
def px_to_en(dx, dy, m_per_px, heading_deg):
    """The drone's motion (east_m, north_m) when the ground slid (dx, dy) pixels in a heading-up frame (lesson §5).
    The ground slides the OTHER way to the camera; the top of the frame points to heading_deg (clockwise from
    north).

    Returns two floats, metres.
    Example: px_to_en(0.0, 10.0, 0.5, 90.0) → (5.0, 0.0)   (the ground slid down: the drone flew forward, east)
    """
    right = -dx * m_per_px
    fwd = dy * m_per_px
    th = math.radians(heading_deg)
    return (fwd * math.sin(th) + right * math.cos(th),
            fwd * math.cos(th) - right * math.sin(th))


# @part 24 todo 3
def integrate(steps, start=(0.0, 0.0)):
    """Dead reckoning (lesson §6): the track that starts at `start` and adds the steps one after the other.

    Inputs: steps — a list (or array) of n (east_m, north_m) steps; start — (east_m, north_m).
    Returns a float numpy array of shape (n + 1, 2): row 0 is the start, row i the position after i steps.
    Example: integrate([(1.0, 0.0), (0.0, 2.0)], start=(10.0, 10.0)) → array([[10., 10.], [11., 10.], [11., 12.]])
             integrate([], start=(7.0, 8.0)) → array([[7., 8.]])   (no step: only the start)
    """
    s = np.asarray(steps, dtype=float).reshape(-1, 2)
    out = np.zeros((len(s) + 1, 2))
    out[0] = start
    out[1:] = out[0] + np.cumsum(s, axis=0)
    return out


# @part 24
def keypoint_matches(a, b, method="orb", model=None, n=500, device="cpu"):
    """Keypoints of picture a matched with picture b (mission 21's tools): ORB keypoints, described by ORB's
    256 bits (method "orb") or by YOUR trained PatchNet (method "learned", `model` from learned_desc.load_weights)
    on 48 × 48 patches around them, computed on `device` ("cpu" or "cuda"). A pair is kept when each point is the
    other's nearest descriptor (mutual nearest neighbours).
    Returns (p1, p2): float32 arrays (N, 2) of matched (x, y), p1[i] in a and p2[i] in b; N may be 0.

    Example: keypoint_matches(np.zeros((240, 320)), np.zeros((240, 320))) → two arrays of shape (0, 2)
    """
    # from mission 24 — finished: read it, use it, do not change it
    from navera_lite.features import detect
    ga = np.clip(to_gray32(a), 0, 255).astype(np.uint8)
    gb = np.clip(to_gray32(b), 0, 255).astype(np.uint8)
    pa, da = detect(ga, "orb", n)
    pb, db = detect(gb, "orb", n)
    empty = np.zeros((0, 2), np.float32)
    if da is None or db is None or len(pa) < 2 or len(pb) < 2:
        return empty, empty
    if method == "orb":
        pairs = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db)
        i = np.array([m.queryIdx for m in pairs], int)
        j = np.array([m.trainIdx for m in pairs], int)
    elif method == "learned":
        if model is None:
            raise ValueError("method 'learned' needs model= (learned_desc.load_weights('my_desc.pt'))")
        from navera_lite.learned_desc import describe

        def cut(g, pts):
            return np.stack([cv2.getRectSubPix(g, (48, 48), (float(x), float(y))) for x, y in pts])
        fa, fb = describe(model, cut(ga, pa), device), describe(model, cut(gb, pb), device)
        d = ((fa[:, None, :] - fb[None, :, :]) ** 2).sum(axis=2)
        j = d.argmin(axis=1)
        i = np.arange(len(pa))
        mutual = d.argmin(axis=0)[j] == i
        i, j = i[mutual], j[mutual]
    else:
        raise ValueError(f"method must be 'orb' or 'learned', got {method!r}")
    if len(i) == 0:
        return empty, empty
    return pa[i].astype(np.float32), pb[j].astype(np.float32)


# @part 24 todo 4
def median_shift(p1, p2, tol_px=1.0):
    """The shift of a picture from matched keypoints (lesson §4): each match (p1[i] → p2[i]) votes for one shift;
    a wrong match votes for nonsense. Returns (dx, dy, n_agree): the median of the votes in x and in y, and how many
    votes lie within tol_px of that (dx, dy) (distance in pixels, ≤). With no match at all: (None, None, 0).

    Inputs: p1, p2 — arrays (N, 2) of (x, y) pixels.
    Example: median_shift([(0, 0), (10, 10), (50, 5)], [(3, 1), (13, 11), (0, 0)]) → (3.0, 1.0, 2)
             (two matches agree on 3 px right, 1 px down; the third is wrong)
    """
    p1 = np.asarray(p1, dtype=float).reshape(-1, 2)
    p2 = np.asarray(p2, dtype=float).reshape(-1, 2)
    if len(p1) == 0:
        return None, None, 0
    d = p2 - p1
    dx, dy = float(np.median(d[:, 0])), float(np.median(d[:, 1]))
    n = int((np.hypot(d[:, 0] - dx, d[:, 1] - dy) <= tol_px).sum())
    return dx, dy, n


# ====================================================================== drift and fixes (session 2)

# @part 24 todo 5
def drift_sigma(n, sigma_step_m, bias_m):
    """The expected size (RMS, metres, in ONE axis) of the dead-reckoning error after n steps, when every step's
    error is the same bias bias_m plus an independent random part of standard deviation sigma_step_m (lesson §7).

    Works on a number n or on a numpy array of n's (one result per n). Returns a float or an array.
    Example: drift_sigma(25, 1.0, 0.0) → 5.0     drift_sigma(25, 0.0, 0.2) → 5.0     drift_sigma(0, 1.0, 0.2) → 0.0
             drift_sigma(25, 1.0, 0.2) → 7.0710…   (not 5 + 5: the two parts are independent)
    """
    n = np.asarray(n, dtype=float)
    out = np.sqrt(n * n * bias_m * bias_m + n * sigma_step_m * sigma_step_m)
    return float(out) if out.ndim == 0 else out


# @part 24 todo 7
def blend(x1, v1, x2, v2):
    """Inverse-variance blend of two independent estimates of the same quantity (lesson §8): x1 with variance v1,
    x2 with variance v2 (variances, σ², not σ). Returns (x, v): the blend and its variance.
    Works on numbers, and element by element on numpy arrays (east and north at once).
    Example: blend(10.0, 9.0, 16.0, 3.0) → (14.5, 2.25)
    """
    x1, v1, x2, v2 = (np.asarray(t, dtype=float) for t in (x1, v1, x2, v2))
    x = (x1 * v2 + x2 * v1) / (v1 + v2)
    v = v1 * v2 / (v1 + v2)
    if x.ndim == 0:
        return float(x), float(v)
    return x, v


# @part 24 todo 8
def vo_gate(v_vo, v_ref, sigma_mps, k=3.0):
    """Accept an odometry velocity only if it agrees with a reference velocity (lesson §9): True when the distance
    between the two velocity vectors (east, north, m/s) is at most k · sigma_mps, else False.

    Example: vo_gate((20.0, 0.0), (19.0, 1.0), 1.0) → True      vo_gate((0.0, 0.0), (20.0, 0.0), 2.0) → False
             vo_gate((20.0, 0.0), (-20.0, 0.0), 2.0) → False   (the same speed, the opposite way)
    """
    return bool(math.hypot(v_vo[0] - v_ref[0], v_vo[1] - v_ref[1]) <= k * sigma_mps)
