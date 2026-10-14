"""run_match.py — runs YOUR functions of navera_lite/match.py and navera_lite/learned_match.py on the lab's map
patches and drone photos, measures them against the truth, and draws them.

  Session 1 — Geometer
    python3 run_match.py test            check each function on its docstring example
    python3 run_match.py look            copy the maps and the session-1 photos into look/              (Step 0)
    python3 run_match.py ratio [PAIR]    SIFT pairs before and after YOUR ratio test (default: city)     (Step 1)
    python3 run_match.py fit             YOUR similarity and homography on the true pairs, vs OpenCV      (Steps 2–3)
    python3 run_match.py iters           YOUR ransac_iterations for a few inlier shares                    (Step 4)
    python3 run_match.py ransac [PAIR]   YOUR RANSAC vs OpenCV's on a pair (default: city_tilt)          (Step 5)
    python3 run_match.py gates           the eight pairs through ratio test → RANSAC → YOUR gates         (Step 6)
  Session 2 — Learned matcher
    python3 run_match.py learned [PAIR]  YOUR learned_pairs vs SIFT on a pair (default: olives_shaken)   (Step 8)
    python3 run_match.py curve           the threshold table of SIFT and of your network (YOUR ratio_curve)(Step 9)
    python3 run_match.py envelope        where your network works: prior heading, prior zoom, blur        (Step 10)
    python3 run_match.py mission         YOUR match_photo on ten scenarios, with your decisions          (Step 11)

PAIR is a name of pairs.json: city, city_tilt, olives, olives_shaken, harbour, sea, wrong_place, hills.
Your network: my_desc.pt in this folder (lab Step 7 copies it). Pictures are saved in out/ — click them in the
file list of the 📝 Code tab. Map pictures: data © OpenStreetMap contributors.
"""
import json
import math
import os
import shutil
import sys
import time

import cv2
import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = "/data/academy/22-matching"
OUT = "out"
RIGHT_PX = 6.0           # a pair is RIGHT when the truth puts its map point within 6 photo pixels of its photo point
RIGHT_M = 10.0           # an accepted match is RIGHT when it puts the photo's centre within 10 m of the truth
_kit_hint = rk._hint


def _hint(e):
    s = str(e)
    if "SVD did not converge" in s:
        return " — the matrix A has NaN or inf values: check the normalised points"
    if "Cannot take a larger sample than population" in s:
        return " — rng.choice(n, s, replace=False) needs n ≥ s: return (None, all False) when there are too few pairs"
    if "not enough values to unpack" in s and "fit" in s:
        return " — fit_similarity returns four numbers (s, theta_deg, tx, ty)"
    if "mat1 and mat2" in s or "Expected 4D" in s:
        return " — describe() wants uint8 patches (N, 48, 48): use patches_at(gray, pts)"
    return _kit_hint(e)


rk._hint = _hint
match = rk.load_student("navera_lite.match")


def lm():
    return rk.load_student("navera_lite.learned_match")


# ================================================================================================= data helpers
def load_json(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"cannot read {path} — is the data folder mounted? (ls {DATA})")
    with open(path) as fh:
        return json.load(fh)


def gray(rel):
    img = cv2.imread(os.path.join(DATA, rel), cv2.IMREAD_GRAYSCALE)
    if img is None:
        sys.exit(f"cannot read {DATA}/{rel} — is the data folder mounted? (ls {DATA})")
    return img


def pair(name, table="pairs.json"):
    rows = {p["name"]: p for p in load_json(table)}
    if name not in rows:
        sys.exit(f"unknown pair {name!r}: choose one of {', '.join(rows)}")
    p = rows[name]
    H = None if p["H"] is None else np.array(p["H"], dtype=np.float64)
    return p, gray(p["map"]), gray(p["photo"]), H


def warp(H, pts):
    p = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    q = np.column_stack([p, np.ones(len(p))]) @ np.asarray(H, dtype=np.float64).T
    return q[:, :2] / q[:, 2:3]


def right_mask(H, src, dst):
    if H is None or len(src) == 0:
        return np.zeros(len(src), dtype=bool)
    return np.hypot(*(warp(H, src) - np.asarray(dst, dtype=np.float64)).T) <= RIGHT_PX


def centre_error_m(M, H, mpp):
    """Distance on the ground (m) between where M and the truth H put the photo's centre on the map."""
    c = np.array([[319.5, 239.5]])
    return float(np.hypot(*(warp(np.linalg.inv(M), c) - warp(np.linalg.inv(H), c))[0]) * mpp)


