import json
import math
import os

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
DICE = [3, 5, 2, 6, 6, 1, 4, 4, 2, 5]


def U():
    return load_student("uncertainty.py")


@c.test("mean(): the average", hint="sum(values) / len(values)")
def _():
    (mean,) = need(U(), "mean")
    c.near(mean([1, 2, 6]), 3.0, 1e-9, "mean([1, 2, 6])")
    c.near(mean(DICE), 3.8, 1e-9, "mean(ten dice throws)")


@c.test("median(): the middle value (odd and even counts)",
        hint="Sort first. Odd count: the middle one. Even count: the average of the two middle ones.")
def _():
    (median,) = need(U(), "median")
    c.near(median([7, 1, 3]), 3.0, 1e-9, "median([7, 1, 3])")
    c.near(median([4, 1, 3, 2]), 2.5, 1e-9, "median([4, 1, 3, 2])")
    c.near(median(DICE), 4.0, 1e-9, "median(ten dice throws)")
    c.near(median([2, 3, 1000]), 3.0, 1e-9, "median([2, 3, 1000])")


@c.test("std(): the standard deviation (divide by n)",
        hint="m = mean(values); then the square root of the mean of (v - m)**2.")
def _():
    (std,) = need(U(), "std")
    c.near(std([2, 4, 4, 4, 5, 5, 7, 9]), 2.0, 1e-9, "std([2, 4, 4, 4, 5, 5, 7, 9])")
    c.near(std([5, 5, 5]), 0.0, 1e-9, "std([5, 5, 5])")
    c.near(std(DICE), 1.661325, 1e-5, "std(ten dice throws)")


@c.test("share_within(): the fraction of errors inside a circle",
        hint="Count the errors <= radius, divide by how many errors there are. Return 0.0 .. 1.0, not a percent.")
def _():
    (f,) = need(U(), "share_within")
    c.near(f([1, 2, 3, 4], 2.5), 0.5, 1e-9, "share_within([1, 2, 3, 4], 2.5)")
    c.near(f([1, 2, 3, 4], 4.0), 1.0, 1e-9, "share_within([1, 2, 3, 4], 4.0) (4 is on the circle: inside)")


@c.test("fuse(): the weighted average beats both measurements",
        hint="w = 1 / sigma**2 for each; x = (w1*x1 + w2*x2) / (w1 + w2); sigma = 1 / sqrt(w1 + w2).")
def _():
    (fuse,) = need(U(), "fuse")
    r = fuse(100.0, 10.0, 110.0, 5.0)
    c.ok(isinstance(r, tuple) and len(r) == 2, f"fuse() should return (value, sigma), got {r!r}")
    c.near(r[0], 108.0, 1e-6, "the fused value of 100 (sigma 10) and 110 (sigma 5)")
    c.near(r[1], 4.472136, 1e-5, "the fused sigma")
    x, s = fuse(10.0, 3.0, 20.0, 3.0)
    c.near(x, 15.0, 1e-9, "equal sigmas: the plain average")
    c.near(s, 3.0 / math.sqrt(2), 1e-6, "equal sigmas: sigma / sqrt(2)")


@c.test("make_covariance(): variances on the diagonal, or UNKNOWN",
        hint="The diagonal holds sigma SQUARED (variances, m²). None -> nine zeros and type 0 (UNKNOWN).")
def _():
    (f,) = need(U(), "make_covariance")
    r = f(3.0, 4.0)
    c.ok(isinstance(r, tuple) and len(r) == 2 and r[0] is not None,
         f"make_covariance() should return (list of 9 numbers, type), got {r!r}")
    cov, kind = r
    c.eq([float(v) for v in cov], [9.0, 0.0, 0.0, 0.0, 16.0, 0.0, 0.0, 0.0, 64.0], "make_covariance(3, 4) matrix")
    c.eq(kind, 2, "make_covariance(3, 4) type (DIAGONAL_KNOWN)")
    cov, kind = f(3.0, 4.0, 10.0)
    c.near(cov[8], 100.0, 1e-9, "make_covariance(3, 4, 10) up variance")
    cov, kind = f(None, None)
    c.eq((list(cov), kind), ([0.0] * 9, 0), "make_covariance(None, None)")


@c.test("the REAL NAVERA arbiter accepts your covariance",
        hint="estimate_message() puts make_covariance() in a PositionEstimate; the arbiter's _sane() and "
             "_stated_sigma() must accept it (sigma = the larger of east and north).")
