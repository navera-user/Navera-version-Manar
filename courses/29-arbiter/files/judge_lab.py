"""judge_lab.py — runs YOUR judge (navera_lite/arbiter.py) on the lab's situations, without ROS.

    python3 judge_lab.py test                       each TODO on its docstring example, and a few traps
    python3 judge_lab.py play FILE                  your judge on a scenario, on a simulated clock: every change
    python3 judge_lab.py play FILE --v0             the same scenario through arbiter v0 (naive, mission 09)
    python3 judge_lab.py play FILE --v0 --eligible  … through arbiter v0 with estimate.eligible() (mission 12)
    python3 judge_lab.py play FILE --open-door      your judge, with its door's future test switched off
    python3 judge_lab.py play FILE --until 45       keep the clock running until t = 45 s
    python3 judge_lab.py status                     the LIVE judge's state and message (listens 6 s)

FILE is a scenario CSV (mission 12's format: t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s); the lab's
scenarios are in /data/academy/29-arbiter/. Pictures are saved in out/ — click them in the file list.
"""
import os
import re
import sys
import time

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = "/data/academy/29-arbiter"
OUT = "out"
CLOCK0 = 1000.0           # the simulated clock at t = 0 of a scenario (s)
TICK_S = 0.2              # the judge also decides at tick_hz = 5 Hz (navera_lite.yaml)

arb_mod = rk.load_student("navera_lite.arbiter")
est_mod = rk.load_student("navera_lite.estimate")
settings = rk.load_student("navera_lite.settings")
Estimate = est_mod.Estimate
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if isinstance(e, KeyError):
        return (" — a dict has no such key: since[...] of a source that is not in since? TODO 2 must give every "
                "candidate its instant, AND step() must call track_since() BEFORE pick() (lab Step 4, hint 3) — "
                "or a cfg key misspelt (the names of navera_lite.yaml)")
    if isinstance(e, TypeError) and "'NoneType' object is not iterable" in s:
        return " — a function returned None where a list or a pair was expected: is that TODO written?"
    if isinstance(e, AttributeError) and "'NoneType'" in s:
        return " — something is None: a TODO not written yet (it returns None), or self.latest.get() of a missing source"
    if isinstance(e, TypeError) and "unhashable" in s:
        return " — a list or an Estimate used as a dict key: the keys are the source names (\"gps\", …)"
    return _kit_hint(e)


rk._hint = _hint


def cfg():
    """The settings of your navera_lite.yaml (the defaults if it cannot be read)."""
    try:
        return settings.load("navera_lite.yaml")
    except Exception as e:                      # a broken yaml: say so, then use the defaults
        print(f"(navera_lite.yaml could not be read: {e} — using the defaults)")
        return dict(settings.DEFAULTS)


def cov9(sigma):
    v = float(sigma) ** 2
    return (v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 * v)


# ------------------------------------------------------------------------------------------------ test
def _same(got, want):
    if isinstance(want, float):
        return isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want) < 1e-6
    if isinstance(want, tuple):
        return isinstance(got, (tuple, list)) and len(got) == len(want) and all(_same(g, w) for g, w in zip(got, want))
    return got == want


def _gps(stamp, sigma=3.0, **kw):
    return Estimate("gps", kw.pop("lat", 35.8256), kw.pop("lon", 10.6084), stamp, cov=cov9(sigma), cov_type=1, **kw)


def _day(stamp, sigma=30.0, **kw):
    return Estimate("day", 35.8257, 10.6085, stamp, cov=cov9(sigma), cov_type=1, **kw)


