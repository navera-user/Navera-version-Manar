"""Hot-plug: a device connected after boot fills an idle source, never a working one, and the
GPS never switches while the vehicle is armed (no hardware: probes are replaced).
"""
import json

from navera_common import discovery as disc
from navera_common import hotplug

GPS = {"kind": "ubx", "port": "/dev/ttyUSB0", "baud": 230400, "fix": True, "satellites": True, "nmea": False}
AP = {"kind": "mavlink", "url": "serial:/dev/ttyACM0:115200", "sysid": 1, "compid": 1, "type": 2, "autopilot": 3}
STREAMS = {"ATTITUDE": True, "GPS2_RAW": False, "gps1_type": 14, "gps2_type": 0}


def boot(found, env=None):
    d = disc.decide(found, env or {})
    return {"found": found, "settings": d["settings"], "report": d["report"], "idle": d["idle"]}


def test_a_usb_gps_plugged_after_boot_fills_the_idle_gps_only():
    doc = boot({"i2c": {"imu": {"bus": 1}}, "cameras": {"usb": ["/dev/v4l/by-id/cam-video-index0"]}})
    assert doc["idle"] == ["gps", "autopilot"] and doc["settings"]["NAVERA_GPS_SOURCE"] == "none"
    found = hotplug.merge(doc["found"], {"serial": [GPS]})
    r = hotplug.fill_idle(doc, found, {}, armed=None, stamp="12:00:00")
    s = r["settings"]
    assert r["changed"] and r["idle"] == ["autopilot"]
    assert (s["NAVERA_GPS_SOURCE"], s["NAVERA_GPS_PORT"], s["NAVERA_GPS_BAUD"]) == ("serial", "/dev/ttyUSB0", "230400")
    # the working sources are untouched
    for k in ("NAVERA_SENSOR_SOURCE", "NAVERA_CAMERA_INPUT", "NAVERA_CAMERA_DEVICE", "NAVERA_BOX_IMU"):
        assert s[k] == doc["settings"][k]
    assert any(line.startswith("hot-plug 12:00:00: GPS: serial") for line in r["report"])


def test_a_working_gps_is_never_replaced():
    doc = boot({"serial": [dict(GPS, port="/dev/ttyTHS1", baud=9600, kind="nmea")]})
    assert "gps" not in doc["idle"]
    found = hotplug.merge(doc["found"], {"serial": [GPS]})          # a second, better receiver appears
    r = hotplug.fill_idle(doc, found, {}, armed=False)
    assert r["settings"]["NAVERA_GPS_PORT"] == "/dev/ttyTHS1" and not any("GPS:" in x for x in r["report"])


def test_never_switch_the_gps_while_armed_or_when_armed_is_unknown_with_an_autopilot():
    doc = boot({"serial": [AP], "autopilot_streams": STREAMS})
    assert doc["idle"] == ["gps", "camera"] and doc["settings"]["NAVERA_VEHICLE_MAVLINK_URL"] == AP["url"]
    found = hotplug.merge(doc["found"], {"serial": [GPS]})
    for armed, why in ((True, "armed"), (None, "not known yet")):
        r = hotplug.fill_idle(doc, found, {}, armed=armed)
        assert not r["changed"] and r["deferred"] == ["gps"] and r["settings"]["NAVERA_GPS_SOURCE"] == "none"
        assert any(why in x for x in r["report"])
    r = hotplug.fill_idle(doc, found, {}, armed=False)              # landed / disarmed: now
    assert r["changed"] and r["settings"]["NAVERA_GPS_SOURCE"] == "serial"


