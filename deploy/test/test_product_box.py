"""Product box (deploy/install.sh --product) and power-cut boot settings, staged without root."""
import os
import shutil
import subprocess

import pytest

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT = os.path.join(DEPLOY, 'product')
FW = os.path.join(PRODUCT, 'navera_firewall.sh')
APPEND = '      APPEND ${cbootargs} root=PARTUUID=x rw rootwait rootfstype=ext4 console=tty0\n'


def sh(args, env=None, **kw):
    e = dict(os.environ, **(env or {}))
    return subprocess.run(args, capture_output=True, text=True, env=e, timeout=120, **kw)


def fake_root(tmp_path, env_extra=''):
    r = tmp_path / 'root'
    (r / 'etc/navera').mkdir(parents=True)
    (r / 'etc/sudoers.d').mkdir()
    (r / 'boot/extlinux').mkdir(parents=True)
    shutil.copy(os.path.join(DEPLOY, 'navera.env.example'), r / 'etc/navera/navera.env')
    with open(r / 'etc/navera/navera.env', 'a') as f:
        f.write(env_extra)
    (r / 'etc/fstab').write_text('/dev/root / ext4 defaults 0 1\n')
    (r / 'boot/extlinux/extlinux.conf').write_text('DEFAULT primary\nLABEL primary\n' + APPEND)
    (r / 'etc/sudoers.d/90-dev').write_text('dev ALL=(ALL) NOPASSWD: ALL\n')
    (r / 'etc/sudoers.d/50-ok').write_text('# NOPASSWD in a comment only\n%adm ALL=(ALL) ALL\n')
    return r


def test_apply_product_staged(tmp_path):
    r = fake_root(tmp_path)
    p = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p.returncode == 0, p.stdout + p.stderr
    env = (r / 'etc/navera/navera.env').read_text()
    assert env.count('\nNAVERA_PRODUCT_MODE=1\n') == 1 and 'NAVERA_PRODUCT_MODE=0' not in env
    token = [ln for ln in env.splitlines() if ln.startswith('NAVERA_WEB_TOKEN=')]
    assert len(token) == 1 and len(token[0].split('=', 1)[1]) == 32
    assert not (r / 'etc/sudoers.d/90-dev').exists() and (r / 'var/backups/navera-sudoers/90-dev').exists()
    assert (r / 'etc/sudoers.d/50-ok').exists()
    sshd = (r / 'etc/ssh/sshd_config.d/10-navera-product.conf').read_text()
    assert 'PasswordAuthentication no' in sshd and 'PermitRootLogin no' in sshd
    assert os.access(r / 'usr/local/sbin/navera_firewall.sh', os.X_OK)
    assert (r / 'etc/systemd/system/multi-user.target.wants/iris-firewall.service').is_symlink()
    assert 'fsck.repair=yes' in (r / 'boot/extlinux/extlinux.conf').read_text()
    # again: idempotent, the token kept
    p2 = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p2.returncode == 0 and 'already set: kept' in p2.stdout
    env2 = (r / 'etc/navera/navera.env').read_text()
    assert env2.count('NAVERA_WEB_TOKEN=') == 1 and token[0] in env2
    assert (r / 'boot/extlinux/extlinux.conf').read_text().count('fsck.repair=yes') == 1


def test_apply_product_ssh_off_and_dry_run(tmp_path):
    r = fake_root(tmp_path)
    before = (r / 'etc/navera/navera.env').read_text()
    p = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r), '--dry-run'])
    assert p.returncode == 0, p.stderr
    assert (r / 'etc/navera/navera.env').read_text() == before and (r / 'etc/sudoers.d/90-dev').exists()
    p = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)], env={'NAVERA_PRODUCT_SSH': 'off'})
    assert p.returncode == 0, p.stderr
    assert not (r / 'etc/ssh/sshd_config.d/10-navera-product.conf').exists()
    assert 'NAVERA_PRODUCT_SSH=off' in (r / 'etc/navera/navera.env').read_text()


def test_apply_product_never_waits_for_every_disk(tmp_path):
    """A bare `sync` flushes every disk on the box: with a USB disk being filled it blocked
    apply_product.sh past the test's time limit (release 0.8.1 test run). Only the files it
    writes, and their file system, are synced."""
    shim = tmp_path / 'bin'
    shim.mkdir()
    (shim / 'sync').write_text('#!/bin/sh\n[ $# -gt 0 ] || { echo "bare sync" >&2; sleep 60; }\nexec /bin/sync "$@"\n')
    (shim / 'sync').chmod(0o755)
    r = fake_root(tmp_path)
    path = {'PATH': f"{shim}:{os.environ['PATH']}"}
    p = subprocess.run([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)], capture_output=True,
                       text=True, env=dict(os.environ, **path), timeout=30)
    assert p.returncode == 0 and 'bare sync' not in p.stderr, p.stdout + p.stderr
    assert 'fsck.repair=yes' in (r / 'boot/extlinux/extlinux.conf').read_text()


def fw(env, *args):
    base = {k: '' for k in ('NAVERA_VEHICLE_MAVLINK_URL', 'NAVERA_MAVLINK_URL', 'NAVERA_FW_ALLOW_FROM',
                            'NAVERA_FW_ALLOW_TCP', 'NAVERA_FW_ALLOW_UDP', 'NAVERA_PRODUCT_SSH', 'NAVERA_WEB_PORT')}
    base.update(ROS_LOCALHOST_ONLY='1', ROS_DOMAIN_ID='42', NAVERA_FW_CAMERAS='0')
    base.update(env)
    return sh(['bash', FW, *args], env=base)


