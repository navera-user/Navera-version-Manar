#!/usr/bin/env python3
"""Replay recorded real-camera day runs through the day guards, offline (F20, F16 / D17, F23).

Inputs are the bench logs that were kept (the 76-run campaign recorded no frames):

- screen_flight CSVs (campaign_day_real.sh, 2026-10-19: 76 runs; the re-check and day-image sets of
  2026-10-19/20): per frame, the match the live track gate let through, its inliers and its error
  vector. The truth is the circuit flown (radius 900 m at the run's speed, a left turn), the camera
  axis offset the median of the GPS-phase matches (as navera_tools/sim/gate_replay.py). The live run
  already refused some matches (column 'gated'): their vectors were not logged, so a replay can only
  refuse MORE, not believe more. 'night' (no match at all) and 'worst' (six conditions) are left out.
- screen_mission CSVs (campaigns 4-7, ~/.navera_sim/bench_2026-10-06): every matcher result with the
  IMU heading the mission simulated (+-5 deg); the truth integrated from it at 25 m/s.

Each run's GPS-lost part goes through day_pkg.vision_nav.VisionNavigator (the node's rules, pure
Python), the heading carried by a simulated gyro as the node does (GyroSim: the true turn rate + a
0.1 deg/s bias + noise, reset from each fix's heading +-2 deg) unless said otherwise, 3 seeds:

  base       the rules of feat/field-sky-test d77f8c4 (strong fixes gated at 6 sigma, no blending)
  product    the defaults of 2026-10-22: day_pkg.fix_consistency (strong fixes at 3 sigma) and
             blend_fixes (a fix averaged with the carried position by their sigmas: heading known)
  sigma 30   the same with every fix's sigma at least 30 m (the node's floor without calibration)
  reacq      + FixConsistency's re-acquisition check (reacquire_confirm)
  rate N     + day_pkg.frame_gate refusing frames smeared > N px. The bench camera did not move, the
             scene did ('wind': screen_overlays._shake; 'vibration': its turn and blur): the rate a
             camera gyro would have measured is the overlay's own at the frame time (26 screen px/deg),
             over a 1/60 s exposure and the bench view (1200 px over 100 deg)
  confirm_n  D17 (2026-10-23): a far-off fix on a good track is believed after 3 agreeing doubted
             fixes in a row (2 until 10-22; 2 still while lost)
  hypotheses D17 (2026-10-23): day_pkg.fix_hypotheses instead of the confirmation rule — alternative
             tracks; a far-off fix while the carried sigma is 30-250 m (or a doubted one) becomes the track
             after 3+ agreeing fixes that lead (the node default since); 'far max inf': at any sigma
  inject     F16 fault injection: 5 % of the lost matches replaced by confident wrong ones (100-650 m,
             100-228 inliers, as the 2026-10-19 hand-tilt run), alone or two in a row (burst 2)

    python3 navera_tools/bench/replay_day_guards.py [--flights DIR ...] [--missions DIR] [--part all]
    --part heading: F23 — blend_fixes with no heading / the true one / the gyro-carried one
"""
import argparse
import csv
import glob
import math
import os
import random
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "day_pkg"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from day_pkg.fix_consistency import FixConsistency  # noqa: E402
from day_pkg.fix_hypotheses import FixHypotheses  # noqa: E402
from day_pkg.gyro_heading import GyroHeading  # noqa: E402
from day_pkg.image_quality import gyro_blur_px  # noqa: E402
from day_pkg.local_matcher import fix_sigma_m  # noqa: E402
from day_pkg.vision_nav import VisionNavigator, _en, _move  # noqa: E402
from screen_overlays import Overlays  # noqa: E402

