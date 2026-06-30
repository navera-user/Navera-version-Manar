import os
from glob import glob
from setuptools import setup, find_packages

package_name = 'imu_pkg'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('imu_pkg/launch/*.py')),
    ('share/' + package_name + '/config', glob('imu_pkg/config/*.yaml')),
]

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'config']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy', 'smbus2'],
    zip_safe=True,
    maintainer='Navera',
    maintainer_email='navera@example.com',
    description='NAVERA IMU sensor driver (MPU6050+BMP180+QMC5883L → /navera/sensors/imu, /mag, /altitude_baro)',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'imu_node.py=imu_pkg.nodes.imu_node:main',
        ],
    },
)
