"""run_locate.py — runs YOUR functions of navera_lite/retrieval.py and navera_lite/locate.py on the lab's photos, and
draws the results.

  python3 run_locate.py test              check each function on its docstring example (and name the symptom)
  Session 1 — Finder
    python3 run_locate.py look              one photo, its north-up view and the map tiles around it        (Step 0)
    python3 run_locate.py embed             DINOv2 embeddings of the 80 photos, with YOUR preprocess        (Step 2)
    python3 run_locate.py retrieve          retrieval vs two baselines, on the 80 photos                    (Step 4)
          options:  --finder dino|mine (default dino)  --sigma S (default: the 200 m priors of photos.csv)
                    --weights FILE (default my_tiles.pt, for --finder mine)
    python3 run_locate.py pairs             look at training pairs made from the map                        (Step 7)
    python3 run_locate.py train             train YOUR TileNet and save it in my_tiles.pt                   (Step 9)
          options:  --n-train N (default 8000)  --epochs E (default 12)  --batch B (64)  --tau T (0.1)
                    --shift S (0.5)  --no-augment  --out FILE (my_tiles.pt)  --device cpu
    python3 run_locate.py speed             time per photo: DINOv2 vs your TileNet, on the CPU              (Step 11)
  Session 2 — Locator
    python3 run_locate.py local pNN         the fine step on one photo, around its prior                    (Step 13)
          option:   --sigma S (default 50)
    python3 run_locate.py sweep             fine step alone vs retrieval first, for four prior σ             (Step 14)
    python3 run_locate.py budget            YOUR error budget, next to the measured errors                  (Step 15)
    python3 run_locate.py run               YOUR locate() on the 80 photos: the four numbers                 (Step 16)
          options:  --sigma S (default: the 200 m priors)  --finder dino|mine (default mine)

Training and DINOv2 use the shared GPU (academy_gpu: at most 3 jobs in the class; the runner waits for a free slot,
or uses the CPU). Every training writes logs/<FILE>.json: its settings, its curves, its retrieval result and the
SHA-256 fingerprint of the weights it saved — the check compares it with your weights file.
Pictures are saved in out/ — click them in the file list of the 📝 Code tab. Map data © OpenStreetMap contributors.
"""
import contextlib
import csv
import json
import math
import os
import sys
import time

import cv2
import numpy as np

import runner_kit as rk
from academy_gpu import limit_threads, torch_device

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = "/data/academy/23-locate-on-map"
OUT = "out"
LOGS = "logs"
SWEEP_SIGMAS = (50.0, 100.0, 200.0, 400.0)
SWEEP_PHOTOS = 20            # the first 20 photos (13 textured, 4 sparse, 3 sea) keep the sweep near 5 minutes
_kit_hint = rk._hint


def _hint(e):
    s = str(e)
    if "mat1 and mat2 shapes cannot be multiplied" in s:
        return (" — the Linear layer got the wrong number of inputs: after the global average pooling there is ONE "
                "number per map of conv4 (lab Step 8)")
    if "Expected 4D" in s or "Expected 3D (unbatched) or 4D" in s:
        return " — a Conv2d wants (N, 3, 64, 64): use the tensors of tile_tensor(), not the uint8 pictures"
    if "does not require grad" in s:
        return " — the loss has no gradient: torch operations only (no .item(), no numpy, no torch.tensor of a result)"
    if "cannot assign module before Module.__init__()" in s:
        return " — write super().__init__() as the FIRST line of TileNet.__init__"
    if "same device" in s:
        return " — the model and the tensors must be on the same device: the targets too (device=za.device)"
    if "Expected floating point type for target" in s or "expected scalar type Long" in s:
        return " — cross_entropy wants the right answers as whole numbers (torch.arange gives them)"
    return _kit_hint(e)


rk._hint = _hint
os.environ.setdefault("NAVERA_LITE_MODELS", "/data/models")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")   # less GPU memory kept in reserve


def retr():
    return rk.load_student("navera_lite.retrieval")


def loc():
    return rk.load_student("navera_lite.locate")


