"""run_night.py — runs YOUR functions of navera_lite/night.py and navera_lite/homography_net.py on the lab's data,
and draws them.

  Session 1 — Night watch
    python3 run_night.py test          check each function on its docstring example
    python3 run_night.py look          one place by day, at night, at noon in thermal, at dawn            (Step 0)
    python3 run_night.py audit         NAVERA's night replay set against its day set, with YOUR ncc        (Step 2)
    python3 run_night.py coverage      footprints, coverage and the minimum height of three cameras       (Steps 3–4)
    python3 run_night.py prepare       the 12 frames of a night flight, prepared north-up (or refused)    (Step 5)
    python3 run_night.py ncc           NCC template matching in five conditions                           (Step 6)
    python3 run_night.py gate          a night matcher's fixes through YOUR motion gate                   (Step 7)
  Session 2 — Night navigator
    python3 run_night.py pairs         eight training pairs made by YOUR cut_pair, with their true corners (Step 8)
    python3 run_night.py train         train YOUR HomographyNet and save it in my_homography.pt           (Step 11)
          options:  --n-train N (default 16 000 pairs)  --epochs E (default 8)  --scenes K (only the first K
                    training places)  --device cpu  --out FILE (default my_homography.pt)
    python3 run_night.py compare       prior, NCC, untrained and trained network, in five conditions      (Step 13)
          option:   --weights FILE (default my_homography.pt)
    python3 run_night.py sabotage      what loading weights with strict=False does                        (Step 14)
    python3 run_night.py fly           the night flight, end to end: prepare → network → position → gate  (Step 15)

Training and inference share the class's GPU through academy_gpu.py (at most 3 GPU jobs at once: the runner waits for
a free slot or uses the CPU). Pictures are saved in out/ — click them in the file list of the 📝 Code tab. The views
are drawn from OpenStreetMap data: © OpenStreetMap contributors.
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

DATA = "/data/academy/25-thermal-night"
OUT = "out"
P = 64                       # patch side (homography_net.PATCH_PX)
LESSON_CAM = (84.0, 68.0)    # the lesson's camera (NAVERA's simulated thermal view), degrees
FLIGHT_CAM = (75.0, 63.0)    # the flight's camera
FIRST_CAM = (56.7, 48.0)     # the simulator's first physical thermal camera
OK_PX = 3.0                  # a fix "within 3 px" (≈ 23 m) counts as good
_kit_hint = rk._hint


def _hint(e):
    s = str(e)
    if "mat1 and mat2 shapes cannot be multiplied" in s:
        return (" — fc1 got the wrong number of inputs: after four 2 × 2 poolings a 64 × 64 pair is 4 × 4, with 64 "
                "maps: flatten to 64 * 4 * 4 = 1024 numbers (x.flatten(1))")
    if "expected input" in s and "channels" in s:
        return " — conv1 takes 2 input channels (the reference and the thermal patch): nn.Conv2d(2, 16, 3, padding=1)"
    if "Expected 4D" in s or "Expected 3D (unbatched) or 4D" in s:
        return " — a Conv2d wants (N, 2, 64, 64): pass the pairs through to_input first"
    if "cannot assign module before Module.__init__()" in s:
        return " — write super().__init__() as the FIRST line of HomographyNet.__init__"
    if "same device" in s or "device type" in s:
        return (" — two tensors live on different devices (CPU and GPU). In train(), move each BATCH with "
                "to_input(train_x[idx], device) and the targets with train_y[idx].to(device)")
    if "Byte" in s and ("Float" in s or "float" in s):
        return " — the network needs float input: use to_input(...) (it converts uint8 to float32)"
    if "getPerspectiveTransform" in s or "checkVector" in s:
        return (" — cv2.getPerspectiveTransform wants two float32 arrays of shape (4, 2): "
                "np.float32(...) or .astype(np.float32)")
    if "src.cols > 0" in s or "_src.empty()" in s:
        return " — OpenCV got an empty picture: check the shapes you pass"
    return _kit_hint(e)


rk._hint = _hint
night = rk.load_student("navera_lite.night")
_SC = {}


def hnet():
    return rk.load_student("navera_lite.homography_net")


def scenes(name):
    if name not in _SC:
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            sys.exit(f"cannot read {path} — is the data folder mounted? (ls {DATA})")
        _SC[name] = dict(np.load(path))
    return _SC[name]


def stamp(img):
    """(c) OpenStreetMap contributors in the corner of a saved picture made from the map data (the licence asks)."""
    text = "(c) OpenStreetMap contributors"
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
    H, W = img.shape[:2]
    cv2.rectangle(img, (W - w - 9, H - h - 9), (W - 1, H - 1), (255, 255, 255), -1)
    cv2.putText(img, text, (W - w - 6, H - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
    return img


def save(name, img, osm=True):
    os.makedirs(OUT, exist_ok=True)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(os.path.join(OUT, name), stamp(img) if osm else img)
    rk.saved(f"out/{name}")


def label(img, text, scale=0.45):
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1] - 1, 18), (255, 255, 255), -1)
    cv2.putText(out, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 1, cv2.LINE_AA)
    return out


def close(got, want, tol):
    try:
        g = np.asarray(got, dtype=float)
        return g.shape == np.shape(want) and bool(np.all(np.abs(g - np.asarray(want, dtype=float)) <= tol))
    except (TypeError, ValueError):
        return False


def show(v):
    if v is None:
        return "None"
    if isinstance(v, str):
        return v
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        return repr(v)
    if a.ndim == 0:
        return f"{float(a):.6g}"
    return np.array2string(a, precision=4, suppress_small=True, separator=", ").replace("\n", "")


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


# ================================================================================================= test
def test():
    ok_all = True

    def line(todo, name, got, err, good, note):
        nonlocal ok_all
        if err:
            print(f"✘ {todo:<4} {name:22s} {err}")
            ok_all = False
        elif good:
            print(f"✔ {todo:<4} {name:22s} {show(got)}")
        else:
            print(f"✘ {todo:<4} {name:22s} got {show(got)} — {note}")
            ok_all = False

    print("TODO  function               result")
    a = np.array([[10, 20], [30, 40]])
    for b, want in ((np.array([[100, 120], [140, 160]]), 1.0), (np.array([[9, 7], [5, 3]]), -1.0),
                    (np.array([[7, 7], [7, 7]]), 0.0)):
        v, e = rk.call(night, "ncc", a, b)
        note = f"the docstring says {want}. "
        if not e and want == 0.0 and v is not None and isinstance(v, float) and math.isnan(v):
            note += "nan: a uniform picture has nothing to compare — return 0.0 before dividing by 0 (lab Step 1, hint 3)"
        elif not e and v is not None and abs(float(v)) > 1.0001:
            note += "|NCC| > 1: subtract the MEANS first, then divide by the square root of BOTH sums of squares"
        elif not e and isinstance(v, (int, float)) and not isinstance(v, bool) and want == 1.0 and abs(v) < 1:
            note += "the gain does not cancel: subtract each picture's mean BEFORE multiplying (lab Step 1, hint 2)"
        else:
            note += "lab Step 1, hints"
        good = not e and isinstance(v, float) and abs(v - want) < 1e-9
        if not e and not isinstance(v, float) and v is not None:
            note += f" (return a Python float: float(...), not {type(v).__name__})"
        line(1, f"ncc case {'+1' if want == 1 else '-1' if want == -1 else 'uniform'}", v, e, good, note)
    v, e = rk.call(night, "footprint_m", 100.0, 90.0, 60.0)
    note = "the docstring says (200.0, 115.47). "
    if not e and close(v, [200 * math.tan(math.radians(45)) / 2, 115.47 / 2], 0.05):
        note += "Half the size: the footprint spans tan(fov/2) on EACH side of the centre"
    elif not e and v is not None and close(v, [2 * 100 * math.tan(45.0), 2 * 100 * math.tan(30.0)], 0.5):
        note += "math.tan takes RADIANS: math.radians(fov / 2)"
    line(2, "footprint_m", v, e, not e and close(v, [200.0, 115.470054], 1e-3), note)
    for args, want in (((600.0, 300.0, 0.0, 400.0), 0.75), ((600.0, 300.0, 90.0, 400.0), 0.75)):
        v, e = rk.call(night, "coverage", *args)
        note = f"the docstring says {want}. "
        if not e and v is not None and isinstance(v, (int, float)) and v > 1:
            note += "a share is at most 1: divide by the reference square's area"
        elif not e and v is not None and isinstance(v, (int, float)) and abs(v - 1.0) < 1e-6:
            note += "1.0: the rectangle reaches w/2 and h/2 on each side of the centre — half sizes (lab Step 3, hint 3)"
        elif not e and args[2] == 90.0 and v is not None:
            note += "right at 0° but not at 90°? the heading must be in radians: math.radians (lab Step 3, hint 4)"
        else:
            note += "lab Step 3, hints"
        line(3, f"coverage{args}", v, e, not e and v is not None and close(v, want, 0.005), note)
    frame = np.full((512, 640), 200, np.uint8)
    v, e = rk.call(night, "prepare", frame, 400.0, 75.0, 63.0, 0.0, 7.75, 64)
    if not e:
        if not (isinstance(v, tuple) and len(v) == 3):
            e = f"prepare() must return (patch, cov, reason), got {type(v).__name__}"
    if not e:
        patch, cov, why = v
        good = (patch is not None and np.shape(patch) == (64, 64) and close(cov, 0.988388, 0.005) and why == "ok"
                and int(np.asarray(patch)[32, 32]) == 200)
        line(4, "prepare (400 m)", f"patch {None if patch is None else np.shape(patch)}, cov {show(cov)}, {why!r}",
             None, good, "the docstring says a (64, 64) patch of 200s, cov 0.988…, 'ok' (lab Step 5, hints)")
    else:
        line(4, "prepare (400 m)", None, e, False, "")
    mark = np.zeros((512, 640), np.uint8)
    mark[0:80, 280:360] = 255                                  # a bright mark at the TOP of the frame
    v, e = rk.call(night, "prepare", mark, 400.0, 75.0, 63.0, 90.0, 7.75, 64)
    if not e:
        good = isinstance(v, tuple) and len(v) == 3 and v[0] is not None and np.shape(v[0]) == (64, 64)
        if good:
            p = np.asarray(v[0], dtype=float)
            ys, xs = np.nonzero(p > 128)
            good = len(xs) > 0 and xs.mean() > 44 and abs(ys.mean() - 31.5) < 6
            where = "nowhere" if len(xs) == 0 else f"at x ≈ {xs.mean():.0f}, y ≈ {ys.mean():.0f}"
        else:
            where = "no patch"
        line(4, "prepare (heading 90°)", f"the top mark lands {where}", None, good,
             "with heading 90° the frame's top looks EAST: its top mark must land on the RIGHT of the patch, on the "
             "middle row (lab Step 5, 🧰 'which way to turn')")
    else:
        line(4, "prepare (heading 90°)", None, e, False, "")
    v, e = rk.call(night, "prepare", frame, 200.0, 75.0, 63.0, 30.0, 7.75, 64)
    if not e:
        good = isinstance(v, tuple) and len(v) == 3 and v[0] is None and "fly higher" in str(v[2])
        line(4, "prepare (200 m)", v if not good else f"(None, {show(v[1])}, {v[2]!r})", None, good,
             "at 200 m the frame covers too little: return (None, cov, a reason with 'fly higher')")
    else:
        line(4, "prepare (200 m)", None, e, False, "")
    s = np.random.default_rng(0).integers(0, 255, (9, 9)).astype(np.uint8)
    v, e = rk.call(night, "ncc_locate", s[1:6, 3:8], s)
    note = "the docstring says (1.0, -1.0, 1.0). "
    if not e and v is not None and close(v, [3.0, 1.0, 1.0], 1e-6):
        note += "(3, 1) is the template's TOP-LEFT corner: return its CENTRE relative to the search CENTRE (lab Step 6)"
    elif not e and v is not None and close(v, [1.0, 3.0, 1.0], 1e-6):
        note += "x and y swapped: minMaxLoc gives (x, y) = (column, row)"
    elif not e and v is not None and np.size(v) == 3 and abs(float(np.asarray(v, dtype=float)[2])) > 1.0001:
        note += "a score above 1: use the NORMALISED mode cv2.TM_CCOEFF_NORMED"
    line(5, "ncc_locate", v, e, not e and v is not None and close(v, [1.0, -1.0, 1.0], 1e-5), note)
    for t, want in ((1.0, (False, "implausible jump 90 m in 1.0 s (max 60 m)")), (3.0, (True, "ok"))):
        v, e = rk.call(night, "motion_gate", (35.8, 10.6), 0.0, (35.8, 10.601), t)
        good = (not e and isinstance(v, tuple) and len(v) == 2 and v[0] is want[0] and
                (("jump" in str(v[1]) and "90" in str(v[1]) and "60" in str(v[1])) if not want[0] else True))
        line(6, f"motion_gate t = {t}", v, e, good, f"the docstring says {want} (lab Step 7, hints)")
    v, e = rk.call(night, "motion_gate", None, 0.0, (35.8, 10.6), 1.0)
    line(6, "motion_gate (no anchor)", v, e, not e and isinstance(v, tuple) and len(v) == 2 and v[0] is True,
         "without an anchor the first fix is accepted: (True, 'first fix')")

    hn = hnet()
    try:
        import torch
    except ImportError:
        sys.exit("PyTorch is not installed in this sandbox: tell your teacher.")
    limit_threads()
    sc = np.random.default_rng(0).integers(0, 255, (160, 160)).astype(np.uint8)
    for offs, crop, what in (([0.0] * 8, (30, 94, 20, 84), "offsets 0"), ([5.0, 0.0] * 4, (30, 94, 25, 89), "offsets (5, 0)")):
        v, e = rk.call(hn, "cut_pair", sc, sc, (20, 30), offs)
        if not e and not (isinstance(v, tuple) and len(v) == 2):
            e = f"cut_pair() must return (ref_patch, thermal_patch), got {type(v).__name__}"
        if not e:
            a_, b_ = (np.asarray(x) for x in v)
            want = sc[crop[0]:crop[1], crop[2]:crop[3]]
            good = a_.shape == (64, 64) and b_.shape == (64, 64) and np.array_equal(b_, want) and \
                np.array_equal(a_, sc[30:94, 20:84]) and b_.dtype == np.uint8
            note = "the docstring's crops. "
            if b_.shape == (64, 64) and np.array_equal(b_, sc[30:94, 15:79]):
                note += "The thermal patch moved LEFT: offsets say where the thermal corners ARE in the scene (+ = right)"
            elif b_.shape == (64, 64) and not np.array_equal(b_, want) and offs[0] == 0:
                note += "With offsets 0 the thermal patch must be the plain crop: SQUARE is [[0, 0], [63, 0], [63, 63], [0, 63]]"
            else:
                note += "Lab Step 8, hints"
            line(7, f"cut_pair {what}", f"shapes {a_.shape}, {b_.shape}", None, good, note)
        else:
            line(7, f"cut_pair {what}", None, e, False, "")
    v, e = rk.call(hn, "to_input", np.array([[[[0, 2], [4, 6]], [[9, 9], [9, 9]]]], np.uint8))
    want = [[[[-0.8375, -0.2792], [0.2792, 0.8375]], [[0, 0], [0, 0]]]]
    note = "the docstring's numbers. "
    if not e and torch.is_tensor(v) and np.shape(v) == (1, 2, 2, 2) and \
            close(v.detach().cpu().numpy()[0, 0], [[-1.1619, -0.3873], [0.3873, 1.1619]], 1e-3):
        note += "−1.16… (and nan for the uniform channel): you divided by the std alone — the docstring divides by (std + 1.0)"
    elif not e and torch.is_tensor(v) and v.dtype != torch.float32:
        note += f"dtype {v.dtype}: the network needs float32"
    elif not e and not torch.is_tensor(v):
        note += f"return a torch tensor, not {type(v).__name__}"
    else:
        note += "each channel of each pair on its own: mean and std over dim=(2, 3), keepdim=True"
    line(8, "to_input", None if e or not torch.is_tensor(v) else v.detach().cpu().numpy().round(4), e,
         not e and torch.is_tensor(v) and v.dtype == torch.float32 and close(v.detach().cpu().numpy(), want, 1e-3), note)
    net, e = rk.call(hn, "HomographyNet")
    if not e:
        names = [n for n, _ in net.named_children()]
        n = sum(p.numel() for p in net.parameters())
        out, e2 = rk.call(net, "forward", torch.zeros(3, 2, 64, 64))
        if e2:
            line(9, "HomographyNet", None, e2, False, "")
        else:
            shape = tuple(out.shape)
            good = names == ["conv1", "conv2", "conv3", "conv4", "fc1", "fc2"] and shape == (3, 8) and n == 192600
            if names != ["conv1", "conv2", "conv3", "conv4", "fc1", "fc2"]:
                note = f"the layers are {names}: the docstring's names are conv1 … conv4, fc1, fc2, in that order"
            elif shape != (3, 8):
                note = f"the output has shape {shape}, the docstring says (3, 8)"
            else:
                note = f"{n} parameters, the docstring says 192 600: check each layer's sizes (and padding=1)"
            line(9, "HomographyNet", f"layers {names}, output {shape}, {n} parameters", None, good, note)
    else:
        line(9, "HomographyNet", None, e, False, "")
    v, e = rk.call(hn, "offsets_to_H", [2.0, -1.0] * 4)
    note = "the docstring says [[1, 0, 2], [0, 1, -1], [0, 0, 1]]. "
    if not e and v is not None and close(v, [[1, 0, -2], [0, 1, 1], [0, 0, 1]], 1e-6):
        note += "This is the INVERSE: H sends the thermal patch's corners (the square) to the corners + offsets"
    line(10, "offsets_to_H", v, e, not e and v is not None and close(v, [[1, 0, 2], [0, 1, -1], [0, 0, 1]], 1e-6), note)
    rng = np.random.default_rng(1)
    x = rng.integers(0, 255, (48, 2, 64, 64)).astype(np.uint8)
    y = rng.uniform(-12, 12, (48, 8)).astype(np.float32)
    torch.manual_seed(0)
    net, e = rk.call(hn, "HomographyNet")
    if e:
        line(11, "train", None, "train() needs YOUR HomographyNet (TODO 9) for this test: " + e, False, "")
    else:
        v, e = rk.call(hn, "train", net, torch.as_tensor(x[:32]), torch.as_tensor(y[:32]), torch.as_tensor(x[32:]),
                       torch.as_tensor(y[32:]), epochs=2, batch=16, device="cpu")
        bad = number_row(v) if not e else None
        line(11, "train (2 epochs)", None if e or bad else
             f"{len(v)} rows, train_loss {[round(r['train_loss'], 3) for r in v]}", e or bad, True, "")
    print("\nAll docstring examples pass." if ok_all else "\nFix the ✘ lines first (the hint names the lab step).")


def number_row(history):
    """One plain sentence for a history the runner cannot use, or None."""
    if not isinstance(history, list) or not history:
        return f"train() must return a list with one dict per epoch, got {history!r:.80}"
    for r in history:
        if not isinstance(r, dict) or not {"epoch", "train_loss", "val_loss"} <= set(r):
            return f"each row of the history must be a dict with epoch, train_loss, val_loss: got {r!r:.100}"
        for k in ("train_loss", "val_loss"):
            if isinstance(r[k], bool) or not isinstance(r[k], (int, float)):
                return f"history[…][{k!r}] must be a float (loss.item()), got {type(r[k]).__name__}"
    got = [r["epoch"] for r in history]
    if got != list(range(1, len(history) + 1)):
        return f"the epochs must be numbered 1, 2, 3…, got {got}"
    return None


# ================================================================================================= session 1
def look():
    v = scenes("scenes_val.npz")
    i = int(np.argmax([float(np.std(r)) for r in v["ref"]]))
    big = lambda a: cv2.resize(a, (320, 320), interpolation=cv2.INTER_CUBIC)          # noqa: E731
    row = [label(big(v["ref"][i]), "A: day aerial view (the reference)"), label(big(v["night"][i]), "B: thermal, night"),
           label(big(v["day"][i]), "C: thermal, noon"), label(big(v["crossover"][i]), "D: thermal, dawn")]
    gap = np.full((320, 8, 3), 255, np.uint8)
    save("look.png", np.hstack([row[0], gap, row[1], gap, row[2], gap, row[3]]))
    print(f"One place ({v['lat'][i]:.4f}, {v['lon'][i]:.4f}), {v['m_per_px'][i]:.2f} m per pixel, 1.24 km wide, north up.")
    print("B, C, D are 'temperature' pictures (bright = warm) made from the same drawing by a material model: thermal-")
    print("LIKE, not real thermal. They are before the camera's noise and automatic gain.")


def replay():
    d = os.path.join(DATA, "replay")
    if not os.path.isdir(d):
        sys.exit(f"{d} is missing — is the data folder mounted?")
    small = lambda p: cv2.resize(cv2.imread(p, cv2.IMREAD_GRAYSCALE), (192, 91), interpolation=cv2.INTER_AREA)  # noqa
    nights = [small(os.path.join(d, f"night_{k:02d}.jpg")) for k in range(1, 31)]
    days = [small(os.path.join(d, f"day_{k:02d}.jpg")) for k in range(1, 31)]

    def labels(name):
        with open(os.path.join(d, name)) as f:
            return {int(r["frame"]): r for r in csv.DictReader(f)}
    return nights, days, labels("night_labels.csv"), labels("day_labels.csv")


def audit():
    nights, days, nl, dl = replay()
    v, err = rk.call(night, "ncc", nights[0], days[0])
    if err:
        sys.exit(err)
    S = np.zeros((30, 30))
    for i in range(30):
        for j in range(30):
            S[i, j] = rk.need_ok(night, "ncc", nights[i], days[j], kind=float)
    print("Every night frame against every day frame, with YOUR ncc (pictures reduced to 192 × 91 px).")
    print("night  best day  NCC    2nd best  | brightness night / day")
    for i in range(30):
        o = np.argsort(S[i])[::-1]
        print(f"  {i + 1:2d}    {o[0] + 1:2d}     {S[i, o[0]]:5.3f}   {S[i, o[1]]:5.3f}   | "
              f"{nights[i].mean():5.1f} / {days[o[0]].mean():5.1f}")
    best = S.max(axis=1)
    second = np.sort(S, axis=1)[:, -2]
    print(f"\nmedian best NCC {np.median(best):.3f}; median second best {np.median(second):.3f}")
    i, j = 0, int(np.argmax(S[0]))
    n0 = cv2.imread(os.path.join(DATA, "replay", "night_01.jpg"), cv2.IMREAD_GRAYSCALE)
    d0 = cv2.imread(os.path.join(DATA, "replay", f"day_{j + 1:02d}.jpg"))
    stretched = cv2.normalize(n0, None, 0, 255, cv2.NORM_MINMAX)
    save("audit.png", np.vstack([label(cv2.cvtColor(stretched, cv2.COLOR_GRAY2BGR), "night_01 (contrast stretched)"),
                                  label(d0, f"day_{j + 1:02d}: its best NCC")]), osm=False)
    print("(These two are NAVERA's replay frames, copied as data; their imagery is not OpenStreetMap.)")


def coverage_mode():
    ref = 512 * 40075016.686 * math.cos(math.radians(35.83)) / 2 ** 17 / 256
    print(f"Reference square: 512 map pixels at zoom 17 = {ref:.1f} m (NAVERA's), the frame's centre on its centre.\n")
    print(f"Lesson camera {LESSON_CAM[0]:g}° × {LESSON_CAM[1]:g}°: coverage of the reference square")
    print("  height    heading 0°   30°     45°     90°")
    for alt in (250, 300, 350, 400, 500):
        w, h = rk.need_ok(night, "footprint_m", float(alt), *LESSON_CAM, n=2)
        row = [rk.need_ok(night, "coverage", w, h, hd, ref, kind=float) for hd in (0.0, 30.0, 45.0, 90.0)]
        print(f"  {alt:4d} m   " + "  ".join(f"{c:6.3f}" for c in row) + f"    footprint {w:5.0f} × {h:4.0f} m")
    print(f"\nMinimum height for {night.MIN_COVERAGE:.0%} coverage (given min_altitude, with YOUR footprint_m and coverage):")
    for name, cam in (("lesson camera", LESSON_CAM), ("flight camera", FLIGHT_CAM), ("first simulator camera", FIRST_CAM)):
        alts = []
        for hd in (0.0, 45.0):
            a, err = rk.call(night, "min_altitude", cam[0], cam[1], hd, ref)
            if err:
                sys.exit(err)
            alts.append(a)
        print(f"  {name:24s} {cam[0]:4.1f}° × {cam[1]:4.1f}°   heading 0°: {alts[0]:5.0f} m   heading 45°: {alts[1]:5.0f} m")


def flight():
    d = os.path.join(DATA, "flight")
    with open(os.path.join(d, "frames.csv")) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in r:
            r[k] = float(r[k])
    with open(os.path.join(d, "ref_area.json")) as f:
        area = json.load(f)
    img = cv2.imread(os.path.join(d, "ref_area.png"), cv2.IMREAD_GRAYSCALE)
    return rows, area, img


def frame(k):
    return cv2.imread(os.path.join(DATA, "flight", f"frame_{int(k):02d}.png"), cv2.IMREAD_GRAYSCALE)


def area_px(area, lat, lon):
    """(x, y) of a point in ref_area.png, pixel-centre convention (the corner of the picture is at −0.5, −0.5)."""
    e = (lon - area["corner_lon"]) * 111320.0 * math.cos(math.radians(area["centre_lat"]))
    n = (area["corner_lat"] - lat) * 111320.0
    return e / area["m_per_px"] - 0.5, n / area["m_per_px"] - 0.5


def ref_patch(img, area, lat, lon):
    """The reference patch (P × P) whose centre point ((P − 1)/2, (P − 1)/2) is at (lat, lon)."""
    x, y = area_px(area, lat, lon)
    M = np.float32([[1, 0, x - (P - 1) / 2.0], [0, 1, y - (P - 1) / 2.0]])
    return cv2.warpAffine(img, M, (P, P), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)


def prepare_mode():
    rows, area, img = flight()
    print(f"Night flight: 12 frames, 640 × 512, camera {FLIGHT_CAM[0]:g}° × {FLIGHT_CAM[1]:g}°; reference "
          f"{area['m_per_px']:.2f} m/px, patch {P} px = {P * area['m_per_px']:.0f} m.")
    print(" frame  height  heading  coverage  result")
    tiles = []
    for r in rows:
        out = rk.need_ok(night, "prepare", frame(r["frame"]), r["alt_m"], *FLIGHT_CAM, r["heading_deg"],
                         area["m_per_px"], P)
        if not (isinstance(out, tuple) and len(out) == 3):
            sys.exit(f"prepare() must return (patch, cov, reason), got {out!r:.80}")
        patch, cov, why = out
        print(f"  {int(r['frame']):3d}   {r['alt_m']:5.0f} m  {r['heading_deg']:5.1f}°   {float(cov):6.3f}   {why}")
        if patch is not None and len(tiles) < 3:
            truth = ref_patch(img, area, r["true_lat"], r["true_lon"])
            big = lambda a: cv2.resize(np.asarray(a, np.uint8), (256, 256), interpolation=cv2.INTER_NEAREST)  # noqa
            tiles.append(np.hstack([label(big(patch), f"frame {int(r['frame'])} prepared"),
                                    np.full((256, 6, 3), 255, np.uint8),
                                    label(big(truth), "day reference at its TRUE place")]))
    if tiles:
        f1 = cv2.resize(frame(rows[0]["frame"]), (320, 256), interpolation=cv2.INTER_AREA)
        top = np.hstack([label(f1, "frame 1 as the camera saw it"), np.full((256, 198, 3), 255, np.uint8)])
        save("prepared.png", np.vstack([top] + tiles))


def ncc_pairs(hn_mod, cond, n=256, seed=11):
    """Pairs of the validation places for one condition (made with the course's own cutting, so that session 1
    does not need YOUR cut_pair)."""
    v = scenes("scenes_val.npz")
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for k in range(n):
        i = k % len(v["ref"])
        a = v["ref"][i]
        b = {"same": a, "night": v["night"][i], "noon": v["day"][i], "dawn": v["crossover"][i],
             "night inverted": 255 - v["night"][i]}[cond]
        x0, y0 = rng.uniform(16, 160 - P - 16, 2)
        off = rng.uniform(-12, 12, (1, 2)) + rng.uniform(-4, 4, (4, 2))
        sq = np.float32([[0, 0], [P - 1, 0], [P - 1, P - 1], [0, P - 1]])
        Hr = cv2.getPerspectiveTransform(sq + np.float32([x0, y0]), sq)
        Ht = cv2.getPerspectiveTransform((sq + np.float32([x0, y0]) + off).astype(np.float32), sq)
        ra = cv2.warpPerspective(a, Hr, (P, P))
        tb = cv2.warpPerspective(b, Ht, (P, P)).astype(np.float32)
        tb = tb + rng.normal(0, 1.0, tb.shape) + rng.normal(0, 0.5, (1, P))
        lo, hi = np.percentile(tb, (1, 99))
        tb = np.clip((tb - lo) / max(hi - lo, 1e-3) * 255, 0, 255).astype(np.uint8)
        xs.append(np.stack([ra, tb]))
        ys.append(off.reshape(8))
    return np.array(xs), np.array(ys, np.float32)


def true_centre(off):
    """(dx, dy) of the thermal centre in the reference patch, from the true offsets (pixels)."""
    sq = np.float32([[0, 0], [P - 1, 0], [P - 1, P - 1], [0, P - 1]])
    H = cv2.getPerspectiveTransform(sq, (sq + np.asarray(off, np.float32).reshape(4, 2)).astype(np.float32))
    m = (P - 1) / 2.0
    c = H @ np.array([m, m, 1.0])
    return c[0] / c[2] - m, c[1] / c[2] - m


def ncc_errors(xs, ys):
    """Centre error (px) of NCC template matching: the thermal patch's central 32 × 32 searched in the reference."""
    errs = []
    for (a, b), off in zip(xs, ys):
        out = rk.need_ok(night, "ncc_locate", b[16:48, 16:48], a, n=3)
        tx, ty = true_centre(off)
        errs.append(math.hypot(out[0] - tx, out[1] - ty))
    return np.array(errs)


