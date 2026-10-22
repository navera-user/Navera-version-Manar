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
    description='NAVERA GPS sources (NMEA / UBX, DroneCAN, vehicle / ROS GPS → /navera/sensors/gps_*)',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'gps_node.py=gps_pkg.nodes.gps_node:main',
            'ros_gps_node.py=gps_pkg.nodes.ros_gps_node:main',
            'dronecan_gps_node.py=gps_pkg.nodes.dronecan_gps_node:main',
        ],
    },
)
