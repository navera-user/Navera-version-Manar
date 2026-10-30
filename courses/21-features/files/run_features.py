"""run_features.py — runs YOUR functions of navera_lite/features.py and navera_lite/learned_desc.py on the lab's
pictures and patches, and draws them.

  Session 1 — Scout & detector
    python3 run_features.py test          check each function on its docstring example
    python3 run_features.py house         the structure tensor at three points of a house, and its Harris corners  (Step 2–3)
    python3 run_features.py corners       the 300 strongest Harris corners of the city                              (Step 3)
    python3 run_features.py repeat        repeatability of Harris, ORB and SIFT on six photo pairs                   (Step 4)
    python3 run_features.py terrain       keypoints and matchability of every terrain, and what CLAHE does          (Step 5)
  Session 2 — Learner
    python3 run_features.py hamming       ORB descriptors: the same ground point vs two random points               (Step 6)
    python3 run_features.py patches       8 training pairs and 8 random non-pairs, as the network sees them         (Step 7)
    python3 run_features.py train         train YOUR PatchNet, save the weights and their log                      (Step 10)
          options:  --n-train N (default: all 12 288 pairs)  --epochs E (default 8)  --device cpu
                    --out FILE (default my_desc.pt)   and for Step 13 ONE of:
                    --margin M (default 0.5)  --batch B (default 256)  --negatives all (default: hardest)
                    --train fc (only the last layer learns)   --seed S (the random start, default 0)
    python3 run_features.py filters       conv1 before/after training, and how far each layer moved                (Step 11)
    python3 run_features.py compare       matching score of raw pixels, ORB, SIFT and your network; its failures   (Step 12)
          option:   --weights FILE (default my_desc.pt)

Training and inference share the class's GPU through academy_gpu.py (at most 3 GPU jobs at once: the runner
waits for a free slot, or uses the CPU). Every training writes logs/<FILE>.json: its settings, its loss curves and a
fingerprint (SHA-256) of the weights it saved — the check compares it with your weights file.
Pictures are saved in out/ — click them in the file list of the 📝 Code tab. Map pictures: data © OpenStreetMap
contributors.
"""
import contextlib
import hashlib
import json
import os
import sys
import time

import cv2
import numpy as np

import runner_kit as rk
from academy_gpu import limit_threads, torch_device

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = "/data/academy/21-features"
OUT = "out"
N_POINTS = 1000          # the same number of points for every detector: a fair comparison
TOL_PX = 3.0             # a point is "found again" within 3 pixels
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if "unpackbits" in s or ("ufunc" in s and "bitwise" in s):
        return " — np.bitwise_xor and np.unpackbits need uint8 arrays: np.asarray(d, dtype=np.uint8)"
    if "mat1 and mat2 shapes cannot be multiplied" in s:
        return (" — the Linear layer got another number of inputs than it was built for. The first number after the "
                "'x' is what reached fc per patch: compute by hand what three blocks make of a 1 × 32 × 32 patch "
                "(maps × height × width). A conv without padding=1 shrinks the picture by 2 (32 → 30), so the "
                "sizes no longer halve cleanly (lab Step 8, hint 3)")
    if "Expected 4D" in s or "Expected 3D (unbatched) or 4D" in s:
        return " — a Conv2d wants (N, 1, 32, 32): use the tensors of to_tensor(), not the uint8 patches"
    if "does not require grad" in s:
        return (" — the loss has no gradient: compute it with torch operations only (no .item(), no numpy, no "
                "torch.tensor(...) of a result)")
    if "cannot assign module before Module.__init__()" in s:
        return " — write super().__init__() as the FIRST line of PatchNet.__init__"
    if "out of memory" in s.lower():
        return (" — the GPU (or the computer) has no memory left: classmates are training too. Run the command "
                "again in a minute, or train on the CPU: --device cpu --n-train 4096 --epochs 4")
    if "mask" in s and ("device" in s or "cuda" in s):
        return (" — the MASK lives on the CPU while the distances are on the GPU: create it on the data's device, "
                "torch.eye(len(da), dtype=torch.bool, device=da.device) (lab Step 9, hint 5). The runner already "
                "moves the model and the patches")
    if "same device" in s or "Expected all tensors to be on the same device" in s or "device type" in s:
        return (" — two tensors live on different devices (CPU and GPU). The runner moves the model and the patches; "
                "a tensor YOU create inside triplet_loss or train (torch.eye, torch.zeros, torch.randperm…) must be "
                "put on the data's device: device=da.device or .to(train_a.device)")
    return _kit_hint(e)


rk._hint = _hint
feat = rk.load_student("navera_lite.features")


def learned():
    return rk.load_student("navera_lite.learned_desc")


def gray(name):
    img = cv2.imread(os.path.join(DATA, name), cv2.IMREAD_GRAYSCALE)
    if img is None:
        sys.exit(f"cannot read {DATA}/{name} — is the data folder mounted? (ls {DATA})")
    return img


def colour(name):
    return cv2.imread(os.path.join(DATA, name))


