"""atomic_io: power-cut-safe writes and tolerant readers."""
import json
import os

import pytest

from navera_common import atomic_io as aio


def test_atomic_write_replaces_whole_file_and_leaves_no_temp(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("old")
    os.chmod(p, 0o640)
    aio.atomic_write_json(str(p), {"x": 1})
    assert json.loads(p.read_text()) == {"x": 1}
    assert os.stat(p).st_mode & 0o777 == 0o640           # permissions of the replaced file kept
    assert sorted(os.listdir(tmp_path)) == ["a.json"]


def test_atomic_write_failure_keeps_old_file(tmp_path, monkeypatch):
    p = tmp_path / "a.env"
    p.write_text("A=1\n")

    def boom(*_a):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(aio.os, "replace", boom)
    with pytest.raises(OSError):
        aio.atomic_write(str(p), "A=2\n")
    assert p.read_text() == "A=1\n"
    assert sorted(os.listdir(tmp_path)) == ["a.env"]     # the temporary file removed


@pytest.mark.parametrize("content", [b"", b'{"a": 1', b"\x00" * 64, b"\xff\xfe garbage", b"[1, 2]", b"3"])
def test_read_json_tolerant(tmp_path, content):
    p = tmp_path / "s.json"
    p.write_bytes(content)
    assert aio.read_json(str(p), default="D") == "D"
    assert aio.read_json(str(tmp_path / "missing.json"), default="D") == "D"


def test_read_env_skips_damaged_lines(tmp_path):
    p = tmp_path / "x.env"
    p.write_bytes(b"# c\nA=1\nB=\x00\x00\nC=\xff\nbad line\n9X=1\nD=two=2\nE=cu")
    assert aio.read_env(str(p)) == {"A": "1", "D": "two=2", "E": "cu"}


@pytest.mark.parametrize("content,damaged", [
    (b"A=1\n# c\n\n", False), (b"", False), (b"A=1\nB=2", True), (b"A=1\n\x00\x00\x00", True),
    (b"A=\xff\n", True), (b"A=1\nnot a setting\n", True)])
def test_env_file_damaged_and_quarantine(tmp_path, content, damaged):
    p = tmp_path / "settings.env"
    p.write_bytes(content)
    assert (aio.env_file_damaged(str(p)) is not None) == damaged
    assert aio.quarantine_damaged_env(str(p), log=lambda *_: None) == damaged
    assert p.exists() != damaged
    assert (tmp_path / "settings.env.damaged").exists() == damaged


def test_quarantine_missing_file_is_fine(tmp_path):
    assert aio.main(["--check-env", str(tmp_path / "none.env")]) == 0


def test_fsync_tree_never_raises(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f").write_text("x")
    aio.fsync_tree(str(tmp_path))
    aio.fsync_tree(str(tmp_path / "missing"))