def ncc_mode():
    print("NCC template matching on 256 pairs of the validation places per condition: the thermal patch's central")
    print("32 × 32 px searched in the 64 × 64 reference patch with YOUR ncc_locate. Error = distance between the found")
    print(f"and the true centre, pixels (1 px ≈ 7.75 m). 'Good' = within {OK_PX:g} px.")
    print("  condition          median error   good")
    res = {}
    for cond in ("same", "night", "night inverted", "noon", "dawn"):
        xs, ys = ncc_pairs(None, cond)
        e = ncc_errors(xs, ys)
        res[cond] = e
        name = {"same": "day vs day"}.get(cond, cond)
        print(f"  {name:18s} {np.median(e):8.1f} px   {np.mean(e < OK_PX):5.0%}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(7, 3.3))
        for cond, e in res.items():
            ax.hist(np.clip(e, 0, 30), bins=np.arange(0, 31, 1), histtype="step", lw=1.6,
                    label={"same": "day vs day"}.get(cond, cond))
        ax.set_xlabel("centre error (px), clipped at 30")
        ax.set_ylabel("pairs")
        ax.legend()
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "ncc.png"), dpi=90)
        rk.saved("out/ncc.png")


def gate_mode():
    with open(os.path.join(DATA, "night_fixes.csv")) as f:
        rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
    print("A night matcher's fixes on another flight (25 m/s), through YOUR motion_gate (30 m/s, margin 30 m).")
    print("   t (s)   score   jump from anchor   result")
    anchor, t_anchor = None, 0.0
    for r in rows:
        fix = (r["lat"], r["lon"])
        out = rk.need_ok(night, "motion_gate", anchor, t_anchor, fix, r["t_s"])
        if not (isinstance(out, tuple) and len(out) == 2):
            sys.exit(f"motion_gate() must return (ok, reason), got {out!r:.80}")
        ok, why = out
        jump = "" if anchor is None else f"{night.haversine_m(anchor[0], anchor[1], fix[0], fix[1]):7.0f} m"
        print(f"  {r['t_s']:5.1f}   {r['score']:.2f}   {jump:>16}   {'ACCEPTED' if ok else 'refused '}  {why}")
        if ok:
            anchor, t_anchor = fix, r["t_s"]


