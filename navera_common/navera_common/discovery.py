"""What is connected to this NAVERA box, and which source to use for what.

At every boot (navera-discover.service, before the other units) NAVERA looks for:
  * its own sensors: IMU (BNO085, I2C 0x4A/0x4B) and clock (DS3231, I2C 0x68) on I2C
    buses 1 and 7;
  * GPS receivers, in every common form: checksummed NMEA or u-blox UBX (NAV-PVT) on the
    serial ports — the box's receiver, a USB GPS, or a passive tap (Y-cable) on the TX wire
    of the GPS an autopilot uses —, DroneCAN GNSS nodes (Fix2: Here3/Here4, Holybro...) on
    the CAN interfaces that are up, NMEA / UBX over the network (NAVERA_DISCOVER_GPS_URLS);
  * an autopilot: MAVLink heartbeats on the serial ports and the network (UDP 14550/14551,
    TCP 127.0.0.1:5760, NAVERA_DISCOVER_MAVLINK); it is asked which data it streams
    (attitude, rangefinder, its GPS receivers) and its GPS types;
  * a ROS vehicle: IMU / GPS / camera / height topics on the ROS domains;
  * cameras: USB (/dev/v4l/by-id), CSI (Jetson video inputs), and an Insta360 One R in USB
    "Android" mode (USB id 2e1a:0002: the Insta360 kit, camera AND IMU, navera-insta360).
then decides, for each need, the best source found (decide()): attitude box IMU >
autopilot > ROS > Insta360 kit; GPS serial receiver (UBX or NMEA) > DroneCAN GNSS > network GPS >
autopilot's second GPS > autopilot's first GPS (only when NAVERA does not feed it) > ROS;
camera Insta360 kit > USB > CSI > ROS; outputs: MAVLink to the autopilot when one answers (through
vehicle_link's relay when it is the same link), /navera/fix on ROS when a ROS vehicle is
there. A GPS NAVERA itself feeds (GPS type 14 = MAVLink, or NMEA when NAVERA's NMEA output
is set) is never a source: NAVERA would check its output against itself.

Only settings left to "auto" (or unset) are decided: a value written in navera.env always
wins. The result is an env file read by the services after navera.env, and a JSON report.
Probing only READS: serial ports, CAN buses (a passive DroneCAN listener: no node id, no
frame sent) and network GPS streams are never written to, except an identified autopilot,
which is asked for its data streams; a port another process holds open is never touched.
After boot, navera_common.hotplug looks again when a device appears (hot-plug).
"""
import glob
import os
import re
import threading
import time
from typing import Dict, List, Optional

I2C_SLAVE = 0x0703
IMU_ADDRS, RTC_ADDR = (0x4A, 0x4B), 0x68
SERIAL_GLOBS = ("/dev/ttyTHS*", "/dev/ttyUSB*", "/dev/ttyACM*")
# common bauds first; 230400: a u-blox an autopilot configured (ArduPilot), seen through a tap
SERIAL_BAUDS = (9600, 38400, 57600, 115200, 230400, 460800, 921600, 4800, 19200)
NMEA_RE = re.compile(rb"\$([A-Z]{2}[A-Z]{3}),[^*\r\n]*\*([0-9A-F]{2})")
NAVERA_NS = ("/navera", "/day", "/night", "/thermal", "/celestial", "/cn", "/rosout", "/parameter_events")
AUTO_KEYS = ("NAVERA_SENSOR_SOURCE", "NAVERA_GPS_SOURCE", "NAVERA_CAMERA_INPUT")
MAVLINK_NET_DEFAULT = ("udpin:0.0.0.0:14550", "udpin:0.0.0.0:14551", "tcp:127.0.0.1:5760")
# NMEA-0183 over IP (IEC 61162-450 / de-facto 10110), serial-to-Ethernet converters (2000, 4001)
GPS_NET_PORTS = (10110, 2000, 4001)
GPS_TYPE_MAV, GPS_TYPE_NMEA = 14, 5           # ArduPilot GPS_TYPE values NAVERA may itself feed


# ── probes (each returns plain data; never raises) ─────────────────────────
def probe_i2c(buses=(1, 7)) -> Dict[str, dict]:
    """{"imu": {"bus", "address"}, "rtc": {...}} for the chips that answer (or are held by a
    kernel driver, which proves they are there).
    """
    import errno
    import fcntl
    found = {}
    for bus in buses:
        path = f"/dev/i2c-{bus}"
        if not os.path.exists(path):
            continue
        for name, addrs in (("imu", IMU_ADDRS), ("rtc", (RTC_ADDR,))):
            for a in addrs:
                if name in found:
                    break
                try:
                    fd = os.open(path, os.O_RDWR)
                except OSError:
                    continue
                try:
                    fcntl.ioctl(fd, I2C_SLAVE, a)
                    os.read(fd, 1)
                    found[name] = {"bus": bus, "address": hex(a)}
                except OSError as e:
                    if e.errno == errno.EBUSY:          # a kernel driver owns it: present
                        found[name] = {"bus": bus, "address": hex(a), "kernel_driver": True}
                finally:
                    os.close(fd)
    return found


def nmea_valid(data: bytes) -> int:
    """Number of NMEA sentences with a correct checksum in data."""
    n = 0
    for m in NMEA_RE.finditer(data):
        body = m.group(0)[1:m.group(0).index(b"*")]
        c = 0
        for b in body:
            c ^= b
        n += c == int(m.group(2), 16)
    return n


def nmea_info(data: bytes) -> dict:
    """What the checksummed NMEA sentences in data say: {"valid", "satellites" (GSV/GSA
    seen: a receiver tracking satellites — an autopilot's NMEA output sends none), "fix"
    (GGA quality 1/2/4/5 or RMC status A)}.
    """
    info = {"valid": 0, "satellites": False, "fix": False}
    for m in NMEA_RE.finditer(data):
        raw = m.group(0)
        body = raw[1:raw.index(b"*")]
        c = 0
        for b in body:
            c ^= b
        if c != int(m.group(2), 16):
            continue
        info["valid"] += 1
        kind = m.group(1)[2:]
        f = body.split(b",")
        if kind in (b"GSV", b"GSA"):
            info["satellites"] = True
        elif kind == b"GGA" and len(f) > 6 and f[6] in (b"1", b"2", b"4", b"5"):
            info["fix"] = True
        elif kind == b"RMC" and len(f) > 2 and f[2] == b"A":
            info["fix"] = True
    return info


