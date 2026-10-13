# Lab 19 — your answers. Numbers without quotes (MY_FX = 671.2). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… / REASON_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Lens modeller ========

# ---- Step 0: pinhole or fisheye? (no code) ---------------------------------------------------------
PREDICT_EDGE = "Pinhole: tan 80 / tan 40 is about 6.8 times; fisheye: 80 / 40 = 2 times."

# ---- Step 2: the fisheye projection (TODO 1) ---------------------------------------------------------
STEP2_U = 331.98
STEP2_V = 482.88
PINHOLE_GAP_PX = 155.2

# ---- Step 3: where is the model valid? (TODO 2, python3 run_lens.py curve) ---------------------------
PIXEL_ANGLE_DEG = 47.82
EXPLAIN_TURN_BACK = ("The polynomial was fitted only on corners within about 52 degrees of the axis; beyond the data "
                     "it extrapolates, and four numbers can bend the curve back down where no corner was seen.")

# ---- Step 4: how wide? (TODO 3, python3 run_lens.py stretch) -----------------------------------------
PREDICT_STRETCH = "About 3, like 1/cos² of 55.5 degrees."
STRETCH_EDGE_111 = 2.51
H_MAX_DEG = 110.94
H_MAX_PARTNER_DEG = 121.28
EXPLAIN_FOV = ("At 111 degrees f_new is 659.8 px, so the centre keeps 99.9 % of the lens detail; at 150 degrees "
               "f_new is 257 px and the centre keeps only 38.9 %, and the edges at 75 degrees are beyond the valid "
               "model. Map matching needs the centre detail more than a wider, stretched view.")

# ---- Step 5: straighten (TODO 4, python3 run_lens.py straighten) -------------------------------------
BEND_BEFORE_PX = 5.12
BEND_AFTER_PX = 0.63
EXPLAIN_RESIDUAL = ("The calibration itself only fits the corners to about 0.5 px RMS, the corner detector has its own "
                    "noise, and the screen showing the board is not perfectly flat, so a fraction of a pixel remains.")

# ======== Session 2 — Calibrator ========

# ---- Step 7: your calibration (TODO 5, TODO 6, python3 calibrate_lab.py calibrate) ----------------------
PREDICT_FX = "Close to 660.5, maybe a few pixels different because the views are not all the same."
MY_FX = 670.28
MY_RMS = 0.506
VIEWS_USED = 34
REFUSED_VIEWS = ["f0023", "f0208"]
FARTHEST_USED_DEG = 43.0
EXPLAIN_REFUSED = ("Both refused views put the board far to the right, with corners 45 and 52 degrees from the axis, "
                   "farther than any other view; there the model is barely constrained, so their pose is "
                   "ill-conditioned. Refusing them means the calibration has no corner beyond 43 degrees.")

# ---- Step 8: the reprojection error (TODO 7) ----------------------------------------------------------
WORST_VIEW = "f0022"

# ---- Step 9: stability (python3 calibrate_lab.py stability) --------------------------------------------
PREDICT_STD = "About 10 px with 8 views and 2 px with 30."
FX_STD_8 = 38.9
FX_STD_30 = 3.4
EXPLAIN_STABILITY = ("Each subset fits its own corners to about 0.5 px, yet fx moves by tens of pixels with 8 views "
                     "and a few pixels with 30: the RMS does not show this spread, so a calibration needs many "
                     "varied views, 30 or more.")

# ---- Step 10: the honest test (TODO 8, python3 calibrate_lab.py holdout, then curves) -------------------
TRAIN_RMS = 0.474
TEST_RMS = 0.567
BC_TEST_RMS = 0.570
REASON_BC = ("All the test corners are within about 43 degrees of the axis, where tan is still small and a "
             "Brown–Conrady polynomial can follow the lens; the angle curves part beyond the corners, where the "
             "hold-out does not test, and Brown–Conrady runs away towards its tan 90 degrees limit at the edges.")

# ---- Step 11: the calibration tool --------------------------------------------------------------------------
CLI_HFOV_DEG = 110.15
REASON_FX = ("Different views: the course has 36 of the bench session's 39 views, and the three left out are enough to "
             "move fx, since none of my 30-view subsets reached 660.5 px (664.8 to 675.1). And fx trades against the "
             "board distance with the same RMS of about 0.5 px, so the RMS cannot tell 660 from 670.")
REASON_HFOV = ("NAVERA's rule keeps f_new at least fx: with my fx of 670.3 px the widest view is "
               "2 atan(960 / 670.3) = 110.15 degrees, narrower than with the bench fx of 660.5 px.")

# ---- Step 12: look back (not graded; for you and your teacher) --------------------------------------
LOOK_BACK = ""

# ======== Going further (optional, not graded; your teacher reads them) ========
ZHANG_FX = 0.0
GOING_FURTHER = ""
