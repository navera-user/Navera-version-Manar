# Lab 25 — reference answers (teacher). Numbers measured with the reference solution and
# solutions/25-thermal-night/my_homography.pt (16 000 pairs, 8 epochs, GPU). See TEACHER.md.

PREDICT_LOOK = "B (night) should be easiest because it keeps the shapes of A, D (dawn) hardest because it has no contrast; C reverses some materials."
PREDICT_AUDIT = "Low, maybe 0.2 or 0.3, because the materials change their brightness order at night."
TWIN_OF_NIGHT_01 = 9
AUDIT_BEST_NCC = 0.90
EXPLAIN_AUDIT = ("The night frames are day photos made darker: each one has an NCC of about 0.9 with one day frame, "
                 "far above the second best, they show sun shadows, and the twin is 8 frames later, so the labels "
                 "put each night frame at the wrong place.")

PREDICT_FIRST_CAM = "No, I think it needs more than 400 m."
COV_350_0 = 0.952
MIN_ALT_FIRST_0 = 474
MIN_ALT_FIRST_45 = 524
EXPLAIN_COVERAGE = ("At 45 degrees the corners of the square stick out of the turned rectangle, so more height is "
                    "needed; the first camera needs at least 474 m, above the 400 m ceiling, so it can never give a "
                    "night fix.")
REFUSED_FRAME = 7

PREDICT_NCC = "Day vs day yes; night and noon no because materials reverse; inverted maybe half; dawn no contrast."
NCC_GOOD_SAME = 1.00
NCC_GOOD_NIGHT = 0.23
NCC_GOOD_INVERTED = 0.39
EXPLAIN_NCC = ("NCC only undoes a gain and an offset, so it works for the same kind of picture; at night the road "
               "reverses but trees do not, the relation is not monotonic, and inverting fixes only some materials.")

GATE_REFUSED = [8.0, 34.0, 36.0, 38.0, 40.0]
EXPLAIN_GATE = ("At 8 s the jump was 256 m but the reach after 2 s was only 90 m. At 32 s the gap of 14 s made the "
                "reach 450 m so the wrong fix passed and became the anchor; after it every correct fix was too far "
                "from that wrong anchor and refused: the gate locked onto a wrong position.")

EXPLAIN_CORNERS = ("The 8 numbers are the x and y offsets of the frame's 4 corners in the reference patch; corners are "
                   "all pixels of the same size and bounded, while the 9 entries of H have very different scales.")
EXPLAIN_NORM = ("The thermal camera's automatic gain changes brightness and contrast, and the reference is pale, so "
                "each channel loses its own mean and std; the + 1 stops a uniform sea patch from blowing its noise up.")
PREDICT_PARAMS = "fc1, because it sees every number of the last maps."
N_PARAMS_FC1 = 131200
VAL_CENTRE_PX = 3.84
PREDICT_OVERFIT = "The training loss will fall a lot and the validation loss will stop falling and rise."
EXPLAIN_OVERFIT = ("The training loss fell to 0.016 while the validation loss stopped near 0.16 at epoch 17 and rose: "
                   "with only 3 places the network memorised them instead of learning to align any ground. I would "
                   "have stopped at about epoch 17.")
PREDICT_ABLATION = "a: without normalisation I expect it to be clearly worse, maybe 5 px instead of 3.8."
ABLATION = "a"
ABLATION_PX = 5.08
EXPLAIN_ABLATION = ("Without per-channel normalisation the error was 5.08 px instead of my 3.83 px, so the author's "
                    "choice was worth it: the network had to learn the camera's gain and the pale reference from "
                    "examples. One run is not proof, but 1.2 px is much more than the 0.1-0.2 px seed noise.")
NET_NIGHT_PX = 3.8
NCC_NIGHT_PX = 14.5
NET_NOON_PX = 12.1
EXPLAIN_LEARNED = ("It was trained only on night pairs, so it learned the night relation between materials; at noon "
                   "and dawn the data is different and it is no better than the prior. Before trusting it I would "
                   "test it on real thermal frames with true positions, other seasons and weather.")
PREDICT_STRICT = "Much worse than the prior, because random weights give random corners."
MISSING_KEYS = 12
EXPLAIN_STRICT = ("With strict=False no layer name matched and no error was raised, so the network kept its random "
                  "weights and still answered; after LOC-6 NAVERA refuses to start if the weights do not load.")
FLY_MEDIAN_M = 25.0
LOOK_BACK = ""
