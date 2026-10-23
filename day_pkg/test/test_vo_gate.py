"""Visual odometry against a stale track velocity (F32): believed when two clear steps agree."""
from types import MethodType, SimpleNamespace

from day_pkg.nodes.day_subscriber import DaySubscriber


def _node():
    n = SimpleNamespace(VO_AGREE_MPS=2.5, VO_AGREE_REL=0.25, VO_MIN_QUALITY=0.5, VO_MIN_SHIFT_PX=4.0,
                        VO_MAX_GAP_S=3.0)
    n._vo_gate = MethodType(DaySubscriber._vo_gate, n)
    return n


V = (10.0, 0.0, 0.5)                  # the track: 10 m/s east


def test_agreeing_with_the_track_is_used_as_before():
    assert _node()._vo_gate((19.0, 1.0, 2.0, 0.9), V, 1.0, 30.0) is not None


def test_a_single_disagreeing_step_is_not_used():
    assert _node()._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 1.0, 30.0) is None


def test_two_clear_steps_agreeing_against_the_track_are_used():
    n = _node()
    assert n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 1.0, 30.0) is None
    assert n._vo_gate((-17.0, 1.0, 2.0, 0.9), V, 3.0, 30.0) is not None      # turned round: 9 m/s west


def test_a_lock_on_the_image_is_never_believed():
    n = _node()
    n._vo_gate((-20.0, 0.0, 2.0, 0.9), V, 1.0, 0.5)          # no image shift: something fixed in the image
    assert n._vo_gate((-20.0, 0.0, 2.0, 0.9), V, 3.0, 0.5) is None


def test_weak_or_far_apart_steps_do_not_confirm():
    n = _node()
    n._vo_gate((-18.0, 0.0, 2.0, 0.3), V, 1.0, 30.0)          # low quality
    assert n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 3.0, 30.0) is None
    n = _node()
    n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 1.0, 30.0)
    assert n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 6.0, 30.0) is None          # 5 s apart
    n = _node()
    n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 1.0, 30.0)
    assert n._vo_gate((0.0, 18.0, 2.0, 0.9), V, 3.0, 30.0) is None          # disagree with each other


def test_a_failed_step_breaks_the_chain():
    n = _node()
    n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 1.0, 30.0)
    n._vo_gate(None, V, 2.0, None)
    assert n._vo_gate((-18.0, 0.0, 2.0, 0.9), V, 3.0, 30.0) is None


def test_without_a_track_velocity_the_step_is_used():
    assert _node()._vo_gate((5.0, 0.0, 2.0, 0.9), None, 1.0, 30.0) is not None
