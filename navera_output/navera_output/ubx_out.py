"""u-blox UBX output: NAVERA as a u-blox GPS module on a serial port, for any flight controller that
takes one (PX4, INAV, Betaflight, ArduPilot GPS_TYPE = 2, and most others).

Unlike NMEA, UBX NAV-PVT carries the accuracy (hAcc, vAcc, sAcc): a vision position goes out with
its own stated accuracy, as over MAVLink, so the same forwarding rules apply (policy.decide).

Sent per position: NAV-PVT (newer drivers) and NAV-POSLLH / NAV-STATUS / NAV-SOL / NAV-VELNED /
NAV-DOP (older ones), minus those the driver turned off (rate 0). A driver that configures its
receiver sends CFG messages and waits for an ACK, and some read the configuration back (ArduPilot
GPS_AUTO_CONFIG = 1): Responder answers as a u-blox M8 does (CFG polls answered with the value last
set, MON-VER with protocol 18 and NAV-SVINFO with "M8", so the drivers use their M8 path; CFG-VALSET /
VALGET, unknown to an M8, are refused), and a baud rate change asked by CFG-PRT (UART1) is returned so
the caller switches its port after the ACK.

A position without a measured height (vision / celestial) carries the last GNSS height sent with
vAcc "unknown" (the autopilot must take its height from the barometer), as HIL_GPS does
(mavlink_out). Satellites: the receiver's count with a GNSS fix; for a non-GNSS position
`estimated_satellites` (default 0, which some firmwares refuse: INAV needs gps_min_sats,
Betaflight gps_rescue_min_sats; the accuracy fields remain the honest statement).
"""
import math
import struct
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from navera_output.mavlink_out import gps_week_time
from navera_output.policy import KIND_ESTIMATED, KIND_FIX, Output

SYNC = b"\xb5\x62"
NAV, ACK, CFG, MON = 0x01, 0x05, 0x06, 0x0A
NAV_POSLLH, NAV_STATUS, NAV_DOP, NAV_SOL, NAV_PVT, NAV_VELNED = 0x02, 0x03, 0x04, 0x06, 0x07, 0x12
ACK_ACK = 0x01
CFG_PRT, CFG_VALSET = 0x00, 0x8A
MON_VER = 0x04
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
                      estimated_satellites: int = 0, ids: Optional[Iterable[int]] = None) -> bytes:
    """The UBX messages for one output decision, stamped `t_utc` (the measurement instant).

    `ids`: the NAV message ids to send (Responder.position_ids: those the driver left on); default all.
    """
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
    payloads = {NAV_PVT: pvt, NAV_POSLLH: posllh, NAV_STATUS: status, NAV_SOL: sol, NAV_VELNED: velned,
                NAV_DOP: dops}
    wanted = set(payloads if ids is None else ids)
    return b"".join(frame(NAV, mid, pl) for mid, pl in payloads.items() if mid in wanted)


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


# The configuration a polling driver reads back (ArduPilot GPS_AUTO_CONFIG, PX4, INAV): the values a
# u-blox M8 holds after a reset, changed by the CFG messages the driver sends. NAVERA's output itself
# does not change with them (rate, dynamic model, GNSS systems mean nothing to a vision position),
# except the message rates: a NAV message set to rate 0 is no longer sent.
NAV_SVINFO = 0x30
CFG_MSG, CFG_RATE, CFG_CFG, CFG_SBAS, CFG_NAV5, CFG_TP5, CFG_GNSS = 0x01, 0x08, 0x09, 0x16, 0x24, 0x31, 0x3E
CFG_VALGET = 0x8B
ACK_NAK = 0x00
UBX_PORT = 1                          # UART1: the port index of NAVERA's serial line
POSITION_IDS = (NAV_PVT, NAV_POSLLH, NAV_STATUS, NAV_SOL, NAV_VELNED, NAV_DOP)
_NAV5_DEFAULT = struct.pack("<HBBiIbBHHHHBBBB2xHB5x", 0xFFFF, 0, 3, 0, 10000, 5, 0, 250, 250, 100, 300,
                            0, 60, 0, 0, 0, 0)
# CFG-NAV5 mask bit -> the payload bytes it applies
_NAV5_GROUPS = {0: (2, 3), 1: (12, 13), 2: (3, 12), 3: (13, 14), 4: (14, 20), 5: (20, 22),
                6: (22, 23), 7: (23, 24), 8: (24, 26), 10: (30, 31)}
# CFG-GNSS blocks of an M8 (gnssId, resTrkCh, maxTrkCh, flags): GPS, SBAS, Galileo, BeiDou, IMES, QZSS,
# GLONASS
_GNSS_DEFAULT = ((0, 8, 16, 0x01010001), (1, 1, 3, 0x01010001), (2, 4, 8, 0x01010001),
                 (3, 8, 16, 0x01010000), (4, 0, 8, 0x01010000), (5, 0, 3, 0x05050001),
                 (6, 8, 14, 0x01010001))


