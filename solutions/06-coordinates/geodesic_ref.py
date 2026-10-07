# Reference: the distance ON THE WGS84 ELLIPSOID (Vincenty's inverse formula, 1975).
# You do not need to change this file. error_study.py uses it as the "truth" to measure
# how wrong the spherical haversine is. Accuracy: better than 1 mm for any two points that
# are not almost opposite on the Earth (then the iteration may not converge -> ValueError).
import math

A = 6_378_137.0
F = 1.0 / 298.257223563
B = A * (1.0 - F)


def vincenty(lat1, lon1, lat2, lon2):
    """(distance_m, initial_bearing_deg, final_bearing_deg) on the WGS84 ellipsoid."""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0, 0.0, 0.0
    u1 = math.atan((1.0 - F) * math.tan(math.radians(lat1)))      # reduced latitudes
    u2 = math.atan((1.0 - F) * math.tan(math.radians(lat2)))
    big_l = math.radians(lon2 - lon1)
    lam = big_l
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        sin_s = math.hypot(cu2 * sl, cu1 * su2 - su1 * cu2 * cl)
        cos_s = su1 * su2 + cu1 * cu2 * cl
        sigma = math.atan2(sin_s, cos_s)
        sin_a = cu1 * cu2 * sl / sin_s
        cos2_a = 1.0 - sin_a * sin_a
        cos_2sm = cos_s - 2.0 * su1 * su2 / cos2_a if cos2_a != 0.0 else 0.0
        c = F / 16.0 * cos2_a * (4.0 + F * (4.0 - 3.0 * cos2_a))
        lam_prev = lam
        lam = big_l + (1.0 - c) * F * sin_a * (
            sigma + c * sin_s * (cos_2sm + c * cos_s * (-1.0 + 2.0 * cos_2sm ** 2)))
        if abs(lam - lam_prev) < 1e-13:
            break
    else:
        raise ValueError("Vincenty did not converge (points almost antipodal)")
    u_sq = cos2_a * (A * A - B * B) / (B * B)
    k_a = 1.0 + u_sq / 16384.0 * (4096.0 + u_sq * (-768.0 + u_sq * (320.0 - 175.0 * u_sq)))
    k_b = u_sq / 1024.0 * (256.0 + u_sq * (-128.0 + u_sq * (74.0 - 47.0 * u_sq)))
    d_sigma = k_b * sin_s * (cos_2sm + k_b / 4.0 * (
        cos_s * (-1.0 + 2.0 * cos_2sm ** 2)
        - k_b / 6.0 * cos_2sm * (-3.0 + 4.0 * sin_s ** 2) * (-3.0 + 4.0 * cos_2sm ** 2)))
    s = B * k_a * (sigma - d_sigma)
    az1 = math.degrees(math.atan2(cu2 * math.sin(lam), cu1 * su2 - su1 * cu2 * math.cos(lam))) % 360.0
    az2 = math.degrees(math.atan2(cu1 * math.sin(lam), -su1 * cu2 + cu1 * su2 * math.cos(lam))) % 360.0
    return s, az1, az2
