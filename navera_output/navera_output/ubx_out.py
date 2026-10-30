"""u-blox UBX output: NAVERA as a u-blox GPS module on a serial port, for any flight controller that
takes one (PX4, INAV, Betaflight, ArduPilot GPS_TYPE = 2, and most others).

Unlike NMEA, UBX NAV-PVT carries the accuracy (hAcc, vAcc, sAcc): a vision position goes out with
its own stated accuracy, as over MAVLink, so the same forwarding rules apply (policy.decide).

Sent per position: NAV-PVT (newer drivers) and NAV-POSLLH / NAV-STATUS / NAV-SOL / NAV-VELNED /
NAV-DOP (older ones). A driver that configures its receiver sends CFG messages and waits for an
ACK; every CFG message is acknowledged (nothing is actually configurable), MON-VER is answered
(protocol 18, a u-blox M8: the drivers then use their M8 path), and a baud rate change asked by
CFG-PRT or CFG-VALSET (UART1) is returned so the caller switches its port after the ACK.

A position without a measured height (vision / celestial) carries the last GNSS height sent with
vAcc "unknown" (the autopilot must take its height from the barometer), as HIL_GPS does
(mavlink_out). Satellites: the receiver's count with a GNSS fix; for a non-GNSS position
`estimated_satellites` (default 0, which some firmwares refuse: INAV needs gps_min_sats,
Betaflight gps_rescue_min_sats; the accuracy fields remain the honest statement).
"""
import math
import struct
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from navera_output.mavlink_out import gps_week_time
from navera_output.policy import KIND_ESTIMATED, KIND_FIX, Output

SYNC = b"\xb5\x62"
NAV, ACK, CFG, MON = 0x01, 0x05, 0x06, 0x0A
NAV_POSLLH, NAV_STATUS, NAV_DOP, NAV_SOL, NAV_PVT, NAV_VELNED = 0x02, 0x03, 0x04, 0x06, 0x07, 0x12
ACK_ACK = 0x01
CFG_PRT, CFG_VALSET = 0x00, 0x8A
MON_VER = 0x04
CFG_UART1_BAUDRATE = 0x40520001
UERE_M = 2.0
UNKNOWN_MM = 0xFFFFFFFF
FIX_NONE, FIX_3D = 0, 3


def checksum(body: bytes) -> bytes:
    a = b = 0
    for x in body:
        a = (a + x) & 0xFF
        b = (b + a) & 0xFF
    return bytes((a, b))


def frame(cls: int, mid: int, payload: bytes = b"") -> bytes:
    body = struct.pack("<BBH", cls, mid, len(payload)) + payload
    return SYNC + body + checksum(body)


def _mm(v: float) -> int:
    return int(min(max(round(v * 1000.0), 0), UNKNOWN_MM - 1)) if math.isfinite(v) else UNKNOWN_MM


def _fields(out: Output, held_alt_msl_m: float, estimated_satellites: int):
    """(fix, lat, lon, h_ell_mm, h_msl_mm, h_acc_mm, v_acc_mm, vn, ve, s_acc_mm, sats, dop_x100)."""
    if out.kind not in (KIND_FIX, KIND_ESTIMATED):
        return (False, 0, 0, 0, 0, UNKNOWN_MM, UNKNOWN_MM, 0, 0, UNKNOWN_MM, 0, 9999)
    msl, sep = (out.alt_msl_m, out.geoid_sep_m) if out.gnss else (math.nan, math.nan)
    v_acc = _mm(out.sigma_v_m)
    if not math.isfinite(msl):
        msl, v_acc = (held_alt_msl_m if math.isfinite(held_alt_msl_m) else 0.0), UNKNOWN_MM
    ell = msl + (sep if math.isfinite(sep) else 0.0)
    vn = round(out.vel_n_mps * 1000.0) if out.has_velocity else 0
    ve = round(out.vel_e_mps * 1000.0) if out.has_velocity else 0
    s_acc = _mm(out.vel_sigma_mps)
    if out.gnss:
        sats = out.satellites if out.satellites is not None else 0
    else:
        sats = int(estimated_satellites)
    dop = int(min(out.sigma_h_m / UERE_M, 99.99) * 100) if math.isfinite(out.sigma_h_m) else 9999
    return (True, round(out.lat * 1e7), round(out.lon * 1e7), round(ell * 1000.0), round(msl * 1000.0),
            _mm(out.sigma_h_m), v_acc, vn, ve, s_acc, min(max(sats, 0), 255), dop)


