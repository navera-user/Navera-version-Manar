#!/bin/bash
# NAVERA closed-loop demo on the PC (SIMULATION): ArduPilot SITL flies an AUTO mission over the
# Isaac Sim scene; after the GPS cut the autopilot flies ONLY on NAVERA's vision positions.
#
#   ~/Navera/navera_tools/isaac/run_closed_loop.sh [--name NAME] [--alt 250] [--radius 500]
#       [--speed 8] [--cut-after 15] [--time 10:30] [--sigma 30] [--gate FILE] [--hold 600]
#
#   --gate FILE  everything is prepared (NAVERA loaded, SITL configured), then NO window opens
#                until FILE exists (e.g. the user has started a screen recording)
#   --hold S     at the end every window stays open S seconds, or until $res/stop_windows exists
#   --vehicle copter|plane --model quad|plane|plane-jet --scene kalaa|<prepared scene> --legs N
#   --wind M/S --wind-dir DEG --turb M/S --gimbal true|false (default: copter true, plane false)
#   --endurance S  fly the diamond again and again for S s after the GPS cut, then RTL (hours:
#                  infinite SITL battery, no battery failsafe; resources.csv every 30 s)
#   --isaac-args "..." (isaac_flight.py conditions) --link-args "-p k:=v ..." (isaac_link.py conditions)
#   --day-args / --cam-args "-p k:=v ..." (day_subscriber / live_camera parameters), e.g. the bench
#                  camera delay: --cam-args "-p capture_latency_s:=1.3" (NAVERA_CAMERA_LATENCY_S)
#   --set K=V,...  extra / overriding ArduPilot parameters (after NAVERA's recommended ones)
#   NAVERA_ISAAC_WS (env): the colcon build directory (default ~/.navera_isaac_ws; one per checkout)
#   --vlink URL|off  vehicle_link on the autopilot's SERIAL2 (default tcp:127.0.0.1:5763): its velocity for
#                  the day node's carry (open3); off = without it (the day node carries as before)
#   --area NAME  NAVERA's map ~/navera_data/isaac_NAME_area (default: the scene's, isaac_<scene>_area)
#
#   windows: "NAVERA - Isaac Sim flight" (the scene, chase view), MAVProxy map + console,
#            "NAVERA - live error" (truth / NAVERA / autopilot EKF, map, camera, status)
#   chain:   SITL truth -> sitl_demo.py -> Isaac Sim (pose) + isaac_link (IMU, baro, GPS, truth)
#            Isaac frames -> isaac_link (real camera) -> live_camera -> day_subscriber -> estimator
#            -> vehicle_output_node -> GPS_INPUT -> SITL (GPS_TYPE 14, SIM_GPS_DISABLE 1)
#   results: ~/navera_results/NAME (summary.json, ekf.csv, position.csv, flight.mp4, sitl/, logs/)
set -u
name=closed_loop_$(date +%Y%m%d_%H%M%S); alt=250; radius=500; speed=8; cut_after=15; tod=10:30; sigma=30
gate=""; hold=30; vehicle=copter; model=quad; scene=kalaa; legs=4; wind=4; wind_dir=290; turb=1.0
isaac_extra=""; link_extra=""; gimbal=""; day_extra=""; cam_extra=""; endurance=0; area=""; ap_set=""
vlink=tcp:127.0.0.1:5763
while [ $# -gt 0 ]; do
  case $1 in
    --name) name=$2;; --alt) alt=$2;; --radius) radius=$2;; --speed) speed=$2;; --cut-after) cut_after=$2;;
    --time) tod=$2;; --sigma) sigma=$2;; --gate) gate=$2;; --hold) hold=$2;;
    --vehicle) vehicle=$2;; --model) model=$2;; --scene) scene=$2;; --legs) legs=$2;; --wind) wind=$2;;
    --wind-dir) wind_dir=$2;; --turb) turb=$2;; --isaac-args) isaac_extra=$2;; --link-args) link_extra=$2;;
    --gimbal) gimbal=$2;; --day-args) day_extra=$2;; --cam-args) cam_extra=$2;; --endurance) endurance=$2;;
    --area) area=$2;;
    --set) ap_set=$2;;
    --vlink) vlink=$2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac; shift 2
done
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../.." && pwd)
D=/mnt/d/navera_isaac; DW='D:\navera_isaac'
ws=${NAVERA_ISAAC_WS:-$HOME/.navera_isaac_ws}
res=$HOME/navera_results/$name; mkdir -p "$res/sitl" "$ws"/{build,install,log}
VENV=$HOME/.venv-navera-sitl; AP=$HOME/ardupilot
cp "$here"/isaac_flight.py "$here"/flight_profile.py "$D"/
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$res/run.log"; }
export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
pids=()
cleanup() {
  kill "${pids[@]}" 2>/dev/null
  pkill -f "build/sitl/bin/ardu[a-z]* --model" 2>/dev/null; pkill -f "mavproxy.py --master tcp:127.0.0.1:5760" 2>/dev/null
  docker stop navera_isaac > /dev/null 2>&1
}
trap cleanup EXIT

