#!/usr/bin/env bash
# sudo bash /opt/navera-academy/deploy/teacher_password.sh — a NEW password for "teacher", printed once.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo" >&2; exit 1; }
set -a; . /etc/navera-academy/academy.env; set +a
PW="$(runuser -u academy -- env HOME=/var/lib/navera-academy ACADEMY_PRODUCT=1 ACADEMY_VAR="$ACADEMY_VAR" \
      PYTHONUSERBASE="$PYTHONUSERBASE" PYTHONDONTWRITEBYTECODE=1 python3 /opt/navera-academy/server/manage.py teacher-password)"
echo "teacher / $PW   (shown once)"