def _():
    (msg_of, mk) = need(U(), "estimate_message", "make_covariance")
    c.ok(isinstance(mk(3.0, 4.0), tuple) and mk(3.0, 4.0)[0] is not None, "finish make_covariance() first (TODO 6)")
    try:
        from navera_estimator.nodes.estimator_node import EstimatorNode as E
    except ImportError as e:
        c.skip(f"NAVERA's estimator cannot be imported here ({e})")
    m = msg_of(35.734, 10.576, 3.0, 4.0)
    c.ok(E._sane(m), "the real arbiter's _sane() refuses this covariance: " + str(list(m.position_covariance)))
    s = E._stated_sigma(m)
    c.ok(s is not None and abs(s - 4.0) < 1e-9, f"the real arbiter reads a stated sigma of {s}, expected 4.0 m")
    m = msg_of(35.734, 10.576, None, None)
    c.ok(E._sane(m) and E._stated_sigma(m) is None,
         "with sigma None the arbiter must see 'uncertainty unknown' (type 0, sane)")


def results():
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet: run `python3 analyse.py`")
    with open("results.json") as f:
        return json.load(f)


@c.test("analyse.py: the GPS error statistics", hint="Run `python3 analyse.py` after TODO 1–5.")
def _():
    g = results()["gps"]
    c.near(g["median_m"], 2.0811, 0.01, "GPS median error (m)")
    c.near(g["mean_m"], 2.2169, 0.01, "GPS mean error (m)")
    c.near(g["max_m"], 5.9197, 0.01, "GPS max error (m)")
    c.near(g["sigma_east_m"], 1.9437, 0.01, "GPS sigma east (m)")


@c.test("analyse.py: the share of fixes inside the 1, 2, 3 sigma circles (TODO 7)",
        hint="share_within(dist, k * sigma) for k = 1, 2, 3 — a fraction, not a percent.")
def _():
    g = results()["gps"]
    for k, want in ((1, 0.3933), (2, 0.8867), (3, 0.9667)):
        c.ok(g.get(f"within_{k}s") is not None, f"within_{k}s is still None (TODO 7)")
        c.near(g[f"within_{k}s"], want, 0.004, f"share inside {k} sigma")


@c.test("analyse.py: mean vs median with three wrong vision matches",
        hint="Run analyse.py: the vision numbers use your mean() and median().")
def _():
    v = results()["vision"]
    c.near(v["median_m"], 8.348, 0.01, "vision median error (m)")
    c.near(v["mean_m"], 10.245, 0.01, "vision mean error (m)")


@c.test("analyse.py: the fused position beats both sources (TODO 8)",
        hint="For each row: fe, _ = fuse(e1, SIGMA_A, e2, SIGMA_B), the same for north, then append "
             "math.hypot(fe, fn).")
def _():
    f = results()["fusion"]
    c.ok(f.get("median_fused_m") is not None, "median_fused_m is None: the list `fused` is empty (TODO 8)")
    c.near(f["median_fused_m"], 5.863, 0.01, "median error of the fused position (m)")
    c.ok(f["median_fused_m"] < f["median_a_m"] and f["median_fused_m"] < f["median_b_m"],
         "the fused error should be smaller than both A and B")


@c.test("error_circles.png: the fixes and the three circles (TODO 9)",
        hint="ax.add_patch(plt.Circle((0, 0), k * sigma, fill=False, color=color, label=label)), then run "
             "analyse.py and open error_circles.png in the editor.")
def _():
    c.file_exists("error_circles.png")
    with open("error_circles.png", "rb") as f:
        head = f.read(8)
    c.ok(head == b"\x89PNG\r\n\x1a\n", "error_circles.png is not a PNG image")
    code, out = sh("grep -v '^ *#' analyse.py | grep -c 'Circle('", timeout=10)
    c.ok(out.strip().isdigit() and int(out.strip()) >= 1, "analyse.py does not draw any plt.Circle yet")


ANSWERS = {"Q1": "b", "Q2": "b", "Q3": "c", "Q4": "b", "Q5": "a"}


@c.test("quiz (answers.py)", hint="Each answer is in the course tab; Q5 is your fuse() with 6 and 9.")
def _():
    m = load_student("answers.py")
    wrong = []
    for q, good in ANSWERS.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        if v != good:
            wrong.append(f"{q} = {v!r}" if v else f"{q} is empty")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


c.run()
