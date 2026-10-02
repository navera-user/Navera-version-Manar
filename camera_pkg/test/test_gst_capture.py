"""GStreamer capture (the CSI path) with a test-pattern source."""
import pytest

pytest.importorskip("gi")

from camera_pkg.gst_capture import GstCapture, csi_pipeline  # noqa: E402


def test_frames_come_out_bgr_at_the_requested_size():
    cap = GstCapture("videotestsrc pattern=smpte ! video/x-raw,width=642,height=480,framerate=30/1 ! "
                     "videoconvert ! video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false")
    assert cap.isOpened()
    for _ in range(3):
        assert cap.grab()
    ok, img = cap.retrieve()
    assert ok and img.shape == (480, 642, 3) and img.std() > 10
    # SMPTE bars are vertical: with the row padding (odd width) mishandled they slant
    assert max(img[:250, x].std(axis=0).max() for x in (50, 300, 600)) < 1.0
    assert cap.retrieve() == (False, None)                            # one retrieve per grab
    ok, img = cap.read()
    assert ok and img.shape == (480, 642, 3)
    cap.release()
    assert not cap.isOpened() and cap.grab() is False


def test_a_bad_pipeline_is_not_opened():
    assert not GstCapture("no_such_element ! appsink name=sink").isOpened()


def test_csi_pipeline_text():
    p = csi_pipeline(1920, 1080, sensor_id=1)
    assert "nvarguscamerasrc sensor-id=1" in p and "width=1920,height=1080" in p and "name=sink" in p
