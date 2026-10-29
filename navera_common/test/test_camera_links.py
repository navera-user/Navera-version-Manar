"""The other ways a drone camera talks: RTSP without ONVIF, the MAVLink camera protocol, a GoPro on
USB, GigE Vision / USB3 Vision through Aravis (navera_common.cameras, camera_pkg.aravis_capture)."""
import http.server
import os
import re
import socket
import struct
import sys
import threading

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "camera_pkg"))

from navera_common import cameras  # noqa: E402


def rtsp_paths_server(host, paths, login=False):
    """An RTSP server answering DESCRIBE: 200 for the given paths, 404 for others (401 if login)."""
    s = socket.socket()
    s.bind((host, 0))
    s.listen(16)

    def serve():
        while True:
            try:
                c, _ = s.accept()
            except OSError:
                return
            req = re.match(r"DESCRIBE (\S+)", c.recv(65536).decode())
            if not req:                                 # a port check: connect and close
                c.close()
                continue
            uri = req.group(1)
            path = re.sub(r"rtsp://[^/]+", "", uri)
            if login:
                c.sendall(b'RTSP/1.0 401 Unauthorized\r\nCSeq: 2\r\nWWW-Authenticate: Digest realm="x", nonce="n"\r\n\r\n')
            elif path in paths:
                sdp = "v=0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n"
                c.sendall(f"RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}".encode())
            else:
                c.sendall(b"RTSP/1.0 404 Not Found\r\nCSeq: 2\r\n\r\n")
            c.close()
    threading.Thread(target=serve, daemon=True).start()
    return s, s.getsockname()[1]


def test_an_rtsp_camera_without_onvif_is_found_by_its_stream_path():
    srv, port = rtsp_paths_server("127.0.0.2", {"/video1"})
    try:
        cams, notes = cameras.rtsp_scan([{"ipv4": [("127.0.0.1", 30)]}], ports=(port,))
    finally:
        srv.close()
    assert notes == [] and len(cams) == 1
    c = cams[0]
    assert c["id"] == f"rtsp://127.0.0.2:{port}/video1" and c["scanned"] and c["codec"] == "H264"
    assert "rtspsrc location=rtsp://127.0.0.2" in c["pipeline"] and "nvv4l2decoder" in c["pipeline"]


def test_an_rtsp_camera_asking_for_a_login_is_reported_not_used():
    srv, port = rtsp_paths_server("127.0.0.2", set(), login=True)
    try:
        cams, notes = cameras.rtsp_scan([{"ipv4": [("127.0.0.1", 30)]}], ports=(port,))
    finally:
        srv.close()
    assert cams == [] and len(notes) == 1 and "NAVERA_IP_CAMERA_USER" in notes[0]


def test_hosts_already_known_and_the_box_itself_are_not_scanned():
    srv, port = rtsp_paths_server("127.0.0.2", {""})
    try:
        cams, _ = cameras.rtsp_scan([{"ipv4": [("127.0.0.1", 30)]}], skip_hosts={"127.0.0.2"}, ports=(port,))
    finally:
        srv.close()
    assert cams == []


def test_mavlink_streams_of_each_type_give_a_pipeline():
    udp = cameras.mavlink_stream_camera(dict(type=1, uri="udp://0.0.0.0:5600", encoding=2, name="EO",
                                             resolution_h=1280, resolution_v=720, hfov=62, flags=1))
    assert "udpsrc port=5600" in udp["pipeline"] and "rtph265depay" in udp["pipeline"]
    assert udp["size"] == [1280, 720] and udp["hfov_deg"] == 62 and udp["lens_source"] == "camera"
    assert udp["spectrum"] is None                     # nothing says thermal: the picture decides
    ts = cameras.mavlink_stream_camera(dict(type=3, uri="5601", name="IR", flags=3))
    assert "tsdemux" in ts["pipeline"] and ts["spectrum"] == "thermal"
    tcp = cameras.mavlink_stream_camera(dict(type=2, uri="tcp://192.168.1.20:5000"))
    assert "tcpclientsrc host=192.168.1.20 port=5000" in tcp["pipeline"]
    assert cameras.mavlink_stream_camera(dict(type=0, uri="")) is None
    assert cameras.mavlink_stream_camera(dict(type=9, uri="udp://:5600")) is None
    # the pipeline goes into discovered.env: no quote, no $ (write_env refuses them)
    assert not re.search(r"[\"'$`]", udp["pipeline"] + ts["pipeline"] + tcp["pipeline"])


