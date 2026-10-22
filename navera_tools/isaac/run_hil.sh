#!/bin/bash
# NAVERA hardware in the loop, PC side (SIMULATION feeding the REAL box): Isaac Sim + ArduPilot SITL
# here, NAVERA on the Jetson as deployed (staged systemd units, its navera.env), over the network.
# Started by the box (navera_tools/isaac/hil_flight.sh) through ssh; not run by hand.
#
#   run_hil.sh --name NAME --box BOX_IP [--alt 250] [--radius 400] [--speed 10] [--legs 3]
#       [--cut-after 75] [--time 10:30] [--hold 5] [--instance 5] [--rtsp-port 8564]
#       [--nmea-port 10117] [--truth-port 15531] [--duration 1500] [--link-args "-p k:=v"]
#
# What the box gets (the same signals a real installation gives it):
#   camera  the vehicle camera as an RTSP / H.264 network camera: rtsp://<PC>:RTSP_PORT/navera
#           (isaac_link's real-camera model -> ffmpeg libx264 -> mediamtx), 1.3 s exposure->send
#   GPS     NMEA (GGA + RMC, 5 Hz) on tcp://<PC>:NMEA_PORT, jammed (no fix) after the cut
#   vehicle ArduPilot SITL copter SERIAL1 = tcp://<PC>:5762+10*INSTANCE: the box's vehicle link
#           reads attitude / baro there and relays NAVERA's GPS_INPUT back (GPS_TYPE 14)
#   truth   SIM_STATE + the autopilot's EKF as UDP JSON to BOX_IP:TRUTH_PORT (the box's recorder)
# Gates (files in ~/navera_results/NAME): "streaming" = the camera stream is up (the box then
# starts NAVERA); the box writes "jetson_ready" when NAVERA is up, and SITL arms only then.
# Isolation: its own SITL instance, ports, container (navera_hil), results dir; it kills only
# what it started (by PID).
set -u
name=hil_$(date +%Y%m%d_%H%M%S); box=""; alt=250; radius=400; speed=10; legs=3; cut_after=75; tod=10:30
hold=5; inst=5; rtsp_port=8564; nmea_port=10117; truth_port=15531; duration=1500; link_extra=""
wind=4; wind_dir=290; turb=1.0; scene=kalaa; ready_timeout=900
while [ $# -gt 0 ]; do
  case $1 in
    --name) name=$2;; --box) box=$2;; --alt) alt=$2;; --radius) radius=$2;; --speed) speed=$2;;
    --legs) legs=$2;; --cut-after) cut_after=$2;; --time) tod=$2;; --hold) hold=$2;; --instance) inst=$2;;
    --rtsp-port) rtsp_port=$2;; --nmea-port) nmea_port=$2;; --truth-port) truth_port=$2;;
    --duration) duration=$2;; --link-args) link_extra=$2;; --ready-timeout) ready_timeout=$2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac; shift 2
done
[ -n "$box" ] || { echo "--box BOX_IP is required" >&2; exit 2; }
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../.." && pwd)
D=/mnt/d/navera_isaac; DW='D:\navera_isaac'
res=$HOME/navera_results/$name; mkdir -p "$res/sitl" "$HOME/.navera_hil_ws"/{build,install,log}
VENV=$HOME/.venv-navera-sitl; AP=$HOME/ardupilot; TOOLS=$HOME/navera_hil_tools
p0=$((5760 + 10 * inst)); gcs_port=$((14550 + 10 * inst)); pose_port=$((15500 + 20 * inst)); link_port=$((pose_port + 1))
cp "$here"/isaac_flight.py "$here"/flight_profile.py "$D"/
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$res/run.log"; }
export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
pids=()
cleanup() {
  touch "$D/runs/stop_$name" 2>/dev/null
  kill "${pids[@]}" 2>/dev/null
  docker stop navera_hil > /dev/null 2>&1
  sleep 1; kill -9 "${pids[@]}" 2>/dev/null
}
trap cleanup EXIT
read -r lat0 lon0 zref < <(python3 -c "import json; s=json.load(open('$D/scenes/$scene/scene.json')); print(s['lat0'], s['lon0'], round(s['z_ref_m'], 1))")
log "HIL $name: box $box, copter quad gimbal, $alt m, $speed m/s, legs $legs r $radius, cut ${cut_after} s after altitude; SITL -I$inst (SERIAL1 tcp:$((p0 + 2))), RTSP :$rtsp_port, NMEA tcp:$nmea_port, truth -> $box:$truth_port"

# 0. the RTSP server (camera stream)
cat > "$res/mediamtx.yml" <<EOF
logLevel: warn
rtsp: yes
rtspAddress: :$rtsp_port
rtspTransports: [tcp, udp]
rtpAddress: :$((rtsp_port + 2))
rtcpAddress: :$((rtsp_port + 3))
rtmp: no
hls: no
webrtc: no
srt: no
api: no
metrics: no
paths:
  all_others:
EOF
"$TOOLS/mediamtx" "$res/mediamtx.yml" > "$res/mediamtx.log" 2>&1 &
pids+=($!)

