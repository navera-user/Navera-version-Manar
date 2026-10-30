"""navera_common.cameras: what each camera is and which job it gets (no hardware: fake ONVIF and
RTSP servers on loopback, synthetic pictures)."""
import base64
import hashlib
import http.server
import re
import socket
import threading

import numpy as np

from navera_common import cameras
from navera_common.cameras import assign_roles, best_size, lens_info, picture_traits, role_settings


def cam(kind, ident, name=None, spectrum=None, sky=None, **kw):
    traits = None if sky is None else dict(mono=spectrum == "thermal", sky_score=sky, brightness=0.5, texture=0.1,
                                           blue=0.0, dark=False)
    d = dict(kind=kind, id=ident, name=name or ident, spectrum=spectrum, traits=traits, size=[1280, 720],
             hfov_deg=None, lens_model="pinhole")
    d.update(kw)
    return d


# ── what a camera is ───────────────────────────────────────────────────────
def test_lens_database_tells_thermal_cores_and_known_lenses():
    assert lens_info("09cb:4007 FLIR Boson")[0] == "thermal"
    assert lens_info("1e4e:0100 PureThermal (fw:v1.3.0)")[:2] == ("thermal", 57.0)
    assert lens_info("vi-output, imx219 9-0010")[:2] == ("rgb", 62.2)
    assert lens_info("HIKVISION DS-2TD2617B-3/PA")[0] == "thermal"
    assert lens_info("046d:0825 UVC Camera") == (None, None, "pinhole")


def test_best_size_prefers_mjpg_near_1080p_and_takes_a_thermal_core_as_it_is():
    fmts = {"MJPG": [(640, 480), (1920, 1080), (3840, 2160)], "YUYV": [(640, 480)]}
    assert best_size(fmts) == ("MJPG", (1920, 1080))
    assert best_size({"Y16 ": [(640, 512)]}) == ("Y16 ", (640, 512))


def ground_picture(seed=0):
    rng = np.random.default_rng(seed)
    import cv2
    img = (rng.uniform(0, 255, (360, 640, 3))).astype(np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 2.0)
    img[..., 0] = (img[..., 0] * 0.6).astype(np.uint8)          # earth tones: less blue than red
    return img


def sky_picture():
    y = np.linspace(0, 1, 360)[:, None]
    img = np.zeros((360, 640, 3), np.uint8)
    img[..., 0] = (235 - 30 * y).astype(np.uint8)                 # blue
    img[..., 1] = (190 - 30 * y).astype(np.uint8)
    img[..., 2] = (140 - 20 * y).astype(np.uint8)
    return img


def test_picture_traits_sky_ground_mono_and_16_bit():
    g, s = picture_traits(ground_picture()), picture_traits(sky_picture())
    assert s["sky_score"] > 0.3 > g["sky_score"] and s["sky_score"] - g["sky_score"] > 0.5
    assert not g["mono"] and not s["mono"]
    grey = np.repeat(ground_picture()[..., 1:2], 3, axis=2)
    assert picture_traits(grey)["mono"]
    raw16 = (np.random.default_rng(1).uniform(20000, 24000, (512, 640))).astype(np.uint16)
    t = picture_traits(raw16)
    assert t["mono"] and 0.2 < t["brightness"] < 0.8
    assert picture_traits(np.full((360, 640, 3), 8, np.uint8))["dark"]


# ── who does what ─────────────────────────────────────────────────────────
def test_one_colour_and_one_thermal_camera():
    r = assign_roles([cam("usb", "/dev/v4l/by-id/usb-Logitech-video-index0", spectrum="rgb"),
                      cam("usb", "/dev/v4l/by-id/usb-FLIR_Boson-video-index0", spectrum="thermal")], {})
    assert r["roles"]["day"]["id"].endswith("Logitech-video-index0")
    assert r["roles"]["thermal"]["id"].endswith("Boson-video-index0")
    assert "star" not in r["roles"]


def test_two_colour_cameras_the_one_seeing_sky_is_the_star_camera():
    r = assign_roles([cam("usb", "/dev/a", spectrum="rgb", sky=0.9), cam("usb", "/dev/b", spectrum="rgb", sky=-0.6)], {})
    assert r["roles"]["star"]["id"] == "/dev/a" and r["roles"]["day"]["id"] == "/dev/b"


def test_two_colour_cameras_that_look_alike_are_reported_not_guessed():
    r = assign_roles([cam("usb", "/dev/a", spectrum="rgb", sky=0.1), cam("usb", "/dev/b", spectrum="rgb", sky=0.0)], {})
    assert "star" not in r["roles"] and r["roles"]["day"]["id"] == "/dev/b"     # the less sky-like
    assert any(x.startswith("CHECK two colour cameras") for x in r["report"])


def test_names_say_sky_and_ground_ros_topics_too():
    r = assign_roles([cam("ros", "/vehicle/camera_up/image_raw", spectrum="rgb"),
                      cam("ros", "/vehicle/camera_down/image_raw", spectrum="rgb"),
                      cam("ros", "/vehicle/thermal/image_raw", spectrum="thermal")], {})
    assert r["roles"]["star"]["id"] == "/vehicle/camera_up/image_raw"
    assert r["roles"]["day"]["id"] == "/vehicle/camera_down/image_raw"
    assert r["roles"]["thermal"]["id"] == "/vehicle/thermal/image_raw"


