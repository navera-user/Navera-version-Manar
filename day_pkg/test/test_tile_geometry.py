"""Unit tests for the day tile geometry (tile centres, dataset coordinates)."""
import math

import pandas as pd
import pytest

from day_pkg.nodes.day_localizer import dataset_coords, haversine_m, tile_center_latlon


def nw_corner(z, x, y):
    n = 2 ** z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n)))), x / n * 360 - 180


def test_centre_is_half_a_tile_from_the_nw_corner():
    """Regression: the dataset stores NW corners; publishing them biased fixes ~175 m."""
    lat, lon = tile_center_latlon("tile_17_69388_51536.jpg")
    c_lat, c_lon = nw_corner(17, 69388, 51536)
    assert (c_lat, c_lon) == pytest.approx((35.8534396195918, 10.579833984375))
    assert haversine_m(lat, lon, c_lat, c_lon) == pytest.approx(175.0, abs=1.0)
    assert lat < c_lat and lon > c_lon                      # centre is SE of the NW corner


def test_centre_matches_mercator_midpoint():
    z, x, y = 17, 69400, 51550
    lat, lon = tile_center_latlon(f"/some/dir/tile_{z}_{x}_{y}.jpg")
    a, b = nw_corner(z, x, y), nw_corner(z, x + 1, y + 1)
    assert lon == pytest.approx((a[1] + b[1]) / 2)
    assert b[0] < lat < a[0]


@pytest.mark.parametrize("name", ["frame_0001.jpg", "tile_17_a_b.jpg", "tile_17_1.jpg", ""])
def test_non_tile_names_are_rejected(name):
    assert tile_center_latlon(name) is None


def test_dataset_coords_uses_centres_and_falls_back_to_columns():
    df = pd.DataFrame({"imageName": ["tile_17_69388_51536.jpg", "custom.jpg"],
                       "lat": [35.8534396195918, 36.0], "lon": [10.579833984375, 10.5]})
    c = dataset_coords(df)
    assert c.shape == (2, 2)
    assert tuple(c[0]) == pytest.approx(tile_center_latlon("tile_17_69388_51536.jpg"))
    assert tuple(c[1]) == (36.0, 10.5)


def test_dataset_coords_accepts_long_column_names():
    df = pd.DataFrame({"imageName": ["custom.jpg"], "latitude": [1.5], "longitude": [2.5]})
    assert tuple(dataset_coords(df)[0]) == (1.5, 2.5)
