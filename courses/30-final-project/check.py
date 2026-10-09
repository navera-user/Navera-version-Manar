import json
import math
import os
import re
import shutil
import tempfile

import numpy as np

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
NAV = os.path.expanduser("~/navera")
DATA = "/data/academy/30-final-project"
SECTIONS = ["Proposal", "Change", "Test", "Measurement", "Result", "Limits"]
LABELS = ["Problem", "Hypothesis", "Metric", "Acceptance criterion"]
IGNORED = ("build/", "install/", "log/")          # build products are never part of a project


# ---------------------------------------------------------------- helpers
def git(args, timeout=30):
    code, out = sh(f"git -C {NAV} {args}", timeout=timeout)
    if code != 0:
        raise CheckFailed(f"`git {args}` failed in ~/navera:\n{out[-400:]}")
    return out.strip()


def sections():
    if not os.path.exists("PROJECT.md"):
        raise CheckFailed("PROJECT.md is missing — did you rename or delete it? (↺ Reset lab files gives it back)")
    text = open("PROJECT.md", encoding="utf-8", errors="replace").read()
    out = {}
    for p in re.split(r"^##\s+", text, flags=re.M)[1:]:
        title, _, body = p.partition("\n")
        out[title.strip()] = body.strip()
    return out


def no_placeholder(text):
    return re.sub(r"\((?:[^()]|\([^()]*\))*\)", "", text).strip()     # "(…)" placeholders removed


def changed_files():
    out = git("diff --name-only base..HEAD")
    return [f for f in out.splitlines() if f and not f.startswith(IGNORED)]


def tests_changed():
    return [f for f in changed_files() if re.search(r"(^|/)test_[^/]*\.py$", f)
            and os.path.exists(os.path.join(NAV, f))]


def results():
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet (the example writes it in TODO 5; for another "
                          "project use write_results() from stats_tools.py)")
    try:
        return json.load(open("results.json"))
    except ValueError as e:
        raise CheckFailed(f"results.json is not valid JSON: {e}")


def stats():
    return load_student("stats_tools.py")


def ar1(n, rho, seed):
    rng = np.random.default_rng(seed)
    e = np.empty(n)
    e[0] = rng.normal()
    for k in range(1, n):
        e[k] = rho * e[k - 1] + math.sqrt(1 - rho ** 2) * rng.normal()
    return e


def pair(r, what):
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"{what} should return (lo, hi), got {r!r}")
    lo, hi = float(r[0]), float(r[1])
    c.ok(math.isfinite(lo) and math.isfinite(hi) and lo <= hi, f"{what} returned lo={lo}, hi={hi}")
    return lo, hi


# ---------------------------------------------------------------- the statistics
@c.test("stats_tools.percentile() uses linear interpolation (same as numpy's default)",
        hint="h = (n - 1) * q / 100; take x[floor(h)] and move the fraction h - floor(h) towards the next "
             "sorted value. q = 100 has no next value; an empty list gives nan.")
def _():
    (percentile,) = need(stats(), "percentile")
    rng = np.random.default_rng(3)
    for n in (1, 2, 7, 50):
        x = rng.exponential(5.0, n)
        for q in (0, 5, 50, 90, 95, 100):
            c.near(percentile(list(x), q), float(np.percentile(x, q)), 1e-9, what=f"percentile(n={n}, q={q})")
    r = percentile([], 50)
    c.ok(isinstance(r, float) and math.isnan(r), f"percentile([], 50) should be nan, got {r!r}")


@c.test("bootstrap_ci(): (lo, hi), reproducible with a seed, about 2 x 1.96 sigma / sqrt(n) wide for a mean",
        hint="Create ONE generator rng = np.random.default_rng(seed) before the loop; each resample draws n "
             "indices with replacement; the CI is the alpha/2 and 1 - alpha/2 percentiles of the statistics.")
