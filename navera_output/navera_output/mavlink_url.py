"""One MAVLink address format for every NAVERA setting (output and vehicle link).

Accepted, all equivalent for a serial port:
    serial:/dev/ttyTHS2:921600     (NAVERA's documented form)
    /dev/ttyTHS2,921600            (pymavlink's own form)
and any pymavlink network URL: udpin:0.0.0.0:14551, udpout:127.0.0.1:14550,
tcp:127.0.0.1:5763, tcpin:0.0.0.0:5770.
"""
from typing import Optional, Tuple

_NETWORK = ("udp:", "udpin:", "udpout:", "udpbcast:", "tcp:", "tcpin:")


def parse(url: str) -> Tuple[str, Optional[int]]:
    """(device or URL, baud for a serial port else None); ValueError on a malformed one."""
    u = str(url).strip()
    if not u:
        raise ValueError("empty MAVLink address")
    if u.startswith(_NETWORK):
        return u, None
    if u.startswith("serial:"):
        rest = u[len("serial:"):]
        dev, sep, baud = rest.rpartition(":")
    else:
        dev, sep, baud = u.rpartition(",")
    if not sep or not dev.startswith("/dev/") or not baud.isdigit():
        raise ValueError(f"MAVLink address {url!r}: expected serial:/dev/<port>:<baud>, "
                         "udpin:<ip>:<port>, udpout:<ip>:<port> or tcp:<ip>:<port>")
    return dev, int(baud)


def connect(url: str, source_system: int, source_component: int):
    from pymavlink import mavutil
    dev, baud = parse(url)
    kw = dict(source_system=source_system, source_component=source_component)
    if baud is not None:
        kw["baud"] = baud
    return mavutil.mavlink_connection(dev, **kw)
