#!/usr/bin/env python3
"""check_boot.py — the reboot validation: after a power-on, is every NAVERA unit up, with its ROS node?

Runs WITHOUT root and changes nothing (read-only: systemctl show, /proc, the ROS graph).

    navera_tools/check_boot.py                 # table + verdict; exit 0 = PASS
    navera_tools/check_boot.py --wait 8        # listen longer to the ROS graph (default 5 s)

Units checked: every navera-*.service in deploy/systemd/ plus every installed unit whose name
contains "navera" (systemctl list-unit-files). For each unit:

    installed?   in deploy/ but not installed -> FAIL (the box is not deployed)
    enabled?     disabled units (e.g. the pipelines not selected) are not expected at boot: SKIP
    active?      an enabled unit must be active (oneshot navera-discover: active/exited, success)
    stable?      NRestarts must not grow while the check runs (a restart loop looks "active")
    node up?     the unit's ROS node(s) must be in the ROS graph (same ROS_DOMAIN_ID as the units:
                 /etc/navera/navera.env, /var/lib/navera/settings.env, discovered.env)
    idle         a driver unit whose device is not configured runs `sleep infinity` by design
                 (navera_boot_*.sh): PASS, marked idle, no node expected

The 2026-09-28 restart mechanism (Restart=always + on_exit=Shutdown) needs a reboot test:
    sudo reboot   ...then, once logged in:   navera_tools/check_boot.py
deploy/check_boot.sh is the older unit-only check (+ check_box.py); this one adds the node check.

Staged mode (no root, no deployed box; deploy/stage_check.sh): the same checks on the user units of
a staged copy of the stack, which carry a prefix and run on their own ROS domain:
    navera_tools/check_boot.py --user --prefix navera-stage- --env-file <stage>/etc/navera/navera.env
Only the installed units with that prefix are checked (a unit not staged is not reported); each is
judged as the product unit of the same name (navera-stage-estimator = navera-estimator).
"""
import argparse
import glob
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# unit -> alternatives of required node sets (node base names, any namespace), from the launch
# files the boot wrappers start (deploy/systemd/navera_boot_*.sh). Empty = no ROS node.
CAMERA = ('camera_publisher', 'live_camera')      # replay camera or the live one (NAVERA_CAMERA)
EXPECTED_NODES = {
    'navera-discover.service': [],
    'navera-estimator.service': [('estimator_node',)],
    'navera-gps.service': [('gps_node',), ('ros_gps',)],
    'navera-imu.service': [('imu_node',)],
    'navera-rtc.service': [('rtc_node',)],
    'navera-vehicle-link.service': [('vehicle_link',)],
    'navera-output.service': [('vehicle_output',)],
    'navera-pipeline-day.service': [('day_subscriber', c) for c in CAMERA],
    'navera-pipeline-night.service': [('night_subscriber', c) for c in CAMERA],
    'navera-pipeline-cn.service': [('cn_subscriber', c) for c in CAMERA],
    'navera-web.service': [('navera_web_bridge',), ('navera_stellar_bridge',)],
}
ENV_FILES = ('/etc/navera/navera.env', '/var/lib/navera/settings.env', '/var/lib/navera/discovered.env')
PROPS = ('LoadState', 'UnitFileState', 'ActiveState', 'SubState', 'Result', 'Type', 'MainPID',
         'NRestarts', 'ActiveEnterTimestampMonotonic')


SYSTEMCTL = ['systemctl']          # ['systemctl', '--user'] in staged mode (--user)
PREFIX = 'navera-'                 # unit name prefix; staged mode: e.g. navera-stage-


def product_name(unit):
    """The product unit a (possibly staged) unit stands for: navera-stage-gps.service -> navera-gps.service."""
    return 'navera-' + unit[len(PREFIX):] if unit.startswith(PREFIX) else unit


