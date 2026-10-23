"""F39: the in-flight sigma calibration kept per camera across flights, and kept at a plain GPS loss."""
import time
from types import MethodType, SimpleNamespace

from day_pkg.fix_sigma import SigmaCalibration, load_stored, save_stored
from day_pkg.nodes.day_subscriber import DaySubscriber
from day_pkg.vision_nav import VisionNavigator


def _calibrated(err=14.0, model=8.0, n=20, t0=0.0):
    c = SigmaCalibration(30.0, 15)
    for i in range(n):
        c.add(err, model, t=t0 + i)
    return c


def test_a_stored_calibration_is_the_prior_until_this_flight_has_its_own():
    c = SigmaCalibration(30.0, 15)
    assert c.apply(8.0) == 30.0                                   # nothing known: the no-calibration floor
    assert c.set_prior(1.2, 5.0, "stored (cam)", inflation=1.3, floor_m=10.0)
    assert abs(c.apply(8.0) - max(1.3 * (((8.0 * 1.2) ** 2 + 25.0) ** 0.5), 10.0)) < 1e-9
    assert c.apply(1.0) == 10.0                                   # never below the floor
    assert c.state()["prior"]["in_use"]
    for i in range(15):                                           # this flight's own calibration takes over
        c.add(4.0, 8.0, t=float(i))
    assert c.terms() is not None and not c.state()["prior"]["in_use"]
    assert abs(c.apply(8.0) - (8.0 ** 2 + (4.0 / 2.4477) ** 2) ** 0.5) < 1e-3


def test_implausible_priors_are_refused():
    c = SigmaCalibration()
    assert not c.set_prior(0.5, 5.0) and not c.set_prior(float("nan"), 5.0) and not c.set_prior(1.0, -1.0)
    assert c.prior is None


def test_a_prior_contradicted_by_this_flights_samples_is_dropped():
    c = SigmaCalibration(30.0, 15)
    c.set_prior(1.0, 2.0, "stored (cam)", inflation=1.0, floor_m=5.0)   # states ~8 m for an 8 m model
    c.add(10.0, 8.0, t=0.0)
    assert c.prior is not None                                    # within 3 sigma
    c.add(40.0, 8.0, t=1.0)
    c.add(45.0, 8.0, t=2.0)                                       # two beyond 3 sigma: another camera / terrain
    assert c.prior is None and "beyond 3 sigma" in c.state()["prior_dropped"]
    assert c.apply(8.0) == 30.0                                   # back to the no-calibration floor


def test_export_leaves_out_the_samples_a_late_refusal_could_roll_back():
    c = _calibrated(n=20)
    assert c.export(until_t=10.0) is None                         # 11 samples up to t = 10: too few
    e = c.export(until_t=17.0)
    assert e["samples"] == 18 and e["f"] >= 1.0 and abs(e["b"] - 14.0 / 2.4477) < 0.01
    assert c.export()["samples"] == 20


def test_store_round_trip_age_and_key(tmp_path):
    assert save_stored("hik lens.yaml", {"f": 1.5, "b": 6.2, "samples": 20}, str(tmp_path))
    kept = load_stored("hik lens.yaml", 86400.0, str(tmp_path))
    assert kept["f"] == 1.5 and kept["b"] == 6.2 and kept["samples"] == 20 and kept["saved_at"] <= time.time()
    assert load_stored("other.yaml", 86400.0, str(tmp_path)) is None
    assert load_stored("hik lens.yaml", -1.0, str(tmp_path)) is None   # too old
    assert save_stored("hik lens.yaml", None, str(tmp_path))
    assert load_stored("hik lens.yaml", 86400.0, str(tmp_path)) is None  # forgotten


def _node(refused):
    logs = []
    n = SimpleNamespace(calib_rollback_s=60.0, sigma_cal=_calibrated(t0=time.time() - 30.0),
                        map_bias=VisionNavigator(), _gps_refused_flag=refused, mount_cal=None,
                        get_logger=lambda: SimpleNamespace(info=logs.append))
    n._rollback_gps_learning = MethodType(DaySubscriber._rollback_gps_learning, n)
    n._save_mount_cal = MethodType(DaySubscriber._save_mount_cal, n)
    return n, logs


def test_a_plain_gps_loss_keeps_the_sigma_samples_a_refusal_forgets_them():
    lost, logs = _node(refused=False)                             # jammed right after take-off (Isaac 2026-10-22)
    lost._rollback_gps_learning()
    assert lost.sigma_cal.samples == 20 and any("keeps its 20 samples" in m for m in logs)
    refused, _ = _node(refused=True)                              # refused: a slow spoof may be in them
    refused._rollback_gps_learning()
    assert refused.sigma_cal.samples == 0


def test_the_node_saves_once_a_minute_and_at_the_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    logs = []
    n = SimpleNamespace(_sigma_store_key="cam.yaml", _sigma_store_t=0.0, _sigma_store_saved=None,
                        calib_rollback_s=60.0, sigma_cal=_calibrated(t0=time.time() - 30.0),
                        get_logger=lambda: SimpleNamespace(info=logs.append))
    n._sigma_store_save = MethodType(DaySubscriber._sigma_store_save, n)
    n._sigma_store_save()                                         # samples < 60 s old: nothing safe to keep yet
    assert load_stored("cam.yaml", 3600.0) is None
    n._sigma_store_save(final=True)                               # at the GPS loss (after the rollback rule)
    assert load_stored("cam.yaml", 3600.0)["samples"] == 20 and logs