def test_mavlink_rtsp_stream_takes_its_codec_from_the_camera():
    srv, port = rtsp_paths_server("127.0.0.1", {"/live"})
    try:
        c = cameras.mavlink_stream_camera(dict(type=0, uri=f"rtsp://127.0.0.1:{port}/live", encoding=2))
    finally:
        srv.close()
    assert "rtph264depay" in c["pipeline"] and c["auth"] is False


def test_a_mavlink_camera_announcing_its_stream_is_found():
    from pymavlink import mavutil
    from pymavlink.dialects.v20 import ardupilotmega as v2
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cam = mavutil.mavlink_connection(f"udpout:127.0.0.1:{port}", source_system=1, source_component=100)
    cam.mav = v2.MAVLink(cam, srcSystem=1, srcComponent=100)
    stop = threading.Event()

    def camera():
        while not stop.is_set():
            cam.mav.heartbeat_send(cameras.MAV_TYPE_CAMERA, 8, 0, 0, 4)
            m = cam.recv_match(type="COMMAND_LONG", blocking=True, timeout=0.2)
            if m and m.command == cameras.MAV_CMD_REQUEST_MESSAGE and int(m.param1) == cameras.VIDEO_STREAM_INFORMATION:
                cam.mav.video_stream_information_send(1, 1, 1, 1, 30.0, 1920, 1080, 4000, 0, 81,
                                                      b"Gimbal EO", b"udp://0.0.0.0:5600")
    t = threading.Thread(target=camera, daemon=True)
    t.start()
    try:
        found = cameras.mavlink_cameras(f"udpin:127.0.0.1:{port}", env={}, wait_s=2.0)
    finally:
        stop.set()
        t.join(2)
        cam.close()
    assert len(found) == 1
    c = found[0]
    assert c["name"] == "MAVLink camera Gimbal EO" and c["size"] == [1920, 1080] and c["hfov_deg"] == 81
    assert "udpsrc port=5600" in c["pipeline"] and c["mavlink"]


def test_a_gopro_on_usb_is_found_and_told_to_stream(monkeypatch):
    asked = []
    monkeypatch.setattr(cameras, "http_get", lambda u, timeout=2.0: asked.append(u) or 200)
    cams = cameras.gopro_cameras([("172.25.148.53", 24), ("192.168.1.5", 24)])
    assert asked == ["http://172.25.148.51:8080/gopro/webcam/status"] and len(cams) == 1
    c = cams[0]
    assert c["start_url"].split() == ["http://172.25.148.51:8080/gopro/camera/control/wired_usb?p=1",
                                      "http://172.25.148.51:8080/gopro/webcam/start?res=12&fov=4"]
    assert "udpsrc port=8554 ! tsdemux" in c["pipeline"]
    s = cameras.role_settings("day", c, {})
    assert s["NAVERA_CAMERA_START_URL"] == c["start_url"] and s["NAVERA_CAMERA_INPUT"] == "gst"


def test_camera_start_urls_are_fetched_in_order():
    from camera_pkg.gst_capture import start_camera
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            got.append(self.path)
            self.send_response(200 if "start" in self.path else 404)
            self.end_headers()
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        r = start_camera(f"{base}/a?p=1 {base}/webcam/start?res=12&fov=4")
    finally:
        srv.shutdown()
    assert got == ["/a?p=1", "/webcam/start?res=12&fov=4"] and [x[1] for x in r] == [404, 200]
    assert start_camera("") == [] and start_camera("http://127.0.0.1:1/x", timeout_s=0.5)[0][1] is None


