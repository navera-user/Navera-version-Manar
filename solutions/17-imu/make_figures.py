#!/usr/bin/env python3
"""Teacher only — draws the figures of lesson 17 into courses/17-imu/assets/.

    python3 solutions/17-imu/make_figures.py

Every number drawn is computed here (the 1-D complementary filter, the drift, the forces, the WMM field near
Monastir through pygeomag). The cold-open trace is a synthetic illustration (seed 7), not the lab's file.
"""
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ACADEMY, "courses", "17-imu", "assets")
INK, BLUE, RED, ORANGE, GREY, BG, GREEN = "#1d2733", "#0b6e8a", "#d64545", "#a8680d", "#8a96a3", "#f7fafc", "#2e9e4f"
HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {{w}} {{h}}" font-family="sans-serif" font-size="13">'
        f'<rect width="{{w}}" height="{{h}}" fill="{BG}"/><defs>'
        + "".join(f'<marker id="m{n}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                  f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
                  for n, c in (("i", INK), ("r", RED), ("b", BLUE), ("o", ORANGE), ("g", GREY), ("n", GREEN)))
        + "</defs>")


def text(x, y, s, size=13, color=INK, anchor="middle", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}">{s}</text>')


def arrow(x1, y1, x2, y2, color=INK, m="i", width=2.0, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"'
            f'{d} marker-end="url(#m{m})"/>')


