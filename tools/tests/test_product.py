"""The product build on the NAVERA box: local accounts only, fully offline pages, the flight gate, the installer.

    python3 -m pytest -q tools/tests/test_product.py

The app is imported in a child process with a throw-away ACADEMY_VAR (never the dev state/), so nothing
here touches a running academy.
"""
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.abspath(os.path.join(HERE, "..", ".."))
SERVER = os.path.join(ACADEMY, "server")
STATIC = os.path.join(SERVER, "static")
sys.path.insert(0, SERVER)


# ----------------------------------------------------------------------------------------- helpers
def run_app(tmp_path, code, url="http://127.0.0.1:9/none", gate="on"):
    """Run python code with the app imported (product mode, throw-away state); returns its stdout."""
    env = dict(os.environ, ACADEMY_PRODUCT="1", ACADEMY_VAR=str(tmp_path / "var"), ACADEMY_DATA=str(tmp_path / "data"),
               ACADEMY_NAVERA_STATE_URL=url, ACADEMY_FLIGHT_GATE=gate, PYTHONDONTWRITEBYTECODE="1")
    (tmp_path / "var" / "state").mkdir(parents=True, exist_ok=True)
    pre = f"import sys, json; sys.path.insert(0, {SERVER!r}); import app as A\n"
    r = subprocess.run([sys.executable, "-c", pre + code], cwd=SERVER, env=env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    return r.stdout


class _State(http.server.BaseHTTPRequestHandler):
    doc = {}

    def do_GET(self):
        body = json.dumps(type(self).doc).encode() if type(self).doc is not None else b"<html>not json"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def navera():
    """A fake NAVERA web bridge; set navera.doc to what /api/mission/state answers."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _State)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.url = f"http://127.0.0.1:{srv.server_address[1]}/api/mission/state"
    yield srv
    srv.shutdown()


# ----------------------------------------------------------------------------------------- 1. no OAuth
def test_no_oauth_routes(tmp_path):
    out = run_app(tmp_path, "print(json.dumps(sorted(r.rule for r in A.app.url_map.iter_rules())))")
    rules = json.loads(out)
    assert not [r for r in rules if r.startswith("/auth/") or "oauth" in r.lower()], rules
    assert "/api/login" in rules or any(r.startswith("/api/login") for r in rules)


def test_no_external_sign_in_left():
    pat = re.compile(r"oauth|accounts\.google|googleapis|facebook|github\.com/login|api\.github\.com|(?<!/api)/auth/", re.I)
    files = [os.path.join(SERVER, f) for f in os.listdir(SERVER) if f.endswith(".py")]
    files += [os.path.join(STATIC, f) for f in ("login.html", "teacher.html", "app.html", "app.js", "setup.html")]
    hits = [f"{f}:{i}" for f in files if os.path.exists(f)
            for i, line in enumerate(open(f, encoding="utf-8", errors="replace"), 1) if pat.search(line)]
    assert not hits, hits
    assert not os.path.exists(os.path.join(ACADEMY, "tools", "set_oauth.py"))


def test_auth_options_has_no_providers(tmp_path):
    out = run_app(tmp_path, "c = A.app.test_client(); print(json.dumps(c.get('/api/auth/options').get_json()))")
    d = json.loads(out)
    assert not ({"google", "github", "facebook"} & set(d)), d
    assert d["signup"] is False                 # on the box the teacher creates the accounts


# ----------------------------------------------------------------------------------------- 2. offline pages
OK_URL = re.compile(r"https?://(www\.)?w3\.org/")
REQUEST = re.compile(r"""src\s*=\s*["']https?://|<link[^>]+href\s*=\s*["']https?://|url\(\s*["']?https?://|@import\s+["']https?://|"""
                     r"""fetch\(\s*["'`]https?://|importScripts\(\s*["']https?://|new\s+WebSocket\(\s*["']wss?://|"""
                     r"""XMLHttpRequest[^;]*open\([^)]*https?://""")


def _served_files():
    for top in (STATIC, os.path.join(SERVER, "templates")):
        for d, _, fs in os.walk(top):
            for f in fs:
                if f.endswith((".html", ".js", ".css", ".svg", ".json", ".mjs")):
                    yield os.path.join(d, f)


