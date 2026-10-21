"""normalize_query: thermal frame → north-up, map resolution, STHN's 512 px footprint (LOC-16)."""
import math

import numpy as np
import pytest

from night_pkg.nodes.night_localizer import (MIN_QUERY_COVERAGE, STHN_QUERY_PX,
                                             ground_resolution_m, normalize_query)

LAT = 35.83


def frame(w=640, h=480):
    img = np.full((h, w, 3), 100, np.uint8)
    img[: h // 10, w // 2 - 20: w // 2 + 20] = 255          # bright mark at the image top
    return img


def test_needs_altitude_and_field_of_view():
    for alt, fov in ((None, 84.0), (float("nan"), 84.0), (0.0, 84.0), (400.0, None),
                     (400.0, float("nan"))):
        q, info = normalize_query(frame(), LAT, 17, alt, fov)
        assert q is None and info["reason"]


def test_resampled_to_the_map_resolution():
    q, info = normalize_query(frame(), LAT, 17, 400.0, 84.0)
    assert q.shape == (STHN_QUERY_PX, STHN_QUERY_PX, 3)
    fw = 2 * 400 * math.tan(math.radians(42))
    assert info["footprint_w_m"] == pytest.approx(fw)
    assert info["scale"] == pytest.approx(fw / 640 / ground_resolution_m(LAT, 17))
    assert info["coverage"] == pytest.approx(1.0)


def test_turned_north_up_with_the_heading():
    # Heading 90: the image top looks east. North-up, the mark must be on the RIGHT.
    q, _ = normalize_query(frame(), LAT, 17, 400.0, 84.0, heading_deg=90.0)
    col = q[:, :, 0].astype(float).mean(axis=0)
    assert col.argmax() > STHN_QUERY_PX * 0.7
    q, _ = normalize_query(frame(), LAT, 17, 400.0, 84.0, heading_deg=0.0)
    row = q[:, :, 0].astype(float).mean(axis=1)
    assert row.argmax() < STHN_QUERY_PX * 0.3                # heading 0: still at the top


def test_too_small_footprint_is_refused():
    q, info = normalize_query(frame(), LAT, 17, 300.0, 84.0, heading_deg=45.0)
    assert q is None and info["coverage"] < MIN_QUERY_COVERAGE and "fly higher" in info["reason"]


def _centred_blob(w, h):
    y, x = np.mgrid[0:h, 0:w]
    g = np.exp(-((x - (w - 1) / 2) ** 2 + (y - (h - 1) / 2) ** 2) / (2 * 6.0 ** 2)) * 200 + 20
    return np.repeat(g.astype(np.uint8)[..., None], 3, axis=2)


@pytest.mark.parametrize("size", [(640, 512), (160, 120), (640, 480)])
@pytest.mark.parametrize("heading", [None, 0.0, 37.0, 90.0, 200.0, 313.0])
def test_frame_centre_lands_on_the_query_centre(size, heading):
    # The frame's optical centre must be the query's centre whatever the heading and the
    # camera resolution: the position is read from the query's centre. Turning about
    # (w/2, h/2) and cropping with a floor moved it by up to 8 query px (7 m) for a
    # 160 x 120 camera at 1000 m.
    for alt in (700.0, 1000.0):
        q, info = normalize_query(_centred_blob(*size), LAT, 17, alt, 50.0, heading_deg=heading)
        assert q is not None, info.get("reason")
        g = q[:, :, 0].astype(float) - 20.0
        g[g < 0] = 0
        yy, xx = np.mgrid[0:STHN_QUERY_PX, 0:STHN_QUERY_PX]
        c = (STHN_QUERY_PX - 1) / 2.0
        assert (g * xx).sum() / g.sum() == pytest.approx(c, abs=0.05)
        assert (g * yy).sum() / g.sum() == pytest.approx(c, abs=0.05)
