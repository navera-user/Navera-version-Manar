"""mav_lab.py — session 1's runner: the bytes on the autopilot's link, and the sensor models.

    python3 mav_lab.py hex          Step 0: the first bytes of the recording (no code needed)
    python3 mav_lab.py hex --answer Step 0's answer: where the first GPS_INPUT frame starts, its header named
    python3 mav_lab.py test         the examples of TODOs 1–7 (✔ / ✘)
    python3 mav_lab.py stream       Steps 2–3: YOUR parse_frames, decode_gps_input, lost_frames on the recording
    python3 mav_lab.py noise        Step 4: YOUR gauss_markov, stationary_sigma, autocorrelation (out/noise.png)
    python3 mav_lab.py rayleigh     Step 5: YOUR rayleigh_quantile against 200 000 simulated vision errors

The recording is /data/academy/31-simulator/gps_input.bin: what an autopilot received on its serial link during
60 s of a simulated flight of NAVERA Lite (GPS good, then jammed at 30 s: day vision takes over).
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import math
import os
import struct
import sys

import numpy as np

import runner_kit as rk

DATA = os.environ.get("NAVERA_LITE_SIM_DATA", "/data/academy/31-simulator")
BIN = os.path.join(DATA, "gps_input.bin")


def recording():
    try:
        with open(BIN, "rb") as f:
            return f.read()
    except OSError:
        sys.exit(f"{BIN} is missing (tell your teacher)")


def hexdump():
    data = recording()
    print(f"{BIN}: {len(data)} bytes. The first 80, 16 per line (offset in hexadecimal, then the bytes):\n")
    for i in range(0, 80, 16):
        print(f"  {i:04x}  " + " ".join(f"{b:02x}" for b in data[i:i + 16]))
    if "--answer" not in sys.argv:
        print("\nFind the first GPS_INPUT frame (lesson §3: which bytes start a MAVLink 2 frame, which byte is len?).")
        print("Then: python3 mav_lab.py hex --answer")
        return
    k = data.index(bytes([0xFD, 0x3F]))
    f = data[k:k + 10 + 63 + 2]
    print(f"\nThe first GPS_INPUT frame starts at offset {k} (0x{k:x}). Its 10 header bytes, then its payload:")
    print("  header : " + " ".join(f"{b:02x}" for b in f[:10]))
    for i in range(10, 10 + 63, 16):
        print(f"  payload: " + " ".join(f"{b:02x}" for b in f[i:min(i + 16, 73)]))
    print("  crc    : " + " ".join(f"{b:02x}" for b in f[73:75]))
    print("\nLesson §3 has the table of the header bytes and the payload's field order.")


def out_mod():
    return rk.load_student("navera_lite.output")


def sensors_mod():
    return rk.load_student("navera_lite.sim.sensors")


def short(v):
    """Payload bytes shown as their length (a bytes repr of 60 bytes helps nobody)."""
    if isinstance(v, list):
        return [short(x) for x in v]
    if isinstance(v, dict):
        return {k: (f"<{len(x)} bytes>" if isinstance(x, (bytes, bytearray)) else x) for k, x in v.items()}
    return v


def show(what, got, err, ok, want):
    got, want = short(got), short(want)
    if err:
        print(f"✘ {what}: {err}")
    else:
        print(f"{'✔' if ok else '✘'} {what} → {got!r}" + ("" if ok else f"   (expected {want})"))


def close(a, b, tol=1e-3):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def test():
    O, S = out_mod(), sensors_mod()
    p1 = struct.pack(O.GPS_INPUT_FORMAT, 0, 0, 358242433, 106360050, *[0.0] * 9, 0, 0, 0, 3, 0, 0)
    v, e = rk.call(O, "decode_gps_input", bytes(65))
    show("decode_gps_input(bytes(65))['fix_type']", None if e else (v or {}).get("fix_type"), e,
         isinstance(v, dict) and v.get("fix_type") == 0, 0)
    v, e = rk.call(O, "decode_gps_input", p1[:62])
    show("decode_gps_input(<62 bytes>)['lat']", None if e else (v or {}).get("lat") if isinstance(v, dict) else v, e,
         isinstance(v, dict) and close(v.get("lat"), 35.8242433, 1e-7), 35.8242433)
    v, e = rk.call(O, "decode_gps_input", bytes(66))
    print("✔ decode_gps_input(<66 bytes>) raises ValueError" if e and "ValueError" in e else
          f"✘ decode_gps_input(<66 bytes>) must raise ValueError (got {v!r}{', ' + e if e else ''})")
    fields = dict.fromkeys(O.GPS_INPUT_FIELDS, 0)
    fields.update(lat=358242433, lon=106360050, fix_type=3, horiz_accuracy=1.8, ignore_flags=180)
    f = O.encode_gps_input(fields, 7)
    v, e = rk.call(O, "parse_frames", b"\x00\x13" + f + f[:5])
    want = [{"seq": 7, "sysid": 1, "compid": 191, "msgid": 232, "payload": f[10:-2], "crc_ok": True}]
    show("parse_frames(noise + 1 frame + a cut frame)", v, e, v == want, want)
    bad = bytearray(f)
    bad[20] ^= 1
    v, e = rk.call(O, "parse_frames", bytes(bad) + f)
    show("parse_frames(<damaged frame> + <frame>): crc_ok of each", None if e else [d.get("crc_ok") for d in v or []],
         e, isinstance(v, list) and [d.get("crc_ok") for d in v] == [False, True], [False, True])
    odd = bytes([O.STX, 2, 0, 0, 9, 1, 1, 0xE8, 0x00, 0x01, 7, 7, 0x12, 0x34])     # msgid 0x0100E8 = 65768: unknown
    v, e = rk.call(O, "parse_frames", odd)
    show("parse_frames(<a frame with msgid 65768>): msgid, crc_ok", None if e else [(d.get("msgid"), d.get("crc_ok"))
         for d in v or []], e, isinstance(v, list) and [(d.get("msgid"), d.get("crc_ok")) for d in v] == [(65768, None)],
         [(65768, None)])
    v, e = rk.call(O, "lost_frames", [250, 251, 253, 253, 0, 1])
    show("lost_frames([250, 251, 253, 253, 0, 1])", v, e, tuple(v or ()) == (3, 1), (3, 1))
    v, e = rk.call(S, "gauss_markov", 3, 0.2, 20.0, 0.6, np.random.default_rng(0))
    want = [0.03374, -0.00205, 0.16982]
    show("gauss_markov(3, 0.2, 20.0, 0.6, np.random.default_rng(0))", None if e else np.round(np.asarray(v), 5), e,
         v is not None and np.shape(v) == (3,) and np.allclose(v, want, atol=1e-4), want)
    v, e = rk.call(S, "stationary_sigma", 0.2, 20.0, 0.6)
    show("stationary_sigma(0.2, 20.0, 0.6)", v, e, close(v, 1.9021), 1.9021)
    v, e = rk.call(S, "autocorrelation", [1.0, 2.0, 3.0, 4.0], 1)
    show("autocorrelation([1.0, 2.0, 3.0, 4.0], 1)", v, e, close(v, 0.25, 1e-9), 0.25)
    v, e = rk.call(S, "rayleigh_quantile", 15.0, 0.5)
    show("rayleigh_quantile(15.0, 0.5)", v, e, close(v, 17.661), 17.661)
    v, e = rk.call(S, "rayleigh_quantile", 15.0, 0.95)
    show("rayleigh_quantile(15.0, 0.95)", v, e, close(v, 36.716), 36.716)


def stream():
    O = out_mod()
    data = recording()
    frames = rk.need_ok(O, "parse_frames", data, kind=list)
    if not all(isinstance(d, dict) for d in frames):
        sys.exit("parse_frames() must return a list of dicts")
    by_id = {}
    for d in frames:
        by_id[d.get("msgid")] = by_id.get(d.get("msgid"), 0) + 1
    print(f"{len(data)} bytes → {len(frames)} frames (by your parse_frames):")
    print("  by message id : " + ", ".join(f"{k}: {v}" for k, v in sorted(by_id.items(), key=lambda kv: str(kv[0]))))
    print(f"  crc_ok True  : {sum(d.get('crc_ok') is True for d in frames)}")
    print(f"  crc_ok False : {sum(d.get('crc_ok') is False for d in frames)}")
    print(f"  crc_ok None  : {sum(d.get('crc_ok') is None for d in frames)}  (message id with no known CRC_EXTRA)")
    gps = [d for d in frames if d.get("msgid") == O.GPS_INPUT_ID and d.get("crc_ok") is True]
    if not gps:
        return
    dec = []
    for d in gps:
        dec.append(rk.need_ok(O, "decode_gps_input", d["payload"], kind=dict))
    print(f"\nGPS_INPUT with a good checksum: {len(gps)}; payload lengths {min(len(d['payload']) for d in gps)}–"
          f"{max(len(d['payload']) for d in gps)} bytes (65 when complete)")
    flags = {}
    for m in dec:
        key = (m["ignore_flags"], m["fix_type"], m["satellites_visible"])
        flags[key] = flags.get(key, 0) + 1
    print("  ignore_flags  fix_type  satellites  count   ignored (output.ignored(), given)")
    for (fl, ft, sat), n in sorted(flags.items()):
        names, err = rk.call(O, "ignored", int(fl))
        print(f"  {fl:12d} {ft:9d} {sat:11d} {n:6d}   {err or ', '.join(names)}")
    acc = sorted({round(m["horiz_accuracy"], 2) for m in dec})
    print(f"  horiz_accuracy values (m): {acc}")
    seqs = [d["seq"] for d in gps]
    lost = rk.need_ok(O, "lost_frames", seqs, n=2)
    print(f"\nSequence numbers of those frames: {seqs[:6]} … {seqs[-4:]}")
    print(f"  your lost_frames → lost {lost[0]}, doubled {lost[1]}")
    m0 = dec[0]
    print(f"\nFirst GPS_INPUT: lat {m0['lat']:.7f}, lon {m0['lon']:.7f}, time_week {m0['time_week']}, "
          f"time_week_ms {m0['time_week_ms']}")
    plt = rk.plt_or_none()
    if plt:
        fig, ax = plt.subplots(figsize=(5, 5))
        for sat, col, lab in ((10, "#1f77b4", "satellites 10 (GPS)"), (0, "#ff7f0e", "satellites 0")):
            pts = [(m["lon"], m["lat"]) for m in dec if m["satellites_visible"] == sat]
            if pts:
                ax.scatter(*zip(*pts), s=6, color=col, label=lab)
        ax.set_xlabel("longitude (°)")
        ax.set_ylabel("latitude (°)")
        ax.legend(fontsize=8)
        ax.ticklabel_format(useOffset=False)
        fig.tight_layout()
        os.makedirs("out", exist_ok=True)
        fig.savefig("out/stream.png", dpi=80)
        rk.saved("out/stream.png")


def noise():
    S = sensors_mod()
    dt, tau, q = 0.2, 20.0, 0.6
    n = int(3600 / dt)
    x = rk.need_ok(S, "gauss_markov", n, dt, tau, q, np.random.default_rng(31))
    x = np.asarray(x, dtype=float)
    if x.shape != (n,):
        sys.exit(f"gauss_markov() must return {n} numbers, got shape {x.shape}")
    sig = rk.need_ok(S, "stationary_sigma", dt, tau, q, kind=float)
    print(f"One hour of receiver noise, one axis (dt {dt} s, τ {tau:g} s, q {q}), seed 31:")
    print(f"  measured standard deviation   {x.std():.3f} m")
    print(f"  your stationary_sigma         {sig:.3f} m")
    a = 1.0 - dt / tau
    print("  lag      your autocorrelation   a^lag")
    for lag_s in (1, 10, 20, 60):
        lag = int(round(lag_s / dt))
        r = rk.need_ok(S, "autocorrelation", x, lag, kind=float)
        print(f"  {lag_s:3d} s    {r:8.3f}               {a ** lag:.3f}")
    means = [np.mean(x[i:i + int(10 / dt)]) for i in range(0, n, int(10 / dt))]
    print(f"\n  the 10 s averages of the noise still spread by {np.std(means):.2f} m (σ / √50 would be "
          f"{sig / math.sqrt(50):.2f} m)")
    plt = rk.plt_or_none()
    if plt:
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5))
        t = np.arange(n) * dt
        a1.plot(t[:3000], x[:3000], lw=0.8)
        a1.set_xlabel("time (s)")
        a1.set_ylabel("noise, east (m)")
        lags = np.arange(0, 600)
        ac = [S.autocorrelation(x, int(k)) for k in lags[::10]]
        a2.plot(lags[::10] * dt, ac, label="your autocorrelation")
        a2.plot(lags * dt, a ** lags, "--", label="a^lag")
        a2.set_xlabel("lag (s)")
        a2.legend()
        fig.tight_layout()
        os.makedirs("out", exist_ok=True)
        fig.savefig("out/noise.png", dpi=80)
        rk.saved("out/noise.png")


def rayleigh():
    S = sensors_mod()
    rng = np.random.default_rng(32)
    print("200 000 vision errors per profile: east and north each N(0, σ²). Horizontal error r = √(e² + n²).")
    print("  σ (m)     p      measured r_p (m)   your rayleigh_quantile (m)")
    for sigma in (15.0, 373.7):
        e, n = rng.normal(0, sigma, (2, 200000))
        r = np.hypot(e, n)
        for p in (0.5, 0.95, 0.99):
            want = rk.need_ok(S, "rayleigh_quantile", sigma, p, kind=float)
            print(f"  {sigma:6.1f}  {p:5.2f}   {np.percentile(r, 100 * p):12.1f}        {want:12.1f}")
    print(f"\nsigma_for_median(440.0) = {S.sigma_for_median(440.0):.1f} m: the 'measured' profile's σ")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"hex": hexdump, "test": test, "stream": stream, "noise": noise, "rayleigh": rayleigh}.get(
        mode, lambda: sys.exit(__doc__.split("\n\n")[1]))()


if __name__ == "__main__":
    main()
