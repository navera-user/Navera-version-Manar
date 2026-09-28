"""The celestial solver's subprocess handling: a timeout kills the whole group."""
import os
import time

from cn_pkg.nodes.solver import _run_group


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_timeout_kills_grandchildren():
    """solve-field starts helpers; killing only the direct child left them running."""
    code, out, err, timed_out = _run_group(["bash", "-c", "sleep 60 & echo $!; wait"], 1.0)
    assert timed_out
    grandchild = int(out.split()[0])
    for _ in range(20):
        if not _alive(grandchild):
            break
        time.sleep(0.1)
    assert not _alive(grandchild)


def test_normal_completion():
    code, out, err, timed_out = _run_group(["bash", "-c", "echo ok"], 5.0)
    assert (code, out.strip(), timed_out) == (0, "ok", False)
