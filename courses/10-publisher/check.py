import contextlib
import io
import json
import math
import os
import re
import tempfile
import time

from academy_check import (CheckFailed, Checker, explained, is_stub, load_student, need, predicted, run, sh)

c = Checker()
NS = "/check10"                    # the check runs its own nodes in this namespace: your terminals cannot disturb it
FIX_TOPIC = NS + "/navera_lite/fix/gps"
R = 6_371_000.0


# ------------------------------------------------------------------------------------------- helpers
def gps():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.ros.gps_node", fresh=True)


def functions(*names):
    fns = need(gps(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in "
                              "navera_lite/ros/gps_node.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def go(fn, *args):
    """run() with this mission's extra sentence, and the 300-digit float bounds of ROS cut out."""
    try:
        return run(fn, *args)
    except CheckFailed as e:
        msg = re.sub(r"\[-?\d{20,}[^\]]*\]", "[…]", str(e))
        if "not supported between instances of 'NoneType'" in msg or (
                "unsupported operand" in msg and "'NoneType'" in msg):
            msg += (" — your function received None (an input such as sigma_m = None) and compared or computed it "
                    "with a number: test `sigma_m is None` FIRST (🧰 box of lab Step 4)")
        if "of type 'float'" in msg:
            msg += (" — a ROS float field got an int (or a list holding ints): write 0.0, not 0, and float(x) for "
                    "the inputs (lesson §4, the type trap)")
        raise CheckFailed(msg)


def en_m(lat0, lon0, lat, lon):
    """(east, north) metres from point 0 to a point, local flat map (mean latitude), across ±180°."""
    dlon = (lon - lon0 + 180.0) % 360.0 - 180.0
    return (R * math.cos(math.radians((lat0 + lat) / 2)) * math.radians(dlon), R * math.radians(lat - lat0))


def dist_dir(lat0, lon0, lat, lon):
    e, n = en_m(lat0, lon0, lat, lon)
    return math.hypot(e, n), math.degrees(math.atan2(e, n)) % 360.0


def angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def stamp_s(m):
    return m["t"]


# ---------------------------------------------------------------- running the student's node (in the student's Python)
# Everything ROS happens in ONE script run in the student's own Python: the student's node, arbiter v0 and a
# listener in one process (the checker's own process may not see the student's network, and rclpy objects cannot
# be passed to student code). The script holds inputs only, no expected value; its results are judged here.
DRIVER = r"""
import json, os, random, sys, time, traceback
sys.path.insert(0, os.getcwd())
mode = sys.argv[1]
argv = sys.argv[2:]
fixes, statuses, out = [], [], {}

def where(e):
    tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith("gps_node.py")]
    return f" (navera_lite/ros/gps_node.py line {tb[-1].lineno}, in {tb[-1].name})" if tb else ""

def done(err=None):
    out.update({"fixes": fixes, "statuses": statuses})
    if err is not None:
        out["error"] = err
    print("RESULT " + json.dumps(out), flush=True)
    os._exit(0)

try:
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.parameter import Parameter
    from sensor_msgs.msg import NavSatFix
    from diagnostic_msgs.msg import DiagnosticStatus
    from navera_lite.ros import gps_node as g
    from navera_lite.ros.qos import FIX_QOS, STATUS_QOS
except Exception as e:
    done(f"{type(e).__name__}: {e}{where(e)}")
rclpy.init(args=argv)

if mode == "inspect":
    class N(g.FakeGps):
        calls = 0
        def on_timer(self):
            N.calls += 1
    try:
        n = N()
    except NotImplementedError as e:
        done(f"{e} is not written yet (NotImplementedError)")
    except Exception as e:
        done(f"{type(e).__name__}: {e}{where(e)}")
    out["params"] = {k: (n.get_parameter(k).value if n.has_parameter(k) else "<missing>") for k in g.DEFAULTS}
    out["latlon"] = [n.lat, n.lon]
    out["pubs"] = [[p.topic_name, p.msg_type.__name__, p.qos_profile.reliability.name] for p in n.publishers
                   if not p.topic_name.endswith(("rosout", "parameter_events"))]
    out["pub_attr"] = type(n.pub).__name__
    out["timers"] = [t.timer_period_ns * 1e-9 for t in n.timers]
    out["calls"] = N.calls
    done()

rng = random.Random()
class Late(g.FakeGps):
    ticks = 0
    def on_timer(self):
        Late.ticks += 1
        time.sleep(1.2 if Late.ticks == 4 else rng.uniform(0.0, 0.2))
        super().on_timer()

try:
    node = Late() if mode == "late" else g.NODE_CLASS()
except NotImplementedError as e:
    done(f"building your node: {e} is not written yet (NotImplementedError)")
except Exception as e:
    done(f"building your node: {type(e).__name__}: {e}{where(e)}")
ex = MultiThreadedExecutor(num_threads=4)
ex.add_node(node)
col = rclpy.create_node("check10_listener")
def on_fix(m):
    fixes.append({"t": m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, "lat": m.latitude, "lon": m.longitude,
                  "frame": m.header.frame_id, "status": int(m.status.status), "service": int(m.status.service),
                  "cov": [float(x) for x in m.position_covariance], "type": int(m.position_covariance_type),
                  "recv": time.time()})
col.create_subscription(NavSatFix, "navera_lite/fix/gps", on_fix, FIX_QOS)
if mode == "late":
    from navera_lite.ros.arbiter_v0 import ArbiterV0
    ex.add_node(ArbiterV0())
    col.create_subscription(DiagnosticStatus, "navera_lite/status", lambda m: statuses.append(m.message), STATUS_QOS)
ex.add_node(col)

def spin_until(cond, seconds):
    end = time.time() + seconds
    while time.time() < end and not cond():
        try:
            ex.spin_once(timeout_sec=0.05)
        except Exception as e:
            done(f"your node crashed after {len(fixes)} fix(es): {type(e).__name__}: {str(e)[:300]}{where(e)}")

if mode == "late":
    spin_until(lambda: len(fixes) >= 11, 14)
    spin_until(lambda: False, 0.5)
else:
    spin_until(lambda: len(fixes) >= 6, 8)
    out["set_at"] = len(fixes)
    try:
        node.set_parameters([Parameter("heading_deg", value=180.0), Parameter("speed_mps", value=9.0),
                             Parameter("sigma_m", value=2.0), Parameter("stamp_offset_s", value=-5.0)])
        out["set"] = "ok"
    except Exception as e:
        out["set"] = f"{type(e).__name__}: {e}"
    spin_until(lambda: False, 0.6)
    out["after_from"] = len(fixes)
    n0 = len(fixes)
    spin_until(lambda: len(fixes) >= n0 + 8, 8)
done()
"""


def last_error(text):
    text = re.sub(r"\[-?\d{20,}[^\]]*\]", "[…]", text)
    if "of type 'float'" in text:
        text += ("\n→ a ROS float field got an int (or a list holding ints): write 0.0, not 0 (lesson §4, the type "
                 "trap)")
    return text


def ros_args(params):
    return "--ros-args -r __ns:=" + NS + "".join(f" -p {k}:={v}" for k, v in params.items())


_live = {}


def live_run(mode, params):
    """Run the driver once per mode (cached); returns its RESULT dict."""
    key = (mode, tuple(sorted(params.items())))
    if key in _live:
        return _live[key]
    fd, path = tempfile.mkstemp(prefix="check10_", suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(DRIVER)
    try:
        code, out = sh(f"timeout 45 python3 {path} {mode} {ros_args(params)}", timeout=60)
    finally:
        os.remove(path)
    m = re.search(r"^RESULT (.*)$", out, re.M)
    if not m:
        tail = "\n".join(out.strip().splitlines()[-4:])
        res = {"error": "your node could not be run:\n" + last_error(tail[-700:]), "fixes": [], "statuses": []}
    else:
        res = json.loads(m.group(1))
    _live[key] = res
    return res


def need_fixes(res, fixes, n, what):
    if len(fixes) >= n:
        return fixes
    if res.get("error"):
        raise CheckFailed(f"{what}: {last_error(res['error'])}")
    raise CheckFailed(f"{what}: only {len(fixes)} fix(es) arrived on {FIX_TOPIC} (the node runs in the namespace "
                      f"{NS}: TOPIC must stay a RELATIVE name). Does on_timer publish with self.pub?")


def pair_report(fixes, speed, heading, label):
    """Every consecutive pair must move speed × (difference of the stamps) on heading."""
    bad = []
    for a, b in zip(fixes, fixes[1:]):
        dt = b["t"] - a["t"]
        d, h = dist_dir(a["lat"], a["lon"], b["lat"], b["lon"])
        if dt <= 0:
            bad.append(f"two fixes with stamps {a['t']:.3f} and {b['t']:.3f}: time must run forward")
            continue
        if abs(d / dt - speed) > 0.02 * speed + 0.05:
            bad.append(f"{d:.2f} m in {dt:.3f} s = {d / dt:.2f} m/s")
        elif d > 0.05 and angle_diff(h, heading) > 2.0:
            bad.append(f"towards {h:.0f}° instead of {heading:.0f}°")
    if bad:
        bad = list(dict.fromkeys(bad))
        raise CheckFailed(f"{label}: between consecutive fixes your vehicle moved " + "; ".join(bad[:3])
                          + f" — at {speed} m/s every pair must give {speed} m/s, whatever the delay between the ticks")


# ============================================================================== session 1 — build
SOUSSE = (35.8256, 10.6084)


@c.test("TODO 1: step() moves the right distance in the right direction, anywhere on Earth",
        hint="Lesson §3, the worked example: the velocity (east, north) from mission 03's part, times dt_s, then "
             "mission 06's offset — east FIRST. A heading is clockwise from north.")
def _():
    (step,) = functions("step")
    cases = [((64.1466, -21.9426, 15.0, 225.0, 2.5), (64.14636153134775, -21.943146856287456), "Reykjavik"),
             ((-0.1807, -78.4678, 8.0, 0.0, 1.25), (-0.18061006783940814, -78.4678), "Quito"),
             ((-33.8688, 151.2093, 20.0, 300.0, 0.4), (-33.86876402713576, 151.2092249601061), "Sydney"),
             ((-17.70, 179.9999, 30.0, 90.0, 2.0), (-17.7, -179.99953359422614), "Fiji, across ±180°"),
             ((51.5074, -0.1278, 7.0, 180.0, 0.0), (51.5074, -0.1278), "London, dt 0")]
    for args, want, place in cases:
        got = run(step, *args)
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"step() must return (lat, lon), two numbers — for {place} it returned {got!r}")
        lat, lon = number(got[0], "the latitude"), number(got[1], "the longitude")
        miss, _ = dist_dir(want[0], want[1], lat, lon)
        if miss < 0.01:
            continue
        lat0, lon0, v, h, dt = args
        d, hh = dist_dir(lat0, lon0, lat, lon)
        if abs(d) > 1e5:
            why = "it lands far away: a longitude past 180° must come back to −180 (geo.offset does it)"
        elif angle_diff(hh, (90.0 - h) % 360.0) < 1.0 and d > 0.01:
            why = (f"it went towards {hh:.0f}° instead of {h:.0f}°: north and east are swapped. Did you give geo.offset "
                   "north before east? It is offset(lat, lon, e_m, n_m), east FIRST. (Or, if you wrote your own sin/cos: "
                   "east = v·sin h, north = v·cos h, h clockwise from north.)")
        elif abs(d - v * dt) > 0.05 and abs(d - v) < 0.05:
            why = "it always moves speed_mps metres: multiply the velocity by dt_s"
        elif abs(d - v * dt) < 0.05 and angle_diff(hh, h) > 1.0:
            why = (f"right distance, wrong direction ({hh:.0f}° instead of {h:.0f}°): math.sin/cos need radians, or "
                   "east and north are swapped in geo.offset(lat, lon, e_m, n_m)")
        else:
            why = f"it moved {d:.2f} m towards {hh:.0f}°, not {v * dt:.2f} m towards {h:.0f}°"
        raise CheckFailed(f"step{args} for {place}: {why}")


@c.test("TODO 1: step() refuses a negative dt with ValueError",
        hint="The docstring: raise ValueError(\"dt_s must be >= 0, got …\") before anything else (🧰 of lab Step 2).")
def _():
    (step,) = functions("step")
    try:
        got = run(step, 35.0, 10.0, 5.0, 45.0, -0.3)
    except CheckFailed as e:
        if "ValueError" in str(e):
            return
        raise
    if isinstance(got, BaseException) or "Error(" in repr(got):
        raise CheckFailed(f"step(35.0, 10.0, 5.0, 45.0, -0.3) RETURNED {got!r}: write `raise ValueError(...)`, not "
                          "`return` (🧰 box of lab Step 2)")
    raise CheckFailed(f"step(35.0, 10.0, 5.0, 45.0, -0.3) returned {got!r}: a negative time step is impossible — "
                      "raise ValueError instead of moving the vehicle backwards")


@c.test("TODO 2: covariance_from_sigma() states variances as floats in m², and UNKNOWN when nothing is stated",
        hint="Lesson §4: σ² on East and North, (2σ)² on Up, 0.0 elsewhere, type COV_APPROXIMATED (1). None, nan, "
             "0 or a negative σ → nine 0.0 and COV_UNKNOWN (0). Every number a float.")
def _():
    (f,) = functions("covariance_from_sigma")
    for sigma, want in ((1.5, [2.25, 0.0, 0.0, 0.0, 2.25, 0.0, 0.0, 0.0, 9.0]),
                        (2, [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 16.0]),
                        (250.0, [62500.0, 0.0, 0.0, 0.0, 62500.0, 0.0, 0.0, 0.0, 250000.0])):
        got = go(f, sigma)
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"covariance_from_sigma({sigma!r}) must return (cov9, cov_type), got {got!r}")
        cov, typ = got
        if not (isinstance(cov, (list, tuple)) and len(cov) == 9):
            raise CheckFailed(f"covariance_from_sigma({sigma!r}): cov9 must be 9 numbers, got {cov!r}")
        if not all(isinstance(x, float) for x in cov):
            raise CheckFailed(f"covariance_from_sigma({sigma!r}) gives {list(cov)!r}: some numbers are ints. ROS "
                              "float fields refuse ints (lesson §4): write 0.0, and float(sigma_m) ** 2")
        if abs(cov[0] - sigma) < 1e-9 and sigma != 1:
            raise CheckFailed(f"covariance_from_sigma({sigma!r}): cov[0] is σ = {cov[0]} — the covariance holds "
                              "VARIANCES, σ² in m²")
        if abs(cov[8] - sigma ** 2) < 1e-9:
            raise CheckFailed(f"covariance_from_sigma({sigma!r}): Up is σ² — the docstring says (2σ)² for Up")
        c.ok(all(abs(a - b) < 1e-9 for a, b in zip(cov, want)),
             f"covariance_from_sigma({sigma!r}) gives {list(cov)!r}: check the positions (ENU, row-major: the "
             "diagonal is at indices 0, 4 and 8)")
        c.ok(typ == 1, f"covariance_from_sigma({sigma!r}) gives the type {typ!r}: a stated σ is "
                       "COV_APPROXIMATED (1)" + (" — DIAGONAL_KNOWN (2) would claim the variances are KNOWN"
                                                  if typ == 2 else ""))
    for sigma in (None, 0.0, -2.0, float("nan"), float("inf")):
        got = go(f, sigma)
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"covariance_from_sigma({sigma!r}) must return (cov9, cov_type), got {got!r}")
        cov, typ = got
        c.ok(isinstance(cov, (list, tuple)) and len(cov) == 9 and all(isinstance(x, float) and x == 0.0 for x in cov)
             and typ == 0,
             f"covariance_from_sigma({sigma!r}) gives ({cov!r}, {typ!r}): an accuracy that is not stated is never "
             "invented — nine 0.0 and COV_UNKNOWN (0). (math.isfinite() catches nan and inf; test None first.)")


