import enum


class ClockType(enum.IntEnum):
    UNINITIALIZED = 0
    ROS_TIME = 1
    SYSTEM_TIME = 2
    STEADY_TIME = 3


class Clock:
    def __init__(self, *, clock_type=ClockType.ROS_TIME):
        self.clock_type = clock_type

    def now(self):
        from .time import Time
        from ._core import BUS
        return Time(nanoseconds=BUS.now_ns, clock_type=self.clock_type)


ROSClock = Clock
