"""ImuWatchdog (F14): the camera's IMU feed silent -> restart the stream, then reset the USB device."""
from navera_common.insta360_protocol import ImuWatchdog


def _run(w, t0, seconds, imu_age_at):
    out = []
    for k in range(1, seconds + 1):
        a = w.step(t0 + k, imu_age_at(t0 + k))
        if a:
            out.append((k, a))
    return out


def test_restarts_then_a_reset_before_the_servers_10_s():
    w = ImuWatchdog(started=0.0)
    acts = _run(w, 10.0, 12, lambda t: t - 10.0)           # silent from t = 10 (warm-up long over)
    assert acts[:4] == [(2, "restart"), (4, "restart"), (6, "restart"), (8, "reset")]   # before the server's 10 s
    assert w.failed == 0


def test_imu_back_clears_the_count():
    w = ImuWatchdog(started=0.0)
    assert w.step(12.0, 3.0) == "restart"
    assert w.step(13.0, 0.1) is None and w.failed == 0     # the restart brought it back


def test_nothing_during_the_warm_up():
    w = ImuWatchdog(started=100.0)
    assert w.step(103.0, float("inf")) is None
    assert w.step(104.5, float("inf")) == "restart"
