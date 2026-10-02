#!/usr/bin/env python3
"""
estimator.launch.py — start the NAVERA position arbiter (GPS > day > night > celestial).

Examples:
  ros2 launch navera_estimator estimator.launch.py
  ros2 launch navera_estimator estimator.launch.py gps_timeout_s:=2.0
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo, DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from navera_common.vehicle import imu_topic_params, max_speed_mps_from_env, max_speed_params


def generate_launch_description():
    pkg_share = get_package_share_directory('navera_estimator')
    cfg = os.path.join(pkg_share, 'config', 'estimator_params.yaml')

    return LaunchDescription([
            LogInfo(msg='WARNING: NAVERA_MAX_SPEED_KMH is not set in /etc/navera/navera.env — the estimator uses its default speed limit; set the vehicle\'s maximum speed (km/h).') if not max_speed_params() else LogInfo(msg=f'vehicle maximum speed: {max_speed_mps_from_env():.1f} m/s'),
        DeclareLaunchArgument('publish_rate_hz', default_value='5.0'),
        DeclareLaunchArgument('gps_timeout_s',   default_value='3.0'),
        DeclareLaunchArgument('imu_timeout_s',   default_value='1.0'),

        Node(
            package='navera_estimator',
            executable='estimator_node.py',
            name='estimator_node',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[
                cfg,
                {
                    'publish_rate_hz': LaunchConfiguration('publish_rate_hz'),
                    'gps_timeout_s':   LaunchConfiguration('gps_timeout_s'),
                    'imu_timeout_s':   LaunchConfiguration('imu_timeout_s'),
                },
                # the vehicle's maximum speed (NAVERA_MAX_SPEED_KMH): GPS plausibility gate
                max_speed_params(),
                # IMU liveness on the attitude NAVERA actually uses (box, vehicle or ROS)
                imu_topic_params(),
            ],
        ),
    ])
