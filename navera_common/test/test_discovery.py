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
    # type 14 = MAVLink GPS (NAVERA's GPS_INPUT); type 5 = NMEA while NAVERA's NMEA output is on
    for g1, g2, env, word in ((14, 14, {}, "NAVERA's own output"), (14, 0, {}, "NAVERA's own output"),
                              (0, 14, {}, "NAVERA's own output"), (None, None, {}, "could not be read"),
                              (0, 0, {}, "NO GPS"),
                              (5, 0, {"NAVERA_NMEA_PORT": "/dev/ttyTHS2"}, "NAVERA's own output")):
        d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, gps1_type=g1, gps2_type=g2)}, env)
        assert d["settings"]["NAVERA_GPS_SOURCE"] == "none", (g1, g2)
        assert any(word in r for r in d["report"]), d["report"]
        assert "gps" in d["idle"]


def test_the_autopilots_first_gps_when_navera_is_its_second():
    """Wiring C: the client's GPS stays on the autopilot (GPS1), NAVERA feeds GPS2 (type 14).
    ArduPilot's GPS_RAW_INT is always instance 1: never NAVERA's output.
    """
    d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, gps1_type=2, gps2_type=14)}, {})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "vehicle_gps1"
    assert any("NAVERA is its second GPS" in r for r in d["report"])
    # NMEA GPS1 is a real receiver when NAVERA's NMEA output is off
    d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, gps1_type=5, gps2_type=14)}, {})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "vehicle_gps1"
    # the option turned off
    d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, gps1_type=2, gps2_type=14)},
               {"NAVERA_GPS_MONITOR_GPS1": "0"})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "none"
    assert any("NAVERA_GPS_MONITOR_GPS1=0" in r for r in d["report"])
    # a real second GPS keeps priority (as before)
    d = decide({"serial": [AP], "autopilot_streams": dict(STREAMS, gps1_type=1, gps2_type=1)}, {})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "vehicle"


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
    import os
    import pty
    import threading
    import time
    import tty
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


PX4_OK = {"MAV_USEHILGPS": 1, "EKF2_GPS_CTRL": 1, "EKF2_HGT_REF": 0, "EKF2_GPS_CHECK": 240, "SYS_HAS_GPS": 1}


def test_px4_gets_hil_gps_through_the_relay_and_the_imu_address_is_kept():
    """PX4 has no GPS_INPUT handler: its output is HIL_GPS (MAV_USEHILGPS), relayed by vehicle_link."""
    px4 = dict(AP, autopilot=12)
    d = decide({"serial": [px4], "i2c": {"imu": {"bus": 1, "address": "0x4b"}},
                "autopilot_streams": dict(STREAMS, px4_params=PX4_OK)}, {})
    s = d["settings"]
    assert s["NAVERA_MAVLINK_URL"] == "udpout:127.0.0.1:14650" and s["NAVERA_MAVLINK_MESSAGE"] == "hil_gps"
    assert s["NAVERA_MAVLINK_SYSID"] == "1"                  # PX4 reads HIL_GPS only from its own id
    assert any("PX4" in r and "HIL_GPS" in r for r in d["report"])
    assert not any(r.startswith("CHECK") for r in d["report"]), d["report"]
    assert s["NAVERA_BOX_IMU_ADDR"] == "0x4b"
    # off stays off; a written message is kept, gps_input to PX4 is a CHECK
    d = decide({"serial": [px4], "autopilot_streams": STREAMS}, {"NAVERA_MAVLINK_URL": "off"})
    assert "NAVERA_MAVLINK_MESSAGE" not in d["settings"]
    d = decide({"serial": [px4], "autopilot_streams": dict(STREAMS, px4_params=PX4_OK)},
               {"NAVERA_MAVLINK_MESSAGE": "gps_input"})
    assert "NAVERA_MAVLINK_MESSAGE" not in d["settings"] and any("ignores GPS_INPUT" in r for r in d["report"])
    # ArduPilot: unchanged (GPS_INPUT, no message key)
    d = decide({"serial": [AP], "autopilot_streams": STREAMS}, {})
    assert "NAVERA_MAVLINK_MESSAGE" not in d["settings"]


def test_px4_parameters_that_break_the_hil_gps_output_are_reported():
    from navera_common.discovery import px4_param_int
    px4 = dict(AP, autopilot=12)
    bad = dict(PX4_OK, MAV_USEHILGPS=0, EKF2_GPS_CTRL=7, EKF2_HGT_REF=1, EKF2_GPS_CHECK=245)
    rep = decide({"serial": [px4], "autopilot_streams": dict(STREAMS, px4_params=bad)}, {})["report"]
    for name in ("MAV_USEHILGPS", "EKF2_GPS_CTRL", "EKF2_HGT_REF", "EKF2_GPS_CHECK"):
        assert any(r.startswith(f"CHECK PX4 {name} ") for r in rep), (name, rep)
    rep = decide({"serial": [px4], "autopilot_streams": STREAMS}, {})["report"]      # not read
    assert any("PX4 parameters not all read" in r for r in rep)
    # PX4 sends INT32 parameters bytewise in PARAM_VALUE's float
    import struct
    assert px4_param_int(struct.unpack("<f", struct.pack("<i", 240))[0], 6) == 240
    assert px4_param_int(5.0, 9) == 5


