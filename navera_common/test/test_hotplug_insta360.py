"""Hot-plug and the Insta360 kit: a One R put in USB Android mode after boot fills the idle camera
and attitude (sysfs only, the camera never opened); a working source is never replaced.
"""
from unittest import mock

from navera_common import discovery as disc
from navera_common import hotplug


def boot(found, env=None):
    d = disc.decide(found, env or {})
    return {"found": found, "settings": d["settings"], "report": d["report"], "idle": d["idle"]}


def test_the_listing_includes_the_insta360_by_usb_id():
    with mock.patch.object(disc, "serial_ports", return_value=[]), \
            mock.patch.object(disc, "can_interfaces", return_value=[]), \
            mock.patch.object(disc, "probe_cameras", return_value={"usb": [], "csi": [], "insta360": []}), \
            mock.patch.object(disc, "probe_insta360", return_value=["1-2.1"]):
        now = hotplug.devices({})
    assert now["insta360"] == ["1-2.1"]
    assert hotplug.added({"insta360": []}, now)["insta360"] == ["1-2.1"]


def test_an_insta360_plugged_after_boot_fills_camera_and_attitude():
    doc = boot({"cameras": {"usb": [], "csi": [], "insta360": []}})
    assert "camera" in doc["idle"] and "attitude" in doc["idle"]
    frag = hotplug.probe({"insta360": ["1-2.1"]}, {})
    found = hotplug.merge(doc["found"], frag)
    assert found["cameras"]["insta360"] == ["1-2.1"]
    r = hotplug.fill_idle(doc, found, {}, armed=None, stamp="12:00:00")
    s = r["settings"]
    assert s["NAVERA_CAMERA_INPUT"] == "insta360" and s["NAVERA_SENSOR_SOURCE"] == "insta360"
    assert "camera" not in r["idle"] and "attitude" not in r["idle"]


def test_a_working_attitude_is_kept_when_the_insta360_appears():
    doc = boot({"i2c": {"imu": {"bus": 1}}, "cameras": {"usb": [], "csi": [], "insta360": []}})
    assert "attitude" not in doc["idle"]
    found = hotplug.merge(doc["found"], hotplug.probe({"insta360": ["1-2.1"]}, {}))
    r = hotplug.fill_idle(doc, found, {}, armed=False)
    assert r["settings"]["NAVERA_SENSOR_SOURCE"] == "box" and r["settings"]["NAVERA_CAMERA_INPUT"] == "insta360"