def mavlink_heartbeats(data: bytes) -> List[dict]:
    """Heartbeats parsed from raw bytes: [{"sysid", "compid", "type", "autopilot"}]."""
    from pymavlink.dialects.v20 import common as mav
    p = mav.MAVLink(None)
    p.robust_parsing = True
    out = []
    try:
        msgs = p.parse_buffer(data) or []
    except Exception:                                     # noqa: BLE001 — garbage at a wrong baud
        return out
    for m in msgs:
        if m.get_type() == "HEARTBEAT":
            out.append(dict(sysid=m.get_srcSystem(), compid=m.get_srcComponent(), type=m.type,
                            autopilot=m.autopilot))
    return out


def is_autopilot(hb: dict) -> bool:
    # MAV_AUTOPILOT_INVALID (8): ground station, camera, companion; MAV_TYPE 6 GCS, 18 onboard, 26 gimbal, 30 camera
    return hb["autopilot"] != 8 and hb["type"] not in (6, 18, 26, 30)


def system_reserved(path: str) -> Optional[str]:
    """Why the system keeps this port for itself (kernel console, a login terminal), or None.
    Root's processes cannot be seen in /proc as the navera user: these are checked instead.
    """
    name = os.path.basename(os.path.realpath(path))
    try:
        cmdline = open("/proc/cmdline").read()
        if re.search(rf"\bconsole={re.escape(name)}\b", cmdline):
            return "kernel console"
    except OSError:
        pass
    import subprocess
    try:
        r = subprocess.run(["systemctl", "is-active", f"serial-getty@{name}.service"],
                           capture_output=True, text=True, timeout=3)
        if r.stdout.strip() == "active":
            return "login terminal (serial-getty)"
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def port_in_use(path: str) -> bool:
    real = os.path.realpath(path)
    for fd in glob.glob("/proc/[0-9]*/fd/*"):
        try:
            if os.readlink(fd) == real:
                return True
        except OSError:
            continue
    return False


def gps_kind(data: bytes) -> Optional[dict]:
    """A GPS receiver in raw bytes: {"kind": "ubx"|"nmea", "fix", "satellites", ...} or None.

    UBX: checksummed NAV-PVT frames (a u-blox receiver; an autopilot never sends them, so a
    tap on the receiver's TX wire is recognised the same way). NMEA: 2+ checksummed
    sentences; "satellites" (GSV/GSA) tells a receiver from an autopilot's NMEA output.
    UBX frames without NAV-PVT (a u-blox 6, or NAV-PVT turned off) are reported, not used.
    """
    from navera_common.gnss import ubx_info
    u = ubx_info(data)
    n = nmea_info(data)
    if u["pvt"]:
        return {"kind": "ubx", "fix": u["fix"], "satellites": True, "nmea": n["valid"] >= 2}
    if n["valid"] >= 2:
        return {"kind": "nmea", "satellites": n["satellites"], "fix": n["fix"],
                **({"ubx_without_pvt": True} if u["valid"] >= 2 else {})}
    if u["valid"] >= 2:
        return {"kind": "ubx_no_pvt", "fix": False, "satellites": False}
    return None


def probe_serial_port(path: str, bauds=SERIAL_BAUDS, listen_s: float = 2.2) -> Optional[dict]:
    """{"port", "baud", "kind": "nmea"|"ubx"|"mavlink", ...} for what talks on this port, or None.
    Only reads (a GPS receiver is never configured, an autopilot only once identified).
    """
    try:
        import serial
    except ImportError:
        return None
    if port_in_use(path):
        return {"port": path, "kind": "busy"}
    why = system_reserved(path)
    if why:
        return {"port": path, "kind": "busy", "why": why}
    for baud in bauds:
        try:
            s = serial.Serial(path, baud, timeout=0.2)
        except Exception:                                 # noqa: BLE001 — no such port / no access
            return None
        data, t0 = b"", time.time()
        try:
            while time.time() - t0 < listen_s:
                data += s.read(4096)
                g = gps_kind(data)
                if g and g["satellites"] and g["fix"] and (g["kind"] == "ubx" or nmea_info(data)["valid"] >= 2):
                    break                                 # all there is to know
                hbs = [h for h in mavlink_heartbeats(data) if is_autopilot(h)]
                if hbs:
                    return {"port": path, "baud": baud, "kind": "mavlink", "url": f"serial:{path}:{baud}",
                            **hbs[0]}
            g = gps_kind(data)
            if g:
                return {"port": path, "baud": baud, **g}
        finally:
            s.close()
    return None


def serial_ports() -> List[str]:
    ports = sorted({p for g in SERIAL_GLOBS for p in glob.glob(g)})
    return [p for p in ports if os.access(p, os.R_OK | os.W_OK)]


def probe_mavlink_url(url: str, wait_s: float = 3.0) -> Optional[dict]:
    """An autopilot on a network URL (udpin:0.0.0.0:14550, tcp:host:port)."""
    try:
        from pymavlink import mavutil
        m = mavutil.mavlink_connection(url, source_system=1, source_component=192)
    except Exception:                                     # noqa: BLE001
        return None
    try:
        end = time.time() + wait_s
        while time.time() < end:
            hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=0.5)
            if hb is not None:
                d = dict(sysid=hb.get_srcSystem(), compid=hb.get_srcComponent(), type=hb.type,
                         autopilot=hb.autopilot)
                if is_autopilot(d):
                    return {"kind": "mavlink", "url": url, **d}
    finally:
        m.close()
    return None


