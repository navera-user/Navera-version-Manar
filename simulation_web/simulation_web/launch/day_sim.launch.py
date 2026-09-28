#!/usr/bin/env python3
"""
day_sim.launch.py — full NAVERA "day" simulation in one command.

Thin wrapper over the two halves of the chain:
  day_pipeline.launch.py   camera_pkg (day) → day_subscriber (DayLocalizer, DINOv2, GPU)
  bridge.launch.py         navera_web_bridge (HTTP :8181)

It exists for the single-command dev/test workflow: `ros2 launch simulation_web
day_sim.launch.py` brings up the whole day chain (pipeline + bridge) at once. It is
NOT used at boot — production runs the pipeline and the bridge as two separate systemd
services (navera-pipeline-day, navera-web); see deploy/README.md. The composition
itself lives in the two included files — nothing is declared twice here.

Then open http://<jetson>:8181/ , pick "day", set Point A, launch — the drone
marker moves on the .mbtiles map from the real ROS localization.

To run two pipelines side by side, do NOT use this file: start each pipeline without
a bridge (*_pipeline.launch.py) plus exactly one bridge.launch.py, otherwise the
second bridge dies binding the same HTTP port.

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


def generate_launch_description():
    web_share = get_package_share_directory('simulation_web')

    default_mbtiles = os.environ.get('NAVERA_MBTILES', '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles')

    # Public interface: same argument names and same defaults as before the split, so
    # every existing invocation (systemd service, docs, CLI overrides) keeps working.
    return LaunchDescription([
        DeclareLaunchArgument('web_port',       default_value='8181'),
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.75'),
        # anti-jump filter (predicted frames only) — toggle/tune without rebuild
        DeclareLaunchArgument('antijump_enabled',    default_value='true'),
        DeclareLaunchArgument('antijump_margin',     default_value='3.0'),
        DeclareLaunchArgument('antijump_min_step_m', default_value='120.0'),
        DeclareLaunchArgument('antijump_alpha',      default_value='0.4'),

        # 1) Localization pipeline: camera(day) + day_subscriber
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(web_share, 'launch', 'day_pipeline.launch.py')
            ),
            launch_arguments={
                'conf_threshold':      LaunchConfiguration('conf_threshold'),
                'antijump_enabled':    LaunchConfiguration('antijump_enabled'),
                'antijump_margin':     LaunchConfiguration('antijump_margin'),
                'antijump_min_step_m': LaunchConfiguration('antijump_min_step_m'),
                'antijump_alpha':      LaunchConfiguration('antijump_alpha'),
            }.items(),
        ),

        # 2) ROS→web bridge, pointed at the day pipeline. The topics are spelled out
        # even though they are also the bridge's own defaults: day_sim must keep
        # driving day if those defaults ever move.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(web_share, 'launch', 'bridge.launch.py')
            ),
            launch_arguments={
                'status_topic': '/day/day_status',
                'fix_topic':    '/day/position_estimate',
                'start_topic':  '/day/camera/start',
                'mbtiles_path': LaunchConfiguration('mbtiles_path'),
                'web_port':     LaunchConfiguration('web_port'),
            }.items(),
        ),
    ])
