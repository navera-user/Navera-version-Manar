"""One private network per student, shared by all of that student's sandboxes.

Every student sandbox (each terminal tab, the sealed check, try_lesson runs) used to get its own
network namespace (bwrap --unshare-net): ROS 2 nodes started in one terminal were invisible to a second
terminal and to the checker. Now each student has ONE long-lived "holder" process:

    bwrap --unshare-user --unshare-net ... -- sleep infinity      (argv[0] "academy-netns-<name>")

which owns a user namespace + a network namespace with only a loopback (bwrap brings `lo` up). A
student sandbox is started inside them:

    systemd-run --scope ... nsenter --target <holder> --user --net --preserve-credentials -- bwrap ...

(bwrap then runs without --unshare-net; its own user/pid/ipc/uts/mount namespaces are created nested,
exactly as before). No root needed: the holder's namespaces belong to this uid. Different students
have different holders, so they cannot see each other; nothing on the host network is reachable.

Lifetime: started on demand (file lock: the server and tools/try_lesson.py share it); its record in
state/netns/<name>.json (pid + start time, so a reused PID is never trusted). reap() stops a holder when
no other process has used its network for IDLE seconds (the server calls it every minute; try_lesson
after its run); stop() when the student is deleted. After a server restart, a living holder is reused
and a dead one is replaced.
"""
import fcntl
import hashlib
import json
import os
import select
import shutil
import signal
import subprocess
import time

import config

IDLE = 600                       # seconds without any process in the network before the holder stops
MARK = "academy-netns-"
DIR = os.path.join(config.STATE, "netns")
# one folder per academy (live, copies, worktrees never mix): /dev/shm/academy-<uid>-<hash of STATE>/
SHM_ROOT = os.path.join("/dev/shm", f"academy-{os.getuid()}-" +
                        hashlib.sha1(os.path.realpath(config.STATE).encode()).hexdigest()[:10])


def enabled():
    """ON by default (ROS missions re-verified with it, 2026-10-16). ACADEMY_SHARED_NETNS=0 turns it off:
    every sandbox then gets its own network again (bwrap --unshare-net)."""
    return os.environ.get("ACADEMY_SHARED_NETNS", "1") != "0"


def _rec_path(name):
    return os.path.join(DIR, name + ".json")


