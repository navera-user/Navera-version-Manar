#!/usr/bin/env python3
"""
cn_pipeline.launch.py — the NAVERA "stellar" (celestial) pipeline, WITHOUT a bridge.

  camera_pkg (celestial, etoiles.jpeg + meta)
    → cn_subscriber (astrometry geolocation)
      → /cn/position_estimate + /cn/cn_status

Start the bridge separately (bridge.launch.py). cn_sim.launch.py remains as a
wrapper that starts this pipeline plus the stellar bridge, for the single-command
workflow.

This pipeline is CPU-only (astrometry.net solve-field), so unlike day/night it can
run alongside a vision pipeline without competing for VRAM.

Note: tilt / azimuth / utc_time below are launch-time constants fitted to the
bundled etoiles.jpeg sample. They are not yet fed by the IMU and the RTC, so the
celestial fix is only as good as those three numbers. Celestial position error is
proportional to attitude error (1 arcmin ≈ 1852 m), which is why this source is a
coarse fallback rather than a metric one.

Examples:
  ros2 launch simulation_web cn_pipeline.launch.py
  ros2 launch simulation_web cn_pipeline.launch.py solver_mode:=wcs       # placeholder solver
  ros2 launch simulation_web cn_pipeline.launch.py tilt:=75.46 azimuth:=283.18 \
                                                   utc_time:="2026-03-10 20:20:00"
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    camera_share = get_package_share_directory('camera_pkg')

    conf_threshold = LaunchConfiguration('conf_threshold')

    return LaunchDescription([
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),
        # Celestial solver config (defaults match the bundled etoiles.jpeg sample)
        DeclareLaunchArgument('solver_mode', default_value='geoloc'),
        DeclareLaunchArgument('tilt',        default_value='75.46'),
        DeclareLaunchArgument('azimuth',     default_value='283.18'),
        DeclareLaunchArgument('utc_time',    default_value='2026-03-10 20:20:00'),
        # Operating-area prior (Sousse) — picks between the two positions a sky
        # direction is consistent with.
        DeclareLaunchArgument('prior_lat',   default_value='35.83'),
        DeclareLaunchArgument('prior_lon',   default_value='10.64'),

        # 1) Camera publisher (celestial namespace, etoiles.jpeg + meta)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(camera_share, 'launch', 'celestial.launch.py')
            ),
            launch_arguments={
                'start_paused': 'true',   # idle until Launch Mission flips /celestial/camera/start
                'loop':         'false',  # one-shot: solve frame 1 once, no endless re-solve loop
            }.items(),
        ),

        # 2) Celestial navigation subscriber (astrometry)
        Node(
            package='cn_pkg',
            executable='cn_subscriber.py',
            name='cn_subscriber',
            output='screen',
            parameters=[{
                'conf_threshold': conf_threshold,
                'image_topic':  '/celestial/image_raw',
                'meta_topic':   '/celestial/frame_meta',
                'fix_topic':    '/cn/position_estimate',
                'status_topic': '/cn/cn_status',
                'solver_mode':  ParameterValue(LaunchConfiguration('solver_mode'), value_type=str),
                'tilt':         ParameterValue(LaunchConfiguration('tilt'), value_type=float),
                'azimuth':      ParameterValue(LaunchConfiguration('azimuth'), value_type=float),
                # Force str — "YYYY-MM-DD HH:MM:SS" would otherwise be inferred as datetime.
                'utc_time':     ParameterValue(LaunchConfiguration('utc_time'), value_type=str),
                'prior_lat':    ParameterValue(LaunchConfiguration('prior_lat'), value_type=float),
                'prior_lon':    ParameterValue(LaunchConfiguration('prior_lon'), value_type=float),
            }],
        ),
    ])
