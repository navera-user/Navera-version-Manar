"""Box access: hotspot settings, captive portal, access gate (public link) and the access card."""
import http.client
import http.server
import importlib.util
import os
import subprocess
import sys
import threading

import pytest

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT = os.path.join(DEPLOY, 'product')
REPO = os.path.dirname(DEPLOY)
KEY = '0123456789abcdef01234567'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate_mod = load(os.path.join(PRODUCT, 'navera_access_gate.py'), 'navera_access_gate')


def sh(args, env=None):
    return subprocess.run(args, capture_output=True, text=True, timeout=60, env=dict(os.environ, **(env or {})))


def serve(handler):
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def web():
    class Web(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = f'page {self.path} cookie={self.headers.get("Cookie")}'.encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_GET
    srv = serve(Web)
    yield srv.server_address[1]
    srv.shutdown()


def request(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read().decode()


def test_gate_lets_in_only_with_the_key_and_hides_it(web):
    srv = serve(gate_mod.make_handler(gate_mod.Gate(KEY, web, control=False)))
    p = srv.server_address[1]
    assert request(p, 'GET', '/')[0] == 401                       # no key: nothing of NAVERA
    assert request(p, 'GET', '/?k=wrong')[0] == 401
    st, h, _ = request(p, 'GET', f'/operator?k={KEY}&x=1')
    assert st == 303 and h['Location'] == '/operator?x=1'         # the key leaves the address bar
    cookie = h['Set-Cookie'].split(';')[0]
    assert 'HttpOnly' in h['Set-Cookie'] and 'Secure' in h['Set-Cookie']
    st, _, body = request(p, 'GET', '/operator?x=1', {'Cookie': cookie})
    assert st == 200 and body.startswith('page /operator?x=1') and 'cookie=None' in body   # cookie not passed on
    st, _, body = request(p, 'POST', '/api/mission/apply', {'Cookie': cookie}, b'{}')
    assert st == 403 and 'read-only' in body                       # view only from the internet
    srv.shutdown()


def test_gate_control_when_allowed_and_wrong_keys_slowed(web):
    gate = gate_mod.Gate(KEY, web, control=True)
    srv = serve(gate_mod.make_handler(gate))
    p = srv.server_address[1]
    cookie = request(p, 'GET', f'/?k={KEY}')[1]['Set-Cookie'].split(';')[0]
    assert request(p, 'POST', '/api/mission/apply', {'Cookie': cookie}, b'{}')[0] == 200
    for _ in range(gate_mod.FAIL_LIMIT):
        assert request(p, 'GET', '/?k=bad', {'X-Forwarded-For': '203.0.113.9'})[0] == 401
    assert request(p, 'GET', f'/?k={KEY}', {'X-Forwarded-For': '203.0.113.9'})[0] == 429
    assert request(p, 'GET', f'/?k={KEY}', {'X-Forwarded-For': '203.0.113.10'})[0] == 303
    srv.shutdown()


def test_gate_refuses_a_short_key():
    with pytest.raises(ValueError):
        gate_mod.Gate('short', 8181, False)


def test_portal_sends_every_address_to_the_page():
    srv = serve(gate_mod.make_portal_handler('http://10.42.0.1:8181/'))
    for path in ('/generate_204', '/hotspot-detect.html', '/anything?x=1'):
        st, h, _ = request(srv.server_address[1], 'GET', path, {'Host': 'connectivitycheck.gstatic.com'})
        assert st == 302 and h['Location'] == 'http://10.42.0.1:8181/'
    srv.shutdown()


def test_hotspot_settings_and_checks():
    p = sh([os.path.join(PRODUCT, 'navera_hotspot.sh'), '--print'], {'NAVERA_WIFI_IFACE': 'wlan0'})
    assert p.returncode == 0 and 'ssid NAVERA' in p.stdout and 'ipv4.method shared' in p.stdout
    assert 'navera-iris' not in p.stdout                              # the password is not printed
    assert sh([os.path.join(PRODUCT, 'navera_hotspot.sh'), '--print'],
              {'NAVERA_WIFI_PASSWORD': 'short'}).returncode == 2
    assert sh([os.path.join(PRODUCT, 'navera_hotspot.sh'), '--print'],
              {'NAVERA_WIFI_SSID': 'a b'}).returncode == 2


def test_firewall_opens_hotspot_services_only_with_the_hotspot():
    fw = os.path.join(PRODUCT, 'navera_firewall.sh')
    on = sh([fw, '--print'], {'NAVERA_HOTSPOT': '1'}).stdout
    assert '-i wl+ -p udp -m multiport --dports 53,67 -j ACCEPT' in on
    assert '-i wl+ -p tcp --dport 8182 -j ACCEPT' in on
    assert '-A NAVERA-PORTAL -i wl+ -p tcp --dport 80 -j REDIRECT --to-ports 8182' in on
    off = sh([fw, '--print'], {'NAVERA_HOTSPOT': '0'}).stdout
    assert 'wl+' not in off and 'REDIRECT' not in off


def test_access_card_has_the_wifi_code(tmp_path):
    env = tmp_path / 'navera.env'
    env.write_text('NAVERA_WIFI_SSID=NAVERA\nNAVERA_WIFI_PASSWORD=navera-iris\n')
    p = sh([sys.executable, os.path.join(REPO, 'navera_tools', 'access_card.py'), '--out', str(tmp_path / 'c'),
            '--env', str(env), '--link', ''])
    assert p.returncode == 0, p.stderr
    html = (tmp_path / 'c' / 'access_card.html').read_text()
    assert 'Wi-Fi: NAVERA' in html and 'http://10.42.0.1:8181/' in html
    assert (tmp_path / 'c' / 'qr_wifi.png').exists() and not (tmp_path / 'c' / 'qr_remote.png').exists()
    cv2 = pytest.importorskip('cv2')
    img = cv2.imread(str(tmp_path / 'c' / 'qr_wifi.png'), cv2.IMREAD_GRAYSCALE)
    small = cv2.resize(img, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)
    assert cv2.QRCodeDetector().detectAndDecode(small)[0] == 'WIFI:T:WPA;S:NAVERA;P:navera-iris;;'


def test_apply_product_sets_up_access(tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_product_box import fake_root
    r = fake_root(tmp_path)
    p = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p.returncode == 0, p.stdout + p.stderr
    env = (r / 'etc/navera/navera.env').read_text()
    assert '\nNAVERA_HOTSPOT=1\n' in env and '\nNAVERA_WIFI_SSID=NAVERA\n' in env
    key = [ln.split('=', 1)[1] for ln in env.splitlines() if ln.startswith('NAVERA_REMOTE_KEY=')]
    assert len(key) == 1 and len(key[0]) == 24
    for u in ('navera-hotspot', 'navera-portal', 'navera-access-gate', 'navera-remote'):
        assert (r / f'etc/systemd/system/multi-user.target.wants/{u}.service').is_symlink()
    assert os.access(r / 'usr/local/lib/navera/navera_access_gate.py', os.X_OK)
    p2 = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p2.returncode == 0 and f'NAVERA_REMOTE_KEY={key[0]}' in (r / 'etc/navera/navera.env').read_text()
