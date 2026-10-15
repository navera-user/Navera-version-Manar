#!/usr/bin/env python3
"""Mission 31: the check's hidden data (teacher only). Run after any change to the reference parts, the campaign
scenarios or the dataset:

    python3 solutions/31-simulator/make_expected.py        # ≈ 1 min; writes courses/31-simulator/hidden/expected.json

Everything is computed from the course's reference (solutions/31-simulator/navera_lite, campaign.py) in a scratch
folder that looks like a student's lesson folder, with the dataset of datasets/31-simulator:
  units     unseen inputs for TODOs 1–10 and the reference answers
  lab       the lab's own numbers (stream, noise, Rayleigh, rule-based expectations, the campaign's metrics,
            plane_delayed), for the answers and results.json checks
  flights   two hidden scenarios the check flies with the student's decoder, and their reference metrics
  scenarios the campaign's scenario files as shipped (the check refuses edited ones)
"""
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
FILES = os.path.join(REPO, "courses", "31-simulator", "files")
HIDDEN = os.path.join(REPO, "courses", "31-simulator", "hidden")
DATA = os.path.join(REPO, "datasets", "31-simulator")
HIDDEN_FLIGHTS = [
    {"name": "h_boat_off", "vehicle": "boat", "vision": "target", "seed": 501, "duration_s": 80,
     "faults": [[20, "gps", "off"], [50, "gps", "ok"]]},
    {"name": "h_night_blind", "vehicle": "drone", "vision": "target", "light": "night", "seed": 502,
     "duration_s": 60, "faults": [[25, "gps", "jammed"], [35, "camera", "blackout"]]},
]


def scratch():
    d = tempfile.mkdtemp(prefix="m31exp_")
    for f in ("navera_lite.yaml", "runner_kit.py", "academy_gpu.py", "mav_lab.py", "vision_check.py", "ref_desc.pt",
              "ref_homography.pt"):
        shutil.copy(os.path.join(FILES, f), d)
    shutil.copytree(os.path.join(FILES, "campaign"), os.path.join(d, "campaign"))
    shutil.copytree(os.path.join(HERE, "navera_lite"), os.path.join(d, "navera_lite"))
    shutil.copy(os.path.join(HERE, "campaign.py"), d)
    return d


