#!/usr/bin/env python3
"""A synthetic Insta360 One R raw recording of a flight over a map — the Insta360 kit end to end
without the camera. SIMULATION: flat ground, the map's own imagery (or another date's), kinematic
IMU with the measured noise; the USB packets and their timing are the camera's.

    python3 navera_tools/sim/insta360_raw_sim.py --area AREA_IMAGES_DIR --lat 35.8223 --lon 10.6169 \
        --seconds 150 --agl 400 --out OUT_DIR [--profile uav_survey] [--render-tiles OTHER_DATE_DIR]

OUT_DIR/raw/raw360_0000.bin   the field RawRecorder's format (navera_common.insta360_protocol): IMU
                              packets (0x30, 50 records of 500 Hz, camera ms + accel g + gyro rad/s in
                              the camera's IMU frame) and H.264 key frames (0x20, 3840x1920 dual
                              fisheye, SPS/PPS in each, 2 per second), stamped at the exposure on the
                              camera's clock, arriving ~150 ms later on the host clock
OUT_DIR/truth.csv             t (host s), lat, lon, agl, qx, qy, qz, qw (body -> ENU), heading
OUT_DIR/gps.csv               t, lat, lon, alt: a GPS at 5 Hz with 1.5 m noise (until the replay denies it)

The camera is mounted LYING with the LEFT lens looking down (NAVERA_INSTA360_MOUNT_AXES default
+x,+z,-y); the right lens sees a plain sky. Ground colours come from the map tiles (z of the files),
sampled on a half-resolution ray grid; the lens is the calibrated equidistant model
(camera_pkg.insta360_view, lens file or the 2026-10-19 values).
"""
import argparse
import csv
import math
import os
import re
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "camera_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

from camera_pkg.insta360_imu import mount_rotation  # noqa: E402
from camera_pkg.insta360_kit import KIT_EXPOSURE_LAG_MS, video_packet  # noqa: E402
from camera_pkg.insta360_view import FRAME_H, FRAME_W, load_lenses  # noqa: E402
from navera_common import insta360_protocol as proto  # noqa: E402
from navera_tools.sim.insta360_motion import decimate, simulate  # noqa: E402

G = 9.80665
CAM0_MS = 7_000_000
HOST0 = 1_800_000_000.0


class TileMap:
    """The tiles of an area folder (tile_Z_X_Y.jpg) as one mosaic, sampled by east/north metres."""

    def __init__(self, folder: str):
        names = [n for n in os.listdir(folder) if re.fullmatch(r"tile_\d+_\d+_\d+\.(jpg|png)", n)]
        if not names:
            raise SystemExit(f"{folder}: no tile_Z_X_Y.jpg files")
        zs = sorted({int(n.split("_")[1]) for n in names})
        self.z = zs[-1]
        xy = [tuple(int(v) for v in n.split(".")[0].split("_")[2:]) for n in names if int(n.split("_")[1]) == self.z]
        self.x0, self.y0 = min(x for x, _ in xy), min(y for _, y in xy)
        nx, ny = max(x for x, _ in xy) - self.x0 + 1, max(y for _, y in xy) - self.y0 + 1
        self.img = np.full((ny * 256, nx * 256, 3), 90, np.uint8)
        ext = names[0].split(".")[-1]
        for x, y in xy:
            t = cv2.imread(os.path.join(folder, f"tile_{self.z}_{x}_{y}.{ext}"))
            if t is not None and t.shape[:2] == (256, 256):
                self.img[(y - self.y0) * 256:(y - self.y0 + 1) * 256, (x - self.x0) * 256:(x - self.x0 + 1) * 256] = t

    def pixel(self, lat, lon):
        n = 2 ** self.z
        r = np.radians(lat)
        fx = (np.asarray(lon) + 180.0) / 360.0 * n
        fy = (1.0 - np.log(np.tan(r) + 1.0 / np.cos(r)) / math.pi) / 2.0 * n
        return (fx - self.x0) * 256.0, (fy - self.y0) * 256.0

    def m_per_px(self, lat):
        return 40_075_016.7 * math.cos(math.radians(lat)) / (2 ** self.z * 256)


