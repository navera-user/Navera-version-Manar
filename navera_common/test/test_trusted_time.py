"""Unit tests for navera_common.trusted_time (hazard H-08: celestial solves only on a trusted time)."""
import pytest

from navera_common.trusted_time import TrustedClock


class Clocks:
    """A wall clock and a monotonic clock the test moves by hand."""

    def __init__(self):
        self.w, self.m, self.ntp, self.ntp_calls = 1_800_000_000.0, 100.0, False, 0

    def wall(self):
        return self.w

    def mono(self):
        return self.m

    def synced(self):
        self.ntp_calls += 1
        return self.ntp

    def tick(self, s):
        self.w += s
        self.m += s


def _clock(c, **kw):
    return TrustedClock(ntp_synced=c.synced, wall=c.wall, mono=c.mono, **kw)


def test_no_source_means_no_trusted_time():
    """F27: a box without a battery clock, GPS, autopilot or internet must not solve."""
    c = Clocks()
    off, why = _clock(c).offset()
    assert off is None and "no trusted time" in why and "NTP" in why and "GPS time anchor" in why


def test_a_valid_rtc_gives_its_time():
    c = Clocks()
    t = _clock(c)
    t.add_rtc_status(valid=True, lost_power=False)
    t.add_rtc(c.w + 3600.0, c.w)                       # the system clock is 1 h behind the RTC
    c.tick(2.0)
    utc, src = t.utc()
    assert src == "rtc" and utc == c.w + 3600.0
    c.tick(10.0)                                       # the RTC node went silent
    assert t.offset()[0] is None


def test_an_rtc_that_lost_power_or_is_invalid_is_not_trusted():
    c = Clocks()
    t = _clock(c)
    t.add_rtc(c.w, c.w)
    assert t.offset()[0] is None                       # no status yet
    t.add_rtc_status(valid=True, lost_power=True)
    assert t.offset()[0] is None
    t.add_rtc_status(valid=False, lost_power=False)
    assert t.offset()[0] is None


def test_the_gps_anchor_holds_for_hours_without_gps_and_its_uncertainty_grows():
    """Operating rule: GPS good at take-off, then lost for hours; the monotonic clock carries the anchor."""
    c = Clocks()
    t = _clock(c, drift_ppm=20.0, gnss_sigma_s=0.5)
    assert t.add_gnss(c.w - 0.4, c.w) is True
    off, src, sig = t.offset_sigma()
    assert src == "gnss" and off == pytest.approx(-0.4) and sig == pytest.approx(0.5)
    c.tick(3 * 3600.0)                                 # 3 h without GPS
    off, src, sig = t.offset_sigma()
    assert src == "gnss" and off == pytest.approx(-0.4)
    assert sig == pytest.approx(0.5 + 20e-6 * 3 * 3600.0)           # 0.716 s
    st = t.status()
    assert st["source"] == "gnss" and st["sigma_s"] == pytest.approx(0.716, abs=1e-3)
    assert st["anchor"]["age_s"] == pytest.approx(10800.0)


def test_the_anchor_survives_a_system_clock_step():
    """NTP steps the wall clock +16 h after an offline boot: the anchor is on the monotonic clock."""
    c = Clocks()
    steps = []
    t = _clock(c, on_step=steps.append)
    t.add_gnss(c.w + 2.0, c.w)                         # UTC = wall + 2 s
    c.w += 57_600.0                                    # +16 h, monotonic unchanged
    off, why = t.offset()
    assert off is None and "stepped +57600.0 s" in why and steps == [57_600.0]
    c.tick(61.0)                                       # settled: stamps on the new clock again
    off, src = t.offset()
    assert src == "gnss" and off == pytest.approx(2.0 - 57_600.0)
    assert t.utc(c.w)[0] == pytest.approx(c.w + 2.0 - 57_600.0)


def test_an_untrusted_gps_never_anchors():
    """Refused or suspected GPS (estimator): its time is not taken."""
    c = Clocks()
    t = _clock(c)
    assert t.add_gnss(c.w + 100.0, c.w, trusted=False, why_untrusted="GPS refused by the estimator") is False
    assert t.offset()[0] is None
    st = t.status()
    assert st["gnss_untrusted"] == 1 and "refused" in st["gnss_untrusted_why"]


def test_a_spoofed_time_jump_is_logged_and_the_first_anchor_kept():
    c = Clocks()
    ev = []
    t = _clock(c, on_event=lambda k, s: ev.append(k))
    t.add_gnss(c.w, c.w)
    c.tick(60.0)
    for _ in range(5):                                 # a spoofer moves the GPS time by 30 s
        assert t.add_gnss(c.w + 30.0, c.w) is False
        c.tick(1.0)
    assert t.offset()[0] == pytest.approx(0.0)         # the anchor stands
    assert t.gnss_jumps == 5 and t.last_jump_s == pytest.approx(30.0)
    assert ev.count("gnss_jump") == 1                  # logged once per streak
    assert t.add_gnss(c.w + 0.1, c.w) is True          # agrees again: refreshes the anchor
    assert t.offset()[0] == pytest.approx(0.1)
    assert ev[-1] == "gnss_agree"


