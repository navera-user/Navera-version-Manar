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
import unicodedata
import urllib.parse
import select
import shutil
import signal
import socket
import struct
import subprocess
import termios
import threading
import time

from flask import Flask, Response, abort, jsonify, make_response, redirect, render_template, request, send_file, send_from_directory, session
from flask_sock import Sock
from werkzeug.security import check_password_hash, generate_password_hash

from flask.sessions import SecureCookieSessionInterface

import certs
import config
import orgs
import simlite
import webtools
import netns
import sandbox
import sealed
import workspaces

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
sock = Sock(app)


class _FromProxy:
    """Behind the HTTPS front door (Caddy on this machine), take the visitor's real address and scheme
    from its headers — only when the request really comes from 127.0.0.1, so nobody can fake them."""
    def __init__(self, wsgi):
        self.wsgi = wsgi

    def __call__(self, env, start):
        if env.get("REMOTE_ADDR") == "127.0.0.1" and env.get("HTTP_X_FORWARDED_FOR"):
            # the LAST address is the one our own front door added; earlier ones come from the visitor
            env["REMOTE_ADDR"] = env["HTTP_X_FORWARDED_FOR"].split(",")[-1].strip()
            proto = env.get("HTTP_X_FORWARDED_PROTO", "").split(",")[-1].strip()
            if proto in ("http", "https"):
                env["wsgi.url_scheme"] = proto
        return self.wsgi(env, start)


app.wsgi_app = _FromProxy(app.wsgi_app)
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

class _Sessions(SecureCookieSessionInterface):
    """Over HTTPS (the public address) the sign-in cookie is marked Secure, so a browser never sends it
    over plain HTTP; on the local network (http://…:8300, navera-academy.local) sign-in keeps working."""
    def get_cookie_secure(self, app):
        return request.scheme == "https"


app.session_interface = _Sessions()


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


# roles: admin (the client's manager) → teacher (own classes; "pending" until the admin approves) → student
STAFF = ("teacher", "admin")


def is_staff(u):
    return bool(u) and u.get("role") in STAFF and u.get("status", "active") == "active"


def is_admin(u):
    return bool(u) and u.get("role") == "admin"


def can_see(viewer, vrec, name):
    """May this account look at (and act on) that student's work?"""
    if viewer == name:
        return True
    if not is_staff(vrec):
        return False
    s = users().get(name)
    if not s or s.get("role") != "student":
        return False
    if is_admin(vrec):
        return True
    c = orgs.get(s.get("class") or "")
    return bool(c) and c["teacher"] == viewer


def visible_students(viewer, vrec, cid=None):
    out = {}
    own = {c["id"] for c in orgs.owned_by(viewer)}
    for name, rec in users().items():
        if rec.get("role") != "student":
            continue
        if not is_admin(vrec) and rec.get("class") not in own:
            continue
        if cid is not None and (rec.get("class") or "") != cid:
            continue
        out[name] = rec
    return out


def ensure_teacher():
    """The IRIS support account ("teacher", password in state/teacher_password.txt) is an administrator."""
    with _lock:
        u = users()
        changed = False
        if "teacher" in u and u["teacher"]["role"] == "teacher":           # before classes: one teacher = the admin
            u["teacher"].update(role="admin", support=True)
            changed = True
        if not any(v["role"] == "admin" for v in u.values()):
            pw = secrets.token_urlsafe(9)
            u["teacher"] = {"role": "admin", "support": True, "pw": generate_password_hash(pw), "index": 0,
                            "display": "IRIS support"}
            changed = True
            with open(os.path.join(config.STATE, "teacher_password.txt"), "w") as f:
                f.write(pw + "\n")
            os.chmod(os.path.join(config.STATE, "teacher_password.txt"), 0o600)
            print(f"IRIS support account created: teacher / {pw}  (state/teacher_password.txt)")
        if changed:
            _save("users.json", u)


# ---------------------------------------------------------------- auth
PENDING_OK = {"api_me", "api_password", "api_prefs_get", "api_prefs_set", "api_pending_code"}


def login_required(role=None):
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **kw):
            name = session.get("user")
            u = users().get(name) if name else None
            if not u:
                abort(401)
            if u.get("status") == "pending" and fn.__name__ not in PENDING_OK:
                return jsonify(error="Your teacher account is waiting for the administrator's approval."), 403
            if (role == "teacher" and not is_staff(u)) or (role == "admin" and not is_admin(u)) \
                    or (role == "student" and u["role"] != "student"):
                abort(403)
            request.user = name
            request.urec = u
            return fn(*a, **kw)
        return wrap
    return deco


def sandbox_user():
    """The sandbox to use: the logged-in student, or the student a teacher is viewing."""
    name = request.user
    if is_staff(request.urec):
        other = request.args.get("as") or (request.get_json(silent=True) or {}).get("as")
        if other:
            if not can_see(request.user, request.urec, other):
                abort(403)
            name = other
    u = users().get(name)
    if not u:
        abort(404)
    workspaces.create_student(name)
    return name, u


_fails = {}           # ("dev:", "ip:", "acc:", "user:" or "setup:" key) -> [times of wrong passwords]
LOGIN_FAILS = 30      # wrong passwords on one browser (any accounts) before it waits: stops guessing many accounts
NETWORK_FAILS = 100   # per network address: a whole school shares one, so only a high ceiling against robots
ACCOUNT_FAILS = 5     # on one account FROM ONE BROWSER: then that browser gets one try per ACCOUNT_PAUSE s
ACCOUNT_PAUSE = 30    # (keyed per browser, so a classmate's wrong tries never block the student's own browser)
ACCOUNT_CEILING = 50  # on one account from all browsers in 15 min: a real attack — the teacher resets it
DEVICE_COOKIE = "nav_dev"


def _recent(k, now=None):
    now = now or time.time()
    _fails[k] = [t for t in _fails.get(k, []) if now - t < 900]
    return _fails[k]


def _too_many_fails(*keys):
    return any(len(_recent(k)) >= 10 for k in keys)


def _login_wait(dev, ip, acc_dev, acc):
    """Seconds this sign-in must wait (0 = may try now), and why."""
    now = time.time()
    if len(_recent(acc, now)) >= ACCOUNT_CEILING:
        return int(900 - (now - _fails[acc][0])) + 1, "ceiling"
    if len(_recent(dev, now)) >= LOGIN_FAILS:
        return int(900 - (now - _fails[dev][0])) + 1, "device"
    if len(_recent(ip, now)) >= NETWORK_FAILS:
        return int(900 - (now - _fails[ip][0])) + 1, "network"
    f = _recent(acc_dev, now)
    if len(f) >= ACCOUNT_FAILS and now - f[-1] < ACCOUNT_PAUSE:
        return int(ACCOUNT_PAUSE - (now - f[-1])) + 1, "account"
    return 0, ""


