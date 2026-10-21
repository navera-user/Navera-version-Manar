#!/bin/bash
# Watch one closed-loop GPS-denied mission (sitl_closed_loop.py --viewer): MAVProxy map + console
# show the vehicle flying on NAVERA's positions only, a small window plots the autopilot's error
# and NAVERA's against the simulator's truth. SIMULATION only. Set up first: sitl_pc_setup.sh.
#
#   navera_tools/tests/sitl_watch.sh [copter|plane] [scenario] [extra sitl_closed_loop.py args]
#
# Results: ~/.navera_sim/sitl_closed_loop/<vehicle>_<scenario>_watch.json (copy them back to the
# Jetson). On WSL2 the windows open on the Windows desktop (WSLg).
set -eu
wt="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${NAVERA_SITL_VENV:-$HOME/.venv-navera-sitl}"
export DISPLAY="${DISPLAY:-:0}"
if [ -d /mnt/wslg ]; then
  export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}"
fi
vehicle="${1:-copter}"; scenario="${2:-nominal}"; shift $(( $# > 2 ? 2 : $# ))
exec "$VENV/bin/python" -u "$wt/navera_tools/tests/sitl_closed_loop.py" --vehicle "$vehicle" \
  --scenarios "$scenario" --tag watch --viewer --mavproxy "$VENV/bin/mavproxy.py" \
  --ardupilot "${NAVERA_ARDUPILOT:-$HOME/ardupilot}" --instance 0 "$@"
