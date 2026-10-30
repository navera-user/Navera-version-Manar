"""run_lab.py — runs YOUR functions of detective.py on the lab's cases.

    python3 run_lab.py test                     each function on its docstring example
    python3 run_lab.py stat review_me.patch     your diff_stat next to git's own count     (Step 3)
    python3 run_lab.py toy                      your first_bad on made-up histories         (Step 6)
    python3 run_lab.py history                  your first_bad on the real repository      (Step 6)

Run it from ~/lessons/05-git (the folder of this file).
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "navera-lite-history")
START = os.getcwd()                       # where you ran it from (a patch path is relative to it)
os.chdir(HERE)
d = rk.load_student("detective")


def show(label, got, err, want, why="the docstring example says"):
    if err:
        print(f"✘ {label}\n    {err}")
    elif got == want:
        print(f"✔ {label} = {got!r}")
    else:
        print(f"✘ {label} = {got!r}, but {why} {want!r}")


class EndlessLoop(Exception):
    pass


def counted(pred, n):
    """is_bad that records each commit it is asked about, and stops an endless loop after 2n + 5 calls."""
    asked = []

    def is_bad(c):
        asked.append(c)
        if len(asked) > 2 * n + 5:
            raise EndlessLoop(f"is_bad was called more than {2 * n + 5} times for {n} commits: your loop never ends. "
                              "When the middle is GOOD, the answer is AFTER it (lab Step 6, hint 3)")
        return pred(c)
    return is_bad, asked


# A second patch for TODO 2: inside a hunk, the removed line "-- separator" is written "--- separator"
# and the added line "++ counter" is written "+++ counter". They are changes, not file headers.
TRAP_PATCH = """diff --git a/docs/notes.md b/docs/notes.md
index 3b18e51..a7f2c40 100644
--- a/docs/notes.md
+++ b/docs/notes.md
@@ -1,3 +1,3 @@
 # Notes
--- separator
+++ counter
 End.
"""


def test():
    for line, want in (("@@ -78,7 +78,8 @@ class JumpGate:", (78, 7, 78, 8)), ("@@ -5 +5,2 @@", (5, 1, 5, 2))):
        v, err = rk.call(d, "hunk_header", line)
        if not err and isinstance(v, list):
            v = tuple(v)
        show(f'hunk_header("{line}")', v, err, want)
    v, err = rk.call(d, "diff_stat", d.EXAMPLE_PATCH)
    if not err and isinstance(v, dict):
        v = {k: tuple(x) if isinstance(x, list) else x for k, x in v.items()}
    show("diff_stat(EXAMPLE_PATCH)", v, err, {"README.md": (2, 0), "navera_lite.yaml": (1, 1)})
    v, err = rk.call(d, "diff_stat", TRAP_PATCH)
    if not err and isinstance(v, dict):
        v = {k: tuple(x) if isinstance(x, list) else x for k, x in v.items()}
    show("diff_stat(TRAP_PATCH)  (a removed '-- separator', an added '++ counter')", v, err, {"docs/notes.md": (1, 1)},
         why="inside a hunk '--- separator' is a removed line and '+++ counter' an added one (Step 3, hint 4): git says")
    is_bad, asked = counted(lambda c: c >= 11, 16)
    v, err = rk.call(d, "first_bad", list(range(1, 17)), is_bad)
    show("first_bad(commits 1…16, bad from 11)", v, err, 11)
    if asked:
        print(f"    is_bad was asked about: {asked[:12]}{' …' if len(asked) > 12 else ''} → {len(asked)} test(s)")
        if 0 in asked or [a + 1 for a in asked if isinstance(a, int)] == [8, 12, 10, 11]:
            print("    these look like POSITIONS (mid), not commits: call is_bad(commits[mid]) and return commits[…]")


def numstat(path):
    """git's own count: `git apply --numstat` (works on a patch file, inside or outside a repository)."""
    r = subprocess.run(["git", "apply", "--numstat", path], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"git apply --numstat {path} failed: {r.stderr.strip()}")
    out = {}
    for line in r.stdout.splitlines():
        a, rm, p = line.split("\t")
        out[p] = (int(a), int(rm))
    return out


