"""run_timing.py — runs YOUR functions of navera_lite/timing.py on the lab's data, and draws them.

    python3 run_timing.py test            check each function on its docstring example (and a few traps)
    python3 run_timing.py bench           NAVERA's real Insta360 frames: two halves, JPEG size, decode time  (Step 1)
    python3 run_timing.py stats           60 s of grab times: rate, jitter, drops, a stall          (Step 2, TODO 1)
    python3 run_timing.py flashes         the screen-flash bench: one delay per flash               (Step 3, TODO 2)
    python3 run_timing.py budget          what a time error costs on the ground                     (Step 5, TODO 3)
    python3 run_timing.py turn            the plane's turn: which attitude belongs to each frame?   (Steps 7–8)
    python3 run_timing.py turn --latency 0.0     the same with another delay setting (seconds)
    python3 run_timing.py scan            which delay setting makes the frames agree with the truth (Step 9)
    python3 run_timing.py straighten      one frame of the turn straightened with two attitudes     (Step 7)

Data: /data/academy/20-live-camera/. Settings: camera.yaml (the delay setting latency_s, the refusal rules).
Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import bisect
import csv
import math
import os
import statistics
import sys
import time

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

tm = rk.load_student("navera_lite.timing")
DATA = os.environ.get("LAB20_DATA", "/data/academy/20-live-camera")
OUT = "out"
SCREEN_S = 0.020          # the bench screen's own delay, measured with a photodiode (lab Step 4)
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if "not supported between instances of 'NoneType'" in s:
        return (" — a value is None: an attitude_at() call returned None (no IMU sample near that time) "
                "and the code compares or uses it without testing `is None` first")
    if "ambiguous" in s and "truth value" in s:
        return " — `if q:` on a numpy array is ambiguous: write `if q is None:`"
    if "list index out of range" in s or "index out of bounds" in s:
        return (" — an index past the end of a list: with bisect, i can be 0 (before the first sample) or len(…) "
                "(after the last): handle both ends before reading [i] or [i - 1]")
    if "division by zero" in s or "divide by zero" in s:
        return " — a division by zero: two samples with the same time? or a median of 0?"
    return _kit_hint(e)


rk._hint = _hint


def _need_data(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: the lab's data is not mounted here (run this in the lab's terminal).")
    return path


def read_csv(name):
    with open(_need_data(name), newline="") as f:
        return list(csv.DictReader(f))


def settings():
    try:
        return tm.load_camera_settings("camera.yaml")
    except ValueError as e:
        sys.exit(f"camera.yaml: {e}")


def close(got, want, tol):
    try:
        return abs(float(got) - want) <= tol
    except (TypeError, ValueError):
        return False


def show(v):
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k!r}: {show(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)) and not hasattr(v, "shape"):
        return "[" + ", ".join(show(x) for x in v) + "]"
    if v is None:
        return "None"
    if isinstance(v, (bool, int, str)):
        return repr(v)
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return repr(v)
    if a.ndim == 0:
        return f"{float(a):.6g}"
    return np.array2string(a, precision=5, suppress_small=True, separator=", ")


# ============================================================================ test
QZ20 = (0.0, 0.0, 0.173648, 0.984808)          # yaw +20°
I = (0.0, 0.0, 0.0, 1.0)


def _check_stats(got):
    """Compare frame_stats([0, .1, .2, .4, .5]) with the docstring; name the symptom of a wrong key."""
    if not isinstance(got, dict):
        return f"frame_stats() must return a dict, got {type(got).__name__}"
    want = {"n": 5, "fps": 8.0, "median_ms": 100.0, "jitter_ms": 43.30127, "max_gap_ms": 200.0, "dropped": 1}
    missing = [k for k in want if k not in got]
    if missing:
        return f"frame_stats() has no key {missing[0]!r} (the keys: {', '.join(want)})"
    extra = [k for k in got if k not in want]
    if extra:
        return f"frame_stats() has an extra key {extra[0]!r}: exactly the six keys of the docstring"
    if close(got["fps"], 10.0, 1e-6):
        return "fps = 10.0 instead of 8.0: 5 frames have only 4 intervals — lab Step 2, hint 2"
    if close(got["median_ms"], 0.1, 1e-6) or close(got["max_gap_ms"], 0.2, 1e-6):
        return "median_ms / max_gap_ms in seconds: the dict wants milliseconds (× 1000)"
    if close(got["jitter_ms"], 50.0, 1e-3):
        return "jitter_ms = 50.0 instead of 43.3: that is ddof = 1 (pandas' default); numpy's default is ddof = 0 — 🧰 box of Step 2"
    if got["dropped"] == 2:
        return "dropped = 2 instead of 1: an interval of 2 periods holds ONE missing frame — round(d / median) − 1"
    for k, w in want.items():
        if not close(got[k], w, 1e-3):
            return f"{k} = {show(got[k])}, the docstring says {w:g}"
    if isinstance(got["n"], bool) or not isinstance(got["n"], (int, np.integer)) or \
            isinstance(got["dropped"], bool) or not isinstance(got["dropped"], (int, np.integer)):
        return "n and dropped must be whole numbers (int): int(…) or round(…)"
    return None


def test():
    done, total = 0, 0

    def report(k, ok, label, note=None):
        nonlocal done, total
        total += 1
        if ok:
            done += 1
            print(f"✔ TODO {k}  {label}")
        else:
            print(f"✘ TODO {k}  {label}" + (f"\n          {note}" if note else ""))

    # TODO 1
    got, err = rk.call(tm, "frame_stats", [0.0, 0.1, 0.2, 0.4, 0.5])
    note = err or _check_stats(got)
    report(1, note is None, "frame_stats([0, 0.1, 0.2, 0.4, 0.5])" + ("" if note else f" = {show(got)}"), note)
    f = getattr(tm, "frame_stats", None)
    if f is not None and not rk.is_stub(f):
        try:
            f([3.0])
            report(1, False, "frame_stats([3.0]) must raise ValueError (one stamp: no interval)",
                   "it returned without an error — add a test before you compute anything")
        except ValueError:
            report(1, True, "frame_stats([3.0]) raises ValueError")
        except Exception as e:
            report(1, False, f"frame_stats([3.0]) must raise ValueError, not {type(e).__name__}: {e}")
    # TODO 2
    cases = [(([1.0], [0.9, 1.05, 1.1, 1.2], [30, 40, 200, 210]), [0.1], "the docstring example",
              "[0.05]? the frame at 1.05 is not above the midpoint (30 + 210) / 2 = 120 — lab Step 3, hint 2"),
             (([1.0], [0.9, 1.05, 1.1, 1.2], [30, 31, 33, 32]), [None], "a flash the camera did not see",
              "a rise of 3 is not a flash (min_rise = 20): None — lab Step 3, hint 3"),
             (([1.0], [0.9, 1.05, 1.1, 1.2], [30, 120, 200, 210]), [0.1], "a frame EXACTLY at the midpoint",
              "brightness 120 is the midpoint (30 + 210) / 2, not brighter than it: use >, not >= — lab Step 3, hint 2"),
             (([1.0, 2.0], [0.9, 1.12, 1.3, 1.9, 2.15, 2.3], [30, 200, 205, 32, 120, 210]), [0.12, 0.3],
              "two flashes, the second frame half lit", "the half-lit frame (120 < (32 + 210) / 2) is not "
              "the first one above the midpoint — lab Step 3, hint 2")]
    for args, want, label, hint in cases:
        got, err = rk.call(tm, "delay_from_flashes", *args)
        ok = (err is None and isinstance(got, (list, tuple)) and len(got) == len(want) and
              all((w is None and g is None) or (w is not None and g is not None and close(g, w, 1e-9))
                  for g, w in zip(got, want)))
        report(2, ok, f"delay_from_flashes: {label}" + ("" if err else f" → {show(got)}"), None if ok else (err or hint))
    # TODO 3
    got, err = rk.call(tm, "time_error_m", 100.0, 20.0, 0.1)
    note = err
    if not err:
        if close(got, 218.50, 0.1):
            note = "218.5: math.tan got DEGREES — math.tan(math.radians(…))"
        elif close(got, 3.4907, 1e-3):
            note = "3.4907 = h × angle: the small-angle formula; the docstring wants the exact tangent"
        elif not close(got, 3.492077, 1e-5):
            note = f"{show(got)} — the docstring says about 3.492 (rate × dt is the angle, in degrees)"
    report(3, note is None, "time_error_m(100, 20, 0.1)" + ("" if err else f" = {show(got)}"), note)
    # TODO 4
    T2, Q2 = [0.0, 0.2], [I, QZ20]
    cases4 = [((0.05, T2, Q2), [0, 0, 0.0436194, 0.9990482], "between two samples (the docstring example)",
               "yaw 15° instead of 5° ([0, 0, 0.1305, 0.9914])? the fraction is upside down — lab Step 6, hint 3"),
              ((0.2, T2, Q2), list(QZ20), "exactly on the last sample", "on a sample: that sample"),
              ((0.30, T2, Q2), list(QZ20), "0.1 s after the last sample (within max_gap_s)",
               "after the last sample: hold the last one, never extrapolate — lab Step 6, hint 4"),
              ((-0.15, T2, Q2), list(I), "0.15 s before the first sample", "before the first: the first sample"),
              ((0.45, T2, Q2), None, "0.25 s after the last sample (beyond max_gap_s)",
               "no sample within 0.2 s: None — lab Step 6, hint 5"),
              ((0.5, [0.0, 1.0], [I, QZ20]), None, "in the middle of a 1 s hole", "the nearest sample is 0.5 s "
               "away: None — lab Step 6, hint 5"),
              ((0.15, [0.0, 0.3], [I, QZ20]), [0, 0, 0.0871557, 0.9961947], "in the middle of a 0.3 s hole",
               "the nearest sample is 0.15 s away (≤ 0.2): interpolate"),
              ((1.0, [], []), None, "an empty history", "no sample at all: None")]
    for args, want, label, hint in cases4:
        got, err = rk.call(tm, "attitude_at", *args)
        if want is None:
            ok = err is not None and "returned None" in err
            report(4, ok, f"attitude_at: {label} → None" if ok else f"attitude_at: {label}",
                   None if ok else (err or f"it returned {show(got)} — {hint}"))
            continue
        ok = False
        if not err:
            try:
                a = np.asarray(got, dtype=float)
                ok = a.shape == (4,) and (np.allclose(a, want, atol=1e-5) or np.allclose(-a, want, atol=1e-5))
            except (TypeError, ValueError):
                pass
        if not ok and not err:
            a = np.asarray(got, dtype=float) if got is not None else None
            if a is not None and a.shape == (4,) and abs(a[0]) > 0.9:
                hint = "the scalar part came FIRST: quaternions here are (x, y, z, w), w last — lab Step 6, hint 6"
            elif "docstring" in label and not (a is not None and a.shape == (4,) and
                                                np.allclose(np.abs(a), [0, 0, 0.1305262, 0.9914449], atol=1e-4)):
                hint = ("close, but not the slerp result: call rotations.slerp(q0, q1, f) — a formula of your own "
                        "(averaging the four numbers) is not exact")
        if err and "returned None" in err:
            err = f"it returned None, but a sample is within max_gap_s — {hint}"
        report(4, ok, f"attitude_at: {label}" + ("" if err else f" → {show(got)}"), None if ok else (err or hint))
    # TODO 5
    got, err = rk.call(tm, "rotation_rate_dps", 0.2, T2, Q2)
    note = err or (None if close(got, 100.0, 1e-3) else f"{show(got)} — 20° in 0.2 s is 100 °/s. "
                   "20.0? divide the angle by window_s — lab Step 8, hint 1")
    report(5, note is None, "rotation_rate_dps(0.2, …) (20° in 0.2 s)" + ("" if err else f" = {show(got)}"), note)
    got, err = rk.call(tm, "rotation_rate_dps", 0.9, [0.0, 1.0], [I, QZ20])
    ok = err is not None and "returned None" in err
    report(5, ok, "rotation_rate_dps(0.9, …) in a 1 s hole: no attitude at 0.7 s → None" if ok else
           "rotation_rate_dps(0.9, …) in a 1 s hole: no attitude at 0.7 s",
           None if ok else (err or f"it returned {show(got)}: the attitude at 0.7 s is None (no sample within 0.2 s), so the rate is None"))
    # TODO 6
    D = dict(tm.DEFAULTS)
    roll50 = (0.4226183, 0.0, 0.0, 0.9063078)
    cases6 = [(((0.0, 0.0, 0.0, 1.0), 12.0, D), (True, "ok"), "level, 12 °/s"),
              ((None, 12.0, D), (False, "no attitude at the exposure"), "no attitude"),
              (((0.0, 0.0, 0.0, 1.0), None, D), (False, "rotation rate unknown"), "rate unknown"),
              (((0.0, 0.0, 0.0, 1.0), 41.23, D), (False, "turning 41.2 °/s > 30.0 °/s"), "41.23 °/s"),
              ((roll50, 10.0, D), (False, "tilted 50.0° > 45.0°"), "rolled 50°"),
              ((roll50, 41.23, D), (False, "turning 41.2 °/s > 30.0 °/s"), "rolled 50° AND 41.23 °/s (the order)"),
              ((roll50, 41.23, dict(D, gimbal=True)), (True, "ok"), "the same with a gimbal")]
    for args, want, label in cases6:
        got, err = rk.call(tm, "usable", *args)
        ok = (not err and isinstance(got, (tuple, list)) and len(got) == 2 and got[0] is want[0]
              and str(got[1]) == want[1])
        hint = None
        if not ok and not err:
            if isinstance(got, (tuple, list)) and len(got) == 2 and got[0] == want[0] and got[0] is not want[0]:
                hint = "the first value must be True or False (a bool), not a number"
            elif "order" in label and isinstance(got, (tuple, list)) and len(got) == 2 and \
                    str(got[1]).startswith("tilted"):
                hint = "the rate rule comes BEFORE the tilt rule — lab Step 8, hint 4"
            elif isinstance(got, (tuple, list)) and len(got) == 2 and got[0] == want[0]:
                hint = f"the reason must be exactly {want[1]!r} (the docstring's words, one decimal)"
            else:
                hint = f"the docstring's rules give {want!r} — lab Step 8, hint {4 if 'order' in label else 3}"
        report(6, ok, f"usable: {label}" + ("" if err else f" → {show(got)}"), None if ok else (err or hint))
    print(f"\n{done} of {total} lines ✔.", "Every TODO works on its examples: now run the lab's step."
          if done == total else "Fix the first ✘ line first: the next ones often depend on it.")


# ============================================================================ bench (Step 1)
def bench():
    import cv2
    path = _need_data("bench/frame_000.jpg")
    raw = open(path, "rb").read()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    times = []
    for _ in range(25):
        t = time.perf_counter()
        cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        times.append(time.perf_counter() - t)
    decode_ms = 1000.0 * statistics.median(times[5:])
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "bench_top.jpg"), img[: h // 2])
    cv2.imwrite(os.path.join(OUT, "bench_bottom.jpg"), img[h // 2:])
    lat = None
    for line in open(_need_data("bench/insta360_top.yaml")):
        if line.startswith("latency_s:"):
            lat = float(line.split(":")[1])
    print("NAVERA's camera on the bench (Insta360 ONE R, USB webcam mode, MJPG) — a real recorded frame:")
    print(f"  picture        {w} × {h} pixels, two halves of {w} × {h // 2} (top lens, bottom lens)")
    print(f"  as a JPEG      {len(raw) / 1000:.0f} kB          decoded (3 bytes per pixel): {w * h * 3 / 1e6:.1f} MB")
    print(f"  decode time    {decode_ms:.1f} ms per frame on THIS computer (median of 20 decodes, cv2.imdecode)")
    print(f"  latency_s      {lat} s in NAVERA's calibration file of the top lens (insta360_top.yaml)")
    print("  the two halves: out/bench_top.jpg (the lens NAVERA uses) and out/bench_bottom.jpg (pixelated: people)")


# ============================================================================ stats (Step 2)
def grab_log():
    return [float(r["grab_s"]) for r in read_csv("grab_log.csv")]


def stats():
    t = grab_log()
    whole = rk.need_ok(tm, "frame_stats", t)
    first = rk.need_ok(tm, "frame_stats", [x for x in t if x < t[0] + 40.0])
    note = _check_stats(rk.need_ok(tm, "frame_stats", [0.0, 0.1, 0.2, 0.4, 0.5]))
    if note:
        print(f"⚠ your frame_stats() fails its own example ({note}): the numbers below are wrong\n")
    print(f"{'':22s}{'n':>6s}{'fps':>9s}{'median_ms':>11s}{'jitter_ms':>11s}{'max_gap_ms':>12s}{'dropped':>9s}")
    for label, s in (("the first 40 s", first), ("the whole 60 s", whole)):
        try:
            print(f"{label:22s}{s['n']:6d}{s['fps']:9.2f}{s['median_ms']:11.2f}{s['jitter_ms']:11.2f}"
                  f"{s['max_gap_ms']:12.1f}{s['dropped']:9d}")
        except (KeyError, TypeError, ValueError) as e:
            sys.exit(f"frame_stats() returned {show(s)} — it needs the six keys of its docstring ({e})")
    plt = rk.plt_or_none()
    if plt:
        d = np.diff(t) * 1000.0
        fig, ax = plt.subplots(figsize=(9, 3.6))
        ax.plot(np.array(t[1:]) - t[0], d, ".", ms=3)
        ax.set_yscale("log")
        ax.set_xlabel("time since the first frame (s)")
        ax.set_ylabel("interval to the previous frame (ms, log scale)")
        ax.set_title("60 s of grab times: each dot is one interval")
        ax.grid(alpha=0.3, which="both")
        os.makedirs(OUT, exist_ok=True)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "intervals.png"), dpi=110)
        rk.saved(os.path.join(OUT, "intervals.png"))


# ============================================================================ flashes (Step 3)
def flash_delays():
    flashes = [float(r["t_white_s"]) for r in read_csv("flashes.csv")]
    rows = read_csv("bench_frames.csv")
    ft = [float(r["grab_s"]) for r in rows]
    fb = [float(r["brightness"]) for r in rows]
    d = rk.need_ok(tm, "delay_from_flashes", flashes, ft, fb)
    if not isinstance(d, (list, tuple)) or len(d) != len(flashes):
        sys.exit(f"delay_from_flashes() must return a list with one entry per flash ({len(flashes)}), got {show(d)}")
    return flashes, ft, fb, list(d)


def flashes_mode():
    flashes, ft, fb, d = flash_delays()
    print("flash   delay (ms)")
    for k, x in enumerate(d):
        print(f"{k:5d}   " + ("not seen" if x is None else f"{1000 * x:7.1f}"))
    v = np.array([x for x in d if x is not None], dtype=float)
    if v.size == 0:
        sys.exit("no flash was seen: is delay_from_flashes() right? (python3 run_timing.py test)")
    T = 1000.0 / 28.8
    print(f"\n{v.size} flashes seen of {len(d)}.  median {1000 * np.median(v):.1f} ms   min {1000 * v.min():.1f} ms   "
          f"max {1000 * v.max():.1f} ms   mean {1000 * v.mean():.1f} ms   std {1000 * v.std():.1f} ms")
    print(f"one frame period at 28.8 fps: T = {T:.1f} ms")
    plt = rk.plt_or_none()
    if plt:
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.8))
        ft_a, fb_a = np.array(ft), np.array(fb)
        for k, t0 in enumerate(flashes):
            m = (ft_a > t0 - 0.15) & (ft_a < t0 + 0.45)
            a1.plot(1000 * (ft_a[m] - t0), fb_a[m], "-", lw=0.8, alpha=0.6)
        a1.axvline(0, color="k", lw=1)
        a1.set_xlabel("grab time − flash time (ms)")
        a1.set_ylabel("brightness of the frame centre")
        a1.set_title("every flash, aligned on the instant it was asked")
        a2.plot([k for k, x in enumerate(d) if x is not None], 1000 * v, "o")
        a2.axhline(1000 * np.median(v), color="C1", label="median")
        a2.axhline(1000 * v.min(), color="C2", ls="--", label="minimum")
        a2.set_xlabel("flash number")
        a2.set_xticks(range(0, len(d), 2))
        a2.set_ylabel("delay (ms)")
        a2.set_title("one delay per flash seen")
        a2.legend()
        for a in (a1, a2):
            a.grid(alpha=0.3)
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "flashes.png"), dpi=110)
        rk.saved(os.path.join(OUT, "flashes.png"))


# ============================================================================ budget (Step 5)
def budget():
    rk.need_ok(tm, "time_error_m", 100.0, 20.0, 0.1, kind=float)
    for h in (150.0, 300.0):
        print(f"\nground error (m) at {h:.0f} m above flat ground, by rotation rate and time error:")
        dts = (0.010, 1 / 28.8, 0.138, 0.5)
        print(f"{'rate':>10s}" + "".join(f"{f'δt {1000 * x:.0f} ms':>14s}" for x in dts))
        for rate in (5.0, 13.0, 25.0, 30.0, 60.0):
            print(f"{rate:6.0f} °/s" + "".join(f"{rk.need_ok(tm, 'time_error_m', h, rate, x):14.2f}" for x in dts))


# ============================================================================ the flight (Steps 7–9)
def flight():
    imu = read_csv("flight/imu.csv")
    it = [float(r["t_s"]) for r in imu]
    iq = [tuple(float(r[k]) for k in ("qx", "qy", "qz", "qw")) for r in imu]
    fr = read_csv("flight/frames.csv")
    for r in fr:
        r["grab_s"] = float(r["grab_s"])
        r["height_m"] = float(r["height_m"])
        r["q_true"] = tuple(float(r[k]) for k in ("true_qx", "true_qy", "true_qz", "true_qw"))
    return it, iq, fr


def angle_deg(q0, q1):
    a, b = np.asarray(q0, float), np.asarray(q1, float)
    return math.degrees(2 * math.acos(min(1.0, abs(float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))))))


def methods(it, iq, fr, latency):
    """Per frame: the attitude a naive program holds at the grab, the nearest sample to the exposure, yours."""
    att = getattr(tm, "attitude_at")
    rows = []
    for r in fr:
        g = r["grab_s"]
        e = g - latency
        i = bisect.bisect_right(it, g) - 1
        q_grab = iq[i] if i >= 0 else None
        j = bisect.bisect_left(it, e)
        cand = [k for k in (j - 1, j) if 0 <= k < len(it)]
        k = min(cand, key=lambda k: abs(it[k] - e))
        q_near = iq[k] if abs(it[k] - e) <= 0.2 else None
        q_mine = att(e, it, iq)
        rows.append((r, q_grab, q_near, q_mine))
    return rows


def metres(r, q):
    return None if q is None else r["height_m"] * math.tan(math.radians(angle_deg(q, r["q_true"])))


def turn(latency=None):
    cfg = settings()
    lat = cfg["latency_s"] if latency is None else latency
    it, iq, fr = flight()
    rk.need_ok(tm, "attitude_at", 0.05, [0.0, 0.2], [I, QZ20])
    try:
        rows = methods(it, iq, fr, lat)
    except Exception as e:
        sys.exit(f"attitude_at() stopped on the flight's data with {type(e).__name__}: {e}{_hint(e)}")
    names = ("the IMU sample held at the grab", "the nearest sample to the exposure", "YOUR attitude_at(exposure)")
    print(f"{len(fr)} frames of the plane's flight, delay setting latency_s = {lat:.3f} s "
          f"({'camera.yaml' if latency is None else '--latency'}): exposure = grab − {lat:.3f} s")
    print(f"\nground error of the image centre, from the attitude error at {fr[0]['height_m']:.0f} m (metres):")
    print(f"{'attitude used':40s}{'median':>8s}{'p95':>8s}{'max':>8s}{'no attitude':>13s}")
    errs = []
    for m, name in enumerate(names):
        e = [metres(row[0], row[1 + m]) for row in rows]
        v = np.array([x for x in e if x is not None])
        errs.append(e)
        print(f"{name:40s}{np.median(v):8.2f}{np.percentile(v, 95):8.2f}{v.max():8.2f}{len(e) - v.size:13d}")
    print("(the first line does not use latency_s at all: it is the same for every setting)")
    # the decisions
    have = [hasattr(tm, n) and not rk.is_stub(getattr(tm, n)) for n in ("rotation_rate_dps", "usable")]
    counts, decisions = {}, []
    if all(have):
        for row in rows:
            r = row[0]
            e = r["grab_s"] - lat
            rate, err = rk.call(tm, "rotation_rate_dps", e, it, iq, cfg["rate_window_s"], cfg["max_gap_s"])
            if err and "returned None" not in err:
                sys.exit(err)
            v, err = rk.call(tm, "usable", row[3], rate, cfg)
            if err:
                sys.exit(err)
            ok, why = v
            key = "ok" if ok else str(why).split(" ")[0]
            key = {"no": "no attitude", "rotation": "rate unknown"}.get(key, key)
            counts[key] = counts.get(key, 0) + 1
            decisions.append((r["grab_s"], ok, rate))
        print("\nYOUR usable() on every frame (settings of camera.yaml):")
        for key in ("ok", "no attitude", "rate unknown", "turning", "tilted"):
            print(f"  {key:14s}{counts.get(key, 0):5d}")
        other = {k: v for k, v in counts.items() if k not in ("ok", "no attitude", "rate unknown", "turning", "tilted")}
        if other:
            print(f"  other reasons: {other} — use the docstring's words")
    else:
        print("\n(rotation_rate_dps and usable are not written yet: Step 8 adds the decisions here)")
    plt = rk.plt_or_none()
    if plt:
        t0 = fr[0]["grab_s"]
        tt = np.array([r["grab_s"] - t0 for r in fr])
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        for e, name, st in zip(errs, names, ("C3.", "C1.", "C0.")):
            ok = [i for i, x in enumerate(e) if x is not None]
            a2.plot(tt[ok], np.maximum(0.01, [e[i] for i in ok]), st, ms=3, label=name)
        a2.set_yscale("log")
        a2.set_ylabel("ground error (m, log scale)")
        a2.set_xlabel("time of the grab (s since the first frame)")
        a2.legend(fontsize=8, loc="upper right")
        roll = []
        for r in fr:
            R = _matrix(r["q_true"])
            roll.append(math.degrees(math.atan2(R[2, 1], R[2, 2])))
        a1.plot(tt, roll, "k-", lw=1, label="true roll (°)")
        if decisions:
            rate = np.array([np.nan if d[2] is None else d[2] for d in decisions])
            a1.plot(tt, rate, "C0-", lw=1, label="your rotation rate (°/s)")
            bad = [i for i, d in enumerate(decisions) if not d[1]]
            a1.plot(tt[bad], np.zeros(len(bad)), "rx", ms=4, label="refused by your usable()")
        a1.axhline(30, color="C0", ls=":", lw=1)
        a1.axhline(-45, color="k", ls=":", lw=1)
        a1.set_ylabel("degrees, °/s")
        a1.legend(fontsize=8, loc="lower left")
        for a in (a1, a2):
            a.grid(alpha=0.3, which="both")
        fig.suptitle(f"the plane's turn: which attitude belongs to each frame? (latency_s = {lat:.3f} s)")
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "turn.png"), dpi=110)
        rk.saved(os.path.join(OUT, "turn.png"))


def _matrix(q):
    x, y, z, w = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def scan():
    it, iq, fr = flight()
    rk.need_ok(tm, "attitude_at", 0.05, [0.0, 0.2], [I, QZ20])
    lats = np.round(np.arange(0.060, 0.2001, 0.002), 3)
    med = []
    for lat in lats:
        e = [metres(r, tm.attitude_at(r["grab_s"] - lat, it, iq)) for r in fr]
        med.append(float(np.median([x for x in e if x is not None])))
    best = int(np.argmin(med))
    print("delay setting (s)   median ground error with YOUR attitude_at (m)")
    for lat, m in zip(lats, med):
        if abs(round(lat * 100) - lat * 100) < 1e-6 or lat == lats[best]:
            print(f"   {lat:.3f}            {m:6.2f}" + ("   ← the smallest" if lat == lats[best] else ""))
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(8, 3.6))
        ax.plot(lats, med, "o-", ms=3)
        ax.set_xlabel("delay setting latency_s (s)")
        ax.set_ylabel("median ground error (m)")
        ax.set_title("which delay makes the IMU agree with the frames' true attitude?")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "scan.png"), dpi=110)
        rk.saved(os.path.join(OUT, "scan.png"))


def straighten():
    import cv2
    try:
        from navera_lite.ros.camera_node import GroundPainter
    except ImportError as e:
        sys.exit(f"this step needs ROS's Python packages ({e}): open a new terminal (it sources ROS) and try again")
    from navera_lite.camera import backproject_ground, camera_rotation, camera_rotation_hpr, nadir_homography
    from navera_lite.rotations import heading_deg_from_q
    cfg = settings()
    it, iq, fr = flight()
    rk.need_ok(tm, "attitude_at", 0.05, [0.0, 0.2], [I, QZ20])
    try:
        rows = methods(it, iq, fr, cfg["latency_s"])
    except Exception as e:
        sys.exit(f"attitude_at() stopped on the flight's data with {type(e).__name__}: {e}{_hint(e)}")
    # the frame of the first roll-in (3 s to 6 s) where the attitude held at the grab is the most wrong
    t0 = fr[0]["grab_s"]
    best = max((row for row in rows if row[3] is not None and 3.0 <= row[0]["grab_s"] - t0 <= 6.0),
               key=lambda row: metres(row[0], row[1]))
    r, q_grab, _, q_mine = best
    p = GroundPainter(os.path.join(DATA, "flight"))
    img = p.draw(float(r["east_m"]), float(r["north_m"]), r["height_m"], r["q_true"])
    C = [float(r["east_m"]), float(r["north_m"]), r["height_m"]]
    centre = (p.size[0] / 2.0, p.size[1] / 2.0)
    true_g = backproject_ground(p.K, camera_rotation(r["q_true"]), C, *centre)
    panels, lines = [], []
    level = camera_rotation_hpr(heading_deg_from_q(r["q_true"]))
    truth = p.draw(C[0], C[1], C[2], _level_q(heading_deg_from_q(r["q_true"])))
    for name, q in (("held at the grab", q_grab), ("YOUR attitude_at(exposure)", q_mine)):
        H = nadir_homography(p.K, camera_rotation(q), level)
        st = cv2.warpPerspective(img, H, p.size, borderMode=cv2.BORDER_CONSTANT)
        g = backproject_ground(p.K, camera_rotation(q), C, *centre)
        err = float(np.hypot(*(np.asarray(g) - np.asarray(true_g))))
        mix = cv2.addWeighted(st, 0.5, truth, 0.5, 0)
        cv2.putText(mix, f"{name}: {err:.1f} m", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        panels.append(mix)
        lines.append(f"  attitude {name:28s} → the image centre lands {err:5.1f} m from the truth")
    print(f"frame {r['frame']} (grab at {r['grab_s'] - fr[0]['grab_s']:.2f} s, latency_s {cfg['latency_s']:.3f} s), "
          f"straightened to a level view and laid over the true level view (50 % each):")
    print("\n".join(lines))
    out = np.vstack([img, panels[0], panels[1]])
    text = "(c) OpenStreetMap contributors"                  # map data: every picture of the map carries it
    cv2.rectangle(out, (out.shape[1] - 232, out.shape[0] - 18), (out.shape[1] - 1, out.shape[0] - 1), (255, 255, 255), -1)
    cv2.putText(out, text, (out.shape[1] - 228, out.shape[0] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1,
                cv2.LINE_AA)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "straighten.png"), out)
    rk.saved(os.path.join(OUT, "straighten.png") + " — top: the raw frame; middle: held at the grab; bottom: yours")


def _level_q(heading_deg):
    a = math.radians(90.0 - heading_deg) / 2.0
    return (0.0, 0.0, math.sin(a), math.cos(a))


MODES = {"test": test, "bench": bench, "stats": stats, "flashes": flashes_mode, "budget": budget, "turn": turn,
         "scan": scan, "straighten": straighten}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in MODES:
        sys.exit(__doc__)
    if args[0] == "turn" and len(args) == 3 and args[1] == "--latency":
        try:
            turn(float(args[2]))
        except ValueError:
            sys.exit("--latency wants a number of seconds, e.g. --latency 0.0")
    else:
        MODES[args[0]]()