# ── GPS in every common form (UBX, DroneCAN, network) ──────────────────────
def _pvt(fix=True):
    from navera_common.gnss import NAV, NAV_PVT, ubx_frame
    from test_gnss import nav_pvt
    return ubx_frame(NAV, NAV_PVT, nav_pvt() if fix else nav_pvt(fix_type=0, flags=0))


def test_a_u_blox_seen_through_a_passive_tap_is_recognised_and_never_written_to():
    """A u-blox ArduPilot set to UBX at 230400, tapped by a Y-cable on the receiver's TX.

    NAVERA must recognise NAV-PVT and send nothing back.
    """
    import os
    import select
    import threading
    from navera_common.discovery import probe_serial_port
    from navera_common.gnss import NAV, ubx_frame
    ports = [_fake_port(_pvt()), _fake_port(ubx_frame(NAV, 0x02, bytes(28)) * 3)]   # NAV-POSLLH only
    written, stop = [], threading.Event()

    def listen(master):                                          # what the probe sends to the "receiver"
        while not stop.is_set():
            if select.select([master], [], [], 0.05)[0]:
                try:
                    written.append(os.read(master, 100))
                except OSError:                                  # no one has the port open
                    pass
    for _, _, (master,) in ports:
        threading.Thread(target=listen, args=(master,), daemon=True).start()
    try:
        g = probe_serial_port(ports[0][0], bauds=(230400,), listen_s=1.0)
        assert g == {"port": ports[0][0], "baud": 230400, "kind": "ubx", "fix": True, "satellites": True,
                     "nmea": False}
        old = probe_serial_port(ports[1][0], bauds=(9600,), listen_s=0.8)
        assert old["kind"] == "ubx_no_pvt"
        assert b"".join(written) == b"", "the probe wrote to the receiver"
    finally:
        stop.set()
        for _, stop_talk, fds in ports:
            stop_talk.set()
            for fd in fds:
                os.close(fd)


UBX_RX = {"kind": "ubx", "port": "/dev/ttyUSB0", "baud": 230400, "fix": True, "satellites": True, "nmea": False}
HERE3 = {"kind": "dronecan", "iface": "can0", "gnss": [{"node": 124, "fix": True, "sats": 14, "type": "Fix2"}],
         "nodes": [10, 124], "controllers": [10], "alloc_requests": False, "allocator": True}
NET = {"kind": "gps_net", "url": "tcp:192.168.1.20:10110", "protocol": "nmea", "fix": True, "satellites": True}


def test_gps_priority_serial_then_dronecan_then_network_then_autopilot():
    st = {"serial": [AP], "autopilot_streams": STREAMS}
    d = decide(dict(st, serial=[AP, UBX_RX], can=[HERE3], gps_net=[NET]), {})
    s = d["settings"]
    assert (s["NAVERA_GPS_SOURCE"], s["NAVERA_GPS_PORT"], s["NAVERA_GPS_BAUD"]) == ("serial", "/dev/ttyUSB0", "230400")
    assert any("u-blox UBX" in r for r in d["report"]) and any("CHECK several GPS receivers" in r for r in d["report"])
    s = decide(dict(st, can=[HERE3], gps_net=[NET]), {})["settings"]
    assert (s["NAVERA_GPS_SOURCE"], s["NAVERA_GPS_CAN_IFACE"], s["NAVERA_GPS_CAN_NODE"]) == ("dronecan", "can0", "124")
    s = decide(dict(st, gps_net=[NET]), {})["settings"]
    assert (s["NAVERA_GPS_SOURCE"], s["NAVERA_GPS_URL"]) == ("network", NET["url"])
    assert decide(st, {})["settings"]["NAVERA_GPS_SOURCE"] == "vehicle"
    # a receiver with a fix beats one without, whatever the form
    s = decide({"serial": [dict(UBX_RX, fix=False)], "can": [HERE3]}, {})["settings"]
    assert s["NAVERA_GPS_SOURCE"] == "serial"       # serial first: a fix only orders receivers of one form
    s = decide({"serial": [dict(RECEIVER, fix=False), UBX_RX]}, {})["settings"]
    assert s["NAVERA_GPS_PORT"] == "/dev/ttyUSB0"


