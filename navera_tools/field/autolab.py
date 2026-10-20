#!/usr/bin/env python3
"""Expert routines that start by themselves when a 360 test records, and improve it while the car drives.

    python3 -m navera_tools.field.autolab [--root ~/navera-field]     (run_field.sh starts it next to the server)

No Claude session and no internet needed: it runs on the Jetson from START to END. At T+10, T+25 and T+40 min
(ROUNDS_MIN) it replays the last LAST_MIN minutes of the raw recording (live_lab: the live folder is only read)
with the settings in use and with a few preset expert variants (VARIANTS, two new ones per round, in turn),
scores each against the phone's GPS, and applies at most one change per round to the live server (livectl's
live_params.json, by "autolab"), only if it wins on the real data (accept(), below). A change that scores worse
than the defaults at a later round is reverted. At END: one report-only round, and any change it made is
removed so the next test starts from the defaults. Never touches the tilt calibration.

One replay at a time, nice 19, so the live solver keeps its CPU; a round waits while the load average is above
MAX_LOAD or the median solve time of the last 5 min is above MAX_SOLVE_S. Every decision: an 'autolab' event in
the test's events.jsonl, <test>/autolab_round_N.md, a line in ~/navera-field/AUTOLAB.txt (shown in STATUS.txt)
and in ALERTS.log. Off with NAVERA_AUTOLAB=0 or the file ~/navera-field/autolab_off.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ROUNDS_MIN = (10.0, 25.0, 40.0)        # minutes after START
LAST_MIN = 5.0                         # minutes replayed per round (a replay takes about as long as what it replays)
NEW_PER_ROUND = 2                      # variants tried per round
MAX_LOAD = 4.0
MAX_SOLVE_S = 5.0
MEDIAN_TOL_KM = 0.5
WRONG_KM = 50.0
POLL_S = 30.0

# The preset expert variants, most promising first (each: module constants live_lab --set and livectl accept).
# Stars: a lower detection threshold / more spots / fewer stars needed find more stars on a hazy or bright sky;
# the opposite cut junk (lights, clouds). Stillness: a looser test gets more stops in an idling car, a tighter one
# refuses fooled stops. The tilt calibration (server.CAL_*) is never a variant.
VARIANTS = (
    ("k5", {"allsky.DETECT_K_SIGMA": 5.0}),
    ("stars8", {"server.MIN_STARS": 8}),
    ("spots80", {"allsky.LOCATE_MAX_SPOTS": 80}),
    ("still_loose", {"insta360_usb.STILL_ACC_STD_G": 0.0045, "insta360_usb.STILL_RATE_DPS": 0.8}),
    ("rms015", {"allsky.MAX_RMS_DEG": 0.15}),
    ("k8", {"allsky.DETECT_K_SIGMA": 8.0}),
    ("spots40", {"allsky.LOCATE_MAX_SPOTS": 40}),
    ("stars10", {"server.MIN_STARS": 10}),
    ("still_tight", {"insta360_usb.STILL_ACC_STD_G": 0.002, "insta360_usb.STILL_RATE_DPS": 0.3}),
)


# ── when ──────────────────────────────────────────────────────────────────────
def enabled(root, env=None):
    env = os.environ if env is None else env
    return env.get("NAVERA_AUTOLAB", "1") != "0" and not os.path.exists(os.path.join(root, "autolab_off"))


def due_round(started, now, done, rounds=ROUNDS_MIN):
    """Index of the newest round whose time has come and that is not done, or None."""
    due = [i for i, m in enumerate(rounds) if now - started >= 60.0 * m and i not in done]
    return due[-1] if due else None


def round_variants(k, applied=None):
    """The NEW_PER_ROUND variants for round k, in turn through VARIANTS (the one in use is skipped)."""
    pool = [v for v in VARIANTS if not applied or v[0] != applied.get("name")]
    start = (k * NEW_PER_ROUND) % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(min(NEW_PER_ROUND, len(pool)))]


def busy(folder, now):
    """Why the live test needs the CPU now (load, slow solves), or None."""
    load = os.getloadavg()[0]
    if load > MAX_LOAD:
        return f"load {load:.1f} > {MAX_LOAD}"
    from navera_tools.field.supervisor import read_jsonl
    ss = sorted(f["solve_s"] for f in read_jsonl(os.path.join(folder, "frames.jsonl"), tail=400_000)
                if isinstance(f, dict) and isinstance(f.get("solve_s"), (int, float)) and now - f.get("t", 0) <= 300)
    if ss and ss[len(ss) // 2] > MAX_SOLVE_S:
        return f"median solve {ss[len(ss) // 2]:.1f} s > {MAX_SOLVE_S}"
    return None


# ── which ─────────────────────────────────────────────────────────────────────
def _block(s):
    """The error block to judge on: tilt-corrected when there are corrected fixes, else raw."""
    return s["corrected"] if s["corrected"]["n"] else s["raw"]


def _outside(b):
    return b["n"] - b["within_3sigma"]


def accept(cand, base):
    """None if cand may replace base, else why not. MORE trusted fixes, corrected median not worse (+0.5 km),
    p90 not worse, ZERO fixes > 50 km, no more fixes outside 3 sigma than the baseline."""
    if cand is None:
        return "replay failed"
    if cand["raw"]["wrong"] or cand["corrected"]["wrong"]:
        return f"{cand['raw']['wrong'] + cand['corrected']['wrong']} fix(es) > {WRONG_KM:.0f} km"
    if cand["trusted"] <= base["trusted"]:
        return f"trusted fixes {cand['trusted']} not more than {base['trusted']}"
    cb, bb = _block(cand), _block(base)
    if bb["err_km_p50_p90_max"] and cb["err_km_p50_p90_max"]:
        (c50, c90, _), (b50, b90, _) = cb["err_km_p50_p90_max"], bb["err_km_p50_p90_max"]
        if c50 > b50 + MEDIAN_TOL_KM:
            return f"median {c50} km worse than {b50}"
        if c90 > b90:
            return f"p90 {c90} km worse than {b90}"
    if _outside(cb) > _outside(bb):
        return f"{_outside(cb)} fixes outside 3 sigma (baseline {_outside(bb)})"
    return None


def worse(cur, ref):
    """Why the configuration in use scores worse than the reference (then it is reverted), or None."""
    if cur is None:
        return None                                   # no evidence: keep
    if cur["raw"]["wrong"] + cur["corrected"]["wrong"] > ref["raw"]["wrong"] + ref["corrected"]["wrong"]:
        return "more fixes > 50 km than the defaults"
    if cur["trusted"] < ref["trusted"]:
        return f"fewer trusted fixes ({cur['trusted']} < {ref['trusted']})"
    cb, rb = _block(cur), _block(ref)
    if rb["err_km_p50_p90_max"] and cb["err_km_p50_p90_max"]:
        if cb["err_km_p50_p90_max"][0] > rb["err_km_p50_p90_max"][0] + MEDIAN_TOL_KM:
            return "median worse than the defaults"
        if cb["err_km_p50_p90_max"][1] > rb["err_km_p50_p90_max"][1] + MEDIAN_TOL_KM:
            return "p90 worse than the defaults"
    if _outside(cb) > _outside(rb):
        return "more fixes outside 3 sigma than the defaults"
    return None


def decide(scores, applied):
    """scores: {run name: score or None}; 'current' = the settings in use ('baseline' when nothing is applied),
    'baseline' = the defaults, other names = variants. Returns (action, name, reason): ('revert', applied name,
    why) | ('apply', variant, why) | ('keep', None, why)."""
    base = scores.get("baseline")
    cur = scores.get("current", base) if applied else base
    if base is None or cur is None:
        return "keep", None, "no baseline score (replay failed)"
    if applied:
        why = worse(cur, base)
        if why:
            return "revert", applied["name"], why        # one change per round: nothing else this round
    best, best_s, notes = None, None, []
    for name, s in scores.items():
        if name in ("baseline", "current"):
            continue
        why = accept(s, cur)
        notes.append(f"{name}: {why or 'better'}")
        if why is None and (best_s is None or s["trusted"] > best_s["trusted"]):
            best, best_s = name, s
    if best:
        return "apply", best, "; ".join(notes)
    return "keep", None, "; ".join(notes) or "no variant"


# ── doing ─────────────────────────────────────────────────────────────────────
def run_lab(folder, out, runs, last_min, jobs=1):
    """live_lab on the test so far: {name: score or None}. runs: [(name, {key: value})]; 'baseline' = defaults."""
    cmd = [sys.executable, "-m", "navera_tools.field.live_lab", folder, "--out", out, "--jobs", str(jobs)]
    if last_min:
        cmd += ["--last-min", str(last_min)]
    for name, sets in runs:
        if name != "baseline":
            cmd += ["--variant", name + ":" + ",".join(f"{k}={json.dumps(v)}" for k, v in sets.items())]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "navera_common"),
                                                        os.path.join(ROOT, "cn_pkg"), os.environ.get("PYTHONPATH", "")]))
    p = subprocess.run(["nice", "-n", "19"] + cmd, capture_output=True, text=True, env=env, cwd=ROOT, timeout=5400)
    try:
        lab = json.load(open(os.path.join(out, "lab.json")))
    except (OSError, ValueError):
        raise RuntimeError(f"live_lab failed (rc {p.returncode}): {p.stderr[-400:]}")
    return {r["name"]: r.get("score") for r in lab.get("runs", [])}


def set_live(root, add=None, remove=()):
    """Change live_params.json (atomically, by autolab); the server applies it within a second."""
    from navera_tools.field import livectl
    path = os.path.join(root, livectl.LIVE_PARAMS_FILE)
    cur = livectl.read_file(path)
    if add:
        new, bad = livectl.parse_sets([f"{k}={json.dumps(v)}" for k, v in add.items()])
        if bad:
            raise ValueError(f"refused by the server's ranges: {bad}")
        cur.update(new)
    for k in remove:
        cur.pop(k, None)
    cur["_by"] = "autolab"
    livectl.write_file(path, cur)


def append_event(folder, **rec):
    """One 'autolab' line in the test's events.jsonl (a single O_APPEND write: no interleaving with the server)."""
    line = (json.dumps({"t": time.time(), "kind": "autolab", **rec}, default=str, separators=(",", ":")) + "\n").encode()
    fd = os.open(os.path.join(folder, "events.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def note(root, text):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(root, "AUTOLAB.txt"), "a") as f:
        f.write(f"{stamp} {text}\n")
    with open(os.path.join(root, "ALERTS.log"), "a") as f:
        f.write(f"{stamp} AUTOLAB {text}\n")


def _fmt(s):
    if not s:
        return "replay failed"
    b = _block(s)
    e = b["err_km_p50_p90_max"]
    return (f"{s['trusted']} trusted, err km p50/p90/max {'/'.join(map(str, e)) if e else '-'}, "
            f"wrong {s['raw']['wrong'] + s['corrected']['wrong']}, outside 3σ {_outside(b)}")


def load_state(folder):
    try:
        return json.load(open(os.path.join(folder, "autolab_state.json")))
    except (OSError, ValueError):
        return {"done": [], "applied": None, "end_done": False}


def save_state(folder, st):
    tmp = os.path.join(folder, "autolab_state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, os.path.join(folder, "autolab_state.json"))


def do_round(root, folder, k, st, lab=run_lab, final=False):
    """One round: replay, score, decide, apply (live rounds only), report. Returns the decision dict."""
    applied = st.get("applied")
    runs = [("baseline", {})]
    if applied:
        runs.append(("current", applied["sets"]))
    runs += list(VARIANTS) if final else round_variants(k, applied)
    out = os.path.join(folder, "autolab", f"round_{k + 1}" if not final else "end")
    scores = lab(folder, out, runs, None if final else LAST_MIN, 2 if final else 1)
    action, name, why = decide(scores, applied) if not final else ("report", None, "END: report only")
    sets = dict(VARIANTS).get(name, {}) if action == "apply" else {}
    if action == "revert":
        set_live(root, remove=list(applied["sets"]))
        st["applied"] = None
    elif action == "apply":
        set_live(root, add=sets, remove=[x for x in (applied or {}).get("sets", {}) if x not in sets])
        st["applied"] = {"name": name, "sets": sets, "round": k + 1}
    rec = {"round": "end" if final else k + 1, "action": action, "variant": name, "sets": sets, "reason": why,
           "scores": {n: _fmt(s) for n, s in scores.items()}}
    append_event(folder, **rec)
    title = "END (report only)" if final else f"round {k + 1}"
    lines = [f"# autolab {title} — {os.path.basename(folder)}", "",
             f"Replayed: {'the whole test' if final else f'the last {LAST_MIN:g} min'}; decision: **{action}**"
             + (f" {name}" if name else "") + f" ({why})", "", "| run | settings | score |", "|---|---|---|"]
    for n, s in scores.items():
        st_sets = applied["sets"] if n == "current" and applied else dict(VARIANTS).get(n, {})
        lines.append(f"| {n} | {json.dumps(st_sets) if st_sets else 'defaults'} | {_fmt(s)} |")
    with open(os.path.join(folder, f"autolab_round_{'end' if final else k + 1}.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    note(root, f"{os.path.basename(folder)} {title}: {action}" + (f" {name} {json.dumps(sets)}" if name else "")
         + f" — {why[:200]}")
    return rec


def step(root, now=None, lab=run_lab):
    """One look at the newest test: run the round that is due, or the END round. Never raises."""
    from navera_tools.field.supervisor import newest_session
    now = time.time() if now is None else now
    try:
        if not enabled(root):
            return None
        folder = newest_session(root)
        if not folder:
            return None
        meta = json.load(open(os.path.join(folder, "session.json")))
        if meta.get("mode") != "360" or not os.path.isdir(os.path.join(folder, "raw")):
            return None
        st = load_state(folder)
        if meta.get("ended"):
            if st.get("end_done"):
                return None
            st["end_done"] = True
            if st.get("applied"):                    # the next test starts from the defaults
                set_live(root, remove=list(st["applied"]["sets"]))
                append_event(folder, action="removed at END", variant=st["applied"]["name"])
                note(root, f"{os.path.basename(folder)} END: removed {st['applied']['name']}")
                st["applied"] = None
            save_state(folder, st)
            if now - meta["ended"] < 3600:           # report round only right after the test
                return do_round(root, folder, len(ROUNDS_MIN), st, lab, final=True)
            return None
        k = due_round(meta["started"], now, st["done"])
        if k is None:
            return None
        why = busy(folder, now)
        if why:
            if st.get("waiting") != k:
                st["waiting"] = k
                save_state(folder, st)
                note(root, f"{os.path.basename(folder)} round {k + 1} waits: {why}")
            return None
        st["done"].append(k)
        save_state(folder, st)
        rec = do_round(root, folder, k, st, lab)
        save_state(folder, st)
        return rec
    except Exception as e:                          # never stops: the supervisor and the test go on
        try:
            note(root, f"error: {e!r}"[:300])
        except OSError:
            pass
        return {"action": "error", "reason": repr(e)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field")))
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    while True:
        step(a.root)
        if a.once:
            return 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
