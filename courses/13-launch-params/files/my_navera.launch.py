"""my_navera.launch.py — a small NAVERA bench with ONE command:

    ros2 launch ./my_navera.launch.py
    ros2 launch ./my_navera.launch.py with_boat:=false
    ros2 launch ./my_navera.launch.py gps_source:=boat

It starts:
  1. a car's fake GNSS in the namespace /car    (params from my_gps.yaml, topic remapped to /car/fix)
  2. a boat's fake GNSS in the namespace /boat   (only if with_boat is true)
  3. NAVERA's GNSS bridge (ros_gps_node), listening to /<gps_source>/fix
  4. NAVERA's arbiter, through NAVERA's OWN launch file, with gps_timeout_s = 2.0
Ctrl+C stops all of them.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo  # noqa: F401
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.abspath(__file__))       # the folder of this launch file
NODE_SCRIPT = os.path.join(HERE, "fake_gps_node.py")
PARAMS = os.path.join(HERE, "my_gps.yaml")


def fake_gps(namespace, condition=None):
    """One fake GNSS node in `namespace`, with my_gps.yaml, publishing on <namespace>/fix."""
    # TODO 4: course section 5 (the Node action) and section 4 (the worked remapping example).
    #         Return a Node that runs NODE_SCRIPT, named "fake_gps", in `namespace`, with the file PARAMS,
    #         a remapping that turns the ABSOLUTE topic /fake_gps/fix into the RELATIVE "fix",
    #         the given `condition`, and its output on the screen.
    return None


def generate_launch_description():
    # TODO 5: course section 5 (DeclareLaunchArgument). Two arguments:
    #         "with_boat" (default "true") and "gps_source" (default "car").
    args = []

    # TODO 6: NAVERA's GNSS bridge: package gps_pkg, executable ros_gps_node.py, name "ros_gps".
    #         Its parameter fix_topic must become "/<gps_source>/fix" at launch time
    #         (course section 5: substitutions — remember that "/" + LaunchConfiguration(...) fails).
    ros_gps = None

    # TODO 7: course "In NAVERA". Include NAVERA's own launch file estimator.launch.py (package
    #         navera_estimator, folder launch in its share directory) with the launch argument
    #         gps_timeout_s = "2.0".
    estimator = None

    # TODO 8: the car (always) and the boat (only when with_boat is true: course section 5, conditions).
    #         Return ONE LaunchDescription with the arguments and the four actions.
    if None in (ros_gps, estimator):
        return LaunchDescription(args + [LogInfo(msg="TODO 4 to 8 not done yet: nothing to start.")])
    return LaunchDescription(args)
