#!/usr/bin/env python3
"""NAVERA Academy — the course dashboard (http://<jetson-ip>:8300).

Students log in, read a lesson beside an editor, a terminal and the simulator, run the
lab in their own sandbox (sandbox.py) and press "Check my work". The teacher creates the
accounts, follows the progress, resets copies and refreshes the base snapshot.
"""
import fcntl
import functools
import json
import os
import pty
import re
import secrets
import select
import shutil
import signal
import socket
import struct
import subprocess
import termios
import threading
import time

from flask import Flask, abort, jsonify, redirect, request, send_file, send_from_directory, session
from flask_sock import Sock
from werkzeug.security import check_password_hash, generate_password_hash

import config
import sandbox
import workspaces

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
sock = Sock(app)
_lock = threading.RLock()

for d in (config.STATE, config.STUDENTS, config.LOGS, config.COURSES):
    os.makedirs(d, exist_ok=True)
_secret = os.path.join(config.STATE, "secret.key")
if not os.path.exists(_secret):
    with open(_secret, "w") as f:
        f.write(secrets.token_hex(32))
    os.chmod(_secret, 0o600)
app.secret_key = open(_secret).read().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  MAX_CONTENT_LENGTH=8 * 1024 * 1024)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,23}$")
HIDDEN = {".git", "build", "install", "log", "__pycache__", ".navera_state", ".torch_cache",
          ".cache", ".ros", ".navera_sim", ".pytest_cache"}


# ---------------------------------------------------------------- state files
def _load(name, default):
    p = os.path.join(config.STATE, name)
    try:
        with open(p) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(name, data):
    p = os.path.join(config.STATE, name)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, p)


def users():
    return _load("users.json", {})


def ensure_teacher():
    with _lock:
        u = users()
        if not any(v["role"] == "teacher" for v in u.values()):
            pw = secrets.token_urlsafe(9)
            u["teacher"] = {"role": "teacher", "pw": generate_password_hash(pw), "index": 0,
                            "display": "Teacher"}
            _save("users.json", u)
            with open(os.path.join(config.STATE, "teacher_password.txt"), "w") as f:
                f.write(pw + "\n")
            os.chmod(os.path.join(config.STATE, "teacher_password.txt"), 0o600)
            print(f"teacher account created: teacher / {pw}  (state/teacher_password.txt)")


# ---------------------------------------------------------------- auth
def login_required(role=None):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **kw):
            name = session.get("user")
            u = users().get(name) if name else None
            if not u:
                abort(401)
            if role and u["role"] != role:
                abort(403)
            request.user = name
            request.urec = u
            return fn(*a, **kw)
        return wrap
    return deco


def sandbox_user():
    """The sandbox to use: the logged-in student, or the student a teacher is viewing."""
    name = request.user
    if request.urec["role"] == "teacher":
        name = request.args.get("as") or (request.get_json(silent=True) or {}).get("as") or "teacher"
    u = users().get(name)
    if not u:
        abort(404)
    workspaces.create_student(name)
    return name, u


@app.post("/api/login")
def api_login():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip().lower()
    u = users().get(name)
    if not u or not check_password_hash(u["pw"], d.get("password") or ""):
        time.sleep(0.7)
        return jsonify(error="Wrong name or password"), 401
    session.clear()
    session["user"] = name
    session.permanent = True
    return jsonify(ok=True, role=u["role"])


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@login_required()
def api_me():
    b = workspaces.base_info()
    return jsonify(name=request.user, role=request.urec["role"], display=request.urec.get("display", request.user),
                   domain=config.domain_for(request.urec["index"]), base=b, host=_host_ip())


@app.post("/api/password")
@login_required()
def api_password():
    d = request.get_json(force=True)
    with _lock:
        u = users()
        if not check_password_hash(u[request.user]["pw"], d.get("old") or ""):
            return jsonify(error="The current password is wrong"), 400
        if len(d.get("new") or "") < 6:
            return jsonify(error="At least 6 characters"), 400
        u[request.user]["pw"] = generate_password_hash(d["new"])
        _save("users.json", u)
    return jsonify(ok=True)


def _host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


# ---------------------------------------------------------------- courses
def lesson_ids():
    return sorted(d for d in os.listdir(config.COURSES)
                  if os.path.isfile(os.path.join(config.COURSES, d, "meta.json")))


def lesson_meta(lid):
    with open(os.path.join(config.COURSES, lid, "meta.json")) as f:
        m = json.load(f)
    m["id"] = lid
    return m


