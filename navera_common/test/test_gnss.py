"""GNSS receivers in every form: UBX, mixed UBX + NMEA, DroneCAN Fix2, network streams."""
import math
import socket
import struct
import threading
import time
import types

import pytest

from navera_common import gnss
from navera_common.gnss import (NAV, NAV_DOP, NAV_PVT, StreamDecoder, fix2_fix, parse_nav_dop, parse_nav_pvt,
                                parse_stream_url, pvt_fix, ubx_frame, ubx_info)


def nav_pvt(lat=35.7340010, lon=10.5758485, height_mm=127400, hmsl_mm=95300, fix_type=3, flags=0x01,
            num_sv=12, h_acc_mm=1500, v_acc_mm=2500, vel_ned_mm=(1000, -2000, 300), valid=0x07,
            utc=(2026, 10, 22, 14, 16, 21), nano=250_000_000, invalid_llh=False, length=92):
    """A NAV-PVT payload laid out as in the u-blox M8/M9/M10 interface descriptions."""
    y, mo, d, h, mi, s = utc
    p = struct.pack("<IHBBBBBBIiBBBBiiiiIIiiiiiIIH", 123456000, y, mo, d, h, mi, s, valid, 30, nano, fix_type,
                    flags, 0, num_sv, round(lon * 1e7), round(lat * 1e7), height_mm, hmsl_mm, h_acc_mm, v_acc_mm,
                    *vel_ned_mm, 2236, 0, 500, 0, 120)
    p += bytes((1 if invalid_llh else 0,)) + bytes(13)
    return p[:length]


def nmea(body):
    c = 0
    for ch in body.encode():
        c ^= ch
    return f"${body}*{c:02X}\r\n".encode()


GGA = nmea("GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,")


def test_ubx_frame_checksum_matches_the_u_blox_example():
    # UBX-CFG-MSG poll of NAV-PVT, a frame quoted in u-blox application notes: B5 62 06 01 02 00 01 07 11 3A
    assert ubx_frame(0x06, 0x01, bytes((0x01, 0x07))) == bytes.fromhex("b562060102000107113a")


def test_decoder_splits_mixed_ubx_and_nmea_across_any_chunking():
    stream = b"\x00\xff junk " + ubx_frame(NAV, NAV_PVT, nav_pvt()) + GGA + b"\xb5\x62\x01" + \
        ubx_frame(NAV, NAV_DOP, struct.pack("<IHHHHHHH", 123456000, 150, 130, 90, 110, 72, 60, 50)) + GGA * 20
    # a truncated frame ("b5 62 01") makes the decoder wait for the length it reads, then
    # resynchronise on the next frame: nothing is lost, the stream goes on
    for chunk in (1, 3, 7, 64, len(stream)):
        dec, out = StreamDecoder(), []
        for i in range(0, len(stream), chunk):
            out += dec.feed(stream[i:i + chunk])
        kinds = [(o[0], o[2]) if o[0] == "ubx" else ("nmea", o[1][:6]) for o in out]
        assert kinds[:3] == [("ubx", NAV_PVT), ("nmea", "$GNGGA"), ("ubx", NAV_DOP)], (chunk, kinds)
        assert len(kinds) == 23


def test_decoder_drops_a_corrupted_frame_and_stays_bounded():
    f = bytearray(ubx_frame(NAV, NAV_PVT, nav_pvt()))
    f[30] ^= 0x40                                           # one bit flipped in the position
    dec = StreamDecoder()
    assert dec.feed(bytes(f)) == [] and dec.ubx_bad == 1
    assert dec.feed(ubx_frame(NAV, NAV_PVT, nav_pvt()))[0][2] == NAV_PVT       # resynchronised
    dec.feed(bytes(range(256)) * 100)                       # noise at a wrong baud
    assert len(dec.buf) <= 4 * gnss.UBX_MAX_LEN
    # a sync followed by an absurd length is a false sync, not a 60 kB wait
    assert dec.feed(b"\xb5\x62\x01\x07\xff\xff" + GGA)[0][0] == "nmea"


