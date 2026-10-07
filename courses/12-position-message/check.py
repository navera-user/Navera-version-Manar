import math
import time

from academy_check import Background, Checker, load_student, need, wait_for_messages

c = Checker()
STAMP = (1_800_000_000, 250_000_000)


def build(sigma=15.0):
    from builtin_interfaces.msg import Time
    (f,) = need(load_student("my_source.py"), "build_estimate")
    m = f(35.8, 10.6, sigma, Time(sec=STAMP[0], nanosec=STAMP[1]))
    from navera_msgs.msg import PositionEstimate
    c.ok(isinstance(m, PositionEstimate), f"build_estimate should return a PositionEstimate, got {type(m).__name__}")
    return m


def fault(name):
    (f,) = need(load_student("my_source.py"), "apply_fault")
    m = f(build(), name)
    c.ok(m is not None, "apply_fault must return the message (return est)")
    return m


def arbiter():
    """NAVERA's own rules, imported from your copy of the estimator."""
    from navera_estimator.nodes.estimator_node import EstimatorNode
    return EstimatorNode


@c.test("my_source.py loads without errors", hint="Run `python3 my_source.py` and read the error message.")
def _():
    need(load_student("my_source.py"), "build_estimate", "apply_fault", "MySource")


@c.test("TODO 1 — WHO and HOW: source, mode, valid, reason",
        hint="source = PositionEstimate.SOURCE_DAY_VISION, mode = PositionEstimate.MODE_MEASURED, "
             "valid = True and an empty reason for a good estimate.")
def _():
    from navera_msgs.msg import PositionEstimate as P
    m = build()
    c.eq(m.source, P.SOURCE_DAY_VISION, "source")
    c.eq(m.mode, P.MODE_MEASURED, "mode")
    c.eq(m.valid, True, "valid")
    c.eq(m.reason, "", "reason")


@c.test("TODO 1 — WHERE: position, NaN altitude, covariance of 15 m",
        hint="altitude = math.nan; position_covariance = [σ², 0, 0, 0, σ², 0, 0, 0, 0] with σ = sigma_m; "
             "type COVARIANCE_TYPE_APPROXIMATED.")
def _():
    from navera_msgs.msg import PositionEstimate as P
    m = build()
    c.near(m.latitude, 35.8, 1e-9, "latitude")
    c.near(m.longitude, 10.6, 1e-9, "longitude")
    c.ok(math.isnan(m.altitude), f"altitude is {m.altitude} — unknown must be math.nan (0.0 means sea level)")
    cov = list(m.position_covariance)
    c.near(cov[0], 225.0, 1e-6, "position_covariance[0]")
    c.near(cov[4], 225.0, 1e-6, "position_covariance[4]")
    c.ok(all(cov[i] == 0.0 for i in (1, 2, 3, 5, 6, 7)), f"off-diagonal numbers must be 0.0: {cov}")
    c.eq(m.position_covariance_type, P.COVARIANCE_TYPE_APPROXIMATED, "position_covariance_type")


@c.test("TODO 1 — WHEN and traceability: both stamps, producer, frame_index",
        hint="header.stamp = stamp AND sensor_stamp = stamp; frame_id, producer and model_id are texts; "
             "frame_index = -1.")
def _():
    m = build()
    c.eq((m.header.stamp.sec, m.header.stamp.nanosec), STAMP, "header.stamp (sec, nanosec)")
    c.eq((m.sensor_stamp.sec, m.sensor_stamp.nanosec), STAMP, "sensor_stamp (sec, nanosec)")
    c.ok(m.header.frame_id != "", "header.frame_id is empty")
    c.eq(m.producer, "my_source", "producer")
    c.ok(m.model_id != "", "model_id is empty")
    c.eq(m.frame_index, -1, "frame_index")


