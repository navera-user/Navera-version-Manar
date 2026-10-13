"""Check of mission 02 — Linux and the shell for robotics.

Runs in the student's sandbox, in ~/lessons/02-terminal. Expected values are numbers measured once on
the course data (solutions/02-terminal/make_dataset.py); nothing here solves the exercises. The box's
evidence is its journal (box/log/journal.log and the earlier runs in box/old/): the check runs in its own
sandbox and cannot see the processes of the student's terminal.
"""
import glob
import os
import re
import shlex
import subprocess
import tempfile

from academy_check import CheckFailed, Checker, StudentError, explained, hidden, load_student, need, predicted, sh

c = Checker()
LESSON = os.path.dirname(os.path.abspath(__file__))        # /academy/courses/02-terminal
STARTER = os.path.join(LESSON, "files")
INBOX = os.path.join(STARTER, "inbox")
TREE = "/data/academy/02-terminal/navera_lite_tree"
PHOTOS = ["cam_0001.jpg", "cam_0002.jpg", "cam_0003.jpg"]
LOGS = ["sousse_2026-09-21.log", "range_2026-09-22.log"]
TMPS = ["cache_01.tmp", "cache_02.tmp", "cache_03.tmp"]
SCRIPT = "mission/bin/log_report.sh"
UNIT = "mission/deploy/navera_lite-gps.service"

# measured on the skeleton (make_dataset.py) and the evidence files
Q1_PY_FILES = 54                        # find navera_lite -name "*.py" | wc -l
Q1_WITH_COPIES = 140                    # the same from the top folder (build/ and install/ copies)
Q2_SOURCE = "navera_lite/uncertainty.py"
Q3_ROS_LINES = 134
Q4_SERVICES = 5                         # find deploy -name "*.service" (4 in systemd/, 1 in bench/)
Q4_ONLY_SYSTEMD = 4
Q4_WITH_COPIES = 10
Q5_PART = "imu.py"
P1_PORT_MODE = 660
P2_GROUP = "dialout"
# measured on the two flight logs
Q6_NODE = "day_vision"
Q7_TIME = "08:45:24"
Q8_ERROR_NODES = 3


# ------------------------------------------------------------------ helpers
def same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def answers():
    try:
        return load_student("answers.py")
    except StudentError as e:
        if "syntax error" in str(e):
            raise StudentError(f"{e} — is a text answer missing its quotes? (E2 = \"/data/…\", Q6 = \"…\")")
        raise


def answer(name):
    (v,) = need(answers(), name)
    return v


def as_int(v, name):
    try:
        return int(str(v).strip())
    except ValueError:
        raise CheckFailed(f"{name} should be a whole number, got {v!r}")


def text(v):
    return str(v).strip().strip("'\"").strip()


