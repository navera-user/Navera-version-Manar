"""Compute health of the Jetson: temperatures, memory, swap, GPU load, thermal throttling (hazard H-11).

Read from the same kernel files tegrastats uses, without root:
  /sys/class/thermal/thermal_zone*/{type,temp}          temperatures (milli-degC; a zone that cannot
                                                        be read, e.g. a powered-down CV engine, is skipped)
  /sys/class/thermal/cooling_device*/{type,cur_state}   throttling: a "*-throttle-alert", "cpufreq-*"
                                                        or "devfreq-*" device above state 0 (fans excluded)
  /proc/meminfo                                         MemTotal, MemAvailable, SwapTotal, SwapFree
  /sys/devices/gpu.0/load, /sys/devices/platform/17000000.gpu/load   GPU load (per mille)
Every reader takes a `root` so the tests can point it at a fake tree. No ROS here: the node
(navera_estimator compute_health_node) publishes the result.

Levels: OK, WARN (temperature >= temp_warn_c, available memory <= mem_warn_pct, throttling,
no swap) and DEGRADED (temperature >= temp_degrade_c or available memory <= mem_degrade_pct):
the localizers then skip their optional heavy retries until it clears (with hysteresis).
Measured on the bench (2026-10-21, Orin Nano, idle with another GPU job): tj 63 C, 3.8 of 7.8 GB
available; F5: a day pipeline without swap was OOM-killed after 4.6 min.
"""
import glob
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

GPU_LOAD_FILES = ("sys/devices/gpu.0/load", "sys/devices/platform/17000000.gpu/load")
_THROTTLE_KINDS = ("throttle", "cpufreq", "devfreq")


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def read_temperatures(root: str = "/") -> Dict[str, float]:
    """{zone type: degC} of every readable thermal zone."""
    out = {}
    for z in sorted(glob.glob(os.path.join(root, "sys/class/thermal/thermal_zone*"))):
        name, raw = _read(os.path.join(z, "type")), _read(os.path.join(z, "temp"))
        try:
            out[name or os.path.basename(z)] = int(raw) / 1000.0
        except (TypeError, ValueError):
            continue
    return out


def read_throttling(root: str = "/") -> List[str]:
    """Cooling devices that are throttling now ("type state/max")."""
    out = []
    for c in sorted(glob.glob(os.path.join(root, "sys/class/thermal/cooling_device*"))):
        kind = _read(os.path.join(c, "type")) or ""
        if not any(k in kind for k in _THROTTLE_KINDS):
            continue
        try:
            cur = int(_read(os.path.join(c, "cur_state")) or 0)
        except ValueError:
            continue
        if cur > 0:
            out.append(f"{kind} {cur}/{_read(os.path.join(c, 'max_state')) or '?'}")
    return out


def read_memory(root: str = "/") -> Dict[str, float]:
    """MemTotal, MemAvailable, SwapTotal, SwapFree in MB (missing keys absent)."""
    out = {}
    text = _read(os.path.join(root, "proc/meminfo")) or ""
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            try:
                out[key] = int(rest.split()[0]) / 1024.0
            except (IndexError, ValueError):
                pass
    return out


def read_gpu_load(root: str = "/") -> Optional[float]:
    """GPU load in percent, None when the kernel does not expose it."""
    for rel in GPU_LOAD_FILES:
        raw = _read(os.path.join(root, rel))
        if raw is not None:
            try:
                return int(raw) / 10.0
            except ValueError:
                return None
    return None


@dataclass
class Thresholds:
    """Levels of the assessment (degC, percent of MemTotal available)."""

    temp_warn_c: float = 85.0
    temp_degrade_c: float = 95.0
    mem_warn_pct: float = 15.0
    mem_degrade_pct: float = 8.0
    temp_clear_c: float = 5.0        # hysteresis: degraded ends this far below temp_degrade_c
    mem_clear_pct: float = 4.0       # ... and this far above mem_degrade_pct


