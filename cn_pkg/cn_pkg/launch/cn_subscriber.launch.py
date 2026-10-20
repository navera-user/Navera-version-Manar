#!/usr/bin/env python3
"""
cn_subscriber.launch.py — start the NAVERA celestial-navigation subscriber.

It consumes /celestial/image_raw + /celestial/frame_meta (published by
camera_pkg) and emits /cn/position_estimate + /cn/cn_status.

Examples:
  ros2 launch cn_pkg cn_subscriber.launch.py
  ros2 launch cn_pkg cn_subscriber.launch.py min_log_odds:=30
  ros2 launch cn_pkg cn_subscriber.launch.py solver_mode:=allsky360 allsky_up_source:=vehicle
  ros2 launch cn_pkg cn_subscriber.launch.py image_topic:=/celestial/image_raw \
                                              meta_topic:=/celestial/frame_meta
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('min_log_odds',   default_value='20.7'),
        DeclareLaunchArgument('camera_fov_deg', default_value='nan'),
        DeclareLaunchArgument('image_topic',    default_value='/celestial/image_raw'),
        DeclareLaunchArgument('meta_topic',     default_value='/celestial/frame_meta'),
        DeclareLaunchArgument('fix_topic',      default_value='/cn/position_estimate'),
        DeclareLaunchArgument('status_topic',   default_value='/cn/cn_status'),
        DeclareLaunchArgument('solver_mode',    default_value='geoloc'),        # or allsky360 (360 camera)
        DeclareLaunchArgument('allsky_up_source', default_value='auto'),     # auto | camera | vehicle

        Node(
            package='cn_pkg',
            executable='cn_subscriber.py',
            name='cn_subscriber',
            output='screen',
            parameters=[{
                'min_log_odds': ParameterValue(LaunchConfiguration('min_log_odds'), value_type=float),
                'camera_fov_deg': ParameterValue(LaunchConfiguration('camera_fov_deg'), value_type=float),
                'image_topic':    LaunchConfiguration('image_topic'),
                'meta_topic':     LaunchConfiguration('meta_topic'),
                'fix_topic':      LaunchConfiguration('fix_topic'),
                'status_topic':   LaunchConfiguration('status_topic'),
                'solver_mode':    LaunchConfiguration('solver_mode'),
                'allsky_up_source': LaunchConfiguration('allsky_up_source'),
            }],
        ),
    ])