@app.get("/api/courses")
@login_required()
def api_courses():
    name = request.args.get("as") if request.urec["role"] == "teacher" else request.user
    prog = _load("progress.json", {}).get(name or "", {})
    mods = _load_modules()
    out = []
    for lid in lesson_ids():
        m = lesson_meta(lid)
        m["progress"] = prog.get(lid, {})
        out.append(m)
    return jsonify(lessons=out, modules=mods)


def _load_modules():
    p = os.path.join(config.COURSES, "modules.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return []


@app.get("/api/lesson/<lid>")
@login_required()
def api_lesson(lid):
    if lid not in lesson_ids():
        abort(404)
    name, _ = sandbox_user()
    workspaces.install_lesson(name, lid)
    base = os.path.join(config.COURSES, lid)
    def read(fn):
        p = os.path.join(base, fn)
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    m = lesson_meta(lid)
    m["course"] = read("lesson.md")
    m["lab"] = read("lab.md")
    m["has_check"] = os.path.exists(os.path.join(base, "check.py"))
    m["progress"] = _load("progress.json", {}).get(name, {}).get(lid, {})
    m["workdir"] = f"lessons/{lid}"
    m["outdated"] = workspaces.installed_version(name, lid) != workspaces.course_version(lid)
    return jsonify(m)


@app.get("/course-assets/<lid>/<path:fn>")
@login_required()
def course_asset(lid, fn):
    if lid not in lesson_ids():
        abort(404)
    return send_from_directory(os.path.join(config.COURSES, lid, "assets"), fn)


def run_in_sandbox(name, cmd, timeout=180, resources=(), heavy=False):
    u = users()[name]
    argv = sandbox.bwrap_argv(name, workspaces.student_home(name), u["index"], cmd,
                              resources=resources, heavy=heavy, extra_ro=_course_mounts())
    try:
        r = subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                           start_new_session=True, preexec_fn=_default_signals)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") + f"\n⏱ The check took longer than {timeout} s and was stopped."


def _default_signals():
    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_DFL)


def _course_mounts():
    lib = os.path.join(config.COURSES, "_lib")
    m = [(lib, "/academy/lib")] if os.path.isdir(lib) else []
    for lid in lesson_ids():
        m.append((os.path.join(config.COURSES, lid), f"/academy/courses/{lid}"))
    return m


@app.post("/api/lesson/<lid>/check")
@login_required()
def api_check(lid):
    if lid not in lesson_ids():
        abort(404)
    name, _ = sandbox_user()
    m = lesson_meta(lid)
    timeout = int(m.get("check_timeout_s", 180))
    res = [r for r in m.get("resources", []) if _holder(r) == name]
    code, out = run_in_sandbox(name, ["bash", "-lc",
                                      f"source ~/.bashrc >/dev/null 2>&1; cd ~/lessons/{lid} && "
                                      f"PYTHONPATH=/academy/lib:$PYTHONPATH python3 /academy/courses/{lid}/check.py"],
                               timeout=timeout, resources=res, heavy=bool(res))
    score = None
    mres = re.findall(r"^ACADEMY_RESULT (\{.*\})$", out, re.M)
    if mres:
        try:
            score = json.loads(mres[-1])
        except json.JSONDecodeError:
            pass
    out = re.sub(r"^ACADEMY_RESULT .*\n?", "", out, flags=re.M)
    passed = code == 0 and (score is None or score.get("passed") == score.get("total"))
    if request.urec["role"] != "teacher" or name == request.user:
        with _lock:
            p = _load("progress.json", {})
            rec = p.setdefault(name, {}).setdefault(lid, {})
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["last"] = time.strftime("%Y-%m-%d %H:%M")
            if score:
                rec["best"] = max(rec.get("best", 0), score.get("passed", 0))
                rec["total"] = score.get("total")
            if passed:
                rec["status"] = "passed"
                rec.setdefault("passed_at", rec["last"])
            elif rec.get("status") != "passed":
                rec["status"] = "started"
            _save("progress.json", p)
    return jsonify(passed=passed, code=code, output=out[-20000:], score=score)


@app.post("/api/lesson/<lid>/reset")
@login_required()
def api_lesson_reset(lid):
    if lid not in lesson_ids():
        abort(404)
    name, _ = sandbox_user()
    workspaces.install_lesson(name, lid, overwrite=True)
    return jsonify(ok=True)


@app.post("/api/reset_navera")
@login_required()
def api_reset_navera():
    name, _ = sandbox_user()
    _kill_terminals(name)
    saved = workspaces.reset_navera(name)
    return jsonify(ok=True, backup=os.path.basename(saved) if saved else None)


