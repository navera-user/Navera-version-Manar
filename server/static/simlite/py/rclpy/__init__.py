"""NAVERA Sim Lite: a small stand-in for rclpy, running in the browser (Pyodide).

It gives a node the same API it has on the robot (clock, timers, topics, parameters,
logging), driven by the Sim Lite clock instead of ROS 2 and DDS. One process, one bus,
simulated time: callbacks run in order, exactly when the simulator says.
"""
from . import _core
from ._core import ok, init, shutdown, spin, spin_once  # noqa: F401
from . import node, time, duration, clock, qos, executors, parameter  # noqa: F401
