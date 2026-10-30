"""Box access: the box's Wi-Fi (hotspot), its captive portal and the access card."""
import http.client
import http.server
import importlib.util
import json
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


def test_setup_page_and_wifi_request(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_mod, 'SPOOL', str(tmp_path))
    (tmp_path / 'scan.json').write_text('{"networks": [{"ssid": "ClientNet", "signal": 80, "secure": true}]}')
    monkeypatch.setenv('NAVERA_WIFI_ADDRESS', '127.0.0.1/8')     # the test client is the hotspot's
    (tmp_path / 'state.json').write_text('{"mode": "hotspot"}')
    srv = serve(portal_mod.make_handler())
    p = srv.server_address[1]
    for path in ('/generate_204', '/hotspot-detect.html', '/'):            # every address: the setup page
        st, _, body = request(p, 'GET', path, {'Host': 'connectivitycheck.gstatic.com'})
        assert st == 200 and 'ClientNet' in body and 'Open NAVERA' in body
    hdr = {'Content-Type': 'application/x-www-form-urlencoded'}
    st, _, body = request(p, 'POST', '/wifi', hdr, b'ssid=ClientNet&other=&password=short')
    assert st == 400 and not (tmp_path / 'request.json').exists()
    st, _, body = request(p, 'POST', '/wifi', hdr, b'ssid=ClientNet&other=&password=secret123')
    assert st == 200 and 'Connecting to ClientNet' in body
    req = json.loads((tmp_path / 'request.json').read_text())
    assert req['ssid'] == 'ClientNet' and req['password'] == 'secret123'
    request(p, 'POST', '/wifi', hdr, b'ssid=ClientNet&other=Hidden+Net&password=')   # typed name wins
    assert json.loads((tmp_path / 'request.json').read_text())['ssid'] == 'Hidden Net'
    (tmp_path / 'request.json').unlink()
    monkeypatch.setenv('NAVERA_WIFI_ADDRESS', '10.42.0.1/24')    # a client off the hotspot's subnet
    st, _, _ = request(p, 'POST', '/wifi', hdr, b'ssid=ClientNet&other=&password=secret123')
    assert st == 403 and not (tmp_path / 'request.json').exists()
    monkeypatch.setenv('NAVERA_WIFI_ADDRESS', '127.0.0.1/8')
    (tmp_path / 'state.json').write_text('{"mode": "client", "ssid": "ClientNet", "address": "192.168.1.50",'
                                         ' "hostname": "navera"}')
    assert 'http://navera.local:8181/' in request(p, 'GET', '/')[2]
    st, _, _ = request(p, 'POST', '/wifi', hdr, b'ssid=Other&other=&password=secret123')   # on the client Wi-Fi
    assert st == 403 and not (tmp_path / 'request.json').exists()
    srv.shutdown()


def test_wifi_manager_request_checks(tmp_path, monkeypatch):
    wifi = load(os.path.join(PRODUCT, 'navera_wifi.py'), 'navera_wifi')
    calls = []
    monkeypatch.setattr(wifi, 'nmcli', lambda *a, **k: (calls.append(a), (0, ''))[1])
    monkeypatch.setattr(wifi, 'hotspot', lambda on: calls.append(('hotspot', on)))
    assert wifi.apply_request('wlan0', {'ssid': '', 'password': ''}) == 'invalid network name'
    assert 'password' in wifi.apply_request('wlan0', {'ssid': 'X', 'password': 'short'})
    assert calls == []
    assert wifi.apply_request('wlan0', {'ssid': 'Client Net', 'password': 'secret123'}) == ''
    add = [c for c in calls if c[:2] == ('con', 'add')][0]
    assert 'navera-wifi-Client_Net-new' in add and 'secret123' in add and ('hotspot', False) in calls
    # the old profile of that name is deleted only after the new one joined, then the new takes its name
    i_up = calls.index(('con', 'up', 'navera-wifi-Client_Net-new'))
    assert calls.index(('con', 'delete', 'navera-wifi-Client_Net')) > i_up
    assert calls[-1] == ('con', 'modify', 'navera-wifi-Client_Net-new', 'connection.id', 'navera-wifi-Client_Net')
    calls.clear()                                       # join fails: the working profile stays
    monkeypatch.setattr(wifi, 'nmcli', lambda *a, **k: (calls.append(a), (4 if a[:2] == ('con', 'up') else 0, ''))[1])
    assert 'could not join' in wifi.apply_request('wlan0', {'ssid': 'Client Net', 'password': 'secret123'})
    assert ('con', 'delete', 'navera-wifi-Client_Net') not in calls
    assert calls[-1] == ('con', 'delete', 'navera-wifi-Client_Net-new')
    # a link planted in place of the request is not followed
    monkeypatch.setattr(wifi, 'REQUEST', str(tmp_path / 'request.json'))
    os.symlink('/etc/hostname', tmp_path / 'request.json')
    assert wifi.read_request() == {} and not os.path.lexists(tmp_path / 'request.json')


