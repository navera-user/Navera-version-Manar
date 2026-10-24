# Isaac Sim tests — how to run them yourself (SIMULATION)

Everything here is simulation: a 3-D world (Isaac Sim, on the RTX PC), the real ArduPilot
autopilot program (SITL), and NAVERA's real code. Results are never flight data.

## What is where

| What | Where |
|---|---|
| All results so far (126 runs) | Jetson `~/.navera_sim/isaac/` — one folder per campaign, one sub-folder per run |
| Index of every run with its numbers | Jetson `~/.navera_sim/isaac/ISAAC_RUNS_INDEX.md` (rebuild: `python3 navera_tools/isaac/index_runs.py`) |
| Backup of all results | ADATA disk `NAVERA_TESTDATA/isaac_sim_results/` |
| Results of a run started on the PC | PC (WSL) `~/navera_results/<name>/` |
| NAVERA code used by the PC | PC (WSL) `~/Navera` (release 0.5.1; the old copy is `~/Navera_old_20261024`) |
| The 3-D scenes and map | PC `D:\navera_isaac` (WSL `/mnt/d/navera_isaac`) and WSL `~/navera_data/` |

Inside each run folder: `flight.mp4` (video: 3-D view + what NAVERA's camera sees + live error
plot), `plot_final.png` (error over time, track on the map), `summary.json` (all numbers; campaign runs also
`summary_flight.json`),
`position.csv` (every NAVERA position vs the truth), `ekf.csv` (the autopilot's own position),
`sitl/` (autopilot logs), `logs/` (every NAVERA program), `ENDURANCE.md` (long flights).

## Before you start (once)

1. Turn on the PC, log in to Windows, open **Ubuntu (WSL)** from the Start menu.
2. Check the GPU is visible: `nvidia-smi.exe` (in WSL) must show the RTX card.
3. Check nothing else is running: `docker ps` must show no `navera` container. If one is left
   over: `docker stop <its name>`.
4. Close other heavy programs (games, browsers with many tabs): Isaac Sim needs the GPU.

## Run one test — the standard closed-loop flight (~14 min)

The copter takes off with GPS, flies a 4-leg square at 250 m, GPS is cut (as if jammed), the
autopilot then flies ONLY on NAVERA's camera positions, and comes home.

In the WSL window on the PC:

```bash
~/Navera/navera_tools/isaac/run_closed_loop.sh --name my_first_test --sigma 15
```

What you will see (4 windows open by themselves after 1–3 minutes of start-up):
- **"NAVERA - Isaac Sim flight"** — the 3-D world, seen from behind the drone.
- **MAVProxy map + console** — the autopilot's map, its mode (AUTO, then RTL) and messages.
- **"NAVERA - live error"** — truth vs NAVERA vs the autopilot, the error curve, the camera image,
  NAVERA's status. The red dashed line "GPS cut" marks the jamming.

Wait until the console says the mission is over (RTL, landed or holding over home). The windows
stay open 30 s at the end (`--hold 600` keeps them 10 minutes).

Results: `~/navera_results/my_first_test/` — open `plot_final.png` and `flight.mp4`, and read
`summary.json` (`after_cut.fix_err_stamp_m` = NAVERA's error; `wrong_fixes`;
`mission.completed`).

## Change the conditions

Add options to the same command. Common ones:

| You want | Add |
|---|---|
| Other time of day | `--time 07:00` (dawn), `--time 12:30` (noon) |
| GPS lost right after take-off | `--cut-after 12` |
| Higher / faster | `--alt 600`, `--speed 15` |
| Plane instead of copter | `--vehicle plane --model plane` |
| Wind | `--wind 8 --wind-dir 290 --turb 2` |
| Camera delay measured on the bench (recommended) | `--cam-args "-p capture_latency_s:=1.3"` |
| Weather / obstacles (rain, dust, fog, clouds, birds…) | `--isaac-args "..."`, see the conditions in `navera_tools/isaac/campaign.py` (`CONDITIONS`) |
| Wide 12 x 12 km scene (fast planes) | `--scene kalaa_wide` (map `isaac_kalaa_wide_area` follows; or `--area kalaa_wide`) |
| A 60 m/s jet on a 2.5 km circle | campaign condition `plane60_wide` (`--loiter-turns 1` + jet cruise `--set` limits) |
| A long flight without GPS (e.g. 2 h) | `--endurance 7200 --cut-after 12 --isaac-args "--sun-ramp 1"` |

Example — a 2-hour GPS-denied flight like the one that completed on 2026-10-23 (~2.5 h):

```bash
~/Navera/navera_tools/isaac/run_closed_loop.sh --name endurance_2h --endurance 7200 --cut-after 12 \
    --sigma 15 --time 10:00 --isaac-args "--sun-ramp 1" --cam-args "-p capture_latency_s:=1.3"
```
Then summarise it: `python3 ~/Navera/navera_tools/isaac/endurance_report.py ~/navera_results/endurance_2h`.

## Run a whole set of conditions from the Jetson (campaign)

On the Jetson, in `~/Navera` (needs the PC on, reachable as `dev@100.115.52.19`):

```bash
python3 navera_tools/isaac/campaign.py --list                                  # all conditions
python3 navera_tools/isaac/campaign.py --ssh dev@100.115.52.19 --repo '~/Navera' \
    --only base,rain,fog --prefix my_ --out ~/.navera_sim/isaac/my_campaign
```
It runs the flights one after the other (~15 min each) and writes `campaign.md` (one row per
flight) in the `--out` folder. One flight at a time: never start two on the PC.

## Run the real Jetson box in the loop (advanced)

NAVERA runs on the Jetson exactly as installed; Isaac Sim feeds it over the network.
See `navera_tools/isaac/README.md`, section "Hardware in the loop", e.g.
`navera_tools/isaac/hil_flight.sh --name hil_test --kill navera-estimator@180` (from the Jetson).

## After a run

- Rebuild the index: `python3 navera_tools/isaac/index_runs.py` (Jetson).
- Copy PC results to the Jetson: `rsync -a dev@100.115.52.19:navera_results/<name> ~/.navera_sim/isaac/results/`.
- Back up: `rsync -a ~/.navera_sim/isaac/ "/media/shadow-team/ADATA SD620/NAVERA_TESTDATA/isaac_sim_results/"`.
- Videos are large (~1–3 GB per hour): delete old `flight.mp4` files you no longer need.

## If something goes wrong

| Symptom | Fix |
|---|---|
| No window after 5 minutes | `docker ps`: a leftover container? Stop it and start again. Check `~/navera_results/<name>/run.log`. |
| "GPU not found" | `nvidia-smi.exe` in WSL; restart WSL (`wsl --shutdown` in Windows PowerShell) |
| The drone lands soon after the GPS cut | Check `EK3_GLITCH_RAD 100` is in `sitl/` params (the script sets it for Copter) and read `summary.json` → `mission.failsafe` |
| A run was spoiled by another one | Only one flight at a time on the PC |
