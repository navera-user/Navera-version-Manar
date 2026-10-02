#!/usr/bin/env python3
"""vehicle_output.launch.py — NAVERA output to the autopilot (NMEA and/or MAVLink).

Examples:
  ros2 launch navera_output vehicle_output.launch.py nmea_port:=/dev/ttyUSB0
  ros2 launch navera_output vehicle_output.launch.py mavlink_url:=udpout:127.0.0.1:14550
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _env_overrides():
    """Installation settings (/etc/navera/navera.env) that override the YAML defaults."""
    out, env = {}, os.environ
    if env.get('NAVERA_FORWARD_DEGRADED'):
        out['forward_degraded'] = env['NAVERA_FORWARD_DEGRADED'].strip().lower() in ('1', 'true', 'yes')
    for key, param in (('NAVERA_DEGRADED_SIGMA_M', 'degraded_sigma_m'),
                       ('NAVERA_MAX_MEASUREMENT_AGE_S', 'max_measurement_age_s')):
        if env.get(key):
            out[param] = float(env[key])
    if 'NAVERA_ROS_FIX_TOPIC' in env:                  # set but empty: no ROS output
        out['ros_fix_topic'] = env['NAVERA_ROS_FIX_TOPIC'].strip()
    return out


def generate_launch_description():
    cfg = os.path.join(get_package_share_directory('navera_output'), 'config',
                       'vehicle_output.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('nmea_port', default_value=(os.environ.get('NAVERA_NMEA_PORT') or '')),
        DeclareLaunchArgument('nmea_baud', default_value=(os.environ.get('NAVERA_NMEA_BAUD') or '9600')),
        DeclareLaunchArgument('mavlink_url', default_value=(os.environ.get('NAVERA_MAVLINK_URL') or '')),
        Node(
            package='navera_output',
            executable='vehicle_output_node.py',
            name='vehicle_output',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit restarts it.
            on_exit=Shutdown(reason='node exited'),
            parameters=[cfg, {
                'nmea_port': LaunchConfiguration('nmea_port'),
                'nmea_baud': LaunchConfiguration('nmea_baud'),
                'mavlink_url': LaunchConfiguration('mavlink_url'),
            }, _env_overrides()],
        ),
    ])
