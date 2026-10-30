"""Flight safety first: the Academy runs on the NAVERA box, so GPU/AI training and Sim Lite are refused while
NAVERA is flying (armed, moving, navigating without GPS) — and whenever that cannot be known.

NAVERA's web bridge answers GET http://127.0.0.1:8181/api/mission/state. The Academy reads, in this order:
  in_flight_refusal   string = refuse with NAVERA's own reason (mission_prep.in_flight_refusal), null = allowed
  in_flight           true = refuse, false = allowed
  armed / moving_mps / nav_state   the same inputs in_flight_refusal() uses (armed, > 1.5 m/s, state 3 = DEGRADED)
If the bridge is unreachable, answers garbage, or reports none of these fields: REFUSE (when unsure, refuse).

Effects while refused (applied by monitor(), every POLL_S seconds):
  - /api/simlite/* code and flights answer 423 (app.py asks refusal()),
  - GPU_SLOT_DIR/FLIGHT_LOCK exists: academy_gpu.py in every sandbox refuses a GPU slot,
  - new sandboxes start without the GPU device nodes (sandbox.py asks gpu_allowed()),
  - running Academy processes that hold the GPU (an open /dev/nv* or a GPU slot lock) are stopped.
"""
import json
import os
import signal
import ssl
import threading
import time
import urllib.request

import config

POLL_S = 2.0
TIMEOUT_S = 1.5
MOVING_MPS = 1.5            # = NAVERA mission_prep.MOVING_MPS
STATE_DEGRADED = 3          # = navera_msgs/NavStatus DEGRADED (navigating without GPS)
LOCK_NAME = "FLIGHT_LOCK"

_cache = {"t": 0.0, "why": "not checked yet"}
_lock = threading.Lock()


def decide(doc):
    """NAVERA's /api/mission/state document (dict, or None when unreachable) -> reason to refuse, or None."""
    if not isinstance(doc, dict):
        return "NAVERA's status cannot be read (its web bridge on port 8181 does not answer): refused to be safe"
    if "in_flight_refusal" in doc:
        why = doc["in_flight_refusal"]
        if why is None or why is False or why == "":
            return None
        return f"NAVERA is flying ({why})" if isinstance(why, str) else "NAVERA is flying"
    if "in_flight" in doc:
        if doc["in_flight"] is False:
            return None
        return "NAVERA is flying"
    known = False
    if "armed" in doc:
        if doc["armed"]:
            return "NAVERA: the vehicle is armed"
        known = doc["armed"] is False
    sp = doc.get("moving_mps")
    if isinstance(sp, (int, float)) and sp > MOVING_MPS:
        return f"NAVERA: the vehicle is moving ({sp:.0f} m/s)"
    if doc.get("nav_state") == STATE_DEGRADED:
        return "NAVERA is navigating without GPS"
    if known and isinstance(sp, (int, float)):
        return None
    return "NAVERA does not report whether it is flying (needs a NAVERA with in_flight_refusal in /api/mission/state): refused to be safe"


def fetch(url=None, timeout=TIMEOUT_S):
    url = url or config.NAVERA_STATE_URL
    ctx = None
    if url.startswith("https://127.0.0.1") or url.startswith("https://localhost"):
        ctx = ssl.create_default_context()          # NAVERA_WEB_TLS: its own certificate, on this box only
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return json.loads(r.read(1 << 20).decode("utf-8", "replace"))
    except Exception:            # noqa: BLE001 — any failure means "unsure"
        return None


def refusal(max_age=POLL_S):
    """Reason the heavy jobs are refused now, or None. Cached for max_age seconds."""
    if not config.FLIGHT_GATE:
        return None
    with _lock:
        if time.monotonic() - _cache["t"] < max_age:
            return _cache["why"]
    why = decide(fetch())
    with _lock:
        _cache.update(t=time.monotonic(), why=why)
    return why


def gpu_allowed():
    return refusal() is None


def _lock_path():
    return os.path.join(config.GPU_SLOT_DIR, LOCK_NAME)


def apply(why):
    """Make the sandboxes see the decision (FLIGHT_LOCK) and stop GPU work when refused."""
    os.makedirs(config.GPU_SLOT_DIR, exist_ok=True)
    p = _lock_path()
    if why:
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            f.write(why + "\n")
        os.replace(tmp, p)
        return stop_gpu_jobs()
    if os.path.exists(p):
        os.unlink(p)
    return []


def _gpu_holders():
    """PIDs of this user's processes (never this server) with a GPU device or a GPU slot lock open."""
    me, uid, out = os.getpid(), os.getuid(), []
    slots = os.path.realpath(config.GPU_SLOT_DIR) + os.sep
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            for fd in os.listdir(f"/proc/{pid}/fd"):
                t = os.readlink(f"/proc/{pid}/fd/{fd}")
                if t.startswith(("/dev/nvmap", "/dev/nvgpu", "/dev/nvhost-gpu", "/dev/nvhost-ctrl-gpu", "/dev/nvidia")) \
                        or t.startswith(slots) or t.startswith(config.S_GPU_SLOTS + "/slot"):
                    out.append(int(pid))
                    break
        except OSError:
            continue
    return out


def stop_gpu_jobs():
    pids = _gpu_holders()
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    if pids:
        print(f"flight gate: stopped {len(pids)} GPU process(es) of the Academy", flush=True)
    return pids


def monitor():
    """Background thread of the server."""
    last = object()
    while True:
        try:
            why = refusal(max_age=0)
            if why != last:
                print(f"flight gate: {'REFUSING heavy jobs: ' + why if why else 'heavy jobs allowed'}", flush=True)
            apply(why)
            last = why
        except Exception as e:      # noqa: BLE001 — never let the monitor die
            print("flight gate:", e, flush=True)
        time.sleep(POLL_S)