def stamp(img):
    """(c) OpenStreetMap contributors in the corner of a saved map picture (the licence asks for it)."""
    text = "(c) OpenStreetMap contributors"
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
    H, W = img.shape[:2]
    cv2.rectangle(img, (W - w - 9, H - h - 9), (W - 1, H - 1), (255, 255, 255), -1)
    cv2.putText(img, text, (W - w - 6, H - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
    return img


def label(img, text):
    cv2.rectangle(img, (0, 0), (8 * len(text) + 8, 18), (255, 255, 255), -1)
    cv2.putText(img, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
    return img


def close(got, want, tol):
    try:
        g = np.asarray(got, dtype=float)
        return g.shape == np.shape(want) and bool(np.all(np.abs(g - np.asarray(want, dtype=float)) <= tol))
    except (TypeError, ValueError):
        return False


def show(v):
    if v is None:
        return "None"
    if isinstance(v, (str, dict)):
        return str(v)
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return repr(v)
    if a.ndim == 0:
        return f"{float(a):.6g}"
    return np.array2string(a, precision=4, suppress_small=True, separator=", ").replace("\n", "")


# ================================================================================================= data
def photos():
    """The lab's photos: a list of dicts (id, meta, prior, terrain, truth)."""
    path = os.path.join(DATA, "photos.csv")
    if not os.path.exists(path):
        sys.exit(f"cannot read {path} — is the data folder mounted? (ls {DATA})")
    truth = {r["id"]: r for r in csv.DictReader(open(os.path.join(DATA, "truth.csv")))}
    out = []
    for r in csv.DictReader(open(path)):
        out.append({"id": r["id"], "terrain": r["terrain"],
                    "meta": {"alt_m": float(r["alt_m"]), "heading_deg": float(r["heading_deg"]),
                             "hfov_deg": float(r["hfov_deg"])},
                    "prior": (float(r["prior_lat"]), float(r["prior_lon"]), float(r["prior_sigma_m"])),
                    "truth": (float(truth[r["id"]]["lat"]), float(truth[r["id"]]["lon"]))})
    return out


def image(pid):
    img = cv2.imread(os.path.join(DATA, "photos", f"{pid}.jpg"))
    if img is None:
        sys.exit(f"cannot read {DATA}/photos/{pid}.jpg")
    return img


def prior_at(p, sigma):
    """A prior of σ `sigma` for photo p: the truth moved by a 2-D Gaussian draw (the same draw for every student)."""
    if sigma is None:
        return p["prior"]
    from navera_lite.geo import offset
    rng = np.random.default_rng(int(p["id"][1:]) * 1000 + int(sigma))
    e, n = rng.normal(0, sigma, 2)
    lat, lon = offset(p["truth"][0], p["truth"][1], float(e), float(n))
    return lat, lon, float(sigma)


def view(R, p, img=None):
    """The north-up colour view of photo p at the map's scale (given north_up)."""
    from navera_lite.camera import gsd
    from navera_lite.tiles import m_per_px
    img = image(p["id"]) if img is None else img
    m = p["meta"]
    return R.north_up(img, m["heading_deg"], gsd(m["alt_m"], m["hfov_deg"], img.shape[1]), m_per_px(p["prior"][0], 17))


def dist(a, b):
    from navera_lite.geo import haversine_m
    return haversine_m(a[0], a[1], b[0], b[1])


def table(rows, cols):
    w = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(cols)))
    for r in rows:
        print("  ".join(str(v).ljust(w[i]) for i, v in enumerate(r)))


def fmt(v, nd=0):
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


# ================================================================================================= test
def tilenet_problem(net):
    """None if the four blocks give (1, 128, 4, 4) on a 64 × 64 picture as the rule says, else one sentence."""
    import torch
    import torch.nn.functional as F
    try:
        y = torch.randn(1, 3, 64, 64)
        with torch.no_grad():
            for c in (net.conv1, net.conv2, net.conv3, net.conv4):
                y = F.max_pool2d(F.relu(c(y)), 2)
    except Exception as ex:                                              # noqa: BLE001
        return f"the four blocks stop with {type(ex).__name__}: {ex}"
    if tuple(y.shape) != (1, 128, 4, 4):
        return (f"after conv4 the maps are {tuple(y.shape)}, the rule gives (1, 128, 4, 4): padding=1 keeps the width "
                "and height, each pooling halves them (lab Step 8, hint 1)")
    n = sum(p.numel() for p in net.parameters())
    if n != 257344:
        return f"{n} parameters: the sizes do NOT follow the rule (count yours by hand: lab Step 8)"
    return None


def test():
    import torch
    limit_threads()
    R, L = retr(), loc()
    print("TODO  function          result")
    ok_all = True

    def line(todo, name, got, err, good, note):
        nonlocal ok_all
        if err:
            print(f"✘ {todo:<4} {name:16s} {err}")
            ok_all = False
        elif good:
            print(f"✔ {todo:<4} {name:16s} {show(got)}")
        else:
            print(f"✘ {todo:<4} {name:16s} got {show(got)} — {note}")
            ok_all = False

    z = np.zeros((2, 256, 256, 3), np.uint8)
    z[1, :128, :, 2] = 255                                               # picture 1: top half pure RED (BGR order) …
    z[1, 128:, :, 1] = 255                                               # … bottom half pure GREEN
    v, e = rk.call(R, "preprocess", z)
    if not e:
        try:
            t = v.detach().cpu().numpy() if hasattr(v, "detach") else np.asarray(v)
        except Exception:                                                # noqa: BLE001
            t = np.asarray([])
        red, green = [2.2489, -2.0357, -1.8044], [-2.1179, 2.4286, -1.8044]
        want = [-2.1179] + red + green
        ok_shape = t.shape == (2, 3, 224, 224)
        got = ([float(t[0, 0, 0, 0])] + [float(t[1, k, 5, 5]) for k in range(3)]
               + [float(t[1, k, 200, 5]) for k in range(3)]) if ok_shape else None
        note = "the docstring: shape (2, 3, 224, 224); a red pixel gives (2.2489, −2.0357, −1.8044). "
        if not ok_shape:
            note += f"Your shape is {t.shape}: channels first, size × size (lab Step 1, hint 4)"
        elif max(abs(x) for x in got) > 100 and got[3] > 100:
            note += ("Values of hundreds AND red in channel 2: reverse the channels and divide by 255 "
                     "(lab Step 1, hints 2 and 3)")
        elif max(abs(x) for x in got) > 100:
            note += "Values of hundreds: scale 0..255 to 0..1 first (lab Step 1, hint 3)"
        elif close(got[1], -2.1179, 1e-3) and close(got[3], (1 - 0.406) / 0.225, 1e-3):
            note += "Red ended up in channel 2: OpenCV gives BGR, DINOv2 wants RGB (lab Step 1, hint 2)"
        elif close(sorted(float(t[1, 0, 5, k]) for k in range(3)), sorted(red), 2e-3):
            note += ("Red, green and blue follow each other along a ROW: reshape(3, size, size) mixes pixels and "
                     "channels; move the axis with .transpose(2, 0, 1) (lab Step 1, hint 6)")
        line(1, "preprocess", got, None, got is not None and close(got, want, 2e-3), note)
    else:
        line(1, "preprocess", None, e, False, "")
    v, e = rk.call(R, "rank", [1.0, 0.0], [[0.0, 2.0], [3.0, 3.0], [5.0, 0.0]])
    good = not e and isinstance(v, tuple) and len(v) == 2 and close(v[0], [2, 1, 0], 0) and \
        close(v[1], [0.0, 0.70711, 1.0], 1e-4)
    note = "the docstring says (array([2, 1, 0]), array([0., 0.7071, 1.]))"
    if not e and isinstance(v, tuple) and len(v) == 2 and close(v[0], [0, 1, 2], 0):
        note += " — the order is the LEAST similar first: largest similarity first (hint 3)"
    elif not e and isinstance(v, tuple) and len(v) == 2 and close(v[1], [0.0, 3.0, 5.0], 1e-6):
        note += " — those are dot products: a cosine divides by both lengths (hint 2)"
    elif not e and isinstance(v, tuple) and len(v) == 2 and close(v[1], [1.0, 0.70711, 0.0], 1e-4):
        note += " — sims must stay in E's own order (not sorted)"
    line(2, "rank", v, e, good, note)
    v, e = rk.call(L, "evaluate", [4.0, None, 12.0, 80.0, 2.0])
    want = {"n": 5, "accepted": 4, "availability": 0.8, "median_m": 8.0, "p90_m": 59.6, "within_300": 1.0, "wrong": 1}
    good = not e and isinstance(v, dict) and all(k in v and v[k] is not None and abs(float(v[k]) - w) < 1e-6
                                                 for k, w in want.items())
    note = f"the docstring says {want}"
    if not e and isinstance(v, dict) and v.get("p90_m") is not None and abs(float(v["p90_m"]) - 80.0) < 1e-6:
        note += " — p90 = 80 is the nearest sample: the course's percentiles are LINEAR (np.percentile)"
    elif not e and isinstance(v, dict) and v.get("availability") == 1.0:
        note += " — availability counts the refused photos (None) too: accepted / ALL photos"
    line(3, "evaluate", v, e, good, note)

    v, e = rk.call(R, "TileNet")
    if not e:
        try:
            names = [n for n, _ in v.named_children()]
            out = v(torch.zeros(2, 3, 64, 64))
            norms = out.norm(dim=1).tolist()
            ok = names == ["conv1", "conv2", "conv3", "conv4", "fc"] and tuple(out.shape) == (2, 128) and \
                close(norms, [1.0, 1.0], 1e-4)
            got = f"layers {names}, output {tuple(out.shape)}, row lengths {[round(x, 3) for x in norms]}"
            problem = tilenet_problem(v) if ok else None
            if problem:
                ok, note = False, problem
            else:
                note = "the docstring: layers conv1..conv4, fc; output (2, 128); rows of length 1"
            line(4, "TileNet", got + (f", sizes follow the rule" if ok else ""), None, ok, note)
        except Exception as ex:                                          # noqa: BLE001
            line(4, "TileNet", None, f"TileNet stopped with {type(ex).__name__}: {ex}{_hint(ex)}", False, "")
    else:
        line(4, "TileNet", None, e, False, "")
    za = torch.tensor([[1.0, 0.0], [0.0, 1.0]], requires_grad=True)
    zp = torch.tensor([[0.8, 0.6], [0.6, 0.8]])
    v, e = rk.call(R, "info_nce", za, zp, tau=0.5)
    if not e:
        try:
            val = float(v.detach())
            grad = bool(v.requires_grad)
        except Exception:                                                # noqa: BLE001
            val, grad = None, False
        note = "the docstring says tensor(0.5130), with a gradient"
        if val is not None and abs(val - 0.5981) < 1e-3:
            note += " — 0.5981: the division by tau is missing (lab Step 9, hint 3)"
        elif val is not None and abs(val - 0.6444) < 1e-3:
            note += " — 0.6444: the similarities were MULTIPLIED by tau; they are divided by it"
        elif val is not None and abs(val - 1.0260) < 1e-3:
            note += " — 1.0260 is the SUM over the batch: the docstring asks for the mean"
        elif not grad:
            note += " — the loss lost its gradient (no .item(), numpy or torch.tensor of a result)"
        line(5, "info_nce", val, None, val is not None and abs(val - 0.5130) < 1e-3 and grad, note)
    else:
        line(5, "info_nce", None, e, False, "")

    for args, want in (((120.0,), 360.0), ((10.0,), 80.0), ((900.0,), 1500.0)):
        v, e = rk.call(L, "search_radius", *args)
        line(6, f"search_radius{args}", v, e, not e and close(v, want, 1e-9),
             f"the docstring says {want} (k·σ, then the two limits)")
    v, e = rk.call(L, "place", np.array([[1.0, 0.0, 100.0], [0.0, 1.0, 50.0]]), 20, (101, 101), 69408.0, 51546.0)
    want = (35.830300767, 10.636380315)
    good = not e and isinstance(v, tuple) and len(v) == 3 and v[0] is not None and \
        close(v[:2], want, 1e-8) and str(v[2]).startswith("ok")
    note = "the docstring says (35.83030…, 10.63638…, 'ok: 20 inliers, scale 1.00')"
    if not e and isinstance(v, tuple) and len(v) == 3 and v[0] is not None and close(v[:2], want, 1e-5):
        note += " — off by about half a metre: OpenCV's pixel centres vs the map's coordinates (+ 0.5, lab Step 13)"
    line(7, "place", v, e, good, note)
    v, e = rk.call(L, "place", None, 2, (101, 101), 69408.0, 51546.0)
    line(7, "place (no fit)", v, e, not e and isinstance(v, tuple) and len(v) == 3 and v[0] is None and
         "inlier" in str(v[2]), "A is None or too few inliers → (None, None, '<n> inliers (min 6)')")
    v, e = rk.call(L, "budget", {"tilt": 3.0, "matcher": 4.0})
    note = "the docstring says 5.0"
    if not e and close(v, 7.0, 1e-9):
        note += " — 7 is the plain sum: independent errors add as SQUARES (lesson §9)"
    line(9, "budget", v, e, not e and close(v, 5.0, 1e-9), note)
    print("(TODO 8 locate() is tried by `local`, `sweep` and `run`.)")
    print("\nAll the TODOs written so far give their docstring results." if ok_all else
          "\nSome lines are ✘: fix the first one (a TODO you have not reached yet is ✘ too: that is normal).")


# ================================================================================================= session 1
def look():
    import shutil
    from navera_lite.tiles import ATTRIBUTION, map_patch, tile_xy
    R = retr()
    p = next(q for q in photos() if q["terrain"] == "textured")
    img = image(p["id"])
    os.makedirs(OUT, exist_ok=True)
    nu = view(R, p, img)
    x, y = (int(v) for v in tile_xy(p["truth"][0], p["truth"][1], 17))
    tiles = np.vstack([np.hstack([map_patch(*R.tile_centre(x + i, y + j), 17, 256, 256) for i in (-1, 0, 1)])
                       for j in (-1, 0, 1)])
    for i in range(1, 3):
        cv2.line(tiles, (256 * i, 0), (256 * i, 767), (90, 90, 90), 1)
        cv2.line(tiles, (0, 256 * i), (767, 256 * i), (90, 90, 90), 1)
    left = np.full((768, 640, 3), 255, np.uint8)
    left[:480] = label(img.copy(), f"photo {p['id']} (heading {p['meta']['heading_deg']:.0f} deg)")
    left[500:756, 192:448] = label(nu.copy(), "north-up view")
    out = np.hstack([left, np.full((768, 12, 3), 255, np.uint8), label(stamp(tiles), "9 map tiles (zoom 17)")])
    cv2.imwrite(os.path.join(OUT, "look.png"), out)
    shutil.copy(os.path.join(DATA, "photos", f"{p['id']}.jpg"), os.path.join(OUT, f"{p['id']}.jpg"))
    print(f"saved {OUT}/look.png: photo {p['id']}, its north-up view (at the map's scale, 256 × 256 px ≈ 248 m) and "
          f"the 9 tiles around it. {ATTRIBUTION}.")
    print("Which tile holds the photo's centre? Write PREDICT_LOOK in answers.py before you go on.")


def embed():
    import torch
    R = retr()
    ps = photos()
    views = np.stack([view(R, p) for p in ps])
    _, e = rk.call(R, "preprocess", views[:1])
    if e:
        sys.exit(e)
    idx = np.load(os.path.join(DATA, "dino_index.npz"))
    from navera_lite.tiles import decode_tile, open_map, read_tile
    db = open_map()
    probe = np.stack([decode_tile(read_tile(db, 17, int(x), int(y))) for x, y in idx["xy"][:4]])
    t0 = time.time()
    with torch_device() as dev:
        print(f"DINOv2 on {dev} ...", flush=True)
        model = R.load_dino(dev)
        mine = R.embed_dino(model, probe, dev)
        diff = float(np.abs(mine - idx["emb"][:4].astype(np.float32)).max())
        print(f"4 map tiles embedded with YOUR preprocess vs the index made with the course's: largest difference "
              f"{diff:.4f}")
        if diff > 0.02:
            sys.exit("Your preprocess does not give DINOv2 the input it learned from (the index would not be "
                     "comparable with your photos). Lab Step 1's hints: BGR kept (hint 2), no / 255 (hint 3), or "
                     "reshape instead of transpose (hint 6) — `python3 run_locate.py test` names most of them.")
        q = R.embed_dino(model, views, dev)
    os.makedirs(OUT, exist_ok=True)
    np.save(os.path.join(OUT, "dino_queries.npy"), q)
    print(f"✔ your preprocess matches. Saved {OUT}/dino_queries.npy: {q.shape[0]} embeddings of {q.shape[1]} numbers "
          f"({time.time() - t0:.1f} s, {(time.time() - t0) / len(views):.2f} s per photo on {dev}).")


def finder_dino(R):
    path = os.path.join(OUT, "dino_queries.npy")
    if not os.path.exists(path):
        sys.exit("out/dino_queries.npy is missing: run `python3 run_locate.py embed` first (Step 2)")
    return R.TileIndex.load(os.path.join(DATA, "dino_index.npz")), np.load(path)


def finder_mine(R, weights):
    if not os.path.exists(weights):
        sys.exit(f"{weights} is missing: train it first (`python3 run_locate.py train`, Step 9)")
    limit_threads()
    model = R.load_tilenet(weights)
    small = R.SmallTiles()
    xy = [tuple(int(v) for v in t) for t in np.load(os.path.join(DATA, "dino_index.npz"))["xy"]]
    index = R.tilenet_index(model, small, xy)
    q = R.embed_tilenet(model, np.stack([view(R, p) for p in photos()]))
    return index, q


def retrieval_errors(R, index, q, sigma, seed=23):
    """For every photo: the error of retrieval's top-1 tile centre, of the prior, of a random tile, of the best tile."""
    from navera_lite.locate import DEFAULTS
    L = loc()
    rng = np.random.default_rng(seed)
    rows = []
    for i, p in enumerate(photos()):
        plat, plon, s = prior_at(p, sigma)
        r = rk.need_ok(L, "search_radius", s, DEFAULTS["k_sigma"], DEFAULTS["r_min_m"], DEFAULTS["r_max_m"], kind=float)
        cands = index.search(q[i], plat, plon, r)
        if not cands:
            rows.append(None)
            continue
        d = [dist(p["truth"], (c[2], c[3])) for c in cands]
        by_xy = sorted(range(len(cands)), key=lambda j: (cands[j][0], cands[j][1]))   # the same draw for any finder
        pick = by_xy[int(rng.integers(len(cands)))]
        rows.append({"id": p["id"], "terrain": p["terrain"], "r": r, "n": len(cands), "top1": d[0],
                     "prior": dist(p["truth"], (plat, plon)), "random": d[pick], "best": min(d),
                     "sim": cands[0][4], "right": d[0] <= min(d) + 1e-6})
    return [r for r in rows if r is not None]


def retrieve(finder="dino", sigma=None, weights="my_tiles.pt", quiet=False):
    R, L = retr(), loc()
    rk.need_ok(R, "rank", [1.0, 0.0], [[0.0, 1.0], [1.0, 0.0]], n=None)
    if finder == "dino":
        index, q = finder_dino(R)
    else:
        index, q = finder_mine(R, weights)
    rows = retrieval_errors(R, index, q, sigma)
    res = {}
    names = (("retrieval (" + ("DINOv2" if finder == "dino" else os.path.basename(weights)) + ")", "top1"),
             ("baseline: stay at the prior", "prior"), ("baseline: random tile in the circle", "random"),
             ("best tile in the circle (the limit)", "best"))
    out = []
    for name, key in names:
        ev = rk.need_ok(L, "evaluate", [r[key] for r in rows])
        if not isinstance(ev, dict):
            sys.exit(f"evaluate() must return a dict, got {type(ev).__name__}")
        res[key] = ev
        out.append((name, fmt(ev.get("median_m")), fmt(ev.get("p90_m")),
                    "—" if ev.get("within_300") is None else f"{100 * ev['within_300']:.0f} %"))
    if quiet:
        return res, rows
    s_txt = "the 200 m priors of photos.csv" if sigma is None else f"priors of σ {sigma:.0f} m"
    print(f"{len(rows)} photos, {s_txt}, search radius {rows[0]['r']:.0f} m "
          f"(about {np.mean([r['n'] for r in rows]):.0f} tiles per circle). Errors in metres, to the photo's true centre:\n")
    table(out, ("method", "median", "p90", "within 300 m"))
    print("\nBy terrain (median error of the retrieval's top tile, and how often it is the best tile of the circle):")
    for t in ("textured", "sparse", "sea"):
        sel = [r for r in rows if r["terrain"] == t]
        if sel:
            print(f"  {t:9s} {len(sel):2d} photos: median {np.median([r['top1'] for r in sel]):6.0f} m, "
                  f"best tile chosen {100 * np.mean([r['right'] for r in sel]):3.0f} %")
    good = [r["sim"] for r in rows if r["right"]]
    bad = [r["sim"] for r in rows if not r["right"]]
    if good and bad:
        print(f"\nSimilarity of the top tile: when it IS the best tile {min(good):.3f}–{max(good):.3f}, when it is NOT "
              f"{min(bad):.3f}–{max(bad):.3f}.")
    plt = rk.plt_or_none()
    if plt is not None:
        os.makedirs(OUT, exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for (name, key), col in zip(names, ("C0", "C1", "C2", "0.6")):
            e = np.sort([r[key] for r in rows])
            ax.plot(e, np.arange(1, len(e) + 1) / len(e), color=col, label=name, lw=2 if key == "top1" else 1.3)
        ax.set_xlabel("error (m)")
        ax.set_ylabel("share of photos with an error ≤ x")
        ax.set_xlim(0, max(1600, rows[0]["r"] * 1.3))
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower right")
        tag = f"{finder}_{'csv' if sigma is None else int(sigma)}"
        ax.set_title(f"Retrieval vs baselines ({s_txt})", fontsize=10)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, f"retrieval_{tag}.png"), dpi=110)
        print(f"\nsaved {OUT}/retrieval_{tag}.png")
    return res, rows


