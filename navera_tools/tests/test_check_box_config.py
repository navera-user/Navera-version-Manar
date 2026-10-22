#!/usr/bin/env python3
"""check_box's static settings checks catch the integrator's bad configuration (I-F13).
Exit code 0 = pass."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import check_box  # noqa: E402

BAD = {"ROS_LOCALHOST_ONLY": "1", "NAVERA_SENSOR_SOURCE": "ros", "NAVERA_FORWARD_DEGRADED": "true",
       "NAVERA_DEGRADED_SIGMA_M": "", "NAVERA_MAVLINK_URL": "serial:/dev/ttyTHS2",
       "NAVERA_GPS_SOURCE": "serial", "NAVERA_GPS_PORT": "/dev/ttyTHS2", "NAVERA_NMEA_PORT": "/dev/ttyTHS2",
       "NAVERA_VEHICLE_MAVLINK_URL": "serial:/dev/ttyTHS2:921600"}


def main():
    fails = []
    found = check_box.config_findings(BAD)
    text = "\n".join(f"{lv} {w}: {d}" for lv, w, d in found)
    for must in ("MAVLink address", "is used by", "without NAVERA_DEGRADED_SIGMA_M", "ROS_LOCALHOST_ONLY=1"):
        if must not in text:
            fails.append(f"not flagged: {must}")
    good = {"NAVERA_GPS_SOURCE": "serial", "NAVERA_GPS_PORT": "/dev/ttyTHS1",
            "NAVERA_MAVLINK_URL": "udpout:127.0.0.1:14650", "NAVERA_VEHICLE_MAVLINK_URL": "serial:/dev/ttyTHS2:921600",
            "NAVERA_FORWARD_DEGRADED": "true", "NAVERA_DEGRADED_SIGMA_M": "30"}
    if check_box.config_findings(good):
        fails.append(f"a good configuration flagged: {check_box.config_findings(good)}")
    d = tempfile.mkdtemp()
    empty = os.path.join(d, "empty.mbtiles")
    open(empty, "w").close()
    full = os.path.join(d, "map.mbtiles")
    con = sqlite3.connect(full)
    con.execute("CREATE TABLE tiles (zoom_level, tile_column, tile_row, tile_data)")
    con.execute("INSERT INTO tiles VALUES (17, 1, 1, x'00')")
    con.commit()
    con.close()
    if check_box.mbtiles_verdict(empty)[0] != check_box.FAIL:
        fails.append("an empty map file passed")
    if check_box.mbtiles_verdict(full)[0] != check_box.OK:
        fails.append("a valid map file failed")
    # the Insta360 kit: used when either source is insta360; its USB node's permission
    if not check_box.insta360_used({"NAVERA_CAMERA_INPUT": "insta360"}) or check_box.insta360_used({}):
        fails.append("Insta360 kit use not recognised")
    sysfs, dev = os.path.join(d, "sys"), os.path.join(d, "dev")
    os.makedirs(os.path.join(sysfs, "1-2.1"))
    open(os.path.join(sysfs, "1-2.1", "busnum"), "w").write("1\n")
    open(os.path.join(sysfs, "1-2.1", "devnum"), "w").write("10\n")
    if check_box.usb_node_writable("1-2.1", sysfs, dev) is not None:
        fails.append("a missing USB node was judged")
    os.makedirs(os.path.join(dev, "001"))
    open(os.path.join(dev, "001", "010"), "w").close()
    if check_box.usb_node_writable("1-2.1", sysfs, dev) is not True:
        fails.append("a writable USB node was refused")
    print(text)
    for f in fails:
        print("FAIL", f)
    print("check_box_config:", "PASS" if not fails else f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
