import contextlib
import csv
import io
import json
import math
import os
import re
import tempfile
import time

from academy_check import (Background, CheckFailed, Checker, explained, hidden, is_stub, load_student, need,
                           predicted, publishers_ok, run, wait_for_messages)

c = Checker()

# ---------------------------------------------------------------- expected values (course reference:
# solutions/12-position-message/expected.py on datasets/12-position-message/day_vision_lag.csv; the unseen
# eligibility faults are courses/12-position-message/hidden/eligible_faults.json)
DEFAULTS = {"gps_timeout_s": 3.0, "day_timeout_s": 5.0, "night_timeout_s": 5.0, "celestial_timeout_s": 45.0,
            "future_tolerance_s": 0.5, "fix_max_sigma_m": 25.0, "min_stated_sigma_m": 0.01,
            "switch_holdoff_s": 2.0, "tick_hz": 5.0, "max_speed_mps": 100.0, "gps_jump_margin_m": 50.0,
            "vehicle": "drone"}
TIMEOUT_KEY = {"gps": "gps_timeout_s", "day": "day_timeout_s", "night": "night_timeout_s",
               "celestial": "celestial_timeout_s"}
SOURCES = ("gps", "day", "night", "celestial")
LAB = {"LAG_PLANE_MEDIAN_M": (64.30, 0.06), "LAG_PLANE_WITHIN_PCT": (0.0, 0.01),
       "LAG_DRONE_WITHIN_PCT": (76.88, 0.07), "LAG_OLD_WINDOW_REFUSED": (6, 0),
       "LAG_SPEED_MAX_MPS": (13.025, 0.175)}     # 12.85–13.2: 13.0 measured, 13.1 = 30 / p90 (2.284 s)
NIGHT = {"source": "night", "lat": 35.7712, "lon": 10.8265, "stamp_s": 812.4,
         "a": 324.0, "b": 0.0, "c": 576.0, "up": 900.0, "cov_type": 2}          # lab Step 1
ATTACKS = ("zero", "unknown", "not_psd", "future")


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def functions(*names):
    fns = need(quiet("navera_lite.estimate"), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/estimate.py)")
    return fns


def answers(*names):
    return need(quiet("answers.py"), *names)


TIPS = [("is not iterable", " — refuse what is not a list of 9 numbers first (try/except TypeError), before you "
                               "loop over it"),
        ("has no len()", " — refuse what is not a list of 9 numbers first (try/except TypeError, or isinstance)"),
        ("not subscriptable", " — cov9[k] on something that is not a list: refuse it with \"not 9 numbers\" first"),
        ("could not convert", " — float() of a text: catch ValueError and answer \"not 9 numbers\""),
        ("KeyError", " — cfg keys are the names of navera_lite.yaml; TIMEOUT_KEY[source] names a source's timeout: "
                     "test `source in TIMEOUT_KEY` before using it"),
        ("'tuple' object has no attribute", " — stated_sigma(est, cfg) takes an Estimate (est.cov, est.cov_type)"),
        ("not supported between instances", " — a comparison with None or a text: one value is not a number")]


def go(fn, *args, **kw):
    """run() with one more sentence for the errors students meet most in this mission."""
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def pair(got, what):
    """(ok, reason) as returned by is_covariance / eligible, or a clear ✘."""
    if not (isinstance(got, (tuple, list)) and len(got) == 2):
        raise CheckFailed(f"{what} must return a pair (ok, reason), like (False, \"not finite\"), got {got!r}")
    if not isinstance(got[0], bool):
        raise CheckFailed(f"{what}: the first item must be True or False (a bool), got {got[0]!r}")
    if not isinstance(got[1], str):
        raise CheckFailed(f"{what}: the second item must be the reason as text, got {got[1]!r}")
    return got[0], got[1]