# ---------------------------------------------------------------- files
def _safe(name, rel):
    home = os.path.realpath(workspaces.student_home(name))
    p = os.path.realpath(os.path.join(home, (rel or "").lstrip("/")))
    if p != home and not p.startswith(home + os.sep):
        abort(403)
    return home, p


@app.get("/api/files")
@login_required()
def api_files():
    name, _ = sandbox_user()
    home, p = _safe(name, request.args.get("path", ""))
    if not os.path.isdir(p):
        abort(404)
    items = []
    for e in sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower())):
        if e.name in HIDDEN or (e.name.startswith(".") and e.name not in (".bashrc",)):
            continue
        try:
            isdir = e.is_dir()
            size = 0 if isdir else e.stat().st_size
        except OSError:
            continue
        items.append({"name": e.name, "dir": isdir, "size": size,
                      "path": os.path.relpath(e.path, home)})
    return jsonify(items=items)


TEXT_LIMIT = 2 * 1024 * 1024


@app.get("/api/file")
@login_required()
def api_file_get():
    name, _ = sandbox_user()
    home, p = _safe(name, request.args.get("path"))
    if not os.path.isfile(p):
        abort(404)
    if request.args.get("raw"):
        return send_file(p)
    if os.path.getsize(p) > TEXT_LIMIT:
        return jsonify(binary=True, reason="file too large to edit")
    with open(p, "rb") as f:
        data = f.read()
    try:
        return jsonify(content=data.decode("utf-8"), mtime=os.path.getmtime(p))
    except UnicodeDecodeError:
        return jsonify(binary=True, reason="binary file")


@app.put("/api/file")
@login_required()
def api_file_put():
    name, _ = sandbox_user()
    d = request.get_json(force=True)
    home, p = _safe(name, d.get("path"))
    if os.path.isdir(p):
        abort(400)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".academy-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(d.get("content", ""))
    if os.path.exists(p):
        shutil.copymode(p, tmp)
    os.replace(tmp, p)
    return jsonify(ok=True, mtime=os.path.getmtime(p))


@app.post("/api/file/new")
@login_required()
def api_file_new():
    name, _ = sandbox_user()
    d = request.get_json(force=True)
    home, p = _safe(name, d.get("path"))
    if os.path.exists(p):
        return jsonify(error="already exists"), 400
    if d.get("dir"):
        os.makedirs(p)
    else:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()
    return jsonify(ok=True)


@app.post("/api/file/delete")
@login_required()
def api_file_delete():
    name, _ = sandbox_user()
    home, p = _safe(name, (request.get_json(force=True)).get("path"))
    if p == home or os.path.relpath(p, home) in ("navera", "lessons"):
        return jsonify(error="this folder cannot be deleted (use Reset)"), 400
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p)
    elif os.path.lexists(p):
        os.remove(p)
    return jsonify(ok=True)


# ---------------------------------------------------------------- bookings
def bookings():
    return _load("bookings.json", {})


def _holder(res):
    b = bookings().get(res)
    return b["user"] if b else None


def _ports_busy(ports):
    out = subprocess.run(["ss", "-ltnH"], text=True, capture_output=True).stdout
    return [p for p in ports if re.search(rf":{p}\s", out)]


@app.get("/api/bookings")
@login_required()
def api_bookings():
    b = bookings()
    return jsonify({k: {"title": v["title"], "holder": b.get(k, {}).get("user"),
                        "since": b.get(k, {}).get("since")} for k, v in config.RESOURCES.items()})


@app.post("/api/book")
@login_required()
def api_book():
    d = request.get_json(force=True)
    res, action = d.get("resource"), d.get("action", "take")
    if res not in config.RESOURCES:
        abort(404)
    name = request.user
    with _lock:
        b = bookings()
        cur = b.get(res, {}).get("user")
        if action == "take":
            if cur and cur != name:
                return jsonify(error=f"{res} is used by {cur}. Ask them or the teacher to release it."), 409
            busy = _ports_busy(config.RESOURCES[res].get("ports", []))
            if busy and not cur:
                return jsonify(error=f"ports {busy} are in use on the Jetson (the teacher's NAVERA or a demo is "
                                     f"running). Ask the teacher."), 409
            b[res] = {"user": name, "since": time.strftime("%H:%M")}
        else:
            if cur and cur != name and request.urec["role"] != "teacher":
                abort(403)
            if cur:
                _kill_terminals(cur, only_with=res)
            b.pop(res, None)
        _save("bookings.json", b)
    return jsonify(ok=True)


