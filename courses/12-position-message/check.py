import json
import math
import re
import time

from academy_check import Background, Checker, load_student, need, wait_for_messages

c = Checker()
STAMP = (1_800_000_000, 250_000_000)
REF_COV = [83.25, 81.8394, 0.0, 81.8394, 177.75, 0.0, 0.0, 0.0, 36.0]


def src():
    return load_student("my_source.py")


def E():
    """NAVERA's own arbiter class, imported from the student's NAVERA copy."""
    from navera_estimator.nodes.estimator_node import EstimatorNode
    return EstimatorNode


def build(cov=None):
    from builtin_interfaces.msg import Time
    from navera_msgs.msg import PositionEstimate as P
    (b, ec) = need(src(), "build_estimate", "enu_covariance")
    m = b(23.5880, 58.3829, cov if cov is not None else ec(15.0, 6.0, 30.0, 6.0),
          P.COVARIANCE_TYPE_APPROXIMATED, Time(sec=STAMP[0], nanosec=STAMP[1]))
    c.ok(isinstance(m, P), f"build_estimate should return a PositionEstimate, got {type(m).__name__}")
    return m


def fault(name):
    (f,) = need(src(), "apply_fault")
    m = f(build(), name)
    c.ok(m is not None, "apply_fault must return the message (return est)")
    return m


def secs(t):
    return t.sec + t.nanosec * 1e-9


@c.test("my_source.py and probability.py load without errors",
        hint="Run `python3 -c \"import my_source, probability\"` and read the error.")
def _():
    need(src(), "enu_covariance", "is_psd_2x2", "error_ellipse", "build_estimate", "apply_fault", "MySource")
    need(load_student("probability.py"), "mahalanobis2", "p_inside")


@c.test("TODO 1 — enu_covariance(): Σ = R·diag(σa², σc²)·Rᵀ, row-major, floats",
        hint="Σ_EE = A·sin²h + C·cos²h, Σ_NN = A·cos²h + C·sin²h, Σ_EN = Σ_NE = (A − C)·sin h·cos h, Σ_UU = σ_up²; "
             "h in radians; 9 floats.")
def _():
    (f,) = need(src(), "enu_covariance")
    cov = f(15.0, 6.0, 30.0, 6.0)
    c.ok(isinstance(cov, (list, tuple)) and len(cov) == 9, f"expected 9 numbers, got {cov!r}")
    c.ok(all(isinstance(x, float) for x in cov), f"all 9 numbers must be floats, got {cov!r}")
    for i, want in enumerate(REF_COV):
        c.near(cov[i], want, 1e-3, f"enu_covariance(15, 6, 30, 6)[{i}]")
    c.eq([round(x, 9) for x in f(10.0, 2.0, 0.0)], [4.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0],
         "enu_covariance(10, 2, 0) (along = north)")


@c.test("TODO 2 — is_psd_2x2() agrees with NAVERA's _sane() on six matrices",
        hint="Finite; Σ_EE ≥ 0 and Σ_NN ≥ 0; |Σ_EN − Σ_NE| small; Σ_EE·Σ_NN − Σ_EN·Σ_NE ≥ −tolerance.")
def _():
    from navera_msgs.msg import PositionEstimate as P
    (f,) = need(src(), "is_psd_2x2")
    cases = [REF_COV, [100.0, 120.0, 0.0, 120.0, 100.0, 0.0, 0.0, 0.0, 0.0],
             [4.0, 1.0, 0.0, 2.0, 4.0, 0.0, 0.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0],
             [4.0, 2.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0], [math.nan, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0]]
    for cov in cases:
        m = P(latitude=23.588, longitude=58.3829, position_covariance=[float(x) for x in cov])
        c.eq(bool(f(cov)), E()._sane(m), f"is_psd_2x2({cov[:5]}…) compared with NAVERA's _sane")