def test_no_external_urls_in_served_pages():
    bad = []
    for p in _served_files():
        text = open(p, encoding="utf-8", errors="replace").read()
        vendor = os.sep + "vendor" + os.sep in p
        if vendor:                     # third-party code: links in comments/licences are fine, requests are not
            bad += [f"{p}: {m.group(0)}" for m in REQUEST.finditer(text)]
        else:
            bad += [f"{p}: {m.group(0)}" for m in re.finditer(r"https?://[^\s\"'<>)]+", text)
                    if not OK_URL.match(m.group(0))]
    assert not bad, "\n".join(bad[:40])


def test_lessons_load_no_outside_images():
    bad = []
    for d, _, fs in os.walk(os.path.join(ACADEMY, "courses")):
        for f in fs:
            if f.endswith(".md"):
                t = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
                bad += [f"{f}: {m}" for m in re.findall(r"!\[[^\]]*\]\((https?://[^)]+)\)|<img[^>]+src=[\"'](https?://[^\"']+)", t)]
    assert not bad, bad


# ----------------------------------------------------------------------------------------- 3. flight gate
def test_decide_rules():
    import flightgate as G
    assert G.decide(None)                                        # unreachable → refuse
    assert G.decide({"settings": {}})                            # NAVERA 0.8.1: no flight field → refuse
    assert G.decide({"in_flight_refusal": None}) is None
    assert G.decide({"in_flight_refusal": "the vehicle is armed: disarm it"}) == "NAVERA says: the vehicle is armed: disarm it"
    serial = ("land and disarm first; armed state unknown (no MAVLink vehicle link) and NAVERA is the flight "
              "controller's GPS (serial output): a restart would cut it")
    assert G.decide({"in_flight_refusal": serial}) == "NAVERA says: " + serial
    assert G.decide({"in_flight_refusal": True})
    assert G.decide({"in_flight": True}) and G.decide({"in_flight": False}) is None
    assert G.decide({"armed": True, "moving_mps": 0})
    assert G.decide({"armed": False, "moving_mps": 5.0})
    assert G.decide({"armed": False, "moving_mps": 0.2, "nav_state": 3})
    assert G.decide({"armed": False, "moving_mps": 0.2}) is None
    assert G.decide({"armed": False})                            # speed unknown → unsure → refuse
    assert G.decide([1, 2])                                      # not an object → refuse


def _simlite_status(tmp_path, url):
    code = """
from werkzeug.security import generate_password_hash
A._save('users.json', {'s1': {'role': 'student', 'index': 3, 'pw': generate_password_hash('pw123456'), 'display': 'S'}})
c = A.app.test_client()
with c.session_transaction() as s: s['user'] = 's1'
r = c.get('/api/simlite/code'); g = c.get('/api/flight_gate').get_json()
print(json.dumps({'code': r.status_code, 'body': r.get_json(), 'gate': g}))
"""
    return json.loads(run_app(tmp_path, code, url=url).strip().splitlines()[-1])


def test_simlite_refused_when_navera_unreachable(tmp_path):
    r = _simlite_status(tmp_path, "http://127.0.0.1:9/api/mission/state")
    assert r["code"] == 423 and r["body"]["flight_lock"] and not r["gate"]["allowed"]
    assert "Refused for flight safety" in r["body"]["error"]


def test_simlite_refused_when_navera_says_in_flight(tmp_path, navera):
    _State.doc = {"settings": {}, "in_flight_refusal": "the vehicle is armed: disarm it before changing NAVERA"}
    r = _simlite_status(tmp_path, navera.url)
    assert r["code"] == 423 and "armed" in r["body"]["error"]


def test_simlite_refused_when_navera_answers_garbage(tmp_path, navera):
    _State.doc = None
    assert _simlite_status(tmp_path, navera.url)["code"] == 423


def test_simlite_allowed_when_navera_on_ground(tmp_path, navera):
    _State.doc = {"settings": {}, "in_flight_refusal": None}
    r = _simlite_status(tmp_path, navera.url)
    assert r["code"] != 423 and r["gate"]["allowed"], r


