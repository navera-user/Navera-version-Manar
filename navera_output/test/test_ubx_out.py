"""Unit tests for the u-blox UBX output (navera_output.ubx_out), decoded here by the u-blox layout."""
import math
import struct
from datetime import datetime, timezone

from navera_output import ubx_out
from navera_output.policy import KIND_ESTIMATED, KIND_FIX, KIND_NONE, Output

T = datetime(2026, 9, 28, 12, 34, 56, 780000, tzinfo=timezone.utc)
SIZES = {ubx_out.NAV_PVT: 92, ubx_out.NAV_POSLLH: 28, ubx_out.NAV_STATUS: 16, ubx_out.NAV_SOL: 52,
         ubx_out.NAV_VELNED: 36, ubx_out.NAV_DOP: 18}


def frames(data: bytes):
    """Every UBX frame in `data` as (class, id, payload), checking sync and checksum."""
    found, i = [], 0
    while i < len(data):
        assert data[i:i + 2] == ubx_out.SYNC
        cls, mid, n = struct.unpack_from("<BBH", data, i + 2)
        body = data[i + 2:i + 6 + n]
        assert ubx_out.checksum(body) == data[i + 6 + n:i + 8 + n]
        found.append((cls, mid, body[4:]))
        i += 8 + n
    return found


def pvt(data: bytes) -> dict:
    p = {mid: pl for cls, mid, pl in frames(data) if cls == ubx_out.NAV}[ubx_out.NAV_PVT]
    v = struct.unpack("<IHBBBBBBIiBBBBiiiiIIiiiiiIIHH4xiHH", p)
    keys = ("iTOW year month day hour min sec valid tAcc nano fixType flags flags2 numSV lon lat height "
            "hMSL hAcc vAcc velN velE velD gSpeed headMot sAcc headAcc pDOP flags3 headVeh magDec magAcc")
    return dict(zip(keys.split(), v))


def gps_fix():
    return Output(KIND_FIX, lat=35.8288, lon=10.6360, alt_ellipsoid_m=43.0, geoid_sep_m=33.0,
                  sigma_h_m=2.0, sigma_v_m=4.0, satellites=9, gnss=True, vel_n_mps=3.0, vel_e_mps=-4.0,
                  vel_sigma_mps=0.5)


def test_every_message_has_its_u_blox_size_and_checksum():
    got = frames(ubx_out.position_messages(gps_fix(), T))
    assert [(c, m) for c, m, _ in got] == [(ubx_out.NAV, m) for m in SIZES]
    assert all(len(p) == SIZES[m] for _, m, p in got)


def test_a_gps_fix_round_trips_through_nav_pvt():
    d = pvt(ubx_out.position_messages(gps_fix(), T))
    assert d["fixType"] == 3 and d["flags"] & 1 and d["numSV"] == 9 and not d["flags3"] & 1
    assert d["lat"] == round(35.8288e7) and d["lon"] == round(10.6360e7)
    assert d["hMSL"] == 10000 and d["height"] == 43000
    assert d["hAcc"] == 2000 and d["vAcc"] == 4000 and d["sAcc"] == 500
    assert (d["velN"], d["velE"], d["velD"], d["gSpeed"]) == (3000, -4000, 0, 5000)
    assert math.isclose(d["headMot"] * 1e-5, math.degrees(math.atan2(-4, 3)) % 360, abs_tol=1e-4)
    # the time rounded to the nearest second, the rest in nano
    assert (d["hour"], d["min"], d["sec"], d["nano"]) == (12, 34, 57, -220_000_000)


def test_a_vision_position_carries_its_own_accuracy_and_no_vision_height():
    out = Output(KIND_ESTIMATED, lat=35.8, lon=10.6, sigma_h_m=25.0, vel_n_mps=10.0, vel_e_mps=0.0,
                 vel_sigma_mps=2.0)
    d = pvt(ubx_out.position_messages(out, T, held_alt_msl_m=120.0))
    assert d["fixType"] == 3 and d["hAcc"] == 25000 and d["sAcc"] == 2000
    assert d["hMSL"] == 120000 and d["vAcc"] == ubx_out.UNKNOWN_MM      # the last GNSS height, unknown
    assert d["numSV"] == 0
    assert pvt(ubx_out.position_messages(out, T, estimated_satellites=8))["numSV"] == 8


def test_no_fix_carries_no_position():
    d = pvt(ubx_out.position_messages(Output(KIND_NONE, "x"), T))
    assert d["fixType"] == 0 and not d["flags"] & 1 and d["flags3"] & 1
    assert d["lat"] == d["lon"] == 0 and d["hAcc"] == ubx_out.UNKNOWN_MM