@c.test("TODO 3 — error_ellipse(): semi-axes from the eigenvalues, heading of the major axis",
        hint="λ = (a+c)/2 ± √(((a−c)/2)² + b²); heading = ½·atan2(2b, c − a) in degrees, modulo 180.")
def _():
    (f, ec) = need(src(), "error_ellipse", "enu_covariance")
    for a, cc, h in ((15.0, 6.0, 30.0), (30.0, 5.0, 45.0), (20.0, 4.0, 120.0), (8.0, 3.0, 0.0)):
        out = f(ec(a, cc, h))
        c.ok(isinstance(out, (tuple, list)) and len(out) == 3, f"error_ellipse should return 3 numbers, got {out!r}")
        c.near(out[0], a, 1e-6, f"semi-major for ({a}, {cc}, {h}°)")
        c.near(out[1], cc, 1e-6, f"semi-minor for ({a}, {cc}, {h}°)")
        c.near(out[2] % 180.0, h, 1e-6, f"heading of the major axis for ({a}, {cc}, {h}°)")


@c.test("TODO 4 — build_estimate(): WHO, HOW and the stamps",
        hint="source DAY_VISION, mode MEASURED, valid True, reason \"\"; header.stamp AND sensor_stamp = stamp; "
             "producer \"my_source\", model_id \"lesson12\", frame_index -1, frame_id \"student_camera\".")
def _():
    from navera_msgs.msg import PositionEstimate as P
    m = build()
    c.eq((m.source, m.mode, m.valid, m.reason), (P.SOURCE_DAY_VISION, P.MODE_MEASURED, True, ""),
         "(source, mode, valid, reason)")
    c.eq((m.header.stamp.sec, m.header.stamp.nanosec), STAMP, "header.stamp")
    c.eq((m.sensor_stamp.sec, m.sensor_stamp.nanosec), STAMP, "sensor_stamp")
    c.eq((m.producer, m.model_id, m.frame_index, m.header.frame_id),
         ("my_source", "lesson12", -1, "student_camera"), "(producer, model_id, frame_index, frame_id)")


@c.test("TODO 4 — WHERE: NaN altitude, your covariance, and NAVERA finds it sane with a stated 13.3 m",
        hint="altitude = math.nan; position_covariance = cov; type = cov_type. NAVERA's _stated_sigma reads "
             "√max(Σ_EE, Σ_NN) = √177.75.")
def _():
    m = build()
    c.ok(math.isnan(m.altitude), f"altitude is {m.altitude} — unknown must be math.nan (0.0 is sea level)")
    c.near(m.latitude, 23.588, 1e-9, "latitude")
    c.near(m.position_covariance[1], REF_COV[1], 1e-3, "position_covariance[1]")
    c.ok(E()._sane(m), "NAVERA's EstimatorNode._sane(your message) is False")
    c.near(E()._stated_sigma(m), math.sqrt(177.75), 1e-6, "NAVERA's _stated_sigma(your message)")


@c.test("TODO 5 — faults that break the WHERE: nan, not_psd, unknown_cov, big_sigma, tilted",
        hint="not_psd: indices 1 AND 3 = 2·√(Σ_EE·Σ_NN). unknown_cov: nine 0.0 + COVARIANCE_TYPE_UNKNOWN. "
             "big_sigma / tilted: enu_covariance(30, 30, HEADING_DEG, SIGMA_UP_M) / (30, 5, 45.0, SIGMA_UP_M).")