def _():
    (bci,) = need(stats(), "bootstrap_ci")
    x = np.random.default_rng(7).normal(10.0, 1.0, 400)
    r1 = pair(bci(x, np.mean, n_boot=1000, alpha=0.05, seed=1), "bootstrap_ci")
    r2 = pair(bci(x, np.mean, n_boot=1000, alpha=0.05, seed=1), "bootstrap_ci")
    c.ok(r1 == r2, "two calls with the same seed give different intervals: is the seed used?")
    c.ok(r1[0] < x.mean() < r1[1], f"the CI {r1} does not contain the sample mean {x.mean():.3f}")
    w, theory = r1[1] - r1[0], 2 * 1.96 * x.std() / math.sqrt(len(x))
    c.ok(0.8 * theory < w < 1.2 * theory, f"CI width {w:.3f}, expected about {theory:.3f} (2 x 1.96 sigma/sqrt n)")


@c.test("bootstrap_ci(): alpha changes the level, any statistic works (median, p95)",
        hint="alpha = 0.20 is an 80 % interval: narrower than the 95 % one. `stat` is a function you call "
             "on each resample — do not hard-code np.mean.")
def _():
    (bci,) = need(stats(), "bootstrap_ci")
    x = np.random.default_rng(8).exponential(3.0, 300)
    w95 = np.subtract(*pair(bci(x, np.median, n_boot=800, alpha=0.05, seed=2), "bootstrap_ci")[::-1])
    w80 = np.subtract(*pair(bci(x, np.median, n_boot=800, alpha=0.20, seed=2), "bootstrap_ci")[::-1])
    c.ok(w80 < w95, f"the 80 % CI ({w80:.3f} wide) should be narrower than the 95 % CI ({w95:.3f})")
    lo, hi = pair(bci(x, lambda v: float(np.percentile(v, 95)), n_boot=800, alpha=0.05, seed=2), "bootstrap_ci")
    c.ok(lo < np.percentile(x, 95) < hi, "the CI of the p95 does not contain the sample p95: is `stat` used?")


@c.test("block_bootstrap_ci(): resamples whole blocks — honest (wider) intervals on correlated errors",
        hint="Each resample is idx = block_indices(n, block_len, rng) and its value is metric(idx). On a "
             "correlated series (rho = 0.9) the block CI must be several times wider than the iid one; "
             "with block_len = 1 it must be about the iid width.")
def _():
    m = stats()
    bci, bbci = need(m, "bootstrap_ci", "block_bootstrap_ci")
    e = ar1(1800, 0.9, seed=4)
    seen = []

    def metric(idx):
        seen.append(idx)
        return float(np.mean(e[idx]))
    r = pair(bbci(len(e), metric, block_len=60, n_boot=300, alpha=0.05, seed=5), "block_bootstrap_ci")
    c.ok(len(seen) == 300, f"metric() was called {len(seen)} times for n_boot=300")
    idx = np.asarray(seen[0])
    c.ok(idx.dtype.kind in "iu" and len(idx) == 1800 and idx.min() >= 0 and idx.max() < 1800,
         "metric() should receive an integer array of 1800 epoch indices between 0 and 1799")
    c.ok(np.sum(np.diff(idx) == 1) > 1700, "the indices are not in consecutive blocks — use block_indices()")
    w_block = r[1] - r[0]
    w_iid = np.subtract(*pair(bci(e, np.mean, n_boot=300, alpha=0.05, seed=5), "bootstrap_ci")[::-1])
    c.ok(w_block > 2.5 * w_iid, f"block CI width {w_block:.3f} is not much wider than iid {w_iid:.3f}")
    w1 = np.subtract(*pair(bbci(len(e), lambda i: float(np.mean(e[i])), block_len=1, n_boot=300, seed=5),
                           "block_bootstrap_ci")[::-1])
    c.ok(0.75 * w_iid < w1 < 1.33 * w_iid, f"block_len=1 gives width {w1:.3f}, expected about {w_iid:.3f}")


