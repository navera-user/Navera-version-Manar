"""Which DroneCAN GNSS node NAVERA listens to (gps_pkg dronecan_gps_node.GnssSelector)."""
from gps_pkg.nodes.dronecan_gps_node import LISTEN_FIRST_S, SWITCH_AFTER_S, GnssSelector


def test_a_written_node_id_is_the_only_one_used():
    s = GnssSelector(124)
    assert s.accept(124, True, 0.0) and s.accept(124, False, 0.1)   # its no-fix messages too
    assert not s.accept(42, True, 10.0)
    s.controller(124)                                               # written: the operator decides
    assert s.accept(124, True, 11.0)


def test_any_node_listens_first_then_keeps_one_receiver():
    s = GnssSelector(0, start=0.0)
    s.controller(10)                                                # the autopilot commands ESCs
    assert not s.accept(124, True, 0.5)                             # still learning who is who
    assert not s.accept(10, True, LISTEN_FIRST_S + 0.1)             # an autopilot re-broadcast: never
    assert not s.accept(124, False, LISTEN_FIRST_S + 0.1)           # no fix: not chosen
    assert s.accept(124, True, LISTEN_FIRST_S + 0.2)
    assert not s.accept(125, True, LISTEN_FIRST_S + 0.3)            # one receiver, not two alternating
    assert s.accept(124, False, LISTEN_FIRST_S + 0.4)               # it losing its fix is still said
    t = LISTEN_FIRST_S + 0.4 + SWITCH_AFTER_S + 0.1                 # silent 5 s: another one
    assert s.accept(125, True, t) and not s.accept(124, True, t + 0.1)
