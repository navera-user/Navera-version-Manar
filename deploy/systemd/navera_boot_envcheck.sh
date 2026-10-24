#!/usr/bin/env bash
#
# navera_boot_envcheck.sh — power-cut safety at boot: a damaged settings file (NUL bytes,
# a cut last line, not KEY=VALUE) is moved aside to <file>.damaged before any NAVERA unit
# reads it, so the units start on /etc/navera/navera.env alone instead of a cut value.
# Called by navera-discover.service (ExecStartPre, before every other unit). Stdlib Python
# only (no ROS, no workspace build needed). Never fails the boot.
#   NAVERA_ENVCHECK_FILES  the files (default: the web settings and the discovered devices)
NAVERA_WS="${NAVERA_WS:-/home/navera/isaac_ros_common}"
state="${NAVERA_STATE_DIR:-/var/lib/navera}"
files="${NAVERA_ENVCHECK_FILES:-$state/settings.env $state/discovered.env}"
# shellcheck disable=SC2086
/usr/bin/python3 -I "$NAVERA_WS/navera_common/navera_common/atomic_io.py" --check-env $files \
  || echo "[navera-boot] env check failed (ignored)" >&2
exit 0
