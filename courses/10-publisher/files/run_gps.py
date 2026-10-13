"""run_gps.py — runs YOUR fake GNSS receiver (navera_lite/ros/gps_node.py) on the lab's situations.

    python3 run_gps.py bug [--rate 10]   the "stopped, then jumped" bug, replayed (no code)          (Step 0)
    python3 run_gps.py test       TODO 1–3 on their docstring examples and a few traps; state of 4–6
    python3 run_gps.py drive [--reveal]  your step() on a busy computer's real tick times            (Step 3)
    python3 run_gps.py node       your node is built and inspected, its timer never fires (TODO 4–5) (Step 5)
    python3 run_gps.py jitter     your node runs 12 s on a computer that is late at random (TODO 4–6) (Step 7)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import math
import os
import random
import sys
import time

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

gps = rk.load_student("navera_lite.ros.gps_node")
geo = rk.load_student("navera_lite.geo")             # mission 06's part, finished: offset, haversine_m, enu_flat
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if isinstance(e, AssertionError) and "of type 'float'" in s:
        return (" — a ROS float field got an int (or a list holding ints): write 9.0, not 9, and float(x) for "
                "the inputs (lesson §4, the type trap)")
    if isinstance(e, AssertionError) and "of type 'int'" in s and "covariance_type" in s:
        return " — position_covariance_type takes an int such as 1, not a float or a list"
    if isinstance(e, TypeError) and "cannot unpack non-iterable NoneType" in s:
        return " — a function you call returned None: is one of your TODOs still a stub (TODO 1 or 2)?"
    if isinstance(e, TypeError) and "not supported between instances of 'NoneType'" in s:
        return (" — a value is None (an INPUT such as sigma_m = None?) and was compared with a number: test "
                "`x is None` FIRST, before any comparison (🧰 box of Step 4)")
    if isinstance(e, TypeError) and "unsupported operand" in s and "'NoneType'" in s and "-" in s:
        return (" — a value is None: an input such as sigma_m = None, or self.last_t on the first tick "
                "(dt is 0.0 then, TODO 6 docstring)")
    return _kit_hint(e)


rk._hint = _hint
OUT = "out"
SOUSSE = (35.8256, 10.6084)
SINGAPORE = (1.2644, 103.8200)                       # a survey boat leaves a harbour (Step 3)


def short(v, n=60):
    r = repr(v)
    return r if len(r) <= n else r[:n - 4] + " …" + r[-1]


def dist_dir(lat1, lon1, lat2, lon2):
    """(metres, direction in degrees clockwise from north) from point 1 to point 2, on a local flat map."""
    e, n = geo.enu_flat(lat1, lon1, lat2, lon2)
    return math.hypot(e, n), math.degrees(math.atan2(e, n)) % 360.0


# =============================================================================== Step 0: the bug
def bug(rate=5):
    """A GPS gives one fix per second on a vehicle at 10 m/s. A forwarder re-sends the LATEST fix `rate` times a
    second, each time with a fresh stamp (the bug). What does a listener compute from consecutive messages?"""
    v = 10.0
    print("A vehicle flies east at 10 m/s. Its GPS measures one position per second.")
    print(f"A forwarder sends the LATEST position {rate} times per second, stamped with the time it SENDS it.\n")
    print(f"{'sent at (s)':>11}  {'position (m east)':>17}  {'speed a listener computes (m/s)':>32}")
    rows, prev = [], None
    for k in range(3 * rate + 1):
        t = round(k / rate, 3)
        x = v * math.floor(t + 1e-9)                 # the latest measurement: taken at the last whole second
        speed = None if prev is None else (x - prev[1]) / (t - prev[0])
        rows.append((t, x, speed))
        print(f"{t:>11.2f}  {x:>17.1f}  {'' if speed is None else f'{speed:>32.1f}'}")
        prev = (t, x)
    print("\nSame positions, each sent ONCE, stamped when it was MEASURED: 0 s → 0 m, 1 s → 10 m, 2 s → 20 m, 3 s → 30 m")
    print("→ the listener computes 10.0 m/s every time.")
    plt = rk.plt_or_none()
    if plt:
        os.makedirs(OUT, exist_ok=True)
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
        ts = [r[0] for r in rows]
        ax[0].plot(ts, [v * t for t in ts], "--", color="#888", label="where the vehicle really is")
        ax[0].step(ts, [r[1] for r in rows], where="post", color="#d64545", label="what the listener is told")
        ax[0].plot(ts, [r[1] for r in rows], "o", color="#d64545", ms=4)
        ax[0].set_xlabel("time (s)"); ax[0].set_ylabel("position east (m)"); ax[0].legend(fontsize=8)
        ax[1].bar(ts[1:], [r[2] for r in rows[1:]], width=0.6 / rate, color="#d64545")
        ax[1].axhline(v, ls="--", color="#888"); ax[1].text(0.1, v + 1.5, "true speed 10 m/s", fontsize=8)
        ax[1].set_xlabel("time (s)"); ax[1].set_ylabel("speed from two messages (m/s)")
        fig.suptitle(f'"Stopped, then jumped": one measurement re-sent {rate} times per second with fresh stamps')
        fig.tight_layout(); fig.savefig(os.path.join(OUT, "bug.png"), dpi=90)
        rk.saved(os.path.join(OUT, "bug.png"))


# =============================================================================== test
def test():
    print("Each TODO on its docstring example (and a few traps).\n")
    ok_all = True

    def line(ok, label, detail):
        nonlocal ok_all
        ok_all = ok_all and ok
        print(f"  {'✔' if ok else '✘'} {label}: {detail}")

    # TODO 1
    v, err = rk.call(gps, "step", SOUSSE[0], SOUSSE[1], 10.0, 90.0, 0.62)
    if err:
        line(False, "TODO 1 step", err)
    elif not (isinstance(v, (tuple, list)) and len(v) == 2):
        line(False, "TODO 1 step", f"must return (lat, lon), two numbers — it returned {short(v)}")
    else:
        d, h = dist_dir(SOUSSE[0], SOUSSE[1], v[0], v[1])
        good = abs(d - 6.2) < 0.01 and abs(h - 90.0) < 0.5
        why = "" if good else (f" — expected 6.20 m towards 90° (east)" + (
            "; north and east are swapped: did you give geo.offset north before east? It is offset(lat, lon, e_m, "
            "n_m), east FIRST (or: east = v·sin h, north = v·cos h)"
            if abs(h - 0.0) < 0.5 or abs(h - 360.0) < 0.5 else "") + (
            "; is dt_s used? distance = speed × dt" if abs(d - 10.0) < 0.05 else ""))
        line(good, "TODO 1 step", f"step(35.8256, 10.6084, 10.0, 90.0, 0.62) → ({v[0]:.6f}, {v[1]:.6f}), "
                                  f"{d:.2f} m towards {h:.1f}°{why}")
        v2, err2 = rk.call(gps, "step", SOUSSE[0], SOUSSE[1], 10.0, 90.0, -1.0)
        line(err2 is not None and "ValueError" in err2, "TODO 1 step, dt_s = −1.0",
             "ValueError ✔" if err2 and "ValueError" in err2 else
             f"must raise ValueError (time does not run backwards), got {short(v2) if not err2 else err2}")

    # TODO 2
    v, err = rk.call(gps, "covariance_from_sigma", 3.0)
    want = [9.0, 0.0, 0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 36.0]
    if err:
        line(False, "TODO 2 covariance_from_sigma", err)
    elif not (isinstance(v, (tuple, list)) and len(v) == 2):
        line(False, "TODO 2 covariance_from_sigma", f"must return (cov9, cov_type) — it returned {short(v)}")
    else:
        cov, typ = v
        floats = isinstance(cov, (list, tuple)) and all(isinstance(x, float) for x in cov)
        good = floats and list(cov) == want and typ == 1
        why = ""
        if isinstance(cov, (list, tuple)) and not floats:
            why = " — every number must be a float (0.0, not 0): ROS refuses ints in a float field"
        elif isinstance(cov, (list, tuple)) and len(cov) == 9 and abs(cov[0] - 3.0) < 1e-9:
            why = " — σ is a standard deviation in metres; the covariance holds VARIANCES, σ², in m²"
        elif isinstance(cov, (list, tuple)) and len(cov) == 9 and abs(cov[8] - 9.0) < 1e-9:
            why = " — Up gets (2σ)², not σ²"
        elif typ == 2:
            why = " — the type is APPROXIMATED (1): a stated σ is an approximation, not a known diagonal (lesson §4)"
        line(good, "TODO 2 covariance_from_sigma(3.0)", f"{short(cov, 70)}, type {typ!r}{why}")
        for bad in (None, 0.0, float("nan")):
            v, err = rk.call(gps, "covariance_from_sigma", bad)
            if err:
                line(False, f"TODO 2 covariance_from_sigma({bad})", err)
                continue
            cov, typ = v
            good = list(cov) == [0.0] * 9 and typ == 0 and all(isinstance(x, float) for x in cov)
            line(good, f"TODO 2 covariance_from_sigma({bad})",
                 f"{short(cov, 50)}, type {typ!r}" + ("" if good else " — nothing is stated: nine 0.0 and "
                                                     "COV_UNKNOWN (0), never an invented number"))

    # TODO 3
    v, err = rk.call(gps, "make_fix", SOUSSE[0], SOUSSE[1], 40.0, 3.0, 100.5)
    if err:
        line(False, "TODO 3 make_fix", err)
    elif type(v).__name__ != "NavSatFix":
        line(False, "TODO 3 make_fix", f"must return a NavSatFix message — it returned {short(v)}")
    else:
        problems = []
        st = v.header.stamp
        if (st.sec, st.nanosec) != (100, 500000000):
            problems.append(f"stamp is sec={st.sec}, nanosec={st.nanosec} (use s_to_stamp(stamp_s))")
        if v.header.frame_id != "gps":
            problems.append(f"frame_id is {v.header.frame_id!r}, not 'gps'")
        if v.status.service != 1:
            problems.append(f"status.service is {v.status.service} (SERVICE_GPS is 1)")
        if v.status.status != 0:
            problems.append(f"status.status is {v.status.status} (STATUS_FIX is 0)")
        if abs(v.latitude - SOUSSE[0]) > 1e-9 or abs(v.longitude - SOUSSE[1]) > 1e-9 or v.altitude != 40.0:
            problems.append(f"position is ({v.latitude}, {v.longitude}, {v.altitude})")
        if list(v.position_covariance) != [9.0, 0.0, 0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 36.0]:
            problems.append(f"covariance is {list(v.position_covariance)}")
        if v.position_covariance_type != 1:
            problems.append(f"covariance type is {v.position_covariance_type}")
        line(not problems, "TODO 3 make_fix(35.8256, 10.6084, 40.0, 3.0, 100.5)",
             "every field ✔" if not problems else "; ".join(problems))
        v, err = rk.call(gps, "make_fix", 36, 10, 40, 2.0, 7.0)
        line(err is None, "TODO 3 make_fix(36, 10, 40, 2.0, 7.0) — whole numbers as inputs",
             "accepted ✔" if err is None else err)

    # TODO 4–6: methods of a node — the runner can only tell whether they are still stubs here
    for todo, name in ((4, "declare_all"), (5, "start"), (6, "on_timer")):
        f = getattr(gps.FakeGps, name, None)
        stub = f is None or rk.is_stub(f)
        print(f"  {'·' if stub else '✔'} TODO {todo} FakeGps.{name}: "
              + ("still the stub" if stub else "written — try it with `python3 run_gps.py "
                 + ("node`" if todo < 6 else "jitter`")))
    print("\nAll ✔ above: TODO 1–3 work on their examples. ✔ Check my work also tries numbers they have never seen."
          if ok_all else "\nFix the ✘ lines first (the first one first).")


# =============================================================================== Step 3: drive
# The instants (s) at which a 2 Hz timer really called on_timer on a busy computer: each call a little late,
# and once the computer was busy for about 1.5 s (the timer does not make up the ticks it missed).
DRIVE_TICKS = [0.00, 0.53, 1.08, 1.50, 2.06, 2.51, 3.12, 4.58, 5.02, 5.55, 6.04]
DRIVE_SPEED, DRIVE_HEADING, DRIVE_PERIOD = 12.0, 45.0, 0.5


def drive(reveal=False):
    lat0, lon0 = SINGAPORE
    v, h = DRIVE_SPEED, DRIVE_HEADING
    print(f"A survey boat leaves Singapore's harbour at {v} m/s on heading {h}°. Timer: {1 / DRIVE_PERIOD:.0f} Hz "
          f"(period {DRIVE_PERIOD} s).")
    print("Two receivers run on the same busy computer, at the same instants:")
    print("  REAL dt    = YOUR step(), with dt = the real time since the previous tick")
    print(f"  NOMINAL dt = step() with dt = {DRIVE_PERIOD} s every time (what the timer was asked for)"
          + ("" if reveal else "   — hidden (?) until you run `drive --reveal`") + "\n")
    lat_r, lon_r = lat0, lon0
    lat_n, lon_n = lat0, lon0
    rows = []
    for k, t in enumerate(DRIVE_TICKS):
        dt = 0.0 if k == 0 else t - DRIVE_TICKS[k - 1]
        p = rk.need_ok(gps, "step", lat_r, lon_r, v, h, dt, n=2)
        lat_r, lon_r = p
        if k > 0:
            lat_n, lon_n = rk.need_ok(gps, "step", lat_n, lon_n, v, h, DRIVE_PERIOD, n=2)
        truth = geo.offset(lat0, lon0, v * t * math.sin(math.radians(h)), v * t * math.cos(math.radians(h)))
        err_r = geo.haversine_m(lat_r, lon_r, *truth)
        err_n = geo.haversine_m(lat_n, lon_n, *truth)
        rows.append((t, dt, (lat_r, lon_r), (lat_n, lon_n), err_r, err_n))
    print(f"{'stamp (s)':>9} {'real dt':>8} | {'REAL: error (m)':>15} {'speed seen':>10} | "
          f"{'NOMINAL: error (m)':>18} {'speed seen':>10}")
    sp_r, sp_n = [], []
    for k, (t, dt, pr, pn, er, en) in enumerate(rows):
        s_r = s_n = ""
        if k > 0:
            dt_stamp = t - rows[k - 1][0]
            a = geo.haversine_m(*rows[k - 1][2], *pr) / dt_stamp
            b = geo.haversine_m(*rows[k - 1][3], *pn) / dt_stamp
            sp_r.append(a); sp_n.append(b)
            s_r, s_n = f"{a:10.1f}", (f"{b:10.1f}" if reveal else "?")
        e_n = f"{en:18.2f}" if reveal else "?"
        print(f"{t:9.2f} {dt:8.2f} | {er:15.2f} {s_r:>10} | {e_n:>18} {s_n:>10}")
    print("\n(speed seen = what a listener computes from two consecutive fixes: distance ÷ difference of the stamps)")
    if max(r[4] for r in rows) > 0.05:
        print("\n✘ YOUR step() with the real dt should stay on the truth (error about 0.00 m). Run `python3 run_gps.py test`.")
    if not reveal:
        print(f"\nAfter {DRIVE_TICKS[-1]:.2f} s: REAL dt is {rows[-1][4]:.2f} m from the truth. The NOMINAL columns are "
              "hidden: compute them from the stamps (lab Step 3), then run `python3 run_gps.py drive --reveal`.")
        return
    print(f"\nAfter {DRIVE_TICKS[-1]:.2f} s: REAL dt is {rows[-1][4]:.2f} m from the truth, NOMINAL dt "
          f"{rows[-1][5]:.2f} m. Speeds seen: REAL {min(sp_r):.1f}–{max(sp_r):.1f} m/s, "
          f"NOMINAL {min(sp_n):.1f}–{max(sp_n):.1f} m/s.")
    plt = rk.plt_or_none()
    if plt:
        os.makedirs(OUT, exist_ok=True)
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
        ts = [r[0] for r in rows]
        ax[0].plot(ts, [r[4] for r in rows], "o-", color="#2f7a2f", label="real dt (yours)")
        ax[0].plot(ts, [r[5] for r in rows], "s-", color="#d64545", label=f"nominal dt = {DRIVE_PERIOD} s")
        ax[0].set_xlabel("stamp (s)"); ax[0].set_ylabel("distance from the truth at the stamp (m)")
        ax[0].legend(fontsize=8)
        ax[1].plot(ts[1:], sp_r, "o-", color="#2f7a2f", label="real dt")
        ax[1].plot(ts[1:], sp_n, "s-", color="#d64545", label="nominal dt")
        ax[1].axhline(v, ls="--", color="#888")
        ax[1].set_xlabel("stamp (s)"); ax[1].set_ylabel("speed a listener computes (m/s)"); ax[1].legend(fontsize=8)
        fig.suptitle("The same busy computer, two ways to integrate"); fig.tight_layout()
        fig.savefig(os.path.join(OUT, "drive.png"), dpi=90)
        rk.saved(os.path.join(OUT, "drive.png"))


# =============================================================================== ROS helpers
def ros_args(extra):
    return ["--ros-args"] + extra if extra and extra[0] != "--ros-args" else extra


def where_in_student(e):
    """'navera_lite/ros/gps_node.py line N, in on_timer' for the deepest frame in the student's file."""
    import traceback
    mine = os.path.abspath(gps.__file__)
    frames = [fr for fr in traceback.extract_tb(e.__traceback__) if os.path.abspath(fr.filename) == mine]
    if not frames:
        return ""
    fr = frames[-1]
    return f" (navera_lite/ros/gps_node.py line {fr.lineno}, in {fr.name})"


