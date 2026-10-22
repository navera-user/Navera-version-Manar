"""B11: compass-free celestial fix for the narrow star camera (geoloc mode).

A synthetic plate solution (TAN WCS) of a camera mounted at a known rotation on a vehicle with a known attitude, at
a known place and time: the plate solve's whole rotation + 'up' from the IMU's roll/pitch must give the place back
whatever the heading (no compass); the one-direction method with the same heading error is far off.
"""
import json
import math
import os
import stat
import sys

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.io import fits
from astropy.time import Time

from cn_pkg.nodes import celestial_math as cm

UTC = "2026-10-31 21:30:00"
LAT, LON = 36.8, 10.2


def _haversine_km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _vec(c):
    ra, dec = math.radians(c.ra.deg), math.radians(c.dec.deg)
    return np.array([math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)])


def _R_icrs_enu(lat=LAT, lon=LON, utc=UTC):
    frame = AltAz(obstime=Time(utc), location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg), pressure=0)
    cols = [_vec(SkyCoord(alt=alt * u.deg, az=az * u.deg, frame=frame).icrs) for alt, az in ((0, 90), (0, 0), (90, 0))]
    R = np.column_stack(cols)
    U, _, Vt = np.linalg.svd(R)
    return U @ Vt


def _R_enu_body(yaw_deg, pitch_deg, roll_deg):
    from scipy.spatial.transform import Rotation
    return Rotation.from_euler("ZYX", [yaw_deg, pitch_deg, roll_deg], degrees=True).as_matrix()


def _quat(R):
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(R).as_quat()          # x, y, z, w


def _wcs_header(R_icrs_cam, width=1920, height=1080, scale_deg=0.03, mirror=False):
    x, y, z = R_icrs_cam[:, 0], R_icrs_cam[:, 1], R_icrs_cam[:, 2]
    if mirror:
        x = -x
    ra, dec = math.atan2(z[1], z[0]), math.asin(z[2])
    e = np.array([-math.sin(ra), math.cos(ra), 0.0])
    n = np.array([-math.sin(dec) * math.cos(ra), -math.sin(dec) * math.sin(ra), math.cos(dec)])
    h = fits.Header()
    h["CTYPE1"], h["CTYPE2"] = "RA---TAN", "DEC--TAN"
    h["CRVAL1"], h["CRVAL2"] = math.degrees(ra) % 360.0, math.degrees(dec)
    h["CRPIX1"], h["CRPIX2"] = (width - 1) / 2.0 + 1.0, (height - 1) / 2.0 + 1.0
    h["CD1_1"], h["CD1_2"] = scale_deg * float(x @ e), scale_deg * float(y @ e)
    h["CD2_1"], h["CD2_2"] = scale_deg * float(x @ n), scale_deg * float(y @ n)
    h["IMAGEW"], h["IMAGEH"] = width, height
    return h


def _scene(yaw=37.0, pitch=4.0, roll=-3.0, mount=(70.0, 30.0, 15.0)):
    R_eb = _R_enu_body(yaw, pitch, roll)
    Rcb = cm.mount_rotation(*mount)
    R_icrs_cam = _R_icrs_enu() @ R_eb @ Rcb.T
    return R_eb, Rcb, R_icrs_cam


def test_mount_rotation_is_a_rotation_and_points_where_boresight_altaz_says():
    rng = np.random.default_rng(0)
    for _ in range(50):
        el, az, rl = rng.uniform(10, 90), rng.uniform(0, 360), rng.uniform(-180, 180)
        Rcb = cm.mount_rotation(el, az, rl)
        assert np.allclose(Rcb @ Rcb.T, np.eye(3), atol=1e-12) and np.linalg.det(Rcb) > 0
        q = _quat(_R_enu_body(rng.uniform(0, 360), rng.uniform(-20, 20), rng.uniform(-20, 20)))
        alt, _ = cm.boresight_altaz(q, el, az)
        assert math.degrees(math.asin(cm.up_in_camera(q, Rcb)[2])) == pytest.approx(alt, abs=1e-9)


