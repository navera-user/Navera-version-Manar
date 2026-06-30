from setuptools import setup, find_packages
from glob import glob
import os

package_name = 'day_pkg'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'data', 'resources']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/day_pkg']),
        ('share/day_pkg', ['package.xml']),
        ('share/day_pkg/launch', glob('day_pkg/launch/*.py')),
    ],
    install_requires=['setuptools', 'rclpy', 'launch', 'launch-ros'],
    zip_safe=True,
    author='Navera',
    author_email='navera@example.com',
    maintainer='Navera',
    maintainer_email='navera@example.com',
    description='Day Mode ROS2 Package - NVIDIA Isaac',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'day_subscriber.py=day_pkg.nodes.day_subscriber:main',
        ],
    },
)