def plain(e, during):
    if isinstance(e, NotImplementedError):
        return f"{during}: {e} is not written yet (it still raises NotImplementedError)."
    return f"{during}: {type(e).__name__}: {e}{where_in_student(e)}{_hint(e)}"


def build(node_class, args):
    import rclpy
    rclpy.init(args=ros_args(args))
    try:
        return node_class()
    except Exception as e:
        rclpy.try_shutdown()
        sys.exit(plain(e, "Building the node (its __init__ calls your declare_all() then start()) failed"))


# =============================================================================== Step 5: node
def node(args):
    import rclpy
    from rclpy.qos import ReliabilityPolicy

    class Inspected(gps.FakeGps):
        calls = 0

        def on_timer(self):                          # replaces YOUR on_timer: it only counts calls
            Inspected.calls += 1

    n = build(Inspected, args)
    print(f"Your node, built with {' '.join(args) if args else 'no -p (the defaults)'}; its timer never fires here.\n")
    ok_all = True

    def line(ok, label, detail):
        nonlocal ok_all
        ok_all = ok_all and ok
        print(f"  {'✔' if ok else '✘'} {label}: {detail}")

    missing = [k for k in gps.DEFAULTS if not n.has_parameter(k)]
    line(not missing, f"TODO 4 parameters ({len(gps.DEFAULTS)} in DEFAULTS)",
         "all declared: " + ", ".join(f"{k}={n.get_parameter(k).value!r}" for k in gps.DEFAULTS)
         if not missing else f"not declared: {', '.join(missing)}")
    if not missing:
        lat, lon = n.get_parameter("start_lat").value, n.get_parameter("start_lon").value
        line(n.lat == lat and n.lon == lon, "TODO 4 start position",
             f"self.lat, self.lon = {n.lat}, {n.lon}" + ("" if (n.lat, n.lon) == (lat, lon) else
                                                       f" — the parameters say ({lat}, {lon}): read them"))
    pubs = [p for p in n.publishers if p.topic_name.endswith("navera_lite/fix/gps")]
    if n.pub is None or not pubs:
        line(False, "TODO 5 publisher", "self.pub is None, or no publisher on navera_lite/fix/gps (use TOPIC)")
    else:
        p = pubs[0]
        rel = p.qos_profile.reliability == ReliabilityPolicy.RELIABLE
        line(p.msg_type.__name__ == "NavSatFix" and rel, "TODO 5 publisher",
             f"{p.msg_type.__name__} on {p.topic_name}, {p.qos_profile.reliability.name}, depth {p.qos_profile.depth}"
             + ("" if rel else " — use qos.FIX_QOS (RELIABLE)"))
    timers = [t for t in n.timers]
    if Inspected.calls:
        line(False, "TODO 5 timer", "on_timer was CALLED while the node was built: give the method itself, "
                                    "self.on_timer, without () (lesson §1)")
    elif not timers:
        line(False, "TODO 5 timer", "no timer was created")
    else:
        period = timers[0].timer_period_ns * 1e-9
        rate = n.get_parameter("rate_hz").value if n.has_parameter("rate_hz") else None
        good = rate is not None and abs(period - 1.0 / rate) < 1e-6
        line(good, "TODO 5 timer", f"period {period:.3f} s" + (f" = 1 / rate_hz ({rate}) ✔" if good else
                                                             f" — rate_hz is {rate}: the period is 1 / rate_hz"))
    print("\n" + ("Next: write TODO 6 and run the node for real (lab Step 6)." if ok_all else "Fix the ✘ lines."))
    n.destroy_node()
    rclpy.try_shutdown()