def test_cfg_messages_are_acknowledged_and_mon_ver_answered_even_split_across_reads():
    r = ubx_out.Responder()
    msg = ubx_out.frame(ubx_out.CFG, 0x01, bytes((0x01, 0x07, 1)))      # CFG-MSG NAV-PVT rate 1
    poll = ubx_out.frame(ubx_out.MON, ubx_out.MON_VER)
    reply, baud = r.feed(b"\x00junk" + msg[:5])
    assert reply == b"" and baud is None
    reply, baud = r.feed(msg[5:] + poll)
    got = frames(reply)
    assert got[0] == (ubx_out.ACK, ubx_out.ACK_ACK, bytes((ubx_out.CFG, 0x01)))
    assert got[1][:2] == (ubx_out.MON, ubx_out.MON_VER) and b"PROTVER=18.00" in got[1][2]
    assert baud is None


def test_a_bad_checksum_is_ignored():
    bad = bytearray(ubx_out.frame(ubx_out.CFG, 0x08, b"\x64\x00\x01\x00\x01\x00"))
    bad[-1] ^= 0xFF
    assert ubx_out.Responder().feed(bytes(bad)) == (b"", None)


def test_a_baud_change_is_returned_after_its_ack():
    prt = struct.pack("<BBHIIHHHH", 1, 0, 0, 0x08D0, 115200, 1, 1, 0, 0)
    reply, baud = ubx_out.Responder().feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_PRT, prt))
    assert baud == 115200 and frames(reply)[0][0] == ubx_out.ACK
    usb = struct.pack("<BBHIIHHHH", 3, 0, 0, 0, 0, 1, 1, 0, 0)                # USB port: no baud
    assert ubx_out.Responder().feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_PRT, usb))[1] is None
    valset = (struct.pack("<BBBB", 0, 1, 0, 0) + struct.pack("<IB", 0x10740001, 1)     # protocol 27+: an M8
              + struct.pack("<II", 0x40520001, 230400))                               # refuses it, no baud change
    reply, baud = ubx_out.Responder().feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_VALSET, valset))
    assert baud is None and frames(reply) == [(ubx_out.ACK, ubx_out.ACK_NAK, bytes((ubx_out.CFG, ubx_out.CFG_VALSET)))]


def poll(r, mid, payload=b"", cls=ubx_out.CFG):
    """The frames `r` answers to one message."""
    return frames(r.feed(ubx_out.frame(cls, mid, payload))[0])


def answered(r, mid, payload=b""):
    """The polled CFG value, checking it comes before its ACK."""
    got = poll(r, mid, payload)
    assert len(got) == 2 and got[0][:2] == (ubx_out.CFG, mid)
    assert got[1] == (ubx_out.ACK, ubx_out.ACK_ACK, bytes((ubx_out.CFG, mid)))
    return got[0][2]


def test_cfg_prt_poll_names_uart1_at_the_current_baud():
    r = ubx_out.Responder(38400)
    p = answered(r, ubx_out.CFG_PRT)
    assert len(p) == 20 and p[0] == ubx_out.UBX_PORT and struct.unpack_from("<I", p, 8)[0] == 38400
    prt = struct.pack("<BBHIIHHHH", 1, 0, 0, 0x08D0, 230400, 1, 1, 0, 0)
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_PRT, prt))
    assert struct.unpack_from("<I", answered(r, ubx_out.CFG_PRT, b"\x01"), 8)[0] == 230400


def test_cfg_msg_rates_are_kept_and_read_back_on_uart1():
    r = ubx_out.Responder()
    p = answered(r, ubx_out.CFG_MSG, bytes((ubx_out.NAV, ubx_out.NAV_PVT)))
    assert p == bytes((ubx_out.NAV, ubx_out.NAV_PVT, 0, 1, 0, 0, 0, 0))
    assert answered(r, ubx_out.CFG_MSG, bytes((0x0A, 0x09)))[2 + ubx_out.UBX_PORT] == 0    # MON-HW: off
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_MSG, bytes((0x0A, 0x09, 5))))           # current port
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_MSG, bytes((ubx_out.NAV, ubx_out.NAV_POSLLH, 9, 0, 9, 9, 9, 9))))
    assert answered(r, ubx_out.CFG_MSG, bytes((0x0A, 0x09)))[2 + ubx_out.UBX_PORT] == 5
    assert ubx_out.NAV_POSLLH not in r.position_ids() and ubx_out.NAV_PVT in r.position_ids()


def test_a_message_set_to_rate_0_is_no_longer_sent():
    sent = frames(ubx_out.position_messages(gps_fix(), T, ids=(ubx_out.NAV_PVT, ubx_out.NAV_DOP)))
    assert [mid for _, mid, _ in sent] == [ubx_out.NAV_PVT, ubx_out.NAV_DOP]


