import csv
import json
import math
import os
import re
import sys

import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/20-live-camera"

# expected values computed once from the lesson's (seeded) dataset
GRAB = {"n": 1713, "fps": 28.5497, "median_ms": 34.732, "jitter_ms": 8.2284, "max_gap_ms": 347.34, "dropped": 15}
LAT = {"n": 20, "median_s": 0.1408, "min_s": 0.1249}
ATT_UNUSABLE = 12
ATT = {"latest_at_grab": (2.142, 5.61), "nearest_at_exposure": (0.052, 0.14), "slerp_at_exposure": (0.012, 0.03)}


def tools():
    return load_student("camera_tools.py")


def rows(name):
    with open(os.path.join(DATA, name)) as f:
        return list(csv.DictReader(f))


def qyaw(deg):
    a = math.radians(deg) / 2
    return np.array([math.cos(a), 0.0, 0.0, math.sin(a)])


def yaw_of(q):
    w, x, y, z = q
    return math.degrees(2 * math.atan2(z, w))


def load_json(path, run):
    c.file_exists(path)
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError:
        c.ok(False, f"{path} is not valid JSON — run `{run}` again")


@c.test("split_halves() cuts the frame in two halves, for any height",
        hint="frame.shape[0] is the height. Slice rows: frame[:h] and frame[h:] with h = half the height.")
def _():
    (split_halves,) = need(tools(), "split_halves")
    f = np.zeros((1080, 1920, 3), np.uint8)
    f[540:] = 200
    r = split_halves(f)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"split_halves() should return (top, bottom), got {r!r:.60}")
    c.eq(tuple(r[0].shape), (540, 1920, 3), "top.shape")
    c.ok(r[0].max() == 0 and r[1].min() == 200, "top and bottom are swapped or mixed: the top lens is rows 0 to 539")
    g = np.arange(40 * 6).reshape(40, 6).astype(np.uint8)
    top, bottom = split_halves(g)
    c.ok(np.array_equal(top, g[:20]) and np.array_equal(bottom, g[20:]), "wrong rows for a 40-row picture (don't write 540)")


@c.test("frame_stats() on a small example: fps, median, jitter, max gap, dropped",
        hint="Work on the intervals np.diff(times). fps = (n-1)/(last-first). jitter = np.std of the intervals "
             "(ddof=0). A gap g > 1.5 x median counts round(g/median) - 1 dropped frames. Return 0 values when n < 2.")
def _():
    (frame_stats,) = need(tools(), "frame_stats")
    s = frame_stats([0.0, 0.1, 0.2, 0.4, 0.5])
    c.ok(isinstance(s, dict), f"frame_stats() should return a dict, got {type(s).__name__}")
    for k in ("n", "fps", "period_ms", "median_ms", "jitter_ms", "max_gap_ms", "dropped"):
        c.ok(k in s, f"the dict has no key '{k}'")
    c.eq(s["n"], 5, "n")
    c.near(s["fps"], 8.0, 1e-6, "fps of [0, .1, .2, .4, .5]")
    c.near(s["period_ms"], 125.0, 1e-6, "period_ms (mean interval)")
    c.near(s["median_ms"], 100.0, 1e-6, "median_ms")
    c.near(s["jitter_ms"], 43.30127, 1e-3, "jitter_ms (np.std of the intervals, in ms)")
    c.near(s["max_gap_ms"], 200.0, 1e-6, "max_gap_ms")
    c.eq(int(s["dropped"]), 1, "dropped")
    s = frame_stats([0.0, 0.1, 0.2, 0.6])
    c.eq(int(s["dropped"]), 3, "dropped for [0, 0.1, 0.2, 0.6] (one 400 ms gap, median 100 ms: round(4) - 1)")
    s1 = frame_stats([3.0])
    c.ok(isinstance(s1, dict) and s1.get("fps") == 0.0 and s1.get("dropped") == 0,
         f"frame_stats([3.0]) should give fps 0.0 and dropped 0, got {s1!r:.80}")


@c.test("frame_stats() of the 60 s grab log (grab_log.csv)",
        hint="The same function on 1713 real-looking grab times: if the small example passes and this fails, "
             "look at the median (np.median) and at how you count the long gaps.")