def stamp(img):
    """(c) OpenStreetMap contributors in the corner of a saved map picture (the licence asks for it)."""
    text = "(c) OpenStreetMap contributors"
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
    H, W = img.shape[:2]
    cv2.rectangle(img, (W - w - 9, H - h - 9), (W - 1, H - 1), (255, 255, 255), -1)
    cv2.putText(img, text, (W - w - 6, H - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
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
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return repr(v)
    if a.ndim == 0:
        return f"{float(a):.6g}"
    return np.array2string(a, precision=4, suppress_small=True, separator=", ").replace("\n", "")


# ================================================================================================= test
def test():
    ramp = np.tile(np.arange(6, dtype=np.uint8) * 3, (5, 1))
    gx20 = np.full((10, 10), 20.0, np.float32)
    zero = np.zeros((10, 10), np.float32)
    sq = np.zeros((40, 40), np.uint8)
    sq[10:30, 10:30] = 255
    print("TODO  function             result")
    ok_all = True

    def line(todo, name, got, err, good, note):
        nonlocal ok_all
        if err:
            print(f"✘ {todo:<4} {name:20s} {err}")
            ok_all = False
        elif good:
            print(f"✔ {todo:<4} {name:20s} {show(got) if not isinstance(got, str) else got}")
        else:
            print(f"✘ {todo:<4} {name:20s} got {show(got)} — {note}")
            ok_all = False

    v, e = rk.call(feat, "gradients", ramp)
    if not e and not (isinstance(v, tuple) and len(v) == 2):
        e = f"gradients() must return two arrays (gx, gy), got {type(v).__name__}"
    if not e:
        gx = np.asarray(v[0])
        note = "the docstring says [0, 3, 3, 3, 3, 0] on row 2. "
        if close(gx[2], [0, 24, 24, 24, 24, 0], 1e-3):
            note += "8 times too big: divide the Sobel sums by 8 (lab Step 1, hint 2)"
        elif gx.dtype != np.float32:
            note += f"The dtype is {gx.dtype}: lab Step 1, hint 3"
        else:
            note += "Lab Step 1, hints"
        line(1, "gradients", gx[2], None, close(gx[2], [0, 3, 3, 3, 3, 0], 1e-4) and gx.dtype == np.float32, note)
    else:
        line(1, "gradients", None, e, False, "")
    v, e = rk.call(feat, "structure_tensor", gx20, zero)
    if not e and not (isinstance(v, tuple) and len(v) == 3):
        e = f"structure_tensor() must return three arrays (sxx, syy, sxy), got {type(v).__name__}"
    line(2, "structure_tensor", None if e else [float(np.asarray(x)[5, 5]) for x in v], e,
         not e and close([float(np.asarray(x)[5, 5]) for x in v], [400, 0, 0], 1e-2),
         "the docstring says sxx = 400, syy = 0, sxy = 0: products of gradients, then the Gaussian window")
    for args, want in (((200.0, 200.0, 0.0), [200, 200]), ((400.0, 0.0, 0.0), [400, 0]), ((5.0, 5.0, 3.0), [8, 2])):
        v, e = rk.call(feat, "eigen2", *args)
        note = f"the docstring says {tuple(want)}. "
        if not e and want[0] != want[1] and close(v, want[::-1], 1e-6):
            note += "The order: l1 is the LARGER one (lab Step 2, hint 3)"
        else:
            note += "Lab Step 2, hint 2"
        line(3, f"eigen2{args}", v, e, not e and close(v, want, 1e-6), note)
    v, e = rk.call(feat, "harris", sq)
    if not e:
        r = np.asarray(v, dtype=float)
        good = r.shape == (40, 40) and r[10, 10] > 0 and r[20, 10] < 0
        line(4, "harris", f"R[10, 10] = {r[10, 10]:.4g} (corner), R[20, 10] = {r[20, 10]:.4g} (edge)", None, good,
             "a corner must be > 0 and the middle of a side < 0: Lab Step 3, hint 1")
        v2, e2 = rk.call(feat, "harris", sq, 0.06, 1.0)
        if not e2:
            same = np.allclose(np.asarray(v2, dtype=float), r)
            line(4, "harris(k=0.06, sigma=1.0)", "differs from the defaults" if not same else "same as the defaults",
                 None, not same, "another k and sigma must give another R: use the arguments k and sigma (lab Step 3, "
                 "hint 3)")
        else:
            line(4, "harris(k=0.06, sigma=1.0)", None, e2, False, "")
    else:
        line(4, "harris", None, e, False, "")
    v, e = rk.call(feat, "repeatability", [[1, 1], [5, 5], [50, 50]], [[3.0, 1.0], [9.0, 9.0]], np.eye(3), (20, 20))
    note = "the docstring says 0.5. "
    if not e and close(v, 1 / 3, 1e-6):
        note += "1/3: (50, 50) is outside picture 2 and must not count (lab Step 4, hint 2)"
    elif not e and close(v, 0.0, 1e-6):
        note += "0: is the distance test ≤ tol_px, and do you take the NEAREST point of picture 2?"
    line(5, "repeatability", v, e, not e and close(v, 0.5, 1e-9), note)
    for args, why in ((([[1.0, 1.0]], np.zeros((0, 2)), np.eye(3), (20, 20)), "picture 2 has no point"),
                      (([[50.0, 50.0]], [[1.0, 1.0]], np.eye(3), (20, 20)), "no point falls inside")):
        v, e = rk.call(feat, "repeatability", *args)
        good = not e and v is not None and not np.isnan(float(v)) and abs(float(v)) < 1e-12
        line(5, f"repeatability, {why}", v, e, good, "the docstring says 0.0 in this case (lab Step 4, hint 3)")
    v, e = rk.call(feat, "hamming", np.array([0b10110000], np.uint8), np.array([0b10010001], np.uint8))
    is_int = isinstance(v, int) and not isinstance(v, bool)
    if not e and v == 2 and not is_int:
        note = f"the value is right but it is a {type(v).__name__}: return a Python int, int(...)"
    elif not e and v == 6:
        note = "the docstring says 2. 6 = bits that are EQUAL: count the ones of the XOR (lab Step 6)"
    else:
        note = "the docstring says 2"
    line(6, "hamming", v, e, not e and v == 2 and is_int, note)

    ld = learned()
    try:
        import torch
    except ImportError:
        sys.exit("PyTorch is not installed in this sandbox: tell your teacher.")
    limit_threads()
    net, e = rk.call(ld, "PatchNet")
    if not e:
        n = sum(p.numel() for p in net.parameters())
        names = [name for name, _ in net.named_children()]
        out, e2 = rk.call(net, "forward", torch.zeros(2, 1, 32, 32))
        if e2:
            line(7, "PatchNet", None, e2, False, "")
        else:
            shape_ok = tuple(out.shape) == (2, 64)
            unit = shape_ok and bool(torch.allclose(out.detach().norm(dim=1), torch.ones(2), atol=1e-4))
            sizes_ok = n == 88896
            if names != ["conv1", "conv2", "conv3", "fc"]:
                note = f"the layers are {names}: the docstring's names are conv1, conv2, conv3, fc, in that order"
            elif not shape_ok:
                note = f"the output has shape {tuple(out.shape)}, the docstring says (2, 64)"
            elif not unit:
                note = "the rows must have length 1: divide each row by its length at the end (lab Step 8 🧰)"
            else:
                note = (f"{n} parameters: not what the rule gives — recompute each layer's sizes "
                        "(the maps double each block; fc takes ALL the numbers of the last block; padding=1)")
            line(7, "PatchNet", f"layers {names}, output {tuple(out.shape)}, row lengths "
                 f"{[round(float(x), 4) for x in out.detach().norm(dim=1)]}, sizes "
                 f"{'follow the rule' if sizes_ok else 'do NOT follow the rule'}", None,
                 sizes_ok and names == ["conv1", "conv2", "conv3", "fc"] and unit, note)
    else:
        line(7, "PatchNet", None, e, False, "")
    cases = ((torch.tensor([[0.6, 0.8], [0.8, 0.6]]), 0.7620, "docstring"),
             (torch.tensor([[0.8, 0.6], [0.6, 0.8]]), 0.2380, "second case"))
    da = torch.tensor([[1.0, 0.0], [0.0, 1.0]])
    for dp, want, label in cases:
        v, e = rk.call(ld, "triplet_loss", da, dp)
        if e:
            line(8, "triplet_loss", None, e, False, "")
            continue
        val = float(v.detach()) if hasattr(v, "detach") else float(v)
        note = f"the {label} expects {want:.4f}. "
        if abs(val - (want - 0.5)) < 1e-3:
            note += "Exactly 0.5 too small: the margin is missing (lab Step 9, hint 2)"
        elif abs(val - 0.5) < 1e-3:
            note += "0.5: the diagonal was not left out, so d_neg = d_pos (lab Step 9, hint 3)"
        elif abs(val - 2 * want) < 1e-3:
            note += "twice too big: the SUM — the docstring asks for the mean"
        else:
            note += "Lab Step 9, hints"
        line(8, f"triplet_loss ({label})", f"{val:.4f}", None, abs(val - want) < 1e-3, note)
    if torch.cuda.is_available():
        with torch_device(wait_s=20, quiet=True) as dev:
            if dev == "cuda":
                v, e = rk.call(ld, "triplet_loss", da.to(dev), cases[0][0].to(dev))
                if e and ("device" in e or "cuda" in e):
                    line(8, "triplet_loss (GPU)", None, "on the GPU it fails: a tensor you create inside (the mask?) "
                         "is on the CPU — torch.eye(len(da), dtype=torch.bool, device=da.device) (lab Step 9, hint 5)",
                         False, "")
                elif e:
                    line(8, "triplet_loss (GPU)", None, e, False, "")
                else:
                    line(8, "triplet_loss (GPU)", f"{float(v.detach().cpu()):.4f}", None,
                         abs(float(v.detach().cpu()) - 0.7620) < 1e-3, "the GPU gives another value than the CPU")
    if not ok_all:
        print("\nTODO 9 (train) is tested by `python3 run_features.py train --n-train 512 --epochs 3 --out quick.pt` "
              "once TODO 7–8 are ✔.")
    else:
        print("\nAll examples ✔. TODO 9: python3 run_features.py train --n-train 512 --epochs 3 --out quick.pt")


# ================================================================================================= session 1
HOUSE_POINTS = {"point 1": (20, 60), "point 2": (110, 30), "point 3": (90, 70)}     # (x, y) in house.png


def house():
    g = gray("house.png")
    gx_gy, err = rk.call(feat, "gradients", g)
    if err:
        sys.exit(err)
    st = rk.need_ok(feat, "structure_tensor", *gx_gy)
    print("The structure tensor of house.png (window σ = 1.5 px), at three points:")
    print(f"  {'':8s} {'(x, y)':>10s} {'Sxx':>9s} {'Syy':>9s} {'Sxy':>9s}")
    for name, (x, y) in HOUSE_POINTS.items():
        s = [float(np.asarray(a)[y, x]) for a in st]
        print(f"  {name:8s} {str((x, y)):>10s} {s[0]:9.1f} {s[1]:9.1f} {s[2]:9.1f}")
    print("\nNow compute l1, l2 (your eigen2) and R (k = 0.04) for each point, and decide: flat, edge or corner?")
    r, err = rk.call(feat, "harris", g)
    if err:
        print(f"\n(The Harris corners need your harris() — TODO 4: {err})")
        return
    pts, err = rk.call(feat, "harris_corners", g, 12)
    if err:
        print(f"\n(Harris corners: {err})")
        return
    out = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    out = cv2.resize(out, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    for x, y in np.asarray(pts):
        cv2.drawMarker(out, (int(round(3 * x + 1)), int(round(3 * y + 1))), (0, 0, 255), cv2.MARKER_CROSS, 18, 2)
    for name, (x, y) in HOUSE_POINTS.items():
        cv2.circle(out, (3 * x + 1, 3 * y + 1), 10, (255, 160, 0), 2)
        cv2.putText(out, name[-1], (3 * x + 14, 3 * y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 160, 0), 2)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "house_corners.png"), out)
    print(f"\nYour harris_corners found {len(pts)} corners (red crosses; blue circles: the three points).")
    rk.saved("out/house_corners.png")


def corners():
    img = colour("terrain_city.png")
    need_harris(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    pts = rk.need_ok(feat, "harris_corners", cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 300)
    out = img.copy()
    for x, y in np.asarray(pts):
        cv2.drawMarker(out, (int(round(x)), int(round(y))), (0, 255, 255), cv2.MARKER_CROSS, 7, 1)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "harris_city.png"), stamp(out))
    print(f"{len(pts)} Harris corners on terrain_city.png (yellow crosses).")
    rk.saved("out/harris_city.png")