@c.test("TODO 1 — NAVERA's own arbiter code finds your estimate sane, with a stated 15 m",
        hint="The check calls EstimatorNode._sane() and _stated_sigma() from your NAVERA copy. Look at them in "
             "estimator_node.py: a finite position, a covariance that is one, a defined covariance type.")
def _():
    E = arbiter()
    m = build()
    c.ok(E._sane(m), "EstimatorNode._sane(your message) is False")
    s = E._stated_sigma(m)
    c.ok(s is not None, "EstimatorNode._stated_sigma(your message) is None: no stated accuracy")
    c.near(s, 15.0, 1e-6, "the sigma NAVERA reads from your covariance")


@c.test("TODO 2 — faults 'nan' and 'bad_cov' make the estimate insane (and change nothing else)",
        hint="'nan': latitude = math.nan. 'bad_cov': position_covariance[0] = -(value) - 1.0. "
             "Use if / elif on the fault name.")
def _():
    E = arbiter()
    m = fault("nan")
    c.ok(math.isnan(m.latitude), "fault 'nan': latitude is not NaN")
    c.ok(not E._sane(m), "fault 'nan': NAVERA still finds it sane")
    m = fault("bad_cov")
    c.ok(m.position_covariance[0] < 0, "fault 'bad_cov': position_covariance[0] is not negative")
    c.ok(math.isfinite(m.latitude) and m.valid, "fault 'bad_cov' must not change the position or valid")
    c.ok(not E._sane(m), "fault 'bad_cov': NAVERA still finds it sane")
    m = fault("none")
    c.ok(E._sane(m) and m.valid, "fault 'none' must leave a good estimate")


@c.test("TODO 2 — faults 'stale', 'invalid', 'replayed', 'unknown_cov'",
        hint="'stale': BOTH stamps 10 s earlier (sec - 10). 'invalid': valid False + a reason. "
             "'replayed': mode MODE_REPLAYED. 'unknown_cov': 9 zeros and COVARIANCE_TYPE_UNKNOWN.")
def _():
    from navera_msgs.msg import PositionEstimate as P
    E = arbiter()
    m = fault("stale")
    c.eq(m.header.stamp.sec, STAMP[0] - 10, "fault 'stale': header.stamp.sec")
    c.eq(m.sensor_stamp.sec, STAMP[0] - 10, "fault 'stale': sensor_stamp.sec")
    m = fault("invalid")
    c.ok(m.valid is False, "fault 'invalid': valid is not False")
    c.ok(m.reason.strip() != "", "fault 'invalid': give a reason for humans")
    m = fault("replayed")
    c.eq(m.mode, P.MODE_REPLAYED, "fault 'replayed': mode")
    m = fault("unknown_cov")
    c.eq(m.position_covariance_type, P.COVARIANCE_TYPE_UNKNOWN, "fault 'unknown_cov': position_covariance_type")
    c.ok(E._stated_sigma(m) is None and E._sane(m), "fault 'unknown_cov': the covariance must be 9 zeros")


RES = {}


def verdicts():
    """Run NAVERA's estimator once, and your source with several faults; keep the last status of each."""
    if not RES:
        from navera_msgs.msg import NavStatus, PositionEstimate
        RES["_"] = None
        with Background("ros2 run navera_estimator estimator_node.py", settle=2.5):
            for f in ("none", "stale", "nan", "unknown_cov"):
                with Background(f"python3 -u my_source.py {f}", settle=2.0) as bg:
                    time.sleep(2.5)
                    msgs = wait_for_messages("/navera/nav_status", NavStatus, count=3, timeout=6)
                    pos = wait_for_messages("/navera/position", PositionEstimate, count=1, timeout=2.5) \
                        if f == "none" else []
                RES[f] = (msgs[-1] if msgs else None, pos, bg.output())
    return RES


def status_of(f):
    st, pos, out = verdicts()[f]
    c.ok(st is not None, "no /navera/nav_status message — the estimator did not run. Your node printed:\n"
         + out[-500:])
    return st, pos