def _():
    (frame_stats,) = need(tools(), "frame_stats")
    s = frame_stats([float(r["grab_time_s"]) for r in rows("grab_log.csv")])
    c.ok(isinstance(s, dict), f"frame_stats() should return a dict, got {type(s).__name__}")
    c.eq(s.get("n"), GRAB["n"], "n")
    c.near(s["fps"], GRAB["fps"], 0.001, "fps")
    c.near(s["median_ms"], GRAB["median_ms"], 0.01, "median_ms")
    c.near(s["jitter_ms"], GRAB["jitter_ms"], 0.01, "jitter_ms")
    c.near(s["max_gap_ms"], GRAB["max_gap_ms"], 0.05, "max_gap_ms")
    c.eq(int(s["dropped"]), GRAB["dropped"], "dropped")


@c.test("exposure_time() and load_latency()",
        hint="The picture is OLDER than its grab: subtract the delay. load_latency: calib.get(\"latency_s\", 0.0) as a float.")
def _():
    exposure_time, load_latency = need(tools(), "exposure_time", "load_latency")
    c.near(exposure_time(100.0, 0.138), 99.862, 1e-9, "exposure_time(100.0, 0.138)")
    c.near(exposure_time(5.0, 0.0), 5.0, 1e-9, "exposure_time(5.0, 0.0)")
    c.near(load_latency(os.path.join(DATA, "insta360_top.yaml")), 0.138, 1e-9, "load_latency(insta360_top.yaml)")
    os.makedirs("out", exist_ok=True)
    tmp = "out/_check_no_latency.yaml"
    with open(tmp, "w") as f:
        f.write("model: fisheye\nimage_width: 1920\n")
    try:
        v = load_latency(tmp)
        c.ok(isinstance(v, float), f"load_latency() should return a float, got {type(v).__name__}")
        c.near(v, 0.0, 1e-9, "load_latency(a file without latency_s)")
    finally:
        os.remove(tmp)


@c.test("latency_from_flashes(): the screen-flash method",
        hint="For each flash t0: lo = median before [t0-0.3, t0), hi = median after [t0+0.4, t0+0.65]; skip the "
             "flash if a window is empty or hi-lo < 20; delay = first frame time >= t0 whose brightness is ABOVE "
             "(lo+hi)/2, minus t0.")
def _():
    (lff,) = need(tools(), "latency_from_flashes")
    ft = [round(i * 0.05, 3) for i in range(100)]
    br = []
    for t in ft:
        if 1.0 <= t < 1.15:
            b = 30.0
        elif abs(t - 1.15) < 1e-9:
            b = 100.0                                  # half-lit frame: below the midpoint 115
        elif 1.15 < t < 2.5:
            b = 200.0
        else:
            b = 30.0
        br.append(b)
    d = lff([1.0, 3.5], ft, br)                         # the flash at 3.5 s is never seen
    c.ok(isinstance(d, (list, tuple, np.ndarray)), f"latency_from_flashes() should return a list, got {d!r:.60}")
    c.eq(len(d), 1, "number of delays (the second flash is not seen and must be skipped)")
    c.near(d[0], 0.20, 1e-6, "delay of the flash at 1.0 s (the frame at 1.15 s is only half lit)")
    fl = [float(r["t_white_s"]) for r in rows("flashes.csv")]
    fr = rows("flash_frames.csv")
    d = lff(fl, [float(r["grab_time_s"]) for r in fr], [float(r["brightness"]) for r in fr])
    c.eq(len(d), LAT["n"], "number of flashes seen in flash_frames.csv")
    c.near(float(np.median(d)), LAT["median_s"], 0.0005, "median delay of the bench (s)")
    c.near(min(d), LAT["min_s"], 0.0005, "smallest delay of the bench (s)")


@c.test("quat_angle_deg() and slerp() (quaternions w, x, y, z)",
        hint="Angle = 2*acos(min(1, |q0.q1|)) in degrees. slerp: if the dot is negative use -q1; for d > 0.9995 "
             "interpolate linearly; else the sin formula; always return q/|q| as a numpy array.")