P0 = (35.82227, 10.61691)
MAP_MPP = 0.97                      # z17 at 35.8 deg
PPD = 26.0                          # screen px per camera degree (screen_overlays)
BENCH_FOCAL_PX = 0.5 * 1200 / math.tan(math.radians(50.0))   # 1200 px over 100 deg
EXPOSURE_S = 1.0 / 60.0
_OV = Overlays.__new__(Overlays)
_OV.ppd = PPD


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def overlay_of(name):
    """('wind' | 'vibration' | other, amount) from a run's file name."""
    m = re.search(r"(wind|vib|vibration)_?a?(0\.\d|\d\d)", name)
    if not m:
        return None, 0.0
    a = m.group(2)
    amt = float(a) if "." in a else float(a) / 10.0
    return ("wind" if m.group(1) == "wind" else "vibration"), amt


def bench_rate_dps(kind, amount, t):
    """|omega| (deg/s) a camera gyro would have measured if the camera had moved as the scene did: the
    largest over the exposure +-20 ms (the frame time is known to ~+-25 ms)."""
    if kind is None:
        return 0.0
    best = 0.0
    for d in np.linspace(-0.02 - EXPOSURE_S / 2, 0.02 + EXPOSURE_S / 2, 9):
        tt = t + d
        if kind == "wind":
            _, _, vx, vy = _OV._shake(tt, amount)
            best = max(best, math.hypot(vx, vy) / PPD)
        else:
            gust = 1.0 + 1.5 * max(0.0, math.sin(2 * math.pi * tt / 8.0)) ** 8
            amp = (0.3 + 1.7 * amount) * gust
            om = amp * sum(2 * math.pi * fr * math.cos(2 * math.pi * fr * tt + ph) / (1 + 0.6 * i)
                           for i, (fr, ph) in enumerate(((3.1, 0.2), (5.3, 1.3), (8.9, 2.2), (11.7, 0.9))))
            L = (4 + 36 * amount) * gust * (0.7 + 0.3 * math.sin(2 * math.pi * 0.37 * tt))   # screen px blur
            best = max(best, abs(om), L / PPD / EXPOSURE_S)
    return best


def load_flight(path):
    """screen_flight rows -> list of frames (dict), the run's speed."""
    speed = float(re.search(r"_v(\d+)", os.path.basename(path)).group(1))
    rows = list(csv.DictReader(open(path)))
    g = [r for r in rows if r["phase"] == "gps" and r["matched"] == "1" and r["vis_de"]]
    if len(g) < 3:
        return None, speed
    axis = (float(np.median([float(r["vis_de"]) for r in g])), float(np.median([float(r["vis_dn"]) for r in g])))
    kind, amt = overlay_of(os.path.basename(path))
    out, w = [], speed / 900.0
    for r in rows:
        t = float(r["t"])
        ang = w * t
        truth = _move(P0, 900.0 * math.sin(ang), 900.0 * (1 - math.cos(ang)))
        hdg = math.degrees(math.atan2(math.cos(ang), math.sin(ang))) % 360.0
        fix = None
        if r["matched"] == "1" and r["vis_de"]:
            fix = _move(truth, float(r["vis_de"]) - axis[0], float(r["vis_dn"]) - axis[1])
        out.append(dict(t=t, gps=r["phase"] != "lost", truth=truth, fix=fix, inl=int(f(r["inliers"]) or 0),
                        spread=1.0, hdg=hdg, rate=bench_rate_dps(kind, amt, t),
                        turn_dps=-math.degrees(w)))          # a left circuit: the heading decreases
    return out, speed


def load_mission(path, speed=25.0):
    rows = list(csv.DictReader(open(path)))
    out, p, tp, hp = [], P0, None, None
    for r in rows:
        t, h = float(r["t"]), float(r["heading"])
        turn = 0.0
        if tp is not None:
            p = _move(p, speed * (t - tp) * math.sin(math.radians(h)), speed * (t - tp) * math.cos(math.radians(h)))
            turn = ((h - hp + 180) % 360 - 180) / max(t - tp, 1e-3)
        tp, hp = t, h
        fix = None
        if r["matched"] == "1" and r["vision_e"] not in ("", None):
            fix = _move(p, float(r["vision_e"]), float(r["vision_n"]))
        out.append(dict(t=t, gps=r["gps"] == "1", truth=p, fix=fix, inl=int(f(r["inliers"]) or 0),
                        spread=f(r["spread"]) or 1.0, hdg=h, rate=0.0, turn_dps=turn))
    return out, speed


