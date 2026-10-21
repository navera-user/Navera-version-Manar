"""map_levels: the map zoom a frame is matched against (area.json zooms, frame height)."""
import json

from day_pkg.map_levels import area_zooms, choose_zoom, map_m_per_px
from day_pkg.local_matcher import LocalMatcher


def _area(tmp_path, info, tiles):
    (tmp_path / "images").mkdir()
    for name in tiles:
        (tmp_path / "images" / name).write_bytes(b"x")
    if info is not None:
        (tmp_path / "area.json").write_text(json.dumps(info))
    return str(tmp_path / "images")


def test_an_area_without_area_json_is_zoom_17(tmp_path):
    assert area_zooms(_area(tmp_path, None, ["tile_17_1_2.jpg"])) == [17]


def test_area_zoom_and_zooms_with_tiles_present(tmp_path):
    d = _area(tmp_path, {"zoom": 17, "zooms": [18, 17, 19]}, ["tile_17_1_2.jpg", "tile_18_2_4.jpg"])
    assert area_zooms(d) == [17, 18]                       # no z19 tile: not offered


def test_single_zoom_area_is_kept(tmp_path):
    assert area_zooms(_area(tmp_path, {"zoom": 18}, ["tile_18_2_4.jpg"])) == [18]


def test_finer_map_for_low_frames_coarsest_for_high_ones():
    lat = 39.95
    mpp = lambda h: LocalMatcher.frame_m_per_px(1224, h, 80.0)     # noqa: E731 — the MARS-LVIG camera
    assert choose_zoom([17, 18], mpp(100.0), lat) == 18            # 0.17 m/px frame, z18 0.46 m/px
    assert choose_zoom([17, 18], mpp(140.0), lat) == 18            # frame 2.4x finer than z18: measured
    assert choose_zoom([17, 18], mpp(400.0), lat) == 17
    assert choose_zoom([17, 18, 19], mpp(60.0), lat) == 19
    assert choose_zoom([17], mpp(60.0), lat) == 17                 # existing maps: unchanged
    assert choose_zoom([17, 18], None, lat) == 17 and choose_zoom([17, 18], mpp(60.0), None) == 17
    assert abs(map_m_per_px(lat, 17) - 0.916) < 0.01
