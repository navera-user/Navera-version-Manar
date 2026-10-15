# Lab 31 — your answers. Numbers without quotes (JAM_RECOVER_S = 3.4). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Messenger ========

# ---- Step 0: the bytes (python3 mav_lab.py hex) -----------------------------------------------------------------
PREDICT_FRAME = "10 header bytes + 65 payload + 2 checksum = 77 bytes, because GPS_INPUT has 65 bytes of fields"          # BEFORE running: how many bytes do you expect in ONE GPS_INPUT frame, and why?
HEADER_LEN_BYTE = 63         # the 'len' byte of the first GPS_INPUT frame, as a decimal number
EXPLAIN_63 = "MAVLink 2 drops the trailing zero bytes of the payload; the last field, yaw, is 0 (two zero bytes), so only 63 bytes travel. The receiver must pad the payload with zeros back to 65 bytes before unpacking it."             # why is it not 65, and what must a receiver do about it?

# ---- Steps 2–3: the recording through YOUR decoder (python3 mav_lab.py stream) ----------------------------------
STREAM_BAD_CRC = 2          # how many of them have crc_ok False
STREAM_LOST = 6             # your lost_frames on the good GPS_INPUT frames: lost …
STREAM_DOUBLED = 1          # … and doubled
VISION_FLAGS = 189            # the ignore_flags of the frames sent while day vision flew (satellites 0)
EXPLAIN_FLAGS = "189 = 1 + 4 + 8 + 16 + 32 + 128: the autopilot must ignore the altitude and the horizontal velocity. Day vision does not measure them, so NAVERA Lite flags them instead of inventing numbers."          # what do those frames tell the autopilot NOT to use, and why is that honest?
EXPLAIN_LOST = "A frame whose checksum is wrong is thrown away, so for the receiver it is lost: its seq is missing from the good frames. The 6 lost include the 2 damaged ones."           # the recording has 2 frames with a bad checksum: how do they show up in "lost"? why?

# ---- Step 4: the receiver's noise (python3 mav_lab.py noise) -----------------------------------------------------
PREDICT_AVERAGE = "Less than 7 times, because the receiver noise changes slowly and the 50 fixes are not independent."        # BEFORE running: you average the GPS noise over 10 s (50 fixes). By how much does the
                            # spread go down: about √50 ≈ 7 times, or less? why?
GM_SIGMA_MEASURED = 1.964     # the measured standard deviation of the hour of noise (m)
CORR_10S = 0.636              # your autocorrelation at 10 s
EXPLAIN_AVERAGE = "The samples are correlated: with tau = 20 s the noise 10 s later is still about 0.6 correlated, so 50 fixes in 10 s are worth only about one independent sample and the average keeps almost the whole spread (1.83 m instead of 0.27 m)."        # why do 10 s averages spread almost as much as single fixes?

# ---- Step 5: vision errors (python3 mav_lab.py rayleigh) ---------------------------------------------------------
PREDICT_RAYLEIGH_95 = "2.45 sigma: in 2-D the error adds two axes, so it needs more than the 1.96 of one axis."
EXPLAIN_MEDIAN = "sigma is the spread on each axis (east and north); the horizontal error combines both axes and follows a Rayleigh law whose median is 1.177 sigma, so sigma = 440 / 1.177 = 373.7 m."         # the 'measured' profile has a MEDIAN of 440 m. Why is its σ 373.7 m and not 440 m?

# ======== Session 2 — Test engineer ========

# ---- Step 6: a first flight (python3 -m navera_lite.sim.run campaign/jam.json) ---------------------------------
PREDICT_JAM = "A few seconds later: the judge waits for its hold-off of 2 s, and the guard first wants vision to agree with a GPS that comes back after an outage."            # BEFORE running: GPS jammed at 30 s, back at 70 s. When does NAVERA Lite use the GPS
                            # again: at 70 s, a little later, much later? why?
JAM_RECOVER_S = 3.4         # from the events: the time NAVERA Lite flies on the GPS again, minus 70 s

