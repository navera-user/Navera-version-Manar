#!/usr/bin/env python3
"""Validate sunmoon (Sun/Moon line of position) on synthetic frames and on real 360 sessions.

    python3 -m cn_pkg.sunmoon_validate synth [--n 60] [--body sun|moon] [--bg FRAME.jpg] [--out rows.jsonl]
    python3 -m cn_pkg.sunmoon_validate real SESSION [SESSION ...] [--truth LAT,LON] [--every N]

synth: the body is drawn into a background frame (a real frame of the camera: its lamps and windows are the
distractors) at its true place for a random time, heading and camera tilt, through the calibrated lens model;
the solver then gets 'up' with a random error (SIGMA_UP_DEG) and a lens mounting that is off by a random
rotation (SIGMA_LENS_DEG), the prior 30 km off. Reported: altitude error, the error across the line, the fix
error and how many errors exceed 3 sigma.
real: every saved frame of the sessions (frames.jsonl: up_imu, t_exp), prior = the true place (session's phone
GPS or --truth) with 30 km; any sight accepted where no Sun/Moon is visible is a WRONG sight.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "navera_common")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cn_pkg import sunmoon as sm  # noqa: E402
from cn_pkg.sky360 import default_lenses  # noqa: E402


def rot_about(axis, ang_rad):
    a = sm._unit(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(ang_rad) * K + (1 - math.cos(ang_rad)) * K @ K


def pose(up_imu, heading_deg):
    """R (ENU → IMU) with ENU up mapped to up_imu and the rest turned by heading_deg about it."""
    up = sm._unit(up_imu)
    t = np.array([1.0, 0, 0]) if abs(up[0]) < 0.9 else np.array([0, 1.0, 0])
    e = sm._unit(np.cross(t, up))
    n = np.cross(up, e)
    R = np.stack([e, n, up], axis=1)                     # columns: ENU east, north, up in IMU
    return R @ rot_about([0, 0, 1], math.radians(heading_deg))


def enu_vec(alt_deg, az_deg):
    a, z = math.radians(alt_deg), math.radians(az_deg)
    return np.array([math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a)])


def render_body(frame, lenses, ray_imu, radius_deg, bloom_deg=0.6, halo_deg=2.0, halo_dn=120.0, lit=1.0,
                sun_dir_imu=None, level=255.0):
    """Draw a disc (with saturated bloom and a halo) centred on ray_imu into the 8-bit gray frame. Moon: lit < 1
    and sun_dir_imu (unit, from the Moon towards the Sun, IMU frame) keep only the lit part of the disc."""
    from cn_pkg.allsky import unproject
    out = frame.astype(np.float32).copy()
    m = sm._unit(ray_imu)
    for L in lenses:
        v = L.R_lens_imu @ m
        if v[2] < math.cos(math.radians(97)):
            continue
        x, y, th = L.project(v[None])
        x, y = float(x[0]), float(y[0])
        if math.degrees(th[0]) > 95:
            continue
        rad = int(math.radians(radius_deg + bloom_deg + 4 * halo_deg) * L.f) + 4
        x0, y0 = max(0, int(x) - rad), max(0, int(y) - rad)
        x1, y1 = min(frame.shape[1], int(x) + rad + 1), min(frame.shape[0], int(y) + rad + 1)
        if x1 <= x0 or y1 <= y0:                                  # projected outside the frame
            continue
        # 4x supersampled
        ss = 4
        yy, xx = np.mgrid[y0:y1:1.0 / ss, x0:x1:1.0 / ss]
        rays = unproject(L, xx.ravel() + 0.5 / ss - 0.5, yy.ravel() + 0.5 / ss - 0.5)
        rays = rays / np.linalg.norm(rays, axis=1, keepdims=True)
        ang = np.degrees(np.arccos(np.clip(rays @ m, -1, 1))).reshape(xx.shape)
        inside = ang < radius_deg
        if lit < 0.999 and sun_dir_imu is not None:
            s_t = sm._unit(sun_dir_imu - np.dot(sun_dir_imu, m) * m)
            p_t = np.cross(m, s_t)
            d = rays.reshape(xx.shape + (3,))
            px = (d @ s_t) / math.sin(math.radians(radius_deg))     # disc coordinates, x towards the Sun
            py = (d @ p_t) / math.sin(math.radians(radius_deg))
            pz = np.sqrt(np.clip(1 - px ** 2 - py ** 2, 0, 1))
            i = math.acos(2 * lit - 1)                                # phase angle
            inside &= (px * math.sin(i) + pz * math.cos(i)) > 0
        val = np.zeros_like(ang)
        val[inside] = level
        if bloom_deg > 0:
            from scipy.ndimage import distance_transform_edt
            dist = distance_transform_edt(~inside) / (ss * L.f) * 180 / math.pi     # deg from the lit disc
            val = np.maximum(val, np.where(dist < bloom_deg, level, 0))
            val = np.maximum(val, halo_dn * np.exp(-dist / halo_deg))
        v2 = val.reshape(y1 - y0, ss, x1 - x0, ss).mean(axis=(1, 3))
        sub = out[y0:y1, x0:x1]
        out[y0:y1, x0:x1] = sub + v2 * (1 - sub / 255.0)              # light adds, saturates at 255
    return np.clip(out, 0, 255).astype(np.uint8)


def lens_off(lenses, sigma_deg, rng):
    """A copy of the lenses with their mounting turned by a random small rotation (the unknown mount error)."""
    import copy
    out = []
    ax = rng.normal(size=3)
    R = rot_about(ax, math.radians(abs(rng.normal(0, sigma_deg)) * math.sqrt(1.5)))
    for L in lenses:
        L2 = copy.copy(L)
        L2.R_lens_imu = L.R_lens_imu @ R
        out.append(L2)
    return out


def utc_str(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def synth_case(rng, body, bg, up_true, truth, day0, lenses, jpeg=True, prior_km=30.0):
    """One synthetic frame → (row of results). The body is placed for a random time when it is >= 5 deg up."""
    import cv2
    lat, lon = truth
    for _ in range(400):
        t = day0 + rng.uniform(0, 86400)
        utc = utc_str(t)
        place = sm.body_place(body, utc)
        h, az, _ = place.altaz(lat, lon)
        if body == "moon" and sm.body_place("sun", utc).altaz(lat, lon)[0] > -6:
            continue
        if h >= 5.0:
            break
    else:
        return None
    heading = rng.uniform(0, 360)
    R = pose(up_true, heading)
    h_app = h + sm.refraction_deg(h)
    ray = R @ enu_vec(h_app, az)
    true_lenses = lens_off(lenses, sm.SIGMA_LENS_DEG, rng)
    # only frames where a lens sees it (both lenses together see everything but a band at the seam)
    sd = place.semidiameter_deg(lat, lon)
    if body == "sun":
        img = render_body(bg, true_lenses, ray, sd, bloom_deg=rng.uniform(0.3, 2.5), halo_deg=rng.uniform(1, 4),
                          halo_dn=rng.uniform(60, 200))
    else:
        s_enu = sm.enu_basis(lat, lon) @ sm._unit(place.sun_ecef_km - place.r_ecef_km)
        img = render_body(bg, true_lenses, ray, sd, bloom_deg=rng.uniform(0.0, 0.8), halo_deg=rng.uniform(0.5, 2),
                          halo_dn=rng.uniform(20, 120), lit=place.illuminated_fraction(), sun_dir_imu=R @ s_enu)
    if jpeg:
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    # what the solver is told: 'up' with an error, the nominal lens model
    up_meas = rot_about(rng.normal(size=3), math.radians(abs(rng.normal(0, sm.SIGMA_UP_DEG)) * math.sqrt(1.5))) \
        @ sm._unit(up_true)
    ang = rng.uniform(0, 2 * math.pi)
    dk = abs(rng.normal(0, prior_km))
    plat, plon = sm.offset_latlon(lat, lon, dk * math.cos(ang), dk * math.sin(ang))
    s, rep = sm.sight_from_frame(img, up_meas, utc, (plat, plon, prior_km), body=body, lenses=lenses)
    row = {"body": body, "utc": utc, "alt_true": round(h, 3), "az_true": round(az, 2), "heading": round(heading, 1),
           "prior_off_km": round(dk, 1), **{k: v for k, v in rep.items() if k not in ("utc", "body")}}
    if s is None:
        row["sight"] = False
        return row
    fix = sm.fuse([s], (plat, plon, prior_km))
    err_alt = s.alt_deg - h
    # error of the fix across the line (along the body's azimuth) and in total, vs the truth
    dn = (fix.lat - lat) * sm.KM_PER_DEG
    de = (fix.lon - lon) * sm.KM_PER_DEG * math.cos(math.radians(lat))
    u = np.array([math.cos(math.radians(az)), math.sin(math.radians(az))])
    across = float(np.array([dn, de]) @ u)
    sig_across = float(math.sqrt(u @ fix.cov_km2 @ u))
    row.update(fix_lat=round(fix.lat, 5), fix_lon=round(fix.lon, 5), sigma_major_km=round(fix.sigma_major_km, 1))
    row.update(sight=True, err_alt_deg=round(err_alt, 3), fix_err_km=round(math.hypot(dn, de), 1),
               across_err_km=round(across, 1), sigma_across_km=round(sig_across, 1),
               prior_across_km=round(float(np.array([(plat - lat) * sm.KM_PER_DEG, (plon - lon) * sm.KM_PER_DEG
                                                     * math.cos(math.radians(lat))]) @ u), 1),
               mahal=round(fix.mahalanobis(lat, lon), 2), accepted=fix.accepted)
    return row


def summarize(rows, label):
    s = [r for r in rows if r.get("sight")]
    if not s:
        print(f"{label}: {len(rows)} frames, 0 sights")
        return {}
    ea = np.array([r["err_alt_deg"] for r in s])
    ac = np.array([abs(r["across_err_km"]) for r in s])
    pa = np.array([abs(r["prior_across_km"]) for r in s])
    sg = np.array([r["sigma_across_km"] for r in s])
    mh = np.array([r["mahal"] for r in s])
    out = {"frames": len(rows), "sights": len(s), "alt_err_rms_deg": float(np.sqrt(np.mean(ea ** 2))),
           "across_med_km": float(np.median(ac)), "across_p90_km": float(np.percentile(ac, 90)),
           "prior_across_med_km": float(np.median(pa)), "sigma_across_med_km": float(np.median(sg)),
           "beyond_3sigma": int((mh > 3).sum()), "beyond_2sigma": int((mh > 2).sum())}
    print(f"{label}: " + ", ".join(f"{k} {v:.3g}" if isinstance(v, float) else f"{k} {v}" for k, v in out.items()))
    return out


def run_synth(a):
    import cv2
    rng = np.random.default_rng(a.seed)
    lenses = default_lenses()
    bg = cv2.imread(a.bg, cv2.IMREAD_GRAYSCALE) if a.bg else np.full((1920, 3840), 12, np.uint8)
    rows = []
    day0 = datetime(2026, 10, 30, tzinfo=timezone.utc).timestamp()
    for k in range(a.n):
        up = sm._unit(np.asarray(a.up, float) + rng.normal(0, 0.15, 3))
        r = synth_case(rng, a.body, bg, up, (a.lat, a.lon), day0 + 86400 * rng.integers(0, 30), lenses,
                       prior_km=a.prior_km)
        if r is None:
            continue
        rows.append(r)
        if r.get("sight"):
            append_csv(a.csv, [[f"sunmoon-synthetic-{a.body}-1sight-prior{a.prior_km:g}km",
                                f"synthetic-seed{a.seed}", k, r["utc"], r["fix_lat"], r["fix_lon"], r["sigma_major_km"],
                                a.lat, a.lon, r["fix_err_km"]]])
        if a.out:
            with open(a.out, "a") as fh:
                fh.write(json.dumps(r) + "\n")
    summarize(rows, f"synthetic {a.body} (bg {'real frame' if a.bg else 'dark'})")
    return rows


def session_truth(session):
    p = os.path.join(session, "phone.jsonl")
    if os.path.exists(p):
        with open(p) as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("lat") is not None and (r.get("acc") or 99) < 50:
                    return r["lat"], r["lon"]
    return None


CSV_HEADER = "tool,session,frame,utc,lat,lon,sigma_km,truth_lat,truth_lon,err_km\n"


def append_csv(path, rows):
    """Positions for the user to check (shared file: header only when new)."""
    if not path:
        return
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a") as fh:
        if new:
            fh.write(CSV_HEADER)
        for r in rows:
            fh.write(",".join(str(v) for v in r) + "\n")


def offset_prior(truth, prior_km, seed):
    """The prior's centre: the truth moved by a random (seeded) |N(0, prior_km)| in a random direction."""
    rng = np.random.default_rng(seed)
    ang, d = rng.uniform(0, 2 * math.pi), abs(rng.normal(0, prior_km))
    return sm.offset_latlon(truth[0], truth[1], d * math.cos(ang), d * math.sin(ang))


