# Lab 9 — answers (teacher solution). The domain-dependent values are computed from the
# environment so that this file works in any sandbox; a student writes plain numbers.
import os

_D = int(os.environ.get("ROS_DOMAIN_ID", "0"))

MY_DOMAIN_ID = _D
DISCOVERY_PORT = 7400 + 250 * _D

CHATTER_TYPE = "std_msgs/msg/String"
CHATTER_RELIABILITY = "RELIABLE"
CHATTER_DURABILITY = "VOLATILE"
TALKER_HZ = 1.0
CHATTER_MSG_BYTES = 24
DDS_PORTS = [7400 + 250 * _D, 7410 + 250 * _D, 7411 + 250 * _D, 7412 + 250 * _D, 7413 + 250 * _D]

CHATTER_SUBSCRIBERS = 1

OTHER_DOMAIN_SEES_CHATTER = False

BE_PUB_RELIABLE_SUB_RECEIVED = False
BE_PUB_BE_SUB_RECEIVED = True
LATCHED_TRANSIENT_RECEIVED = True
LATCHED_VOLATILE_RECEIVED = False

SERVICE_SUM = _D + 1000
FIBONACCI_8 = [0, 1, 1, 2, 3, 5, 8, 13, 21]

MODE_REPLAYED = 3
STATE_FIX = 2

ESTIMATOR_SUBSCRIBES = ["/navera/estimate/gps", "/navera/estimate/day", "/navera/estimate/night",
                        "/navera/estimate/cn", "/navera/sensors/imu"]
ESTIMATOR_PUBLISHES = ["/navera/position", "/navera/nav_status"]
FIRST_STATE = 0
NAV_STATUS_HZ = 5.0
FIX_MAX_SIGMA_M = 25.0

Q1 = "b"
Q2 = "b"
Q3 = "b"
