#!/usr/bin/env python3
"""insta360_imu.launch.py — the Insta360 One R's IMU as sensor_msgs/Imu (camera_pkg insta360_imu.py).

Examples:
  ros2 launch camera_pkg insta360_imu.launch.py replay_path:=$HOME/navera-field/2026-10-20_1150/raw
  ros2 launch camera_pkg insta360_imu.launch.py source:=live mount_axes:=-y,-z,+x
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    cfg = os.path.join(get_package_share_directory('camera_pkg'), 'config', 'insta360_imu.yaml')
    args = [
        ('source', 'replay', 'live (the camera over USB) or replay (a raw recording)'),
        ('replay_path', '', 'raw recording: a <test>/raw folder or one raw360_NNNN.bin'),
        ('replay_rate', '1.0', 'replay pacing: 1 real time, 0 as fast as possible'),
        ('replay_loop', 'false', 'start the recording again at its end'),
        ('topic', '/navera/sensors/insta360/imu', 'sensor_msgs/Imu output topic'),
        ('mount_axes', '+y,+z,+x', 'camera IMU axes along body x,y,z'),
    ]
    return LaunchDescription(
        [DeclareLaunchArgument(n, default_value=d, description=h) for n, d, h in args] + [
            Node(
                package='camera_pkg',
                executable='insta360_imu.py',
                name='insta360_imu',
                output='screen',
                parameters=[cfg, {n: LaunchConfiguration(n) for n, _, _ in args}],
            ),
        ])
