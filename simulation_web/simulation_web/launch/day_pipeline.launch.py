#!/usr/bin/env python3
"""day_pipeline.launch.py — the NAVERA "day" localization pipeline, WITHOUT a bridge.

  camera_pkg (day, /day/* test images)
    → day_subscriber (DayLocalizer, DINOv2, GPU)
      → /day/position_estimate + /day/day_status

Start the bridge separately (bridge.launch.py) so that only one process binds the
HTTP port and several pipelines can run side by side. day_sim.launch.py remains as
a wrapper that starts this pipeline plus a bridge, for the single-command workflow.

VRAM: this pipeline loads DINOv2. Do NOT run it alongside night_pipeline — DINOv2
and STHN together do not fit in the Orin Nano's 8 GB shared envelope.

Examples:
  ros2 launch simulation_web day_pipeline.launch.py
  ros2 launch simulation_web day_pipeline.launch.py conf_threshold:=0.6
  ros2 launch simulation_web day_pipeline.launch.py default_gps_valid:=false  # GPS-denied
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo, DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from navera_common.vehicle import max_speed_mps_from_env, max_speed_params, shadow_mode_from_env


def generate_launch_description():
    camera_share = get_package_share_directory('camera_pkg')
    day_data = os.path.join(camera_share, 'data', 'day')

    conf_threshold = LaunchConfiguration('conf_threshold')

    return LaunchDescription([
        LogInfo(msg='WARNING: NAVERA_MAX_SPEED_KMH is not set in /etc/navera/navera.env — day vision uses its '
                    'default speed limit; set the vehicle\'s maximum speed (km/h).')
        if not max_speed_params() else LogInfo(msg=f'vehicle maximum speed: {max_speed_mps_from_env():.1f} m/s'),
        DeclareLaunchArgument('conf_threshold', default_value='0.75'),
        # track filter — toggle/tune without rebuild
        DeclareLaunchArgument('antijump_enabled',    default_value='true'),
        DeclareLaunchArgument('max_consecutive_rejects', default_value='3'),
        # the node's default (120 s): dead-reckoning also stops once its stated accuracy passes
        # dead_reckon_max_sigma_m (900 m, ~80 s at 10 m/s); 30 s (a retrieval-era value) cut the
        # position in the middle of a 30-60 s cloud bank (Isaac Sim closed loop, F32)
        DeclareLaunchArgument('max_dead_reckon_s',       default_value='120.0'),
        # Test flights: vision runs while GPS is valid, for measurement.
        DeclareLaunchArgument('shadow_mode', default_value=shadow_mode_from_env()),
        DeclareLaunchArgument('allow_global_search',     default_value='false'),
        # Day camera horizontal field of view (deg), from NAVERA_DAY_HFOV_DEG: with the frame
        # altitude it gives the frame scale local matching needs. Unset = DINOv2 retrieval.
        DeclareLaunchArgument('camera_hfov_deg', default_value=(os.environ.get('NAVERA_DAY_HFOV_DEG') or 'nan')),
        # NAVERA_DAY_MATCHER: auto (DISK + LightGlue when it loads, else SIFT) | learned | local | retrieval
        DeclareLaunchArgument('matcher', default_value=(os.environ.get('NAVERA_DAY_MATCHER') or 'auto')),
        # default_gps_valid: mirrors day.yaml ('true'), so this argument changes
        # nothing by itself — it forwards day.launch.py's argument up to this level,
        # which is what lets the GPS-denied regime be MEASURED without editing a
        # config file shared with the live service.
        #   'true'  → CSV rows carrying lat/lon are replayed (MODE_REPLAYED, no DINOv2)
        #   'false' → every frame is GPS-denied: DINOv2 runs, the 25 rows with
        #             lat/lon become measurable ground truth.
        DeclareLaunchArgument('default_gps_valid', default_value='true'),
        # Replay data. $NAVERA_DAY_CSV / $NAVERA_DAY_IMAGES_DIR let a machine keep
        # the frames outside the install tree (e.g. on an external data disk).
        DeclareLaunchArgument('csv_path', default_value=os.environ.get(
            'NAVERA_DAY_CSV', os.path.join(day_data, 'flight_demo.csv'))),
        DeclareLaunchArgument('images_dir', default_value=os.environ.get(
            'NAVERA_DAY_IMAGES_DIR', day_data)),

        # 1) Camera publisher (day namespace, test images)
        # NAVERA_CAMERA=live: the real camera (camera_pkg live.launch.py, settings in
        # navera.env); otherwise the replay camera below (recorded frames).
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(camera_share, 'launch', 'live.launch.py')),
            # a camera that exits (stalled, unplugged) is started again alone: the day node goes on
            # dead-reckoning meanwhile (B23)
            launch_arguments={'camera_type': 'day', 'ns': 'day',
                              'ready_topic': '/day/localizer_ready', 'respawn': 'true'}.items(),
        ) if (os.environ.get('NAVERA_CAMERA') or 'replay') == 'live' else IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(camera_share, 'launch', 'day.launch.py')
            ),
            launch_arguments={
                'start_paused': 'true',
                'fps': '0.5',
                'start_delay_s': '7.0',
                'flow_control': 'ack',   # back-pressure: next frame only after subscriber ack
                'csv_path': LaunchConfiguration('csv_path'),
                'images_dir': LaunchConfiguration('images_dir'),
                'default_gps_valid': LaunchConfiguration('default_gps_valid'),
            }.items(),
        ),

        # 2) Day localization subscriber (GPU)
        Node(
            package='day_pkg',
            executable='day_subscriber.py',
            name='day_subscriber',
            output='screen',
            # Started again alone, 1 s after it exits (crash, OOM kill), B23: the camera keeps its
            # stream open and sends the next frame as soon as the new node says it is ready
            # (live_camera._on_ready), the output bridges the gap from the last position it sent.
            # A whole-pipeline restart by systemd took 25 s in flight (camera reopened, models
            # reloaded twice over): longer than the output's 10 s bridge — the copter landed.
            # The replay camera (tests, simulation) still ends the launch when it exits.
            respawn=True,
            respawn_delay=1.0,
            parameters=[{
                'conf_threshold': conf_threshold,
                'image_topic':  '/day/image_raw',
                'meta_topic':   '/day/frame_meta',
                'fix_topic':    '/day/position_estimate',
                'status_topic': '/day/day_status',
                'antijump_enabled':    LaunchConfiguration('antijump_enabled'),
                'max_consecutive_rejects': LaunchConfiguration('max_consecutive_rejects'),
                'max_dead_reckon_s':       LaunchConfiguration('max_dead_reckon_s'),
                'shadow_mode':       LaunchConfiguration('shadow_mode'),
                'allow_global_search':     LaunchConfiguration('allow_global_search'),
                # day camera's horizontal field of view: the frame scale for local matching
                'camera_hfov_deg': ParameterValue(LaunchConfiguration('camera_hfov_deg'), value_type=float),
                'matcher': LaunchConfiguration('matcher'),
            }, max_speed_params()],    # the vehicle's maximum speed: vision motion gate
        ),
    ])
