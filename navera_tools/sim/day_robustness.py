#!/usr/bin/env python3
"""Day-vision robustness matrix, offline: rendered camera frames with ground truth.

Built on dayvision_conditions.py (the renderer, the imagery, the degradations); this adds the
test matrix of the 2026-10-19 campaign (docs/test_reports/day_2026-10-19.md):

  att      attitude errors: tilt error 0-4 deg, yaw (heading) error 0-45 deg, heights 300-2000 m
  oblique  a physically tilted camera 0-30 deg, straightened with the right attitude
  timing   frame/attitude time offset 0-200 ms at turn rates 5-30 deg/s (attitude error = rate x offset)
  speed    0-80 m/s motion blur + the stream delay mis-estimated by +-0.2 s (along-track v x error)
  cond     clouds, haze, glare, dusk, birds, aircraft, drones, blur, JPEG / H.264, noise, exposure
  prior    prior 0-2 km off, with the product's search window (<= 600 m) and an uncapped one
  terrain  coast / sea, farms, olives, hills, urban, desert, forest, 2017 imagery
  hsearch  no magnetometer: heading unknown or 20-180 deg wrong, with / without heading search

Camera: the straight view the Insta360 360 bench cuts (1200 x 900, 100 deg) unless --size/--hfov.
Scenes: "bench" = the bench map (Sousse, the tiles the real screen bench shows): query frames from
the same source (MBTiles z18 below 1000 m, the map's own z17 above) with a fixed camera/screen
appearance change — optimistic like the screen bench; "xdate2022" = Esri Wayback 2022 vs the ~2025
map — the realistic case (its imagery covers frames up to ~800 m).

A frame is WRONG when accepted with an error > 50 m; "beyond 3 sigma" when accepted with an error
beyond 3 x the sigma the matcher states (sigma_m; the day node publishes max(30 m, it)).
Never opens a camera or a window.

    python3 navera_tools/sim/day_robustness.py --groups att --frames 30 --out att.json
"""
import argparse
from fractions import Fraction
import json
import math
import os
import sys
import time
from typing import Dict, List

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_common.camera_model import heading_of_image_up_deg, nadir_homography  # noqa: E402
from navera_tools.sim import dayvision_conditions as dv  # noqa: E402

SIM = os.path.expanduser("~/.navera_sim")
BENCH_AREA = os.path.join(SIM, "bench_2026-10-06", "area")
SCENES = dict(dv.SCENES)
SCENES["bench"] = dict(map=BENCH_AREA, query="mbtiles", qz=18, centre=(35.82227, 10.61691), spread_m=500.0,
                       app=True, note="screen-bench map (Sousse), same source + appearance change")
SCENES["bench_z17"] = dict(SCENES["bench"], query=BENCH_AREA, qz=17,
                           note="screen-bench map's own z17 tiles + appearance change (high frames)")
SCENES["sea"] = dict(SCENES["coast"], centre=(35.8580, 10.6420), spread_m=400.0,
                     note="coast: frames centred ~1.5 km offshore (mostly sea)")
WRONG_M = 50.0
G = 9.81


# ── extra degradations ───────────────────────────────────────────────────
def d_h264(img, rng, crf=35, shift_px=3):
    """H.264 (libx264) artefacts: a short P-frame sequence of the frame moving shift_px per frame,
    the last decoded frame returned (blocking, ringing, smeared detail of a low-bitrate stream)."""
    import av
    h, w = img.shape[:2]
    w2, h2 = w - w % 2, h - h % 2
    out = None
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = w2, h2, "yuv420p"
    enc.time_base = Fraction(1, 10)
    enc.options = {"crf": str(crf), "preset": "ultrafast", "tune": "zerolatency"}
    frames = []
    for k in range(5):
        M = np.float32([[1, 0, (4 - k) * shift_px], [0, 1, 0]])
        src = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)[:h2, :w2]
        vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(src), format="bgr24").reformat(format="yuv420p")
        vf.pts = k
        frames += list(enc.encode(vf))
    frames += list(enc.encode(None))
    dec = av.CodecContext.create("h264", "r")
    for pkt in frames:
        for fr in dec.decode(pkt):
            out = fr.to_ndarray(format="bgr24")
    for fr in dec.decode(None):
        out = fr.to_ndarray(format="bgr24")
    if out is None:
        return img
    res = img.copy()
    res[:h2, :w2] = out
    return res


