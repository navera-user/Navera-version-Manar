"""project.py — the measuring bench of your final project (mission 33): it flies a PRE-REGISTERED campaign on a
COMMITTED version of your NAVERA Lite, before and after your change, and judges the paired difference with a
confidence interval and the decision rule you wrote first. You do not need to change this file (the check
compares it with the given one); your work is in navera_lite/, your test, project.json and REPORT.md.

    python3 project.py plan                 read project.json: is it complete? the decision rule in words
    python3 project.py red                  your test FAILS on the committed code, the rest of the suite passes
    python3 project.py campaign before      fly every scenario × seed from the commit tagged "before" → runs/before/
    python3 project.py green                your test PASSES on the committed code (HEAD), and the whole suite
    python3 project.py campaign after       the same campaign from HEAD (your change, committed) → runs/after/
    python3 project.py evaluate             metric of every run, paired difference, 95 % CI, decision
                                            → evaluation.json and out/project.png
    python3 project.py status               what is done, what comes next
    python3 project.py one campaign/jam.json 101    fly ONE run of the working folder (exploring) → my_runs/
    python3 project.py metrics my_runs/jam_s101.csv campaign/jam.json   every metric of one run

Explore with seeds below 1000 (`one`), pre-register a block of seeds of 1000 or more that you never flew. Every
'after' campaign and every evaluation is written in runs/journal.txt: report each change you evaluated.

Why commits: a campaign flies the code of a COMMIT (git archive), never your unsaved files, so that "before" and
"after" are exactly two versions of the stack that anyone can rebuild from your branch. runs/ is not committed
(runs/.gitignore): the runs are evidence you can regenerate, not source.
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import csv
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
LABELS = {"before": "before", "after": "HEAD"}          # label → the git revision it flies
METRICS = {
    # name: (what it measures, unit, kind, natural direction)  kind "share": a fraction 0–1; "event": 0 or 1
    "err_median": ("median of NAVERA Lite's error (lite_err_m) over the window's rows with a position", "m", "value", "lower"),
    "err_p90": ("90th percentile (linear rule) of NAVERA Lite's error over the window", "m", "value", "lower"),
    "err_p95": ("95th percentile (linear rule) of NAVERA Lite's error over the window", "m", "value", "lower"),
    "err_max": ("largest NAVERA Lite error in the window", "m", "value", "lower"),
    "ap_err_median": ("median of the autopilot's error (ap_err_m) over the window", "m", "value", "lower"),
    "ap_err_p95": ("95th percentile of the autopilot's error over the window", "m", "value", "lower"),
    "ap_err_max": ("largest autopilot error in the window: what the vehicle really suffered", "m", "value", "lower"),
    "availability": ("share of the window's rows with a usable position (FIX or DEGRADED)", "", "share", "higher"),
    "fix_share": ("share of the window's rows in FIX", "", "share", "higher"),
    "honest2": ("share of the rows with a position AND a stated σ whose error is ≤ 2 × lite_sigma_m "
                "(an honest round 2-D Gaussian: 0.86)", "", "share", "closer"),
    "bad_fix": ("share of the window's rows in FIX whose error is > 3 × the stated σ (a FIX the judge should not "
                "have claimed)", "", "share", "lower"),
    "failsafe": ("1 if the autopilot went to failsafe (LAND / HOLD) during the run, else 0", "", "event", "lower"),
    "detected": ("1 if NAVERA Lite stopped flying on the GPS during the window, else 0", "", "event", "higher"),
    "detect_s": ("seconds from the window's start to the first row NOT flown on the GPS (undefined if it never "
                 "happens: then use 'detected')", "s", "value", "lower"),
    "false_alarm": ("1 if NAVERA Lite left an honest GPS (rows before any GPS fault, after 5 s), else 0", "", "event",
                    "lower"),
    "custom": ("your own metric: metric(rows, scenario) in my_metric.py, one number per run", "", "value", None),
}
NUMERIC = ("t_s", "lite_sigma_m", "lite_err_m", "gps_err_m", "vis_err_m", "ap_err_m", "truth_speed_mps")
STACK = ("navera_lite", "navera_lite.yaml", "ref_desc.pt", "ref_homography.pt", "campaign", "project.json",
         "my_metric.py", "my_vision_profile.json")
MIN_RUNS, MAX_RUNS = 20, 300


def die(msg):
    sys.exit("✘ " + msg)


# ------------------------------------------------------------------------------------------------ git helpers
def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)
    if check and r.returncode:
        die(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def is_repo():
    return os.path.isdir(os.path.join(HERE, ".git"))


def need_repo():
    if not is_repo():
        die("this folder is not a git repository yet: bash navera_lite/tools/init_repo.sh (lab Step 1)")


def sha_of(rev):
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", rev + "^{commit}"], cwd=HERE, capture_output=True,
                       text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def branch():
    r = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=HERE, capture_output=True, text=True)
    return r.stdout.strip()


def dirty_stack():
    """Uncommitted changes in the files a campaign flies (the stack, the settings, the scenarios, project.json)."""
    out = git("status", "--porcelain", "--untracked-files=all", "--", *[p for p in STACK if os.path.exists(
        os.path.join(HERE, p))] or ["."])
    return [ln.split(None, 1)[1] for ln in out.splitlines() if ln.strip() and "__pycache__" not in ln
            and ".pytest_cache" not in ln and ".hypothesis" not in ln]


def extract(sha):
    """The whole committed folder at `sha`, unpacked in runs/.code/<sha12>/ (git archive): what a campaign flies."""
    dst = os.path.join(RUNS, ".code", sha[:12])
    if os.path.isdir(dst):
        return dst
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=HERE, capture_output=True).stdout
    tmp = dst + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(tmp)
    os.replace(tmp, dst)
    return dst


def ensure_runs_ignored():
    os.makedirs(RUNS, exist_ok=True)
    gi = os.path.join(RUNS, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w") as f:
            f.write("# runs are regenerated from commits by project.py: never committed\n*\n")


def env_for(code_dir):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    keep = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p.startswith("/opt/ros/")]
    env["PYTHONPATH"] = os.pathsep.join([code_dir] + keep)
    return env


# ------------------------------------------------------------------------------------------------ project.json
def load_project(path=None, text=None):
    """project.json read and checked: every mistake reported in words. Returns the dict (seeds expanded)."""
    path = path or os.path.join(HERE, "project.json")
    try:
        if text is None:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        p = json.loads(text)
    except OSError:
        die(f"{path} is missing")
    except ValueError as e:
        die(f"project.json is not valid JSON: {e} (look at commas and quotes near that line; no comments in JSON)")
    if not isinstance(p, dict):
        die("project.json must be one object {...}")
    problems = []
    for key in ("title", "hypothesis", "idea", "kind", "test", "scenarios", "seeds", "metric", "better"):
        if key not in p:
            problems.append(f'"{key}" is missing')
    if problems:
        die("project.json: " + "; ".join(problems))
    if not isinstance(p["title"], str) or len(p["title"].split()) < 3 or "(fill in" in p["title"]:
        problems.append('"title": a short sentence that names your change (3 words or more)')
    hy = p["hypothesis"]
    if not isinstance(hy, str) or len(hy.split()) < 6 or "(fill in" in hy:
        problems.append('"hypothesis": one sentence the measurement can prove wrong (6 words or more), written now')
    if not (p["idea"] == "own" or (isinstance(p["idea"], int) and not isinstance(p["idea"], bool)
                                   and 1 <= p["idea"] <= 10)):
        problems.append('"idea": a number 1–10 from the lesson\'s menu, or "own" (agreed with your teacher)')
    if p["kind"] not in ("stack", "sim"):
        problems.append('"kind": "stack" (you change NAVERA Lite) or "sim" (you change the simulator\'s model)')
    t = p["test"]
    if not (isinstance(t, str) and t.startswith("navera_lite/tests/test_") and t.endswith(".py") and "/" not in t[18:]):
        problems.append('"test": the file of your red test, like "navera_lite/tests/test_my_change.py"')
    sc = p["scenarios"]
    if not (isinstance(sc, list) and sc and all(isinstance(s, str) and s.endswith(".json") for s in sc)
            and len(set(sc)) == len(sc)):
        problems.append('"scenarios": a list of scenario files, like ["campaign/jam.json", "campaign/blind.json"]')
    s = p["seeds"]
    if not (isinstance(s, dict) and set(s) == {"first", "count"}
            and all(isinstance(s[k], int) and not isinstance(s[k], bool) for k in s) and s["first"] >= 0):
        problems.append('"seeds": {"first": 101, "count": 20} — a block of consecutive seeds chosen in advance')
    m = p["metric"]
    if not (isinstance(m, dict) and m.get("name") in METRICS):
        problems.append('"metric": {"name": one of ' + ", ".join(METRICS) + ', "window": "fault" | "all" | [t0, t1]}')
    else:
        problems += check_window(m, "metric") + check_subset(m, sc, "metric")
        nat = METRICS[m["name"]][3]
        if nat and p["better"] != nat:
            problems.append(f'"better": {m["name"]} is better when "{nat}"'
                            + (' (with a "target", e.g. 0.86)' if nat == "closer" else ""))
    if p["better"] not in ("lower", "higher", "closer"):
        problems.append('"better": "lower", "higher" or "closer" (closer to "target")')
    if p["better"] == "closer" and not isinstance(p.get("target"), (int, float)):
        problems.append('"better": "closer" needs a "target" (a number, e.g. 0.86 for honest2)')
    me = p.get("min_effect", 0.0)
    if not isinstance(me, (int, float)) or isinstance(me, bool) or me < 0:
        problems.append('"min_effect": a number ≥ 0 (the smallest gain that matters, in the metric\'s unit)')
    g = p.get("guardrail")
    if g is not None:
        if not (isinstance(g, dict) and isinstance(g.get("metric"), dict) and g["metric"].get("name") in METRICS
                and g.get("better") in ("lower", "higher") and isinstance(g.get("max_loss"), (int, float))
                and not isinstance(g.get("max_loss"), bool) and g["max_loss"] >= 0):
            problems.append('"guardrail": {"metric": {"name": …, "window": …}, "better": "lower" | "higher", '
                            '"max_loss": a number ≥ 0} — or null for none')
        else:
            problems += check_window(g["metric"], "guardrail metric") + check_subset(g["metric"], sc, "guardrail metric")
            gn = METRICS[g["metric"]["name"]][3]
            if gn in ("lower", "higher") and g["better"] != gn:
                problems.append(f'guard-rail "better": {g["metric"]["name"]} is better when "{gn}" (not your choice)')
            if gn == "closer":
                problems.append(f'guard-rail: {g["metric"]["name"]} has a target — use it as the metric, not as a '
                                'guard-rail')
    for key, lo, hi, default in (("B", 500, 20000, 2000), ("alpha", 0.001, 0.2, 0.05)):
        v = p.get(key, default)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            problems.append(f'"{key}": a number from {lo} to {hi} (default {default})')
    bs = p.get("boot_seed", 33)
    if not isinstance(bs, int) or isinstance(bs, bool):
        problems.append('"boot_seed": a whole number (the bootstrap\'s seed)')
    if problems:
        die("project.json: " + "; ".join(problems))
    n = len(sc) * s["count"]
    if not MIN_RUNS <= n <= MAX_RUNS:
        die(f"project.json: {len(sc)} scenario(s) × {s['count']} seeds = {n} runs; use {MIN_RUNS} to {MAX_RUNS} "
            "(fewer cannot give a useful interval; more takes too long on the shared machine)")
    p = dict(p, min_effect=float(me), B=int(p.get("B", 2000)), alpha=float(p.get("alpha", 0.05)), boot_seed=bs)
    p["seed_list"] = list(range(s["first"], s["first"] + s["count"]))
    return p


def check_subset(m, scenarios, what):
    """An optional "scenarios" inside a metric: the runs it is computed on (a part of the campaign's list)."""
    s = m.get("scenarios")
    if s is None:
        return []
    if isinstance(s, list) and s and isinstance(scenarios, list) and all(x in scenarios for x in s) \
            and len(set(s)) == len(s):
        return []
    bad = [x for x in s if x not in (scenarios or [])] if isinstance(s, list) else s
    return [f'{what} "scenarios": {bad} — each must be one of {scenarios} (or leave "scenarios" out: all of them)']


def runs_of(m, runs):
    """The runs (manifest entries) a metric is computed on: its own "scenarios" if it has some, else all."""
    s = m.get("scenarios")
    return [r for r in runs if s is None or r["file"] in s]


def check_window(m, what):
    w = m.get("window", "fault")
    if w in ("fault", "all"):
        return []
    if (isinstance(w, list) and len(w) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in w)
            and 0 <= w[0] < w[1]):
        return []
    return [f'{what} "window": "fault", "all" or [t0, t1] in mission seconds (t0 < t1)']


