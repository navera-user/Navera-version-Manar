#!/usr/bin/env bash
#
# stage_check.sh — validate the NAVERA deployment WITHOUT root and without a deployed box.
#
#   deploy/stage_check.sh [--stage DIR] [--reuse] [--keep] [--kill UNIT]... [--no-day]
#
#   --stage DIR   where the staged root goes (default ~/.cache/navera-stage)
#   --reuse       keep an existing staged build (no colcon build; the code is re-synced)
#   --keep        leave the staged user units running at the end (default: stop and remove)
#   --kill UNIT   product unit whose ROS node is killed to prove the restart (repeatable;
#                 default navera-estimator)
#   --no-day      do not stage the day pipeline (it loads the vision models: GPU and ~2-3 GB)
#
# Steps, each reported:
#   1. deploy/install.sh --root DIR      the real installer, staged (no apt/useradd/chown/pip)
#   2. deploy/verify_units.py --root DIR systemd-analyze verify, ExecStart / launch / env checks
#   3. the staged units run as USER units (systemctl --user) named navera-stage-*, from the
#      staged wrappers and build, on their own ROS domain (NAVERA_STAGE_DOMAIN, default 87,
#      localhost only), web on NAVERA_STAGE_PORT (default 8281). Hardware is replaced by the
#      product's own "not present" paths (IMU, clock, vehicle link idle) and a simulated vehicle
#      GPS read through the real ROS GPS source (deploy/stage/fake_vehicle_gps.py). The day
#      pipeline runs for real on the replay camera with the data paths of the caller's
#      environment (NAVERA_MBTILES, DAY_DATASET_DIR, TORCH_HOME, NAVERA_DAY_CSV,
#      NAVERA_DAY_IMAGES_DIR — e.g. source ~/navera_env.sh first); without them it is not
#      staged. NAVERA_STAGE_GPU_LOCK=<file> wraps it in flock <file> (shared-GPU machines);
#      NAVERA_STAGE_DAY_CPU=1 hides the GPU from it instead (CUDA_VISIBLE_DEVICES empty: the
#      matcher falls back to SIFT on the CPU, as the product does without CUDA).
#   4. navera_tools/check_boot.py --user --prefix navera-stage- : every staged unit active,
#      stable, its node in the graph
#   5. restart test: the node of each --kill unit is killed (SIGKILL, by PID); the unit must
#      restart by itself (Restart=always) and check_boot.py must PASS again
#   6. clean-up (unless --keep): units stopped, runtime-enabled links and unit files removed
#
# Not covered here (needs root / the real box): the navera user and groups, file owners,
# /dev and I2C access, navera-discover (it probes serial ports, I2C and cameras), boot
# ordering at power-on, the sudoers rule in use. See docs/certification/DEPLOYMENT_VALIDATION.md.
# Never touches the system units (navera-*, navera-field, navera-academy), port 8181 or
# a camera. Exit 0 = every step PASS.
set -uo pipefail
case "${1:-}" in -h|--help) sed -n '2,/^set -uo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;; esac

SRC="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
STAGE="$HOME/.cache/navera-stage"; REUSE=0; KEEP=0; KILLS=(); DAY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --stage) shift; STAGE="$1" ;;
    --reuse) REUSE=1 ;;
    --keep) KEEP=1 ;;
    --kill) shift; KILLS+=("$1") ;;
    --no-day) DAY=0 ;;
    *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
  esac
  shift