@c.test("TODO 3: make_fix() fills every field of an honest NavSatFix",
        hint="Lesson §4 table: header.stamp = s_to_stamp(stamp_s), frame_id \"gps\", status.status STATUS_FIX, "
             "status.service SERVICE_GPS, float(lat/lon/alt), covariance and type from covariance_from_sigma().")
def _():
    (f,) = functions("make_fix")
    m = go(f, -33.9249, 18.4241, 12.5, 1.5, 1791890000.25)
    c.ok(type(m).__name__ == "NavSatFix", f"make_fix() must return a sensor_msgs NavSatFix, got {m!r}")
    st = m.header.stamp
    c.ok(st.sec == 1791890000 and abs(st.nanosec - 250000000) < 2000,
         f"stamp 1791890000.25 s became sec={st.sec}, nanosec={st.nanosec}: use s_to_stamp(stamp_s) "
         "(int() alone loses the fraction)")
    c.ok(m.header.frame_id == "gps", f"header.frame_id is {m.header.frame_id!r}: the source name \"gps\"")
    c.ok(m.status.status == 0, f"status.status is {m.status.status}: STATUS_FIX is 0")
    c.ok(m.status.service == 1, f"status.service is {m.status.service}: set it to NavSatStatus.SERVICE_GPS (1)")
    c.ok(abs(m.latitude + 33.9249) < 1e-12 and abs(m.longitude - 18.4241) < 1e-12 and m.altitude == 12.5,
         f"position ({m.latitude}, {m.longitude}, {m.altitude}): latitude, longitude, altitude from the inputs")
    c.ok(list(m.position_covariance) == [2.25, 0.0, 0.0, 0.0, 2.25, 0.0, 0.0, 0.0, 9.0]
         and m.position_covariance_type == 1,
         f"σ 1.5 m gave the covariance {list(m.position_covariance)} type {m.position_covariance_type}: use "
         "covariance_from_sigma(sigma_m)")
    m = go(f, -34, 18, 12, None, 5.75)
    c.ok(m.latitude == -34.0 and m.position_covariance_type == 0 and list(m.position_covariance) == [0.0] * 9,
         f"make_fix(-34, 18, 12, None, 5.75): position ({m.latitude}, {m.longitude}), type "
         f"{m.position_covariance_type} — no σ stated means COV_UNKNOWN (0)")
    c.ok(m.header.stamp.sec == 5 and m.header.stamp.nanosec == 750000000,
         f"stamp 5.75 s became sec={m.header.stamp.sec}, nanosec={m.header.stamp.nanosec}")


