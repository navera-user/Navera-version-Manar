#!/usr/bin/env python3
"""
gps.launch.py — start the NAVERA GPS node.

Examples:
  ros2 launch gps_pkg gps.launch.py
  ros2 launch gps_pkg gps.launch.py serial_port:=/dev/ttyUSB0 baud_rate:=115200
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('gps_pkg')
    cfg = os.path.join(pkg_share, 'config', 'gps_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('serial_port', default_value='/dev/ttyTHS1'),
        DeclareLaunchArgument('baud_rate',   default_value='9600'),

        Node(
            package='gps_pkg',
            executable='gps_node.py',
            name='gps_node',
            output='screen',
            parameters=[
                cfg,
                {
                    'serial_port': LaunchConfiguration('serial_port'),
                    'baud_rate':   LaunchConfiguration('baud_rate'),
                },
            ],
        ),
    ])
