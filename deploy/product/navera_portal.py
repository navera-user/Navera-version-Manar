#!/usr/bin/env python3
"""navera_portal.py — the captive portal of the box's own Wi-Fi.

A phone that joins the box's Wi-Fi (the access card's QR code) checks whether it is online by
fetching a web address; on the hotspot every name resolves to the box (navera_hotspot.sh) and
the firewall sends port 80 here (navera_firewall.sh). Every request is answered with a redirect
to NAVERA's page, so the phone opens it by itself ("sign in to network", like a hotel Wi-Fi).
Standard library only.

    navera_portal.py      # NAVERA_PORTAL_PORT (default 8182), NAVERA_WIFI_ADDRESS, NAVERA_WEB_PORT
"""
import http.server
import os
import sys


def make_handler(page: str):
    class Portal(http.server.BaseHTTPRequestHandler):
        server_version = "NAVERA"
        sys_version = ""

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            body = f"<!doctype html><meta charset=utf-8><title>NAVERA</title><a href='{page}'>Open NAVERA</a>"
            data = body.encode()
            self.send_response(302)
            self.send_header("Location", page)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_HEAD = do_GET
        do_POST = do_GET

    return Portal


def page_url(env=os.environ) -> str:
    addr = env.get("NAVERA_WIFI_ADDRESS", "10.42.0.1/24").split("/")[0]
    return f"http://{addr}:{env.get('NAVERA_WEB_PORT', '8181')}/"


def main() -> int:
    port = int(os.environ.get("NAVERA_PORTAL_PORT", "8182"))
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), make_handler(page_url()))
    print(f"navera_portal: on :{port} -> {page_url()}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