def test_gpu_lock_file_and_academy_gpu(tmp_path):
    import flightgate as G
    import config
    old = config.GPU_SLOT_DIR
    config.GPU_SLOT_DIR = str(tmp_path / "slots")
    try:
        G.apply("NAVERA is flying (test)", stop=False)
        assert open(os.path.join(config.GPU_SLOT_DIR, "FLIGHT_LOCK")).read().startswith("NAVERA is flying")
        env = dict(os.environ, ACADEMY_GPU_SLOTS=f"{config.GPU_SLOT_DIR}:1")
        lib = os.path.join(ACADEMY, "courses", "_lib")
        prog = ("import sys; sys.path.insert(0, %r); import academy_gpu as g\n"
                "try:\n    with g.gpu_slot(): print('GOT')\nexcept g.FlightLock as e: print('REFUSED', e)\n"
                "try:\n    with g.torch_device() as d: print('DEV', d)\nexcept g.FlightLock as e: print('REFUSED2')\n") % lib
        out = subprocess.run([sys.executable, "-c", prog], env=env, capture_output=True, text=True, timeout=120).stdout
        assert "REFUSED" in out and "REFUSED2" in out and "GOT" not in out, out
        G.apply(None, stop=False)
        assert not os.path.exists(os.path.join(config.GPU_SLOT_DIR, "FLIGHT_LOCK"))
        out = subprocess.run([sys.executable, "-c", prog.split("try:\n    with g.torch")[0]], env=env,
                             capture_output=True, text=True, timeout=60).stdout
        assert "GOT" in out, out
    finally:
        config.GPU_SLOT_DIR = old


def test_mission_copies_of_academy_gpu_are_current():
    lib = open(os.path.join(ACADEMY, "courses", "_lib", "academy_gpu.py")).read()
    for d in os.listdir(os.path.join(ACADEMY, "courses")):
        p = os.path.join(ACADEMY, "courses", d, "files", "academy_gpu.py")
        if os.path.exists(p):
            assert open(p).read() == lib, p


def test_sandbox_gets_no_gpu_when_refused(tmp_path, monkeypatch):
    import flightgate as G
    import sandbox
    monkeypatch.setattr(G, "refusal", lambda max_age=2.0: "NAVERA is flying (test)")
    monkeypatch.setattr(sandbox.config, "GPU_SLOT_DIR", str(tmp_path / "slots"))
    monkeypatch.setattr(sandbox.config, "STATE", str(tmp_path / "state"))
    os.makedirs(tmp_path / "state", exist_ok=True)
    argv = sandbox.bwrap_argv("_gate_test", str(tmp_path), 0, ["true"])
    assert not [a for a in argv if a.startswith("/dev/nv") or a == "/dev/dri"], argv


# ----------------------------------------------------------------------------------------- 4. installer
def _fake_release(tmp_path):
    src = tmp_path / "rel" / "navera-academy-1.0"
    (src / "server").mkdir(parents=True)
    for f in ("app.py", "manage.py", "config.py"):
        shutil.copy(os.path.join(SERVER, f), src / "server" / f)
    shutil.copytree(os.path.join(ACADEMY, "deploy"), src / "deploy")
    (src / "VERSION").write_text("1.0 test\n")
    tb = tmp_path / "navera-academy-1.0.tar.gz"
    with tarfile.open(tb, "w:gz") as t:
        t.add(src, arcname="navera-academy-1.0")
    digest = subprocess.run(["sha256sum", str(tb)], capture_output=True, text=True).stdout.split()[0]
    (tmp_path / "navera-academy-1.0.tar.gz.sha256").write_text(f"{digest}  navera-academy-1.0.tar.gz\n")
    return tb


def _install(tmp_path, root, tb, *extra):
    data = tmp_path / "data_src"
    (data / "models").mkdir(parents=True, exist_ok=True)
    (data / "osm_sousse.mbtiles").write_bytes(b"x")
    py = tmp_path / "py_src"
    site = py / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    import markupsafe
    import werkzeug
    for m in (werkzeug, markupsafe):            # what manage.py needs (a link: the test copies no 2.5 GB)
        if not (site / m.__name__).exists():
            os.symlink(os.path.dirname(m.__file__), site / m.__name__)
    return subprocess.run(["bash", os.path.join(ACADEMY, "deploy", "install_academy.sh"), "--root", str(root),
                           "--tarball", str(tb), "--data-from", str(data), "--pyuser-from", str(py), *extra],
                          capture_output=True, text=True, timeout=300)


