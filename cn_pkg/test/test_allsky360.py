"""cn_pkg 360 all-sky mode: shared solver, offline catalogue, camera-to-body mount, tilt calibration, node glue.

The end-to-end cases render synthetic frames with the simulator (navera_tools/sim/celestial360_conditions.py):
SIMULATION ONLY. Run from the repository root (PYTHONPATH=.:cn_pkg:navera_common).
"""
import math
import os

import numpy as np
import pytest

from cn_pkg import allsky, allsky_mount
from cn_pkg.allsky_locator import AllSkyLocator

BSC5 = os.path.expanduser("~/.navera_sim/bsc5.dat")
need_bsc5 = pytest.mark.skipif(not os.path.exists(BSC5), reason="Yale catalogue (bsc5.dat) not installed")


def _sim():
    try:
        from navera_tools.sim import celestial360_conditions as cc
    except ImportError:
        pytest.skip("simulator (navera_tools) not on the path")
    return cc


def _rot(rng):
    from scipy.spatial.transform import Rotation
    return Rotation.from_quat(rng.normal(size=4)).as_matrix()


@pytest.fixture(scope="module")
def cat():
    return allsky.Catalogue(limit_mag=4.0, path=allsky.BUNDLED_CATALOGUE)


# ── sharing and offline ──────────────────────────────────────────────

def test_field_tools_use_the_same_modules():
    try:
        from navera_tools.field import allsky as field_allsky, sky360 as field_sky360
    except ImportError:
        pytest.skip("navera_tools not on the path")
    from cn_pkg import sky360
    assert field_allsky is allsky and field_sky360 is sky360     # one module: live knobs act on both


@need_bsc5
def test_bundled_catalogue_is_bsc5():
    ra, dec, mag = allsky.load_bsc5(BSC5)
    rb, db, mb = allsky.load_bsc5(allsky.BUNDLED_CATALOGUE)
    k = mag <= 4.5
    assert np.array_equal(rb, ra[k]) and np.array_equal(db, dec[k]) and np.array_equal(mb, mag[k])


def test_catalogue_is_never_downloaded(tmp_path):
    with pytest.raises(FileNotFoundError):
        allsky.Catalogue(path=str(tmp_path / "bsc5.dat"))
    with pytest.raises(FileNotFoundError):
        allsky.Catalogue(work_dir=str(tmp_path))


def test_bundled_catalogue_loads(cat):
    assert 400 < len(cat.vec) < 700 and cat.mag.max() <= 4.0


# ── mount rotation ───────────────────────────────────────────────────

def test_up_standing_camera_level_vehicle():
    up = allsky_mount.up_camera_from_body((0, 0, 0, 1), allsky_mount.R_CAM_BODY_STANDING)
    assert np.allclose(up, [1, 0, 0])                            # camera +x is up when standing


def test_up_follows_vehicle_pitch_and_any_mount():
    from scipy.spatial.transform import Rotation
    rng = np.random.default_rng(0)
    for _ in range(20):
        M = _rot(rng)
        R_enu_body = Rotation.from_rotvec(rng.normal(size=3) * 0.5)
        up = allsky_mount.up_camera_from_body(R_enu_body.as_quat(), M)
        assert np.allclose(up, M @ R_enu_body.as_matrix().T @ [0, 0, 1], atol=1e-12)
    # nose up 10 deg (body x = east tilted up): in the body 'up' leans 10 deg forward, i.e. towards camera -z
    q = Rotation.from_euler("y", -10, degrees=True).as_quat()
    up = allsky_mount.up_camera_from_body(q, allsky_mount.R_CAM_BODY_STANDING)
    assert math.degrees(math.atan2(up[2], up[0])) == pytest.approx(-10.0, abs=1e-9)


def test_rotation_matrix_checks():
    R = allsky_mount.rotation_matrix(np.round(_rot(np.random.default_rng(1)), 4).ravel())
    assert np.allclose(R @ R.T, np.eye(3)) and np.linalg.det(R) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        allsky_mount.rotation_matrix(np.diag([1.0, 1.0, -1.0]).ravel())     # a mirror
    with pytest.raises(ValueError):
        allsky_mount.rotation_matrix(2 * np.eye(3).ravel())


# ── tilt of 'up' learned on a reference (GPS) then frozen ────────────

