"""QoS for the sensor topics NAVERA reads from others (a vehicle's IMU, GPS, rangefinder).

Most ROS sensor drivers (IMU drivers, MAVROS, GPS drivers) publish BEST_EFFORT
(rclpy.qos.qos_profile_sensor_data). A RELIABLE subscription never receives from a
BEST_EFFORT publisher; a BEST_EFFORT subscription receives from both. Depth 50: an IMU
at 200 Hz arriving in bursts under load is not cut to its last sample.
"""
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

SENSOR_QOS = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
                        history=HistoryPolicy.KEEP_LAST, depth=50)
