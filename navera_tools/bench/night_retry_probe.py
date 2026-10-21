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

# shifted-map control distances (satellite pixels, ~0.8-1 m each at z17)
PROBE_SHIFTS_PX = (24.0, 64.0)


def _m(a_lat, a_lon, b_lat, b_lon):
    if None in (a_lat, a_lon, b_lat, b_lon):
        return None
    dn = (a_lat - b_lat) * 111_320.0
    de = (a_lon - b_lon) * 111_320.0 * math.cos(math.radians(b_lat))
    return math.hypot(dn, de)


def record(a, d, f):
    """The JSON-able evidence of one attempt (result dict a of NightLocalizer._attempt)."""
    v = a.get("verify") or {}
    rc = a.get("recheck") or {}
    rv = rc.get("verify") or {}
    return dict(d=d, f=f, success=bool(a.get("success")), reason=str(a.get("reason") or "")[:90],
                conf=a.get("conf"), ncc=v.get("ncc"), ncc_ctrl=v.get("ncc_ctrl"), ncc_margin=v.get("ncc_margin"),
                recheck_m=a.get("recheck_m"), ncc2=rv.get("ncc"), ncc2_ctrl=rv.get("ncc_ctrl"),
                c1=[a.get("first_lat", a.get("pred_lat")), a.get("first_lon", a.get("pred_lon"))],
                c2=[rc.get("lat"), rc.get("lon")],
                lat=a.get("lat") if a.get("success") else None, lon=a.get("lon") if a.get("success") else None,
                sigma_m=a.get("sigma_m"), dt_ms=a.get("dt_ms"))


def probe(loc, img, prior_lat, prior_lon, altitude_m, hfov_deg, heading_deg, heading_retry_deg, height_retry,
          require_scale=True):
    """First attempt, then every retry localize would consider (not stopping at a success)."""
    from night_pkg.nodes.night_localizer import retry_plan
    first = loc._attempt(img, prior_lat, prior_lon, altitude_m, hfov_deg, heading_deg, require_scale)
    out = [record(first, 0.0, 0.0)]
    for d, f in retry_plan(first, heading_deg, altitude_m, heading_retry_deg, height_retry):
        a = loc._attempt(img, prior_lat, prior_lon, altitude_m * (1.0 + f),
                         hfov_deg, None if heading_deg is None else (heading_deg + d) % 360.0, require_scale)
        out.append(record(a, d, f))
    return out


def decide(attempts, gate=None):
    """Index of the attempt localize keeps (first success, retries through `gate`), or None.

    gate(att, k, attempts) -> bool, for a retried success att = attempts[k] (k >= 1).
    """
    for k, a in enumerate(attempts):
        if not a["success"]:
            continue
        if k == 0 or gate is None or gate(a, k, attempts):
            return k
    return None


def error_m(a, lat, lon):
    return _m(a["lat"], a["lon"], lat, lon)
