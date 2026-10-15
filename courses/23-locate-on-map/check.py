import contextlib
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import tempfile

import numpy as np

from academy_check import (CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run)

c = Checker()
DATA = "/data/academy/23-locate-on-map"
MAP = "/data/map.mbtiles"


# ---------------------------------------------------------------- loading and small helpers
def module(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def functions(mod, *names):
    m = module(f"navera_lite.{mod}")
    fns = need(m, *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/{mod}.py)")
    return fns


def answers(*names):
    return need(module("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def go(fn, *args, seconds=60, **kw):
    try:
        return run(fn, *args, seconds=seconds, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "does not require grad" in msg:
            msg += " — the loss lost its gradient: torch operations only (no .item(), numpy or torch.tensor of a result)"
        if "mat1 and mat2" in msg:
            msg += " — the Linear layer gets the wrong size: one number per map of conv4 after the global average pooling"
        raise CheckFailed(msg)


def arr(v, what, shape=None):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return numbers, got {type(v).__name__}")
    if shape is not None and a.shape != shape:
        raise CheckFailed(f"{what} should have shape {shape}, got {a.shape}")
    return a


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def tile_centre(x, y, z=17):
    n = 2 ** z
    lon = (x + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))
    return lat, lon


# ======================================================================== session 1 — Finder
IMG = np.random.default_rng(2323).integers(0, 256, (2, 300, 260, 3)).astype(np.uint8)
PIX = [(0, 0, 0, 0), (0, 1, 50, 60), (1, 2, 223, 223), (1, 0, 100, 7), (0, 2, 13, 200)]
PRE224 = [0.9988, 0.29272, -0.91556, 1.01593, -0.41011]
PRE_BGR = [-0.9363, 0.29272, 1.54196, -1.17604, 0.49621]
PRE_LINEAR = [1.30705, 0.15266, -1.10728, 1.44404, -0.44497]
PRE_RESHAPE = [0.9988, 0.91451, -0.91556, -0.7993, -1.39866]
PRE112 = [0.10831, 0.31022, 1.45482]


def tensor_values(t, what):
    try:
        shape = tuple(int(s) for s in t.shape)
        a = np.asarray(t.detach().cpu().numpy() if hasattr(t, "detach") else t, dtype=float)
    except Exception:                                                       # noqa: BLE001
        raise CheckFailed(f"{what} must return a torch tensor, got {type(t).__name__}")
    return shape, a


@c.test("TODO 1: preprocess() on unseen pictures — RGB, 0..1, ImageNet normalisation, INTER_AREA, channels first",
        hint="Lesson §3: per picture cv2.resize(…, (size, size), interpolation=cv2.INTER_AREA), BGR → RGB ([:, :, ::-1]), "
             "/ 255, (x − mean) / std with IMAGENET_MEAN/STD (red first), .transpose(2, 0, 1); a float32 tensor (N, 3, size, size).")
def _():
    (f,) = functions("retrieval", "preprocess")
    t = go(f, IMG)
    shape, a = tensor_values(t, "preprocess")
    if shape == (2, 224, 224, 3):
        raise CheckFailed("preprocess returns (N, 224, 224, 3): the channels must come first, (N, 3, 224, 224)")
    c.ok(shape == (2, 3, 224, 224), f"preprocess of 2 pictures 300 × 260 should have shape (2, 3, 224, 224), got {shape}")
    c.ok(str(getattr(t, "dtype", "")) == "torch.float32", f"the tensor must be float32, got {getattr(t, 'dtype', '?')}")
    v = [float(a[p]) for p in PIX]
    if np.allclose(v, PRE_RESHAPE, atol=2e-3):
        raise CheckFailed("reshape(3, size, size) mixes pixels and channels: move the channel axis with "
                          ".transpose(2, 0, 1) (lab Step 1, hint 6)")
    if np.abs(a).max() > 50 and abs(v[0] - 299.19214) < 1 and abs(v[2] - 851.52889) < 1:
        raise CheckFailed("values in the hundreds AND the channels still in BGR order: reverse the channels and divide "
                          "by 255 (lab Step 1, hints 2 and 3)")
    if np.allclose(v, PRE_BGR, atol=2e-3):
        raise CheckFailed("the channels are still in OpenCV's BGR order: DINOv2 learned from RGB (lesson §3)")
    if np.abs(a).max() > 50:
        raise CheckFailed(f"values up to {np.abs(a).max():.0f}: scale the pixels to 0..1 (/ 255) before normalising")
    if np.allclose(v, PRE_LINEAR, atol=2e-3):
        raise CheckFailed("the resize is not cv2.INTER_AREA (the index was made with INTER_AREA: shrinking averages)")
    c.ok(np.allclose(v, PRE224, atol=2e-3), f"values at 5 places {np.round(v, 4).tolist()}: expected other values — "
         "mean and std per channel, in RED, GREEN, BLUE order, after / 255")
    t2 = go(f, IMG[:1], size=112)
    shape2, a2 = tensor_values(t2, "preprocess(size=112)")
    c.ok(shape2 == (1, 3, 112, 112), f"with size=112 the shape should be (1, 3, 112, 112), got {shape2}: use the size "
         "argument")
    c.ok(np.allclose([float(a2[0, k, 40, 70]) for k in range(3)], PRE112, atol=2e-3), "with size=112 the values are wrong")


@c.test("TODO 2: rank() on unseen vectors — cosine, rows of any length, best first, ties in index order",
        hint="Lesson §2: sims = (E @ q) / (‖each row of E‖ · ‖q‖); order = np.argsort(−sims, kind=\"stable\"); return "
             "(order, sims) with sims in E's own order.")
def _():
    (f,) = functions("retrieval", "rank")
    q = [0.3, -1.2, 2.0, 0.5]
    E = [[1.0, 0.0, 0.0, 0.0], [0.6, -2.4, 4.0, 1.0], [-0.3, 1.2, -2.0, -0.5], [0.0, 0.0, 3.0, 0.0],
         [2.0, 1.0, 0.5, -1.0], [0.0, 0.0, 3.0, 0.0]]
    v = go(f, q, E)
    if not isinstance(v, tuple) or len(v) != 2:
        raise CheckFailed(f"rank() must return two arrays (order, sims), got {type(v).__name__}")
    order = [int(x) for x in np.asarray(v[0]).ravel()]
    sims = arr(v[1], "rank's sims", (6,))
    want_s = [0.124784, 1.0, -1.0, 0.83189, -0.016638, 0.83189]
    if np.allclose(sims, np.asarray(E) @ np.asarray(q), atol=1e-4):
        raise CheckFailed("rank's sims are dot products: a cosine divides by the lengths of the row AND of q")
    if np.allclose(sorted(sims, reverse=True), sorted(want_s, reverse=True), atol=1e-5) and \
            not np.allclose(sims, want_s, atol=1e-5):
        raise CheckFailed("rank's sims are sorted: they must stay in E's own order (sims[i] belongs to row i)")
    c.ok(np.allclose(sims, want_s, atol=1e-5), f"sims {np.round(sims, 5).tolist()}: expected the cosine of q with each row")
    if order == [2, 4, 0, 3, 5, 1] or order == [2, 4, 0, 5, 3, 1]:
        raise CheckFailed("the order is the LEAST similar first: largest similarity first")
    if order == [1, 5, 3, 0, 4, 2]:
        raise CheckFailed("rows 3 and 5 have the same similarity: the lower index comes first (kind=\"stable\")")
    c.ok(order == [1, 3, 5, 0, 4, 2], f"order {order}: expected the rows from the most to the least similar")


EVALS = [([12.0, 3.5, None, 410.0, 7.25, None, 64.0, 1.0], 50.0,
          {"n": 8, "accepted": 6, "availability": 0.75, "median_m": 9.625, "p90_m": 237.0, "within_300": 5 / 6,
           "wrong": 2}),
         ([12.0, 3.5, None, 410.0, 7.25, None, 64.0, 1.0], 10.0,
          {"n": 8, "accepted": 6, "availability": 0.75, "median_m": 9.625, "p90_m": 237.0, "within_300": 5 / 6,
           "wrong": 3}),
         ([300.0, 301.0, 55.0, 50.0], 50.0,
          {"n": 4, "accepted": 4, "availability": 1.0, "median_m": 177.5, "p90_m": 300.7, "within_300": 0.75,
           "wrong": 3}),
         ([None, None], 50.0,
          {"n": 2, "accepted": 0, "availability": 0.0, "median_m": None, "p90_m": None, "within_300": None, "wrong": 0})]


@c.test("TODO 3: evaluate() on unseen error lists — refusals, linear percentiles, ≤ 300 m, wrong, nothing accepted",
        hint="Lesson §4: keep the errors that are not None; availability = kept / all; np.percentile(kept, 50) and 90 "
             "(linear); within_300 = share of kept ≤ 300; wrong = kept > wrong_m; None for the statistics when nothing "
             "is kept; ValueError for an empty list.")
def _():
    (f,) = functions("locate", "evaluate")
    for errs, wm, want in EVALS:
        got = go(f, errs, wrong_m=wm)
        if not isinstance(got, dict):
            raise CheckFailed(f"evaluate() must return a dict, got {type(got).__name__}")
        miss = [k for k in want if k not in got]
        if miss:
            raise CheckFailed(f"evaluate()'s dict has no key {miss[0]!r} (keys: n, accepted, availability, median_m, "
                              "p90_m, within_300, wrong)")
        for k, w in want.items():
            g = got[k]
            if w is None:
                c.ok(g is None, f"evaluate({errs}): {k} = {g!r}, expected None when nothing was accepted")
                continue
            if g is None:
                raise CheckFailed(f"evaluate({errs}): {k} is None, expected a number")
            if k == "p90_m" and errs[0] == 12.0 and min(abs(float(g) - 410.0), abs(float(g) - 64.0)) < 1e-6:
                raise CheckFailed(f"p90 = {float(g):g} is one of the samples (a nearest-rank rule): the course's percentiles are LINEAR "
                                  "(np.percentile)")
            if k == "availability" and abs(float(g) - 1.0) < 1e-9 and w != 1.0:
                raise CheckFailed("availability counts the refused photos too: accepted / ALL photos")
            if k == "wrong" and wm != 50.0 and int(g) == 2:
                raise CheckFailed("evaluate ignores wrong_m: the threshold is an argument (50 m by default)")
            if k == "within_300" and abs(float(g) - 5 / 8) < 1e-9:
                raise CheckFailed("within_300 is a share of the ACCEPTED errors (not of all photos)")
            c.ok(abs(float(g) - w) < 1e-6, f"evaluate({errs}, wrong_m={wm}): {k} = {g!r}, expected {round(w, 6)}")
    try:
        run(f, [], seconds=10)
        raise CheckFailed("evaluate([]) should raise ValueError (no photo at all), it returned a result")
    except CheckFailed as e:
        if "ValueError" not in str(e) and "should raise" not in str(e):
            raise CheckFailed(f"evaluate([]) should raise ValueError: {e}")
        if "should raise" in str(e):
            raise


# ---------------------------------------------------------------- the lab's numbers (reference, recomputed)
REF = {"P90_DINO": 559.0, "P90_PRIOR": 442.0, "MED_DINO": 181.0, "MED_PRIOR": 246.0, "MED_RANDOM": 457.0, "MED_BEST": 103.0, "MED_DINO_800": 559.0,
       "MED_PRIOR_800": 816.0, "MED_DINO_400": 240.0}
TOL = {"P90_DINO": 15.0, "P90_PRIOR": 1.0, "MED_DINO": 8.0, "MED_PRIOR": 1.0, "MED_RANDOM": 1.0, "MED_BEST": 1.0, "MED_DINO_800": 25.0,
       "MED_PRIOR_800": 1.0, "MED_DINO_400": 12.0}


@c.test("Steps 0–6: DINOv2's patches, retrieval against the baselines, a worse prior, failures",
        hint="Copy the medians printed by `python3 run_locate.py retrieve` (σ 200 m), `retrieve --sigma 800` and "
             "`retrieve --sigma 400` (no decimals), then explain in your own words.")
def _():
    (pl, npatch, pd, md, mp, mr, mb, p9d, p9p, why_b, md8, mp8, why_s, worst, why_sc, md4) = answers(
        "PREDICT_LOOK", "N_PATCHES", "PREDICT_DINO", "MED_DINO", "MED_PRIOR", "MED_RANDOM", "MED_BEST", "P90_DINO",
        "P90_PRIOR", "EXPLAIN_BASELINE", "MED_DINO_800", "MED_PRIOR_800", "EXPLAIN_SIGMA", "WORST_TERRAIN", "EXPLAIN_SCORE",
        "MED_DINO_400")
    predicted("PREDICT_LOOK", pl)
    n = number(npatch, "N_PATCHES")
    if n == 16:
        raise CheckFailed("N_PATCHES = 16 is the patches on ONE side: 224 / 14 = 16 per side, and the picture is square")
    c.eq(int(n), 256, "N_PATCHES")
    predicted("PREDICT_DINO", pd)
    vals = {"MED_DINO": md, "MED_PRIOR": mp, "MED_RANDOM": mr, "MED_BEST": mb, "MED_DINO_800": md8,
            "MED_PRIOR_800": mp8, "MED_DINO_400": md4, "P90_DINO": p9d, "P90_PRIOR": p9p}
    got = {k: number(v, k) for k, v in vals.items()}
    if abs(got["MED_DINO"] - REF["MED_PRIOR"]) < 1 and abs(got["MED_PRIOR"] - REF["MED_DINO"]) < 9:
        raise CheckFailed("MED_DINO and MED_PRIOR are swapped: retrieval is the first line of the table")
    for k in vals:
        c.ok(abs(got[k] - REF[k]) <= TOL[k], f"{k} = {got[k]:g}: not the number `retrieve` prints for it (its median or p90 "
             "column; if your `test` is all ✔ for TODO 1–3, run `embed` and the three `retrieve` commands again)")
    explained("EXPLAIN_BASELINE", why_b,
              ((r"prior", r"stay", r"baseline", r"random"), "the comparison with the baselines"),
              ((r"p90", r"tail", r"far wrong", r"worst", r"when it is wrong", r"when wrong", r"large error", r"300"),
               "what the p90 (or within 300 m) shows"),
              ((r"tile", r"centre", r"center", r"resolution", r"grid", r"size", r"limit", r"\b248", r"half"),
               "why even the best tile is not 0 m away"))
    explained("EXPLAIN_SIGMA", why_s,
              ((r"sigma", r"σ", r"prior", r"uncertain", r"circle", r"radius", r"large", r"lost", r"big"),
               "when the prior is poor (σ large)"),
              ((r"better", r"beat", r"worth", r"useful", r"help", r"gain", r"win", r"improve", r"smaller", r"less"),
               "what retrieval gains or not"))
    w = str(worst).strip().lower().strip(".")
    c.ok(w == "sea", f"WORST_TERRAIN = {worst!r}: the by-terrain lines of `retrieve` (largest median, best tile chosen 0 %)")
    explained("EXPLAIN_SCORE", why_sc,
              ((r"overlap", r"same range", r"also high", r"high", r"similar", r"cannot", r"can't", r"can not", r"no\b",
                r"not"), "whether the score separates right from wrong"),
              ((r"gate", r"check", r"refus", r"verif", r"independ", r"trust", r"confirm", r"local", r"fine", r"match"),
               "what a drone needs instead"))


def check_net():
    """TileNet as its docstring's rule specifies, built by the check (never the student's class)."""
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    torch.set_num_threads(2)

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
            self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
            self.conv3 = nn.Conv2d(64, 128, 3, padding=1)
            self.conv4 = nn.Conv2d(128, 128, 3, padding=1)
            self.fc = nn.Linear(128, 128)

        def forward(self, x):
            for conv in (self.conv1, self.conv2, self.conv3, self.conv4):
                x = F.max_pool2d(F.relu(conv(x)), 2)
            return F.normalize(self.fc(x.mean(dim=(2, 3))), dim=1)
    return Net()


def small_tensor(imgs):
    import torch
    x = torch.as_tensor(np.asarray(imgs).astype(np.float32)).permute(0, 3, 1, 2)
    x = x - x.mean(dim=(1, 2, 3), keepdim=True)
    return x / (x.std(dim=(1, 2, 3), keepdim=True) + 1e-3)


def embed_ref(net, imgs):
    import torch
    net.eval()
    with torch.no_grad():
        return np.concatenate([net(small_tensor(imgs[s:s + 128])).numpy() for s in range(0, len(imgs), 128)])


@c.test("TODO 4: TileNet — the five layers of the rule, their sizes, the forward pass in order, unit rows",
        hint="Lab Step 8: conv1 3 → 32, then each block doubles the maps until DIM, then keeps them (3 × 3, padding=1), each followed by ReLU "
             "and 2 × 2 max-pooling; then the mean over the width and height; fc to DIM; F.normalize(…, dim=1).")
def _():
    import torch
    R = module("navera_lite.retrieval")
    (cls,) = need(R, "TileNet")
    net = go(cls)
    keys = sorted(str(k) for k in net.state_dict().keys())
    want = sorted(f"{n}.{p}" for n in ("conv1", "conv2", "conv3", "conv4", "fc") for p in ("weight", "bias"))
    c.ok(keys == want, f"TileNet's parameters are {keys}; the check and Sim Lite need exactly {want} — the attribute "
         "names conv1 … conv4 and fc")
    n = sum(int(p.numel()) for p in net.parameters())
    if n == 503104:
        raise CheckFailed("TileNet has 503 104 parameters: fc takes 128 · 4 · 4 = 2 048 numbers — the rule averages "
                          "each map instead (one number per map)")
    c.ok(n == 257344, f"TileNet has {n} parameters: the sizes do not follow the rule (count them by hand: lab Step 8)")
    torch.manual_seed(23)
    ref = check_net()
    fd, path = tempfile.mkstemp(suffix=".pt")
    os.close(fd)
    try:
        torch.save(ref.state_dict(), path)
        mine = go(R.load_tilenet, path)
        probe = np.random.default_rng(4).integers(0, 256, (5, 64, 64, 3)).astype(np.uint8)
        got = arr(go(R.embed_tilenet, mine, probe), "embed_tilenet(your TileNet, 5 pictures)", (5, 128))
    finally:
        os.remove(path)
    norms = np.linalg.norm(got, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-4):
        raise CheckFailed(f"the embeddings have lengths {np.round(norms, 3).tolist()}: divide each row by its length at "
                          "the end (F.normalize(x, dim=1))")
    c.ok(np.allclose(got, embed_ref(ref, probe), atol=1e-4), "with the same weights, your forward() gives other "
         "embeddings than the rule: conv → ReLU → 2 × 2 max-pooling (four times; padding=1 in every conv), the mean over "
         "width and height, fc, then length 1")


ZA = [[0.598084, 0.168449, -0.555749, -0.552326], [0.808839, -0.107588, -0.052356, -0.575728],
      [0.977612, -0.162285, 0.131741, -0.024137], [0.500028, 0.600679, -0.363214, 0.507181],
      [0.363366, 0.015445, -0.572003, -0.735214], [-0.318858, 0.799711, 0.489253, -0.139369]]
ZP = [[0.555976, -0.160733, -0.152462, -0.801131], [-0.483351, -0.118341, 0.124634, -0.85839],
      [0.277017, 0.535386, 0.551134, 0.576954], [0.499388, 0.617491, -0.605703, -0.049393],
      [0.298567, -0.598789, -0.414682, -0.616724], [-0.669098, 0.24404, 0.701932, -0.006706]]


@c.test("TODO 5: info_nce() on unseen embeddings — rows pick their diagonal, the temperature, the mean, a gradient",
        hint="Lesson §6: logits = za @ zp.T / tau; the right answer of row i is i (torch.arange(len(za), "
             "device=za.device)); F.cross_entropy(logits, answers) gives the mean of −log(softmax). Torch operations only.")
def _():
    R = module("navera_lite.retrieval")
    (f,) = functions("retrieval", "info_nce")
    za = R.torch.tensor(ZA, requires_grad=True)
    zp = R.torch.tensor(ZP)
    out = go(f, za, zp, 0.1)
    if out is None:
        raise CheckFailed("info_nce returned None")
    v = float(out.detach())
    for bad, why in ((13.757504, "the SUM over the rows — the docstring asks for the mean"),
                     (1.575238, "each COLUMN picks its diagonal (za and zp swapped): row i is za[i] against every zp[j]"),
                     (1.463745, "the temperature is ignored: divide the similarities by tau"),
                     (1.934078, "the mean of both directions (rows and columns): the docstring asks for the rows only")):
        if abs(v - bad) < 1e-4:
            raise CheckFailed(f"info_nce = {v:.4f}: {why}")
    c.near(v, 2.292917, 1e-4, "info_nce on 6 unseen pairs (tau 0.1)")
    c.ok(bool(out.requires_grad), "the loss has no gradient: compute it with torch operations only (no .item(), numpy, "
         "float() or torch.tensor() of a result inside)")
    c.near(float(go(f, za, zp, 0.5).detach()), 1.346312, 1e-4, "info_nce with tau = 0.5 (use the tau argument)")
    c.near(float(go(f, za, zp, tau=1.0).detach()), 1.463745, 1e-4, "info_nce with tau = 1.0")


# ---------------------------------------------------------------- the student's trained network
NEED_400 = 380.0          # hidden test median (m) over land to pass; see TEACHER.md for the measured values
DINO_HIDDEN = 259.0       # DINOv2 on the same photos and priors (reference, for the message)


def weights_ok(path):
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) > 5_000_000:
        raise CheckFailed(f"{path} is larger than 5 MB: it should hold TileNet's weights only (about 1 MB)")
    return True


def run_log(name):
    path = os.path.join("logs", name + ".json")
    if not os.path.exists(path):
        raise CheckFailed(f"logs/{name}.json is missing: train {name} with `python3 run_locate.py train` (it writes the "
                          "weights and their log together)")
    if os.path.getsize(path) > 2_000_000:
        raise CheckFailed(f"logs/{name}.json is too large to be a training log")
    try:
        with open(path, encoding="utf-8") as fh:
            log = json.load(fh)
    except (OSError, ValueError):
        raise CheckFailed(f"logs/{name}.json is not readable JSON: train {name} again with the runner")
    if not isinstance(log, dict) or not isinstance(log.get("history"), list):
        raise CheckFailed(f"logs/{name}.json is not a training log: train {name} again with the runner")
    h = hashlib.sha256()
    with open(name, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    if log.get("sha256") != h.hexdigest():
        raise CheckFailed(f"{name} is not the file its log logs/{name}.json describes (its fingerprint differs): train "
                          "it yourself with the runner (copying weights is not training them)")
    if log.get("weights") != name:
        raise CheckFailed(f"logs/{name}.json describes {log.get('weights')!r}, not {name}: train {name} itself with "
                          "the runner (`--out " + name + "`)")
    me = os.environ.get("ACADEMY_STUDENT")
    if me and log.get("student") not in (None, "", me):
        raise CheckFailed(f"{name} and its log were not trained in your workspace: train your own (Step 9 / 10)")
    return log


def load_check_net(path):
    import torch
    net = check_net()
    try:
        sd = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"{path} cannot be read as weights ({type(e).__name__}): train it with the runner")
    try:
        net.load_state_dict(sd)
    except Exception as e:                                                  # noqa: BLE001
        raise CheckFailed(f"{path} does not fit TileNet's rule (fix TODO 4 first, then train again): "
                          f"{str(e).splitlines()[0][:160]}")
    return net


def hidden_queries():
    return json.loads(hidden("queries.json"))


def tiles64(xy):
    """The zoom-17 tiles xy from the course map, decoded and shrunk to 64 × 64 (INTER_AREA), as SmallTiles does."""
    import cv2
    db = sqlite3.connect(f"file:{MAP}?mode=ro", uri=True)
    out = {}
    try:
        for x, y in xy:
            row = db.execute("SELECT tile_data FROM tiles WHERE zoom_level=17 AND tile_column=? AND tile_row=?",
                             (int(x), 2 ** 17 - 1 - int(y))).fetchone()
            img = cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_COLOR) if row else None
            if img is None:
                img = np.full((256, 256, 3), 40, np.uint8)
            out[(int(x), int(y))] = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA)
    finally:
        db.close()
    return out


