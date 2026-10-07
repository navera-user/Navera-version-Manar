import os
import re
import subprocess
import tempfile

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
NAV = os.path.expanduser("~/navera")
BRANCH = "my-first-change"
TAG = "lab5"
ACADEMY_ID = ("NAVERA Academy", "academy@localhost")      # who made the base commit
GEO = "navera_common/navera_common/geo.py"
PARAMS = "navera_estimator/navera_estimator/config/estimator_params.yaml"
GPS_NODE = "gps_pkg/gps_pkg/nodes/gps_node.py"
GENERIC = {"auto-save before reset", "wip", "update", "updates", "commit", "changes", "fix", "test",
           "stuff", "my commit", "first commit", "asdf", "edit", "modified"}


def git(*args, env=None):
    r = subprocess.run(["git", "-C", NAV, *args], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout.strip()


def git_ok(*args):
    code, out = git(*args)
    if code != 0:
        raise CheckFailed(f"`git {' '.join(args)}` failed in ~/navera")
    return out


def need_branch():
    if not os.path.isdir(os.path.join(NAV, ".git")):
        raise CheckFailed("~/navera is not a git repository any more — did you delete .git?")
    code, _ = git("rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}")
    if code != 0:
        raise CheckFailed(f"there is no branch called {BRANCH} in ~/navera yet")


def branch_commits():
    """Commits on the branch that are not in the base, oldest first: [(hash, name, email, subject)]."""
    need_branch()
    out = git_ok("log", "--reverse", "--format=%H%x1f%an%x1f%ae%x1f%s", f"refs/tags/base..refs/heads/{BRANCH}")
    return [tuple(l.split("\x1f")) for l in out.splitlines() if l]


def changed_files(rev_range):
    return [l for l in git_ok("diff", "--name-only", rev_range).splitlines() if l]


def show(rev, path):
    code, out = git("show", f"{rev}:{path}")
    return out if code == 0 else None


def answers():
    return load_student("answers.py")


@c.test("git knows your name and e-mail (git config --global)",
        hint='git config --global user.name "…" and user.email "…" — with YOUR name, not the example of the course.')
def _():
    _, name = git("config", "--global", "user.name")
    _, email = git("config", "--global", "user.email")
    c.ok(name != "", "user.name is not set")
    c.ok(name not in (ACADEMY_ID[0], "Your Name", "Navi Swallow", "Salim Al Harthy", "Aisha Al Balushi"),
         f"user.name is {name!r}: use your own name")
    c.ok("@" in email and "." in email.split("@")[-1], f"user.email = {email!r} does not look like an e-mail address")
    c.ok(email not in ("you@example.com", "navi.swallow@example.com", "salim.alharthy@example.com", "aisha@example.com"),
         "user.email is still the example of the course: write your own (it can be invented)")


@c.test(f"the branch {BRANCH} has at least 3 commits of yours on top of base",
        hint="README line, GPS log message, then the reviewed part of the patch: three commits. "
             "git log --oneline --graph --decorate shows them.")
def _():
    commits = branch_commits()
    c.ok(len(commits) >= 3, f"{BRANCH} has {len(commits)} commit(s) on top of base, expected at least 3")
    _, email = git("config", "--global", "user.email")
    for h, name, mail, _ in commits:
        c.ok((name, mail) != ACADEMY_ID, f"commit {h[:7]} was not made by you (auto-save of a Reset?)")
    c.ok(any(mail == email for _, _, mail, _ in commits),
         f"none of the commits has your e-mail ({email}) — set your identity BEFORE committing")


@c.test("commit messages: specific, short, and at least one in the type(scope): summary style",
        hint='A subject says WHAT changed in < 72 characters, e.g. "fix(gps): clearer start-up log message". '
             "To fix the last message: git commit --amend -m \"…\" (only before you share it).")
def _():
    commits = branch_commits()
    c.ok(commits, f"{BRANCH} has no commits yet")
    for h, _, _, subject in commits:
        s = subject.strip()
        c.ok(len(s) >= 10, f'commit {h[:7]}: "{s}" is too short to say what changed')
        c.ok(s.lower().rstrip(".") not in GENERIC, f'commit {h[:7]}: "{s}" does not say what changed')
        c.ok(len(s) <= 72, f"commit {h[:7]}: the subject has {len(s)} characters — keep it under 72")
    c.ok(any(re.match(r"^[a-z]+(\([\w./-]+\))?: \S", s) for *_, s in commits),
         "no subject follows the NAVERA style type(scope): summary")


@c.test("ACADEMY_README.md has a new line, committed on the branch",
        hint="Add a line at the end of ~/navera/ACADEMY_README.md, save, git add, git commit.")
def _():
    need_branch()
    c.ok("ACADEMY_README.md" in changed_files(f"refs/tags/base...refs/heads/{BRANCH}"),
         f"ACADEMY_README.md is not changed by the commits of {BRANCH}")
    diff = git_ok("diff", f"refs/tags/base...refs/heads/{BRANCH}", "--", "ACADEMY_README.md")
    added = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
    c.ok(added, "no new (non-empty) line in ACADEMY_README.md")


@c.test("a log message of gps_node.py was changed, committed, and every changed .py file is valid Python",
        hint="Change only the text between the quotes of get_logger().info(\"Read thread started\"); "
             "python3 -m py_compile <file> prints nothing when the file is valid.")
def _():
    need_branch()
    files = changed_files(f"refs/tags/base...refs/heads/{BRANCH}")
    c.ok(GPS_NODE in files, f"{GPS_NODE} is not changed by the commits of {BRANCH}")
    diff = git_ok("diff", f"refs/tags/base...refs/heads/{BRANCH}", "--", GPS_NODE)
    c.ok("get_logger()" in diff, "the change in gps_node.py is not a log message (get_logger())")
    for f in files:
        if f.endswith(".py"):
            src = show(f"refs/heads/{BRANCH}", f)
            c.ok(src is not None, f"{f} was deleted on the branch")
            try:
                compile(src, f, "exec")
            except SyntaxError as e:
                raise CheckFailed(f"{f} line {e.lineno} has a syntax error on the branch: {e.msg}")


@c.test("review: the good part of review_me.patch (geo.py) is committed, alone in its commit",
        hint="git apply can leave a file out of a patch (see git apply --help, option --exclude). "
             "Then add + commit geo.py only: one concern per commit.")
def _():
    need_branch()
    src = show(f"refs/heads/{BRANCH}", GEO) or ""
    c.ok("return 2 * EARTH_RADIUS_M * math.asin" in src, "haversine_m() on the branch does not use EARTH_RADIUS_M yet")
    c.ok("2 * 6_371_000.0 * math.asin" not in src, "the literal 6_371_000.0 is still in haversine_m() on the branch")
    commits = branch_commits()
    geo_commits = [h for h, *_ in commits if GEO in git_ok("show", "--name-only", "--format=", h).splitlines()]
    c.ok(geo_commits, "no commit of yours changes geo.py")
    for h in geo_commits:
        files = [f for f in git_ok("show", "--name-only", "--format=", h).splitlines() if f]
        c.ok(files == [GEO], f"commit {h[:7]} changes {', '.join(files)} — the geo.py fix should be alone")


@c.test("review: the harmful change (gps_jump_margin_m) was NOT applied",
        hint="Compare with base: git diff base -- <path>. Not committed: git restore <path>. Already committed: "
             "git restore --source=base <path>, then commit that correction (or git revert the bad commit).")
def _():
    need_branch()
    c.ok(show(f"refs/heads/{BRANCH}", PARAMS) == show("refs/tags/base", PARAMS),
         f"estimator_params.yaml on {BRANCH} differs from base — the gate margin must stay as it was")
    try:
        with open(os.path.join(NAV, PARAMS)) as f:
            now = f.read()
    except OSError:
        raise CheckFailed("estimator_params.yaml is missing from ~/navera")
    c.ok("5000" not in now, "estimator_params.yaml in your folder still has the 5000 m margin")


@c.test("the branch work was not changed",
        hint="Your commits belong on my-first-change. If you committed on work by mistake: "
             "git switch work, git reset --hard base, git switch my-first-change.")
def _():
    code, n = git("rev-list", "--count", "refs/tags/base..refs/heads/work")
    c.ok(code == 0, "the branch work has disappeared")
    c.ok(n == "0", f"work has {n} commit(s) that are not in base")


@c.test(f"an annotated tag {TAG} marks a commit of your branch",
        hint=f"git tag -a {TAG} -m \"…\" on the last commit of {BRANCH}. A tag without -a has no message: "
             "delete it with git tag -d and make it again.")
def _():
    need_branch()
    code, _ = git("rev-parse", "--verify", "--quiet", f"refs/tags/{TAG}")
    c.ok(code == 0, f"there is no tag {TAG}")
    _, kind = git("cat-file", "-t", f"refs/tags/{TAG}")
    c.ok(kind == "tag", f"{TAG} is a lightweight tag — make an ANNOTATED one (-a, with a message)")
    _, target = git("rev-parse", f"refs/tags/{TAG}^{{commit}}")
    _, base = git("rev-parse", "refs/tags/base^{commit}")
    c.ok(target != base, f"{TAG} points at base — put it on one of YOUR commits")
    code, _ = git("merge-base", "--is-ancestor", target, f"refs/heads/{BRANCH}")
    c.ok(code == 0, f"{TAG} points at a commit that is not on {BRANCH}")


@c.test("my_changes.patch: your work exported as a patch that applies to base",
        hint="git format-patch (or git diff) from base to your branch, redirected with > into "
             "~/lessons/05-git/my_changes.patch. It must contain the README and gps_node.py changes.")
def _():
    c.file_exists("my_changes.patch")
    with open("my_changes.patch", errors="replace") as f:
        text = f.read()
    c.ok("diff --git" in text, "my_changes.patch contains no diff — was the command's output empty?")
    for p in ("ACADEMY_README.md", GPS_NODE):
        c.ok(f"a/{p}" in text, f"my_changes.patch does not contain the change of {p}")
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(d, "index"))
        code, _ = git("read-tree", "refs/tags/base", env=env)
        c.ok(code == 0, "could not read the base tree")
        code, _ = git("apply", "--cached", "--check", os.path.abspath("my_changes.patch"), env=env)
    c.ok(code == 0, "my_changes.patch does not apply cleanly to base (git apply --check fails)")


