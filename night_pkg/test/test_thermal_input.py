"""16-bit thermal frames must keep their contrast when converted for STHN."""
import numpy as np
from cv_bridge import CvBridge

from night_pkg.nodes.night_subscriber import image_to_bgr8


def test_mono16_is_contrast_stretched():
    # A realistic radiometric frame: values around 7500 with a warm object.
    raw = np.full((64, 64), 7500, np.uint16)
    raw[20:40, 20:40] = 8200
    msg = CvBridge().cv2_to_imgmsg(raw, encoding="mono16")
    out = image_to_bgr8(CvBridge(), msg)
    assert out.shape == (64, 64, 3) and out.dtype == np.uint8
    assert int(out[30, 30, 0]) - int(out[5, 5, 0]) > 200     # object stands out


def test_bgr8_passes_through():
    img = np.random.default_rng(0).integers(0, 255, (8, 8, 3), dtype=np.uint8)
    out = image_to_bgr8(CvBridge(), CvBridge().cv2_to_imgmsg(img, encoding="bgr8"))
    assert (out == img).all()
