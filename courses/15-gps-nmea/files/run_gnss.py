"""run_gnss.py — runs YOUR functions of navera_lite/gnss.py on the lab's situations, and draws them.

    python3 run_gnss.py naive          a naive reader on the drive log (no code to write)          (Step 0)
    python3 run_gnss.py test           check each function on its docstring example (and a few traps)
    python3 run_gnss.py log            the damaged lines of the drive log, found by YOUR is_valid    (Step 2)
    python3 run_gnss.py forge          test FORGED_LINE of answers.py against your parser          (Step 5)
    python3 run_gnss.py sky            DOP experiments on skies you choose                         (Step 6)
    python3 run_gnss.py dop            recompute the receiver's DOPs on the whole drive            (Step 7)
    python3 run_gnss.py drive          the whole drive through your judge; writes results.json     (Step 8)

Pictures are saved in out/ — click them in the file list of the 📝 Code tab.
"""
import json
import math
import os
import sys

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

g = rk.load_student("navera_lite.gnss")
geo = rk.load_student("navera_lite.geo")          # finished part from mission 06: haversine_m, enu_flat
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if isinstance(e, TypeError) and "unsupported operand type(s) for ^" in s:
        return " — XOR works on numbers, not characters: use ord(ch) (lesson §2, 🧰 XOR and hex)"
    if isinstance(e, ValueError) and "could not convert string to float" in s:
        return " — an empty or damaged field reached float(): use the given to_float(), which returns None"
    if isinstance(e, IndexError):
        return (" — a list or a string is shorter than you think: check len(…) BEFORE reading [k] (a cut line has few "
                "fields; an empty line has no [0]: use startswith)")
    if isinstance(e, AttributeError) and "'NoneType'" in s:
        return (" — something is None: in is_valid, test isinstance(line, str) FIRST; elsewhere, fields(line) is None "
                "for an invalid line: test it before using it")
    if isinstance(e, ValueError) and "not enough values to unpack" in s:
        return (" — split(\"*\", 1) gave one piece: the line has no \"*\". Test \"*\" in line before unpacking "
                "(Step 2, hint 3)")
    if isinstance(e, TypeError) and "unsupported operand type(s) for +" in s and "NoneType" in s:
        return (" — an empty field is None, and None + a number crashes: add only when BOTH values are not None "
                "(Step 3 🧰); the geoid separation is field 11")
    if "Singular matrix" in s:
        return (" — np.linalg.inv() of a singular GᵀG: test the rank of G first (np.linalg.matrix_rank) and return "
                "None (lesson §5)")
    return _kit_hint(e)


rk._hint = _hint

DATA = "/data/academy/15-gps-nmea"
LOG = os.path.join(DATA, "sousse_drive.nmea")
TRUTH = os.path.join(DATA, "truth.csv")
OUT = "out"
REAL = "$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70"   # lesson §3
FORGE_BASE = "$GPGGA,052200.00,3545.89257,N,01045.14417,E,1,12,0.77,2.1,M,32.0,M,,*59"   # the log, 05:22:00
GATE_V_MPS, GATE_MARGIN_M = 100.0, 50.0           # mission 01's jump gate (navera_lite.yaml)


def need_log():
    if not os.path.exists(LOG):
        sys.exit(f"{LOG} is missing: the course data is not mounted in this sandbox — tell your teacher.")
    return g.read_log(LOG)


def hms(t):
    """seconds since midnight → '05:17:31'"""
    if t is None:
        return "??:??:??"
    t = int(round(t))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def truth_by_second():
    out = {}
    if os.path.exists(TRUTH):
        with open(TRUTH) as f:
            next(f)
            for row in f:
                u, la, lo, _ = row.strip().split(",")
                out[int(u[:2]) * 3600 + int(u[2:4]) * 60 + int(float(u[4:]))] = (float(la), float(lo))
    return out


def stop_if_err(err):
    if err:
        sys.exit(err)