@c.test("measure_project.summary(): availability, CEP50, p95 and max of the accepted epochs",
        hint="Keep errors[accepted] only; availability = accepted / all epochs (rejected epochs count!); "
             "use percentile() for CEP50 (q=50) and p95; nan everywhere when nothing is accepted.")
def _():
    (summary,) = need(load_student("measure_project.py"), "summary")
    acc = [True, True, False, True, True, False, True, True, True, True]
    err = [1.0, 2.0, 99.0, 3.0, 4.0, float("nan"), 5.0, 6.0, 7.0, 50.0]
    s = summary(acc, err)
    c.ok(isinstance(s, dict), f"summary() should return a dict, got {s!r}")
    for k, v in (("n_epochs", 10), ("n_accepted", 8), ("availability", 0.8),
                 ("cep50", float(np.percentile([1, 2, 3, 4, 5, 6, 7, 50], 50))),
                 ("p95", float(np.percentile([1, 2, 3, 4, 5, 6, 7, 50], 95))), ("max", 50.0)):
        c.ok(k in s, f"the dict has no key '{k}'")
        c.near(s[k], v, 1e-9, what=f"summary(...)['{k}']")
    z = summary([False, False], [1.0, 2.0])
    c.ok(isinstance(z, dict) and math.isnan(float(z.get("p95", 0.0))) and z.get("n_accepted") == 0,
         "with nothing accepted: n_accepted 0 and p95 nan")


# ---------------------------------------------------------------- the report and the numbers
@c.test("PROJECT.md has its six sections, each one written by you",
        hint="Keep the headings ## Proposal, ## Change, ## Test, ## Measurement, ## Result, ## Limits and "
             "replace every '(…)' placeholder by your own text — a few sentences each.")
def _():
    s = sections()
    missing = [h for h in SECTIONS if h not in s]
    c.ok(not missing, "missing heading(s): " + ", ".join("## " + h for h in missing))
    todo = [h for h in SECTIONS if len(no_placeholder(s[h]).split()) < 15]
    c.ok(not todo, "still empty or only the placeholder: " + ", ".join(todo) + " (at least a few sentences each)")


@c.test("PROJECT.md: a real proposal (problem, hypothesis, metric, acceptance criterion) and a measurement with CIs",
        hint="Under ## Proposal keep the four bold labels and write after each one. ## Measurement needs the "
             "numbers before AND after and their 95 % confidence intervals (write 'CI' or 'confidence').")
def _():
    s = sections()
    prop = s.get("Proposal", "")
    for lab in LABELS:
        mt = re.search(r"\*\*" + lab + r":?\*\*:?(.*?)(?=\*\*[A-Z][a-z ]+:?\*\*|\Z)", prop, re.S)
        c.ok(mt, f"## Proposal has no **{lab}:** label")
        c.ok(len(no_placeholder(mt.group(1)).split()) >= 6, f"**{lab}:** is still empty or only the placeholder")
    m = s.get("Measurement", "")
    c.ok(len(re.findall(r"\d", m)) >= 8, "## Measurement contains (almost) no numbers")
    c.ok(re.search(r"before", m, re.I) and re.search(r"after", m, re.I),
         "## Measurement should show the result BEFORE and AFTER your change")
    c.ok(re.search(r"\bCIs?\b|confidence", m, re.I), "## Measurement should give the 95 % confidence intervals")
    c.ok(re.search(r"\b(accept|reject|inconclusive)", s.get("Result", ""), re.I),
         "## Result should state the decision: accept, reject or inconclusive")


@c.test("results.json: complete and self-consistent (values inside their CIs, difference = after - before)",
        hint="Write it with write_results() (stats_tools.py). Each of before / after / difference has a value and "
             "a ci95 [lo, hi] with lo <= value <= hi; at least 1000 resamples; n = number of samples.")
