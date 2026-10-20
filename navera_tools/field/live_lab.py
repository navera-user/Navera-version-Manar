#!/usr/bin/env python3
"""Try settings on the test so far, while it runs: snapshot the live session, replay it (replay360) with the
baseline and each variant in parallel, and score every run against the phone's GPS.

    python3 -m navera_tools.field.live_lab <session folder> \\
        --variant k5:allsky.DETECT_K_SIGMA=5 --variant gap1:server.STOPPED_SOLVE_GAP_S=1,allsky.MIN_MATCHED=9 \\
        [--last-min N] [--jobs 2] [--out DIR] [--no-baseline]
    python3 -m navera_tools.field.live_lab <session folder> --export-stops DIR     # lossless PNGs of the stops

Read-only on the live folder: the closed raw files are hard-linked (copied across file systems), the one being
written is copied up to its last complete record, the .jsonl files up to their last complete line. --last-min N
keeps only the last N minutes of the recording (faster; the tilt calibration then starts again in the replay).
A variant is NAME:KEY=VALUE[,KEY=VALUE...]; KEY is any module constant replay360 --set accepts (server., allsky.,
sky360., insta360_usb.); knobs of the live server (server.LIVE_PARAMS) are also range-checked here so that a
winner can be applied live with livectl as it is. Each run is scored on its own frames: trusted (stopped) fixes,
error median / p90 / max raw and tilt-corrected (after the calibration froze), wrong (> 50 km), within 3 sigma,
why frames were not solved, solve time. One markdown table on stdout, everything in <out>/lab.json.
"""
import argparse
import collections
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field.insta360_usb import RAW_MAGIC, RAW_RECORD  # noqa: E402

WRONG_KM = 50.0
MODULES = ("server", "allsky", "sky360", "insta360_usb")


def complete_raw_length(path):
    """Bytes of a raw file up to its last complete record (the file may be growing)."""
    with open(path, "rb") as f:
        if f.read(len(RAW_MAGIC)) != RAW_MAGIC:
            return 0
        end = f.tell()
        size = os.fstat(f.fileno()).st_size
        while True:
            h = f.read(RAW_RECORD.size)
            if len(h) < RAW_RECORD.size:
                return end
            ln = RAW_RECORD.unpack(h)[3]
            if end + RAW_RECORD.size + ln > size:
                return end
            f.seek(ln, 1)
            end = f.tell()


def _copy_prefix(src, dst, n):
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        left = n
        while left > 0:
            b = fi.read(min(left, 8 << 20))
            if not b:
                break
            fo.write(b)
            left -= len(b)


def _copy_lines(src, dst):
    """A .jsonl file up to its last complete line."""
    if not os.path.exists(src):
        return
    with open(src, "rb") as fi:
        data = fi.read()
    cut = data.rfind(b"\n") + 1
    with open(dst, "wb") as fo:
        fo.write(data[:cut])


def snapshot(session, dest, last_min=None):
    """Copy of the session as it is now, safe while the server writes it. Returns dest."""
    os.makedirs(os.path.join(dest, "raw"), exist_ok=True)
    shutil.copy(os.path.join(session, "session.json"), os.path.join(dest, "session.json"))
    for n in ("events.jsonl", "phone.jsonl", "frames.jsonl"):
        _copy_lines(os.path.join(session, n), os.path.join(dest, n))
    raw = os.path.join(session, "raw")
    names = sorted(n for n in os.listdir(raw) if n.startswith("raw360_") and n.endswith(".bin")) if os.path.isdir(raw) else []
    if not names:
        raise SystemExit(f"{raw}: no raw recording to replay")
    for i, n in enumerate(names):
        src, dst = os.path.join(raw, n), os.path.join(dest, "raw", n)
        if i < len(names) - 1:
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy(src, dst)
        else:
            _copy_prefix(src, dst, complete_raw_length(src))
    if last_min:
        _keep_last(os.path.join(dest, "raw"), last_min)
    return dest