class FakeAravis:
    """Aravis' module functions and Camera / Stream / Buffer, as far as NAVERA uses them."""
    class AcquisitionMode:
        CONTINUOUS = 1

    class BufferStatus:
        SUCCESS = 0

    class Buffer:
        def __init__(self, data=b"", w=0, h=0, fmt=0, status=0):
            self.data, self.w, self.h, self.fmt, self.status = data, w, h, fmt, status

        @classmethod
        def new_allocate(cls, size):
            return cls()

        def get_status(self):
            return self.status

        def get_data(self):
            return self.data

        def get_image_width(self):
            return self.w

        def get_image_height(self):
            return self.h

        def get_image_pixel_format(self):
            return self.fmt

    def __init__(self, devices, frames=(), fmt="BayerRG12Packed", offered=("BayerRG12Packed", "BayerRG8")):
        self.devices, self.frames, self.fmt, self.offered = devices, list(frames), fmt, offered
        self.pushed, self.set = [], {}
        ar = self

        class Stream:
            def push_buffer(self, b):
                ar.pushed.append(b)

            def timeout_pop_buffer(self, us):
                return ar.frames.pop(0) if ar.frames else None

        class Camera:
            @staticmethod
            def new(dev):
                if dev not in (None, *[d[0] for d in ar.devices]):
                    raise RuntimeError(f"no camera {dev}")
                return Camera()

            def get_pixel_format_as_string(self):
                return ar.fmt

            def dup_available_pixel_formats_as_strings(self):
                return list(ar.offered)

            def set_pixel_format_from_string(self, f):
                ar.fmt = f

            def set_string(self, k, v):
                if k == "GainAuto":
                    raise RuntimeError("no such feature")
                ar.set[k] = v

            def set_region(self, *a):
                ar.set["region"] = a

            def is_gv_device(self):
                return True

            def gv_auto_packet_size(self):
                ar.set["packet"] = True

            def set_acquisition_mode(self, m):
                pass

            def create_stream(self, a, b):
                return Stream()

            def get_payload(self):
                return 16

            def start_acquisition(self):
                ar.set["started"] = True

            def stop_acquisition(self):
                ar.set["stopped"] = True
        self.Camera = Camera

    def update_device_list(self):
        pass

    def get_n_devices(self):
        return len(self.devices)

    def get_device_id(self, i):
        return self.devices[i][0]

    def get_device_vendor(self, i):
        return self.devices[i][1]

    def get_device_model(self, i):
        return self.devices[i][2]

    def get_device_protocol(self, i):
        return self.devices[i][3]


def test_genicam_cameras_are_listed_through_aravis_and_the_fake_one_left_out():
    ar = FakeAravis([("Basler-123", "Basler", "acA1920-40gc", "GigEVision"),
                     ("FLIR-A70-9", "FLIR", "A70 thermal", "GigEVision"), ("Fake_1", "Aravis", "Fake", "Fake")])
    cams, notes = cameras.genicam_cameras([], aravis=ar)
    assert notes == [] and [c["id"] for c in cams] == ["Basler-123", "FLIR-A70-9"]
    assert cams[1]["spectrum"] == "thermal" and cams[0]["spectrum"] is None
    s = cameras.role_settings("thermal", cams[1], {})
    assert s["NAVERA_THERMAL_CAMERA_INPUT"] == "aravis" and s["NAVERA_THERMAL_CAMERA_DEVICE"] == "FLIR-A70-9"
    assert s["NAVERA_THERMAL_CAMERA_SIZE"] == "auto"


