from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    web_port_arg = DeclareLaunchArgument(
        'web_port',
        default_value='8080',
        description='Web server port'
    )
    
    simulation_web_node = Node(
        package='simulation_web',
        executable='server.py',
        name='simulation_web_node',
        parameters=[
            {'web_port': LaunchConfiguration('web_port')},
        ],
        output='screen',
    )
    
    return LaunchDescription([
        web_port_arg,
        simulation_web_node,
    ])
