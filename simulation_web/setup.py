from setuptools import setup, find_packages
from glob import glob

package_name = 'simulation_web'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Launch files - IMPORTANT!
        ('share/' + package_name + '/launch',
            glob('simulation_web/launch/*.py')),
        # Resources
        ('share/' + package_name + '/resources',
            glob('simulation_web/resources/*.html')),
        ('share/' + package_name + '/resources/leaflet',
            glob('simulation_web/resources/leaflet/*')),
        # Data
        ('share/' + package_name + '/data',
            glob('simulation_web/data/*')),
    ],
    install_requires=['setuptools', 'rclpy', 'launch', 'launch-ros'],
    zip_safe=True,
    author='IRIS Systems',
    author_email='contact@iris-systems.tn',
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA web bridge: operator view, dashboard, map tiles, launch files',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'navera_web_bridge.py=simulation_web.scripts.navera_web_bridge:main',
            'navera_stellar_bridge.py=simulation_web.scripts.navera_stellar_bridge:main',
        ],
    },
)
