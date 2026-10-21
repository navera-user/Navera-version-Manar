#!/usr/bin/env python3
"""MARS-LVIG rosbag (ROS 1) -> a replayable flight directory for replay_flight_dataset.py.

    python3 -I navera_tools/bench/mars_lvig_extract.py SEQ.bag OUT_DIR [--scale 0.5] [--every 1]

MARS-LVIG (HKU MaRS lab, mars.hku.hk/dataset.html, CC BY-NC-SA 4.0, academic use): a DJI M300 RTK
with a downward Hikvision CA-050 global-shutter camera (2448x2048, 10 Hz), the drone's own IMU /
attitude / GNSS / barometric height (DJI OSDK), a Livox Avia (its BMI088 IMU) and the M300's RTK
(position truth). Written:

  OUT/frames/<idx>.jpg   the camera frames (scaled by --scale; JPEG q 92)
  OUT/frames.csv         idx, t (exposure, s), file
  OUT/sensors.npz        att_t/att_q (DJI attitude, xyzw), imu_t/imu_w/imu_q (DJI IMU rate rad/s +
                         orientation), limu_t/limu_w (Livox BMI088 rate rad/s, LiDAR frame),
                         gps_t/gps (DJI GNSS lat, lon, alt, status), rtk_t/rtk (RTK lat, lon, alt),
                         rel_t/rel_h (height above take-off, m), vel_t/vel (DJI velocity, m/s),
                         gimbal_t/gimbal (deg)
  OUT/info.json          sequence name, image size, topics found, time span

Only standard message types are read (the DJI-specific ones are not needed). Times are the
messages' header stamps (the bag's record time for std_msgs/Float32, which has none).

--partial LEDGER: the bag is only partly downloaded (a file of the bag's size, LEDGER listing
the 64 MiB blocks present, one index per line): the bag's uncompressed chunks found in those
blocks are read directly (the connections from the bag's index at its end, which must be present).
"""
import argparse
import csv
import json
import os
import struct
import sys

import cv2
import numpy as np


BLOCK = 64 * 1024 * 1024


def _fields(h: bytes) -> dict:
    d, i = {}, 0
    while i + 4 <= len(h):
        n = struct.unpack("<I", h[i:i + 4])[0]
        if n == 0 or i + 4 + n > len(h) or b"=" not in h[i + 4:i + 4 + n]:
            raise ValueError("not a record header")
        k, v = h[i + 4:i + 4 + n].split(b"=", 1)
        d[k] = v
        i += 4 + n
    return d


def _records(buf: bytes, p: int = 0):
    """(header fields, data) of the records in buf from p (stops at the first incomplete one)."""
    while p + 8 <= len(buf):
        hl = struct.unpack("<I", buf[p:p + 4])[0]
        if hl > 1 << 20 or p + 8 + hl > len(buf):
            return
        h = _fields(buf[p + 4:p + 4 + hl])
        dl = struct.unpack("<I", buf[p + 4 + hl:p + 8 + hl])[0]
        if p + 8 + hl + dl > len(buf):
            return
        yield h, buf[p + 8 + hl:p + 8 + hl + dl]
        p += 8 + hl + dl


class _Conn:
    def __init__(self, topic, msgtype):
        self.topic, self.msgtype = topic, msgtype


