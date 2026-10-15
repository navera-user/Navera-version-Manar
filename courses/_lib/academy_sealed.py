"""Entry point of a sealed check — started by server/sealed.py (the dashboard and tools/try_lesson.py):

    bash --norc --noprofile -c 'source /opt/ros/humble/setup.bash; exec /usr/bin/python3 -s -B \\
        /academy/lib/academy_sealed.py <payload fd> <result fd>'

1. The process becomes non-dumpable (PR_SET_DUMPABLE 0): no other process of the sandbox can read its
   memory, environment or open files through /proc or ptrace (yama ptrace_scope=1 forbids the rest).
2. It reads the payload (check.py source, courses/<id>/hidden/ files, a nonce) from a memfd and closes
   it: check.py and the hidden data are never on any disk the sandbox can see.
3. It never reads the student's ~/.bashrc itself: that runs in a child, only to compute the
   environment the student's commands get (as before: ~/.bashrc sourced, /academy/lib on PYTHONPATH).
   The checker's sys.path holds read-only folders only.
4. Student code runs only in other processes: commands (subprocess, os.system, sh(), Background()) and
   the student's Python modules (academy_remote: load_student() and imports from writable folders).
5. Checker.run() reports the result on the result fd (inherited by no one), with the nonce.
"""
import ctypes
import json
import os
import sys

PR_SET_DUMPABLE, PR_GET_DUMPABLE = 4, 3


def _seal_process():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0 or libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0) != 0:
        print("The check could not protect itself (prctl) — tell your teacher.", flush=True)
        os._exit(3)


def _read_payload(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while True:
        b = os.read(fd, 1 << 20)
        if not b:
            break
        chunks.append(b)
    os.close(fd)
    return json.loads(b"".join(chunks).decode("utf-8"))


def _student_env(lid, base_env):
    """The environment the student's commands had before (bash -l, ~/.bashrc sourced, cd to the
    lesson): computed by a child shell — the student's files never run in this process."""
    import subprocess
    end = b"\0__ACADEMY_ENV_END__\0"
    cmd = (f"source ~/.bashrc >/dev/null 2>&1; cd ~/lessons/{lid} >/dev/null 2>&1; "
           "env -0; printf '\\0__ACADEMY_ENV_END__\\0'")
    env = dict(base_env)
    try:
        p = subprocess.Popen(["bash", "-lc", cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=base_env, start_new_session=True)
        import select
        import time
        buf, deadline = b"", time.monotonic() + 30
        while end not in buf and time.monotonic() < deadline:
            r, _, _ = select.select([p.stdout], [], [], max(0.0, deadline - time.monotonic()))
            if not r:
                break
            b = os.read(p.stdout.fileno(), 1 << 16)
            if not b:
                break
            buf += b
        p.stdout.close()
        if end in buf:
            got = {}
            for item in buf.split(end)[0].split(b"\0"):
                if b"=" in item:
                    k, v = item.split(b"=", 1)
                    got[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
            if got.get("HOME"):
                env = got
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass                                       # a background job of ~/.bashrc: the sandbox ends it
    except OSError:
        pass
    env["PYTHONPATH"] = "/academy/lib" + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _trusted_sys_path(user_site):
    import academy_remote
    keep = [p for p in sys.path if p and academy_remote.read_only(p)]
    if user_site and os.path.isdir(user_site):
        import site
        before = list(keep)
        sys.path[:] = keep
        site.addsitedir(user_site)
        added = [p for p in sys.path if p not in before]
        i = next((i for i, p in enumerate(before) if p.endswith(("site-packages", "dist-packages"))
                  and not p.startswith("/opt/")), len(before))
        keep = before[:i] + [p for p in added if academy_remote.read_only(p)] + before[i:]
    sys.path[:] = keep


def _patch_children(student_env):
    """Every command check.py starts gets the student's environment (unless it passes env=)."""
    import inspect
    import subprocess
    orig = subprocess.Popen._execute_child
    pos = list(inspect.signature(orig).parameters).index("env") - 1      # without self

    def execute_child(self, *a, **k):
        a = list(a)
        if len(a) > pos and a[pos] is None:
            a[pos] = student_env
        elif "env" in k and k["env"] is None:
            k["env"] = student_env
        return orig(self, *a, **k)
    subprocess.Popen._execute_child = execute_child

    def system(command):
        rc = subprocess.call(command, shell=True)
        return rc << 8 if rc >= 0 else -rc
    os.system = system


def main():
    _seal_process()
    payload_fd, result_fd = int(sys.argv[1]), int(sys.argv[2])
    P = _read_payload(payload_fd)
    devnull = os.open("/dev/null", os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    os.set_inheritable(result_fd, False)
    nonce, lid = P["nonce"], P["lid"]
    hidden = {k: bytes.fromhex(v) for k, v in P.get("hidden", {}).items()}
    source = P["source"]
    user_site = P.get("user_site") or ""
    stored_seal = P.get("seal")
    del P

    _trusted_sys_path(user_site)
    import academy_remote
    lesson = os.path.join(os.environ.get("HOME", "/home/student"), "lessons", lid)
    student_env = _student_env(lid, dict(os.environ))
    if not os.path.isdir(lesson):
        print(f"Your lesson folder ~/lessons/{lid} is missing — open the lesson once to get its files.")
        _report(result_fd, nonce, {"passed": 0, "total": 1})
        os._exit(1)
    os.chdir(lesson)
    _patch_children(student_env)
    untrusted = ["/home/", "/tmp/", "/dev/shm/", "/run/", "/var/tmp/", os.path.realpath(lesson) + "/"]
    academy_remote.activate(student_env, lesson, untrusted)

    import academy_check
    sent = []

    def report(result):
        sent.append(result)
        _report(result_fd, nonce, result)
    academy_check._SEALED = {"report": report, "hidden": hidden, "seal": stored_seal}

    import linecache
    import types
    filename = f"/academy/courses/{lid}/check.py"
    lines = source.splitlines(True)
    linecache.cache[filename] = (len(source), None, lines, filename)
    main_mod = types.ModuleType("__main__")
    main_mod.__file__ = filename
    main_mod.__builtins__ = __builtins__
    sys.modules["__main__"] = main_mod
    sys.argv = [filename]
    code = 0
    try:
        exec(compile(source, filename, "exec", dont_inherit=True), main_mod.__dict__)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except BaseException:                                        # noqa: BLE001
        import traceback
        traceback.print_exc()
        code = 1
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        academy_remote.shutdown()
    if not sent:
        code = code or 1
    os._exit(code)


def _report(fd, nonce, result):
    try:
        os.write(fd, (nonce + " " + json.dumps(result) + "\n").encode())
    except OSError:
        pass


if __name__ == "__main__":
    main()