@c.test("TODO 4–5: the node declares its 8 parameters, starts where -p says, and has a publisher and a timer",
        hint="Lesson §1–§2. TODO 4: one parameter per item of DEFAULTS, then the start position READ from the "
             "parameters. TODO 5: keep the publisher in self.pub (TOPIC, FIX_QOS); the timer period is 1 / rate_hz, "
             "and it gets the method itself. `python3 run_gps.py node` shows each part.")
def _():
    r = live_run("inspect", {"rate_hz": "4.0", "start_lat": "-33.9249", "start_lon": "18.4241", "speed_mps": "6.5"})
    if r.get("error"):
        raise CheckFailed("building your node (its __init__ calls declare_all() then start()) failed: "
                          + last_error(r["error"]))
    missing = [k for k, v in r["params"].items() if v == "<missing>"]
    c.ok(not missing, f"parameters not declared: {', '.join(missing)} — one declare_parameter per item of DEFAULTS")
    c.ok(r["params"]["speed_mps"] == 6.5 and r["params"]["rate_hz"] == 4.0,
         f"started with -p speed_mps:=6.5 -p rate_hz:=4.0, the parameters say {r['params']['speed_mps']} and "
         f"{r['params']['rate_hz']}: declare_parameter(name, DEFAULTS[name]) lets -p win")
    c.ok(r["latlon"] == [-33.9249, 18.4241],
         f"started with -p start_lat:=-33.9249 -p start_lon:=18.4241, self.lat/self.lon are {r['latlon']}: READ them "
         "from the parameters (get_parameter(…).value), not from DEFAULTS")
    c.ok(r["calls"] == 0, "on_timer was CALLED while the node was built: give the method itself to create_timer, "
                          "self.on_timer, without () (lesson §1)")
    fix_pubs = [p for p in r["pubs"] if p[0] == FIX_TOPIC]
    c.ok(fix_pubs, f"no publisher on {FIX_TOPIC} (it has {[p[0] for p in r['pubs']]}): use TOPIC, a relative name, "
                   "so that a namespace moves it")
    c.ok(fix_pubs[0][1] == "NavSatFix" and fix_pubs[0][2] == "RELIABLE",
         f"the publisher is {fix_pubs[0][1]}, {fix_pubs[0][2]}: NavSatFix with qos.FIX_QOS")
    c.ok(r["pub_attr"] == "Publisher", "self.pub is not the publisher: store it, self.pub = self.create_publisher(…)")
    c.ok(len(r["timers"]) == 1, f"{len(r['timers'])} timers: start() creates exactly one")
    c.ok(abs(r["timers"][0] - 0.25) < 1e-6,
         f"with rate_hz 4.0 the timer period is {r['timers'][0]:.3f} s: the period is 1 / rate_hz = 0.25 s")


