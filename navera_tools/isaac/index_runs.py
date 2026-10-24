#!/usr/bin/env python3
"""Index every Isaac Sim run kept on this computer into one markdown table (SIMULATION results).

    python3 navera_tools/isaac/index_runs.py [ROOT=~/.navera_sim/isaac] [OUT=ROOT/ISAAC_RUNS_INDEX.md]

Reads each folder's campaign.jsonl (campaign.py runs) and every run folder's summary_flight.json
or summary.json (single runs: run_closed_loop.sh, hil_flight.sh, endurance). One row per run:
folder, condition, matched %, fix error at the stated time (median/p90/max), wrong fixes (> 50 m),
outputs beyond 3 sigma, autopilot EKF max, mission outcome.
"""
import json
import os
import sys


def _num(v, fmt="{:.1f}"):
    return "–" if v is None else fmt.format(v)


def _row(group, run, what, s):
    ac = s.get("after_cut") or s.get("denied") or {}
    err = ac.get("fix_err_stamp_m") or {}
    b3 = s.get("output_beyond_3sigma") or {}
    ekf = s.get("autopilot_ekf_err_after_cut_m") or s.get("ekf_err_m") or {}
    m = s.get("mission") or {}
    if m.get("completed"):
        mission = "completed"
    elif m:
        mission = "NOT completed" + (f" ({m['failsafe'][0]})" if m.get("failsafe") else "")
    else:
        mission = "–"
    return (f"| {group} | {run} | {what} | {_num(ac.get('accepted_pct'))} | "
            f"{_num(err.get('median'))}/{_num(err.get('p90'))}/{_num(err.get('max'))} | "
            f"{ac.get('wrong_fixes', '–')} | {b3.get('n', '–')}/{b3.get('of', '–')} | "
            f"{_num(ekf.get('max'), '{:.0f}')} | {mission} |")


def main(argv):
    root = os.path.expanduser(argv[1] if len(argv) > 1 else "~/.navera_sim/isaac")
    out = argv[2] if len(argv) > 2 else os.path.join(root, "ISAAC_RUNS_INDEX.md")
    rows, seen = [], set()
    for group in sorted(os.listdir(root)):
        gdir = os.path.join(root, group)
        if not os.path.isdir(gdir):
            continue
        cj = os.path.join(gdir, "campaign.jsonl")
        if os.path.exists(cj):
            for line in open(cj):
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("summary"):
                    rows.append(_row(group, d["run"], d.get("what") or d.get("condition", ""), d["summary"]))
                    seen.add(os.path.join(gdir, d["run"]))
        for run in sorted(os.listdir(gdir)):
            rdir = os.path.join(gdir, run)
            if rdir in seen or not os.path.isdir(rdir):
                continue
            for name in ("summary_flight.json", "summary.json"):
                p = os.path.join(rdir, name)
                if os.path.exists(p):
                    try:
                        s = json.load(open(p))
                    except ValueError:
                        break
                    if isinstance(s, dict) and (s.get("after_cut") or s.get("mission") or s.get("denied")):
                        rows.append(_row(group, run, "single run", s))
                    break
    head = ["# Isaac Sim runs — index (SIMULATION)", "",
            f"{len(rows)} runs under `{root}`. Fix error = NAVERA's error at its stated time after the GPS cut "
            "(median/p90/max, m); wrong = fixes > 50 m off; >3σ = outputs beyond 3 × the stated accuracy; "
            "EKF max = the autopilot's worst position error (m). Each run folder holds its own files "
            "(flight.mp4, plot_final.png, summary_flight.json, ENDURANCE.md for long flights).", "",
            "| folder | run | condition | matched % | fix error med/p90/max | wrong | >3σ | EKF max | mission |",
            "|---|---|---|---|---|---|---|---|---|"]
    with open(out, "w") as f:
        f.write("\n".join(head + rows) + "\n")
    print(f"{out}: {len(rows)} runs")


if __name__ == "__main__":
    main(sys.argv)
