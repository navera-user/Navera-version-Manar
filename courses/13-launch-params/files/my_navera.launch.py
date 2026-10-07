"""my_navera.launch.py — a small NAVERA on the bench, with ONE command:

    ros2 launch ./my_navera.launch.py

  1. your fake GPS, with its settings from my_gps.yaml
  2. NAVERA's GPS bridge (ros_gps_node), listening to the fake GPS
  3. NAVERA's arbiter, started by NAVERA's OWN launch file (with estimator_params.yaml)

Ctrl+C stops all of them.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

HERE = os.path.dirname(os.path.abspath(__file__))       # the folder of this launch file


def generate_launch_description():
    # TODO 4: your fake GPS. Our script is not in a ROS package, so start it as a plain process:
    #   fake_gps = ExecuteProcess(cmd=["python3", <path of fake_gps_params.py>,
    #                                  "--ros-args", "--params-file", <path of my_gps.yaml>],
    #                             output="screen")
    #   Build the paths with os.path.join(HERE, "...").

    # TODO 5: NAVERA's GPS bridge, a node of the package gps_pkg:
    #   ros_gps = Node(package="gps_pkg", executable="ros_gps_node.py", name="ros_gps",
    #                  parameters=[{"fix_topic": ...}], output="screen")

    # TODO 6: NAVERA's arbiter, through NAVERA's own launch file:
    #   path = os.path.join(get_package_share_directory("navera_estimator"), "launch", "estimator.launch.py")
    #   estimator = IncludeLaunchDescription(PythonLaunchDescriptionSource(path))

    # TODO 7: put the three actions in the list below.
    return LaunchDescription([])
