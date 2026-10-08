import enum


class ReliabilityPolicy(enum.IntEnum):
    SYSTEM_DEFAULT = 0
    RELIABLE = 1
    BEST_EFFORT = 2


class DurabilityPolicy(enum.IntEnum):
    SYSTEM_DEFAULT = 0
    TRANSIENT_LOCAL = 1
    VOLATILE = 2


class HistoryPolicy(enum.IntEnum):
    SYSTEM_DEFAULT = 0
    KEEP_LAST = 1
    KEEP_ALL = 2


class QoSProfile:
    def __init__(self, **kw):
        self.depth = kw.get("depth", 10)
        self.reliability = kw.get("reliability", ReliabilityPolicy.RELIABLE)
        self.durability = kw.get("durability", DurabilityPolicy.VOLATILE)
        self.history = kw.get("history", HistoryPolicy.KEEP_LAST)


qos_profile_sensor_data = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
qos_profile_system_default = QoSProfile()
