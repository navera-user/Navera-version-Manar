"""Field Insta360 driver (F14 follow-ups): 20 s of IMU history, the public IMU-history reader, and the USB reset
after 3 stream restarts in vain; the field server waits for that reset before reopening the camera. Fake USB, no
camera (the real one is held by navera-field)."""
import collections
import threading
import time

import numpy as np

from navera_tools.field import insta360_usb as iu
from navera_tools.field import server as srv
from navera_common import insta360_protocol as proto


class FakeUsb:
    """usb.core and usb.util at once, and the device."""

    def __init__(self):
        self.written, self.resets, self.claimed = [], 0, 0

    def find(self, idVendor):
        return self

    def claim_interface(self, dev, n):
        self.claimed += 1

    def release_interface(self, dev, n):
        pass

    def dispose_resources(self, dev):
        pass

    def reset(self):
        self.resets += 1

    def write(self, ep, data, timeout):
        self.written.append(data)


def _driver():
    d = iu.Insta360Usb.__new__(iu.Insta360Usb)
    d._init_state(3.0, True)
    fake = FakeUsb()
    d.dev, d._usb, d._util = fake, fake, fake
    return d, fake


def test_the_driver_keeps_20_s_of_imu_and_reads_it_publicly():
    d, _ = _driver()
    assert d._imu.maxlen == int(iu.IMU_HISTORY_S * proto.IMU_HZ) == 10_000
    for k in range(12_000):                                 # 24 s at 500 Hz
        d._imu.append((time.time(), k * 2.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0))
    rows = d.imu_rows(19.0, at_ms=23_000.0, after_s=0.5)
    assert len(rows) == 9751 and rows[0][1] == 4000.0 and rows[-1][1] == 23_500.0
    assert len(d.imu_rows(30.0, at_ms=23_000.0)) == 9501      # what is older than 20 s is gone


def test_silent_imu_restarts_three_times_then_resets_the_usb_device():
    d, fake = _driver()
    t0 = d._started
    start = proto.frame_packet(proto.message_payload(proto.CMD_START_LIVE, 1, proto.START_FULL))
    for k in range(1, 13):                                  # never an IMU packet: 12 s of silence
        d._keepalive_once(t0 + k)
    assert d.imu_restarts == 3 and d.usb_resets == 1 and fake.resets == 1 and fake.claimed == 1
    assert start in fake.written and proto.frame_packet(proto.PKT_SYNC) in fake.written
    assert "USB device reset" in d.error and abs(d.last_reset_t - (t0 + 11)) < 1e-9


class _Cam:
    def __init__(self, reset_ago):
        self.last_reset_t, self.usb_resets, self.imu_restarts = time.time() - reset_ago, 1, 3
        self.error, self.closed = None, False
        self._lock = threading.Lock()
        self._imu = collections.deque(maxlen=10)

    def latest(self):
        return np.zeros((4, 4), np.uint8), time.time()

    def imu_age(self):
        return 12.0

    def close(self):
        self.closed = True


def test_the_server_waits_for_the_drivers_usb_reset_before_reopening(monkeypatch):
    cam = srv.Camera360.__new__(srv.Camera360)
    mod = type("M", (), {"Insta360Usb": lambda: _Cam(30.0), "IMU_CALIBRATION": "none", "RawRecorder": None})
    cam._mod, cam.cal_path, cam.raw, cam.frame_ms = mod, "none", None, None
    cam.stillness, cam.reconnects, cam.imu_restarts_total = srv.Stillness(), [], 0
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    cam.cam, cam.opened_at = _Cam(2.0), time.time() - 30.0  # reset 2 s ago: give it time
    assert cam._watch_once() is None
    cam.cam.last_reset_t -= 10.0                            # the reset did not help either
    assert cam._watch_once() == "camera IMU silent for 10 s"
    assert cam.health()["usb_resets"] == 2                  # 1 of the closed driver + 1 of the new one
