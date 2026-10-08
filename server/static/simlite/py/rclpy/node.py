import time as _wall

from ._core import BUS, NS
from .clock import Clock, ClockType
from .parameter import Parameter


class _Logger:
    def __init__(self, node):
        self.node = node
        self._last = {}

    def _emit(self, level, msg, throttle_duration_sec=None, once=False, skip_first=False, **_):
        key = (level, str(msg)[:60])
        if once and key in self._last:
            return
        if throttle_duration_sec:
            prev = self._last.get(key)
            if prev is not None and BUS.now_ns - prev < throttle_duration_sec * NS:
                return
        self._last[key] = BUS.now_ns
        if BUS.log:
            BUS.log(level, self.node, str(msg))

    def debug(self, msg, **kw): pass
    def info(self, msg, **kw): self._emit("info", msg, **kw)
    def warning(self, msg, **kw): self._emit("warn", msg, **kw)
    warn = warning
    def error(self, msg, **kw): self._emit("error", msg, **kw)
    def fatal(self, msg, **kw): self._emit("error", msg, **kw)


class Publisher:
    def __init__(self, node, msg_type, topic):
        self.node, self.msg_type, self.topic = node, msg_type, topic
        self.active = True

    def publish(self, msg):
        if self.active:
            BUS.publish(self.topic, msg)

    def get_subscription_count(self):
        return len(BUS.subs.get(self.topic, ()))

    def destroy(self):
        self.active = False
        BUS.pubs.get(self.topic, []).remove(self)


class Subscription:
    def __init__(self, node, msg_type, topic, callback):
        self.node, self.msg_type, self.topic, self.callback = node, msg_type, topic, callback
        self.active = True

    def destroy(self):
        self.active = False
        BUS.subs.get(self.topic, []).remove(self)


class Timer:
    def __init__(self, period_s, callback):
        self.period_ns = max(1, int(period_s * NS))
        self.callback = callback
        self.active = True
        self.next_ns = BUS.now_ns + self.period_ns

    def cancel(self):
        self.active = False

    def reset(self):
        import heapq, itertools  # noqa: E401
        self.active = True
        self.next_ns = BUS.now_ns + self.period_ns
        heapq.heappush(BUS.timers, (self.next_ns, next(BUS.seq), self))

    def is_canceled(self):
        return not self.active

    def destroy(self):
        self.active = False

    @property
    def timer_period_ns(self):
        return self.period_ns


class Node:
    def __init__(self, node_name, *, namespace="", parameter_overrides=None, **_):
        self._name = node_name
        self._ns = namespace or "/"
        self._params = {}
        self._overrides = dict(BUS.params.get(node_name, {}))
        for p in parameter_overrides or ():
            self._overrides[p.name] = p.value
        self._clock = Clock(clock_type=ClockType.ROS_TIME)
        self._logger = _Logger(node_name)
        self._entities = []
        BUS.nodes.append(self)

    # -- identity
    def get_name(self): return self._name
    def get_namespace(self): return self._ns
    def get_fully_qualified_name(self): return "/" + self._name
    def get_clock(self): return self._clock
    def get_logger(self): return self._logger

    # -- parameters
    def declare_parameter(self, name, value=None, descriptor=None, ignore_override=False):
        v = value if ignore_override else self._overrides.get(name, value)
        p = Parameter(name, value=v)
        self._params[name] = p
        return p

    def declare_parameters(self, namespace, parameters):
        out = []
        for item in parameters:
            name, value = item[0], (item[1] if len(item) > 1 else None)
            full = f"{namespace}.{name}" if namespace else name
            out.append(self.declare_parameter(full, value))
        return out

    def has_parameter(self, name): return name in self._params

    def get_parameter(self, name):
        if name not in self._params:
            raise KeyError(f"parameter '{name}' has not been declared")
        return self._params[name]

    def get_parameter_or(self, name, alternative=None):
        return self._params.get(name, alternative)

    def set_parameters(self, params):
        for p in params:
            self._params[p.name] = Parameter(p.name, value=p.value)
        return []

    def add_on_set_parameters_callback(self, cb):
        return None

    # -- topics and timers
    def create_publisher(self, msg_type, topic, qos, **_):
        p = Publisher(self, msg_type, topic)
        BUS.pubs.setdefault(topic, []).append(p)
        self._entities.append(p)
        return p

    def create_subscription(self, msg_type, topic, callback, qos, **_):
        s = Subscription(self, msg_type, topic, callback)
        BUS.subs.setdefault(topic, []).append(s)
        self._entities.append(s)
        return s

    def create_timer(self, timer_period_sec, callback, callback_group=None, clock=None):
        import heapq
        t = Timer(timer_period_sec, callback)
        heapq.heappush(BUS.timers, (t.next_ns, next(BUS.seq), t))
        self._entities.append(t)
        return t

    def destroy_timer(self, t): t.cancel()
    def destroy_publisher(self, p): p.destroy()
    def destroy_subscription(self, s): s.destroy()

    # -- graph
    def count_publishers(self, topic):
        return len([p for p in BUS.pubs.get(topic, ()) if p.active])

    def count_subscribers(self, topic):
        return len([s for s in BUS.subs.get(topic, ()) if s.active])

    def get_node_names(self):
        return [n._name for n in BUS.nodes]

    def get_topic_names_and_types(self):
        return [(t, []) for t in set(BUS.pubs) | set(BUS.subs)]

    def destroy_node(self):
        for e in self._entities:
            e.active = False
        if self in BUS.nodes:
            BUS.nodes.remove(self)