@c.test("geo.py is back and nothing is left uncommitted (clean working tree)",
        hint="git status shows what is changed. git restore <file> brings a file back as in the last commit.")
def _():
    c.ok(os.path.isfile(os.path.join(NAV, GEO)), f"{GEO} is still deleted — git restore can bring it back")
    dirty = git_ok("status", "--porcelain", "--untracked-files=no")
    c.ok(dirty == "", "these files are changed but not committed:\n" + dirty)


@c.test("answers.py: FIRST_COMMIT and NAVERA_SOURCE_COMMIT",
        hint="git log --oneline --decorate: FIRST_COMMIT is the first word of the line with YOUR first message. "
             "The base line has two hashes: the second one, inside the message, is the real NAVERA commit.")
def _():
    m = answers()
    first, src = need(m, "FIRST_COMMIT", "NAVERA_SOURCE_COMMIT")
    first = str(first).strip().lower()
    c.ok(len(first) >= 7, f'FIRST_COMMIT = "{first}" is too short: copy at least 7 characters')
    commits = branch_commits()
    c.ok(commits, f"{BRANCH} has no commits yet")
    _, base_hash = git("rev-parse", "refs/tags/base^{commit}")
    c.ok(not base_hash.startswith(first), "FIRST_COMMIT is the base commit — take the line with YOUR message")
    c.ok(commits[0][0].startswith(first),
         f'"{first}" is not your first commit on {BRANCH}' +
         (" (it is a later one)" if any(h.startswith(first) for h, *_ in commits[1:]) else ""))
    _, msg = git("log", "-1", "--format=%s", "refs/tags/base")
    mm = re.search(r"—\s*([0-9a-f]{7,40})", msg)
    c.ok(mm is not None, "the base commit message has no source hash (unexpected — ask your teacher)")
    src = str(src).strip().lower()
    c.ok(len(src) >= 7, f'NAVERA_SOURCE_COMMIT = "{src}" is too short')
    c.ok(mm.group(1).startswith(src) or src.startswith(mm.group(1)),
         f'NAVERA_SOURCE_COMMIT = "{src}" is not the hash written inside the base message')