done
[ ${#KILLS[@]} -eq 0 ] && KILLS=(navera-estimator)
STAGE="$(realpath -m "$STAGE")"
DOMAIN="${NAVERA_STAGE_DOMAIN:-87}"; PORT="${NAVERA_STAGE_PORT:-8281}"
WS=/home/navera/isaac_ros_common
UDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PFX=navera-stage-
FAKE_UNIT=navera-stagefake-gps.service          # not under the prefix: not a product unit
export TMPDIR="${TMPDIR:-$STAGE/tmp}"; mkdir -p "$TMPDIR"
verdicts=()
step() { echo; echo "=== $*"; }
verdict() { verdicts+=("$1  $2"); echo "--> $1  $2"; }

[ "$DOMAIN" = 0 ] && { echo "NAVERA_STAGE_DOMAIN must not be 0" >&2; exit 2; }
if ss -ltn 2>/dev/null | grep -q ":$PORT "; then echo "port $PORT is in use: set NAVERA_STAGE_PORT" >&2; exit 2; fi
systemctl --user is-system-running >/dev/null 2>&1 || systemctl --user status >/dev/null 2>&1 \
  || { echo "no user systemd instance (systemctl --user): cannot stage" >&2; exit 2; }

UNITS="navera-estimator navera-gps navera-imu navera-insta360 navera-rtc navera-vehicle-link navera-output navera-web"
[ "$DAY" = 1 ] && [ -n "${NAVERA_MBTILES:-}" ] && [ -n "${DAY_DATASET_DIR:-}" ] && UNITS="$UNITS navera-pipeline-day"
case " $UNITS " in *" navera-pipeline-day "*) ;; *) echo "(day pipeline not staged: --no-day, or NAVERA_MBTILES / DAY_DATASET_DIR unset)";; esac

# ---------------------------------------------------------------- 1. staged install
step "1. staged install: deploy/install.sh --root $STAGE"
args=(--root "$STAGE" --units "navera-discover $UNITS")
[ "$REUSE" = 1 ] && [ -f "$STAGE$WS/install/setup.bash" ] && args+=(--no-build)
if nice -n 19 "$SRC/deploy/install.sh" "${args[@]}" > "$STAGE.install.log" 2>&1; then
  grep -E '^== |skipped|Summary' "$STAGE.install.log" | sed 's/^/    /'
  verdict PASS "staged install (log $STAGE.install.log)"
else
  tail -20 "$STAGE.install.log"; verdict FAIL "staged install"; exit 1
fi

# ---------------------------------------------------------------- 2. static unit checks
step "2. unit checks: deploy/verify_units.py --root $STAGE"
if python3 "$SRC/deploy/verify_units.py" --root "$STAGE" --units "navera-discover $UNITS" > "$STAGE.verify.log" 2>&1; then
  tail -1 "$STAGE.verify.log" | sed 's/^/    /'; verdict PASS "unit checks"
else
  grep -E '^(FAIL|WARN)' "$STAGE.verify.log"; tail -1 "$STAGE.verify.log"; verdict FAIL "unit checks"
fi

# ---------------------------------------------------------------- 3. user units
step "3. staged stack as user units ${PFX}* (ROS_DOMAIN_ID=$DOMAIN, localhost only, web :$PORT)"
ENV="$STAGE/etc/navera/navera.env"
mkdir -p "$STAGE/var/log/ros"
# the staged box's settings: the example, then this test's choices (later lines win)
cp "$SRC/deploy/navera.env.example" "$ENV"
cat >> "$ENV" <<EOF

# ── staged test (deploy/stage_check.sh) ──
ROS_DOMAIN_ID=$DOMAIN
ROS_LOCALHOST_ONLY=1
ROS_LOG_DIR=$STAGE/var/log/ros
NAVERA_WS=$STAGE$WS
NAVERA_WEB_PORT=$PORT
NAVERA_PIPELINE=day
NAVERA_MAX_SPEED_KMH=100
NAVERA_GPS_SOURCE=ros
NAVERA_ROS_GPS_TOPIC=/navera/stage/vehicle_gps
NAVERA_SENSOR_SOURCE=box
NAVERA_VEHICLE_MAVLINK_URL=
NAVERA_MAVLINK_URL=off
NAVERA_NMEA_PORT=
NAVERA_CAMERA=replay
NAVERA_SETTINGS_FILE=$STAGE/var/lib/navera/settings.env
NAVERA_STATE_DIR=$STAGE/var/lib/navera
NAVERA_AREAS_DIR=$STAGE/data/navera/areas
NAVERA_TILE_CACHE=$STAGE/data/navera/areas/downloaded_tiles.mbtiles
EOF
# data paths of the caller's environment (an empty value would replace a launch default)
for v in NAVERA_MBTILES DAY_DATASET_DIR TORCH_HOME NAVERA_DAY_CSV NAVERA_DAY_IMAGES_DIR; do
  [ -n "${!v:-}" ] && echo "$v=${!v}" >> "$ENV"