def test_without_aravis_an_industrial_camera_is_reported_with_the_install_command(tmp_path, monkeypatch):
    iface = tmp_path / "2-1:1.0"
    iface.mkdir()
    (iface / "bInterfaceClass").write_text("ef\n")
    (iface / "bInterfaceSubClass").write_text("05\n")
    (tmp_path / "2-1").mkdir()
    (tmp_path / "2-1" / "manufacturer").write_text("Basler\n")
    (tmp_path / "2-1" / "product").write_text("daA1280-54uc\n")
    assert cameras.usb3vision_devices(str(tmp_path)) == ["Basler daA1280-54uc"]
    monkeypatch.setattr(cameras, "usb3vision_devices", lambda: ["Basler daA1280-54uc"])
    monkeypatch.setattr(cameras, "load_aravis", lambda: None)
    cams, notes = cameras.genicam_cameras([])
    assert cams == [] and "USB3 Vision" in notes[0] and cameras.ARAVIS_INSTALL in notes[0]


def test_a_gvcp_discovery_answer_gives_the_camera_address_and_name():
    regs = bytearray(248)
    regs[36:40] = socket.inet_aton("192.168.10.40")
    regs[72:72 + 6] = b"Basler"
    regs[104:104 + 12] = b"acA1920-40gm"
    ack = struct.pack(">HHHH", 0, 0x0003, 248, 1) + bytes(regs)
    assert cameras.gvcp_ack(ack, "192.168.10.40") == dict(ip="192.168.10.40", maker="Basler", model="acA1920-40gm")
    assert cameras.gvcp_ack(ack[:40], "x") is None


def test_aravis_frames_are_converted_bayer_mono16_rgb():
    import cv2
    from camera_pkg import aravis_capture as ac
    bgr = np.zeros((4, 6, 3), np.uint8)
    bgr[..., 2] = 200                                   # red
    rggb = np.zeros((4, 6), np.uint8)
    rggb[0::2, 0::2] = 200                              # R at (0, 0): GenICam BayerRG
    out = ac.to_image(rggb.tobytes(), 6, 4, 0x01080009)
    assert out.shape == (4, 6, 3) and out[1:3, 1:5, 2].mean() > 150 and out[1:3, 1:5, 0].mean() < 30
    m16 = (np.arange(24, dtype="<u2") * 1000).reshape(4, 6)
    assert np.array_equal(ac.to_image(m16.tobytes(), 6, 4, ac.MONO16), m16)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    assert np.array_equal(ac.to_image(rgb.tobytes(), 6, 4, ac.RGB8), bgr)
    assert ac.to_image(b"\0" * 24, 6, 4, 0x010C0006) is None        # a packed format: not read


def test_aravis_capture_switches_a_packed_format_and_reads_frames():
    from camera_pkg import aravis_capture as ac
    mono = np.full((4, 6), 77, np.uint8)
    ar = FakeAravis([("Cam-1", "X", "Y", "USB3Vision")],
                    frames=[FakeAravis.Buffer(status=1), FakeAravis.Buffer(mono.tobytes(), 6, 4, ac.MONO8)])
    cap = ac.AravisCapture("Cam-1", aravis=ar)
    assert cap.isOpened() and ar.fmt == "BayerRG8" and ar.set["ExposureAuto"] == "Continuous"
    assert ar.set["started"] and ar.set["packet"]
    assert cap.grab() is False                          # a frame with lost packets is given back
    ok, img = cap.read()
    assert ok and np.array_equal(img, mono)
    assert cap.read() == (False, None)                  # no more frames: a timeout
    cap.release()
    assert ar.set["stopped"] and not cap.isOpened()
    bad = ac.AravisCapture("nope", aravis=ar)
    assert not bad.isOpened() and "no camera" in bad.error


def test_the_camera_node_accepts_an_industrial_camera_and_a_start_url():
    from navera_common.vehicle import live_camera_params
    p = live_camera_params({"NAVERA_CAMERA_INPUT": "aravis", "NAVERA_CAMERA_DEVICE": "Basler-123",
                            "NAVERA_CAMERA_SIZE": "auto", "NAVERA_CAMERA_HFOV_DEG": "60"})
    assert p["input"] == "aravis" and p["device"] == "Basler-123" and p["width"] == 0
    p = live_camera_params({"NAVERA_CAMERA_INPUT": "aravis", "NAVERA_CAMERA_SIZE": "auto", "NAVERA_CAMERA_HFOV_DEG": "60"})
    assert p["device"] == ""                            # the first camera Aravis lists
    p = live_camera_params({"NAVERA_CAMERA_INPUT": "gst", "NAVERA_CAMERA_SIZE": "auto", "NAVERA_CAMERA_HFOV_DEG": "60",
                            "NAVERA_CAMERA_GST_PIPELINE": cameras.udp_pipeline(8554, ts=True),
                            "NAVERA_CAMERA_START_URL": "http://x/start"})
    assert p["start_url"] == "http://x/start"


