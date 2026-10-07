import csv
import math
import os

import cv2
import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/22-locate-on-map"


def truth():
    with open(f"{DATA}/truth.csv") as f:
        return {r["file"].split("/")[-1][:-4]: r for r in csv.DictReader(f)}


ROWS = truth()
_results = {}


def hav(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def run_locate(name):
    """The student's locate() on one photo of the dataset (cached: each photo is located once)."""
    if name not in _results:
        (locate,) = need(load_student("locate.py"), "locate")
        r = ROWS[name]
        photo = cv2.imread(f"{DATA}/{r['file']}")
        res = locate(photo, float(r["prior_lat"]), float(r["prior_lon"]), float(r["altitude_m"]),
                     float(r["hfov_deg"]), float(r["search_m"]))
        if not isinstance(res, dict):
            c.ok(False, f"locate() returned {type(res).__name__}, not a dict")
        err = None
        if res.get("accepted"):
            c.ok(res.get("lat") is not None and res.get("lon") is not None,
                 f"{name}: accepted is True but lat / lon are None")
            err = hav(float(res["lat"]), float(res["lon"]), float(r["true_lat"]), float(r["true_lon"]))
        _results[name] = (res, err)
    return _results[name]


@c.test("photo_m_per_px() follows the camera model of lesson 17",
        hint="2 × altitude × tan(hfov / 2) is the footprint width; divide by the width in pixels. "
             "Did you convert the angle to radians before math.tan?")
def _():
    (f,) = need(load_student("locate.py"), "photo_m_per_px")
    c.near(f(640, 200, 75), 0.47958, tol=0.001, what="photo_m_per_px(640, 200, 75)")
    c.near(f(1000, 100, 90), 0.2, tol=0.0005, what="photo_m_per_px(1000, 100, 90)")


@c.test("build_search_patch() cuts the right piece of map, centred on the prior",
        hint="Half-width in pixels = (search_m + margin_m) / meters per pixel, rounded up; the patch is "
             "2 × half pixels wide. Return the three things: patch, origin, mpp.")
def _():
    m = load_student("locate.py")
    (f,) = need(m, "build_search_patch")
    out = f(35.8256, 10.6370, 300.0, 200.0)
    c.ok(isinstance(out, tuple) and len(out) == 3, "build_search_patch() should return (patch, (x0, y0), mpp)")
    patch, (x0, y0), mpp = out
    c.ok(isinstance(patch, np.ndarray) and patch.ndim == 3, "the patch should be a colour image (numpy array)")
    c.near(mpp, 0.9684, tol=0.002, what="meters per map pixel at zoom 17")
    c.near(patch.shape[1], 1034, tol=2, what="patch width (px) for 300 m + 200 m")
    c.near(patch.shape[0], 1034, tol=2, what="patch height (px)")
    # its centre is the prior
    n = 2 ** 17
    cx = (10.6370 + 180) / 360 * n * 256
    r = math.radians(35.8256)
    cy = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n * 256
    c.near(x0 + patch.shape[1] / 2, cx, tol=2, what="x of the patch centre (global px)")
    c.near(y0 + patch.shape[0] / 2, cy, tol=2, what="y of the patch centre (global px)")
    c.ok(patch.mean() > 40, "the patch is (almost) black: did you read the map at zoom z?")


@c.test("match_features() keeps only the matches that pass the ratio test",
        hint="knnMatch(d1, d2, k=2) gives 2 neighbours per photo keypoint. Keep p[0] only when "
             "p[0].distance < RATIO * p[1].distance. Without the test you would keep all 1500.")
def _():
    (match_features,) = need(load_student("locate.py"), "match_features")
    (map_patch,) = need(load_student("navmap.py"), "map_patch")
    r = ROWS["p01_medina"]
    grey = cv2.imread(f"{DATA}/{r['file']}", cv2.IMREAD_GRAYSCALE)
    s = 0.47958 / 0.9684                          # photo pixels -> map pixels (zoom 17)
    small = cv2.resize(grey, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    patch, _ = map_patch(float(r["prior_lat"]), float(r["prior_lon"]), 17, 1034, 1034)
    src, dst = match_features(small, cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY))
    src, dst = np.asarray(src), np.asarray(dst)
    c.ok(src.ndim == 2 and src.shape[1:] == (2,) and dst.shape == src.shape,
         f"src and dst should both have the shape (N, 2); got {src.shape} and {dst.shape}")
    c.ok(len(src) >= 100, f"only {len(src)} matches kept: is the comparison the right way round (<)?")
    c.ok(len(src) <= 1400, f"{len(src)} matches kept out of 1500 keypoints: the ratio test is missing")


@c.test("locate() finds photo p01 (old town of Sousse) within 5 m",
        hint="Check TODO 4 step d: the photo centre carried by A is in PATCH pixels; add (x0, y0) to get "
             "global pixels before navmap.pixel_to_latlon(..., Z).")
def _():
    res, err = run_locate("p01_medina")
    c.ok(res.get("accepted") is True, f"p01 was not accepted: {res.get('reason')}")
    c.ok(err < 5.0, f"p01 is located {err:.1f} m from the truth (it should be < 5 m)")


@c.test("locate() measures the photo's rotation and scale (p01: heading 30°, scale 1)",
        hint="scale = math.hypot(A[0,0], A[1,0]); rotation = math.degrees(math.atan2(A[1,0], A[0,0])). "
             "Store them in res as 'scale' and 'rotation_deg'.")
def _():
    res, _ = run_locate("p01_medina")
    c.near(res.get("scale"), 1.0, tol=0.05, what="res['scale']")
    c.near(res.get("rotation_deg"), 30.0, tol=3.0, what="res['rotation_deg']")
    c.ok(int(res.get("inliers") or 0) >= 50, f"res['inliers'] is {res.get('inliers')}: count the RANSAC inliers")


@c.test("over the open sea (p12) locate() answers 'no position'",
        hint="Nothing to match over water: return accepted=False with a reason, never a guess.")
def _():
    res, _ = run_locate("p12_sea")
    c.ok(res.get("accepted") is False, "p12 (open sea) was accepted: that position can only be a guess")
    c.ok(res.get("lat") is None, "a refused photo should have lat = None")


@c.test("with a prior 1.2 km off (p13) locate() answers 'no position', not a wrong one",
        hint="The true place is outside the searched map. The gates (minimum inliers, scale 1 ± 15 %) "
             "must refuse whatever RANSAC fits there.")
def _():
    res, err = run_locate("p13_lost")
    c.ok(res.get("accepted") is False,
         f"p13 was accepted {err:.0f} m from the truth — the gates should refuse it" if err is not None
         else "p13 was accepted")


@c.test("error_m() and median() are right",
        hint="median: sort, take the middle (or the mean of the two middle values); None for []. "
             "error_m: None when not accepted, else navmap.haversine_m to the truth.")
def _():
    m = load_student("evaluate.py")
    error_m, median = need(m, "error_m", "median")
    c.eq(median([3.0, 1.0, 2.0]), 2.0, "median([3, 1, 2])")
    c.near(median([4.0, 1.0, 3.0, 2.0]), 2.5, tol=1e-9, what="median([4, 1, 3, 2])")
    c.eq(median([]), None, "median([])")
    row = {"true_lat": "35.8256", "true_lon": "10.6370"}
    c.eq(error_m({"accepted": False, "lat": None, "lon": None}, row), None, "error_m of a refused photo")
    c.near(error_m({"accepted": True, "lat": 35.8265, "lon": 10.6370}, row), 100.08, tol=0.5,
           what="error_m for a point 0.0009° further north")


@c.test("on the 13 photos: at least 8 located, median error under 3 m, no wrong position accepted",
        hint="Run python3 evaluate.py and read the table. A photo accepted far from the truth means a gate "
             "is missing; many 'no fix' on land usually means a scale or ratio problem.")
def _():
    errs, wrong = [], []
    for name in ROWS:
        _, err = run_locate(name)
        if err is not None:
            errs.append(err)
            if err > 50:
                wrong.append(f"{name} ({err:.0f} m)")
    c.ok(not wrong, "wrong positions accepted: " + ", ".join(wrong))
    c.ok(len(errs) >= 8, f"only {len(errs)} of 13 photos located (at least 8 expected)")
    errs.sort()
    n = len(errs)
    med = errs[n // 2] if n % 2 else 0.5 * (errs[n // 2 - 1] + errs[n // 2])
    c.ok(med < 3.0, f"median error {med:.1f} m (should be under 3 m)")


@c.test("you ran evaluate.py: results.csv (13 photos) and errors.png exist",
        hint="Run python3 evaluate.py in the terminal, after your code works.")
def _():
    c.file_exists("results.csv")
    c.file_exists("errors.png")
    with open("results.csv") as f:
        rows = list(csv.DictReader(f))
    c.eq(len(rows), 13, "the number of rows in results.csv")
    acc = [r for r in rows if r.get("accepted") == "True"]
    c.ok(len(acc) >= 8, f"results.csv has only {len(acc)} accepted photos: run evaluate.py again after "
                        "your last change")


c.run()
