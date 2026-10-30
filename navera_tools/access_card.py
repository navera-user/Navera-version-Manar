#!/usr/bin/env python3
"""access_card.py — the box's printable access card: one QR code that joins the box's setup Wi-Fi
(the same name and password on every box, so the same code everywhere); its setup page then
opens by itself: put the box on the client's Wi-Fi, or open NAVERA's page right there.

Works offline (QR codes by OpenCV, already on the box). The card holds the Wi-Fi password and
is the same for every box: print it as the box's label.

    python3 navera_tools/access_card.py --out DIR [--env /etc/navera/navera.env]
      DIR/access_card.html   the printable card (QR image inside)
      DIR/qr_wifi.png        the QR code alone (for a sticker)
"""
import argparse
import base64
import html
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


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
.grid {{ display: grid; grid-template-columns: minmax(0, 340px); gap: 16px; }}
section {{ border: 1px solid var(--line); border-radius: 10px; padding: 14px; break-inside: avoid; }}
h2 {{ font-size: 17px; margin: 0 0 8px; }} img {{ width: 100%; max-width: 240px; display: block; }}
.cap {{ font-family: ui-monospace, monospace; font-size: 13px; word-break: break-all; }}
.none {{ padding: 40px 0; text-align: center; color: var(--muted); }}
ol {{ padding-left: 18px; margin: 6px 0 0; }} .warn {{ color: var(--muted); font-size: 12px; margin-top: 16px; }}
@media print {{ body {{ margin: 8mm; }} }}
</style></head><body>
<h1>NAVERA — access card</h1><p class="sub">IRIS Systems · keep this card with the box</p>
<div class="grid">{''.join(blocks)}</div>
<p class="warn">Anyone near the box with this code can open NAVERA's page.</p></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--env", default="/etc/navera/navera.env")
    a = ap.parse_args()
    env = read_env(a.env)
    ssid = env.get("NAVERA_WIFI_SSID") or "NAVERA"
    password = env.get("NAVERA_WIFI_PASSWORD") or "navera-iris"
    addr = (env.get("NAVERA_WIFI_ADDRESS") or "10.42.0.1/24").split("/")[0]
    local = f"http://{addr}:{env.get('NAVERA_WEB_PORT') or '8181'}/"

    os.makedirs(a.out, exist_ok=True)
    wifi_png = qr_png(wifi_payload(ssid, password))
    with open(os.path.join(a.out, "qr_wifi.png"), "wb") as f:
        f.write(wifi_png)
    e = html.escape
    cards = [("Scan → NAVERA setup opens", "<ol><li>Phone camera on this code, tap “Join”</li>"
              "<li>The setup page opens by itself</li>"
              "<li><b>Your Wi-Fi:</b> choose it, type its password, Connect — then everyone on your Wi-Fi "
              "opens <b>http://navera.local:8181/</b></li>"
              "<li><b>No Wi-Fi around:</b> tap “Open NAVERA” right there</li></ol>",
              wifi_png, f"Setup Wi-Fi: {e(ssid)}<br>Password: {e(password)}<br>Page: {e(local)}")]
    with open(os.path.join(a.out, "access_card.html"), "w") as f:
        f.write(card_html(cards))
    print(f"access card: {os.path.join(a.out, 'access_card.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