def test_a_camera_written_in_navera_env_keeps_its_job_and_is_no_candidate():
    env = {"NAVERA_STAR_CAMERA_DEVICE": "/dev/a"}
    r = assign_roles([cam("usb", "/dev/a", spectrum="rgb", sky=-1.0), cam("usb", "/dev/b", spectrum="rgb")], env)
    assert r["roles"]["day"]["id"] == "/dev/b" and "star" not in r["roles"]


def test_with_the_insta360_kit_a_second_colour_camera_must_clearly_see_sky():
    looks_up = assign_roles([cam("usb", "/dev/a", spectrum="rgb", sky=0.8)], {}, day_taken=True)
    assert looks_up["roles"]["star"]["id"] == "/dev/a" and "day" not in looks_up["roles"]
    unclear = assign_roles([cam("usb", "/dev/a", spectrum="rgb", sky=-0.2)], {}, day_taken=True)
    assert not unclear["roles"] and any("not used" in x for x in unclear["report"])


def test_a_thermal_guess_from_a_grey_picture_is_flagged():
    c = cam("usb", "/dev/a", spectrum="thermal", sky=-0.3)
    c["spectrum_guess"] = True
    r = assign_roles([c], {})
    assert r["roles"]["thermal"] is c and any(x.startswith("CHECK thermal camera") for x in r["report"])


def test_role_settings_never_carry_a_password_and_fill_only_what_is_not_written():
    c = cam("ip", "rtsp://10.0.0.5/ch1", name="HIKVISION DS-2TD visible", spectrum="rgb",
            pipeline=cameras.gst_rtsp_pipeline("rtsp://admin:secret@10.0.0.5/ch1", "H265", True))
    env = {"NAVERA_IP_CAMERA_PASSWORD": "secret", "NAVERA_CAMERA_FPS": "2"}
    s = role_settings("day", c, env)
    assert s["NAVERA_CAMERA_INPUT"] == "gst" and "secret" not in "".join(s.values())
    assert "@NAVERA_IP_CAMERA_PASSWORD@" in s["NAVERA_CAMERA_GST_PIPELINE"] and "rtph265depay" in \
        s["NAVERA_CAMERA_GST_PIPELINE"]
    assert s["NAVERA_CAMERA_HFOV_DEG"] == "70" and s["NAVERA_CAMERA_LENS_SOURCE"] == "guess"
    t = role_settings("thermal", cam("usb", "/dev/b", spectrum="thermal", fourcc="Y16 ", hfov_deg=57.0),
                      {"NAVERA_THERMAL_CAMERA_HFOV_DEG": "50"})
    assert t["NAVERA_THERMAL_CAMERA_FOURCC"] == "Y16" and "NAVERA_THERMAL_CAMERA_HFOV_DEG" not in t


def test_the_camera_node_fills_the_secrets_in():
    from camera_pkg.gst_capture import expand_secrets
    p = cameras.gst_rtsp_pipeline("rtsp://cam/ch1", "H264", True)
    out = expand_secrets(p, {"NAVERA_IP_CAMERA_USER": "admin", "NAVERA_IP_CAMERA_PASSWORD": 'p"w'})
    assert 'user-id="admin"' in out and 'user-pw="p\\"w"' in out and "@" not in out.split("location=")[0]


# ── network cameras (fake servers on loopback) ─────────────────────────────
PROFILES = ('<trt:GetProfilesResponse><trt:Profiles token="Profile_1"><tt:Name>mainStream</tt:Name>'
            '<tt:VideoSourceConfiguration><tt:SourceToken>VideoSource_1</tt:SourceToken></tt:VideoSourceConfiguration>'
            '<tt:Resolution><tt:Width>2688</tt:Width><tt:Height>1520</tt:Height></tt:Resolution></trt:Profiles>'
            '<trt:Profiles token="Profile_2"><tt:Name>thermalStream</tt:Name><tt:VideoSourceConfiguration>'
            '<tt:SourceToken>VideoSource_2</tt:SourceToken></tt:VideoSourceConfiguration><tt:Resolution>'
            '<tt:Width>1280</tt:Width><tt:Height>720</tt:Height></tt:Resolution></trt:Profiles>'
            '</trt:GetProfilesResponse>')


