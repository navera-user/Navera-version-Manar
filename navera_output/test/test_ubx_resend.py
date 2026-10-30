"""UBX output repeats the last decision at rate_hz between measurements (PX4 drops a GPS silent 0.5 s);
NMEA and MAVLink still send each position once.
"""
import dataclasses
import struct
from types import MethodType, SimpleNamespace

import pytest

from navera_output import ubx_out
from navera_output.nodes import vehicle_output_node as von
from navera_output.policy import KIND_ESTIMATED, KIND_FIX, KIND_NONE, Config, Output

RATE = 5.0


class _Log:
    def __init__(self):
        self.lines = []

    def warn(self, m, **_):
        self.lines.append(m)

    info = error = fatal = debug = warn


class _Serial:
    def __init__(self):
        self.chunks = []

    def write(self, b):
        self.chunks.append(bytes(b))


class _Mav:
    def __init__(self):
        self.sent = 0
        self.mav = self

    def gps_input_send(self, **_):
        self.sent += 1


def _pvts(chunks):
    """(fixType, hAcc mm) of every NAV-PVT written."""
    out = []
    for c in chunks:
        i = 0
        while i < len(c):
            cls, mid, n = struct.unpack_from("<BBH", c, i + 2)
            if (cls, mid) == (ubx_out.NAV, ubx_out.NAV_PVT):
                p = c[i + 6:i + 6 + n]
                out.append((p[20], struct.unpack_from("<I", p, 40)[0]))
            i += 8 + n
    return out


@pytest.fixture
def world(monkeypatch):
    clock = [100.0]
    decision = {"out": Output(KIND_NONE, "nothing")}
    monkeypatch.setattr(von, "time", SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1e9 + clock[0]))
    monkeypatch.setattr(von, "decide", lambda *a, **k: decision["out"])
    monkeypatch.setattr(von.state_store, "save", lambda *a, **k: None)
    return clock, decision


def _node(proto="ubx", cfg=None, mav=False):
    n = SimpleNamespace(
        cfg=cfg or Config(forward_degraded=True, degraded_sigma_m=50.0, reacquire_after_s=0.0),
        _status=None, _status_rx=None,
        _vel=None, _vel_rx=None, _vel_timeout=1.0, _pos=None, _pos_rx=None, _last_kind=None, _sent_pos=None,
        _held=None, _last_tx=None, _last_pos_tx=None, _bridging=False, _held_saved_at=None,
        _drift_alarm=1e9, _held_alt_msl=float("nan"), _serial=_Serial(), _ubx_sats=0,
        _ubx=ubx_out.Responder(115200) if proto == "ubx" else None, _nmea_degraded=False,
        _mav=_Mav() if mav else None, _msg="gps_input", _fix_type_without_alt=3, _pub_fix=None,
        _period_s=1.0 / RATE, _ubx_last=None, _ubx_last_t=None, _ubx_first_t=None, failed=False, _log=_Log())
    n.get_logger = lambda: n._log
    n._measured_age = lambda pos: 0.1
    n._ground_velocity = n._autopilot_velocity = lambda: None
    for m in ("_tick", "_bridged", "_resend_ubx", "_write_ubx", "_check_drift", "_save_held"):
        setattr(n, m, MethodType(getattr(von.VehicleOutputNode, m), n))
    return n


def _run(n, clock, decision, out, t_end, new_pos_at=(0.0,), age_grows=True):
    """Ticks at rate_hz from now to t_end s; a new position object arrives at each new_pos_at."""
    t0 = base = clock[0]
    k = 0
    while k * (1.0 / RATE) <= t_end + 1e-9:
        dt = k / RATE
        clock[0] = t0 + dt
        if any(abs(dt - t) < 1e-6 for t in new_pos_at):
            n._pos, n._pos_rx = object(), clock[0]
            base = clock[0]
        decision["out"] = dataclasses.replace(out, age_s=out.age_s + (clock[0] - base if age_grows else 0.0))
        n._tick()
        k += 1


