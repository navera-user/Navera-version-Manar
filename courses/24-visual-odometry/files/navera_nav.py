"""Lesson 24 — The flight through NAVERA's VisionNavigator (day_pkg/vision_nav.py).

Run:   python3 navera_nav.py
GPS for the first 4 frames, then lost. Your visual odometry (vo.py) feeds
VisionNavigator.odometry() as a velocity; scenario A gives it the map fixes of
map_fixes.csv, scenario B none at all. Prints what NAVERA would output.
"""
import json
import math

import vo                      # your vo.py (TODOs 1-6 needed)


# TODO 11: NAVERA's odometry gate, written by you
def vo_gate(v_vo, v_ref, vel_sigma):
    """True when a visual-odometry velocity v_vo = (ve, vn) m/s may be used, given the velocity
    v_ref the map fixes measured and its uncertainty vel_sigma (m/s): the difference |v_vo - v_ref|
    must not exceed max(3 vel_sigma, 0.3 |v_ref|, 3.0)."""
    raise NotImplementedError("TODO 11")


# ---- you don't need to change anything below this line ----

M_PER_DEG = 111_320.0


def en_to_latlon(e, n, lat0, lon0):
    return lat0 + n / M_PER_DEG, lon0 + e / (M_PER_DEG * math.cos(math.radians(lat0)))


def latlon_err(lat, lon, e, n, lat0, lon0):
    tl, tn = en_to_latlon(e, n, lat0, lon0)
    return math.hypot((lat - tl) * M_PER_DEG, (lon - tn) * M_PER_DEG * math.cos(math.radians(lat0)))


def fly(steps, truth, fixes, info, use_fixes):
    from vision_nav import VisionNavigator
    lat0, lon0 = info["start_lat"], info["start_lon"]
    nav = VisionNavigator()
    rows, gate_agree = [], 0
    for t in range(len(truth)):
        e, n = truth[t]
        if t < 4:                                          # GPS still good
            nav.gps(float(t), *en_to_latlon(e, n, lat0, lon0), sigma_m=5.0)
        else:
            de, dn = steps[t - 1]
            mine = vo_gate((de, dn), nav.vel, nav.vel_sigma) if nav.vel is not None else True
            theirs = nav.odometry(float(t), de, dn, 1.0, 1.0)
            gate_agree += int(mine == theirs)
            if use_fixes and t in fixes:
                la, lo = en_to_latlon(*fixes[t], lat0, lon0)
                nav.update(float(t), {"accepted": True, "predicted_lat": la, "predicted_lon": lo,
                                      "inliers": 120, "sigma_m": 4.0, "spread": 1.0}, None)
        lat, lon, sig, mode = nav.output(float(t))
        err = None if lat is None else latlon_err(lat, lon, e, n, lat0, lon0)
        rows.append((t, mode, sig, err))
    return rows, gate_agree


def main():
    info, frames, truth, fixes, _ = vo.load_flight()
    mpp = vo.frame_m_per_px(info["altitude_m"], info["camera_hfov_deg"], info["width_px"])
    steps = vo.measure_steps(frames, mpp, "numpy")
    out = {}
    for name, use in (("A_with_fixes", True), ("B_no_fixes", False)):
        rows, agree = fly(steps, truth, fixes, info, use)
        print(f"\nScenario {name}: frame, NAVERA's mode, stated sigma, true error")
        for t, mode, sig, err in rows:
            if t % 5 == 0 or (mode == "unavailable" and rows[t - 1][1] != "unavailable"):
                print(f"  {t:3d}  {mode:12s} sigma {sig:7.1f} m   error "
                      + ("   --" if err is None else f"{err:6.1f} m"))
        first_off = next((t for t, m, _, _ in rows if m == "unavailable"), None)
        errs = [e for _, _, _, e in rows if e is not None]
        inside = sum(1 for _, _, s, e in rows if e is not None and e <= 2 * s) / max(1, len(errs))
        print(f"  -> first 'unavailable' at frame {first_off}; worst error while a position was given "
              f"{max(errs):.1f} m; error within 2 sigma on {100 * inside:.0f} % of them; "
              f"your gate agreed with NAVERA's on {agree} of {len(rows) - 4} steps")
        if not use and first_off:                          # the comparison asked in the lab (Step 10)
            k = first_off - 1
            track = vo.integrate(steps, truth[0])
            plain = math.hypot(track[k][0] - truth[k][0], track[k][1] - truth[k][1])
            print(f"  -> for comparison: your plain integrated odometry (vo.integrate) is {plain:.1f} m off "
                  f"at frame {k}, the last frame before 'unavailable'")
        out[name] = {"first_unavailable": first_off, "worst_error_m": round(max(errs), 2),
                     "inside_2sigma": round(inside, 3), "gate_agree": agree}
    try:
        with open("results.json") as f:
            res = json.load(f)
    except (OSError, ValueError):
        res = {}
    res["navigator"] = out
    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    print("\nresults.json updated (navigator)")


if __name__ == "__main__":
    try:
        main()
    except NotImplementedError as e:
        print(f"Not finished yet: {e} is still to do. Read the lab, fill it in, save, and run again.")
        raise SystemExit(1)
