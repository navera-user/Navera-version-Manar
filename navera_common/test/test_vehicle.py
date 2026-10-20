"""Unit tests for the installation's vehicle settings (maximum speed)."""
import pytest

from navera_common.vehicle import ENV_MAX_SPEED_KMH, max_speed_mps_from_env, max_speed_params


def test_unset_or_empty_keeps_the_node_defaults():
    assert max_speed_mps_from_env({}) is None
    assert max_speed_mps_from_env({ENV_MAX_SPEED_KMH: "  "}) is None
    assert max_speed_params({}) == {}


@pytest.mark.parametrize("kmh,mps", [("108", 30.0), ("900", 250.0), (" 36.0 ", 10.0)])
def test_km_per_hour_becomes_metres_per_second(kmh, mps):
    assert max_speed_mps_from_env({ENV_MAX_SPEED_KMH: kmh}) == pytest.approx(mps)
    assert max_speed_params({ENV_MAX_SPEED_KMH: kmh}) == {"max_speed_mps": pytest.approx(mps)}


@pytest.mark.parametrize("bad", ["fast", "0", "-50", "3", "5000", "nan"])
def test_a_wrong_value_stops_the_node(bad):
    with pytest.raises(ValueError, match=ENV_MAX_SPEED_KMH):
        max_speed_mps_from_env({ENV_MAX_SPEED_KMH: bad})


from navera_common.vehicle import imu_params  # noqa: E402


def test_imu_settings():
    assert imu_params({}) == {}
    assert imu_params({"NAVERA_IMU_MOUNT_RPY": "0, 180,-90", "NAVERA_DECLINATION_DEG": "3.3"}) == {
        "mount_roll_deg": 0.0, "mount_pitch_deg": 180.0, "mount_yaw_deg": -90.0, "declination_deg": 3.3}


@pytest.mark.parametrize("env", [{"NAVERA_IMU_MOUNT_RPY": "1,2"}, {"NAVERA_IMU_MOUNT_RPY": "0,0,400"},
                                 {"NAVERA_DECLINATION_DEG": "east"}, {"NAVERA_DECLINATION_DEG": "120"}])
def test_bad_imu_settings_stop_the_node(env):
    with pytest.raises(ValueError, match="NAVERA_"):
        imu_params(env)


from navera_common.vehicle import live_camera_params, sensor_topics  # noqa: E402


def test_sensor_source_box_is_the_default():
    t = sensor_topics({})
    assert t["sensor_source"] == "box" and t["imu_topic"] == "/navera/sensors/imu"


def test_vehicle_and_ros_sources():
    assert sensor_topics({"NAVERA_SENSOR_SOURCE": "vehicle"})["imu_topic"] == "/navera/vehicle/imu"
    t = sensor_topics({"NAVERA_SENSOR_SOURCE": "ros", "NAVERA_ROS_IMU_TOPIC": "/mavros/imu/data",
                       "NAVERA_ROS_GPS_TOPIC": "/mavros/global_position/raw/fix"})
    assert t["imu_topic"] == "/mavros/imu/data" and t["gps_topic"] == "/mavros/global_position/raw/fix"
    with pytest.raises(ValueError, match="NAVERA_ROS_IMU_TOPIC"):
        sensor_topics({"NAVERA_SENSOR_SOURCE": "ros"})
    with pytest.raises(ValueError, match="NAVERA_SENSOR_SOURCE"):
        sensor_topics({"NAVERA_SENSOR_SOURCE": "satellite"})


def test_live_camera_settings():
    p = live_camera_params({"NAVERA_CAMERA_DEVICE": "/dev/video2", "NAVERA_CAMERA_SIZE": "1920x1080",
                            "NAVERA_CAMERA_CALIBRATION": "/etc/navera/camera.yaml",
                            "NAVERA_CAMERA_MOUNT_RPY": "0,-5,180", "NAVERA_SENSOR_SOURCE": "vehicle"})
    assert (p["device"], p["width"], p["height"]) == ("/dev/video2", 1920, 1080)
    assert (p["mount_pitch_deg"], p["mount_yaw_deg"]) == (-5.0, 180.0)
    assert p["imu_topic"] == "/navera/vehicle/imu" and p["calibration_file"] == "/etc/navera/camera.yaml"
    with pytest.raises(ValueError, match="CALIBRATION"):
        live_camera_params({})
    with pytest.raises(ValueError, match="SIZE"):
        live_camera_params({"NAVERA_CAMERA_HFOV_DEG": "84", "NAVERA_CAMERA_SIZE": "big"})


def test_fixed_camera_on_a_fast_multirotor_is_flagged():
    from navera_common.vehicle import camera_mount_advice
    assert "gimbal" in camera_mount_advice("drone", 15.0, gimbal=False)
    assert camera_mount_advice("drone", 15.0, gimbal=True) is None
    assert camera_mount_advice("drone", 8.0, gimbal=False) is None
    assert camera_mount_advice("boat", 20.0, gimbal=False) is None


def test_camera_identity_follows_the_by_id_link(tmp_path):
    from navera_common.vehicle import camera_identity
    dev = tmp_path / "video3"
    dev.write_text("")
    by_id = tmp_path / "by-id"
    by_id.mkdir()
    (by_id / "usb-Insta360_ONE_R_SN123-video-index0").symlink_to(dev)
    assert camera_identity(str(dev), str(by_id)) == "usb-Insta360_ONE_R_SN123-video-index0"
    assert camera_identity(str(tmp_path / "video9"), str(by_id)) is None
    assert camera_identity(str(dev), str(tmp_path / "missing")) is None


@pytest.mark.parametrize("key,value", [("NAVERA_CAMERA_FPS", "0"), ("NAVERA_CAMERA_FPS", "nan"),
                                       ("NAVERA_CAMERA_HFOV_DEG", "180"), ("NAVERA_CAMERA_MAX_TILT_DEG", "90"),
                                       ("NAVERA_CAMERA_LATENCY_S", "-1"), ("NAVERA_CAMERA_SIZE", "0x0")])
def test_camera_settings_out_of_range_are_refused(key, value):
    from navera_common.vehicle import live_camera_params
    env = {"NAVERA_CAMERA_HFOV_DEG": "84", key: value}
    with pytest.raises(ValueError):
        live_camera_params(env)


def test_imu_topic_and_shadow_mode_follow_the_settings():
    from navera_common.vehicle import imu_topic_params, shadow_mode_from_env
    assert imu_topic_params({}) == {"imu_topic": "/navera/sensors/imu"}
    assert imu_topic_params({"NAVERA_SENSOR_SOURCE": "vehicle"}) == {"imu_topic": "/navera/vehicle/imu"}
    assert (imu_topic_params({"NAVERA_SENSOR_SOURCE": "ros", "NAVERA_ROS_IMU_TOPIC": "/boat/imu"})
            == {"imu_topic": "/boat/imu"})
    assert imu_topic_params({"NAVERA_SENSOR_SOURCE": "bad"}) == {"imu_topic": "/navera/sensors/imu"}
    assert shadow_mode_from_env({"NAVERA_SHADOW_MODE": "true"}) == "true"
    assert shadow_mode_from_env({}) == "false"
