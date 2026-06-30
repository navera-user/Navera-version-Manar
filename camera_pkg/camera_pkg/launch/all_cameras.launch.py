#!/usr/bin/env python3
"""
all_cameras.launch.py — start thermal + celestial + day cameras together.

Each one publishes on its own namespace:
  /thermal/image_raw    /thermal/gps    /thermal/frame_meta
  /celestial/image_raw  /celestial/gps  /celestial/frame_meta
  /day/image_raw        /day/gps        /day/frame_meta
"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    pkg_share = get_package_share_directory('camera_pkg')
    return LaunchDescription([
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'thermal.launch.py'))),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'celestial.launch.py'))),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'day.launch.py'))),
    ])