def rule_words(p):
    m = p["metric"]
    d = {"lower": "lower is better", "higher": "higher is better",
         "closer": f"closer to {p.get('target')} is better"}[p["better"]]
    unit = METRICS[m["name"]][1]
    eff = p["min_effect"]
    out = [f"metric: {m['name']} ({METRICS[m['name']][0]}), window {m.get('window', 'fault')}, {d}"
           + (f", on {', '.join(m['scenarios'])} only" if m.get("scenarios") else ""),
           f"statistic over the runs: {'|mean − target|' if p['better'] == 'closer' else 'the mean'}; "
           f"D = statistic(after) − statistic(before), paired by run, 95 % bootstrap interval "
           f"(B {p['B']}, seed {p['boot_seed']})",
           ("ACCEPT if the whole interval of D is above " + f"{eff:g}" if p["better"] == "higher" else
            "ACCEPT if the whole interval of D is below " + f"{-eff:g}") + (f" {unit}" if unit else "")
           + (" and the guard-rail cannot have lost more than its limit" if p.get("guardrail") else ""),
           ("REJECT if the whole interval of D is below 0" if p["better"] == "higher" else
            "REJECT if the whole interval of D is above 0")
           + (", or the guard-rail's interval is entirely beyond its limit" if p.get("guardrail") else ""),
           "INCONCLUSIVE otherwise (the data cannot tell)"]
    g = p.get("guardrail")
    if g:
        out.insert(2, f"guard-rail: {g['metric']['name']} (window {g['metric'].get('window', 'fault')}), "
                      f"{g['better']} is better, may lose at most {g['max_loss']:g}"
                      + (f", on {', '.join(g['metric']['scenarios'])} only" if g['metric'].get("scenarios") else "")
                      + ("; a 0/1 metric: its interval is never narrower than Newcombe's (Wilson) one"
                         if METRICS[g['metric']['name']][2] == "event" else ""))
    return out


