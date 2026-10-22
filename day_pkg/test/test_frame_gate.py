"""day_pkg.frame_gate (F20): frames refused for the camera's rotation during the exposure or blur."""
import cv2
import numpy as np

from day_pkg.frame_gate import FrameGate, focal_px


def test_the_rate_at_the_exposure_refuses_a_smeared_frame_only():
    g = FrameGate(max_blur_px=6.0, exposure_s=1 / 60)
    f = focal_px(1200, 100.0)                                   # ~503 px
    for i in range(100):
        t = i * 0.005
        g.add_rate(t, (0.0, 80.0 if 0.2 <= t <= 0.25 else 5.0, 0.0))   # a 50 ms gust at 80 deg/s
    assert g.check(0.1, None, f)["refuse"] is None                     # 5 deg/s: 0.7 px
    q = g.check(0.22, None, f)
    assert q["refuse"] is not None and q["rate_dps"] == 80.0 and q["blur_px"] > 6.0
    assert g.check(3.0, None, f)["refuse"] is None                    # no samples: no opinion
    assert g.refused_rate == 1


def test_sharpness_is_judged_against_the_flight_baseline():
    rng = np.random.default_rng(1)
    g = FrameGate(max_blur_px=0.0, sharp_rel=0.6, min_baseline=5)
    frames = [(rng.random((240, 320)) * 255).astype(np.uint8) for _ in range(6)]
    for fr in frames:
        assert g.check(None, cv2.GaussianBlur(fr, (0, 0), 1.0), None)["refuse"] is None
    blurred = cv2.GaussianBlur(frames[0], (0, 0), 6.0)
    q = g.check(None, blurred, None)
    assert q["refuse"] is not None and "blurred" in q["refuse"]


def test_off_by_default_settings_never_refuse():
    g = FrameGate(max_blur_px=0.0, sharp_rel=0.0)
    g.add_rate(0.0, (500.0, 0.0, 0.0))
    assert g.check(0.0, np.zeros((10, 10), np.uint8), 500.0)["refuse"] is None
    assert focal_px(0, 100.0) is None and focal_px(1200, 0.0) is None
