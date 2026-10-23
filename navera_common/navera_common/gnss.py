"""GNSS receivers in every common form: what their bytes and messages say (no ROS).

Used by gps_pkg (the GPS source nodes) and by discovery (what is plugged in):

  * u-blox UBX binary (NAV-PVT, NAV-DOP), alone or mixed with NMEA on one stream — a
    receiver on a box UART / USB, or a passive tap (Y-cable on the receiver's TX) of the
    GPS an autopilot configured to UBX;
  * DroneCAN uavcan.equipment.gnss.Fix2 (Here3 / Here4, Holybro and other DroneCAN GNSS);
  * the stream address of a GPS: serial port, TCP client or UDP listener.

Every receiver becomes one normalized fix (``Fix``) with the same rules as the NMEA path
of gps_node: a fix only from satellites (no dead reckoning / time-only / manual), altitude
above the WGS84 ellipsoid, the receiver's own accuracy when it states one (UBX hAcc / vAcc,
Fix2 covariance), else unknown — never invented.

Read-only by design: nothing here writes to a receiver except ``ubx_enable_pvt_frames``,
which a caller sends only when the operator explicitly allowed NAVERA to configure the
receiver (NAVERA_GPS_CONFIGURE=1).
"""
import datetime
import math
import socket
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

UBX_SYNC = b"\xb5\x62"
UBX_MAX_LEN = 1024                # longer than any message NAVERA reads: a false sync
NAV, CFG = 0x01, 0x06
NAV_PVT, NAV_DOP, NAV_SAT = 0x07, 0x04, 0x35
NMEA_MAX = 100                    # NMEA 0183: 82 characters; some receivers exceed it a little

# GPS epoch, and the GPS-UTC offset since 2017-01-01 (used only when a receiver gives GPS
# time with no leap-second count)
GPS_EPOCH = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc).timestamp()
GPS_UTC_LEAP_S = 18


# ── UBX framing ──────────────────────────────────────────────────────────
def ubx_checksum(body: bytes) -> bytes:
    """8-bit Fletcher over class, id, length and payload."""
    a = b = 0
    for x in body:
        a = (a + x) & 0xFF
        b = (b + a) & 0xFF
    return bytes((a, b))


def ubx_frame(cls: int, mid: int, payload: bytes = b"") -> bytes:
    body = bytes((cls, mid)) + struct.pack("<H", len(payload)) + payload
    return UBX_SYNC + body + ubx_checksum(body)


class StreamDecoder:
    """Splits a byte stream into checksummed UBX frames and NMEA lines, in order.

    feed(data) -> [("ubx", cls, id, payload) | ("nmea", line)]. NMEA lines are returned as
    text without their line end; their checksum is checked by the caller (pynmea2
    check=True, or discovery). A UBX frame with a wrong checksum is dropped. Bytes that
    are neither (MAVLink, noise at a wrong baud) are skipped; the buffer stays bounded.
    """

    def __init__(self):
        self.buf = bytearray()
        self.ubx_bad = 0

    def feed(self, data: bytes) -> list:
        self.buf += data
        out, b = [], self.buf
        i = 0
        while True:
            j_u, j_n = b.find(UBX_SYNC, i), b.find(b"$", i)
            cands = [j for j in (j_u, j_n) if j >= 0]
            if not cands:
                i = max(i, len(b) - 1)                    # keep a lone 0xB5 for the next feed
                break
            j = min(cands)
            if j == j_u:
                if len(b) - j < 6:
                    i = j
                    break
                n = b[j + 4] | (b[j + 5] << 8)
                if n > UBX_MAX_LEN:
                    i = j + 1
                    continue
                if len(b) - j < 8 + n:
                    i = j
                    break
                body = bytes(b[j + 2:j + 6 + n])
                if ubx_checksum(body) == bytes(b[j + 6 + n:j + 8 + n]):
                    out.append(("ubx", body[0], body[1], body[4:]))
                    i = j + 8 + n
                else:
                    self.ubx_bad += 1
                    i = j + 1
            else:
                e = b.find(b"\n", j)
                if e < 0:
                    if len(b) - j > NMEA_MAX:
                        i = j + 1
                        continue
                    i = j
                    break
                line = bytes(b[j:e]).rstrip(b"\r")
                if len(line) <= NMEA_MAX and all(32 <= c < 127 for c in line):
                    out.append(("nmea", line.decode("ascii")))
                    i = e + 1
                else:
                    i = j + 1
        del b[:i]
        if len(b) > 4 * UBX_MAX_LEN:
            del b[:-UBX_MAX_LEN]
        return out


