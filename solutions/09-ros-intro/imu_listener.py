"""imu_listener.py — a small ROS 2 node that listens to the IMU heartbeat of NAVERA Lite and counts what it hears.

    python3 imu_listener.py          listen for 5 s, then print how many IMU messages arrived
    python3 imu_listener.py 20       listen for 20 s (handy while you inspect the graph in the same terminal)

It was written by "an integrator" for lab 9. The replay node publishes an IMU message 10 times a second on
navera_lite/imu, `ros2 topic echo` shows them... and this listener hears nothing. Lab Step 0 shows the
symptom; lab Step 10 is where you repair it. Change as little as possible: the fix is one line (plus an
import if you need one).
"""
import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu

from navera_lite.ros.qos import SENSOR_QOS

TOPIC = "navera_lite/imu"          # relative name: /navera_lite/imu when the node has no namespace


class ImuListener(Node):
    """Counts the Imu messages that reach it."""

    def __init__(self):
        super().__init__("imu_listener")
        self.count = 0
        self.create_subscription(Imu, TOPIC, self.on_imu, SENSOR_QOS)    # repaired: request BEST_EFFORT

    def on_imu(self, msg):
        self.count += 1


# ---- you don't need to change anything below this line ----
def main():
    try:
        seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    except ValueError:
        sys.exit(f"usage: python3 imu_listener.py [seconds] — {sys.argv[1]!r} is not a number of seconds")
    rclpy.init()
    node = ImuListener()
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    print(f"heard {node.count} IMU messages in {seconds:.1f} s on {node.resolve_topic_name(TOPIC)}", flush=True)
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
