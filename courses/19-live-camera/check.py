import csv
import json
import os

import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/19-live-camera"
DEVICE = "/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0"


def tools():
    return load_student("camera_tools.py")


@c.test("split_halves() cuts a 1920x1080 frame into two 1920x540 halves",
        hint="frame.shape[0] is the height. Cut with slices: frame[:h] and frame[h:], with h = half the height.")
def _():
    (split_halves,) = need(tools(), "split_halves")
    f = np.zeros((1080, 1920, 3), np.uint8)
    f[540:] = 200
    r = split_halves(f)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"split_halves() should return (top, bottom), got {type(r).__name__}")
    top, bottom = r
    c.eq(tuple(top.shape), (540, 1920, 3), "top.shape")
    c.eq(tuple(bottom.shape), (540, 1920, 3), "bottom.shape")
    c.ok(top.max() == 0 and bottom.min() == 200, "top and bottom are swapped (or mixed): the top lens is rows 0 to 539")


@c.test("split_halves() works for any size (not only 1920x1080)",
        hint="Don't write 540: compute half of frame.shape[0].")
def _():
    (split_halves,) = need(tools(), "split_halves")
    f = np.arange(40 * 6).reshape(40, 6).astype(np.uint8)
    r = split_halves(f)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"split_halves() should return (top, bottom), got {type(r).__name__}")
    top, bottom = r
    c.eq(tuple(top.shape), (20, 6), "top.shape of a 6x40 picture")
    c.ok(np.array_equal(top, f[:20]) and np.array_equal(bottom, f[20:]), "the halves are not the right rows")


@c.test("measure_fps() gives the frame rate of a list of grab times (0.0 for fewer than 2)",
        hint="5 frames = 4 gaps. fps = (number of times - 1) / (last time - first time). "
             "With 0 or 1 time there is no gap: check len(grab_times) before dividing.")
def _():
    (measure_fps,) = need(tools(), "measure_fps")
    c.near(measure_fps([0.0, 0.1, 0.2, 0.3, 0.4]), 10.0, 1e-6, "measure_fps([0, 0.1, 0.2, 0.3, 0.4])")
    c.near(measure_fps([5.0, 6.0]), 1.0, 1e-6, "measure_fps([5, 6])")
    c.near(measure_fps([3.0]), 0.0, 1e-9, "measure_fps([3.0]) (one time: no gap)")
    c.near(measure_fps([]), 0.0, 1e-9, "measure_fps([])")


@c.test("measure_fps() of the recorded grab times is about 28.8 fps",
        hint="The check gives your function the 30 times of /data/academy/19-live-camera/grab_times.csv. "
             "Use the first and the last time (grab_times[0], grab_times[-1]), not fixed numbers.")
def _():
    (measure_fps,) = need(tools(), "measure_fps")
    with open(os.path.join(DATA, "grab_times.csv")) as f:
        times = [float(r["grab_time_s"]) for r in csv.DictReader(f)]
    c.near(measure_fps(times), 28.8, 0.2, "measure_fps(recorded times)")


@c.test("exposure_time() puts the stamp back by the camera delay",
        hint="The picture is OLDER than the moment you grab it: subtract the delay.")
def _():
    (exposure_time,) = need(tools(), "exposure_time")
    c.near(exposure_time(100.0, 0.138), 99.862, 1e-9, "exposure_time(100.0, 0.138)")
    c.near(exposure_time(5.0, 0.0), 5.0, 1e-9, "exposure_time(5.0, 0.0)")


@c.test("load_latency() reads latency_s from the calibration file (0.0 when absent)",
        hint="calib is a dict: calib.get(\"latency_s\", 0.0), turned into a float.")
def _():
    (load_latency,) = need(tools(), "load_latency")
    c.near(load_latency(os.path.join(DATA, "insta360_top.yaml")), 0.138, 1e-9, "load_latency(insta360_top.yaml)")
    os.makedirs("out", exist_ok=True)
    tmp = "out/_check_no_latency.yaml"
    with open(tmp, "w") as f:
        f.write("model: fisheye\nimage_width: 1920\n")
    try:
        c.near(load_latency(tmp), 0.0, 1e-9, "load_latency(a file without latency_s)")
    finally:
        os.remove(tmp)


