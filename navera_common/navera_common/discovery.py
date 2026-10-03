"""What is connected to this NAVERA box, and which source to use for what.

At every boot (navera-discover.service, before the other units) NAVERA looks for:
  * its own sensors: IMU (BNO085, I2C 0x4A/0x4B) and clock (DS3231, I2C 0x68) on I2C
    buses 1 and 7, a GPS receiver (checksummed NMEA) on the serial ports;
  * an autopilot: MAVLink heartbeats on the serial ports and the network (UDP 14550/14551);
    it is asked which data it streams (attitude, rangefinder, second GPS);
  * a ROS vehicle: IMU / GPS / camera / height topics on the ROS domains;
  * cameras: USB (/dev/v4l/by-id) and CSI (Jetson video inputs).
then decides, for each need, the best source found (decide()): attitude box IMU >
autopilot > ROS; GPS box receiver > autopilot's second GPS > ROS; camera USB > CSI > ROS;
outputs: MAVLink to the autopilot when one answers (through vehicle_link's relay when it is
the same link), /navera/fix on ROS when a ROS vehicle is there.

Only settings left to "auto" (or unset) are decided: a value written in navera.env always
wins. The result is an env file read by the services after navera.env, and a JSON report.
Probing only READS serial ports, except an identified autopilot, which is asked for its
data streams; a port another process holds open is never touched.
"""
import glob
import json
import os
import re
import threading
import time
from typing import Dict, List, Optional

I2C_SLAVE = 0x0703
IMU_ADDRS, RTC_ADDR = (0x4A, 0x4B), 0x68
SERIAL_GLOBS = ("/dev/ttyTHS*", "/dev/ttyUSB*", "/dev/ttyACM*")
SERIAL_BAUDS = (9600, 38400, 57600, 115200, 230400, 460800, 921600)
NMEA_RE = re.compile(rb"\$([A-Z]{2}[A-Z]{3}),[^*\r\n]*\*([0-9A-F]{2})")
NAVERA_NS = ("/navera", "/day", "/night", "/thermal", "/celestial", "/cn", "/rosout", "/parameter_events")
AUTO_KEYS = ("NAVERA_SENSOR_SOURCE", "NAVERA_GPS_SOURCE", "NAVERA_CAMERA_INPUT")


# ── probes (each returns plain data; never raises) ─────────────────────────
def probe_i2c(buses=(1, 7)) -> Dict[str, dict]:
    """{"imu": {"bus", "address"}, "rtc": {...}} for the chips that answer (or are held by a
    kernel driver, which proves they are there)."""
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
    (GGA quality 1/2/4/5 or RMC status A)}."""
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
    Root's processes cannot be seen in /proc as the navera user: these are checked instead."""
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


def probe_serial_port(path: str, bauds=SERIAL_BAUDS, listen_s: float = 2.2) -> Optional[dict]:
    """{"port", "baud", "kind": "nmea"|"mavlink", ...} for what talks on this port, or None."""
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
                n = nmea_info(data)
                if n["valid"] >= 2 and n["satellites"] and n["fix"]:
                    break                                 # all there is to know
                hbs = [h for h in mavlink_heartbeats(data) if is_autopilot(h)]
                if hbs:
                    return {"port": path, "baud": baud, "kind": "mavlink", "url": f"serial:{path}:{baud}",
                            **hbs[0]}
            n = nmea_info(data)
            if n["valid"] >= 2:
                return {"port": path, "baud": baud, "kind": "nmea", "satellites": n["satellites"],
                        "fix": n["fix"]}
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


GPS_TYPE_PARAMS = ("GPS_TYPE", "GPS_TYPE2", "GPS1_TYPE", "GPS2_TYPE")   # ArduPilot 4.5 / 4.6+


