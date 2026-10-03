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


def test_the_box_alone():
    d = decide({"i2c": {"imu": {}, "rtc": {}}, "serial": [{"kind": "nmea", "port": "/dev/ttyTHS1", "baud": 9600}],
                "cameras": {"usb": ["/dev/v4l/by-id/usb-Insta360-video-index0"], "csi": []}}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "box" and s["NAVERA_GPS_SOURCE"] == "serial"
    assert s["NAVERA_GPS_PORT"] == "/dev/ttyTHS1" and s["NAVERA_GPS_BAUD"] == "9600"
    assert s["NAVERA_CAMERA_INPUT"] == "usb" and s["NAVERA_CAMERA_DEVICE"].endswith("index0")
    assert "NAVERA_MAVLINK_URL" not in s and any("NMEA" in r for r in d["report"])


def test_a_drone_with_an_autopilot_and_no_box_sensors():
    d = decide({"serial": [AP], "cameras": {"usb": ["/dev/v4l/by-id/cam-video-index0"]},
                "autopilot_streams": {"ATTITUDE": True, "GPS2_RAW": True}}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "vehicle" and s["NAVERA_GPS_SOURCE"] == "vehicle"
    assert s["NAVERA_VEHICLE_MAVLINK_URL"] == AP["url"]
    assert s["NAVERA_MAVLINK_URL"] == "udpout:127.0.0.1:14650"     # relayed by vehicle_link


def test_box_sensors_win_but_the_autopilot_still_gets_the_position():
    d = decide({"i2c": {"imu": {}}, "serial": [AP, {"kind": "nmea", "port": "/dev/ttyUSB0", "baud": 38400}],
                "autopilot_streams": {"ATTITUDE": True, "GPS2_RAW": True}}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "box" and s["NAVERA_GPS_SOURCE"] == "serial"
    assert s["NAVERA_MAVLINK_URL"] == "udpout:127.0.0.1:14650"


def test_a_ros_boat():
    d = decide({"ros": ROS, "cameras": {}}, {})
    s = d["settings"]
    assert s["NAVERA_SENSOR_SOURCE"] == "ros" and s["NAVERA_ROS_IMU_TOPIC"] == "/boat/imu/data"
    assert s["NAVERA_GPS_SOURCE"] == "ros" and s["NAVERA_ROS_GPS_TOPIC"] == "/boat/gps/fix"
    assert s["NAVERA_CAMERA_INPUT"] == "ros" and s["NAVERA_CAMERA_TOPIC"] == "/boat/cam_down/image_raw"
    assert s["ROS_DOMAIN_ID"] == "0" and s["ROS_LOCALHOST_ONLY"] == "0" and s["NAVERA_ROS_FIX_TOPIC"] == "/navera/fix"


def test_written_settings_always_win():
    env = {"NAVERA_SENSOR_SOURCE": "box", "NAVERA_GPS_SOURCE": "serial", "NAVERA_CAMERA_INPUT": "csi",
           "NAVERA_VEHICLE_MAVLINK_URL": "udpin:0.0.0.0:14551"}
    s = decide({"ros": ROS, "serial": [AP]}, env)["settings"]
    for k in ("NAVERA_SENSOR_SOURCE", "NAVERA_GPS_SOURCE", "NAVERA_CAMERA_INPUT", "NAVERA_VEHICLE_MAVLINK_URL"):
        assert k not in s
    assert decide({"ros": ROS}, {"NAVERA_SENSOR_SOURCE": "auto"})["settings"]["NAVERA_SENSOR_SOURCE"] == "ros"


def test_nothing_found_is_said_plainly():
    d = decide({}, {})
    text = "\n".join(d["report"])
    assert "found: nothing" in text and "NO attitude" in text and "NO GPS" in text and "NO camera" in text


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
        for payload in (GGA + RMC, hb_ap, hb_gcs):
            ports.append(_fake_port(payload))
        gps = probe_serial_port(ports[0][0], bauds=(9600,), listen_s=1.0)
        ap = probe_serial_port(ports[1][0], bauds=(57600,), listen_s=1.5)
        gcs = probe_serial_port(ports[2][0], bauds=(57600,), listen_s=1.5)
        assert gps == {"port": ports[0][0], "baud": 9600, "kind": "nmea"}
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