@app.post("/api/login")
def api_login():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip().lower()
    if not name or not d.get("password"):
        return jsonify(error="Enter your name (or e-mail) and your password."), 400
    dev_id = request.cookies.get(DEVICE_COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", dev_id):
        dev_id = secrets.token_urlsafe(18)

    def reply(body, code=200):
        r = make_response(jsonify(body), code)
        r.set_cookie(DEVICE_COOKIE, dev_id, max_age=3 * 365 * 86400, httponly=True, samesite="Lax",
                     secure=request.scheme == "https")
        return r

    dev, ip, acc = "dev:" + dev_id, "ip:" + (request.remote_addr or "?"), "user:" + name
    acc_dev = f"acc:{name}|{dev_id}"
    wait, why = _login_wait(dev, ip, acc_dev, acc)
    if wait:
        mins = max(1, round(wait / 60))
        msg = {"account": f"Several wrong passwords — wait {wait} seconds and try again.",
               "device": f"Too many wrong passwords on this computer — wait {mins} min.",
               "network": f"Too many wrong passwords from this network — wait {mins} min.",
               "ceiling": "This account is protected after many wrong passwords — ask your teacher for a new password."}[why]
        return reply({"error": msg, "wait": wait, "why": why}, 429)
    all_users = users()
    if name not in all_users and "@" in name:                     # sign in with the e-mail address too
        name = next((k for k, v in all_users.items() if (v.get("email") or "").lower() == name), name)
    u = all_users.get(name)
    if not u or not u.get("pw") or not check_password_hash(u["pw"], d.get("password") or ""):
        now = time.time()
        for k in (dev, ip, acc_dev, acc):
            _fails[k].append(now)
        time.sleep(0.7)
        return reply({"error": "Wrong name or password"}, 401)
    _fails.pop(dev, None)                 # a right password clears this browser's counts
    _fails.pop(acc_dev, None)
    session.clear()
    session["user"] = name
    session.permanent = True
    return reply({"ok": True, "role": u["role"], "status": u.get("status", "active")})


# ---------------------------------------------------------------- accounts: sign-up, preferences, Google/GitHub
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)
_signups = {}          # ip -> [times]: at most SIGNUP_PER_HOUR new accounts per device per hour
SIGNUP_PER_HOUR = 30   # a whole class may sign up from one school address


def settings():
    s = {"allow_signup": True}
    s.update(_load("settings.json", {}))
    return s


def oauth_conf():
    """state/oauth.json: {"base_url": "https://academy.example.com",
    "google": {"client_id": "…", "client_secret": "…"}, "github": {"client_id": "…", "client_secret": "…"}}"""
    c = _load("oauth.json", {})
    ok = lambda p: bool(c.get("base_url") and (c.get(p) or {}).get("client_id") and (c.get(p) or {}).get("client_secret"))
    return c, {p: ok(p) for p in OAUTH}