LATE = {"rate_hz": "2.0", "speed_mps": "8.0", "heading_deg": "30.0", "start_lat": "-33.9249",
        "start_lon": "18.4241", "sigma_m": "1.5"}
TURN = {"rate_hz": "4.0", "speed_mps": "6.0", "heading_deg": "0.0", "start_lat": "51.5074",
        "start_lon": "-0.1278", "sigma_m": "0.0", "stamp_offset_s": "-2.0"}


@c.test("TODO 6: the node moves at speed_mps on heading_deg with the REAL time between ticks (random delays)",
        hint="Lesson §3: dt is the REAL time since the previous tick, read on the same clock as the stamp. A fixed "
             "dt = 1 / rate_hz fails here: the check delays your ticks at random, as `python3 run_gps.py jitter` "
             "does. Run it and read the 'speed seen' column.")
def _():
    res = live_run("late", LATE)
    fixes = need_fixes(res, res["fixes"], 6, "with random delays")
    first = fixes[0]
    c.ok(first["frame"] == "gps" and first["type"] == 1 and abs(first["cov"][0] - 2.25) < 1e-9,
         f"with -p sigma_m:=1.5 the fixes say frame {first['frame']!r}, covariance[0] {first['cov'][0]}, type "
         f"{first['type']}: build them with make_fix(…, sigma_m read from the parameters, …)")
    pair_report(fixes, 8.0, 30.0, "8.0 m/s on heading 30°")
    d, h = dist_dir(-33.9249, 18.4241, fixes[-1]["lat"], fixes[-1]["lon"])
    c.ok(d < 8.0 * 30, f"started at -p start_lat/start_lon (Cape Town), the vehicle is {d:,.0f} m away from that "
                       "start: does it start from the parameters?")
    lag = fixes[-1]["recv"] - fixes[-1]["t"]
    c.ok(abs(lag) < 3.0, f"the last stamp is {lag:.1f} s away from the clock: stamp = now (+ stamp_offset_s, 0.0 here)")
    span = fixes[-1]["t"] - fixes[0]["t"]
    c.ok(0.35 < span / (len(fixes) - 1) < 0.8,
         f"{len(fixes)} fixes over {span:.1f} s at rate_hz 2.0: the timer period must be 1 / rate_hz")
    if res.get("error"):
        raise CheckFailed(last_error(res["error"]))


