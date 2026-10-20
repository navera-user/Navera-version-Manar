from glob import glob
from setuptools import setup, find_packages

package_name = 'rtc_pkg'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('rtc_pkg/launch/*.py')),
    ('share/' + package_name + '/config', glob('rtc_pkg/config/*.yaml')),
]

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'config']),
    data_files=data_files,
    # Runtime pip deps (DS3231 via Adafruit Blinka) are NOT listed here on purpose:
    # they are provided by the image (Dockerfile.navera) and by the host for the
    # navera-rtc systemd service. Listing them would make `colcon build` try to
    # resolve them from PyPI on a machine that has no network.
    #   adafruit-blinka, adafruit-circuitpython-ds3231, adafruit-register
    install_requires=['setuptools', 'rclpy'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA RTC driver — DS3231 over I2C → /navera/sensors/rtc_time',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'rtc_node.py=rtc_pkg.nodes.rtc_node:main',
        ],
    },
)
