"""The DS3231 battery clock as a trusted time for the field server's star solves (F27), without ROS or extra packages.

The Jetson has no battery clock of its own (its PMIC RTC resets with the power): it boots on the last saved time
(16 h off on 2026-10-21) until NTP or the phone sets it, and a star fix is ~28 km off per minute of clock error.
A DS3231 module on the 40-pin header keeps UTC through power cuts (TCXO, +-2 ppm). This reads it directly:

  i2c     /dev/i2c-<bus>, address 0x68 (the same chip rtc_pkg's rtc_node reads; the user is in the i2c group, no
          root): time registers 0x00-0x06 (BCD) and the status register 0x0F (bit 7 OSF = the oscillator stopped:
          it lost power since it was set, its time is not trusted);
  kernel  if a kernel driver owns the chip (rtc-ds1307, shown as UU by i2cdetect), /sys/class/rtc/rtcN whose name
          says ds1307/ds3231: since_epoch (the driver refuses to read a chip whose oscillator stopped).

The DS3231 counts whole seconds. Reading it at a random moment is up to 1 s late (0.46 km); the reader polls until
the seconds register ticks and stamps the system clock at that edge (a few ms), once a minute.

A reading counts only when: the oscillator did not stop, the year is >= 2024, it is not a whole number of hours from
the system clock (an RTC set to local time: 1 h = 15 deg of longitude), and the system clock has not stepped since
(a step makes the measured offset wrong; the next reading is taken at once). The DS3231 must hold UTC: set it once
from a synchronised clock (rtc_pkg README; `python3 -m navera_tools.field.rtc_clock --set-from-system` does it
over I2C when the system clock is NTP-synchronised).

    python3 -m navera_tools.field.rtc_clock [--bus 1]             # read it, print the offset to the system clock
"""
import argparse
import fcntl
import glob
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

ADDRESS = 0x68
I2C_SLAVE = 0x0703
MIN_YEAR = 2024
POLL_S = 60.0                 # a new edge-synced reading every minute
MAX_AGE_S = 180.0             # a reading older than this no longer vouches
STEP_TOLERANCE_S = 1.0        # wall clock minus monotonic clock moving by more = a clock step


def _bcd(v: int) -> int:
    return (v >> 4) * 10 + (v & 0x0F)