def test_installer_staged(tmp_path):
    tb = _fake_release(tmp_path)
    root = tmp_path / "root"
    (root / "etc" / "navera").mkdir(parents=True)
    (root / "etc" / "navera" / "navera.env").write_text("NAVERA_PRODUCT_MODE=1\nNAVERA_FW_ALLOW_TCP=5600\n")
    r = _install(tmp_path, root, tb)
    assert r.returncode == 0, r.stdout + r.stderr
    unit = (root / "etc/systemd/system/navera-academy.service").read_text()
    for k in ("User=academy", "MemoryMax=1536M", "CPUWeight=10", "IOWeight=10", "Nice=10",
              "WorkingDirectory=/opt/navera-academy/server", "EnvironmentFile=/etc/navera-academy/academy.env"):
        assert k in unit, k
    assert "@UID@" not in unit
    assert "/home" not in unit
    env = (root / "etc/navera-academy/academy.env").read_text()
    assert "ACADEMY_PRODUCT=1" in env and "ACADEMY_VAR=/var/lib/navera-academy" in env
    assert "NAVERA_FW_ALLOW_TCP=5600,8300" in (root / "etc/navera/navera.env").read_text()
    assert (root / "opt/navera-academy/server/app.py").exists()
    assert (root / "var/lib/navera-academy/data/osm_sousse.mbtiles").exists()
    # the teacher password: printed once, stored only as a hash, never in clear text on disk
    m = re.search(r"Password:\s+(\S+)", r.stdout)
    assert m and len(m.group(1)) >= 12
    users = json.loads((root / "var/lib/navera-academy/state/users.json").read_text())
    assert users["teacher"]["role"] == "admin" and users["teacher"]["pw"].startswith(("scrypt:", "pbkdf2:"))
    from werkzeug.security import check_password_hash
    assert check_password_hash(users["teacher"]["pw"], m.group(1))
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            if os.path.isfile(p) and os.path.getsize(p) < 5_000_000:
                assert m.group(1).encode() not in open(p, "rb").read(), p
    # run again: idempotent (8300 once, password kept)
    r2 = _install(tmp_path, root, tb)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (root / "etc/navera/navera.env").read_text().count("8300") == 1
    assert "Password:" not in r2.stdout
    assert check_password_hash(json.loads((root / "var/lib/navera-academy/state/users.json").read_text())
                               ["teacher"]["pw"], m.group(1))
    assert (root / "opt/navera-academy.old").is_dir()


def test_installer_refuses_bad_checksum(tmp_path):
    tb = _fake_release(tmp_path)
    (tmp_path / "navera-academy-1.0.tar.gz.sha256").write_text("0" * 64 + "  x\n")
    r = _install(tmp_path, tmp_path / "root", tb)
    assert r.returncode != 0 and "MISMATCH" in (r.stdout + r.stderr)


def test_installer_adds_firewall_line_when_absent(tmp_path):
    tb = _fake_release(tmp_path)
    root = tmp_path / "root"
    (root / "etc" / "navera").mkdir(parents=True)
    (root / "etc" / "navera" / "navera.env").write_text("NAVERA_PRODUCT_MODE=1\n")
    assert _install(tmp_path, root, tb).returncode == 0
    assert "NAVERA_FW_ALLOW_TCP=8300\n" in (root / "etc/navera/navera.env").read_text()


