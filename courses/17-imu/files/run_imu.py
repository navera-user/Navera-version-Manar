"""run_imu.py — runs YOUR functions of navera_lite/imu.py on a simulated flight, and draws the results.

    python3 run_imu.py test              check each function on its docstring example (and a few traps)
    python3 run_imu.py look              the log: what the three sensors say                          (Step 1)
    python3 run_imu.py gyro [BX BY BZ]   the gyroscope alone; optionally subtract a bias (°/s) first   (Step 2)
    python3 run_imu.py tilt              tilt from gravity vs the truth, in turns and speed changes    (Step 3)
    python3 run_imu.py tau [ROLL]        the complementary filter for seven τ (optional wrong start, °) (Step 4)
    python3 run_imu.py compass [TAU]     compass, declination and the chip's own attitude              (Steps 5–6)
    python3 run_imu.py stale [N]         a frozen IMU: when does StaleDetector(max_repeat=N) trip?     (Step 7)

Data: /data/academy/17-imu/ (read only). Pictures are saved in out/ — click them in the 📝 Code tab.
"""
import json
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = os.environ.get("IMU_DATA", "/data/academy/17-imu")
imu = rk.load_student("navera_lite.imu")
rot = rk.load_student("navera_lite.rotations")
TAUS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)


def wrap(e):
    """Angle differences into [−180, 180) degrees."""
    return (np.asarray(e, dtype=float) + 180.0) % 360.0 - 180.0


def load(name="imu_log.csv"):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: the course data is not mounted here (tell your teacher)")
    L = np.genfromtxt(path, delimiter=",", names=True)
    return L


def columns(L, *names):
    return np.stack([L[n] for n in names], axis=1)


def meta():
    with open(os.path.join(DATA, "imu_log_meta.json")) as f:
        return json.load(f)


def start_attitude(L):
    """The true attitude at t = 0 (the drone on its pad, heading known from the pad's markings)."""
    return rot.q_from_euler_zyx(math.radians(L["true_roll_deg"][0]), -math.radians(L["true_pitch_up_deg"][0]),
                                math.radians(90.0 - L["true_heading_deg"][0]))


def quats(v, n, fn):
    """The student's N × 4 result as an array, or stop with one plain sentence."""
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return an N × 4 numpy array of quaternions, but it returned {type(v).__name__}")
    if a.shape != (n, 4):
        sys.exit(f"{fn}() must return one quaternion per sample, an array of shape ({n}, 4); yours has shape {a.shape}")
    if not np.all(np.isfinite(a)):
        bad = int(np.argmax(~np.all(np.isfinite(a), axis=1)))
        sys.exit(f"{fn}() returned nan/inf from row {bad} on — a division by a zero length? (row 0 is q0)")
    return a


def human(Q):
    """(roll, pitch_up, heading) in degrees for every row, with the given rpy_human."""
    return np.array([rot.rpy_human(q) for q in Q])


def plt_ready():
    plt = rk.plt_or_none()
    if plt is not None:
        os.makedirs("out", exist_ok=True)
    return plt


# ------------------------------------------------------------------------------------------- test
def attempt(fn, name):
    """Run fn() (a call of the student's function name); (result, None) or (None, one plain sentence)."""
    import contextlib
    import io
    import traceback
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            v = fn()
    except NotImplementedError:
        return None, "it is not written yet"
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith(os.path.join("navera_lite", "imu.py"))]
        where = f" (navera_lite/imu.py line {tb[-1].lineno}, in {tb[-1].name}())" if tb else ""
        hint = rk._hint(e)
        s = str(e)
        if "rotation axis must not be zero" in s:
            hint = (" — a rate of (0, 0, 0) has no axis: q_from_axis_angle refuses it. When the turn angle is 0, "
                    "skip the turn (the attitude does not change)")
        elif "only length-1 arrays" in s or "only size-1 arrays" in s:
            hint = " — math.atan2/math.hypot take single numbers: use np.arctan2 and np.hypot so arrays work too"
        elif "truth value of an array" in s:
            hint = " — comparing two numpy arrays with == gives an array: turn the sample into a tuple first"
        return None, f"{name}() stopped with {type(e).__name__}: {e}{where}{hint}"
    if v is None:
        return None, f"{name}() returned None: every path must end with a `return`"
    return v, None


