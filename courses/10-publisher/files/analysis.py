#!/usr/bin/env python3
"""analysis.py — how good is the fake GPS? Writes results.json for the check.

    python3 analysis.py

Part 1 (TODO 8, 9): the error of the flat-Earth conversion of fake_gps.py, compared with the
great circle that NAVERA computes (navera_common.geo.dead_reckon, imported from YOUR NAVERA copy).
Part 2: your measurements of the running node (`ros2 topic hz` and `ros2 topic bw`), copied below.
"""
import json
import math

from navera_common.geo import dead_reckon, haversine_m

from fake_gps import EARTH_RADIUS_M, offset_to_latlon, velocity_ne

START = (35.8277, 10.6388)          # Sousse, the fake GPS's default start
DISTANCES_M = [1_000.0, 10_000.0, 100_000.0]

# ---- Part 2: copy YOUR measurements here (lab, step 6). Numbers, without quotes.
MEASURED = {
    "rate_hz": None,          # `average rate` of ros2 topic hz /fake_gps/fix
    "period_min_s": None,     # `min`
    "period_max_s": None,     # `max`
    "period_std_s": None,     # `std dev`
    "msg_bytes": None,        # `Message size mean` of ros2 topic bw /fake_gps/fix
}


def flat_error_m(distance_m, heading_deg, start=START):
    """Distance (m) between the flat-Earth end point and the great-circle end point after driving
    `distance_m` from `start` with a constant initial heading."""
    # TODO 8:
    #   1. north, east = the offset in metres: velocity_ne(distance_m, heading_deg) gives exactly
    #      that if you pretend the "speed" is the distance travelled in 1 s.
    #   2. flat = offset_to_latlon(start[0], start[1], north, east)
    #   3. sphere = dead_reckon(start[0], start[1], heading_deg, distance_m, 1.0)  (NAVERA: d = speed * dt)
    #   4. return haversine_m(flat[0], flat[1], sphere[0], sphere[1])
    return 0.0


def predicted_due_east_m(distance_m, lat_deg):
    """The course's small-distance formula for a due-east drive: y = d^2 * tan(lat) / (2R)."""
    # TODO 9: implement the formula (tan of the latitude in RADIANS, R = EARTH_RADIUS_M).
    return 0.0


# ---- you don't need to change anything below this line ----
def main():
    res = {"flat_error_heading30_m": {}, "flat_error_east_m": {}, "predicted_east_m": {}}
    print(f"{'distance':>10} | {'heading 30':>12} | {'due east':>10} | {'formula (east)':>14}")
    for d in DISTANCES_M:
        e30, e90, p90 = flat_error_m(d, 30.0), flat_error_m(d, 90.0), predicted_due_east_m(d, START[0])
        key = str(int(d))
        res["flat_error_heading30_m"][key] = e30
        res["flat_error_east_m"][key] = e90
        res["predicted_east_m"][key] = p90
        print(f"{d / 1000:>7.0f} km | {e30:>10.3f} m | {e90:>8.3f} m | {p90:>12.3f} m")
    res["measured"] = MEASURED
    with open("results.json", "w") as f:
        json.dump(res, f, indent=2)
    print("written results.json")


if __name__ == "__main__":
    main()