@c.test("TODO 6: `ros2 param set` changes heading, speed, σ and stamp offset while it runs",
        hint="Read speed_mps, heading_deg, sigma_m and stamp_offset_s with get_parameter(…).value INSIDE on_timer, "
             "at every tick — values read once (in declare_all() or at the first tick) never change. The stamp is "
             "now + stamp_offset_s.")
def _():
    res = live_run("turn", TURN)
    k = res.get("set_at", len(res["fixes"]))
    before = need_fixes(res, res["fixes"][:k], 4, "before the change")
    c.ok(all(m["type"] == 0 and m["cov"] == [0.0] * 9 for m in before),
         "with -p sigma_m:=0.0 (no accuracy stated) the fixes must say COV_UNKNOWN and nine 0.0: pass sigma_m "
         "from the parameters to make_fix")
    lag = before[-1]["recv"] - before[-1]["t"]
    if -3.5 < lag < -0.5:
        raise CheckFailed(f"with -p stamp_offset_s:=-2.0 the stamps are {-lag:.1f} s AHEAD of the clock: you subtracted "
                          "the offset. The stamp is now + stamp_offset_s")
    c.ok(0.5 < lag < 3.5, f"with -p stamp_offset_s:=-2.0 the stamps are {lag:.1f} s behind the clock instead of "
                          "about 2 s: stamp = now + stamp_offset_s")
    pair_report(before, 6.0, 0.0, "before the change, 6.0 m/s north")
    c.ok(res.get("set") == "ok", f"the check could not set the parameters of your node: {res.get('set')}")
    if "ValueError" in res.get("error", ""):
        raise CheckFailed("after stamp_offset_s changed from -2.0 to -5.0, " + last_error(res["error"])
                          + " — dt is the REAL time between two ticks (now − last_t, on the clock you read), BEFORE "
                          "stamp_offset_s is added: the offset moves the stamp, never the vehicle")
    after = need_fixes(res, res["fixes"][res.get("after_from", k):], 4, "after the change")
    a, b = after[-2], after[-1]
    d, h = dist_dir(a["lat"], a["lon"], b["lat"], b["lon"])
    dt = b["t"] - a["t"]
    lag2 = b["recv"] - b["t"]
    stuck = []
    if angle_diff(h, 0.0) < 3.0:
        stuck.append("heading_deg (still north)")
    if dt > 0 and abs(d / dt - 6.0) < 0.3:
        stuck.append("speed_mps (still 6.0 m/s)")
    if b["type"] == 0:
        stuck.append("sigma_m (still no σ)")
    if lag2 < 3.5:
        stuck.append(f"stamp_offset_s (stamps still {lag2:.1f} s behind)")
    c.ok(not stuck, "after the check set heading_deg 180.0, speed_mps 9.0, sigma_m 2.0 and stamp_offset_s -5.0 "
                    "(what `ros2 param set` does), these did not change: " + ", ".join(stuck) + ". Read them from "
                    "the parameters at EVERY tick, inside on_timer")
    pair_report(after, 9.0, 180.0, "after the change, 9.0 m/s south")
    c.ok(abs(b["cov"][0] - 4.0) < 1e-9, f"after sigma_m 2.0 the covariance[0] is {b['cov'][0]}, not 4.0")
    c.ok(not -7.0 < lag2 < -3.5, f"after stamp_offset_s -5.0 the stamps are {-lag2:.1f} s AHEAD of the clock: you "
                                 "subtracted the offset. The stamp is now + stamp_offset_s")
    c.ok(3.5 < lag2 < 7.0, f"after stamp_offset_s -5.0 the stamps are {lag2:.1f} s behind the clock, not about 5 s")


