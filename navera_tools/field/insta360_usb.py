#!/usr/bin/env python3
"""Insta360 One R full 360 live stream and its own IMU over USB, without Insta360's SDK.

    python3 -m navera_tools.field.insta360_usb [seconds] [out.jpg]    # grab a frame + gravity

The camera must be in USB mode "Android" (it then enumerates as 2e1a:0002 with one vendor bulk
interface) and the user must be allowed to open it (udev rule MODE="0666" for vendor 2e1a).
It speaks the protocol the Insta360 app uses over Wi-Fi (reverse engineered in
RigacciOrg/insta360-wifi-api): every packet is an int32 little-endian total length + payload.

  sync       06 00 00 "syNceNdinS"          keepalive  05 00 00
  message    04 00 00 <code u16> 02 <seq u24> 80 00 00 <protobuf>
  stream     01 00 00 <kind> <camera ms u32> ...   payload from byte 12
             kind 0x20 H.264 (Annex-B), 0x30 IMU, 0x40 per-frame info, 0x10 other

Asking for two preview streams makes the camera send its full 3840x1920 dual fisheye
(~18 fps, ~30 Mbit/s); one stream is always 1280x640. IMU records (500 Hz) are 56 bytes:
u64 camera ms, accelerometer x y z (g), gyroscope x y z (rad/s), in the camera's own frame.

Measured 2026-10-17 on the user's One R: 3840x1920 decoded at 16 fps on the Jetson (OpenCV
reading a FIFO); camera at rest: |accel| 0.997 g, noise 0.0017 g per sample.
"""
import collections
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time

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
IMU_CALIBRATION = os.environ.get("NAVERA_INSTA360_IMU", os.path.expanduser("~/.navera_sim/insta360_usb_imu.json"))


def load_imu_calibration(path: str = IMU_CALIBRATION):
    """(accel bias g, accel scale, gyro bias rad/s) from a 6-position calibration, or neutral values."""
    try:
        with open(path) as f:
            d = json.load(f)
        return (np.array(d["accel_bias_g"], float), np.array(d["accel_scale"], float),
                np.array(d["gyro_bias_rad_s"], float))
    except (OSError, ValueError, KeyError):
        return np.zeros(3), np.ones(3), np.zeros(3)