def test_cfg_rate_poll_reads_back_the_rate_set():
    r = ubx_out.Responder()
    assert struct.unpack("<HHH", answered(r, ubx_out.CFG_RATE)) == (1000, 1, 1)
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_RATE, struct.pack("<HHH", 200, 1, 0)))
    assert struct.unpack("<HHH", answered(r, ubx_out.CFG_RATE)) == (200, 1, 0)


def test_cfg_nav5_applies_only_the_masked_fields():
    r = ubx_out.Responder()
    p = bytearray(answered(r, ubx_out.CFG_NAV5))
    assert len(p) == 36 and p[2] == 0 and p[12] == 5                     # portable, 5 deg min elevation
    p[0:2], p[2], p[12] = struct.pack("<H", 0x0001), 8, 15              # airborne <4g; min elev not masked
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_NAV5, bytes(p)))
    q = answered(r, ubx_out.CFG_NAV5)
    assert q[2] == 8 and q[12] == 5


def test_cfg_sbas_poll_reads_back_the_mode_set():
    r = ubx_out.Responder()
    assert answered(r, ubx_out.CFG_SBAS)[0] == 0x01
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_SBAS, struct.pack("<BBBBI", 0, 7, 3, 0, 0)))
    assert answered(r, ubx_out.CFG_SBAS)[0] == 0


def test_cfg_gnss_lists_the_m8_systems_and_keeps_a_changed_block():
    r = ubx_out.Responder()
    p = answered(r, ubx_out.CFG_GNSS)
    assert p[:4] == bytes((0, 32, 32, 7)) and len(p) == 4 + 7 * 8
    assert [p[4 + 8 * i] for i in range(7)] == [0, 1, 2, 3, 4, 5, 6]
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_GNSS, bytes((0, 32, 32, 1)) + struct.pack("<BBBBI", 3, 8, 16, 0,
                                                                                            0x01010001)))
    q = answered(r, ubx_out.CFG_GNSS)
    assert q == p[:4 + 3 * 8] + struct.pack("<BBBBI", 3, 8, 16, 0, 0x01010001) + p[4 + 4 * 8:]


def test_cfg_tp5_poll_and_set():
    r = ubx_out.Responder()
    assert len(answered(r, ubx_out.CFG_TP5)) == 32
    tp = bytearray(answered(r, ubx_out.CFG_TP5, b"\x00"))
    tp[28:32] = struct.pack("<I", 0x3F)
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_TP5, bytes(tp)))
    assert answered(r, ubx_out.CFG_TP5) == bytes(tp)


def test_nav_svinfo_poll_says_m8_and_valget_is_refused():
    r = ubx_out.Responder()
    got = poll(r, ubx_out.NAV_SVINFO, cls=ubx_out.NAV)
    assert got[0][:2] == (ubx_out.NAV, ubx_out.NAV_SVINFO) and got[0][2][5] & 0x07 == 4
    valget = struct.pack("<BBH", 0, 0, 0) + struct.pack("<I", 0x20030001)
    assert poll(r, ubx_out.CFG_VALGET, valget) == [(ubx_out.ACK, ubx_out.ACK_NAK,
                                                    bytes((ubx_out.CFG, ubx_out.CFG_VALGET)))]


def test_cfg_cfg_save_is_only_acknowledged():
    r = ubx_out.Responder()
    assert poll(r, ubx_out.CFG_CFG, bytes(12)) == [(ubx_out.ACK, ubx_out.ACK_ACK, bytes((ubx_out.CFG, 0x09)))]


def test_mon_gnss_follows_the_enabled_systems():
    r = ubx_out.Responder()
    got = poll(r, ubx_out.MON_GNSS, cls=ubx_out.MON)
    assert got[0][:2] == (ubx_out.MON, ubx_out.MON_GNSS) and len(got[0][2]) == 8
    version, supported, default, enabled, simultaneous = got[0][2][:5]
    assert (version, supported, enabled, simultaneous) == (0, 0x0F, 0x0B, 3)       # GPS, GLONASS, Galileo
    r.feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_GNSS, bytes((0, 32, 32, 1)) + struct.pack("<BBBBI", 6, 8, 14, 0,
                                                                                            0x01010000)))
    assert poll(r, ubx_out.MON_GNSS, cls=ubx_out.MON)[0][2][3] == 0x09                # GLONASS off


def test_ubx_below_38400_baud_is_refused_at_start():
    import pytest
    from navera_output.nodes.vehicle_output_node import check_serial_output
    with pytest.raises(ValueError, match="NAVERA_NMEA_BAUD >= 38400"):
        check_serial_output("ubx", "/dev/ttyTHS2", 9600)
    check_serial_output("ubx", "/dev/ttyTHS2", 38400)
    check_serial_output("ubx", "/dev/ttyTHS2", 115200)
    check_serial_output("nmea", "/dev/ttyTHS2", 9600)      # NMEA at 9600 is fine
    check_serial_output("ubx", "", 9600)                    # no serial output at all