# ── the normalized fix ───────────────────────────────────────────────────
@dataclass
class Fix:
    """One receiver solution, as NAVERA's GPS source contract needs it."""
    valid: bool
    reason: str = ""
    lat: float = math.nan
    lon: float = math.nan
    alt: float = math.nan                       # m above the WGS84 ellipsoid
    h_acc: Optional[float] = None               # m, 1 sigma, as stated by the receiver
    v_acc: Optional[float] = None
    gbas: bool = False                          # differential / RTK
    num_sats: int = 0
    vel_enu: Optional[Tuple[float, float, float]] = None     # m/s
    utc: Optional[float] = None                 # epoch s of the solution, when the receiver vouches for it
    details: dict = field(default_factory=dict)

    def covariance(self) -> Optional[List[float]]:
        """Return the diagonal ENU variances (m^2) from the stated accuracy, or None if unknown."""
        if self.h_acc is None or not math.isfinite(self.h_acc) or self.h_acc <= 0:
            return None
        h = self.h_acc ** 2
        v = self.v_acc ** 2 if self.v_acc is not None and math.isfinite(self.v_acc) and self.v_acc > 0 else 4 * h
        return [h, 0.0, 0.0, 0.0, h, 0.0, 0.0, 0.0, v]


# ── u-blox NAV messages ──────────────────────────────────────────────────
PVT_FIX_NAMES = {0: "no fix", 1: "dead reckoning only", 2: "2D", 3: "3D", 4: "GNSS + dead reckoning",
                 5: "time only"}


def parse_nav_pvt(p: bytes) -> Optional[dict]:
    """UBX-NAV-PVT payload (92 bytes, u-blox 7 and later; 84 on u-blox 7) -> fields, or None."""
    if len(p) < 84:
        return None
    (itow, year, month, day, hour, minute, sec, valid, t_acc, nano, fix_type, flags, flags2, num_sv,
     lon, lat, height, h_msl, h_acc, v_acc, vel_n, vel_e, vel_d, g_speed, head_mot, s_acc, head_acc,
     p_dop) = struct.unpack_from("<IHBBBBBBIiBBBBiiiiIIiiiiiIIH", p, 0)
    return dict(itow=itow, year=year, month=month, day=day, hour=hour, minute=minute, sec=sec,
                valid=valid, t_acc=t_acc, nano=nano, fix_type=fix_type, flags=flags, num_sv=num_sv,
                lon=lon * 1e-7, lat=lat * 1e-7, height_m=height / 1000.0, h_msl_m=h_msl / 1000.0,
                h_acc_m=h_acc / 1000.0, v_acc_m=v_acc / 1000.0,
                vel_ned=(vel_n / 1000.0, vel_e / 1000.0, vel_d / 1000.0),
                s_acc=s_acc / 1000.0, p_dop=p_dop * 0.01,
                invalid_llh=bool(p[78] & 1) if len(p) >= 92 else False)


def parse_nav_dop(p: bytes) -> Optional[dict]:
    if len(p) < 18:
        return None
    itow, g, pd, t, v, h, n, e = struct.unpack_from("<IHHHHHHH", p, 0)
    return dict(itow=itow, gdop=g * 0.01, pdop=pd * 0.01, tdop=t * 0.01, vdop=v * 0.01, hdop=h * 0.01)


