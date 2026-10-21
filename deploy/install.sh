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
#   deploy/install.sh --root /tmp/stage         # staged install into another root, no sudo:
#                                               # (or DESTDIR=/tmp/stage) for checks, see below
#
# It performs deploy/README.md §3 (system packages, the `navera` service user and its
# groups, the code in /home/navera/isaac_ros_common, Python packages for that user, the
# build, /var/lib/navera, /etc/navera/navera.env if absent, sudoers, wrappers and units,
# enabling). Safe to run again: an existing /etc/navera/navera.env is never overwritten;
# the code is synchronised from this repository (build/, install/, log/ excluded).
# After it: edit /etc/navera/navera.env, calibrate the camera, then
#   sudo reboot      and, after the reboot:      deploy/check_boot.sh
#
# --root DIR (or DESTDIR=DIR) installs the same files under DIR instead of /: the code in
# DIR/home/navera/isaac_ros_common (built there as the current user unless --no-build),
# the wrappers in DIR/home/navera, the units in DIR/etc/systemd/system (enabled with
# systemctl --root), DIR/etc/navera, DIR/etc/sudoers.d (checked with visudo -f),
# DIR/var/lib/navera, DIR/data/navera. Nothing outside DIR changes, no root is needed, and
# what needs root on a real box (apt, the navera user and its groups, file owners, pip,
# daemon-reload, start) is skipped and listed. deploy/stage_check.sh uses it.
# Without --root / DESTDIR the install is exactly as before.
set -euo pipefail

SRC="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
WS=/home/navera/isaac_ros_common
UNITS="navera-discover navera-estimator navera-gps navera-imu navera-rtc navera-vehicle-link navera-pipeline-day navera-output navera-web"
DRY=0; PIP=1; APT=1; START=0; HEADLESS=0; BUILD=1
R="${DESTDIR:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --no-pip) PIP=0 ;;
    --no-apt) APT=0 ;;
    --start) START=1 ;;
    --headless) HEADLESS=1 ;;
    --units) shift; UNITS="$1" ;;
    --no-build) BUILD=0 ;;
    --root) shift; R="$1" ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (--help)" >&2; exit 2 ;;
  esac
  shift
done

say() { echo -e "\n== $*"; }
run() { if [ "$DRY" = 1 ]; then echo "  + $*"; else "$@"; fi; }
if [ -n "$R" ]; then
  R="$(realpath -m "$R")"
  [ "$R" = / ] && { echo "--root /: use the normal install (sudo $0)" >&2; exit 2; }
  # staged: every target path is under $R, files belong to the current user
  OWN=(); OWN_ENV=(); SYSTEMCTL=(systemctl --root="$R")
  skip() { echo "  (staged in $R: skipped) $*"; }
  as_navera() { if [ "$DRY" = 1 ]; then echo "  + (as $(id -un)) $1"; else bash -c "$1"; fi; }
  APT=0; PIP=0
  # the source may be a git worktree inside a repository: never copy git data or other worktrees
  STAGE_EXCLUDES=(--exclude /.git --exclude /.claude/)
else
  OWN=(-o navera -g navera); OWN_ENV=(-o root -g navera); SYSTEMCTL=(systemctl); STAGE_EXCLUDES=()
  skip() { :; }
  as_navera() { if [ "$DRY" = 1 ]; then echo "  + (as navera) $1"; else sudo -u navera -H bash -c "$1"; fi; }
fi

if [ "$DRY" = 0 ] && [ -z "$R" ] && [ "$(id -u)" != 0 ]; then
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

[ -n "$R" ] && skip "apt-get install (system packages), pip install (Python packages for navera)"

say "service user 'navera' and its hardware access (serial, I2C, cameras)"
if [ -n "$R" ]; then
  skip "useradd navera; usermod -aG dialout,i2c,video,gpio navera"
else
  id navera >/dev/null 2>&1 || run useradd -m -s /bin/bash navera
  for g in dialout i2c video gpio; do
    getent group "$g" >/dev/null && run usermod -aG "$g" navera
  done
fi

say "code: $SRC -> $R$WS"
run install -d "${OWN[@]}" "$R$WS"
run rsync -a --delete --exclude /build/ --exclude /install/ --exclude /log/ "${STAGE_EXCLUDES[@]}" \
    "$SRC/" "$R$WS/"
