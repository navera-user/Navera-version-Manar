"""Power cut while a state file was written: every reader of NAVERA's saved state must still start.

The writers are atomic (navera_common.atomic_io: temp + fsync + rename), but a damaged card or an
older install can still leave a truncated, zero-filled or garbage file. Each reader is fed every
damaged form of a real file and must return "nothing saved" (or its good part) without raising:
a reader that raises at start would put its unit in a restart loop for as long as the file lives.
The staged equivalent (every unit starting on damaged files) is deploy/stage_check.sh --corrupt-state.
"""
import json
import math
import time

import pytest

from navera_common import atomic_io, hotplug, state_store
from navera_common.altitude import AltitudeEstimator
from navera_common.geo import is_finite_latlon


def damaged_forms(good: bytes):
    """Truncations of the good file, zero fill (ext4 after a cut in an unsynced write), garbage."""
    cuts = sorted({1, len(good) // 3, len(good) // 2, len(good) - 1})
    forms = [good[:c] for c in cuts if 0 < c < len(good)]
    return forms + [b"", b"\x00" * len(good), good[:len(good) // 2] + b"\x00" * 32,
                    b"\xff\xfe\x80garbage", b"null", b"[]", b'"text"', b"42"]


def wrong_types(record: dict):
    """The same record with each field replaced by a wrong value, plus each field missing."""
    for k in record:
        if k == "saved_at":
            continue
        for bad in ("x", None, [], {}, float("nan"), [1, "a"], 1e308):
            yield dict(record, **{k: bad})
        yield {kk: v for kk, v in record.items() if kk != k}


# ── state_store records, as their writers save them ─────────────────────────────────────────
def _held(now):
    return {"lat": 36.8, "lon": 10.2, "sigma_h_m": 12.0, "t_wall": now - 1, "ground_vel": [1.0, 2.0, 0.0],
            "sent_vel": [1.0, 2.0, 0.0], "saved_at": now}


def _track(now):
    return {"pts": [[now - 2, 36.8, 10.2, 5.0], [now - 1, 36.80001, 10.2, 5.0]], "carry": None,
            "anchor": None, "headings": [[now - 1, 90.0]], "vel_epoch": now - 2, "track_heading": 90.0,
            "last_measured": now - 1, "snap": None, "saved_at": now}


def read_held(d):
    from navera_output.nodes.vehicle_output_node import held_from_state
    return held_from_state(d, time.monotonic(), time.time(), 30.0)


def read_track(d):
    from day_pkg.carry_state import restore_track
    return restore_track(d, time.time(), 60.0)


def read_anchor(d):            # day_subscriber.__init__ (inline there): reuse only a finite position
    if d is not None and is_finite_latlon(d.get("lat"), d.get("lon")):
        return float(d["lat"]), float(d["lon"]), float(d["saved_at"])
    return None


def read_ground(d):            # live_camera: AltitudeEstimator(saved_ground=...) then a GPS fix
    a = AltitudeEstimator(saved_ground=d)
    a.add_gps(time.monotonic(), 100.0, 36.8, 10.2)
    assert a.ground is not None and math.isfinite(a.ground)
    return a.ground


READERS = {
    "output_held": (_held, read_held),
    "day_track": (_track, read_track),
    "day_anchor": (lambda now: {"lat": 36.8, "lon": 10.2, "saved_at": now}, read_anchor),
    "ground": (lambda now: {"altitude_m": 12.0, "lat": 36.8, "lon": 10.2, "saved_at": now}, read_ground),
}


@pytest.mark.parametrize("name", sorted(READERS))
def test_state_readers_survive_damaged_files(tmp_path, name):
    make, read = READERS[name]
    good = json.dumps(make(time.time())).encode()
    read(state_store.load(name, 3600.0, str(tmp_path)))            # nothing saved yet
    path = tmp_path / f"{name}.json"
    for form in damaged_forms(good):
        path.write_bytes(form)
        read(state_store.load(name, 3600.0, str(tmp_path)))       # must not raise
    for rec in wrong_types(make(time.time())):
        path.write_text(json.dumps(rec))
        read(state_store.load(name, 3600.0, str(tmp_path)))
    path.write_bytes(good)                                         # and the good file still reads
    assert read(state_store.load(name, 3600.0, str(tmp_path))) is not None


def test_fix_sigma_store_survives_damaged_files(tmp_path):
    from day_pkg import fix_sigma
    key = "cam1"
    path = tmp_path / f"{fix_sigma._store_name(key)}.json"
    good = json.dumps({"key": key, "terms": {"f": 1.0, "b": 2.0, "samples": 3}, "saved_at": time.time()}).encode()
    for form in damaged_forms(good) + [json.dumps({"key": key, "terms": {"f": "x"}, "saved_at": 1}).encode()]:
        path.write_bytes(form)
        assert fix_sigma.load_stored(key, 3600.0, str(tmp_path)) is None
    path.write_bytes(good)
    assert fix_sigma.load_stored(key, 3600.0, str(tmp_path))["f"] == 1.0


def test_state_store_save_is_atomic_and_never_raises(tmp_path):
    assert state_store.save("x", {"a": 1}, str(tmp_path))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.json"]
    assert not state_store.save("y", {"a": object()}, str(tmp_path))    # not serialisable: False
    assert not state_store.save("z", {"a": 1}, str(tmp_path / "x.json"))  # not a directory: False


def test_hotplug_survives_a_damaged_discovery_report(tmp_path):
    good = json.dumps({"found": {"serial": []}, "settings": {"A": "1"}, "report": [], "idle": []}).encode()
    for form in damaged_forms(good):
        jp, ep = tmp_path / "discovery.json", tmp_path / "discovered.env"
        jp.write_bytes(form)
        hotplug.run({}, str(jp), str(ep), lambda: None, interval_s=0, rescan_s=1e9, log=lambda s: None, passes=1)


def test_web_settings_and_missions_survive_damaged_files(tmp_path):
    from simulation_web import mission_prep
    sp = tmp_path / "settings.env"
    for form in damaged_forms(b"NAVERA_MAX_SPEED_KMH=80\nNAVERA_PIPELINE=day\n"):
        sp.write_bytes(form)
        assert isinstance(mission_prep.read_settings(str(sp)), dict)
    sp.write_bytes(b"NAVERA_MAX_SPEED_KMH=80\n\x00\x00\x00")
    assert mission_prep.read_settings(str(sp)).get("NAVERA_MAX_SPEED_KMH") == "80"   # good lines kept
    jobs = mission_prep.AreaJobs(str(tmp_path), str(tmp_path / "none.mbtiles"))
    mf = jobs._missions_file()
    good = json.dumps([{"name": "m", "route": [[36.8, 10.2], [36.9, 10.3]]}]).encode()
    for form in damaged_forms(good) + [b'[1, "x", {"name": "ok"}]']:
        with open(mf, "wb") as f:
            f.write(form)
        assert all(isinstance(m, dict) for m in jobs.missions())
        jobs.save_mission("new", [[36.8, 10.2], [36.9, 10.3]])     # a damaged list is replaced
        assert jobs.missions()[0]["name"] == "new"


def test_boot_moves_a_damaged_env_file_aside(tmp_path):
    p = tmp_path / "settings.env"
    good = b"NAVERA_BOX_IMU=0\nNAVERA_BOX_RTC=0\n"
    for form in damaged_forms(good):
        whole_lines = form == b"" or (good.startswith(form) and form.endswith(b"\n"))   # a cut at a line end
        p.write_bytes(form)
        assert atomic_io.quarantine_damaged_env(str(p), log=lambda s: None) == (not whole_lines), form
        assert p.exists() == whole_lines
    p.write_bytes(b"NAVERA_BOX_IMU=0\n")
    assert not atomic_io.quarantine_damaged_env(str(p), log=lambda s: None) and p.exists()
