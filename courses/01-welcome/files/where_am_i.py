"""where_am_i.py — runs YOUR functions of beacons.py on the lab's situations, and draws them.

    python3 where_am_i.py test     check each function with its example
    python3 where_am_i.py clean    exact distances                     (lab step 5)
    python3 where_am_i.py clock    the receiver clock is 1 µs ahead     (lab step 6)
    python3 where_am_i.py two      three beacons or two, unknown clock  (lab step 7)
    python3 where_am_i.py spoof    a spoofer sends a fake position      (lab step 8)
    python3 where_am_i.py gate     NAVERA's jump gate against two attacks (lab step 9)

Pictures are saved in the folder out/ — click them in the file list of the 📝 Code tab.
"""
import contextlib
import inspect
import io
import math
import os
import sys
import traceback

# ---- you don't need to change anything in this file (but you can read it!) ----

BEACONS = [(0, 0), (10, 0), (0, 10)]
NAMES = ["A", "B", "C"]
TRUTH = (3, 4)
EXACT = [5.0, 8.062, 6.708]
LATE = [5.3, 8.362, 7.008]          # clock 1 µs fast: + 0.3 km on every distance
FAKE = (7, 2)

try:
    import beacons as b
except Exception:                   # a syntax error in beacons.py: show it simply
    print("beacons.py has an error, so it cannot be loaded:\n")
    traceback.print_exc(limit=0)
    print("\nRead the LAST line above: it names the problem and the line number.")
    sys.exit(1)


def call(fn, *args):
    """Run one of your functions; turn a crash into a short message."""
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
        line = next((f.lineno for f in reversed(tb) if f.filename.endswith("beacons.py")), "?")
        extra = ""
        if isinstance(e, NameError) and "sqrt" in str(e):
            extra = " — write math.sqrt, with `import math` at the top"
        return None, f"{fn}() stopped with {type(e).__name__}: {e} (beacons.py line {line}){extra}"


def km(v):
    return f"{v:.3f} km"


