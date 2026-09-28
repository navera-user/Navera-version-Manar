"""declare_float: float parameters must accept integer overrides."""
import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter

from navera_common.params import declare_float


def test_integer_override_is_accepted():
    rclpy.init()
    try:
        node = Node("params_test", parameter_overrides=[
            Parameter("speed", Parameter.Type.INTEGER, 25),
            Parameter("rate", Parameter.Type.DOUBLE, 2.5)])
        declare_float(node, "speed", 100.0)      # plain declare_parameter raised here
        declare_float(node, "rate", 5.0)
        declare_float(node, "unset", 1.5)
        assert float(node.get_parameter("speed").value) == 25.0
        assert float(node.get_parameter("rate").value) == 2.5
        assert float(node.get_parameter("unset").value) == 1.5
        node.destroy_node()
    finally:
        rclpy.shutdown()
