#!/usr/bin/env python3
"""
day.launch.py — launch ONE camera (day).

The YAML file config/day.yaml carries all camera-specific defaults
(camera_type, topic_ns, encoding, fps, default_gps_valid, ...).

Overridable at launch time: csv_path / images_dir / loop (they depend on where
the data lives), the cadence/handshake arguments, and default_gps_valid — whose
default here MIRRORS day.yaml, so overriding nothing reproduces the YAML exactly.

  ros2 launch camera_pkg day.launch.py                            # GPS-known replay
  ros2 launch camera_pkg day.launch.py default_gps_valid:=false   # GPS-denied
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('camera_pkg')
    cfg       = os.path.join(pkg_share, 'config', 'day.yaml')
    data_dir  = os.path.join(pkg_share, 'data', 'day')

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
        # default_gps_valid: mirrors day.yaml ('true'), so this argument changes
        # nothing by itself — it only makes the value reachable without editing a
        # file, which is what lets the GPS-denied regime be MEASURED before it is
        # shipped. Same pattern as thermal.launch.py.
        # 'true'  → a CSV row carrying lat/lon is replayed as GPS-known (MODE_REPLAYED,
        #           no DINOv2 inference). Only the 5 rows with a blank lat/lon are
        #           localized — the 5 frames with no ground truth to check against.
        # 'false' → every frame is GPS-denied: DINOv2 runs on all 30, and the 25 rows
        #           that DO carry lat/lon become measurable.
        DeclareLaunchArgument('default_gps_valid', default_value='true'),
        # ── handshake "ready" + cadence (Problème 1) ──
        DeclareLaunchArgument('wait_for_ready', default_value='true'),       # frame 1 attend le subscriber prêt
        DeclareLaunchArgument('ready_timeout_s', default_value='0.0'),       # 0 = attendre indéfiniment
        DeclareLaunchArgument('min_frame_interval', default_value='1.0'),    # cadence min visible (ack)

        Node(
            package='camera_pkg',
            executable='camera_publisher.py',
            name='camera_publisher',
            namespace='day',
            output='screen',
            parameters=[
                cfg,
                {
                    'csv_path':   LaunchConfiguration('csv_path'),
                    'images_dir': LaunchConfiguration('images_dir'),
                    'loop':       LaunchConfiguration('loop'),
                    'default_gps_valid': LaunchConfiguration('default_gps_valid'),
                    'start_paused': LaunchConfiguration('start_paused'),
                    'fps':        LaunchConfiguration('fps'),
                    'start_delay_s': LaunchConfiguration('start_delay_s'),
                    'flow_control': LaunchConfiguration('flow_control'),
                    'wait_for_ready': LaunchConfiguration('wait_for_ready'),
                    'ready_timeout_s': LaunchConfiguration('ready_timeout_s'),
                    'min_frame_interval': LaunchConfiguration('min_frame_interval'),
                },
            ],
        ),
    ])
