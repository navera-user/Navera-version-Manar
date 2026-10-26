"""The star camera's field width measured from the stars (cn_subscriber._fov_for / _learn_fov): kept per
camera, narrows the next solves, and a failed narrow solve is tried once with the wide search."""
import math
from types import MethodType, SimpleNamespace

from cn_pkg.nodes.cn_subscriber import CNSubscriber


class _Log:
    def info(self, m):
        pass


def node(fov=float("nan")):
    n = SimpleNamespace(camera_fov_deg=fov, _fov_learned={}, _fov_failed=0)
    n.get_logger = lambda: _Log()
    n._fov_for = MethodType(CNSubscriber._fov_for, n)
    n._learn_fov = MethodType(CNSubscriber._learn_fov, n)
    return n


def test_unknown_width_is_measured_kept_and_used(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node()
    meta = {"lens_key": "cam1"}
    assert math.isnan(n._fov_for(meta))                        # first sky: the wide search
    n._learn_fov(meta, {"success": True, "field_width_deg": 61.7})
    assert n._fov_for(meta) == 61.7
    assert node()._fov_for(meta) == 61.7                       # the next start: kept for this camera
    assert math.isnan(node()._fov_for({"lens_key": "another camera"}))


def test_a_failed_narrow_solve_tries_the_wide_search_once(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node()
    meta = {"lens_key": "cam1"}
    n._learn_fov(meta, {"success": True, "field_width_deg": 40.0})
    n._learn_fov(meta, {"success": False})
    assert math.isnan(n._fov_for(meta))                        # this frame: wide
    n._learn_fov(meta, {"success": False})
    assert n._fov_for(meta) == 40.0                            # then narrow again


def test_a_configured_width_is_never_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node(30.0)
    n._learn_fov({"lens_key": "cam1"}, {"success": True, "field_width_deg": 61.7})
    assert n._fov_for({"lens_key": "cam1"}) == 30.0