def _():
    r = results()
    for k in ("metric", "unit", "better", "n", "before", "after", "difference", "bootstrap", "acceptance", "decision"):
        c.ok(k in r, f"results.json has no key '{k}'")
    c.ok(r["better"] in ("lower", "higher"),
         "'better' must be \"lower\" or \"higher\" (write_results saves better=\"closer\" as \"lower\")")
    c.ok(isinstance(r["n"], int) and r["n"] >= 20, "'n' should be the number of samples (at least 20)")
    for k in ("before", "after", "difference"):
        v, ci = r[k].get("value"), r[k].get("ci95")
        c.ok(isinstance(ci, list) and len(ci) == 2, f"{k}.ci95 should be [lo, hi]")
        c.ok(ci[0] - 1e-6 <= v <= ci[1] + 1e-6, f"{k}: value {v} is outside its CI {ci}")
    c.near(r["difference"]["value"], r["after"]["value"] - r["before"]["value"], 1e-3,
           what="difference.value (should be after - before)")
    b = r["bootstrap"]
    c.ok(b.get("method") in ("moving-block", "iid") and int(b.get("n_boot", 0)) >= 1000 and "seed" in b,
         "bootstrap should say method (moving-block or iid), n_boot >= 1000 and the seed")


AVAIL_LIMIT = -0.10        # the example's guard-rail, fixed in its proposal: availability may drop by <= 10 points


def is_example(r):
    """The worked example (idea 1), whatever the student called it in results.json."""
    if r.get("project") == "min-satellites":
        return True
    try:
        if "min-satellites" in git("rev-parse --abbrev-ref HEAD"):
            return True
        diff = git("diff base..HEAD -- gps_pkg/gps_pkg/nodes/gps_node.py")
    except CheckFailed:
        diff = ""
    added = "\n".join(ln for ln in diff.splitlines() if ln.startswith("+"))
    if re.search(r"num_sats|MIN_SAT|satellites", added, re.I):
        return True
    return "nmea_bench" in str(r.get("data", "")) and "target" not in r and "availability" in r.get("secondary", {})


def side(ci, limit, better):
    """'good' if the whole CI is on the good side of `limit`, 'bad' if entirely on the bad side, else None."""
    lo, hi = float(ci[0]), float(ci[1])
    if better == "lower":
        return "good" if hi < limit else ("bad" if lo > limit else None)
    return "good" if lo > limit else ("bad" if hi < limit else None)


def guard_rails(r):
    """[(name, ci95 of the difference, limit, better)] — every secondary metric that has a 'limit'
    (and, for the example, the availability limit of its proposal)."""
    out = []
    for name, m in (r.get("secondary") or {}).items():
        if isinstance(m, dict) and "limit" in m:
            out.append((name, m["difference"]["ci95"], float(m["limit"]), m.get("better", "higher")))
    if is_example(r) and not any(g[0] == "availability" for g in out):
        av = (r.get("secondary") or {}).get("availability")
        c.ok(isinstance(av, dict) and "difference" in av,
             "the example's guard-rail (secondary.availability with its difference and CI) is missing")
        out.append(("availability", av["difference"]["ci95"], AVAIL_LIMIT, "higher"))
    return out


def expected_decision(r):
    """The decision rule of the lesson (section 7): accept only when the primary CI is entirely on the
    better side of 0 AND every guard-rail CI stays on the good side of its limit; reject when the
    primary CI is entirely on the worse side or a guard-rail CI is entirely beyond its limit;
    otherwise inconclusive."""
    primary = side(r["difference"]["ci95"], 0.0, r["better"])
    guards = [(name, ci, lim, side(ci, lim, b)) for name, ci, lim, b in guard_rails(r)]
    if primary == "bad" or any(g[3] == "bad" for g in guards):
        return "reject", guards
    if primary == "good" and all(g[3] == "good" for g in guards):
        return "accept", guards
    return "inconclusive", guards


