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

echo "== unit tests (${#UNIT[@]} files)"
python3 -m pytest -q -p no:cacheprovider "${UNIT[@]}"
rc=$?

if [ "${1:-}" = "--integration" ]; then
  export ROS_DOMAIN_ID="${NAVERA_TEST_DOMAIN_ID:-77}"
  export ROS_LOCALHOST_ONLY=1
  for t in navera_tools/tests/test_*.py; do
    echo "== integration: $t"
    python3 "$t" || rc=1
  done
fi

[ "$rc" -eq 0 ] && echo "ALL TESTS PASSED" || echo "TESTS FAILED"
exit "$rc"