def autopilot_streams(url: str, wait_s: float = 4.0) -> dict:
    """Ask an identified autopilot for attitude, rangefinder, second GPS and its height
    above home, and for its GPS receiver types; report what arrives:
    {"ATTITUDE": bool, ..., "GPS2_RAW": bool (sent, any fix), "gps1_type", "gps2_type"}.
    GPS type 14 (MAV) is a GPS fed over MAVLink — NAVERA's own GPS_INPUT, never a source."""
    want = {"ATTITUDE": 30, "DISTANCE_SENSOR": 132, "GPS2_RAW": 124, "GLOBAL_POSITION_INT": 33}
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
        for p in GPS_TYPE_PARAMS:
            m.mav.param_request_read_send(m.target_system, m.target_component, p.encode(), -1)
        end = time.time() + wait_s
        while time.time() < end and not (all(seen[k] for k in want) and seen["gps2_type"] is not None):
            msg = m.recv_match(blocking=True, timeout=0.5)
            if msg is None:
                continue
            t = msg.get_type()
            if t in want:
                seen[t] = True
            elif t == "PARAM_VALUE":
                pid = msg.param_id.rstrip("\x00") if isinstance(msg.param_id, str) else msg.param_id
                if pid in ("GPS_TYPE", "GPS1_TYPE"):
                    seen["gps1_type"] = int(msg.param_value)
                elif pid in ("GPS_TYPE2", "GPS2_TYPE"):
                    seen["gps2_type"] = int(msg.param_value)
    finally:
        m.close()
    return seen


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
    return {"usb": usb, "csi": csi}


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
             "cameras": {}, "ros": {}}
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
    extra = [u.strip() for u in str(env.get("NAVERA_DISCOVER_MAVLINK", "")).split(",") if u.strip()]
    for url in ["udpin:0.0.0.0:14550", "udpin:0.0.0.0:14551"] + extra:
        run("network", probe_mavlink_url, url)
    domains = sorted({0, int(env.get("ROS_DOMAIN_ID", "0") or 0)} |
                     {int(x) for x in str(env.get("NAVERA_DISCOVER_ROS_DOMAINS", "")).split(",") if x.strip().isdigit()})
    run("ros", probe_ros, domains, ros_wait_s)
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    ap = next((x for x in found["serial"] + found["network"] if x.get("kind") == "mavlink"), None)
    if ap:
        found["autopilot_streams"] = autopilot_streams(ap["url"])
    return found


# ── decision (pure) ─────────────────────────────────────────────────────────
def _pick(topics: List[str], words) -> Optional[str]:
    if not topics:
        return None
    return sorted(topics, key=lambda t: (-sum(w in t.lower() for w in words), len(t), t))[0]


def _port_rank(p: str) -> int:
    """Wired UARTs first (an autopilot TELEM port, the box's GPS), then USB."""
    return 0 if "ttyTHS" in p else 1 if "ttyACM" in p else 2