def pairs(augment=True):
    R = retr()
    a, v = R.make_pairs(R.SmallTiles(), R.TRAIN_AREA, 8, seed=7, augment=augment)
    big = lambda im: cv2.resize(im, (128, 128), interpolation=cv2.INTER_NEAREST)  # noqa: E731
    top = np.hstack([big(x) for x in a])
    bot = np.hstack([big(x) for x in v])
    img = np.vstack([top, np.full((6, top.shape[1], 3), 255, np.uint8), bot])
    os.makedirs(OUT, exist_ok=True)
    name = "pairs.png" if augment else "pairs_plain.png"
    cv2.imwrite(os.path.join(OUT, name), stamp(img))
    print(f"saved {OUT}/{name}: top row = 8 map tiles (anchors), bottom row = a view of a place INSIDE each tile"
          f"{'' if augment else ' (no augmentation)'}. Map data © OpenStreetMap contributors.")


def train(n_train=8000, epochs=12, batch=64, tau=0.1, shift=0.5, augment=True, out="my_tiles.pt", device=None):
    """Train in a separate process (it gives all its GPU memory back when it ends; this process does not even load
    PyTorch before), then measure the saved weights on the CPU and write logs/<out>.json."""
    import subprocess
    os.makedirs(OUT, exist_ok=True)
    job = {"n_train": n_train, "epochs": epochs, "batch": batch, "tau": tau, "shift": shift, "augment": augment,
           "out": out, "device": device}
    done = os.path.join(OUT, f".train_{out}.json")
    if os.path.exists(done):
        os.remove(done)
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "_train", json.dumps(job)])
    if r.returncode != 0 or not os.path.exists(done):
        sys.exit("the training stopped before the end (see the line above)." + (
            " It was killed: the sandbox ran out of memory. Close other programs that use PyTorch (a second "
            "training, `speed`, `embed`) and train again." if r.returncode in (-9, 137) else ""))
    R = retr()
    res_train = json.load(open(done))
    os.remove(done)
    hist, seconds, dev = res_train["history"], res_train["seconds"], res_train["device"]
    print("measuring it on the lab's photos ...", flush=True)
    res, _ = retrieve("mine", 400.0, out, quiet=True)
    os.makedirs(LOGS, exist_ok=True)
    record = {"weights": out, "student": os.environ.get("ACADEMY_STUDENT", ""), "sha256": R.sha256(out), "n_train": n_train, "epochs": epochs, "batch": batch,
              "tau": tau, "shift": shift, "augment": augment, "device": dev, "seconds": round(seconds, 1),
              "history": hist, "retrieval_400": {k: res[k] for k in ("top1", "prior", "random", "best")}}
    with open(os.path.join(LOGS, out + ".json"), "w") as f:
        json.dump(record, f, indent=1)
    plt = rk.plt_or_none()
    if plt is not None:
        fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
        ep = [r["epoch"] for r in hist]
        ax[0].plot(ep, [r["train_loss"] for r in hist], "o-", label="training")
        ax[0].plot(ep, [r["val_loss"] for r in hist], "o-", label="validation")
        ax[0].set_xlabel("epoch")
        ax[0].set_ylabel("InfoNCE loss")
        ax[0].legend()
        ax[1].plot(ep, [r["val_recall"] for r in hist], "o-", color="C2")
        ax[1].set_xlabel("epoch")
        ax[1].set_ylabel("validation recall (1 of 256)")
        ax[1].set_ylim(0, 1)
        for a in ax:
            a.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, f"train_{os.path.splitext(out)[0]}.png"), dpi=110)
    m = res["top1"]["median_m"]
    print(f"\nsaved {out} ({os.path.getsize(out) / 1e3:.0f} kB) and {LOGS}/{out}.json ({seconds:.0f} s of training).")
    print(f"Retrieval with it on the 80 lab photos, priors of σ 400 m (radius 1 200 m): median {m:.0f} m "
          f"(stay at the prior: {res['prior']['median_m']:.0f} m, random tile: {res['random']['median_m']:.0f} m).")


