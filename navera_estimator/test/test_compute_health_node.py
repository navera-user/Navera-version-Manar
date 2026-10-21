"""compute_health_node (hazard H-11): /diagnostics, the JSON sample and the latched degraded flag."""
import json
import os
import time

import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from navera_common.compute_health import watch_degraded
from navera_estimator.nodes.compute_health_node import ComputeHealthNode


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


@pytest.fixture
def ros():
    rclpy.init()
    yield
    rclpy.shutdown()


def test_a_hot_box_is_reported_and_degrades_the_localizers(ros, tmp_path):
    root = str(tmp_path)
    _write(root, "sys/class/thermal/thermal_zone0/type", "tj-thermal\n")
    _write(root, "sys/class/thermal/thermal_zone0/temp", "60000\n")
    _write(root, "proc/meminfo", "MemTotal: 8000000 kB\nMemAvailable: 4000000 kB\nSwapTotal: 0 kB\n")
    node = ComputeHealthNode(parameter_overrides=[rclpy.parameter.Parameter("root", value=root),
                                                  rclpy.parameter.Parameter("period_s", value=0.1)])
    diags, samples = [], []
    node.pub_diag.publish = diags.append
    node.pub_json.publish = samples.append
    assert "no swap" in node.swap_warning
    localizer = Node("fake_localizer")
    degraded = watch_degraded(localizer)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    ex.add_node(localizer)
    try:
        h = node.tick()
        assert h.level == "WARN" and not h.degraded
        st = diags[-1].status[0]
        assert st.name == "navera: compute health" and st.level == st.WARN and "no swap" in st.message
        assert json.loads(samples[-1].data)["swap_warning"]
        _write(root, "sys/class/thermal/thermal_zone0/temp", "97000\n")
        end = time.time() + 10
        while not degraded() and time.time() < end:
            ex.spin_once(timeout_sec=0.1)
        assert degraded(), "the localizer never heard the degraded flag"
        assert diags[-1].status[0].level == diags[-1].status[0].ERROR
        assert json.loads(samples[-1].data)["degraded"] is True
        _write(root, "sys/class/thermal/thermal_zone0/temp", "70000\n")
        end = time.time() + 10
        while degraded() and time.time() < end:
            ex.spin_once(timeout_sec=0.1)
        assert not degraded()
    finally:
        ex.shutdown()
        localizer.destroy_node()
        node.destroy_node()
