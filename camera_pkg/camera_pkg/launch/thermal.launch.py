#!/usr/bin/env python3
"""
thermal.launch.py — launch ONE camera (thermal).

The YAML file config/thermal.yaml carries all camera-specific defaults
(camera_type, topic_ns, encoding, fps, default_gps_valid, ...).
Only csv_path / images_dir / loop can be overridden at launch time, since
those depend on where the data lives.
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('camera_pkg')
    cfg       = os.path.join(pkg_share, 'config', 'thermal.yaml')
    data_dir  = os.path.join(pkg_share, 'data', 'thermal')

    return LaunchDescription([
        DeclareLaunchArgument('csv_path',
            default_value=os.path.join(data_dir, 'flight_ready.csv')),
        DeclareLaunchArgument('images_dir',
            default_value=data_dir),
        DeclareLaunchArgument('loop', default_value='false'),
        DeclareLaunchArgument('start_paused', default_value='false'),
        DeclareLaunchArgument('fps', default_value='0.1'),
        DeclareLaunchArgument('start_delay_s', default_value='0.0'),
        DeclareLaunchArgument('flow_control', default_value='rate'),   # rate | ack (back-pressure)
        # default_gps_valid: thermal.yaml force 'false' ; night le met 'true' pour que
        # les frames du CSV avec lat/lon passent en GPS-known (navigation directe).
        DeclareLaunchArgument('default_gps_valid', default_value='false'),
        # ── handshake "ready" + cadence (Problème 1) ──
        DeclareLaunchArgument('wait_for_ready', default_value='false'),
        DeclareLaunchArgument('ready_topic', default_value='/night/localizer_ready'),
        DeclareLaunchArgument('ready_timeout_s', default_value='0.0'),
        DeclareLaunchArgument('min_frame_interval', default_value='1.0'),

        Node(
            package='camera_pkg',
            executable='camera_publisher.py',
            name='camera_publisher',
            namespace='thermal',
            output='screen',
            parameters=[
                cfg,
                {
                    'csv_path':   LaunchConfiguration('csv_path'),
                    'images_dir': LaunchConfiguration('images_dir'),
                    'loop':       LaunchConfiguration('loop'),
                    'default_gps_valid': LaunchConfiguration('default_gps_valid'),
                    'start_paused':  LaunchConfiguration('start_paused'),
                    'fps':           LaunchConfiguration('fps'),
                    'start_delay_s': LaunchConfiguration('start_delay_s'),
                    'flow_control':  LaunchConfiguration('flow_control'),
                    'wait_for_ready':     LaunchConfiguration('wait_for_ready'),
                    'ready_topic':        LaunchConfiguration('ready_topic'),
                    'ready_timeout_s':    LaunchConfiguration('ready_timeout_s'),
                    'min_frame_interval': LaunchConfiguration('min_frame_interval'),
                },
            ],
        ),
    ])
