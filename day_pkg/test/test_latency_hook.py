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
                        get_logger=lambda: SimpleNamespace(warn=logs.append))
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