def lens_rays_body(lens, R_body_cam, step=2):
    """Body-frame unit rays of the lens' pixels on a grid of `step` px (its half of the frame), and
    the grid's pixel coordinates; rays beyond 95 deg from the axis are NaN."""
    xs = np.arange(lens.x_range[0], lens.x_range[1], step) + 0.5 * (step - 1)
    ys = np.arange(0, FRAME_H, step) + 0.5 * (step - 1)
    X, Y = np.meshgrid(xs, ys)
    dx, dy = X - lens.cx, Y - lens.cy
    r = np.hypot(dx, dy)
    th = r / lens.f
    for _ in range(8):                                   # r = f (th + k1 th^3), Newton
        g = lens.f * (th + lens.k1 * th ** 3) - r
        th -= g / (lens.f * (1 + 3 * lens.k1 * th ** 2))
    phi = np.arctan2(dy, dx)
    v_lens = np.stack([np.sin(th) * np.cos(phi), np.sin(th) * np.sin(phi), np.cos(th)], -1)
    v_imu = v_lens @ lens.R_lens_imu                      # lens = R_lens_imu @ imu
    v_body = v_imu @ R_body_cam.T
    v_body[th > math.radians(95)] = np.nan
    return v_body, X, Y


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", required=True, help="map tiles folder (the area's images/)")
    ap.add_argument("--render-tiles", help="tiles the GROUND is drawn from (default --area: same imagery)")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--seconds", type=float, default=150.0)
    ap.add_argument("--agl", type=float, default=400.0)
    ap.add_argument("--profile", default="uav_survey")
    ap.add_argument("--heading", type=float, default=30.0)
    ap.add_argument("--mount", default="+x,+z,-y")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    os.makedirs(os.path.join(a.out, "raw"), exist_ok=True)
    tiles = TileMap(a.render_tiles or a.area)
    R_bc = mount_rotation(a.mount)
    lenses, _ = load_lenses()
    down = lenses[0]
    rays, gx, gy = lens_rays_body(down, R_bc)
    m = simulate(a.profile, a.seconds, seed=a.seed, heading0_deg=a.heading)
    lat0, lon0 = a.lat, a.lon
    lat = lat0 + m.north / 111_320.0
    lon = lon0 + m.east / (111_320.0 * math.cos(math.radians(lat0)))
    cam_ms = CAM0_MS + np.round(m.t * 1000.0).astype(np.int64)
    host = HOST0 + m.t                                    # camera ms -> host: offset HOST0 - CAM0/1000

    # the IMU in the camera's frame, g and rad/s
    acc_cam = (m.f @ R_bc) / G                            # cam = R_bc^T body (row vectors)
    gyr_cam = m.w @ R_bc
    records = []                                          # (arrival, packet)
    for k in range(0, len(m.t) - 50, 50):
        body = b"".join(proto.IMU_RECORD.pack(int(cam_ms[k + i]), *acc_cam[k + i], *gyr_cam[k + i]) for i in range(50))
        p = b"\x01\x00\x00" + bytes([proto.KIND_IMU]) + int(cam_ms[k]).to_bytes(4, "little") + b"\x00" * 4 + body
        records.append((host[k + 49] + 0.004 + 0.02 * np.random.default_rng(k).random(), p))

    import av
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = FRAME_W, FRAME_H, "yuv420p"
    enc.options = {"preset": "ultrafast", "tune": "zerolatency", "x264-params": "keyint=1:repeat-headers=1",
                   "crf": "20"}
    sky = np.zeros((FRAME_H, FRAME_W // 2, 3), np.uint8)
    sky[:] = (235, 200, 160)
    truth = []
    step = int(round(500 / a.fps))
    for k in range(250, len(m.t) - 1000, step):           # from 0.5 s, not in the last 2 s
        R = m.R[k]
        d = rays @ R.T                                    # world (ENU) directions
        dz = -d[..., 2]
        ok = dz > 0.05
        t = np.where(ok, a.agl / np.where(ok, dz, 1.0), np.nan)
        east, north = d[..., 0] * t, d[..., 1] * t
        px, py = tiles.pixel(lat[k] + north / 111_320.0,
                             lon[k] + east / (111_320.0 * math.cos(math.radians(lat0))))
        mx = cv2.resize(np.nan_to_num(px, nan=-1e5).astype(np.float32), (FRAME_W // 2, FRAME_H))
        my = cv2.resize(np.nan_to_num(py, nan=-1e5).astype(np.float32), (FRAME_W // 2, FRAME_H))
        ground = cv2.remap(tiles.img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                           borderValue=(200, 180, 160))
        inside = cv2.resize(np.isfinite(px).astype(np.uint8), (FRAME_W // 2, FRAME_H), interpolation=cv2.INTER_NEAREST)
        ground[inside == 0] = 0
        frame = np.concatenate([ground, sky], axis=1)
        data = b""
        for pk in enc.encode(av.VideoFrame.from_ndarray(frame, format="bgr24")):
            data += bytes(pk)
        exp_ms = int(cam_ms[k])
        records.append((host[k] + 0.15 + len(data) / 40e6, video_packet(exp_ms + KIT_EXPOSURE_LAG_MS, data)))
        q = _quat(R)
        truth.append((host[k], lat[k], lon[k], a.agl, *q, m.heading[k]))
        if len(truth) % 20 == 0:
            print(f"  {len(truth)} frames, t {m.t[k]:.0f} s, {len(data) / 1e3:.0f} kB", flush=True)
    for pk in enc.encode(None):
        pass
    records.sort(key=lambda r: r[0])
    path = os.path.join(a.out, "raw", "raw360_0000.bin")
    with open(path, "wb") as f:
        f.write(proto.RAW_MAGIC)
        for t, p in records:
            kind, ms = proto.stream_kind(p)
            f.write(proto.RAW_RECORD.pack(t, kind, ms, len(p)))
            f.write(p)
    with open(os.path.join(a.out, "truth.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "lat", "lon", "agl", "qx", "qy", "qz", "qw", "heading"])
        w.writerows(truth)
    rng = np.random.default_rng(a.seed + 11)
    with open(os.path.join(a.out, "gps.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "lat", "lon", "alt"])
        for k in range(0, len(m.t), 100):
            e, n = rng.normal(0, 1.5, 2)
            w.writerow([host[k], lat[k] + n / 111_320.0, lon[k] + e / (111_320.0 * math.cos(math.radians(lat0))),
                        a.agl + rng.normal(0, 3.0)])
    # the decimated IMU truth for the attitude comparison
    td, _, _ = decimate(m)
    np.savez_compressed(os.path.join(a.out, "motion_truth.npz"), t=HOST0 + m.t[::5], R=m.R[::5],
                        heading=m.heading[::5], speed=m.speed[::5], td=HOST0 + td)
    print(f"{len(truth)} frames, {len(records)} packets -> {path} ({os.path.getsize(path) / 1e6:.0f} MB)")


def _quat(R):
    from camera_pkg.insta360_attitude import quat_from_matrix
    return quat_from_matrix(R)


if __name__ == "__main__":
    main()