def stamp(img):
    """(c) OpenStreetMap contributors in the corner of a saved map picture (the licence asks for it)."""
    text = "(c) OpenStreetMap contributors"
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
    H, W = img.shape[:2]
    cv2.rectangle(img, (W - w - 9, H - h - 9), (W - 1, H - 1), (255, 255, 255), -1)
    cv2.putText(img, text, (W - w - 6, H - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
    return img


def draw_pairs(map_g, photo_g, src, dst, good, path, title=""):
    """Map on the left, photo on the right, one line per pair: green = right, red = wrong (from the truth)."""
    hm, wm = map_g.shape
    hp, wp = photo_g.shape
    canvas = np.full((max(hm, hp) + 24, wm + wp + 10, 3), 255, np.uint8)
    canvas[24:24 + hm, :wm] = cv2.cvtColor(map_g, cv2.COLOR_GRAY2BGR)
    canvas[24:24 + hp, wm + 10:] = cv2.cvtColor(photo_g, cv2.COLOR_GRAY2BGR)
    for (x1, y1), (x2, y2), g in zip(src, dst, good):
        col = (40, 170, 40) if g else (30, 30, 220)
        cv2.line(canvas, (int(x1), int(y1) + 24), (int(x2) + wm + 10, int(y2) + 24), col, 1, cv2.LINE_AA)
    title = title.replace("—", "-").replace("–", "-")             # cv2.putText draws ASCII only
    cv2.putText(canvas, title, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(path, stamp(canvas))
    rk.saved(path)


def sift_candidates(map_g, photo_g):
    """SIFT keypoints of both pictures, every distance, and each map point's two nearest photo points."""
    feat = rk.load_student("navera_lite.features")
    p1, d1 = feat.detect(map_g, "sift", 1500)
    p2, d2 = feat.detect(photo_g, "sift", 1500)
    if d1 is None or d2 is None:
        return p1, p2, np.zeros((len(p1), len(p2)))
    return p1, p2, match.distance_matrix(d1, d2)


def two_nearest(dist):
    o = np.argsort(dist, axis=1, kind="stable")[:, :2]
    r = np.arange(len(dist))
    return o[:, 0], dist[r, o[:, 0]], dist[r, o[:, 1]]


def session1_ready(why="session 2 uses your session-1 functions (ratio test, RANSAC, gates)"):
    """Stop with one sentence if a session-1 function this command needs is still a TODO."""
    for fn in ("ratio_test", "fit_similarity", "ransac", "gates"):
        f = getattr(match, fn, None)
        if f is None or rk.is_stub(f):
            sys.exit(f"{fn}() in navera_lite/match.py is still a TODO: {why}. Write it first "
                     "(python3 run_match.py test).")


def model():
    """YOUR network from mission 21 (my_desc.pt in this folder), loaded safely."""
    try:
        from academy_gpu import limit_threads
        limit_threads()
    except ImportError:
        pass
    session1_ready()
    if not os.path.exists("my_desc.pt"):
        sys.exit("my_desc.pt is missing in this folder: lab Step 7 copies your network from mission 21:\n"
                 "    cp ../21-features/my_desc.pt .\n"
                 "(no network of your own? use the course's: cp ref_desc.pt my_desc.pt)")
    ld = rk.load_student("navera_lite.learned_desc")
    try:
        return ld.load_weights("my_desc.pt")
    except Exception as e:                                                   # noqa: BLE001
        sys.exit(f"my_desc.pt cannot be loaded as PatchNet weights ({type(e).__name__}: {str(e)[:120]}). "
                 "Copy it again from ../21-features (or: cp ref_desc.pt my_desc.pt).")


def decisions(need_limit=True):
    """Your session-2 decisions, read from answers.py: (cfg, None) or (None, why)."""
    a = rk.load_student("answers")
    cfg = {"learned_ratio": getattr(a, "LEARNED_RATIO", None), "learned_max_dist": getattr(a, "LEARNED_MAX_DIST", None),
           "heading_limit_deg": getattr(a, "HEADING_LIMIT_DEG", None)}
    steps = {"learned_ratio": "Step 9", "heading_limit_deg": "Step 10"}
    for k in ("learned_ratio", "heading_limit_deg") if need_limit else ("learned_ratio",):
        v = cfg[k]
        if v is None:
            return None, f"{k.upper()} in answers.py is still None: decide it first (lab {steps[k]})"
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            return None, f"{k.upper()} in answers.py must be a number > 0 (got {v!r})"
    md = cfg["learned_max_dist"]
    if md is not None and (isinstance(md, bool) or not isinstance(md, (int, float)) or md <= 0):
        return None, f"LEARNED_MAX_DIST in answers.py must be None or a number > 0 (got {md!r})"
    return cfg, None


def fmt(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


# ================================================================================================= test
def test():
    print("TODO  function             result")
    ok_all = True

    def line(todo, name, got, err, good, note):
        nonlocal ok_all
        if err:
            print(f"✘ {todo:<4} {name:20s} {err}")
            ok_all = False
        elif good:
            print(f"✔ {todo:<4} {name:20s} {got}")
        else:
            print(f"✘ {todo:<4} {name:20s} got {got} — {note}")
            ok_all = False

    D = np.array([[1.0, 5.0, 9.0], [4.0, 3.0, 3.5], [2.0, 8.0, 2.4]])
    v, e = rk.call(match, "ratio_test", D, 0.8)
    g = None if e else np.asarray(v).reshape(-1, 2).tolist() if np.size(v) else np.asarray(v).tolist()
    note = "the docstring says [[0, 0]]. "
    if not e and g == [[0, 0], [2, 0]]:
        note += "Row 2 kept: the test is strictly < ratio × the SECOND-nearest (2.4), not × the farthest"
    elif not e and g == [[0, 0], [1, 1], [2, 0]]:
        note += "Every row kept: compare best < ratio × second (lab Step 1, hint 2)"
    elif not e and g == [[0, 0], [2, 2]]:
        note += "(2, 2)? j must be the column of the NEAREST distance (argmin), not the second one"
    line(1, "ratio_test", g, e, not e and g == [[0, 0]], note + " Lab Step 1 hints")
    v, e = rk.call(match, "fit_similarity", [[0, 0], [10, 0]], [[5, 5], [5, 25]])
    want = [2.0, 90.0, 5.0, 5.0]
    good = not e and np.size(v) == 4 and np.allclose(np.asarray(v, float), want, atol=1e-6)
    note = "the docstring says (2.0, 90.0, 5.0, 5.0). "
    if not e and np.size(v) == 4 and np.allclose(np.asarray(v, float), [2.0, -90.0, 5.0, 5.0], atol=1e-6):
        note += "θ has the wrong sign: the second equation is y2 = s·(sin θ·x1 + cos θ·y1) + ty (lab Step 2, hint 2)"
    elif not e and np.size(v) == 4 and abs(float(np.asarray(v, float)[1]) - math.pi / 2) < 1e-6:
        note += "θ in radians: return degrees (math.degrees)"
    line(2, "fit_similarity", None if e else tuple(round(float(x), 4) for x in np.ravel(v)), e, good, note)
    v, e = rk.call(match, "dlt_homography", [[0, 0], [1, 0], [1, 1], [0, 1]], [[1, 2], [3, 2], [3, 4], [1, 4]])
    want = np.array([[2, 0, 1], [0, 2, 2], [0, 0, 1.0]])
    good = not e and np.shape(v) == (3, 3) and np.allclose(np.asarray(v, float), want, atol=1e-6)
    note = "the docstring says [[2, 0, 1], [0, 2, 2], [0, 0, 1]]. "
    if not e and np.shape(v) == (3, 3) and abs(float(np.asarray(v)[2, 2]) - 1.0) > 1e-6:
        note += "Scale H so that H[2, 2] = 1 (divide by it)"
    elif not e and np.shape(v) == (3, 3) and np.allclose(np.asarray(v, float), want.T, atol=1e-6):
        note += "H is transposed: h is read row by row (vt[-1].reshape(3, 3))"
    else:
        note += "Lab Step 3 hints"
    line(3, "dlt_homography", None if e else np.round(np.asarray(v, float), 4).tolist(), e, good, note)
    for args, want in (((0.99, 0.5, 2), 17), ((0.99, 1.0, 4), 1), ((0.99, 0.3, 4), 567)):
        v, e = rk.call(match, "ransac_iterations", *args)
        note = f"the expected value is {want}. "
        if not e and isinstance(v, float):
            note += "Return a whole number: int(math.ceil(...))"
        elif not e and v == want - 1:
            note += "Round UP (math.ceil), not down"
        line(4, f"ransac_iterations{args}", v, e,
             not e and v == want and isinstance(v, (int, np.integer)) and not isinstance(v, bool), note)
    src = np.array([[0, 0], [10, 0], [0, 10], [10, 10], [5, 5], [3, 7], [8, 2], [6, 9], [1, 1], [9, 4]], float)
    dst = 2 * src
    dst[8], dst[9] = [50, 0], [0, 50]
    v, e = rk.call(match, "ransac", src, dst, "similarity", 1.0, 20, np.random.default_rng(1))
    if not e and not (isinstance(v, tuple) and len(v) == 2):
        e = f"ransac() must return two things (M, inliers), got {type(v).__name__}"
    if not e:
        M, inl = v
        inl = np.asarray(inl)
        good = (M is not None and np.allclose(np.asarray(M, float), np.diag([2.0, 2.0, 1.0]), atol=1e-6)
                and inl.dtype == bool and inl.tolist() == [True] * 8 + [False, False])
        note = "the docstring says M ≈ diag(2, 2, 1) and 8 inliers then 2 outliers. "
        if M is not None and inl.dtype != bool:
            note += f"inliers must be a bool array, got {inl.dtype}"
        elif M is None:
            note += "M is None: does any sample give a model? (rng.choice(len(src), 2, replace=False))"
        line(5, "ransac", f"M = {np.round(np.asarray(M, float), 3).tolist() if M is not None else None}, "
             f"inliers = {inl.astype(int).tolist()}", None, good, note)
    else:
        line(5, "ransac", None, e, False, "")
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.uniform(0, 640, 40), rng.uniform(0, 480, 40)])
    cases = (((1.62, -35.0, 10.0, 4.0), pts, 1.6, (True, "ok")), ((1.62, -35.0, 10.0, 4.0), pts, 2.0, (False, "scale off")),
             (None, pts, 1.6, (False, "no fit")), ((1.6, 0.0, 0.0, 0.0), pts[:5], 1.6, (False, "too few inliers")),
             ((1.6, 0.0, 0.0, 0.0), np.full((20, 2), 100.0), 1.6, (False, "inliers bunched")))
    for fit, p, sc, want in cases:
        v, e = rk.call(match, "gates", fit, p, (480, 640), sc)
        good = not e and isinstance(v, tuple) and len(v) == 2 and bool(v[0]) == want[0] and v[1] == want[1]
        line(6, "gates", v, e, good, f"expected {want} (the order of the gates: lesson §5, lab Step 6)")
    v, e = rk.call(lm(), "ratio_curve", [1.0, 2.0, 3.0, 3.0], [4.0, 4.0, 4.0, 3.2], [True, True, False, False], [0.6, 0.8])
    want = [{"ratio": 0.6, "kept": 2, "right": 2, "precision": 1.0}, {"ratio": 0.8, "kept": 3, "right": 2, "precision": 2 / 3}]
    good = (not e and isinstance(v, list) and len(v) == 2 and all(isinstance(r, dict) for r in v)
            and all(r.get(k) == w[k] for r, w in zip(v, want) for k in ("ratio", "kept", "right"))
            and all(r.get("precision") is not None and abs(r["precision"] - w["precision"]) < 1e-9 for r, w in zip(v, want)))
    line(8, "ratio_curve", v, e, good, "the docstring says kept 2 and 3, right 2 and 2, precision 1.0 and 0.667")
    print("\nEdge cases (the check tests these too, on other numbers)")

    def raises(fn, *args):
        f = getattr(match, fn, None)
        if f is None or rk.is_stub(f):
            return None, f"{fn}() is not written yet"
        try:
            f(*args)
        except ValueError:
            return True, None
        except Exception as ex:                                          # noqa: BLE001
            return False, f"raised {type(ex).__name__} ({ex}), not ValueError"
        return False, "returned a value, no ValueError"

    v, e = rk.call(match, "ratio_test", np.array([[4.0, 4.0, 9.0]]), 1.0)
    line(1, "ratio_test, a tie", None if e else np.asarray(v).tolist(), e, not e and np.asarray(v).size == 0,
         "best 4 and second 4: 4 < 1.0 × 4 is False — the test is strict (<)")
    v, e = rk.call(match, "ratio_test", np.array([[1.0], [2.0]]), 0.8)
    line(1, "ratio_test, 1 column", None if e else np.asarray(v).tolist(), e, not e and np.asarray(v).size == 0,
         "one column has no second-nearest: return np.zeros((0, 2), dtype=int)")
    for args, why in ((([[1.0, 2.0]], [[3.0, 4.0]]), "one pair"), (([[3.0, 3.0], [3.0, 3.0]], [[1.0, 1.0], [2.0, 2.0]]),
                                                                    "one point twice")):
        ok, e = raises("fit_similarity", *args)
        line(2, f"fit_similarity, {why}", "ValueError" if ok else None, e, bool(ok), "raise ValueError")
    rng = np.random.default_rng(5)
    big = rng.uniform(1000, 1600, (20, 2))
    Ht = np.array([[1.1, 0.1, 25.0], [-0.08, 0.95, 10.0], [3e-4, -2e-4, 1.0]])
    tgt = warp(Ht, big) + rng.normal(0, 1.0, (20, 2))
    v, e = rk.call(match, "dlt_homography", big, tgt)
    if not e:
        H_cv, _ = cv2.findHomography(big, tgt, 0)
        grid = np.array([[x, y] for x in (1000, 1300, 1600) for y in (1000, 1300, 1600)], float)
        dev = float(np.hypot(*(warp(np.asarray(v, float), grid) - warp(H_cv, grid)).T).max())
        line(3, "dlt_homography, big pixels", f"within {dev:.2f} px of OpenCV", None, dev < 3.0,
             f"{dev:.1f} px away from OpenCV's fit on 20 noisy pairs near (1 300, 1 300): normalise with "
             "normalise_points and undo it at the end (lab Step 3, hint 3)")
    else:
        line(3, "dlt_homography, big pixels", None, e, False, "")
    ok, e = raises("ransac_iterations", 0.99, 0.0, 2)
    line(4, "ransac_iterations, w = 0", "ValueError" if ok else None, e, bool(ok), "w = 0: raise ValueError")
    src2 = src + np.random.default_rng(2).normal(0, 0.3, src.shape)
    v, e = rk.call(match, "ransac", src2, dst, "similarity", 1.5, 30, np.random.default_rng(1))
    if not e and isinstance(v, tuple) and len(v) == 2 and v[0] is not None:
        inl = np.asarray(v[1], dtype=bool)
        refit = match.fit_model("similarity", src2[inl], dst[inl])
        good = refit is not None and np.allclose(np.asarray(v[0], float), refit, atol=1e-6)
        line(5, "ransac, the refit", "M = the fit on all the inliers" if good else "M ≠ refit", None, good,
             "return fit_model(kind, src[best], dst[best]) at the end, not the best SAMPLE's model (lab Step 5, hint 5)")
    else:
        line(5, "ransac, the refit", None, e or f"got {v!r:.80}", False, "")
    v, e = rk.call(match, "ransac", np.zeros((0, 2)), np.zeros((0, 2)), "similarity", 3.0, 10, np.random.default_rng(0))
    good = not e and isinstance(v, tuple) and v[0] is None and np.asarray(v[1]).size == 0
    line(5, "ransac, no pairs", None if e else "(None, [])" if good else repr(v)[:60], e, good,
         "with fewer pairs than a sample needs, return (None, an all-False array) before drawing")
    for args, want, why in (((None, np.zeros((2, 2)), (480, 640), 1.6), (False, "no fit"), "fit None, 2 points"),
                            (((3.0, 0.0, 0.0, 0.0), np.zeros((4, 2)), (480, 640), 1.6), (False, "too few inliers"),
                             "4 inliers, wrong scale")):
        v, e = rk.call(match, "gates", *args)
        good = not e and isinstance(v, tuple) and len(v) == 2 and (bool(v[0]), v[1]) == want
        line(6, f"gates, {why}", v, e, good, f"expected {want}: the gates in the docstring's order")
    v, e = rk.call(lm(), "ratio_curve", [1.0, 0.2], [1.0, 0.5], [True, False], [1.0, 0.1])
    good = (not e and isinstance(v, list) and len(v) == 2 and all(isinstance(r, dict) for r in v)
            and v[0].get("kept") == 1 and v[0].get("right") == 0 and v[1].get("kept") == 0 and v[1].get("precision") is None)
    line(8, "ratio_curve, tie, none kept", v, e, good, "expected kept 1 (1.0 < 1.0 × 1.0 is False: strict <), right 0; "
         "then kept 0 with precision None (no division by 0)")
    print("\nTODO 7 (learned_pairs) and TODO 9 (match_photo) need the data and your network: "
          "`python3 run_match.py learned` and `python3 run_match.py mission`.")
    print("\nAll these examples pass. They are not the check: ✔ here means the docstring examples and these edge "
          "cases work; the check tests other numbers." if ok_all else "\nFix the ✘ lines first, from the top.")


# ================================================================================================= session 1
def look():
    os.makedirs("look", exist_ok=True)
    for p in load_json("pairs.json"):
        for rel in (p["map"], p["photo"]):
            dst = os.path.join("look", os.path.basename(rel))
            if rel.startswith("map_"):
                img = cv2.imread(os.path.join(DATA, rel))
                cv2.imwrite(dst, stamp(img))
            else:
                shutil.copyfile(os.path.join(DATA, rel), dst)
    print("Copied into look/: the map patches (map_*.png) and the eight session-1 photos. Click them (⟳ to refresh).")
    print(f"{'pair':14s} {'map':16s} prior heading ± σ, zoom")
    for p in load_json("pairs.json"):
        pr = p["prior"]
        print(f"{p['name']:14s} {p['map']:16s} {pr['heading_deg']:6.1f}° ± {pr['heading_sigma_deg']:.0f}°, {pr['zoom']}")


def ratio(name):
    p, mg, pg, H = pair(name)
    p1, p2, dist = sift_candidates(mg, pg)
    j, b, s = two_nearest(dist)
    right = right_mask(H, p1, p2[j])
    print(f"pair {name}: {len(p1)} SIFT points in the map, {len(p2)} in the photo; each map point's nearest photo point")
    print(f"{'ratio':>6} {'kept':>6} {'right':>6} {'precision':>10}   (right = the truth agrees within {RIGHT_PX:.0f} px)")
    print(f"{'none':>6} {len(j):6d} {int(right.sum()):6d} {right.mean() if len(j) else 0:10.3f}")
    for r in (0.6, 0.7, 0.8, 0.9):
        v, e = rk.call(match, "ratio_test", dist, r)
        if e:
            sys.exit(e)
        m = np.asarray(v, dtype=int).reshape(-1, 2)
        ok = right_mask(H, p1[m[:, 0]], p2[m[:, 1]])
        print(f"{r:6.1f} {len(m):6d} {int(ok.sum()):6d} {ok.mean() if len(m) else 0:10.3f}")
        if r == 0.8:
            keep = (m, ok)
    m, ok = keep
    sel = np.random.default_rng(0).permutation(len(m))[:150]
    draw_pairs(mg, pg, p1[m[sel, 0]], p2[m[sel, 1]], ok[sel], os.path.join(OUT, f"ratio_{name}.png"),
               f"{name}: 150 of the {len(m)} pairs kept by your ratio test (0.8) - green right, red wrong")


def fit():
    print("The pairs the truth calls right (SIFT, ratio 0.8), fitted with YOUR functions and with OpenCV.")
    print("Residual = distance (photo px) between the fitted model's image of a map point and its photo point.\n")
    print(f"{'pair':10s} {'pairs':>5}  {'model':11s} {'median':>7} {'p90':>7} {'OpenCV median':>14}  fit")
    for name in ("city", "city_tilt"):
        p, mg, pg, H = pair(name)
        p1, p2, dist = sift_candidates(mg, pg)
        v, e = rk.call(match, "ratio_test", dist, 0.8)
        if e:
            sys.exit(e)
        m = np.asarray(v, dtype=int).reshape(-1, 2)
        src, dst = p1[m[:, 0]].astype(np.float64), p2[m[:, 1]].astype(np.float64)
        good = right_mask(H, src, dst)
        src, dst = src[good], dst[good]
        sim = rk.need_ok(match, "fit_similarity", src, dst, n=4)
        Ms = match.similarity_matrix(*sim)
        Hd = rk.need_ok(match, "dlt_homography", src, dst)
        A_cv = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=1e6)[0]
        H_cv, _ = cv2.findHomography(src, dst, 0)
        for label, M, Mcv in (("similarity", Ms, np.vstack([A_cv, [0, 0, 1]])), ("homography", np.asarray(Hd, float), H_cv)):
            r = np.hypot(*(warp(M, src) - dst).T)
            rc = np.hypot(*(warp(Mcv, src) - dst).T)
            extra = (f"s = {sim[0]:.3f}, θ = {sim[1]:.1f}°" if label == "similarity" else
                     f"H[2] = [{M[2, 0]:.2e}, {M[2, 1]:.2e}, 1]")
            print(f"{name:10s} {len(src):5d}  {label:11s} {np.median(r):7.2f} {np.percentile(r, 90):7.2f} "
                  f"{np.median(rc):14.2f}  {extra}")


def iters():
    print("YOUR ransac_iterations with p = 0.99 (the course's value; NAVERA uses 0.999)\n")
    print(f"{'w (inlier share)':>17} {'s = 2 (similarity)':>19} {'s = 4 (homography)':>19}")
    for w in (0.9, 0.5, 0.3, 0.2, 0.1):
        a = rk.need_ok(match, "ransac_iterations", 0.99, w, 2)
        b = rk.need_ok(match, "ransac_iterations", 0.99, w, 4)
        print(f"{w:17.1f} {a:19d} {b:19d}")


def ransac_cmd(name):
    p, mg, pg, H = pair(name)
    p1, p2, dist = sift_candidates(mg, pg)
    m = np.asarray(rk.need_ok(match, "ratio_test", dist, 0.8), dtype=int).reshape(-1, 2)
    src, dst = p1[m[:, 0]].astype(np.float64), p2[m[:, 1]].astype(np.float64)
    good = right_mask(H, src, dst)
    w = good.mean() if len(good) else 0.0
    print(f"pair {name}: {len(src)} pairs after the ratio test, {int(good.sum())} right (w = {w:.2f})\n")
    print(f"{'who':24s} {'iters':>6} {'inliers':>8} {'right in.':>9} {'centre err m':>12} {'time s':>7}")
    rows = []
    for kind, fixed in (("similarity", None), ("homography", None), ("similarity", 500), ("homography", 500)):
        n_it = fixed or rk.need_ok(match, "ransac_iterations", 0.99, max(w, 0.05), match.MIN_SAMPLE[kind])
        t = time.time()
        v = rk.need_ok(match, "ransac", src, dst, kind, 6.0, n_it, np.random.default_rng(0))
        dt = time.time() - t
        M, inl = v
        inl = np.asarray(inl, dtype=bool)
        err = centre_error_m(np.asarray(M, float), H, p["map_m_per_px"]) if M is not None and H is not None else None
        print(f"{'yours, ' + kind:24s} {n_it:6d} {int(inl.sum()):8d} {int((inl & good).sum()):9d} {fmt(err):>12} {dt:7.3f}")
        rows.append((kind, M, inl))
        if kind == "homography" and fixed is None:
            print(f"{'':24s} (the first two rows use ransac_iterations(0.99, {w:.2f}, s); the next two use 500)")
    t = time.time()
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=6.0, maxIters=5000,
                                         confidence=0.999)
    dt = time.time() - t
    if A is not None:
        inl = inl.ravel() > 0
        err = centre_error_m(np.vstack([A, [0, 0, 1]]), H, p["map_m_per_px"]) if H is not None else None
        print(f"{'OpenCV, similarity':24s} {'auto':>6} {int(inl.sum()):8d} {int((inl & good).sum()):9d} {fmt(err):>12} {dt:7.3f}")
    t = time.time()
    Hc, inl = cv2.findHomography(src, dst, cv2.RANSAC, 6.0, maxIters=5000, confidence=0.999)
    dt = time.time() - t
    if Hc is not None:
        inl = inl.ravel() > 0
        err = centre_error_m(Hc, H, p["map_m_per_px"]) if H is not None else None
        print(f"{'OpenCV, homography':24s} {'auto':>6} {int(inl.sum()):8d} {int((inl & good).sum()):9d} {fmt(err):>12} {dt:7.3f}")
    kind, M, inl = rows[2]
    draw_pairs(mg, pg, src[inl], dst[inl], good[inl], os.path.join(OUT, f"ransac_{name}.png"),
               f"{name}: the inliers of YOUR similarity RANSAC — green right, red wrong")


