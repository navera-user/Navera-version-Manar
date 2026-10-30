"""Mission preparation on the box: settings file, mission files, map jobs (no ROS)."""
import json
import os
import sqlite3
import sys
import time

import pytest

from simulation_web import mission_prep as mp

WPL = """QGC WPL 110
0\t1\t0\t16\t0\t0\t0\t0\t35.825600\t10.638500\t10.0\t1
1\t0\t3\t22\t0\t0\t0\t0\t35.825600\t10.638500\t100.0\t1
2\t0\t3\t16\t0\t0\t0\t0\t35.840000\t10.620000\t100.0\t1
3\t0\t3\t178\t0\t20\t-1\t0\t0\t0\t0\t1
4\t0\t3\t16\t0\t0\t0\t0\t35.856000\t10.601000\t100.0\t1
5\t0\t3\t20\t0\t0\t0\t0\t0\t0\t0\t1
"""

PLAN = {"fileType": "Plan", "version": 1, "mission": {
    "plannedHomePosition": [48.8534951, 2.3483915, 40],
    "items": [
        {"type": "SimpleItem", "command": 22, "params": [0, 0, 0, None, 48.8534951, 2.3483915, 50]},
        {"type": "SimpleItem", "command": 16, "params": [0, 0, 0, None, 48.0, 3.0, 300]},
        {"type": "SimpleItem", "command": 178, "params": [1, 30, -1, 0, 0, 0, 0]},
        {"type": "ComplexItem", "complexItemType": "survey",
         "TransectStyleComplexItem": {"VisualTransectPoints": [[47.9, 3.1], [47.8, 3.2]]}},
        {"type": "SimpleItem", "command": 21, "params": [0, 0, 0, None, 47.5, 3.5, 0]},
    ]}}


def test_waypoints_file_keeps_home_and_flown_points():
    assert mp.parse_mission(WPL) == [[35.8256, 10.6385], [35.84, 10.62], [35.856, 10.601]]


def test_plan_file_with_survey_and_landing():
    assert mp.parse_mission(json.dumps(PLAN)) == [
        [48.8534951, 2.3483915], [48.0, 3.0], [47.9, 3.1], [47.8, 3.2], [47.5, 3.5]]


@pytest.mark.parametrize("bad", ["hello", "QGC WPL 110\n1\t2\t3", "{}", '{"mission": {"items": []}}',
                                 "QGC WPL 110\n0\t1\t0\t16\t0\t0\t0\t0\t35.8\t10.6\t10\t1\n"])
def test_bad_mission_files_are_refused(bad):
    with pytest.raises(ValueError):
        mp.parse_mission(bad)


def test_settings_are_validated_and_written_atomically(tmp_path):
    f = str(tmp_path / "settings.env")
    ok = mp.validate_settings({"NAVERA_MAX_SPEED_KMH": "900", "NAVERA_IMU_MOUNT_RPY": "0, 0, 90",
                               "NAVERA_VEHICLE_TYPE": "plane", "NAVERA_THERMAL_HFOV_DEG": 84})
    cur = mp.write_settings(ok, f)
    assert cur == {"NAVERA_MAX_SPEED_KMH": "900", "NAVERA_IMU_MOUNT_RPY": "0,0,90",
                   "NAVERA_VEHICLE_TYPE": "plane", "NAVERA_THERMAL_HFOV_DEG": "84"}
    assert mp.read_settings(f) == cur
    text = open(f).read()
    assert text.startswith("#") and "NAVERA_MAX_SPEED_KMH=900\n" in text
    # an empty value removes the key (navera.env applies again)
    assert "NAVERA_THERMAL_HFOV_DEG" not in mp.write_settings(mp.validate_settings({"NAVERA_THERMAL_HFOV_DEG": ""}), f)
    assert not [p for p in os.listdir(tmp_path) if ".tmp" in p]


@pytest.mark.parametrize("key,value", [("NAVERA_MAX_SPEED_KMH", "2"), ("NAVERA_MAX_SPEED_KMH", "fast"),
                                       ("NAVERA_IMU_MOUNT_RPY", "1,2"), ("NAVERA_VEHICLE_TYPE", "tank"),
                                       ("DAY_DATASET_DIR", "/tmp"), ("ROS_DOMAIN_ID", "0"),
                                       ("NAVERA_MAX_SPEED_KMH", "100\nROS_DOMAIN_ID=0")])
def test_bad_settings_are_refused(key, value):
    with pytest.raises(ValueError, match=key.split("=")[0]):
        mp.validate_settings({key: value})


def test_area_id_follows_the_legs():
    long = [[48.8534951, 2.3483915], [33.8439408, 9.400138]]
    assert mp.area_id(long) == mp.area_id(mp.parse_mission(json.dumps(
        {"mission": {"plannedHomePosition": long[0], "items": [
            {"type": "SimpleItem", "command": 16, "params": [0, 0, 0, 0, *long[1], 0]}]}})))


