"""The Insta360 One R USB protocol (Android USB mode, reverse engineered) and its raw recordings.

Shared, not copied, by the field tools' live driver (navera_tools.field.insta360_usb, which imports
these names) and the flight camera package (camera_pkg.insta360_imu: the camera's IMU as
sensor_msgs/Imu). Pure Python + numpy, no USB, no ROS.

Every packet is an int32 little-endian total length (itself included) + payload:

  sync       06 00 00 "syNceNdinS"          keepalive  05 00 00
  message    04 00 00 <code u16> 02 <seq u24> 80 00 00 <protobuf>
  stream     01 00 00 <kind> <camera ms u32> ...   payload from byte 12
             kind 0x20 H.264 (Annex-B), 0x30 IMU, 0x40 per-frame info, 0x10 other

IMU records (~500 Hz, 50 per packet) are 56 bytes: u64 camera ms, accelerometer x y z (g),
gyroscope x y z (rad/s), in the camera's own IMU frame (+x up when the camera stands, +y the
LEFT circle's optical axis, +z = x cross y).
"""
import json
import os
import struct
from typing import Iterator, List, Optional, Tuple

import numpy as np

VENDOR = 0x2E1A
EP_OUT, EP_IN, EP_IN2 = 0x01, 0x81, 0x82
PKT_SYNC = b"\x06\x00\x00syNceNdinS"
PKT_KEEPALIVE = b"\x05\x00\x00"
CMD_START_LIVE, CMD_STOP_LIVE = 1, 2
# StartLiveStream: enableVideo, videoBitrate 40, resolution 3840x1920, enableGyro,
# videoBitrate1 40, resolution1 3040x1520, previewStreamNum 2 (→ full resolution)
START_FULL = bytes.fromhex("10013028380040014828500f5802")
KIND_VIDEO, KIND_IMU, KIND_FRAME = 0x20, 0x30, 0x40
IMU_RECORD = struct.Struct("<Q6d")
# a video packet's camera-clock stamp is ~1.5 s after the picture was taken (on the IMU's clock): measured
# 2026-10-19 against a dot grid on the screen while the camera was turned by hand (bench/attitude_check.py,
# best match at -1500 ms, worse by 0.2 deg at +-50 ms; the turn error fell from 1.8 to 0.4 deg median)
FRAME_STAMP_LAG_MS = 1500
IMU_HZ = 500
MAX_PACKET_BYTES = 8_000_000
IMU_CALIBRATION = os.environ.get("NAVERA_INSTA360_IMU", os.path.expanduser("~/.navera_sim/insta360_usb_imu.json"))

RAW_MAGIC = b"NAVRAW360v1\n"
RAW_RECORD = struct.Struct("<dBII")                     # Jetson arrival time, kind, camera ms, packet length


def load_imu_calibration(path: str = IMU_CALIBRATION):
    """(accel bias g, accel scale, gyro bias rad/s) from a 6-position calibration, or neutral values."""
    try:
        with open(path) as f:
            d = json.load(f)
        return (np.array(d["accel_bias_g"], float), np.array(d["accel_scale"], float),
                np.array(d["gyro_bias_rad_s"], float))
    except (OSError, ValueError, KeyError):
        return np.zeros(3), np.ones(3), np.zeros(3)


def frame_packet(payload: bytes) -> bytes:
    """A payload with its int32 length prefix, as written to the camera."""
    return struct.pack("<i", len(payload) + 4) + payload


def message_payload(code: int, seq: int, body: bytes) -> bytes:
    """A command message (before frame_packet): code, its sequence number (24 bits), protobuf body."""
    return (b"\x04\x00\x00" + code.to_bytes(2, "little") + b"\x02"
            + struct.pack("<i", seq)[:3] + b"\x80\x00\x00" + body)


