"""The student sandbox: bubblewrap + a systemd scope (memory / process limits).

Inside, a student sees the system read only, their own home (/home/student: lesson files, and a
NAVERA copy only for staff and students given access) read-write, the shared data read only, and nothing else of
this machine's home folder: not the real ~/Navera, not keys, not other students.
"""
import glob
import os
import subprocess

import config
import netns

GPU_DEVICES = ["/dev/nvmap", "/dev/nvsciipc", "/dev/nvgpu", "/dev/nvidia0", "/dev/nvidiactl",
               "/dev/nvidia-modeset", "/dev/dri", "/dev/host1x-fence", "/dev/dma_heap"] + sorted(glob.glob("/dev/nvhost-*"))


def student_env(name, index, heavy=False, domain=None, navera=None):
    """The sandbox's environment. A student without NAVERA access (navera False) gets no NAVERA path or
    variable: only the course's own (NAVERA_LITE_MAP). navera=None: ask config.navera_allowed(name)."""
    if navera is None:
        navera = config.navera_allowed(name)
    dom = str(domain if domain is not None else config.domain_for(index))
    env = {
        "HOME": config.S_HOME,
        "USER": "student",
        "LOGNAME": "student",
        "SHELL": "/bin/bash",
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONUSERBASE": config.PYTHON_USER_BASE,
        "ROS_DOMAIN_ID": dom,
        "ROS_LOCALHOST_ONLY": "1",
        # system + pip-user matplotlib are mixed: hide the harmless "Unable to import Axes3D" warning
        "PYTHONWARNINGS": "ignore:Unable to import Axes3D",
        "ACADEMY_STUDENT": name,
        "NAVERA_LITE_MAP": config.S_DATA + "/map.mbtiles",
        "ACADEMY_GPU_SLOTS": f"{config.S_GPU_SLOTS}:{config.GPU_SLOTS}",
    }
    if navera:                  # staff, or a student the teacher gave full NAVERA access
        env.update({
            "NAVERA_SIM_DOMAIN": dom,   # run_sim.sh: the student's own domain
            "NAVERA_MBTILES": config.S_DATA + "/map.mbtiles",
            "NAVERA_ARDUPILOT": config.S_DATA + "/ardupilot",
            "NAVERA_STHN_DIR": config.S_DATA + "/navera_data/night_pkg/STHN",
            "NAVERA_STHN_WEIGHTS": config.S_DATA + "/navera_data/night_pkg/STHN/weights/one_stage/model.safetensors",
            "DAY_DATASET_DIR": config.S_DATA + "/navera_data/day_pkg/day_pkg/dataset",
            "NAVERA_DAY_IMAGES_DIR": config.S_DATA + "/navera_data/camera_pkg/camera_pkg/data/day",
            "NAVERA_DAY_CSV": config.S_DATA + "/navera_data/camera_pkg/camera_pkg/data/day/flight_log.csv",
            "TORCH_HOME": config.S_DATA + "/navera_data/.torch_cache",   # the models (DINOv2…), read only
            "NAVERA_STATE_DIR": config.S_HOME + "/.navera_state",
        })
    for k in ("CUDA_HOME", "LD_LIBRARY_PATH"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def bwrap_argv(name, home, index, command, resources=(), heavy=False, writable_base=None, extra_ro=(),
               interactive=False, domain=None, host_net=False):
    """argv that runs `command` (list) in the student's sandbox. Without host_net (students) it runs in
    the student's own network (netns.py: only a loopback, shared by ALL sandboxes of this student:
    terminal tabs, the sealed check, try_lesson): ROS between the student's own nodes works across
    tabs, but nothing on the Jetson (the academy itself, SSH, other students, the teacher's simulator)
    and no internet is reachable. Staff keep the Jetson's network: the full simulator must be reachable
    by the academy."""
    navera = bool(writable_base) or config.navera_allowed(name)
    a = ["bwrap", "--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
         "--hostname", "navera" if navera else "academy"]
    join = []
    if not host_net:
        if netns.enabled():
            try:
                join = netns.prefix(name)        # nsenter into the student's network, then bwrap
            except Exception:                    # noqa: BLE001 — never break the sandbox for this
                join = []
        if not join:
            a += ["--unshare-net"]               # a private network for this sandbox alone (as before)
    if not interactive:          # a terminal keeps its tty (job control, Ctrl-C)
        a += ["--new-session"]
    for d in ("/usr", "/etc", "/opt", "/var/lib", "/sys", "/snap"):
        if os.path.exists(d):
            a += ["--ro-bind", d, d]
    for l in ("bin", "sbin", "lib", "lib64"):
        p = "/" + l
        if os.path.islink(p):
            a += ["--symlink", os.readlink(p), p]
        elif os.path.isdir(p):
            a += ["--ro-bind", p, p]
    a += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run"]
    # the student's own network shares one /dev/shm too (ROS 2 shared-memory transport, netns.py)
    a += ["--bind", netns.shm(name), "/dev/shm"] if join else ["--tmpfs", "/dev/shm"]
    a += ["--tmpfs", "/home", "--tmpfs", "/media", "--tmpfs", "/mnt"]
    if os.path.exists("/run/systemd/resolve"):
        a += ["--ro-bind", "/run/systemd/resolve", "/run/systemd/resolve"]   # DNS (pip, git)
    import flightgate                    # no GPU while NAVERA flies (or cannot tell): flightgate.py
    for d in (GPU_DEVICES if flightgate.gpu_allowed() else []):
        if os.path.exists(d):
            a += ["--dev-bind", d, d]
    for r in resources:
        for d in config.RESOURCES.get(r, {}).get("devices", []):
            if os.path.exists(d):
                a += ["--dev-bind", d, d]
    # Python packages installed with pip --user (torch for Jetson, kornia, lightglue…).
    if os.path.isdir(config.PYTHON_USER_SITE):
        a += ["--ro-bind", config.PYTHON_USER_SITE, config.PYTHON_USER_SITE]
    os.makedirs(config.GPU_SLOT_DIR, exist_ok=True)
    a += ["--bind", config.GPU_SLOT_DIR, config.S_GPU_SLOTS]    # shared GPU slot locks (academy_gpu.py)
    a += ["--bind", home, config.S_HOME]
    if writable_base:                    # used once, to build the base snapshot
        a += ["--bind", writable_base, config.S_NAVERA]
    for host, inside in list(config.data_mounts(navera=navera)) + list(extra_ro):
        a += ["--ro-bind", host, inside]
    a += ["--ro-bind", _passwd(), "/etc/passwd", "--ro-bind", _group(), "/etc/group"]
    a += ["--chdir", config.S_HOME, "--clearenv"]
    env = student_env(name, index, heavy, domain, navera=navera)
    lb = loopback_lib() if "sim" in resources else None
    if lb:                               # the full simulator listens on this machine only (not the Wi-Fi)
        a += ["--ro-bind", lb, "/academy/loopback_bind.so"]
        env["LD_PRELOAD"] = "/academy/loopback_bind.so"
    for k, v in env.items():
        a += ["--setenv", k, v]
    a += ["--"] + list(command)
    mem = config.HEAVY_MEMORY_MAX if heavy else config.MEMORY_MAX
    scope = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
             "--unit", f"academy-{name}-{os.getpid()}-{_counter()}",
             "-p", f"MemoryMax={mem}", "-p", "MemorySwapMax=0", "-p", f"TasksMax={config.PIDS_MAX}"]
    return scope + join + a


