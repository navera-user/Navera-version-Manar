#!/usr/bin/env python3
"""
night_sim.launch.py — full NAVERA "night" simulation in one command (Option A).

Clone de day_sim.launch.py, mais la localisation GPS-denied passe par STHN.
Démarre toute la chaîne ROS→web :
  camera_pkg (thermal, /thermal/* test images)
    → night_subscriber (NightLocalizer / STHN, GPU)
      → /night/position_estimate + /night/night_status
        → navera_web_bridge (HTTP :8181 : navera.html + tiles + gps_status.json)

Ouvre http://<jetson>:8181/ , choisis le mode, place le Point A, lance — le marker
drone bouge sur la map .mbtiles depuis la localisation ROS réelle.

Examples:
  ros2 launch simulation_web night_sim.launch.py
  ros2 launch simulation_web night_sim.launch.py web_port:=8181 conf_threshold:=0.30
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
        DeclareLaunchArgument('web_port',       default_value='8181'),   # même URL que day/cn (un mode à la fois)
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),   # seuil conf STHN
        DeclareLaunchArgument('dr_step_min_m',  default_value='120.0'),  # plancher dead-reckon
        # patch_size STHN : 512 fait OOM (NvMap ENOMEM) sur Orin Nano 8 Go ;
        # 256 divise la VRAM des volumes de corrélation IHN par ~4.
        DeclareLaunchArgument('patch_size',     default_value='256'),
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
        DeclareLaunchArgument('mixed_precision', default_value='true'),
        DeclareLaunchArgument('sthn_dir',
            default_value='/home/navera/isaac_ros_common/night_pkg/STHN'),
        DeclareLaunchArgument('weights',
            default_value='/home/navera/isaac_ros_common/night_pkg/STHN/weights/one_stage/model.safetensors'),

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
                'default_gps_valid': 'true',      # CSV lat/lon → GPS-known (direct nav)
                'wait_for_ready': 'true',         # frame 1 attend STHN chargé
                'ready_topic': '/night/localizer_ready',
                'min_frame_interval': '1.0',      # cadence visible frame-par-frame
                'csv_path': os.path.join(camera_share, 'data', 'thermal', 'flight_ready.csv'),
            }.items(),
        ),

        # 2) Night localization subscriber (STHN, GPU)
        Node(
            package='night_pkg',
            executable='night_subscriber.py',
            name='night_subscriber',
            output='screen',
            parameters=[{
                'sthn_dir':       LaunchConfiguration('sthn_dir'),
                'weights':        LaunchConfiguration('weights'),
                'mbtiles':        mbtiles_path,
                'conf_threshold': conf_threshold,
                'patch_size':     LaunchConfiguration('patch_size'),
                'dr_step_min_m':  LaunchConfiguration('dr_step_min_m'),
                # value_type=str : sinon launch_ros coerce 'true'→bool et le nœud
                # (qui déclare/parse mixed_precision en string) crashe au démarrage.
                'mixed_precision': ParameterValue(
                    LaunchConfiguration('mixed_precision'), value_type=str),
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

        # 3) ROS→web bridge (HTTP :8181 — navera.html + tiles + gps_status.json)
        Node(
            package='simulation_web',
            executable='navera_web_bridge.py',
            name='navera_web_bridge',
            output='screen',
            parameters=[{
                'status_topic': '/night/night_status',
                'fix_topic':    '/night/position_estimate',
                'start_topic':  '/thermal/camera/start',
                'mbtiles_path': mbtiles_path,
                'web_port':     web_port,
            }],
        ),
    ])
