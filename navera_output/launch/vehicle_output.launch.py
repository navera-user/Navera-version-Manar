#!/usr/bin/env python3
"""vehicle_output.launch.py — NAVERA output to the autopilot (NMEA and/or MAVLink).

Examples:
  ros2 launch navera_output vehicle_output.launch.py nmea_port:=/dev/ttyUSB0
  ros2 launch navera_output vehicle_output.launch.py mavlink_url:=udpout:127.0.0.1:14550
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    cfg = os.path.join(get_package_share_directory('navera_output'), 'config',
                       'vehicle_output.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('nmea_port', default_value=os.environ.get('NAVERA_NMEA_PORT', '')),
        DeclareLaunchArgument('nmea_baud', default_value=os.environ.get('NAVERA_NMEA_BAUD', '9600')),
        DeclareLaunchArgument('mavlink_url', default_value=os.environ.get('NAVERA_MAVLINK_URL', '')),
        Node(
            package='navera_output',
            executable='vehicle_output_node.py',
            name='vehicle_output',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit restarts it.
            on_exit=Shutdown(reason='node exited'),
            parameters=[cfg, {
                'nmea_port': LaunchConfiguration('nmea_port'),
                'nmea_baud': LaunchConfiguration('nmea_baud'),
                'mavlink_url': LaunchConfiguration('mavlink_url'),
            }],
        ),
    ])