# ------------------------------------------------------------------------------------------------ metrics
def read_rows(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in NUMERIC:
            v = r.get(k, "")
            r[k] = float(v) if v not in ("", None) else None
    return rows


def window_of(m, scenario):
    """(t0, t1) in mission seconds. "fault": from the first fault to the moment that sensor is back to "ok"
    (or the end); "all": the whole run; [t0, t1]: as written."""
    w = m.get("window", "fault")
    if isinstance(w, list):
        return float(w[0]), float(w[1])
    if w == "all":
        return 0.0, math.inf
    faults = sorted((list(f) for f in scenario.get("faults", [])), key=lambda f: f[0])
    if not faults:
        return 0.0, math.inf
    t0, sensor = float(faults[0][0]), faults[0][1]
    for t, s, mode in faults[1:]:
        if s == sensor and mode == "ok" and t > t0:
            return t0, float(t)
    return t0, math.inf


def lin_pct(v, q):
    v = sorted(v)
    pos = (len(v) - 1) * q / 100.0
    i = int(math.floor(pos))
    if i + 1 >= len(v):
        return float(v[-1])
    return float(v[i] + (pos - i) * (v[i + 1] - v[i]))


def custom_metric(code_dir):
    """metric(rows, scenario) from my_metric.py of the commit that is measured (it is part of the ruler)."""
    import importlib.util
    path = os.path.join(code_dir, "my_metric.py")
    if not os.path.exists(path):
        die("metric 'custom' needs my_metric.py (committed) with metric(rows, scenario) → a number")
    spec = importlib.util.spec_from_file_location("my_metric", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "metric", None)):
        die("my_metric.py has no function metric(rows, scenario)")
    return mod.metric


def metric_value(m, rows, scenario, code_dir=HERE):
    """One number for one run (None: not defined in this run)."""
    name = m["name"]
    if name == "custom":
        v = custom_metric(code_dir)(rows, scenario)
        return None if v is None else float(v)
    t0, t1 = window_of(m, scenario)
    win = [r for r in rows if r["t_s"] is not None and t0 <= r["t_s"] < t1]
    if name == "failsafe":
        return 1.0 if any(r["ap_mode"] in ("LAND", "HOLD") for r in rows) else 0.0
    if name == "false_alarm":
        gps_faults = [float(f[0]) for f in scenario.get("faults", []) if f[1] == "gps" and f[2] != "ok"]
        end = min(gps_faults) if gps_faults else math.inf
        calm = [r for r in rows if r["t_s"] is not None and 5.0 <= r["t_s"] < end]
        return 1.0 if any(r["lite_source"] not in ("gps",) for r in calm) else 0.0
    if not win:
        return None
    if name == "detected":
        return 1.0 if any(r["lite_source"] != "gps" for r in win) else 0.0
    if name == "detect_s":
        hit = next((r for r in win if r["lite_source"] != "gps"), None)
        return None if hit is None else hit["t_s"] - t0
    if name in ("availability", "fix_share"):
        ok = ("FIX", "DEGRADED") if name == "availability" else ("FIX",)
        return sum(r["lite_state"] in ok for r in win) / len(win)
    if name == "bad_fix":
        return sum(r["lite_state"] == "FIX" and r["lite_err_m"] is not None and r["lite_sigma_m"]
                   and r["lite_err_m"] > 3.0 * r["lite_sigma_m"] for r in win) / len(win)
    if name == "honest2":
        both = [r for r in win if r["lite_err_m"] is not None and r["lite_sigma_m"]]
        return sum(r["lite_err_m"] <= 2.0 * r["lite_sigma_m"] for r in both) / len(both) if both else None
    col = "ap_err_m" if name.startswith("ap_") else "lite_err_m"
    v = [r[col] for r in win if r[col] is not None]
    if not v:
        return None
    kind = name.split("_")[-1]
    return {"median": lin_pct(v, 50), "p90": lin_pct(v, 90), "p95": lin_pct(v, 95), "max": max(v)}[kind]


