# Lab 19 — your answers. Numbers without quotes (MY_FX = 671.2). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… / REASON_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Lens modeller ========

# ---- Step 0: pinhole or fisheye? (no code) ---------------------------------------------------------
PREDICT_EDGE = ""           # Two cameras with the same f = 600 px: a pinhole (r = f·tan θ) and an ideal fisheye
                            # (r = f·θ). A ray at 80° and a ray at 40° from the axis: for EACH camera, how many
                            # times farther from the centre is the 80° ray than the 40° ray? (a guess)

# ---- Step 1: the data -------------------------------------------------------------------------------
CALIB_SIZE = (0, 0)         # the picture size the bench calibration is for: (width, height) in pixels

# ---- Step 2: the fisheye projection (TODO 1) ---------------------------------------------------------
STEP2_U = 0.0               # YOUR fisheye_project of X_c = (−1.6, 0.4, 1.4) m with the bench calibration: u (px)
STEP2_V = 0.0               # ... and v (px), two decimals
PINHOLE_GAP_PX = 0.0        # distance (px) between that pixel and the ideal PINHOLE pixel with the same K (one decimal)

# ---- Step 3: where is the model valid? (TODO 2, python3 run_lens.py curve) ---------------------------
PIXEL_ANGLE_DEG = 0.0       # YOUR theta_from_theta_d: the angle from the optical axis of pixel (1500, 100), degrees
EXPLAIN_TURN_BACK = ""      # why does the calibrated curve turn back down after 67.4°, when a real lens never does?

# ---- Step 4: how wide? (TODO 3, python3 run_lens.py stretch) -----------------------------------------
PREDICT_STRETCH = ""        # before running: at the LEFT/RIGHT EDGE of the 111° straight view, how many straight-view
                            # pixels are made from one lens pixel? (a guess)
STRETCH_EDGE_111 = 0.0      # the stretch at the edge of the 111° view (two decimals)
H_MAX_DEG = 0.0             # the widest straight view with f_new ≥ fx for the bench lens, 1920 px wide (two decimals)
H_MAX_PARTNER_DEG = 0.0     # the same rule for a partner's camera: fx = 540 px, pictures 1920 px wide (two decimals)
EXPLAIN_FOV = ""            # as the trade-off engineer: why 111° and not 150° for NAVERA? Use two numbers.

# ---- Step 5: straighten (TODO 4, python3 run_lens.py straighten) -------------------------------------
BEND_BEFORE_PX = 0.0        # f0216: the most bent chessboard line in the fisheye picture (px)
BEND_AFTER_PX = 0.0         # ... and in your straightened 111° picture (px)
EXPLAIN_RESIDUAL = ""       # why is the "after" value not 0?

# ======== Session 2 — Calibrator ========

# ---- Step 7: your calibration (TODO 5, TODO 6, python3 calibrate_lab.py calibrate) ----------------------
PREDICT_FX = ""             # before running: will your fx be the bench's 660.5 px? higher, lower, how far?
MY_FX = 0.0                 # your calibration: fx (px, two decimals)
MY_RMS = 0.0                # your calibration: RMS (px, three decimals)
VIEWS_USED = 0              # how many views your calibration used
REFUSED_VIEWS = []          # the names of the views OpenCV refused, e.g. ["f0001", "f0002"]
FARTHEST_USED_DEG = 0.0     # the farthest corner used by your calibration, degrees from the optical axis
EXPLAIN_REFUSED = ""        # detective: what do the refused views have in common, and why can OpenCV not trust them?

# ---- Step 8: the reprojection error (TODO 7) ----------------------------------------------------------
WORST_VIEW = ""             # the used view with the largest RMS, e.g. "f0001"

# ---- Step 9: stability (python3 calibrate_lab.py stability) --------------------------------------------
FX_STD_8 = 0.0              # the spread (std) of fx with 8 views (px, one decimal)
FX_STD_30 = 0.0             # ... with 30 views
EXPLAIN_STABILITY = ""      # what do these spreads say about "RMS 0.5 px" and about how many views to take?

# ---- Step 10: the honest test (TODO 8, python3 calibrate_lab.py holdout, then curves) -------------------
TRAIN_RMS = 0.0             # fisheye: train RMS (px, three decimals)
TEST_RMS = 0.0              # fisheye: test RMS on the 8 unseen views (px, three decimals)
BC_TEST_RMS = 0.0           # Brown–Conrady: test RMS on the same 8 views (px, three decimals)
REASON_BC = ""              # the lesson says a fisheye lens needs the fisheye model, yet Brown–Conrady does as well on
                            # the hold-out. Why is there no contradiction? (my_curves.png helps)

# ---- Step 11: the calibration tool --------------------------------------------------------------------------
CLI_HFOV_DEG = 0.0          # the straight-view width your my_calib.yaml says (out_hfov_deg)
REASON_FX = ""              # why is your fx (and the tool's) not the bench's 660.5 px? Give two reasons.
REASON_HFOV = ""            # why does your file say CLI_HFOV_DEG and not 111°?

# ---- Step 12: look back (not graded; for you and your teacher) --------------------------------------
LOOK_BACK = ""

# ======== Going further (optional, not graded; your teacher reads them) ========
ZHANG_FX = 0.0              # Zhang's closed form by hand: the fx it gives
GOING_FURTHER = ""          # anything else you tried (fewer parameters, your calibration at work, …)
