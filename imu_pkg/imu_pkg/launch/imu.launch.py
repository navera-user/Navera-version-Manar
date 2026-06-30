#!/usr/bin/env python3
"""
imu.launch.py — start the NAVERA IMU node (MPU6050 + BMP180 + QMC5883L).

Examples:
  ros2 launch imu_pkg imu.launch.py
  ros2 launch imu_pkg imu.launch.py i2c_bus:=1 publish_rate:=20.0
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
        DeclareLaunchArgument('i2c_bus',      default_value='7'),
        DeclareLaunchArgument('publish_rate', default_value='10.0'),

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
