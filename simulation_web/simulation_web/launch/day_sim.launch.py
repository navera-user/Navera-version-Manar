#!/usr/bin/env python3
"""
day_sim.launch.py — full NAVERA "day" simulation in one command.

Starts the whole ROS→web chain:
  camera_pkg (day, /day/* test images)
    → day_subscriber (DayLocalizer, GPU)
      → /day/position_estimate + /day/day_status
        → navera_web_bridge (HTTP :8181: navera.html + tiles + gps_status.json)

Then open http://<jetson>:8181/ , pick "day", set Point A, launch — the drone
marker moves on the .mbtiles map from the real ROS localization.

Examples:
  ros2 launch simulation_web day_sim.launch.py
  ros2 launch simulation_web day_sim.launch.py web_port:=8181 conf_threshold:=0.6
  ros2 launch simulation_web day_sim.launch.py \
       mbtiles_path:=/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles
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

    default_mbtiles = '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles'

    web_port       = LaunchConfiguration('web_port')
    mbtiles_path   = LaunchConfiguration('mbtiles_path')
    conf_threshold = LaunchConfiguration('conf_threshold')

    return LaunchDescription([
        DeclareLaunchArgument('web_port',       default_value='8181'),
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.75'),
        # anti-jump filter (predicted frames only) — toggle/tune without rebuild
        DeclareLaunchArgument('antijump_enabled',    default_value='true'),
        DeclareLaunchArgument('antijump_margin',     default_value='3.0'),
        DeclareLaunchArgument('antijump_min_step_m', default_value='120.0'),
        DeclareLaunchArgument('antijump_alpha',      default_value='0.4'),

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

        # 3) ROS→web bridge (HTTP :8181 — navera.html + tiles + gps_status.json)
        Node(
            package='simulation_web',
            executable='navera_web_bridge.py',
            name='navera_web_bridge',
            output='screen',
            parameters=[{
                'status_topic': '/day/day_status',
                'fix_topic':    '/day/position_estimate',
                'mbtiles_path': mbtiles_path,
                'web_port':     web_port,
            }],
        ),
    ])