def cov9(a, b, c, up=0.0):
    return [float(a), float(b), 0.0, float(b), float(c), 0.0, 0.0, 0.0, float(up)]


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")
    if not math.isfinite(x):
        raise CheckFailed(f"{name} is {x}: not a usable number")
    return x


# ---------------------------------------------------------------- the checker's own judges (models of arbiter v0
# and of an honest judge, written independently of the student's files) for the attack scenarios
def _dist_m(lat1, lon1, lat2, lon2):
    k = math.pi / 180.0 * 6371000.0
    return math.hypot((lon2 - lon1) * k * math.cos(math.radians((lat1 + lat2) / 2)), (lat2 - lat1) * k)


def _finite_latlon(lat, lon):
    return (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180
            and not (lat == 0 and lon == 0))


def _is_cov(a, b, c):
    vals = (a, b, c)
    size = max(1.0, abs(a), abs(c))
    return all(math.isfinite(v) for v in vals) and a >= 0 and c >= 0 and a * c - b * b >= -1e-9 * size * size


def read_attack(path):
    """The rows of an attack CSV, as the replay node reads them, or a CheckFailed with the reason."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        need_cols = {"t_s", "source", "lat", "lon"}
        if not reader.fieldnames or not need_cols <= set(h.strip() for h in reader.fieldnames):
            raise CheckFailed(f"{path}: the header must be t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s "
                              f"(got {reader.fieldnames})")
        for n, raw in enumerate(reader, start=2):
            raw = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            try:
                row = {"t_s": float(raw["t_s"]), "source": raw["source"], "lat": float(raw["lat"]),
                       "lon": float(raw["lon"])}
                for key, default, kind in (("a", 0.0, float), ("b", 0.0, float), ("c", 0.0, float),
                                           ("cov_type", 0, int), ("valid", 1, int), ("delay_s", 0.0, float)):
                    row[key] = kind(raw[key]) if raw.get(key) else default
            except (KeyError, ValueError) as e:
                raise CheckFailed(f"{path} line {n}: this row cannot be read ({e})")
            if row["source"] not in SOURCES:
                raise CheckFailed(f"{path} line {n}: source must be one of {', '.join(SOURCES)}")
            rows.append(row)
    if not rows:
        raise CheckFailed(f"{path} has no row: write at least one fix under the header")
    return sorted(rows, key=lambda r: r["t_s"])


def verdict(rows, honest, extra_s=0.5):
    """(state, reason, judged_row) at extra_s after the last row: arbiter v0's rules, or an honest judge's."""
    latest, trusted = {}, None
    for r in rows:
        stamp = r["t_s"] - r["delay_s"]
        if r["source"] == "gps" and r["valid"] and _finite_latlon(r["lat"], r["lon"]):
            if trusted is not None:
                el = max(0.0, stamp - trusted[2])
                if _dist_m(trusted[0], trusted[1], r["lat"], r["lon"]) > 100.0 * el + 50.0:
                    continue                                  # the jump gate refuses it
            trusted = (r["lat"], r["lon"], stamp)
        latest[r["source"]] = r
    now = rows[-1]["t_s"] + extra_s
    whys = []
    for name in SOURCES:
        r = latest.get(name)
        if r is None:
            continue
        age = now - (r["t_s"] - r["delay_s"])
        timeout = DEFAULTS[TIMEOUT_KEY[name]]
        stated = r["cov_type"] in (1, 2, 3)
        if not r["valid"]:
            why = "no position"
        elif not _finite_latlon(r["lat"], r["lon"]):
            why = "bad position"
        elif honest and stated and not _is_cov(r["a"], r["b"], r["c"]):
            why = "not a covariance"
        elif honest and age < -DEFAULTS["future_tolerance_s"]:
            why = "from the future"
        elif age > timeout:
            why = "stale"
        else:
            if honest:
                ok = stated and _is_cov(r["a"], r["b"], r["c"])
                sigma = math.sqrt(max(r["a"], r["c"])) if ok else None
                if sigma is not None and sigma < DEFAULTS["min_stated_sigma_m"]:
                    sigma = None
            else:
                m = max(r["a"], r["c"], 0.0)
                sigma = math.sqrt(m) if math.isfinite(m) else None
            if sigma is None:
                return "DEGRADED", f"{name}: σ unknown", r
            if sigma > DEFAULTS["fix_max_sigma_m"]:
                return "DEGRADED", f"{name}: σ {sigma:.1f} m > 25.0 m", r
            return "FIX", f"{name}: σ {sigma:.1f} m", r
        whys.append(f"{name}: {why}")
    return "NO_FIX", "no usable source (" + "; ".join(whys) + ")", None


def attack_rows(name):
    path = f"attacks/{name}.csv"
    if not os.path.exists(path):
        raise CheckFailed(f"{path} does not exist yet (lab Step 5)")
    return read_attack(path)


# ================================================================ Session 1 — the contract
@c.test("Step 1 — MY_ESTIMATE fills the contract for the night-vision fix",
        hint="Lesson §1 and §2: the stamp is when the frame was TAKEN; the covariance holds variances (σ², m²); "
             "a type that says what is known and nothing more; an unknown altitude is nan, not 0.")
def _():
    (e,) = answers("MY_ESTIMATE")
    c.ok(e is not None, "MY_ESTIMATE is still None: write Estimate(...) for the night-vision fix of lab Step 1")
    try:
        src, lat, lon, stamp = e.source, e.lat, e.lon, e.stamp_s
        cov, ctype, alt, valid = list(e.cov), e.cov_type, e.alt_m, e.valid
    except Exception:
        raise CheckFailed(f"MY_ESTIMATE must be an Estimate(...) (from navera_lite.estimate), got {e!r}")
    c.ok(src == NIGHT["source"], f"source is {src!r}: which source matched a THERMAL frame? (estimate.SOURCES)")
    c.ok(abs(number(lat, "lat") - NIGHT["lat"]) < 1e-6 and abs(number(lon, "lon") - NIGHT["lon"]) < 1e-6,
         f"lat, lon = {lat}, {lon}: copy the position of the sentence (degrees, north and east are positive)")
    st = number(stamp, "stamp_s")
    c.ok(abs(st - 813.5) > 1e-6, "stamp_s is when the result was PUBLISHED: the contract stamps the MEASUREMENT "
                                 "(when the frame was taken) — lesson §4")
    c.ok(abs(st - NIGHT["stamp_s"]) < 1e-6, f"stamp_s = {stamp}: the instant the frame was taken, on the judge's clock")
    c.ok(len(cov) == 9, f"cov must hold 9 numbers, got {len(cov)}")
    if abs(cov[0] - 18.0) < 1e-6 or abs(cov[4] - 24.0) < 1e-6:
        raise CheckFailed("cov holds σ (18, 24): a covariance holds VARIANCES, σ² in m² (lesson §2)")
    c.ok(abs(cov[0] - NIGHT["a"]) < 1e-6 and abs(cov[4] - NIGHT["c"]) < 1e-6,
         f"cov[0], cov[4] = {cov[0]}, {cov[4]}: a = σE² at index 0, c = σN² at index 4 (lesson §2)")
    c.ok(cov[1] == 0 and cov[3] == 0, "b (indices 1 and 3) must be 0: the matcher does not know the correlation, and "
                                       "a type that says so is how you tell it (not an invented number)")
    c.ok(abs(cov[8] - NIGHT["up"]) < 1e-6, f"cov[8] = {cov[8]}: the up variance, σU² (m²)")
    c.ok(ctype == NIGHT["cov_type"], f"cov_type = {ctype!r}: the three variances are known, the correlations are not "
                                    "— which type says exactly that? (lesson §3)")
    c.ok(isinstance(alt, float) and math.isnan(alt), f"alt_m = {alt!r}: the altitude is unknown — 0.0 would mean sea "
                                                      "level (lesson §1)")
    c.ok(valid is True, "valid must be True: the source has a position")


@c.test("TODO 1 — is_covariance() accepts real covariances it has never seen",
        hint="Lesson §2: symmetric, a ≥ 0, c ≥ 0, σU² ≥ 0 and a·c − b² ≥ 0, with a tolerance RELATIVE to the size of the "
             "numbers (the docstring says how). A negative b is allowed; a correlation of exactly ±1 is allowed, even "
             "with km-sized σ where rounding makes a·c − b² slightly negative.")
def _():
    (f,) = functions("is_covariance")
    good = [("a=400, b=−150, c=100 (a negative correlation)", cov9(400, -150, 100, 2500)),
            ("a=16, b=12, c=9 (correlation exactly 1: determinant 0)", cov9(16, 12, 9)),
            ("all zero", cov9(0, 0, 0)),
            ("b differs by 1e-12 between its two places", [4.0, 0.5, 0, 0.5 + 1e-12, 4.0, 0, 0, 0, 1.0]),
            ("a tuple, not a list", tuple(cov9(25, 5, 36, 49))),
            ("σ 1.5 km and 4.3 km, correlation exactly 1 (a·c − b² rounds to −0.016 m⁴)",
             cov9(1533.134075052139 ** 2, 1533.134075052139 * 4338.682908789684, 4338.682908789684 ** 2))]
    for label, m in good:
        ok, why = pair(go(f, m), f"is_covariance({label})")
        c.ok(ok is True and why == "ok", f"is_covariance({label}) → ({ok}, {why!r}): it is a covariance, "
                                         "expected (True, \"ok\")")
    ok, why = pair(go(f, cov9(4, 2.05, 1), tol=0.5), "is_covariance(a=4, b=2.05, c=1, tol=0.5)")
    c.ok(ok is True, "a=4, b=2.05, c=1 with tol=0.5: a·c − b² = −0.2025 is within the tolerance you were given, so "
                     "it is accepted — use the tol argument, not a fixed number")


@c.test("TODO 1 — is_covariance() names the first broken rule, on matrices it has never seen",
        hint="The docstring's order: 9 numbers, finite, symmetric, variances ≥ 0, then the determinant. A matrix with "
             "a = c = −1 and b = 0 has a positive determinant: only the variance rule catches it.")
def _():
    (f,) = functions("is_covariance")
    bad = [("a=16, b=12.5, c=9", cov9(16, 12.5, 9), "not positive semi-definite"),
           ("a=4, b=2.05, c=1 (default tol)", cov9(4, 2.05, 1), "not positive semi-definite"),
           ("a=−1, b=0, c=−1 (determinant +1)", cov9(-1, 0, -1), "negative variance"),
           ("an up variance of −1", cov9(9, 0, 9, -1), "negative variance"),
           ("a=−4, b=1, c=4 (negative variance AND negative determinant)", cov9(-4, 1, 4), "negative variance"),
           ("b = 0.5 at index 1, 0.5000001 at index 3", [4.0, 0.5, 0, 0.5000001, 4.0, 0, 0, 0, 1.0], "not symmetric"),
           ("an infinite c", cov9(4, 0, float("inf")), "not finite"),
           ("a nan AND b not symmetric", [float("nan"), 1.0, 0, 2.0, 4.0, 0, 0, 0, 0], "not finite"),
           ("b not symmetric AND a < 0", [-4.0, 1.0, 0, 2.0, 4.0, 0, 0, 0, 0], "not symmetric")]
    for label, m, want in bad:
        ok, why = pair(go(f, m), f"is_covariance({label})")
        c.ok(ok is False and why == want, f"is_covariance({label}) → ({ok}, {why!r}); expected (False, {want!r})")


@c.test("TODO 1 — is_covariance() answers anything without crashing",
        hint="Whatever arrives from the network: None, a number, 8 or 10 numbers, text. Refuse it with "
             "(False, \"not 9 numbers\") before you index it (try/except TypeError, ValueError).")
def _():
    (f,) = functions("is_covariance")
    for label, m in (("None", None), ("the number 12.0", 12.0), ("10 numbers", [1.0] * 10),
                     ("8 numbers", [1.0] * 8), ("the text 'abc'", "abc"), ("an empty list", [])):
        ok, why = pair(go(f, m), f"is_covariance({label})")
        c.ok(ok is False and why == "not 9 numbers", f"is_covariance({label}) → ({ok}, {why!r}); expected "
                                                     "(False, \"not 9 numbers\")")


@c.test("TODO 2 — stated_sigma() on estimates it has never seen",
        hint="Lesson §3: None unless the type states an accuracy (1, 2 or 3), the numbers ARE a covariance (your "
             "is_covariance) and √max(a, c) is at least cfg[\"min_stated_sigma_m\"]. Read the minimum from cfg.")
def _():
    (f,) = functions("stated_sigma")
    E = quiet("navera_lite.estimate").Estimate
    base = {"source": "gps", "lat": 35.76, "lon": 10.81, "stamp_s": 50.0}
    cases = [("type KNOWN, a=400, c=100", cov9(400, 0, 100), 3, DEFAULTS, 20.0),
             ("type DIAGONAL_KNOWN, a=36, c=64", cov9(36, 0, 64), 2, DEFAULTS, 8.0),
             ("type APPROXIMATED, a=900, b=200, c=100", cov9(900, 200, 100), 1, DEFAULTS, 30.0),
             ("type UNKNOWN, a=c=100", cov9(100, 0, 100), 0, DEFAULTS, None),
             ("type 7 (not a defined type), a=c=100", cov9(100, 0, 100), 7, DEFAULTS, None),
             ("type APPROXIMATED, all 1e-6 m² (σ 1 mm)", cov9(1e-6, 0, 1e-6), 1, DEFAULTS, None),
             ("type APPROXIMATED, a=c=9 but b=10 (not PSD)", cov9(9, 10, 9), 1, DEFAULTS, None),
             ("type APPROXIMATED, a=−9, c=4", cov9(-9, 0, 4), 1, DEFAULTS, None),
             ("σ 3 m with min_stated_sigma_m = 5.0", cov9(9, 0, 9), 1, dict(DEFAULTS, min_stated_sigma_m=5.0), None)]
    for label, cov, ctype, cfg, want in cases:
        got = go(f, E(cov=tuple(cov), cov_type=ctype, **base), cfg)
        if want is None:
            c.ok(got is None, f"stated_sigma({label}) → {got!r}; expected None: this estimate states no usable "
                              "accuracy")
        else:
            c.ok(isinstance(got, (int, float)) and not isinstance(got, bool),
                 f"stated_sigma({label}) → {got!r}; expected a number of metres")
            c.ok(abs(got - want) < 1e-6, f"stated_sigma({label}) → {got!r}: σ = √max(a, c), in metres (lesson §3)")


@c.test("TODO 3 — staleness_m() on values it has never seen",
        hint="Lesson §4: the distance flown during the age. A negative speed or age raises ValueError.")
def _():
    (f,) = functions("staleness_m")
    for v, a, want in ((12.5, 0.4, 5.0), (75.0, 0.8, 60.0), (0.0, 3.0, 0.0), (10, 2, 20.0)):
        got = go(f, v, a)
        c.ok(isinstance(got, (int, float)) and not isinstance(got, bool), f"staleness_m({v}, {a}) → {got!r}: a number")
        c.ok(abs(got - want) < 1e-9, f"staleness_m({v}, {a}) → {got!r}: not the distance flown during the age")
    for v, a in ((-3.0, 1.0), (20.0, -0.1)):
        try:
            got = f(v, a)
        except ValueError:
            continue
        except Exception as e:
            raise CheckFailed(f"staleness_m({v}, {a}) raised {type(e).__name__}; it must raise ValueError")
        raise CheckFailed(f"staleness_m({v}, {a}) → {got!r}: a negative {'speed' if v < 0 else 'age'} must raise "
                          "ValueError (an age below 0 is a stamp from the future: lesson §4)")


@c.test("Step 0 and Step 4 — the dead GPS and the lag study",
        hint="python3 contract_lab.py lag; for the fastest speed, 30 m ÷ the p90 age, confirmed with one run of "
             "lag --speed. Numbers without quotes; the EXPLAIN answers need a real sentence.")
def _():
    a = quiet("answers.py")
    for name in ("PREDICT_DEAD", "PREDICT_LAG"):
        predicted(name, getattr(a, name, ""))
    for name, (want, tol) in LAB.items():
        x = number(getattr(a, name, None), name)
        c.ok(abs(x - want) <= tol + 1e-9, f"{name} = {x!r} is not what `python3 contract_lab.py lag` gives "
             + ("(compute 30 m / the p90 age, then confirm with one run of --speed: about 90 % within 30 m)"
                if name == "LAG_SPEED_MAX_MPS" else ""))
    explained("EXPLAIN_DEAD", getattr(a, "EXPLAIN_DEAD", ""),
              ([r"futur", r"ahead", r"later than", r"in advance"], "that the fixes were stamped in the future"),
              ([r"age", r"old", r"negative", r"stale", r"fresh", r"timeout"],
               "what that does to the age / the freshness test"))
    explained("EXPLAIN_LAG", getattr(a, "EXPLAIN_LAG", ""),
              ([r"age", r"old", r"late", r"latenc", r"delay", r"lag", r"second"], "the age of the fix"),
              ([r"mov", r"fl[iy]", r"travel", r"speed", r"m/s", r"distance"], "that the vehicle keeps moving"))


# ================================================================ Session 2 — attack, then defend
@c.test("Step 5 — four attacks that fool arbiter v0",
        hint="attacks/zero.csv, unknown.csv, not_psd.csv, future.csv (header of lesson §5). Each must end with v0 "
             "saying FIX: `python3 contract_lab.py attacks` shows v0's verdict.")
def _():
    for name in ATTACKS:
        rows = attack_rows(name)
        state, reason, _ = verdict(rows, honest=False)
        c.ok(state == "FIX", f"attacks/{name}.csv: arbiter v0 says {state} ({reason}) 0.5 s after your last fix — "
                             "the attack must make v0 say FIX")


@c.test("Step 5 — each attack uses its own hole (an honest judge refuses it)",
        hint="zero: a stated type with a = b = c = 0. unknown: type 0 with numbers in it. not_psd: a stated type, "
             "a ≥ 0, c ≥ 0, but a·c < b². future: delay_s more negative than −0.5. Lesson §5, \"Attacker's view\".")
def _():
    rules = {
        "zero": (lambda r: r["cov_type"] in (1, 2, 3) and r["a"] == 0 and r["b"] == 0 and r["c"] == 0,
                 "the judged fix must state a type (1, 2 or 3) and have a = b = c = 0"),
        "unknown": (lambda r: r["cov_type"] not in (1, 2, 3) and max(r["a"], r["c"]) > 0,
                    "the judged fix must have cov_type 0 (unknown) and numbers in a and c that v0 reads anyway"),
        "not_psd": (lambda r: r["cov_type"] in (1, 2, 3) and r["a"] >= 0 and r["c"] >= 0
                    and r["a"] * r["c"] - r["b"] ** 2 < 0,
                    "the judged fix must state a type, have a ≥ 0 and c ≥ 0, and a·c − b² < 0"),
        "future": (lambda r: r["delay_s"] < -DEFAULTS["future_tolerance_s"],
                   "the judged fix must be stamped in the future by more than 0.5 s (delay_s < −0.5)"),
    }
    for name in ATTACKS:
        rows = attack_rows(name)
        _, _, judged = verdict(rows, honest=False)
        test, what = rules[name]
        c.ok(judged is not None and test(judged), f"attacks/{name}.csv: {what}")
        state, reason, _ = verdict(rows, honest=True)
        c.ok(state != "FIX", f"attacks/{name}.csv: an honest judge also says FIX ({reason}) — it is a good fix, "
                             "not an attack on a hole")


def _load_faults():
    try:
        return json.loads(hidden("eligible_faults.json"))
    except Exception as e:
        raise CheckFailed(f"the check's test data could not be read ({e}) — tell your teacher")


@c.test("TODO 4 — eligible() gives the right verdict on 20 situations it has never seen",
        hint="The docstring's order of rules; the source's timeout is cfg[TIMEOUT_KEY[source]] (day 5 s, celestial "
             "45 s); a stamp in the future is age < −cfg[\"future_tolerance_s\"]; read every number from cfg.")
def _():
    (f,) = functions("eligible")
    E = quiet("navera_lite.estimate").Estimate
    wrong = []
    for fault in _load_faults():
        kw = dict(fault["est"])
        if "cov" in kw:
            kw["cov"] = tuple(kw["cov"])
        cfg = dict(DEFAULTS)
        cfg.update(fault["cfg"])
        ok, why = pair(go(f, E(**kw), fault["now"], cfg), f"eligible({fault['label']})")
        want = tuple(fault["want"])
        if (ok, why) != want:
            wrong.append(f"{fault['label']}: you return ({ok}, {why!r}), expected {want!r}")
    c.ok(not wrong, f"{len(wrong)} wrong verdict(s) of 20, e.g. " + "; ".join(wrong[:2]))


@c.test("Steps 6 and 8 — the verdicts you saw, v0 then your judge",
        hint="Copy the line `python3 contract_lab.py status` prints while the attack plays live (Steps 6 and 8): the "
             "state, then the message, e.g. \"FIX | gps: σ 0.0 m\".")
def _():
    v0, mine = answers("VERDICTS_V0", "VERDICTS_MINE")
    for label, table, honest in (("VERDICTS_V0", v0, False), ("VERDICTS_MINE", mine, True)):
        c.ok(isinstance(table, dict), f"{label} must stay a dict {{\"zero\": \"…\", …}}")
        for name in ATTACKS:
            text = str(table.get(name, "")).strip()
            c.ok(text, f"{label}[\"{name}\"] is empty")
            state, reason, _ = verdict(attack_rows(name), honest=honest)
            first = text.split()[0].upper().strip(":,")
            c.ok(first == state, f"{label}[\"{name}\"] starts with {first!r}: for your attacks/{name}.csv this judge "
                                 f"says {state}" + ("" if honest else " (the attack must fool v0)"))
            if state == "NO_FIX":
                c.ok("no usable source" in text.lower(), f"{label}[\"{name}\"]: copy the LIVE status line "
                     "(`python3 contract_lab.py status`): its NO_FIX message starts \"no usable source (…\"")
            m = re.search(r"\((?:\w+): ([a-z ]+)", reason)          # NO_FIX: "no usable source (gps: from the future)"
            key = m.group(1).strip() if (state == "NO_FIX" and m) else ("unknown" if "unknown" in reason else "σ")
            c.ok(key in text.lower() or (key == "σ" and "sigma" in text.lower()),
                 f"{label}[\"{name}\"] does not give the judge's message (it should contain {key!r}): copy the "
                 "message after the state")


@c.test("Step 8 — live: arbiter v0 with YOUR eligible() refuses a GPS stamped in the future",
        hint="Stop every node of the lab first (`kill -INT $(jobs -p)`). The check starts arbiter v0 with "
             "-p use_eligible:=true and plays a GPS stamped 30 s ahead: your eligible() must say \"from the future\".")
def _():
    functions("eligible", "stated_sigma")
    publishers_ok("/navera_lite/status", expected=0)
    publishers_ok("/navera_lite/fix/gps", expected=0)
    from diagnostic_msgs.msg import DiagnosticStatus
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="probe_", dir=os.getcwd())
    try:
        with os.fdopen(fd, "w") as f:
            f.write("t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s\n")
            for k in range(3):
                f.write(f"{k}.0,gps,35.7604,10.81{k},4.0,0.0,4.0,1,1,-30.0\n")
        with Background("python3 -m navera_lite.ros.arbiter_v0 --ros-args -p use_eligible:=true", settle=2.0) as arb:
            with Background(f"python3 -m navera_lite.ros.replay_node --ros-args -p file:={path} -p loop:=true",
                            settle=1.0):
                end, seen = time.time() + 14.0, []
                while time.time() < end:
                    seen += [m.message for m in wait_for_messages("/navera_lite/status", DiagnosticStatus,
                                                                  count=10, timeout=2.0)]
                    if any("from the future" in s for s in seen):
                        break
        if not any("from the future" in s for s in seen):
            fixes = [s for s in seen if s.startswith("gps: σ")]
            if fixes:
                raise CheckFailed(f"the judge said {fixes[-1]!r} (FIX) for a GPS stamped 30 s in the future: your "
                                  "eligible() let it through")
            if not seen:
                raise CheckFailed("no status message in 14 s: did arbiter v0 start? Run it yourself as in Step 8 "
                                  "and read its first lines.\n" + arb.output()[-600:])
            raise CheckFailed(f"the judge never said \"from the future\"; its last message was {seen[-1]!r}")
    finally:
        os.remove(path)


@c.test("Step 8 — the dead source that comes back",
        hint="Predict before the 70 s watch, then explain: what does the judge keep from a refused fix, and what "
             "changes when the clock reaches its stamp?")
def _():
    a = quiet("answers.py")
    predicted("PREDICT_REVIVE", getattr(a, "PREDICT_REVIVE", ""))
    explained("EXPLAIN_REVIVE", getattr(a, "EXPLAIN_REVIVE", ""),
              ([r"stor", r"kept", r"keep", r"remember", r"latest", r"newest", r"last fix", r"memory", r"still there",
                r"again", r"re-?check", r"re-?test", r"every tick", r"each tick"], "that the judge keeps the refused fix "
               "and tests it again"),
              ([r"clock", r"catch", r"reach", r"no longer", r"not .*future", r"becom", r"fresh", r"age", r"time pass",
                r"60 ?s", r"now"], "what changes when the time reaches the stamp"))


@c.test("Step 9 — the limit of a checklist",
        hint="Which of your rules could see that a stated 3 m is a lie? Think about what the judge can compare a "
             "source with (mission 01).")
def _():
    (t,) = answers("EXPLAIN_HONEST")
    explained("EXPLAIN_HONEST", t,
              ([r"believ", r"trust", r"claim", r"stat", r"says", r"self", r"own", r"valid", r"nothing", r"inside",
                r"in the message", r"covariance", r"lie", r"honest", r"look(s)? (fine|right|correct|normal)",
                r"well.formed", r"correct", r"form"], "why the message itself looks fine to the judge"),
              ([r"cross", r"another", r"other source", r"independent", r"compar", r"second", r"validat", r"measur",
                r"vision", r"jump", r"gate", r"ground truth", r"reference"],
               "what can catch it (something independent of that source)"),
              min_words=12)


c.milestone("session1", "Step 1", "TODO 1", "TODO 2", "TODO 3", "Step 0", label="Contract keeper")
c.milestone("session2", "Step 1", "TODO", "Step", label="Honest judge")
c.run()
