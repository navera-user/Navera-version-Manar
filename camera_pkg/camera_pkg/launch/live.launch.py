#!/usr/bin/env python3
"""
live.launch.py — the live camera (live_camera.py) configured from the installation.

Settings (environment, /etc/navera/navera.env or the web page's settings.env):
    NAVERA_CAMERA_INPUT        usb | csi | gst | ros | insta360   (default usb)
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
    NAVERA_SENSOR_SOURCE       box | vehicle | ros | insta360: where attitude / height / GPS come
                               from (navera_common.vehicle.sensor_topics)

Arguments: camera_type (day|thermal|star), ns (topic namespace), ready_topic,
settings (NAVERA_CAMERA_ or NAVERA_STAR_CAMERA_), wait_for_ready.
NAVERA_CAMERA_INPUT may also be gst (NAVERA_CAMERA_GST_PIPELINE: any GStreamer source).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from navera_common.vehicle import live_camera_params


def _lens_text(params) -> str:
    if params['calibration_file']:
        return 'calibrated'
    return 'Insta360 kit view (ideal by construction)' if params['input'] == 'insta360' else 'IDEAL (not calibrated)'


def _nodes(context):
    params = live_camera_params(prefix=LaunchConfiguration('settings').perform(context))
    params.update(camera_type=LaunchConfiguration('camera_type').perform(context),
                  ready_topic=LaunchConfiguration('ready_topic').perform(context),
                  wait_for_ready=LaunchConfiguration('wait_for_ready').perform(context) == 'true',
                  frame_id=f"{LaunchConfiguration('ns').perform(context)}_camera_link")
    return [
        LogInfo(msg=f"live camera: {params['input']} {params.get('device') if params['input'] == 'usb' else ''} "
                    f"{params['width']}x{params['height']}, attitude from {params['imu_topic']}, "
                    f"lens {_lens_text(params)}"),
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
        # NAVERA_STAR_CAMERA_ for the celestial pipeline's star camera
        DeclareLaunchArgument('settings', default_value='NAVERA_CAMERA_'),
        DeclareLaunchArgument('wait_for_ready', default_value='true'),
        OpaqueFunction(function=_nodes),
    ])
