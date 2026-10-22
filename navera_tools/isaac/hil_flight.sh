#!/bin/bash
# NAVERA hardware in the loop: the REAL box (this Jetson) flies a simulated flight. NAVERA runs as
# deployed — the product's systemd units, staged as user units (deploy/stage_check.sh), its
# navera.env — and is fed over the network by the Isaac Sim PC (run_hil.sh there):
#   camera  RTSP / H.264 network camera (NAVERA_CAMERA_INPUT=gst, rtspsrc ! nvv4l2decoder)
#   GPS     NMEA over TCP (NAVERA_GPS_SOURCE=network, NAVERA_GPS_URL), jammed after the cut
#   vehicle ArduPilot SITL over MAVLink TCP (NAVERA_SENSOR_SOURCE=vehicle, navera-vehicle-link):
#           attitude + baro in, NAVERA's GPS_INPUT out through the link's relay (GPS_TYPE 14)
# SIMULATION feeding the real box: the box's timing, load and recovery are real; the world,
# the camera and the vehicle are not.
#
#   navera_tools/isaac/hil_flight.sh --name NAME [--pc dev@100.115.52.19] [--pc-ip 192.168.1.192]
#       [--box-ip 192.168.1.118] [--pc-repo Navera_hil] [--kill navera-estimator@60,navera-output@120]
#       [--stage DIR] [--prepare-only] [--pc-args "--legs 3 --radius 400 --speed 10 --cut-after 75"]
#
#   --kill UNIT[:NODE]@S,...  S s after the GPS cut, SIGKILL (like stage_check.sh) that unit's ROS node:
#                      the first one (deepest first child of its launch), or the node whose script is
#                      NODE (e.g. navera-pipeline-day:day_subscriber), or with NODE "unit" the unit's main
#                      process (its launch: systemd restarts the whole unit). hil_kills.jsonl says when the
#                      node was back (respawned by its launch, or the unit restarted by systemd)
#   --prepare-only     sync the PC copy and build the staged install, fly nothing
# Locks (shared machines): the PC flight under $PC_LOCK (one flight per lock), the box's GPU under
# $GPU_LOCK, and $QUIET_LOCK exclusively (other CPU-heavy work on the box takes it shared).
# Results: ~/.navera_sim/isaac/hil/NAME (hil_summary.json, hil_report.md, the records, logs/).
set -u
name=hil_$(date +%Y%m%d_%H%M); pc=dev@100.115.52.19; pc_ip=192.168.1.192; box_ip=192.168.1.118
pc_repo=Navera_hil; kills="navera-estimator@60,navera-output@120"; prepare_only=0
pc_args="--legs 3 --radius 400 --speed 10 --cut-after 75 --alt 250 --time 10:30"
STAGE=$HOME/.cache/navera-hil-stage; inner=0
PC_LOCK=${PC_LOCK:-/tmp/claude-1000/navera_pc.lock}; GPU_LOCK=${GPU_LOCK:-/tmp/claude-1000/navera_gpu.lock}
QUIET_LOCK=${QUIET_LOCK:-/tmp/claude-1000/navera_hil_quiet.lock}
args=("$@")
while [ $# -gt 0 ]; do
  case $1 in
    --name) name=$2;; --pc) pc=$2;; --pc-ip) pc_ip=$2;; --box-ip) box_ip=$2;; --pc-repo) pc_repo=$2;;
    --kill) kills=$2;; --stage) STAGE=$2;; --pc-args) pc_args=$2;;
    --prepare-only) prepare_only=1; shift; continue;;
    --inner) inner=1; shift; continue;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac; shift 2
done
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../.." && pwd)
res=$HOME/.navera_sim/isaac/hil/$name; mkdir -p "$res/logs"
SSH=(ssh -o BatchMode=yes -o ServerAliveInterval=10 "$pc")
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$res/hil.log"; }
UDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"; PFX=navera-stage-
DOMAIN=${NAVERA_STAGE_DOMAIN:-87}
inst=5; sitl_serial1=$((5762 + 10 * inst)); rtsp_port=8564; nmea_port=10117; truth_port=15531

# the data the staged day pipeline uses (the Isaac scene's map, the models)
export NAVERA_MBTILES=${NAVERA_MBTILES:-$HOME/navera_data_map.mbtiles}
export DAY_DATASET_DIR=$HOME/.navera_sim/isaac/kalaa_area
export TORCH_HOME=${TORCH_HOME:-$HOME/navera_data/.torch_cache}
zref=$(python3 -c "import json; print(round(json.load(open('$HOME/.navera_sim/isaac/kalaa_scene/scene.json'))['z_ref_m'], 1))")

