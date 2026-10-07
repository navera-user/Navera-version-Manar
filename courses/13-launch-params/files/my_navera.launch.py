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
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.abspath(__file__))       # the folder of this launch file
NODE_SCRIPT = os.path.join(HERE, "fake_gps_node.py")
PARAMS = os.path.join(HERE, "my_gps.yaml")


def fake_gps(namespace, condition=None):
    """One fake GNSS node in `namespace`, with my_gps.yaml, publishing on <namespace>/fix."""
    # TODO 4: return Node(executable=NODE_SCRIPT, name="fake_gps", namespace=namespace,
    #                     parameters=[PARAMS], remappings=[("/fake_gps/fix", "fix")],
    #                     condition=condition, output="screen")
    #         The remapping turns the node's ABSOLUTE topic into a RELATIVE one, resolved in its namespace.
    return None


def generate_launch_description():
    # TODO 5: two launch arguments: "with_boat" (default "true") and "gps_source" (default "car").
    args = []

    # TODO 6: NAVERA's GNSS bridge, package gps_pkg, executable ros_gps_node.py, name "ros_gps",
    #         parameters=[{"fix_topic": ["/", LaunchConfiguration("gps_source"), "/fix"]}]
    #         (a LIST of strings and substitutions is joined into one string at launch time).
    ros_gps = None

    # TODO 7: NAVERA's arbiter through its own launch file, with a launch argument:
    #   path = os.path.join(get_package_share_directory("navera_estimator"), "launch", "estimator.launch.py")
    #   estimator = IncludeLaunchDescription(PythonLaunchDescriptionSource(path),
    #                                        launch_arguments={"gps_timeout_s": "2.0"}.items())
    estimator = None

    # TODO 8: the car (always) and the boat (condition=IfCondition(LaunchConfiguration("with_boat"))),
    #         then return everything in ONE list:  LaunchDescription(args + [car, boat, ros_gps, estimator])
    return LaunchDescription(args)
