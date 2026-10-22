#!/usr/bin/env python3
"""insta360.launch.py — the Insta360 kit (camera_pkg insta360_node.py): the One R in USB Android mode
as the day camera's straight-down view AND the IMU / attitude, from ONE process.

The installation settings (navera_common.vehicle.insta360_kit_params) give the mount and the view:
NAVERA_INSTA360_MOUNT_AXES, NAVERA_INSTA360_MOUNT_RPY, NAVERA_INSTA360_VIEW_SIZE,
NAVERA_INSTA360_VIEW_HFOV_DEG, NAVERA_INSTA360_LENS, NAVERA_INSTA360_IMU.

Examples:
  ros2 launch camera_pkg insta360.launch.py                       # the camera over USB (boot service)
  ros2 launch camera_pkg insta360.launch.py source:=replay replay_path:=$HOME/navera-field/2026-10-20_1150/raw
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from navera_common.vehicle import insta360_kit_params

ARGS = [
    ('source', 'live', 'live (the camera over USB) or replay (a raw recording)'),
    ('replay_path', '', 'raw recording: a <test>/raw folder or one raw360_NNNN.bin'),
    ('replay_rate', '1.0', 'replay pacing: 1 real time, 0 as fast as possible'),
    ('replay_loop', 'false', 'start the recording again at its end'),
    ('exit_at_end', 'true', 'replay: the node ends with the recording'),
]


def _nodes(context):
    cfg = os.path.join(get_package_share_directory('camera_pkg'), 'config', 'insta360.yaml')
    kit = insta360_kit_params()
    args = {n: LaunchConfiguration(n).perform(context) for n, _, _ in ARGS}
    args['replay_rate'] = float(args['replay_rate'])
    args['replay_loop'] = args['replay_loop'] == 'true'
    args['exit_at_end'] = args['exit_at_end'] == 'true'
    return [
        LogInfo(msg=f"Insta360 kit ({args['source']}): mount {kit['mount_axes']}, view "
                    f"{kit['view_width']}x{kit['view_height']} {kit['view_hfov_deg']:g} deg"),
        Node(package='camera_pkg', executable='insta360_node.py', name='insta360', output='screen',
             on_exit=Shutdown(reason='insta360 node exited'),
             parameters=[cfg, kit, args]),
    ]


def generate_launch_description():
    return LaunchDescription([DeclareLaunchArgument(n, default_value=d, description=h) for n, d, h in ARGS]
                             + [OpaqueFunction(function=_nodes)])
