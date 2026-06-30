#!/usr/bin/env python3
"""
cn_subscriber.launch.py — start the NAVERA celestial-navigation subscriber.

It consumes /celestial/image_raw + /celestial/frame_meta (published by
camera_pkg) and emits /cn/position_estimate + /cn/cn_status.

Examples:
  ros2 launch cn_pkg cn_subscriber.launch.py
  ros2 launch cn_pkg cn_subscriber.launch.py conf_threshold:=0.5
  ros2 launch cn_pkg cn_subscriber.launch.py image_topic:=/celestial/image_raw \
                                              meta_topic:=/celestial/frame_meta
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),
        DeclareLaunchArgument('image_topic',    default_value='/celestial/image_raw'),
        DeclareLaunchArgument('meta_topic',     default_value='/celestial/frame_meta'),
        DeclareLaunchArgument('fix_topic',      default_value='/cn/position_estimate'),
        DeclareLaunchArgument('status_topic',   default_value='/cn/cn_status'),

        Node(
            package='cn_pkg',
            executable='cn_subscriber.py',
            name='cn_subscriber',
            output='screen',
            parameters=[{
                'conf_threshold': LaunchConfiguration('conf_threshold'),
                'image_topic':    LaunchConfiguration('image_topic'),
                'meta_topic':     LaunchConfiguration('meta_topic'),
                'fix_topic':      LaunchConfiguration('fix_topic'),
                'status_topic':   LaunchConfiguration('status_topic'),
            }],
        ),
    ])
