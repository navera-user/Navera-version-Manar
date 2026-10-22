#!/usr/bin/env python3
"""Check the 360 camera's own attitude (gyro + gravity) against the screen: a fixed grid of dots on the
screen gives, in every frame, the camera's true rotation AND position relative to the screen (pose fit
with the calibrated lens), so a turn by hand is measured apart from the lens moving.

    python3 navera_tools/bench/attitude_check.py [--seconds 120] [--out attitude_check.csv]

Why: on the map bench (screen_flight.py) a hand tilt also moves the lens, and with the screen 41 cm away
1 cm of lens movement looks like ~34 m of vehicle movement at 1,400 m, so position errors there cannot
tell an attitude error from a moved camera. Here, per frame: the gyro's turn since the start, the
screen's measured turn, their difference (the attitude error that would misplace a fix on a real
vehicle: 1 degree = 24 m at 1,400 m) and how far the lens moved (mm).

Run lens_calib_screen.py --save before (the left lens and a first screen pose). Lights may stay on.

--kit: the attitude and the frame stamps of the PRODUCT's Insta360 kit (camera_pkg insta360_kit:
AttitudeFilter, each key frame decoded alone and stamped with its own packet) instead of the field
driver's; --mount: the camera's axes on the "vehicle" for it (the bench: standing, +y,+z,+x). The
offset fit at the end then checks the kit's exposure stamp (expected best near 0 ms).
"""
import argparse
import csv
import json
import math
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    sys.path.insert(0, p)

from navera_tools.bench.lens_calib_screen import POSE_FILE, SH, SW, grid  # noqa: E402
from navera_tools.field.insta360_usb import Insta360Usb  # noqa: E402
from navera_tools.field.reprocess360 import rotvec  # noqa: E402
from navera_tools.field.sky360 import default_lenses  # noqa: E402
from navera_common.camera_model import quat_to_matrix  # noqa: E402

W = "NAVERA attitude"


class KitCam:
    """The product kit behind the field driver's interface (latest_stamped, attitude_at, gravity):
    camera_pkg.insta360_kit on the live camera, attitudes as R (camera IMU -> world)."""

    def __init__(self, mount: str):
        import collections
        import threading
        for p in (os.path.join(ROOT, "camera_pkg"),):
            sys.path.insert(0, p)
        from camera_pkg.insta360_attitude import AttitudeFilter
        from camera_pkg.insta360_imu import ImuStream, UsbImuSource, mount_rotation
        from camera_pkg.insta360_kit import Insta360Kit, imu_calibration_file
        from navera_common.insta360_protocol import load_imu_calibration
        self.R_bc = mount_rotation(mount)
        self.kit = Insta360Kit(ImuStream(self.R_bc, 5, load_imu_calibration(imu_calibration_file())),
                               AttitudeFilter(), None)
        self._lock = threading.Lock()
        self._att = collections.deque(maxlen=6000)        # (camera ms, R camera IMU -> world)
        self._acc = collections.deque(maxlen=100)
        self._frame = (None, 0.0, None)
        self.error = None
        self._stop = False
        self.usb = UsbImuSource(self._on_packet)
        threading.Thread(target=self._frames, daemon=True).start()

    def _on_packet(self, t, p):
        for s, st in self.kit.feed(t, p):
            with self._lock:
                self._att.append((s.cam_ms, quat_to_matrix(st.q) @ self.R_bc))
                self._acc.append(self.R_bc.T @ s.accel)

    def _frames(self):
        while not self._stop:
            for fr in self.kit.wait_frames(0.5):
                with self._lock:
                    self._frame = (fr.image, fr.arrival, fr.cam_ms)

    def latest_stamped(self):
        with self._lock:
            return self._frame

    def attitude_at(self, cam_ms):
        with self._lock:
            hist = list(self._att)
        if not hist or cam_ms is None or cam_ms < hist[0][0] or cam_ms > hist[-1][0] + 200:
            return None
        return min(hist, key=lambda h: abs(h[0] - cam_ms))[1]

    def gravity(self):
        with self._lock:
            a = np.mean(list(self._acc), axis=0) if self._acc else None
        return (None, None, None) if a is None else (a / np.linalg.norm(a), None, None)

    def close(self):
        self._stop = True
        self.usb.close()


