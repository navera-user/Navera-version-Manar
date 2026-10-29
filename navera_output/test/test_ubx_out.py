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
    valset = (struct.pack("<BBBB", 0, 1, 0, 0) + struct.pack("<IB", 0x10740001, 1)     # a 1-bit key first
              + struct.pack("<II", ubx_out.CFG_UART1_BAUDRATE, 230400))
    assert ubx_out.Responder().feed(ubx_out.frame(ubx_out.CFG, ubx_out.CFG_VALSET, valset))[1] == 230400