def test_rotation_from_the_plate_solution():
    _, _, R = _scene()
    got = cm.camera_rotation_from_wcs(_wcs_header(R))
    assert np.degrees(np.arccos(np.clip((np.trace(got.T @ R) - 1) / 2, -1, 1))) < 0.002


def test_a_mirrored_solution_is_refused():
    _, _, R = _scene()
    with pytest.raises(ValueError):
        cm.camera_rotation_from_wcs(_wcs_header(R, mirror=True))


@pytest.mark.parametrize("yaw", [0.0, 37.0, 135.0, 271.0])
def test_zenith_fix_is_right_and_needs_no_heading(yaw):
    R_eb, Rcb, R = _scene(yaw=yaw)
    R_wcs = cm.camera_rotation_from_wcs(_wcs_header(R))
    q = _quat(R_eb)
    lat, lon = cm.zenith_fix(R_wcs, cm.up_in_camera(q, Rcb), UTC)
    assert _haversine_km(lat, lon, LAT, LON) < 1.0
    q_bad = _quat(_R_enu_body(yaw + 25.0, 4.0, -3.0))          # the compass 25 deg off: 'up' does not change
    assert np.allclose(cm.up_in_camera(q_bad, Rcb), cm.up_in_camera(q, Rcb), atol=1e-12)


def test_compass_method_with_a_heading_error_is_far_off_and_zenith_is_not():
    """The B11 comparison on one scene: a 5 deg compass error moves the one-direction fix by tens to hundreds of
    km (depending on the hour angle); the zenith fix does not move."""
    R_eb, Rcb, R = _scene(yaw=37.0)
    R_wcs = cm.camera_rotation_from_wcs(_wcs_header(R))
    z = R_wcs[:, 2]
    ra, dec = math.degrees(math.atan2(z[1], z[0])) % 360.0, math.degrees(math.asin(z[2]))
    ra_a, dec_a = cm.apparent_radec(ra, dec, UTC)
    gast = cm.gast_deg(UTC)
    q_bad = _quat(_R_enu_body(42.0, 4.0, -3.0))
    alt, az = cm.boresight_altaz(q_bad, 70.0, 30.0)
    cands = cm.observer_candidates(alt, az, ra_a, dec_a, gast)
    compass_err = min(_haversine_km(a, b, LAT, LON) for a, b in cands) if cands else float("inf")
    lat, lon = cm.zenith_fix(R_wcs, cm.up_in_camera(q_bad, Rcb), UTC)
    assert compass_err > 50.0
    assert _haversine_km(lat, lon, LAT, LON) < 1.0


def test_wrong_roll_of_the_mount_costs_tilt_times_roll_error():
    """When the mount's roll is wrong by d, a level vehicle is still exact (the camera's 'up' is on its axis
    only for a zenith camera); the error grows with the vehicle tilt. Stated so a user knows what to measure."""
    R_eb, Rcb, R = _scene(yaw=10.0, pitch=0.0, roll=0.0, mount=(90.0, 0.0, 0.0))
    R_wcs = cm.camera_rotation_from_wcs(_wcs_header(R))
    lat, lon = cm.zenith_fix(R_wcs, cm.up_in_camera(_quat(R_eb), cm.mount_rotation(90.0, 0.0, 5.0)), UTC)
    assert _haversine_km(lat, lon, LAT, LON) < 1.0                  # level: the roll does not matter
    R_eb, Rcb, R = _scene(yaw=10.0, pitch=5.0, roll=0.0, mount=(90.0, 0.0, 0.0))
    R_wcs = cm.camera_rotation_from_wcs(_wcs_header(R))
    lat, lon = cm.zenith_fix(R_wcs, cm.up_in_camera(_quat(R_eb), cm.mount_rotation(90.0, 0.0, 5.0)), UTC)
    err = _haversine_km(lat, lon, LAT, LON)
    assert 30.0 < err < 70.0                                         # ~5 deg tilt x 5 deg roll = 0.44 deg = 48 km


