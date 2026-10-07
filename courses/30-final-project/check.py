import os
import re

from academy_check import CheckFailed, Checker, sh

c = Checker()
NAV = os.path.expanduser("~/navera")
SECTIONS = ["Idea", "Change", "Test", "Measurement", "Result", "Limits"]
# folders of the copy whose files are never part of a project (build products)
IGNORED = ("build/", "install/", "log/")


def git(args, timeout=30):
    code, out = sh(f"git -C {NAV} {args}", timeout=timeout)
    if code != 0:
        raise CheckFailed(f"`git {args}` failed in ~/navera:\n{out[-400:]}")
    return out.strip()


def sections():
    if not os.path.exists("PROJECT.md"):
        raise CheckFailed("PROJECT.md is missing — did you rename or delete it? (↺ Reset lab files gives it back)")
    text = open("PROJECT.md", encoding="utf-8", errors="replace").read()
    parts = re.split(r"^##\s+", text, flags=re.M)
    out = {}
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        out[title.strip()] = body.strip()
    return out


def changed_files():
    out = git("diff --name-only base..HEAD")
    return [f for f in out.splitlines() if f and not f.startswith(IGNORED)]


@c.test("PROJECT.md has its six sections, each one written by you",
        hint="Keep the headings ## Idea, ## Change, ## Test, ## Measurement, ## Result, ## Limits and "
             "replace every '(…)' placeholder by your own text — a few sentences each.")
def _():
    s = sections()
    missing = [h for h in SECTIONS if h not in s]
    c.ok(not missing, "missing heading(s): " + ", ".join("## " + h for h in missing))
    todo = []
    for h in SECTIONS:
        body = re.sub(r"\((?:[^()]|\([^()]*\))*\)", "", s[h]).strip()   # placeholders "(…)" removed
        if len(body.split()) < 8:
            todo.append(h)
    c.ok(not todo, "still empty or only the placeholder: " + ", ".join(todo) + " (at least a few sentences each)")


@c.test("PROJECT.md: the measurement has numbers, before and after",
        hint="Write the numbers of your measurement (before AND after) in ## Measurement, e.g. a small table.")
def _():
    s = sections()
    m = s.get("Measurement", "")
    c.ok(len(re.findall(r"\d", m)) >= 4, "## Measurement contains (almost) no numbers")
    c.ok(re.search(r"before", m, re.I) and re.search(r"after", m, re.I),
         "## Measurement should show the result BEFORE and AFTER your change")


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


def tests_changed():
    return [f for f in changed_files() if re.search(r"(^|/)test_[^/]*\.py$", f)
            and os.path.exists(os.path.join(NAV, f))]


@c.test("your project adds or changes a test, and it passes",
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


@c.test("NAVERA's own unit tests still pass in every package you touched",
        hint="cd ~/navera && python3 -m pytest -q <package>/test — read the first failure: did your change "
             "break something that worked?")
def _():
    pkgs = sorted({f.split("/")[0] for f in changed_files() if "/" in f})
    c.ok(pkgs, "your commits do not change any NAVERA package yet")
    with_tests = [p for p in pkgs if os.path.isdir(os.path.join(NAV, p, "test"))]
    if not with_tests:
        c.skip(f"the package(s) you touched ({', '.join(pkgs) or 'none'}) have no unit-test folder")
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


c.run()