def need_harris(img):
    """harris_corners uses YOUR harris(): say plainly when it is not ready."""
    r, err = rk.call(feat, "harris", img)
    if err:
        sys.exit("harris_corners needs your harris(): " + err)
    if not hasattr(r, "shape") or tuple(r.shape) != tuple(img.shape[:2]):
        sys.exit(f"harris() must return an array of the picture's shape {img.shape[:2]}, got {type(r).__name__} "
                 f"{getattr(r, 'shape', '')}")


def points(img, method):
    if method == "harris":
        need_harris(img)
        return np.asarray(rk.need_ok(feat, "harris_corners", img, N_POINTS), dtype=np.float64).reshape(-1, 2)
    pts, _ = feat.detect(img, method, N_POINTS)
    return pts


def chance_level(n, shape, tol=TOL_PX, trials=4000, seed=0):
    """What a useless detector scores: random points against n random points (lesson §4)."""
    rng = np.random.default_rng(seed)
    h, w = shape[:2]
    a = rng.uniform([0, 0], [w - 1, h - 1], (trials, 2))
    b = rng.uniform([0, 0], [w - 1, h - 1], (n, 2))
    return rk.need_ok(feat, "repeatability", a, b, np.eye(3), shape, tol, kind=float)


def repeat():
    pairs = json.load(open(os.path.join(DATA, "pairs.json")))
    print(f"Repeatability: share of the map patch's points found again in the photo within {TOL_PX:.0f} px")
    print(f"({N_POINTS} points per detector and picture; chance = random points)\n")
    print(f"  {'pair':20s} {'turn':>5s} {'zoom':>5s} {'harris':>7s} {'orb':>7s} {'sift':>7s} {'chance':>7s}")
    rows = {}
    for p in pairs:
        a, b, H = gray(p["map"]), gray(p["photo"]), np.array(p["H"])
        row = {}
        for m in ("harris", "orb", "sift"):
            v = rk.need_ok(feat, "repeatability", points(a, m), points(b, m), H, b.shape, TOL_PX, kind=float)
            row[m] = round(float(v), 3)
        row["chance"] = round(float(chance_level(N_POINTS, b.shape)), 3)
        rows[p["name"]] = row
        print(f"  {p['name']:20s} {p['heading_deg']:4.0f}° {p['zoom']:5.1f} {row['harris']:7.2f} {row['orb']:7.2f} "
              f"{row['sift']:7.2f} {row['chance']:7.2f}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(10.5, 4))
        names = list(rows)
        x = np.arange(len(names))
        for i, (m, c) in enumerate((("harris", "#d95f02"), ("orb", "#1b9e77"), ("sift", "#7570b3"))):
            ax.bar(x + (i - 1) * 0.25, [rows[n][m] for n in names], 0.25, label=m, color=c)
        ax.plot(x, [rows[n]["chance"] for n in names], "k--", label="chance")
        ax.set_xticks(x, names, rotation=20, fontsize=8)
        ax.set_ylabel("repeatability")
        ax.set_ylim(0, 1)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0))
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "repeat.png"), dpi=90)
        rk.saved("out/repeat.png")