def _():
    from navera_msgs.msg import PositionEstimate as P
    k = E()
    m = fault("nan")
    c.ok(math.isnan(m.latitude) and not k._sane(m), "fault 'nan': latitude must be NaN and NAVERA must refuse it")
    m = fault("not_psd")
    cov = list(m.position_covariance)
    c.ok(cov[1] == cov[3] and cov[1] > math.sqrt(cov[0] * cov[4]), f"fault 'not_psd': indices 1 and 3 = {cov[1]}, {cov[3]}")
    c.ok(not k._sane(m) and math.isfinite(m.latitude), "fault 'not_psd': NAVERA must refuse it (and the position stays)")
    m = fault("unknown_cov")
    c.ok(list(m.position_covariance) == [0.0] * 9 and m.position_covariance_type == P.COVARIANCE_TYPE_UNKNOWN,
         "fault 'unknown_cov': nine zeros and COVARIANCE_TYPE_UNKNOWN")
    c.ok(k._sane(m) and k._stated_sigma(m) is None, "fault 'unknown_cov' must stay sane, with no stated sigma")
    c.near(k._stated_sigma(fault("big_sigma")), 30.0, 1e-6, "stated sigma of fault 'big_sigma'")
    c.near(k._stated_sigma(fault("tilted")), math.sqrt(462.5), 1e-6, "stated sigma of fault 'tilted'")
    c.ok(k._sane(fault("none")), "fault 'none' must leave a good estimate")


@c.test("TODO 5 — faults of WHEN and HOW: stale, latency, future, invalid, replayed, held, propagated",
        hint="stale / latency: ONLY sensor_stamp, 10 s / 2 s earlier (use shifted()). future: BOTH stamps +5 s. "
             "invalid: valid False, reason \"lens covered\". replayed / held / propagated: the mode.")
def _():
    from navera_msgs.msg import PositionEstimate as P
    t0 = STAMP[0] + STAMP[1] * 1e-9
    m = fault("stale")
    c.near(secs(m.sensor_stamp), t0 - 10.0, 1e-6, "fault 'stale': sensor_stamp")
    c.near(secs(m.header.stamp), t0, 1e-6, "fault 'stale': header.stamp (must NOT change: published now)")
    m = fault("latency")
    c.near(secs(m.sensor_stamp), t0 - 2.0, 1e-6, "fault 'latency': sensor_stamp")
    c.near(secs(m.header.stamp), t0, 1e-6, "fault 'latency': header.stamp")
    m = fault("future")
    c.near(secs(m.sensor_stamp), t0 + 5.0, 1e-6, "fault 'future': sensor_stamp")
    c.near(secs(m.header.stamp), t0 + 5.0, 1e-6, "fault 'future': header.stamp")
    m = fault("invalid")
    c.eq((m.valid, m.reason), (False, "lens covered"), "fault 'invalid': (valid, reason)")
    for name, mode in (("replayed", P.MODE_REPLAYED), ("held", P.MODE_HELD), ("propagated", P.MODE_PROPAGATED)):
        c.eq(fault(name).mode, mode, f"fault '{name}': mode")


def results():
    try:
        return json.load(open("results.json"))
    except FileNotFoundError:
        c.ok(False, "results.json does not exist yet — run `python3 probability.py`")
    except ValueError as e:
        c.ok(False, f"results.json is not valid JSON: {e}")


@c.test("TODO 6/7 — probability.py: Mahalanobis distance, theory and sampling agree (results.json)",
        hint="d² = (c·e_E² − 2b·e_E·e_N + a·e_N²)/(ac − b²); p_inside(k) = 1 − exp(−k²/2). Then run "
             "`python3 probability.py`.")
