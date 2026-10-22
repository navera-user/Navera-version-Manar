"""An idle NAVERA unit (no GPS / no autopilot found) restarts by itself when hot-plug finds one.

navera_boot_lib.sh::navera_idle_until_discovered waits while discovered.env is unchanged and
exits 0 when navera-hotplug rewrites it (systemd, Restart=always, then restarts the unit with
the new settings). The wrappers are read to check they use it.
"""
import os
import subprocess
import time

SYSTEMD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'systemd')
LIB = os.path.join(SYSTEMD, 'navera_boot_lib.sh')


def test_an_idle_unit_waits_then_exits_when_discovery_changes(tmp_path):
    env_file = tmp_path / 'discovered.env'
    env_file.write_text('NAVERA_GPS_SOURCE=none\n')
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'NAVERA_DISCOVERED_ENV': str(env_file),
           'NAVERA_IDLE_POLL_S': '0.2'}
    p = subprocess.Popen(['bash', '-c', f'source "{LIB}"\nnavera_idle_until_discovered "GPS idle"; echo NOT_REACHED'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    time.sleep(1.0)
    assert p.poll() is None                                # nothing changed: still idle
    time.sleep(0.05)
    env_file.write_text('NAVERA_GPS_SOURCE=serial\nNAVERA_GPS_PORT=/dev/ttyUSB0\n')
    out, err = p.communicate(timeout=5)
    assert p.returncode == 0 and 'NOT_REACHED' not in out
    assert 'GPS idle' in err and 'discovered settings changed' in err


def test_a_missing_discovered_env_that_appears_also_wakes_it(tmp_path):
    env_file = tmp_path / 'discovered.env'
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'NAVERA_DISCOVERED_ENV': str(env_file),
           'NAVERA_IDLE_POLL_S': '0.2'}
    p = subprocess.Popen(['bash', '-c', f'source "{LIB}"\nnavera_idle_until_discovered idle'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    time.sleep(0.6)
    env_file.write_text('X=1\n')
    p.communicate(timeout=5)
    assert p.returncode == 0


def test_the_gps_and_vehicle_link_wrappers_idle_this_way():
    for name in ('navera_boot_gps.sh', 'navera_boot_vehicle_link.sh'):
        text = open(os.path.join(SYSTEMD, name)).read()
        assert 'navera_idle_until_discovered' in text and 'sleep infinity' not in text, name
    gps = open(os.path.join(SYSTEMD, 'navera_boot_gps.sh')).read()
    for source in ('serial)', 'network)', 'dronecan)', 'vehicle)', 'vehicle_gps1)', 'ros)'):
        assert source in gps
    # read-only by default: the receiver is configured / the CAN bus written only on an opt-in
    assert 'NAVERA_GPS_CONFIGURE:-0' in gps and 'NAVERA_GPS_CAN_ALLOCATE:-0' in gps