done
# what navera-discover would write on a box without the I2C IMU / clock (not run: it probes hardware)
printf 'NAVERA_BOX_IMU=0\nNAVERA_BOX_RTC=0\n' > "$STAGE/var/lib/navera/discovered.env"
: > "$STAGE/var/lib/navera/settings.env"

mkdir -p "$UDIR"
staged_units=()
for u in $UNITS; do
  src="$STAGE/etc/systemd/system/$u.service"; dst="$UDIR/$PFX${u#navera-}.service"
  pre=""; extra=""
  if [ "$u" = navera-pipeline-day ] && [ "${NAVERA_STAGE_DAY_CPU:-0}" = 1 ]; then
    extra=" CUDA_VISIBLE_DEVICES="
  elif [ "$u" = navera-pipeline-day ] && [ -n "${NAVERA_STAGE_GPU_LOCK:-}" ]; then
    pre="/usr/bin/flock $NAVERA_STAGE_GPU_LOCK "
  fi
  # the product unit, as a user unit of the staged root: no User/Group (the current user),
  # staged paths, unit names under the prefix, started by default.target, niced; a negative
  # OOMScoreAdjust needs root (a user manager would refuse to start the unit): left out here
  sed -e '/^User=/d' -e '/^Group=/d' -e '/^SupplementaryGroups=/d' -e '/^OOMScoreAdjust=-/d' \
      -e "s#^Description=#Description=[STAGED TEST] #" \
      -e "s#EnvironmentFile=-/#EnvironmentFile=-$STAGE/#" \
      -e "s#^WorkingDirectory=.*#WorkingDirectory=$STAGE$WS#" \
      -e "s#^ExecStart=/home/navera/#ExecStart=$pre$STAGE/home/navera/#" \
      -e "s#navera-\([a-z-]*\)\.service#$PFX\1.service#g" \
      -e "s#^WantedBy=multi-user.target#WantedBy=default.target#" \
      -e "s#^\[Service\]#[Service]\nEnvironment=NAVERA_WS=$STAGE$WS ROS_LOG_DIR=$STAGE/var/log/ros$extra\nNice=19#" \
      "$src" > "$dst"
  staged_units+=("$PFX${u#navera-}.service")
done
cat > "$UDIR/$FAKE_UNIT" <<EOF
[Unit]
Description=[STAGED TEST] simulated vehicle GPS for navera-stage-gps (deploy/stage/fake_vehicle_gps.py)

[Service]
Type=simple
Environment=ROS_DOMAIN_ID=$DOMAIN ROS_LOCALHOST_ONLY=1 NAVERA_ALLOW_SIM=1 ROS_LOG_DIR=$STAGE/var/log/ros
Nice=19
ExecStart=/bin/bash -c 'source /opt/ros/humble/setup.bash && exec python3 $SRC/deploy/stage/fake_vehicle_gps.py /navera/stage/vehicle_gps'
Restart=always
RestartSec=5
EOF

cleanup() {
  [ "$KEEP" = 1 ] && { echo; echo "(--keep: staged units left running: systemctl --user stop ${PFX}'*' $FAKE_UNIT)"; return; }
  step "6. clean-up"
  systemctl --user stop "${staged_units[@]}" "$FAKE_UNIT" 2>/dev/null
  systemctl --user disable --runtime "${staged_units[@]}" >/dev/null 2>&1
  for f in "${staged_units[@]}" "$FAKE_UNIT"; do rm -f "$UDIR/$f"; done
  systemctl --user daemon-reload
  systemctl --user reset-failed "${staged_units[@]}" "$FAKE_UNIT" 2>/dev/null
  left=$(systemctl --user list-unit-files --no-legend "${PFX}*" "$FAKE_UNIT" 2>/dev/null | wc -l)
  echo "    staged user units removed (left: $left)"
}
trap cleanup EXIT

systemctl --user daemon-reload
systemctl --user enable --runtime "${staged_units[@]}" >/dev/null 2>&1   # gone at the next boot
systemctl --user start "$FAKE_UNIT"
t_start=$(date +%s)
systemctl --user start "${staged_units[@]}"
printf '    %s\n' "${staged_units[@]}" "$FAKE_UNIT (simulated GPS)"
verdict PASS "staged units started"