def loopback_lib():
    """server/native/loopback_bind.c built once into state/ (gcc); None if it cannot be built."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native", "loopback_bind.c")
    so = os.path.join(config.STATE, "loopback_bind.so")
    try:
        if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
            subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-o", so + ".tmp", src, "-ldl"], check=True,
                           capture_output=True, timeout=60)
            os.replace(so + ".tmp", so)
        return so
    except (OSError, subprocess.SubprocessError):
        return None


def _group():
    """/etc/group for the sandbox: this gid is called "student" (never the Jetson's own group name)."""
    p = os.path.join(config.STATE, "sandbox_group")
    gid = str(os.getgid())
    lines = [l for l in open("/etc/group") if l.split(":")[2:3] != [gid]]
    lines.append(f"student:x:{gid}:\n")
    data = "".join(lines)
    if not os.path.exists(p) or open(p).read() != data:
        os.makedirs(config.STATE, exist_ok=True)
        with open(p, "w") as f:
            f.write(data)
    return p


_n = [0]


def _counter():
    _n[0] += 1
    return _n[0]


def _passwd():
    """/etc/passwd for the sandbox: this uid is called "student", home /home/student."""
    p = os.path.join(config.STATE, "sandbox_passwd")
    uid, gid = os.getuid(), os.getgid()
    lines = [l for l in open("/etc/passwd") if not l.split(":")[2:3] == [str(uid)]]
    lines.append(f"student:x:{uid}:{gid}:Academy student:{config.S_HOME}:/bin/bash\n")
    data = "".join(lines)
    if not os.path.exists(p) or open(p).read() != data:
        os.makedirs(config.STATE, exist_ok=True)
        with open(p, "w") as f:
            f.write(data)
    return p
