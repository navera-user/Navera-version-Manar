from .clock import ClockType
from .duration import Duration
from ._core import NS


class Time:
    def __init__(self, *, seconds=0, nanoseconds=0, clock_type=ClockType.ROS_TIME):
        self._ns = int(round(seconds * NS)) + int(nanoseconds)
        self.clock_type = clock_type

    @property
    def nanoseconds(self):
        return self._ns

    def seconds_nanoseconds(self):
        return divmod(self._ns, NS)

    def to_msg(self):
        from builtin_interfaces.msg import Time as TimeMsg
        s, n = divmod(self._ns, NS)
        return TimeMsg(sec=s, nanosec=n)

    @classmethod
    def from_msg(cls, msg, clock_type=ClockType.ROS_TIME):
        return cls(nanoseconds=int(msg.sec) * NS + int(msg.nanosec), clock_type=clock_type)

    def __add__(self, other):
        if isinstance(other, Duration):
            return Time(nanoseconds=self._ns + other.nanoseconds, clock_type=self.clock_type)
        return NotImplemented

    __radd__ = __add__

    def __sub__(self, other):
        if isinstance(other, Time):
            return Duration(nanoseconds=self._ns - other._ns)
        if isinstance(other, Duration):
            return Time(nanoseconds=self._ns - other.nanoseconds, clock_type=self.clock_type)
        return NotImplemented

    def _cmp(self, other):
        if not isinstance(other, Time):
            raise TypeError("can only compare Time with Time")
        return self._ns - other._ns

    def __eq__(self, o): return isinstance(o, Time) and self._ns == o._ns
    def __ne__(self, o): return not self == o
    def __lt__(self, o): return self._cmp(o) < 0
    def __le__(self, o): return self._cmp(o) <= 0
    def __gt__(self, o): return self._cmp(o) > 0
    def __ge__(self, o): return self._cmp(o) >= 0
    def __hash__(self): return hash(self._ns)
    def __repr__(self): return f"Time(nanoseconds={self._ns})"