def clean_path(v):
    v = text(v)
    for prefix in (TREE + "/", "navera_lite_tree/", "./"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v.rstrip("/")


def lines_of(s):
    return [l.rstrip() for l in s.splitlines() if l.strip()]


def log_lines(name):
    with open(os.path.join(INBOX, name)) as f:
        return f.read().splitlines()


def report(lines, name):
    """The expected 7 lines of log_report.sh for a log given as a list of lines."""
    def count(level):
        return sum(l.startswith(f"[{level}]") for l in lines)
    nodes = {l.split(" ")[2] for l in lines if len(l.split(" ")) > 2}
    return [f"file: {name}", f"lines: {len(lines)}", f"INFO: {count('INFO')}", f"WARN: {count('WARN')}",
            f"ERROR: {count('ERROR')}", f"nodes: {len(nodes)}",
            f"no_fix: {sum('state NO_FIX' in l for l in lines)}"]


def hidden_log():
    """A log the student never saw (courses/02-terminal/hidden/, sealed: never on disk in the sandbox): no
    ERROR line, the words WARN and ERROR inside INFO messages, a node that appears once, a NO_FIX inside a
    WARN line. Written to a temp file only while the student's script reads it (check 13)."""
    return hidden("harbour_2026-10-02.log").splitlines()


def run_script(args):
    """Run the student's script; returns (exit code, stdout, stderr)."""
    if not os.path.isfile(SCRIPT):
        raise CheckFailed(f"{SCRIPT} does not exist yet")
    try:
        r = subprocess.run(["bash", "-c", f"./{SCRIPT} {args}"], capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise CheckFailed(f"./{SCRIPT} {args} did not finish in 20 s — does a command wait for input because "
                          "its file name is missing (\"$log\")?")
    return r.returncode, r.stdout, r.stderr


def compare(got, want, what):
    c.ok(len(got) == len(want), f"{what}: {len(got)} lines printed, expected {len(want)} "
                                "(file, lines, INFO, WARN, ERROR, nodes, no_fix)")
    for g, w in zip(got, want):
        if g != w:
            field = w.split(":")[0]
            raise CheckFailed(f'{what}: the line "{g}" is not right (the {field} line; compare with your '
                              "pipelines of Step 8)")


def section(md, title):
    m = re.search(r"^##\s*" + title + r"\b.*$", md, re.I | re.M)
    if not m:
        return None
    rest = md[m.end():]
    n = re.search(r"^##\s", rest, re.M)
    return rest[:n.start()] if n else rest


def has_number(s, n):
    return re.search(r"(?<![\d.:])" + re.escape(str(n)) + r"(?![\d:])", s) is not None


# ------------------------------------------------------------------ the box's journal
JLINE = re.compile(r"^\w{3} +\d+ (\d\d):(\d\d):(\d\d) box (\S+?)\[(\d+)\]: (.*)$")


def runs():
    """Every run of the box (newest first): a list of (seconds, name, pid, message)."""
    files = sorted(glob.glob("box/old/*/journal.log")) + (["box/log/journal.log"]
                                                          if os.path.exists("box/log/journal.log") else [])
    out = []
    for f in reversed(files):
        ev = []
        with open(f, errors="replace") as fh:
            for line in fh:
                m = JLINE.match(line.strip())
                if m:
                    h, mi, s, name, pid, msg = m.groups()
                    ev.append((int(h) * 3600 + int(mi) * 60 + int(s), name, int(pid), msg))
        out.append(ev)
    return out


def before_stop(ev):
    for i, e in enumerate(ev):
        if e[1] == "box.sh" and e[3].startswith("stop requested"):
            return ev[:i]
    return ev


def orphan_verdict(ev):
    """(ok, message) for one run: the orphan got SIGTERM, and a supervised arbiter was stopped and
    restarted by its supervisor (the observation of PREDICT_PKILL). The order does not matter: stopping
    the supervised one first is harmless, the box restarts it."""
    ev = before_stop(ev)
    orphan = next((int(m.group(1)) for _, n, _, msg in ev if n == "sim_launcher"
                   for m in [re.search(r"started navera_lite_arbiter as pid (\d+)", msg)] if m), None)
    if orphan is None:
        return False, "this run of the box has no orphan arbiter in its journal"
    supervised = [int(m.group(1)) for _, n, _, msg in ev if n == "supervise"
                  for m in [re.search(r"started navera_lite_arbiter as pid (\d+)", msg)] if m]
    term = any(n == "navera_lite_arbiter" and p == orphan and msg.startswith("received SIGTERM")
               for _, n, p, msg in ev)
    sigint = any(n == "navera_lite_arbiter" and p == orphan and msg.startswith("received SIGINT")
                 for _, n, p, msg in ev)
    observed = any(n == "navera_lite_arbiter" and p in supervised and msg.startswith("received SIGTERM")
                   for _, n, p, msg in ev) and len(supervised) >= 2
    if not term:
        if sigint:
            return False, "the orphan received SIGINT, not SIGTERM: stop it with plain `kill PID`"
        if observed:
            return False, ("you stopped the SUPERVISED arbiter (the supervisor started it again, see the journal), "
                           "but the orphan was not stopped: find it by its parent (ps -o pid,ppid,lstart,args) and "
                           "`kill` that PID — if the box is still running, no need to restart it; if you already "
                           "stopped it, ./box.sh start and do Step 6 in the new run (one correct run is enough)")
        return False, ("the orphan arbiter has no 'received SIGTERM' line in the journal: it is still running, or "
                       "it was killed with kill -9 (SIGKILL cannot be caught, so it could not write anything)")
    t_orphan = next(t for t, n, p, msg in ev
                    if n == "navera_lite_arbiter" and p == orphan and msg.startswith("received SIGTERM"))
    if any(n == "navera_lite_arbiter" and p in supervised and msg.startswith("received SIGTERM")
           and abs(t - t_orphan) <= 1 for t, n, p, msg in ev):
        return False, ("both arbiters received SIGTERM in the same second: that is pkill/killall by name (or one "
                       "kill with both PIDs). Find the orphan by its parent and kill only that PID; then, separately, "
                       "kill the supervised one to observe its supervisor. Run ./box.sh start for a new run "
                       "(one correct run is enough)")
    if not observed:
        return False, ("the orphan is stopped. Now observe your PREDICT_PKILL (Step 6): `kill` the remaining "
                       "arbiter by its PID, wait 2 s, and see in the journal what its supervisor does")
    return True, ""


def camera_verdict(ev):
    ev = before_stop(ev)
    first = next((int(m.group(1)) for _, n, _, msg in ev if n == "supervise"
                  for m in [re.search(r"started camera as pid (\d+)", msg)] if m), None)
    if first is None:
        return False, "this run has no camera reader in its journal"
    t_term = next((t for t, n, p, msg in ev if n == "camera" and p == first and msg.startswith("received SIGTERM")),
                  None)
    killed = next(((t, msg) for t, n, _, msg in ev if n == "supervise" and msg.startswith(f"camera[{first}] ended")),
                  None)
    if killed is None:
        if t_term is not None:
            return False, ("the camera reader received SIGTERM but did not end: check it with ps -p PID, then use "
                           "the next step of the ladder")
        return False, "the hung camera reader is still running: send it SIGTERM first (kill PID)"
    t_kill, msg = killed
    if t_term is None:
        return False, ("no 'received SIGTERM' line from the camera reader before it was killed: either you did not "
                       "send plain `kill PID` first, or you sent `kill -9` too soon (it needs a second or two to "
                       "write that line). Ladder: kill PID, wait 5 s, ps -p PID, then kill -9 PID")
    if "signal KILL" not in msg:
        return False, f"the journal says: {msg} — the reader should end with SIGKILL after SIGTERM"
    if t_kill - t_term < 2:
        return False, ("SIGKILL came less than 2 s after SIGTERM: wait a few seconds and check with ps -p PID "
                       "before you use kill -9")
    restarted = any(n == "supervise" and m and int(m.group(1)) != first
                    for _, n, _, msg in ev for m in [re.search(r"started camera as pid (\d+)", msg)])
    if not restarted:
        return False, "no new camera reader was started after the kill"
    return True, ""


def best(verdict):
    rs = runs()
    if not rs:
        raise CheckFailed("box/log/journal.log does not exist: start the box with ./box.sh start (Step 0)")
    msgs = []
    for ev in rs:
        ok, msg = verdict(ev)
        if ok:
            return
        msgs.append(msg)
    raise CheckFailed(msgs[0] + (" (latest run of the box; earlier runs were checked too)" if len(rs) > 1 else ""))


# ================================================================== Session 1
@c.test("mission/ folders exist; the views and the logs are moved (not copied) into them",
        hint="mkdir -p takes several paths. One mv with a wildcard per kind of file: the shell expands the "
             "pattern into all the matching names.")
def _():
    for d in ("mission/photos", "mission/logs", "mission/docs", "mission/bin", "mission/deploy"):
        c.ok(os.path.isdir(d), f"the folder {d} does not exist yet")
    for sub, names in (("photos", PHOTOS), ("logs", LOGS)):
        for p in names:
            dst = os.path.join("mission", sub, p)
            c.ok(os.path.isfile(dst), f"{dst} is missing")
            c.ok(same_bytes(dst, os.path.join(INBOX, p)), f"{dst} is not the original file any more")
            c.ok(not os.path.exists(os.path.join("inbox", p)), f"inbox/{p} is still there — use mv, not cp")


@c.test("notes renamed mission/docs/notes.txt, .tmp files deleted, inbox removed",
        hint="mv moves and renames in one go. Look with ls before rm. rmdir removes only an EMPTY folder.")
def _():
    c.ok(os.path.isfile("mission/docs/notes.txt"), "mission/docs/notes.txt does not exist yet")
    c.ok(same_bytes("mission/docs/notes.txt", os.path.join(INBOX, "notes_for_pilot.txt")),
         "mission/docs/notes.txt is not the pilot's notes")
    left = [t for t in TMPS if os.path.exists(os.path.join("inbox", t))]
    c.ok(not left, "still in inbox/: " + ", ".join(left))
    c.ok(not os.path.exists("inbox"), "the folder inbox still exists")


@c.test("mission/bin/preflight.sh is executable by its owner, unchanged; P3 is its octal mode",
        hint="ls -l shows the bits; chmod u+x adds x for the owner. Octal: r=4 w=2 x=1, for owner, group, others.")
def _():
    p = "mission/bin/preflight.sh"
    c.ok(os.path.isfile(p), f"{p} does not exist yet (it was in the inbox)")
    c.ok(same_bytes(p, os.path.join(INBOX, "preflight.sh")), f"{p} was changed — only move it and chmod it")
    mode = os.stat(p).st_mode & 0o777
    c.ok(mode & 0o100, f"{p} has no execute (x) bit for its owner yet")
    c.ok(not mode & 0o002, f"{p} runs, but its mode lets every user change a script the box runs (the w bit for "
                           "others, as in chmod 777): chmod it back, then use chmod u+x (lesson §3)")
    p3 = as_int(answer("P3"), "P3")
    c.ok(p3 == int(oct(mode)[2:]), f"P3 = {p3} is not the mode of your preflight.sh (ls -l shows "
                                   f"{''.join('rwx'[i % 3] if mode >> (8 - i) & 1 else '-' for i in range(9))})")


@c.test("the GPS unit in mission/deploy has the serial port's group, and nothing else changed",
        hint="cp the unit from the skeleton's deploy/systemd/, then add ONE line in [Service]: "
             "SupplementaryGroups=<the port's group>. diff against the original must show only that line.")
def _():
    c.ok(os.path.isfile(UNIT), f"{UNIT} does not exist yet — copy it from the skeleton with cp")
    orig = open(os.path.join(TREE, "deploy/systemd/navera_lite-gps.service")).read().splitlines()
    mine = open(UNIT).read().splitlines()

    def body(ls):
        return [l.strip() for l in ls if l.strip() and not l.strip().startswith("#")]
    o, m = body(orig), body(mine)
    added = [l for l in m if l not in o]
    removed = [l for l in o if l not in m]
    if removed:
        raise CheckFailed(f"you changed or removed an original line: {removed[0]!r} — add one line, change nothing")
    c.ok(added, "nothing was added to the unit yet")
    c.ok(len(added) == 1, f"add exactly one line; you added {len(added)}: {', '.join(added)}")
    line = added[0]
    if "#" in line:
        raise CheckFailed(f"{line!r}: a unit file has no end-of-line comments — systemd would read '#' and the "
                          "words after it as group names. Put a comment on its own line above.")
    key, _, val = line.partition("=")
    c.ok(key.strip() == "SupplementaryGroups", f"{line!r}: the setting that adds a group to the service's user is "
                                               "SupplementaryGroups (Group= replaces its own group)")
    if val.strip().strip("\"'") == P2_GROUP and val.strip() != P2_GROUP:
        raise CheckFailed(f"{line!r}: no quotes in a unit file — write SupplementaryGroups={P2_GROUP}")
    if P2_GROUP in val.split() and val.strip() != P2_GROUP:
        raise CheckFailed(f"{line!r}: the GPS reader needs only the serial port's group; every extra group is "
                          "access it does not need (least privilege). Keep only the port's group.")
    c.ok(val.strip() == P2_GROUP, f"{line!r}: is that the group of /dev/ttyTHS1 in the evidence?")
    i, s, inst = m.index(line), m.index("[Service]"), m.index("[Install]")
    c.ok(s < i < inst, "the line is not in the [Service] section (systemd ignores it elsewhere)")
    c.ok(os.access("mission/bin/preflight.sh", os.X_OK), "mission/bin/preflight.sh is not executable yet (Step 4a)")
    code, out = sh("./mission/bin/preflight.sh", timeout=30)
    if "data disk" in out and out.count("!!") == 1:
        c.skip("your unit is right; the map is missing because the data disk is not connected — tell the "
               "teacher (not your mistake)")
    c.ok(code == 0 and "PRE-FLIGHT OK" in out, "./mission/bin/preflight.sh does not report PRE-FLIGHT OK:\n"
         + out[-400:])


@c.test("P1, P2, E1, E2 and ros_env.txt (sorted ROS_ variables)",
        hint="P1/P2: evidence/ls_dev.txt and the two id files. E1/E2: echo $ROS_DOMAIN_ID, env | grep ^NAVERA_LITE. "
             "ros_env.txt: env | grep with ^ROS_ | sort > ros_env.txt.")
def _():
    p1 = as_int(answer("P1"), "P1")
    c.ok(p1 == P1_PORT_MODE, f"P1 = {p1} is not the octal mode of crw-rw---- (r=4, w=2, x=1 per group of three)")
    p2 = text(answer("P2"))
    c.ok(p2 != "", "P2 is still empty")
    c.ok(p2 == P2_GROUP, f"P2 = {p2!r}: which group of the port does the developer have, and the service user not?")
    e1 = as_int(answer("E1"), "E1")
    c.ok(e1 == int(os.environ.get("ROS_DOMAIN_ID", "-99")), f"E1 = {e1} is not your ROS_DOMAIN_ID")
    e2 = text(answer("E2"))
    c.ok(e2 == os.environ.get("NAVERA_LITE_MAP", "/data/map.mbtiles"), f"E2 = {e2!r} is not the value of NAVERA_LITE_MAP")
    c.file_exists("ros_env.txt")
    lines = lines_of(open("ros_env.txt").read())
    c.ok(lines, "ros_env.txt is empty")
    bad = [l for l in lines if not l.startswith("ROS_")]
    c.ok(not bad, f"ros_env.txt: this line does not start with ROS_: {bad[0]!r}" if bad else "")
    c.ok(lines == sorted(lines), "ros_env.txt: the lines are not sorted")
    dom = os.environ.get("ROS_DOMAIN_ID", "")
    c.ok(f"ROS_DOMAIN_ID={dom}" in lines, f"ros_env.txt: the line ROS_DOMAIN_ID={dom} is missing")
    c.ok("ROS_LOCALHOST_ONLY=1" in lines, "ros_env.txt: the line ROS_LOCALHOST_ONLY=1 is missing")


@c.test("Q1–Q5: exploring the NAVERA Lite skeleton",
        hint="Work from the skeleton's top folder. Q1 find … | wc -l (in which folder?). Q2 grep -rl, keep the "
             "source. Q3 find … | xargs wc -l (the total). Q4 a *.service wildcard. Q5 grep -l \"mission 17\".")
def _():
    q1 = as_int(answer("Q1"), "Q1")
    c.ok(q1 != Q1_WITH_COPIES, "Q1 counts the copies in build/ and install/ too: search the source package only")
    c.ok(q1 == Q1_PY_FILES, f"Q1 = {q1} is not right (every sub-folder of navera_lite/ counts)")
    q2 = clean_path(answer("Q2"))
    c.ok(q2 != "", "Q2 is still empty")
    c.ok(not q2.startswith(("build/", "install/")), "Q2 is a copy made by the packaging tool: give the source")
    c.ok(q2 == Q2_SOURCE, f"Q2 = {q2!r} is not the file that defines mahalanobis2")
    q3 = as_int(answer("Q3"), "Q3")
    c.ok(q3 == Q3_ROS_LINES, f"Q3 = {q3} is not the total of the .py files of navera_lite/ros "
                             "(the last line of wc -l)")
    q4 = as_int(answer("Q4"), "Q4")
    c.ok(q4 != Q4_ONLY_SYSTEMD, "Q4: deploy/systemd is not the only folder that holds a unit: search all of deploy")
    c.ok(q4 != Q4_WITH_COPIES, "Q4 counts the copies in install/ too: search the source folder deploy only")
    c.ok(q4 == Q4_SERVICES, f"Q4 = {q4} is not right (only names ending in .service, copies excluded)")
    q5 = os.path.basename(clean_path(answer("Q5")))
    c.ok(q5 != "", "Q5 is still empty")
    c.ok(q5 == Q5_PART, f"Q5 = {q5!r} is not the part written in mission 17")


@c.test("the orphan arbiter was found and stopped with SIGTERM, by its PID; the supervisor was observed",
        hint="pgrep -a -f navera_lite_arbiter; ps -o pid,ppid,lstart,args -p A,B: the orphan's starter is gone "
             "(PPID 1). kill <that PID> — plain kill sends SIGTERM. Then kill the other one and watch the journal.")
def _():
    a = answers()
    (pp,) = need(a, "PREDICT_PKILL")
    predicted("PREDICT_PKILL", pp)
    best(orphan_verdict)
    ppid = as_int(answer("ORPHAN_PPID"), "ORPHAN_PPID")
    c.ok(ppid == 1, f"ORPHAN_PPID = {ppid}: read the PPID column of ps for the orphan (who adopts orphans?)")
    explained("EXPLAIN_ORPHAN", answer("EXPLAIN_ORPHAN"),
              ([r"ppid", r"parent", r"\b1\b", r"adopt", r"supervis", r"launcher", r"\binit\b"],
               "what its parent showed"),
              ([r"later", r"after", r"younger", r"newer", r"sim", r"param", r"yaml", r"command",
                r"no_fix", r"journal"], "a second clue (command line, journal, or its start time — it is the younger one)"))


@c.test("the hung camera reader: SIGTERM, a wait, then SIGKILL; the supervisor restarted it",
        hint="pgrep -a -f box/bin/camera; kill PID; wait 5 s; ps -p PID; only then kill -9 PID. The journal "
             "(tail box/log/journal.log) shows the exit code.")
def _():
    best(camera_verdict)
    code = as_int(answer("KILL_EXIT_CODE"), "KILL_EXIT_CODE")
    c.ok(code == 137, f"KILL_EXIT_CODE = {code}: read the supervisor's line about the camera in the journal")
    explained("EXPLAIN_KILL", answer("EXPLAIN_KILL"),
              ([r"catch", r"caught", r"trap", r"ignor", r"handl", r"cannot", r"can't", r"can not", r"stuck",
                r"driver", r"wait", r"hung", r"hang", r"block", r"busy", r"freez", r"frozen"],
               "why SIGTERM was not enough and SIGKILL was"),
              ([r"restart", r"again", r"new", r"supervis", r"systemd"], "what the supervisor did next"))


SESSION1 = [t for t, _, _ in c.tests]
c.milestone("orphan-hunter", *SESSION1, label="Orphan hunter")


# ================================================================== Session 2
@c.test("ls_out.txt holds the normal output and ls_err.txt the error message",
        hint="One ls with two names (one exists, one does not): stdout with >, stderr with 2>.")
def _():
    for p in ("ls_out.txt", "ls_err.txt"):
        c.file_exists(p)
    out, err = open("ls_out.txt").read(), open("ls_err.txt").read()
    c.ok("navera_lite.yaml" in out, "ls_out.txt should contain the name navera_lite.yaml")
    c.ok("No such file" not in out, "the error message went into ls_out.txt: it belongs in ls_err.txt")
    c.ok("No such file" in err, "ls_err.txt should contain ls's error message (No such file or directory)")


@c.test("Q6–Q8 and PREDICT_UNIQ: questions about the flight logs",
        hint="Q6: WARN lines, field 3, sort | uniq -c | sort -rn. Q7: grep -m 1, the seconds, TZ=Africa/Tunis "
             "date -d @SECONDS +%T. Q8: ERROR lines of both logs, field 3, sort -u, wc -l.")
def _():
    predicted("PREDICT_UNIQ", answer("PREDICT_UNIQ"))
    q6 = text(answer("Q6")).strip("[]:")
    c.ok(q6 != "", "Q6 is still empty")
    c.ok(q6 == Q6_NODE, f"Q6 = {q6!r} is not the node with the most WARN lines in the Sousse log")
    q7 = text(answer("Q7"))
    c.ok(q7 != "", "Q7 is still empty")
    c.ok(re.fullmatch(r"\d\d:\d\d:\d\d", q7) is not None, f"Q7 = {q7!r}: the format is \"HH:MM:SS\"")
    if q7 == "07:45:24":
        raise CheckFailed("Q7 is the UTC time: Tunisia is UTC+1")
    c.ok(q7 == Q7_TIME, f"Q7 = {q7!r} is not the Tunisian time of the first state NO_FIX")
    q8 = as_int(answer("Q8"), "Q8")
    c.ok(q8 == Q8_ERROR_NODES, f"Q8 = {q8} is not the number of DIFFERENT nodes with an ERROR line (both logs)")


@c.test("log_report.sh: shebang, executable, errors on stderr with a non-zero exit code",
        hint="First line #!/bin/bash; chmod u+x. If $# is not 1: a message to stderr (>&2) and exit 2. A missing "
             "file: a message to stderr and exit 1. Nothing on stdout in both cases.")
def _():
    c.ok(os.path.isfile(SCRIPT), f"{SCRIPT} does not exist yet")
    first = open(SCRIPT).readline().strip()
    c.ok(first.startswith("#!") and "bash" in first, f"the first line is {first!r}, expected #!/bin/bash")
    c.ok(os.stat(SCRIPT).st_mode & 0o100, f"{SCRIPT} is not executable (x) yet")
    code, out, err = run_script("")
    m = re.search(r"\[\S*: command not found", err)
    if m:
        raise CheckFailed(f"bash said '{m.group(0)}': your [ … ] test is missing a space, so bash ran a command "
                          "called '[…'. Write if [ $# -ne 1 ]; then (spaces inside the brackets). Without it the "
                          "script goes on with no file and, in a terminal, waits for the keyboard (Ctrl+C).")
    c.ok(code == 2, f"without an argument the exit code is {code}, expected 2")
    c.ok(out.strip() == "", f"without an argument the script printed on stdout: {out.strip()[:80]!r} — use >&2")
    c.ok(err.strip() != "", "without an argument the script printed no message on stderr")
    code, out, err = run_script("mission/logs/a.log mission/logs/b.log")
    c.ok(code == 2, f"with two arguments the exit code is {code}, expected 2 (exactly one argument)")
    code, out, err = run_script("/tmp/no_such_flight.log")
    c.ok(code == 1, f"with a file that does not exist the exit code is {code}, expected 1")
    c.ok(out.strip() == "" and err.strip() != "", "a missing file: the message must go to stderr, nothing to stdout")


@c.test("log_report.sh gives the exact 7-line summary of the Sousse log",
        hint="Severity = the START of the line (^ and \\[ in grep). nodes = field 3, sort -u, wc -l. The name with "
             "basename. lines with wc -l < file.")
def _():
    code, out, err = run_script(f"mission/logs/{LOGS[0]}")
    c.ok(code == 0, f"the script failed (exit code {code}):\n{(err or out)[-400:]}")
    compare(lines_of(out), report(log_lines(LOGS[0]), LOGS[0]), "Sousse log")


@c.test("log_report.sh is right on a log it has never seen (no ERROR line, tricky messages, a space in the path)",
        hint="grep -c that counts 0 exits with 1: under set -e, n=$(grep -c …) stops the script (add || true). "
             "An INFO message may contain the word WARN or ERROR: only the first field counts. Quote \"$log\".")
def _():
    lines = hidden_log()
    name = "harbour_2026-10-02.log"
    with tempfile.TemporaryDirectory() as d:
        plain, spaced = os.path.join(d, "logs"), os.path.join(d, "flight logs")   # "$log" must be quoted
        for folder in (plain, spaced):
            os.makedirs(folder)
            with open(os.path.join(folder, name), "w") as f:
                f.write("\n".join(lines) + "\n")
        code, out, err = run_script(shlex.quote(os.path.join(plain, name)))
        code2, out2, err2 = run_script(shlex.quote(os.path.join(spaced, name)))
    if code != 0 and 0 < len(lines_of(out)) < 7:
        raise CheckFailed(f"the script stopped early (after {len(lines_of(out))} lines, exit code {code}) on a log "
                          "without ERROR lines: grep -c found 0, exited with 1, and set -e stopped the script — "
                          "add || true")
    want = report(lines, name)
    if code == 0 and lines_of(out) == want and (code2 != 0 or lines_of(out2) != want):
        first = next((l for l in err2.splitlines() if l.strip()), "")
        bad = next((g for g, w in zip(lines_of(out2), want) if g != w), "")
        raise CheckFailed("right on the new log, but wrong when the log sits in a folder whose name has a space "
                          "('flight logs'): quote every \"$log\" (lesson §7), also inside $(basename …) and "
                          "after wc -l <" + (f". Bash said: {first.strip()[:160]}" if first else "")
                          + (f". Wrong line: \"{bad}\"" if bad else ""))
    c.ok(code == 0, f"the script failed on the new log (exit code {code}):\n{(err or out)[-400:]}")
    compare(lines_of(out), report(lines, "harbour_2026-10-02.log"), "new log")


@c.test("the two reports are saved in mission/docs/report_<flight>.txt",
        hint="A for loop over mission/logs/*.log; basename \"$f\" .log removes the folder and the .log ending.")
def _():
    for name in LOGS:
        p = f"mission/docs/report_{name[:-4]}.txt"
        c.ok(os.path.isfile(p), f"{p} does not exist yet")
        compare(lines_of(open(p).read()), report(log_lines(name), name), p)


@c.test("mission/docs/flight_report.md: Sousse, Range and Conclusion with the right numbers",
        hint="## Sousse, ## Range, ## Conclusion. Each flight: its NO_FIX count and its ERROR count; Sousse: the "
             "Tunisian time of the first NO_FIX; a conclusion of at least 40 words.")
def _():
    p = "mission/docs/flight_report.md"
    c.ok(os.path.isfile(p), f"{p} does not exist yet")
    md = open(p).read()
    for name, title in ((LOGS[0], "Sousse"), (LOGS[1], "Range")):
        body = section(md, title)
        c.ok(body is not None, f"no '## {title}' section in {p}")
        lines = log_lines(name)
        c.ok(has_number(body, sum("state NO_FIX" in l for l in lines)),
             f"the {title} section does not give its number of NO_FIX events")
        c.ok(has_number(body, sum(l.startswith("[ERROR]") for l in lines)),
             f"the {title} section does not give its number of ERROR lines")
    sousse = section(md, "Sousse")
    c.ok(Q7_TIME in sousse or re.search(r"(?<![\d:])" + re.escape(Q7_TIME.lstrip("0")), sousse),
         "the Sousse section does not give the Tunisian time of the first NO_FIX (HH:MM:SS, as date +%T prints it)")
    c.ok(re.search(r"sea|water|vision|match|dead.?reckon", sousse, re.I),
         "the Sousse section gives numbers but does not say what happened (where was the drone, why did vision fail?)")
    concl = section(md, "Conclusion")
    c.ok(concl is not None, f"no '## Conclusion' section in {p}")
    n = len(re.findall(r"[A-Za-z]+", concl))
    c.ok(n >= 40, f"the conclusion has {n} words, at least 40 are expected")
    c.ok(len(set(w.lower() for w in re.findall(r"[A-Za-z]+", concl))) >= 25,
         "the conclusion repeats the same few words: write real sentences")
    c.ok(re.search(r"vision|gps|sea|land|camera|jamm", concl, re.I),
         "the conclusion does not talk about the flights (vision, GPS, sea, land…)")
    c.ok(re.search(r"recommend|should|next|keep|avoid|investigat|must|plan", concl, re.I),
         "the conclusion has no recommendation for the next test")


c.milestone("log-detective", *[t for t, _, _ in c.tests], label="Log detective")

c.run()