TERRAINS = ["city", "olives", "fields", "saltpans", "coast", "sea"]


def terrain():
    print(f"  {'picture':24s} {'SIFT':>6s} {'SIFT 0.02':>9s} {'match':>6s}  reason")
    shots = []
    counts = {}
    for name in [f"terrain_{t}.png" for t in TERRAINS] + ["drone_city.jpg", "drone_city_dark.jpg",
                                                          "real_town.jpg", "real_coast.jpg"]:
        g = gray(name)
        pts = feat.detect(g, "sift", 100000)[0]
        n, n2 = len(pts), len(feat.detect(g, "sift", 100000, contrast=0.02)[0])
        score, reason = feat.matchability(g)
        print(f"  {name:24s} {n:6d} {n2:9d} {score:6.2f}  {reason}")
        if name.startswith("terrain_"):
            tile = colour(name).copy()
            step = max(1, n // 400)                                     # at most 400 circles: still readable
            for x, y in pts[::step]:
                cv2.circle(tile, (int(round(x)), int(round(y))), 4, (0, 0, 255), 1, cv2.LINE_AA)
            shots.append(cv2.resize(tile, (256, 256), interpolation=cv2.INTER_AREA))
            counts[name[8:-4]] = n
    dark = gray("drone_city_dark.jpg")
    boosted = feat.clahe(dark)
    nb, na = len(feat.detect(dark, "sift", 100000)[0]), len(feat.detect(boosted, "sift", 100000)[0])
    sb, sa = feat.matchability(dark), feat.matchability(boosted)
    print(f"\nCLAHE (clip 2.0, 8 × 8 tiles) on drone_city_dark.jpg: SIFT {nb} → {na} keypoints, "
          f"matchability {sb[0]:.2f} ({sb[1]}) → {sa[0]:.2f} ({sa[1]})")
    sea = gray("real_coast.jpg")
    print(f"CLAHE on real_coast.jpg: SIFT {len(feat.detect(sea, 'sift', 100000)[0])} → "
          f"{len(feat.detect(feat.clahe(sea), 'sift', 100000)[0])} keypoints")
    os.makedirs(OUT, exist_ok=True)
    grid = np.vstack([np.hstack(shots[:3]), np.hstack(shots[3:])])
    for i, t in enumerate(TERRAINS):
        label = f"{t} {counts[t]}"
        cv2.putText(grid, label, (8 + 256 * (i % 3), 22 + 256 * (i // 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(grid, label, (8 + 256 * (i % 3), 22 + 256 * (i // 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1)
    cv2.imwrite(os.path.join(OUT, "terrains.png"), stamp(grid))
    side = np.hstack([cv2.cvtColor(dark, cv2.COLOR_GRAY2BGR), cv2.cvtColor(boosted, cv2.COLOR_GRAY2BGR)])
    cv2.imwrite(os.path.join(OUT, "clahe_dark.png"), stamp(side))
    rk.saved("out/terrains.png (red circles: SIFT keypoints, at most 400 drawn) and out/clahe_dark.png (left: before, right: after CLAHE)")


# ================================================================================================= session 2
def hamming_mode():
    p = next(q for q in json.load(open(os.path.join(DATA, "pairs.json"))) if q["name"] == "city_rot35")
    a, b, H = gray(p["map"]), gray(p["photo"]), np.array(p["H"])
    pa, da = feat.detect(a, "orb", 2000)
    pb, db = feat.detect(b, "orb", 2000)
    proj = feat.warp_points(H, pa)
    same = []
    for i, q in enumerate(proj):
        d = np.hypot(*(pb - q).T)
        j = int(np.argmin(d))
        if d[j] <= 1.5:
            v = rk.need_ok(feat, "hamming", da[i], db[j], kind=int)
            same.append(v)
    rng = np.random.default_rng(1)
    rnd = [rk.need_ok(feat, "hamming", da[i], db[j], kind=int)
           for i, j in zip(rng.integers(0, len(da), 2000), rng.integers(0, len(db), 2000))]
    print(f"ORB descriptors: {da.shape[1]} bytes = {8 * da.shape[1]} bits each.")
    print(f"Same ground point (map patch ↔ photo turned 35°, {len(same)} pairs): median Hamming distance "
          f"{np.median(same):.0f} bits")
    print(f"Two random points ({len(rnd)} pairs): median {np.median(rnd):.0f} bits")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        bins = np.arange(0, 257, 8)
        ax.hist(same, bins, alpha=0.7, label="same ground point", color="#1b9e77")
        ax.hist(rnd, bins, alpha=0.7, label="random pairs", color="#d95f02")
        ax.set_xlabel("Hamming distance (bits of 256)")
        ax.legend()
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "hamming.png"), dpi=90)
        rk.saved("out/hamming.png")


def option(name, default, cast=str):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 >= len(sys.argv):
            sys.exit(f"{name} needs a value, e.g. {name} {default}")
        try:
            return cast(sys.argv[i + 1])
        except ValueError:
            sys.exit(f"{name} {sys.argv[i + 1]}: not a valid value")
    return default


def load_patches(name):
    d = np.load(os.path.join(DATA, name))
    return d["a"], d["b"]


def patches_mode():
    ta, tp = load_patches("patches_train.npz")
    rng = np.random.default_rng(7)
    idx = rng.choice(len(ta), 8, replace=False)
    other = rng.choice(len(ta), 8, replace=False)
    big = lambda p: cv2.resize(p, (96, 96), interpolation=cv2.INTER_NEAREST)        # noqa: E731
    gap = np.full((96, 6), 255, np.uint8)
    row = lambda ims: np.hstack(sum([[big(x), gap] for x in ims], [])[:-1])          # noqa: E731
    width = row(ta[idx]).shape[1]

    def label(text):
        strip = np.full((20, width), 255, np.uint8)
        cv2.putText(strip, text, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, 0, 1, cv2.LINE_AA)
        return strip
    numbers = np.full((20, width), 255, np.uint8)
    for k in range(8):
        cv2.putText(numbers, str(k + 1), (k * 102 + 42, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1, cv2.LINE_AA)
    grid = np.vstack([numbers, label("map patches"), row(ta[idx]), label("the SAME places in the drone photo"), row(tp[idx]),
                      label("8 OTHER places in the drone photo (non-pairs)"), row(tp[other])])
    out = cv2.cvtColor(grid, cv2.COLOR_GRAY2BGR)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "patches.png"), stamp(out))
    print(f"{len(ta)} training pairs of {ta.shape[1]} × {ta.shape[2]} px. Columns 1–8: pairs (top: map, middle: photo);")
    print("bottom row: photo patches of 8 other places, the kind of impostor the loss must push away.")
    rk.saved("out/patches.png")


def all_negatives_loss(da, dp, margin=0.5):
    """Step 13 option `--negatives all`: the mean over EVERY impostor j ≠ i of max(0, margin + d_pos − d(da[i], dp[j]))
    instead of the hardest one only (written for the course, not by you)."""
    import torch
    d = torch.cdist(da, dp)
    pos = d.diagonal().unsqueeze(1)
    off = ~torch.eye(len(da), dtype=torch.bool, device=da.device)
    return torch.relu(margin + pos - d)[off].mean()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def number_row(history):
    """One plain sentence for a history the runner cannot use, or None."""
    if not isinstance(history, list) or not history:
        return f"train() must return a list with one dict per epoch, got {type(history).__name__}"
    for i, row in enumerate(history):
        if not isinstance(row, dict):
            return f"history[{i}] must be a dict, got {type(row).__name__}"
        missing = {"epoch", "train_loss", "val_loss"} - set(row)
        if missing:
            return f"each row of the history needs the keys epoch, train_loss, val_loss — missing {sorted(missing)}"
        for k in ("train_loss", "val_loss"):
            if isinstance(row[k], bool) or not isinstance(row[k], (int, float)):
                return (f"history[{i}]['{k}'] is a {type(row[k]).__name__}: store a Python number "
                        "(loss.item(), or float(...) of a mean)")
    got = [r["epoch"] for r in history]
    if got != list(range(1, len(history) + 1)):
        return f"the epochs must be numbered 1, 2, 3…, got {got}"
    return None


def train_mode():
    import functools
    import torch
    ld = learned()
    n_train = option("--n-train", 0, int)
    epochs = option("--epochs", 8, int)
    out = option("--out", "my_desc.pt")
    margin = option("--margin", 0.5, float)
    batch = option("--batch", 256, int)
    negatives = option("--negatives", "hardest")
    seed = option("--seed", 0, int)
    part = option("--train", "all")
    if part not in ("all", "fc"):
        sys.exit("--train is 'all' (the default) or 'fc' (only the last layer learns)")
    if negatives not in ("hardest", "all"):
        sys.exit("--negatives is 'hardest' (the default) or 'all'")
    if out.endswith(".json") or "/" in out:
        sys.exit("--out is a file name in this folder, e.g. --out exp.pt")
    ta, tp = load_patches("patches_train.npz")
    va, vp = load_patches("patches_val.npz")
    if n_train:
        ta, tp = ta[:n_train], tp[:n_train]
    if negatives == "all":
        ld.triplet_loss = functools.partial(all_negatives_loss, margin=margin)        # the course's variant
    elif margin != 0.5:
        ld.triplet_loss = functools.partial(ld.triplet_loss, margin=margin)          # YOUR loss, another margin
    torch.manual_seed(seed)                       # the network's random start: the same for the same --seed
    model, err = rk.call(ld, "PatchNet")
    if err:
        sys.exit(err)
    if part == "fc":                              # Step 13 "freeze": the three conv blocks keep their random start
        for name in ("conv1", "conv2", "conv3"):
            getattr(model, name).requires_grad_(False)
    want_cpu = option("--device", "auto") == "cpu"
    if want_cpu:
        limit_threads()
    with (contextlib.nullcontext("cpu") if want_cpu else torch_device()) as device:
        model = model.to(device)
        t0 = time.time()
        print(f"Training PatchNet on {len(ta)} pairs ({epochs} epochs, {device}, batch {batch}, margin {margin}, "
              f"negatives {negatives}, seed {seed}{', only fc learns' if part == 'fc' else ''}); validation: {len(va)} "
              "pairs of other places.")
        print("  epoch  train loss  val loss   elapsed")

        def log(row):
            try:
                print(f"  {row.get('epoch', '?'):>5}  {float(row.get('train_loss', float('nan'))):10.4f}  "
                      f"{float(row.get('val_loss', float('nan'))):8.4f}  {time.time() - t0:6.1f} s",
                      flush=True, file=sys.__stdout__)
            except (TypeError, ValueError, AttributeError, RuntimeError):
                print(f"  (a row the runner cannot print: {row!r:.80})", file=sys.__stdout__)

        history, err = rk.call(ld, "train", model, ld.to_tensor(ta, device), ld.to_tensor(tp, device),
                               ld.to_tensor(va, device), ld.to_tensor(vp, device), epochs=epochs, batch=batch,
                               device=device, log=log)
        if err:
            sys.exit(err)
        bad = number_row(history)
        if bad:
            sys.exit(bad)
        torch.save(model.state_dict(), out)
        acc = ld.nn_accuracy(ld.describe(model, va, device), ld.describe(model, vp, device))
        took = time.time() - t0
    os.makedirs("logs", exist_ok=True)
    record = {"weights": out, "sha256": sha256(out), "n_train": len(ta), "epochs": epochs, "batch": batch,
              "margin": margin, "negatives": negatives, "seed": seed, "train": part, "device": device, "seconds": round(took, 1),
              "val_score": round(float(acc), 4), "history": history}
    with open(os.path.join("logs", out + ".json"), "w") as f:
        json.dump(record, f, indent=1)
    print(f"\nsaved {out} ({os.path.getsize(out) / 1e3:.0f} kB) and logs/{out}.json. Matching score on the validation "
          f"pairs: {acc:.3f}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot([r["epoch"] for r in history], [r["train_loss"] for r in history], "o-", label="train")
        ax.plot([r["epoch"] for r in history], [r["val_loss"] for r in history], "s-", label="validation")
        ax.set_xlabel("epoch")
        ax.set_ylabel("triplet loss")
        ax.set_ylim(0, max(0.5, max(r["val_loss"] for r in history) * 1.1))          # one scale for every run
        ax.set_title(f"{out}: {len(ta)} training pairs")
        ax.legend()
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        name = f"loss_{out.rsplit('.', 1)[0]}.png"
        fig.savefig(os.path.join(OUT, name), dpi=90)
        rk.saved(f"out/{name}")


def load_or_exit(ld, weights):
    if not os.path.exists(weights):
        sys.exit(f"{weights} does not exist: run `python3 run_features.py train` first")
    try:
        return ld.load_weights(weights)
    except Exception as e:                                           # noqa: BLE001
        sys.exit(f"{weights} does not fit PatchNet ({type(e).__name__}: {str(e).splitlines()[0][:160]}) — "
                 "did you change the layers or their names, or retrain after changing them?")


def filters_mode():
    import torch
    ld = learned()
    limit_threads()
    weights = option("--weights", "my_desc.pt")
    mine = load_or_exit(ld, weights)
    seed = 0
    try:
        with open(os.path.join("logs", weights + ".json")) as f:
            seed = int(json.load(f).get("seed", 0))
    except (OSError, ValueError, TypeError):
        print(f"(no log for {weights}: assuming it started from --seed 0)")
    torch.manual_seed(seed)
    fresh, err = rk.call(ld, "PatchNet")          # the same random start as your training run
    if err:
        sys.exit(err)
    plt = rk.plt_or_none()
    if not plt:
        sys.exit("matplotlib is missing: cannot draw the filters")
    before = fresh.conv1.weight.detach().cpu().numpy()[:, 0]
    after = mine.conv1.weight.detach().cpu().numpy()[:, 0]
    m = float(np.abs(before).max()) or 1.0
    fig, axes = plt.subplots(6, 8, figsize=(9, 7.2))
    for r, (w, title) in enumerate(((before, "before"), (after, "after"), (after - before, "difference"))):
        for i in range(16):
            ax = axes[2 * r + i // 8, i % 8]
            ax.imshow(w[i], cmap="RdBu_r", vmin=-m, vmax=m)
            ax.set_xticks([])
            ax.set_yticks([])
            if i % 8 == 0:
                ax.set_ylabel(title, fontsize=9)
    fig.suptitle(f"conv1's 16 filters (3 × 3) of {weights}, one colour scale: red = positive, blue = negative")
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "filters.png"), dpi=90)
    print(f"Rows 1–2: conv1 before training (seed {seed}, the start of {weights}); rows 3–4: after; rows 5–6: after − "
          "before.")
    print("How far each layer moved from its start, ‖after − before‖ / ‖before‖:")
    for name in ("conv1", "conv2", "conv3", "fc"):
        a = getattr(mine, name).weight.detach().cpu()
        b = getattr(fresh, name).weight.detach().cpu()
        print(f"  {name:6s} {float((a - b).norm() / b.norm()):.2f}")
    rk.saved("out/filters.png")


def opencv_descriptors(patches, kind):
    """ORB or SIFT descriptor of each 48 × 48 patch, at its centre, with angle 0: the photo patches are north-up within
    the ±20° heading error of the data, so OpenCV's own orientation is not used (like an upright matcher)."""
    det = cv2.SIFT_create() if kind == "sift" else cv2.ORB_create(edgeThreshold=15, patchSize=31)
    size = 8.0 if kind == "sift" else 31.0          # SIFT: of 8, 12, 16, 24, 32 px, 8 scores best on these pairs
    c = (patches.shape[1] - 1) / 2.0
    out = []
    for p in patches:
        _, d = det.compute(p, [cv2.KeyPoint(c, c, size, 0)])
        out.append(d[0] if d is not None and len(d) else np.zeros(128 if kind == "sift" else 32,
                                                                   np.float32 if kind == "sift" else np.uint8))
    return np.array(out)


def failures(ld, model, va, vp, device, n=6):
    """The first n validation map patches whose nearest photo descriptor is the WRONG one."""
    da, dp = ld.describe(model, va, device), ld.describe(model, vp, device)
    rows = []
    for s in range(0, len(da), 256):
        a, b = da[s:s + 256], dp[s:s + 256]
        dist = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        pick = dist.argmin(axis=1)
        for i in np.nonzero(pick != np.arange(len(a)))[0]:
            rows.append((s + i, s + pick[i]))
            if len(rows) >= n:
                break
        if len(rows) >= n:
            break
    big = lambda p: cv2.resize(p[8:40, 8:40], (96, 96), interpolation=cv2.INTER_NEAREST)     # noqa: E731
    gap = np.full((96, 8), 255, np.uint8)
    lines = [np.hstack([big(va[i]), gap, big(vp[i]), gap, big(vp[j])]) for i, j in rows]
    if not lines:
        return 0
    sep = np.full((8, lines[0].shape[1]), 255, np.uint8)
    img = cv2.cvtColor(np.vstack(sum([[x, sep] for x in lines], [])[:-1]), cv2.COLOR_GRAY2BGR)
    header = np.full((40, img.shape[1], 3), 255, np.uint8)
    for k, text in enumerate(("map | its true photo |", "the photo your network chose")):
        cv2.putText(header, text, (4, 15 + 18 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 200), 1, cv2.LINE_AA)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "failures.png"), stamp(np.vstack([header, img])))
    return len(rows)


