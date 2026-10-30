#!/usr/bin/env python3
"""navera_wifi.py — the box's Wi-Fi: on the client's network when it can, its own setup Wi-Fi when not.

The box has one Wi-Fi card, which is either a client of a network or a hotspot, not both. So:

1. At boot NetworkManager joins a saved network (the client's Wi-Fi, entered once on the setup
   page). Connected → the box has internet (map downloads, IRIS maintenance) and NAVERA's page is
   open to every device on that network (http://<hostname>.local:8181/).
2. Not connected within NAVERA_WIFI_JOIN_S (default 45 s) → the setup hotspot comes up: name
   NAVERA_WIFI_SSID / password NAVERA_WIFI_PASSWORD, the same on every box (the access card's QR
   code). A phone that joins it gets the setup page by itself (captive portal, navera_portal.py):
   the networks the box can see, a password field, and the link to NAVERA's page (in the field,
   without any other Wi-Fi, NAVERA is used right there).
3. The page drops a request in NAVERA_WIFI_SPOOL (the navera user may write there; this service
   runs as root); the request is applied here: the network is saved, the hotspot goes down, the
   box joins. Joined → status "connected" with the address; failed → hotspot back, status
   "failed: <reason>". While the hotspot is up with nobody on it (no phone seen on it for
   NAVERA_WIFI_CLIENT_HOLD_S, default 300 s), the saved networks are tried again every
   NAVERA_WIFI_RETRY_S (default 300 s).

    sudo navera_wifi.py            # the service loop (navera-wifi.service)
    navera_wifi.py --once-status   # print the state file
Settings from /etc/navera/navera.env (see navera.env.example, "Access").
"""
import grp
import json
import os
import tempfile
import re
import subprocess
import sys
import time

HOTSPOT = "navera-hotspot"
CLIENT_PREFIX = "navera-wifi-"
SPOOL = os.environ.get("NAVERA_WIFI_SPOOL", "/var/lib/navera/wifi")
STATE = os.path.join(SPOOL, "state.json")
REQUEST = os.path.join(SPOOL, "request.json")
SCAN = os.path.join(SPOOL, "scan.json")
HOTSPOT_SH = os.environ.get("NAVERA_HOTSPOT_SH", "/usr/local/sbin/navera_hotspot.sh")
# A phone seen on the hotspot within this long keeps the hotspot up (no saved-network retry): a
# phone between two "station dump"s, or asleep a moment, is still someone using the setup page.
CLIENT_HOLD_S = float(os.environ.get("NAVERA_WIFI_CLIENT_HOLD_S", "300"))
_last_client = [0.0]         # time.time() a station was last seen on the hotspot
SSID_RE = re.compile(r"^[^\x00-\x1f]{1,32}$")


def nmcli(*args, timeout=60):
    """(exit code, output) of nmcli; a hung or missing nmcli is an error, never an exception."""
    try:
        p = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"nmcli timed out after {timeout} s"
    except OSError as e:
        return 127, f"nmcli: {e}"
    return p.returncode, (p.stdout + p.stderr).strip()


def wifi_iface() -> str:
    if os.environ.get("NAVERA_WIFI_IFACE"):
        return os.environ["NAVERA_WIFI_IFACE"]
    _, out = nmcli("-t", "-f", "DEVICE,TYPE", "dev")
    for line in out.splitlines():
        dev, _, typ = line.partition(":")
        if typ == "wifi":
            return dev
    return ""


def active_connection(dev: str) -> str:
    _, out = nmcli("-t", "-f", "GENERAL.CONNECTION,GENERAL.STATE", "dev", "show", dev)
    con = state = ""
    for line in out.splitlines():
        k, _, v = line.partition(":")
        if k == "GENERAL.CONNECTION":
            con = v
        elif k == "GENERAL.STATE":
            state = v
    return con if state.startswith("100") else ""


def address(dev: str) -> str:
    _, out = nmcli("-t", "-f", "IP4.ADDRESS", "dev", "show", dev)
    for line in out.splitlines():
        if ":" in line:
            return line.split(":", 1)[1].split("/")[0]
    return ""