def picture(name, circles, points, title, bias=0.0):
    """Draw beacons, circles (radius = measured − bias) and points; save out/<name>.png."""
    try:
        import warnings
        warnings.filterwarnings("ignore", message="Unable to import Axes3D")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    colours = {"A": "#0b6e8a", "B": "#d17a00", "C": "#7a3fb0"}
    for (bx, by), r, n in circles:
        ax.add_patch(plt.Circle((bx, by), max(r - bias, 0), fill=False, color=colours.get(n, "#0b6e8a"), lw=1.6,
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


def need(*names):
    """Stop with a friendly message if a function still returns its starter value."""
    starters = {"distance": ((0, 0), (3, 4)), "mismatch": ((4, 4), BEACONS, EXACT)}
    for n in names:
        if n in starters:
            v, err = call(n, *starters[n])
            if err:
                sys.exit(f"First finish {n}() — run:  python3 where_am_i.py test\n({err})")


# ---------------------------------------------------------------- the situations
def test():
    cases = [
        ("distance", ((0, 0), (3, 4)), 5.0, 1e-6),
        ("distance", ((10, 0), (3, 4)), math.sqrt(65), 1e-6),
        ("mismatch", ((4, 4), BEACONS, EXACT), 1.409, 0.002),
        ("mismatch", (TRUTH, BEACONS, EXACT), 0.0, 1e-5),
        ("mismatch", (TRUTH, BEACONS, LATE, 0.3), 0.0, 1e-5),
        ("find_position", (BEACONS, EXACT), (3.0, 4.0), 1e-6),
        ("find_position_and_bias", (BEACONS, LATE), (3.0, 4.0, 0.3), 1e-6),
        ("find_position_and_bias", (BEACONS, [d - 0.05 for d in LATE]), (3.0, 4.0, 0.25), 1e-6),
        ("spoof_measurements", ([(0, 0), (10, 0)], (6, 8), 0.5), [10.5, math.sqrt(80) + 0.5], 1e-6),
        ("gate_ok", ((0, 0), (120, 0), 1.0, 100.0, 50.0), True, 0),
        ("gate_ok", ((0, 0), (500, 0), 1.0, 100.0, 50.0), False, 0),
        ("count_refused", ([(0, 0)] + [(500, 0)] * 6 + [(900, 0)], 1.0, 100.0, 50.0), 5, 0),
    ]
    done = 0
    for fn, args, want, tol in cases:
        shown = ", ".join(repr(a) if not isinstance(a, list) or len(a) < 4 else "[…]" for a in args)
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
    need("distance", "mismatch")
    print("Beacons:", ", ".join(f"{n} {p}" for n, p in zip(NAMES, BEACONS)))
    print("Measured distances:", ", ".join(f"{n} {km(d)}" for n, d in zip(NAMES, EXACT)))
    p, err = call("find_position", BEACONS, EXACT)
    if err:
        sys.exit(err)
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        sys.exit(f"find_position() must return a point (x, y), but it returned {p!r}.")
    m, _ = call("mismatch", p, BEACONS, EXACT)
    print(f"\nfind_position  ->  {p}     mismatch there: {m:.4f}")
    picture("clean", list(zip(BEACONS, EXACT, NAMES)), [(p, "found by find_position", "k*")],
            "Exact distances")


def clock():
    need("distance", "mismatch")
    print("The receiver clock is 1 µs ahead: every range is 0.3 km too long.")
    print("Measured pseudoranges:", ", ".join(f"{n} {km(d)}" for n, d in zip(NAMES, LATE)))
    p, err = call("find_position", BEACONS, LATE)
    if err:
        sys.exit(err)
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        sys.exit(f"find_position() must return a point (x, y), but it returned {p!r}.")
    m, _ = call("mismatch", p, BEACONS, LATE)
    off = math.dist(p, TRUTH) * 1000
    print(f"\n1) find_position (ignores the clock)  ->  {p}")
    print(f"   mismatch there: {m:.4f}      distance from the true position: {off:.0f} m")
    pts = [(TRUTH, "true position", "o"), (p, "find_position (no bias)", "rX")]
    q, err = call("find_position_and_bias", BEACONS, LATE)
    if err:
        print("\n2) " + err)
    elif not isinstance(q, (list, tuple)) or len(q) != 3:
        print(f"\n2) find_position_and_bias() must return three numbers (x, y, bias), but it returned {q!r}.")
    else:
        m2, _ = call("mismatch", q[:2], BEACONS, LATE, q[2])
        print(f"\n2) find_position_and_bias  ->  x = {q[0]}, y = {q[1]}, bias = {q[2]} km")
        print(f"   mismatch there: {m2:.4f}      distance from the true position: "
              f"{math.dist(q[:2], TRUTH) * 1000:.0f} m")
        pts.append((q[:2], "find_position_and_bias", "g*"))
    picture("clock", list(zip(BEACONS, LATE, NAMES)), pts, "Clock 1 µs ahead (circles = pseudoranges)")


def two():
    need("distance", "mismatch")
    print("The clock bias is unknown. How many guesses (x, y, bias) explain the measurements")
    print("almost perfectly (mismatch below 0.005)? Trying all 214 221 guesses, twice…")
    counts = {}
    for label, nb in (("A, B and C", 3), ("only A and B", 2)):
        good = []
        for i in range(101):
            for j in range(101):
                for k in range(21):
                    m, err = call("mismatch", (i / 10, j / 10), BEACONS[:nb], LATE[:nb], k / 20)
                    if err:
                        sys.exit(err)
                    if m < 0.005:
                        good.append((i / 10, j / 10, k / 20))
        counts[label] = good
        print(f"\n  with {label}: {len(good)} guess(es) fit. Some of them:")
        for g in good[:: max(1, len(good) // 5)][:5]:
            print(f"     x = {g[0]:4.1f}  y = {g[1]:4.1f}  bias = {g[2]:.2f}")
    good = counts["only A and B"]
    picture("two", list(zip(BEACONS[:2], LATE[:2], NAMES)),
            [((g[0], g[1]), None, "b.") for g in good] + [(TRUTH, "true position", "k*")],
            "Only A and B, unknown clock: every blue dot fits\n(only y from 0 to 10 is searched)")


def spoof():
    need("distance", "mismatch")
    print(f"You are really at {TRUTH}. A spoofer wants you to believe you are at {FAKE}.")
    fake_m, err = call("spoof_measurements", BEACONS, FAKE, 0.3)
    if err:
        sys.exit(err)
    if not isinstance(fake_m, (list, tuple)) or len(fake_m) != 3:
        sys.exit(f"spoof_measurements() must return a LIST with one value per beacon (3 here), "
                 f"but it returned {fake_m!r}. See the hints of Step 8.")
    print("The spoofer sends:", ", ".join(f"{n} {km(d)}" for n, d in zip(NAMES, fake_m)))
    q, err = call("find_position_and_bias", BEACONS, fake_m)
    if err:
        sys.exit(err)
    if not isinstance(q, (list, tuple)) or len(q) != 3:
        sys.exit(f"find_position_and_bias() must return three numbers (x, y, bias), but it returned {q!r}.")
    m, _ = call("mismatch", q[:2], BEACONS, fake_m, q[2])
    print(f"\nYour receiver computes: x = {q[0]}, y = {q[1]}, bias = {q[2]} km")
    print(f"mismatch there: {m:.4f}      distance from the TRUE position: {math.dist(q[:2], TRUTH) * 1000:.0f} m")
    picture("spoof", list(zip(BEACONS, fake_m, NAMES)),
            [(TRUTH, "where you really are", "o"), (q[:2], "what the receiver says", "r*")],
            "Spoofed: the circles meet perfectly… at the wrong place", bias=q[2])


def gate():
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            import answers
        except Exception as e:
            sys.exit(f"answers.py has an error, so it cannot be read: {type(e).__name__}: {e}\n"
                     'Text must be in quotes, for example ARCH = "aarch64".')
    try:
        v_max, margin = float(answers.V_MAX_MPS), float(answers.MARGIN_M)
    except Exception:
        v_max = margin = 0.0
    if v_max <= 0 or margin <= 0:
        sys.exit("First write V_MAX_MPS and MARGIN_M in answers.py (lab step 3).")
    print(f"NAVERA's settings from your answers.py: v_max = {v_max:g} m/s, margin = {margin:g} m. One fix per second.")
    attacks = {
        "A) a 300 m jump, then the fake position stays": [(0, 0)] + [(300, 0)] * 8,
        "B) a slow drag: 20 m further every second, for 60 s": [(20 * t, 0) for t in range(61)],
    }
    for title, fixes in attacks.items():
        print(f"\n{title}")
        n, err = call("count_refused", fixes, 1.0, v_max, margin)
        if err:
            sys.exit(err)
        line, last, elapsed = [], fixes[0], 0.0
        for f in fixes[1:11]:
            elapsed += 1.0
            ok, err = call("gate_ok", last, f, elapsed, v_max, margin)
            if err:
                sys.exit(err)
            line.append("✔" if ok else "✘")
            if ok:
                last, elapsed = f, 0.0
        print(f"   first {len(line)} fixes (gate_ok):  " + " ".join(line) + "      (✔ accepted, ✘ refused)")
        print(f"   count_refused  ->  {n} refused, final position {fixes[-1][0]} m from the start")


if __name__ == "__main__":
    steps = {"test": test, "clean": clean, "clock": clock, "two": two, "spoof": spoof, "gate": gate}
    if len(sys.argv) != 2 or sys.argv[1] not in steps:
        sys.exit(__doc__)
    steps[sys.argv[1]]()
