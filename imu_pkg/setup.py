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
    # Runtime pip deps (BNO085 via Adafruit Blinka) are NOT listed here on purpose:
    # they are provided by the image (Dockerfile.navera) and by the host for the
    # navera-imu systemd service. Listing them would make `colcon build` try to
    # resolve them from PyPI on a machine that has no network.
    #   Jetson.GPIO>=2.1.12, adafruit-blinka, adafruit-circuitpython-bno08x
    install_requires=['setuptools', 'rclpy'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA IMU sensor driver — BNO085 9-DoF over I2C → /navera/sensors/imu',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'imu_node.py=imu_pkg.nodes.imu_node:main',
        ],
    },
)
