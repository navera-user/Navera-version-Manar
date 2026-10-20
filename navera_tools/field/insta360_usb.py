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
import math
import os
import shutil
import struct
import sys
import tempfile
import threading
import time

import numpy as np

# the protocol, the IMU record and the raw recording format are shared with the flight camera package
# (camera_pkg.insta360_imu publishes this IMU as sensor_msgs/Imu): one definition, in navera_common
_COMMON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "navera_common")
if _COMMON not in sys.path:
    sys.path.insert(0, _COMMON)
from navera_common.insta360_protocol import (  # noqa: E402,F401
    CMD_START_LIVE, CMD_STOP_LIVE, EP_IN, EP_IN2, EP_OUT, FRAME_STAMP_LAG_MS, IMU_CALIBRATION, IMU_HZ, IMU_RECORD,
    KIND_FRAME, KIND_IMU, KIND_VIDEO, PKT_KEEPALIVE, PKT_SYNC, RAW_MAGIC, RAW_RECORD, START_FULL, VENDOR,
    frame_packet, imu_records, load_imu_calibration, message_payload, read_raw, split_packets)
# stillness: means over 0.2 s blocks. 0.1 s blocks left 4-cylinder idle vibration (0.05 g at 27 Hz) in the means and
# called a parked car moving in 80% of its frames (simulated, navera_tools/sim/car360_drive.py); 0.5 s blocks average
# out the 1-2 Hz body bounce too and called gently accelerating cars stopped
STILL_BLOCK_S = 0.2
STILL_WINDOW_S = 2.0         # stopped(): the vehicle at rest over this long ...
STILL_ACC_STD_G = 0.003      # ... with the STILL_BLOCK_S accelerometer means steady within this
STILL_RATE_DPS = 0.5         # ... and turning slower than this
IMU_COVERAGE = 0.9           # fraction of the stillness window the IMU rows must cover


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


RAW_ROTATE_BYTES = 1 << 30


