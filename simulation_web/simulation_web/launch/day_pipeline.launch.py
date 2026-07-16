#!/usr/bin/env python3
"""
day_pipeline.launch.py — the NAVERA "day" localization pipeline, WITHOUT a bridge.

  camera_pkg (day, /day/* test images)
    → day_subscriber (DayLocalizer, DINOv2, GPU)
      → /day/position_estimate + /day/day_status

Start the bridge separately (bridge.launch.py) so that only one process binds the
HTTP port and several pipelines can run side by side. day_sim.launch.py remains as
a wrapper that starts this pipeline plus a bridge, for the single-command workflow.

VRAM: this pipeline loads DINOv2. Do NOT run it alongside night_pipeline — DINOv2
and STHN together do not fit in the Orin Nano's 8 GB shared envelope.

Examples:
  ros2 launch simulation_web day_pipeline.launch.py
  ros2 launch simulation_web day_pipeline.launch.py conf_threshold:=0.6
  ros2 launch simulation_web day_pipeline.launch.py default_gps_valid:=false  # GPS-denied
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    camera_share = get_package_share_directory('camera_pkg')

    conf_threshold = LaunchConfiguration('conf_threshold')

    return LaunchDescription([
        DeclareLaunchArgument('conf_threshold', default_value='0.75'),
        # anti-jump filter (predicted frames only) — toggle/tune without rebuild
        DeclareLaunchArgument('antijump_enabled',    default_value='true'),
        DeclareLaunchArgument('antijump_margin',     default_value='3.0'),
        DeclareLaunchArgument('antijump_min_step_m', default_value='120.0'),
        DeclareLaunchArgument('antijump_alpha',      default_value='0.4'),
        # default_gps_valid: mirrors day.yaml ('true'), so this argument changes
        # nothing by itself — it forwards day.launch.py's argument up to this level,
        # which is what lets the GPS-denied regime be MEASURED without editing a
        # config file shared with the live service.
        #   'true'  → CSV rows carrying lat/lon are replayed (MODE_REPLAYED, no DINOv2)
        #   'false' → every frame is GPS-denied: DINOv2 runs, the 25 rows with
        #             lat/lon become measurable ground truth.
        DeclareLaunchArgument('default_gps_valid', default_value='true'),

        # 1) Camera publisher (day namespace, test images)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(camera_share, 'launch', 'day.launch.py')
            ),
            launch_arguments={
                'start_paused': 'true',
                'fps': '0.5',
                'start_delay_s': '7.0',
                'flow_control': 'ack',   # back-pressure: next frame only after subscriber ack
                'csv_path': os.path.join(camera_share, 'data', 'day', 'flight_demo.csv'),
                'default_gps_valid': LaunchConfiguration('default_gps_valid'),
            }.items(),
        ),

        # 2) Day localization subscriber (GPU)
        Node(
            package='day_pkg',
            executable='day_subscriber.py',
            name='day_subscriber',
            output='screen',
            parameters=[{
                'conf_threshold': conf_threshold,
                'image_topic':  '/day/image_raw',
                'meta_topic':   '/day/frame_meta',
                'fix_topic':    '/day/position_estimate',
                'status_topic': '/day/day_status',
                'antijump_enabled':    LaunchConfiguration('antijump_enabled'),
                'antijump_margin':     LaunchConfiguration('antijump_margin'),
                'antijump_min_step_m': LaunchConfiguration('antijump_min_step_m'),
                'antijump_alpha':      LaunchConfiguration('antijump_alpha'),
            }],
        ),
    ])
