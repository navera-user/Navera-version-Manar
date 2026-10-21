"""deploy/systemd/navera_boot_lib.sh: the ROS logs stay bounded (NAV-DEP-03).

navera_prune_logs runs in bash on temporary log folders.
"""
import os
import subprocess
import time

SYSTEMD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'systemd')
LIB = os.path.join(SYSTEMD, 'navera_boot_lib.sh')


def _bash(script, env=None):
    e = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': os.environ.get('HOME', '/tmp')}
    e.update(env or {})
    return subprocess.run(['bash', '-c', f'source "{LIB}"\n{script}'], capture_output=True, text=True,
                          env=e, timeout=60)


def _folder(d, name, age_days=0.0, kb=0):
    p = d / name
    p.mkdir()
    if kb:
        (p / 'launch.log').write_bytes(os.urandom(kb * 1024))
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def test_log_folders_older_than_7_days_are_pruned(tmp_path):
    """DEP-03: at every unit start (navera_prune_logs), folders older than 7 days go, recent ones stay."""
    logs = tmp_path / 'log'
    logs.mkdir()
    old, recent = _folder(logs, 'old', age_days=9), _folder(logs, 'recent', age_days=1)
    r = _bash('navera_prune_logs; echo DONE', {'ROS_LOG_DIR': str(logs), 'NAVERA_MIN_FREE_MB': '0'})
    assert r.returncode == 0 and 'DONE' in r.stdout
    assert not old.exists() and recent.exists()


def test_a_restart_loop_cannot_fill_the_disk_oldest_logs_go_first(tmp_path):
    """DEP-03: above NAVERA_LOG_MAX_MB the oldest folders are removed until it fits."""
    logs = tmp_path / 'log'
    logs.mkdir()
    folders = [_folder(logs, f'run{i}', age_days=(10 - i) / 24.0, kb=400) for i in range(10)]   # 4 MB, 10 restarts
    r = _bash('navera_prune_logs', {'ROS_LOG_DIR': str(logs), 'NAVERA_LOG_MAX_MB': '2', 'NAVERA_MIN_FREE_MB': '0'})
    assert r.returncode == 0
    kept = [f.name for f in folders if f.exists()]
    assert kept == [f'run{i}' for i in range(10 - len(kept), 10)] and 3 <= len(kept) <= 5     # the newest stay


def test_low_free_space_is_warned_and_never_stops_the_unit(tmp_path):
    logs = tmp_path / 'log'
    logs.mkdir()
    r = _bash('navera_prune_logs; echo DONE', {'ROS_LOG_DIR': str(logs), 'NAVERA_MIN_FREE_MB': str(10 ** 9)})
    assert r.returncode == 0 and 'DONE' in r.stdout and 'WARNING: only' in r.stderr
    r = _bash('navera_prune_logs; echo DONE', {'ROS_LOG_DIR': str(tmp_path / 'absent')})
    assert r.returncode == 0 and 'DONE' in r.stdout