def hidden_median(net, Q):
    """Q: the hidden queries to use (a subset of queries.json, in its order); their views come from views64.npz."""
    views = np.load(io.BytesIO(hidden("views64.npz", text=False)))["views"]
    row = {q["id"]: i for i, q in enumerate(hidden_queries())}
    qe = embed_ref(net, views[[row[q["id"]] for q in Q]])
    allxy = sorted({tuple(t) for q in Q for t in q["cand400"]})
    imgs = tiles64(allxy)
    te = dict(zip(allxy, embed_ref(net, np.stack([imgs[t] for t in allxy]))))
    errs = []
    for q, e in zip(Q, qe):
        cand = [tuple(t) for t in q["cand400"]]
        j = int(np.argmax(np.stack([te[t] for t in cand]) @ e))
        errs.append(haversine(q["lat"], q["lon"], *tile_centre(*cand[j])))
    return float(np.median(errs)), errs


@c.test("Your trained TileNet: my_tiles.pt on 36 photos over land you never saw (priors of σ 400 m)",
        hint="Lab Step 9: `python3 run_locate.py train` (on the GPU) writes my_tiles.pt and logs/my_tiles.pt.json. Do not "
             "rename exp.pt into my_tiles.pt.")
def _():
    if not weights_ok("my_tiles.pt"):
        raise CheckFailed("my_tiles.pt is missing: train it (`python3 run_locate.py train`, Step 9)")
    log = run_log("my_tiles.pt")
    hist = log.get("history") or []
    c.ok(len(hist) >= 2 and hist[-1].get("train_loss", 9) < hist[0].get("train_loss", 0),
         "logs/my_tiles.pt.json shows no training whose loss went down: train my_tiles.pt again (Step 9)")
    net = load_check_net("my_tiles.pt")
    Q = [q for q in hidden_queries() if q["terrain"] != "sea"]          # over the sea every tile is alike
    m, errs = hidden_median(net, Q)
    prior = float(np.median([haversine(q["lat"], q["lon"], *q["priors"]["400"]) for q in Q]))
    print(f"  your network on {len(Q)} hidden photos over land (σ 400 m priors): median {m:.0f} m (stay at the prior: "
          f"{prior:.0f} m, DINOv2: {DINO_HIDDEN:.0f} m)")
    c.ok(m <= NEED_400, f"my_tiles.pt gives a median of {m:.0f} m on the hidden photos (staying at the prior: {prior:.0f} "
         f"m); it needs {NEED_400:.0f} m or less. Train it with the default settings, on the GPU (Step 9).")