def test():
    """Each function on its docstring example and a few traps."""
    D = dict(cfg())
    A = arb_mod
    print("Each line runs one of YOUR functions. A TODO you have not written yet shows ✘ — that is normal.\n")
    bad = 0

    def line(todo, label, ok, note):
        nonlocal bad
        bad += not ok
        print(f"{'✔' if ok else '✘'} TODO {todo} — {label}: {note}")

    def case(todo, label, fn, args, want):
        got, err = rk.call(A, fn, *args)
        if err and "returned None for this case" in err and want is None:
            got, err = None, None                     # None may be the right answer
        if err and "returned None for this case" in err and fn == "pick":
            err = (f"returned None (no winner), the docstring/lesson says {want!r} — when the current winner is not a "
                   "candidate (lost, or None), there is no hold-off: the first candidate wins at once (Step 2, hint 1)")
        if err:
            line(todo, label, False, err)
        elif _same(got, want):
            line(todo, label, True, repr(got))
        else:
            line(todo, label, False, f"returned {got!r}, the docstring/lesson says {want!r}")

    # TODO 1
    got, err = rk.call(A, "candidates", {"day": Estimate("day", 35.8, 10.6, 98.5),
                                         "gps": Estimate("gps", 35.8, 10.6, 96.0)}, 100.0, D)
    if err:
        line(1, "candidates(), the docstring example", False, err)
    else:
        note = repr(got) if got == ["day"] else f"returned {got!r}, the docstring says ['day']"
        if got != ["day"] and isinstance(got, list) and "gps" in got:
            note += (" — the GPS fix is 4.0 s old (stale): eligible() returns a PAIR (ok, reason), and a pair is "
                     "always true in an `if`: use eligible(...)[0]")
        line(1, "candidates(), the docstring example", got == ["day"], note)
    case(1, "a dict in the 'wrong' order: the answer is in PRIORITY order", "candidates",
         ({"celestial": Estimate("celestial", 35.8, 10.6, 80.0), "day": _day(99.0), "gps": _gps(99.5)}, 100.0, D),
         ["gps", "day", "celestial"])
    case(1, "nothing stored yet", "candidates", ({}, 100.0, D), [])
    # TODO 2
    case(2, "track_since(), the docstring example", "track_since",
         ({"day": 90.0, "night": 95.0}, ["gps", "day"], 100.0), {"gps": 100.0, "day": 90.0})
    case(2, "nobody eligible: everything is forgotten", "track_since", ({"gps": 50.0}, [], 100.0), {})
    # TODO 3
    S = {"gps": 99.0, "day": 80.0}
    case(3, "pick(), the docstring example (GPS waits)", "pick", (["gps", "day"], "day", S, 100.0, D), "day")
    case(3, "the same, 1 s later: the hold-off is over", "pick", (["gps", "day"], "day", S, 101.0, D), "gps")
    case(3, "exactly 2.0 s of eligibility: GPS takes over", "pick",
         (["gps", "day"], "day", {"gps": 97.5, "day": 80.0}, 99.5, D), "gps")
    case(3, "night wins; day has waited, GPS not yet: day takes over", "pick",
         (["gps", "day", "night"], "night", {"gps": 99.5, "day": 90.0, "night": 80.0}, 100.0, D), "day")
    case(3, "the winner is lost: the next one at once", "pick", (["day"], "gps", {"day": 99.9}, 100.0, D), "day")
    case(3, "no winner before: the best one at once", "pick", (["gps", "day"], None, S, 99.1, D), "gps")
    case(3, "no candidate", "pick", ([], "gps", {}, 100.0, D), None)
    # TODO 4 and 5: on a fresh Arbiter each time
    arb, err = rk.call(A, "Arbiter", D)
    if err:
        line(4, "Arbiter(cfg)", False, err)
        return _end(bad)

    def fresh():
        return A.Arbiter(D)

    a = fresh()
    got, err = rk.call(a, "receive", Estimate("gps", 35.8, 10.6, 120.0), 100.0)
    if err:
        line(4, "receive(), the docstring example (a fix 20 s in the future)", False, err)
    else:
        ok = _same(got, (False, "from the future (20.0 s ahead)")) and a.latest == {}
        line(4, "receive(), the docstring example (a fix 20 s in the future)", ok,
             repr(got) if ok else f"returned {got!r} and latest = {a.latest!r}; the docstring says "
             "(False, 'from the future (20.0 s ahead)') and nothing stored")
        ok = a.refused.get("gps", "").startswith("from the future")
        line(4, "… and the refusal is remembered in refused[\"gps\"]", ok,
             repr(a.refused) if ok else f"refused = {a.refused!r}")
    a = fresh()
    got, err = rk.call(a, "receive", _gps(99.6), 100.0)
    line(4, "a fresh GPS fix is stored", not err and _same(got, (True, "stored")) and "gps" in a.latest,
         err or f"{got!r}, latest has {sorted(a.latest)}")
    if not err:
        got, err = rk.call(a, "receive", _gps(99.1), 100.2)
        line(4, "a fix older than the stored one: old news", not err and _same(got, (False, "old news"))
             and a.latest["gps"].stamp_s == 99.6, err or f"{got!r}, the stored stamp is {a.latest['gps'].stamp_s}")
        got, err = rk.call(a, "receive", _gps(100.6, lat=35.8706), 100.6)     # 5 km north in 1 s
        line(4, "a GPS fix 5 km away 1 s later: refused by the jump gate",
             not err and isinstance(got, (tuple, list)) and got and got[0] is False and "jump" in str(got[1])
             and a.latest["gps"].stamp_s == 99.6, err or f"{got!r}")
        got, err = rk.call(a, "receive", Estimate("gps", float("nan"), float("nan"), 101.0, valid=False), 101.0)
        line(4, "a GPS saying 'no position' (valid False) is stored: the source is alive",
             not err and _same(got, (True, "stored")) and a.latest["gps"].valid is False, err or f"{got!r}")
        got, err = rk.call(a, "receive", Estimate("radar", 35.8, 10.6, 101.0), 101.0)
        line(4, "an unknown source is refused", not err and isinstance(got, (tuple, list)) and got and got[0] is False,
             err or f"{got!r}")
    a = fresh()
    got, err = rk.call(a, "receive", _gps(float("nan")), 100.0)
    line(4, "a GPS fix stamped NaN: bad stamp (a NaN passes every `x > limit` test and never ages)",
         not err and _same(got, (False, "bad stamp")) and a.latest == {},
         err or f"returned {got!r}, latest has {sorted(a.latest)} — the docstring says (False, 'bad stamp'), "
         "nothing stored: test it with math.isfinite(est.stamp_s) (NaN == NaN is False, so `== float('nan')` "
         "never catches it)")
    a = fresh()
    a.receive(Estimate("gps", 35.8, 10.6, 120.0), 100.0)
    got, err = rk.call(a, "receive", _gps(100.4), 100.5)
    ok = not err and _same(got, (True, "stored")) and "gps" not in a.refused
    line(4, "a good fix stored after a refused one clears the refusal", ok,
         err or (repr(a.refused) if ok else f"returned {got!r}, refused = {a.refused!r} — storing a fix forgets its "
                 "source's refusal (self.refused.pop(name, None))"))
    if not err and "gps" in a.latest:
        tr = a.latest["gps"].t_recv_s
        line(4, "the stored fix records when it arrived (est.t_recv_s = now_s)", tr == 100.5,
             f"t_recv_s = {tr!r}" + ("" if tr == 100.5 else " — the docstring says 100.5 (now_s)"))
    # TODO 5
    a = fresh()
    d, err = rk.call(a, "step", 0.0)
    line(5, "step() before anything: STARTING", not err and getattr(d, "state", None) == "STARTING",
         err or f"state {getattr(d, 'state', d)!r}")
    a = fresh()
    a.receive(_gps(99.5), 100.0)
    d, err = rk.call(a, "step", 100.0)
    want = ("FIX", "gps", "gps: σ 3.0 m", True)
    got = (getattr(d, "state", None), getattr(d, "source", None), getattr(d, "reason", None), getattr(d, "switched", None))
    line(5, "the docstring example", not err and got == want and a.switches == [(100.0, None, "gps")],
         err or f"{got!r}, switches {a.switches!r}" + ("" if got == want else f" — the docstring says {want!r}"))
    if not err:
        a.receive(_day(102.0), 102.4)
        d, err = rk.call(a, "step", 104.0)            # GPS stale (4.5 s > 3.0 s): day, σ 30 m
        want = ("DEGRADED", "day", "day: σ 30.0 m > 25.0 m")
        got = None if err else (d.state, d.source, d.reason)
        line(5, "GPS 4.5 s old, a day fix: DEGRADED on day", got == want,
             err or repr(got) + ("" if got == want else f" — the docstring/lesson says {want!r}"))
        d, err = rk.call(a, "step", 108.0)
        ok = not err and d.state == "NO_FIX" and d.reason.startswith("no usable source (gps: stale")
        line(5, "everything old: NO_FIX with the reasons", ok,
             err or repr((d.state, d.reason)) + ("" if ok else " — the docstring says NO_FIX, "
                                                 "'no usable source (gps: stale (8.5 s > 3.0 s); day: stale …)'"))
        want_sw = [(100.0, None, "gps"), (104.0, "gps", "day"), (108.0, "day", None)]
        line(5, "the switches so far", a.switches == want_sw,
             repr(a.switches) + ("" if a.switches == want_sw else f" — the docstring says {want_sw!r}: a change "
                                 "TO None (no winner) is a switch too"))
    a = fresh()
    a.receive(_day(99.8), 100.0)
    d0, err = rk.call(a, "step", 100.0)
    if not err:
        a.receive(_gps(100.4), 100.5)
        d, err = rk.call(a, "step", 100.5)
        got = None if err else (d.state, d.source)
        want = ("DEGRADED", "day")
        msg = err or repr(got) + ("" if got == want else f" — it should be {want!r} (GPS has waited 0.0 s)")
        if err and "KeyError" in err:
            msg = (f"{err.split(' (')[0]} — step() must bring self.since up to date (track_since) BEFORE it calls "
                   "pick(): pick() reads since[\"gps\"] of the new candidate")
        line(5, "a new candidate while day vision wins: since is updated BEFORE pick()", got == want, msg)
    _end(bad)