def _():
    p = load_student("probability.py")
    c.near(p.p_inside(2.0), 1 - math.exp(-2.0), 1e-9, "p_inside(2)")
    c.near(p.mahalanobis2(15.0 * math.sin(math.radians(30)), 15.0 * math.cos(math.radians(30)), REF_COV), 1.0, 1e-3,
           "mahalanobis2 of a 1-sigma error along the major axis")
    r = (results() or {}).get("probability")
    c.ok(isinstance(r, dict), "results.json has no `probability` section — run python3 probability.py")
    for k, want in (("1.0", 0.3935), ("2.0", 0.8647), ("2.448", 0.9500)):
        c.near(r["theory"][k], want, 1e-3, f"probability.theory[{k}]")
        c.near(r["sampled"][k], want, 0.006, f"probability.sampled[{k}]")
    c.near(r["east_within_1sigma"], 0.6827, 0.006, "probability.east_within_1sigma")
    s = (results() or {}).get("stated_vs_max") or {}
    c.ok("tilted" in s and s["tilted"].get("stated_sigma_m") is not None, "results.json has no stated_vs_max.tilted")
    c.near(s["tilted"]["sigma_max_m"], 30.0, 1e-3, "stated_vs_max.tilted.sigma_max_m")
    c.near(s["tilted"]["stated_sigma_m"], math.sqrt(462.5), 1e-3, "stated_vs_max.tilted.stated_sigma_m")


LIVE_FAULTS = ("none", "stale", "latency", "not_psd", "future", "big_sigma", "tilted")
RES = {}


def verdicts():
    """Run NAVERA's estimator once, and the source with several faults; keep the last status of each."""
    if not RES:
        from navera_msgs.msg import NavStatus, PositionEstimate
        RES["_"] = None
        with Background("ros2 run navera_estimator estimator_node.py", settle=2.5):
            for f in LIVE_FAULTS:
                with Background(f"python3 -u my_source.py {f}", settle=2.0) as bg:
                    time.sleep(3.5)       # slow machines: let the arbiter discover the new source
                    msgs = wait_for_messages("/navera/nav_status", NavStatus, count=3, timeout=6)
                    pos = wait_for_messages("/navera/position", PositionEstimate, count=1, timeout=5.0) \
                        if f == "none" else []
                RES[f] = (msgs[-1] if msgs else None, pos, bg.output())
    return RES


def status_of(f):
    st, pos, out = verdicts()[f]
    c.ok(st is not None, "no /navera/nav_status message — the estimator did not run. Your node printed:\n" + out[-500:])
    return st, pos


@c.test("live — `python3 my_source.py`: FIX from day vision, and NAVERA republishes your position",
        hint="Run the estimator and your source, then `ros2 topic echo /navera/nav_status --field reason`. "
             "A FIX needs valid, MEASURED, fresh (sensor_stamp), sane, and a stated sigma ≤ 25 m.")
def _():
    from navera_msgs.msg import NavStatus
    st, pos = status_of("none")
    c.ok(st.state == NavStatus.STATE_FIX and st.active_source == NavStatus.SOURCE_DAY_VISION,
         f"state {st.state}, source {st.active_source}, reason: {st.reason!r}")
    c.ok(pos and abs(pos[0].latitude - 23.5880) < 1e-6 and pos[0].producer == "navera_estimator",
         "no /navera/position with your latitude (23.5880) re-signed by navera_estimator")


@c.test("live — stale is refused, latency is not: freshness is judged on sensor_stamp",
        hint="'stale': sensor_stamp 10 s old → NO_FIX `day: stale (…)`. 'latency': sensor_stamp 2 s old, inside "
             "the 3 s window → still FIX.")
def _():
    from navera_msgs.msg import NavStatus
    st, _ = status_of("stale")
    c.ok(st.state == NavStatus.STATE_NO_FIX and "day: stale" in st.reason, f"stale: state {st.state}, reason {st.reason!r}")
    st, _ = status_of("latency")
    c.ok(st.state == NavStatus.STATE_FIX, f"latency: state {st.state}, reason {st.reason!r} — expected FIX")


@c.test("live — not_psd and future are refused with the right reasons",
        hint="not_psd → `day: non-finite position or covariance`; future → `day: timestamp …s in the future`.")
def _():
    from navera_msgs.msg import NavStatus
    st, _ = status_of("not_psd")
    c.ok(st.state == NavStatus.STATE_NO_FIX and "non-finite" in st.reason, f"not_psd: state {st.state}, reason {st.reason!r}")
    st, _ = status_of("future")
    c.ok(st.state == NavStatus.STATE_NO_FIX and "in the future" in st.reason, f"future: state {st.state}, reason {st.reason!r}")


