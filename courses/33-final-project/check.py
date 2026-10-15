import hashlib
import json
import math
import os
import re
import shlex
import tempfile

import numpy as np

from academy_check import CheckFailed, Checker, explained, load_student, need, predicted, sh, stored_seal

c = Checker()

GIVEN = "/academy/courses/33-final-project/files"
METRICS = {"err_median": "value", "err_p90": "value", "err_p95": "value", "err_max": "value",
           "ap_err_median": "value", "ap_err_p95": "value", "ap_err_max": "value", "availability": "share",
           "fix_share": "share", "honest2": "share", "bad_fix": "share", "failsafe": "event", "detected": "event",
           "detect_s": "value", "false_alarm": "event", "custom": "value"}
NATURAL = {"err_median": "lower", "err_p90": "lower", "err_p95": "lower", "err_max": "lower", "ap_err_median": "lower",
           "ap_err_p95": "lower", "ap_err_max": "lower", "availability": "higher", "fix_share": "higher",
           "honest2": "closer", "bad_fix": "lower", "failsafe": "lower", "detected": "higher", "detect_s": "lower",
           "false_alarm": "lower", "custom": None}
NUMERIC = ("t_s", "lite_sigma_m", "lite_err_m", "gps_err_m", "vis_err_m", "ap_err_m", "truth_speed_mps")
RULER = ("navera_lite/sim/world.py", "navera_lite/sim/run.py", "navera_lite/sim/sensors.py")
STACK = ("navera_lite", "navera_lite.yaml", "ref_desc.pt", "ref_homography.pt", "campaign", "project.json",
         "my_metric.py", "my_vision_profile.json")
SECTIONS = (("1. The problem", 40), ("2. Pre-registration", 30), ("3. The change", 30), ("4. The red test", 30),
            ("5. The campaign", 25), ("6. Results", 20), ("7. Decision", 15), ("8. Limits", 50))
CACHE = {}


# ------------------------------------------------------------------------------------------------ git, in the sandbox
def git(args, ok_codes=(0,)):
    code, out = sh("git " + args, timeout=60)
    if code not in ok_codes:
        raise CheckFailed(f"git {args.split()[0]} failed: {out.strip()[-300:]}")
    return code, out.strip()


def sha(rev):
    code, out = sh(f"git rev-parse --verify --quiet {shlex.quote(rev + '^{commit}')}")
    return out.strip() if code == 0 and re.fullmatch(r"[0-9a-f]{40}", out.strip()) else None


def ancestor(a, b):
    return sh(f"git merge-base --is-ancestor {a} {b}")[0] == 0


def show(rev, path):
    code, out = sh(f"git show {rev}:{shlex.quote(path)}")
    return out if code == 0 else None


def changed(a, b, *paths):
    tail = (" -- " + " ".join(shlex.quote(p) for p in paths)) if paths else ""
    code, out = sh(f"git diff --name-only {a} {b}{tail}")
    if code:
        raise CheckFailed(f"git diff {a[:10]} {b[:10]} failed: {out[-200:]}")
    return [ln for ln in out.splitlines() if ln.strip()]


def extract(rev_sha):
    if rev_sha in CACHE.setdefault("dirs", {}):
        return CACHE["dirs"][rev_sha]
    d = tempfile.mkdtemp(prefix="chk33_")
    code, out = sh(f"git archive {rev_sha} | tar -x -C {d}", timeout=120)
    if code:
        raise CheckFailed(f"git archive of {rev_sha[:10]} failed: {out[-200:]}")
    CACHE["dirs"][rev_sha] = d
    return d


def pytest_at(rev_sha, target):
    key = (rev_sha, target)
    if key not in CACHE.setdefault("pytest", {}):
        d = extract(rev_sha)
        CACHE["pytest"][key] = sh(f"cd {d} && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={d}:$PYTHONPATH python3 -B -m pytest "
                                  f"-q -p no:cacheprovider -rf {shlex.quote(target)}", timeout=300)
    return CACHE["pytest"][key]


def last_line(out):
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def failed_files(out):
    return sorted({ln.split()[1].split("::")[0] for ln in out.splitlines()
                   if ln.startswith(("FAILED ", "ERROR ")) and len(ln.split()) > 1})


