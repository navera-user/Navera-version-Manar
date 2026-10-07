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
#   gga is a dictionary from nt.parse_gga (or None for a line that is not a valid GGA:
#   then return (False, "not a GGA sentence")).
#   - quality = gga["quality"], or 0 when it is None (gps_node: int(...) fails -> 0)
#   - position present = lat AND lon are not None
#   - if no position OR quality not in USABLE_QUALITIES:
#         quality 6, 7 or 8 -> reason f"receiver reports a non-satellite position (qual={q}) — not used"
#         otherwise         -> reason f"no GPS fix (qual={q})"
#     and return (False, reason)
#   - otherwise return (True, "")
#   The dash in the first reason is an EM DASH "—" (copy it from gps_node.py).
def navera_decision(gga):
    if gga is None:
        return False, "not a GGA sentence"
    q = gga.get("quality")
    q = 0 if q is None else q
    has_pos = gga.get("lat") is not None and gga.get("lon") is not None
    if not has_pos or q not in USABLE_QUALITIES:
        if q in (6, 7, 8):
            return False, f"receiver reports a non-satellite position (qual={q}) — not used"
        return False, f"no GPS fix (qual={q})"
    return True, ""


# TODO 10: the position covariance gps_node writes (a list of 9 floats, row-major 3 x 3,
#   axes East, North, Up), or None when hdop is None or <= 0 (covariance UNKNOWN):
#       s = HDOP * UERE_M ;  diagonal = [s^2, s^2, 4 s^2] ; all other entries 0.0
def navera_covariance(hdop):
    if hdop is None or hdop <= 0:
        return None
    cov = (hdop * UERE_M) ** 2
    return [cov, 0.0, 0.0, 0.0, cov, 0.0, 0.0, 0.0, cov * 4]


# TODO 11: a "jump gate". Going from prev (lat, lon) to cur (lat, lon) in dt seconds is
#   plausible when the distance (nt.haversine_m) is at most  v_max * dt + slack_m.
#   slack_m allows for the noise of the fixes themselves (the lab uses 3 sigma of cur).
#   Return True / False. prev None -> True (first fix). dt None or <= 0 -> False.
def jump_ok(prev, cur, dt, slack_m=0.0, v_max=V_MAX_MPS):
    if prev is None:
        return True
    if dt is None or dt <= 0:
        return False
    return nt.haversine_m(prev[0], prev[1], cur[0], cur[1]) <= v_max * dt + slack_m


if __name__ == "__main__":
    tests = ["$GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,*70",
             "$GPGGA,052009.00,,,,,0,00,99.99,,,,,,*68"]
    for ln in tests:
        g = nt.parse_gga(ln)
        decision = navera_decision(g)
        cov = navera_covariance(g["hdop"]) if decision and decision[0] else "UNKNOWN (no fix: no covariance)"
        print("TODO 9 ", decision, "  TODO 10", cov)
    print("TODO 9  quality 6:", navera_decision({"quality": 6, "lat": 24.4, "lon": 56.6, "hdop": None}))
    print("TODO 11 jump 830 m in 1 s ok?", jump_ok((24.40, 56.70), (24.4075, 56.70), 1.0), "(should be False)")