def compare():
    import torch
    ld = learned()
    weights = option("--weights", "my_desc.pt")
    va, vp = load_patches("patches_val.npz")
    with torch_device(wait_s=60) as device:
        raw = lambda p: ld.to_tensor(p).reshape(len(p), -1).numpy()      # noqa: E731
        rows = [("raw pixels (32 × 32, normalised)", ld.nn_accuracy(raw(va), raw(vp)))]
        rows.append(("ORB (256 bits, Hamming)", ld.nn_accuracy(opencv_descriptors(va, "orb"),
                                                               opencv_descriptors(vp, "orb"), "hamming")))
        rows.append(("SIFT (128 floats)", ld.nn_accuracy(opencv_descriptors(va, "sift"),
                                                         opencv_descriptors(vp, "sift"))))
        torch.manual_seed(0)
        fresh, err = rk.call(ld, "PatchNet")
        if err:
            sys.exit(err)
        rows.append(("PatchNet, untrained (random weights)",
                     ld.nn_accuracy(ld.describe(fresh.to(device), va, device), ld.describe(fresh, vp, device))))
        mine = load_or_exit(ld, weights).to(device)
        rows.append((f"PatchNet, trained ({weights})",
                     ld.nn_accuracy(ld.describe(mine, va, device), ld.describe(mine, vp, device))))
        n_fail = failures(ld, mine, va, vp, device)
    print(f"Matching score on {len(va)} validation pairs (places never seen in training): for each map patch, is the")
    print("nearest of the 256 drone patches of its group the right one?\n")
    for name, acc in rows:
        print(f"  {name:40s} {acc:6.3f}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.barh([r[0] for r in rows][::-1], [r[1] for r in rows][::-1], color="#7570b3")
        ax.set_xlim(0, 1)
        ax.set_xlabel("matching score")
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "compare.png"), dpi=90)
        rk.saved("out/compare.png")
    if n_fail:
        rk.saved(f"out/failures.png ({n_fail} map patches your network matched to the wrong photo patch)")


MODES = {"test": test, "house": house, "corners": corners, "repeat": repeat, "terrain": terrain,
         "hamming": hamming_mode, "patches": patches_mode, "train": train_mode, "filters": filters_mode,
         "compare": compare}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit("usage: python3 run_features.py " + " | ".join(MODES))
    MODES[mode]()
