#!/usr/bin/env python3
"""
cn_sim.launch.py — full NAVERA "stellar" (celestial) simulation in one command.

Thin wrapper over the two halves of the chain:
  cn_pipeline.launch.py   camera_pkg (celestial) → cn_subscriber (astrometry)
  bridge.launch.py        navera_stellar_bridge (HTTP :8181)

It exists so the single-command workflow keeps working. The composition itself
lives in the two included files — nothing is declared twice here.

Celestial uses its own bridge binary (navera_stellar_bridge), selected here via
bridge.launch.py's bridge_executable/bridge_name arguments. That bridge has no GPS
source, so it does not declare gps_fix_topic; bridge.launch.py passes the parameter
anyway. That is harmless and verified: rclpy silently ignores an override for a
parameter the node never declares (the node starts, binds its port and serves). The
two bridges merge once the arbiter (navera_estimator) exists — see the package README.

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


def generate_launch_description():
    web_share = get_package_share_directory('simulation_web')

    default_mbtiles = '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles'

    # Public interface: same argument names and same defaults as before the split, so
    # every existing invocation (docs, CLI overrides) keeps working.
    return LaunchDescription([
        DeclareLaunchArgument('web_port',       default_value='8181'),
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),
        # Celestial solver config (defaults match the bundled etoiles.jpeg sample)
        DeclareLaunchArgument('solver_mode', default_value='geoloc'),
        DeclareLaunchArgument('tilt',        default_value='75.46'),
        DeclareLaunchArgument('azimuth',     default_value='283.18'),
        DeclareLaunchArgument('utc_time',    default_value='2026-03-10 20:20:00'),

        # 1) Celestial pipeline: camera(celestial) + cn_subscriber (astrometry, CPU)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(web_share, 'launch', 'cn_pipeline.launch.py')
            ),
            launch_arguments={
                'conf_threshold': LaunchConfiguration('conf_threshold'),
                'solver_mode':    LaunchConfiguration('solver_mode'),
                'tilt':           LaunchConfiguration('tilt'),
                'azimuth':        LaunchConfiguration('azimuth'),
                'utc_time':       LaunchConfiguration('utc_time'),
            }.items(),
        ),

        # 2) ROS→web bridge — the stellar one, pointed at the celestial pipeline.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(web_share, 'launch', 'bridge.launch.py')
            ),
            launch_arguments={
                'bridge_executable': 'navera_stellar_bridge.py',
                'bridge_name':       'navera_stellar_bridge',
                'status_topic':      '/cn/cn_status',
                'fix_topic':         '/cn/position_estimate',
                'start_topic':       '/celestial/camera/start',
                'mbtiles_path':      LaunchConfiguration('mbtiles_path'),
                'web_port':          LaunchConfiguration('web_port'),
            }.items(),
        ),
    ])
