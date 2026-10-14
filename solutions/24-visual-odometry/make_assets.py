#!/usr/bin/env python3
"""Mission 24 lesson pictures (teacher only). Writes courses/24-visual-odometry/assets/.

    python3 solutions/24-visual-odometry/make_assets.py      (after make_dataset.py: the strip uses its frames)

flight_strip.jpg: four frames of the lab flight (map data © OpenStreetMap contributors).
shift_theorem.svg, drift.svg, sawtooth.svg: matplotlib (numbers are the lesson's worked examples, not the lab's).
slide.svg, axes.svg, turn.svg, two_failures.svg: hand-drawn SVG text below.
"""
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "courses", "24-visual-odometry", "assets")
DATA = os.path.join(REPO, "datasets", "24-visual-odometry")

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"font.size": 10, "svg.fonttype": "none", "figure.facecolor": "white"})
BLUE, RED, INK, AMBER = "#0b6e8a", "#d64545", "#1d2733", "#f2a33a"


def strip():
    tiles = []
    for i, label in ((12, "frame 12: city"), (40, "frame 40: city"), (60, "frame 60: open sea"),
                     (84, "frame 84: overlay")):
        im = cv2.imread(os.path.join(DATA, "flight", f"frame_{i:03d}.jpg"))
        cv2.rectangle(im, (0, 0), (170, 24), (0, 0, 0), -1)
        cv2.putText(im, label, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(im)
        tiles.append(np.full((240, 6, 3), 255, np.uint8))
    s = np.hstack(tiles[:-1])
    cv2.putText(s, "Map data (c) OpenStreetMap contributors", (s.shape[1] - 300, 232), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(OUT, "flight_strip.jpg"), s, [cv2.IMWRITE_JPEG_QUALITY, 85])


def shift_theorem():
    a = np.array([0, 0, 1, 3, 1, 0, 0, 0], float)
    b = np.roll(a, 2)
    R = np.fft.fft(b) * np.conj(np.fft.fft(a))
    R /= np.abs(R)
    r = np.real(np.fft.ifft(R))
    fig, ax = plt.subplots(1, 3, figsize=(10, 2.6))
    x = np.arange(8)
    ax[0].stem(x, a, linefmt=INK, markerfmt="o", basefmt=" ")
    ax[0].set_title("a")
    ax[1].stem(x, b, linefmt=BLUE, markerfmt="o", basefmt=" ")
    ax[1].set_title("b = a moved 2 samples right")
    ax[2].stem(x, r, linefmt=RED, markerfmt="o", basefmt=" ")
    ax[2].set_title("ifft of B·A* / |B·A*|: one spike, at 2")
    for k in ax:
        k.set_xticks(x)
        k.set_ylim(-0.3, 3.3 if k is not ax[2] else 1.15)
        k.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "shift_theorem.svg"))
    plt.close(fig)


def drift():
    n = np.arange(1, 401)
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.loglog(n, 0.4 * np.sqrt(n), color=BLUE, label="random only (σ = 0.4 m): slope ½")
    ax.loglog(n, 0.05 * n, color=RED, label="bias only (b = 0.05 m): slope 1")
    ax.set_xlabel("steps n")
    ax.set_ylabel("RMS error, one axis (m)")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "drift.svg"))
    plt.close(fig)


def sawtooth():
    rng = np.random.default_rng(5)
    t = np.arange(0, 121)
    err, sig, e, s = [], [], 0.0, 3.0
    fixes = set(range(20, 121, 20)) - {80}
    for k in t:
        if k:
            e += 0.9 + rng.normal(0, 0.3)
            s += 0.6
        if k in fixes:
            K = s * s / (s * s + 16)
            e = (1 - K) * e + rng.normal(0, 1.5)
            s = np.sqrt((1 - K) * s * s)
        err.append(abs(e))
        sig.append(s)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(t, err, color=BLUE, label="true error")
    ax.plot(t, 2 * np.array(sig), "--", color=BLUE, lw=1, label="2σ stated")
    for f in fixes:
        ax.axvline(f, color=AMBER, ls=":", lw=1)
    ax.annotate("no fix here:\na longer tooth", (100, 33), xytext=(62, 40), fontsize=9,
                arrowprops={"arrowstyle": "->", "color": INK})
    ax.set_xlabel("frame (dotted: a map fix)")
    ax.set_ylabel("metres")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sawtooth.svg"))
    plt.close(fig)