def sha256_text(t):
    return hashlib.sha256(t.encode() if isinstance(t, str) else t).hexdigest()


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------------------------------------ project.json
def validate(p):
    """The check's own reading of a pre-registration (the same rules as project.py plan)."""
    probs = []
    if not isinstance(p, dict):
        return ["project.json must be one object {...}"]
    for k in ("title", "hypothesis", "idea", "kind", "test", "scenarios", "seeds", "metric", "better"):
        if k not in p:
            probs.append(f'"{k}" is missing')
    if probs:
        return probs
    if not isinstance(p["title"], str) or len(p["title"].split()) < 3 or "(fill in" in p["title"]:
        probs.append('"title" is not written yet')
    hy = p["hypothesis"]
    if not isinstance(hy, str) or len(hy.split()) < 6 or "(fill in" in hy:
        probs.append('"hypothesis" is not written yet (one sentence, 6 words or more)')
    if not (p["idea"] == "own" or (isinstance(p["idea"], int) and not isinstance(p["idea"], bool)
                                   and 1 <= p["idea"] <= 10)):
        probs.append('"idea" must be 1–10 (the lesson\'s menu) or "own"')
    if p["kind"] not in ("stack", "sim"):
        probs.append('"kind" must be "stack" or "sim"')
    t = p["test"]
    if not (isinstance(t, str) and re.fullmatch(r"navera_lite/tests/test_[A-Za-z0-9_]+\.py", t)):
        probs.append('"test" must be a file navera_lite/tests/test_<name>.py')
    sc = p["scenarios"]
    if not (isinstance(sc, list) and sc and all(isinstance(s, str) and s.endswith(".json") for s in sc)
            and len(set(sc)) == len(sc)):
        probs.append('"scenarios" must be a list of different .json files')
    s = p["seeds"]
    if not (isinstance(s, dict) and set(s) == {"first", "count"} and all(isinstance(s[k], int)
                                                                         and not isinstance(s[k], bool) for k in s)):
        probs.append('"seeds" must be {"first": …, "count": …}')
    m = p["metric"]
    if not (isinstance(m, dict) and m.get("name") in METRICS):
        probs.append('"metric" name is not one of project.py\'s metrics')
    else:
        if NATURAL[m["name"]] and p["better"] != NATURAL[m["name"]]:
            probs.append(f'"better": {m["name"]} is better when "{NATURAL[m["name"]]}"')
        probs += subset_problems(m, sc, "metric")
    if p["better"] not in ("lower", "higher", "closer"):
        probs.append('"better" must be lower, higher or closer')
    if p["better"] == "closer" and not isinstance(p.get("target"), (int, float)):
        probs.append('"better": "closer" needs a "target"')
    g = p.get("guardrail")
    if g is not None and not (isinstance(g, dict) and isinstance(g.get("metric"), dict)
                              and g["metric"].get("name") in METRICS and g.get("better") in ("lower", "higher")
                              and isinstance(g.get("max_loss"), (int, float))):
        probs.append('"guardrail" is not complete (metric, better, max_loss) — or null')
    elif g is not None:
        gn = NATURAL[g["metric"]["name"]]
        if gn in ("lower", "higher") and g["better"] != gn:
            probs.append(f'guard-rail "better": {g["metric"]["name"]} is better when "{gn}"')
        if gn == "closer":
            probs.append(f'guard-rail: {g["metric"]["name"]} has a target — use it as the metric')
        probs += subset_problems(g["metric"], sc, "guard-rail metric")
    if not probs:
        n = len(sc) * s["count"]
        if not 20 <= n <= 300:
            probs.append(f"{n} runs: use 20 to 300")
    return probs


def subset_problems(m, scenarios, what):
    s = m.get("scenarios")
    if s is None:
        return []
    if isinstance(s, list) and s and isinstance(scenarios, list) and all(x in scenarios for x in s) \
            and len(set(s)) == len(s):
        return []
    return [f'{what} "scenarios" must be some of the campaign\'s scenario files']


def metric_runs(m, runs):
    """(scenario file, seed, name) of the runs a metric is computed on (its own "scenarios", else all)."""
    s = m.get("scenarios")
    return [r for r in runs if s is None or r[0] in s]


def wilson(k, n, z=1.96):
    p = k / n
    cen = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, cen - half), min(1.0, cen + half)


def newcombe(kb, ka, n):
    lb, ub = wilson(kb, n)
    la, ua = wilson(ka, n)
    pb, pa = kb / n, ka / n
    return ((pa - pb) - math.sqrt((pa - la) ** 2 + (ub - pb) ** 2),
            (pa - pb) + math.sqrt((ua - pa) ** 2 + (pb - lb) ** 2))


def project_at(rev_sha, where):
    text = show(rev_sha, "project.json")
    if text is None:
        raise CheckFailed(f"project.json is not in the commit {where}")
    try:
        p = json.loads(text)
    except ValueError as e:
        raise CheckFailed(f"project.json at {where} is not valid JSON: {e}")
    probs = validate(p)
    if probs:
        raise CheckFailed(f"project.json at {where}: " + "; ".join(probs) + " — python3 project.py plan")
    p = dict(p, min_effect=float(p.get("min_effect", 0.0)), B=int(p.get("B", 2000)), alpha=float(p.get("alpha", 0.05)),
             boot_seed=int(p.get("boot_seed", 33)))
    p["seed_list"] = list(range(p["seeds"]["first"], p["seeds"]["first"] + p["seeds"]["count"]))
    return p, text


# ------------------------------------------------------------------------------------------------ the chain of commits
def repo():
    if not os.path.isdir(".git"):
        raise CheckFailed("this folder is not a git repository yet: bash navera_lite/tools/init_repo.sh (lab Step 1)")
    s = sha("start")
    if s is None:
        raise CheckFailed("there is no tag 'start': the repository must come from navera_lite/tools/init_repo.sh")
    return s


def before():
    s0 = repo()
    b = sha("before")
    if b is None:
        raise CheckFailed("there is no tag 'before' yet: commit your red test and project.json, check with "
                          "`python3 project.py red`, then `git tag before` (lab Step 5)")
    if b == s0 or not ancestor(s0, b):
        raise CheckFailed("the commit tagged 'before' must come AFTER 'start' on your branch (your red test commit)")
    return s0, b


def manifest(label):
    path = os.path.join("runs", label, "manifest.json")
    if not os.path.exists(path):
        raise CheckFailed(f"runs/{label}/ has no campaign: python3 project.py campaign {label}")
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError:
        raise CheckFailed(f"runs/{label}/manifest.json is damaged: fly the campaign again")


def after():
    s0, b = before()
    ma = manifest("after")
    a = ma.get("sha")
    if not (isinstance(a, str) and sha(a) == a):
        raise CheckFailed("runs/after/manifest.json names a commit that is not in your repository: fly "
                          "`python3 project.py campaign after` again")
    if a == b or not ancestor(b, a):
        raise CheckFailed("the 'after' campaign must fly a commit that comes AFTER the tag 'before' (your change)")
    head = sha("HEAD")
    if not ancestor(a, head):
        raise CheckFailed("the commit the 'after' campaign flew is not on your branch any more (rebased? reset?): "
                          "fly `python3 project.py campaign after` again")
    return s0, b, a, head


