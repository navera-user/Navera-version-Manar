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
from launch_ros.parameter_descriptions import ParameterValue
from navera_common.vehicle import max_speed_params


def _mavlink_url():
    url = (os.environ.get('NAVERA_MAVLINK_URL') or '').strip()
    return '' if url.lower() in ('off', 'none', 'false', '0') else url


def _bool(key, value):
    v = value.strip().lower()
    if v in ('1', 'true', 'yes', 'on'):
        return True
    if v in ('0', 'false', 'no', 'off'):
        return False
    raise ValueError(f"{key}={value!r}: expected true or false")    # never a silent false


def _env_overrides():
    """Installation settings (/etc/navera/navera.env) that override the YAML defaults."""
    out, env = {}, os.environ
    for key, param in (('NAVERA_FORWARD_DEGRADED', 'forward_degraded'),
                       ('NAVERA_NMEA_FORWARD_DEGRADED', 'nmea_forward_degraded'),
                       ('NAVERA_ROS_FORWARD_DEGRADED', 'ros_forward_degraded')):
        if env.get(key):
            out[param] = _bool(key, env[key])
    for key, param in (('NAVERA_DEGRADED_SIGMA_M', 'degraded_sigma_m'),
                       ('NAVERA_MAX_MEASUREMENT_AGE_S', 'max_measurement_age_s'),
                       ('NAVERA_BRIDGE_MAX_S', 'bridge_max_s')):
        if env.get(key):
            out[param] = float(env[key])
    if (env.get('NAVERA_MAVLINK_SYSID') or '').strip().isdigit():
        out['mavlink_system_id'] = int(env['NAVERA_MAVLINK_SYSID'])     # the autopilot's own id
    if (env.get('NAVERA_ROS_FIX_FRAME_ID') or '').strip():
        out['ros_fix_frame_id'] = env['NAVERA_ROS_FIX_FRAME_ID'].strip()
    if 'NAVERA_ROS_FIX_TOPIC' in env:                  # set but empty: no ROS output
        out['ros_fix_topic'] = env['NAVERA_ROS_FIX_TOPIC'].strip()
    return out


def generate_launch_description():
    cfg = os.path.join(get_package_share_directory('navera_output'), 'config',
                       'vehicle_output.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('nmea_port', default_value=(os.environ.get('NAVERA_NMEA_PORT') or '')),
        DeclareLaunchArgument('nmea_baud', default_value=(os.environ.get('NAVERA_NMEA_BAUD') or '9600')),
        # "off" / "none": no MAVLink output (also when navera-discover found an autopilot)
        DeclareLaunchArgument('mavlink_url', default_value=_mavlink_url()),
        Node(
            package='navera_output',
            executable='vehicle_output_node.py',
            name='vehicle_output',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit restarts it.
            on_exit=Shutdown(reason='node exited'),
            parameters=[cfg, {
                # text, always: launch would read "off" / "no" as booleans
                'nmea_port': ParameterValue(LaunchConfiguration('nmea_port'), value_type=str),
                'nmea_baud': LaunchConfiguration('nmea_baud'),
                'mavlink_url': ParameterValue(LaunchConfiguration('mavlink_url'), value_type=str),
            }, _env_overrides(), max_speed_params()],
        ),
    ])
