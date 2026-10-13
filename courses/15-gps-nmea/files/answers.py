# Lab 15 — your answers. Numbers without quotes (BAD_LINES = 12). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — The wire (Step 0 needs no answer) ========

# ---- Step 1: the raw log ------------------------------------------------------------------------
BYTES_PER_S = 0      # bytes per second of the drive log (its size / its 1069 seconds)
LINK_LOAD_PCT = 0    # that rate as a % of what a 9600-baud serial link can carry

# ---- Step 2: checksum and validation ---------------------------------------------------------------
PREDICT_BAD = ""     # how many damaged lines will your is_valid find in 6414? what kinds of damage?
BAD_LINES = -1       # how many lines your is_valid refuses (python3 run_gnss.py log)
EXPLAIN_BAD = ""     # what happened on the wire to them? name at least three kinds of damage

# ---- Step 3: degrees-minutes and GGA ------------------------------------------------------------
IMPOSSIBLE_UTC = ""  # "hhmmss" of the GGA whose checksum is right but whose latitude is impossible
IMPOSSIBLE_WHY = ""  # which check of yours refuses it, and why did the checksum not?

# ---- Step 5: be the saboteur ------------------------------------------------------------------
PREDICT_FORGE_KM = ""   # how far (km) can ONE swap of two characters move the position and still pass?
FORGED_LINE = ""        # your forged line: the original with two characters swapped (keep the quotes)
FORGE_KM = 0.0          # how far your forged line moves the position (python3 run_gnss.py forge)
EXPLAIN_FORGE = ""      # why does the checksum not see it, and what in a navigation stack could?

# ======== Session 2 — The sky ========

# ---- Step 6: DOP experiments ------------------------------------------------------------------
PREDICT_ROTATE = ""  # the whole sky turns by 37° in azimuth: what happens to HDOP, VDOP, EDOP, NDOP?
PREDICT_STREET = ""  # in a north-south street, which is larger: EDOP or NDOP? why?
PREDICT_LOW = ""     # a 7th satellite, low in the ESE: which drops more, HDOP or VDOP?
STREET_EDOP = 0.0    # from python3 run_gnss.py sky (two decimals)
STREET_NDOP = 0.0
EXPLAIN_STREET = ""  # why is the error so much larger in one direction?
EXPLAIN_LOW = ""     # why does one low satellite cut VDOP more than HDOP?

# ---- Step 7: the receiver's DOPs, recomputed ------------------------------------------------------
DOP_MAX_DIFF = -1.0  # largest of the HDOP, PDOP, VDOP differences (python3 run_gnss.py dop)
HDOP_MAX = 0.0       # the largest HDOP of the drive

# ---- Step 8: the judge ----------------------------------------------------------------------------
PREDICT_STATES = ""  # before `drive`: about how many seconds FIX, DEGRADED, NO_FIX out of 1069?
N_FIX = -1           # from python3 run_gnss.py drive
N_DEGRADED = -1
N_NO_FIX = -1
SIGMA_MAX_M = 0.0    # the largest σ your stack stated (one decimal)
JUMP_UTC = ""        # "hhmmss" of the first position your gnss part let through but the jump gate refuses
EXPLAIN_JUMP = ""    # why did gnss.py accept it, how big was its σ, and which part of a stack refuses it?

# ---- Look back (not graded) -----------------------------------------------------------------------
LOOK_BACK = ""
