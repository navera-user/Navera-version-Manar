"""Every camera plugged into the box: what it is, and which job it gets.

The client plugs a camera — or two — and NAVERA works out the rest (navera_common.discovery calls
this at boot, navera_common.hotplug when a camera appears later):

  find      USB / UVC cameras (/dev/v4l/by-id, an HDMI capture stick is one too), Jetson CSI
            cameras, network cameras (ONVIF WS-Discovery on every wired interface, IPv4 and IPv6
            link-local — a camera with a static address in another subnet answers on IPv6 — and the
            fixed addresses of common drone gimbal cameras, e.g. SIYI 192.168.144.25:8554), and the
            vehicle's ROS image topics (discovery.probe_ros);
  describe  colour or thermal: the USB id / name / model (FLIR Boson, Lepton / PureThermal, Seek,
            InfiRay, Hikvision "2TD" ...), a grey-only pixel format (Y16, GREY: a radiometric core),
            and the picture itself (one channel, R = G = B); looking at the GROUND or the SKY: the
            picture (a day sky is bright, smooth, blue or white; ground has texture — two cameras
            are compared with each other, which is far surer than either alone); the topic / stream
            name when it says (down, nadir / sky, star, up);
  assign    day   = the colour camera looking down (day vision, NAVERA_CAMERA_*),
            thermal = the thermal camera looking down (night vision, NAVERA_THERMAL_CAMERA_*),
            star  = the camera looking up (celestial, NAVERA_STAR_CAMERA_*).
            A value written in navera.env always wins; what cannot be told apart is reported with
            CHECK (check_box, the web page), never guessed silently.

The lens: a known camera gets its field of view from LENS_DB (a starting value, `lens_source`
"database"); any other one the generic guess GUESS_HFOV_DEG. Neither is a calibration: the day
pipeline calibrates the lens in flight against the map while the GPS is trusted (day_pkg.lens_selfcal)
and the star pipeline from the stars (plate scale); navera_tools/calibrate_camera.py stays the
bench method, and a file it wrote always wins.

Probing READS only: V4L2 devices are queried (VIDIOC_QUERYCAP / ENUM_FMT / ENUM_FRAMESIZES, no
streaming) and one frame is read in a child process with a time limit (a stuck driver cannot hang
the boot); a device another process holds is never opened; the Insta360 in Android mode is never
opened (discovery.probe_insta360, D10). Network passwords: NAVERA_IP_CAMERA_USER /
NAVERA_IP_CAMERA_PASSWORD (navera.env); they are never written into discovered.env or the JSON
report — the pipeline written there names them (@NAVERA_IP_CAMERA_USER@ ...) and the camera node
fills them in at start (gst_capture.expand_secrets).
"""
import base64
import fcntl
import glob
import hashlib
import ipaddress
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import uuid
from typing import Dict, List, Optional, Tuple

# ── lens starting values ───────────────────────────────────────────────────
# (pattern on "vendor:product name model", spectrum, horizontal field of view deg or None, lens model)
# Only values from the makers' datasheets; a camera sold with several lenses has None (the in-flight
# calibration, or NAVERA_<ROLE>_HFOV_DEG, sets it).
LENS_DB = (
    (r"09cb:4007|\bboson\b", "thermal", None, "pinhole"),             # FLIR Boson: 4-95 deg lenses
    (r"1e4e:0100|purethermal|lepton ?3", "thermal", 57.0, "pinhole"),  # Lepton 3.x on PureThermal
    (r"lepton ?2", "thermal", 51.0, "pinhole"),
    (r"289d:00\d\d|seek ?thermal", "thermal", None, "pinhole"),
    (r"infiray|hikmicro|\btc001\b|tiny1|\bp2 ?pro\b", "thermal", None, "pinhole"),
    (r"ds-2td\d", "thermal", None, "pinhole"),                         # Hikvision thermal / bi-spectrum
    (r"\bthermal\b|\blwir\b|\bflir\b|thermo", "thermal", None, "pinhole"),
    (r"imx219", "rgb", 62.2, "pinhole"),                               # Raspberry Pi camera v2
    (r"imx708_wide", "rgb", 102.0, "fisheye"),                         # Raspberry Pi camera 3 wide
    (r"imx708", "rgb", 66.0, "pinhole"),                               # Raspberry Pi camera 3
    (r"046d:082d|\bc920\b", "rgb", 70.4, "pinhole"),                   # Logitech C920
    (r"siyi.*a8|a8 ?mini", "rgb", 81.0, "pinhole"),
)
GUESS_HFOV_DEG = 70.0          # an unknown camera: a common webcam / gimbal width; refined in flight
GREY_FORMATS = {"Y16 ", "Y12 ", "Y10 ", "Y8  ", "GREY", "Y16B", "B16 "}
SKY_WORDS, GROUND_WORDS = r"sky|star|zenith|(?<![a-z])up(?![a-z])|upward|celest", r"down|nadir|bottom|ground"
THERMAL_WORDS = r"thermal|\blwir\b|\bir\b|/ir/|infrared|\bflir\b|boson|lepton"
ROLES = {"day": "NAVERA_CAMERA_", "thermal": "NAVERA_THERMAL_CAMERA_", "star": "NAVERA_STAR_CAMERA_"}
# drone cameras that stream without a password at a fixed address (probed only when an interface
# of the box is in that subnet)
FIXED_RTSP = (
    ("192.168.144.0/24", "rtsp://192.168.144.25:8554/main.264", "SIYI gimbal camera"),
    ("192.168.144.0/24", "rtsp://192.168.144.25:8554/video1", "SIYI gimbal camera (ZT / ZR)"),
    ("192.168.144.0/24", "rtsp://192.168.144.25:8554/video2", "SIYI gimbal camera, second sensor"),
    ("192.168.144.0/24", "rtsp://192.168.144.108:554/stream=1", "Skydroid camera"),
    ("192.168.43.0/24", "rtsp://192.168.43.1:8554/fpv_stream", "Herelink air unit camera"),
)


def lens_info(text: str) -> Tuple[Optional[str], Optional[float], str]:
    """(spectrum or None, hfov deg or None, model) of the first LENS_DB entry matching text."""
    t = text.lower()
    for pat, spectrum, hfov, model in LENS_DB:
        if re.search(pat, t):
            return spectrum, hfov, model
    return None, None, "pinhole"


# ── USB / CSI (V4L2) ───────────────────────────────────────────────────────
def _ioc(direction, nr, size):
    return (direction << 30) | (size << 16) | (ord("V") << 8) | nr


VIDIOC_QUERYCAP = _ioc(2, 0, 104)
VIDIOC_ENUM_FMT = _ioc(3, 2, 64)
VIDIOC_ENUM_FRAMESIZES = _ioc(3, 74, 44)
V4L2_BUF_TYPE_VIDEO_CAPTURE, V4L2_CAP_VIDEO_CAPTURE, V4L2_CAP_DEVICE_CAPS = 1, 0x1, 0x80000000


def _cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("ascii", "replace").strip()


def v4l2_query(dev: str) -> Optional[dict]:
    """{card, driver, bus, formats: {fourcc: [(w, h), ...]}} of a capture device, None if it is not one."""
    try:
        fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        cap = bytearray(104)
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, cap)
        caps, dcaps = struct.unpack_from("<II", cap, 84)
        if not ((dcaps if caps & V4L2_CAP_DEVICE_CAPS else caps) & V4L2_CAP_VIDEO_CAPTURE):
            return None                                   # a metadata node of the same camera
        out = {"card": _cstr(cap[16:48]), "driver": _cstr(cap[0:16]), "bus": _cstr(cap[48:80]), "formats": {}}
        for i in range(32):
            fd_ = bytearray(64)
            struct.pack_into("<II", fd_, 0, i, V4L2_BUF_TYPE_VIDEO_CAPTURE)
            try:
                fcntl.ioctl(fd, VIDIOC_ENUM_FMT, fd_)
            except OSError:
                break
            pixfmt = struct.unpack_from("<I", fd_, 44)[0]
            fourcc = struct.pack("<I", pixfmt).decode("ascii", "replace")
            sizes = []
            for j in range(64):
                fs = bytearray(44)
                struct.pack_into("<II", fs, 0, j, pixfmt)
                try:
                    fcntl.ioctl(fd, VIDIOC_ENUM_FRAMESIZES, fs)
                except OSError:
                    break
                kind = struct.unpack_from("<I", fs, 8)[0]
                if kind == 1:                             # discrete
                    sizes.append(struct.unpack_from("<II", fs, 12))
                else:                                     # stepwise / continuous: the largest
                    sizes.append(struct.unpack_from("<II", fs, 16)[0:1] + struct.unpack_from("<I", fs, 24))
                    break
            out["formats"][fourcc] = sorted(set(sizes))
        return out
    except OSError:
        return None
    finally:
        os.close(fd)