def train_child(job):
    """The training itself (run by train() in its own process)."""
    import torch
    torch.backends.cudnn.deterministic = True     # the same result every run, and less GPU memory (measured)
    torch.backends.cudnn.benchmark = False
    R = retr()
    net, e = rk.call(R, "TileNet")
    if e:
        sys.exit(e)
    problem = tilenet_problem(net)
    if problem:
        sys.exit(f"Your TileNet does not follow the docstring's rule yet: {problem}. Fix TODO 4 first "
                 "(`python3 run_locate.py test`).")
    za = torch.nn.functional.normalize(torch.randn(4, 8), dim=1)
    v, e = rk.call(R, "info_nce", za, za.clone())
    if e:
        sys.exit(e)
    del net
    t0 = time.time()
    small = R.SmallTiles()
    print(f"making {job['n_train']} training pairs (north of the map) and 1 024 validation pairs (south) ...", flush=True)
    ta, tv = R.make_pairs(small, R.TRAIN_AREA, job["n_train"], seed=1, augment=job["augment"], shift=job["shift"])
    va, vv = R.make_pairs(small, R.VAL_AREA, 1024, seed=2, augment=True)
    print(f"  {time.time() - t0:.0f} s", flush=True)
    torch.manual_seed(0)
    model = R.TileNet()

    def log(row):
        print(f"epoch {row['epoch']:2d}  train loss {row['train_loss']:.3f}  val loss {row['val_loss']:.3f}  "
              f"val recall {row['val_recall']:.3f}   ({time.time() - t0:.0f} s)", flush=True)

    from academy_gpu import NoGpuSlot
    try:
        ctx = torch_device(cpu_ok=False) if job["device"] != "cpu" else contextlib.nullcontext("cpu")
        dev = ctx.__enter__()
    except NoGpuSlot as ex:
        sys.exit(f"{ex}\nThis network is too heavy for the CPU (it would take hours and stay below the check's bar): "
                 "ask your teacher, then run the same `train` command again.")
    try:
        limit_threads()
        print(f"training on {dev}: {job['n_train']} pairs, {job['epochs']} epochs, batch {job['batch']}, tau "
              f"{job['tau']}, shift {job['shift']}, augment {job['augment']}", flush=True)
        hist = R.train_tilenet(model, ta, tv, va, vv, epochs=job["epochs"], batch=job["batch"], tau=job["tau"],
                               device=dev, log=log)
        if not isinstance(hist, list) or not hist:
            sys.exit("train_tilenet returned no history")
    finally:
        ctx.__exit__(None, None, None)
    torch.save(model.to("cpu").state_dict(), job["out"])
    with open(os.path.join(OUT, f".train_{job['out']}.json"), "w") as f:
        json.dump({"history": hist, "seconds": time.time() - t0, "device": dev}, f)


