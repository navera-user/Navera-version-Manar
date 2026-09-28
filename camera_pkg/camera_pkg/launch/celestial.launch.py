#!/usr/bin/env python3
"""
celestial.launch.py — launch ONE camera (celestial).

The YAML file config/celestial.yaml carries all camera-specific defaults
(camera_type, topic_ns, encoding, fps, default_gps_valid, ...).
Only csv_path / images_dir / loop can be overridden at launch time, since
those depend on where the data lives.
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('camera_pkg')
    cfg       = os.path.join(pkg_share, 'config', 'celestial.yaml')
    data_dir  = os.path.join(pkg_share, 'data', 'celestial')

    return LaunchDescription([
        DeclareLaunchArgument('csv_path',
            default_value=os.path.join(data_dir, 'flight_ready.csv')),
        DeclareLaunchArgument('images_dir',
            default_value=data_dir),
        DeclareLaunchArgument('loop', default_value='true'),
        DeclareLaunchArgument('startup_delay', default_value='3.0'),
        # Latched camera/start gate (mirrors day): true → publisher blocks on
        # frame 1 until the bridge flips /celestial/camera/start=true.
        DeclareLaunchArgument('start_paused', default_value='false'),

        Node(
            package='camera_pkg',
            executable='camera_publisher.py',
            name='camera_publisher',
            namespace='celestial',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[
                cfg,
                {
                    'csv_path':   LaunchConfiguration('csv_path'),
                    'images_dir': LaunchConfiguration('images_dir'),
                    'loop':           LaunchConfiguration('loop'),
                    'startup_delay':  LaunchConfiguration('startup_delay'),
                    'start_paused':   LaunchConfiguration('start_paused'),
                },
            ],
        ),
    ])