def split_packets(buf: bytearray) -> List[bytes]:
    """The whole packets at the start of buf (removed from it); a partial one stays for the next read.
    A length out of range means the stream is out of step: everything buffered is dropped.
    """
    out, i = [], 0
    while i + 4 <= len(buf):
        n = struct.unpack_from("<i", buf, i)[0]
        if n < 4 or n > MAX_PACKET_BYTES:
            i = len(buf)
            break
        if i + n > len(buf):
            break
        out.append(bytes(buf[i + 4:i + n]))
        i += n
    del buf[:i]
    return out


def stream_kind(p: bytes):
    """(kind, camera ms) of a stream packet, or (None, None) for any other packet."""
    if p[:1] != b"\x01" or len(p) < 12:
        return None, None
    return p[3], struct.unpack_from("<I", p, 4)[0]


def imu_records(p: bytes) -> List[Tuple]:
    """The IMU records of a stream packet of kind KIND_IMU: (camera ms, ax, ay, az g, wx, wy, wz rad/s)."""
    body = p[12:]
    return [IMU_RECORD.unpack_from(body, k) for k in range(0, len(body) - IMU_RECORD.size + 1, IMU_RECORD.size)]


def raw_files(path: str) -> List[str]:
    """The raw360_NNNN.bin files of a recording, in order: path is the folder, or one of its files."""
    if os.path.isfile(path):
        return [path]
    names = sorted(n for n in os.listdir(path) if n.startswith("raw360_") and n.endswith(".bin"))
    return [os.path.join(path, n) for n in names]


def read_raw(folder: str) -> Iterator[Tuple[float, int, int, bytes]]:
    """The records of a raw recording, in order: (t_arrival, kind, cam_ms, packet bytes). A record cut short by a
    power loss at the end of a file is skipped. folder may also be a single raw360_NNNN.bin file.
    """
    for path in raw_files(folder):
        with open(path, "rb") as f:
            if f.read(len(RAW_MAGIC)) != RAW_MAGIC:
                raise ValueError(f"{os.path.basename(path)}: not a NAVERA raw 360 recording")
            while True:
                h = f.read(RAW_RECORD.size)
                if len(h) < RAW_RECORD.size:
                    break
                t, kind, cam_ms, ln = RAW_RECORD.unpack(h)
                p = f.read(ln)
                if len(p) < ln:
                    break
                yield t, kind, cam_ms, p


# ── the IMU feed going silent (F14) ──────────────────────────────────────
IMU_SILENT_S = 1.5               # no IMU packet for this long: the feed is silent
IMU_RESTART_GAP_S = 2.0          # between two actions (the IMU counts as back at imu_age < IMU_SILENT_S)
IMU_WARMUP_S = 4.0               # after opening (or resetting) the camera, before the first action
IMU_RESTARTS_BEFORE_RESET = 3    # StartLiveStream re-sent this many times in vain: reset the USB device


class ImuWatchdog:
    """What a driver does when the camera's IMU feed goes silent while the video goes on (seen on the first
    starts after power-on, F14): re-send StartLiveStream (it usually brings the IMU back); after
    IMU_RESTARTS_BEFORE_RESET restarts in a row that did not, reset the USB device (~8 s after the silence
    began, before the field server's 10 s full reconnect). step() is called about once a second.
    """

    def __init__(self, started: float, silent_s: float = IMU_SILENT_S, gap_s: float = IMU_RESTART_GAP_S,
                 warmup_s: float = IMU_WARMUP_S, restarts_before_reset: int = IMU_RESTARTS_BEFORE_RESET):
        self.started, self.silent_s, self.gap_s, self.warmup_s = started, silent_s, gap_s, warmup_s
        self.restarts_before_reset = restarts_before_reset
        self.failed = 0                 # restarts since the IMU was last heard
        self._last = -1e18

    def step(self, now: float, imu_age: float) -> Optional[str]:
        """None, "restart" (re-send StartLiveStream) or "reset" (reset the USB device, then start again)."""
        if imu_age < self.silent_s:
            self.failed = 0
            return None
        if now - self.started <= self.warmup_s or now - self._last < self.gap_s:
            return None
        self._last = now
        if self.failed >= self.restarts_before_reset:
            self.failed, self.started = 0, now
            return "reset"
        self.failed += 1
        return "restart"

