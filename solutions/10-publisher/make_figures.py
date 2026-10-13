"""Writes the SVG figures of mission 10 (run on the host)."""
import math, os
A = os.path.expanduser("~/navera-academy-v2/courses/10-publisher/assets")
os.makedirs(A, exist_ok=True)
HEAD = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="13">
  <rect width="{w}" height="{h}" fill="#f7fafc"/>
  <defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#5a6b7b"/></marker></defs>
'''

# ---------------------------------------------------------------- 1. cold open: stopped, then jumped
s = [HEAD.format(w=780, h=350)]
s.append('<text x="390" y="24" text-anchor="middle" font-size="15" fill="#1d2733">One GPS fix per second, re-sent 5 times per second with a fresh stamp</text>')
# left axes
x0, y0, px_s, px_m = 70, 250, 95, 5.5
s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0+300}" y2="{y0}" stroke="#5a6b7b"/><line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0-185}" stroke="#5a6b7b"/>')
for t in range(4):
    s.append(f'<line x1="{x0+t*px_s}" y1="{y0}" x2="{x0+t*px_s}" y2="{y0+5}" stroke="#5a6b7b"/><text x="{x0+t*px_s}" y="{y0+19}" text-anchor="middle" font-size="11">{t} s</text>')
for m in (0, 10, 20, 30):
    s.append(f'<text x="{x0-8}" y="{y0-m*px_m+4}" text-anchor="end" font-size="11">{m} m</text><line x1="{x0-4}" y1="{y0-m*px_m}" x2="{x0}" y2="{y0-m*px_m}" stroke="#5a6b7b"/>')
s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0+3*px_s}" y2="{y0-30*px_m}" stroke="#888" stroke-dasharray="5,4"/>')
s.append(f'<text x="{x0+3*px_s-6}" y="{y0-30*px_m-8}" text-anchor="end" font-size="11" fill="#5a6b7b">where the vehicle is (10 m/s)</text>')
for k in range(16):
    t = 0.2 * k
    x = 10 * math.floor(t + 1e-9)
    s.append(f'<circle cx="{x0+t*px_s:.1f}" cy="{y0-x*px_m:.1f}" r="3.6" fill="#d64545"/>')
s.append(f'<text x="{x0+150}" y="{y0+40}" text-anchor="middle" font-size="12" fill="#d64545">● what the autopilot is told, 5 times per second</text>')
s.append(f'<text x="{x0+150}" y="{y0+56}" text-anchor="middle" font-size="11" fill="#5a6b7b">position east (m) vs time (s)</text>')
# right: speeds
x1, sc = 450, 3.0
s.append(f'<line x1="{x1}" y1="{y0}" x2="{x1+300}" y2="{y0}" stroke="#5a6b7b"/><line x1="{x1}" y1="{y0}" x2="{x1}" y2="{y0-170}" stroke="#5a6b7b"/>')
for v in (0, 10, 50):
    s.append(f'<text x="{x1-8}" y="{y0-v*sc+4}" text-anchor="end" font-size="11">{v}</text>')
s.append(f'<line x1="{x1}" y1="{y0-10*sc}" x2="{x1+300}" y2="{y0-10*sc}" stroke="#888" stroke-dasharray="5,4"/><text x="{x1+46}" y="{y0-10*sc-5}" text-anchor="middle" font-size="11" fill="#5a6b7b">true 10 m/s</text>')
for k in range(1, 16):
    t = 0.2 * k
    v = 50.0 if abs(t - round(t)) < 1e-9 else 0.0
    xx = x1 + t * px_s
    if v:
        s.append(f'<rect x="{xx-5:.1f}" y="{y0-v*sc:.1f}" width="10" height="{v*sc:.1f}" fill="#d64545"/><text x="{xx:.1f}" y="{y0-v*sc-6:.1f}" text-anchor="middle" font-size="11" fill="#d64545">50</text>')
    else:
        s.append(f'<rect x="{xx-5:.1f}" y="{y0-2}" width="10" height="2" fill="#d64545"/>')
for t in range(4):
    s.append(f'<text x="{x1+t*px_s}" y="{y0+19}" text-anchor="middle" font-size="11">{t} s</text>')
s.append(f'<text x="{x1+150}" y="{y0+40}" text-anchor="middle" font-size="12" fill="#d64545">speed computed from two messages (m/s): 0, 0, 0, 0, 50 …</text>')
s.append(f'<text x="{x1+150}" y="{y0+56}" text-anchor="middle" font-size="11" fill="#5a6b7b">"stopped, then jumped"</text>')
s.append('<text x="390" y="338" text-anchor="middle" font-size="12" fill="#2f7a2f">The repair: each measurement sent once, stamped when it was measured → 10 m/s every time</text>')
s.append('</svg>\n')
open(os.path.join(A, "cold_open.svg"), "w").write("\n".join(s))

# ---------------------------------------------------------------- 2. node anatomy
s = [HEAD.format(w=780, h=400)]
s.append('<text x="390" y="24" text-anchor="middle" font-size="15" fill="#1d2733">Inside the fake_gps node: what runs once, and what runs at every tick</text>')
s.append('<rect x="14" y="40" width="540" height="345" rx="14" fill="#e6f2f6" stroke="#0b6e8a" stroke-width="2"/>')
s.append('<text x="28" y="62" font-weight="bold" fill="#0b6e8a">class FakeGps(Node) — node "fake_gps", kept alive by rclpy.spin()</text>')
# once
s.append('<rect x="28" y="76" width="250" height="132" rx="8" fill="#fff" stroke="#a8680d" stroke-width="1.5"/>')
s.append('<text x="153" y="95" text-anchor="middle" font-weight="bold" fill="#a8680d">once, in __init__ (given)</text>')
s.append('<g font-family="monospace" font-size="12" fill="#1d2733">')
s.append('<text x="40" y="118">super().__init__("fake_gps")</text>')
s.append('<text x="40" y="140">declare_all()   ✏️ TODO 4</text>')
s.append('<text x="52" y="157" font-size="11" fill="#5a6b7b">8 parameters, start position</text>')
s.append('<text x="40" y="180">start()         ✏️ TODO 5</text>')
s.append('<text x="52" y="197" font-size="11" fill="#5a6b7b">self.pub, one timer: 1 / rate_hz</text>')
s.append('</g>')
# parameters
s.append('<rect x="300" y="76" width="240" height="132" rx="8" fill="#fff" stroke="#a8680d" stroke-width="1.5"/>')
s.append('<text x="420" y="95" text-anchor="middle" font-weight="bold" fill="#a8680d">parameters (the node\'s settings)</text>')
s.append('<g font-family="monospace" font-size="11.5" fill="#1d2733" xml:space="preserve">')
for i, (k, v) in enumerate([("rate_hz", "1.0"), ("speed_mps", "10.0"), ("heading_deg", "90.0"), ("start_lat/lon", "35.8256, 10.6084"),
                            ("sigma_m", "3.0"), ("stamp_offset_s", "0.0"), ("vehicle", '"drone" (13)')]):
    s.append(f'<text x="312" y="{112+i*14}">{k:<15}{v}</text>')
s.append('</g>')
# every tick
s.append('<rect x="28" y="226" width="512" height="146" rx="8" fill="#fff" stroke="#0b6e8a" stroke-width="1.5"/>')
s.append('<text x="284" y="245" text-anchor="middle" font-weight="bold" fill="#0b6e8a">at every tick: the timer calls on_timer()   ✏️ TODO 6</text>')
s.append('<g font-family="monospace" font-size="12" fill="#1d2733">')
s.append('<text x="42" y="270">1. now = the clock;  dt = now − last_t  (the REAL time)</text>')
s.append('<text x="42" y="292">2. read speed_mps, heading_deg, sigma_m, stamp_offset_s  ◀</text>')
s.append('<text x="42" y="314">3. lat, lon = step(lat, lon, speed, heading, dt)     ✏️ TODO 1</text>')
s.append('<text x="42" y="336">4. msg = make_fix(lat, lon, alt, σ, now + offset)    ✏️ TODO 2, 3</text>')
s.append('<text x="42" y="358">5. self.pub.publish(msg)</text>')
s.append('</g>')
# arrows out
s.append('<line x1="520" y1="210" x2="520" y2="282" stroke="#a8680d" stroke-width="1.4" stroke-dasharray="4,3" marker-end="url(#a)"/>')
s.append('<rect x="590" y="64" width="176" height="62" rx="8" fill="#fff" stroke="#5a6b7b"/>')
s.append('<text x="678" y="86" text-anchor="middle" font-size="12">your terminal</text>')
s.append('<text x="678" y="106" text-anchor="middle" font-family="monospace" font-size="11">ros2 param set …</text>')
s.append('<line x1="590" y1="110" x2="544" y2="130" stroke="#5a6b7b" stroke-width="1.5" marker-end="url(#a)"/>')
s.append('<line x1="540" y1="354" x2="600" y2="354" stroke="#5a6b7b" stroke-width="1.8" marker-end="url(#a)"/>')
s.append('<text x="680" y="300" text-anchor="middle" font-family="monospace" font-size="11.5">navera_lite/fix/gps</text>')
s.append('<text x="680" y="316" text-anchor="middle" font-size="11" fill="#5a6b7b">NavSatFix, FIX_QOS</text>')
s.append('<rect x="604" y="330" width="160" height="48" rx="8" fill="#d7f0d2" stroke="#2f7a2f"/>')
s.append('<text x="684" y="351" text-anchor="middle" font-size="12">arbiter v0 (09)</text>')
s.append('<text x="684" y="368" text-anchor="middle" font-size="11" fill="#2f7a2f">FIX "gps: σ 3.0 m"</text>')
s.append('</svg>\n')
open(os.path.join(A, "node_anatomy.svg"), "w").write("\n".join(s))

# ---------------------------------------------------------------- 3. real dt
calls = [0.00, 0.50, 1.12, 1.53, 2.08, 3.30, 3.50, 4.00]
s = [HEAD.format(w=860, h=330)]
s.append('<text x="430" y="24" text-anchor="middle" font-size="15" fill="#1d2733">A 2 Hz timer on a busy computer: asked, and what really happened</text>')
X0, PX = 160, 160
def X(t): return X0 + t * PX
s.append(f'<text x="148" y="70" text-anchor="end" font-size="12">deadlines (asked)</text>')
for k in range(9):
    t = 0.5 * k
    miss = t in (2.5, 3.0)
    s.append(f'<line x1="{X(t)}" y1="58" x2="{X(t)}" y2="78" stroke="{"#d64545" if miss else "#9aa7b4"}" stroke-width="2"/>')
    if miss:
        s.append(f'<text x="{X(t)}" y="52" text-anchor="middle" font-size="14" fill="#d64545">✕</text>')
s.append(f'<text x="{(X(2.5)+X(3.0))/2}" y="96" text-anchor="middle" font-size="11" fill="#d64545">2 deadlines passed → 1 late call</text>')
s.append(f'<text x="148" y="128" text-anchor="end" font-size="12">calls (real)</text>')
s.append(f'<rect x="{X(2.08)}" y="112" width="{X(3.30)-X(2.08)}" height="22" fill="#fde2e2" stroke="#d64545" stroke-dasharray="3,2"/>')
s.append(f'<text x="{(X(2.08)+X(3.30))/2}" y="127" text-anchor="middle" font-size="11" fill="#d64545">callback busy 1.22 s</text>')
for t in calls:
    s.append(f'<circle cx="{X(t)}" cy="123" r="5" fill="#0b6e8a"/>')
s.append(f'<line x1="{X0}" y1="150" x2="{X(4.1)}" y2="150" stroke="#5a6b7b" marker-end="url(#a)"/>')
for t in range(5):
    s.append(f'<text x="{X(t)}" y="166" text-anchor="middle" font-size="11">{t} s</text>')
s.append('<text x="148" y="206" text-anchor="end" font-size="12">stamp (s)</text>')
s.append('<text x="148" y="232" text-anchor="end" font-size="12" fill="#2f7a2f">real dt → (m)</text>')
s.append('<text x="148" y="258" text-anchor="end" font-size="12" fill="#d64545">nominal 0.5 s → (m)</text>')
for k, t in enumerate(calls):
    s.append(f'<text x="{X(t)}" y="206" text-anchor="middle" font-size="11">{t:.2f}</text>')
    s.append(f'<text x="{X(t)}" y="232" text-anchor="middle" font-size="11" fill="#2f7a2f">{10*t:.1f}</text>')
    s.append(f'<text x="{X(t)}" y="258" text-anchor="middle" font-size="11" fill="#d64545">{5*k:.0f}</text>')
s.append('<text x="430" y="292" text-anchor="middle" font-size="12" fill="#1d2733">Vehicle at 10 m/s. Distance travelled at each stamp: green = where it really was (10 × stamp),</text>')
s.append('<text x="430" y="310" text-anchor="middle" font-size="12" fill="#1d2733">red = 5 m added per call. At 3.30 s it is 8 m behind its stamp; then 5 m behind for good (one tick lost).</text>')
s.append('</svg>\n')
open(os.path.join(A, "real_dt.svg"), "w").write("\n".join(s))
print("ok")
