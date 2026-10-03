#!/usr/bin/env bash
#
# install.sh — install (or update) NAVERA on this Jetson as boot services, in one command.
#
#   sudo deploy/install.sh                      # install / update, enable the typical units
#   sudo deploy/install.sh --dry-run            # print what would be done, change nothing
#   sudo deploy/install.sh --units "navera-estimator navera-gps ..."   # choose the units
#   sudo deploy/install.sh --no-pip --no-apt    # code + build + units only (fast update)
#   sudo deploy/install.sh --start              # also start them now
#   sudo deploy/install.sh --headless           # boot without the desktop (multi-user.target)
#
# It performs deploy/README.md §3 (system packages, the `navera` service user and its
# groups, the code in /home/navera/isaac_ros_common, Python packages for that user, the
# build, /var/lib/navera, /etc/navera/navera.env if absent, sudoers, wrappers and units,
# enabling). Safe to run again: an existing /etc/navera/navera.env is never overwritten;
# the code is synchronised from this repository (build/, install/, log/ excluded).
# After it: edit /etc/navera/navera.env, calibrate the camera, then
#   sudo reboot      and, after the reboot:      deploy/check_boot.sh
set -euo pipefail

SRC="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
WS=/home/navera/isaac_ros_common
UNITS="navera-discover navera-estimator navera-gps navera-imu navera-rtc navera-vehicle-link navera-pipeline-day navera-output navera-web"
DRY=0; PIP=1; APT=1; START=0; HEADLESS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --no-pip) PIP=0 ;;
    --no-apt) APT=0 ;;
    --start) START=1 ;;
    --headless) HEADLESS=1 ;;
    --units) shift; UNITS="$1" ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
  esac
  shift
done

say() { echo -e "\n== $*"; }
run() { if [ "$DRY" = 1 ]; then echo "  + $*"; else "$@"; fi; }
as_navera() { if [ "$DRY" = 1 ]; then echo "  + (as navera) $1"; else sudo -u navera -H bash -c "$1"; fi; }

if [ "$DRY" = 0 ] && [ "$(id -u)" != 0 ]; then
  echo "run it with sudo: sudo $0 $*" >&2; exit 1
fi
[ -f /opt/ros/humble/setup.bash ] || { echo "ROS 2 Humble is not installed in /opt/ros/humble" >&2; exit 1; }
for u in $UNITS; do
  [ -f "$SRC/deploy/systemd/$u.service" ] || { echo "unknown unit: $u" >&2; exit 2; }
done

if [ "$APT" = 1 ]; then
  say "system packages"
  run apt-get update -q
  run apt-get install -y -q git rsync python3-pip python3-colcon-common-extensions python3-yaml \
      python3-gi gir1.2-gstreamer-1.0 ros-humble-cv-bridge ros-humble-rosbag2-py
  if echo "$UNITS" | grep -q navera-pipeline-cn; then
    run apt-get install -y -q astrometry.net astrometry-data-tycho2-10-19
  fi
fi

say "service user 'navera' and its hardware access (serial, I2C, cameras)"
id navera >/dev/null 2>&1 || run useradd -m -s /bin/bash navera
for g in dialout i2c video gpio; do
  getent group "$g" >/dev/null && run usermod -aG "$g" navera
done

say "code: $SRC -> $WS"
run install -d -o navera -g navera "$WS"
run rsync -a --delete --exclude /build/ --exclude /install/ --exclude /log/ "$SRC/" "$WS/"
run chown -R navera:navera "$WS"

if [ "$PIP" = 1 ]; then
  say "Python packages for navera (Jetson PyTorch build)"
  as_navera '
printf "torch==2.8.0\ntorchvision==0.23.0\nnumpy<2\nsetuptools<80\n" > ~/navera-constraints.txt
pip3 install -q --user --no-deps --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple \
    torch==2.8.0 torchvision==0.23.0
pip3 install -q --user -c ~/navera-constraints.txt \
    "numpy<2" "scipy>=1.11,<1.14" timm kornia safetensors einops huggingface_hub \
    scikit-learn pandas "astropy<7" opencv-python==4.11.0.86 \
    pyserial pynmea2 pymavlink pygeomag==1.1.0 \
    Jetson.GPIO adafruit-blinka adafruit-circuitpython-bno08x adafruit-circuitpython-ds3231'
fi

say "build (as navera)"
as_navera "cd $WS && source /opt/ros/humble/setup.bash && colcon build --symlink-install \
    --packages-up-to navera_msgs navera_common navera_estimator navera_output gps_pkg imu_pkg rtc_pkg \
    camera_pkg day_pkg night_pkg cn_pkg simulation_web 2>&1 | tail -3"

say "directories and settings"
# each level owned by navera (install -d leaves created parents root-owned: the model
# cache in /data/navera then could not be written)
run install -d -o navera -g navera /var/lib/navera /data/navera /data/navera/areas
run install -d -m 0755 /etc/navera
if [ -f /etc/navera/navera.env ]; then
  echo "  /etc/navera/navera.env exists: kept (compare with deploy/navera.env.example)"
else
  run install -m 0640 -o root -g navera "$SRC/deploy/navera.env.example" /etc/navera/navera.env
  NEW_ENV=1
fi
run install -m 0440 "$SRC/deploy/sudoers/navera-web" /etc/sudoers.d/navera-web
if [ "$DRY" = 0 ] && ! visudo -c -q; then
  rm -f /etc/sudoers.d/navera-web; echo "sudoers check failed: navera-web removed" >&2; exit 1
fi

say "wrappers and units"
run install -o navera -g navera -m 0755 "$SRC"/deploy/systemd/navera_boot_*.sh /home/navera/
run install -m 0644 "$SRC"/deploy/systemd/navera-*.service /etc/systemd/system/
run systemctl daemon-reload

say "enable at boot: $UNITS"
# shellcheck disable=SC2086
run systemctl enable $UNITS
[ "$HEADLESS" = 1 ] && run systemctl set-default multi-user.target
if [ "$START" = 1 ]; then
  # shellcheck disable=SC2086
  run systemctl restart $UNITS
fi

say "done"
[ "${NEW_ENV:-0}" = 1 ] && echo "  NEW /etc/navera/navera.env: edit it first (sudoedit /etc/navera/navera.env):
  NAVERA_MAX_SPEED_KMH, sensor/GPS sources, camera, data paths, NAVERA_WEB_TOKEN"
echo "  next: calibrate the camera (deploy/README.md §4), then
    sudo reboot
  and after the reboot:
    $WS/deploy/check_boot.sh"
