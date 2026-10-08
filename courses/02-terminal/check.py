import os
import re
import subprocess
import tempfile

from academy_check import CheckFailed, Checker, load_student, need, sh

c = Checker()
NAV = os.path.expanduser("~/navera")
LESSON = os.path.dirname(os.path.abspath(__file__))       # /academy/courses/02-terminal
STARTER = os.path.join(LESSON, "files")
PHOTOS = ["frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg"]
LOGS = ["sousse_2026-09-21.log", "range_2026-09-22.log"]
TMPS = ["cache_01.tmp", "cache_02.tmp", "cache_03.tmp"]
SCRIPT = "mission/bin/log_report.sh"


# ------------------------------------------------------------------ helpers
def git_show(path):
    """A file of NAVERA as it was at the start (tag "base"), whatever the student changed since."""
    r = subprocess.run(["git", "-C", NAV, "show", "refs/tags/base:" + path], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout
    with open(os.path.join(NAV, path)) as f:
        return f.read()


def base_files(prefix):
    r = subprocess.run(["git", "-C", NAV, "ls-tree", "-r", "--name-only", "refs/tags/base", "--", prefix],
                       capture_output=True, text=True)
    return r.stdout.split()


def same_bytes(a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def clean_path(v):
    """'~/navera/x', '/home/student/navera/x', 'navera/x' and 'x' are the same answer."""
    v = str(v).strip().strip("'\"").strip()
    for prefix in ("/home/student/navera/", "~/navera/", "navera/", "./"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    return v.rstrip("/")


def report(lines, name):
    """The expected output of log_report.sh for a log given as a list of lines."""
    def count(level):
        return sum(l.startswith(f"[{level}]") for l in lines)
    nodes = {l.split(" ")[2] for l in lines if len(l.split(" ")) > 2}
    return [f"file: {name}", f"lines: {len(lines)}", f"INFO: {count('INFO')}", f"WARN: {count('WARN')}",
            f"ERROR: {count('ERROR')}", f"nodes: {len(nodes)}",
            f"no_fix: {sum('state NO_FIX' in l for l in lines)}"]


def log_lines(name):
    with open(os.path.join(STARTER, "inbox", name)) as f:
        return f.read().splitlines()


def hidden_log():
    """A log the student never saw: no ERROR line at all, the words WARN / ERROR inside INFO
    messages, a node that appears once."""
    t = 1790000000
    out = []
    plan = ([("INFO", "estimator_node", "arbiter started: priority GPS > day > night > cn"),
             ("INFO", "estimator_node", "state FIX source=GPS")]
            + [("INFO", "gps_node", f"fix OK, {9 + i % 4} satellites, hdop 1.1") for i in range(12)]
            + [("WARN", "gps_node", "no fix for 2.0 s (jamming simulated)"),
               ("WARN", "estimator_node", "state DEGRADED source=day vision (GPS lost)")]
            + [("INFO", "day_subscriber", f"match OK, {20 + i} inliers, sigma 30 m") for i in range(9)]
            + [("WARN", "day_subscriber", "no match: sea, nothing to recognise")] * 3
            + [("WARN", "estimator_node", "state NO_FIX: no source usable (dead-reckoning limit 120 s)"),
               ("INFO", "estimator_node", "WARN threshold reached, no ERROR raised (test message)"),
               ("INFO", "day_subscriber", "match OK, 31 inliers, sigma 30 m"),
               ("WARN", "estimator_node", "state DEGRADED source=day vision (GPS lost)"),
               ("WARN", "estimator_node", "state NO_FIX: no source usable (day vision stale)"),
               ("INFO", "rtc_node", "clock synchronised"),
               ("INFO", "gps_node", "fix OK, 8 satellites, hdop 1.7"),
               ("INFO", "estimator_node", "state FIX source=GPS")])
    for i, (lvl, node, msg) in enumerate(plan):
        out.append(f"[{lvl}] [{t + 2 * i}.{(i * 7919) % 10**9:09d}] [{node}]: {msg}")
    return out


def run_script(arg):
    """Run the student's script; returns (exit code, stdout, stderr)."""
    if not os.path.isfile(SCRIPT):
        raise CheckFailed(f"{SCRIPT} does not exist yet")
    try:
        r = subprocess.run(["bash", "-c", f'./{SCRIPT} {arg}'], capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise CheckFailed(f"./{SCRIPT} {arg} did not finish in 20 s — does a command wait for input "
                          "because its file name is missing?")
    return r.returncode, r.stdout, r.stderr


def lines_of(text):
    return [l.rstrip() for l in text.splitlines() if l.strip()]


def compare(got, want, what):
    c.ok(len(got) == len(want), f"{what}: {len(got)} lines printed, expected {len(want)} "
                                f"(file, lines, INFO, WARN, ERROR, nodes, no_fix)")
    for g, w in zip(got, want):
        c.ok(g == w, f'{what}: the line "{g}" should be "{w}"')


def answer(q):
    (v,) = need(load_student("answers.py"), q)
    return v


def as_int(v, q):
    try:
        return int(str(v).strip())
    except ValueError:
        raise CheckFailed(f"{q} should be a whole number, got {v!r}")


def is_fake_node(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"fake_node" in f.read()
    except OSError:
        return False


def section(text, title):
    """The body of the '## title' section of a Markdown text (None if absent)."""
    m = re.search(r"^##\s*" + title + r"\b.*$", text, re.I | re.M)
    if not m:
        return None
    rest = text[m.end():]
    n = re.search(r"^##\s", rest, re.M)
    return rest[:n.start()] if n else rest


def has_number(text, n):
    return re.search(r"(?<![\d.:])" + re.escape(str(n)) + r"(?![\d:])", text) is not None


# ------------------------------------------------------------------ 1. tidy the inbox
@c.test("the folders mission/photos, mission/logs, mission/docs and mission/bin exist",
        hint="mkdir -p accepts several paths in one command, and creates the parent folder too.")
def _():
    for d in ("mission", "mission/photos", "mission/logs", "mission/docs", "mission/bin"):
        c.ok(os.path.isdir(d), f"the folder {d} does not exist yet")


@c.test("photos and logs are moved (not copied) into mission/photos and mission/logs",
        hint="One mv with a wildcard per type of file: the shell expands the pattern into all matching names.")
def _():
    for sub, names in (("photos", PHOTOS), ("logs", LOGS)):
        for p in names:
            dst = os.path.join("mission", sub, p)
            c.ok(os.path.isfile(dst), f"{dst} is missing")
            c.ok(same_bytes(dst, os.path.join(STARTER, "inbox", p)), f"{dst} is not the original file any more")
            c.ok(not os.path.exists(os.path.join("inbox", p)), f"inbox/{p} is still there — use mv, not cp")


@c.test("notes renamed mission/docs/notes.txt, .tmp files deleted, inbox removed",
        hint="mv can move and rename in one go. Look with ls before rm. rmdir removes only an EMPTY folder.")
def _():
    c.ok(os.path.isfile("mission/docs/notes.txt"), "mission/docs/notes.txt does not exist yet")
    with open("mission/docs/notes.txt", "rb") as f, open(os.path.join(STARTER, "inbox", "notes_for_pilot.txt"), "rb") as g:
        c.ok(f.read().startswith(g.read()), "mission/docs/notes.txt is not the pilot's notes")
    left = [t for t in TMPS if os.path.exists(os.path.join("inbox", t))]
    c.ok(not left, "still in inbox/: " + ", ".join(left))
    c.ok(not os.path.exists("inbox"), "the folder inbox still exists")


@c.test("mission/bin/preflight.sh is executable and reports PRE-FLIGHT OK",
        hint="ls -l shows the permission bits. chmod gives the x bit; then ./mission/bin/preflight.sh runs it.")
def _():
    p = "mission/bin/preflight.sh"
    c.ok(os.path.isfile(p), f"{p} does not exist yet (it was in the inbox)")
    c.ok(same_bytes(p, os.path.join(STARTER, "inbox", "preflight.sh")), f"{p} was changed — only move it")
    c.ok(os.stat(p).st_mode & 0o100, f"{p} has no execute (x) permission for its owner yet")
    code, out = sh(f"./{p}", timeout=20)
    if "data disk" in out:
        raise CheckFailed("the map file is missing because the data disk is not connected — ask the teacher "
                          "(your preflight.sh is fine: it found the problem)")
    c.ok(code == 0 and "PRE-FLIGHT OK" in out, f"./{p} did not report PRE-FLIGHT OK:\n{out[-400:]}")


@c.test("mission/docs/gps_params.yaml is an exact copy, and the original is still in ~/navera",
        hint="find ~/navera -name gps_params.yaml — take the source (not install/), and copy it with cp.")
def _():
    dst = "mission/docs/gps_params.yaml"
    c.ok(os.path.isfile(dst), f"{dst} does not exist yet")
    with open(dst) as f:
        c.ok(f.read() == git_show("gps_pkg/gps_pkg/config/gps_params.yaml"), f"{dst} is not an exact copy")
    c.ok(os.path.isfile(os.path.join(NAV, "gps_pkg/gps_pkg/config/gps_params.yaml")),
         "the original gps_params.yaml is gone from ~/navera — you moved it instead of copying it")


# ------------------------------------------------------------------ 2. environment, streams, processes
@c.test("ros_env.txt holds the ROS_ environment variables, sorted",
        hint="env prints every variable; grep with ^ keeps the lines that START with ROS_; sort; > saves.")
def _():
    c.file_exists("ros_env.txt")
    with open("ros_env.txt") as f:
        lines = lines_of(f.read())
    c.ok(lines, "ros_env.txt is empty")
    bad = [l for l in lines if not l.startswith("ROS_")]
    c.ok(not bad, f"this line does not start with ROS_: {bad[0]!r}" if bad else "")
    c.ok(lines == sorted(lines), "the lines are not sorted")
    dom = os.environ.get("ROS_DOMAIN_ID", "")
    c.ok(f"ROS_DOMAIN_ID={dom}" in lines, f"the line ROS_DOMAIN_ID={dom} is missing")
    c.ok("ROS_LOCALHOST_ONLY=1" in lines, "the line ROS_LOCALHOST_ONLY=1 is missing")


@c.test("ls_out.txt holds the normal output and ls_err.txt the error message (2>)",
        hint="One ls command with two file names (one exists, one does not), stdout with > and stderr with 2>.")
def _():
    for p in ("ls_out.txt", "ls_err.txt"):
        c.file_exists(p)
    out, err = open("ls_out.txt").read(), open("ls_err.txt").read()
    c.ok("README.md" in out, "ls_out.txt should contain the path of ~/navera/README.md")
    c.ok("No such file" not in out, "the error message went into ls_out.txt: it belongs in ls_err.txt")
    c.ok("No such file" in err, "ls_err.txt should contain ls's error message (No such file or directory)")
    c.ok("README.md" not in err.replace("NO_SUCH_FILE", ""), "the normal output went into ls_err.txt")


@c.test("fake_node.sh was stopped with SIGTERM, by its PID",
        hint="Start it with & , find its PID (pgrep -a -f, or cat fake_node.pid), then kill <PID> — "
             "plain kill sends SIGTERM. Not Ctrl+C, not kill -9.")
def _():
    c.ok(os.path.isfile("fake_node.log"), "fake_node.log does not exist: fake_node.sh was never started")
    log = open("fake_node.log").read()
    started = re.findall(r"pid=(\d+) started", log)
    c.ok(started, "fake_node.log has no 'started' line")
    stopped = re.findall(r"pid=(\d+) received SIGTERM", log)
    c.ok(stopped, "fake_node.log has no 'received SIGTERM' line yet (SIGINT or SIGKILL do not count)")
    c.ok(set(stopped) <= set(started), "the SIGTERM line does not match a started fake_node")
    alive = [p for p in started if p not in stopped and is_fake_node(p)]
    c.ok(not alive, f"a fake_node.sh is still running (PID {', '.join(alive)}): stop it with kill <PID>")


# ------------------------------------------------------------------ 3. the log report script
@c.test("mission/bin/log_report.sh: shebang, executable, usage error without argument",
        hint="First line #!/bin/bash; chmod +x. With no argument ($# is 0): a message to stderr (>&2) and "
             "exit with a non-zero code, nothing on stdout.")
def _():
    c.ok(os.path.isfile(SCRIPT), f"{SCRIPT} does not exist yet")
    with open(SCRIPT) as f:
        first = f.readline().strip()
    c.ok(first.startswith("#!") and "bash" in first, f"the first line is {first!r}, expected a shebang like #!/bin/bash")
    c.ok(os.stat(SCRIPT).st_mode & 0o100, f"{SCRIPT} is not executable (x) yet")
    code, out, err = run_script("")
    c.ok(code != 0, "without an argument the script exits with code 0 — it should fail (e.g. exit 2)")
    c.ok(out.strip() == "", f"without an argument the script printed on stdout: {out.strip()[:80]!r} — use >&2")
    c.ok(err.strip() != "", "without an argument the script printed no message on stderr (>&2)")
    code, out, err = run_script("/tmp/no_such_flight.log")
    c.ok(code != 0, "with a file that does not exist the script exits with code 0 — it should fail")


@c.test("log_report.sh gives the exact 7-line summary of the Sousse log",
        hint="Count the level at the START of the line (^ and \\[ in grep), nodes = field 3 with cut, sort -u, wc -l. "
             "Print the name with basename, not the whole path.")
def _():
    code, out, err = run_script(f"mission/logs/{LOGS[0]}")
    c.ok(code == 0, f"the script failed (exit code {code}):\n{(err or out)[-400:]}")
    compare(lines_of(out), report(log_lines(LOGS[0]), LOGS[0]), "Sousse log")


@c.test("log_report.sh is right on a log it has never seen (no ERROR line, tricky messages)",
        hint="A grep that counts 0 lines exits with code 1: in n=$(grep -c …) under set -e that stops the script (add || true). "
             "And an INFO message may contain the word WARN: only the level at the start of the line counts.")
def _():
    lines = hidden_log()
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "monastir_2026-10-01.log")
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        code, out, err = run_script(p)
    c.ok(code == 0, f"the script failed on the new log (exit code {code}):\n{(err or out)[-400:]}")
    compare(lines_of(out), report(lines, "monastir_2026-10-01.log"), "new log")


@c.test("the two reports are saved in mission/docs/report_<flight>.txt",
        hint="A for loop over mission/logs/*.log; basename \"$f\" .log removes the folder and the .log ending.")
def _():
    for name in LOGS:
        p = f"mission/docs/report_{name[:-4]}.txt"
        c.ok(os.path.isfile(p), f"{p} does not exist yet")
        with open(p) as f:
            compare(lines_of(f.read()), report(log_lines(name), name), p)


# ------------------------------------------------------------------ 4. answers and report
@c.test("E1, E2: the values of ROS_DOMAIN_ID and NAVERA_MBTILES",
        hint="echo $ROS_DOMAIN_ID and echo $NAVERA_MBTILES. E1 is a number (no quotes), E2 a path in quotes.")
def _():
    e1 = as_int(answer("E1"), "E1")
    c.ok(e1 == int(os.environ.get("ROS_DOMAIN_ID", "-99")), f"E1 = {e1} is not your ROS_DOMAIN_ID")
    e2 = str(answer("E2")).strip()
    c.ok(e2 != "", "E2 is still empty")
    c.ok(e2 == os.environ.get("NAVERA_MBTILES", "/data/map.mbtiles"), f"E2 = {e2!r} is not the value of NAVERA_MBTILES")


@c.test("Q1–Q5: exploring ~/navera",
        hint="Q1 find … | wc -l. Q2 find -name. Q3 find … -name \"*.py\" | xargs wc -l (the total line). "
             "Q4 ls …/*.service | wc -l. Q5 find -name nmea.py: the first folder after navera/.")
def _():
    want1 = sum(n.endswith(".py") for n in base_files("day_pkg"))
    v = as_int(answer("Q1"), "Q1")
    c.ok(v == want1, f"Q1 = {v} is not right (did you count every sub-folder?)")
    q2 = clean_path(answer("Q2"))
    c.ok(q2 != "", "Q2 is still empty")
    c.ok(not q2.startswith(("install/", "build/")), "Q2 is a copy made by the build — give the source file")
    c.ok(q2 == "navera_msgs/msg/PositionEstimate.msg", f"Q2 = {q2!r} is not the path of PositionEstimate.msg")
    want3 = sum(git_show(n).count("\n") for n in base_files("navera_estimator") if n.endswith(".py"))
    v = as_int(answer("Q3"), "Q3")
    c.ok(v == want3, f"Q3 = {v} is not right (the total of all the .py files, sub-folders included)")
    want4 = sum(n.startswith("deploy/systemd/") and n.endswith(".service") for n in base_files("deploy/systemd"))
    v = as_int(answer("Q4"), "Q4")
    c.ok(v == want4, f"Q4 = {v} is not right")
    q5 = clean_path(answer("Q5")).split("/")[0]
    c.ok(q5 != "", "Q5 is still empty")
    c.ok(q5 == "navera_output", f"Q5 = {q5!r} is not the package that holds nmea.py")


@c.test("Q6–Q9: logs, permissions, signals",
        hint="Q6: grep the WARN lines, cut the node field, sort | uniq -c | sort -rn. Q7: grep -m 1, take the "
             "seconds, TZ=Africa/Tunis date -d @SECONDS +%T. Q8: r=4 w=2 x=1. Q9: the course's signal table.")
def _():
    lines = log_lines(LOGS[0])
    counts = {}
    for l in lines:
        if l.startswith("[WARN]"):
            n = l.split(" ")[2].strip("[]:")
            counts[n] = counts.get(n, 0) + 1
    q6 = str(answer("Q6")).strip().strip("[]:")
    c.ok(q6 != "", "Q6 is still empty")
    c.ok(q6 == max(counts, key=counts.get), f"Q6 = {q6!r} is not the node with the most WARN lines")
    first = next(l for l in lines if "state NO_FIX" in l)
    secs = int(first.split(" ")[1].strip("[]").split(".")[0])
    r = subprocess.run(["date", "-d", f"@{secs}", "+%T"], capture_output=True, text=True,
                       env=dict(os.environ, TZ="Africa/Tunis"))
    q7 = str(answer("Q7")).strip()
    c.ok(q7 != "", "Q7 is still empty")
    c.ok(q7 == r.stdout.strip(), f"Q7 = {q7!r} is not right — Tunisian time is UTC+1, "
                                 "and the format is HH:MM:SS")
    q8 = as_int(answer("Q8"), "Q8")
    c.ok(q8 == 640, f"Q8 = {q8} is not the octal form of rw-r-----")
    q9 = str(answer("Q9")).strip().upper()
    c.ok(q9 in ("SIGINT", "INT"), f"Q9 = {q9!r} is not the signal of Ctrl+C")


@c.test("mission/docs/flight_report.md: Sousse, Range and Conclusion sections with the right numbers",
        hint="Three headings (## Sousse, ## Range, ## Conclusion). In each flight section, write its number of "
             "NO_FIX events and of ERROR lines; in Sousse, the Tunisian time of the first NO_FIX; "
             "a conclusion of at least 40 words.")
def _():
    p = "mission/docs/flight_report.md"
    c.ok(os.path.isfile(p), f"{p} does not exist yet")
    text = open(p).read()
    for name, title in ((LOGS[0], "Sousse"), (LOGS[1], "Range")):
        body = section(text, title)
        c.ok(body is not None, f"no '## {title}' section in {p}")
        lines = log_lines(name)
        nf = sum("state NO_FIX" in l for l in lines)
        er = sum(l.startswith("[ERROR]") for l in lines)
        c.ok(has_number(body, nf), f"the {title} section does not give its number of NO_FIX events ({title} log)")
        c.ok(has_number(body, er), f"the {title} section does not give its number of ERROR lines")
    lines = log_lines(LOGS[0])
    first = next(l for l in lines if "state NO_FIX" in l)
    secs = int(first.split(" ")[1].strip("[]").split(".")[0])
    t = subprocess.run(["date", "-d", f"@{secs}", "+%T"], capture_output=True, text=True,
                       env=dict(os.environ, TZ="Africa/Tunis")).stdout.strip()
    c.ok(t in section(text, "Sousse"), "the Sousse section does not give the Tunisian time of the first NO_FIX (HH:MM:SS)")
    concl = section(text, "Conclusion")
    c.ok(concl is not None, f"no '## Conclusion' section in {p}")
    words = len(re.findall(r"[A-Za-z]+", concl))
    c.ok(words >= 40, f"the conclusion has {words} words, at least 40 are expected")


c.run()