def _to_bcd(v: int) -> int:
    return ((v // 10) << 4) | (v % 10)


def decode(regs: bytes) -> Optional[datetime]:
    """UTC datetime from the 7 time registers (seconds .. year), None for a date that is not a date."""
    try:
        sec, mins = _bcd(regs[0] & 0x7F), _bcd(regs[1] & 0x7F)
        h = regs[2]
        if h & 0x40:                                   # 12-hour mode
            hour = _bcd(h & 0x1F) % 12 + (12 if h & 0x20 else 0)
        else:
            hour = _bcd(h & 0x3F)
        day, month = _bcd(regs[4] & 0x3F), _bcd(regs[5] & 0x1F)
        year = 2000 + _bcd(regs[6]) + (100 if regs[5] & 0x80 else 0)
        return datetime(year, month, day, hour, mins, sec, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


class I2cDevice:
    """Raw Linux I2C access to the DS3231 (no smbus package needed)."""

    def __init__(self, bus: int = 1, address: int = ADDRESS):
        self.path = f"/dev/i2c-{bus}"
        self.fd = os.open(self.path, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)

    def read(self, reg: int, n: int) -> bytes:
        os.write(self.fd, bytes([reg]))
        return os.read(self.fd, n)

    def write(self, reg: int, data: bytes):
        os.write(self.fd, bytes([reg]) + bytes(data))

    def close(self):
        os.close(self.fd)


def kernel_rtc(root: str = "/sys/class/rtc") -> Optional[str]:
    """The sysfs folder of a kernel-bound DS3231 (rtc-ds1307 driver), or None. Never the Jetson's own RTCs."""
    for d in sorted(glob.glob(os.path.join(root, "rtc*"))):
        try:
            name = open(os.path.join(d, "name")).read().strip().lower()
        except OSError:
            continue
        if "ds1307" in name or "ds3231" in name:
            return d
    return None


class RtcClock:
    """Edge-synced DS3231 readings and the offset they give to the system clock (see the module doc).

    reader() -> (rtc epoch at a seconds tick, system epoch at that tick, lost_power) or raises OSError; injected
    in tests (a fake RTC). By default: the kernel device if one is bound, else I2C bus `bus`.
    """

    def __init__(self, bus: int = 1, reader: Optional[Callable[[], Tuple[float, float, bool]]] = None,
                 wall: Callable[[], float] = time.time, mono: Callable[[], float] = time.monotonic,
                 sysfs_root: str = "/sys/class/rtc"):
        self.bus, self.wall, self.mono, self.sysfs_root = bus, wall, mono, sysfs_root
        self._reader = reader
        self.last: dict = {"ok": False, "why": "not read yet"}
        self._t_read = None                        # mono of the last good reading
        self._wall_minus_mono = wall() - mono()
        self._lock = threading.Lock()
        self.kind = "injected" if reader is not None else None

    # ── reading ───────────────────────────────────────────────────────
    def _default_reader(self) -> Tuple[float, float, bool]:
        k = kernel_rtc(self.sysfs_root)
        if k is not None:
            self.kind = f"kernel {os.path.basename(k)}"
            path = os.path.join(k, "since_epoch")
            first = int(open(path).read())
            deadline = self.wall() + 1.3
            while self.wall() < deadline:            # wait for the next tick
                v = int(open(path).read())
                if v != first:
                    return float(v), self.wall(), False
                time.sleep(0.005)
            raise OSError("kernel RTC did not tick in 1.3 s")
        dev = I2cDevice(self.bus)
        self.kind = f"i2c-{self.bus} 0x68"
        try:
            lost = bool(dev.read(0x0F, 1)[0] & 0x80)
            first = dev.read(0x00, 1)[0]
            deadline = self.wall() + 1.3
            while self.wall() < deadline:
                regs = dev.read(0x00, 7)
                t_sys = self.wall()
                if regs[0] != first:
                    d = decode(regs)
                    if d is None:
                        raise OSError(f"DS3231 date is not a date: {regs.hex()}")
                    return d.timestamp(), t_sys, lost
                time.sleep(0.003)
            raise OSError("DS3231 seconds did not tick in 1.3 s (oscillator stopped?)")
        finally:
            dev.close()

    def _stepped(self) -> bool:
        w = self.wall() - self.mono()
        step = w - self._wall_minus_mono
        self._wall_minus_mono = w
        return abs(step) > STEP_TOLERANCE_S

    def read(self) -> dict:
        """Take one reading now; returns and keeps the status dict ('ok', 'offset_s' = RTC - system, 'why')."""
        self._stepped()
        try:
            rtc, sys_t, lost = (self._reader or self._default_reader)()
        except (OSError, ValueError) as e:
            st = {"ok": False, "why": f"no DS3231: {e}"[:160], "kind": self.kind}
        else:
            off = rtc - sys_t
            year = datetime.fromtimestamp(rtc, tz=timezone.utc).year
            hours = round(off / 3600.0)
            why = None
            if lost:
                why = "DS3231 lost power since it was set (oscillator stop flag): its time is not trusted"
            elif year < MIN_YEAR:
                why = f"DS3231 says {year}: not set"
            elif hours != 0 and abs(hours) <= 14 and abs(off - hours * 3600.0) <= 1.5:      # time zones: -12..+14 h
                why = f"DS3231 is {hours:+d} h from the system clock: it holds local time, not UTC"
            st = {"ok": why is None, "why": why, "offset_s": round(off, 3), "kind": self.kind,
                  "rtc_utc": datetime.fromtimestamp(rtc, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
        with self._lock:
            self.last = st
            self._t_read = self.mono() if st["ok"] else None
        return st

    def offset(self) -> Tuple[Optional[float], str]:
        """(UTC - system clock in s, "rtc ...") from the last good reading, or (None, why it does not vouch)."""
        if self._stepped():
            with self._lock:
                self._t_read = None
                self.last = {"ok": False, "why": "system clock stepped since the last DS3231 reading"}
            return None, self.last["why"]
        with self._lock:
            st, t = dict(self.last), self._t_read
        if not st.get("ok") or t is None:
            return None, st.get("why") or "no DS3231 reading"
        if self.mono() - t > MAX_AGE_S:
            return None, f"last DS3231 reading {self.mono() - t:.0f} s old"
        return float(st["offset_s"]), f"rtc ({st.get('kind')})"

    def run(self, stop: Optional[threading.Event] = None, poll_s: float = POLL_S):
        """Read every poll_s (sooner after a clock step) until stop is set; for a daemon thread."""
        stop = stop or threading.Event()
        while not stop.is_set():
            self.read()
            waited = 0.0
            while waited < poll_s and not stop.is_set():
                time.sleep(1.0)
                waited += 1.0
                if self.offset()[0] is None and self.last.get("why", "").startswith("system clock stepped"):
                    break

    def start(self) -> "RtcClock":
        threading.Thread(target=self.run, daemon=True, name="ds3231").start()
        return self


def set_from_system(bus: int = 1) -> str:
    """Write the system clock (UTC) to the DS3231 at a second's edge and clear its oscillator-stop flag. Refused
    unless the system clock is NTP-synchronised (a wrong system clock written to the RTC is worse than none)."""
    try:
        synced = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], capture_output=True,
                                text=True, timeout=3).stdout.strip() == "yes"
    except (OSError, subprocess.SubprocessError):
        synced = False
    if not synced:
        return "refused: the system clock is not NTP-synchronised (connect the Jetson to the internet first)"
    if kernel_rtc() is not None:
        return "a kernel driver owns the DS3231: use `sudo hwclock -w -u` instead"
    dev = I2cDevice(bus)
    try:
        t = time.time()
        time.sleep(1.0 - (t % 1.0))                       # write at the start of a second
        d = datetime.fromtimestamp(round(time.time()), tz=timezone.utc)
        dev.write(0x00, bytes([_to_bcd(d.second), _to_bcd(d.minute), _to_bcd(d.hour), _to_bcd(d.isoweekday()),
                               _to_bcd(d.day), _to_bcd(d.month) | (0x80 if d.year >= 2100 else 0),
                               _to_bcd(d.year % 100)]))
        status = dev.read(0x0F, 1)[0]
        dev.write(0x0F, bytes([status & 0x7F]))           # clear OSF
    finally:
        dev.close()
    return f"DS3231 set to {d.strftime('%Y-%m-%d %H:%M:%S')} UTC"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bus", type=int, default=1)
    ap.add_argument("--set-from-system", action="store_true", help="write the (NTP-synchronised) system UTC to it")
    a = ap.parse_args(argv)
    if a.set_from_system:
        print(set_from_system(a.bus))
    st = RtcClock(a.bus).read()
    print(st)
    return 0 if st.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