# ----------------------------------------------------------------------------------------- 5. simulation only
SANDBOX_PROBE = r"""
import sys, json, os, subprocess
sys.path.insert(0, %(server)r)
import config, sandbox, workspaces, netns
assert config.PRODUCT and not config.navera_allowed("teacher") and not config.RESOURCES
out = {}
for who, staff in (("_prod_probe", False), ("teacher", True)):
    if staff:
        users = {"teacher": {"role": "admin", "index": 0}}
        os.makedirs(config.STATE, exist_ok=True); json.dump(users, open(os.path.join(config.STATE, "users.json"), "w"))
    workspaces.create_student(who)
    argv = sandbox.bwrap_argv(who, workspaces.student_home(who), 7, ["true"], resources=("camera", "sensors", "sim"),
                              host_net=staff)
    out[who] = argv
probe = '''
import os, socket, glob, json
r = {"etc_navera": sorted(os.listdir("/etc/navera")) if os.path.isdir("/etc/navera") else None,
     "opt": sorted(os.listdir("/opt")) if os.path.isdir("/opt") else [],
     "var_lib": [e for e in os.listdir("/var/lib") if e.startswith("navera")],
     "data": sorted(os.listdir("/data")) if os.path.isdir("/data") else [],
     "home": sorted(os.listdir("/home")), "navera_ws": os.path.exists("/home/student/navera"),
     "devs": sorted(glob.glob("/dev/video*") + glob.glob("/dev/ttyTHS*") + glob.glob("/dev/i2c-*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))}
for port in (8181, 8182, 8300):
    s = socket.socket(); s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", port)); r[str(port)] = "open"
    except OSError:
        r[str(port)] = "closed"
    s.close()
print("PROBE " + json.dumps(r))
'''
argv = sandbox.bwrap_argv("_prod_probe", workspaces.student_home("_prod_probe"), 7, ["python3", "-c", probe])
p = subprocess.run(argv, capture_output=True, text=True, timeout=120)
netns.release("_prod_probe")
out["probe"] = next((json.loads(l[6:]) for l in p.stdout.splitlines() if l.startswith("PROBE ")), {"err": p.stderr[-800:]})
workspaces.delete_student("_prod_probe"); workspaces.delete_student("teacher")
print("RESULT " + json.dumps(out))
"""


