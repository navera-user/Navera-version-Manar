"""The Insta360 kit: ONE owner of the Insta360 One R in USB Android mode giving both NAVERA's day
camera frames and its IMU / attitude (no BNO085, no autopilot needed). Pure Python, no ROS: the
node (camera_pkg.nodes.insta360_node) and the tests use it.

Per camera packet (live over USB, or replayed from a field raw recording):
  IMU (0x30, 500 Hz)  -> camera_pkg.insta360_imu.ImuStream (host clock, calibration, gyro bias at
                         rest, mount rotation, 100 Hz means) -> AttitudeFilter (roll / pitch from
                         gyro + accelerometer, yaw from the gyro set by the GPS course / vision)
  video (0x20 H.264)  -> key frames only (~2/s: every frame decodes slower than the camera sends
                         them on the Jetson, measured), each decoded ON ITS OWN (a fresh decoder,
                         flushed: 170-250 ms on the Jetson), cut into the body-fixed nadir view
                         (camera_pkg.insta360_view.NadirView), stamped at its EXPOSURE on the host
                         clock: its OWN packet's camera ms - exposure_lag_ms, mapped by the IMU's clock.

Exposure stamp (F15). The field driver's 1.5 s (navera_common.insta360_protocol.FRAME_STAMP_LAG_MS,
measured 2026-10-19 against the dot grid) was measured through a decoder that gives each key frame
out THREE key frames later (the H.264 parser holds one access unit, the decoder two: checked on the
2026-10-20 recording, key frames 500 ms apart): the picture was stamped with a packet 3 x 500 ms
newer, minus 1.5 s. Stamped with its own packet, the same measurement gives an exposure lag of
1500 - 3 x 500 = 0 ms (+-50 ms, the measurement's resolution): KIT_EXPOSURE_LAG_MS. Decoding each key
frame alone also delivers it ~1 s sooner than the field driver did.
"""
import collections
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Tuple

import numpy as np

from navera_common.insta360_protocol import FRAME_STAMP_LAG_MS, KIND_IMU, KIND_VIDEO, read_raw, stream_kind
from camera_pkg.insta360_attitude import AttitudeFilter, AttitudeState
from camera_pkg.insta360_imu import ImuSample, ImuStream
from camera_pkg.insta360_view import NadirView

KEYFRAME_INTERVAL_MS = 500                     # measured: 2 key frames per second
FIELD_DECODER_DELAY_FRAMES = 3                 # parser 1 + decoder 2 (module doc)
KIT_EXPOSURE_LAG_MS = FRAME_STAMP_LAG_MS - FIELD_DECODER_DELAY_FRAMES * KEYFRAME_INTERVAL_MS


BOX_IMU_CALIBRATION = "/var/lib/navera/insta360_imu.json"


def imu_calibration_file(path: str = "") -> str:
    """The IMU calibration in use: path, else NAVERA_INSTA360_IMU, else the box's
    /var/lib/navera/insta360_imu.json when it exists, else the bench file (insta360_protocol)."""
    import os
    from navera_common.insta360_protocol import IMU_CALIBRATION
    for p in (path, os.environ.get("NAVERA_INSTA360_IMU", "")):
        if p:
            return p
    return BOX_IMU_CALIBRATION if os.path.isfile(BOX_IMU_CALIBRATION) else IMU_CALIBRATION


def has_keyframe(p: bytes, start: int = 12) -> bool:
    """True when the H.264 access unit holds an IDR slice (NAL 5) or a sequence header (7)."""
    i = p.find(b"\x00\x00\x01", start)
    while 0 <= i and i + 3 < len(p):
        if p[i + 3] & 0x1F in (5, 7):
            return True
        i = p.find(b"\x00\x00\x01", i + 3)
    return False


@dataclass
class KitFrame:
    t: float                 # exposure, host clock (s)
    cam_ms: float            # exposure, camera clock (ms)
    arrival: float           # when its packet arrived (host s)
    image: np.ndarray        # the nadir view (BGR)
    full_shape: Tuple[int, int]


