"""Hot-plug: a device connected after boot fills a source NAVERA left idle.

navera-discover decides the sources once per boot. When it found nothing for a need (no GPS,
no autopilot, no camera, no attitude: decide()'s "idle" list), navera-hotplug.service keeps
looking, lightly:

  * every few seconds it lists the devices (serial ports /dev/tty{THS,USB,ACM}*, SocketCAN
    interfaces that are up, USB cameras) and probes only the NEW ones, read-only, exactly as
    discovery does;
  * while a GPS is missing it also listens again, every NAVERA_HOTPLUG_RESCAN_S (default
    60 s), to the CAN buses, the network GPS addresses and the serial ports that answered
    nothing (a GPS powered after the box, a Here3 that got its node id late);

then runs the same decide() on what is now known and writes discovered.env again — but only
the settings of the idle needs: a working source is never changed. The idle units (they wait
in navera_boot_lib.sh::navera_idle_until_discovered) see the new file and restart with it.

The GPS is never switched while the vehicle is armed: with an autopilot link configured, the
GPS need is filled only once the autopilot says it is disarmed (/navera/vehicle/status,
fresh); armed or unknown -> deferred, retried. Without an autopilot there is no armed state:
filled at once (NAVERA's rule: the vehicle has GPS at take-off).

NAVERA_HOTPLUG=0 turns it off (the unit then idles).
"""
import json
import os
import threading
import time
from typing import Callable, Dict, List, Optional

from navera_common import discovery as disc

SLOT_KEYS = {
    "gps": ("NAVERA_GPS_", "NAVERA_ROS_GPS_TOPIC"),
    "autopilot": ("NAVERA_VEHICLE_MAVLINK_URL", "NAVERA_MAVLINK_SYSID", "NAVERA_MAVLINK_URL"),
    "attitude": ("NAVERA_SENSOR_SOURCE", "NAVERA_ROS_IMU_TOPIC", "NAVERA_ROS_ALTITUDE_TOPIC"),
    "camera": ("NAVERA_CAMERA_",),
    "thermal_camera": ("NAVERA_THERMAL_CAMERA_",),
    "star_camera": ("NAVERA_STAR_CAMERA_",),
}
REPORT_PREFIX = {"gps": "GPS:", "attitude": "attitude:", "camera": "camera:", "autopilot": "output:",
                 "thermal_camera": ("thermal camera:", "CHECK thermal camera:"),
                 "star_camera": ("star camera:", "CHECK star camera:")}
CAMERA_SLOTS = ("camera", "thermal_camera", "star_camera")
ARMED_FRESH_S = 5.0


def _in_slot(key: str, slot: str) -> bool:
    return any(key == k or (k.endswith("_") and key.startswith(k)) for k in SLOT_KEYS[slot])


def devices(env) -> Dict[str, List[str]]:
    """What is connected now (names only: cheap enough to list every few seconds)."""
    return {"serial": disc.serial_ports(),
            "can": [c["iface"] for c in disc.can_interfaces() if c["up"]],
            "cameras": disc.probe_cameras().get("usb", []),
            "insta360": disc.probe_insta360()}             # the Insta360 kit: USB id from sysfs, never opened


def added(before: Dict[str, List[str]], now: Dict[str, List[str]]) -> Dict[str, List[str]]:
    return {k: [x for x in now.get(k, []) if x not in set(before.get(k, []))] for k in now}