SLIDE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 270" font-family="sans-serif" font-size="13">
<rect width="700" height="270" fill="#ffffff"/>
<defs><marker id="a" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="6" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="#d64545"/></marker>
<marker id="b" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="6" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="#0b6e8a"/></marker></defs>
<text x="20" y="24" fill="#1d2733" font-weight="bold">Two frames, one second apart. Heading-up: the drone flies towards the top.</text>
<g transform="translate(30,45)">
 <rect x="0" y="0" width="200" height="150" fill="#f3efe6" stroke="#1d2733"/>
 <rect x="40" y="30" width="40" height="28" fill="#c9b79c"/><rect x="120" y="70" width="50" height="34" fill="#a7c4cf"/>
 <circle cx="70" cy="110" r="12" fill="#7a9a63"/>
 <text x="70" y="172" fill="#1d2733">frame i−1</text>
</g>
<g transform="translate(270,45)">
 <rect x="0" y="0" width="200" height="150" fill="#f3efe6" stroke="#1d2733"/>
 <rect x="40" y="70" width="40" height="28" fill="#c9b79c"/><rect x="120" y="110" width="50" height="34" fill="#a7c4cf"/>
 <path d="M58,150 A12,12 0 0,1 82,150 Z" fill="#7a9a63"/>
 <rect x="10" y="4" width="34" height="22" fill="#d9cdb6"/>
 <line x1="100" y1="36" x2="100" y2="72" stroke="#d64545" stroke-width="3" marker-end="url(#a)"/>
 <text x="80" y="172" fill="#1d2733">frame i</text>
</g>
<text x="490" y="95" fill="#d64545">dy &gt; 0: the ground</text>
<text x="490" y="113" fill="#d64545">slid DOWN in the picture</text>
<line x1="520" y1="190" x2="520" y2="140" stroke="#0b6e8a" stroke-width="3" marker-end="url(#b)"/>
<text x="535" y="160" fill="#0b6e8a">so the drone flew</text>
<text x="535" y="178" fill="#0b6e8a">FORWARD (up)</text>
<text x="20" y="232" fill="#1d2733">The ground moves in the picture the opposite way to the camera; new ground enters at the top.</text>
<text x="20" y="252" fill="#1d2733">Most of frame i−1 is still in frame i: that overlap is what phase correlation measures.</text>
</svg>
"""

AXES = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 300" font-family="sans-serif" font-size="13">
<rect width="700" height="300" fill="#ffffff"/>
<defs><marker id="k" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#1d2733"/></marker>
<marker id="b" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="6" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="#0b6e8a"/></marker></defs>
<text x="20" y="24" font-weight="bold" fill="#1d2733">1. In the picture</text>
<rect x="30" y="50" width="240" height="170" fill="#f3efe6" stroke="#1d2733"/>
<line x1="30" y1="50" x2="100" y2="50" stroke="#1d2733" stroke-width="2" marker-end="url(#k)"/><text x="108" y="45" fill="#1d2733">x (dx &gt; 0: right)</text>
<line x1="30" y1="50" x2="30" y2="120" stroke="#1d2733" stroke-width="2" marker-end="url(#k)"/><text x="36" y="136" fill="#1d2733">y (dy &gt; 0: down)</text>
<line x1="150" y1="180" x2="150" y2="110" stroke="#0b6e8a" stroke-width="3" marker-end="url(#b)"/><text x="160" y="112" fill="#0b6e8a">forward = +dy · g</text>
<line x1="150" y1="180" x2="215" y2="180" stroke="#0b6e8a" stroke-width="3" marker-end="url(#b)"/><text x="160" y="205" fill="#0b6e8a">right = −dx · g</text>
<text x="30" y="245" fill="#1d2733">g = metres per pixel (mission 18)</text>
<text x="370" y="24" font-weight="bold" fill="#1d2733">2. On the ground</text>
<text x="370" y="42" fill="#1d2733">heading θ: clockwise from north</text>
<line x1="470" y1="200" x2="470" y2="60" stroke="#1d2733" stroke-width="1.5" marker-end="url(#k)"/><text x="476" y="66" fill="#1d2733">north</text>
<line x1="470" y1="200" x2="640" y2="200" stroke="#1d2733" stroke-width="1.5" marker-end="url(#k)"/><text x="612" y="218" fill="#1d2733">east</text>
<line x1="470" y1="200" x2="530" y2="95" stroke="#0b6e8a" stroke-width="3" marker-end="url(#b)"/><text x="536" y="98" fill="#0b6e8a">forward</text>
<line x1="470" y1="200" x2="555" y2="249" stroke="#0b6e8a" stroke-width="3" marker-end="url(#b)"/><text x="562" y="252" fill="#0b6e8a">right</text>
<path d="M470,150 A50,50 0 0,1 495,157" fill="none" stroke="#d64545" stroke-width="2"/><text x="484" y="143" fill="#d64545">θ</text>
<text x="300" y="276" fill="#1d2733">east = forward·sin θ + right·cos θ</text>
<text x="300" y="294" fill="#1d2733">north = forward·cos θ − right·sin θ</text>
</svg>
"""

