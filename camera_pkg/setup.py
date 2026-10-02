import os
from glob import glob
from setuptools import setup, find_packages

package_name = 'camera_pkg'

# Static data files: package.xml, resource marker, launch, config
data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('camera_pkg/launch/*.py')),
    ('share/' + package_name + '/config', glob('camera_pkg/config/*.yaml')),
]

# Data files: walk the data/ tree and preserve sub-directory structure
data_root = 'camera_pkg/data'
if os.path.isdir(data_root):
    for dirpath, _dirnames, filenames in os.walk(data_root):
        files_here = [os.path.join(dirpath, f) for f in filenames if not f.startswith('.')]
        if not files_here:
            continue
        # Mirror the relative path from camera_pkg/data/... into share/camera_pkg/data/...
        rel = os.path.relpath(dirpath, 'camera_pkg')   # e.g. "data/celestial"
        install_dir = 'share/' + package_name + '/' + rel
        data_files.append((install_dir, files_here))

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'data', 'resources', 'config']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy', 'launch', 'launch-ros'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='Camera / frame source ROS2 package for NAVERA (replaces PC-Nour)',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'camera_publisher.py=camera_pkg.nodes.camera_publisher:main',
            'live_camera.py=camera_pkg.nodes.live_camera:main',
        ],
    },
)