def _end(bad):
    print("\nAll the examples agree." if not bad else f"\n{bad} line(s) to fix (or TODOs not written yet).")
    print("These are the examples only: ✔ Check my work tries your judge on situations it has never seen.")


# ------------------------------------------------------------------------------------------------ play
def _rows(path):
    rp = rk.load_student("navera_lite.ros.replay_node")
    if not os.path.exists(path):
        sys.exit(f"{path} does not exist (the lab's scenarios are in {DATA}/)")
    try:
        rows = rp.read_rows(path)
    except ValueError as e:
        sys.exit(f"{e}\nThe header must be: t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s")
    if not rows:
        sys.exit(f"{path} has a header but no row to play.")
    return rows


class OpenDoor:
    """Your judge with the future test of its door switched off: during receive() only, the future tolerance
    is infinite. Everything else is your code (eligible() still refuses a fix from the future)."""

    def __init__(self, c):
        self.arb = arb_mod.Arbiter(c)

    def receive(self, est, now_s):
        keep = self.arb.cfg["future_tolerance_s"]
        self.arb.cfg["future_tolerance_s"] = 1e9
        try:
            return self.arb.receive(est, now_s)
        finally:
            self.arb.cfg["future_tolerance_s"] = keep

    def step(self, now_s):
        return self.arb.step(now_s)


