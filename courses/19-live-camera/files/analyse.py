#!/usr/bin/env python3
# Lesson 19 — the analysis of the lab. Uses YOUR functions of camera_tools.py on the lesson's
# data (/data/academy/19-live-camera) and on your own measurements in out/, then writes:
#
#   results.json            every number of your report (the check reads it)
#   out/jitter.png          histogram of the frame intervals of grab_log.csv
#   out/latency.png         the 20 flash delays of the latency bench
#   out/attitude_error.png  attitude error at each frame, for three ways of choosing it
#
#     python3 analyse.py
# You don't need to change this file — but read it: it is the experiment.
import bisect
import json
import math
import os
import sys
import time

import numpy as np

import camera_tools as ct

HEIGHT_M = 150.0                       # flight height used to turn an angle into metres


def need(value, todo):
    if value is None:
        sys.exit(f"finish {todo} in camera_tools.py first")
    return value


def stats_deg(errors):
    e = np.asarray(errors, float)
    ground = HEIGHT_M * np.tan(np.radians(e))
    return {"median_deg": round(float(np.median(e)), 4), "p95_deg": round(float(np.percentile(e, 95)), 4),
            "max_deg": round(float(e.max()), 4), "median_ground_m": round(float(np.median(ground)), 3),
            "max_ground_m": round(float(ground.max()), 3)}