def _text(v, n=80):
    """A name typed by someone: one line, no invisible/direction-changing characters (U+202E…)."""
    v = "".join(ch for ch in str(v or "") if unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs"))
    return re.sub(r"\s+", " ", v).strip()[:n]


def new_student(display, email=None, password=None, provider=None, provider_id=None, klass=None, role="student", status=None):
    """Create an account (login name derived from the e-mail) and its sandbox. Returns the login name."""
    display = _text(display, 60)
    with _lock:
        u = users()
        used = {v["index"] for v in u.values()}
        idx = next((i for i in range(1, len(config.STUDENT_DOMAINS)) if i not in used), None)
        if idx is None:
            raise ValueError("The academy is full — ask the teacher.")
        base = re.sub(r"[^a-z0-9_]", "", ((email or display or "student").split("@")[0]).lower().replace(".", "_").replace("-", "_"))
        if not base or not base[0].isalpha():
            base = "s" + base
        base = base[:18]
        name, n = base if len(base) >= 2 else base + "1", 1
        while name in u:
            n += 1
            name = f"{base}{n}"
        rec = {"role": role, "index": idx, "display": (display or name)[:40], "created": time.strftime("%Y-%m-%d %H:%M"),
               "pw": generate_password_hash(password) if password else None}
        if email:
            rec["email"] = email.lower()
        if provider:
            rec["provider"] = provider
            rec["provider_id"] = provider_id
        if klass:
            rec["class"] = klass
        if status:
            rec["status"] = status
        u[name] = rec
        _save("users.json", u)
    workspaces.create_student(name)
    return name


@app.get("/api/auth/options")
def api_auth_options():
    _, ready = oauth_conf()
    o = orgs.org()
    return jsonify(signup=settings()["allow_signup"], need_class=bool(orgs.classes()), org=o.get("name", ""),
                   logo=f"/org/logo.png?v={o.get('logo_v', 0)}" if o.get("logo") else "", **ready)


def _class_seats_used(cid):
    return sum(1 for v in users().values() if v.get("role") == "student" and v.get("class") == cid)


def _class_for_join(code):
    """(class, None) or (None, error) — a code is needed once the academy has classes."""
    if not code:
        if orgs.classes():
            return None, "Enter the class code your teacher gave you."
        return None, None
    c = orgs.by_code(code)
    err = orgs.join_problem(c, _class_seats_used(c["id"]) if c else 0)
    return (None, err) if err else (c, None)


_peeks = {}


@app.get("/api/class-info")
def api_class_info():
    """What a class code opens, shown before the student confirms (no login; a few tries per minute)."""
    ip = request.remote_addr or "?"
    now = time.time()
    _peeks[ip] = [t for t in _peeks.get(ip, []) if now - t < 60][-40:] + [now]
    if len(_peeks[ip]) > 30:
        return jsonify(error="Too many tries — wait a minute."), 429
    c, err = _class_for_join(request.args.get("code", ""))
    if not c:
        return jsonify(error=err or "Enter a class code."), 404
    t = users().get(c["teacher"], {})
    return jsonify(name=c["name"], org=orgs.org().get("name", ""), teacher=t.get("display", ""))


@app.get("/join/<code>")
def page_join(code):
    return redirect("/?join=" + re.sub(r"[^A-Za-z0-9-]", "", code)[:20])


@app.post("/api/signup")
def api_signup():
    d = request.get_json(force=True)
    kind = "teacher" if d.get("kind") == "teacher" else "student"
    invite = re.sub(r"[^A-Z0-9]", "", (d.get("invite_code") or "").upper())
    if not settings()["allow_signup"] and not (kind == "teacher" and invite):
        return jsonify(error="Account creation is closed. Ask your teacher for an account." if kind == "student" else
                       "Account creation is closed: teachers need the invitation code from the administrator."), 403
    display = _text(d.get("display"), 60)
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if len(display) < 2:
        return jsonify(error="Please enter your full name."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="Please enter a valid e-mail address."), 400
    if len(pw) < 8:
        return jsonify(error="The password needs at least 8 characters."), 400
    if any((v.get("email") or "") == email for v in users().values()):
        return jsonify(error="An account with this e-mail already exists — sign in instead."), 409
    ip = request.remote_addr or "?"
    now = time.time()
    _signups[ip] = [t for t in _signups.get(ip, []) if now - t < 3600]
    if len(_signups[ip]) >= SIGNUP_PER_HOUR:
        return jsonify(error="Too many new accounts from this device. Try again later."), 429
    klass, status = None, None
    if kind == "student":
        c, err = _class_for_join(d.get("class_code", ""))
        if err:
            return jsonify(error=err), 400
        klass = c["id"] if c else None
    else:
        status = _teacher_code_status(invite)
        if status == "wrong":
            return jsonify(error="This invitation code is not right — check it with your administrator, or leave "
                                 "it empty to ask for approval instead."), 400
        if status == "slow":
            return jsonify(error="Too many wrong invitation codes — wait 15 minutes."), 429
    try:
        name = new_student(display, email=email, password=pw, klass=klass, role=kind, status=status)
    except ValueError as e:
        return jsonify(error=str(e)), 409
    _signups[ip].append(now)
    session.clear(); session["user"] = name; session.permanent = True
    return jsonify(ok=True, role=kind, status=status or "active", name=name)


def _teacher_code_status(code):
    """'' (no code: waits for approval), 'active', 'wrong' or 'slow' (too many wrong codes from here)."""
    if not code:
        return "pending"
    k = "invite:" + (request.remote_addr or "?")
    if _too_many_fails(k):
        return "slow"
    good = re.sub(r"[^A-Z0-9]", "", orgs.org().get("teacher_code", ""))
    if good and secrets.compare_digest(code, good):
        return "active"
    _fails[k].append(time.time())
    return "wrong"


@app.post("/api/pending/code")
@login_required()
def api_pending_code():
    """A teacher waiting for approval types the invitation code: active at once."""
    if request.urec.get("status") != "pending":
        return jsonify(ok=True)
    st = _teacher_code_status(re.sub(r"[^A-Z0-9]", "", (request.get_json(force=True).get("code") or "").upper()))
    if st != "active":
        return jsonify(error={"slow": "Too many wrong codes — wait 15 minutes.",
                              "pending": "Type the invitation code."}.get(st, "This code is not right — check it "
                                                                                "with your administrator.")), 400
    with _lock:
        u = users()
        u[request.user]["status"] = "active"
        _save("users.json", u)
    return jsonify(ok=True)


@app.get("/api/prefs")
@login_required()
def api_prefs_get():
    return jsonify(users()[request.user].get("prefs", {}))


@app.post("/api/prefs")
@login_required()
def api_prefs_set():
    d = request.get_json(force=True)
    with _lock:
        u = users()
        prefs = u[request.user].setdefault("prefs", {})
        for k, v in d.items():
            if re.fullmatch(r"[a-z0-9_-]{1,32}", k) and isinstance(v, (bool, int, str)) and len(str(v)) < 200:
                prefs[k] = v
        _save("users.json", u)
    return jsonify(ok=True)


OAUTH = {
    "google": {"auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token",
               "user": "https://openidconnect.googleapis.com/v1/userinfo", "scope": "openid email profile"},
    "github": {"auth": "https://github.com/login/oauth/authorize", "token": "https://github.com/login/oauth/access_token",
               "user": "https://api.github.com/user", "scope": "read:user user:email"},
}


@app.get("/auth/<provider>")
def auth_start(provider):
    conf, ready = oauth_conf()
    if provider not in OAUTH or not ready.get(provider):
        return redirect("/?auth_error=" + provider + "_not_configured")
    from urllib.parse import urlencode
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    session["join_code"] = request.args.get("code", "")[:20]
    q = {"client_id": conf[provider]["client_id"], "redirect_uri": conf["base_url"].rstrip("/") + f"/auth/{provider}/callback",
         "response_type": "code", "scope": OAUTH[provider]["scope"], "state": state}
    if provider == "google":
        q["prompt"] = "select_account"
    return redirect(OAUTH[provider]["auth"] + "?" + urlencode(q))


@app.get("/auth/<provider>/callback")
def auth_callback(provider):
    import requests as rq
    conf, ready = oauth_conf()
    if provider not in OAUTH or not ready.get(provider):
        return redirect("/?auth_error=" + provider + "_not_configured")
    if not request.args.get("code") or request.args.get("state") != session.pop("oauth_state", None):
        return redirect("/?auth_error=cancelled")
    redirect_uri = conf["base_url"].rstrip("/") + f"/auth/{provider}/callback"
    data = {"client_id": conf[provider]["client_id"], "client_secret": conf[provider]["client_secret"],
            "code": request.args["code"], "redirect_uri": redirect_uri, "grant_type": "authorization_code"}
    try:
        tok = rq.post(OAUTH[provider]["token"], data=data, headers={"Accept": "application/json"}, timeout=15).json()
        auth = {"Authorization": "Bearer " + tok["access_token"], "Accept": "application/json"}
        info = rq.get(OAUTH[provider]["user"], headers=auth, timeout=15).json()
        # only an address the provider has verified may join an existing account
        if provider == "google":
            email = (info.get("email") or "").lower() if info.get("email_verified") else ""
        else:
            mails = rq.get("https://api.github.com/user/emails", headers=auth, timeout=15).json()
            email = next((m["email"].lower() for m in mails if m.get("primary") and m.get("verified")), "")
            info["name"] = info.get("name") or info.get("login")
    except Exception:
        return redirect("/?auth_error=provider_failed")
    pid = str(info.get("sub") or info.get("id") or "")
    u = users()
    name = next((k for k, v in u.items() if (email and (v.get("email") or "") == email)
                 or (v.get("provider") == provider and v.get("provider_id") == pid)), None)
    if not name:
        if not settings()["allow_signup"]:
            return redirect("/?auth_error=signup_closed")
        c, err = _class_for_join(session.pop("join_code", ""))
        if err:
            return redirect("/?auth_error=need_class_code")
        try:
            name = new_student(info.get("name") or email, email=email or None, provider=provider, provider_id=pid,
                               klass=c["id"] if c else None)
        except ValueError:
            return redirect("/?auth_error=full")
    session.clear(); session["user"] = name; session.permanent = True
    return redirect("/teacher" if is_staff(users()[name]) else "/")


@app.get("/api/admin/settings")
@login_required("admin")
def api_admin_settings():
    _, ready = oauth_conf()
    return jsonify(settings=settings(), oauth=ready)


@app.post("/api/admin/settings")
@login_required("admin")
def api_admin_settings_set():
    d = request.get_json(force=True)
    with _lock:
        s = settings()
        if "allow_signup" in d:
            s["allow_signup"] = bool(d["allow_signup"])
        _save("settings.json", s)
    return jsonify(ok=True, settings=s)


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@login_required()
def api_me():
    b = workspaces.base_info()
    c = orgs.get(request.urec.get("class") or "")
    o = orgs.org()
    return jsonify(name=request.user, role=request.urec["role"], status=request.urec.get("status", "active"),
                   staff=is_staff(request.urec), admin=is_admin(request.urec), org=o.get("name", ""),
                   navera=config.navera_allowed(request.user),
                   klass={"id": c["id"], "name": c["name"], "ranking": c.get("ranking", False)} if c else None,
                   display=request.urec.get("display", request.user),
                   email=request.urec.get("email"), prefs=request.urec.get("prefs", {}),
                   domain=config.domain_for(request.urec["index"]), base=b, host=_host_ip())


@app.post("/api/password")
@login_required()
def api_password():
    d = request.get_json(force=True)
    with _lock:
        u = users()
        if u[request.user].get("pw") and not check_password_hash(u[request.user]["pw"], d.get("old") or ""):
            return jsonify(error="The current password is wrong"), 400
        if len(d.get("new") or "") < 8:
            return jsonify(error="At least 8 characters"), 400
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
    name = request.user
    if is_staff(request.urec) and request.args.get("as"):
        if not can_see(request.user, request.urec, request.args["as"]):
            abort(403)
        name = request.args["as"]
    prog = _load("progress.json", {}).get(name or "", {})
    mods = _load_modules()
    out = []
    for lid in lesson_ids():
        m = lesson_meta(lid)
        m["progress"] = prog.get(lid, {})
        m["locked_until"], m["locked_after"] = lesson_lock(name, lid)
        out.append(m)
    return jsonify(lessons=out, modules=mods)


def lesson_leg(lid):
    return next((i for i, m in enumerate(_load_modules()) if lid in (m.get("lessons") or [])), -1)


def previous_lesson(lid):
    """The mission before `lid` by number ('' for the first one)."""
    ids = lesson_ids()
    i = ids.index(lid) if lid in ids else 0
    return ids[i - 1] if i > 0 else ""


def lesson_lock(name, lid):
    """(date, previous) — why a student cannot open mission `lid` yet: ("YYYY-MM-DD", "") while their
    class's leg is not open, ("", "NN") while mission NN (the one before) is not passed, ("", "") when
    it is open. Staff are never locked; a mission the student started or passed stays open (their own
    work); the first mission has no previous one; a teacher can open a mission for one student
    (users.json "open_missions", dashboard "Open mission…"): that lifts the order rule, not the leg date."""
    rec = users().get(name or "", {})
    if rec.get("role") != "student":
        return "", ""
    prog = _load("progress.json", {}).get(name, {})
    if prog.get(lid, {}).get("status"):
        return "", ""
    until = orgs.leg_open_from(orgs.get(rec.get("class") or ""), lesson_leg(lid))
    if until:
        return until, ""
    prev = previous_lesson(lid)
    if prev and prog.get(prev, {}).get("status") != "passed" and lid not in (rec.get("open_missions") or []):
        return "", lesson_meta(prev).get("number") or prev[:2]
    return "", ""


def lock_error(name, lid):
    """The sentence a locked mission answers with (None when it is open)."""
    until, after = lesson_lock(name, lid)
    if until:
        return f"This leg opens on {until}."
    if after:
        return f"Pass mission {after} first: missions open in order."
    return None


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
    if lock_error(name, lid):
        return jsonify(error=lock_error(name, lid), locked=True), 403
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
    if lock_error(request.user, lid):
        abort(403)
    return send_from_directory(os.path.join(config.COURSES, lid, "assets"), fn)


def run_in_sandbox(name, cmd, timeout=180, resources=(), heavy=False, lid=None):
    u = users()[name]
    argv = sandbox.bwrap_argv(name, workspaces.student_home(name), u["index"], cmd,
                              resources=resources, heavy=heavy, extra_ro=_course_mounts(lid), host_net=is_staff(u))
    try:
        r = subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                           start_new_session=True, preexec_fn=_default_signals)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") + f"\n⏱ The check took longer than {timeout} s and was stopped."


