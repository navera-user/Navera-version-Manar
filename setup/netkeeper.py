#!/usr/bin/env python3
"""NAVERA network keeper — first-time Wi-Fi setup without cables, screen or keyboard.

At power-on it waits for a known Wi-Fi. If none comes, the Jetson opens its own Wi-Fi
"NAVERA-Setup-XXXX"; every address typed on it shows the setup page (http://navera.setup):
the client picks their Wi-Fi, types the password, and the Jetson joins it. If that fails (wrong
password) or the Wi-Fi disappears later, the setup Wi-Fi comes back by itself.

While connected it publishes the local name navera-academy.local and sends port 80 to the academy.

    sudo python3 netkeeper.py                 # the service (installed by install.sh)
    python3 netkeeper.py --preview --port 8099   # only the setup page, fake networks, no network change
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# Flask is installed for the academy's owner (~/.local), not for root: use the owner's packages too
_owner_home = __import__("pwd").getpwuid(os.stat(HERE).st_uid).pw_dir
sys.path.append(os.path.join(_owner_home, ".local/lib/python%d.%d/site-packages" % sys.version_info[:2]))
STATE_DIR = "/var/lib/navera-setup"
CONF = "/etc/navera/setup.json"            # {"ssid": "NAVERA-Setup-0CE9", "password": "…", "public_url": "…"}
AP_CON = "navera-setup"
CLIENT_CON = "navera-client"
AP_IP = "10.42.0.1"
LOCAL_NAME = "navera-academy.local"
ACADEMY_PORT = 8300
PORTAL_HOST = "navera.setup"
WAIT_AT_BOOT_S = 75                        # time for a known Wi-Fi to come back after power-on
LOST_BEFORE_SETUP_S = 120                  # Wi-Fi gone this long → setup mode

state = {"mode": "starting", "networks": [], "last_error": "", "connecting": None, "iface": None}
lock = threading.Lock()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def sh(cmd, timeout=60, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)}: {r.stderr.strip() or r.stdout.strip()}")
    return r


def conf():
    try:
        with open(CONF) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ------------------------------------------------------------------ Wi-Fi helpers (NetworkManager)
def wifi_iface():
    for line in sh(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"]).stdout.splitlines():
        dev, typ = line.split(":")[:2]
        if typ == "wifi":
            return dev
    return None


def connected():
    """True when the Wi-Fi is connected to a network that is not our own setup Wi-Fi."""
    out = sh(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"]).stdout
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] == state["iface"]:
            return parts[1] == "connected" and parts[2] != AP_CON
    return False


def current_ip():
    out = sh(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", state["iface"]]).stdout
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)/", out)
    return m.group(1) if m else None


def scan():
    sh(["nmcli", "device", "wifi", "rescan", "ifname", state["iface"]], timeout=30)
    time.sleep(4)
    out = sh(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", state["iface"]], timeout=30).stdout
    best = {}
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3 or not parts[0]:
            continue
        ssid = parts[0].replace("\\:", ":")
        if ssid.startswith("NAVERA-Setup"):
            continue
        sig = int(parts[1] or 0)
        if ssid not in best or sig > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": sig, "secure": parts[2] not in ("", "--")}
    return sorted(best.values(), key=lambda n: -n["signal"])


def start_ap():
    c = conf()
    sh(["nmcli", "connection", "delete", AP_CON])
    sh(["nmcli", "connection", "add", "type", "wifi", "ifname", state["iface"], "con-name", AP_CON, "autoconnect", "no",
        "ssid", c["ssid"], "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
        "ipv4.method", "shared", "ipv4.addresses", f"{AP_IP}/24", "ipv6.method", "disabled",
        "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", c["password"]], check=True)
    sh(["nmcli", "connection", "up", AP_CON], timeout=60, check=True)
    log("setup Wi-Fi up:", c["ssid"])


def stop_ap():
    sh(["nmcli", "connection", "down", AP_CON])


# ------------------------------------------------------------------ connected-mode extras
_avahi = None


def connected_extras(on):
    """navera-academy.local on the client's network, and port 80 → the academy."""
    global _avahi
    rule = ["PREROUTING", "-i", state["iface"], "-p", "tcp", "--dport", "80", "-j", "REDIRECT", "--to-ports", str(ACADEMY_PORT)]
    if on:
        if sh(["iptables", "-t", "nat", "-C"] + rule).returncode:
            r = sh(["iptables", "-t", "nat", "-A"] + rule)
            if r.returncode and not getattr(connected_extras, "warned", False):
                connected_extras.warned = True
                log("port-80 rule not set (the setup page redirects instead):", r.stderr.strip()[:200])
        ip = current_ip()
        if ip and (_avahi is None or _avahi.poll() is not None or getattr(_avahi, "ip", None) != ip):
            if _avahi and _avahi.poll() is None:
                _avahi.terminate()
            _avahi = subprocess.Popen(["avahi-publish", "-a", "-R", LOCAL_NAME, ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _avahi.ip = ip
            log(f"{LOCAL_NAME} → {ip}")
    else:
        while sh(["iptables", "-t", "nat", "-D"] + rule).returncode == 0:
            pass
        if _avahi and _avahi.poll() is None:
            _avahi.terminate()


# ------------------------------------------------------------------ connecting to the client's Wi-Fi
def try_connect(ssid, password):
    with lock:
        state["mode"] = "connecting"
    log("connecting to", ssid)
    time.sleep(3)                                   # let the page answer before the setup Wi-Fi goes down
    stop_ap()
    sh(["nmcli", "connection", "delete", CLIENT_CON])
    cmd = ["nmcli", "device", "wifi", "connect", ssid, "ifname", state["iface"], "name", CLIENT_CON]
    if password:
        cmd += ["password", password]
    r = sh(cmd, timeout=60)
    ok = r.returncode == 0
    for _ in range(20):
        if ok and connected():
            break
        time.sleep(2)
    if ok and connected():
        sh(["nmcli", "connection", "modify", CLIENT_CON, "connection.autoconnect", "yes", "connection.autoconnect-priority", "10"])
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "state.json"), "w") as f:
            json.dump({"ssid": ssid, "since": time.strftime("%Y-%m-%d %H:%M")}, f)
        with lock:
            state.update(mode="connected", last_error="", connecting=None)
        connected_extras(True)
        log("connected to", ssid)
        return
    sh(["nmcli", "connection", "delete", CLIENT_CON])
    err = (r.stderr or r.stdout or "").strip()
    reason = "wrong Wi-Fi password" if re.search(r"secret|password|802-1x|auth", err, re.I) else "could not join this Wi-Fi"
    with lock:
        state.update(last_error=f"Could not connect to “{ssid}”: {reason}. Please try again.", connecting=None)
    log("failed:", err[:200])
    enter_setup()