def test_solver_passes_up_cam_and_reads_the_method(tmp_path, monkeypatch):
    """solve_image_b64_geoloc hands --up-cam to drone_sky_prep and reads back the method and the rotation."""
    from cn_pkg.nodes import solver
    stub = tmp_path / "stub_prep.py"
    log = tmp_path / "args.json"
    stub.write_text(
        "import json, sys\n"
        f"json.dump(sys.argv, open({str(log)!r}, 'w'))\n"
        "print('│  Log-odds        : 55.0')\n"
        "print('│  Method          : zenith (camera rotation + IMU up, no compass)')\n"
        "print('│  R_icrs_cam      : ' + ','.join(['1','0','0','0','1','0','0','0','1']))\n"
        "print('│  Latitude        : +36.800000°')\n"
        "print('│  Longitude       : +10.200000°')\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(solver, "DRONE_SKY_PREP", str(stub))
    import base64
    r = solver.solve_image_b64_geoloc(base64.b64encode(b"x").decode(), float("nan"), float("nan"), UTC,
                                      up_cam=[0.1, -0.2, 0.97])
    args = json.load(open(log))
    assert "--up-cam" in args and "--prior-lat" not in args
    assert [float(v) for v in args[args.index("--up-cam") + 1].split(",")] == pytest.approx([0.1, -0.2, 0.97])
    assert r["success"] and r["method"] == "zenith" and r["R_icrs_cam"] == [1, 0, 0, 0, 1, 0, 0, 0, 1]
    assert r["predicted_lat"] == pytest.approx(36.8)


rclpy = pytest.importorskip("rclpy") if os.environ.get("NAVERA_SKIP_ROS") != "1" else None


def _node(args):
    from cn_pkg.nodes import cn_subscriber as cs
    rclpy.init(args=["--ros-args", *args])
    n = cs.CNSubscriber()
    n.sent = []
    n.pub_est.publish = n.sent.append
    return n, cs


@pytest.mark.parametrize("with_roll", [True, False])
def test_node_uses_the_compass_free_fix_when_the_mount_is_known(monkeypatch, with_roll):
    args = ["-p", "camera_mount_elevation_deg:=70.0", "-p", "camera_mount_azimuth_deg:=30.0",
            "-p", "utc_time:=" + UTC]
    if with_roll:
        args += ["-p", "camera_mount_roll_deg:=15.0"]
    n, cs = _node(args)
    try:
        R_eb, Rcb, R = _scene()
        q = _quat(R_eb)
        n._imu_hist.append((1_000_000_000, tuple(q)))
        n._imu_hist.append((1_050_000_000, tuple(q)))
        calls = []

        def fake(b64, tilt, az, utc, plat, plon, fov, up_cam=None):
            calls.append({"up_cam": up_cam, "prior": (plat, plon)})
            out = {"success": True, "predicted_lat": LAT, "predicted_lon": LON, "log_odds": 60.0, "source": "stellar"}
            if up_cam is not None:
                out.update(method="zenith", R_icrs_cam=list(cm.camera_rotation_from_wcs(_wcs_header(R)).ravel()))
            return out
        monkeypatch.setattr(cs.cn_solver, "solve_image_b64_geoloc", fake)
        meta = {"frame_id": 1, "image_stamp_ns": 1_025_000_000}
        assert n._busy_lock.acquire(blocking=False)
        n._process_frame(1, np.zeros((60, 80, 3), np.uint8), meta)
        est = n.sent[-1]
        d = json.loads(est.details_json)
        if with_roll:
            assert calls[0]["up_cam"] is not None
            assert np.allclose(calls[0]["up_cam"], cm.up_in_camera(q, Rcb), atol=1e-9)
            assert all(math.isnan(v) for v in calls[0]["prior"])        # one answer: no prior needed
            assert d["fix_method"].startswith("zenith") and est.valid
        else:
            assert calls[0]["up_cam"] is None
            assert "compass" in d["fix_method"] and "camera_R_cam_body" in d["fix_method"]
    finally:
        n.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
