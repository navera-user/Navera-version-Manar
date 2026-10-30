#!/usr/bin/env python3
"""access_card.py — the box's printable access card. The main QR code joins the box's Wi-Fi
(the same name and password on every box, so the same code everywhere); the box's captive
portal then opens NAVERA's page by itself. A second, optional code opens the public link.

Works offline (QR codes by OpenCV, already on the box). The card holds the Wi-Fi password and
the remote key: print it for the client, keep it with the box, do not publish it.

    python3 navera_tools/access_card.py --out DIR [--env /etc/navera/navera.env] [--link URL]
      DIR/access_card.html   the printable card (A5/A4, QR images inside)
      DIR/qr_wifi.png, qr_local.png, qr_remote.png
--link: the public link (default: `navera_remote.sh --link`; none when Tailscale is not set up).
"""
import argparse
import base64
import html
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REMOTE_SH = os.path.join(os.path.dirname(HERE), "deploy", "product", "navera_remote.sh")


def read_env(path: str) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def wifi_escape(s: str) -> str:
    """Escape for the WIFI: QR format (backslash, ; , : " are special)."""
    return "".join("\\" + c if c in '\\;,:"' else c for c in s)


def wifi_payload(ssid: str, password: str) -> str:
    return f"WIFI:T:WPA;S:{wifi_escape(ssid)};P:{wifi_escape(password)};;"


def qr_png(text: str, scale: int = 10, border: int = 4) -> bytes:
    """A PNG of the QR code of `text`, checked by decoding it back."""
    q = cv2.QRCodeEncoder.create().encode(text)
    if q is None or q.size == 0:
        raise ValueError("QR encoding failed")
    q = (q > 127).astype(np.uint8) * 255

    def draw(sc):
        im = cv2.resize(q, None, fx=sc, fy=sc, interpolation=cv2.INTER_NEAREST)
        return cv2.copyMakeBorder(im, border * sc, border * sc, border * sc, border * sc,
                                  cv2.BORDER_CONSTANT, value=255)

    # checked by decoding it back (OpenCV's detector is unreliable on very large modules: small sizes)
    if not any(cv2.QRCodeDetector().detectAndDecode(draw(sc))[0] == text for sc in (3, 4, 5, 6)):
        raise ValueError("QR code does not decode back to its text")
    img = draw(scale)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("PNG encoding failed")
    return buf.tobytes()


def public_link(env: dict) -> str:
    try:
        p = subprocess.run([REMOTE_SH, "--link"], capture_output=True, text=True, timeout=20,
                           env=dict(os.environ, **env))
    except OSError:
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def card_html(cards) -> str:
    """cards: [(title, steps html, png bytes or None, caption)]."""
    blocks = []
    for title, steps, png, caption in cards:
        img = (f'<img alt="QR code" src="data:image/png;base64,{base64.b64encode(png).decode()}">'
               if png else '<div class="none">not set up</div>')
        blocks.append(f'<section><h2>{html.escape(title)}</h2>{img}'
                      f'<p class="cap">{caption}</p>{steps}</section>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>NAVERA access card</title>
<style>
:root {{ --ink:#111; --muted:#555; --line:#ccc; --bg:#fff; }}
body {{ font-family: system-ui, sans-serif; color: var(--ink); background: var(--bg); margin: 16px; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }} .sub {{ color: var(--muted); margin: 0 0 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
section {{ border: 1px solid var(--line); border-radius: 10px; padding: 14px; break-inside: avoid; }}
h2 {{ font-size: 17px; margin: 0 0 8px; }} img {{ width: 100%; max-width: 240px; display: block; }}
.cap {{ font-family: ui-monospace, monospace; font-size: 13px; word-break: break-all; }}
.none {{ padding: 40px 0; text-align: center; color: var(--muted); }}
ol {{ padding-left: 18px; margin: 6px 0 0; }} .warn {{ color: var(--muted); font-size: 12px; margin-top: 16px; }}
@media print {{ body {{ margin: 8mm; }} }}
</style></head><body>
<h1>NAVERA — access card</h1><p class="sub">IRIS Systems · keep this card with the box</p>
<div class="grid">{''.join(blocks)}</div>
<p class="warn">This card holds the Wi-Fi password and the remote key: anyone with it can view
NAVERA. Do not post it publicly.</p></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--env", default="/etc/navera/navera.env")
    ap.add_argument("--link", help="the public link (default: navera_remote.sh --link)")
    a = ap.parse_args()
    env = read_env(a.env)
    ssid = env.get("NAVERA_WIFI_SSID") or "NAVERA"
    password = env.get("NAVERA_WIFI_PASSWORD") or "navera-iris"
    addr = (env.get("NAVERA_WIFI_ADDRESS") or "10.42.0.1/24").split("/")[0]
    local = f"http://{addr}:{env.get('NAVERA_WEB_PORT') or '8181'}/"
    link = a.link if a.link is not None else public_link(env)

    os.makedirs(a.out, exist_ok=True)
    wifi_png, local_png = qr_png(wifi_payload(ssid, password)), qr_png(local)
    remote_png = qr_png(link) if link else None
    for name, png in (("qr_wifi.png", wifi_png), ("qr_local.png", local_png), ("qr_remote.png", remote_png)):
        if png:
            with open(os.path.join(a.out, name), "wb") as f:
                f.write(png)
    e = html.escape
    cards = [
        ("Scan → NAVERA opens", "<ol><li>Phone camera on this code</li><li>Tap “Join”</li>"
         "<li>The NAVERA page opens by itself (if not: open the address below)</li></ol>",
         wifi_png, f"Wi-Fi: {e(ssid)}<br>Password: {e(password)}<br>Page: {e(local)}"),
    ]
    if link:
        cards.append(("From anywhere (optional)", "<ol><li>Any phone or PC with internet</li>"
                      "<li>Scan or open the link: nothing to install</li><li>View only</li></ol>"
                      "<p>The box needs internet (Ethernet or 4G stick).</p>", remote_png, e(link)))
    with open(os.path.join(a.out, "access_card.html"), "w") as f:
        f.write(card_html(cards))
    print(f"access card: {os.path.join(a.out, 'access_card.html')}"
          + ("" if link else " (no public link: Tailscale not set up)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
