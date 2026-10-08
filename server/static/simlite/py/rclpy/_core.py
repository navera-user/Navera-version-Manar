import heapq
import itertools

NS = 1_000_000_000


class Bus:
    """Topics, timers and the simulated clock shared by every node in the page."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.now_ns = 0
        self.subs = {}            # topic -> [Subscription]
        self.pubs = {}            # topic -> [Publisher]
        self.timers = []          # heap of (due_ns, seq, Timer)
        self.queue = []           # messages waiting for delivery: (topic, msg)
        self.seq = itertools.count()
        self.nodes = []
        self.log = None           # callable(level, node, text)
        self.params = {}          # node name -> {param: value} overrides
        self.running = True

    def publish(self, topic, msg):
        self.queue.append((topic, msg))

    def deliver(self):
        """Hand queued messages to their subscribers (a message published from a callback
        is delivered in the same round, like an intra-process ROS 2 executor)."""
        n = 0
        while self.queue and n < 10000:
            topic, msg = self.queue.pop(0)
            for s in list(self.subs.get(topic, ())):
                if s.active:
                    s.callback(msg)
            n += 1

    def advance(self, until_ns):
        """Run every timer due up to until_ns, in time order, then set the clock."""
        self.deliver()
        while self.timers and self.timers[0][0] <= until_ns:
            due, _, t = heapq.heappop(self.timers)
            if not t.active:
                continue
            self.now_ns = max(self.now_ns, due)
            t.callback()
            self.deliver()
            if t.active:
                t.next_ns = due + t.period_ns
                heapq.heappush(self.timers, (t.next_ns, next(self.seq), t))
        self.now_ns = max(self.now_ns, until_ns)
        self.deliver()


BUS = Bus()


def init(args=None, context=None):
    BUS.running = True


def ok(context=None):
    return BUS.running


def shutdown(context=None):
    BUS.running = False


def spin(node=None, executor=None):
    """In the browser the simulator drives time: spin() returns at once."""
    return


def spin_once(node=None, executor=None, timeout_sec=None):
    BUS.deliver()
