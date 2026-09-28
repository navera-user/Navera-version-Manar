from setuptools import setup, find_packages

package_name = 'navera_common'

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
]

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=data_files,
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='IRIS Systems',
    maintainer_email='contact@iris-systems.tn',
    description='NAVERA shared utilities (process lifecycle, geodesy helpers).',
    license='Proprietary',
    # Library package: no console_scripts. Imported by the pipeline nodes.
    entry_points={
        'console_scripts': [],
    },
)
