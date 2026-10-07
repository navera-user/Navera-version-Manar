# Lab 6 report — how far can NAVERA trust its flat-Earth shortcut?

## Method

The home point is the medina of Sousse (NAVERA's test area) at height 0. For 41 distances from
10 m to 300 km and 8 bearings, error_study.py places a point exactly in the WGS84 local
tangent frame (east, north, up = 0) and converts it to latitude and longitude with my
enu_to_geodetic(). Then it converts that point back to (east, north) with two shortcuts:
NAVERA's flat_en() (111 320 m per degree for both axes) and a flat version that uses the
WGS84 radii M and N of the home latitude. The horizontal distance between the shortcut and the
exact east/north is the error; I keep the worst bearing. It also compares the spherical
haversine with the ellipsoidal Vincenty distance.

## Results

NAVERA's flat error reaches 1 m at 369.0 m and 10 m at 3752.7 m. It is about 3.3 m at 1 km
and 33.1 m at 10 km, so it grows linearly: 0.33 % of the distance. The WGS84-radii version
reaches 1 m only at 4855.9 m and is 6.5 m at 10 km; its error grows with the square of the
distance. From Sousse to Rome the sphere gives 692.906 km and the ellipsoid 691.924 km, a
difference of 982.2 m (0.142 %).

## Discussion

The NAVERA error is a scale error. One degree of latitude at Sousse is 110.96 km on WGS84, but
the code uses 111.32 km, so every north displacement is 0.33 % too long. The east scale is
almost right because 111 320 m is close to N times pi over 180. The second shortcut removes the
scale error; what remains is the convergence of the meridians and the curvature, which are
second-order effects (larger at Sousse than near the equator, because tan of the latitude is 0.72).
Day vision measures its velocity with _en() and applies it with _move(), so the same wrong
constant is used in both directions and the scale error cancels in the carried position. It does
not cancel in numbers that are compared with true meters, such as distance gates and stated
uncertainties: over 2 km that is about 7 m, small compared with the uncertainty NAVERA states for
a dead-reckoned position, so it is acceptable. For a 300 km survey flight with a single flat frame
the error reaches about 6 km: the software must use exact ENU or move its home point often. Using
the radii M and N costs one square root per call and would remove the scale part of the error.