EXP_KEYS = ("n_train", "epochs", "batch", "tau", "shift", "augment")


@c.test("Steps 7–11: your network's numbers, one experiment, the cost",
        hint="N_PARAMS: count each layer's weights and biases (lab Step 8). Copy MED_MINE_400 and EXP_MEDIAN from the "
             "last line of each `train`, MS_… from `speed`. The experiment changes ONE setting of my_tiles.pt's run.")
def _():
    (why_p, npar, mm4, pe, em, why_e, msd, msm, why_c) = answers(
        "EXPLAIN_PAIRS", "N_PARAMS", "MED_MINE_400", "PREDICT_EXPERIMENT", "EXP_MEDIAN", "EXPLAIN_EXPERIMENT",
        "MS_DINO", "MS_MINE", "EXPLAIN_CHOICE")
    explained("EXPLAIN_PAIRS", why_p,
              ((r"offset", r"anywhere", r"not cent", r"shift", r"inside", r"never cent", r"real photo", r"random place",
                r"position"), "why a view is not centred on its tile"),
              ((r"augment", r"invarian", r"ignore", r"robust", r"real", r"camera", r"photo", r"like", r"effect"),
               "what the effects teach"))
    n = number(npar, "N_PARAMS")
    if int(n) == 256864:
        raise CheckFailed("N_PARAMS = 256 864: the biases count too (one per filter, one per output of fc)")
    if int(n) == 503104:
        raise CheckFailed("N_PARAMS = 503 104 counts a flattening fc (2 048 inputs): the rule averages each map")
    c.eq(int(n), 257344, "N_PARAMS")
    if not weights_ok("my_tiles.pt"):
        raise CheckFailed("my_tiles.pt is missing (Step 9)")
    log = run_log("my_tiles.pt")
    logged = (log.get("retrieval_400") or {}).get("top1", {}).get("median_m")
    if logged is None:
        raise CheckFailed("logs/my_tiles.pt.json has no retrieval result: train my_tiles.pt again with the runner")
    c.ok(abs(number(mm4, "MED_MINE_400") - logged) <= 1.0, f"MED_MINE_400 = {mm4}, but the log of your my_tiles.pt says "
         f"{logged:.0f} m (the last line of `train`)")
    predicted("PREDICT_EXPERIMENT", pe)
    flags = sum(bool(re.search(k, str(pe).lower())) for k in (r"aug", r"shift", r"n.?train|pairs|2000|2 000", r"tau|τ|temperat"))
    c.ok(flags >= 3, "PREDICT_EXPERIMENT should RANK the four flags (no-augment, shift 0, n-train 2000, tau 0.5), most "
         "harmful first, before you train exp.pt (Step 10)")
    if not weights_ok("exp.pt"):
        raise CheckFailed("exp.pt is missing: Step 10 trains it with ONE flag and `--out exp.pt`")
    ex = run_log("exp.pt")
    diff = [k for k in EXP_KEYS if ex.get(k) != log.get(k)]
    if not diff:
        raise CheckFailed("exp.pt was trained with the same settings as my_tiles.pt: change ONE (Step 10's table)")
    c.ok(len(diff) == 1, f"exp.pt changes {', '.join(diff)} compared with my_tiles.pt: an experiment changes ONE setting "
         "(train both with the defaults, except one flag)")
    e_med = (ex.get("retrieval_400") or {}).get("top1", {}).get("median_m")
    c.ok(e_med is not None and abs(number(em, "EXP_MEDIAN") - e_med) <= 1.0,
         f"EXP_MEDIAN = {em}, but logs/exp.pt.json says {e_med} (the last line of its training)")
    explained("EXPLAIN_EXPERIMENT", why_e,
              ((r"augment", r"shift", r"cent", r"pair", r"data", r"tau", r"temperat", r"softmax", r"fewer", r"less"),
               "what you changed"),
              ((r"\d",), "by how much (a number)"),
              ((r"because", r"since", r"so\b", r"learn", r"invarian", r"overfit", r"memor", r"general", r"robust",
                r"offset", r"sharp", r"impostor", r"negative"), "why"))
    msd, msm = number(msd, "MS_DINO"), number(msm, "MS_MINE")
    c.ok(30 <= msd <= 30000 and 0.05 <= msm <= 2000, f"MS_DINO = {msd:g}, MS_MINE = {msm:g}: copy the milliseconds per "
         "photo printed by `speed`")
    c.ok(msd >= 5 * msm, f"MS_DINO ({msd:g} ms) should be many times MS_MINE ({msm:g} ms): did you swap them?")
    explained("EXPLAIN_CHOICE", why_c,
              ((r"accura", r"median", r"error", r"better", r"worse", r"\bm\b", r"metre", r"meter"), "accuracy"),
              ((r"time", r"ms\b", r"millisec", r"fast", r"slow", r"cpu", r"gpu", r"cost", r"memory", r"power", r"param",
                r"jetson"), "cost"))


