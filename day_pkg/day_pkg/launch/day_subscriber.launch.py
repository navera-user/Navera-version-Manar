#!/usr/bin/env python3
"""
day_subscriber.launch.py — start the NAVERA day visual-localization subscriber.

It consumes /day/image_raw + /day/frame_meta (published by camera_pkg) and
emits /day/position_estimate + /day/day_status.

Examples:
  ros2 launch day_pkg day_subscriber.launch.py
  ros2 launch day_pkg day_subscriber.launch.py conf_threshold:=0.80
  ros2 launch day_pkg day_subscriber.launch.py image_topic:=/day/image_raw \
                                               meta_topic:=/day/frame_meta
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('conf_threshold', default_value='0.75'),
        DeclareLaunchArgument('image_topic',    default_value='/day/image_raw'),
        DeclareLaunchArgument('meta_topic',     default_value='/day/frame_meta'),
        DeclareLaunchArgument('fix_topic',      default_value='/day/position_estimate'),
        DeclareLaunchArgument('status_topic',   default_value='/day/day_status'),
        DeclareLaunchArgument('ready_topic',    default_value='/day/localizer_ready'),

        Node(
            package='day_pkg',
            executable='day_subscriber.py',
            name='day_subscriber',
            output='screen',
            parameters=[{
                'conf_threshold': LaunchConfiguration('conf_threshold'),
                'image_topic':    LaunchConfiguration('image_topic'),
                'meta_topic':     LaunchConfiguration('meta_topic'),
                'fix_topic':      LaunchConfiguration('fix_topic'),
                'status_topic':   LaunchConfiguration('status_topic'),
                'ready_topic':    LaunchConfiguration('ready_topic'),
            }],
        ),
    ])