@c.test("capture.py saved the two halves (out/top.jpg, out/bottom.jpg: 1920x540)",
        hint="Run `python3 capture.py` after finishing the TODOs; it writes the out/ folder.")
def _():
    import cv2
    for name in ("top", "bottom"):
        c.file_exists(f"out/{name}.jpg")
        img = cv2.imread(f"out/{name}.jpg")
        c.ok(img is not None, f"out/{name}.jpg is not an image")
        c.eq((img.shape[1], img.shape[0]), (1920, 540), f"size of out/{name}.jpg")


@c.test("out/stamps.csv: every exposure time is its grab time - 0.138 s",
        hint="Run `python3 capture.py` again once exposure_time() and load_latency() are right.")
def _():
    c.file_exists("out/stamps.csv")
    with open("out/stamps.csv") as f:
        rows = list(csv.DictReader(f))
    c.ok(len(rows) >= 10, f"only {len(rows)} frames in out/stamps.csv (run capture.py with at least 10)")
    for r in rows:
        g, e = float(r["grab_time_s"]), float(r["exposure_time_s"])
        c.near(g - e, 0.138, 0.0002, f"grab - exposure of frame {r['frame']}")
    c.file_exists("out/capture_info.json")
    with open("out/capture_info.json") as f:
        info = json.load(f)
    c.ok(10.0 < float(info["fps"]) < 40.0, f"the frame rate in out/capture_info.json is {info['fps']} fps")


@c.test("NAVERA's live camera ran on the recorded frames (out/live_meta.json)",
        hint="Run `bash live_demo.sh` (lab, step 6). It saves the last frame NAVERA published in out/.")
def _():
    c.file_exists("out/live_meta.json")
    with open("out/live_meta.json") as f:
        meta = json.load(f)
    c.ok(meta.get("attitude_source") == "imu", "the frame has no IMU attitude — was replay_camera.py running?")
    c.ok(meta.get("straightened") is True, "the frame was not straightened")
    c.near(meta.get("camera_hfov_deg"), 111.0, 0.5, "camera_hfov_deg of the published picture")
    if "source_stamp_ns" in meta:
        c.near((meta["source_stamp_ns"] - meta["image_stamp_ns"]) / 1e9, 0.138, 0.002,
               "camera message stamp - exposure stamp (s)")


@c.test("the published picture is the straightened top lens (out/live_view.jpg: 1920x540)",
        hint="watch_live.py saves it — run `bash live_demo.sh` again if the file is missing.")
def _():
    import cv2
    c.file_exists("out/live_view.jpg")
    img = cv2.imread("out/live_view.jpg")
    c.ok(img is not None, "out/live_view.jpg is not an image")
    c.eq((img.shape[1], img.shape[0]), (1920, 540), "size of out/live_view.jpg")


QUIZ = {"Q1": ("b", "The light hit the sensor BEFORE the frame arrived: which attitude belongs to the picture?"),
        "Q2": ("a", "Read the part about grab() and retrieve() in the course again."),
        "Q3": ("b", "Think of a vehicle at 20 m/s and a frame that waited 2 s in a queue."),
        "Q4": ("a", "Look at the crop parameter in live_demo.sh.")}
for q, (good, hint) in QUIZ.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")


@c.test("with the real camera: capture.py read it at about 28.8 fps",
        hint="Book the camera in the dashboard, then run `python3 capture.py` again.")
def _():
    if not os.path.exists(DEVICE):
        c.skip("no camera in your sandbox (not booked) — the recorded frames were used")
    import cv2
    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
    free = cap.isOpened() and cap.grab()
    cap.release()
    if not free:
        c.skip("the camera is booked but busy or not sending — the recorded frames were used")
    c.file_exists("out/capture_info.json")
    with open("out/capture_info.json") as f:
        info = json.load(f)
    c.ok(info.get("source") == "camera", "out/capture_info.json says the frames were recorded ones: "
                                         "run capture.py again now that the camera is here")
    c.near(info["fps"], 28.8, 3.0, "fps measured on the camera")


c.run()
