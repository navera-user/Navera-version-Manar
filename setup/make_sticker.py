#!/usr/bin/env python3
"""Printable sticker for the box: QR 1 joins the setup Wi-Fi, QR 2 opens the setup page.

    python3 make_sticker.py [--conf /etc/navera/setup.json] [--out sticker.html]
Open the HTML in a browser and print it (A6 / label size).
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import segno

ap = argparse.ArgumentParser()
ap.add_argument("--conf", default="/etc/navera/setup.json")
ap.add_argument("--out", default="sticker.html")
a = ap.parse_args()
c = json.load(open(a.conf))
esc = lambda s: "".join("\\" + ch if ch in '\;,:"' else ch for ch in s)
wifi = segno.make(f'WIFI:T:WPA;S:{esc(c["ssid"])};P:{esc(c["password"])};;', error="m").svg_data_uri(scale=6, dark="#0b1730")
page = segno.make("http://navera.setup", error="m").svg_data_uri(scale=6, dark="#0b1730")
html = f"""<!doctype html><meta charset="utf-8"><title>NAVERA sticker</title>
<style>body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:20px;color:#0b1730}}
.s{{width:150mm;border:2px solid #0b1730;border-radius:6mm;padding:7mm}}h1{{margin:0 0 2mm;font-size:20pt}}
.row{{display:flex;gap:8mm;margin-top:5mm}}.q{{flex:1;text-align:center}}.q img{{width:52mm}}
.n{{display:inline-block;background:#e8706a;color:#fff;border-radius:50%;width:8mm;height:8mm;line-height:8mm;font-weight:700}}
code{{font-size:12pt}}p{{margin:2mm 0}}</style>
<div class="s"><h1>NAVERA Academy — first start</h1><p>Power on, wait 2 minutes, then:</p>
<div class="row"><div class="q"><span class="n">1</span><p><b>Join the setup Wi-Fi</b></p><img src="{wifi}">
<p><code>{c['ssid']}</code><br>password <code>{c['password']}</code></p></div>
<div class="q"><span class="n">2</span><p><b>Open the setup page</b></p><img src="{page}"><p><code>http://navera.setup</code></p></div></div>
<p style="margin-top:5mm">3 · Choose your Wi-Fi, type its password, press <b>Connect</b>. Done.</p></div>"""
open(a.out, "w").write(html)
print("wrote", a.out)
