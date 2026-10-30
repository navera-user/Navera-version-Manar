#!/usr/bin/env python3
"""Teacher only — draws the figures of lesson 16 into courses/16-rotations/assets/.

    python3 solutions/16-rotations/make_figures.py

Every vector drawn in order.svg, gimbal.svg and qtrap.svg is computed with the course reference
(solutions/_navera_lite/navera_lite/rotations.py), so the pictures follow the code.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import rotations as rot  # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "16-rotations", "assets")
INK, BLUE, RED, ORANGE, GREY, BG = "#1d2733", "#0b6e8a", "#d64545", "#a8680d", "#8a96a3", "#f7fafc"
GREEN = "#2e9e4f"
TAIL = "#7a8794"
HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {{w}} {{h}}" font-family="sans-serif" font-size="13">'
        f'<rect width="{{w}}" height="{{h}}" fill="{BG}"/><defs>'
        + "".join(f'<marker id="m{n}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                  f'orient="auto"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
                  for n, c in (("i", INK), ("r", RED), ("b", BLUE), ("o", ORANGE), ("g", GREY))) + "</defs>")
PLANE = {"fuselage": [(-40, 0, 0), (40, 0, 0)], "nose": [(40, 0, 0), (52, 0, 0)],
         "left wing": [(5, 0, 0), (5, 48, 0)], "right wing": [(5, 0, 0), (5, -48, 0)], "tail": [(-40, 17, 0), (-40, -17, 0)], "fin": [(-40, 0, 0), (-40, 0, 16)]}
PCOL = {"fuselage": INK, "nose": RED, "left wing": GREEN, "right wing": BLUE, "tail": TAIL, "fin": ORANGE}


def text(x, y, s, size=13, color=INK, anchor="middle", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}">{s}</text>')


def arrow(x1, y1, x2, y2, color=INK, m="i", width=2.0, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"'
            f'{d} marker-end="url(#m{m})"/>')


def plane_view(M, cx, cy, view, scale=1.0):
    """Lines of the small aircraft rotated by M (body → world), seen from above ('top': east right, north
    up) or from the south ('south': east right, up up)."""
    i, j = (0, 1) if view == "top" else (0, 2)
    out = []
    for part, pts in PLANE.items():
        w = [M @ np.array(p, dtype=float) * scale for p in pts]
        x1, y1, x2, y2 = cx + w[0][i], cy - w[0][j], cx + w[1][i], cy - w[1][j]
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{PCOL[part]}" '
                   f'stroke-width="{6 if part == "nose" else 4}" stroke-linecap="round"/>')
    return "".join(out)


def save(name, w, h, body):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(HEAD.format(w=w, h=h) + body + "</svg>\n")
    print("wrote", name)


# ---------------------------------------------------------------------------------------- cold open
def cold_open():
    b = []
    cx, cy = 210, 225
    b.append(text(395, 24, "Three gimbals hold the platform still while the spacecraft turns around it", 14,
                  weight="bold"))
    b.append(f'<ellipse cx="{cx}" cy="{cy}" rx="150" ry="150" fill="none" stroke="{GREY}" stroke-width="10"/>')
    b.append(f'<ellipse cx="{cx}" cy="{cy}" rx="112" ry="112" fill="none" stroke="{BLUE}" stroke-width="10"/>')
    b.append(f'<ellipse cx="{cx}" cy="{cy}" rx="30" ry="112" fill="none" stroke="{ORANGE}" stroke-width="10"/>')
    b.append(f'<rect x="{cx - 22}" y="{cy - 22}" width="44" height="44" fill="{INK}" rx="4"/>')
    b.append(arrow(cx, cy + 172, cx, cy - 172, RED, "r", 2.5, "6 4"))
    b.append(arrow(cx - 175, cy, cx + 175, cy, GREY, "g", 2, "6 4"))
    b.append(text(cx + 10, cy - 160, "outer axis", 12, RED, "start"))
    b.append(text(cx + 10, cy + 172, "= inner axis: two axes in one line", 12, RED, "start"))
    b.append(text(cx + 180, cy + 4, "middle axis", 12, GREY, "start"))
    b.append(text(cx + 28, cy + 40, "platform", 11, INK, "start"))
    b.append(text(cx - 105, cy - 150, "outer gimbal", 12, GREY, "end"))
    b.append(text(cx - 118, cy - 92, "middle", 12, BLUE, "end"))
    b.append(text(cx + 40, cy - 70, "inner", 12, ORANGE, "start"))
    x0 = 465
    b.append(f'<rect x="{x0}" y="90" width="315" height="236" rx="8" fill="#ffffff" stroke="{GREY}"/>')
    lines = [("Apollo 11, 20 July 1969, about two hours", 0), ("after the Moon landing", 0), ("", 0),
             ("104:59:35  Houston: “We noticed you are", 1), ("maneuvering very close to gimbal lock.", 1),
             ("I suggest you move back away.”", 1), ("", 0),
             ("105:00:30  Collins: “How about sending me", 2), ("a fourth gimbal for Christmas.”", 2)]
    y = 118
    for s, kind in lines:
        b.append(text(x0 + 16, y, s, 13, (INK, BLUE, RED)[kind], "start", "bold" if kind == 2 else "normal"))
        y += 21
    b.append(text(x0 + 16, y + 6, "NASA Apollo Lunar Surface Journal (E. Jones, P. Fjeld)", 10, GREY, "start"))
    b.append(text(395, 428, "When the middle gimbal turns 90°, the inner and outer axes line up: one way of turning "
                            "is lost (gimbal lock).", 12, INK))
    save("cold_open.svg", 790, 445, "".join(b))


# ---------------------------------------------------------------------------------------- frames and signs
def frames():
    b = []
    # ENU world
    ox, oy = 95, 190
    b.append(text(95, 32, "World: ENU", 15, BLUE, weight="bold"))
    b.append(arrow(ox, oy, ox + 85, oy, INK))
    b.append(arrow(ox, oy, ox + 52, oy - 52, INK))
    b.append(arrow(ox, oy, ox, oy - 100, INK))
    b.append(text(ox + 92, oy + 5, "x = East", 12, INK, "start"))
    b.append(text(ox + 56, oy - 58, "y = North", 12, INK, "start"))
    b.append(text(ox, oy - 108, "z = Up", 12, INK))
    b.append(text(95, 230, "heading: from North,", 12, INK))
    b.append(text(95, 247, "clockwise (East = 90°)", 12, INK))
    b.append(text(95, 270, "ENU yaw: from East,", 12, INK))
    b.append(text(95, 287, "counter-clockwise", 12, INK))
    b.append(text(95, 310, "heading = 90° − yaw", 12, RED, weight="bold"))

    def panel(cx, title, sub, M, view_xy, arc, note1, note2):
        b.append(text(cx, 32, title, 15, BLUE, weight="bold"))
        b.append(text(cx, 50, sub, 11, GREY))
        cy = 165
        b.append(f'<line x1="{cx - 80}" y1="{cy}" x2="{cx + 80}" y2="{cy}" stroke="{GREY}" stroke-dasharray="4 4"/>')
        for part, pts in PLANE.items():
            w = [M @ np.array(p, dtype=float) for p in pts]
            (a1, b1), (a2, b2) = view_xy(w[0]), view_xy(w[1])
            b.append(f'<line x1="{cx + a1:.1f}" y1="{cy - b1:.1f}" x2="{cx + a2:.1f}" y2="{cy - b2:.1f}" '
                     f'stroke="{PCOL[part]}" stroke-width="{6 if part == "nose" else 4}" stroke-linecap="round"/>')
        b.append(arc(cx, cy))
        b.append(text(cx, 262, note1, 12, INK))
        b.append(text(cx, 282, note2, 12, RED, weight="bold"))

    a = math.radians(20)
    # roll, seen from behind: viewer's right = body right (−y); up = z. axis +x points AWAY from the viewer.
    panel(300, "+ roll", "seen from behind (x points away from you)", rot.rot_x(a),
          lambda v: (-v[1], v[2]),
          lambda cx, cy: (f'<path d="M{cx - 55} {cy - 75} A80 80 0 0 1 {cx + 55} {cy - 75}" fill="none" stroke="{RED}" '
                          f'stroke-width="2.5" marker-end="url(#mr)"/>'),
          "looks clockwise from behind:", "the RIGHT wing goes down")
    # pitch, seen from the left side: viewer looks along −y; viewer's right = −x (nose on the left); up = z.
    panel(510, "+ ROS pitch", "seen from the left side (y points at you)", rot.rot_y(a),
          lambda v: (-v[0], v[2]),
          lambda cx, cy: (f'<path d="M{cx - 85} {cy + 35} A90 90 0 0 0 {cx - 85} {cy - 35}" fill="none" stroke="{RED}" '
                          f'stroke-width="2.5" marker-start="url(#mr)"/>'),
          "counter-clockwise seen from the left:", "the nose goes DOWN")
    # yaw, seen from above: east right, north up; z points at the viewer.
    panel(720, "+ yaw", "seen from above (z points at you)", rot.rot_z(a),
          lambda v: (v[0], v[1]),
          lambda cx, cy: (f'<path d="M{cx + 75} {cy + 30} A80 80 0 0 0 {cx + 75} {cy - 30}" fill="none" stroke="{RED}" '
                          f'stroke-width="2.5" marker-end="url(#mr)"/>'),
          "counter-clockwise from above:", "the nose turns LEFT")
    b.append(text(470, 318, "Body FLU: x = nose (red), y = left wing (green), z = up (fin, orange; grey = tailplane). Pilot's pitch_up = −(ROS pitch).", 12, INK))
    save("frames.svg", 830, 335, "".join(b))


# ---------------------------------------------------------------------------------------- order matters
def order():
    b = [text(400, 26, "Same two turns, two orders: R = Rx(90°) · Ry(90°)  versus  R = Ry(90°) · Rx(90°)", 14,
              weight="bold")]
    cases = [("Rx(90°) · Ry(90°)", rot.rot_x(math.radians(90)) @ rot.rot_y(math.radians(90)), 210),
             ("Ry(90°) · Rx(90°)", rot.rot_y(math.radians(90)) @ rot.rot_x(math.radians(90)), 590)]
    for title, M, cx in cases:
        b.append(text(cx, 56, title, 14, BLUE, weight="bold"))
        b.append(text(cx - 90, 78, "from above", 11, GREY))
        b.append(text(cx + 90, 78, "from the south", 11, GREY))
        b.append(plane_view(M, cx - 90, 160, "top"))
        b.append(plane_view(M, cx + 90, 160, "south"))
        nose, top = M[:, 0], M[:, 2]
        names = {0: ("east", "west"), 1: ("north", "south"), 2: ("up", "down")}
        nz = lambda v: names[int(np.argmax(np.abs(v)))][0 if v[int(np.argmax(np.abs(v)))] > 0 else 1]  # noqa: E731
        b.append(text(cx, 250, f"nose → {nz(nose)},  tail fin → {nz(top)}", 13, INK))
    b.append(text(400, 285, "red = nose, green = left wing, blue = right wing, grey = tailplane, orange = tail fin (on top).",
                  12, GREY))
    save("order.svg", 800, 300, "".join(b))


# ---------------------------------------------------------------------------------------- gimbal lock
def gimbal():
    b = [text(390, 26, "Gimbal lock: at ROS pitch +90° the nose points straight down", 14, weight="bold")]
    for k, (roll, yaw) in enumerate([(0, 30), (20, 50), (-15, 15)]):
        M = rot.euler_zyx_to_matrix(math.radians(roll), math.radians(90), math.radians(yaw))
        cx = 140 + k * 250
        b.append(text(cx, 56, f"roll {roll}°, yaw {yaw}°", 13, BLUE, weight="bold"))
        b.append(plane_view(M, cx, 150, "top", 0.9))
        b.append(text(cx, 236, "seen from above", 11, GREY))
    b.append(text(390, 270, "Three (roll, yaw) pairs, one attitude: only yaw − roll = 30° matters. The roll axis (the nose)",
                  12, INK))
    b.append(text(390, 288, "now lies along the yaw axis (vertical), so turning about one is turning about the other.",
                  12, INK))
    save("gimbal.svg", 780, 305, "".join(b))


# ---------------------------------------------------------------------------------------- the order trap
def qtrap():
    q = np.array([0.0, 0.0, 0.0, 1.0])
    good = rot.q_to_matrix(q)
    w, x, y, z = q
    bad = rot.q_to_matrix((x, y, z, w))
    b = [text(390, 26, "The same four numbers (0, 0, 0, 1), read two ways", 14, weight="bold")]
    for title, M, cx, note in (("as (x, y, z, w) — ROS", good, 200, "no rotation: level, nose east (heading 90°)"),
                               ("as (w, x, y, z) — the trap", bad, 580, "180° about z: level, nose WEST (heading 270°)")):
        b.append(text(cx, 56, title, 14, BLUE if cx < 300 else RED, weight="bold"))
        b.append(plane_view(M, cx, 140, "top"))
        b.append(text(cx, 222, note, 12, INK))
    b.append(text(390, 252, "No error, no warning: the length is still 1. Only the attitude is wrong.", 12, RED))
    save("qtrap.svg", 780, 270, "".join(b))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    cold_open()
    frames()
    order()
    gimbal()
    qtrap()
