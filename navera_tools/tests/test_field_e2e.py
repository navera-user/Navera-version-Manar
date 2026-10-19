"""e2e_check --live: read-only, and a server that does not answer is a failure, not a crash."""
from navera_tools.field import e2e_check


def test_live_on_a_dead_server_fails_cleanly():
    ok, verdict = e2e_check.live(f"https://127.0.0.1:{e2e_check.free_port()}", key="x" * 12)
    assert not ok and verdict.startswith("live FAIL")
