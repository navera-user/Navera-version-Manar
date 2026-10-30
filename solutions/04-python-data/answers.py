# Lab 4 — reference answers (teacher only). The check accepts the tolerances written in check.py.

# ======== Session 1 ========
ROWS_RAW = 1402
MOST_ROWS_FLIGHT = "sahel_hills"
EMPTY_LAT_ROWS = 31
DROPNA_ROWS_LOST = 119
PREDICT_CLEAN = "About ten rows: some duplicates, the 9999 m altitude and maybe a zero position; duplicates most."
EXPLAIN_KEEP_NOFIX = ("A NO_FIX row is a real moment of the flight when no source had a position. Dropping it would "
                      "make the outages shorter than they were and hide the time the judge had nothing.")
FASTEST_SOURCE = "day"
PREDICT_RUNS = "[(0, 2), (4, 5), (6, 9)]"

# ======== Session 2 ========
CLOCK_FIX_S = {"sahel_hills": -3600.0}
SPEED_FACTOR = {"grid_survey": 1 / 3.6}
EXPLAIN_DETECTIVE = ("sahel_hills starts at 10:10:00 in the log but took off at 09:10:00 UTC on the sheet: exactly "
                     "3600 s, the logger kept local time (Tunisia is UTC+1), and it overlaps grid_survey with the same "
                     "drone. grid_survey's logged speed has a median of 71.9 while the positions give 20.0 m/s, a ratio "
                     "of 3.6: the column is in km/h, above the drone's 30 m/s limit.")
UNPLANNED_FLIGHT = "sousse_port"
UNPLANNED_START_UTC = "08:27:00"

PREDICT_NOISE = "gps: sqrt(2)*1.5/2 = 1.06, with the 0.3 logged noise 1.10 m/s; day: sqrt(2)*6/2 = 4.24, so 4.25 m/s."
EXPLAIN_ROBUST = ("Day vision has a few matches that jump 300 to 520 m, which give speed errors of 150 to 265 m/s; "
                  "squared, they dominate std (36 m/s) while the MAD only sees the typical errors (3.7 m/s). The robust "
                  "sigma is the noise, but a report must add the tail (p95, max) and the sample size. The median did "
                  "not protect the gps numbers from the km/h flight: a systematic error on a third of the rows moved "
                  "the median and raised the MAD from 1.19 to 1.98 m/s until it was corrected.")
