"""navera_lite/ros/qos.py — the three QoS profiles of NAVERA Lite's topics, and the rule that says whether a
publisher and a subscriber connect. Part of NAVERA Lite, the course's teaching stack (mission 09).
Written for the course; it is not NAVERA code.

A publisher OFFERS a quality of service, a subscriber REQUESTS one. They connect only if what is offered is
at least as good as what is requested, policy by policy (lesson 09 §4).
"""
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data

# @part 09
FIX_QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=10,
                     durability=DurabilityPolicy.VOLATILE)        # /navera_lite/fix/*, /navera_lite/position
# @part 09
SENSOR_QOS = qos_profile_sensor_data                              # /navera_lite/imu: BEST_EFFORT, depth 5
# @part 09
STATUS_QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=1,
                        durability=DurabilityPolicy.TRANSIENT_LOCAL)   # /navera_lite/status: "latched"


# @part 09
def describe(qos):
    """A QoS profile in a few words, as `ros2 topic info -v` prints it.

    Example: describe(STATUS_QOS) → "RELIABLE, TRANSIENT_LOCAL, KEEP_LAST 1"
    """
    return f"{qos.reliability.name}, {qos.durability.name}, {qos.history.name} {qos.depth}"


# @part 09 todo 1
def compatible(offered, requested):
    """Do a publisher offering `offered` and a subscriber requesting `requested` connect?
    Look at two policies only, reliability and durability (lesson §4 table):
      - a BEST_EFFORT offer cannot serve a RELIABLE request;
      - a VOLATILE offer cannot serve a TRANSIENT_LOCAL request.
    Every other pair connects. Inputs: two rclpy QoSProfile. Returns True or False.
    Example: compatible(SENSOR_QOS, FIX_QOS) → False   (the IMU offers BEST_EFFORT, the listener asks RELIABLE)
             compatible(FIX_QOS, SENSOR_QOS) → True
    """
    if offered.reliability == ReliabilityPolicy.BEST_EFFORT and requested.reliability == ReliabilityPolicy.RELIABLE:
        return False
    if offered.durability == DurabilityPolicy.VOLATILE and requested.durability == DurabilityPolicy.TRANSIENT_LOCAL:
        return False
    return True