def test():
    D = math.radians
    cases = []          # (TODO, label, call, check(result) -> (ok, note))

    def rows_chk(want, extra=None):
        def chk(v):
            a = np.asarray(v, dtype=float) if v is not None else None
            if a is None or a.shape != np.shape(want):
                return False, f"expected an array of shape {np.shape(want)}, got {np.shape(v) if hasattr(v, 'shape') else v!r}"
            if extra:
                msg = extra(a)
                if msg:
                    return False, msg
            ok = all(np.abs(a[i] - want[i]).max() < 2e-4 or np.abs(a[i] + want[i]).max() < 2e-4 for i in range(len(a)))
            return ok, None
        return chk

    def yaw_after(want_rad, msgs):
        def chk(v):
            a = np.asarray(v, dtype=float)
            if a.ndim != 2 or a.shape[1] != 4:
                return False, f"expected an N × 4 array, got shape {a.shape}"
            yaw = 2 * math.atan2(a[-1][2], a[-1][3])
            for bad, m in msgs:
                if abs(yaw - bad) < 1e-6:
                    return False, m
            return abs(yaw - want_rad) < 1e-6, f"the last yaw is {yaw:.4f} rad, expected {want_rad:.4f} rad"
        return chk

    def body_chk(v):
        a = np.asarray(v, dtype=float)
        if a.ndim != 2 or a.shape != (3, 4):
            return False, f"expected a 3 × 4 array, got shape {a.shape}"
        r, p, h = rot.rpy_human(a[-1])
        if abs(p - 28.65) < 0.1 and abs(r) < 0.1:
            return False, ("the turn was applied about the WORLD axes (the nose went up): the gyro measures in the "
                           "BODY frame, so the small turn multiplies on the RIGHT, q ⊗ Δq (lesson §2)")
        return abs(r - 28.65) < 0.05 and abs(p) < 0.05 and abs(h) < 0.05, \
            f"expected roll 28.65°, pitch_up 0°, heading 0° (a roll about the nose); got {r:.2f}°, {p:.2f}°, {h:.2f}°"

    def tilt_chk(want_deg):
        def chk(v):
            if not (isinstance(v, (tuple, list)) and len(v) == 2):
                return False, f"expected two values (roll_rad, pitch_rad), got {v!r}"
            try:
                rr, pp = (np.degrees(np.asarray(x, dtype=float)) for x in v)
            except (TypeError, ValueError):
                return False, f"expected two numbers or two arrays, got {v!r}"
            rr, pp = np.atleast_1d(rr), np.atleast_1d(pp)
            w = np.atleast_2d(want_deg)
            if np.allclose(rr, w[:, 0], atol=0.02) and np.allclose(pp, -w[:, 1], atol=0.02) and np.any(np.abs(w[:, 1]) > 1):
                return False, "the pitch has the wrong sign: ROS pitch is positive NOSE DOWN, pitch = atan2(−ax, …)"
            if np.any(np.abs(pp - 36.05) < 0.05) and np.any(np.abs(w[:, 1] - 20.0) < 0.01):
                return False, "with a 60° roll the pitch is wrong: the denominator is np.hypot(ay, az), not az alone"
            if np.any(np.abs(w) > 1) and np.allclose(np.radians(rr), w[:, 0], atol=0.02) \
                    and np.allclose(np.abs(np.radians(pp)), np.abs(w[:, 1]), atol=0.02):
                return False, "these are degrees: the function returns RADIANS (np.arctan2 already gives radians)"
            return np.allclose(rr, w[:, 0], atol=0.02) and np.allclose(pp, w[:, 1], atol=0.02), \
                f"got roll {np.round(rr, 2).tolist()}°, pitch {np.round(pp, 2).tolist()}° (ROS sign)"
        return chk

    def comp_chk(want_roll, want_heading):
        def chk(v):
            a = np.asarray(v, dtype=float)
            if a.ndim != 2 or a.shape[1] != 4:
                return False, f"expected an N × 4 array, got shape {a.shape}"
            r = [rot.rpy_human(q) for q in a]
            rolls = [x[0] for x in r]
            if all(abs(x - y) < 0.05 for x, y in zip(rolls, (0.0, 22.5, 28.12))) and want_roll[1] < 10:
                return False, "α and 1 − α are swapped: the GYRO side gets α = τ / (τ + dt), gravity gets 1 − α"
            if rolls[-1] < -0.5:
                return False, "the roll went the WRONG way: the nudge must turn 'seen up' TOWARDS (0, 0, 1) — axis = seen_up × up"
            heads = [x[2] for x in r]
            if abs(wrap(heads[-1] - want_heading)) > 0.05:
                return False, (f"the heading moved ({heads[-1]:.2f}° instead of {want_heading:.2f}°): gravity's nudge is "
                               "about a horizontal WORLD axis, so it multiplies on the LEFT (lesson §4)")
            if len(rolls) > 1 and abs(rolls[1] - 7.16) < 0.05 and abs(want_roll[1] - 7.5) < 0.01:
                return False, ("the first step moved 7.16°, not 7.5°: |seen_up × up| is sin(error); the angle is "
                               "math.atan2(s, seen_up[2])")
            ok = all(abs(x - y) < 0.05 for x, y in zip(rolls, want_roll))
            return ok, f"the roll goes {[round(x, 2) for x in rolls]}°, expected {list(want_roll)}°"
        return chk

    def deg_chk(want, tol=0.01, msgs=()):
        def chk(v):
            try:
                x = float(v)
            except (TypeError, ValueError):
                return False, f"expected one number (degrees), got {v!r}"
            for bad, m in msgs:
                if abs(x - bad) < tol:
                    return False, m
            if not 0.0 <= x < 360.0:
                return False, f"{x:.2f} is outside [0, 360): use % 360.0"
            return abs(x - want) < tol, None
        return chk

    def q_chk(want, msgs=()):
        def chk(v):
            try:
                a = np.asarray(v, dtype=float).reshape(4)
            except (TypeError, ValueError):
                return False, f"expected 4 numbers (x, y, z, w), got {v!r}"
            for bad, m in msgs:
                if np.abs(a - bad).max() < 2e-4 or np.abs(a + bad).max() < 2e-4:
                    return False, m
            return np.abs(a - want).max() < 2e-4 or np.abs(a + want).max() < 2e-4, None
        return chk

    def stale_run(seq, n):
        def go():
            d = imu.StaleDetector(max_repeat=n)
            return [d.update(s) for s in seq]
        return go

    def list_chk(want, msgs=()):
        def chk(v):
            got = [bool(x) if isinstance(x, (bool, np.bool_)) else x for x in v]
            if any(x is None for x in got):
                return False, "update() returned None for some samples: return True or False every time"
            for bad, m in msgs:
                if got == bad:
                    return False, m
            return got == want, (f"expected {want}: trace it by hand — after each sample write self.last and "
                                 "self.repeats (two bugs at once give lists no single message names)")
        return chk

    def zero_case(acc):
        def go():
            try:
                v = imu.complementary((0, 0, 0, 1), [0.0, 0.02, 0.04], [[0, 0, 0]] * 3, acc, 1.0)
            except Exception as e:                       # noqa: BLE001 — turned into one sentence below
                return f"crash: {type(e).__name__}: {e}"
            return v
        return go

    def zero_chk(msg):
        def chk(v):
            if isinstance(v, str):
                return False, f"{v} — {msg}"
            a = np.asarray(v, dtype=float)
            if a.shape != (3, 4) or not np.all(np.isfinite(a)):
                return False, f"got nan/inf or a wrong shape — {msg}"
            return bool(np.all(np.abs(np.abs(a[:, 3]) - 1.0) < 1e-9)), f"the attitude must stay level — {msg}"
        return chk

    a1 = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    q_bank = rot.q_from_euler_zyx(D(30), 0.0, 0.0)                  # 30° right wing down, nose east (heading 90° mag)
    cases += [
        (1, "integrate_gyro: 0.6 rad/s about up for 1 s (docstring)",
         lambda: imu.integrate_gyro((0, 0, 0, 1), [0.0, 0.5, 1.0], [[0, 0, 0.6]] * 3),
         rows_chk([[0, 0, 0, 1], [0, 0, 0.149438, 0.988771], [0, 0, 0.295520, 0.955336]])),
        (1, "integrate_gyro: heading north, then 0.5 rad/s about the NOSE for 1 s",
         lambda: imu.integrate_gyro((0, 0, 0.7071068, 0.7071068), [0.0, 0.5, 1.0], [[0.5, 0, 0]] * 3), body_chk),
        (1, "integrate_gyro: uneven times, changing rates, then no rate at all",
         lambda: imu.integrate_gyro((0, 0, 0, 1), [0.0, 0.5, 2.0, 2.5], [[0, 0, 0.2], [0, 0, 0.4], [0, 0, 0], [0, 0, 0]]),
         yaw_after(0.7, ((0.2, "you used the rate of sample k for the step k−1 → k: use the rate of sample k−1 (the "
                                "rate measured at the START of the step)"),
                         (0.3, "dt is not the same for every step here: use t_s[k] − t_s[k−1] at each step")))),
        (2, "tilt_from_accel(0, 0, 9.81) — level", lambda: imu.tilt_from_accel(0.0, 0.0, 9.81), tilt_chk([[0.0, 0.0]])),
        (2, "tilt_from_accel(−1.6, 0, 9.68) — nose down", lambda: imu.tilt_from_accel(-1.6, 0.0, 9.68),
         tilt_chk([[0.0, 9.3855]])),
        (2, "tilt_from_accel on arrays — roll 60° and ROS pitch 20°, then level",
         lambda: imu.tilt_from_accel(np.array([-3.3552, 0.0]), np.array([7.9836, 0.0]), np.array([4.6094, 9.81])),
         tilt_chk([[60.0, 20.0], [0.0, 0.0]])),
        (3, "complementary: no turn, gravity says 30° right wing down, τ = 1.5 s (docstring)",
         lambda: imu.complementary((0, 0, 0, 1), [0.0, 0.5, 1.0], a1, [[0, 4.905, 8.496]] * 3, 1.5),
         comp_chk((0.0, 7.5, 13.12), 90.0)),
        (3, "complementary: heading 30°, same tilt — the heading must not move",
         lambda: imu.complementary(rot.q_from_euler_zyx(0.0, 0.0, D(60)), [0.0, 0.5, 1.0], a1, [[0, 4.905, 8.496]] * 3, 1.5),
         comp_chk((0.0, 7.5, 13.12), 30.0)),
        (3, "complementary: level, gravity exactly (0, 0, 9.81) — nothing to correct",
         zero_case([[0.0, 0.0, 9.81]] * 3),
         zero_chk("seen_up is exactly up: the axis is zero, nothing to correct — skip the gravity step when the "
                  "axis length is (almost) 0 (hint 3)")),
        (3, "complementary: a free-fall sample f = (0, 0, 0)",
         zero_case([[0.0, 0.0, 9.81], [0.0, 0.0, 0.0], [0.0, 0.0, 9.81]]),
         zero_chk("f = (0, 0, 0) has no direction (free fall): skip the gravity step when |f| is 0 (hint 2)")),
        (4, "mag_heading level, magnetic north on the left (docstring)", lambda: imu.mag_heading((0.0, 28.2, -34.3), 0.0, 0.0),
         deg_chk(90.0, msgs=((270.0, "270° is the mirror image: in FLU (y = LEFT) the heading is atan2(y, x) of the level "
                                     "field; tutorials written for y = RIGHT use atan2(−y, x)"),
                             (0.0, "0°: x and y are swapped in atan2 — it is atan2(y, x) of the level field")))),
        (4, "mag_heading tilted: roll 20°, ROS pitch −10° (docstring)",
         lambda: imu.mag_heading((13.68, 6.0, -41.82), D(20), D(-10)),
         deg_chk(45.0, tol=0.05, msgs=((23.68, "23.7° = no tilt compensation: turn the field with rot_y(pitch) @ rot_x(roll) first"),
                                       (42.37, "42.4°: the two turns are in the wrong order — the roll is undone FIRST, so "
                                               "rot_x(roll) stands next to the vector: rot_y(pitch) @ rot_x(roll) @ m")))),
        (4, "mag_heading level, heading 300° (atan2 gives −60°)", lambda: imu.mag_heading((14.125, -24.465, -34.3), 0.0, 0.0),
         deg_chk(300.0, tol=0.02)),
        (5, "true_heading(350, +12.8)", lambda: imu.true_heading(350.0, 12.8),
         deg_chk(2.8, msgs=((337.2, "you subtracted the declination: true = magnetic + D (D positive east)"),))),
        (5, "true_heading(10, −26.8)", lambda: imu.true_heading(10.0, -26.8), deg_chk(343.2)),
        (6, "q_true_north(level, nose to magnetic east, D = +10°) (docstring)", lambda: imu.q_true_north((0, 0, 0, 1), 10.0),
         q_chk(np.array([0, 0, -0.087156, 0.996195]),
               ((np.array([0, 0, 0.087156, 0.996195]), "the turn has the wrong sign: true = magnetic + D, so the yaw DEcreases by D"),
                (np.array([0, 0, 0.958924, 0.283662]), "the declination went into a sin/cos in degrees: convert with math.radians")))),
        (6, "q_true_north(banked 30°, D = +10°) — left or right?", lambda: imu.q_true_north(q_bank, 10.0),
         q_chk(rot.q_mul(rot.q_from_axis_angle((0, 0, 1), -D(10)), q_bank),
               ((rot.q_mul(q_bank, rot.q_from_axis_angle((0, 0, 1), -D(10))),
                 "you multiplied on the RIGHT (a turn about the BODY's up axis): the declination turns the WORLD frame, "
                 "q_turn ⊗ q_mag (lesson §5)"),))),
        (7, "StaleDetector(2) on the docstring's samples", stale_run([(1, 5), (1, 5), (1, 5), (1, 5), (1, 6), (1, 6)], 2),
         list_chk([False, False, True, True, False, False],
                  ((([False, False, False, True, False, False]), "one sample too late: the 2nd REPEAT (the 3rd equal "
                                                                   "sample) is already frozen"),
                   ([False, True, True, True, False, True], "one sample too early: the first sample is not a repeat"),
                   ([False, False, True, True, True, True], "it says True for (1, 6) after (1, 5): a DIFFERENT sample must "
                                                            "start the count again — compare the WHOLE sample (all its "
                                                            "numbers), and set the count back to 0 when it differs"),
                   ([False, False, False, True, True, True], "two bugs: one sample too late (use >=: the max_repeat-th "
                                                             "repeat is already frozen) AND the count does not start "
                                                             "again after (1, 6)")))),
        (7, "StaleDetector(2): A, A, A, B, A, A, A — the count starts again after B",
         stale_run([(1, 5), (1, 5), (1, 5), (2, 0), (1, 5), (1, 5), (1, 5)], 2),
         list_chk([False, False, True, False, False, False, True],
                  (([False, False, True, True, True, True, True], "the count did not start again after a different "
                                                                  "sample: set repeats back to 0"),))),
    ]
    names = {1: "integrate_gyro", 2: "tilt_from_accel", 3: "complementary", 4: "mag_heading", 5: "true_heading",
             6: "q_true_north", 7: "StaleDetector.update"}
    done, said = 0, set()
    for k, label, fn, chk in cases:
        name = names[k]
        func = getattr(imu.StaleDetector, "update", None) if k == 7 else getattr(imu, name, None)
        if func is None:
            print(f"✘ TODO {k}  {name}() does not exist in navera_lite/imu.py — did you rename it?")
            continue
        if rk.is_stub(func):
            if k not in said:
                print(f"· TODO {k}  {name}() is not written yet")
            said.add(k)
            continue
        got, err = attempt(fn, name.split(".")[-1])
        if err:
            print(f"✘ TODO {k}  {label}: {err}")
            continue
        try:
            ok, note = chk(got)
        except Exception as e:                                   # a strange return value
            ok, note = False, f"could not read the result {got!r} ({type(e).__name__})"
        shown = got
        if hasattr(got, "shape") and np.ndim(got) == 2:
            shown = np.asarray(got, dtype=float)[-1].round(4).tolist()
            shown = f"last row {shown}"
        elif isinstance(got, tuple) and len(got) == 2:
            shown = "(" + ", ".join(str((np.round(np.degrees(np.asarray(x, dtype=float)), 2) + 0.0).tolist())
                                    for x in got) + ") in degrees"
        elif isinstance(got, (float, int, np.floating)):
            shown = f"{float(got):.4f}"
        elif hasattr(got, "shape"):
            shown = np.asarray(got, dtype=float).round(4).tolist()
        print(f"{'✔' if ok else '✘'} TODO {k}  {label}  ->  {shown}" + ("" if ok else f"\n          ({note or 'not the docstring result'})"))
        done += bool(ok)
    print(f"\n{done} of {len(cases)} examples give the expected result.")