OFFSETS_MS = (-400, -300, -200, -150, -100, -60, -30, 0, 30, 60, 100, 150, 200, 300, 400)


def angle_deg(R):
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))


def project(lens, Rs, T, P):
    X = P @ Rs.T + T                                       # screen mm → IMU frame
    x, y, _ = lens.project(X @ lens.R_lens_imu.T)
    return np.c_[x, y]


def detect(g, near, radius=750.0):
    """Dot centres (full-frame pixels) near the screen; only that part of the frame is searched."""
    x0, y0 = max(0, int(near[0] - radius)), max(0, int(near[1] - radius))
    x1, y1 = min(g.shape[1], int(near[0] + radius)), min(g.shape[0], int(near[1] + radius))
    g = g[y0:y1, x0:x1]
    r = g - cv2.GaussianBlur(g, (0, 0), 15)
    thr = max(25.0, 0.4 * float(np.percentile(r, 99.9)))
    n, lab, st, cen = cv2.connectedComponentsWithStats((r > thr).astype(np.uint8))
    out = []
    for k in range(1, n):
        if not 2 <= st[k, cv2.CC_STAT_AREA] <= 400:
            continue
        bx, by, bw, bh = st[k, :4]
        sub = lab[by:by + bh, bx:bx + bw] == k
        w = np.clip(r[by:by + bh, bx:bx + bw], 0, None) * sub
        ys, xs = np.mgrid[by:by + bh, bx:bx + bw]
        if w.sum() > 0 and math.hypot(cen[k][0] + x0 - near[0], cen[k][1] + y0 - near[1]) < radius:
            out.append((float((xs * w).sum() / w.sum()) + x0, float((ys * w).sum() / w.sum()) + y0))
    return np.array(out).reshape(-1, 2)


def pair(pred, det, tol):
    """Shift the prediction by the offset most pairs agree on (the lens may have moved), then pair."""
    from scipy.spatial import cKDTree
    if len(det) < 6:
        return np.array([], int), np.array([], int), np.zeros(2)
    tree = cKDTree(det)
    d, k = tree.query(pred)
    off = np.median(det[k] - pred, axis=0)
    for _ in range(2):
        d, k = tree.query(pred + off, distance_upper_bound=tol)
        ok = np.isfinite(d)
        if ok.sum() >= 6:
            off = np.median(det[k[ok]] - pred[ok], axis=0)
    d, k = tree.query(pred + off, distance_upper_bound=tol)
    ok = np.isfinite(d)
    kk = k[ok]
    uniq = np.array([np.sum(kk == v) == 1 for v in kk], bool)
    return np.nonzero(ok)[0][uniq], kk[uniq], off