def fix_row(tool, sess, frame, utc, fix, truth):
    return [tool, os.path.basename(sess.rstrip("/")), frame, utc, round(fix.lat, 5), round(fix.lon, 5),
            round(fix.sigma_major_km, 1), truth[0], truth[1], round(sm.distance_km(fix.lat, fix.lon, *truth), 1)]


def across_z(fix, truth, sight):
    """The fix's error across the body's line of position (along its azimuth), in its own sigma."""
    az = math.radians(sm.body_place(sight.body, sight.utc).altaz(*truth)[1])
    u = np.array([math.cos(az), math.sin(az)])
    e = np.array([(fix.lat - truth[0]) * sm.KM_PER_DEG,
                  (fix.lon - truth[1]) * sm.KM_PER_DEG * math.cos(math.radians(truth[0]))])
    return float(e @ u / math.sqrt(u @ fix.cov_km2 @ u))


def run_real(a):
    import cv2
    total = {"frames": 0, "sights": 0, "candidates": 0, "beyond_3sigma": 0}
    for sess in a.sessions:
        truth = tuple(a.truth) if a.truth else session_truth(sess)
        if truth is None:
            print(f"{sess}: no true position (give --truth)")
            continue
        with open(os.path.join(sess, "frames.jsonl")) as fh:
            rows = [json.loads(line) for line in fh]
        rows = [r for r in rows if r.get("image") and r.get("up_imu")]
        if a.since_utc:
            rows = [r for r in rows if utc_str(r.get("t_exp") or r["t"]) >= a.since_utc]
        rows = rows[::a.every]
        n = cands = 0
        found, out_rows, rep = [], [], {}
        for r in rows:
            img = cv2.imread(os.path.join(sess, r["image"]), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            utc = r.get("utc_used") or utc_str(r.get("t_exp") or r["t"])
            idx = r.get("idx", n)
            plat, plon = offset_prior(truth, a.prior_km, idx)
            s, rep = sm.sight_from_frame(img, r["up_imu"], utc, (plat, plon, a.prior_km))
            n += 1
            cands += rep.get("candidates", 0)
            if s is None:
                continue
            fix = sm.fuse([s], (plat, plon, a.prior_km))
            mh = fix.mahalanobis(*truth)
            za = across_z(fix, truth, s)
            total["beyond_3sigma"] += int(mh > 3)
            total["across_beyond_3sigma"] = total.get("across_beyond_3sigma", 0) + int(abs(za) > 3)
            found.append(s)
            out_rows.append(fix_row(f"sunmoon-{s.body}-1sight-prior{a.prior_km:g}km", sess, r["image"], utc, fix,
                                    truth))
            print(f"  SIGHT {os.path.basename(sess)} {r['image']} {s.body} intercept {rep['intercept_deg']:+.2f} deg"
                  f" fix err {out_rows[-1][-1]} km sigma {out_rows[-1][6]} km mahal {mh:.2f} z across {za:+.2f}")
        if found:
            plat, plon = offset_prior(truth, a.prior_km, 12345)
            fix = sm.fuse(found, (plat, plon, a.prior_km))
            out_rows.append(fix_row(f"sunmoon-fused{len(found)}-prior{a.prior_km:g}km", sess, "all", found[-1].utc,
                                    fix, truth))
            print(f"  FUSED {len(found)} sights: err {out_rows[-1][-1]} km, sigma {fix.sigma_minor_km:.0f}x"
                  f"{fix.sigma_major_km:.0f} km, mahal {fix.mahalanobis(*truth):.2f}, "
                  f"{'accepted' if fix.accepted else fix.why}")
        append_csv(a.csv, out_rows)
        print(f"{sess}: {n} frames, truth {truth}, {len(found)} sights accepted, saturated candidates {cands}, "
              f"body {rep.get('body')} alt {rep.get('alt_pred')} at the last frame")
        total["frames"] += n
        total["sights"] += len(found)
        total["candidates"] += cands
    print("real total", total)
    return total


SKY = os.environ.get("NAVERA_TESTDATA_SKY", "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/sky")


def run_mascot(a):
    """Real Moon frames of ESO Paranal's MASCOT all-sky camera (8 s, star-calibrated lens and mount from other
    nights, navera_tools/bench/realsky_validate): the detector, the halo/phase centre and the ephemeris on a real
    Moon at every phase. 'up' is the camera's fixed mount (no IMU error here); azimuth with the mount's north."""
    root = os.path.dirname(os.path.dirname(HERE))
    if root not in sys.path:
        sys.path.insert(0, root)
    from navera_tools.bench import realsky_validate as rv
    cam = rv.CAMERAS["mascot"]
    truth = (cam["lat"], cam["lon"])
    cals = [json.load(open(os.path.join(SKY, "results", n))) for n in ("mascot_lens.json", "mascot_lens_2023-02.json")]
    full = None
    rows = [json.loads(line) for line in open(os.path.join(SKY, "results", "mascot.jsonl"))]
    rows = [r for r in rows if (r.get("moon_alt") or -90) > 5][::a.every]
    out, csv_rows = [], []
    for k, r in enumerate(rows):
        path = os.path.join(SKY, "eso_mascot", "raw", r["frame"])
        if not os.path.exists(path):
            continue
        best = None
        for c in cals:
            img, utc, exp = rv.load_frame(path, cam, c["mirror"])
            lens = rv.lens_from(c, img.shape)
            if full is None:
                from cn_pkg import allsky
                full = allsky.Catalogue(limit_mag=4.5, max_sep_deg=1.0, path=allsky.BUNDLED_CATALOGUE)
            alt, az = rv.star_altaz(full.vec, utc, cam)
            R, n = rv.per_frame_mount(img, lens, np.array(c["R_cam_enu"]), alt, az)
            if best is None or n > best[1]:
                best = (R, n, lens, img, utc)
        R, n, lens, img, utc = best
        img = img.copy()                       # MASCOT burns text into its frames (title, ESO logo, N/E arrows)
        img[:80, :90] = 0
        img[:90, -70:] = 0
        img[-60:, :80] = 0
        up = R @ np.array([0, 0, 1.0])
        north = R @ np.array([0, 1.0, 0]) if a.heading else None
        utc_s = utc.replace("T", " ")
        plat, plon = offset_prior(truth, a.prior_km, k)
        s, rep = sm.sight_from_frame(img, up, utc_s, (plat, plon, a.prior_km), body="moon", lenses=[lens],
                                     ref_width=img.shape[1], pressure_hpa=cam["pressure_hpa"], temp_c=10.0,
                                     north_imu=north, sigma_heading_deg=1.0)
        h_true = sm.body_place("moon", utc_s).altaz(*truth, cam["elev_m"] / 1000.0)[0]
        row = {"frame": r["frame"], "utc": utc_s, "moon_illum": r["moon_illum"], "alt_true": round(h_true, 3),
               "mount_stars": n, "sight": s is not None, **{k2: v for k2, v in rep.items() if k2 != "utc"}}
        if s is not None:
            fix = sm.fuse([s], (plat, plon, a.prior_km))
            row.update(err_alt_deg=round(s.alt_deg - h_true, 3), fix_err_km=round(sm.distance_km(fix.lat, fix.lon,
                       *truth), 1), mahal=round(fix.mahalanobis(*truth), 2), sigma_km=round(fix.sigma_major_km, 1))
            csv_rows.append(fix_row(f"sunmoon-moon-1sight-prior{a.prior_km:g}km{'-az' if a.heading else ''}",
                                    "eso_mascot", r["frame"], utc_s, fix, truth))
        out.append(row)
        print(json.dumps(row), flush=True)
    append_csv(a.csv, csv_rows)
    s_ = [r for r in out if r["sight"]]
    if s_:
        e = np.array([r["err_alt_deg"] for r in s_])
        mh = np.array([r["mahal"] for r in s_])
        print(f"MASCOT moon: {len(out)} frames, {len(s_)} sights, altitude error mean {e.mean():+.3f} rms "
              f"{np.sqrt(np.mean(e ** 2)):.3f} deg (|err| p90 {np.percentile(np.abs(e), 90):.3f}), fix err median "
              f"{np.median([r['fix_err_km'] for r in s_]):.1f} km, beyond 3 sigma {int((mh > 3).sum())}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("synth")
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--body", default="sun", choices=("sun", "moon"))
    p.add_argument("--bg")
    p.add_argument("--up", type=float, nargs=3, default=[0.0, 1.0, 0.0], help="'up' in the IMU frame")
    p.add_argument("--lat", type=float, default=35.83)
    p.add_argument("--lon", type=float, default=10.64)
    p.add_argument("--prior-km", type=float, default=30.0)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out")
    p.add_argument("--csv", help="append every position to this CSV (positions for the user)")
    p = sub.add_parser("real")
    p.add_argument("sessions", nargs="+")
    p.add_argument("--truth", type=float, nargs=2)
    p.add_argument("--every", type=int, default=1)
    p.add_argument("--prior-km", type=float, default=30.0)
    p.add_argument("--since-utc", help="only frames from this UTC time on (YYYY-mm-dd HH:MM)")
    p.add_argument("--csv", help="append every position to this CSV (positions for the user)")
    p = sub.add_parser("mascot")
    p.add_argument("--every", type=int, default=1)
    p.add_argument("--prior-km", type=float, default=150.0)
    p.add_argument("--heading", action="store_true", help="also use the azimuth (the mount's north as a compass)")
    p.add_argument("--csv")
    a = ap.parse_args(argv)
    if a.cmd == "synth":
        run_synth(a)
    elif a.cmd == "mascot":
        run_mascot(a)
    else:
        run_real(a)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    main()
