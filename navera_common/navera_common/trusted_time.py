"""Trusted UTC time for the celestial solver (hazard H-08, problems log F27).

A star fix is ~0.46 km off per second of clock error (28 km per minute). The Jetson has no
battery clock: it boots on the last saved time (16 h off on 2026-10-21) and steps when NTP
reaches the internet, possibly mid-mission. Operating rule (2026-10-22): GPS is always good at
take-off, then may be lost for hours. So the time comes, in this order, from:

  gnss       the GPS ANCHOR: UTC from a trusted GNSS fix (gps_pkg: UBX NAV-PVT with validDate,
             validTime and fullyResolved; NMEA RMC status A / ZDA with a valid fix), held as
             (UTC - monotonic clock) and carried by the monotonic clock afterwards, so it
             survives the loss of the GPS for hours AND a step of the system clock. Only a
             sample the caller says is trusted (the estimator elects the GPS: not refused, not
             suspected of spoofing) may anchor. The first anchor is kept; a later trusted sample
             refreshes it only when it agrees with the first one (within gnss_sigma_s plus the
             clock drift since): a spoofed GPS cannot walk the time away, its jumps are counted
             and reported (on_event "gnss_jump").
  autopilot  the autopilot's MAVLink SYSTEM_TIME (time_unix_usec; ArduPilot sets it from its GPS
             and keeps it while powered): a recent sample (autopilot_max_age_s). It is also the
             cross-check of the anchor: when both exist and disagree by more than crosscheck_s
             (1 s), NO time is trusted (one of them is wrong) and on_event "disagree" alarms.
  rtc        the DS3231 (rtc_pkg, optional): a recent reading whose status says valid and not
             lost_power.
  phone      the field-test phone's clock (navera_tools/field/server.py only).
  ntp        the system clock when NTP-synchronised (timedatectl NTPSynchronized=yes).

Every source has a stated 1-sigma uncertainty that grows with the time since its sample at
drift_ppm (the Jetson's crystal: a few ppm, 20 ppm stated until measured); a source whose
uncertainty exceeds max_sigma_s is not used. status() says which source is used, its
uncertainty, the anchor's age and jumps, and the anchor-minus-autopilot difference.

The anchor is NOT valid across a reboot: the monotonic clock restarts and there is no battery
clock to carry it, so it is never persisted. A Jetson that reboots mid-flight with the GPS
denied falls back to the autopilot's SYSTEM_TIME (the autopilot keeps time while powered), or
the DS3231 when one is fitted, else it has no trusted time and does not solve.

System-clock instants (frame stamps) are converted through the current wall-minus-monotonic
difference. A wall-clock step (that difference moving by more than step_tolerance_s) therefore
does not touch the anchor or the other samples (they are held on the monotonic clock), but a
frame stamped before the step is on the old clock: for settle_s after a step no time is given
for a stamp, and NTP is asked again. No ROS here: the nodes feed it.
"""
import subprocess
import time
from typing import Callable, Dict, Optional, Tuple

SOURCES = ("gnss", "autopilot", "rtc", "phone", "ntp")


def timedatectl_ntp_synced() -> bool:
    """True when systemd-timesyncd / chrony report the clock synchronised (no root needed)."""
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                             capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return out == "yes"


