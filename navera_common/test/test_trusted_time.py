"""Unit tests for navera_common.trusted_time (hazard H-08: celestial solves only on a trusted time)."""
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


def test_no_rtc_no_gnss_no_ntp_means_no_trusted_time():
    """F27: a box without a battery clock and without internet must not solve."""
    c = Clocks()
    off, why = _clock(c).offset()
    assert off is None and "no trusted time" in why and "NTP" in why


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


def test_gnss_time_and_ntp_vouch_for_the_system_clock():
    c = Clocks()
    t = _clock(c, gnss_max_age_s=300.0)
    t.add_gnss(c.w - 0.4, c.w)
    c.tick(100.0)
    off, src = t.offset()
    assert src == "gnss" and abs(off + 0.4) < 1e-6
    c.tick(250.0)                                      # GNSS time too old, NTP not synchronised
    assert t.offset()[0] is None
    c.ntp = True
    c.tick(31.0)
    assert t.offset() == (0.0, "ntp")


def test_ntp_is_asked_at_most_every_30_s():
    c = Clocks()
    c.ntp = True
    t = _clock(c)
    for _ in range(10):
        t.offset()
        c.tick(1.0)
    assert c.ntp_calls == 1


def test_a_clock_step_drops_the_evidence_and_waits_before_trusting_again():
    """A wall-clock step (NTP after an offline boot) mid-mission: earlier samples are on the old clock."""
    c = Clocks()
    steps = []
    t = _clock(c, on_step=steps.append)
    t.add_rtc_status(valid=True, lost_power=False)
    t.add_rtc(c.w, c.w)
    t.add_gnss(c.w, c.w)
    assert t.offset()[1] == "rtc"
    c.w += 57_600.0                                    # +16 h, monotonic unchanged
    off, why = t.offset()
    assert off is None and "stepped +57600.0 s" in why and steps == [57_600.0]
    c.ntp = True
    c.tick(30.0)
    assert t.offset()[0] is None                       # still settling: frames from before the step
    c.tick(31.0)
    assert t.offset() == (0.0, "ntp")                  # gnss and rtc samples were dropped
    c.ntp = False
    t.add_rtc_status(valid=True, lost_power=False)
    t.add_rtc(c.w + 1.0, c.w)
    assert t.utc(c.w - 5.0) == (c.w - 4.0, "rtc")      # an exposure 5 s ago, on the RTC's time


def test_a_slow_slew_is_not_a_step():
    c = Clocks()
    t = _clock(c)
    for _ in range(100):
        c.tick(1.0)
        c.w += 0.0005                                  # NTP slewing 500 ppm
        assert not t.check_step()