c.milestone("finder", "TODO 1:", "TODO 2:", "TODO 3:", "Steps 0–6:", "TODO 4:", "TODO 5:", "Your trained", "Steps 7–11:",
            label="Finder")


# ======================================================================== session 2 — Locator
@c.test("TODO 6: search_radius() on unseen σ, other k and limits, impossible σ",
        hint="Lesson §5: min(max(k · σ, r_min_m), r_max_m), a float; σ negative, NaN or infinite → ValueError.")
def _():
    (f,) = functions("locate", "search_radius")
    for args, want in (((37.5,), 112.5), ((37.5, 2.0), 80.0), ((7.0, 3.0, 50.0), 50.0),
                       ((700.0, 3.0, 80.0, 1000.0), 1000.0), ((0.0,), 80.0), ((260.0, 2.5, 80.0, 1500.0), 650.0)):
        v = go(f, *args)
        if v is None or isinstance(v, bool):
            raise CheckFailed(f"search_radius{args} returned {v!r}")
        if args == (37.5, 2.0) and abs(float(v) - 112.5) < 1e-9:
            raise CheckFailed("search_radius(37.5, 2.0) = 112.5: use the k argument (3 is only the default)")
        c.ok(abs(float(v) - want) < 1e-9, f"search_radius{args} = {v!r}, expected {want}")
    for bad in (-1.0, float("nan"), float("inf")):
        try:
            run(f, bad, seconds=10)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise CheckFailed(f"search_radius({bad}) should raise ValueError: {e}")
        raise CheckFailed(f"search_radius({bad}) should raise ValueError (an impossible σ), it returned a radius")