def speed():
    import torch
    R = retr()
    limit_threads()
    torch.set_num_threads(2)
    views = np.stack([view(R, p) for p in photos()[:8]])
    model = R.load_dino("cpu")
    R.embed_dino(model, views[:1])
    t = time.time()
    R.embed_dino(model, views[:4], batch=1)
    t_dino = (time.time() - t) / 4
    if os.path.exists("my_tiles.pt"):
        net = R.load_tilenet("my_tiles.pt")
    else:
        net, e = rk.call(R, "TileNet")
        if e:
            sys.exit(e)
    R.embed_tilenet(net, views[:1])
    t = time.time()
    for v in views:
        R.embed_tilenet(net, v[None])
    t_mine = (time.time() - t) / len(views)
    n_d = sum(p.numel() for p in model.parameters())
    n_m = sum(p.numel() for p in net.parameters())
    print(f"one photo on the CPU (2 threads), embedding only:\n  DINOv2  {n_d:>10,} parameters  {1000 * t_dino:8.0f} ms"
          f"\n  TileNet {n_m:>10,} parameters  {1000 * t_mine:8.1f} ms")


# ================================================================================================= session 2
def cfg_from_answers():
    from navera_lite.locate import DEFAULTS
    cfg = dict(DEFAULTS)
    try:
        a = rk.load_student("answers")
        v = getattr(a, "DIRECT_MAX_R_M", None)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            cfg["direct_max_r_m"] = float(v)
    except SystemExit:
        pass
    return cfg


