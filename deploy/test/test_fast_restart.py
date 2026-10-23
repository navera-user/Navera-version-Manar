"""Crashed NAVERA units are back fast, and a unit failing at every start does not spin (B23).

On the real box a killed estimator was back after 15.4 s and a killed day pipeline after 25.5 s
(RestartSec=10): longer than the output's 10 s bridge, the autopilot's EKF failsafe landed the
copter. The critical and pipeline units restart after 1 s and never give up; the wrappers back off
(2, 4, 8... s, at most 30 s) only when a unit keeps failing at start.
"""
import glob
import os
import subprocess
import sys
import time

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DEPLOY)
import verify_units   # noqa: E402

LIB = os.path.join(DEPLOY, 'systemd', 'navera_boot_lib.sh')
UNITS = {os.path.basename(p): verify_units.parse_unit(p)
         for p in glob.glob(os.path.join(DEPLOY, 'systemd', 'navera-*.service'))}


def test_critical_and_pipeline_units_restart_within_1_s_and_never_give_up():
    found = verify_units.restart_findings(UNITS, open(LIB).read())
    names = {f[1] for f in found}
    for u in ('navera-estimator', 'navera-output', 'navera-vehicle-link', 'navera-gps', 'navera-pipeline-day',
              'navera-pipeline-night', 'navera-insta360'):
        assert u + '.service' in names
    assert 'navera-web.service' not in names                     # not needed to navigate
    assert [f for f in found if f[0] != 'PASS'] == []


def test_a_slow_restart_or_a_missing_backoff_fails():
    slow = {'Unit': [('StartLimitIntervalSec', '0')], 'Service': [('Restart', 'always'), ('RestartSec', '10')]}
    capped = {'Unit': [('StartLimitIntervalSec', '10')], 'Service': [('Restart', 'always'), ('RestartSec', '1')]}
    fast = {'Unit': [('StartLimitIntervalSec', '0')], 'Service': [('Restart', 'always'), ('RestartSec', '500ms')]}
    lv = {f[1]: f[0] for f in verify_units.restart_findings(
        {'navera-estimator.service': slow, 'navera-output.service': capped, 'navera-gps.service': fast}, '')}
    assert lv == {'navera-estimator.service': 'FAIL', 'navera-output.service': 'FAIL',
                  'navera-gps.service': 'PASS', 'navera_boot_lib.sh': 'FAIL'}       # no backoff in the lib
    assert verify_units.seconds('2min') == 120.0 and verify_units.seconds('x') is None


def _start(run_dir, ws='/ws', **env):
    e = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': os.environ.get('HOME', '/tmp'),
         'NAVERA_RUN_DIR': str(run_dir), 'NAVERA_WS': ws, 'NAVERA_BACKOFF_FREE': '2', 'NAVERA_BACKOFF_MAX_S': '1'}
    e.update(env)
    t = time.monotonic()
    r = subprocess.run(['bash', '-c', f'source "{LIB}"\nnavera_restart_backoff /x/navera_boot_test.sh; echo DONE'],
                       capture_output=True, text=True, env=e, timeout=30)
    assert r.returncode == 0 and 'DONE' in r.stdout
    return time.monotonic() - t, r.stderr


def test_a_single_crash_is_restarted_at_once_a_restart_loop_backs_off(tmp_path):
    d1, _ = _start(tmp_path)
    d2, _ = _start(tmp_path)
    assert d1 < 0.8 and d2 < 0.8                                 # within NAVERA_BACKOFF_FREE: no wait
    d3, err = _start(tmp_path)
    assert d3 >= 0.9 and 'restart loop: 3 starts' in err         # past it: waits (capped at 1 s here)
    d_other, _ = _start(tmp_path, ws='/other')                   # another workspace counts apart
    assert d_other < 0.8


def test_old_starts_are_forgotten_and_a_broken_record_never_blocks(tmp_path):
    files = []
    _start(tmp_path)
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    files[0].write_text('garbage\n1\n2\n')                       # malformed / very old entries
    d, _ = _start(tmp_path)
    assert d < 0.8
    d, _ = _start(tmp_path, NAVERA_RUN_DIR=str(tmp_path / 'missing'))   # cannot write: still starts
    assert d < 0.8