def gps_urls(env) -> List[str]:
    """The network GPS addresses to probe: NAVERA_DISCOVER_GPS_URLS (comma-separated);
    "tcp:<host>" without a port tries the common NMEA-over-IP ports of that host, "udp"
    alone listens on 10110. Nothing by default: NAVERA never connects to an address it was
    not given.
    """
    out = []
    for u in str(env.get("NAVERA_DISCOVER_GPS_URLS", "") or "").split(","):
        u = u.strip()
        if not u:
            continue
        kind, _, rest = u.partition(":")
        if kind == "tcp" and rest and ":" not in rest:
            out += [f"tcp:{rest}:{p}" for p in GPS_NET_PORTS]
        elif kind == "udp" and not rest:
            out.append(f"udp:{GPS_NET_PORTS[0]}")
        else:
            out.append(u)
    return list(dict.fromkeys(out))


def probe_gps_url(url: str, listen_s: float = 3.0) -> Optional[dict]:
    """{"kind": "gps_net", "url", "protocol": "ubx"|"nmea", "fix", "satellites"} for a GPS
    stream on the network (read only), or None.
    """
    from navera_common.gnss import Stream
    try:
        st = Stream(url, timeout=0.3)
    except (OSError, ValueError):
        return None
    data, t0 = b"", time.time()
    try:
        while time.time() - t0 < listen_s and len(data) < 65536:
            try:
                data += st.read()
            except (OSError, ConnectionError):
                break
            g = gps_kind(data)
            if g and g["fix"] and g["satellites"]:
                break
    finally:
        st.close()
    g = gps_kind(data)
    if not g or g["kind"] == "ubx_no_pvt":
        return None
    return {"kind": "gps_net", "url": url, "protocol": g["kind"], "fix": g["fix"], "satellites": g["satellites"]}


# ── DroneCAN (CAN bus GNSS) ─────────────────────────────────────────────────
ARPHRD_CAN = 280
CAN_CONTROLLER_TYPES = ("uavcan.equipment.esc.RawCommand", "uavcan.equipment.actuator.ArrayCommand")


def can_interfaces() -> List[dict]:
    """[{"iface", "up"}] for the SocketCAN interfaces of this computer (can0, vcan0, slcan0...)."""
    out = []
    for d in sorted(glob.glob("/sys/class/net/*")):
        try:
            if int(open(os.path.join(d, "type")).read()) != ARPHRD_CAN:
                continue
            flags = int(open(os.path.join(d, "flags")).read(), 16)
        except (OSError, ValueError):
            continue
        out.append({"iface": os.path.basename(d), "up": bool(flags & 0x1)})
    return out


def probe_dronecan(iface: str, listen_s: float = 3.0) -> dict:
    """What a DroneCAN bus carries, heard by a PASSIVE node (no node id: it sends nothing):
    {"kind": "dronecan", "iface", "gnss": [{"node", "fix", "sats", "type"}], "nodes": [ids],
    "controllers": [ids sending ESC / actuator commands: an autopilot], "alloc_requests":
    anonymous nodes ask for an id, "allocator": a node answers them}. iface: a SocketCAN
    name (can0), or any pydronecan address (slcan:/dev/ttyACM0, mcast:0).
    """
    r = {"kind": "dronecan", "iface": iface, "gnss": [], "nodes": [], "controllers": [],
         "alloc_requests": False, "allocator": False}
    try:
        import dronecan
    except ImportError:
        r["error"] = "pydronecan is not installed (pip install dronecan)"
        return r
    import multiprocessing
    before = set(multiprocessing.active_children())
    try:
        node = dronecan.make_node(iface, bitrate=1000000)          # node_id None: passive
    except Exception as e:                                       # noqa: BLE001 — interface down / absent
        r["error"] = str(e)
        return r
    gnss, nodes, ctrl = {}, set(), set()

    def hook(t):
        src = t.source_node_id or 0
        try:
            name = dronecan.get_dronecan_data_type(t.payload).full_name
        except Exception:                                        # noqa: BLE001 — unknown type
            name = ""
        if name == "uavcan.protocol.dynamic_node_id.Allocation":
            if src == 0:
                r["alloc_requests"] = True
            else:
                r["allocator"] = True
        if not src:
            return
        nodes.add(src)
        if name in CAN_CONTROLLER_TYPES:
            ctrl.add(src)
        elif name in ("uavcan.equipment.gnss.Fix2", "uavcan.equipment.gnss.Fix"):
            p = t.payload
            ok = int(p.status) in (2, 3) and (p.latitude_deg_1e8 or p.longitude_deg_1e8)
            g = gnss.setdefault(src, {"node": src, "fix": False, "sats": 0, "type": name.rsplit(".", 1)[1]})
            g["fix"] = g["fix"] or bool(ok)
            g["sats"] = max(g["sats"], int(p.sats_used))
            if name.endswith("Fix2"):
                g["type"] = "Fix2"

    try:
        node.add_transfer_hook(hook)
        end = time.monotonic() + listen_s
        while time.monotonic() < end:
            node.spin(timeout=min(0.2, max(0.0, end - time.monotonic())))
    except Exception as e:                                       # noqa: BLE001
        r["error"] = str(e)
    finally:
        try:
            node.close()
        except Exception:                                        # noqa: BLE001
            pass
        for p in set(multiprocessing.active_children()) - before:   # SLCAN / mcast I/O process
            p.kill()
    r["gnss"] = [gnss[k] for k in sorted(gnss)]
    r["nodes"], r["controllers"] = sorted(nodes), sorted(ctrl)
    return r


def can_buses(env) -> List[str]:
    """The CAN buses to listen to: SocketCAN interfaces that are up, and NAVERA_DISCOVER_CAN
    (comma-separated pydronecan addresses, e.g. slcan:/dev/ttyACM1).
    """
    up = [c["iface"] for c in can_interfaces() if c["up"]]
    extra = [u.strip() for u in str(env.get("NAVERA_DISCOVER_CAN", "") or "").split(",") if u.strip()]
    return list(dict.fromkeys(up + extra))


