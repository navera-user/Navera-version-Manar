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