GPS = Output(KIND_FIX, "gps", lat=35.8, lon=10.6, alt_ellipsoid_m=43.0, geoid_sep_m=33.0, sigma_h_m=2.0,
             sigma_v_m=4.0, satellites=9, gnss=True, age_s=0.1)
VISION = Output(KIND_ESTIMATED, "estimated", lat=35.8, lon=10.6, sigma_h_m=30.0, age_s=0.1)


def test_a_silent_gps_is_not_repeated_at_its_receiver_accuracy(world):
    clock, decision = world
    n = _node()
    _run(n, clock, decision, GPS, 1.0)                    # one fix, then 1 s with no new measurement
    got = _pvts(n._serial.chunks)
    # review H2: only while the fix is younger than 2 periods, never 1 s later at +-2 m
    assert all(g == (3, 2000) for g in got) and 1 <= len(got) <= 3


def test_ubx_repeats_a_vision_position_until_the_bridge_then_the_bridge_grows_its_accuracy(world):
    clock, decision = world
    n = _node()
    soft = Output(KIND_NONE, "no new position", soft=True)
    _run(n, clock, decision, VISION, 0.0)                 # a vision position sent once...
    for k in range(1, 26):                                # ...then the arbiter goes soft "no fix" for 5 s
        clock[0] = 100.0 + k / RATE
        decision["out"] = soft
        n._tick()
    got = _pvts(n._serial.chunks)
    assert all(f == 3 for f, _ in got)                            # a position, never invented
    # review H1: before the bridge too, the repeat is carried with a growing accuracy, never the old one
    later = [h for _, h in got[1:]]
    assert later and later == sorted(later) and later[-1] > 30000 and all(h >= 30000 for h in later)


def test_nothing_is_repeated_past_the_max_measurement_age(world):
    clock, decision = world
    cfg = Config(forward_degraded=True, degraded_sigma_m=50.0, max_measurement_age_s=1.0, bridge_max_s=0.0,
                 reacquire_after_s=0.0)
    n = _node(cfg=cfg)
    _run(n, clock, decision, VISION, 0.0)
    n._held = von.Held(35.8, 10.6, 30.0, 100.0, None, None)       # held, but the bridge is off
    n._last_tx = 100.0
    sent = []
    for k in range(1, 15):                                         # waiting (bridge_max 0 -> soft passes)
        clock[0] = 100.0 + k / RATE
        n._resend_ubx(clock[0])
        sent.append(len(_pvts(n._serial.chunks)))
    # the bridge is off: the held position is never repeated (review H1: no stale repeat)
    assert set(sent) == {1}


def test_nmea_and_mavlink_still_send_each_position_once(world):
    clock, decision = world
    n = _node(proto="nmea", mav=True)
    _run(n, clock, decision, GPS, 1.0)
    assert len(n._serial.chunks) == 1 and n._mav.sent == 1


def test_ubx_with_mavlink_repeats_only_the_ubx(world):
    clock, decision = world
    n = _node(mav=True)
    _run(n, clock, decision, VISION, 1.0)
    assert len(_pvts(n._serial.chunks)) == 6 and n._mav.sent == 1


def test_a_no_fix_is_not_turned_into_a_repeated_position(world):
    clock, decision = world
    n = _node()
    _run(n, clock, decision, VISION, 0.4)
    _run(n, clock, decision, Output(KIND_NONE, "position measured 6 s ago"), 0.4, new_pos_at=())
    got = _pvts(n._serial.chunks)
    assert got[:3] == [(3, 30000)] * 3 and all(f == 0 for f, _ in got[3:])


def test_the_running_config_is_published_as_json():
    import json
    d = json.loads(von.running_config(Config(forward_degraded=True, degraded_sigma_m=50.0), "ubx"))
    assert d["forward_degraded"] is True and d["degraded_sigma_m"] == 50.0 and d["protocol"] == "ubx"
    d = json.loads(von.running_config(Config(), "nmea"))
    assert d["forward_degraded"] is False and d["degraded_sigma_m"] is None
