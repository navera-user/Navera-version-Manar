"""Trusted UTC time for the celestial solver (hazard H-08, problems log F27).

A star fix is ~28 km off per minute of clock error. A Jetson without a battery clock boots on
the last saved time (16 h off on 2026-10-21) and steps when NTP reaches the internet, possibly
mid-mission. The system clock is therefore used only when something vouches for it:

  rtc   the DS3231 node (rtc_pkg) published a time recently and its latest status says
        valid and not lost_power: the RTC time is used (carried by the system clock since
        the read)
  gnss  a GNSS receiver time (sensor_msgs/TimeReference) arrived within gnss_max_age_s:
        the system clock corrected by the offset measured then
  ntp   the system clock is NTP-synchronised (timedatectl NTPSynchronized=yes)

and only when the wall clock has not stepped since that evidence was taken: a step (wall
clock minus monotonic clock moving by more than step_tolerance_s) discards every earlier RTC
and GNSS sample and re-asks NTP, and for settle_s after it no time is trusted (a frame exposed
before the step carries a stamp on the old clock). Without any of them there is no trusted time, and the caller
must not solve (the reason says why). Same rule as the field server (db2f95c,
navera_tools/field/server.py star_clock_offset_s / _clock_jumped). No ROS here: the node feeds it.
"""
import subprocess
import time
from typing import Callable, Optional, Tuple


def timedatectl_ntp_synced() -> bool:
    """True when systemd-timesyncd / chrony report the clock synchronised (no root needed)."""
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                             capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return out == "yes"


class TrustedClock:
    """UTC epoch seconds only when an independent source vouches for the system clock."""

    def __init__(self, rtc_max_age_s: float = 5.0, gnss_max_age_s: float = 300.0,
                 step_tolerance_s: float = 1.0, ntp_check_s: float = 30.0, settle_s: float = 60.0,
                 ntp_synced: Callable[[], bool] = timedatectl_ntp_synced,
                 wall: Callable[[], float] = time.time, mono: Callable[[], float] = time.monotonic,
                 on_step: Optional[Callable[[float], None]] = None):
        self.rtc_max_age_s, self.gnss_max_age_s = float(rtc_max_age_s), float(gnss_max_age_s)
        self.step_tolerance_s, self.ntp_check_s = float(step_tolerance_s), float(ntp_check_s)
        self.settle_s = float(settle_s)
        self._ntp_synced, self._wall, self._mono, self._on_step = ntp_synced, wall, mono, on_step
        self._wall_minus_mono = wall() - mono()
        self._rtc = None            # (rtc epoch, system epoch at the read, mono at reception)
        self._rtc_ok = None         # (valid and not lost_power, mono at reception) of the last status
        self._gnss = None           # (gnss epoch - system epoch, mono at reception)
        self._ntp = (False, None)   # (synchronised, mono of the check)
        self.last_step_s = None     # size of the last wall-clock step seen (s)
        self._step_mono = None      # mono when it was seen
        self.steps = 0

    # ── inputs ────────────────────────────────────────────────────────
    def check_step(self) -> bool:
        """True when the wall clock stepped since the last check: earlier evidence is dropped."""
        w = self._wall() - self._mono()
        step = w - self._wall_minus_mono
        self._wall_minus_mono = w
        if abs(step) <= self.step_tolerance_s:
            return False
        self._rtc, self._gnss, self._ntp = None, None, (False, None)
        self.last_step_s, self.steps, self._step_mono = step, self.steps + 1, self._mono()
        if self._on_step is not None:
            self._on_step(step)
        return True

    def add_rtc(self, rtc_epoch: float, system_epoch_at_read: float) -> None:
        """A DS3231 reading (rtc_time: time_ref, header.stamp = system clock at the read)."""
        self.check_step()
        self._rtc = (float(rtc_epoch), float(system_epoch_at_read), self._mono())

    def add_rtc_status(self, valid: bool, lost_power: bool) -> None:
        """The clock node's health (rtc_status JSON)."""
        self.check_step()
        self._rtc_ok = (bool(valid) and not bool(lost_power), self._mono())

    def add_gnss(self, gnss_epoch: float, system_epoch_at_receipt: float) -> None:
        """A GNSS receiver time (TimeReference: time_ref = GNSS UTC, header.stamp = system clock)."""
        self.check_step()
        self._gnss = (float(gnss_epoch) - float(system_epoch_at_receipt), self._mono())

    # ── output ────────────────────────────────────────────────────────
    def _ntp_ok(self) -> bool:
        synced, at = self._ntp
        now = self._mono()
        if at is None or now - at > self.ntp_check_s:
            synced = bool(self._ntp_synced())
            self._ntp = (synced, now)
        return synced

    def offset(self) -> Tuple[Optional[float], str]:
        """(seconds to add to the system clock for UTC, source) or (None, why there is no trusted time)."""
        self.check_step()
        now = self._mono()
        if self._step_mono is not None and now - self._step_mono < self.settle_s:
            return None, (f"no trusted time: the system clock stepped {self.last_step_s:+.1f} s "
                          f"{now - self._step_mono:.0f} s ago (frames stamped before it are on the old clock)")
        if self._rtc is not None and now - self._rtc[2] <= self.rtc_max_age_s:
            ok = self._rtc_ok is not None and self._rtc_ok[0] and now - self._rtc_ok[1] <= self.rtc_max_age_s
            if ok:
                return self._rtc[0] - self._rtc[1], "rtc"
        if self._gnss is not None and now - self._gnss[1] <= self.gnss_max_age_s:
            return self._gnss[0], "gnss"
        if self._ntp_ok():
            return 0.0, "ntp"
        why = ["no trusted time: no valid RTC reading (DS3231 absent, lost power or not UTC)",
               f"no GNSS time in the last {self.gnss_max_age_s:.0f} s", "system clock not NTP-synchronised"]
        if self.last_step_s is not None:
            why.append(f"system clock stepped {self.last_step_s:+.1f} s")
        return None, "; ".join(why)

    def utc(self, system_epoch: Optional[float] = None) -> Tuple[Optional[float], str]:
        """(trusted UTC epoch of a system-clock instant (default: now), source) or (None, reason)."""
        off, src = self.offset()
        if off is None:
            return None, src
        return (self._wall() if system_epoch is None else float(system_epoch)) + off, src
