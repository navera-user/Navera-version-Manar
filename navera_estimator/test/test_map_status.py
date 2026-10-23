"""The estimator's mission-area guard: NavStatus.map_area / map_edge_m from the published position."""
import math
from types import MethodType, SimpleNamespace

from navera_common.map_area import MapArea, tile_bounds
from navera_estimator.nodes.estimator_node import EstimatorNode
from navera_msgs.msg import NavStatus

TILES = [(17, 69360 + i, 51517 + j) for i in range(9) for j in range(9)]     # ~2.2 km square


def _node(hold_s=60.0):
    logs = []
    lg = SimpleNamespace(warn=lambda m: logs.append(("warn", m)), info=lambda m: logs.append(("info", m)))
    n = SimpleNamespace(_map=MapArea(TILES), _map_warn=500.0, _map_hold=hold_s, _map_last=None, _map_flag=None,
                        get_logger=lambda: lg)
    n._map_status = MethodType(EstimatorNode._map_status, n)
    return n, logs


def _pos(lat, lon):
    return SimpleNamespace(latitude=lat, longitude=lon)


def test_inside_near_edge_outside_and_held_after_the_last_position():
    n, logs = _node()
    s, w, nn, e = (min(tile_bounds(*t)[0] for t in TILES), min(tile_bounds(*t)[1] for t in TILES),
                   max(tile_bounds(*t)[2] for t in TILES), max(tile_bounds(*t)[3] for t in TILES))
    lat_c, lon_c = (s + nn) / 2, (w + e) / 2
    assert n._map_status(_pos(lat_c, lon_c))[0] == NavStatus.MAP_AREA_INSIDE
    flag, edge = n._map_status(_pos(nn - 200 / 111319.5, lon_c))
    assert flag == NavStatus.MAP_AREA_NEAR_EDGE and 150 < edge < 250
    flag, edge = n._map_status(_pos(nn + 300 / 111319.5, lon_c))
    assert flag == NavStatus.MAP_AREA_OUTSIDE and edge < -250
    assert n._map_status(None)[0] == NavStatus.MAP_AREA_OUTSIDE          # NO_FIX: the last position still counts
    assert [lvl for lvl, _ in logs] == ["warn", "warn"]


def test_unknown_without_a_map_or_once_the_last_position_is_too_old():
    n, _ = _node(hold_s=-1.0)
    n._map_status(_pos(35.88, 10.53))
    assert n._map_status(None)[0] == NavStatus.MAP_AREA_UNKNOWN
    n._map = None
    flag, edge = n._map_status(_pos(35.88, 10.53))
    assert flag == NavStatus.MAP_AREA_UNKNOWN and math.isnan(edge)