# ------------------------------------------------------------------------------------------------ the campaign
DRIVER = r'''
import json, sys
from navera_lite.sim import run as R
spec = json.load(open(sys.argv[1]))
for i, job in enumerate(spec["jobs"]):
    sc = dict(job["scenario"]); sc["seed"] = job["seed"]; sc["name"] = job["name"]
    try:
        w = R.fly(sc, mine=False)
    except Exception as e:
        print(json.dumps({"i": i, "name": job["name"], "error": f"{type(e).__name__}: {e}"}), flush=True)
        sys.exit(3)
    R.write(w, spec["out"])
    print(json.dumps({"i": i, "name": job["name"], "rows": len(w.rows), "parts": w.parts,
                      "outcome": w.outcome()}), flush=True)
'''


def jobs_of(p, code_dir):
    jobs = []
    for s in p["scenarios"]:
        path = os.path.join(code_dir, s)
        try:
            with open(path) as f:
                sc = json.load(f)
        except OSError:
            die(f"{s} is not in the commit you fly: git add {s} and commit it")
        except ValueError as e:
            die(f"{s} is not valid JSON: {e}")
        if not isinstance(sc, dict) or not isinstance(sc.get("name"), str):
            die(f'{s}: a scenario must be one object with a "name"')
        for seed in p["seed_list"]:
            jobs.append({"file": s, "scenario": sc, "seed": seed, "name": f"{sc['name']}_s{seed}"})
    names = [j["name"] for j in jobs]
    if len(set(names)) != len(names):
        die('two scenarios have the same "name": give each one its own')
    return jobs


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def fly_jobs(code_dir, jobs, out_dir, quiet=False):
    """Fly the jobs with the stack of code_dir; returns {name: report line}."""
    os.makedirs(out_dir, exist_ok=True)
    spec = os.path.join(out_dir, ".jobs.json")
    with open(spec, "w") as f:
        json.dump({"jobs": jobs, "out": os.path.abspath(out_dir)}, f)
    drv = os.path.join(out_dir, ".driver.py")
    with open(drv, "w") as f:
        f.write(DRIVER)
    proc = subprocess.Popen([sys.executable, "-B", drv, spec], cwd=code_dir, env=env_for(code_dir),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    done, t_start = {}, time.time()
    for line in proc.stdout:
        try:
            rep = json.loads(line)
        except ValueError:
            continue
        if "error" in rep:
            proc.wait()
            die(f"run {rep['name']} stopped: {rep['error']} — the stack of this commit cannot fly it (fix the stack, "
                "commit, and fly again)")
        done[rep["name"]] = rep
        k = len(done)
        if not quiet and (sys.stdout.isatty() or k % 10 == 0 or k == len(jobs)):
            eta = (time.time() - t_start) / k * (len(jobs) - k)
            print(("\r" if sys.stdout.isatty() else "") + f"  {k:3d}/{len(jobs)} runs flown  ({rep['name']}; about "
                  f"{eta:.0f} s left)   ", end="" if sys.stdout.isatty() else "\n", flush=True)
    err = proc.stderr.read()
    proc.wait()
    if not quiet and sys.stdout.isatty():
        print()
    if proc.returncode or len(done) != len(jobs):
        tail = "\n".join(err.strip().splitlines()[-6:])
        die(f"the campaign stopped after {len(done)} of {len(jobs)} runs:\n{tail}")
    for p in (spec, drv):
        os.remove(p)
    return done


def cmd_campaign(label):
    if label not in LABELS:
        die("python3 project.py campaign before   or   python3 project.py campaign after")
    need_repo()
    rev = LABELS[label]
    sha = sha_of(rev)
    if sha is None:
        die("there is no tag 'before' yet: commit your red test, check it with `python3 project.py red`, then "
            "`git tag before` (lab Step 5)" if label == "before" else "no commit yet")
    if label == "after":
        d = dirty_stack()
        if d:
            die("uncommitted changes in what a campaign flies: " + ", ".join(d[:6]) +
                " — a campaign flies the COMMITTED code: git add …, git commit, then fly again")
        if sha == sha_of("before"):
            die("HEAD is still the commit tagged 'before': make your change, commit it, then fly 'after'")
    code = extract(sha)
    p = load_project(os.path.join(code, "project.json"))
    if label == "after":
        b = manifest("before", required=False)
        if b and b.get("project_sha256") != sha256_file(os.path.join(code, "project.json")):
            die("project.json at HEAD is not the one the 'before' campaign flew: a pre-registration is never "
                "changed after the baseline (git diff before HEAD -- project.json)")
    jobs = jobs_of(p, code)
    ensure_runs_ignored()
    out = os.path.join(RUNS, label)
    old = manifest(label, required=False) if label == "after" else None
    history = list((old or {}).get("afters_history", []))
    shutil.rmtree(out, ignore_errors=True)
    print(f"Campaign '{label}': {len(jobs)} runs ({len(p['scenarios'])} scenario(s) × {len(p['seed_list'])} seeds "
          f"{p['seed_list'][0]}–{p['seed_list'][-1]}) with the stack of commit {sha[:10]} ({rev})")
    t0 = time.time()
    done = fly_jobs(code, jobs, out)
    runs = []
    for j in jobs:
        csv_path = os.path.join(out, j["name"] + ".csv")
        runs.append({"name": j["name"], "file": j["file"], "seed": j["seed"], "rows": done[j["name"]]["rows"],
                     "csv_sha256": sha256_file(csv_path), "parts": done[j["name"]]["parts"]})
    man = {"label": label, "rev": rev, "sha": sha, "branch": branch(), "tree_navera_lite": git("rev-parse", sha + ":navera_lite"),
           "project_sha256": sha256_file(os.path.join(code, "project.json")),
           "started": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0, 1), "runs": runs}
    if label == "after":
        b12 = man_before_sha()
        if [b12, sha[:12]] not in history:
            history.append([b12, sha[:12]])
        man["afters_history"] = history          # every after-commit flown against each baseline (lesson §2)
        git("update-ref", f"refs/flown/{b12}-{sha[:12]}", sha, check=False)
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
    print(f"  wrote runs/{label}/ ({len(runs)} CSV + events logs) and runs/{label}/manifest.json in "
          f"{time.time() - t0:.0f} s")
    if label == "before":
        for m in [p["metric"]] + ([p["guardrail"]["metric"]] if p.get("guardrail") else []):
            values_of(p, man, "before", m)          # dies, naming the run, if the metric is undefined somewhere
        print("  ✔ the metric" + (" and the guard-rail are" if p.get("guardrail") else " is")
              + " defined in every baseline run")
        print("  next: make your change in navera_lite/, then `python3 project.py green` (lab Step 6)")
    else:
        journal(f"campaign after {sha[:12]} against before {man_before_sha()}")
        print("  next: python3 project.py evaluate")