[ -z "$gimbal" ] && { [ "$vehicle" = copter ] && gimbal=true || gimbal=false; }
gflag=""; [ "$gimbal" = true ] && gflag="--gimbal"
read -r lat0 lon0 zref < <(python3 -c "import json; s=json.load(open('$D/scenes/$scene/scene.json')); print(s['lat0'], s['lon0'], round(s['z_ref_m'], 1))")
log "closed loop $name: $vehicle ($model, gimbal $gimbal), scene $scene, $alt m, ${speed} m/s, wind $wind@$wind_dir turb $turb, GPS cut ${cut_after} s after reaching altitude; home $lat0,$lon0,$zref; isaac [$isaac_extra] link [$link_extra]"

# 0. nothing of an earlier demo may survive (SITL ports 5760-5763, the truth stream ports)
pkill -f "build/sitl/bin/ardu[a-z]* --model" 2>/dev/null; pkill -f "mavproxy.py --master tcp:127.0.0.1:5760" 2>/dev/null
pkill -f "isaac/sitl_demo.py" 2>/dev/null; sleep 1

# 1. NAVERA (container): its real nodes + vehicle_output to SITL's SERIAL1
docker rm -f navera_isaac >/dev/null 2>&1
rm -rf "$D/runs/$name"
docker run -d --rm --name navera_isaac --gpus all --network host --user "$(id -u):$(id -g)" -e HOME=/results \
  -e RUN="$name" -e MATCHER=auto -e MAX_SPEED=$([ "$vehicle" = plane ] && echo 75 || echo 30) -e GROUND_ALT="$zref" -e VEHICLE_OUT=tcp:127.0.0.1:5762 \
  -e VEHICLE_LINK="$([ "$vlink" = off ] || echo "$vlink")" \
  -e DEGRADED_SIGMA="$sigma" -e GIMBAL=$gimbal -e DAY_ARGS="$day_extra" -e CAM_ARGS="$cam_extra" \
  -e LINK_ARGS="-p truth_udp_port:=15501 -p delay_s:=1.3 -p scene_dir:=/isaac/scenes/$scene $link_extra" \
  -v "$repo":/ws/src/navera -v "$ws/build":/ws/build \
  -v "$ws/install":/ws/install -v "$ws/log":/ws/log \
  -v "$D":/isaac -v "$HOME/navera_data/isaac_${area:-$scene}_area":/data/area -v "$HOME/navera_data/lens":/data/lens \
  -v "$HOME/navera_data/torch_home":/torch_home -v "$res":/results \
  navera-humble bash /ws/src/navera/navera_tools/isaac/run_navera_nodes.sh > /dev/null || exit 1
for i in $(seq 1 900); do
  [ -f "$res/navera_ready" ] && break
  docker ps -q -f name=navera_isaac | grep -q . || { log "container stopped: see $res/logs"; exit 1; }
  sleep 1
done
log "NAVERA ready (day pipeline loaded)"

# 2. ArduPilot SITL (copter) with NAVERA's recommended parameters: its only GPS is NAVERA
{
cat <<PARM
GPS_TYPE 14
GPS_AUTO_CONFIG 0
SERIAL1_PROTOCOL 2
EK3_SRC1_POSXY 3
EK3_SRC1_VELXY 0
EK3_SRC1_VELZ 0
EK3_SRC1_POSZ 1
EK3_OGN_HGT_MASK 0
SIM_GPS_DISABLE 1
ARMING_CHECK 2096126
SIM_WIND_SPD $wind
SIM_WIND_DIR $wind_dir
SIM_WIND_TURB $turb
PARM
if [ "$endurance" != 0 ]; then cat <<PARM
SIM_BATT_CAP_AH 0
BATT_FS_LOW_ACT 0
BATT_FS_CRT_ACT 0
BATT_LOW_MAH 0
BATT_CRT_MAH 0
PARM
fi
if [ "$vehicle" = copter ]; then cat <<PARM
WPNAV_SPEED $((speed * 100))
WPNAV_SPEED_UP 500
WPNAV_SPEED_DN 300
LAND_SPEED_HIGH 300
ANGLE_MAX 3500
AUTO_OPTIONS 3
RTL_ALT $((alt * 100))
RTL_ALT_FINAL $((alt * 100))
EK3_GLITCH_RAD 100
PARM
else cat <<PARM
AIRSPEED_CRUISE $speed
AIRSPEED_MIN $((speed > 20 ? speed - 8 : 12))
AIRSPEED_MAX $((speed + 15))
TKOFF_ALT 60
RTL_RADIUS 350
WP_LOITER_RAD 350
WP_RADIUS 120
RTL_ALTITUDE $alt
RTL_AUTOLAND 0
ROLL_LIMIT_DEG 40
PARM
fi
echo "$ap_set" | tr ',' '\n' | sed -n 's/^ *\([A-Z0-9_]*\) *= *\(.*\)$/\1 \2/p'
} > "$res/sitl/navera.parm"
case $model in
  quad) bin=arducopter; defs="$AP/Tools/autotest/default_params/copter.parm";;
  plane) bin=arduplane; defs="$AP/Tools/autotest/models/plane.parm";;
  plane-jet) bin=arduplane; defs="$AP/Tools/autotest/models/plane.parm,$AP/Tools/autotest/default_params/plane-jet.parm";;
