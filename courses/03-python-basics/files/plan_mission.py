"""plan_mission.py — runs YOUR NAVERA Lite parts (navera_lite/vehicle.py, navera_lite/track.py) on the lab's
situations, prints the results and draws pictures.

    python3 plan_mission.py test      check each function on its docstring example
    python3 plan_mission.py wind      the lighthouse inspection: wind, heading, ground speed   (Step 3)
    python3 plan_mission.py gonogo    the go/no-go decision for the quad                       (Step 4)
    python3 plan_mission.py fleet     the same mission for every vehicle of the fleet          (Step 7)
    python3 plan_mission.py track     the recorded harbour survey: length and speeds           (Step 9)
    python3 plan_mission.py glitch    the glitch hunt                                          (Step 10)
    python3 plan_mission.py speed     a Python loop against NumPy on 200 000 positions          (Step 11)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import inspect
import math
import os
import sys
import time

import runner_kit as rk

DATA = "/data/academy/03-python-basics/harbour_track.csv"

# The mission (synthetic numbers): inspect a lighthouse 7.5 km from the take-off site, on the
# ground track 030°, and come back. Forecast: wind FROM 020° at 6 m/s.
LEG_M = 7500.0
TRACK_OUT_DEG = 30.0
WIND_FROM_DEG = 20.0
WIND_MPS = 6.0
RESERVE = 0.2
# The quad, as plain numbers (session 1); session 2 builds it as an object.
QUAD_TAS_MPS, QUAD_BATTERY_WH, QUAD_POWER_W = 12.0, 160.0, 350.0

veh = rk.load_student("navera_lite.vehicle")


def attempt(label, fn, *args, **kwargs):
    """Run one of your functions or methods: (result, None) or (None, one plain sentence)."""
    name = getattr(fn, "__name__", label)
    try:
        r = fn(*args, **kwargs)
    except NotImplementedError as e:
        return None, f"{label}: your {e} is not written yet — write it in navera_lite/, save, and run again"
    except Exception as e:
        tb = [f for f in inspect.trace() if "navera_lite" in f.filename]
        where = f" ({os.path.relpath(tb[-1].filename)} line {tb[-1].lineno})" if tb else ""
        return None, f"{label} stopped with {type(e).__name__}: {e}{where}{rk._hint(e)}"
    if r is None and name not in ("add", "__init__"):
        if rk.is_stub(fn):
            return None, f"{label}: not written yet — write its TODO and `return` the result"
        return None, f"{label} returned None: every path must end with a `return`"
    return r, None


def need(label, fn, *args, **kwargs):
    r, err = attempt(label, fn, *args, **kwargs)
    if err:
        sys.exit(err)
    return r


def wind_vector():
    """The forecast wind as (east, north) m/s: FROM 020° means the air goes TOWARDS 200°."""
    e, n = need("heading_vector()", veh.heading_vector, (WIND_FROM_DEG + 180.0) % 360.0)
    return WIND_MPS * e, WIND_MPS * n


def legs(tas_mps):
    """heading and ground speed out and back, with your heading_for_track()."""
    we, wn = wind_vector()
    back = (TRACK_OUT_DEG + 180.0) % 360.0
    out = need(f"heading_for_track({TRACK_OUT_DEG:g}, {tas_mps:g}, …)", veh.heading_for_track,
               TRACK_OUT_DEG, tas_mps, we, wn)
    ret = need(f"heading_for_track({back:g}, {tas_mps:g}, …)", veh.heading_for_track, back, tas_mps, we, wn)
    for r, what in ((out, "out"), (ret, "back")):
        if not (isinstance(r, tuple) and len(r) == 2):
            sys.exit(f"heading_for_track() must return a tuple (heading_deg, gs_mps), got {r!r} ({what})")
    return out, ret


# ---------------------------------------------------------------- test
def test():
    T = None
    try:
        tr_mod = rk.load_student("navera_lite.track")
        T = tr_mod.Track
    except SystemExit:
        pass

    class GoodRefused(Exception):
        pass

    def third_add():
        tr = T()
        try:
            tr.add(0, 0, 0)
            tr.add(1, 3, 4)
        except ValueError as e:
            raise GoodRefused(str(e))
        tr.add(1, 6, 8)

    def track_of(points):
        tr = T()
        for p in points:
            tr.add(*p)
        return tr

    cases = [
        ("heading_vector(90)", lambda: veh.heading_vector(90), (1.0, 0.0), 1e-9, veh.heading_vector),
        ("heading_vector(225)", lambda: veh.heading_vector(225), (-0.70711, -0.70711), 1e-4, veh.heading_vector),
        ("ground_velocity(10.0, 90.0, 0.0, 3.0)", lambda: veh.ground_velocity(10.0, 90.0, 0.0, 3.0), (10.0, 3.0),
         1e-9, veh.ground_velocity),
        ("wind_components(0.0, 2.0, -5.0)", lambda: veh.wind_components(0.0, 2.0, -5.0), (-5.0, 2.0), 1e-9,
         veh.wind_components),
        ("heading_for_track(0.0, 10.0, 6.0, 0.0)", lambda: veh.heading_for_track(0.0, 10.0, 6.0, 0.0),
         (323.13, 8.0), 0.01, veh.heading_for_track),
        ("heading_for_track(0.0, 10.0, 11.0, 0.0)  (too windy)", lambda: veh.heading_for_track(0.0, 10.0, 11.0, 0.0),
         "ValueError", 0, veh.heading_for_track),
        ("heading_for_track(0.0, 10.0, -11.0, 0.0)  (too windy, pushing LEFT)",
         lambda: veh.heading_for_track(0.0, 10.0, -11.0, 0.0), "ValueError", 0, veh.heading_for_track),
        ("heading_for_track(0.0, 10.0, 0.0, -10.0)  (headwind = airspeed)",
         lambda: veh.heading_for_track(0.0, 10.0, 0.0, -10.0), "ValueError", 0, veh.heading_for_track),
        ("endurance_s(50.0, 200.0, 0.1)", lambda: veh.endurance_s(50.0, 200.0, 0.1), 810.0, 1e-6, veh.endurance_s),
        ("endurance_s(50.0, 0.0)  (bad input)", lambda: veh.endurance_s(50.0, 0.0), "ValueError", 0, veh.endurance_s),
        ('Vehicle("rover", 2.0, 3.0, 400.0, 100.0).max_speed_mps',
         lambda: veh.Vehicle("rover", 2.0, 3.0, 400.0, 100.0).max_speed_mps, 3.0, 0, veh.Vehicle.__init__),
        ('Vehicle("rover", 2.0, 3.0, 400.0, 100.0).endurance_s()',
         lambda: veh.Vehicle("rover", 2.0, 3.0, 400.0, 100.0).endurance_s(), 11520.0, 1e-6, veh.Vehicle.endurance_s),
        ('Vehicle("rover", 2.0, 3.0, 400.0, 100.0).range_m(-0.5)',
         lambda: veh.Vehicle("rover", 2.0, 3.0, 400.0, 100.0).range_m(-0.5), 17280.0, 1e-6, veh.Vehicle.range_m),
        ('FixedWing("glider", 15.0, 25.0, 60.0, 80.0, 9.0).endurance_s()',
         lambda: veh.FixedWing("glider", 15.0, 25.0, 60.0, 80.0, 9.0).endurance_s(), 2160.0, 1e-6,
         veh.FixedWing.__init__),
    ]
    if T is not None:
        cases += [
            ("Track: add (0,0,0), (1,3,4) → len", lambda: len(track_of([(0, 0, 0), (1, 3, 4)])), 2, 0, T.add),
            ("Track: add(1, 6, 8) after time 1", third_add, "ValueError", 0, T.add),
            ("Track (0,0), (6,8), (6,20): length_m()",
             lambda: track_of([(0, 0, 0), (2, 6, 8), (3, 6, 20)]).length_m(), 22.0, 1e-9, T.length_m),
            ("Track … at 0, 2, 3 s: speeds_mps()",
             lambda: list(track_of([(0, 0, 0), (2, 6, 8), (3, 6, 20)]).speeds_mps()), [5.0, 12.0], 1e-9, T.speeds_mps),
            ("Track (0,0),(10,0),(20,0),(95,0): glitches(50)",
             lambda: track_of([(0, 0, 0), (1, 10, 0), (2, 20, 0), (3, 95, 0)]).glitches(50), [3], 0, T.glitches),
        ]
    done = 0
    for label, f, want, tol, src in cases:
        try:
            got = f()
        except NotImplementedError as e:
            print(f"·  {label}: not written yet ({e})")
            continue
        except Exception as e:
            if type(e).__name__ == "GoodRefused":
                print(f"✘ {label}  ->  your add() refused a GOOD position ({e}): test, then append (Step 8 hint 2)")
            elif want == "ValueError" and isinstance(e, ValueError) and "math domain" in str(e):
                print(f"✘ {label}  ->  ValueError: {e}   (math.asin refused, not YOUR code: check "
                      "abs(cross) > tas_mps yourself, before math.asin, and raise your own ValueError)")
            elif want == "ValueError" and isinstance(e, ValueError):
                print(f"✔ {label}  ->  ValueError: {e}")
                done += 1
            else:
                tb = [fr for fr in inspect.trace() if "navera_lite" in fr.filename]
                where = f" ({os.path.relpath(tb[-1].filename)} line {tb[-1].lineno})" if tb else ""
                print(f"✘ {label}  ->  {type(e).__name__}: {e}{where}{rk._hint(e)}")
            continue
        if got is None and rk.is_stub(src):
            print(f"·  {label}: not written yet")
            continue
        if want == "ValueError":
            print(f"✘ {label}  ->  {got!r}   (expected: raise ValueError)")
            continue
        if isinstance(want, (tuple, list)):
            ok = (isinstance(got, (tuple, list)) and len(got) == len(want)
                  and all(isinstance(g, (int, float)) and abs(g - w) <= tol for g, w in zip(got, want)))
            if ok and isinstance(want, list) and isinstance(got, list) and tol == 0:
                ok = all(type(g) is int for g in got)
        else:
            ok = isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want) <= tol
        shown = tuple(round(g, 4) for g in got) if isinstance(got, tuple) and all(
            isinstance(g, float) for g in got) else got
        extra = "  (a NumPy array: end with .tolist())" if not ok and hasattr(got, "tolist") and isinstance(want, list) else ""
        print(f"{'✔' if ok else '✘'} {label}  ->  {shown!r}" + ("" if ok else f"   (expected {want!r}){extra}"))
        done += ok
    print(f"\n{done} of {len(cases)} examples give the expected result."
          + ("" if T is not None else "  (navera_lite/track.py could not be loaded: see the message above)"))


# ---------------------------------------------------------------- session 1
def wind():
    we, wn = wind_vector()
    print(f"Forecast: wind FROM {WIND_FROM_DEG:03.0f}° at {WIND_MPS:g} m/s  →  the air goes TOWARDS "
          f"{(WIND_FROM_DEG + 180) % 360:03.0f}°")
    print(f"wind vector (your heading_vector)       wind_e = {we:+.3f} m/s   wind_n = {wn:+.3f} m/s\n")
    print(f"Quad, true airspeed {QUAD_TAS_MPS:g} m/s, leg {LEG_M / 1000:g} km each way\n")
    print(f"{'leg':<6}{'track':>7}{'along':>10}{'cross':>10}")
    out, ret = legs(QUAD_TAS_MPS)
    for trk, name in ((TRACK_OUT_DEG, "out"), ((TRACK_OUT_DEG + 180) % 360, "back")):
        comp = need("wind_components()", veh.wind_components, trk, we, wn)
        print(f"{name:<6}{trk:>6.0f}°{comp[0]:>+9.2f} {comp[1]:>+9.2f}")
    print("\n(along > 0: tailwind; cross > 0: the wind pushes to the RIGHT of the track)")
    print("Heading and ground speed: compute them yourself with heading_for_track (lab Step 3);")
    print("the picture shows whether your heading lands on the track.")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    h, gs = out
    ae, an = need("ground_velocity()", veh.ground_velocity, QUAD_TAS_MPS, h)
    ge, gn = need("ground_velocity()", veh.ground_velocity, QUAD_TAS_MPS, h, we, wn)
    kw = dict(angles="xy", scale_units="xy", scale=1, width=0.012)
    ax.quiver(0, 0, ae, an, color="#1f6fb2", label="air velocity (your heading, airspeed)", **kw)
    ax.quiver(ae, an, we, wn, color="#d17a00", label=f"wind ({we:+.2f}, {wn:+.2f}) m/s", **kw)
    ax.quiver(0, 0, ge, gn, color="#2e8b57", label="ground velocity", **kw)
    te, tn = veh.heading_vector(TRACK_OUT_DEG)
    ax.plot([0, 14 * te], [0, 14 * tn], "k--", lw=1, label=f"wanted track {TRACK_OUT_DEG:03.0f}°")
    ax.set_xlim(-4, 10); ax.set_ylim(-2, 14); ax.set_aspect("equal"); ax.grid(alpha=.3)
    ax.set_xlabel("east (m/s)"); ax.set_ylabel("north (m/s)"); ax.set_title("Outbound leg: the wind triangle")
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig("out/wind.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    rk.saved("out/wind.png")


def gonogo():
    (h1, gs1), (h2, gs2) = legs(QUAD_TAS_MPS)
    t_out, t_back = LEG_M / gs1, LEG_M / gs2
    still = 2 * LEG_M / QUAD_TAS_MPS
    endu = need("endurance_s()", veh.endurance_s, QUAD_BATTERY_WH, QUAD_POWER_W, RESERVE)
    print(f"Quad: {QUAD_TAS_MPS:g} m/s, {QUAD_BATTERY_WH:g} Wh, {QUAD_POWER_W:g} W, reserve {RESERVE:.0%}\n")
    print(f"  still air, out and back          {still:7.0f} s = {still / 60:6.2f} min")
    print(f"  with the wind: out               {t_out:7.0f} s = {t_out / 60:6.2f} min")
    print(f"                 back              {t_back:7.0f} s = {t_back / 60:6.2f} min")
    print(f"  endurance (your endurance_s)     {endu:7.0f} s = {endu / 60:6.2f} min\n")
    print("Round trip and decision: yours to work out (lab Step 4).")


# ---------------------------------------------------------------- session 2
def fleet():
    quad = need("Multirotor(...)", veh.Multirotor, "quad", 12.0, 20.0, 160.0, 350.0)
    wing = need("FixedWing(...)", veh.FixedWing, "wing", 20.0, 35.0, 150.0, 220.0, 12.0)
    we, wn = wind_vector()
    print(f"Mission: {LEG_M / 1000:g} km out on {TRACK_OUT_DEG:03.0f}° and back, wind from {WIND_FROM_DEG:03.0f}° at "
          f"{WIND_MPS:g} m/s\n")
    print(f"{'vehicle':<34}{'endurance':>11}{'range, still':>14}{'range, 6 m/s head':>19}")
    for v in (quad, wing):
        if not hasattr(v, "cruise_mps"):
            sys.exit(f"{v.__class__.__name__} has no attribute cruise_mps — did its __init__ store it, or call super().__init__(...)?")
        endu = need(f"{v.name}.endurance_s()", v.endurance_s)
        r0 = need(f"{v.name}.range_m()", v.range_m)
        r1 = need(f"{v.name}.range_m(-6.0)", v.range_m, -6.0)
        print(f"{v!r:<34}{endu / 60:>8.2f} min{r0 / 1000:>11.2f} km{r1 / 1000:>16.2f} km")
    print("\n(the round trips and the decisions: yours to compute, lab Step 7)")
    print(f"\nisinstance(wing, Vehicle) = {isinstance(wing, veh.Vehicle)};  "
          f"wing turn radius at 30° bank = {wing.turn_radius_m():.1f} m")
    print(f"quad hover time at 420 W = {quad.hover_s(420.0) / 60:.1f} min  (cruise at 12 m/s draws only 350 W)")


def load():
    if not os.path.exists(DATA):
        sys.exit(f"{DATA} is missing: the lesson's dataset is not mounted — tell your teacher.")
    trm = rk.load_student("navera_lite.track")
    tr, err = attempt("load_track()", trm.load_track, DATA, "harbour")
    if err:
        sys.exit(err + "  (load_track() is finished: it calls your Track.add)")
    return trm, tr


def track():
    import numpy as np
    _, tr = load()
    s = need("speeds_mps()", tr.speeds_mps)
    L = need("length_m()", tr.length_m)
    if not isinstance(s, np.ndarray):
        sys.exit(f"speeds_mps() must return a NumPy array, got a {type(s).__name__}")
    print("harbour survey, one position per second")
    print(f"  length                 {L:9.1f} m")
    print(f"  speeds                 {len(s)} values")
    print(f"  median speed           {np.median(s):9.2f} m/s")
    print(f"  mean speed             {np.mean(s):9.2f} m/s")
    print("  (the number of positions and the maximum speed: find them yourself, lab Step 9)")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    t, e, n = tr.arrays()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6))
    a1.plot(e, n, ".-", ms=3, lw=0.8); a1.plot(0, 0, "ks", label="take-off")
    a1.set_aspect("equal"); a1.grid(alpha=.3); a1.set_xlabel("east (m)"); a1.set_ylabel("north (m)")
    a1.set_title("Harbour survey track"); a1.legend(fontsize=8)
    a2.plot(t[1:], s, lw=0.9); a2.set_xlabel("time of the position reached (s)"); a2.set_ylabel("speed (m/s)")
    a2.grid(alpha=.3); a2.set_title("Segment speeds")
    fig.savefig("out/track.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    rk.saved("out/track.png")


def glitch():
    import numpy as np
    _, tr = load()
    quad = need("Multirotor(...)", veh.Multirotor, "quad", 12.0, 20.0, 160.0, 350.0)
    limit = quad.max_speed_mps
    g = need(f"glitches({limit:g})", tr.glitches, limit)
    if not isinstance(g, list) or not all(type(i) is int for i in g):
        sys.exit(f"glitches() must return a list of Python ints, got {g!r}"
                 + ("  (a NumPy array? use .tolist())" if hasattr(g, "tolist") else ""))
    t, e, n = tr.arrays()
    print(f"threshold = the quad's max speed = {limit:g} m/s")
    print(f"glitches({limit:g}) = {g}")
    for i in g:
        print(f"  position {i}: t = {t[i]:.0f} s, e = {e[i]:8.2f} m, n = {n[i]:8.2f} m, "
              f"reached at {tr.speeds_mps()[i - 1]:.1f} m/s")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    lo, hi = (max(0, min(g) - 6), min(len(t), max(g) + 7)) if g else (140, 160)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(e[lo:hi], n[lo:hi], "o-", ms=4, lw=0.8, label="positions")
    for i in range(lo, hi):
        ax.annotate(f"{t[i]:.0f}", (e[i], n[i]), xytext=(5, 0), textcoords="offset points", fontsize=7)
    if g:
        ax.plot(e[g], n[g], "o", ms=12, mfc="none", mec="r", mew=2, label="listed by glitches()")
    ax.set_aspect("equal"); ax.grid(alpha=.3); ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
    ax.set_title("Zoom on the glitch (labels: time in s)"); ax.legend(fontsize=8)
    fig.savefig("out/glitch.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    rk.saved("out/glitch.png")


def speed():
    import numpy as np
    trm = rk.load_student("navera_lite.track")
    rng = np.random.default_rng(3)
    N = 200_000
    tr = trm.Track("big")
    e = np.cumsum(rng.normal(0, 12, N)); n = np.cumsum(rng.normal(0, 12, N))
    for i in range(N):
        try:
            tr.add(float(i), e[i], n[i])
        except Exception as ex:
            sys.exit(f"Track.add stopped with {type(ex).__name__}: {ex}")
    def python_loop():
        out = []
        for i in range(N - 1):                  # the plain Python way, one segment at a time
            d = math.hypot(tr.e_m[i + 1] - tr.e_m[i], tr.n_m[i + 1] - tr.n_m[i])
            out.append(d / (tr.t_s[i + 1] - tr.t_s[i]))
        return out

    def best(f, repeat=5):                      # the fastest of 5 runs: less noise from a busy computer
        times = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            f()
            times.append(time.perf_counter() - t0)
        return min(times)

    loop = python_loop()
    s = need("speeds_mps()", tr.speeds_mps)
    t_loop = best(python_loop)
    t_np = best(tr.speeds_mps)
    t_conv = best(tr.arrays)                    # the list → array conversion alone
    same = len(s) == len(loop) and np.allclose(s, loop)
    print(f"{N} positions, same results: {same}   (each time: the best of 5 runs)")
    print(f"  Python loop                     {t_loop * 1000:8.1f} ms")
    print(f"  your speeds_mps()               {t_np * 1000:8.1f} ms")
    print(f"     of which lists → arrays      {t_conv * 1000:8.1f} ms   (arrays())")
    print(f"     of which the NumPy maths     {max(t_np - t_conv, 1e-6) * 1000:8.1f} ms")
    print(f"  speeds_mps() is about {t_loop / t_np:.0f} times faster than the loop; "
          f"the maths alone about {t_loop / max(t_np - t_conv, 1e-6):.0f} times")


MODES = {"test": test, "wind": wind, "gonogo": gonogo, "fleet": fleet, "track": track, "glitch": glitch,
         "speed": speed}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(__doc__)
        sys.exit(1)
    MODES[sys.argv[1]]()
