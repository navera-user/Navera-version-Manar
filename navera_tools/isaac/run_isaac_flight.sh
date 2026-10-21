#!/bin/bash
# NAVERA - Isaac Sim flight, end to end, on the PC (WSL2 + Windows Isaac Sim 6.0). SIMULATION.
#
#   navera_tools/isaac/run_isaac_flight.sh [--name NAME] [--traj plane|copter|none] [--time 08:30]
#       [--date 2026-10-21] [--duration 420] [--spoof 0] [--gps-cut 60] [--delay 1.3]
#       [--clouds 0.25] [--haze 12000] [--max-speed 45] [--matcher auto|local] [--mount-err r,p,y]
#
# 1. NAVERA's real nodes + the Isaac link in the navera-humble container (run_navera_nodes.sh),
#    waiting until day_subscriber has loaded its map (first time: builds the DINOv2 cache)
# 2. the live plot window "NAVERA - live error" (WSLg)
# 3. Isaac Sim (Windows) flies the recorded autopilot flight: window "NAVERA - Isaac Sim flight"
# 4. at the end: summary.json, videos (chase.mp4, navera_view.mp4, flight.mp4) in ~/navera_results/NAME
#
# Data (prepared once, see navera_tools/isaac/README.md): D:\navera_isaac\{scenes\kalaa,traj},
# ~/navera_data/isaac_kalaa_area (NAVERA's map), ~/navera_data/lens, ~/navera_data/torch_home.
set -u
name=flight_$(date +%Y%m%d_%H%M%S); traj=plane; tod=08:30; date_=2026-10-21; dur=420; spoof=0; cut=60
delay=1.3; clouds=0.25; haze=12000; maxs=45; mount=1.5,-1.0,2.0; matcher=auto
while [ $# -gt 0 ]; do
  case $1 in
    --name) name=$2;; --traj) traj=$2;; --time) tod=$2;; --date) date_=$2;; --duration) dur=$2;;
    --spoof) spoof=$2;; --gps-cut) cut=$2;; --delay) delay=$2;; --clouds) clouds=$2;; --haze) haze=$2;;
    --max-speed) maxs=$2;; --mount-err) mount=$2;; --matcher) matcher=$2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac; shift 2
done
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../.." && pwd)
D=/mnt/d/navera_isaac; DW='D:\navera_isaac'
res=$HOME/navera_results/$name; mkdir -p "$res" "$HOME/.navera_isaac_ws"/{build,install,log}
cp "$here"/isaac_flight.py "$here"/flight_profile.py "$D"/
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$res/run.log"; }

traj_arg=(); ground=nan
if [ "$traj" != none ]; then
  traj_arg=(--traj "$DW\\traj\\$traj.csv")
  ground=$(head -1 "$D/traj/$traj.csv" | sed -n 's/.*home=[^,]*,[^,]*,\([0-9.]*\).*/\1/p')
fi
link="-p gps_cut_s:=$cut -p spoof_mps:=$spoof -p delay_s:=$delay -p haze_visibility_m:=$haze"
log "run $name: traj $traj, $date_ $tod, GPS cut $cut s, spoof $spoof m/s, delay $delay s"

docker rm -f navera_isaac >/dev/null 2>&1
rm -rf "$D/runs/$name"                     # before the link starts: it must not read an old session
docker run -d --rm --name navera_isaac --gpus all --network host --user "$(id -u):$(id -g)" -e HOME=/results \
  -e RUN="$name" -e MATCHER="$matcher" -e MAX_SPEED="$maxs" -e GROUND_ALT="$ground" -e LINK_ARGS="$link" \
  -v "$repo":/ws/src/navera -v "$HOME/.navera_isaac_ws/build":/ws/build \
  -v "$HOME/.navera_isaac_ws/install":/ws/install -v "$HOME/.navera_isaac_ws/log":/ws/log \
  -v "$D":/isaac -v "$HOME/navera_data/isaac_kalaa_area":/data/area -v "$HOME/navera_data/lens":/data/lens \
  -v "$HOME/navera_data/torch_home":/torch_home -v "$res":/results \
  navera-humble bash /ws/src/navera/navera_tools/isaac/run_navera_nodes.sh > /dev/null || exit 1
log "NAVERA nodes starting in the container (map + models loading)…"
for i in $(seq 1 900); do
  [ -f "$res/navera_ready" ] && break
  docker ps -q -f name=navera_isaac | grep -q . || { log "container stopped: see $res/logs, $res/colcon.log"; exit 1; }
  sleep 1
done
[ -f "$res/navera_ready" ] || { log "NAVERA not ready after 15 min"; exit 1; }
log "NAVERA ready"

export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
nohup python3 "$here/live_plot.py" "$res" --gps-cut "$cut" > "$res/plot.log" 2>&1 &
log "window 'NAVERA - live error' open; starting Isaac Sim (window 'NAVERA - Isaac Sim flight')"
( while docker ps -q -f name=navera_isaac | grep -q .; do
    echo "$(date +%T) $(/mnt/c/Windows/System32/nvidia-smi.exe --query-gpu=memory.used,utilization.gpu --format=csv,noheader)"
    sleep 10; done > "$res/gpu.log" 2>&1 ) &
/mnt/c/Windows/System32/cmd.exe /c "cd /d $DW && D:\\isaac\\isaacsim-6.0\\python.bat isaac_flight.py \
  --out $DW\\runs\\$name --scene $DW\\scenes\\kalaa ${traj_arg[*]} --date $date_ --time $tod \
  --duration $dur --clouds $clouds --mount-err $mount" > "$res/isaac.log" 2>&1
log "Isaac Sim finished: $(cat "$D/runs/$name/done.json" 2>/dev/null | tr -d '\n ')"
for i in $(seq 1 90); do [ -f "$res/finished" ] && break; sleep 1; done
sleep 3
docker stop navera_isaac > /dev/null 2>&1
cp "$D/runs/$name/session.json" "$D/runs/$name/frames.jsonl" "$res/" 2>/dev/null

ff="ffmpeg -loglevel error -y"
$ff -framerate 10 -i "$D/runs/$name/video/v_%06d.jpg" -c:v libx264 -pix_fmt yuv420p -crf 23 "$res/chase.mp4"
$ff -framerate 1 -i "$res/navera_view/n_%05d.jpg" -c:v libx264 -pix_fmt yuv420p -crf 23 "$res/navera_view.mp4"
$ff -framerate 10 -i "$D/runs/$name/video/v_%06d.jpg" -framerate 1 -i "$res/navera_view/n_%05d.jpg" \
  -framerate 0.5 -i "$res/plot/p_%05d.png" -filter_complex \
  "[0]scale=960:540,fps=10[a];[1]scale=960:540,fps=10[b];[a][b]hstack[t];[2]scale=1920:-2,fps=10[c];[t][c]vstack,format=yuv420p" \
  -shortest -c:v libx264 -crf 24 "$res/flight.mp4"
log "videos: $res/{flight,chase,navera_view}.mp4"
python3 "$here/summarise.py" "$res" --gps-cut "$cut" | tee -a "$res/run.log"
