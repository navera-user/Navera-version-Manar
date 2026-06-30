from setuptools import setup

package_name = 'vision_pkg'
setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='navera',
    maintainer_email='navera@todo.todo',
    description='NAVERA Vision Package',
    license='MIT',
    entry_points={
        'console_scripts': [
            'vision_node = vision_pkg.vision_node:main',
            'receiver = vision_pkg.receiver:main',
        ],
    },
)
