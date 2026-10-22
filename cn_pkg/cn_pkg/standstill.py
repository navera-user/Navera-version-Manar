"""Is the vehicle at rest at a frame's exposure? Camera IMU only (accelerometer in g, gyro in rad/s), no ROS.

Why it matters (D8, D12): the celestial 'up' is the accelerometer's mean, so any vehicle acceleration tilts it
(0.1 g = 5.7 deg = ~640 km) and no star check sees it. Only fixes taken at rest are trusted. The camera driver's
test (insta360_usb.stopped: 0.2 s accelerometer means steady within 0.003 g and rotation < 0.5 deg/s over 2.5 s)
is fooled on a very smooth road: a car cruising or speeding up gently (0.02-0.05 g) shakes so little that it looks
parked (glass-road simulation: 333 of 901 moving frames called stopped, 106 with 'up' 0.3-7.4 deg off).

What the accelerometer alone cannot see is a STEADY acceleration: it only tilts the measured 'up'. What it can see
is the CHANGE of 'up' when such an acceleration starts or ends, once the turn of the camera itself is taken out of
it with the gyro (gyro-propagated vertical). So, on top of the exposure window (the driver's test: 0.2 s means
steady, rotation < 0.5 deg/s, 2 s before to 0.5 s after the exposure):

1. magnitude: the mean |a| over the exposure window within MAG_TOL_G of g_ref, |a| at rest (the 6-position
   calibration makes it ~1.000): a steady acceleration h gives |a| = sqrt(1 + h^2), so >~0.09 g is refused here;
2. gyro-propagated vertical: every 0.5 s accelerometer mean of the last LONG_S seconds is turned into the camera's
   frame at the exposure with the integrated gyro (the car's own pitching, rolling and people getting in are taken
   out). Blocks whose 'up' differs from the exposure window's by more than DIR_TOL_DEG are a change of the
   vehicle's acceleration: 0.02 g = 1.1 deg.
3. which side of the change was gravity? Only one of the two states can be rest, and rest has the SMALLEST |a|:
   if the exposure is at rest, the changed blocks were accelerating and their |a| exceeds the exposure's by
   E = 1/cos(theta) - 1 (theta their angle to the exposure's 'up'); if the exposure is the accelerating one,
   the changed blocks are lower by about as much. The change is accepted as "braked, then stopped" when the
   mean excess of the last changed blocks (the newest 2 s of the last change) over the exposure window is at
   least EXPLAIN_FRACTION x E and E stands EXPLAIN_SIGMAS above the noise of block magnitudes (vertical bounce);
   otherwise the frame is not called stopped. A gentle acceleration (0.02-0.05 g: E = 0.0002-0.0013) is too
   small to be told from rest this way on a normal road, so it is refused for LONG_S after it starts; a stop after
   real braking (0.1 g: E = 0.005) is accepted at once. A change larger than ~5.4 deg (E > MAG_TOL_G + 0.0005) needs no
   comparison: had the exposure held that acceleration, check 1 would have refused it (rough roads, where the
   bounce hides E in the block magnitudes).

Limits, stated: a steady gentle acceleration that has lasted the whole LONG_S window, or a very gentle roll to a
stop, are not separable from rest by an IMU; the latter is refused (safe), the former is not. Cruising at a
constant speed on a perfectly smooth, straight road looks like rest too, but then 'up' IS gravity.
"""
import math
from typing import Optional

import numpy as np

SHORT_BEFORE_S = 2.0        # the exposure window: as the driver's stopped() (STILL_WINDOW_S) ...
AFTER_S = 0.5               # ... and 0.5 s after the exposure
LONG_S = 10.0               # how far back a change of 'up' is looked for (the gentle phases simulated last 3-9 s)
BLOCK_S = 0.5               # accelerometer means: 26.7 Hz idle vibration averages out (13 cycles)
MAG_TOL_G = 0.004           # |mean |a| - g_ref| over the exposure window
DIR_TOL_DEG = 0.3           # a block whose propagated 'up' is further than this from the exposure's has changed
EXPLAIN_FRACTION = 0.3      # changed blocks' |a| excess over the exposure's must reach this part of E ...
EXPLAIN_SIGMAS = 3.0        # ... and E must stand this many sigmas above the block magnitude noise
EXPLAIN_BLOCKS = 4          # judged on the newest 2 s of the last change before the exposure
EXPLAIN_MAG_MARGIN_G = 0.0005  # a change whose E exceeds MAG_TOL_G + this (> ~5.4 deg) is explained by the |a| check
RUN_EXTRA_S = 5.0           # a change that ends within LONG_S is followed back this much further (its start)
MAG_NOISE_FLOOR_G = 0.0002  # the block magnitude noise is never taken below this
RATE_DPS = 0.5              # the exposure window's rotation (as the driver)
ACC_STD_G = 0.003           # the exposure window's 0.2 s accelerometer means steady within (as the driver)
COVERAGE = 0.9              # fraction of a window the IMU samples must cover


