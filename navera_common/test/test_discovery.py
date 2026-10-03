"""What NAVERA decides from what it finds connected (no hardware needed)."""
import os

from navera_common.discovery import decide, mavlink_heartbeats, nmea_valid, write_env

GGA = b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n"
RMC = b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n"
AP = {"kind": "mavlink", "url": "serial:/dev/ttyTHS2:921600", "sysid": 1, "compid": 1, "type": 2, "autopilot": 3}
ROS = {0: {"sensor_msgs/msg/Imu": ["/boat/imu/data"], "sensor_msgs/msg/NavSatFix": ["/boat/gps/fix"],
           "sensor_msgs/msg/Image": ["/boat/depth/image_raw", "/boat/cam_down/image_raw", "/boat/cam_front/image_raw"]}}


def test_nmea_and_mavlink_recognised_in_raw_bytes():
    assert nmea_valid(b"\x00garbage" + GGA + RMC) == 2
    assert nmea_valid(GGA.replace(b"*47", b"*48")) == 0          # wrong checksum
    from pymavlink.dialects.v20 import common as mav
    m = mav.MAVLink(None, srcSystem=1, srcComponent=1)
    data = m.heartbeat_encode(2, 3, 0, 0, 0).pack(m) + b"\xff\x00junk"
    assert mavlink_heartbeats(data) == [{"sysid": 1, "compid": 1, "type": 2, "autopilot": 3}]


GSV = b"$GPGSV,1,1,04,05,63,180,45,12,50,060,40,17,30,240,38,19,20,300,35*76\r\n"
RECEIVER = {"kind": "nmea", "port": "/dev/ttyTHS1", "baud": 9600, "satellites": True, "fix": True}
STREAMS = {"ATTITUDE": True, "GPS2_RAW": True, "gps1_type": 1, "gps2_type": 1}


def test_nmea_info_tells_a_receiver_from_an_autopilot_output():
    from navera_common.discovery import nmea_info
    assert nmea_info(GGA + RMC) == {"valid": 2, "satellites": False, "fix": True}
    no_fix = b"$GPGGA,,,,,,0,00,99.99,,,,,,*48\r\n"
    assert nmea_info(no_fix)["fix"] is False


def test_the_box_alone():
    d = decide({"i2c": {"imu": {"bus": 1}, "rtc": {"bus": 1}}, "serial": [RECEIVER],
                "cameras": {"usb": ["/dev/v4l/by-id/usb-Insta360-video-index0"], "csi": []}}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "box" and s["NAVERA_GPS_SOURCE"] == "serial"
    assert s["NAVERA_GPS_PORT"] == "/dev/ttyTHS1" and s["NAVERA_GPS_BAUD"] == "9600"
    assert s["NAVERA_CAMERA_INPUT"] == "usb" and s["NAVERA_CAMERA_DEVICE"].endswith("index0")
    assert "NAVERA_MAVLINK_URL" not in s and any("NMEA" in r for r in d["report"])
    assert s["NAVERA_BOX_IMU"] == "1" and s["NAVERA_BOX_RTC"] == "1"
    assert decide({}, {})["settings"]["NAVERA_BOX_IMU"] == "0"      # services idle, no restart loop


def test_a_drone_with_an_autopilot_and_no_box_sensors():
    d = decide({"serial": [AP], "cameras": {"usb": ["/dev/v4l/by-id/cam-video-index0"]},
                "autopilot_streams": STREAMS}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "vehicle" and s["NAVERA_GPS_SOURCE"] == "vehicle"
    assert s["NAVERA_VEHICLE_MAVLINK_URL"] == AP["url"] and s["NAVERA_MAVLINK_SYSID"] == "1"
    assert s["NAVERA_MAVLINK_URL"] == "udpout:127.0.0.1:14650"     # relayed by vehicle_link


def test_navera_never_reads_its_own_output_back_as_a_gps():
    for g2, word in ((14, "NAVERA's own output"), (None, "could not be read"), (0, "NO GPS")):
        d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, gps2_type=g2)}, {})
        assert d["settings"]["NAVERA_GPS_SOURCE"] == "none"
        assert any(word in r for r in d["report"]), d["report"]


def test_a_second_gps_without_a_fix_yet_is_still_the_vehicles_gps():
    d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, GPS2_RAW=False)}, {})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "vehicle"


