"""navera_tools/pipeline_select.py: the automatic day / night / celestial choice."""
import datetime as dt
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'pipeline_select', os.path.join(HERE, '..', '..', 'navera_tools', 'pipeline_select.py'))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def cams(**k):
    d = dict(day=False, thermal=False, star=False)
    d.update(k)
    return d


def test_sun_elevation_sousse():
    utc = dt.timezone.utc
    assert P.sun_elevation(35.83, 10.63, dt.datetime(2026, 10, 31, 11, 30, tzinfo=utc)) > 35     # midday
    assert -4 < P.sun_elevation(35.83, 10.63, dt.datetime(2026, 10, 31, 16, 30, tzinfo=utc)) < 0  # sunset
    assert P.sun_elevation(35.83, 10.63, dt.datetime(2026, 10, 31, 23, 30, tzinfo=utc)) < -50    # midnight


def test_rules():
    assert P.choose(40, cams(day=True, thermal=True))[0] == 'day'
    assert P.choose(40, cams(thermal=True))[0] == 'night'
    assert P.choose(-8, cams(day=True, thermal=True))[0] == 'night'          # twilight: thermal
    assert P.choose(-8, cams(day=True, star=True))[0] == 'day'               # twilight: no stars yet
    assert P.choose(-20, cams(day=True, star=True))[0] == 'cn'               # dark, sky view
    assert P.choose(-20, cams(day=True, thermal=True, star=True))[0] == 'night'
    assert P.choose(-20, cams(day=True))[0] == 'day'                         # best effort
    assert P.choose(None, cams())[0] == 'day'                                # nothing plugged in
    assert P.choose(40, cams(day=True), 'cn') == ('cn', 'forced in the settings (NAVERA_PIPELINE=cn)')


def test_camera_roles_from_settings():
    assert P.cameras({'NAVERA_CAMERA_INPUT': 'usb'}) == cams()               # "NO camera found"
    assert P.cameras({'NAVERA_CAMERA_INPUT': 'insta360'}) == cams(day=True, star=True)
    assert P.cameras({'NAVERA_CAMERA_DEVICE': '/dev/video0',
                      'NAVERA_THERMAL_CAMERA_NAME': 'Hikvision'}) == cams(day=True, thermal=True)
    assert P.cameras({'NAVERA_STAR_CAMERA_TOPIC': '/sky'}) == cams(star=True)


def test_env_files_later_win(tmp_path):
    a, b = tmp_path / 'a.env', tmp_path / 'b.env'
    a.write_text('NAVERA_PIPELINE=night\nX=1\n')
    b.write_text('# comment\nNAVERA_PIPELINE="auto"\n')
    assert P.read_env((str(a), str(b))) == {'NAVERA_PIPELINE': 'auto', 'X': '1'}


def test_check_boot_skips_the_pipeline_the_automatic_choice_stopped(tmp_path, monkeypatch):
    spec2 = importlib.util.spec_from_file_location(
        'check_boot', os.path.join(HERE, '..', '..', 'navera_tools', 'check_boot.py'))
    cb = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(cb)
    st = tmp_path / 'pipeline.json'
    st.write_text('{"pipeline": "night"}')
    monkeypatch.setattr(cb, 'PIPELINE_STATE', str(st))
    p = {'LoadState': 'loaded', 'UnitFileState': 'enabled', 'ActiveState': 'inactive', 'SubState': 'dead'}
    assert cb.check('navera-pipeline-day.service', p, p, set())[0] == 'SKIP'
    st.write_text('{"pipeline": "day"}')
    assert cb.check('navera-pipeline-day.service', p, p, set())[0] == 'FAIL'      # it should run: a real failure