class Responder:
    """Reads what the flight controller sends and gives the replies a u-blox M8 gives.

    Every CFG message is acknowledged (ACK-ACK), except CFG-VALSET / CFG-VALGET (protocol 27+, unknown to
    an M8: ACK-NAK, so a driver that probes with them, PX4, takes its M8 path).
    A poll is answered with the current value before its ACK: CFG-PRT, CFG-MSG, CFG-RATE, CFG-NAV5,
    CFG-SBAS, CFG-GNSS, CFG-TP5, and MON-VER, NAV-SVINFO (the hardware generation: M8). A CFG message
    that sets a value is kept and read back, so a driver that checks its configuration
    (ArduPilot GPS_AUTO_CONFIG = 1) finds it done.
    """

    def __init__(self, baud: int = 0):
        self._buf = bytearray()
        self.baud = baud
        self.rates = {(NAV, mid): 1 for mid in POSITION_IDS}
        self._nav_rate = struct.pack("<HHH", 1000, 1, 1)
        self._nav5 = bytearray(_NAV5_DEFAULT)
        self._sbas = struct.pack("<BBBBI", 0x01, 0x07, 3, 0, 0)
        self._gnss = {g: struct.pack("<BBBBI", g, res, mx, 0, fl) for g, res, mx, fl in _GNSS_DEFAULT}
        self._tp5 = {}

    def position_ids(self) -> Tuple[int, ...]:
        """The NAV messages to send per position (those not set to rate 0)."""
        return tuple(mid for mid in POSITION_IDS if self.rates.get((NAV, mid), 0))

    def feed(self, data: bytes) -> Tuple[bytes, Optional[int]]:
        """(bytes to send back, a baud rate to switch to after sending them, or None)."""
        self._buf += data
        reply, baud = b"", None
        for cls, mid, payload in self._messages():
            if cls == CFG:
                if mid in (CFG_VALSET, CFG_VALGET):
                    reply += frame(ACK, ACK_NAK, bytes((cls, mid)))
                    continue
                reply += self._cfg(mid, payload) + frame(ACK, ACK_ACK, bytes((cls, mid)))
                baud = requested_baud(mid, payload) or baud
            elif cls == MON and mid == MON_VER and not payload:
                reply += mon_ver()
            elif cls == NAV and mid == NAV_SVINFO and not payload:
                reply += frame(NAV, NAV_SVINFO, struct.pack("<IBB2x", 0, 0, 4))    # globalFlags 4: M8
        if baud:
            self.baud = baud
        return reply, baud

    def _cfg(self, mid: int, p: bytes) -> bytes:
        """The polled value for a CFG poll; a CFG set is kept (b"" returned)."""
        if mid == CFG_PRT:
            if len(p) <= 1:
                port = p[0] if p else UBX_PORT
                return frame(CFG, CFG_PRT, struct.pack("<BBHIIHHHH", port, 0, 0, 0x08D0, self.baud,
                                                       0x07, 0x01, 0, 0))
        elif mid == CFG_MSG:
            if len(p) == 2:
                rate = self.rates.get((p[0], p[1]), 0)
                rates = bytes(rate if i == UBX_PORT else 0 for i in range(6))
                return frame(CFG, CFG_MSG, p + rates)
            if len(p) == 3:
                self.rates[(p[0], p[1])] = p[2]
            elif len(p) == 8:
                self.rates[(p[0], p[1])] = p[2 + UBX_PORT]
        elif mid == CFG_RATE:
            if not p:
                return frame(CFG, CFG_RATE, self._nav_rate)
            if len(p) == 6:
                self._nav_rate = p
        elif mid == CFG_NAV5:
            if not p:
                return frame(CFG, CFG_NAV5, bytes(self._nav5))
            if len(p) == 36:
                mask = struct.unpack_from("<H", p)[0]
                for bit, (a, b) in _NAV5_GROUPS.items():
                    if mask & (1 << bit):
                        self._nav5[a:b] = p[a:b]
        elif mid == CFG_SBAS:
            if not p:
                return frame(CFG, CFG_SBAS, self._sbas)
            if len(p) == 8:
                self._sbas = p
        elif mid == CFG_GNSS:
            if not p:
                blocks = b"".join(self._gnss[g] for g in sorted(self._gnss))
                return frame(CFG, CFG_GNSS, struct.pack("<BBBB", 0, 32, 32, len(self._gnss)) + blocks)
            for i in range(min(p[3], (len(p) - 4) // 8) if len(p) >= 4 else 0):
                block = p[4 + 8 * i:12 + 8 * i]
                self._gnss[block[0]] = block
        elif mid == CFG_TP5:
            if len(p) <= 1:
                idx = p[0] if p else 0
                return frame(CFG, CFG_TP5, self._tp5.get(idx, struct.pack(
                    "<BB2xhhIIIIiI", idx, 1, 50, 0, 1000000, 1000000, 0, 100000, 0, 0x77)))
            if len(p) == 32:
                self._tp5[p[0]] = p
        return b""

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
    """The UART baud rate a CFG-PRT for port 1 (UART1) sets."""
    if mid == CFG_PRT and len(payload) >= 20 and payload[0] == 1:
        return struct.unpack_from("<I", payload, 8)[0] or None
    return None
