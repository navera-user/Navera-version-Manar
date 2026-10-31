#!/usr/bin/env bash
#
# check_boot.sh — the reboot test: after a power-on, did every enabled NAVERA unit start
# by itself and stay up? No root needed.
#
#   deploy/check_boot.sh            # report; exit 0 = every enabled unit active
#
# For each navera-* unit enabled at boot: active or not, how long after boot it became
# active, how many times systemd restarted it, and its last error lines; then the swap on
# disk (a warning when short of NAVERA_MIN_SWAP_MB, F5), the clock
# (RTC), and NAVERA's own pre-flight check (navera_tools/check_box.py) when ROS is there.
set -u
case "${1:-}" in
  -h|--help) sed -n '2,/^set -u/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
esac
WS=/home/navera/isaac_ros_common
fail=0
# the automatic day / night / celestial choice (navera-pipeline-select) runs one pipeline and
# stops the others: a pipeline it stopped is not a failure (only while the choice itself runs)
auto=""
if systemctl is-active --quiet navera-pipeline-select.service; then
  auto=$(sed -n 's/.*"pipeline": *"\([a-z]*\)".*/\1/p' /var/lib/navera/pipeline.json 2>/dev/null)
fi
boot_s=$(cut -d. -f1 /proc/uptime)
echo "up for ${boot_s}s ($(uptime -s 2>/dev/null || true) )"
printf "%-26s %-9s %-14s %s\n" unit state "active after" restarts
for u in $(systemctl list-unit-files 'navera-*.service' --state=enabled --no-legend 2>/dev/null | awk '{print $1}'); do
  st=$(systemctl is-active "$u")
  n=$(systemctl show -p NRestarts --value "$u")
  mono=$(systemctl show -p ActiveEnterTimestampMonotonic --value "$u")
  after="-"
  [ "${mono:-0}" -gt 0 ] 2>/dev/null && after="$((mono / 1000000))s"
  printf "%-26s %-9s %-14s %s\n" "$u" "$st" "$after" "$n"
  case "$u" in navera-pipeline-day.service|navera-pipeline-night.service|navera-pipeline-cn.service)
    if [ "$st" != active ] && [ -n "$auto" ] && [ "$u" != "navera-pipeline-$auto.service" ]; then
      echo "    stopped by the automatic choice: navera-pipeline-$auto runs now"; continue
    fi ;;
  esac
  if [ "$st" != active ]; then
    fail=1
    journalctl -b -u "$u" -n 5 --no-pager -o cat 2>/dev/null | sed 's/^/    /'
  fi
done
if [ -n "$auto" ]; then              # the pipeline the automatic choice runs (it may be one not enabled at boot)
  u="navera-pipeline-$auto.service"; st=$(systemctl is-active "$u")
  echo "automatic choice: $u $st — $(sed -n 's/.*"reason": *"\([^"]*\)".*/\1/p' /var/lib/navera/pipeline.json | sed 's/\\u00b0/°/g')"
  [ "$st" = active ] || fail=1
fi
[ -z "$(systemctl list-unit-files 'navera-*.service' --state=enabled --no-legend 2>/dev/null)" ] && {
  echo "no NAVERA unit is enabled at boot (sudo deploy/install.sh)"; exit 1; }

echo
# swap on disk (F5): a warning, not a failure (zram does not count)
"$(dirname "$(readlink -f "$0")")/setup_swap.sh" --check 2>&1 | sed 's/^swap: WARNING/WARN  swap:/' || true
journalctl -b -u navera-rtc --no-pager -o cat 2>/dev/null | grep -iE "valid|lost_power|drift" | tail -2
if [ -f "$WS/install/setup.bash" ]; then
  echo
  # shellcheck disable=SC1091
  ( set +u; source /opt/ros/humble/setup.bash; source "$WS/install/setup.bash"   # ROS scripts use unset variables
    set -a; . /etc/navera/navera.env 2>/dev/null; . /var/lib/navera/settings.env 2>/dev/null
    . /var/lib/navera/discovered.env 2>/dev/null; set +a
    python3 "$WS/navera_tools/check_box.py" --seconds 10 ) || fail=1
fi
echo
echo "reboot test: $([ $fail = 0 ] && echo PASS || echo FAIL)"
exit $fail