def journal(line):
    """runs/journal.txt: one line per 'after' campaign and per evaluation (lesson §2: every change you evaluate
    against a baseline is reported)."""
    ensure_runs_ignored()
    with open(os.path.join(RUNS, "journal.txt"), "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + line + "\n")


def afters_evaluated(before_sha):
    """The 'after' commits flown or evaluated against this baseline (oldest first): from the journal, from the git
    refs refs/flown/<before12>-<after12> the bench writes at every 'after' campaign, and from runs/after's manifest."""
    seen, b12 = [], before_sha[:12]
    try:
        with open(os.path.join(RUNS, "journal.txt")) as f:
            for ln in f:
                w = ln.split()
                if len(w) >= 7 and w[2] == "evaluate" and w[6] == b12:
                    seen.append(w[4])
                elif len(w) >= 8 and w[2] == "campaign" and w[3] == "after" and w[7] == b12:
                    seen.append(w[4])
    except OSError:
        pass
    refs = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", "refs/flown/"], cwd=HERE,
                          capture_output=True, text=True).stdout.split()
    seen += [r.split("-", 1)[1] for r in refs if r.startswith("flown/" + b12 + "-")]
    m = manifest("after", required=False)
    seen += [a for b, a in (m or {}).get("afters_history", []) if b == b12]
    out = []
    for s in seen:
        if s[:12] not in out:
            out.append(s[:12])
    return out


def man_before_sha():
    b = manifest("before", required=False)
    return b["sha"][:12] if b else "(none)"


def manifest(label, required=True):
    path = os.path.join(RUNS, label, "manifest.json")
    if not os.path.exists(path):
        if required:
            die(f"runs/{label}/ has no campaign yet: python3 project.py campaign {label}")
        return None
    with open(path) as f:
        return json.load(f)


# ------------------------------------------------------------------------------------------------ tests
def pytest_at(sha, target, timeout=600):
    code = extract(sha)
    r = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", target],
                       cwd=code, env=env_for(code), capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def failed_files(out):
    return sorted({ln.split()[1].split("::")[0] for ln in out.splitlines() if ln.startswith(("FAILED ", "ERROR "))
                   and len(ln.split()) > 1})


def last_line(out):
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def cmd_red():
    need_repo()
    p = load_project()
    rev = "before" if sha_of("before") else "HEAD"
    sha = sha_of(rev)
    d = dirty_stack()
    if rev == "HEAD" and d:
        die("uncommitted changes: " + ", ".join(d[:6]) + " — commit your test and project.json first "
            "(the check reads the COMMIT, not your files)")
    if not branch().startswith("project/") and rev == "HEAD":
        die(f"you are on '{branch() or 'a detached HEAD'}': work on a project branch "
            "(git switch -c project/<short-name>, lab Step 2)")
    code = extract(sha)
    if not os.path.exists(os.path.join(code, p["test"])):
        die(f"{p['test']} is not in commit {sha[:10]} ({rev}): git add it and commit")
    rc, out = pytest_at(sha, p["test"])
    print(f"Your red test at {rev} ({sha[:10]}): {last_line(out)}")
    if rc == 0:
        moved = [f for f in git("diff", "--name-only", "start", sha, "--", "navera_lite", "navera_lite.yaml",
                                check=False).split() if not f.startswith(("navera_lite/tests/", "navera_lite/sim/"))]
        if moved and sha_of("start"):
            red = red_commit_before_change(sha)
            die("your test passes at '" + rev + "' because that commit already holds a change of the stack ("
                + ", ".join(moved[:4]) + "): the tag 'before' must sit on the red commit, BEFORE the change. Your red "
                f"commit is probably {red}: git switch -c {branch() or 'project/<name>'}-v2 {red}   (lab Step 5 hint 2)")
        die("your test PASSES on the code without your change: it does not see the problem yet. Make it ask for "
            "the behaviour you want (lesson §3)")
    if rc != 1:
        die("pytest could not even run your test (exit code %d) — a typo, an import at the top of the file? Put "
            "imports of NEW names inside the test function, so that the test FAILS instead of crashing:\n%s"
            % (rc, "\n".join(out.strip().splitlines()[-8:])))
    rc2, out2 = pytest_at(sha, "navera_lite/tests")
    others = [f for f in failed_files(out2) if f != p["test"]]
    print(f"The whole suite at {rev}: {last_line(out2)}")
    if others or (rc2 not in (0, 1)):
        die("other tests fail too: " + (", ".join(others) or "\n" + "\n".join(out2.strip().splitlines()[-8:]))
            + "\n— the code before your change must be healthy")
    print(f"✔ RED: your test fails for the right reason, the rest of the suite passes. Red commit: {sha[:7]} "
          "(note it: a new pre-registration branches from it — lab Step 5 hint 2)")
    if rev == "HEAD":
        print("  next: git tag before   then   python3 project.py campaign before")


def red_commit_before_change(sha):
    """The commit just before the first commit (start..sha) that changed the stack outside tests/ and sim/."""
    for c in git("log", "--format=%H", "--reverse", f"start..{sha}", check=False).split():
        files = git("diff-tree", "--no-commit-id", "--name-only", "-r", c, check=False).split()
        if any((f.startswith("navera_lite/") or f == "navera_lite.yaml")
               and not f.startswith(("navera_lite/tests/", "navera_lite/sim/")) for f in files):
            return git("log", "--format=%h", "-1", c + "~1", check=False) or "<red-commit-id>"
    return "<red-commit-id>"


