import os
import sys
from glob import glob
from setuptools import setup, find_packages

package_name = 'cn_pkg'

# Python site-packages dir for THIS interpreter (the one colcon builds/runs with).
# Hardcoding 'python3.10' silently dropped astrometry.cfg into a dead dir whenever
# the container's Python differed — derive it so the cfg always lands beside the
# installed nodes/ scripts that load it via os.path.dirname(__file__).
_PY_SITE = 'lib/python{}.{}/site-packages'.format(sys.version_info.major,
                                                  sys.version_info.minor)

# Static data files: package.xml, resource marker, launch
data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('cn_pkg/launch/*.py')),
]

# Walk cn_pkg/data/ and preserve sub-directory structure
# (astrometry/*.fits, astrometry.cfg, images/*, etc.)
data_root = 'cn_pkg/data'
if os.path.isdir(data_root):
    for dirpath, _dirnames, filenames in os.walk(data_root):
        files_here = [os.path.join(dirpath, f) for f in filenames if not f.startswith('.')]
        if not files_here:
            continue
        rel = os.path.relpath(dirpath, 'cn_pkg')   # e.g. "data/astrometry"
        install_dir = 'share/' + package_name + '/' + rel
        data_files.append((install_dir, files_here))


# Also copy astrometry.cfg next to solver.py / drone_sky_prep.py inside
# lib/<python>/site-packages/cn_pkg/nodes/, because BOTH load it via
# `os.path.join(os.path.dirname(__file__), 'astrometry.cfg')` at runtime.
data_files.append((
    _PY_SITE + '/' + package_name + '/nodes',
    ['cn_pkg/data/astrometry.cfg'],
))

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test', 'data']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy', 'opencv-python', 'numpy'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA celestial navigation ROS2 subscriber',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'cn_subscriber.py=cn_pkg.nodes.cn_subscriber:main',
        ],
    },
)
