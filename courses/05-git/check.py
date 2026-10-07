import os
import subprocess

from academy_check import CheckFailed, Checker, load_student, need

c = Checker()
NAV = os.path.expanduser("~/navera")
BRANCH = "my-first-change"
ACADEMY_ID = ("NAVERA Academy", "academy@localhost")      # who made the base commit


def git(*args):
    r = subprocess.run(["git", "-C", NAV, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def git_ok(*args):
    code, out = git(*args)
    if code != 0:
        raise CheckFailed(f"`git {' '.join(args)}` failed in ~/navera")
    return out


def need_branch():
    code, _ = git("rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}")
    if code != 0:
        raise CheckFailed(f"there is no branch called {BRANCH} in ~/navera yet")


def branch_commits():
    """Commits on the branch that are not in the base, oldest first: [(hash, name, email, subject)]."""
    need_branch()
    out = git_ok("log", "--reverse", "--format=%H%x1f%an%x1f%ae%x1f%s", f"refs/tags/base..{BRANCH}")
    return [tuple(l.split("\x1f")) for l in out.splitlines() if l]


def changed_files():
    need_branch()
    return [l for l in git_ok("diff", "--name-only", f"refs/tags/base...{BRANCH}").splitlines() if l]


@c.test("git knows your name and e-mail (git config --global)",
        hint='git config --global user.name "Your Name"  and  git config --global user.email "you@example.com"')
def _():
    _, name = git("config", "--global", "user.name")
    _, email = git("config", "--global", "user.email")
    c.ok(name != "", "user.name is not set")
    c.ok(name not in (ACADEMY_ID[0], "Your Name"), f"user.name is {name!r}: use your own name")
    c.ok(email != "", "user.email is not set")
    c.ok("@" in email, f"user.email = {email!r} does not look like an e-mail address")
    c.ok(email != "you@example.com", "user.email is still the example: write your own (it can be invented, e.g. sarra@example.com)")


@c.test(f"the branch {BRANCH} exists in ~/navera",
        hint=f"cd ~/navera, then git switch -c {BRANCH}   (-c = create). git branch lists the branches.")
def _():
    need_branch()


@c.test(f"{BRANCH} has at least 2 commits of yours on top of the base",
        hint="Each change: edit, git add <file>, git commit -m \"message\". git log --oneline shows them.")
def _():
    commits = branch_commits()
    c.ok(len(commits) >= 2, f"{BRANCH} has {len(commits)} commit(s) on top of the base, expected at least 2")
    _, email = git("config", "--global", "user.email")
    for h, name, mail, subject in commits:
        c.ok((name, mail) != ACADEMY_ID, f"commit {h[:7]} was not made by you")
    c.ok(any(mail == email for _, _, mail, _ in commits),
         f"none of the commits has your e-mail ({email}) — did you set it BEFORE committing?")


@c.test("your commit messages say what changed",
        hint='A good message is a short sentence: git commit -m "Add my name to the academy README"')
def _():
    for h, _, _, subject in branch_commits():
        s = subject.strip()
        c.ok(len(s) >= 8, f'commit {h[:7]} has the message "{s}": too short to say what changed')
        c.ok(s.lower() not in ("auto-save before reset", "wip", "update", "commit", "changes"),
             f'commit {h[:7]}: "{s}" does not say what changed')


@c.test("ACADEMY_README.md has a new line, committed on the branch",
        hint="Add a line to ~/navera/ACADEMY_README.md, save, then git add + git commit.")
def _():
    c.ok("ACADEMY_README.md" in changed_files(), f"ACADEMY_README.md is not changed by the commits of {BRANCH}")
    diff = git_ok("diff", f"refs/tags/base...{BRANCH}", "--", "ACADEMY_README.md")
    added = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]
    c.ok(added, "no new (non-empty) line in ACADEMY_README.md")


@c.test("a log message of NAVERA's Python code was changed, and the file is still valid Python",
        hint="Change only the text between the quotes in a get_logger().info(...) line, keep the quotes "
             "and the parentheses, then add + commit.")
def _():
    py = [f for f in changed_files() if f.endswith(".py")]
    c.ok(py, f"no Python file is changed by the commits of {BRANCH}")
    for f in py:
        code, src = git("show", f"{BRANCH}:{f}")
        c.ok(code == 0, f"{f} was deleted on the branch")
        try:
            compile(src, f, "exec")
        except SyntaxError as e:
            raise CheckFailed(f"{f} line {e.lineno} has a syntax error on the branch: {e.msg}")


@c.test("the branch work was not changed",
        hint="Your commits belong on my-first-change. If you committed on work by mistake, ask your teacher, "
             "or: git switch work, git reset --hard base, git switch my-first-change.")
def _():
    code, n = git("rev-list", "--count", "refs/tags/base..work")
    c.ok(code == 0, "the branch work has disappeared")
    c.ok(n == "0", f"work has {n} commit(s) that are not in the base")


@c.test("geo.py is back and nothing is left uncommitted (clean working tree)",
        hint="git status shows what is changed. git restore <file> brings a file back as in the last commit; "
             "finished changes go in a commit.")
def _():
    c.ok(os.path.isfile(os.path.join(NAV, "navera_common/navera_common/geo.py")),
         "navera_common/navera_common/geo.py is still deleted — git restore can bring it back")
    dirty = git_ok("status", "--porcelain", "--untracked-files=no")
    c.ok(dirty == "", "these files are changed but not committed:\n" + dirty)


@c.test("FIRST_COMMIT is the hash of your first commit on the branch",
        hint="git log --oneline: your first commit is the one just ABOVE the \"NAVERA base\" line. Copy its 7 characters.")
def _():
    (v,) = need(load_student("answers.py"), "FIRST_COMMIT")
    v = str(v).strip().lower()
    c.ok(v != "", "FIRST_COMMIT is still empty")
    c.ok(len(v) >= 7, f'"{v}" is too short: copy at least 7 characters')
    commits = branch_commits()
    c.ok(commits, f"{BRANCH} has no commits yet")
    c.ok(commits[0][0].startswith(v),
         f'"{v}" is not your first commit on {BRANCH}' +
         (" (it is a later one)" if any(h.startswith(v) for h, *_ in commits[1:]) else ""))


ANSWERS = {"Q1": ("b", "git add prepares the next commit; nothing is saved in the history until git commit."),
           "Q2": ("a", "Read the part about git restore in the course."),
           "Q3": ("b", "Read the part 'The Reset button' in the course.")}

for q, (good, hint) in ANSWERS.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f'{q} = "{v}" is not the right answer')


c.run()