def test_a_3d_fix_with_the_receivers_own_accuracy():
    f = pvt_fix(parse_nav_pvt(nav_pvt()))
    assert f.valid and f.reason == ""
    assert f.lat == pytest.approx(35.7340010, abs=1e-7) and f.lon == pytest.approx(10.5758485, abs=1e-7)
    assert f.alt == pytest.approx(127.4)                   # above the ellipsoid (NAV-PVT height)
    assert f.details["geo_sep_m"] == pytest.approx(32.1)   # height - hMSL, for MSL outputs
    assert f.h_acc == pytest.approx(1.5) and f.v_acc == pytest.approx(2.5)
    assert f.covariance() == pytest.approx([2.25, 0, 0, 0, 2.25, 0, 0, 0, 6.25])
    assert f.vel_enu == pytest.approx((-2.0, 1.0, -0.3))   # NED (1, -2, 0.3) -> ENU
    assert f.num_sats == 12 and not f.gbas
    assert f.utc == pytest.approx(1792678581.25)            # 2026-10-22T14:16:21.25Z


def test_only_satellite_fixes_count():
    for kw, word in ((dict(fix_type=1), "dead reckoning only"), (dict(fix_type=5), "time only"),
                     (dict(fix_type=0, flags=0), "no GPS fix"), (dict(flags=0), "gnssFixOK not set"),
                     (dict(invalid_llh=True), "flags the position invalid")):
        f = pvt_fix(parse_nav_pvt(nav_pvt(**kw)))
        assert not f.valid and word in f.reason, (kw, f.reason)
        assert math.isnan(f.lat) and f.covariance() is None
    assert pvt_fix(parse_nav_pvt(nav_pvt(fix_type=2))).valid           # 2D: a satellite fix (as GGA 1)
    assert pvt_fix(parse_nav_pvt(nav_pvt(fix_type=4))).valid           # GNSS + dead reckoning


def test_rtk_and_dgps_are_gbas_and_unknown_accuracy_stays_unknown():
    assert pvt_fix(parse_nav_pvt(nav_pvt(flags=0x01 | 0x80))).details["rtk"] == "fixed"
    assert pvt_fix(parse_nav_pvt(nav_pvt(flags=0x03))).gbas
    f = pvt_fix(parse_nav_pvt(nav_pvt(h_acc_mm=0, v_acc_mm=0)))
    assert f.valid and f.covariance() is None


def test_time_only_when_the_receiver_vouches_for_it():
    assert pvt_fix(parse_nav_pvt(nav_pvt(valid=0x03))).utc is None     # not fully resolved
    assert pvt_fix(parse_nav_pvt(nav_pvt(nano=-100_000_000))).utc == pytest.approx(1792678580.9)


def test_u_blox_7_short_nav_pvt_and_nav_dop():
    assert pvt_fix(parse_nav_pvt(nav_pvt(length=84))).valid
    assert parse_nav_pvt(b"\x00" * 40) is None
    dop = parse_nav_dop(struct.pack("<IHHHHHHH", 123456000, 150, 130, 90, 110, 72, 60, 50))
    f = pvt_fix(parse_nav_pvt(nav_pvt()), dop)
    assert f.details["hdop"] == pytest.approx(0.72)


def test_ubx_info_for_discovery():
    assert ubx_info(ubx_frame(NAV, NAV_PVT, nav_pvt()) * 2) == {"valid": 2, "pvt": True, "nav": True, "fix": True}
    assert ubx_info(ubx_frame(NAV, NAV_PVT, nav_pvt(fix_type=0, flags=0)))["fix"] is False
    assert ubx_info(GGA * 3)["valid"] == 0


def test_receiver_configuration_frames_are_well_formed_and_ram_only():
    frames = gnss.ubx_enable_pvt_frames()
    for f in frames:
        out = StreamDecoder().feed(f)
        assert len(out) == 1 and out[0][1] == gnss.CFG
    valset = StreamDecoder().feed(frames[-1])[0][3]
    assert valset[1] == 0x01                                # layer RAM only, never flash


# ── DroneCAN Fix2 ─────────────────────────────────────────────────────────
def fix2(**kw):
    m = dict(status=3, mode=0, sats_used=14, pdop=1.1, latitude_deg_1e8=3573400100, longitude_deg_1e8=1057584850,
             height_ellipsoid_mm=127400, height_msl_mm=95300, ned_velocity=[1.0, -2.0, 0.3],
             covariance=[2.25, 2.25, 6.25, 0.04, 0.04, 0.04],
             gnss_timestamp=types.SimpleNamespace(usec=1792678581250000), gnss_time_standard=2, num_leap_seconds=0)
    m.update(kw)
    return types.SimpleNamespace(**m)


