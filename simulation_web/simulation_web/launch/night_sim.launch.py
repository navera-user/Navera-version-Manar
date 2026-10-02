#!/usr/bin/env python3
"""
night_sim.launch.py — full NAVERA "night" simulation in one command.

Thin wrapper over the two halves of the chain:
  night_pipeline.launch.py   camera_pkg (thermal) → night_subscriber (STHN, GPU)
  bridge.launch.py           navera_web_bridge (HTTP :8181)

It exists so the single-command workflow keeps working. The composition itself
lives in the two included files — nothing is declared twice here.

Ouvre http://<jetson>:8181/ , choisis le mode, place le Point A, lance — le marker
drone bouge sur la map .mbtiles depuis la localisation ROS réelle.

To run two pipelines side by side, do NOT use this file: start each pipeline without
a bridge (*_pipeline.launch.py) plus exactly one bridge.launch.py, otherwise the
second bridge dies binding the same HTTP port. Note that night + day is the one
combination that does not fit anyway: STHN and DINOv2 together exceed the Orin
Nano's 8 GB shared envelope.

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


def generate_launch_description():
    web_share = get_package_share_directory('simulation_web')

    default_mbtiles = (os.environ.get('NAVERA_MBTILES') or '/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles')

    # Public interface: same argument names and same defaults as before the split, so
    # every existing invocation (docs, CLI overrides) keeps working. The STHN tuning
    # knobs (cuda_*, mixed_precision, weights) are documented in
    # night_pipeline.launch.py, which is where they are consumed.
    return LaunchDescription([
        DeclareLaunchArgument('web_port',       default_value='8181'),   # même URL que day/cn (un mode à la fois)
        DeclareLaunchArgument('mbtiles_path',   default_value=default_mbtiles),
        DeclareLaunchArgument('conf_threshold', default_value='0.30'),   # seuil conf STHN
        DeclareLaunchArgument('max_dead_reckon_s', default_value='30.0'),
        DeclareLaunchArgument('cuda_visible_devices', default_value='0'),
        DeclareLaunchArgument('cuda_alloc_conf', default_value='expandable_segments:True'),
        DeclareLaunchArgument('mixed_precision', default_value='false'),
        DeclareLaunchArgument('sthn_dir',
            default_value=(os.environ.get('NAVERA_STHN_DIR') or '/home/navera/isaac_ros_common/night_pkg/STHN')),
        DeclareLaunchArgument('weights',
            default_value=(os.environ.get('NAVERA_STHN_WEIGHTS') or '/home/navera/isaac_ros_common/night_pkg/STHN/weights/one_stage/model.safetensors')),

        # 1) Localization pipeline: camera(thermal) + night_subscriber (STHN)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(web_share, 'launch', 'night_pipeline.launch.py')
            ),
            launch_arguments={
                'mbtiles_path':          LaunchConfiguration('mbtiles_path'),
                'conf_threshold':        LaunchConfiguration('conf_threshold'),
                'max_dead_reckon_s':         LaunchConfiguration('max_dead_reckon_s'),
                'cuda_visible_devices':  LaunchConfiguration('cuda_visible_devices'),
                'cuda_alloc_conf':       LaunchConfiguration('cuda_alloc_conf'),
                'mixed_precision':       LaunchConfiguration('mixed_precision'),
                'sthn_dir':              LaunchConfiguration('sthn_dir'),
                'weights':               LaunchConfiguration('weights'),
            }.items(),
        ),

        # 2) ROS→web bridge, pointed at the night pipeline. The topics are spelled out
        # even though status/fix also happen to be the bridge's defaults for day:
        # night_sim must keep driving night if those defaults ever move. start_topic
        # is the thermal camera — the bridge publishes it on Launch Mission.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(web_share, 'launch', 'bridge.launch.py')
            ),
            launch_arguments={
                'status_topic': '/night/night_status',
                'fix_topic':    '/night/position_estimate',
                'start_topic':  '/thermal/camera/start',
                'mbtiles_path': LaunchConfiguration('mbtiles_path'),
                'web_port':     LaunchConfiguration('web_port'),
            }.items(),
        ),
    ])
