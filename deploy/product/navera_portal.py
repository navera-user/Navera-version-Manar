#!/usr/bin/env python3
"""navera_portal.py — the box's Wi-Fi setup page (captive portal).

A phone that scans the access card's QR code joins the box's setup Wi-Fi; every web address
then leads here (navera_hotspot.sh: DNS; navera_firewall.sh: port 80), so the phone shows this
page by itself (its "am I online?" checks are answered "captive" until the page has been shown
on that phone, then "online" for 10 min, so the phone keeps the setup Wi-Fi). On it: the
networks the box sees, a password field to put the box on the client's own Wi-Fi (internet for
map downloads and IRIS maintenance; navera_wifi.py applies it), the box's current
state, and the link to NAVERA's page. Standard library only.

    navera_portal.py      # NAVERA_PORTAL_PORT (default 8182), NAVERA_WIFI_SPOOL, NAVERA_WEB_PORT
"""
import html
import http.server
import ipaddress
import json
import os
import sys
import threading
import time
from urllib.parse import parse_qs

SPOOL = os.environ.get("NAVERA_WIFI_SPOOL", "/var/lib/navera/wifi")
MAX_FORM = 4096

# Phones' "am I online?" checks (path -> the answer meaning "online"). Until a phone has shown the
# setup page they get the page (= "captive": the phone opens it by itself); once it has, they get
# the online answer, so the phone keeps the box's Wi-Fi (no switch to mobile data, the
# mini-browser stays open). Hosts: connectivitycheck.gstatic.com / clients3.google.com (Android),
# captive.apple.com (iOS, macOS), www.msftconnecttest.com / www.msftncsi.com (Windows).
APPLE_OK = b"<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"
PROBES = {
    "/generate_204": (204, b"", "text/plain"),
    "/gen_204": (204, b"", "text/plain"),
    "/hotspot-detect.html": (200, APPLE_OK, "text/html"),
    "/library/test/success.html": (200, APPLE_OK, "text/html"),
    "/connecttest.txt": (200, b"Microsoft Connect Test", "text/plain"),
    "/ncsi.txt": (200, b"Microsoft NCSI", "text/plain"),
}
SEEN_PATH = "/_navera_seen.gif"     # a 1-pixel image in the setup page: only a browser that drew the
SEEN_TTL_S = 4 * 3600.0             # page loads it (the phone's online checks never do)
SEEN_MAX = 256                      # clients remembered at most (oldest forgotten first)
GIF = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
       b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


class SeenClients:
    """Client IPs that were shown the setup page, each for `ttl_s`; at most `max_n` remembered."""

    def __init__(self, ttl_s: float = SEEN_TTL_S, max_n: int = SEEN_MAX, clock=time.monotonic):
        self.ttl_s, self.max_n, self.clock = ttl_s, max_n, clock
        self._t = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(ip: str) -> str:
        try:
            a = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            return ip
        return str(a.ipv4_mapped if a.version == 6 and a.ipv4_mapped else a)

    def mark(self, ip: str):
        now, k = self.clock(), self._key(ip)
        with self._lock:
            self._t.pop(k, None)
            self._t[k] = now                    # dict order = age order: re-marked goes last
            for old in [c for c, t in self._t.items() if now - t > self.ttl_s]:
                del self._t[old]
            while len(self._t) > self.max_n:
                del self._t[next(iter(self._t))]

    def seen(self, ip: str) -> bool:
        with self._lock:
            t = self._t.get(self._key(ip))
            return t is not None and self.clock() - t <= self.ttl_s

    def __len__(self):
        return len(self._t)