# ------------------------------------------------------------------------------------------- scenarios
def look():
    L, m = load(), meta()
    t = L["t_s"]
    print(f"The log: {len(t)} samples, {t[0]:.2f} → {t[-1]:.2f} s, {m['rate_hz']:.0f} per second — {m['place']}")
    print(f"  lat {m['lat']}, lon {m['lon']}, date {m['date']} (decimal year {m['decimal_year']}). {m['pad']}.\n")
    print("   t_s     gx        gy        gz      |   ax      ay      az    |   mx      my      mz")
    for i in (0, 1, 2, len(t) // 2):
        print(f"  {t[i]:6.2f} {L['gx'][i]:+.5f} {L['gy'][i]:+.5f} {L['gz'][i]:+.5f} | {L['ax'][i]:+6.2f} {L['ay'][i]:+6.2f} "
              f"{L['az'][i]:+6.2f} | {L['mx'][i]:+6.1f} {L['my'][i]:+6.1f} {L['mz'][i]:+6.1f}")
    print("\n  rad/s (body x, y, z)               m/s² (body)               µT (body)")
    plt = plt_ready()
    if plt is None:
        return
    fig, axs = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)
    for ax, (cols, unit, title) in zip(axs, ((("gx", "gy", "gz"), "°/s", "gyroscope (shown in °/s)"),
                                            (("ax", "ay", "az"), "m/s²", "accelerometer (specific force)"),
                                            (("mx", "my", "mz"), "µT", "magnetometer"))):
        for c, col in zip(cols, ("#d64545", "#2e9e4f", "#0b6e8a")):
            y = np.degrees(L[c]) if cols[0] == "gx" else L[c]
            ax.plot(t, y, lw=0.6, color=col, label=c)
        ax.axvspan(0, 10, color="#a8680d", alpha=0.12, lw=0)
        ax.set_ylabel(unit)
        ax.set_title(title, fontsize=9, loc="left")
        ax.legend(loc="upper right", fontsize=8, ncol=3)
        ax.grid(alpha=0.3)
    axs[0].text(5, axs[0].get_ylim()[1] * 0.8, "pad", ha="center", fontsize=8, color="#a8680d")
    axs[-1].set_xlabel("t (s)")
    fig.tight_layout()
    fig.savefig("out/look.png", dpi=90)
    rk.saved("out/look.png")


