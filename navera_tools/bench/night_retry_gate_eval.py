#!/usr/bin/env python3
"""Right vs wrong retried night fixes, and what a retry gate would keep (offline).

Reads the --probe-jsonl files of night_real_thermal.py / night_conditions.py (every hypothesis
of every frame, night_retry_probe) and:
  * lists every retried success with its evidence (map-check NCC, shifted-map control margin,
    second-centre distance, consistency, retry size, number of hypotheses tried, agreement with
    the other hypotheses' answers) and its true error;
  * replays localize's choice per frame without a gate and with the gate of
    night_localizer.retry_evidence_ok (or a grid of its parameters), and prints the
    accepted / wrong / right-retried counts per run.

    python3 navera_tools/bench/night_retry_gate_eval.py probe1.jsonl probe2.jsonl [--list] [--grid]
"""
import argparse
import itertools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT / "night_pkg", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import night_retry_probe as nrp  # noqa: E402

WRONG_M = 50.0


def load(paths):
    frames = []
    for p in paths:
        for line in open(p):
            d = json.loads(line)
            d["file"] = Path(p).stem
            d["run"] = f"{Path(p).stem}:{d.get('cond') or d['sensor']}:{d['agl']:.0f}"
            for a in d["attempts"]:
                a["err"] = nrp.error_m(a, d["lat"], d["lon"]) if a["success"] else None
            frames.append(d)
    return frames


def support_m(a, k, attempts):
    """Distance from attempt k's fix to the nearest answer of another hypothesis of the same
    frame (either search centre, accepted or not)."""
    best = None
    for j, b in enumerate(attempts):
        if j == k:
            continue
        for c in (b["c1"], b["c2"]):
            m = nrp._m(a["lat"], a["lon"], c[0], c[1]) if c and c[0] is not None else None
            if m is not None and (best is None or m < best):
                best = m
    return best


def gate_from(params):
    """A gate callable from params (the localizer's own retry_evidence_ok)."""
    from night_pkg.nodes.night_localizer import retry_evidence_ok

    def g(a, k, attempts):
        return retry_evidence_ok(dict(verify=dict(ncc=a["ncc"]), recheck=dict(verify=dict(ncc=a["ncc2"])),
                                      recheck_m=a["recheck_m"], conf=a["conf"]), k, **params)
    return g


def replay(frames, gate):
    out = defaultdict(lambda: dict(n=0, acc=0, wrong=0, retried_right=0, retried_wrong=0))
    for f in frames:
        s = out[f["run"]]
        s["n"] += 1
        k = nrp.decide(f["attempts"], gate)
        if k is None:
            continue
        a = f["attempts"][k]
        wrong = f.get("no_info") or a["err"] > WRONG_M
        s["acc"] += 1
        s["wrong"] += bool(wrong)
        if k:
            s["retried_wrong" if wrong else "retried_right"] += 1
    return out


def totals(stats):
    t = dict(n=0, acc=0, wrong=0, retried_right=0, retried_wrong=0)
    for s in stats.values():
        for key in t:
            t[key] += s[key]
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl", nargs="+")
    ap.add_argument("--list", action="store_true", help="list every retried success")
    ap.add_argument("--grid", action="store_true", help="evaluate a grid of gate parameters")
    ap.add_argument("--params", default="", help="gate params as JSON (default: the localizer's defaults)")
    a = ap.parse_args()
    frames = load(a.jsonl)
    print(f"{len(frames)} frames, {sum(len(f['attempts']) for f in frames)} hypotheses")

    if a.list:
        print(f"\n{'run':34s} {'i':>3s} {'k':>2s} {'d':>4s} {'f':>5s} {'err':>5s} {'ncc':>6s} {'ctrl':>6s} "
              f"{'margin':>6s} {'ncc2':>6s} {'rc':>5s} {'conf':>5s} {'supp':>5s} {'ok_tries':>8s}")
        for f in frames:
            att = f["attempts"]
            for k, x in enumerate(att):
                if k == 0 or not x["success"]:
                    continue
                sup = support_m(x, k, att)
                oks = sum(1 for y in att[1:] if y["success"])
                err = x["err"] if not f.get("no_info") else 9999
                print(f"{f['run'][:34]:34s} {f['i']:3d} {k:2d} {x['d']:4.0f} {x['f']:5.2f} {err:5.0f} "
                      f"{x['ncc']:6.3f} {x['ncc_ctrl'] if x['ncc_ctrl'] is not None else float('nan'):6.3f} "
                      f"{x['ncc_margin'] if x['ncc_margin'] is not None else float('nan'):6.3f} "
                      f"{x['ncc2'] if x['ncc2'] is not None else float('nan'):6.3f} {x['recheck_m']:5.1f} "
                      f"{x['conf']:5.3f} {sup if sup is not None else float('nan'):5.0f} {oks:8d}"
                      f"{'  WRONG' if err > WRONG_M else ''}")

    base = replay(frames, None)
    from night_pkg.nodes.night_localizer import RETRY_GATE_DEFAULTS
    params = json.loads(a.params) if a.params else dict(RETRY_GATE_DEFAULTS)
    gated = replay(frames, gate_from(params))
    print(f"\ngate {params}")
    print(f"{'run':40s} {'n':>4s} {'acc':>9s} {'wrong':>7s} {'retried ok':>11s} {'retried wrong':>13s}")
    for run in base:
        b, g = base[run], gated[run]
        print(f"{run[:40]:40s} {b['n']:4d} {b['acc']:4d}>{g['acc']:<4d} {b['wrong']:3d}>{g['wrong']:<3d} "
              f"{b['retried_right']:5d}>{g['retried_right']:<5d} {b['retried_wrong']:6d}>{g['retried_wrong']:<6d}")
    tb, tg = totals(base), totals(gated)
    print(f"{'TOTAL':40s} {tb['n']:4d} {tb['acc']:4d}>{tg['acc']:<4d} {tb['wrong']:3d}>{tg['wrong']:<3d} "
          f"{tb['retried_right']:5d}>{tg['retried_right']:<5d} {tb['retried_wrong']:6d}>{tg['retried_wrong']:<6d}")

    if a.grid:
        rows = []
        for ncc, both, rc, per, conf in itertools.product(
                (0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12), (False, True), (25.0, 20.0, 15.0, 12.0),
                (0.0, 0.005, 0.01, 0.02), (None, 0.9, 0.93, 0.95, 0.96, 0.97)):
            p = dict(min_ncc=ncc, both_centres=both, recheck_max_m=rc, ncc_per_try=per, min_conf=conf)
            t = totals(replay(frames, gate_from(p)))
            rows.append((t["retried_wrong"], -t["retried_right"], p, t))
        rows.sort(key=lambda r: (r[0], r[1]))
        print("\nbest gates (retried wrong, retried right kept):")
        for w, r, p, t in rows[:25]:
            print(f"  wrong {w}  right {-r}/{tb['retried_right']} ({-r / max(1, tb['retried_right']):.0%})  "
                  f"total wrong {t['wrong']}  {p}")


if __name__ == "__main__":
    main()
