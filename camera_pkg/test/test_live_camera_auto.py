"""live_camera plug-and-play: the size from the first frame, a thermal core's 16-bit pictures, and the
lens calibrated in flight (applied when published, and at the next start)."""
import json

import numpy as np
import pytest
import rclpy
from rclpy.parameter import Parameter
from std_msgs.msg import String

from camera_pkg.nodes.live_camera import LiveCamera
from navera_common import state_store

LENS = dict(model="fisheye", camera_matrix=[300.0, 0, 320, 0, 300.0, 240, 0, 0, 1], distortion=[0.02, -0.01, 0, 0],
            image_width=640, image_height=480)


@pytest.fixture
def ros(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    rclpy.init()
    yield
    rclpy.shutdown()


def camera():
    params = [Parameter("input", value="ros"), Parameter("width", value=0), Parameter("height", value=0),
              Parameter("camera_hfov_deg", value=70.0), Parameter("input_topic", value="/test/cam/image_raw"),
              Parameter("wait_for_ready", value=False)]
    return LiveCamera(parameter_overrides=params)


def test_the_size_comes_from_the_first_frame_and_the_lens_calibrated_in_flight_is_applied(ros):
    n = camera()
    try:
        assert n.builder is None                          # size unknown until a frame comes
        assert n._adopt(np.zeros((480, 640, 3), np.uint8))
        assert (n.w, n.h) == (640, 480) and n.lens_source == "ideal"
        assert not n._adopt(np.zeros((240, 320, 3), np.uint8))       # then frames must keep that size
        key = n.lens_key
        n._on_lens(String(data=json.dumps({"lens_key": "another camera", "lens": LENS})))
        assert n.builder.cam.model == "pinhole"           # not this camera's: ignored
        n._on_lens(String(data=json.dumps({"lens_key": key, "lens": LENS, "views": 14, "rms_px": 0.8})))
        assert n.builder.cam.model == "fisheye" and n.lens_source == "in-flight calibration"
        state_store.save(f"lens_auto_{key}", {"lens": LENS, "date": "today", "views": 14, "rms_px": 0.8})
    finally:
        n._stop.set()
        n.destroy_node()
    m = camera()                                          # the next start: the kept lens at once
    try:
        m._adopt(np.zeros((480, 640, 3), np.uint8))
        assert m.lens_key == key and m.builder.cam.model == "fisheye" and m.lens_source == "in-flight calibration"
    finally:
        m._stop.set()
        m.destroy_node()


def test_a_16_bit_thermal_picture_becomes_8_bit_bgr():
    raw = np.linspace(20000, 24000, 640 * 512).reshape(512, 640).astype(np.uint16)
    out = LiveCamera.to_bgr8(raw)
    assert out.dtype == np.uint8 and out.shape == (512, 640, 3)
    assert out[..., 0].min() == 0 and out[..., 0].max() == 255 and (out[..., 0] == out[..., 2]).all()
    grey = np.full((120, 160), 90, np.uint8)
    assert LiveCamera.to_bgr8(grey).shape == (120, 160, 3)


def test_a_lens_on_trial_alternates_with_the_lens_in_use_then_is_kept_or_dropped(ros):
    n = camera()
    try:
        n._adopt(np.zeros((480, 640, 3), np.uint8))
        old = n.builder
        n._on_lens(String(data=json.dumps({"lens_key": n.lens_key, "lens": LENS, "trial": True})))
        assert n.builder is old and n._trial_builder.cam.model == "fisheye"
        n._on_lens(String(data=json.dumps({"lens_key": n.lens_key, "lens": {}, "revert": True})))
        assert n._trial_builder is None and n.builder is old       # (a revert needs no valid lens to end the trial)
        n._on_lens(String(data=json.dumps({"lens_key": n.lens_key, "lens": LENS, "trial": True})))
        n._on_lens(String(data=json.dumps({"lens_key": n.lens_key, "lens": LENS, "keep": True})))
        assert n.builder.cam.model == "fisheye" and n._trial_builder is None
    finally:
        n._stop.set()
        n.destroy_node()


def test_a_late_frame_is_redated_from_the_camera_stamp_or_flagged(ros):
    """navera_common.frame_lateness at the grab: a frame 1.5 s later than the usual delay is moved
    back by that much when the source stamps it (GStreamer PTS), flagged for the localizer when only
    the frame interval shows it; on-time frames give nothing."""
    from types import SimpleNamespace
    node = camera()
    try:
        cap = SimpleNamespace(stamps=None)
        for k in range(20):
            cap.stamps = (100.0 + k * 0.1 + 0.2, k * 0.1)
            assert node._watch_delay(cap) == (0.0, 0.0, "")
        cap.stamps = (100.0 + 2.0 + 0.2 + 1.5, 2.0)
        shift, unsure, basis = node._watch_delay(cap)
        assert basis == "camera_stamp" and abs(shift - 1.5) < 1e-6 and unsure == 0.0
        from navera_common.frame_lateness import meta_fields
        assert meta_fields(shift, unsure, basis) == {"late_s": 1.5, "late_basis": "camera_stamp",
                                                     "late_redated": True}
    finally:
        node.destroy_node()
