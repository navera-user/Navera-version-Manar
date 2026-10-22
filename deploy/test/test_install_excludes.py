"""deploy/install.sh never ships git data, other worktrees, build products or test data (B18).

The real installer runs staged (--root, no root needed, --no-build) from a copy of deploy/ placed
in a fake working repository that holds every kind of junk; the staged workspace must hold the
code and none of the junk, and verify_units.py's check must agree.
"""
import os
import shutil
import subprocess
import sys

import pytest

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DEPLOY)
import verify_units   # noqa: E402

WS = '/home/navera/isaac_ros_common'
JUNK = ['.git/HEAD', '.claude/worktrees/other/README.md', 'build/pkg/x.o', 'install/setup.bash', 'log/latest/x',
        'navera_common/.pytest_cache/v/x', 'navera_tools/rosbag2_2026_10_21/rosbag2_2026_10_21_0.db3',
        'recordings/flight.mcap', 'day_pkg/test/stray.db3']
CODE = ['navera_common/navera_common/geo.py', 'deploy/install.sh', 'camera_pkg/camera_pkg/data/day/flight_log.csv']


def _touch(root, rel):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write('x\n')


@pytest.fixture
def repo(tmp_path):
    src = tmp_path / 'repo'
    shutil.copytree(DEPLOY, src / 'deploy', ignore=shutil.ignore_patterns('test', '__pycache__'))
    for rel in JUNK + CODE[:1] + CODE[2:]:
        _touch(str(src), rel)
    return src


def test_install_sh_lists_every_required_exclude():
    have = verify_units.install_excludes()
    assert all(p in have for p in verify_units.REQUIRED_EXCLUDES), have


@pytest.mark.skipif(not (shutil.which('rsync') and shutil.which('systemctl') and shutil.which('visudo')
                         and os.path.isfile('/opt/ros/humble/setup.bash')), reason='rsync / systemd / ROS absent')
def test_a_staged_install_from_a_working_repository_ships_no_junk(repo, tmp_path):
    stage = tmp_path / 'stage'
    r = subprocess.run(['bash', str(repo / 'deploy' / 'install.sh'), '--root', str(stage), '--no-build',
                        '--units', 'navera-estimator'], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    ws = str(stage) + WS
    for rel in CODE:
        assert os.path.isfile(os.path.join(ws, rel)), rel
    for rel in JUNK:
        assert not os.path.lexists(os.path.join(ws, rel)), rel
    assert not os.path.lexists(os.path.join(ws, '.git')) and not os.path.lexists(os.path.join(ws, '.claude'))
    assert verify_units.shipped_junk(ws) == []


def test_the_real_install_dry_run_excludes_them_too():
    """Real mode (no --root) prints the same rsync with the excludes; nothing is changed (--dry-run)."""
    if not os.path.isfile('/opt/ros/humble/setup.bash'):
        pytest.skip('ROS absent')
    r = subprocess.run(['bash', os.path.join(DEPLOY, 'install.sh'), '--dry-run', '--no-apt', '--no-pip',
                        '--no-build'], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    line = next(ln for ln in r.stdout.splitlines() if 'rsync -a --delete' in ln)
    for p in ('/.git', '/.claude/', '/build/', '/install/', '/log/', '*.mcap'):
        assert f'--exclude {p}' in line, line


def test_verify_units_finds_junk_in_a_workspace(tmp_path):
    ws = str(tmp_path / 'ws')
    for rel in JUNK + CODE:
        _touch(ws, rel)
    found = {os.path.relpath(p, ws) for p in verify_units.shipped_junk(ws)}
    assert {'.git', '.claude', 'navera_common/.pytest_cache', 'navera_tools/rosbag2_2026_10_21',
            'recordings/flight.mcap', 'day_pkg/test/stray.db3'} == found     # build / install / log: built there


@pytest.mark.skipif(not (shutil.which('rsync') and shutil.which('systemctl') and shutil.which('visudo')
                         and os.path.isfile('/opt/ros/humble/setup.bash')), reason='rsync / systemd / ROS absent')
def test_an_update_removes_the_junk_an_older_install_left_on_the_box(repo, tmp_path):
    """rsync --delete skips excluded paths: an update over an install older than B18 must still
    remove its .git, worktrees, caches and recordings — and keep build/, install/, log/."""
    stage = tmp_path / 'stage'
    ws = str(stage) + WS
    for rel in JUNK:
        _touch(ws, rel)
    r = subprocess.run(['bash', str(repo / 'deploy' / 'install.sh'), '--root', str(stage), '--no-build',
                        '--units', 'navera-estimator'], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert verify_units.shipped_junk(ws) == []
    for rel in ('build/pkg/x.o', 'install/setup.bash', 'log/latest/x'):
        assert os.path.isfile(os.path.join(ws, rel)), rel
    for rel in CODE:
        assert os.path.isfile(os.path.join(ws, rel)), rel
