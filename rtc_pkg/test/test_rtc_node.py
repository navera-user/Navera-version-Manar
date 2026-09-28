"""RTC driver behaviour with a simulated DS3231 (no hardware, no Adafruit stack)."""
import json
import sys
import time
import types

import pytest
import rclpy


class FakeDS3231:
    offset_s = 0.0          # RTC - system
    lost = False
    fail_lost_power = False

    def __init__(self, i2c):
        pass

    @property
    def datetime(self):
        return time.gmtime(time.time() + FakeDS3231.offset_s)

    @property
    def lost_power(self):
        if FakeDS3231.fail_lost_power:
            raise OSError("I2C transfer failed")
        return FakeDS3231.lost

    @property
    def temperature(self):
        return 25.0


@pytest.fixture(scope="module")
def rtc_module():
    board = types.ModuleType("board")
    board.SCL_1 = board.SDA_1 = board.SCL = board.SDA = object()
    busio = types.ModuleType("busio")
    busio.I2C = lambda scl, sda: object()
    ds = types.ModuleType("adafruit_ds3231")
    ds.DS3231 = FakeDS3231
    sys.modules.update({"board": board, "busio": busio, "adafruit_ds3231": ds})
    from rtc_pkg.nodes import rtc_node
    rclpy.init()
    yield rtc_node
    rclpy.shutdown()


def _status_after_one_read(rtc_module, offset_s, lost=False):
    FakeDS3231.offset_s, FakeDS3231.lost = offset_s, lost
    node = rtc_module.RTCNode()
    statuses, times = [], []
    node.pub_status.publish = lambda m: statuses.append(json.loads(m.data))
    node.pub_time.publish = times.append
    try:
        node.publish_rtc()
    finally:
        node.destroy_node()
    return statuses[-1], times


def test_utc_rtc_is_valid(rtc_module):
    st, times = _status_after_one_read(rtc_module, 0.0)
    assert st["valid"] and st["reason"] == "" and len(times) == 1


@pytest.mark.parametrize("hours", [1, -2])
def test_rtc_in_local_time_is_invalid(rtc_module, hours):
    st, times = _status_after_one_read(rtc_module, hours * 3600.0)
    assert not st["valid"] and "local time" in st["reason"] and times == []


def test_large_non_hour_drift_is_not_mistaken_for_local_time(rtc_module):
    st, _ = _status_after_one_read(rtc_module, 1800.0)
    assert st["valid"]


def test_lost_power_is_invalid(rtc_module):
    st, times = _status_after_one_read(rtc_module, 0.0, lost=True)
    assert not st["valid"] and "lost power" in st["reason"] and times == []


def test_transient_error_during_connect_does_not_crash(rtc_module):
    FakeDS3231.fail_lost_power = True
    try:
        node = rtc_module.RTCNode()          # used to raise out of __init__
        assert node.rtc is None
        node.destroy_node()
    finally:
        FakeDS3231.fail_lost_power = False
