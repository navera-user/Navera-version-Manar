"""mission.py — use navlib to answer the mission planner's questions (lab 3, Step 6).

Scenario (synthetic numbers): an inspection of a point 9 km from the take-off site, from a
small harbour on a desert coast, along the ground track 030° (north-north-east), and back.
Wind: 5 m/s blowing TOWARDS the south-west, i.e. wind_east = -3 m/s, wind_north = -4 m/s.

Run:   python3 mission.py        -> prints a summary and writes results.json
"""
import json

import numpy as np

from navlib import FixedWing, Vehicle, load_track, wind_correction

LEG_M = 9000.0
TRACK_OUT_DEG = 30.0
WIND_E, WIND_N = -3.0, -4.0


def round_trip_min(vehicle):
    """Minutes to fly LEG_M out along TRACK_OUT_DEG and back, with the wind."""
    # TODO B1: two calls of wind_correction() (out: TRACK_OUT_DEG, back: the opposite track,
    #          kept in [0, 360) with % 360), then time = distance / ground speed for each leg.
    raise NotImplementedError("mission TODO B1")


def main():
    results = {}

    # TODO A — the wind triangle for the quad (airspeed 12 m/s) on the OUTBOUND leg:
    #          store the heading to fly and the ground speed.
    quad = Vehicle("quad", 12.0, 160.0, 350.0)
    results["out_heading_deg"] = None
    results["out_ground_speed_ms"] = None

    # TODO B2 — for the quad AND this fixed wing, store (use v.name in the key):
    #   "<name>_endurance_min", "<name>_round_trip_min", "<name>_can_do_it" (a bool)
    #   then "wing_turn_radius_m" for a 30° bank.
    wing = FixedWing("wing", 20.0, 150.0, 220.0, 12.0)

    # TODO C — the recorded survey track (file harbour_track.csv): load it with load_track(),
    #   then store "track_points", "track_length_m", "track_max_speed_ms",
    #   "track_median_speed_ms" and
    #   "glitch_time_s": the time t of the FIRST point reached at more than 25 m/s
    #   (a boolean mask on the speeds, np.argmax, and mind the index shift: speed i ends at point i+1).
    #   Convert NumPy numbers with float(...) so that json can write them.

    # ---- you don't need to change anything below this line ----
    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)
    for k, v in results.items():
        if isinstance(v, float):
            print(f"{k:<26} {v:12.3f}")
        else:
            print(f"{k:<26} {v!s:>12}")
    print("-> results.json written")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError as e:
        print(f"{e} is not written yet — finish it first (python3 navlib.py shows where you are in navlib.py).")