def _():
    qa, slerp = need(tools(), "quat_angle_deg", "slerp")
    c.near(qa(qyaw(10), qyaw(40)), 30.0, 1e-6, "quat_angle_deg(yaw 10, yaw 40)")
    c.near(qa(qyaw(25), -qyaw(25)), 0.0, 1e-6, "quat_angle_deg(q, -q) (the same attitude)")
    c.near(qa(qyaw(0), qyaw(0)), 0.0, 1e-6, "quat_angle_deg(q, q)")
    c.near(yaw_of(slerp(qyaw(0), qyaw(90), 0.5)), 45.0, 1e-6, "yaw of slerp(yaw 0, yaw 90, 0.5)")
    c.near(yaw_of(slerp(qyaw(0), qyaw(90), 0.0)), 0.0, 1e-6, "yaw of slerp(..., 0.0)")
    c.near(yaw_of(slerp(qyaw(0), qyaw(90), 1.0)), 90.0, 1e-6, "yaw of slerp(..., 1.0)")
    m = slerp(qyaw(170), qyaw(-170), 0.5)                     # their dot product is negative
    c.near(abs(yaw_of(m)), 180.0, 1e-6, "slerp(yaw 170, yaw -170, 0.5): the SHORT way passes through 180")
    s = slerp(qyaw(10), qyaw(10.001), 0.3)
    c.ok(np.all(np.isfinite(s)), "slerp of two almost equal quaternions gives NaN: use the linear branch for d > 0.9995")
    c.near(float(np.linalg.norm(s)), 1.0, 1e-9, "norm of slerp(...)")
    q = slerp(np.array([0.9, 0.1, 0.3, 0.2]) / np.linalg.norm([0.9, 0.1, 0.3, 0.2]), qyaw(60), 0.25)
    c.near(float(np.linalg.norm(q)), 1.0, 1e-9, "norm of a general slerp")


@c.test("attitude_at(): interpolates, and refuses when there is no sample near t",
        hint="Follow the rules in the docstring (they are NAVERA's History.at): bisect.bisect_left, the two ends, "
             "and the hole test (t1 - t0 > 2*max_gap and both distances > max_gap -> None).")
def _():
    (attitude_at,) = need(tools(), "attitude_at")
    ts = [0.0, 0.2, 1.0, 1.02]
    qs = [qyaw(0), qyaw(20), qyaw(40), qyaw(42)]
    q = attitude_at(0.05, ts, qs)
    c.ok(q is not None, "attitude_at(0.05) gave None between two samples 0.2 s apart")
    c.near(yaw_of(q), 5.0, 1e-6, "yaw at t = 0.05 (between yaw 0 at 0 s and yaw 20 at 0.2 s)")
    c.ok(attitude_at(0.6, ts, qs) is None, "t = 0.6 s is 0.4 s from both samples around it: must be None")
    c.near(yaw_of(attitude_at(0.25, ts, qs)), 21.25, 1e-6, "yaw at t = 0.25 (near the edge of the hole: still interpolated)")
    c.near(yaw_of(attitude_at(-0.1, ts, qs)), 0.0, 1e-6, "yaw at t = -0.1 (0.1 s before the first sample: first value)")
    c.ok(attitude_at(-0.5, ts, qs) is None, "t = -0.5 s is 0.5 s before the first sample: must be None")
    c.near(yaw_of(attitude_at(1.15, ts, qs)), 42.0, 1e-6, "yaw at t = 1.15 (after the last sample, within 0.2 s)")
    c.ok(attitude_at(1.5, ts, qs) is None, "t = 1.5 s is 0.48 s after the last sample: must be None")


@c.test("attitude_at() gives NAVERA's attitude (History + slerp) at every exposure of the turn",
        hint="Run `python3 compare_with_navera.py` to see where you differ. Remember: NAVERA's quaternions are "
             "(x, y, z, w), yours (w, x, y, z).")