def units_to_check():
    """Return the sorted unit names from deploy/systemd and the installed unit files
    (staged mode: only the installed units with the prefix)."""
    staged = SYSTEMCTL != ['systemctl'] or PREFIX != 'navera-'
    names = set() if staged else {os.path.basename(p) for p in
                                  glob.glob(os.path.join(REPO, 'deploy', 'systemd', '*.service'))}
    out = subprocess.run(SYSTEMCTL + ['list-unit-files', '--no-legend', '--no-pager'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        name = line.split()[0] if line.split() else ''
        if not name.endswith(('.service', '.timer')):
            continue
        if (name.startswith(PREFIX) if staged else 'navera' in name.lower()):
            names.add(name)
    return sorted(names)


def unit_props(unit):
    """Return the systemd properties of a unit (systemctl show, no root needed)."""
    out = subprocess.run(SYSTEMCTL + ['show', unit, '--no-pager'] + ['-p' + p for p in PROPS],
                         capture_output=True, text=True).stdout
    return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)


def is_idle(pid):
    """Return True when the unit's main process is `sleep` (boot wrapper idling by design)."""
    try:
        with open(f'/proc/{int(pid)}/cmdline', 'rb') as f:
            argv0 = f.read().split(b'\0')[0].decode(errors='replace')
    except (OSError, ValueError):
        return False
    return os.path.basename(argv0) == 'sleep'


def read_env_files():
    """Return KEY=VALUE pairs of the NAVERA env files the units read (later files win)."""
    env = {}
    for path in ENV_FILES:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        env[k.strip().removeprefix('export ').strip()] = v.strip().strip('"\'')
        except OSError:
            pass
    return env


def ros_domain(env):
    """Return (ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY) the units run with (navera_boot_lib.sh rules)."""
    dom = env.get('ROS_DOMAIN_ID', os.environ.get('ROS_DOMAIN_ID', '0')) or '0'
    local = env.get('ROS_LOCALHOST_ONLY', os.environ.get('ROS_LOCALHOST_ONLY', '0')) or '0'
    if not dom.isdigit():                 # "auto" and no vehicle found: NAVERA's isolated domain
        dom, local = '42', '1'
    return dom, local


GRAPH_PROBE = r'''
import sys, time, rclpy
rclpy.init()
n = rclpy.create_node('navera_check_boot')
end = time.time() + float(sys.argv[1])
while time.time() < end:
    rclpy.spin_once(n, timeout_sec=0.2)
for name, ns in n.get_node_names_and_namespaces():
    if name != 'navera_check_boot':
        print(ns.rstrip('/') + '/' + name)
n.destroy_node()
rclpy.shutdown()
'''


def ros_nodes(domain, localhost_only, wait_s):
    """Return the set of node base names seen in the ROS graph, or None when ROS is unavailable."""
    env = dict(os.environ, ROS_DOMAIN_ID=domain, ROS_LOCALHOST_ONLY=localhost_only)
    cmd = [sys.executable, '-c', GRAPH_PROBE, str(wait_s)]
    try:
        import rclpy  # noqa: F401  (only to know whether ROS is sourced)
    except ImportError:                   # not sourced: source ROS 2 Humble for the probe only
        setup = '/opt/ros/humble/setup.bash'
        if not os.path.isfile(setup):
            return None
        cmd = ['bash', '-c', f'source {setup} && exec python3 -c "$0" "$1"', GRAPH_PROBE, str(wait_s)]
    try:
        out = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=wait_s + 30)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0:
        return None
    return {line.rsplit('/', 1)[-1] for line in out.stdout.split()}