def gates_cmd():
    session1_ready("`gates` runs your ratio test, your RANSAC and your gates")
    print("Each pair: SIFT, ratio test 0.8, YOUR RANSAC (similarity, 6 px, 500 samples), then YOUR gates with the zoom")
    print("the drone predicts. 'prototype' = NAVERA's first rule: at least 12 inliers, no scale check.\n")
    print(f"{'pair':14s} {'pairs':>5} {'inliers':>7} {'scale':>6} {'theta':>7} {'prototype':>9}  {'your gates':24s} truth")
    for p in load_json("pairs.json"):
        _, mg, pg, H = pair(p["name"])
        p1, p2, dist = sift_candidates(mg, pg)
        m = np.asarray(rk.need_ok(match, "ratio_test", dist, 0.8), dtype=int).reshape(-1, 2)
        src, dst = p1[m[:, 0]].astype(np.float64), p2[m[:, 1]].astype(np.float64)
        r, e = rk.call(match, "ransac", src, dst, "similarity", 6.0, 500, np.random.default_rng(0))
        if e:
            sys.exit(f"{p['name']} ({len(src)} pairs): {e}" + (" — with fewer pairs than a sample needs, return "
                     "(None, all False) before drawing (lab Step 5, hint 1)" if len(src) < 2 else ""))
        fit_, inl = match.ransac_similarity(src, dst, 6.0, 500, np.random.default_rng(0))
        inl = np.asarray(inl, dtype=bool)
        v, e = rk.call(match, "gates", fit_, dst[inl], pg.shape, p["prior"]["zoom"])
        if e:
            sys.exit(e)
        proto = "accept" if fit_ is not None and inl.sum() >= 12 else "refuse"
        if H is None:
            truth = "another place"
        elif fit_ is None:
            truth = "—"
        else:
            truth = f"centre {centre_error_m(match.similarity_matrix(*fit_), H, p['map_m_per_px']):.1f} m off"
        sc = f"{fit_[0]:.2f}" if fit_ else "—"
        th = f"{fit_[1]:.1f}" if fit_ else "—"
        print(f"{p['name']:14s} {len(src):5d} {int(inl.sum()):7d} {sc:>6} {th:>7} {proto:>9}  "
              f"{str(v[0]) + ', ' + v[1]:24s} {truth}")


