"""mission.py — use navlib to answer the mission planner's questions (lab 3, Step 6).

Scenario (synthetic numbers): an inspection of a point 9 km from the take-off site, on a
port of the Batinah coast, along the ground track 030° (north-north-east), and back.
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
    _, gs_out = wind_correction(vehicle.cruise_ms, TRACK_OUT_DEG, WIND_E, WIND_N)
    _, gs_back = wind_correction(vehicle.cruise_ms, (TRACK_OUT_DEG + 180.0) % 360.0, WIND_E, WIND_N)
    return (LEG_M / gs_out + LEG_M / gs_back) / 60.0


def main():
    results = {}

    # TODO A — the wind triangle for the quad (airspeed 12 m/s) on the outbound leg
    quad = Vehicle("quad", 12.0, 160.0, 350.0)
    heading, gs = wind_correction(quad.cruise_ms, TRACK_OUT_DEG, WIND_E, WIND_N)
    results["out_heading_deg"] = heading
    results["out_ground_speed_ms"] = gs

    # TODO B — endurance and round trip for the quad and for the fixed wing
    wing = FixedWing("wing", 20.0, 150.0, 220.0, 12.0)
    for v in (quad, wing):
        endurance = v.endurance_s() / 60.0
        trip = round_trip_min(v)
        results[f"{v.name}_endurance_min"] = endurance
        results[f"{v.name}_round_trip_min"] = trip
        results[f"{v.name}_can_do_it"] = trip <= endurance
    results["wing_turn_radius_m"] = wing.turn_radius_m(30.0)

    # TODO C — the recorded survey track
    track = load_track("sohar_track.csv", "survey")
    t, _, _ = track.arrays()
    speeds = track.speeds_ms()
    results["track_points"] = len(track)
    results["track_length_m"] = track.length_m()
    results["track_max_speed_ms"] = float(np.max(speeds))
    results["track_median_speed_ms"] = float(np.median(speeds))
    results["glitch_time_s"] = float(t[np.argmax(speeds > 25.0) + 1])

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
