#!/usr/bin/env python3
"""Train the star-segmentation U-Net (cn_pkg.starseg) on synthetic stars added to real starless night frames.

    python3 -m navera_tools.field.starseg_train <session> [<session> ...] --out WEIGHTS.pth [--iters N] [--seed S]

Crops (CROP px) of the sessions' saved frames inside the lens circles: half at random, half centred on what the
production detector finds at a low threshold (the real junk: lamps, reflections, cloud texture, codec blocks).
Every real pixel is labelled 'not star' (the 2026-10-29 sessions hold no starlight, measured by starcheck /
forcedcheck). On the fly, 0-8 synthetic stars per crop: Gaussian or Moffat PSF (sigma 0.6-2.2 px), peak 0.3-4 DN
log-uniform (30 %: 4-150 DN; v1 had faint stars only and learnt 'bright point = junk'), sub-pixel centre, half
the crops with extra noise up to 1.5 DN, added to the 8-bit frame and rounded like a saved frame, half then JPEG
re-encoded (q 40-95: v3; v2 had no compressed star and dropped the stars of JPEG copies). Label: a 1.5 px
disc for stars of peak >= 0.5 DN; stars below 0.5 DN are 'don't care' (neither rewarded nor punished).
Deterministic for a given seed. Memory: ~CROPS_PER_FRAME x frames x 46 kB + the GPU batch (< 1 GB in all).
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CROP = 96
CROPS_PER_FRAME = 40
LABEL_MIN_DN = 0.5
SIGMA_MIN, SIGMA_MAX = 0.6, 2.2   # px: Insta360 ~1 px; wider for defocus / other lenses
BRIGHT_FRAC = 0.3                 # stars drawn 4..BRIGHT_MAX DN (a bright star is a star, not junk)
BRIGHT_MAX = 150.0
EXTRA_NOISE_MAX = 1.5             # DN: extra Gaussian noise on half the crops (other sensors / exposures)
JPEG_FRAC = 0.5                   # crops re-encoded (JPEG q JPEG_Q) AFTER the stars are added: a real star reaches
JPEG_Q = (40, 95)                 # the file through the codec too (v2 had no such case and dropped compressed stars)


def jpeg_some(inj, torch, gen, dev):
    """JPEG_FRAC of the (n, CROP, CROP) 8-bit crops encoded and decoded at a random quality in JPEG_Q."""
    import cv2
    import numpy as np
    n = inj.shape[0]
    pick = (torch.rand(n, generator=gen, device=dev) < JPEG_FRAC).cpu().numpy()
    qs = (JPEG_Q[0] + torch.rand(n, generator=gen, device=dev) * (JPEG_Q[1] - JPEG_Q[0])).cpu().numpy()
    if not pick.any():
        return inj
    arr = inj.to(torch.uint8).cpu().numpy()
    for i in np.nonzero(pick)[0]:
        ok, enc = cv2.imencode(".jpg", arr[i], [cv2.IMWRITE_JPEG_QUALITY, int(qs[i])])
        arr[i] = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return torch.from_numpy(arr).to(dev).float()


def collect(sessions, rng):
    """uint8 raw crops, float16 residuals and noise maps (N, CROP, CROP) from the sessions' frames."""
    import cv2
    import numpy as np
    from cn_pkg import allsky, sky360
    lenses = sky360.default_lenses()
    raws, ress, noises = [], [], []
    for s in sessions:
        with open(os.path.join(s, "frames.jsonl")) as fh:
            rows = [json.loads(line) for line in fh]
        for r in rows:
            if not r.get("image"):
                continue
            g = cv2.imread(os.path.join(s, r["image"]), cv2.IMREAD_GRAYSCALE)
            if g is None:
                continue
            from cn_pkg.starseg import residual_noise
            res, noise = residual_noise(g)
            cand = []
            for L in lenses:
                cand += [(x, y) for x, y, _ in allsky.detect_spots(g, L, k_sigma=4.0, max_spots=300)]
            H, W = g.shape
            for i in range(CROPS_PER_FRAME):
                if i % 2 and cand:
                    x, y = cand[rng.integers(len(cand))]
                    x, y = int(x) + rng.integers(-30, 31), int(y) + rng.integers(-30, 31)
                else:
                    L = lenses[rng.integers(len(lenses))]
                    a, rr = rng.uniform(0, 2 * math.pi), L.radius * math.sqrt(rng.uniform(0, 1))
                    x, y = int(L.cx + rr * math.cos(a)), int(L.cy + rr * math.sin(a))
                x = int(np.clip(x - CROP // 2, 0, W - CROP))
                y = int(np.clip(y - CROP // 2, 0, H - CROP))
                raws.append(g[y:y + CROP, x:x + CROP].copy())
                ress.append(res[y:y + CROP, x:x + CROP].astype(np.float16))
                noises.append(noise[y:y + CROP, x:x + CROP].astype(np.float16))
        print(f"{s}: {len(raws)} crops so far", flush=True)
    return np.stack(raws), np.stack(ress), np.stack(noises)


def render(torch, n, gen, device, max_stars: int = 8):
    """(star images (n, CROP, CROP), label, care masks) of random synthetic stars, on device."""
    yy, xx = torch.meshgrid(torch.arange(CROP, device=device, dtype=torch.float32),
                            torch.arange(CROP, device=device, dtype=torch.float32), indexing="ij")
    k = max_stars
    present = torch.rand(n, k, generator=gen, device=device) < torch.rand(n, 1, generator=gen, device=device)
    cx = 6 + torch.rand(n, k, generator=gen, device=device) * (CROP - 12)
    cy = 6 + torch.rand(n, k, generator=gen, device=device) * (CROP - 12)
    sig = SIGMA_MIN + torch.rand(n, k, generator=gen, device=device) * (SIGMA_MAX - SIGMA_MIN)
    faint = torch.exp(math.log(0.3) + torch.rand(n, k, generator=gen, device=device) * math.log(4.0 / 0.3))
    bright = torch.exp(math.log(4.0) + torch.rand(n, k, generator=gen, device=device) * math.log(BRIGHT_MAX / 4.0))
    amp = torch.where(torch.rand(n, k, generator=gen, device=device) < BRIGHT_FRAC, bright, faint)
    moffat = torch.rand(n, k, generator=gen, device=device) < 0.5
    beta = 2.5 + torch.rand(n, k, generator=gen, device=device) * 1.5
    r2 = (xx[None, None] - cx[..., None, None]) ** 2 + (yy[None, None] - cy[..., None, None]) ** 2
    s2 = (sig ** 2)[..., None, None]
    gauss = torch.exp(-r2 / (2 * s2))
    alpha2 = s2 * 2 * math.log(2) / (2 ** (1 / beta[..., None, None]) - 1)   # same FWHM as the Gaussian
    moff = (1 + r2 / alpha2) ** (-beta[..., None, None])
    psf = torch.where(moffat[..., None, None], moff, gauss)
    a = (amp * present)[..., None, None]
    star = (a * psf).sum(1)
    disc = r2 <= 1.5 ** 2
    lab = (disc & (present & (amp >= LABEL_MIN_DN))[..., None, None]).any(1)
    dont = ((r2 <= 2.0 ** 2) & (present & (amp < LABEL_MIN_DN))[..., None, None]).any(1)
    return star, lab.float(), (~dont).float()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--iters", type=int, default=4000)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--width", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    import numpy as np
    import torch
    from cn_pkg.starseg import build
    rng = np.random.default_rng(a.seed)
    torch.manual_seed(a.seed)
    raws, ress, noises = collect(a.sessions, rng)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    raws_t = torch.from_numpy(raws).to(dev)
    ress_t = torch.from_numpy(ress).to(dev)
    noises_t = torch.from_numpy(noises).to(dev)
    net = build(a.width).to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=2e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.iters)
    gen = torch.Generator(device=dev).manual_seed(a.seed)
    lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(20.0, device=dev), reduction="none")
    t0 = time.time()
    N = len(raws)
    for it in range(a.iters):
        idx = torch.randint(0, N, (a.batch,), generator=gen, device=dev)
        raw = raws_t[idx].float()
        star, lab, care = render(torch, a.batch, gen, dev)
        if torch.rand(1, generator=gen, device=dev).item() < 0.5:     # flips / transposes: the junk has no up
            raw, star, lab, care = (t.flip(-1) for t in (raw, star, lab, care))
        en = EXTRA_NOISE_MAX * torch.rand(a.batch, 1, 1, generator=gen, device=dev)
        en = torch.where(torch.rand(a.batch, 1, 1, generator=gen, device=dev) < 0.5, en, torch.zeros_like(en))
        extra = en * torch.randn(raw.shape, generator=gen, device=dev)
        inj = torch.clamp(torch.round(raw + star + extra), 0, 255)
        if JPEG_FRAC > 0:
            inj = jpeg_some(inj, torch, gen, dev)
        delta = inj - raw
        res = ress_t[idx].float() + delta
        noise = torch.sqrt(noises_t[idx].float() ** 2 + en ** 2)
        x = torch.stack([torch.clamp(res / 4.0, -8, 16), torch.clamp(res / noise / 6.0, -4, 8)], 1)
        logit = net(x)[:, 0]
        loss = (lossf(logit, lab) * care).sum() / care.sum()
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if it % 250 == 0 or it == a.iters - 1:
            print(f"iter {it} loss {loss.item():.4f} ({time.time() - t0:.0f} s)", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    torch.save({"model": net.cpu().state_dict(), "width": a.width, "sessions": a.sessions, "seed": a.seed,
                "iters": a.iters, "crop": CROP}, a.out)
    print(f"saved {a.out} ({sum(p.numel() for p in net.parameters())} parameters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
