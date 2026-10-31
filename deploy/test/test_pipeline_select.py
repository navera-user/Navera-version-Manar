"""navera_tools/pipeline_select.py: the automatic day / night / celestial choice."""
import datetime as dt
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, '..', '..', 'navera_tools', name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = load('pipeline_select')


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
    assert P.choose(-20, cams(day=True, star=True))[0] == 'cn'               # dark, star camera
    assert P.choose(-20, cams(day=True, thermal=True, star=True))[0] == 'night'
    assert P.choose(-20, cams(day=True))[0] == 'day'                         # best effort
    assert P.choose(None, cams())[0] == 'day'                                # nothing plugged in, sun unknown
    assert P.choose(-30, cams())[0] == 'night'                               # night: by the time alone
    assert P.choose(30, cams())[0] == 'day'
    assert P.choose(40, cams(day=True), 'cn')[0] == 'cn'


def test_camera_roles(tmp_path):
    assert P.cameras({}, {'NAVERA_CAMERA_INPUT': 'usb'}) == cams()           # discovery: "NO camera found"
    assert P.cameras({}, {'NAVERA_CAMERA_INPUT': 'insta360'}) == cams(day=True)   # the kit: no sky pipeline
    assert P.cameras({'NAVERA_CAMERA_INPUT': 'csi'}, {}) == cams(day=True)   # chosen by a person, default device
    assert P.cameras({'NAVERA_THERMAL_CAMERA_INPUT': 'gst'}, {}) == cams(thermal=True)
    assert P.cameras({}, {'NAVERA_CAMERA_GST_PIPELINE': 'rtspsrc ...', 'NAVERA_STAR_CAMERA_TOPIC': '/sky'}) == \
        cams(day=True, star=True)
    dev = tmp_path / 'video9'
    dev.write_text('')
    assert P.cameras({}, {'NAVERA_THERMAL_CAMERA_DEVICE': str(dev)}) == cams(thermal=True)   # present
    assert P.cameras({}, {'NAVERA_THERMAL_CAMERA_DEVICE': '/dev/video_unplugged_99'}) == cams()


def test_env_files_later_win(tmp_path):
    a, b = tmp_path / 'a.env', tmp_path / 'b.env'
    a.write_text('NAVERA_PIPELINE_MODE=night\nX=1\n')
    b.write_text('# comment\nNAVERA_PIPELINE_MODE="auto"\n')
    assert P.read_env((str(a), str(b))) == {'NAVERA_PIPELINE_MODE': 'auto', 'X': '1'}


def test_corrupt_or_old_state_file_never_crashes(tmp_path, monkeypatch):
    st = tmp_path / 'pipeline.json'
    monkeypatch.setattr(P, 'STATE', str(st))
    for text in ('{"lat": 35.8}', 'null', '[1]', '{"lat": 999, "lon": 10, "pos_time": 1e12}', 'junk'):
        st.write_text(text)
        assert P.stored_position() == (None, 0.0)
    now = P.time.time()
    st.write_text(json.dumps({'lat': 35.8, 'lon': 10.6, 'pos_time': now}))
    assert P.stored_position() == ((35.8, 10.6), now)
    st.write_text(json.dumps({'lat': 35.8, 'lon': 10.6, 'pos_time': now - 30 * 86400}))
    assert P.stored_position() == (None, 0.0)                                # a month old: not trusted


class Box:
    """Fake systemd: which pipelines run, and which ones fail to start."""

    def __init__(self, active, broken=()):
        self.active, self.broken, self.calls = set(active), set(broken), []

    def run(self, cmd, **kw):
        self.calls.append(cmd)
        unit = cmd[-1]
        name = next((n for n, u in P.UNITS.items() if u == unit), None)
        rc = 0
        if cmd[1] == 'is-active':
            rc = 0 if name in self.active else 3
        elif cmd[1] == 'start' and name:
            if name not in self.broken:
                self.active.add(name)
        elif cmd[1] == 'stop' and name:
            self.active.discard(name)
        return type('R', (), {'returncode': rc})()


