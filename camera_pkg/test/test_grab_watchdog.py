"""Camera stall watchdog (camera unplugged / stuck driver: the live camera exits for a restart)."""
from camera_pkg.grab_watchdog import GrabWatchdog


def test_not_stalled_before_start_or_while_frames_come():
    w = GrabWatchdog(10.0)
    assert w.stalled(1e9) is None                        # not opened yet: nothing to judge
    w.start(100.0)
    for t in range(101, 200, 3):
        w.ok(float(t))
        assert w.stalled(t + 9.9) is None


def test_stalled_after_stall_s_without_a_frame_and_a_new_frame_clears_it():
    w = GrabWatchdog(10.0)
    w.start(0.0)
    assert w.stalled(10.0) is None
    why = w.stalled(10.5)
    assert why and "no frame from the camera for 10 s" in why
    w.ok(11.0)
    assert w.stalled(12.0) is None


def test_a_device_that_never_sends_its_first_frame_is_stalled():
    w = GrabWatchdog(5.0)
    w.start(0.0)
    assert w.stalled(6.0)


def test_zero_disables_it():
    w = GrabWatchdog(0.0)
    w.start(0.0)
    assert w.stalled(1e6) is None