esac
(cd "$res/sitl" && exec "$AP/build/sitl/bin/$bin" --model "$model" --home "$lat0,$lon0,$zref,0" \
   --defaults "$defs,$res/sitl/navera.parm" -I0 > sitl.log 2>&1) &
pids+=($!)
log "SITL started (headless)"
if [ -n "$gate" ]; then
  touch "$res/prepared"
  log "PREPARED: waiting for $gate before opening any window"
  until [ -f "$gate" ]; do sleep 2; done
  log "GO"
fi
sleep 1
"$VENV/bin/mavproxy.py" --master tcp:127.0.0.1:5760 --out udp:127.0.0.1:14550 --map --console \
  --non-interactive --state-basedir "$res/sitl" > "$res/sitl/mavproxy.log" 2>&1 &
pids+=($!)
log "MAVProxy (map, console) started"

# 3. the mission + truth stream (arms once Isaac Sim renders)
"$VENV/bin/python" "$here/sitl_demo.py" --master udpin:127.0.0.1:14550 --results "$res" --lat0 "$lat0" --lon0 "$lon0" \
  --alt "$alt" --radius "$radius" --speed "$speed" --cut-after "$cut_after" --vehicle "$vehicle" --legs "$legs" \
  --arm-after-file "$D/runs/$name/session.json" --endurance "$endurance" \
  --timeout $(python3 -c "print(1200 + 1.0 * $endurance)") > "$res/sitl/demo.log" 2>&1 &
demo=$!
pids+=($demo)

# 4. live plot + Isaac Sim (pose from SITL)
python3 "$here/live_plot.py" "$res" --gps-cut 99999 --scene "$D/scenes/$scene" > "$res/plot.log" 2>&1 &
pids+=($!)
( while docker ps -q -f name=navera_isaac | grep -q .; do
    echo "$(date +%T) $(/mnt/c/Windows/System32/nvidia-smi.exe --query-gpu=memory.used,utilization.gpu --format=csv,noheader)"
    sleep 10; done > "$res/gpu.log" 2>&1 ) &
"$here/resource_monitor.sh" "$res" "$D/runs/$name" > /dev/null 2>&1 &
pids+=($!)
log "starting Isaac Sim (window 'NAVERA - Isaac Sim flight')"
rm -f "$D/runs/stop_$name"
/mnt/c/Windows/System32/cmd.exe /c "cd /d $DW && D:\\isaac\\isaacsim-6.0\\python.bat isaac_flight.py \
  --out $DW\\runs\\$name --scene $DW\\scenes\\$scene --pose-udp 15500 --time $tod --duration $(python3 -c "print(int(1500 + 1.0 * $endurance))") \
  --fps 10 --clouds 0.2 $gflag --wind $wind@$wind_dir $isaac_extra --linger $((hold + 120)) --stop-file $DW\\runs\\stop_$name" > "$res/isaac.log" 2>&1 &
isaac=$!
wait $demo 2>/dev/null
log "mission over (sitl_demo finished)"
for i in $(seq 1 60); do [ -f "$res/finished" ] && break; sleep 1; done
log "holding the windows open ${hold} s (or until $res/stop_windows)"
for i in $(seq 1 "$hold"); do [ -f "$res/stop_windows" ] && break; sleep 1; done
touch "$D/runs/stop_$name"
wait $isaac 2>/dev/null
log "Isaac Sim closed: $(cat "$D/runs/$name/done.json" 2>/dev/null | tr -d '\n ')"
cp "$D/runs/$name/session.json" "$D/runs/$name/frames.jsonl" "$res/" 2>/dev/null

ff="ffmpeg -loglevel error -y"
$ff -framerate 10 -i "$D/runs/$name/video/v_%06d.jpg" -framerate 1 -i "$res/navera_view/n_%05d.jpg" \
  -framerate 0.5 -i "$res/plot/p_%05d.png" -filter_complex \
  "[0]scale=960:540,fps=10[a];[1]scale=960:540,fps=10[b];[a][b]hstack[t];[2]scale=1920:-2,fps=10[c];[t][c]vstack,format=yuv420p" \
  -shortest -c:v libx264 -preset ultrafast -crf 26 "$res/flight.mp4"
log "videos: $res/flight.mp4"
[ -s "$res/flight.mp4" ] && rm -rf "$D/runs/$name/frames" "$D/runs/$name/video"   # ~2 GB of JPEG per run
cut=$(cat "$res/gps_cut" 2>/dev/null || echo 99999)
python3 "$here/summarise.py" "$res" --gps-cut "$cut" | tee -a "$res/run.log"