A_PL = [[0.97, -0.21, 412.3], [0.21, 0.97, 377.9]]


@c.test("TODO 7: place() on unseen fits — the two gates and their reasons, the centre, the half pixel",
        hint="Lesson §7: gate 1 (None or n < min_inliers), gate 2 (|hypot(A[0][0], A[1][0]) − 1| > scale_tol), then "
             "A @ ((w − 1)/2, (h − 1)/2, 1) and pixel_to_latlon(u + 0.5, v + 0.5, z, x0, y0); reasons as in the docstring.")
def _():
    (f,) = functions("locate", "place")
    v = go(f, np.array(A_PL), 23, (447, 447), 69391.2421875, 51553.71875)
    if not isinstance(v, tuple) or len(v) != 3:
        raise CheckFailed(f"place() must return (lat, lon, reason), got {v!r:.80}")
    if v[0] is None:
        raise CheckFailed(f"place() refused a good fit (23 inliers, scale 0.99): {v[2]!r}")
    if abs(v[0] - 35.808407749) < 2e-7 and abs(v[1] - 10.594980741) < 2e-7:
        raise CheckFailed("the position is 0.7 m off: OpenCV's pixel centres need + 0.5 before pixel_to_latlon (lesson §7)")
    c.ok(abs(v[0] - 35.808403399) < 2e-8 and abs(v[1] - 10.594986105) < 2e-8,
         f"an unseen fit gives ({v[0]:.7f}, {v[1]:.7f}): expected another point — the centre ((w − 1)/2, (h − 1)/2) "
         "through A, then pixel_to_latlon with the patch's origin")
    c.ok(str(v[2]).startswith("ok") and "23" in str(v[2]) and "0.99" in str(v[2]),
         f"the reason of an accepted fit should be 'ok: 23 inliers, scale 0.99', got {v[2]!r}")
    v = go(f, np.array(A_PL), 23, (447, 447, 3), 69391.2421875, 51553.71875)
    c.ok(v[0] is not None and abs(v[0] - 35.808403399) < 2e-8, "a view_shape (h, w, 3) must give the same answer "
         "(h, w = view_shape[:2])")
    v = go(f, np.array(A_PL), 23, (447, 447), 2 * 69391.2421875, 2 * 51553.71875, z=18)
    c.ok(v[0] is not None and abs(v[0] - 35.811194321) < 2e-8 and abs(v[1] - 10.591862512) < 2e-8,
         "with z=18 the answer is wrong: use the zoom argument")
    big = np.array([[1.2, 0.0, 10.0], [0.0, 1.2, 10.0]])
    v = go(f, big, 40, (101, 101), 69391.0, 51553.0)
    c.ok(v[0] is None and v[1] is None and "scale" in str(v[2]) and "1.20" in str(v[2]),
         f"a fit of scale 1.20 must be refused with 'scale 1.20 (expected 1 ± 0.15)', got {v!r}")
    v = go(f, big, 40, (101, 101), 69391.0, 51553.0, scale_tol=0.25)
    c.ok(v[0] is not None and abs(v[0] - 35.814972617) < 2e-8, "with scale_tol=0.25 a scale of 1.20 passes: use the "
         "scale_tol argument")
    v = go(f, np.array(A_PL), 5, (447, 447), 69391.0, 51553.0)
    c.ok(v[0] is None and "5 inliers" in str(v[2]) and "6" in str(v[2]),
         f"5 inliers must be refused with '5 inliers (min 6)', got {v!r}")
    v = go(f, np.array(A_PL), 5, (447, 447), 69391.0, 51553.0, min_inliers=4)
    c.ok(v[0] is not None and abs(v[0] - 35.810004339) < 2e-8, "with min_inliers=4, 5 inliers pass: use the argument")
    v = go(f, None, 2, (447, 447), 69391.0, 51553.0)
    c.ok(isinstance(v, tuple) and len(v) == 3 and v[0] is None and "inlier" in str(v[2]),
         f"A = None must give (None, None, '2 inliers (min 6)'), got {v!r}")


