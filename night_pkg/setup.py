import os
from glob import glob
from setuptools import setup, find_packages

package_name = 'night_pkg'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('night_pkg/launch/*.py')),
]

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'STHN', 'STHN.*']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy', 'opencv-python', 'numpy', 'torch', 'safetensors'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA night STHN ROS2 subscriber',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'night_subscriber.py=night_pkg.nodes.night_subscriber:main',
        ],
    },
)