@c.test("The judge: arbiter v0 shows your receiver as FIX with the σ it states",
        hint="Arbiter v0 (mission 09) listens on navera_lite/fix/gps. It shows FIX \"gps: σ 1.5 m\" when your fixes "
             "are fresh and state σ 1.5 m: stamp them NOW, with a covariance of σ² (lab Step 8).")
def _():
    res = live_run("late", LATE)
    need_fixes(res, res["fixes"], 2, "for the judge")
    msgs = res["statuses"]
    c.ok(msgs, "arbiter v0 published no status in the check's run")
    c.ok(any(m == "gps: σ 1.5 m" for m in msgs),
         f"arbiter v0 says {msgs[-1]!r} about your receiver, not 'gps: σ 1.5 m' (FIX)")


@c.test("Steps 0 and 3: the bug and the busy computer, in numbers",
        hint="Step 0: 10 m between two messages, sent 1/10 s apart. Step 3: the nominal receiver adds 12 m/s × 0.5 s "
             "per tick after the first; the boat really moved 12 m/s × (last stamp − first stamp). The largest "
             "nominal speed comes from the SHORTEST interval. Check with `drive --reveal`.")
def _():
    bug, p, err, vmax, ex = answers("BUG_SPEED_10HZ_MPS", "PREDICT_DRIVE", "NOMINAL_ERROR_M", "NOMINAL_SPEED_MAX_MPS",
                                    "EXPLAIN_DRIVE")
    b = number(bug, "BUG_SPEED_10HZ_MPS")
    c.ok(abs(b - 50.0) > 0.6, "BUG_SPEED_10HZ_MPS = 50 is the 5 Hz forwarder of the figure: the question asks a "
                              "forwarder at 10 Hz (`python3 run_gps.py bug --rate 10`)")
    c.ok(abs(b - 100.0) < 0.6, f"BUG_SPEED_10HZ_MPS = {bug}: the largest speed with a 10 Hz forwarder — 10 m in how "
                               "many seconds?")
    predicted("PREDICT_DRIVE", p)
    e = number(err, "NOMINAL_ERROR_M")
    c.ok(abs(e - 12.96) > 0.05, "NOMINAL_ERROR_M = 12.96 is the largest error (at 4.58 s): the question asks the "
                                "error at the LAST stamp")
    c.ok(abs(e) > 0.05, "NOMINAL_ERROR_M = 0 is YOUR receiver's error (REAL dt): read the NOMINAL column")
    c.ok(abs(e - 12.48) < 0.1, f"NOMINAL_ERROR_M = {err}: not what `drive` prints for NOMINAL dt at the last stamp")
    v = number(vmax, "NOMINAL_SPEED_MAX_MPS")
    c.ok(abs(v - 12.0) > 0.05, "NOMINAL_SPEED_MAX_MPS = 12.0 is the true speed (REAL dt): read the NOMINAL column")
    c.ok(abs(v - 14.29) < 0.1, f"NOMINAL_SPEED_MAX_MPS = {vmax}: the largest speed seen in the NOMINAL column")
    explained("EXPLAIN_DRIVE", ex, ([r"tick", r"miss", r"lost", r"skip", r"busy", r"stall", r"late", r"delay"],
                                    "what the busy second did to the ticks"),
              ([r"stamp", r"real time", r"real dt", r"\bdt\b", r"time", r"interval", r"0\.5"],
               "which time step the nominal receiver used"))


