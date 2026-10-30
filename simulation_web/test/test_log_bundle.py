"""The dashboard's log archive (GET /api/logs.tar.gz): secrets removed, size capped, read-only access rule."""
import io
import json
import os
import sys
import tarfile

import pytest

from simulation_web import log_bundle, web_common


def _members(f):
    with tarfile.open(fileobj=f, mode="r:gz") as t:
        return {m.name.split("/", 1)[1]: t.extractfile(m).read().decode() for m in t.getmembers()}


def test_env_lines_naming_a_token_password_or_key_are_dropped():
    text = ("NAVERA_WEB_TOKEN=abc123\nNAVERA_MAX_SPEED_KMH=60\nwifi_password='x y'\nNAVERA_API_KEY=k\n"
            "NAVERA_FORWARD_DEGRADED=true\nNAVERA_KEYBOARD=1\nThermalPassword=p\n")
    out, dropped = log_bundle.strip_secrets(text)
    assert out == "NAVERA_MAX_SPEED_KMH=60\nNAVERA_FORWARD_DEGRADED=true\n" and dropped == 5
    for s in ("abc123", "x y", "=k", "=p"):
        assert s not in out


def test_journal_secret_values_are_masked():
    line = "2026-10-30T15:00:00+0100 jetson navera-web[1]: env NAVERA_WEB_TOKEN=abc123 password: hunter2 ok\n"
    red = log_bundle.redact_journal_line(line)
    assert "abc123" not in red and "hunter2" not in red and "NAVERA_WEB_TOKEN=***" in red and red.endswith("ok\n")


def _env(tmp_path):
    s = tmp_path / "settings.env"
    s.write_text("NAVERA_WEB_TOKEN=supersecret\nNAVERA_FORWARD_DEGRADED=true\n")
    d = tmp_path / "discovered.env"
    d.write_text("NAVERA_CAMERA_URL=rtsp://cam\nNAVERA_THERMAL_PASSWORD=pw\n")
    return [str(s), str(d), str(tmp_path / "missing.env")]


def _printer(n_lines, width=80):
    code = f"import sys\nfor i in range({n_lines}): sys.stdout.write('%08d ' % i + 'x' * {width} + '\\n')"
    return [sys.executable, "-c", code]


def test_the_archive_holds_the_journal_and_the_settings_without_secrets(tmp_path):
    f = log_bundle.build(env_files=_env(tmp_path), journal_cmd=_printer(100))
    got = _members(f)
    assert set(got) == {"README.txt", "settings.env", "discovered.env", "journal.log"}
    assert "supersecret" not in got["settings.env"] and "NAVERA_FORWARD_DEGRADED=true" in got["settings.env"]
    assert "pw" not in got["discovered.env"] and "rtsp://cam" in got["discovered.env"]
    assert got["journal.log"].count("\n") == 100 and "cut" not in got["journal.log"]
    assert "missing.env: not read" in got["README.txt"]


def test_the_journal_is_cut_to_its_newest_lines_under_the_cap(tmp_path):
    cap = 200_000
    f = log_bundle.build(max_bytes=cap, env_files=_env(tmp_path), journal_cmd=_printer(20_000))
    size = os.fstat(f.fileno()).st_size
    assert size <= cap
    j = _members(f)["journal.log"]
    lines = j.splitlines()
    assert lines[0].startswith("# journal cut to its newest") and lines[-1].startswith("00019999 ")
    assert len(j.encode()) <= cap and all(len(ln) == 89 for ln in lines[1:])       # whole lines only


def test_an_archive_over_the_cap_is_refused_not_truncated(tmp_path):
    big = tmp_path / "settings.env"
    big.write_bytes(b"NAVERA_X=" + os.urandom(300_000).hex().encode() + b"\n")    # incompressible-ish
    with pytest.raises(log_bundle.ArchiveTooLarge):
        log_bundle.build(max_bytes=100_000, env_files=[str(big)], journal_cmd=None)


def test_read_tail_keeps_the_last_bytes_at_a_line_start():
    data, dropped = log_bundle.read_tail([b"aaaa\nbbbb\n", b"cccc\n", b"dd\n"], 9)
    assert data == b"cccc\ndd\n" and dropped == 10 + 5 + 3 - 8


def test_a_missing_journalctl_gives_a_note_not_an_error():
    assert log_bundle.journal(1000, ["/nonexistent/journalctl"]).startswith(b"# journal not available")


class _H:
    authorize_read = web_common.BridgeHandler.authorize_read

    def __init__(self, ip, token_header=""):
        self.client_address = (ip, 1234)
        self.headers = {"X-Navera-Token": token_header} if token_header else {}
        self.sent = []

    def send_json(self, code, obj):
        self.sent.append((code, json.dumps(obj)))


def test_logs_are_free_from_a_trusted_network_else_need_the_code(monkeypatch):
    monkeypatch.setenv("NAVERA_WEB_TRUST_NETS", "10.42.0.0/24")
    assert _H("10.42.0.7").authorize_read("tok")
    assert _H("10.42.0.7").authorize_read("")                       # trusted: even without a code set
    h = _H("192.168.1.5")
    assert not h.authorize_read("tok") and h.sent[0][0] == 401
    h = _H("192.168.1.6")
    assert not h.authorize_read("") and h.sent[0][0] == 403
    assert _H("192.168.1.7", "tok").authorize_read("tok")
    assert not _H("192.168.1.8", "bad").authorize_read("tok")


def test_send_stream_writes_every_byte():
    class W:
        sent, hdr = io.BytesIO(), []
        wfile = sent
        send_stream = web_common.BridgeHandler.send_stream

        def send_response(self, c):
            self.hdr.append(c)

        def send_header(self, k, v):
            self.hdr.append((k, v))

        def end_headers(self):
            pass
    w, data = W(), os.urandom(200_000)
    w.send_stream("application/gzip", io.BytesIO(data), len(data), "x.tar.gz")
    assert w.sent.getvalue() == data and ("Content-Disposition", 'attachment; filename="x.tar.gz"') in w.hdr