def local(pid, sigma=50.0):
    L = loc()
    ps = {p["id"]: p for p in photos()}
    if pid not in ps:
        sys.exit(f"no photo {pid!r}: p01 … p80")
    p = ps[pid]
    plat, plon, s = prior_at(p, sigma)
    from navera_lite.locate import DEFAULTS
    r = rk.need_ok(L, "search_radius", s, kind=float)
    t = time.time()
    v = rk.need_ok(L, "local_match", image(pid), p["meta"], plat, plon, r, DEFAULTS)
    lat, lon, why = v
    print(f"photo {pid} ({p['terrain']}), prior σ {s:.0f} m → search radius {r:.0f} m around the prior "
          f"(the prior is {dist(p['truth'], (plat, plon)):.0f} m from the truth)")
    print(f"  fine step: {why}   ({time.time() - t:.1f} s)")
    if lat is not None:
        print(f"  position {lat:.6f}, {lon:.6f} → error {dist(p['truth'], (lat, lon)):.1f} m")


def sweep(finder="mine", weights="my_tiles.pt"):
    L, R = loc(), retr()
    from navera_lite.locate import DEFAULTS
    index, q = (finder_dino(R) if finder == "dino" else finder_mine(R, weights))
    ps = photos()[:SWEEP_PHOTOS]
    qi = {p["id"]: i for i, p in enumerate(photos())}
    result = {"finder": finder, "photos": len(ps), "rows": []}
    t_all = time.time()
    print(f"{len(ps)} photos; each σ twice: 'fine only' searches the whole circle with local matching, 'retrieval' asks"
          f" the finder ({finder}) for 3 tiles first. About 5 minutes — read lesson §8 meanwhile.\n", flush=True)
    rows_out = []
    for s in SWEEP_SIGMAS:
        for mode in ("fine only", "retrieval"):
            cfg = dict(DEFAULTS, direct_max_r_m=1e9 if mode == "fine only" else 0.0)
            errs, calls, t0 = [], [0], time.time()
            for p in ps:
                prior = prior_at(p, s)

                def finder_fn(view_img, lat, lon, r_m, k, _i=qi[p["id"]]):
                    calls[0] += 1
                    return index.search(q[_i], lat, lon, r_m, k)
                v = rk.need_ok(L, "locate", image(p["id"]), p["meta"], prior, finder_fn, cfg)
                if not (isinstance(v, tuple) and len(v) == 3):
                    sys.exit(f"locate() must return (lat, lon, reason), got {v!r}")
                errs.append(None if v[0] is None else dist(p["truth"], (v[0], v[1])))
            if mode == "retrieval" and calls[0] != len(ps):
                sys.exit(f"locate() called the finder {calls[0]} times for {len(ps)} photos in retrieval mode: "
                         "once per photo, when the radius is above cfg['direct_max_r_m']")
            if mode == "fine only" and calls[0]:
                sys.exit("locate() called the finder although the radius was below cfg['direct_max_r_m']")
            ev = rk.need_ok(L, "evaluate", errs)
            sec = (time.time() - t0) / len(ps)
            r = rk.need_ok(L, "search_radius", s, kind=float)
            result["rows"].append({"sigma": s, "r": r, "mode": mode, "sec": sec, **ev})
            rows_out.append((f"{s:.0f}", f"{r:.0f}", mode, f"{ev['accepted']}/{ev['n']}", fmt(ev["median_m"], 1),
                             fmt(ev["p90_m"], 1), ev["wrong"], f"{sec:.1f}"))
            print(f"  σ {s:4.0f} m, {mode:9s}: done ({time.time() - t_all:.0f} s)", flush=True)
    print()
    table(rows_out, ("σ (m)", "radius", "mode", "accepted", "median", "p90", "wrong", "s/photo"))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sweep.json"), "w") as f:
        json.dump(result, f, indent=1)
    print(f"\nsaved {OUT}/sweep.json. Errors in metres (accepted photos only); 'wrong' = accepted with an error > 50 m.")


