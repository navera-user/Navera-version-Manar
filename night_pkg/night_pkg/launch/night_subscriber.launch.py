#!/usr/bin/env python3
"""
night_subscriber.launch.py — NAVERA night STHN subscriber.

Consumes /thermal/image_raw + /thermal/frame_meta (from camera_pkg)
and emits /night/position_estimate + /night/night_status.

Examples:
  ros2 launch night_pkg night_subscriber.launch.py
  ros2 launch night_pkg night_subscriber.launch.py conf_threshold:=0.5
  ros2 launch night_pkg night_subscriber.launch.py \
       weights:=/path/to/other/model.safetensors
"""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('sthn_dir',
            default_value=os.environ.get('NAVERA_STHN_DIR', '/home/navera/isaac_ros_common/night_pkg/STHN')),
        DeclareLaunchArgument('weights',
            default_value=os.environ.get('NAVERA_STHN_WEIGHTS', '/home/navera/isaac_ros_common/night_pkg/STHN/weights/one_stage/model.safetensors')),
        DeclareLaunchArgument('mbtiles',
            default_value=os.environ.get('NAVERA_MBTILES', '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles')),
        DeclareLaunchArgument('zoom',           default_value='17'),
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),
        DeclareLaunchArgument('image_topic',    default_value='/thermal/image_raw'),
        DeclareLaunchArgument('meta_topic',     default_value='/thermal/frame_meta'),
        DeclareLaunchArgument('fix_topic',      default_value='/night/position_estimate'),
        DeclareLaunchArgument('status_topic',   default_value='/night/night_status'),

        Node(
            package='night_pkg',
            executable='night_subscriber.py',
            name='night_subscriber',
            output='screen',
            parameters=[{
                'sthn_dir':        LaunchConfiguration('sthn_dir'),
                'weights':         LaunchConfiguration('weights'),
                'mbtiles':         LaunchConfiguration('mbtiles'),
                'zoom':            LaunchConfiguration('zoom'),
                'conf_threshold':  LaunchConfiguration('conf_threshold'),
                'image_topic':     LaunchConfiguration('image_topic'),
                'meta_topic':      LaunchConfiguration('meta_topic'),
                'fix_topic':       LaunchConfiguration('fix_topic'),
                'status_topic':    LaunchConfiguration('status_topic'),
            }],
        ),
    ])
