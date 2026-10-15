"""vehicle_output's gap bridging: when it stays silent, when it sends a carried position, when it ends."""
import math
from types import MethodType, SimpleNamespace

from navera_output.nodes.vehicle_output_node import VehicleOutputNode
from navera_output.policy import KIND_ESTIMATED, KIND_FIX, KIND_NONE, Config, Held, Output

CFG = Config(forward_degraded=True, degraded_sigma_m=50.0)


class _Log:
    def __init__(self):
        self.lines = []

    def warn(self, m):
        self.lines.append(m)


def _node(held=True):
    n = SimpleNamespace(cfg=CFG, _held=Held(35.8, 10.6, 60.0, 100.0, (15.0, 0.0, 1.0)) if held else None,
                        _last_tx=100.0, _bridging=False, _pos=object(), _log=_Log())
    n._sent_pos = n._pos
    n.get_logger = lambda: n._log
    n._bridged = MethodType(VehicleOutputNode._bridged, n)
    return n


def _same_pos_estimate():
    return Output(KIND_ESTIMATED, "estimated", lat=35.8, lon=10.6, sigma_h_m=60.0)


def test_between_two_positions_nothing_changes_and_nothing_is_sent_early():
    n = _node()
    out = _same_pos_estimate()
    assert n._bridged(out, 101.0) is out                  # the dedupe in _tick keeps it silent
    assert n._bridged(out, 102.4) is out
    assert not n._bridging


def test_the_gap_is_bridged_from_2_5_s_once_a_second_and_ends_at_10_s():
    n = _node()
    soft = Output(KIND_NONE, "no fix", soft=True)
    assert n._bridged(soft, 101.0) is None                # not told "no fix" yet: a bridge may start
    b = n._bridged(soft, 102.6)
    assert b.kind == KIND_ESTIMATED and b.bridged and n._bridging and "bridging" in n._log.lines[0]
    n._last_tx = 102.6                                    # _tick records the send
    assert n._bridged(soft, 103.0) is None                # next one in a second
    b2 = n._bridged(soft, 103.7)
    assert b2.bridged and b2.sigma_h_m > b.sigma_h_m
    n._last_tx = 103.7
    end = n._bridged(soft, 110.9)
    assert end.kind == KIND_NONE and "longer than the bridge" in end.reason and not n._bridging
    assert "bridge ended" in n._log.lines[-1]
    assert n._held is None                                # then plain "no fix", no more bridging
    assert n._bridged(soft, 111.0) is soft


def test_a_carried_estimate_is_also_bridged_while_the_arbiter_still_says_degraded():
    n = _node()
    b = n._bridged(_same_pos_estimate(), 103.0)           # the same position, 3 s old, nothing newer
    assert b.bridged and b.kind == KIND_ESTIMATED


def test_no_bridge_without_a_held_estimate_or_for_a_hard_no_fix():
    soft = Output(KIND_NONE, "no fix", soft=True)
    n = _node(held=False)
    assert n._bridged(soft, 105.0) is soft                # nothing to bridge: "no fix" as before
    silent = Output(KIND_NONE, "arbiter silent")          # the arbiter is dead: never bridge
    n = _node()
    assert n._bridged(silent, 105.0) is silent
    n = SimpleNamespace(cfg=Config(forward_degraded=True, degraded_sigma_m=50.0, bridge_max_s=0.0),
                        _held=Held(35.8, 10.6, 60.0, 100.0, None), _last_tx=100.0, _bridging=False,
                        _pos=object(), _sent_pos=None, get_logger=lambda: _Log())
    n._bridged = MethodType(VehicleOutputNode._bridged, n)
    assert n._bridged(soft, 105.0) is soft                # bridge_max_s = 0: never


def test_a_gps_fix_clears_the_held_estimate():
    n = _node()
    fix = Output(KIND_FIX, "fix", lat=35.8, lon=10.6, sigma_h_m=2.0, gnss=True)
    assert n._bridged(fix, 101.0) is fix
    assert n._held is None and n._last_tx is None
    assert math.isfinite(fix.lat)