# ================================================================================================= session 2
def learned_cmd(name):
    net = model()
    L = lm()
    p, mg, pg, H = pair(name)
    pr = p["prior"]
    print(f"pair {name}: prior heading {pr['heading_deg']}° (± {pr['heading_sigma_deg']}°), zoom {pr['zoom']}\n")
    print(f"{'who':30s} {'pairs':>6} {'right':>6} {'share':>6} {'inliers':>8} {'centre err m':>12} {'time s':>7}")
    for who in ("SIFT (ratio 0.8)", "your network (ratio 0.8)"):
        t = time.time()
        if who.startswith("SIFT"):
            v, e = rk.call(L, "sift_pairs", mg, pg, 0.8)
        else:
            v, e = rk.call(L, "learned_pairs", mg, pg, pr["heading_deg"], pr["zoom"], net, 0.8, None)
        if e:
            sys.exit(e)
        if not (isinstance(v, tuple) and len(v) == 2):
            sys.exit(f"learned_pairs() must return two arrays (src, dst), got {type(v).__name__}")
        src, dst = (np.asarray(x, dtype=np.float64).reshape(-1, 2) for x in v)
        dt = time.time() - t
        good = right_mask(H, src, dst)
        fit_, inl = match.ransac_similarity(src, dst, 6.0, 500, np.random.default_rng(0))
        err = centre_error_m(match.similarity_matrix(*fit_), H, p["map_m_per_px"]) if fit_ and H is not None else None
        print(f"{who:30s} {len(src):6d} {int(good.sum()):6d} {good.mean() if len(good) else 0:6.2f} "
              f"{int(np.sum(inl)):8d} {fmt(err):>12} {dt:7.2f}")
        if not who.startswith("SIFT"):
            if len(src) and good.mean() < 0.3:
                print("\n  Few of your pairs are right. If SIFT's are: are the photo points in the ORIGINAL photo's pixels? "
                      "(lab Step 8, hint 3)")
            up, _, _ = L.upright(pg, pr["heading_deg"], pr["zoom"])
            os.makedirs(OUT, exist_ok=True)
            cv2.imwrite(os.path.join(OUT, f"upright_{name}.png"), up)
            sel = np.random.default_rng(0).permutation(len(src))[:150]
            draw_pairs(mg, pg, src[sel], dst[sel], good[sel], os.path.join(OUT, f"learned_{name}.png"),
                       f"{name}: 150 of the {len(src)} pairs of YOUR network - green right, red wrong")
            print(f"   and out/upright_{name}.png: the photo as your network sees it (north up, map scale)")


