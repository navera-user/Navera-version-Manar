#!/usr/bin/env python3
"""
rtc.launch.py — start the NAVERA RTC node (DS3231, I2C bus 1 @ 0x68).

Examples:
  ros2 launch rtc_pkg rtc.launch.py
  ros2 launch rtc_pkg rtc.launch.py i2c_bus:=7 publish_rate:=0.2
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('rtc_pkg')
    cfg = os.path.join(pkg_share, 'config', 'rtc_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('i2c_bus', default_value='1',
                              description='I2C bus: 1 (pins 27/28) or 7 (pins 3/5)'),
        DeclareLaunchArgument('publish_rate', default_value='1.0',
                              description='Publication rate in Hz (DS3231 resolves 1 s)'),

        Node(
            package='rtc_pkg',
            executable='rtc_node.py',
            name='rtc_node',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[
                cfg,
                {
                    'i2c_bus':      LaunchConfiguration('i2c_bus'),
                    'publish_rate': LaunchConfiguration('publish_rate'),
                },
            ],
        ),
    ])
