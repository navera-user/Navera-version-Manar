"""deploy/make_release.sh signs the archive (openssl) and deploy/verify_release.sh checks it."""
import os
import shutil
import subprocess

import pytest

DEPLOY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, **(env or {})))


@pytest.mark.skipif(not shutil.which('openssl') or not shutil.which('git'), reason='openssl / git missing')
def test_signed_release_verifies_and_tampering_is_caught(tmp_path):
    repo = tmp_path / 'repo'
    (repo / 'deploy').mkdir(parents=True)
    shutil.copy(os.path.join(DEPLOY, 'make_release.sh'), repo / 'deploy')
    (repo / 'README').write_text('x\n')
    for c in (['git', 'init', '-q'], ['git', 'add', '.'],
              ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'r']):
        assert run(c, cwd=repo).returncode == 0
    key, pub, out = tmp_path / 'k.pem', tmp_path / 'pub.pem', tmp_path / 'out'
    assert run(['openssl', 'genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256',
                '-out', str(key)]).returncode == 0
    assert run(['openssl', 'pkey', '-in', str(key), '-pubout', '-out', str(pub)]).returncode == 0
    p = run(['bash', str(repo / 'deploy/make_release.sh'), '1.2.3', 'HEAD', str(out)],
            env={'NAVERA_RELEASE_SIGN': f'openssl:{key}'})
    assert p.returncode == 0, p.stderr
    arc = out / 'navera-1.2.3.tar.gz'
    assert (out / 'navera-1.2.3.tar.gz.sig').exists()
    verify = os.path.join(DEPLOY, 'verify_release.sh')
    ok = run(['bash', verify, str(arc), str(pub)])
    assert ok.returncode == 0 and 'PASS  signature' in ok.stdout, ok.stderr
    # another key: refused
    other = tmp_path / 'o.pem'
    run(['openssl', 'genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256', '-out', str(other)])
    run(['openssl', 'pkey', '-in', str(other), '-pubout', '-out', str(tmp_path / 'opub.pem')])
    assert run(['bash', verify, str(arc), str(tmp_path / 'opub.pem')]).returncode == 1
    # tampered archive (sha256 recomputed by the attacker): the signature still catches it
    with open(arc, 'ab') as f:
        f.write(b'x')
    run(['bash', '-c', f'cd {out} && sha256sum navera-1.2.3.tar.gz > navera-1.2.3.tar.gz.sha256'])
    assert run(['bash', verify, str(arc), str(pub)]).returncode == 1
    # unsigned: a warning, a failure when signatures are required
    os.remove(out / 'navera-1.2.3.tar.gz.sig')
    assert run(['bash', verify, str(arc)]).returncode == 0
    assert run(['bash', verify, str(arc)], env={'NAVERA_RELEASE_REQUIRE_SIG': '1'}).returncode == 1