def curve_cmd():
    net = model()
    L = lm()
    rows = {"sift": [[], [], []], "learned": [[], [], []]}
    shaken = []
    for p in load_json("curve.json"):
        mg, pg = gray(p["map"]), gray(p["photo"])
        H = np.array(p["H"])
        pr = p["prior"]
        p1, p2, dist = sift_candidates(mg, pg)
        j, b, s = two_nearest(dist)
        rows["sift"][0].append(b)
        rows["sift"][1].append(s)
        rows["sift"][2].append(right_mask(H, p1, p2[j]))
        up, valid, A = L.upright(pg, pr["heading_deg"], pr["zoom"])
        q1 = L.keypoints(mg)
        q2 = L.keypoints(up, valid=valid)
        ld = rk.load_student("navera_lite.learned_desc")
        dd = match.distance_matrix(ld.describe(net, L.patches_at(mg, q1)), ld.describe(net, L.patches_at(up, q2)))
        j, b, s = two_nearest(dd)
        rows["learned"][0].append(b)
        rows["learned"][1].append(s)
        rows["learned"][2].append(right_mask(H, q1, warp(np.linalg.inv(A), q2[j])))
        shaken.append(np.full(len(b), p.get("effects") == "shaken"))
        print(f"  {p['name']} done", flush=True)
    tables = {}
    for who in ("sift", "learned"):
        b, s, c = (np.concatenate(x) for x in rows[who])
        tables[who] = (b, s, c)
    ratios = [0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    dists = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    out = {}
    for who, label in (("sift", "SIFT, ratio test"), ("learned", "your network, ratio test")):
        b, s, c = tables[who]
        v, e = rk.call(L, "ratio_curve", b, s, c, ratios)
        if e:
            sys.exit(e)
        out[label] = v
    b, s, c = tables["learned"]
    v, e = rk.call(L, "ratio_curve", b, np.ones_like(b), c, dists)      # a distance cut is a ratio test against 1
    if e:
        sys.exit(e)
    out["your network, distance < d (no ratio)"] = [dict(r, d=r["ratio"]) for r in v]
    sh = np.concatenate(shaken)
    v, e = rk.call(L, "ratio_curve", b[sh], s[sh], c[sh], ratios)
    if e:
        sys.exit(e)
    shaken_label = "your network, ratio test, SHAKEN photos only"
    n_sh = int(sum(1 for p in load_json("curve.json") if p.get("effects") == "shaken"))
    for label, table in list(out.items()) + [(shaken_label, v)]:
        n = int(sh.sum()) if label == shaken_label else len(tables["sift" if label.startswith("SIFT") else "learned"][0])
        npairs = n_sh if label == shaken_label else 12
        print(f"\n{label}: {n} map points of {npairs} pairs; 'right' = the nearest one is the true point")
        key = "d" if "distance" in label else "ratio"
        loose = next((r["right"] for r in table if r[key] == 0.95), None)
        print(f"  {key:>6} {'kept':>6} {'right':>6} {'precision':>10}" + ("  right / right at 0.95" if loose else ""))
        for r in table:
            share = f"  {r['right'] / loose:20.2f}" if loose else ""
            print(f"  {r[key]:6.2f} {r['kept']:6d} {r['right']:6d} {fmt(r['precision'], 3):>10}{share}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for label, table in out.items():
            x = [r["right"] for r in table]
            y = [r["precision"] if r["precision"] is not None else np.nan for r in table]
            ax.plot(x, y, "o-", label=label)
            key = "d" if "distance" in label else "ratio"
            for r, xx, yy in zip(table, x, y):
                ax.annotate(f"{r[key]:g}", (xx, yy), fontsize=7, xytext=(3, 3), textcoords="offset points")
        ax.set_xlabel("right pairs kept (more is better)")
        ax.set_ylabel("precision = right / kept")
        ax.set_ylim(0.3, 1.01)
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
        ax.set_title("Choosing a threshold: each point is one threshold")
        os.makedirs(OUT, exist_ok=True)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "curve.png"), dpi=110)
        rk.saved(os.path.join(OUT, "curve.png"))


