#!/bin/bash
# NAVERA's real node chain on the Jetson for a long soak, without Isaac Sim or the PC
# (SIMULATION, development only): stand_in_render.py writes an Isaac-like run directory (frames
# cut from the scene's orthophoto along a 500 m circle at 250 m, 8 m/s), isaac_link.py turns it
# into the real camera / IMU / baro / NMEA GPS exactly as in the closed loop (1.3 s camera delay,
# GPS cut), and gps_node, estimator, live_camera, day_subscriber run as in run_navera_nodes.sh.
# day_subscriber runs under navera_tools/bench/memprofile.py (tracemalloc, torch, gc, containers
# every 60 s -> day_mem.jsonl); every node's RSS -> rss.csv every 30 s.
#
#   navera_tools/isaac/memory_soak.sh OUT_DIR [minutes=40] [--no-trace] [-- extra day_subscriber -p k:=v ...]
#
# Needs: colcon build of this workspace, ~/.navera_sim/isaac/kalaa_scene (mosaic) and kalaa_area
# (NAVERA's map), the Hikvision lens file, TORCH_HOME with the DISK/LightGlue weights. Holds the
# GPU lock (NAVERA_GPU_LOCK, default /tmp/claude-1000/navera_gpu.lock) for the whole run.
set -u
out=$(realpath -m "$1"); minutes=${2:-40}; shift 2 2>/dev/null || shift $#
trace=""; day_extra=()
while [ $# -gt 0 ]; do
  case $1 in --no-trace) trace=--no-trace;; --) shift; day_extra=("$@"); break;; esac; shift
done
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../.." && pwd)
SIM=${NAVERA_SIM_DIR:-$HOME/.navera_sim}
scene=$SIM/isaac/kalaa_scene; area=$SIM/isaac/kalaa_area
lens=${LENS:-$SIM/hik_visible_lens_2026-10-20.yaml}
lock=${NAVERA_GPU_LOCK:-/tmp/claude-1000/navera_gpu.lock}
mkdir -p "$out/logs" "$out/run" "$out/state"
# isaac_link's camera model encodes H.264 with ffmpeg: a host without one uses imageio-ffmpeg's
if ! command -v ffmpeg > /dev/null; then
  ff=$(python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null) || {
    echo "no ffmpeg (apt install ffmpeg, or pip install --user imageio-ffmpeg)"; exit 1; }
  mkdir -p "$out/bin"; ln -sf "$ff" "$out/bin/ffmpeg"; export PATH="$out/bin:$PATH"
fi
if [ -z "${MEMSOAK_LOCKED:-}" ]; then
  echo "[$(date +%T)] waiting for the GPU lock $lock"
  exec env MEMSOAK_LOCKED=1 flock "$lock" "$0" "$out" "$minutes" $trace -- "${day_extra[@]}"
fi
echo "[$(date +%T)] GPU lock held: soak $minutes min -> $out"
set +u; source /opt/ros/humble/setup.bash; source "$repo/install/setup.bash"; set -u
export ROS_DOMAIN_ID=${SOAK_DOMAIN_ID:-64} ROS_LOCALHOST_ONLY=1
# never share a ROS domain with another run on this computer (its nodes would see ours)
if grep -lqsx "ROS_DOMAIN_ID=$ROS_DOMAIN_ID" --null-data /proc/[0-9]*/environ 2>/dev/null; then
  echo "ROS domain $ROS_DOMAIN_ID is in use by another process: set SOAK_DOMAIN_ID"; exit 1
fi
export NAVERA_STATE_DIR=$out/state DAY_DATASET_DIR=$area TORCH_HOME=${TORCH_HOME:-$HOME/navera_data/.torch_cache}
L=$out/logs; pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; sleep 2; kill -9 "${pids[@]}" 2>/dev/null; }
trap cleanup EXIT INT TERM
zref=$(python3 -c "import json; print(round(json.load(open('$scene/scene.json'))['z_ref_m'], 1))")
share=$(ros2 pkg prefix navera_estimator)/share/navera_estimator/config/estimator_params.yaml
ros2 run navera_estimator estimator_node.py --ros-args --params-file "$share" -p max_speed_mps:=30.0 \
  > $L/estimator.log 2>&1 & pids+=($!)
python3 "$repo/navera_tools/bench/memprofile.py" --out "$out/day_mem.jsonl" $trace day_pkg.nodes.day_subscriber \
  --ros-args -p matcher:=auto -p max_speed_mps:=30.0 "${day_extra[@]}" > $L/day.log 2>&1 & pids+=($!)
day_pid=$!
python3 "$here/isaac_link.py" --ros-args -p run_dir:="$out/run" -p results:="$out" -p lens_file:="$lens" \
  -p scene_dir:="$scene" -p delay_s:=1.3 -p gps_cut_s:=150.0 -p camera_fps:=3.0 > $L/link.log 2>&1 & pids+=($!)
link=$!
until [ -f "$out/lens.yaml" ] && [ -f "$out/gps_port" ]; do
  kill -0 $link 2>/dev/null || { echo "isaac_link failed: $L/link.log"; exit 1; }; sleep 0.5
done
ros2 run gps_pkg gps_node.py --ros-args -p serial_port:=$(cat "$out/gps_port") > $L/gps.log 2>&1 & pids+=($!)
ros2 run camera_pkg live_camera.py --ros-args -r __ns:=/day -p input:=ros -p input_topic:=/isaac/camera/image_raw \
  -p width:=1344 -p height:=760 -p calibration_file:="$out/lens.yaml" -p fps:=3.0 -p wait_for_ready:=true \
  -p ready_topic:=/day/localizer_ready -p ground_altitude_m:=$zref -p gimbal:=true > $L/camera.log 2>&1 & pids+=($!)
until grep -q "awaiting frames\|DayLocalizer ready\|localizer_ready=True" $L/day.log 2>/dev/null; do
  kill -0 $day_pid 2>/dev/null || { echo "day_subscriber failed: $L/day.log"; exit 1; }; sleep 1
done
echo "[$(date +%T)] day_subscriber ready; rendering $minutes min"
python3 "$here/stand_in_render.py" --scene "$scene" --out "$out/run" --duration $((minutes * 60)) --fps 3 \
  > $L/render.log 2>&1 & pids+=($!)
render=$!
echo "t,node,pid,rss_mib,swap_mib" > "$out/rss.csv"     # swap: on a loaded box RSS alone hides pages swapped out
t0=$(date +%s)
while kill -0 $render 2>/dev/null; do
  for p in "${pids[@]}"; do
    [ -r /proc/$p/status ] || continue
    # the node behind a "ros2 run" wrapper is its child python process
    for q in $p $(pgrep -P $p); do
      n=$(tr '\0' ' ' < /proc/$q/cmdline | grep -o '[a-z_]*\(node\|subscriber\|camera\|link\|render\)[a-z_]*\.py\|day_pkg.nodes.day_subscriber' | head -1)
      [ -n "$n" ] && echo "$(( $(date +%s) - t0 )),$n,$q,$(awk '/VmRSS/{r=$2} /VmSwap/{w=$2} END{printf "%.1f,%.1f", r/1024, w/1024}' /proc/$q/status)" >> "$out/rss.csv"
    done
  done
  sleep 30
done
echo "[$(date +%T)] soak over"