def d_drones(img, rng, n=5):
    """Quadcopters near (big) and far (small), dark and light airframes (screen_flight's overlay)."""
    out = img.copy()
    h, w = img.shape[:2]
    for k in range(n):
        size = (12, 18, 26, 40, 60)[k % 5]
        x, y = rng.uniform(0.1, 0.9) * w, rng.uniform(0.1, 0.9) * h
        col = (40, 40, 40) if k % 2 else (200, 200, 205)
        for dx, dy in ((1, 1), (1, -1)):
            cv2.line(out, (int(x - dx * size), int(y - dy * size)), (int(x + dx * size), int(y + dy * size)), col,
                     max(2, size // 6))
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            cv2.circle(out, (int(x + dx * size), int(y + dy * size)), max(3, size // 2), col, max(1, size // 10))
        cv2.circle(out, (int(x), int(y)), max(3, size // 3), col, -1)
    return out


def d_dusk(img, rng, gain=0.18, noise=5.0):
    """Dusk: little light (gain), warm, the sensor's noise amplified, then 8-bit."""
    f = img.astype(np.float32) * gain * np.array([0.8, 0.95, 1.15], np.float32)
    f += rng.normal(0, noise, f.shape)
    return np.clip(f, 0, 255).astype(np.uint8)


def d_resolution(img, rng, factor=0.6):
    """Less real detail than pixels (a straight view cut from a fisheye): down then up."""
    h, w = img.shape[:2]
    s = cv2.resize(img, (int(w * factor), int(h * factor)), interpolation=cv2.INTER_AREA)
    return cv2.resize(s, (w, h), interpolation=cv2.INTER_LINEAR)


def d_noise(img, rng, sigma=10.0):
    return np.clip(img.astype(np.float32) + rng.normal(0, sigma, img.shape), 0, 255).astype(np.uint8)


DEGRADE = dict(dv.DEGRADE, h264=d_h264, drones=d_drones, dusk=d_dusk, resolution=d_resolution, noise=d_noise)


# ── the matrix ───────────────────────────────────────────────────────────
BASE = dict(scene="bench", height=800.0, tilt=0.0, tilt_err=0.0, yaw_err=0.0, heading=True, prior_err=100.0,
            radius=None, degrade=[], pose=True, speed=0.0, exposure_s=0.002, delay_err=(0.0,), heading_search=0)


def bench_scene(h: float) -> str:
    return "bench" if h < 1000 else "bench_z17"


def matrix(hfov: float, width: int) -> List[dict]:
    C = []

    def add(group, name, **kw):
        c = dict(BASE, group=group, name=name)
        c.update(kw)
        C.append(c)
    # frames per cell: 30 at 300 m (~0.4 s/frame); 20 above (a frame larger than the map's
    # scale is described in chunks: 2.3-2.6 s/frame at 800 m on the Orin) — the run fits a day
    for h in (300.0, 800.0, 1500.0, 2000.0):
        sc, nf = bench_scene(h), (30 if h < 500 else 20)
        tilts = (0.0, 0.1, 0.5, 1.0, 2.0, 4.0) if h < 500 else (0.0, 1.0, 2.0, 4.0)
        yaws = (2.0, 5.0, 10.0, 20.0, 30.0, 45.0) if h < 500 else (10.0, 20.0, 30.0)
        for e in tilts:
            add("att", f"{h:.0f} m, tilt error {e:g} deg", scene=sc, height=h, tilt_err=e, frames=nf)
        for e in yaws:
            add("att", f"{h:.0f} m, yaw error {e:g} deg", scene=sc, height=h, yaw_err=e, frames=nf)
    for e in (0.0, 1.0, 2.0, 4.0):
        add("att_x", f"xdate2022 300 m, tilt error {e:g} deg", scene="xdate2022", height=300.0, tilt_err=e,
            prior_err=50.0)
    for e in (10.0, 20.0):
        add("att_x", f"xdate2022 300 m, yaw error {e:g} deg", scene="xdate2022", height=300.0, yaw_err=e,
            prior_err=50.0)
    for t in (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0):
        add("oblique", f"300 m, camera tilted {t:g} deg, straightened (attitude right)", height=300.0, tilt=t)
    add("oblique", "300 m, camera tilted 20 deg, straightened, NO pose (frame centre)", height=300.0, tilt=20.0,
        pose=False)
    add("oblique", "800 m, camera tilted 20 deg, straightened (attitude right)", height=800.0, tilt=20.0, frames=20)
    for rate in (5.0, 10.0, 20.0, 30.0):
        for dt in (0.0, 0.05, 0.1, 0.2):
            if rate * dt == 0 and rate > 5:
                continue                                    # the same cell as turn 5 deg/s, 0 ms
            e = rate * dt
            add("timing", f"turn {rate:g} deg/s, offset {dt * 1000:.0f} ms (att. error {e:.1f} deg)", height=300.0,
                tilt_err=e, yaw_err=e)
    for h in (300.0, 800.0):
        nf = 30 if h < 500 else 20
        for v in (0.0, 20.0, 40.0, 60.0, 80.0):
            add("speed", f"{h:.0f} m, {v:g} m/s, 2 ms exposure, delay error -0.2/0/+0.2 s", height=h, speed=v,
                delay_err=(-0.2, 0.0, 0.2), frames=nf)
        add("speed", f"{h:.0f} m, 80 m/s, 8 ms exposure (dim)", height=h, speed=80.0, exposure_s=0.008, frames=nf)
    for sc in ("bench", "xdate2022"):
        tag = "bench 300 m" if sc == "bench" else "xdate 300 m"
        pe = 100.0 if sc == "bench" else 50.0
        for cov in (0.1, 0.3, 0.5, 0.7):
            add("cond", f"{tag}: clouds {cov:.0%}", scene=sc, height=300.0, prior_err=pe,
                degrade=[("clouds", dict(cover=cov, shadows=True))])
        for name, deg in (("haze t=0.5", [("haze", dict(t=0.5))]),
                          ("glare", [("glare", {})]),
                          ("dusk (gain 0.18, noise)", [("dusk", {})]),
                          ("birds 40 + 2 aircraft", [("birds", dict(n=40, aircraft=2))]),
                          ("5 drones", [("drones", {})]),
                          ("motion blur 8 px", [("motion", dict(length_px=8.0))]),
                          ("JPEG q15 + noise 12", [("jpeg_noise", {})]),
                          ("H.264 crf 35", [("h264", dict(crf=35))]),
                          ("H.264 crf 45", [("h264", dict(crf=45))]),
                          ("sensor noise sigma 20", [("noise", dict(sigma=20.0))]),
                          ("under-exposed x0.3", [("exposure", dict(gain=0.3, noise=3.0))]),
                          ("over-exposed x2.2", [("exposure", dict(gain=2.2))]),
                          ("fisheye-cut resolution x0.6", [("resolution", dict(factor=0.6))])):
            add("cond", f"{tag}: {name}", scene=sc, height=300.0, prior_err=pe, degrade=deg)
    for pe in (0.0, 250.0, 500.0, 1000.0, 1500.0, 2000.0):
        add("prior", f"prior {pe:g} m off, product window (3 x (pe/2+30) in 80-600 m)", height=300.0,
            prior_err=pe, radius=min(max(3.0 * (pe / 2.0 + 30.0), 80.0), 600.0))
        if pe >= 1000:
            add("prior", f"prior {pe:g} m off, window 1.3 x offset", height=300.0, prior_err=pe, radius=1.3 * pe,
                frames=20)
    for sc in ("coast", "sea", "farms", "olives", "hills", "urban", "desert", "forest", "xdate2017"):
        add("terrain", f"{sc} 300 m", scene=sc, height=300.0, prior_err=50.0)
    for err in (0.0, 20.0, 45.0, 90.0, 180.0):
        add("hsearch", f"heading {err:g} deg wrong, no search", height=300.0, yaw_err=err)
        add("hsearch", f"heading {err:g} deg wrong, heading search", height=300.0, yaw_err=err, heading_search=1)
    add("hsearch", "no heading at all (SIFT, rotation invariant)", height=300.0, heading=False)
    return C


def make_matcher(kind: str, images_dir: str):
    if kind == "sift":
        from day_pkg.local_matcher import LocalMatcher
        return LocalMatcher(images_dir)
    from day_pkg.learned_matcher import LearnedMatcher
    return LearnedMatcher(images_dir)


def run_one(matcher, imagery, scene: dict, c: dict, i: int, size, hfov: float, seed: int = 0) -> dict:
    rng = np.random.default_rng(1000 * seed + i)
    ang, r = rng.uniform(0, 2 * math.pi), scene["spread_m"] * math.sqrt(rng.uniform(0, 1))
    heading = rng.uniform(0, 360)
    R = dv.camera_R(heading, c["tilt"], rng.uniform(0, 360))
    K = dv.K_of(size[0], size[1], hfov)
    frame = None
    for _ in range(6):
        pos = dv.move(scene["centre"], r * math.cos(ang), r * math.sin(ang))
        frame, valid = dv.render(imagery, scene["qz"], pos, c["height"], R, K, size)
        if frame is not None and valid >= 0.98:
            break
        r *= 0.5
    else:
        return dict(skip=True)
    drng = np.random.default_rng(7 + 1000 * seed + i)
    if scene["app"]:
        frame = dv.appearance(frame, drng)
    mpp_true = 2.0 * c["height"] * math.tan(math.radians(hfov) / 2.0) / size[0]
    if c["speed"] > 0:                              # along the image's up axis (the heading)
        frame = dv.d_motion(frame, drng, length_px=c["speed"] * c["exposure_s"] / mpp_true, angle_deg=-90.0)
    for name, kw in c["degrade"]:
        frame = DEGRADE[name](frame, drng, **kw)
    R_est = dv.small_rotation(c["tilt_err"], rng) @ R
    frame = cv2.warpPerspective(frame, nadir_homography(K, R_est), size, flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT)
    hdg = None
    if c["heading"]:
        hdg = (heading_of_image_up_deg(R_est) + rng.choice([-1, 1]) * c["yaw_err"]) % 360
    pa = rng.uniform(0, 2 * math.pi)
    prior = dv.move(pos, c["prior_err"] * math.cos(pa), c["prior_err"] * math.sin(pa))
    radius = c["radius"] or max(1.3 * c["prior_err"], 100.0)
    if hasattr(matcher, "_heading"):
        matcher._heading = None
    kw = dict(hfov_deg=hfov) if c["pose"] else {}
    if c["heading_search"] and hasattr(matcher, "heading_search_deg"):
        kw["heading_search"] = True
    t0 = time.time()
    res = matcher.locate(frame, prior, radius, mpp_true, heading_deg=hdg, **kw)
    ms = (time.time() - t0) * 1000.0
    out = dict(skip=False, accepted=bool(res.get("accepted")), inliers=int(res.get("inliers") or 0),
               spread=float(res.get("spread") or 0.0), ms=ms, features=res.get("features"),
               reason=(res.get("reason") or "")[:90], scale=res.get("scale_residual"),
               sigma=res.get("sigma_m"), position_from=res.get("position_from"),
               rotation=res.get("rotation_deg"), heading_tried=res.get("heading_tried"))
    if res.get("predicted_lat") is not None:
        out["err_m"] = dv.dist_m(pos, (res["predicted_lat"], res["predicted_lon"]))
        if c["speed"] > 0 and any(c["delay_err"]):
            # the fix is dated with a delay mis-estimated by d: the vehicle was v x d further along
            de =(res["predicted_lon"] - pos[1]) * 111320.0 * math.cos(math.radians(pos[0]))
            dn = (res["predicted_lat"] - pos[0]) * 111320.0
            th = math.radians(heading)
            out["err_delay"] = {f"{d:+.1f}": math.hypot(de - c["speed"] * d * math.sin(th),
                                                        dn - c["speed"] * d * math.cos(th)) for d in c["delay_err"]}
    return out


def summarize(c: dict, rows: List[dict]) -> List[dict]:
    rows = [r for r in rows if not r.get("skip")]
    n = len(rows)
    variants = [("", "err_m")]
    if c["speed"] > 0 and any(c["delay_err"]):
        variants = [(f" [delay err {d:+.1f} s]", d) for d in c["delay_err"]]
    out = []
    for suffix, key in variants:
        acc = [r for r in rows if r["accepted"]]
        errs = [r["err_m"] if key == "err_m" else r["err_delay"][f"{key:+.1f}"] for r in acc]
        e = np.array(errs) if errs else np.array([])
        sig = np.array([max(float(r.get("sigma") or 0.0), 1.0) for r in acc])
        out.append(dict(group=c["group"], name=c["name"] + suffix, n=n, accepted=len(acc),
                        ok=int((e <= WRONG_M).sum()) if len(e) else 0,
                        wrong=int((e > WRONG_M).sum()) if len(e) else 0,
                        beyond3s=int((e > 3 * sig).sum()) if len(e) else 0,
                        beyond3s30=int((e > 3 * np.maximum(sig, 30.0)).sum()) if len(e) else 0,
                        med=float(np.median(e)) if len(e) else None,
                        p90=float(np.percentile(e, 90)) if len(e) else None,
                        max=float(e.max()) if len(e) else None,
                        ms=float(np.median([r["ms"] for r in rows])) if rows else None))
    return out


def fmt(s: dict) -> str:
    f = (lambda v: "-" if v is None else f"{v:.0f}" if v >= 10 else f"{v:.1f}")
    return (f"| {s['group']} | {s['name']} | {s['n']} | {s['accepted']} | {s['ok']} | {s['wrong']} | "
            f"{s['beyond3s']} | {s['beyond3s30']} | {f(s['med'])} | {f(s['p90'])} | {f(s['max'])} | {f(s['ms'])} |")


HEADER = ("| group | cell | n | accepted | <=50 m | WRONG >50 m | >3 sigma (matcher) | >3 sigma (published) | "
          "median m | p90 m | max m | ms/frame |\n|---|---|---|---|---|---|---|---|---|---|---|---|")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--groups", default="", help="comma list of groups (default all)")
    ap.add_argument("--match", default="", help="only cells whose name contains this")
    ap.add_argument("--frames", type=int, default=30, help="per cell (cells above 500 m: at most 20)")
    ap.add_argument("--matcher", choices=["learned", "sift"], default="learned")
    ap.add_argument("--hfov", type=float, default=100.0)
    ap.add_argument("--size", default="1200x900")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="", help="JSON: per-frame results and the table")
    a = ap.parse_args()
    size = tuple(int(v) for v in a.size.split("x"))
    cells = matrix(a.hfov, size[0])
    if a.groups:
        cells = [c for c in cells if c["group"] in a.groups.split(",")]
    if a.match:
        cells = [c for c in cells if a.match in c["name"]]
    by_map: Dict[str, List[dict]] = {}
    for c in cells:
        by_map.setdefault(SCENES[c["scene"]]["map"], []).append(c)
    summaries, frames = [], {}
    print(HEADER, flush=True)
    for map_dir, cs in by_map.items():
        matcher = make_matcher(a.matcher, map_dir)
        imageries = {}
        for c in cs:
            scene = SCENES[c["scene"]]
            q = map_dir if scene["query"] == "map" else scene["query"]
            imagery = imageries.setdefault(q, dv.Imagery(q))
            nf = min(a.frames, c.get("frames", a.frames))
            rows = [run_one(matcher, imagery, scene, c, i, size, a.hfov, a.seed) for i in range(nf)]
            for s in summarize(c, rows):
                summaries.append(s)
                print(fmt(s), flush=True)
            frames[c["name"]] = rows
            if a.out:
                with open(a.out, "w") as fh:
                    json.dump(dict(args=vars(a), summary=summaries, frames=frames), fh, indent=0, default=str)
        del matcher
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:                          # noqa: BLE001 — SIFT only
            pass


if __name__ == "__main__":
    main()
