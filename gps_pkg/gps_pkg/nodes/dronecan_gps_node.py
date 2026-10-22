#!/usr/bin/env python3
"""dronecan_gps_node.py — a DroneCAN GNSS receiver (Here3 / Here4, Holybro DroneCAN GNSS...)
as NAVERA's GPS source.

Listens to uavcan.equipment.gnss.Fix2 (and the legacy Fix) on a CAN bus and publishes them
exactly like gps_node (gps_pkg.fix_publish): /navera/sensors/gps_fix, /navera/sensors/gps_vel,
/navera/estimate/gps, /navera/sensors/gnss_time.

Passive by default: the node has no DroneCAN node id, so it sends nothing on the bus — it
can share the vehicle's CAN bus with the autopilot and listen to the GPS the autopilot uses.
A node that also sends ESC / actuator commands (an autopilot re-broadcasting ITS GPS, which
may be NAVERA's own GPS_INPUT) is never taken as the GPS.

A DroneCAN GPS alone on NAVERA's CAN (no autopilot to give it a node id) waits forever for an
id: with allocate_node_ids true (opt-in), NAVERA joins the bus as node own_node_id and runs a
dynamic node id allocator — it then transmits (its NodeStatus and the allocations).

Exits with code 1 when the bus cannot be opened or fails, so the service restarts it.

Parameters:
    can_interface     (default "can0") — SocketCAN interface, or a pydronecan address
                      (slcan:/dev/ttyACM0 for a USB-CAN adapter, mcast:0 for a virtual bus)
    bitrate           (default 1000000) — for SLCAN adapters (SocketCAN: set by `ip link`)
    node_id           (default 0) — the GNSS node to use; 0 = the first one heard with a fix
    allocate_node_ids (default false) — opt-in allocator (see above)
    own_node_id       (default 125) — NAVERA's node id when allocating
    allocation_db     (default ":memory:") — where the allocator keeps the ids it gave (a file
                      keeps each device's id across restarts)
"""
import sys
import threading
import time

import rclpy
from navera_common.gnss import fix2_fix
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from gps_pkg.fix_publish import FixPublisher

CONTROLLER_TYPES = ("uavcan.equipment.esc.RawCommand", "uavcan.equipment.actuator.ArrayCommand")
SWITCH_AFTER_S = 5.0        # with node_id 0: another GNSS node is taken only after this silence
LISTEN_FIRST_S = 2.0        # with node_id 0: who commands motors is learned before choosing


class GnssSelector:
    """Which GNSS node's fixes are used (pure logic, no bus).

    node_id > 0: only that node. 0: after LISTEN_FIRST_S of listening (to learn which nodes
    command motors), the first node heard with a fix, kept while it talks (one receiver, not
    two antennas alternating); another one after SWITCH_AFTER_S of silence. Nodes that
    command motors are never used.
    """

    def __init__(self, node_id: int = 0, start: float = 0.0):
        self.wanted = int(node_id)
        self.current = self.wanted or None
        self.last_t = -1e9
        self.start = start
        self.controllers = set()

    def controller(self, src: int) -> None:
        self.controllers.add(src)
        if self.current == src and not self.wanted:
            self.current = None

    def accept(self, src: int, has_fix: bool, now: float) -> bool:
        if src in self.controllers and not self.wanted:
            return False
        if self.wanted:
            ok = src == self.wanted
        elif self.current == src:
            ok = True
        elif has_fix and now - self.start >= LISTEN_FIRST_S and \
                (self.current is None or now - self.last_t > SWITCH_AFTER_S):
            self.current, ok = src, True
        else:
            ok = False
        if ok:
            self.last_t = now
        return ok