def _():
    attitude_at, exposure_time = need(tools(), "attitude_at", "exposure_time")
    c.ok(isinstance(exposure_time(1.0, 0.1), float), "finish exposure_time() first (TODO 3)")
    c.ok(attitude_at(0.05, [0.0, 0.1], [qyaw(0), qyaw(10)]) is not None, "finish attitude_at() first (TODO 8)")
    sys.path.insert(0, os.path.expanduser("~/navera/navera_common"))
    try:
        from navera_common.sensor_history import History, slerp as nslerp
    except Exception as e:                                     # noqa: BLE001
        c.ok(False, f"cannot import NAVERA's sensor_history from ~/navera ({e}) — reset your NAVERA copy?")
    imu = rows("turn_imu.csv")
    it = [float(r["t_s"]) for r in imu]
    iq = [np.array([float(r["qw"]), float(r["qx"]), float(r["qy"]), float(r["qz"])]) for r in imu]
    h = History(maxlen=4000, max_gap_s=0.2, interp=nslerp)
    for t, q in zip(it, iq):
        h.add(t, (q[1], q[2], q[3], q[0]))
    worst, none = 0.0, 0
    for r in rows("turn_frames.csv"):
        e = exposure_time(float(r["grab_time_s"]), 0.138)
        a, b = attitude_at(e, it, iq, 0.2), h.at(e)
        c.ok((a is None) == (b is None), f"at t = {e:.3f} s yours is {'None' if a is None else 'a value'}, "
                                          f"NAVERA's is {'None' if b is None else 'a value'}")
        if a is None:
            none += 1
            continue
        d = abs(float(np.dot(np.asarray(a, float), [b[3], b[0], b[1], b[2]])))
        worst = max(worst, math.degrees(2 * math.acos(min(1.0, d))))
    c.ok(worst < 1e-4, f"your attitude differs from NAVERA's by up to {worst:.4f} deg")
    c.eq(none, ATT_UNUSABLE, "number of exposures without attitude (IMU dropout)")


@c.test("results.json: the analysis of the dataset (python3 analyse.py)",
        hint="Run `python3 analyse.py` after all the TODOs pass; it writes results.json from your functions.")
def _():
    r = load_json("results.json", "python3 analyse.py")
    for k in ("grab_log", "latency_bench", "attitude"):
        c.ok(isinstance(r.get(k), dict), f"results.json has no '{k}' section — run analyse.py again")
    c.near(r["grab_log"]["fps"], GRAB["fps"], 0.001, "results.json grab_log.fps")
    c.eq(int(r["grab_log"]["dropped"]), GRAB["dropped"], "results.json grab_log.dropped")
    c.near(r["latency_bench"]["median_s"], LAT["median_s"], 0.0005, "results.json latency_bench.median_s")
    c.eq(int(r["attitude"]["unusable"]), ATT_UNUSABLE, "results.json attitude.unusable")
    m = r["attitude"]["methods"]
    for k, (deg, metres) in ATT.items():
        c.near(m[k]["median_deg"], deg, max(0.003, 0.03 * deg), f"results.json {k} median_deg")
        c.near(m[k]["median_ground_m"], metres, max(0.01, 0.03 * metres), f"results.json {k} median_ground_m")


@c.test("live GStreamer timing measured (gst_timing.py, with and without 50 ms of work)",
        hint="Run `python3 gst_timing.py` and `python3 gst_timing.py --work-ms 50`, then `python3 analyse.py` again.")
def _():
    r = load_json("results.json", "python3 analyse.py")
    w0, w50 = r.get("gstreamer_w0"), r.get("gstreamer_w50")
    c.ok(w0 is not None, "results.json has no gstreamer_w0: run `python3 gst_timing.py`, then analyse.py")
    c.ok(w50 is not None, "results.json has no gstreamer_w50: run `python3 gst_timing.py --work-ms 50`, then analyse.py")
    c.ok(w0["n"] >= 100, f"only {w0['n']} frames in the gst_timing run (use the default 150)")
    c.ok(20.0 <= w0["fps"] <= 32.0, f"gst_timing without work measured {w0['fps']:.1f} fps — expected close to 28.8 "
                                     "(was the machine very busy? run it again)")
    c.ok(w50["fps"] < 0.8 * w0["fps"], f"with 50 ms of work per frame the rate ({w50['fps']:.1f} fps) should drop well "
                                        f"below {w0['fps']:.1f} fps")
    c.ok(w50.get("lost_vs_nominal", 0) > 0, "with 50 ms of work the appsink should have dropped frames (lost_vs_nominal > 0)")


@c.test("capture.py saved the halves and the stamps (out/top.jpg, out/stamps.csv)",
        hint="Run `python3 capture.py` after finishing the TODOs; it writes the out/ folder.")