@c.test("results.json: the decision follows the acceptance rule (CI of the difference AND guard-rails)",
        hint="Lesson section 7: 'accept' only when the whole CI of the difference is on the 'better' side "
             "of 0 AND every guard-rail CI stays on the good side of its limit; 'reject' when a CI is "
             "entirely on the bad side; anything else (a CI that contains 0 or crosses a guard-rail "
             "limit) is 'inconclusive'.")
def _():
    r = results()
    d = r.get("decision")
    c.ok(d in ("accept", "reject", "inconclusive"), f"decision is {d!r}: use accept, reject or inconclusive")
    want, guards = expected_decision(r)
    lo, hi = r["difference"]["ci95"]
    why = f"CI of the difference [{lo}, {hi}] ({r['better']} is better)"
    for name, ci, lim, s in guards:
        why += f"; guard-rail {name}: CI of the difference {list(ci)}, limit {lim:+g}"
    c.ok(d == want, f"decision is {d!r} but the acceptance rule gives {want!r}: {why}")


def _self_test_decision_rule():
    """The example of the lab (Step 10): Δp95 CI below 0 but the availability CI crosses -10 points
    -> inconclusive. Run when the check starts: a broken rule must never reach the students."""
    ex = {"project": "min-satellites", "better": "lower", "difference": {"ci95": [-60.0, -20.0]},
          "secondary": {"availability": {"difference": {"ci95": [-0.139, -0.020]}}}}
    assert expected_decision(ex)[0] == "inconclusive", "decision rule: example should be inconclusive"
    ex["secondary"]["availability"]["difference"]["ci95"] = [-0.05, -0.02]
    assert expected_decision(ex)[0] == "accept"
    ex["secondary"]["availability"]["difference"]["ci95"] = [-0.20, -0.12]
    assert expected_decision(ex)[0] == "reject"
    ex["difference"]["ci95"] = [-5.0, 3.0]
    ex["secondary"]["availability"]["difference"]["ci95"] = [-0.05, -0.02]
    assert expected_decision(ex)[0] == "inconclusive"


def reference_example():
    import pynmea2
    truth = json.load(open(f"{DATA}/truth.json"))
    m_lat = 111_195.0
    acc_b, acc_a, err = [], [], []
    for line in open(f"{DATA}/nmea_bench.txt"):
        line = line.strip()
        if not line.startswith("$GPGGA"):
            continue
        try:
            m = pynmea2.parse(line, check=True)
        except pynmea2.ParseError:
            acc_b.append(False), acc_a.append(False), err.append(math.nan)
            continue
        pos = bool(m.lat) and bool(m.lon)
        q = int(m.gps_qual or 0)
        sats = int(m.num_sats) if m.num_sats else None
        ok = pos and q in (1, 2, 4, 5)
        acc_b.append(ok)
        acc_a.append(ok and (sats is None or sats >= 4))
        err.append(math.hypot((m.latitude - truth["lat"]) * m_lat,
                              (m.longitude - truth["lon"]) * m_lat * math.cos(math.radians(truth["lat"])))
                   if pos else math.nan)
    err, acc_b, acc_a = np.array(err), np.array(acc_b), np.array(acc_a)
    return (float(np.percentile(err[acc_b], 95)), float(np.percentile(err[acc_a], 95)),
            float(acc_b.mean()), float(acc_a.mean()), len(err), acc_b, acc_a)


@c.test("example project: results.json agrees with a re-measurement of nmea_bench.txt",
        hint="Run python3 measure_project.py again after your last change; the p95 values and the availability "
             "must come from the 1800 epochs of the file (corrupted lines count as epochs, not accepted).")