def partial_messages(bag: str, ledger: str, want):
    """(connection, t_bag_ns, raw) of the messages of `want` topics in the blocks present."""
    have = sorted({int(x) for x in open(ledger).read().split()})
    size = os.path.getsize(bag)
    with open(bag, "rb") as f:
        head = f.read(4096)
        hl = struct.unpack("<I", head[13:17])[0]
        index_pos = struct.unpack("<Q", _fields(head[17:17 + hl])[b"index_pos"])[0]
        if not all(k in have for k in range(index_pos // BLOCK, (size - 1) // BLOCK + 1)):
            raise SystemExit("the bag's index (its last blocks) is not downloaded")
        f.seek(index_pos)
        conns = {}
        for h, d in _records(f.read(size - index_pos)):
            if h.get(b"op") == b"\x07":
                msgtype = _fields(d)[b"type"].decode().replace("/", "/msg/")
                conns[struct.unpack("<I", h[b"conn"])[0]] = _Conn(h[b"topic"].decode(), msgtype)
        runs = []                                    # contiguous block ranges present
        for k in have:
            if runs and k == runs[-1][1] + 1:
                runs[-1][1] = k
            else:
                runs.append([k, k])
        for k0, k1 in runs:
            f.seek(k0 * BLOCK)
            buf = f.read(min(size, (k1 + 1) * BLOCK) - k0 * BLOCK)
            p = buf.find(b"op=\x05")
            while p >= 0:
                for q in range(max(0, p - 64), p):   # the chunk header starts a little before
                    try:
                        hl = struct.unpack("<I", buf[q:q + 4])[0]
                        h = _fields(buf[q + 4:q + 4 + hl]) if 8 < hl < 256 else None
                    except ValueError:
                        h = None
                    if h and h.get(b"op") == b"\x05" and b"compression" in h:
                        break
                else:
                    p = buf.find(b"op=\x05", p + 1)
                    continue
                dl = struct.unpack("<I", buf[q + 4 + hl:q + 8 + hl])[0]
                if q + 8 + hl + dl > len(buf):
                    break
                if h[b"compression"] == b"none":
                    for mh, md in _records(buf[q + 8 + hl:q + 8 + hl + dl]):
                        if mh.get(b"op") != b"\x02":
                            continue
                        c = conns.get(struct.unpack("<I", mh[b"conn"])[0])
                        if c is not None and c.topic in want:
                            sec, nsec = struct.unpack("<II", mh[b"time"])
                            yield c, sec * 1_000_000_000 + nsec, md
                p = buf.find(b"op=\x05", q + 8 + hl + dl)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bag")
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=0.5, help="image scale (0.5: 1224x1024)")
    ap.add_argument("--every", type=int, default=1, help="keep every n-th camera frame")
    ap.add_argument("--partial", default="", help="ledger of the 64 MiB blocks present (partly downloaded bag)")
    a = ap.parse_args()
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore
    ts = get_typestore(Stores.ROS1_NOETIC)
    os.makedirs(os.path.join(a.out, "frames"), exist_ok=True)
    want = {"/left_camera/image/compressed", "/dji_osdk_ros/attitude", "/dji_osdk_ros/imu", "/livox/imu",
            "/dji_osdk_ros/gps_position", "/dji_osdk_ros/rtk_position", "/dji_osdk_ros/height_above_takeoff",
            "/dji_osdk_ros/velocity", "/dji_osdk_ros/gimbal_angle"}
    S = {k: [] for k in ("att", "imu", "limu", "gps", "rtk", "rel", "vel", "gimbal")}
    rows, n_img, size = [], 0, None
    stamp = lambda m: m.header.stamp.sec + m.header.stamp.nanosec * 1e-9   # noqa: E731
    found = set()

    def messages():
        if a.partial:
            yield from partial_messages(a.bag, a.partial, want)
            return
        with Reader(a.bag) as r:
            conns = [c for c in r.connections if c.topic in want]
            yield from r.messages(connections=conns)

    for c, t_bag, raw in messages():
        found.add(c.topic)
        m = ts.deserialize_ros1(raw, c.msgtype)
        tp = c.topic
        if tp == "/left_camera/image/compressed":
            n_img += 1
            if (n_img - 1) % a.every:
                continue
            img = cv2.imdecode(np.frombuffer(bytes(m.data), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            if a.scale != 1.0:
                img = cv2.resize(img, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_AREA)
            size = (img.shape[1], img.shape[0])
            idx = len(rows)
            f = f"{idx:06d}.jpg"
            cv2.imwrite(os.path.join(a.out, "frames", f), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            rows.append((idx, f"{stamp(m):.6f}", f))
            if idx % 500 == 0:
                print("frames", idx, flush=True)
        elif tp == "/dji_osdk_ros/attitude":
            q = m.quaternion
            S["att"].append((stamp(m), q.x, q.y, q.z, q.w))
        elif tp == "/dji_osdk_ros/imu":
            w, q = m.angular_velocity, m.orientation
            S["imu"].append((stamp(m), w.x, w.y, w.z, q.x, q.y, q.z, q.w))
        elif tp == "/livox/imu":
            w = m.angular_velocity
            S["limu"].append((stamp(m), w.x, w.y, w.z))
        elif tp == "/dji_osdk_ros/gps_position":
            S["gps"].append((stamp(m), m.latitude, m.longitude, m.altitude, m.status.status))
        elif tp == "/dji_osdk_ros/rtk_position":
            S["rtk"].append((stamp(m), m.latitude, m.longitude, m.altitude))
        elif tp == "/dji_osdk_ros/height_above_takeoff":
            S["rel"].append((t_bag * 1e-9, m.data))
        elif tp == "/dji_osdk_ros/velocity":
            v = m.vector
            S["vel"].append((stamp(m), v.x, v.y, v.z, t_bag * 1e-9))
        elif tp == "/dji_osdk_ros/gimbal_angle":
            v = m.vector
            S["gimbal"].append((stamp(m), v.x, v.y, v.z))
    with open(os.path.join(a.out, "frames.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "t", "file"])
        w.writerows(rows)
    out = {}
    for k, v in S.items():
        arr = np.array(v, dtype=np.float64) if v else np.zeros((0, 2))
        if len(arr):
            arr = arr[np.argsort(arr[:, 0], kind="stable")]
        out[k] = arr
    np.savez_compressed(os.path.join(a.out, "sensors.npz"), **out)
    info = dict(sequence=os.path.splitext(os.path.basename(a.bag))[0], image_size=size, scale=a.scale,
                every=a.every, frames=len(rows), topics=sorted(found), partial=bool(a.partial),
                counts={k: int(len(v)) for k, v in out.items()},
                t0=float(rows[0][1]) if rows else None, t1=float(rows[-1][1]) if rows else None)
    json.dump(info, open(os.path.join(a.out, "info.json"), "w"), indent=1)
    print(json.dumps(info), flush=True)


if __name__ == "__main__":
    sys.exit(main())
