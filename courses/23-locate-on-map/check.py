import csv
import json
import math
import os
import re

import cv2
import numpy as np

from academy_check import Checker, load_student, need

c = Checker()
DATA = "/data/academy/23-locate-on-map"


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


def ref_percentile(v, q):
    return None if not v else float(np.percentile(v, q))


def load_json(name):
    c.file_exists(name)
    try:
        with open(name) as f:
            return json.load(f)
    except ValueError as e:
        c.ok(False, f"{name} is not valid JSON ({e}): run the program again")


# ---------------------------------------------------------------- locate.py
@c.test("TODO 1 — photo_m_per_px() follows the pinhole footprint of lesson 18",
        hint="Footprint width = 2 × altitude × tan(hfov / 2), divided by the width in pixels. "
             "Did you convert the angle to radians before math.tan?")
def _():
    (f,) = need(load_student("locate.py"), "photo_m_per_px")
    c.near(f(640, 200, 75), 0.47958, tol=0.001, what="photo_m_per_px(640, 200, 75)")
    c.near(f(1000, 100, 90), 0.2, tol=0.0005, what="photo_m_per_px(1000, 100, 90)")


@c.test("TODO 2 — build_search_patch() cuts the right piece of map, centred on the prior",
        hint="Half-width in pixels = (search_m + margin_m) / metres per pixel, rounded up; the patch is "
             "2 × half pixels wide. Return the three things: patch, origin, mpp.")
def _():
    (f,) = need(load_student("locate.py"), "build_search_patch")
    out = f(35.8256, 10.6370, 300.0, 200.0)
    c.ok(isinstance(out, tuple) and len(out) == 3, "build_search_patch() should return (patch, (x0, y0), mpp)")
    patch, (x0, y0), mpp = out
    c.ok(isinstance(patch, np.ndarray) and patch.ndim == 3, "the patch should be a colour image (numpy array)")
    c.near(mpp, 0.9684, tol=0.002, what="metres per map pixel at zoom 17")
    c.near(patch.shape[1], 1034, tol=2, what="patch width (px) for 300 m + 200 m")
    c.near(patch.shape[0], 1034, tol=2, what="patch height (px)")
    n = 2 ** 17
    cx = (10.6370 + 180) / 360 * n * 256
    r = math.radians(35.8256)
    cy = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n * 256
    c.near(x0 + patch.shape[1] / 2, cx, tol=2, what="x of the patch centre (global px)")
    c.near(y0 + patch.shape[0] / 2, cy, tol=2, what="y of the patch centre (global px)")
    c.ok(patch.mean() > 40, "the patch is (almost) black: did you read the map at zoom z?")


