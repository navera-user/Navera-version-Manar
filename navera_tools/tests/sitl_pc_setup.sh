#!/bin/bash
# Set up a desktop PC (Ubuntu 22.04/24.04, also WSL2 with WSLg) to WATCH NAVERA's closed-loop
# GPS-denied SITL missions: ArduPilot 4.5.7 SITL (Copter + Plane), MAVProxy (map + console) and
# pymavlink in a venv. No sudo: needs git, build-essential, python3-venv, python3-wxgtk4.0,
# python3-matplotlib, python3-opencv already installed. SIMULATION only.
#
#   bash navera_tools/tests/sitl_pc_setup.sh            # once (~15-30 min: clone + build)
#   navera_tools/tests/sitl_watch.sh copter nominal     # then, to watch a mission
set -eu
AP="${NAVERA_ARDUPILOT:-$HOME/ardupilot}"
VENV="${NAVERA_SITL_VENV:-$HOME/.venv-navera-sitl}"
if [ ! -d "$AP/.git" ]; then
  # the same release as the Jetson measurements (ArduCopter / ArduPlane 4.5.7)
  git clone --depth 1 --branch Copter-4.5.7 --recurse-submodules --shallow-submodules \
      https://github.com/ArduPilot/ardupilot.git "$AP"
fi
# system wxPython / OpenCV / matplotlib (MAVProxy map) visible inside the venv
[ -x "$VENV/bin/python" ] || python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "pymavlink>=2.4.41" MAVProxy empy==3.3.4 future pexpect
cd "$AP"
PATH="$VENV/bin:$PATH" ./waf configure --board sitl
PATH="$VENV/bin:$PATH" ./waf copter plane
ls -la build/sitl/bin/
echo "ready: navera_tools/tests/sitl_watch.sh copter nominal   (or: plane nominal)"
