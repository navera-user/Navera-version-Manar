# Lab 15 — your answers. Numbers without quotes (BAD_LINES = 12). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — The wire (Step 0 needs no answer) ========

# ---- Step 1: the raw log ------------------------------------------------------------------------
BYTES_PER_S = 410.6      # bytes per second of the drive log (its size / its 1069 seconds)
LINK_LOAD_PCT = 42.8    # that rate as a % of what a 9600-baud serial link can carry

# ---- Step 2: checksum and validation ---------------------------------------------------------------
PREDICT_BAD = "about 10: some cut lines and a few flipped characters"     # how many damaged lines will your is_valid find in 6414? what kinds of damage?
BAD_LINES = 7       # how many lines your is_valid refuses (python3 run_gnss.py log)
EXPLAIN_BAD = ("The checksum refused them: one GGA had a flipped character, one GGA was cut, one RMC lost its checksum, one line was garbage, two sentences were glued when a line ending was lost, a GSV had a non-ASCII byte and a GSA had a flipped character in its VDOP.")     # what happened on the wire to them? name at least three kinds of damage

# ---- Step 3: degrees-minutes and GGA ------------------------------------------------------------
IMPOSSIBLE_UTC = "051731"  # "hhmmss" of the GGA whose checksum is right but whose latitude is impossible
IMPOSSIBLE_WHY = ("dm_to_deg refuses it because 74 minutes is not below 60. The checksum did not see it because two digits were only swapped, and XOR does not depend on the order of the characters.")  # which check of yours refuses it, and why did the checksum not?

# ---- Step 5: be the saboteur ------------------------------------------------------------------
PREDICT_FORGE_KM = "maybe 50 km, like the 74-minute line"   # how far (km) can ONE swap of two characters move the position and still pass?
FORGED_LINE = "$GPGGA,052200.00,5345.89257,N,01045.14417,E,1,12,0.77,2.1,M,32.0,M,,*59"        # your forged line: the original with two characters swapped (keep the quotes)
FORGE_KM = 2001.509          # how far your forged line moves the position (python3 run_gnss.py forge)
EXPLAIN_FORGE = ("XOR does not depend on the order of the characters, so a swap keeps the checksum, and 53° is a possible latitude. Only a plausibility check can see it: the jump gate compares it with the last trusted fix and 2000 km in one second is impossible.")      # why do the checksum AND your range checks not see it, and what in a stack could?

# ======== Session 2 — The sky ========

# ---- Step 6: DOP experiments ------------------------------------------------------------------
PREDICT_ROTATE = "nothing changes, the satellites keep the same angles between them"  # the whole sky turns by 37° in azimuth: what happens to HDOP, VDOP, EDOP, NDOP?
PREDICT_STREET = "NDOP, because the satellites are north and south"  # in a north-south street, which is larger: EDOP or NDOP? why?
PREDICT_LOW = "HDOP, because the new satellite fills a gap in the sky"     # a 7th satellite, low in the ESE: which drops more, HDOP or VDOP?
STREET_EDOP = 3.26    # from python3 run_gnss.py sky (two decimals)
STREET_NDOP = 0.80
EXPLAIN_STREET = ("The satellites are all along the north-south street, so their ranges change when we move north or south but hardly when we move east or west: the east error, across the street, is four times larger.")  # why is the error so much larger in one direction?
EXPLAIN_LOW = ("Every other satellite is high, so their -u_U are all clearly negative and the Up column looks like a multiple of the clock column. The low satellite has -u_U close to 0, so it breaks that proportion and the solver can separate height from clock; horizontally it is just one more direction.")     # why does one low satellite cut VDOP more than HDOP?

# ---- Step 7: the receiver's DOPs, recomputed ------------------------------------------------------
DOP_MAX_DIFF = 0.005  # largest of the HDOP, PDOP, VDOP differences (python3 run_gnss.py dop)
HDOP_MAX = 18.8       # the largest HDOP of the drive

# ---- Step 8: the judge ----------------------------------------------------------------------------
PREDICT_STATES = "1000 FIX, 10 DEGRADED, 59 NO_FIX"  # before `drive`: about how many seconds FIX, DEGRADED, NO_FIX out of 1069?
N_FIX = 976           # from python3 run_gnss.py drive
N_DEGRADED = 30
N_NO_FIX = 63
SIGMA_MAX_M = 37.6    # the largest σ your stack stated (one decimal)
JUMP_UTC = "052421"        # "hhmmss" of the first position your gnss part let through but the jump gate refuses
EXPLAIN_JUMP = ("Two digits of the latitude minutes were swapped: the checksum is still valid, the minutes are below 60 and the quality is 1, so gnss.py accepted it with a small sigma of 1.5 m from HDOP 0.77. The jump gate of the arbiter refuses it: 665 m in 1 s is more than 100 m/s x 1 s + 50 m.")    # why did gnss.py accept it, how big was its σ, and which part of a stack refuses it?

# ---- Look back (not graded) -----------------------------------------------------------------------
LOOK_BACK = ""
