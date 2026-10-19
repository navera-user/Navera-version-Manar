"""screen_flight's screen conditions draw without a window, and only wind moves the scene."""
import numpy as np
import pytest

from navera_tools.bench.screen_overlays import KINDS, Overlays


def test_every_overlay_draws_and_only_wind_shifts_the_scene():
    w, h = 640, 360
    ov = Overlays(w, h, px_per_deg=26.0)
    base = (np.random.default_rng(0).random((h, w, 3)) * 255).astype(np.uint8)
    for kind in KINDS:
        for amount in (0.3, 0.7):
            img, shift = ov.draw(base, 1.3, [kind], amount)
            assert img.shape == base.shape and img.dtype == np.uint8
            assert (img != base).mean() > 0.001, kind                     # it changes the frame
            if kind == "wind":
                assert 5.0 < np.hypot(*shift) < 3.5 * 26.0 * 2.5           # 0.5-3 deg, gusts
            else:
                assert shift == (0.0, 0.0)
    with pytest.raises(ValueError):
        ov.draw(base, 0.0, ["rainn"], 0.3)
