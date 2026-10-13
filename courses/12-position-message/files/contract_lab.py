"""contract_lab.py — runs YOUR functions of navera_lite/estimate.py on the lab's situations.

    python3 contract_lab.py test                     each TODO on its docstring example, and a few traps
    python3 contract_lab.py lag                      the day-vision lag study (Step 4), with YOUR staleness_m
    python3 contract_lab.py lag --speed 20           the same study at another speed (m/s)
    python3 contract_lab.py judge attacks/zero.csv   play a scenario through arbiter v0, without ROS (Step 5)
    python3 contract_lab.py judge attacks/zero.csv --eligible    … through v0 with YOUR eligible() (Step 7)
    python3 contract_lab.py judge FILE --until 70    keep the clock running until t = 70 s
    python3 contract_lab.py attacks                  every attacks/*.csv: arbiter v0's verdict, without ROS
    python3 contract_lab.py attacks --eligible       … and the verdict of v0 with YOUR eligible() (Step 7)
    python3 contract_lab.py status                   the LIVE judge's state and message (listens 6 s)
    python3 contract_lab.py status --watch 45        every change of the live judge during 45 s, with the time

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import contextlib
import csv
import glob
import io
import math
import os
import re
import sys
import time

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

est_mod = rk.load_student("navera_lite.estimate")
settings = rk.load_student("navera_lite.settings")
Estimate = est_mod.Estimate
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if isinstance(e, TypeError) and "is not iterable" in s:
        return " — refuse what is not a list of 9 numbers first (lab Step 2 🧰: try/except TypeError)"
    if isinstance(e, TypeError) and "object of type" in s and "has no len()" in s:
        return " — len() of something that is not a list: test it first (isinstance, or try/except TypeError)"
    if isinstance(e, TypeError) and "not subscriptable" in s:
        return (" — cov9[k] on something that is not a list (None? a number?): refuse it first with "
                "\"not 9 numbers\"")
    if isinstance(e, TypeError) and ("'<' not supported" in s or "'>' not supported" in s):
        return " — you compared a number with None or a text: one of your values is not a number"
    if isinstance(e, KeyError):
        return (" — cfg has no such key: the keys are the names in navera_lite.yaml (e.g. \"gps_timeout_s\"); "
                "TIMEOUT_KEY[source] gives the key of a source's timeout")
    if isinstance(e, AttributeError) and "'tuple' object has no attribute" in s:
        return " — stated_sigma(est, cfg) takes an Estimate (est.cov, est.cov_type), not the 9 numbers"
    return _kit_hint(e)


rk._hint = _hint

DATA = "/data/academy/12-position-message/day_vision_lag.csv"
OUT = "out"
STATED_DAY_SIGMA_M = 30.0          # what the matcher states for every fix (lesson §4)
CLOCK0 = 1000.0                    # the offline judge's clock at t = 0 of a scenario (s)


def cfg():
    """The settings of your navera_lite.yaml (the defaults if it cannot be read)."""
    try:
        return settings.load("navera_lite.yaml")
    except Exception as e:                      # a broken yaml: say so, then use the defaults
        print(f"(navera_lite.yaml could not be read: {e} — using the defaults)")
        return dict(settings.DEFAULTS)


def cov9(a, b, c, up=0.0):
    return (float(a), float(b), 0.0, float(b), float(c), 0.0, 0.0, 0.0, float(up))


# ------------------------------------------------------------------------------------------------ test
def _same(got, want):
    if isinstance(want, float):
        return isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want) < 1e-6
    if isinstance(want, tuple):
        return (isinstance(got, (tuple, list)) and len(got) == 2 and got[0] == want[0]
                and isinstance(got[0], bool) and got[1] == want[1])
    return got == want


def test():
    """Each function on its docstring example (first line of each TODO) and a few traps."""
    D = cfg()
    gps = dict(source="gps", lat=35.8256, lon=10.6084, stamp_s=100.0)
    cases = [
        # (todo, label, function, args, expected)
        (1, "the docstring example (lesson §2)", "is_covariance", ([25.0, 30.0, 0, 30.0, 16.0, 0, 0, 0, 1.0],),
         (False, "not positive semi-definite")),
        (1, "a round 3 m covariance", "is_covariance", (cov9(9, 0, 9, 36),), (True, "ok")),
        (1, "8 numbers", "is_covariance", ([9.0, 0, 0, 0, 9.0, 0, 0, 0],), (False, "not 9 numbers")),
        (1, "None", "is_covariance", (None,), (False, "not 9 numbers")),
        (1, "a nan", "is_covariance", (cov9(float("nan"), 0, 9),), (False, "not finite")),
        (1, "b = 1 at index 1, 2 at index 3", "is_covariance", ([4.0, 1.0, 0, 2.0, 4.0, 0, 0, 0, 0],),
         (False, "not symmetric")),
        (1, "a negative north variance", "is_covariance", (cov9(4, 0, -1),), (False, "negative variance")),
        (1, "an up variance of −1", "is_covariance", (cov9(4, 0, 4, -1),), (False, "negative variance")),
        (1, "an infinite up variance", "is_covariance", (cov9(4, 0, 4, float("inf")),), (False, "not finite")),
        (1, "a=9, b=10, c=9, up variance 10⁶ (altitude unknown)", "is_covariance", (cov9(9, 10, 9, 1e6),),
         (False, "not positive semi-definite")),
        (1, "b differs by 1e-12 between its places (rounding)", "is_covariance",
         ([4.0, 1.0, 0, 1.0 + 1e-12, 4.0, 0, 0, 0, 1.0],), (True, "ok")),
        (1, "σ 3.6 km and 4.7 km, correlation exactly 1 (rounding: a·c − b² < 0)", "is_covariance",
         (cov9(3615.9 ** 2, 3615.9 * 4706.3, 4706.3 ** 2),), (True, "ok")),
        (2, "the docstring example", "stated_sigma",
         (Estimate(cov=(9.0, 0, 0, 0, 4.0, 0, 0, 0, 36.0), cov_type=est_mod.COV_DIAGONAL_KNOWN, **gps), D), 3.0),
        (2, "type UNKNOWN, numbers inside", "stated_sigma",
         (Estimate(cov=cov9(9, 0, 9), cov_type=est_mod.COV_UNKNOWN, **gps), D), None),
        (2, "all zero, type APPROXIMATED", "stated_sigma",
         (Estimate(cov=cov9(0, 0, 0), cov_type=est_mod.COV_APPROXIMATED, **gps), D), None),
        (2, "the tilted ellipse of lesson §3", "stated_sigma",
         (Estimate(cov=cov9(83.25, 81.84, 177.75, 36.0), cov_type=est_mod.COV_KNOWN, **gps), D),
         math.sqrt(177.75)),
        (2, "σ exactly 0.01 m (the minimum is believed)", "stated_sigma",
         (Estimate(cov=cov9(1e-4, 0, 1e-4), cov_type=est_mod.COV_KNOWN, **gps), D), 0.01),
        (2, "type APPROXIMATED, b too big (not a covariance)", "stated_sigma",
         (Estimate(cov=cov9(9, 10, 9), cov_type=est_mod.COV_APPROXIMATED, **gps), D), None),
        (3, "the docstring example", "staleness_m", (40.0, 2.5), 100.0),
        (3, "standing still", "staleness_m", (0.0, 7.0), 0.0),
        (4, "the docstring example", "eligible", (Estimate(**gps), 103.4, D), (False, "stale (3.4 s > 3.0 s)")),
        (4, "a fresh GPS fix", "eligible", (Estimate(**gps), 101.0, D), (True, "eligible")),
        (4, "the source says: no position", "eligible", (Estimate(valid=False, **gps), 100.5, D),
         (False, "no position")),
        (4, "a day fix 4.2 s old", "eligible", (Estimate("day", 35.8, 10.6, 100.0), 104.2, D), (True, "eligible")),
        (4, "type UNKNOWN with impossible numbers", "eligible",
         (Estimate(cov=cov9(100, 120, 100), cov_type=est_mod.COV_UNKNOWN, **gps), 101.0, D), (True, "eligible")),
        (4, "a GPS fix exactly 3.0 s old", "eligible", (Estimate(**gps), 103.0, D), (True, "eligible")),
    ]
    print("Each line runs one of YOUR functions. A TODO you have not written yet shows ✘ — that is normal.\n")
    bad = 0
    for todo, label, fn, args, want in cases:
        got, err = rk.call(est_mod, fn, *args)
        if err and "returned None for this case" in err:
            got, err = None, None                     # judged below: None may be the right answer
        if err:
            ok, note = False, err
        elif _same(got, want):
            ok, note = True, f"{got!r}"
        else:
            ok, note = False, f"returned {got!r}, the docstring/lesson says {want!r}"
        bad += not ok
        print(f"{'✔' if ok else '✘'} TODO {todo} {fn}() — {label}: {note}")
    # the errors staleness_m must raise
    for args in ((-5.0, 1.0), (10.0, -0.5)):
        f = getattr(est_mod, "staleness_m", None)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                v = f(*args)
            ok, note = False, (f"returned {v!r}: a negative {'speed' if args[0] < 0 else 'age'} must raise "
                               "ValueError (lesson §4: a negative age is a stamp from the future)")
            if v is None and rk.is_stub(f):
                note = "staleness_m() is not written yet"
        except ValueError:
            ok, note = True, "raises ValueError"
        except Exception as e:
            ok, note = False, f"raises {type(e).__name__}: {e} — it must raise ValueError"
        bad += not ok
        print(f"{'✔' if ok else '✘'} TODO 3 staleness_m{args}: {note}")
    print("\nAll the examples agree." if not bad else f"\n{bad} line(s) to fix (or TODOs not written yet).")
    print("These are the examples only: ✔ Check my work tries your functions on cases they have never seen.")


# ------------------------------------------------------------------------------------------------- lag
def _pct(values, q):
    import numpy as np
    return float(np.percentile(values, q))


def lag(speeds):
    if not os.path.exists(DATA):
        sys.exit(f"{DATA} is missing: the course data is not mounted in this sandbox — tell your teacher.")
    with open(DATA, newline="") as f:
        rows = list(csv.DictReader(f))
    ages = [float(r["published_s"]) - float(r["exposure_s"]) for r in rows]
    match = [float(r["match_err_m"]) for r in rows]
    print(f"{len(rows)} day-vision fixes. Age when they reach the judge (= latency): median {_pct(ages, 50):.3f} s, "
          f"p90 {_pct(ages, 90):.3f} s, max {max(ages):.3f} s")
    print(f"older than 3.0 s: {sum(a > 3.0 for a in ages)} fixes · older than 5.0 s: {sum(a > 5.0 for a in ages)} fixes")
    print(f"the matcher states σ = {STATED_DAY_SIGMA_M:.0f} m for every fix; its match error is "
          f"{min(match):.2f}–{max(match):.2f} m (at the photo's instant)\n")
    print("error NOW = staleness_m(speed, age) + match error   (worst case: both point the same way)\n")
    series = {}
    for v in speeds:                                   # YOUR staleness_m first: a stub stops here, plainly
        series[v] = [rk.need_ok(est_mod, "staleness_m", v, a, kind=float) + m for a, m in zip(ages, match)]
    print(f"{'speed':>10} | {'median error':>12} | {'p90 error':>9} | {'within σ = 30 m':>15}")
    for v, errs in series.items():
        within = 100.0 * sum(e <= STATED_DAY_SIGMA_M for e in errs) / len(errs)
        print(f"{v:>6.1f} m/s | {_pct(errs, 50):>10.2f} m | {_pct(errs, 90):>7.2f} m | {within:>13.2f} %")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs(OUT, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    top = max(max(e) for e in series.values())
    bins = [i * top / 40 for i in range(41)]
    for v, errs in series.items():
        ax.hist(errs, bins=bins, alpha=0.55, label=f"{v:g} m/s")
    ax.axvline(STATED_DAY_SIGMA_M, color="k", ls="--", lw=1.2)
    ax.text(STATED_DAY_SIGMA_M, ax.get_ylim()[1] * 0.92, "  stated σ = 30 m", fontsize=9)
    ax.set_xlabel("error of the day-vision position when the judge uses it (m)")
    ax.set_ylabel("fixes")
    ax.set_title("A position is as old as its photo")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(OUT, "lag.png")
    fig.savefig(path, dpi=110)
    rk.saved(path)


# ----------------------------------------------------------------------------------------------- judge
def _v0():
    av0 = rk.load_student("navera_lite.ros.arbiter_v0")
    rp = rk.load_student("navera_lite.ros.replay_node")
    return av0, rp


def _rows(path):
    _, rp = _v0()
    if not os.path.exists(path):
        sys.exit(f"{path} does not exist. Write it first (lab Step 5): a CSV with the header "
                 "t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s")
    try:
        rows = rp.read_rows(path)
    except ValueError as e:
        sys.exit(f"{e}\nThe header must be: t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s "
                 "(lesson §5 and the replay node's docstring).")
    if not rows:
        sys.exit(f"{path} has a header but no row to play.")
    return rows


def play(rows, use_eligible, until=None, step=0.5):
    """Feed the rows to a NaiveJudge on a simulated clock; return [(t, state, reason)] at every arrival and
    every `step` seconds, until `until` (default: 10 s after the last row)."""
    av0, rp = _v0()
    try:
        judge = av0.NaiveJudge(cfg(), use_eligible=use_eligible)
    except ValueError as e:
        sys.exit(str(e))
    end = rows[-1]["t_s"] + 10.0 if until is None else float(until)
    times = sorted({r["t_s"] for r in rows} | {k * step for k in range(int(end / step) + 1)})
    out, i = [], 0
    for t in times:
        while i < len(rows) and rows[i]["t_s"] <= t:
            judge.receive(rp.row_to_estimate(rows[i], CLOCK0 + rows[i]["t_s"]), CLOCK0 + rows[i]["t_s"])
            i += 1
        try:
            d = judge.decide(CLOCK0 + t)
        except Exception as e:
            who = "your eligible() or stated_sigma()" if use_eligible else "the judge"
            sys.exit(f"at t = {t:.1f} s {who} stopped with {type(e).__name__}: {e}{_hint(e)}")
        out.append((t, d["state"], d["reason"]))
    return out


def judge(path, use_eligible, until):
    rows = _rows(path)
    who = "arbiter v0 with YOUR eligible() and stated_sigma()" if use_eligible else "arbiter v0 (naive)"
    print(f"{path}: {len(rows)} fix(es), the last at t = {rows[-1]['t_s']:.1f} s. Judge: {who}.")
    print("Simulated clock, no ROS: the same decisions as the node, without discovery delays.\n")
    last = None
    for t, state, reason in play(rows, use_eligible, until):
        key = (state, re.sub(r"[0-9.]+", "#", reason))       # a new age is not a new verdict
        if key != last:
            print(f"t = {t:5.1f} s  {_short(state, reason, 80)}")
            last = key
    print(f"t = {t:5.1f} s  {_short(state, reason, 80)}   (end of the simulation)")


def _short(state, reason, width=38):
    """'NO_FIX no usable source (gps: from the future)' → 'NO_FIX   gps: from the future' (the simulation's short
    form; the live judge's message is the long one)."""
    if reason.startswith("no usable source (") and reason.endswith(")"):
        reason = reason[len("no usable source ("):-1]
    text = f"{state:8s} {reason}"
    return text if len(text) <= width else text[:width - 1] + "…"


def attacks(mine):
    files = sorted(glob.glob("attacks/*.csv"))
    if not files:
        sys.exit("no attacks/*.csv yet (lab Step 5).")
    print("Simulated verdict 0.5 s after the last fix of each file (no ROS).\n")
    head = f"{'file':22s} | {'arbiter v0 (naive)':38s}"
    print(head + (f" | {'v0 + YOUR eligible()':38s}" if mine else ""))
    for path in files:
        try:
            rows = _rows(path)
        except SystemExit as e:
            print(f"{path:22s} | cannot be read: {e}")
            continue
        t_end = rows[-1]["t_s"] + 0.5
        _, s0, r0 = play(rows, False, until=t_end)[-1]
        line = f"{path:22s} | {_short(s0, r0):38s}"
        if mine:
            _, s1, r1 = play(rows, True, until=t_end)[-1]
            line += f" | {_short(s1, r1):38s}"
        print(line)
    print("\nAn attack works when v0 says FIX although an honest judge must not (lesson §5).")


# ---------------------------------------------------------------------------------------------- status
def status(watch_s):
    """Listen to the LIVE judge on /navera_lite/status. watch_s None: print the last status of 6 s; else print
    every change of state or message (numbers ignored) during watch_s seconds, with the time since the start."""
    try:
        import rclpy
        from diagnostic_msgs.msg import DiagnosticStatus
        from navera_lite.ros.qos import STATUS_QOS
    except ImportError as e:
        sys.exit(f"ROS 2 is not available in this terminal ({e}): open a new terminal tab.")
    got = []
    rclpy.init()
    node = rclpy.create_node("lab_status")
    node.create_subscription(DiagnosticStatus, "/navera_lite/status", got.append, STATUS_QOS)
    t0 = time.time()
    end = t0 + (6.0 if watch_s is None else float(watch_s))
    last, seen = None, 0
    try:
        while time.time() < end:
            rclpy.spin_once(node, timeout_sec=0.1)
            if watch_s is None:
                continue
            for msg in got[seen:]:
                state = {kv.key: kv.value for kv in msg.values}.get("state", "?")
                key = (state, re.sub(r"[0-9.]+", "#", msg.message))
                if key != last:
                    print(f"{time.time() - t0:5.1f} s  {state} | {msg.message}", flush=True)
                    last = key
            seen = len(got)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    if not got:
        sys.exit("no status in this time: is the judge running in THIS terminal tab? (`jobs`, then `tail arbiter.log`)")
    if watch_s is None:
        msg = got[-1]
        state = {kv.key: kv.value for kv in msg.values}.get("state", "?")
        print(f"{state} | {msg.message}")
    else:
        print(f"{time.time() - t0:5.1f} s  (end of the watch)")


def main():
    args = sys.argv[1:]
    mode = args[0] if args else ""
    if mode == "test":
        test()
    elif mode == "lag":
        speeds = [40.0, 15.0]
        if "--speed" in args:
            try:
                speeds = [float(args[args.index("--speed") + 1])]
            except (IndexError, ValueError):
                sys.exit("write a number after --speed, e.g. python3 contract_lab.py lag --speed 20")
        lag(speeds)
    elif mode == "judge":
        if len(args) < 2 or args[1].startswith("--"):
            sys.exit("which scenario? e.g. python3 contract_lab.py judge attacks/zero.csv")
        until = None
        if "--until" in args:
            try:
                until = float(args[args.index("--until") + 1])
            except (IndexError, ValueError):
                sys.exit("write a number of seconds after --until, e.g. --until 70")
        judge(args[1], "--eligible" in args, until)
    elif mode == "attacks":
        attacks("--eligible" in args)
    elif mode == "status":
        watch = None
        if "--watch" in args:
            try:
                watch = float(args[args.index("--watch") + 1])
            except (IndexError, ValueError):
                sys.exit("write a number of seconds after --watch, e.g. --watch 45")
        status(watch)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