def _():
    import cv2
    for name in ("top", "bottom"):
        c.file_exists(f"out/{name}.jpg")
        img = cv2.imread(f"out/{name}.jpg")
        c.ok(img is not None, f"out/{name}.jpg is not an image")
        c.eq((img.shape[1], img.shape[0]), (1920, 540), f"size of out/{name}.jpg")
    c.file_exists("out/stamps.csv")
    with open("out/stamps.csv") as f:
        st = list(csv.DictReader(f))
    c.ok(len(st) >= 10, f"only {len(st)} frames in out/stamps.csv (run capture.py with at least 10)")
    for row in st:
        c.near(float(row["grab_time_s"]) - float(row["exposure_time_s"]), 0.138, 0.0002,
               f"grab - exposure of frame {row['frame']}")
    info = load_json("out/capture_info.json", "python3 capture.py")
    c.ok(10.0 < float(info.get("fps", 0)) < 40.0, f"the frame rate in out/capture_info.json is {info.get('fps')} fps")


@c.test("NAVERA's live camera ran on the recorded frames (out/live_meta.json, out/live_view.jpg)",
        hint="Run `bash live_demo.sh` (lab, step 8) with the vehicle level; it saves the last frame NAVERA published.")
def _():
    import cv2
    meta = load_json("out/live_meta.json", "bash live_demo.sh")
    c.ok(meta.get("attitude_source") == "imu", "the frame has no IMU attitude — was replay_camera.py running?")
    c.ok(meta.get("straightened") is True and meta.get("usable") is True,
         f"the last saved frame is not a usable straightened frame ({meta.get('reason')}) — run `bash live_demo.sh` "
         "again without options")
    c.near(meta.get("camera_hfov_deg"), 111.0, 0.5, "camera_hfov_deg of the published picture")
    if "source_stamp_ns" in meta:
        c.near((meta["source_stamp_ns"] - meta["image_stamp_ns"]) / 1e9, 0.138, 0.002,
               "camera message stamp - exposure stamp (s)")
    c.file_exists("out/live_view.jpg")
    img = cv2.imread("out/live_view.jpg")
    c.ok(img is not None and (img.shape[1], img.shape[0]) == (1920, 540), "out/live_view.jpg should be 1920x540")


SECTIONS = ["## Frame timing", "## Camera delay", "## Attitude at the exposure", "## Recommendation"]


@c.test("report.md: four sections, your numbers, at least 250 words",
        hint="Keep the four headings of the template, replace every TODO with your text, and quote your numbers: "
             "the grab-log fps (2 decimals), the median delay of the bench in ms, the median ground error of "
             "'latest_at_grab' in m, and your own GStreamer fps without work.")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for s in SECTIONS:
        c.ok(s.lower() in text.lower(), f"report.md has no section '{s}'")
    c.ok("TODO" not in text, "report.md still contains 'TODO'")
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    c.ok(words >= 250, f"report.md has about {words} words; write at least 250")
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text)]

    def has(v, tol):
        return any(abs(n - v) <= tol for n in nums)
    c.ok(has(GRAB["fps"], 0.006), "the report does not quote the fps of grab_log.csv (28.55)")
    c.ok(has(LAT["median_s"] * 1000, 0.6) or has(LAT["median_s"], 0.0006),
         "the report does not quote the median delay of the latency bench (in ms or s)")
    c.ok(has(ATT["latest_at_grab"][1], 0.06), "the report does not quote the median ground error (m) of latest_at_grab")
    r = load_json("results.json", "python3 analyse.py")
    if r.get("gstreamer_w0"):
        c.ok(has(r["gstreamer_w0"]["fps"], 0.06), f"the report does not quote your GStreamer fps without work "
                                                  f"({r['gstreamer_w0']['fps']:.2f})")


@c.test("with the real camera: capture.py read it at about 28.8 fps",
        hint="Only when you booked the camera and it was free: run `python3 capture.py 150` again.")
def _():
    info = None
    if os.path.exists("out/capture_info.json"):
        try:
            info = json.load(open("out/capture_info.json"))
        except ValueError:
            info = None
    if not info or info.get("source") != "camera":
        c.skip("no camera capture (camera not booked, absent or busy) — the recorded frames were used")
    c.near(info["fps"], 28.8, 3.0, "fps measured on the camera")


c.run()
