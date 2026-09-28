"""Unit tests for navera_common.health."""
from navera_common.health import FrozenSampleDetector, RetryTimer


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