def gyro(args):
    L = load()
    t = L["t_s"]
    g = columns(L, "gx", "gy", "gz")
    title = "raw gyro, nothing subtracted"
    if args:
        try:
            b = [float(x) for x in args]
        except ValueError:
            sys.exit("give the bias as three numbers in °/s, e.g.  python3 run_imu.py gyro 0.1 -0.02 0.05")
        if len(b) != 3:
            sys.exit("give the bias as THREE numbers (x, y, z) in °/s")
        if max(abs(x) for x in b) > 5:
            sys.exit("these numbers are too large for a bias in °/s — did you give rad/s converted twice, or deg·s?")
        g = g - np.radians(b)
        title = f"bias ({b[0]:+.4f}, {b[1]:+.4f}, {b[2]:+.4f}) °/s subtracted"
    q0 = start_attitude(L)
    Q = quats(rk.need_ok(imu, "integrate_gyro", q0, t, g), len(t), "integrate_gyro")
    H = human(Q)
    e_h = wrap(H[:, 2] - L["true_heading_deg"])
    e_r = H[:, 0] - L["true_roll_deg"]
    e_p = H[:, 1] - L["true_pitch_up_deg"]
    print(f"The gyroscope alone, from the true attitude at t = 0 ({title}).")
    print("Errors = your integrated attitude − the truth (degrees; heading wrapped to ±180°):\n")
    print("   t (s)   heading error   roll error   pitch_up error")
    for ts in (10, 60, 150, 300):
        i = int(np.searchsorted(t, ts - 1e-9))
        print(f"   {t[i]:5.0f}     {e_h[i]:+8.2f}      {e_r[i]:+8.2f}      {e_p[i]:+8.2f}")
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(t, e_h, color="#0b6e8a", label="heading error")
    ax.plot(t, e_r, color="#d64545", lw=0.8, label="roll error")
    ax.plot(t, e_p, color="#2e9e4f", lw=0.8, label="pitch_up error")
    ax.axhline(0, color="#1d2733", lw=0.6)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("degrees")
    ax.set_title(f"Gyroscope only — {title}", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    name = "out/gyro_bias.png" if args else "out/gyro.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


def moving(x, n=50):
    """1-second (50-sample) centred average."""
    k = np.ones(n) / n
    return np.convolve(x, k, mode="same")


def tilt():
    L = load()
    t = L["t_s"]
    rr, pp = rk.need_ok(imu, "tilt_from_accel", L["ax"], L["ay"], L["az"])
    try:
        rr, pp = np.asarray(rr, dtype=float), np.asarray(pp, dtype=float)
    except (TypeError, ValueError):
        sys.exit("tilt_from_accel() must return two numpy arrays when it gets arrays")
    if rr.shape != t.shape or pp.shape != t.shape:
        sys.exit(f"tilt_from_accel() on arrays of {len(t)} samples must return two arrays of {len(t)} values "
                 f"(np.arctan2 and np.hypot work on whole arrays); got shapes {rr.shape} and {pp.shape}")
    roll, pitch_up = np.degrees(rr), -np.degrees(pp)
    tr, tp = L["true_roll_deg"], L["true_pitch_up_deg"]
    print("The accelerometer's tilt (your tilt_from_accel) against the truth. A single sample is noisy (vibration),")
    print("so the table shows 1-second averages.\n")
    print("  The four turns, at the steepest bank:")
    print("      t (s)   true roll (°)   accelerometer roll (°)")
    ar, ap = moving(roll), moving(pitch_up)
    for a, b in ((30, 40), (90, 110), (160, 170), (230, 250)):
        sel = (t >= a) & (t <= b)
        i = np.flatnonzero(sel)[np.argmax(np.abs(tr[sel]))]
        print(f"     {t[i]:6.1f}      {tr[i]:+6.1f}          {ar[i]:+6.1f}")
    print("\n  Speeding up (10–20 s) and slowing down (280–290 s), at the largest true pitch change:")
    print("      t (s)   true pitch_up (°)   accelerometer pitch_up (°)")
    for a, b in ((10, 20), (280, 290)):
        sel = (t >= a) & (t <= b)
        i = np.flatnonzero(sel)[np.argmax(np.abs(tp[sel]))]
        print(f"     {t[i]:6.1f}       {tp[i]:+6.1f}              {ap[i]:+6.1f}")
    print(f"\n  Over the whole flight (single samples): roll error RMS {np.sqrt(np.mean((roll - tr) ** 2)):.2f}°, "
          f"pitch_up error RMS {np.sqrt(np.mean((pitch_up - tp) ** 2)):.2f}°")
    plt = plt_ready()
    if plt is None:
        return
    fig, axs = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    axs[0].plot(t, roll, color="#8a96a3", lw=0.4, label="accelerometer (each sample)")
    axs[0].plot(t, ar, color="#d64545", lw=1.2, label="accelerometer (1 s average)")
    axs[0].plot(t, tr, color="#1d2733", lw=1.2, label="truth")
    axs[0].set_ylabel("roll (°)")
    axs[1].plot(t, pitch_up, color="#8a96a3", lw=0.4)
    axs[1].plot(t, ap, color="#2e9e4f", lw=1.2, label="accelerometer (1 s average)")
    axs[1].plot(t, tp, color="#1d2733", lw=1.2, label="truth")
    axs[1].set_ylabel("pitch_up (°)")
    axs[1].set_xlabel("t (s)")
    for ax in axs:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower left")
    fig.suptitle("Tilt from gravity vs the truth", fontsize=10)
    fig.tight_layout()
    fig.savefig("out/tilt.png", dpi=90)
    rk.saved("out/tilt.png")


def tau(args=()):
    L = load()
    t = L["t_s"]
    g, a = columns(L, "gx", "gy", "gz"), columns(L, "ax", "ay", "az")
    q0 = start_attitude(L)
    start = "from the true start"
    if args:
        try:
            wrong = float(args[0])
        except ValueError:
            sys.exit("give the wrong start as a roll in degrees, e.g.  python3 run_imu.py tau 10")
        q0 = rot.q_mul(rot.q_from_axis_angle((1.0, 0.0, 0.0), math.radians(wrong)), q0)
        start = f"from a WRONG start: {wrong:g}° of extra roll"
    tr, tp = L["true_roll_deg"], L["true_pitch_up_deg"]
    print(f"The complementary filter on the whole flight (raw gyro: no bias subtracted), {start}.")
    print("Errors against the truth, in degrees. tilt error = √(roll error² + pitch_up error²). About 3 s per τ…\n")
    print("   τ (s)    roll RMS   pitch_up RMS   tilt RMS   worst tilt")
    keep, rms = {}, []
    for tau_s in TAUS:
        Q = quats(rk.need_ok(imu, "complementary", q0, t, g, a, tau_s), len(t), "complementary")
        H = human(Q)
        er, ep = H[:, 0] - tr, H[:, 1] - tp
        tilt_e = np.hypot(er, ep)
        rms.append(math.sqrt(float(np.mean(tilt_e ** 2))))
        print(f"  {tau_s:6.1f}    {math.sqrt(float(np.mean(er ** 2))):7.2f}     {math.sqrt(float(np.mean(ep ** 2))):7.2f}"
              f"      {rms[-1]:7.2f}     {tilt_e.max():7.2f}", flush=True)
        keep[tau_s] = H
    plt = plt_ready()
    if plt is None:
        return
    fig, axs = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [1, 2]})
    axs[0].semilogx(TAUS, rms, "o-", color="#0b6e8a")
    axs[0].set_xlabel("τ (s), log scale")
    axs[0].set_ylabel("tilt RMS (°)")
    axs[0].grid(alpha=0.3, which="both")
    sel = (t >= 80) & (t <= 130)
    axs[1].plot(t[sel], tr[sel], color="#1d2733", lw=1.5, label="truth")
    for tau_s, col in ((TAUS[1], "#d64545"), (TAUS[4], "#2e9e4f"), (TAUS[-1], "#a8680d")):
        axs[1].plot(t[sel], keep[tau_s][sel, 0], color=col, lw=1, label=f"τ = {tau_s:g} s")
    axs[1].set_xlabel("t (s) — the turn at 90–110 s")
    axs[1].set_ylabel("roll (°)")
    axs[1].legend(fontsize=8)
    axs[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("out/tau.png", dpi=90)
    rk.saved("out/tau.png")


def compass(args):
    L, m = load(), meta()
    t = L["t_s"]
    th = L["true_heading_deg"]
    mags = columns(L, "mx", "my", "mz")
    D = imu.declination_deg(m["lat"], m["lon"], m["decimal_year"], m.get("alt_km", 0.0))
    print(f"Declination at the log's place (lat {m['lat']}, lon {m['lon']}, year {m['decimal_year']}), "
          f"WMM through declination_deg: {D:+.3f}°\n")
    tilts = [("no tilt compensation (roll = pitch = 0)", np.zeros(len(t)), np.zeros(len(t))),
             ("compensated with the TRUE roll and pitch", np.radians(L["true_roll_deg"]), -np.radians(L["true_pitch_up_deg"]))]
    if not rk.is_stub(imu.tilt_from_accel):
        rr, pp = rk.need_ok(imu, "tilt_from_accel", L["ax"], L["ay"], L["az"])
        tilts.append(("compensated with your ACCELEROMETER tilt", np.asarray(rr, dtype=float), np.asarray(pp, dtype=float)))
    if args:
        try:
            tau_s = float(args[0])
        except ValueError:
            sys.exit("give τ in seconds, e.g.  python3 run_imu.py compass 10")
        q0 = start_attitude(L)
        Q = quats(rk.need_ok(imu, "complementary", q0, t, columns(L, "gx", "gy", "gz"), columns(L, "ax", "ay", "az"),
                             tau_s), len(t), "complementary")
        Rm = [rot.matrix_to_euler_zyx(rot.q_to_matrix(q)) for q in Q]
        tilts.append((f"compensated with your FILTER's tilt (τ = {tau_s:g} s)", np.array([x[0] for x in Rm]),
                      np.array([x[1] for x in Rm])))
    print("  your mag_heading − true heading        your true_heading(…, D) − true heading")
    print("  (mean, RMS) in degrees                  (mean, RMS) in degrees")
    curves = {}
    for label, rr, pp in tilts:
        h = np.array([rk.need_ok(imu, "mag_heading", mags[i], float(rr[i]), float(pp[i])) for i in range(len(t))], dtype=float)
        ht = np.array([rk.need_ok(imu, "true_heading", float(x), D) for x in h], dtype=float)
        e1, e2 = wrap(h - th), wrap(ht - th)
        print(f"  {label}:")
        print(f"     {e1.mean():+7.2f}, {math.sqrt(float(np.mean(e1 ** 2))):6.2f}"
              f"                         {e2.mean():+7.2f}, {math.sqrt(float(np.mean(e2 ** 2))):6.2f}")
        curves[label] = e2
    chip = columns(L, "chip_qx", "chip_qy", "chip_qz", "chip_qw")
    hc = np.array([rot.heading_deg_from_q(q) for q in chip])
    e = wrap(hc - th)
    print(f"\nThe IMU chip's own attitude (chip_q…): heading − true heading, mean {e.mean():+.2f}°, "
          f"RMS {math.sqrt(float(np.mean(e ** 2))):.2f}°   (as the chip gives it)")
    if rk.is_stub(imu.q_true_north):
        print("   (write TODO 6, q_true_north, to correct it)")
    else:
        qt = [rk.need_ok(imu, "q_true_north", q, D) for q in chip]
        e2 = wrap(np.array([rot.heading_deg_from_q(q) for q in qt]) - th)
        print(f"   after your q_true_north: mean {e2.mean():+.2f}°, RMS {math.sqrt(float(np.mean(e2 ** 2))):.2f}°")
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    for (label, e2), col in zip(curves.items(), ("#8a96a3", "#1d2733", "#d64545", "#2e9e4f")):
        ax.plot(t, e2, lw=0.7, color=col, label=label)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("true heading error (°)")
    ax.set_title("Your compass, corrected to true north", fontsize=9)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("out/compass.png", dpi=90)
    rk.saved("out/compass.png")


def stale(args):
    n = 50
    if args:
        try:
            n = int(args[0])
        except ValueError:
            sys.exit("give max_repeat as a whole number, e.g.  python3 run_imu.py stale 50")
    F = load("imu_frozen.csv")
    t = F["t_s"]
    cols = ("gx", "gy", "gz", "ax", "ay", "az", "mx", "my", "mz")
    gaps = np.diff(t)
    print(f"imu_frozen.csv: {len(t)} samples over {t[-1] - t[0]:.2f} s; a new timestamp every "
          + (f"{gaps.min():.2f} s" if abs(gaps.max() - gaps.min()) < 1e-6 else f"{gaps.min():.2f}–{gaps.max():.2f} s")
          + ", from start to end.")
    if rk.is_stub(getattr(imu.StaleDetector, "update", None)):
        sys.exit("StaleDetector.update() is not written yet: write TODO 7 in navera_lite/imu.py")
    try:
        d = imu.StaleDetector(max_repeat=n)
    except Exception as e:
        sys.exit(f"StaleDetector(max_repeat={n}) stopped with {type(e).__name__}: {e}")
    first, count = None, 0
    for i in range(len(t)):
        v, err = rk.call(d, "update", tuple(float(F[c][i]) for c in cols))
        if err:
            sys.exit(f"at t = {t[i]:.2f} s: {err}")
        if not isinstance(v, (bool, np.bool_)):
            sys.exit(f"update() must return True or False, but it returned {v!r} at t = {t[i]:.2f} s")
        if v:
            count += 1
            if first is None:
                first = t[i]
    print(f"\nYour StaleDetector(max_repeat={n}), fed the 9 readings of every sample:")
    if first is None:
        print("   never said 'frozen'.")
    else:
        print(f"   first 'frozen' at t = {first:.2f} s; {count} samples called frozen in all.")


MODES = {"test": test, "look": look, "tilt": tilt}

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("gyro", "compass", "stale", "tau"):
        {"gyro": gyro, "compass": compass, "stale": stale, "tau": tau}[sys.argv[1]](sys.argv[2:])
    elif len(sys.argv) == 2 and sys.argv[1] in MODES:
        MODES[sys.argv[1]]()
    else:
        print(__doc__)
        sys.exit(1)
