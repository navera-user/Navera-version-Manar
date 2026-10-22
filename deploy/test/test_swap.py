"""Swap on disk for the 8 GB Jetson (F5 / H-11, NAV-PERF-06): made by the install, checked at boot.

F5: the day pipeline peaked at 3.5 GB and was OOM-killed after 4.6 min without swap. JetPack's
zram swap lives in RAM and does not count. deploy/setup_swap.sh makes /swapfile (staged here:
--root, no root needed), the pipelines' boot wrappers and check_boot.sh warn when it is missing.
"""
import os
import shutil
import subprocess

import pytest

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(DEPLOY, 'setup_swap.sh')
LIB = os.path.join(DEPLOY, 'systemd', 'navera_boot_lib.sh')
HEAD = 'Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n'
ZRAM_ONLY = HEAD + ''.join(f'/dev/zram{i}  partition\t649148\t0\t5\n' for i in range(6))   # ~3.8 GB in RAM
DISK_8G = ZRAM_ONLY + '/swapfile  file\t8388604\t0\t-2\n'


def _swaps(tmp_path, text):
    p = tmp_path / 'swaps'
    p.write_text(text)
    return str(p)


def _run(args, swaps, **env):
    e = dict(os.environ, NAVERA_SWAPS=swaps, **{k: str(v) for k, v in env.items()})
    e.pop('NAVERA_SWAP_MB', None) if 'NAVERA_SWAP_MB' not in env else None
    return subprocess.run(['bash', SETUP] + args, capture_output=True, text=True, env=e, timeout=60)


def test_zram_alone_is_not_enough_and_disk_swap_is(tmp_path):
    r = _run(['--check'], _swaps(tmp_path, ZRAM_ONLY))
    assert r.returncode == 1 and 'only 0 MB on disk' in r.stderr
    r = _run(['--check'], _swaps(tmp_path, DISK_8G))
    assert r.returncode == 0 and '8191 MB on disk' in r.stdout


@pytest.mark.skipif(not shutil.which('mkswap'), reason='mkswap absent')
def test_a_staged_setup_makes_a_swap_file_and_one_fstab_line_and_is_idempotent(tmp_path):
    root, swaps = tmp_path / 'stage', _swaps(tmp_path, ZRAM_ONLY)
    for _ in range(2):
        r = _run(['--root', str(root)], swaps, NAVERA_SWAP_MB=16)
        assert r.returncode == 0, r.stdout + r.stderr
        assert 'skipped) swapon /swapfile' in r.stdout
    f = root / 'swapfile'
    assert f.stat().st_size == 16 << 20 and oct(f.stat().st_mode & 0o777) == '0o600'
    assert f.read_bytes()[4086:4096] == b'SWAPSPACE2'              # mkswap's signature
    assert (root / 'etc' / 'fstab').read_text() == '/swapfile none swap sw,nofail 0 0\n'
    assert not (root / 'swapfile.part').exists()


def test_a_foreign_file_and_a_full_disk_are_refused(tmp_path):
    root, swaps = tmp_path / 'stage', _swaps(tmp_path, ZRAM_ONLY)
    root.mkdir()
    (root / 'swapfile').write_text('somebody else\'s data\n')
    r = _run(['--root', str(root)], swaps, NAVERA_SWAP_MB=16)
    assert r.returncode == 1 and 'not touched' in r.stderr
    assert (root / 'swapfile').read_text() == 'somebody else\'s data\n'
    r = _run(['--root', str(tmp_path / 's2')], swaps, NAVERA_SWAP_MB=1 << 40)
    assert r.returncode == 1 and 'not enough disk' in r.stderr and not (tmp_path / 's2' / 'swapfile').exists()


def test_the_real_mode_dry_run_prints_the_root_commands(tmp_path):
    r = _run(['--dry-run'], _swaps(tmp_path, ZRAM_ONLY), NAVERA_SWAP_FILE=str(tmp_path / 'sf'), NAVERA_SWAP_MB=16)
    assert r.returncode == 0, r.stderr
    for cmd in ('fallocate -l 16M', 'mkswap', 'swapon ' + str(tmp_path / 'sf'), 'none swap sw,nofail 0 0'):
        assert cmd in r.stdout, cmd
    assert not (tmp_path / 'sf').exists()


@pytest.mark.parametrize('text,warned', [(ZRAM_ONLY, True), (DISK_8G, False)])
def test_a_pipeline_start_warns_in_the_journal_without_disk_swap(tmp_path, text, warned):
    r = subprocess.run(['bash', '-c', f'source {LIB}; navera_check_swap; echo rc=$?'], capture_output=True,
                       text=True, env=dict(os.environ, NAVERA_SWAPS=_swaps(tmp_path, text)), timeout=30)
    assert 'rc=0' in r.stdout                                     # never stops the pipeline
    assert ('WARNING: only 0 MB of swap on disk' in r.stderr) is warned


def test_both_gpu_pipelines_check_swap_before_starting():
    for name in ('navera_boot_pipeline_day.sh', 'navera_boot_pipeline_night.sh'):
        text = open(os.path.join(DEPLOY, 'systemd', name)).read()
        assert text.index('navera_check_swap') < text.index('exec ros2'), name


@pytest.mark.skipif(not (shutil.which('rsync') and shutil.which('systemctl') and shutil.which('visudo')
                         and shutil.which('mkswap') and os.path.isfile('/opt/ros/humble/setup.bash')),
                    reason='rsync / systemd / ROS absent')
@pytest.mark.parametrize('swap_mb', ['', '16'])
def test_the_staged_install_makes_the_swap_only_when_asked_and_caps_the_journal(tmp_path, swap_mb):
    src = tmp_path / 'repo'
    shutil.copytree(DEPLOY, src / 'deploy', ignore=shutil.ignore_patterns('test', '__pycache__'))
    stage = tmp_path / 'stage'
    env = dict(os.environ, NAVERA_SWAPS=_swaps(tmp_path, ZRAM_ONLY))
    env.pop('NAVERA_SWAP_MB', None)
    if swap_mb:
        env['NAVERA_SWAP_MB'] = swap_mb
    r = subprocess.run(['bash', str(src / 'deploy' / 'install.sh'), '--root', str(stage), '--no-build',
                        '--units', 'navera-estimator'], capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert (stage / 'swapfile').exists() is bool(swap_mb)
    assert ('skipped) deploy/setup_swap.sh' in r.stdout) is not bool(swap_mb)
    conf = (stage / 'etc' / 'systemd' / 'journald.conf.d' / 'navera.conf').read_text()
    assert 'SystemMaxUse=1G' in conf and 'SystemKeepFree=2G' in conf


def test_the_preflight_check_warns_without_disk_swap():
    """navera_tools/check_box.py (run by check_boot.sh and before a test) says the same."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(DEPLOY), 'navera_tools'))
    import check_box
    lv, what, detail = check_box.swap_verdict(ZRAM_ONLY)
    assert (lv, what) == ('WARN', 'swap on disk') and 'setup_swap.sh' in detail
    assert check_box.swap_verdict(DISK_8G)[0] == 'PASS'
    assert check_box.swap_verdict(DISK_8G, min_mb=16384)[0] == 'WARN'
    assert check_box.swap_verdict('')[0] == 'WARN'