def test_tilt_calibration_removes_a_mount_tilt():
    rng = np.random.default_rng(7)
    lat, lon = 36.8, 10.2
    w_true = np.radians(1.0) * np.array([0.0, 0.6, 0.8])        # 1 deg tilt, perpendicular to 'up' (+x)
    cal = allsky_mount.TiltCalibration(min_samples=4, max_samples=6)
    errs_raw, errs_cal = [], []
    for i in range(10):
        utc = f"2026-10-18 0{i % 4}:{10 + i:02d}:00"
        z = allsky_mount.zenith_icrs(lat, lon, utc)
        up_true = np.array([1.0, 0.02 * rng.normal(), 0.02 * rng.normal()])
        up_true /= np.linalg.norm(up_true)
        # R_icrs_imu with R @ up_true = z (any turn about it)
        a = np.cross(up_true, z)
        s, c = np.linalg.norm(a), float(up_true @ z)
        R = allsky_mount.rotvec(a / s * math.atan2(s, c))
        R = allsky_mount.rotvec(z * rng.uniform(0, 6.28)) @ R
        up_meas = allsky_mount.rotvec(-w_true) @ up_true            # what the tilted accelerometer reports
        la, lo = allsky_mount.position(R @ up_meas, utc)
        errs_raw.append(math.hypot(la - lat, (lo - lon) * math.cos(math.radians(lat))) * 111.2)
        got = cal.corrected(R, up_meas, utc)
        if got is not None:
            errs_cal.append(math.hypot(got[0] - lat, (got[1] - lon) * math.cos(math.radians(lat))) * 111.2)
        cal.add(R, up_meas, z)
    assert cal.frozen and len(cal.samples) == 6
    assert min(errs_raw) > 100.0                                    # 1 deg = 111 km on every raw fix
    assert len(errs_cal) == 6 and max(errs_cal) < 1.0               # after the 4th sample: corrected
    assert math.degrees(np.linalg.norm(cal.fit["w"])) == pytest.approx(1.0, abs=0.01)
    assert cal.fit["sigma_deg"] == allsky_mount.CAL_SIGMA_FLOOR_DEG


def test_fit_tilt_is_the_field_servers_fit():
    """fit_tilt is what the field server applies (server._tilt_corrected): same Q, residual and floor. These samples
    are random (nothing agrees), so the plain fit is compared; the robust one refuses them (no majority)."""
    rng = np.random.default_rng(3)
    samples = []
    for _ in range(5):
        z = rng.normal(size=3)
        z /= np.linalg.norm(z)
        up = np.array([1.0, 0.0, 0.0]) + 0.01 * rng.normal(size=3)
        samples.append((_rot(rng), up, z))
    fit = allsky_mount.fit_tilt(samples, 0.05, robust=False)
    w = allsky_mount.fit_mount(samples)
    assert np.allclose(fit["w"], w) and np.allclose(fit["Q"], allsky_mount.rotvec(w))
    assert fit["n"] == 5 and fit["sigma_deg"] == max(fit["rms_deg"], 0.05)
    assert not allsky_mount.fit_tilt(samples, 0.05)["ok"]


# ── 'up' sources and gates of the locator ────────────────────────────

def test_up_sources(cat):
    loc = AllSkyLocator(catalogue=cat)
    up, src, why = loc.up({"up_imu": [2.0, 0.0, 0.0]})
    assert src == "camera" and why is None and np.allclose(up, [1, 0, 0])
    up, src, why = loc.up({}, (0, 0, 0, 1))
    assert src == "vehicle" and np.allclose(up, [1, 0, 0])
    assert loc.up({}, None)[0] is None
    up, _, why = loc.up({"up_imu": [1, 0, 0], "accel_g": 1.05})      # braking: 'up' is not gravity
    assert up is None and "accelerating" in why
    assert AllSkyLocator(catalogue=cat, up_source="camera").up({}, (0, 0, 0, 1))[0] is None
    with pytest.raises(ValueError):
        AllSkyLocator(catalogue=cat, up_source="compass")


def test_no_up_no_fix(cat):
    out = AllSkyLocator(catalogue=cat, up_source="vehicle").process(np.zeros((1920, 3840), np.uint8),
                                                                    "2026-10-18 01:00:00", {})
    assert not out["success"] and "attitude" in out["error"]


# ── end to end on simulated frames (SIMULATION ONLY) ─────────────────

def _frame(cc, cond, seed):
    sc = cc.Scene(cond, seed)
    frame = cc.render(sc)
    up, gate = cc.solver_up(sc)
    assert gate is None
    return sc, frame, up