def main():
    res = {}
    os.makedirs("out", exist_ok=True)

    # ---- 1. frame timing of a 60 s grab log --------------------------------------------
    grab = [float(r["grab_time_s"]) for r in ct.read_csv(ct.DATA + "/grab_log.csv")]
    st = need(ct.frame_stats(grab), "TODO 2 (frame_stats)")
    res["grab_log"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in st.items()}
    print(f"grab_log.csv: {st['n']} frames, {st['fps']:.3f} fps, median period {st['median_ms']:.2f} ms, "
          f"jitter {st['jitter_ms']:.2f} ms, max gap {st['max_gap_ms']:.1f} ms, ~{st['dropped']} dropped")

    # ---- 2. the latency bench ---------------------------------------------------------
    flashes = [float(r["t_white_s"]) for r in ct.read_csv(ct.DATA + "/flashes.csv")]
    rows = ct.read_csv(ct.DATA + "/flash_frames.csv")
    ft = [float(r["grab_time_s"]) for r in rows]
    br = [float(r["brightness"]) for r in rows]
    d = need(ct.latency_from_flashes(flashes, ft, br), "TODO 5 (latency_from_flashes)")
    if not d:
        sys.exit("latency_from_flashes() found no flash: check the lo / hi windows")
    period = float(np.median(np.diff(ft)))
    res["latency_bench"] = {"n_flashes": len(d), "median_s": round(float(np.median(d)), 4),
                            "mean_s": round(float(np.mean(d)), 4), "min_s": round(float(min(d)), 4),
                            "max_s": round(float(max(d)), 4), "std_s": round(float(np.std(d)), 4),
                            "frame_period_s": round(period, 5),
                            "mean_minus_half_period_s": round(float(np.mean(d)) - period / 2, 4)}
    print(f"latency bench: {len(d)} flashes, median {np.median(d) * 1000:.1f} ms, min {min(d) * 1000:.1f}, "
          f"max {max(d) * 1000:.1f}, std {np.std(d) * 1000:.1f} ms (frame period {period * 1000:.1f} ms)")
    lat = need(ct.load_latency(ct.CALIB), "TODO 4 (load_latency)")
    res["calibration_latency_s"] = lat

    # ---- 3. attitude at the exposure ---------------------------------------------------
    imu = ct.read_csv(ct.DATA + "/turn_imu.csv")
    it = [float(r["t_s"]) for r in imu]
    iq = [np.array([float(r["qw"]), float(r["qx"]), float(r["qy"]), float(r["qz"])]) for r in imu]
    frames = ct.read_csv(ct.DATA + "/turn_frames.csv")
    err = {"latest_at_grab": [], "nearest_at_exposure": [], "slerp_at_exposure": []}
    t_ok, unusable = [], 0
    for r in frames:
        g = float(r["grab_time_s"])
        e = need(ct.exposure_time(g, lat), "TODO 3 (exposure_time)")
        truth = np.array([float(r[k]) for k in ("true_qw", "true_qx", "true_qy", "true_qz")])
        q_slerp = ct.attitude_at(e, it, iq, 0.2)
        if q_slerp is None:                  # NAVERA marks such a frame unusable
            unusable += 1
            continue
        i = bisect.bisect_right(it, g) - 1                   # last sample received before the grab
        q_latest = iq[max(i, 0)]
        j = bisect.bisect_left(it, e)                        # sample nearest to the exposure
        cand = [k for k in (j - 1, j) if 0 <= k < len(it)]
        q_near = iq[min(cand, key=lambda k: abs(it[k] - e))]
        for name, q in (("latest_at_grab", q_latest), ("nearest_at_exposure", q_near), ("slerp_at_exposure", q_slerp)):
            a = need(ct.quat_angle_deg(q, truth), "TODO 6 (quat_angle_deg)")
            err[name].append(a)
        t_ok.append(e - it[0])
    res["attitude"] = {"frames": len(frames), "unusable": unusable, "height_m": HEIGHT_M,
                       "methods": {k: stats_deg(v) for k, v in err.items()}}
    print(f"attitude: {len(frames)} frames, {unusable} unusable (no IMU sample within 0.2 s of the exposure)")
    for k, v in res["attitude"]["methods"].items():
        print(f"   {k:20s} median {v['median_deg']:.3f} deg  p95 {v['p95_deg']:.3f}  max {v['max_deg']:.3f} deg"
              f"  -> at {HEIGHT_M:.0f} m: median {v['median_ground_m']:.2f} m, max {v['max_ground_m']:.2f} m")

    # ---- 4. your live measurements -------------------------------------------------------
    for w in (0, 50):
        p = f"out/gst_timing_w{w}.json"
        res[f"gstreamer_w{w}"] = json.load(open(p)) if os.path.exists(p) else None
        if res[f"gstreamer_w{w}"] is None:
            print(f"(no {p} yet: run  python3 gst_timing.py" + (f" --work-ms {w}" if w else "") + ")")
    res["capture"] = json.load(open("out/capture_info.json")) if os.path.exists("out/capture_info.json") else None
    import cv2
    buf = np.fromfile(ct.DATA + "/frames/frame_000.jpg", np.uint8)
    t0 = time.perf_counter()
    for _ in range(10):
        cv2.imdecode(buf, cv2.IMREAD_COLOR)
    res["mjpg_decode_ms"] = round((time.perf_counter() - t0) / 10 * 1000, 2)
    res["mjpg_frame_kb"] = round(len(buf) / 1000, 1)
    print(f"decoding one 1920x1080 JPEG ({len(buf) // 1000} kB) here: {res['mjpg_decode_ms']} ms")

    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    print("saved results.json")

    # ---- plots --------------------------------------------------------------------------
    import warnings
    warnings.filterwarnings("ignore")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    di = np.diff(grab) * 1000
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.hist(di[di < 60], bins=80, color="#0b6e8a")
    ax.set_xlabel("interval between grabs (ms)  [intervals > 60 ms not shown]")
    ax.set_ylabel("count")
    ax.set_title(f"grab_log.csv: median {np.median(di):.2f} ms, jitter {np.std(di):.2f} ms, max {di.max():.0f} ms")
    fig.tight_layout()
    fig.savefig("out/jitter.png", dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(np.array(d) * 1000, "o", color="#d64545")
    ax.axhline(np.median(d) * 1000, color="#1d2733", lw=1, label="median")
    ax.set_xlabel("flash")
    ax.set_ylabel("delay (ms)")
    ax.set_title("latency bench: one delay per flash (spread = one frame period)")
    ax.legend()
    fig.tight_layout()
    fig.savefig("out/latency.png", dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.8))
    for k, col in (("latest_at_grab", "#d64545"), ("nearest_at_exposure", "#e0a030"), ("slerp_at_exposure", "#0b6e8a")):
        ax.semilogy(t_ok, np.maximum(err[k], 1e-3), ".", ms=3, color=col, label=k)
    ax.set_xlabel("time in the flight (s)")
    ax.set_ylabel("attitude error (deg, log)")
    ax.set_title("which attitude belongs to the picture?")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig("out/attitude_error.png", dpi=100)
    plt.close(fig)
    print("saved out/jitter.png, out/latency.png, out/attitude_error.png")


if __name__ == "__main__":
    main()
