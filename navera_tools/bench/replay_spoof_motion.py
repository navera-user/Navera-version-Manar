#!/usr/bin/env python3
"""Replay real recordings through the product's GPS refusal rules, without and with the relative-motion
test (navera_common.gps_motion_check.GpsMotionCheck: GPS displacement vs visual odometry):

    python3 navera_tools/bench/replay_spoof_motion.py --bench REC_PARENT_DIR [...] \
        --visloc UAVVISLOC_DIR [...] --visloc-results DIR --cache DIR [--vo-scale 0.5] [--vo-period 0.9] \
        [--synthetic-hours 40]

Sources (the VO is computed once per recording with day_pkg.frame_odometry.FrameOdometry, as the day
node does while GPS is trusted, and cached under --cache):
  * --bench: screen-bench runs recorded by screen_flight --record (rec_<name>/frames.jsonl + JPEGs) and
    their CSV <name>.csv: the truth of every frame, the vision fix error (vis_de/vis_dn minus the
    camera axis, as replay_spoof_trend.py) at one fix per --cadence s (gps_check_period_s);
  * --visloc: UAV-VisLoc flights (photos 1-5 s apart; the GPS labels are the honest GPS; the map fixes
    and their errors from uavvisloc_eval.py results f<NN>_guard4.json in --visloc-results; flight 06
    photos 99-180 have wrong GPS labels: left out, a gap);
  * --synthetic-hours: long honest flights (straight legs, turns, 0-60 m/s, hover), VO with the
    per-step noise and the scale / heading error measured on the bench, map fixes 15-37 m with a
    wandering bias and wrong fixes, GPS with a Gauss-Markov wander — false refusals only.
The honest GPS is the truth plus a Gauss-Markov wander (--gps-gm-m, 60 s) and white noise
(--gps-white-m) (the bench GPS was the truth itself). Drifts are injected at 0.5 / 1 / 3 / 5 m/s in
three directions from the drift start (bench: the recorded drift phase; UAV-VisLoc: every 240 s).
Printed: false refusals with a good GPS, and the drift at the first refusal (median / p90), size +
growth rules (GpsCrossCheck + GpsDriftTrend, today's product) vs the same plus the motion test.
"""
import argparse
import csv
import glob
import json
import math
import os
import random
import statistics as st
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "day_pkg")]
from day_pkg.local_matcher import fix_sigma_m  # noqa: E402
from navera_common.gps_crosscheck import GpsCrossCheck, GpsDriftTrend  # noqa: E402
from navera_common.gps_motion_check import GpsMotionCheck  # noqa: E402

M_LAT = 111320.0
GPS_SIGMA_M = 2.5


def en(p, ref):
    """(east, north) metres of lat/lon p from ref."""
    return ((p[1] - ref[1]) * M_LAT * math.cos(math.radians(ref[0])), (p[0] - ref[0]) * M_LAT)


def vo_steps(images, scale, period, max_dt):
    """[(i0, i1, de, dn)] FrameOdometry steps over images [(t, path, heading, mpp, grey)], one frame
    every period s at most (frame indices)."""
    import cv2
    from day_pkg.frame_odometry import FrameOdometry
    vo = FrameOdometry(scale=scale, max_dt_s=max_dt)
    out, last = [], None
    for i, (t, path, hdg, mpp, reduce) in enumerate(images):
        if last is not None and t - images[last][0] < period:
            continue
        img = cv2.imread(path, cv2.IMREAD_REDUCED_GRAYSCALE_4 if reduce else cv2.IMREAD_GRAYSCALE)
        if img is None:
            vo.reset()
            last = None
            continue
        r = vo.step(img, hdg, mpp * (4.0 if reduce else 1.0), t)
        if r is not None and last is not None:
            out.append((last, i, r[0], r[1]))
        last = i
    return out


