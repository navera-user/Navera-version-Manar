"""Field server: the stopped test is the camera driver's window AND the long-window test (D8/D12); the camera
stream is reopened when its IMU stays silent (F14); every 360 frame record carries the drive measurements (F19).
Fake camera driver, synthetic 500 Hz IMU (no hardware)."""
import collections
import math
import threading
import time

import numpy as np

from navera_tools.field import insta360_usb
from navera_tools.field import server as srv

HZ = 500


def _driver(phases):
    """A real Insta360Usb driver object (no USB) holding synthetic IMU rows: phases [(s, horizontal accel g)]."""
    d = insta360_usb.Insta360Usb.__new__(insta360_usb.Insta360Usb)
    d._lock = threading.Lock()
    d._imu = collections.deque(maxlen=3500)                     # the driver's own 7 s
    d.acc_bias, d.acc_scale, d.gyro_bias = np.zeros(3), np.ones(3), np.zeros(3)
    d.max_rate = math.radians(3.0)
    d._imu_t = time.time()
    d.error = None
    srv.Stillness.extend_history(d)
    rng = np.random.default_rng(0)
    t0 = 0.0
    for dur, h in phases:
        for k in range(int(dur * HZ)):
            ms = (t0 + k / HZ) * 1000.0
            a = np.array([1.0, h, 0.0]) + rng.normal(0, 0.0005, 3)
            w = rng.normal(0, math.radians(0.05), 3)
            d._imu.append((time.time(), ms, *a, *w))
        t0 += dur
    return d


def test_history_is_extended_for_the_long_window():
    d = _driver([(1, 0.0)])
    assert d._imu.maxlen >= srv.Stillness.HISTORY_S * 500


def test_gentle_acceleration_on_a_smooth_road_is_not_stopped():
    d = _driver([(12, 0.0), (8, 0.03)])
    exp_ms = 19000.0
    assert d.stopped(at_ms=exp_ms)["stopped"]                   # the driver alone is fooled
    st = srv.Stillness().judge(d, exp_ms)
    assert not st["stopped"] and "gentle" in st["why"] and st["driver_stopped"]


def test_stop_after_braking_is_stopped():
    d = _driver([(8, 0.0), (4, -0.15), (6, 0.0)])
    st = srv.Stillness().judge(d, 16500.0)
    assert st["stopped"], st


def test_long_check_can_be_switched_off_live():
    d = _driver([(12, 0.0), (8, 0.03)])
    old = srv.Stillness.LONG_CHECK
    try:
        srv.Stillness.LONG_CHECK = 0
        assert srv.Stillness().judge(d, 19000.0)["stopped"]
    finally:
        srv.Stillness.LONG_CHECK = old


class _Cam:
    """Stands in for insta360_usb.Insta360Usb in Camera360 (F14): frames arrive, the IMU may be silent."""
    made = 0

    def __init__(self):
        type(self).made += 1
        self.imu_silent_since = time.time() - 30.0
        self.imu_restarts = 4
        self.error = None
        self.closed = False
        self._lock = threading.Lock()
        self._imu = collections.deque(maxlen=10)

    def latest(self):
        return np.zeros((4, 4), np.uint8), time.time()

    def imu_age(self):
        return time.time() - self.imu_silent_since

    def close(self):
        self.closed = True


def test_silent_imu_reopens_the_camera_and_is_counted(monkeypatch):
    mod = type("M", (), {"Insta360Usb": _Cam, "IMU_CALIBRATION": "none", "RawRecorder": None})
    cam = srv.Camera360.__new__(srv.Camera360)
    cam._mod, cam.cal_path, cam.raw, cam.frame_ms = mod, "none", None, None
    cam.stillness, cam.reconnects, cam.imu_restarts_total = srv.Stillness(), [], 0
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    cam._open()
    first = cam.cam
    cam.opened_at -= 30.0
    assert cam._watch_once() == "camera IMU silent for 10 s"
    assert first.closed and cam.cam is not first
    h = cam.health()
    assert h["reconnects"] == 1 and h["imu_restarts"] == 8          # 4 before the reconnect + 4 of the new driver
    cam.cam.imu_silent_since = time.time()                          # IMU back
    cam.opened_at -= 30.0
    assert cam._watch_once() is None


def test_host_stats_and_vibration_stats_are_plain_numbers():
    h = srv.host_stats()
    assert all(isinstance(v, (int, float)) for v in h.values())
    from cn_pkg import standstill
    rng = np.random.default_rng(1)
    a = np.array([1.0, 0, 0]) + rng.normal(0, 0.01, (1250, 3))
    v = standstill.vibration_stats(a, rng.normal(0, 0.01, (1250, 3)))
    assert 0.012 < v["acc_hp_rms_g"] < 0.02 and v["n"] == 1250


def test_report_sums_up_the_drive_measurements():
    """F19: analyze.drive_measurements counts stops, trusted fixes per stop, the stopped flag against the phone's
    speed (incl. what the long window refused), vibration, solve times on a quiet Jetson, time sources."""
    from navera_tools.field import analyze
    phone = [{"t": float(t), "speed": 0.0 if (t < 20 or 60 <= t < 80) else 12.0} for t in range(0, 100)]
    frames = []
    for t in range(2, 100, 4):
        still = t < 20 or 60 <= t < 80
        frames.append({"t": t + 2.0, "t_exp": float(t), "mode": "360", "stopped": still and t != 66,
                       "solved": still, "solve_s": 2.0, "host": {"load1": 1.0 if t < 50 else 5.0, "temp_c": 50.0},
                       "imu_vib": {"acc_hp_rms_g": 0.01 if still else 0.05, "gyro_rms_dps": 0.1},
                       "stillness": {"driver_stopped": True} if t == 66 else {},
                       "time_source": "phone", "rtc_minus_phone_s": 0.4, "cam_health": {"reconnects": 1, "imu_restarts": 2}})
    frames.append({"t": 31.0, "t_exp": 30.0, "mode": "360", "stopped": True, "solved": False})   # fooled while driving
    dm = analyze.drive_measurements(frames, phone, [])
    assert len(dm["stops"]) == 2 and [s["fixes_trusted"] for s in dm["stops"]] == [5, 4]
    assert dm["stopped_flag_vs_phone"]["stopped_flag_while_moving"] == 1
    assert dm["stopped_flag_vs_phone"]["driver_said_stopped_long_window_refused"] == 1
    assert dm["vibration"]["rest_acc_hp_rms_g"]["median"] == 0.01
    assert dm["solve_s"]["quiet_jetson_load_lt_2"]["n"] < dm["solve_s"]["all"]["n"]
    assert dm["time_source"] == {"phone": 25} and dm["camera"]["reconnects"] == 1
