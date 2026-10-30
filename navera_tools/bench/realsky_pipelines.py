#!/usr/bin/env python3
"""Real stars (ESO MASCOT / ALPACA all-sky frames): the 360 solver's input stages side by side - production
detector, star-segmentation network (filter / detector), sky cleaning - lost-in-space and with a position prior.

    python3 navera_tools/bench/realsky_pipelines.py --camera mascot --lens LENS.json --frames F... --out OUT.jsonl
        [--degrade G,N,Q] [--starseg W.pth] [--pipelines base,clean,unet-filter,unet] [--modes lis,prior]
        [--prior-km 10] [--positions CSV] [--tag NAME]

Uses realsky_validate's adapter unchanged (8-bit frame, one fisheye lens, fixed 'up' of the calibrated mount;
--up-per-frame is not supported here, so ALPACA's tracking mount is out of scope). For every frame:
- star recall from the truth (never fed to a solver): catalogue stars <= RECALL_MAG above 15 deg at their true
  place (astropy alt/az, calibrated lens and mount) that have a spot within RECALL_PX, per detector;
- each pipeline x mode solved by allsky.locate with every gate unchanged; a fix > 50 km from the site is WRONG.
'clean' = cn_pkg.skyclean.SkyCleaner with the OTHER frames of the same night as the ring (offline: the live
service would only have earlier ones). The prior is the true site, radius --prior-km / 111.2 + 0.5 deg ('up').
Every fix is appended to --positions (tool,session,frame,utc,lat,lon,sigma_km,truth_lat,truth_lon,err_km).
Reads the archive only; writes only --out and --positions.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, HERE, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RECALL_MAG = 3.5
RECALL_PX = 2.0
POS_COLS = ["tool", "session", "frame", "utc", "lat", "lon", "sigma_km", "truth_lat", "truth_lon", "err_km"]


def night_of(utc: str) -> str:
    """The local night a UTC time belongs to (Chile, ~UTC-4: noon to noon)."""
    t = datetime.fromisoformat(utc.replace("T", " ")[:19])
    return (t - timedelta(hours=16)).strftime("%Y-%m-%d")


def append_positions(path, rows):
    if not path or not rows:
        return
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, POS_COLS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--camera", required=True)
    ap.add_argument("--lens", required=True)
    ap.add_argument("--frames", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--degrade")
    ap.add_argument("--starseg")
    ap.add_argument("--prob-min", type=float, default=0.5)
    ap.add_argument("--pipelines", default="base,clean,unet-filter,unet")
    ap.add_argument("--modes", default="lis,prior")
    ap.add_argument("--prior-km", type=float, default=10.0)
    ap.add_argument("--positions")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    import numpy as np
    import realsky_validate as rv
    from cn_pkg import allsky, skyclean
    from navera_tools.field.forcedcheck import StarlightGate
    cam = rv.CAMERAS[a.camera]
    cal = json.load(open(a.lens))
    R_cam_enu = np.array(cal["R_cam_enu"])
    up = np.array(cal["up_cam"])
    cat = allsky.Catalogue(limit_mag=4.0, path=allsky.BUNDLED_CATALOGUE)
    full = allsky.Catalogue(limit_mag=4.5, max_sep_deg=1.0, path=allsky.BUNDLED_CATALOGUE)
    deg = None
    if a.degrade:
        g, n, q = a.degrade.split(",")
        deg = dict(gain=float(g), read_noise=float(n), jpeg_q=int(q))
    pipes, modes = a.pipelines.split(","), a.modes.split(",")
    finders = {"base": None, "clean": None}
    det_for_recall = {"thr k=6": None}
    if a.starseg:
        from cn_pkg import starseg
        net = starseg.StarSeg(a.starseg)
        finders["unet-filter"] = starseg.finder(net, "filter", a.prob_min)
        finders["unet"] = starseg.finder(net, "detect", a.prob_min)
        det_for_recall.update({"unet-filter": finders["unet-filter"], "unet": finders["unet"]})
    prior = (cam["lat"], cam["lon"], a.prior_km / rv.KM_PER_DEG + 0.5)

    frames = []
    for fp in sorted(a.frames):
        try:
            img, utc, _ = rv.load_frame(fp, cam, cal["mirror"])
        except Exception as e:                                        # a truncated download
            print("skip", os.path.basename(fp), e, flush=True)
            continue
        if deg:
            img = rv.degrade_frame(img, **deg)
        frames.append((os.path.basename(fp), utc, img))
    by_night = defaultdict(list)
    for name, utc, img in frames:
        by_night[night_of(utc)].append((name, utc, img))

    def tsec(utc):
        return datetime.fromisoformat(utc.replace("T", " ")[:19]).timestamp()

    with open(a.out, "a") as fh:
        for name, utc, img in frames:
            lens = rv.lens_from(cal, img.shape)
            alt, az = rv.star_altaz(full.vec, utc, cam)
            sel = (alt > 15.0) & (full.mag <= RECALL_MAG)
            x, y, _ = lens.project(rv.enu(alt[sel], az[sel]) @ R_cam_enu.T)
            H, W = img.shape
            ins = (x > 3) & (x < W - 4) & (y > 3) & (y < H - 4)
            truth_xy = np.stack([x[ins], y[ins]], 1)
            imgs = {"base": img}
            if "clean" in pipes:
                cl = skyclean.SkyCleaner()
                for n2, u2, im2 in by_night[night_of(utc)]:
                    if n2 != name:
                        cl.ring.append((tsec(u2), im2))
                cl.ring = type(cl.ring)(sorted(cl.ring, key=lambda r: r[0]), maxlen=None)
                imgs["clean"], info = cl.clean(img, tsec(utc))
            rec = {"tag": a.tag, "frame": name, "utc": utc, "stars_expected": int(len(truth_xy))}
            tr, _ = rv.transparency(img, lens, up, R_cam_enu, alt, az, full.mag)
            rec["transparency"] = None if tr is None else round(tr, 3)
            gate = StarlightGate([lens], n_frames=1, min_frames=1)
            gate.add(img, up, utc, cam["lat"], cam["lon"])
            rec["starlight"] = gate.verdict()
            rec["gate_why"] = gate.reason()
            for d, f in det_for_recall.items():
                sp = (f or allsky.detect_spots)(img, lens, up_imu=up, min_alt=12.0, max_spots=600)
                xy = np.array([(s[0], s[1]) for s in sp]).reshape(-1, 2)
                hit = 0
                if len(xy) and len(truth_xy):
                    dd = ((truth_xy[:, None, :] - xy[None, :, :]) ** 2).sum(2)
                    hit = int((dd.min(1) <= RECALL_PX ** 2).sum())
                    junk = int((dd.min(0) > (3 * RECALL_PX) ** 2).sum())
                else:
                    junk = len(xy)
                rec[f"recall_{d}"] = hit
                rec[f"spots_{d}"] = len(xy)
                rec[f"unmatched_{d}"] = junk
            pos = []
            for p in pipes:
                if p not in finders:
                    continue
                im = imgs.get(p, img)
                for m in modes:
                    r = allsky.locate(im, up, utc, cat, lenses=[lens], f_scales=(1.0,),
                                      prior=prior if m == "prior" else None, spot_finder=finders[p])
                    key = f"{p}/{m}"
                    rec[key] = {"solved": bool(r.get("solved")), "matched": r.get("matched"),
                                "p": r.get("p_chance"), "rms": r.get("rms_deg"), "spots": r.get("spots")}
                    if r.get("solved"):
                        err = rv.great_circle_km(r["lat"], r["lon"], cam["lat"], cam["lon"])
                        rec[key].update(err_km=round(err, 2), wrong=err > rv.WRONG_KM)
                        pos.append({"tool": f"realsky_pipelines {key}", "session": f"{a.camera}{a.tag}",
                                    "frame": name, "utc": utc, "lat": round(r["lat"], 5), "lon": round(r["lon"], 5),
                                    "sigma_km": round(r.get("sigma_fit_deg", 0.0) * rv.KM_PER_DEG, 2),
                                    "truth_lat": cam["lat"], "truth_lon": cam["lon"], "err_km": round(err, 2)})
            append_positions(a.positions, pos)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            print(json.dumps(rec), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
