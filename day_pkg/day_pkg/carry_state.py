"""The day node's carried position outside the matching thread: the watchdog and a restart.

Two problems of the day node (problems list B23, F32, endurance endur2) share one cure:

- a match can stall (5.7 s in the 2-hour endurance flight endur2, 7-10 s at 1200 m): the carried
  position was published only by the thread doing the match, so the autopilot heard nothing
  meanwhile. A *snapshot* of the last output and the velocity it moved with (DrSnap) is kept by
  the matching thread (and by the GPS thread while the GPS is trusted); a watchdog in its own
  thread carries it to the present and publishes it when the outputs stop — read-only, it never
  touches the matching thread's state;
- a day node restarted alone in flight (crash, respawn) started from its last position only, with
  a 600 m search circle and no dead reckoning: the track (measured points, the carried velocity,
  the headings) is persisted at most once a second (navera_common.state_store "day_track") and
  restored with its original times, so the restarted node carries it on at once with the
  uncertainty grown by the time elapsed — never as a fresh fix.

Pure Python (no ROS).
"""
import math
from collections import namedtuple
from typing import Optional, Tuple

from day_pkg.vision_nav import _move

# lat, lon: the position output at t (s, the frames' time base); sigma: its stated 1-sigma (m);
# ve, vn, sig_v: the velocity it moves with (m/s) and its 1-sigma; since_v: seconds between the
# instant that velocity was measured and t (the unseen-acceleration term grows from there);
# t_meas: the last MEASURED fix (the dead-reckoning limit counts from it); heading: the heading the
# velocity is turned to (deg, None: unknown)
DrSnap = namedtuple("DrSnap", "lat lon t sigma ve vn sig_v since_v t_meas heading")


def carry_snap(snap: DrSnap, t: float, track, turn_deg: float = 0.0,
               heading_sigma_deg: float = 0.0) -> Tuple[float, float, float]:
    """(lat, lon, sigma_m) of the snapshot carried to t: its velocity turned by turn_deg (taken at a
    constant rate, in <= 5 deg steps), the sigma grown like the node's own carry
    (TrackVelocity.sigma_growth of `track`, plus half the reach of a heading error of
    heading_sigma_deg)."""
    dt = max(0.0, t - snap.t)
    a = math.radians(turn_deg or 0.0)
    steps = max(1, int(abs(a) / math.radians(5.0)))
    de = dn = 0.0
    for i in range(steps):
        ai = a * (i + 0.5) / steps
        de += (snap.ve * math.cos(ai) + snap.vn * math.sin(ai)) * dt / steps
        dn += (-snap.ve * math.sin(ai) + snap.vn * math.cos(ai)) * dt / steps
    speed = math.hypot(snap.ve, snap.vn)
    p = _move((snap.lat, snap.lon), de, dn)
    sigma = snap.sigma + track.sigma_growth(snap.sig_v, speed, dt, max(0.0, snap.since_v), turn_deg) \
        + 0.5 * math.radians(heading_sigma_deg) * speed * dt
    return p[0], p[1], sigma


def watchdog_carry(snap: Optional[DrSnap], t: float, track, max_dr_s: float, max_sigma_m: float,
                   turn_deg: float = 0.0, heading_sigma_deg: float = 0.0):
    """(lat, lon, sigma_m) the watchdog may publish at t, or (None, why): no snapshot, the
    dead-reckoning limit (max_dr_s since the last measured fix) or the uncertainty limit reached."""
    if snap is None:
        return None, "nothing carried yet"
    if t - snap.t_meas > max_dr_s:
        return None, f"dead-reckoning limit {max_dr_s:.0f}s reached"
    lat, lon, sigma = carry_snap(snap, t, track, turn_deg, heading_sigma_deg)
    if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(sigma)):
        return None, "non-finite carry"
    if sigma > max_sigma_m:
        return None, f"dead-reckoning uncertainty {sigma:.0f} m > {max_sigma_m:.0f} m"
    return (lat, lon, sigma), None


# ── persistence (state_store "day_track") ─────────────────────────────────────
TRACK_STATE = "day_track"
PERSIST_WINDOW_S = 25.0          # track points kept: the velocity fit's 20 s window and a margin


def _finite(*xs) -> bool:
    try:
        return all(math.isfinite(float(x)) for x in xs)
    except (TypeError, ValueError):
        return False


def track_state(points, carry, vel_epoch, track_heading, headings, anchor, last_measured,
                snap: Optional[DrSnap]) -> dict:
    """The JSON-able record of the track. points: the TrackVelocity points (t, lat, lon, sigma);
    carry: the node's _carry tuple or None; headings: (t, heading) of the frames; anchor:
    (lat, lon, t, sigma) of the last output."""
    pts = list(points)
    if pts:
        t_end = pts[-1][0]
        pts = [list(p) for p in pts if t_end - p[0] <= PERSIST_WINDOW_S]
    hs = [list(h) for h in headings if pts and pts[-1][0] - h[0] <= PERSIST_WINDOW_S]
    return {"pts": pts, "carry": list(carry) if carry is not None else None, "vel_epoch": vel_epoch,
            "track_heading": track_heading, "headings": hs,
            "anchor": list(anchor) if anchor is not None else None, "last_measured": last_measured,
            "snap": list(snap) if snap is not None else None}


def restore_track(data: Optional[dict], now: float, max_dr_s: float) -> Optional[dict]:
    """The persisted track if it can be carried on at `now` (its last measured point at most max_dr_s
    old, not in the future, every number finite), as {pts, carry, vel_epoch, track_heading, headings,
    anchor, last_measured, snap (DrSnap or None)}; else None. The times are kept as they were: the
    position is carried from its measurement, its uncertainty grows with the time elapsed."""
    if not data or not data.get("pts"):
        return None
    try:
        pts = [tuple(float(x) for x in p) for p in data["pts"]]
        if any(len(p) != 4 or not _finite(*p) for p in pts):
            return None
        t_last = pts[-1][0]
        if not (now - max_dr_s <= t_last <= now + 1.0):
            return None
        carry = data.get("carry")
        if carry is not None:
            carry = tuple(None if x is None else float(x) for x in carry)
            if len(carry) != 7 or not _finite(carry[0], carry[1], carry[2], carry[4], carry[5], carry[6]) \
                    or carry[2] > now + 1.0:
                carry = None
        snap = data.get("snap")
        if snap is not None:
            snap = DrSnap(*[None if x is None else float(x) for x in snap])
            if not _finite(snap.lat, snap.lon, snap.t, snap.sigma, snap.ve, snap.vn, snap.sig_v,
                           snap.since_v, snap.t_meas) or snap.t > now + 1.0:
                snap = None
        anchor = data.get("anchor")
        if anchor is not None:
            anchor = tuple(float(x) for x in anchor)
            if len(anchor) != 4 or not _finite(*anchor):
                anchor = None
        hs = [(float(t), float(h)) for t, h in (data.get("headings") or []) if _finite(t, h)]
        ve = data.get("vel_epoch")
        th = data.get("track_heading")
        lm = data.get("last_measured")
        return {"pts": pts, "carry": carry, "vel_epoch": float(ve) if _finite(ve) else None,
                "track_heading": float(th) if _finite(th) else None, "headings": hs, "anchor": anchor,
                "last_measured": float(lm) if _finite(lm) else t_last, "snap": snap}
    except (TypeError, ValueError):
        return None
