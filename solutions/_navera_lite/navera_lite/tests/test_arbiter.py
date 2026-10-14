"""Tests of navera_lite/arbiter.py (mission 29): the judge as a state machine. Written for the course."""
import math

from navera_lite.arbiter import Arbiter, candidates, no_fix_reason, pick, source_report, track_since
from navera_lite.estimate import Estimate
from navera_lite.settings import DEFAULTS


def cov9(sigma):
    v = sigma * sigma
    return (v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 * v)


def gps(stamp, sigma=3.0, lat=35.8256, lon=10.6084, **kw):
    return Estimate("gps", lat, lon, stamp, cov=cov9(sigma), cov_type=1, **kw)


def day(stamp, sigma=30.0):
    return Estimate("day", 35.8257, 10.6085, stamp, cov=cov9(sigma), cov_type=1)


def test_candidates_in_priority_order():
    latest = {"day": Estimate("day", 35.8, 10.6, 98.5), "gps": Estimate("gps", 35.8, 10.6, 96.0)}
    assert candidates(latest, 100.0, DEFAULTS) == ["day"]
    latest = {"celestial": Estimate("celestial", 35.8, 10.6, 80.0), "day": day(99.0), "gps": gps(99.5)}
    assert candidates(latest, 100.0, DEFAULTS) == ["gps", "day", "celestial"]
    assert candidates({}, 100.0, DEFAULTS) == []


def test_track_since():
    assert track_since({"day": 90.0, "night": 95.0}, ["gps", "day"], 100.0) == {"gps": 100.0, "day": 90.0}
    assert track_since({"gps": 50.0}, [], 100.0) == {}


def test_pick_holdoff():
    s = {"gps": 99.0, "day": 80.0}
    assert pick(["gps", "day"], "day", s, 100.0, DEFAULTS) == "day"
    assert pick(["gps", "day"], "day", s, 101.0, DEFAULTS) == "gps"
    assert pick(["gps", "day"], "day", {"gps": 97.5, "day": 80.0}, 99.5, DEFAULTS) == "gps"   # exactly 2.0 s
    assert pick(["day"], "gps", {"day": 99.9}, 100.0, DEFAULTS) == "day"
    assert pick(["gps", "day"], None, s, 99.1, DEFAULTS) == "gps"
    assert pick([], "gps", {}, 100.0, DEFAULTS) is None
    # day has waited long enough, GPS not yet: day replaces night
    assert pick(["gps", "day", "night"], "night", {"gps": 99.5, "day": 90.0, "night": 80.0}, 100.0, DEFAULTS) == "day"


def test_receive_door():
    a = Arbiter(DEFAULTS)
    assert a.receive(Estimate("gps", 35.8, 10.6, 120.0), 100.0) == (False, "from the future (20.0 s ahead)")
    assert a.latest == {} and a.refused["gps"].startswith("from the future")
    assert a.receive(gps(99.6), 100.0) == (True, "stored") and "gps" not in a.refused
    assert a.receive(gps(99.1), 100.2) == (False, "old news")
    ok, why = a.receive(gps(100.6, lat=35.8706), 100.6)
    assert not ok and why.startswith("jump") and a.latest["gps"].stamp_s == 99.6
    assert a.receive(Estimate("gps", math.nan, math.nan, 101.0, valid=False), 101.0) == (True, "stored")
    assert a.receive(Estimate("radar", 35.8, 10.6, 101.0), 101.0)[0] is False
    assert a.receive(gps(math.nan), 102.0) == (False, "bad stamp") and a.refused["gps"] == "bad stamp"
    assert a.receive(gps(102.5), 102.5) == (True, "stored") and "gps" not in a.refused
    assert a.latest["gps"].t_recv_s == 102.5


def test_step_states_and_switches():
    a = Arbiter(DEFAULTS)
    assert a.step(0.0).state == "STARTING"
    a.receive(gps(99.5), 100.0)
    d = a.step(100.0)
    assert (d.state, d.source, d.reason, d.switched, d.sigma_m) == ("FIX", "gps", "gps: σ 3.0 m", True, 3.0)
    a.receive(day(102.0), 102.4)
    d = a.step(104.0)
    assert (d.state, d.source, d.reason) == ("DEGRADED", "day", "day: σ 30.0 m > 25.0 m")
    d = a.step(108.0)
    assert d.state == "NO_FIX" and d.reason.startswith("no usable source (gps: stale")
    assert a.switches == [(100.0, None, "gps"), (104.0, "gps", "day"), (108.0, "day", None)]


def test_future_fix_never_revives():
    """One GPS fix stamped 20 s ahead, then GPS dead: it must never win, even when the clock reaches its stamp."""
    a = Arbiter(DEFAULTS)
    for k in range(5):
        a.receive(gps(100.0 + k), 100.0 + k)
        a.step(100.0 + k)
    a.receive(gps(125.0), 105.0)
    winners = set()
    for k in range(200):
        t = 105.0 + 0.2 * k
        if k % 5 == 0:
            a.receive(day(t - 0.8), t)
        winners.add(a.step(t).source)
    assert "gps" not in winners or a.switches[-1][2] != "gps"
    assert all(not (sw[0] > 108.0 and sw[2] == "gps") for sw in a.switches)


def test_reports():
    rep = source_report({}, {"gps": "from the future (20.0 s ahead)"}, 100.0, DEFAULTS)
    assert rep["gps"] == "refused: from the future (20.0 s ahead)" and rep["day"] == "nothing received"
    assert no_fix_reason({"gps": "stale (4.0 s > 3.0 s)", "day": "nothing received", "night": "nothing received",
                          "celestial": "nothing received"}) == "no usable source (gps: stale (4.0 s > 3.0 s))"