def pvt_fix(pvt: dict, dop: Optional[dict] = None) -> Fix:
    """The fix a NAV-PVT states. Valid only with gnssFixOK and a 2D / 3D / GNSS+DR fix
    (dead reckoning only and time only are not satellite positions), and a position the
    receiver does not flag invalid.
    """
    ft, ok = pvt["fix_type"], bool(pvt["flags"] & 0x01)
    details = {"num_sats": pvt["num_sv"], "fix_type": ft, "h_acc_m": round(pvt["h_acc_m"], 3),
               "v_acc_m": round(pvt["v_acc_m"], 3), "pdop": round(pvt["p_dop"], 2)}
    if dop and dop.get("itow") == pvt["itow"]:
        details["hdop"] = round(dop["hdop"], 2)
    if not ok or ft not in (2, 3, 4) or pvt["invalid_llh"]:
        why = ("receiver reports a non-satellite position (" + PVT_FIX_NAMES.get(ft, str(ft)) + ") — not used"
               if ft in (1, 5) else
               "receiver flags the position invalid" if pvt["invalid_llh"] and ok else
               f"no GPS fix ({PVT_FIX_NAMES.get(ft, ft)}{'' if ok else ', gnssFixOK not set'})")
        return Fix(valid=False, reason=why, num_sats=pvt["num_sv"], details=details)
    carr = (pvt["flags"] >> 6) & 0x03                          # 1 RTK float, 2 RTK fixed
    if carr:
        details["rtk"] = "fixed" if carr == 2 else "float"
    vn, ve, vd = pvt["vel_ned"]
    utc = None
    if pvt["valid"] & 0x07 == 0x07:                            # validDate, validTime, fullyResolved
        try:
            utc = datetime.datetime(pvt["year"], pvt["month"], pvt["day"], pvt["hour"], pvt["minute"],
                                    min(pvt["sec"], 59), tzinfo=datetime.timezone.utc).timestamp() \
                + (pvt["sec"] - min(pvt["sec"], 59)) + pvt["nano"] * 1e-9
        except ValueError:
            utc = None
    details["geo_sep_m"] = round(pvt["height_m"] - pvt["h_msl_m"], 3)
    return Fix(valid=True, lat=pvt["lat"], lon=pvt["lon"], alt=pvt["height_m"],
               h_acc=pvt["h_acc_m"] if pvt["h_acc_m"] > 0 else None,
               v_acc=pvt["v_acc_m"] if pvt["v_acc_m"] > 0 else None,
               gbas=bool(pvt["flags"] & 0x02) or bool(carr), num_sats=pvt["num_sv"],
               vel_enu=(ve, vn, -vd), utc=utc, details=details)


def ubx_info(data: bytes) -> dict:
    """What the UBX frames in raw bytes say (discovery): {"valid": checksummed frames,
    "pvt": NAV-PVT seen (a receiver NAVERA can use), "nav": any NAV message, "fix": a
    satellite fix stated}.
    """
    info = {"valid": 0, "pvt": False, "nav": False, "fix": False}
    for item in StreamDecoder().feed(data):
        if item[0] != "ubx":
            continue
        info["valid"] += 1
        _, cls, mid, payload = item
        if cls == NAV:
            info["nav"] = True
            if mid == NAV_PVT:
                pvt = parse_nav_pvt(payload)
                if pvt is not None:
                    info["pvt"] = True
                    info["fix"] = info["fix"] or pvt_fix(pvt).valid
    return info


# Opt-in receiver configuration (NAVERA_GPS_CONFIGURE=1 on a receiver NAVERA owns): turn on
# NAV-PVT and NAV-DOP at every navigation solution on all its ports, in RAM only (lost at
# power-off; the receiver's saved configuration is never changed). u-blox 6/7/8: CFG-MSG;
# u-blox 9/10: CFG-VALSET (layer RAM). A receiver ignores the form it does not know.
_VALSET_KEYS = (
    (0x10740001, 1),          # CFG-UART1OUTPROT-UBX
    (0x10780001, 1),          # CFG-USBOUTPROT-UBX
    (0x20910007, 1), (0x20910008, 1), (0x20910009, 1),    # CFG-MSGOUT-UBX_NAV_PVT UART1/UART2/USB
    (0x20910039, 1), (0x2091003A, 1), (0x2091003B, 1),    # CFG-MSGOUT-UBX_NAV_DOP UART1/UART2/USB
)