def _keep_last(raw_dir, minutes):
    """Rewrite the snapshot's raw files keeping the last `minutes` (+10 s of IMU history before them)."""
    from navera_tools.field.insta360_usb import read_raw
    t_end = None
    for t, *_ in read_raw(raw_dir):
        t_end = t
    if t_end is None:
        return
    t0 = t_end - 60.0 * minutes - 10.0
    out = os.path.join(raw_dir, "keep.tmp")
    with open(out, "wb") as fo:
        fo.write(RAW_MAGIC)
        for t, kind, cam_ms, p in read_raw(raw_dir):
            if t >= t0:
                fo.write(RAW_RECORD.pack(t, kind, cam_ms, len(p)))
                fo.write(p)
    for n in os.listdir(raw_dir):
        if n.startswith("raw360_"):
            os.remove(os.path.join(raw_dir, n))
    os.replace(out, os.path.join(raw_dir, "raw360_0000.bin"))


def parse_variant(spec):
    """'NAME:KEY=VAL,KEY=VAL' -> (name, [KEY=VAL, ...]); refuses unknown modules and out-of-range live knobs."""
    from navera_tools.field.server import LIVE_PARAMS, check_live_param
    name, sep, rest = spec.partition(":")
    if not sep or not re.fullmatch(r"[A-Za-z0-9_.+-]+", name):
        raise SystemExit(f"--variant {spec!r}: expected NAME:KEY=VALUE[,KEY=VALUE]")
    sets = []
    for item in re.split(r",(?=[A-Za-z_][A-Za-z0-9_]*\.)", rest):       # commas inside a tuple value stay with it
        k, eq, v = item.partition("=")
        mod = k.partition(".")[0]
        if not eq or mod not in MODULES:
            raise SystemExit(f"--variant {spec!r}: {item!r} is not MODULE.NAME=VALUE with MODULE in {MODULES}")
        if k in LIVE_PARAMS:
            try:
                val = json.loads(v.replace("(", "[").replace(")", "]"))
            except ValueError:
                val = v
            _, why = check_live_param(k, val)
            if why:
                raise SystemExit(f"--variant {spec!r}: {k} {why}")
        sets.append(f"{k}={v}")
    return name, sets


def run_replay(snap, out_dir, sets):
    cmd = ["nice", "-n", "19", sys.executable, "-m", "navera_tools.field.replay360", snap, "--out", out_dir]
    for s in sets:
        cmd += ["--set", s]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "navera_common"),
                                                        os.path.join(ROOT, "cn_pkg"), os.environ.get("PYTHONPATH", "")]),
               OMP_NUM_THREADS="1")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)
    m = re.search(r"replayed test: (.+)", p.stdout)
    return {"folder": m.group(1).strip() if m else None, "wall_s": round(time.time() - t0, 1), "rc": p.returncode,
            "stderr_tail": p.stderr[-600:] if p.returncode or not m else ""}