def _default_signals():
    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_DFL)


def _course_mounts(lid=None):
    """Public parts of ONE mission (helpers, starter files). check.py, meta.json and hidden/ are never
    mounted: a check runs sealed (server/sealed.py) and gets them in memory."""
    return sealed.mounts(lid) if lid else []


@app.post("/api/lesson/<lid>/check")
@login_required()
def api_check(lid):
    if lid not in lesson_ids():
        abort(404)
    name, _ = sandbox_user()
    if lock_error(name, lid):
        return jsonify(error=lock_error(name, lid), locked=True), 403
    workspaces.install_lesson(name, lid)               # files missing (never opened): put them in place, keep any work
    m = lesson_meta(lid)
    timeout = int(m.get("check_timeout_s", 180))
    res = [r for r in m.get("resources", []) if _holder(r) == name]
    # sealed: check.py and hidden data stay in the checker's memory, the score comes on a private
    # channel (an ACADEMY_RESULT line printed by the student's code is ignored and removed)
    u = users()[name]
    code, out, score = sealed.run_check(name, lid, u["index"], timeout=timeout, resources=res, heavy=bool(res),
                                        host_net=is_staff(u))
    passed = sealed.passed(code, score)
    if not is_staff(request.urec) or name == request.user:
        with _lock:
            p = _load("progress.json", {})
            rec = p.setdefault(name, {}).setdefault(lid, {})
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["last"] = time.strftime("%Y-%m-%d %H:%M")
            if score:
                rec["best"] = max(rec.get("best", 0), score.get("passed", 0))
                rec["total"] = score.get("total")
                got = [m for m in (score.get("milestones") or []) if isinstance(m, str) and len(m) < 40]
                if got:
                    rec["milestones"] = sorted(set(rec.get("milestones", [])) | set(got))
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
    if lock_error(name, lid):
        return jsonify(error=lock_error(name, lid), locked=True), 403
    workspaces.install_lesson(name, lid, overwrite=True)
    return jsonify(ok=True)


@app.post("/api/reset_navera")
@login_required()
def api_reset_navera():
    name, _ = sandbox_user()
    if not config.navera_allowed(name):
        return jsonify(error="NAVERA is not part of the course: your teacher can open it for you"), 403
    _kill_terminals(name)
    saved = workspaces.reset_navera(name)
    return jsonify(ok=True, backup=os.path.basename(saved) if saved else None)


# ---------------------------------------------------------------- files
def _safe(name, rel):
    home = os.path.realpath(workspaces.student_home(name))
    p = os.path.realpath(os.path.join(home, (rel or "").lstrip("/")))
    if p != home and not p.startswith(home + os.sep):
        abort(403)
    if _navera_path(home, p) and not config.navera_allowed(name):
        abort(403)                       # real NAVERA is not part of the course: staff, or given access
    return home, p


def _navera_path(home, p):
    """Is p ~/navera or inside it (the NAVERA copy of staff and students given access)?"""
    q = os.path.realpath(os.path.join(home, "navera"))
    return p == q or p.startswith(q + os.sep)


@app.get("/api/files")
@login_required()
def api_files():
    name, _ = sandbox_user()
    home, p = _safe(name, request.args.get("path", ""))
    if not os.path.isdir(p):
        abort(404)
    items = []
    navera = config.navera_allowed(name)
    for e in sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower())):
        if e.name in HIDDEN or (e.name.startswith(".") and e.name not in (".bashrc",)):
            continue
        if not navera and _navera_path(home, os.path.realpath(e.path)):
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
    seen = d.get("mtime")             # the version the editor loaded: refuse to overwrite a newer one silently
    if seen is not None and not d.get("force") and os.path.exists(p) and abs(os.path.getmtime(p) - float(seen)) > 0.001:
        return jsonify(error="This file was changed outside the editor (a terminal or a program).", conflict=True,
                       mtime=os.path.getmtime(p)), 409
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


@app.route("/web/<tool>/", defaults={"sub": ""}, methods=["GET", "POST"])
@app.route("/web/<tool>/<path:sub>", methods=["GET", "POST"])
@login_required()
def web_tool(tool, sub):
    """Simulator and operator view inside the page, under the academy's address (see webtools.py)."""
    if tool not in webtools.PORTS:
        abort(404)
    if not config.navera_allowed(request.user) and (config.RESOURCES["sim"].get("teacher_only") or _holder("sim") != request.user):
        return webtools.message("The full simulator is for the teacher",
                                "You fly <b>Sim Lite</b>: open the 🛩️ <b>Simulator</b> tab. It runs your own NAVERA code, "
                                "and no booking is needed.", 423, lite=True)
    return webtools.proxy(app, tool, sub, request)


# ---------------------------------------------------------------- Sim Lite (runs in the browser)
@app.get("/api/simlite/code")
@login_required()
def api_simlite_code():
    teacher = config.navera_allowed(request.user)          # the original NAVERA: teacher, or a student given access
    src = "original" if teacher and request.args.get("src") == "original" else "mine"
    try:
        return jsonify(simlite.code(request.user, src, allow_original=teacher))
    except FileNotFoundError as e:
        return jsonify(error=str(e)), 409


@app.get("/api/simlite/script")
@login_required()
def api_simlite_script():
    return jsonify(text=simlite.script(request.user))


@app.post("/api/simlite/script")
@login_required()
def api_simlite_script_save():
    try:
        simlite.save_script(request.user, str(request.get_json(force=True).get("text", "")))
    except ValueError as e:
        return jsonify(error=str(e), conflict=simlite.CONFLICT in str(e)), 409 if simlite.CONFLICT in str(e) else 413
    return jsonify(ok=True)