def line(x1, y1, x2, y2, color=INK, width=1.0, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{d}/>'


def poly(xs, ys, color, width=2.0, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{d} stroke-linejoin="round"/>'


def save(name, w, h, body):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(HEAD.format(w=w, h=h) + body + "</svg>\n")
    print("wrote", name, os.path.getsize(os.path.join(OUT, name)), "bytes")


def axes(x0, y0, w, h, xmax, ymin, ymax, xlabel, ylabel, xticks, yticks):
    """A simple plot frame; returns (body, X(x), Y(y))."""
    X = lambda x: x0 + w * x / xmax                                        # noqa: E731
    Y = lambda y: y0 + h - h * (y - ymin) / (ymax - ymin)                   # noqa: E731
    b = [line(x0, y0 + h, x0 + w, y0 + h, INK), line(x0, y0, x0, y0 + h, INK)]
    for xt in xticks:
        b.append(line(X(xt), y0 + h, X(xt), y0 + h + 4, INK))
        b.append(text(X(xt), y0 + h + 17, f"{xt:g}", 11, INK))
    for yt in yticks:
        b.append(line(x0 - 4, Y(yt), x0, Y(yt), INK))
        b.append(line(x0, Y(yt), x0 + w, Y(yt), "#d8dee5", 0.8))
        b.append(text(x0 - 7, Y(yt) + 4, f"{yt:g}", 11, INK, "end"))
    b.append(text(x0 + w / 2, y0 + h + 34, xlabel, 12, INK))
    b.append(f'<text x="{x0 - 38}" y="{y0 + h / 2}" font-size="12" fill="{INK}" text-anchor="middle" '
             f'transform="rotate(-90 {x0 - 38} {y0 + h / 2})">{ylabel}</text>')
    return "".join(b), X, Y


# ---------------------------------------------------------------------------------------- cold open (IMU-1)
def cold_open():
    rng = np.random.default_rng(7)
    t = np.arange(0, 6.0001, 0.02)
    y = 1.2 * np.sin(2 * np.pi * t / 2.5) + rng.normal(0, 0.35, len(t))
    k = int(np.searchsorted(t, 3.0))
    y[k:] = y[k - 1]
    b = [text(395, 26, "A frozen IMU looks like a perfectly calm drone", 15, weight="bold")]
    body, X, Y = axes(70, 50, 470, 180, 6.0, -2.5, 2.5, "time (s)", "gyro z (°/s)", (0, 1, 2, 3, 4, 5, 6), (-2, 0, 2))
    b.append(body)
    b.append(poly([X(v) for v in t[:k]], [Y(v) for v in y[:k]], BLUE, 1.4))
    b.append(poly([X(v) for v in t[k - 1:]], [Y(v) for v in y[k - 1:]], RED, 2.2))
    for v in t[::5]:
        b.append(line(X(v), 268, X(v), 276, GREEN, 1.2))
    b.append(text(305, 293, "a new message with a fresh timestamp every 20 ms — before AND after the freeze", 11, GREEN))
    b.append(arrow(X(3.0), 62, X(3.0), Y(y[k - 1]) - 8, RED, "r", 1.5))
    b.append(text(X(3.0) - 6, 58, "the chip stops answering;", 11, RED, "end"))
    b.append(text(X(3.0) + 6, 58, "the library hands back its last report", 11, RED, "start"))
    x0 = 565
    b.append(f'<rect x="{x0}" y="60" width="210" height="170" rx="8" fill="#ffffff" stroke="{GREY}"/>')
    for i, (s, col, wt) in enumerate((("NAVERA backlog, item IMU-1", INK, "bold"), ("severity: high", RED, "normal"),
                                      ("“Possible stale data", INK, "normal"), ("published forever (library", INK, "normal"),
                                      ("caches last report)”", INK, "normal"), ("", INK, "normal"),
                                      ("fixed: a frozen-data detector", GREEN, "normal"), ("(this mission, §6)", GREEN, "normal"))):
        b.append(text(x0 + 14, 84 + 19 * i, s, 12, col, "start", wt))
    b.append(text(395, 318, "Synthetic illustration. After the freeze every number is the same; nothing in the message says so.",
                  11, GREY))
    save("cold_open.svg", 790, 330, "".join(b))


# ---------------------------------------------------------------------------------------- specific force
def forces():
    g = 9.81
    b = [text(415, 24, "What the accelerometer feels: the specific force f = (all forces except gravity) / mass", 14,
              weight="bold")]

    def drone(cx, cy, tilt_deg, f_len, f_label, reading, title, note, accel=None):
        a = math.radians(tilt_deg)
        ux, uy = math.sin(a), -math.cos(a)                  # body z (up) in screen coordinates
        px, py = math.cos(a), math.sin(a)                   # body x/y across
        out = [text(cx, 52, title, 13, BLUE, weight="bold")]
        out.append(line(cx - 46 * px, cy - 46 * py, cx + 46 * px, cy + 46 * py, INK, 7))
        for s in (-1, 1):
            out.append(line(cx + s * 46 * px - 18 * px, cy + s * 46 * py - 18 * py - 4 * 0,
                            cx + s * 46 * px + 18 * px, cy + s * 46 * py + 18 * py, GREY, 3))
        out.append(arrow(cx - 6, cy, cx - 6 + 60 * ux, cy + 60 * uy, ORANGE, "o", 2, "4 3"))
        out.append(text(cx + 68 * ux + 4, cy + 68 * uy, "body z", 10, ORANGE, "start"))
        if f_len > 0:
            k = 5.5
            out.append(arrow(cx + 6, cy, cx + 6 + f_len * k * ux, cy + f_len * k * uy, RED, "r", 3))
            out.append(text(cx + 20 + f_len * k * ux, cy + f_len * k * uy + 14, f_label, 11, RED, "start"))
        out.append(arrow(cx - 70, cy + 10, cx - 70, cy + 52, GREY, "g", 2))
        out.append(text(cx - 70, cy + 66, "gravity", 10, GREY))
        if accel:
            out.append(arrow(cx - 75, cy - 70, cx - 75 + accel[0], cy - 70, BLUE, "b", 2.5))
            out.append(text(cx - 75 + accel[0] / 2, cy - 78, accel[1], 10, BLUE))
        out.append(text(cx, 248, reading, 12, INK, weight="bold"))
        out.append(text(cx, 266, note, 11, GREY))
        return "".join(out)

    a_fwd = 2.0
    a_turn = 12 * math.radians(20)
    b.append(drone(105, 160, 0, g, "f = 9.81 up", "reads (0, 0, +9.81)", "on a table / hovering",
                   "the table (or thrust) pushes UP"))
    b.append(drone(310, 160, 0, 0, "", "reads (0, 0, 0)", "free fall", "nothing pushes: weightless"))
    b.append(drone(520, 160, math.degrees(math.atan(a_fwd / g)), math.hypot(a_fwd, g), f"|f| = {math.hypot(a_fwd, g):.2f}",
                   f"reads (0, 0, +{math.hypot(a_fwd, g):.2f})", f"speeding up at {a_fwd:g} m/s²",
                   f"tilted {math.degrees(math.atan(a_fwd / g)):.1f}°, yet it looks level", (34, "a")))
    b.append(drone(725, 160, math.degrees(math.atan(a_turn / g)), math.hypot(a_turn, g), f"|f| = {math.hypot(a_turn, g):.2f}",
                   f"reads (0, 0, +{math.hypot(a_turn, g):.2f})", "turn: 12 m/s at 20°/s",
                   f"banked {math.degrees(math.atan(a_turn / g)):.1f}°, yet it looks level", (60, "a to the centre")))
    b.append(text(415, 292, "Seen from behind (turn) or from the side (speeding up). A multirotor's thrust is always along "
                            "its body z axis: when the drone accelerates, f stays along body z.", 11, INK))
    save("forces.svg", 830, 305, "".join(b))


# ---------------------------------------------------------------------------------------- drift
def drift():
    b_deg = 0.01
    sig, dt = 0.003, 0.02
    t = np.linspace(0, 600, 301)
    bias = b_deg * t
    noise = np.degrees(sig * np.sqrt(dt * t))
    b = [text(395, 24, "Integrating a gyroscope: the bias grows like t, the noise like √t", 14, weight="bold")]
    body, X, Y = axes(80, 45, 520, 200, 600, -1.5, 7, "time (s)", "heading error (°)", (0, 100, 200, 300, 400, 500, 600),
                      (0, 2, 4, 6))
    b.append(body)
    top = [Y(v) for v in noise]
    bot = [Y(-v) for v in noise]
    pts = " ".join(f"{X(x):.1f},{y:.1f}" for x, y in zip(t, top)) + " " + \
        " ".join(f"{X(x):.1f},{y:.1f}" for x, y in zip(t[::-1], bot[::-1]))
    b.append(f'<polygon points="{pts}" fill="{BLUE}" fill-opacity="0.25" stroke="none"/>')
    b.append(poly([X(x) for x in t], [Y(v) for v in bias], RED, 2.5))
    b.append(text(X(600) + 8, Y(6.0) + 4, f"bias {b_deg}°/s: {b_deg * 600:.0f}° after 10 min", 12, RED, "start"))
    b.append(text(X(600) + 8, Y(noise[-1]) + 4, f"noise: ±{noise[-1]:.1f}° (1σ)", 12, BLUE, "start"))
    b.append(text(X(600) + 8, Y(noise[-1]) + 20, f"σ = {sig} rad/s per sample", 11, BLUE, "start"))
    b.append(text(X(600) + 8, Y(noise[-1]) + 35, f"at {1 / dt:.0f} Hz", 11, BLUE, "start"))
    b.append(text(395, 300, "The two are equal after only 6 s; after that the bias wins. The bias is the enemy to fight first.",
                  12, INK))
    save("drift.svg", 790, 312, "".join(b))


# ---------------------------------------------------------------------------------------- complementary filter
def complementary():
    dt, b_rate = 0.02, 0.1                                  # s, °/s
    t = np.arange(0, 60.0001, dt)
    acc_err = np.where((t >= 10) & (t < 22), 23.0, 0.0)     # a 12 s turn: gravity says "level" while banked 23°
    b = [text(415, 24, "The complementary filter: trust the gyro for seconds, gravity over minutes", 14, weight="bold")]
    # block diagram
    b.append(f'<rect x="20" y="58" width="150" height="46" rx="6" fill="#ffffff" stroke="{BLUE}"/>')
    b.append(text(95, 78, "gyroscope", 12, BLUE, weight="bold"))
    b.append(text(95, 95, "turn by ω·dt", 11, INK))
    b.append(f'<rect x="20" y="168" width="150" height="46" rx="6" fill="#ffffff" stroke="{GREEN}"/>')
    b.append(text(95, 188, "accelerometer", 12, GREEN, weight="bold"))
    b.append(text(95, 205, "tilt from gravity", 11, INK))
    b.append(f'<circle cx="245" cy="136" r="22" fill="#ffffff" stroke="{INK}"/>')
    b.append(text(245, 141, "+", 18, INK))
    b.append(arrow(170, 81, 226, 122, BLUE, "b", 2))
    b.append(text(206, 92, "× α", 12, BLUE, "start"))
    b.append(arrow(170, 191, 226, 150, GREEN, "n", 2))
    b.append(text(204, 196, "× (1 − α)", 12, GREEN, "start"))
    b.append(arrow(267, 136, 312, 136, INK, "i", 2))
    b.append(text(300, 124, "tilt", 11, INK))
    b.append(f'<path d="M290 136 L290 236 L10 236 L10 81 L18 81" fill="none" stroke="{GREY}" stroke-dasharray="4 3" '
             f'marker-end="url(#mg)"/>')
    b.append(text(150, 252, "the next step starts from this estimate", 11, GREY))
    b.append(text(165, 280, "α = τ / (τ + dt)", 13, INK, weight="bold"))
    # response plot
    body, X, Y = axes(390, 45, 400, 190, 60, 0, 25, "time (s) — gravity is fooled from 10 s to 22 s (a turn)",
                      "tilt error (°)", (0, 10, 20, 30, 40, 50, 60), (0, 5, 10, 15, 20, 25))
    b.append(body)
    b.append(f'<rect x="{X(10):.1f}" y="{Y(23):.1f}" width="{X(22) - X(10):.1f}" height="{Y(0) - Y(23):.1f}" '
             f'fill="{GREEN}" fill-opacity="0.12" stroke="{GREEN}" stroke-dasharray="3 3"/>')
    for tau, col in ((1.0, RED), (30.0, BLUE)):
        a = tau / (tau + dt)
        e, ys = 0.0, []
        for k in range(len(t)):
            e = a * (e + b_rate * dt) + (1 - a) * acc_err[k]
            ys.append(e)
        step = max(1, len(t) // 300)
        b.append(poly([X(v) for v in t[::step]], [Y(v) for v in ys[::step]], col, 2))
        lab = f"τ = {tau:g} s: follows the fooled gravity" if tau < 5 else \
            f"τ = {tau:g} s: {max(ys):.1f}° at most, but keeps b·τ = {b_rate * tau:g}°"
        b.append(text(X(23) + 4, Y(ys[int(21.5 / dt)]) - 6 if tau < 5 else Y(max(ys)) - 8, lab, 11, col, "start"))
    b.append(text(590, 292, f"1-D filter, dt = {dt} s, gyro bias {b_rate} °/s, gravity wrong by 23° for 12 s", 11, GREY))
    save("complementary.svg", 830, 305, "".join(b))


# ---------------------------------------------------------------------------------------- the 3-D nudge
def nudge():
    b = [text(310, 24, "The gravity step in 3-D: a small turn about a horizontal axis", 14, weight="bold")]
    cx, cy = 150, 210
    b.append(line(40, cy, 300, cy, GREY, 1, "5 4"))
    b.append(text(296, cy + 16, "horizontal", 10, GREY, "end"))
    b.append(arrow(cx, cy, cx, cy - 140, INK, "i", 2.5))
    b.append(text(cx - 6, cy - 146, "up (0, 0, 1)", 12, INK, "end"))
    a = math.radians(24)
    sx, sy = cx + 140 * math.sin(a), cy - 140 * math.cos(a)
    b.append(arrow(cx, cy, sx, sy, RED, "r", 2.5))
    b.append(text(sx + 6, sy, "seen_up", 12, RED, "start", "bold"))
    b.append(text(sx + 6, sy + 16, "gravity's push, turned", 10, RED, "start"))
    b.append(text(sx + 6, sy + 30, "into the world by q", 10, RED, "start"))
    b.append(f'<path d="M{cx + 70 * math.sin(a):.1f} {cy - 70 * math.cos(a):.1f} A70 70 0 0 0 {cx:.1f} {cy - 70}" '
             f'fill="none" stroke="{ORANGE}" stroke-width="2" marker-end="url(#mo)"/>')
    b.append(text(cx + 40, cy - 80, "error", 11, ORANGE, "start"))
    b.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="#ffffff" stroke="{BLUE}" stroke-width="2"/>')
    b.append(f'<circle cx="{cx}" cy="{cy}" r="2" fill="{BLUE}"/>')
    b.append(text(cx, cy + 26, "axis = seen_up × up (horizontal, out of the page)", 11, BLUE))
    x0 = 360
    for i, s in enumerate(("1. turn with the gyro: q ← q ⊗ Δq", "2. where does gravity's push point,",
                           "   according to q?  seen_up", "3. turn the WORLD by (1 − α) · error",
                           "   about the horizontal axis:", "   q ← Δ_gravity ⊗ q   (on the LEFT)",
                           "", "A horizontal axis never turns the", "drone about the vertical: gravity",
                           "cannot see the heading.")):
        b.append(text(x0, 70 + 19 * i, s, 12, INK if i < 6 else GREY, "start"))
    save("nudge.svg", 620, 260, "".join(b))


# ---------------------------------------------------------------------------------------- compass
def compass():
    from pygeomag import GeoMag
    gm = GeoMag().calculate(glat=35.76, glon=10.75, alt=0, time=2026.79)
    H, Z, F, I, D = math.hypot(gm.x, gm.y) / 1000, gm.z / 1000, gm.f / 1000, gm.i, gm.d
    b = [text(415, 24, "The Earth's field near Monastir (WMM2025, October 2026), and the two norths", 14, weight="bold")]
    ox, oy, k = 60, 90, 4.2
    b.append(line(30, oy, 330, oy, GREY, 1, "5 4"))
    b.append(text(ox + H * k + 10, oy + 16, "horizontal, to magnetic north →", 10, GREY, "start"))
    b.append(arrow(ox, oy, ox + H * k, oy + Z * k, RED, "r", 3))
    b.append(text(ox + H * k + 6, oy + Z * k + 4, f"F = {F:.1f} µT", 12, RED, "start"))
    b.append(arrow(ox, oy, ox + H * k, oy, BLUE, "b", 2))
    b.append(text(ox + H * k / 2, oy - 8, f"H = {H:.1f} µT", 11, BLUE))
    b.append(arrow(ox + H * k, oy, ox + H * k, oy + Z * k, GREEN, "n", 2, "4 3"))
    b.append(text(ox + H * k + 6, oy + Z * k / 2, f"Z = {Z:.1f} µT down", 11, GREEN, "start"))
    b.append(f'<path d="M{ox + 45} {oy} A45 45 0 0 1 {ox + 45 * math.cos(math.radians(I)):.1f} '
             f'{oy + 45 * math.sin(math.radians(I)):.1f}" fill="none" stroke="{ORANGE}" stroke-width="2"/>')
    b.append(text(ox + 52, oy + 30, f"I = {I:.1f}°", 12, ORANGE, "start"))
    b.append(text(180, 268, "Side view: the field dips steeply. Tilt the drone", 11, INK))
    b.append(text(180, 284, "and the big Z leaks into its x and y readings.", 11, INK))
    # map view
    cx, cy = 600, 200
    b.append(arrow(cx, cy, cx, cy - 140, INK, "i", 2.5))
    b.append(text(cx, cy - 148, "true north (maps)", 12, INK))
    dd = math.radians(12.0)
    b.append(arrow(cx, cy, cx + 140 * math.sin(dd), cy - 140 * math.cos(dd), RED, "r", 2.5))
    b.append(text(cx + 140 * math.sin(dd) + 6, cy - 140 * math.cos(dd) + 12, "magnetic north", 12, RED, "start"))
    b.append(f'<path d="M{cx} {cy - 90} A90 90 0 0 1 {cx + 90 * math.sin(dd):.1f} {cy - 90 * math.cos(dd):.1f}" '
             f'fill="none" stroke="{ORANGE}" stroke-width="2"/>')
    b.append(text(cx + 14, cy - 98, "D", 13, ORANGE, "start", "bold"))
    hh = math.radians(60.0)
    b.append(arrow(cx, cy, cx + 130 * math.sin(hh), cy - 130 * math.cos(hh), BLUE, "b", 3))
    b.append(text(cx + 130 * math.sin(hh) + 6, cy - 130 * math.cos(hh) + 4, "nose", 12, BLUE, "start"))
    b.append(text(cx, cy + 34, "true heading = magnetic heading + D", 13, INK, weight="bold"))
    b.append(text(cx, cy + 52, f"(D east positive; here D = +{D:.2f}°, drawn larger)", 11, GREY))
    save("compass.svg", 830, 300, "".join(b))


if __name__ == "__main__":
    cold_open()
    forces()
    drift()
    complementary()
    nudge()
    compass()
