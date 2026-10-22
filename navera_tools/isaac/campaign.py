#!/usr/bin/env python3
"""Closed-loop conditions campaign: run_closed_loop.sh once per condition, one after another.

    python3 navera_tools/isaac/campaign.py --ssh dev@100.115.52.19 --only base,dawn,... \
        [--prefix c1_] [--notice /tmp/claude-1000/isaac_window_soon.txt] [--copy-to DIR]
    python3 navera_tools/isaac/campaign.py --list

Each condition changes ONE factor against the clear baseline (or names a worst-case combination).
Per run: notice line, the launcher on the PC (windows open, no gate), its results summarised
(summarise.py) and copied to --copy-to; campaign.md / campaign.jsonl collect the table.
SIMULATION only (Isaac Sim scene, ArduPilot SITL, NAVERA's real nodes).
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from summarise import summarise  # noqa: E402

SHORT = "--legs 3 --radius 400 --speed 10 --cut-after 75 --sigma 15"
FULL = "--legs 4 --radius 500 --speed 8 --cut-after 75 --sigma 15"
PLANE = "--vehicle plane --gimbal false --legs 4 --radius 1300 --cut-after 75 --sigma 15 --alt 400"

# name: (what, launcher arguments)
CONDITIONS = {
    "base": ("clear baseline, 10:30, copter 250 m, gimbal", SHORT),
    "base_nolat": ("baseline, auto_latency OFF", SHORT + " --day-args '-p auto_latency:=false'"),
    "dawn": ("low sun 07:00 (long shadows, low contrast)", SHORT + " --time 07:00"),
    "dusk": ("low sun 17:15", SHORT + " --time 17:15"),
    "noon": ("noon harsh shadows 12:30", SHORT + " --time 12:30"),
    "overcast": ("overcast flat light", SHORT + " --isaac-args '--sun 250 --sky 900 --clouds 0'"),
    "haze_light": ("light haze, visibility 8 km", SHORT + " --link-args '-p haze_visibility_m:=8000'"),
    "haze_medium": ("medium haze, visibility 4 km", SHORT + " --link-args '-p haze_visibility_m:=4000'"),
    "haze_thick": ("thick haze, visibility 2 km", SHORT + " --link-args '-p haze_visibility_m:=2000'"),
    "fog": ("fog patches", SHORT + " --link-args '-p fog:=0.5'"),
    "dust": ("dust / sand storm: brown haze 2.5 km",
             SHORT + " --link-args '-p haze_visibility_m:=2500 -p haze_rgb:=0.8/0.62/0.4'"),
    "rain": ("rain: streaks + drops on the window", SHORT + " --link-args '-p rain:=0.7'"),
    "lowcloud_part": ("low clouds below the vehicle, 30 %", SHORT + " --isaac-args '--low-clouds 0.3'"),
    "lowcloud_most": ("low clouds below the vehicle, 70 %", SHORT + " --isaac-args '--low-clouds 0.7'"),
    "cloudshadow": ("heavy moving cloud shadows (60 %)", SHORT + " --isaac-args '--clouds 0.6'"),
    "glare": ("sun glare in the lens", SHORT + " --link-args '-p glare:=0.6'"),
    "world2017": ("world = Wayback 2017 imagery (map ~2025)", SHORT + " --scene kalaa2017"),
    "season": ("season change: greener fields than the map", SHORT + " --link-args '-p season:=0.8'"),
    "newbuild": ("120 new buildings not in the map", SHORT + " --isaac-args '--extra-buildings 120'"),
    "obst_birds_air": ("bird flocks + another aircraft below", SHORT + " --isaac-args '--obstacles birds,aircraft'"),
    "obst_ground": ("power lines + moving cars/trucks", SHORT + " --isaac-args '--obstacles powerlines,cars'"),
    "obst_smoke": ("smoke plume", SHORT + " --isaac-args '--obstacles smoke'"),
    "obst_all": ("birds + aircraft below + power lines + cars/trucks + smoke",
                 SHORT + " --isaac-args '--obstacles birds,aircraft,powerlines,cars,smoke'"),
    "terrain_coast": ("coast with sea (Sousse)", SHORT + " --scene coast"),
    "terrain_hills": ("hills / relief", SHORT + " --scene hills"),
    "terrain_farms": ("farmland", SHORT + " --scene farms"),
    "h150": ("height 150 m", SHORT + " --alt 150"),
    "h600": ("height 600 m", SHORT + " --alt 600"),
    "h1200": ("height 1200 m", SHORT + " --alt 1200"),
    "wind": ("strong wind 12 m/s + gusts (turbulence 4)", SHORT + " --wind 12 --turb 4"),
    "shake": ("vibration: camera jitter 0.7 deg + IMU noise", SHORT
              + " --isaac-args '--shake 0.7' --link-args '-p imu_vibration_g:=0.02'"),
    "mount4": ("camera mount error 4 deg (unknown to NAVERA)", SHORT + " --isaac-args '--mount-err 3.0,-2.5,4.0'"),
    "imubias": ("IMU gyro bias 0.27 deg/s on every axis", SHORT + " --link-args '-p gyro_bias_dps:=0.27/0.27/0.27'"),
    "outage30": ("30 s vision outage (cloud bank) 40 s after the cut", SHORT + " --link-args '-p outages:=40/30'"),
    "outage60": ("60 s vision outage 40 s after the cut", SHORT + " --link-args '-p outages:=40/60'"),
    "spoof": ("slow GPS spoof 3 m/s for 30 s before the cut", SHORT + " --link-args '-p spoof_mps:=3.0'"),
    "plane15": ("plane 15 m/s, 400 m, body-fixed camera", PLANE + " --speed 15 --model plane"),
    "plane30": ("plane 30 m/s, 400 m, body-fixed camera", PLANE + " --speed 30 --model plane"),
    # radius 900: with 1500 the jet's turns (r ~ 450 m at 40 deg bank) left the 4 km scene (2026-10-21)
    "plane60": ("plane 60 m/s (jet model), 500 m", PLANE.replace("--alt 400", "--alt 500")
                + " --speed 60 --model plane-jet --radius 900"),
    "worst_copter": ("dusk + dust 3 km + rain + wind 10 + outage 30 (full mission)",
                     FULL + " --time 17:15 --wind 10 --turb 3 --link-args '-p haze_visibility_m:=3000 "
                     "-p haze_rgb:=0.8/0.62/0.4 -p rain:=0.5 -p outages:=60/30'"),
    "worst_plane": ("plane 30 m/s + world 2017 + cloud shadows + glare + mount 3 deg",
                    PLANE + " --speed 30 --model plane --scene kalaa2017 --isaac-args '--clouds 0.5 --mount-err 2,-2,3' "
                    "--link-args '-p glare:=0.4'"),
}


def sh(cmd, ssh):
    full = ["ssh", "-o", "BatchMode=yes", ssh, cmd] if ssh else ["bash", "-c", cmd]
    return subprocess.run(full, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ssh", default="", help="user@host of the PC (empty: run here)")
    ap.add_argument("--only", default="", help="comma list of conditions (default all, in order)")
    ap.add_argument("--prefix", default="c_")
    ap.add_argument("--notice", default="")
    ap.add_argument("--copy-to", default="")
    ap.add_argument("--out", default=os.path.expanduser("~/.navera_sim/isaac/campaign"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--repo", default="~/Navera", help="the NAVERA checkout on the PC whose code runs")
    ap.add_argument("--ws", default="", help="its colcon build directory on the PC (default ~/.navera_isaac_ws)")
    ap.add_argument("--extra", default="", help="launcher arguments appended to every condition's")
    a = ap.parse_args()
    if a.list:
        for k, (what, args) in CONDITIONS.items():
            print(f"{k:16s} {what}\n{'':16s} {args}")
        return
    names = [n for n in (a.only.split(",") if a.only else CONDITIONS) if n]
    os.makedirs(a.out, exist_ok=True)
    for n in names:
        what, args = CONDITIONS[n]
        run = a.prefix + n
        if a.notice:
            with open(a.notice, "a") as f:
                f.write(f"{time.strftime('%F %T')} NOTICE: campaign run '{run}' ({what}) starts now: MAVProxy map+console, "
                        f"'NAVERA - live error' and ~1.5 min later 'NAVERA - Isaac Sim flight' open, ~9 min.\n")
        t0 = time.time()
        args = f"{args} {a.extra}".strip()
        cmd = (f"rm -rf ~/navera_results/{run}; {'NAVERA_ISAAC_WS=' + a.ws + ' ' if a.ws else ''}bash {a.repo}/navera_tools/isaac/run_closed_loop.sh --name {run} "
               f"--hold 5 {args} > ~/navera_{run}.out 2>&1")
        r = sh(cmd, a.ssh)
        rec = dict(run=run, condition=n, what=what, args=args, minutes=round((time.time() - t0) / 60, 1), rc=r.returncode)
        dst = os.path.join(a.copy_to or a.out, run)
        if a.ssh:
            subprocess.run(["rsync", "-a", "-e", "ssh -o BatchMode=yes", "--exclude", "state", "--exclude", "plot",
                            "--exclude", "sitl/terrain", f"{a.ssh}:navera_results/{run}/", dst + "/"])
        try:
            cut = float(open(os.path.join(dst, "gps_cut")).read())
            rec["summary"] = summarise(dst, cut)
            json.dump(rec["summary"], open(os.path.join(dst, "summary_flight.json"), "w"), indent=1)
        except (OSError, ValueError) as e:
            rec["error"] = f"no summary: {e}"
        with open(os.path.join(a.out, "campaign.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps({k: rec.get(k) for k in ("run", "minutes", "rc", "error")}), flush=True)
    table(a.out)


def table(out):
    """campaign.md from campaign.jsonl (the last record per run)."""
    recs = {}
    for line in open(os.path.join(out, "campaign.jsonl")):
        r = json.loads(line)
        recs[r["run"]] = r
    rows = ["| run | condition | matched % | NAVERA fix err (stated time) med/p90/max | at exposure med/p90/max | "
            "output err med/p90/max | > 3 sigma | wrong | autopilot EKF med/p90/max | mission | truth from home at RTL arrival | "
            "delay est. |", "|" + "---|" * 12]
    f3 = lambda d: "/".join("-" if d.get(k) is None else f"{d[k]:.0f}" for k in ("median", "p90", "max")) if d else "-"  # noqa: E731
    for r in recs.values():
        s = r.get("summary")
        if not s:
            rows.append(f"| {r['run']} | {r['what']} | FAILED: {r.get('error', r.get('rc'))} |" + " |" * 10)
            continue
        a, m, lat = s["after_cut"], s.get("mission") or {}, s.get("latency_last") or {}
        rows.append(f"| {r['run']} | {r['what']} | {a['accepted_pct']} | {f3(a['fix_err_stamp_m'])} | "
                    f"{f3(a['fix_err_exposure_m'])} | {f3(a['output_err_m'])} | "
                    f"{s['output_beyond_3sigma']['n']}/{s['output_beyond_3sigma']['of']} | {a['wrong_fixes']} | "
                    f"{f3(s.get('autopilot_ekf_err_after_cut_m'))} | "
                    f"{'completed' if m.get('completed') else 'NOT completed'}"
                    f"{' (' + ', '.join(m.get('failsafe') or []) + ')' if m.get('failsafe') else ''} | "
                    f"{m.get('dist_from_home_at_rtl_arrival_m')} m | {lat.get('applied_s') or lat.get('estimate_s') or '-'} |")
    open(os.path.join(out, "campaign.md"), "w").write("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
