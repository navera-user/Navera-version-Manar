"""navera_common.map_area: distance to the edge of the mission's map, the fence inside it."""
import math
import os

import pytest

from navera_common.map_area import (MAP_AREA_INSIDE, MAP_AREA_NEAR_EDGE, MAP_AREA_OUTSIDE, MAP_AREA_UNKNOWN,
                                    MapArea, classify, tile_bounds)

Z = 17
X0, Y0 = 69360, 51517            # Kalaa Kebira, ~245 x 245 m tiles at zoom 17


def block(nx, ny, x0=X0, y0=Y0):
    return [(Z, x0 + i, y0 + j) for i in range(nx) for j in range(ny)]


def centre(tiles):
    b = [tile_bounds(*t) for t in tiles]
    return (min(x[0] for x in b) + max(x[2] for x in b)) / 2, (min(x[1] for x in b) + max(x[3] for x in b)) / 2


def test_tile_bounds_are_the_xyz_tile():
    s, w, n, e = tile_bounds(Z, X0, Y0)
    assert w == pytest.approx(10.5029296875) and n == pytest.approx(35.89572525865905)
    assert s < n and w < e and (n - s) * 111320 == pytest.approx(245, abs=5)


def test_edge_distance_inside_outside_and_far():
    tiles = block(9, 9)                                          # ~2.2 km square
    a = MapArea(tiles)
    lat, lon = centre(tiles)
    half = 9 * 245 / 2
    assert a.edge_distance_m(lat, lon) == pytest.approx(half, abs=60)
    # 400 m north of the north edge: outside by ~400 m
    n_edge = max(tile_bounds(*t)[2] for t in tiles)
    assert a.edge_distance_m(n_edge + 400 / 111319.5, lon) == pytest.approx(-400, abs=40)
    # far beyond the padded grid: still outside, by at least the distance to the box
    assert a.edge_distance_m(lat + 0.2, lon) < -20000
    assert math.isnan(a.edge_distance_m(math.nan, lon))


def test_classify():
    assert classify(math.nan, 500) == MAP_AREA_UNKNOWN
    assert classify(-1.0, 500) == MAP_AREA_OUTSIDE
    assert classify(499.0, 500) == MAP_AREA_NEAR_EDGE
    assert classify(501.0, 500) == MAP_AREA_INSIDE


def test_fence_polygon_stays_margin_inside_an_l_shaped_corridor():
    tiles = block(12, 4) + block(4, 12)                          # an L: two 3 km x 1 km arms
    a = MapArea(tiles)
    margin = 200.0
    poly = a.fence_polygon(margin, max_vertices=20)
    assert 4 <= len(poly) <= 20
    # every point of every edge of the polygon is at least ~margin inside the map
    worst = min(a.edge_distance_m(p[0] + (q[0] - p[0]) * k / 50, p[1] + (q[1] - p[1]) * k / 50)
                for p, q in zip(poly, poly[1:] + poly[:1]) for k in range(51))
    assert worst >= margin - 2 * a.cell
    # it follows the L (not its bounding box): the empty corner is outside the fence
    assert a.edge_distance_m(*centre(block(8, 8, X0 + 4, Y0 + 4))) < 0


def test_no_fence_when_the_map_is_narrower_than_twice_the_margin():
    assert MapArea(block(2, 2)).fence_polygon(400.0) == []


def test_from_images_dir_reads_the_tile_names(tmp_path):
    for z, x, y in block(3, 2):
        open(os.path.join(tmp_path, f"tile_{z}_{x}_{y}.jpg"), "w").close()
    open(os.path.join(tmp_path, "dataset.csv"), "w").close()
    a = MapArea.from_images_dir(str(tmp_path))
    assert len(a.tiles) == 6
    assert MapArea.from_images_dir(str(tmp_path / "missing")) is None