def _rotvec(w) -> np.ndarray:
    t = float(np.linalg.norm(w))
    if t < 1e-15:
        return np.eye(3)
    k = np.asarray(w, float) / t
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def propagate(t_s: np.ndarray, gyro: np.ndarray, chunk: int = 10) -> np.ndarray:
    """R_k (N,3,3) mapping a vector in the IMU frame at sample k to the IMU frame at sample 0 (gyro integrated).

    The gyro is integrated per chunk of samples (10 = 20 ms at 500 Hz: the turn within a chunk is far below
    the tolerances here) so a 12 s window costs ~600 small rotations, not 6000.
    """
    n = len(t_s)
    R = np.empty((n, 3, 3))
    dt = np.diff(t_s, prepend=t_s[0])
    dt = np.where((dt > 0.0) & (dt < 0.1), dt, 0.0)
    inc = gyro * dt[:, None]
    cur = np.eye(3)
    for k0 in range(0, n, chunk):
        k1 = min(n, k0 + chunk)
        R[k0:k1] = cur
        cur = cur @ _rotvec(inc[k0 + 1:k1 + 1].sum(axis=0)) if k0 + 1 < n else cur
    return R


def judge(t_ms, acc_g, gyro_rads, exp_ms: float, g_ref: float = 1.0, hz: float = 500.0,
          long_s: Optional[float] = None) -> dict:
    """{'stopped': bool, 'why': reason when not, and the measurements} for the exposure at camera ms exp_ms.

    t_ms (N,) camera ms of the samples, acc_g (N,3) calibrated accelerometer (g), gyro_rads (N,3) bias-corrected
    gyro (rad/s). The samples should cover [exp - long_s - RUN_EXTRA_S, exp + AFTER_S]: a change of 'up' is
    looked for in the last long_s, and followed back up to RUN_EXTRA_S further when it began earlier (the braking
    of a stop seen only by its end). With less history the check uses what there is (long_window_s), but the
    exposure window must be covered.
    """
    long_s = LONG_S if long_s is None else float(long_s)
    t = np.asarray(t_ms, float) / 1000.0
    a = np.asarray(acc_g, float)
    w = np.asarray(gyro_rads, float)
    te = float(exp_ms) / 1000.0
    out = {"stopped": False}
    sel = (t >= te - long_s - RUN_EXTRA_S) & (t <= te + AFTER_S)
    t, a, w = t[sel], a[sel], w[sel]
    short = t >= te - SHORT_BEFORE_S
    span = SHORT_BEFORE_S + AFTER_S
    if short.sum() < COVERAGE * hz * span:
        out["why"] = "no sensor data" if short.sum() < 50 else \
            f"sensor data cover {short.sum() / (hz * span):.0%} of the exposure window"
        return out
    # the exposure window (the driver's own test, repeated so this module stands alone)
    b = max(1, int(round(0.2 * hz)))
    a_s, w_s = a[short], w[short]
    m = len(a_s) // b * b
    means = a_s[:m].reshape(-1, b, 3).mean(axis=1)
    out["acc_std_g"] = round(float(means.std(axis=0).max()), 5)
    out["rate_dps"] = round(float(np.degrees(np.linalg.norm(w_s[:m].reshape(-1, b, 3).mean(axis=1), axis=1)).max()), 3)
    mag_now = float(np.linalg.norm(a_s.mean(axis=0)))
    out["mag_excess_g"] = round(mag_now - g_ref, 5)
    if out["acc_std_g"] >= ACC_STD_G:
        out["why"] = f"accelerometer not steady ({out['acc_std_g']:.4f} g)"
        return out
    if out["rate_dps"] >= RATE_DPS:
        out["why"] = f"turning ({out['rate_dps']:.2f} deg/s)"
        return out
    if abs(mag_now - g_ref) > MAG_TOL_G:
        out["why"] = f"|a| {mag_now:.4f} g vs {g_ref:.4f} at rest: accelerating"
        return out
    # the long window: 0.5 s blocks ending at the exposure (what happens after it does not tilt its 'up'; the
    # exposure window above already refuses a vehicle that moves off), turned into the exposure's frame (gyro)
    bl = max(1, int(round(BLOCK_S * hz)))
    k_e = int(np.argmin(np.abs(t - te)))
    nb = (k_e + 1) // bl
    out["long_window_s"] = round(min(long_s, te - t[0]), 2)
    if nb < 2:
        out["stopped"] = True
        return out
    R = propagate(t[:k_e + 1], w[:k_e + 1])
    Re_T = R[k_e].T
    idx = np.arange(k_e + 1 - nb * bl, k_e + 1).reshape(nb, bl)
    t_b = t[idx].mean(axis=1)
    a_b = a[idx].mean(axis=1)
    mag_b = np.linalg.norm(a_b, axis=1)
    up_b = np.einsum("ij,njk,nk->ni", Re_T, R[idx[:, bl // 2]], a_b)
    up_b /= np.linalg.norm(up_b, axis=1, keepdims=True)
    now = t_b >= te - SHORT_BEFORE_S
    up_now = up_b[now].mean(axis=0)
    up_now /= np.linalg.norm(up_now)
    theta = np.degrees(np.arccos(np.clip(up_b @ up_now, -1.0, 1.0)))
    changed = (theta > DIR_TOL_DEG) & ~now
    recent = t_b >= te - long_s
    out["up_change_deg"] = round(float(theta[~now & recent].max()) if (~now & recent).any() else 0.0, 3)
    if not (changed & recent).any():
        out["stopped"] = True
        return out
    # which side was gravity: rest has the smallest |a| (see the module doc). Judged on the last change before the
    # exposure only: the newest EXPLAIN_BLOCKS of the most recent run of changed blocks (an older, larger change
    # such as pulling away must not vouch for a newer, gentle one)
    k_last = int(np.nonzero(changed & recent)[0][-1])
    k_first = k_last
    while k_first > 0 and changed[k_first - 1]:
        k_first -= 1
    whole = np.zeros(nb, bool)
    whole[k_first:k_last + 1] = True
    run = whole.copy()
    run[:max(k_first, k_last + 1 - EXPLAIN_BLOCKS)] = False
    e_now = float(mag_b[now].mean())
    excess = float((mag_b[run] - e_now).mean())
    expect = float((1.0 / np.cos(np.radians(theta[run])) - 1.0).mean())
    # the noise of a block's |a| (vertical bounce, bumps): measured on the run itself and the exposure window,
    # each about its own median (a steady braking or rest is flat), never below the floor
    dev = np.concatenate([mag_b[whole] - np.median(mag_b[whole]), mag_b[now] - np.median(mag_b[now])])
    noise = max(1.4826 * float(np.median(np.abs(dev))), MAG_NOISE_FLOOR_G)
    sig = noise * math.sqrt(1.0 / run.sum() + 1.0 / now.sum())
    out.update(changed_blocks=int(changed.sum()), excess_g=round(excess, 5), expected_g=round(expect, 5),
               noise_g=round(sig, 5))
    if expect >= MAG_TOL_G + EXPLAIN_MAG_MARGIN_G:
        # so large a tilt cannot be what the exposure holds: its |a| would exceed g_ref by `expect`, and the
        # magnitude check above passed. The vehicle held an acceleration before (braking to this stop)
        out["stopped"] = True
        out["explained"] = "the change is too large to be the exposure's acceleration (|a| at rest now)"
        return out
    if expect >= EXPLAIN_SIGMAS * sig and excess >= EXPLAIN_FRACTION * expect:
        out["stopped"] = True
        out["explained"] = "an acceleration ended before the exposure (its |a| was the larger)"
        return out
    when = te - float(t_b[k_last])
    out["why"] = (f"'up' moved {theta[run].max():.2f} deg {when:.0f} s before the exposure without the camera "
                  "turning, and |a| does not show that it is now at rest: gentle acceleration")
    return out


def ground_change(prev_gray: np.ndarray, gray: np.ndarray, mask: np.ndarray, step: int = 8) -> Optional[float]:
    """Image standstill measure: how much the scene below the horizon changed between two key frames, in units
    of the frame-to-frame noise of the sky (median |difference| ratio). ~1 at rest (only noise changes), >> 1 when
    the vehicle moves past lit ground features. None when the masked area is too dark or too small to tell (a
    dark desert): the image then says nothing, and the IMU decides. Logged only (no gating) until a real night
    shows its behaviour; stars do not move between two frames 0.5 s apart (0.002 deg).
    """
    p = prev_gray[::step, ::step].astype(np.float32)
    c = gray[::step, ::step].astype(np.float32)
    m = mask[::step, ::step] if mask.shape == prev_gray.shape else mask
    if p.shape != c.shape or m.shape != p.shape or m.sum() < 200 or (~m).sum() < 200:
        return None
    d = np.abs(c - p)
    noise = float(np.median(d[~m])) + 0.5
    texture = float(np.percentile(c[m], 90) - np.percentile(c[m], 10))
    if texture < 8.0:
        return None
    return round(float(np.median(d[m]) + np.percentile(d[m], 90)) / (2.0 * noise), 2)


def vibration_stats(acc_g, gyro_rads, hz: float = 500.0) -> dict:
    """What the camera's IMU felt over a window, for the field logs (F19: the drive's real vibration, never measured):
    acc_hp_rms_g (vibration above ~5 Hz: residual about 0.2 s means), acc_lf_std_g (0.2 s means' spread: body
    bounce, braking), gyro_rms_dps, mag_mean_g, n.
    """
    a = np.asarray(acc_g, float)
    w = np.asarray(gyro_rads, float)
    b = max(1, int(round(0.2 * hz)))
    m = len(a) // b * b
    if m < b:
        return {"n": int(len(a))}
    blocks = a[:m].reshape(-1, b, 3)
    means = blocks.mean(axis=1)
    hp = blocks - means[:, None, :]
    return {"n": int(len(a)), "acc_hp_rms_g": round(float(np.sqrt((hp ** 2).sum(axis=2).mean())), 5),
            "acc_lf_std_g": round(float(means.std(axis=0).max()), 5),
            "gyro_rms_dps": round(float(np.degrees(np.sqrt((w ** 2).sum(axis=1).mean()))), 4),
            "mag_mean_g": round(float(np.linalg.norm(a, axis=1).mean()), 5)}