def _q(v):
    v = sorted(v)
    if not v:
        return None
    return [round(v[len(v) // 2], 1), round(v[min(len(v) - 1, int(0.9 * len(v)))], 1), round(v[-1], 1)]


def score(folder):
    """Scores of one (replayed or live) test folder against its phone track."""
    from navera_tools.field.reprocess360 import haversine_km, truth_at
    from navera_tools.field.store import read_jsonl
    frames = [f for f in read_jsonl(os.path.join(folder, "frames.jsonl")) if isinstance(f, dict) and f.get("mode") == "360"]
    phone = sorted((p for p in read_jsonl(os.path.join(folder, "phone.jsonl")) if isinstance(p, dict) and p.get("t")),
                   key=lambda p: p["t"])
    solved = [f for f in frames if f.get("solved")]
    trusted = [f for f in solved if f.get("stopped") and not f.get("stopped_but_phone_moving")]
    raw, cal = [], []
    for f in trusted:
        tru = truth_at(phone, f.get("t_exp") or f.get("t"))
        if tru is None:
            continue
        e = haversine_km(f["lat"], f["lon"], *tru)
        raw.append((e, f.get("sigma_km")))
        if f.get("lat_cal") is not None and not f.get("cal_sample"):
            cal.append((haversine_km(f["lat_cal"], f["lon_cal"], *tru), f.get("sigma_km_cal")))
    why = collections.Counter(str(f.get("why") or "?").split("(")[0].split(":")[0].strip()[:40]
                              for f in frames if not f.get("solved"))
    solve = sorted(f["solve_s"] for f in frames if isinstance(f.get("solve_s"), (int, float)))

    def block(rows):
        return {"n": len(rows), "err_km_p50_p90_max": _q([e for e, _ in rows]),
                "wrong": sum(e > WRONG_KM for e, _ in rows),
                "within_3sigma": sum(1 for e, s in rows if s and e <= 3 * s)}
    return {"frames": len(frames), "solved": len(solved), "trusted": len(trusted), "moving_fixes": len(solved) - len(trusted),
            "raw": block(raw), "corrected": block(cal),
            "not_solved": dict(why.most_common(4)), "solve_s_median": solve[len(solve) // 2] if solve else None}


def table(results):
    def f3(v):
        return " / ".join(str(x) for x in v) if v else "-"
    lines = ["| run | settings | frames | trusted fixes | raw err km p50/p90/max | raw wrong | raw in 3σ | "
             "corrected fixes | corrected err km p50/p90/max | corr. wrong | corr. in 3σ | solve s | not solved (top) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r.get("score")
        if not s:
            lines.append(f"| {r['name']} | {' '.join(r['sets']) or 'baseline'} | replay failed (rc {r['rc']}) |"
                         + " |" * 10)
            continue
        ra, co = s["raw"], s["corrected"]
        why = "; ".join(f"{k} x{v}" for k, v in s["not_solved"].items())
        lines.append(f"| {r['name']} | {' '.join(r['sets']) or 'baseline'} | {s['frames']} | {s['trusted']} | "
                     f"{f3(ra['err_km_p50_p90_max'])} | {ra['wrong']} | {ra['within_3sigma']}/{ra['n']} | {co['n']} | "
                     f"{f3(co['err_km_p50_p90_max'])} | {co['wrong']} | {co['within_3sigma']}/{co['n']} | "
                     f"{s['solve_s_median']} | {why} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--variant", action="append", default=[], metavar="NAME:KEY=VAL[,KEY=VAL]")
    ap.add_argument("--last-min", type=float, default=None)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--out", default="")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--export-stops", default="", metavar="DIR")
    a = ap.parse_args(argv)
    variants = [parse_variant(v) for v in a.variant]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = a.out or os.path.join(os.path.dirname(os.path.normpath(a.session)), "lab",
                                os.path.basename(os.path.normpath(a.session)) + "_" + stamp)
    snap = snapshot(a.session, os.path.join(out, "snapshot"), a.last_min)
    print(f"snapshot: {snap}", flush=True)
    if a.export_stops:
        from navera_tools.field.replay360 import export_frames
        n = export_frames(os.path.join(snap, "raw"), a.export_stops, True, False)
        print(f"{n} stopped frames written to {a.export_stops}")
        if not variants:
            return 0
    runs = ([] if a.no_baseline else [("baseline", [])]) + variants
    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = {ex.submit(run_replay, snap, os.path.join(out, name), sets): (name, sets) for name, sets in runs}
        for fu in cf.as_completed(futs):
            name, sets = futs[fu]
            r = {"name": name, "sets": sets, **fu.result()}
            r["score"] = score(r["folder"]) if r["folder"] and os.path.isdir(r["folder"]) else None
            print(f"  done {name} in {r['wall_s']} s" + ("" if r["score"] else f" FAILED: {r['stderr_tail'][-200:]}"),
                  flush=True)
            results.append(r)
    order = [n for n, _ in runs]
    results.sort(key=lambda r: order.index(r["name"]))
    md = table(results)
    print(md)
    with open(os.path.join(out, "lab.json"), "w") as fh:
        json.dump({"session": a.session, "snapshot": snap, "last_min": a.last_min, "runs": results}, fh, indent=1)
    with open(os.path.join(out, "lab.md"), "w") as fh:
        fh.write(md + "\n")
    print(f"written: {os.path.join(out, 'lab.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