def cmd_green():
    need_repo()
    p = load_project()
    d = dirty_stack()
    if d:
        print("  (uncommitted changes are NOT tested: " + ", ".join(d[:6]) + ")")
    sha = sha_of("HEAD")
    if sha == sha_of("before"):
        die("HEAD is the commit tagged 'before': commit your change first")
    rc, out = pytest_at(sha, p["test"])
    print(f"Your test at HEAD ({sha[:10]}): {last_line(out)}")
    if rc:
        die("your test still fails on the committed code: " + "\n".join(out.strip().splitlines()[-10:]))
    rc2, out2 = pytest_at(sha, "navera_lite/tests")
    print(f"The whole suite at HEAD: {last_line(out2)}")
    if rc2:
        die("the change broke other tests: " + (", ".join(failed_files(out2)) or "\n" + "\n".join(
            out2.strip().splitlines()[-8:])) + "\n— fix them before you measure (python3 -m pytest -q navera_lite/tests)")
    if sha_of("before"):
        b = extract(sha_of("before"))
        if sha256_file(os.path.join(b, p["test"])) != sha256_file(os.path.join(extract(sha), p["test"])):
            die(f"{p['test']} changed after the tag 'before': the red test is your specification, frozen before the "
                "change (add new tests in another file)")
    print("✔ GREEN: your test passes, the whole suite passes.  next: python3 project.py campaign after")


# ------------------------------------------------------------------------------------------------ evaluate
def values_of(p, man, label, m):
    code = extract(man["sha"])
    out = []
    for run in runs_of(m, man["runs"]):
        with open(os.path.join(code, run["file"])) as f:
            sc = json.load(f)
        csv_path = os.path.join(RUNS, label, run["name"] + ".csv")
        if not os.path.exists(csv_path):
            die(f"runs/{label}/{run['name']}.csv is missing: fly the campaign again")
        v = metric_value(m, read_rows(csv_path), sc, code)
        if v is None or not math.isfinite(v):
            die(f"{m['name']} is not defined in run {label}/{run['name']} (no row in its window?). Every run counts: "
                "a metric that is undefined in some runs cannot be used — this needs a NEW pre-registration (another "
                "metric, window or \"scenarios\" for it): lab Step 5 hint 2")
        out.append(v)
    return out


def newcombe(kb, ka, n, wilson):
    """Newcombe's hybrid score interval of p_after − p_before from two Wilson intervals (mission 32's wilson)."""
    lb, ub = wilson(kb, n)
    la, ua = wilson(ka, n)
    pb, pa = kb / n, ka / n
    return ((pa - pb) - math.sqrt((pa - la) ** 2 + (ub - pb) ** 2),
            (pa - pb) + math.sqrt((ua - pa) ** 2 + (pb - lb) ** 2))


def stat_fn(better, target, np):
    if better == "closer":
        return lambda x: abs(float(np.mean(x)) - float(target))
    return lambda x: float(np.mean(x))


def decide(p, d, ci, g):
    """accept / reject / inconclusive with the pre-registered rule; d, ci for the metric; g = guard-rail result."""
    lo, hi = ci
    eff = p["min_effect"]
    good = lo > eff if p["better"] == "higher" else hi < -eff
    bad = hi < 0 if p["better"] == "higher" else lo > 0
    why = []
    if g:
        glo, ghi = g["ci"]
        loss_hi = -glo if g["better"] == "higher" else ghi        # the largest plausible loss
        loss_lo = -ghi if g["better"] == "higher" else glo        # the smallest plausible loss
        g_bad, g_ok = loss_lo > g["max_loss"], loss_hi <= g["max_loss"]
    else:
        g_bad, g_ok = False, True
    if bad or g_bad:
        why.append("the interval of D is entirely on the bad side of 0" if bad else
                   "the guard-rail's interval is entirely beyond its limit")
        return "reject", why
    if good and g_ok:
        return "accept", ["the whole interval of D is beyond the minimum effect, on the good side"
                          + (", and the guard-rail cannot lose more than its limit" if g else "")]
    if not good:
        why.append("the interval of D reaches the bad side of the minimum effect" if eff else
                   "the interval of D contains 0")
    if not g_ok:
        why.append("the guard-rail's interval crosses its limit")
    return "inconclusive", why


