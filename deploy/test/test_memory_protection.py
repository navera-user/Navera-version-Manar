"""The units protect NAVERA's critical processes from the OOM killer (F5 / H-11, NAV-PERF-06).

On the 8 GB Jetson the day pipeline peaked at 3.5 GB and was OOM-killed without swap (F5). Each
unit has a memory class: the small units the output to the vehicle depends on are taken last by
the kernel OOM killer and never by systemd-oomd; the vision pipelines are protected but less;
the web page and the boot discovery are taken first and capped (MemoryHigh / MemoryMax).
"""
import glob
import os
import shutil
import subprocess
import sys

import pytest

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DEPLOY)
import verify_units   # noqa: E402

UNITS = {os.path.basename(p): verify_units.parse_unit(p)
         for p in glob.glob(os.path.join(DEPLOY, 'systemd', 'navera-*.service'))}


def _adj(name):
    return int(verify_units.values(UNITS[name], 'Service', 'OOMScoreAdjust')[0])


def test_every_unit_has_a_memory_class_and_passes_it():
    found = verify_units.memory_findings(UNITS)
    assert len(found) == len(UNITS) == 14           # navera-hotplug, navera-pipeline-select: non-critical; navera-insta360: pipeline
    assert [f for f in found if f[0] != 'PASS'] == []


def test_the_oom_killer_order_is_web_then_pipelines_then_the_output_chain():
    web, day = _adj('navera-web.service'), _adj('navera-pipeline-day.service')
    for crit in ('navera-estimator', 'navera-output', 'navera-gps', 'navera-vehicle-link'):
        assert _adj(crit + '.service') < day < 0 < web


def test_a_unit_without_a_class_or_with_a_weak_setting_fails():
    unit = {'Service': [('OOMScoreAdjust', '-100'), ('ManagedOOMPreference', 'omit')]}
    lv = dict((f[1], f[0]) for f in verify_units.memory_findings(
        {'navera-estimator.service': unit, 'navera-new-thing.service': unit,
         'navera-web.service': {'Service': [('OOMScoreAdjust', '500')]},          # no MemoryMax
         'navera-pipeline-day.service': {'Service': [('OOMScoreAdjust', '-900'),   # above the output chain
                                                     ('ManagedOOMPreference', 'avoid')]}}))
    assert lv == {'navera-estimator.service': 'FAIL', 'navera-new-thing.service': 'FAIL',
                  'navera-web.service': 'FAIL', 'navera-pipeline-day.service': 'FAIL'}


def test_stage_check_drops_only_the_negative_oom_adjustment_of_user_units():
    """A user manager cannot lower an OOM score (needs root): the staged copy leaves it out."""
    text = open(os.path.join(DEPLOY, 'stage_check.sh')).read()
    assert "-e '/^OOMScoreAdjust=-/d'" in text


@pytest.mark.skipif(not shutil.which('systemd-analyze'), reason='systemd absent')
def test_systemd_knows_the_memory_keys():
    """systemd-analyze verify flags unknown keys ("Unknown key name"): the memory keys are known."""
    r = subprocess.run([sys.executable, os.path.join(DEPLOY, 'verify_units.py')], capture_output=True, text=True,
                       timeout=120)
    assert 'Unknown key' not in r.stdout + r.stderr
    assert 'systemd-analyze verify' in r.stdout and 'FAIL  navera' not in r.stdout