def usb_ids(dev: str, sysfs: str = "/sys/class/video4linux") -> str:
    """'vvvv:pppp' of the USB device behind /dev/videoN ('' when not USB)."""
    d = os.path.realpath(os.path.join(sysfs, os.path.basename(os.path.realpath(dev)), "device"))
    for _ in range(4):
        try:
            v = open(os.path.join(d, "idVendor")).read().strip()
            p = open(os.path.join(d, "idProduct")).read().strip()
            return f"{v}:{p}".lower()
        except OSError:
            d = os.path.dirname(d)
    return ""


def held_by(dev: str) -> Optional[int]:
    """The pid of a process that has dev open (never opened then), None if none."""
    real = os.path.realpath(dev)
    for fd in glob.glob("/proc/[0-9]*/fd/*"):
        try:
            if os.readlink(fd) == real:
                return int(fd.split("/")[2])
        except OSError:
            continue
    return None


def best_size(formats: Dict[str, list], want=(1920, 1080)) -> Tuple[str, Tuple[int, int]]:
    """(fourcc, (w, h)): MJPG at the size nearest the wanted one (a 1 fps vision feed needs no more),
    else the format with the largest size (a thermal core: Y16 at its only size)."""
    def near(sizes):
        return min(sizes, key=lambda s: (abs(s[0] * s[1] - want[0] * want[1]), -s[0]))
    for fc in ("MJPG", "YUYV", "NV12", "UYVY"):
        if formats.get(fc):
            return fc, near(formats[fc])
    fc = max(formats, key=lambda f: max((w * h for w, h in formats[f]), default=0), default="")
    return fc, (max(formats[fc], key=lambda s: s[0] * s[1]) if fc and formats[fc] else (0, 0))


def usb_cameras() -> List[dict]:
    """The USB cameras (by-id name, its USB id, V4L2 description, best size), the Insta360 kit excluded."""
    cams = []
    for path in sorted(glob.glob("/dev/v4l/by-id/*-video-index0")):
        q = v4l2_query(path) or {}
        ids = usb_ids(path)
        text = f"{ids} {os.path.basename(path)} {q.get('card', '')}"
        spectrum, hfov, model = lens_info(text)
        fmts = q.get("formats") or {}
        fourcc, size = best_size(fmts) if fmts else ("", (0, 0))
        if spectrum is None and fmts and set(fmts) <= GREY_FORMATS:
            spectrum = "thermal"                          # grey-only formats: a radiometric core
        cams.append(dict(kind="usb", id=path, name=q.get("card") or os.path.basename(path), usb_id=ids,
                         spectrum=spectrum, hfov_deg=hfov, lens_model=model, fourcc=fourcc,
                         size=list(size), formats={k: [list(s) for s in v] for k, v in fmts.items()}))
    return cams


def csi_cameras(sysfs: str = "/sys/class/video4linux") -> List[dict]:
    out = []
    for d in sorted(glob.glob(os.path.join(sysfs, "video*"))):
        try:
            name = open(os.path.join(d, "name")).read().strip()
        except OSError:
            continue
        if "vi-output" in name or re.search(r"\b(imx|ov)\d", name, re.I):
            _, hfov, model = lens_info(name)
            m = re.search(r"(\d+)-00", name)
            out.append(dict(kind="csi", id=name, name=name, sensor=str(len(out)), spectrum="rgb",
                            hfov_deg=hfov, lens_model=model, i2c_bus=m.group(1) if m else None))
    return out


# ── network cameras (ONVIF, fixed drone-camera addresses) ──────────────────
WSD_PROBE = ('<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
             'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
             'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
             'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><e:Header>'
             '<w:MessageID>uuid:{id}</w:MessageID><w:To e:mustUnderstand="true">'
             'urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To><w:Action e:mustUnderstand="true">'
             'http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header><e:Body>'
             '<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>')
SKIP_IFACES = re.compile(r"^(lo|docker|l4tbr|tailscale|wg|tun|virbr|veth|br-|can|usb\d)")


def wired_interfaces(wifi: bool = False) -> List[dict]:
    """[{name, ipv4: [(addr, prefix)], index}] of the interfaces that are up (no loopback/VPN/docker).
    Wi-Fi only with wifi=True (NAVERA_DISCOVER_IP_CAMERAS=wifi): on a hangar or office Wi-Fi a security
    camera would answer like the vehicle's own; drone cameras are on the vehicle's Ethernet."""
    out = []
    for name in sorted(os.listdir("/sys/class/net")):
        if SKIP_IFACES.match(name) or (not wifi and (name.startswith("wl") or
                                                     os.path.isdir(f"/sys/class/net/{name}/wireless"))):
            continue
        try:
            if open(f"/sys/class/net/{name}/operstate").read().strip() not in ("up", "unknown"):
                continue
            idx = socket.if_nametoindex(name)
        except OSError:
            continue
        out.append(dict(name=name, index=idx, ipv4=ipv4_of(name)))
    return out


def ipv4_of(name: str) -> List[Tuple[str, int]]:
    """[(address, prefix)] of one interface."""
    try:
        txt = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", name], capture_output=True,
                             text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [(a, int(p)) for a, p in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", txt)]


def ws_discovery(ifaces: List[dict], wait_s: float = 2.5) -> List[dict]:
    """[{xaddrs: [url], scopes: str, iface}] of the ONVIF devices answering a WS-Discovery probe."""
    msg = WSD_PROBE.format(id=uuid.uuid4()).encode()
    socks = []
    for f in ifaces:
        for addr, _ in f["ipv4"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(addr))
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                s.bind((addr, 0))
                s.sendto(msg, ("239.255.255.250", 3702))
                socks.append((s, f["name"]))
            except OSError:
                pass
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, f["index"])
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 1)
            s.sendto(msg, ("ff02::c", 3702, 0, f["index"]))
            socks.append((s, f["name"]))
        except OSError:
            pass
    found, end = {}, time.monotonic() + wait_s
    while socks and time.monotonic() < end:
        for s, name in socks:
            s.settimeout(0.05)
            try:
                data, _ = s.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            txt = data.decode("utf-8", "replace")
            xa = re.search(r"<[^>]*XAddrs>([^<]+)<", txt)
            if not xa:
                continue
            urls = xa.group(1).split()
            key = re.search(r"<[^>]*Address>([^<]+)<", txt)
            key = key.group(1) if key else urls[0]
            sc = re.search(r"<[^>]*Scopes[^>]*>([^<]*)<", txt)
            found.setdefault(key, dict(xaddrs=urls, scopes=sc.group(1) if sc else "", iface=name))
    for s, _ in socks:
        s.close()
    return list(found.values())


def _scoped(url: str, iface: str) -> str:
    """An IPv6 link-local URL with its interface (http://[fe80::1%enP8p1s0]/...)."""
    m = re.match(r"(\w+://)\[(fe80:[^\]%]+)\](.*)", url, re.I)
    return f"{m.group(1)}[{m.group(2)}%{iface}]{m.group(3)}" if m else url


