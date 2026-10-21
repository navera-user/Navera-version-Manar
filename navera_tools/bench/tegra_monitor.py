#!/usr/bin/env python3
"""Jetson load monitor for benchmarks: tegrastats plus the sysfs counters it does not print.

    with TegraMonitor("/path/run_tegra.log", interval_ms=500) as mon:
        ... the measured work ...
    print(mon.summary())

Logged every interval: tegrastats' line (RAM, per-core CPU load and clock, GPU load, temperatures,
VDD_IN / VDD_CPU_GPU_CV / VDD_SOC power) and, from sysfs, the GPU clock, the fan speed and the
soctherm over-current throttle event counters (they count hardware power throttling). No root.

summary(): mean / max of power and temperatures, GPU clock min / median / max while the GPU is
busy, CPU clock min / max, over-current throttle events during the run, and the hottest zone's
margin to the 99 C software throttle trip of this board (thermal_zone*/trip_point_0, "passive").

Also a command: python3 navera_tools/bench/tegra_monitor.py LOG  (prints the summary of a log).
"""
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional

GPU_FREQ = "/sys/class/devfreq/17000000.gpu/cur_freq"
FAN_RPM = "/sys/class/hwmon/hwmon2/rpm"
OC_DIR = "/sys/class/hwmon/hwmon3"
THROTTLE_TRIP_C = 99.0            # thermal_zone*/trip_point_0 "passive" on this Orin Nano (JetPack 6.2)

_TEMP = re.compile(r"(\w+)@(-?[\d.]+)C")
_RAIL = re.compile(r"(VDD_\w+) (\d+)mW/(\d+)mW")
_CPU = re.compile(r"CPU \[([^\]]*)\]")
_GR3D = re.compile(r"GR3D_FREQ (\d+)%")
_RAM = re.compile(r"RAM (\d+)/(\d+)MB")


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def oc_events() -> Dict[str, int]:
    """Over-current (power) throttle event counters of the SoC, by name."""
    out = {}
    for k in ("oc1", "oc2", "oc3"):
        v = _read(os.path.join(OC_DIR, f"{k}_event_cnt"))
        if v is not None and v.isdigit():
            out[k] = int(v)
    return out


def parse_line(line: str) -> Optional[dict]:
    """One tegrastats line -> dict (None if it is not one)."""
    m = _RAM.search(line)
    if not m:
        return None
    d = {"ram_mb": int(m.group(1)), "ram_total_mb": int(m.group(2))}
    c = _CPU.search(line)
    if c:
        loads, freqs = [], []
        for core in c.group(1).split(","):
            if "%@" in core:
                p, f = core.split("%@")
                loads.append(int(p))
                freqs.append(int(f))
        d["cpu_load"] = loads
        d["cpu_mhz"] = freqs
    g = _GR3D.search(line)
    if g:
        d["gpu_load"] = int(g.group(1))
    for name, v in _TEMP.findall(line):
        d[f"t_{name}"] = float(v)
    for name, cur, _avg in _RAIL.findall(line):
        d[name] = int(cur)
    return d


class TegraMonitor:
    """tegrastats + sysfs sampler writing one JSON line per sample to `log` (see module doc)."""

    def __init__(self, log: str, interval_ms: int = 500):
        self.log, self.interval = log, int(interval_ms)
        self.samples: List[dict] = []
        self._stop = threading.Event()
        self._proc = None
        self._oc0: Dict[str, int] = {}
        self._t0 = 0.0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        self._oc0, self._t0 = oc_events(), time.time()
        self._proc = subprocess.Popen(["tegrastats", "--interval", str(self.interval)], stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._f = open(self.log, "w")
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self):
        for line in self._proc.stdout:
            if self._stop.is_set():
                break
            d = parse_line(line)
            if d is None:
                continue
            d["t"] = round(time.time() - self._t0, 2)
            gf = _read(GPU_FREQ)
            d["gpu_mhz"] = int(gf) // 1_000_000 if gf and gf.isdigit() else None
            rpm = _read(FAN_RPM)
            d["fan_rpm"] = int(rpm) if rpm and rpm.isdigit() else None
            d["oc"] = oc_events()
            self.samples.append(d)
            self._f.write(json.dumps(d) + "\n")
            self._f.flush()

    def stop(self):
        self._stop.set()
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._th.join(timeout=3)
        self._f.close()

    def summary(self) -> dict:
        return summarize(self.samples, self._oc0)


def summarize(samples: List[dict], oc0: Optional[Dict[str, int]] = None) -> dict:
    """Mean / max of power and temperatures, clocks and throttle evidence of a run's samples."""
    if not samples:
        return {}
    out = {"seconds": samples[-1]["t"] - samples[0]["t"], "n": len(samples)}

    def stat(key, nd=0):
        v = [s[key] for s in samples if s.get(key) is not None]
        if v:
            out[key] = {"mean": round(statistics.mean(v), nd), "max": round(max(v), nd)}
    for k in ("VDD_IN", "VDD_CPU_GPU_CV", "VDD_SOC", "ram_mb", "gpu_load", "fan_rpm"):
        stat(k)
    temps = sorted({k for s in samples for k in s if k.startswith("t_")})
    for k in temps:
        stat(k, 1)
    busy = [s["gpu_mhz"] for s in samples if s.get("gpu_mhz") and (s.get("gpu_load") or 0) >= 50]
    if busy:
        out["gpu_mhz_busy"] = {"min": min(busy), "median": int(statistics.median(busy)), "max": max(busy)}
    cpu = [f for s in samples for f in s.get("cpu_mhz", [])]
    if cpu:
        out["cpu_mhz"] = {"min": min(cpu), "max": max(cpu)}
    oc0 = oc0 if oc0 is not None else samples[0].get("oc", {})
    last = samples[-1].get("oc", {})
    out["oc_throttle_events"] = {k: last[k] - oc0.get(k, last[k]) for k in last}
    hottest = max((out[k]["max"] for k in temps if k in out and k != "t_tj"), default=None)
    if out.get("t_tj"):
        hottest = out["t_tj"]["max"]
    if hottest is not None:
        out["hottest_c"] = hottest
        out["margin_to_throttle_c"] = round(THROTTLE_TRIP_C - hottest, 1)
    return out


if __name__ == "__main__":
    rows = [json.loads(x) for x in open(sys.argv[1]) if x.strip()]
    print(json.dumps(summarize(rows), indent=1))
