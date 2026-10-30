"""Box access: the box's Wi-Fi (hotspot), its captive portal and the access card."""
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


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


portal_mod = load(os.path.join(PRODUCT, 'navera_portal.py'), 'navera_portal')


def sh(args, env=None):
    return subprocess.run(args, capture_output=True, text=True, timeout=60, env=dict(os.environ, **(env or {})))


def serve(handler):
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def request(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    return r.status, dict(r.getheaders()), r.read().decode()


def test_portal_sends_every_address_to_the_page():
    srv = serve(portal_mod.make_handler(portal_mod.page_url({})))
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
            '--env', str(env)])
    assert p.returncode == 0, p.stderr
    html = (tmp_path / 'c' / 'access_card.html').read_text()
    assert 'Wi-Fi: NAVERA' in html and 'http://10.42.0.1:8181/' in html
    assert sorted(os.listdir(tmp_path / 'c')) == ['access_card.html', 'qr_wifi.png']
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
    for u in ('navera-hotspot', 'navera-portal'):
        assert (r / f'etc/systemd/system/multi-user.target.wants/{u}.service').is_symlink()
    assert os.access(r / 'usr/local/lib/navera/navera_portal.py', os.X_OK)
    p2 = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p2.returncode == 0 and (r / 'etc/navera/navera.env').read_text().count('\nNAVERA_HOTSPOT=') == 1