def cmd_evaluate():
    import numpy as np
    sys.path.insert(0, HERE)
    from navera_lite import stats
    need_repo()
    mb, ma = manifest("before"), manifest("after")
    if mb["project_sha256"] != ma["project_sha256"]:
        die("the two campaigns did not fly the same project.json: fly 'after' again (the pre-registration is the "
            "one of the commit tagged 'before')")
    if [r["name"] for r in mb["runs"]] != [r["name"] for r in ma["runs"]]:
        die("the two campaigns do not hold the same runs: fly them again")
    for label, man in (("before", mb), ("after", ma)):
        for r in man["runs"]:
            path = os.path.join(RUNS, label, r["name"] + ".csv")
            if not os.path.exists(path) or sha256_file(path) != r["csv_sha256"]:
                die(f"runs/{label}/{r['name']}.csv is not the file the campaign wrote: fly 'campaign {label}' again")
    p = load_project(os.path.join(extract(ma["sha"]), "project.json"))
    res = {"metric": p["metric"], "better": p["better"], "target": p.get("target"), "min_effect": p["min_effect"],
           "hypothesis": p["hypothesis"], "n_campaign": len(mb["runs"]), "B": p["B"], "alpha": p["alpha"],
           "boot_seed": p["boot_seed"], "before_sha": mb["sha"], "after_sha": ma["sha"],
           "runs": [r["name"] for r in runs_of(p["metric"], mb["runs"])]}
    b = values_of(p, mb, "before", p["metric"])
    a = values_of(p, ma, "after", p["metric"])
    res["n_runs"] = len(b)
    st = stat_fn(p["better"], p.get("target"), np)
    lo, hi = stats.paired_diff_ci(a, b, st, B=p["B"], alpha=p["alpha"], seed=p["boot_seed"])
    if METRICS[p["metric"]["name"]][2] == "event":
        nlo, nhi = newcombe(int(round(sum(b))), int(round(sum(a))), len(b), stats.wilson)
        res["ci_bootstrap"] = [lo, hi]
        lo, hi = min(lo, nlo), max(hi, nhi)          # never narrower than the score interval (lesson §5)
    res.update(before=st(np.array(b)), after=st(np.array(a)), mean_before=float(np.mean(b)),
               mean_after=float(np.mean(a)), D=st(np.array(a)) - st(np.array(b)), ci=[lo, hi],
               values_before=b, values_after=a)
    if METRICS[p["metric"]["name"]][2] == "event":
        n = len(b)
        res["wilson_before"] = list(stats.wilson(int(round(sum(b))), n))
        res["wilson_after"] = list(stats.wilson(int(round(sum(a))), n))
    g = None
    if p.get("guardrail"):
        gp = p["guardrail"]
        gb = values_of(p, mb, "before", gp["metric"])
        ga = values_of(p, ma, "after", gp["metric"])
        glo, ghi = stats.paired_diff_ci(ga, gb, lambda x: float(np.mean(x)), B=p["B"], alpha=p["alpha"],
                                        seed=p["boot_seed"] + 1)
        g = {"metric": gp["metric"], "better": gp["better"], "max_loss": gp["max_loss"], "n_runs": len(gb),
             "before": float(np.mean(gb)), "after": float(np.mean(ga)), "D": float(np.mean(ga) - np.mean(gb)),
             "ci": [glo, ghi]}
        if METRICS[gp["metric"]["name"]][2] == "event":
            nlo, nhi = newcombe(int(round(sum(gb))), int(round(sum(ga))), len(gb), stats.wilson)
            g["ci_bootstrap"] = [glo, ghi]
            g["ci"] = [min(glo, nlo), max(ghi, nhi)]
            g["counts"] = [int(round(sum(gb))), int(round(sum(ga)))]
        res["guardrail"] = g
    res["decision"], res["why"] = decide(p, res["D"], (lo, hi), g)
    res["changes"] = git("diff", "--stat", mb["sha"], ma["sha"], "--", ".").splitlines()[-1:] or ["(none)"]
    journal(f"evaluate after {ma['sha'][:12]} before {mb['sha'][:12]} {res['decision']} D {res['D']:.6g} "
            f"[{lo:.6g}, {hi:.6g}]")
    res["afters_evaluated"] = afters_evaluated(mb["sha"])
    with open(os.path.join(HERE, "evaluation.json"), "w") as f:
        json.dump(res, f, indent=1)
    show(p, res)
    if len(res["afters_evaluated"]) > 1:
        print(f"  ⚠ you evaluated {len(res['afters_evaluated'])} different changes against this baseline ("
              + ", ".join(x[:7] for x in res["afters_evaluated"]) + "): section 8 of REPORT.md must name each of them "
              "and say why (lesson §2: tuning on the pre-registered seeds is a forking path)")
    figure(p, res, np)


def fmt(v):
    return "n/a" if v is None else f"{v:#.4g}"


def show(p, r):
    m, unit = p["metric"]["name"], METRICS[p["metric"]["name"]][1]
    stat = "|mean − target|" if p["better"] == "closer" else "mean"
    print(f"Evaluation of {r['n_runs']} paired runs (before {r['before_sha'][:10]} → after {r['after_sha'][:10]}):")
    print(f"  hypothesis: {r['hypothesis']}")
    print(f"  metric {m} ({unit or 'share/event'}), {p['better']} is better; statistic: {stat}")
    print(f"  before {fmt(r['before'])}   after {fmt(r['after'])}   D = after − before = {fmt(r['D'])}   "
          f"95 % CI of D [{fmt(r['ci'][0])}, {fmt(r['ci'][1])}]")
    if p["better"] == "closer":
        print(f"  (means: before {fmt(r['mean_before'])}, after {fmt(r['mean_after'])}, target {p['target']})")
    if "wilson_before" in r:
        wb, wa = r["wilson_before"], r["wilson_after"]
        print(f"  as rates: before {sum(r['values_before']):.0f}/{r['n_runs']} (Wilson [{wb[0]:.3f}, {wb[1]:.3f}]), "
              f"after {sum(r['values_after']):.0f}/{r['n_runs']} (Wilson [{wa[0]:.3f}, {wa[1]:.3f}])")
    g = r.get("guardrail")
    if g:
        print(f"  guard-rail {g['metric']['name']}: before {fmt(g['before'])}   after {fmt(g['after'])}   "
              f"D {fmt(g['D'])}   95 % CI [{fmt(g['ci'][0])}, {fmt(g['ci'][1])}]   (may lose at most {g['max_loss']:g})"
              + (f"\n    0/1 guard-rail: {g['counts'][0]}/{g['n_runs']} → {g['counts'][1]}/{g['n_runs']}; the interval is "
                 "Newcombe's (Wilson), never narrower than the bootstrap" if "counts" in g else ""))
    print(f"  DECISION (your pre-registered rule): {r['decision'].upper()} — " + "; ".join(r["why"]))
    print("  wrote evaluation.json and out/project.png — the numbers of REPORT.md come from here")


