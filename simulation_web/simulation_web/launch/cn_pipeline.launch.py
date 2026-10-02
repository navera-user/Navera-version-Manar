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

Two modes. With NAVERA_STAR_CAMERA_INPUT set, a real star camera (live_camera with
the NAVERA_STAR_CAMERA_* settings): attitude from the IMU at each exposure (no IMU:
no position), time from the RTC, prior from NAVERA's last position. Without it, the
bundled etoiles.jpeg sample with the tilt / azimuth / utc_time / area it was taken
with (launch constants below) — a demonstration, not navigation. Celestial position error is
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
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from navera_common.vehicle import imu_topic_params
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    camera_share = get_package_share_directory('camera_pkg')
    # NAVERA_STAR_CAMERA_INPUT set: a real star camera (live_camera, NAVERA_STAR_CAMERA_*
    # settings), attitude from the IMU at each exposure, time from the RTC/system clock,
    # prior from NAVERA's last position. Otherwise: the bundled sample sky, with the
    # attitude, time and area it was taken with (demonstration only).
    live = bool((os.environ.get('NAVERA_STAR_CAMERA_INPUT') or '').strip())
    sample = (lambda value: 'nan' if live else value)


    return LaunchDescription([
        DeclareLaunchArgument('min_log_odds',   default_value='20.7'),
        DeclareLaunchArgument('camera_fov_deg', default_value=(
            (os.environ.get('NAVERA_STAR_CAMERA_HFOV_DEG') or 'nan') if live else 'nan')),
        # Celestial solver config (defaults match the bundled etoiles.jpeg sample)
        DeclareLaunchArgument('solver_mode', default_value='geoloc'),
        DeclareLaunchArgument('tilt',        default_value=sample('75.46')),
        DeclareLaunchArgument('azimuth',     default_value=sample('283.18')),
        DeclareLaunchArgument('utc_time',    default_value='' if live else '2026-03-10 20:20:00'),
        # Operating-area prior (Sousse) — picks between the two positions a sky
        # direction is consistent with.
        DeclareLaunchArgument('prior_lat',   default_value=sample('35.83')),
        DeclareLaunchArgument('prior_lon',   default_value=sample('10.64')),
        # Star-camera attitude from the IMU (when frame_meta has none): mounting,
        # magnetic declination, and the IMU's attitude accuracy (sets the stated
        # accuracy: ~111 km per degree). See cn_pkg/README.md.
        DeclareLaunchArgument('camera_mount_elevation_deg', default_value=(os.environ.get('NAVERA_STAR_CAMERA_ELEVATION_DEG') or '90.0')),
        DeclareLaunchArgument('camera_mount_azimuth_deg', default_value=(os.environ.get('NAVERA_STAR_CAMERA_AZIMUTH_DEG') or '0.0')),
        DeclareLaunchArgument('magnetic_declination_deg', default_value=(os.environ.get('NAVERA_MAGNETIC_DECLINATION_DEG') or '0.0')),
        DeclareLaunchArgument('attitude_sigma_deg', default_value=(os.environ.get('NAVERA_ATTITUDE_SIGMA_DEG') or 'nan')),

        # 1) Star camera: live, or the bundled sample (celestial namespace)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(camera_share, 'launch', 'live.launch.py')),
            launch_arguments={'camera_type': 'star', 'ns': 'celestial', 'settings': 'NAVERA_STAR_CAMERA_',
                              'wait_for_ready': 'false'}.items(),
        ) if live else IncludeLaunchDescription(
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
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[{
                'min_log_odds': ParameterValue(LaunchConfiguration('min_log_odds'), value_type=float),
                'camera_fov_deg': ParameterValue(LaunchConfiguration('camera_fov_deg'), value_type=float),
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
                'camera_mount_elevation_deg': ParameterValue(LaunchConfiguration('camera_mount_elevation_deg'), value_type=float),
                'camera_mount_azimuth_deg': ParameterValue(LaunchConfiguration('camera_mount_azimuth_deg'), value_type=float),
                'magnetic_declination_deg': ParameterValue(LaunchConfiguration('magnetic_declination_deg'), value_type=float),
                'attitude_sigma_deg': ParameterValue(LaunchConfiguration('attitude_sigma_deg'), value_type=float),
            }, imu_topic_params()],          # the star camera's attitude: box, vehicle or ROS IMU
        ),
    ])