def budget():
    L = loc()
    terms = {"tilt left after straightening (0.5° at 360 m)": 360 * math.tan(math.radians(0.5)),
             "matcher noise (2 map pixels of 0.97 m)": 2 * 0.97,
             "photo timing (0.1 s at 20 m/s)": 0.1 * 20.0,
             "map drawn from OpenStreetMap (registration)": 3.0}
    tot = rk.need_ok(L, "budget", terms, kind=float)
    for k, v in terms.items():
        print(f"  {k:48s} {v:5.2f} m")
    print(f"  {'total, from YOUR budget()':48s} {tot:5.2f} m")
    path = os.path.join(OUT, "run_csv.json")
    if os.path.exists(path):
        r = json.load(open(path))
        print(f"\nMeasured by your last `run` (σ 200 m priors): median {fmt(r['median_m'], 1)} m, p90 {fmt(r['p90_m'], 1)} m."
              " (The photos have NO timing error: their budget is smaller than a real flight's.)")


def run_all(sigma=None, finder="mine", weights="my_tiles.pt"):
    L, R = loc(), retr()
    cfg = cfg_from_answers()
    index, q = (finder_dino(R) if finder == "dino" else finder_mine(R, weights))
    ps = photos()
    errs, rows = [], []
    t0 = time.time()
    for i, p in enumerate(ps):
        prior = prior_at(p, sigma)

        def finder_fn(view_img, lat, lon, r_m, k, _i=i):
            return index.search(q[_i], lat, lon, r_m, k)
        v = rk.need_ok(L, "locate", image(p["id"]), p["meta"], prior, finder_fn, cfg)
        if not (isinstance(v, tuple) and len(v) == 3):
            sys.exit(f"locate() must return (lat, lon, reason), got {v!r}")
        e = None if v[0] is None else dist(p["truth"], (v[0], v[1]))
        errs.append(e)
        rows.append((p["id"], p["terrain"], "—" if e is None else f"{e:.1f}", str(v[2])[:60]))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/80 ({time.time() - t0:.0f} s)", flush=True)
    ev = rk.need_ok(L, "evaluate", errs)
    print()
    table(rows, ("photo", "terrain", "error (m)", "reason"))
    s_txt = "σ 200 m priors of photos.csv" if sigma is None else f"priors of σ {sigma:.0f} m"
    print(f"\n{s_txt}, direct_max_r_m = {cfg['direct_max_r_m']:.0f} m, finder {finder}:")
    print(f"  availability {ev['accepted']}/{ev['n']} = {ev['availability']:.2f}   median {fmt(ev['median_m'], 1)} m   "
          f"p90 {fmt(ev['p90_m'], 1)} m   wrong accepted {ev['wrong']}")
    for t in ("textured", "sparse", "sea"):
        sel = [e for e, p in zip(errs, ps) if p["terrain"] == t]
        print(f"  {t:9s}: {sum(e is not None for e in sel)}/{len(sel)} accepted")
    os.makedirs(OUT, exist_ok=True)
    tag = "csv" if sigma is None else str(int(sigma))
    with open(os.path.join(OUT, f"run_{tag}.json"), "w") as f:
        json.dump({**ev, "sigma": sigma, "direct_max_r_m": cfg["direct_max_r_m"], "finder": finder,
                   "errors": errs}, f, indent=1)
    print(f"saved {OUT}/run_{tag}.json")