def _():
    r = results()
    if not is_example(r):
        c.skip("your project is not the example (idea 1, refuse fixes from fewer than 4 satellites)")
    p_b, p_a, a_b, a_a, n, acc_b, acc_a = reference_example()
    c.eq(r["n"], n, "results.json n (epochs)")
    c.near(r["before"]["value"], p_b, 0.05, what="before.value (p95, m)")
    c.near(r["after"]["value"], p_a, 0.05, what="after.value (p95, m)")
    av = r.get("secondary", {}).get("availability")
    c.ok(av, "secondary.availability is missing (the guard-rail metric)")
    c.near(av["before"]["value"], a_b, 0.002, what="availability before")
    c.near(av["after"]["value"], a_a, 0.002, what="availability after")
    w = r["difference"]["ci95"][1] - r["difference"]["ci95"][0]
    c.ok(r["bootstrap"].get("method") == "moving-block" and w > 30,
         f"the p95-difference CI is only {w:.1f} m wide: the errors are correlated in time, use the "
         f"moving-block bootstrap (60 s blocks) as in the proposal")
    # the guard-rail CI, recomputed here with YOUR block_bootstrap_ci on the reference epochs
    (bbci,) = need(stats(), "block_bootstrap_ci")
    bt = r["bootstrap"]
    ref = pair(bbci(n, lambda i: float(np.mean(acc_a[i]) - np.mean(acc_b[i])), int(bt.get("block_len", 60)),
                    int(bt.get("n_boot", 2000)), 0.05, int(bt.get("seed", 0))), "block_bootstrap_ci")
    got = av.get("difference", {}).get("ci95", [math.nan, math.nan])
    c.ok(abs(got[0] - ref[0]) < 0.01 and abs(got[1] - ref[1]) < 0.01,
         f"availability difference CI in results.json {got} does not match a re-computation "
         f"[{ref[0]:.4f}, {ref[1]:.4f}] (same epochs, block_len, n_boot, seed): run measure_project.py again")
    c.ok(ref[0] < AVAIL_LIMIT < ref[1], "the re-computed availability CI does not cross the -10 point limit "
                                         "(unexpected for nmea_bench.txt — ask the teacher)")
    c.eq(r["decision"], "inconclusive", "decision of the example (the availability CI crosses -10 points)")


# ---------------------------------------------------------------- the engineering part
@c.test("you work on a project branch in ~/navera",
        hint="cd ~/navera && git checkout -b project/<short-name>   (the check looks at the branch you are on)")
def _():
    c.ok(os.path.isdir(os.path.join(NAV, ".git")), "~/navera is not a git repository any more — ask the teacher")
    b = git("rev-parse --abbrev-ref HEAD")
    c.ok(b not in ("work", "main", "master", "HEAD"),
         f"you are on '{b}': create a project branch (git checkout -b project/<name>)")


@c.test("at least one commit since base, and nothing left uncommitted",
        hint="git add <your files> && git commit -m \"what and why\"; then `git status` must be clean.")
def _():
    n = int(git("rev-list --count base..HEAD") or 0)
    c.ok(n >= 1, "no commit since base on this branch")
    dirty = [ln for ln in git("status --porcelain").splitlines()
             if ln[3:] and not ln.startswith("??") and not ln[3:].startswith(IGNORED)]
    c.ok(not dirty, "uncommitted changes in ~/navera:\n       " + "\n       ".join(dirty[:8]))
    c.ok(changed_files(), "your commits change no file compared with base")


@c.test("your project adds or changes a test, and it passes on your branch",
        hint="Add a test_*.py file (e.g. in <package>/test/) to your commits. Run it: "
             "cd ~/navera && python3 -m pytest -q <the file>")
def _():
    tests = tests_changed()
    c.ok(tests, "no test_*.py file among your committed changes (git diff --name-only base)")
    unit = [t for t in tests if "/test/" in "/" + t]
    integ = [t for t in tests if t not in unit]
    if unit:
        code, out = sh(f"cd {NAV} && python3 -m pytest -q -p no:cacheprovider " + " ".join(unit), timeout=240)
        c.ok(code == 0, "your test(s) fail:\n" + out[-900:])
    for t in integ:                                   # e.g. navera_tools/tests/test_*.py: a script
        code, out = sh(f"cd {NAV} && timeout 280 python3 {t}", timeout=290)
        c.ok(code == 0, f"{t} fails:\n" + out[-900:])


