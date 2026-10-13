"""One private network per student (server/netns.py, sandbox.py with ACADEMY_SHARED_NETNS=1).

All sandboxes of ONE student (terminal tabs, the sealed check, try_lesson) share one network with only a
loopback (and one /dev/shm, for ROS 2's shared-memory transport); another student's sandbox does not see
it, even on the same ROS_DOMAIN_ID; nothing on the host network is reachable.

    python3 -m pytest -q tools/tests/test_shared_netns.py

Throw-away students _netns_a / _netns_b / _netns_chk; their holders are stopped at the end.
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "server"))
import config  # noqa: E402
import netns  # noqa: E402
import sandbox  # noqa: E402
import sealed  # noqa: E402
import workspaces  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("bwrap") is None or not os.path.isdir("/opt/ros/humble"),
                                reason="needs bubblewrap and ROS 2 Humble")
DOMAIN = 91                    # the SAME domain for both students: only the network separates them
A, B, CHK = "_netns_a", "_netns_b", "_netns_chk"

SUB_PY = r'''
import sys, time, rclpy
from std_msgs.msg import String
rclpy.init(); n = rclpy.create_node("probe_sub")
got = []
n.create_subscription(String, sys.argv[1], lambda m: got.append(m.data), 10)
t = time.time()
while time.time() - t < float(sys.argv[2]) and not got:
    rclpy.spin_once(n, timeout_sec=0.3)
print("GOT", got[0] if got else None, flush=True)
'''


@pytest.fixture(autouse=True)
def shared(monkeypatch):
    monkeypatch.setenv("ACADEMY_SHARED_NETNS", "1")
    for n in (A, B, CHK):
        workspaces.create_student(n)
        with open(os.path.join(workspaces.student_home(n), "probe_sub.py"), "w") as f:
            f.write(SUB_PY)
    yield
    for n in (A, B, CHK):
        workspaces.delete_student(n)              # also stops the holder (netns.stop)


def _start(name, cmd, **kw):
    argv = sandbox.bwrap_argv(name, workspaces.student_home(name), 0,
                              ["bash", "-c", "source /opt/ros/humble/setup.bash >/dev/null 2>&1; " + cmd],
                              domain=DOMAIN, **kw)
    assert "--unshare-net" not in argv and "nsenter" in argv, argv
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)


def _run(name, cmd, timeout=60):
    p = _start(name, cmd)
    try:
        return p.communicate(timeout=timeout)[0]
    finally:
        _stop(p)


def _stop(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait()


def _pub(name, topic, data):
    return _start(name, f'exec ros2 topic pub {topic} std_msgs/msg/String "data: {data}" -r 4')


def test_same_student_tabs_share_ros_other_student_does_not():
    pub = _pub(A, "/netns_hello", "hi-from-a")
    try:
        time.sleep(2)
        out = _run(A, "python3 ~/probe_sub.py /netns_hello 20")             # a second tab of A
        assert "GOT hi-from-a" in out, out
        out = _run(A, "timeout 20 ros2 topic echo /netns_hello std_msgs/msg/String --once")
        assert "hi-from-a" in out, out
        out = _run(B, "python3 ~/probe_sub.py /netns_hello 8")              # another student, same domain
        assert "GOT None" in out, out
    finally:
        _stop(pub)


def test_one_network_per_student_loopback_only():
    host_ip = _host_ip()
    probe = ("readlink /proc/self/ns/net; echo LINKS=$(ip -o link | awk -F': ' '{print $2}' | tr '\\n' ,); "
             f"python3 -c \"import socket; s=socket.socket(); s.settimeout(3)\n"
             f"try: s.connect(('{host_ip}', 22)); print('REACHED')\n"
             f"except OSError as e: print('UNREACHABLE', e)\"")
    a1, a2, b = _run(A, probe), _run(A, probe), _run(B, probe)
    net = lambda out: out.split()[0]                                           # noqa: E731
    assert net(a1) == net(a2) != net(b), (a1, a2, b)
    for out in (a1, b):
        assert "UNREACHABLE" in out and "REACHED" not in out.replace("UNREACHABLE", ""), out
        assert "LINKS=lo," in out, out
    rec = netns._load(A)
    assert open(f"/proc/{rec['pid']}/cmdline", "rb").read().startswith(b"academy-netns-" + A.encode())


def test_holder_reused_restarted_and_reaped():
    p1 = netns.holder(A)
    assert netns.holder(A) == p1                                    # reused
    os.kill(p1, signal.SIGKILL)
    for _ in range(50):
        if not os.path.exists(f"/proc/{p1}") or open(f"/proc/{p1}/stat").read().split()[2] == "Z":
            break
        time.sleep(0.05)
    p2 = netns.holder(A)                                            # stale PID: a new holder
    assert p2 != p1
    netns.reap(A, idle=3600)                                        # idle but recently used: kept
    assert netns._load(A)["pid"] == p2
    netns.reap(A, idle=0)                                           # nobody in it: stopped
    assert netns._load(A) is None and not os.path.isdir(os.path.join(netns.SHM_ROOT, A))


def test_fallback_when_holder_cannot_start(monkeypatch):
    def broken(name):
        raise RuntimeError("no holder")
    monkeypatch.setattr(netns, "holder", broken)
    argv = sandbox.bwrap_argv(A, workspaces.student_home(A), 0, ["true"])
    assert "--unshare-net" in argv and "nsenter" not in argv
    assert subprocess.run(argv).returncode == 0
    monkeypatch.setenv("ACADEMY_SHARED_NETNS", "0")
    argv = sandbox.bwrap_argv(A, workspaces.student_home(A), 0, ["true"])
    assert "--unshare-net" in argv and "nsenter" not in argv


CHECK_PY = r'''
from academy_check import Checker, sh
c = Checker()

@c.test("the student's terminal node is visible to the check")
def _():
    code, out = sh("python3 ~/probe_sub.py /netns_term 20", timeout=40)
    c.ok("GOT from-terminal" in out, out)

@c.test("the check is still sealed (non-dumpable)")
def _():
    import ctypes
    c.ok(ctypes.CDLL(None).prctl(3, 0, 0, 0, 0) == 0)

c.run()
'''


def test_sealed_check_sees_the_terminal_node(tmp_path, monkeypatch):
    courses = tmp_path / "courses"
    shutil.copytree(os.path.join(ACADEMY, "courses", "_lib"), courses / "_lib",
                    ignore=shutil.ignore_patterns("__pycache__"))
    c = courses / "97-netns"
    (c / "files").mkdir(parents=True)
    (c / "meta.json").write_text(json.dumps({"number": "97", "title": "netns", "check_timeout_s": 120}))
    (c / "check.py").write_text(CHECK_PY)
    monkeypatch.setattr(config, "COURSES", str(courses))
    workspaces.install_lesson(CHK, "97-netns", overwrite=True)
    pub = _pub(CHK, "/netns_term", "from-terminal")                 # "terminal 1" of the student
    try:
        time.sleep(2)
        code, out, score = sealed.run_check(CHK, "97-netns", 0, timeout=120, domain=DOMAIN)
        assert sealed.passed(code, score), out
    finally:
        _stop(pub)
    # another student's check does not see it
    pub = _pub(B, "/netns_term", "from-terminal")
    try:
        time.sleep(2)
        code, out, score = sealed.run_check(CHK, "97-netns", 0, timeout=120, domain=DOMAIN)
        assert score and score["passed"] == 1, out                  # only the prctl test passes
    finally:
        _stop(pub)


def _host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