def test_trusted_networks():
    sys.path.insert(0, os.path.join(REPO, 'simulation_web'))
    from simulation_web import web_common
    nets = web_common.trusted_networks('10.42.0.0/24, 100.64.0.0/10, junk')
    assert web_common.is_trusted('10.42.0.7', nets) and web_common.is_trusted('100.101.1.2', nets)
    assert web_common.is_trusted('::ffff:10.42.0.9', nets)
    assert not web_common.is_trusted('192.168.1.5', nets) and not web_common.is_trusted('x', nets)
    assert not web_common.is_trusted('10.42.0.7', web_common.trusted_networks(''))


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
    assert '-i wl+ -p udp -m multiport --dports 53,67,5353 -j ACCEPT' in on
    assert '-i wl+ -s 10.42.0.0/24 -p tcp --dport 8182 -j ACCEPT' in on
    assert '-A NAVERA-PORTAL -i wl+ -s 10.42.0.0/24 -p tcp --dport 80 -j REDIRECT --to-ports 8182' in on
    assert '-i wl+ -p tcp --dport 8182' not in on                       # never from any Wi-Fi client
    other = sh([fw, '--print'], {'NAVERA_HOTSPOT': '1', 'NAVERA_WIFI_ADDRESS': '192.168.77.9/23'}).stdout
    assert '-s 192.168.76.0/23 -p tcp --dport 8182 -j ACCEPT' in other
    bad = sh([fw, '--print'], {'NAVERA_HOTSPOT': '1', 'NAVERA_WIFI_ADDRESS': '10.42.0.1'})
    assert '8182' not in bad.stdout and '--dports 53,67,5353' in bad.stdout
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
    for u in ('navera-wifi', 'navera-portal'):
        assert (r / f'etc/systemd/system/multi-user.target.wants/{u}.service').is_symlink()
    assert os.access(r / 'usr/local/lib/navera/navera_portal.py', os.X_OK)
    assert os.access(r / 'usr/local/lib/navera/navera_wifi.py', os.X_OK)
    assert '\nNAVERA_WEB_TRUST_NETS=hotspot\n' in env       # not the client Wi-Fi, not the VPN
    p2 = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p2.returncode == 0 and (r / 'etc/navera/navera.env').read_text().count('\nNAVERA_HOTSPOT=') == 1


def test_wifi_manager_survives_nmcli_hangs_and_rechecks_the_hotspot(monkeypatch):
    import subprocess
    wifi = load(os.path.join(PRODUCT, 'navera_wifi.py'), 'navera_wifi')

    def hang(*a, **k):
        raise subprocess.TimeoutExpired(a[0], k.get('timeout', 1))
    monkeypatch.setattr(wifi.subprocess, 'run', hang)
    assert wifi.nmcli('dev', timeout=1)[0] == 124          # no exception out of nmcli
    wifi.hotspot(True)                                    # nor out of the hotspot script
    # the hotspot is started again until its connection is really active
    starts, up = [], iter(['', '', 'navera-hotspot'])
    monkeypatch.setattr(wifi, 'hotspot', lambda on: starts.append(on))
    monkeypatch.setattr(wifi, 'active_connection', lambda dev: next(up, 'navera-hotspot'))
    monkeypatch.setattr(wifi.time, 'sleep', lambda s: None)
    assert wifi.ensure_hotspot('wlan0', within_s=5) and starts == [True]
    monkeypatch.setattr(wifi, 'active_connection', lambda dev: '')
    clock = iter(range(0, 1000, 3))
    monkeypatch.setattr(wifi.time, 'time', lambda: next(clock))
    starts.clear()
    assert not wifi.ensure_hotspot('wlan0', within_s=30) and len(starts) >= 2   # started again
