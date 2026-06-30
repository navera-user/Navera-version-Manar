#!/usr/bin/env python3
"""
cn_sim.launch.py — full NAVERA "stellar" (celestial) simulation in one command.

Stellar counterpart of day_sim.launch.py. Starts the whole ROS→web chain:
  camera_pkg (celestial, etoiles.jpeg + meta)
    → cn_subscriber (astrometry geolocation)
      → /cn/position_estimate + /cn/cn_status
        → navera_stellar_bridge (HTTP :8181: navera.html + tiles + gps_status.json)

Then open http://<jetson>:8181/ , pick "Stellar Mode", set Point A, launch — the
drone marker moves on the .mbtiles map from the real ROS celestial fix.

Examples:
  ros2 launch simulation_web cn_sim.launch.py
  ros2 launch simulation_web cn_sim.launch.py conf_threshold:=0.5
  ros2 launch simulation_web cn_sim.launch.py solver_mode:=wcs       # placeholder solver
  ros2 launch simulation_web cn_sim.launch.py tilt:=75.46 azimuth:=283.18 \
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

    default_mbtiles = '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles'

    web_port       = LaunchConfiguration('web_port')
    mbtiles_path   = LaunchConfiguration('mbtiles_path')
    conf_threshold = LaunchConfiguration('conf_threshold')

    return LaunchDescription([
        DeclareLaunchArgument('web_port',       default_value='8181'),
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),
        # Celestial solver config (defaults match the bundled etoiles.jpeg sample)
        DeclareLaunchArgument('solver_mode', default_value='geoloc'),
        DeclareLaunchArgument('tilt',        default_value='75.46'),
        DeclareLaunchArgument('azimuth',     default_value='283.18'),
        DeclareLaunchArgument('utc_time',    default_value='2026-03-10 20:20:00'),

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
            }],
        ),

        # 3) ROS→web bridge (HTTP :8181 — navera.html + tiles + gps_status.json)
        Node(
            package='simulation_web',
            executable='navera_stellar_bridge.py',
            name='navera_stellar_bridge',
            output='screen',
            parameters=[{
                'status_topic': '/cn/cn_status',
                'fix_topic':    '/cn/position_estimate',
                'mbtiles_path': mbtiles_path,
                'web_port':     web_port,
            }],
        ),
    ])