def test_an_autopilot_plugged_later_fills_the_link_and_the_attitude():
    doc = boot({})
    assert set(doc["idle"]) == {"gps", "attitude", "camera", "autopilot"}
    found = hotplug.merge(doc["found"], {"serial": [AP]})
    found["autopilot_streams"] = dict(STREAMS, gps1_type=2, gps2_type=14)    # its GPS1 real, NAVERA = GPS2
    r = hotplug.fill_idle(doc, found, {}, armed=None)
    s = r["settings"]
    assert s["NAVERA_VEHICLE_MAVLINK_URL"] == AP["url"] and s["NAVERA_SENSOR_SOURCE"] == "vehicle"
    assert r["deferred"] == ["gps"]                                 # armed state unknown until the link runs
    doc2 = dict(doc, settings=s, idle=r["idle"])
    r2 = hotplug.fill_idle(doc2, found, {}, armed=False)
    assert r2["settings"]["NAVERA_GPS_SOURCE"] == "vehicle_gps1" and "camera" in r2["idle"]


def test_written_settings_are_never_filled():
    doc = boot({}, {"NAVERA_GPS_SOURCE": "serial", "NAVERA_GPS_PORT": "/dev/ttyTHS1"})
    assert "gps" not in doc["idle"]


def test_the_loop_probes_only_new_devices_and_rewrites_discovered_env(tmp_path, monkeypatch):
    doc = boot({"i2c": {"imu": {"bus": 1}}})
    jp, ep = tmp_path / "discovery.json", tmp_path / "discovered.env"
    jp.write_text(json.dumps(doc))
    disc.write_env(doc["settings"], str(ep))
    states = [{"serial": ["/dev/ttyTHS1"], "can": [], "cameras": []}] * 2 + \
             [{"serial": ["/dev/ttyTHS1", "/dev/ttyUSB0"], "can": [], "cameras": []}] * 2
    monkeypatch.setattr(hotplug, "devices", lambda env: states.pop(0))      # boot, pass 1, pass 2, pass 3
    probed = []

    def fake_probe(path, *a, **k):
        probed.append(path)
        return GPS if path == "/dev/ttyUSB0" else None
    monkeypatch.setattr(disc, "probe_serial_port", fake_probe)
    logs = []
    hotplug.run({}, str(jp), str(ep), lambda: None, interval_s=0, rescan_s=1e9, log=logs.append, passes=3)
    assert probed == ["/dev/ttyUSB0"]                              # only the new port, once
    env_text = ep.read_text()
    assert "NAVERA_GPS_SOURCE=serial" in env_text and "NAVERA_GPS_PORT=/dev/ttyUSB0" in env_text
    saved = json.loads(jp.read_text())
    assert "gps" not in saved["idle"] and any("hot-plug" in r for r in saved["report"])
    assert any("new /dev/ttyUSB0" in x for x in logs)


def test_while_the_gps_is_missing_the_silent_ports_and_buses_are_listened_to_again(tmp_path, monkeypatch):
    """A GPS powered after the box (on a port that answered nothing at boot), or a DroneCAN GPS
    that got its node id late: the periodic rescan finds it.
    """
    doc = boot({"i2c": {"imu": {"bus": 1}}})
    jp, ep = tmp_path / "discovery.json", tmp_path / "discovered.env"
    jp.write_text(json.dumps(doc))
    monkeypatch.setattr(hotplug, "devices", lambda env: {"serial": ["/dev/ttyTHS1"], "can": ["can0"], "cameras": []})
    monkeypatch.setattr(disc, "probe_serial_port", lambda p, *a, **k: None)
    monkeypatch.setattr(disc, "can_buses", lambda env: ["can0"])
    here3 = {"kind": "dronecan", "iface": "can0", "gnss": [{"node": 42, "fix": True, "sats": 12, "type": "Fix2"}],
             "nodes": [42], "controllers": [], "alloc_requests": False, "allocator": False}
    monkeypatch.setattr(disc, "probe_dronecan", lambda b, *a, **k: here3)
    hotplug.run({}, str(jp), str(ep), lambda: None, interval_s=0, rescan_s=0, log=lambda s: None, passes=1)
    t = ep.read_text()
    assert "NAVERA_GPS_SOURCE=dronecan" in t and "NAVERA_GPS_CAN_NODE=42" in t and "NAVERA_GPS_CAN_IFACE=can0" in t