def test_dronecan_an_autopilot_rebroadcasting_its_gps_and_a_gps_without_a_node_id():
    ap_node = dict(HERE3, gnss=[{"node": 10, "fix": True, "sats": 20, "type": "Fix2"}])
    d = decide({"can": [ap_node]}, {})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "none"
    assert any("commands motors" in r for r in d["report"])
    alone = dict(HERE3, gnss=[], nodes=[], controllers=[], alloc_requests=True, allocator=False)
    d = decide({"can": [alone], "can_ifaces": [{"iface": "can0", "up": True}, {"iface": "can1", "up": False}]}, {})
    assert any("NAVERA_GPS_CAN_ALLOCATE=1" in r for r in d["report"])
    assert any("can1 is down" in r and "bitrate 1000000" in r for r in d["report"])
    d = decide({"can": [dict(HERE3, gnss=[], error="pydronecan is not installed")]}, {})
    assert any(r.startswith("CHECK DroneCAN on can0") for r in d["report"])


def test_network_gps_addresses_and_mavlink_defaults():
    from navera_common.discovery import gps_urls, mavlink_urls
    assert gps_urls({}) == []                                    # never an address it was not given
    assert gps_urls({"NAVERA_DISCOVER_GPS_URLS": "tcp:10.0.0.5, udp, tcp:10.0.0.6:5017"}) == [
        "tcp:10.0.0.5:10110", "tcp:10.0.0.5:2000", "tcp:10.0.0.5:4001", "udp:10110", "tcp:10.0.0.6:5017"]
    assert mavlink_urls({"NAVERA_DISCOVER_MAVLINK": "tcp:127.0.0.1:5760,tcp:10.0.0.2:5760"}) == [
        "udpin:0.0.0.0:14550", "udpin:0.0.0.0:14551", "tcp:127.0.0.1:5760", "tcp:10.0.0.2:5760"]
    d = decide({"gps_net": [dict(NET, satellites=False)]}, {})
    assert d["settings"]["NAVERA_GPS_SOURCE"] == "none" and any("without satellite" in r for r in d["report"])


def test_network_gps_probe_tcp_and_udp():
    import socket
    import threading
    import time
    from navera_common.discovery import probe_gps_url
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        for _ in range(10):
            try:
                c.sendall(_pvt())
            except OSError:
                break
            time.sleep(0.1)
        c.close()
    threading.Thread(target=serve, daemon=True).start()
    r = probe_gps_url(f"tcp:127.0.0.1:{port}", listen_s=2.0)
    srv.close()
    assert r == {"kind": "gps_net", "url": f"tcp:127.0.0.1:{port}", "protocol": "ubx", "fix": True, "satellites": True}
    assert probe_gps_url(f"tcp:127.0.0.1:{port}", listen_s=0.5) is None           # nothing listens any more

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    uport = probe.getsockname()[1]
    probe.close()
    stop = threading.Event()

    def send():
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while not stop.is_set():
            tx.sendto(GGA + RMC + GSV, ("127.0.0.1", uport))
            time.sleep(0.1)
        tx.close()
    threading.Thread(target=send, daemon=True).start()
    try:
        r = probe_gps_url(f"udp:127.0.0.1:{uport}", listen_s=2.0)
    finally:
        stop.set()
    assert r["protocol"] == "nmea" and r["fix"] and r["satellites"]


def test_dronecan_probe_on_a_virtual_bus():
    """A Here3-like node (Fix2) and an autopilot node (ESC commands + its own Fix2) on a
    pydronecan multicast bus: the passive probe hears both, sends nothing.
    """
    import threading
    import pytest
    dronecan = pytest.importorskip("dronecan")
    from navera_common.discovery import probe_dronecan
    bus = "mcast:7"
    here3 = dronecan.make_node(bus, node_id=124)
    fc = dronecan.make_node(bus, node_id=10)
    stop, sent_by_probe = threading.Event(), []
    spy = dronecan.make_node(bus)
    spy.add_transfer_hook(lambda t: sent_by_probe.append(t.source_node_id)
                          if t.source_node_id not in (124, 10) else None)

    def run():
        fix = dronecan.uavcan.equipment.gnss.Fix2(latitude_deg_1e8=3573400100, longitude_deg_1e8=1057584850,
                                                  status=3, sats_used=14)
        while not stop.is_set():
            here3.broadcast(fix)
            fc.broadcast(fix)
            fc.broadcast(dronecan.uavcan.equipment.esc.RawCommand(cmd=[0, 0, 0, 0]))
            for n in (here3, fc, spy):
                n.spin(0.05)
    th = threading.Thread(target=run, daemon=True)
    th.start()
    try:
        r = probe_dronecan(bus, listen_s=1.5)
    finally:
        stop.set()
        th.join(2)
        for n in (here3, fc, spy):
            n.close()
    assert "error" not in r, r
    assert [g["node"] for g in r["gnss"]] == [10, 124] and all(g["fix"] for g in r["gnss"])
    assert r["controllers"] == [10] and set(r["nodes"]) >= {10, 124}
    assert sent_by_probe == []                                   # the probe never transmitted
    d = decide({"can": [r]}, {})
    assert d["settings"]["NAVERA_GPS_CAN_NODE"] == "124"         # the autopilot's re-broadcast is not a GPS