# ---------------------------------------------------------------- TODO 8 on hidden photos
GOOD = ["h02", "h03", "h11", "h31", "h34"]      # textured, accepted by the reference at σ 40 m and σ 400 m (< 10 m)
LATER = ["h33", "h37"]                          # the finder's first tile is wrong; the 2nd / 3rd one is found (< 5 m)
SEA = "h08"
FAR = "h14"                                     # the right tile is found, but 1 214 m from a prior whose circle is 1 200 m
CFG = {"z": 17, "k_sigma": 3.0, "r_min_m": 80.0, "r_max_m": 1500.0, "direct_max_r_m": 300.0, "top_k": 3,
       "tile_r_m": 180.0, "ratio": 0.9, "min_inliers": 6, "scale_tol": 0.15, "max_patch_px": 2000}


def photo(q):
    import cv2
    return cv2.imdecode(np.frombuffer(hidden(q["id"] + ".jpg", text=False), np.uint8), cv2.IMREAD_COLOR)


def meta(q):
    return {"alt_m": q["alt_m"], "heading_deg": q["heading_deg"], "hfov_deg": q["hfov_deg"]}


@c.test("TODO 8: locate() on hidden photos — the fine step alone for small circles, the finder for large ones, refusals",
        hint="Lesson §8 and the docstring: r from search_radius; r ≤ cfg['direct_max_r_m'] → one local_match around the "
             "prior (no finder); otherwise ONE finder call, then local_match around each candidate's (lat, lon) "
             "(cand[2], cand[3]) with cfg['tile_r_m'], the first accepted; at the end refuse a position farther than r.")
