# Lab 18 — your answers. Numbers without quotes (HEIGHT_A_M = 101.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Measurer ========

# ---- Step 0: ahead or behind? (no code) ----------------------------------------------------------
PREDICT_TILT = ""           # 200 m above flat ground, nose north, the drone pitches 15° nose DOWN. The camera is
                            # fixed under it, looking down. The image centre shows the ground: ahead of the drone
                            # (north) or behind it (south)? How many metres from the point under the drone?

# ---- Step 1: K (TODO 1, TODO 2) --------------------------------------------------------------------
VFOV_INSTA_DEG = 0.0        # NAVERA's straightened Insta360 view: 1920 × 540 px, HFOV 111°. Its VERTICAL FOV (°)?

# ---- Step 2: projection (TODO 3, python3 run_camera.py project) ------------------------------------
MAST_LEAN_PX = 0.0          # distance in pixels between the top and the foot of the 30 m mast in the image
EXPLAIN_MAST = ""           # why does the top appear FARTHER from the image centre than the foot? What does it mean
                            # for a camera that assumes flat ground?

# ---- Step 3: back-projection (TODO 4, python3 run_camera.py centre) --------------------------------
CENTRE_BEHIND_M = 0.0       # 200 m, nose down 15°: distance from the point under the drone to the ground point of
                            # the image centre (m, positive)
EXPLAIN_TILT = ""           # why does a nose-down drone's camera look BEHIND it? (your side view)
CENTRE_ROLL_E_M = 0.0     # YOUR backproject_ground: the image centre (480, 270), camera 200 m up, heading 40°,
CENTRE_ROLL_N_M = 0.0     # pitch −15°, roll +10° (camera_rotation_hpr) — metres east and north
EXPLAIN_T = ""            # why does project() need R_wc.T while backproject_ground() uses R_wc itself?

# ---- Step 4: measure the height (TODO 5, TODO A, python3 measure_pad.py) -----------------------------
PREDICT_PAD = ""            # before running: which photo, A or B, will give the more precise height? why?
HEIGHT_A_M = 0.0            # height of the camera of photo A (m, one decimal)
HEIGHT_B_M = 0.0            # height of the camera of photo B (m, one decimal)
HEIGHT_B_RANGE_M = 0.0      # photo B: width of the ±1 px range (largest − smallest height, m)
EXPLAIN_PIXEL = ""          # why is one photo's height so much less precise than the other's?

# ---- Step 5: where is the pad? (TODO B, python3 measure_pad.py) -------------------------------------
PAD_T_E_M = 0.0             # photo T: the pad's position, metres EAST of the point under the drone
PAD_T_N_M = 0.0             # photo T: the pad's position, metres NORTH of the point under the drone
LEVEL_ERROR_M = 0.0         # YOUR backproject_ground with a LEVEL camera (camera_rotation_hpr(40)) on the same
                            # pixel: its distance to the pad (m)
HEIGHT_SHIFT_M = 0.0        # YOUR backproject_ground with the right attitude but 150 m instead of 170 m:
                            # how far the pad moves (m)
EXPLAIN_LEVEL = ""          # what did the level assumption get wrong, and what does a matcher need to avoid it?

# ======== Session 2 — Straightener ========

# ---- Step 6: footprints (TODO 6, python3 run_camera.py footprint) -----------------------------------
PREDICT_AREA = ""           # before running: at nose-down 30°, how many times the nadir footprint's area?
AREA_RATIO_30 = 0.0         # area at pitch −30° / area at pitch 0° (two decimals)
EXPLAIN_FOOTPRINT = ""      # why is the footprint a trapezoid whose FAR side is the wide one?

# ---- Step 7: height error -> scale error (your gsd, no new code) ------------------------------------
SCALE_PLATEAU = 0.0         # the fitted scale on the plateau (true GSD / predicted GSD, two decimals)
VERDICT_PLATEAU = ""        # "accepted" or "refused" by a ±15 % scale gate
HEIGHT_FROM_SCALE_M = 0.0   # predicted height 300 m, the match fits a scale of 1.08: the measured height (m)

# ---- Step 8: what an attitude error costs (TODO 7) -------------------------------------------------
PREDICT_ATTACK = ""         # before computing: at 250 m and 8° of tilt, how large a tilt error moves the centre
                            # point by 30 m? (degrees, a guess)
ATTACK_DTILT_DEG = 0.0      # the smallest positive tilt error that moves it by 30 m or more (tilt 8°), two decimals
ATTACK_DTILT_35_DEG = 0.0   # the same at a tilt of 35° (two decimals)
EXPLAIN_ATTACK = ""         # why does a tilted camera need a better attitude than a level one?

# ---- Step 9: straighten photo T (TODO 8, python3 run_camera.py straighten) --------------------------
PREDICT_STRAIGHT = ""       # before running: in the level, north-up view, how many px wide will the pad be, and at
                            # which pixel (u, v) do you expect its centre? (Step 5's position, the GSD at 170 m)
STRAIGHT_PAD_PX = 0         # the pad's width in the straightened view (px, an int)
STRAIGHT_PAD_E_M = 0.0      # the pad's position measured in the straightened view: metres east (one decimal)
STRAIGHT_PAD_N_M = 0.0      # ... and metres north (one decimal)
EXPLAIN_STRAIGHT = ""       # why can a single 3 × 3 matrix straighten the whole photo without knowing any depth?

# ---- Step 12: look back (not graded; for you and your teacher) -------------------------------------
LOOK_BACK = ""