def _soap(url: str, body: str, user: str = "", password: str = "", timeout: float = 4.0) -> Optional[str]:
    """POST one ONVIF request (WS-UsernameToken digest when a user is given); the reply text or None."""
    import urllib.request
    head = ""
    if user:
        nonce = os.urandom(16)
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
        head = ('<s:Header><Security xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-'
                'secext-1.0.xsd"><UsernameToken><Username>{u}</Username><Password Type="http://docs.oasis-open.'
                'org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{d}</Password><Nonce '
                'EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#'
                'Base64Binary">{n}</Nonce><Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-'
                'wssecurity-utility-1.0.xsd">{c}</Created></UsernameToken></Security></s:Header>').format(
            u=user, d=digest, n=base64.b64encode(nonce).decode(), c=created)
    env = (f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
           f'{head}<s:Body>{body}</s:Body></s:Envelope>')
    host = re.match(r"\w+://\[([^\]]+)\]", url)
    try:
        if host and "%" in host.group(1):                 # urllib cannot open a scoped IPv6 URL
            return _soap_raw(url, env, timeout)
        req = urllib.request.Request(url, env.encode(), {"Content-Type": "application/soap+xml; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:                                 # noqa: BLE001 — a probe never raises
        txt = getattr(e, "read", lambda: b"")()
        return txt.decode("utf-8", "replace") if txt else None


def _soap_raw(url: str, envelope: str, timeout: float) -> Optional[str]:
    m = re.match(r"\w+://\[([^\]%]+)%([^\]]+)\](?::(\d+))?(/.*)?", url)
    if not m:
        return None
    addr, iface, port, path = m.group(1), m.group(2), int(m.group(3) or 80), m.group(4) or "/"
    data = envelope.encode()
    try:
        with socket.create_connection((f"{addr}%{iface}", port), timeout=timeout) as s:
            s.sendall((f"POST {path} HTTP/1.1\r\nHost: [{addr}]\r\nContent-Type: application/soap+xml; "
                       f"charset=utf-8\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode() + data)
            chunks = []
            while True:
                b = s.recv(65536)
                if not b:
                    break
                chunks.append(b)
        raw = b"".join(chunks)
        return raw.split(b"\r\n\r\n", 1)[-1].decode("utf-8", "replace")
    except OSError:
        return None


def _tag(txt: str, name: str) -> List[str]:
    return re.findall(rf"<(?:\w+:)?{name}[^>]*>([^<]*)</(?:\w+:)?{name}>", txt or "")


def onvif_streams(dev: dict, user: str = "", password: str = "") -> dict:
    """{name, model, maker, streams: [{uri, width, height, name}], auth} of one ONVIF device."""
    url = _scoped(dev["xaddrs"][0], dev.get("iface", ""))
    info = _soap(url, '<GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>', user, password) or ""
    scopes = dev.get("scopes", "")
    out = dict(url=url, maker=(_tag(info, "Manufacturer") or [""])[0],
               model=(_tag(info, "Model") or re.findall(r"onvif://www.onvif.org/hardware/(\S+)", scopes) or [""])[0],
               name=(re.findall(r"onvif://www.onvif.org/name/(\S+)", scopes) or [""])[0], streams=[])
    if "NotAuthorized" in info or "Sender" in info and not out["maker"]:
        out["auth"] = "needed"
    caps = _soap(url, '<GetCapabilities xmlns="http://www.onvif.org/ver10/device/wsdl"><Category>Media</Category>'
                      '</GetCapabilities>', user, password) or ""
    media = re.search(r"<(?:\w+:)?Media>\s*<(?:\w+:)?XAddr>([^<]+)<", caps)
    media = _scoped(media.group(1), dev.get("iface", "")) if media else url
    prof = _soap(media, '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>', user, password) or ""
    if "NotAuthorized" in prof:
        out["auth"] = "needed" if not user else "refused"
        return out
    for m in re.finditer(r"<(?:\w+:)?Profiles[^>]*token=\"([^\"]+)\"(.*?)</(?:\w+:)?Profiles>", prof, re.S):
        token, body = m.group(1), m.group(2)
        w, h = (_tag(body, "Width") or ["0"])[0], (_tag(body, "Height") or ["0"])[0]
        src = re.search(r"SourceToken>([^<]+)<", body)
        r = _soap(media, '<GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl"><StreamSetup><Stream '
                         'xmlns="http://www.onvif.org/ver10/schema">RTP-Unicast</Stream><Transport xmlns="http://'
                         'www.onvif.org/ver10/schema"><Protocol>RTSP</Protocol></Transport></StreamSetup>'
                         f'<ProfileToken>{token}</ProfileToken></GetStreamUri>', user, password) or ""
        uri = (_tag(r, "Uri") or [""])[0].replace("&amp;", "&")
        if uri:
            out["streams"].append(dict(uri=_scoped(uri, dev.get("iface", "")), width=int(w or 0), height=int(h or 0),
                                       name=(_tag(body, "Name") or [token])[0],
                                       source=src.group(1) if src else ""))
    return out


def rtsp_describe(uri: str, user: str = "", password: str = "", timeout: float = 4.0) -> Optional[dict]:
    """{codec: H264|H265|JPEG|?, status} from an RTSP DESCRIBE (Basic or Digest auth), None: no answer."""
    m = re.match(r"rtsp://(?:[^@/]*@)?(\[[^\]]+\]|[^:/]+)(?::(\d+))?(/.*)?", uri)
    if not m:
        return None
    host, port = m.group(1).strip("[]"), int(m.group(2) or 554)
    clean = re.sub(r"rtsp://[^@/]*@", "rtsp://", uri)

    conn = {}

    def ask(auth: str = "", cseq: int = 2) -> Tuple[int, str]:
        # the login goes on the connection that got the challenge: some cameras (Hikvision) tie
        # the nonce to it and refuse it on a new one
        reused = "s" in conn
        s = conn.get("s")
        if s is None:
            s = conn["s"] = socket.create_connection((host, port), timeout=timeout)
        try:
            s.sendall(f"DESCRIBE {clean} RTSP/1.0\r\nCSeq: {cseq}\r\nAccept: application/sdp\r\n{auth}\r\n".encode())
        except OSError:
            if not reused:
                raise
            conn.pop("s").close()
            return ask(auth, cseq)
        data, t_end = b"", time.monotonic() + timeout
        while time.monotonic() < t_end:
            b = s.recv(65536)
            if not b:
                conn.pop("s").close()                     # closed by the camera: a new one if asked again
                break
            data += b
            head, _, body = data.partition(b"\r\n\r\n")
            n = re.search(rb"Content-Length:\s*(\d+)", head, re.I)
            if _ and len(body) >= (int(n.group(1)) if n else 0):
                break
        if not data and reused:                           # the camera had closed it: a new connection
            return ask(auth, cseq)
        txt = data.decode("utf-8", "replace")
        code = re.match(r"RTSP/1.0 (\d+)", txt)
        return (int(code.group(1)) if code else 0), txt
    try:
        d = _rtsp_describe(ask, clean, user, password)
        if d["status"] == 401 and user:
            # refused although logged in: some cameras (Hikvision) mix up the nonces of logins that
            # arrive together — once more on a new connection before calling the password wrong
            if conn.get("s"):
                conn.pop("s").close()
            time.sleep(0.3)
            d = _rtsp_describe(ask, clean, user, password)
        return d
    except OSError:
        return None
    finally:
        if conn.get("s"):
            conn["s"].close()


def _rtsp_describe(ask, clean: str, user: str, password: str) -> dict:
    """DESCRIBE, then again with the login when challenged: {status, codec}."""
    code, txt = ask()
    if code == 401 and user:
        ch = re.search(r'WWW-Authenticate:\s*Digest\s+(.*)', txt, re.I)
        if ch:
            kv = dict(re.findall(r'(\w+)="([^"]*)"', ch.group(1)))
            ha1 = hashlib.md5(f"{user}:{kv.get('realm', '')}:{password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"DESCRIBE:{clean}".encode()).hexdigest()
            resp = hashlib.md5(f"{ha1}:{kv.get('nonce', '')}:{ha2}".encode()).hexdigest()
            auth = (f'Authorization: Digest username="{user}", realm="{kv.get("realm", "")}", '
                    f'nonce="{kv.get("nonce", "")}", uri="{clean}", response="{resp}"\r\n')
        else:
            auth = "Authorization: Basic " + base64.b64encode(f"{user}:{password}".encode()).decode() + "\r\n"
        code, txt = ask(auth, 3)
    codec = re.search(r"a=rtpmap:\d+\s+(H264|H265|HEVC|JPEG)", txt, re.I)
    size = re.search(r"a=(?:x-dimensions:|framesize:\d+\s+)(\d+)[,-](\d+)", txt)
    # what tells two streams apart: their encoder parameters (SPS/PPS) and size, not their path (a
    # camera may answer any path with its default stream)
    sprop = re.search(r"sprop-(?:parameter-sets|vps|sps)=([^;\s]+)", txt)
    return dict(status=code, codec=(codec.group(1).upper().replace("HEVC", "H265") if codec else "?"),
                size=[int(size.group(1)), int(size.group(2))] if size else [0, 0],
                fingerprint=f"{sprop.group(1) if sprop else ''} {size.group(0) if size else ''}".strip())


def gst_rtsp_pipeline(uri: str, codec: str, auth: bool) -> str:
    """The NAVERA_*_GST_PIPELINE for an RTSP stream: hardware decoding (the box has no software
    decoder, navera.env), credentials as @NAVERA_IP_CAMERA_USER@ / @NAVERA_IP_CAMERA_PASSWORD@ (filled in at start)."""
    clean = re.sub(r"rtsp://[^@/]*@", "rtsp://", uri)
    cred = " user-id=@NAVERA_IP_CAMERA_USER@ user-pw=@NAVERA_IP_CAMERA_PASSWORD@" if auth else ""
    if codec == "JPEG":
        dec = "rtpjpegdepay ! jpegdec ! videoconvert"
    else:
        c = "h265" if codec == "H265" else "h264"
        dec = f"rtp{c}depay ! {_hw_decode(c)}"
    return f"rtspsrc location={clean} protocols=tcp latency=0{cred} ! {dec} ! {SINK}"


SINK = "video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false"


def _hw_decode(c: str) -> str:
    return (f"video/x-{c},stream-format=byte-stream,alignment=au ! nvv4l2decoder ! nvvidconv ! "
            "video/x-raw,format=BGRx ! videoconvert")


def udp_pipeline(port: int, codec: str = "H264", ts: bool = False) -> str:
    """A stream the camera SENDS to the box: RTP (ts=False) or MPEG-TS (ts=True) over UDP."""
    c = "h265" if codec == "H265" else "h264"
    src = (f"udpsrc port={int(port)} ! tsdemux ! {c}parse ! " if ts else
           f"udpsrc port={int(port)} ! application/x-rtp,media=video,clock-rate=90000,encoding-name={c.upper()} ! "
           f"rtp{c}depay ! ")
    return f"{src}{_hw_decode(c)} ! {SINK}"


def tcp_ts_pipeline(host: str, port: int, codec: str = "H264") -> str:
    c = "h265" if codec == "H265" else "h264"
    return f"tcpclientsrc host={host} port={int(port)} ! tsdemux ! {c}parse ! {_hw_decode(c)} ! {SINK}"


def network_cameras(env, wait_s: float = 2.5) -> List[dict]:
    """The network cameras' video streams: [{kind: ip, id: uri, name, spectrum, pipeline, ...}]."""
    user = str(env.get("NAVERA_IP_CAMERA_USER", "") or "").strip()
    pw = str(env.get("NAVERA_IP_CAMERA_PASSWORD", "") or "")
    ifaces = wired_interfaces(wifi=str(env.get("NAVERA_DISCOVER_IP_CAMERAS", "") or "").strip().lower() == "wifi")
    out, notes = [], []
    for dev in ws_discovery(ifaces, wait_s):
        d = onvif_streams(dev, user, pw)
        label = " ".join(x for x in (d["maker"], d["model"] or d["name"]) if x) or d["url"]
        if d.get("auth"):
            notes.append(f"CHECK network camera {label} ({d['url']}): "
                         + ("password refused — check NAVERA_IP_CAMERA_USER / _PASSWORD" if d["auth"] == "refused"
                            else "it needs its login: set NAVERA_IP_CAMERA_USER and NAVERA_IP_CAMERA_PASSWORD"))
            continue
        spectrum0, hfov, model = lens_info(f"{d['maker']} {d['model']} {d['name']}")
        # a bi-spectrum camera (one visible and one thermal sensor): main streams only (the first
        # profile of each video source), the thermal one told by its name or its small size
        seen = set()
        for s in d["streams"]:
            if s["source"] in seen:
                continue
            seen.add(s["source"])
            desc = rtsp_describe(s["uri"], user, pw) or {}
            name = f"{label} {s['name']}".strip()
            spectrum = ("thermal" if re.search(THERMAL_WORDS, f"{s['name']} {s['source']}", re.I)
                        else spectrum0 if spectrum0 == "rgb" or len(d["streams"]) == 1 else None)
            out.append(dict(kind="ip", id=s["uri"], name=name, spectrum=spectrum, hfov_deg=hfov, lens_model=model,
                            size=[s["width"], s["height"]], codec=desc.get("codec", "?"),
                            pipeline=gst_rtsp_pipeline(s["uri"], desc.get("codec", "H264"), bool(user)),
                            auth=bool(user), bispectrum=len({x["source"] for x in d["streams"]}) > 1))
    nets = [ipaddress.ip_network(f"{a}/{p}", strict=False) for f in ifaces for a, p in f["ipv4"]]
    for subnet, uri, label in FIXED_RTSP:
        if not any(n.overlaps(ipaddress.ip_network(subnet)) for n in nets) or any(c["id"] == uri for c in out):
            continue
        desc = rtsp_describe(uri, timeout=2.0)
        if desc and desc["status"] == 200:
            spectrum, hfov, model = lens_info(label)
            out.append(dict(kind="ip", id=uri, name=label, spectrum=spectrum, hfov_deg=hfov, lens_model=model,
                            size=[0, 0], codec=desc["codec"], auth=False,
                            pipeline=gst_rtsp_pipeline(uri, desc["codec"], False)))
    if str(env.get("NAVERA_DISCOVER_RTSP_SCAN", "1") or "1").strip().lower() not in ("0", "off", "false", "no"):
        scanned, more = rtsp_scan(ifaces, user, pw, skip_hosts={stream_host(c["id"]) for c in out})
        out += scanned
        notes += more
    out += gopro_cameras()
    gen, more = genicam_cameras(ifaces)
    out += gen
    notes += more
    for c in out:
        c["notes"] = notes
    return out if out else ([dict(kind="note", notes=notes)] if notes else [])


# ── cameras with their own way of talking ──────────────────────────────────
# RTSP paths asked of a host that has an RTSP port open and did not answer ONVIF (a gimbal camera
# with its own firmware: Viewpro, Topotek, Gremsy, A8-type modules...), the most common first.
# DESCRIBE only: nothing is changed on the camera.
RTSP_PATHS = ("", "/main.264", "/video1", "/stream=0", "/stream=1", "/live", "/stream0", "/stream1", "/ch0",
              "/0", "/live/0", "/h264", "/main", "/live/ch00_0", "/11", "/Streaming/Channels/101",
              "/cam/realmonitor?channel=1&subtype=0", "/fpv_stream")
RTSP_PORTS = (554, 8554)


def stream_host(uri: str) -> str:
    m = re.match(r"\w+://(?:[^@/]*@)?(\[[^\]]+\]|[^:/]+)", str(uri))
    return m.group(1).strip("[]") if m else ""


def _port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def rtsp_scan(ifaces: List[dict], user: str = "", password: str = "", skip_hosts=(),
              timeout: float = 0.4, ports=RTSP_PORTS) -> Tuple[List[dict], List[str]]:
    """([cameras], [notes]) of the RTSP cameras that do not answer ONVIF: every host of the box's
    wired subnets (the /24 around each address at most) with an RTSP port open is asked for the
    usual stream paths. ~3 s for a /24."""
    from concurrent.futures import ThreadPoolExecutor
    own, hosts = set(), []
    for f in ifaces:
        for a, p in f["ipv4"]:
            own.add(a)
            hosts += [str(h) for h in ipaddress.ip_network(f"{a}/{max(int(p), 24)}", strict=False).hosts()]
    # a camera whose static IPv4 is in another subnet (a factory 192.168.1.64 on a box at
    # 192.168.77.10) still answers on its IPv6 link-local address: the wired neighbours
    hosts += ipv6_neighbours(ifaces)
    targets = [(h, port) for h in dict.fromkeys(hosts) if h not in own and h not in set(skip_hosts)
               for port in ports]
    if not targets:
        return [], []
    with ThreadPoolExecutor(64) as ex:
        live = [t for t, ok in zip(targets, ex.map(lambda t: _port_open(t[0], t[1], timeout), targets)) if ok]

    def ask(t):
        for path in RTSP_PATHS:
            uri = f"{_rtsp_base(t[0], t[1])}{path}"
            d = rtsp_describe(uri, user, password, timeout=2.0)
            if d is None:
                return None
            if d["status"] in (200, 401):
                return uri, d
        return None
    with ThreadPoolExecutor(16) as ex:
        answers = [a for a in ex.map(ask, live) if a]
    macs = neighbour_macs()
    answers.sort(key=lambda x: ":" in stream_host(x[0]))  # IPv4 first: one camera answers on both
    out, notes, seen = [], [], set()
    for uri, d in answers:
        host = stream_host(uri)
        key = macs.get(host.split("%")[0]) or eui64_mac(host) or host
        if key in seen:
            continue
        seen.add(key)
        if d["status"] == 401:
            notes.append(f"CHECK network camera at {host} (RTSP): "
                         + ("password refused — check NAVERA_IP_CAMERA_USER / _PASSWORD" if user else
                            "it needs its login: set NAVERA_IP_CAMERA_USER and NAVERA_IP_CAMERA_PASSWORD"))
            continue
        streams = _channels(re.match(r"rtsp://(\[[^\]]+\]|[^/]+)", uri).group(0), uri, d, user, password)
        for i, (u, dd) in enumerate(streams):
            codec = dd["codec"] if dd["codec"] != "?" else "H264"
            out.append(dict(kind="ip", id=u, name=f"RTSP camera {host}" + (f" channel {i + 1}" if i else ""),
                            spectrum=None, hfov_deg=None, lens_model="pinhole", size=dd.get("size") or [0, 0],
                            codec=dd["codec"],
                            auth=bool(user), scanned=True, bispectrum=len(streams) > 1,
                            pipeline=gst_rtsp_pipeline(u, codec, bool(user))))
    return out, notes


# the numbered channels of a camera with several video sources (a bi-spectrum camera: Hikvision
# visible 101 / thermal 201), asked even when the bare address already answers (its default stream)
CHANNEL_FAMILIES = (("/Streaming/Channels/101", "/Streaming/Channels/201", "/Streaming/Channels/301"),
                    ("/stream=0", "/stream=1"), ("/video1", "/video2"))


def _channels(base: str, uri: str, d: dict, user: str, password: str) -> List[Tuple[str, dict]]:
    """[(uri, describe)] of the camera's video channels; [(uri, d)] when it has no numbered ones.
    A channel counts only if its stream differs (encoder parameters, size) from the ones before:
    a camera answering any path with its default stream gives one channel, not three."""
    for fam in CHANNEL_FAMILIES:
        got, prints = [], set()
        for path in fam:
            dd = rtsp_describe(base + path, user, password, timeout=2.0)
            if not dd or dd["status"] != 200:
                break
            if dd.get("fingerprint") and dd["fingerprint"] in prints:
                continue
            prints.add(dd.get("fingerprint"))
            got.append((base + path, dd))
        if got:
            return got
    return [(uri, d)]


def neighbour_macs() -> Dict[str, str]:
    """{address: MAC} of the box's IPv4 and IPv6 neighbours (one camera, two addresses)."""
    try:
        txt = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return {a: m.lower() for a, m in re.findall(r"^(\S+) .*?lladdr ([0-9a-fA-F:]{17})", txt, re.M)}


def eui64_mac(host: str) -> str:
    """The MAC inside an IPv6 link-local address made from it (…:a614:37ff:fe84:d176 → a4:14:37:84:d1:76)."""
    try:
        b = ipaddress.IPv6Address(host.split("%")[0]).packed[8:]
    except ValueError:
        return ""
    if b[3:5] != b"\xff\xfe":
        return ""
    return ":".join(f"{x:02x}" for x in (b[0] ^ 0x02, b[1], b[2], b[5], b[6], b[7]))


def _rtsp_base(host: str, port: int) -> str:
    return f"rtsp://[{host}]:{port}" if ":" in host else f"rtsp://{host}:{port}"


def ipv6_neighbours(ifaces: List[dict], wait_s: float = 1.0) -> List[str]:
    """The IPv6 link-local addresses answering on each wired interface ("fe80::...%iface"): an
    all-nodes ping fills the neighbour table, which is then read."""
    out = []
    for f in ifaces:
        name = f.get("name")
        if not name:
            continue
        try:
            subprocess.run(["ping", "-6", "-c", "2", "-i", "0.3", "-W", str(wait_s), f"ff02::1%{name}"],
                           capture_output=True, timeout=wait_s + 3)
            txt = subprocess.run(["ip", "-6", "neigh", "show", "dev", name], capture_output=True, text=True,
                                 timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        out += [f"{a}%{name}" for a, state in re.findall(r"^(fe80:\S+)\s.*?(\S+)\s*$", txt, re.M)
                if state.upper() not in ("FAILED", "INCOMPLETE")]
    return list(dict.fromkeys(out))


# MAVLink camera protocol (a camera, or the autopilot for a gimbal it drives, announces its stream)
MAV_TYPE_CAMERA = 30
MAV_CMD_REQUEST_MESSAGE = 512
VIDEO_STREAM_INFORMATION = 269
VIDEO_STREAM_FLAGS_THERMAL = 2


def mavlink_stream_camera(s: dict, user: str = "", password: str = "") -> Optional[dict]:
    """A camera description from one VIDEO_STREAM_INFORMATION (its fields as a dict), None if the
    stream cannot be read (an unknown type, no address)."""
    uri = str(s.get("uri") or "").replace("\x00", "").strip()
    typ, codec = int(s.get("type", 0) or 0), {2: "H265"}.get(int(s.get("encoding", 0) or 0), "H264")
    m = re.search(r":(\d+)(?:/|$)", uri) or re.fullmatch(r"(\d+)", uri)
    if typ == 0 and uri.startswith("rtsp://"):
        d = rtsp_describe(uri, user, password, timeout=2.0) or {}
        if d.get("codec") in ("H264", "H265", "JPEG"):
            codec = d["codec"]
        auth = bool(user) or d.get("status") == 401        # rtspsrc sends the login only if asked
        pipeline = gst_rtsp_pipeline(uri, codec, auth)
    elif typ in (1, 3) and m:
        auth, pipeline = False, udp_pipeline(int(m.group(1)), codec, ts=typ == 3)
    elif typ == 2 and m and stream_host(uri):
        auth, pipeline = False, tcp_ts_pipeline(stream_host(uri), int(m.group(1)), codec)
    else:
        return None
    name = str(s.get("name") or "").replace("\x00", "").strip() or f"stream {s.get('stream_id', 1)}"
    thermal = bool(int(s.get("flags", 0) or 0) & VIDEO_STREAM_FLAGS_THERMAL) or bool(re.search(THERMAL_WORDS, name, re.I))
    hfov = float(s.get("hfov", 0) or 0)
    w, h = int(s.get("resolution_h", 0) or 0), int(s.get("resolution_v", 0) or 0)
    _, db_hfov, model = lens_info(name)
    return dict(kind="ip", id=uri, name=f"MAVLink camera {name}".strip(), spectrum="thermal" if thermal else None,
                hfov_deg=hfov if 5 <= hfov <= 170 else db_hfov, lens_source="camera" if 5 <= hfov <= 170 else None,
                lens_model=model, size=[w, h] if w and h else [0, 0], codec=codec, auth=auth, pipeline=pipeline,
                mavlink=True)


def mavlink_cameras(url: str, env=None, wait_s: float = 4.0) -> List[dict]:
    """The video streams announced over MAVLink (camera protocol v2): VIDEO_STREAM_INFORMATION asked
    of the autopilot (ArduPilot / PX4 answer for a gimbal camera they drive) and of every camera
    component heard (HEARTBEAT type CAMERA)."""
    env = os.environ if env is None else env
    try:
        from navera_output.mavlink_url import connect
        from pymavlink.dialects.v20 import ardupilotmega as v2
        m = connect(url, 1, 191)
        # VIDEO_STREAM_INFORMATION (id 269) exists only in MAVLink 2: this link's parser speaks it
        # (the box's other links keep pymavlink's default)
        m.mav = v2.MAVLink(m, srcSystem=1, srcComponent=191)
        m.mav.robust_parsing = m.robust_parsing
        m.WIRE_PROTOCOL_VERSION = v2.WIRE_PROTOCOL_VERSION
    except Exception:                                     # noqa: BLE001
        return []
    streams = {}
    try:
        if m.wait_heartbeat(timeout=3) is None:
            return []
        asked = {}

        def ask(sysid, comp):
            asked[(sysid, comp)] = True
            m.mav.command_long_send(sysid, comp, MAV_CMD_REQUEST_MESSAGE, 0, VIDEO_STREAM_INFORMATION,
                                    0, 0, 0, 0, 0, 0)
        ask(m.target_system, m.target_component)
        end, again = time.time() + wait_s, time.time() + wait_s / 2
        while time.time() < end:
            if again and time.time() > again:             # a request lost on a radio / UDP link
                again = None
                for k in list(asked):
                    ask(*k)
            msg = m.recv_match(blocking=True, timeout=0.3)
            if msg is None:
                continue
            t = msg.get_type()
            src = (msg.get_srcSystem(), msg.get_srcComponent())
            if t == "HEARTBEAT" and msg.type == MAV_TYPE_CAMERA and src not in asked:
                ask(*src)
            elif t == "VIDEO_STREAM_INFORMATION":
                d = msg.to_dict()
                streams[(src, d.get("stream_id"))] = d
    except Exception:                                     # noqa: BLE001 — a broken link: what was heard
        pass
    finally:
        try:
            m.close()
        except Exception:                                 # noqa: BLE001
            pass
    user = str(env.get("NAVERA_IP_CAMERA_USER", "") or "").strip()
    pw = str(env.get("NAVERA_IP_CAMERA_PASSWORD", "") or "")
    out = [mavlink_stream_camera(d, user, pw) for _, d in sorted(streams.items(), key=lambda x: str(x[0]))]
    return [c for c in out if c]


# GoPro HERO9 and later on USB: a network interface (USB NCM), the camera at 172.2X.1YZ.51 (the last
# digits of its serial), HTTP on port 8080; webcam mode sends MPEG-TS over UDP to the box, port 8554
# (Open GoPro). Linear lens mode: the least distortion.
GOPRO_ADDR = re.compile(r"172\.2\d\.1\d\d\.\d+$")


def http_get(url: str, timeout: float = 2.0) -> Optional[int]:
    """The HTTP status of a GET, None: no answer."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (OSError, ValueError):
        return None


def gopro_start_urls(ip: str) -> str:
    base = f"http://{ip}:8080/gopro"
    return f"{base}/camera/control/wired_usb?p=1 {base}/webcam/start?res=12&fov=4"


def gopro_cameras(addresses=None) -> List[dict]:
    """The GoPros on USB (addresses: [(interface address, prefix)], default every interface's)."""
    if addresses is None:
        addresses = [a for n in sorted(os.listdir("/sys/class/net")) for a in ipv4_of(n)]
    out = []
    for a, _ in addresses:
        if not GOPRO_ADDR.match(a):
            continue
        ip = a.rsplit(".", 1)[0] + ".51"
        if ip == a or http_get(f"http://{ip}:8080/gopro/webcam/status") is None:
            continue
        out.append(dict(kind="ip", id=f"gopro://{ip}", name=f"GoPro (USB, {ip})", spectrum="rgb", hfov_deg=None,
                        lens_model="pinhole", size=[1920, 1080], codec="H264", auth=False,
                        start_url=gopro_start_urls(ip), pipeline=udp_pipeline(8554, "H264", ts=True)))
    return out


# GigE Vision / USB3 Vision (GenICam) industrial cameras — Basler, Teledyne FLIR, Allied Vision,
# Hikrobot, Daheng, Lucid, radiometric FLIR A-series... — through Aravis (open source, no maker SDK)
GVCP_PORT = 3956
ARAVIS_INSTALL = "sudo apt install gir1.2-aravis-0.8 aravis-tools"


def load_aravis():
    """The Aravis module (gi), or None when it is not installed."""
    try:
        import gi
        gi.require_version("Aravis", "0.8")
        from gi.repository import Aravis
        return Aravis
    except (ImportError, ValueError, AttributeError):
        return None


def gvcp_discovery(ifaces: List[dict], wait_s: float = 1.0) -> List[dict]:
    """[{ip, maker, model}] of the GigE Vision cameras answering a GVCP discovery broadcast."""
    out = {}
    for f in ifaces:
        for a, _ in f["ipv4"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.bind((a, 0))
                s.sendto(struct.pack(">BBHHH", 0x42, 0x11, 0x0002, 0, 1), ("255.255.255.255", GVCP_PORT))
            except OSError:
                continue
            end = time.monotonic() + wait_s
            while time.monotonic() < end:
                s.settimeout(max(0.05, end - time.monotonic()))
                try:
                    data, peer = s.recvfrom(1024)
                except OSError:
                    break
                d = gvcp_ack(data, peer[0])
                if d:
                    out[peer[0]] = d
            s.close()
    return list(out.values())


def gvcp_ack(data: bytes, peer: str) -> Optional[dict]:
    """{ip, maker, model} of a GVCP discovery answer (the bootstrap registers after an 8-byte header)."""
    if len(data) < 8 + 136 or struct.unpack(">H", data[2:4])[0] != 0x0003:
        return None
    p = data[8:]
    return dict(ip=socket.inet_ntoa(p[36:40]) if any(p[36:40]) else peer, maker=_cstr(p[72:104]),
                model=_cstr(p[104:136]))


def usb3vision_devices(sysfs: str = "/sys/bus/usb/devices") -> List[str]:
    """Names of the USB3 Vision cameras plugged in (interface class EF, subclass 05)."""
    out = []
    for d in sorted(glob.glob(os.path.join(sysfs, "*:*"))):
        try:
            cls = open(os.path.join(d, "bInterfaceClass")).read().strip().lower()
            sub = open(os.path.join(d, "bInterfaceSubClass")).read().strip().lower()
        except OSError:
            continue
        if (cls, sub) == ("ef", "05"):
            dev = d.rsplit(":", 1)[0]                     # 2-1:1.0 -> the device 2-1
            name = " ".join(_read(os.path.join(dev, f)) for f in ("manufacturer", "product")).strip()
            out.append(name or os.path.basename(dev))
    return sorted(set(out))


def _read(path: str) -> str:
    try:
        return open(path).read().strip()
    except OSError:
        return ""


def genicam_cameras(ifaces: List[dict], aravis=None) -> Tuple[List[dict], List[str]]:
    """([cameras], [notes]) of the GigE Vision / USB3 Vision cameras: listed by Aravis when it is
    installed, else only seen (GVCP broadcast, USB class) and reported with the command that adds it."""
    ar = aravis if aravis is not None else load_aravis()
    if ar is None:
        seen = [f"{d['maker']} {d['model']} ({d['ip']}, GigE Vision)".strip() for d in gvcp_discovery(ifaces)]
        seen += [f"{n} (USB3 Vision)" for n in usb3vision_devices()]
        return [], [f"CHECK industrial camera {n} found: it needs Aravis (open source, no maker software) — "
                    f"{ARAVIS_INSTALL}, then restart navera-discover" for n in seen]
    out = []
    try:
        ar.update_device_list()
        for i in range(ar.get_n_devices()):
            proto = str(ar.get_device_protocol(i) or "")
            if proto.lower() == "fake":
                continue
            name = " ".join(str(x or "") for x in (ar.get_device_vendor(i), ar.get_device_model(i))).strip()
            spectrum, hfov, model = lens_info(name)
            out.append(dict(kind="aravis", id=str(ar.get_device_id(i)), name=name or str(ar.get_device_id(i)),
                            protocol=proto, spectrum=spectrum, hfov_deg=hfov, lens_model=model, size=[0, 0]))
    except Exception:                                     # noqa: BLE001 — Aravis present but broken
        return [], []
    return out, []


# ── what a picture says ────────────────────────────────────────────────────
def picture_traits(img) -> dict:
    """{mono, brightness, texture, blue, sky_score, dark} of one frame (BGR or grey, 8 or 16 bit).

    sky_score > 0: looks like a day sky (bright, smooth, blue or white), < 0 like ground (texture,
    not blue); about 0: cannot tell (night, a dark room, a wall). Used to COMPARE cameras: the more
    sky-like of two is the one looking up.
    """
    import cv2
    import numpy as np
    a = np.asarray(img)
    if a.dtype != np.uint8:                               # 16-bit radiometric: stretch to 8 bit
        lo, hi = np.percentile(a, (1, 99))
        a = np.clip((a.astype(np.float32) - lo) * (255.0 / max(hi - lo, 1.0)), 0, 255).astype(np.uint8)
    small = cv2.resize(a, (160, 120), interpolation=cv2.INTER_AREA)
    if small.ndim == 2 or small.shape[2] == 1:
        grey, mono, blue = small.reshape(120, 160), True, 0.0
    else:
        b, g, r = (small[..., i].astype(np.float32) for i in range(3))
        # 90th percentile: a thermal camera's own overlays (a coloured measurement box, text) are a few
        # percent of the pixels; a colour camera's picture is coloured nearly everywhere
        mono = float(np.percentile(np.abs(b - g) + np.abs(g - r), 90)) < 6.0
        grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        blue = float(np.mean(b - r) / 255.0)
    gf = grey.astype(np.float32)
    texture = float(np.mean(np.hypot(cv2.Sobel(gf, cv2.CV_32F, 1, 0), cv2.Sobel(gf, cv2.CV_32F, 0, 1))) / 255.0)
    bright = float(np.mean(gf) / 255.0)
    dark = bright < 0.12
    score = 0.0 if dark else (2.0 * (bright - 0.5) + 6.0 * max(blue, 0.0) - 4.0 * min(texture, 0.5) + 0.4)
    return dict(mono=mono, brightness=round(bright, 3), texture=round(texture, 4), blue=round(blue, 3),
                sky_score=round(score, 3), dark=dark)


SAMPLE_CODE = r"""
import sys, cv2, numpy as np
src, kind, fourcc, w, h = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
if kind == "usb":
    cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
    if fourcc.strip() and fourcc not in ("Y16 ", "GREY", "Y8  "):
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    else:
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
    if w and h:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    frame = None
    for _ in range(8):          # auto-exposure settles over the first frames
        ok, f = cap.read()
        if ok:
            frame = f
else:
    sys.path.insert(0, sys.argv[6])
    if kind == "aravis":
        from camera_pkg.aravis_capture import AravisCapture
        cap = AravisCapture(src)
    else:
        from camera_pkg.gst_capture import GstCapture, expand_secrets, start_camera
        start_camera(sys.argv[7] if len(sys.argv) > 7 else "")
        cap = GstCapture(expand_secrets(src), timeout_s=5.0)
    frame = None
    for _ in range(4):
        ok, f = cap.read()
        if ok:
            frame = f
cap.release()
if frame is None:
    sys.exit(3)
import io
buf = io.BytesIO()                  # np.save needs a seekable file: a pipe is not one
np.save(buf, frame)
sys.stdout.buffer.write(buf.getvalue())
"""


def sample_frame(cam: dict, timeout_s: float = 12.0):
    """One frame of the camera (numpy array) read in a child process, or None. Never a device
    another process holds; never the Insta360 kit."""
    import io
    import numpy as np
    if cam["kind"] == "usb":
        if held_by(cam["id"]):
            return None
        args = [cam["id"], "usb", cam.get("fourcc") or "", str(cam["size"][0]), str(cam["size"][1]), ""]
    elif cam["kind"] in ("ip", "aravis"):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pkg = next((p for p in sys.path if os.path.isdir(os.path.join(p, "camera_pkg"))), here)
        args = ([cam["pipeline"], "gst", "", "0", "0", pkg, cam.get("start_url", "")] if cam["kind"] == "ip"
                else [cam["id"], "aravis", "", "0", "0", pkg])
    else:
        return None
    try:
        r = subprocess.run([sys.executable, "-c", SAMPLE_CODE] + args, capture_output=True, timeout=timeout_s)
        if r.returncode != 0 or not r.stdout:
            return None
        return np.load(io.BytesIO(r.stdout), allow_pickle=False)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def describe(cams: List[dict], sample: bool = True) -> List[dict]:
    """Add the picture's traits (sample=True: one frame each) and settle the spectrum."""
    for c in cams:
        if c["kind"] not in ("usb", "ip", "aravis"):
            continue
        img = sample_frame(c) if sample else None
        if img is None:
            c["traits"] = None
            continue
        t = picture_traits(img)
        c["traits"] = t
        if not c.get("size") or not c["size"][0]:
            c["size"] = [int(img.shape[1]), int(img.shape[0])]
        if c.get("spectrum") is None:
            # one channel and nothing else saying colour: thermal, to be confirmed (a monochrome
            # visible camera exists, rarely on a drone)
            c["spectrum"], c["spectrum_guess"] = ("thermal" if t["mono"] else "rgb"), True
    # a two-sensor camera (visible + thermal channels of one address): its grey channel beside a
    # colour one is the thermal sensor, not a guess
    for c in cams:
        if c.get("bispectrum") and c.get("spectrum_guess") and c["spectrum"] == "thermal":
            host = stream_host(c["id"])
            if any(o is not c and o.get("bispectrum") and stream_host(o["id"]) == host and
                   (o.get("traits") or {}).get("mono") is False for o in cams):
                c["spectrum_guess"] = False
    return cams


# ── who does what ──────────────────────────────────────────────────────────
def _looks(c: dict) -> Optional[str]:
    """'sky' / 'ground' from the camera's own name (a ROS topic, a stream name), else None."""
    n = f"{c.get('id', '')} {c.get('name', '')}".lower()
    if re.search(SKY_WORDS, n):
        return "sky"
    if re.search(GROUND_WORDS, n):
        return "ground"
    return None


def assign_roles(cams: List[dict], env, day_taken: bool = False) -> dict:
    """{"roles": {role: camera}, "report": [lines]} for the cameras found (pure: tests feed it lists).

    Rules: a camera named in navera.env (NAVERA_<ROLE>DEVICE / _TOPIC / _GST_PIPELINE) keeps its role
    and is no candidate for another; thermal cameras -> thermal (looking down: STHN matches thermal
    pictures with the map); colour cameras -> day, and with two the one whose picture is clearly more
    sky-like (or whose name says sky / up) -> star. Two colour cameras that look alike: the first is
    day, the other is left out with CHECK (a wrong sky camera would only waste the celestial
    pipeline; a wrong day camera would mislead vision). day_taken: the day camera is another one
    (the Insta360 kit): a colour camera is then the star camera only if it clearly looks up.
    """
    get = lambda k: str(env.get(k, "") or "").strip()           # noqa: E731
    roles, rep = {}, []
    imposed = {}
    for role, pre in ROLES.items():
        for k in ("DEVICE", "TOPIC", "GST_PIPELINE"):
            if get(pre + k):
                imposed[role] = get(pre + k)
    if day_taken:
        imposed.setdefault("day", "the Insta360 kit")
    taken = {os.path.realpath(v) if v.startswith("/dev/") else v for v in imposed.values()}
    free = [c for c in cams if c.get("kind") in ("usb", "csi", "ip", "aravis", "ros")
            and (os.path.realpath(c["id"]) if str(c["id"]).startswith("/dev/") else c["id"]) not in taken]
    thermal = [c for c in free if c.get("spectrum") == "thermal" and _looks(c) != "sky"]
    colour = [c for c in free if c not in thermal]
    if "thermal" not in imposed and thermal:
        roles["thermal"] = thermal[0]
        if len(thermal) > 1:
            rep.append("CHECK several thermal cameras (" + ", ".join(c["name"] for c in thermal)
                       + f"): using {thermal[0]['name']} — set NAVERA_THERMAL_CAMERA_DEVICE to choose")
    sky = [c for c in colour if _looks(c) == "sky"]
    ground = [c for c in colour if _looks(c) == "ground"]
    if not sky and "day" in imposed and colour:
        best = max(colour, key=lambda c: (c.get("traits") or {}).get("sky_score") or -9.0)
        if ((best.get("traits") or {}).get("sky_score") or -9.0) > 0.3:
            sky = [best]
        else:
            rep.append("CHECK colour camera(s) " + ", ".join(c["name"] for c in colour) + " not used: the day "
                       "camera is " + imposed["day"] + " and the picture does not show sky — point it up "
                       "(daylight) and restart navera-discover, or set NAVERA_STAR_CAMERA_DEVICE")
    elif not sky and len(colour) >= 2:
        sc = [((c.get("traits") or {}).get("sky_score"), c) for c in colour]
        known = sorted([x for x in sc if x[0] is not None], key=lambda x: -x[0])
        if len(known) >= 2 and known[0][0] - known[1][0] >= 0.5 and known[0][0] > 0.2:
            sky = [known[0][1]]
        else:
            rep.append("CHECK two colour cameras and their pictures do not say which looks up ("
                       + ", ".join(c["name"] for c in colour) + "): the less sky-like is the day camera, none is the "
                       "star camera — point one at the sky (daylight) and restart navera-discover, or set "
                       "NAVERA_STAR_CAMERA_DEVICE")
    if "star" not in imposed and sky and get("NAVERA_STAR_CAMERA_INPUT").lower() in ("", "auto"):
        roles["star"] = sky[0]
    if "day" not in imposed:
        left = [c for c in (ground + colour) if c is not roles.get("star")]
        if left:
            pick = sorted(left, key=lambda c: (c["kind"] == "ros", c["kind"] == "ip", c.get("traits") is None,
                                               (c.get("traits") or {}).get("sky_score") or 0.0))[0]
            roles["day"] = pick
            others = [c for c in left if c is not pick and c is not roles.get("thermal")]
            if others and len(colour) > 2:
                rep.append("CHECK more colour cameras than jobs: " + ", ".join(c["name"] for c in others)
                           + " not used")
    for role in ROLES:
        c = roles.get(role)
        if c:
            why = []
            if c.get("spectrum_guess"):
                why.append("single-channel picture" if c["spectrum"] == "thermal" else "colour picture")
            t = c.get("traits")
            if role == "star":
                why.append("its name says sky" if _looks(c) == "sky" else
                           f"its picture looks like sky (score {t['sky_score']:+.2f})" if t else "")
            why = ", ".join(w for w in why if w)
            line = f"{role} camera: {c['name']} ({c['kind']}){' — ' + why if why else ''}"
            if c.get("spectrum_guess") and c["spectrum"] == "thermal":
                line = "CHECK " + line + " — thermal guessed from a grey picture: if it is a colour camera set " \
                       "NAVERA_CAMERA_DEVICE"
            rep.append(line)
        elif role in imposed:
            rep.append(f"{role} camera: {imposed[role]} (written in navera.env)")
    return {"roles": roles, "report": rep}


def role_settings(role: str, cam: dict, env) -> Dict[str, str]:
    """The NAVERA_<ROLE>_* settings for one camera (only those not written in navera.env)."""
    pre = ROLES[role]
    get = lambda k: str(env.get(k, "") or "").strip()           # noqa: E731
    out = {}
    if cam["kind"] == "usb":
        out.update({pre + "INPUT": "usb", pre + "DEVICE": cam["id"]})
        if cam.get("fourcc"):
            out[pre + "FOURCC"] = cam["fourcc"].strip()
    elif cam["kind"] == "csi":
        out.update({pre + "INPUT": "csi", pre + "DEVICE": cam.get("sensor", "0")})
    elif cam["kind"] == "ip":
        out.update({pre + "INPUT": "gst", pre + "GST_PIPELINE": cam["pipeline"]})
        if cam.get("start_url"):
            out[pre + "START_URL"] = cam["start_url"]
    elif cam["kind"] == "aravis":
        out.update({pre + "INPUT": "aravis", pre + "DEVICE": cam["id"]})
    elif cam["kind"] == "ros":
        out.update({pre + "INPUT": "ros", pre + "TOPIC": cam["id"]})
    size = cam.get("size") or [0, 0]
    if size[0] and size[1]:
        out[pre + "SIZE"] = f"{int(size[0])}x{int(size[1])}"
    elif cam["kind"] in ("ip", "aravis", "ros"):
        out[pre + "SIZE"] = "auto"                        # the stream's own size, read at start
    if not get(pre + "CALIBRATION") and not get(pre + "HFOV_DEG"):
        out[pre + "HFOV_DEG"] = f"{cam.get('hfov_deg') or GUESS_HFOV_DEG:g}"
        out[pre + "LENS_SOURCE"] = cam.get("lens_source") or ("database" if cam.get("hfov_deg") else "guess")
    out[pre + "SPECTRUM"] = cam.get("spectrum") or "rgb"
    out[pre + "NAME"] = re.sub(r"[^\w .:/+()-]", "", str(cam.get("name", "")))[:80]
    return {k: v for k, v in out.items() if not get(k) or get(k).lower() == "auto"}


def main(argv=None) -> int:
    """navera_tools: python3 -m navera_common.cameras — list the cameras and the jobs they would get."""
    import argparse
    ap = argparse.ArgumentParser(description="List the cameras plugged into this box and their jobs.")
    ap.add_argument("--no-sample", action="store_true", help="do not read a frame from each camera")
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--mavlink", default="", help="also ask this autopilot link for its cameras' streams "
                                                  "(e.g. udpin:0.0.0.0:14550, /dev/ttyTHS1:921600)")
    a = ap.parse_args(argv)
    cams = usb_cameras() + csi_cameras() + ([] if a.no_network else network_cameras(os.environ))
    cams += mavlink_cameras(a.mavlink) if a.mavlink else []
    for n in sorted({n for c in cams for n in c.get("notes") or []}):
        print(n)
    cams = describe([c for c in cams if c["kind"] != "note"], sample=not a.no_sample)
    for c in cams:
        print(json.dumps({k: v for k, v in c.items() if k not in ("formats", "notes")}, default=str))
    r = assign_roles(cams, os.environ)
    print("\n".join(r["report"]) or "no camera")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