class Insta360Usb:
    """Live full-360 frames and IMU. latest() → (BGR frame, Jetson time it arrived); gravity() → unit
    vector of 'down' in the camera's IMU frame, averaged over the last second, or None while moving."""

    def __init__(self, max_rate_dps: float = 3.0):
        import usb.core
        import usb.util
        self._usb, self._util = usb.core, usb.util
        self.dev = usb.core.find(idVendor=VENDOR)
        if self.dev is None:
            raise RuntimeError("Insta360 not found in USB mode 'Android' (vendor 2e1a)")
        self._util.claim_interface(self.dev, 0)
        self.max_rate = np.radians(max_rate_dps)
        self.acc_bias, self.acc_scale, self.gyro_bias = load_imu_calibration()
        self.error = None
        self._seq = 1
        self._lock = threading.Lock()
        self._frame, self._frame_t = None, 0.0
        self._imu = collections.deque(maxlen=1500)          # 3 s at 500 Hz
        self._stop = False
        self._buf = bytearray()
        self._dir = tempfile.mkdtemp(prefix="insta360_")
        self._fifo = os.path.join(self._dir, "video.h264")
        os.mkfifo(self._fifo)
        self._video = None
        self._send(PKT_SYNC)
        self._message(CMD_START_LIVE, START_FULL)
        for target in (self._read_usb, self._keepalive, self._decode):
            threading.Thread(target=target, daemon=True).start()

    # ── protocol ────────────────────────────────────────────────────────
    def _send(self, payload: bytes):
        self.dev.write(EP_OUT, struct.pack("<i", len(payload) + 4) + payload, timeout=1000)

    def _message(self, code: int, body: bytes):
        with self._lock:
            seq, self._seq = self._seq, self._seq + 1
        self._send(b"\x04\x00\x00" + code.to_bytes(2, "little") + b"\x02"
                   + struct.pack("<i", seq)[:3] + b"\x80\x00\x00" + body)

    def _keepalive(self):
        while not self._stop:
            time.sleep(1.0)
            try:
                self._send(PKT_KEEPALIVE)
            except Exception as e:                       # the reader reports the lost camera
                self.error = f"keepalive: {e}"

    def _read_usb(self):
        while not self._stop:
            try:
                self._buf += bytes(self.dev.read(EP_IN, 262144, timeout=500))
            except self._usb.USBTimeoutError:
                continue
            except Exception as e:
                self.error = f"camera lost: {e}"
                time.sleep(0.5)
                continue
            self._parse()

    def _parse(self):
        b = self._buf
        i = 0
        while i + 4 <= len(b):
            n = struct.unpack_from("<i", b, i)[0]
            if n < 4 or n > 8_000_000:                   # out of step: drop what we have
                i = len(b)
                break
            if i + n > len(b):
                break
            p = bytes(b[i + 4:i + n])
            i += n
            if p[:1] != b"\x01" or len(p) < 12:
                continue
            if p[3] == KIND_VIDEO and self._video is not None:
                try:
                    self._video.write(p[12:])
                except OSError as e:
                    self.error = f"decoder pipe: {e}"
            elif p[3] == KIND_IMU:
                body = p[12:]
                now = time.time()
                with self._lock:
                    for k in range(0, len(body) - IMU_RECORD.size + 1, IMU_RECORD.size):
                        self._imu.append((now,) + IMU_RECORD.unpack_from(body, k))
        del b[:i]

    def _decode(self):
        import cv2
        threading.Thread(target=self._open_pipe, daemon=True).start()
        cap = cv2.VideoCapture(self._fifo, cv2.CAP_FFMPEG)
        while not self._stop:
            ok, f = cap.read()
            if not ok:
                self.error = self.error or "video decoder stopped"
                time.sleep(0.2)
                continue
            with self._lock:
                self._frame, self._frame_t = f, time.time()

    def _open_pipe(self):
        self._video = open(self._fifo, "wb", buffering=0)    # blocks until the decoder opens it

    # ── outputs ─────────────────────────────────────────────────────────
    def latest(self):
        with self._lock:
            return self._frame, self._frame_t

    def gravity(self, window_s: float = 1.0):
        """(unit 'down' vector in the IMU frame, accel norm g, max rotation rad/s) over the last window,
        or (None, ...) when the camera turned faster than max_rate_dps (the accelerometer then sees more than gravity)."""
        with self._lock:
            rows = [r for r in self._imu if r[0] >= time.time() - window_s]
        if len(rows) < 50:
            return None, None, None
        a = (np.array([r[2:5] for r in rows]) - self.acc_bias) / self.acc_scale
        w = np.array([r[5:8] for r in rows]) - self.gyro_bias
        rate = float(np.linalg.norm(w, axis=1).max())
        m = a.mean(axis=0)
        g = float(np.linalg.norm(m))
        if rate > self.max_rate or not 0.95 < g < 1.05:
            return None, g, rate
        return m / g, g, rate

    def close(self):
        try:
            self._message(CMD_STOP_LIVE, b"")
        except Exception:
            pass
        self._stop = True
        time.sleep(0.8)                                  # the reader's 0.5 s timeout lets it leave the USB read
        try:
            self._util.release_interface(self.dev, 0)
        except Exception:
            pass
        try:
            self._util.dispose_resources(self.dev)       # without this a new instance gets "Resource busy"
        except Exception:
            pass
        shutil.rmtree(self._dir, ignore_errors=True)


def main():
    import cv2
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    out = sys.argv[2] if len(sys.argv) > 2 else None
    cam = Insta360Usb()
    time.sleep(secs)
    f, t = cam.latest()
    down, g, rate = cam.gravity()
    print("frame:", None if f is None else f.shape, f"{time.time() - t:.1f}s old" if f is not None else "",
          "| gravity (camera IMU frame):", None if down is None else np.round(down, 4),
          f"| |a| {g:.4f} g, max rotation {np.degrees(rate):.2f} deg/s" if g else "", "| error:", cam.error)
    if out and f is not None:
        cv2.imwrite(out, f)
    cam.close()
    os._exit(0)                                          # the blocked decoder thread must not hold the exit


if __name__ == "__main__":
    main()