def stat(path):
    path = os.path.normpath(os.path.join(START, os.path.expanduser(path)))
    tip = (". Run this from INSIDE navera-lite-history:  cd ~/lessons/05-git/navera-lite-history"
           if os.path.basename(START) != "navera-lite-history" else "")
    if not os.path.isfile(path):
        sys.exit(f"there is no file {path} — make it first (lab Step 3), or check the name" + tip)
    text = open(path, errors="replace").read()
    if "diff --git" not in text:
        sys.exit(f"{path} contains no diff (is it empty? was the git diff command right?)"
                 + (tip + ", then make the patch again (Step 3)" if tip else ""))
    mine = rk.need_ok(d, "diff_stat", text, kind=dict)
    git = numstat(path)
    print(f"{'file':32s} {'yours (+/−)':>14s} {'git (+/−)':>12s}")
    same = True
    for p in sorted(set(mine) | set(git)):
        m, g = mine.get(p), git.get(p)
        m_s = "—" if m is None else f"{m[0]} / {m[1]}"
        g_s = "—" if g is None else f"{g[0]} / {g[1]}"
        ok = m is not None and g is not None and tuple(m) == g
        same &= ok
        print(f"{p:32s} {m_s:>14s} {g_s:>12s}  {'✔' if ok else '✘'}")
    hunks = sum(1 for l in text.splitlines() if l.startswith("@@"))
    print(f"\n{len(git)} file(s), {hunks} hunk(s). " + ("Your diff_stat agrees with git." if same else
          "Your diff_stat does not agree with git yet: compare the ✘ lines (see the Step 3 hints)."))
    if os.path.basename(path) == "review_me.patch" and os.path.isdir(os.path.join(REPO, ".git")):
        r = subprocess.run(["git", "diff", "--name-only", "main...kenji/fewer-refusals"], cwd=REPO,
                           capture_output=True, text=True)
        view = set(r.stdout.split()) if r.returncode == 0 else None
        if view is not None and view != set(git):
            print(f"⚠ This patch has {len(git)} file(s); the reviewer's view (three dots) has {len(view)}. Made with two "
                  "dots? Make it again: git diff main...kenji/fewer-refusals > ../review_me.patch (Step 3)")


def toy():
    commits = [f"c{i:02d}" for i in range(1, 17)]
    is_bad, asked = counted(lambda c: int(c[1:]) >= 11, 16)
    v = rk.need_ok(d, "first_bad", commits, is_bad)
    print(f"16 commits c01…c16, bad from c11: your first_bad says {v!r}; it tested {asked} ({len(asked)} tests)")
    print("\nHow many tests in the worst case? (over every possible first bad commit)")
    print(f"{'suspects':>9s} {'your worst case':>16s} {'⌈log₂ n⌉':>9s}")
    for n in (2, 3, 16, 30, 40, 100, 1000):
        worst, wrong = 0, None
        for bad in range(n):
            is_bad, asked = counted(lambda c, bad=bad: c >= bad, n)
            v, err = rk.call(d, "first_bad", list(range(n)), is_bad)
            if err:
                sys.exit(err)
            if v != bad and wrong is None:
                wrong = (bad, v)
            worst = max(worst, len(asked))
        note = "" if wrong is None else f"   ✘ wrong answer: first bad {wrong[0]}, you returned {wrong[1]!r}"
        if wrong is None and worst > math.ceil(math.log2(n)):
            note = "   ✘ too many tests (Step 6 hint 4: do you test the last commit?)"
        print(f"{n:9d} {worst:16d} {math.ceil(math.log2(n)):9d}{note}")


def git(*args, cwd=REPO):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def history():
    if not os.path.isdir(os.path.join(REPO, ".git")):
        sys.exit("navera-lite-history is missing: run lab Step 0 first")
    suspects = git("rev-list", "--reverse", "v0.1..main").split()
    subject = {h: git("log", "-1", "--format=%s", h) for h in suspects}
    work = tempfile.mkdtemp(prefix=".history-", dir=HERE)          # a private copy: your repository is not touched
    try:
        git("clone", "-q", "--no-checkout", REPO, work, cwd=HERE)
        probe = os.path.join(HERE, "probe_gate.py")

        def verdict(h):
            git("checkout", "-q", "--force", h, cwd=work)
            r = subprocess.run([sys.executable, probe], cwd=work, capture_output=True, text=True)
            return None if r.returncode == 3 else r.stdout.strip() != "5"

        def is_bad(h):
            if len(asked) > 2 * len(suspects) + 5:
                raise EndlessLoop("is_bad was called too many times: your loop never ends (lab Step 6, hint 3)")
            i = suspects.index(h)
            v = verdict(h)
            note = ""
            while v is None:                                   # cannot be tested: test the next commit instead
                i += 1
                v = verdict(suspects[i])
                note = f"  (cannot be tested: git skips it; here its child {suspects[i][:7]} answers for it)"
            lines.append(f"  test {len(asked) + 1}: {h[:7]} {subject[h][:52]:52s} → {'BAD' if v else 'good'}{note}")
            asked.append(h)
            return v

        asked, lines = [], []
        print(f"{len(suspects)} suspects between v0.1 (good) and main (bad). Your first_bad asks:")
        v, err = rk.call(d, "first_bad", suspects, is_bad)
        print("\n".join(lines))
        if err:
            sys.exit(err)
        print(f"\nYour first_bad: {str(v)[:7]} {subject.get(v, '?')}  —  {len(asked)} test(s), "
              f"⌈log₂ {len(suspects)}⌉ = {math.ceil(math.log2(len(suspects)))}")
        print("Real git bisect may need more tests: after a skip it jumps to another commit (lesson §4). "
              "Compare with your bisect.log in Step 7.")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "test":
        test()
    elif mode == "stat" and len(sys.argv) > 2:
        stat(sys.argv[2])
    elif mode == "toy":
        toy()
    elif mode == "history":
        history()
    else:
        print(__doc__)