def decide(found: dict, env) -> dict:
    """{"settings": {KEY: value}, "report": [lines]} — values only for settings left to
    "auto" or unset in env; the report says what was found and why each choice. Lines
    with "NO " or "CHECK" are warnings (check_box)."""
    get = lambda k: str(env.get(k, "") or "").strip()                       # noqa: E731
    auto = lambda k: get(k).lower() in ("", "auto")                         # noqa: E731
    out, rep = {}, []
    i2c = found.get("i2c") or {}
    serial = found.get("serial") or []
    cams = found.get("cameras") or {}
    streams = found.get("autopilot_streams") or {}

    # GPS receivers: they track satellites (GSV/GSA) — an autopilot's NMEA output does not
    receivers = sorted((s for s in serial if s.get("kind") == "nmea" and s.get("satellites")),
                       key=lambda s: (not s.get("fix"), _port_rank(s["port"]), s["port"]))
    gps_port = receivers[0] if receivers else None
    for s in serial:
        if s.get("kind") == "nmea" and not s.get("satellites"):
            rep.append(f"  {s['port']}: NMEA without satellite data (an autopilot's NMEA output?) — "
                       f"not used as a GPS")
    # autopilots: one per system id, its wired port preferred
    aps = [x for x in serial + (found.get("network") or []) if x.get("kind") == "mavlink"]
    aps.sort(key=lambda x: (_port_rank(x["url"]), x["url"]))
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
        f"GPS receiver {gps_port['port']} @{gps_port['baud']}{'' if gps_port.get('fix') else ' (no fix yet)'}"
        if gps_port else None,
        f"autopilot {ap['url']} (system {ap['sysid']})" if ap else None,
        f"ROS vehicle on domain {ros_domain}" if ros_domain is not None else None,
        f"USB camera {os.path.basename(usb[0])}" if usb else None,
        f"CSI camera {cams['csi'][0]}" if cams.get("csi") else None])) or "nothing"))
    for s in serial:
        if s.get("kind") == "busy":
            rep.append(f"  {s['port']} is held by {s.get('why') or 'another program'}: not probed")
    if len(receivers) > 1:
        rep.append("CHECK several GPS receivers (" + ", ".join(r["port"] for r in receivers)
                   + f"): using {gps_port['port']} — set NAVERA_GPS_PORT to choose")

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
        else:
            out["NAVERA_SENSOR_SOURCE"], why = "box", "NO attitude source found (frames will be unusable)"
        rep.append(f"attitude: {out['NAVERA_SENSOR_SOURCE']} — {why}")
    # GPS (the start position and the cross-check)
    if auto("NAVERA_GPS_SOURCE"):
        g2 = streams.get("gps2_type")
        if gps_port:
            out.update(NAVERA_GPS_SOURCE="serial", NAVERA_GPS_PORT=gps_port["port"],
                       NAVERA_GPS_BAUD=str(gps_port["baud"]))
            why = f"the box's receiver on {gps_port['port']}" + ("" if gps_port.get("fix") else " (no fix yet)")
        elif ap and g2 not in (None, 0, 14):
            out["NAVERA_GPS_SOURCE"], why = "vehicle", f"the autopilot's second GPS (type {g2})"
        elif ros_gps:
            out.update(NAVERA_GPS_SOURCE="ros", NAVERA_ROS_GPS_TOPIC=ros_gps)
            why = f"ROS {ros_gps}"
        else:
            out["NAVERA_GPS_SOURCE"] = "none"
            why = "NO GPS found — NAVERA needs one fix at start"
            if ap and g2 == 14:
                why += " (the autopilot's second GPS is fed over MAVLink — NAVERA's own output: never used)"
            elif ap and g2 is None:
                why += " (the autopilot's GPS types could not be read: its second GPS is not trusted)"
        rep.append(f"GPS: {out['NAVERA_GPS_SOURCE']} — {why}")
    # camera
    if auto("NAVERA_CAMERA_INPUT"):
        written = get("NAVERA_CAMERA_DEVICE")
        if written:
            out["NAVERA_CAMERA_INPUT"], why = "usb", f"the device written in navera.env ({written})"
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
            rep.append(f"output: NAVERA's position to the autopilot over MAVLink ({ap['url']}, system {ap['sysid']})")
    # ROS vehicle: publish /navera/fix on its graph
    if ros_domain is not None:
        if join_domain:
            out.update(ROS_DOMAIN_ID=str(ros_domain), ROS_LOCALHOST_ONLY="0")
        if "NAVERA_ROS_FIX_TOPIC" not in env:
            out["NAVERA_ROS_FIX_TOPIC"] = "/navera/fix"
        rep.append(f"output: /navera/fix (sensor_msgs/NavSatFix) on ROS domain {ros_domain}")
    if not ap and ros_domain is None:
        rep.append("output: no autopilot and no ROS vehicle found — set NAVERA_NMEA_PORT for an NMEA GPS input")
    return {"settings": out, "report": rep}


def write_env(settings: dict, path: str) -> None:
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write("# Written at boot by navera-discover (navera_common.discovery): what was found.\n"
                "# Only for settings left to auto in /etc/navera/navera.env. Do not edit.\n")
        for k in sorted(settings):
            v = str(settings[k])
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", k) or re.search(r"[\x00-\x1f\x7f]", v):
                continue
            f.write(f"{k}={v}\n")
    os.replace(tmp, path)


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
        tmp = f"{a.json_out}.tmp"
        with open(tmp, "w") as f:
            json.dump(dict(found=found, settings=d["settings"], report=d["report"]), f, indent=1, default=str)
        os.replace(tmp, a.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
