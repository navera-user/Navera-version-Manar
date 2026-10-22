"""HeadingHistory: the IMU heading at a frame's exposure (D20)."""
from night_pkg.nodes.heading_history import HeadingHistory


def _turn(h, t0=100.0, rate=20.0, n=50, dt=0.02, start=350.0):
    for k in range(n):
        h.add(t0 + k * dt, start + rate * k * dt)


def test_interpolated_at_the_exposure_in_a_turn():
    h = HeadingHistory()
    _turn(h)                                       # 20 deg/s through north, 1 s of samples
    hd, gap = h.at(100.5)
    assert abs(hd - 0.0) < 1e-6 and gap < 1e-9    # 350 + 10 deg wraps to 0
    hd, gap = h.at(100.51)
    assert abs(hd - 0.2) < 1e-6 and abs(gap - 0.01) < 1e-9
    # the latest sample (what the node used to read) is 9.6 deg later than the exposure
    assert abs(h.at(100.98)[0] - 9.6) < 1e-6


def test_outside_or_in_a_hole_is_not_answered():
    h = HeadingHistory(max_gap_s=0.25)
    _turn(h)
    assert h.at(99.7) is None                      # before the history
    assert h.at(101.2)[1] < 0.25 and h.at(101.3) is None
    h2 = HeadingHistory(max_gap_s=0.25)
    h2.add(0.0, 10.0)
    h2.add(1.0, 20.0)
    assert h2.at(0.5) is None                      # 0.5 s from both samples
    assert abs(h2.at(0.2)[0] - 12.0) < 1e-6


def test_old_samples_dropped_and_rewind_clears():
    h = HeadingHistory(keep_s=1.0)
    for k in range(300):
        h.add(k * 0.01, 90.0)
    assert h.at(0.5) is None and h.at(2.9) is not None
    h.add(0.0, 180.0)                               # replay rewound: the clock went back
    assert h.at(0.0) == (180.0, 0.0)
    h.add(0.0, 10.0)                                # duplicate stamp ignored
    assert h.at(0.0)[0] == 180.0


def test_node_uses_the_heading_at_the_exposure():
    """night_subscriber._heading: frame_meta first, then the IMU at the exposure stamp, then
    the latest IMU (the old behaviour) only when the exposure is not in the history.
    """
    import time
    from types import SimpleNamespace

    from night_pkg.nodes.night_subscriber import NightSubscriber
    h = HeadingHistory()
    _turn(h)
    node = SimpleNamespace(_imu_history=h, _imu_heading=(9.8, time.monotonic()), _imu_timeout=1.0)
    hd, src = NightSubscriber._heading(node, {"heading_deg": 42.0, "image_stamp_ns": int(100.5e9)})
    assert (hd, src) == (42.0, "frame")
    hd, src = NightSubscriber._heading(node, {"image_stamp_ns": int(100.5e9)})
    assert abs(hd) < 1e-6 and src == "imu at exposure"
    hd, src = NightSubscriber._heading(node, {"image_stamp_ns": int(50e9)})
    assert hd == 9.8 and src.startswith("imu (latest")