# ================================================================================================= main
def arg(name, default, cast=str):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 >= len(sys.argv):
            sys.exit(f"{name} needs a value")
        try:
            return cast(sys.argv[i + 1])
        except ValueError:
            sys.exit(f"{name} {sys.argv[i + 1]!r}: not a {cast.__name__}")
    return default


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    sig = arg("--sigma", None, float)
    if cmd == "test":
        test()
    elif cmd == "look":
        look()
    elif cmd == "embed":
        embed()
    elif cmd == "retrieve":
        retrieve(arg("--finder", "dino"), sig, arg("--weights", "my_tiles.pt"))
    elif cmd == "pairs":
        pairs("--no-augment" not in sys.argv)
    elif cmd == "train":
        train(arg("--n-train", 8000, int), arg("--epochs", 12, int), arg("--batch", 64, int), arg("--tau", 0.1, float),
              arg("--shift", 0.5, float), "--no-augment" not in sys.argv, arg("--out", "my_tiles.pt"),
              arg("--device", None))
    elif cmd == "_train":
        train_child(json.loads(sys.argv[2]))
    elif cmd == "speed":
        speed()
    elif cmd == "local":
        if len(sys.argv) < 3 or sys.argv[2].startswith("-"):
            sys.exit("which photo? e.g. python3 run_locate.py local p07")
        local(sys.argv[2], 50.0 if sig is None else sig)
    elif cmd == "sweep":
        sweep(arg("--finder", "mine"), arg("--weights", "my_tiles.pt"))
    elif cmd == "budget":
        budget()
    elif cmd == "run":
        run_all(sig, arg("--finder", "mine"), arg("--weights", "my_tiles.pt"))
    else:
        print(__doc__)
