"""Optional time sources of the field server: NAVERA's GPS receiver and the autopilot's SYSTEM_TIME.

The field server (server.py) gives a star solve the time of navera_common.trusted_time.TrustedClock in
the product's order: GPS anchor > autopilot SYSTEM_TIME > DS3231 > phone > NTP. These two feeds are off
unless their address is set (both read-only; nothing is sent to a receiver, and only a message-rate
request to the autopilot):

  NAVERA_FIELD_GPS      the GPS stream, as gps_node takes it (serial:/dev/ttyACM0:38400, tcp:host:port,
                        udp:port): UBX NAV-PVT (validDate + validTime + fullyResolved, with a fix), NMEA RMC
                        status A, ZDA within ZDA_FIX_MAX_AGE_S of a valid fix. Do not point it at a port a
                        running gps_node holds.
  NAVERA_FIELD_MAVLINK  the autopilot (pymavlink address, e.g. udpin:0.0.0.0:14552): SYSTEM_TIME at 1 Hz.

There is no estimator in the field server, so "trusted GPS" means here: a satellite fix, and, while the
phone shares a GPS position, within GPS_PHONE_MAX_KM of it (a gross spoof or a wrong receiver is refused).
"""
import math
import threading
import time
from typing import Callable, List, Optional, Tuple

from navera_common.gnss import (NAV, NAV_DOP, NAV_PVT, Stream, StreamDecoder, parse_nav_dop, parse_nav_pvt,
                                pvt_fix, rmc_utc_epoch, zda_utc_epoch)

ZDA_FIX_MAX_AGE_S = 2.0
GPS_PHONE_MAX_KM = 2.0
MIN_UNIX_TIME_S = 1_577_836_800          # 2020-01-01: an autopilot below it has no real time


class GnssTimeParser:
    """Bytes of a GPS stream -> [(UTC epoch, lat, lon)] for the samples whose time the receiver vouches for."""

    def __init__(self, mono: Callable[[], float] = time.monotonic):
        self.dec, self.mono = StreamDecoder(), mono
        self._dop = None
        self._fix_t = -1e9
        self._pos: Tuple[Optional[float], Optional[float]] = (None, None)

    def feed(self, data: bytes) -> List[Tuple[float, Optional[float], Optional[float]]]:
        import pynmea2
        out = []
        for item in self.dec.feed(data):
            if item[0] == "ubx":
                _, cls, mid, payload = item
                if cls != NAV:
                    continue
                if mid == NAV_DOP:
                    self._dop = parse_nav_dop(payload)
                elif mid == NAV_PVT:
                    pvt = parse_nav_pvt(payload)
                    fix = pvt_fix(pvt, self._dop) if pvt is not None else None
                    if fix is not None and fix.valid:
                        self._fix_t, self._pos = self.mono(), (fix.lat, fix.lon)
                        if fix.utc is not None and math.isfinite(fix.utc) and fix.utc > 0:
                            out.append((float(fix.utc), fix.lat, fix.lon))
                continue
            try:
                msg = pynmea2.parse(item[1], check=True)
            except pynmea2.ParseError:
                continue
            if isinstance(msg, pynmea2.types.talker.GGA):
                try:
                    ok = int(msg.gps_qual or 0) in (1, 2, 4, 5) and bool(msg.lat) and bool(msg.lon)
                except (TypeError, ValueError):
                    ok = False
                if ok:
                    self._fix_t, self._pos = self.mono(), (msg.latitude, msg.longitude)
            elif isinstance(msg, pynmea2.types.talker.RMC):
                t = rmc_utc_epoch(msg)
                if t is not None:
                    self._fix_t = self.mono()
                    if msg.lat and msg.lon:
                        self._pos = (msg.latitude, msg.longitude)
                    out.append((t, *self._pos))
            elif isinstance(msg, pynmea2.types.talker.ZDA):
                t = zda_utc_epoch(msg)
                if t is not None and self.mono() - self._fix_t <= ZDA_FIX_MAX_AGE_S:
                    out.append((t, *self._pos))
        return out


