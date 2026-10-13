# Lab 18 — your answers. Numbers without quotes (HEIGHT_A_M = 101.5). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Measurer ========

# ---- Step 0: ahead or behind? (no code) ----------------------------------------------------------
PREDICT_TILT = "Behind it, to the south: about 200 · tan 15° = 54 m."
                            # fixed under it, looking down. The image centre shows the ground: ahead of the drone
                            # (north) or behind it (south)? How many metres from the point under the drone?

# ---- Step 1: K (TODO 1, TODO 2) --------------------------------------------------------------------
VFOV_INSTA_DEG = 44.51

# ---- Step 2: projection (TODO 3, python3 run_camera.py project) ------------------------------------
MAST_LEAN_PX = 37.7
EXPLAIN_MAST = "The top is 30 m closer to the camera, so the same east/north offset is divided by a smaller depth (120 m instead of 150 m) and lands farther from the centre: tall objects lean away from the image centre. A flat-ground model puts the top of the mast at the wrong ground point."
                            # for a camera that assumes flat ground?

# ---- Step 3: back-projection (TODO 4, python3 run_camera.py centre) --------------------------------
CENTRE_BEHIND_M = 53.59
                            # the image centre (m, positive)
EXPLAIN_TILT = "The camera is fixed to the body and looks along the body's down axis. When the nose goes down the belly turns backwards, so the optical axis points behind the drone, h·tan(15°) = 53.6 m back."
CENTRE_ROLL_E_M = -62.41
CENTRE_ROLL_N_M = -17.58
EXPLAIN_T = "project goes world to camera, so it must undo R_wc with its inverse, the transpose R_wcᵀ; backproject_ground goes the other way, camera to world, which is exactly what R_wc does."

# ---- Step 4: measure the height (TODO 5, TODO A, TODO C, python3 measure_pad.py) -----------------------------
PREDICT_PAD = "A: the pad is bigger in pixels there, so one pixel is a smaller fraction of it."
HEIGHT_A_M = 134.0
HEIGHT_B_M = 261.8
HEIGHT_B_RANGE_M = 23.9
EXPLAIN_PIXEL = "Photo B is higher, so the pad covers only 22 pixels instead of 43; one pixel is 4.5 % of the pad instead of 2.3 %, and the height is proportional to 1/pixels, so the same ±1 px gives about twice the relative error."

# ---- Step 5: where is the pad? (TODO B, python3 measure_pad.py) -------------------------------------
PAD_T_E_M = -17.9
PAD_T_N_M = -66.0
LEVEL_ERROR_M = 45.9
HEIGHT_SHIFT_M = 8.04
EXPLAIN_HEIGHT_SHIFT = "The pixel's ray is fixed; the ground point is C + λ·d with λ = −h/d_z, so its distance from the point under the drone is proportional to h: 150 instead of 170 m shortens it by 20/170."
EXPLAIN_LEVEL = "Assuming a level camera ignores the 14° nose-down pitch and 5° roll, so every ray is turned and lands tens of metres away (45.9 m here). A matcher needs the attitude at the photo instant (from the IMU) to back-project or straighten the photo first."

# ======== Session 2 — Straightener ========

# ---- Step 6: footprints (TODO 6, python3 run_camera.py footprint) -----------------------------------
PREDICT_AREA = "About 1.5 times."
AREA_RATIO_30 = 1.92
EXPLAIN_FOOTPRINT = "The far edge of the image is seen at a larger distance (slant range), and the same angle covers more ground far away, so the far side is wider and longer; the near side is close and narrow."

# ---- Step 7: height error -> scale error (your gsd, no new code) ------------------------------------
SCALE_PLATEAU = 0.6
VERDICT_PLATEAU = "refused"
HEIGHT_FROM_SCALE_M = 324.0

# ---- Step 8: what an attitude error costs (TODO 7) -------------------------------------------------
PREDICT_ATTACK = "About 7°."
                            # point by 30 m? (degrees, a guess)
ATTACK_DTILT_DEG = 6.60
ATTACK_DTILT_35_DEG = 4.36
EXPLAIN_ATTACK = "The ground point is h·tan(tilt) from the drone, and tan grows faster at larger angles (its slope is 1/cos²): a tilted camera turns the same attitude error into a bigger ground error, so it needs a better attitude."

# ---- Step 9: straighten photo T (TODO 8, python3 run_camera.py straighten) --------------------------
PREDICT_STRAIGHT = "About 12 / 0.354 = 34 px wide, centre near (429, 456) from Step 5's position."
                            # drone be, and will the pad look square?
STRAIGHT_PAD_PX = 35
STRAIGHT_PAD_E_M = -18.0
STRAIGHT_PAD_N_M = -66.1
EXPLAIN_STRAIGHT = "The real and the level camera share the same centre and only rotate, so every pixel ray just turns: K·Rᵀ·R·K⁻¹ maps rays to rays and does not need the depth. Only measuring metres in the straightened view needs flat ground and the height."

# ---- Step 12: look back (not graded; for you and your teacher) -------------------------------------
LOOK_BACK = ""

# ======== Going further (optional, not graded) ========
SLOPE_SHIFT_M = 0.0
GATE_REFUSED_PCT = 0.0
GOING_FURTHER = ""