# ---------------------------------------------------------------- terminal
TERMS = {}     # id -> {"user", "pid", "fd", "resources"}


def _kill_terminals(name, only_with=None):
    for tid, t in list(TERMS.items()):
        if t["user"] == name and (only_with is None or only_with in t["resources"]):
            _kill(t)


def _kill(t):
    try:
        os.killpg(t["pid"], signal.SIGKILL)
    except ProcessLookupError:
        pass


@sock.route("/ws/term")
def ws_term(ws):
    name = session.get("user")
    u = users().get(name) if name else None
    if not u:
        ws.close()
        return
    if u["role"] == "teacher" and request.args.get("as"):
        name = request.args["as"]
        u = users().get(name)
        if not u:
            ws.close()
            return
    workspaces.create_student(name)
    cwd = request.args.get("cwd", "")
    if not re.fullmatch(r"[A-Za-z0-9_./-]*", cwd) or ".." in cwd:
        cwd = ""
    res = [r for r in config.RESOURCES if _holder(r) == name]
    cmd = ["bash", "-c", f"cd ~/{cwd} 2>/dev/null; exec bash --rcfile ~/.bashrc -i"]
    argv = sandbox.bwrap_argv(name, workspaces.student_home(name), u["index"], cmd,
                              resources=res, heavy="sim" in res or "camera" in res,
                              extra_ro=_course_mounts(), interactive=True)
    pid, fd = pty.fork()
    if pid == 0:
        try:
            for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP, signal.SIGPIPE, signal.SIGHUP, signal.SIGTERM):
                signal.signal(sig, signal.SIG_DFL)   # a server started with & ignores SIGINT: undo it
            os.execvp(argv[0], argv)
        finally:
            os._exit(1)
    tid = f"{pid}"
    TERMS[tid] = {"user": name, "pid": pid, "fd": fd, "resources": res}
    if res:
        ws.send(f"\x1b[33m[this terminal has access to: {', '.join(res)}]\x1b[0m\r\n")
    alive = [True]

    def reader():
        try:
            while alive[0]:
                r, _, _ = select.select([fd], [], [], 0.5)
                if fd in r:
                    try:
                        data = os.read(fd, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    ws.send(data.decode("utf-8", "replace"))
        except Exception:
            pass
        finally:
            alive[0] = False
            try:
                ws.send("\r\n\x1b[31m[terminal closed — press Enter or open a new one]\x1b[0m\r\n")
                ws.close()
            except Exception:
                pass

    threading.Thread(target=reader, daemon=True).start()
    try:
        while alive[0]:
            msg = ws.receive(timeout=1)
            if msg is None:
                continue
            if isinstance(msg, str) and msg.startswith("\x00resize:"):
                try:
                    rows, cols = map(int, msg[8:].split("x"))
                    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                except (ValueError, OSError):
                    pass
                continue
            os.write(fd, msg.encode() if isinstance(msg, str) else msg)
    except Exception:
        pass
    finally:
        alive[0] = False
        _kill(TERMS.pop(tid, {"pid": pid}))
        try:
            os.close(fd)
            os.waitpid(pid, 0)
        except OSError:
            pass


# ---------------------------------------------------------------- teacher
@app.get("/api/admin/students")
@login_required("teacher")
def api_admin_students():
    u = users()
    p = _load("progress.json", {})
    n = len(lesson_ids())
    out = []
    for name, rec in sorted(u.items()):
        if rec["role"] != "student":
            continue
        pr = p.get(name, {})
        out.append({"name": name, "display": rec.get("display", name), "index": rec["index"],
                    "passed": sum(1 for v in pr.values() if v.get("status") == "passed"),
                    "started": sum(1 for v in pr.values() if v.get("status") == "started"),
                    "lessons": n, "progress": pr,
                    "terminals": sum(1 for t in TERMS.values() if t["user"] == name),
                    "backups": len(os.listdir(os.path.join(config.STUDENTS, name, "backups")))
                    if os.path.isdir(os.path.join(config.STUDENTS, name, "backups")) else 0})
    return jsonify(students=out, base=workspaces.base_info(), lessons=lesson_ids())


@app.post("/api/admin/students")
@login_required("teacher")
def api_admin_add():
    d = request.get_json(force=True)
    created = []
    with _lock:
        u = users()
        used = {v["index"] for v in u.values()}
        for line in (d.get("names") or "").splitlines():
            parts = [x.strip() for x in line.split(",")]
            name = parts[0].lower()
            if not name:
                continue
            if not NAME_RE.match(name):
                return jsonify(error=f"'{name}': lower-case letters, digits, _ (2–24, starts with a letter)"), 400
            if name in u:
                continue
            idx = next((i for i in range(1, len(config.STUDENT_DOMAINS)) if i not in used), None)
            if idx is None:
                return jsonify(error=f"at most {len(config.STUDENT_DOMAINS) - 1} students"), 400
            used.add(idx)
            pw = parts[2] if len(parts) > 2 and parts[2] else secrets.token_urlsafe(5)
            u[name] = {"role": "student", "pw": generate_password_hash(pw), "index": idx,
                       "display": parts[1] if len(parts) > 1 and parts[1] else name}
            created.append({"name": name, "password": pw})
        _save("users.json", u)
    for c in created:
        workspaces.create_student(c["name"])
    return jsonify(created=created)


@app.post("/api/admin/student/<name>")
@login_required("teacher")
def api_admin_student(name):
    d = request.get_json(force=True)
    action = d.get("action")
    with _lock:
        u = users()
        if name not in u or u[name]["role"] != "student":
            abort(404)
        if action == "password":
            pw = secrets.token_urlsafe(5)
            u[name]["pw"] = generate_password_hash(pw)
            _save("users.json", u)
            return jsonify(password=pw)
        if action == "delete":
            _kill_terminals(name)
            del u[name]
            _save("users.json", u)
            p = _load("progress.json", {})
            p.pop(name, None)
            _save("progress.json", p)
            b = bookings()
            for k in [k for k, v in b.items() if v["user"] == name]:
                b.pop(k)
            _save("bookings.json", b)
            workspaces.delete_student(name)
            return jsonify(ok=True)
    if action == "reset_navera":
        _kill_terminals(name)
        return jsonify(ok=True, backup=os.path.basename(workspaces.reset_navera(name) or ""))
    if action == "kill":
        _kill_terminals(name)
        return jsonify(ok=True)
    abort(400)


@app.get("/api/admin/commits")
@login_required("teacher")
def api_admin_commits():
    r = subprocess.run(["git", "-C", config.REAL_REPO, "log", "--all", "-25",
                        "--format=%h|%ad|%D|%s", "--date=short"], text=True, capture_output=True)
    out = []
    for line in r.stdout.splitlines():
        h, date, refs, subj = line.split("|", 3)
        out.append({"hash": h, "date": date, "refs": refs, "subject": subj})
    return jsonify(commits=out, base=workspaces.base_info())


BASE_JOB = {"running": False, "log": []}


@app.post("/api/admin/base")
@login_required("teacher")
def api_admin_base():
    commit = (request.get_json(force=True)).get("commit", "")
    if not re.fullmatch(r"[0-9a-f]{6,40}", commit):
        return jsonify(error="give a commit hash"), 400
    if BASE_JOB["running"]:
        return jsonify(error="a base build is already running"), 409

    def job():
        BASE_JOB.update(running=True, log=[], error=None)
        try:
            workspaces.build_base(commit, log=lambda s: BASE_JOB["log"].append(s))
        except Exception as e:
            BASE_JOB["error"] = str(e)
        finally:
            BASE_JOB["running"] = False
    threading.Thread(target=job, daemon=True).start()
    return jsonify(ok=True)


@app.get("/api/admin/base")
@login_required("teacher")
def api_admin_base_state():
    return jsonify(running=BASE_JOB["running"], log=BASE_JOB["log"][-30:], error=BASE_JOB.get("error"),
                   base=workspaces.base_info())


# ---------------------------------------------------------------- pages
@app.get("/")
def page_index():
    if not session.get("user") or session["user"] not in users():
        return send_from_directory(app.static_folder, "login.html")
    return send_from_directory(app.static_folder, "app.html")


@app.get("/teacher")
def page_teacher():
    u = users().get(session.get("user") or "")
    if not u or u["role"] != "teacher":
        return redirect("/")
    return send_from_directory(app.static_folder, "teacher.html")


@app.after_request
def no_cache(r):
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    elif request.path == "/" or request.path == "/teacher" or request.path.endswith((".html", ".js", ".css")):
        # the dashboard changes often: browsers must re-check (they still reuse an unchanged file)
        r.headers["Cache-Control"] = "no-cache"
    return r


if __name__ == "__main__":
    if not workspaces.base_info():
        raise SystemExit("no base yet: python3 -c 'import workspaces; workspaces.build_base(\"<commit>\")'")
    ensure_teacher()
    workspaces.create_student("teacher")
    print(f"NAVERA Academy on http://{_host_ip()}:{config.PORT}")
    app.run(host="0.0.0.0", port=config.PORT, threaded=True)
