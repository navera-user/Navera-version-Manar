from glob import glob

from setuptools import find_packages, setup

package_name = 'navera_output'

setup(
    name=package_name,
    version='0.3.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'pyserial', 'pymavlink'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA output to the vehicle: NMEA GPS emulation and MAVLink GPS_INPUT',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'vehicle_output_node.py=navera_output.nodes.vehicle_output_node:main',
            'vehicle_link_node.py=navera_output.nodes.vehicle_link_node:main',
        ],
    },
)
