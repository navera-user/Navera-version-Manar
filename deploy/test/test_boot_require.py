"""deploy/systemd/navera_boot_lib.sh: a missing data disk never starts a half-blind pipeline (NAV-DEP-02).

The shell function runs in bash on temporary folders; the wrappers and units are read.
"""
import os
import re
import subprocess

import pytest

SYSTEMD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'systemd')
LIB = os.path.join(SYSTEMD, 'navera_boot_lib.sh')


def _bash(script, env=None):
    e = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': os.environ.get('HOME', '/tmp')}
    e.update(env or {})
    return subprocess.run(['bash', '-c', f'source "{LIB}"\n{script}'], capture_output=True, text=True,
                          env=e, timeout=60)


def test_a_missing_data_disk_stops_the_wrapper_before_the_pipeline(tmp_path):
    """DEP-02: a map on an unmounted disk -> exit 1 (systemd retries in 10 s), the launch never runs."""
    r = _bash('navera_require NAVERA_MBTILES DAY_DATASET_DIR; echo LAUNCHED',
              {'NAVERA_MBTILES': '/data/not-mounted/map.mbtiles', 'DAY_DATASET_DIR': str(tmp_path)})
    assert r.returncode == 1 and 'LAUNCHED' not in r.stdout
    assert 'NAVERA_MBTILES=/data/not-mounted/map.mbtiles does not exist (data disk not mounted?)' in r.stderr
    r = _bash('navera_require NAVERA_STHN_WEIGHTS; echo LAUNCHED')
    assert r.returncode == 1 and 'NAVERA_STHN_WEIGHTS is not set' in r.stderr
    (tmp_path / 'map.mbtiles').write_text('x')
    r = _bash('navera_require NAVERA_MBTILES DAY_DATASET_DIR; echo LAUNCHED',
              {'NAVERA_MBTILES': str(tmp_path / 'map.mbtiles'), 'DAY_DATASET_DIR': str(tmp_path)})
    assert r.returncode == 0 and 'LAUNCHED' in r.stdout


@pytest.mark.parametrize('pipeline,needs', [('day', {'NAVERA_MBTILES', 'DAY_DATASET_DIR'}),
                                            ('night', {'NAVERA_MBTILES', 'NAVERA_STHN_DIR', 'NAVERA_STHN_WEIGHTS'})])
def test_each_vision_pipeline_checks_its_data_before_launching_and_is_retried(pipeline, needs):
    """DEP-02: the wrapper requires its map / weights before `exec ros2 launch`; the unit restarts in 10 s."""
    text = open(os.path.join(SYSTEMD, f'navera_boot_pipeline_{pipeline}.sh')).read()
    req = re.search(r'^navera_require (.+)$', text, re.M)
    assert req and set(req.group(1).split()) >= needs
    assert req.start() < text.index('exec ros2 launch')
    unit = open(os.path.join(SYSTEMD, f'navera-pipeline-{pipeline}.service')).read()
    assert re.search(r'^Restart=always$', unit, re.M) and re.search(r'^RestartSec=10$', unit, re.M)