@app.get("/api/simlite/scenario")
@login_required()
def api_simlite_scenario():
    try:
        return jsonify(simlite.scenario(request.user, request.args.get("lesson", "")))
    except FileNotFoundError:
        lesson = request.args.get("lesson", "")
        expected = "/" not in lesson and os.path.exists(os.path.join(config.COURSES, lesson, "files", "my_scenario.json"))
        if not expected:
            return jsonify(none=True)                      # this mission has no scenario: nothing to show
        return jsonify(error="my_scenario.json is missing from your mission folder: open the 📝 Code tab, "
                             "or put it back from the mission's files", expected=True), 404
    except (ValueError, json.JSONDecodeError) as e:
        return jsonify(error=f"my_scenario.json: {e}"), 400


@app.post("/api/simlite/flight")
@login_required()
def api_simlite_flight():
    d = request.get_json(force=True)
    try:
        path = simlite.save_flight(request.user, str(d.get("lesson", "")), str(d.get("run", "")),
                                   str(d.get("csv", "")), str(d.get("events", "")))
    except (ValueError, OSError) as e:
        return jsonify(error=str(e)), 400
    return jsonify(ok=True, path=path)


@app.get("/api/simlite/map")
@login_required()
def api_simlite_map():
    path, native = simlite.map_file()
    return jsonify(available=bool(path), max_native_zoom=native, bounds=simlite.bounds())


@app.get("/api/simlite/tiles/<int:z>/<int:x>/<int:y>.jpg")
@login_required()
def api_simlite_tile(z, x, y):
    data = simlite.tile(z, x, y)
    if not data:
        return "", 204
    r = app.response_class(data, content_type="image/jpeg")
    r.headers["Cache-Control"] = "private, max-age=86400"
    return r


@app.get("/api/bookings")
@login_required()
def api_bookings():
    b = bookings()
    teacher = config.navera_allowed(request.user)          # the full simulator: staff, or a student given access
    return jsonify({k: {"title": v["title"], "holder": b.get(k, {}).get("user"),
                        "since": b.get(k, {}).get("since")} for k, v in config.RESOURCES.items()
                    if teacher or not v.get("teacher_only")})


@app.post("/api/book")
@login_required()
def api_book():
    d = request.get_json(force=True)
    res, action = d.get("resource"), d.get("action", "take")
    if res not in config.RESOURCES:
        abort(404)
    if config.RESOURCES[res].get("teacher_only") and not config.navera_allowed(request.user):
        return jsonify(error="Students fly Sim Lite (Simulator tab): no booking needed."), 403
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
            if cur and cur != name and not is_staff(request.urec):
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
    origin = request.headers.get("Origin")
    if origin and urllib.parse.urlsplit(origin).netloc != request.host:     # another site's page
        u = None
    if not u or u.get("status") == "pending":
        ws.close()
        return
    if is_staff(u) and request.args.get("as"):
        if not can_see(name, u, request.args["as"]):
            ws.close()
            return
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
                              interactive=True, host_net=is_staff(u) or ("sim" in res and config.navera_allowed(name)))
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
    cid = request.args.get("class")
    seen = visible_students(request.user, request.urec, None if cid in (None, "all") else cid)
    p = _load("progress.json", {})
    n = len(lesson_ids())
    out = []
    for name, rec in sorted(seen.items()):
        pr = p.get(name, {})
        last = max((v.get("last", "") for v in pr.values()), default="")
        c = certs.for_user(name)
        out.append({"name": name, "display": rec.get("display", name), "index": rec["index"], "class": rec.get("class") or "",
                    "last": last or rec.get("created", ""), "certificate": c["id"] if c and not c.get("revoked") else "",
                    "email": rec.get("email"), "navera": bool(rec.get("navera_access")),
                    "open_missions": rec.get("open_missions") or [], "provider": rec.get("provider", "email" if rec.get("email") else "teacher"),
                    "passed": sum(1 for v in pr.values() if v.get("status") == "passed"),
                    "started": sum(1 for v in pr.values() if v.get("status") == "started"),
                    "lessons": n, "progress": pr,
                    "terminals": sum(1 for t in TERMS.values() if t["user"] == name),
                    "backups": len(os.listdir(os.path.join(config.STUDENTS, name, "backups")))
                    if os.path.isdir(os.path.join(config.STUDENTS, name, "backups")) else 0})
    return jsonify(students=out, base=workspaces.base_info(), lessons=lesson_ids(),
                   missing_data=config.missing_data() if is_admin(request.urec) else [])


@app.post("/api/admin/students")
@login_required("teacher")
def api_admin_add():
    d = request.get_json(force=True)
    created = []
    cid = d.get("class") or None
    if cid and (not orgs.get(cid) or (not is_admin(request.urec) and orgs.get(cid)["teacher"] != request.user)):
        return jsonify(error="Choose one of your classes."), 400
    if not cid and not is_admin(request.urec):
        return jsonify(error="Choose the class for these students."), 400
    with _lock:
        u = users()
        used = {v["index"] for v in u.values()}
        skipped = []
        free = None
        if cid:
            c = orgs.get(cid)
            free = int(c.get("seats") or 0) - sum(1 for v in u.values() if v.get("class") == cid)
        for line in (d.get("names") or "").splitlines():
            parts = [x.strip() for x in line.split(",")]
            name = parts[0].lower()
            if not name:
                continue
            if not NAME_RE.match(name):
                return jsonify(error=f"'{name}': lower-case letters, digits, _ (2–24, starts with a letter)"), 400
            if name in u:
                skipped.append(name)
                continue
            if free is not None and len(created) >= free:
                return jsonify(error=f"{c['name']} has {max(0, free)} free seat(s): add seats in its Class options "
                                     "first (nobody was created)."), 409
            idx = next((i for i in range(1, len(config.STUDENT_DOMAINS)) if i not in used), None)
            if idx is None:
                return jsonify(error=f"at most {len(config.STUDENT_DOMAINS) - 1} students"), 400
            used.add(idx)
            pw = parts[2] if len(parts) > 2 and parts[2] else secrets.token_urlsafe(8)
            u[name] = {"role": "student", "pw": generate_password_hash(pw), "index": idx,
                       "display": _text(parts[1], 60) if len(parts) > 1 and parts[1] else name, "created": time.strftime("%Y-%m-%d %H:%M")}
            if cid:
                u[name]["class"] = cid
            created.append({"name": name, "password": pw})
        _save("users.json", u)
    for c in created:
        workspaces.create_student(c["name"])
    return jsonify(created=created, skipped=skipped)