write_env() {   # the box's installation: what a real box fed by this vehicle would have in navera.env
  cp "$HOME/.navera_sim/isaac/campaign/c3_base/lens.yaml" "$res/lens.yaml"   # the camera's calibration
  cat > "$res/hil.env" <<EOF
# hardware in the loop ($name): a box on a copter whose camera, GPS and autopilot are on the network
NAVERA_PIPELINE=day
NAVERA_MAX_SPEED_KMH=108
NAVERA_VEHICLE_TYPE=drone
NAVERA_SENSOR_SOURCE=vehicle
NAVERA_VEHICLE_MAVLINK_URL=tcp:$pc_ip:$sitl_serial1
NAVERA_GPS_SOURCE=network
NAVERA_GPS_URL=tcp:$pc_ip:$nmea_port
NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650
NAVERA_FORWARD_DEGRADED=true
NAVERA_DEGRADED_SIGMA_M=15
NAVERA_CAMERA=live
NAVERA_CAMERA_INPUT=gst
NAVERA_CAMERA_GST_PIPELINE="rtspsrc location=rtsp://$pc_ip:$rtsp_port/navera latency=0 protocols=tcp ! rtph264depay ! video/x-h264,stream-format=byte-stream,alignment=au ! nvv4l2decoder ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false"
NAVERA_CAMERA_SIZE=1344x760
NAVERA_CAMERA_FPS=3
NAVERA_CAMERA_CALIBRATION=$res/lens.yaml
NAVERA_CAMERA_GIMBAL=true
NAVERA_CAMERA_LATENCY_S=0
NAVERA_GROUND_ALTITUDE_M=$zref
NAVERA_DAY_MATCHER=auto
DAY_DATASET_DIR=$DAY_DATASET_DIR
NAVERA_MBTILES=$NAVERA_MBTILES
TORCH_HOME=$TORCH_HOME
EOF
}

if [ "$inner" = 0 ]; then
  # ── preparation (no lock): the PC's own copy, the staged install ──
  log "HIL $name: syncing $repo -> $pc:~/$pc_repo"
  rsync -a --delete -e "ssh -o BatchMode=yes" --exclude .git --exclude /build --exclude /install --exclude /log \
    --exclude '__pycache__' "$repo/" "$pc:$pc_repo/" || { log "rsync to the PC failed"; exit 1; }
  write_env
  units="navera-discover navera-estimator navera-gps navera-imu navera-insta360 navera-rtc navera-vehicle-link navera-output navera-web navera-pipeline-day"
  if [ ! -f "$STAGE/home/navera/isaac_ros_common/install/setup.bash" ]; then
    log "staged install (deploy/install.sh --root $STAGE): colcon build, niced"
    flock -s "$QUIET_LOCK" nice -n 19 "$repo/deploy/install.sh" --root "$STAGE" --units "$units" > "$res/install.log" 2>&1 \
      || { log "staged install failed: $res/install.log"; exit 1; }
  fi
  [ "$prepare_only" = 1 ] && { log "prepared"; exit 0; }
  log "waiting for the PC ($PC_LOCK), the GPU ($GPU_LOCK) and a quiet box ($QUIET_LOCK, max 15 min)"
  exec flock "$PC_LOCK" flock "$GPU_LOCK" bash "$here/$(basename "$0")" "${args[@]}" --inner
fi