# ------------------------------------------------------------------------------------------------ metrics (the check's own)
def read_rows(path):
    import csv
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in NUMERIC:
            v = r.get(k, "")
            r[k] = float(v) if v not in ("", None) else None
    return rows


def window_of(m, sc):
    w = m.get("window", "fault")
    if isinstance(w, list) and len(w) == 2:
        return float(w[0]), float(w[1])
    if w == "all":
        return 0.0, math.inf
    faults = sorted((list(f) for f in sc.get("faults", [])), key=lambda f: f[0])
    if not faults:
        return 0.0, math.inf
    t0, sensor = float(faults[0][0]), faults[0][1]
    for t, s, mode in faults[1:]:
        if s == sensor and mode == "ok" and t > t0:
            return t0, float(t)
    return t0, math.inf


def lin_pct(v, q):
    return float(np.percentile(np.asarray(v, dtype=float), q))


def metric_value(m, rows, sc):
    name = m["name"]
    if name == "custom":
        mm = load_student("my_metric.py", fresh=True)
        (f,) = need(mm, "metric")
        v = f(rows, sc)
        return None if v is None else float(v)
    t0, t1 = window_of(m, sc)
    win = [r for r in rows if r["t_s"] is not None and t0 <= r["t_s"] < t1]
    if name == "failsafe":
        return 1.0 if any(r["ap_mode"] in ("LAND", "HOLD") for r in rows) else 0.0
    if name == "false_alarm":
        g = [float(f[0]) for f in sc.get("faults", []) if f[1] == "gps" and f[2] != "ok"]
        end = min(g) if g else math.inf
        return 1.0 if any(r["lite_source"] != "gps" for r in rows if r["t_s"] is not None and 5.0 <= r["t_s"] < end) else 0.0
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
        return sum(r["lite_state"] == "FIX" and r["lite_err_m"] is not None and bool(r["lite_sigma_m"])
                   and r["lite_err_m"] > 3.0 * r["lite_sigma_m"] for r in win) / len(win)
    if name == "honest2":
        both = [r for r in win if r["lite_err_m"] is not None and r["lite_sigma_m"]]
        return sum(r["lite_err_m"] <= 2.0 * r["lite_sigma_m"] for r in both) / len(both) if both else None
    col = "ap_err_m" if name.startswith("ap_") else "lite_err_m"
    v = [r[col] for r in win if r[col] is not None]
    if not v:
        return None
    return {"median": lin_pct(v, 50), "p90": lin_pct(v, 90), "p95": lin_pct(v, 95), "max": max(v)}[name.split("_")[-1]]


def stat_of(better, target):
    if better == "closer":
        return lambda x: abs(float(np.mean(x)) - float(target))
    return lambda x: float(np.mean(x))


