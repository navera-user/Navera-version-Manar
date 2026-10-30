#!/usr/bin/env python3
"""Mission 31 figures (teacher only): writes courses/31-simulator/assets/{loop,mavlink_frame,campaign}.svg.

    python3 solutions/31-simulator/make_figures.py      # campaign.svg flies the reference jam and plane_late runs

loop.svg and mavlink_frame.svg are drawn from constants (the frame's bytes are the first GPS_INPUT frame of
datasets/31-simulator/gps_input.bin, decoded by the reference); campaign.svg plots two reference runs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
ASSETS = os.path.join(REPO, "courses", "31-simulator", "assets")
DATA = os.path.join(REPO, "datasets", "31-simulator")
INK, BLUE, ORANGE, RED, GREEN, GREY, BG = "#1d2733", "#0b6e8a", "#c98a06", "#d64545", "#2e9e4f", "#7a8794", "#f7fafc"


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def box(x, y, w, h, title, lines, colour, fill="#ffffff"):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{colour}" stroke-width="2"/>',
           f'<text x="{x + w / 2}" y="{y + 20}" text-anchor="middle" font-weight="bold" fill="{colour}">{esc(title)}</text>']
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + w / 2}" y="{y + 38 + 16 * i}" text-anchor="middle" font-size="12" fill="{INK}">'
                   f'{esc(ln)}</text>')
    return out


def arrow(x1, y1, x2, y2, label="", colour=INK, dy=-6, anchor="middle"):
    m = {INK: "mi", BLUE: "mb", ORANGE: "ma", RED: "mr", GREEN: "mg"}[colour]
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" stroke-width="2" marker-end="url(#{m})"/>']
    if label:
        out.append(f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 + dy}" text-anchor="{anchor}" font-size="12" '
                   f'fill="{colour}">{esc(label)}</text>')
    return out


def svg(w, h, body):
    defs = "".join(f'<marker id="{i}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                   f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{c}"/></marker>'
                   for i, c in (("mi", INK), ("mb", BLUE), ("ma", ORANGE), ("mr", RED), ("mg", GREEN)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="13">'
            f'<rect width="{w}" height="{h}" fill="{BG}"/><defs>{defs}</defs>' + "".join(body) + "</svg>")


def loop():
    b = []
    b.append(f'<text x="20" y="26" font-weight="bold" font-size="15" fill="{INK}">The closed loop of mission 31: what '
             'is real, what is simulated</text>')
    b.append(f'<rect x="14" y="40" width="262" height="330" rx="10" fill="#fdf3e3" stroke="{ORANGE}" '
             'stroke-dasharray="5 4"/>')
    b.append(f'<text x="145" y="60" text-anchor="middle" font-weight="bold" fill="{ORANGE}">SIMULATED (sim/world.py)</text>')
    b += box(30, 72, 230, 62, "GPS receiver", ["Gauss–Markov noise, 5 Hz", "jammed · off · jump · drift"], ORANGE)
    b += box(30, 144, 230, 62, "cameras", ["error profile (target / measured)", "or YOUR networks on pictures"], ORANGE)
    b += box(30, 216, 230, 46, "IMU", ["ok · tilt bias · off"], ORANGE)
    b += box(30, 274, 230, 80, "truth (kinematics)", ["x[k+1] = f(x[k], u[k], Δt)", "turn rate and acceleration",
                                                       "limits, no wind, Δt = 0.1 s"], ORANGE)
    b.append(f'<rect x="300" y="40" width="250" height="330" rx="10" fill="#e8f3f6" stroke="{BLUE}" '
             'stroke-dasharray="5 4"/>')
    b.append(f'<text x="425" y="60" text-anchor="middle" font-weight="bold" fill="{BLUE}">REAL: NAVERA Lite</text>')
    b += box(316, 72, 218, 62, "judge (mission 29)", ["+ guard (mission 30)", "Estimates → Decision"], BLUE)
    b += box(316, 160, 218, 62, "messenger (output.py)", ["each NEW position once", "GPS_INPUT bytes, MAVLink 2"], BLUE)
    b += box(316, 248, 218, 106, "your choice: --mine", ["your arbiter (29), guard (30)", "your Kalman filter (28)",
                                                          "your weights (21, 25)", "your decoder (31) always"], BLUE)
    b.append(f'<rect x="574" y="40" width="226" height="330" rx="10" fill="#eaf6ee" stroke="{GREEN}" '
             'stroke-dasharray="5 4"/>')
    b.append(f'<text x="687" y="60" text-anchor="middle" font-weight="bold" fill="{GREEN}">the autopilot (simulated)</text>')
    b += box(590, 72, 194, 78, "reads the link", ["YOUR parse_frames", "YOUR decode_gps_input", "(only these bytes)"], GREEN)
    b += box(590, 166, 194, 78, "its filter", ["predict with its IMU", "update, χ² gate 99 %", "glitch reset after 5 s"], GREEN)
    b += box(590, 260, 194, 78, "guidance", ["fly to the destination", "no fix for 5 s:", "FAILSAFE (LAND / HOLD)"], GREEN)
    b += arrow(260, 103, 316, 103, "fixes", ORANGE)
    b += arrow(260, 175, 316, 118, "", ORANGE)
    b += arrow(425, 134, 425, 160, "", BLUE)
    b += arrow(534, 191, 590, 111, "bytes", BLUE, dy=-8)
    b += arrow(687, 150, 687, 166, "", GREEN)
    b += arrow(687, 244, 687, 260, "", GREEN)
    b.append(f'<path d="M687 338 L687 392 L145 392 L145 354" fill="none" stroke="{INK}" stroke-width="2" '
             'marker-end="url(#mi)"/>')
    b.append(f'<text x="416" y="386" text-anchor="middle" font-size="12" fill="{INK}">commands u[k]: the vehicle moves → '
             'the sensors see the NEW true position → …</text>')
    b.append(f'<text x="20" y="418" font-size="12" fill="{GREY}">A wrong position from NAVERA Lite changes the '
             'trajectory, which changes the next measurements: only a closed loop shows that.</text>')
    return svg(816, 430, b)


def mavlink_frame():
    sys.path.insert(0, os.path.join(HERE, "navera_lite", ".."))
    from navera_lite import output as O
    data = open(os.path.join(DATA, "gps_input.bin"), "rb").read()
    k = data.index(bytes([0xFD, 0x3F]))
    f = data[k:k + 75]
    d = O.decode_gps_input(f[10:73])
    cells = [("STX", "fd", 0), ("len", "3f", 1), ("inc", "00", 2), ("cmp", "00", 3), ("seq", f"{f[4]:02x}", 4),
             ("sys", f"{f[5]:02x}", 5), ("comp", f"{f[6]:02x}", 6), ("msgid (3 B, LE)", "e8 00 00", 7)]
    b = [f'<text x="20" y="26" font-weight="bold" font-size="15" fill="{INK}">One MAVLink 2 frame: the first GPS_INPUT '
         'of gps_input.bin</text>']
    x = 20
    for name, val, off in cells:
        w = 120 if off == 7 else 60
        b.append(f'<rect x="{x}" y="44" width="{w}" height="56" fill="#ffffff" stroke="{BLUE}" stroke-width="1.5"/>')
        b.append(f'<text x="{x + w / 2}" y="64" text-anchor="middle" font-size="12" fill="{BLUE}">{esc(name)}</text>')
        b.append(f'<text x="{x + w / 2}" y="88" text-anchor="middle" font-family="monospace" fill="{INK}">{val}</text>')
        b.append(f'<text x="{x + 3}" y="116" font-size="11" fill="{GREY}">{off}</text>')
        x += w
    b.append(f'<rect x="{x}" y="44" width="140" height="56" fill="#fff8ec" stroke="{ORANGE}" stroke-width="1.5"/>')
    b.append(f'<text x="{x + 70}" y="64" text-anchor="middle" font-size="12" fill="{ORANGE}">payload (len bytes)</text>')
    b.append(f'<text x="{x + 70}" y="88" text-anchor="middle" fill="{INK}">63 bytes</text>')
    b.append(f'<text x="{x + 3}" y="116" font-size="11" fill="{GREY}">10</text>')
    x += 140
    b.append(f'<rect x="{x}" y="44" width="84" height="56" fill="#ffffff" stroke="{RED}" stroke-width="1.5"/>')
    b.append(f'<text x="{x + 42}" y="64" text-anchor="middle" font-size="12" fill="{RED}">checksum</text>')
    b.append(f'<text x="{x + 42}" y="88" text-anchor="middle" font-family="monospace" fill="{INK}">'
             f'{f[73]:02x} {f[74]:02x}</text>')
    b.append(f'<text x="{x + 3}" y="116" font-size="11" fill="{GREY}">10 + len</text>')
    lines = [f"fd = MAVLink 2 · len 0x3f = 63 · not signed (inc bit 0 = 0) · seq {f[4]} · system {f[5]}, component {f[6]}"
             " · msgid 0x0000e8 = 232 (GPS_INPUT)",
             "checksum = crc_x25 over bytes 1 … 9 + len, then over CRC_EXTRA = 151 (known to both sides, never sent)",
             'payload = struct "<QIiifffffffffHHBBBH": 8-byte fields first, then 4, 2, 1 (65 bytes when complete)',
             "time_usec(8) · time_week_ms(4) · lat(4) · lon(4) · alt hdop vdop vn ve vd speed_acc horiz_acc vert_acc (9 × 4)",
             "· ignore_flags(2) · time_week(2) · gps_id · fix_type · satellites (1 each) · yaw(2)",
             f"here: lat {d['lat']:.7f}°, lon {d['lon']:.7f}°, fix_type {d['fix_type']}, horiz_accuracy "
             f"{d['horiz_accuracy']:.1f} m, ignore_flags {d['ignore_flags']}, yaw 0",
             "yaw = 0 → its 2 zero bytes are not sent (63, not 65): the receiver pads the payload back to 65 bytes"]
    for i, ln in enumerate(lines):
        b.append(f'<text x="20" y="{146 + 20 * i}" font-size="12.5" fill="{INK}">{esc(ln)}</text>')
    return svg(820, 296, b)


def campaign():
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = tempfile.mkdtemp(prefix="m31fig_")
    try:
        files = os.path.join(REPO, "courses", "31-simulator", "files")
        shutil.copytree(os.path.join(files, "campaign"), os.path.join(d, "campaign"))
        shutil.copy(os.path.join(files, "navera_lite.yaml"), d)
        shutil.copytree(os.path.join(HERE, "navera_lite"), os.path.join(d, "navera_lite"))
        env = dict(os.environ, NAVERA_LITE_SIM_DATA=DATA, PYTHONPATH="")
        subprocess.run([sys.executable, "-m", "navera_lite.sim.run", "campaign/jam.json", "--quiet"], cwd=d, env=env,
                       check=True, stdout=subprocess.DEVNULL)
        with open(os.path.join(d, "my_runs", "jam.csv")) as fh:
            rows = list(csv.DictReader(fh))
    finally:
        shutil.rmtree(d)
    t = [float(r["t_s"]) for r in rows]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.2, 4.2), sharex=True, gridspec_kw={"height_ratios": [1, 2]})
    lvl = {"gps": 2, "day": 1, "": 0}
    a1.step(t, [lvl.get(r["lite_source"], 0) for r in rows], where="post", color=BLUE)
    a1.set_yticks([0, 1, 2], ["none", "day", "GPS"])
    a1.set_ylabel("source")
    for ax in (a1, a2):
        ax.axvspan(30, 70, color="#f2d0d0", lw=0)
    e = [float(r["lite_err_m"]) if r["lite_err_m"] else None for r in rows]
    a2.plot(t, [x if x is not None else float("nan") for x in e], ".", ms=2.5, color=ORANGE, label="NAVERA Lite's error")
    a2.plot(t, [float(r["ap_err_m"]) for r in rows], color=INK, lw=1, label="the autopilot's error")
    a2.set_ylabel("error (m)")
    a2.set_xlabel("mission time (s)")
    a2.legend(fontsize=8, loc="upper right")
    a1.set_ylim(-0.4, 2.6)
    a1.annotate("t0 = 30 s: GPS jammed", (30, 1.6), (6, 0.6), fontsize=8, arrowprops={"arrowstyle": "->"})
    a1.annotate("t1 = 70 s: GPS back", (70, 0.9), (80, 0.2), fontsize=8, arrowprops={"arrowstyle": "->"})
    a1.set_title("campaign/jam.json flown with the course's parts (red band: the GPS is jammed)", fontsize=9)
    fig.tight_layout()
    path = os.path.join(ASSETS, "campaign.svg")
    fig.savefig(path)
    plt.close(fig)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for name, fn in (("loop.svg", loop), ("mavlink_frame.svg", mavlink_frame)):
        with open(os.path.join(ASSETS, name), "w") as f:
            f.write(fn())
    campaign()
    for old in ("simulator.svg",):
        p = os.path.join(ASSETS, old)
        if os.path.exists(p):
            os.remove(p)
    print("wrote", sorted(os.listdir(ASSETS)))


if __name__ == "__main__":
    main()