def test_no_real_navera_in_a_product_sandbox(tmp_path):
    env = dict(os.environ, ACADEMY_PRODUCT="1", ACADEMY_VAR=str(tmp_path / "var"), ACADEMY_DATA=str(tmp_path / "data"),
               ACADEMY_NAVERA_STATE_URL="http://127.0.0.1:9/x", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-c", SANDBOX_PROBE % {"server": SERVER}], cwd=SERVER, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(next(l[7:] for l in r.stdout.splitlines() if l.startswith("RESULT ")))
    for who in ("_prod_probe", "teacher"):
        argv = out[who]
        # its own network (never the box's): netns join or --unshare-net
        assert "--unshare-net" in argv or "nsenter" in argv, (who, argv[:20])
        binds = [(argv[i], argv[i + 1], argv[i + 2]) for i in range(len(argv) - 2)
                 if argv[i] in ("--bind", "--ro-bind", "--dev-bind")]
        for kind, src, dst in binds:
            if src == "/dev/null":
                continue
            low_dst = dst.lower()
            assert not low_dst.startswith(("/etc/navera", "/opt/navera", "/var/lib/navera", "/data/navera",
                                           "/home/navera", "/usr/local/lib/navera")), (who, src, dst)
            assert not os.path.realpath(src).startswith(("/home/navera", "/data/navera", "/opt/navera-release",
                                                          os.path.expanduser("~/Navera"))), (who, src)
            assert not dst.startswith(("/dev/video", "/dev/ttyTHS", "/dev/i2c", "/dev/ttyUSB", "/dev/ttyACM", "/dev/v4l")), (who, dst)
            assert dst != config_s_navera(), (who, dst)
        assert not any("8181" in a or "8182" in a for a in argv), who
    p = out["probe"]
    assert "err" not in p, p
    assert not p["etc_navera"], p                         # /etc/navera masked (exists on this Jetson)
    assert not [e for e in p["opt"] if e.startswith("navera")], p
    assert not p["var_lib"] and not p["navera_ws"] and "navera" not in p["home"], p   # (dev: the pip user site shows its home)
    assert "navera_data" not in p["data"] and "ardupilot" not in p["data"], p
    assert not p["devs"], p
    assert p["8181"] == p["8182"] == p["8300"] == "closed", p


def config_s_navera():
    import config
    return config.S_NAVERA


def test_navera_access_switch_is_gone(tmp_path):
    code = """
from werkzeug.security import generate_password_hash
A._save('users.json', {'teacher': {'role': 'admin', 'index': 0, 'pw': 'x'}, 's1': {'role': 'student', 'index': 3, 'pw': 'x'}})
c = A.app.test_client()
with c.session_transaction() as s: s['user'] = 'teacher'
r = [c.post('/api/admin/student/s1', json={'action': a}, headers={'Origin': 'http://localhost'}).status_code
     for a in ('navera_on', 'navera_off', 'reset_navera')]
r += [c.get('/api/admin/commits').status_code, c.post('/api/admin/base', json={'commit': 'abcdef1'}).status_code,
      c.post('/api/reset_navera', json={}).status_code, c.get('/web/sim/').status_code]
import json as J; u = J.load(open(A.config.STATE + '/users.json'))
print(json.dumps({'codes': r, 'navera_access': 'navera_access' in u['s1']}))
"""
    d = json.loads(run_app(tmp_path, code).strip().splitlines()[-1])
    assert d["codes"][:6] == [410] * 6 and d["codes"][6] == 404 and not d["navera_access"], d
    t = open(os.path.join(STATIC, "teacher.html")).read()
    assert "navera_on" not in t and "Give full NAVERA access" not in t and "NAVERA version" not in t


# ----------------------------------------------------------------------------------------- 6. no join code on the box
def test_no_join_code_or_qr_in_product(tmp_path):
    code = """
import orgs
A._save('users.json', {'teacher': {'role': 'admin', 'index': 0, 'pw': 'x'}})
c = A.app.test_client()
o = c.get('/api/auth/options').get_json()
r = {'opts': o, 'join': c.get('/join/ABC123').status_code, 'info': c.get('/api/class-info?code=ABC123').status_code,
     'signup': c.post('/api/signup', json={'kind': 'teacher', 'display': 'Tt', 'email': 't@x.org', 'password': 'p' * 10,
                                            'invite_code': 'X'}, headers={'Origin': 'http://localhost'}).status_code}
with c.session_transaction() as s: s['user'] = 'teacher'
me = c.get('/api/me').get_json()
cl = c.post('/api/classes', json={'name': 'Class A', 'seats': 10}, headers={'Origin': 'http://localhost'}).get_json() or {}
cid = (cl.get('class') or cl).get('id') or (orgs.classes()[0]['id'] if orgs.classes() else 'none')
r.update(me_product=me.get('product'), qr=c.get(f'/api/classes/{cid}/qr.svg').status_code,
         poster=c.get(f'/class/{cid}/poster').status_code, cid=cid)
print(json.dumps(r))
"""
    d = json.loads(run_app(tmp_path, code).strip().splitlines()[-1])
    assert d["opts"]["product"] is True and d["opts"]["signup"] is False and d["opts"]["need_class"] is False, d
    assert d["join"] == 404 and d["info"] == 404 and d["signup"] == 403, d
    assert d["me_product"] is True and d["cid"] != "none", d
    assert d["qr"] == 404 and d["poster"] == 404, d
    t = open(os.path.join(STATIC, "teacher.html")).read()
    hide = t[t.index("if (ME.product) {"):t.index("}", t.index("if (ME.product) {"))]
    for el in ("joinBox", "oJoin", "tInviteBox", "signupOpt"):
        assert el in hide, el
    assert "if (!ME.product) $('cQr').src" in t
    assert "if (o.product) { $('tabUp').style.display = 'none'; }" in open(os.path.join(STATIC, "login.html")).read()


def test_no_broken_local_images_or_assets():
    """Every /static/… file a page or template names exists (a missing one is a broken image offline)."""
    bad = []
    tops = [STATIC, os.path.join(SERVER, "templates")]
    for top in tops:
        for d, _, fs in os.walk(top):
            if os.sep + "vendor" in d:
                continue
            for f in fs:
                if not f.endswith((".html", ".js", ".css")):
                    continue
                t = open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
                for m in re.findall(r"""["'(](/static/[A-Za-z0-9_./-]+)""", t):
                    if "${" in m:
                        continue
                    if not os.path.exists(os.path.join(SERVER, m.lstrip("/"))):
                        bad.append(f"{f}: {m}")
    assert not bad, bad


def test_release_vendors_the_qr_library():
    """Certificates keep a QR code (verify link): made on the box by segno, shipped in setup/vendor."""
    assert "setup/vendor/segno" in open(os.path.join(ACADEMY, "deploy", "make_release.sh")).read()
