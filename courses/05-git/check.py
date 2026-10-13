import contextlib
import io
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
TEACHER_NOTE = " (Your teacher reads these answers with a rubric: the check only verifies that you really answered.)"
HERE = os.getcwd()                                     # ~/lessons/05-git
REPO = os.path.join(HERE, "navera-lite-history")
BRANCH = "my-first-change"
REVIEW = "kenji/fewer-refusals"
# The repository comes from /data/academy/05-git/navera-lite-history.tar.gz, identical for everyone (fixed hashes).
MAIN_TIP = "1f76dac5891a593db12395f03f946f232513a629"
V01 = "7b00fee44cfb257129c43484c8405c5a2c9f991c"
TEAM = "@lite.example"                                 # the invented team's e-mails
EXAMPLE_IDS = {"Ana Souza", "Navi Swallow", "Your Name"}
EXAMPLE_MAILS = {"ana.souza@example.com", "navi.swallow@example.com", "you@example.com"}
GENERIC = {"wip", "update", "updates", "commit", "changes", "fix", "test", "stuff", "my commit", "first commit",
           "asdf", "edit", "modified", "changes from review", "review"}
PROBE = next((p for p in ("/academy/courses/05-git/files/probe_gate.py", os.path.join(HERE, "probe_gate.py"))
              if os.path.exists(p)), None)