def units(O, S, C):
    rng = np.random.default_rng(3101)
    dec = []
    for k in range(6):
        f = {"time_usec": int(rng.integers(1, 2 ** 52)), "time_week_ms": int(rng.integers(0, 604800000)),
             "lat": int(rng.integers(-900000000, 900000000)), "lon": int(rng.integers(-1800000000, 1800000000)),
             "alt": float(np.float32(rng.uniform(-50, 3000))), "hdop": float(np.float32(rng.uniform(0, 5))),
             "vdop": 0.0, "vn": float(np.float32(rng.normal(0, 20))), "ve": float(np.float32(rng.normal(0, 20))),
             "vd": 0.0, "speed_accuracy": 0.0, "horiz_accuracy": float(np.float32(rng.uniform(0, 400))),
             "vert_accuracy": 0.0, "ignore_flags": int(rng.integers(0, 256)), "time_week": int(rng.integers(2000, 2500)),
             "gps_id": 0, "fix_type": int(rng.integers(0, 4)), "satellites_visible": int(rng.integers(0, 20)),
             "yaw": int(rng.integers(0, 36000)) if k % 2 else 0}
        payload = struct.pack(O.GPS_INPUT_FORMAT, *(f[n] for n in O.GPS_INPUT_FIELDS)).rstrip(b"\x00")
        want = O.decode_gps_input(payload)
        dec.append({"payload": payload.hex(), "want": want})
    fields = dict.fromkeys(O.GPS_INPUT_FIELDS, 0)
    fields.update(lat=-339249000, lon=184241000, fix_type=3, horiz_accuracy=4.5, ignore_flags=189, time_week=2390)
    frames = [O.encode_gps_input(dict(fields, time_usec=10 ** 15 + i), 250 + i) for i in range(8)]
    hb = bytes([O.STX, 9, 0, 0, 3, 1, 1, 0, 0, 0]) + bytes([1, 2, 3, 4, 2, 3, 81, 4, 3])
    hb = hb + O.frame_crc(hb + b"\0\0", 0).to_bytes(2, "little")
    other = bytes([O.STX, 4, 0, 0, 9, 1, 1, 33, 0, 0, 1, 2, 3, 4, 0x12, 0x34])        # msgid 33: no CRC_EXTRA here
    signed = bytearray(frames[3])
    signed[2] = 1                                                                  # signed: 13 more bytes
    # its 13 signature bytes hold something that looks like a frame start: only a parser that skips them is right
    sig = bytes([0xFD, 0x02, 0x00, 0x00, 0x05, 0x01, 0x01, 0xE8, 0x00, 0x00, 0x11, 0x22, 0x33])
    signed = bytes(signed[:-2]) + O.frame_crc(bytes(signed), 232).to_bytes(2, "little") + sig
    bad = bytearray(frames[5])
    bad[25] ^= 0x10
    streams = [b"\xfd" + frames[0] + b"\x00\xfd\x02" + frames[1] + hb + frames[2][:-1],
               bytes(bad) + frames[6] + other + frames[7],
               b"\x11" * 7 + signed + frames[4] + b"\xfd",
               frames[0] + frames[0] + frames[2]]
    parse = [{"data": s.hex(), "want": [{k: (v.hex() if isinstance(v, bytes) else v) for k, v in d.items()}
                                         for d in O.parse_frames(s)]} for s in streams]
    ign = [{"flags": f, "want": O.ignored(f)} for f in (0, 1, 64, 189, 180, 255, 130)]
    lost = [{"seqs": s, "want": list(O.lost_frames(s))} for s in
            ([1, 2, 3], [7, 7, 7, 8], [254, 255, 0, 2], [10, 9], [], [5], [100, 150, 200, 250, 44])]
    gm = []
    for n, dt, tau, q, seed, x0 in ((5, 0.5, 10.0, 1.2, 7, 0.0), (4, 0.2, 20.0, 0.6, 99, 3.0), (6, 1.0, 5.0, 2.0, 1, -1.0)):
        gm.append({"args": [n, dt, tau, q, seed, x0],
                   "want": S.gauss_markov(n, dt, tau, q, np.random.default_rng(seed), x0).tolist()})
    stat = [{"args": a, "want": S.stationary_sigma(*a)} for a in ((0.5, 10.0, 1.2), (1.0, 30.0, 0.3), (0.1, 2.0, 5.0))]
    rr = random.Random(5)
    ac = []
    for lag in (0, 1, 3, 7):
        x = [round(rr.gauss(0, 2) + 0.3 * i, 3) for i in range(12)]
        ac.append({"x": x, "lag": lag, "want": S.autocorrelation(x, lag)})
    ray = [{"args": a, "want": S.rayleigh_quantile(*a)} for a in ((30.0, 0.5), (2.5, 0.9), (100.0, 0.99), (8.0, 0.0))]
    lat = []
    rows = [{"t_s": round(10 + 0.2 * i, 1), "lite_source": s} for i, s in
            enumerate(["gps"] * 6 + ["night"] * 5 + [""] * 4 + ["night"] * 3 + ["gps"] * 4)]
    for t0, t1 in ((10.4, 13.0), (11.0, 13.4), (10.0, None), (13.8, 14.0), (14.4, 50.0), (11.2, 13.6), (12.1, 13.5)):
        lat.append({"rows": rows, "t0": t0, "t1": t1, "want": list(C.latencies(rows, t0, t1))})
    ver = [{"args": a, "want": list(C.verdict(*a))} for a in
           ((2.5, "<=", 4.0), (4.0, "<=", 4.0), (4.01, "<=", 4.0), (0.97, ">=", 0.95), (0.5, ">=", 0.95),
            (None, ">=", 0.95), (0.0, "<=", 0.0))]
    return {"decode": dec, "parse": parse, "ignored": ign, "lost": lost, "gauss_markov": gm, "stationary": stat,
            "autocorr": ac, "rayleigh": ray, "latencies": lat, "verdict": ver}


