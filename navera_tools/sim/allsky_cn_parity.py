#!/usr/bin/env python3
"""Parity of the flight node's 360 mode (cn_pkg AllSkyLocator, as cn_subscriber calls it) with the field path
(allsky.locate as the field server calls it) on the simulated stress set. SIMULATION ONLY.

    PYTHONPATH=.:cn_pkg:navera_common python3 -m navera_tools.sim.allsky_cn_parity [--seeds 4] [--set stress]
        [--workers 3] [--only name,name] [--json out.json]

Every frame of celestial360_conditions is solved three ways:
  field    allsky.locate(frame, up, ...) with the field's catalogue (~/.navera_sim/bsc5.dat) and the server's sigma;
  camera   AllSkyLocator.process with 'up' in frame_meta (up_imu), the bundled catalogue, the image as the node
           receives it (mono8);
  vehicle  AllSkyLocator.process with 'up' from a vehicle orientation (quaternion, random heading) through a
           random camera-to-body mount rotation R_cam_body (the camera mounted at any angle on the vehicle).
The three must agree: same accept / refuse, same position, same stated sigma.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.sim import celestial360_conditions as cc  # noqa: E402

_STATE = {}


def _random_rotation(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    from scipy.spatial.transform import Rotation
    return Rotation.from_quat(q).as_matrix()


def vehicle_attitude(up_cam, R_cam_body, heading_deg):
    """A vehicle orientation (sensor_msgs/Imu quaternion x, y, z, w; body → ENU) under which the camera, mounted
    with R_cam_body, sees 'up' along up_cam."""
    from scipy.spatial.transform import Rotation
    up_body = R_cam_body.T @ (up_cam / np.linalg.norm(up_cam))
    ez = np.array([0.0, 0.0, 1.0])
    axis = np.cross(up_body, ez)
    s, c = np.linalg.norm(axis), float(up_body @ ez)
    level = Rotation.from_rotvec(axis / s * math.atan2(s, c)) if s > 1e-12 else \
        Rotation.from_rotvec([math.pi, 0, 0] if c < 0 else [0, 0, 0])
    R_enu_body = Rotation.from_rotvec([0, 0, math.radians(heading_deg)]) * level
    return R_enu_body.as_quat()                                   # x, y, z, w


def run_one(args):
    try:
        return _run_one(args)
    except Exception as ex:
        cond, seed = args
        return {"cond": cond.name, "seed": seed, "junk": cond.junk, "harness_error": repr(ex)}


def _run_one(args):
    from datetime import datetime, timedelta
    import cv2
    from cn_pkg import allsky
    from cn_pkg.allsky_locator import AllSkyLocator
    cond, seed = args
    if "field_cat" not in _STATE:
        _STATE["field_cat"] = allsky.Catalogue(limit_mag=4.0)
        _STATE["node_cat"] = allsky.Catalogue(limit_mag=4.0, path=allsky.BUNDLED_CATALOGUE)
    sc = cc.Scene(cond, seed)
    frame = cc.render(sc)
    up, gate = cc.solver_up(sc)
    row = {"cond": cond.name, "seed": seed, "junk": cond.junk}
    if up is None:
        row["gated"] = gate
        return row
    utc = sc.utc
    if cond.clock_err_s:
        utc = (datetime.strptime(utc, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=cond.clock_err_s)).strftime(
            "%Y-%m-%d %H:%M:%S")
    fs = cc.F_SCALE_SEARCH if cond.search_focal else (cond.f_true,)
    # field path (server._solve360: locate, then the stated sigma of a stopped fix)
    t0 = time.time()
    r = allsky.locate(frame, up, utc, _STATE["field_cat"], f_scales=fs)
    row["t_field"] = time.time() - t0
    row["field"] = {"solved": bool(r.get("solved")), "why": r.get("why")}
    if r.get("solved"):
        sig = math.hypot(cc.ATTITUDE_SIGMA_360_DEG, r.get("sigma_fit_deg") or 0.0) * 111.2
        row["field"].update(lat=r["lat"], lon=r["lon"], sigma_km=sig, matched=r["matched"])
    # the node receives the frame as an image message: mono8 (a BGR frame is converted the same way)
    img = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rng = np.random.default_rng(5000 + seed)
    R_cam_body = _random_rotation(rng)
    q = vehicle_attitude(up, R_cam_body, rng.uniform(0, 360))
    for name, kw in (("camera", {"meta": {"up_imu": [float(v) for v in up]}}),
                     ("vehicle", {"meta": {}, "q_xyzw": q})):
        loc = AllSkyLocator(catalogue=_STATE["node_cat"], f_scale_search=fs, R_cam_body=R_cam_body,
                            up_source=name)
        t0 = time.time()
        o = loc.process(img, utc, **kw)
        row["t_" + name] = time.time() - t0
        row[name] = {"solved": bool(o.get("success")), "why": o.get("error"), "up_dev_deg": math.degrees(math.acos(
            max(-1.0, min(1.0, float(np.dot(o.get("up_cam") or up, up) / np.linalg.norm(o.get("up_cam") or up))))))}
        if o.get("success"):
            row[name].update(lat=o["predicted_lat"], lon=o["predicted_lon"], sigma_km=o["sigma_m"] / 1000.0,
                             matched=o.get("matched"))
    for p in ("field", "camera", "vehicle"):
        if row[p].get("solved"):
            from navera_tools.field.reprocess360 import haversine_km
            row[p]["err_km"] = haversine_km(row[p]["lat"], row[p]["lon"], cond.lat, cond.lon)
    return row


def compare(rows, tol_km=0.01, tol_sigma_km=0.2):
    """Per path: solved, wrong (>50 km or any junk fix); and the frames where a node path differs from the field."""
    out = {}
    for p in ("field", "camera", "vehicle"):
        ok = [r for r in rows if p in r and r[p]["solved"]]
        out[p] = {"solved": len(ok), "wrong": sum(1 for r in ok if r["junk"] or r[p]["err_km"] > cc.WRONG_KM)}
    diffs = []
    for r in rows:
        if "field" not in r:
            continue
        f = r["field"]
        for p in ("camera", "vehicle"):
            n = r[p]
            if n["solved"] != f["solved"]:
                diffs.append((r["cond"], r["seed"], p, "accept differs", f.get("why"), n.get("why")))
            elif n["solved"]:
                from navera_tools.field.reprocess360 import haversine_km
                d = haversine_km(f["lat"], f["lon"], n["lat"], n["lon"])
                if d > tol_km or abs(f["sigma_km"] - n["sigma_km"]) > tol_sigma_km:
                    diffs.append((r["cond"], r["seed"], p, f"fix differs {d:.4f} km", f["sigma_km"], n["sigma_km"]))
    out["frames"] = len(rows)
    out["gated_before_solver"] = sum(1 for r in rows if "gated" in r)
    out["harness_errors"] = [r for r in rows if "harness_error" in r]
    out["diffs"] = diffs
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--set", choices=("stress", "car"), default="stress")
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    conds = cc.car_matrix() if a.set == "car" else cc.conditions()
    if a.only:
        keys = [k.strip() for k in a.only.split(",") if k.strip()]
        conds = [c for c in conds if any(k in c.name for k in keys)]
    jobs = [(c, s) for c in conds for s in range(a.seeds)]
    t0 = time.time()
    rows = []
    if a.workers > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(a.workers, maxtasksperchild=8) as pool:
            rows = list(pool.imap_unordered(run_one, jobs, chunksize=1))
    else:
        rows = [run_one(j) for j in jobs]
    res = compare(rows)
    print("SIMULATION ONLY - synthetic frames")
    for p in ("field", "camera", "vehicle"):
        print(f"{p:8s}: {res[p]['solved']} solved of {res['frames']} frames, {res[p]['wrong']} wrong "
              f"(>{cc.WRONG_KM:.0f} km or junk accepted)")
    print(f"gated before the solver (both paths alike): {res['gated_before_solver']}; "
          f"harness errors: {len(res['harness_errors'])}")
    print(f"node vs field differences: {len(res['diffs'])}")
    for d in res["diffs"]:
        print("  ", d)
    print(f"wall {time.time() - t0:.0f} s")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"rows": rows, "compare": res}, f, indent=1, default=float)
    return 0 if not res["diffs"] and not res["harness_errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
