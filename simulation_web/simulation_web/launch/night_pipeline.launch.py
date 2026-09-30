#!/usr/bin/env python3
"""
night_pipeline.launch.py — the NAVERA "night" localization pipeline, WITHOUT a bridge.

  camera_pkg (thermal, /thermal/* test images)
    → night_subscriber (NightLocalizer / STHN, GPU)
      → /night/position_estimate + /night/night_status

Start the bridge separately (bridge.launch.py). night_sim.launch.py remains as a
wrapper that starts this pipeline plus a bridge, for the single-command workflow.

VRAM: this pipeline loads STHN. Do NOT run it alongside day_pipeline — STHN and
DINOv2 together do not fit in the Orin Nano's 8 GB shared envelope.

Examples:
  ros2 launch simulation_web night_pipeline.launch.py
  ros2 launch simulation_web night_pipeline.launch.py conf_threshold:=0.30
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    camera_share = get_package_share_directory('camera_pkg')

    default_mbtiles = os.environ.get('NAVERA_MBTILES', '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles')

    mbtiles_path   = LaunchConfiguration('mbtiles_path')
    conf_threshold = LaunchConfiguration('conf_threshold')

    return LaunchDescription([
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),   # seuil conf STHN
        DeclareLaunchArgument('max_dead_reckon_s', default_value='30.0'),
        # Test flights: vision runs while GPS is valid, for measurement.
        DeclareLaunchArgument('shadow_mode', default_value='false'),
        # Replay data ($NAVERA_THERMAL_CSV / $NAVERA_THERMAL_IMAGES_DIR, e.g. on the data disk)
        # and whether CSV lat/lon rows count as GPS (replay only).
        DeclareLaunchArgument('csv_path', default_value=os.environ.get(
            'NAVERA_THERMAL_CSV', os.path.join(camera_share, 'data', 'thermal', 'flight_ready.csv'))),
        DeclareLaunchArgument('images_dir', default_value=os.environ.get(
            'NAVERA_THERMAL_IMAGES_DIR', os.path.join(camera_share, 'data', 'thermal'))),
        DeclareLaunchArgument('default_gps_valid', default_value='true'),
        # VRAM Jetson 8 Go partagée : si STHN OOM dès l'init du contexte CUDA
        # (network.py:168, torch.zeros().to(device) — alloc minuscule qui échoue
        # car la VRAM est déjà saturée), forcer le night STHN sur CPU avec
        #   cuda_visible_devices:=''
        # '' = CPU (aucun OOM GPU) ; '0' = GPU (défaut, comportement inchangé).
        # NB : ça pilote CUDA_VISIBLE_DEVICES du SEUL night_subscriber ; le day
        # garde le GPU. CPU est OK ici (back-pressure + faux thermique → DR).
        DeclareLaunchArgument('cuda_visible_devices', default_value='0'),
        # A) allocateur CUDA : 'expandable_segments:True' défragmente (débloque cuSOLVER
        #    + réduit l'OOM forward sur ~2 Go libres). '' pour désactiver (tester A seul/off).
        DeclareLaunchArgument('cuda_alloc_conf', default_value='expandable_segments:True'),
        # B) fp16 sur le forward STHN (fnet1 + update_block_4, ~2× VRAM). 'false' pour désactiver.
        # fp16 measured on the Orin: same accuracy, no speed or memory gain → off.
        DeclareLaunchArgument('mixed_precision', default_value='false'),
        # Thermal camera horizontal field of view (deg): with the frame altitude it
        # brings each frame to STHN's scale. Unset = no night position (LOC-16).
        DeclareLaunchArgument('camera_hfov_deg',
            default_value=os.environ.get('NAVERA_THERMAL_HFOV_DEG', 'nan')),
        DeclareLaunchArgument('sthn_dir',
            default_value=os.environ.get('NAVERA_STHN_DIR', '/home/navera/isaac_ros_common/night_pkg/STHN')),
        DeclareLaunchArgument('weights',
            default_value=os.environ.get('NAVERA_STHN_WEIGHTS', '/home/navera/isaac_ros_common/night_pkg/STHN/weights/one_stage/model.safetensors')),

        # 1) Camera publisher (thermal namespace, test images) — back-pressure + handshake
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(camera_share, 'launch', 'thermal.launch.py')
            ),
            launch_arguments={
                'start_paused': 'true',
                'fps': '0.5',
                'start_delay_s': '7.0',
                'flow_control': 'ack',            # next frame only after night_subscriber ack
                'default_gps_valid': LaunchConfiguration('default_gps_valid'),
                'wait_for_ready': 'true',         # frame 1 attend STHN chargé
                'ready_topic': '/night/localizer_ready',
                'min_frame_interval': '1.0',      # cadence visible frame-par-frame
                'csv_path': LaunchConfiguration('csv_path'),
                'images_dir': LaunchConfiguration('images_dir'),
            }.items(),
        ),

        # 2) Night localization subscriber (STHN, GPU)
        Node(
            package='night_pkg',
            executable='night_subscriber.py',
            name='night_subscriber',
            output='screen',
            # Any node exiting ends the launch, so the systemd unit
            # (Restart=always) restarts the whole pipeline.
            on_exit=Shutdown(reason='node exited'),
            parameters=[{
                'sthn_dir':       LaunchConfiguration('sthn_dir'),
                'weights':        LaunchConfiguration('weights'),
                'mbtiles':        mbtiles_path,
                'conf_threshold': conf_threshold,
                'max_dead_reckon_s':  LaunchConfiguration('max_dead_reckon_s'),
                'shadow_mode':  LaunchConfiguration('shadow_mode'),
                # value_type=str : sinon launch_ros coerce 'true'→bool et le nœud
                # (qui déclare/parse mixed_precision en string) crashe au démarrage.
                'mixed_precision': ParameterValue(
                    LaunchConfiguration('mixed_precision'), value_type=str),
                'camera_hfov_deg': ParameterValue(
                    LaunchConfiguration('camera_hfov_deg'), value_type=float),
                'image_topic':    '/thermal/image_raw',
                'meta_topic':     '/thermal/frame_meta',
                'fix_topic':      '/night/position_estimate',
                'status_topic':   '/night/night_status',
                'done_topic':     '/thermal/frame_done',
                'ready_topic':    '/night/localizer_ready',
            }],
            # CUDA_VISIBLE_DEVICES posé AVANT l'import torch du process →
            # '' rend torch.cuda.is_available()==False → night_localizer DEVICE/
            # self.device = cpu de façon cohérente (sans toucher network.py).
            additional_env={
                'CUDA_VISIBLE_DEVICES':    LaunchConfiguration('cuda_visible_devices'),
                'PYTORCH_CUDA_ALLOC_CONF': LaunchConfiguration('cuda_alloc_conf'),
            },
        ),
    ])
