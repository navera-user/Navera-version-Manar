"""Run a mission's check.py sealed in the student's sandbox (dashboard "Check my work" and
tools/try_lesson.py use exactly this code).

What the sandbox sees: /academy/lib (public helpers) and /academy/courses/<id>/files (the public starter
files), never check.py, meta.json or courses/<id>/hidden/. check.py and the hidden files reach the
checker in a memfd it reads and closes (courses/_lib/academy_sealed.py); the checker is non-dumpable
and runs every piece of student code in other processes. The score comes back on a private pipe,
tagged with a nonce: an "ACADEMY_RESULT" line in the output (which the student's code can print) is
ignored and removed.
"""
import json
import os
import re
import secrets
import select
import signal
import subprocess
import sys
import time

import config
import sandbox
import workspaces

MAX_HIDDEN = 64 << 20
PYTHON = "/usr/bin/python3"


def payload(lid):
    base = os.path.join(config.COURSES, lid)
    with open(os.path.join(base, "check.py"), encoding="utf-8") as f:
        source = f.read()
    hidden, size = {}, 0
    hdir = os.path.join(base, "hidden")
    for d, _, files in os.walk(hdir):
        for fn in sorted(files):
            p = os.path.join(d, fn)
            with open(p, "rb") as f:
                data = f.read()
            size += len(data)
            if size > MAX_HIDDEN:
                raise ValueError(f"courses/{lid}/hidden/ is larger than {MAX_HIDDEN >> 20} MB")
            hidden[os.path.relpath(p, hdir)] = data.hex()
    py = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return {"lid": lid, "source": source, "hidden": hidden, "nonce": secrets.token_hex(16),
            "user_site": os.path.join(config.PYTHON_USER_SITE, py, "site-packages")}


def mounts(lid):
    """Read-only mounts of a sealed check: the helpers and the public starter files only."""
    m = []
    lib = os.path.join(config.COURSES, "_lib")
    if os.path.isdir(lib):
        m.append((lib, "/academy/lib"))
    files = os.path.join(config.COURSES, lid, "files")
    if os.path.isdir(files):
        m.append((files, f"/academy/courses/{lid}/files"))
    return m


def parse_result(raw, nonce):
    """The checker's report: '<nonce> {json}' lines on the private pipe; the last valid one counts."""
    score = None
    for line in raw.decode("utf-8", "replace").splitlines():
        tag, _, rest = line.partition(" ")
        if not secrets.compare_digest(tag, nonce):
            continue
        try:
            r = json.loads(rest)
        except ValueError:
            continue
        if not (isinstance(r, dict) and isinstance(r.get("passed"), int) and isinstance(r.get("total"), int)):
            continue
        s = {"passed": r["passed"], "total": r["total"]}
        ms = [m for m in (r.get("milestones") or []) if isinstance(m, str) and len(m) < 40]
        if ms:
            s["milestones"] = ms
        score = s
    return score


FORGED = re.compile(r"^.*ACADEMY_RESULT.*$\n?", re.M)


def run_check(name, lid, index=0, timeout=180, resources=(), heavy=False, host_net=False, domain=None,
              stream=None):
    """Run check.py of `lid` sealed for student `name`. Returns (exit code, output, score).
    score is None when the checker reported nothing (crash, timeout, killed): never a pass.
    stream: a file to copy the output to while it runs (try_lesson)."""
    P = payload(lid)
    nonce = P["nonce"]
    data = json.dumps(P).encode("utf-8")
    del P
    mfd = os.memfd_create("academy-check", os.MFD_CLOEXEC)
    rr, rw = os.pipe()
    try:
        os.write(mfd, data)
        del data
        cmd = ["bash", "--noprofile", "--norc", "-c",
               f"source /opt/ros/humble/setup.bash >/dev/null 2>&1; exec {PYTHON} -s -B "
               f"/academy/lib/academy_sealed.py {mfd} {rw}"]
        argv = sandbox.bwrap_argv(name, workspaces.student_home(name), index, cmd, resources=resources,
                                  heavy=heavy, extra_ro=mounts(lid), host_net=host_net, domain=domain)
        p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             pass_fds=(mfd, rw), start_new_session=True, preexec_fn=_default_signals)
    finally:
        os.close(mfd)
        os.close(rw)
    out, raw, timed_out = [], [], False
    deadline = time.monotonic() + timeout
    fds = {p.stdout.fileno(): out, rr: raw}
    pending = ""
    while fds:
        left = deadline - time.monotonic()
        if left <= 0:
            timed_out = True
            p.kill()
            break
        ready, _, _ = select.select(list(fds), [], [], min(left, 1.0))
        for fd in ready:
            b = os.read(fd, 1 << 16)
            if not b:
                del fds[fd]
                continue
            fds_out = out if fd == p.stdout.fileno() else raw
            fds_out.append(b)
            if stream is not None and fd == p.stdout.fileno():
                pending += b.decode("utf-8", "replace")
                *lines, pending = pending.split("\n")
                for line in lines:
                    stream.write(_shown(line) + "\n")
                stream.flush()
    try:
        code = p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
        code = p.wait()
    if stream is not None and pending:
        stream.write(_shown(pending) + "\n")
    p.stdout.close()
    try:
        while True:                               # whatever is left on the result pipe
            r, _, _ = select.select([rr], [], [], 0)
            if not r:
                break
            b = os.read(rr, 1 << 16)
            if not b:
                break
            raw.append(b)
    finally:
        os.close(rr)
    text = b"".join(out).decode("utf-8", "replace")
    text = FORGED.sub("", text)
    if timed_out:
        code = 124
        text += f"\n⏱ The check took longer than {timeout} s and was stopped."
    score = None if timed_out else parse_result(b"".join(raw), nonce)
    return code, text, score


def passed(code, score):
    return code == 0 and score is not None and score.get("total", 0) > 0 and score["passed"] == score["total"]


def _shown(line):
    return "(ignored: a line printed by the student's code imitated the check's result)" \
        if "ACADEMY_RESULT" in line else line


def _default_signals():
    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_DFL)