class RawRecorder:
    """Every packet the camera sends (all video frames, IMU, the rest), as it arrived, to raw360_NNNN.bin files
    in a folder: a one-time test can then be replayed and re-analysed offline with any change (replay360.py).

    File: RAW_MAGIC, then records RAW_RECORD + the whole packet (its 12-byte stream header included). kind is the
    stream kind byte (0x20 video, 0x30 IMU, 0x40 frame info, 0x10 other) or 0 for a non-stream packet; cam_ms the
    packet header's camera ms (0 for non-stream). A writer thread does the disk work, so the USB reader never waits
    on the disk; when the queue holds more than max_queue_bytes the packet is dropped and counted. Files rotate at
    rotate_bytes; numbering goes on after the files already in the folder (a resumed test does not overwrite)."""

    def __init__(self, folder: str, rotate_bytes: int = RAW_ROTATE_BYTES, max_queue_bytes: int = 192 << 20):
        os.makedirs(folder, exist_ok=True)
        self.folder, self.rotate_bytes, self.max_queue_bytes = folder, rotate_bytes, max_queue_bytes
        done = [n for n in os.listdir(folder) if n.startswith("raw360_") and n.endswith(".bin")]
        self._n = max([int(n[7:11]) for n in done if n[7:11].isdigit()] or [-1]) + 1
        self._q = collections.deque()
        self._cv = threading.Condition()
        self.queue_bytes = self.bytes = self.records = self.drops = self.drop_bytes = 0
        self.files: list = []
        self.error = None
        self._f, self._fbytes, self._closed = None, 0, False
        self._thread = threading.Thread(target=self._writer, daemon=True)
        self._thread.start()

    def put(self, t: float, p: bytes):
        """Queue one packet (called by the USB reader: never blocks on the disk)."""
        stream = p[:1] == b"\x01" and len(p) >= 12
        kind = p[3] if stream else 0
        cam_ms = struct.unpack_from("<I", p, 4)[0] if stream else 0
        with self._cv:
            if self._closed:
                return
            if self.queue_bytes + len(p) > self.max_queue_bytes:
                self.drops += 1
                self.drop_bytes += len(p)
                return
            self._q.append((t, kind, cam_ms, p))
            self.queue_bytes += len(p)
            self._cv.notify()

    def _open_next(self):
        if self._f is not None:
            self._f.close()
        path = os.path.join(self.folder, f"raw360_{self._n:04d}.bin")
        self._n += 1
        self._f = open(path, "wb")
        self._f.write(RAW_MAGIC)
        self._fbytes = len(RAW_MAGIC)
        self.files.append(os.path.basename(path))

    def _writer(self):
        last_flush = time.time()
        while True:
            with self._cv:
                while not self._q and not self._closed:
                    self._cv.wait(0.5)
                    if time.time() - last_flush > 1.0:
                        break
                batch = list(self._q)
                self._q.clear()
                self.queue_bytes = 0
                closed = self._closed
            try:
                for t, kind, cam_ms, p in batch:
                    if self._f is None or self._fbytes >= self.rotate_bytes:
                        self._open_next()
                    self._f.write(RAW_RECORD.pack(t, kind, cam_ms, len(p)))
                    self._f.write(p)
                    self._fbytes += RAW_RECORD.size + len(p)
                    self.bytes += RAW_RECORD.size + len(p)
                    self.records += 1
                if self._f is not None and (time.time() - last_flush > 1.0 or closed):
                    self._f.flush()
                    last_flush = time.time()
            except OSError as e:                         # disk full or gone: keep counting what is lost
                self.error = f"raw recording: {e}"
                with self._cv:
                    self.drops += len(batch)
            if closed:
                if self._f is not None:
                    self._f.close()
                    self._f = None
                return

    def stats(self) -> dict:
        return {"folder": self.folder, "files": list(self.files), "mb": round(self.bytes / 1e6, 1), "records": self.records,
                "drops": self.drops, "drop_mb": round(self.drop_bytes / 1e6, 1), "queue_mb": round(self.queue_bytes / 1e6, 1),
                "error": self.error}

    def close(self) -> dict:
        """Write what is queued, close the file; the final stats."""
        with self._cv:
            self._closed = True
            self._cv.notify()
        self._thread.join(timeout=60)
        return self.stats()


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
        self._init_state(max_rate_dps, keyframes_only)
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

    def _init_state(self, max_rate_dps: float, keyframes_only: bool):
        """Everything but the USB device, its threads and the decoder (replay360 builds the driver from this)."""
        self.max_rate = np.radians(max_rate_dps)
        # the decoder is slower than the stream (~18 fps): fed every frame it falls behind and the delay
        # grows; key frames only (one in 15 here, ~2 per second) keep it current
        self.keyframes_only = keyframes_only
        self.acc_bias, self.acc_scale, self.gyro_bias = load_imu_calibration()
        self.error = None
        self._seq = 1
        self._lock = threading.Lock()
        self._frame, self._frame_t = None, 0.0
        self._imu = collections.deque(maxlen=3500)          # 7 s at 500 Hz: the newest frame's exposure is ~1.7 s back
        # attitude: gyro integrated (bias-corrected), tilt pulled towards gravity; R maps IMU → reference
        # frame (the camera's frame at start). History by camera ms, the clock frames are stamped with.
        self._R = np.eye(3)
        self._ref_up = None
        self._last_ms = None
        self._att = collections.deque(maxlen=6000)          # (camera ms, R) — 12 s
        self._frame_ms = None
        # the IMU feed sometimes stops after its first packet while the video goes on (seen 2026-10-19 on the
        # first starts after power-on): the keepalive restarts the stream when the IMU goes quiet
        self._started, self._imu_t, self.imu_restarts = time.time(), 0.0, 0
        self._stop = False
        self.recorder = None                                # RawRecorder: every packet to disk (record())
        self.stack_ring = None                              # stack.StackRing: recent key frames while stacking is on
        self._buf = bytearray()

    # ── protocol ────────────────────────────────────────────────────────
    def _send(self, payload: bytes):
        self.dev.write(EP_OUT, frame_packet(payload), timeout=1000)

    def _message(self, code: int, body: bytes):
        with self._lock:
            seq, self._seq = self._seq, self._seq + 1
        self._send(message_payload(code, seq, body))

    def _keepalive(self):
        last_restart = 0.0
        while not self._stop:
            time.sleep(1.0)
            try:
                self._send(PKT_KEEPALIVE)
                now = time.time()
                if now - self._started > 4.0 and self.imu_age() > 1.5 and now - last_restart > 3.0:
                    self._message(CMD_START_LIVE, START_FULL)   # asking again brings the IMU back
                    last_restart, self.imu_restarts = now, self.imu_restarts + 1
                    self.error = f"camera IMU silent: stream restarted ({self.imu_restarts})"
                elif self.imu_age() < 1.0 and (self.error or "").startswith("camera IMU silent"):
                    self.error = None
            except Exception as e:                       # the reader reports the lost camera
                self.error = f"keepalive: {e}"

    def imu_age(self) -> float:
        """Seconds since the last IMU packet (inf before the first)."""
        return time.time() - self._imu_t if self._imu_t else float("inf")

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
        for p in split_packets(self._buf):               # out of step: what was buffered is dropped
            self._packet(p, time.time())

    def _packet(self, p: bytes, now: float):
        """One packet from the camera, arrived at Jetson time now (replay360 feeds recorded ones here)."""
        rec = self.recorder
        if rec is not None:
            rec.put(now, p)                                 # every packet, before any filtering
        if p[:1] != b"\x01" or len(p) < 12:
            return
        if p[3] == KIND_VIDEO:
            if self.keyframes_only and not _has_keyframe(p, 12):
                return
            self._on_video(now, p[12:], struct.unpack_from("<I", p, 4)[0])
        elif p[3] == KIND_IMU:
            self._imu_t = now
            with self._lock:
                for r in imu_records(p):
                    self._imu.append((now,) + r)
                    self._track(r)

    def _on_video(self, now: float, data: bytes, cam_ms: int):
        if self._codec is not None:
            self._packets.append((now, data, cam_ms))
            self._packet_ready.set()
            return
        if self._video is None:
            return
        try:
            self._video.write(data)
        except OSError as e:
            self.error = f"decoder pipe: {e}"

    def record(self, folder_or_recorder):
        """Start writing every packet to disk (a folder, or a RawRecorder shared across reconnects)."""
        r = folder_or_recorder
        self.recorder = r if isinstance(r, RawRecorder) else RawRecorder(r)
        return self.recorder

    def stop_record(self) -> dict:
        """Stop recording; the recorder's final stats ({} when not recording)."""
        r, self.recorder = self.recorder, None
        return r.close() if r is not None else {}

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
                                # arrival (Jetson clock); exposure on the camera/IMU clock
                                self._frame, self._frame_t, self._frame_ms = img, t_in, cam_ms - FRAME_STAMP_LAG_MS
                            self._keep_for_stack(img, cam_ms - FRAME_STAMP_LAG_MS)
                except Exception as e:                    # a damaged packet: skip it, the next key frame resyncs
                    self.error = f"decode: {e}"

    def _keep_for_stack(self, img, ms):
        """A decoded key frame into the stacking ring (grey), when the server has one (stack.py)."""
        ring = self.stack_ring
        if ring is not None:
            import cv2
            ring.keep(ms, cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img)

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
        """(BGR frame, arrival time, camera-clock ms of its exposure: the clock attitude_at() and the IMU use)."""
        with self._lock:
            return self._frame, self._frame_t, self._frame_ms

    def _open_pipe(self):
        self._video = open(self._fifo, "wb", buffering=0)    # blocks until the decoder opens it

    # ── outputs ─────────────────────────────────────────────────────────
    def latest(self):
        with self._lock:
            return self._frame, self._frame_t

    def _rows(self, window_s, at_ms, after_s=0.0):
        """IMU rows over window_s ending at camera ms at_ms (+ after_s), or ending now when at_ms is None."""
        with self._lock:
            if at_ms is None:
                return [r for r in self._imu if r[0] >= time.time() - window_s]
            return [r for r in self._imu if at_ms - 1000.0 * window_s <= r[1] <= at_ms + 1000.0 * after_s]

    def stopped(self, window_s: "float | None" = None, at_ms=None) -> dict:
        """Is the vehicle at rest? Vehicle acceleration tilts the measured 'up' (0.1 g braking or a curve = ~6 deg,
        hundreds of km) without changing |a| enough to notice, so a trusted fix needs the vehicle stopped:
        STILL_BLOCK_S means of the accelerometer steady within 0.003 g and rotation under 0.5 deg/s, over window_s.
        at_ms: judge the moment of a frame's exposure (latest_stamped()), with 0.5 s after it too (the frame arrives
        ~1.7 s late: 'now' would judge the wrong moment, e.g. a frame taken while braking judged on the stop that
        followed). The window must be covered (IMU_COVERAGE): after a silence of the IMU feed the stillness of the
        missing part is unknown, so it is not called stopped."""
        window_s = STILL_WINDOW_S if window_s is None else window_s
        rows = self._rows(window_s, at_ms, 0.5)
        span = window_s + (0.5 if at_ms is not None else 0.0)
        if len(rows) < IMU_COVERAGE * IMU_HZ * span:
            return {"stopped": False, "why": "no sensor data" if len(rows) < 50 else
                    f"sensor data cover {len(rows) / (IMU_HZ * span):.0%} of the window"}
        a = (np.array([r[2:5] for r in rows]) - self.acc_bias) / self.acc_scale
        w = np.array([r[5:8] for r in rows]) - self.gyro_bias
        b = int(round(STILL_BLOCK_S * IMU_HZ))
        n = len(a) // b * b
        means = a[:n].reshape(-1, b, 3).mean(axis=1)
        acc_std = float(means.std(axis=0).max())
        rate = float(np.degrees(np.linalg.norm(w[:n].reshape(-1, b, 3).mean(axis=1), axis=1)).max())
        return {"stopped": acc_std < STILL_ACC_STD_G and rate < STILL_RATE_DPS, "acc_std_g": round(acc_std, 4),
                "rate_dps": round(rate, 2)}

    def gravity(self, window_s: float = 1.0, at_ms=None):
        """(unit 'up' vector in the IMU frame (the accelerometer at rest reads +1 g upwards), accel norm g, max rotation rad/s) over the last window,
        or (None, ...) when the camera turned faster than max_rate_dps (the accelerometer then sees more than gravity).
        at_ms: the window centred on a frame's exposure (camera ms, latest_stamped()) instead of the last one."""
        rows = self._rows(window_s / 2, at_ms, window_s / 2) if at_ms is not None else self._rows(window_s, None)
        if len(rows) < 50:
            return None, None, None
        a = (np.array([r[2:5] for r in rows]) - self.acc_bias) / self.acc_scale
        w = np.array([r[5:8] for r in rows]) - self.gyro_bias
        b = 50 if len(w) >= 50 else 1                      # 0.1 s means: mount jitter at 10-30 Hz does not turn 'up'
        n = len(w) // b * b
        rate = float(np.linalg.norm(w[:n].reshape(-1, b, 3).mean(axis=1), axis=1).max())
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