class _Lock:
    def __init__(self, name):
        self.p = os.path.join(DIR, name + ".lock")

    def __enter__(self):
        os.makedirs(DIR, exist_ok=True)
        self.f = open(self.p, "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _start_time(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[19]      # field 22: start time (clock ticks)
    except (OSError, IndexError):
        return None


def _netns(pid):
    try:
        return os.readlink(f"/proc/{pid}/ns/net")
    except OSError:
        return None


def _load(name):
    try:
        with open(_rec_path(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save(name, rec):
    tmp = _rec_path(name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, _rec_path(name))


def _alive(name, rec):
    """The record's holder is still running (same PID, same start time, same network, our marker)."""
    if not rec:
        return False
    pid = rec.get("pid")
    if not isinstance(pid, int) or _start_time(pid) != rec.get("start") or _netns(pid) != rec.get("net"):
        return False
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().split(b"\0")[0] == (MARK + name).encode()
    except OSError:
        return False


def _usr_mounts():
    a = ["--ro-bind", "/usr", "/usr"]
    for l in ("bin", "sbin", "lib", "lib64"):
        p = "/" + l
        if os.path.islink(p):
            a += ["--symlink", os.readlink(p), p]
        elif os.path.isdir(p):
            a += ["--ro-bind", p, p]
    return a


def _spawn(name):
    """Start a holder (detached: setsid -f, so it is never a child of the server). Returns its record."""
    r, w = os.pipe()
    # keep it minimal: with --dev (or --unshare-pid/--proc) bwrap 0.6 nests a second user namespace
    # and the network can no longer be joined (setns EPERM)
    argv = ["setsid", "-f", "bwrap", "--unshare-user", "--unshare-net", "--new-session"] + _usr_mounts() + \
           ["--tmpfs", "/tmp", "--info-fd", str(w), "--clearenv",
            "--", "/bin/bash", "-c", 'exec -a "$0" sleep infinity', MARK + name]
    try:
        subprocess.run(argv, pass_fds=(w,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=20)
    finally:
        os.close(w)
    try:
        data, deadline = b"", time.monotonic() + 20
        while time.monotonic() < deadline:          # bwrap writes {"child-pid": …} then closes the fd
            ready, _, _ = select.select([r], [], [], max(0.0, deadline - time.monotonic()))
            b = os.read(r, 4096) if ready else b""
            if not b:
                break
            data += b
        info = json.loads(data)
    finally:
        os.close(r)
    pid = int(info["child-pid"])
    for _ in range(200):                             # until bash has exec'd "sleep" under its marker
        rec = {"pid": pid, "start": _start_time(pid), "net": _netns(pid), "created": time.time()}
        if _alive(name, rec):
            break
        time.sleep(0.02)
    else:
        _kill(pid)
        raise RuntimeError(f"the network holder of {name} did not start")
    if subprocess.run(_join(pid) + ["true"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, timeout=20).returncode != 0:
        _kill(pid)                                   # never hand out a network that cannot be joined
        raise RuntimeError(f"the network of {name} cannot be joined")
    return rec


def _join(pid):
    return ["nsenter", f"--target={pid}", "--user", "--net", "--preserve-credentials", "--"]


def holder(name):
    """PID of the student's holder, started if needed. Marks the network as just used."""
    with _Lock(name):
        rec = _load(name)
        if not _alive(name, rec):
            rec = _spawn(name)
        rec["used"] = time.time()
        _save(name, rec)
        return rec["pid"]


def shm(name):
    """The student's shared /dev/shm: a folder in the host's /dev/shm (RAM), private (0700) to this
    student's sandboxes. Fast DDS (ROS 2) uses shared memory between processes it believes are on the
    same host (same loopback-only address), so all sandboxes sharing a network must share /dev/shm
    too, or topics are discovered but no data arrives. Removed with the holder."""
    p = os.path.join(SHM_ROOT, name)
    os.makedirs(SHM_ROOT, mode=0o700, exist_ok=True)
    os.makedirs(p, mode=0o700, exist_ok=True)
    return p


def _rm_shm(name):
    shutil.rmtree(os.path.join(SHM_ROOT, name), ignore_errors=True)


def prefix(name):
    """argv to put in front of bwrap: run it inside the student's own network."""
    return _join(holder(name))


def users_of(net, holder_pid):
    """PIDs (other than the holder) whose network is `net`. Processes we cannot inspect are skipped:
    every sandbox has a readable process in it (the outer bwrap), so a busy network is always seen."""
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit() and int(d) != holder_pid and _netns(d) == net:
            out.append(int(d))
    return out


def _kill(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def stop(name):
    """Stop the student's holder (student deleted). Sandboxes still running keep their network."""
    if os.path.exists(_rec_path(name)):
        _stop_locked(name)
    _rm_shm(name)
    try:
        os.remove(os.path.join(DIR, name + ".lock"))
    except OSError:
        pass


def _stop_locked(name):
    with _Lock(name):
        rec = _load(name)
        if _alive(name, rec):
            _kill(rec["pid"])
        try:
            os.remove(_rec_path(name))
        except OSError:
            pass


def reap(name=None, idle=IDLE):
    """Stop the holders (of `name`, or all) that nobody used for `idle` seconds; forget dead ones."""
    if not os.path.isdir(DIR):
        return
    names = [f[:-5] for f in os.listdir(DIR) if f.endswith(".json") and (name is None or f[:-5] == name)]
    for n in names:
        with _Lock(n):
            rec = _load(n)
            if not _alive(n, rec):
                try:
                    os.remove(_rec_path(n))
                except OSError:
                    pass
                if not rec or not users_of(rec.get("net"), rec.get("pid")):
                    _rm_shm(n)
                continue
            if users_of(rec["net"], rec["pid"]):
                rec["used"] = time.time()
                _save(n, rec)
                continue
            if time.time() - rec.get("used", 0) >= idle:
                _kill(rec["pid"])
                os.remove(_rec_path(n))
                _rm_shm(n)


def release(name, wait=5.0, idle=2):
    """A one-off run (tools/try_lesson.py) ended: give its sandbox processes `wait` seconds to exit,
    then stop the holder unless something still uses it (or holder() was called in the last `idle` s)."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        rec = _load(name)
        if not _alive(name, rec) or not users_of(rec["net"], rec["pid"]):
            break
        time.sleep(0.2)
    reap(name, idle=idle)
