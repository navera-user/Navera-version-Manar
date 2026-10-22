"""Discovery of the Insta360 kit: a One R in USB Android mode (2e1a:0002) is the camera AND, when
no better attitude source is found, the IMU; it is found from sysfs without opening it.
"""
import os

from navera_common.discovery import decide, probe_insta360

AP = {"kind": "mavlink", "url": "serial:/dev/ttyTHS2:921600", "sysid": 1, "compid": 1, "type": 2, "autopilot": 3}
STREAMS = {"ATTITUDE": True, "GPS2_RAW": True, "gps1_type": 1, "gps2_type": 1}
KIT = {"usb": [], "csi": [], "insta360": ["1-2.1"]}


def _usb_dev(root, name, vid, pid):
    d = os.path.join(root, name)
    os.makedirs(d)
    open(os.path.join(d, "idVendor"), "w").write(vid + "\n")
    open(os.path.join(d, "idProduct"), "w").write(pid + "\n")


def test_probe_reads_the_usb_id_from_sysfs(tmp_path):
    _usb_dev(tmp_path, "1-2.1", "2e1a", "0002")                 # the One R in Android mode
    _usb_dev(tmp_path, "1-2.3", "04ca", "004f")                 # a keyboard
    _usb_dev(tmp_path, "1-2.4", "2e1a", "0001")                 # another mode: not the kit
    os.makedirs(tmp_path / "1-0:1.0")                           # an interface: no id files
    assert probe_insta360(str(tmp_path)) == ["1-2.1"]
    assert probe_insta360(str(tmp_path / "missing")) == []


def test_the_insta360_kit_alone_is_camera_and_attitude():
    d = decide({"cameras": KIT}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "insta360" and s["NAVERA_CAMERA_INPUT"] == "insta360"
    assert "NAVERA_CAMERA_DEVICE" not in s
    assert any("Insta360" in r for r in d["report"] if r.startswith("found"))


def test_a_better_attitude_source_wins_the_camera_stays_the_kit():
    d = decide({"serial": [AP], "cameras": KIT, "autopilot_streams": STREAMS}, {})
    assert d["settings"]["NAVERA_SENSOR_SOURCE"] == "vehicle" and d["settings"]["NAVERA_CAMERA_INPUT"] == "insta360"
    d = decide({"i2c": {"imu": {"bus": 1}}, "cameras": KIT}, {})
    assert d["settings"]["NAVERA_SENSOR_SOURCE"] == "box"


def test_written_settings_win():
    d = decide({"cameras": KIT}, {"NAVERA_SENSOR_SOURCE": "box", "NAVERA_CAMERA_INPUT": "csi"})
    assert "NAVERA_SENSOR_SOURCE" not in d["settings"] and "NAVERA_CAMERA_INPUT" not in d["settings"]


def test_webcam_mode_is_flagged():
    d = decide({"cameras": {"usb": ["/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0"], "csi": []}}, {})
    assert d["settings"]["NAVERA_CAMERA_INPUT"] == "usb"
    assert any(r.startswith("CHECK") and "Android" in r for r in d["report"])