CHECK=(python3 "$SRC/navera_tools/check_boot.py" --user --prefix "$PFX" --env-file "$ENV"
       --env-file "$STAGE/var/lib/navera/settings.env" --env-file "$STAGE/var/lib/navera/discovered.env")

wait_pass() {   # wait_pass <timeout s> <label> → 0 when check_boot passes
  local limit=$1 t0; t0=$(date +%s)
  while [ $(( $(date +%s) - t0 )) -lt "$limit" ]; do
    if "${CHECK[@]}" --wait 6 > "$STAGE.check.log" 2>&1; then return 0; fi
    sleep 5
  done
  return 1
}

# ---------------------------------------------------------------- 4. boot check
step "4. check_boot.py --user --prefix $PFX (stack up, nodes in the graph)"
if wait_pass 420; then
  cat "$STAGE.check.log" | sed 's/^/    /'
  verdict PASS "stack up in $(( $(date +%s) - t_start )) s, every staged unit active with its node"
else
  cat "$STAGE.check.log" | sed 's/^/    /'
  for u in "${staged_units[@]}"; do journalctl --user -u "$u" -n 5 --no-pager -o cat 2>/dev/null | sed "s/^/    [$u] /"; done
  verdict FAIL "stack did not come up within 420 s"
  exit 1
fi
# the stack's own view: the arbiter's decision and the web bridge
( set +u; source /opt/ros/humble/setup.bash; source "$STAGE$WS/install/setup.bash"
  export ROS_DOMAIN_ID=$DOMAIN ROS_LOCALHOST_ONLY=1
  timeout 15 ros2 topic echo --once /navera/nav_status 2>/dev/null | grep -E '^(state|reason|active_source):' | sed 's/^/    nav_status /' )
code=$(curl -s -o /dev/null -w '%{http_code}' -m 3 "http://127.0.0.1:$PORT/health")
[ "$code" = 200 ] && verdict PASS "web bridge /health on :$PORT answers 200" || verdict FAIL "web bridge /health on :$PORT: HTTP $code"

# ---------------------------------------------------------------- 5. restart test
for ku in "${KILLS[@]}"; do
  unit="$PFX${ku#navera-}.service"
  step "5. restart test: kill the ROS node of $unit"
  main=$(systemctl --user show -p MainPID --value "$unit")
  n0=$(systemctl --user show -p NRestarts --value "$unit")
  # the node = the deepest descendant of the unit's main process (ros2 launch → node)
  victim=$main
  while child=$(ps -o pid= --ppid "$victim" 2>/dev/null | head -1 | tr -d ' '); [ -n "$child" ]; do victim=$child; done
  echo "    main PID $main ($(ps -o comm= -p "$main")), node PID $victim: $(ps -o args= -p "$victim" | cut -c1-110)"
  t_kill=$(date +%s)
  kill -KILL "$victim"
  restarted=0
  for _ in $(seq 60); do
    sleep 1
    n=$(systemctl --user show -p NRestarts --value "$unit")
    st=$(systemctl --user show -p ActiveState --value "$unit")
    if [ "$n" -gt "$n0" ] && [ "$st" = active ]; then restarted=1; break; fi
  done
  if [ "$restarted" = 1 ]; then
    verdict PASS "$unit restarted by systemd $(( $(date +%s) - t_kill )) s after the kill (NRestarts $n0 → $n)"
  else
    verdict FAIL "$unit not restarted within 60 s (NRestarts $n0 → $n, state $st)"; continue
  fi
  if wait_pass 180; then
    verdict PASS "check_boot PASS again $(( $(date +%s) - t_kill )) s after the kill (node back in the graph)"
  else
    sed 's/^/    /' "$STAGE.check.log"; verdict FAIL "check_boot not PASS within 180 s after the restart"
  fi
done
step "final check_boot.py output"
sed 's/^/    /' "$STAGE.check.log"

echo; echo "=== summary"
printf '    %s\n' "${verdicts[@]}"
if printf '%s\n' "${verdicts[@]}" | grep -q '^FAIL'; then echo "stage check: FAIL"; exit 1; fi
echo "stage check: PASS"