class GyroSim:
    """The product's gyro-heading carry on a simulated gyro: the true turn rate + bias + noise at 100 Hz,
    reset from each map fix's heading (+-2 deg) with >= 20 inliers (day_subscriber._gyro_reset)."""

    def __init__(self, seed=1, bias_dps=0.1, noise=0.004):
        self.rng = random.Random(seed)
        self.bias = self.rng.choice((-1, 1)) * bias_dps
        self.noise = noise
        self.g = GyroHeading(bias_dps, noise, 2.0, 10.0)
        self.t = None

    def step(self, t, turn_dps):
        t0 = t if self.t is None else self.t
        n = max(1, int((t - t0) * 100))
        for i in range(1, n + 1):
            self.g.add_rate(t0 + (t - t0) * i / n, turn_dps + self.bias + self.rng.gauss(0, self.noise * 10))
        self.t = t

    def heading(self, t):
        h = self.g.at(t)
        return None if h is None else h[0]

    def reset(self, t, hdg):
        self.g.reset(t, (hdg + self.rng.gauss(0, 2.0)) % 360.0)


def inject(frames, seed, rate=0.05, burst=1):
    """F16 fault injection: a copy of the frames where ~rate of the GPS-lost matches are replaced by a
    confident wrong one (100-650 m off in a random direction, 100-228 inliers: the 2026-10-19 hand-tilt
    run's wrong matches), burst frames in a row at the same wrong place (carried with the vehicle)."""
    rng = random.Random(seed)
    out, left, off, inl = [], 0, None, 0
    for fr in frames:
        fr = dict(fr)
        if not fr["gps"] and fr["fix"]:
            if left == 0 and rng.random() < rate:
                left, a, d, inl = burst, rng.uniform(0, 2 * math.pi), rng.uniform(100, 650), rng.randint(100, 228)
                off = (d * math.sin(a), d * math.cos(a))
            if left > 0:
                fr["fix"], fr["inl"], fr["injected"] = _move(fr["truth"], *off), inl, True
                left -= 1
        out.append(fr)
    return out


def run(frames, speed, variant, vmax=None, heading="none", seed=1):
    """Per GPS-lost frame: dict(out_err, sigma, measured, vis_err, used)."""
    cons = None
    if variant.get("confirm"):
        cons = FixConsistency(strong_gate_k=variant.get("strong_k", 3.0),
                              reacquire_check=variant.get("reacq", True),
                              confirm_n=variant.get("confirm_n", 3), confirm_lost_n=variant.get("confirm_lost_n", 2))
    hyp = None
    if cons is not None and variant.get("mht") is not None:
        hyp = FixHypotheses(cons, **variant["mht"])
    nav = VisionNavigator(max_speed_mps=vmax or 1.5 * speed, consistency=cons, hypotheses=hyp,
                          blend_fixes=variant.get("blend", False),
                          blend_below_inliers=variant.get("blend_below", 10 ** 9))
    gyro = GyroSim(seed) if heading == "gyro" else None
    max_rate = variant.get("max_blur_px")
    res = []
    for fr in frames:
        t = fr["t"]
        if gyro is not None:
            gyro.step(t, fr["turn_dps"])
        hdg = fr["hdg"] if heading == "true" else (gyro.heading(t) if gyro else None)
        if fr["gps"]:
            nav.gps(t, *fr["truth"], heading_deg=hdg if heading != "gyro" else fr["hdg"])
            if gyro is not None:
                gyro.reset(t, fr["hdg"])
            continue
        fix, used = fr["fix"], False
        verr = math.hypot(*_en(fix, fr["truth"])) if fix else None
        if fix and max_rate is not None and gyro_blur_px(fr["rate"], EXPOSURE_S, BENCH_FOCAL_PX) > max_rate:
            fix = None                                     # FrameGate: not matched at all
        if fix:
            r = dict(accepted=True, predicted_lat=fix[0], predicted_lon=fix[1], inliers=fr["inl"],
                     spread=fr["spread"], scale_residual=1.0,
                     sigma_m=max(fix_sigma_m(fr["inl"], MAP_MPP), variant.get("sigma_floor", 0.0)))
            used = nav.update(t, r, None, hdg, gps_valid=False)
            if used and gyro is not None and fr["inl"] >= 20:
                gyro.reset(t, fr["hdg"])
        lat, lon, sig, m = nav.output(t, hdg)
        e = math.hypot(*_en((lat, lon), fr["truth"])) if lat is not None else None
        res.append(dict(out=e, sig=sig, meas=m == "measured", verr=verr, used=used))
    return res