class TrustedClock:
    """UTC epoch seconds only when an independent source vouches for it, with its uncertainty."""

    def __init__(self, rtc_max_age_s: float = 5.0, autopilot_max_age_s: float = 5.0,
                 phone_max_age_s: float = 30.0, step_tolerance_s: float = 1.0,
                 ntp_check_s: float = 30.0, settle_s: float = 60.0, drift_ppm: float = 20.0,
                 gnss_sigma_s: float = 0.5, autopilot_sigma_s: float = 0.2, rtc_sigma_s: float = 1.0,
                 phone_sigma_s: float = 0.5, ntp_sigma_s: float = 0.1, max_sigma_s: float = 5.0,
                 crosscheck_s: float = 1.0,
                 ntp_synced: Callable[[], bool] = timedatectl_ntp_synced,
                 wall: Callable[[], float] = time.time, mono: Callable[[], float] = time.monotonic,
                 on_step: Optional[Callable[[float], None]] = None,
                 on_event: Optional[Callable[[str, str], None]] = None):
        self.max_age = {"autopilot": float(autopilot_max_age_s), "rtc": float(rtc_max_age_s),
                        "phone": float(phone_max_age_s)}
        self.sigma0 = {"gnss": float(gnss_sigma_s), "autopilot": float(autopilot_sigma_s),
                       "rtc": float(rtc_sigma_s), "phone": float(phone_sigma_s), "ntp": float(ntp_sigma_s)}
        self.step_tolerance_s, self.ntp_check_s = float(step_tolerance_s), float(ntp_check_s)
        self.settle_s, self.drift = float(settle_s), float(drift_ppm) * 1e-6
        self.max_sigma_s, self.crosscheck_s = float(max_sigma_s), float(crosscheck_s)
        self._ntp_synced, self._wall, self._mono = ntp_synced, wall, mono
        self._on_step, self._on_event = on_step, on_event
        self._wall_minus_mono = wall() - mono()
        self._samples: Dict[str, Tuple[float, float]] = {}   # source -> (UTC - mono, mono of the sample)
        self._rtc_ok = None         # (valid and not lost_power, mono at reception) of the last status
        self._ntp = (False, None)   # (synchronised, mono of the check)
        # the GPS anchor: first (UTC - mono, mono), latest agreeing (UTC - mono, mono)
        self._anchor_first: Optional[Tuple[float, float]] = None
        self._anchor: Optional[Tuple[float, float]] = None
        self.gnss_jumps, self.last_jump_s, self._in_jump = 0, None, False
        self.gnss_untrusted, self.last_untrusted = 0, ""
        self._disagree = False
        self.last_step_s = None     # size of the last wall-clock step seen (s)
        self._step_mono = None      # mono when it was seen
        self.steps = 0

    def _event(self, kind: str, text: str) -> None:
        if self._on_event is not None:
            self._on_event(kind, text)

    def _to_mono(self, system_epoch: float) -> float:
        return float(system_epoch) - self._wall_minus_mono

    # ── inputs ────────────────────────────────────────────────────────
    def check_step(self) -> bool:
        """True when the wall clock stepped since the last check (NTP is asked again)."""
        w = self._wall() - self._mono()
        step = w - self._wall_minus_mono
        self._wall_minus_mono = w
        if abs(step) <= self.step_tolerance_s:
            return False
        self._ntp = (False, None)
        self.last_step_s, self.steps, self._step_mono = step, self.steps + 1, self._mono()
        if self._on_step is not None:
            self._on_step(step)
        return True

    def _add(self, src: str, utc_epoch: float, system_epoch: float) -> None:
        self.check_step()
        self._samples[src] = (float(utc_epoch) - self._to_mono(system_epoch), self._mono())

    def add_rtc(self, rtc_epoch: float, system_epoch_at_read: float) -> None:
        """A DS3231 reading (rtc_time: time_ref, header.stamp = system clock at the read)."""
        self._add("rtc", rtc_epoch, system_epoch_at_read)

    def add_rtc_status(self, valid: bool, lost_power: bool) -> None:
        """The clock node's health (rtc_status JSON)."""
        self.check_step()
        self._rtc_ok = (bool(valid) and not bool(lost_power), self._mono())

    def add_autopilot(self, utc_epoch: float, system_epoch_at_receipt: float) -> None:
        """The autopilot's SYSTEM_TIME.time_unix_usec (vehicle_link: /navera/vehicle/system_time)."""
        self._add("autopilot", utc_epoch, system_epoch_at_receipt)

    def add_phone(self, utc_epoch: float, system_epoch_at_receipt: float) -> None:
        """The field-test phone's clock (GPS / network time)."""
        self._add("phone", utc_epoch, system_epoch_at_receipt)

    def add_gnss(self, gnss_epoch: float, system_epoch_at_receipt: float, trusted: bool = True,
                 why_untrusted: str = "") -> bool:
        """A GNSS receiver UTC (TimeReference: time_ref = GNSS UTC, header.stamp = system clock).

        Anchors (or refreshes the anchor) only when trusted and, after the first anchor, only when it
        agrees with it. Returns True when the sample was used.
        """
        self.check_step()
        if not trusted:
            self.gnss_untrusted += 1
            self.last_untrusted = why_untrusted or "GPS not trusted"
            return False
        umm, now = float(gnss_epoch) - self._to_mono(system_epoch_at_receipt), self._mono()
        if self._anchor_first is None:
            self._anchor_first = self._anchor = (umm, now)
            self._event("anchor", f"time anchored on the GPS (UTC - system clock {umm - self._wall_minus_mono:+.3f} s)")
            return True
        first, t0 = self._anchor_first
        tol = self.sigma0["gnss"] + self.drift * (now - t0)
        diff = umm - first
        if abs(diff) <= tol:
            self._anchor = (umm, now)
            if self._in_jump:
                self._in_jump = False
                self._event("gnss_agree", "GPS time agrees with the anchor again")
            return True
        self.gnss_jumps += 1
        self.last_jump_s = umm - self._anchor[0]
        if not self._in_jump:
            self._in_jump = True
            self._event("gnss_jump", f"GPS time jumped {self.last_jump_s:+.3f} s from the anchor "
                                     f"(tolerance {tol:.3f} s): anchor kept (spoofed or faulty GPS?)")
        return False

    # ── output ────────────────────────────────────────────────────────
    def _ntp_ok(self) -> bool:
        synced, at = self._ntp
        now = self._mono()
        if at is None or now - at > self.ntp_check_s:
            synced = bool(self._ntp_synced())
            self._ntp = (synced, now)
        return synced

    def _candidate(self, src: str, now: float) -> Tuple[Optional[Tuple[float, float]], str]:
        """((UTC - mono, sigma) or None, why not) for one source."""
        if src == "gnss":
            if self._anchor is None:
                return None, ("no GPS time anchor (no trusted GPS fix since boot; "
                              "an anchor does not survive a reboot)")
            umm, at = self._anchor
        elif src == "ntp":
            if not self._ntp_ok():
                return None, "system clock not NTP-synchronised"
            return (self._wall_minus_mono, self.sigma0["ntp"]), ""
        else:
            s = self._samples.get(src)
            names = {"autopilot": "no autopilot SYSTEM_TIME",
                     "rtc": "no valid DS3231 reading (absent, lost power or not UTC)", "phone": "no phone clock"}
            if s is None:
                return None, names[src]
            umm, at = s
            if now - at > self.max_age[src]:
                return None, f"{names[src]} in the last {self.max_age[src]:.0f} s"
            if src == "rtc" and not (self._rtc_ok is not None and self._rtc_ok[0]
                                     and now - self._rtc_ok[1] <= self.max_age["rtc"]):
                return None, names["rtc"]
        sigma = self.sigma0[src] + self.drift * max(0.0, now - at)
        if sigma > self.max_sigma_s:
            return None, f"{src} time uncertainty {sigma:.2f} s > {self.max_sigma_s:.1f} s"
        return (umm, sigma), ""

    def best(self) -> Tuple[Optional[float], str, Optional[float]]:
        """(UTC - monotonic clock, source, 1-sigma s) of the first source that vouches, else (None, why, None)."""
        self.check_step()
        now = self._mono()
        why = []
        for src in SOURCES:
            got, reason = self._candidate(src, now)
            if got is None:
                why.append(reason)
                continue
            umm, sigma = got
            if src == "gnss":
                ap, _ = self._candidate("autopilot", now)
                if ap is not None and abs(umm - ap[0]) > self.crosscheck_s:
                    msg = (f"no trusted time: the GPS anchor and the autopilot's SYSTEM_TIME disagree by "
                           f"{umm - ap[0]:+.2f} s (> {self.crosscheck_s:.1f} s): one is wrong (spoofed GPS?)")
                    if not self._disagree:
                        self._disagree = True
                        self._event("disagree", msg)
                    return None, msg, None
                self._disagree = False
            return umm, src, sigma
        if self.last_step_s is not None:
            why.append(f"system clock stepped {self.last_step_s:+.1f} s")
        return None, "no trusted time: " + "; ".join(why), None

    def offset_sigma(self) -> Tuple[Optional[float], str, Optional[float]]:
        """(seconds to add to the system clock for UTC, source, 1-sigma s) or (None, why, None)."""
        umm, src, sigma = self.best()
        if umm is None:
            return None, src, None
        now = self._mono()
        if self._step_mono is not None and now - self._step_mono < self.settle_s:
            return None, (f"no trusted time: the system clock stepped {self.last_step_s:+.1f} s "
                          f"{now - self._step_mono:.0f} s ago (frames stamped before it are on the old clock)"), None
        return umm - self._wall_minus_mono, src, sigma

    def offset(self) -> Tuple[Optional[float], str]:
        """(seconds to add to the system clock for UTC, source) or (None, why there is no trusted time)."""
        off, src, _ = self.offset_sigma()
        return off, src

    def utc(self, system_epoch: Optional[float] = None) -> Tuple[Optional[float], str]:
        """(trusted UTC epoch of a system-clock instant (default: now), source) or (None, reason)."""
        off, src = self.offset()
        if off is None:
            return None, src
        return (self._wall() if system_epoch is None else float(system_epoch)) + off, src

    def status(self) -> dict:
        """What the status page / time_status topic shows: source, uncertainty, anchor, cross-check."""
        off, src, sigma = self.offset_sigma()
        now = self._mono()
        out = {"trusted": off is not None, "source": src if off is not None else None,
               "sigma_s": None if sigma is None else round(sigma, 3),
               "offset_s": None if off is None else round(off, 3),
               "reason": "" if off is not None else src, "steps": self.steps,
               "last_step_s": self.last_step_s}
        if self._anchor is not None:
            umm, at = self._anchor
            a = {"age_s": round(now - self._anchor_first[1], 1), "refreshed_s_ago": round(now - at, 1),
                 "sigma_s": round(self.sigma0["gnss"] + self.drift * (now - at), 3),
                 "jumps": self.gnss_jumps, "last_jump_s": self.last_jump_s}
            ap, _ = self._candidate("autopilot", now)
            a["minus_autopilot_s"] = None if ap is None else round(umm - ap[0], 3)
            out["anchor"] = a
        else:
            out["anchor"] = None
        out["gnss_untrusted"] = self.gnss_untrusted
        if self.gnss_untrusted:
            out["gnss_untrusted_why"] = self.last_untrusted
        out["sources"] = {s: (self._candidate(s, now)[0] is not None) for s in SOURCES if s != "ntp"}
        return out
