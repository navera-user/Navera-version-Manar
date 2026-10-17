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
import math
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


def _has_keyframe(p: bytes, start: int) -> bool:
    """True when the H.264 access unit holds an IDR slice (NAL type 5) or a sequence header (7)."""
    i = p.find(b"\x00\x00\x01", start)
    while i >= 0 and i + 3 < len(p):
        if p[i + 3] & 0x1F in (5, 7):
            return True
        i = p.find(b"\x00\x00\x01", i + 3)
    return False


def _rotvec(w):
    t = float(np.linalg.norm(w))
    if t < 1e-12:
        return np.eye(3)
    k = w / t
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


class Insta360Usb:
    """Live full-360 frames and IMU. latest() → (BGR frame, Jetson time it arrived); gravity() → unit
    vector of 'down' in the camera's IMU frame, averaged over the last second, or None while moving."""

    def __init__(self, max_rate_dps: float = 3.0, keyframes_only: bool = True):
        import usb.core
        import usb.util
        self._usb, self._util = usb.core, usb.util
        self.dev = usb.core.find(idVendor=VENDOR)
        if self.dev is None:
            raise RuntimeError("Insta360 not found in USB mode 'Android' (vendor 2e1a)")
        self._util.claim_interface(self.dev, 0)
        self.max_rate = np.radians(max_rate_dps)
        # the decoder is slower than the stream (~18 fps): fed every frame it falls behind and the delay
        # grows; key frames only (one in 15 here, ~2 per second) keep it current
        self.keyframes_only = keyframes_only
        self.acc_bias, self.acc_scale, self.gyro_bias = load_imu_calibration()
        self.error = None
        self._seq = 1
        self._lock = threading.Lock()
        self._frame, self._frame_t = None, 0.0
        self._imu = collections.deque(maxlen=1500)          # 3 s at 500 Hz
        # attitude: gyro integrated (bias-corrected), tilt pulled towards gravity; R maps IMU → reference
        # frame (the camera's frame at start). History by camera ms, the clock frames are stamped with.
        self._R = np.eye(3)
        self._ref_up = None
        self._last_ms = None
        self._att = collections.deque(maxlen=6000)          # (camera ms, R) — 12 s
        self._frame_ms = None
        self._stop = False
        self._buf = bytearray()
        self._dir = tempfile.mkdtemp(prefix="insta360_")
        self._fifo = os.path.join(self._dir, "video.h264")
        os.mkfifo(self._fifo)
        self._video = None
        # key frames: keep the newest two (old ones dropped); every frame: a P frame needs all before it.
        # Measured on the Jetson: every frame decodes at ~8 fps (< the camera's 18: falls behind, errors);
        # key frames only give 2 fresh frames per second, 1.5 s behind the scene (screen flash test)
        self._packets = collections.deque(maxlen=2 if keyframes_only else 64)
        self._packet_ready = threading.Event()
        try:
            import av                                         # packet-by-packet decoding: no decoder backlog
            self._codec = av.CodecContext.create("h264", "r")
            self._codec.thread_type = "SLICE"
            self._codec.thread_count = 4
        except Exception:
            self._codec = None                                # fallback: OpenCV reading a FIFO (adds delay)
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
            if p[3] == KIND_VIDEO:
                if self.keyframes_only and not _has_keyframe(p, 12):
                    continue
                if self._codec is not None:
                    self._packets.append((time.time(), p[12:], struct.unpack_from("<I", p, 4)[0]))
                    self._packet_ready.set()
                    continue
                if self._video is None:
                    continue
                try:
                    self._video.write(p[12:])
                except OSError as e:
                    self.error = f"decoder pipe: {e}"
            elif p[3] == KIND_IMU:
                body = p[12:]
                now = time.time()
                with self._lock:
                    for k in range(0, len(body) - IMU_RECORD.size + 1, IMU_RECORD.size):
                        rec = IMU_RECORD.unpack_from(body, k)
                        self._imu.append((now,) + rec)
                        self._track(rec)
        del b[:i]

    def _decode(self):
        if self._codec is not None:
            return self._decode_av()
        import cv2
        threading.Thread(target=self._open_pipe, daemon=True).start()
        # FFmpeg's frame threads each hold a frame: with 8 threads the picture came 1.2 s late at the full
        # rate and 4.3 s late with key frames only. One thread, no buffering: the frame is out as it arrives.
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                              "threads;1|fflags;nobuffer|flags;low_delay|probesize;100000|analyzeduration;0")
        cap = cv2.VideoCapture(self._fifo, cv2.CAP_FFMPEG)
        while not self._stop:
            ok, f = cap.read()
            if not ok:
                self.error = self.error or "video decoder stopped"
                time.sleep(0.2)
                continue
            with self._lock:
                self._frame, self._frame_t = f, time.time()

    def _decode_av(self):
        """Each key frame is decoded as soon as it arrives (measured on the screen: see view360)."""
        while not self._stop:
            if not self._packet_ready.wait(0.5):
                continue
            self._packet_ready.clear()
            while self._packets:
                t_in, data, cam_ms = self._packets.popleft()
                try:
                    for pkt in self._codec.parse(data):
                        for fr in self._codec.decode(pkt):
                            img = fr.to_ndarray(format="bgr24")
                            with self._lock:
                                self._frame, self._frame_t, self._frame_ms = img, t_in, cam_ms   # arrival; camera clock
                except Exception as e:                    # a damaged packet: skip it, the next key frame resyncs
                    self.error = f"decode: {e}"

    def _track(self, rec):
        """One IMU sample into the attitude (called with the lock held)."""
        ms = rec[0]
        a = (np.array(rec[1:4]) - self.acc_bias) / self.acc_scale
        w = np.array(rec[4:7]) - self.gyro_bias
        if self._ref_up is None:
            # first 2 s, camera still: 'up' = their mean accel (not one noisy sample), and the gyro bias measured
            # again (it moves with temperature: the 6-position value left ~1.5 deg/min about the vertical)
            self._init = getattr(self, "_init", []) + [(a, np.array(rec[4:7]))]
            if len(self._init) < 1000:
                return
            acc = np.array([x[0] for x in self._init])
            gyr = np.array([x[1] for x in self._init])
            if float(np.abs(gyr - gyr.mean(axis=0)).max()) < math.radians(2.0):    # it was still
                self.gyro_bias = gyr.mean(axis=0)
            m = acc.mean(axis=0)
            self._ref_up, self._last_ms = m / np.linalg.norm(m), ms
            self._att.append((ms, self._R.copy()))
            return
        dt = (ms - self._last_ms) / 1000.0
        self._last_ms = ms
        if not 0.0 < dt < 0.1:
            return
        self._R = self._R @ _rotvec(w * dt)
        # still (gyro and accelerometer quiet for 1 s): track the gyro bias, it creeps as the camera warms up
        # (measured 0.017 deg/s in 40 s = 1 deg/min about the vertical, which gravity cannot correct)
        self._still = getattr(self, "_still", collections.deque(maxlen=500))
        self._still.append((np.array(rec[4:7]), a))
        if len(self._still) == 500 and ms % 100 < 3:
            gw = np.array([x[0] for x in self._still])
            ga = np.array([x[1] for x in self._still])
            if float(gw.std(axis=0).max()) < math.radians(0.15) and float(ga.std(axis=0).max()) < 0.004 \
                    and float(np.linalg.norm(gw.mean(axis=0) - self.gyro_bias)) < math.radians(0.3):
                self.gyro_bias = 0.8 * self.gyro_bias + 0.2 * gw.mean(axis=0)
        g = float(np.linalg.norm(a))
        if 0.97 < g < 1.03:                               # not accelerating: pull the tilt towards gravity
            up_pred = self._R.T @ self._ref_up            # where 'up' should be in the IMU frame
            err = np.cross(up_pred, a / g)                # small rotation from predicted to measured
            self._R = self._R @ _rotvec(-0.002 * err)
        u, _, vt = np.linalg.svd(self._R)                 # keep it a rotation
        self._R = u @ vt
        self._att.append((ms, self._R.copy()))

    def attitude_at(self, cam_ms):
        """R (IMU → the camera's frame at start) at camera time cam_ms, or None outside the history."""
        with self._lock:
            hist = list(self._att)
        if not hist or cam_ms is None or cam_ms < hist[0][0] or cam_ms > hist[-1][0] + 200:
            return None
        i = min(range(len(hist)), key=lambda k: abs(hist[k][0] - cam_ms))
        return hist[i][1]

    def latest_stamped(self):
        """(BGR frame, arrival time, camera ms of the frame)."""
        with self._lock:
            return self._frame, self._frame_t, self._frame_ms

    def _open_pipe(self):
        self._video = open(self._fifo, "wb", buffering=0)    # blocks until the decoder opens it

    # ── outputs ─────────────────────────────────────────────────────────
    def latest(self):
        with self._lock:
            return self._frame, self._frame_t

    def stopped(self, window_s: float = 2.0) -> dict:
        """Is the vehicle at rest? Vehicle acceleration tilts the measured 'up' (0.1 g braking or a curve = ~6 deg,
        hundreds of km) without changing |a| enough to notice, so a trusted fix needs the vehicle stopped:
        0.1 s means of the accelerometer steady within 0.003 g (engine vibration averages out) and rotation
        under 0.5 deg/s, over window_s."""
        with self._lock:
            rows = [r for r in self._imu if r[0] >= time.time() - window_s]
        if len(rows) < 400:
            return {"stopped": False, "why": "no sensor data"}
        a = (np.array([r[2:5] for r in rows]) - self.acc_bias) / self.acc_scale
        w = np.array([r[5:8] for r in rows]) - self.gyro_bias
        n = len(a) // 50 * 50
        means = a[:n].reshape(-1, 50, 3).mean(axis=1)                 # 0.1 s blocks
        acc_std = float(means.std(axis=0).max())
        rate = float(np.degrees(np.linalg.norm(w[:n].reshape(-1, 50, 3).mean(axis=1), axis=1)).max())   # 0.1 s means too
        return {"stopped": acc_std < 0.003 and rate < 0.5, "acc_std_g": round(acc_std, 4), "rate_dps": round(rate, 2)}

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