def summary(res):
    errs = np.array([r["out"] for r in res if r["out"] is not None] or [np.nan])
    meas = [r for r in res if r["meas"]]
    cov = [r for r in res if r["out"] is not None and r["sig"] is not None]
    return dict(
        frames=len(res), avail=len([r for r in res if r["out"] is not None]),
        used=sum(r["used"] for r in res),
        wrong_vis=sum(1 for r in res if r["verr"] is not None and r["verr"] > 50),
        wrong_used=sum(1 for r in res if r["verr"] is not None and r["verr"] > 50 and r["used"]),
        good_lost=sum(1 for r in res if r["verr"] is not None and r["verr"] <= 20 and not r["used"]),
        good=sum(1 for r in res if r["verr"] is not None and r["verr"] <= 20),
        wrong_meas=sum(1 for r in meas if r["out"] is not None and r["out"] > 50),
        wrong_any=int(np.sum(errs > 50)), med=float(np.nanmedian(errs)), p95=float(np.nanpercentile(errs, 95)),
        mx=float(np.nanmax(errs)), in3=sum(1 for r in cov if r["out"] <= 3 * r["sig"]), ncov=len(cov))


def fmt(name, s):
    return (f"| {name} | {s['frames']} | {s['avail']} | {s['used']} | {s['wrong_vis']} | {s['wrong_used']} | "
            f"{s['good_lost']}/{s['good']} | **{s['wrong_meas']}** | {s['wrong_any']} | {s['med']:.1f} | "
            f"{s['p95']:.0f} | {s['mx']:.0f} | {s['in3']}/{s['ncov']} |")