def figure(p, r, np):
    try:
        import warnings
        import matplotlib
        matplotlib.use("Agg")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")          # a harmless "Axes3D" warning on this machine
            import matplotlib.pyplot as plt
    except ImportError:
        return
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    b, a = np.array(r["values_before"]), np.array(r["values_after"])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    for i in range(len(b)):
        ax[0].plot([0, 1], [b[i], a[i]], color="0.7", lw=0.8)
    ax[0].plot(np.zeros(len(b)), b, "o", color="#3366aa", ms=4, label="before")
    ax[0].plot(np.ones(len(a)), a, "o", color="#cc6622", ms=4, label="after")
    ax[0].set_xticks([0, 1], ["before", "after"])
    ax[0].set_ylabel(p["metric"]["name"])
    ax[0].set_title(f"{r['n_runs']} runs, each flown twice (same seed)")
    if p["better"] == "closer":
        ax[0].axhline(p["target"], color="green", ls=":", label=f"target {p['target']}")
    ax[0].legend(loc="best", fontsize=8)
    d = a - b
    ax[1].hist(d, bins=min(30, max(8, len(d) // 3)), color="0.6")
    ax[1].axvline(0, color="k", lw=1)
    if p["better"] != "closer" and p["min_effect"]:
        ax[1].axvline(-p["min_effect"] if p["better"] == "lower" else p["min_effect"], color="#c33", ls="--",
                      label="minimum effect")
    lo, hi = r["ci"]
    ax[1].axvspan(lo, hi, color="#cc6622", alpha=0.25, label="95 % CI of D")
    ax[1].set_xlabel("after − before, per run" + (" (the CI is for |mean − target|)" if p["better"] == "closer" else ""))
    ax[1].set_title(f"decision: {r['decision']}")
    ax[1].legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "out", "project.png"), dpi=90)
    plt.close(fig)


# ------------------------------------------------------------------------------------------------ small commands
def cmd_plan():
    p = load_project()
    print(f"Project: {p['title']}  (idea {p['idea']}, kind {p['kind']})")
    print(f"Hypothesis: {p['hypothesis']}")
    if p["seed_list"][0] < 1000:
        print("  ⚠ your seeds start below 1000: did you fly any of them while exploring? Pre-register seeds you never flew")
    both = sorted(explored_seeds() & set(p["seed_list"]))
    if both:
        die(f"seeds {both[:5]} of your block were flown while exploring (my_runs/): pre-register a block you never "
            "flew (lesson §2)")
    print(f"Red test: {p['test']}")
    print(f"Campaign: {len(p['scenarios'])} scenario(s) × seeds {p['seed_list'][0]}–{p['seed_list'][-1]} = "
          f"{len(p['scenarios']) * len(p['seed_list'])} paired runs")
    for s in p["scenarios"]:
        try:
            with open(os.path.join(HERE, s)) as f:
                sc = json.load(f)
            sys.path.insert(0, HERE)
            from navera_lite.sim.run import check_scenario
            check_scenario(dict(sc, name=sc.get("name", "x")))
            print(f"  {s}: {sc.get('vehicle', 'drone')}, vision {sc.get('vision', 'target')}, "
                  f"{sc.get('light', 'day')}, {sc.get('duration_s')} s, faults {sc.get('faults', [])}")
        except OSError:
            die(f"{s}: no such file")
        except ValueError as e:
            die(f"{s}: {e}")
    print("Decision rule:")
    for line in rule_words(p):
        print("  - " + line)
    if p["metric"]["name"] == "custom" or (p.get("guardrail") or {}).get("metric", {}).get("name") == "custom":
        if not os.path.exists(os.path.join(HERE, "my_metric.py")):
            die("metric 'custom' needs my_metric.py with metric(rows, scenario) → a number")
    print("✔ project.json is complete. Commit it with your red test (lab Step 4).")


def explored_seeds():
    """Seeds of the exploring runs in my_runs/ (project.py one names them <scenario>_s<seed>.csv)."""
    import re
    d = os.path.join(HERE, "my_runs")
    if not os.path.isdir(d):
        return set()
    return {int(m.group(1)) for f in os.listdir(d) if (m := re.search(r"_s(\d+)\.csv$", f))}


def cmd_one(args):
    if len(args) < 2:
        die("python3 project.py one campaign/jam.json 101")
    sys.path.insert(0, HERE)
    from navera_lite.sim import run as R
    try:
        with open(args[0]) as f:
            sc = json.load(f)
        seed = int(args[1])
    except OSError:
        die(f"{args[0]}: no such file")
    except ValueError as e:
        die(f"{args[0]} is not valid JSON, or {args[1]!r} is not a whole number: {e}")
    sc = dict(sc, seed=seed, name=f"{sc.get('name', 'run')}_s{seed}")
    w = R.fly(sc, mine=False)
    path = R.write(w, os.path.join(HERE, "my_runs"))
    print(f"wrote {os.path.relpath(path, HERE)} ({len(w.rows)} rows) with the WORKING folder's stack (uncommitted "
          f"changes included: exploring only)")
    cmd_metrics([path, args[0]])


def cmd_metrics(args):
    if len(args) < 2:
        die("python3 project.py metrics my_runs/jam_s101.csv campaign/jam.json")
    try:
        rows = read_rows(args[0])
        with open(args[1]) as f:
            sc = json.load(f)
    except OSError as e:
        die(f"{e.filename}: no such file")
    except ValueError as e:
        die(f"{args[1]} is not valid JSON: {e}")
    for window in ("fault", "all"):
        t0, t1 = window_of({"window": window}, sc)
        vals = []
        for name in METRICS:
            if name == "custom":
                continue
            v = metric_value({"name": name, "window": window}, rows, sc)
            vals.append(f"{name} {fmt(v)}")
        print(f"window {window} ({t0:g}–{t1:g} s): " + ", ".join(vals))


def cmd_status():
    steps = []
    steps.append(("git repository (init_repo.sh)", is_repo()))
    if is_repo():
        steps.append(("tag 'start'", sha_of("start") is not None))
        steps.append((f"on a project branch (now: {branch() or 'detached'})", branch().startswith("project/")))
        steps.append(("tag 'before' (your red test committed)", sha_of("before") is not None))
    steps.append(("runs/before/ (baseline campaign)", manifest("before", required=False) is not None))
    steps.append(("runs/after/ (campaign with your change)", manifest("after", required=False) is not None))
    steps.append(("evaluation.json", os.path.exists(os.path.join(HERE, "evaluation.json"))))
    for what, ok in steps:
        print(f"  {'✔' if ok else '·'} {what}")
    nxt = next((w for w, ok in steps if not ok), None)
    print("next: " + (nxt if nxt else "REPORT.md, then ✔ Check my work"))


def main(argv):
    if not argv:
        sys.exit(__doc__.split("\n\n")[1])
    cmd, rest = argv[0], argv[1:]
    if cmd == "plan":
        cmd_plan()
    elif cmd == "red":
        cmd_red()
    elif cmd == "campaign":
        cmd_campaign(rest[0] if rest else "")
    elif cmd == "green":
        cmd_green()
    elif cmd == "evaluate":
        cmd_evaluate()
    elif cmd == "status":
        cmd_status()
    elif cmd == "one":
        cmd_one(rest)
    elif cmd == "metrics":
        cmd_metrics(rest)
    else:
        sys.exit(__doc__.split("\n\n")[1])


if __name__ == "__main__":
    main(sys.argv[1:])
