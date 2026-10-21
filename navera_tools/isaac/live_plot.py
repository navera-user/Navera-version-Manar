#!/usr/bin/env python3
"""NAVERA - live error: the Isaac Sim flight's truth vs NAVERA's position, live (matplotlib/Tk).

    python3 navera_tools/isaac/live_plot.py ~/navera_results/<run> [--gps-cut 60] [--scene DIR]

Reads isaac_link.py's record as it grows (position.csv, day.csv, live.json, latest_frame.jpg):
the track (truth, and NAVERA's output coloured by what produced it), the error over time with
NAVERA's stated 1-sigma, the frame NAVERA received, and the status. Saves a snapshot every
2 s into plot/ (for the run's video) and plot_final.png when the run has finished; the window
stays open until it is closed.
"""
import csv
import json
import math
import os
import sys
import time

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402

TITLE = "NAVERA - live error"
COL = {("gps", "measured"): "#1f77b4", ("day", "measured"): "#2ca02c", ("day", "propagated"): "#ff7f0e"}


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [r for r in csv.DictReader(f) if r.get("t")]


def main():
    res = os.path.expanduser(sys.argv[1])
    arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d     # noqa: E731
    cut = float(arg("--gps-cut", 60.0))
    scene = arg("--scene", "")
    bg = None
    if scene and os.path.exists(os.path.join(scene, "scene.json")):
        import cv2
        sc = json.load(open(os.path.join(scene, "scene.json")))
        img = cv2.imread(os.path.join(scene, "mosaic.jpg"), cv2.IMREAD_REDUCED_COLOR_4)
        mo = sc["mosaic"]
        k = 111320.0 * math.cos(math.radians(sc["lat0"]))
        bg = (img[:, :, ::-1], [(mo["lon_w"] - sc["lon0"]) * k, (mo["lon_e"] - sc["lon0"]) * k,
                                (mo["lat_s"] - sc["lat0"]) * 111320.0, (mo["lat_n"] - sc["lat0"]) * 111320.0],
              sc["lat0"], sc["lon0"])
    os.makedirs(os.path.join(res, "plot"), exist_ok=True)
    plt.rcParams.update({"font.size": 9})
    fig = plt.figure(TITLE, figsize=(13, 7.5))
    try:
        fig.canvas.manager.set_window_title(TITLE)
    except Exception:                                    # noqa: BLE001
        pass
    gs = fig.add_gridspec(2, 3, width_ratios=[1.1, 1.4, 1.1])
    ax_map, ax_err = fig.add_subplot(gs[:, 0]), fig.add_subplot(gs[0, 1:])
    ax_img, ax_txt = fig.add_subplot(gs[1, 1]), fig.add_subplot(gs[1, 2])
    plt.tight_layout()
    plt.ion()
    plt.show(block=False)
    last_snap, k, final = 0.0, 0, False
    while plt.fignum_exists(fig.number):
        pos = read_csv(os.path.join(res, "position.csv"))
        live = {}
        try:
            live = json.load(open(os.path.join(res, "live.json")))
        except (OSError, ValueError):
            pass
        lat0 = next((float(r["truth_lat"]) for r in pos if r["valid"] == "1"), None)
        ekf = read_csv(os.path.join(res, "ekf.csv"))
        if os.path.exists(os.path.join(res, "gps_cut")):
            try:
                cut = float(open(os.path.join(res, "gps_cut")).read())
            except ValueError:
                pass
        ax_map.cla(), ax_err.cla(), ax_txt.cla()
        if lat0:
            lon0 = next(float(r["truth_lon"]) for r in pos if r["valid"] == "1")
            if bg is not None:
                lat0, lon0 = bg[2], bg[3]
                ax_map.imshow(bg[0], extent=bg[1], origin="upper")
            kx = 111320.0 * math.cos(math.radians(lat0))
            en = lambda la, lo: ((lo - lon0) * kx, (la - lat0) * 111320.0)      # noqa: E731
            v = [r for r in pos if r["valid"] == "1"]
            tr = [en(float(r["truth_lat"]), float(r["truth_lon"])) for r in v]
            ax_map.plot([p[0] for p in tr], [p[1] for p in tr], "-", color="0.4", lw=1, label="truth")
            for key, c in COL.items():
                pts = [en(float(r["lat"]), float(r["lon"])) for r in v if (r["source"], r["mode"]) == key]
                if pts:
                    ax_map.plot([p[0] for p in pts], [p[1] for p in pts], ".", ms=3, color=c, label="/".join(key))
            if ekf:
                pe = [en(float(r["ekf_lat"]), float(r["ekf_lon"])) for r in ekf]
                ax_map.plot([p[0] for p in pe], [p[1] for p in pe], "-", color="#d62728", lw=0.8, label="autopilot EKF")
            if bg is not None and tr:
                xs, ys = [p[0] for p in tr], [p[1] for p in tr]
                ax_map.set_xlim(min(xs) - 400, max(xs) + 400)
                ax_map.set_ylim(min(ys) - 400, max(ys) + 400)
            ax_map.set_aspect("equal")
            ax_map.legend(loc="upper right", fontsize=7)
            ax_map.set_title("track (m, from the first fix)")
            for key, c in COL.items():
                pts = [(float(r["t"]), float(r["err_m"])) for r in v if (r["source"], r["mode"]) == key
                       and r["err_m"] not in ("", "nan")]
                if pts:
                    ax_err.plot([p[0] for p in pts], [p[1] for p in pts], ".", ms=3, color=c, label="/".join(key))
            if ekf:
                ax_err.plot([float(r["t"]) for r in ekf], [max(float(r["err_m"]), 0.1) for r in ekf], "-",
                            color="#d62728", lw=0.8, label="autopilot EKF")
            sg = [(float(r["t"]), float(r["sigma_m"])) for r in v if r["sigma_m"] not in ("", "nan")]
            if sg:
                ax_err.plot([p[0] for p in sg], [p[1] for p in sg], "-", color="0.6", lw=0.8, label="stated 1-sigma")
            ax_err.axvline(cut, color="r", ls="--", lw=1)
            ax_err.text(cut, ax_err.get_ylim()[1] * 0.95, " GPS cut", color="r", va="top", fontsize=8)
            ax_err.set_yscale("log")
            ax_err.set_xlabel("flight time (s)")
            ax_err.set_ylabel("error vs truth (m)")
            ax_err.grid(True, which="both", alpha=0.3)
            ax_err.legend(loc="upper left", fontsize=7)
            after = sorted(float(r["err_m"]) for r in v if float(r["t"]) >= cut and r["err_m"] not in ("", "nan"))
        else:
            after = []
        ax_err.set_title("NAVERA position error (log)")
        fp = os.path.join(res, "latest_frame.jpg")
        if os.path.exists(fp):
            try:
                img = plt.imread(fp)
                ax_img.cla()
                ax_img.imshow(img)
                ax_img.set_title("what NAVERA's camera delivers (fisheye, H.264, delayed)", fontsize=8)
                ax_img.axis("off")
            except (OSError, ValueError, SyntaxError):
                pass
        lines = [f"t = {live.get('t', 0):.0f} s   GPS: {live.get('gps', '-')}",
                 *([f"autopilot: {live.get('ap_mode')}  {live.get('phase')}",
                    f"autopilot EKF error: {live.get('ekf_err_m', '-')} m"] if live.get("ap_mode") else []),
                 f"NAVERA state: {live.get('state', '-')}   source: {live.get('source', '-')}/{live.get('mode', '-')}",
                 f"error now: {live.get('err_m', '-')} m   stated sigma: {live.get('sigma_m', '-')} m",
                 f"camera frames: rendered {live.get('frames_in', 0)}, delivered {live.get('frames_out', 0)}"]
        d = live.get("day") or {}
        if d:
            lines.append(f"last frame {d.get('frame_id')}: {'ACCEPTED' if d.get('success') else 'rejected'} "
                         f"{str(d.get('reason') or '')[:40]}")
        lat = live.get("latency") or {}
        if lat:
            lines.append("camera delay est.: " + ", ".join(f"{k} {v}" for k, v in list(lat.items())[:3]))
        if after:
            lines.append(f"after GPS cut: median {after[len(after) // 2]:.1f} m, "
                         f"p90 {after[int(0.9 * len(after))]:.1f} m, max {after[-1]:.1f} m")
        if os.path.exists(os.path.join(res, "summary.json")):
            try:
                s = json.load(open(os.path.join(res, "summary.json")))["after_cut"]
                lines += ["", "FINISHED", f"accepted {s['accepted']}/{s['frames']} ({s['accepted_pct']} %)",
                          f"fix error median {s['fix_err_stamp_m']['median']} m, p90 {s['fix_err_stamp_m']['p90']} m",
                          f"wrong fixes (>50 m): {s['wrong_fixes']}"]
            except (OSError, ValueError, KeyError):
                pass
        ax_txt.axis("off")
        ax_txt.text(0.0, 1.0, "\n".join(lines), va="top", family="monospace", fontsize=8.5, transform=ax_txt.transAxes)
        ax_txt.set_title(os.path.basename(res.rstrip("/")), fontsize=9)
        fig.canvas.draw_idle()
        plt.pause(1.0)
        if time.time() - last_snap > 2.0 and not final and live.get("t", 0) > 0:
            fig.savefig(os.path.join(res, "plot", f"p_{k:05d}.png"), dpi=70)
            k, last_snap = k + 1, time.time()
        if os.path.exists(os.path.join(res, "finished")) and os.path.exists(os.path.join(res, "summary.json")) \
                and not final:
            fig.savefig(os.path.join(res, "plot_final.png"), dpi=110)
            final = True


if __name__ == "__main__":
    main()