if [ -n "$R" ]; then skip "chown -R navera:navera $WS"; else run chown -R navera:navera "$WS"; fi

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

if [ "$BUILD" = 1 ]; then
  say "build (as navera)"
  as_navera "cd $R$WS && source /opt/ros/humble/setup.bash && colcon build --symlink-install \
    --packages-up-to navera_msgs navera_common navera_estimator navera_output gps_pkg imu_pkg rtc_pkg \
    camera_pkg day_pkg night_pkg cn_pkg simulation_web 2>&1 | tail -3"
else
  say "build: skipped (--no-build)"
fi

if [ "$PIP" = 1 ]; then
  say "learned day matcher models (DISK, LightGlue) into TORCH_HOME: the box flies offline"
  as_navera "set -a; . /etc/navera/navera.env 2>/dev/null || . $SRC/deploy/navera.env.example; set +a
python3 -c 'import kornia.feature as KF; KF.DISK.from_pretrained(\"depth\"); KF.LightGlueMatcher(\"disk\"); print(\"models ready\")' \
    || echo 'WARNING: DISK/LightGlue models not downloaded: day vision uses SIFT (NAVERA_DAY_MATCHER=auto)'"
fi

say "directories and settings"
# each level owned by navera (install -d leaves created parents root-owned: the model
# cache in /data/navera then could not be written)
run install -d "${OWN[@]}" "$R/var/lib/navera" "$R/data/navera" "$R/data/navera/areas"
run install -d -m 0755 "$R/etc/navera"
if [ -f "$R/etc/navera/navera.env" ]; then
  echo "  $R/etc/navera/navera.env exists: kept (compare with deploy/navera.env.example)"
else
  run install -m 0640 "${OWN_ENV[@]}" "$SRC/deploy/navera.env.example" "$R/etc/navera/navera.env"
  NEW_ENV=1
fi
[ -n "$R" ] && run install -d -m 0750 "$R/etc/sudoers.d"
run install -m 0440 "$SRC/deploy/sudoers/navera-web" "$R/etc/sudoers.d/navera-web"
if [ -n "$R" ]; then
  # the staged file alone (the real install checks the whole sudoers configuration)
  if [ "$DRY" = 0 ] && ! visudo -c -q -f "$R/etc/sudoers.d/navera-web"; then
    echo "sudoers check failed: $R/etc/sudoers.d/navera-web" >&2; exit 1
  fi
elif [ "$DRY" = 0 ] && ! visudo -c -q; then
  rm -f /etc/sudoers.d/navera-web; echo "sudoers check failed: navera-web removed" >&2; exit 1
fi

say "wrappers and units"
[ -n "$R" ] && run install -d "$R/home/navera" "$R/etc/systemd/system"
run install "${OWN[@]}" -m 0755 "$SRC"/deploy/systemd/navera_boot_*.sh "$R/home/navera/"
run install -m 0644 "$SRC"/deploy/systemd/navera-*.service "$R/etc/systemd/system/"
if [ -n "$R" ]; then skip "systemctl daemon-reload"; else run systemctl daemon-reload; fi

say "enable at boot: $UNITS"
# shellcheck disable=SC2086
run "${SYSTEMCTL[@]}" enable $UNITS
[ "$HEADLESS" = 1 ] && run "${SYSTEMCTL[@]}" set-default multi-user.target
if [ "$START" = 1 ]; then
  if [ -n "$R" ]; then
    skip "systemctl restart $UNITS"
  else
    # shellcheck disable=SC2086
    run systemctl restart $UNITS
  fi
fi

say "done"
[ -n "$R" ] && { echo "  staged under $R (nothing installed on this machine)"; exit 0; }
[ "${NEW_ENV:-0}" = 1 ] && echo "  NEW /etc/navera/navera.env: edit it first (sudoedit /etc/navera/navera.env):
  NAVERA_MAX_SPEED_KMH, sensor/GPS sources, camera, data paths, NAVERA_WEB_TOKEN"
echo "  next: calibrate the camera (deploy/README.md §4), then
    sudo reboot
  and after the reboot:
    $WS/deploy/check_boot.sh"