TURN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 250" font-family="sans-serif" font-size="13">
<rect width="660" height="250" fill="#ffffff"/>
<defs><marker id="r" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#d64545"/></marker>
<marker id="b" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 Z" fill="#0b6e8a"/></marker></defs>
<text x="20" y="22" font-weight="bold" fill="#1d2733">A shift: every point moves the same way</text>
<rect x="30" y="40" width="240" height="160" fill="#f3efe6" stroke="#1d2733"/>
<g stroke="#0b6e8a" stroke-width="2.5">
<line x1="70" y1="70" x2="70" y2="100" marker-end="url(#b)"/><line x1="230" y1="70" x2="230" y2="100" marker-end="url(#b)"/>
<line x1="150" y1="110" x2="150" y2="140" marker-end="url(#b)"/><line x1="70" y1="150" x2="70" y2="180" marker-end="url(#b)"/>
<line x1="230" y1="150" x2="230" y2="180" marker-end="url(#b)"/></g>
<text x="30" y="222" fill="#0b6e8a">five equal votes: phase correlation</text>
<text x="30" y="240" fill="#0b6e8a">and the median of the votes agree</text>
<text x="340" y="22" font-weight="bold" fill="#1d2733">A shift + a 12° turn: the votes differ</text>
<rect x="350" y="40" width="240" height="160" fill="#f3efe6" stroke="#1d2733"/>
<g stroke="#d64545" stroke-width="2.5">
<line x1="390" y1="70" x2="379" y2="104" marker-end="url(#r)"/><line x1="550" y1="70" x2="562" y2="94" marker-end="url(#r)"/>
<line x1="470" y1="110" x2="470" y2="140" marker-end="url(#r)"/><line x1="390" y1="150" x2="373" y2="172" marker-end="url(#r)"/>
<line x1="550" y1="150" x2="557" y2="187" marker-end="url(#r)"/></g>
<text x="350" y="222" fill="#d64545">no single shift fits: first turn the older</text>
<text x="350" y="240" fill="#d64545">frame by the IMU heading change (derotate)</text>
</svg>
"""

FAILURES = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 210" font-family="sans-serif" font-size="13">
<rect width="660" height="210" fill="#ffffff"/>
<text x="20" y="22" font-weight="bold" fill="#1d2733">Two ways an odometer fails</text>
<rect x="20" y="40" width="290" height="150" rx="8" fill="#eef5f8" stroke="#0b6e8a"/>
<text x="34" y="64" font-weight="bold" fill="#0b6e8a">Nothing to measure</text>
<text x="34" y="88" fill="#1d2733">open sea, fog, uniform sand, darkness</text>
<text x="34" y="110" fill="#1d2733">→ no common motion → a LOW peak</text>
<text x="34" y="140" font-weight="bold" fill="#1d2733">Defence: a response threshold</text>
<text x="34" y="162" fill="#1d2733">refuse the step, carry on with the last</text>
<text x="34" y="180" fill="#1d2733">velocity turned by the IMU</text>
<rect x="330" y="40" width="310" height="150" rx="8" fill="#fbeeee" stroke="#d64545"/>
<text x="344" y="64" font-weight="bold" fill="#d64545">The wrong thing measured, confidently</text>
<text x="344" y="88" fill="#1d2733">a text overlay, lens dirt, the drone's legs:</text>
<text x="344" y="110" fill="#1d2733">→ fixed in the picture → a HIGH peak at 0</text>
<text x="344" y="140" font-weight="bold" fill="#1d2733">Defence: a gate on the velocity</text>
<text x="344" y="162" fill="#1d2733">refuse a step far from the expected</text>
<text x="344" y="180" fill="#1d2733">velocity (a threshold cannot see it)</text>
</svg>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    strip()
    shift_theorem()
    drift()
    sawtooth()
    for name, text in (("slide.svg", SLIDE), ("axes.svg", AXES), ("turn.svg", TURN), ("two_failures.svg", FAILURES)):
        with open(os.path.join(OUT, name), "w") as f:
            f.write(text)
    print("assets:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