@app.post("/api/admin/student/<name>")
@login_required("teacher")
def api_admin_student(name):
    d = request.get_json(force=True)
    action = d.get("action")
    if not can_see(request.user, request.urec, name) or name == request.user:
        abort(404)
    with _lock:
        u = users()
        if name not in u or u[name]["role"] != "student":
            abort(404)
        if action == "move":                                   # to another class (one of mine, or any for the admin)
            c = orgs.get(d.get("class") or "")
            if d.get("class") and (not c or (not is_admin(request.urec) and c["teacher"] != request.user)):
                return jsonify(error="Choose one of your classes."), 400
            if not c and not is_admin(request.urec):
                return jsonify(error="Choose one of your classes."), 400
            if c:
                taken = sum(1 for k, v in u.items() if v.get("class") == c["id"] and k != name)
                if taken >= int(c.get("seats") or 0):
                    return jsonify(error=f"{c['name']} is full ({taken} of {c.get('seats')} seats) — add seats in "
                                         "its Class options first."), 409
                u[name]["class"] = c["id"]
            else:
                u[name].pop("class", None)
            _save("users.json", u)
            return jsonify(ok=True)
        if action in ("navera_on", "navera_off"):          # real NAVERA is not part of the course: the teacher opens it
            if action == "navera_on":
                u[name]["navera_access"] = True
            else:
                u[name].pop("navera_access", None)
            _save("users.json", u)
            _kill_terminals(name)
            workspaces.create_student(name)                # clones ~/navera, or backs it up and removes it
            return jsonify(ok=True)
        if action in ("open_mission", "close_mission"):    # missions open in order; the teacher can open one early
            lid = d.get("lesson") or ""
            if lid not in lesson_ids():
                return jsonify(error="Choose a mission."), 400
            opened = [x for x in (u[name].get("open_missions") or []) if x in lesson_ids() and x != lid]
            if action == "open_mission":
                opened.append(lid)
            if opened:
                u[name]["open_missions"] = sorted(opened)
            else:
                u[name].pop("open_missions", None)
            _save("users.json", u)
            until, _ = lesson_lock(name, lid)
            return jsonify(ok=True, open_missions=opened, leg_opens=until)
        if action == "password":
            pw = secrets.token_urlsafe(8)
            u[name]["pw"] = generate_password_hash(pw)
            _save("users.json", u)
            _fails.pop("user:" + name, None)              # the account's protection ends with a new password
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
        if not config.navera_allowed(name):
            return jsonify(error="this student has no NAVERA access"), 403
        _kill_terminals(name)
        return jsonify(ok=True, backup=os.path.basename(workspaces.reset_navera(name) or ""))
    if action == "kill":
        _kill_terminals(name)
        return jsonify(ok=True)
    abort(400)


@app.get("/api/admin/commits")
@login_required("admin")
def api_admin_commits():
    r = subprocess.run(["git", "-C", config.REAL_REPO, "log", "--all", "-25",
                        "--format=%h|%ad|%D|%s", "--date=short"], text=True, capture_output=True)
    out = []
    for line in r.stdout.splitlines():
        h, date, refs, subj = line.split("|", 3)
        out.append({"hash": h, "date": date, "refs": refs, "subject": subj})
    return jsonify(commits=out, base=workspaces.base_info())


BASE_JOB = {"running": False, "log": []}


@app.get("/api/admin/fullsim")
@login_required("teacher")
def api_admin_fullsim():
    """Is the full simulator running (sim page :8190, operator view :8181), and who holds it."""
    busy = _ports_busy([webtools.PORTS["sim"], webtools.PORTS["op"]])
    return jsonify(sim=webtools.PORTS["sim"] in busy, op=webtools.PORTS["op"] in busy, holder=_holder("sim"))


@app.post("/api/admin/base")
@login_required("admin")
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
@login_required("admin")
def api_admin_base_state():
    return jsonify(running=BASE_JOB["running"], log=BASE_JOB["log"][-30:], error=BASE_JOB.get("error"),
                   base=workspaces.base_info())


# ---------------------------------------------------------------- pages
# ---------------------------------------------------------------- organisation, classes, teachers (orgs.py)
@app.get("/api/setup")
def api_setup_state():
    return jsonify(needed=not orgs.configured() and not any(v.get("role") == "student" or not v.get("support")
                                                            for v in users().values()))


@app.post("/api/setup")
def api_setup():
    """First start of a client's Jetson: the organisation and its first administrator (needs the sticker's code)."""
    if orgs.configured() or any(v.get("role") == "student" or not v.get("support") for v in users().values()):
        return jsonify(error="This academy is already set up — sign in."), 409
    d = request.get_json(force=True)
    ip = "setup:" + (request.remote_addr or "?")
    if _too_many_fails(ip):
        return jsonify(error="Too many wrong codes. Wait 15 minutes."), 429
    code = re.sub(r"[^A-Z0-9]", "", (d.get("setup_code") or "").upper())
    if not code:
        return jsonify(error="Enter the setup code — it is on the sticker under the NAVERA box."), 400
    if not secrets.compare_digest(code, re.sub(r"[^A-Z0-9]", "", orgs.setup_code())):
        _fails[ip].append(time.time())
        return jsonify(error="This setup code is not right — it is on the sticker under the NAVERA box."), 403
    org = _text(d.get("org"), 80)
    display = _text(d.get("display"), 60)
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if len(org) < 2:
        return jsonify(error="Enter the name of your organisation."), 400
    if len(display) < 2:
        return jsonify(error="Enter your full name."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="Enter a valid e-mail address."), 400
    if len(pw) < 10 or pw.isdigit() or len(set(pw)) < 5:
        return jsonify(error="The administrator password needs at least 10 characters, not only digits "
                             "(it controls the whole academy)."), 400
    name = new_student(display, email=email, password=pw, role="admin")
    orgs.save_org(name=org)
    session.clear(); session["user"] = name; session.permanent = True
    return jsonify(ok=True, name=name)


@app.get("/org/logo.png")
def org_logo():
    if not os.path.exists(orgs.LOGO):
        abort(404)
    return send_file(orgs.LOGO, mimetype="image/png", max_age=300)


@app.get("/api/admin/org")
@login_required("admin")
def api_admin_org():
    o = orgs.org()
    return jsonify(name=o.get("name", ""), teacher_code=o.get("teacher_code", ""), logo=bool(o.get("logo")),
                   logo_url=f"/org/logo.png?v={o.get('logo_v', 0)}" if o.get("logo") else "",
                   join_url=_public_url() + "/")


@app.post("/api/admin/org")
@login_required("admin")
def api_admin_org_set():
    d = request.get_json(force=True)
    if d.get("action") == "new_teacher_code":
        return jsonify(teacher_code=orgs.new_teacher_code())
    if d.get("action") == "remove_logo":
        if os.path.exists(orgs.LOGO):
            os.remove(orgs.LOGO)
        orgs.save_org(logo=False)
        return jsonify(ok=True)
    name = _text(d.get("name"), 80)
    if len(name) < 2:
        return jsonify(error="Enter the name of your organisation."), 400
    orgs.save_org(name=name)
    return jsonify(ok=True)


@app.post("/api/admin/org/logo")
@login_required("admin")
def api_admin_org_logo():
    data = request.get_data()
    if not data or len(data) > 3_000_000:
        return jsonify(error="Choose a PNG or JPEG picture under 3 MB."), 400
    try:
        orgs.save_logo(data)
    except Exception as e:
        return jsonify(error=str(e) if isinstance(e, ValueError) else "This file is not a PNG or JPEG picture."), 400
    return jsonify(ok=True)


def _class_view(c):
    t = users().get(c["teacher"], {})
    return dict(c, teacher_name=t.get("display", c["teacher"]), students=_class_seats_used(c["id"]),
                join_url=f"{_public_url()}/join/{c['code']}")


@app.get("/api/classes")
@login_required("teacher")
def api_classes():
    cs = orgs.classes().values() if is_admin(request.urec) else orgs.owned_by(request.user)
    teachers = [{"name": k, "display": v.get("display", k)} for k, v in users().items()
                if is_staff(v)] if is_admin(request.urec) else []
    mods = [{"index": i, "leg": m.get("leg", ""), "title": m.get("title", "")} for i, m in enumerate(_load_modules())]
    unassigned = sum(1 for v in users().values() if v.get("role") == "student" and not orgs.get(v.get("class") or ""))
    return jsonify(classes=sorted((_class_view(c) for c in cs), key=lambda c: c["created"]), teachers=teachers,
                   legs=mods, unassigned=unassigned if is_admin(request.urec) else 0)


