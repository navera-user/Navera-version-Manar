#!/usr/bin/env python3
"""Live plot for sitl_closed_loop.py --viewer: the autopilot's position error and NAVERA's.

    python3 navera_tools/tests/sitl_live_plot.py <work dir>/live.jsonl

Follows the file written by the closed-loop run (one JSON line per 0.2 s of simulation): the
autopilot's EKF position minus the simulator's truth, the error of the last position NAVERA sent
(vs the truth of its instant) and the accuracy NAVERA stated for it. Shaded: GPS still used.
Display only; the numbers are in the run's JSON.
"""
import json
import sys

import matplotlib.pyplot as plt


def main(path):
    plt.ion()
    fig, ax = plt.subplots(figsize=(7, 3.6))
    fig.canvas.manager.set_window_title("NAVERA closed loop: error vs truth")
    rows, pos = [], 0
    while plt.fignum_exists(fig.number):
        with open(path) as f:
            f.seek(pos)
            for line in f:
                if line.endswith("\n"):
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
            pos = f.tell()
        if rows:
            t = [r["t"] for r in rows]
            ax.clear()
            ax.plot(t, [r["ekf_err"] for r in rows], label="autopilot (EKF) error", lw=1.6)
            ax.plot(t, [r["navera_err"] for r in rows], ".", ms=2.5, label="NAVERA position error")
            ax.plot(t, [r["navera_sigma"] for r in rows], "--", lw=1, label="NAVERA stated sigma")
            gps_t = [r["t"] for r in rows if r.get("gps")]
            if gps_t:
                ax.axvspan(t[0], max(gps_t), color="0.85", label="GPS")
            last = rows[-1]
            ax.set_title(f"{last.get('scenario', '')}   mode {last['mode']}   EKF error {last['ekf_err']:.0f} m",
                         fontsize=10)
            ax.set_xlabel("simulation time (s)")
            ax.set_ylabel("m")
            ax.set_ylim(0, max(60.0, min(400.0, max(r["ekf_err"] for r in rows) * 1.1)))
            ax.legend(loc="upper left", fontsize=8)
            ax.grid(alpha=0.3)
        plt.pause(1.0)


if __name__ == "__main__":
    main(sys.argv[1])