class Insta360Kit:
    def __init__(self, stream: ImuStream, attitude: AttitudeFilter, view: Optional[NadirView],
                 speed_at: Optional[Callable[[float], Tuple[Optional[float], Optional[float]]]] = None,
                 decoder_factory: Optional[Callable] = None, exposure_lag_ms: float = KIT_EXPOSURE_LAG_MS):
        """speed_at(t) -> (speed m/s, along-track accel m/s^2) or (None, None): the trusted GPS
        track's (camera_pkg.insta360_attitude.GpsCourse.speed). exposure_lag_ms: a key frame's
        packet camera ms minus its exposure (module doc)."""
        self.exposure_lag_ms = float(exposure_lag_ms)
        self.stream, self.attitude, self.view = stream, attitude, view
        self.speed_at = speed_at or (lambda t: (None, None))
        self._decoder_factory = decoder_factory or _pyav_decoder
        self._decoder = None
        self._video = collections.deque(maxlen=2)     # newest key frames waiting for the decoder
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self.video_packets = self.keyframes = self.decoded = self.decode_errors = self.unstamped = 0
        self.last_error: Optional[str] = None

    # ── packets in ────────────────────────────────────────────────────────
    def feed(self, arrival: float, packet: bytes) -> List[Tuple[ImuSample, AttitudeState]]:
        """One camera packet: the new IMU samples with the attitude after each (video packets are
        queued for decode_pending / the decoder thread)."""
        kind, cam_ms = stream_kind(packet)
        if kind == KIND_VIDEO:
            self.video_packets += 1
            if has_keyframe(packet):
                self.keyframes += 1
                self._video.append((arrival, cam_ms, packet[12:]))
                self._ready.set()
            return []
        if kind != KIND_IMU:
            return []
        out = []
        with self._lock:
            for s in self.stream.feed(arrival, packet):
                sp, acc = self.speed_at(s.t)
                st = self.attitude.update(s.t, s.gyro, s.accel, sp, acc)
                if st is not None:
                    out.append((s, st))
        return out

    # ── frames out ────────────────────────────────────────────────────────
    def decode_pending(self) -> List[KitFrame]:
        """Decode the waiting key frames (newest two at most): the nadir views, stamped."""
        out = []
        while self._video:
            arrival, cam_ms, data = self._video.popleft()
            if self._decoder is None:
                self._decoder = self._decoder_factory()
            try:
                images = self._decoder(data)
            except Exception as e:                    # a damaged packet: the next key frame resyncs
                self.decode_errors += 1
                self.last_error = f"decode: {e}"
                continue
            for img in images:
                self.decoded += 1
                exp_ms = float(cam_ms) - self.exposure_lag_ms
                with self._lock:
                    t = self.stream.clock.to_host(exp_ms)
                if t is None:                         # no IMU packet yet: the clock is not known
                    self.unstamped += 1
                    continue
                view = self.view.apply(img) if self.view is not None else img
                out.append(KitFrame(t, exp_ms, arrival, view, img.shape[:2]))
        return out

    def wait_frames(self, timeout: float) -> List[KitFrame]:
        """Block until a key frame arrives (or timeout), then decode_pending()."""
        if self._ready.wait(timeout):
            self._ready.clear()
        return self.decode_pending()


def _pyav_decoder():
    """H.264 key frame (one access unit, SPS + PPS + IDR) -> [its BGR picture]: a fresh decoder per
    key frame, flushed, so the picture comes out of the call that fed it (a long-lived decoder
    gives it 2 calls later, and its parser 1 more: module doc)."""
    import av

    def decode(data: bytes):
        codec = av.CodecContext.create("h264", "r")
        codec.thread_type = "SLICE"
        codec.thread_count = 4
        frames = list(codec.decode(av.Packet(data))) + list(codec.decode(None))
        return [fr.to_ndarray(format="bgr24") for fr in frames]
    return decode


def replay_all(path: str, rate: float = 1.0, clock: str = "now", loop: bool = False,
               stop: Optional[threading.Event] = None, now: Callable[[], float] = time.time,
               sleep: Callable[[float], None] = time.sleep) -> Iterator[Tuple[float, bytes]]:
    """(host arrival, packet) of EVERY packet of a raw recording (camera_pkg.insta360_imu.
    replay_packets gives the IMU only): clock 'now' shifts the recording to start now, 'recorded'
    keeps its times; rate 1 = real time, 0 = as fast as possible (pacing only)."""
    if clock not in ("now", "recorded"):
        raise ValueError(f"replay clock {clock!r}: expected 'now' or 'recorded'")
    while True:
        first = wall0 = shift = None
        for t, kind, _, p in read_raw(path):
            if stop is not None and stop.is_set():
                return
            if first is None:
                first, wall0 = t, now()
                shift = wall0 - t if clock == "now" else 0.0
            if rate > 0:
                wait = wall0 + (t - first) / rate - now()
                if wait > 0:
                    sleep(wait)
            yield t + shift, p
        if not loop or first is None:
            return


def video_packet(cam_ms: int, h264: bytes) -> bytes:
    """A KIND_VIDEO stream packet (as the camera sends it) around an H.264 access unit."""
    return b"\x01\x00\x00" + bytes([KIND_VIDEO]) + struct.pack("<I", int(cam_ms) & 0xFFFFFFFF) + b"\x00" * 4 + h264