def run_once(monkeypatch, tmp_path, box, want, flying=False):
    monkeypatch.setattr(P.subprocess, 'run', box.run)
    monkeypatch.setattr(P.time, 'sleep', lambda s: None)
    monkeypatch.setattr(P, 'STATE', str(tmp_path / 'p.json'))
    monkeypatch.setattr(P, 'ACTIVE_ENV', str(tmp_path / 'p.env'))
    monkeypatch.setattr(P, 'WRITTEN_ENV', (str(tmp_path / 'none.env'),))
    monkeypatch.setattr(P, 'FOUND_ENV', str(tmp_path / 'none2.env'))
    monkeypatch.setattr(P, 'position', lambda port: None)
    monkeypatch.setattr(P, 'flying', lambda port: flying)
    monkeypatch.setattr(P, 'choose', lambda sun, cams, forced: (want, 'test'))
    P.main(['--once'])
    return json.loads((tmp_path / 'p.json').read_text())


def test_failed_start_falls_back_to_the_previous_pipeline(monkeypatch, tmp_path):
    box = Box({'day'}, broken={'night'})
    st = run_once(monkeypatch, tmp_path, box, 'night')
    assert box.active == {'day'} and st['pipeline'] == 'day'                 # the truth, not 'night'
    assert (tmp_path / 'p.env').read_text().endswith('NAVERA_PIPELINE_ACTIVE=day\n')


def test_switch_and_web_page_follows(monkeypatch, tmp_path):
    box = Box({'day'})
    st = run_once(monkeypatch, tmp_path, box, 'night')
    assert box.active == {'night'} and st['pipeline'] == 'night'
    assert ['systemctl', 'try-restart', P.WEB_UNIT] in box.calls


def test_no_switch_in_flight(monkeypatch, tmp_path):
    box = Box({'day'})
    st = run_once(monkeypatch, tmp_path, box, 'night', flying=True)
    assert box.active == {'day'} and st['waiting']


def test_a_second_pipeline_left_running_is_stopped(monkeypatch, tmp_path):
    box = Box({'day', 'cn'})
    run_once(monkeypatch, tmp_path, box, 'day')
    assert box.active == {'day'}


def test_check_boot_skips_the_pipeline_the_automatic_choice_stopped(tmp_path, monkeypatch):
    cb = load('check_boot')
    st = tmp_path / 'pipeline.json'
    st.write_text('{"pipeline": "night"}')
    monkeypatch.setattr(cb, 'PIPELINE_STATE', str(st))
    monkeypatch.setattr(cb.subprocess, 'run', lambda *a, **k: type('R', (), {'returncode': 0})())
    p = {'LoadState': 'loaded', 'UnitFileState': 'enabled', 'ActiveState': 'inactive', 'SubState': 'dead'}
    assert cb.check('navera-pipeline-day.service', p, p, set())[0] == 'SKIP'
    st.write_text('{"pipeline": "day"}')
    assert cb.check('navera-pipeline-day.service', p, p, set())[0] == 'FAIL'      # it should run: a real failure
    st.write_text('{"pipeline": "night"}')
    monkeypatch.setattr(cb.subprocess, 'run', lambda *a, **k: type('R', (), {'returncode': 3})())
    assert cb.check('navera-pipeline-day.service', p, p, set())[0] == 'FAIL'      # choice not running: stale file


def test_map_centre(tmp_path):
    import sqlite3
    f = tmp_path / 'm.mbtiles'
    con = sqlite3.connect(f)
    con.execute('CREATE TABLE metadata (name TEXT, value TEXT)')
    con.execute("INSERT INTO metadata VALUES ('bounds', '10.0,35.0,11.0,36.0')")
    con.commit()
    con.close()
    assert P.map_centre(str(f)) == (35.5, 10.5)
    assert P.map_centre(str(tmp_path / 'missing.mbtiles')) is None
