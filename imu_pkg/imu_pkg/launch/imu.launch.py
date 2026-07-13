#!/usr/bin/env python3
"""
imu.launch.py — start the NAVERA IMU node (BNO085, 9-DoF with on-chip fusion).

Examples:
  ros2 launch imu_pkg imu.launch.py
  ros2 launch imu_pkg imu.launch.py i2c_bus:=7 publish_rate:=100.0
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('imu_pkg')
    cfg = os.path.join(pkg_share, 'config', 'imu_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('i2c_bus', default_value='1',
                              description='I2C bus: 1 (pins 27/28) or 7 (pins 3/5)'),
        DeclareLaunchArgument('publish_rate', default_value='50.0',
                              description='Publication rate in Hz'),

        Node(
            package='imu_pkg',
            executable='imu_node.py',
            name='imu_node',
            output='screen',
            parameters=[
                cfg,
                {
                    'i2c_bus':      LaunchConfiguration('i2c_bus'),
                    'publish_rate': LaunchConfiguration('publish_rate'),
                },
            ],
        ),
    ])
