"""test_arbiter_launch.py — a launch test of NAVERA Lite's judge, arbiter v0 (mission 14: TODO 7a, 7b).

    launch_test test_arbiter_launch.py

launch_test (lesson §5) (1) calls generate_test_description() and starts what it returns: here the real
arbiter v0, as `ros2 launch` would; (2) runs the tests of TestJudge WHILE the judge runs — they talk to it
over ROS like any other node; (3) stops the judge and runs TestShutdown, which checks its exit code.
About 10 seconds. Run `jobs` first: no other judge may run in your terminal (lesson 09).
"""
import math
import os
import sys
import time
import unittest

import launch
import launch_testing.actions
import launch_testing.asserts
import pytest
import rclpy
from diagnostic_msgs.msg import DiagnosticStatus
from sensor_msgs.msg import NavSatFix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))    # launch_test loads this file by its path
from navera_lite.estimate import Estimate  # noqa: E402
from navera_lite.geo import offset  # noqa: E402
from navera_lite.ros.convert import status_values, to_navsatfix  # noqa: E402
from navera_lite.ros.launch_util import fl_node  # noqa: E402
from navera_lite.ros.qos import FIX_QOS, STATUS_QOS  # noqa: E402

START = (35.8256, 10.6084)                                  # Sousse, as in missions 10–13
COV_3M = (9.0, 0.0, 0.0, 0.0, 9.0, 0.0, 0.0, 0.0, 36.0)     # σ 3 m horizontal, 6 m vertical


@pytest.mark.launch_test
def generate_test_description():
    """The processes under test: the judge, started from this folder with navera_lite.yaml (mission 13's
    fl_node). ReadyToTest() says: the tests may start now. The dict names the process for TestShutdown."""
    judge = fl_node("arbiter_v0", "arbiter", params_file="navera_lite.yaml")
    return launch.LaunchDescription([judge, launch_testing.actions.ReadyToTest()]), {"judge": judge}


class TestJudge(unittest.TestCase):
    """unittest runs the test_ methods in ALPHABETICAL order (test_0 before test_1), all against ONE judge
    that keeps its memory between them."""

    @classmethod
    def setUpClass(cls):                     # once, before the first test: a tester node with its topics
        rclpy.init()
        cls.node = rclpy.create_node("judge_tester")
        cls.statuses, cls.positions = [], []          # every message received, in order of arrival
        cls.node.create_subscription(DiagnosticStatus, "/navera_lite/status", cls.statuses.append, STATUS_QOS)
        cls.node.create_subscription(NavSatFix, "/navera_lite/position", cls.positions.append, FIX_QOS)
        cls.gps = cls.node.create_publisher(NavSatFix, "/navera_lite/fix/gps", FIX_QOS)

    @classmethod
    def tearDownClass(cls):                  # once, after the last test
        cls.node.destroy_node()
        rclpy.shutdown()

    # ---------- helpers ----------
    def spin_for(self, seconds):
        """Let ROS deliver messages to the lists above for `seconds`."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self.node, timeout_sec=0.05)

    def drain(self, seconds=0.3):
        """Let the messages already on their way arrive, then forget them: the test starts from a clean list."""
        self.spin_for(seconds)
        self.positions.clear()

    def send_gps(self, e_m=0.0, lat=None, lon=None):
        """Publish one GPS fix stamped NOW with σ 3 m: e_m metres east of START, or at (lat, lon) if given.
        Returns the (lat, lon) sent."""
        if lat is None:
            lat, lon = offset(START[0], START[1], e_m, 0.0)
        now_s = self.node.get_clock().now().nanoseconds * 1e-9
        self.gps.publish(to_navsatfix(Estimate("gps", lat, lon, now_s, cov=COV_3M, cov_type=1)))
        return lat, lon

    def last_status(self):
        """(values, message) of the newest status: values is a dict, e.g. {"state": "FIX", "source": "gps",
        "src.gps": "eligible", …}; message is the judge's reason, e.g. "gps: σ 3.0 m"."""
        return status_values(self.statuses[-1]), self.statuses[-1].message

    # ---------- the tests ----------
    def test_0_the_judge_starts_and_listens(self):
        # discovery takes time: wait for a first status AND for the judge's subscription to our GPS topic,
        # or the first fix we publish is lost (FIX_QOS is VOLATILE: no late delivery)
        end = time.monotonic() + 15.0
        while time.monotonic() < end and not (self.statuses and self.gps.get_subscription_count() > 0):
            self.spin_for(0.2)
        self.assertTrue(self.statuses, "the judge published no status in 15 s")
        self.assertEqual(self.last_status()[0]["state"], "STARTING")
        self.assertGreater(self.gps.get_subscription_count(), 0, "nobody listens to /navera_lite/fix/gps")

    def test_1_a_5_km_jump_is_refused(self):
        """TODO 7a — goal: one good fix, then 1 s later a fix 5 km east (a spoofer's jump).
        Done when you assert, after the jump: the judge still says FIX (on the good fix, still fresh);
        its status names the jump for the GPS source; and it published exactly ONE position since the
        test began (drain() first) — the good fix, never the jump, never the same one twice."""
        self.drain()
        good = self.send_gps(0.0)
        self.spin_for(1.0)
        self.send_gps(5000.0)
        self.spin_for(1.0)
        values, _ = self.last_status()
        self.assertEqual(values["state"], "FIX")                       # still the good fix (1 s old)
        self.assertIn("jump", values["src.gps"])                       # "eligible; last fix refused: jump 5000 m > …"
        self.assertEqual(len(self.positions), 1, "one measurement, one position")
        self.assertAlmostEqual(self.positions[0].longitude, good[1], places=7)

    def test_2_a_nan_fix_gives_no_fix(self):
        """TODO 7b — goal: a GPS fix whose latitude and longitude are NaN (a broken receiver).
        Done when you assert: the judge says NO_FIX, its message says why (arbiter_v0.py has the words),
        and it published no position AFTER the NaN fix arrived (send it, then drain(), then wait 1 s)."""
        self.send_gps(lat=math.nan, lon=math.nan)
        self.drain()                                                   # what was on its way before
        self.spin_for(1.0)
        values, message = self.last_status()
        self.assertEqual(values["state"], "NO_FIX")
        self.assertIn("bad position", message)                         # "no usable source (gps: bad position)"
        self.assertEqual(self.positions, [])


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    """Runs after the judge was stopped (Ctrl+C, as at the end of a launch)."""

    def test_exit_code(self, proc_info, judge):
        launch_testing.asserts.assertExitCodes(proc_info, process=judge)     # it must stop cleanly: exit code 0