@c.test("Steps 4, 6 and 7: make_fix vs to_navsatfix, your node's rate, and why it stays right on a late computer",
        hint="Step 4: open navera_lite/ros/convert.py and compare to_navsatfix with your make_fix, field by field. "
             "Step 6: `ros2 topic hz /navera_lite/fix/gps` with the default node (1 Hz); copy the last 'average rate' "
             "and 'std dev'. Step 7: `python3 run_gps.py jitter`, then explain in your words.")
def _():
    fx, rate, std, p, ex = answers("EXPLAIN_FIX", "MEASURED_RATE_HZ", "MEASURED_STD_S", "PREDICT_JITTER",
                                   "EXPLAIN_JITTER")
    explained("EXPLAIN_FIX", fx, ([r"frame", r"service", r"status", r"altitude", r"alt_m", r"nan", r"valid"],
                                  "which field to_navsatfix fills differently"),
              ([r"source", r"estimate", r"day", r"night", r"celestial", r"no.?fix", r"invalid", r"unknown",
                r"not gps", r"other"], "why (where its values come from)"), min_words=6)
    r = number(rate, "MEASURED_RATE_HZ")
    c.ok(0.9 < r < 1.1, f"MEASURED_RATE_HZ = {rate}: the default node publishes about 1.0 Hz (rate_hz 1.0) — "
                        "measure it with `ros2 topic hz`" + (" (that is a period in s, not a rate)" if r > 5 else ""))
    s = number(std, "MEASURED_STD_S")
    c.ok(0.0 <= s < 0.1, f"MEASURED_STD_S = {std}: the 'std dev' line of `ros2 topic hz`, in seconds")
    predicted("PREDICT_JITTER", p)
    explained("EXPLAIN_JITTER", ex, ([r"stamp", r"real", r"measur", r"\bdt\b", r"interval", r"clock", r"time"],
                                     "that your node uses the real time between ticks"),
              ([r"nominal", r"fixed", r"0\.5", r"constant", r"wrong", r"would", r"speed"],
               "what a nominal-dt node would show"))


# ============================================================================== session 2 — sabotage
@c.test("Step 9: arbiter v0's four verdicts on your sabotaged receiver",
        hint="Run the four experiments of Step 9 and copy the state of each (\"FIX\", \"DEGRADED\" or \"NO_FIX\") "
             "from the status; age_s is one of the status values.")