def onvif_server(password):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            ok = False
            m = re.search(r"<Username>(.*?)</Username><Password[^>]*>(.*?)</Password><Nonce[^>]*>(.*?)</Nonce>"
                          r"<Created[^>]*>(.*?)</Created>", body)
            if m:
                want = base64.b64encode(hashlib.sha1(base64.b64decode(m.group(3)) + m.group(4).encode()
                                                     + password.encode()).digest()).decode()
                ok = m.group(1) == "admin" and m.group(2) == want
            if not ok:
                txt = "<s:Fault><s:Code><s:Value>s:Sender</s:Value></s:Code><s:Reason>NotAuthorized</s:Reason></s:Fault>"
            elif "GetDeviceInformation" in body:
                txt = "<tds:Manufacturer>HIKVISION</tds:Manufacturer><tds:Model>DS-2TD2617B-3/PA</tds:Model>"
            elif "GetCapabilities" in body:
                txt = f"<tt:Media><tt:XAddr>http://127.0.0.1:{self.server.server_port}/onvif/Media</tt:XAddr></tt:Media>"
            elif "GetProfiles" in body:
                txt = PROFILES
            elif "GetStreamUri" in body:
                ch = "101" if "Profile_1" in body else "201"
                txt = f"<tt:Uri>rtsp://127.0.0.1:1/Streaming/Channels/{ch}</tt:Uri>"
            else:
                txt = ""
            data = f"<s:Envelope><s:Body>{txt}</s:Body></s:Envelope>".encode()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_onvif_streams_of_a_bispectrum_camera_with_its_login():
    srv = onvif_server("pw123")
    try:
        dev = {"xaddrs": [f"http://127.0.0.1:{srv.server_port}/onvif/device_service"], "scopes": "", "iface": "lo"}
        d = cameras.onvif_streams(dev, "admin", "pw123")
        assert d["maker"] == "HIKVISION" and d["model"].startswith("DS-2TD")
        assert [s["uri"].rsplit("/", 1)[1] for s in d["streams"]] == ["101", "201"]
        assert d["streams"][1]["name"] == "thermalStream" and d["streams"][0]["width"] == 2688
        refused = cameras.onvif_streams(dev, "admin", "wrong")
        assert refused.get("auth") == "refused" and not refused["streams"]
        assert cameras.onvif_streams(dev).get("auth") == "needed"
    finally:
        srv.shutdown()


def rtsp_server(user, password, codec="H265"):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(4)

    def serve():
        while True:
            try:
                c, _ = s.accept()
            except OSError:
                return
            req = c.recv(65536).decode()
            m = re.search(r'response="([0-9a-f]+)"', req)
            uri = re.match(r"DESCRIBE (\S+)", req).group(1)
            ha1 = hashlib.md5(f"{user}:cam:{password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode()).hexdigest()
            good = m and m.group(1) == hashlib.md5(f"{ha1}:n0nce:{ha2}".encode()).hexdigest()
            if good:
                sdp = f"v=0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 {codec}/90000\r\n"
                c.sendall(f"RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Length: {len(sdp)}\r\n\r\n{sdp}".encode())
            else:
                c.sendall(b'RTSP/1.0 401 Unauthorized\r\nCSeq: 2\r\nWWW-Authenticate: Digest realm="cam", '
                          b'nonce="n0nce"\r\n\r\n')
            c.close()
    threading.Thread(target=serve, daemon=True).start()
    return s


def test_rtsp_describe_with_digest_login_gives_the_codec():
    s = rtsp_server("admin", "pw")
    try:
        url = f"rtsp://127.0.0.1:{s.getsockname()[1]}/Streaming/Channels/101"
        d = cameras.rtsp_describe(url, "admin", "pw")
        assert (d["status"], d["codec"]) == (200, "H265")
        assert cameras.rtsp_describe(url, "admin", "bad")["status"] == 401
        assert cameras.rtsp_describe("rtsp://127.0.0.1:1/x") is None            # nothing there
    finally:
        s.close()


def test_a_scoped_ipv6_link_local_address_keeps_its_interface():
    assert cameras._scoped("http://[fe80::a614:37ff:fe84:d176]/onvif/device_service", "enP8p1s0") == \
        "http://[fe80::a614:37ff:fe84:d176%enP8p1s0]/onvif/device_service"
    assert cameras._scoped("http://192.168.1.64/onvif", "eth0") == "http://192.168.1.64/onvif"


def test_v4l2_query_of_a_missing_device_is_none():
    assert cameras.v4l2_query("/dev/does-not-exist") is None


def test_rtsp_describe_reconnects_when_a_reused_connection_was_reset(monkeypatch):
    """The camera closes the connection after its 401: the login's read on the reused socket can raise
    ECONNRESET (seen as a flaky probe returning None); it must reconnect instead."""
    s = rtsp_server("admin", "pw")
    real = socket.create_connection
    made = []

    class ResetOnSecondRead:
        def __init__(self, sock):
            self.sock, self.reads = sock, 0

        def recv(self, n):
            self.reads += 1
            if self.reads == 2:
                raise ConnectionResetError(104, "Connection reset by peer")
            return self.sock.recv(n)

        def __getattr__(self, name):
            return getattr(self.sock, name)

    def create(*a, **k):
        c = real(*a, **k)
        made.append(c)
        return ResetOnSecondRead(c) if len(made) == 1 else c
    monkeypatch.setattr(cameras.socket, "create_connection", create)
    try:
        url = f"rtsp://127.0.0.1:{s.getsockname()[1]}/Streaming/Channels/101"
        d = cameras.rtsp_describe(url, "admin", "pw")
        assert d is not None and (d["status"], d["codec"]) == (200, "H265") and len(made) >= 2
    finally:
        s.close()
