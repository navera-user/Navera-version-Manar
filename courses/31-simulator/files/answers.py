# Lab 31 — your answers. Numbers without quotes (JAM_RECOVER_S = 3.4). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Messenger ========

# ---- Step 0: the bytes (python3 mav_lab.py hex) -----------------------------------------------------------------
PREDICT_FRAME = ""          # BEFORE running: how many bytes do you expect in ONE GPS_INPUT frame, and why?
HEADER_LEN_BYTE = 0         # the 'len' byte of the first GPS_INPUT frame, as a decimal number
EXPLAIN_63 = ""             # why is it not 65, and what must a receiver do about it?

# ---- Steps 2–3: the recording through YOUR decoder (python3 mav_lab.py stream) ----------------------------------
STREAM_FRAMES = 0           # how many frames your parse_frames finds in the recording
STREAM_BAD_CRC = 0          # how many of them have crc_ok False
STREAM_LOST = 0             # your lost_frames on the good GPS_INPUT frames: lost …
STREAM_DOUBLED = 0          # … and doubled
VISION_FLAGS = 0            # the ignore_flags of the frames sent while day vision flew (satellites 0)
EXPLAIN_FLAGS = ""          # what do those frames tell the autopilot NOT to use, and why is that honest?
EXPLAIN_LOST = ""           # the recording has 2 frames with a bad checksum: how do they show up in "lost"? why?

# ---- Step 4: the receiver's noise (python3 mav_lab.py noise) -----------------------------------------------------
PREDICT_AVERAGE = ""        # BEFORE running: you average the GPS noise over 10 s (50 fixes). By how much does the
                            # spread go down: about √50 ≈ 7 times, or less? why?
GM_SIGMA_MEASURED = 0.0     # the measured standard deviation of the hour of noise (m)
CORR_10S = 0.0              # your autocorrelation at 10 s
EXPLAIN_AVERAGE = ""        # why do 10 s averages spread almost as much as single fixes?

# ---- Step 5: vision errors (python3 mav_lab.py rayleigh) ---------------------------------------------------------
RAYLEIGH_P95_15 = 0.0       # your rayleigh_quantile(15.0, 0.95), in m
EXPLAIN_MEDIAN = ""         # the 'measured' profile has a MEDIAN of 440 m. Why is its σ 373.7 m and not 440 m?

# ======== Session 2 — Test engineer ========

# ---- Step 6: a first flight (python3 -m navera_lite.sim.run campaign/jam.json) ---------------------------------
PREDICT_JAM = ""            # BEFORE running: GPS jammed at 30 s, back at 70 s. When does NAVERA Lite use the GPS
                            # again: at 70 s, a little later, much later? why?
JAM_RECOVER_S = 0.0         # from the events: the time NAVERA Lite flies on the GPS again, minus 70 s

# ---- Step 8: expected values FROM THE RULES (before the campaign) -------------------------------------------------
EXPECT_OFF_SWITCH_S = 0.0   # GPS "off" (silent) at 30 s: after how many seconds should NAVERA Lite stop using it?
EXPECT_JUMP_GATE_M = 0.0    # the jump gate's reach for the next GPS fix (0.2 s later), drone: in metres
EXPECT_DRIFT_REFUSED_S = 0.0  # drift_alarm_time for the campaign's drift (lab Step 8 gives the numbers), in s

# ---- Step 9: the campaign (python3 campaign.py run, then report) -------------------------------------------------
DRIFT_MEASURED_S = 0.0      # the drift run's switch_s: when NAVERA Lite really stopped flying on the spoofed GPS
EXPLAIN_DRIFT = ""          # expected vs measured: why are they not equal? which one would you put in a requirement?
FAILED = ""                 # the id of the requirement that FAILS (for example "R3")
EXPLAIN_FAIL = ""           # your diagnosis: what went wrong, step by step, and what would fix it
                            # (then confirm with campaign/plane_delayed.json, lab Step 9)

# ---- Step 10: your own stack (python3 campaign.py run --mine, then report --mine) --------------------------------
EXPLAIN_MINE = ""           # which of your parts flew? did any verdict change compared with the course's parts? why?

# ---- Step 11: your networks in the loop (python3 vision_check.py, then the night flight) -------------------------
NIGHT_MINE_MEDIAN_M = 0.0   # vision_check's night median error (m) for the weights it used
EXPLAIN_NETWORKS = ""       # what did your networks do in the loop (night flight)? what makes these numbers
                            # optimistic, and what would you need to measure them honestly?

# ---- Step 12: your own test (my_scenario.json) -------------------------------------------------------------------
MY_METRIC = ""              # the metric your requirement uses (a name from campaign.py's measure(), e.g. "switch_s")
MY_OP = ""                  # "<=" or ">="
MY_LIMIT = 0.0              # its limit
MY_VALUE = 0.0              # the value your run measured (python3 campaign.py one <name>); None if it never happened
MY_VERDICT = ""             # "PASS" or "FAIL", from your run
EXPLAIN_MY_TEST = ""        # what does your scenario test, and why this requirement?
EXPLAIN_PROVES = ""         # what does this whole campaign prove about NAVERA Lite, and what does it NOT prove?