@c.test("live — big_sigma is DEGRADED but tilted is FIX (the design question)",
        hint="big_sigma: a 30 m circle → `uncertainty 30 m > 25 m`. tilted: 30 m × 5 m at 45° → stated √462.5 = 21.5 m.")
def _():
    from navera_msgs.msg import NavStatus
    st, _ = status_of("big_sigma")
    c.ok(st.state == NavStatus.STATE_DEGRADED and "30 m > 25 m" in st.reason, f"big_sigma: state {st.state}, reason {st.reason!r}")
    st, _ = status_of("tilted")
    c.ok(st.state == NavStatus.STATE_FIX, f"tilted: state {st.state}, reason {st.reason!r}")


WANT = {"none": (2, ["day vision fix"]), "nan": (1, ["non-finite"]), "not_psd": (1, ["non-finite"]),
        "stale": (1, ["stale", ">3.0s"]), "latency": (2, ["day vision fix"]), "future": (1, ["in the future"]),
        "invalid": (1, ["invalid", "lens covered"]), "replayed": (1, ["replayed not usable"]),
        "held": (1, ["held not usable"]), "propagated": (3, ["propagated"]),
        "unknown_cov": (3, ["uncertainty unknown"]), "big_sigma": (3, ["30 m > 25 m"]), "tilted": (2, ["day vision fix"])}


@c.test("verdicts.py — the state and reason of all 13 runs, and Q1/Q2",
        hint="For each fault, copy `state` (a number) and the day-vision part of `reason` from /navera/nav_status. "
             "Q1/Q2: read the warning box 'The arbiter believes the stated σ'.")
def _():
    (v, q1, q2) = need(load_student("verdicts.py"), "VERDICTS", "Q1", "Q2")
    for name, (state, words) in WANT.items():
        got = v.get(name)
        c.ok(isinstance(got, (tuple, list)) and len(got) == 2, f"VERDICTS[{name!r}] should be (state, \"reason\")")
        c.ok(got[0] == state, f"VERDICTS[{name!r}] state = {got[0]!r} is not what the arbiter says")
        c.ok(all(w in str(got[1]) for w in words), f"VERDICTS[{name!r}] reason = {got[1]!r} is not what the arbiter says")
    c.ok(str(q1).strip().lower() == "b" and str(q2).strip().lower() == "b", f"Q1 = {q1!r}, Q2 = {q2!r}: not both right")


@c.test("report.md — Covariance, Probability and Stated sigma, with your numbers",
        hint="Keep the three headings, at least 40 words each. Covariance must quote the determinant 8100; "
             "Probability your sampled 1-sigma fraction (0.39…); Stated sigma the value 21.5 and a design choice.")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8", errors="replace").read()
    secs_ = {}
    for title in ("Covariance", "Probability", "Stated sigma"):
        m = re.search(r"^##\s*" + title + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
        c.ok(m is not None, f"the heading `## {title}` is missing")
        body = re.sub(r"^\*(?=\S)[^*]+?\*\s*$", "", m.group(1), flags=re.M | re.S)
        words = len(re.findall(r"[A-Za-z0-9_.]+", body))
        c.ok(words >= 40, f"section {title} has {words} words of yours — write at least 40")
        secs_[title] = body
    c.ok("8100" in secs_["Covariance"].replace(" ", "").replace(",", ""), "the Covariance section does not give the determinant (8100)")
    c.ok(re.search(r"0\.39|39\s*%|39\.\d\s*%", secs_["Probability"]), "the Probability section does not quote the 1-sigma fraction")
    c.ok("21.5" in secs_["Stated sigma"], "the Stated sigma section does not quote NAVERA's stated sigma for tilted (21.5 m)")


c.run()
