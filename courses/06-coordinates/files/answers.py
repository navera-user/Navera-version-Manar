# Write your answers, then save. The course and the lab have everything you need.

# Q1. How many KILOMETERS long is 1 degree of LONGITUDE at Muscat (latitude 23.5839°),
#     on the WGS84 ellipsoid?  (N · cos(lat) · π / 180, in km — a number, e.g.  Q1 = 50.0)
Q1 = 0

# Q2. is_finite_latlon() in ~/navera/navera_common/navera_common/geo.py refuses the position (0, 0).
#     Why is that a good idea?
#   a) (0, 0) is in the open Atlantic ("Null Island"), and it is what a broken or not-ready
#      receiver or a forgotten default value often sends
#   b) Python cannot compute the cosine of 0
#   c) (0, 0) is the North Pole, where longitude is not defined
Q2 = ""

# Q3. At Muscat, NAVERA's haversine_m() uses a sphere of radius 6 371 000 m. For which direction
#     of travel is its distance the MOST wrong?
#   a) east-west      b) north-south      c) the same error in every direction
Q3 = ""