@dataclass
class Health:
    """One assessment."""

    level: str = "OK"                                   # OK | WARN | DEGRADED
    degraded: bool = False
    messages: List[str] = field(default_factory=list)
    temperatures_c: Dict[str, float] = field(default_factory=dict)
    max_temp_c: Optional[float] = None
    mem_available_pct: Optional[float] = None
    memory_mb: Dict[str, float] = field(default_factory=dict)
    swap_mb: Optional[float] = None
    gpu_load_pct: Optional[float] = None
    throttling: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """JSON-ready."""
        return {"level": self.level, "degraded": self.degraded, "messages": self.messages,
                "temperatures_c": {k: round(v, 1) for k, v in self.temperatures_c.items()},
                "max_temp_c": None if self.max_temp_c is None else round(self.max_temp_c, 1),
                "mem_available_pct": None if self.mem_available_pct is None else round(self.mem_available_pct, 1),
                "memory_mb": {k: round(v) for k, v in self.memory_mb.items()},
                "swap_mb": None if self.swap_mb is None else round(self.swap_mb),
                "gpu_load_pct": self.gpu_load_pct, "throttling": self.throttling}


class ComputeHealthMonitor:
    """Reads the sources and keeps the degraded state with hysteresis."""

    def __init__(self, thresholds: Optional[Thresholds] = None, root: str = "/"):
        self.th, self.root = thresholds or Thresholds(), root
        self.degraded = False

    def swap_report(self) -> Optional[str]:
        """A warning when the box has no swap (checked at start), else None."""
        swap = read_memory(self.root).get("SwapTotal")
        if swap is not None and swap <= 0.0:
            return ("no swap configured: an out-of-memory kill ends navigation (F5: day pipeline killed "
                    "after 4.6 min) — add a swap file (deploy/README.md)")
        return None

    def sample(self) -> Health:
        """Read every source once and assess it."""
        th = self.th
        h = Health(temperatures_c=read_temperatures(self.root), memory_mb=read_memory(self.root),
                   gpu_load_pct=read_gpu_load(self.root), throttling=read_throttling(self.root))
        h.max_temp_c = max(h.temperatures_c.values()) if h.temperatures_c else None
        total, avail = h.memory_mb.get("MemTotal"), h.memory_mb.get("MemAvailable")
        if total and avail is not None:
            h.mem_available_pct = 100.0 * avail / total
        h.swap_mb = h.memory_mb.get("SwapTotal")
        warn = []
        hot = h.max_temp_c is not None and h.max_temp_c >= th.temp_degrade_c
        low = h.mem_available_pct is not None and h.mem_available_pct <= th.mem_degrade_pct
        if hot or low:
            self.degraded = True
        elif self.degraded:
            cool = h.max_temp_c is None or h.max_temp_c < th.temp_degrade_c - th.temp_clear_c
            roomy = h.mem_available_pct is None or h.mem_available_pct > th.mem_degrade_pct + th.mem_clear_pct
            self.degraded = not (cool and roomy)
        if h.max_temp_c is not None and h.max_temp_c >= th.temp_warn_c:
            zone = max(h.temperatures_c, key=h.temperatures_c.get)
            warn.append(f"{zone} {h.max_temp_c:.0f} C (warn {th.temp_warn_c:.0f}, degrade {th.temp_degrade_c:.0f})")
        if h.mem_available_pct is not None and h.mem_available_pct <= th.mem_warn_pct:
            warn.append(f"memory available {h.mem_available_pct:.0f} % ({avail:.0f} MB; warn "
                        f"{th.mem_warn_pct:.0f} %, degrade {th.mem_degrade_pct:.0f} %)")
        if h.throttling:
            warn.append("thermal throttling: " + ", ".join(h.throttling))
        if h.swap_mb is not None and h.swap_mb <= 0.0:
            warn.append("no swap")
        h.degraded = self.degraded
        h.messages = warn + (["degraded: heavy retries skipped"] if self.degraded else [])
        h.level = "DEGRADED" if self.degraded else ("WARN" if warn else "OK")
        return h


DEGRADED_TOPIC = "/navera/compute/degraded"


def watch_degraded(node):
    """Subscribe `node` to the latched DEGRADED_TOPIC; returns a function telling whether the compute
    is degraded now (False until the monitor says otherwise). The localizers use it to skip their
    optional heavy retries.
    """
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from std_msgs.msg import Bool
    state = {"degraded": False}

    def on_msg(msg):
        if bool(msg.data) != state["degraded"]:
            node.get_logger().warn("compute degraded (hot or short of memory): optional heavy retries skipped"
                                   if msg.data else "compute healthy again: retries back on")
        state["degraded"] = bool(msg.data)

    node.create_subscription(Bool, DEGRADED_TOPIC, on_msg,
                             QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                        reliability=ReliabilityPolicy.RELIABLE))
    return lambda: state["degraded"]
