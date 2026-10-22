"""B4 / B14: the night replay set's labels (camera_pkg/camera_pkg/data) match the places the frames show.

The thermal/ frames are day photos made grey (a day-derived stand-in, not thermal imagery);
thermal frame k is day frame k + 8 (cyclic). Every frame was located on the map
(truth_from_map.csv, 2026-10-20); this keeps the labels from drifting back.
"""
import csv
import math
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "camera_pkg" / "camera_pkg" / "data"


def _rows(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def _m(a_lat, a_lon, b_lat, b_lon):
    return math.hypot((a_lat - b_lat) * 111_320.0,
                      (a_lon - b_lon) * 111_320.0 * math.cos(math.radians(a_lat)))


pytestmark = pytest.mark.skipif(not (DATA / "truth_from_map.csv").exists(), reason="no replay labels")


def test_thermal_labels_are_where_the_map_puts_the_frames():
    truth = {int(r["thermal_frame"]): r for r in _rows(DATA / "truth_from_map.csv")}
    checked = 0
    for r in _rows(DATA / "thermal" / "flight_ready.csv"):
        t = truth[int(r["frame_id"])]
        assert r["heading_deg"] not in ("", "0")                     # B14: every heading was 0
        if t["accepted"] != "1":
            continue
        d = ((float(r["heading_deg"]) - float(t["map_rotation_deg"]) + 180.0) % 360.0) - 180.0
        assert abs(d) < 3.0, (r["frame_id"], d)
        if r["lat"]:
            assert _m(float(r["lat"]), float(r["lon"]), float(t["map_lat"]), float(t["map_lon"])) < 10.0
            checked += 1
    assert checked >= 20


def test_day_twin_carries_the_same_place():
    """Thermal frame k shows day frame k + 8: their labels must be the same place."""
    day = {int(r["frame_id"]): r for r in _rows(DATA / "day" / "flight_log.csv")}
    therm = _rows(DATA / "thermal" / "flight_ready.csv")
    n = len(therm)
    pairs = 0
    for r in therm:
        k = int(r["frame_id"])
        dr = day[(k + 8 - 1) % n + 1]
        if r["lat"] and dr["lat"]:
            assert _m(float(r["lat"]), float(r["lon"]), float(dr["lat"]), float(dr["lon"])) < 10.0
            pairs += 1
    assert pairs >= 15


def test_marked_as_a_day_derived_stand_in():
    text = (DATA / "README.md").read_text()
    assert "not thermal imagery" in text and "stand-in" in text