# ================================================================================================= session 2
def pairs_mode():
    hn = hnet()
    v = scenes("scenes_val.npz")
    x, y, err = None, None, None
    try:
        idx = np.linspace(0, len(v["ref"]) - 1, 8).astype(int)            # eight places spread over the set
        x, y = hn.make_pairs(v["ref"][idx], v["night"][idx], 8, seed=3, augment=False)
    except Exception as e:                                                     # noqa: BLE001
        _, err = rk.call(hn, "cut_pair", v["ref"][0], v["night"][0], (20.0, 20.0), [0.0] * 8)
        sys.exit(err or f"make_pairs stopped: {type(e).__name__}: {e}")
    tiles = []
    for (a, b), off in zip(x, y):
        A = cv2.cvtColor(cv2.resize(a, (192, 192), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
        sq = np.float32([[0, 0], [P - 1, 0], [P - 1, P - 1], [0, P - 1]])
        quad = (sq + off.reshape(4, 2)) * 3 + 1
        cv2.polylines(A, [np.round(quad).astype(np.int32)], True, (0, 200, 0), 1, cv2.LINE_AA)
        B = cv2.cvtColor(cv2.resize(b, (192, 192), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
        tiles.append(np.vstack([A, np.full((4, 192, 3), 255, np.uint8), B]))
        print(f"  offsets (px): {[round(float(v), 1) for v in off]}")
    gap = np.full((tiles[0].shape[0], 6, 3), 255, np.uint8)
    save("pairs.png", np.hstack(sum([[t, gap] for t in tiles], [])[:-1]))
    print("Top: the reference patch, with the TRUE place of the thermal patch's 4 corners (green). Bottom: the thermal")
    print("patch (after the camera: noise, automatic gain). Your network will have to find the green corners.")


def train_pairs(hn, n_train, k_scenes, seed=1):
    t = scenes("scenes_train.npz")
    ref, nt = t["ref"], t["night"]
    if k_scenes:
        ref, nt = ref[:k_scenes], nt[:k_scenes]
    x, y = hn.make_pairs(ref, nt, n_train, seed=seed, augment=True)
    v = scenes("scenes_val.npz")
    vx, vy = hn.make_pairs(v["ref"], v["night"], 1024, seed=2, augment=False)
    return x, y, vx, vy, len(ref)


def train_mode():
    import torch
    hn = hnet()
    n_train = option("--n-train", 16000, int)
    epochs = option("--epochs", 8, int)
    k_scenes = option("--scenes", 0, int)
    out = option("--out", "my_homography.pt")
    if out.endswith(".json") or "/" in out or not out.endswith(".pt"):
        sys.exit("--out is a .pt file name in this folder, e.g. --out overfit.pt")
    t0 = time.time()
    try:
        x, y, vx, vy, n_sc = train_pairs(hn, n_train, k_scenes)
    except Exception:                                                          # noqa: BLE001
        v = scenes("scenes_val.npz")
        _, err = rk.call(hn, "cut_pair", v["ref"][0], v["night"][0], (20.0, 20.0), [0.0] * 8)
        sys.exit(err or "make_pairs() could not use your cut_pair: run `python3 run_night.py test`")
    print(f"{len(x)} training pairs from {n_sc} places, {len(vx)} validation pairs from {len(scenes('scenes_val.npz')['ref'])}"
          f" other places (made in {time.time() - t0:.0f} s).")
    want_cpu = option("--device", "auto") == "cpu"
    if want_cpu:
        limit_threads()
    with (contextlib.nullcontext("cpu") if want_cpu else torch_device()) as device:
        torch.manual_seed(0)
        model, err = rk.call(hn, "HomographyNet")
        if err:
            sys.exit(err)
        model = model.to(device)
        t0 = time.time()
        print(f"Training HomographyNet ({epochs} epochs, {device}).")
        print("  epoch  train loss  val loss   elapsed")

        def log(row):
            try:
                print(f"  {row.get('epoch', '?'):>5}  {float(row.get('train_loss', float('nan'))):10.4f}  "
                      f"{float(row.get('val_loss', float('nan'))):8.4f}  {time.time() - t0:6.1f} s",
                      flush=True, file=sys.__stdout__)
            except (TypeError, ValueError, AttributeError, RuntimeError):
                print(f"  (a row the runner cannot print: {row!r:.80})", file=sys.__stdout__)

        history, err = rk.call(hn, "train", model, torch.as_tensor(x), torch.as_tensor(y), torch.as_tensor(vx),
                               torch.as_tensor(vy), epochs=epochs, device=device, log=log)
        if err:
            sys.exit(err)
        bad = number_row(history)
        if bad:
            sys.exit(bad)
        took = time.time() - t0
        torch.save(model.state_dict(), out)
        pred = hn.predict(model, vx, device)
    ce, cc = hn.corner_error(pred, vy), hn.centre_error(pred, vy)
    mpp = float(np.mean(scenes("scenes_val.npz")["m_per_px"]))
    os.makedirs("logs", exist_ok=True)
    record = {"weights": out, "n_train": int(len(x)), "places": int(n_sc), "epochs": epochs, "device": device,
              "seconds": round(took, 1), "val_corner_px": round(float(np.median(ce)), 3),
              "val_centre_px": round(float(np.median(cc)), 3), "history": history}
    with open(os.path.join("logs", out + ".json"), "w") as f:
        json.dump(record, f, indent=1)
    print(f"\nsaved {out} ({os.path.getsize(out) / 1e6:.1f} MB) and logs/{out}.json, {took:.0f} s of training.")
    print(f"On the validation pairs: median corner error {np.median(ce):.2f} px, median centre error {np.median(cc):.2f} px"
          f" (≈ {np.median(cc) * mpp:.0f} m); within {OK_PX:g} px: {np.mean(cc < OK_PX):.0%}.")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot([r["epoch"] for r in history], [r["train_loss"] for r in history], "o-", label="train")
        ax.plot([r["epoch"] for r in history], [r["val_loss"] for r in history], "s-", label="validation")
        ax.set_xlabel("epoch")
        ax.set_ylabel("loss (mean squared error of offsets / 16)")
        ax.set_ylim(0, 0.25)                                      # one scale for every run; answering 0 scores ≈ 0.21
        ax.set_title(f"{out}: {len(x)} pairs from {n_sc} places")
        ax.legend()
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        name = f"loss_{out.rsplit('.', 1)[0]}.png"
        fig.savefig(os.path.join(OUT, name), dpi=90)
        rk.saved(f"out/{name}")


def load_or_exit(hn, weights):
    if not os.path.exists(weights):
        sys.exit(f"{weights} does not exist: run `python3 run_night.py train` first")
    try:
        return hn.load_weights(weights)
    except Exception as e:                                                     # noqa: BLE001
        sys.exit(f"{weights} does not fit HomographyNet ({type(e).__name__}: {str(e).splitlines()[0][:160]}) — did you "
                 "change the layers or their names after training?")


def compare_sets(hn):
    v = scenes("scenes_val.npz")
    c = scenes("scenes_coast.npz")
    sets = {}
    sets["night"] = hn.make_pairs(v["ref"], v["night"], 512, seed=21, augment=False)
    sets["dawn"] = hn.make_pairs(v["ref"], v["crossover"], 512, seed=21, augment=False)
    sets["noon"] = hn.make_pairs(v["ref"], v["day"], 512, seed=21, augment=False)
    sets["coast"] = hn.make_pairs(c["ref"], c["night"], 256, seed=21, augment=False)
    sets["shift 22 px"] = hn.make_pairs(v["ref"], v["night"], 512, seed=21, augment=False, shift_px=22.0)
    return sets


def compare():
    import torch
    hn = hnet()
    weights = option("--weights", "my_homography.pt")
    mine = load_or_exit(hn, weights)
    torch.manual_seed(0)
    fresh, err = rk.call(hn, "HomographyNet")
    if err:
        sys.exit(err)
    try:
        sets = compare_sets(hn)
    except Exception:                                                          # noqa: BLE001
        sys.exit("make_pairs() could not use your cut_pair: run `python3 run_night.py test`")
    print(f"Centre error on validation places (median, px; 1 px ≈ 7.75 m) and share within {OK_PX:g} px.")
    print("  condition      prior only        NCC            untrained net     " + weights)
    rows = {}
    with torch_device(wait_s=60) as device:
        for name, (x, y) in sets.items():
            e0 = hn.centre_error(np.zeros_like(y), y)
            en = ncc_errors(x, y)
            eu = hn.centre_error(hn.predict(fresh.to(device), x, device), y)
            em = hn.centre_error(hn.predict(mine.to(device), x, device), y)
            rows[name] = (e0, en, eu, em)
            cell = lambda e: f"{np.median(e):5.1f} px {np.mean(e < OK_PX):4.0%}"      # noqa: E731
            print(f"  {name:12s}  {cell(e0)}    {cell(en)}    {cell(eu)}    {cell(em)}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(8, 3.6))
        names = list(rows)
        w = 0.2
        for k, (lab, col) in enumerate((("prior only", "#999999"), ("NCC", "#d95f02"), ("untrained", "#7570b3"),
                                        (weights, "#1b9e77"))):
            ax.bar(np.arange(len(names)) + (k - 1.5) * w, [np.median(rows[n][k]) for n in names], w, label=lab, color=col)
        ax.set_xticks(np.arange(len(names)))
        ax.set_xticklabels(names)
        ax.set_ylabel("median centre error (px)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "compare.png"), dpi=90)
        rk.saved("out/compare.png")


def sabotage():
    import torch
    hn = hnet()
    weights = option("--weights", "my_homography.pt")
    load_or_exit(hn, weights)
    sd = torch.load(weights, map_location="cpu", weights_only=True)
    renamed = {"module." + k: v for k, v in sd.items()}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "checkpoint_from_another_script.pt")
    torch.save(renamed, path)
    print(f"{path}: the SAME numbers as {weights}, saved by a script that wrapped the network (every name now starts")
    print(f"with 'module.', e.g. {list(renamed)[0]!r}).\n")
    torch.manual_seed(0)
    model, err = rk.call(hn, "HomographyNet")
    if err:
        sys.exit(err)
    res = model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=False)
    print("1) load_state_dict(..., strict=False):  no error.")
    print(f"   missing keys: {len(res.missing_keys)} of {len(sd)}; unexpected keys: {len(res.unexpected_keys)}")
    v = scenes("scenes_val.npz")
    x, y = hn.make_pairs(v["ref"], v["night"], 512, seed=21, augment=False)
    with torch_device(wait_s=60) as device:
        e_sab = hn.centre_error(hn.predict(model.to(device), x, device), y)
        e_ok = hn.centre_error(hn.predict(hn.load_weights(weights).to(device), x, device), y)
    print(f"   it runs, and answers: median centre error {np.median(e_sab):.1f} px on the night validation pairs")
    print(f"   ({weights} loaded correctly: {np.median(e_ok):.1f} px).\n")
    print("2) load_state_dict(...) with strict=True (PyTorch's default):")
    try:
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        print("   no error?!")
    except RuntimeError as e:
        print("   RuntimeError: " + str(e).splitlines()[0][:150])
        print("   " + str(e).splitlines()[1][:150] if len(str(e).splitlines()) > 1 else "")


def fly():
    hn = hnet()
    weights = option("--weights", "my_homography.pt")
    mine = load_or_exit(hn, weights)
    rows, area, img = flight()
    mpp = area["m_per_px"]
    print(f"The night flight, end to end with {weights}: prepare → reference patch around the prior → network →")
    print("offsets_to_H → centre_shift → position → motion gate. Errors against the true position, metres.")
    print(" frame  prior err   NCC err   net err   gate")
    anchor, t_anchor = None, 0.0
    errs = []
    with torch_device(wait_s=60) as device:
        for r in rows:
            prior_err = night.haversine_m(r["prior_lat"], r["prior_lon"], r["true_lat"], r["true_lon"])
            patch, cov, why = rk.need_ok(night, "prepare", frame(r["frame"]), r["alt_m"], *FLIGHT_CAM, r["heading_deg"],
                                         mpp, P)
            if patch is None:
                print(f"  {int(r['frame']):3d}   {prior_err:6.0f} m   refused: {why}")
                continue
            ref = ref_patch(img, area, r["prior_lat"], r["prior_lon"])
            pair = np.stack([ref, np.asarray(patch, np.uint8)])[None]
            off = hn.predict(mine.to(device), pair, device)[0]
            H = rk.need_ok(hn, "offsets_to_H", off)
            dx, dy = hn.centre_shift(H)
            east, north = dx * mpp, -dy * mpp
            lat = r["prior_lat"] + north / 111320.0
            lon = r["prior_lon"] + east / (111320.0 * math.cos(math.radians(r["prior_lat"])))
            err = night.haversine_m(lat, lon, r["true_lat"], r["true_lon"])
            nx, ny, _ = rk.need_ok(night, "ncc_locate", np.asarray(patch, np.uint8)[16:48, 16:48], ref, n=3)
            nlat = r["prior_lat"] - ny * mpp / 111320.0
            nlon = r["prior_lon"] + nx * mpp / (111320.0 * math.cos(math.radians(r["prior_lat"])))
            nerr = night.haversine_m(nlat, nlon, r["true_lat"], r["true_lon"])
            ok, gwhy = rk.need_ok(night, "motion_gate", anchor, t_anchor, (lat, lon), r["t_s"])
            if ok:
                anchor, t_anchor = (lat, lon), r["t_s"]
            errs.append(err)
            print(f"  {int(r['frame']):3d}   {prior_err:6.0f} m   {nerr:6.0f} m  {err:6.0f} m   {'ok' if ok else gwhy}")
    if errs:
        print(f"\nnetwork: median error {np.median(errs):.0f} m over {len(errs)} prepared frames")


MODES = {"test": test, "look": look, "audit": audit, "coverage": coverage_mode, "prepare": prepare_mode,
         "ncc": ncc_mode, "gate": gate_mode, "pairs": pairs_mode, "train": train_mode, "compare": compare,
         "sabotage": sabotage, "fly": fly}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit(__doc__)
    MODES[mode]()
