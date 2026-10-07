"""Lesson 15 — NAVERA's GPS quality filter, rewritten outside ROS.

These functions copy the DECISIONS of gps_pkg/gps_pkg/nodes/gps_node.py (_publish_fix)
so that you can test them on a whole log without a serial port. Open gps_node.py next to
this file: the reasons must be the SAME text, character for character.
"""
import nmea_tools as nt

USABLE_QUALITIES = {1, 2, 4, 5}       # gps_node.py: _VALID_GPS_QUAL
UERE_M = 2.0                          # gps_node.py: "sigma = HDOP x 2 m (assumed user range error)"
V_MAX_MPS = 60.0                      # jump gate of this lab (NOT in gps_node): 216 km/h


# TODO 9: what gps_node publishes for one GGA, as a pair (valid, reason).
#   gga is a dictionary from nt.parse_gga, or None for a line that is not a valid GGA:
#   then return (False, "not a GGA sentence").
#   Read gps_node.py (_publish_fix and _VALID_GPS_QUAL) and copy its RULES and its reason
#   TEXTS exactly (one reason contains an EM DASH "—": copy it from the file).
#   Valid fix -> (True, ""). A missing quality counts as 0, like in gps_node.
#   Note: gps_node judges the position AND the quality. A GGA with quality 1 but no position
#   is not a fix, and gps_node's reason is then "no GPS fix (qual=1)". Your parser gives
#   lat = None for the 74-minute line, so you will see this strange-looking text. It is correct.
def navera_decision(gga):
    return None  # TODO 9: replace this line with your code


# TODO 10: the position covariance gps_node writes (a list of 9 floats, row-major 3 x 3,
#   axes East, North, Up), or None when hdop is None or <= 0 (covariance UNKNOWN).
#   Read the covariance in gps_node.py _publish_fix (it uses UERE_M above). Course: section 6,
#   "NAVERA's choice".
def navera_covariance(hdop):
    return None  # TODO 10: replace this line with your code


# TODO 11: a "jump gate". Going from prev (lat, lon) to cur (lat, lon) in dt seconds is
#   plausible when the distance is not more than what a vehicle at v_max can drive in dt,
#   plus slack_m (use nt.haversine_m for the distance).
#   slack_m allows for the noise of the fixes themselves (the lab uses 3 sigma of cur).
#   Return True / False. prev None -> True (first fix). dt None or <= 0 -> False.
def jump_ok(prev, cur, dt, slack_m=0.0, v_max=V_MAX_MPS):
    return None  # TODO 11: replace this line with your code


if __name__ == "__main__":
    tests = ["$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70",
             "$GPGGA,052009.00,,,,,0,00,99.99,,,,,,*68"]
    for ln in tests:
        g = nt.parse_gga(ln)
        decision = navera_decision(g)
        cov = navera_covariance(g["hdop"]) if decision and decision[0] else "UNKNOWN (no fix: no covariance)"
        print("TODO 9 ", decision, "  TODO 10", cov)
    print("TODO 9  quality 6:", navera_decision({"quality": 6, "lat": 35.8, "lon": 10.7, "hdop": None}))
    print("TODO 11 jump 830 m in 1 s ok?", jump_ok((35.80, 10.70), (35.8075, 10.70), 1.0), "(should be False)")