@c.test("live — `python3 my_source.py`: NAVERA says FIX from day vision and publishes your position",
        hint="Run the estimator and your source, then `ros2 topic echo /navera/nav_status --field reason`. "
             "A FIX needs valid, MEASURED, fresh, sane, and a stated sigma ≤ 25 m.")
def _():
    from navera_msgs.msg import NavStatus
    st, pos = status_of("none")
    c.ok(st.state == NavStatus.STATE_FIX and st.active_source == NavStatus.SOURCE_DAY_VISION,
         f"state {st.state}, source {st.active_source}, reason: {st.reason!r}")
    c.ok(pos and abs(pos[0].latitude - 35.8256) < 1e-6 and pos[0].producer == "navera_estimator",
         "no /navera/position with your latitude (35.8256) — is LAT still 35.8256?")


@c.test("live — `python3 my_source.py stale`: refused as stale",
        hint="The arbiter judges the age on sensor_stamp. Both stamps must be 10 s old.")
def _():
    from navera_msgs.msg import NavStatus
    good, _ = status_of("none")
    c.ok(good.state == NavStatus.STATE_FIX, "first make `python3 my_source.py` (no fault) reach FIX — "
                                            "a broken estimate is refused for many reasons")
    st, _ = status_of("stale")
    c.ok(st.state == NavStatus.STATE_NO_FIX and "day: stale" in st.reason,
         f"state {st.state}, reason: {st.reason!r} — expected NO_FIX with `day: stale (...)`")


@c.test("live — `python3 my_source.py nan`: refused as non-finite",
        hint="A NaN latitude must make the arbiter say `day: non-finite position or covariance`.")
def _():
    from navera_msgs.msg import NavStatus
    st, _ = status_of("nan")
    c.ok(st.state == NavStatus.STATE_NO_FIX and "non-finite" in st.reason,
         f"state {st.state}, reason: {st.reason!r}")


@c.test("live — `python3 my_source.py unknown_cov`: used, but DEGRADED (uncertainty unknown)",
        hint="With COVARIANCE_TYPE_UNKNOWN the position is usable but NAVERA cannot know how good it is.")
def _():
    from navera_msgs.msg import NavStatus
    st, _ = status_of("unknown_cov")
    c.ok(st.state == NavStatus.STATE_DEGRADED and "uncertainty unknown" in st.reason,
         f"state {st.state}, reason: {st.reason!r}")


WANT = {"REASON_GOOD": ["day vision fix"], "REASON_NAN": ["non-finite"], "REASON_BAD_COV": ["non-finite"],
        "REASON_STALE": ["stale", ">3.0s"], "REASON_INVALID": ["invalid", "lens covered"],
        "REASON_REPLAYED": ["replayed not usable"], "REASON_UNKNOWN_COV": ["uncertainty unknown"],
        "REASON_SIGMA_40": ["40 m > 25 m"]}


@c.test("verdicts.py — you recorded the arbiter's reason for each run",
        hint="Run the estimator, then your source with each fault, and copy the `day…` part of "
             "`ros2 topic echo /navera/nav_status --field reason` into verdicts.py.")
def _():
    m = load_student("verdicts.py")
    for name, words in WANT.items():
        (v,) = need(m, name)
        v = str(v)
        c.ok(v.strip() != "", f"{name} is still empty")
        c.ok(all(w in v for w in words), f"{name} = {v!r} is not what the arbiter says for this case")
    c.ok(abs(float(getattr(load_student("my_source.py"), "SIGMA_M", 0)) - 15.0) < 1e-9,
         "put SIGMA_M back to 15.0 in my_source.py")


@c.test("verdicts.py — quiz Q1 and Q2", hint="Read the warning box 'The other side of one rule' in the course.")
def _():
    m = load_student("verdicts.py")
    for q in ("Q1", "Q2"):
        (v,) = need(m, q)
        c.ok(str(v).strip().lower() == "b", f"{q} = {v!r} is not the right answer")


c.run()
