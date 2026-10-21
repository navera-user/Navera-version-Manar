"""Unit tests for navera_common.compute_health (hazard H-11) on a fake /sys + /proc tree."""
import os

import pytest

from navera_common import compute_health as ch


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _box(root, temps=(("cpu-thermal", 63000), ("gpu-thermal", 62000)), avail_kb=3_800_000,
         swap_kb=20_000_000, throttle=0, gpu="998", gpu_path="sys/devices/platform/17000000.gpu/load"):
    for i, (name, t) in enumerate(temps):
        _write(root, f"sys/class/thermal/thermal_zone{i}/type", name + "\n")
        _write(root, f"sys/class/thermal/thermal_zone{i}/temp", f"{t}\n")
    os.makedirs(os.path.join(root, f"sys/class/thermal/thermal_zone{len(temps)}"))   # powered-down zone
    _write(root, f"sys/class/thermal/thermal_zone{len(temps)}/type", "cv0-thermal\n")
    for i, (kind, cur) in enumerate((("pwm-fan", 2), ("cpu-throttle-alert", throttle), ("cpufreq-cpu0", 0))):
        _write(root, f"sys/class/thermal/cooling_device{i}/type", kind + "\n")
        _write(root, f"sys/class/thermal/cooling_device{i}/cur_state", f"{cur}\n")
        _write(root, f"sys/class/thermal/cooling_device{i}/max_state", "2\n")
    _write(root, "proc/meminfo", f"MemTotal:        7789824 kB\nMemFree: 1 kB\nMemAvailable:    {avail_kb} kB\n"
                                 f"SwapTotal:      {swap_kb} kB\nSwapFree:       {swap_kb} kB\n")
    if gpu is not None:
        _write(root, gpu_path, gpu + "\n")
    return root


def test_the_readers_parse_the_tegra_files(tmp_path):
    root = _box(str(tmp_path), throttle=1)
    assert ch.read_temperatures(root) == {"cpu-thermal": 63.0, "gpu-thermal": 62.0}   # cv0 unreadable: skipped
    assert ch.read_throttling(root) == ["cpu-throttle-alert 1/2"]                      # the fan is no throttling
    mem = ch.read_memory(root)
    assert mem["MemTotal"] == pytest.approx(7607.25) and mem["SwapTotal"] > 0
    assert ch.read_gpu_load(root) == 99.8
    assert ch.read_gpu_load(_box(str(tmp_path / "b"), gpu="250", gpu_path="sys/devices/gpu.0/load")) == 25.0
    assert ch.read_gpu_load(_box(str(tmp_path / "c"), gpu=None)) is None


def test_a_healthy_box_is_ok(tmp_path):
    h = ch.ComputeHealthMonitor(root=_box(str(tmp_path))).sample()
    assert h.level == "OK" and not h.degraded and h.messages == []
    assert h.max_temp_c == 63.0 and 48 < h.mem_available_pct < 50 and h.gpu_load_pct == 99.8


def test_hot_or_short_of_memory_degrades_with_hysteresis(tmp_path):
    root = str(tmp_path)
    m = ch.ComputeHealthMonitor(root=_box(root, temps=(("tj-thermal", 88000),)))
    h = m.sample()
    assert h.level == "WARN" and not h.degraded and "tj-thermal 88 C" in h.messages[0]
    _write(root, "sys/class/thermal/thermal_zone0/temp", "96000\n")
    h = m.sample()
    assert h.level == "DEGRADED" and h.degraded
    _write(root, "sys/class/thermal/thermal_zone0/temp", "92000\n")       # below 95 but not 5 C below
    assert m.sample().degraded
    _write(root, "sys/class/thermal/thermal_zone0/temp", "89000\n")
    assert not m.sample().degraded
    m2 = ch.ComputeHealthMonitor(root=_box(str(tmp_path / "mem"), avail_kb=500_000))   # 6 % available
    h = m2.sample()
    assert h.degraded and any("memory available 6 %" in x for x in h.messages)


def test_throttling_warns_and_no_swap_is_reported_at_start(tmp_path):
    m = ch.ComputeHealthMonitor(root=_box(str(tmp_path), throttle=2, swap_kb=0))
    h = m.sample()
    assert h.level == "WARN" and "thermal throttling: cpu-throttle-alert 2/2" in h.messages
    assert "no swap" in h.messages and "F5" in m.swap_report()
    assert ch.ComputeHealthMonitor(root=_box(str(tmp_path / "s"))).swap_report() is None


def test_this_machine_can_be_read_without_root():
    if not os.path.isdir("/sys/class/thermal"):
        pytest.skip("no thermal zones here")
    h = ch.ComputeHealthMonitor().sample()
    assert h.temperatures_c and h.mem_available_pct is not None and h.as_dict()["level"] in ("OK", "WARN", "DEGRADED")