def phone_trust(phone: dict, phone_age_s: float, lat: Optional[float], lon: Optional[float]) -> Tuple[bool, str]:
    """(trusted, why not): the GPS position must be within GPS_PHONE_MAX_KM of a fresh phone GPS position."""
    if lat is None or lon is None:
        return False, "GPS time without a position"
    plat, plon, acc = phone.get("lat"), phone.get("lon"), phone.get("acc")
    if plat is None or plon is None or phone_age_s > 5.0 or (acc is not None and acc > 100):
        return True, ""
    r = 6371.0
    dlat, dlon = math.radians(lat - plat), math.radians(lon - plon)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(plat)) * math.cos(math.radians(lat)) * math.sin(dlon / 2) ** 2
    d = 2 * r * math.asin(min(1.0, math.sqrt(a)))
    if d > GPS_PHONE_MAX_KM:
        return False, f"NAVERA's GPS is {d:.1f} km from the phone's: not trusted"
    return True, ""


def autopilot_epoch(msg) -> Optional[float]:
    """SYSTEM_TIME.time_unix_usec as UTC epoch seconds, None while the autopilot has no real time."""
    usec = int(getattr(msg, "time_unix_usec", 0) or 0)
    return usec / 1e6 if usec >= MIN_UNIX_TIME_S * 1_000_000 else None


class _Feed:
    """A daemon thread that reads one source and reconnects after an error; .last says how it goes."""

    name = "feed"

    def __init__(self, url: str):
        self.url = url
        self.last = {"ok": False, "why": "not connected yet", "samples": 0}
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name=f"field-{self.name}").start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except Exception as e:                          # a lost port: say so and try again
                self.last.update(ok=False, why=f"{self.name}: {e!r}"[:160])
            self._stop.wait(5.0)


class GnssTimeFeed(_Feed):
    """NAVERA's GPS receiver -> on_sample(utc epoch, system epoch at receipt, lat, lon)."""

    name = "gps"

    def __init__(self, url: str, on_sample: Callable[[float, float, Optional[float], Optional[float]], None],
                 stream_factory: Callable[[str], object] = Stream):
        super().__init__(url)
        self.on_sample, self.stream_factory = on_sample, stream_factory

    def _session(self):
        s = self.stream_factory(self.url)
        parser = GnssTimeParser()
        try:
            while not self._stop.is_set():
                data = s.read()
                now = time.time()
                for utc, lat, lon in parser.feed(data):
                    self.last.update(ok=True, why="", samples=self.last["samples"] + 1,
                                     utc_minus_system_s=round(utc - now, 3))
                    self.on_sample(utc, now, lat, lon)
        finally:
            s.close()


class AutopilotTimeFeed(_Feed):
    """The autopilot's SYSTEM_TIME -> on_sample(utc epoch, system epoch at receipt)."""

    name = "autopilot"

    def __init__(self, url: str, on_sample: Callable[[float, float], None], connect=None):
        super().__init__(url)
        self.on_sample, self.connect = on_sample, connect

    def _session(self):
        if self.connect is None:
            from pymavlink import mavutil
            m = mavutil.mavlink_connection(self.url, source_system=1, source_component=193)
        else:
            m = self.connect(self.url)
        try:
            asked = 0.0
            while not self._stop.is_set():
                if time.monotonic() - asked > 30.0 and getattr(m, "target_system", 0):
                    asked = time.monotonic()
                    m.mav.command_long_send(m.target_system, m.target_component, 511, 0, 2, 1e6, 0, 0, 0, 0, 0)
                msg = m.recv_match(type=["SYSTEM_TIME", "HEARTBEAT"], blocking=True, timeout=1.0)
                if msg is None:
                    continue
                if msg.get_type() == "HEARTBEAT":
                    if getattr(msg, "autopilot", 8) != 8 and not getattr(m, "target_system", 0):
                        m.target_system, m.target_component = msg.get_srcSystem(), msg.get_srcComponent()
                    continue
                now = time.time()
                utc = autopilot_epoch(msg)
                if utc is None:
                    self.last.update(ok=False, why="the autopilot has no time yet (no GPS since it was powered)")
                    continue
                self.last.update(ok=True, why="", samples=self.last["samples"] + 1,
                                 utc_minus_system_s=round(utc - now, 3))
                self.on_sample(utc, now)
        finally:
            m.close()