def test_firewall_default_closed_except_web_and_ssh():
    out = fw({}, '--print').stdout
    assert out.count('-A NAVERA-IN -j DROP') == 2
    assert '-p tcp -m multiport --dports 8181,22 -j ACCEPT' in out
    assert '-p udp -m multiport' not in out                 # ROS localhost only, no MAVLink listener
    assert '-p ipv6-icmp -j ACCEPT' in out                  # neighbour discovery (IPv6 cameras)


def test_firewall_follows_the_settings():
    out = fw({'NAVERA_PRODUCT_SSH': 'off', 'NAVERA_VEHICLE_MAVLINK_URL': 'udpin:0.0.0.0:14550',
              'NAVERA_MAVLINK_URL': 'tcpin:0.0.0.0:5760', 'ROS_LOCALHOST_ONLY': '0', 'ROS_DOMAIN_ID': '2',
              'NAVERA_FW_ALLOW_UDP': '5600,bad;rm', 'NAVERA_FW_ALLOW_FROM': '192.168.144.0/24'}, '--print')
    assert out.returncode == 0
    v4, v6 = out.stdout.split('## IPv6')
    assert '-s 192.168.144.0/24 -p tcp -m multiport --dports 8181,5760 -j ACCEPT' in v4
    assert '-s 192.168.144.0/24 -p udp -m multiport --dports 14550,7900:8149,5600 -j ACCEPT' in v4
    assert 'dports' not in v6                                # IPv4-only sources: nothing open on IPv6
    assert 'ignored port' in out.stderr


def test_firewall_lets_plug_and_play_cameras_in_by_default():
    out = fw({'NAVERA_FW_CAMERAS': ''}, '--print').stdout       # unset: on
    assert '-p udp -m multiport --dports 5600,8554 -j ACCEPT' in out      # pushed RTP / GoPro MPEG-TS
    # ONVIF / GigE Vision answers, to the box's ephemeral ports only (not a way past the firewall)
    assert '-p udp -m udp --dport 32768:60999 -m multiport --sports 3702,3956 -j ACCEPT' in out
    out = fw({'NAVERA_FW_CAMERAS': '', 'NAVERA_FW_ALLOW_FROM': '192.168.144.0/24'}, '--print').stdout
    assert '-s 192.168.144.0/24 -p udp -m udp --dport 32768:60999 -m multiport --sports 3702,3956 -j ACCEPT' in out
    assert '-p udp -m multiport --sports' not in fw({}, '--print').stdout  # NAVERA_FW_CAMERAS=0


def test_firewall_rules_load_in_a_namespace():
    if sh(['unshare', '-rn', 'true']).returncode != 0 or not shutil.which('iptables-restore'):
        pytest.skip('no user namespaces / iptables here')
    p = fw({'ROS_LOCALHOST_ONLY': '0', 'ROS_DOMAIN_ID': 'auto', 'NAVERA_FW_ALLOW_FROM': '10.0.0.0/8,fe80::/10'},
           '--check')
    assert p.returncode == 0, p.stderr
    assert 'firewall rules OK' in p.stdout


def test_setup_fs_flags_unsafe_mounts_and_missing_nofail(tmp_path):
    r = fake_root(tmp_path)
    (r / 'etc/fstab').write_text('/dev/root / ext4 data=writeback 0 1\nUUID=x /data ext4 defaults 0 2\n')
    p = sh([os.path.join(DEPLOY, 'setup_fs.sh'), '--root', str(r), '--check'])
    assert p.returncode == 1
    assert 'FAIL  root mounted with data=writeback' in p.stdout and 'without nofail' in p.stdout
    assert 'fsck.repair=yes' not in (r / 'boot/extlinux/extlinux.conf').read_text()   # --check changes nothing


def test_web_host_resolution():
    lib = os.path.join(DEPLOY, 'systemd', 'navera_boot_lib.sh')
    cases = {'': '0.0.0.0', 'localhost': '127.0.0.1', '10.1.2.3': '10.1.2.3', 'iface:lo': '127.0.0.1',
             'iface:no_such_if0': '127.0.0.1', '0.0.0.0; rm -rf /': '127.0.0.1'}
    for value, want in cases.items():
        p = sh(['bash', '-c', f'source "{lib}"; navera_web_host'],
               env={'NAVERA_WEB_HOST': value, 'NAVERA_WEB_HOST_WAIT_S': '0'})
        assert p.stdout.strip() == want, (value, p.stdout, p.stderr)


def test_boot_envcheck_wrapper(tmp_path):
    (tmp_path / 'settings.env').write_bytes(b'NAVERA_PIPELINE=da')
    (tmp_path / 'discovered.env').write_text('NAVERA_BOX_IMU=0\n')
    repo = os.path.dirname(DEPLOY)
    p = sh([os.path.join(DEPLOY, 'systemd', 'navera_boot_envcheck.sh')],
           env={'NAVERA_WS': repo, 'NAVERA_STATE_DIR': str(tmp_path)})
    assert p.returncode == 0
    assert sorted(os.listdir(tmp_path)) == ['discovered.env', 'settings.env.damaged']
