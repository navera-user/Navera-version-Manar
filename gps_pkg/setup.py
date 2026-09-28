import os
from glob import glob
from setuptools import setup, find_packages

package_name = 'gps_pkg'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('gps_pkg/launch/*.py')),
    ('share/' + package_name + '/config', glob('gps_pkg/config/*.yaml')),
]

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'config']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy', 'pyserial', 'pynmea2'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA GPS sensor driver (NMEA → /navera/sensors/gps_*)',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'gps_node.py=gps_pkg.nodes.gps_node:main',
        ],
    },
)
