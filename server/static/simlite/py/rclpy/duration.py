from ._core import NS


class Duration:
    def __init__(self, *, seconds=0, nanoseconds=0):
        self._ns = int(round(seconds * NS)) + int(nanoseconds)

    @property
    def nanoseconds(self):
        return self._ns

    def to_msg(self):
        from builtin_interfaces.msg import Duration as DurationMsg
        s, n = divmod(self._ns, NS)
        return DurationMsg(sec=s, nanosec=n)

    @classmethod
    def from_msg(cls, msg):
        return cls(nanoseconds=int(msg.sec) * NS + int(msg.nanosec))

    def __add__(self, o): return Duration(nanoseconds=self._ns + o.nanoseconds)
    def __sub__(self, o): return Duration(nanoseconds=self._ns - o.nanoseconds)
    def __neg__(self): return Duration(nanoseconds=-self._ns)
    def __mul__(self, k): return Duration(nanoseconds=int(self._ns * k))
    __rmul__ = __mul__
    def __eq__(self, o): return isinstance(o, Duration) and self._ns == o._ns
    def __lt__(self, o): return self._ns < o.nanoseconds
    def __le__(self, o): return self._ns <= o.nanoseconds
    def __gt__(self, o): return self._ns > o.nanoseconds
    def __ge__(self, o): return self._ns >= o.nanoseconds
    def __hash__(self): return hash(self._ns)
    def __repr__(self): return f"Duration(nanoseconds={self._ns})"