def _():
    (f,) = functions("locate", "locate")
    Q = {q["id"]: q for q in hidden_queries()}
    calls = []

    def finder(view, lat, lon, r_m, k):
        calls.append((round(float(r_m), 1), int(k)))
        return [tuple(cnd) for cnd in finder.q["dino400"][:int(k)]]

    for pid in GOOD:
        q = Q[pid]
        finder.q = q
        calls.clear()
        v = go(f, photo(q), meta(q), (*q["priors"]["40"], 40.0), finder, CFG, seconds=90)
        if not isinstance(v, tuple) or len(v) != 3:
            raise CheckFailed(f"locate() must return (lat, lon, reason), got {v!r:.80}")
        c.ok(not calls, f"σ 40 m gives a 120 m circle (≤ direct_max_r_m = 300 m): the finder must NOT be called "
             f"(it was called {len(calls)} time(s))")
        c.ok(v[0] is not None, f"a hidden textured photo with a σ 40 m prior was refused: {v[2]!r} (the fine step "
             "around the prior with the radius r finds it: local_match(photo, meta, prior_lat, prior_lon, r, cfg))")
        err = haversine(q["lat"], q["lon"], v[0], v[1])
        c.ok(err < 15.0, f"a hidden photo placed {err:.0f} m from the truth with a σ 40 m prior (the fine step gives "
             "< 10 m here): is the position the one local_match returned?")
    for pid in GOOD[:3]:
        q = Q[pid]
        finder.q = q
        calls.clear()
        v = go(f, photo(q), meta(q), (*q["priors"]["400"], 400.0), finder, CFG, seconds=120)
        c.ok(len(calls) == 1, f"σ 400 m gives a 1 200 m circle: the finder must be called exactly once (it was called "
             f"{len(calls)} times)")
        c.ok(calls[0] == (1200.0, 3), f"the finder was called with r_m, k = {calls[0]}: expected (1200.0, 3) — the "
             "search radius and cfg['top_k']")
        c.ok(v[0] is not None and haversine(q["lat"], q["lon"], v[0], v[1]) < 15.0,
             f"with a σ 400 m prior and the finder's 3 candidates, a hidden textured photo gave {v!r:.90}: try "
             "local_match around EACH candidate's (lat, lon) = (cand[2], cand[3]) with cfg['tile_r_m'], keep the first "
             "accepted one")
    for pid in LATER:
        q = Q[pid]
        finder.q = q
        v = go(f, photo(q), meta(q), (*q["priors"]["400"], 400.0), finder, CFG, seconds=120)
        c.ok(v[0] is not None and haversine(q["lat"], q["lon"], v[0], v[1]) < 15.0,
             f"a hidden photo whose FIRST candidate is a wrong tile was refused ({v[2]!r}): when the fine step refuses "
             "a candidate, try the next one (up to k), and keep the first accepted position")
    q = Q[GOOD[3]]
    finder.q = q
    calls.clear()
    cfg = dict(CFG, direct_max_r_m=100.0)
    v = go(f, photo(q), meta(q), (*q["priors"]["40"], 40.0), finder, cfg, seconds=90)
    c.ok(len(calls) == 1 and v[0] is not None, "with cfg['direct_max_r_m'] = 100 m, a 120 m circle must use the finder: "
         "read the threshold from cfg, not a fixed 300")
    q = Q[SEA]
    finder.q = q
    v = go(f, photo(q), meta(q), (*q["priors"]["400"], 400.0), finder, CFG, seconds=120)
    c.ok(v[0] is None and v[1] is None and isinstance(v[2], str) and v[2] != "",
         f"a photo of the open sea must be refused with a reason, got {v!r:.90}")
    q = Q[FAR]
    finder.q = q
    v = go(f, photo(q), meta(q), (*q["priors"]["400"], 400.0), finder, CFG, seconds=120)
    c.ok(v[0] is None and "outside" in str(v[2]),
         f"the fine step found this photo 1 214 m from a prior whose circle is 1 200 m: refuse it with \"outside the "
         f"search circle (…)\" (the docstring's last rule) — this fix was actually right: that is the price of the 3σ "
         f"rule (lesson §8). Got {v!r:.90}")


