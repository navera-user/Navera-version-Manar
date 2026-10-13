"""navera_lite/ros/launch_util.py — one helper for launch files: start a NAVERA Lite node the way you start it
in a terminal (`python3 -m navera_lite.ros.<module> --ros-args ...`). Part of NAVERA Lite, the course's
teaching stack (given in mission 13). Written for the course; it is not NAVERA code.

Product packages are built with colcon and started with launch_ros.actions.Node(package=..., executable=...).
NAVERA Lite is not built, so fl_node() gives the same command line to a plain ExecuteProcess. The two map
one to one (lesson 13 §5):
    Node(package="pkg", executable="exe", name="n", namespace="ns",
         parameters=["file.yaml", {"k": v}], remappings=[("from", "to")])
    fl_node("exe", "n", namespace="ns", params_file="file.yaml", params={"k": v}, remaps=[("from", "to")])
"""
import os
import sys

from launch.actions import ExecuteProcess

# @part 13
LESSON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # holds navera_lite/


# @part 13
def ros_value(value):
    """A Python value as ROS command-line text: floats keep their ".0", booleans are lower case.
    A launch substitution (or a list of them) is returned as it is.

    Example: ros_value(12.0) → "12.0";  ros_value(True) → "true";  ros_value(12) → "12"
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (int, str)):
        return str(value)
    return value


# @part 13
def _joined(head, value):
    """One command-line argument made of a text head and a value (launch joins the pieces when it runs).

    Example: _joined("speed_mps:=", 12.0) → ["speed_mps:=", "12.0"]
    """
    v = ros_value(value)
    return [head, *v] if isinstance(v, (list, tuple)) else [head, v]


# @part 13
def fl_node(module, name, namespace="", params_file=None, params=None, remaps=None, condition=None,
            output="screen"):
    """An ExecuteProcess that runs `python3 -m navera_lite.ros.<module>` from the lesson folder.

    module: "arbiter_v0", "gps_node"… · name: the node name · namespace: "" or "drone" (no leading slash
    needed) · params_file: a ROS params file (relative paths start at the lesson folder) · params: a dict
    name → value (written as -p name:=value; values may be launch substitutions) · remaps: a list of
    (from, to) topic names · condition: e.g. IfCondition(LaunchConfiguration("use_boat")).
    Example: fl_node("gps_node", "fake_gps", namespace="drone", params={"speed_mps": 12.0})
             runs: python3 -m navera_lite.ros.gps_node --ros-args -r __node:=fake_gps -r __ns:=/drone
                   -p speed_mps:=12.0
    """
    cmd = [sys.executable, "-m", f"navera_lite.ros.{module}", "--ros-args", "-r", f"__node:={name}"]
    if namespace:
        cmd += ["-r", "__ns:=/" + namespace.strip("/")]
    if params_file:
        cmd += ["--params-file", os.path.join(LESSON_DIR, params_file)]
    for key, value in (params or {}).items():
        cmd += ["-p", _joined(f"{key}:=", value)]
    for src, dst in remaps or []:
        cmd += ["-r", _joined(f"{src}:=", dst)]
    label = f"{namespace.strip('/')}/{name}" if namespace else name
    return ExecuteProcess(cmd=cmd, cwd=LESSON_DIR, name=label, output=output, condition=condition,
                          sigterm_timeout="5")