def write_json(path: str, obj):
    # the spool is writable by the navera user: a fresh private temp file, never a fixed name
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".w")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def read_request() -> dict:
    """The setup page's request (a regular file, not a link), removed once read."""
    try:
        fd = os.open(REQUEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        try:
            os.unlink(REQUEST)
        except OSError:
            pass
        return {}
    try:
        with os.fdopen(fd) as f:
            req = json.loads(f.read(4096)) if os.fstat(f.fileno()).st_size <= 4096 else {}
    except (OSError, ValueError):
        req = {}
    try:
        os.unlink(REQUEST)
    except OSError:
        pass
    return req if isinstance(req, dict) else {}


def set_state(**kw):
    kw["t"] = time.time()
    write_json(STATE, kw)


def scan(dev: str):
    """The networks in range (only possible while not a hotspot), strongest first."""
    nmcli("dev", "wifi", "rescan", "ifname", dev, timeout=20)
    time.sleep(3)
    _, out = nmcli("-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", dev, timeout=20)
    seen = {}
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3 or not parts[0]:
            continue
        ssid = parts[0].replace("\\:", ":")
        sig = int(parts[1]) if parts[1].isdigit() else 0
        if ssid not in seen or sig > seen[ssid]["signal"]:
            seen[ssid] = {"ssid": ssid, "signal": sig, "secure": parts[2] not in ("", "--")}
    nets = sorted(seen.values(), key=lambda n: -n["signal"])
    write_json(SCAN, {"t": time.time(), "networks": nets})
    return nets


def hotspot(on: bool):
    try:
        subprocess.run([HOTSPOT_SH] if on else [HOTSPOT_SH, "--stop"], capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as e:
        log(f"hotspot {'start' if on else 'stop'} failed: {e}")


HOTSPOT_CHECK_S = 30.0    # the hotspot must be really up within this, else it is started again


def log(msg: str):
    print(f"navera_wifi: {msg}", file=sys.stderr, flush=True)


def ensure_hotspot(dev: str, within_s: float = HOTSPOT_CHECK_S) -> bool:
    """Start the hotspot and check its connection is really active on dev; started again
    (every 10 s) until it is, for at most within_s. True when it is up."""
    end = time.time() + within_s
    while True:
        hotspot(True)
        t_retry = min(end, time.time() + 10.0)
        while time.time() < t_retry:
            if active_connection(dev) == HOTSPOT:
                return True
            time.sleep(2)
        if time.time() >= end:
            log(f"the hotspot is not up after {within_s:.0f} s")
            return False


def try_saved(dev: str, wait_s: float) -> str:
    """Bring up the saved client networks (NetworkManager picks); the connection name or ''."""
    hotspot(False)
    nmcli("dev", "set", dev, "autoconnect", "yes")
    nmcli("dev", "connect", dev, timeout=int(wait_s) + 5)
    end = time.time() + wait_s
    while time.time() < end:
        con = active_connection(dev)
        if con and con != HOTSPOT:
            return con
        time.sleep(2)
    return ""


def apply_request(dev: str, req: dict) -> str:
    """Save and join the network of a setup-page request; '' on success, else the reason."""
    ssid, password = str(req.get("ssid", "")), str(req.get("password", ""))
    if not SSID_RE.match(ssid):
        return "invalid network name"
    if password and not 8 <= len(password) <= 63:
        return "the password must have 8 to 63 characters"
    name = CLIENT_PREFIX + re.sub(r"[^A-Za-z0-9_.-]", "_", ssid)[:40]
    # a saved, working profile of the same name stays until the new one has joined: the new one
    # is added under a temporary name and takes the name only on success
    new = name + "-new"
    nmcli("con", "delete", new)
    hotspot(False)
    add = ["con", "add", "type", "wifi", "ifname", dev, "con-name", new, "ssid", ssid,
           "connection.autoconnect", "yes", "connection.autoconnect-priority", "50"]
    if password:
        add += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
    code, out = nmcli(*add)
    if code != 0:
        return f"not saved: {out[-200:]}"
    code, out = nmcli("con", "up", new, timeout=60)
    if code != 0:
        nmcli("con", "delete", new)
        return "could not join (wrong password, or the network is out of range)"
    nmcli("con", "delete", name)                       # the old profile, if any (not the active one)
    nmcli("con", "modify", new, "connection.id", name)
    return ""


def main_loop():
    os.makedirs(SPOOL, exist_ok=True)
    try:                      # the portal (navera user) drops requests; this root service reads them
        os.chown(SPOOL, 0, grp.getgrnam(os.environ.get("NAVERA_WIFI_GROUP", "navera")).gr_gid)
        os.chmod(SPOOL, 0o1770)
    except KeyError:
        os.chmod(SPOOL, 0o1777)
    join_s = float(os.environ.get("NAVERA_WIFI_JOIN_S", "45"))
    retry_s = float(os.environ.get("NAVERA_WIFI_RETRY_S", "300"))
    dev = ""
    while not dev:
        dev = wifi_iface()
        if not dev:
            set_state(mode="no-wifi", message="no Wi-Fi card found")
            time.sleep(10)
    scan(dev)
    con = try_saved(dev, join_s)
    mode, last_try = ("client", 0.0) if con else ("hotspot", time.time())
    if mode == "hotspot":
        ensure_hotspot(dev)
    last_fail = ""
    while True:
        try:
            mode, last_try, last_fail = step(dev, mode, last_try, last_fail, join_s, retry_s)
        except Exception as e:      # noqa: BLE001 — one bad turn (nmcli, a file) never stops the service
            log(f"error, carrying on: {e!r}")
        time.sleep(5)


def step(dev, mode, last_try, last_fail, join_s, retry_s):
    """One turn of the main loop; the new (mode, last_try, last_fail)."""
    if os.path.lexists(REQUEST):
        req = read_request()
        set_state(mode="joining", ssid=str(req.get("ssid", ""))[:32], message="joining")
        reason = apply_request(dev, req)
        if reason:
            last_fail = reason
            mode = "hotspot"
            ensure_hotspot(dev)
        else:
            last_fail, mode = "", "client"
    con = active_connection(dev)
    if mode == "hotspot" and hotspot_clients(dev):
        _last_client[0] = time.time()          # someone is on the setup Wi-Fi
    if mode == "client" and not (con and con != HOTSPOT):
        con = try_saved(dev, join_s)            # lost the client network: try again, else hotspot
        if not con:
            scan(dev)
            mode, last_try = "hotspot", time.time()
            ensure_hotspot(dev)
    elif mode == "hotspot" and time.time() - last_try > retry_s and time.time() - _last_client[0] > CLIENT_HOLD_S:
        last_try = time.time()
        if saved_networks():
            con = try_saved(dev, join_s)
            if con:
                mode = "client"
            else:
                scan(dev)
                ensure_hotspot(dev)
    elif mode == "hotspot" and con != HOTSPOT:   # the hotspot fell (or never came up): again
        ensure_hotspot(dev)
    if mode == "client":
        set_state(mode="client", ssid=con, address=address(dev), hostname=os.uname().nodename)
    else:
        set_state(mode="hotspot", ssid=os.environ.get("NAVERA_WIFI_SSID", "NAVERA"),
                  address=address(dev), message=last_fail, hostname=os.uname().nodename)
    return mode, last_try, last_fail


def saved_networks():
    _, out = nmcli("-t", "-f", "NAME,TYPE", "con", "show")
    return [ln.split(":")[0] for ln in out.splitlines()
            if ln.endswith(":802-11-wireless") and not ln.startswith(HOTSPOT + ":")]


def hotspot_clients(dev: str) -> int:
    try:
        p = subprocess.run(["iw", "dev", dev, "station", "dump"], capture_output=True, text=True, timeout=10)
        return p.stdout.count("Station ")
    except (OSError, subprocess.SubprocessError):
        return 0


def main() -> int:
    if sys.argv[1:] == ["--once-status"]:
        try:
            print(open(STATE).read())
        except OSError:
            print("{}")
        return 0
    main_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