class V0:
    """Arbiter v0 (mission 09) with the same two calls as your judge."""

    def __init__(self, c, use_eligible):
        av0 = rk.load_student("navera_lite.ros.arbiter_v0")
        self.j = av0.NaiveJudge(c, use_eligible=use_eligible)

    def receive(self, est, now_s):
        return self.j.receive(est, now_s)

    def step(self, now_s):
        d = self.j.decide(now_s)
        return arb_mod.Decision(d["state"], d["source"], d["estimate"], d["sigma_m"], d["reason"], d["sources"])


def simulate(judge, rows, until, tick_s=TICK_S, clock0=CLOCK0):
    """Feed the rows to a judge on a simulated clock, as the ROS node does: on each arrival receive() then
    step(); between arrivals step() every tick_s. Returns [(t, Decision, refusal or None)] for every decision.
    At equal times the arrival comes first."""
    rp = rk.load_student("navera_lite.ros.replay_node")
    out, i, k = [], 0, 0
    while True:
        tk = round(k * tick_s, 6)
        if i < len(rows) and rows[i]["t_s"] <= tk + 1e-9:
            t = rows[i]["t_s"]
            now = clock0 + t
            got = judge.receive(rp.row_to_estimate(rows[i], now), now)
            refusal = got[1] if isinstance(got, (tuple, list)) and len(got) == 2 and not got[0] else None
            out.append((t, judge.step(now), refusal))
            i += 1
        elif tk <= until + 1e-9:
            out.append((tk, judge.step(clock0 + tk), None))
            k += 1
        else:
            return out


def _short(state, reason, width=130):
    text = f"{state:8s} {reason}"
    return text if len(text) <= width else text[:width - 1] + "…"


def _key(d):
    return (d.state, d.source, re.sub(r"[0-9.]+", "#", d.reason))     # a new age is not a new decision