def enter_setup():
    connected_extras(False)
    with lock:
        state["mode"] = "setup"
    try:
        state["networks"] = scan()
    except Exception as e:
        log("scan failed:", e)
    start_ap()


# ------------------------------------------------------------------ the setup page
def make_portal(preview=False):
    from flask import Flask, jsonify, redirect, request, send_from_directory
    app = Flask(__name__, static_folder=os.path.join(HERE, "portal"), static_url_path="/s")
    captive = {"/generate_204", "/gen_204", "/hotspot-detect.html", "/library/test/success.html", "/connecttest.txt",
               "/ncsi.txt", "/canonical.html", "/success.txt", "/redirect", "/check_network_status.txt"}

    @app.before_request
    def to_portal():
        with lock:
            mode = state["mode"]
        if not preview and mode != "setup":
            # on the client's network: whatever the port-80 rule does, send visitors to the academy itself
            host = request.host.split(":")[0]
            return redirect(f"http://{host}:{ACADEMY_PORT}{request.full_path.rstrip('?')}", code=302)
        # phones test the internet with these addresses: answering with our page opens the setup page by itself
        if request.path in captive or (not preview and request.host.split(":")[0] not in (PORTAL_HOST, AP_IP)):
            return redirect(f"http://{PORTAL_HOST}/", code=302)

    @app.get("/")
    def page():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/state")
    def api_state():
        c = conf()
        with lock:
            return jsonify(mode=state["mode"], networks=state["networks"], error=state["last_error"],
                           local_url=f"http://{LOCAL_NAME}", public_url=c.get("public_url", ""))

    @app.post("/api/rescan")
    def api_rescan():
        if preview:
            return jsonify(ok=True)
        # the radio is busy being a hotspot: a fresh scan needs a short pause of the setup Wi-Fi
        def job():
            stop_ap()
            try:
                state["networks"] = scan()
            finally:
                start_ap()
        threading.Thread(target=job, daemon=True).start()
        return jsonify(ok=True, note="The setup Wi-Fi restarts for a few seconds: reconnect to it if your phone leaves it.")

    @app.post("/api/connect")
    def api_connect():
        d = request.get_json(force=True)
        ssid = (d.get("ssid") or "").strip()
        pw = d.get("password") or ""
        if not ssid or len(ssid) > 32:
            return jsonify(error="Choose a Wi-Fi network."), 400
        if pw and not 8 <= len(pw) <= 63:
            return jsonify(error="A Wi-Fi password has 8 to 63 characters."), 400
        if preview:
            with lock:
                state["last_error"] = ""
            return jsonify(ok=True)
        with lock:
            if state["mode"] != "setup":                     # only while the setup Wi-Fi is open
                return jsonify(error="The device is not in setup mode."), 409
        threading.Thread(target=try_connect, args=(ssid, pw), daemon=True).start()
        return jsonify(ok=True)

    return app


