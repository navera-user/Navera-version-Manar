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

from day_pkg.carry_aids import autopilot_sigma_growth, carry_autopilot, carry_with_turns
from day_pkg.vision_nav import _move

# lat, lon: the position output at t (s, the frames' time base); sigma: its stated 1-sigma (m);
# ve, vn, sig_v: the velocity it moves with (m/s) and its 1-sigma; since_v: seconds between the
# instant that velocity was measured and t (the unseen-acceleration term grows from there);
# t_meas: the last MEASURED fix (the dead-reckoning limit counts from it); heading: the heading the
# velocity is turned to (deg, None: unknown); yaw: the IMU attitude's yaw at t (deg, None: unknown — the
# turn across a restart, carry_aids.AttitudeYaw); be, bn: the bias fitted to the autopilot's velocity
# (m/s, None: not carried along the autopilot's velocity; sig_v is then that bias's 1-sigma)
DrSnap = namedtuple("DrSnap", "lat lon t sigma ve vn sig_v since_v t_meas heading yaw be bn",
                    defaults=(None, None, None))


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


def carry_snap_aided(snap: DrSnap, t: float, track, apv=None, yaw=None, gyro=None, drift_mps2: float = 0.1,
                     gyro_bias_dps: float = 0.1):
    """The snapshot carried to t with what is known of the motion since (carry_aids): along the
    autopilot's velocity + the snapshot's bias (apv; a first gap after a restart bridged), else turned
    by the IMU attitude's yaw since the snapshot's (yaw, seeded with snap.yaw: across a restart), else
    by the gyro's integrated turn (gyro, within this process), else straight (carry_snap).
    Returns (DrSnap carried to t, how): its position, sigma, velocity, the same measurement times."""
    dt = max(0.0, t - snap.t)
    if apv is not None and snap.be is not None:
        r = carry_autopilot(snap.lat, snap.lon, snap.t, t, apv, (snap.be, snap.bn), snap.ve, snap.vn)
        if r is not None:
            lat, lon, ve, vn, gap, dvg = r
            sigma = snap.sigma + autopilot_sigma_growth(snap.sig_v, dt, snap.since_v, drift_mps2, gap, dvg,
                                                        track.accel)
            return snap._replace(lat=lat, lon=lon, t=t, sigma=sigma, ve=ve, vn=vn, since_v=snap.since_v + dt,
                                 yaw=yaw.yaw(t) if yaw is not None else None), "autopilot velocity"
    speed = math.hypot(snap.ve, snap.vn)
    if yaw is not None and snap.yaw is not None:
        yaw.seed(snap.t, snap.yaw)
        tr = yaw.turn(snap.t, t)
        if tr is not None:
            def turn_at(s):
                x = yaw.turn(snap.t, s)
                return x[0] if x is not None else None
            lat, lon, ve, vn = carry_with_turns(snap.lat, snap.lon, snap.t, snap.ve, snap.vn, t, turn_at)
            # measured turns: the track's growth without its half-turn term, but for the turn inside a
            # gap (when it turned is not known) and the yaw's drift (gyro bias x time)
            sigma = (snap.sigma + track.sigma_growth(snap.sig_v, speed, dt, max(0.0, snap.since_v))
                     + 0.5 * math.radians(tr[2]) * speed * tr[1]
                     + 0.5 * math.radians(gyro_bias_dps * dt) * speed * dt)
            return snap._replace(lat=lat, lon=lon, t=t, sigma=sigma, ve=ve, vn=vn, since_v=snap.since_v + dt,
                                 yaw=yaw.yaw(t), heading=None if snap.heading is None else
                                 (snap.heading + tr[0]) % 360.0), "attitude yaw"
    turn, h_sig, how = 0.0, 0.0, "straight"
    if gyro is not None:
        d = gyro.turn(snap.t, t)
        if d is not None:
            turn, h_sig, how = d, gyro.bias * dt, "gyro turn"
    lat, lon, sigma = carry_snap(snap, t, track, turn, h_sig)
    a = math.radians(turn)
    ve, vn = snap.ve * math.cos(a) + snap.vn * math.sin(a), -snap.ve * math.sin(a) + snap.vn * math.cos(a)
    return snap._replace(lat=lat, lon=lon, t=t, sigma=sigma, ve=ve, vn=vn, since_v=snap.since_v + dt), how


def watchdog_carry(snap: Optional[DrSnap], t: float, track, max_dr_s: float, max_sigma_m: float,
                   turn_deg: float = 0.0, heading_sigma_deg: float = 0.0, aids: Optional[dict] = None):
    """(lat, lon, sigma_m) the watchdog may publish at t, or (None, why): no snapshot, the
    dead-reckoning limit (max_dr_s since the last measured fix) or the uncertainty limit reached.
    aids: carry_snap_aided's keyword arguments (apv, yaw, gyro, ...) — then turn_deg is not used."""
    if snap is None:
        return None, "nothing carried yet"
    if t - snap.t_meas > max_dr_s:
        return None, f"dead-reckoning limit {max_dr_s:.0f}s reached"
    if aids is not None:
        c, _ = carry_snap_aided(snap, t, track, **aids)
        lat, lon, sigma = c.lat, c.lon, c.sigma
    else:
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
            vals = [None if x is None else float(x) for x in snap]
            snap = DrSnap(*vals) if 10 <= len(vals) <= 13 else None
        if snap is not None:
            if not _finite(snap.lat, snap.lon, snap.t, snap.sigma, snap.ve, snap.vn, snap.sig_v,
                           snap.since_v, snap.t_meas) or snap.t > now + 1.0:
                snap = None
        if snap is not None:
            if snap.be is None or snap.bn is None or not _finite(snap.be, snap.bn):
                snap = snap._replace(be=None, bn=None)
            if snap.yaw is not None and not _finite(snap.yaw):
                snap = snap._replace(yaw=None)
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