class DroneCanGps(Node):
    def __init__(self):
        super().__init__("dronecan_gps")
        self.declare_parameter("can_interface", "can0")
        self.declare_parameter("bitrate", 1000000)
        self.declare_parameter("node_id", 0)
        self.declare_parameter("allocate_node_ids", False)
        self.declare_parameter("own_node_id", 125)
        self.declare_parameter("allocation_db", ":memory:")
        import dronecan
        self.dronecan = dronecan
        self.iface = str(self.get_parameter("can_interface").value)
        self.allocate = bool(self.get_parameter("allocate_node_ids").value)
        self.sel = GnssSelector(int(self.get_parameter("node_id").value), time.monotonic())
        self.out = FixPublisher(self, "dronecan_gps_node", "dronecan_fix2")
        self.failed, self.running = False, True
        # pydronecan (and its allocator's database) must live in the thread that spins it
        self._ready, self._open_error = threading.Event(), None
        self._thread = threading.Thread(target=self._spin_can, daemon=True)
        self._thread.start()
        if not self._ready.wait(10.0) or self._open_error is not None:
            self.running = False
            raise RuntimeError(self._open_error or f"{self.iface}: no answer from the CAN driver")
        self.get_logger().info(f"DroneCAN GPS on {self.iface} ("
                               f"{'node %d' % self.sel.wanted if self.sel.wanted else 'any node'}"
                               f"{', passive' if not self.allocate else ''})")

    def _open(self):
        dronecan = self.dronecan
        own = int(self.get_parameter("own_node_id").value) if self.allocate else None
        self.can = dronecan.make_node(self.iface, node_id=own, bitrate=int(self.get_parameter("bitrate").value))
        if self.allocate:
            from dronecan.app.dynamic_node_id import CentralizedServer
            from dronecan.app.node_monitor import NodeMonitor
            self._monitor = NodeMonitor(self.can)
            self._allocator = CentralizedServer(self.can, self._monitor,
                                                database_storage=str(self.get_parameter("allocation_db").value),
                                                dynamic_node_id_range=(1, min(124, own - 1)))
            self.get_logger().warn(f"allocating DroneCAN node ids as node {own} (NAVERA transmits on {self.iface})")
        self.can.add_transfer_hook(self._hook)
        self.can.add_handler(dronecan.uavcan.equipment.gnss.Fix2, lambda e: self._on_fix(e, "dronecan_fix2"))
        self.can.add_handler(dronecan.uavcan.equipment.gnss.Fix, lambda e: self._on_fix(e, "dronecan_fix"))

    def _hook(self, t):
        try:
            name = self.dronecan.get_dronecan_data_type(t.payload).full_name
        except Exception:                                    # noqa: BLE001 — a type pydronecan does not know
            return
        if name in CONTROLLER_TYPES and t.source_node_id:
            self.sel.controller(t.source_node_id)

    def _on_fix(self, e, model_id):
        src = e.transfer.source_node_id
        fix = fix2_fix(e.message)
        if not self.sel.accept(src, fix.valid, time.monotonic()):
            return
        fix.details["node_id"] = src
        self.out.publish(fix, model_id)
        if fix.valid:
            self.get_logger().info(f"FIX #{self.out.count} node {src}: lat={fix.lat:.6f} lon={fix.lon:.6f} "
                                   f"sats={fix.num_sats} hAcc={fix.h_acc}", throttle_duration_sec=10.0)
        else:
            self.get_logger().info(f"node {src}: {fix.reason}", throttle_duration_sec=10.0)

    def _spin_can(self):
        try:
            self._open()
        except Exception as e:                               # noqa: BLE001 — interface down / absent
            self._open_error = str(e) or type(e).__name__
            return
        finally:
            self._ready.set()
        while self.running:
            try:
                self.can.spin(0.2)
            except Exception as e:                           # noqa: BLE001 — bus down / adapter unplugged
                if self.running:
                    self.get_logger().fatal(f"CAN bus error: {e} — exiting so the service restarts")
                    self.failed = True
                    self.context.try_shutdown()
                return

    def destroy_node(self):
        self.running = False
        self._thread.join(timeout=2.0)
        try:
            if hasattr(self, "can"):
                self.can.close()
        except Exception:                                    # noqa: BLE001
            pass
        # pydronecan's SLCAN / multicast drivers run an I/O process forked after rclpy.init:
        # it inherited rclpy's SIGTERM handler and would never stop — the node would hang at exit
        import multiprocessing
        for p in multiprocessing.active_children():
            p.kill()
        super().destroy_node()


def main(args=None):
    die_with_parent()
    rclpy.init(args=args)
    try:
        node = DroneCanGps()
    except Exception as e:                                   # noqa: BLE001 — no bus, no pydronecan
        rclpy.logging.get_logger("dronecan_gps").fatal(f"cannot open the CAN bus: {e} — exiting so the "
                                                       "service restarts")
        rclpy.try_shutdown()
        sys.exit(1)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        failed = node.failed
        node.destroy_node()
        rclpy.try_shutdown()
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