def attempt(L, net, mg, pg, method, heading, zoom, cfg, H, mpp, prior_zoom=None):
    """One matcher on one photo: (inliers, verdict string, success bool)."""
    if method == "sift":
        src, dst = L.sift_pairs(mg, pg, 0.8)
    else:
        v, e = rk.call(L, "learned_pairs", mg, pg, heading, zoom, net, cfg["learned_ratio"], cfg["learned_max_dist"])
        if e:
            sys.exit(e)
        src, dst = (np.asarray(x, dtype=np.float64).reshape(-1, 2) for x in v)
    fit_, inl = match.ransac_similarity(src, dst, 6.0, 500, np.random.default_rng(0))
    inl = np.asarray(inl, dtype=bool)
    ok, reason = match.gates(fit_, dst[inl] if len(dst) else dst, pg.shape, prior_zoom or zoom)
    if not ok:
        return int(inl.sum()), reason, False
    err = centre_error_m(match.similarity_matrix(*fit_), H, mpp)
    return int(inl.sum()), ("ok" if err <= RIGHT_M else f"WRONG {err:.0f} m"), err <= RIGHT_M


def envelope_cmd():
    net = model()
    L = lm()
    cfg, why = decisions(need_limit=False)
    if cfg is None:
        sys.exit(why + " — the envelope uses your network's threshold (HEADING_LIMIT_DEG is decided after this step: "
                       "it may stay None for now)")
    print(f"Your network with LEARNED_RATIO = {cfg['learned_ratio']}, LEARNED_MAX_DIST = {cfg['learned_max_dist']}. "
          "SIFT with ratio 0.8. Each cell: inliers, then the gates' verdict (ok = accepted and right).\n")
    env = {(e["place"], e["effect"]): e for e in load_json("envelope.json")}
    result = {}
    print("A. The prior heading is WRONG by … (the photo is sharp; the zoom prior is right)")
    print(f"{'error':>7}  " + "  ".join(f"{pl + ', ' + who:>24s}" for pl in ("city", "olives") for who in ("network", "SIFT")))
    for err_deg in (0, 5, 10, 15, 20, 25, 30, 35, 40, 60, 90):
        cells = []
        for pl in ("city", "olives"):
            e = env[(pl, "sharp")]
            mg, pg, H = gray(e["map"]), gray(e["photo"]), np.array(e["H"])
            a = attempt(L, net, mg, pg, "learned", e["heading_deg"] + err_deg, e["zoom"], cfg, H, e["map_m_per_px"])
            s = attempt(L, net, mg, pg, "sift", None, e["zoom"], cfg, H, e["map_m_per_px"]) if err_deg == 0 else None
            result[("heading", pl, err_deg)] = a[2]
            cells += [f"{a[0]:4d} {a[1]:>18s}", f"{s[0]:4d} {s[1]:>18s}" if s else f"{'(no prior: as above)':>23s}"]
        print(f"{err_deg:6d}°  " + "  ".join(f"{c:>24s}" for c in cells), flush=True)
    both = [e for e in (0, 5, 10, 15, 20, 25, 30, 35, 40, 60, 90)
            if result[("heading", "city", e)] and result[("heading", "olives", e)]]
    run = 0
    for e in (0, 5, 10, 15, 20, 25, 30, 35, 40):                    # the last error of the first unbroken run of oks
        if e in both:
            run = e
        else:
            break
    print(f"   → your network matched BOTH places for every heading error up to {run}° (an error, not a σ: lab Step 10)")
    print("\nB. The prior ZOOM is wrong by … (the altitude is wrong; the heading prior is right)")
    for factor in (1.0, 1.1, 1.2, 1.3, 1.45):
        cells = []
        for pl in ("city", "olives"):
            e = env[(pl, "sharp")]
            mg, pg, H = gray(e["map"]), gray(e["photo"]), np.array(e["H"])
            z = e["zoom"] / factor
            a = attempt(L, net, mg, pg, "learned", e["heading_deg"], z, cfg, H, e["map_m_per_px"])
            s = attempt(L, net, mg, pg, "sift", None, z, cfg, H, e["map_m_per_px"])
            result[("zoom", pl, factor)] = a[2]
            cells += [f"{a[0]:4d} {a[1]:>18s}", f"{s[0]:4d} {s[1]:>18s}"]
        print(f"{'×' + str(factor):>7}  " + "  ".join(f"{c:>24s}" for c in cells), flush=True)
    print("\nC. Blur and shake (both priors right)")
    for tag in ("sharp", "blur2", "blur3", "blur4", "shake9", "shake13", "shake17"):
        cells = []
        for pl in ("city", "olives"):
            e = env[(pl, tag)]
            mg, pg, H = gray(e["map"]), gray(e["photo"]), np.array(e["H"])
            a = attempt(L, net, mg, pg, "learned", e["heading_deg"], e["zoom"], cfg, H, e["map_m_per_px"])
            s = attempt(L, net, mg, pg, "sift", None, e["zoom"], cfg, H, e["map_m_per_px"])
            cells += [f"{a[0]:4d} {a[1]:>18s}", f"{s[0]:4d} {s[1]:>18s}"]
        print(f"{tag:>7}  " + "  ".join(f"{c:>24s}" for c in cells), flush=True)
    print("\n(Photos: /data/academy/22-matching/photos/env_*.jpg — copy one into look/ to see it.)")


