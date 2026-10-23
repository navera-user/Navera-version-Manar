"""F27: the DS3231 battery clock as the field server's trusted star time, with a fake RTC (no hardware).

Order of trust for a star solve (the product's, navera_common.trusted_time): NAVERA's GPS anchor, the autopilot's
SYSTEM_TIME, a valid DS3231, the phone's clock, an NTP-synchronised Jetson; none of them -> no solve. A DS3231 that lost power, is unset (year 2000) or holds local
time is refused; a system clock step withdraws the reading until the next one.
"""
import collections
import threading
import time

from navera_tools.field import rtc_clock
from navera_tools.field import server as srv


class FakeClocks:
    def __init__(self):
        self.w, self.m = 1_800_000_000.0, 1000.0

    def wall(self):
        return self.w

    def mono(self):
        return self.m


def _rtc(off=7200.0, lost=False, year_2000=False, fail=False, clocks=None):
    c = clocks or FakeClocks()

    def reader():
        if fail:
            raise OSError("[Errno 121] Remote I/O error")
        rtc = 946684800.0 if year_2000 else c.w + off
        return rtc, c.w, lost
    return rtc_clock.RtcClock(reader=reader, wall=c.wall, mono=c.mono), c


def test_decode_bcd_registers():
    regs = bytes([0x30, 0x59, 0x23, 0x05, 0x31, 0x10, 0x26])         # 2026-10-31 23:59:30
    assert rtc_clock.decode(regs).strftime("%Y-%m-%d %H:%M:%S") == "2026-10-31 23:59:30"
    assert rtc_clock.decode(bytes([0x00, 0x00, 0x72, 0, 0x01, 0x01, 0x26])).hour == 12   # 12 h mode, 12 PM
    assert rtc_clock.decode(bytes([0x00, 0x00, 0x52, 0, 0x01, 0x01, 0x26])).hour == 0    # 12 AM
    assert rtc_clock.decode(bytes([0x00, 0x00, 0x00, 0, 0x45, 0x13, 0x26])) is None      # month 13


def test_valid_rtc_gives_its_offset():
    r, _ = _rtc(off=57600.4)                          # the Jetson booted 16 h behind (2026-10-21)
    assert r.read()["ok"]
    off, src = r.offset()
    assert abs(off - 57600.4) < 1e-6 and src.startswith("rtc")


def test_lost_power_unset_and_local_time_are_refused():
    for kw, word in (({"lost": True}, "lost power"), ({"year_2000": True}, "not set"), ({"off": 3600.2}, "local time"),
                     ({"fail": True}, "no DS3231")):
        r, _ = _rtc(**kw)
        st = r.read()
        assert not st["ok"] and word in st["why"], (kw, st)
        assert r.offset()[0] is None


def test_clock_step_withdraws_the_reading_and_old_readings_expire():
    r, c = _rtc(off=5.0)
    r.read()
    c.w += 3600.0                                     # NTP stepped the system clock
    off, why = r.offset()
    assert off is None and "stepped" in why
    r.read()                                          # a fresh reading after the step vouches again
    assert r.offset()[0] is not None
    c.m += rtc_clock.MAX_AGE_S + 1
    c.w += rtc_clock.MAX_AGE_S + 1
    assert r.offset()[0] is None


def _field(rtc=None, ntp=False):
    s = srv.Field.__new__(srv.Field)
    s.lock = threading.Lock()
    s.offsets = collections.deque(maxlen=60)
    s._wall_minus_mono = time.time() - time.monotonic()
    s._ntp_checked, s._ntp_synced = time.monotonic(), ntp
    s.session = None
    s.rtc = rtc
    s.phone, s.phone_recv = {}, 0.0
    return s


def test_server_trusts_the_rtc_without_phone_or_internet():
    r, _ = _rtc(off=-120.0)                           # the DS3231 says the Jetson is 2 min ahead
    r.read()
    s = _field(r)
    off, src = s.star_time()
    assert src == "rtc" and abs(off - 120.0) < 1e-6   # offset to SUBTRACT from the Jetson time
    assert abs(s.star_clock_offset_s() - off) < 1e-6


def test_server_prefers_the_rtc_to_the_phone_and_logs_the_rtc_error():
    r, _ = _rtc(off=-120.0)
    r.read()
    s = _field(r)
    s.offsets.extend([120.4, 120.3, 120.5])           # Jetson - phone
    off, src = s.star_time()
    assert src == "rtc" and abs(off - 120.0) < 1e-3
    assert abs(s.rtc_minus_phone_s() - 0.4) < 1e-6    # the DS3231 runs 0.4 s ahead of the phone
    s.rtc = None
    off, src = s.star_time()
    assert src == "phone" and abs(off - 120.4) < 1e-3


def test_server_without_any_trusted_time_does_not_solve():
    r, _ = _rtc(lost=True)
    r.read()
    off, why = _field(r).star_time()
    assert off is None and "lost power" in why
    off, src = _field(r, ntp=True).star_time()
    assert off == 0.0 and src == "ntp"
    assert _field(None).star_time()[0] is None


def test_server_gps_anchor_beats_the_others_and_the_autopilot_cross_checks_it():
    r, _ = _rtc(off=-120.0)
    r.read()
    s = _field(r, ntp=True)
    now = time.time()
    s.on_autopilot_time(now + 30.0, now)
    assert s.star_time()[1] == "autopilot"
    s.on_gps_time(now + 30.2, now, 35.0, 10.0)        # no phone position: a satellite fix is trusted
    off, src, sig = s.star_time_sigma()
    assert src == "gnss" and abs(off + 30.2) < 1e-3 and abs(sig - 0.5) < 1e-3
    st = s.time_status()
    assert st["source"] == "gnss" and abs(st["anchor"]["minus_autopilot_s"] - 0.2) < 1e-3
    s.on_autopilot_time(now + 32.0, now)              # 1.8 s from the anchor: one of them lies
    off, why = s.star_time()
    assert off is None and "disagree" in why


def test_server_refuses_a_gps_far_from_the_phone():
    s = _field(None)
    s.phone, s.phone_recv = {"lat": 35.0, "lon": 10.0, "acc": 5.0}, time.time()
    now = time.time()
    s.on_gps_time(now + 5.0, now, 36.0, 10.0)         # 111 km away
    off, why = s.star_time()
    assert off is None and "GPS time anchor" in why
    assert "km from the phone" in s.time_status()["gnss_untrusted_why"]
    s.on_gps_time(now + 5.0, now, 35.001, 10.0)
    assert s.star_time()[1] == "gnss"