def test_the_discovery_keeps_one_entry_per_camera_the_named_one_first(monkeypatch):
    from navera_common import discovery
    monkeypatch.setattr(cameras, "describe", lambda cams, sample=True: cams)
    found = {"cameras": {"list": []}, "ip_cameras": [
        dict(kind="ip", id="udp://0.0.0.0:5600", name="MAVLink camera EO", mavlink=True),
        dict(kind="ip", id="rtsp://192.168.144.25:8554/main.264", name="SIYI gimbal camera"),
        dict(kind="ip", id="rtsp://192.168.144.25:8554/video1", name="RTSP camera 192.168.144.25", scanned=True),
        dict(kind="ip", id="rtsp://192.168.2.119:554/Streaming/Channels/101", name="RTSP camera 192.168.2.119",
             scanned=True),
        dict(kind="ip", id="rtsp://192.168.2.119:554/Streaming/Channels/201", name="RTSP camera 192.168.2.119 channel 2",
             scanned=True),
        dict(kind="aravis", id="Basler-123", name="Basler")]}
    discovery.describe_cameras(found)
    assert [c["name"] for c in found["cameras"]["list"]] == [
        "MAVLink camera EO", "SIYI gimbal camera", "RTSP camera 192.168.2.119", "RTSP camera 192.168.2.119 channel 2",
        "Basler"]


def test_the_real_aravis_reads_its_simulated_camera():
    """Aravis' own simulated GenICam camera (Mono8 at start), when Aravis is installed."""
    import pytest
    from camera_pkg import aravis_capture as ac
    try:
        ar = ac.load_aravis()
    except (ImportError, ValueError):
        pytest.skip("Aravis not installed (sudo apt install gir1.2-aravis-0.8)")
    ar.enable_interface("Fake")
    cap = ac.AravisCapture("Fake_1", timeout_s=3.0, aravis=ar)
    try:
        assert cap.isOpened(), cap.error
        ok, img = cap.read()
        assert ok and img.ndim == 2 and img.shape[0] > 0 and img.max() > img.min()
    finally:
        cap.release()


