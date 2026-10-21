"""Unit tests for navera_common.health."""
import numpy as np

from navera_common.health import FrozenFrameDetector, FrozenSampleDetector, RetryTimer


def test_noisy_samples_are_never_frozen():
    d = FrozenSampleDetector(max_repeats=5)
    assert not any(d.update((0.1 + i * 1e-6, 9.81)) for i in range(100))


def test_identical_samples_become_frozen_after_max_repeats():
    d = FrozenSampleDetector(max_repeats=5)
    results = [d.update((0.1, 9.81)) for _ in range(6)]
    assert results == [False] * 5 + [True]


def test_a_change_resets_the_count():
    d = FrozenSampleDetector(max_repeats=3)
    for _ in range(3):
        d.update((1,))
    assert not d.update((2,))
    d.reset()
    assert not d.update((2,))


def test_retry_timer_limits_attempts():
    t = RetryTimer(2.0)
    assert t.ready(now=10.0)
    assert not t.ready(now=11.0)
    assert not t.ready(now=11.99)
    assert t.ready(now=12.0)


def _frame(seed, shape=(120, 160, 3)):
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


def test_a_camera_delivering_new_pictures_is_never_frozen():
    """D24: noisy, changing frames, moving or not, are fresh."""
    d = FrozenFrameDetector()
    assert all(d.update(_frame(i), float(i), moving=bool(i % 2)) is None for i in range(20))
    assert not d.frozen


def test_an_identical_picture_is_frozen_until_the_camera_recovers():
    """D24 / H-01b: the same picture again (stuck driver) is frozen even with no motion known."""
    d = FrozenFrameDetector()
    img = _frame(1)
    assert d.update(img, 1.0) is None
    why = d.update(img.copy(), 2.0)
    assert why and "identical" in why and d.frozen and d.frozen_since == 2.0
    assert d.update(img.copy(), 3.0) and d.repeats == 2 and d.frozen_since == 2.0
    assert d.update(_frame(2), 4.0) is None                     # new picture: recovered
    assert not d.frozen and d.repeats == 0 and d.frozen_since is None


def test_a_frame_whose_time_does_not_advance_is_frozen():
    """D24: a ROS camera re-publishing the same frame (same stamp) is caught even if re-encoded."""
    d = FrozenFrameDetector()
    assert d.update(_frame(1), 10.0) is None
    why = d.update(_frame(2), 10.0)
    assert why and "did not advance" in why
    assert d.update(_frame(3), 9.0)                             # stamp going back
    assert d.update(_frame(4), 9.5) is None                     # advancing again (clock step back)


def test_a_nearly_identical_picture_is_frozen_only_when_the_vehicle_moved():
    """D24: a re-decoded stale picture (tiny noise) while the IMU says the vehicle moved."""
    d = FrozenFrameDetector()
    img = _frame(5)
    noisy = np.clip(img.astype(np.int16) + np.random.default_rng(6).integers(-1, 2, img.shape), 0, 255)
    noisy = noisy.astype(np.uint8)
    assert d.update(img, 1.0) is None
    assert d.update(noisy, 2.0, moving=False) is None           # hovering: a still scene is legitimate
    assert d.update(img, 3.0, moving=None) is None              # motion unknown: not judged on similarity
    why = d.update(noisy, 4.0, moving=True)
    assert why and "while the vehicle moved" in why
    d.reset()
    assert d.update(noisy, 5.0, moving=True) is None            # no previous frame after a reset
