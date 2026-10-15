#!/usr/bin/env python3
"""Teacher only — draws the four figures of lesson 30 into courses/30-spoofing/assets/.

    python3 solutions/30-spoofing/make_figures.py

Every number drawn is computed here with the course reference (solutions/30-spoofing/navera_lite/spoof.py) and the
lab's scenarios.py. The cold open uses a 2 m/s drift with another noise seed than the lab, so it shows the story
without giving away the lab's numbers.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
COURSE = os.path.join(ACADEMY, "courses", "30-spoofing")
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(COURSE, "files"))
from navera_lite import spoof as S                          # noqa: E402
from navera_lite.geo import enu_flat                        # noqa: E402
from navera_lite.settings import DEFAULTS                   # noqa: E402
import scenarios                                            # noqa: E402

OUT = os.path.join(COURSE, "assets")
INK, BLUE, RED, AMBER, GREY, BG, GREEN, SEA, LAND = ("#1d2733", "#0b6e8a", "#d64545", "#c98a06", "#8a96a3", "#f7fafc",
                                                     "#2e9e4f", "#dcecf5", "#efe9dc")
HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {{w}} {{h}}" font-family="sans-serif" font-size="13">'
        f'<rect width="{{w}}" height="{{h}}" fill="{BG}"/><defs>'
        + "".join(f'<marker id="m{n}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                  f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
                  for n, c in (("i", INK), ("r", RED), ("b", BLUE), ("a", AMBER), ("g", GREEN)))
        + "</defs>")


def text(x, y, s, size=13, color=INK, anchor="middle", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}">{s}</text>')


def line(x1, y1, x2, y2, color=INK, width=1.0, dash="", marker=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#m{marker})"' if marker else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{d}{m}/>'


def poly(xs, ys, color, width=2.0, dash="", fill="none"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline points="{pts}" fill="{fill}" stroke="{color}" stroke-width="{width}"{d} stroke-linejoin="round"/>'


def path(d, color, width=2.0, fill="none", marker=""):
    m = f' marker-end="url(#m{marker})"' if marker else ""
    return f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}"{m}/>'


def save(name, w, h, body):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(HEAD.format(w=w, h=h) + "".join(body) + "</svg>\n")
    print("wrote", name)


# ------------------------------------------------------------------------------------------- cold open
def cold_open():
    rows = scenarios.build("drift", seed=7, drift_mps=2.0)
    cfg = dict(DEFAULTS, max_speed_mps=30.0)
    g = S.SpoofGuard(cfg)
    gps, vis = [], []
    for _, e, off, la0, lo0 in rows:
        v = g.check(e)
        x, y = enu_flat(scenarios.START[0], scenarios.START[1], e.lat, e.lon)
        if e.source == "gps":
            gps.append((x, y, v[0], e.stamp_s))
        else:
            vis.append((x, y))
    gps = [p for p in gps if p[3] <= 90]
    vis = [p for p in vis if p[1] <= gps[-1][1] + 10]
    W, H = 760, 330
    x0, sx = 230.0, 1.6                     # east metres → px
    y0, sy = 300.0, 0.205                   # north metres → px (up)
    X = lambda e: x0 + sx * e                                     # noqa: E731
    Y = lambda n: y0 - sy * n                                     # noqa: E731
    b = [f'<rect x="0" y="0" width="{X(-40):.0f}" height="{H}" fill="{LAND}"/>',
         f'<rect x="{X(-40):.0f}" y="0" width="{W - X(-40):.0f}" height="{H}" fill="{SEA}"/>',
         text(X(-40) - 8, 22, "land", 12, GREY, "end"), text(X(-40) + 8, 22, "sea", 12, BLUE, "start"),
         line(X(0), Y(0), X(0), Y(15 * 90), INK, 1.5, "5 4"), line(X(-40) - 4, Y(700), X(0) - 4, Y(700), INK, 1.0),
         text(X(-40) - 8, Y(700) + 4, "true track", 12, INK, "end")]
    b += [f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.6" fill="{BLUE}"/>' for x, y in vis]
    col = {"TRUSTED": GREEN, "IN_DOUBT": AMBER, "REFUSED": RED}
    b += [f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.6" fill="{col[v]}"/>' for x, y, v, _ in gps]
    first = {}
    for x, y, v, t in gps:
        first.setdefault(v, (x, y, t))
    for v, dy, lab in (("IN_DOUBT", 22, "IN DOUBT: GPS kept, but DEGRADED"),
                       ("REFUSED", 28, "REFUSED: the judge flies on vision")):
        if v in first:
            x, y, t = first[v]
            b += [line(X(x) + 6, Y(y) + 3, X(x) + 70, Y(y) + dy, col[v], 1.2),
                  text(X(x) + 74, Y(y) + dy + 4, lab, 12, col[v], "start")]
    lx = 540
    b += [f'<rect x="{lx - 10}" y="40" width="225" height="100" rx="6" fill="#ffffff" fill-opacity="0.85"/>']
    b += [text(lx, 57, "GPS fix, guard says:", 12, INK, "start"),
          f'<circle cx="{lx + 6}" cy="71" r="4" fill="{GREEN}"/>', text(lx + 16, 75, "TRUSTED", 12, INK, "start"),
          f'<circle cx="{lx + 96}" cy="71" r="4" fill="{AMBER}"/>', text(lx + 106, 75, "IN DOUBT", 12, INK, "start"),
          f'<circle cx="{lx + 6}" cy="89" r="4" fill="{RED}"/>', text(lx + 16, 93, "REFUSED", 12, INK, "start"),
          f'<circle cx="{lx + 96}" cy="89" r="4" fill="{BLUE}"/>', text(lx + 106, 93, "vision fix", 12, INK, "start"),
          text(lx, 113, "The spoofer pulls the GPS east a little", 11, GREY, "start"),
          text(lx, 127, "more every second; vision sees the truth.", 11, GREY, "start"),
          text(W / 2, H - 8, "Drone flying north along a coast (schematic; east scale ×8 the north scale)", 11, GREY)]
    save("cold_open.svg", W, H, b)


# ------------------------------------------------------------------------------------------- the jump gate's hole
def gate():
    v, s, m, D = 20.0, 8.0, 50.0, 1500.0
    dt = S.patient_accept_time(D, s, v, m)
    W, H = 760, 300
    x0, x1, y0, y1 = 70.0, 720.0, 250.0, 40.0
    T, R = 110.0, 2400.0
    X = lambda t: x0 + (x1 - x0) * t / T                          # noqa: E731
    Y = lambda r: y0 - (y0 - y1) * r / R                          # noqa: E731
    ts = np.linspace(0, T, 111)
    b = [line(x0, y0, x1, y0, INK, 1.2, marker="i"), line(x0, y0, x0, y1 - 10, INK, 1.2, marker="i"),
         text(x1, y0 + 38, "Δt since the last trusted fix (s)", 12, INK, "end"),
         text(x0 - 8, y1 - 16, "distance (m)", 12, INK, "start")]
    for t in range(0, 111, 20):
        b += [line(X(t), y0, X(t), y0 + 5, INK), text(X(t), y0 + 18, f"{t}", 11)]
    for r in range(0, 2401, 500):
        b += [line(x0 - 5, Y(r), x0, Y(r), INK), text(x0 - 9, Y(r) + 4, f"{r}", 11, INK, "end")]
    b += [poly([X(t) for t in ts], [Y(v * t + m) for t in ts], GREEN, 2.5),
          poly([X(t) for t in ts], [Y(math.hypot(s * t, D)) for t in ts], RED, 2.5),
          line(X(dt), y0, X(dt), Y(v * dt + m), GREY, 1.0, "4 3"),
          f'<circle cx="{X(dt):.1f}" cy="{Y(v * dt + m):.1f}" r="5" fill="{INK}"/>',
          text(X(dt) + 8, Y(v * dt + m) - 10, f"accepted after {dt:.1f} s", 13, INK, "start", "bold"),
          text(X(30) + 6, Y(v * 30 + m) + 22, "allowed: v_max·Δt + m (20 m/s, 50 m)", 12, GREEN, "start"),
          text(X(8), Y(math.hypot(s * 8, D)) - 10, "the spoof: √((s·Δt)² + D²), boat at 8 m/s, D = 1 500 m", 12, RED,
               "start"),
          text(X(dt) + 8, Y(v * dt + m) + 40, "after this, the TRUE GPS", 11, GREY, "start"),
          text(X(dt) + 8, Y(v * dt + m) + 54, "is the one refused", 11, GREY, "start")]
    save("gate.svg", W, H, b)


# ------------------------------------------------------------------------------------------- H0, H1, threshold
def hypothesis():
    gamma = S.chi2_threshold_2d(0.01)
    lam = 60.0 ** 2 / 243.0
    x = np.linspace(0.0, 45.0, 4501)
    p0 = 0.5 * np.exp(-x / 2)
    p1 = 0.5 * np.exp(-(x + lam) / 2) * np.i0(np.sqrt(lam * x))
    dx = x[1] - x[0]
    pmd = float(np.sum(p1[x <= gamma]) * dx)
    pfa = float(np.exp(-gamma / 2))
    W, H = 760, 320
    x0, x1, y0, y1 = 60.0, 720.0, 250.0, 50.0
    X = lambda v: x0 + (x1 - x0) * v / 45.0                        # noqa: E731
    Y = lambda p: y0 - (y0 - y1) * p / 0.5                         # noqa: E731
    sel = x <= 45
    b = [line(x0, y0, x1, y0, INK, 1.2, marker="i"), text(x1, y0 + 34, "test statistic d² = rᵀ S⁻¹ r", 12, INK, "end"),
         text(x0, y1 - 18, "probability density", 12, INK, "start")]
    for t in range(0, 46, 5):
        b += [line(X(t), y0, X(t), y0 + 5, INK), text(X(t), y0 + 18, f"{t}", 11)]
    fa = x >= gamma
    b += [poly([X(v) for v in x[fa][::10]] + [X(45), X(gamma)], [Y(p) for p in p0[fa][::10]] + [Y(0), Y(0)], "none", 0,
               fill="#9fcfe0"),
          poly([X(v) for v in x[~fa][::5]] + [X(gamma), X(0)], [Y(p) for p in p1[~fa][::5]] + [Y(0), Y(0)], "none", 0,
               fill="#f6e2b3"),
          poly([X(v) for v in x[sel][::10]], [Y(min(p, 0.5)) for p in p0[sel][::10]], BLUE, 2.5),
          poly([X(v) for v in x[sel][::10]], [Y(p) for p in p1[sel][::10]], RED, 2.5),
          line(X(gamma), y0, X(gamma), y1 + 10, INK, 1.5, "5 4"),
          text(X(gamma) + 6, y1 + 20, f"threshold γ = {gamma:.2f} (P_FA 1 %)", 12, INK, "start", "bold"),
          line(X(gamma) + 8, Y(0.30), X(2.6), Y(0.14), BLUE, 1.0),
          text(X(gamma) + 12, Y(0.30), "H0: GPS honest", 13, BLUE, "start", "bold"),
          text(X(gamma) + 12, Y(0.30) + 16, "χ² law, 2 degrees of freedom", 12, BLUE, "start"),
          text(X(24), Y(0.075), "H1: GPS pulled 60 m away", 13, RED, "start", "bold"),
          text(X(24), Y(0.075) + 16, f"(S = 243·I: d² centred near {lam + 2:.0f})", 12, RED, "start"),
          text(X(gamma) + 6, Y(0.115), f"false alarms: {100 * pfa:.0f} % (H0's tail beyond γ: too thin to see)", 12,
               BLUE, "start"),
          text(X(gamma) - 6, Y(0.115), f"missed: {100 * pmd:.0f} %", 12, AMBER, "end"),
          text(X(gamma) - 6, Y(0.115) + 14, "(yellow area)", 11, AMBER, "end"),
          text(W / 2, H - 10, "Move γ right: fewer false alarms, more missed attacks. Move it left: the opposite.", 12,
               GREY)]
    save("hypothesis.svg", W, H, b)
    return pfa, pmd


# ------------------------------------------------------------------------------------------- the guard's states
def guard_states():
    W, H = 760, 330
    box = {"TRUSTED": (110, 165, GREEN), "IN_DOUBT": (380, 70, AMBER), "REFUSED": (650, 165, RED)}
    b = []
    for name, (cx, cy, col) in box.items():
        b += [f'<rect x="{cx - 75}" y="{cy - 24}" width="150" height="48" rx="10" fill="#ffffff" stroke="{col}" '
              f'stroke-width="2.5"/>', text(cx, cy + 5, name.replace("_", " "), 15, col, weight="bold")]
    b += [text(110, 210, "GPS used as it is", 11, GREY), text(380, 115, "GPS used, widened to the gap:", 11, GREY),
          text(380, 129, "the judge says DEGRADED", 11, GREY), text(650, 210, "GPS not used:", 11, GREY),
          text(650, 224, "the judge flies on vision", 11, GREY)]
    b += [path("M150 141 Q 210 70 305 66", AMBER, 2, marker="a"),
          text(150, 58, "2 tests in a row d² > γ", 12, AMBER, "start"),
          text(150, 73, "(gap ≤ 500 m)", 11, AMBER, "start"),
          path("M310 92 Q 230 135 186 160", GREEN, 2, marker="g"),
          text(268, 150, "1 test d² ≤ γ", 12, GREEN, "start"),
          path("M455 66 Q 560 70 612 141", RED, 2, marker="r"),
          text(470, 24, "5 in a row d² > γ, or", 12, RED, "start"),
          text(470, 38, "2 in a row d² > γ_far, a jump,", 12, RED, "start"),
          text(470, 52, "or back from an outage", 12, RED, "start"),
          path("M185 178 L 575 178", RED, 2, marker="r"),
          text(400, 170, "a jump · 2 in a row d² > γ_far · back from an outage (reference heard)", 11, RED),
          path("M575 196 Q 380 290 185 196", GREEN, 2, marker="g"),
          text(380, 262, "2 reference fixes in a row agree (d² ≤ γ): confirmed", 12, GREEN),
          text(380, 278, "or, with no stated reference for 120 s: the jump gate says reachable again", 11, GREEN),
          text(W / 2, H - 12, "Every arrow needs evidence; the way back needs more evidence than the way out "
                              "(hysteresis).", 12, GREY)]
    save("guard_states.svg", W, H, b)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cold_open()
    gate()
    pfa, pmd = hypothesis()
    print(f"hypothesis: P_FA {pfa:.4f}, P_MD {pmd:.4f} (60 m, S = 243·I)")
    guard_states()
