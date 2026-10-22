"""Field server time feeds (time_feeds.py) on synthetic GPS bytes and a fake autopilot link (no hardware)."""
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "navera_common"))

from navera_common.gnss import NAV, NAV_PVT, ubx_frame  # noqa: E402
from navera_tools.field import time_feeds as tf  # noqa: E402


def nmea(body):
    c = 0
    for ch in body.encode():
        c ^= ch
    return f"${body}*{c:02X}\r\n".encode()


def nav_pvt(valid=0x07, fix_type=3, flags=0x01, utc=(2026, 10, 22, 14, 16, 21), nano=250_000_000):
    y, mo, d, h, mi, s = utc
    p = struct.pack("<IHBBBBBBIiBBBBiiiiIIiiiiiIIH", 123456000, y, mo, d, h, mi, s, valid, 30, nano, fix_type,
                    flags, 0, 12, round(10.5 * 1e7), round(35.7 * 1e7), 127400, 95300, 1500, 2500,
                    0, 0, 0, 0, 0, 500, 0, 120)
    return p + bytes(14)


class Mono:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_ubx_time_only_when_valid_and_fully_resolved():
    p = tf.GnssTimeParser()
    out = p.feed(ubx_frame(NAV, NAV_PVT, nav_pvt()))
    assert len(out) == 1 and abs(out[0][0] - 1792678581.25) < 1e-6 and abs(out[0][1] - 35.7) < 1e-9
    assert p.feed(ubx_frame(NAV, NAV_PVT, nav_pvt(valid=0x03))) == []          # not fully resolved
    assert p.feed(ubx_frame(NAV, NAV_PVT, nav_pvt(fix_type=0, flags=0))) == []  # no fix


def test_rmc_and_zda_next_to_a_fix_only():
    m = Mono()
    p = tf.GnssTimeParser(mono=m)
    zda = nmea("GPZDA,201959.50,21,10,2026,00,00")
    assert p.feed(zda) == []                                                     # no fix yet
    out = p.feed(nmea("GPRMC,201959.00,A,3549.73,N,01038.16,E,0.0,0.0,211026,,,A"))
    assert len(out) == 1 and abs(out[0][0] - 1792613999.0) < 1e-6
    out = p.feed(zda)
    assert len(out) == 1 and abs(out[0][0] - 1792613999.5) < 1e-6 and out[0][1] is not None
    m.t += 3.0
    assert p.feed(zda) == []                                                     # the fix is 3 s old
    assert p.feed(nmea("GPRMC,201959.00,V,,,,,,,211026,,,N")) == []


def test_phone_trust():
    phone = {"lat": 35.0, "lon": 10.0, "acc": 5.0}
    assert tf.phone_trust(phone, 1.0, 35.001, 10.0)[0] is True
    ok, why = tf.phone_trust(phone, 1.0, 35.1, 10.0)
    assert not ok and "km from the phone" in why
    assert tf.phone_trust(phone, 60.0, 35.1, 10.0)[0] is True                   # phone position stale: not a referee
    assert tf.phone_trust({}, 0.0, None, None)[0] is False


class FakeMsg:
    def __init__(self, kind, usec=0, src=(1, 1), autopilot=3):
        self.kind, self.time_unix_usec, self.src, self.autopilot = kind, usec, src, autopilot

    def get_type(self):
        return self.kind

    def get_srcSystem(self):
        return self.src[0]

    def get_srcComponent(self):
        return self.src[1]


class FakeLink:
    def __init__(self, msgs, feed):
        self.msgs, self.feed, self.target_system, self.target_component, self.sent = list(msgs), feed, 0, 0, []
        outer = self

        class Mav:
            def command_long_send(self, *a):
                outer.sent.append(a)
        self.mav = Mav()

    def recv_match(self, **kw):
        if not self.msgs:
            self.feed.stop()
            return None
        return self.msgs.pop(0)

    def close(self):
        pass


def test_autopilot_feed_reads_system_time_and_asks_for_it():
    got = []
    feed = tf.AutopilotTimeFeed("udpin:0.0.0.0:1", lambda u, s: got.append(u))
    msgs = [FakeMsg("HEARTBEAT"), FakeMsg("SYSTEM_TIME", 0), FakeMsg("SYSTEM_TIME", 1_792_613_999_500_000)]
    link = FakeLink(msgs, feed)
    feed.connect = lambda url: link
    feed._session()
    assert got == [1_792_613_999.5] and feed.last["ok"] and feed.last["samples"] == 1
    assert link.target_system == 1 and link.sent and link.sent[0][2] == 511            # SET_MESSAGE_INTERVAL
