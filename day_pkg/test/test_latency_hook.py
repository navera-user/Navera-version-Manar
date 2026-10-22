"""day_subscriber's camera-delay hook: GPS-check matches feed navera_common.latency_cal, the frame stamps move."""
import math
from types import MethodType, SimpleNamespace

from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.latency_cal import LatencyCalibrator, shift_meta

M = 111320.0


def _ll(e, n):
    return 35.82 + n / M, 10.61 + e / (M * math.cos(math.radians(35.82)))


def test_check_matches_set_the_delay_and_new_frames_are_dated_by_it():
    logs = []
    n = SimpleNamespace(latency_cal=LatencyCalibrator(nominal_s=0.4), auto_latency=True, _latency_applied=None,
                        get_logger=lambda: SimpleNamespace(warn=logs.append), _relearn_after_delay_change=lambda: None)
    n._latency_sample = MethodType(DaySubscriber._latency_sample, n)
    track = (lambda t: (900 * math.sin(t / 15), 900 * (1 - math.cos(t / 15))))     # 60 m/s circle
    for k in range(900):
        t = 1000 + k * 0.1
        n.latency_cal.add_gps(t, *_ll(*track(t)))
        if k % 20 == 5 and k > 50:                     # a GPS check every 2 s
            meta = {"image_stamp_ns": int((t - 0.6) * 1e9)}   # arrived t - 0.2, the camera took off 0.4 s
            shift_meta(meta, n.latency_cal.correction())
            n._check_fix = (*_ll(*track(t - 1.2)), 0.0)    # exposed 1.0 s before arrival
            n._latency_sample(meta)
    assert abs(n.latency_cal.delay() - 1.0) < 0.03 and logs
    meta = shift_meta({"image_stamp_ns": 10_000_000_000}, n.latency_cal.correction())
    assert abs(meta["image_stamp_ns"] / 1e9 - (10.0 - 0.6)) < 0.03 and meta["image_stamp_raw_ns"] == 10_000_000_000


def test_a_frame_without_a_raw_stamp_is_no_sample():
    n = SimpleNamespace(latency_cal=LatencyCalibrator(), auto_latency=True, _latency_applied=None)
    DaySubscriber._latency_sample(n, {})
    assert n.latency_cal.samples == 0 and not n.latency_cal._pending


def test_a_moved_delay_forgets_the_map_bias_and_sigma_samples_dated_by_the_old_one():
    """Learned at delay 0, the delay then applied as 1.25 s: the samples compared vision with the GPS
    1.25 s off (37 m at 30 m/s) — forgotten. A move below latency_relearn_s keeps them."""
    from day_pkg.fix_sigma import SigmaCalibration
    from day_pkg.vision_nav import VisionNavigator
    logs = []
    lc = LatencyCalibrator()
    n = SimpleNamespace(latency_cal=lc, latency_relearn_s=0.2, _learned_delay=0.0,
                        sigma_cal=SigmaCalibration(5.0, 15), map_bias=VisionNavigator(),
                        get_logger=lambda: SimpleNamespace(info=logs.append))
    for k in range(6):
        n.map_bias.bias_sample((35.82, 10.61), (35.8201, 10.61), 90.0, t=100.0 + k)
        n.sigma_cal.add(10.0, 8.0, t=100.0 + k)
    lc.applied = 0.15
    DaySubscriber._relearn_after_delay_change(n)
    assert len(n.map_bias._bias) == 6 and not logs
    lc.applied = 1.25
    DaySubscriber._relearn_after_delay_change(n)
    assert len(n.map_bias._bias) == 0 and n.sigma_cal.rollback(float("-inf")) == 0 and logs
    assert n._learned_delay == 1.25