# ---- Step 8: expected values FROM THE RULES (before the campaign) -------------------------------------------------
EXPECT_OFF_SWITCH_S = 3.0   # GPS "off" (silent) at 30 s: after how many seconds should NAVERA Lite stop using it?
EXPECT_JUMP_GATE_M = 56.0    # the jump gate's reach for the next GPS fix (0.2 s later), drone: in metres
EXPECT_DRIFT_SIGMA_S_M = 15.42  # the σ_s (m) you passed to drift_alarm_time: the innovation σ on one axis
EXPECT_DRIFT_REFUSED_S = 16.0  # drift_alarm_time for the campaign's drift (lab Step 8 gives the numbers), in s

# ---- Step 9: the campaign (python3 campaign.py run, then report) -------------------------------------------------
DRIFT_MEASURED_S = 18.4      # the drift run's switch_s: when NAVERA Lite really stopped flying on the spoofed GPS
EXPLAIN_DRIFT = "The rule without noise gives 16 s; the run gives 18.4 s because each vision fix reaches the judge 0.3 s after the picture and the noise made one test agree, which reset the streak of 5. A requirement should use the rule plus a margin for noise and latency, not the exact theoretical value."          # expected vs measured: why are they not equal? which one would you put in a requirement?
FAILED = "R9"                 # the id of the requirement that FAILS (for example "R3")
EXPLAIN_FAIL = "The plane camera is 1.5 s late and its pictures are stamped when they arrive, so each vision fix is 60 m behind the plane (40 m/s x 1.5 s) but claims to be from now. The guard sees the honest GPS disagree with vision for 5 fixes and refuses it as a drift spoof, then flies on the 60 m wrong vision and keeps the GPS locked out. Stamping each picture at exposure fixes the guard (plane_delayed shows no refusal), but the autopilot fuses fixes on arrival, so a vision fix should also be carried to now with a grown sigma, as NAVERA does."
                            # (then confirm with campaign/plane_delayed.json, lab Step 9)

# ---- Step 10: your own stack (python3 campaign.py run --mine, then report --mine) --------------------------------
EXPLAIN_MINE = "I changed confirm_n from 2 to 6 in a copy of the guard and predicted that the GPS would come back later after an outage. R4 moved from PASS to FAIL: jam.recover_s went from 3.4 s to 7.4 s, because six agreeing vision fixes take four more seconds."

# ---- Step 11: your networks in the loop (python3 vision_check.py, then the night flight) -------------------------
NIGHT_MINE_MEDIAN_M = 25.43
EXPLAIN_NETWORKS = "At night the homography network located each thermal patch around the prior with a median error of about 25 m; it states sigma 21.6 m, below fix_max_sigma_m 25 m, so the night source flew FIX. The numbers are optimistic: the thermal pictures are synthetic and cut from the same reference the network matches against. An honest measurement needs real thermal frames from a real flight with a real camera."
                            # optimistic, and what would you need to measure them honestly?

# ---- Step 12: your own test (my_scenario.json) -------------------------------------------------------------------
MY_METRIC = "ap_max_err_m"              # the metric your requirement uses (a name from campaign.py's measure(), e.g. "switch_s")
MY_OP = "<="                  # "<=" or ">="
MY_LIMIT = 20.0              # its limit
MY_VALUE = 14.9              # the value your run measured (python3 campaign.py one <name>); None if it never happened
MY_VERDICT = "PASS"             # "PASS" or "FAIL", from your run
EXPLAIN_MY_TEST = "An IMU tilt bias of 3 degrees from 20 s, then the GPS jammed at 30 s: vision becomes the only source and is shifted 8 m. The requirement says the autopilot must stay within 20 m because the mission corridor is narrow."        # what does your scenario test, and why this requirement?
EXPLAIN_PROVES = "It proves behaviour: the rules, their timing, the decoding and the integration with the autopilot under the faults we injected. It does not prove real accuracy, because the sensors are models and the pictures are synthetic; that needs field tests."         # what does this whole campaign prove about NAVERA Lite, and what does it NOT prove?
