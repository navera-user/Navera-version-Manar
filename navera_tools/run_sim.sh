#!/bin/bash
# NAVERA mission simulator: the real NAVERA nodes + an ArduPilot autopilot
# (SITL), driven by a simulated world. No hardware. SIMULATED data only.
#
#   navera_tools/run_sim.sh
#
# Control page:  http://<jetson-ip>:8190   (choose start, destination, faults)
# Operator view: http://<jetson-ip>:8181/operator   (the product's own view)
#
# Needs an ArduPilot build with SITL copter + rover ($NAVERA_ARDUPILOT, default
# ~/ardupilot: ./waf configure --board sitl && ./waf copter rover).
# One instance at a time; its own ROS domain (79), loopback only. Never start
# it on a box in service (the real bridge owns port 8181). Stop with Ctrl-C.
# Logs: ~/.navera_sim/
set -u
cd "$(dirname "$0")/.." || exit 1
: "${NAVERA_MBTILES:?set NAVERA_MBTILES to the map (.mbtiles) — e.g. source ~/navera_env.sh}"
ap="${NAVERA_ARDUPILOT:-$HOME/ardupilot}"
for b in arducopter ardurover; do
  [ -x "$ap/build/sitl/bin/$b" ] || { echo "missing $ap/build/sitl/bin/$b (build ArduPilot SITL: ./waf copter rover)" >&2; exit 1; }
done

export NAVERA_SIM_DIR="$HOME/.navera_sim"; mkdir -p "$NAVERA_SIM_DIR"
exec 9>"$NAVERA_SIM_DIR/sim.lock"
if ! flock -n 9; then
  echo "the NAVERA simulator is already running: open http://$(hostname -I | awk '{print $1}'):8190" >&2
  exit 1
fi
for port in 8181 "${NAVERA_SIM_PORT:-8190}" "${NAVERA_SIM_TLS_PORT:-8443}" 5760 5762; do
  if ss -ltn 2>/dev/null | grep -q ":$port "; then
    echo "port $port is in use (NAVERA web service, a demo, or another ArduPilot SITL): stop it first." >&2
    exit 1
  fi
done

# Self-signed certificate for the HTTPS port (browsers share the device location
# only with HTTPS pages). Created once; the browser asks to accept it the first time.
tls="$NAVERA_SIM_DIR/tls"
if [ ! -f "$tls/cert.pem" ] && command -v openssl >/dev/null; then
  mkdir -p "$tls"
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=navera-sim" \
    -keyout "$tls/key.pem" -out "$tls/cert.pem" >/dev/null 2>&1 && chmod 600 "$tls/key.pem"
fi

set +u; source /opt/ros/humble/setup.bash && source install/setup.bash; set -u
export ROS_DOMAIN_ID="${NAVERA_SIM_DOMAIN:-79}" ROS_LOCALHOST_ONLY=1 NAVERA_ALLOW_SIM=1 NAVERA_ARDUPILOT="$ap"
ip=$(hostname -I | awk '{print $1}')
echo "NAVERA simulator — dashboard: http://$ip:8190  (or https://$ip:8443 for 'My location')"
echo "                  operator view: http://$ip:8181/operator"
echo "(Ctrl-C to stop; logs in $NAVERA_SIM_DIR)"
exec python3 navera_tools/sim/sim_server.py