FAKE_PREPARE = r'''
import json, os, sys
out = sys.argv[sys.argv.index("--out") + 1]
for i in range(3):
    print(json.dumps({"stage": "descriptors", "done": i + 1, "total": 3}), flush=True)
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "descriptors_cache.npz"), "w").write("x")
'''


@pytest.fixture
def jobs(tmp_path):
    mb = tmp_path / "map.mbtiles"
    con = sqlite3.connect(mb)
    con.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
    con.commit()
    con.close()
    script = tmp_path / "fake_prepare.py"
    script.write_text(FAKE_PREPARE)
    marker = tmp_path / "restarted"
    logs = []
    j = mp.AreaJobs(str(tmp_path / "areas"), str(mb), prepare_cmd=[sys.executable, str(script)],
                    restart_cmd=[sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ok')"],
                    settings_file=str(tmp_path / "settings.env"), log=lambda lvl, txt: logs.append((lvl, txt)))
    return j, marker, logs, tmp_path


def test_plan_generate_activate(jobs):
    j, marker, logs, tmp = jobs
    plan = j.plan([[35.8256, 10.6385], [35.8560, 10.6010]])
    assert plan["tiles"] > 100 and plan["missing_n"] == plan["tiles"] and not plan["prepared"]
    with pytest.raises(ValueError):
        j.activate(plan["id"])                         # not generated yet
    j.start(plan["id"])
    for _ in range(100):
        if j.state()["job"]["status"] != "running":
            break
        time.sleep(0.05)
    st = j.state()["job"]
    assert st["status"] == "done" and st["done"] == 3
    assert any("no download source" in t for _, t in logs)    # missing tiles reported
    j.activate(plan["id"])
    assert marker.read_text() == "ok"
    assert mp.read_settings(j.settings_file)["DAY_DATASET_DIR"] == j.path(plan["id"])
    assert j.plan([[35.8256, 10.6385], [35.8560, 10.6010]])["active"] is True


def test_a_failed_restart_is_reported(jobs):
    j, _, _, tmp = jobs
    plan = j.plan([[35.8256, 10.6385], [35.8560, 10.6010]])
    os.makedirs(j.path(plan["id"]))
    open(os.path.join(j.path(plan["id"]), "descriptors_cache.npz"), "w").write("x")
    j.restart_cmd = [sys.executable, "-c", "import sys; sys.exit('Access denied')"]
    with pytest.raises(RuntimeError, match="restart"):
        j.activate(plan["id"])


@pytest.mark.parametrize("aid", ["../../etc", "abc", "0123456789ab\nNAVERA_X=1", "/tmp/x", None, "0123456789AB"])
def test_a_forged_map_id_is_refused(jobs, aid):
    j, marker, _, _ = jobs
    for call in (j.activate, j.start):
        with pytest.raises(ValueError):
            call(aid)
    assert not marker.exists()


def test_a_line_break_cannot_inject_a_setting(tmp_path):
    with pytest.raises(ValueError):
        mp.write_settings({"DAY_DATASET_DIR": "/x\nNAVERA_WEB_TOKEN="}, str(tmp_path / "s.env"))
    with pytest.raises(ValueError):
        mp.write_settings({"bad key": "1"}, str(tmp_path / "s.env"))


def test_services_are_not_restarted_in_flight():
    assert "armed" in mp.in_flight_refusal(True, 2)
    assert "without GPS" in mp.in_flight_refusal(None, mp.STATE_DEGRADED)
    assert mp.in_flight_refusal(False, 2) is None          # disarmed, GPS fix
    assert mp.in_flight_refusal(None, None) is None        # no vehicle link, arbiter silent
    assert "moving" in mp.in_flight_refusal(None, 2, speed_mps=12.0)   # no link, but NAVERA sees it move
    assert mp.in_flight_refusal(None, 2, speed_mps=0.3) is None
    # NAVERA is the flight controller's GPS (NMEA / UBX port) and no MAVLink link tells "armed"
    assert "armed state unknown" in mp.in_flight_refusal(None, 2, serial_gps_output=True)
    assert mp.in_flight_refusal(False, 2, serial_gps_output=True) is None     # link says disarmed
    assert mp.in_flight_refusal(None, None, action="generate", serial_gps_output=True) is None


def test_terrain_of_a_generated_map_is_shown_in_its_plan(jobs):
    j, _, _, _ = jobs
    route = [[35.8256, 10.6385], [35.8560, 10.6010]]
    aid = j.plan(route)["id"]
    os.makedirs(j.path(aid))
    terrain = {"featureless_km": 12.4, "longest_km": 12.4, "stretches": [[1.36, 13.76]], "unknown_km": 0.0}
    with open(os.path.join(j.path(aid), "area.json"), "w") as f:
        json.dump({"terrain": terrain}, f)
    assert j.plan(route)["terrain"] == terrain


def test_named_missions_are_saved_replaced_and_deleted(jobs):
    j, _, _, _ = jobs
    r1 = [[35.8256, 10.6385], [35.84, 10.62], [35.8560, 10.6010]]
    m = j.save_mission("Sousse coast", r1)
    assert m[0]["name"] == "Sousse coast" and len(m[0]["route"]) == 3 and m[0]["length_km"] > 3
    j.save_mission("Other", r1[:2])
    m = j.save_mission("Sousse coast", r1[:2])                 # same name: replaced, newest first
    assert [x["name"] for x in m] == ["Sousse coast", "Other"] and len(m[0]["route"]) == 2
    assert j.state()["missions"] == m
    assert [x["name"] for x in j.delete_mission("Other")] == ["Sousse coast"]
    for name, route in (("", r1), ("x" * 61, r1), ("<script>", r1), ("ok", [[35.8, 10.6]]),
                        ("ok", [[95, 10], [35, 10]])):
        with pytest.raises(ValueError):
            j.save_mission(name, route)


def test_wrong_codes_lock_the_address_for_a_while():
    from simulation_web.web_common import _CodeGuard
    g = _CodeGuard()
    for _ in range(4):
        g.failed("10.0.0.9")
    assert g.blocked_for("10.0.0.9") == 0.0
    g.failed("10.0.0.9")
    assert g.blocked_for("10.0.0.9") > 50 and g.blocked_for("10.0.0.8") == 0.0


def test_generate_refusal_says_why():
    assert "processor" in mp.in_flight_refusal(None, mp.STATE_DEGRADED, action="generate")
    assert "restart" in mp.in_flight_refusal(None, mp.STATE_DEGRADED, action="apply")


# ── offline mission bundle command (navera_tools/mission_bundle.py) ─────
def test_bundle_command_is_validated():
    route = [[35.82, 10.596], [35.83, 10.60], [35.8215, 10.606]]
    cmd = mp.bundle_command("build", route, "/data/bundles/m1", corridor_m=1500, max_height_m=900,
                            sources=["onboard", "esri"])
    assert cmd[1].endswith("navera_tools/mission_bundle.py") and os.path.exists(cmd[1])
    assert cmd[2:6] == ["build", "/data/bundles/m1", "--yes", "--progress-json"]
    assert cmd[cmd.index("--start") + 1] == "35.82,10.596" and cmd[cmd.index("--dest") + 1] == "35.8215,10.606"
    assert cmd[cmd.index("--waypoint") + 1] == "35.83,10.6" and cmd[-2:] == ["onboard", "esri"]
    assert mp.bundle_command("check", out_dir="/b")[-2:] == ["/b", "--json"]
    for bad in (dict(sources=["onboard; rm -rf /"]), dict(route=[[95, 10]]), dict(corridor_m=1e9)):
        kw = dict(route=route, sources=["onboard"])
        kw.update(bad)
        with pytest.raises(ValueError):
            mp.bundle_command("plan", **kw)


def test_route_plans_kept_are_bounded_newest_first(jobs, monkeypatch):
    """Hours of use (or a client planning in a loop) never grow the plans kept in memory."""
    j = jobs[0]
    monkeypatch.setattr(mp, "plan_tiles", lambda *a, **k: {"missing": [], "needed": [], "in_base": 0, "in_cache": 0})
    monkeypatch.setattr(mp.AreaJobs, "_quick_terrain", lambda self, legs: None)
    ids = [j.plan([[35.80 + i * 0.001, 10.60], [35.85, 10.65]])["id"] for i in range(mp.MAX_PLANS + 15)]
    assert len(j.plans) == mp.MAX_PLANS
    assert list(j.plans) == ids[-mp.MAX_PLANS:]
    j.plan([[35.80 + 20 * 0.001, 10.60], [35.85, 10.65]])          # planned again: becomes the newest
    assert next(reversed(j.plans)) == ids[20] and len(j.plans) == mp.MAX_PLANS


def test_forwarding_settings():
    v = mp.validate_settings({"NAVERA_FORWARD_DEGRADED": "on", "NAVERA_DEGRADED_SIGMA_M": "30"})
    assert v == {"NAVERA_FORWARD_DEGRADED": "true", "NAVERA_DEGRADED_SIGMA_M": "30"}
    off = mp.validate_settings({"NAVERA_FORWARD_DEGRADED": "Off"})
    assert off["NAVERA_FORWARD_DEGRADED"] == "false"
    with pytest.raises(ValueError):
        mp.validate_settings({"NAVERA_FORWARD_DEGRADED": "maybe"})
    with pytest.raises(ValueError):
        mp.validate_settings({"NAVERA_DEGRADED_SIGMA_M": "500"})   # above ArduPilot's 100 m cap
    with pytest.raises(ValueError):
        mp.check_forwarding({"NAVERA_FORWARD_DEGRADED": "true"})
    mp.check_forwarding({"NAVERA_FORWARD_DEGRADED": "true", "NAVERA_DEGRADED_SIGMA_M": "30"})
    mp.check_forwarding({"NAVERA_FORWARD_DEGRADED": "false"})