def main():
    d = scratch()
    env = dict(os.environ, NAVERA_LITE_SIM_DATA=DATA, PYTHONPATH="")
    sys.path.insert(0, d)
    os.chdir(d)
    from navera_lite import output as O
    from navera_lite import spoof
    from navera_lite.sim import sensors as S
    import campaign as C
    E = {"units": units(O, S, C)}
    with open(os.path.join(HIDDEN, "stream_truth.json")) as f:
        stream = json.load(f)
    x = S.gauss_markov(int(3600 / 0.2), 0.2, 20.0, 0.6, np.random.default_rng(31))
    sig_s = math.sqrt(1.8 ** 2 + 15.0 ** 2 + (30.0 * 0.1) ** 2)
    lab = {"header_len": 63, "stream": stream, "gm_sigma": float(x.std()), "corr_10s": S.autocorrelation(x, 50),
           "rayleigh_p95_15": S.rayleigh_quantile(15.0, 0.95), "expect_off_switch_s": 3.0,
           "expect_jump_gate_m": 30.0 * 0.2 + 50.0,
           "expect_drift_s": spoof.drift_alarm_time(4.0, sig_s, spoof.chi2_threshold_2d(0.01), 5, 1.0)}
    subprocess.run([sys.executable, "campaign.py", "run"], check=True, env=env, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, "-m", "navera_lite.sim.run", "campaign/plane_delayed.json", "--quiet"], check=True,
                   env=env, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, "campaign.py", "report"], check=True, env=env, stdout=subprocess.DEVNULL)
    with open("results.json") as f:
        res = json.load(f)
    lab["runs"] = res["runs"]
    lab["verdicts"] = {v["id"]: v["verdict"] for v in res["verdicts"]}
    lab["failed"] = [k for k, v in lab["verdicts"].items() if v == "FAIL"]
    lab["plane_delayed"] = C.measure(C.load_run("my_runs/plane_delayed.csv"), C.scenario("plane_delayed"))
    lab["rows"] = {n: len(C.load_run(f"my_runs/{n}.csv")) for n in C.RUNS + ["plane_delayed"]}
    flights = []
    for sc in HIDDEN_FLIGHTS:
        with open("h.json", "w") as f:
            json.dump(sc, f)
        subprocess.run([sys.executable, "-m", "navera_lite.sim.run", "h.json", "--out", "hid", "--quiet"], check=True,
                       env=env, stdout=subprocess.DEVNULL)
        m = C.measure(C.load_run(f"hid/{sc['name']}.csv"), sc)
        flights.append({"scenario": sc, "want": m, "rows": len(C.load_run(f"hid/{sc['name']}.csv"))})
    E["lab"], E["flights"] = lab, flights
    E["scenarios"] = {}
    for fn in sorted(os.listdir("campaign")):
        with open(os.path.join("campaign", fn)) as f:
            E["scenarios"][fn] = json.load(f)
    os.makedirs(HIDDEN, exist_ok=True)
    with open(os.path.join(HIDDEN, "expected.json"), "w") as f:
        json.dump(E, f, indent=1)
    print("lab:", json.dumps({k: v for k, v in lab.items() if k not in ("runs", "stream")}, indent=1))
    for n, m in lab["runs"].items():
        print(n, m)
    for fl in flights:
        print(fl["scenario"]["name"], fl["want"])
    shutil.rmtree(d)


if __name__ == "__main__":
    main()
