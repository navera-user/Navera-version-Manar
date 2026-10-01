#!/bin/bash
# Run the NAVERA test suite from the workspace root (after colcon build).
#
#   navera_tools/run_tests.sh                 unit tests (no hardware, no ROS graph)
#   navera_tools/run_tests.sh --integration   + integration tests (start real nodes)
#
# Integration tests run on their own ROS domain, loopback only, so they never
# talk to a live NAVERA system on the same machine or network.
# Exit code 0 = everything passed.
cd "$(dirname "$0")/.." || exit 1
# ROS setup scripts reference unset variables: source them before `set -u`.
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

# Unit tests: every package's test/test_*.py except the ament style linters,
# skipping directories colcon ignores (vendored / legacy code).
mapfile -t UNIT < <(find . -path ./build -prune -o -path ./install -prune -o \
    -path '*/test/test_*.py' -print \
  | grep -vE 'test_(flake8|pep257|copyright)\.py$' \
  | while read -r f; do
      pkg=$(echo "$f" | cut -d/ -f2)
      [ -e "$pkg/COLCON_IGNORE" ] || echo "$f"
    done | sort)

# Every step has a time limit: a hang fails the run (TIMED OUT) instead of
# blocking it. The step runs in its own process group, so the ROS nodes an
# integration test started are stopped with it.
UNIT_LIMIT_S="${NAVERA_TEST_UNIT_LIMIT_S:-600}"
INTEGRATION_LIMIT_S="${NAVERA_TEST_INTEGRATION_LIMIT_S:-300}"
run_limited() {   # run_limited <seconds> <command...>  → the command's exit code, 124 on timeout
  local limit=$1; shift
  setsid "$@" &
  local pid=$! t=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$t" -ge "$limit" ]; then
      echo "TIMED OUT after ${limit} s: $*"
      kill -TERM -- "-$pid" 2>/dev/null; sleep 5; kill -KILL -- "-$pid" 2>/dev/null
      wait "$pid" 2>/dev/null
      return 124
    fi
    sleep 1; t=$((t + 1))
  done
  wait "$pid"
}

echo "== unit tests (${#UNIT[@]} files)"
run_limited "$UNIT_LIMIT_S" python3 -m pytest -q -p no:cacheprovider "${UNIT[@]}"
rc=$?
[ "$rc" -eq 0 ] || echo "FAILED STEP: unit tests (exit $rc)"

if [ "${1:-}" = "--integration" ]; then
  export ROS_DOMAIN_ID="${NAVERA_TEST_DOMAIN_ID:-77}"
  export ROS_LOCALHOST_ONLY=1
  for t in navera_tools/tests/test_*.py; do
    echo "== integration: $t"
    run_limited "$INTEGRATION_LIMIT_S" python3 "$t"
    code=$?
    if [ "$code" -ne 0 ]; then echo "FAILED STEP: $t (exit $code)"; rc=1; fi
  done
fi

[ "$rc" -eq 0 ] && echo "ALL TESTS PASSED" || echo "TESTS FAILED"
exit "$rc"