def _():
    p, old, coarse, nos, fut, age, why_b = answers("PREDICT_SABOTAGE", "V0_OLD", "V0_COARSE", "V0_NO_SIGMA",
                                                   "V0_FUTURE", "AGE_FUTURE_S", "V0_COARSE_REASON")
    predicted("PREDICT_SABOTAGE", p)
    states = ("FIX", "DEGRADED", "NO_FIX")
    for name, v in (("V0_OLD", old), ("V0_COARSE", coarse), ("V0_NO_SIGMA", nos), ("V0_FUTURE", fut)):
        c.ok(isinstance(v, str) and v.strip().upper() in states,
             f"{name} = {v!r}: write one of \"FIX\", \"DEGRADED\", \"NO_FIX\" (with the quotes)")
    got = {"V0_OLD": old.strip().upper(), "V0_COARSE": coarse.strip().upper(), "V0_NO_SIGMA": nos.strip().upper(),
           "V0_FUTURE": fut.strip().upper()}
    want = {"V0_OLD": "NO_FIX", "V0_COARSE": "DEGRADED", "V0_NO_SIGMA": "FIX", "V0_FUTURE": "FIX"}
    wrong = [k for k in want if got[k] != want[k]]
    c.ok(not wrong, f"{', '.join(wrong)}: not what arbiter v0 says in that experiment — run it again and read the "
                    "state value (or the level) of the status, not your prediction")
    c.ok(isinstance(why_b, str) and why_b.strip().strip("'\"") == "gps: σ 40.0 m > 25.0 m",
         f"V0_COARSE_REASON = {why_b!r}: copy the `message` line of the status in experiment B exactly, as v0 "
         "writes it (without the outer quotes)")
    a = number(age, "AGE_FUTURE_S")
    c.ok(-31.5 < a < -28.0, f"AGE_FUTURE_S = {age}: the age_s value of the status in experiment D (now − stamp; a "
                            "stamp in the future makes it negative)")


@c.test("Step 9: you explain the holes of arbiter v0 and of its jump gate",
        hint="Which two verdicts are wrong? For each one, what does v0 compute (the age, the σ) and what does it never "
             "ask? Lesson §5. EXPLAIN_JUMP: elapsed = new stamp − stamp of the last trusted fix (mission 01's gate).")
def _():
    (ex, frozen, jump) = answers("EXPLAIN_HOLES", "FROZEN_S", "EXPLAIN_JUMP")
    f = number(frozen, "FROZEN_S")
    c.ok(20 <= f <= 45, f"FROZEN_S = {frozen}: how many seconds v0 kept saying FIX after you stopped the receiver of "
                        "experiment D: the time in brackets of the NO_FIX line in arbiter.log minus the number `date +%s` printed "
                        "when you stopped the receiver (Step 9) — not the time you waited")
    explained("EXPLAIN_HOLES", ex, ([r"future", r"negative", r"ahead", r"30"], "the stamp from the future"),
              ([r"unknown", r"no accuracy", r"not stated", r"zero", r"σ ?0", r"sigma ?0", r"0\.0", r"type"],
               "the receiver that states no accuracy"), min_words=15)
    explained("EXPLAIN_JUMP", jump, ([r"negative", r"minus", r"earlier", r"older", r"before", r"behind", r"back",
                                      r"slow", r"-5", r"−5"], "why the elapsed time is negative"),
              ([r"assum", r"forward", r"increas", r"order", r"always", r"later", r"newer", r"never go"],
               "what the gate assumes about stamps"))


@c.test("report.md: your memo to the NAVERA Lite team",
        hint="Three sections, at least 150 words of your own, no TODO left; quote your measured rate, the nominal "
             "error of Step 3 and the two wrong verdicts of Step 9.")
def _():
    c.ok(os.path.exists("report.md"), "report.md is missing")
    body = open("report.md", encoding="utf-8").read()
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok("TODO" not in body, "report.md still contains TODO")
    c.ok(len(words) >= 150, f"report.md has {len(words)} words of your own: at least 150, please")
    c.ok(re.search(r"\b(0\.9\d*|1\.0\d*|1)\s*Hz", body), "report.md does not quote the rate you measured (e.g. "
                                                          "\"1.000 Hz\")")
    c.ok(re.search(r"12\.[45]\d*\s*m", body), "report.md does not quote the nominal receiver's error of Step 3 "
                                               "(in metres)")
    c.ok(re.search(r"futur|negative", body, re.I) and re.search(r"unknown|no accuracy|not stat|σ ?0|sigma", body, re.I),
         "report.md section 3 does not name the two holes (the stamp from the future, the receiver that states no "
         "accuracy)")


c.milestone("builder", "TODO", "The judge", "Steps 0 and 3", "Steps 4, 6 and 7", label="Builder")
c.milestone("saboteur", "TODO", "The judge", "Step", "report", label="Saboteur")
c.run()