def fit_pose(lens, Rs, T, P, det):
    from scipy.optimize import least_squares
    from scipy.spatial.transform import Rotation
    x0 = np.r_[Rotation.from_matrix(Rs).as_rotvec(), T]

    def res(x):
        return (project(lens, rotvec(x[:3]), x[3:], P) - det).ravel()
    f = least_squares(res, x0, x_scale="jac", loss="soft_l1", f_scale=2.0)
    r = res(f.x).reshape(-1, 2)
    return rotvec(f.x[:3]), f.x[3:], float(np.sqrt(np.mean(np.sum(r ** 2, axis=1))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--height", type=float, default=1403.0, help="m: the map bench's height, to express lens movement on the ground")
    ap.add_argument("--out", default="attitude_check.csv")
    ap.add_argument("--kit", action="store_true", help="the product kit's attitude and stamps (camera_pkg)")
    ap.add_argument("--mount", default="+y,+z,+x", help="--kit: camera IMU axes along the body x,y,z")
    a = ap.parse_args()
    pose = json.load(open(POSE_FILE))
    lens = next(L for L in default_lenses() if L.name == pose.get("lens", "left"))
    mm = pose["mm_per_px"]
    G = grid(8, 5)
    P = np.c_[(G - [SW / 2, SH / 2]) * mm, np.zeros(len(G))]
    img = np.zeros((SH, SW), np.uint8)
    for x, y in G:
        cv2.circle(img, (int(x), int(y)), 9, 255, -1, cv2.LINE_AA)
    cv2.namedWindow(W, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(W, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam = KitCam(a.mount) if a.kit else Insta360Usb()
    end = time.time() + 5.0                                # the stream delay and the IMU start
    while time.time() < end:
        cv2.imshow(W, img)
        cv2.waitKey(40)
    Rs, T = rotvec(np.array(pose["rotvec"])), np.array(pose["T_mm"])
    Rs0 = T0 = R_att0 = None
    rows, last_ms, t0 = [], None, time.time()
    frames, att_log, att_seen = [], [], -1                 # for the time-offset fit afterwards (any offset)
    while time.time() - t0 < a.seconds:
        cv2.imshow(W, img)
        cv2.waitKey(30)
        f, _, ms = cam.latest_stamped()
        if f is None or ms == last_ms:
            continue
        last_ms = ms
        R_att = cam.attitude_at(ms)
        if R_att is None:
            print(f"{time.time() - t0:6.1f}s no attitude for this frame (IMU silent? {cam.error})", flush=True)
            continue
        if Rs0 is not None:                                # predict from the gyro: the screen stays, the camera turns
            Rs, T = R_att.T @ R_att0 @ Rs0, R_att.T @ R_att0 @ T0
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        pred = project(lens, Rs, T, P)
        det = detect(g, pred.mean(axis=0))
        pi, di, off = pair(pred, det, 30.0 if Rs0 is not None else 60.0)
        if len(pi) < 12:
            print(f"{time.time() - t0:6.1f}s only {len(pi)} dots paired ({len(det)} spots)", flush=True)
            continue
        Rs_t, T_t, rms = fit_pose(lens, Rs, T, P[pi], det[di])
        if Rs0 is None and rms > 1.0:                      # the saved pose was a first guess: pair again from this fit
            Rs, T = Rs_t, T_t
            print(f"start: fit {rms:.1f} px, pairing again", flush=True)
            continue
        if Rs0 is None:
            Rs0, T0, R_att0 = Rs_t, T_t, R_att
            up0 = cam.gravity()[0]
            up0 = up0 if up0 is not None else np.array([1.0, 0.0, 0.0])      # the accelerometer at rest points up
            up_ref = R_att0 @ up0                          # 'up' in the attitude's reference frame
            c0 = -Rs0.T @ T0                               # the lens in screen mm
            print(f"start: {len(pi)} dots, rms {rms:.2f} px, lens {np.linalg.norm(T0):.0f} mm from the screen centre", flush=True)
            continue
        R_gyro = R_att0.T @ R_att                          # IMU now → IMU at start, by the camera's own sensor
        R_vis = Rs0 @ Rs_t.T                               # the same, measured on the screen
        err = angle_deg(R_vis.T @ R_gyro)
        # split: tilt (where 'up' points: what misplaces a fix seen from above, and the celestial zenith)
        # and the rest, a turn about the vertical (heading: gravity cannot correct it, the stars and the map can)
        up_t = R_att.T @ up_ref                            # true 'up' now, in the IMU frame, from the gyro
        up_v = Rs_t @ Rs0.T @ up0                          # the same from the screen: IMU at start → now
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(up_t @ up_v)))))
        c = -Rs_t.T @ T_t
        dc = c - c0                                        # lens movement in screen axes (x right, y down, z away)
        dist = float(np.linalg.norm(T0))
        ground = a.height * float(np.hypot(dc[0], dc[1])) / dist
        row = dict(t=round(time.time() - t0, 2), dots=len(pi), rms_px=round(rms, 2), gyro_turn_deg=round(angle_deg(R_gyro), 2),
                   screen_turn_deg=round(angle_deg(R_vis), 2), attitude_err_deg=round(err, 2), tilt_err_deg=round(tilt, 2),
                   err_on_ground_m=round(math.radians(err) * a.height, 1),
                   lens_moved_mm=round(float(np.linalg.norm(dc)), 1), lens_moved_on_ground_m=round(ground, 1))
        # the frame's capture time against the IMU's: the attitude a few ms either side, for the offset fit
        for off_ms in OFFSETS_MS:
            Ro = cam.attitude_at(ms + off_ms)
            row[f"err_at_{off_ms}ms"] = None if Ro is None else round(angle_deg(R_vis.T @ R_att0.T @ Ro), 3)
        rows.append(row)
        frames.append((ms, R_vis))
        with cam._lock:
            hist = [h for h in cam._att if h[0] > att_seen]
        if hist:
            att_log.extend(hist)
            att_seen = hist[-1][0]
        print(f"{row['t']:6.1f}s turned: gyro {row['gyro_turn_deg']:5.1f} screen {row['screen_turn_deg']:5.1f} deg | "
              f"attitude error {err:4.2f} deg, tilt {tilt:4.2f} deg (= {math.radians(tilt) * a.height:5.1f} m) | lens moved {row['lens_moved_mm']:5.1f} mm "
              f"(= {ground:5.0f} m on the map bench) | {len(pi)} dots {rms:.1f} px", flush=True)
    with cam._lock:
        att_log.extend(h for h in cam._att if h[0] > att_seen)
    cam.close()
    cv2.destroyAllWindows()
    if frames:
        np.savez(os.path.splitext(a.out)[0] + "_attitude.npz", att_ms=np.array([h[0] for h in att_log]),
                 att_R=np.array([h[1] for h in att_log]), frame_ms=np.array([f[0] for f in frames]),
                 frame_R_vis=np.array([f[1] for f in frames]), frame_rms=np.array([r["rms_px"] for r in rows]),
                 R_att0=R_att0)
    if rows:
        with open(a.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        # frames taken while turning are blurred and the pose fit is poor: judge on sharp fits only
        sharp = [r for r in rows if r["rms_px"] < 1.0]
        for name, rr in (("sharp frames", sharp), ("sharp, turned > 3 deg", [r for r in sharp if r["gyro_turn_deg"] > 3.0])):
            if rr:
                e = np.array([r["attitude_err_deg"] for r in rr])
                tl = np.array([r["tilt_err_deg"] for r in rr])
                lm = np.array([r["lens_moved_on_ground_m"] for r in rr])
                print(f"{name}: {len(rr)} frames, attitude error median {np.median(e):.2f} max {e.max():.2f} deg; "
                      f"tilt error median {np.median(tl):.2f} max {tl.max():.2f} deg "
                      f"(= {math.radians(np.median(tl)) * a.height:.0f} / {math.radians(tl.max()) * a.height:.0f} m at {a.height:.0f} m); "
                      f"lens movement as map error median {np.median(lm):.0f} max {lm.max():.0f} m")
        # frame time vs IMU time: the offset that makes the gyro agree best with the screen while turning
        mv = [r for r in sharp if r["gyro_turn_deg"] > 1.0 or r["screen_turn_deg"] > 1.0]
        if len(mv) >= 5:
            med = {o: float(np.median([r[f"err_at_{o}ms"] for r in mv if r[f"err_at_{o}ms"] is not None] or [np.nan]))
                   for o in OFFSETS_MS}
            best = min(med, key=lambda o: med[o] if med[o] == med[o] else 1e9)
            print("attitude error (median, sharp turned frames) by IMU time offset: "
                  + ", ".join(f"{o:+d} ms {v:.2f}" for o, v in med.items()) + f" | best {best:+d} ms")
    os._exit(0)


if __name__ == "__main__":
    main()