def play(path, mode, until):
    rows = _rows(path)
    c = dict(cfg())
    end = rows[-1]["t_s"] + 8.0 if until is None else float(until)
    if mode == "v0":
        judge, who = V0(c, False), "arbiter v0 (naive, mission 09)"
    elif mode == "v0e":
        judge, who = V0(c, True), "arbiter v0 with estimate.eligible() (mission 12)"
    elif mode == "open":
        judge, who = OpenDoor(c), "YOUR judge with its door's future test switched off"
    else:
        judge, who = arb_mod.Arbiter(c), "YOUR judge (navera_lite/arbiter.py)"
    print(f"{path}: {len(rows)} fix(es), the last at t = {rows[-1]['t_s']:.1f} s. Judge: {who}.")
    print("Simulated clock, no ROS: arrivals and 5 Hz ticks, as the node does. Only the CHANGES are printed.\n")
    try:
        run = simulate(judge, rows, end)
    except Exception as e:
        where = "Arbiter.receive() or Arbiter.step()" if mode in ("mine", "open") else "the judge"
        if isinstance(e, NotImplementedError) or "NoneType" in str(e):
            sys.exit(f"{where} is not written yet (or returns None): `python3 judge_lab.py test` shows which TODO.")
        sys.exit(f"{where} stopped with {type(e).__name__}: {e}{_hint(e)}")
    last, switches, prev_src = None, [], None
    same, same_key = [], [None]                 # repeated refusals of one kind: printed once, then counted

    def flush():
        if len(same) > 1:
            print(f"            ⤫ … the same refusal {len(same) - 1} more time(s), the last at t = {same[-1]:.1f} s")
        same.clear()

    for t, d, refusal in run:
        if refusal:
            key = refusal if refusal.startswith("jump") else re.sub(r"[0-9.]+", "#", refusal)
            if same and key == same_key[0]:
                same.append(t)
            else:
                flush()
                print(f"t = {t:5.1f} s  ⤫ refused at the door: {refusal}")
                same.append(t)
                same_key[:] = [key]
        if d is None:
            sys.exit("Arbiter.step() returned None: TODO 5 is not written yet.")
        if d.source != prev_src and t > 0:
            switches.append((t, prev_src, d.source))
        prev_src = d.source
        if _key(d) != last:
            flush()
            print(f"t = {t:5.1f} s  {_short(d.state, d.reason)}")
            last = _key(d)
    flush()
    t, d, _ = run[-1]
    print(f"t = {t:5.1f} s  {_short(d.state, d.reason)}   (end of the simulation)")
    shown = switches if len(switches) <= 8 else switches[:6]
    sw = ", ".join(f"{a or '—'}→{b or '—'} at {t:.1f} s" for t, a, b in shown)
    if len(switches) > 8:
        sw += f", … and {len(switches) - 6} more"
    print(f"\nchanges of winner: {len(switches)}" + (f" ({sw})" if switches else ""))
    _picture(path, who, run, mode)


COLORS = {"FIX": "#2e7d32", "DEGRADED": "#ef6c00", "NO_FIX": "#c62828", "STARTING": "#9e9e9e"}


def _picture(path, who, run, mode):
    plt = rk.plt_or_none()
    if plt is None:
        return
    srcs = ["celestial", "night", "day", "gps"]
    fig, ax = plt.subplots(figsize=(9.0, 3.4))
    for (t0, d, _), (t1, _, _) in zip(run, run[1:]):
        y = srcs.index(d.source) if d.source in srcs else -1
        ax.plot([t0, t1], [y, y], color=COLORS.get(d.state, "k"), lw=6, solid_capstyle="butt")
    ax.set_yticks(range(-1, 4))
    ax.set_yticklabels(["(none)"] + srcs)
    ax.set_xlabel("time since the start of the scenario (s)")
    ax.set_title(f"{os.path.basename(path)} — {who}", fontsize=9, pad=22)
    for state, col in COLORS.items():
        ax.plot([], [], color=col, lw=6, label=state)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), fontsize=7, ncol=4, frameon=False)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    name = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(OUT, f"{name}_{mode}.png")
    fig.savefig(out, dpi=100)
    rk.saved(out)


# ---------------------------------------------------------------------------------------------- status
def status(watch_s):
    """Listen to the LIVE judge on /navera_lite/status (as in mission 12)."""
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
        sys.exit("no status in this time: is your judge running in THIS terminal tab? (`jobs`, then `tail arbiter.log`)")
    if watch_s is None:
        msg = got[-1]
        values = {kv.key: kv.value for kv in msg.values}
        print(f"{values.get('state', '?')} | {msg.message}")
        for k in sorted(values):
            if k.startswith("src.") or k in ("waiting", "switches"):
                print(f"   {k:14s} {values[k] or '(none)'}")


def main():
    args = sys.argv[1:]
    mode = args[0] if args else ""
    if mode == "test":
        test()
    elif mode == "play":
        if len(args) < 2 or args[1].startswith("--"):
            sys.exit(f"which scenario? e.g. python3 judge_lab.py play {DATA}/race.csv")
        until = None
        if "--until" in args:
            try:
                until = float(args[args.index("--until") + 1])
            except (IndexError, ValueError):
                sys.exit("write a number of seconds after --until, e.g. --until 45")
        if "--v0" in args:
            who = "v0e" if "--eligible" in args else "v0"
        else:
            who = "open" if "--open-door" in args else "mine"
        play(args[1], who, until)
    elif mode == "status":
        watch = None
        if "--watch" in args:
            try:
                watch = float(args[args.index("--watch") + 1])
            except (IndexError, ValueError):
                sys.exit("write a number of seconds after --watch, e.g. --watch 30")
        status(watch)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
