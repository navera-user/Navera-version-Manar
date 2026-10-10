"""where_am_i.py — runs YOUR functions of beacons.py on the lab's scenarios, and draws them.

    python3 where_am_i.py test       check each function on its docstring example
    python3 where_am_i.py clean      exact ranges, brute force                   (Step 3)
    python3 where_am_i.py clock      receiver clock 1 µs ahead                    (Step 4)
    python3 where_am_i.py two        three beacons, then only two                 (Step 5)
    python3 where_am_i.py gn         Gauss–Newton against brute force             (Step 6)
    python3 where_am_i.py spoof      a full spoof                                 (Step 7)
    python3 where_am_i.py partial    four beacons, only three spoofed             (Step 7)
    python3 where_am_i.py gate       the jump gate against two attacks            (Step 8)
    python3 where_am_i.py flight     the spoofed survey flight                    (Step 10)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import contextlib
import csv
import inspect
import io
import math
import os
import sys
import time
import traceback

# ---- you don't need to change anything in this file (but you can read it!) ----

BEACONS = [(0, 0), (10, 0), (0, 10)]
NAMES = ["A", "B", "C", "D"]
TRUTH = (3, 4)
EXACT = [5.0, 8.062, 6.708]
LATE = [5.3, 8.362, 7.008]          # clock 1 µs ahead: + 0.3 km on every range
FAKE = (7, 2)

try:
    import beacons as b
except Exception:                   # a syntax error in beacons.py: show it simply
    print("beacons.py has an error, so it cannot be loaded:\n")
    traceback.print_exc(limit=0)
    print("\nRead the LAST line above: it names the problem and the line number.")
    sys.exit(1)


def call(fn, *args):
    """Run one of your functions; turn a crash or a missing return into one plain sentence."""
    try:
        result = getattr(b, fn)(*args)
        if result is None:
            try:
                stub = "return None   # TODO" in inspect.getsource(getattr(b, fn))
            except (OSError, TypeError):
                stub = False
            if stub:
                return None, f"{fn}() is not written yet: write its TODO in beacons.py and `return` the result"
            return None, (f"{fn}() returned None for this case: every path must end with a `return` "
                          "(an `if` without `else`?)")
        return result, None
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        mine = [f for f in tb if f.filename.endswith("beacons.py")]
        where = "beacons.py"
        if mine:
            deepest = mine[-1]
            where = f"beacons.py line {deepest.lineno}"
            if deepest.name != fn:
                outer = next((f for f in mine if f.name == fn), None)
                where = (f"in {deepest.name}() line {deepest.lineno}, called from {fn}()"
                         + (f" line {outer.lineno}" if outer else "") + " — the mistake may be in what "
                         f"{fn}() passes to {deepest.name}()")
        extra = ""
        if isinstance(e, NameError) and "sqrt" in str(e):
            extra = " — write math.sqrt, with `import math` at the top"
        if any(k in str(e) for k in ("could not be broadcast", "length-1 arrays", "0-dimensional arrays")):
            extra = " — did you write `delta = np.linalg.lstsq(...)` without `, *_`?"
        return None, f"{fn}() stopped with {type(e).__name__}: {e} ({where}){extra}"


def need_ok(fn, *args, n=None):
    """Call a function needed by a scenario; stop with a plain message if it is not usable yet."""
    v, err = call(fn, *args)
    if err:
        sys.exit(err)
    if n is not None and (not isinstance(v, (list, tuple)) or len(v) != n):
        sys.exit(f"{fn}() must return {n} numbers, but it returned {v!r}.")
    return v


def km(v):
    return f"{v:.3f} km"


def plt_or_none():
    try:
        import warnings
        warnings.filterwarnings("ignore", message="Unable to import Axes3D")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        return None


def picture(name, circles, points, title, bias=0.0):
    """Draw beacons, circles (radius = measured − bias) and points; save out/<name>.png."""
    plt = plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    colours = {"A": "#0b6e8a", "B": "#d17a00", "C": "#7a3fb0", "D": "#2e8b57"}
    for (bx, by), r, n in circles:
        ax.add_patch(plt.Circle((bx, by), max(r - bias, 0), fill=False, color=colours[n], lw=1.6,
                                label=f"circle around {n}"))
        ax.plot(bx, by, "s", color="#e8706a", ms=10)
        ax.annotate(n, (bx, by), xytext=(8, 8), textcoords="offset points", color="#b0453a", weight="bold")
    for (x, y), label, style in points:
        if style == "o":                      # the truth: a hollow ring, so a point on it stays visible
            ax.plot(x, y, "o", ms=14, mfc="none", mec="k", mew=2, label=label)
        else:
            ax.plot(x, y, style, ms=9, label=label)
    ax.set_xlim(-1, 11); ax.set_ylim(-1, 11); ax.set_aspect("equal"); ax.grid(alpha=.3)
    ax.set_xlabel("x (km)"); ax.set_ylabel("y (km)"); ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    fig.savefig(f"out/{name}.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    print(f"\n🖼  picture saved: out/{name}.png (open it in the 📝 Code tab)")


def settings():
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            import answers
        except Exception as e:
            sys.exit(f"answers.py has an error, so it cannot be read: {type(e).__name__}: {e}\n"
                     'Text must be in quotes, for example PREDICT_GATE = "two".')
    try:
        v, m = float(answers.V_MAX_MPS), float(answers.MARGIN_M)
    except Exception:
        v = m = 0.0
    if v <= 0 or m <= 0:
        sys.exit("First write V_MAX_MPS and MARGIN_M in answers.py (Step 1).")
    return v, m


def read_flight():
    rows = []
    with open("flight.csv") as f:
        for r in csv.DictReader(f):
            rows.append({k: (float(v) if v != "" else None) for k, v in r.items()})
    return rows


# ---------------------------------------------------------------- the scenarios
def test():
    flight_example = [{"t_s": 100, "gps_x_m": 0, "gps_y_m": 0, "vision_x_m": None, "vision_y_m": None,
                       "vision_sigma_m": None},
                      {"t_s": 101, "gps_x_m": 500, "gps_y_m": 0, "vision_x_m": 0, "vision_y_m": 0, "vision_sigma_m": 30}]
    cases = [
        ("distance", ((0, 0), (3, 4)), 5.0, 1e-6),
        ("distance", ((10, 0), (3, 4)), math.sqrt(65), 1e-6),
        ("mismatch", ((4, 4), BEACONS, EXACT), 1.409, 0.002),
        ("mismatch", (TRUTH, BEACONS, EXACT), 0.0, 1e-5),
        ("mismatch", (TRUTH, BEACONS, LATE, 0.3), 0.0, 1e-5),
        ("find_position", (BEACONS, EXACT), (3.0, 4.0), 1e-6),
        ("find_position_and_bias", (BEACONS, LATE), (3.0, 4.0, 0.3), 1e-6),
        ("find_position_and_bias", (BEACONS, [d - 0.05 for d in LATE]), (3.0, 4.0, 0.25), 1e-6),
        ("gauss_newton", (BEACONS, LATE), (3.0, 4.0, 0.3), 0.002),
        ("spoof_measurements", ([(0, 0), (10, 0)], (6, 8), 0.5), [10.5, math.sqrt(80) + 0.5], 1e-6),
        ("gate_ok", ((0, 0), (120, 0), 1.0, 100.0, 50.0), True, 0),
        ("gate_ok", ((0, 0), (500, 0), 1.0, 100.0, 50.0), False, 0),
        ("count_refused", ([(0, 0)] + [(500, 0)] * 6 + [(900, 0)], 1.0, 100.0, 50.0), 5, 0,
         "lesson's 7-row table: [(0,0)] + [(500,0)]*6 + [(900,0)], 1.0, 100.0, 50.0"),
        ("count_refused", ([(0, 0)] + [(300, 0)] * 8, 1.0, 100.0, 50.0), 2, 0,
         "300 m jump: [(0,0)] + [(300,0)]*8, 1.0, 100.0, 50.0"),
        ("first_disagreement", (flight_example,), 101, 0),
    ]
    done = 0
    for case in cases:
        fn, args, want, tol = case[:4]
        shown = ", ".join(repr(a) if not isinstance(a, list) or len(a) < 4 else "[…]" for a in args)
        if len(shown) > 70:
            shown = shown[:67] + "…"
        if len(case) > 4:
            shown = case[4]
        got, err = call(fn, *args)
        if err:
            print(f"✘ {err}")
            continue
        if isinstance(want, bool):
            ok = got is want or got == want
        elif isinstance(want, (tuple, list)):
            ok = (isinstance(got, (tuple, list)) and len(got) == len(want)
                  and all(isinstance(g, (int, float)) and abs(g - w) <= tol for g, w in zip(got, want)))
        else:
            ok = isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want) <= tol
        print(f"{'✔' if ok else '✘'} {fn}({shown})  ->  {got!r}" + ("" if ok else f"   (expected {want!r})"))
        done += ok
    print(f"\n{done} of {len(cases)} examples give the expected result.")


def clean():
    p = need_ok("find_position", BEACONS, EXACT, n=2)
    m = need_ok("mismatch", p, BEACONS, EXACT)
    print("Ranges:", ", ".join(f"{n} {km(d)}" for n, d in zip(NAMES, EXACT)))
    print(f"\nfind_position  ->  {p}     mismatch there: {m:.4f}")
    picture("clean", list(zip(BEACONS, EXACT, NAMES)), [(p, "found by find_position", "k*")], "Exact ranges")


def clock():
    print("The receiver clock is 1 µs ahead: every range is 0.3 km too long.")
    print("Pseudoranges:", ", ".join(f"{n} {km(d)}" for n, d in zip(NAMES, LATE)))
    p = need_ok("find_position", BEACONS, LATE, n=2)
    m = need_ok("mismatch", p, BEACONS, LATE)
    print(f"\n1) find_position (ignores the clock)  ->  {p}")
    print(f"   mismatch there: {m:.4f}      distance from the true position: {math.dist(p, TRUTH) * 1000:.0f} m")
    pts = [(TRUTH, "true position", "o"), (p, "find_position (no bias)", "rX")]
    q, err = call("find_position_and_bias", BEACONS, LATE)
    if err:
        print("\n2) " + err)
    elif not isinstance(q, (list, tuple)) or len(q) != 3:
        print(f"\n2) find_position_and_bias() must return three numbers (x, y, bias), but it returned {q!r}.")
    else:
        m2 = need_ok("mismatch", q[:2], BEACONS, LATE, q[2])
        print(f"\n2) find_position_and_bias  ->  x = {q[0]}, y = {q[1]}, bias = {q[2]} km")
        print(f"   mismatch there: {m2:.4f}      distance from the true position: {math.dist(q[:2], TRUTH) * 1000:.0f} m")
        pts.append((q[:2], "find_position_and_bias", "g*"))
    picture("clock", list(zip(BEACONS, LATE, NAMES)), pts, "Clock 1 µs ahead (circles = pseudoranges)")


def two():
    need_ok("mismatch", TRUTH, BEACONS, EXACT)
    print("Clock bias unknown. Counting the guesses (x, y, bias) with a mismatch below 0.005, among 214 221…")
    good = {}
    for label, nb in (("A, B and C", 3), ("only A and B", 2)):
        good[label] = []
        for i in range(101):
            for j in range(101):
                for k in range(21):
                    m = need_ok("mismatch", (i / 10, j / 10), BEACONS[:nb], LATE[:nb], k / 20)
                    if m < 0.005:
                        good[label].append((i / 10, j / 10, k / 20))
        print(f"\n  with {label}: {len(good[label])} guess(es) fit. Some of them:")
        for g in good[label][:: max(1, len(good[label]) // 5)][:5]:
            print(f"     x = {g[0]:4.1f}  y = {g[1]:4.1f}  bias = {g[2]:.2f}")
    pts = [((g[0], g[1]), "fitting (x, y), each with its own bias" if i == 0 else None, "b.")
           for i, g in enumerate(good["only A and B"])] + [(TRUTH, "true position", "o")]
    picture("two", list(zip(BEACONS[:2], LATE[:2], NAMES)), pts,
            "Only A and B, unknown clock: every blue dot fits\n(biases 0–1 km only: a short piece of the curve)")


def gn():
    print("Same pseudoranges (clock 1 µs ahead). Brute force against Gauss–Newton:\n")
    t0 = time.perf_counter()
    q = need_ok("find_position_and_bias", BEACONS, LATE, n=3)
    t1 = time.perf_counter()
    g = need_ok("gauss_newton", BEACONS, LATE, (5.0, 5.0, 0.0), 10, n=3)
    t2 = time.perf_counter()
    print(f"  brute force    ->  x = {q[0]:.4f}  y = {q[1]:.4f}  bias = {q[2]:.4f}   in {1000 * (t1 - t0):7.1f} ms")
    print(f"  Gauss–Newton   ->  x = {g[0]:.4f}  y = {g[1]:.4f}  bias = {g[2]:.4f}   in {1000 * (t2 - t1):7.1f} ms")
    print("\nGauss–Newton, step by step from the guess (5, 5, 0):")
    for s in range(1, 5):
        g = need_ok("gauss_newton", BEACONS, LATE, (5.0, 5.0, 0.0), s, n=3)
        m = need_ok("mismatch", g[:2], BEACONS, LATE, g[2])
        print(f"  after {s} step(s): x = {g[0]:.4f}  y = {g[1]:.4f}  bias = {g[2]:.4f}   mismatch = {m:.2e}")


def spoof():
    print(f"You are really at {TRUTH}. A spoofer wants you to believe you are at {FAKE}.")
    fake_m = need_ok("spoof_measurements", BEACONS, FAKE, 0.3, n=3)
    print("The spoofer sends:", ", ".join(f"{n} {km(d)}" for n, d in zip(NAMES, fake_m)))
    q = need_ok("gauss_newton", BEACONS, fake_m, (5.0, 5.0, 0.0), 10, n=3)
    m = need_ok("mismatch", q[:2], BEACONS, fake_m, q[2])
    print(f"\nYour receiver computes: x = {q[0]:.3f}, y = {q[1]:.3f}, bias = {q[2]:.3f} km")
    print(f"mismatch there: {m:.4f}      distance from the TRUE position: {math.dist(q[:2], TRUTH) * 1000:.0f} m")
    picture("spoof", list(zip(BEACONS, fake_m, NAMES)),
            [(TRUTH, "where you really are", "o"), (q[:2], "what the receiver says", "r*")],
            "Full spoof", bias=q[2])


def partial():
    four = BEACONS + [(10, 10)]
    real = [need_ok("distance", TRUTH, s) + 0.3 for s in four]
    full = need_ok("spoof_measurements", four, FAKE, 0.3, n=4)
    part = list(full[:3]) + [real[3]]
    print("Four beacons now: D = (10, 10) is added. You are at (3, 4); your clock is 1 µs ahead.")
    print("The spoofer can overpower A, B and C, but D's real signal still reaches you.\n")
    for label, meas in (("no spoof          ", real), ("full spoof (A–D)  ", full), ("partial (A, B, C) ", part)):
        q = need_ok("gauss_newton", four, meas, (5.0, 5.0, 0.0), 10, n=3)
        m = need_ok("mismatch", q[:2], four, meas, q[2])
        print(f"  {label} -> x = {q[0]:6.3f}  y = {q[1]:6.3f}  bias = {q[2]:6.3f}   mismatch = {m:.4f}"
              f"   ({math.dist(q[:2], TRUTH) * 1000:5.0f} m from the truth)")


def gate():
    v_max, margin = settings()
    print(f"NAVERA's settings from your answers.py: v_max = {v_max:g} m/s, margin = {margin:g} m. One fix per second.")
    attacks = {
        "A) a 300 m jump, then the fake position stays": [(0, 0)] + [(300, 0)] * 8,
        "B) a slow drag: 20 m further every second, for 60 s": [(20 * t, 0) for t in range(61)],
    }
    for title, fixes in attacks.items():
        print(f"\n{title}")
        n = need_ok("count_refused", fixes, 1.0, v_max, margin)
        line, last, elapsed = [], fixes[0], 0.0
        for f in fixes[1:11]:
            elapsed += 1.0
            ok = need_ok("gate_ok", last, f, elapsed, v_max, margin)
            line.append("✔" if ok else "✘")
            if ok:
                last, elapsed = f, 0.0
        print(f"   first {len(line)} fixes (gate_ok):  " + " ".join(line) + "      (✔ accepted, ✘ refused)")
        print(f"   count_refused  ->  {n} refused, final position {fixes[-1][0]} m from the start")
        if len(fixes) <= 11 and n != line.count("✘"):
            print("   ⚠ count_refused and gate_ok disagree on these fixes: check TODO 8 (see the Step 8 hints)")


def flight():
    v_max, margin = settings()
    rows = read_flight()
    fixes = [(r["gps_x_m"], r["gps_y_m"]) for r in rows]
    n = need_ok("count_refused", fixes, 1.0, v_max, margin)
    t = need_ok("first_disagreement", rows)
    shifted = [dict(r, t_s=r["t_s"] + 1000) for r in rows]
    t2, _ = call("first_disagreement", shifted)
    if t is not None and t2 is not None and t2 != t + 1000:
        print("⚠ first_disagreement() seems to return the row number, not the row's t_s "
              "(here they are equal by chance; the check uses other times).")
    vision = [r for r in rows if r["vision_x_m"] is not None]
    print(f"Simulated survey flight: {len(rows)} s, one GPS fix per second, day vision on {len(vision)} of them.")
    print(f"\n  jump gate alone (count_refused, v_max {v_max:g}, margin {margin:g})  ->  {n} fixes refused")
    shown = int(t) if isinstance(t, float) and t.is_integer() else t
    print(f"  cross-check (first_disagreement, 5 σ + 50 m)            ->  first disagreement at t = {shown}")
    if t is not None:
        r = next(r for r in rows if r["t_s"] == t)
        d = need_ok("distance", (r["gps_x_m"], r["gps_y_m"]), (r["vision_x_m"], r["vision_y_m"]))
        print(f"     at that moment GPS and vision are {d:.0f} m apart")
    plt = plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(2, 1, figsize=(8, 5.5), sharex=True)
    ts = [r["t_s"] for r in rows]
    ax[0].plot(ts, [r["gps_y_m"] for r in rows], color="#d17a00", lw=1, label="GPS: north offset (m)")
    ax[0].plot([r["t_s"] for r in vision], [r["vision_y_m"] for r in vision], ".", ms=2, color="#0b6e8a",
               label="day vision: north offset (m)")
    ax[1].plot([r["t_s"] for r in vision],
               [math.dist((r["gps_x_m"], r["gps_y_m"]), (r["vision_x_m"], r["vision_y_m"])) for r in vision],
               ".", ms=2, color="#7a3fb0", label="|GPS − vision| (m)")
    ax[1].axhline(5 * 30 + 50, color="#b0453a", ls="--", label="cross-check limit 5 σ + 50 m")
    for a in ax:
        a.axvspan(200, 450, color="#cfe6f5", alpha=.6, lw=0)
        a.grid(alpha=.3); a.legend(fontsize=8, loc="upper left")
    ax[0].set_title("Simulated flight — the blue band is the sea (no vision match)")
    ax[1].set_xlabel("time (s)")
    fig.savefig("out/flight.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    print("\n🖼  picture saved: out/flight.png (open it in the 📝 Code tab)")


if __name__ == "__main__":
    steps = {"test": test, "clean": clean, "clock": clock, "two": two, "gn": gn, "spoof": spoof,
             "partial": partial, "gate": gate, "flight": flight}
    if len(sys.argv) != 2 or sys.argv[1] not in steps:
        sys.exit(__doc__)
    steps[sys.argv[1]]()
