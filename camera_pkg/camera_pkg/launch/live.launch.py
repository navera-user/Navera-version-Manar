#!/usr/bin/env python3
"""
live.launch.py — the live camera (live_camera.py) configured from the installation.

Settings (environment, /etc/navera/navera.env or the web page's settings.env):
    NAVERA_CAMERA_INPUT        usb | csi | ros                    (default usb)
    NAVERA_CAMERA_DEVICE       /dev/videoN for usb                 (default /dev/video0)
    NAVERA_CAMERA_TOPIC        sensor_msgs/Image topic for ros
    NAVERA_CAMERA_SIZE         WIDTHxHEIGHT                        (default 1920x1080)
    NAVERA_CAMERA_FPS          frames offered per second           (default 1)
    NAVERA_CAMERA_CALIBRATION  calibration YAML (navera_tools/calibrate_camera.py)
    NAVERA_CAMERA_HFOV_DEG     ideal lens, when not calibrated
    NAVERA_CAMERA_MOUNT_RPY    camera mounting roll,pitch,yaw (deg)
    NAVERA_CAMERA_LATENCY_S    exposure -> grab delay
    NAVERA_CAMERA_MAX_TILT_DEG frames tilted more are not compared (default 45)
    NAVERA_CAMERA_GIMBAL       true: the camera is held level (only the heading is used)
    NAVERA_GROUND_ALTITUDE_M   site elevation (else the first GPS fix)
    NAVERA_SENSOR_SOURCE       box | vehicle | ros: where attitude / height / GPS come
                               from (navera_common.vehicle.sensor_topics)

Arguments: camera_type (day|thermal), ns (topic namespace), ready_topic.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from navera_common.vehicle import live_camera_params


def _nodes(context):
    params = live_camera_params()
    params.update(camera_type=LaunchConfiguration('camera_type').perform(context),
                  ready_topic=LaunchConfiguration('ready_topic').perform(context),
                  frame_id=f"{LaunchConfiguration('ns').perform(context)}_camera_link")
    return [
        LogInfo(msg=f"live camera: {params['input']} {params.get('device') if params['input'] == 'usb' else ''} "
                    f"{params['width']}x{params['height']}, attitude from {params['imu_topic']}, "
                    f"lens {'calibrated' if params['calibration_file'] else 'IDEAL (not calibrated)'}"),
        Node(package='camera_pkg', executable='live_camera.py', name='live_camera',
             namespace=LaunchConfiguration('ns'), output='screen',
             on_exit=Shutdown(reason='live camera exited'),
             parameters=[params]),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('camera_type', default_value='day'),
        DeclareLaunchArgument('ns', default_value='day'),
        DeclareLaunchArgument('ready_topic', default_value='/day/localizer_ready'),
        OpaqueFunction(function=_nodes),
    ])