@need_bsc5
def test_sim_vehicle_mount_gives_the_field_fix(cat):
    """A camera mounted at an arbitrary angle on the vehicle: 'up' from the vehicle attitude through R_cam_body
    gives the same fix as the field path (camera accelerometer), within 50 km of the truth, with its sigma."""
    cc = _sim()
    from navera_tools.sim.allsky_cn_parity import vehicle_attitude
    from navera_tools.field.reprocess360 import haversine_km
    cond = cc.Condition("baseline mag<=3")
    sc, frame, up = _frame(cc, cond, 0)
    field = allsky.locate(frame, up, sc.utc, cat, f_scales=(1.0,))
    assert field["solved"]
    M = _rot(np.random.default_rng(11))
    loc = AllSkyLocator(catalogue=cat, f_scale_search=(1.0,), R_cam_body=M, up_source="vehicle")
    out = loc.process(frame, sc.utc, {}, vehicle_attitude(up, M, 123.0))
    assert out["success"], out.get("error")
    assert haversine_km(out["predicted_lat"], out["predicted_lon"], field["lat"], field["lon"]) < 0.01
    assert haversine_km(out["predicted_lat"], out["predicted_lon"], cond.lat, cond.lon) < cc.WRONG_KM
    sig = math.hypot(allsky_mount.ATTITUDE_SIGMA_360_DEG, field["sigma_fit_deg"]) * 111.2      # the server's sigma
    assert out["sigma_m"] / 1000.0 == pytest.approx(sig, abs=0.1)
    assert loc.f_scale == field["f_scale"]


@need_bsc5
def test_sim_junk_is_refused(cat):
    cc = _sim()
    cond = cc.Condition("JUNK 60 random points", junk=True, effects={"random_points": 60})
    sc, frame, up = _frame(cc, cond, 0)
    out = AllSkyLocator(catalogue=cat, f_scale_search=(1.0,)).process(frame, sc.utc, {"up_imu": list(up)})
    assert not out["success"]


@need_bsc5
def test_sim_tilt_learned_from_gps_then_corrected(cat):
    """A 1 deg mount error: raw fixes ~111 km off; once the tilt is learned on fixes with a GPS reference, the
    later fixes (no reference) are corrected."""
    cc = _sim()
    from navera_tools.field.reprocess360 import haversine_km
    cond = cc.Condition("baseline, level", tilt_deg=0.0)
    tilt = allsky_mount.rotvec(np.radians(1.0) * np.array([0.0, 0.8, -0.6]))     # 1 deg, perpendicular to 'up'
    loc = AllSkyLocator(catalogue=cat, f_scale_search=(1.0,), cal_min_samples=3, cal_samples=3)
    errs = []
    for seed in range(5):
        sc, frame, up = _frame(cc, cond, seed)
        up = tilt @ up                                  # the mount / accelerometer tilt: the same on every frame
        ref = (cond.lat, cond.lon) if seed < 3 else None
        out = loc.process(frame, sc.utc, {"up_imu": list(up), "stopped": True}, reference=ref)
        assert out["success"], out.get("error")
        errs.append((haversine_km(out["raw_lat"], out["raw_lon"], cond.lat, cond.lon),
                     haversine_km(out["predicted_lat"], out["predicted_lon"], cond.lat, cond.lon), out))
    assert loc.cal.frozen
    assert all(raw > 60.0 for raw, _, _ in errs)
    for raw, cal, out in errs[3:]:
        assert cal < 15.0 and "tilt_cal" in out
        assert cal <= 3 * out["sigma_m"] / 1000.0


# ── node glue (ROS 2) ────────────────────────────────────────────────

@need_bsc5
def test_node_publishes_allsky_fix_with_sigma():
    cc = _sim()
    rclpy = pytest.importorskip("rclpy")
    from cn_pkg.nodes import cn_subscriber as cs
    cond = cc.Condition("baseline mag<=3")
    sc, frame, up = _frame(cc, cond, 1)
    rclpy.init(args=["--ros-args", "-p", "solver_mode:=allsky360", "-p", "allsky_f_scale_search:=[1.0]"])
    try:
        node = cs.CNSubscriber()
        sent = []
        node.pub_est.publish = sent.append
        meta = {"frame_id": 3, "utc_time": sc.utc, "up_imu": [float(v) for v in up], "stopped": True}
        node._publish_result(3, meta, node._solve_allsky(frame, meta))
        est = sent[-1]
        assert est.valid and est.model_id == "allsky360"
        from navera_tools.field.reprocess360 import haversine_km
        assert haversine_km(est.latitude, est.longitude, cond.lat, cond.lon) < cc.WRONG_KM
        assert est.position_covariance_type == est.COVARIANCE_TYPE_APPROXIMATED
        import json
        d = json.loads(est.details_json)
        assert est.position_covariance[0] == pytest.approx(d["sigma_m"] ** 2)
        assert d["up_source"] == "camera" and d["matched"] >= allsky.MIN_MATCHED
        # a frame without 'up' (no camera up_imu, no IMU) is declared invalid, never published as a fix
        meta2 = {"frame_id": 4, "utc_time": sc.utc}
        node._publish_result(4, meta2, node._solve_allsky(frame, meta2))
        assert not sent[-1].valid
        node.destroy_node()
    finally:
        rclpy.shutdown()