STYLE = """
:root { --ink:#13202b; --muted:#5b6b78; --line:#d5dde3; --bg:#f6f8fa; --card:#fff; --accent:#0b6bcb; --bad:#b42318; }
@media (prefers-color-scheme: dark) { :root { --ink:#e6edf3; --muted:#9aa7b2; --line:#30363d; --bg:#0d1117;
  --card:#161b22; --accent:#4c9aff; --bad:#ff7b72; } }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, sans-serif; background:var(--bg); color:var(--ink); }
main { max-width: 480px; margin: 0 auto; padding: 16px; }
h1 { font-size: 22px; margin: 8px 0 4px; } .muted { color: var(--muted); font-size: 14px; }
section { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin: 14px 0; }
label { display:block; font-weight:600; margin: 10px 0 6px; }
select, input { width:100%; font-size:16px; padding:12px; border:1px solid var(--line); border-radius:8px;
  background: var(--card); color: var(--ink); }
button, .btn { display:block; width:100%; margin-top:14px; padding:14px; font-size:16px; font-weight:600; border:0;
  border-radius:8px; background:var(--accent); color:#fff; text-align:center; text-decoration:none; }
.bad { color: var(--bad); }
"""


def read_json(name: str) -> dict:
    try:
        with open(os.path.join(SPOOL, name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def web_url(env=os.environ) -> str:
    addr = env.get("NAVERA_WIFI_ADDRESS", "10.42.0.1/24").split("/")[0]
    return f"http://{addr}:{env.get('NAVERA_WEB_PORT', '8181')}/"


def from_hotspot(client: str, env=os.environ) -> bool:
    """True when the box is in hotspot mode (navera_wifi.py's state.json) and `client` is on the
    hotspot's subnet (NAVERA_WIFI_ADDRESS): nobody on a client Wi-Fi can change the box's Wi-Fi."""
    if read_json("state.json").get("mode") != "hotspot":
        return False
    try:
        net = ipaddress.ip_interface(env.get("NAVERA_WIFI_ADDRESS", "") or "10.42.0.1/24").network
        ip = ipaddress.ip_address(client.split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.version == net.version and ip in net


def box_hostname(state=None, env=os.environ) -> str:
    """The box's name on the client's Wi-Fi (http://<name>.local): navera_wifi.py's state, else
    NAVERA_HOSTNAME, else navera."""
    state = read_json("state.json") if state is None else state
    return str(state.get("hostname") or env.get("NAVERA_HOSTNAME") or "navera")


def page(body: str) -> bytes:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>NAVERA setup</title>"
            f"<style>{STYLE}</style></head><body><main>{body}</main></body></html>").encode()


def setup_page() -> bytes:
    e = html.escape
    state, nets = read_json("state.json"), read_json("scan.json").get("networks", [])
    port = os.environ.get("NAVERA_WEB_PORT", "8181")
    if state.get("mode") == "client":
        now = (f"Connected to <b>{e(state.get('ssid', ''))}</b>. On that Wi-Fi, NAVERA is at "
               f"<b>http://{e(box_hostname(state))}.local:{e(port)}/</b> "
               f"or <b>http://{e(state.get('address', ''))}:{e(port)}/</b>.")
    elif state.get("message"):
        now = f"<span class='bad'>Last try: {e(state['message'])}</span>"
    else:
        now = "Not connected to the internet yet."
    options = "".join(f"<option value='{e(n['ssid'])}'>{e(n['ssid'])} ({n['signal']} %)</option>" for n in nets)
    options += "<option value=''>Other (type the name below)</option>"
    return page(f"""
<h1>NAVERA</h1><p class="muted">IRIS Systems</p>
<section><a class="btn" href="{e(web_url())}">Open NAVERA</a>
<p class="muted">Works right here, without internet.</p></section>
<section><h2 style="font-size:18px;margin:0">Connect the box to your Wi-Fi</h2>
<p class="muted">For map downloads and IRIS support. {now}</p>
<form method="post" action="/wifi">
<label for="ssid">Network</label><select id="ssid" name="ssid">{options}</select>
<label for="other">Other network name</label><input id="other" name="other" maxlength="32" autocomplete="off">
<label for="password">Password</label><input id="password" name="password" type="password" maxlength="63">
<button type="submit">Connect</button></form></section>
<img src="{SEEN_PATH}" width="1" height="1" alt="" style="position:absolute;left:-9px">""")


def joining_page(ssid: str) -> bytes:
    e = html.escape
    port = os.environ.get("NAVERA_WEB_PORT", "8181")
    return page(f"""
<h1>Connecting to {e(ssid)}…</h1>
<section><p>The box now leaves this setup Wi-Fi and joins <b>{e(ssid)}</b> (about 30 seconds).</p>
<ol><li>Put your phone back on <b>{e(ssid)}</b>.</li>
<li>Open <b>http://{e(box_hostname())}.local:{e(port)}/</b> — everyone on that Wi-Fi can.</li></ol>
<p class="muted">If the box cannot join (wrong password), the setup Wi-Fi comes back: scan the QR code
again and this page shows the reason.</p></section>""")


BOX_ADDR = os.environ.get("NAVERA_WIFI_ADDRESS", "10.42.0.1/24").split("/")[0]
PORTAL_LOG = os.environ.get("NAVERA_PORTAL_LOG", "")      # diagnostics: one line per request


def _log(client, host, path, agent):
    if not PORTAL_LOG:
        return
    try:
        with open(PORTAL_LOG, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {client} {host}{path} {agent[:60]}\n")
    except OSError:
        pass


def make_handler(seen=None):
    seen = SeenClients() if seen is None else seen

    class Portal(http.server.BaseHTTPRequestHandler):
        server_version = "NAVERA"
        sys_version = ""

        def log_message(self, fmt, *args):
            pass

        def _client(self) -> str:
            return self.client_address[0] if self.client_address else ""

        def _send(self, code: int, body: bytes, headers=(), ctype="text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if code != 204:                     # a 204 carries no body nor its length
                self.send_header("Content-Length", str(len(body)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD" and body:
                self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == SEEN_PATH:               # the setup page is on this client's screen
                seen.mark(self._client())
                return self._send(200, GIF, ctype="image/gif")
            probe = PROBES.get(path)
            host = (self.headers.get("Host") or "").split(":")[0]
            _log(self._client(), host, path, self.headers.get("User-Agent", ""))
            if probe and seen.seen(self._client()):
                code, body, ctype = probe        # page already shown: tell the phone it is online
                return self._send(code, body, ctype=ctype)
            if host and host != BOX_ADDR:
                # any other site (a phone's online check, a page the user had open): redirect to the
                # box, the answer phones read as "sign-in Wi-Fi" and open by themselves
                return self._send(302, b"", [("Location", f"http://{BOX_ADDR}/")])
            self._send(200, setup_page())

        do_HEAD = do_GET

        def do_POST(self):
            if self.path.split("?")[0] != "/wifi":
                return self._send(303, b"", [("Location", "/")])
            seen.mark(self._client())
            if not from_hotspot(self._client()):
                return self._send(403, page("<p class='bad'>The Wi-Fi is changed only from the box's setup Wi-Fi."
                                            "</p><a href='/'>Back</a>"))
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= MAX_FORM:
                return self._send(413, page("<p>Request too large.</p>"))
            form = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
            ssid = (form.get("other", [""])[0].strip() or form.get("ssid", [""])[0]).strip()
            password = form.get("password", [""])[0]
            if not 1 <= len(ssid.encode()) <= 32:
                return self._send(400, page("<p class='bad'>Choose or type a network name.</p><a href='/'>Back</a>"))
            if password and not 8 <= len(password) <= 63:
                return self._send(400, page("<p class='bad'>A Wi-Fi password has 8 to 63 characters.</p>"
                                            "<a href='/'>Back</a>"))
            req = os.path.join(SPOOL, "request.json")
            tmp = f"{req}.{os.getpid()}.{time.monotonic_ns()}"
            with open(tmp, "w") as f:
                json.dump({"ssid": ssid, "password": password, "t": time.time()}, f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, req)
            self._send(200, joining_page(ssid))

    return Portal


def main() -> int:
    port = int(os.environ.get("NAVERA_PORTAL_PORT", "8182"))
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), make_handler())
    print(f"navera_portal: setup page on :{port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