def paired_ci(a, b, stat, B, alpha, seed):
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = len(a)
    rng = np.random.default_rng(seed)
    reps = np.empty(B)
    for i in range(B):
        idx = rng.integers(0, n, size=n)
        reps[i] = stat(a[idx]) - stat(b[idx])
    lo, hi = np.percentile(reps, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def decide(p, ci, g):
    lo, hi = ci
    eff = p["min_effect"]
    good = lo > eff if p["better"] == "higher" else hi < -eff
    bad = hi < 0 if p["better"] == "higher" else lo > 0
    g_bad, g_ok = False, True
    if g:
        glo, ghi = g["ci"]
        loss_hi = -glo if g["better"] == "higher" else ghi
        loss_lo = -ghi if g["better"] == "higher" else glo
        g_bad, g_ok = loss_lo > g["max_loss"], loss_hi <= g["max_loss"]
    if bad or g_bad:
        return "reject"
    if good and g_ok:
        return "accept"
    return "inconclusive"


def scenarios_at(p, code_dir, where):
    out = {}
    for s in p["scenarios"]:
        try:
            with open(os.path.join(code_dir, s)) as f:
                out[s] = json.load(f)
        except (OSError, ValueError):
            raise CheckFailed(f"{s} is not a readable scenario in the commit {where}")
    return out


def expected_runs(p, scs):
    return [(s, seed, f"{scs[s]['name']}_s{seed}") for s in p["scenarios"] for seed in p["seed_list"]]


DRIVER = r'''
import json, sys
from navera_lite.sim import run as R
spec = json.load(open(sys.argv[1]))
sc = dict(spec["scenario"]); sc["seed"] = spec["seed"]; sc["name"] = spec["name"]
R.write(R.fly(sc, mine=False), spec["out"])
'''


def refly(label, rev_sha, p, scs, man):
    """Fly ONE run of the campaign again, from the commit, and compare it with the CSV in runs/<label>/."""
    runs = expected_runs(p, scs)
    k = int(hashlib.sha256((rev_sha + label).encode()).hexdigest(), 16) % len(runs)
    s, seed, name = runs[k]
    d = extract(rev_sha)
    work = tempfile.mkdtemp(prefix="chk33fly_")
    spec = os.path.join(work, "spec.json")
    with open(spec, "w") as f:
        json.dump({"scenario": scs[s], "seed": seed, "name": name, "out": work}, f)
    with open(os.path.join(work, "drv.py"), "w") as f:
        f.write(DRIVER)
    code, out = sh(f"cd {d} && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH={d}:$PYTHONPATH python3 -B {work}/drv.py {spec}",
                   timeout=240)
    if code:
        raise CheckFailed(f"the commit {rev_sha[:10]} cannot fly {name} again: {out.strip()[-300:]}")
    mine, theirs = os.path.join(work, name + ".csv"), os.path.join("runs", label, name + ".csv")
    if sha256_file(mine) == sha256_file(theirs):
        return name
    va = metric_value(p["metric"], read_rows(mine), scs[s])
    vb = metric_value(p["metric"], read_rows(theirs), scs[s])
    loose = scs[s].get("vision") == "mine"          # trained networks on a GPU are not bit-exact
    if va is not None and vb is not None and abs(va - vb) <= (0.05 * max(abs(va), 1e-9) if loose else 1e-9):
        return name
    raise CheckFailed(f"runs/{label}/{name}.csv is not what commit {rev_sha[:10]} flies (flown again by the check: "
                      f"{p['metric']['name']} {va} instead of {vb}) — fly `python3 project.py campaign {label}` again, "
                      "and never edit the runs")


def campaign_ok(label, rev_sha, where):
    p, text = project_at(rev_sha, where)
    man = manifest(label)
    if man.get("sha") != rev_sha:
        raise CheckFailed(f"runs/{label}/ was flown from commit {str(man.get('sha'))[:10]}, not from {where} "
                          f"({rev_sha[:10]}): python3 project.py campaign {label}")
    if man.get("project_sha256") != sha256_text(text):
        raise CheckFailed(f"runs/{label}/ did not fly the project.json of {where}: fly it again")
    d = extract(rev_sha)
    scs = scenarios_at(p, d, where)
    want = expected_runs(p, scs)
    names = [r.get("name") for r in man.get("runs", [])]
    if names != [n for _, _, n in want]:
        raise CheckFailed(f"runs/{label}/ holds {len(names)} runs, the pre-registration asks for {len(want)} "
                          f"({len(p['scenarios'])} scenario(s) × seeds {p['seed_list'][0]}–{p['seed_list'][-1]}): every "
                          "pre-registered run, no more, no less — fly the campaign again")
    for r in man["runs"]:
        path = os.path.join("runs", label, r["name"] + ".csv")
        if not os.path.exists(path):
            raise CheckFailed(f"{path} is missing: fly the campaign again")
        if sha256_file(path) != r.get("csv_sha256"):
            raise CheckFailed(f"{path} is not the file the campaign wrote (changed by hand?): fly the campaign again")
    return p, scs, man


# ------------------------------------------------------------------------------------------------ the report
def section(text, title):
    mm = re.search(r"^## " + re.escape(title) + r".*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return mm.group(1) if mm else None


# a claim of a gain, and the words that hedge it; "but", "however", "although", "only", "yet" do NOT hedge
# ("improves the error by 1.4 m, but more runs are needed" is still a claim). Regression list:
# solutions/33-final-project/claims_regression.py
NEGATION = re.compile(r"\bnot\b|n't|\bno\b|\bnever\b|cannot|\bunclear\b|\bwhether\b|\bif\b|\bmay\b|\bmight\b"
                      r"|\bwould\b|\bcould\b|uncertain|\bhoped\b|\bexpected\b|\baim|\bmeant\b|\bgoal\b|\bwant"
                      r"|\bhypothes")
CLAIM = re.compile(r"\bbetter\b|\bbeats?\b|\boutperform|more accurate|\bwins?\b|\bsuperior\b|\bimprov"
                   r"|\bfixes\b|\bsolves?\b|\bsolved\b|\breduc|\blower(s|ed)\b|\bfaster\b|\bsooner\b|\bdecreas"
                   r"|\bshortens?\b")
MISSING = re.compile(r"\bno (position|fix|match|gps|data|answer)s?\b")


def claims(text):
    for sent in re.split(r"(?<=[.;!?])\s+|\n\s*\n", str(text)):
        low = MISSING.sub("", sent.lower())
        if re.search(r"\bstill (better|more accurate)\b|^\s*prov(ed|en)\b|(?<!not )\bsignificantly (better|more accurate)\b",
                     low):
            return sent.strip()
        if CLAIM.search(low) and not NEGATION.search(low):
            return sent.strip()
    return None


def numbers(text):
    out = []
    for tok in re.findall(r"[-−]?\d+(?:\.\d+)?", text):
        t = tok.replace("−", "-")
        d = len(t.split(".")[1]) if "." in t else 0
        out.append((float(t), d))
    return out


def written(nums, v, scale, share):
    """Is the value v in the report, correctly rounded, precise enough (or ×100 for a share)?"""
    if v == 0:
        return any(x == 0 for x, d in nums)           # "0", "0.000", "[0, 0]": an exact zero is written as a zero
    need = max(0.05 * abs(v), 0.005 * scale, 1e-9)
    for f in ((1.0, 100.0) if share else (1.0,)):
        for x, d in nums:
            half = 0.5 * 10 ** (-d) / f
            if abs(x / f - v) <= half + 1e-12 and half <= need + 1e-12:
                return True
            if abs(abs(x) / f - abs(v)) <= half + 1e-12 and half <= need + 1e-12 and abs(v) > 0:
                return True     # a difference written as a size ("lower by 0.11")
    return False


# ================================================================================================ Session 1
@c.test("Step 1 — a git repository made by init_repo.sh, tag 'start', and the given measuring bench",
        hint="bash navera_lite/tools/init_repo.sh makes the repository and the tag start; project.py must stay the "
             "given one (git restore project.py, or cp it back from /academy/courses/33-final-project/files/).")
def _():
    s0 = repo()
    c.ok(show(s0, "navera_lite/__init__.py") is not None, "the commit 'start' does not hold navera_lite/: run "
                                                          "init_repo.sh in the lesson folder")
    given = open(os.path.join(GIVEN, "project.py"), encoding="utf-8").read()
    c.ok(os.path.exists("project.py") and open("project.py", encoding="utf-8").read() == given,
         "project.py is not the given measuring bench any more: it is the ruler, put it back (cp "
         f"{GIVEN}/project.py .)")
    for rev in ("start", "before", "HEAD"):
        h = sha(rev)
        if h and show(h, "project.py") not in (None, given):
            raise CheckFailed(f"project.py was changed in a commit (at {rev}): restore the given file and commit it")


@c.test("Step 2 — your work is on a project branch that starts at 'start'",
        hint="git switch -c project/<short-name> (from the commit 'start'); never work on main.")
def _():
    s0 = repo()
    code, out = sh("git symbolic-ref --short -q HEAD")
    b = out.strip()
    c.ok(code == 0 and re.fullmatch(r"project/[A-Za-z0-9._-]+", b or ""),
         f"HEAD is on '{b or 'a detached commit'}': switch to your branch project/<short-name> (git switch …)")
    c.ok(ancestor(s0, "HEAD"), "your branch does not start from the tag 'start'")


@c.test("Step 3 — project.json: a complete pre-registration, frozen at 'before'",
        hint="python3 project.py plan says what is missing; commit project.json WITH your red test, then never "
             "change it (git diff before HEAD -- project.json must be empty).")
def _():
    if not os.path.exists("project.json"):
        raise CheckFailed("project.json is missing")
    try:
        p = json.load(open("project.json", encoding="utf-8"))
    except ValueError as e:
        raise CheckFailed(f"project.json is not valid JSON: {e}")
    probs = validate(p)
    c.ok(not probs, "project.json: " + "; ".join(probs) + " — python3 project.py plan")
    s0, b = before()
    frozen = [f for f in ["project.json", "project.py", "my_metric.py"] + list(p["scenarios"])
              if changed(b, "HEAD", f) or sh(f"git diff --quiet HEAD -- {shlex.quote(f)}")[0]]
    c.ok(not frozen, "changed after the tag 'before': " + ", ".join(frozen) + " — a pre-registration (and the "
                     "scenarios and the ruler it names) is frozen before the baseline; put them back "
                     "(git checkout before -- <file>) or start again from a new red-test commit")
    seal = f"{b[:12]}:{sha256_text(show(b, 'project.json') or '')[:12]}"
    stored = stored_seal()
    c.ok(stored is None or stored == seal,
         f"the pre-registration changed after your Pre-registered badge (sealed {stored}, now {seal}): the tag "
         "'before' or its project.json moved. A new pre-registration needs your teacher: they reset the seal, and both "
         "pre-registrations go in your report")


@c.test("Step 4 — the red test: added before 'before', and it FAILS there (the rest of the suite passes)",
        hint="Commit your test with project.json, then `python3 project.py red`. Imports of NEW names go inside the "
             "test function, so that pytest reports a failure, not a crash.")
def _():
    s0, b = before()
    p, _ = project_at(b, "'before'")
    t = p["test"]
    c.ok(show(b, t) is not None, f"{t} is not in the commit tagged 'before'")
    c.ok(changed(s0, b, t), f"{t} was not added or changed between 'start' and 'before': the red test is YOURS")
    code, out = pytest_at(b, t)
    if code == 0:
        moved = [f for f in changed(s0, b, "navera_lite", "navera_lite.yaml")
                 if not f.startswith(("navera_lite/tests/", "navera_lite/sim/"))]
        if moved:
            raise CheckFailed(f"{t} passes at 'before' because that commit already holds a change of the stack ("
                              + ", ".join(moved[:4]) + "): the tag must sit on the red commit, BEFORE the change "
                              "(lab Step 5 hint 2 puts the commits back in order)")
        raise CheckFailed(f"{t} PASSES at 'before' ({last_line(out)}): it does not see the problem without your "
                          "change (lesson §3)")
    if code != 1:
        raise CheckFailed(f"pytest could not run {t} at 'before' (exit {code}): {last_line(out)} — a syntax error or "
                          "an import at the top of the file? A red test FAILS, it does not crash")
    code, out = pytest_at(b, "navera_lite/tests")
    others = [f for f in failed_files(out) if f != t]
    c.ok(not others, "at 'before' other tests fail too: " + ", ".join(others) + " — the stack must be healthy before "
                     "your change")


@c.test("Step 5 — the baseline campaign flew the commit tagged 'before', every pre-registered run",
        hint="python3 project.py campaign before (after `git tag before`); never edit runs/ by hand.")
def _():
    s0, b = before()
    p, scs, man = campaign_ok("before", b, "'before'")
    CACHE["refly_before"] = refly("before", b, p, scs, man)
    runs = expected_runs(p, scs)
    for m in [p["metric"]] + ([p["guardrail"]["metric"]] if p.get("guardrail") else []):
        for s, _, name in metric_runs(m, runs):
            if metric_value(m, read_rows(os.path.join("runs", "before", name + ".csv")), scs[s]) is None:
                raise CheckFailed(f"{m['name']} is not defined in run before/{name} (no row in its window): this "
                                  "pre-registration cannot be evaluated — make a new one (lab Step 5 hint 2)")
    c.seal = f"{b[:12]}:{sha256_text(show(b, 'project.json') or '')[:12]}"   # kept by the server the first time


# ================================================================================================ Session 2
@c.test("Step 6 — the change: committed after 'before', the ruler untouched, test and suite green",
        hint="Change the stack (navera_lite/, navera_lite.yaml or a ref_*.pt), commit, `python3 project.py green`. "
             "Do not touch the simulator's world (kind stack), the red test or project.json after 'before'.")
def _():
    s0, b, a, head = after()
    p, _ = project_at(b, "'before'")
    files = changed(b, a)
    stack = [f for f in files if (f.startswith("navera_lite/") or f in ("navera_lite.yaml", "ref_desc.pt",
                                                                       "ref_homography.pt"))
             and not f.startswith("navera_lite/tests/")]
    c.ok(stack, "between 'before' and the 'after' campaign nothing changed in the stack (navera_lite/, "
                "navera_lite.yaml, ref_*.pt): where is your change?")
    if p["kind"] == "stack":
        moved = [f for f in RULER if f in files]
        c.ok(not moved, "the simulator's world changed between 'before' and 'after': " + ", ".join(moved) + " — for "
                        "a 'stack' project the ruler must not move (a sensor model belongs in the setup, before "
                        "'before', or in a project of kind 'sim')")
    else:
        out = [f for f in stack if not f.startswith("navera_lite/sim/")]
        c.ok(not out, "a 'sim' project changes only the simulator (navera_lite/sim/): also changed " + ", ".join(out))
    c.ok(not changed(b, a, p["test"]), f"{p['test']} changed after 'before': the red test is frozen (put new tests "
                                       "in another file)")
    code, out = pytest_at(a, p["test"])
    c.ok(code == 0, f"{p['test']} does not pass on the commit you measured: {last_line(out)}")
    code, out = pytest_at(a, "navera_lite/tests")
    c.ok(code == 0, "the suite fails on the commit you measured: " + ", ".join(failed_files(out) or [last_line(out)]))


@c.test("Step 7 — the 'after' campaign flew your committed change, and HEAD still holds it",
        hint="Commit everything in navera_lite/ (git status), then python3 project.py campaign after; after it, "
             "change nothing in the stack (or fly 'after' again).")
def _():
    s0, b, a, head = after()
    p, scs, man = campaign_ok("after", a, "the 'after' commit")
    later = changed(a, "HEAD", *STACK)
    c.ok(not later, "the stack changed after the 'after' campaign: " + ", ".join(later[:5]) + " — fly "
                    "`python3 project.py campaign after` again")
    code, out = sh("git status --porcelain -- " + " ".join(s for s in STACK if os.path.exists(s)))
    dirty = [ln[3:] for ln in out.splitlines() if ln.strip()]
    c.ok(not dirty, "uncommitted changes in the stack: " + ", ".join(dirty[:5]) + " — commit them (and fly 'after' "
                    "again) or throw them away (git restore)")
    mb = manifest("before")
    c.ok([r["name"] for r in mb["runs"]] == [r["name"] for r in man["runs"]], "the two campaigns hold different runs")
    CACHE["refly_after"] = refly("after", a, p, scs, man)


@c.test("Step 8 — evaluation.json: the paired difference, its interval and the decision, from YOUR runs",
        hint="python3 project.py evaluate, after both campaigns (and again after any new campaign).")
def _():
    s0, b, a, head = after()
    p, _ = project_at(b, "'before'")
    if not os.path.exists("evaluation.json"):
        raise CheckFailed("evaluation.json does not exist yet: python3 project.py evaluate")
    try:
        ev = json.load(open("evaluation.json"))
    except ValueError:
        raise CheckFailed("evaluation.json is damaged: python3 project.py evaluate")
    c.ok(ev.get("before_sha") == b and ev.get("after_sha") == a, "evaluation.json is not about your two campaigns: "
                                                                  "python3 project.py evaluate again")
    scs = scenarios_at(p, extract(b), "'before'")
    runs = expected_runs(p, scs)

    def vals(label, m):
        out = []
        for s, _, name in metric_runs(m, runs):
            v = metric_value(m, read_rows(os.path.join("runs", label, name + ".csv")), scs[s])
            if v is None:
                raise CheckFailed(f"{m['name']} is not defined in run {label}/{name}: choose a metric defined in "
                                  "every run")
            out.append(v)
        return out
    vb, va = vals("before", p["metric"]), vals("after", p["metric"])
    for key, mine in (("values_before", vb), ("values_after", va)):
        got = ev.get(key)
        c.ok(isinstance(got, list) and len(got) == len(mine) and all(abs(float(x) - y) <= 1e-9 * max(1, abs(y))
                                                                     for x, y in zip(got, mine)),
             f"evaluation.json {key} are not the metric of your runs: python3 project.py evaluate again")
    st = stat_of(p["better"], p.get("target"))
    D = st(va) - st(vb)
    lo, hi = paired_ci(va, vb, st, p["B"], p["alpha"], p["boot_seed"])
    if METRICS[p["metric"]["name"]] == "event":
        nlo, nhi = newcombe(int(round(sum(vb))), int(round(sum(va))), len(vb))
        lo, hi = min(lo, nlo), max(hi, nhi)
    c.ok(abs(float(ev.get("D", math.nan)) - D) <= 1e-9 * max(1, abs(D)), "evaluation.json D is not "
                                                                         "statistic(after) − statistic(before)")
    tol = 0.1 * max(hi - lo, 0.0) + 1e-9 * max(1.0, abs(D))
    eci = ev.get("ci") or [math.nan, math.nan]
    c.ok(abs(eci[0] - lo) <= tol and abs(eci[1] - hi) <= tol,
         f"evaluation.json's interval [{eci[0]:.4g}, {eci[1]:.4g}] is not the paired bootstrap of your runs (the "
         "check gets another one): python3 project.py evaluate again")
    g = None
    if p.get("guardrail"):
        gp = p["guardrail"]
        gb, ga = vals("before", gp["metric"]), vals("after", gp["metric"])
        glo, ghi = paired_ci(ga, gb, lambda x: float(np.mean(x)), p["B"], p["alpha"], p["boot_seed"] + 1)
        if METRICS[gp["metric"]["name"]] == "event":
            nlo, nhi = newcombe(int(round(sum(gb))), int(round(sum(ga))), len(gb))
            glo, ghi = min(glo, nlo), max(ghi, nhi)
        g = dict(gp, ci=(glo, ghi), D=float(np.mean(ga) - np.mean(gb)), before=float(np.mean(gb)),
                 after=float(np.mean(ga)))
        eg = ev.get("guardrail") or {}
        c.ok(abs(float(eg.get("D", math.nan)) - g["D"]) <= 1e-9 * max(1, abs(g["D"])),
             "evaluation.json's guard-rail is not from your runs: python3 project.py evaluate again")
    dec = decide(p, (lo, hi), g)
    if ev.get("decision") != dec:
        # the student's own stats.py (adopted) may draw another bootstrap: an end within the tolerance of a boundary
        # can tip the decision; then evaluate's decision (from its own interval) stands
        mine = decide(p, tuple(eci), dict(g, ci=tuple((ev.get("guardrail") or {}).get("ci") or g["ci"])) if g else None)
        c.ok(ev.get("decision") == mine, f"evaluation.json says {ev.get('decision')!r}; your pre-registered rule gives "
                                         "another decision on these runs: python3 project.py evaluate again")
        lo, hi = eci
        dec = mine
        if g:
            g["ci"] = tuple((ev.get("guardrail") or {}).get("ci") or g["ci"])
    CACHE["eval"] = dict(p=p, D=D, ci=(lo, hi), before=st(vb), after=st(va), g=g, decision=dec, n=len(vb),
                         afters=[x for x in (ev.get("afters_evaluated") or []) if isinstance(x, str)], b_sha=b,
                         mean_b=float(np.mean(vb)), mean_a=float(np.mean(va)), files=changed(b, a))


def report_text():
    if not os.path.exists("REPORT.md"):
        raise CheckFailed("REPORT.md is missing")
    text = open("REPORT.md", encoding="utf-8", errors="replace").read()
    first = text.find("\n## ")
    return text, (text[first:] if first >= 0 else text)


def evaluation():
    if "eval" not in CACHE:
        raise CheckFailed("the evaluation must pass first (check 8): REPORT.md is checked against it")
    return CACHE["eval"]


@c.test("Step 9 — REPORT.md: every section written, with YOUR numbers (correctly rounded)",
        hint="Copy the numbers that `python3 project.py evaluate` prints: before, after, D and both ends of its 95 % "
             "interval (and the guard-rail's D and interval), the number of runs, the seeds; keep the ## titles.")
def _():
    text, body = report_text()
    left = [s for s in ("(fill in", "…") if s in body]
    c.ok(not left, f"placeholders still there: {left}")
    for title, n in SECTIONS:
        s = section(body, title)
        c.ok(s is not None, f"the section '## {title}' is missing (keep the titles of the template)")
        w = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", s))
        c.ok(w >= n, f"section '{title}' has {w} words (at least {n})")
    e = evaluation()
    p = e["p"]
    share = METRICS[p["metric"]["name"]] in ("share", "event")
    nums = numbers(body.replace("−", "-"))
    scale = max(abs(e["mean_b"]), abs(e["mean_a"]), abs(e["before"]), abs(e["after"]), e["ci"][1] - e["ci"][0], 1e-9)
    for what, v in (("the statistic before", e["before"]), ("the statistic after", e["after"]), ("D", e["D"]),
                    ("the lower end of D's 95 % interval", e["ci"][0]), ("the upper end of D's interval", e["ci"][1])):
        c.ok(written(nums, v, scale, share), f"{what} ({p['metric']['name']}) is not in the report, correctly rounded "
                                             "to at least 2 significant digits")
    if e["g"]:
        g = e["g"]
        gscale = max(abs(g["before"]), abs(g["after"]), g["ci"][1] - g["ci"][0], 1e-9)
        gshare = METRICS[g["metric"]["name"]] in ("share", "event")
        for what, v in (("the guard-rail's D", g["D"]), ("the guard-rail interval's lower end", g["ci"][0]),
                        ("the guard-rail interval's upper end", g["ci"][1])):
            c.ok(written(nums, v, gscale, gshare), f"{what} is not in the report")
    c.ok(any(x == e["n"] and d == 0 for x, d in nums), f"the number of paired runs ({e['n']}) is not in the report")
    camp = section(body, "5. The campaign")
    c.ok(str(p["seed_list"][0]) in camp and str(p["seed_list"][-1]) in camp,
         "section 5 must give the seeds (first and last of the block)")
    ch = section(body, "3. The change")
    c.ok(any(os.path.basename(f) in ch for f in e["files"] if not f.startswith("navera_lite/tests/")),
         "section 3 must name the file(s) you changed")
    rt = section(body, "4. The red test")
    c.ok(os.path.basename(p["test"]) in rt and re.search(r"fail", rt.lower()),
         "section 4 must name your test file and say how it failed at 'before'")
    c.ok(p["metric"]["name"] in section(body, "2. Pre-registration"), "section 2 must name the pre-registered metric")


@c.test("Step 9 — REPORT.md: the decision follows the rule, and no claim the interval does not support",
        hint="Section 7 starts with the decision of `project.py evaluate` (accept / reject / inconclusive); say whether "
             "the interval contains 0 (or crosses the minimum effect); 'better', 'improves' only for an accepted "
             "result; section 8: what a simulation does not show.")
def _():
    text, body = report_text()
    e = evaluation()
    dec = e["decision"]
    sec7 = section(body, "7. Decision") or ""
    first = re.split(r"(?<=[.!?])\s", sec7.strip(), maxsplit=1)[0].lower()
    found = sorted((m.start(), d) for d in ("accept", "reject", "inconclusive")
                   for m in [re.search(r"\b" + d[:6], first)] if m)
    said = found[0][1] if found else "none of accept / reject / inconclusive"
    c.ok(found and found[0][1] == dec, f"the first sentence of section 7 must start with the decision of your rule: "
                                       f"{dec.upper()} (it says {said} first)")
    res = (section(body, "6. Results") or "") + sec7
    c.ok(re.search(r"contain|includ|exclud|cross|\bzero\b|\b0\b|entirely|whole interval|below|above", res.lower()),
         "sections 6–7 must say where the interval lies: does it contain 0 (or the minimum effect)?")
    bad_side = (e["ci"][1] < 0) if e["p"]["better"] == "higher" else (e["ci"][0] > 0)
    if dec == "inconclusive" or (dec == "reject" and bad_side):
        sent = claims(res + (section(body, "8. Limits") or ""))
        if sent is not None:
            raise CheckFailed(f"the result is {dec.upper()}, but the report claims a gain: \"{sent[:120]}\" — say what "
                              "the interval allows (not shown, inconclusive, rejected), not what you hoped")
    lim = (section(body, "8. Limits") or "").lower()
    afters = list(e.get("afters") or [])
    try:
        with open(os.path.join("runs", "journal.txt")) as f:
            for ln in f:
                w = ln.split()
                if len(w) >= 7 and w[2] == "evaluate" and w[6] == e["b_sha"][:12] and w[4] not in afters:
                    afters.append(w[4])
    except OSError:
        pass
    if len(afters) > 1:
        missing = [x[:7] for x in afters if x[:7] not in lim]
        c.ok(not missing, f"you evaluated {len(afters)} different changes against this baseline (runs/journal.txt): "
                          "section 8 must name each of them by its commit id (" + ", ".join(missing) + " missing) and "
                          "say why — tuning on the pre-registered seeds is a forking path (lesson §2)")
    c.ok(re.search(r"simulat|synthetic", lim), "section 8 must say that this is a simulation (and what that means)")
    c.ok(re.search(r"field|real|flight|camera|terrain|wind|hardware|weather|sensor", lim),
         "section 8 must say what the simulation does not show (real sensors, field, terrain…)")


@c.test("answers.py — predictions and explanations",
        hint="PREDICT_SUITE (Step 0) and PREDICT_EFFECT (before the 'after' campaign) only need to be written; the "
             "EXPLAIN_… answers: lesson §2–§5.")
def _():
    a = load_student("answers.py", fresh=True)
    v = need(a, "PREDICT_SUITE", "PREDICT_EFFECT", "EXPLAIN_RED", "EXPLAIN_SEEDS", "EXPLAIN_PAIRED", "EXPLAIN_RULER")
    predicted("PREDICT_SUITE", v[0])
    predicted("PREDICT_EFFECT", v[1])
    explained("EXPLAIN_RED", v[2], ([r"fail", r"red"], "what the test does on the old code"),
              ([r"see", r"detect", r"catch", r"prove", r"show", r"problem", r"bug", r"without (the|my) change",
                r"old code", r"check"], "what that proves about the test"))
    explained("EXPLAIN_SEEDS", v[3], ([r"choos", r"chose", r"pick", r"cherry", r"select", r"luck", r"best", r"favou?r"],
                                      "what a free choice of seeds would allow"),
              ([r"advance", r"before", r"fixed", r"pre-?regist", r"first", r"frozen", r"block", r"consecutive"],
               "why they are fixed beforehand"))
    explained("EXPLAIN_PAIRED", v[4], ([r"same (seed|run|scenario|condition|noise|random|fault|flight)", r"paired",
                                        r"pair"], "that the two campaigns fly the same runs"),
              ([r"differen", r"cancel", r"shared", r"only (the|my) change", r"variance", r"narrow", r"noise",
                r"remov"], "what pairing removes"))
    explained("EXPLAIN_RULER", v[5], ([r"ruler", r"yardstick", r"world", r"simulat", r"measur", r"model"],
                                      "what world.py is for the comparison"),
              ([r"same", r"both", r"compar", r"chang", r"move", r"differen"], "why it must stay the same"))


@c.test("Step 10 — my_project.patch: your change as a patch that matches your branch",
        hint="git diff before HEAD -- navera_lite navera_lite.yaml > my_project.patch, then "
             "git apply --check -R my_project.patch must say nothing.")
def _():
    s0, b, a, head = after()
    c.file_exists("my_project.patch")
    text = open("my_project.patch", encoding="utf-8", errors="replace").read()
    c.ok(text.startswith("diff --git") or "\ndiff --git" in text, "my_project.patch is not a git diff")
    stack = [f for f in changed(b, a) if not f.startswith("navera_lite/tests/") and f != "project.json"]
    c.ok(any(f"b/{f}" in text for f in stack), "my_project.patch does not contain your change (" + ", ".join(stack[:3])
         + ")")
    code, out = sh("git apply --check -R my_project.patch")
    c.ok(code == 0, "git apply --check -R my_project.patch fails: the patch does not match your branch any more — "
                    f"make it again ({out.strip()[-160:]})")


S1 = ("Step 1 —", "Step 2 —", "Step 3 —", "Step 4 —", "Step 5 —")
c.milestone("session1", *S1, label="Pre-registered")
c.milestone("session2", *S1, "Step 6 —", "Step 7 —", "Step 8 —", label="Measured")
c.milestone("final", "Step", "answers", label="Engineer")
c.run()
