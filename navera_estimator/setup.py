import os
from glob import glob
from setuptools import setup, find_packages

package_name = 'navera_estimator'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('navera_estimator/launch/*.py')),
    ('share/' + package_name + '/config', glob('navera_estimator/config/*.yaml')),
]

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'config']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA position arbiter (per-source PositionEstimate → /navera/position + /navera/nav_status)',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'estimator_node.py=navera_estimator.nodes.estimator_node:main',
        ],
    },
)