def test_fix2_as_ardupilot_periph_sends_it():
    f = fix2_fix(fix2())
    assert f.valid and f.lat == pytest.approx(35.734001) and f.alt == pytest.approx(127.4)
    assert f.h_acc == pytest.approx(1.5) and f.v_acc == pytest.approx(2.5)
    assert f.vel_enu == pytest.approx((-2.0, 1.0, -0.3)) and f.utc == pytest.approx(1792678581.25)
    assert f.details["geo_sep_m"] == pytest.approx(32.1) and f.num_sats == 14


def test_fix2_status_covariance_and_time_forms():
    assert not fix2_fix(fix2(status=1)).valid and "time only" in fix2_fix(fix2(status=1)).reason
    assert not fix2_fix(fix2(status=0)).valid
    assert not fix2_fix(fix2(latitude_deg_1e8=0, longitude_deg_1e8=0)).valid
    assert fix2_fix(fix2(covariance=[])).covariance() is None                  # unknown stays unknown
    assert fix2_fix(fix2(covariance=[float("nan")] * 6)).covariance() is None
    full = [0.0] * 36
    full[0], full[7], full[14] = 4.0, 9.0, 16.0
    assert fix2_fix(fix2(covariance=full)).h_acc == pytest.approx(3.0)
    assert fix2_fix(fix2(mode=2)).gbas                                         # RTK
    gps_t = fix2_fix(fix2(gnss_time_standard=3, num_leap_seconds=0))
    assert gps_t.utc == pytest.approx(1792678581.25 - 18)
    assert fix2_fix(fix2(gnss_time_standard=0)).utc is None


def test_fix2_as_a_pydronecan_message():
    dronecan = pytest.importorskip("dronecan")
    m = dronecan.uavcan.equipment.gnss.Fix2(latitude_deg_1e8=3573400100, longitude_deg_1e8=1057584850,
                                            height_ellipsoid_mm=127400, height_msl_mm=95300, status=3,
                                            sats_used=12, covariance=[2.25, 2.25, 6.25, 0.04, 0.04, 0.04],
                                            ned_velocity=[1.0, -2.0, 0.3], gnss_time_standard=2)
    m.gnss_timestamp.usec = 1792678581250000
    f = fix2_fix(m)
    assert f.valid and f.h_acc == pytest.approx(1.5, rel=1e-3) and f.utc == pytest.approx(1792678581.25)


# ── stream addresses ──────────────────────────────────────────────────────
def test_stream_urls():
    assert parse_stream_url("serial:/dev/ttyUSB0:9600") == ("serial", "/dev/ttyUSB0", 9600)
    assert parse_stream_url("tcp:192.168.1.20:10110") == ("tcp", "192.168.1.20", 10110)
    assert parse_stream_url("udp:10110") == ("udp", "0.0.0.0", 10110)
    assert parse_stream_url("udp:127.0.0.1:10110") == ("udp", "127.0.0.1", 10110)
    for bad in ("", "tcp:host", "serial:ttyUSB0:9600", "udp:0", "http://x", "tcp:h:99999"):
        with pytest.raises(ValueError):
            parse_stream_url(bad)


def test_tcp_and_udp_streams_read_and_report_a_lost_connection():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        c.sendall(GGA)
        time.sleep(0.2)
        c.close()
    threading.Thread(target=serve, daemon=True).start()
    st = gnss.Stream(f"tcp:127.0.0.1:{port}", timeout=1.0)
    data = b""
    with pytest.raises(ConnectionError):
        for _ in range(20):
            data += st.read()
    assert data == GGA
    st.close()
    srv.close()

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    uport = probe.getsockname()[1]
    probe.close()
    st = gnss.Stream(f"udp:127.0.0.1:{uport}", timeout=1.0)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.sendto(GGA, ("127.0.0.1", uport))
    assert st.read() == GGA
    assert st.read() == b""                                 # nothing more: no error, no data
    with pytest.raises(OSError):
        st.write(b"x")                                      # a UDP GPS is never written to
    st.close()
    tx.close()