def _class_fields(d):
    f = {}
    if "name" in d:
        f["name"] = _text(d["name"], 80)
        if len(f["name"]) < 2:
            raise ValueError("Give the class a name.")
    for k in ("starts", "ends"):
        if k in d:
            v = str(d[k] or "")
            if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                raise ValueError("Dates look like 2026-10-13.")
            f[k] = v
    if "seats" in d:
        f["seats"] = max(1, min(98, int(d["seats"] or 30)))
    for k in ("join", "ranking", "cert_class"):
        if k in d:
            f[k] = bool(d[k])
    if "legs" in d:
        legs = {}
        for k, v in (d["legs"] or {}).items():
            if re.fullmatch(r"\d{1,2}", str(k)) and (not v or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v))):
                if v:
                    legs[str(k)] = str(v)
        f["legs"] = legs
    return f


@app.post("/api/classes")
@login_required("teacher")
def api_class_create():
    d = request.get_json(force=True)
    try:
        f = _class_fields(dict(d, name=d.get("name", "")))
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400
    owner = request.user
    if is_admin(request.urec) and d.get("teacher") and is_staff(users().get(d["teacher"])):
        owner = d["teacher"]
    if f.get("starts") and f.get("ends") and f["ends"] < f["starts"]:
        return jsonify(error="The class cannot end before it starts."), 400
    c = orgs.create(owner, f["name"], f.get("starts"), f.get("ends"), f.get("seats", 30))
    rest = {k: v for k, v in f.items() if k not in ("name", "starts", "ends", "seats")}
    if rest:
        c = orgs.update(c["id"], **rest)
    return jsonify(_class_view(c))


def _my_class(cid):
    c = orgs.get(cid)
    if not c or not (is_admin(request.urec) or c["teacher"] == request.user):
        abort(404)
    return c


@app.post("/api/classes/<cid>")
@login_required("teacher")
def api_class_update(cid):
    _my_class(cid)
    d = request.get_json(force=True)
    if d.get("action") == "delete":
        with _lock:                              # its students stay, without a class (the admin sees them)
            u = users()
            for v in u.values():
                if v.get("class") == cid:
                    v.pop("class", None)
            _save("users.json", u)
        orgs.delete(cid)
        return jsonify(ok=True)
    try:
        f = _class_fields(d)
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400
    if is_admin(request.urec) and d.get("teacher") and is_staff(users().get(d["teacher"])):
        f["teacher"] = d["teacher"]
    cur = dict(orgs.get(cid), **f)
    if cur.get("starts") and cur.get("ends") and cur["ends"] < cur["starts"]:
        return jsonify(error="The class cannot end before it starts."), 400
    if "seats" in f and f["seats"] < _class_seats_used(cid):
        return jsonify(error=f"{_class_seats_used(cid)} students are already in this class: seats cannot be "
                             "fewer (move or remove students first)."), 400
    c = orgs.update(cid, new_code=bool(d.get("new_code")), **f)
    return jsonify(_class_view(c))


def _cell(rec):
    """One mission in the Excel export: ✔ passed, best score while started, empty otherwise."""
    if rec.get("status") == "passed":
        return "✔"
    if rec.get("status") == "started":
        return f"{rec.get('best', 0)}/{rec.get('total', '?')}"
    return ""


@app.get("/api/classes/<cid>/export.xlsx")
@login_required("teacher")
def api_class_export(cid):
    c = _my_class(cid) if cid != "all" else None
    if cid == "all" and not is_admin(request.urec):
        abort(404)
    ids = lesson_ids()
    p = _load("progress.json", {})
    rows = [["Name", "E-mail", "Login", "Class", "Missions passed", "of", "XP", "Last activity", "Certificate"] +
            [f"M{lesson_meta(i).get('number', i[:2])}" for i in ids]]
    for name, rec in sorted(visible_students(request.user, request.urec, None if cid == "all" else cid).items(),
                            key=lambda kv: kv[1].get("display", kv[0]).lower()):
        pr = p.get(name, {})
        done = sum(1 for i in ids if pr.get(i, {}).get("status") == "passed")
        cert = certs.for_user(name)
        k = orgs.get(rec.get("class") or "")
        rows.append([rec.get("display", name), rec.get("email", ""), name, k["name"] if k else "", done, len(ids), done * 100,
                     max((v.get("last", "") for v in pr.values()), default=""),
                     cert["id"] if cert and not cert.get("revoked") else ""] +
                    [_cell(pr.get(i, {})) for i in ids])
    fn = re.sub(r"[^A-Za-z0-9_-]+", "_", c["name"] if c else "all_students").strip("_") or "class"
    return Response(orgs.xlsx(rows, (c["name"] if c else "Students")[:31]),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fn}.xlsx"'})


@app.get("/api/classes/<cid>/qr.svg")
@login_required("teacher")
def api_class_qr(cid):
    return Response(certs.qr_svg(_class_view(_my_class(cid))["join_url"]), mimetype="image/svg+xml")


@app.get("/class/<cid>/poster")
@login_required("teacher")
def page_class_poster(cid):
    c = _class_view(_my_class(cid))
    o = orgs.org()
    return render_template("poster.html", c=c, org=o.get("name", ""), qr=certs.qr_svg(c["join_url"]),
                           logo=f"/org/logo.png?v={o.get('logo_v', 0)}" if o.get("logo") else "")


@app.get("/api/class/ranking")
@login_required("student")
def api_class_ranking():
    c = orgs.get(request.urec.get("class") or "")
    if not c or not c.get("ranking"):
        return jsonify(ranking=None)
    p = _load("progress.json", {})
    rows = []
    for name, rec in users().items():
        if rec.get("role") == "student" and rec.get("class") == c["id"]:
            xp = 100 * sum(1 for v in p.get(name, {}).values() if v.get("status") == "passed")
            rows.append({"first": (rec.get("display") or name).split(" ")[0], "xp": xp, "me": name == request.user})
    rows.sort(key=lambda r: -r["xp"])
    return jsonify(ranking=rows[:50], klass=c["name"])


@app.get("/api/admin/teachers")
@login_required("admin")
def api_admin_teachers():
    out = []
    for name, rec in sorted(users().items()):
        if rec.get("role") in STAFF:
            out.append({"name": name, "display": rec.get("display", name), "email": rec.get("email", ""),
                        "role": rec["role"], "status": rec.get("status", "active"), "support": bool(rec.get("support")),
                        "classes": len(orgs.owned_by(name)), "created": rec.get("created", "")})
    return jsonify(teachers=out)


@app.post("/api/admin/teacher/<name>")
@login_required("admin")
def api_admin_teacher(name):
    action = request.get_json(force=True).get("action")
    with _lock:
        u = users()
        if name not in u or u[name].get("role") not in STAFF or name == request.user or u[name].get("support"):
            abort(404)
        if action == "approve":
            u[name]["status"] = "active"
        elif action == "make_admin":
            u[name].update(role="admin", status="active")
        elif action == "make_teacher":
            u[name]["role"] = "teacher"
        elif action == "password":
            pw = secrets.token_urlsafe(8)
            u[name]["pw"] = generate_password_hash(pw)
            _save("users.json", u)
            return jsonify(password=pw)
        elif action in ("delete", "reject"):
            for c in orgs.owned_by(name):        # their classes go to the admin who removes them
                orgs.update(c["id"], teacher=request.user)
            _kill_terminals(name)
            del u[name]
            _save("users.json", u)
            workspaces.delete_student(name)
            return jsonify(ok=True)
        else:
            abort(400)
        _save("users.json", u)
    return jsonify(ok=True)