GPS_TYPE_PARAMS = ("GPS_TYPE", "GPS_TYPE2", "GPS1_TYPE", "GPS2_TYPE")   # ArduPilot 4.5 / 4.6+
MAV_AUTOPILOT_PX4 = 12
# PX4 parameters NAVERA's HIL_GPS output depends on (docs/PX4_INTEGRATION.md §2): name -> (check, what
# it must be). A value read from the autopilot that fails its check is reported as a CHECK line.
PX4_PARAMS = {
    "MAV_USEHILGPS": (lambda v: v == 1, "1 (PX4 reads NAVERA's HIL_GPS only then)"),
    "EKF2_GPS_CTRL": (lambda v: v == 1, "1 (position only: PX4 takes HIL_GPS's velocity as valid and "
                                        "NAVERA states no height)"),
    "EKF2_HGT_REF": (lambda v: v == 0, "0 (barometer: NAVERA gives no height)"),
    "EKF2_GPS_CHECK": (lambda v: not (v & 0b100000101), "bits 0, 2 and 8 clear (e.g. 240): a vision "
                                                        "position has no satellites, a 10-30 m accuracy, "
                                                        "no vertical velocity"),
    "SYS_HAS_GPS": (lambda v: v == 1, "1 (the GPS PX4 fuses is NAVERA's HIL_GPS)"),
    "EKF2_GPS_V_GATE": (lambda v: v >= 50,
                        ">= 50: the HIL_GPS velocity is not fused, but its innovation (0 vertical speed in a "
                        "climb) trips PX4's post-takeoff navigation test (Navigation failure, DESCEND — PX4 SITL)"),
}
# only with vision positions forwarded (NAVERA_FORWARD_DEGRADED): PX4's defaults declare a 10-30 m
# position invalid or trust it more than stated
PX4_FORWARD_PARAMS = {
    "COM_POS_FS_EPH": (lambda v: v < 0 or v >= 20,
                       ">= 20 m: the default 5 m declares the position invalid at 12.5 m and starts the failsafe "
                       "right after the GPS loss"),
    "EKF2_NOAID_NOISE": (lambda v: v >= 30, ">= NAVERA_DEGRADED_SIGMA_M: EKF2 caps the GPS noise at this value "
                                            "while the GPS is its only aiding (default 10 m)"),
}


def autopilot_streams(url: str, wait_s: float = 4.0) -> dict:
    """Ask an identified autopilot for attitude, rangefinder, its two GPS and its height
    above home, and for its GPS receiver types; report what arrives:
    {"ATTITUDE": bool, ..., "GPS_RAW_INT" / "GPS2_RAW": bool (sent, any fix), "gps1_type",
    "gps2_type"}.
    GPS type 14 (MAV) is a GPS fed over MAVLink — NAVERA's own GPS_INPUT, never a source.
    """
    want = {"ATTITUDE": 30, "DISTANCE_SENSOR": 132, "GPS2_RAW": 124, "GLOBAL_POSITION_INT": 33, "GPS_RAW_INT": 24}
    seen = {k: False for k in want}
    seen.update(gps1_type=None, gps2_type=None)
    try:
        from pymavlink import mavutil
        from navera_output.mavlink_url import connect
        m = connect(url, 1, 192)
    except Exception:                                     # noqa: BLE001
        return seen
    try:
        hb = m.wait_heartbeat(timeout=3)
        if hb is None:
            return seen
        for mid in want.values():
            m.mav.command_long_send(m.target_system, m.target_component,
                                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, mid, 500000, 0, 0, 0, 0, 0)
        px4 = hb.autopilot == MAV_AUTOPILOT_PX4
        if px4:
            seen["px4_params"] = {}
        for p in (list(PX4_PARAMS) + list(PX4_FORWARD_PARAMS) if px4 else GPS_TYPE_PARAMS):
            m.mav.param_request_read_send(m.target_system, m.target_component, p.encode(), -1)
        end = time.time() + wait_s

        def params_done():
            if px4:
                return len(seen["px4_params"]) == len(PX4_PARAMS) + len(PX4_FORWARD_PARAMS)
            return seen["gps1_type"] is not None and seen["gps2_type"] is not None
        while time.time() < end and not (all(seen[k] for k in want) and params_done()):
            msg = m.recv_match(blocking=True, timeout=0.5)
            if msg is None:
                continue
            t = msg.get_type()
            if t in want:
                seen[t] = True
            elif t == "PARAM_VALUE":
                pid = msg.param_id.rstrip("\x00") if isinstance(msg.param_id, str) else msg.param_id
                if px4 and (pid in PX4_PARAMS or pid in PX4_FORWARD_PARAMS):
                    seen["px4_params"][pid] = px4_param_int(msg.param_value, msg.param_type)
                elif pid in ("GPS_TYPE", "GPS1_TYPE"):
                    seen["gps1_type"] = int(msg.param_value)
                elif pid in ("GPS_TYPE2", "GPS2_TYPE"):
                    seen["gps2_type"] = int(msg.param_value)
    finally:
        m.close()
    return seen


def px4_param_int(value: float, param_type: int) -> int:
    """An integer PX4 parameter from PARAM_VALUE: PX4 sends INT32 bytewise in the float field
    (MAV_PARAM_TYPE_INT32 = 6); a REAL32 one is rounded.
    """
    import struct
    if param_type == 6:
        return struct.unpack("<i", struct.pack("<f", value))[0]
    return int(round(value))


def px4_param_checks(params: dict, forward: bool = False) -> List[str]:
    """CHECK lines for the PX4 parameters read that NAVERA's HIL_GPS output cannot work with
    (forward: vision positions are forwarded, NAVERA_FORWARD_DEGRADED — their parameters too).
    """
    rep = []
    for name, (ok, want) in list(PX4_PARAMS.items()) + (list(PX4_FORWARD_PARAMS.items()) if forward else []):
        if name in params and not ok(params[name]):
            rep.append(f"CHECK PX4 {name} = {params[name]}: must be {want} — docs/PX4_INTEGRATION.md")
    return rep


INSTA360_USB_ID = ("2e1a", "0002")          # the One R in USB "Android" mode (insta360_protocol.VENDOR)


def probe_insta360(sysfs: str = "/sys/bus/usb/devices") -> List[str]:
    """USB device paths of Insta360 One R cameras in USB "Android" mode (read from sysfs only:
    the camera is never opened here — a wrong probe has wedged it until replugged, D10).
    """
    out = []
    for d in sorted(glob.glob(os.path.join(sysfs, "*"))):
        try:
            ids = tuple(open(os.path.join(d, f)).read().strip().lower() for f in ("idVendor", "idProduct"))
        except OSError:
            continue
        if ids == INSTA360_USB_ID:
            out.append(os.path.basename(d))
    return out


