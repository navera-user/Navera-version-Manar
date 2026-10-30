#!/usr/bin/env python3
"""navera_access_gate.py — the door between the internet and NAVERA's web page.

The public link (navera_remote.sh: a Tailscale Funnel https address, nothing to install for the
viewer) reaches ONLY this gate, on 127.0.0.1. The gate lets a browser in when the link carries
the box's remote key (``?k=<NAVERA_REMOTE_KEY>``, the access card's QR code): it then sets a
cookie and the key leaves the address bar. Without the key, or with a wrong one, nothing of
NAVERA is shown. Repeated wrong keys from one address are slowed down.

Once in, the viewer sees the web page (GET); the controls (POST: mission, settings, restart)
are refused from the internet unless NAVERA_REMOTE_CONTROL=1 — and even then the web page's own
control token is still asked. Standard library only (works on the box offline).

Portal mode (``--portal``): on the box's own Wi-Fi every web address a phone tries is sent to
NAVERA's page, so after scanning the Wi-Fi QR code the phone opens NAVERA by itself (its
"sign in to network" window, like a hotel Wi-Fi). The firewall sends the hotspot's port 80 here.

    navera_access_gate.py --portal             # NAVERA_PORTAL_PORT (default 8182), every network
    navera_access_gate.py                      # settings from the environment:
      NAVERA_REMOTE_KEY        the key in the link (required, >= 16 characters)
      NAVERA_REMOTE_PORT       the gate's port on 127.0.0.1 (default 8190)
      NAVERA_WEB_PORT          the web page it opens (default 8181, on 127.0.0.1)
      NAVERA_REMOTE_CONTROL    1: let control requests through (default 0: view only)
"""
import hmac
import http.client
import http.server
import os
import secrets
import sys
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlparse

COOKIE = "navera_remote"
SESSION_S = 12 * 3600
FAIL_LIMIT = 5             # wrong keys per address ...
FAIL_WINDOW_S = 300        # ... per 5 minutes, then refused until the window passes
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "cookie"}

DENIED_PAGE = (b"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
               b"<title>NAVERA</title><body style='font-family:sans-serif;padding:2em'>"
               b"<h2>NAVERA</h2><p>Open NAVERA with the link or the QR code of the box's access "
               b"card.</p></body>")


class Gate:
    """Sessions and the wrong-key counter (shared by the request threads)."""

    def __init__(self, key: str, web_port: int, control: bool):
        if len(key) < 16:
            raise ValueError("NAVERA_REMOTE_KEY: at least 16 characters")
        self.key, self.web_port, self.control = key, web_port, control
        self._sessions = {}
        self._fails = {}
        self._lock = threading.Lock()

    def key_ok(self, given: str) -> bool:
        return hmac.compare_digest(given.encode(), self.key.encode())

    def blocked(self, who: str, now: float) -> bool:
        with self._lock:
            times = [t for t in self._fails.get(who, []) if now - t < FAIL_WINDOW_S]
            self._fails[who] = times
            return len(times) >= FAIL_LIMIT

    def failed(self, who: str, now: float):
        with self._lock:
            self._fails.setdefault(who, []).append(now)

    def new_session(self, now: float) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._sessions = {s: t for s, t in self._sessions.items() if now - t < SESSION_S}
            self._sessions[sid] = now
        return sid

    def session_ok(self, sid: str, now: float) -> bool:
        with self._lock:
            t = self._sessions.get(sid)
            return t is not None and now - t < SESSION_S


def cookie_value(header: str) -> str:
    for part in (header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value
    return ""


def make_handler(gate: Gate):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "NAVERA"
        sys_version = ""

        def log_message(self, fmt, *args):  # no request log with keys in it
            pass

        def _who(self) -> str:
            # Tailscale Funnel connects from 127.0.0.1 and names the viewer in X-Forwarded-For
            return (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()

        def _send(self, code: int, body: bytes, headers=()):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _admit(self) -> bool:
            """True when the request may reach NAVERA; otherwise the answer is already sent."""
            now = time.monotonic()
            if gate.session_ok(cookie_value(self.headers.get("Cookie")), now):
                return True
            url = urlparse(self.path)
            query = parse_qsl(url.query, keep_blank_values=True)
            given = [v for k, v in query if k == "k"]
            who = self._who()
            if not given:
                self._send(401, DENIED_PAGE)
                return False
            if gate.blocked(who, now):
                self._send(429, DENIED_PAGE, [("Retry-After", str(FAIL_WINDOW_S))])
                return False
            if not gate.key_ok(given[-1]):
                gate.failed(who, now)
                self._send(401, DENIED_PAGE)
                return False
            rest = urlencode([(k, v) for k, v in query if k != "k"])
            target = (url.path or "/") + ("?" + rest if rest else "")
            cookie = (f"{COOKIE}={gate.new_session(now)}; Path=/; Max-Age={SESSION_S}; "
                      "HttpOnly; Secure; SameSite=Strict")
            self._send(303, b"", [("Location", target), ("Set-Cookie", cookie)])
            return False

        def _forward(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            conn = http.client.HTTPConnection("127.0.0.1", gate.web_port, timeout=30)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                r = conn.getresponse()
                data = r.read()
            except OSError:
                return self._send(502, b"NAVERA's web page is not answering (starting?)")
            finally:
                conn.close()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_GET(self):
            if self._admit():
                self._forward()

        do_HEAD = do_GET

        def do_POST(self):
            if not self._admit():
                return
            if not gate.control:
                return self._send(403, b"Remote view is read-only: control NAVERA from the box's own Wi-Fi.")
            self._forward()

    return Handler


def make_portal_handler(page: str):
    class Portal(http.server.BaseHTTPRequestHandler):
        server_version = "NAVERA"
        sys_version = ""

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            body = (f"<!doctype html><meta charset=utf-8><title>NAVERA</title>"
                    f"<a href='{page}'>Open NAVERA</a>").encode()
            self.send_response(302)
            self.send_header("Location", page)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        do_HEAD = do_GET
        do_POST = do_GET

    return Portal


def portal_main() -> int:
    addr = os.environ.get("NAVERA_WIFI_ADDRESS", "10.42.0.1/24").split("/")[0]
    page = f"http://{addr}:{os.environ.get('NAVERA_WEB_PORT', '8181')}/"
    port = int(os.environ.get("NAVERA_PORTAL_PORT", "8182"))
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), make_portal_handler(page))
    print(f"navera_access_gate: portal on :{port} -> {page}", flush=True)
    srv.serve_forever()
    return 0


def main() -> int:
    if sys.argv[1:] == ["--portal"]:
        return portal_main()
    key = os.environ.get("NAVERA_REMOTE_KEY", "")
    try:
        gate = Gate(key, int(os.environ.get("NAVERA_WEB_PORT", "8181")),
                    os.environ.get("NAVERA_REMOTE_CONTROL", "0") == "1")
    except ValueError as e:
        print(f"navera_access_gate: {e}", file=sys.stderr)
        return 2
    port = int(os.environ.get("NAVERA_REMOTE_PORT", "8190"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(gate))
    print(f"navera_access_gate: on 127.0.0.1:{port} -> web page 127.0.0.1:{gate.web_port}"
          f" ({'view and control' if gate.control else 'view only'})", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
