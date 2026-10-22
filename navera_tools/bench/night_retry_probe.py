#!/usr/bin/env python3
"""Every hypothesis NightLocalizer.localize would try on a frame, with its evidence.

localize stops at the first verified hypothesis; to study what separates right retried fixes
from wrong ones this runs the first attempt and then (if it failed the way that triggers the
retries) ALL the retries of night_localizer.retry_plan, recording for each: map-check NCC,
the shifted-map control (verify_match shifts_px), both search centres' answers and their
distance, the STHN consistency. `decide` replays localize's choice (optionally through a
gate) from those records, so gates can be compared offline on the same inferences.

Used by night_real_thermal.py / night_conditions.py with --probe-jsonl; summarised by
night_retry_gate_eval.py.
"""
import math
import os

# shifted-map control distances (satellite pixels, ~0.8-1 m each at z17)
PROBE_SHIFTS_PX = (24.0, 64.0)
# NAVERA_PROBE_RETRY_BELOW_CONF: default of probe's retry_below_conf (unset: retries only as localize)
_ENV_RETRY_BELOW = os.environ.get("NAVERA_PROBE_RETRY_BELOW_CONF")


def _m(a_lat, a_lon, b_lat, b_lon):
    if None in (a_lat, a_lon, b_lat, b_lon):
        return None
    dn = (a_lat - b_lat) * 111_320.0
    de = (a_lon - b_lon) * 111_320.0 * math.cos(math.radians(b_lat))
    return math.hypot(dn, de)


def quad_rotation_deg(quad):
    """Rotation (deg, + clockwise seen from above) of STHN's footprint quad (4 lat/lon corners,
    top-left first, clockwise) from north-up, and its scale spread (longest / shortest side):
    a frame turned or scaled wrongly that STHN half-absorbed shows here. None without a quad.
    """
    if not quad or len(quad) != 4:
        return None, None
    lat0 = sum(c[0] for c in quad) / 4.0
    xy = [((c[1]) * 111_320.0 * math.cos(math.radians(lat0)), -(c[0]) * 111_320.0) for c in quad]
    angs = []
    for i, j in ((0, 1), (3, 2)):                    # the top and bottom edges, west -> east
        angs.append(math.atan2(xy[j][1] - xy[i][1], xy[j][0] - xy[i][0]))
    for i, j in ((0, 3), (1, 2)):                    # the left and right edges, north -> south
        angs.append(math.atan2(xy[j][1] - xy[i][1], xy[j][0] - xy[i][0]) - math.pi / 2.0)
    s = sum(math.sin(x) for x in angs)
    c = sum(math.cos(x) for x in angs)
    sides = [math.hypot(xy[(i + 1) % 4][0] - xy[i][0], xy[(i + 1) % 4][1] - xy[i][1]) for i in range(4)]
    return math.degrees(math.atan2(s, c)), max(sides) / max(min(sides), 1e-9)


def record(a, d, f):
    """The JSON-able evidence of one attempt (result dict a of NightLocalizer._attempt)."""
    v = a.get("verify") or {}
    rc = a.get("recheck") or {}
    rv = rc.get("verify") or {}
    rot, aspect = quad_rotation_deg(a.get("footprint_quad"))
    return dict(rot_deg=rot, side_ratio=aspect, d=d, f=f, success=bool(a.get("success")), reason=str(a.get("reason") or "")[:90],
                conf=a.get("conf"), ncc=v.get("ncc"), ncc_ctrl=v.get("ncc_ctrl"), ncc_margin=v.get("ncc_margin"),
                recheck_m=a.get("recheck_m"), ncc2=rv.get("ncc"), ncc2_ctrl=rv.get("ncc_ctrl"),
                c1=[a.get("first_lat", a.get("pred_lat")), a.get("first_lon", a.get("pred_lon"))],
                c2=[rc.get("lat"), rc.get("lon")],
                lat=a.get("lat") if a.get("success") else None, lon=a.get("lon") if a.get("success") else None,
                sigma_m=a.get("sigma_m"), dt_ms=a.get("dt_ms"))


def probe(loc, img, prior_lat, prior_lon, altitude_m, hfov_deg, heading_deg, heading_retry_deg, height_retry,
          require_scale=True, retry_below_conf=None):
    """First attempt, then every retry localize would consider (not stopping at a success).

    retry_below_conf: also run the retries after a SUCCESSFUL first attempt whose consistency is
    below this (to study a first-try gate offline: what the retries would then have found).
    """
    from night_pkg.nodes.night_localizer import retry_plan
    first = loc._attempt(img, prior_lat, prior_lon, altitude_m, hfov_deg, heading_deg, require_scale)
    out = [record(first, 0.0, 0.0)]
    if retry_below_conf is None and _ENV_RETRY_BELOW:
        retry_below_conf = float(_ENV_RETRY_BELOW)
    plan_on = first
    if (retry_below_conf is not None and first.get("success")
            and float(first.get("conf") or 0.0) < retry_below_conf):
        plan_on = dict(first, success=False, map_check_failed=True)
    for d, f in retry_plan(plan_on, heading_deg, altitude_m, heading_retry_deg, height_retry):
        a = loc._attempt(img, prior_lat, prior_lon, altitude_m * (1.0 + f),
                         hfov_deg, None if heading_deg is None else (heading_deg + d) % 360.0, require_scale)
        out.append(record(a, d, f))
    return out


def decide(attempts, gate=None, first_min_conf=None):
    """Index of the attempt localize keeps (first success, retries through `gate`), or None.

    gate(att, k, attempts) -> bool, for a retried success att = attempts[k] (k >= 1).
    first_min_conf: the localizer's first-try gate (a weaker first success is refused; its
    retries are in the record only when it was probed with retry_below_conf above that).
    """
    for k, a in enumerate(attempts):
        if not a["success"]:
            continue
        if k == 0 and first_min_conf is not None and float(a.get("conf") or 0.0) < first_min_conf:
            continue
        if k == 0 or gate is None or gate(a, k, attempts):
            return k
    return None


def error_m(a, lat, lon):
    return _m(a["lat"], a["lon"], lat, lon)