def cached(cache, key, fn):
    path = os.path.join(cache, key.replace("/", "_") + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    v = fn()
    os.makedirs(cache, exist_ok=True)
    json.dump(v, open(path, "w"))
    return v


# ---------------------------------------------------------------- recordings -> flights

def load_bench(rec_dir, a):
    """A flight dict: t[], truth[] (east, north m), fixes [(frame i, err_e, err_n, sigma)], vo [(i0, i1, de, dn)]."""
    name = os.path.basename(rec_dir)[4:]
    fr = [json.loads(x) for x in open(os.path.join(rec_dir, "frames.jsonl"))]
    rows = list(csv.DictReader(open(os.path.join(os.path.dirname(rec_dir), name + ".csv"))))
    if len(rows) != len(fr):
        return None
    ref = fr[0]["truth"]
    t = [f["t"] for f in fr]
    truth = [en(f["truth"], ref) for f in fr]
    g = [r for r in rows if r["phase"] == "gps" and r["vis_de"] not in ("", "None")]
    ax = (st.median(float(r["vis_de"]) for r in g), st.median(float(r["vis_dn"]) for r in g))
    fixes, last = [], None
    for i, r in enumerate(rows):
        if r["vis_de"] in ("", "None") or (last is not None and t[i] < last + a.cadence - 0.25):
            continue
        last = t[i]
        fixes.append((i, float(r["vis_de"]) - ax[0], float(r["vis_dn"]) - ax[1],
                      max(fix_sigma_m(int(float(r["inliers"] or 0)), 156543.03392 * math.cos(math.radians(35.82227))
                                      / 2 ** 17), 30.0)))
    images = [(f["t"], os.path.join(rec_dir, f["file"]), f["rot_deg"], f["mpp"] or fr[0]["mpp"], False) for f in fr]
    vo = cached(a.cache, f"bench_{name}_{a.vo_scale}_{a.vo_period}",
                lambda: vo_steps(images, a.vo_scale, a.vo_period, 2.5))
    t_drift = next((t[i] for i, r in enumerate(rows) if r["phase"] != "gps"), None)
    return dict(name=name, t=t, truth=truth, fixes=fixes, vo=vo, drift_starts=[t_drift] if t_drift else [])


def load_visloc(flight_dir, res_dir, a):
    fl = os.path.basename(flight_dir.rstrip("/"))
    rows = list(csv.DictReader(open(os.path.join(flight_dir, fl + ".csv"))))
    res = json.load(open(os.path.join(res_dir, f"f{fl}_guard4.json")))
    hfov = res["summary"]["hfov"]
    gp = os.path.join(res_dir, f"ground_{fl}.csv")
    ground = {r["filename"]: float(r["ground_m"]) for r in csv.DictReader(open(gp))} if os.path.exists(gp) else {}
    bad = set(range(99, 181)) if fl == "06" else set()
    t0 = datetime.fromisoformat(rows[0]["date"])
    t = [(datetime.fromisoformat(r["date"]) - t0).total_seconds() for r in rows]
    ref = (float(rows[0]["lat"]), float(rows[0]["lon"]))
    truth = [en((float(r["lat"]), float(r["lon"])), ref) for r in rows]
    by_file = {f["file"]: f for f in res["frames"]}
    fixes, last = [], None
    for i, r in enumerate(rows):
        f = by_file.get(r["filename"])
        if i + 1 in bad or f is None or not f["accepted"] or (last is not None and t[i] < last + a.cadence - 0.25):
            continue
        last = t[i]
        fixes.append((i, f["east_m"], f["north_m"], max(f.get("stated_sigma_m") or 30.0, 30.0)))

    def images():
        out = []
        for i, r in enumerate(rows):
            h = float(r["height"]) - ground.get(r["filename"], 0.0)
            path = os.path.join(flight_dir, "drone", r["filename"])
            # the photo reduced 4 x (994 px wide): mpp of that width
            out.append((t[i], path if i + 1 not in bad else "/nonexistent",
                        float(r["Phi2"]) % 360.0, 2 * h * math.tan(math.radians(hfov) / 2) / 3976.0, True))
        return out
    vo = cached(a.cache, f"visloc_{fl}_{a.vo_scale}", lambda: vo_steps(images(), a.vo_scale, 0.0, 6.0))
    # one flight per stretch of photos in time order (flight 06 holds several sessions out of order) and
    # without a wrong label
    cuts = [0] + [i for i in range(1, len(t)) if t[i] <= t[i - 1] or (i + 1 in bad) != (i in bad)]
    out = []
    for k, (i0, i1) in enumerate(zip(cuts, cuts[1:] + [len(t)])):
        if i0 + 1 in bad or t[i1 - 1] - t[i0] < 120.0:
            continue
        out.append(dict(name=f"visloc{fl}" + (f".{k}" if len(cuts) > 1 else ""), t=t, truth=truth,
                        fixes=[f for f in fixes if i0 <= f[0] < i1],
                        vo=[s for s in vo if i0 <= s[0] and s[1] < i1],
                        drift_starts=[x for x in range(int(t[i0]) + 120, int(t[i1 - 1]) - 120, 240)]))
    return out


# ---------------------------------------------------------------- the rules

class GpsNoise:
    """Gauss-Markov wander (sigma gm, 60 s) + white noise, sampled at arbitrary times in order."""

    def __init__(self, gm, white, seed):
        self.rng, self.gm, self.white = random.Random(seed), gm, white
        self.t, self.x = None, (0.0, 0.0)
        self.cache = {}

    def at(self, t):
        if t in self.cache:
            return self.cache[t]
        if self.t is None:
            self.x = (self.rng.gauss(0, self.gm), self.rng.gauss(0, self.gm))
        else:
            phi = math.exp(-max(t - self.t, 0.0) / 60.0)
            q = self.gm * math.sqrt(max(1 - phi * phi, 0.0))
            self.x = tuple(phi * v + self.rng.gauss(0, q) for v in self.x)
        self.t = t
        v = (self.x[0] + self.rng.gauss(0, self.white), self.x[1] + self.rng.gauss(0, self.white))
        self.cache[t] = v
        return v


def motion_from_args(a):
    """GpsMotionCheck with the test parameters given on the command line (the class defaults otherwise)."""
    names = {"h": "h", "k": "k", "min_growth": "min_growth_m", "bias_mps": "bias_mps", "min_sigma": "min_sigma_m",
             "eps_floor": "eps_floor", "calib_recent_s": "calib_recent_s"}
    return GpsMotionCheck(**{kw: getattr(a, n) for n, kw in names.items() if getattr(a, n, None) is not None})


def replay(fl, drift, use_motion, a, seed=1):
    """(t, drift m, rule) of the first refusal or None. drift(t) -> (east, north) m added to GPS."""
    noise = GpsNoise(a.gps_gm_m, a.gps_white_m, seed)
    t, truth = fl["t"], fl["truth"]

    def gps(i):
        n, d = noise.at(t[i]), drift(t[i])
        return truth[i][0] + n[0] + d[0], truth[i][1] + n[1] + d[1]
    x = GpsCrossCheck(trend=GpsDriftTrend())
    m = motion_from_args(a) if use_motion else None
    ev = [(t[s[1]], 0, s) for s in fl["vo"]] + [(t[f[0]], 1, f) for f in fl["fixes"]]
    ev.sort(key=lambda e: (e[0], e[1]))
    for tt, kind, e in ev:
        if kind == 0:
            if m is None:
                continue
            i0, i1, de, dn = e
            g0, g1 = gps(i0), gps(i1)
            why = m.add_step(t[i0], t[i1], de, dn, g1[0] - g0[0], g1[1] - g0[1])
            rule = "motion"
        else:
            i, ee, en_, sig = e
            g = gps(i)
            fix = (truth[i][0] + ee, truth[i][1] + en_)
            oe, on = g[0] - fix[0], g[1] - fix[1]
            if m is not None:
                m.add_fix(tt, fix[0], fix[1], (oe, on))
            why = x.update(tt, math.hypot(oe, on), 5.0 * sig + 50.0, 3.0 * sig, tt, "day vision",
                           sample=(tt, oe, on, math.hypot(sig, GPS_SIGMA_M)))
            rule = "growth" if why and "grew" in why else "size"
        if why:
            return tt, math.hypot(*drift(tt)), rule, why
    return None


def summary(hits, v):
    got = sorted(h[1] for h in hits if h is not None and h[1] >= 0.25)
    early = sum(1 for h in hits if h is not None and h[1] < 0.25)
    if not got:
        return f"0/{len(hits)}"
    rules = {}
    for h in hits:
        if h is not None and h[1] >= 0.25:
            rules[h[2]] = rules.get(h[2], 0) + 1
    return (f"{len(got)}/{len(hits)} at {st.median(got):.0f} m (p90 {got[int(0.9 * (len(got) - 1))]:.0f} m, "
            f"{st.median(got) / v:.0f} s) {rules}{f', {early} before the drift' if early else ''}")


# ---------------------------------------------------------------- synthetic flights

def synthetic(hours, seed, a):
    """Honest flights for the false-refusal count (no images: VO from the measured error model)."""
    rng = random.Random(seed)
    flights = []
    for k in range(int(math.ceil(hours * 3600 / 1800.0))):
        dt_f = rng.choice((0.5, 1.0))
        n = int(1800 / dt_f)
        speed = rng.choice((0.0, 2.0, 8.0, 20.0, 35.0, 60.0))
        scale_err = rng.gauss(0, 0.03)              # uncalibrated scale error of this flight's VO
        rot_err = math.radians(rng.gauss(0, 1.0))
        vo_sig = rng.choice((0.5, 1.0, 2.0))        # per-step random VO error (bench: 0.7-3 m)
        fix_sig = rng.choice((10.0, 20.0, 30.0))
        hdg, turn = rng.uniform(0, 2 * math.pi), 0.0
        p = (0.0, 0.0)
        t, truth = [], []
        for i in range(n):
            if rng.random() < dt_f / 60.0:
                turn = rng.choice((0.0, 0.0, rng.uniform(-0.1, 0.1)))
            if rng.random() < dt_f / 300.0:
                speed = max(0.0, speed + rng.gauss(0, 8.0))
            hdg += turn * dt_f
            t.append(i * dt_f)
            truth.append(p)
            p = (p[0] + speed * dt_f * math.sin(hdg), p[1] + speed * dt_f * math.cos(hdg))
        vo, shake, target = [], 0j, 1.0 + scale_err
        scale = target
        for i in range(1, n):
            # the VO scale wanders (the height it uses) and now and then jumps (height recalibrated);
            # the day node scales the VO by its height smoothed over gps_vo_height_tau_s
            target += rng.gauss(0, 0.01 * math.sqrt(dt_f / 600.0))
            if rng.random() < dt_f / 600.0:
                target += rng.choice((-1, 1)) * rng.uniform(0.01, 0.04)
            w = 1.0 - math.exp(-dt_f / a.vo_height_tau_s) if a.vo_height_tau_s > 0 else 1.0
            scale += w * (target - scale)
            if rng.random() < 0.05:
                continue                             # VO failed on this frame
            c = scale * complex(math.cos(rot_err), math.sin(rot_err))
            d = complex(truth[i][0] - truth[i - 1][0], truth[i][1] - truth[i - 1][1]) / c
            new = complex(rng.gauss(0, vo_sig * 0.7), rng.gauss(0, vo_sig * 0.7))
            d += new - shake + complex(rng.gauss(0, vo_sig * 0.7), rng.gauss(0, vo_sig * 0.7))
            shake = new
            if rng.random() < 0.01:
                d = complex(rng.gauss(0, 30), rng.gauss(0, 30))   # wrong peak
            elif rng.random() < 0.01 and speed > 5:
                d = 0j                                           # lock on what does not move
            vo.append((i - 1, i, d.real, d.imag))
        fixes, bias, last = [], (rng.gauss(0, 0.5 * fix_sig), rng.gauss(0, 0.5 * fix_sig)), -1e9
        for i in range(n):
            if t[i] < last + a.cadence - 0.25 or rng.random() < 0.3:
                continue
            last = t[i]
            phi = math.exp(-a.cadence / 300.0)              # the map bias wanders (AR(1), 300 s)
            bias = tuple(phi * b + rng.gauss(0, 0.5 * fix_sig * math.sqrt(1 - phi * phi)) for b in bias)
            e = (bias[0] + rng.gauss(0, fix_sig * 0.7), bias[1] + rng.gauss(0, fix_sig * 0.7))
            if rng.random() < 0.02:
                e = (rng.uniform(-300, 300), rng.uniform(-300, 300))
            fixes.append((i, e[0], e[1], max(fix_sig, 30.0)))
        flights.append(dict(name=f"syn{k}", t=t, truth=truth, fixes=fixes, vo=vo, drift_starts=[]))
    return flights


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", nargs="*", default=[], help="directories holding rec_<name>/ and <name>.csv")
    ap.add_argument("--visloc", nargs="*", default=[], help="UAV-VisLoc directories holding <NN>/<NN>.csv + drone/")
    ap.add_argument("--visloc-results", default=os.path.expanduser("~/.navera_sim/uavvisloc/more"))
    ap.add_argument("--flights", default="01,03,04,05,06,08,10,11")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--cadence", type=float, default=2.0, help="s between map fixes (gps_check_period_s)")
    ap.add_argument("--vo-scale", type=float, default=1.0)
    ap.add_argument("--vo-period", type=float, default=0.9)
    ap.add_argument("--gps-gm-m", type=float, default=1.5)
    ap.add_argument("--gps-white-m", type=float, default=0.3)
    ap.add_argument("--synthetic-hours", type=float, default=0.0)
    ap.add_argument("--vo-height-tau-s", type=float, default=60.0,
                    help="synthetic: the VO height smoothed over this time (day node gps_vo_height_tau_s)")
    ap.add_argument("--h", type=float, default=GpsMotionCheck().h)
    ap.add_argument("--k", type=float, default=GpsMotionCheck().k)
    ap.add_argument("--min-growth", type=float, default=GpsMotionCheck().min_growth)
    ap.add_argument("--bias-mps", type=float, default=GpsMotionCheck().bias_mps)
    ap.add_argument("--min-sigma", type=float, default=GpsMotionCheck().min_sigma)
    ap.add_argument("--eps-floor", type=float, default=GpsMotionCheck().eps_floor)
    ap.add_argument("--calib-recent-s", type=float, default=GpsMotionCheck().cal_recent_s)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--speeds", default="0.5,1,3,5")
    a = ap.parse_args()
    flights = []
    for d in a.bench:
        for rec in sorted(glob.glob(os.path.join(d, "rec_*"))):
            f = load_bench(rec, a)
            if f:
                flights.append(f)
    if a.visloc:
        for fl in a.flights.split(","):
            fd = next((os.path.join(d, fl) for d in a.visloc if os.path.exists(os.path.join(d, fl, fl + ".csv"))), None)
            if fd is not None:
                flights += load_visloc(fd, a.visloc_results, a)
            else:
                print(f"flight {fl}: no {fl}.csv, skipped")
    syn = synthetic(a.synthetic_hours, 7, a) if a.synthetic_hours > 0 else []
    for f in flights:
        idx = [x[0] for x in f["fixes"]] + [x[1] for x in f["vo"]]
        dur = (f["t"][max(idx)] - f["t"][min(idx)]) if idx else 0.0
        print(f"{f['name']:22s} {dur:6.0f} s, {len(f['fixes'])} map fixes, {len(f['vo'])} VO steps")
    if syn:
        print(f"synthetic: {len(syn)} flights, {sum(f['t'][-1] for f in syn) / 3600:.1f} h")
    for use_motion in (False, True):
        label = "size + growth + motion" if use_motion else "size + growth (today)"
        false = []
        for f in flights + syn:
            for s in range(a.seeds if f in flights else 1):
                r = replay(f, lambda t: (0.0, 0.0), use_motion, a, seed=s)
                if r:
                    false.append((f["name"], s, round(r[0], 1), r[2], r[3]))
        print(f"{label}: false refusals with a good GPS {len(false)}")
        for x in false[:20]:
            print("    ", x)
        for v in [float(x) for x in a.speeds.split(",")]:
            for group in ("bench", "visloc"):
                hits = []
                for f in flights:
                    if f["name"].startswith("visloc") != (group == "visloc"):
                        continue
                    for td in f["drift_starts"]:
                        for ang in (0.0, 90.0, 225.0):
                            ce, cn = math.cos(math.radians(ang)), math.sin(math.radians(ang))

                            def drift(t, td=td, ce=ce, cn=cn):
                                return v * max(0.0, t - td) * ce, v * max(0.0, t - td) * cn
                            hits.append(replay(f, drift, use_motion, a))
                if hits:
                    print(f"    {group:6s} {v:g} m/s: refused {summary(hits, v)}")


if __name__ == "__main__":
    main()