def probe(new: Dict[str, List[str]], env, rescan: Optional[dict] = None) -> dict:
    """Probe the new devices (and, for a rescan, the given serial ports / CAN buses / network
    GPS addresses) in parallel, read-only: a found fragment in discovery's format.
    """
    rescan = rescan or {}
    frag = {"serial": [], "can": [], "gps_net": [],
            "cameras": {"usb": list(new.get("cameras", [])), "insta360": list(new.get("insta360", []))}}
    if new.get("cameras") or rescan.get("ip_cameras"):
        # what the new cameras are (one frame each, in a child process) and the network cameras
        from navera_common import cameras
        added_usb = [c for c in cameras.usb_cameras() if c["id"] in set(new.get("cameras", []))]
        ip = [c for c in cameras.network_cameras(env) if c.get("kind") == "ip"] if rescan.get("ip_cameras") else []
        frag["cameras"]["list"] = cameras.describe(added_usb + ip)
    ports = dict.fromkeys(new.get("serial", []) + rescan.get("serial", []))
    jobs = [("serial", disc.probe_serial_port, p) for p in ports]
    jobs += [("can", disc.probe_dronecan, b) for b in dict.fromkeys(new.get("can", []) + rescan.get("can", []))]
    jobs += [("gps_net", disc.probe_gps_url, u) for u in rescan.get("gps_net", [])]
    lock = threading.Lock()

    def run(key, fn, arg):
        r = fn(arg)
        if r:
            with lock:
                frag[key].append(r)
    threads = [threading.Thread(target=run, args=j, daemon=True) for j in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return frag


def merge(found: dict, frag: dict) -> dict:
    """Return found with the fragment's results replacing those of the same port / bus / address."""
    out = dict(found)
    for key, ident in (("serial", "port"), ("can", "iface"), ("gps_net", "url")):
        new = frag.get(key) or []
        names = {x.get(ident) for x in new}
        out[key] = [x for x in (found.get(key) or []) if x.get(ident) not in names] + new
    cams = dict(found.get("cameras") or {})
    for kind in ("usb", "insta360"):
        cams[kind] = sorted(set(cams.get(kind) or []) | set((frag.get("cameras") or {}).get(kind) or []))
    new = (frag.get("cameras") or {}).get("list") or []
    if new:
        ids = {c["id"] for c in new}
        cams["list"] = [c for c in cams.get("list") or [] if c.get("id") not in ids] + new
    out["cameras"] = cams
    return out


def gps_switch_allowed(env, settings: dict, armed: Optional[bool]) -> Optional[str]:
    """None when the GPS may be filled now, else why not (armed / armed state unknown)."""
    if armed:
        return "the vehicle is armed"
    link = str(env.get("NAVERA_VEHICLE_MAVLINK_URL", "") or settings.get("NAVERA_VEHICLE_MAVLINK_URL", ""))
    if armed is None and link:
        return "the autopilot's armed state is not known yet"
    return None


def fill_idle(doc: dict, found: dict, env, armed: Optional[bool], stamp: str = "") -> dict:
    """Decide again with what is now known and fill ONLY the idle needs of doc (the last
    discovery.json: found, settings, report, idle). Returns {"settings", "idle", "report":
    new lines, "changed": bool, "deferred": [needs found but not filled yet]}.
    """
    settings = dict(doc.get("settings") or {})
    idle = list(doc.get("idle") or [])
    # the cameras already given a job count as written: a new camera never takes over their job,
    # and an old camera is never given a second one
    busy = {k: v for k, v in settings.items()
            if any(_in_slot(k, slot) for slot in CAMERA_SLOTS if slot not in idle)}
    d = disc.decide(found, {**busy, **env})
    lines, deferred, changed = [], [], False
    for slot in sorted(idle, key=lambda x: x != "autopilot"):     # the link first: it tells "armed"
        if slot in d["idle"]:
            continue                                        # still nothing for it
        if slot == "gps":
            why = gps_switch_allowed(env, {**d["settings"], **settings}, armed)
            if why:
                deferred.append(slot)
                lines.append(f"hot-plug {stamp}: a GPS is there, not switched to: {why} (retried)")
                continue
        before = {k: v for k, v in settings.items() if _in_slot(k, slot)}
        for k in before:
            del settings[k]
        settings.update({k: v for k, v in d["settings"].items() if _in_slot(k, slot)})
        idle.remove(slot)
        changed = changed or before != {k: v for k, v in settings.items() if _in_slot(k, slot)}
        pre = REPORT_PREFIX[slot]
        pre = pre if isinstance(pre, tuple) else (pre,)
        lines += [f"hot-plug {stamp}: {r}" for r in d["report"] if r.startswith(pre)]
    return {"settings": settings, "idle": idle, "report": lines, "changed": changed, "deferred": deferred}


class ArmedWatch:
    """The autopilot's armed state from /navera/vehicle/status (vehicle_link), or None."""

    def __init__(self):
        self.armed, self.t = None, 0.0
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from std_msgs.msg import String
            rclpy.init()
            self.node = rclpy.create_node("navera_hotplug")
            self.node.create_subscription(String, "/navera/vehicle/status", self._on, 10)
            ex = SingleThreadedExecutor()
            ex.add_node(self.node)
            threading.Thread(target=ex.spin, daemon=True).start()
        except Exception:                                   # noqa: BLE001 — no ROS: armed state unknown
            self.node = None

    def _on(self, msg):
        try:
            self.armed, self.t = json.loads(msg.data).get("armed"), time.monotonic()
        except ValueError:
            pass

    def __call__(self) -> Optional[bool]:
        if time.monotonic() - self.t > ARMED_FRESH_S or self.armed is None:
            return None
        return bool(self.armed)


def _save(doc: dict, json_path: str, env_path: str) -> None:
    disc.write_env(doc["settings"], env_path)
    from navera_common.atomic_io import atomic_write_json
    atomic_write_json(json_path, doc, indent=1, default=str)


def run(env, json_path: str, env_path: str, armed: Callable[[], Optional[bool]],
        interval_s: float = 3.0, rescan_s: float = 60.0, log=print, passes: Optional[int] = None) -> None:
    """The hot-plug loop (passes: stop after that many, for tests)."""
    while not os.path.exists(json_path):                    # navera-discover has not finished
        if passes is not None:
            return
        time.sleep(interval_s)
    from navera_common.atomic_io import read_json
    doc = read_json(json_path)
    if doc is None or not isinstance(doc.get("found"), dict):   # damaged report (power cut): start afresh
        log(f"hotplug: {json_path} unreadable or damaged: rescanning from nothing")
        doc = {"found": {}, "settings": {}, "report": []}
    doc.setdefault("settings", {})
    if "idle" not in doc:                                   # a report written before hot-plug existed
        doc["idle"] = disc.decide(doc.get("found") or {}, env).get("idle", [])
    before = devices(env)
    last_rescan = time.monotonic()
    n = 0
    while passes is None or n < passes:
        n += 1
        if doc.get("idle"):
            now = devices(env)
            new = added(before, now)
            rescan = None
            if time.monotonic() - last_rescan >= rescan_s:
                rescan = {}
                if "gps" in doc["idle"]:
                    answered = {s.get("port") for s in doc["found"].get("serial") or []}
                    rescan = {"serial": [p for p in now["serial"] if p not in answered],
                              "can": disc.can_buses(env), "gps_net": disc.gps_urls(env)}
                ip_on = str(env.get("NAVERA_DISCOVER_IP_CAMERAS", "1")).strip().lower()
                ip_on = ip_on not in ("0", "off", "no", "false")
                if ip_on and any(s in doc["idle"] for s in CAMERA_SLOTS):
                    rescan["ip_cameras"] = True             # a network camera powered after the box
                rescan = rescan or None
                last_rescan = time.monotonic()
            if any(new.values()) or rescan:
                if any(new.values()):
                    log(f"hot-plug: new {', '.join(x for v in new.values() for x in v)}")
                frag = probe(new, env, rescan)
                doc["found"] = merge(doc.get("found") or {}, frag)
                aps = disc.autopilots(doc["found"])
                if aps and not (doc["found"].get("autopilot_streams") or {}).get("ATTITUDE") and \
                        ("autopilot" in doc["idle"] or "gps" in doc["idle"]):
                    doc["found"]["autopilot_streams"] = disc.autopilot_streams(aps[0]["url"])
            before = now
            res = fill_idle(doc, doc.get("found") or {}, env, armed(), time.strftime("%H:%M:%S"))
            if res["changed"] or res["report"] != doc.get("_last_hotplug_lines"):
                for line in res["report"]:
                    log(line)
            doc["_last_hotplug_lines"] = res["report"]
            if res["changed"]:
                doc["settings"], doc["idle"] = res["settings"], res["idle"]
                doc["report"] = list(doc.get("report") or []) + [r for r in res["report"] if "not switched" not in r]
                _save(doc, json_path, env_path)
        if passes is None or n < passes:
            time.sleep(interval_s)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Fill NAVERA's idle sources when a device is connected after boot.")
    ap.add_argument("--env-out", default="/var/lib/navera/discovered.env")
    ap.add_argument("--json", default="/var/lib/navera/discovery.json")
    ap.add_argument("--interval", type=float, default=3.0)
    a = ap.parse_args(argv)
    env = dict(os.environ)
    if str(env.get("NAVERA_HOTPLUG", "1")).strip().lower() in ("0", "off", "false", "no"):
        print("hot-plug turned off (NAVERA_HOTPLUG=0)", flush=True)
        while True:
            time.sleep(3600)
    # decide() must see the ROS settings as written (navera_boot_hotplug.sh passes them), and
    # the armed-state subscriber must be on the domain the nodes use (discovered.env's, if any)
    for k in ("ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY"):
        written = os.environ.get(f"NAVERA_WRITTEN_{k}")
        if written is not None:
            env[k] = written
    try:
        with open(a.json) as f:
            ds = json.load(f).get("settings") or {}
        for k in ("ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY"):
            if k in ds:
                os.environ[k] = str(ds[k])
    except (OSError, ValueError):
        pass
    rescan = float(env.get("NAVERA_HOTPLUG_RESCAN_S", "60") or 60)
    run(env, a.json, a.env_out, ArmedWatch(), interval_s=a.interval, rescan_s=rescan,
        log=lambda s: print(s, flush=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
