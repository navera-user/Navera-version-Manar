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


def test_phone_checks_captive_until_page_shown_then_online(tmp_path, monkeypatch):
    monkeypatch.setattr(portal_mod, 'SPOOL', str(tmp_path))
    (tmp_path / 'state.json').write_text('{"mode": "hotspot"}')
    srv = serve(portal_mod.make_handler())
    p = srv.server_address[1]
    probes = [('/generate_204', 'connectivitycheck.gstatic.com'), ('/hotspot-detect.html', 'captive.apple.com'),
              ('/connecttest.txt', 'www.msftconnecttest.com'), ('/ncsi.txt', 'www.msftncsi.com')]
    for path, host in probes:                      # not shown yet: "captive" (the setup page), twice
        for _ in range(2):
            st, _, body = request(p, 'GET', path, {'Host': host})
            assert st == 200 and 'Open NAVERA' in body
    st, _, body = request(p, 'GET', '/', {'Host': 'captive.apple.com'})
    assert portal_mod.SEEN_PATH in body             # the page asks the browser for its beacon
    c = http.client.HTTPConnection('127.0.0.1', p, timeout=10)
    c.request('GET', portal_mod.SEEN_PATH)
    r = c.getresponse()
    assert r.status == 200 and r.getheader('Content-Type') == 'image/gif' and r.read().startswith(b'GIF89a')
    want = {'/generate_204': (204, ''), '/hotspot-detect.html': (200, portal_mod.APPLE_OK.decode()),
            '/connecttest.txt': (200, 'Microsoft Connect Test'), '/ncsi.txt': (200, 'Microsoft NCSI')}
    for path, host in probes:                      # shown: "online"
        st, hdr, body = request(p, 'GET', path, {'Host': host})
        assert (st, body) == want[path]
    assert request(p, 'GET', '/hotspot-detect.html')[2] == \
        '<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>'
    assert 'Open NAVERA' in request(p, 'GET', '/')[2]          # the page itself still works
    srv.shutdown()


def test_seen_clients_expire_and_stay_bounded():
    now = [0.0]
    seen = portal_mod.SeenClients(ttl_s=600, max_n=3, clock=lambda: now[0])
    seen.mark('10.42.0.5')
    assert seen.seen('10.42.0.5') and seen.seen('::ffff:10.42.0.5') and not seen.seen('10.42.0.6')
    now[0] = 599
    assert seen.seen('10.42.0.5')
    now[0] = 601
    assert not seen.seen('10.42.0.5')               # 10 min later: captive again
    for i in range(100):
        seen.mark(f'10.42.0.{i}')
    assert len(seen) == 3 and seen.seen('10.42.0.99') and not seen.seen('10.42.0.0')
    seen.mark('10.42.0.97')                         # re-marked: youngest again
    seen.mark('10.42.0.200')
    assert seen.seen('10.42.0.97') and not seen.seen('10.42.0.98')
    now[0] = 2000
    seen.mark('10.42.0.1')                          # expired ones are dropped on the next mark
    assert len(seen) == 1


def test_wifi_keeps_hotspot_while_a_phone_was_seen_recently(tmp_path, monkeypatch):
    wifi = load(os.path.join(PRODUCT, 'navera_wifi.py'), 'navera_wifi_hold')
    monkeypatch.setattr(wifi, 'STATE', str(tmp_path / 'state.json'))
    monkeypatch.setattr(wifi, 'REQUEST', str(tmp_path / 'request.json'))
    now, stations, tries = [10000.0], [1], []
    monkeypatch.setattr(wifi.time, 'time', lambda: now[0])
    monkeypatch.setattr(wifi, 'active_connection', lambda dev: wifi.HOTSPOT)
    monkeypatch.setattr(wifi, 'hotspot_clients', lambda dev: stations[0])
    monkeypatch.setattr(wifi, 'saved_networks', lambda: ['navera-wifi-Home'])
    monkeypatch.setattr(wifi, 'try_saved', lambda dev, s: (tries.append(now[0]), '')[1])
    for f in ('scan', 'ensure_hotspot', 'address'):
        monkeypatch.setattr(wifi, f, lambda *a, **k: '')
    state = ('hotspot', 0.0, '')
    state = wifi.step('wlan0', *state, 45, 300)        # a phone on it now: no retry
    assert tries == []
    stations[0] = 0                                     # the phone between two checks / asleep
    for dt in (5, 60, 200, 299):
        now[0] = 10000.0 + dt
        state = wifi.step('wlan0', *state, 45, 300)
    assert tries == [], 'hotspot dropped while a phone was seen within 5 min'
    now[0] = 10000.0 + 301                              # nobody for 5 min: retry the saved network
    state = wifi.step('wlan0', *state, 45, 300)
    assert tries == [10301.0] and state[0] == 'hotspot'


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
    assert '--dports 443,853 -j REJECT --reject-with tcp-reset' in on
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
    env.write_text('NAVERA_WIFI_SSID=NAVERA-3FA9\nNAVERA_WIFI_PASSWORD=Kp7mWx4zQa9t\nNAVERA_HOSTNAME=navera-3fa9\n')
    p = sh([sys.executable, os.path.join(REPO, 'navera_tools', 'access_card.py'), '--out', str(tmp_path / 'c'),
            '--env', str(env)])
    assert p.returncode == 0, p.stderr
    html = (tmp_path / 'c' / 'access_card.html').read_text()
    assert 'Wi-Fi: NAVERA-3FA9' in html and 'Password: Kp7mWx4zQa9t' in html and 'http://10.42.0.1:8181/' in html
    assert 'http://navera-3fa9.local:8181/' in html and 'navera.local' not in html
    assert sorted(os.listdir(tmp_path / 'c')) == ['access_card.html', 'qr_wifi.png']
    cv2 = pytest.importorskip('cv2')
    img = cv2.imread(str(tmp_path / 'c' / 'qr_wifi.png'), cv2.IMREAD_GRAYSCALE)
    small = cv2.resize(img, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)
    assert cv2.QRCodeDetector().detectAndDecode(small)[0] == 'WIFI:T:WPA;S:NAVERA-3FA9;P:Kp7mWx4zQa9t;;'


