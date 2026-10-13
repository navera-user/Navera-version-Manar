# Lab 21 — your answers. Numbers without quotes (REP_SIFT_ZOOM4 = 0.71). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Scout & detector ========

# ---- Step 0: the scout (no code) ---------------------------------------------------------------
PREDICT_RANK = "city, olives, coast, fields, saltpans, sea; I would trust the city most"        # the six terrains, from the MOST keypoints to the fewest, and the one you would trust most
                         # to be found on a map (look at out/… only after you wrote this: see the lab)

# ---- Steps 2–3: the house ---------------------------------------------------------------------
KIND_1 = "flat"              # "flat", "edge" or "corner" (from YOUR eigen2 and harris on the printed Sxx, Syy, Sxy)
KIND_2 = "edge"
KIND_3 = "corner"
R_POINT_3 = 5674          # the Harris response R (k = 0.04) of point 3, computed from its Sxx, Syy, Sxy (no decimals)
EXPLAIN_EIGEN = "Each eigenvalue says how fast the window content changes when it moves in one direction: both small is flat, one large is an edge, both large is a corner. Harris uses the determinant and the trace instead, which give the product and the sum of the eigenvalues without a square root at every pixel."       # what do the two eigenvalues say about a window, and why does Harris not compute them?

# ---- Step 4: repeatability ----------------------------------------------------------------------
PREDICT_ZOOM = "Harris, because its window has a fixed size"        # which detector will suffer most when the photo is 4 times closer, and why?
REP_HARRIS_ROT35 = 0.85   # from `repeat`, two decimals
REP_HARRIS_ZOOM4 = 0.39
REP_SIFT_ZOOM4 = 0.78
CHANCE = 0.08             # the chance level of the table (all rows show the same)
EXPLAIN_SCALE = "R depends only on the eigenvalues, which a rotation does not change, so Harris keeps 0.85 after the turn. Its window is fixed, so in a photo 4 times closer it finds small details that the map does not have and drops to 0.39, while SIFT chooses a scale for each point and keeps 0.78, far above the chance level of 0.08."       # why does Harris survive the turn but not the 4× zoom, while SIFT survives both?

# ---- Step 5: terrains ----------------------------------------------------------------------------
MOST_KEYPOINTS = "olives"      # the terrain with the most SIFT keypoints (OpenCV's default contrast)
SIFT_FIELDS = 71          # SIFT keypoints of terrain_fields.png (default contrast)
DARK_SIFT_BEFORE = 17     # drone_city_dark.jpg: SIFT keypoints before CLAHE
DARK_SIFT_AFTER = 632      #                      and after CLAHE
EXPLAIN_TERRAIN = "The olive grove has three times more keypoints than the city but they are repetitive: every tree looks like the others, so a descriptor has many look-alikes and ORB repeated only 0.35 there. The fields looked textured to me but are almost uniform (71 keypoints). Many keypoints is not the same as distinct, well spread keypoints."     # which terrain fooled your Step 0 ranking, and why many keypoints do not mean easy matching

# ======== Session 2 — Learner ========

# ---- Step 6: binary descriptors -----------------------------------------------------------------
HAMMING_SAME = 61         # median Hamming distance, same ground point (from `hamming`)
HAMMING_RANDOM = 127       # median Hamming distance, random pairs
EXPLAIN_HAMMING = "For unrelated points each of the 256 bits is like a coin toss, so about half differ: 128. The same ground point differs in only about 61 bits, so a matcher can keep the nearest descriptor and reject pairs whose distance is close to the random level."     # why is the random median close to 128, and what does the gap allow?

# ---- Step 7: the network ---------------------------------------------------------------------------
PREDICT_PARAMS = "about 100 000"      # before you count: how many numbers does PatchNet learn? (a guess)
N_PARAMS_CONV1 = 160       # the parameters of conv1 alone, by hand (weights + biases)

# ---- Steps 9–10: training and overfitting -----------------------------------------------------------
VAL_SCORE_FULL = 0.957     # the matching score printed after the full training (three decimals)
PREDICT_OVERFIT = "the training loss will go to almost zero and the validation loss will stop falling"     # with only 300 training pairs and 30 epochs: what will the two loss curves do?
EXPLAIN_OVERFIT = "With 300 pairs the training loss fell to almost 0 but the validation loss stopped near 0.35 after about 12 epochs and then rose a little: the network memorised the 300 training patches instead of learning what makes a ground point recognisable. I would stop around epoch 12, or use more data."     # what happened to the train and validation losses with 300 pairs, and why?

# ---- Step 11: learned vs OpenCV --------------------------------------------------------------------
SCORE_ORB = 0.756          # from `compare`, three decimals
SCORE_SIFT = 0.875
SCORE_UNTRAINED = 0.530
SCORE_LEARNED = 0.957
EXPLAIN_LEARNED = "It was trained on exactly this kind of pairs, drawn map views with the same blur, turns and noise, so it learned what changes and what stays. Before trusting it on a drone I would test it on real camera frames against the map, with other light, seasons and real buildings, and compare again with SIFT."     # why does your network win here, and what would you need before trusting it on a real drone?

# ---- Look back (not graded) ----
LOOK_BACK = ""
