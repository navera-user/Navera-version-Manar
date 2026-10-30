"""Night reads the onboard map, then the tiles downloaded on the /mission page."""
import sqlite3

import cv2
import numpy as np

from night_pkg.nodes import night_localizer as nl


def make_mbtiles(path, tiles):
    """Write an MBTiles with uniform JPEG tiles {(z, x, y): grey value}."""
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, "
              "tile_row INTEGER, tile_data BLOB)")
    for (z, x, y), val in tiles.items():
        img = np.full((256, 256, 3), val, np.uint8)
        jpg = cv2.imencode(".jpg", img)[1].tobytes()
        c.execute("INSERT INTO tiles VALUES (?,?,?,?)", (z, x, (2 ** z - 1) - y, jpg))
    c.commit()
    c.close()


def test_onboard_first_then_downloaded_and_a_cache_created_later(tmp_path):
    main, cache = str(tmp_path / "main.mbtiles"), str(tmp_path / "downloaded.mbtiles")
    make_mbtiles(main, {(17, 1, 1): 50})
    src = nl.TileSources(main, [cache])                      # the cache does not exist yet
    assert nl._read_tile(src, 17, 1, 1) is not None
    assert nl._read_tile(src, 17, 2, 2) is None   # nowhere yet: not remembered as absent
    make_mbtiles(cache, {(17, 2, 2): 200, (17, 1, 1): 10})   # generated on /mission
    t = nl._read_tile(src, 17, 2, 2)
    assert t is not None and abs(int(t.mean()) - 200) < 5
    onboard = nl._read_tile(src, 17, 1, 1)                   # the onboard map wins
    assert abs(int(onboard.mean()) - 50) < 5


def test_single_map_as_before(tmp_path):
    main = str(tmp_path / "main.mbtiles")
    make_mbtiles(main, {(17, 3, 3): 90})
    src = nl.TileSources(main)
    assert nl._read_tile(src, 17, 3, 3) is not None and nl._read_tile(src, 17, 4, 4) is None