# ------------------------------------------------------------------ main loop
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="only the setup page, fake networks, no network change")
    ap.add_argument("--port", type=int, default=80)
    a = ap.parse_args()
    if a.preview:
        state.update(mode="setup", networks=[{"ssid": "Client-Office", "signal": 82, "secure": True},
                                             {"ssid": "Client-Guests", "signal": 64, "secure": True},
                                             {"ssid": "Meeting room", "signal": 41, "secure": False}])
        make_portal(preview=True).run(host="0.0.0.0", port=a.port, threaded=True)
        return
    if os.geteuid() != 0:
        sys.exit("run as root (the service does): the Wi-Fi settings need it")
    state["iface"] = wifi_iface()
    if not state["iface"]:
        sys.exit("no Wi-Fi device")
    def portal():
        try:
            make_portal().run(host="0.0.0.0", port=a.port, threaded=True)
        except BaseException as e:                  # no setup page = useless keeper: let systemd restart us
            log("setup page failed:", e)
            os._exit(1)
    threading.Thread(target=portal, daemon=True).start()
    log("waiting for a known Wi-Fi…")
    t0 = time.time()
    while time.time() - t0 < WAIT_AT_BOOT_S and not connected():
        time.sleep(3)
    if connected():
        state["mode"] = "connected"
        connected_extras(True)
    else:
        enter_setup()
    lost_since = None
    while True:
        time.sleep(10)
        with lock:
            mode = state["mode"]
        if mode == "connected":
            if connected():
                lost_since = None
                connected_extras(True)              # follows a new IP address
            else:
                lost_since = lost_since or time.time()
                if time.time() - lost_since > LOST_BEFORE_SETUP_S:
                    log("Wi-Fi lost → setup mode")
                    lost_since = None
                    enter_setup()
        elif mode == "setup" and connected():       # a known Wi-Fi came back by itself
            stop_ap()
            state["mode"] = "connected"
            connected_extras(True)


if __name__ == "__main__":
    main()