# ======================================================================================== naive (Step 0)
def naive():
    """A naive reader: it takes every line that starts with $GPGGA, does not check the checksum, the fix
    quality or the minutes, and believes what it reads. (The runner's own code, not yours.)"""
    lines = need_log()
    truth = truth_by_second()
    used, worst = [], []
    for ln in lines:
        if not ln.startswith("$GPGGA"):
            continue
        f = ln.split("*")[0].split(",")
        if len(f) < 7:
            continue                                   # too short even for a naive reader
        try:
            t = int(f[1][:2]) * 3600 + int(f[1][2:4]) * 60 + int(float(f[1][4:]))
            la, lo = float(f[2]), float(f[4])
        except (ValueError, IndexError):
            continue                                   # the naive reader skips what it cannot read at all
        lat = int(la // 100) + (la - 100 * int(la // 100)) / 60.0
        lon = int(lo // 100) + (lo - 100 * int(lo // 100)) / 60.0
        used.append((t, lat, lon, f[6]))
        if t in truth:
            err = geo.haversine_m(lat, lon, *truth[t])
            worst.append((err, t, f[6], ln))
    worst.sort(reverse=True)
    far = [w for w in worst if w[0] > 100.0]
    print(f"The naive reader used {len(used)} positions from {len(lines)} lines.")
    q6 = sum(1 for u in used if u[3] == "6")
    print(f"{q6} of them have quality 6, and {sum(1 for u in used if u[3] == '0')} quality 0.")
    print(f"{len(far)} of them are more than 100 m from where the car really was. The worst five:\n")
    print(f"  {'UTC':8s}  {'error':>10s}  quality  line")
    for err, t, q, ln in worst[:5]:
        print(f"  {hms(t)}  {err / 1000:8.2f} km     {q:>2s}    {ln[:62]}")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs(OUT, exist_ok=True)
    lat0, lon0 = 35.8270, 10.6420
    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    te = [geo.enu_flat(lat0, lon0, *truth[t]) for t in sorted(truth)]
    ne = [geo.enu_flat(lat0, lon0, la, lo) for _, la, lo, _ in used]
    for a, zoom in zip(ax, (False, True)):
        a.plot([e / 1000 for e, _ in te], [n / 1000 for _, n in te], "-", color="0.6", lw=4, label="truth")
        a.plot([e / 1000 for e, _ in ne], [n / 1000 for _, n in ne], ".-", color="#d64545", ms=2, lw=0.7,
               label="naive reader")
        a.set_xlabel("east (km)")
        a.set_ylabel("north (km)")
        a.set_aspect("equal", adjustable="box")
        if zoom:
            a.set_xlim(-1, 21)
            a.set_ylim(-9, 3)
            a.set_title("zoom on the drive")
        else:
            a.set_title("the whole picture")
        a.legend(loc="best")
    fig.suptitle("A naive NMEA reader on a 19 km drive (synthetic log, Sousse → Monastir)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/naive.png", dpi=90)
    rk.saved(f"{OUT}/naive.png")


# ======================================================================================== test
def close(got, want, tol):
    try:
        return abs(float(got) - want) <= tol
    except (TypeError, ValueError):
        return False


def test():
    import numpy as np
    rows = []          # (todo, label, ok, got-string, note)

    def add(todo, label, fn, args, check, show=repr, note=""):
        got, err = rk.call(g, fn, *args)
        if err and "returned None" in err:
            if check(None):
                got, err = None, None                      # None is the right answer here
            else:                                          # None is a possible answer, just not here
                rows.append((todo, label, False, "None", note(None) if callable(note) else note))
                return
        if err:
            rows.append((todo, label, False, err, ""))
            return
        try:
            ok = bool(check(got))
        except Exception:
            ok = False
        if not ok and callable(note):
            try:
                note = note(got)
            except Exception:
                note = ""
        rows.append((todo, label, ok, show(got), "" if ok else note))

    add(1, 'nmea_checksum("GPGSA,A,1") → "32"', "nmea_checksum", ("GPGSA,A,1",), lambda v: v == "32",
        note='expected the str "32" — 2 upper-case hex digits: f"{x:02X}"')
    add(1, 'nmea_checksum("GPGSA,A,18") → "0A", two digits', "nmea_checksum", ("GPGSA,A,18",), lambda v: v == "0A",
        note='"A", "a" or "0a" instead of "0A": the format needs 02X (2 digits, upper case)')
    for line, want, label, why in [
            ("$GPGSA,A,1*32\r\n", True, "with \\r\\n at the end", "strip the line BEFORE you test it"),
            ("$GPGSA,A,1*33", False, "wrong checksum", "compare the 2 digits after * with nmea_checksum(body)"),
            ("$GPGSA,A,3,02,05,07,09,13,20,23,24,30,,,,1.98,1.15,1.61*0c", True, "lower-case hex digits",
             "hex digits may be lower case: compare with given.upper()"),
            ("$GPGSA,A,1*3", False, "only one hex digit", "exactly 2 characters after *"),
            ("$GPGSA,A,1", False, "no checksum", "no * → False"),
            ("$GPGSA,A,1$GPGSA,A,1*32", False, "two sentences glued", "a $ inside the body → False"),
            (None, False, "None", "test isinstance(line, str) first"), ("", False, "empty line", "")]:
        add(2, f"is_valid({line!r:.40}) → {want}  ({label})", "is_valid", (line,), lambda v, w=want: v is w,
            note=why or "is_valid must return True or False (not None)")
    add(3, 'dm_to_deg("3544.04006", "N") → 35.734001', "dm_to_deg", ("3544.04006", "N"),
        lambda v: close(v, 35.734001, 1e-6), note="35.4404006: you divided by 100 — the last two digits before "
        "the point are MINUTES (lesson §3)")
    add(3, 'dm_to_deg("01034.55091", "W") → −10.575849', "dm_to_deg", ("01034.55091", "W"),
        lambda v: close(v, -10.5758485, 1e-6),
        note=lambda v: ("you divided by 100 — minutes / 60 (lesson §3)" if close(abs(v), 10.3455091, 1e-6)
                        else "W and S are negative"))
    add(3, 'dm_to_deg("3574.17098", "N") → None (74 minutes)', "dm_to_deg", ("3574.17098", "N"), lambda v: v is None,
        note="minutes must be in [0, 60)")
    add(3, 'dm_to_deg("", "N") → None', "dm_to_deg", ("", "N"), lambda v: v is None,
        note="an empty field is no value: use to_float(), which gives None")
    add(4, "parse_gga(the line of lesson §3)", "parse_gga", (REAL,),
        lambda v: isinstance(v, dict) and v.get("qual") == 1 and v.get("sats") == 12 and close(v.get("lat"), 35.734001, 1e-6)
        and close(v.get("lon"), 10.5758485, 1e-6) and close(v.get("hdop"), 0.72, 1e-9)
        and close(v.get("h_ell_m"), 127.4, 1e-6) and close(v.get("t_utc_s"), 51381.0, 1e-6),
        show=lambda v: repr(v)[:140], note="compare each key with the docstring Example")
    add(4, "parse_gga(a no-fix GGA): qual 0, lat None, h_ell_m None", "parse_gga",
        ("$GPGGA,052009.00,,,,,0,00,99.99,,,,,,*68",),
        lambda v: isinstance(v, dict) and v.get("qual") == 0 and v.get("lat") is None and v.get("h_ell_m") is None,
        show=lambda v: repr(v)[:140], note="empty fields → None, never 0 (a missing height is not 0 m)")
    add(4, "parse_gga(no altitude, geoid separation present): h_ell_m None, no crash", "parse_gga",
        ("$GPGGA,101013.00,3544.04006,N,01034.55091,E,1,08,1.10,,M,32.1,M,,*72",),
        lambda v: isinstance(v, dict) and v.get("alt_msl_m") is None and close(v.get("geoid_m"), 32.1, 1e-9)
        and v.get("h_ell_m") is None, show=lambda v: repr(v)[:140],
        note="add the two heights only when BOTH are not None")
    add(4, "parse_gga(latitude with hemisphere E, longitude with N) → lat None, lon None", "parse_gga",
        ("$GPGGA,101014.00,3544.04006,E,01034.55091,N,1,08,1.10,12.0,M,32.1,M,,*68",),
        lambda v: isinstance(v, dict) and v.get("lat") is None and v.get("lon") is None,
        show=lambda v: repr(v)[:140], note="the latitude's hemisphere must be N or S, the longitude's E or W")
    add(4, "parse_gga(an RMC line) → None", "parse_gga",
        ("$GPRMC,051217.00,A,3549.61531,N,01038.52535,E,11.88,136.6,121026,,,A*5F",), lambda v: v is None,
        note="only a GGA gives a dict: test the address f[0]")
    add(5, "parse_gsa(the docstring line)", "parse_gsa", ("$GPGSA,A,3,02,05,07,09,13,20,23,24,30,,,,1.98,1.15,1.61*0C",),
        lambda v: isinstance(v, dict) and v.get("mode") == 3 and v.get("prns") == [2, 5, 7, 9, 13, 20, 23, 24, 30]
        and close(v.get("pdop"), 1.98, 1e-9) and close(v.get("hdop"), 1.15, 1e-9) and close(v.get("vdop"), 1.61, 1e-9),
        show=lambda v: repr(v)[:140], note="prns: ints, empty slots skipped; DOPs from fields 15, 16, 17")
    add(5, "parse_gsa(NMEA 4.10, with a system ID)", "parse_gsa",
        ("$GNGSA,A,3,02,05,07,09,,,,,,,,,2.10,1.20,1.72,1*0C",),
        lambda v: isinstance(v, dict) and v.get("prns") == [2, 5, 7, 9] and close(v.get("vdop"), 1.72, 1e-9),
        show=lambda v: repr(v)[:140], note="a 19th item (system ID) must be accepted: len(f) >= 18, not == 18")
    add(5, "parse_gsa(all 12 slots used)", "parse_gsa",
        ("$GPGSA,A,3,01,02,03,04,05,06,07,08,09,10,11,12,1.0,0.6,0.8*3E",),
        lambda v: isinstance(v, dict) and v.get("prns") == list(range(1, 13)),
        show=lambda v: repr(v)[:140], note="the 12th slot is f[14]: slots 3 to 14 inclusive, f[3:15]")
    add(6, "geometry_matrix([90.0], [30.0]) → [[−0.866, −0.0, −0.5, 1.0]]", "geometry_matrix", ([90.0], [30.0]),
        lambda v: np.allclose(np.asarray(v, dtype=float), [[-0.8660254, 0.0, -0.5, 1.0]], atol=1e-6),
        show=lambda v: repr(np.round(np.asarray(v, dtype=float), 4).tolist()),
        note="[[−0.138, 0.069, 0.988, 1.0]]: np.sin/np.cos got degrees (np.radians); +0.866: the signs (−u); "
             "a value in the North column: east = cos(el)·sin(az)")
    ex = ([0, 90, 180, 270, 0], [30, 30, 30, 30, 90])
    add(7, "dops(lesson §5 example): HDOP 1.155, VDOP 2.236", "dops", ex,
        lambda v: isinstance(v, dict) and close(v.get("HDOP"), 1.1547, 1e-3) and close(v.get("VDOP"), 2.2361, 1e-3)
        and close(v.get("TDOP"), 1.4142, 1e-3) and close(v.get("GDOP"), 2.8868, 1e-3) and close(v.get("EDOP"), 0.8165, 1e-3),
        show=lambda v: repr({k: round(x, 3) for k, x in v.items()}) if isinstance(v, dict) else repr(v),
        note="Q = inverse of GᵀG; HDOP = √(Q_EE + Q_NN), VDOP = √Q_UU … (lesson §5)")
    add(7, "dops(lesson §5 example without the overhead satellite) → None", "dops", ([0, 90, 180, 270], [30, 30, 30, 30]),
        lambda v: v is None, show=lambda v: repr({k: f"{x:.3g}" for k, x in v.items()}) if isinstance(v, dict) else repr(v),
        note="singular geometry: return None — numpy's inv() does not fail here: test the rank of G before inverting")
    add(7, "dops(3 satellites) → None", "dops", ([0, 120, 240], [30, 50, 70]), lambda v: v is None,
        note="fewer than 4 satellites: return None")
    gga6 = {"qual": 6, "lat": 35.8, "lon": 10.7, "hdop": None}
    add(8, "fix_decision(quality 6) → (False, 'receiver dead reckoning (quality 6)')", "fix_decision", (gga6,),
        lambda v: tuple(v) == (False, "receiver dead reckoning (quality 6)"), note="quality 6 is checked first")
    add(8, "fix_decision(quality 1, no latitude) → (False, 'no position')", "fix_decision",
        ({"qual": 1, "lat": None, "lon": 10.7, "hdop": 0.9},), lambda v: tuple(v) == (False, "no position"))
    add(8, "fix_decision(None) → (False, 'not a GGA sentence')", "fix_decision", (None,),
        lambda v: tuple(v) == (False, "not a GGA sentence"))
    add(9, "covariance_from_hdop(0.72) → ([2.0736, 0, 0, 0, 2.0736, 0, 0, 0, 8.2944], 1)", "covariance_from_hdop",
        (0.72,), lambda v: len(v) == 2 and v[1] == 1 and np.allclose(v[0], [2.0736, 0, 0, 0, 2.0736, 0, 0, 0, 8.2944]),
        show=lambda v: repr(v)[:120], note="σ = 2 × HDOP (m) on E and N, 2σ on Up; variances are σ², not σ")
    add(9, "covariance_from_hdop(None) → (nine 0.0, 0)", "covariance_from_hdop", (None,),
        lambda v: len(v) == 2 and v[1] == 0 and list(v[0]) == [0.0] * 9, show=lambda v: repr(v)[:120],
        note="unknown accuracy: type COV_TYPE_UNKNOWN (0), never an invented number")
    add(10, 'fix_state(the line of lesson §3) → ("FIX", "σ 1.4 m")', "fix_state", ({"qual": 1, "lat": 35.734,
        "lon": 10.5758, "hdop": 0.72},), lambda v: tuple(v) == ("FIX", "σ 1.4 m"))
    add(10, 'fix_state(HDOP 20) → ("DEGRADED", "σ 40.0 m > 25.0 m")', "fix_state", ({"qual": 1, "lat": 35.734,
        "lon": 10.5758, "hdop": 20.0},), lambda v: tuple(v) == ("DEGRADED", "σ 40.0 m > 25.0 m"))

    failed = {r[0] for r in rows if not r[2]}
    needs = {4: (2, 3), 7: (6,), 10: (8, 9)}            # a TODO that uses earlier TODOs
    for k, r in enumerate(rows):
        first = [t for t in needs.get(r[0], ()) if t in failed]
        if not r[2] and first:
            rows[k] = r[:4] + ((r[4] + " " if r[4] else "") + f"(fix TODO {first[0]} first: TODO {r[0]} uses it)",)
    last = None
    for todo, label, ok, got, note in rows:
        if todo != last:
            print()
            last = todo
        mark = "✔" if ok else "✘"
        print(f"{mark} TODO {todo:2d}  {label}")
        if not ok:
            print(f"            got: {got}")
            if note:
                print(f"            → {note}")
    done = sum(1 for r in rows if r[2])
    print(f"\n{done} of {len(rows)} lines ✔ (a TODO not written yet shows ✘ \"not written yet\": that is normal).")


# ======================================================================================== log (Step 2)
def log():
    lines = need_log()
    bad = []
    for i, ln in enumerate(lines, 1):
        v, err = rk.call(g, "is_valid", ln)
        if err and "returned None" not in err:
            sys.exit(f"line {i}: {err}")
        if v is None or not isinstance(v, bool):
            sys.exit(f"is_valid() returned {v!r} for line {i}: it must return True or False, for every line.")
        if not v:
            bad.append((i, ln))
    print(f"Your is_valid refused {len(bad)} of {len(lines)} lines:\n")
    for i, ln in bad[:40]:
        print(f"  line {i:5d}  {ln[:74]!r}")
    if len(bad) > 40:
        print(f"  … and {len(bad) - 40} more: far too many — test is_valid on a good line of the log")


# ======================================================================================== forge (Step 5)
def forge(line):
    base = FORGE_BASE
    print(f"original: {base}")
    print(f"forged:   {line}")
    if len(line) != len(base):
        print(f"\n✘ Not the same length ({len(line)} vs {len(base)} characters): a swap keeps the length.")
    diff = [k for k, (a, b) in enumerate(zip(base, line)) if a != b]
    swap = len(diff) == 2 and base[diff[0]] == line[diff[1]] and base[diff[1]] == line[diff[0]]
    print(f"\ncharacters changed at positions {diff[:8]}{' …' if len(diff) > 8 else ''}: "
          + ("one swap of two characters ✔" if swap else "NOT exactly one swap of two characters ✘"))
    v, err = rk.call(g, "is_valid", line)
    stop_if_err(err)
    print(f"your is_valid:   {v}")
    p, err = rk.call(g, "parse_gga", line)
    if err and "returned None" in err and v is False:
        print("your parse_gga:  None (correct: the line is refused). The forgery did not get through: try another swap.")
        return
    if err:
        print(f"your parse_gga:  {err}")
        return
    p0, _ = rk.call(g, "parse_gga", base)
    print(f"your parse_gga:  lat {p.get('lat')}, lon {p.get('lon')}, quality {p.get('qual')}")
    s, err = rk.call(g, "fix_state", p)
    if not err:
        print(f"your fix_state:  {s}")
    if p.get("lat") is not None and p.get("lon") is not None and p0 and p0.get("lat") is not None:
        d = geo.haversine_m(p0["lat"], p0["lon"], p["lat"], p["lon"])
        print(f"\nthe position moved by {d / 1000:.3f} km" + ("  ✔ more than 1 km" if d > 1000 else "  (not 1 km yet)"))
    else:
        print("\nyour parser refused the position: the forgery did not get through. Try other characters.")


# ======================================================================================== sky (Step 6)
def show_dops(label, az, el):
    d, err = rk.call(g, "dops", az, el)
    if err and "returned None" in err:
        print(f"  {label:44s} None")
        return None
    stop_if_err(err)
    print(f"  {label:44s} " + "  ".join(f"{k} {d[k]:6.2f}" for k in ("HDOP", "VDOP", "EDOP", "NDOP")))
    return d


def sky():
    ex_az, ex_el = [0, 90, 180, 270, 0], [30, 30, 30, 30, 90]
    open_az, open_el = [10, 80, 150, 200, 300, 250], [15, 50, 35, 70, 25, 60]
    st_az, st_el = [5, 350, 175, 190, 120, 260], [30, 55, 40, 65, 75, 80]
    print("1. The lesson's sky, then without the satellite overhead")
    show_dops("4 at 30° (N, E, S, W) + 1 overhead", ex_az, ex_el)
    show_dops("the same without the overhead one", ex_az[:4], ex_el[:4])
    print("\n2. An open sky of 6 satellites, then the same sky turned by 37° in azimuth")
    show_dops("open sky", open_az, open_el)
    show_dops("open sky turned by 37°", [a + 37 for a in open_az], open_el)
    print("\n3. A street running north–south: only the sky along the street, and near the zenith")
    show_dops("north–south street", st_az, st_el)
    print("\n4. The open sky with a 7th satellite, low in the east-south-east")
    show_dops("open sky + 1 low satellite", open_az + [110], open_el + [12])
    plt = rk.plt_or_none()
    if plt is None:
        return
    import numpy as np
    os.makedirs(OUT, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), subplot_kw={"projection": "polar"})
    for ax, (title, az, el) in zip(axes, [("lesson §5", ex_az, ex_el), ("open sky", open_az, open_el),
                                          ("north–south street", st_az, st_el)]):
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_rlim(0, 90)
        ax.set_yticks([30, 60, 90])
        ax.set_yticklabels(["60°", "30°", "0°"], fontsize=8)
        ax.plot(np.radians(az), [90 - e for e in el], "o", ms=10, color="#0b6e8a")
        ax.set_title(title)
    fig.suptitle("Sky plots, drawn like a map (north up, east right): centre = straight up, edge = horizon")
    fig.tight_layout()
    fig.savefig(f"{OUT}/sky.png", dpi=90)
    rk.saved(f"{OUT}/sky.png")


# ======================================================================================== the drive, second by second
def seconds_of(lines):
    """Group the log into seconds: {t: {"gga": dict|None, "gsa": dict|None, "sats": {prn: (el, az)}}}.
    A second starts with its GGA or RMC (their UTC time); GSA and GSV lines belong to the last second seen."""
    for i, ln in enumerate(lines, 1):                     # the given fields() calls your is_valid: test it first
        v, err = rk.call(g, "is_valid", ln)
        if err:
            sys.exit(f"line {i} of the log: {err}")
    secs, cur = {}, None
    for ln in lines:
        f = g.fields(ln)
        if f is None:
            continue
        kind = f[0][-3:]
        if kind in ("GGA", "RMC"):
            t = g.utc_seconds(f[1]) if len(f) > 1 else None
            if t is None:
                continue
            cur = int(round(t))
            sec = secs.setdefault(cur, {"gga": None, "gsa": None, "sats": {}, "gsv1": False})
            if kind == "GGA":
                p, err = rk.call(g, "parse_gga", ln)
                stop_if_err(err)
                sec["gga"] = p
        elif cur is not None and kind == "GSA":
            p, err = rk.call(g, "parse_gsa", ln)
            stop_if_err(err)
            if secs[cur]["gsa"] is None:
                secs[cur]["gsa"] = p
        elif cur is not None and kind == "GSV":
            p = g.parse_gsv(ln)
            if p["msg"] == 1 and secs[cur]["gsv1"]:          # a new second whose GGA and RMC were lost
                cur += 1
                secs.setdefault(cur, {"gga": None, "gsa": None, "sats": {}, "gsv1": False})
            secs[cur]["gsv1"] = secs[cur]["gsv1"] or p["msg"] == 1
            for prn, el, az, _ in p["sats"]:
                if el is not None and az is not None:
                    secs[cur]["sats"][prn] = (el, az)
    return secs


def dop():
    lines = need_log()
    secs = seconds_of(lines)
    rows, none_count, skipped = [], 0, 0
    for t in sorted(secs):
        s = secs[t]
        gsa = s["gsa"]
        if not gsa or gsa.get("mode") != 3 or gsa.get("hdop") is None:
            continue
        if any(p not in s["sats"] for p in gsa["prns"]):
            skipped += 1                                     # a GSV line of this second was damaged
            continue
        el = [s["sats"][p][0] for p in gsa["prns"]]
        az = [s["sats"][p][1] for p in gsa["prns"]]
        d, err = rk.call(g, "dops", az, el)
        if err and "returned None" in err:
            none_count += 1
            continue
        stop_if_err(err)
        rows.append((t, len(az), gsa["hdop"], d["HDOP"], gsa["pdop"], d["PDOP"], gsa["vdop"], d["VDOP"]))
    if not rows:
        sys.exit("No second could be compared: are parse_gsa (TODO 5) and dops (TODO 7) written?")
    dh = max(abs(r[2] - r[3]) for r in rows)
    dp = max(abs(r[4] - r[5]) for r in rows)
    dv = max(abs(r[6] - r[7]) for r in rows)
    print(f"Seconds compared: {len(rows)} (skipped: {skipped} with a damaged GSV line; your dops() said None: "
          f"{none_count}).")
    print(f"Largest difference, yours vs the receiver's:  HDOP {dh:.4f}   PDOP {dp:.4f}   VDOP {dv:.4f}")
    if max(dh, dp, dv) > 0.006:
        print("⚠ More than the 2-decimal rounding (0.005): your geometry is not the receiver's. Does parse_gsa keep all "
              "12 PRN slots (f[3] to f[14])? Do geometry_matrix and dops pass `test`?")
    big = max(rows, key=lambda r: r[3])
    print(f"Largest HDOP of the drive: {big[3]:.2f} at {hms(big[0])} ({big[1]} satellites; the receiver wrote {big[2]})")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs(OUT, exist_ok=True)
    t0 = rows[0][0]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    a1.plot([(r[0] - t0) / 60 for r in rows], [r[3] for r in rows], ".", ms=3, color="#0b6e8a", label="your HDOP")
    a1.plot([(r[0] - t0) / 60 for r in rows], [r[7] for r in rows], ".", ms=3, color="#b07a3a", label="your VDOP")
    a1.axhline(12.5, color="#d64545", lw=1, ls="--", label="HDOP 12.5 (σ = 25 m)")
    a1.set_yscale("log")
    a1.set_ylabel("DOP")
    a1.legend(loc="upper left")
    a2.plot([(r[0] - t0) / 60 for r in rows], [r[1] for r in rows], ".", ms=3, color="0.3")
    a2.set_ylabel("satellites used")
    a2.set_xlabel("minutes since the first fix")
    fig.suptitle("The drive's geometry, second by second (synthetic log)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/dop_timeline.png", dpi=90)
    rk.saved(f"{OUT}/dop_timeline.png")


def drive():
    lines = need_log()
    bad = 0
    for ln in lines:
        v, err = rk.call(g, "is_valid", ln)
        stop_if_err(err)
        bad += not v
    secs = seconds_of(lines)
    truth = truth_by_second()
    t_all = range(min(secs), max(secs) + 1)
    states, reasons, positions = {}, {}, {}
    for t in t_all:
        gga = secs.get(t, {}).get("gga")
        st, err = rk.call(g, "fix_state", gga)
        stop_if_err(err)
        if not (isinstance(st, (tuple, list)) and len(st) == 2):
            sys.exit(f"fix_state() must return (state, reason), two str — it returned {st!r}")
        state, why = st
        if gga is None:
            why = "no valid GGA this second"
        states[t] = state
        if state != "FIX":
            reasons[why] = reasons.get(why, 0) + 1
        if state in ("FIX", "DEGRADED"):
            cov, _ = g.covariance_from_hdop(gga["hdop"])
            positions[t] = (gga["lat"], gga["lon"], math.sqrt(cov[0]) if cov[0] > 0 else None)
    count = {k: sum(1 for s in states.values() if s == k) for k in ("FIX", "DEGRADED", "NO_FIX")}
    print(f"Lines refused by your is_valid: {bad}")
    print(f"Seconds of the drive: {len(states)}   FIX {count['FIX']}   DEGRADED {count['DEGRADED']}   "
          f"NO_FIX {count['NO_FIX']}")
    print("Why not FIX (seconds):")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {why}")
    sig = [(p[2], -t) for t, p in positions.items() if p[2] is not None]
    smax = max(sig) if sig else (None, None)
    smax = (smax[0], -smax[1]) if sig else smax              # the first second with the largest σ
    if sig:
        print(f"Largest σ your stack stated: {smax[0]:.1f} m at {hms(smax[1])}")
    # mission 01's jump gate (last trusted position, elapsed time), run on what your gnss part let through
    jumps, trusted = [], None
    for t in sorted(positions):
        if trusted is not None:
            d = geo.haversine_m(positions[trusted][0], positions[trusted][1], positions[t][0], positions[t][1])
            if d > GATE_V_MPS * (t - trusted) + GATE_MARGIN_M:
                jumps.append((t, d, t - trusted))
                continue                                  # refused: never becomes the trusted position
        trusted = t
    print(f"\nPositions your gnss part let through that mission 01's jump gate (100 m/s, 50 m) refuses: {len(jumps)}")
    for t, d, dt in jumps:
        print(f"  {hms(t)}  {d:8.1f} m from the last trusted position, {dt} s later")
    errs = [(geo.haversine_m(p[0], p[1], *truth[t]), t) for t, p in positions.items()
            if t in truth and states[t] == "FIX"]
    if errs:
        e, t = max(errs)
        print(f"Largest error of a FIX position (vs the true track): {e:.1f} m at {hms(t)}, "
              f"stated σ {positions[t][2]:.1f} m")
    res = {"lines": len(lines), "bad_lines": bad, "seconds": len(states), "fix": count["FIX"],
           "degraded": count["DEGRADED"], "no_fix": count["NO_FIX"], "not_fix_reasons": reasons,
           "sigma_max_m": round(smax[0], 1) if sig else None,
           "jumps_utc": [hms(t) for t, _, _ in jumps], "worst_fix_error_m": round(max(errs)[0], 1) if errs else None}
    with open("results.json", "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print("\nresults.json written.")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs(OUT, exist_ok=True)
    lat0, lon0 = 35.8270, 10.6420
    fig, ax = plt.subplots(figsize=(11, 6.5))
    te = [geo.enu_flat(lat0, lon0, *truth[t]) for t in sorted(truth)]
    ax.plot([e / 1000 for e, _ in te], [n / 1000 for _, n in te], "-", color="0.75", lw=5, label="truth")
    colours = {"FIX": "#2f7a2f", "DEGRADED": "#e09b2d"}
    for state, col in colours.items():
        pts = [geo.enu_flat(lat0, lon0, p[0], p[1]) for t, p in positions.items() if states[t] == state]
        ax.plot([e / 1000 for e, _ in pts], [n / 1000 for _, n in pts], ".", ms=3, color=col, label=state)
    nofix = [geo.enu_flat(lat0, lon0, *truth[t]) for t in states if states[t] == "NO_FIX" and t in truth]
    ax.plot([e / 1000 for e, _ in nofix], [n / 1000 for _, n in nofix], "x", ms=5, color="#d64545",
            label="NO_FIX (drawn on the true track)")
    ax.set_xlim(-1, 21)
    ax.set_ylim(-9, 3)
    ax.set_aspect("equal")
    ax.set_xlabel("east of the start (km)")
    ax.set_ylabel("north of the start (km)")
    ax.legend(loc="upper right")
    ax.set_title("Your judge on the drive, Sousse port → Monastir (synthetic log)")
    fig.tight_layout()
    fig.savefig(f"{OUT}/drive.png", dpi=90)
    rk.saved(f"{OUT}/drive.png")


MODES = {"naive": naive, "test": test, "log": log, "sky": sky, "dop": dop, "drive": drive}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "forge":
        a = rk.load_student("answers")
        line = getattr(a, "FORGED_LINE", "")
        if not isinstance(line, str) or not line.strip():
            sys.exit("FORGED_LINE in answers.py is still empty: copy the original line there, swap two characters, "
                     "save (Ctrl+S) and run again.")
        forge(line.strip())
    elif mode in MODES:
        MODES[mode]()
    else:
        print(__doc__)
