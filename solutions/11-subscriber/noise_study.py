#!/usr/bin/env python3
"""noise_study.py — what does GNSS noise do to speed and distance? (no ROS: runs in a second)

It replays 2 minutes of the track player's drive (6 m/s, 2 Hz) through YOUR Tracker, without
noise and with 3 m of Gaussian noise (fixed random seed: everybody gets the same numbers), and
writes the statistics into results.json (section "noise").

    python3 noise_study.py
"""
import json
import math
import random
import statistics

from gps_listener import Tracker, haversine_m
from gps_track_player import route_point, to_latlon

SPEED, RATE, DURATION = 6.0, 2.0, 120.0


def run(noise_m, seed=7):
    rng = random.Random(seed)
    tr = Tracker(window=10)
    inst, win = [], []
    n = int(DURATION * RATE)
    for k in range(n):
        t = k / RATE
        north, east = route_point(SPEED * t)
        if noise_m > 0:
            north, east = north + rng.gauss(0, noise_m), east + rng.gauss(0, noise_m)
        lat, lon = to_latlon(north, east)
        v = tr.update(lat, lon, 1_800_000_000.0 + t, 0)
        if v is not None:
            inst.append(v)
        if tr.window_speed_mps is not None and len(tr.history) == tr.history.maxlen:
            win.append(tr.window_speed_mps)
    true_distance = SPEED * (n - 1) / RATE
    out = {"fixes": tr.count,
           "true_distance_m": true_distance,
           "distance_m": tr.distance_m,
           "distance_ratio": tr.distance_m / true_distance if true_distance else None}
    for name, xs in (("instant", inst), ("window", win)):
        out[f"{name}_mean_mps"] = statistics.fmean(xs) if xs else None
        out[f"{name}_std_mps"] = statistics.pstdev(xs) if len(xs) > 1 else None
    return out


def main():
    res = {}
    try:
        with open("results.json") as f:
            res = json.load(f)
    except (OSError, ValueError):
        pass
    res["noise"] = {"sigma_0m": run(0.0), "sigma_3m": run(3.0)}
    if res["noise"]["sigma_0m"]["fixes"] == 0:
        print("TODO 1/2 not done yet: your Tracker accepted no fix, so all the numbers below are 0.")
    with open("results.json", "w") as f:
        json.dump(res, f, indent=2)
    for k, r in res["noise"].items():
        print(f"{k}: distance {r['distance_m']:.0f} m (true {r['true_distance_m']:.0f} m, ratio "
              f"{r['distance_ratio']:.2f}) | instant speed {r['instant_mean_mps'] or 0:.2f} ± "
              f"{r['instant_std_mps'] or 0:.2f} m/s | window speed {r['window_mean_mps'] or 0:.2f} ± "
              f"{r['window_std_mps'] or 0:.2f} m/s")
    print("written results.json")


if __name__ == "__main__":
    main()
