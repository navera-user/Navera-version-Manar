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
    q, info = normalize_query(frame(), LAT, 17, 150.0, 84.0)
    assert q is None and info["coverage"] < MIN_QUERY_COVERAGE and "fly higher" in info["reason"]
