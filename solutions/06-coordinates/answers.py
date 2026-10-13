# Lab 6 — your answers. Numbers without quotes (OFFSET_KM = 12.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Navigator (the sphere) ========

# ---- Step 0: which way to Tunisia? ---------------------------------------------------------------
PREDICT_ROUTE = "West of the line, maybe 10 km at most."          # the shortest path Paris -> central Tunisia: east or west of the straight
                            # lat/lon line? by how many km at most?

# ---- Step 2: bearings (your bearing_deg, Paris -> central Tunisia) -------------------------------
TURN_DEG = 4.70              # arrival heading − departure heading on the great circle (degrees, with sign)
EXPLAIN_BEARING = "A great circle is not a line of constant bearing: the meridians converge towards the pole, so the angle between the path and the local meridian changes along the way; flying south-east from Paris, the heading grows from 158.1 to 162.8 degrees, a turn to the right."        # why does a great-circle flight change heading, and why to the right here?

# ---- Step 3: the route-length audit (python3 run_geo.py cos) -------------------------------------
PREDICT_COS = "Start latitude about 20 km short, mean latitude about 2 km long."            # before running: how many km will the start-latitude and the mean-latitude flat
                            # versions be off the great circle (1768 km)? two numbers
ROUTE_FLAT_START_KM = 1746.9   # flat, cos(START latitude), km
ROUTE_GC_KM = 1767.8           # great circle (your haversine_m), km
EXPLAIN_COS = "The start column (cos of the Paris latitude) gives 1746.9 km, the closest to the server's 1750 km, so the server most likely took cos at the start (or 111 320 m per degree, 1748.9 km). Paris is the northern end, where the parallels are shortest, so every east metre is shrunk; the mean latitude is the typical latitude of the route and lands within 2 km of the great circle."            # which version comes closest to the server's 1750 km? why is the mean latitude better?

# ---- Step 4: the corridor audit (python3 run_geo.py route) ---------------------------------------
PREDICT_LEG = "About 1.1 m: 34.2 km x (10/1768)^2."  # before reading the leg line: offset of the 10 km mid-route leg, scaled from OFFSET_KM (m)
OFFSET_KM = 34.2             # max_offset_km(Paris, Tunisia), km
LEG_OFFSET_M = 1.09          # max offset of the 10 km leg in the middle of the route, in METRES
EXPLAIN_ROUTE = "The great circle passes north-east of the straight lat/lon line, towards the pole, up to 34 km away, so a corridor of plus or minus 1 km around the straight line held almost none of the tiles under the real path. With short legs of 10 km the great circle and the straight line between the leg ends are only about 1 m apart, so the map corridor and the flown path agree."          # which side does the great circle pass? what did it mean for a ±1 km corridor?
                            # why do short great-circle legs fix it?

# ======== Session 2 — Surveyor (the ellipsoid) ========

# ---- Step 5: radii -------------------------------------------------------------------------------
KM_PER_DEG_LON_ANCHORAGE = 53.736    # 1° of longitude at Anchorage (61.2181°), WGS84, in km
SCALE_NORTH_ZERO_LAT_DEG = 54.81    # latitude where 1° of latitude is exactly 111 320 m (degrees, two decimals)

# ---- Step 6: ECEF --------------------------------------------------------------------------------
GEOCENTRIC_DIFF_DEG = 0.1664   # geodetic − geocentric latitude of a surface point at 30°, in degrees
EXPLAIN_GEOCENTRIC = "The two latitudes agree at the equator and at the pole, by symmetry, so the gap is zero at both ends and peaks in between, near 45.1 degrees."  # why is the difference largest there? (where must the two angles agree?)
GEOCENTRIC_MAX_AT_DEG = 45.1 # the latitude where that difference is largest (degrees)

# ---- Step 7: ENU, and heights ----------------------------------------------------------------------
PREDICT_DROP = "About 100 m below."           # Tallinn (sea level) seen from Helsinki's ENU frame (sea level): up = ?
DROP_M = -530.6                # the `up` of Tallinn printed by python3 run_geo.py enu (m, with its sign)
H_ELLIPSOID_M = 283.8         # a receiver says: 312.4 m above mean sea level, geoid separation −28.6 m.
                            # Height above the WGS84 ellipsoid (m)?

# ---- Step 8: the oracle (python3 compare_oracle.py) -----------------------------------------------
PREDICT_SPHERE = "North +0.56 % (6371/6335.4 - 1), east -0.11 %."  # from radii(0) alone: sphere error (%) 100 km north and east of Quito, signs?
SPHERE_ERR_NORTH_PCT_QUITO = 0.561  # sphere error, 100 km due north of Quito (%, with its sign)
SPHERE_ERR_EAST_PCT_QUITO = -0.112   # sphere error, 100 km due east of Quito (%, with its sign)
EXPLAIN_SPHERE = "At the equator the meridian radius M is 6335 km, smaller than the sphere's 6371 km, so the sphere makes north-south distances too long; the east-west radius N is 6378 km, larger than 6371 km, so east-west distances come out too short."               # why is the sphere too long north-south and too short east-west at the equator?

# ---- Step 9: the error study (python3 error_study.py) ---------------------------------------------
PREDICT_STUDY = "Like d squared because of the curvature; 1 m at about 5 km."          # near home, will enu_flat's error grow like d, d² or d³? where will it reach 1 m at Sousse?
D_1M_SOUSSE_M = 477.4         # from results.json: Sousse, d_1m_m
EXPLAIN_STUDY = "Near home the error grows with slope 1, proportional to the distance: it is a scale error, because enu_flat uses the sphere radius 6371 km instead of the radii M and N of the ellipsoid (0.2 % at Sousse). Far away the slope becomes 2: the curvature and the convergence of the meridians that a flat frame ignores take over."          # what makes the error near home? what takes over far away?

# ---- Step 11: look back (not graded; for you and your teacher) -------------------------------------
LOOK_BACK = "The slope-1 result surprised me."