# =============================================================================== Step 7: jitter
JITTER_RATE, JITTER_SPEED, JITTER_RUN_S = 2.0, 10.0, 12.0
JITTER_OFFSET, JITTER_SIGMA = -2.0, 1.5
STALL_AT, STALL_S = 9, 1.3


def jitter(args):
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import NavSatFix
    from navera_lite.ros.qos import FIX_QOS
    rng = random.Random()

    class Late(gps.FakeGps):
        ticks = 0

        def on_timer(self):                          # a busy computer: YOUR on_timer starts late
            Late.ticks += 1
            time.sleep(STALL_S if Late.ticks == STALL_AT else rng.uniform(0.0, 0.2))
            super().on_timer()

    base = ["-p", f"rate_hz:={JITTER_RATE}", "-p", f"speed_mps:={JITTER_SPEED}", "-p", "heading_deg:=90.0",
            "-p", f"stamp_offset_s:={JITTER_OFFSET}", "-p", f"sigma_m:={JITTER_SIGMA}"]
    n = build(Late, base + args)
    got, recv = [], []
    listener = rclpy.create_node("jitter_listener")
    listener.create_subscription(NavSatFix, "navera_lite/fix/gps",
                                 lambda m: (got.append(m), recv.append(time.time())), FIX_QOS)
    ex = SingleThreadedExecutor()
    ex.add_node(n); ex.add_node(listener)
    print(f"Your node runs {JITTER_RUN_S:.0f} s at {JITTER_RATE} Hz, {JITTER_SPEED} m/s east. Each call of your on_timer "
          f"starts 0–0.2 s late, and call {STALL_AT} is {STALL_S} s late (the computer was busy). Its knobs: "
          f"stamp_offset_s {JITTER_OFFSET}, sigma_m {JITTER_SIGMA}…\n")
    end = time.monotonic() + JITTER_RUN_S
    try:
        while time.monotonic() < end:
            ex.spin_once(timeout_sec=0.05)
    except Exception as e:
        sys.exit(plain(e, f"Your on_timer() stopped at tick {Late.ticks}"))
    finally:
        n.destroy_node(); listener.destroy_node(); rclpy.try_shutdown()
    if len(got) < 3:
        sys.exit(f"Only {len(got)} fix(es) arrived in {JITTER_RUN_S:.0f} s: does on_timer publish with self.pub.publish(…)?")
    st = [m.header.stamp.sec + m.header.stamp.nanosec * 1e-9 for m in got]
    t0, (lat0, lon0) = st[0], (got[0].latitude, got[0].longitude)
    dts = [b - a for a, b in zip(st, st[1:])]
    print(f"{'fix':>3} {'stamp − first (s)':>17} {'interval (s)':>12} {'moved (m)':>9} {'speed seen':>10} "
          f"{'error at stamp (m)':>18}")
    speeds, errs = [], []
    for k, m in enumerate(got):
        truth = geo.offset(lat0, lon0, JITTER_SPEED * (st[k] - t0), 0.0)
        err = geo.haversine_m(m.latitude, m.longitude, *truth)
        errs.append(err)
        if k == 0:
            print(f"{k + 1:>3} {0.0:17.3f}")
            continue
        d = geo.haversine_m(got[k - 1].latitude, got[k - 1].longitude, m.latitude, m.longitude)
        speeds.append(d / dts[k - 1] if dts[k - 1] > 0 else float("inf"))
        print(f"{k + 1:>3} {st[k] - t0:17.3f} {dts[k - 1]:12.3f} {d:9.2f} {speeds[-1]:10.2f} {err:18.2f}")
    mean = sum(dts) / len(dts)
    std = math.sqrt(sum((x - mean) ** 2 for x in dts) / len(dts))
    nominal = [JITTER_SPEED / JITTER_RATE / x for x in dts]
    print(f"\nIntervals between stamps: mean {mean:.3f} s, min {min(dts):.3f}, max {max(dts):.3f}, std {std:.3f} s "
          f"({len(got)} fixes).")
    print(f"YOUR node: speeds seen {min(speeds):.2f}–{max(speeds):.2f} m/s, largest error at a stamp {max(errs):.2f} m.")
    print(f"A NOMINAL-dt node at the same instants: speeds seen {min(nominal):.1f}–{max(nominal):.1f} m/s.")
    if max(errs) > 0.5 or max(abs(s - JITTER_SPEED) for s in speeds) > 0.2:
        print("\n✘ Your fixes are not where the vehicle was at their stamps: is dt the REAL time since the previous "
              "tick, and is the stamp the same 'now'? (lesson §3)")
    else:
        print("\n✔ Every fix is where the vehicle was at its stamp, whatever the delays.")
    lag = sum(r - t for r, t in zip(recv, st)) / len(st)
    if abs(lag + JITTER_OFFSET) < 0.6:
        print(f"✔ stamp_offset_s {JITTER_OFFSET}: the stamps are {lag:.2f} s behind the clock.")
    else:
        print(f"✘ stamp_offset_s {JITTER_OFFSET} is ignored: the stamps are {lag:.2f} s behind the clock, not about "
              f"{-JITTER_OFFSET:.1f} s. The stamp is now + stamp_offset_s, read at every tick (Step 6, hint 3).")
    cov0 = got[-1].position_covariance[0]
    print(f"{'✔' if abs(cov0 - JITTER_SIGMA ** 2) < 1e-9 else '✘'} sigma_m {JITTER_SIGMA}: covariance[0] is {cov0}"
          + ("" if abs(cov0 - JITTER_SIGMA ** 2) < 1e-9 else f", not {JITTER_SIGMA ** 2}: pass sigma_m from the parameters"))
    plt = rk.plt_or_none()
    if plt:
        os.makedirs(OUT, exist_ok=True)
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
        ax[0].bar(range(2, len(got) + 1), dts, color="#0b6e8a")
        ax[0].axhline(1 / JITTER_RATE, ls="--", color="#888")
        ax[0].set_xlabel("fix"); ax[0].set_ylabel("interval between stamps (s)")
        ax[1].plot(range(2, len(got) + 1), speeds, "o-", color="#2f7a2f", label="your node")
        ax[1].plot(range(2, len(got) + 1), nominal, "s-", color="#d64545", label="nominal dt")
        ax[1].axhline(JITTER_SPEED, ls="--", color="#888")
        ax[1].set_xlabel("fix"); ax[1].set_ylabel("speed a listener computes (m/s)"); ax[1].legend(fontsize=8)
        fig.suptitle("Your node on a busy computer"); fig.tight_layout()
        fig.savefig(os.path.join(OUT, "jitter.png"), dpi=90)
        rk.saved(os.path.join(OUT, "jitter.png"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "bug":
        rate = 5
        if "--rate" in sys.argv:
            try:
                rate = int(sys.argv[sys.argv.index("--rate") + 1])
            except (IndexError, ValueError):
                sys.exit("--rate needs a whole number of messages per second, e.g. --rate 10")
            if not 2 <= rate <= 50:
                sys.exit("--rate must be between 2 and 50")
        bug(rate)
    elif mode == "test":
        test()
    elif mode == "drive":
        drive("--reveal" in sys.argv)
    elif mode == "node":
        node(sys.argv[2:])
    elif mode == "jitter":
        jitter(sys.argv[2:])
    else:
        print(__doc__)