# ---------------------------------------------------------------- end-of-course certificate (certs.py)
def _public_url():
    """The academy's public address, for the QR code and the links printed on certificates."""
    try:
        with open(os.path.join(config.STATE, "public_url.txt")) as f:
            u = f.read().strip().rstrip("/")
            if u:
                return u
    except OSError:
        pass
    return request.url_root.rstrip("/")


def _course_facts(name):
    """(all passed?, missions, hours of study, date the last mission was passed)."""
    prog = _load("progress.json", {}).get(name, {})
    ids = lesson_ids()
    hours, last = 0, ""
    for lid in ids:
        m = re.match(r"(\d+)\s*h\s*(\d+)?", lesson_meta(lid).get("duration", "") or "")
        if m:
            hours += int(m.group(1)) * 60 + int(m.group(2) or 0)
        last = max(last, prog.get(lid, {}).get("passed_at", ""))
    done = sum(1 for lid in ids if prog.get(lid, {}).get("status") == "passed")
    return done == len(ids) and len(ids) > 0, done, len(ids), round(hours / 60), last[:10]


@app.get("/api/certificate")
@login_required()
def api_certificate():
    ok, done, total, hours, last = _course_facts(request.user)
    c = certs.for_user(request.user)
    return jsonify(eligible=ok, passed=done, total=total, name=request.urec.get("display") or request.user,
                   certificate=None if not c else {"id": c["id"], "name": c["name"], "revoked": c.get("revoked", False),
                                                     "url": f"/certificate/{c['id']}", "verify": f"{_public_url()}/verify/{c['id']}"})


@app.post("/api/certificate")
@login_required("student")
def api_certificate_issue():
    ok, done, total, hours, last = _course_facts(request.user)
    if not ok:
        return jsonify(error=f"The certificate unlocks when all {total} missions are passed ({done} so far)."), 403
    name = _text(request.get_json(force=True).get("name", ""), 80)
    if not 3 <= len(name) <= 60 or not re.search(r"[^\W\d_]", name):
        return jsonify(error="Enter your full name as it should be printed (3 to 60 characters)."), 400
    extra = {}
    o = orgs.org()
    k = orgs.get(request.urec.get("class") or "")
    if o.get("name"):
        extra["organisation"] = o["name"]
    if k and k.get("cert_class", True):
        extra["class"] = k["name"]
    c = certs.issue(request.user, name, last or time.strftime("%Y-%m-%d"), total, hours, extra)
    return jsonify(id=c["id"], url=f"/certificate/{c['id']}")


def _cert_page(template, c, cid=""):
    import datetime
    status = certs.check(c)
    long = ""
    if c:
        try:
            d = datetime.date.fromisoformat(c["completed"])
            long = f"{d.day} {d.strftime('%B %Y')}"
        except ValueError:
            long = c["completed"]
    return render_template(template, c=c, cid=cid or (c or {}).get("id", ""), status=status, completed_long=long,
                           fp=certs.fingerprint(), legs=len(_load_modules()) or 7,
                           xp=(c or {}).get("missions", 0) * 100, rank="Migration Master",
                           verify_url=f"{_public_url()}/verify/{(c or {}).get('id', '')}",
                           verify_short=f"…/verify/{(c or {}).get('id', '')}",
                           qr=certs.qr_svg(f"{_public_url()}/verify/{c['id']}") if c else "",
                           mine=bool(c) and session.get("user") == c.get("user"),
                           org_logo=(f"/org/logo.png?v={orgs.org().get('logo_v', 0)}"
                                     if c and c.get("organisation") and orgs.org().get("logo") else ""))


@app.get("/certificate/<cid>")
def page_certificate(cid):
    """Public, like a paper certificate: whoever has the link (or the QR code) can see it."""
    c = certs.get(cid)
    if not c or certs.check(c) == "invalid":
        return _cert_page("verify.html", None, cid), 404
    return _cert_page("certificate.html", c)


@app.get("/verify")
@app.get("/verify/<cid>")
def page_verify(cid=""):
    cid = (cid or request.args.get("id", "")).strip().upper()[:40]
    if cid and not request.view_args.get("cid"):
        return redirect(f"/verify/{cid}")
    return _cert_page("verify.html", certs.get(cid), cid)


@app.get("/certificates/iris-key.pub")
def cert_public_key():
    return Response(certs.public_pem(), mimetype="text/plain")


@app.get("/api/admin/certificates")
@login_required("teacher")
def api_admin_certificates():
    mine = set(visible_students(request.user, request.urec))
    return jsonify(certificates=[{k: c.get(k, "") for k in ("id", "name", "user", "issued", "completed", "revoked", "class")}
                                 for c in certs.all_certs() if is_admin(request.urec) or c["user"] in mine],
                   key=certs.KEY_NAME, fingerprint=certs.fingerprint())


@app.post("/api/admin/certificates/<cid>")
@login_required("teacher")
def api_admin_certificate_set(cid):
    action = request.get_json(force=True).get("action")
    if action not in ("revoke", "restore"):
        abort(400)
    c0 = certs.get(cid)
    if not c0 or not (is_admin(request.urec) or c0["user"] in visible_students(request.user, request.urec)):
        return jsonify(error="unknown certificate"), 404
    c = certs.set_revoked(cid, action == "revoke")
    return jsonify(ok=True) if c else (jsonify(error="unknown certificate"), 404)


@app.get("/")
def page_index():
    u = users().get(session.get("user") or "")
    if not u:
        if not orgs.configured() and not any(v.get("role") == "student" or not v.get("support") for v in users().values()):
            return send_from_directory(app.static_folder, "setup.html")       # a brand-new Jetson: first start
        return send_from_directory(app.static_folder, "login.html")
    if u.get("status") == "pending":
        return send_from_directory(app.static_folder, "pending.html")
    return send_from_directory(app.static_folder, "app.html")


@app.get("/teacher")
def page_teacher():
    u = users().get(session.get("user") or "")
    if not is_staff(u):
        return redirect("/")
    return send_from_directory(app.static_folder, "teacher.html")


@app.before_request
def same_site_only():
    """A page on another site cannot make a signed-in browser change anything here (CSRF): browsers
    always send Origin on a cross-site POST; it must name this academy."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("Origin")
        if origin and origin != "null" and urllib.parse.urlsplit(origin).netloc != request.host:
            return jsonify(error="Request from another site refused."), 403
        if origin == "null":
            return jsonify(error="Request from another site refused."), 403


@app.after_request
def no_cache(r):
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    elif request.path == "/" or request.path == "/teacher" or request.path.endswith((".html", ".js", ".css")):
        # the dashboard changes often: browsers must re-check (they still reuse an unchanged file)
        r.headers["Cache-Control"] = "no-cache"
    return r


def _netns_reaper():
    """Every minute: stop the private network of a student nobody used for netns.IDLE seconds
    (no terminal, no check): the next sandbox of that student starts a new one."""
    while True:
        try:
            netns.reap()
        except Exception as e:                 # noqa: BLE001 — never let the reaper die
            print("netns reaper:", e, flush=True)
        time.sleep(60)


if __name__ == "__main__":
    if not workspaces.base_info():
        raise SystemExit("no base yet: python3 -c 'import workspaces; workspaces.build_base(\"<commit>\")'")
    ensure_teacher()
    workspaces.create_student("teacher")
    threading.Thread(target=_netns_reaper, daemon=True).start()
    if not orgs.configured():
        orgs.setup_code()               # printed on the sticker; asked on the first-start page
    print(f"NAVERA Academy on http://{_host_ip()}:{config.PORT}")
    app.run(host="0.0.0.0", port=config.PORT, threaded=True)