# 1. the vehicle's sensors (container, HIL=1: only isaac_link — NAVERA runs on the box)
docker rm -f navera_hil >/dev/null 2>&1
rm -rf "$D/runs/$name"
docker run -d --rm --name navera_hil --network host --user "$(id -u):$(id -g)" -e HOME=/results \
  -e RUN="$name" -e HIL=1 -e ROS_DOMAIN_ID=$((60 + inst)) \
  -e LINK_ARGS="-p truth_udp_port:=$link_port -p delay_s:=1.3 -p scene_dir:=/isaac/scenes/$scene -p nmea_tcp_port:=$nmea_port -p stream_url:=rtsp://127.0.0.1:$rtsp_port/navera $link_extra" \
  -v "$repo":/ws/src/navera -v "$HOME/.navera_hil_ws/build":/ws/build \
  -v "$HOME/.navera_hil_ws/install":/ws/install -v "$HOME/.navera_hil_ws/log":/ws/log \
  -v "$D":/isaac -v "$HOME/navera_data/lens":/data/lens -v "$res":/results \
  navera-humble bash /ws/src/navera/navera_tools/isaac/run_navera_nodes.sh > /dev/null || exit 1
for i in $(seq 1 300); do
  [ -f "$res/navera_ready" ] && break
  docker ps -q -f name=navera_hil | grep -q . || { log "container stopped: see $res/logs"; exit 1; }
  sleep 1
done
log "link container up"

# 2. ArduPilot SITL (copter): its only GPS is NAVERA's GPS_INPUT, through the box's vehicle link
#    (SERIAL1 at 921600 like a companion-computer UART: at SITL's default 57600 every message,
#    attitude included, comes at ~11 Hz — measured on the box's vehicle link)
cat > "$res/sitl/navera.parm" <<PARM
GPS_TYPE 14
GPS_AUTO_CONFIG 0
SERIAL1_PROTOCOL 2
SERIAL1_BAUD 921
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
WPNAV_SPEED $((speed * 100))
WPNAV_SPEED_UP 500
WPNAV_SPEED_DN 300
LAND_SPEED_HIGH 300
ANGLE_MAX 3500
AUTO_OPTIONS 3
RTL_ALT $((alt * 100))
RTL_ALT_FINAL $((alt * 100))
PARM
(cd "$res/sitl" && exec "$AP/build/sitl/bin/arducopter" --model quad --home "$lat0,$lon0,$zref,0" \
   --defaults "$AP/Tools/autotest/default_params/copter.parm,$res/sitl/navera.parm" -I"$inst" > sitl.log 2>&1) &
pids+=($!)
sleep 1
"$VENV/bin/mavproxy.py" --master tcp:127.0.0.1:$p0 --out udp:127.0.0.1:$gcs_port --map --console \
  --non-interactive --state-basedir "$res/sitl" > "$res/sitl/mavproxy.log" 2>&1 &
pids+=($!)
log "SITL + MAVProxy started"

# 3. mission + truth stream (arms only when the box says NAVERA is up)
"$VENV/bin/python" "$here/sitl_demo.py" --master udpin:127.0.0.1:$gcs_port --results "$res" --lat0 "$lat0" --lon0 "$lon0" \
  --alt "$alt" --radius "$radius" --speed "$speed" --cut-after "$cut_after" --vehicle copter --legs "$legs" \
  --isaac-port $pose_port --link-port $link_port --extra-dest "$box:$truth_port" \
  --arm-after-file "$res/arm_ok" > "$res/sitl/demo.log" 2>&1 &
demo=$!
pids+=($demo)

# 4. live plot (truth, autopilot EKF) + Isaac Sim
python3 "$here/live_plot.py" "$res" --gps-cut 99999 --scene "$D/scenes/$scene" > "$res/plot.log" 2>&1 &
pids+=($!)
( while docker ps -q -f name=navera_hil | grep -q .; do
    echo "$(date +%T) $(/mnt/c/Windows/System32/nvidia-smi.exe --query-gpu=memory.used,utilization.gpu --format=csv,noheader)"
    sleep 10; done > "$res/gpu.log" 2>&1 ) &
log "starting Isaac Sim"
rm -f "$D/runs/stop_$name"
/mnt/c/Windows/System32/cmd.exe /c "cd /d $DW && D:\\isaac\\isaacsim-6.0\\python.bat isaac_flight.py \
  --out $DW\\runs\\$name --scene $DW\\scenes\\$scene --pose-udp $pose_port --time $tod --duration $duration \
  --fps 10 --clouds 0.2 --gimbal --wind $wind@$wind_dir --linger $((hold + 120)) --stop-file $DW\\runs\\stop_$name" > "$res/isaac.log" 2>&1 &
isaac=$!

# 5. gates: stream up -> the box starts NAVERA -> jetson_ready -> arm
for i in $(seq 1 600); do
  [ -s "$res/stream.csv" ] && [ "$(wc -l < "$res/stream.csv")" -gt 5 ] && break
  kill -0 $demo 2>/dev/null || { log "sitl_demo ended early"; exit 1; }
  sleep 1
done
touch "$res/streaming"
log "camera stream up: waiting for the box (jetson_ready)"
for i in $(seq 1 "$ready_timeout"); do [ -f "$res/jetson_ready" ] && break; sleep 1; done
[ -f "$res/jetson_ready" ] || { log "the box never said ready ($ready_timeout s)"; exit 1; }
until [ -f "$D/runs/$name/session.json" ]; do sleep 1; done
touch "$res/arm_ok"
log "box ready: arming"
wait $demo 2>/dev/null
log "mission over (sitl_demo finished)"
for i in $(seq 1 "$hold"); do [ -f "$res/stop_windows" ] && break; sleep 1; done
touch "$D/runs/stop_$name"
wait $isaac 2>/dev/null
log "Isaac Sim closed: $(cat "$D/runs/$name/done.json" 2>/dev/null | tr -d '\n ')"
cp "$D/runs/$name/session.json" "$D/runs/$name/frames.jsonl" "$res/" 2>/dev/null
rm -rf "$D/runs/$name/frames" "$D/runs/$name/video"   # ~2 GB of JPEG per run (no video for HIL)
touch "$res/pc_done"
log "PC side done"
