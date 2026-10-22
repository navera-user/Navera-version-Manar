"""check_boot.py: a unit idling by design is PASS (idle), not "node missing".

Two ways a boot wrapper idles: `exec sleep infinity`, or navera_idle_until_discovered — the
wrapper's shell polling discovered.env with `sleep 5` (navera-insta360, navera-vehicle-link,
the GPS without a receiver...). Found by the hardware-in-the-loop staging: navera-insta360
idle on a box without the Insta360 kit was reported FAIL ("node not in the graph").
"""
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'navera_tools'))

import check_boot  # noqa: E402


def _spawn(cmd):
    p = subprocess.Popen(cmd)
    time.sleep(0.4)
    return p


def test_sleep_and_polling_wrapper_are_idle():
    procs = [_spawn(['sleep', '30']), _spawn(['bash', '-c', 'while sleep 5; do :; done'])]
    try:
        assert [check_boot.is_idle(p.pid) for p in procs] == [True, True]
    finally:
        for p in procs:
            p.kill()


def test_a_running_node_is_not_idle():
    procs = [_spawn(['bash', '-c', 'python3 -c "import time; time.sleep(30)"; :']),
             _spawn(['python3', '-c', 'import time; time.sleep(30)'])]
    try:
        assert [check_boot.is_idle(p.pid) for p in procs] == [False, False]
    finally:
        for p in procs:
            p.kill()
    assert check_boot.is_idle(10 ** 7) is False                 # no such process
