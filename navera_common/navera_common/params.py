"""ROS 2 parameter helpers shared by the NAVERA nodes."""
from rcl_interfaces.msg import ParameterDescriptor


def declare_float(node, name: str, default: float, description: str = "") -> None:
    """Declare a floating-point parameter that also accepts integer overrides.

    rclpy types a parameter by its default: with a float default, a launch
    override written without a decimal point (`max_speed_mps:=25`) is an
    INTEGER and crashes the node with InvalidParameterTypeException. Dynamic
    typing accepts both; read the value back with float(...).
    """
    node.declare_parameter(
        name, float(default),
        ParameterDescriptor(description=description, dynamic_typing=True))
