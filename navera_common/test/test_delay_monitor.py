"""navera_common.delay_monitor: a change of the camera delay noticed from the source stamps (no GPS)."""
import numpy as np

from navera_common.delay_monitor import DelayChangeMonitor


def feed(mon, duration, fps=10.0, offset=1000.0, delay=lambda t: 0.05, jitter=0.005, seed=1, t0=0.0, skew=0.0):
    rng = np.random.default_rng(seed)
    t = t0
    while t < t0 + duration:
        src = t * (1 + skew) - offset                       # the source's clock
        mon.add(t + delay(t) + abs(rng.normal(0, jitter)), src)
        t += 1.0 / fps
    return mon


def test_a_steady_delay_is_no_change():
    mon = feed(DelayChangeMonitor(), 3600.0)
    assert mon.change_s is not None and abs(mon.change_s) < 0.01 and not mon.significant


def test_a_step_of_the_delay_is_noticed():
    """The queue grows by 0.3 s (CPU load, network) 10 minutes in."""
    mon = feed(DelayChangeMonitor(), 1200.0, delay=lambda t: 0.05 + (0.3 if t > 600 else 0.0))
    assert abs(mon.change_s - 0.3) < 0.02 and mon.significant


def test_clock_skew_is_not_a_change_but_bounds_what_is_seen():
    """Two clocks 50 ppm apart drift 0.18 s in an hour: within the allowance (100 ppm)."""
    mon = feed(DelayChangeMonitor(), 3600.0, skew=-50e-6)
    assert 0.1 < mon.change_s < 0.25 and not mon.significant


def test_occasional_late_frames_do_not_move_the_low_quantile():
    rng = np.random.default_rng(3)
    mon = feed(DelayChangeMonitor(), 900.0, delay=lambda t: 0.05 + (0.5 if rng.random() < 0.1 else 0.0))
    assert abs(mon.change_s) < 0.02 and not mon.significant


def test_a_source_clock_reset_restarts_the_reference():
    mon = feed(DelayChangeMonitor(ref_s=30.0), 300.0)
    feed(mon, 20.0, offset=-5000.0, t0=300.0)              # the camera rebooted: its clock restarted
    assert mon.change_s is None and not mon.significant


def test_no_reference_no_verdict():
    mon = feed(DelayChangeMonitor(ref_s=60.0), 30.0)
    assert mon.change_s is None and not mon.significant and mon.state()["reference"] is False
    mon.add(float("nan"), 1.0)
    mon.add(10.0, float("inf"))                            # no source stamp
    assert mon.change_s is None
