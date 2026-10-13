# Lab 6 — your answers. Numbers without quotes (OFFSET_KM = 12.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Navigator (the sphere) ========

# ---- Step 0: which way to Tunisia? ---------------------------------------------------------------
PREDICT_ROUTE = ""          # the shortest path Paris -> central Tunisia: east or west of the straight
                            # lat/lon line? by how many km at most?

# ---- Step 2: bearings (your bearing_deg, Paris -> central Tunisia) -------------------------------
TURN_DEG = 0.0              # arrival heading − departure heading on the great circle (degrees, with sign)
EXPLAIN_BEARING = ""        # why does a great-circle flight change heading, and why to the right here?

# ---- Step 3: the route-length audit (python3 run_geo.py cos) -------------------------------------
PREDICT_COS = ""            # before running: how many km will the start-latitude and the mean-latitude flat
                            # versions be off the great circle (1768 km)? two numbers
ROUTE_FLAT_START_KM = 0.0   # flat, cos(START latitude), km
ROUTE_GC_KM = 0.0           # great circle (your haversine_m), km
EXPLAIN_COS = ""            # which version comes closest to the server's 1750 km? why is the mean latitude better?

# ---- Step 4: the corridor audit (python3 run_geo.py route) ---------------------------------------
OFFSET_KM = 0.0             # max_offset_km(Paris, Tunisia), km
LEG_OFFSET_M = 0.0          # max offset of the 10 km leg in the middle of the route, in METRES
EXPLAIN_ROUTE = ""          # which side does the great circle pass? what did it mean for a ±1 km corridor?
                            # why do short great-circle legs fix it?

# ======== Session 2 — Surveyor (the ellipsoid) ========

# ---- Step 5: radii -------------------------------------------------------------------------------
KM_PER_DEG_LON_ANCHORAGE = 0.0    # 1° of longitude at Anchorage (61.2181°), WGS84, in km
SCALE_NORTH_ZERO_LAT_DEG = 0.0    # latitude where 1° of latitude is exactly 111 320 m (degrees, two decimals)

# ---- Step 6: ECEF --------------------------------------------------------------------------------
GEOCENTRIC_DIFF_DEG = 0.0   # geodetic − geocentric latitude of a surface point at 30°, in degrees
GEOCENTRIC_MAX_AT_DEG = 0.0 # the latitude where that difference is largest (degrees)

# ---- Step 7: ENU, and heights ----------------------------------------------------------------------
PREDICT_DROP = ""           # Tallinn (sea level) seen from Helsinki's ENU frame (sea level): up = ?
DROP_M = 0.0                # the `up` of Tallinn printed by python3 run_geo.py enu (m, with its sign)
H_ELLIPSOID_M = 0.0         # a receiver says: 312.4 m above mean sea level, geoid separation −28.6 m.
                            # Height above the WGS84 ellipsoid (m)?

# ---- Step 8: the oracle (python3 compare_oracle.py) -----------------------------------------------
SPHERE_ERR_NORTH_PCT_QUITO = 0.0  # sphere error, 100 km due north of Quito (%, with its sign)
SPHERE_ERR_EAST_PCT_QUITO = 0.0   # sphere error, 100 km due east of Quito (%, with its sign)
EXPLAIN_SPHERE = ""               # why is the sphere too long north-south and too short east-west at the equator?

# ---- Step 9: the error study (python3 error_study.py) ---------------------------------------------
PREDICT_STUDY = ""          # near home, will enu_flat's error grow like d, d² or d³? where will it reach 1 m at Sousse?
D_1M_SOUSSE_M = 0.0         # from results.json: Sousse, d_1m_m
EXPLAIN_STUDY = ""          # what makes the error near home? what takes over far away?

# ---- Step 11: look back (not graded; for you and your teacher) -------------------------------------
LOOK_BACK = ""