# ── the flight (locks held) ────────────────────────────────────────────────────────────────
exec 9> "$QUIET_LOCK"
flock -w 900 9 || log "WARNING: the box is not quiet (another CPU-heavy job holds $QUIET_LOCK): flying anyway"
log "locks held: flight $name"
write_env
pids=()
cleanup() {
  [ -n "${rec:-}" ] && kill -INT "$rec" 2>/dev/null
  kill "${pids[@]}" 2>/dev/null
  # the staged units (exactly the ones stage_check.sh wrote), then their files
  mapfile -t su < <(cd "$UDIR" 2>/dev/null && ls ${PFX}*.service navera-stagefake-gps.service 2>/dev/null)
  if [ ${#su[@]} -gt 0 ]; then
    for u in "${su[@]}"; do journalctl --user -u "$u" --since "@$t_start" --no-pager -o short-precise > "$res/logs/$u.log" 2>/dev/null; done
    # the nodes' own logs (a box without a persistent user journal keeps only these)
    find "$STAGE/var/log/ros" -newermt "@$t_start" -type f -exec cp --parents {} "$res/logs/" \; 2>/dev/null
    systemctl --user stop "${su[@]}" 2>/dev/null
    systemctl --user disable --runtime "${su[@]}" >/dev/null 2>&1
    for u in "${su[@]}"; do rm -f "${UDIR:?}/${u:?}"; done
    systemctl --user daemon-reload; systemctl --user reset-failed "${su[@]}" 2>/dev/null
  fi
  "${SSH[@]}" "touch ~/navera_results/$name/stop_windows" 2>/dev/null
}
trap cleanup EXIT
t_start=$(date +%s)

# 1. the PC clock against this box's (NTP-like: 20 exchanges over one ssh, the fastest wins)
python3 - "$pc" > "$res/clock.json" <<'PY'
import json, subprocess, sys, time
p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", sys.argv[1], "python3 -u -c \"import sys,time\nfor l in sys.stdin: print(repr(time.time()), flush=True)\""],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
best = None
for _ in range(25):
    t1 = time.time(); p.stdin.write("x\n"); p.stdin.flush(); pc = float(p.stdout.readline()); t2 = time.time()
    if best is None or t2 - t1 < best[0]:
        best = (t2 - t1, pc - (t1 + t2) / 2)
    time.sleep(0.05)
p.stdin.close(); p.wait()
print(json.dumps(dict(rtt_ms=round(best[0] * 1000, 2), pc_offset_s=round(best[1], 4))))
PY
offset=$(python3 -c "import json; print(json.load(open('$res/clock.json'))['pc_offset_s'])")
log "PC clock - box clock = $offset s ($(cat "$res/clock.json"))"

# 2. the PC side: SITL, Isaac Sim, the vehicle's sensors on the network
"${SSH[@]}" "bash ~/$pc_repo/navera_tools/isaac/run_hil.sh --name $name --box $box_ip --instance $inst \
  --rtsp-port $rtsp_port --nmea-port $nmea_port --truth-port $truth_port $pc_args > ~/navera_hil_$name.out 2>&1" &
pc_pid=$!
pids+=($pc_pid)

# 3. the recorder (staged stack's domain)
( set +u; source /opt/ros/humble/setup.bash; source "$STAGE/home/navera/isaac_ros_common/install/setup.bash"
  export ROS_DOMAIN_ID=$DOMAIN ROS_LOCALHOST_ONLY=1
  exec python3 "$here/hil_record.py" --ros-args -p results:="$res" -p pc_offset_s:="$offset" -p truth_port:=$truth_port \
    -p lat0:=35.8685 -p lon0:=10.5352 -p z_ref:="$zref" -p pc_host:="$pc_ip" -p rtt_port:=$nmea_port ) > "$res/logs/hil_record.log" 2>&1 &
rec=$!

# 4. NAVERA starts once the camera stream is up (a live camera that cannot open exits and restarts)
for i in $(seq 1 600); do
  "${SSH[@]}" "test -f ~/navera_results/$name/streaming" 2>/dev/null && break
  kill -0 $pc_pid 2>/dev/null || { log "PC side ended: $("${SSH[@]}" "tail -5 ~/navera_hil_$name.out")"; exit 1; }
  sleep 3
done
# the box must reach the PC's camera and GPS ports over the LAN (the PC's firewall / WSL mirrored
# networking has refused them: hil_resil1 flew 15 min with neither and never armed)
reach=""
for i in $(seq 1 20); do
  reach=""
  for port in $rtsp_port $nmea_port; do
    timeout 2 bash -c "echo > /dev/tcp/$pc_ip/$port" 2>/dev/null || reach="$reach $port"
  done
  [ -z "$reach" ] && break
  sleep 3
done
[ -z "$reach" ] || { log "the box cannot reach $pc_ip on TCP port(s)$reach (PC firewall / network): no flight"; exit 1; }
log "camera stream up: starting NAVERA (staged product units, nice 0)"
NAVERA_STAGE_DOMAIN=$DOMAIN "$repo/deploy/stage_check.sh" --stage "$STAGE" --reuse --keep --kill none --nice 0 \
  --env-extra "$res/hil.env" > "$res/stage_check.log" 2>&1
grep -E '^--> ' "$res/stage_check.log" | sed 's/^/    /' | tee -a "$res/hil.log"
grep -q '^--> FAIL' "$res/stage_check.log" && { log "staged stack FAILED: $res/stage_check.log"; exit 1; }
for i in $(seq 1 300); do       # the day node's log says when its map and models are loaded
  find "$STAGE/var/log/ros" -newermt "@$t_start" -type f -name '*.log' -print0 2>/dev/null \
    | xargs -0 -r grep -l "localizer_ready=True\|DayLocalizer ready" 2>/dev/null | grep -q . && break
  sleep 2
done
"${SSH[@]}" "touch ~/navera_results/$name/jetson_ready"
log "NAVERA up on the box ($(( $(date +%s) - t_start )) s): the PC arms"

# 5. the flight: kills after the GPS cut, until sitl_demo says done
until [ -f "$res/gps_cut" ]; do
  kill -0 $pc_pid 2>/dev/null || { log "PC side ended before the GPS cut: no flight"; exit 1; }
  sleep 1
done
t_cut_ms=$(date +%s%3N)
killw=()
log "GPS cut (t=$(cat "$res/gps_cut" 2>/dev/null) s)"
IFS=, read -ra KL <<< "$kills"
for k in "${KL[@]}"; do
  [ -n "$k" ] || continue
  spec=${k%@*}; at=${k#*@}
  unit=${spec%%:*}; want=""; [ "$spec" != "$unit" ] && want=${spec#*:}
  su="${PFX}${unit#navera-}.service"
  target=$(( t_cut_ms + at * 1000 ))
  while [ "$(date +%s%3N)" -lt "$target" ]; do
    [ -f "$res/flight_done" ] && break 2; sleep 0.2
  done
  main=$(systemctl --user show -p MainPID --value "$su"); n0=$(systemctl --user show -p NRestarts --value "$su")
  cg=$(systemctl --user show -p ControlGroup --value "$su")
  victim=$main
  if [ "$want" = unit ]; then
    :                                                   # the launch itself: the whole unit restarts
  elif [ -n "$want" ]; then
    victim=""
    for p in $(cat "/sys/fs/cgroup$cg/cgroup.procs" 2>/dev/null); do
      tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q "/$want\.py " && { victim=$p; break; }
    done
    [ -n "$victim" ] || { log "no $want node in $su: kill skipped"; continue; }
  else
    while child=$(ps -o pid= --ppid "$victim" 2>/dev/null | head -1 | tr -d ' '); [ -n "$child" ]; do victim=$child; done
  fi
  node=$(tr '\0' '\n' < "/proc/$victim/cmdline" 2>/dev/null | grep -m1 -E '\.py$' | xargs -r basename)
  [ "$want" = unit ] && node=""
  tk=$(date +%s.%N)
  kill -KILL "$victim" 2>/dev/null
  log "KILLED $su ${node:-main process} PID $victim at cut+$at s"
  ( for _ in $(seq 240); do
      sleep 0.25
      n=$(systemctl --user show -p NRestarts --value "$su"); st=$(systemctl --user show -p ActiveState --value "$su")
      how=""
      if [ "$n" -gt "$n0" ] && [ "$st" = active ]; then
        how=systemd
      elif [ -n "$node" ] && [ "$st" = active ]; then      # respawned alone by its launch (B23)
        for p in $(cat "/sys/fs/cgroup$cg/cgroup.procs" 2>/dev/null); do
          [ "$p" != "$victim" ] && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q "/$node " && how=respawn
        done
      fi
      if [ -n "$how" ]; then
        echo "{\"unit\": \"$spec\", \"box\": $tk, \"pid\": $victim, \"node\": \"$node\", \"restarted\": true, \"how\": \"$how\", \"active_after_s\": $(python3 -c "print(round($(date +%s.%N) - $tk, 1))")}" >> "$res/hil_kills.jsonl"
        exit 0
      fi
    done
    echo "{\"unit\": \"$spec\", \"box\": $tk, \"pid\": $victim, \"node\": \"$node\", \"restarted\": false}" >> "$res/hil_kills.jsonl" ) &
  killw+=($!)
done
until [ -f "$res/flight_done" ]; do kill -0 $pc_pid 2>/dev/null || break; sleep 2; done
log "flight over; waiting for the PC side to finish"
for i in $(seq 1 300); do kill -0 $pc_pid 2>/dev/null || break; sleep 2; done
[ ${#killw[@]} -gt 0 ] && wait "${killw[@]}" 2>/dev/null

# 6. the PC's files next to the box's record, then the numbers
rsync -a -e "ssh -o BatchMode=yes" --exclude state --exclude plot --exclude navera_view --exclude 'sitl/terrain' \
  --exclude position.csv --exclude day.csv --exclude proc.csv --exclude events.jsonl --exclude ekf.csv \
  "$pc:navera_results/$name/" "$res/pc/"
for f in stream.csv sitl_gps.csv frames.jsonl sitl_flown.json sitl_session.json sitl_events.jsonl session.json; do
  [ -f "$res/pc/$f" ] && cp "$res/pc/$f" "$res/"
done
kill -INT $rec 2>/dev/null; wait $rec 2>/dev/null; rec=""
python3 "$here/hil_summarise.py" "$res" > "$res/hil_summary.out" 2>&1 || log "hil_summarise failed: $res/hil_summary.out"
cat "$res/hil_report.md" 2>/dev/null | tee -a "$res/hil.log"
log "done: $res"
