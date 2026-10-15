"""The field test's saved folder, the phone attitude and the report with its problems."""
import json
import os

import pytest

from navera_tools.field import analyze as an
from navera_tools.field import attitude
from navera_tools.field.store import FieldSession, list_sessions, read_jsonl


def test_phone_flat_points_at_the_zenith():
    alt, az, off = attitude.boresight(0.0, 0.0, 120.0)
    assert (round(alt, 6), round(off, 6)) == (90.0, 0.0)


def test_tilt_direction_follows_the_heading():
    # beta > 0 raises the phone's top edge... the axis leans towards the phone's bottom edge (south of its heading)
    alt, az, off = attitude.boresight(10.0, 0.0, 0.0)
    assert round(off, 3) == 10.0 and round(alt, 3) == 80.0
    assert abs(az - 180.0) < 1e-6
    _, az2, _ = attitude.boresight(10.0, 0.0, 90.0)          # phone's top towards east
    assert abs(az2 - 270.0) < 1e-6
    _, az3, _ = attitude.boresight(0.0, 10.0, 0.0)           # gamma > 0 leans towards the right edge
    assert abs(az3 - 90.0) < 1e-6


def test_heading_prefers_gps_course_when_moving():
    assert attitude.best_heading(200.0, 10.0, 90.0) == (200.0, "gps course")
    assert attitude.best_heading(200.0, 0.5, 90.0) == (90.0, "phone compass")
    assert attitude.best_heading(None, None, None) == (None, "none")


def test_session_files_survive_and_a_cut_line_is_dropped(tmp_path):
    s = FieldSession(str(tmp_path), {"operator": "x"})
    s.log("phone", {"lat": 35.8, "lon": 10.6})
    s.event("note", text="rain")
    s.close()
    p = os.path.join(s.dir, "phone.jsonl")
    with open(p, "a") as f:
        f.write('{"t": 1, "lat"')                            # power cut in the middle of a line
    assert len(read_jsonl(p)) == 1
    assert list_sessions(str(tmp_path))[0]["operator"] == "x"
    assert FieldSession(str(tmp_path)).id != s.id          # two tests in one minute do not share a folder


def _write(folder, phone, frames, meta=None):
    os.makedirs(folder, exist_ok=True)
    for name, rows in (("phone", phone), ("frames", frames)):
        with open(os.path.join(folder, name + ".jsonl"), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
    with open(os.path.join(folder, "session.json"), "w") as f:
        json.dump({"id": "t", **(meta or {})}, f)


def _good(i, lat_err=0.2):
    return {"t": 1000 + i * 10, "idx": i, "confirmed": 20, "sky": "clear", "solved": True,
            "lat": 35.8 + lat_err, "lon": 10.6, "sigma_km": 55, "off_vertical_deg": 0.3}


def test_good_test_is_ok_and_error_is_measured(tmp_path):
    phone = [{"t": 1000 + i * 2, "lat": 35.8, "lon": 10.6, "acc": 5} for i in range(300)]
    _write(str(tmp_path), phone, [_good(i) for i in range(20)])
    r = an.analyze(str(tmp_path))
    assert r["verdict"] == "OK"
    assert abs(r["err_km"]["median"] - 22.2) < 0.5              # 0.2 degree of latitude
    assert r["problems"] == []


def test_problems_are_named_with_causes(tmp_path):
    phone = [{"t": 1000 + i * 2, "lat": 35.8, "lon": 10.6, "acc": 60} for i in range(300)]
    frames = [dict(_good(i), confirmed=5, sky="cloudy", off_vertical_deg=3.0, solved=(i % 5 == 0),
                   why="too few stars") for i in range(20)]
    _write(str(tmp_path), phone, frames, {"clock_offset_s": 1.2})
    r = an.analyze(str(tmp_path))
    ids = {p["id"] for p in r["problems"]}
    assert {"few_stars", "sky_not_clear", "not_level", "clock_offset", "phone_gps_poor"} <= ids
    assert r["verdict"] == "PARTLY"
    assert r["problems"][0]["severity"] == "bad"


def test_no_phone_gps_and_no_fix(tmp_path):
    frames = [dict(_good(i), solved=False) for i in range(12)]
    _write(str(tmp_path), [], frames)
    r = an.analyze(str(tmp_path))
    assert r["verdict"] == "NO FIX"
    assert "no_truth" in {p["id"] for p in r["problems"]}


def test_report_files_are_written(tmp_path):
    _write(str(tmp_path), [], [_good(i) for i in range(3)])
    an.write_report(str(tmp_path))
    assert os.path.exists(tmp_path / "report.json") and os.path.exists(tmp_path / "report.md")
    assert an.analyze(str(tmp_path))["verdict"] == "NO DATA"


def test_a_room_instead_of_sky_is_named_as_such(tmp_path):
    phone = [{"t": 1000 + i * 2, "lat": 35.8, "lon": 10.6, "acc": 5} for i in range(300)]
    frames = [dict(_good(i), confirmed=0, sky="blocked", solved=False, why="too few stars (0)") for i in range(20)]
    _write(str(tmp_path), phone, frames)
    ids = [p["id"] for p in an.analyze(str(tmp_path))["problems"]]
    assert ids[0] == "not_looking_at_sky"
    assert "few_stars" not in ids             # the cause is named once, not twice


def test_late_phone_samples_fill_the_gap_in_the_truth(tmp_path):
    from navera_tools.field.server import Field
    f = Field.__new__(Field)                       # only the batch path is under test
    f.session = FieldSession(str(tmp_path))
    f.offsets = []
    import threading
    f.lock = threading.Lock()
    items = [{"phone_t_ms": (1000 + i) * 1000, "lat": 35.8, "lon": 10.6, "acc": 5} for i in range(5)]
    assert f.on_phone_batch(items + [{"lat": 1}]) == 5          # a sample without its time is refused
    rows = read_jsonl(os.path.join(f.session.dir, "phone.jsonl"))
    assert [r["t"] for r in rows] == [1000.0 + i for i in range(5)] and all(r["late"] for r in rows)
