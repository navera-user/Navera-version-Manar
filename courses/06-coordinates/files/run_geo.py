"""run_geo.py — runs YOUR functions of navera_lite/geo.py on the lab's situations, and draws them.

    python3 run_geo.py test        check each function on its docstring example
    python3 run_geo.py bearings    four directions, and a long flight out and back       (Step 2)
    python3 run_geo.py cos         the route-length audit: where to take cos(latitude)    (Step 3)
    python3 run_geo.py route       the corridor audit: great circle vs straight line      (Step 4)
    python3 run_geo.py ecef        round trips geodetic -> ECEF -> geodetic                (Step 6)
    python3 run_geo.py enu         the local frame: rotation checks and a far point        (Step 7)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import math
import os
import sys

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

g = rk.load_student("navera_lite.geo")
_kit_hint = rk._hint


def _hint(e):
    """This mission's version of the kit's extra sentence for a numpy shape error (no lstsq here)."""
    if "could not be broadcast" in str(e):
        return (" — the shapes do not fit: give haversine_m the great-circle points as a (101, 1) column and "
                "the line points as a (1, 1001) row (lab Step 4, 🧰 broadcasting)")
    if "concatenate tuple" in str(e) or ("unsupported operand" in str(e) and "'tuple' and 'float'" in str(e)):
        return " — radii() returns two numbers (M, N): keep only N with `_, n = radii(lat)`"
    return _kit_hint(e)


rk._hint = _hint

# The end points of NAVERA's long simulated route (backlog items R-2 and R-6, 2026-10-01):
PARIS = (48.8534951, 2.3483915)
TUNISIA = (33.8439408, 9.400138)          # central Tunisia


def fmt(v, nd=1):
    """A number with spaces between thousands: 1 767 812.3"""
    s = f"{v:,.{nd}f}".replace(",", " ")
    return s


def close(got, want, tol):
    if isinstance(want, (tuple, list)):
        try:
            vals = [float(x) for x in got]
        except (TypeError, ValueError):
            return False
        return len(vals) == len(want) and all(abs(a - b) <= tol for a, b in zip(vals, want))
    try:
        return abs(float(got) - want) <= tol
    except (TypeError, ValueError):
        return False


def show(v):
    if isinstance(v, (tuple, list)):
        try:
            return "(" + ", ".join(f"{float(x):.6f}" if abs(float(x)) < 1000 else f"{float(x):.1f}" for x in v) + ")"
        except (TypeError, ValueError):
            return repr(v)
    if hasattr(v, "shape"):
        return repr(v.round(3).tolist())
    return f"{v:.6g}" if isinstance(v, float) and abs(v) < 1e5 else (f"{v:.1f}" if isinstance(v, float) else repr(v))


def test():
    import numpy as np
    LON, PAR = (51.5074, -0.1278), (48.8566, 2.3522)
    cases = [  # TODO, function, arguments, docstring result, tolerance
        (1, "enu_flat", (*LON, *PAR), (176585.4, -294755.5), 0.1),
        (1, "enu_flat", (-17.0, 179.99, -17.0, -179.99), (2126.7, 0.0), 0.1,
         "across the ±180° meridian near Fiji: expected (2126.7, 0.0) — bring Δλ into [−180, 180), lesson §1"),
        (1, "enu_flat", (-17.0, -179.99, -17.0, 179.99), (-2126.7, 0.0), 0.1,
         "WEST across the ±180° meridian: expected (−2126.7, 0.0). Tens of thousands of km EAST: your wrap is "
         "`% 360` only — the rule is Δλ = (λ − λ0 + 180) % 360 − 180, lesson §1"),
        (2, "offset", (-33.9249, 18.4241, 1000.0, 2000.0), (-33.906914, 18.434937), 1e-6),
        (2, "offset", (0.0, 179.99, 5000.0, 0.0), (0.0, -179.965034), 1e-6,
         "5 km east of 179.99°: expected (0.0, −179.965034) — bring the new longitude into [−180, 180), lesson §1"),
        (3, "haversine_m", (*LON, *PAR), 343556.1, 0.1),
        (4, "bearing_deg", (*LON, *PAR), 148.12, 0.01),
        (5, "great_circle_points", ((0.0, 0.0), (0.0, 90.0), 3), None, None),
        (5, "great_circle_points", (LON, PAR, 3), (50.1886, 1.1466), 1e-4),
        (6, "max_offset_km", (LON, PAR), 2.48, 0.005),
        (7, "radii", (0.0,), (6335439.327, 6378137.0), 0.001),
        (7, "radii", (45.0,), (6367381.8, 6388838.3), 0.1),
        (8, "geodetic_to_ecef", (1.3521, 103.8198, 15.0), (-1523121.7, 6191803.0, 149494.2), 0.1),
        (9, "ecef_to_geodetic", (-1523121.7, 6191803.0, 149494.2), (1.3521, 103.8198, 15.02), 0.05),
        (9, "ecef_to_geodetic", (2897606.0985, 1351175.9140, 5500563.7365), (60.0, 25.0, 100.0), 0.001,
         "a point at (60°, 25°, 100 m), far from the equator: expected (60.0, 25.0, 100.0) to 1 mm — keep lat in "
         "DEGREES for radii(), radians only in sin/cos/atan2; enough iterations? (100.50 m: the loop repeats the "
         "first guess — inside it, φ = atan2(Z, p·(1 − e²·N/(N + h))))"),
        (10, "enu_matrix", (0.0, 0.0), None, None),
        (10, "enu_matrix", (60.1699, 24.9384), None, None),
        (11, "geodetic_to_enu", (-33.80, 151.30, 0.0, -33.8688, 151.2093, 0.0), (8398.9, 7627.5, -10.1), 0.1),
        (12, "enu_to_geodetic", (8398.9, 7627.5, -10.1, -33.8688, 151.2093, 0.0), (-33.80, 151.30, 0.0), 0.01),
    ]
    done = 0
    for case in cases:
        k, fn, args, want, tol = case[:5]
        note = case[5] if len(case) > 5 else None
        got, err = rk.call(g, fn, *args)
        if err:
            print(f"✘ TODO {k:2d}  {err}")
            continue
        if fn == "great_circle_points" and want is not None:
            mid = got[1] if isinstance(got, list) and len(got) == 3 else got
            ok = close(mid, want, tol)
            want_s, got_s = f"middle point {show(want)}", f"middle point {show(mid)}"
            if not ok and close(mid, (0.0, 0.0), 1.6):
                note = "these look like RADIANS: atan2 returns radians — wrap lat and lon in math.degrees(…)"
        elif fn == "great_circle_points":
            ok = (isinstance(got, list) and len(got) == 3
                  and all(close(p, q, 1e-9) for p, q in zip(got, [(0.0, 0.0), (0.0, 45.0), (0.0, 90.0)])))
            want_s = "[(0, 0), (0, 45), (0, 90)]"
            got_s = repr([tuple(round(float(x), 6) for x in p) for p in got]) if isinstance(got, list) else repr(got)
            if (not ok and isinstance(got, list) and len(got) == 3
                    and abs(float(got[1][1]) - math.pi / 4) < 1e-6):
                note = "(0, 0.785398) is (0, 45°) in RADIANS: atan2 returns radians — wrap lat and lon in math.degrees(…)"
        elif fn == "enu_matrix" and args[0] != 0.0:
            a = np.asarray(got, dtype=float) if not isinstance(got, str) else None
            ok = (a is not None and a.shape == (3, 3) and np.allclose(a @ a.T, np.eye(3), atol=1e-9)
                  and abs(np.linalg.det(a) - 1.0) < 1e-9 and np.allclose(a[2], [0.45105, 0.209738, 0.867504], atol=1e-5))
            got_s = "Helsinki: R @ R.T = I, det = +1, Up row right" if ok else "Helsinki: " + (
                "shape is not (3, 3)" if a is None or a.shape != (3, 3) else
                f"R @ R.T is not I or det = {np.linalg.det(a):+.3f} — a sign lost inside a row, or two rows swapped")
            want_s = "R @ R.T = I, det = +1"
            note = "compare each of the nine entries with lesson §7 (the N row has two minus signs)"
        elif fn == "enu_matrix":
            a = np.asarray(got, dtype=float) if not isinstance(got, str) else None
            ok = a is not None and a.shape == (3, 3) and np.allclose(a, [[0, 1, 0], [0, 0, 1], [1, 0, 0]], atol=1e-12)
            want_s, got_s = "[[0, 1, 0], [0, 0, 1], [1, 0, 0]]", show(a) if a is not None else repr(got)
        else:
            ok = close(got, want, tol)
            want_s, got_s = show(want), show(got)
        why = f"   ({note})" if note else f"   (the docstring says {want_s})"
        print(f"{'✔' if ok else '✘'} TODO {k:2d}  {fn}  ->  {got_s}" + ("" if ok else why))
        done += ok
    # haversine_m must also work on numpy arrays (Step 2, 🧰 box)
    got, err = rk.call(g, "haversine_m", np.array([0.0, 0.0]), 0.0, 0.0, np.array([1.0, 90.0]))
    if not err:
        ok = hasattr(got, "shape") and close(list(got), (111194.9, 10007543.4), 0.1)
        why = ("   (the docstring says [111194.9, 10007543.4])" if hasattr(got, "shape") else
               "   (expected an array of two distances: use np.sin, np.cos, np.arcsin… not math.…)")
        print(f"{'✔' if ok else '✘'} TODO  3  haversine_m on numpy arrays  ->  {show(got)}" + ("" if ok else why))
        done += ok
    elif "only length-1 arrays" in err or "only size-1 arrays" in err:
        print("✘ TODO  3  haversine_m works on numbers but not on numpy arrays: use np.sin, np.cos, np.sqrt, "
              "np.arcsin and np.minimum instead of math.… and min(…)")
    else:
        print(f"✘ TODO  3  (arrays) {err}")
    print(f"\n{done} of {len(cases) + 1} examples give the docstring's result.")


def bearings():
    lat, lon = 46.2044, 6.1432                             # Geneva
    print("From Geneva, a point 0.01° away in each direction (lat first):")
    for name, p in [("north", (lat + 0.01, lon)), ("east", (lat, lon + 0.01)),
                    ("south", (lat - 0.01, lon)), ("west", (lat, lon - 0.01))]:
        b = rk.need_ok(g, "bearing_deg", lat, lon, *p, kind=float)
        print(f"   due {name:5s}  ->  bearing_deg = {b:8.3f}°")
    sing, lond = (1.3644, 103.9915), (51.4700, -0.4543)  # Singapore Changi, London Heathrow
    d = rk.need_ok(g, "haversine_m", *sing, *lond, kind=float)
    out = rk.need_ok(g, "bearing_deg", *sing, *lond, kind=float)
    back = rk.need_ok(g, "bearing_deg", *lond, *sing, kind=float)
    print(f"\nSingapore Changi -> London Heathrow: {fmt(d / 1000)} km on the sphere")
    print(f"   bearing at take-off from Singapore:  {out:7.2f}°")
    print(f"   bearing at take-off from London (the way back):  {back:7.2f}°")
    if not 0.0 <= out < 360.0 or not 0.0 <= back < 360.0:
        print("\n⚠ a bearing must be in [0, 360): did you forget % 360?")


def cos_audit():
    print("Route length: three ways. (On a sphere of radius EARTH_RADIUS_M; distances in km.)\n")
    print(f"{'route':22s} {'flat, cos(START lat)':>22s} {'flat, your enu_flat':>22s} {'great circle (haversine)':>26s}")
    for name, a, b in [("London -> Paris", (51.5074, -0.1278), (48.8566, 2.3522)),
                       ("Paris -> Tunisia", PARIS, TUNISIA)]:
        dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
        start = math.hypot(dlon * g.EARTH_RADIUS_M * math.cos(math.radians(a[0])), dlat * g.EARTH_RADIUS_M)
        e_n = rk.need_ok(g, "enu_flat", *a, *b, n=2)
        mine = math.hypot(*e_n)
        hv, err = rk.call(g, "haversine_m", *a, *b)
        hv_s = f"{fmt(hv / 1000)}" if not err else "(TODO 3 first)"
        print(f"{name:22s} {fmt(start / 1000):>22s} {fmt(mine / 1000):>22s} {hv_s:>26s}")
    print("\nNAVERA's backlog (R-6, 2026-10-01): the server's flat approximation said 1750 km; the route is 1768 km.")


def route():
    pts = rk.need_ok(g, "great_circle_points", PARIS, TUNISIA, 101)
    if not isinstance(pts, list) or len(pts) != 101:
        sys.exit(f"great_circle_points(PARIS, TUNISIA, 101) must return a list of 101 (lat, lon), got {type(pts).__name__}")
    off = rk.need_ok(g, "max_offset_km", PARIS, TUNISIA, kind=float)
    mid_gc = pts[50]
    mid_line = ((PARIS[0] + TUNISIA[0]) / 2, (PARIS[1] + TUNISIA[1]) / 2)
    print("Paris -> central Tunisia")
    print(f"   halfway on the great circle      : ({mid_gc[0]:.4f}, {mid_gc[1]:.4f})")
    print(f"   halfway on the straight lat/lon line: ({mid_line[0]:.4f}, {mid_line[1]:.4f})")
    print(f"   max_offset_km                    : {off:.2f} km      (the map corridor was ±1 km wide)")
    legs = rk.need_ok(g, "great_circle_points", PARIS, TUNISIA, 177)
    step = rk.need_ok(g, "haversine_m", *legs[88], *legs[89], kind=float)
    leg_off = rk.need_ok(g, "max_offset_km", legs[88], legs[89], kind=float)
    print(f"\nNAVERA's fix: fly and map the route as short great-circle legs (≤ 10 km).")
    print(f"   the leg in the middle of the route: {fmt(step, 0)} m long, max offset {leg_off * 1000:.2f} m")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 7))
    ax.plot([PARIS[1], TUNISIA[1]], [PARIS[0], TUNISIA[0]], "--", color="#d17a00", lw=2,
            label="straight line on a lat/lon map (the old corridor)")
    ax.plot([p[1] for p in pts], [p[0] for p in pts], "-", color="#0b6e8a", lw=2, label="great circle (what a vehicle flies)")
    for name, p in (("Paris", PARIS), ("Tunisia", TUNISIA)):
        ax.plot(p[1], p[0], "s", color="#b0453a")
        ax.annotate(name, (p[1], p[0]), xytext=(8, 0), textcoords="offset points")
    ax.set_xlabel("longitude (°)")
    ax.set_ylabel("latitude (°)")
    ax.set_title(f"Paris -> Tunisia: the paths are up to {off:.1f} km apart")
    ax.grid(alpha=.3)
    ax.legend(loc="lower left", fontsize=8)
    fig.savefig("out/route.png", dpi=90, bbox_inches="tight")
    plt.close(fig)
    rk.saved("out/route.png")


PLACES = [("Nairobi", -1.2921, 36.8219, 1795.0), ("Helsinki", 60.1699, 24.9384, 20.0),
          ("Dead Sea shore", 31.5590, 35.4732, -400.0), ("Ushuaia", -54.8019, -68.3030, 30.0),
          ("an airliner over Alaska", 64.8378, -147.7164, 11000.0), ("Anchorage", 61.2181, -149.9003, 40.0)]


def ecef():
    print(f"{'place':24s} {'lat':>9s} {'lon':>10s} {'h (m)':>8s} {'X (km)':>11s} {'Y (km)':>11s} {'Z (km)':>11s}"
          f"   round-trip error")
    worst = 0.0
    for name, lat, lon, h in PLACES:
        x = rk.need_ok(g, "geodetic_to_ecef", lat, lon, h, n=3)
        back = rk.need_ok(g, "ecef_to_geodetic", *x, n=3)
        err_m = math.hypot((back[0] - lat) * 111_000, (back[1] - lon) * 111_000 * math.cos(math.radians(lat)),
                           back[2] - h)
        worst = max(worst, err_m)
        print(f"{name:24s} {lat:9.4f} {lon:10.4f} {h:8.0f} {x[0] / 1000:11.3f} {x[1] / 1000:11.3f} {x[2] / 1000:11.3f}"
              f"   {err_m * 1000:10.4f} mm")
    print(f"\nworst round trip: {worst * 1000:.4f} mm   " + ("✔ below 1 mm" if worst < 1e-3 else
          "✘ above 1 mm: degrees and radians mixed up, or too few iterations? (Step 6 hints)"))


def enu():
    import numpy as np
    home = (60.1699, 24.9384, 0.0)                      # Helsinki, at the ellipsoid
    r = np.asarray(rk.need_ok(g, "enu_matrix", home[0], home[1]), dtype=float)
    if r.shape != (3, 3):
        sys.exit(f"enu_matrix must return a 3 × 3 array, got shape {r.shape}")
    np.set_printoptions(precision=6, suppress=True)
    print("R at Helsinki (rows: East, North, Up in ECEF):\n", r)
    print("\nR @ R.T =\n", r @ r.T)
    det = np.linalg.det(r)
    print(f"\ndet(R) = {det:+.6f}")
    if not np.allclose(r @ r.T, np.eye(3), atol=1e-9):
        print("⚠ R @ R.T is not the identity: the rows are not unit vectors at right angles (radians? a sign?)")
    elif det < 0:
        print("⚠ det(R) = −1: R is a mirror, not a rotation — two rows swapped, or one row with the wrong sign")
    tallinn = (59.4370, 24.7536, 0.0)                   # across the Gulf of Finland, also at the ellipsoid
    e, n, u = rk.need_ok(g, "geodetic_to_enu", *tallinn, *home, n=3)
    print(f"\nTallinn in Helsinki's ENU frame: east {fmt(e)} m, north {fmt(n)} m, up {fmt(u)} m")
    back = rk.need_ok(g, "enu_to_geodetic", e, n, u, *home, n=3)
    print(f"and back to geodetic: ({back[0]:.7f}, {back[1]:.7f}, {back[2]:.4f} m)   (Tallinn: {tallinn})")


MODES = {"test": test, "bearings": bearings, "cos": cos_audit, "route": route, "ecef": ecef, "enu": enu}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(__doc__)
        sys.exit(1)
    MODES[sys.argv[1]]()