def probe_cameras() -> Dict[str, list]:
    usb = sorted(p for p in glob.glob("/dev/v4l/by-id/*-video-index0"))
    csi = []
    for d in sorted(glob.glob("/sys/class/video4linux/video*")):
        try:
            name = open(os.path.join(d, "name")).read().strip()
        except OSError:
            continue
        if "vi-output" in name or re.search(r"\b(imx|ov)\d", name, re.I):
            csi.append(name)
    return {"usb": usb, "csi": csi, "insta360": probe_insta360()}


def probe_ros(domains, wait_s: float = 3.0) -> Dict[int, Dict[str, List[str]]]:
    """{domain: {message type: [topics]}} of the vehicle's topics (NAVERA's own excluded)."""
    out = {}
    os.environ["ROS_LOCALHOST_ONLY"] = "0"                # a vehicle is another computer
    try:
        import rclpy
    except ImportError:
        return out
    for d in domains:
        ctx = rclpy.Context()
        try:
            rclpy.init(context=ctx, domain_id=int(d))
            node = rclpy.create_node("navera_discovery", context=ctx)
            time.sleep(wait_s)
            types = {}
            for name, tys in node.get_topic_names_and_types():
                if name.startswith(NAVERA_NS):
                    continue
                for ty in tys:
                    types.setdefault(ty, []).append(name)
            out[int(d)] = types
            node.destroy_node()
        except Exception:                                 # noqa: BLE001
            continue
        finally:
            try:
                rclpy.shutdown(context=ctx)
            except Exception:                             # noqa: BLE001
                pass
    return out


def discover(env=None, ros_wait_s: float = 8.0) -> dict:
    """Everything found (probes run in parallel: ~20 s)."""
    env = os.environ if env is None else env
    found = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "i2c": {}, "serial": [], "network": [],
             "cameras": {}, "ros": {}, "can": [], "gps_net": [], "can_ifaces": can_interfaces()}
    threads = []

    def run(key, fn, *a):
        def w():
            r = fn(*a)
            if isinstance(found[key], list):
                if r:
                    found[key].append(r)
            else:
                found[key] = r
        threads.append(threading.Thread(target=w, daemon=True))

    run("i2c", probe_i2c)
    run("cameras", probe_cameras)
    for p in serial_ports():
        run("serial", probe_serial_port, p)
    for url in mavlink_urls(env):
        run("network", probe_mavlink_url, url)
    for url in gps_urls(env):
        run("gps_net", probe_gps_url, url)
    for bus in can_buses(env):
        run("can", probe_dronecan, bus)
    written = str(env.get("ROS_DOMAIN_ID", "") or "").strip()     # a number, or "auto"
    domains = sorted({0} | ({int(written)} if written.isdigit() else set()) |
                     {int(x) for x in str(env.get("NAVERA_DISCOVER_ROS_DOMAINS", "")).split(",")
                      if x.strip().isdigit()})
    run("ros", probe_ros, domains, ros_wait_s)
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    aps = autopilots(found)
    if aps:
        found["autopilot_streams"] = autopilot_streams(aps[0]["url"])
    return found


def mavlink_urls(env) -> List[str]:
    extra = [u.strip() for u in str(env.get("NAVERA_DISCOVER_MAVLINK", "")).split(",") if u.strip()]
    return list(dict.fromkeys(list(MAVLINK_NET_DEFAULT) + extra))


def autopilots(found: dict) -> List[dict]:
    """The autopilot links found, the preferred first (wired UART, then USB, then network)."""
    aps = [x for x in (found.get("serial") or []) + (found.get("network") or []) if x.get("kind") == "mavlink"]
    return sorted(aps, key=lambda x: (_port_rank(x["url"]), x["url"]))


# ── decision (pure) ─────────────────────────────────────────────────────────
def _pick(topics: List[str], words) -> Optional[str]:
    if not topics:
        return None
    return sorted(topics, key=lambda t: (-sum(w in t.lower() for w in words), len(t), t))[0]


def _port_rank(p: str) -> int:
    """Wired UARTs first (an autopilot TELEM port, the box's GPS), then USB, then network."""
    return 0 if "ttyTHS" in p else 1 if "ttyACM" in p else 2 if "/dev/" in p else 3


def _proto(kind: str) -> str:
    return {"ubx": "u-blox UBX", "nmea": "NMEA"}.get(kind, kind)