@c.test("your test detects the problem: it FAILS on the base code",
        hint="A good test fails before the change and passes after. The check copies your test next to the "
             "base version of the package: if it still passes there, it does not test your change.")
def _():
    tests = tests_changed()
    c.ok(tests, "no test_*.py file among your committed changes yet")
    unit = [t for t in tests if "/test/" in "/" + t]
    if not unit:
        c.skip("no unit test in <package>/test/ (integration scripts are not re-run on base)")
    pkgs = sorted({t.split("/")[0] for t in unit} | {f.split("/")[0] for f in changed_files() if "/" in f})
    tmp = tempfile.mkdtemp(prefix="base_")
    try:
        code, out = sh(f"git -C {NAV} archive base {' '.join(pkgs)} | tar -x -C {tmp}", timeout=60)
        c.ok(code == 0, "could not extract the base version of your package(s):\n" + out[-300:])
        for t in unit:
            os.makedirs(os.path.dirname(os.path.join(tmp, t)), exist_ok=True)
            shutil.copy(os.path.join(NAV, t), os.path.join(tmp, t))
        pp = ":".join(os.path.join(tmp, p) for p in pkgs)
        code, out = sh(f"cd {tmp} && PYTHONPATH={pp}:$PYTHONPATH python3 -m pytest -q -p no:cacheprovider "
                       + " ".join(unit), timeout=240)
        c.ok(code != 0, "your test(s) also PASS on the base code — they do not detect the problem your "
                        "change solves")
        c.ok(code != 5, "pytest collected no test on the base code — are your tests named test_*?")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@c.test("NAVERA's own unit tests still pass in every package you touched",
        hint="cd ~/navera && python3 -m pytest -q <package>/test — read the first failure: did your change "
             "break something that worked?")
def _():
    pkgs = sorted({f.split("/")[0] for f in changed_files() if "/" in f})
    c.ok(pkgs, "your commits do not change any NAVERA package yet")
    with_tests = [p for p in pkgs if os.path.isdir(os.path.join(NAV, p, "test"))]
    if not with_tests:
        c.skip(f"the package(s) you touched ({', '.join(pkgs)}) have no unit-test folder")
    files = []
    for p in with_tests:
        for f in sorted(os.listdir(os.path.join(NAV, p, "test"))):
            if re.fullmatch(r"test_.*\.py", f) and not re.fullmatch(r"test_(flake8|pep257|copyright)\.py", f):
                files.append(f"{p}/test/{f}")
    code, out = sh(f"cd {NAV} && python3 -m pytest -q -p no:cacheprovider " + " ".join(files), timeout=280)
    c.ok(code == 0, f"unit tests of {', '.join(with_tests)} fail:\n" + out[-900:])


@c.test("my_project.patch: your change, exported after your last commit",
        hint="cd ~/navera && git diff base > ~/lessons/30-final-project/my_project.patch")
def _():
    c.file_exists("my_project.patch")
    text = open("my_project.patch", errors="replace").read()
    c.ok(text.startswith("diff --git"), "my_project.patch does not look like the output of `git diff base`")
    for f in changed_files():
        c.ok(f"b/{f}" in text, f"my_project.patch does not contain {f}: export it again after your last commit")
    code, out = sh(f"cd {NAV} && git apply --check -R {os.path.abspath('my_project.patch')}", timeout=30)
    c.ok(code == 0, "my_project.patch does not match your branch any more (did you commit after exporting it?) "
                    "— export it again:\n" + out[-300:])


_self_test_decision_rule()
c.run()
