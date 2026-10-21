#!/usr/bin/env python3
"""verify_units.py — static checks of the NAVERA boot units, without root and without a deployed box.

    deploy/verify_units.py                       # check deploy/systemd against this repository
    deploy/verify_units.py --root /tmp/stage     # check a staged install (deploy/install.sh --root)
    deploy/verify_units.py --root /              # check the real install on a box (no root needed)

Changes nothing outside a temporary directory. For every deploy/systemd/navera-*.service:

    systemd-analyze  `systemd-analyze verify` on a copy whose /home/navera paths point into the
                     staged root (or this repository's deploy/systemd): unit syntax, ExecStart
                     executable, dependencies known
    paths            ExecStart / WorkingDirectory exist (staged root), EnvironmentFile entries are
                     optional ("-") or exist
    wrapper          the boot wrapper parses (bash -n) and sources navera_boot_lib.sh
    launch / run     every `ros2 launch <pkg> <file>` / `ros2 run <pkg> <exe>` in the wrapper
                     exists in the build (staged root: install/; else the package sources)
    env              every NAVERA_* variable a wrapper reads is documented in navera.env.example
                     (or is one of the internal ones below)
    enabled          (--root) the units --units names are enabled in the staged root
    conflicts        the day and night pipelines conflict with each other (one GPU pipeline)
    sudoers          visudo -c -f deploy/sudoers/navera-web; every unit it may restart exists

Exit 0 = no FAIL. WARN lines are reported but do not fail the check.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = '/home/navera/isaac_ros_common'
HOME = '/home/navera'
# set by systemd / the wrappers themselves, or deliberately left out of the example
INTERNAL_VARS = {'NAVERA_WS', 'NAVERA_BOX_IMU', 'NAVERA_BOX_IMU_BUS', 'NAVERA_BOX_IMU_ADDR',
                 'NAVERA_BOX_RTC', 'NAVERA_BOX_RTC_BUS'}   # written by navera-discover (discovered.env)
DEFAULT_UNITS = ('navera-discover navera-estimator navera-gps navera-imu navera-rtc navera-vehicle-link '
                 'navera-pipeline-day navera-output navera-web')

results = []


def report(level, unit, what, detail=''):
    """Record and print one check result."""
    results.append((level, unit, what, detail))
    print(f'{level:<4}  {unit:<30} {what}' + (f' — {detail}' if detail else ''))


def parse_unit(path):
    """Return {section: [(key, value), ...]} of a unit file (repeated keys kept in order)."""
    sec, out = None, {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('#', ';')):
                continue
            if line.startswith('[') and line.endswith(']'):
                sec = line[1:-1]
                out.setdefault(sec, [])
            elif '=' in line and sec:
                k, v = line.split('=', 1)
                out[sec].append((k.strip(), v.strip()))
    return out


def values(unit, sec, key):
    """All values of `key` in section `sec`."""
    return [v for k, v in unit.get(sec, []) if k == key]


def staged(path, root):
    """Where an absolute target path lives for this check."""
    if root:
        return root + path
    if path.startswith(HOME + '/navera_boot_'):          # wrappers: from the repository
        return os.path.join(REPO, 'deploy', 'systemd', os.path.basename(path))
    if path.startswith(WS):
        return REPO + path[len(WS):]
    return path


def documented_vars():
    """NAVERA_* names in deploy/navera.env.example (set or commented out)."""
    with open(os.path.join(REPO, 'deploy', 'navera.env.example')) as f:
        return set(re.findall(r'^#?\s*(NAVERA_[A-Z0-9_]+)=', f.read(), re.M))


def package_dirs():
    """{package name: source directory} for the NAVERA packages of this repository."""
    out = {}
    for px in glob.glob(os.path.join(REPO, '*', 'package.xml')):
        d = os.path.dirname(px)
        if os.path.exists(os.path.join(d, 'COLCON_IGNORE')):
            continue
        m = re.search(r'<name>\s*([^<\s]+)\s*</name>', open(px).read())
        if m:
            out[m.group(1)] = d
    return out


def launch_exists(pkg, fname, root, pkgs):
    """True when `ros2 launch pkg fname` can find the file."""
    if root:
        return os.path.isfile(os.path.join(root + WS, 'install', pkg, 'share', pkg, 'launch', fname))
    d = pkgs.get(pkg)
    return bool(d) and any(os.path.basename(p) == fname for p in glob.glob(os.path.join(d, '**', fname),
                                                                           recursive=True))


def exe_exists(pkg, exe, root, pkgs):
    """True when `ros2 run pkg exe` can find the executable."""
    if root:
        return os.path.isfile(os.path.join(root + WS, 'install', pkg, 'lib', pkg, exe))
    d = pkgs.get(pkg)
    return bool(d) and bool(glob.glob(os.path.join(d, '**', exe), recursive=True))


def check_wrapper(unit_name, path, root, pkgs, docvars):
    """bash -n, the shared library, launch files / executables and settings of one wrapper."""
    if not os.path.isfile(path):
        report('FAIL', unit_name, 'wrapper missing', path)
        return
    r = subprocess.run(['bash', '-n', path], capture_output=True, text=True)
    report('PASS' if r.returncode == 0 else 'FAIL', unit_name, 'wrapper parses (bash -n)',
           r.stderr.strip()[:200])
    text = open(path).read()
    if 'navera_boot_lib.sh' in text:
        lib = os.path.join(os.path.dirname(path), 'navera_boot_lib.sh')
        report('PASS' if os.path.isfile(lib) else 'FAIL', unit_name, 'navera_boot_lib.sh next to it', lib)
    joined = re.sub(r'\\\n\s*', ' ', text)
    for pkg, fname in re.findall(r'ros2 launch\s+([a-z_]+)\s+([\w.]+\.py)', joined):
        ok = launch_exists(pkg, fname, root, pkgs)
        report('PASS' if ok else 'FAIL', unit_name, f'launch file {pkg}/{fname}')
    for pkg, exe in re.findall(r'ros2 run\s+([a-z_]+)\s+([\w.]+)', joined):
        ok = exe_exists(pkg, exe, root, pkgs)
        report('PASS' if ok else 'FAIL', unit_name, f'executable {pkg}/{exe}')
    used = set(re.findall(r'\$\{?(NAVERA_[A-Z0-9_]+)', text))
    missing = sorted(used - docvars - INTERNAL_VARS)
    report('WARN' if missing else 'PASS', unit_name, 'settings it reads are in navera.env.example',
           ('undocumented: ' + ', '.join(missing)) if missing else f'{len(used)} variable(s)')


def systemd_verify(unit_files, root, tmp):
    """systemd-analyze verify on copies whose /home/navera paths resolve in this check."""
    copies = []
    for path in unit_files:
        text = open(path).read()
        if root:
            text = text.replace(HOME + '/', root + HOME + '/')
        else:
            text = text.replace(WS, REPO)
            text = re.sub(re.escape(HOME) + r'/(navera_boot_\w+\.sh)',
                          lambda m: os.path.join(REPO, 'deploy', 'systemd', m.group(1)), text)
        dst = os.path.join(tmp, os.path.basename(path))
        with open(dst, 'w') as f:
            f.write(text)
        copies.append(dst)
    r = subprocess.run(['systemd-analyze', 'verify', '--man=no'] + copies, capture_output=True, text=True,
                       cwd=tmp)
    ours = [ln for ln in (r.stdout + r.stderr).splitlines()
            if 'navera' in ln and not ln.startswith(('/lib/systemd/', '/etc/systemd/', '/usr/lib/systemd/'))]
    # User=navera does not exist on a test machine: not a unit error
    ours = [ln for ln in ours if not re.search(r"Failed to resolve (user|group)|getpwnam|User=", ln)]
    for path in unit_files:
        name = os.path.basename(path)
        mine = [ln for ln in ours if name in ln]
        report('FAIL' if mine else 'PASS', name, 'systemd-analyze verify', '; '.join(mine)[:300])
    return r.returncode


def main(argv=None):
    """Run every check; return 0 when none FAILs."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', help='staged install root (deploy/install.sh --root)')
    ap.add_argument('--units', default=DEFAULT_UNITS, help='units expected enabled in the staged root')
    args = ap.parse_args(argv)
    root = os.path.realpath(args.root) if args.root else None
    if root and not os.path.isdir(root + WS):
        how = 'sudo deploy/install.sh' if root == '/' else f'deploy/install.sh --root {root}'
        print(f'{WS} not found under {root}: run {how} first', file=sys.stderr)
        return 2
    unit_files = sorted(glob.glob(os.path.join(root + '/etc/systemd/system' if root else
                                               os.path.join(REPO, 'deploy', 'systemd'), 'navera-*.service')))
    if not unit_files:
        print('no navera-*.service found', file=sys.stderr)
        return 2
    print(f'NAVERA unit check — {"staged root " + root if root else "repository " + REPO}; '
          f'{len(unit_files)} unit(s)\n')
    pkgs, docvars = package_dirs(), documented_vars()
    tmp = tempfile.mkdtemp(prefix='navera_verify_')
    try:
        systemd_verify(unit_files, root, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for path in unit_files:
        name = os.path.basename(path)
        u = parse_unit(path)
        for key in ('Type', 'User', 'ExecStart', 'WorkingDirectory'):
            if key in ('Type',) or values(u, 'Service', key):
                continue
            report('FAIL', name, f'[Service] {key} missing')
        for ex in values(u, 'Service', 'ExecStart'):
            exe = ex.lstrip('-@+!:').split()[0]
            p = staged(exe, root)
            ok = os.path.isfile(p) and os.access(p, os.X_OK)
            report('PASS' if ok else 'FAIL', name, 'ExecStart exists and is executable', p)
            check_wrapper(name, p, root, pkgs, docvars)
        for wd in values(u, 'Service', 'WorkingDirectory'):
            p = staged(wd, root)
            report('PASS' if os.path.isdir(p) else 'FAIL', name, 'WorkingDirectory exists', p)
        for ef in values(u, 'Service', 'EnvironmentFile'):
            optional = ef.startswith('-')
            p = staged(ef.lstrip('-'), root) if root else ef.lstrip('-')
            if os.path.exists(p):
                report('PASS', name, 'EnvironmentFile present', p)
            else:
                report('PASS' if optional else 'FAIL', name,
                       'EnvironmentFile ' + ('optional, absent here' if optional else 'MISSING'), p)
        if values(u, 'Service', 'Type') != ['oneshot']:
            rs = values(u, 'Service', 'Restart')
            report('PASS' if rs == ['always'] else 'FAIL', name, 'Restart=always (ros2 launch exits 0 on a crash)',
                   ','.join(rs))
            lim = values(u, 'Unit', 'StartLimitIntervalSec')
            report('PASS' if lim == ['0'] else 'WARN', name, 'StartLimitIntervalSec=0 (never gives up)',
                   ','.join(lim) or 'default (5 starts / 10 s)')
        wb = values(u, 'Install', 'WantedBy')
        report('PASS' if 'multi-user.target' in wb else 'FAIL', name, 'WantedBy=multi-user.target', ','.join(wb))
        if root and name[:-len('.service')] in args.units.split():
            link = os.path.join(root, 'etc/systemd/system/multi-user.target.wants', name)
            report('PASS' if os.path.islink(link) else 'FAIL', name, 'enabled in the staged root', link)

    by = {os.path.basename(p): parse_unit(p) for p in unit_files}
    day, night = by.get('navera-pipeline-day.service'), by.get('navera-pipeline-night.service')
    if day and night:
        ok = ('navera-pipeline-night.service' in ' '.join(values(day, 'Unit', 'Conflicts'))
              and 'navera-pipeline-day.service' in ' '.join(values(night, 'Unit', 'Conflicts')))
        report('PASS' if ok else 'FAIL', 'pipelines', 'day and night conflict (one GPU pipeline)')

    sud = os.path.join(root + '/etc/sudoers.d' if root else os.path.join(REPO, 'deploy', 'sudoers'), 'navera-web')
    if os.path.isfile(sud):
        r = subprocess.run(['visudo', '-c', '-q', '-f', sud], capture_output=True, text=True)
        report('PASS' if r.returncode == 0 else 'FAIL', 'sudoers/navera-web', 'visudo -c -f', r.stderr.strip()[:200])
        text = open(sud).read()
        for unit in sorted(set(re.findall(r'(navera-[\w-]+\.service)', text))):
            report('PASS' if unit in by else 'FAIL', 'sudoers/navera-web', f'may restart {unit}: unit exists')
        if root:
            mode = oct(os.stat(sud).st_mode & 0o777)
            report('PASS' if mode == '0o440' else 'FAIL', 'sudoers/navera-web', 'mode 0440', mode)
    else:
        report('FAIL', 'sudoers/navera-web', 'file missing', sud)

    n = {lv: sum(r[0] == lv for r in results) for lv in ('PASS', 'WARN', 'FAIL')}
    print(f"\n{n['PASS']} PASS, {n['WARN']} WARN, {n['FAIL']} FAIL — unit check: {'FAIL' if n['FAIL'] else 'PASS'}")
    return 1 if n['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