@c.test("TODO 9: budget() on unseen terms — root sum of squares, a dict or a list, impossible σ",
        hint="Lesson §9: the square root of the sum of the squares of the values (dict: its values); empty → 0.0; a "
             "negative or non-finite σ → ValueError.")
def _():
    (f,) = functions("locate", "budget")
    v = go(f, {"a": 1.5, "b": 2.0, "c": 6.0})
    if v is not None and abs(float(v) - 9.5) < 1e-9:
        raise CheckFailed("budget = 9.5 is the plain sum: independent errors add as squares (lesson §9)")
    c.near(float(v), 6.5, 1e-9, "budget({a: 1.5, b: 2.0, c: 6.0})")
    c.near(float(go(f, [0.3, 0.4])), 0.5, 1e-9, "budget([0.3, 0.4]) (a list of σ)")
    c.near(float(go(f, {})), 0.0, 1e-12, "budget({})")
    for bad in ({"x": -1.0}, {"x": float("nan")}):
        try:
            run(f, bad, seconds=10)
        except CheckFailed as e:
            if "ValueError" in str(e):
                continue
            raise CheckFailed(f"budget({bad}) should raise ValueError: {e}")
        raise CheckFailed(f"budget({bad}) should raise ValueError (an impossible σ)")


LOCAL_P02 = 3.0           # `local p02` with the reference (lab Step 13)
BUDGET = 5.16


@c.test("Steps 13–16: the fine step on p02, your rule, the budget, the whole chain",
        hint="Copy LOCAL_ERR_P02 from `local p02`, BUDGET_TOTAL from `budget`, the four numbers from your last `run`; "
             "DIRECT_MAX_R_M from YOUR reading of `sweep`; explain in your own words.")
def _():
    (le, ps, dm, why_d, bt, fa, fm, fp, fw, why_r) = answers(
        "LOCAL_ERR_P02", "PREDICT_SWEEP", "DIRECT_MAX_R_M", "EXPLAIN_DECISION", "BUDGET_TOTAL", "FINAL_AVAIL",
        "FINAL_MEDIAN", "FINAL_P90", "FINAL_WRONG", "EXPLAIN_REFUSED")
    le = number(le, "LOCAL_ERR_P02")
    c.ok(abs(le - LOCAL_P02) <= 0.3, f"LOCAL_ERR_P02 = {le:g}: not the error `local p02` prints (one decimal)")
    predicted("PREDICT_SWEEP", ps)
    dm = number(dm, "DIRECT_MAX_R_M")
    if dm >= 727:
        raise CheckFailed(f"DIRECT_MAX_R_M = {dm:g} m: above about 727 m the patch of the whole circle is wider than "
                          "2 000 px — the sweep's σ 400 m line, 'fine only', gives nothing")
    c.ok(150 <= dm < 600, f"DIRECT_MAX_R_M = {dm:g} m: read the sweep again — where does 'fine only' stop giving as many "
         "positions as 'retrieval', and where does it still work at all? (the radii were 150, 300, 600 and 1 200 m)")
    explained("EXPLAIN_DECISION", why_d,
              ((r"\d",), "numbers from the sweep"),
              ((r"availab", r"accepted", r"position", r"\d+ ?/ ?20", r"found", r"fix"), "how many positions each way gives"),
              ((r"time", r"second", r"\bs\b", r"cost", r"memory", r"patch", r"slow", r"fast", r"large", r"circle"),
               "the cost of a large circle"))
    c.near(number(bt, "BUDGET_TOTAL"), BUDGET, 0.01, "BUDGET_TOTAL (the total `budget` prints)")
    path = os.path.join("out", "run_csv.json")
    if not os.path.exists(path):
        raise CheckFailed("out/run_csv.json is missing: run `python3 run_locate.py run` (Step 16) after you set "
                          "DIRECT_MAX_R_M")
    try:
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
    except (OSError, ValueError):
        raise CheckFailed("out/run_csv.json is not readable: run `python3 run_locate.py run` again")
    c.ok(abs(float(r.get("direct_max_r_m", -1)) - dm) < 1e-6, f"your last `run` used direct_max_r_m = "
         f"{r.get('direct_max_r_m')}, but DIRECT_MAX_R_M = {dm:g}: save answers.py, then run `run` again")
    for name, val, key, tol in (("FINAL_AVAIL", fa, "availability", 0.006), ("FINAL_MEDIAN", fm, "median_m", 0.06),
                                ("FINAL_P90", fp, "p90_m", 0.06), ("FINAL_WRONG", fw, "wrong", 0.0)):
        want = r.get(key)
        if want is None:
            raise CheckFailed(f"your last `run` gave no {key}: did it accept any photo?")
        c.ok(abs(number(val, name) - float(want)) <= tol, f"{name} = {val}, but your last `run` printed {want:.3g}")
    c.ok(float(r["availability"]) >= 0.45 and int(r["wrong"]) <= 1 and float(r["median_m"]) <= 10.0,
         f"your chain gives availability {r['availability']:.2f}, median {r['median_m']:.1f} m, {r['wrong']} wrong: the "
         "reference gives about 0.6, 3.5 m, 0 — check locate() (Step 14) and your rule")
    explained("EXPLAIN_REFUSED", why_r,
              ((r"p\d\d",), "which photo"),
              ((r"inlier", r"scale", r"outside", r"circle", r"gate", r"patch", r"candidate"), "which gate refused it"),
              ((r"sea", r"water", r"uniform", r"feature", r"wrong", r"look", r"trust", r"safe", r"better", r"no fix",
                r"empty", r"field"), "why refusing was right"))


c.milestone("locator", "TODO", "Step", "Your trained", label="Locator")

c.run()