def ubx_enable_pvt_frames() -> List[bytes]:
    frames = [ubx_frame(CFG, 0x01, bytes((NAV, mid, 0, 1, 1, 1, 0, 0))) for mid in (NAV_PVT, NAV_DOP)]
    payload = bytes((0, 0x01, 0, 0))                           # version 0, layer RAM
    for key, val in _VALSET_KEYS:
        payload += struct.pack("<IB", key, val)
    frames.append(ubx_frame(CFG, 0x8A, payload))
    return frames


# ── DroneCAN uavcan.equipment.gnss.Fix2 ──────────────────────────────────
FIX2_STATUS = {0: "no fix", 1: "time only", 2: "2D", 3: "3D"}
FIX2_TIME_NONE, FIX2_TIME_TAI, FIX2_TIME_UTC, FIX2_TIME_GPS = 0, 1, 2, 3


def fix2_fix(m) -> Fix:
    """The fix a DroneCAN Fix2 message states (any object with Fix2's field names: a
    pydronecan message or a test stand-in). Valid with status 2D / 3D only; accuracy from
    its covariance (3 or 6 values: the diagonal, position first; 36: the full matrix; 1:
    one position variance), unknown when it is empty or not a number.
    """
    status, sats = int(m.status), int(m.sats_used)
    details = {"num_sats": sats, "fix_status": status, "mode": int(getattr(m, "mode", 0))}
    pdop = float(getattr(m, "pdop", math.nan))
    if math.isfinite(pdop) and pdop > 0:
        details["pdop"] = round(pdop, 2)
    lat, lon = m.latitude_deg_1e8 * 1e-8, m.longitude_deg_1e8 * 1e-8
    if status not in (2, 3) or (lat == 0.0 and lon == 0.0):
        why = ("receiver reports time only — not a position" if status == 1 else
               f"no GPS fix ({FIX2_STATUS.get(status, status)})" if status not in (2, 3) else "no position (0, 0)")
        return Fix(valid=False, reason=why, num_sats=sats, details=details)
    cov = [float(c) for c in m.covariance]
    h = v = None
    if len(cov) == 36:
        hv, vv = max(cov[0], cov[7]), cov[14]
    elif len(cov) >= 3:
        hv, vv = max(cov[0], cov[1]), cov[2]
    elif len(cov) == 1:
        hv = vv = cov[0]
    else:
        hv = vv = math.nan
    if math.isfinite(hv) and hv > 0:
        h = math.sqrt(hv)
        details["h_acc_m"] = round(h, 3)
    if math.isfinite(vv) and vv > 0:
        v = math.sqrt(vv)
        details["v_acc_m"] = round(v, 3)
    alt = m.height_ellipsoid_mm / 1000.0
    details["geo_sep_m"] = round((m.height_ellipsoid_mm - m.height_msl_mm) / 1000.0, 3)
    vel = None
    nv = [float(x) for x in m.ned_velocity]
    if len(nv) == 3 and all(math.isfinite(x) for x in nv):
        vel = (nv[1], nv[0], -nv[2])
    utc = None
    ts = int(m.gnss_timestamp.usec) if hasattr(m.gnss_timestamp, "usec") else int(m.gnss_timestamp)
    std = int(m.gnss_time_standard)
    if ts > 0 and std == FIX2_TIME_UTC:
        utc = ts * 1e-6
    elif ts > 0 and std == FIX2_TIME_GPS:
        # GPS time: UTC = GPS - leap seconds (the message's count when it gives one)
        leap = int(getattr(m, "num_leap_seconds", 0)) or GPS_UTC_LEAP_S
        utc = ts * 1e-6 - leap
    elif ts > 0 and std == FIX2_TIME_TAI:
        leap = int(getattr(m, "num_leap_seconds", 0))
        utc = ts * 1e-6 - leap if leap else None              # TAI - UTC = 37 s (2017): only when stated
    return Fix(valid=True, lat=lat, lon=lon, alt=alt, h_acc=h, v_acc=v,
               gbas=int(getattr(m, "mode", 0)) in (1, 2), num_sats=sats, vel_enu=vel, utc=utc,
               details=details)