HEADER = ("| set / variant | lost frames | with output | fixes used | vision > 50 m | of them used | right (<= 20 m) "
          "not used | measured output > 50 m | any output > 50 m | median m | p95 m | max m | within 3 sigma |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def merge(rs):
    out = []
    for r in rs:
        out.extend(r)
    return out


def load_all(flight_dirs, missions_dir):
    flights = []
    for d in flight_dirs:
        for p in sorted(glob.glob(os.path.join(d, "*_v*.csv"))):
            if "night" in os.path.basename(p) or "worst" in os.path.basename(p):
                continue
            fr, sp = load_flight(p)
            if fr:
                flights.append((p, fr, sp))
    missions = []
    for p in sorted(glob.glob(os.path.join(missions_dir, "camp[4-7]_*.csv"))):
        fr, sp = load_mission(p)
        if any(x["fix"] for x in fr if not x["gps"]):
            missions.append((p, fr, sp))

    def group(pred):
        return [x for x in flights if pred(os.path.basename(x[0]))]
    return [("wind (scene shaken)", group(lambda n: n.startswith("wind"))),
            ("vibration", group(lambda n: n.startswith("vib"))),
            ("other conditions", group(lambda n: not n.startswith(("wind", "vib")))),
            ("missions camp4-7", missions)]


def replay(runs, variant, heading="gyro", seeds=(1, 2, 3), burst=0):
    """summary() over the runs and seeds, plus (injected, injected used) with burst > 0."""
    rs, inj, inj_used = [], 0, 0
    for p, fr, sp in runs:
        for seed in seeds:
            f2 = inject(fr, seed, burst=burst) if burst else fr
            res = run(f2, sp, variant, vmax=40.0 if "camp" in os.path.basename(p) else None,
                      heading="true" if heading == "true" or (heading == "mission" and "camp" in p) else heading,
                      seed=seed)
            for x, r in zip([x for x in f2 if not x["gps"]], res):
                if x.get("injected"):
                    inj += 1
                    inj_used += r["used"]
            rs += res
    return summary(rs), inj, inj_used


BASE = dict(strong_k=6.0, confirm=True, reacq=False, confirm_n=2)
PRODUCT = dict(confirm=True, reacq=False, blend=True)              # confirm_n 3 since 2026-10-23 (D17)
PRODUCT_22 = dict(PRODUCT, confirm_n=2)                             # the product of 2026-10-22
HYPOTHESES = dict(PRODUCT, mht={})                                   # D17, the node default since 2026-10-23


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flights", nargs="*", default=[
        os.path.expanduser("~/navera-field/day_real_2026-10-19"),
        os.path.expanduser("~/navera-field/day_recheck_2026-10-19"),
        os.path.expanduser("~/navera-field/day_image_2026-10-20/before"),
        os.path.expanduser("~/navera-field/day_image_2026-10-20/pairs")])
    ap.add_argument("--missions", default=os.path.expanduser("~/.navera_sim/bench_2026-10-06"))
    ap.add_argument("--part", choices=("all", "guards", "heading", "inject"), default="all")
    a = ap.parse_args()
    sets = load_all(a.flights, a.missions)
    print(f"{sum(len(r) for n, r in sets[:3])} screen_flight runs, {len(sets[3][1])} screen_mission runs, 3 seeds\n")
    if a.part in ("all", "guards"):
        print("F20 / F16 / D17 — the guards, gyro-carried heading\n")
        print(HEADER)
        variants = [("base", BASE), ("product 10-22 (2 agreeing)", PRODUCT_22), ("product", PRODUCT), ("product, sigma >= 30 m", dict(PRODUCT, sigma_floor=30.0)),
                    ("product + reacq", dict(PRODUCT, reacq=True)), ("hypotheses", HYPOTHESES)]
        variants += [(f"product + rate {b} px", dict(PRODUCT, max_blur_px=b)) for b in (6.0, 10.0, 15.0)]
        for name, runs in sets:
            for vn, v in variants:
                if "rate" in vn and name.startswith(("other", "missions")):
                    continue                        # no shake there: identical to product
                print(fmt(f"{name} / {vn}", replay(runs, v)[0]))
        print()
    if a.part in ("all", "heading"):
        print("F23 — blend_fixes and the heading (strong fixes at 3 sigma)\n")
        print(HEADER)
        for name, runs in sets:
            for hd in ("none", "true", "gyro"):
                for blend in (False, True):
                    v = dict(confirm=True, reacq=False, blend=blend)
                    print(fmt(f"{name} / heading {hd} / {'blend' if blend else 'no blend'}", replay(runs, v, hd)[0]))
        print()
    if a.part in ("all", "inject"):
        print("F16 — injected confident wrong matches (5 % of the lost matches, 100-650 m, 100-228 inliers)\n")
        print("| set / burst / variant | injected | believed | " + HEADER.split("| set / variant | ")[1])
        flights = [x for n, r in sets[:3] for x in r]
        for burst in (1, 2):
            for name, runs in (("flights", flights), ("missions", sets[3][1])):
                for vn, v in (("base", BASE), ("strong 3 sigma", dict(BASE, strong_k=3.0)),
                              ("product 10-22 (2 agreeing)", PRODUCT_22), ("product (3 agreeing, 2 lost)", PRODUCT),
                              ("product, 3 agreeing lost too", dict(PRODUCT, confirm_lost_n=3)),
                              ("product + reacq", dict(PRODUCT, reacq=True)), ("hypotheses", HYPOTHESES),
                              ("hypotheses, far max inf", dict(PRODUCT, mht=dict(far_max_sigma_m=float("inf"))))):
                    s, inj, used = replay(runs, v, burst=burst)
                    print(f"| {name} / {burst} / {vn} | {inj} | {used} " + fmt("", s)[3:])


if __name__ == "__main__":
    main()