def mission_cmd():
    net = model()
    L = lm()
    cfg, why = decisions()
    if cfg is None:
        sys.exit(why)
    print(f"YOUR match_photo with your decisions {cfg}\n")
    print(f"{'scene':6s} {'what the photo shows':30s} {'prior heading':>14} {'zoom':>5}  {'answer':7s} {'method':8s} "
          f"{'inliers':>7} {'reason':16s} verdict")
    counts = {"right": 0, "refused": 0, "WRONG": 0}
    t_all, inl_by = 0.0, {"sift": [], "learned": []}
    for s in load_json("mission.json"):
        mg, pg = gray(s["map"]), gray(s["photo"])
        H = None if s["H"] is None else np.array(s["H"])
        pr = s["prior"]
        t = time.time()
        v, e = rk.call(L, "match_photo", mg, pg, pr, net, cfg)
        if e:
            sys.exit(f"{s['name']}: {e}")
        if not isinstance(v, dict) or not {"ok", "method", "fit", "inliers", "reason"} <= set(v):
            sys.exit(f"match_photo() must return a dict with ok, method, fit, inliers, reason — got {v!r:.150}")
        dt = time.time() - t
        t_all += dt
        if v["ok"] and v["method"] in inl_by:
            inl_by[v["method"]].append(int(v["inliers"]))
        if v["ok"]:
            if v["fit"] is None:
                sys.exit(f"{s['name']}: ok is True but fit is None — an accepted match needs its fit")
            err = None if H is None else centre_error_m(match.similarity_matrix(*v["fit"]), H, s["map_m_per_px"])
            verdict = "right" if err is not None and err <= RIGHT_M else "WRONG"
            note = "another place!" if H is None else f"centre {err:.1f} m off"
        else:
            verdict, note = "refused", ""
        counts[verdict] += 1
        hp = "unknown" if pr["heading_deg"] is None else f"{pr['heading_deg']:.0f}° ± {pr['heading_sigma_deg']:.0f}°"
        print(f"{s['name']:6s} {s.get('desc', ''):30s} {hp:>14} {pr['zoom']:5.2f}  {'accept' if v['ok'] else 'refuse':7s} "
              f"{str(v['method']):8s} "
              f"{int(v['inliers']):7d} {str(v['reason']):16s} {verdict} {note}  ({dt:.1f} s)", flush=True)
    acc = ", ".join(f"{m} {len(x)} (mean {np.mean(x):.0f} inliers)" for m, x in inl_by.items() if x)
    print(f"\naccepted by method: {acc or 'none'}; total time {t_all:.1f} s")
    print(f"right {counts['right']}, refused {counts['refused']}, WRONG {counts['WRONG']} "
          "(a WRONG accepted match is the worst outcome: NAVERA's rule is zero)")


# ================================================================================================= main
if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    arg = args[1] if len(args) > 1 else None
    if cmd == "test":
        test()
    elif cmd == "look":
        look()
    elif cmd == "ratio":
        ratio(arg or "city")
    elif cmd == "fit":
        fit()
    elif cmd == "iters":
        iters()
    elif cmd == "ransac":
        ransac_cmd(arg or "city_tilt")
    elif cmd == "gates":
        gates_cmd()
    elif cmd == "learned":
        learned_cmd(arg or "olives_shaken")
    elif cmd == "curve":
        curve_cmd()
    elif cmd == "envelope":
        envelope_cmd()
    elif cmd == "mission":
        mission_cmd()
    else:
        print(__doc__)