# ── NMEA time (pynmea2 messages; validity rules shared by gps_node and the field tools) ──
def rmc_utc_epoch(msg):
    """UTC epoch seconds of a valid RMC sentence (status A, date and time present), else None."""
    if getattr(msg, "status", None) != "A":
        return None
    d, t = getattr(msg, "datestamp", None), getattr(msg, "timestamp", None)
    if not isinstance(d, datetime.date) or not isinstance(t, datetime.time):
        return None
    return datetime.datetime.combine(d, t.replace(tzinfo=None), tzinfo=datetime.timezone.utc).timestamp()


def zda_utc_epoch(msg):
    """UTC epoch seconds of a ZDA sentence with a time and a date from 2020 on, else None. ZDA has no
    validity flag: the caller accepts it only next to a valid fix.
    """
    t = getattr(msg, "timestamp", None)
    try:
        y, mo, d = int(msg.year), int(msg.month), int(msg.day)
    except (TypeError, ValueError, AttributeError):
        return None
    if not isinstance(t, datetime.time) or y < 2020:
        return None
    try:
        day = datetime.date(y, mo, d)
    except ValueError:
        return None
    return datetime.datetime.combine(day, t.replace(tzinfo=None), tzinfo=datetime.timezone.utc).timestamp()


# ── where the GPS bytes come from ────────────────────────────────────────
def parse_stream_url(url: str) -> Tuple[str, str, int]:
    """("serial", device, baud) | ("tcp", host, port) | ("udp", bind address, port).

    serial:/dev/ttyUSB0:9600, tcp:192.168.1.20:10110 (NAVERA connects), udp:10110 or
    udp:0.0.0.0:10110 (NAVERA listens). ValueError on anything else.
    """
    u = str(url).strip()
    kind, _, rest = u.partition(":")
    try:
        if kind == "serial":
            dev, _, baud = rest.rpartition(":")
            if dev.startswith("/dev/") and int(baud) > 0:
                return "serial", dev, int(baud)
        elif kind == "tcp":
            host, _, port = rest.rpartition(":")
            if host and 0 < int(port) < 65536:
                return "tcp", host, int(port)
        elif kind == "udp":
            host, _, port = rest.rpartition(":")
            if 0 < int(port) < 65536:
                return "udp", host or "0.0.0.0", int(port)
    except ValueError:
        pass
    raise ValueError(f"GPS address {url!r}: expected serial:/dev/<port>:<baud>, tcp:<host>:<port> "
                     "or udp:<port>")


class Stream:
    """A byte stream from a GPS: read() returns what has arrived (b"" when nothing did
    within the timeout); a lost connection raises (OSError / ConnectionError / the serial
    error), so a node can exit and be restarted. write() exists for the opt-in
    configuration only (not on UDP).
    """

    def __init__(self, url: str, timeout: float = 2.0):
        self.kind, self.addr, self.port = parse_stream_url(url)
        self.url = url
        self._s = self._sock = None
        if self.kind == "serial":
            import serial
            self._s = serial.Serial(self.addr, self.port, timeout=timeout)
        elif self.kind == "tcp":
            self._sock = socket.create_connection((self.addr, self.port), timeout=timeout)
            self._sock.settimeout(timeout)
        else:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.addr, self.port))
            self._sock.settimeout(timeout)

    def read(self) -> bytes:
        if self._s is not None:
            return self._s.read(self._s.in_waiting or 1)
        try:
            if self.kind == "tcp":
                data = self._sock.recv(4096)
                if not data:
                    raise ConnectionError(f"{self.url}: connection closed by the GPS")
                return data
            return self._sock.recvfrom(65535)[0]
        except socket.timeout:
            return b""

    def write(self, data: bytes) -> None:
        if self._s is not None:
            self._s.write(data)
        elif self.kind == "tcp":
            self._sock.sendall(data)
        else:
            raise OSError("cannot write to a UDP GPS stream")

    def close(self) -> None:
        for x in (self._s, self._sock):
            try:
                if x is not None:
                    x.close()
            except OSError:
                pass