def decide(found: dict, env) -> dict:
    """{"settings": {KEY: value}, "report": [lines]} — values only for settings left to
    "auto" or unset in env; the report says what was found and why each choice. Lines
    with "NO " or "CHECK" are warnings (check_box).
    """
    get = lambda k: str(env.get(k, "") or "").strip()                       # noqa: E731
    auto = lambda k: get(k).lower() in ("", "auto")                         # noqa: E731
    out, rep = {}, []
    att_none = False
    i2c = found.get("i2c") or {}
    serial = found.get("serial") or []
    cams = found.get("cameras") or {}
    streams = found.get("autopilot_streams") or {}

    # GPS receivers on serial: u-blox UBX (NAV-PVT), or NMEA tracking satellites (GSV/GSA —
    # an autopilot's NMEA output sends none)
    receivers = sorted((s for s in serial if s.get("kind") == "ubx" or
                        (s.get("kind") == "nmea" and s.get("satellites"))),
                       key=lambda s: (not s.get("fix"), _port_rank(s["port"]), s["port"]))
    gps_port = receivers[0] if receivers else None
    for s in serial:
        if s.get("kind") == "nmea" and not s.get("satellites"):
            rep.append(f"  {s['port']}: NMEA without satellite data (an autopilot's NMEA output?) — "
                       f"not used as a GPS")
        elif s.get("kind") == "ubx_no_pvt":
            rep.append(f"  {s['port']} @{s['baud']}: u-blox UBX without NAV-PVT (a u-blox 6, or NAV-PVT turned "
                       f"off) — not used; NMEA from it would be")
    # DroneCAN GNSS nodes (Fix2 / Fix), heard passively on the CAN buses that are up
    can_gnss = []
    for b in found.get("can") or []:
        if b.get("error"):
            rep.append(f"CHECK DroneCAN on {b['iface']}: {b['error']}")
        for g in b.get("gnss") or []:
            if g["node"] in (b.get("controllers") or []):
                rep.append(f"  {b['iface']} node {g['node']} sends a GNSS fix but also commands motors (an autopilot "
                           f"re-broadcasting its own GPS, maybe NAVERA's) — not used")
                continue
            can_gnss.append((b, g))
        if b.get("alloc_requests") and not b.get("allocator"):
            rep.append(f"CHECK {b['iface']}: a DroneCAN device asks for a node id and nothing gives one (a GPS alone "
                       f"on NAVERA's CAN?) — set NAVERA_GPS_CAN_ALLOCATE=1, or give it a fixed node id")
    can_gnss.sort(key=lambda bg: (not bg[1]["fix"], bg[1]["node"], bg[0]["iface"]))
    for c in found.get("can_ifaces") or []:
        if not c["up"]:
            rep.append(f"  {c['iface']} is down: not listened to (a DroneCAN GPS on it: "
                       f"sudo ip link set {c['iface']} up type can bitrate 1000000)")
    # GPS streams on the network (NAVERA_DISCOVER_GPS_URLS)
    net_gps = sorted((g for g in found.get("gps_net") or [] if g.get("protocol") == "ubx" or g.get("satellites")),
                     key=lambda g: (not g.get("fix"), g["url"]))
    for g in found.get("gps_net") or []:
        if g.get("protocol") == "nmea" and not g.get("satellites"):
            rep.append(f"  {g['url']}: NMEA without satellite data — not used as a GPS")
    # autopilots: one per system id, its wired port preferred
    aps = autopilots(found)
    ap = aps[0] if aps else None
    if len({x["sysid"] for x in aps}) > 1:
        rep.append("CHECK several autopilots answer (" + ", ".join(f"{x['url']} system {x['sysid']}" for x in aps)
                   + f"): using {ap['url']} — set NAVERA_VEHICLE_MAVLINK_URL to choose")
    elif len(aps) > 1:
        rep.append(f"  the autopilot answers on {len(aps)} links; using {ap['url']}")
    # ROS vehicle, usable only on NAVERA's domain or with ROS_DOMAIN_ID=auto
    ros, ros_domain = {}, None
    for d, types in sorted((found.get("ros") or {}).items(), key=lambda kv: -len(kv[1])):
        if any(t in types for t in ("sensor_msgs/msg/Imu", "sensor_msgs/msg/NavSatFix", "sensor_msgs/msg/Image")):
            ros, ros_domain = types, int(d)
            break
    join_domain = False
    if ros_domain is not None:
        dom, local = get("ROS_DOMAIN_ID").lower() or "0", get("ROS_LOCALHOST_ONLY")   # ROS default: 0
        if dom == "auto":
            join_domain = True
        elif dom.isdigit() and int(dom) == ros_domain and local != "1":
            pass
        else:
            rep.append(f"CHECK a ROS vehicle is on domain {ros_domain}, NAVERA is on domain {dom or 0}"
                       f"{' (loopback only)' if local == '1' else ''} as written in navera.env: not used "
                       f"— set ROS_DOMAIN_ID=auto (or {ros_domain}) and ROS_LOCALHOST_ONLY=0 to use it")
            ros, ros_domain = {}, None
    ros_imu = _pick(ros.get("sensor_msgs/msg/Imu", []), ("imu", "data"))
    ros_gps = _pick([t for t in ros.get("sensor_msgs/msg/NavSatFix", []) if t != "/navera/fix"], ("gps", "fix"))
    ros_cam = _pick([t for t in ros.get("sensor_msgs/msg/Image", [])
                     if not re.search(r"depth|disparity|thermal|ir/|compressed", t)],
                    ("down", "nadir", "bottom", "camera", "image_raw"))
    ros_alt = _pick(ros.get("sensor_msgs/msg/Range", []), ("down", "altitude", "range"))
    # cameras: the star camera and an imposed device are not candidates for the day camera
    taken = {os.path.realpath(get(k)) for k in ("NAVERA_STAR_CAMERA_DEVICE",) if get(k)}
    usb = [c for c in cams.get("usb") or [] if os.path.realpath(c) not in taken and c not in taken]

    rep.insert(0, "found: " + (", ".join(filter(None, [
        "box IMU" if "imu" in i2c else None, "box clock" if "rtc" in i2c else None,
        f"GPS receiver {gps_port['port']} @{gps_port['baud']} ({_proto(gps_port['kind'])})"
        f"{'' if gps_port.get('fix') else ' (no fix yet)'}" if gps_port else None,
        f"DroneCAN GPS {can_gnss[0][0]['iface']} node {can_gnss[0][1]['node']}"
        f"{'' if can_gnss[0][1]['fix'] else ' (no fix yet)'}" if can_gnss else None,
        f"network GPS {net_gps[0]['url']} ({_proto(net_gps[0]['protocol'])})" if net_gps else None,
        f"autopilot {ap['url']} (system {ap['sysid']})" if ap else None,
        f"ROS vehicle on domain {ros_domain}" if ros_domain is not None else None,
        f"USB camera {os.path.basename(usb[0])}" if usb else None,
        f"CSI camera {cams['csi'][0]}" if cams.get("csi") else None,
        "Insta360 One R in USB Android mode (camera + IMU kit)" if cams.get("insta360") else None])) or "nothing"))
    for s in serial:
        if s.get("kind") == "busy":
            rep.append(f"  {s['port']} is held by {s.get('why') or 'another program'}: not probed")
    direct = ([r["port"] for r in receivers] + [f"{b['iface']} node {g['node']}" for b, g in can_gnss]
              + [g["url"] for g in net_gps])
    if len(direct) > 1:
        rep.append("CHECK several GPS receivers (" + ", ".join(direct) + f"): using {direct[0]} — set "
                   "NAVERA_GPS_SOURCE and NAVERA_GPS_PORT / NAVERA_GPS_CAN_NODE / NAVERA_GPS_URL to choose")

    # which box chips are fitted (the IMU and clock services idle without them)
    out["NAVERA_BOX_IMU"] = "1" if "imu" in i2c else "0"
    out["NAVERA_BOX_RTC"] = "1" if "rtc" in i2c else "0"
    if "imu" in i2c:
        out["NAVERA_BOX_IMU_BUS"] = str(i2c["imu"]["bus"])
        if i2c["imu"].get("address"):
            out["NAVERA_BOX_IMU_ADDR"] = i2c["imu"]["address"]           # 0x4A, or 0x4B
    if "rtc" in i2c:
        out["NAVERA_BOX_RTC_BUS"] = str(i2c["rtc"]["bus"])
    # attitude (and with it the height sources)
    if auto("NAVERA_SENSOR_SOURCE"):
        if "imu" in i2c:
            out["NAVERA_SENSOR_SOURCE"], why = "box", "the box's own IMU (rigid with the camera)"
        elif ap and streams.get("ATTITUDE", True):
            out["NAVERA_SENSOR_SOURCE"], why = "vehicle", "no box IMU; the autopilot's attitude"
        elif ros_imu:
            out["NAVERA_SENSOR_SOURCE"], why = "ros", f"no box IMU, no autopilot; ROS {ros_imu}"
            out["NAVERA_ROS_IMU_TOPIC"] = ros_imu
            if ros_alt:
                out["NAVERA_ROS_ALTITUDE_TOPIC"] = ros_alt
        elif cams.get("insta360"):
            out["NAVERA_SENSOR_SOURCE"], why = "insta360", ("no box IMU, no autopilot, no ROS IMU; the Insta360 "
                                                            "One R's own IMU (the Insta360 kit)")
        else:
            out["NAVERA_SENSOR_SOURCE"], why = "box", "NO attitude source found (frames will be unusable)"
            att_none = True
        rep.append(f"attitude: {out['NAVERA_SENSOR_SOURCE']} — {why}")
    # GPS (the start position and the cross-check). Never a GPS NAVERA itself feeds: the
    # autopilot's MAVLink GPS (type 14 — NAVERA's GPS_INPUT), or its NMEA GPS (type 5) while
    # NAVERA's NMEA output is on (NAVERA_NMEA_PORT).
    if auto("NAVERA_GPS_SOURCE"):
        g1, g2 = streams.get("gps1_type"), streams.get("gps2_type")
        nmea_out = get("NAVERA_NMEA_PORT").lower() not in ("", "off", "none")

        def own_feed(t):
            return t == GPS_TYPE_MAV or (t == GPS_TYPE_NMEA and nmea_out)
        gps1_ok = get("NAVERA_GPS_MONITOR_GPS1").lower() not in ("0", "off", "false", "no")
        if gps_port:
            out.update(NAVERA_GPS_SOURCE="serial", NAVERA_GPS_PORT=gps_port["port"],
                       NAVERA_GPS_BAUD=str(gps_port["baud"]))
            why = (f"the receiver on {gps_port['port']} ({_proto(gps_port['kind'])})"
                   + ("" if gps_port.get("fix") else " (no fix yet)"))
        elif can_gnss:
            b, g = can_gnss[0]
            out.update(NAVERA_GPS_SOURCE="dronecan", NAVERA_GPS_CAN_IFACE=b["iface"],
                       NAVERA_GPS_CAN_NODE=str(g["node"]))
            why = f"DroneCAN GNSS node {g['node']} on {b['iface']}" + ("" if g["fix"] else " (no fix yet)")
        elif net_gps:
            out.update(NAVERA_GPS_SOURCE="network", NAVERA_GPS_URL=net_gps[0]["url"])
            why = f"{_proto(net_gps[0]['protocol'])} from {net_gps[0]['url']}" + \
                ("" if net_gps[0].get("fix") else " (no fix yet)")
        elif ap and g2 not in (None, 0) and not own_feed(g2):
            out["NAVERA_GPS_SOURCE"], why = "vehicle", f"the autopilot's second GPS (type {g2})"
        elif ap and gps1_ok and g1 not in (None, 0) and not own_feed(g1):
            out["NAVERA_GPS_SOURCE"] = "vehicle_gps1"
            why = (f"the autopilot's first GPS (type {g1}; NAVERA does not feed it"
                   + (f": NAVERA is its second GPS, type {g2})" if g2 == GPS_TYPE_MAV else ")"))
        elif ros_gps:
            out.update(NAVERA_GPS_SOURCE="ros", NAVERA_ROS_GPS_TOPIC=ros_gps)
            why = f"ROS {ros_gps}"
        else:
            out["NAVERA_GPS_SOURCE"] = "none"
            why = "NO GPS found — NAVERA needs one fix at start"
            if ap and (own_feed(g1) or own_feed(g2)):
                why += " (the autopilot's GPS fed by NAVERA's own output is never used)"
            elif ap and g1 is None and g2 is None:
                why += " (the autopilot's GPS types could not be read: its GPS are not trusted)"
            if ap and not gps1_ok and g1 not in (None, 0) and not own_feed(g1):
                why += " (the autopilot's first GPS not read: NAVERA_GPS_MONITOR_GPS1=0)"
        rep.append(f"GPS: {out['NAVERA_GPS_SOURCE']} — {why}")
    # camera
    if auto("NAVERA_CAMERA_INPUT"):
        written = get("NAVERA_CAMERA_DEVICE")
        if written:
            out["NAVERA_CAMERA_INPUT"], why = "usb", f"the device written in navera.env ({written})"
        elif cams.get("insta360"):
            # in Android mode the One R is no webcam; only the kit's process can read it
            out["NAVERA_CAMERA_INPUT"], why = "insta360", "the Insta360 One R in USB Android mode (the Insta360 kit)"
        elif usb:
            out.update(NAVERA_CAMERA_INPUT="usb", NAVERA_CAMERA_DEVICE=usb[0])
            why = f"USB {os.path.basename(usb[0])}"
            if len(usb) > 1:
                why += (" — CHECK several cameras (" + ", ".join(os.path.basename(c) for c in usb)
                        + "): set NAVERA_CAMERA_DEVICE to the one looking down")
        elif cams.get("csi"):
            out.update(NAVERA_CAMERA_INPUT="csi", NAVERA_CAMERA_DEVICE="0")
            why = f"CSI {cams['csi'][0]}"
        elif ros_cam:
            out.update(NAVERA_CAMERA_INPUT="ros", NAVERA_CAMERA_TOPIC=ros_cam)
            why = (f"ROS {ros_cam} — CHECK it looks at the ground (else set NAVERA_CAMERA_MOUNT_RPY, "
                   f"or fit NAVERA's camera)")
        else:
            out["NAVERA_CAMERA_INPUT"], why = "usb", "NO camera found"
        rep.append(f"camera: {out['NAVERA_CAMERA_INPUT']} — {why}")
    if any("insta360" in os.path.basename(c).lower() for c in cams.get("usb") or []):
        rep.append("CHECK an Insta360 in WEBCAM mode: cropped strips and no IMU — for the Insta360 kit set its "
                   "USB mode to Android (camera menu), then replug")
    # the autopilot link: read its sensors and give it NAVERA's position, as its companion
    if ap:
        if not get("NAVERA_VEHICLE_MAVLINK_URL"):
            out["NAVERA_VEHICLE_MAVLINK_URL"] = ap["url"]
        if not get("NAVERA_MAVLINK_SYSID"):
            out["NAVERA_MAVLINK_SYSID"] = str(ap["sysid"])
        url = get("NAVERA_MAVLINK_URL").lower()
        if url in ("off", "none"):
            rep.append("output: MAVLink to the autopilot turned off (NAVERA_MAVLINK_URL=off)")
        else:
            if not url:
                # one link: vehicle_link owns it and relays NAVERA's GPS_INPUT
                out["NAVERA_MAVLINK_URL"] = "udpout:127.0.0.1:14650"
            if ap.get("autopilot") == MAV_AUTOPILOT_PX4:
                # PX4 has no GPS_INPUT handler: it reads HIL_GPS as a GPS (MAV_USEHILGPS = 1)
                if get("NAVERA_MAVLINK_MESSAGE").lower() in ("", "auto"):
                    out["NAVERA_MAVLINK_MESSAGE"] = "hil_gps"
                msg = out.get("NAVERA_MAVLINK_MESSAGE") or get("NAVERA_MAVLINK_MESSAGE")
                rep.append(f"output: NAVERA's position to PX4 over MAVLink as {msg.upper()} ({ap['url']}, "
                           f"system {ap['sysid']})")
                if msg == "gps_input":
                    rep.append("CHECK output: NAVERA_MAVLINK_MESSAGE=gps_input, but PX4 ignores GPS_INPUT — "
                               "use hil_gps or auto (docs/PX4_INTEGRATION.md)")
                params = streams.get("px4_params")
                if params is None or any(k not in params for k in PX4_PARAMS):
                    rep.append("CHECK PX4 parameters not all read: set MAV_USEHILGPS 1, EKF2_GPS_CTRL 1, "
                               "EKF2_HGT_REF 0, EKF2_GPS_CHECK 240, EKF2_GPS_V_GATE 100 (docs/PX4_INTEGRATION.md)")
                fwd = get("NAVERA_FORWARD_DEGRADED").lower() in ("1", "true", "yes", "on")
                rep.extend(px4_param_checks(params or {}, fwd))
            else:
                rep.append(f"output: NAVERA's position to the autopilot over MAVLink ({ap['url']}, "
                           f"system {ap['sysid']})")
    # ROS vehicle: publish /navera/fix on its graph
    if ros_domain is not None:
        if join_domain:
            out.update(ROS_DOMAIN_ID=str(ros_domain), ROS_LOCALHOST_ONLY="0")
        if "NAVERA_ROS_FIX_TOPIC" not in env:
            out["NAVERA_ROS_FIX_TOPIC"] = "/navera/fix"
        rep.append(f"output: /navera/fix (sensor_msgs/NavSatFix) on ROS domain {ros_domain}")
    if not ap and ros_domain is None:
        rep.append("output: no autopilot and no ROS vehicle found — set NAVERA_NMEA_PORT for an NMEA GPS input")
    # what stays idle (navera_common.hotplug fills it when a device appears later)
    idle = []
    if out.get("NAVERA_GPS_SOURCE") == "none":
        idle.append("gps")
    if att_none:
        idle.append("attitude")
    if auto("NAVERA_CAMERA_INPUT") and out.get("NAVERA_CAMERA_INPUT") == "usb" and "NAVERA_CAMERA_DEVICE" not in out \
            and not get("NAVERA_CAMERA_DEVICE"):
        idle.append("camera")
    if not ap and not get("NAVERA_VEHICLE_MAVLINK_URL"):
        idle.append("autopilot")
    return {"settings": out, "report": rep, "idle": idle}


