#!/usr/bin/env python3
"""Teacher only — draws the figures of lesson 26 into courses/26-stars/assets/.

    python3 solutions/26-stars/make_figures.py

Every number drawn is computed here with the course reference (solutions/_navera_lite/navera_lite/stars.py):
the lesson's worked example is Capella seen from London, 7 October 2026, 20:00 UTC.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import stars as S                        # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "26-stars", "assets")
INK, BLUE, RED, ORANGE, GREY, BG, GREEN, NIGHT = ("#1d2733", "#0b6e8a", "#d64545", "#a8680d", "#8a96a3", "#f7fafc",
                                                  "#2e9e4f", "#14202e")
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


def poly(xs, ys, color, width=2.0, dash="", fill="none"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline points="{pts}" fill="{fill}" stroke="{color}" stroke-width="{width}"{d} stroke-linejoin="round"/>'


def circle(x, y, r, color=INK, fill="none", width=1.5, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" stroke="{color}" fill="{fill}" stroke-width="{width}"{d}/>'


def ellipse(x, y, rx, ry, color=INK, width=1.2, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" stroke="{color}" fill="none" '
            f'stroke-width="{width}"{d}/>')


def save(name, w, h, body):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(HEAD.format(w=w, h=h) + body + "</svg>\n")
    print("wrote", name, os.path.getsize(os.path.join(OUT, name)), "bytes")


# --------------------------------------------------------------------------------------------- the worked example
JD = S.julian_date(2026, 10, 7, 20)
GST = S.gmst_deg(JD)
LAT, LON = 51.50, -0.12                                      # London
CAP_RA, CAP_DEC = S.precess(79.1725, 45.99806, JD)            # Capella, of date
CAP_ALT, CAP_AZ = S.altaz(CAP_RA, CAP_DEC, LAT, LON, GST)
ROOTS = S.both_roots(round(CAP_ALT, 4), round(CAP_AZ, 4), CAP_RA, CAP_DEC, GST)


def cold_open():
    w, h = 920, 320
    b = [f'<rect x="20" y="40" width="300" height="225" fill="{NIGHT}" rx="6"/>',
         text(170, 28, "a star photo (synthetic)", 13, INK, weight="bold")]
    rng = np.random.default_rng(3)
    for _ in range(70):
        x, y, m = rng.uniform(30, 310), rng.uniform(50, 255), rng.uniform(0, 1)
        b.append(circle(x, y, 0.6 + 2.2 * m ** 3, "#ffffff", "#ffffff", 0.2))
    b.append(circle(170, 152, 9, "#e0a020", width=1.5))
    b.append(text(170, 280, "the centre: ra, dec (plate solve) + alt, az (IMU)", 11, GREY))
    b.append(arrow(328, 152, 368, 152, INK, "i", 2.5))
    x0, y0, W, H = 420, 50, 470, 215
    X = lambda lon: x0 + W * (lon + 30.0) / 130.0                       # noqa: E731
    Y = lambda lat: y0 + H * (75.0 - lat) / 90.0                        # noqa: E731
    b.append(f'<rect x="{x0}" y="{y0}" width="{W}" height="{H}" fill="#e8eef3" stroke="{GREY}"/>')
    for lon in range(-30, 101, 30):
        b.append(line(X(lon), y0, X(lon), y0 + H, GREY, 0.6, "3 3"))
        b.append(text(X(lon), y0 + H + 14, f"{lon}°", 10, GREY))
    for lat in (-15, 0, 15, 30, 45, 60, 75):
        b.append(line(x0, Y(lat), x0 + W, Y(lat), GREY, 0.6, "3 3"))
        b.append(text(x0 - 4, Y(lat) + 4, f"{lat}°", 10, GREY, "end"))
    b.append(text(x0 + W / 2, y0 + H + 30, "longitude (° E)", 11, INK))
    b.append(f'<text x="{x0 - 32}" y="{y0 + H / 2}" text-anchor="middle" font-size="11" fill="{INK}" '
             f'transform="rotate(-90 {x0 - 32} {y0 + H / 2})">latitude (°)</text>')
    (la1, lo1), (la2, lo2) = ROOTS
    d = S.sep_deg(la1, lo1, la2, lo2) * S.KM_PER_DEG
    b.append(line(X(lo2), Y(la2), X(lo1), Y(la1), RED, 1.5, "6 4"))
    b.append(circle(X(lo2), Y(la2), 6, GREEN, GREEN))
    b.append(text(X(lo2) + 10, Y(la2) - 8, "root 2: London (true)", 12, GREEN, "start", "bold"))
    b.append(circle(X(lo1), Y(la1), 6, RED, RED))
    b.append(text(X(lo1) - 12, Y(la1) - 14, f"root 1 (asin): {la1:.1f}°, {lo1:.1f}° — {d:,.0f} km away".replace(",", " "),
                  12, RED, "end", "bold"))
    b.append(text(x0 + W / 2, 28, "the same measurement fits two places on Earth", 13, INK, weight="bold"))
    save("cold_open.svg", w, h, "".join(b))


def sphere():
    w, h = 900, 340
    b = []
    for cx, title in ((215, "fixed to the stars: ra, dec"), (665, "fixed to you: altitude, azimuth")):
        b.append(text(cx, 26, title, 14, INK, weight="bold"))
        b.append(circle(cx, 175, 125, GREY, width=1.2))
    cx, cy, R = 215, 175, 125
    E = lambda t: (cx + R * math.cos(math.radians(t)), cy + 32 * math.sin(math.radians(t)))      # noqa: E731
    b.append(ellipse(cx, cy, R, 32, BLUE, 1.6))
    b.append(text(cx + R + 4, cy - 6, "celestial", 11, BLUE, "start"))
    b.append(text(cx + R + 4, cy + 8, "equator", 11, BLUE, "start"))
    b.append(line(cx, cy - R - 12, cx, cy + R + 12, INK, 1.2, "4 3"))
    b.append(text(cx + 6, cy - R - 2, "north celestial pole (near Polaris)", 11, INK, "start"))
    b.append(circle(cx, cy, 4, INK, INK))
    b.append(text(cx + 8, cy - 6, "Earth", 10, GREY, "start"))
    fx, fy = E(60)
    sx, sy = fx, fy - 92
    b.append(line(fx, fy, sx, sy, ORANGE, 2.0))
    b.append(circle(sx, sy, 5, ORANGE, ORANGE))
    b.append(text(sx + 8, sy - 4, "star", 12, ORANGE, "start", "bold"))
    b.append(text(sx + 6, sy + 50, "dec δ", 12, ORANGE, "start"))
    vx, vy = E(160)
    pts = [E(t) for t in np.linspace(160, 60, 30)]
    b.append(poly([p[0] for p in pts], [p[1] + 4 for p in pts], RED, 2.4))
    b.append(circle(vx, vy, 4, RED, RED))
    b.append(text(cx - R + 6, cy + 62, "vernal equinox: ra 0°", 11, RED, "start"))
    b.append(text(cx + 10, cy + 96, "ra α: measured EAST along the equator", 11, RED))
    cx, cy = 665, 175
    E = lambda t: (cx + R * math.cos(math.radians(t)), cy + 30 * math.sin(math.radians(t)))      # noqa: E731
    b.append(line(cx - R - 10, cy, cx + R + 10, cy, GREEN, 2.0))
    b.append(text(cx - R - 10, cy - 8, "horizon", 11, GREEN, "start"))
    b.append(ellipse(cx, cy, R, 30, GREEN, 1.0, "4 3"))
    b.append(line(cx, cy, cx, cy - R, INK, 1.2, "4 3"))
    b.append(text(cx, cy - R - 6, "zenith (straight up)", 11, INK))
    nx, ny = E(115)
    b.append(circle(nx, ny, 4, INK, INK))
    b.append(text(nx - 6, ny + 18, "north", 12, INK, "end", "bold"))
    b.append(circle(cx, cy, 4, INK, INK))
    b.append(text(cx + 8, cy - 8, "you", 11, INK, "start"))
    fx, fy = E(35)
    sx, sy = fx - 30, fy - 110
    b.append(line(cx, cy, sx, sy, ORANGE, 1.0, "3 3"))
    b.append(line(fx, fy, sx, sy, ORANGE, 2.0))
    b.append(circle(sx, sy, 5, ORANGE, ORANGE))
    b.append(text(sx + 8, sy - 4, "star", 12, ORANGE, "start", "bold"))
    b.append(text(sx + 14, sy + 60, "altitude a", 12, ORANGE, "start"))
    pts = [E(t) for t in np.linspace(115, 35, 30)]
    b.append(poly([p[0] for p in pts], [p[1] + 4 for p in pts], RED, 2.4))
    b.append(text(cx + 10, cy + 70, "azimuth A: clockwise from north", 11, RED))
    b.append(text(450, 330, "The sky turns once in 23 h 56 min 4 s: the left frame turns, the right frame stays.", 12, GREY))
    save("sky_frames.svg", w, h, "".join(b))


def triangle():
    w, h = 640, 330
    cx, cy, R = 200, 175, 135
    b = [circle(cx, cy, R, GREY, width=1.2), text(320, 24, "The navigational triangle: pole P, zenith Z, star X", 14,
                                                    INK, weight="bold")]
    P, Z, X = (cx - 55, cy - 95), (cx + 70, cy - 55), (cx + 5, cy + 75)
    gx, gy = (P[0] + Z[0] + X[0]) / 3, (P[1] + Z[1] + X[1]) / 3
    for (x1, y1), (x2, y2), lab, col in ((P, Z, "90° − φ", BLUE), (Z, X, "90° − a", GREEN), (P, X, "90° − δ", ORANGE)):
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ox, oy = mx - gx, my - gy
        n = math.hypot(ox, oy)
        kx, ky = mx + 22 * ox / n, my + 22 * oy / n
        b.append(f'<path d="M{x1},{y1} Q{kx:.1f},{ky:.1f} {x2},{y2}" stroke="{col}" fill="none" stroke-width="2.4"/>')
        b.append(text(mx + 38 * ox / n, my + 38 * oy / n + 4, lab, 12.5, col, weight="bold"))
    for (x, y), lab, dx, dy in ((P, "P (pole)", -10, -8), (Z, "Z (zenith)", 10, -8), (X, "X (star)", 10, 16)):
        b.append(circle(x, y, 5, INK, INK))
        b.append(text(x + dx, y + dy, lab, 13, INK, "end" if dx < 0 else "start", "bold"))
    b.append(text(P[0] + 26, P[1] + 30, "H", 13, RED, weight="bold"))
    b.append(text(Z[0] - 22, Z[1] + 24, "A", 13, RED, weight="bold"))
    tx = 380
    rows = ["sides are ANGLES (on a unit sphere):",
            "PZ = 90° − φ   (your latitude)",
            "ZX = 90° − a   (the star's altitude)",
            "PX = 90° − δ   (the star's declination)",
            "angle at P = H (the hour angle)",
            "angle at Z = A (the azimuth)",
            "",
            "the spherical law of cosines on ZX:",
            "sin a = sin δ sin φ + cos δ cos φ cos H"]
    for k, r in enumerate(rows):
        b.append(text(tx, 80 + 24 * k, r, 12.5, INK if k != 8 else RED, "start", "bold" if k in (0, 8) else "normal"))
    save("triangle.svg", w, h, "".join(b))


def centroid():
    patch = np.zeros((5, 5))
    patch[1:4, 1:4] = [[0, 10, 0], [10, 60, 30], [0, 10, 0]]
    w, h, c = 760, 320, 46
    x0, y0 = 100, 50
    b = [text(380, 26, "A star covers a few pixels: its centre is a weighted mean", 14, INK, weight="bold")]
    for r in range(5):
        for k in range(5):
            v = patch[r, k]
            g = int(20 + 235 * v / 60)
            b.append(f'<rect x="{x0 + k * c}" y="{y0 + r * c}" width="{c}" height="{c}" fill="rgb({g},{g},{g})" '
                     f'stroke="{GREY}" stroke-width="0.6"/>')
            if r == 2 and k == 2:
                b.append(text(x0 + k * c + 4, y0 + r * c + 13, f"{v:.0f}", 11, INK, "start"))
            else:
                b.append(text(x0 + k * c + c / 2, y0 + r * c + c / 2 + 5, f"{v:.0f}", 13, INK if v > 30 else "#ffffff"))
    for k in range(5):
        b.append(text(x0 + k * c + c / 2, y0 - 6, f"u = {k + 2}", 10, GREY))
        b.append(text(x0 + k * c + c / 2, y0 + 5 * c + 16, f"Σ {patch[:, k].sum():.0f}", 11, RED))
    b.append(text(x0 - 4, y0 + 5 * c + 16, "column sums:", 10, RED, "end"))
    w_sum = patch.sum()
    u = (patch * (np.arange(5) + 2)).sum() / w_sum
    v = (patch.T * (np.arange(5) + 2)).sum() / w_sum
    pu = x0 + (u - 2 + 0.5) * c
    pv = y0 + (v - 2 + 0.5) * c
    b.append(f'<path d="M{pu - 9},{pv}H{pu + 9}M{pu},{pv - 9}V{pv + 9}" stroke="{RED}" stroke-width="3"/>')
    qx = x0 + 2.5 * c
    b.append(f'<path d="M{qx - 7},{pv - 7}L{qx + 7},{pv + 7}M{qx - 7},{pv + 7}L{qx + 7},{pv - 7}" stroke="{BLUE}" '
             f'stroke-width="2.5"/>')
    tx = 380
    rows = [("pixels above the background (one star)", INK, "bold"),
            ("× plain centre of the 5 pixels: u = 4.00", BLUE, "normal"),
            (f"+ weighted centre: u = (3·10 + 4·80 + 5·30) / 120 = {u:.3f}", RED, "normal"),
            ("the bright side pulls the centre towards it:", INK, "normal"),
            ("a fraction of a pixel, and 1 pixel is several km", INK, "normal")]
    for k, (r, col, wt) in enumerate(rows):
        b.append(text(tx, 90 + 30 * k, r, 12.5, col, "start", wt))
    save("centroid.svg", w, h, "".join(b))


def two_roots():
    a, A = round(CAP_ALT, 4), round(CAP_AZ, 4)
    p = math.sin(math.radians(a))
    q = math.cos(math.radians(a)) * math.cos(math.radians(A))
    Rr = math.hypot(p, q)
    psi = math.degrees(math.atan2(q, p))
    sd = math.sin(math.radians(CAP_DEC))
    w, h = 660, 350
    x0, y0, W, H = 60, 40, 470, 220
    X = lambda phi: x0 + W * (phi + 90.0) / 180.0                        # noqa: E731
    Y = lambda val: y0 + H * (1.25 - val) / 2.25                          # noqa: E731
    b = [text(320, 24, "Which latitudes φ give the measured altitude?", 14, INK, weight="bold"),
         line(x0, Y(0), x0 + W, Y(0), GREY, 0.8), line(x0, y0, x0, y0 + H, INK), line(x0, y0 + H, x0 + W, y0 + H, INK)]
    for phi in (-90, -45, 0, 45, 90):
        b.append(text(X(phi), y0 + H + 16, f"{phi}°", 11, GREY))
    b.append(text(x0 + W / 2, y0 + H + 34, "latitude φ", 12, INK))
    for val in (-1, 0, 1):
        b.append(text(x0 - 6, Y(val) + 4, f"{val}", 11, GREY, "end"))
    phis = np.linspace(-90, 90, 181)
    b.append(poly([X(f) for f in phis], [Y(Rr * math.sin(math.radians(f + psi))) for f in phis], BLUE, 2.2))
    b.append(text(X(-85), Y(Rr * math.sin(math.radians(-85 + psi))) - 8, "sin a·sin φ + cos a·cos A·cos φ = R·sin(φ + ψ)",
                  11.5, BLUE, "start"))
    b.append(line(x0, Y(sd), x0 + W, Y(sd), ORANGE, 1.6, "6 4"))
    b.append(text(x0 + W + 6, Y(sd) + 8, f"sin δ = {sd:.4f}", 11.5, ORANGE, "start"))
    b.append(line(x0, Y(Rr), x0 + W, Y(Rr), GREY, 1.0, "2 3"))
    b.append(text(x0 + W + 6, Y(Rr) + 2, f"R = {Rr:.4f}", 11.5, GREY, "start"))
    b.append(line(x0, Y(0.93), x0 + W, Y(0.93), RED, 1.2, "6 4"))
    b.append(text(x0 + W + 6, Y(0.93) - 4, "no root", 11.5, RED, "start"))
    b.append(text(330, 324, "dotted: the top of the curve, R — if sin δ = R the two roots merge (|H| = 90°);", 11, GREY))
    b.append(text(330, 340, "dashed red: a line above the top (|sin δ| > R) meets the curve nowhere: no root at all", 11, GREY))
    for (la, lo), col, lab in ((ROOTS[0], RED, "root 1 (asin)"), (ROOTS[1], GREEN, "root 2")):
        b.append(circle(X(la), Y(sd), 6, col, col))
        b.append(text(X(la), Y(sd) + 22, f"{lab}: {la:.2f}°", 12, col, weight="bold"))
    b.append(text(330, 306, f"Capella from London: a = {a:.2f}°, A = {A:.2f}° → R = {Rr:.4f}, ψ = {psi:.2f}°", 12, GREY))
    save("two_roots.svg", w, h, "".join(b))


def budget():
    w, h = 660, 340
    b = [text(330, 24, "An attitude error becomes a position error", 14, INK, weight="bold")]
    cx, cy, R = 170, 280, 115
    b.append(f'<path d="M{cx - R},{cy} A{R},{R} 0 0 1 {cx + R},{cy}" stroke="{GREY}" fill="#e8eef3" stroke-width="1.5"/>')
    b.append(text(cx, cy + 20, "the Earth", 11, GREY))
    t1, t2 = math.radians(90), math.radians(78)
    for t, col, lab in ((t1, GREEN, "true"), (t2, RED, "computed")):
        x, y = cx + R * math.cos(t), cy - R * math.sin(t)
        b.append(circle(x, y, 5, col, col))
        b.append(arrow(x, y, x + 70 * math.cos(t), y - 70 * math.sin(t), col, "n" if col == GREEN else "r", 2.0))
        b.append(text(x + 80 * math.cos(t) + (4 if col == RED else -4), y - 80 * math.sin(t) - 4, f"zenith ({lab})", 11,
                      col, "start" if col == RED else "end"))
    b.append(text(cx + 48, cy - R + 26, "ε", 15, RED, weight="bold"))
    rows = [("the IMU tilts the sky by ε  →  your zenith moves by ε", INK, "bold"),
            ("→  your position moves ε × 111.2 km", INK, "normal"),
            ("1° = 111.2 km;   1′ = 1.852 km (one nautical mile)", BLUE, "normal"),
            ("a heading error turns the sky about the vertical:", INK, "normal"),
            ("it moves the camera's direction by heading × cos(alt)", INK, "normal"),
            ("independent errors: √(tilt² + (heading·cos alt)²)", RED, "bold")]
    for k, (r, col, wt) in enumerate(rows):
        b.append(text(345, 90 + 32 * k, r, 12.5, col, "start", wt))
    b.append(text(330, 330, "(the one-direction method of lesson §6; with the plate solve's whole rotation the heading "
                            "drops out)", 10.5, GREY))
    save("budget.svg", w, h, "".join(b))


def polaris():
    w, h = 620, 300
    b = [text(310, 24, "Polaris circles the pole: correct the altitude with its hour angle", 14, INK, weight="bold")]
    hx, hy = 60, 250
    b.append(line(30, hy, 330, hy, GREEN, 2.0))
    b.append(text(40, hy + 18, "northern horizon", 11, GREEN, "start"))
    phi = 40
    px, py = hx + 200 * math.cos(math.radians(phi)), hy - 200 * math.sin(math.radians(phi))
    b.append(line(hx, hy, px, py, INK, 1.0, "4 3"))
    b.append(f'<path d="M{hx + 60},{hy} A60,60 0 0 0 {hx + 60 * math.cos(math.radians(phi)):.1f},'
             f'{hy - 60 * math.sin(math.radians(phi)):.1f}" stroke="{BLUE}" fill="none" stroke-width="2"/>')
    b.append(text(hx + 70, hy - 18, "φ", 15, BLUE, "start", "bold"))
    b.append(circle(px, py, 4, INK, INK))
    b.append(text(px + 4, py + 18, "pole", 11, INK, "start"))
    b.append(circle(px, py, 34, ORANGE, width=1.4, dash="4 3"))
    pl = (px, py - 34)
    b.append(circle(pl[0], pl[1], 5, ORANGE, ORANGE))
    b.append(text(pl[0] + 8, pl[1] - 4, "Polaris at H = 0° (above the pole)", 11, ORANGE, "start"))
    b.append(text(px + 40, py + 30, "radius p = 90° − δ", 11, ORANGE, "start"))
    rows = [("the pole stands φ above the horizon:", INK, "bold"),
            ("altitude of the pole = your latitude", INK, "normal"),
            ("Polaris is p ≈ 0.63° away from it (2026)", INK, "normal"),
            ("its altitude: a ≈ φ + p·cos H", INK, "normal"),
            ("so  φ ≈ a − p·cos H", RED, "bold"),
            ("left out: p² terms, refraction, the horizon's dip", GREY, "normal")]
    for k, (r, col, wt) in enumerate(rows):
        b.append(text(350, 70 + 30 * k, r, 12.5, col, "start", wt))
    save("polaris.svg", w, h, "".join(b))


if __name__ == "__main__":
    print(f"worked example: JD {JD:.6f}, GMST {GST:.4f}°, Capella of date {CAP_RA:.4f}°, {CAP_DEC:.4f}°, "
          f"alt {CAP_ALT:.4f}°, az {CAP_AZ:.4f}°, roots {ROOTS}")
    cold_open()
    sphere()
    triangle()
    centroid()
    two_roots()
    budget()
    polaris()