def test_the_anchor_cannot_be_walked_away_by_small_steps():
    """Each sample 0.4 s from the last would pass a 0.5 s check against the LAST one; the check is
    against the FIRST anchor plus the clock drift since.
    """
    c = Clocks()
    t = _clock(c, gnss_sigma_s=0.5, drift_ppm=20.0)
    t.add_gnss(c.w, c.w)
    shift = 0.0
    for _ in range(20):
        c.tick(1.0)
        shift += 0.4
        t.add_gnss(c.w + shift, c.w)
    assert abs(t.offset()[0]) <= 0.5 + 1e-3


def test_autopilot_time_is_second_and_cross_checks_the_anchor():
    c = Clocks()
    ev = []
    t = _clock(c, on_event=lambda k, s: ev.append(k))
    t.add_autopilot(c.w + 5.0, c.w)
    assert t.offset_sigma()[1:] == ("autopilot", pytest.approx(0.2))
    t.add_gnss(c.w + 5.3, c.w)                         # agrees within 1 s: the anchor wins
    assert t.offset() == (pytest.approx(5.3), "gnss")
    assert t.status()["anchor"]["minus_autopilot_s"] == pytest.approx(0.3)
    c.tick(1.0)
    t.add_autopilot(c.w + 7.0, c.w)                    # 1.7 s apart: one of them lies
    off, why = t.offset()
    assert off is None and "disagree" in why and ev.count("disagree") == 1
    c.tick(6.0)                                        # SYSTEM_TIME stale: the anchor alone again
    assert t.offset()[1] == "gnss"


def test_order_gnss_autopilot_rtc_phone_ntp():
    c = Clocks()
    c.ntp = True
    t = _clock(c)
    assert t.offset() == (0.0, "ntp")
    t.add_phone(c.w + 4.0, c.w)
    assert t.offset()[1] == "phone"
    t.add_rtc_status(valid=True, lost_power=False)
    t.add_rtc(c.w + 3.0, c.w)
    assert t.offset()[1] == "rtc"
    t.add_autopilot(c.w + 2.0, c.w)
    assert t.offset()[1] == "autopilot"
    t.add_gnss(c.w + 2.1, c.w)
    assert t.offset() == (pytest.approx(2.1), "gnss")


def test_no_anchor_after_a_reboot_falls_back_to_the_autopilot():
    """A Jetson reboot mid-flight, GPS denied: a new clock object has no anchor (never persisted)."""
    c = Clocks()
    t = _clock(c)
    t.add_autopilot(c.w + 1.0, c.w)
    off, src = t.offset()
    assert src == "autopilot" and off == pytest.approx(1.0)
    assert t.status()["anchor"] is None


def test_too_uncertain_is_not_used():
    c = Clocks()
    t = _clock(c, drift_ppm=20.0, max_sigma_s=1.0)
    t.add_gnss(c.w, c.w)
    c.tick(30_000.0)                                   # 0.5 + 0.6 s > 1 s
    off, why = t.offset()
    assert off is None and "uncertainty" in why


def test_ntp_is_asked_at_most_every_30_s():
    c = Clocks()
    c.ntp = True
    t = _clock(c)
    for _ in range(10):
        t.offset()
        c.tick(1.0)
    assert c.ntp_calls == 1


def test_a_clock_step_waits_before_trusting_stamps_again():
    """A wall-clock step (NTP after an offline boot) mid-mission: frames stamped before it are on the old clock."""
    c = Clocks()
    t = _clock(c)
    t.add_rtc_status(valid=True, lost_power=False)
    t.add_rtc(c.w, c.w)
    c.w += 3600.0
    c.ntp = True
    off, why = t.offset()
    assert off is None and "stepped" in why
    c.tick(61.0)
    assert t.offset() == (0.0, "ntp")                  # the RTC reading is stale now
    t.add_rtc_status(valid=True, lost_power=False)
    t.add_rtc(c.w + 1.0, c.w)
    assert t.utc(c.w - 5.0) == (pytest.approx(c.w - 4.0), "rtc")      # an exposure 5 s ago, on the RTC's time


def test_a_slow_slew_is_not_a_step():
    c = Clocks()
    t = _clock(c)
    for _ in range(100):
        c.tick(1.0)
        c.w += 0.0005                                  # NTP slewing 500 ppm
        assert not t.check_step()
