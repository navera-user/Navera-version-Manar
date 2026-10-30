#!/usr/bin/env python3
"""Teacher only — draws the six figures of lesson 27 into courses/27-uncertainty/assets/.

    python3 solutions/27-uncertainty/make_figures.py

Every ellipse is computed here with the course reference (solutions/_navera_lite/navera_lite/uncertainty.py) from the
lesson's worked examples; the hook's numbers are NAVERA's (validation report 2026-10-01 long route, backlog QA-2).
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import uncertainty as U                    # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "27-uncertainty", "assets")
INK, BLUE, RED, ORANGE, GREY, BG, GREEN, PURPLE = ("#1d2733", "#0b6e8a", "#d64545", "#a8680d", "#8a96a3", "#f7fafc",
                                                   "#2e9e4f", "#7a4fb5")


def head(w, h):
    marks = "".join(f'<marker id="m{n}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                    f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
                    for n, c in (("i", INK), ("r", RED), ("b", BLUE), ("o", ORANGE), ("g", GREY), ("n", GREEN)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="13">'
            f'<rect width="{w}" height="{h}" fill="{BG}"/><defs>{marks}</defs>')


def text(x, y, s, size=13, color=INK, anchor="middle", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}">{s}</text>')


def line(x1, y1, x2, y2, color=INK, width=1.2, dash="", arrow=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#m{arrow})"' if arrow else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{d}{m}/>'


def circle(x, y, r, color=INK, fill="none", width=1.5, dash="", opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" stroke="{color}" fill="{fill}" stroke-width="{width}"{d} '
            f'fill-opacity="{opacity}"/>')


def ell(cx, cy, a, b, ang_deg, color=INK, width=1.8, dash="", fill="none", opacity=0.15):
    """An ellipse in screen pixels; ang_deg from east towards north (screen y goes DOWN, hence the minus)."""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{a:.1f}" ry="{b:.1f}" transform="rotate({-ang_deg:.2f} {cx:.1f} '
            f'{cy:.1f})" stroke="{color}" fill="{fill}" fill-opacity="{opacity}" stroke-width="{width}"{d}/>')


def dot(x, y, color=INK, r=4.0):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>'


def save(name, body, w, h):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(head(w, h) + body + "</svg>\n")
    print("wrote", name)


# ------------------------------------------------------------------ 1. cold open
def cold_open():
    w, h = 760, 340
    s = [text(w / 2, 26, "What the autopilot was told, and what was true (NAVERA's simulator, 2026)", 15, weight="bold")]
    # panel A: vision over uniform terrain — log-normal radial errors with the measured median (351 m) and p90 (853 m)
    cx, cy, k = 190, 180, 0.085                     # px per metre
    s.append(text(cx, 52, "1 Oct · desert route, GPS jammed: day vision", 13, BLUE, weight="bold"))
    rng = np.random.default_rng(3)
    sig = math.log(853.0 / 351.0) / 1.2816
    from statistics import NormalDist
    for i in range(90):                                    # quantile-matched: 45 dots inside 351 m, 9 beyond 853 m
        r = min(351.0 * math.exp(sig * NormalDist().inv_cdf((i + 0.5) / 90)), 1100.0)   # clear of the caption
        t = rng.uniform(0, 2 * math.pi)
        s.append(dot(cx + k * r * math.cos(t), cy + k * r * math.sin(t), GREY, 2.0))
    s.append(circle(cx, cy, 853 * k, GREY, width=1.0, dash="2 3"))
    s.append(circle(cx, cy, 300 * k, RED, width=2.2))
    s.append(circle(cx, cy, 500 * k, ORANGE, width=2.0, dash="6 4"))
    s.append(circle(cx, cy, 100 * k, INK, width=1.6))
    s.append(dot(cx, cy, INK, 3))
    s.append(text(cx + 853 * k * 0.72 + 4, cy - 853 * k * 0.72 - 2, "p90: 853 m", 11, GREY, "start"))
    s.append(text(cx + 300 * k + 4, cy + 4, "told ±300 m", 11, RED, "start"))
    s.append(text(cx - 500 * k - 4, cy + 4, "±500 m", 11, ORANGE, "end"))
    s.append(text(cx - 46, cy - 104, "used: ±100 m", 10, INK, "end"))
    s.append(line(cx - 44, cy - 100, cx - 6, cy - 6, INK, 0.8))
    s.append(text(cx, 294, "matches: median error 351 m, a long tail (p90 853 m)", 12))
    s.append(text(cx, 312, "told ±300 m, the autopilot used ±100 m → failsafe after 45 s", 12, RED))
    s.append(text(cx, 328, "(a second flight told ±500 m: 91 s — also used as ±100 m)", 11, GREY))
    # panel B: a star fix, to scale (0.6 px per km)
    bx, by, kk = 520, 185, 0.6
    s.append(text(560, 52, "30 Sep · QA campaign: a star (celestial) fix", 13, BLUE, weight="bold"))
    fx = bx + 125 * kk
    s.append(circle(fx, by, 55 * kk, PURPLE, fill=PURPLE, opacity=0.08, width=2))
    s.append(dot(bx, by, INK, 4))
    s.append(text(bx - 6, by + 20, "where the drone was", 11, INK, "end"))
    s.append(dot(fx, by, RED, 5))
    s.append(line(bx + 5, by, fx - 6, by, RED, 1.6, arrow="r"))
    s.append(text(fx + 4, by - 40, "the fix, stated by the star", 11, PURPLE, "start"))
    s.append(text(fx + 4, by - 26, "solver as ±55 km (circle)", 11, PURPLE, "start"))
    s.append(text(fx + 4, by + 46, "forwarded as ±300 m:", 11, RED, "start"))
    s.append(text(fx + 4, by + 60, "too small to see here", 11, RED, "start"))
    s.append(text(bx + 125 * kk / 2, by - 8, "125 km", 11, RED))
    s.append(text(560, 294, "it reached the autopilot as ±300 m:", 12))
    s.append(text(560, 312, "the autopilot's own position jumped 125 km", 12, RED))
    s.append(text(560, 328, "(drawn to scale: 0.6 px per km)", 11, GREY))
    s.append(line(380, 50, 380, 330, GREY, 1, "3 4"))
    save("cold_open.svg", "".join(s), w, h)


# ------------------------------------------------------------------ 2. ellipse
def ellipse_fig():
    w, h = 820, 380
    P = np.array([[12.0, 5.0], [5.0, 6.0]])
    a, b, ang = U.ellipse(P)
    sc = 40.0
    cx, cy = 210, 215
    s = [text(w / 2, 24, "P = [[12, 5], [5, 6]] m² is an ellipse", 15, weight="bold")]
    s.append(line(cx - 190, cy, cx + 200, cy, GREY, 1, arrow="g"))
    s.append(line(cx, cy + 150, cx, cy - 165, GREY, 1, arrow="g"))
    s.append(text(cx + 192, cy + 18, "east", 12, GREY))
    s.append(text(cx + 24, cy - 152, "north", 12, GREY))
    sx, sy = math.sqrt(12.0) * sc, math.sqrt(6.0) * sc
    s.append(f'<rect x="{cx - sx:.1f}" y="{cy - sy:.1f}" width="{2 * sx:.1f}" height="{2 * sy:.1f}" fill="none" '
             f'stroke="{GREY}" stroke-dasharray="4 4"/>')
    s.append(ell(cx, cy, a * sc, b * sc, ang, RED, 2.2, fill=RED, opacity=0.08))
    t = math.radians(ang)
    s.append(line(cx, cy, cx + a * sc * math.cos(t), cy - a * sc * math.sin(t), RED, 2.2, arrow="r"))
    s.append(line(cx, cy, cx - b * sc * math.sin(t), cy - b * sc * math.cos(t), BLUE, 2.2, arrow="b"))
    s.append(text(cx + a * sc * math.cos(t) + 10, cy - a * sc * math.sin(t) - 4, f"a_m = √λ₁ = {a:.2f} m", 13, RED, "start"))
    s.append(text(cx - b * sc * math.sin(t) + 30, cy - b * sc * math.cos(t) - 62, f"b_m = √λ₂ = {b:.2f} m", 13, BLUE, "end"))
    s.append(f'<path d="M{cx + 45:.1f} {cy:.1f} A45 45 0 0 0 {cx + 45 * math.cos(t):.1f} {cy - 45 * math.sin(t):.1f}" '
             f'fill="none" stroke="{INK}"/>')
    s.append(text(cx + 58, cy - 10, f"θ = {ang:.1f}°", 12, INK, "start"))
    s.append(line(cx, cy + 3, cx + sx, cy + 3, ORANGE, 2.4))
    s.append(text(cx + sx / 2, cy + 20, f"σE = √12 = {math.sqrt(12):.2f} m", 12, ORANGE))
    x0 = 530
    for i, (txt, col) in enumerate((("λ = (a + c)/2 ± √(((a − c)/2)² + b²)", INK), ("   = 9 ± √(3² + 5²) = 14.83 and 3.17", INK),
                                    ("θ = ½·atan2(2b, a − c) = ½·atan2(10, 6)", INK), ("   = 29.5° north of east", INK),
                                    ("", INK), ("the judge's σ = √max(a, c) = 3.46 m", ORANGE),
                                    ("the long axis = 3.85 m (at most √2 more)", RED),
                                    ("dashed box: ±σE, ±σN — the diagonal only", GREY))):
        s.append(text(x0, 90 + 26 * i, txt, 12, col, "start"))
    save("ellipse.svg", "".join(s), w, h)


# ------------------------------------------------------------------ 3. inside: 1-D vs 2-D
def inside_fig():
    w, h = 700, 360
    s = [text(w / 2, 24, "The same σ holds fewer errors on a map than on one axis", 15, weight="bold")]
    # left: normal curve
    x0, y0, sx, sy = 40, 290, 50, 400
    xs = np.linspace(-3.4, 3.4, 140)
    ys = np.exp(-xs ** 2 / 2) / math.sqrt(2 * math.pi)
    pts = " ".join(f"{x0 + (x + 3.4) * sx:.1f},{y0 - y * sy:.1f}" for x, y in zip(xs, ys))
    s.append(f'<polyline points="{pts}" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    m = xs[np.abs(xs) <= 1]
    poly = f"{x0 + (m[0] + 3.4) * sx:.1f},{y0} " + " ".join(f"{x0 + (x + 3.4) * sx:.1f},{y0 - math.exp(-x * x / 2) / math.sqrt(2 * math.pi) * sy:.1f}" for x in m) + f" {x0 + (m[-1] + 3.4) * sx:.1f},{y0}"
    s.append(f'<polygon points="{poly}" fill="{BLUE}" fill-opacity="0.18"/>')
    s.append(line(x0, y0, x0 + 6.8 * sx, y0, GREY))
    for k in (-3, -2, -1, 0, 1, 2, 3):
        s.append(line(x0 + (k + 3.4) * sx, y0, x0 + (k + 3.4) * sx, y0 + 5, GREY))
        s.append(text(x0 + (k + 3.4) * sx, y0 + 19, f"{k}σ" if k else "0", 11, GREY))
    s.append(text(x0 + 3.4 * sx, 60, "ONE axis: within ±1σ", 13, BLUE, weight="bold"))
    s.append(text(x0 + 3.4 * sx, 80, f"{100 * U.p_inside(1, 1):.1f} %  ·  ±2σ: {100 * U.p_inside(2, 1):.1f} %  ·  ±3σ: "
                                     f"{100 * U.p_inside(3, 1):.1f} %", 12))
    # right: rings with a 2-D cloud
    cx, cy, r1 = 540, 215, 30
    rng = np.random.default_rng(5)
    xy = rng.standard_normal((300, 2))
    for x, y in xy:
        d2 = x * x + y * y
        s.append(dot(cx + x * r1, cy - y * r1, RED if d2 <= 1 else GREY, 1.8))
    for k, dash in ((1, ""), (2, "5 4"), (3, "2 4")):
        s.append(circle(cx, cy, k * r1, INK, width=1.4, dash=dash))
        s.append(text(cx + k * r1 * 0.72 + 4, cy - k * r1 * 0.72 - 2, f"{k}σ", 11, INK, "start"))
    inside1 = 100 * np.mean((xy ** 2).sum(axis=1) <= 1)
    s.append(text(cx, 60, "A MAP: inside the 1-sigma circle (ellipse)", 13, RED, weight="bold"))
    s.append(text(cx, 80, f"{100 * U.p_inside(1):.1f} %  ·  2σ: {100 * U.p_inside(2):.1f} %  ·  3σ: "
                          f"{100 * U.p_inside(3):.1f} %", 12))
    s.append(text(cx, 340, f"300 honest errors drawn: {inside1:.0f} % in red inside 1σ", 11, GREY))
    s.append(text(x0 + 3.4 * sx, 340, "on one axis, d² = x² (χ² with 1 degree of freedom)", 11, GREY))
    save("inside.svg", "".join(s), w, h)


# ------------------------------------------------------------------ 4. radar
def radar_fig():
    w, h = 720, 340
    s = [text(w / 2, 24, "Range ± bearing: an ellipse across the line of sight — until the bearing error is large",
              14, weight="bold")]
    # left: small bearing error, the ellipse
    rx, ry = 70, 300                                  # radar position on screen
    sc = 0.11                                         # px per metre
    r0, b0 = 2000.0, 60.0
    en, P = U.polar_to_en(r0, b0, 5.0, 0.5)
    a, b, ang = U.ellipse(P, k=3)
    tx, ty = rx + en[0] * sc, ry - en[1] * sc
    s.append(line(rx, ry, tx, ty, GREY, 1.2, "5 4"))
    s.append(dot(rx, ry, INK, 5))
    s.append(text(rx, ry + 20, "radar", 12))
    zoom = 2.2
    s.append(ell(tx, ty, a * zoom, b * zoom, ang, RED, 2.0, fill=RED, opacity=0.1))
    s.append(dot(tx, ty, RED, 3))
    s.append(text(30, 122, "3-sigma ellipse (enlarged 20×):", 11, RED, "start"))
    s.append(text(30, 138, f"{3 * 17.5:.0f} m across, {3 * 5:.0f} m along", 11, RED, "start"))
    s.append(text(170, 64, "2 000 m, σr 5 m, σβ 0.5°", 13, BLUE, weight="bold"))
    s.append(text(170, 82, "J P Jᵀ is right: r·σβ = 17.5 m across", 12))
    # right: big bearing error, banana
    ox, oy = 410, 310
    sc2 = 0.075
    rng = np.random.default_rng(9)
    r = 3000 + 8 * rng.standard_normal(500)
    bb = np.radians(30 + 10 * rng.standard_normal(500))
    for e, n in zip(r * np.sin(bb), r * np.cos(bb)):
        s.append(dot(ox + e * sc2, oy - n * sc2, GREY, 1.4))
    en2, P2 = U.polar_to_en(3000.0, 30.0, 8.0, 10.0)
    a2, b2, g2 = U.ellipse(P2, k=math.sqrt(U.chi2_threshold(0.95)))
    s.append(ell(ox + en2[0] * sc2, oy - en2[1] * sc2, a2 * sc2, max(b2 * sc2, 1.0), g2, RED, 1.8))
    s.append(dot(ox, oy, INK, 5))
    s.append(text(ox, oy + 20, "radar", 12))
    s.append(text(560, 64, "3 000 m, bearing 30°, σr 8 m, σβ 10°", 13, BLUE, weight="bold"))
    s.append(text(610, 280, "the true cloud is an arc (grey):", 12))
    s.append(text(610, 298, "no ellipse fits it", 12))
    s.append(text(610, 316, "(red: the 95 % ellipse of J P Jᵀ)", 12, RED))
    s.append(line(360, 50, 360, 325, GREY, 1, "3 4"))
    save("radar.svg", "".join(s), w, h)


# ------------------------------------------------------------------ 5. gate
def gate_fig():
    w, h = 700, 330
    S = np.diag([1609.0, 109.0])
    sc = 1.9
    cx, cy = 260, 175
    s = [text(w / 2, 24, "The χ² gate knows directions: S = P_pred + R = diag(1 609, 109) m²", 15, weight="bold")]
    a99, b99, _ = U.ellipse(S, k=math.sqrt(U.chi2_threshold(0.99)))
    a95, b95, _ = U.ellipse(S, k=math.sqrt(U.chi2_threshold(0.95)))
    s.append(ell(cx, cy, a99 * sc, b99 * sc, 0, RED, 2.0, fill=RED, opacity=0.08))
    s.append(ell(cx, cy, a95 * sc, b95 * sc, 0, ORANGE, 1.5, dash="6 4"))
    s.append(circle(cx, cy, 50 * sc, GREY, width=1.2, dash="3 4"))
    s.append(line(cx - 50, cy, cx + 80, cy, BLUE, 1.5, arrow="b"))
    s.append(text(cx - 52, cy - 8, "track", 11, BLUE, "start"))
    s.append(dot(cx, cy, INK, 4))
    s.append(text(cx - 6, cy + 18, "prediction", 11, INK, "end"))
    s.append(dot(cx + 80 * sc, cy, GREEN, 6))
    s.append(line(cx + 80 * sc, cy - 6, cx + 80 * sc + 10, cy - 66, GREEN, 1, "2 3"))
    s.append(text(cx + 80 * sc + 12, cy - 72, "80 m east: d² = 3.98 ✓", 12, GREEN))
    s.append(dot(cx, cy - 40 * sc, INK, 6))
    s.append(line(cx, cy - 4, cx, cy - 40 * sc + 6, INK, 1, "2 3"))
    s.append(text(cx + 14, cy - 40 * sc - 26, "40 m north: d² = 14.7 ✗", 12, INK, "start"))
    s.append(text(cx + a99 * sc - 4, cy + 50 * sc + 14, f"99 %: up to {a99:.0f} m east, {b99:.0f} m north", 11, RED, "end"))
    s.append(text(cx - 50 * sc - 4, cy + 50 * sc + 2, "a 50 m circle gets both wrong", 11, GREY, "end"))
    x0 = 520
    for i, (t_, c_) in enumerate((("accept ⇔ rᵀ S⁻¹ r ≤ χ²₂(p)", INK), ("99 %: 9.21 · 95 %: 5.99", INK),
                                  ("", INK), ("red: 99 % gate", RED), ("orange dashed: 95 % gate", ORANGE),
                                  ("grey dotted: a 50 m circle", GREY))):
        s.append(text(x0, 230 + 18 * i - 100, t_, 12, c_, "start"))
    save("gate.svg", "".join(s), w, h)


# ------------------------------------------------------------------ 6. fusion
def fusion_fig():
    w, h = 720, 330
    sc = 3.4
    cx, cy = 150, 185
    P1, P2 = np.diag([900.0, 36.0]), np.diag([225.0, 225.0])
    x1, x2 = np.array([0.0, 0.0]), np.array([30.0, 10.0])
    x, P = U.fuse(x1, P1, x2, P2)
    s = [text(w / 2, 24, "Information adds: each estimate corrects the other where it is weak", 15, weight="bold")]
    a1, b1, _ = U.ellipse(P1)
    s.append(ell(cx, cy, a1 * sc, b1 * sc, 0, BLUE, 2, fill=BLUE, opacity=0.08))
    s.append(circle(cx + x2[0] * sc, cy - x2[1] * sc, 15 * sc, ORANGE, width=2, fill=ORANGE, opacity=0.08))
    af, bf, _ = U.ellipse(P)
    s.append(ell(cx + x[0] * sc, cy - x[1] * sc, af * sc, bf * sc, 0, GREEN, 2.4, fill=GREEN, opacity=0.25))
    s.append(dot(cx, cy, BLUE, 4))
    s.append(dot(cx + x2[0] * sc, cy - x2[1] * sc, ORANGE, 4))
    s.append(dot(cx + x[0] * sc, cy - x[1] * sc, GREEN, 4))
    s.append(text(cx - a1 * sc + 4, cy + b1 * sc + 62, "GPS in a canyon: σ 30 m east, 6 m north", 12, BLUE, "start"))
    s.append(text(cx + x2[0] * sc, cy - x2[1] * sc - 15 * sc - 8, "vision: σ 15 m", 12, ORANGE))
    s.append(text(cx + x[0] * sc + 78, cy - x[1] * sc + 2, f"fused: ({x[0]:.1f}, {x[1]:.1f}) m,", 12, GREEN, "start"))
    s.append(text(cx + x[0] * sc + 78, cy - x[1] * sc + 18, f"σ {math.sqrt(P[0, 0]):.1f} m × {math.sqrt(P[1, 1]):.1f} m",
                  12, GREEN, "start"))
    # outlier panel
    ox = 560
    s.append(line(430, 50, 430, 318, GREY, 1, "3 4"))
    s.append(text(ox, 64, "one wrong match at (300, 0) m", 13, RED, weight="bold"))
    s.append(text(ox, 86, "fused without a gate: east = 240 m", 12, RED))
    s.append(text(ox, 104, "its d² = 300²/1 125 = 80 → refused", 12, INK))
    s.append(text(ox, 122, "the good match (30, 10): d² = 1.18 → fused", 12, GREEN))
    xs = 470
    s.append(line(xs, 220, xs + 200, 220, GREY, 1))
    for k, lab in ((0, "0"), (100, "100"), (200, "200"), (300, "300 m")):
        s.append(line(xs + k * 0.62, 216, xs + k * 0.62, 224, GREY))
        s.append(text(xs + k * 0.62, 240, lab, 11, GREY))
    s.append(dot(xs, 220, BLUE, 5))
    s.append(dot(xs + 300 * 0.62, 220, RED, 5))
    s.append(dot(xs + 240 * 0.62, 220, PURPLE, 5))
    s.append(text(xs + 240 * 0.62, 206, "fused (wrong)", 11, PURPLE))
    s.append(text(xs, 206, "GPS", 11, BLUE))
    s.append(text(ox, 290, "gate first, then fuse", 13, INK, weight="bold"))
    save("fusion.svg", "".join(s), w, h)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cold_open()
    ellipse_fig()
    inside_fig()
    radar_fig()
    gate_fig()
    fusion_fig()
