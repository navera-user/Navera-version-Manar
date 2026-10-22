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


class _ThrottledLog:
    """The rclpy logger's throttle: one line per throttle_duration_sec of the test clock."""

    def __init__(self, clock):
        self.lines, self.clock, self._last = [], clock, None

    def warn(self, m, throttle_duration_sec=0.0):
        if self._last is None or self.clock[0] - self._last >= throttle_duration_sec:
            self.lines.append(m)
            self._last = self.clock[0]


def test_a_coarse_forwarded_position_raises_the_drift_alarm_every_5_s():
    """NAV-SAF-11: an estimated position coarser than drift_alarm_sigma_m (100 m) given to the vehicle
    is a drift alarm, at most every 5 s; a fix, a finer estimate or no fix never is.
    """
    clock = [0.0]
    n = SimpleNamespace(_drift_alarm=100.0, _log=_ThrottledLog(clock))
    n.get_logger = lambda: n._log
    n._check_drift = MethodType(VehicleOutputNode._check_drift, n)
    coarse = Output(KIND_ESTIMATED, "estimated (celestial)", lat=35.8, lon=10.6, sigma_h_m=180.0)
    for k in range(11):                                   # 10 s of positions at 1 Hz
        clock[0] = float(k)
        assert n._check_drift(coarse)
    assert len(n._log.lines) == 3                         # t = 0, 5, 10 s
    assert "DRIFT ALARM" in n._log.lines[0] and "±180 m" in n._log.lines[0]
    bridged = Output(KIND_ESTIMATED, "bridged", lat=35.8, lon=10.6, sigma_h_m=150.0, bridged=True)
    assert n._check_drift(bridged)
    assert not n._check_drift(Output(KIND_ESTIMATED, "estimated", lat=35.8, lon=10.6, sigma_h_m=60.0))
    assert not n._check_drift(Output(KIND_ESTIMATED, "estimated", lat=35.8, lon=10.6, sigma_h_m=100.0))
    assert not n._check_drift(Output(KIND_FIX, "fix", lat=35.8, lon=10.6, sigma_h_m=500.0, gnss=True))
    assert not n._check_drift(Output(KIND_NONE, "no fix"))


def _vision_fix(sigma=6.6):
    """A day-vision position the arbiter calls FIX (calibrated sigma): not a GNSS fix."""
    return Output(KIND_FIX, "fix", lat=35.8, lon=10.6, sigma_h_m=sigma, gnss=False,
                  vel_n_mps=0.0, vel_e_mps=8.0, vel_sigma_mps=1.0)


def test_a_vision_fix_is_held_and_its_gap_bridged_like_an_estimate():
    """Isaac endur2 (2026-10-22): the day pipeline stalled 8.7 s after a vision FIX; the FIX had
    cleared the held position, so the autopilot got "no fix" at 5 Hz from 2.8 s on, EKF3 timed its
    position out 7 s after the last fix and the copter landed. The gap must be bridged.
    """
    from navera_output.policy import hold
    n = _node(held=False)
    fix = _vision_fix()
    assert n._bridged(fix, 100.0) is fix                  # a new vision fix goes out unchanged
    assert n._last_tx == 100.0                            # ... and does not reset the bridge clock
    n._held = hold(fix, 100.0, (8.0, 0.0, 1.0))           # what _tick remembers of it
    assert n._held is not None and n._held.sent_vel == (0.0, 8.0, 1.0)
    # the arbiter still says FIX for the same (old) position: wait, then bridge from 2.5 s
    assert n._bridged(fix, 101.0) is fix
    b = n._bridged(fix, 102.6)
    assert b.kind == KIND_ESTIMATED and b.bridged and n._bridging
    n._last_tx = 102.6
    # the day source times out: the arbiter says NO_FIX (soft) -> still bridged, once a second
    soft = Output(KIND_NONE, "no fix", soft=True)
    assert n._bridged(soft, 103.0) is None
    b2 = n._bridged(soft, 103.7)
    assert b2.bridged and b2.sigma_h_m > b.sigma_h_m
    # the 8.7 s stall of endur2 stays inside the bridge (10 s): never "no fix" to the autopilot
    for t in (104.7, 105.7, 106.7, 107.7, 108.7):
        n._last_tx = t - 1.0
        assert n._bridged(soft, t).bridged


def test_a_gnss_fix_still_clears_the_held_position_and_is_never_bridged():
    from navera_output.policy import hold
    gnss = Output(KIND_FIX, "fix", lat=35.8, lon=10.6, sigma_h_m=2.0, gnss=True)
    assert hold(gnss, 100.0, (8.0, 0.0, 1.0)) is None
    n = _node()
    n._sent_pos = n._pos
    assert n._bridged(gnss, 103.0) is gnss and n._held is None and n._last_tx is None