def check(unit, p0, p1, nodes):
    """Return (verdict, state, node column, note) for one unit from two property samples."""
    if p1.get('LoadState') != 'loaded':
        return 'FAIL', 'not installed', '-', 'sudo deploy/install.sh'
    enabled = p1.get('UnitFileState', '')
    state = f"{p1.get('ActiveState')}/{p1.get('SubState')}"
    if enabled not in ('enabled', 'enabled-runtime', 'static', 'alias', 'indirect', 'generated'):
        note = 'not started at boot' + (' (but running now)' if p1.get('ActiveState') == 'active' else '')
        return 'SKIP', f'{enabled}, {state}', '-', note
    if p1.get('ActiveState') != 'active':
        return 'FAIL', state, '-', f"result {p1.get('Result')}, {p1.get('NRestarts', '?')} restarts"
    if p1.get('Type') == 'oneshot' and p1.get('Result') != 'success':
        return 'FAIL', state, '-', f"result {p1.get('Result')}"
    if p1.get('NRestarts') != p0.get('NRestarts') or p1.get('MainPID') != p0.get('MainPID'):
        return 'FAIL', state, '-', 'restarted during the check (restart loop?)'
    mono = int(p1.get('ActiveEnterTimestampMonotonic') or 0)
    since = f'active at boot+{mono / 1e6:.0f} s' if mono else ''
    note = ', '.join(x for x in (since, f"{p1.get('NRestarts', '0')} restarts") if x)
    unit = product_name(unit)
    if unit not in EXPECTED_NODES:
        return 'PASS', state, 'n/a', note + ' (not a ROS unit)'
    if is_idle(p1.get('MainPID', 0)):
        return 'PASS', state, 'idle', note + ' (device not configured: idles by design)'
    wanted = EXPECTED_NODES[unit]
    if not wanted:
        return 'PASS', state, 'n/a', note
    if nodes is None:
        return 'FAIL', state, '?', note + ' (ROS graph not readable)'
    for alt in wanted:
        if all(n in nodes for n in alt):
            return 'PASS', state, '+'.join(alt), note
    missing = ' or '.join('+'.join(n for n in alt if n not in nodes) for alt in wanted)
    return 'FAIL', state, 'missing', note + f' (node not in the graph: {missing})'


def main(argv=None):
    """Print the PASS/FAIL table; return 0 when every unit expected at boot passes."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--wait', type=float, default=5.0, help='seconds to listen to the ROS graph')
    ap.add_argument('--user', action='store_true',
                    help='staged mode: check user units (systemctl --user) instead of system units')
    ap.add_argument('--prefix', default='navera-',
                    help='unit name prefix (staged mode: e.g. navera-stage-); default navera-')
    ap.add_argument('--env-file', action='append', default=None,
                    help='env file the units read, in load order (repeatable); default the box\'s three')
    args = ap.parse_args(argv)
    global SYSTEMCTL, PREFIX, ENV_FILES
    SYSTEMCTL = ['systemctl', '--user'] if args.user else ['systemctl']
    PREFIX = args.prefix
    if args.env_file:
        ENV_FILES = tuple(args.env_file)

    with open('/proc/uptime') as f:
        uptime0 = float(f.read().split()[0])
    units = units_to_check()
    first = {u: unit_props(u) for u in units}
    env = read_env_files()
    domain, local = ros_domain(env)
    nodes = ros_nodes(domain, local, args.wait)
    last = {u: unit_props(u) for u in units}

    boot = subprocess.run(['uptime', '-s'], capture_output=True, text=True).stdout.strip()
    print(f'NAVERA boot check — booted {boot} (up {uptime0:.0f} s); ROS_DOMAIN_ID={domain}'
          f' localhost_only={local}; env files: '
          + (', '.join(p for p in ENV_FILES if os.path.isfile(p)) or 'none found'))
    print(f'ROS graph: {"unreadable (ROS not available)" if nodes is None else f"{len(nodes)} node(s)"}')
    rows = [(u,) + check(u, first[u], last[u], nodes) for u in units]
    w = max(len(r[0]) for r in rows)
    print(f'\n{"unit":<{w}}  {"verdict":<7}  {"state":<26}  {"node":<32}  note')
    for unit, verdict, state, node, note in rows:
        print(f'{unit:<{w}}  {verdict:<7}  {state:<26}  {node:<32}  {note}')
    fails = [r[0] for r in rows if r[1] == 'FAIL']
    counts = {v: sum(r[1] == v for r in rows) for v in ('PASS', 'FAIL', 'SKIP')}
    print(f"\n{counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['SKIP']} SKIP (not enabled at boot)")
    what = 'staged boot check' if (args.user or args.prefix != 'navera-') else 'reboot check'
    print(f"{what}: {'FAIL — ' + ', '.join(fails) if fails else 'PASS'}")
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
