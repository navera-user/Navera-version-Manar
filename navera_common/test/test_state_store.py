"""Facts kept across a restart: written atomically, reused only while recent."""
import json
import time

from navera_common import state_store


def test_save_and_load_while_recent(tmp_path):
    assert state_store.save("ground", {"altitude_m": 40.0}, str(tmp_path))
    d = state_store.load("ground", 60.0, str(tmp_path))
    assert d["altitude_m"] == 40.0


def test_old_future_or_broken_files_are_ignored(tmp_path):
    p = tmp_path / "ground.json"
    p.write_text(json.dumps({"altitude_m": 1.0, "saved_at": time.time() - 100}))
    assert state_store.load("ground", 60.0, str(tmp_path)) is None
    p.write_text(json.dumps({"altitude_m": 1.0, "saved_at": time.time() + 100}))
    assert state_store.load("ground", 60.0, str(tmp_path)) is None
    p.write_text("{not json")
    assert state_store.load("ground", 60.0, str(tmp_path)) is None
    assert state_store.load("missing", 60.0, str(tmp_path)) is None


def test_an_unwritable_directory_does_not_raise():
    assert state_store.save("x", {}, "/proc/navera_cannot_write_here") is False