# ---------------------------------------------------------------- helpers
def git(*args, cwd=REPO, env=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout.strip()


def git_ok(*args, cwd=REPO):
    code, out = git(*args, cwd=cwd)
    if code:
        raise CheckFailed(f"`git {' '.join(args)}` failed in navera-lite-history")
    return out


def need_repo():
    if not os.path.isdir(os.path.join(REPO, ".git")):
        raise CheckFailed("there is no navera-lite-history repository in ~/lessons/05-git yet — do lab Step 0")
    code, tip = git("rev-parse", "--verify", "--quiet", "refs/heads/main")
    if code:
        raise CheckFailed("the branch main has disappeared from navera-lite-history")
    if tip != MAIN_TIP:
        code, mine = git("log", "--format=%ae %s", f"{MAIN_TIP}..main")
        raise CheckFailed("main has moved: it must stay exactly as Step 0 extracted it" +
                          (f" (new on main: {mine.splitlines()[0]})" if code == 0 and mine else "") +
                          ". Your commits belong on my-first-change (lab Step 1 hints).")


def need_branch():
    need_repo()
    code, _ = git("rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}")
    if code:
        raise CheckFailed(f"there is no branch {BRANCH} in navera-lite-history yet (lab Step 1)")


def show(rev, path):
    code, out = git("show", f"{rev}:{path}")
    return out if code == 0 else None


def branch_commits():
    """Commits of the branch that are not on main, oldest first: [(hash, email, subject)]."""
    need_branch()
    out = git_ok("log", "--reverse", "--format=%H%x1f%ae%x1f%s", f"main..refs/heads/{BRANCH}")
    return [tuple(l.split("\x1f")) for l in out.splitlines() if l]


def files_of(h):
    return [f for f in git_ok("show", "--name-only", "--format=", h).splitlines() if f]


def quiet_load(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name)


def answers(*names):
    return need(quiet_load("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str):
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def run(fn, *args, seconds=20):
    def too_long(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, too_long)
    signal.alarm(seconds)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)
    except TimeoutError:
        raise CheckFailed(f"{fn.__name__}() did not finish in {seconds} s — is a loop endless (lo and hi never meet)?")
    except CheckFailed:
        raise
    except Exception as e:
        raise CheckFailed(f"{fn.__name__}() stopped with {type(e).__name__}: {e}")
    finally:
        signal.alarm(0)


def words(s):
    return re.findall(r"[A-Za-zÀ-ÿ']{2,}", str(s))


def predicted(name, value):
    c.ok(isinstance(value, str) and value.strip() != "", f"{name} is empty — write your guess (any honest guess is fine)")


def explained(name, value, *groups):
    c.ok(isinstance(value, str) and value.strip() != "", f"{name} is still empty")
    c.ok(len(words(value)) >= 8, f"{name} is very short — explain in one to three full sentences")
    low = value.lower()
    for keywords, idea in groups:
        c.ok(any(re.search(k, low) for k in keywords), f"{name} does not explain {idea} yet." + TEACHER_NOTE)


class Clone:
    """A private clone of the student's repository (their folder is never touched), placed in the lesson
    folder so that ../probe_gate.py and ../bisect_test.sh resolve as they do in navera-lite-history."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix=".check-", dir=HERE)
        code, out = git("clone", "-q", "--no-checkout", REPO, self.dir, cwd=HERE)
        if code:
            raise CheckFailed("could not copy navera-lite-history to test it (is the repository damaged?)")
        return self

    def checkout(self, rev):
        code, _ = git("checkout", "-q", "--force", rev, cwd=self.dir)
        if code:
            raise CheckFailed(f"could not check out {rev}")
        git("clean", "-q", "-fdx", cwd=self.dir)

    def probe(self, rev):
        """What probe_gate.py prints at rev ('7', '5'…), or None when that commit cannot be imported."""
        self.checkout(rev)
        r = subprocess.run(["python3", PROBE], cwd=self.dir, capture_output=True, text=True, timeout=60)
        return None if r.returncode == 3 else r.stdout.strip()

    def pytest(self, *paths):
        r = subprocess.run(["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths], cwd=self.dir,
                           capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)


def commit_named(sub):
    """Full hash of the commit of main whose subject is exactly sub (computed, not stored)."""
    code, out = git("log", "--format=%H%x1f%s", "main")
    for line in out.splitlines():
        h, s = line.split("\x1f")
        if s == sub:
            return h
    raise CheckFailed("the history of main is not the one of Step 0's archive")


# ---------------------------------------------------------------- session 1: reviewer
@c.test("Step 1: git knows who you are (git config --global)",
        hint='git config --global user.name "…" and user.email "…", with YOUR name — not an example of the course.')
def _():
    _, name = git("config", "--global", "user.name", cwd=HERE)
    _, email = git("config", "--global", "user.email", cwd=HERE)
    c.ok(name != "", "user.name is not set")
    c.ok(name not in EXAMPLE_IDS and not email.endswith(TEAM), f"user.name is {name!r}: use your own name")
    c.ok("@" in email and "." in email.split("@")[-1], f"user.email = {email!r} does not look like an e-mail address")
    c.ok(email not in EXAMPLE_MAILS, "user.email is still the example of the course: write your own (it can be invented)")


HEADERS = [("@@ -1,4 +1,6 @@", (1, 4, 1, 6)), ("@@ -120,9 +121,7 @@ def check_settings(s):", (120, 9, 121, 7)),
           ("@@ -0,0 +1,12 @@", (0, 0, 1, 12)), ("@@ -7 +7 @@ x = 1", (7, 1, 7, 1)), ("@@ -33,0 +34,2 @@", (33, 0, 34, 2))]


@c.test("TODO 1: hunk_header() reads hunk headers it has never seen",
        hint="Lesson §3: '-a,b' is the old start and count, '+c,d' the new ones. Split the line on spaces, drop the "
             "sign, split on ','. A missing count means 1 — but a written 0 means 0.")
def _():
    (hh,) = need(quiet_load("detective.py"), "hunk_header")
    for line, want in HEADERS:
        got = run(hh, line)
        c.ok(isinstance(got, (tuple, list)) and len(got) == 4,
             f"hunk_header({line!r}) should return 4 numbers, got {got!r}")
        c.ok(all(isinstance(x, int) and not isinstance(x, bool) for x in got),
             f"hunk_header({line!r}) returned {tuple(got)!r}: the four numbers must be ints (int(\"78\") is 78)")
        if tuple(got) != want and any(w == 0 and g == 1 for w, g in zip(want, got)):
            raise CheckFailed(f"hunk_header({line!r}) gives {tuple(got)!r}: a count written as 0 is 0 "
                              "(only a count that is LEFT OUT means 1)")
        c.ok(tuple(got) == want, f"hunk_header({line!r}) gives {tuple(got)!r} — not the right numbers")


UNSEEN_PATCH = """diff --git a/docs/notes.md b/docs/notes.md
index 3b18e51..a7f2c40 100644
--- a/docs/notes.md
+++ b/docs/notes.md
@@ -1,6 +1,6 @@
 # Notes

---- separator
+++ counter
 First line.
 Second line.
 Third line.
@@ -20,2 +20,4 @@ Twenty.
 Twenty-one.
 Twenty-two.
+Twenty-two and a half.
+-- a dash comment
diff --git a/navera_lite/new_part.py b/navera_lite/new_part.py
new file mode 100644
index 0000000..e69de29
--- /dev/null
+++ b/navera_lite/new_part.py
@@ -0,0 +1,3 @@
+\"\"\"A new part.\"\"\"
+
+VALUE = 3
diff --git a/old.txt b/old.txt
deleted file mode 100644
index 5626abf..0000000
--- a/old.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-one
-two
\\ No newline at end of file
"""
UNSEEN_STAT = {"docs/notes.md": (3, 1), "navera_lite/new_part.py": (3, 0), "old.txt": (0, 2)}   # = git apply --numstat


@c.test("TODO 2: diff_stat() counts a patch it has never seen exactly as git does",
        hint="Lesson §3. The path is after ' b/' on the 'diff --git' line. Count + and − lines only INSIDE hunks "
             "(after an @@ line, until the next 'diff --git'): a removed line '-- separator' looks like '--- …' "
             "and an added '++ counter' looks like '+++ …'.")
def _():
    (ds,) = need(quiet_load("detective.py"), "diff_stat")
    got = run(ds, UNSEEN_PATCH)
    c.ok(isinstance(got, dict), f"diff_stat should return a dict {{path: (added, removed)}}, got {type(got).__name__}")
    got = {k: tuple(v) if isinstance(v, (list, tuple)) else v for k, v in got.items()}
    for p in UNSEEN_STAT:
        if p not in got:
            near = [k for k in got if str(k).endswith(p) or p.endswith(str(k))]
            raise CheckFailed(f"the file {p} is missing from your result" +
                              (f" (you wrote {near[0]!r}: take the path after ' b/' of the diff --git line)" if near
                               else " — is the path taken from its 'diff --git' line? (a deleted file has +++ /dev/null)"))
    extra = [k for k in got if k not in UNSEEN_STAT]
    c.ok(not extra, f"your result has keys that are not files of the patch: {extra}")
    n = got["docs/notes.md"]
    if n == (2, 0):
        raise CheckFailed("docs/notes.md: you skip every line that starts with '---' or '+++', but inside a hunk "
                          "'---- separator' is a removed line '--- separator' (count only inside hunks)")
    if n == (UNSEEN_STAT["docs/notes.md"][0] + 1, UNSEEN_STAT["docs/notes.md"][1] + 1):
        raise CheckFailed("docs/notes.md: one line too many on each side — you count the header lines --- a/… and "
                          "+++ b/… as changes (count only inside hunks)")
    for p, want in UNSEEN_STAT.items():
        c.ok(got[p] == want, f"{p}: you count {got[p]!r} (added, removed) — git apply --numstat says otherwise. "
                             "Run python3 run_lab.py stat on a patch to compare line by line")


@c.test("Steps 3–4: two dots and three dots, and what Kenji's patch would do (numbers)",
        hint="Step 3: count the file lines of the two `git diff --stat` commands. Step 4: the gate is v_max × 1 s + "
             "margin with Kenji's margin; for the timer, trace Kenji's check() second by second (> is strict).")
def _():
    two, three, why, gate1, t = answers("TWO_DOT_FILES", "THREE_DOT_FILES", "EXPLAIN_DOTS", "KENJI_GATE_1S_M",
                                        "SPOOF_ACCEPTED_AT_S")
    two, three = number(two, "TWO_DOT_FILES"), number(three, "THREE_DOT_FILES")
    if (two, three) == (5, 6):
        raise CheckFailed("TWO_DOT_FILES and THREE_DOT_FILES are swapped")
    c.ok(two == 6, f"TWO_DOT_FILES = {two:g} is not what `git diff --stat main..{REVIEW}` lists")
    c.ok(three == 5, f"THREE_DOT_FILES = {three:g} is not what `git diff --stat main...{REVIEW}` lists")
    explained("EXPLAIN_DOTS", why, ((r"merge.?base", r"fork", r"left", r"split", r"since", r"start", r"only", r"branch did",
                                     r"his (own )?(work|change)", r"kenji'?s"), "what three dots show (only Kenji's work)"),
              ((r"main", r"snapshot", r"tip", r"revers", r"newer", r"both", r"two dots", r"\.\.(?!\.)"),
               "why two dots show more (main's newer commits)"))
    g = number(gate1, "KENJI_GATE_1S_M")
    if g == 150:
        raise CheckFailed("KENJI_GATE_1S_M = 150 is the gate with main's margin (50 m): use Kenji's new margin")
    if g == 500:
        raise CheckFailed("KENJI_GATE_1S_M = 500 is only the margin: the gate is v_max × elapsed + margin")
    c.ok(g == 600, f"KENJI_GATE_1S_M = {g:g} — the gate is max_speed_mps × 1 s + Kenji's gps_jump_margin_m")
    t = number(t, "SPOOF_ACCEPTED_AT_S")
    if t == 11:
        raise CheckFailed("SPOOF_ACCEPTED_AT_S = 11: at t = 11 s, 11 − 1 = 10 is not > 10.0 — the test is strict")
    if t in (10, 1):
        raise CheckFailed(f"SPOOF_ACCEPTED_AT_S = {t:g}: refused_since_s is the time of the FIRST refusal (t = 1 s); "
                          "trace check() second by second")
    c.ok(t == 12, f"SPOOF_ACCEPTED_AT_S = {t:g} — trace Kenji's check(): first refusal at t = 1 s, then which t "
                  "makes t − refused_since_s > 10.0?")


HUNKS = {1: ("README.md", "accept"), 2: ("navera_lite.yaml", "reject"), 3: ("navera_lite/geo.py", "accept"),
         4: ("navera_lite/guard.py", "reject"), 5: ("tests/test_guard.py", "reject")}
WHY = {1: ((r"typo", r"spell", r"receive", r"word", r"text", r"doc"), "that it is only a spelling fix"),
       2: ((r"600", r"150", r"margin", r"500"), "what the larger margin does to the gate, with numbers"),
       3: ((r"constant", r"same", r"6371", r"unchanged", r"value", r"earth_radius"), "why the result does not change"),
       4: ((r"10 ?s", r"10 seconds", r"ten", r"patient", r"wait", r"\bany\b", r"spoof", r"12"), "what a patient spoofer can do"),
       5: ((r"test",), "what is removed")}


@c.test("Step 4: review.md — a verdict and a reason for each hunk",
        hint="Lesson §3: does it do what it says and only that, is it correct (tests!), is it safe (does it weaken "
             "the gate?), is it measured. Reject a hunk if the answer to one question is no.")
def _():
    c.file_exists("review.md")
    text = open("review.md", errors="replace").read()
    c.ok("(write here)" not in text, 'review.md still contains "(write here)"')
    parts = re.split(r"^##\s+", text, flags=re.M)
    sections = {}
    for p in parts[1:]:
        m = re.match(r"hunk\s*(\d)", p, re.I)
        if m:
            sections[int(m.group(1))] = p
    for n, (path, want) in HUNKS.items():
        c.ok(n in sections, f"review.md has no section '## Hunk {n} — {path}' (keep the headings)")
        s = sections[n]
        v = re.search(r"verdict\s*:\s*\**\s*(accept|reject)", s, re.I)
        c.ok(v is not None, f"hunk {n} ({path}): write 'Verdict: accept' or 'Verdict: reject'")
        why = re.search(r"why\s*:(.*)", s, re.I | re.S)
        why = why.group(1) if why else ""
        c.ok(len(words(why)) >= 6, f"hunk {n} ({path}): the Why is missing or very short — one to three sentences")
        c.ok(v.group(1).lower() == want, f"hunk {n} ({path}): not the verdict a careful reviewer gives — ask the four "
                                         "questions of lesson §3 again, one by one")
        keys, idea = WHY[n]
        c.ok(any(re.search(k, why.lower()) for k in keys), f"hunk {n} ({path}): your Why does not say {idea} yet")
    adv = re.search(r"^##\s*advice.*?$(.*)", text, re.I | re.M | re.S)
    c.ok(adv is not None and len(words(adv.group(1))) >= 15, "the '## Advice to the author' section is missing or "
                                                             "shorter than two sentences")
    c.ok(any(k in adv.group(1).lower() for k in ("split", "separate", "one concern", "measur", "test", "cause", "bisect")),
         "the advice should say how to split the change, or what to measure or test first")


@c.test("Step 5: only the hunks you accepted are on my-first-change, committed",
        hint="git apply --include=<path> (one per accepted file) ../review_me.patch, run the tests, then git add + git "
             "commit. Wrong file applied? git restore <file> (not committed yet) or git restore --source=main <file> "
             "and commit (already committed).")
def _():
    need_branch()
    tip = f"refs/heads/{BRANCH}"

    def worktree(path):
        try:
            return open(os.path.join(REPO, path), errors="replace").read().strip()    # as show() strips
        except OSError:
            return None

    # The rejected hunks must be absent from the branch AND from the working folder (applied, not committed).
    readers = [("on your branch", lambda p: show(tip, p))]
    if git("symbolic-ref", "-q", "HEAD")[1] == tip:                   # not during a bisect or a detached look
        readers.append(("in your working folder (not committed)", worktree))
    for where, read in readers:
        c.ok(read("navera_lite.yaml") == show("main", "navera_lite.yaml"),
             f"navera_lite.yaml {where} differs from main: a reviewer who changes a gate value without a "
             "measurement has the same problem as Kenji" + (" — git restore navera_lite.yaml" if read is worktree else ""))
        c.ok("refused_since_s > 10.0" not in (read("navera_lite/guard.py") or ""),
             f"navera_lite/guard.py {where} has Kenji's 10 s timer")
        c.ok("def test_jump_gate_refuses_a_500_m_jump" in (read("tests/test_guard.py") or ""),
             f"tests/test_guard.py {where} lost test_jump_gate_refuses_a_500_m_jump")
    c.ok("you receive" in (show(tip, "README.md") or ""), "README.md on your branch does not have the accepted change yet")
    geo = show(tip, "navera_lite/geo.py") or ""
    c.ok("2 * EARTH_RADIUS_M * math.asin" in geo, "navera_lite/geo.py on your branch does not have the accepted change yet")
    commits = branch_commits()
    geo_commits = [h for h, _, _ in commits if "navera_lite/geo.py" in files_of(h)]
    c.ok(geo_commits, "no commit of yours changes navera_lite/geo.py: did you commit after git apply?")
    for h in geo_commits:
        other = [f for f in files_of(h) if f in ("navera_lite/guard.py", "navera_lite.yaml", "tests/test_guard.py")]
        c.ok(not other, f"commit {h[:7]} mixes the geo.py change with {', '.join(other)}: one concern per commit")
        c.ok("README.md" not in files_of(h),
             f"commit {h[:7]} mixes the geo.py refactor with the README typo: two concerns, so two commits. "
             "Undo the commit but keep the changes (git reset --soft HEAD~1), then add and commit each file alone")
    code, dirty = git("status", "--porcelain", "--untracked-files=no", "--", "README.md", "navera_lite/geo.py")
    c.ok(dirty == "", "an accepted change is applied but not committed:\n" + dirty)


@c.test("Step 5: your commits — on my-first-change, made by you, with clear messages; main untouched",
        hint='One concern per commit; a subject says WHAT changed in < 72 characters, e.g. "refactor(geo): …". '
             "Fix the last message (before sharing it): git commit --amend -m \"…\".")
def _():
    commits = branch_commits()
    c.ok(commits, f"{BRANCH} has no commit of yours yet")
    _, email = git("config", "--global", "user.email", cwd=HERE)
    for h, mail, subject in commits:
        s = subject.strip()
        if s.startswith("Revert \""):
            continue
        c.ok(not mail.endswith(TEAM), f"commit {h[:7]} was made by someone of the invented team, not by you")
        c.ok(len(s) >= 10, f'commit {h[:7]}: "{s}" is too short to say what changed')
        c.ok(s.lower().rstrip(".") not in GENERIC, f'commit {h[:7]}: "{s}" does not say what changed')
        c.ok(len(s) <= 72, f"commit {h[:7]}: the subject has {len(s)} characters — keep it under 72")
    c.ok(any(mail == email for _, mail, _ in commits),
         f"none of your commits has your e-mail ({email}) — set your identity BEFORE committing")
    for h, _, s in commits:
        if s.startswith("Revert \""):
            continue
        if re.match(r"^[a-z]+\([^)]*,[^)]*\): \S", s):
            raise CheckFailed(f'commit {h[:7]}: "{s}" has two scopes — one scope per commit, e.g. docs(readme): … '
                              "(a comma in the scope usually means two concerns in one commit)")
        c.ok(re.match(r"^[a-z]+(\([\w./-]+\))?: \S", s),
             f'commit {h[:7]}: "{s}" does not follow the type(scope): summary style of lesson §2')


# ---------------------------------------------------------------- session 2: detective
def make_cases():
    """(n, first bad index) pairs for the unseen histories."""
    cases = []
    for n in (1, 2, 3, 5, 7, 30, 33, 100):
        for bad in sorted({0, n // 3, n // 2, n - 2, n - 1} if n > 1 else {0}):
            if 0 <= bad < n:
                cases.append((n, bad))
    return cases


@c.test("TODO 3: first_bad() finds the first bad commit by binary search, on histories it has never seen",
        hint="Lesson §4: two positions lo and hi with the answer always between them; test the middle; each answer "
             "keeps one half. Redo the lesson's 16-commit table by hand, then see the Step 6 hints.")
def _():
    (fb,) = need(quiet_load("detective.py"), "first_bad")
    for n, bad in make_cases():
        commits = [f"{(7919 * (i + 3)) % 65521:05x}" for i in range(n)]      # hash-like strings, oldest first
        asked = []

        def is_bad(x, commits=commits, bad=bad, asked=asked):
            if x not in commits:
                raise CheckFailed(f"is_bad() was called with {x!r}, which is not one of the commits — "
                                  "call it with commits[i], not with the position i")
            asked.append(x)
            if len(asked) > 64:
                raise CheckFailed("is_bad() was called more than 64 times — is the loop endless? (when the middle "
                                  "is good, the answer is AFTER it)")
            return commits.index(x) >= bad

        got = run(fb, commits, is_bad)
        if isinstance(got, int) and not isinstance(got, bool) and got == bad:
            raise CheckFailed("first_bad returns the POSITION of the first bad commit: return the commit itself, "
                              "commits[position]")
        c.ok(got == commits[bad], f"with {n} commits, first bad = number {bad + 1}: first_bad returns "
                                  f"{'the commit number ' + str(commits.index(got) + 1) if got in commits else repr(got)}")
        limit = math.ceil(math.log2(n)) if n > 1 else 0
        c.ok(commits[-1] not in asked, "first_bad tests the last commit, but it is known to be bad: "
                                       "never spend a test on it")
        c.ok(len(asked) <= limit, f"with {n} commits it used {len(asked)} tests; binary search needs at most "
                                  f"⌈log₂ {n}⌉ = {limit} (are you testing one by one?)")


@c.test("Step 6: the bug report — the probe on your branch and at v0.1, and your prediction",
        hint="Inside navera-lite-history: python3 ../probe_gate.py on your branch; then git switch --detach v0.1, "
             "run it again, and git switch my-first-change to come back.")
def _():
    pred, pb, pv, pt = answers("PREDICT_PROBE", "PROBE_BRANCH", "PROBE_V01", "PREDICT_TESTS")
    predicted("PREDICT_PROBE", pred)
    predicted("PREDICT_TESTS", pt)
    c.ok(number(pb, "PROBE_BRANCH") == 7, f"PROBE_BRANCH = {pb!r} is not what probe_gate.py prints on main's code "
                                          "(run it on your branch BEFORE Step 8 fixes it)")
    c.ok(number(pv, "PROBE_V01") == 5, f"PROBE_V01 = {pv!r} is not what probe_gate.py prints at v0.1")


def run_script(clone, rev):
    clone.checkout(rev)
    r = subprocess.run(["bash", os.path.join(HERE, "bisect_test.sh")], cwd=clone.dir, capture_output=True, text=True,
                       timeout=60)
    return r.returncode


@c.test("TODO 4: bisect_test.sh answers 0 for a good commit, 1 for a bad one, 125 for a broken one",
        hint="Lesson §4's worked script: keep what the probe prints with $(…), answer 125 when the probe itself "
             "fails (||), 0 when it printed 5, 1 otherwise. Do not cd anywhere: git bisect runs the script inside "
             "the commit to test.")
def _():
    need_repo()
    c.file_exists("bisect_test.sh")
    c.ok(PROBE is not None, "probe_gate.py is missing from ~/lessons/05-git (↺ Reset lab files brings it back)")
    broken = commit_named("wip: guard status line")
    with Clone() as cl:
        code = run_script(cl, V01)
        c.ok(code != 255, "bisect_test.sh still exits 255: it is not written yet")
        c.ok(code == 0, f"at v0.1 (a good commit) bisect_test.sh exits with {code}, not 0")
        code = run_script(cl, MAIN_TIP)
        c.ok(code != 125, "on main (a bad commit that runs fine) it exits with 125 (skip): 125 is only for a commit "
                          "that cannot be tested")
        c.ok(1 <= code <= 127, f"on main (a bad commit) it exits with {code}, not 1")
        code = run_script(cl, broken)
        c.ok(code == 125, f"on the commit '{broken[:7]} wip: guard status line', whose code does not even import, it "
                          f"exits with {code} instead of 125 — such a commit is not bad, it cannot be tested")


def bisect_log():
    c.file_exists("bisect.log")
    text = open("bisect.log", errors="replace").read()
    m = re.search(r"^# first bad commit: \[([0-9a-f]{40})\]", text, re.M)
    c.ok(m is not None, "bisect.log has no '# first bad commit' line: save it with git bisect log > ../bisect.log "
                        "AFTER git bisect run finished, and before git bisect reset")
    tested = re.findall(r"^# (?:good|bad|skip): \[([0-9a-f]{40})\]", text, re.M)
    tested = [h for h in tested if h not in (MAIN_TIP, V01)]
    return m.group(1), tested, text


@c.test("Step 7: git bisect found the first bad commit — FIRST_BAD, TESTS_RUN and bisect.log",
        hint="git bisect start main v0.1, git bisect run ../bisect_test.sh, then git bisect log > ../bisect.log and "
             "git bisect reset. FIRST_BAD: the hash bisect names. TESTS_RUN: the good/bad/skip lines of bisect.log.")
def _():
    need_branch()
    first, word, why = answers("FIRST_BAD", "TESTS_RUN", "EXPLAIN_BISECT")
    h = str(first).strip().lower()
    c.ok(re.fullmatch(r"[0-9a-f]{7,40}", h) is not None, f"FIRST_BAD = {first!r}: copy the hash (at least 7 characters)")
    code, full = git("rev-parse", "--verify", "--quiet", h + "^{commit}")
    c.ok(code == 0, f"FIRST_BAD = {h!r} is not a commit of navera-lite-history")
    code, _ = git("merge-base", "--is-ancestor", V01, full)
    in_range = code == 0 and full != V01 and git("merge-base", "--is-ancestor", full, "main")[0] == 0
    c.ok(in_range, f"FIRST_BAD = {h[:7]} is not one of the suspects between v0.1 and main")
    with Clone() as cl:
        here, before = cl.probe(full), cl.probe(full + "^")
    if here is None:
        raise CheckFailed(f"{h[:7]} cannot even be imported: it is a BROKEN commit, not the bad one. If your bisect "
                          "named it, your script called it bad: it must exit 125 for it (TODO 4)")
    c.ok(here != "5", f"{h[:7]} still behaves well (the probe prints 5 there): the regression comes later")
    c.ok(before == "5", f"{h[:7]} is bad, but so is the commit before it: it is not the FIRST bad commit")
    found, tested, text = bisect_log()
    c.ok(found == full, "bisect.log names another first bad commit than FIRST_BAD: save the log of your last, "
                        "correct bisect")
    c.ok(re.search(r"^# skip:", text, re.M), "bisect.log has no skipped commit: did your bisect_test.sh exit 125 on the "
                                             "broken commit? (redo the bisect with the corrected script)")
    c.ok(number(word, "TESTS_RUN") == len(tested), f"TESTS_RUN = {word!r}, but bisect.log shows a different number "
                                                   "of tested commits (count the '# good', '# bad' and '# skip' lines, "
                                                   "without the two of the start, main and v0.1, and without the last line, '# first bad commit')")
    c.ok(not os.path.exists(os.path.join(REPO, ".git", "BISECT_START")),
         "the bisect is still running: git bisect reset brings you back to your branch")
    explained("EXPLAIN_BISECT", why, ((r"half", r"halv", r"binary", r"log", r"divid"), "why so few tests (halving)"),
              ((r"125", r"skip", r"broken", r"cannot", r"can't", r"import", r"syntax", r"compile"),
               "what exit 125 does for the broken commit"))


@c.test("TODO 5: tests/test_regression.py fails on main's code and passes on your branch",
        hint="Copy ../test_regression.py into tests/, write asserts for EACH fix of lesson 1's table (True = accepted), "
             "and commit it on my-first-change. It must fail on main (the gate never widens) and pass after Step 8.")
def _():
    need_branch()
    src = show(f"refs/heads/{BRANCH}", "tests/test_regression.py")
    c.ok(src is not None, "tests/test_regression.py is not committed on my-first-change "
                          "(cp ../test_regression.py tests/, write it, git add, git commit)")
    c.ok("NotImplementedError" not in src, "tests/test_regression.py on your branch is still the TODO (it raises "
                                           "NotImplementedError)")
    c.ok("assert" in src, "tests/test_regression.py has no assert")
    with Clone() as cl:
        cl.checkout(f"origin/{BRANCH}")
        code, last = cl.pytest("tests/test_regression.py")
        c.ok(code == 0, f"on your branch, tests/test_regression.py fails: {last[0]}")
        cl.checkout("main")
        with open(os.path.join(cl.dir, "tests", "test_regression.py"), "w") as f:
            f.write(src)
        code, last = cl.pytest("tests/test_regression.py")
        c.ok(code != 0, "on main's code your test PASSES: it would not have caught the regression. Assert the "
                        "gate's answer for every fix, including the 500 m fixes that must be accepted after 5 s")


@c.test("Step 8: the regression is undone on my-first-change, and every test passes",
        hint="git revert <FIRST_BAD> (with --no-edit) makes a new commit that undoes it; then python3 ../probe_gate.py "
             "prints 5 and python3 -m pytest -q tests passes. EXPLAIN_REVERT_COST: git show --stat HEAD shows what "
             "else the revert removed.")
def _():
    need_branch()
    _, _, cause, cost = answers("FIRST_BAD", "TESTS_RUN", "EXPLAIN_CAUSE", "EXPLAIN_REVERT_COST")
    with Clone() as cl:
        out = cl.probe(f"origin/{BRANCH}")
        c.ok(out is not None, "on your branch navera_lite/guard.py cannot even be imported")
        c.ok(out == "5", f"on your branch the probe prints {out}, not 5: the regression is still there")
        code, last = cl.pytest("tests")
        c.ok(code == 0, f"on your branch the tests fail: {last[0]}")
    explained("EXPLAIN_CAUSE", cause, ((r"prev", r"previous", r"elapsed", r"last fix", r"every fix", r"refused fix"),
                                       "which time the bad line uses"),
              ((r"lock", r"never", r"widen", r"for ever", r"forever", r"150", r"stuck"), "why GPS stays refused"),
              ((r"kenji", r"symptom", r"timer", r"10 ?s", r"patch", r"cause"), "what it says about Kenji's patch"))
    explained("EXPLAIN_REVERT_COST", cost, ((r"refused_for", r"feature", r"operator", r"display", r"changelog", r"its test",
                                             r"test_refused"), "what else the revert removed"),
              ((r"whole", r"entire", r"concern", r"mix", r"forward", r"split", r"separate", r"one line", r"two commits",
                r"only the"), "how one-concern commits or a fix forward would have avoided it"))


@c.test("Step 9: disaster and rescue — the reflog brought your commits back; nothing left uncommitted",
        hint="git reset --hard HEAD~2 on your branch, then git reflog, then git reset --hard HEAD@{1} (or the hash the "
             "reflog shows). git status must say: nothing to commit.")
def _():
    need_branch()
    (why,) = answers("EXPLAIN_RESCUE")
    _, log = git("reflog", "show", "--format=%gs", f"refs/heads/{BRANCH}")
    c.ok(re.search(r"reset: moving to HEAD[~^]", log), "the reflog of my-first-change shows no `git reset --hard "
                                                     "HEAD~2`: do the disaster of Step 9 (then the rescue)")
    c.ok(not re.match(r"reset: moving to HEAD[~^]", log.splitlines()[0]) and
         show(f"refs/heads/{BRANCH}", "tests/test_regression.py") is not None,
         "your branch is still where the reset left it: git reflog, then git reset --hard HEAD@{1} (the line "
         "just below the reset)")
    c.ok(os.path.isfile(os.path.join(REPO, "navera_lite", "guard.py")), "navera_lite/guard.py is still deleted — "
                                                                        "git restore brings it back")
    _, head = git("symbolic-ref", "-q", "HEAD")
    c.ok(head == f"refs/heads/{BRANCH}", f"you are not on {BRANCH} (git switch {BRANCH})")
    _, dirty = git("status", "--porcelain", "--untracked-files=no")
    c.ok(dirty == "", "these files are changed but not committed:\n" + dirty)
    explained("EXPLAIN_RESCUE", why, ((r"reflog",), "the reflog"),
              ((r"still", r"kept", r"not (deleted|lost|gone)", r"object", r"label", r"pointer", r"moved", r"until",
                r"garbage", r"expire", r"days"), "why the commits were not really gone"),
              ((r"uncommitted", r"not committed", r"never committed", r"edits", r"working", r"saved"),
               "what git could not have given back"))


@c.test("Step 10: my_changes.patch — your branch as a patch that applies to main",
        hint="Inside navera-lite-history: git format-patch main --stdout > ../my_changes.patch (after Step 9).")
def _():
    need_branch()
    c.file_exists("my_changes.patch")
    text = open("my_changes.patch", errors="replace").read()
    c.ok("diff --git" in text, "my_changes.patch contains no diff — was the command's output empty?")
    n_patch, n_branch = len(re.findall(r"^From [0-9a-f]{40} ", text, re.M)), len(branch_commits())
    c.ok(n_patch == n_branch, f"my_changes.patch holds {n_patch} commit(s), your branch has {n_branch}: "
                              "make it again after Step 9")
    for p in ("navera_lite/geo.py", "navera_lite/guard.py", "tests/test_regression.py"):
        c.ok(f"b/{p}" in text, f"my_changes.patch does not contain your change of {p} (make it again after Step 9)")
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(d, "index"))
        code, _ = git("read-tree", "main", env=env)
        c.ok(code == 0, "could not read main")
        code, _ = git("apply", "--cached", "--check", os.path.abspath("my_changes.patch"), env=env)
    c.ok(code == 0, "my_changes.patch does not apply cleanly to main (git apply --check fails)")


# Session 1 (Steps 0–5) earns "Reviewer"; the whole mission earns "Detective".
c.milestone("reviewer", "Step 1:", "TODO 1:", "TODO 2:", "Steps 3–4:", "Step 4:", "Step 5:",
            label="Session 1 complete: Reviewer badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("detective", "TODO", "Step", label="Mission complete: Reviewer and Detective badges earned")

c.run()
