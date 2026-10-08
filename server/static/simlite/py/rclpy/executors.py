class ExternalShutdownException(Exception):
    pass


class _Executor:
    def __init__(self, *a, **kw):
        self.nodes = []

    def add_node(self, node):
        self.nodes.append(node)

    def spin(self):
        return

    def spin_once(self, timeout_sec=None):
        return

    def shutdown(self, timeout_sec=None):
        return True


SingleThreadedExecutor = MultiThreadedExecutor = Executor = _Executor
