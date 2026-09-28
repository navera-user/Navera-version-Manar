"""Simulated GPS receiver: NMEA 0183 on a pseudo-terminal, read by the REAL gps_node.

The receiver is driven by the simulator's true position and a fault mode:
    ok           fixes at the true position + receiver noise (random walk, ~1.5 m)
    jammed       the receiver keeps talking but has no fix (GGA quality 0, RMC V)
    spoof_jump   a spoofer takes over: positions suddenly 2 km away
    spoof_drift  a spoofer pulls the position away slowly (4 m/s)
    off          the receiver is silent (cable cut, power loss)
"""
import math
import os
import pty
import random
import tty
from datetime import datetime, timezone

M_PER_DEG = 111_320.0
MODES = ("ok", "jammed", "spoof_jump", "spoof_drift", "off")


def _cs(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"${body}*{c:02X}\r\n"


def _lat(v):
    a = abs(v)
    d = int(a)
    return f"{d:02d}{(a - d) * 60:07.4f}", "N" if v >= 0 else "S"


def _lon(v):
    a = abs(v)
    d = int(a)
    return f"{d:03d}{(a - d) * 60:07.4f}", "E" if v >= 0 else "W"


class NmeaGps:
    GEO_SEP_M = 33.0          # geoid separation around Sousse

    def __init__(self, seed=3):
        self.master, slave = pty.openpty()
        tty.setraw(slave)
        self.port = os.ttyname(slave)
        self._slave = slave                     # kept open so the pty stays alive
        os.set_blocking(self.master, False)
        self.mode = "ok"
        self.rng = random.Random(seed)
        self.noise = [0.0, 0.0]
        self.spoof = [0.0, 0.0]
        self.sats = 12

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError(mode)
        if mode != self.mode:
            self.spoof = [0.0, 0.0]
            if mode == "spoof_jump":
                ang = self.rng.uniform(0, 2 * math.pi)
                self.spoof = [2000.0 * math.cos(ang), 2000.0 * math.sin(ang)]
        self.mode = mode

    def _write(self, text):
        try:
            os.write(self.master, text.encode("ascii"))
        except (BlockingIOError, OSError):
            pass                                  # nobody reading: drop, like a UART

    def reported(self, lat, lon, dt):
        """Position the receiver reports (truth + noise + spoofing)."""
        for i in (0, 1):                          # first-order Gauss-Markov noise
            self.noise[i] += -self.noise[i] * dt / 20.0 + self.rng.gauss(0, 0.6) * math.sqrt(dt)
        if self.mode == "spoof_drift":
            self.spoof[0] += 4.0 * dt * 0.8
            self.spoof[1] += 4.0 * dt * 0.6
        e, n = self.noise[0] + self.spoof[0], self.noise[1] + self.spoof[1]
        return (lat + n / M_PER_DEG,
                lon + e / (M_PER_DEG * math.cos(math.radians(lat))))

    def tick(self, lat, lon, alt_msl, speed_mps, course_deg, dt):
        """Emit one GGA + RMC epoch. Returns the reported (lat, lon) or None."""
        if self.mode == "off":
            return None
        t = datetime.now(timezone.utc)
        hms = t.strftime("%H%M%S.") + f"{t.microsecond // 10000:02d}"
        dmy = t.strftime("%d%m%y")
        if self.mode == "jammed":
            self._write(_cs(f"GPGGA,{hms},,,,,0,00,99.9,,M,,M,,"))
            self._write(_cs(f"GPRMC,{hms},V,,,,,,,{dmy},,,N"))
            return None
        rlat, rlon = self.reported(lat, lon, dt)
        la, ns = _lat(rlat)
        lo, ew = _lon(rlon)
        self._write(_cs(f"GPGGA,{hms},{la},{ns},{lo},{ew},1,{self.sats:02d},0.7,"
                        f"{alt_msl:.1f},M,{self.GEO_SEP_M:.1f},M,,"))
        self._write(_cs(f"GPRMC,{hms},A,{la},{ns},{lo},{ew},{speed_mps / 0.514444:.2f},"
                        f"{course_deg % 360:.1f},{dmy},,,A"))
        return rlat, rlon

    def close(self):
        for fd in (self.master, self._slave):
            try:
                os.close(fd)
            except OSError:
                pass
