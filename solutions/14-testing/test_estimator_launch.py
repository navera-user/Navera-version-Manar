"""An integration test with launch_testing: start NAVERA's real arbiter, feed it estimates, judge.

    launch_test test_estimator_launch.py

launch_test (1) runs generate_test_description() and starts what it returns, (2) runs the tests of
the normal unittest classes WHILE the nodes run, (3) stops the nodes and runs the classes marked
post_shutdown_test (exit codes). Takes about 10 seconds.
"""
import math
import time
import unittest

import launch
import launch_ros.actions
import launch_testing.actions
import launch_testing.asserts
import pytest
import rclpy
from navera_msgs.msg import NavStatus, PositionEstimate


@pytest.mark.launch_test
def generate_test_description():
    arbiter = launch_ros.actions.Node(package="navera_estimator", executable="estimator_node.py",
                                      name="estimator_node", output="screen")
    # ReadyToTest: the tests may start as soon as the launch is up. The dict gives names to processes.
    return launch.LaunchDescription([arbiter, launch_testing.actions.ReadyToTest()]), {"arbiter": arbiter}


def gps_estimate(node, lat=35.825, lon=10.595):
    """A complete, honest GPS PositionEstimate stamped now (sigma 3 m)."""
    m = PositionEstimate()
    m.header.stamp = node.get_clock().now().to_msg()
    m.sensor_stamp = m.header.stamp
    m.latitude, m.longitude, m.altitude = float(lat), float(lon), math.nan
    m.position_covariance = [9.0, 0.0, 0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 36.0]
    m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    m.source, m.mode, m.valid = PositionEstimate.SOURCE_GPS, PositionEstimate.MODE_MEASURED, True
    return m


class TestArbiter(unittest.TestCase):
    """unittest runs the test_ methods in ALPHABETICAL order: test_1_… before test_2_…"""

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node("arbiter_tester")
        cls.statuses, cls.positions = [], []
        cls.node.create_subscription(NavStatus, "/navera/nav_status", cls.statuses.append, 10)
        cls.node.create_subscription(PositionEstimate, "/navera/position", cls.positions.append, 10)
        cls.pub = cls.node.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def spin_for(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self.node, timeout_sec=0.05)

    def test_0_the_arbiter_starts_initializing(self):
        end = time.time() + 15
        while not self.statuses and time.time() < end:
            self.spin_for(0.2)
        self.assertTrue(self.statuses, "the arbiter published no status in 15 s")
        self.assertEqual(self.statuses[-1].state, NavStatus.STATE_INITIALIZING)

    def test_1_one_gps_estimate_gives_fix_and_one_position(self):
        self.spin_for(1.0)
        self.positions.clear()
        self.pub.publish(gps_estimate(self.node))
        self.spin_for(1.5)
        self.assertEqual(self.statuses[-1].state, NavStatus.STATE_FIX, self.statuses[-1].reason)
        self.assertEqual(len(self.positions), 1)

    def test_2_a_nan_position_is_refused(self):
        self.positions.clear()
        self.pub.publish(gps_estimate(self.node, lat=math.nan))
        self.spin_for(1.5)
        self.assertEqual(self.statuses[-1].state, NavStatus.STATE_NO_FIX)
        self.assertIn("non-finite", self.statuses[-1].reason)
        self.assertEqual(self.positions, [])


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    def test_exit_code(self, proc_info, arbiter):
        """The arbiter must stop cleanly (exit code 0) when the launch ends."""
        launch_testing.asserts.assertExitCodes(proc_info, process=arbiter)
