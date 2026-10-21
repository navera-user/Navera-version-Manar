"""Terrain: the ground height under a position from an offline DEM tile set."""
import json
import math

import numpy as np

from navera_common.terrain import Terrain, save_dem


def test_bilinear_height_slope_and_sigma(tmp_path):
    # a 10x10 grid rising 10 m per row southwards... i.e. falling northwards, flat east-west
    grid = np.tile(np.arange(10, dtype=np.float32)[:, None] * 10.0, (1, 10))
    piece = dict(grid=grid, north=40.0, west=44.0, dlat=0.001, dlon=0.001, sigma_m=4.0)
    save_dem(str(tmp_path / "terrain"), [piece], source="test", sigma_m=4.0)
    T = Terrain.load(str(tmp_path))
    h, s, slope = T.height(40.0 - 0.0025, 44.004)
    assert math.isclose(h, 25.0, abs_tol=1e-4) and s == 4.0
    assert math.isclose(slope, 10.0 / (0.001 * 111320.0), rel_tol=1e-6)
    assert T.height(40.0005, 44.004) is None and T.height(39.0, 44.0) is None
    assert T.height(float("nan"), 44.0) is None


def test_no_data_and_missing_or_foreign_index(tmp_path):
    grid = np.zeros((4, 4), np.float32)
    grid[1, 1] = np.nan
    T = Terrain.from_grid(grid, 1.0, 1.0, 0.01, 0.01)
    assert T.height(1.0 - 0.015, 1.015) is None                  # touches the no-data pixel
    assert T.height(1.0 - 0.025, 1.025) == (0.0, 5.0, 0.0)
    assert Terrain.load(str(tmp_path)) is None and Terrain.load("") is None
    (tmp_path / "dem.json").write_text(json.dumps({"format": "other"}))
    assert Terrain.load(str(tmp_path)) is None


def test_first_piece_holding_the_point_answers():
    a = Terrain.from_grid(np.full((3, 3), 5.0), 1.0, 1.0, 0.01, 0.01)
    b = Terrain.from_grid(np.full((3, 3), 9.0), 1.1, 1.1, 0.01, 0.01)
    T = Terrain(a.pieces + b.pieces)
    assert T.height(0.99, 1.01)[0] == 5.0 and T.height(1.09, 1.11)[0] == 9.0