@c.test("TODO 3 — match_features() keeps only the matches that pass the ratio test",
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


@c.test("TODO 4 — locate() finds photo p01 (old town of Sousse) within 5 m",
        hint="The photo centre carried by A is in PATCH pixels; add (x0, y0) to get global pixels "
             "before navmap.pixel_to_latlon(..., Z).")
def _():
    res, err = run_locate("p01_medina")
    c.ok(res.get("accepted") is True, f"p01 was not accepted: {res.get('reason')}")
    c.ok(err < 5.0, f"p01 is located {err:.1f} m from the truth (it should be < 5 m)")


@c.test("TODO 4 — locate() reports the fitted rotation and scale (p01: heading 30°, scale 1)",
        hint="A = [[s cos θ, −s sin θ, tx], [s sin θ, s cos θ, ty]]: read s and θ from the first column. "
             "Store them in res as 'scale' and 'rotation_deg', and the inlier count as 'inliers'.")
def _():
    res, _ = run_locate("p01_medina")
    c.near(res.get("scale"), 1.0, tol=0.05, what="res['scale']")
    c.near(res.get("rotation_deg"), 30.0, tol=3.0, what="res['rotation_deg']")
    c.ok(int(res.get("inliers") or 0) >= 50, f"res['inliers'] is {res.get('inliers')}: count the RANSAC inliers")


@c.test("TODO 4 — the gates answer 'no fix' over the sea (p12) and with a prior 1.2 km off (p13)",
        hint="RANSAC always returns something. Gate 1 (at least MIN_INLIERS inliers) and gate 2 "
             "(|scale − 1| ≤ SCALE_TOL) must refuse it, with lat = None and a reason.")
def _():
    res, _ = run_locate("p12_sea")
    c.ok(res.get("accepted") is False, "p12 (open sea) was accepted: that position can only be a guess")
    c.ok(res.get("lat") is None, "a refused photo should have lat = None")
    res, err = run_locate("p13_lost")
    c.ok(res.get("accepted") is False,
         f"p13 was accepted {err:.0f} m from the truth — the gates should refuse it" if err is not None
         else "p13 was accepted")
    c.ok(bool(res.get("reason")), "a refused photo needs a reason (res['reason'])")


# ---------------------------------------------------------------- budget.py
@c.test("TODOs 5–6 — expected_scale() and tilt_offset_m()",
        hint="The ground size of a pixel is proportional to the height, so the fitted scale is the ratio "
             "of the two heights (which one on top?). The tilt offset is the opposite side of a right "
             "triangle whose adjacent side is the height.")
def _():
    m = load_student("budget.py")
    es, to = need(m, "expected_scale", "tilt_offset_m")
    c.near(es(200.0, 160.0), 1.25, tol=1e-6, what="expected_scale(h_true=200, h_assumed=160)")
    c.near(es(200.0, 250.0), 0.8, tol=1e-6, what="expected_scale(200, 250)")
    c.near(to(200.0, 5.0), 17.4977, tol=0.01, what="tilt_offset_m(200, 5)")
    c.near(to(1000.0, 1.0), 17.455, tol=0.01, what="tilt_offset_m(1000, 1)")


@c.test("TODO 7 — tilt_homography() is K·R·K⁻¹",
        hint="f = (width / 2) / tan(hfov / 2) in pixels; K = [[f, 0, w/2], [0, f, h/2], [0, 0, 1]]; "
             "R turns about the x axis. With tilt 0 you must get the identity.")
def _():
    (th,) = need(load_student("budget.py"), "tilt_homography")
    H0 = np.asarray(th(640, 480, 75.0, 0.0), float)
    c.ok(H0.shape == (3, 3), f"the result should be a 3 x 3 matrix, got shape {H0.shape}")
    c.ok(np.allclose(H0 / H0[2, 2], np.eye(3), atol=1e-9), "tilt_homography(..., 0) should be the identity")
    H = np.asarray(th(640, 480, 75.0, 10.0), float)
    f = 320.0 / math.tan(math.radians(37.5))
    p = H @ np.array([320.0, 240.0, 1.0])
    p = p / p[2]
    c.near(abs(p[1] - 240.0), f * math.tan(math.radians(10.0)), tol=0.5,
           what="vertical shift of the image centre for a 10° tilt (px)")
    c.near(p[0], 320.0, tol=0.01, what="x of the image centre after a pitch (px)")


@c.test("TODO 8 — rss() and error_budget()",
        hint="rss = square root of the sum of the squares. error_budget returns the four terms in metres "
             "(tilt, matcher pixels × map metres per pixel, speed × lag, map) and total_m = their rss.")
def _():
    m = load_student("budget.py")
    rss, eb = need(m, "rss", "error_budget")
    c.near(rss([3.0, 4.0]), 5.0, tol=1e-9, what="rss([3, 4])")
    c.near(rss([1.0, 2.0, 2.0]), 3.0, tol=1e-9, what="rss([1, 2, 2])")
    b = eb(300.0, 0.3, 8.0, 1.1, 20.0, 0.1, 5.0)
    c.ok(isinstance(b, dict), f"error_budget() should return a dict, got {type(b).__name__}")
    for k, want in (("tilt_m", 1.5708), ("matcher_m", 8.8), ("lag_m", 2.0), ("map_m", 5.0), ("total_m", 10.4366)):
        c.ok(k in b, f"error_budget() has no key '{k}'")
        c.near(b[k], want, tol=0.01, what=f"error_budget(...)['{k}']")


# ---------------------------------------------------------------- evaluate.py
@c.test("TODOs 9–11 — error_m(), percentile() and summarise()",
        hint="percentile: position (n − 1) × q / 100 in the sorted list, linear interpolation between the two "
             "neighbours (numpy's default). summarise: only the accepted errors (not None) count for median, "
             "p90 and worst; availability = accepted / n.")
def _():
    m = load_student("evaluate.py")
    error_m, pct, summ = need(m, "error_m", "percentile", "summarise")
    row = {"true_lat": "35.8256", "true_lon": "10.6370"}
    c.eq(error_m({"accepted": False, "lat": None, "lon": None}, "lat", "lon", row), None, "error_m of a refused photo")
    c.near(error_m({"accepted": True, "la": 35.8265, "lo": 10.6370}, "la", "lo", row), 100.08, tol=0.5,
           what="error_m for a point 0.0009° further north (keys 'la', 'lo')")
    for vals, q in (([3.0, 1.0, 2.0], 50), ([4.0, 1.0, 3.0, 2.0], 50), ([1.0, 2.0, 3.0, 4.0], 90),
                    ([5.0, 0.2, 7.5, 1.1, 0.4, 30.0], 90), ([2.0], 90)):
        c.near(pct(vals, q), ref_percentile(vals, q), tol=1e-9, what=f"percentile({vals}, {q})")
    c.eq(pct([], 50), None, "percentile([], 50)")
    s = summ([0.5, None, 2.0, 120.0, None, 1.0])
    c.ok(isinstance(s, dict), "summarise() should return a dict")
    for k, want in (("n", 6), ("accepted", 4), ("availability", 4 / 6), ("median_m", 1.5),
                    ("p90_m", ref_percentile([0.5, 2.0, 120.0, 1.0], 90)), ("worst_m", 120.0), ("wrong_accepted", 1)):
        c.ok(k in s, f"summarise() has no key '{k}'")
        c.near(s[k], want, tol=1e-6, what=f"summarise(...)['{k}']")
    s0 = summ([None, None])
    c.ok(s0.get("accepted") == 0 and s0.get("median_m") is None, f"summarise([None, None]) gave {s0}")


@c.test("your pipeline on the 13 photos: at least 8 located, median under 3 m, no wrong position",
        hint="Run python3 evaluate.py and read the table. A photo accepted far from the truth means a gate "
             "is missing; many 'no fix' on land usually means a scale or ratio-test problem.")
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
    c.ok(float(np.median(errs)) < 3.0, f"median error {float(np.median(errs)):.1f} m (should be under 3 m)")


# ---------------------------------------------------------------- outputs
@c.test("budget.json — the two experiments were run (wrong height, tilted camera)",
        hint="Run python3 budget.py after TODOs 1–8. The fitted scale should follow h_true / h_assumed, "
             "and the tilt error should follow h·tan(tilt).")
def _():
    b = load_json("budget.json")
    hs, ts = b.get("height_sweep") or [], b.get("tilt_sweep") or []
    c.ok(len(hs) >= 5 and len(ts) >= 3, "budget.json is incomplete: run python3 budget.py again")
    one = [h for h in hs if abs(h["factor"] - 1.0) < 1e-9]
    c.ok(one and one[0]["accepted"], "with the right height (factor 1.0) the photo should be accepted")
    for h in hs:
        if h.get("fitted_scale") is not None:
            c.near(h["fitted_scale"], 1.0 / h["factor"], tol=0.05,
                   what=f"fitted scale with the height x{h['factor']}")
        if abs(h["factor"] - 1.0) >= 0.25:
            c.ok(not h["accepted"], f"height x{h['factor']} was accepted: the scale gate (±15 %) should refuse it")
    five = [t for t in ts if abs(t["tilt_deg"] - 5.0) < 1e-6]
    c.ok(five and five[0]["error_m"] is not None, "no accepted result for the 5° tilt in budget.json")
    c.near(five[0]["error_m"], 200 * math.tan(math.radians(5)), tol=5.0, what="error with a 5° tilt (m)")


@c.test("results.json / results.csv / errors.png — both pipelines measured on the 13 photos",
        hint="Run python3 evaluate.py after TODOs 1–11 (about a minute and a half: it runs your pipeline AND "
             "NAVERA's LocalMatcher). Run it again after your last change.")
def _():
    d = load_json("results.json")
    c.file_exists("errors.png")
    c.file_exists("results.csv")
    per = d.get("per_photo") or []
    c.eq(len(per), 13, "the number of photos in results.json")
    s = d.get("student") or {}
    errs = [p["error_m"] for p in per]
    acc = [e for e in errs if e is not None]
    c.eq(s.get("accepted"), len(acc), "student.accepted (compared with per_photo)")
    c.ok(len(acc) >= 8, f"results.json has only {len(acc)} accepted photos: run evaluate.py again")
    c.near(s.get("median_m"), float(np.median(acc)), tol=0.02, what="student.median_m (compared with per_photo)")
    c.near(s.get("p90_m"), float(np.percentile(acc, 90)), tol=0.02, what="student.p90_m (compared with per_photo)")
    n = d.get("navera")
    c.ok(isinstance(n, dict), "results.json has no 'navera' summary: did NAVERA's LocalMatcher load? "
                              "Read the first line printed by evaluate.py.")
    c.eq(n.get("n"), 13, "navera.n")
    c.eq(n.get("wrong_accepted"), 0, "navera.wrong_accepted")


@c.test("report.md — four sections written, no TODO left",
        hint="Keep the four '## ' headings of the template, replace every TODO line by your own sentences "
             "(at least about 300 words in total).")
def _():
    c.file_exists("report.md")
    t = open("report.md", encoding="utf-8").read()
    for h in ("## 1. Results", "## 2. Error budget", "## 3. My pipeline vs NAVERA's LocalMatcher",
              "## 4. What these numbers do not tell"):
        c.ok(h in t, f"the heading '{h}' is missing")
    c.ok("TODO" not in t, "report.md still contains 'TODO'")
    words = len(re.findall(r"[A-Za-z]{2,}", t))
    c.ok(words >= 300, f"report.md has about {words} words; write at least about 300")


@c.test("report.md — quotes your measured numbers",
        hint="Section 1: your 'a/13'. Section 3: NAVERA's 'b/13'. Section 2: the 5° tilt error (m) and the "
             "worked-case total (Bangkok, m), as budget.json gives them (one decimal is fine).")
def _():
    t = open("report.md", encoding="utf-8").read() if os.path.exists("report.md") else ""
    d = load_json("results.json")
    b = load_json("budget.json")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    a1 = (d.get("student") or {}).get("accepted")
    a2 = (d.get("navera") or {}).get("accepted")
    c.ok(f"{a1}/13" in t.replace(" / ", "/"), f"report.md does not quote your result as '{a1}/13'")
    c.ok(f"{a2}/13" in t.replace(" / ", "/"), f"report.md does not quote NAVERA's result as '{a2}/13'")
    tot = (b.get("worked_case") or {}).get("total_m")
    c.ok(tot is not None and any(abs(x - tot) <= 0.15 for x in nums),
         f"report.md does not quote the worked-case total ({tot} m)")
    five = [x for x in b.get("tilt_sweep", []) if abs(x["tilt_deg"] - 5.0) < 1e-6 and x["error_m"] is not None]
    c.ok(five and any(abs(x - five[0]["error_m"]) <= 0.15 for x in nums),
         "report.md does not quote your measured error for the 5° tilt")


c.run()