def write_env(settings: dict, path: str) -> None:
    from navera_common.atomic_io import atomic_write
    lines = ["# Written at boot by navera-discover (navera_common.discovery): what was found.\n"
             "# Only for settings left to auto in /etc/navera/navera.env. Do not edit.\n"]
    for k in sorted(settings):
        v = str(settings[k])
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", k) or re.search(r"[\x00-\x1f\x7f]", v):
            continue
        lines.append(f"{k}={v}\n")
    atomic_write(path, "".join(lines))          # temp + fsync + rename: power-cut safe


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Find what is connected to this NAVERA box.")
    ap.add_argument("--env-out", help="write the decided settings here (e.g. /var/lib/navera/discovered.env)")
    ap.add_argument("--json-out", help="write the full report here")
    ap.add_argument("--ros-wait", type=float, default=8.0)      # DDS discovery: seconds; ports take ~15 s anyway
    a = ap.parse_args(argv)
    found = discover(ros_wait_s=a.ros_wait)
    d = decide(found, os.environ)
    print("\n".join(d["report"]))
    if a.env_out:
        write_env(d["settings"], a.env_out)
    if a.json_out:
        from navera_common.atomic_io import atomic_write_json
        atomic_write_json(a.json_out, dict(found=found, settings=d["settings"], report=d["report"], idle=d["idle"]),
                          indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
