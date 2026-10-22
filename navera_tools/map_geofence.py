#!/usr/bin/env python3
"""An ArduPilot / PX4 geofence from the mission's map: keep the vehicle where NAVERA can see.

Day vision matches the camera against the mission's satellite map only; past the map's edge
NAVERA has nothing to match, dead-reckons, then gives no position. NAVERA itself only REPORTS
the edge (NavStatus.map_area / map_edge_m, a STATUSTEXT to the autopilot, the operator view).
This tool, run by the operator before flight, turns the map's coverage into an inclusion
polygon the autopilot enforces with its own fence action — the integrator's decision.

    python3 navera_tools/map_geofence.py AREA [--margin-m 500] [--max-vertices 60]
        [--plan fence.plan] [--waypoints fence.waypoints] [--upload URL] [--json]

AREA: the map day vision uses — a mission bundle (its day/images), a prepared area
(prepare_area.py OUT, its images/) or the images directory itself (DAY_DATASET_DIR/images).

The polygon lies at least --margin-m inside the map everywhere (at a grid of 20 m): with the
default 500 m the camera footprint (~600 m wide at 250 m height with a 100 deg lens) stays on
the map at the fence. Outputs: --plan (QGroundControl .plan, geoFence), --waypoints (QGC WPL 110
fence items, MAVProxy `fence load`, Mission Planner), --upload (pymavlink URL, e.g.
udpin:0.0.0.0:14550 or serial:/dev/ttyACM0:115200: MISSION_ITEM_INT, mission_type FENCE). The
autopilot parameters to set are printed (ArduPilot: FENCE_ENABLE 1, FENCE_TYPE includes 4 =
polygon, FENCE_ACTION chosen by the integrator). Exit code 0 = a polygon was produced.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "navera_common"))
from navera_common.map_area import MapArea  # noqa: E402

FENCE_VERTEX_INCLUSION = 5001          # MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION
MISSION_TYPE_FENCE = 1


def images_dir_of(area: str) -> str:
    """The tiles directory of a bundle, a prepared area or the images directory itself."""
    for cand in (os.path.join(area, "day", "images"), os.path.join(area, "images"), area):
        if os.path.isdir(cand) and any(n.startswith("tile_") for n in os.listdir(cand)):
            return cand
    raise SystemExit(f"{area}: no map tiles (tile_<z>_<x>_<y>.jpg) in day/images, images/ or itself")


def qgc_plan(poly) -> dict:
    """A QGroundControl .plan holding only the inclusion fence."""
    return {"fileType": "Plan", "version": 1, "groundStation": "NAVERA map_geofence",
            "mission": {"version": 2, "firmwareType": 3, "vehicleType": 2, "cruiseSpeed": 15,
                        "hoverSpeed": 5, "plannedHomePosition": [poly[0][0], poly[0][1], 0], "items": []},
            "geoFence": {"version": 2, "circles": [],
                         "polygons": [{"inclusion": True, "version": 1,
                                       "polygon": [[round(a, 7), round(b, 7)] for a, b in poly]}]},
            "rallyPoints": {"version": 2, "points": []}}


def wpl(poly) -> str:
    """QGC WPL 110 fence file: one MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION per vertex."""
    lines = ["QGC WPL 110"]
    for i, (lat, lon) in enumerate(poly):
        lines.append(f"{i}\t0\t0\t{FENCE_VERTEX_INCLUSION}\t{len(poly)}\t0\t0\t0\t{lat:.7f}\t{lon:.7f}\t0\t1")
    return "\n".join(lines) + "\n"


def upload(url: str, poly, timeout_s: float = 30.0) -> None:
    """Send the polygon as the autopilot's fence (MAVLink mission protocol, mission_type FENCE)."""
    os.environ.setdefault("MAVLINK20", "1")          # mission_type is a MAVLink 2 extension field
    from pymavlink import mavutil
    m = mavutil.mavlink_connection(url, source_system=255, source_component=190)
    if m.wait_heartbeat(timeout=timeout_s) is None:
        raise SystemExit(f"{url}: no autopilot heartbeat")
    ts, tc = m.target_system, m.target_component
    m.mav.mission_count_send(ts, tc, len(poly), MISSION_TYPE_FENCE)
    end = time.time() + timeout_s
    while time.time() < end:
        r = m.recv_match(type=["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"], blocking=True, timeout=2)
        if r is None or getattr(r, "mission_type", MISSION_TYPE_FENCE) != MISSION_TYPE_FENCE:
            continue
        if r.get_type() == "MISSION_ACK":
            if r.type != 0:
                raise SystemExit(f"fence refused by the autopilot (MAV_MISSION_RESULT {r.type})")
            print(f"fence uploaded: {len(poly)} vertices")
            return
        lat, lon = poly[r.seq]
        m.mav.mission_item_int_send(ts, tc, r.seq, mavutil.mavlink.MAV_FRAME_GLOBAL, FENCE_VERTEX_INCLUSION,
                                    0, 1, len(poly), 0, 0, 0, int(round(lat * 1e7)), int(round(lon * 1e7)), 0.0,
                                    MISSION_TYPE_FENCE)
    raise SystemExit("fence upload timed out")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("area")
    ap.add_argument("--margin-m", type=float, default=500.0, help="fence at least this far inside the map")
    ap.add_argument("--max-vertices", type=int, default=60, help="autopilot fence storage: keep it small")
    ap.add_argument("--plan", help="write a QGroundControl .plan (geoFence)")
    ap.add_argument("--waypoints", help="write a QGC WPL 110 fence file (MAVProxy 'fence load', Mission Planner)")
    ap.add_argument("--upload", help="pymavlink URL of the autopilot: upload the fence now")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    images = images_dir_of(a.area)
    area = MapArea.from_images_dir(images)
    poly = area.fence_polygon(a.margin_m, a.max_vertices)
    report = dict(images_dir=images, tiles=len(area.tiles), map_km2=round(area.area_km2, 2),
                  map_bbox=[round(v, 6) for v in (area.south, area.west, area.north, area.east)],
                  margin_m=a.margin_m, vertices=len(poly), polygon=[[round(x, 7), round(y, 7)] for x, y in poly])
    if not poly:
        print(f"no fence: nothing of the map ({area.area_km2:.1f} km2) is {a.margin_m:.0f} m inside its edge",
              file=sys.stderr)
        return 1
    if a.plan:
        with open(a.plan, "w") as f:
            json.dump(qgc_plan(poly), f, indent=1)
    if a.waypoints:
        with open(a.waypoints, "w") as f:
            f.write(wpl(poly))
    if a.upload:
        upload(a.upload, poly)
    if a.json:
        print(json.dumps(report))
    else:
        print(f"map: {len(area.tiles)} tiles, {area.area_km2:.1f} km2, bbox S {area.south:.5f} W {area.west:.5f} "
              f"N {area.north:.5f} E {area.east:.5f}")
        print(f"fence: inclusion polygon of {len(poly)} vertices, >= {a.margin_m:.0f} m inside the map"
              + (f" -> {a.plan}" if a.plan else "") + (f" -> {a.waypoints}" if a.waypoints else ""))
        print("ArduPilot: FENCE_ENABLE 1, FENCE_TYPE with bit 4 (polygon; e.g. 5 = max altitude + polygon), "
              "FENCE_ACTION as the integrator decides (e.g. 1 = RTL / Land), FENCE_MARGIN; "
              "upload the fence and check it in the ground station before take-off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