def test_nmea_without_satellites_is_not_a_receiver_and_a_fix_wins():
    ap_nmea = {"kind": "nmea", "port": "/dev/ttyTHS2", "baud": 115200, "satellites": False, "fix": True}
    modem = {"kind": "nmea", "port": "/dev/ttyUSB2", "baud": 115200, "satellites": True, "fix": False}
    d = decide({"serial": [ap_nmea, modem, dict(RECEIVER, port="/dev/ttyUSB0")]}, {})
    s = d["settings"]
    assert s["NAVERA_GPS_PORT"] == "/dev/ttyUSB0"                 # the receiver with a fix
    text = "\n".join(d["report"])
    assert "not used as a GPS" in text and "CHECK several GPS receivers" in text


def test_box_sensors_win_but_the_autopilot_still_gets_the_position():
    d = decide({"i2c": {"imu": {"bus": 7}}, "serial": [AP, RECEIVER], "autopilot_streams": STREAMS}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "box" and s["NAVERA_GPS_SOURCE"] == "serial"
    assert s["NAVERA_MAVLINK_URL"] == "udpout:127.0.0.1:14650"


def test_a_ros_boat_on_the_default_domain():
    d = decide({"ros": ROS, "cameras": {}}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "ros" and s["NAVERA_ROS_IMU_TOPIC"] == "/boat/imu/data"
    assert s["NAVERA_GPS_SOURCE"] == "ros" and s["NAVERA_ROS_GPS_TOPIC"] == "/boat/gps/fix"
    assert s["NAVERA_CAMERA_INPUT"] == "ros" and s["NAVERA_CAMERA_TOPIC"] == "/boat/cam_down/image_raw"
    assert "ROS_DOMAIN_ID" not in s and s["NAVERA_ROS_FIX_TOPIC"] == "/navera/fix"


def test_written_ros_network_settings_are_never_replaced():
    env = {"ROS_DOMAIN_ID": "42", "ROS_LOCALHOST_ONLY": "1"}
    d = decide({"ros": ROS}, env)
    s = d["settings"]
    assert "ROS_DOMAIN_ID" not in s and "ROS_LOCALHOST_ONLY" not in s
    assert s.get("NAVERA_SENSOR_SOURCE") != "ros" and "NAVERA_ROS_FIX_TOPIC" not in s
    assert any("ROS_DOMAIN_ID=auto" in r for r in d["report"])
    s = decide({"ros": ROS}, {"ROS_DOMAIN_ID": "auto"})["settings"]          # opted in: joins it
    assert s["ROS_DOMAIN_ID"] == "0" and s["ROS_LOCALHOST_ONLY"] == "0" and s["NAVERA_SENSOR_SOURCE"] == "ros"


def test_written_settings_always_win():
    env = {"NAVERA_SENSOR_SOURCE": "box", "NAVERA_GPS_SOURCE": "serial", "NAVERA_CAMERA_INPUT": "csi",
           "NAVERA_VEHICLE_MAVLINK_URL": "udpin:0.0.0.0:14551", "NAVERA_MAVLINK_URL": "off"}
    s = decide({"ros": ROS, "serial": [AP], "autopilot_streams": STREAMS}, env)["settings"]
    for k in ("NAVERA_SENSOR_SOURCE", "NAVERA_GPS_SOURCE", "NAVERA_CAMERA_INPUT", "NAVERA_VEHICLE_MAVLINK_URL",
              "NAVERA_MAVLINK_URL"):
        assert k not in s


def test_cameras_the_star_camera_and_a_written_device_are_respected():
    usb = ["/dev/v4l/by-id/usb-Arducam_StarCam-video-index0", "/dev/v4l/by-id/usb-Insta360_ONE_R-video-index0"]
    env = {"NAVERA_STAR_CAMERA_DEVICE": usb[0]}
    s = decide({"cameras": {"usb": usb}}, env)["settings"]
    assert s["NAVERA_CAMERA_DEVICE"] == usb[1]
    d = decide({"cameras": {"usb": usb}}, {})
    assert any("CHECK several cameras" in r for r in d["report"])
    s = decide({"cameras": {"usb": usb}}, {"NAVERA_CAMERA_DEVICE": "/dev/v4l/by-id/mine"})["settings"]
    assert s["NAVERA_CAMERA_INPUT"] == "usb" and "NAVERA_CAMERA_DEVICE" not in s


def test_two_autopilots_the_wired_port_and_a_warning():
    usb_ap = dict(AP, url="serial:/dev/ttyACM0:115200")
    other = dict(AP, url="udpin:0.0.0.0:14550", sysid=2)
    d = decide({"serial": [usb_ap, AP], "network": [other], "autopilot_streams": STREAMS}, {})
    assert d["settings"]["NAVERA_VEHICLE_MAVLINK_URL"] == AP["url"]
    assert any("several autopilots" in r for r in d["report"])


def test_nothing_found_is_said_plainly():
    d = decide({}, {})
    text = "\n".join(d["report"])
    assert "found: nothing" in text and "NO attitude" in text and "NO GPS" in text and "NO camera" in text
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "none"            # never a default port


def test_env_file_never_carries_an_injection(tmp_path):
    p = str(tmp_path / "d.env")
    write_env({"NAVERA_CAMERA_TOPIC": "/a\nNAVERA_WEB_TOKEN=x", "ok_lower": "1", "NAVERA_GPS_BAUD": "9600"}, p)
    text = open(p).read()
    assert "NAVERA_GPS_BAUD=9600" in text and "TOKEN" not in text and "ok_lower" not in text
    os.remove(p)


def _fake_port(payload: bytes):
    """A virtual serial port that keeps sending payload (a GPS receiver / an autopilot)."""
    import os, pty, threading, time, tty
    master, slave = pty.openpty()
    tty.setraw(slave)
    name = os.ttyname(slave)
    os.close(slave)              # held open by no one: the probe skips ports in use
    stop = threading.Event()

    def talk():
        while not stop.is_set():
            try:
                os.write(master, payload)
            except OSError:      # nobody reading yet
                pass
            time.sleep(0.2)
    threading.Thread(target=talk, daemon=True).start()
    return name, stop, (master,)


def test_a_gps_receiver_and_an_autopilot_are_recognised_on_serial_ports():
    import os
    from pymavlink.dialects.v20 import common as mav
    from navera_common.discovery import probe_serial_port
    m = mav.MAVLink(None, srcSystem=1, srcComponent=1)
    hb_ap = m.heartbeat_encode(2, 3, 0, 0, 0).pack(m)            # quadrotor, ArduPilot
    g = mav.MAVLink(None, srcSystem=255, srcComponent=190)
    hb_gcs = g.heartbeat_encode(6, 8, 0, 0, 0).pack(g)           # a ground station only
    ports = []
    try:
        for payload in (GGA + RMC + GSV, hb_ap, hb_gcs):
            ports.append(_fake_port(payload))
        gps = probe_serial_port(ports[0][0], bauds=(9600,), listen_s=1.0)
        ap = probe_serial_port(ports[1][0], bauds=(57600,), listen_s=1.5)
        gcs = probe_serial_port(ports[2][0], bauds=(57600,), listen_s=1.5)
        assert gps == {"port": ports[0][0], "baud": 9600, "kind": "nmea", "satellites": True, "fix": True}
        assert ap["kind"] == "mavlink" and ap["url"] == f"serial:{ports[1][0]}:57600" and ap["sysid"] == 1
        assert gcs is None                                       # not an autopilot
        # another program has it (O_NOCTTY: never become this process's terminal — closing
        # it would then hang up the whole test run)
        held = os.open(ports[0][0], os.O_RDWR | os.O_NOCTTY)
        try:
            assert probe_serial_port(ports[0][0], bauds=(9600,), listen_s=0.5)["kind"] == "busy"
        finally:
            os.close(held)
    finally:
        for _, stop, fds in ports:
            stop.set()
            for fd in fds:
                os.close(fd)


def test_discovery_runs_with_ros_domain_auto(monkeypatch):
    import navera_common.discovery as dsc
    seen = {}
    monkeypatch.setattr(dsc, "probe_i2c", lambda: {})
    monkeypatch.setattr(dsc, "probe_cameras", lambda: {})
    monkeypatch.setattr(dsc, "serial_ports", lambda: [])
    monkeypatch.setattr(dsc, "probe_mavlink_url", lambda url, *a: None)
    monkeypatch.setattr(dsc, "probe_ros", lambda domains, wait: seen.setdefault("d", domains) and {})
    dsc.discover({"ROS_DOMAIN_ID": "auto"}, ros_wait_s=0.1)       # crashed: int("auto")
    assert seen["d"] == [0]
    dsc.discover({"ROS_DOMAIN_ID": "42", "NAVERA_DISCOVER_ROS_DOMAINS": "7"}, ros_wait_s=0.1)


def test_px4_gets_no_mavlink_output_and_the_imu_address_is_kept():
    px4 = dict(AP, autopilot=12)
    d = decide({"serial": [px4], "i2c": {"imu": {"bus": 1, "address": "0x4b"}},
                "autopilot_streams": STREAMS}, {})
    assert "NAVERA_MAVLINK_URL" not in d["settings"] and any("PX4" in r for r in d["report"])
    assert d["settings"]["NAVERA_BOX_IMU_ADDR"] == "0x4b"