def nonce_per_connection_server(user, password, channels):
    """An RTSP server like a Hikvision: a new nonce on each connection, the login accepted only on
    the connection that got it; any path answers with the default channel's stream."""
    import hashlib
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(16)

    def serve_one(c):
        nonce = os.urandom(8).hex()
        while True:
            try:
                req = c.recv(65536).decode()
            except OSError:
                break
            m = re.match(r"DESCRIBE (\S+)", req)
            if not m:
                break
            uri = m.group(1)
            r = re.search(r'response="([0-9a-f]+)"', req)
            ha1 = hashlib.md5(f"{user}:cam:{password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
            if r and r.group(1) == hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest():
                path = re.sub(r"rtsp://[^/]+", "", uri)
                w, h, sps = channels.get(path, channels["default"])
                sdp = (f"v=0\r\nm=video 0 RTP/AVP 96\r\na=x-dimensions:{w},{h}\r\na=rtpmap:96 H264/90000\r\n"
                       f"a=fmtp:96 packetization-mode=1; sprop-parameter-sets={sps},aO48sA==\r\n")
                c.sendall(f"RTSP/1.0 200 OK\r\nCSeq: 3\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}".encode())
            else:
                c.sendall(f'RTSP/1.0 401 Unauthorized\r\nCSeq: 2\r\nWWW-Authenticate: Digest realm="cam", '
                          f'nonce="{nonce}"\r\n\r\n'.encode())
        c.close()

    def serve():
        while True:
            try:
                c, _ = s.accept()
            except OSError:
                return
            threading.Thread(target=serve_one, args=(c,), daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()
    return s, s.getsockname()[1]


def test_a_bispectrum_camera_answering_any_path_gives_its_two_real_channels():
    vis, ir = (2688, 1520, "Z2QAMqws"), (1280, 720, "Z2QAH6ws")
    srv, port = nonce_per_connection_server("admin", "pw", {
        "default": vis, "/Streaming/Channels/101": vis, "/Streaming/Channels/201": ir,
        "/Streaming/Channels/301": ir})
    try:
        d = cameras.rtsp_describe(f"rtsp://127.0.0.1:{port}/Streaming/Channels/201", "admin", "pw")
        assert d["status"] == 200 and d["size"] == [1280, 720]
        assert cameras.rtsp_describe(f"rtsp://127.0.0.1:{port}/x", "admin", "bad")["status"] == 401
        cams, notes = cameras.rtsp_scan([{"ipv4": [("127.0.0.0", 31)]}], "admin", "pw", ports=(port,))
    finally:
        srv.close()
    assert notes == [] and [c["id"].split(str(port))[1] for c in cams] == [
        "/Streaming/Channels/101", "/Streaming/Channels/201"]      # 301 is 201 again: left out
    assert [c["size"] for c in cams] == [[2688, 1520], [1280, 720]] and all(c["bispectrum"] for c in cams)


def test_one_camera_on_ipv4_and_ipv6_is_one_camera():
    assert cameras.eui64_mac("fe80::a614:37ff:fe84:d176%eth0") == "a4:14:37:84:d1:76"
    assert cameras.eui64_mac("fe80::f23:aaee:522e:8ddc") == ""          # a random (privacy) address
    assert cameras.eui64_mac("192.168.1.64") == ""


def test_a_grey_thermal_picture_with_a_coloured_overlay_box_is_grey():
    img = np.full((720, 1280, 3), 100, np.uint8)
    img[200:260, 200:330] = 240                                       # a warm object
    img[16:20, 32:1246] = img[700:704, 32:1246] = (255, 0, 0)         # the camera's blue rule box
    img[16:704, 32:36] = img[16:704, 1242:1246] = (255, 0, 0)
    assert cameras.picture_traits(img)["mono"] is True
    col = np.random.default_rng(0).integers(0, 255, (720, 1280, 3)).astype(np.uint8)
    assert cameras.picture_traits(col)["mono"] is False


def test_a_frame_is_really_sampled_through_the_child_process():
    """The child process writes the frame to a pipe (np.save needs a seekable file: it once failed
    there for every camera, unseen by the tests that faked sample_frame)."""
    pytest = __import__("pytest")
    try:
        import gi
        gi.require_version("Gst", "1.0")
    except (ImportError, ValueError):
        pytest.skip("no GStreamer")
    pipe = ("videotestsrc num-buffers=10 ! video/x-raw,width=320,height=240 ! videoconvert ! "
            + cameras.SINK)
    img = cameras.sample_frame(dict(kind="ip", pipeline=pipe))
    assert img is not None and img.shape == (240, 320, 3)


def test_the_grey_channel_of_a_two_sensor_camera_is_its_thermal_sensor_not_a_guess(monkeypatch):
    grey = np.full((120, 160, 3), 90, np.uint8)
    colour = np.random.default_rng(1).integers(0, 255, (120, 160, 3)).astype(np.uint8)
    pics = {"rtsp://10.0.0.5:554/Streaming/Channels/101": colour, "rtsp://10.0.0.5:554/Streaming/Channels/201": grey}
    monkeypatch.setattr(cameras, "sample_frame", lambda c: pics[c["id"]])
    cams = cameras.describe([dict(kind="ip", id=u, spectrum=None, size=[0, 0], bispectrum=True) for u in pics])
    assert [c["spectrum"] for c in cams] == ["rgb", "thermal"] and cams[1]["spectrum_guess"] is False
