# Lesson 22 — the error budget: what a wrong height and a tilted camera do to the position.
# Run:  python3 budget.py      → two experiments with YOUR locate(), then budget.json
import json
import math

import cv2
import numpy as np

import navmap


def expected_scale(h_true, h_assumed):
    """The scale RANSAC will fit when the photo was pre-scaled with h_assumed but taken from h_true."""
    # TODO 5: the ground size of a photo pixel is proportional to the height (lesson 17)
    raise NotImplementedError("TODO 5 (expected_scale)")


def tilt_offset_m(height_m, tilt_deg):
    """Ground distance between the point under the camera and the point at the photo centre,
    for a camera tilted tilt_deg away from straight down (and treated as if it were straight down)."""
    # TODO 6: right triangle: height h, angle tilt at the camera -> opposite side
    raise NotImplementedError("TODO 6 (tilt_offset_m)")


def tilt_homography(width, height, hfov_deg, tilt_deg):
    """3 x 3 matrix H = K R K^-1 that turns a straight-down photo into the photo the same camera
    takes when it is pitched by tilt_deg (rotation about the image x axis, around the lens)."""
    # TODO 7: K from the focal length in pixels f = (width / 2) / tan(hfov / 2), centre (w/2, h/2);
    #         R = rotation about the x axis by tilt_deg:  [[1, 0, 0], [0, cos a, -sin a], [0, sin a, cos a]]
    #         return K @ R @ np.linalg.inv(K)
    raise NotImplementedError("TODO 7 (tilt_homography)")


def rss(terms):
    """Root sum of squares of independent 1-sigma error terms (metres)."""
    # TODO 8a: sqrt(t1^2 + t2^2 + ...)
    raise NotImplementedError("TODO 8a (rss)")


def error_budget(height_m, tilt_sigma_deg, matcher_px, map_mpp, speed_mps, lag_s, map_bias_m):
    """1-sigma error terms of one day-vision fix, in metres, and their total.
    Returns {"tilt_m", "matcher_m", "lag_m", "map_m", "total_m"}."""
    # TODO 8b: tilt -> tilt_offset_m; matcher -> pixels x metres per map pixel;
    #          lag -> speed x lag; map -> map_bias_m; total -> rss of the four
    raise NotImplementedError("TODO 8b (error_budget)")


# ---- you don't need to change anything below this line ----
# A worked case for the report: a survey drone 300 m above the rice fields near Bangkok.
# (The map and the photos of this lab are of Sousse; this case only uses the formulas.)
WORKED_CASE = dict(height_m=300.0, tilt_sigma_deg=0.3, matcher_px=8.0, map_mpp=navmap.m_per_px(13.75, 17),
             speed_mps=20.0, lag_s=0.1, map_bias_m=5.0)


def _photo(name):
    from locate import DATA, read_truth
    row = [r for r in read_truth() if name in r["file"]][0]
    return cv2.imread(f"{DATA}/{row['file']}"), row


def height_sweep(name="p01_medina", factors=(0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3)):
    """locate() with a WRONG height: assumed = factor x true."""
    from locate import locate
    photo, row = _photo(name)
    h = float(row["altitude_m"])
    out = []
    for k in factors:
        r = locate(photo, float(row["prior_lat"]), float(row["prior_lon"]), h * k, float(row["hfov_deg"]),
                   float(row["search_m"]))
        err = None
        if r.get("accepted"):
            err = navmap.haversine_m(r["lat"], r["lon"], float(row["true_lat"]), float(row["true_lon"]))
        out.append(dict(factor=k, assumed_m=round(h * k, 1), accepted=bool(r.get("accepted")),
                        fitted_scale=r.get("scale"), expected_scale=round(expected_scale(h, h * k), 3),
                        error_m=None if err is None else round(err, 2), reason=r.get("reason", "")))
        print(f"  height assumed {h * k:5.0f} m (x{k:.1f}): fitted scale {r.get('scale')}, expected "
              f"{expected_scale(h, h * k):.3f} -> {'ACCEPTED' if r.get('accepted') else 'no fix'}"
              f"{'' if err is None else f', error {err:.1f} m'}")
    return out


def tilt_sweep(name="p01_medina", tilts=(0.0, 2.0, 5.0, 10.0)):
    """locate() on the photo re-rendered as if the camera were pitched by `tilt` degrees,
    while the code still believes it looks straight down."""
    from locate import locate
    photo, row = _photo(name)
    h, hfov = float(row["altitude_m"]), float(row["hfov_deg"])
    out = []
    for t in tilts:
        H = tilt_homography(photo.shape[1], photo.shape[0], hfov, t)
        tilted = cv2.warpPerspective(photo, H, (photo.shape[1], photo.shape[0]))
        if t == tilts[-1]:
            cv2.imwrite("tilted_photo.png", tilted)
        r = locate(tilted, float(row["prior_lat"]), float(row["prior_lon"]), h, hfov, float(row["search_m"]))
        err = None
        if r.get("accepted"):
            err = navmap.haversine_m(r["lat"], r["lon"], float(row["true_lat"]), float(row["true_lon"]))
        pred = tilt_offset_m(h, t)
        out.append(dict(tilt_deg=t, accepted=bool(r.get("accepted")), error_m=None if err is None else round(err, 2),
                        predicted_m=round(pred, 2)))
        print(f"  tilt {t:4.1f} deg: {'error %.1f m' % err if err is not None else 'no fix'}, "
              f"predicted h·tan(tilt) = {pred:.1f} m")
    return out


if __name__ == "__main__":
    try:
        print("Error budget, worked case (Bangkok):", {k: round(v, 2) for k, v in error_budget(**WORKED_CASE).items()})
        print("\n1) Wrong height (photo p01, true height 200 m):")
        hs = height_sweep()
        print("\n2) Tilted camera treated as straight down (photo p01, 200 m):")
        ts = tilt_sweep()
        with open("budget.json", "w") as f:
            json.dump(dict(height_sweep=hs, tilt_sweep=ts,
                           worked_case=dict(WORKED_CASE, **{k: round(v, 3) for k, v in error_budget(**WORKED_CASE).items()})),
                      f, indent=1)
        print("\nwritten: budget.json and tilted_photo.png (the 10 deg photo)")
    except NotImplementedError as e:
        print(f"Not written yet: {e} — fill in that TODO (in budget.py or locate.py) and run again.")