QUIZ = {"Q1": ("b", "staging"), "Q2": ("c", "the three dots"), "Q3": ("b", "the Reset button"),
        "Q4": ("a", "remote-tracking branches"), "Q5": ("c", "merges"), "Q6": ("b", "tags")}


@c.test("answers.py: quiz Q1–Q6",
        hint="Each answer is one letter between quotes. Re-read the course section named in the message.")
def _():
    m = answers()
    wrong = []
    for q, (good, topic) in QUIZ.items():
        (v,) = need(m, q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        if v != good:
            wrong.append(f"{q} (see: {topic})")
    c.ok(not wrong, "not right yet: " + ", ".join(wrong))


@c.test("review.md: your code review of review_me.patch",
        hint="Keep the four ## headings, replace every '(write here)'. Name the parameter you rejected, "
             "its old and new values, and the risk for spoofing; at least 100 words.")
def _():
    c.file_exists("review.md")
    with open("review.md") as f:
        text = f.read()
    low = text.lower()
    for h in ("## what the patch does", "## applied", "## rejected", "## advice"):
        c.ok(h in low, f'review.md has no section starting with "{h}"')
    c.ok("(write here)" not in low, 'review.md still contains "(write here)"')
    words = len(re.findall(r"[A-Za-z]{2,}", text))
    c.ok(words >= 100, f"review.md has about {words} words — write at least 100")
    c.ok("gps_jump_margin_m" in text, "review.md does not name the parameter you rejected")
    c.ok("5000" in text and "50" in re.sub(r"5000", "", text), "review.md should give the old and the new value")
    c.ok("spoof" in low, "review.md should explain the risk for spoofing")


c.run()