def position_messages(out: Output, t_utc: datetime, held_alt_msl_m: float = math.nan,
                      estimated_satellites: int = 0) -> bytes:
    """The UBX messages for one output decision, stamped `t_utc` (the measurement instant)."""
    ok, lat, lon, ell, msl, h_acc, v_acc, vn, ve, s_acc, sats, dop = _fields(
        out, held_alt_msl_m, estimated_satellites)
    t = t_utc.astimezone(timezone.utc)
    week, week_ms = gps_week_time(t)
    itow = week_ms
    fix = FIX_3D if ok else FIX_NONE
    gnss_ok = 0x01 if ok else 0x00
    speed = int(round(math.hypot(vn, ve)))
    head = int(round((math.degrees(math.atan2(ve, vn)) % 360.0) * 1e5)) if speed else 0
    # u-blox: the date and time rounded to the nearest second, nano the rest (-5e8..5e8)
    t_sec = (t + timedelta(milliseconds=500)).replace(microsecond=0)
    nano = round((t - t_sec).total_seconds() * 1e9)
    pvt = struct.pack("<IHBBBBBBIiBBBBiiiiIIiiiiiIIHH4xiHH",
                      itow, t_sec.year, t_sec.month, t_sec.day, t_sec.hour, t_sec.minute, t_sec.second,
                      0x07, 50_000, nano, fix, gnss_ok, 0, sats,
                      lon, lat, ell, msl, h_acc, v_acc, vn, ve, 0, speed, head,
                      s_acc, 18_000_000, dop, 0x0000 if ok else 0x0001, 0, 0, 0)
    posllh = struct.pack("<IiiiiII", itow, lon, lat, ell, msl, h_acc, v_acc)
    status = struct.pack("<IBBBBII", itow, fix, gnss_ok | (0x0C if ok else 0), 0, 0, 0, 0)
    ecef = _ecef_cm(lat * 1e-7, lon * 1e-7, ell / 1000.0) if ok else (0, 0, 0)
    sol = struct.pack("<IihBBiiiIiiiIHBBI", itow, 0, week, fix, gnss_ok | 0x0C if ok else 0,
                      *ecef, min(h_acc // 10, UNKNOWN_MM), 0, 0, 0, min(s_acc // 10, UNKNOWN_MM),
                      dop, 0, sats, 0)
    velned = struct.pack("<IiiiIIiII", itow, int(vn / 10), int(ve / 10), 0, speed // 10,
                         speed // 10, head, min(s_acc // 10, UNKNOWN_MM), 18_000_000)
    dops = struct.pack("<IHHHHHHH", itow, dop, dop, dop, dop, dop, dop, dop)
    return (frame(NAV, NAV_PVT, pvt) + frame(NAV, NAV_POSLLH, posllh) + frame(NAV, NAV_STATUS, status)
            + frame(NAV, NAV_SOL, sol) + frame(NAV, NAV_VELNED, velned) + frame(NAV, NAV_DOP, dops))


def _ecef_cm(lat_deg: float, lon_deg: float, h_m: float) -> Tuple[int, int, int]:
    a, e2 = 6378137.0, 6.69437999014e-3
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    n = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return (round((n + h_m) * math.cos(la) * math.cos(lo) * 100),
            round((n + h_m) * math.cos(la) * math.sin(lo) * 100),
            round((n * (1 - e2) + h_m) * math.sin(la) * 100))


def mon_ver() -> bytes:
    def field(s: str, n: int) -> bytes:
        return s.encode("ascii")[:n - 1].ljust(n, b"\0")
    return frame(MON, MON_VER, field("NAVERA 0.7", 30) + field("00080000", 10)
                 + field("PROTVER=18.00", 30) + field("MOD=NAVERA", 30))


class Responder:
    """Reads what the flight controller sends and gives the replies (ACKs, MON-VER)."""

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data: bytes) -> Tuple[bytes, Optional[int]]:
        """(bytes to send back, a baud rate to switch to after sending them, or None)."""
        self._buf += data
        reply, baud = b"", None
        for cls, mid, payload in self._messages():
            if cls == CFG:
                reply += frame(ACK, ACK_ACK, bytes((cls, mid)))
                baud = requested_baud(mid, payload) or baud
            elif cls == MON and mid == MON_VER and not payload:
                reply += mon_ver()
        return reply, baud

    def _messages(self) -> List[Tuple[int, int, bytes]]:
        found = []
        while True:
            i = self._buf.find(SYNC)
            if i < 0:
                del self._buf[:max(len(self._buf) - 1, 0)]
                return found
            del self._buf[:i]
            if len(self._buf) < 8:
                return found
            cls, mid, n = struct.unpack_from("<BBH", self._buf, 2)
            if n > 1024:                  # not a real frame: skip this sync
                del self._buf[:2]
                continue
            if len(self._buf) < 8 + n:
                return found
            body = bytes(self._buf[2:6 + n])
            if checksum(body) == bytes(self._buf[6 + n:8 + n]):
                found.append((cls, mid, body[4:]))
                del self._buf[:8 + n]
            else:
                del self._buf[:2]


def requested_baud(mid: int, payload: bytes) -> Optional[int]:
    """The UART baud rate a CFG-PRT (port 1, UART1) or CFG-VALSET (CFG-UART1-BAUDRATE) sets."""
    if mid == CFG_PRT and len(payload) >= 20 and payload[0] == 1:
        return struct.unpack_from("<I", payload, 8)[0] or None
    if mid == CFG_VALSET and len(payload) >= 4:
        i = 4
        while i + 4 <= len(payload):
            key = struct.unpack_from("<I", payload, i)[0]
            size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}.get((key >> 28) & 0x7, 0)
            if not size:
                return None
            if key == CFG_UART1_BAUDRATE and i + 4 + size <= len(payload):
                return struct.unpack_from("<I", payload, i + 4)[0] or None
            i += 4 + size
    return None
