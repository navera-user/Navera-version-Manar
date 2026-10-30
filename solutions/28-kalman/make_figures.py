#!/usr/bin/env python3
"""Teacher only — draws the figures of lesson 28 into courses/28-kalman/assets/.

    python3 solutions/28-kalman/make_figures.py

Every number drawn is computed here with the course reference (solutions/_navera_lite/navera_lite/kalman.py) or
quoted from NAVERA's VALIDATION_STATUS.md (Release 0.2, 2026-10-03: the long-route test of 2026-10-01). The
q-trade-off figure uses its OWN synthetic heights (seed 4040), never the lab's data, so it does not answer Step 4.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite.kalman import Height1D, cv_model, kf_predict, kf_update   # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "28-kalman", "assets")
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


def line(x1, y1, x2, y2, color=INK, width=1.0, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"{d}/>'


def arrow(x1, y1, x2, y2, color=INK, m="i", width=2.0):
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}" '
            f'marker-end="url(#m{m})"/>')


def poly(xs, ys, color, width=2.0, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{d} stroke-linejoin="round"/>'


def circle(x, y, r, color=INK, fill="none", width=1.5, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" stroke="{color}" fill="{fill}" stroke-width="{width}"{d}/>'


def rect(x, y, w, h, fill, stroke="none", rx=0, opacity=1.0):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" '
            f'rx="{rx}" fill-opacity="{opacity}"/>')


def save(name, w, h, body):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(HEAD.format(w=w, h=h) + body + "</svg>\n")
    print("wrote", name, os.path.getsize(os.path.join(OUT, name)), "bytes")


def axes(b, x0, y0, W, H, xlim, ylim, xticks, yticks, xlabel, ylabel, fmt="{:g}"):
    X = lambda v: x0 + W * (v - xlim[0]) / (xlim[1] - xlim[0])          # noqa: E731
    Y = lambda v: y0 + H - H * (v - ylim[0]) / (ylim[1] - ylim[0])      # noqa: E731
    b.append(line(x0, y0 + H, x0 + W, y0 + H, INK, 1.0))
    b.append(line(x0, y0, x0, y0 + H, INK, 1.0))
    for v in xticks:
        b.append(line(X(v), y0 + H, X(v), y0 + H + 4, INK))
        b.append(text(X(v), y0 + H + 17, fmt.format(v), 11, GREY))
    for v in yticks:
        b.append(line(x0 - 4, Y(v), x0 + W, Y(v), GREY if v else INK, 0.4, "2 3"))
        b.append(text(x0 - 7, Y(v) + 4, fmt.format(v), 11, GREY, "end"))
    b.append(text(x0 + W / 2, y0 + H + 34, xlabel, 12, INK))
    b.append(f'<text x="{x0 - 40}" y="{y0 + H / 2}" text-anchor="middle" font-size="12" fill="{INK}" '
             f'transform="rotate(-90 {x0 - 40} {y0 + H / 2})">{ylabel}</text>')
    return X, Y


# ----------------------------------------------------------------------------------------- 1 the cold open
def cold_open():
    """VALIDATION_STATUS.md (2026-10-03), Long route (simulator, 2026-10-01): day vision over uniform terrain near
    Gabès, GPS jammed; median 351 m, p90 853 m; forwarded at ±300 m → ArduCopter's EKF failed safe after 45 s;
    536-tile area ±300 m → 61 s; ±500 m → 91 s; with local feature matching the autopilot held 230 s (end of test)."""
    w, h = 900, 330
    b = [text(450, 26, "Simulator, 2026-10-01: GPS jammed over uniform terrain, the autopilot's Kalman filter fed by "
                       "NAVERA's day vision", 13, INK, weight="bold")]
    # left: stated vs measured
    x0, y0, W = 160, 70, 250
    sc = W / 900.0
    b.append(text(x0 + W / 2 - 40, 54, "what day vision SAID vs what it WAS", 12, INK, weight="bold"))
    rows = (("stated σ", 300, BLUE, "±300 m"), ("true error, median", 351, ORANGE, "351 m"),
            ("true error, 90 % below", 853, RED, "853 m"))
    for i, (lab, v, c, s) in enumerate(rows):
        y = y0 + 20 + i * 48
        b.append(text(x0 - 6, y + 15, lab, 11, INK, "end"))
        b.append(rect(x0, y, v * sc, 22, c, rx=3))
        b.append(text(x0 + 6 + v * sc, y + 16, s, 12, c, "start", "bold"))
    b.append(text(x0 + W / 2, y0 + 190, "the filter downstream was told ±300 m (and uses at most 100 m)", 11, GREY))
    # right: time to failsafe
    x1, W2 = 600, 260
    b.append(text(x1 + W2 / 2, 54, "time until the autopilot gave up (failsafe)", 12, INK, weight="bold"))
    sc2 = W2 / 240.0
    rows = (("stated ±300 m", 45, RED, "45 s"), ("stated ±300 m, small map", 61, RED, "61 s"),
            ("stated ±500 m", 91, ORANGE, "91 s"), ("local matching (later)", 230, GREEN, "held 230 s (end of test)"))
    for i, (lab, v, c, s) in enumerate(rows):
        y = y0 + 20 + i * 40
        b.append(text(x1 - 6, y + 15, lab, 11, INK, "end"))
        b.append(rect(x1, y, v * sc2, 20, c, rx=3, opacity=0.85))
        b.append(text(x1 + 6 + v * sc2 if v < 200 else x1 + v * sc2 - 6, y + 15, s, 11,
                      c if v < 200 else "#ffffff", "start" if v < 200 else "end", "bold"))
    b.append(text(450, 300, "Sources: NAVERA validation, troubleshooting and ArduPilot guides, Release 0.2 (2026-10-03) — "
                            "simulation, not a real flight.", 11, GREY))
    save("cold_open.svg", w, h, "".join(b))


# ----------------------------------------------------------------------------------------- 2 the sawtooth
def sawtooth():
    """§1 worked example: P0 = 100 m², w = 1 m²/s, R = 25 m², a measurement every second."""
    w, h = 820, 345
    b = [text(410, 24, "One number, two steps: predict (σ grows), update (σ shrinks)", 13, INK, weight="bold")]
    P, R, wq = 100.0, 25.0, 1.0
    ts, ss = [0.0], [math.sqrt(P)]
    for k in range(1, 9):
        P = P * R / (P + R)                                  # update at t = k − 1 (the first at t = 0)
        ts.append(k - 1.0)
        ss.append(math.sqrt(P))
        P = P + wq                                           # predict to t = k
        ts.append(float(k))
        ss.append(math.sqrt(P))
    pss = (-wq + math.sqrt(wq * wq + 4 * wq * R)) / 2.0
    X, Y = axes(b, 90, 50, 680, 220, (0, 8), (0, 10.5), range(0, 9), (0, 2, 4, 6, 8, 10), "time (s)", "σ (m)")
    b.append(poly([X(t) for t in ts], [Y(s) for s in ss], BLUE, 2.2))
    b.append(line(X(0), Y(5), X(8), Y(5), ORANGE, 1.2, "6 4"))
    b.append(text(X(8) - 4, Y(5) - 6, "a measurement alone: σ = 5 m", 11, ORANGE, "end"))
    b.append(line(X(0), Y(math.sqrt(pss)), X(8), Y(math.sqrt(pss)), GREEN, 1.0, "3 3"))
    b.append(text(X(8) - 4, Y(math.sqrt(pss)) + 14, f"settles at {math.sqrt(pss):.2f} m after each update", 11, GREEN,
                  "end"))
    b.append(text(X(0) + 8, Y(10) + 4, "start: σ 10 m", 11, BLUE, "start"))
    b.append(text(X(0.1), Y(math.sqrt(20)) + 40, "update at 0 s: 4.47 m", 11, BLUE, "start"))
    b.append(text(X(1.0) + 4, Y(math.sqrt(21)) - 26, "predict to 1 s: 4.58 m", 11, BLUE, "start"))
    b.append(line(X(1.0) + 30, Y(math.sqrt(21)) - 22, X(0.97), Y(math.sqrt(21)) - 2, BLUE, 0.8))
    b.append(text(410, 336, "P = 100 m², a measurement every second with R = 25 m² (σ 5 m), the state drifts by "
                            "w = 1 m² per second", 11, GREY))
    save("sawtooth.svg", w, h, "".join(b))


# ----------------------------------------------------------------------------------------- 3 one update in 2-D
def ellipse_pts(c, P, k=1.0, n=90):
    lam, V = np.linalg.eigh(np.asarray(P, dtype=float))
    a = np.linspace(0, 2 * math.pi, n)
    u = np.stack([np.cos(a), np.sin(a)])
    pts = (V @ np.diag(np.sqrt(np.maximum(lam, 0.0)) * k) @ u).T + np.asarray(c)
    return pts[:, 0], pts[:, 1]


def update2d():
    """§2–§3 worked example: x⁻ = [103, 1.5], P⁻ = [[9, 3], [3, 2]]; a height z = 106 m with R = 9."""
    w, h = 820, 375
    xp, Pp = np.array([103.0, 1.5]), np.array([[9.0, 3.0], [3.0, 2.0]])
    xu, Pu, _ = kf_update(xp, Pp, [106.0], [[1.0, 0.0]], [[9.0]])
    b = [text(410, 24, "Measuring the height alone also moves the climb rate (the tilted ellipse)", 13, INK,
              weight="bold")]
    X, Y = axes(b, 90, 50, 640, 250, (96, 112), (-1.5, 5), range(96, 113, 2), (-1, 0, 1, 2, 3, 4, 5),
                "height (m)", "climb rate (m/s)")
    b.append(rect(X(106 - 3), 50, X(106 + 3) - X(106 - 3), 250, ORANGE, opacity=0.12))
    b.append(line(X(106), 50, X(106), 300, ORANGE, 1.4, "5 4"))
    b.append(text(X(106) + 4, 64, "measured: 106 ± 3 m (any climb rate)", 11, ORANGE, "start"))
    ex, ey = ellipse_pts(xp, Pp)
    b.append(poly([X(v) for v in ex], [Y(v) for v in ey], BLUE, 1.8, "6 4"))
    b.append(circle(X(xp[0]), Y(xp[1]), 4, BLUE, BLUE))
    b.append(text(X(99.5), Y(-0.6), "predicted [103, 1.5], 1σ", 11, BLUE, "middle"))
    ex, ey = ellipse_pts(xu, Pu)
    b.append(poly([X(v) for v in ex], [Y(v) for v in ey], GREEN, 2.2))
    b.append(circle(X(xu[0]), Y(xu[1]), 4, GREEN, GREEN))
    b.append(text(X(107.6), Y(3.6), f"updated [{xu[0]:.1f}, {xu[1]:.1f}], 1σ", 11, GREEN, "start", "bold"))
    b.append(arrow(X(xp[0]), Y(xp[1]), X(xu[0]) - 3, Y(xu[1]) + 2, INK, "i", 1.4))
    b.append(text(410, 364, "The ellipse is tilted because P⁻ has a covariance (3): a higher height goes with a faster "
                            "climb. Moving the height up moves the climb up too.", 11, GREY))
    save("update2d.svg", w, h, "".join(b))


# ----------------------------------------------------------------------------------------- 4 the q trade-off
def q_tradeoff():
    """Synthetic heights, NOT the lab's data (seed 4040): a climb from 50 m to 90 m between 10 and 30 s, baro-like
    measurements σ 2 m every 0.8 s. Height1D with climb_accel 0.03, 0.4 and 8 m/s²."""
    rng = np.random.default_rng(4040)

    def truth(t):
        if t < 10:
            return 50.0
        if t < 30:
            return 50.0 + 40.0 * (1 - math.cos(math.pi * (t - 10) / 20)) / 2
        return 90.0
    ts = np.arange(0.4, 50.0, 0.8)
    zs = np.array([truth(t) + 2.0 * rng.standard_normal() for t in ts])
    w, h = 900, 345
    b = [text(450, 24, "The same heights, three values of q: too small lags, too large is noisy", 13, INK,
              weight="bold")]
    X, Y = axes(b, 80, 45, 760, 230, (0, 50), (42, 98), range(0, 51, 10), (50, 60, 70, 80, 90), "time (s)",
                "height (m)")
    b.append(poly([X(t) for t in np.linspace(0, 50, 200)], [Y(truth(t)) for t in np.linspace(0, 50, 200)], INK, 1.2))
    for t, z in zip(ts, zs):
        b.append(circle(X(t), Y(z), 2.0, GREY, GREY, 0.5))
    for ca, c, lab in ((0.03, RED, "σ_a 0.03 m/s²: smooth, but late in the climb"),
                       (0.4, GREEN, "σ_a 0.4 m/s²: follows the climb"),
                       (8.0, ORANGE, "σ_a 8 m/s²: follows every measurement")):
        f = Height1D(ca)
        hs = [f.update(t, z, 2.0)[0] for t, z in zip(ts, zs)]
        b.append(poly([X(t) for t in ts], [Y(v) for v in hs], c, 1.8))
    for i, (c, lab) in enumerate(((RED, "σ_a = 0.03 m/s²: smooth, but late in the climb"),
                                  (GREEN, "σ_a = 0.4 m/s²: follows the climb, smooths the noise"),
                                  (ORANGE, "σ_a = 8 m/s²: follows every measurement"))):
        y = 205 + i * 18
        b.append(line(470, y - 4, 495, y - 4, c, 2.5))
        b.append(text(502, y, lab, 11, c, "start"))
    b.append(text(110, 75, "grey dots: measurements (σ 2 m); black: truth", 11, GREY, "start"))
    b.append(text(450, 336, "Synthetic illustration (not the lab's data).", 11, GREY))
    save("q_tradeoff.svg", w, h, "".join(b))


# ----------------------------------------------------------------------------------------- 5 the gate and lock-out
def gate():
    """§5 worked example: a fix 40 m east of the prediction, R = 25 I. Honest P = 1600 I (σ 40 m): d² = 0.98.
    Overconfident P = 100 I (σ 10 m): d² = 12.8 > 9.21."""
    w, h = 860, 340
    b = [text(430, 24, "The same fix, two filters: the 99 % gate is as wide as the filter's own σ", 13, INK,
              weight="bold")]
    for cx, sig, c, title in ((215, 40.0, GREEN, "honest: σ 40 m per axis"), (645, 10.0, RED,
                                                                              "overconfident: σ 10 m per axis")):
        s = math.sqrt(sig * sig + 25.0)
        d2 = 40.0 ** 2 / (sig * sig + 25.0)
        r99 = math.sqrt(9.2103) * s
        sc, cy = 0.9, 170
        b.append(text(cx, 46, title, 12, c, weight="bold"))
        b.append(f'<circle cx="{cx}" cy="{cy}" r="{r99 * sc:.1f}" fill="{c}" fill-opacity="0.08" stroke="{c}" '
                 f'stroke-width="1.6"/>')
        b.append(circle(cx, cy, 4, BLUE, BLUE))
        b.append(text(cx, cy + 20, "prediction", 11, BLUE))
        b.append(circle(cx + 40 * sc, cy, 5, ORANGE, ORANGE))
        b.append(line(cx, cy, cx + 40 * sc, cy, ORANGE, 1.2, "3 3"))
        b.append(text(cx + 40 * sc + 8, cy - 8, "fix, 40 m east", 11, ORANGE, "start"))
        ok = d2 <= 9.2103
        b.append(text(cx, 300, f"d² = 40² / ({sig:.0f}² + 5²) = {d2:.2f}  →  " + ("accepted" if ok else "REFUSED"),
                      12, GREEN if ok else RED, weight="bold"))
        b.append(text(cx, 318, f"gate radius √9.21 · √(σ² + 5²) = {r99:.0f} m", 11, GREY))
    save("gate.svg", w, h, "".join(b))


if __name__ == "__main__":
    cold_open()
    sawtooth()
    update2d()
    q_tradeoff()
    gate()