def test_apply_product_sets_up_access(tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_product_box import fake_root
    r = fake_root(tmp_path)
    p = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    assert p.returncode == 0, p.stdout + p.stderr
    (r / 'etc/machine-id').write_text('3fa9c0d1e2b34a5c6d7e8f9012345678\n')
    p = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])     # with this box's machine id
    assert p.returncode == 0, p.stdout + p.stderr
    env = (r / 'etc/navera/navera.env').read_text()
    assert '\nNAVERA_HOTSPOT=1\n' in env
    import re
    val = dict(ln.split('=', 1) for ln in env.splitlines() if ln.startswith('NAVERA_') and '=' in ln)
    # per-box access (the first run had no machine id: values of its own, kept)
    assert re.fullmatch(r'NAVERA-[0-9A-F]{4}', val['NAVERA_WIFI_SSID'])
    assert re.fullmatch(r'[A-HJ-NP-Za-km-z2-9]{12}', val['NAVERA_WIFI_PASSWORD'])
    assert val['NAVERA_HOSTNAME'] == 'navera-' + val['NAVERA_WIFI_SSID'][-4:].lower()
    assert val['NAVERA_WIFI_PASSWORD'] != 'navera-iris' and val['NAVERA_WIFI_PASSWORD'] not in p.stdout
    for u in ('navera-wifi', 'navera-portal'):
        assert (r / f'etc/systemd/system/multi-user.target.wants/{u}.service').is_symlink()
    assert os.access(r / 'usr/local/lib/navera/navera_portal.py', os.X_OK)
    assert os.access(r / 'usr/local/lib/navera/navera_wifi.py', os.X_OK)
    assert '\nNAVERA_WEB_TRUST_NETS=hotspot\n' in env       # not the client Wi-Fi, not the VPN
    p2 = sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r)])
    env2 = (r / 'etc/navera/navera.env').read_text()
    assert p2.returncode == 0 and env2.count('\nNAVERA_HOTSPOT=') == 1
    for k in ('NAVERA_WIFI_SSID', 'NAVERA_WIFI_PASSWORD', 'NAVERA_HOSTNAME'):     # kept on a rerun
        assert env2.count(f'\n{k}=') == 1 and f'\n{k}={val[k]}\n' in env2
    # a fresh box: the name comes from its machine id
    r2 = fake_root(tmp_path / 'b')
    (r2 / 'etc/machine-id').write_text('3fa9c0d1e2b34a5c6d7e8f9012345678\n')
    assert sh([os.path.join(PRODUCT, 'apply_product.sh'), '--root', str(r2)]).returncode == 0
    env3 = (r2 / 'etc/navera/navera.env').read_text()
    assert '\nNAVERA_WIFI_SSID=NAVERA-3FA9\n' in env3 and '\nNAVERA_HOSTNAME=navera-3fa9\n' in env3
    pw3 = [ln for ln in env3.splitlines() if ln.startswith('NAVERA_WIFI_PASSWORD=')][0]
    assert pw3 != f"NAVERA_WIFI_PASSWORD={val['NAVERA_WIFI_PASSWORD']}"       # random per box


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
